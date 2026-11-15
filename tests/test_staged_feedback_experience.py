"""Synthetic three-tool feedback histories imported without new scientific actions."""
from contextlib import ExitStack
import copy
import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import test_feedback_selected_holdout as feedback_fixtures
import test_retrieval_holdout as target_fixtures
import test_staged_project_experience as experience_fixtures
from autoresearch import (staged_project_experience as experience, project_experience_dispatch as dispatch,
                          staged_relevance_adapter as staged, retrieval_holdout as holdout,
                          retrieval_lexical as lexical, project_controller, project_report, research_plan_proposal)
from autoresearch.contracts import ResearchError, canonical, fingerprint
from autoresearch.project_controller import ProjectController
from autoresearch.research_project import ResearchProject
from autoresearch.research_memory import observation_id


class StagedFeedbackExperienceTests(unittest.TestCase):
    def source(self, *, notmet=False, hypothesis_mode='joint', negative=False):
        helper=feedback_fixtures.FeedbackSelectedHoldoutTests();helper.addCleanup=self.addCleanup
        manager,project,_,_,_=helper.fixture(threshold=1 if notmet else 0,audit_notmet=notmet,hypothesis_mode=hypothesis_mode,negative=negative)
        state=project.status();primary=state['actions'][0]['id']
        request={'request_id':'continue','project_id':state['id'],'expected_state_version':state['state_version'],
                 'primary_action_id':primary,'reason':'Synthetic experience fixture','registration_request_id':'prediction'}
        receipt=manager.continue_staged(request)
        self.assertEqual((receipt['status'],receipt['phase']),('completed','done'))
        self.assertEqual(project.status()['budget']['local_tool_calls_used'],3)
        return project,primary

    def bundle(self, project, primary):
        before=project.status();digest=hashlib.sha256(project.db.read_bytes()).hexdigest()
        memory=experience.StagedExperienceMemory(Path(self.enterContext(tempfile.TemporaryDirectory()))/'memory')
        with ExitStack() as guards:
            original=Path.open
            def refuse_private(path,*args,**kwargs):
                if 'private_evaluation' in path.parts:raise AssertionError('private holdout accessed during capture')
                return original(path,*args,**kwargs)
            guards.enter_context(patch.object(Path,'open',refuse_private))
            guards.enter_context(patch.object(project_controller,'code_identity',return_value='f'*64))
            for obj,name in ((lexical,'retrieve'),(lexical,'metrics'),(lexical,'build_index'),
                             (staged,'execute'),(holdout,'_verified_private'),(ResearchProject,'step'),
                             (ProjectController,'advance_selection')):
                guards.enter_context(patch.object(obj,name,side_effect=AssertionError('no dispatch or recomputation')))
            receipt=memory.import_project(project.root,primary)
            self.assertEqual(memory.import_project(project.root,primary)['inserted'],0)
            record=memory.recall(receipt['scope'])['entries'][0]['record']
            bundle=memory.export_case(receipt['scope'],record['id'],case_id='feedback-history',version=1,
                                     method_card=experience_fixtures.StagedExperienceTests.card(),limitations=['Synthetic case only.'])
        self.assertEqual(project.status(),before)
        self.assertEqual(hashlib.sha256(project.db.read_bytes()).hexdigest(),digest)
        self.assertEqual(bundle['schema_version'],experience.SCHEMA_V2)
        self.assertEqual(dispatch.parse_bundle(canonical(bundle).encode()),bundle)
        return bundle

    def test_both_branches_capture_and_bind_to_target_without_new_action(self):
        for notmet in (False,True):
            with self.subTest(notmet=notmet):
                source,primary=self.source(notmet=notmet);bundle=self.bundle(source,primary)
                view=dispatch.summary(bundle);feedback=view['observation']['preregistered_feedback']
                self.assertEqual(feedback['registration_schema_version'],'hypothesis-registration-v2')
                self.assertEqual(feedback['outcome'],'condition_not_met' if notmet else 'condition_met')
                self.assertEqual(view['observation']['final']['selected_method'],'bm25' if notmet else 'tfidf_cosine')
                self.assertEqual(feedback['value'][0],0)
                self.assertIn('offline_policy_binding_unverifiable_without_origin',feedback['verification'])
                if notmet:self.assertEqual(view['observation']['final']['comparison_status'],'selected_equals_baseline_single_computation')
                raw=canonical(bundle)
                for forbidden in ('SECRET_FINAL','final-q',hashlib.sha256(b'final-q').hexdigest(),'queries_jsonl','qrels_tsv'):
                    self.assertNotIn(forbidden,raw)
                helper=target_fixtures.RetrievalHoldoutTests();self.addCleanup(helper.doCleanups)
                target,_,_=helper.fixture();controller=ProjectController(target.root)
                initial=controller.selection_context();state=target.status()
                body={'request_id':'import-history','expected_state_version':state['state_version'],
                      'bundle':raw.encode(),'reason':'Synthetic historical reference.'}
                revision=target.import_experience(**body);after=target.status()
                self.assertEqual(target.import_experience(**body),revision)
                context=controller.selection_context()
                for key in ('budget','candidates','conditions','evidence','baseline_decision'):
                    self.assertEqual(context[key],initial[key],key)
                self.assertEqual(context['experience']['cases'][0]['observation']['preregistered_feedback'],feedback)
                plan_context=research_plan_proposal.build_context(target)
                self.assertEqual(plan_context['selection_context']['experience']['cases'][0]['observation']['preregistered_feedback'],feedback)
                self.assertIn(feedback['registration_sha256'],research_plan_proposal.build_prompt(plan_context)['prompt'])
                report=Path(self.enterContext(tempfile.TemporaryDirectory()))/'report'
                project_report.export_report(workspace=target.root,output=report)
                text=(report/'report.md').read_text()
                self.assertIn('原事前反馈条件',text);self.assertIn(feedback['outcome'],text)
                self.assertEqual(target.status(),after)

    def test_tampered_saved_feedback_and_audit_candidate_rejected(self):
        source,primary=self.source();bundle=self.bundle(source,primary)
        changed=copy.deepcopy(bundle);changed['record']['provenance']['feedback_history']['feedback']['value'][1]=0.5
        with self.assertRaises(ResearchError):dispatch.validate_bundle(changed)
        changed=copy.deepcopy(bundle);p=changed['record']['provenance'];hist=p['feedback_history'];parent=p['parent_bindings']['audit']
        hist['audit_proposal']['choice']['candidate_id']='choice-'+'a'*32
        parent['request_sha256']=fingerprint({'project_id':p['origin']['project_id'],'command':'controller.advance_selection',
            'need':'next_check','expected_state_version':parent['state_version_before'],'proposal':hist['audit_proposal']})
        with self.assertRaises(ResearchError):dispatch.validate_bundle(changed)
        changed=copy.deepcopy(bundle);changed['schema_version']=experience.SCHEMA
        with self.assertRaises(ResearchError):dispatch.validate_bundle(changed)
        changed=copy.deepcopy(bundle);r=changed['record'];p=r['provenance'];f=p['freeze']
        self.assertEqual(f['validation_delta_recall20'],0)
        f['validation_delta_recall20']=False
        f['record_sha256']=fingerprint({k:v for k,v in f.items() if k!='record_sha256'})
        a=p['actions'];r['scope']['inputs_sha256']=fingerprint({'primary':a['primary']['result_sha256'],
             'audit':a['audit']['result_sha256'],'final':a['final']['result_sha256'],
             'source':fingerprint(p['source']),'freeze':f['record_sha256']})
        r['id']=observation_id(r)
        with self.assertRaises(ResearchError):dispatch.validate_bundle(changed)
        changed=copy.deepcopy(bundle);r=changed['record'];p=r['provenance'];hist=p['feedback_history'];reg=hist['registration']
        candidate={'method_id':staged.TOOL_ID,'parameters':{'invented':1},'evaluation_ref':reg['candidate']['evaluation_ref']}
        reg['candidate']={'id':'choice-'+fingerprint(candidate)[:32],**candidate}
        reg['request']['hypothesis']['candidate_id']=reg['candidate']['id'];reg['request_sha256']=fingerprint(reg['request'])
        reg['registration_sha256']=fingerprint({k:v for k,v in reg.items() if k!='registration_sha256'})
        hist['feedback']['candidate']=copy.deepcopy(reg['candidate']);hist['feedback']['registration_sha256']=reg['registration_sha256']
        p['freeze']['feedback_binding']['registration_sha256']=reg['registration_sha256']
        p['freeze']['record_sha256']=fingerprint({k:v for k,v in p['freeze'].items() if k!='record_sha256'})
        a=p['actions'];r['scope']['inputs_sha256']=fingerprint({'primary':a['primary']['result_sha256'],
             'audit':a['audit']['result_sha256'],'final':a['final']['result_sha256'],
             'source':fingerprint(p['source']),'freeze':p['freeze']['record_sha256']})
        r['id']=observation_id(r)
        with self.assertRaises(ResearchError):dispatch.validate_bundle(changed)

    def test_execution_still_rejects_changed_project_code(self):
        helper=target_fixtures.RetrievalHoldoutTests();self.addCleanup(helper.doCleanups)
        project,_,_=helper.fixture();before=project.status()
        with patch('autoresearch.research_project.code_identity',return_value='e'*64):
            with self.assertRaises(ResearchError) as caught:
                project.step(request_id='changed-code',expected_state_version=before['state_version'])
        self.assertEqual(caught.exception.code,'CODE_CHANGED')
        self.assertEqual(project.status(),before)

    def test_scalar_and_leave_one_out_registrations_retain_exact_values(self):
        for mode,expected in (('scalar','hypothesis-registration-v1'),('loo','hypothesis-registration-v3')):
            with self.subTest(mode=mode):
                source,primary=self.source(hypothesis_mode=mode);bundle=self.bundle(source,primary)
                feedback=dispatch.summary(bundle)['observation']['preregistered_feedback']
                self.assertEqual(feedback['registration_schema_version'],expected)
                self.assertEqual(feedback['outcome'],'condition_met')
                if mode=='scalar':self.assertEqual(feedback['value'],0)
                else:self.assertEqual(feedback['value']['leave_one_out']['queries'],3)

    def test_negative_validation_is_retained_with_unmet_branch(self):
        source,primary=self.source(notmet=True,negative=True);bundle=self.bundle(source,primary)
        view=dispatch.summary(bundle)['observation'];feedback=view['preregistered_feedback']
        self.assertEqual(feedback['outcome'],'condition_not_met')
        self.assertLess(min(feedback['value']),0)
        self.assertEqual(view['final']['selected_method'],'bm25')
