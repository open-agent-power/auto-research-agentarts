"""SIGKILL at two explicit commit fences in synthetic quality-plan projects.

Workers are real independent Python processes. This checks selected process
termination windows, not power loss, every possible interleaving, or science.
"""
import base64
import hashlib
import json
import os
from pathlib import Path
import selectors
import signal
import sqlite3
import subprocess
import sys
import unittest
from unittest.mock import patch

import test_quality_plan_workbench as fixture
from autoresearch.contracts import ResearchError, canonical, fingerprint
from autoresearch.local_workbench import LocalWorkbench
from autoresearch.project_controller import ProjectController
from autoresearch.research_project import ResearchProject


def _fence(point):
    print(json.dumps({'event':'fence','point':point,'pid':os.getpid()}),flush=True)
    # Parent never releases this pipe: it must terminate the process itself.
    sys.stdin.read(1)
    raise RuntimeError('The parent did not SIGKILL at the fence')


def _worker(mode, kind, point, root, encoded):
    body=json.loads(base64.b64decode(encoded).decode('utf-8'))
    manager=LocalWorkbench(root)
    method=manager.save_quality_plan if kind=='plan' else manager.advance_tabular_quality_feedback_v2
    if mode=='kill':
        if point=='before-core':
            if kind=='plan':
                original=ResearchProject.save_plan
                def save(project,**kwargs):
                    if kwargs.get('_return_created'):_fence(point)
                    return original(project,**kwargs)
                with patch.object(ResearchProject,'save_plan',new=save):method(body)
            else:
                with patch.object(ProjectController,'advance_tabular_quality_feedback_v2',side_effect=lambda **kw:_fence(point)):
                    method(body)
        elif point=='parent-prepared':
            with patch.object(ProjectController,'_dispatch',side_effect=lambda *a,**kw:_fence(point)):
                method(body)
        else:
            original=manager._save
            def save(con,request_id,record):
                if request_id==body['request_id'] and record.get('status')=='completed':_fence(point)
                return original(con,request_id,record)
            with patch.object(manager,'_save',side_effect=save):method(body)
        raise RuntimeError('Operation unexpectedly passed its fence')
    original=ResearchProject.save_plan
    def read_only_plan(project,**kwargs):
        if not kwargs.get('_validate_only'):raise AssertionError('recovery attempted a plan write')
        return original(project,**kwargs)
    try:
        with patch.object(ResearchProject,'save_plan',new=read_only_plan), \
             patch.object(ResearchProject,'step',side_effect=AssertionError('recovery attempted a step')), \
             patch.object(ProjectController,'_dispatch',side_effect=AssertionError('recovery attempted dispatch')):
            result=method(body)
        value={'event':'recovery','pid':os.getpid(),'status':result['status'],'replayed':result['replayed']}
    except ResearchError as exc:
        value={'event':'recovery','pid':os.getpid(),'error':exc.code}
    print(json.dumps(value),flush=True)


