import copy
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from autoresearch import evidence_handoff as handoff
from autoresearch.contracts import ResearchError, fingerprint

FACTS=[{'id':'f1','kind':'numeric','label':'First fact','value':{'n':4},'provenance':{'source':'diagnostic','pointer':'/first'}},
       {'id':'f2','kind':'source','label':'Second fact','value':'source','provenance':{'source':'inventory','pointer':'/second'}},
       {'id':'f3','kind':'gate','label':'Third fact','value':False,'provenance':{'source':'baseline','pointer':'/third'}}]
TASK={'id':'export_mapping','title':'Map original exports','required_fact_ids':['f1','f2'],'source_urls':['https://example.org/source'],'deliverables':['mapping table'],'acceptance':['matched source coordinates'],'requires_external_data':True,'origin':'host_curated_template'}
CATALOG={'schema_version':'fixture','facts':FACTS,'tasks':[TASK],'snapshot_sha256':'a'*64,'scientific_validation':False}


def read_facts(catalog,ids):
    index={f['id']:f for f in catalog['facts']}
    if len(ids)!=len(set(ids)) or not set(ids)<=set(index):raise ResearchError('INVALID_EVIDENCE','Unknown fact')
    return [copy.deepcopy(index[x]) for x in ids]


def request(study,name,rid,params=None):
    state=study.observe();return {'request_id':rid,'observation_sha256':state['observation_sha256'],'action':name,'reason':'Model original reason',
          'source_citation_ids':['p02-evidence-catalog'],'evidence_action_ids':[state['actions'][-1]['id']] if state['actions'] else [],'parameters':params or {}}


def response(name,args):return {'message':{'tool_calls':[{'type':'function','function':{'name':name,'arguments':args}}]}}


def body(loop,state,remaining):return loop._request(state,remaining,[],{'reasoning_effort':'high','context_tokens':32768,'max_output_tokens':4096,'max_request_bytes':65536})


class EvidenceHandoffTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup);self.root=Path(temp.name)
        fake=SimpleNamespace(__file__=__file__,build_catalog=lambda *a:copy.deepcopy(CATALOG),validate_catalog=lambda catalog:None,read_facts=read_facts)
        patcher=patch.object(handoff,'catalog_module',return_value=fake);patcher.start();self.addCleanup(patcher.stop)
        self.loop=handoff.EvidenceHandoffCloudLoop(self.root/'study');self.study=self.loop.study
        self.study.create(self.root/'diagnostic',self.root/'iteration',self.root/'baseline',self.root/'inventory.json','Choose an evidence handoff',4)

    def test_native_read_then_record_atomic_pause_and_replay(self):
        state=self.study.observe();first_body=body(self.loop,state,4);message=response('read_evidence',{'fact_ids':['f1','f2'],'reason':'I need these facts'})
        parsed=self.loop._parse_decision(message,state,'read',first_body);first=self.study.apply(parsed)['action']
        self.assertEqual(first['parameters']['fact_ids'],['f1','f2']);self.assertEqual(first['result']['facts'],FACTS[:2]);self.assertTrue(first['result']['fact_ids_from_tool_arguments'])
        state=self.study.observe();final_body=body(self.loop,state,1);self.assertEqual({t['function']['name'] for t in final_body['tools']},{'record_next_step','pause','stop'})
        parsed=self.loop._parse_decision(response('record_next_step',{'task_id':'export_mapping','fact_ids':['f1','f2'],'reason':'Unreviewed reason'}),state,'record',final_body)
        saved=self.study.apply(parsed)['action'];self.assertEqual(saved['result']['task'],TASK);self.assertEqual(saved['result']['cited_facts'],FACTS[:2]);self.assertEqual(saved['result']['model_reason'],'Unreviewed reason')
        self.assertFalse(saved['result']['external_task_executed']);self.assertTrue(saved['result']['waiting_for_external_input']);self.assertEqual(self.study.observe()['status'],'paused');self.assertTrue(self.study.apply(parsed)['replayed'])
        with self.assertRaises(ResearchError):self.study.apply(request(self.study,'stop','late'))

    def test_reject_unread_unknown_repeated_and_injected_metadata(self):
        state=self.study.observe();self.assertNotIn('record_next_step',handoff.available_actions(state,True))
        for ids in (['unknown'],['f1','f1']):
            with self.assertRaises(ResearchError):self.study.apply(request(self.study,'read_evidence','bad-'+str(len(ids)),{'fact_ids':ids}))
        self.study.apply(request(self.study,'read_evidence','one',{'fact_ids':['f1']}))
        with self.assertRaises(ResearchError):self.study.apply(request(self.study,'record_next_step','unread',{'task_id':'export_mapping','fact_ids':['f1','f2']}))
        with self.assertRaises(ResearchError):self.study.apply(request(self.study,'read_evidence','repeat',{'fact_ids':['f1']}))
        state=self.study.observe();bad=response('read_evidence',{'fact_ids':['f2'],'reason':'x','observation_sha256':state['observation_sha256']})
        with self.assertRaises(ResearchError):self.loop._parse_decision(bad,state,'injected',body(self.loop,state,3))

    def test_catalog_tamper_and_early_stop(self):
        stop=request(self.study,'stop','stop');self.study.apply(stop);self.assertEqual(self.study.observe()['status'],'stopped')
        (self.root/'study'/'catalog.json').write_text('{}')
        with self.assertRaises(ResearchError):self.study.observe()


if __name__=='__main__':unittest.main()
