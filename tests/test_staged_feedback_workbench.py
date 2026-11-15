"""Synthetic S111/S112/S115 feedback choices; no real research or model."""
import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from autoresearch.contracts import ResearchError
from autoresearch.project_controller import ProjectController
from autoresearch.research_project import ResearchProject
from autoresearch.local_workbench import LocalWorkbench
from autoresearch import staged_relevance_adapter as staged, hypothesis_feedback, staged_feedback_reader, staged_project_experience, relevance_retrieval_adapter, retrieval_lexical
from test_staged_hypothesis_workbench import StagedHypothesisWorkbenchTests


class StagedFeedbackWorkbenchTests(unittest.TestCase):
    def fixture(self, branch='wait', outcome='not_met', limit_one=False):
        helper = StagedHypothesisWorkbenchTests()
        self.addCleanup(helper.doCleanups)
        manager, project, original = helper.fixture()
        if limit_one:
            root=Path(self.enterContext(tempfile.TemporaryDirectory()));(root/'input').mkdir()
            source=root/'input'/'source.json';source.write_bytes((project.root/'source.json').read_bytes())
            new_project=ResearchProject(root/'new-project');new_project.create(source=source,goal='Synthetic one-tool limit',
                budget_ref='fixture',max_tool_calls=1,method_id=staged.TOOL_ID)
            new_project.save_plan(request_id='plan',expected_state_version=new_project.status()['state_version'],
                plan={'question':'Fixture?','basis':'synthetic','steps':'validation','expected_feedback':'saved result'},reason='fixture')
            manager=LocalWorkbench(root/'manager');project_id=manager.import_project(request_id='import',workspace=str(new_project.root))['project_id']
            manager.select({'request_id':'select','project_id':project_id});project,_=manager.binding()
            original['project_id']=project_id;original['expected_state_version']=project.status()['state_version']
        choice = {'kind':'wait'} if branch == 'wait' else {'kind':'method', 'method_id':staged.AUDIT_TOOL_ID}
        original['hypothesis']['branches'] = {'condition_met':choice, 'condition_not_met':choice}
        if outcome == 'met': original['hypothesis']['conditions'][0]['operator'] = 'gte'
        registration = manager.register_staged_hypothesis(original)['registration']
        body = {'request_id':registration['controller_request_id'], 'project_id':project.status()['id'],
                'expected_state_version':project.status()['state_version'], 'registration_request_id':registration['request_id'],
                'registration_sha256':registration['registration_sha256'], 'reason':'Synthetic explicit primary'}
        primary = manager.advance_staged_primary(body)['controller']['result']['child']
        feedback = {'request_id':'synthetic-feedback', 'project_id':project.status()['id'],
                    'expected_state_version':project.status()['state_version'], 'registration_request_id':registration['request_id'],
                    'registration_sha256':registration['registration_sha256'], 'primary_action_id':primary['id']}
        return manager,project,feedback

    def test_wait_is_terminal_without_child_or_new_tool(self):
        manager,project,body = self.fixture('wait'); before=project.status()
        answer=manager.advance_staged_feedback(body)
        self.assertEqual(answer['status'],'waiting')
        self.assertIsNone(answer['controller']['child_request_id'])
        self.assertEqual(len(project.status()['actions']),1)
        with patch.object(ProjectController,'_dispatch',side_effect=AssertionError('no dispatch')):
            self.assertTrue(manager.resume_staged_feedback({'request_id':body['request_id'],'project_id':body['project_id']})['replayed'])
        self.assertEqual(project.status()['budget'],before['budget'])

    def test_audit_once_and_terminal_resume(self):
        for outcome in ('met','not_met'):
          with self.subTest(outcome=outcome):
            manager,project,body = self.fixture('audit',outcome); before=project.status()
            self.assertEqual(hypothesis_feedback.feedback_context(project,before)['items'][0]['outcome'],'condition_'+outcome)
            with patch.object(relevance_retrieval_adapter,'retrieve',side_effect=AssertionError('no reranking')), \
                 patch.object(retrieval_lexical,'metrics',side_effect=AssertionError('no rescoring')):
                answer=manager.advance_staged_feedback(body)
            self.assertEqual(answer['status'],'completed')
            state=project.status();self.assertEqual(len(state['actions']),2)
            self.assertEqual(state['budget']['local_tool_calls_used'],before['budget']['local_tool_calls_used']+1)
            with patch.object(ProjectController,'_dispatch',side_effect=AssertionError('no dispatch')):
                self.assertTrue(manager.resume_staged_feedback({'request_id':body['request_id'],'project_id':body['project_id']})['replayed'])
            self.assertEqual(project.status(),state)

    def test_unknown_fault_stops_without_parent_or_dispatch(self):
        manager,project,body=self.fixture('audit');before=project.status()
        with patch.object(staged_feedback_reader,'read_validation_deltas',return_value=[None,0]):
            with self.assertRaises(ResearchError): manager.advance_staged_feedback(body)
        self.assertEqual(project.status(),before)
        self.assertFalse(any(p['request_id']==body['request_id'] for p in project.status()['controller_requests']))

    def test_missing_primary_intent_or_claim_stops_before_feedback(self):
        manager,project,body=self.fixture('audit');before=project.status()
        with project._connect() as con:
            con.execute("DELETE FROM quality_manager_claims WHERE kind='staged_primary_child'")
        with self.assertRaises(ResearchError): manager.advance_staged_feedback(body)
        self.assertEqual(project.status(),before)

    def test_interrupted_original_id_never_dispatches_and_blocks_old_entry(self):
        manager,project,body=self.fixture('audit');before=project.status()
        with patch.object(ProjectController,'_advance_staged_feedback',side_effect=RuntimeError('before core')):
            with self.assertRaises(RuntimeError): manager.advance_staged_feedback(body)
        with patch.object(ProjectController,'_advance_staged_feedback',side_effect=AssertionError('no dispatch')):
            with self.assertRaises(ResearchError): manager.advance_staged_feedback(body)
            with self.assertRaises(ResearchError): manager.resume_staged_feedback({'request_id':body['request_id'],'project_id':body['project_id']})
            with self.assertRaises(ResearchError): manager.advance_feedback({k:v for k,v in body.items() if k not in ('registration_sha256','primary_action_id')})
        changed=copy.deepcopy(body);changed['primary_action_id']='different-action'
        with self.assertRaises(ResearchError) as error: manager.advance_staged_feedback(changed)
        self.assertEqual(error.exception.code,'IDEMPOTENCY_CONFLICT')
        self.assertEqual(project.status(),before)

    def test_primary_drift_between_policy_read_and_parent_acceptance(self):
        original_advance=ProjectController._advance_staged_feedback
        original_read=staged_feedback_reader._checked_primary
        for kind in ('source','artifact','sql'):
          with self.subTest(kind=kind):
            manager,project,body=self.fixture('audit');before=project.status();primary=before['actions'][0]
            def advancing(controller,**kwargs):
              calls=0
              def corrupt(*args,**kw):
                nonlocal calls
                result=original_read(*args,**kw);calls+=1
                if calls==1:
                    if kind=='source':
                        path=project.root/'source.json';path.write_bytes(path.read_bytes()+b' ')
                    elif kind=='artifact':
                        path=project.root/primary['artifact'];path.write_bytes(path.read_bytes()+b' ')
                    else:
                        with project._connect() as con: con.execute("UPDATE actions SET fingerprint=? WHERE request_id=?",('0'*64,primary['request_id']))
                return result
              with patch.object(staged_feedback_reader,'_checked_primary',side_effect=corrupt):
                  return original_advance(controller,**kwargs)
            with patch.object(ProjectController,'_advance_staged_feedback',new=advancing):
                with self.assertRaises(ResearchError): manager.advance_staged_feedback(body)
            state=project.status();self.assertEqual(len(state['actions']),1)
            self.assertEqual(state['budget'],before['budget'])
            self.assertFalse(any(p['request_id']==body['request_id'] for p in state['controller_requests']))
            with project._connect(readonly=True) as con:
                self.assertIsNone(con.execute("SELECT 1 FROM quality_manager_claims WHERE kind='staged_feedback_parent'").fetchone())

    def test_primary_sql_drift_before_child_acceptance_preserves_parent(self):
        manager,project,body=self.fixture('audit');before=project.status();primary=before['actions'][0]
        original_dispatch=ProjectController._dispatch;original_read=staged_feedback_reader._checked_primary
        def dispatch(controller,parent,**kwargs):
            if kwargs.get('_staged_feedback') is None: return original_dispatch(controller,parent,**kwargs)
            calls=0
            def corrupt(*args,**kw):
                nonlocal calls
                result=original_read(*args,**kw);calls+=1
                if calls==1:
                    with project._connect() as con: con.execute("UPDATE actions SET fingerprint=? WHERE request_id=?",('0'*64,primary['request_id']))
                return result
            with patch.object(staged_feedback_reader,'_checked_primary',side_effect=corrupt):
                return original_dispatch(controller,parent,**kwargs)
        with patch.object(ProjectController,'_dispatch',new=dispatch):
            with self.assertRaises(ResearchError): manager.advance_staged_feedback(body)
        state=project.status();self.assertEqual(len(state['actions']),1);self.assertEqual(state['budget'],before['budget'])
        self.assertEqual(state['controller_requests'][-1]['status'],'prepared')
        with project._connect(readonly=True) as con:
            self.assertIsNone(con.execute("SELECT 1 FROM quality_manager_claims WHERE kind='staged_feedback_child'").fetchone())

    def test_primary_sql_drift_during_terminal_inspection_stops_receipt(self):
        manager,project,body=self.fixture('audit');primary=project.status()['actions'][0]
        original_inspect=manager._inspect_staged_feedback_checked;original_read=staged_project_experience._read
        def inspecting(*args,**kwargs):
            calls=0
            def corrupt(p,action):
                nonlocal calls
                result=original_read(p,action)
                if action['command']==staged.AUDIT_TOOL_ID:
                    calls+=1
                    if calls==1:
                        with project._connect() as con: con.execute("UPDATE actions SET fingerprint=? WHERE request_id=?",('0'*64,primary['request_id']))
                return result
            with patch.object(staged_project_experience,'_read',side_effect=corrupt): return original_inspect(*args,**kwargs)
        with patch.object(manager,'_inspect_staged_feedback_checked',side_effect=inspecting):
            with self.assertRaises(ResearchError): manager.advance_staged_feedback(body)
        state=project.status();self.assertEqual(len(state['actions']),2)
        with manager._connect(readonly=True) as con:
            import json
            row=con.execute('SELECT record FROM requests WHERE id=?',(body['request_id'],)).fetchone()
            self.assertEqual(json.loads(row['record'])['status'],'preparing')

    def test_primary_drift_after_audit_acceptance_stops_before_adapter(self):
        manager,project,body=self.fixture('audit');primary=project.status()['actions'][0]
        original_dispatch=ProjectController._dispatch
        from autoresearch.local_workbench import _check_staged_runtime as original_runtime
        def dispatch(controller,parent,**kwargs):
            if kwargs.get('_staged_feedback') is None: return original_dispatch(controller,parent,**kwargs)
            calls=0
            def runtime():
                nonlocal calls
                calls+=1
                if calls==3:
                    with project._connect() as con: con.execute("UPDATE actions SET fingerprint=? WHERE request_id=?",('0'*64,primary['request_id']))
                return original_runtime()
            with patch('autoresearch.local_workbench._check_staged_runtime',side_effect=runtime), \
                 patch.object(staged.AUDIT,'execute_saved',side_effect=AssertionError('adapter must not run')):
                return original_dispatch(controller,parent,**kwargs)
        with patch.object(ProjectController,'_dispatch',new=dispatch):
            with self.assertRaises(ResearchError): manager.advance_staged_feedback(body)
        state=project.status();self.assertEqual(len(state['actions']),2)
        self.assertEqual(state['actions'][-1]['status'],'running')
        self.assertEqual(state['budget']['local_tool_calls_used'],1)
        self.assertEqual(state['budget']['local_tool_calls_reserved'],1)
        with project._connect(readonly=True) as con:
            self.assertIsNotNone(con.execute("SELECT 1 FROM quality_manager_claims WHERE kind='staged_feedback_child'").fetchone())

    def test_parent_only_old_project_and_controller_entries_cannot_dispatch(self):
        manager,project,body=self.fixture('audit');before=project.status()
        with patch.object(ProjectController,'_dispatch',side_effect=RuntimeError('after parent')):
            with self.assertRaises(RuntimeError): manager.advance_staged_feedback(body)
        state=project.status();parent=state['controller_requests'][-1];self.assertEqual(parent['status'],'prepared')
        for request_id in (parent['child_request_id'],'other-audit'):
            with self.assertRaises(ResearchError):
                project.step(request_id=request_id, method_id=staged.AUDIT_TOOL_ID,
                    parameters={'based_on_action_id':body['primary_action_id'],'based_on_result_sha256':state['actions'][0]['result_sha256']},
                    expected_state_version=state['state_version'])
        with self.assertRaises(ResearchError): project.resume(request_id=parent['child_request_id'])
        with self.assertRaises(ResearchError):
            ProjectController(project.root).advance_feedback(request_id=body['request_id'],registration_request_id=body['registration_request_id'],
                                                             expected_state_version=body['expected_state_version'])
        with self.assertRaises(ResearchError): manager.resume_staged_feedback({'request_id':body['request_id'],'project_id':body['project_id']})
        self.assertEqual(project.status(),state);self.assertEqual(state['budget'],before['budget'])

    def test_audit_branch_without_remaining_budget_waits_without_child(self):
        manager,project,body=self.fixture('audit',limit_one=True);before=project.status()
        self.assertEqual(before['budget']['local_tool_call_limit'],1)
        self.assertEqual(before['budget']['local_tool_calls_used'],1)
        result=manager.advance_staged_feedback(body)
        self.assertEqual(result['status'],'waiting');self.assertIsNone(result['controller']['child_request_id'])
        self.assertIn('audit candidate is unavailable',result['controller']['selection_proposal']['rationale'])
        state=project.status();self.assertEqual(state['budget'],before['budget']);self.assertEqual(len(state['actions']),1)

    def test_new_v2_holdout_uses_original_policy_audit_before_freeze(self):
        from test_feedback_selected_holdout import FeedbackSelectedHoldoutTests
        helper=FeedbackSelectedHoldoutTests();self.addCleanup(helper.doCleanups)
        manager,project,_,_,prediction=helper.fixture(register_prediction=False,execute=False,audit_notmet=True)
        registration=manager.register_staged_hypothesis({'request_id':'prediction','project_id':project.status()['id'],
            'expected_state_version':project.status()['state_version'],'hypothesis':prediction})['registration']
        primary=manager.advance_staged_primary({'request_id':registration['controller_request_id'],'project_id':project.status()['id'],
            'expected_state_version':project.status()['state_version'],'registration_request_id':registration['request_id'],
            'registration_sha256':registration['registration_sha256'],'reason':'synthetic'})['controller']['result']['child']
        feedback=manager.advance_staged_feedback({'request_id':'policy-audit','project_id':project.status()['id'],
            'expected_state_version':project.status()['state_version'],'registration_request_id':registration['request_id'],
            'registration_sha256':registration['registration_sha256'],'primary_action_id':primary['id']})
        self.assertEqual(feedback['status'],'completed')
        state=project.status();frozen=project.freeze_retrieval_strategy(request_id='synthetic-freeze',
            expected_state_version=state['state_version'],primary_action_id=primary['id'])
        self.assertEqual(frozen['feedback_binding']['audit_parent_request_id'],'policy-audit')
        self.assertEqual(len(project.status()['actions']),2)  # No final action.

    def test_tampered_audit_bytes_or_parent_identity_cannot_reconcile(self):
        for kind in ('artifact','parent'):
          with self.subTest(kind=kind):
            manager,project,body=self.fixture('audit');manager.advance_staged_feedback(body);state=project.status()
            if kind=='artifact':
                path=project.root/state['actions'][-1]['artifact'];path.write_bytes(path.read_bytes()+b' ')
            else:
                with project._writer(),project._connect() as con:
                    stored=project._project(con);stored['controller_requests'][-1]['controller_code_identity']='0'*64;project._save(con,stored)
            with self.assertRaises(ResearchError):
                manager.resume_staged_feedback({'request_id':body['request_id'],'project_id':body['project_id']})
            self.assertEqual(len(project.status()['actions']),2)

    def test_new_http_feedback_and_resume_enforce_origin(self):
        from test_local_workbench_http import LocalWorkbenchHTTPTests
        manager,project,body=self.fixture('wait');before=project.status()
        helper=LocalWorkbenchHTTPTests();self.addCleanup(helper.doCleanups)
        server=helper.serve(local_workspace=manager,allow_local_actions=True);headers=helper.session(server)
        status,_=helper.request(server,'/api/local-workbench/staged-feedback','POST',body,{**headers,'X-AutoResearch-CSRF':'wrong'})
        self.assertEqual(status,403);self.assertEqual(project.status(),before)
        status,result=helper.request(server,'/api/local-workbench/staged-feedback','POST',body,headers)
        self.assertEqual((status,result['status']),(200,'waiting'))
        status,result=helper.request(server,'/api/local-workbench/staged-feedback-resume','POST',
                                     {'request_id':body['request_id'],'project_id':body['project_id']},headers)
        self.assertEqual(status,200);self.assertTrue(result['replayed']);self.assertEqual(len(project.status()['actions']),1)


if __name__ == '__main__':
    unittest.main()
