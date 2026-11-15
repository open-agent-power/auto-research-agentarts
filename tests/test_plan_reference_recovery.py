"""Synthetic persisted plan intent recovery; no research model or fit."""
import copy
import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

import test_conditional_staged_continuation as waiting_fixture
import test_local_workbench_http as http_fixture
import test_plan_experience_refs as plan_fixture
from autoresearch.contracts import ResearchError, canonical, fingerprint
from autoresearch.local_workbench import LocalWorkbench
from autoresearch.research_project import ResearchProject


class PlanReferenceRecoveryTests(unittest.TestCase):
    fixture = waiting_fixture.ConditionalStagedContinuationTests.fixture
    setup_case = plan_fixture.PlanExperienceReferenceTests.setup_case
    body = staticmethod(plan_fixture.PlanExperienceReferenceTests.body)
    serve = http_fixture.LocalWorkbenchHTTPTests.serve
    request = http_fixture.LocalWorkbenchHTTPTests.request
    session = http_fixture.LocalWorkbenchHTTPTests.session

    def start(self):
        manager,project,plan,refs,_=self.setup_case();plan['experience_case_refs']=refs
        return manager,project,self.body(project,plan)

    @staticmethod
    def interrupt_before_project(manager, body):
        original=ResearchProject.save_plan
        def stop(target, **kwargs):
            if kwargs.get('_validate_only'):return original(target,**kwargs)
            raise KeyboardInterrupt('Synthetic disconnect after durable manager intent')
        with patch.object(ResearchProject,'save_plan',stop):
            try:manager.save_plan(body)
            except KeyboardInterrupt:return
        raise AssertionError('intent interruption not simulated')

    @staticmethod
    def interrupt_after_project(manager, body):
        original=LocalWorkbench._save
        def stop(con, request_id, record):
            if request_id==body['request_id'] and record.get('status')=='completed':
                raise KeyboardInterrupt('Synthetic disconnect after original Project commit')
            return original(con,request_id,record)
        with patch.object(LocalWorkbench,'_save',staticmethod(stop)):
            try:manager.save_plan(body)
            except KeyboardInterrupt:return
        raise AssertionError('receipt interruption not simulated')

    def test_precommit_durable_intent_http_restart_and_original_body_recovery(self):
        manager,project,body=self.start();before=project.status();self.interrupt_before_project(manager,body)
        with manager._connect(readonly=True) as con:
            row=con.execute('SELECT digest,record FROM requests WHERE id=?',(body['request_id'],)).fetchone()
            record=json.loads(row['record'])
        self.assertEqual(row['digest'],fingerprint(body));self.assertEqual(record['intent']['body'],body)
        pending=manager.describe()['pending_requests'];self.assertEqual(len(pending),1)
        self.assertEqual(pending[0]['recovery'],'original_body_available')
        self.assertNotIn(body['plan']['experience_case_refs']['items'][0]['applicability_statement'],canonical(pending))
        self.assertEqual(project.status(),before)
        with self.assertRaises(ResearchError) as error:manager.save_plan({**body,'request_id':'new-id'})
        self.assertEqual(error.exception.code,'OPERATION_INCOMPLETE')
        child='''import json,sys\nfrom autoresearch.local_workbench import LocalWorkbench\nm=LocalWorkbench(sys.argv[1]);print(json.dumps(m.resume_plan(json.loads(sys.stdin.read())),sort_keys=True))'''
        outcome=subprocess.run([sys.executable,'-B','-c',child,str(manager.root)],input=canonical({'request_id':body['request_id'],'project_id':body['project_id']}),
                               text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=30)
        self.assertEqual(outcome.returncode,0,outcome.stderr);saved=json.loads(outcome.stdout)
        self.assertTrue(saved['replayed']);self.assertEqual(saved['plan_revision']['request_id'],body['request_id'])
        self.assertNotIn(body['plan']['experience_case_refs']['items'][0]['applicability_statement'],canonical(saved))
        after=project.status();self.assertEqual(after['state_version'],before['state_version']+1)
        self.assertEqual(after['actions'],before['actions']);self.assertEqual(after['budget'],before['budget'])
        server=self.serve(local_workspace=manager,allow_local_actions=True);headers=self.session(server)
        status,replay=self.request(server,'/api/local-workbench/plan-resume','POST',
                                   {'request_id':body['request_id'],'project_id':body['project_id']},headers)
        self.assertEqual(status,200,replay);self.assertTrue(replay['replayed']);self.assertEqual(project.status(),after)
        self.assertNotIn(body['plan']['experience_case_refs']['items'][0]['applicability_statement'],canonical(replay))
        self.assertEqual(manager.describe()['pending_requests'],[])

    def test_postcommit_reconciles_original_revision_even_after_retirement(self):
        manager,project,body=self.start();self.interrupt_after_project(manager,body)
        saved=project.status();revision=saved['plan_revisions'][-1];self.assertEqual(revision['request_id'],body['request_id'])
        project.set_experience_status(request_id='later-retire',expected_state_version=saved['state_version'],
                case_id='waiting-case',status='retired',reason='Synthetic subsequent decision.')
        source=project.root/'source.json';source_raw=source.read_bytes();source.write_bytes(source_raw+b' ')
        damaged=project.status();manager_bytes=manager.db.read_bytes()
        with self.assertRaises(ResearchError) as error:manager.resume_plan({'request_id':body['request_id'],'project_id':body['project_id']})
        self.assertEqual(error.exception.code,'EVIDENCE_CHANGED');self.assertEqual(project.status(),damaged)
        self.assertEqual(manager.db.read_bytes(),manager_bytes)
        source.write_bytes(source_raw)
        after=project.status();original=manager.resume_plan({'request_id':body['request_id'],'project_id':body['project_id']})
        self.assertTrue(original['replayed']);self.assertEqual(original['plan_revision']['request_id'],revision['request_id'])
        self.assertNotIn(body['plan']['experience_case_refs']['items'][0]['applicability_statement'],canonical(original))
        self.assertEqual(project.status(),after);self.assertEqual(after['actions'],saved['actions']);self.assertEqual(after['budget'],saved['budget'])

    def test_active_project_pending_is_not_crowded_out_by_other_projects(self):
        manager,project,body=self.start();self.interrupt_before_project(manager,body)
        with manager._connect() as con:
            for index in range(12):
                con.execute('INSERT INTO requests VALUES(?,?,?,?)',('other-'+str(index),'a'*64,'save_plan',
                            canonical({'status':'preparing','intent':{'project_id':'other-project-'+str(index)},'result':None})))
        pending=manager.describe()['pending_requests']
        self.assertLessEqual(len(pending),8);self.assertEqual(pending[0]['request_id'],body['request_id'])
        self.assertEqual(pending[0]['recovery'],'original_body_available')
        self.assertNotIn(body['plan']['experience_case_refs']['items'][0]['applicability_statement'],canonical(pending))
        self.assertEqual(manager.resume_plan({'request_id':body['request_id'],'project_id':body['project_id']})['status'],'completed')

    def test_many_legacy_pending_are_counted_and_remain_blocking(self):
        manager,project,body=self.start();self.interrupt_before_project(manager,body);before=project.status()
        with manager._connect() as con:
            for index in range(10):
                con.execute('INSERT INTO requests VALUES(?,?,?,?)',('old-'+str(index),'a'*64,'save_plan',
                            canonical({'status':'preparing','intent':{'project_id':body['project_id']},'result':None})))
        description=manager.describe();summary=description['pending_plan_summary']
        self.assertEqual(summary,{'project_id':body['project_id'],'total':11,'shown':8,'truncated':True})
        self.assertEqual(len(description['pending_requests']),8)
        with self.assertRaises(ResearchError) as error:manager.resume_plan({'request_id':body['request_id'],'project_id':body['project_id']})
        self.assertEqual(error.exception.code,'OPERATION_INCOMPLETE');self.assertEqual(project.status(),before)

    def test_completed_receipt_shape_and_project_binding_are_checked_before_sanitizing(self):
        for mutation in ('project_id','extra','schema','replayed'):
            with self.subTest(mutation=mutation):
                manager,project,body=self.start();manager.save_plan(body);state=project.status()
                with manager._connect() as con:
                    record=json.loads(con.execute('SELECT record FROM requests WHERE id=?',(body['request_id'],)).fetchone()['record'])
                    if mutation=='project_id':record['result']['project_id']='other-project'
                    if mutation=='extra':record['result']['extra']='unexpected'
                    if mutation=='schema':record['result']['schema_version']='incorrect'
                    if mutation=='replayed':record['result']['replayed']=0
                    manager._save(con,body['request_id'],record)
                db=manager.db.read_bytes()
                with self.assertRaises(ResearchError) as error:manager.resume_plan({'request_id':body['request_id'],'project_id':body['project_id']})
                self.assertEqual(error.exception.code,'OPERATION_INCOMPLETE')
                self.assertEqual(project.status(),state);self.assertEqual(manager.db.read_bytes(),db)

    def test_stale_snapshot_code_drift_and_tampered_intent_preserve_original(self):
        for mutation in ('state','manager-source','source-file','body','status'):
            with self.subTest(mutation=mutation):
                manager,project,body=self.start();self.interrupt_before_project(manager,body)
                if mutation=='state':
                    before=project.status()
                    project.set_experience_status(request_id='direct-retire',expected_state_version=before['state_version'],
                        case_id='waiting-case',status='retired',reason='Synthetic changed state.')
                if mutation=='body':
                    with manager._connect() as con:
                        record=json.loads(con.execute('SELECT record FROM requests WHERE id=?',(body['request_id'],)).fetchone()['record'])
                        record['intent']['body']['reason']='altered original'
                        manager._save(con,body['request_id'],record)
                if mutation=='status':
                    with manager._connect() as con:
                        record=json.loads(con.execute('SELECT record FROM requests WHERE id=?',(body['request_id'],)).fetchone()['record'])
                        record['status']='failed'
                        manager._save(con,body['request_id'],record)
                if mutation=='source-file':
                    source=project.root/'source.json';source.write_bytes(source.read_bytes()+b' ')
                state=project.status();db=manager.db.read_bytes()
                kwargs={'request_id':body['request_id'],'project_id':body['project_id']}
                if mutation=='manager-source':
                    with patch('autoresearch.local_workbench.batch_code_identity',return_value='0'*64), self.assertRaises(ResearchError) as error:
                        manager.resume_plan(kwargs)
                    self.assertEqual(error.exception.code,'CODE_CHANGED')
                else:
                    with self.assertRaises(ResearchError) as error:manager.resume_plan(kwargs)
                    expected={'state':'STALE_STATE','source-file':'EVIDENCE_CHANGED','body':'OPERATION_INCOMPLETE','status':'OPERATION_INCOMPLETE'}
                    self.assertEqual(error.exception.code,expected[mutation])
                self.assertEqual(project.status(),state);self.assertEqual(manager.db.read_bytes(),db)

    def test_legacy_pending_body_is_unavailable_and_cannot_be_bypassed(self):
        manager,project,body=self.start();state=project.status()
        with manager._connect() as con:
            con.execute('INSERT INTO requests VALUES(?,?,?,?)',('legacy-plan','a'*64,'save_plan',
                        canonical({'status':'preparing','intent':{'project_id':state['id']},'result':None})))
        pending=manager.describe()['pending_requests'];self.assertEqual(pending[0]['recovery'],'original_body_unavailable')
        with self.assertRaises(ResearchError) as error:manager.resume_plan({'request_id':'legacy-plan','project_id':state['id']})
        self.assertEqual(error.exception.code,'OPERATION_INCOMPLETE')
        with self.assertRaises(ResearchError) as error:manager.save_plan(body)
        self.assertEqual(error.exception.code,'OPERATION_INCOMPLETE');self.assertEqual(project.status(),state)

    def test_unexpected_rejected_legacy_plan_remains_visible_and_blocking(self):
        manager,project,body=self.start();state=project.status()
        with manager._connect() as con:
            con.execute('INSERT INTO requests VALUES(?,?,?,?)',('legacy-rejected','a'*64,'save_plan',
                        canonical({'status':'rejected','intent':{'project_id':state['id']},'result':None})))
        pending=manager.describe()['pending_requests'];self.assertEqual(pending[0]['request_id'],'legacy-rejected')
        self.assertEqual(pending[0]['status'],'rejected');self.assertEqual(pending[0]['recovery'],'original_body_unavailable')
        with self.assertRaises(ResearchError) as error:manager.save_plan(body)
        self.assertEqual(error.exception.code,'OPERATION_INCOMPLETE');self.assertEqual(project.status(),state)


if __name__=='__main__':unittest.main()
