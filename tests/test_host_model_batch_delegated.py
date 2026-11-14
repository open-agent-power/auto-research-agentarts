"""Delegated batch recovery with temporary fixtures; no model or research adapter runs."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import test_local_workbench as fixtures
from autoresearch.contracts import ResearchError, canonical
from autoresearch.host_model_batch import HostModelBatch
from autoresearch.host_model_report import capture_host_models
from autoresearch.local_workbench import LocalWorkbench


class DelegatedBatchTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(self.enterContext(tempfile.TemporaryDirectory()))
        manager = LocalWorkbench(self.tmp / 'manager')
        manager.create(fixtures.LocalWorkbenchTests.create_body(self))
        self.project, _ = manager.binding()
        self.batch = HostModelBatch(self.project.root)
        self.args = dict(request_id='synthetic', expected_state_version=0, max_decisions=1,
                         decision_limit=2, cli_budget_usd=.1, reason='synthetic test', post_action_plan=True)
        self.enterContext(patch('autoresearch.host_model_selection.run_claude_selection', side_effect=AssertionError('model dispatch')))
        self.enterContext(patch('autoresearch.research_project.ResearchProject.step', side_effect=AssertionError('research action')))

    def test_prepared_is_stable_then_wait_stops_without_extra_slot(self):
        first = self.batch.advance_delegated(**self.args)
        self.assertEqual((first['status'], first['record_status']), ('awaiting_external_response', 'incomplete'))
        self.assertEqual(first['steps'][0]['host_status'], 'prepared')
        second = self.batch.advance_delegated(**self.args)
        self.assertEqual(second['steps'], first['steps'])
        self.assertEqual(self.batch.journal.status()['usage']['decision_slots_used'], 1)
        response = self.tmp / 'response.json'
        response.write_bytes(canonical({'choice': {'kind': 'wait'}, 'rationale': 'Wait for suitable evidence.', 'evidence_citation_ids': []}).encode())
        request_id = first['steps'][0]['host_request_id']
        self.batch.journal.import_response(request_id=request_id, response_file=response)
        stopped = self.batch.advance_delegated(**self.args)
        self.assertEqual(stopped['status'], 'waiting')
        self.assertIsNone(stopped['plan_step'])
        self.assertEqual(self.batch.journal.status()['usage']['decision_slots_used'], 1)
        self.assertEqual(self.batch.advance_delegated(**self.args), stopped)
        self.assertEqual(capture_host_models(self.project.root)['batches'], [stopped])

    def test_step_saved_before_prepare_resumes_same_id(self):
        original = self.batch.journal.prepare
        with patch.object(self.batch.journal, 'prepare', side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                self.batch.advance_delegated(**self.args)
        saved = self.batch.status(request_id='synthetic')
        self.assertEqual(saved['steps'][0]['host_status'], 'preparing')
        self.assertEqual(self.batch.journal.status()['usage']['decision_slots_used'], 0)
        with patch.object(self.batch.journal, 'prepare', wraps=original) as prepare:
            resumed = self.batch.advance_delegated(**self.args)
        self.assertEqual(resumed['status'], 'awaiting_external_response')
        self.assertEqual(prepare.call_args.kwargs['request_id'], saved['steps'][0]['host_request_id'])
        self.assertEqual(self.batch.journal.status()['usage']['decision_slots_used'], 1)

    def test_changed_body_and_code_never_replace_request(self):
        original = self.batch.advance_delegated(**self.args)
        with self.assertRaises(ResearchError) as caught:
            self.batch.advance_delegated(**{**self.args, 'decision_limit': 3})
        self.assertEqual(caught.exception.code, 'IDEMPOTENCY_CONFLICT')
        with patch('autoresearch.host_model_batch._delegated_code_identity', return_value={'changed': 'yes'}):
            with self.assertRaises(ResearchError) as caught:
                self.batch.advance_delegated(**self.args)
        self.assertEqual(caught.exception.code, 'CODE_CHANGED')
        self.assertEqual(self.batch.status(request_id='synthetic'), original)
        self.assertEqual(self.batch.journal.status()['usage']['decision_slots_used'], 1)

    def test_unknown_never_dispatches_or_replaces(self):
        first = self.batch.advance_delegated(**self.args)
        request_id = first['steps'][0]['host_request_id']
        state = self.batch.journal._load()
        state['requests'][request_id]['status'] = 'unknown'
        self.batch.journal._save(state)
        resumed = self.batch.advance_delegated(**self.args)
        self.assertEqual((resumed['status'], resumed['record_status']), ('needs_review', 'incomplete'))
        self.assertEqual(self.batch.journal.status()['usage']['decision_slots_used'], 1)
        self.assertEqual(self.batch.advance_delegated(**self.args)['status'], 'needs_review')

    def test_response_bytes_survive_interrupted_journal_save(self):
        first = self.batch.advance_delegated(**self.args)
        request_id = first['steps'][0]['host_request_id']
        response = self.tmp / 'response.json'
        response.write_bytes(canonical({'choice': {'kind': 'wait'}, 'rationale': 'No suitable next action.', 'evidence_citation_ids': []}).encode())
        original_save = self.batch.journal._save
        def interrupt(state):
            if state['requests'][request_id]['status'] == 'received':
                raise KeyboardInterrupt('synthetic interruption')
            return original_save(state)
        with patch.object(self.batch.journal, '_save', side_effect=interrupt):
            with self.assertRaises(KeyboardInterrupt):
                self.batch.journal.import_response(request_id=request_id, response_file=response)
        self.assertEqual(self.batch.journal.status(request_id=request_id)['status'], 'prepared')
        self.assertEqual(self.batch.advance_delegated(**self.args)['status'], 'awaiting_external_response')
        self.assertEqual(self.batch.journal.import_response(request_id=request_id, response_file=response)['status'], 'received')
        self.assertEqual(self.batch.advance_delegated(**self.args)['status'], 'waiting')
        self.assertEqual(self.batch.journal.status()['usage']['decision_slots_used'], 1)


if __name__ == '__main__':
    unittest.main()

class SyntheticCompletionTests(unittest.TestCase):
    """Pure callback receipts exercise control flow; no real action is dispatched."""
    def setUp(self):
        import copy
        from contextlib import nullcontext
        from autoresearch.contracts import fingerprint
        from autoresearch import host_model_batch as module
        self.copy, self.fingerprint = copy, fingerprint
        self.tmp = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.state = {'id': 'project', 'run_id': 'run', 'state_version': 0, 'snapshot_ref': 's0',
                      'source_snapshot_sha256': 'source', 'evidence_sources': [], 'actions': [],
                      'evidence_actions': [], 'controller_requests': [], 'plan_revisions': []}
        outer = self
        class Project:
            root = outer.tmp
            def status(self): return copy.deepcopy(outer.state)
        class Controller:
            def __init__(self, root): pass
            def selection_context(self):
                return {'state_version': outer.state['state_version'], 'blockers': [],
                        'conditions': [{'method_id': 'fixture'}],
                        'candidates': [] if outer.state['state_version'] else [{'method_id': 'fixture', 'parameters': {}}]}
        class Journal:
            def __init__(self): self.requests = {}; self.calls = 0
            def _writer(self): return nullcontext()
            def _load(self): return {'requests': self.requests}
            def status(self):
                return {'grant': None if not self.requests else {'decision_limit': 2, 'cli_budget_usd': .1, 'reason': 'fixture'},
                        'requests': list(self.requests.values()), 'usage': {'decision_slots_used': len(self.requests),
                        'cli_cost_unknown': False, 'known_cli_reported_cost_usd': 0}}
            def prepare(self, **kw):
                rid = kw['request_id']
                if rid not in self.requests:
                    selection = Controller(None).selection_context()
                    context = selection if kw['purpose'] == 'selection' else {'selection_context': selection}
                    self.requests[rid] = {'status': 'prepared', 'context': context, 'prompt': {'context': context},
                                          'request_id': rid, 'provider': 'delegated', 'purpose': kw['purpose'],
                                          'controller_request_id': rid}
                return copy.deepcopy(self.requests[rid])
            def consume(self, *, request_id):
                self.calls += 1
                model = self.requests[request_id]
                if request_id.endswith('-plan'):
                    model['status'] = 'proposed'
                else:
                    child_id = request_id + '-child'
                    child = {'id': 'action', 'request_id': child_id, 'status': 'completed', 'project_id': 'project', 'run_id': 'run',
                             'command': 'synthetic', 'result_sha256': 'fixture-hash'}
                    projected = {key: child[key] for key in ('id', 'request_id', 'command', 'status', 'artifact', 'result_sha256', 'failure') if key in child}
                    outer.state.update(state_version=1, snapshot_ref='s1', actions=[child], controller_requests=[
                        {'request_id': request_id, 'status': 'completed', 'child_request_id': child_id, 'state_version_after': 1,
                         'result': {'child': projected}}])
                    model.update(status='applied', outcome={'status': 'completed', 'request_id': request_id,
                        'project_id': 'project', 'child_request_id': child_id, 'result': {'child': projected}})
                return copy.deepcopy(model)
            def request(self, **kwargs): raise AssertionError('no dispatch')
        batch = HostModelBatch.__new__(HostModelBatch)
        batch.project, batch.journal, batch.directory = Project(), Journal(), self.tmp / 'batches'
        self.batch = batch
        self.enterContext(patch.object(module, 'ProjectController', Controller))
        self.enterContext(patch.object(module.ResearchProject, '_writer', lambda _self: nullcontext()))
        self.enterContext(patch('autoresearch.host_selection_protocol.build_prompt', side_effect=lambda c: {'context': c}))
        self.enterContext(patch('autoresearch.research_plan_proposal.build_context', side_effect=lambda p: {'selection_context': Controller(None).selection_context()}))
        self.enterContext(patch('autoresearch.research_plan_proposal.build_prompt', side_effect=lambda c: {'context': c}))
        self.args = dict(request_id='batch', expected_state_version=0, max_decisions=2, decision_limit=2,
                         cli_budget_usd=.1, reason='fixture', post_action_plan=True)

    def test_no_candidate_after_completed_action_prepares_plan_once(self):
        first = self.batch.advance_delegated(**self.args)
        self.assertEqual(first['status'], 'awaiting_external_response')
        selection_id = first['steps'][0]['host_request_id']
        self.batch.journal.requests[selection_id]['status'] = 'received'
        plan = self.batch.advance_delegated(**self.args)
        self.assertEqual((plan['status'], len(plan['steps'])), ('awaiting_external_response', 1))
        plan_id = plan['plan_step']['host_request_id']
        self.assertEqual(plan['plan_step']['purpose'], 'plan')
        self.assertEqual(plan['plan_step']['expected_state_version'], 1)
        self.assertEqual(len(self.batch.journal.requests), 2)
        self.batch.journal.requests[plan_id]['status'] = 'received'
        proposed = self.batch.advance_delegated(**self.args)
        self.assertEqual((proposed['status'], proposed['record_status']), ('awaiting_adoption', 'incomplete'))
        self.assertEqual(self.state['plan_revisions'], [])
        self.assertEqual(self.batch.advance_delegated(**self.args)['status'], 'awaiting_adoption')
        self.assertEqual(self.batch.journal.calls, 2)
        self.assertEqual(len(self.batch.journal.requests), 2)

    def test_optional_plan_never_exceeds_original_global_limit(self):
        args = {**self.args, 'decision_limit': 1}
        first = self.batch.advance_delegated(**args)
        request_id = first['steps'][0]['host_request_id']
        self.batch.journal.requests[request_id]['status'] = 'received'
        stopped = self.batch.advance_delegated(**args)
        self.assertEqual(stopped['stop']['code'], 'HOST_DECISION_LIMIT')
        self.assertIsNone(stopped['plan_step'])
        self.assertEqual(len(self.batch.journal.requests), 1)

    def test_missing_applied_outcome_is_incomplete_and_never_reissued(self):
        first = self.batch.advance_delegated(**self.args)
        request_id = first['steps'][0]['host_request_id']
        self.batch.journal.requests[request_id]['status'] = 'applied'
        stopped = self.batch.advance_delegated(**self.args)
        self.assertEqual((stopped['status'], stopped['record_status']), ('needs_review', 'incomplete'))
        self.assertEqual(stopped['stop']['code'], 'CONTROLLER_UNKNOWN')
        self.assertEqual(self.batch.advance_delegated(**self.args)['status'], 'needs_review')
        self.assertEqual(len(self.batch.journal.requests), 1)

    def test_applied_plan_without_revision_stays_incomplete(self):
        first = self.batch.advance_delegated(**self.args)
        self.batch.journal.requests[first['steps'][0]['host_request_id']]['status'] = 'received'
        second = self.batch.advance_delegated(**self.args)
        plan_id = second['plan_step']['host_request_id']
        self.batch.journal.requests[plan_id]['status'] = 'applied'
        stopped = self.batch.advance_delegated(**self.args)
        self.assertEqual((stopped['status'], stopped['record_status']), ('needs_review', 'incomplete'))
        self.assertEqual(stopped['stop']['code'], 'PLAN_RESULT_UNKNOWN')
        self.assertEqual(len(self.batch.journal.requests), 2)

    def test_applied_plan_requires_original_completed_outcome_binding(self):
        first = self.batch.advance_delegated(**self.args)
        self.batch.journal.requests[first['steps'][0]['host_request_id']]['status'] = 'received'
        second = self.batch.advance_delegated(**self.args)
        plan_id = second['plan_step']['host_request_id']
        plan = {'request_id': plan_id, 'based_on_state_version': 1}
        self.state.update(state_version=2, snapshot_ref='s2', plan_revisions=[plan])
        model = self.batch.journal.requests[plan_id]
        model.update(status='applied', outcome={'status': 'unknown', 'kind': 'plan_revision',
                                                'state_version': 2, 'research_plan': plan})
        stopped = self.batch.advance_delegated(**self.args)
        self.assertEqual((stopped['status'], stopped['record_status']), ('needs_review', 'incomplete'))
        self.assertEqual(stopped['stop']['code'], 'PLAN_RESULT_UNKNOWN')

    def test_explicitly_adopted_matching_plan_is_terminal(self):
        first = self.batch.advance_delegated(**self.args)
        self.batch.journal.requests[first['steps'][0]['host_request_id']]['status'] = 'received'
        second = self.batch.advance_delegated(**self.args)
        plan_id = second['plan_step']['host_request_id']
        plan = {'request_id': plan_id, 'based_on_state_version': 1}
        self.state.update(state_version=2, snapshot_ref='s2', plan_revisions=[plan])
        self.batch.journal.requests[plan_id].update(status='applied', outcome={'status': 'completed',
            'kind': 'plan_revision', 'state_version': 2, 'research_plan': plan})
        finished = self.batch.advance_delegated(**self.args)
        self.assertEqual((finished['status'], finished['record_status']), ('plan_adopted', 'completed'))
        self.assertEqual(self.batch.advance_delegated(**self.args), finished)
        self.assertEqual(len(self.batch.journal.requests), 2)

    def test_wrong_controller_identity_never_consumes_received_response(self):
        first = self.batch.advance_delegated(**self.args)
        request_id = first['steps'][0]['host_request_id']
        self.batch.journal.requests[request_id].update(status='received', controller_request_id='other')
        stopped = self.batch.advance_delegated(**self.args)
        self.assertEqual(stopped['stop']['code'], 'EVIDENCE_CHANGED')
        self.assertEqual(self.batch.journal.calls, 0)
        self.assertEqual(self.state['actions'], [])
        self.assertEqual(len(self.batch.journal.requests), 1)

    def test_unrecognized_host_and_malformed_controller_result_stop(self):
        first = self.batch.advance_delegated(**self.args)
        request_id = first['steps'][0]['host_request_id']
        model = self.batch.journal.requests[request_id]
        model['status'] = 'unrecognized'
        stopped = self.batch.advance_delegated(**self.args)
        self.assertEqual((stopped['status'], stopped['record_status']), ('needs_review', 'incomplete'))
        model.update(status='applied', outcome={'status': 'completed', 'result': ['invalid']})
        stopped = self.batch.advance_delegated(**self.args)
        self.assertEqual((stopped['status'], stopped['record_status']), ('needs_review', 'incomplete'))
        self.assertEqual(stopped['stop']['code'], 'CONTROLLER_RESULT_UNKNOWN')
        self.assertEqual(self.batch.journal.calls, 0)

    def test_changed_host_child_result_stops_before_next_request(self):
        first = self.batch.advance_delegated(**self.args)
        request_id = first['steps'][0]['host_request_id']
        self.batch.journal.requests[request_id]['status'] = 'received'
        original = self.batch.journal.consume
        def changed(**kwargs):
            model = original(**kwargs)
            model['outcome']['result']['child']['result_sha256'] = 'different'
            return model
        with patch.object(self.batch.journal, 'consume', side_effect=changed):
            stopped = self.batch.advance_delegated(**self.args)
        self.assertEqual((stopped['status'], stopped['record_status']), ('needs_review', 'incomplete'))
        self.assertEqual(stopped['stop']['code'], 'CONTROLLER_RESULT_CHANGED')
        self.assertEqual(len(self.batch.journal.requests), 1)

    def test_missing_projected_child_field_stops_even_if_parent_matches(self):
        first = self.batch.advance_delegated(**self.args)
        request_id = first['steps'][0]['host_request_id']
        self.batch.journal.requests[request_id]['status'] = 'received'
        original = self.batch.journal.consume
        def changed(**kwargs):
            model = original(**kwargs)
            del model['outcome']['result']['child']['result_sha256']
            del self.state['controller_requests'][0]['result']['child']['result_sha256']
            return model
        with patch.object(self.batch.journal, 'consume', side_effect=changed):
            stopped = self.batch.advance_delegated(**self.args)
        self.assertEqual((stopped['status'], stopped['record_status']), ('needs_review', 'incomplete'))
        self.assertEqual(stopped['stop']['code'], 'CONTROLLER_RESULT_CHANGED')
        self.assertEqual(len(self.batch.journal.requests), 1)
