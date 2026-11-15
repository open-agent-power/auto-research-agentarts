"""Synthetic optional staged registration projection; never executes research."""
import unittest

from autoresearch.contracts import ResearchError
from autoresearch import hypothesis_feedback
from autoresearch.project_workbench import _projection
from test_staged_hypothesis_workbench import StagedHypothesisWorkbenchTests


class StagedPrimaryProjectionTests(unittest.TestCase):
    def fixture(self):
        helper = StagedHypothesisWorkbenchTests()
        self.addCleanup(helper.doCleanups)
        return helper.fixture()

    def test_optional_metadata_and_plan_change(self):
        manager, project, body = self.fixture()
        self.assertNotIn('staged_primary_choices', _projection(project, project.status()))
        registration = manager.register_staged_hypothesis(body)['registration']
        state = project.status(); view = _projection(project, state)
        projection = view['staged_primary_choices']; item = projection['items'][0]
        self.assertEqual((projection['snapshot_ref'], projection['state_version']), (state['snapshot_ref'], state['state_version']))
        self.assertEqual(projection['verification'], 'registration_metadata_only')
        self.assertFalse(projection['manager_ownership_verified'])
        self.assertEqual(item['registration_sha256'], registration['registration_sha256'])
        self.assertEqual(item['controller_request_id'], registration['controller_request_id'])
        self.assertTrue(item['plan_matches'] and item['source_matches'] and item['code_matches'])
        self.assertNotIn('request', item)
        project.save_plan(request_id='later-plan', expected_state_version=state['state_version'],
            plan={'question':'Later?', 'basis':'synthetic', 'steps':'wait', 'expected_feedback':'none'}, reason='fixture')
        self.assertFalse(_projection(project, project.status())['staged_primary_choices']['items'][0]['plan_matches'])
        self.assertEqual(project.status()['actions'], [])

    def test_direct_registration_is_not_manager_claim(self):
        manager, project, body = self.fixture()
        registration = hypothesis_feedback.register(project, **{k:v for k,v in body.items() if k != 'project_id'})
        state = project.status(); projection = _projection(project, state)['staged_primary_choices']
        self.assertTrue(projection['items'][0]['plan_matches'])
        request = {'request_id':registration['controller_request_id'], 'project_id':state['id'], 'expected_state_version':state['state_version'],
                   'registration_request_id':registration['request_id'], 'registration_sha256':registration['registration_sha256'], 'reason':'fixture'}
        with self.assertRaises(ResearchError): manager.advance_staged_primary(request)
        self.assertEqual(project.status(), state)


if __name__ == '__main__':
    unittest.main()
