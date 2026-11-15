"""Isolated synthetic manager/HTTP quality integration; no external research."""
import copy
import json
import sqlite3
import subprocess
import sys
import unittest
from unittest.mock import patch

import test_local_workbench_http as http
import test_tabular_quality_feedback as fixture
from autoresearch import tabular_quality_feedback as quality_feedback
from autoresearch.contracts import ResearchError, canonical, fingerprint
from autoresearch.local_workbench import LocalWorkbench
from autoresearch.project_controller import ProjectController
from autoresearch.research_project import ResearchProject


class QualityWorkbenchTests(unittest.TestCase):
    serve = http.LocalWorkbenchHTTPTests.serve
    request = http.LocalWorkbenchHTTPTests.request
    session = http.LocalWorkbenchHTTPTests.session

    def stage(self):
        f = fixture.QualityFeedbackTests(methodName='runTest')
        f.setUp(); self.addCleanup(f.doCleanups)
        manager = LocalWorkbench(f.root/'manager')
        project_id = f.project.status()['id']
        manager.import_project(request_id='import', workspace=f.project.root)
        manager.select({'request_id':'select', 'project_id':project_id})
        f.project, _ = manager.binding(); f.controller = ProjectController(f.project.root)
        body = {'request_id':'reg', 'project_id':project_id, 'controller_request_id':'quality',
                'expected_state_version':f.project.status()['state_version'], 'candidate_id':f.candidate['id'],
                'conditions':f.valid}
        return f, manager, body

    def advance_body(self, f, body):
        return {'request_id':'branch', 'project_id':body['project_id'], 'registration_request_id':'reg',
                'expected_state_version':f.project.status()['state_version']}

    def assert_error(self, code, fn, *args):
        with self.assertRaises(ResearchError) as err: fn(*args)
        self.assertEqual(err.exception.code, code)

    def test_http_full_flow_security_and_readonly(self):
        f,m,b=self.stage(); server=self.serve(local_workspace=m,allow_local_actions=True); headers=self.session(server)
        route='/api/local-workbench/tabular-quality-registration'
        for altered in ({**headers,'Origin':'http://evil.invalid'}, {**headers,'X-AutoResearch-CSRF':'wrong'},
                        {**headers,'Host':'evil.invalid'}, {**headers,'Sec-Fetch-Site':'cross-site'}):
            self.assertEqual(self.request(server,route,'POST',b,altered)[0],403)
        status,registered=self.request(server,route,'POST',b,headers); self.assertEqual(status,200,registered)
        state=f.project.status(); query='?project_id='+b['project_id']+'&snapshot_ref='+state['snapshot_ref']+'&registration_request_id=reg'
        status,result=self.request(server,'/api/local-workbench/tabular-quality-feedback.json'+query)
        self.assertEqual((status,result['outcome']),(200,'unknown'))
        self.assertEqual(self.request(server,'/api/local-workbench/tabular-quality-feedback.json'+query+'&project_id=x')[0],400)
        f.execute(); state=f.project.status(); query='?project_id='+b['project_id']+'&snapshot_ref='+state['snapshot_ref']+'&registration_request_id=reg'
        before=f.project.db.read_bytes(); status,result=self.request(server,'/api/local-workbench/tabular-quality-feedback.json'+query)
        self.assertEqual((status,result['outcome']),(200,'condition_met')); self.assertEqual(before,f.project.db.read_bytes())
        advance=self.advance_body(f,b)
        status,result=self.request(server,'/api/local-workbench/advance-tabular-quality-feedback','POST',advance,headers)
        self.assertEqual(status,200,result); self.assertEqual(result['status'],'completed')
        after=f.project.status(); self.assertEqual(after['budget']['local_tool_calls_used'],2)
        self.assertEqual((after['budget']['new_model_requests'],after['budget']['new_fits'],after['budget']['evidence_reads_used']),(0,0,0))
        with patch.object(ProjectController,'_dispatch',side_effect=AssertionError('re-dispatch')):
            replay=LocalWorkbench(m.root).advance_tabular_quality_feedback(advance)
        self.assertEqual(replay['child_request_id'],result['child_request_id']); self.assertEqual(f.project.status(),after)
        readonly=self.serve(local_workspace=LocalWorkbench.open_readonly(m.root),allow_local_actions=False)
        self.assertEqual(self.request(readonly,'/api/local-workbench/tabular-quality-feedback.json'+query)[0],404)

    def test_lost_registration_receipt_and_missing_core_stop(self):
        f,m,b=self.stage(); original=m._save
        def lose(con,request_id,record):
            if record.get('status') == 'completed': raise KeyboardInterrupt('lost receipt')
            return original(con,request_id,record)
        with patch.object(m,'_save',side_effect=lose), self.assertRaises(KeyboardInterrupt):m.register_tabular_quality_conditions(b)
        before=f.project.status()
        with patch.object(quality_feedback,'_register_with_created',side_effect=AssertionError('retry')):
            result=LocalWorkbench(m.root).register_tabular_quality_conditions(b)
        self.assertEqual(result['status'],'completed'); self.assertEqual(f.project.status(),before)
        f,m,b=self.stage()
        with patch.object(quality_feedback,'_register_with_created',side_effect=KeyboardInterrupt), self.assertRaises(KeyboardInterrupt):
            m.register_tabular_quality_conditions(b)
        with patch.object(quality_feedback,'_register_with_created',side_effect=AssertionError('retry')):
            self.assert_error('OPERATION_INCOMPLETE',m.register_tabular_quality_conditions,b)
        self.assertEqual(f.project.status().get('tabular_quality_registrations',[]),[])

    def test_missing_or_nonterminal_parent_never_redispatches(self):
        for phase in ('before-parent','after-parent'):
            with self.subTest(phase=phase):
                f,m,b=self.stage();m.register_tabular_quality_conditions(b);f.execute();advance=self.advance_body(f,b)
                target='advance_tabular_quality_feedback' if phase=='before-parent' else '_dispatch'
                with patch.object(ProjectController,target,side_effect=KeyboardInterrupt), self.assertRaises(KeyboardInterrupt):
                    m.advance_tabular_quality_feedback(advance)
                before=f.project.status()
                with patch.object(ProjectController,'advance_tabular_quality_feedback',side_effect=AssertionError('retry')):
                    self.assert_error('OPERATION_INCOMPLETE' if phase=='before-parent' else 'EXECUTION_UNKNOWN',
                                      LocalWorkbench(m.root).advance_tabular_quality_feedback,advance)
                self.assertEqual(f.project.status(),before)
                self.assert_error('OPERATION_INCOMPLETE',m.advance_tabular_quality_feedback,{**advance,'request_id':'another'})

    def test_lost_terminal_receipt_reconciles_without_dispatch(self):
        f,m,b=self.stage();m.register_tabular_quality_conditions(b);f.execute();advance=self.advance_body(f,b)
        original=m._save
        def lose(con,request_id,record):
            if record.get('status')=='completed':raise KeyboardInterrupt('lost receipt')
            return original(con,request_id,record)
        with patch.object(m,'_save',side_effect=lose), self.assertRaises(KeyboardInterrupt):m.advance_tabular_quality_feedback(advance)
        before=f.project.status()
        with patch.object(ProjectController,'_dispatch',side_effect=AssertionError('re-dispatch')):
            self.assertEqual(LocalWorkbench(m.root).advance_tabular_quality_feedback(advance)['status'],'completed')
        self.assertEqual(f.project.status(),before)

    def test_preflight_rejects_invalid_and_existing_core_without_manager_intent(self):
        f,m,b=self.stage()
        self.assert_error('INVALID_REQUEST',m.register_tabular_quality_conditions,{**b,'controller_request_id':'reg'})
        self.assertEqual(m.describe()['pending_requests'],[])
        f.project.register_tabular_quality_conditions(**{k:v for k,v in b.items() if k!='project_id'})
        self.assert_error('IDEMPOTENCY_CONFLICT',m.register_tabular_quality_conditions,
                          {**b,'expected_state_version':f.project.status()['state_version']})
        self.assertEqual(m.describe()['pending_requests'],[])

    def test_core_parent_without_manager_intent_cannot_be_adopted(self):
        f,m,b=self.stage(); m.register_tabular_quality_conditions(b); f.execute()
        body=self.advance_body(f,b)
        f.controller.advance_tabular_quality_feedback(request_id=body['request_id'],
            registration_request_id=body['registration_request_id'],expected_state_version=body['expected_state_version'])
        before=f.project.status()
        with patch.object(ProjectController,'advance_tabular_quality_feedback',side_effect=AssertionError('must not replay')):
            self.assert_error('IDEMPOTENCY_CONFLICT',m.advance_tabular_quality_feedback,
                              {**body,'expected_state_version':before['state_version']})
        self.assertEqual(f.project.status(),before)
        self.assertEqual(m.describe()['pending_requests'],[])

    def test_unknown_wait_and_original_intent_tampering(self):
        f,m,b=self.stage();m.register_tabular_quality_conditions(b); body=self.advance_body(f,b)
        result=m.advance_tabular_quality_feedback(body)
        self.assertEqual(result['status'],'waiting'); before=f.project.status()
        with patch.object(ProjectController,'_dispatch',side_effect=AssertionError('must not dispatch')):
            self.assertEqual(LocalWorkbench(m.root).advance_tabular_quality_feedback(body)['status'],'waiting')
        self.assertEqual(f.project.status(),before)
        with sqlite3.connect(m.db) as con:
            record=json.loads(con.execute('select record from requests where id=?',('branch',)).fetchone()[0])
            record['intent']['body']['registration_request_id']='other'
            con.execute('update requests set record=? where id=?',(canonical(record),'branch'))
        self.assert_error('EVIDENCE_CHANGED',m.advance_tabular_quality_feedback,body)
        self.assertEqual(f.project.status(),before)

    def test_pending_scans_beyond_display_limit(self):
        f,m,b=self.stage()
        with patch.object(quality_feedback,'_register_with_created',side_effect=KeyboardInterrupt), self.assertRaises(KeyboardInterrupt):
            m.register_tabular_quality_conditions(b)
        with m._connect() as con:
            for i in range(10):
                con.execute('insert into requests values (?,?,?,?)',
                    (f'newer-{i}','a'*64,'register_tabular_quality_conditions',
                     canonical({'status':'completed','intent':{'project_id':b['project_id']},'result':{}})))
        self.assert_error('OPERATION_INCOMPLETE',m.advance_tabular_quality_feedback,self.advance_body(f,b))

    def test_registration_raced_by_direct_core_never_adopted(self):
        for different in (False, True):
            with self.subTest(different=different):
                f,m,b=self.stage(); register=quality_feedback._register_with_created
                def raced(project, **kwargs):
                    direct={k:v for k,v in kwargs.items() if k!='_manager_intent_sha256'}
                    if different:
                        direct['conditions']=fixture.rules(fixture.condition('rows','eq',5))
                    register(project, **direct)
                    return register(project, **kwargs)
                with patch.object(quality_feedback,'_register_with_created',side_effect=raced):
                    self.assert_error('IDEMPOTENCY_CONFLICT' if different else 'OPERATION_INCOMPLETE',m.register_tabular_quality_conditions,b)
                before=f.project.status()
                with patch.object(quality_feedback,'_register_with_created',side_effect=AssertionError('redispatch')):
                    self.assert_error('EVIDENCE_CHANGED' if different else 'OPERATION_INCOMPLETE',m.register_tabular_quality_conditions,b)
                self.assertEqual(f.project.status(),before)

    def test_policy_raced_by_direct_core_never_adopted(self):
        f,m,b=self.stage();m.register_tabular_quality_conditions(b);f.execute(); body=self.advance_body(f,b)
        original=ProjectController.advance_tabular_quality_feedback
        def raced(controller, **kwargs):
            direct={k:v for k,v in kwargs.items() if k!='_manager_intent_sha256'}
            original(controller, **direct)
            return original(controller, **kwargs)
        with patch.object(ProjectController,'advance_tabular_quality_feedback',new=raced):
            self.assert_error('OPERATION_INCOMPLETE',m.advance_tabular_quality_feedback,body)
        before=f.project.status()
        with patch.object(ProjectController,'advance_tabular_quality_feedback',side_effect=AssertionError('redispatch')):
            self.assert_error('OPERATION_INCOMPLETE',m.advance_tabular_quality_feedback,body)
        self.assertEqual(f.project.status(),before)

    def test_claim_and_core_rollback_together(self):
        for kind in ('registration','policy'):
            with self.subTest(kind=kind):
                f,m,b=self.stage()
                if kind=='policy':m.register_tabular_quality_conditions(b);f.execute()
                before=f.project.status();original=quality_feedback._manager_claim
                def fail_after_insert(con, target, request, intent, core, **kwargs):
                    result=original(con,target,request,intent,core,**kwargs)
                    if target==kind and kwargs.get('create'):raise KeyboardInterrupt('before transaction commit')
                    return result
                with patch.object(quality_feedback,'_manager_claim',side_effect=fail_after_insert), self.assertRaises(KeyboardInterrupt):
                    (m.register_tabular_quality_conditions(b) if kind=='registration'
                     else m.advance_tabular_quality_feedback(self.advance_body(f,b)))
                self.assertEqual(f.project.status(),before)
                with f.project._connect(readonly=True) as con:
                    exists=con.execute("select 1 from sqlite_master where type='table' and name='quality_manager_claims'").fetchone()
                    if exists:self.assertIsNone(con.execute('select 1 from quality_manager_claims where kind=?',(kind,)).fetchone())

    def test_claim_missing_or_changed_blocks_recovery(self):
        for kind in ('registration','policy'):
            for mutation in ('delete','change'):
                with self.subTest(kind=kind,mutation=mutation):
                    f,m,b=self.stage()
                    if kind=='policy':m.register_tabular_quality_conditions(b);f.execute();body=self.advance_body(f,b)
                    original=m._save
                    def lose(con,request_id,record):
                        if record.get('status')=='completed':raise KeyboardInterrupt('lost receipt')
                        return original(con,request_id,record)
                    with patch.object(m,'_save',side_effect=lose), self.assertRaises(KeyboardInterrupt):
                        (m.register_tabular_quality_conditions(b) if kind=='registration' else m.advance_tabular_quality_feedback(body))
                    with sqlite3.connect(f.project.db) as con:
                        if mutation=='delete':con.execute('delete from quality_manager_claims where kind=?',(kind,))
                        else:con.execute('update quality_manager_claims set intent_sha256=? where kind=?',('a'*64,kind))
                    before=f.project.status()
                    with patch.object(ProjectController,'_dispatch',side_effect=AssertionError('redispatch')):
                        self.assert_error('OPERATION_INCOMPLETE',m.register_tabular_quality_conditions if kind=='registration'
                                          else m.advance_tabular_quality_feedback,b if kind=='registration' else body)
                    self.assertEqual(f.project.status(),before)

    def test_cross_process_core_writer_excluded_until_intent_commit(self):
        code = '''import json,sys
from autoresearch.contracts import ResearchError
from autoresearch.research_project import ResearchProject
from autoresearch.project_controller import ProjectController
p=ResearchProject(sys.argv[1]); k=sys.argv[2]; b=json.loads(sys.argv[3])
try:
    if k=="registration": p.register_tabular_quality_conditions(**b)
    else: ProjectController(p.root).advance_tabular_quality_feedback(**b)
except ResearchError as e: print(e.code)
else: print("ACCEPTED")
'''
        for kind in ('registration','policy'):
            with self.subTest(kind=kind):
                f,m,b=self.stage()
                if kind=='policy':m.register_tabular_quality_conditions(b);f.execute();body=self.advance_body(f,b)
                else:body=b
                original=m._accept; seen=[]
                def competing(con, accepted_body, digest, command, intent):
                    request={k:v for k,v in accepted_body.items() if k!='project_id'}
                    child=subprocess.run([sys.executable,'-B','-c',code,str(f.project.root),kind,json.dumps(request)],
                                         check=True,capture_output=True,text=True,timeout=15)
                    seen.append(child.stdout.strip())
                    return original(con,accepted_body,digest,command,intent)
                with patch.object(m,'_accept',side_effect=competing):
                    result=(m.register_tabular_quality_conditions(body) if kind=='registration'
                            else m.advance_tabular_quality_feedback(body))
                self.assertEqual(seen,['PROJECT_BUSY']);self.assertEqual(result['status'],'completed')

    def test_intent_nonce_and_manager_root_bind_original_owner(self):
        f,m,b=self.stage(); state=f.project.status(); digest=fingerprint(b); command='register_tabular_quality_conditions'
        first=m._quality_intent(b,digest,command,state); second=m._quality_intent(b,digest,command,state)
        self.assertNotEqual(first['nonce'],second['nonce']);self.assertNotEqual(first['intent_sha256'],second['intent_sha256'])
        other=LocalWorkbench(f.root/'other-manager')
        self.assert_error('EVIDENCE_CHANGED',other._check_quality_intent,first,b,digest,command,state)
        tampered=dict(first,nonce='a'*64)
        self.assert_error('EVIDENCE_CHANGED',m._check_quality_intent,tampered,b,digest,command,state)


if __name__=='__main__':unittest.main()
