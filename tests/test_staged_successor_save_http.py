"""Synthetic S121/S124 HTTP wiring and full manager pending scan."""
import copy
import hashlib
import json
from pathlib import Path
import unittest
from unittest.mock import patch
from urllib.parse import urlencode
from autoresearch.contracts import ResearchError,canonical,fingerprint
import test_local_workbench_http as http
from staged_successor_http_fixture import request as successor_request
import test_staged_feedback_successor_plan as fixtures


class StagedSuccessorSaveHTTPTests(unittest.TestCase):
    serve=http.LocalWorkbenchHTTPTests.serve
    request=successor_request
    session=http.LocalWorkbenchHTTPTests.session

    def fixture(self):
        manager,project,_,_,body=fixtures.StagedFeedbackSuccessorPlanTests.fixture(self,'wait')
        server=self.serve(local_workspace=manager,allow_local_actions=True)
        return manager,project,body,server,self.session(server)

    def scan(self,server,project):
        state=project.status();query=urlencode({'project_id':state['id'],'snapshot_ref':state['snapshot_ref']})
        return self.request(server,'/api/local-workbench/staged-feedback-plan-pending.json?'+query)

    def test_full_scan_and_save_resume_are_bounded_and_redacted(self):
        manager,project,body,server,headers=self.fixture();before=project.status()
        status,scan=self.scan(server,project);self.assertEqual(status,200)
        self.assertEqual((scan['status'],scan['total'],scan['shown'],scan['truncated']),('available',0,0,False))
        body['plan']['question']='SYNTHETIC_PRIVATE_SENTINEL';body['reason']='SYNTHETIC_PRIVATE_REASON'
        status,saved=self.request(server,'/api/local-workbench/staged-feedback-plan','POST',body,headers)
        self.assertEqual(status,200);self.assertEqual(saved['schema_version'],'staged-successor-plan-receipt-v1')
        self.assertNotIn('SYNTHETIC_PRIVATE',json.dumps(saved));self.assertFalse(saved['replayed'])
        state=project.status();self.assertEqual(state['budget'],before['budget'])
        status,scan=self.scan(server,project);self.assertEqual((status,scan['status'],scan['total']),(200,'available',0))
        self.assertNotIn('SYNTHETIC_PRIVATE',json.dumps(scan))
        project_hash=hashlib.sha256(project.db.read_bytes()).hexdigest()
        status,replayed=self.request(server,'/api/local-workbench/staged-feedback-plan-resume','POST',body,headers)
        self.assertEqual(status,200);self.assertTrue(replayed['replayed']);self.assertEqual(saved['plan_sha256'],replayed['plan_sha256'])
        self.assertEqual(project_hash,hashlib.sha256(project.db.read_bytes()).hexdigest())

    def test_resume_missing_row_and_changed_body_never_create(self):
        manager,project,body,server,headers=self.fixture();before=project.status()
        hashes=[hashlib.sha256(p.read_bytes()).hexdigest() for p in (manager.db,project.db)]
        status,_=self.request(server,'/api/local-workbench/staged-feedback-plan-resume','POST',body,headers)
        self.assertNotEqual(status,200);self.assertEqual(hashes,[hashlib.sha256(p.read_bytes()).hexdigest() for p in (manager.db,project.db)])
        self.assertEqual(project.status(),before)
        self.assertEqual(self.request(server,'/api/local-workbench/staged-feedback-plan','POST',body,headers)[0],200)
        changed=copy.deepcopy(body);changed['plan']['steps']='different synthetic body'
        self.assertNotEqual(self.request(server,'/api/local-workbench/staged-feedback-plan-resume','POST',changed,headers)[0],200)

    def test_preparing_and_committed_revision_recovery_windows(self):
        for mode in ('intent_only','project_committed'):
            with self.subTest(mode=mode):
                manager,project,body,server,headers=self.fixture()
                if mode=='intent_only':
                    actual=manager._staged_plan_reference_locked;calls=[]
                    def interrupt(*args):
                        value=actual(*args);calls.append(1)
                        if len(calls)==2:raise ResearchError('SYNTHETIC_INTERRUPT','after original intent')
                        return value
                    context=patch.object(manager,'_staged_plan_reference_locked',side_effect=interrupt)
                else:context=patch.object(manager,'_save',side_effect=ResearchError('SYNTHETIC_INTERRUPT','after project commit'))
                with context:self.assertNotEqual(self.request(server,'/api/local-workbench/staged-feedback-plan','POST',body,headers)[0],200)
                state=project.status();status,scan=self.scan(server,project)
                self.assertEqual((status,scan['status'],scan['total']),(200,'available',1))
                self.assertEqual(scan['items'],[{'request_id':body['request_id'],'status':'preparing'}])
                before=[hashlib.sha256(p.read_bytes()).hexdigest() for p in (manager.db,project.db)]
                status,_=self.request(server,'/api/local-workbench/staged-feedback-plan-resume','POST',body,headers)
                if mode=='intent_only':
                    self.assertNotEqual(status,200);self.assertEqual(before,[hashlib.sha256(p.read_bytes()).hexdigest() for p in (manager.db,project.db)])
                else:
                    self.assertEqual(status,200);self.assertEqual(before[1],hashlib.sha256(project.db.read_bytes()).hexdigest())
                self.assertEqual(project.status(),state)

    def test_malformed_unassignable_row_and_completed_record_return_unknown(self):
        manager,project,body,server,headers=self.fixture()
        with manager._connect() as con:con.execute('INSERT INTO requests VALUES(?,?,?,?)',('bad','0'*64,'save_staged_feedback_plan',canonical({'status':'preparing','intent':{},'result':None})))
        status,scan=self.scan(server,project);self.assertEqual((status,scan['status'],scan['total']),(200,'unknown',None));self.assertEqual(scan['items'],[])
        with manager._connect() as con:con.execute('DELETE FROM requests WHERE id=?',('bad',))
        self.assertEqual(self.request(server,'/api/local-workbench/staged-feedback-plan','POST',body,headers)[0],200)
        with manager._connect() as con:
            row=con.execute('SELECT record FROM requests WHERE id=?',(body['request_id'],)).fetchone();record=json.loads(row['record']);del record['result']['research_plan']
            con.execute('UPDATE requests SET record=? WHERE id=?',(canonical(record),body['request_id']))
        status,scan=self.scan(server,project);self.assertEqual((status,scan['status'],scan['total']),(200,'unknown',None))

    def test_nine_well_formed_pending_are_counted_and_truncated(self):
        manager,project,body,server,headers=self.fixture();actual=manager._staged_plan_reference_locked;calls=[]
        def interrupt(*args):
            value=actual(*args);calls.append(1)
            if len(calls)==2:raise ResearchError('SYNTHETIC_INTERRUPT','preserve intent')
            return value
        with patch.object(manager,'_staged_plan_reference_locked',side_effect=interrupt):
            self.assertNotEqual(self.request(server,'/api/local-workbench/staged-feedback-plan','POST',body,headers)[0],200)
        with manager._connect() as con:
            row=con.execute('SELECT record FROM requests WHERE id=?',(body['request_id'],)).fetchone();template=json.loads(row['record'])
            for index in range(8):
                record=copy.deepcopy(template);intent=record['intent'];new_id='synthetic-pending-'+str(index)
                intent['body']['request_id']=new_id;intent['request_sha256']=fingerprint(intent['body']);intent['intent_sha256']=fingerprint({k:v for k,v in intent.items() if k!='intent_sha256'})
                con.execute('INSERT INTO requests VALUES(?,?,?,?)',(new_id,intent['request_sha256'],'save_staged_feedback_plan',canonical(record)))
        status,scan=self.scan(server,project);self.assertEqual((status,scan['status'],scan['total'],scan['shown'],scan['truncated']),(200,'available',9,8,True))
        self.assertEqual(len(scan['items']),8)

    def test_disabled_host_rejects_pending_scan_without_creating_locks(self):
        manager,project,body,server,headers=self.fixture();readonly=self.serve(local_workspace=manager,allow_local_actions=False)
        for root in (manager.root,project.root):
            lock=root/'writer.lock'
            if lock.exists():lock.unlink()
        query=urlencode({'project_id':body['project_id'],'snapshot_ref':project.status()['snapshot_ref']})
        status,_=self.request(readonly,'/api/local-workbench/staged-feedback-plan-pending.json?'+query)
        self.assertEqual(status,405)
        for root in (manager.root,project.root):self.assertFalse((root/'writer.lock').exists())
        for db in (manager.db,project.db):
            for suffix in ('-wal','-shm','-journal'):self.assertFalse(Path(str(db)+suffix).exists())
