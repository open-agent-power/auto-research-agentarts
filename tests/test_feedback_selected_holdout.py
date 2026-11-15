"""Opt-in predeclared feedback selection, synthetic research only."""
import base64
import copy
import json
import os
import random
import subprocess
import sys
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import test_staged_relevance_adapter as fixtures
import test_local_workbench_http as http_fixtures
from autoresearch import (retrieval_holdout as holdout, staged_relevance_adapter as staged,
                          staged_project_experience, staged_continuation, project_selection)
from autoresearch.contracts import ResearchError,canonical,fingerprint
from autoresearch.local_workbench import LocalWorkbench
from autoresearch.project_controller import ProjectController
from autoresearch.research_project import ResearchProject


class FeedbackSelectedHoldoutTests(unittest.TestCase):
    def fixture(self, *, threshold=0, register_prediction=True, execute=True, register_holdout=True, audit_notmet=False):
        helper=fixtures.StagedDevelopmentTests();helper.setUp();self.addCleanup(helper.doCleanups)
        rng=random.Random(108); words=['amber','blue','cyan','denim','ecru']
        docs=[{'_id':str(i),'title':'','text':' '.join(w for w in words for _ in range(rng.randint(0,5))),'metadata':{}} for i in range(40)]
        queries=[{'_id':'qd','text':'amber','metadata':{}},{'_id':'qv','text':'amber blue cyan','metadata':{}}]
        (helper.root/'corpus.jsonl').write_text(fixtures._rows(docs));(helper.root/'queries.jsonl').write_text(fixtures._rows(queries))
        (helper.root/'qrels.tsv').write_text('query-id\tcorpus-id\tscore\nqd\t1\t1\nqv\t1\t1\n');helper.write_spec()
        packet=helper.capture();case_root=os.environ.get('S063_CASE_ROOT')
        if case_root:
            root=Path(case_root);root.mkdir(parents=True,exist_ok=False)
        else:
            root=Path(self.enterContext(tempfile.TemporaryDirectory()))
        (root/'input').mkdir();source=root/'input/source.json';source.write_text(canonical(packet))
        original=ResearchProject(root/'original');original.create(source=source,goal='Synthetic fixed feedback selection',budget_ref='fixture',max_tool_calls=3,method_id=staged.TOOL_ID)
        original.save_plan(request_id='plan',expected_state_version=original.status()['state_version'],
            plan={'question':'Fixture?','basis':'Synthetic','steps':'Fixed comparison','expected_feedback':'Saved validation'},reason='Fixture')
        manager=LocalWorkbench(root/'manager');project_id=manager.import_project(request_id='import',workspace=original.root)['project_id']
        manager.select({'request_id':'select','project_id':project_id});project,_=manager.binding()
        private={'schema_version':'retrieval-holdout-v1','corpus_sha256':packet['assets']['corpus']['sha256'],
            'queries_jsonl':canonical({'_id':'final-q','text':'SECRET_FINAL amber','metadata':{}})+'\n',
            'qrels_tsv':'query-id\tcorpus-id\tscore\nfinal-q\t1\t1\n'}
        policy={'kind':'registered_feedback','registration_request_id':'prediction','condition_met':'tfidf_cosine',
                'condition_not_met':'bm25','unknown':'stop'}
        body={'request_id':'holdout','project_id':project_id,'expected_state_version':project.status()['state_version'],
              'holdout_base64':base64.b64encode(canonical(private).encode()).decode(),'selection_policy':policy}
        if not register_holdout:return manager,project,body,None,None
        saved=manager.register_holdout(body);self.assertEqual(saved['private_evaluation']['schema_version'],'retrieval-holdout-registration-v2')
        self.assertTrue(manager.register_holdout(body)['replayed'])
        controller=ProjectController(project.root);ctx=controller.selection_context();candidate=next(x for x in ctx['candidates'] if x['method_id']==staged.TOOL_ID)
        prediction={'candidate_id':candidate['id'],'controller_request_id':'primary',
           'conditions':[{'metric':'recall@20','operator':'gte','threshold':0},{'metric':'mrr@10','operator':'gt','threshold':threshold}],
           'branches':{'condition_met':{'kind':'method','method_id':staged.AUDIT_TOOL_ID},
                       'condition_not_met':({'kind':'method','method_id':staged.AUDIT_TOOL_ID} if audit_notmet else {'kind':'wait'})}}
        record=None
        if register_prediction:record=project.register_hypothesis(request_id='prediction',expected_state_version=ctx['state_version'],hypothesis=prediction)
        if execute:
            ctx=controller.selection_context();proposal={'schema_version':'project-selection-proposal-v1','context_sha256':ctx['context_sha256'],
                'provider':{'kind':'human','label':'Synthetic fixture'},'choice':{'kind':'execute','candidate_id':candidate['id']},
                'rationale':'Original synthetic primary','evidence_citation_ids':[]}
            controller.advance_selection(request_id='primary',expected_state_version=ctx['state_version'],proposal=proposal)
        return manager,project,body,record,prediction

    def test_real_conditional_flow_uses_predeclared_feedback_when_recall_is_zero(self):
        manager,project,body,record,prediction=self.fixture();state=project.status()
        context=ProjectController(project.root).selection_context();item=context['hypothesis_feedback']['items'][0]
        self.assertEqual(item['outcome'],'condition_met');self.assertEqual(item['value'][0],0);self.assertGreater(item['value'][1],0)
        self.assertEqual(context['staged_evaluation']['schema_version'],'staged-evaluation-context-v2')
        request={'request_id':'continue','project_id':state['id'],'expected_state_version':state['state_version'],
                 'primary_action_id':state['actions'][0]['id'],'reason':'Synthetic conditional continuation',
                 'registration_request_id':'prediction'}
        result=manager.continue_staged(request)
        if result['phase'] == 'report':
            from autoresearch import project_report
            project_report.collect_report(project.root)
        self.assertEqual((result['status'],result['phase']),('completed','done'),result.get('stop'))
        after=project.status();frozen=after['frozen_evaluation_strategy']
        self.assertEqual(frozen['schema_version'],'retrieval-holdout-freeze-v2')
        self.assertEqual(frozen['validation_delta_recall20'],0)
        self.assertEqual(frozen['selected_method'],'tfidf_cosine')
        self.assertEqual(frozen['feedback_binding']['registration_sha256'],record['registration_sha256'])
        self.assertEqual(frozen['feedback_binding']['outcome'],'condition_met')
        self.assertEqual([a['command'] for a in after['actions']],[staged.TOOL_ID,staged.AUDIT_TOOL_ID,holdout.FINAL_TOOL_ID])
        self.assertEqual(after['budget']['local_tool_calls_used'],3)
        self.assertEqual((after['budget']['new_fits'],after['budget']['new_model_requests']),(0,0))
        self.assertEqual(LocalWorkbench(manager.root).continue_staged(request),result)
        self.assertEqual(project.status(),after)
        with self.assertRaises(ResearchError) as error:staged_project_experience.derive_staged_observation(project.root,state['actions'][0]['id'])
        self.assertEqual(error.exception.code,'METHOD_NOT_SUPPORTED')

    def test_wait_branch_refuses_lowlevel_freeze_and_s052_waits(self):
        manager,project,_,_,_=self.fixture(threshold=1);state=project.status();primary=state['actions'][0]['id']
        with self.assertRaises(ResearchError):project.freeze_retrieval_strategy(request_id='freeze',expected_state_version=state['state_version'],primary_action_id=primary)
        self.assertEqual(project.status(),state)
        body={'request_id':'continue','project_id':state['id'],'expected_state_version':state['state_version'],
              'primary_action_id':primary,'reason':'Synthetic waiting branch','registration_request_id':'prediction'}
        result=manager.continue_staged(body);self.assertEqual((result['phase'],result['conditional']['feedback']['outcome']),('waiting','condition_not_met'))
        self.assertEqual(project.status(),state)

    def test_missing_registration_and_v1_continuation_cannot_freeze_or_dispatch(self):
        manager,project,_,_,_=self.fixture(register_prediction=False);state=project.status();primary=state['actions'][0]['id']
        with self.assertRaises(ResearchError):project.freeze_retrieval_strategy(request_id='freeze',expected_state_version=state['state_version'],primary_action_id=primary)
        request={'request_id':'continue','project_id':state['id'],'expected_state_version':state['state_version'],
                 'primary_action_id':primary,'reason':'Do not bypass the declared policy'}
        with self.assertRaises(ResearchError):manager.continue_staged(request)
        self.assertEqual(project.status(),state);self.assertEqual(len(state['actions']),1)
        with manager._connect(readonly=True) as con:self.assertIsNone(con.execute("SELECT 1 FROM requests WHERE id='continue'").fetchone())

    def test_hand_selected_audit_cannot_be_passed_as_the_registered_branch(self):
        manager,project,_,_,_=self.fixture();controller=ProjectController(project.root);ctx=controller.selection_context()
        candidate=next(x for x in ctx['candidates'] if x['method_id']==staged.AUDIT_TOOL_ID)
        proposal={'schema_version':'project-selection-proposal-v1','context_sha256':ctx['context_sha256'],
          'provider':{'kind':'human','label':'Manual'},'choice':{'kind':'execute','candidate_id':candidate['id']},
          'rationale':'Manual audit, not the predeclared branch','evidence_citation_ids':[]}
        controller.advance_selection(request_id='manual-audit',expected_state_version=ctx['state_version'],proposal=proposal)
        state=project.status()
        with self.assertRaises(ResearchError):project.freeze_retrieval_strategy(request_id='freeze',expected_state_version=state['state_version'],primary_action_id=state['actions'][0]['id'])
        self.assertEqual(project.status(),state);self.assertNotIn('frozen_evaluation_strategy',state)

    def test_bad_policy_rejected_before_manager_acceptance_or_private_write(self):
        manager,project,body,_,_=self.fixture(register_holdout=False)
        for policy in (None,{}, {**body['selection_policy'],'unknown':'bm25'}, {**body['selection_policy'],'registration_request_id':'holdout'}):
            request={**body,'selection_policy':policy};before=project.status()
            with self.subTest(policy=policy),self.assertRaises(ResearchError):manager.register_holdout(request)
            self.assertEqual(project.status(),before)
            with manager._connect(readonly=True) as con:self.assertIsNone(con.execute("SELECT 1 FROM requests WHERE id='holdout'").fetchone())
            self.assertFalse((project.root/'private_evaluation').exists())
        with self.assertRaises(ResearchError):project.register_holdout(request_id='holdout',expected_state_version=body['expected_state_version'],holdout=base64.b64decode(body['holdout_base64']),selection_policy=None)

    def test_future_registration_id_claimed_by_other_command_cannot_freeze(self):
        manager,project,_,_,_=self.fixture(register_prediction=False,execute=False)
        controller=ProjectController(project.root);ctx=controller.selection_context()
        candidate=next(x for x in ctx['candidates'] if x['method_id']==staged.TOOL_ID)
        proposal={'schema_version':'project-selection-proposal-v1','context_sha256':ctx['context_sha256'],
                  'provider':{'kind':'human','label':'Synthetic fixture'},'choice':{'kind':'execute','candidate_id':candidate['id']},
                  'rationale':'Other command claimed the future ID','evidence_citation_ids':[]}
        controller.advance_selection(request_id='prediction',expected_state_version=ctx['state_version'],proposal=proposal)
        before=project.status()
        with self.assertRaises(ResearchError):
            project.freeze_retrieval_strategy(request_id='freeze',expected_state_version=before['state_version'],primary_action_id=before['actions'][0]['id'])
        self.assertEqual(project.status(),before)
        self.assertNotIn('frozen_evaluation_strategy',before)
        self.assertEqual(before['budget']['local_tool_calls_used'],1)

    def test_loopback_http_and_fresh_process_same_id_replay(self):
        manager,project,body,_,_=self.fixture(register_holdout=False)
        http=http_fixtures.LocalWorkbenchHTTPTests();http.addCleanup=self.addCleanup
        server=http.serve(local_workspace=manager,allow_local_actions=True);headers=http.session(server)
        def post(path, request):
            status,result=http.request(server,path,'POST',request,headers)
            self.assertEqual(status,200,result)
            return result
        registration=post('/api/local-workbench/retrieval-holdout',body)
        self.assertTrue(post('/api/local-workbench/retrieval-holdout',body)['replayed'])
        controller=ProjectController(project.root);ctx=controller.selection_context()
        candidate=next(x for x in ctx['candidates'] if x['method_id']==staged.TOOL_ID)
        prediction={'candidate_id':candidate['id'],'controller_request_id':'primary',
            'conditions':[{'metric':'recall@20','operator':'gte','threshold':0},{'metric':'mrr@10','operator':'gt','threshold':0}],
            'branches':{'condition_met':{'kind':'method','method_id':staged.AUDIT_TOOL_ID},'condition_not_met':{'kind':'wait'}}}
        hypothesis_body={'request_id':'prediction','project_id':body['project_id'],
                         'expected_state_version':ctx['state_version'],'hypothesis':prediction}
        hypothesis_receipt=post('/api/local-workbench/hypothesis',hypothesis_body)
        ctx=controller.selection_context()
        proposal={'schema_version':'project-selection-proposal-v1','context_sha256':ctx['context_sha256'],
                  'provider':{'kind':'human','label':'Synthetic HTTP'},'choice':{'kind':'execute','candidate_id':candidate['id']},
                  'rationale':'Declared synthetic primary','evidence_citation_ids':[]}
        primary_body={'request_id':'primary','project_id':body['project_id'],
                      'expected_state_version':ctx['state_version'],'proposal':proposal}
        primary_receipt=post('/api/local-workbench/advance',primary_body)
        state=project.status()
        request={'request_id':'continue','project_id':body['project_id'],'expected_state_version':state['state_version'],
                 'primary_action_id':state['actions'][0]['id'],'reason':'Synthetic HTTP conditional flow','registration_request_id':'prediction'}
        result=post('/api/local-workbench/staged-continue',request)
        self.assertEqual((result['status'],result['phase']),('completed','done'))
        after=project.status();self.assertEqual(after['budget']['local_tool_calls_used'],3)
        child='''import http.client,json,sys,threading
from autoresearch.local_workbench import LocalWorkbench
from autoresearch.project_workbench import create_project_server
s=create_project_server(port=0,local_workspace=LocalWorkbench(sys.argv[1]),allow_local_actions=True)
t=threading.Thread(target=s.serve_forever,daemon=True);t.start()
def call(path,method="GET",body=None,headers={}):
 c=http.client.HTTPConnection("127.0.0.1",s.server_port,timeout=30);c.request(method,path,body,headers);r=c.getresponse();value=json.loads(r.read());c.close();return r.status,value
_,meta=call("/api/local-workbench")
h={"Origin":f"http://127.0.0.1:{s.server_port}","X-AutoResearch-CSRF":meta["csrf_token"] or "disabled","Content-Type":"application/json"}
status,value=call("/api/local-workbench/staged-continue","POST",sys.stdin.read(),h)
print(json.dumps({"status":status,"value":value},sort_keys=True));s.shutdown();s.server_close();t.join()
'''
        child_result=subprocess.run([sys.executable,'-B','-c',child,str(manager.root)],input=canonical(request),text=True,
                                    capture_output=True,env=os.environ.copy(),timeout=60,check=True)
        replay=json.loads(child_result.stdout)
        self.assertEqual((replay['status'],replay['value']),(200,result))
        self.assertEqual(project.status(),after)
        if os.environ.get('S063_CASE_ROOT'):
            (manager.root.parent/'case-evidence.json').write_text(canonical({'holdout_body':body,'holdout_receipt':registration,
                'hypothesis_body':hypothesis_body,'hypothesis_receipt':hypothesis_receipt,'primary_body':primary_body,
                'primary_receipt':primary_receipt,'continue_body':request,'continue_receipt':result,
                'fresh_process_http_replay':replay,'final_state':after})+'\n')

    def test_unmet_condition_with_declared_audit_selects_declared_baseline(self):
        manager,project,_,record,_=self.fixture(threshold=1,audit_notmet=True)
        state=project.status()
        request={'request_id':'continue','project_id':state['id'],'expected_state_version':state['state_version'],
                 'primary_action_id':state['actions'][0]['id'],'reason':'Declared unmet branch','registration_request_id':'prediction'}
        result=manager.continue_staged(request)
        self.assertEqual((result['status'],result['phase']),('completed','done'))
        after=project.status();frozen=after['frozen_evaluation_strategy']
        self.assertEqual(frozen['selected_method'],'bm25')
        self.assertEqual(frozen['feedback_binding']['outcome'],'condition_not_met')
        self.assertEqual(frozen['feedback_binding']['registration_sha256'],record['registration_sha256'])
        self.assertEqual(after['budget']['local_tool_calls_used'],3)
        if os.environ.get('S063_CASE_ROOT'):
            child='import json,sys; from autoresearch.local_workbench import LocalWorkbench; print(json.dumps(LocalWorkbench(sys.argv[1]).continue_staged(json.load(sys.stdin)),sort_keys=True))'
            completed=subprocess.run([sys.executable,'-B','-c',child,str(manager.root)],input=canonical(request),text=True,
                                     capture_output=True,env=os.environ.copy(),timeout=60,check=True)
            replay=json.loads(completed.stdout)
            self.assertEqual(replay,result);self.assertEqual(project.status(),after)
            (manager.root.parent/'case-evidence.json').write_text(canonical({'registration':record,'continue_body':request,
                'continue_receipt':result,'replay_receipt':replay,'final_state':after})+'\n')

    def test_freeze_uses_saved_public_evidence_without_private_holdout_read(self):
        manager,project,_,_,_=self.fixture();controller=ProjectController(project.root)
        ctx=controller.selection_context()
        controller.advance_feedback(request_id='audit',registration_request_id='prediction',expected_state_version=ctx['state_version'])
        state=project.status();original_path_open=Path.open;original_os_open=os.open
        def deny(path):
            if isinstance(path,(str,bytes,os.PathLike)) and 'private_evaluation' in Path(path).parts:
                raise AssertionError('private holdout accessed before final')
        def checked_path_open(path,*args,**kwargs):
            deny(path);return original_path_open(path,*args,**kwargs)
        def checked_os_open(path,*args,**kwargs):
            deny(path);return original_os_open(path,*args,**kwargs)
        with patch.object(Path,'open',checked_path_open),patch.object(os,'open',checked_os_open):
            frozen=project.freeze_retrieval_strategy(request_id='freeze',expected_state_version=state['state_version'],
                                                      primary_action_id=state['actions'][0]['id'])
        self.assertEqual(frozen['selected_method'],'tfidf_cosine')
        self.assertEqual(project.status()['budget']['local_tool_calls_used'],2)

    def test_resealed_different_audit_proposal_cannot_freeze(self):
        manager,project,_,_,_=self.fixture();controller=ProjectController(project.root)
        ctx=controller.selection_context()
        controller.advance_feedback(request_id='audit',registration_request_id='prediction',expected_state_version=ctx['state_version'])
        with project._writer(),project._connect() as con:
            state=project._project(con)
            parent=next(row for row in state['controller_requests'] if row['request_id']=='audit')
            parent['request']['proposal']['provider']['label']='Other resealed provider'
            parent['request_sha256']=fingerprint(parent['request'])
            project._save(con,state)
        before=project.status()
        with self.assertRaises(ResearchError):
            project.freeze_retrieval_strategy(request_id='freeze',expected_state_version=before['state_version'],
                                              primary_action_id=before['actions'][0]['id'])
        self.assertEqual(project.status(),before)
        self.assertNotIn('frozen_evaluation_strategy',before)

    def test_resealed_primary_or_audit_holdout_count_cannot_freeze(self):
        for parent_id in ('primary','audit'):
            with self.subTest(parent_id=parent_id):
                manager,project,_,_,_=self.fixture();controller=ProjectController(project.root)
                ctx=controller.selection_context()
                controller.advance_feedback(request_id='audit',registration_request_id='prediction',expected_state_version=ctx['state_version'])
                with project._writer(),project._connect() as con:
                    state=project._project(con)
                    parent=next(row for row in state['controller_requests'] if row['request_id']==parent_id)
                    context=parent['selection_context']
                    context['staged_evaluation']['query_count']+=1
                    sealed=project_selection.seal_context({k:v for k,v in context.items() if k!='context_sha256'})
                    parent['selection_context']=sealed
                    parent['request']['proposal']['context_sha256']=sealed['context_sha256']
                    parent['request_sha256']=fingerprint(parent['request'])
                    parent['decision']['selection_ref']['context_sha256']=sealed['context_sha256']
                    parent['decision_sha256']=fingerprint(parent['decision'])
                    project._save(con,state)
                before=project.status()
                with self.assertRaises(ResearchError) as caught:
                    project.freeze_retrieval_strategy(request_id='freeze',expected_state_version=before['state_version'],
                                                      primary_action_id=before['actions'][0]['id'])
                self.assertEqual(caught.exception.code,'EVIDENCE_CHANGED')
                self.assertEqual(project.status(),before)
                self.assertNotIn('frozen_evaluation_strategy',before)
