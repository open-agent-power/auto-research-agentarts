"""Predeclared policy through strict S111/S112/S115 and synthetic holdout; no real study."""
import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

import test_feedback_selected_holdout as fixtures
from autoresearch import hypothesis_feedback, retrieval_holdout, staged_relevance_adapter as staged
from autoresearch.contracts import ResearchError, canonical
from autoresearch.project_controller import ProjectController


class StrictFeedbackFinalSelectionTests(unittest.TestCase):
    def test_fixed_feedback_routes_to_distinct_frozen_and_final_methods(self):
        output_root = os.environ.get('S120_OUTPUT_ROOT')
        outcomes = []
        for label, negative, expected_outcome, expected_method in (
            ('met', False, 'condition_met', 'tfidf_cosine'),
            ('notmet', True, 'condition_not_met', 'bm25'),
        ):
            with self.subTest(label=label):
                helper = fixtures.FeedbackSelectedHoldoutTests(); self.addCleanup(helper.doCleanups)
                before_environment = os.environ.get('S063_CASE_ROOT')
                if output_root:
                    os.environ['S063_CASE_ROOT'] = str(Path(output_root).resolve() / label)
                try:
                    manager, project, holdout_body, _, prediction = helper.fixture(
                        register_prediction=False, execute=False, audit_notmet=True, negative=negative)
                finally:
                    if before_environment is None:
                        os.environ.pop('S063_CASE_ROOT', None)
                    else:
                        os.environ['S063_CASE_ROOT'] = before_environment
                self.assertEqual(prediction['conditions'], [
                    {'metric':'recall@20','operator':'gte','threshold':0},
                    {'metric':'mrr@10','operator':'gt','threshold':0}])
                audit = {'kind':'method','method_id':staged.AUDIT_TOOL_ID}
                self.assertEqual(prediction['branches'], {'condition_met':audit, 'condition_not_met':audit})
                self.assertEqual(holdout_body['selection_policy'], {'kind':'registered_feedback','registration_request_id':'prediction',
                    'condition_met':'tfidf_cosine','condition_not_met':'bm25','unknown':'stop'})
                initial = project.status(); self.assertEqual(initial['actions'], []); self.assertEqual(initial['budget']['local_tool_calls_used'], 0)
                reg_body = {'request_id':'prediction','project_id':initial['id'],
                    'expected_state_version':initial['state_version'],'hypothesis':prediction}
                registration = manager.register_staged_hypothesis(reg_body)['registration']
                self.assertLess(initial['private_evaluation']['state_version_before'],registration['state_version_before'])
                primary_body = {'request_id':registration['controller_request_id'],'project_id':initial['id'],
                    'expected_state_version':project.status()['state_version'],'registration_request_id':registration['request_id'],
                    'registration_sha256':registration['registration_sha256'],'reason':'Fixed synthetic feedback experiment'}
                primary = manager.advance_staged_primary(primary_body)['controller']['result']['child']
                state = project.status(); self.assertEqual(state['budget']['local_tool_calls_used'],1)
                observed = hypothesis_feedback.feedback_context(project,state)['items'][0]
                self.assertEqual(observed['outcome'],expected_outcome)
                self.assertEqual(observed['action_id'],primary['id'])
                feedback_body = {'request_id':'strict-feedback','project_id':initial['id'],'expected_state_version':state['state_version'],
                    'registration_request_id':registration['request_id'],'registration_sha256':registration['registration_sha256'],
                    'primary_action_id':primary['id']}
                feedback = manager.advance_staged_feedback(feedback_body)
                self.assertEqual(feedback['status'],'completed')
                state = project.status();self.assertEqual(state['budget']['local_tool_calls_used'],2)
                freeze_body = {'request_id':'freeze','project_id':initial['id'], 'expected_state_version':state['state_version'],
                               'primary_action_id':primary['id']}
                frozen = manager.freeze_retrieval_strategy(freeze_body)['frozen_evaluation_strategy']
                self.assertEqual(frozen['selected_method'],expected_method)
                self.assertEqual(frozen['feedback_binding']['outcome'],expected_outcome)
                self.assertEqual(frozen['feedback_binding']['audit_parent_request_id'],feedback_body['request_id'])
                frozen_state = project.status()
                with patch.object(staged.AUDIT, 'execute_saved', side_effect=AssertionError('must not re-audit')):
                    replay_before_final = manager.freeze_retrieval_strategy(freeze_body)
                self.assertTrue(replay_before_final['replayed']);self.assertEqual(replay_before_final['frozen_evaluation_strategy'],frozen)
                self.assertEqual(project.status(),frozen_state)
                params = {'based_on_action_id':primary['id'],'based_on_result_sha256':primary['result_sha256']}
                final_body = {'request_id':'final','expected_state_version':project.status()['state_version'],
                              'method_id':retrieval_holdout.FINAL_TOOL_ID,'parameters':params}
                final = project.step(**final_body); state = project.status()
                self.assertEqual(final['status'],'completed');self.assertEqual(state['budget']['local_tool_calls_used'],3)
                self.assertEqual([x['command'] for x in state['actions']], [staged.TOOL_ID,staged.AUDIT_TOOL_ID,retrieval_holdout.FINAL_TOOL_ID])
                for key in ('new_model_requests','model_requests_allowed','model_requests_reserved','new_fits','fit_attempts_used',
                            'fits_reserved','evidence_reads_used','local_tool_calls_reserved'):
                    self.assertEqual(state['budget'][key],0,key)
                envelope = json.loads(project._artifact(final).read_bytes()); result = envelope['tool_result']; retrieval_holdout.validate_final_result(result)
                self.assertEqual(result['result']['selected_method'],expected_method)
                self.assertEqual(result['result']['baseline_method'],'bm25')
                n = len(result['result']['per_query']);calls = n if expected_method=='bm25' else 2*n
                self.assertEqual(result['result']['usage']['ranking_calls'],calls);self.assertEqual(result['result']['usage']['scoring_calls'],calls)
                if expected_method=='bm25':
                    self.assertEqual(result['result']['summary']['delta']['recall@20'],0)
                    self.assertEqual(result['result']['summary']['delta']['mrr@10'],0)
                before = copy.deepcopy(state)
                replay_script = '''import json,os,sys\nfrom autoresearch.local_workbench import LocalWorkbench\nfrom autoresearch.research_project import ResearchProject\nx=json.load(sys.stdin);m=LocalWorkbench(x['manager']);p=ResearchProject(x['project']);before=p.status()\na=m.resume_staged_hypothesis({'request_id':x['registration']['request_id'],'project_id':x['registration']['project_id']})\nb=m.resume_staged_primary({'request_id':x['primary']['request_id'],'project_id':x['primary']['project_id']})\nc=m.resume_staged_feedback({'request_id':x['feedback']['request_id'],'project_id':x['feedback']['project_id']})\nd=m.freeze_retrieval_strategy(x['freeze']);e=p.step(**x['final']);after=p.status()\nassert before==after\nprint(json.dumps({'pid':os.getpid(),'registration':a,'primary':b,'feedback':c,'freeze':d,'final':e,'state_unchanged':before==after},sort_keys=True))'''
                replay_input = {'manager':str(manager.root),'project':str(project.root),'registration':reg_body,'primary':primary_body,
                                'feedback':feedback_body,'freeze':freeze_body,'final':final_body}
                completed = subprocess.run([sys.executable,'-B','-c',replay_script],input=canonical(replay_input),text=True,
                                           stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=60,check=False,env=os.environ.copy())
                self.assertEqual(completed.returncode,0,completed.stderr)
                replay=json.loads(completed.stdout);self.assertTrue(replay['state_unchanged']);self.assertNotEqual(replay['pid'],os.getpid());self.assertEqual(project.status(),before)
                self.assertTrue(replay['registration']['replayed']);self.assertTrue(replay['primary']['replayed']);self.assertTrue(replay['feedback']['replayed'])
                self.assertTrue(replay['freeze']['replayed']);self.assertEqual(replay['final']['id'],final['id'])
                outcomes.append((observed['outcome'],frozen['selected_method']))
                if output_root:
                    case = Path(output_root)/label
                    record = {'schema_version':'s120-synthetic-case-v1','label':label,'input_kind':'fully_synthetic',
                        'source_sha256':hashlib.sha256((project.root/'source.json').read_bytes()).hexdigest(),
                        'manager_root':str(manager.root),'project_root':str(project.root), 'holdout_body':holdout_body,
                        'registration_body':reg_body,'registration':registration,'primary_body':primary_body,'primary':primary,
                        'feedback_body':feedback_body,'feedback':feedback,'observed':observed,'freeze_body':freeze_body,'freeze':frozen,
                        'final_body':final_body,'final':final,'final_result':result,'final_state':state,'parent_pid':os.getpid(),'replay':replay,
                        'cost':'unknown','scientific_validation':False}
                    (case/'s120-receipt.json').write_text(canonical(record)+'\n')
        self.assertEqual(outcomes,[('condition_met','tfidf_cosine'),('condition_not_met','bm25')])


    def prepare_frozen(self):
        helper = fixtures.FeedbackSelectedHoldoutTests(); self.addCleanup(helper.doCleanups)
        manager, project, _, _, prediction = helper.fixture(register_prediction=False, execute=False, audit_notmet=True)
        state=project.status(); body={'request_id':'prediction','project_id':state['id'],'expected_state_version':state['state_version'],'hypothesis':prediction}
        registration=manager.register_staged_hypothesis(body)['registration']
        primary=manager.advance_staged_primary({'request_id':registration['controller_request_id'],'project_id':state['id'],
            'expected_state_version':project.status()['state_version'],'registration_request_id':registration['request_id'],
            'registration_sha256':registration['registration_sha256'],'reason':'Synthetic corruption control'})['controller']['result']['child']
        manager.advance_staged_feedback({'request_id':'strict-feedback','project_id':state['id'],
            'expected_state_version':project.status()['state_version'],'registration_request_id':registration['request_id'],
            'registration_sha256':registration['registration_sha256'],'primary_action_id':primary['id']})
        body={'request_id':'freeze','project_id':state['id'],'expected_state_version':project.status()['state_version'],'primary_action_id':primary['id']}
        manager.freeze_retrieval_strategy(body)
        return manager,project,body,primary

    def test_freeze_replay_rejects_changed_source_action_audit_plan_and_parent(self):
        for damage in ('source','primary_sql','audit_artifact','audit_missing','plan','parent','frozen'):
            with self.subTest(damage=damage):
                manager,project,body,primary=self.prepare_frozen();state=project.status()
                if damage=='source':
                    path=project.root/'source.json';path.write_bytes(path.read_bytes()+b' ')
                elif damage=='primary_sql':
                    with project._connect() as con:con.execute('UPDATE actions SET fingerprint=? WHERE request_id=?',('0'*64,primary['request_id']))
                elif damage in ('audit_artifact','audit_missing'):
                    action=next(a for a in state['actions'] if a['command']==staged.AUDIT_TOOL_ID);path=project.root/action['artifact']
                    if damage=='audit_artifact':path.write_bytes(b'{broken')
                    else:path.unlink()
                else:
                    with project._connect() as con:
                        raw=project._project(con)
                        if damage=='plan':raw['plan_revisions'][-1]['question']='changed synthetic plan'
                        elif damage=='parent':next(p for p in raw['controller_requests'] if p['request_id']=='strict-feedback')['decision_sha256']='0'*64
                        else:raw['frozen_evaluation_strategy']['record_sha256']='0'*64
                        project._save(con,raw)
                before=project.status()
                with patch.object(staged.AUDIT,'execute_saved',side_effect=AssertionError('no re-dispatch')):
                    with self.assertRaises(ResearchError) as caught:manager.freeze_retrieval_strategy(body)
                    if damage in ('audit_artifact','audit_missing'):self.assertEqual(caught.exception.code,'EVIDENCE_CHANGED')
                self.assertEqual(project.status(),before);self.assertEqual(before['budget']['local_tool_calls_used'],2)

    def test_http_freeze_replay_reports_malformed_evidence_without_dispatch(self):
        import test_local_workbench_http as http_fixtures
        manager,project,body,_=self.prepare_frozen();state=project.status()
        audit=next(a for a in state['actions'] if a['command']==staged.AUDIT_TOOL_ID)
        (project.root/audit['artifact']).write_bytes(b'{broken')
        before=project.status();http=http_fixtures.LocalWorkbenchHTTPTests();http.addCleanup=self.addCleanup
        server=http.serve(local_workspace=manager,allow_local_actions=True);headers=http.session(server)
        with patch.object(staged.AUDIT,'execute_saved',side_effect=AssertionError('no re-dispatch')):
            status,result=http.request(server,'/api/local-workbench/retrieval-freeze','POST',body,headers)
        self.assertEqual(status,400);self.assertEqual(result['code'],'EVIDENCE_CHANGED')
        self.assertEqual(project.status(),before);self.assertEqual(before['budget']['local_tool_calls_used'],2)

    def test_freeze_replay_rejects_different_id_and_snapshot_drift(self):
        _,project,body,_=self.prepare_frozen();before=project.status()
        with self.assertRaises(ResearchError):
            project.freeze_retrieval_strategy(request_id='different-freeze',expected_state_version=body['expected_state_version'],primary_action_id=body['primary_action_id'])
        self.assertEqual(project.status(),before)
        original_check=retrieval_holdout._check_frozen;original_status=project.status;verified=False
        def checked(*args,**kwargs):
            nonlocal verified
            value=original_check(*args,**kwargs);verified=True;return value
        def drifted():
            value=original_status()
            if verified:value['snapshot_ref']='0'*64
            return value
        with patch.object(retrieval_holdout,'_check_frozen',side_effect=checked),patch.object(project,'status',side_effect=drifted):
            with self.assertRaises(ResearchError):
                project.freeze_retrieval_strategy(request_id=body['request_id'],expected_state_version=body['expected_state_version'],primary_action_id=body['primary_action_id'])
        self.assertTrue(verified);self.assertEqual(project.status(),before)


if __name__ == '__main__':
    unittest.main()
