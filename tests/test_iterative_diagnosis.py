import copy
import unittest
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from autoresearch import iterative_diagnosis as module, iterative_diagnosis_evidence as evidence
from autoresearch.contracts import ResearchError,fingerprint
from test_diagnostic_followup_evidence import payload as prior_payload


def action(index,name,params,result):
    return {'id':'r76-action-'+str(index),'ordinal':index,'request_id':'prior-'+str(index),'observation_sha256':'a'*64,'action':name,'reason':'Original unreviewed reason','parameters':params,'source_citation_ids':['p02-diagnostic-followup-source'],'evidence_action_ids':[] if index==1 else ['r76-action-'+str(index-1)],'result':result,'result_sha256':fingerprint(result)}


def synthetic():
    prior=prior_payload();orig=prior['original_source'];orig['summary']['candidate_metrics']={name:{'pooled_mae':2.5,'r54_chemistry_mae':1.0} for name in orig['inputs']['policies']}
    orig['snapshot_sha256']=fingerprint({k:v for k,v in orig.items() if k!='snapshot_sha256'})
    for a in prior['prior_study']['actions']:
        if a['action'] in ('inspect_residuals','compare_policies'):
            a['result']['source_snapshot_sha256']=orig['snapshot_sha256'];a['result_sha256']=fingerprint(a['result'])
    prior['summary']=__import__('autoresearch.diagnostic_followup_evidence',fromlist=['_summary'])._summary(prior)
    prior['snapshot_sha256']=fingerprint({k:v for k,v in prior.items() if k!='snapshot_sha256'})
    result={'summary':{'named_tool':'investigate_feature_representation','model_assertion':{'finding':'raw hypothesis','next_check':'inspect topography'}}}
    seed=action(1,'investigate_feature_representation',{'finding':'raw hypothesis','next_check':'inspect topography'},result)
    pause=action(2,'pause',{}, {'summary':{'decision':'pause'}})
    old={'configuration_sha256':'b'*64,'study_status':'paused','controller_status':'complete','max_requests':4,'actions':[seed,pause],
         'native_trace':[{'ordinal':1,'status':'applied','action_id':seed['id']},{'ordinal':2,'status':'invalid','action_id':None},{'ordinal':3,'status':'applied','action_id':pause['id']}],
         'invalid_requests':[{'ordinal':2,'error_code':'MISSING_TOOL_CALL','content':'{"action":"inspect_topography"}', 'tool_calls':[]}],'new_fits':0}
    value={'schema_version':'p02-iterative-diagnosis-source-v1','prior_source':prior,'prior_study':old,'scope':prior['scope'],'seed_judgment':seed,'facts':evidence._facts(prior),'topography_available':True}
    value['snapshot_sha256']=fingerprint(value);return value


def req(study,name,rid,params=None):
    state=study.observe();return {'request_id':rid,'observation_sha256':state['observation_sha256'],'action':name,'reason':'Unreviewed original reason','source_citation_ids':['p02-iterative-diagnosis-source'],'evidence_action_ids':[state['actions'][-1]['id']] if state['actions'] else [],'parameters':params or {}}


class IterativeDiagnosisTests(unittest.TestCase):
    def test_binding_judgment_analysis_revision_pause_replay(self):
        source=synthetic();evidence.validate_source(source)
        self.assertTrue(all(row['comparison']=='worse' for row in source['facts']['policies']))
        self.assertEqual(source['prior_study']['invalid_requests'][0]['error_code'],'MISSING_TOOL_CALL')
        altered=copy.deepcopy(source);altered['prior_study']['actions'][0]['result']['summary']['named_tool']='changed';altered['snapshot_sha256']=fingerprint({k:v for k,v in altered.items() if k!='snapshot_sha256'})
        with self.assertRaises(ResearchError):evidence.validate_source(altered)
        with tempfile.TemporaryDirectory() as directory:
            fake=SimpleNamespace(__file__=evidence.__file__,prepare_source=lambda _:copy.deepcopy(source),validate_source=evidence.validate_source,inspect_topography=evidence.inspect_topography)
            with patch.object(module,'evidence_module',return_value=fake):
                study=module.IterativeDiagnosisStudy(Path(directory)/'study');study.create(Path(directory)/'prior','Synthetic goal',5)
                fields={'finding':'First model finding','next_check':'Inspect topography'};first=study.apply(req(study,'investigate_feature_representation','first',fields))['action']
                self.assertEqual(first['result']['summary']['replaces_id'],source['seed_judgment']['id'])
                self.assertIn('inspect_topography',module.available_actions(study.observe()))
                with self.assertRaises(ResearchError):study.apply(req(study,'investigate_data_mapping','early',fields))
                check=study.apply(req(study,'inspect_topography','analysis'))['action'];self.assertEqual(check['result']['dimension'],'topography')
                revision=study.apply(req(study,'investigate_data_mapping','revision',fields))['action'];self.assertEqual(revision['result']['summary']['proposal_version'],2);self.assertEqual(revision['result']['summary']['replaces_id'],first['id'])
                pause_request=req(study,'pause','pause');study.apply(pause_request);self.assertTrue(study.apply(pause_request)['replayed']);self.assertEqual(study.observe()['status'],'paused')
                final=module.tools_for(study.observe(),True);self.assertEqual({t['function']['name'] for t in final},{'pause','stop'})


if __name__=='__main__':unittest.main()
