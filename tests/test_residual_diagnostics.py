import copy
import hashlib
import unittest

from autoresearch import residual_diagnostics as diagnostics
from autoresearch.contracts import ResearchError, canonical, fingerprint


def fixture():
    policies=['recorded_equal_batch','positive_equal_batch','recorded_equal_section','positive_equal_section']
    rows={};predictions=[]
    for index,policy in enumerate(policies):
        rows[policy]=[]
        for topography,chemistry in ((2,0),(2,1),(3,0),(3,1)):
            target=float(index+chemistry);row={'topography':topography,'chemistry':chemistry,'fold':topography-1,'target':target,'chemistry_prediction':target,'additive_prediction':target+.5,'interaction_prediction':target+1}
            rows[policy].append(row);predictions.append({'policy':policy,'topography':topography,'chemistry':chemistry,'fold':row['fold'],'target':target,'prediction':target+topography})
    inputs={'policies':policies,'rows_by_policy':rows};inputs_sha=fingerprint(inputs);config_sha='a'*64
    candidate={'schema_version':'configured-candidate-result-v1','inputs_sha256':inputs_sha,'configuration_sha256':config_sha,'candidate_id':'candidate','alpha':.5,'summary':{'metrics':{},'candidate_id':'candidate'},'predictions':predictions}
    raw=canonical(candidate).encode();artifact=hashlib.sha256(raw).hexdigest();result_sha=fingerprint({'summary':candidate['summary'],'artifact':{'sha256':artifact,'bytes':len(raw)}})
    action={'id':'candidate-action','action':'run_candidate','parameters':{'candidate_id':'candidate'},'summary':candidate['summary'],'result_sha256':result_sha}
    view={'schema_version':'p02-iteration-view-v1','status':'stopped','inputs_sha256':inputs_sha,'study_configuration_sha256':config_sha,'actions':[action]};view['snapshot_sha256']=fingerprint(view)
    scope={'inputs_sha256':inputs_sha,'study_configuration_sha256':config_sha,'iteration_snapshot_sha256':view['snapshot_sha256'],'candidate_action_id':action['id'],'candidate_artifact_sha256':artifact,'candidate_result_sha256':result_sha}
    payload={'schema_version':'p02-diagnostic-source-v1','iteration':view,'inputs':inputs,'candidate':candidate,'scope':scope,'summary':{}}
    payload['snapshot_sha256']=fingerprint(payload);return payload


class ResidualTests(unittest.TestCase):
    def test_group_arithmetic_pairing_and_identity(self):
        source=fixture();result=diagnostics.inspect_residuals(source,'topography');policy='recorded_equal_batch'
        total=result['summary']['policies'][policy]['methods']['current_candidate']
        self.assertEqual(total['n'],4);self.assertEqual(total['mae'],2.5);self.assertEqual(total['signed_bias'],2.5)
        self.assertEqual(total['delta_mae_vs_chemistry'],2.5);self.assertEqual(total['worse_groups'],2)
        self.assertEqual(total['top5_absolute_error_share'],1.0);self.assertEqual(total['top5_absolute_error_n'],4)
        self.assertEqual(len(result['rows']),16);self.assertEqual(len(result['rankings'][0]['worst5_delta']),2)
        contrast=diagnostics.compare_policies(source);row=next(v for v in contrast['summary']['contrasts'] if v['contrast']=='zero_batch' and v['method']=='current_candidate')
        self.assertEqual(row['paired_n'],4);self.assertEqual(row['mean_target_shift'],1);self.assertEqual(row['mean_residual_shift'],0);self.assertEqual(len(contrast['rows']),64)
        bad=copy.deepcopy(source);bad['candidate']['predictions'][0]['target']+=1;bad['snapshot_sha256']=fingerprint({k:v for k,v in bad.items() if k!='snapshot_sha256'})
        with self.assertRaises(ResearchError):diagnostics.inspect_residuals(bad)


if __name__=='__main__':unittest.main()
