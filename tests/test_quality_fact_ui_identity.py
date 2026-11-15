"""Snapshot-only Host identities for the opt-in quality fact UI."""
import copy
import unittest

import test_host_supplied_quality_workbench as fixture
from autoresearch.contracts import fingerprint


class QualityFactUIIdentityTests(unittest.TestCase):
    def stage(self, supplied=True):
        helper=fixture.SuppliedQualityWorkbenchTests('runTest')
        result=helper.stage(supplied=supplied);self.addCleanup(helper.doCleanups)
        return result

    def test_identity_hashes_same_returned_record_and_no_research_write(self):
        f,manager,host,_,_=self.stage();before=f.project.status();db=f.project.db.read_bytes()
        view=manager.model_view();record=view['records'][0];identity=view['quality_fact_identities'][0]
        material=record['context']['supplied_materials'][0]
        self.assertEqual(identity,{'host_request_id':record['request_id'],'status':'available',
            'context_sha256':fingerprint(record['context']),'response_sha256':record['response_sha256'],
            'materials':[{'registration_request_id':material['registration_request_id'],
                'registration_sha256':material['registration_sha256'],'material_sha256':fingerprint(material)}]})
        self.assertEqual(f.project.status(),before);self.assertEqual(f.project.db.read_bytes(),db)
        self.assertEqual(before['budget']['local_tool_calls_used'],1)
        self.assertEqual(host.status(request_id=record['request_id'])['context'],record['context'])

    def test_old_records_keep_model_view_shape(self):
        _,manager,_,_,_=self.stage(supplied=False)
        self.assertNotIn('quality_fact_identities',manager.model_view())

    def test_missing_response_or_ambiguous_registration_has_no_usable_hash(self):
        _,manager,host,_,_=self.stage();original=host._load()
        for mutation in ('response','duplicate','bad_hash'):
            with self.subTest(mutation=mutation):
                state=copy.deepcopy(original);record=state['requests']['host-plan']
                if mutation=='response':record.pop('response_sha256')
                elif mutation=='duplicate':record['context']['supplied_materials'].append(copy.deepcopy(record['context']['supplied_materials'][0]))
                else:record['context']['supplied_materials'][0]['registration_sha256']='bad'
                host._save(state)
                try:
                    identity=manager.model_view()['quality_fact_identities'][0]
                    self.assertEqual(identity,{'host_request_id':'host-plan','status':'unavailable'})
                finally:host._save(original)


if __name__=='__main__':unittest.main()
