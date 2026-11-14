"""Manager receipt reconciliation with isolated wait and mocked-core fixtures; no fit or solver."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from autoresearch import tabular_quality_adapter
from autoresearch.contracts import ResearchError, canonical, fingerprint
from autoresearch.local_workbench import LocalWorkbench
from autoresearch.project_controller import ProjectController
import test_local_workbench as workbench_fixtures


class LocalAdvanceReceiptTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.manager = LocalWorkbench(Path(self.temp.name) / 'manager')
        self.created = self.manager.create(workbench_fixtures.LocalWorkbenchTests.create_body(self))
        self.project, _ = self.manager.binding()

    def wait_body(self, request_id='wait-fixture'):
        context = ProjectController(self.project.root).selection_context()
        return {'request_id': request_id, 'project_id': self.created['project_id'],
                'expected_state_version': context['state_version'],
                'proposal': workbench_fixtures.LocalWorkbenchTests.proposal(self, context)}

    def receipt(self, request_id):
        with self.manager._connect(readonly=True) as con:
            row = con.execute('SELECT digest,command,record FROM requests WHERE id=?', (request_id,)).fetchone()
        return row['digest'], row['command'], json.loads(row['record'])

    def mock_response(self, body, status, *, replayed=False):
        response = {'schema_version': 'project-controller-advance-v1', 'project_id': body['project_id'],
                'request_id': body['request_id'], 'request_sha256': 'a' * 64, 'status': status,
                'replayed': replayed, 'decision': {'reason': 'synthetic'}, 'child_request_id': None,
                'result': None, 'scientific_validation': False}
        if status == 'completed':
            response['child_request_id'] = 'mock-child'
            response['result'] = {'child': {'request_id': 'mock-child', 'status': 'completed'}}
        return response

    def test_real_wait_persists_exact_response_and_always_asks_core_on_replay(self):
        body = self.wait_body()
        with patch.object(tabular_quality_adapter, 'execute', side_effect=AssertionError('no tools')):
            result = self.manager.advance(body)
            self.assertEqual((result['status'], result['child_request_id']), ('waiting', None))
            before = self.project.status()
            original = ProjectController.advance_selection
            with patch.object(ProjectController, 'advance_selection', autospec=True, side_effect=original) as core:
                replay = self.manager.advance(body)
                core.assert_called_once()
            self.assertTrue(replay['replayed']); self.assertEqual(self.project.status(), before)
        digest, command, record = self.receipt(body['request_id'])
        self.assertEqual((digest, command, record['status']), (fingerprint(body), 'advance', 'waiting'))
        self.assertEqual(record['result'], result)
        self.assertNotEqual(record['intent']['request_sha256'], result['request_sha256'])
        self.assertEqual(self.project.status()['actions'], [])

    def test_real_recipe_wait_receipt_replay(self):
        state = self.project.status()
        recipe = {'schema_version': 'research-recipe-v1', 'id': 'fixture-wait', 'version': 1,
                  'question': 'Should the synthetic fixture wait?', 'scope_match': {'domain': 'unmatched', 'contract': 'fixture'},
                  'need': 'next_check', 'ordered_methods': [{'method_id': 'fixture.never', 'evaluation_ref': 'fixture'}],
                  'on_no_match': 'wait'}
        body = {'request_id': 'recipe-wait', 'project_id': self.created['project_id'],
                'expected_state_version': state['state_version'], 'recipe': recipe}
        with patch.object(tabular_quality_adapter, 'execute', side_effect=AssertionError('no tools')):
            result = self.manager.advance_recipe(body)
            self.assertEqual(result['status'], 'waiting')
            self.assertTrue(self.manager.advance_recipe(body)['replayed'])
        _, command, record = self.receipt(body['request_id'])
        self.assertEqual((command, record['status'], record['result']['recipe_decision']['recipe']), ('advance_recipe', 'waiting', recipe))
        self.assertEqual(self.project.status()['actions'], [])

    def test_lost_manager_write_recovers_original_wait_id(self):
        body = self.wait_body('interrupted-wait'); original = self.manager._save
        def interrupt(con, request_id, record):
            if request_id == body['request_id'] and record['status'] == 'waiting':
                raise KeyboardInterrupt('fixture after durable core wait')
            return original(con, request_id, record)
        with patch.object(self.manager, '_save', side_effect=interrupt):
            with self.assertRaises(KeyboardInterrupt): self.manager.advance(body)
        self.assertEqual(self.receipt(body['request_id'])[2]['status'], 'preparing')
        before = self.project.status()
        self.assertEqual(before['controller_requests'][-1]['status'], 'waiting')
        result = self.manager.advance(body)
        self.assertTrue(result['replayed']); self.assertEqual(self.project.status(), before)
        self.assertEqual(self.receipt(body['request_id'])[2]['status'], 'waiting')

    def test_mocked_unknown_to_completed_preserves_unknown_and_same_request(self):
        body = self.wait_body('mock-unknown')
        responses = [self.mock_response(body, 'unknown'), self.mock_response(body, 'completed', replayed=True)]
        with patch.object(ProjectController, 'advance_selection', autospec=True, side_effect=responses) as core:
            self.assertEqual(self.manager.advance(body)['status'], 'unknown')
            self.assertEqual(self.receipt(body['request_id'])[2]['status'], 'unknown')
            self.assertEqual(self.manager.advance(body)['status'], 'completed')
            self.assertEqual(core.call_count, 2)
            self.assertTrue(all(call.kwargs['request_id'] == body['request_id'] for call in core.call_args_list))
        _, _, record = self.receipt(body['request_id'])
        self.assertEqual(record['status'], 'completed')
        self.assertEqual(record['previous_unknown']['status'], 'unknown')
        self.assertEqual(record['result']['status'], 'completed')
        self.assertEqual(self.project.status()['actions'], [])

    def test_mocked_malformed_completed_and_unknown_drift_do_not_overwrite(self):
        bad = self.wait_body('bad-completed')
        fake = self.mock_response(bad, 'completed'); fake['result']['child']['request_id'] = 'different-child'
        with patch.object(ProjectController, 'advance_selection', autospec=True, return_value=fake):
            with self.assertRaises(ResearchError) as error: self.manager.advance(bad)
            self.assertEqual(error.exception.code, 'EVIDENCE_CHANGED')
        self.assertEqual(self.receipt(bad['request_id'])[2]['status'], 'preparing')
        body = self.wait_body('unknown-drift')
        first = self.mock_response(body, 'unknown'); changed = copy.deepcopy(first)
        changed['decision']['reason'] = 'changed core decision'; changed['replayed'] = True
        with patch.object(ProjectController, 'advance_selection', autospec=True, side_effect=[first, changed]):
            self.manager.advance(body)
            with self.assertRaises(ResearchError) as error: self.manager.advance(body)
            self.assertEqual(error.exception.code, 'EVIDENCE_CHANGED')
        saved = self.receipt(body['request_id'])[2]
        self.assertEqual(saved['status'], 'unknown'); self.assertEqual(saved['result'], first)

    def test_unfinished_manager_with_no_core_parent_still_invokes_core_and_keeps_original_error(self):
        body = self.wait_body('no-parent')
        with self.manager._connect() as con:
            self.manager._accept(con, body, fingerprint(body), 'advance', {'project_id': body['project_id'], 'request_sha256': fingerprint(body)})
        with patch.object(ProjectController, 'advance_selection', autospec=True, side_effect=ResearchError('CODE_CHANGED', 'fixture core rejection')) as core:
            with self.assertRaises(ResearchError) as error: self.manager.advance(body)
            self.assertEqual(error.exception.code, 'CODE_CHANGED'); core.assert_called_once()
        self.assertEqual(self.receipt(body['request_id'])[2]['status'], 'preparing')
        self.assertEqual(self.project.status()['controller_requests'] if 'controller_requests' in self.project.status() else [], [])

    def test_mock_prepared_parent_without_child_still_uses_original_core_path(self):
        body = self.wait_body('prepared-fixture')
        with self.manager._connect() as con:
            self.manager._accept(con, body, fingerprint(body), 'advance', {'project_id': body['project_id'], 'request_sha256': fingerprint(body)})
        with self.project._writer(), self.project._connect() as con:
            state = self.project._project(con)
            state['controller_requests'] = [{'request_id': body['request_id'], 'project_id': body['project_id'],
                                             'status': 'prepared', 'child_request_id': 'fixture-missing-child'}]
            self.project._save(con, state)
        with patch.object(ProjectController, 'advance_selection', autospec=True, side_effect=ResearchError('PROJECT_BUSY', 'fixture core')) as core:
            with self.assertRaises(ResearchError) as error: self.manager.advance(body)
            self.assertEqual(error.exception.code, 'PROJECT_BUSY'); core.assert_called_once()
        self.assertEqual(self.receipt(body['request_id'])[2]['status'], 'preparing')

    def test_preparing_receipt_without_result_is_not_overwritten(self):
        body = self.wait_body('missing-result')
        with self.manager._connect() as con:
            record = self.manager._accept(con, body, fingerprint(body), 'advance', {'project_id': body['project_id'], 'request_sha256': fingerprint(body)})
            record.pop('result'); self.manager._save(con, body['request_id'], record)
        with patch.object(ProjectController, 'advance_selection', autospec=True) as core:
            with self.assertRaises(ResearchError) as error: self.manager.advance(body)
            self.assertEqual(error.exception.code, 'EVIDENCE_CHANGED'); core.assert_not_called()
        self.assertEqual(self.receipt(body['request_id'])[2], record)

    def test_unknown_adapter_interruption_is_not_redispatched(self):
        context = ProjectController(self.project.root).selection_context()
        proposal = workbench_fixtures.LocalWorkbenchTests.proposal(self, context, tabular_quality_adapter.TOOL_ID)
        body = {'request_id': 'unknown-fixture', 'project_id': self.created['project_id'],
                'expected_state_version': context['state_version'], 'proposal': proposal}
        with patch.object(tabular_quality_adapter, 'execute', side_effect=KeyboardInterrupt) as execute:
            with self.assertRaises(KeyboardInterrupt): self.manager.advance(body)
            response = self.manager.advance(body)
            self.assertEqual(response['status'], 'unknown')
            self.assertEqual(self.manager.advance(body)['status'], 'unknown')
            execute.assert_called_once()
        state = self.project.status(); self.assertEqual(state['budget']['local_tool_calls_reserved'], 1)
        self.assertEqual(self.receipt(body['request_id'])[2]['status'], 'unknown')

    def test_terminal_and_unknown_tampering_is_not_overwritten(self):
        body = self.wait_body('tamper-fixture'); result = self.manager.advance(body)
        with self.manager._connect() as con:
            _, _, record = self.receipt(body['request_id'])
            record['result']['decision']['reason'] = 'tampered'
            self.manager._save(con, body['request_id'], record)
        original = ProjectController.advance_selection
        with patch.object(ProjectController, 'advance_selection', autospec=True, side_effect=original) as core:
            with self.assertRaises(ResearchError) as error: self.manager.advance(body)
            self.assertEqual(error.exception.code, 'EVIDENCE_CHANGED'); core.assert_called_once()
        self.assertEqual(self.receipt(body['request_id'])[2]['result']['decision']['reason'], 'tampered')
        for outer, wrong in (('waiting', 'completed'), ('unknown', 'waiting')):
            with self.subTest(outer=outer):
                with self.manager._connect() as con:
                    record['status'] = outer; record['result'] = {**result, 'status': wrong}
                    self.manager._save(con, body['request_id'], record)
                with patch.object(ProjectController, 'advance_selection', autospec=True) as core:
                    with self.assertRaises(ResearchError) as error: self.manager.advance(body)
                    self.assertEqual(error.exception.code, 'EVIDENCE_CHANGED'); core.assert_not_called()
        with self.manager._connect() as con:
            record['status'] = 'unknown'; record['result'] = {**result, 'status': 'unknown', 'request_id': 'other'}
            self.manager._save(con, body['request_id'], record)
        with patch.object(ProjectController, 'advance_selection', autospec=True) as core:
            with self.assertRaises(ResearchError) as error: self.manager.advance(body)
            self.assertEqual(error.exception.code, 'EVIDENCE_CHANGED'); core.assert_not_called()


if __name__ == '__main__': unittest.main()
