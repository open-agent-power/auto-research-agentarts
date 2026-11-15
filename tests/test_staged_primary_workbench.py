"""Synthetic staged primary ownership and conservative recovery; no real study."""
import copy
import json
import os
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from autoresearch.contracts import ResearchError, canonical, fingerprint
from autoresearch.project_controller import ProjectController
from autoresearch.research_project import ResearchProject
from autoresearch import hypothesis_feedback
from test_staged_hypothesis_workbench import StagedHypothesisWorkbenchTests
from test_local_workbench_http import LocalWorkbenchHTTPTests


class StagedPrimaryWorkbenchTests(unittest.TestCase):
    def fixture(self):
        helper = StagedHypothesisWorkbenchTests()
        self.addCleanup(helper.doCleanups)
        manager, project, registration_body = helper.fixture()
        registration = manager.register_staged_hypothesis(registration_body)['registration']
        body = {'request_id': registration['controller_request_id'], 'project_id': project.status()['id'],
                'expected_state_version': project.status()['state_version'], 'registration_request_id': registration['request_id'],
                'registration_sha256': registration['registration_sha256'], 'reason': 'Synthetic explicit primary authorization.'}
        return manager, project, body

    def test_completed_resume_and_bytes_tamper(self):
        manager, project, body = self.fixture()
        answer = manager.advance_staged_primary(body)
        self.assertEqual(answer['status'], 'completed')
        state = project.status()
        self.assertEqual(len(state['actions']), 1)
        feedback = hypothesis_feedback.feedback_context(project, state)['items'][0]
        self.assertNotEqual(feedback['outcome'], 'unknown')
        with patch.object(ProjectController, '_dispatch', side_effect=AssertionError('must not redispatch')):
            self.assertTrue(manager.resume_staged_primary({'request_id':body['request_id'], 'project_id':body['project_id']})['replayed'])
            self.assertTrue(manager.advance_staged_primary(body)['replayed'])
        self.assertEqual(project.status(), state)
        path = project.root / state['actions'][0]['artifact']
        original = path.read_bytes()
        path.write_text(json.dumps(json.loads(original), indent=2), encoding='utf-8')
        with self.assertRaises(ResearchError) as error:
            manager.resume_staged_primary({'request_id':body['request_id'], 'project_id':body['project_id']})
        self.assertEqual(error.exception.code, 'EVIDENCE_CHANGED')

    def test_missing_core_cannot_dispatch_on_replay(self):
        manager, project, body = self.fixture()
        before = project.status()
        with patch.object(ProjectController, '_advance_staged_primary', side_effect=RuntimeError('synthetic interruption')):
            with self.assertRaises(RuntimeError): manager.advance_staged_primary(body)
        self.assertEqual(project.status(), before)
        self.assertTrue(any(item['request_id'] == body['request_id'] for item in manager.describe()['pending_requests']))
        with patch.object(ProjectController, '_advance_staged_primary', side_effect=AssertionError('must not dispatch')):
            with self.assertRaises(ResearchError): manager.advance_staged_primary(body)
            with self.assertRaises(ResearchError): manager.resume_staged_primary({'request_id':body['request_id'], 'project_id':body['project_id']})
        changed = copy.deepcopy(body); changed['reason'] += ' changed'
        with self.assertRaises(ResearchError) as error: manager.advance_staged_primary(changed)
        self.assertEqual(error.exception.code, 'IDEMPOTENCY_CONFLICT')
        self.assertEqual(project.status(), before)

    def test_parent_only_rejects_direct_entry(self):
        manager, project, body = self.fixture()
        with patch.object(ProjectController, '_dispatch', side_effect=RuntimeError('synthetic interruption')):
            with self.assertRaises(RuntimeError): manager.advance_staged_primary(body)
        before = project.status()
        parent = before['controller_requests'][-1]
        self.assertEqual(parent['status'], 'prepared')
        self.assertEqual(before['actions'], [])
        for request_id in (parent['child_request_id'], 'unrelated-primary'):
            with self.assertRaises(ResearchError):
                project.step(request_id=request_id, method_id=parent['decision']['next_action']['method_id'],
                             expected_state_version=before['state_version'])
        with self.assertRaises(ResearchError): manager.resume_staged_primary({'request_id':body['request_id'], 'project_id':body['project_id']})
        with self.assertRaises(ResearchError):
            project.upgrade(request_id='direct-upgrade', expected_code_identity=before['code_identity'],
                            evidence_read_limit=before['budget'].get('evidence_read_limit', 8))
        limit = before['budget']['local_tool_call_limit']
        with self.assertRaises(ResearchError):
            project.extend_local_budget(request_id='direct-budget', expected_limit=limit, new_limit=limit+1,
                                        reason='synthetic', expected_state_version=before['state_version'])
        with self.assertRaises(ResearchError):
            project.save_plan(request_id='direct-plan', expected_state_version=before['state_version'],
                              plan={'question':'Later?', 'basis':'synthetic', 'steps':'wait', 'expected_feedback':'none'}, reason='fixture')
        self.assertEqual(project.status(), before)

    def test_parent_decision_reseal_rejected(self):
        manager, project, body = self.fixture()
        manager.advance_staged_primary(body)
        with project._writer(), project._connect() as con:
            state = project._project(con)
            parent = state['controller_requests'][-1]
            parent['decision']['reason'] = 'tampered'
            parent['decision_sha256'] = fingerprint(parent['decision'])
            project._save(con, state)
        with self.assertRaises(ResearchError):
            manager.resume_staged_primary({'request_id':body['request_id'], 'project_id':body['project_id']})

    def test_child_completed_parent_unfinished_stays_stopped(self):
        manager, project, body = self.fixture()
        with patch.object(ProjectController, '_finish', side_effect=RuntimeError('before parent finish')):
            with self.assertRaises(RuntimeError): manager.advance_staged_primary(body)
        before = project.status()
        self.assertEqual(before['controller_requests'][-1]['status'], 'prepared')
        self.assertEqual(before['actions'][0]['status'], 'completed')
        child = before['actions'][0]['request_id']
        with patch.object(ProjectController, '_dispatch', side_effect=AssertionError('no redispatch')):
            with self.assertRaises(ResearchError): manager.resume_staged_primary({'request_id':body['request_id'], 'project_id':body['project_id']})
            with self.assertRaises(ResearchError): project.resume(request_id=child)
            with self.assertRaises(ResearchError): project.step(request_id=child, expected_state_version=before['state_version'])
        self.assertEqual(project.status(), before)

    def test_terminal_core_receipt_can_be_completed_but_claim_required(self):
        manager, project, body = self.fixture()
        with patch.object(manager, '_inspect_staged_primary', side_effect=RuntimeError('manager receipt interrupted')):
            with self.assertRaises(RuntimeError): manager.advance_staged_primary(body)
        before = project.status()
        with patch.object(ProjectController, '_dispatch', side_effect=AssertionError('no redispatch')):
            answer = manager.resume_staged_primary({'request_id':body['request_id'], 'project_id':body['project_id']})
        self.assertTrue(answer['replayed'])
        self.assertEqual(project.status(), before)
        with project._connect() as con:
            con.execute("DELETE FROM quality_manager_claims WHERE kind='staged_primary_child'")
        with self.assertRaises(ResearchError): manager.resume_staged_primary({'request_id':body['request_id'], 'project_id':body['project_id']})

    def test_drift_at_child_preflight_preserves_parent_and_budget(self):
        manager, project, body = self.fixture()
        original = ProjectController._dispatch
        def drift(controller, *args, **kwargs):
            with patch('autoresearch.local_workbench._check_staged_runtime', side_effect=ResearchError('CODE_CHANGED', 'synthetic drift')):
                return original(controller, *args, **kwargs)
        before = project.status()
        with patch.object(ProjectController, '_dispatch', new=drift):
            with self.assertRaises(ResearchError) as error: manager.advance_staged_primary(body)
        self.assertEqual(error.exception.code, 'CODE_CHANGED')
        after = project.status()
        self.assertEqual(after['actions'], [])
        self.assertEqual(after['budget'], before['budget'])
        self.assertEqual(after['controller_requests'][-1]['status'], 'prepared')

    def test_evidence_entry_and_ordinary_controller_reject_pending(self):
        manager, project, body = self.fixture()
        with patch.object(ProjectController, '_dispatch', side_effect=RuntimeError('parent accepted')):
            with self.assertRaises(RuntimeError): manager.advance_staged_primary(body)
        before = project.status()
        parent = before['controller_requests'][-1]
        with self.assertRaises(ResearchError): project.read_evidence(request_id=parent['child_request_id'], receipt_snapshot_sha256='0'*64)
        with self.assertRaises(ResearchError): project.attach_evidence(request_id=parent['child_request_id'], bundle=b'{}')
        with self.assertRaises(ResearchError):
            ProjectController(project.root).advance_selection(request_id=body['request_id'], proposal=parent['request']['proposal'],
                                                              expected_state_version=body['expected_state_version'])
        self.assertEqual(project.status(), before)

    def test_orphan_replay_both_directions_never_finalizes_parent(self):
        original = ProjectController._dispatch
        for reverse in (False, True):
            with self.subTest(reverse=reverse):
                manager, project, body = self.fixture()
                def competing(controller, parent, **kwargs):
                    child = parent['child_request_id']
                    pair = ('foreign', child) if reverse else (child, 'foreign')
                    with project._connect() as con:
                        con.execute('INSERT INTO replays VALUES(?, ?)', pair)
                    return original(controller, parent, **kwargs)
                with patch.object(ProjectController, '_dispatch', new=competing):
                    with self.assertRaises(ResearchError): manager.advance_staged_primary(body)
                after = project.status()
                self.assertEqual(after['controller_requests'][-1]['status'], 'prepared')
                self.assertEqual(after['actions'], [])
                with self.assertRaises(ResearchError): manager.resume_staged_primary({'request_id':body['request_id'], 'project_id':body['project_id']})

    def test_code_drift_after_child_acceptance_never_calls_adapter(self):
        manager, project, body = self.fixture()
        original = ProjectController._dispatch
        def drift(controller, *args, **kwargs):
            with patch('autoresearch.local_workbench._check_staged_runtime', side_effect=[None, ResearchError('CODE_CHANGED', 'synthetic drift')]):
                return original(controller, *args, **kwargs)
        with patch.object(ProjectController, '_dispatch', new=drift), \
             patch('autoresearch.staged_relevance_adapter.execute', side_effect=AssertionError('adapter must not run')):
            with self.assertRaises(ResearchError) as error: manager.advance_staged_primary(body)
        self.assertEqual(error.exception.code, 'CODE_CHANGED')
        state = project.status()
        self.assertEqual(state['controller_requests'][-1]['status'], 'prepared')
        self.assertEqual(state['actions'][0]['status'], 'running')
        with self.assertRaises(ResearchError): manager.resume_staged_primary({'request_id':body['request_id'], 'project_id':body['project_id']})

    def test_terminal_replay_after_new_plan_preserves_original(self):
        manager, project, body = self.fixture()
        original = manager.advance_staged_primary(body)
        state = project.status()
        project.save_plan(request_id='later-plan', expected_state_version=state['state_version'],
                          plan={'question':'Later?', 'basis':'synthetic', 'steps':'wait', 'expected_feedback':'none'}, reason='fixture')
        before = project.status()
        result = manager.resume_staged_primary({'request_id':body['request_id'], 'project_id':body['project_id']})
        self.assertEqual(result['controller'], original['controller'])
        self.assertEqual(project.status(), before)

    def test_direct_controller_winner_is_not_adopted(self):
        manager, project, body = self.fixture()
        strict = ProjectController._advance_staged_primary
        def competitor(controller, **kwargs):
            with patch.object(ProjectController, '_dispatch', side_effect=RuntimeError('competitor parent only')):
                with self.assertRaises(RuntimeError):
                    controller.advance_selection(request_id=kwargs['request_id'], proposal=kwargs['proposal'],
                                                 expected_state_version=kwargs['expected_state_version'])
            return strict(controller, **kwargs)
        with patch.object(ProjectController, '_advance_staged_primary', new=competitor):
            with self.assertRaises(ResearchError): manager.advance_staged_primary(body)
        state = project.status()
        self.assertEqual(state['actions'], [])
        self.assertNotIn('staged_primary', state['controller_requests'][-1])
        with self.assertRaises(ResearchError): manager.resume_staged_primary({'request_id':body['request_id'], 'project_id':body['project_id']})

    def test_missing_original_intent_and_claim_never_dispatch(self):
        manager, project, body = self.fixture()
        self.assertEqual(project.status()['actions'], [])
        with self.assertRaises(ResearchError) as error:
            manager.resume_staged_primary({'request_id':body['request_id'], 'project_id':body['project_id']})
        self.assertEqual(error.exception.code, 'OPERATION_INCOMPLETE')
        with project._connect() as con:
            con.execute("DELETE FROM quality_manager_claims WHERE kind='hypothesis_registration'")
        with patch.object(ProjectController, '_advance_staged_primary', side_effect=AssertionError('no dispatch')):
            with self.assertRaises(ResearchError): manager.advance_staged_primary(body)
        self.assertEqual(project.status()['actions'], [])

    def test_original_id_replay_in_new_process_without_dispatch(self):
        manager, project, body = self.fixture()
        original = manager.advance_staged_primary(body)
        before = project.status()
        program = ("import json,sys; from autoresearch.local_workbench import LocalWorkbench; "
                   "m=LocalWorkbench(sys.argv[1]); print(json.dumps(m.resume_staged_primary(json.loads(sys.argv[2]))))")
        with tempfile.TemporaryDirectory() as cache:
            env = dict(os.environ, PYTHONPYCACHEPREFIX=cache, PYTHONDONTWRITEBYTECODE='1')
            result = subprocess.run([sys.executable, '-B', '-c', program, str(manager.root),
                                     json.dumps({'request_id':body['request_id'], 'project_id':body['project_id']})],
                                    capture_output=True, text=True, env=env, check=True)
        replay = json.loads(result.stdout)
        self.assertTrue(replay['replayed'])
        self.assertEqual(replay['controller'], original['controller'])
        self.assertEqual(project.status(), before)

    def test_explicit_http_primary_and_resume(self):
        manager, project, body = self.fixture()
        helper = LocalWorkbenchHTTPTests()
        self.addCleanup(helper.doCleanups)
        server = helper.serve(local_workspace=manager, allow_local_actions=True)
        headers = helper.session(server)
        status, _ = helper.request(server, '/api/local-workbench/staged-primary', 'POST', body,
                                   {**headers, 'X-AutoResearch-CSRF':'wrong'})
        self.assertEqual(status, 403)
        self.assertEqual(project.status()['actions'], [])
        status, response = helper.request(server, '/api/local-workbench/staged-primary', 'POST', body, headers)
        self.assertEqual((status, response['status']), (200, 'completed'))
        before = project.status()
        status, replay = helper.request(server, '/api/local-workbench/staged-primary-resume', 'POST',
                                        {'request_id':body['request_id'], 'project_id':body['project_id']}, headers)
        self.assertEqual(status, 200)
        self.assertTrue(replay['replayed'])
        self.assertEqual(project.status(), before)


if __name__ == '__main__':
    unittest.main()
