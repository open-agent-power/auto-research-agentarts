"""Synthetic workbench delegated batch integration; no model transport or fits."""
import base64
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import test_local_workbench as fixtures
import test_local_workbench_continuation as continuation
import test_hypothesis_feedback as hypothesis_fixtures
from autoresearch import hypothesis_feedback
from autoresearch.contracts import ResearchError, canonical, fingerprint
from autoresearch.host_model_selection import HostModelSelection
from autoresearch.local_workbench import LocalWorkbench
from autoresearch.project_controller import ProjectController


class LocalDelegatedBatchTests(unittest.TestCase):
    plan = staticmethod(continuation.LocalWorkbenchContinuationTests.plan)
    body = continuation.LocalWorkbenchContinuationTests.body
    answer = continuation.LocalWorkbenchContinuationTests.answer
    seed_grant = continuation.LocalWorkbenchContinuationTests.seed_grant

    def setUp(self):
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.manager = LocalWorkbench(self.root / 'manager')
        self.manager.create(fixtures.LocalWorkbenchTests.create_body(self))
        self.project, _ = self.manager.binding()
        self.journal = self.seed_grant(4)
        self.grant = self.journal.status()['grant']
        self.enterContext(patch('autoresearch.host_model_selection.run_claude_selection', side_effect=AssertionError('no model dispatch')))
        self.enterContext(patch('autoresearch.research_project.ResearchProject.fit', create=True, side_effect=AssertionError('no fits')))

    def new_body(self, request_id='continue-delegated', plan=False):
        methods = [item['method_id'] for item in ProjectController(self.project.root).selection_context()['conditions']]
        return {**self.body(request_id, execution_mode='delegated', maximum=1, methods=methods), 'post_action_plan': plan}

    def import_answer(self, body, host_id, answer):
        raw = canonical(answer).encode()
        command = {'request_id': body['request_id'], 'project_id': body['project_id'],
                   'host_request_id': host_id, 'response_base64': base64.b64encode(raw).decode()}
        return command, self.manager.delegated_response(command)

    def assert_code(self, code, fn, *args):
        with self.assertRaises(ResearchError) as caught:
            fn(*args)
        self.assertEqual(caught.exception.code, code)

    def test_restart_import_exact_bytes_execute_and_explicit_post_plan_adoption(self):
        body = self.new_body(plan=True)
        original_budget = self.project.status()['budget']
        first = self.manager.continue_research(body)
        self.assertEqual((first['status'], first['record_status'], first['batch_ref']['kind']),
                         ('awaiting_external_response', 'incomplete', 'delegated'))
        selection = first['steps'][-1]['request_id']
        host = self.journal.status(request_id=selection)
        self.assertEqual(self.journal.status()['usage']['decision_slots_used'], 2)
        self.manager = LocalWorkbench(self.manager.root)
        self.assertEqual(self.manager.continue_research(body), first)
        choice = {'choice': {'kind': 'execute', 'candidate_id': host['context']['candidates'][0]['id']},
                  'rationale': 'Synthetic fixture selection.', 'evidence_citation_ids': []}
        command, imported = self.import_answer(body, selection, choice)
        self.assertEqual(imported['status'], 'received')
        self.assertEqual(self.manager.delegated_response(command)['status'], 'received')
        self.assert_code('IDEMPOTENCY_CONFLICT', self.manager.delegated_response,
                         {**command, 'response_base64': base64.b64encode(b'{}').decode()})
        pending = self.manager.continue_research(body)
        self.assertEqual((pending['status'], pending['record_status']), ('awaiting_external_response', 'incomplete'))
        plan_id = pending['batch_ref']['plan_request_id']
        self.assertEqual(pending['steps'][-1]['phase'], 'post_action_plan')
        self.assertEqual(self.project.status()['budget']['local_tool_calls_used'], original_budget['local_tool_calls_used'] + 1)
        plan_host = self.journal.status(request_id=plan_id)
        feedback = plan_host['context']['feedback']
        proposal = {'plan': self.plan(), 'reason': 'Inspect the synthetic observation.',
                    'feedback_action_ids': [feedback[0]['action_id']] if feedback else [],
                    'expected_improvement': 'Retain the observed fixture result.'}
        self.import_answer(body, plan_id, proposal)
        self.manager = LocalWorkbench(self.manager.root)
        proposed = self.manager.continue_research(body)
        self.assertEqual((proposed['status'], proposed['steps'][-1]['status']), ('awaiting_adoption', 'proposed'))
        before = len(self.project.status()['plan_revisions'])
        self.assertEqual(self.manager.continue_research(body), proposed)
        self.assertEqual(len(self.project.status()['plan_revisions']), before)
        self.manager.model_plan_adopt({'request_id': plan_id, 'project_id': body['project_id']})
        finished = self.manager.continue_research(body)
        self.assertEqual((finished['status'], finished['record_status']), ('plan_adopted', 'completed'))
        self.assertEqual(self.manager.continue_research(body), finished)
        self.assertEqual(self.journal.status()['grant'], self.grant)
        self.assertEqual(self.journal.status()['usage']['decision_slots_used'], 3)
        self.assertEqual(self.project.status()['budget']['new_fits'], original_budget['new_fits'])
        self.assertEqual(self.project.status()['budget']['new_model_requests'], original_budget['new_model_requests'])

    def test_unknown_identity_and_scope_never_replaced(self):
        body = self.new_body()
        first = self.manager.continue_research(body)
        selection = first['steps'][-1]['request_id']
        command = {'request_id': body['request_id'], 'project_id': body['project_id'], 'host_request_id': 'seed-plan',
                   'response_base64': base64.b64encode(b'{}').decode()}
        self.assert_code('ARTIFACT_NOT_FOUND', self.manager.delegated_response, command)
        self.assert_code('IDEMPOTENCY_CONFLICT', self.manager.continue_research, {**body, 'post_action_plan': True})
        ledger = self.journal._load()
        ledger['requests'][selection]['status'] = 'unknown'
        self.journal._save(ledger)
        result = LocalWorkbench(self.manager.root).continue_research(body)
        self.assertEqual((result['status'], result['record_status'], result['stop']['code']),
                         ('needs_review', 'incomplete', 'HOST_REQUEST_UNKNOWN'))
        self.assertEqual(self.manager.continue_research(body), result)
        self.assertEqual(self.journal.status()['usage']['decision_slots_used'], 2)
        self.assertEqual(self.project.status()['actions'], [])
        self.assert_code('OPERATION_INCOMPLETE', self.manager.continue_research, self.new_body('replacement'))

    def test_plan_first_import_and_code_drift(self):
        body = {**self.new_body(), 'plan_mode': 'suggest'}
        pending = self.manager.continue_research(body)
        plan_id = pending['plan_ref']['request_id']
        host = self.journal.status(request_id=plan_id)
        answer = {'plan': self.plan(), 'reason': 'Synthetic plan from the original context.',
                  'feedback_action_ids': [], 'expected_improvement': 'Keep this fixture bounded.'}
        command = {'request_id': body['request_id'], 'project_id': body['project_id'], 'host_request_id': plan_id,
                   'response_base64': base64.b64encode(canonical(answer).encode()).decode()}
        with patch('autoresearch.local_workbench.batch_code_identity', return_value='changed'):
            self.assert_code('EVIDENCE_CHANGED', self.manager.delegated_response, command)
        self.assertEqual(self.journal.status(request_id=plan_id)['status'], 'prepared')
        self.assertEqual(host['provider'], 'delegated')
        self.assertEqual(self.manager.delegated_response(command)['status'], 'received')
        proposed = LocalWorkbench(self.manager.root).continue_research(body)
        self.assertEqual((proposed['phase'], proposed['plan_ref']['status']), ('awaiting_adoption', 'proposed'))
        self.manager.model_plan_adopt({'request_id': plan_id, 'project_id': body['project_id']})
        actions = self.manager.continue_research(body)
        self.assertEqual((actions['phase'], actions['status']), ('actions', 'awaiting_external_response'))
        self.assertEqual(self.journal.status()['grant'], self.grant)
        self.assertEqual(self.journal.status()['usage']['decision_slots_used'], 3)

    def test_import_rejects_host_context_grant_and_malformed_bytes(self):
        body = self.new_body()
        first = self.manager.continue_research(body)
        host_id = first['steps'][-1]['request_id']
        answer = {'choice': {'kind': 'wait'}, 'rationale': 'Synthetic fixture wait.', 'evidence_citation_ids': []}
        command = {'request_id': body['request_id'], 'project_id': body['project_id'], 'host_request_id': host_id,
                   'response_base64': base64.b64encode(canonical(answer).encode()).decode()}
        self.assert_code('INVALID_REQUEST', self.manager.delegated_response, {**command, 'response_base64': '%%%'})
        original = self.journal._load()
        for field in ('context', 'prompt'):
            altered = self.journal._load()
            altered['requests'][host_id][field]['unexpected'] = True
            self.journal._save(altered)
            self.assert_code('EVIDENCE_CHANGED', self.manager.delegated_response, command)
            self.journal._save(original)
        altered = self.journal._load()
        altered['grant']['reason'] = 'changed fixture grant'
        self.journal._save(altered)
        self.assert_code('EVIDENCE_CHANGED', self.manager.delegated_response, command)
        self.journal._save(original)
        with patch('autoresearch.local_workbench.batch_code_identity', return_value='changed'):
            self.assert_code('EVIDENCE_CHANGED', self.manager.delegated_response, command)
            stopped = self.manager.continue_research(body)
            self.assertEqual((stopped['record_status'], stopped['stop']['code']), ('incomplete', 'CODE_CHANGED'))
        self.assertEqual(self.manager.delegated_response(command)['status'], 'received')
        result = self.manager.continue_research(body)
        self.assertEqual((result['status'], result['record_status']), ('waiting', 'completed'))
        self.assertEqual(self.manager.continue_research(body), result)
        self.assertEqual(self.journal.status()['usage']['decision_slots_used'], 2)

    def test_missing_original_response_never_dispatches_replacement(self):
        body = self.new_body()
        first = self.manager.continue_research(body)
        host_id = first['steps'][-1]['request_id']
        answer = {'choice': {'kind': 'wait'}, 'rationale': 'Synthetic fixture wait.', 'evidence_citation_ids': []}
        self.import_answer(body, host_id, answer)
        saved = self.journal.status(request_id=host_id)
        (self.journal.directory / saved['response_file']).unlink()
        stopped = LocalWorkbench(self.manager.root).continue_research(body)
        self.assertNotEqual(stopped['status'], 'waiting')
        self.assertEqual(self.journal.status()['usage']['decision_slots_used'], 2)
        self.assertEqual(self.project.status()['actions'], [])

    def test_no_existing_grant_does_not_create_one(self):
        self.manager.create(fixtures.LocalWorkbenchTests.create_body(self, 'without-host-grant'))
        self.project, _ = self.manager.binding()
        self.project.save_plan(request_id='operator-plan', expected_state_version=0, plan=self.plan(), reason='Synthetic plan.')
        body = self.new_body('no-grant')
        stopped = self.manager.continue_research(body)
        self.assertEqual(stopped['stop']['code'], 'HOST_GRANT_REQUIRED')
        self.assertIsNone(HostModelSelection(self.project.root).status()['grant'])

    def test_preview_is_readonly_and_binds_registered_future_retrieval(self):
        helper = hypothesis_fixtures.HypothesisFeedbackTests()
        self.addCleanup(helper.doCleanups)
        source_project, _ = helper.fixture()
        source_journal = HostModelSelection(source_project.root)
        seed_id = 'fixture-grant'
        source_journal.prepare(request_id=seed_id, provider='delegated', expected_state_version=source_project.status()['state_version'],
                               decision_limit=3, cli_budget_usd=.1, reason='Original synthetic Host grant.')
        raw = canonical({'choice': {'kind': 'wait'}, 'rationale': 'Reserve existing synthetic grant.', 'evidence_citation_ids': []}).encode()
        seed = self.root / 'seed.json'
        seed.write_bytes(raw)
        source_journal.import_response(request_id=seed_id, response_file=seed)
        source_journal.consume(request_id=seed_id)
        imported = self.manager.import_project(request_id='import-retrieval', workspace=source_project.root)
        project_id = imported['project_id']
        self.manager.select({'request_id': 'select-retrieval', 'project_id': project_id})
        self.project, _ = self.manager.binding()
        self.journal = HostModelSelection(self.project.root)
        state = self.project.status()
        context = ProjectController(self.project.root).selection_context()
        body = {'request_id': 'future-continuation', 'project_id': project_id,
                'expected_state_version': state['state_version'] + 1, 'plan_mode': 'reuse', 'execution_mode': 'delegated',
                'max_actions': 1, 'allowed_methods': [item['method_id'] for item in context['conditions']],
                'source_receipt_sha256s': [], 'reason': 'Synthetic preregistered continuation.', 'post_action_plan': False}
        def tree():
            return {str(p.relative_to(self.manager.root)): p.read_bytes() for p in self.manager.root.rglob('*') if p.is_file()}
        before = tree()
        preview = self.manager.preview_continuation(body)
        self.assertEqual(tree(), before)
        self.assertEqual((preview['body_sha256'], preview['status'], preview['authorization'], preview['preparation_state'], preview['execution_eligibility']),
                         (fingerprint(body), 'identifiers_computed', 'not_authorized', 'unknown_not_checked', 'not_checked'))
        uncertain = self.manager.preview_continuation({**body, 'plan_mode': 'suggest'})
        self.assertEqual((uncertain['status'], uncertain['batch_request_id'], uncertain['steps']), ('stage_unknown', None, []))
        self.assertEqual(tree(), before)
        candidate = context['candidates'][0]
        registration = {'request_id': 'synthetic-hypothesis', 'project_id': project_id,
                        'expected_state_version': state['state_version'],
                        'hypothesis': {'candidate_id': candidate['id'], 'controller_request_id': preview['steps'][0]['controller_request_id'],
                                       'metric': 'recall@20', 'operator': 'gt', 'threshold': 0}}
        self.manager.register_hypothesis(registration)
        self.assertEqual(self.project.status()['state_version'], body['expected_state_version'])
        pending = self.manager.continue_research(body)
        self.assertEqual(pending['batch_ref']['request_id'], preview['batch_request_id'])
        self.assertEqual(self.manager.preview_continuation(body), preview)
        host_id = pending['steps'][-1]['request_id']
        self.assertEqual(host_id, preview['steps'][0]['host_request_id'])
        host = self.journal.status(request_id=host_id)
        choice = {'choice': {'kind': 'execute', 'candidate_id': host['context']['candidates'][0]['id']},
                  'rationale': 'Execute the registered synthetic retrieval pair.', 'evidence_citation_ids': []}
        self.import_answer(body, host_id, choice)
        finished = LocalWorkbench(self.manager.root).continue_research(body)
        self.assertEqual((finished['status'], finished['record_status']), ('limit_reached', 'completed'))
        item = hypothesis_feedback.feedback_context(self.project, self.project.status())['items'][0]
        self.assertEqual((item['controller_request_id'], item['outcome']), (host_id, 'condition_not_met'))
        self.assertEqual(self.journal.status()['usage']['decision_slots_used'], 2)

    def test_interrupted_projection_recovers_original_batch_and_inactive_project_is_blocked(self):
        body = self.new_body()
        with patch.object(self.manager, '_complete_continuation_batch', side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                self.manager.continue_research(body)
        saved = self.manager.continuation_record(body['request_id'])
        self.assertEqual(saved['batch_ref']['status'], 'prepared')
        resumed = LocalWorkbench(self.manager.root).continue_research(body)
        selection = resumed['steps'][-1]['request_id']
        self.assertEqual(self.journal.status()['usage']['decision_slots_used'], 2)
        self.manager.create(fixtures.LocalWorkbenchTests.create_body(self, 'second-fixture'))
        command = {'request_id': body['request_id'], 'project_id': body['project_id'], 'host_request_id': selection,
                   'response_base64': base64.b64encode(b'{}').decode()}
        self.assert_code('STALE_STATE', self.manager.delegated_response, command)
        self.assert_code('STALE_STATE', self.manager.continue_research, body)
        self.assertEqual(self.journal.status()['usage']['decision_slots_used'], 2)


if __name__ == '__main__':
    unittest.main()
