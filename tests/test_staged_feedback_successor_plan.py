"""Synthetic strict feedback -> explicit successor plan; no real research or model."""
import copy
import unittest
from unittest.mock import patch

from autoresearch.contracts import ResearchError, fingerprint
from autoresearch.project_controller import ProjectController
from autoresearch import staged_relevance_adapter as staged
import test_staged_feedback_workbench as feedback_tests


class StagedFeedbackSuccessorPlanTests(unittest.TestCase):
    def fixture(self, branch='wait', outcome='not_met'):
        manager, project, feedback = feedback_tests.StagedFeedbackWorkbenchTests.fixture(self, branch, outcome)
        answer = manager.advance_staged_feedback(feedback)
        before = project.status()
        body = {'request_id':'successor-plan', 'project_id':before['id'],
                'expected_state_version':before['state_version'], 'feedback_request_id':feedback['request_id'],
                'plan':{'question':'Next synthetic question?', 'basis':'Original validation feedback',
                        'steps':'Choose a later, separately authorized action', 'expected_feedback':'Review the new result'},
                'reason':'Update after the original saved feedback'}
        return manager,project,feedback,answer,body

    def test_wait_and_audit_successor_and_original_id_replay(self):
        for branch in ('wait','audit'):
            with self.subTest(branch=branch):
                manager,project,feedback,answer,body=self.fixture(branch)
                before=project.status()
                with patch.object(ProjectController,'_dispatch',side_effect=AssertionError('No dispatch')):
                    saved=manager.save_staged_feedback_plan(body)
                    state=project.status()
                    replay=manager.save_staged_feedback_plan(copy.deepcopy(body))
                self.assertEqual(saved['status'],'completed')
                self.assertTrue(replay['replayed'])
                self.assertEqual(project.status(),state)
                self.assertEqual(state['budget'],before['budget'])
                revision=saved['research_plan']; ref=revision['staged_feedback_ref']
                self.assertEqual(revision['version'],2)
                self.assertEqual(ref['original_plan_sha256'],fingerprint(before['plan_revisions'][0]))
                self.assertEqual(ref['feedback_parent_request_id'],feedback['request_id'])
                self.assertEqual(ref['primary_action_id'],feedback['primary_action_id'])
                self.assertEqual(ref['decision'],branch)
                self.assertEqual(ref['feedback_outcome'],'condition_not_met')
                self.assertEqual(ref['audit_action_id'] is None,branch=='wait')
                self.assertEqual(answer['status'],'waiting' if branch=='wait' else 'completed')
                manager.resume_staged_feedback({'request_id':feedback['request_id'],'project_id':body['project_id']})
                self.assertEqual(project.status(),state)

    def test_same_id_different_body_and_incomplete_intent_stop(self):
        manager,project,feedback,answer,body=self.fixture()
        manager.save_staged_feedback_plan(body); state=project.status()
        changed=copy.deepcopy(body);changed['plan']['steps']='Different successor'
        with self.assertRaises(ResearchError) as caught: manager.save_staged_feedback_plan(changed)
        self.assertEqual(caught.exception.code,'IDEMPOTENCY_CONFLICT')
        self.assertEqual(project.status(),state)

    def test_plan_drift_and_missing_feedback_stop_before_acceptance(self):
        manager,project,feedback,answer,body=self.fixture(); state=project.status()
        changed=copy.deepcopy(body);changed['feedback_request_id']='missing-feedback'
        with self.assertRaises(ResearchError): manager.save_staged_feedback_plan(changed)
        self.assertEqual(project.status(),state)
        project.save_plan(request_id='other-plan',expected_state_version=state['state_version'],plan=body['plan'],reason='independent change')
        state=project.status();body['expected_state_version']=state['state_version']
        with self.assertRaises(ResearchError): manager.save_staged_feedback_plan(body)
        self.assertEqual(project.status(),state)

    def test_audit_actual_completion_time_is_required_on_replay(self):
        import json
        from autoresearch.contracts import canonical
        manager,project,feedback,answer,body=self.fixture('audit')
        manager.save_staged_feedback_plan(body)
        parent=next(x for x in project.status()['controller_requests'] if x['request_id']==feedback['request_id'])
        self.assertGreater(parent['state_version_after'],parent['dispatch_state_version'])
        forged=copy.deepcopy(body);forged['expected_state_version']=parent['dispatch_state_version']
        with manager._connect() as con:
            row=con.execute('SELECT record FROM requests WHERE id=?',(body['request_id'],)).fetchone()
            record=json.loads(row['record']);intent=record['intent'];intent['body']=forged;intent['request_sha256']=fingerprint(forged)
            intent['intent_sha256']=fingerprint({k:v for k,v in intent.items() if k!='intent_sha256'})
            record['status']='preparing';record['result']=None
            con.execute('UPDATE requests SET digest=?,record=? WHERE id=?',(fingerprint(forged),canonical(record),body['request_id']))
        with project._connect() as con:
            stored=project._project(con);rev=next(x for x in stored['plan_revisions'] if x['request_id']==body['request_id'])
            rev['based_on_state_version']=forged['expected_state_version'];project._save(con,stored)
            con.execute("UPDATE quality_manager_claims SET intent_sha256=?,core_sha256=? WHERE kind='staged_feedback_plan' AND request_id=?",
                        (intent['intent_sha256'],fingerprint(rev),body['request_id']))
        before=project.status()
        with self.assertRaises(ResearchError):manager.save_staged_feedback_plan(forged)
        self.assertEqual(project.status(),before)

    def test_drifting_experience_bytes_after_intent_never_saves_revision_or_claim(self):
        import test_plan_experience_refs as cases
        helper=cases.PlanExperienceReferenceTests();self.addCleanup(helper.doCleanups)
        _,history,_,refs,historical_case=helper.setup_case()
        raw=(history.root / historical_case['bundle_ref']).read_bytes()
        manager,project,feedback,answer,body=self.fixture()
        imported=project.import_experience(request_id='local-case',expected_state_version=project.status()['state_version'],
                                           bundle=raw,reason='Synthetic analogy')
        body['expected_state_version']=project.status()['state_version']
        item=copy.deepcopy(refs['items'][0]);item.update(case_id=imported['case_id'],case_version=imported['case_version'],bundle_sha256=imported['bundle_sha256'])
        body['plan']['experience_case_refs']={'schema_version':'project-plan-experience-refs-v1','items':[item]}
        saved_file=project.root / imported['bundle_ref']; before=project.status(); actual=manager._staged_plan_reference_locked; calls=[]
        def during(*args):
            result=actual(*args);calls.append(1)
            if len(calls)==2: saved_file.write_bytes(raw+b' ')
            return result
        with patch.object(manager,'_staged_plan_reference_locked',side_effect=during):
            with self.assertRaises(ResearchError):manager.save_staged_feedback_plan(body)
        self.assertEqual(len(calls),2)
        self.assertEqual(project.status(),before)
        with project._connect(readonly=True) as con:
            self.assertIsNone(con.execute("SELECT 1 FROM quality_manager_claims WHERE kind='staged_feedback_plan' AND request_id=?",(body['request_id'],)).fetchone())
        status=manager.describe()['pending_staged_feedback_plan_summary']
        self.assertEqual(status['total'],1)

    def test_missing_original_manager_feedback_and_source_drift_stop(self):
        manager,project,feedback,answer,body=self.fixture();before=project.status()
        with manager._connect() as con:con.execute('DELETE FROM requests WHERE id=?',(feedback['request_id'],))
        with self.assertRaises(ResearchError):manager.save_staged_feedback_plan(body)
        self.assertEqual(project.status(),before)
        manager,project,feedback,answer,body=self.fixture();before=project.status()
        path=project.root/'source.json';path.write_bytes(path.read_bytes()+b' ')
        with self.assertRaises(ResearchError):manager.save_staged_feedback_plan(body)
        self.assertEqual(project.status(),before)

    def test_private_evaluation_marker_blocks_successor(self):
        manager,project,feedback,answer,body=self.fixture()
        with project._connect() as con:
            stored=project._project(con);stored['private_evaluation']={'request_id':'isolated-invalid-holdout'};project._save(con,stored)
        before=project.status()
        with self.assertRaises(ResearchError):manager.save_staged_feedback_plan(body)
        self.assertEqual(project.status(),before)

    def test_malformed_primary_artifact_is_integrity_error_without_plan(self):
        manager,project,feedback,answer,body=self.fixture();before=project.status()
        action=next(a for a in before['actions'] if a['id']==feedback['primary_action_id'])
        project._artifact(action).write_bytes(b'{')
        with self.assertRaises(ResearchError) as caught:manager.save_staged_feedback_plan(body)
        self.assertEqual(caught.exception.code,'INVALID_SOURCE')
        self.assertEqual(project.status(),before)
        with manager._connect(readonly=True) as con:
            self.assertIsNone(con.execute('SELECT 1 FROM requests WHERE id=?',(body['request_id'],)).fetchone())

    def test_experience_and_feedback_refs_can_coexist_and_replay(self):
        import test_plan_experience_refs as cases
        helper=cases.PlanExperienceReferenceTests();self.addCleanup(helper.doCleanups)
        _,history,_,refs,historical_case=helper.setup_case()
        raw=(history.root / historical_case['bundle_ref']).read_bytes()
        manager,project,feedback,answer,body=self.fixture()
        imported=project.import_experience(request_id='local-case',expected_state_version=project.status()['state_version'],
                                           bundle=raw,reason='Synthetic analogy')
        body['expected_state_version']=project.status()['state_version']
        item=copy.deepcopy(refs['items'][0]);item.update(case_id=imported['case_id'],case_version=imported['case_version'],bundle_sha256=imported['bundle_sha256'])
        body['plan']['experience_case_refs']={'schema_version':'project-plan-experience-refs-v1','items':[item]}
        before=project.status();saved=manager.save_staged_feedback_plan(body);after=project.status()
        self.assertEqual(after['budget'],before['budget'])
        self.assertEqual(saved['research_plan']['experience_case_refs'],body['plan']['experience_case_refs'])
        self.assertEqual(saved['research_plan']['staged_feedback_ref']['feedback_parent_request_id'],feedback['request_id'])
        self.assertTrue(manager.save_staged_feedback_plan(copy.deepcopy(body))['replayed'])
        self.assertEqual(project.status(),after)
        (project.root/imported['bundle_ref']).write_bytes(raw+b' ')
        with self.assertRaises(ResearchError):manager.save_staged_feedback_plan(copy.deepcopy(body))

    def test_claim_insert_failure_rolls_back_revision_and_resume_cannot_create(self):
        from autoresearch import tabular_quality_feedback as claims
        manager,project,feedback,answer,body=self.fixture();before=project.status();original=claims._manager_claim
        def fail_new(con,kind,request_id,intent_sha256,core_sha256,*,create=False):
            if kind=='staged_feedback_plan' and create:
                raise ResearchError('SYNTHETIC_FAILURE','Claim insert failed')
            return original(con,kind,request_id,intent_sha256,core_sha256,create=create)
        with patch.object(claims,'_manager_claim',side_effect=fail_new):
            with self.assertRaises(ResearchError):manager.save_staged_feedback_plan(body)
        self.assertEqual(project.status(),before)
        with project._connect(readonly=True) as con:
            self.assertIsNone(con.execute("SELECT 1 FROM quality_manager_claims WHERE kind='staged_feedback_plan' AND request_id=?",(body['request_id'],)).fetchone())
        with self.assertRaises(ResearchError) as caught:manager.save_staged_feedback_plan(body)
        self.assertEqual(caught.exception.code,'OPERATION_INCOMPLETE')
        self.assertEqual(project.status(),before)
        self.assertEqual(manager.describe()['pending_staged_feedback_plan_summary']['total'],1)

    def test_source_artifact_deleted_maps_to_integrity_error(self):
        manager,project,feedback,answer,body=self.fixture();before=project.status()
        action=next(a for a in before['actions'] if a['id']==feedback['primary_action_id'])
        project._artifact(action).unlink()
        with self.assertRaises(ResearchError) as caught:manager.save_staged_feedback_plan(body)
        self.assertIn(caught.exception.code,('EVIDENCE_CHANGED','INVALID_SOURCE'))
        self.assertEqual(project.status(),before)

    def test_old_plan_entry_cannot_read_or_replay_new_manager_revision(self):
        manager,project,feedback,answer,body=self.fixture();saved=manager.save_staged_feedback_plan(body);before=project.status()
        for text in (body['plan'],{**body['plan'],'steps':'Different text'}):
            with self.assertRaises(ResearchError) as caught:
                project.save_plan(request_id=body['request_id'],expected_state_version=body['expected_state_version'],plan=text,reason=body['reason'])
            self.assertEqual(caught.exception.code,'OPERATION_INCOMPLETE')
        with self.assertRaises(ResearchError):
            manager.save_plan({'request_id':body['request_id'],'project_id':body['project_id'],
                               'expected_state_version':body['expected_state_version'],'plan':body['plan'],'reason':body['reason']})
        self.assertTrue(manager.save_staged_feedback_plan(body)['replayed']);self.assertEqual(project.status(),before)
        with project._connect() as con:
            con.execute("DELETE FROM quality_manager_claims WHERE kind='staged_feedback_plan' AND request_id=?",(body['request_id'],))
        with self.assertRaises(ResearchError):manager.save_staged_feedback_plan(body)
        with self.assertRaises(ResearchError) as caught:
            project.save_plan(request_id=body['request_id'],expected_state_version=body['expected_state_version'],plan=body['plan'],reason=body['reason'])
        self.assertEqual(caught.exception.code,'OPERATION_INCOMPLETE');self.assertEqual(project.status(),before)

    def test_unresolved_source_or_local_model_blocks_first_save(self):
        for kind in ('source','local_model'):
            with self.subTest(kind=kind):
                manager,project,feedback,answer,body=self.fixture()
                with project._connect() as con:
                    state=project._project(con)
                    if kind=='source':state.setdefault('source_requests',[]).append({'request_id':'unfinished-source','status':'unknown'})
                    else:state.setdefault('local_model_requests',[]).append({'request_id':'unfinished-model','status':'reserved'})
                    project._save(con,state)
                before=project.status();body['expected_state_version']=before['state_version']
                with self.assertRaises(ResearchError):manager.save_staged_feedback_plan(body)
                self.assertEqual(project.status(),before)
                with manager._connect(readonly=True) as con:
                    self.assertIsNone(con.execute('SELECT 1 FROM requests WHERE id=?',(body['request_id'],)).fetchone())
                with project._connect(readonly=True) as con:
                    self.assertIsNone(con.execute("SELECT 1 FROM quality_manager_claims WHERE kind='staged_feedback_plan' AND request_id=?",(body['request_id'],)).fetchone())

    def test_real_preregistered_holdout_is_rejected_after_authenticated_feedback(self):
        from test_feedback_selected_holdout import FeedbackSelectedHoldoutTests
        helper=FeedbackSelectedHoldoutTests();self.addCleanup(helper.doCleanups)
        manager,project,_,_,prediction=helper.fixture(register_prediction=False,execute=False,audit_notmet=True)
        registration=manager.register_staged_hypothesis({'request_id':'prediction','project_id':project.status()['id'],
            'expected_state_version':project.status()['state_version'],'hypothesis':prediction})['registration']
        primary=manager.advance_staged_primary({'request_id':registration['controller_request_id'],'project_id':project.status()['id'],
            'expected_state_version':project.status()['state_version'],'registration_request_id':registration['request_id'],
            'registration_sha256':registration['registration_sha256'],'reason':'Synthetic preregistered primary'})['controller']['result']['child']
        feedback={'request_id':'policy-audit','project_id':project.status()['id'],'expected_state_version':project.status()['state_version'],
                  'registration_request_id':registration['request_id'],'registration_sha256':registration['registration_sha256'],
                  'primary_action_id':primary['id']}
        manager.advance_staged_feedback(feedback);before=project.status()
        self.assertIsNotNone(before['private_evaluation'])
        body={'request_id':'blocked-successor','project_id':before['id'],'expected_state_version':before['state_version'],
              'feedback_request_id':feedback['request_id'],'plan':{'question':'Next?','basis':'Synthetic feedback',
              'steps':'Future action','expected_feedback':'Inspect later'},'reason':'Do not amend registered holdout'}
        with self.assertRaises(ResearchError) as caught:manager.save_staged_feedback_plan(body)
        self.assertEqual(caught.exception.code,'CONDITION_NOT_SATISFIED')
        self.assertEqual(project.status(),before)
        with manager._connect(readonly=True) as con:
            self.assertIsNone(con.execute('SELECT 1 FROM requests WHERE id=?',(body['request_id'],)).fetchone())
