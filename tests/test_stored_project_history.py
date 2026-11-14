"""Synthetic saved plans, report metadata and cross-record bindings only."""
import hashlib
import http.client
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import threading
import unittest
from unittest.mock import patch

from autoresearch.local_workbench import LocalWorkbench
from autoresearch import stored_project_summary, stored_project_history, project_workbench


def encode(value):
    return json.dumps(value, separators=(',', ':')).encode()


class StoredProjectHistoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'manager'; LocalWorkbench(self.root)
        self.pid, self.slot, self.report_slot = 'project-fixture', 'a' * 64, 'b' * 64
        self.db = self.root / 'projects' / self.slot / 'project.sqlite'; self.db.parent.mkdir(parents=True)
        self.plans = [{'version': n, 'request_id': f'plan-{n}', 'based_on_state_version': n, 'question': f'question {n}',
                       'basis': f'basis {n}', 'steps': f'steps {n}', 'expected_feedback': f'feedback {n}', 'reason': f'reason {n}'} for n in (1, 2)]
        self.controllers = [{'project_id': self.pid, 'request_id': 'advance-1', 'status': 'completed', 'child_request_id': 'child-1',
                             'decision': {'next_action': {'kind': 'conditional_proposal', 'execution_status': 'not_executed'}},
                             'selection_context': {'research_plan': self.plans[0]}},
                            {'project_id': self.pid, 'request_id': 'advance-2', 'status': 'waiting', 'child_request_id': None,
                             'decision': {'next_action': {'kind': 'external_wait', 'execution_status': 'not_executed'}},
                             'selection_context': {'research_plan': self.plans[1]}}]
        self.project = {'schema_version': 'local-research-project-v3', 'id': self.pid, 'run_id': 'run-fixture',
                        'state_version': 13, 'code_identity': 'fixture-native', 'runtime_dependencies': {},
                        'budget': {'local_tool_call_limit': 2, 'historical_spend_cny': None},
                        'plan_revisions': self.plans, 'controller_requests': self.controllers}
        action = {'id': 'action-fixture', 'request_id': 'child-1', 'project_id': self.pid, 'run_id': 'run-fixture',
                  'status': 'completed', 'command': 'fixture.method', 'code_identity': 'fixture-native'}
        with sqlite3.connect(self.db) as con:
            con.executescript('CREATE TABLE project(id INTEGER PRIMARY KEY, record TEXT NOT NULL);'
                              'CREATE TABLE actions(request_id TEXT PRIMARY KEY, fingerprint TEXT NOT NULL, record TEXT NOT NULL);')
            con.execute('INSERT INTO project VALUES(1,?)', (encode(self.project).decode(),))
            con.execute('INSERT INTO actions VALUES(?,?,?)', (action['request_id'], 'unused', encode(action).decode()))
        report_dir = self.root / 'reports' / self.report_slot; report_dir.mkdir(parents=True)
        self.report_dir = report_dir
        report = {'schema_version': 'research-project-report-v1', 'project_id': self.pid,
                  'project_snapshot_ref': 'fixture-snapshot', 'project': {'state_version': 13}, 'title': 'fixture report',
                  'exporter_code_identity': 'fixture-exporter', 'scientific_validation': False}
        report_raw = encode(report); (report_dir / 'report.json').write_bytes(report_raw)
        declared = {'report.json': {'bytes': len(report_raw), 'sha256': hashlib.sha256(report_raw).hexdigest()},
                    **{name: {'bytes': 5, 'sha256': 'c' * 64} for name in ('report.pdf', 'report.md', 'input.json')}}
        manifest = {'schema_version': 'project-report-export-v1', 'project_id': self.pid,
                    'project_snapshot_ref': 'fixture-snapshot', 'files': declared}
        (report_dir / 'manifest.json').write_bytes(encode(manifest))
        self.manager_db = self.root / 'workbench.sqlite'
        with sqlite3.connect(self.manager_db) as con:
            con.execute("INSERT INTO metadata VALUES('active_project_id',?)", (self.pid,))
            con.execute('INSERT INTO projects VALUES(?,?,?,?)', (self.pid, 'fixture', self.slot, self.report_slot))
            for plan in self.plans:
                self.insert_receipt(con, plan['request_id'], 'save_plan', 'completed', {'status': 'completed', 'research_plan': plan})
            for name in ('advance-1', 'advance-2'):
                self.insert_receipt(con, name, 'advance', 'preparing', None)
            self.insert_receipt(con, 'report-1', 'export', 'completed', {'status': 'exported'},
                                report_slot=self.report_slot, snapshot_ref='fixture-snapshot', state_version=13)

    def insert_receipt(self, con, request_id, command, status, result, **intent):
        if result is not None:
            result = {**result, 'project_id': self.pid, 'request_id': request_id}
        record = {'status': status, 'result': result, 'intent': {'project_id': self.pid, **intent}}
        con.execute('INSERT INTO requests VALUES(?,?,?,?)', (request_id, 'unused', command, encode(record).decode()))

    def write_project(self):
        with sqlite3.connect(self.db) as con:
            con.execute('UPDATE project SET record=?', (encode(self.project).decode(),))

    def snapshot(self):
        return {str(path.relative_to(self.root)): hashlib.sha256(path.read_bytes()).hexdigest()
                for path in self.root.rglob('*') if path.is_file()}

    def test_saved_plan_bindings_and_report_are_distinct_and_read_only(self):
        before = self.snapshot()
        opened = []
        original_open = os.open
        def track_open(path, *args, **kwargs):
            opened.append(Path(path).name)
            return original_open(path, *args, **kwargs)
        with patch('autoresearch.research_project.ResearchProject.__init__', side_effect=AssertionError('no runtime')), \
             patch.object(stored_project_history.os, 'open', side_effect=track_open):
            result = stored_project_summary.read_stored_project_summary(self.root)
        self.assertEqual(set(opened), {'manifest.json', 'report.json'})
        self.assertEqual(result['status'], 'available')
        history = result['stored_history']; self.assertEqual(history['status'], 'available')
        first, waiting = history['plans']; self.assertEqual(first['revision'], self.plans[0])
        self.assertEqual(first['manager_receipt']['record_status'], 'completed')
        self.assertEqual(first['manager_receipt']['plan_binding_status'], 'matched')
        parent = first['controllers'][0]
        self.assertEqual(parent['status'], 'completed')
        self.assertEqual(parent['decision_next_action']['execution_status'], 'not_executed')
        self.assertEqual(parent['manager_receipt']['record_status'], 'preparing')
        self.assertTrue(parent['manager_receipt']['result_recorded']); self.assertFalse(parent['manager_receipt']['result_present'])
        self.assertEqual(parent['matched_action']['status'], 'completed')
        self.assertEqual(waiting['controllers'][0]['status'], 'waiting')
        self.assertEqual(waiting['controllers'][0]['child_binding_status'], 'explicit_null')
        self.assertIsNone(waiting['controllers'][0]['matched_action'])
        report = result['stored_report']; self.assertEqual((report['status'], report['currentness']), ('available', 'unknown'))
        self.assertEqual(report['metadata']['saved_project_state_version'], 13)
        self.assertEqual(len(report['declared_files']), 4)
        self.assertEqual(report['declaration_scope'], 'manifest_declarations_only_report_json_checked')
        self.assertFalse((self.report_dir / 'report.pdf').exists())
        self.assertEqual(self.snapshot(), before)

    def test_mismatch_and_missing_child_never_fabricate_relationship(self):
        self.project['controller_requests'][0]['selection_context']['research_plan'] = dict(self.plans[0], reason='different')
        self.project['controller_requests'][1].pop('child_request_id')
        self.write_project()
        history = stored_project_summary.read_stored_project_summary(self.root)['stored_history']
        self.assertEqual(history['status'], 'partial')
        self.assertEqual(history['plans'][0]['controllers'], [])
        self.assertEqual(history['unmatched_controllers'][0]['request_id'], 'advance-1')
        self.assertEqual(history['plans'][1]['controllers'][0]['child_binding_status'], 'not_recorded')

    def test_cross_project_invalid_report_and_missing_records_are_local(self):
        self.project['controller_requests'][0]['project_id'] = 'different-project'; self.write_project()
        result = stored_project_summary.read_stored_project_summary(self.root)
        self.assertEqual(result['stored_history']['status'], 'integrity_error')
        self.assertEqual(result['stored_budget'], self.project['budget'])
        with sqlite3.connect(self.manager_db) as con:
            con.execute('UPDATE projects SET report=?', ('../unsafe',))
        result = stored_project_summary.read_stored_project_summary(self.root)
        self.assertEqual(result['stored_report']['status'], 'integrity_error')
        self.assertIsNone(result['stored_report']['slot'])
        self.assertEqual(result['stored_budget'], self.project['budget'])
        self.project.pop('controller_requests'); self.write_project()
        history = stored_project_summary.read_stored_project_summary(self.root)['stored_history']
        self.assertEqual(history['status'], 'partial')
        self.assertIsNone(history['plans'][0]['controllers'])

    def test_report_unavailable_or_incomplete_never_claims_current(self):
        (self.report_dir / 'manifest.json').unlink()
        report = stored_project_summary.read_stored_project_summary(self.root)['stored_report']
        self.assertEqual((report['status'], report['currentness']), ('unavailable', 'unknown'))
        self.assertNotIn('declared_files', report)

    def test_incomplete_export_receipt_cannot_make_report_available(self):
        with sqlite3.connect(self.manager_db) as con:
            record = {'status': 'preparing', 'result': None,
                      'intent': {'project_id': self.pid, 'report_slot': self.report_slot, 'snapshot_ref': 'fixture-snapshot'}}
            con.execute("UPDATE requests SET record=? WHERE id='report-1'", (encode(record).decode(),))
        report = stored_project_summary.read_stored_project_summary(self.root)['stored_report']
        self.assertEqual((report['status'], report['currentness']), ('partial', 'unknown'))
        self.assertEqual(report['export_receipt']['record_status'], 'preparing')
        self.assertFalse(report['export_receipt']['result_present'])

    def test_plan_receipt_mismatch_or_missing_keeps_original_status_without_false_binding(self):
        for saved, expected in ((dict(self.plans[0], reason='different'), 'integrity_error'), (None, 'partial')):
            with self.subTest(expected=expected), sqlite3.connect(self.manager_db) as con:
                result = {'status': 'completed', 'project_id': self.pid, 'request_id': 'plan-1'}
                if saved is not None:
                    result['research_plan'] = saved
                record = {'status': 'completed', 'result': result, 'intent': {'project_id': self.pid}}
                con.execute("UPDATE requests SET record=? WHERE id='plan-1'", (encode(record).decode(),))
            history = stored_project_summary.read_stored_project_summary(self.root)['stored_history']
            receipt = history['plans'][0]['manager_receipt']
            self.assertEqual((receipt['view_status'], receipt['record_status']), (expected, 'completed'))
            self.assertNotEqual(receipt['plan_binding_status'], 'matched')
            self.assertEqual(history['status'], 'partial')

    def test_export_missing_snapshot_is_partial_but_keeps_metadata(self):
        with sqlite3.connect(self.manager_db) as con:
            record = {'status': 'completed', 'result': {'status': 'exported', 'project_id': self.pid, 'request_id': 'report-1'},
                      'intent': {'project_id': self.pid, 'report_slot': self.report_slot, 'state_version': 13}}
            con.execute("UPDATE requests SET record=? WHERE id='report-1'", (encode(record).decode(),))
        report = stored_project_summary.read_stored_project_summary(self.root)['stored_report']
        self.assertEqual((report['status'], report['currentness']), ('partial', 'unknown'))
        self.assertEqual(report['metadata']['title'], 'fixture report')
        self.assertEqual(report['export_receipt']['record_status'], 'completed')

    def test_project_summary_http_and_history_source_drift(self):
        self.assertIn(Path(stored_project_history.__file__).resolve(), project_workbench._runtime_sources())
        marker = Path(self.temp.name) / 'source.py'; marker.write_text('before')
        with patch.object(project_workbench, '_runtime_sources', return_value={marker: marker.read_bytes()}):
            server = project_workbench.create_project_server(local_workspace=LocalWorkbench.open_readonly(self.root), port=0)
        thread = threading.Thread(target=lambda: server.serve_forever(poll_interval=.01), daemon=True); thread.start()
        self.addCleanup(thread.join, 2); self.addCleanup(server.server_close); self.addCleanup(server.shutdown)
        def request():
            conn = http.client.HTTPConnection('127.0.0.1', server.server_port, timeout=5)
            try:
                conn.request('GET', '/api/local-workbench/project-summary')
                response = conn.getresponse(); return response.status, json.loads(response.read())
            finally:
                conn.close()
        status, body = request()
        self.assertEqual((status, body['stored_history']['plans'][0]['revision']['request_id']), (200, 'plan-1'))
        marker.write_text('after')
        status, body = request()
        self.assertEqual((status, body['code']), (409, 'WORKBENCH_RESTART_REQUIRED'))

    def test_history_display_bound_does_not_remove_budget(self):
        self.project['plan_revisions'][0]['basis'] = 'x' * (stored_project_history._MAX_HISTORY + 1)
        self.write_project()
        result = stored_project_summary.read_stored_project_summary(self.root)
        self.assertEqual(result['stored_history']['status'], 'partial')
        self.assertIsNone(result['stored_history']['plans'])
        self.assertEqual(result['stored_budget'], self.project['budget'])
        self.assertLess(len(encode(result)), 300000)


if __name__ == '__main__':
    unittest.main()
