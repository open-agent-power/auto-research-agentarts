import copy
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from autoresearch import postrun_research as post, research_memory
from autoresearch.contracts import ResearchError, fingerprint

SCOPE={'source_manifest_sha256':'a'*64,'inputs_sha256':'b'*64,'analysis_code_sha256':'c'*64,'protocol':'configured-iteration-v1:test'}
PAYLOAD={'schema_version':'postrun-source-v1','scope':SCOPE,'snapshot_sha256':'d'*64,'facts':[{'action_id':'candidate-1','candidate_id':'a3','alpha':3,'metrics':{},'comparisons':{},'result_sha256':'e'*64}], 'view':{'prior_evidence':{'known_iterations':[]}}}


def derive(payload,proposal):
    entries=[]
    for kind,action in [('fit_observation','candidate-1'),('agent_decision',proposal['id'])]:
        rec={'schema_version':'conditional-research-memory-v1','kind':kind,'scope':payload['scope'],'payload':{'action':action},'provenance':{'action_id':action,'source_record_sha256':fingerprint({'action':action})}}
        rec['id']=research_memory.observation_id(rec);entries.append(rec)
    return {'scope':payload['scope'],'entries':entries,'validation':{'fixture':True}}


def request(study,action,rid,params=None):
    state=study.observe()
    return {'request_id':rid,'action':action,'observation_sha256':state['observation_sha256'],'reason':'Synthetic model reason', 'source_citation_ids':['p02-current-iteration'],'evidence_action_ids':[state['actions'][-1]['id']] if state['actions'] else [],'parameters':params or {}}


def proposal():
    return {'choice':'change_hypothesis','hypothesis':'new hypothesis','next_check':'test independently','success_criterion':'success','failure_criterion':'failure','source_action_ids':['candidate-1']}


class PostrunTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup);self.root=Path(temp.name)
        self.fake=SimpleNamespace(__file__=__file__,prepare_source=lambda *args:copy.deepcopy(PAYLOAD),derive_entries=derive)
        p=patch.object(post,'evidence_module',return_value=self.fake);p.start();self.addCleanup(p.stop)
        self.study=post.PostrunStudy(self.root/'post');self.study.create(self.root/'source',self.root/'publication',self.root/'memory','Find a useful next question',max_requests=6)

    def test_native_propose_remember_recall_stop(self):
        loop=post.PostrunCloudLoop(self.root/'post')
        for i,(action,params) in enumerate([('propose_next',proposal()),('remember_observations',{}),('recall_observations',{}),('stop',{})]):
            state=self.study.observe();body=loop._request(state,6-i,[],{'reasoning_effort':'low','context_tokens':32768,'max_output_tokens':2048,'max_request_bytes':65536})
            args={'observation_sha256':state['observation_sha256'],'reason':'model reasoning','source_citation_ids':['p02-current-iteration'],'evidence_action_ids':[state['actions'][-1]['id']] if state['actions'] else [],**params}
            response={'message':{'tool_calls':[{'type':'function','function':{'name':action,'arguments':args}}]}}
            parsed=loop._parse_decision(response,state,'request-'+str(i),body);result=self.study.apply(parsed)['action']
            if action=='recall_observations':self.assertEqual(len(result['result']['entries']),2)
        self.assertEqual(self.study.observe()['status'],'stopped')
        self.assertEqual(set(x['function']['name'] for x in loop._request(self.study.observe(),1,[],{'reasoning_effort':'low','context_tokens':32768,'max_output_tokens':2048,'max_request_bytes':65536})['tools']),{'pause','stop'})

    def test_pending_import_recovers_idempotently_and_retired_stays_retired(self):
        self.study.apply(request(self.study,'propose_next','p',proposal()))
        remember=request(self.study,'remember_observations','m')
        original=research_memory.ResearchMemory._import_derived
        with patch.object(research_memory.ResearchMemory,'_import_derived',side_effect=OSError('fixture failure')):
            with self.assertRaises(ResearchError):self.study.apply(remember)
        self.assertTrue(self.study.observe()['pending_import'])
        with self.assertRaises(ResearchError):self.study.apply(request(self.study,'stop','blocked'))
        result=self.study.apply(remember);self.assertTrue(result['replayed'])
        memory=research_memory.ResearchMemory(self.root/'memory');entries=memory.recall(SCOPE)['entries'];self.assertEqual(len(entries),2)
        entry_id=entries[0]['record']['id'];memory.set_status(entry_id,'retired','fixture','retire-one')
        self.study.apply(remember);self.assertEqual(len(memory.recall(SCOPE)['entries']),1)
        different={**SCOPE,'inputs_sha256':'f'*64};self.assertEqual(memory.recall(different)['entries'],[])

    def test_source_tamper_and_wrong_ids_rejected(self):
        invalid=request(self.study,'propose_next','p',proposal());invalid['parameters']['source_action_ids']=['invented']
        with self.assertRaises(ResearchError):self.study.apply(invalid)
        (self.root/'post'/'source.json').write_text('{}')
        with self.assertRaises(ResearchError):self.study.observe()


if __name__=='__main__':unittest.main()
