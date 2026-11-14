"""Staged continuation integration against tiny synthetic SQLite projects."""
import base64
import http.client
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

import test_local_workbench_http as http_fixtures
import test_retrieval_holdout as fixtures
from autoresearch import retrieval_holdout, staged_relevance_adapter as staged
from autoresearch.contracts import ResearchError, canonical, fingerprint
from autoresearch.local_workbench import LocalWorkbench
from autoresearch.project_controller import ProjectController


class StagedContinuationTests(unittest.TestCase):
    serve = http_fixtures.LocalWorkbenchHTTPTests.serve
    session = http_fixtures.LocalWorkbenchHTTPTests.session

    def request(self, server, path, method='GET', body=None, headers=None):
        connection = http.client.HTTPConnection('127.0.0.1', server.server_port, timeout=60)
        self.addCleanup(connection.close)
        raw = canonical(body).encode('utf-8') if body is not None else None
        connection.request(method, path, body=raw, headers=headers or {})
        response = connection.getresponse()
        return response.status, json.loads(response.read())

    def setUp(self):
        self.temp = self.enterContext(tempfile.TemporaryDirectory())
        helper = fixtures.RetrievalHoldoutTests()
        self.addCleanup(helper.doCleanups)
        project, _, holdout = helper.fixture()
        self.manager = LocalWorkbench(Path(self.temp) / 'manager')
        imported = self.manager.import_project(request_id='import', workspace=project.root)
        self.project_id = imported['project_id']
        self.manager.select({'request_id': 'select', 'project_id': self.project_id})
        self.project, _ = self.manager.binding()
        self.manager.register_holdout({'request_id': 'holdout', 'project_id': self.project_id,
            'expected_state_version': self.project.status()['state_version'],
            'holdout_base64': base64.b64encode(holdout).decode()})
        self.enterContext(patch('sklearn.linear_model.Ridge.fit', side_effect=AssertionError('No fitting')))
        self.enterContext(patch('sklearn.preprocessing.StandardScaler.fit', side_effect=AssertionError('No fitting')))
        self.enterContext(patch('autoresearch.host_model_selection.run_claude_selection', side_effect=AssertionError('No model')))
        self.primary = self.project.step(request_id='synthetic-primary', expected_state_version=self.project.status()['state_version'])
        self.body = {'request_id': 'staged-run', 'project_id': self.project_id,
                     'expected_state_version': self.project.status()['state_version'], 'primary_action_id': self.primary['id'],
                     'reason': 'Authorize the original two synthetic followups and report.'}

    def assert_code(self, code, callback, *args):
        with self.assertRaises(ResearchError) as caught:
            callback(*args)
        self.assertEqual(caught.exception.code, code)

    def test_http_exact_original_sequence_replay_report_and_busy_gate(self):
        server = self.serve(local_workspace=self.manager, allow_local_actions=True)
        headers = self.session(server)
        original_export = self.manager._export
        def verify_busy(body, *, staged_parent=None):
            self.assertEqual(staged_parent, self.body['request_id'])
            self.assert_code('OPERATION_INCOMPLETE', original_export,
                {'request_id': 'foreign-report', 'project_id': self.project_id,
                 'expected_state_version': self.project.status()['state_version']})
            self.assert_code('OPERATION_INCOMPLETE', self.manager.save_plan,
                {'request_id': 'foreign-plan', 'project_id': self.project_id,
                 'expected_state_version': self.project.status()['state_version'],
                 'plan': {'question': 'No', 'basis': 'No', 'steps': 'No', 'expected_feedback': 'No'}, 'reason': 'No'})
            return original_export(body, staged_parent=staged_parent)
        with patch.object(self.manager, '_export', side_effect=verify_busy):
            started = time.monotonic()
            status, result = self.request(server, '/api/local-workbench/staged-continue', 'POST', self.body, headers)
            elapsed = time.monotonic() - started
        print('synthetic_loopback_staged_seconds=%.3f' % elapsed, flush=True)
        self.assertEqual((status, result['status'], result['phase']), (200, 'completed', 'done'))
        self.assertEqual([a['command'] for a in self.project.status()['actions']],
                         [staged.TOOL_ID, staged.AUDIT_TOOL_ID, retrieval_holdout.FINAL_TOOL_ID])
        self.assertEqual(self.project.status()['budget']['local_tool_calls_used'], 3)
        self.assertEqual((self.project.status()['budget']['new_fits'], self.project.status()['budget']['new_model_requests']), (0, 0))
        self.assertEqual(self.request(server, '/api/local-workbench/staged-continue/staged-run.json'), (200, result))
        self.assertEqual(LocalWorkbench(self.manager.root).continue_staged(self.body), result)
        self.assert_code('IDEMPOTENCY_CONFLICT', self.manager.continue_staged, {**self.body, 'reason': 'Changed'})
        self.assertEqual(len(list((self.manager.root / 'reports').iterdir())), 1)
        report = next((self.manager.root / 'reports').iterdir()) / 'report.md'
        report.write_bytes(report.read_bytes() + b'changed')
        self.assert_code('EVIDENCE_CHANGED', self.manager.continue_staged, self.body)

    def test_interruption_after_audit_recovers_exact_parent_and_child(self):
        original = self.manager._save_staged_continuation
        def interrupted(record):
            if record['phase'] == 'freeze' and record['steps']['audit']['status'] == 'completed':
                raise KeyboardInterrupt('Synthetic manager interruption after audit commit')
            return original(record)
        with patch.object(self.manager, '_save_staged_continuation', side_effect=interrupted):
            with self.assertRaises(KeyboardInterrupt):
                self.manager.continue_staged(self.body)
        saved = self.manager.staged_continuation_record('staged-run')
        self.assertEqual(saved['phase'], 'audit')
        audit_id = saved['steps']['audit']['body']['request_id']
        audit_parent = ProjectController._parent(self.project.status(), audit_id)
        self.assertEqual(audit_parent['status'], 'completed')
        self.assert_code('OPERATION_INCOMPLETE', self.manager.continue_staged, {**self.body, 'request_id': 'replacement'})
        result = LocalWorkbench(self.manager.root).continue_staged(self.body)
        self.assertEqual((result['status'], result['steps']['audit']['reference']['parent_request_id']), ('completed', audit_id))
        self.assertEqual(len([a for a in self.project.status()['actions'] if a['command'] == staged.AUDIT_TOOL_ID]), 1)

    def test_unknown_final_does_not_redispatch_or_change_request(self):
        with patch.object(retrieval_holdout, '_verified_private', side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                self.manager.continue_staged(self.body)
        saved = self.manager.staged_continuation_record('staged-run')
        self.assertEqual(saved['phase'], 'final')
        final_id = saved['steps']['final']['body']['request_id']
        original_actions = self.project.status()['actions']
        self.assertEqual(len(list((self.project.root / retrieval_holdout.PRIVATE_DIR).glob('execution-*.json'))), 1)
        with patch.object(retrieval_holdout.FINAL, 'execute_project', side_effect=AssertionError('No redispatch')):
            stopped = LocalWorkbench(self.manager.root).continue_staged(self.body)
            self.assertEqual((stopped['status'], stopped['phase']), ('incomplete', 'final'))
            self.assertEqual(stopped['steps']['final']['body']['request_id'], final_id)
            self.assertEqual(self.project.status()['actions'], original_actions)
            self.assert_code('OPERATION_INCOMPLETE', self.manager.continue_staged, {**self.body, 'request_id': 'replacement'})
        self.assertEqual(len(list((self.project.root / retrieval_holdout.PRIVATE_DIR).glob('execution-*.json'))), 1)

    def test_saved_step_body_tamper_never_dispatches(self):
        original_save = self.manager._save_staged_continuation
        def interrupted(record):
            original_save(record)
            if record['phase'] == 'audit' and record['steps'].get('audit', {}).get('status') == 'prepared':
                raise KeyboardInterrupt('Synthetic after frozen step')
        with patch.object(self.manager, '_save_staged_continuation', side_effect=interrupted):
            with self.assertRaises(KeyboardInterrupt):
                self.manager.continue_staged(self.body)
        before = self.project.status()
        with self.manager._connect() as con:
            row = con.execute("SELECT record FROM requests WHERE id=?", (self.body['request_id'],)).fetchone()
            record = json.loads(row['record'])
            record['steps']['audit']['body']['proposal']['rationale'] = 'Changed after authorization.'
            record['record_sha256'] = fingerprint({k: v for k, v in record.items() if k != 'record_sha256'})
            self.manager._save(con, self.body['request_id'], record)
        stopped = self.manager.continue_staged(self.body)
        self.assertEqual((stopped['status'], stopped['stop']['code']), ('incomplete', 'EVIDENCE_CHANGED'))
        self.assertEqual(self.project.status(), before)

    def _assert_prepared_stage_tamper(self, phase):
        original_save = self.manager._save_staged_continuation
        def interrupted(record):
            original_save(record)
            if record['phase'] == phase and record['steps'].get(phase, {}).get('status') == 'prepared':
                raise KeyboardInterrupt('Synthetic after frozen ' + phase)
        with patch.object(self.manager, '_save_staged_continuation', side_effect=interrupted):
            with self.assertRaises(KeyboardInterrupt):
                self.manager.continue_staged(self.body)
        before = self.project.status()
        with self.manager._connect() as con:
            row = con.execute("SELECT record FROM requests WHERE id=?", (self.body['request_id'],)).fetchone()
            record = json.loads(row['record'])
            if phase == 'freeze':
                record['steps'][phase]['body']['primary_action_id'] = 'other-primary'
            elif phase == 'final':
                record['steps'][phase]['body']['proposal']['rationale'] = 'Altered after authorization.'
            else:
                record['steps'][phase]['body']['request_id'] = 'other-report'
            record['record_sha256'] = fingerprint({k: v for k, v in record.items() if k != 'record_sha256'})
            self.manager._save(con, self.body['request_id'], record)
        stopped = self.manager.continue_staged(self.body)
        self.assertEqual((stopped['status'], stopped['stop']['code']), ('incomplete', 'EVIDENCE_CHANGED'))
        self.assertEqual(self.project.status(), before)
        self.assertFalse((self.manager.root / 'reports').exists())

    def test_frozen_strategy_body_tamper_never_executes(self):
        self._assert_prepared_stage_tamper('freeze')

    def test_frozen_final_body_tamper_never_dispatches(self):
        self._assert_prepared_stage_tamper('final')

    def test_frozen_report_body_tamper_never_exports(self):
        self._assert_prepared_stage_tamper('report')

    def test_existing_original_audit_and_freeze_are_reused(self):
        from autoresearch import staged_continuation
        context = ProjectController(self.project.root).selection_context()
        primary = {'action_id': self.primary['id'], 'request_id': self.primary['request_id'],
                   'result_sha256': self.primary['result_sha256']}
        proposal = staged_continuation.selection_proposal(context, staged.AUDIT_TOOL_ID, primary)
        response = ProjectController(self.project.root).advance_selection(request_id='existing-audit', proposal=proposal,
                                                                           expected_state_version=context['state_version'])
        self.assertEqual(response['status'], 'completed')
        self.project.freeze_retrieval_strategy(request_id='existing-freeze', expected_state_version=self.project.status()['state_version'],
                                               primary_action_id=self.primary['id'])
        body = {**self.body, 'expected_state_version': self.project.status()['state_version']}
        completed = self.manager.continue_staged(body)
        self.assertEqual(completed['status'], 'completed')
        self.assertTrue(completed['steps']['audit']['reused'])
        self.assertTrue(completed['steps']['freeze']['reused'])
        self.assertEqual(completed['steps']['audit']['reference']['parent_request_id'], 'existing-audit')
        self.assertEqual(completed['steps']['freeze']['reference']['request_id'], 'existing-freeze')
        self.assertEqual(self.project.status()['budget']['local_tool_calls_used'], 3)

    def test_completed_report_without_manager_receipt_never_reexports(self):
        from autoresearch import project_report
        original = project_report.export_report
        def interrupted(**kwargs):
            original(**kwargs)
            raise KeyboardInterrupt('Synthetic after report publication before manager receipt')
        with patch.object(project_report, 'export_report', side_effect=interrupted):
            with self.assertRaises(KeyboardInterrupt):
                self.manager.continue_staged(self.body)
        saved = self.manager.staged_continuation_record(self.body['request_id'])
        self.assertEqual(saved['phase'], 'report')
        report_id = saved['steps']['report']['body']['request_id']
        self.assertEqual(len(list((self.manager.root / 'reports').iterdir())), 1)
        with patch.object(project_report, 'export_report', side_effect=AssertionError('No re-export')):
            stopped = LocalWorkbench(self.manager.root).continue_staged(self.body)
        self.assertEqual((stopped['status'], stopped['phase'], stopped['stop']['code']),
                         ('incomplete', 'report', 'OPERATION_INCOMPLETE'))
        self.assertEqual(stopped['steps']['report']['body']['request_id'], report_id)
        self.assert_code('OPERATION_INCOMPLETE', self.manager.continue_staged, {**self.body, 'request_id': 'replacement'})
        self.assertEqual(len(list((self.manager.root / 'reports').iterdir())), 1)


if __name__ == '__main__':
    unittest.main()
