import copy
import json
import unittest

from autoresearch import compact_iteration as compact
from autoresearch.contracts import ResearchError, fingerprint


def observation():
    state={'schema_version':'configured-iteration-study-v1','configuration_sha256':'a'*64,'status':'active',
           'protocol':{'goal':'synthetic','candidates':[{'id':'alpha3','alpha':3},{'id':'alpha30','alpha':30}], 'max_fits':280,'max_requests':4},
           'inputs_sha256':'b'*64,'prior_evidence':{'known_iterations':[]},'limits':['fixture'],
           'citations':[{'citation_id':'p02-r54','source_sha256':'c'*64},{'citation_id':'p02-r59','source_sha256':'d'*64}],
           'actions':[],'reservations':[],'budget':{'fits_reserved':0,'max_fits':280},'endpoint_gate':{'ALP_eligible':False},'scientific_validation':False}
    state['observation_sha256']=fingerprint(state);return state


def body(state,remaining=4):
    return compact.CompactCloudLoop('unused')._request(state,remaining,[],{'reasoning_effort':'low','context_tokens':32768,'max_output_tokens':2048,'max_request_bytes':65536})


def response(name,args):return {'message':{'tool_calls':[{'type':'function','function':{'name':name,'arguments':args}}]}}


class CompactTests(unittest.TestCase):
    def test_compact_binding_and_invalid_native_arguments(self):
        state=observation();state['actions']=[{'id':'actual-action','ordinal':1,'action':'run_candidate','parameters':{'candidate_id':'alpha3'},'reason':'earlier','result_sha256':'e'*64,'result':{'summary':{}}}];state['reservations']=[{'candidate_id':'alpha3','status':'committed'}];state['budget']['fits_reserved']=140
        state['observation_sha256']=fingerprint({k:v for k,v in state.items() if k!='observation_sha256'})
        original=body(state);res=response('run_candidate',{'candidate_id':'alpha30','reason':'Actual model reason'});saved=copy.deepcopy(res)
        request=compact.parse_compact(res,state,'request-1',original)
        self.assertEqual(request['reason'],'Actual model reason');self.assertEqual(request['parameters'],{'candidate_id':'alpha30'})
        self.assertEqual(request['observation_sha256'],state['observation_sha256']);self.assertEqual(request['source_citation_ids'],['p02-r54','p02-r59']);self.assertEqual(request['evidence_action_ids'],['actual-action']);self.assertEqual(res,saved)
        for invalid in (response('run_candidate',{'candidate_id':'alpha30','reason':'x','observation_sha256':state['observation_sha256']}),response('run_candidate',{'candidate_id':'not-offered','reason':'x'}),response('made_up',{'reason':'x'})):
            with self.assertRaises(ResearchError):compact.parse_compact(invalid,state,'x',original)
        forged=copy.deepcopy(original);ctx=json.loads(forged['messages'][1]['content']);ctx['host_binding']['evidence_action_ids']=[];forged['messages'][1]['content']=json.dumps(ctx)
        with self.assertRaises(ResearchError):compact.parse_compact(saved,state,'x',forged)

    def test_final_slot_early_stop_and_frozen_budget(self):
        state=observation();final=body(state,1)
        self.assertEqual({t['function']['name'] for t in final['tools']},{'pause','stop'})
        stopped=compact.parse_compact(response('stop',{'reason':'Enough evidence'}),state,'stop',body(state,4))
        self.assertEqual(stopped['parameters'],{});self.assertEqual(stopped['evidence_action_ids'],[])
        exhausted=copy.deepcopy(state);exhausted['budget']['fits_reserved']=280;exhausted['observation_sha256']=fingerprint({k:v for k,v in exhausted.items() if k!='observation_sha256'})
        self.assertEqual({t['function']['name'] for t in body(exhausted,3)['tools']},{'pause','stop'})
        with self.assertRaises(ResearchError):compact.parse_compact(response('run_candidate',{'candidate_id':'alpha3','reason':'x'}),state,'not-offered',final)


if __name__=='__main__':unittest.main()
