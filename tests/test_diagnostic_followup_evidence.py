import copy
import unittest

from autoresearch import diagnostic_followup_evidence as followup, residual_diagnostics
from autoresearch.contracts import ResearchError, fingerprint
from test_residual_diagnostics import fixture


def action(index,name,params,result):
    return {'id':'action-'+str(index),'ordinal':index,'request_id':'request-'+str(index),'observation_sha256':'a'*64,'action':name,'reason':'fixture','parameters':params,'source_citation_ids':['p02-diagnostic-source'],'evidence_action_ids':[] if index==1 else ['action-'+str(index-1)],'result':result,'result_sha256':fingerprint(result)}


def payload():
    original=fixture();original['summary']={'candidate_id':'candidate','alpha':.5,'limitations':['fixture limits']};original['snapshot_sha256']=fingerprint({k:v for k,v in original.items() if k!='snapshot_sha256'})
    chemistry=residual_diagnostics.inspect_residuals(original,'chemistry');policies=residual_diagnostics.compare_policies(original)
    actions=[action(1,'inspect_residuals',{'dimension':'chemistry'},chemistry),action(2,'compare_policies',{},policies),action(3,'stop',{}, {'summary':{'decision':'stop'}})]
    prior={'configuration_sha256':'b'*64,'status':'stopped','actions':actions,'native_trace':[{'ordinal':1,'status':'applied','action_id':'action-1'},{'ordinal':2,'status':'invalid','action_id':None},{'ordinal':3,'status':'applied','action_id':'action-2'},{'ordinal':4,'status':'applied','action_id':'action-3'}],'invalid_requests':[{'ordinal':2,'error_code':'INVALID_REQUEST','tool_calls':[{'tool_name':'inspect_residuals','arguments':{'dimension':'missing'}}]}],'controller_status':'stopped','max_requests':6,'new_fits':0}
    result={'schema_version':'p02-diagnostic-followup-source-v1','original_source':original,'prior_study':prior,'scope':original['scope']};result['summary']=followup._summary(result);result['snapshot_sha256']=fingerprint(result);return result


class FollowupEvidenceTests(unittest.TestCase):
    def test_binding_projection_and_single_missing_topography(self):
        value=payload();summary=followup.decision_summary(value)
        candidate=summary['candidate_first_same_policy_chemistry_groups']['recorded_equal_batch']
        self.assertEqual(candidate['worse_groups'],2);self.assertEqual(candidate['group_count'],2)
        self.assertEqual(summary['candidate_alpha'],.5);self.assertTrue(summary['topography_available'])
        self.assertEqual(summary['invalid_requests'][0]['error_code'],'INVALID_REQUEST')
        self.assertEqual(followup.inspect_topography(value)['dimension'],'topography')
        changed=copy.deepcopy(value);changed['prior_study']['actions'][0]['result']['summary']['dimension']='changed';changed['snapshot_sha256']=fingerprint({k:v for k,v in changed.items() if k!='snapshot_sha256'})
        with self.assertRaises(ResearchError):followup.validate_source(changed)
        altered=copy.deepcopy(value);altered['prior_study']['native_trace'][0]['action_id']='wrong';altered['snapshot_sha256']=fingerprint({k:v for k,v in altered.items() if k!='snapshot_sha256'})
        with self.assertRaises(ResearchError):followup.validate_source(altered)
        extra=copy.deepcopy(value);topography=followup.inspect_topography(value);extra['prior_study']['actions'].append(action(4,'inspect_residuals',{'dimension':'topography'},topography));extra['prior_study']['native_trace'].append({'ordinal':5,'status':'applied','action_id':'action-4'});extra['summary']=followup._summary(extra);extra['snapshot_sha256']=fingerprint({k:v for k,v in extra.items() if k!='snapshot_sha256'})
        with self.assertRaises(ResearchError):followup.inspect_topography(extra)


if __name__=='__main__':unittest.main()
