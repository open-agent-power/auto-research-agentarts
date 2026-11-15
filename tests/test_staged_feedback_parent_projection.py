"""Only synthetic, state-only feedback identity projection."""
import copy
import unittest
from autoresearch.project_workbench import _projection
import test_staged_feedback_workbench as feedback_fixture

class StagedFeedbackParentProjectionTests(unittest.TestCase):
    def fixture(self, branch):
        helper=feedback_fixture.StagedFeedbackWorkbenchTests()
        self.addCleanup(helper.doCleanups)
        return helper.fixture(branch)
    def test_optional_projection_wait_and_audit(self):
        for branch in ('wait', 'audit'):
            with self.subTest(branch=branch):
                manager, project, body = self.fixture(branch)
                before=project.status()
                self.assertNotIn('staged_feedback_parents', _projection(project,before))
                result=manager.advance_staged_feedback(body)
                state=project.status(); view=_projection(project,state)['staged_feedback_parents']
                self.assertEqual(view['verification'],'state_fields_only_not_claim_sql_or_artifacts')
                self.assertEqual(view['snapshot_ref'],state['snapshot_ref'])
                self.assertEqual(len(view['items']),1)
                item=view['items'][0]
                self.assertEqual(item['registration_sha256'],body['registration_sha256'])
                self.assertEqual(item['registration_request_id'],body['registration_request_id'])
                self.assertEqual(item['primary_action_id'],body['primary_action_id'])
                self.assertEqual(item['status'],result['status'])
                self.assertEqual(item['child_request_id'],result['controller']['child_request_id'])
                self.assertNotIn('body',item)
                self.assertNotIn('manager_intent_sha256',item)
    def test_duplicate_or_corrupt_parent_is_unavailable(self):
        manager,project,body=self.fixture('wait');manager.advance_staged_feedback(body)
        state=project.status();duplicate=copy.deepcopy(state);duplicate['controller_requests'].append(copy.deepcopy(duplicate['controller_requests'][-1]))
        # Existing selection_view also rejects duplicated identities before projection.
        from autoresearch.contracts import ResearchError
        with self.assertRaises(ResearchError): _projection(project,duplicate)
        state['controller_requests'][-1]['staged_feedback_policy']['record_sha256']='0'*64
        view=_projection(project,state)['staged_feedback_parents']
        self.assertEqual(view['verification'],'unavailable');self.assertEqual(view['items'],[])
