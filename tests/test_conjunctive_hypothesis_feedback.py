"""Two preregistered staged validation predicates; synthetic engineering only."""
import base64
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import test_retrieval_holdout as fixtures
import test_hypothesis_feedback as legacy_fixtures
from autoresearch import (hypothesis_feedback as feedback, feedback_policy, staged_feedback_reader as reader,
                          staged_relevance_adapter as staged, retrieval_holdout as holdout, project_selection)
from autoresearch.contracts import ResearchError, canonical, fingerprint
from autoresearch.local_workbench import LocalWorkbench
from autoresearch.project_controller import ProjectController
from autoresearch.research_project import ResearchProject


class ConjunctiveFeedbackTests(unittest.TestCase):
    def fixture(self, sign=None, *, first='gt', second='gte', second_threshold=0, execute=True):
        temp = self.enterContext(tempfile.TemporaryDirectory())
        helper = fixtures.RetrievalHoldoutTests(); self.addCleanup(helper.doCleanups)
        original, _, private = helper.fixture(sign)
        manager = LocalWorkbench(Path(temp) / 'manager')
        imported = manager.import_project(request_id='import', workspace=original.root)
        project_id = imported['project_id']; manager.select({'request_id':'select','project_id':project_id})
        project, _ = manager.binding()
        manager.register_holdout({'request_id':'holdout','project_id':project_id,
            'expected_state_version':project.status()['state_version'], 'holdout_base64':base64.b64encode(private).decode()})
        controller = ProjectController(project.root); context = controller.selection_context()
        candidate = next(c for c in context['candidates'] if c['method_id'] == staged.TOOL_ID)
        hypothesis = {'candidate_id':candidate['id'], 'controller_request_id':'future',
            'conditions':[{'metric':'recall@20','operator':first,'threshold':0},
                          {'metric':'mrr@10','operator':second,'threshold':second_threshold}],
            'branches':{'condition_met':{'kind':'method','method_id':staged.AUDIT_TOOL_ID},
                        'condition_not_met':{'kind':'wait'}}}
        version = context['state_version']; budget = copy.deepcopy(project.status()['budget'])
        record = project.register_hypothesis(request_id='prediction',expected_state_version=version,hypothesis=hypothesis)
        self.assertEqual(project.status()['budget'],budget)
        if execute:
            context = controller.selection_context()
            proposal = {'schema_version':'project-selection-proposal-v1','context_sha256':context['context_sha256'],
                'provider':{'kind':'human','label':'Synthetic fixture'},'choice':{'kind':'execute','candidate_id':candidate['id']},
                'rationale':'Run preregistered engineering pair.','evidence_citation_ids':[]}
            controller.advance_selection(request_id='future',expected_state_version=context['state_version'],proposal=proposal)
        return manager,project,record,hypothesis,version

    def test_zero_and_joint_truth_and_single_checked_source(self):
        for first, second, expected in [('gt','gte','condition_not_met'),('gte','gte','condition_met'),('gte','gt','condition_not_met')]:
            with self.subTest(first=first,second=second):
                _, project, record, _, _ = self.fixture(None,first=first,second=second)
                self.assertEqual(record['schema_version'],'hypothesis-registration-v2')
                with patch.object(reader,'_checked_primary',wraps=reader._checked_primary) as checked:
                    context=feedback.feedback_context(project,project.status())
                    self.assertEqual(checked.call_count,1)
                item=context['items'][0]
                self.assertEqual(context['schema_version'],'hypothesis-feedback-context-v2')
                self.assertEqual(item['value'],[0,0]); self.assertEqual(item['outcome'],expected)
                self.assertEqual(feedback.validate_context(context),context)
                self.assertIn('both registered validation predicates',project_selection.hypothesis_notice({'hypothesis_feedback':context}))

    def test_unknown_is_all_or_nothing_and_no_rescoring(self):
        _,project,_,_,_=self.fixture('positive')
        before=project.status()
        for bad in ([0,None],[0,True],[0,float('nan')],[0,float('inf')],[0],None):
            with self.subTest(bad=bad), patch.object(reader,'read_validation_deltas',return_value=bad):
                item=feedback.feedback_context(project,before)['items'][0]
                self.assertEqual((item['outcome'],item['value'],item['action_id'],item['result_sha256']),('unknown',None,None,None))
                self.assertEqual(item['unknown_reason'],'invalid_saved_metric')
        action=before['actions'][0]; original=project._artifact(action).read_bytes()
        try:
            env=json.loads(original); env['tool_result']['result']['rankings'][0]['query_line']+=1
            project._artifact(action).write_text(canonical(env))
            item=feedback.feedback_context(project,project.status())['items'][0]
            self.assertEqual(item['outcome'],'unknown'); self.assertIsNone(item['value'])
        finally: project._artifact(action).write_bytes(original)
        self.assertEqual(project.status(),before)

    def test_replay_conditions_and_frozen_context_reject_malformed_values(self):
        _,project,record,hypothesis,version=self.fixture(None)
        reopened=ResearchProject(project.root)
        self.assertEqual(reopened.register_hypothesis(request_id='prediction',expected_state_version=version,hypothesis=hypothesis),record)
        changed=copy.deepcopy(hypothesis);changed['conditions'][1]['threshold']=1
        with self.assertRaises(ResearchError) as error:
            reopened.register_hypothesis(request_id='prediction',expected_state_version=version,hypothesis=changed)
        self.assertEqual(error.exception.code,'IDEMPOTENCY_CONFLICT')
        context=feedback.feedback_context(reopened,reopened.status())
        for bad in ([0,True],[0,None],[0,float('nan')],[0],0):
            v=copy.deepcopy(context);v['items'][0]['value']=bad
            with self.subTest(bad=bad),self.assertRaises(ResearchError):feedback.validate_context(v)
        changed=copy.deepcopy(context);changed['items'][0]['condition']['all'][0]['threshold']=False
        with self.assertRaises(ResearchError):feedback.validate_context(changed)
        changed=copy.deepcopy(context);changed['schema_version']='hypothesis-feedback-context-v1'
        with self.assertRaises(ResearchError):feedback.validate_context(changed)
        for mutation in ('duplicate','mixed','too_few','bool','unknown_metric','extra'):
            invalid=copy.deepcopy(hypothesis)
            if mutation=='duplicate':invalid['conditions'][1]['metric']=invalid['conditions'][0]['metric']
            if mutation=='mixed':invalid['metric']='recall@20'
            if mutation=='too_few':invalid['conditions'].pop()
            if mutation=='bool':invalid['conditions'][0]['threshold']=True
            if mutation=='unknown_metric':invalid['conditions'][0]['metric']='test/recall@20'
            if mutation=='extra':invalid['conditions'][0]['split']='test'
            invalid['controller_request_id']='different'
            with self.subTest(mutation=mutation),self.assertRaises(ResearchError):
                reopened.register_hypothesis(request_id='invalid',expected_state_version=reopened.status()['state_version'],hypothesis=invalid)

    def test_unknown_and_false_wait_vs_met_audit_original_s052(self):
        for sign,first,second_threshold,expected in [('positive','gt',1,'waiting'),('positive','gt',-1,'done')]:
            with self.subTest(expected=expected):
                manager,project,_,_,_=self.fixture(sign,first=first,second_threshold=second_threshold)
                state=project.status();body={'request_id':'continue','project_id':state['id'],
                  'expected_state_version':state['state_version'],'primary_action_id':state['actions'][0]['id'],
                  'reason':'Synthetic fixed policy continuation','registration_request_id':'prediction'}
                result=manager.continue_staged(body)
                self.assertEqual(result['phase'],expected)
                self.assertEqual(manager.continue_staged(body),result)
                after=project.status()
                self.assertEqual(after['budget']['local_tool_calls_used'],3 if expected=='done' else 1)
                self.assertEqual((after['budget']['new_fits'],after['budget']['new_model_requests']),(0,0))
                if expected=='done':
                    self.assertEqual([a['command'] for a in after['actions']],[staged.TOOL_ID,staged.AUDIT_TOOL_ID,holdout.FINAL_TOOL_ID])
                else:self.assertEqual(after,state)

    def test_registration_comparison_preserves_v1_and_exact_v2(self):
        _, project, joint, _, _ = self.fixture(None, execute=False)
        ctx = ProjectController(project.root).selection_context()
        candidate = next(c for c in ctx['candidates'] if c['method_id'] == staged.TOOL_ID)
        scalar = {'candidate_id':candidate['id'], 'controller_request_id':'scalar-future',
                  'metric':'recall@20','operator':'gte','threshold':0}
        v1 = project.register_hypothesis(request_id='scalar-prediction', expected_state_version=ctx['state_version'], hypothesis=scalar)
        v1_changed=copy.deepcopy(v1);v1_changed['condition']['threshold']=0.0
        v1_changed['registration_sha256']=fingerprint({k:v for k,v in v1_changed.items() if k!='registration_sha256'})
        feedback._check_record(v1_changed)  # Historical v1 Python numeric equivalence.
        v2_changed=copy.deepcopy(joint);v2_changed['condition']['all'][0]['threshold']=0.0
        v2_changed['registration_sha256']=fingerprint({k:v for k,v in v2_changed.items() if k!='registration_sha256'})
        with self.assertRaises(ResearchError):feedback._check_record(v2_changed)

    def test_resealed_context_numeric_type_does_not_change_registered_condition(self):
        _, project, record, _, _ = self.fixture('positive', second_threshold=-1)
        context = ProjectController(project.root).selection_context()
        provider = {'kind':'human','label':'Synthetic fixture'}
        actual = feedback_policy.select_from_feedback(context, registration=record, provider=provider)
        self.assertEqual(actual['choice']['kind'], 'execute')
        changed = copy.deepcopy(context)
        changed['hypothesis_feedback']['items'][0]['condition']['all'][0]['threshold'] = 0.0
        changed.pop('context_sha256')
        resealed = project_selection.seal_context(changed)
        proposal = feedback_policy.select_from_feedback(resealed, registration=record, provider=provider)
        self.assertEqual(proposal['choice']['kind'], 'wait')
        self.assertEqual(proposal['rationale'], 'Feedback policy waits: original bound feedback is unavailable or changed.')

    def test_mixed_scalar_and_joint_records_preserve_each_condition(self):
        _, project, joint, _, _ = self.fixture(None, execute=False)
        current = ProjectController(project.root).selection_context()
        candidate = next(c for c in current['candidates'] if c['method_id'] == staged.TOOL_ID)
        scalar = {'candidate_id':candidate['id'], 'controller_request_id':'scalar-future',
                  'metric':'recall@20','operator':'gte','threshold':0}
        saved = project.register_hypothesis(request_id='scalar-prediction', expected_state_version=current['state_version'], hypothesis=scalar)
        result = feedback.feedback_context(project, project.status())
        self.assertEqual(result['schema_version'], 'hypothesis-feedback-context-v2')
        items = {item['request_id']:item for item in result['items']}
        self.assertEqual(items['prediction']['condition'],joint['condition'])
        self.assertEqual(items['scalar-prediction']['condition'],saved['condition'])
        self.assertEqual([item['outcome'] for item in result['items']],['unknown','unknown'])
        self.assertEqual(feedback.validate_context(result),result)
        changed=copy.deepcopy(result);changed['items'][1]['candidate']['method_id']='research.other'
        with self.assertRaises(ResearchError):feedback.validate_context(changed)
        changed=copy.deepcopy(result);changed['items'].pop(0)
        with self.assertRaises(ResearchError):feedback.validate_context(changed)

    def test_legacy_family_rejects_joint_registration(self):
        helper=legacy_fixtures.HypothesisFeedbackTests();self.addCleanup(helper.doCleanups)
        project,candidate=helper.fixture()
        hypothesis={'candidate_id':candidate['id'],'controller_request_id':'future','conditions':[
            {'metric':'recall@20','operator':'gt','threshold':0},{'metric':'mrr@10','operator':'gte','threshold':0}]}
        before=project.status()
        with self.assertRaises(ResearchError):project.register_hypothesis(request_id='prediction',expected_state_version=before['state_version'],hypothesis=hypothesis)
        self.assertEqual(project.status(),before)