class ProcessRecoveryTests(unittest.TestCase):
    def stage(self):
        helper=fixture.QualityPlanWorkbenchTests(methodName='runTest')
        f,m,b=helper.stage();self.addCleanup(helper.doCleanups)
        return helper,f,m,b

    def spawn(self, mode, kind, point, manager, body):
        data=base64.b64encode(canonical(body).encode()).decode('ascii')
        proc=subprocess.Popen([sys.executable,'-B',str(Path(__file__).resolve()),'--worker',mode,kind,point,
                               str(manager.root),data],stdin=subprocess.PIPE,stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE,text=True,bufsize=1)
        def cleanup():
            if proc.poll() is None:proc.kill()
            proc.communicate(timeout=15)
        self.addCleanup(cleanup)
        return proc

    def event(self,proc,timeout=30):
        with selectors.DefaultSelector() as selector:
            selector.register(proc.stdout,selectors.EVENT_READ)
            ready=selector.select(timeout)
        if not ready:
            proc.kill();out,err=proc.communicate(timeout=10)
            self.fail('Worker did not reach fence: '+out+' '+err)
        line=proc.stdout.readline()
        if not line:
            _,err=proc.communicate(timeout=10);self.fail('Worker exited before fence: '+err)
        value=json.loads(line)
        self.assertEqual(value['pid'],proc.pid)
        return value

    @staticmethod
    def manager_record(manager,request_id):
        with sqlite3.connect(manager.db.as_uri()+'?mode=ro',uri=True) as con:
            row=con.execute('select record from requests where id=?',(request_id,)).fetchone()
        return json.loads(row[0]) if row else None

    @staticmethod
    def claims(project,kind,request_id):
        with sqlite3.connect(project.db.as_uri()+'?mode=ro',uri=True) as con:
            return con.execute('select intent_sha256,core_sha256 from quality_manager_claims where kind=? and request_id=?',
                               (kind,request_id)).fetchall()

    @staticmethod
    def artifacts(project,state):
        return {a['request_id']:hashlib.sha256((project.root/a['artifact']).read_bytes()).hexdigest()
                for a in state['actions'] if a.get('artifact')}

    def run_cut(self,kind,point):
        helper,f,m,b=self.stage()
        if kind=='plan':body=helper.plan_body(f,b)
        else:
            plan=m.save_quality_plan(helper.plan_body(f,b))['research_plan']
            body=helper.policy_body(f,b,plan)
        original=f.project.status();original_artifacts=self.artifacts(f.project,original)
        proc=self.spawn('kill',kind,point,m,body)
        self.assertEqual(self.event(proc),{'event':'fence','point':point,'pid':proc.pid})
        intent=self.manager_record(m,body['request_id'])
        self.assertEqual(intent['status'],'preparing');self.assertEqual(intent['intent']['body'],body)
        at_fence=f.project.status();at_artifacts=self.artifacts(f.project,at_fence)
        self.assertEqual(len(at_artifacts),len(at_fence['actions']))
        self.assertGreaterEqual(len(at_artifacts),1)
        claim=self.claims(f.project,kind,body['request_id'])
        if point=='before-core':
            self.assertEqual(at_fence,original);self.assertEqual(at_artifacts,original_artifacts);self.assertEqual(claim,[])
        else:
            self.assertEqual(len(claim),1);self.assertEqual(claim[0][0],intent['intent']['intent_sha256'])
            if kind=='plan':
                self.assertEqual(len(at_fence['plan_revisions']),len(original['plan_revisions'])+1)
                self.assertEqual(claim[0][1],fingerprint(at_fence['plan_revisions'][-1]))
                self.assertEqual(at_fence['budget'],original['budget'])
            else:
                parent=next(p for p in at_fence['controller_requests'] if p['request_id']==body['request_id'])
                self.assertEqual(claim[0][1],fingerprint({'request_sha256':parent['request_sha256'],
                                                          'policy_sha256':parent['tabular_quality_policy']['record_sha256']}))
                self.assertEqual(parent['status'],'prepared' if point=='parent-prepared' else 'completed')
                self.assertEqual(len(at_fence['actions']),1 if point=='parent-prepared' else 2)
                self.assertEqual(at_fence['budget']['local_tool_calls_used'],1 if point=='parent-prepared' else 2)
                with sqlite3.connect(f.project.db.as_uri()+'?mode=ro',uri=True) as con:
                    row=con.execute('select fingerprint,record from actions where request_id=?',
                                    (parent['child_request_id'],)).fetchone()
                if point=='parent-prepared':
                    self.assertIsNone(row);self.assertIsNone(parent['result'])
                else:
                    action=at_fence['actions'][-1];child=parent['result']['child']
                    self.assertIsNotNone(row)
                    self.assertEqual(row[0],action['request_sha256'])
                    self.assertEqual(json.loads(row[1]),action)
                    self.assertEqual((child['id'],child['request_id'],child['result_sha256']),
                                     (action['id'],action['request_id'],action['result_sha256']))
                    self.assertEqual(child['request_id'],parent['child_request_id'])
                    envelope=json.loads((f.project.root/action['artifact']).read_bytes())
                    self.assertEqual(envelope['sha256'],action['result_sha256'])
                    self.assertEqual(envelope['sha256'],fingerprint({k:v for k,v in envelope.items() if k!='sha256'}))
                self.assertEqual((at_fence['budget']['new_model_requests'],at_fence['budget']['new_fits'],
                                  at_fence['budget']['evidence_reads_used']),(0,0,0))
        os.kill(proc.pid,signal.SIGKILL)
        proc.wait(timeout=15);self.assertEqual(proc.returncode,-signal.SIGKILL)
        self.assertEqual(self.manager_record(m,body['request_id']),intent)
        self.assertEqual(f.project.status(),at_fence);self.assertEqual(self.artifacts(f.project,at_fence),at_artifacts)
        project_bytes=f.project.db.read_bytes()
        recovery=self.spawn('recover',kind,point,m,body);reply=self.event(recovery);recovery.wait(timeout=30)
        self.assertEqual(recovery.returncode,0);self.assertNotEqual(recovery.pid,proc.pid)
        if point in ('before-core','parent-prepared'):
            self.assertEqual(reply,{'event':'recovery','pid':recovery.pid,
                                   'error':'EXECUTION_UNKNOWN' if point=='parent-prepared' else 'OPERATION_INCOMPLETE'})
            self.assertEqual(self.manager_record(m,body['request_id']),intent)
        else:
            self.assertEqual(reply,{'event':'recovery','pid':recovery.pid,'status':'completed','replayed':True})
            self.assertEqual(self.manager_record(m,body['request_id'])['status'],'completed')
        self.assertEqual(f.project.db.read_bytes(),project_bytes)
        self.assertEqual(f.project.status(),at_fence);self.assertEqual(self.artifacts(f.project,at_fence),at_artifacts)
        print(json.dumps({'kind':kind,'fence':point,'killed_pid':proc.pid,'kill_returncode':proc.returncode,
                          'recovery_pid':recovery.pid,'recovery':reply,'manager_before':'preparing',
                          'manager_after':self.manager_record(m,body['request_id'])['status'],
                          'claim_count':len(claim),'actions':len(at_fence['actions']),
                          'tool_calls_used':at_fence['budget']['local_tool_calls_used'],
                          'project_db_sha256':hashlib.sha256(project_bytes).hexdigest(),
                          'artifact_sha256':at_artifacts}),flush=True)

    def test_plan_before_core(self):self.run_cut('plan','before-core')
    def test_plan_after_core(self):self.run_cut('plan','after-core')
    def test_policy_before_core(self):self.run_cut('policy','before-core')
    def test_policy_parent_prepared(self):self.run_cut('policy','parent-prepared')
    def test_policy_after_core(self):self.run_cut('policy','after-core')


if __name__=='__main__':
    if len(sys.argv)==7 and sys.argv[1]=='--worker':_worker(*sys.argv[2:])
    else:unittest.main()
