"""Synthetic recovery chain: completed child and unresolved original parent."""
import unittest
from unittest.mock import patch

import test_tabular_quality_feedback as fixture
import test_research_recipe as recipe_fixture
from autoresearch import research_project, tabular_quality_adapter as tabular
from autoresearch.contracts import ResearchError
from autoresearch.plan_readiness import assess_plan_readiness
from autoresearch.project_controller import ProjectController
from autoresearch.research_plan_proposal import build_context
from autoresearch.research_project import ResearchProject


class UnknownParentTests(unittest.TestCase):
    def setUp(self):
        self.f=fixture.QualityFeedbackTests(methodName='runTest');self.f.setUp();self.addCleanup(self.f.doCleanups)
        self.f.register(target='original-parent')
        self.project=self.f.project;self.controller=self.f.controller
        ctx=self.controller.selection_context();self.before_version=ctx['state_version']
        self.proposal={'schema_version':'project-selection-proposal-v1','context_sha256':ctx['context_sha256'],
            'provider':{'kind':'human','label':'synthetic'},'choice':{'kind':'execute','candidate_id':self.f.candidate['id']},
            'rationale':'Synthetic saved-result recovery','evidence_citation_ids':[]}

    def make_unknown_parent_with_completed_child(self):
        pending=[]
        def delayed(path,envelope):
            pending.append((path,envelope));raise KeyboardInterrupt('delay synthetic result publication')
        with patch.object(research_project,'write_once',side_effect=delayed),self.assertRaises(KeyboardInterrupt):
            self.controller.advance_selection(request_id='original-parent',proposal=self.proposal,
                                              expected_state_version=self.before_version)
        self.assertEqual(len(pending),1)
        unknown=self.controller.advance_selection(request_id='original-parent',proposal=self.proposal,
                                                  expected_state_version=self.before_version)
        self.assertEqual(unknown['status'],'unknown')
        parent=self.project.status()['controller_requests'][-1]
        research_project.write_once(*pending[0])
        with patch.object(tabular,'execute',side_effect=AssertionError('must not execute again')):
            child=self.project.step(request_id=parent['child_request_id'])
        self.assertEqual(child['status'],'completed')
        state=self.project.status()
        self.assertEqual(state['controller_requests'][-1]['status'],'unknown')
        self.assertEqual([a['status'] for a in state['actions']],['completed'])
        self.assertEqual(state['budget']['local_tool_calls_used'],1)
        return state

    def assert_error(self,code,fn,**kwargs):
        with self.assertRaises(ResearchError) as err:fn(**kwargs)
        self.assertEqual(err.exception.code,code)

    def test_preview_and_plan_context_report_unknown_as_blocker(self):
        state=self.make_unknown_parent_with_completed_child()
        context=self.controller.selection_context()
        self.assertEqual([b['code'] for b in context['blockers']],['EXECUTION_UNKNOWN'])
        self.assertEqual(context['candidates'],[])
        readiness=assess_plan_readiness(build_context(self.project))
        self.assertEqual(readiness['execution_status'],'blocked')
        self.assertEqual([b['code'] for b in readiness['blockers']],['EXECUTION_UNKNOWN'])
        self.assertEqual(self.controller.next()['status'],'needs_review')
        self.assertEqual(self.project.status(),state)

    def test_writer_rejects_new_selection_default_recipe_and_quality_policy(self):
        state=self.make_unknown_parent_with_completed_child();before=self.project.db.read_bytes()
        with patch.object(ProjectController,'_dispatch',side_effect=AssertionError('must not dispatch')), \
             patch.object(ResearchProject,'step',side_effect=AssertionError('must not step')):
            self.assert_error('EXECUTION_UNKNOWN',self.controller.advance_selection,request_id='new-selection',
                              proposal=self.proposal,expected_state_version=state['state_version'])
            self.assert_error('EXECUTION_UNKNOWN',self.controller.advance,request_id='new-default',
                              expected_state_version=state['state_version'])
            self.assert_error('EXECUTION_UNKNOWN',self.controller.advance_recipe,request_id='new-recipe',
                              recipe=recipe_fixture.recipe(),expected_state_version=state['state_version'])
            self.assert_error('EXECUTION_UNKNOWN',self.controller.advance_tabular_quality_feedback,
                              request_id='new-policy',registration_request_id='reg',expected_state_version=state['state_version'])
            self.assert_error('EXECUTION_UNKNOWN',self.controller.advance_tabular_quality_feedback_v2,
                              request_id='new-policy-v2',registration_request_id='reg',plan_request_id='plan',
                              plan_sha256='a'*64,expected_state_version=state['state_version'])
        self.assertEqual(self.project.db.read_bytes(),before);self.assertEqual(self.project.status(),state)

    def test_original_id_can_reconcile_without_second_tool(self):
        state=self.make_unknown_parent_with_completed_child()
        with patch.object(tabular,'execute',side_effect=AssertionError('must not execute again')):
            result=self.controller.advance_selection(request_id='original-parent',proposal=self.proposal,
                                                     expected_state_version=self.before_version)
        after=self.project.status()
        self.assertEqual(result['status'],'completed');self.assertTrue(result['replayed'])
        self.assertEqual(len(after['actions']),1);self.assertEqual(after['budget'],state['budget'])
        self.assertEqual(after['controller_requests'][-1]['status'],'completed')
        self.assertTrue(any(c['method_id']=='data.numeric-association' for c in self.controller.selection_context()['candidates']))


if __name__=='__main__':unittest.main()
