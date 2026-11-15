"""Synthetic resume-only verification; no new real research or model."""
import copy
import hashlib
import json
import unittest
from unittest.mock import patch

from autoresearch.contracts import ResearchError,canonical
from autoresearch.project_controller import ProjectController
import test_staged_feedback_successor_plan as fixtures


class StagedSuccessorPlanResumeTests(unittest.TestCase):
    def fixture(self):
        return fixtures.StagedFeedbackSuccessorPlanTests.fixture(self,'wait')

    @staticmethod
    def hashes(manager,project):
        return [hashlib.sha256(p.read_bytes()).hexdigest() for p in (manager.db,project.db)]

    def test_missing_intent_never_accepts_and_original_save_is_unchanged(self):
        manager,project,_,_,body=self.fixture();before=project.status();hashes=self.hashes(manager,project)
        with patch.object(manager,'_accept',side_effect=AssertionError('resume must not accept')), \
             patch.object(ProjectController,'_dispatch',side_effect=AssertionError('no dispatch')):
            with self.assertRaises(ResearchError) as error:manager.resume_staged_feedback_plan(body)
        self.assertEqual(error.exception.code,'OPERATION_INCOMPLETE')
        self.assertEqual(self.hashes(manager,project),hashes);self.assertEqual(project.status(),before)
        saved=manager.save_staged_feedback_plan(body);self.assertEqual(saved['status'],'completed')
        self.assertFalse(saved['replayed']);self.assertTrue(manager.resume_staged_feedback_plan(body)['replayed'])

    def test_preparing_before_project_save_stops_without_creating(self):
        manager,project,_,_,body=self.fixture();before=project.status();actual=manager._staged_plan_reference_locked;calls=[]
        def interrupt(*args):
            result=actual(*args);calls.append(1)
            if len(calls)==2:raise ResearchError('SYNTHETIC_INTERRUPT','after manager intent commit')
            return result
        with patch.object(manager,'_staged_plan_reference_locked',side_effect=interrupt):
            with self.assertRaises(ResearchError):manager.save_staged_feedback_plan(body)
        self.assertEqual(project.status(),before);hashes=self.hashes(manager,project)
        with patch.object(manager,'_accept',side_effect=AssertionError('no accept')), \
             patch.object(ProjectController,'_dispatch',side_effect=AssertionError('no dispatch')):
            with self.assertRaises(ResearchError) as error:manager.resume_staged_feedback_plan(body)
        self.assertEqual(error.exception.code,'OPERATION_INCOMPLETE')
        self.assertEqual(self.hashes(manager,project),hashes);self.assertEqual(project.status(),before)
        with manager._connect(readonly=True) as con:
            row=con.execute('SELECT record FROM requests WHERE id=?',(body['request_id'],)).fetchone()
            self.assertEqual(json.loads(row['record'])['status'],'preparing')

    def test_project_commit_before_manager_receipt_can_only_fill_original_receipt(self):
        manager,project,_,_,body=self.fixture();before=project.status()
        with patch.object(manager,'_save',side_effect=ResearchError('SYNTHETIC_INTERRUPT','after project commit')):
            with self.assertRaises(ResearchError):manager.save_staged_feedback_plan(body)
        committed=project.status();project_sha=self.hashes(manager,project)[1]
        self.assertEqual(len(committed['plan_revisions']),len(before['plan_revisions'])+1)
        self.assertEqual(committed['budget'],before['budget'])
        with patch.object(manager,'_accept',side_effect=AssertionError('no accept')), \
             patch.object(ProjectController,'_dispatch',side_effect=AssertionError('no dispatch')):
            result=manager.resume_staged_feedback_plan(body)
        self.assertTrue(result['replayed']);self.assertEqual(result['status'],'completed')
        self.assertEqual(self.hashes(manager,project)[1],project_sha);self.assertEqual(project.status(),committed)
        original=result['research_plan']
        project.save_plan(request_id='later-plan',expected_state_version=committed['state_version'],
                          plan={'question':'Later?', 'basis':'synthetic','steps':'Review','expected_feedback':'Wait'},reason='Later revision')
        later=project.status();hashes=self.hashes(manager,project)
        self.assertEqual(manager.resume_staged_feedback_plan(body)['research_plan'],original)
        self.assertEqual(self.hashes(manager,project),hashes);self.assertEqual(project.status(),later)

    def test_different_body_and_wrong_command_do_not_recover(self):
        manager,project,_,_,body=self.fixture();manager.save_staged_feedback_plan(body);hashes=self.hashes(manager,project)
        changed=copy.deepcopy(body);changed['plan']['steps']='different body'
        with self.assertRaises(ResearchError) as error:manager.resume_staged_feedback_plan(changed)
        self.assertEqual(error.exception.code,'IDEMPOTENCY_CONFLICT');self.assertEqual(self.hashes(manager,project),hashes)
        with manager._connect() as con:con.execute('UPDATE requests SET command=? WHERE id=?',('other-command',body['request_id']))
        hashes=self.hashes(manager,project)
        with self.assertRaises(ResearchError) as error:manager.resume_staged_feedback_plan(body)
        self.assertEqual(error.exception.code,'OPERATION_INCOMPLETE');self.assertEqual(self.hashes(manager,project),hashes)

    def test_missing_or_corrupt_original_claim_stops_without_write(self):
        for mode in ('missing','changed'):
            with self.subTest(mode=mode):
                manager,project,_,_,body=self.fixture();manager.save_staged_feedback_plan(body)
                with project._connect() as con:
                    if mode=='missing':con.execute("DELETE FROM quality_manager_claims WHERE kind='staged_feedback_plan' AND request_id=?",(body['request_id'],))
                    else:con.execute("UPDATE quality_manager_claims SET core_sha256=? WHERE kind='staged_feedback_plan' AND request_id=?",('0'*64,body['request_id']))
                hashes=self.hashes(manager,project);before=project.status()
                with self.assertRaises(ResearchError):manager.resume_staged_feedback_plan(body)
                self.assertEqual(self.hashes(manager,project),hashes);self.assertEqual(project.status(),before)

    def test_missing_original_body_stops(self):
        manager,project,_,_,body=self.fixture();manager.save_staged_feedback_plan(body)
        with manager._connect() as con:
            row=con.execute('SELECT record FROM requests WHERE id=?',(body['request_id'],)).fetchone()
            record=json.loads(row['record']);del record['intent']['body']
            con.execute('UPDATE requests SET record=? WHERE id=?',(canonical(record),body['request_id']))
        hashes=self.hashes(manager,project)
        with self.assertRaises(ResearchError):manager.resume_staged_feedback_plan(body)
        self.assertEqual(self.hashes(manager,project),hashes)

    def test_deleted_accepted_manager_row_never_recreates_request(self):
        manager,project,_,_,body=self.fixture();manager.save_staged_feedback_plan(body);before=project.status()
        with manager._connect() as con:con.execute('DELETE FROM requests WHERE id=?',(body['request_id'],))
        hashes=self.hashes(manager,project)
        with patch.object(manager,'_accept',side_effect=AssertionError('must not accept')):
            with self.assertRaises(ResearchError) as error:manager.resume_staged_feedback_plan(body)
        self.assertEqual(error.exception.code,'OPERATION_INCOMPLETE')
        self.assertIn('acceptance cannot be established',str(error.exception))
        self.assertEqual(self.hashes(manager,project),hashes);self.assertEqual(project.status(),before)

    def test_other_active_project_cannot_resume_original(self):
        import test_retrieval_holdout as holdout
        manager,project,_,_,body=self.fixture();manager.save_staged_feedback_plan(body)
        helper=holdout.RetrievalHoldoutTests();self.addCleanup(helper.doCleanups);other,_,_=helper.fixture()
        imported=manager.import_project(request_id='import-other',workspace=str(other.root))['project_id']
        manager.select({'request_id':'select-other','project_id':imported})
        old_before=project.status();hashes=self.hashes(manager,project)
        with self.assertRaises(ResearchError):manager.resume_staged_feedback_plan(body)
        self.assertEqual(self.hashes(manager,project),hashes);self.assertEqual(project.status(),old_before)
        manager.select({'request_id':'select-original','project_id':body['project_id']})
        self.assertTrue(manager.resume_staged_feedback_plan(body)['replayed'])

    def test_preparing_with_committed_revision_but_missing_or_changed_claim_never_fills_receipt(self):
        for mode in ('missing','changed'):
            with self.subTest(mode=mode):
                manager,project,_,_,body=self.fixture()
                with patch.object(manager,'_save',side_effect=ResearchError('SYNTHETIC_INTERRUPT','after project commit')):
                    with self.assertRaises(ResearchError):manager.save_staged_feedback_plan(body)
                with project._connect() as con:
                    if mode=='missing':con.execute("DELETE FROM quality_manager_claims WHERE kind='staged_feedback_plan' AND request_id=?",(body['request_id'],))
                    else:con.execute("UPDATE quality_manager_claims SET intent_sha256=? WHERE kind='staged_feedback_plan' AND request_id=?",('0'*64,body['request_id']))
                hashes=self.hashes(manager,project);before=project.status()
                with patch.object(manager,'_save',side_effect=AssertionError('must not fill receipt')):
                    with self.assertRaises(ResearchError):manager.resume_staged_feedback_plan(body)
                self.assertEqual(self.hashes(manager,project),hashes);self.assertEqual(project.status(),before)
                with manager._connect(readonly=True) as con:
                    row=con.execute('SELECT record FROM requests WHERE id=?',(body['request_id'],)).fetchone()
                    self.assertEqual(json.loads(row['record'])['status'],'preparing')

    def test_both_commit_windows_resume_in_fresh_process(self):
        import os,subprocess,sys,tempfile
        script='''import json,sys\nfrom autoresearch.local_workbench import LocalWorkbench\nfrom autoresearch.contracts import ResearchError\nv=json.load(sys.stdin);m=LocalWorkbench(v["root"])\ntry:\n r=m.resume_staged_feedback_plan(v["body"]);print(json.dumps({"status":r["status"],"replayed":r["replayed"]}))\nexcept ResearchError as e: print(json.dumps({"code":e.code}))\n'''
        for window in ('intent_only','project_committed'):
            with self.subTest(window=window):
                manager,project,_,_,body=self.fixture();before=project.status()
                if window=='intent_only':
                    actual=manager._staged_plan_reference_locked;calls=[]
                    def interrupt(*args):
                        result=actual(*args);calls.append(1)
                        if len(calls)==2:raise ResearchError('SYNTHETIC_INTERRUPT','after intent')
                        return result
                    context=patch.object(manager,'_staged_plan_reference_locked',side_effect=interrupt)
                else:context=patch.object(manager,'_save',side_effect=ResearchError('SYNTHETIC_INTERRUPT','after project commit'))
                with context:
                    with self.assertRaises(ResearchError):manager.save_staged_feedback_plan(body)
                committed=project.status();hashes=self.hashes(manager,project)
                with tempfile.TemporaryDirectory() as cache:
                    env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1',PYTHONPYCACHEPREFIX=cache)
                    result=subprocess.run([sys.executable,'-B','-c',script],input=json.dumps({'root':str(manager.root),'body':body}),
                                          text=True,capture_output=True,env=env,timeout=60,check=True)
                observed=json.loads(result.stdout)
                if window=='intent_only':
                    self.assertEqual(observed,{'code':'OPERATION_INCOMPLETE'});self.assertEqual(self.hashes(manager,project),hashes)
                    self.assertEqual(committed,before)
                else:
                    self.assertEqual(observed,{'status':'completed','replayed':True});self.assertEqual(self.hashes(manager,project)[1],hashes[1])
                    self.assertEqual(project.status(),committed);self.assertEqual(committed['budget'],before['budget'])
