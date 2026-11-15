"""Bounded quality-registration selection metadata, synthetic data only."""
import copy
import unittest

import test_tabular_quality_feedback as fixture
from autoresearch.project_workbench import _projection


class QualityMaterialChoicesTests(unittest.TestCase):
    def setUp(self):
        self.f=fixture.QualityFeedbackTests('runTest');self.f.setUp();self.addCleanup(self.f.doCleanups)

    def test_optional_projection_binds_original_registration_without_raw_input(self):
        f=self.f;before=f.project.status();self.assertNotIn('quality_registration_choices',_projection(f.project,before))
        reg=f.register();state=f.project.status();db=f.project.db.read_bytes()
        choice=_projection(f.project,state)['quality_registration_choices']
        self.assertEqual((choice['status'],choice['verification']),('available','registration_metadata_only'))
        self.assertEqual(len(choice['items']),1);item=choice['items'][0]
        self.assertEqual((item['registration_request_id'],item['registration_sha256'],item['controller_request_id']),
                         (reg['request_id'],reg['registration_sha256'],reg['controller_request_id']))
        self.assertEqual(item['conditions'],reg['conditions'])
        self.assertTrue(item['plan_matches']);self.assertTrue(item['source_matches'])
        self.assertEqual(set(item),{'registration_request_id','registration_sha256','controller_request_id','conditions',
                                    'plan_version','plan_sha256','source_snapshot_sha256','plan_matches','source_matches'})
        self.assertEqual(f.project.status(),state);self.assertEqual(f.project.db.read_bytes(),db)
        self.assertEqual(state['budget']['local_tool_calls_used'],0)

    def test_changed_plan_or_invalid_registration_never_offers_match(self):
        f=self.f;f.register();state=f.project.status()
        f.project.save_plan(request_id='later',expected_state_version=state['state_version'],
            plan={'question':'Later','basis':'Synthetic','steps':'Wait','expected_feedback':'Unknown'},reason='Test')
        current=f.project.status();choice=_projection(f.project,current)['quality_registration_choices']
        self.assertFalse(choice['items'][0]['plan_matches'])
        corrupted=copy.deepcopy(current);corrupted['tabular_quality_registrations'][0]['registration_sha256']='0'*64
        view=_projection(f.project,corrupted)['quality_registration_choices']
        self.assertEqual(view,{'status':'unavailable','items':[],'verification':'registration_metadata_only'})
        self.assertEqual(f.project.status(),current)


if __name__=='__main__':unittest.main()
