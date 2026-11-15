"""Synthetic HTTP wiring for saved staged successor preview; no real study/model."""
import hashlib
import unittest
from unittest.mock import patch
from autoresearch.contracts import fingerprint
from autoresearch.project_controller import ProjectController
from autoresearch.research_project import ResearchProject
import test_local_workbench_http as http_fixture
import test_staged_successor_preview as fixture


class StagedSuccessorPreviewHTTPTests(unittest.TestCase):
    serve=http_fixture.LocalWorkbenchHTTPTests.serve
    request=http_fixture.LocalWorkbenchHTTPTests.request
    session=http_fixture.LocalWorkbenchHTTPTests.session

    def setup_preview(self,branch='wait'):
        manager,project,feedback,body=fixture.StagedSuccessorPreviewTests.fixture(self,branch)
        server=self.serve(local_workspace=manager,allow_local_actions=True)
        return manager,project,feedback,body,server,self.session(server)

    def test_projection_and_real_post_remain_bound_and_read_only(self):
        manager,project,feedback,body,server,headers=self.setup_preview()
        status,view=self.request(server,'/api/project');self.assertEqual(status,200)
        identity=view['staged_successor_plan_identity'];self.assertEqual(identity['plan_sha256'],body['plan_sha256'])
        self.assertEqual(identity['verification'],'state_fields_only_not_claim_sql_or_artifacts')
        self.assertEqual(identity['primary_action_id'],feedback['primary_action_id'])
        self.assertEqual(identity['plan_sha256'],fingerprint(project.status()['plan_revisions'][-1]))
        state=project.status();before=[hashlib.sha256(p.read_bytes()).hexdigest() for p in (manager.db,project.db)]
        with patch.object(ProjectController,'_dispatch',side_effect=AssertionError('no dispatch')), \
             patch.object(ResearchProject,'step',side_effect=AssertionError('no action')):
            status,response=self.request(server,'/api/local-workbench/staged-feedback-plan-preview','POST',body,headers)
        self.assertEqual(status,200);self.assertEqual(response['decision'],'wait');self.assertFalse(response['may_execute'])
        self.assertEqual(response['context_sha256'],self.request(server,'/api/project/selection-context.json')[1]['context_sha256'])
        self.assertEqual(response['registration_sha256'],identity['registration_sha256'])
        self.assertEqual(before,[hashlib.sha256(p.read_bytes()).hexdigest() for p in (manager.db,project.db)])
        self.assertEqual(state['budget'],project.status()['budget'])

    def test_post_origin_csrf_and_snapshot_gates(self):
        manager,project,feedback,body,server,headers=self.setup_preview()
        state=project.status()
        for changed in ({**headers,'Origin':'http://external.invalid'},{**headers,'X-AutoResearch-CSRF':'bad'}):
            self.assertEqual(self.request(server,'/api/local-workbench/staged-feedback-plan-preview','POST',body,changed)[0],403)
        stale={**body,'snapshot_ref':'0'*64}
        self.assertNotEqual(self.request(server,'/api/local-workbench/staged-feedback-plan-preview','POST',stale,headers)[0],200)
        self.assertEqual(project.status(),state)

    def test_readonly_service_does_not_offer_post(self):
        manager,project,feedback,body,server,headers=self.setup_preview()
        readonly=self.serve(local_workspace=manager,allow_local_actions=False)
        self.assertEqual(self.request(readonly,'/api/local-workbench/staged-feedback-plan-preview','POST',body,{'Content-Type':'application/json'})[0],405)

    def test_existing_unlinked_plan_does_not_gain_preview_projection(self):
        import test_staged_hypothesis_workbench as hypotheses
        helper=hypotheses.StagedHypothesisWorkbenchTests();self.addCleanup(helper.doCleanups)
        manager,project,body=helper.fixture()
        server=self.serve(local_workspace=manager,allow_local_actions=True)
        status,view=self.request(server,'/api/project')
        self.assertEqual(status,200);self.assertIsNotNone(view['research_plan']['current'])
        self.assertNotIn('staged_successor_plan_identity',view)
