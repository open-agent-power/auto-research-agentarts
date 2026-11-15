"""Synthetic local manager/HTTP tests for a quality-linked plan and v2 policy."""
import copy
import json
import sqlite3
import subprocess
import sys
import unittest
from unittest.mock import patch

import test_local_workbench_http as http
import test_tabular_quality_workbench as workbench_fixture
from autoresearch.contracts import ResearchError, canonical, fingerprint
from autoresearch.local_workbench import LocalWorkbench
from autoresearch.project_controller import ProjectController
from autoresearch.research_project import ResearchProject
from autoresearch import tabular_quality_feedback as quality


class QualityPlanWorkbenchTests(unittest.TestCase):
    serve=http.LocalWorkbenchHTTPTests.serve
    request=http.LocalWorkbenchHTTPTests.request
    session=http.LocalWorkbenchHTTPTests.session

    def stage(self):
        helper=workbench_fixture.QualityWorkbenchTests(methodName='runTest')
        f,m,b=helper.stage();self.addCleanup(helper.doCleanups)
        m.register_tabular_quality_conditions(b);f.execute()
        return f,m,b

    def plan_body(self,f,b,ref=None):
        if ref is None:ref=f.project.prepare_tabular_quality_plan_ref(registration_request_id='reg')
        return {'request_id':'plan2','project_id':b['project_id'],'expected_state_version':f.project.status()['state_version'],
                'plan':{'question':'Synthetic linked plan','basis':'Saved quality evidence','steps':'Test association',
                        'expected_feedback':'Retain uncertainty','quality_feedback_ref':ref},'reason':'Synthetic'}

    def policy_body(self,f,b,plan):
        return {'request_id':'next','project_id':b['project_id'],'registration_request_id':'reg','plan_request_id':'plan2',
                'plan_sha256':fingerprint(plan),'expected_state_version':f.project.status()['state_version']}

    def error(self,code,fn,*args):
        with self.assertRaises(ResearchError) as err:fn(*args)
        self.assertEqual(err.exception.code,code)

    def test_real_http_end_to_end_and_security(self):
        f,m,b=self.stage();server=self.serve(local_workspace=m,allow_local_actions=True);headers=self.session(server)
        state=f.project.status();query='?project_id='+b['project_id']+'&snapshot_ref='+state['snapshot_ref']+'&registration_request_id=reg'
        before=(m.db.read_bytes(),f.project.db.read_bytes());status,ref=self.request(server,'/api/local-workbench/tabular-quality-plan-ref.json'+query)
        self.assertEqual(status,200,ref);self.assertEqual(before,(m.db.read_bytes(),f.project.db.read_bytes()))
        self.assertEqual(self.request(server,'/api/local-workbench/tabular-quality-plan-ref.json'+query+'&project_id=x')[0],400)
        body=self.plan_body(f,b,ref);route='/api/local-workbench/quality-plan'
        for h in ({**headers,'Origin':'http://external.invalid'},{**headers,'X-AutoResearch-CSRF':'bad'},
                  {**headers,'Host':'external.invalid'},{**headers,'Sec-Fetch-Site':'cross-site'}):
            self.assertEqual(self.request(server,route,'POST',body,h)[0],403)
        self.assertEqual(self.request(server,'/api/local-workbench/plan','POST',body,headers)[0],400)
        status,result=self.request(server,route,'POST',body,headers);self.assertEqual(status,200,result)
        plan=result['research_plan'];self.assertEqual(plan['quality_feedback_ref'],ref)
        self.assertEqual(self.request(server,route,'POST',body,headers)[0],200)
        after_plan=f.project.status();new_query='?project_id='+b['project_id']+'&snapshot_ref='+after_plan['snapshot_ref']+'&registration_request_id=reg'
        self.assertNotEqual(self.request(server,'/api/local-workbench/tabular-quality-plan-ref.json'+new_query)[0],200)
        policy=self.policy_body(f,b,plan)
        status,result=self.request(server,'/api/local-workbench/advance-tabular-quality-feedback-v2','POST',policy,headers)
        self.assertEqual(status,200,result);self.assertEqual(result['status'],'completed')
        state=f.project.status();self.assertEqual((state['budget']['local_tool_calls_used'],state['budget']['new_model_requests'],
              state['budget']['new_fits'],state['budget']['evidence_reads_used']),(2,0,0,0))
        with patch.object(ProjectController,'_dispatch',side_effect=AssertionError('redispatch')):
            self.assertEqual(LocalWorkbench(m.root).advance_tabular_quality_feedback_v2(policy)['status'],'completed')
        self.assertEqual(f.project.status(),state)
        readonly=self.serve(local_workspace=LocalWorkbench.open_readonly(m.root),allow_local_actions=False)
        self.assertEqual(self.request(readonly,'/api/local-workbench/tabular-quality-plan-ref.json'+query)[0],404)

    def test_plan_intent_missing_core_and_completed_receipt_loss(self):
        f,m,b=self.stage();body=self.plan_body(f,b)
        original=ResearchProject.save_plan
        def cut(project,**kwargs):
            if not kwargs.get('_validate_only'):raise KeyboardInterrupt('before core commit')
            return original(project,**kwargs)
        with patch.object(ResearchProject,'save_plan',new=cut),self.assertRaises(KeyboardInterrupt):m.save_quality_plan(body)
        before=f.project.status()
        with patch.object(ResearchProject,'save_plan',side_effect=AssertionError('no retry')):
            self.error('OPERATION_INCOMPLETE',m.save_quality_plan,body)
        self.assertEqual(f.project.status(),before)
        f,m,b=self.stage();body=self.plan_body(f,b);save=m._save
        def lose(con,request_id,record):
            if record.get('status')=='completed':raise KeyboardInterrupt('lost receipt')
            return save(con,request_id,record)
        with patch.object(m,'_save',side_effect=lose),self.assertRaises(KeyboardInterrupt):m.save_quality_plan(body)
        before=f.project.status();result=LocalWorkbench(m.root).save_quality_plan(body)
        self.assertTrue(result['replayed']);self.assertEqual(f.project.status(),before)

    def test_direct_core_plan_race_never_adopted(self):
        for different in (False,True):
            with self.subTest(different=different):
                f,m,b=self.stage();body=self.plan_body(f,b);original=ResearchProject.save_plan
                def race(project,**kwargs):
                    if not kwargs.get('_return_created'):return original(project,**kwargs)
                    direct={k:v for k,v in kwargs.items() if k not in ('_manager_intent_sha256','_return_created')}
                    if different:direct['reason']='Different synthetic reason'
                    original(project,**direct)
                    return original(project,**kwargs)
                with patch.object(ResearchProject,'save_plan',new=race):
                    self.error('IDEMPOTENCY_CONFLICT' if different else 'OPERATION_INCOMPLETE',m.save_quality_plan,body)
                before=f.project.status();self.error('OPERATION_INCOMPLETE',m.save_quality_plan,body)
                self.assertEqual(f.project.status(),before)

    def test_policy_core_missing_nonterminal_and_lost_receipt(self):
        for phase in ('before-parent','after-parent','after-result'):
            with self.subTest(phase=phase):
                f,m,b=self.stage();saved=m.save_quality_plan(self.plan_body(f,b))['research_plan'];body=self.policy_body(f,b,saved)
                if phase in ('before-parent','after-parent'):
                    target='advance_tabular_quality_feedback_v2' if phase=='before-parent' else '_dispatch'
                    with patch.object(ProjectController,target,side_effect=KeyboardInterrupt),self.assertRaises(KeyboardInterrupt):
                        m.advance_tabular_quality_feedback_v2(body)
                else:
                    save=m._save
                    def lose(con,request_id,record):
                        if record.get('status')=='completed':raise KeyboardInterrupt('lost receipt')
                        return save(con,request_id,record)
                    with patch.object(m,'_save',side_effect=lose),self.assertRaises(KeyboardInterrupt):m.advance_tabular_quality_feedback_v2(body)
                before=f.project.status()
                if phase=='after-result':
                    with patch.object(ProjectController,'_dispatch',side_effect=AssertionError('redispatch')):
                        self.assertEqual(LocalWorkbench(m.root).advance_tabular_quality_feedback_v2(body)['status'],'completed')
                else:
                    with patch.object(ProjectController,'advance_tabular_quality_feedback_v2',side_effect=AssertionError('retry')):
                        self.error('OPERATION_INCOMPLETE' if phase=='before-parent' else 'EXECUTION_UNKNOWN',
                                   m.advance_tabular_quality_feedback_v2,body)
                self.assertEqual(f.project.status(),before)

    def test_direct_policy_race_cannot_be_adopted(self):
        f,m,b=self.stage();plan=m.save_quality_plan(self.plan_body(f,b))['research_plan'];body=self.policy_body(f,b,plan)
        original=ProjectController.advance_tabular_quality_feedback_v2
        def race(controller,**kwargs):
            direct={k:v for k,v in kwargs.items() if k!='_manager_intent_sha256'}
            original(controller,**direct)
            return original(controller,**kwargs)
        with patch.object(ProjectController,'advance_tabular_quality_feedback_v2',new=race):
            self.error('OPERATION_INCOMPLETE',m.advance_tabular_quality_feedback_v2,body)
        before=f.project.status()
        with patch.object(ProjectController,'advance_tabular_quality_feedback_v2',side_effect=AssertionError('retry')):
            self.error('OPERATION_INCOMPLETE',m.advance_tabular_quality_feedback_v2,body)
        self.assertEqual(f.project.status(),before)

    def test_claim_atomicity_and_missing_claim(self):
        for kind in ('plan','policy'):
            with self.subTest(kind=kind):
                f,m,b=self.stage();plan_body=self.plan_body(f,b)
                if kind=='policy':plan=m.save_quality_plan(plan_body)['research_plan'];body=self.policy_body(f,b,plan)
                else:body=plan_body
                before=f.project.status();original=quality._manager_claim
                def fail(con,target,request,intent,core,**kw):
                    result=original(con,target,request,intent,core,**kw)
                    if target==kind and kw.get('create'):raise KeyboardInterrupt('before core commit')
                    return result
                with patch.object(quality,'_manager_claim',side_effect=fail),self.assertRaises(KeyboardInterrupt):
                    (m.save_quality_plan(body) if kind=='plan' else m.advance_tabular_quality_feedback_v2(body))
                self.assertEqual(f.project.status(),before)
                self.error('OPERATION_INCOMPLETE',m.save_quality_plan if kind=='plan' else m.advance_tabular_quality_feedback_v2,body)
        for kind in ('plan','policy'):
            with self.subTest(kind=kind,mode='missing'):
                f,m,b=self.stage();plan_body=self.plan_body(f,b)
                if kind=='policy':plan=m.save_quality_plan(plan_body)['research_plan'];body=self.policy_body(f,b,plan)
                else:body=plan_body
                save=m._save
                def lose(con,request_id,record):
                    if record.get('status')=='completed':raise KeyboardInterrupt('lost receipt')
                    return save(con,request_id,record)
                with patch.object(m,'_save',side_effect=lose),self.assertRaises(KeyboardInterrupt):
                    (m.save_quality_plan(body) if kind=='plan' else m.advance_tabular_quality_feedback_v2(body))
                with sqlite3.connect(f.project.db) as con:con.execute('delete from quality_manager_claims where kind=?',(kind,))
                before=f.project.status()
                self.error('OPERATION_INCOMPLETE',m.save_quality_plan if kind=='plan' else m.advance_tabular_quality_feedback_v2,body)
                self.assertEqual(f.project.status(),before)

    def test_cross_process_writer_excluded_before_manager_commit(self):
        code='''import json,sys
from autoresearch.contracts import ResearchError
from autoresearch.research_project import ResearchProject
from autoresearch.project_controller import ProjectController
p=ResearchProject(sys.argv[1]); kind=sys.argv[2]; b=json.loads(sys.argv[3])
try:
    if kind=="plan":p.save_plan(**b)
    else:ProjectController(p.root).advance_tabular_quality_feedback_v2(**b)
except ResearchError as e:print(e.code)
else:print("ACCEPTED")
'''
        for kind in ('plan','policy'):
            with self.subTest(kind=kind):
                f,m,b=self.stage();plan_body=self.plan_body(f,b)
                if kind=='policy':plan=m.save_quality_plan(plan_body)['research_plan'];body=self.policy_body(f,b,plan)
                else:body=plan_body
                original=m._accept;seen=[]
                def competing(con,accepted,digest,command,intent):
                    core={k:v for k,v in accepted.items() if k!='project_id'}
                    child=subprocess.run([sys.executable,'-B','-c',code,str(f.project.root),kind,json.dumps(core)],
                                         check=True,capture_output=True,text=True,timeout=15)
                    seen.append(child.stdout.strip())
                    return original(con,accepted,digest,command,intent)
                with patch.object(m,'_accept',side_effect=competing):
                    result=m.save_quality_plan(body) if kind=='plan' else m.advance_tabular_quality_feedback_v2(body)
                self.assertEqual(seen,['PROJECT_BUSY']);self.assertEqual(result['status'],'completed')

    def test_orphan_replays_both_directions_stop_before_intent(self):
        for position in ('request_id','action_request_id'):
            with self.subTest(position=position):
                f,m,b=self.stage();body=self.plan_body(f,b)
                row=('plan2','orphan') if position=='request_id' else ('alias','plan2')
                with sqlite3.connect(f.project.db) as con:con.execute('insert into replays values(?,?)',row)
                before=m.db.read_bytes();self.error('IDEMPOTENCY_CONFLICT',m.save_quality_plan,body)
                self.assertEqual(m.db.read_bytes(),before)

    def test_manager_intent_absent_or_tampered_cannot_adopt_core(self):
        for kind in ('plan','policy'):
            for mode in ('delete','nonce'):
                with self.subTest(kind=kind,mode=mode):
                    f,m,b=self.stage();pb=self.plan_body(f,b)
                    if kind=='policy':plan=m.save_quality_plan(pb)['research_plan'];body=self.policy_body(f,b,plan);fn=m.advance_tabular_quality_feedback_v2
                    else:body=pb;fn=m.save_quality_plan
                    fn(body);before=f.project.status()
                    with sqlite3.connect(m.db) as con:
                        if mode=='delete':con.execute('delete from requests where id=?',(body['request_id'],))
                        else:
                            rec=json.loads(con.execute('select record from requests where id=?',(body['request_id'],)).fetchone()[0])
                            rec['intent']['nonce']='a'*64
                            con.execute('update requests set record=? where id=?',(canonical(rec),body['request_id']))
                    with self.assertRaises(ResearchError):fn(body)
                    self.assertEqual(f.project.status(),before)

    def test_plan_preflight_rechecks_sql_after_validation(self):
        f,m,b=self.stage();body=self.plan_body(f,b);action=f.project.status()['actions'][0]
        original=ResearchProject.save_plan
        def mutate(project,**kwargs):
            result=original(project,**kwargs)
            if kwargs.get('_validate_only'):
                with sqlite3.connect(project.db) as con:con.execute('update actions set fingerprint=? where request_id=?',('a'*64,action['request_id']))
            return result
        before=m.db.read_bytes()
        with patch.object(ResearchProject,'save_plan',new=mutate):
            self.error('CONDITION_NOT_SATISFIED',m.save_quality_plan,body)
        self.assertEqual(m.db.read_bytes(),before)

    def test_v1_v2_manager_same_id_conflicts(self):
        for first in ('v1','v2'):
            with self.subTest(first=first):
                f,m,b=self.stage();plan=m.save_quality_plan(self.plan_body(f,b))['research_plan'];v2=self.policy_body(f,b,plan)
                v1={k:v for k,v in v2.items() if k not in ('plan_request_id','plan_sha256')}
                if first=='v1':m.advance_tabular_quality_feedback(v1);self.error('IDEMPOTENCY_CONFLICT',m.advance_tabular_quality_feedback_v2,v2)
                else:m.advance_tabular_quality_feedback_v2(v2);self.error('IDEMPOTENCY_CONFLICT',m.advance_tabular_quality_feedback,v1)

    def test_quality_and_experience_references_together(self):
        from test_plan_experience_refs import PlanExperienceReferenceTests
        cases=PlanExperienceReferenceTests(methodName='runTest');other_manager,other_project,_,refs,revision=cases.setup_case()
        self.addCleanup(cases.doCleanups)
        raw=(other_project.root/revision['bundle_ref']).read_bytes()
        f,m,b=self.stage()
        f.project.import_experience(request_id='synthetic-case',expected_state_version=f.project.status()['state_version'],
                                    bundle=raw,reason='Synthetic cross-project reference')
        body=self.plan_body(f,b);body['plan']['experience_case_refs']=refs
        result=m.save_quality_plan(body);before=f.project.status()
        self.assertEqual(result['research_plan']['experience_case_refs'],refs)
        self.assertEqual(LocalWorkbench(m.root).save_quality_plan(body)['research_plan'],result['research_plan'])
        self.assertEqual(f.project.status(),before)

    def test_manager_intent_transaction_rollback_preserves_core(self):
        for kind in ('plan','policy'):
            with self.subTest(kind=kind):
                f,m,b=self.stage();pb=self.plan_body(f,b)
                if kind=='policy':plan=m.save_quality_plan(pb)['research_plan'];body=self.policy_body(f,b,plan);fn=m.advance_tabular_quality_feedback_v2
                else:body=pb;fn=m.save_quality_plan
                before_project=f.project.status();before_manager=m.db.read_bytes();original=m._accept
                def interrupted(*args,**kwargs):
                    original(*args,**kwargs)
                    raise KeyboardInterrupt('before manager intent commit')
                with patch.object(m,'_accept',side_effect=interrupted),self.assertRaises(KeyboardInterrupt):fn(body)
                self.assertEqual(f.project.status(),before_project);self.assertEqual(m.db.read_bytes(),before_manager)

    def test_policy_rejection_and_later_plan_replay_keep_original(self):
        f,m,b=self.stage();plan=m.save_quality_plan(self.plan_body(f,b))['research_plan'];body=self.policy_body(f,b,plan)
        with patch.object(ResearchProject,'step',side_effect=ResearchError('SYNTHETIC_REJECTED','Synthetic failure')):
            self.error('SYNTHETIC_REJECTED',m.advance_tabular_quality_feedback_v2,body)
        before=f.project.status()
        with patch.object(ProjectController,'_dispatch',side_effect=AssertionError('redispatch')):
            self.error('SYNTHETIC_REJECTED',m.advance_tabular_quality_feedback_v2,body)
        self.assertEqual(f.project.status(),before)
        f,m,b=self.stage();plan=m.save_quality_plan(self.plan_body(f,b))['research_plan'];body=self.policy_body(f,b,plan)
        result=m.advance_tabular_quality_feedback_v2(body);state=f.project.status()
        later={'question':'Later','basis':'Synthetic','steps':'Wait','expected_feedback':'None'}
        f.project.save_plan(request_id='later',expected_state_version=state['state_version'],plan=later,reason='Synthetic')
        before=f.project.status()
        with patch.object(ProjectController,'_dispatch',side_effect=AssertionError('redispatch')):
            replay=LocalWorkbench(m.root).advance_tabular_quality_feedback_v2(body)
        self.assertEqual(replay['result'],result['result']);self.assertEqual(f.project.status(),before)

    def test_ref_get_checks_active_snapshot_and_runtime_drift(self):
        from pathlib import Path
        import autoresearch.project_workbench as server_module
        f,m,b=self.stage();server=self.serve(local_workspace=m,allow_local_actions=True)
        state=f.project.status();query='?project_id='+b['project_id']+'&snapshot_ref='+state['snapshot_ref']+'&registration_request_id=reg'
        path='/api/local-workbench/tabular-quality-plan-ref.json'; before=(m.db.read_bytes(),f.project.db.read_bytes())
        self.assertEqual(self.request(server,path+query)[0],200)
        self.assertNotEqual(self.request(server,path+query.replace(state['snapshot_ref'],'a'*64))[0],200)
        self.assertNotEqual(self.request(server,path+query.replace(b['project_id'],'different'))[0],200)
        self.assertEqual(before,(m.db.read_bytes(),f.project.db.read_bytes()))
        read=Path.read_bytes;target=Path(server_module.__file__).resolve()
        def drift(p):
            raw=read(p);return raw+b'\n# synthetic runtime change' if p.resolve()==target else raw
        with patch.object(Path,'read_bytes',drift):self.assertNotEqual(self.request(server,path+query)[0],200)


if __name__=='__main__':unittest.main()
