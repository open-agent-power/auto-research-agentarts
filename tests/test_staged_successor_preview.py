"""Synthetic staged-plan decision preview; no real research, model or dispatch."""
import copy
import hashlib
from pathlib import Path
import unittest
from unittest.mock import patch

from autoresearch.contracts import ResearchError, fingerprint
from autoresearch.project_controller import ProjectController
from autoresearch.research_project import ResearchProject
from autoresearch import staged_relevance_adapter as staged
import test_staged_feedback_successor_plan as successor_fixture
import test_staged_feedback_workbench as feedback_fixture


class StagedSuccessorPreviewTests(unittest.TestCase):
    @staticmethod
    def rule():
        return {'schema_version':'staged-feedback-preview-rule-v1','condition_met':'audit',
                'condition_not_met':'audit','posthoc_acknowledged':True}

    def fixture(self, branch='wait', *, limit_one=False, outcome='not_met'):
        if not limit_one:
            manager,project,feedback,_,plan=successor_fixture.StagedFeedbackSuccessorPlanTests.fixture(self,branch,outcome)
        else:
            manager,project,feedback=feedback_fixture.StagedFeedbackWorkbenchTests.fixture(self,'wait',limit_one=True)
            manager.advance_staged_feedback(feedback);state=project.status()
            plan={'request_id':'successor-plan','project_id':state['id'],'expected_state_version':state['state_version'],
                  'feedback_request_id':feedback['request_id'],'plan':{'question':'Synthetic?','basis':'Original result',
                  'steps':'Review','expected_feedback':'Inspect'},'reason':'Synthetic successor'}
        revision=manager.save_staged_feedback_plan(plan)['research_plan'];state=project.status()
        body={'project_id':state['id'],'snapshot_ref':state['snapshot_ref'],
              'plan_request_id':revision['request_id'],'plan_sha256':fingerprint(revision)}
        return manager,project,feedback,body

    def checked_preview(self,manager,project,body):
        files=[manager.db,project.db];before=[hashlib.sha256(p.read_bytes()).hexdigest() for p in files]
        def tree():
            return {str(p.relative_to(manager.root)):hashlib.sha256(p.read_bytes()).hexdigest()
                    for p in manager.root.rglob('*') if p.is_file() and p.name != 'writer.lock'}
        initial_tree=tree();budget=copy.deepcopy(project.status()['budget'])
        with patch.object(manager,'_save',side_effect=AssertionError('no manager receipt')), \
             patch.object(manager,'_accept',side_effect=AssertionError('no manager intent')), \
             patch.object(ProjectController,'_dispatch',side_effect=AssertionError('no dispatch')), \
             patch.object(ResearchProject,'save_plan',side_effect=AssertionError('no plan save')):
            result=manager.preview_staged_feedback_plan(body)
        self.assertEqual(before,[hashlib.sha256(p.read_bytes()).hexdigest() for p in files])
        self.assertEqual(initial_tree,tree())
        self.assertEqual(budget,project.status()['budget'])
        self.assertFalse(result['may_execute']);self.assertFalse(result['scientific_validation'])
        self.assertEqual((result['additional_dispatches'],result['model_calls'],result['new_fits']),(0,0,0))
        return result

    def test_default_wait_and_explicit_posthoc_audit_are_preview_only(self):
        manager,project,feedback,body=self.fixture('wait')
        result=self.checked_preview(manager,project,body)
        self.assertEqual((result['decision'],result['candidate']),('wait',None))
        self.assertIsNone(result['candidate_potential_cost'])
        self.assertEqual(result['original_feedback_decision'],'wait')
        self.assertEqual(result['primary_action_id'],feedback['primary_action_id'])
        self.assertEqual(result['registration_sha256'],feedback['registration_sha256'])
        self.assertEqual(result['feedback_request_id'],feedback['request_id'])
        body['posthoc_rule']=self.rule();result=self.checked_preview(manager,project,body)
        self.assertEqual((result['decision'],result['reason']),('suggest_audit','posthoc_new_authorization_required'))
        self.assertEqual(result['candidate']['method_id'],staged.AUDIT_TOOL_ID)
        self.assertEqual(result['candidate_potential_cost'],{'local_tool_calls':1,'evidence_reads':0,'estimator_fits':0})
        self.assertEqual(result['candidate']['parameters']['based_on_action_id'],feedback['primary_action_id'])

    def test_completed_audit_or_exhausted_budget_wait(self):
        for branch,limit_one,expected in [('audit',False,'audit_already_completed'),('wait',True,'tool_budget_exhausted')]:
            with self.subTest(branch=branch):
                manager,project,feedback,body=self.fixture(branch,limit_one=limit_one);body['posthoc_rule']=self.rule()
                result=self.checked_preview(manager,project,body)
                self.assertEqual((result['decision'],result['reason'],result['candidate']),('wait',expected,None))

    def test_wrong_snapshot_plan_and_unacknowledged_rule_reject(self):
        manager,project,feedback,body=self.fixture()
        for changed in ({**body,'snapshot_ref':'0'*64},{**body,'plan_sha256':'0'*64},
                        {**body,'posthoc_rule':{**self.rule(),'posthoc_acknowledged':False}}):
            with self.subTest(changed=changed),self.assertRaises(ResearchError):manager.preview_staged_feedback_plan(changed)

    def test_incomplete_manager_and_missing_plan_claim_stop_without_receipt_write(self):
        import json
        from autoresearch.contracts import canonical
        manager,project,feedback,body=self.fixture()
        with manager._connect() as con:
            row=con.execute('SELECT record FROM requests WHERE id=?',(body['plan_request_id'],)).fetchone()
            record=json.loads(row['record']);record['status']='preparing';record['result']=None
            con.execute('UPDATE requests SET record=? WHERE id=?',(canonical(record),body['plan_request_id']))
        before=hashlib.sha256(manager.db.read_bytes()).hexdigest()
        with self.assertRaises(ResearchError):manager.preview_staged_feedback_plan(body)
        self.assertEqual(hashlib.sha256(manager.db.read_bytes()).hexdigest(),before)
        manager,project,feedback,body=self.fixture()
        with project._connect() as con:con.execute("DELETE FROM quality_manager_claims WHERE kind='staged_feedback_plan' AND request_id=?",(body['plan_request_id'],))
        before=hashlib.sha256(project.db.read_bytes()).hexdigest()
        with self.assertRaises(ResearchError):manager.preview_staged_feedback_plan(body)
        self.assertEqual(hashlib.sha256(project.db.read_bytes()).hexdigest(),before)

    def test_database_sidecar_rejected_and_lock_file_side_effect_disclosed(self):
        manager,project,feedback,body=self.fixture()
        lock=manager.root/'writer.lock';lock.unlink()
        self.checked_preview(manager,project,body)
        self.assertTrue(lock.is_file());self.assertEqual(lock.stat().st_size,1)
        sidecar=Path(str(project.db)+'-journal');sidecar.write_bytes(b'synthetic-pending')
        before=hashlib.sha256(project.db.read_bytes()).hexdigest()
        with self.assertRaises(ResearchError):manager.preview_staged_feedback_plan(body)
        self.assertEqual(hashlib.sha256(project.db.read_bytes()).hexdigest(),before)
        self.assertEqual(sidecar.read_bytes(),b'synthetic-pending')

    def test_original_primary_sql_or_artifact_damage_stops_without_writes(self):
        for damaged in ('sql','artifact'):
            with self.subTest(damaged=damaged):
                manager,project,feedback,body=self.fixture()
                action=next(a for a in project.status()['actions'] if a['id']==feedback['primary_action_id'])
                if damaged=='sql':
                    with project._connect() as con:con.execute('UPDATE actions SET fingerprint=? WHERE request_id=?',('0'*64,action['request_id']))
                else:project._artifact(action).write_bytes(b'{')
                before=[hashlib.sha256(p.read_bytes()).hexdigest() for p in (manager.db,project.db)]
                with self.assertRaises(ResearchError):manager.preview_staged_feedback_plan(body)
                self.assertEqual(before,[hashlib.sha256(p.read_bytes()).hexdigest() for p in (manager.db,project.db)])

    def test_plan_three_and_unknown_current_feedback_stop(self):
        from autoresearch import project_selection
        manager,project,feedback,body=self.fixture();state=project.status()
        project.save_plan(request_id='plan-3',expected_state_version=state['state_version'],
                          plan={'question':'Another?','basis':'Test','steps':'Observe','expected_feedback':'Later'},reason='Synthetic revision')
        body['snapshot_ref']=project.status()['snapshot_ref']
        with self.assertRaises(ResearchError):manager.preview_staged_feedback_plan(body)
        manager,project,feedback,body=self.fixture();original=ProjectController._selection_context
        def unknown(controller,state,need,**kwargs):
            context=original(controller,state,need,**kwargs)
            context['hypothesis_feedback']['items'][0]['outcome']='unknown'
            return project_selection.seal_context({k:v for k,v in context.items() if k!='context_sha256'})
        before=[hashlib.sha256(p.read_bytes()).hexdigest() for p in (manager.db,project.db)]
        with patch.object(ProjectController,'_selection_context',unknown):
            with self.assertRaises(ResearchError):manager.preview_staged_feedback_plan(body)
        self.assertEqual(before,[hashlib.sha256(p.read_bytes()).hexdigest() for p in (manager.db,project.db)])

    def test_another_primary_or_unbound_audit_stops(self):
        from autoresearch.contracts import canonical
        for command in (staged.TOOL_ID,staged.AUDIT_TOOL_ID):
            with self.subTest(command=command):
                manager,project,feedback,body=self.fixture();state=project.status()
                source=next(a for a in state['actions'] if a['id']==feedback['primary_action_id'])
                fake=copy.deepcopy(source);fake.update(id='synthetic-other-action',request_id='synthetic-other-request',command=command)
                with project._connect() as con:
                    con.execute('INSERT INTO actions VALUES(?,?,?)',(fake['request_id'],fake['request_sha256'],canonical(fake)))
                body['snapshot_ref']=project.status()['snapshot_ref']
                before=[hashlib.sha256(p.read_bytes()).hexdigest() for p in (manager.db,project.db)]
                with self.assertRaises(ResearchError):manager.preview_staged_feedback_plan(body)
                self.assertEqual(before,[hashlib.sha256(p.read_bytes()).hexdigest() for p in (manager.db,project.db)])

    def test_direct_same_primary_new_id_reuses_not_dispatches(self):
        manager,project,feedback,body=self.fixture();before=project.status()
        with patch.object(staged,'execute',side_effect=AssertionError('must not rerun primary')):
            result=project.step(request_id='other-primary-id',expected_state_version=before['state_version'])
        after=project.status()
        self.assertTrue(result['reused']);self.assertEqual(len(after['actions']),len(before['actions']))
        self.assertEqual(after['budget'],before['budget'])
        with project._connect(readonly=True) as con:
            self.assertIsNotNone(con.execute('SELECT 1 FROM replays WHERE request_id=?',('other-primary-id',)).fetchone())
        body['snapshot_ref']=after['snapshot_ref'];result=self.checked_preview(manager,project,body)
        self.assertEqual(result['decision'],'wait')

    def test_empty_lock_is_filled_and_dangling_sidecar_stops(self):
        manager,project,feedback,body=self.fixture()
        lock=project.root/'writer.lock';lock.write_bytes(b'')
        self.checked_preview(manager,project,body)
        self.assertEqual(lock.stat().st_size,1)
        sidecar=Path(str(project.db)+'-wal');sidecar.symlink_to(project.root/'does-not-exist')
        before=hashlib.sha256(project.db.read_bytes()).hexdigest()
        with self.assertRaises(ResearchError):manager.preview_staged_feedback_plan(body)
        self.assertTrue(sidecar.is_symlink());self.assertEqual(hashlib.sha256(project.db.read_bytes()).hexdigest(),before)

    def test_same_explicit_posthoc_rule_yields_distinct_known_outcomes(self):
        rule={'schema_version':'staged-feedback-preview-rule-v1','condition_met':'audit',
              'condition_not_met':'wait','posthoc_acknowledged':True}
        for outcome,expected in [('met','suggest_audit'),('not_met','wait')]:
            with self.subTest(outcome=outcome):
                manager,project,feedback,body=self.fixture(outcome=outcome);body['posthoc_rule']=rule
                value=self.checked_preview(manager,project,body)
                self.assertEqual(value['feedback_outcome'],'condition_'+outcome)
                self.assertEqual(value['decision'],expected)
                self.assertEqual(value['rule_scope'],'caller_declared_posthoc_not_extracted_from_plan')

    def test_host_journal_changes_between_first_hash_and_status_stop(self):
        from autoresearch.host_model_selection import HostModelSelection
        from autoresearch.contracts import canonical
        manager,project,feedback,body=self.fixture();original=HostModelSelection.status;calls=[]
        def drift(host,*args,**kwargs):
            calls.append(1)
            if len(calls)==1:
                host.directory.mkdir(exist_ok=True)
                host.state_file.write_text(canonical({'schema_version':'host-model-selections-v1','project_id':project.status()['id'],
                                                     'grant':None,'requests':{},'synthetic_note':'changed'}))
            return original(host,*args,**kwargs)
        before=[hashlib.sha256(p.read_bytes()).hexdigest() for p in (manager.db,project.db)]
        with patch.object(HostModelSelection,'status',drift):
            with self.assertRaises(ResearchError):manager.preview_staged_feedback_plan(body)
        self.assertEqual(before,[hashlib.sha256(p.read_bytes()).hexdigest() for p in (manager.db,project.db)])
