"""Synthetic Project gates after original child recovery and unknown parent."""
from pathlib import Path
import unittest
from unittest.mock import patch

import test_unknown_controller_parent as fixture
from autoresearch import numeric_association_adapter, research_methods, source_evidence_adapter, tabular_quality_adapter
from autoresearch.contracts import ResearchError
from autoresearch.local_workbench import LocalWorkbench
from autoresearch.project_controller import ProjectController
from autoresearch.research_project import ResearchProject


class UnknownParentProjectGatesTests(unittest.TestCase):
    def stage(self, *, manager=False):
        helper=fixture.UnknownParentTests(methodName='runTest')
        # Preserve the Project's default eight source slots for limit tests.
        with patch.object(ResearchProject,'limit_evidence_budget',return_value=None):helper.setUp()
        self.addCleanup(helper.doCleanups)
        workbench=None
        if manager:
            workbench=LocalWorkbench(helper.f.root/'manager')
            project_id=helper.project.status()['id']
            workbench.import_project(request_id='import',workspace=helper.project.root)
            workbench.select({'request_id':'activate','project_id':project_id})
            helper.project,_=workbench.binding();helper.controller=ProjectController(helper.project.root)
        return helper,workbench

    def error(self,code,fn,**kwargs):
        with self.assertRaises(ResearchError) as caught:fn(**kwargs)
        self.assertEqual(caught.exception.code,code)

    def test_new_project_requests_stop_before_side_effects(self):
        h,_=self.stage();state=h.make_unknown_parent_with_completed_child();p=h.project
        before=p.db.read_bytes();files={str(x.relative_to(p.root)) for x in p.root.rglob('*')}
        option=next(x for x in research_methods.match_methods(state) if x['method_id']=='data.numeric-association')
        with patch.object(numeric_association_adapter,'execute',side_effect=AssertionError('new tool dispatch')), \
             patch.object(source_evidence_adapter,'execute',side_effect=AssertionError('source dispatch')), \
             patch.object(source_evidence_adapter,'capture_bundle',side_effect=AssertionError('capture')):
            self.error('EXECUTION_UNKNOWN',p.step,request_id='direct-next',method_id=option['method_id'],
                       parameters=option['parameters'],expected_state_version=state['state_version'])
            self.error('EXECUTION_UNKNOWN',p.read_evidence,request_id='new-source-read',receipt_snapshot_sha256='a'*64,
                       expected_state_version=state['state_version'])
            self.error('EXECUTION_UNKNOWN',p.register_evidence,request_id='new-source-register',bundle=Path('/synthetic/no-file'),
                       expected_state_version=state['state_version'])
            self.error('EXECUTION_UNKNOWN',p.extend_local_budget,request_id='new-budget',expected_limit=2,new_limit=3,
                       expected_state_version=state['state_version'],reason='Synthetic')
            self.error('EXECUTION_UNKNOWN',p.limit_evidence_budget,request_id='new-source-limit',expected_limit=8,new_limit=7,
                       expected_state_version=state['state_version'],reason='Synthetic')
            self.error('EXECUTION_UNKNOWN',p.upgrade,request_id='new-upgrade',expected_code_identity=state['code_identity'],evidence_read_limit=8)
        self.assertEqual(p.db.read_bytes(),before);self.assertEqual(p.status(),state)
        self.assertEqual({str(x.relative_to(p.root)) for x in p.root.rglob('*')},files)

    def test_original_revisions_and_child_replay_remain_readable(self):
        h,_=self.stage();p=h.project;state=p.status()
        budget_args={'request_id':'old-budget','expected_limit':2,'new_limit':3,'reason':'Synthetic',
                     'expected_state_version':state['state_version']}
        budget=p.extend_local_budget(**budget_args);state=p.status()
        limit_args={'request_id':'old-limit','expected_limit':8,'new_limit':7,'reason':'Synthetic',
                    'expected_state_version':state['state_version']}
        limit=p.limit_evidence_budget(**limit_args);state=p.status()
        upgrade_args={'request_id':'old-upgrade','expected_code_identity':state['code_identity'],'evidence_read_limit':7}
        upgrade=p.upgrade(**upgrade_args)
        ctx=h.controller.selection_context();h.before_version=ctx['state_version'];h.proposal['context_sha256']=ctx['context_sha256']
        state=h.make_unknown_parent_with_completed_child();before=p.db.read_bytes()
        self.assertEqual(p.extend_local_budget(**budget_args),budget)
        self.assertEqual(p.limit_evidence_budget(**limit_args),limit)
        self.assertEqual(p.upgrade(**upgrade_args),upgrade)
        child=state['controller_requests'][-1]['child_request_id']
        with patch.object(tabular_quality_adapter,'execute',side_effect=AssertionError('second tool')):
            self.assertEqual(p.step(request_id=child)['status'],'completed')
            result=h.controller.advance_selection(request_id='original-parent',proposal=h.proposal,expected_state_version=h.before_version)
        self.assertEqual(result['status'],'completed');after=p.status()
        self.assertEqual(after['budget'],state['budget']);self.assertEqual(len(after['actions']),1)
        self.assertNotEqual(p.db.read_bytes(),before)  # Only original parent reconciliation advances state.
        self.assertEqual(p.extend_local_budget(request_id='after-reconcile',expected_limit=3,new_limit=4,
                                               expected_state_version=after['state_version'],reason='Synthetic')['new_limit'],4)

    def test_prepared_parent_can_dispatch_first_child(self):
        h,_=self.stage();before=h.project.status()
        result=h.controller.advance_selection(request_id='original-parent',proposal=h.proposal,expected_state_version=h.before_version)
        self.assertEqual(result['status'],'completed');after=h.project.status()
        self.assertEqual(len(after['actions']),1);self.assertEqual(after['budget']['local_tool_calls_used'],1)
        self.assertEqual(before['budget']['local_tool_calls_used'],0)

    def test_manager_batch_and_continuation_do_not_create_new_intents(self):
        h,m=self.stage(manager=True);state=h.make_unknown_parent_with_completed_child();pid=state['id']
        common={'project_id':pid,'expected_state_version':state['state_version'],'max_actions':1,
                'allowed_methods':['data.numeric-association'],'source_receipt_sha256s':[],'reason':'Synthetic'}
        batch={**common,'request_id':'new-batch'}
        continuation={**common,'request_id':'new-continuation','plan_mode':'reuse','execution_mode':'rules'}
        before_project=h.project.db.read_bytes();before_manager=m.db.read_bytes()
        self.error('EXECUTION_UNKNOWN',m.batch,body=batch)
        self.error('EXECUTION_UNKNOWN',m.continue_research,body=continuation)
        self.assertEqual(h.project.db.read_bytes(),before_project);self.assertEqual(m.db.read_bytes(),before_manager)

    def test_original_source_registration_and_read_ids_survive_unknown_parent(self):
        from test_project_controller import ProjectControllerTests
        from autoresearch import research_project
        helper=ProjectControllerTests(methodName='runTest');helper.setUp();self.addCleanup(helper.doCleanups)
        folder,_=helper.bundle();project=helper.project
        registration=project.register_evidence(request_id='old-registration',bundle=folder)
        receipt=registration['receipt_snapshot_sha256'];controller=ProjectController(project.root);captured=[]
        def delayed(path,envelope):
            captured.append((path,envelope));raise KeyboardInterrupt('synthetic source publication delay')
        with patch.object(research_project,'write_once',side_effect=delayed),self.assertRaises(KeyboardInterrupt):
            controller.advance(request_id='original-source-parent')
        self.assertEqual(controller.advance(request_id='original-source-parent')['status'],'unknown')
        parent=project.status()['controller_requests'][-1];self.assertEqual(len(captured),1)
        research_project.write_once(*captured[0])
        child_id=parent['child_request_id']
        self.assertEqual(project.read_evidence(request_id=child_id,receipt_snapshot_sha256=receipt)['status'],'completed')
        state=project.status();self.assertEqual(state['controller_requests'][-1]['status'],'unknown')
        before=project.db.read_bytes()
        with patch.object(source_evidence_adapter,'execute',side_effect=AssertionError('source extraction repeated')):
            self.assertTrue(project.read_evidence(request_id=child_id,receipt_snapshot_sha256=receipt)['replayed'])
            self.assertTrue(project.register_evidence(request_id='old-registration',bundle=folder)['replayed'])
            self.error('EXECUTION_UNKNOWN',project.read_evidence,request_id='new-source-read',receipt_snapshot_sha256=receipt)
            self.error('EXECUTION_UNKNOWN',project.register_evidence,request_id='new-registration',bundle=folder)
            self.assertEqual(project.db.read_bytes(),before)
            self.assertEqual(controller.advance(request_id='original-source-parent')['status'],'completed')
        after=project.status();self.assertEqual(after['budget'],state['budget'])
        self.assertEqual(len(after['evidence_actions']),1)


if __name__=='__main__':unittest.main()
