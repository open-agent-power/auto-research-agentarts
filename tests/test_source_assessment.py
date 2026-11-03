import copy
import json
import tempfile
import unittest
from pathlib import Path

from autoresearch import returned_evidence, source_assessment as module
from autoresearch.contracts import ResearchError, canonical, fingerprint


def fixture():
    sources=[{'id':'paper','sha256':'a'*64,'url':'https://example.org/paper.pdf','media_type':'application/pdf','license_note':'fixture','bytes':1000},
             {'id':'inventory','sha256':'b'*64,'url':'https://example.org/inventory.json','media_type':'application/json','license_note':'fixture','bytes':1200}]
    chunks=[];claims=[]
    for index in range(11):
        source=sources[0 if index<6 else 1];kind='pdf_page' if index<6 else 'json_pointer';value=str(index+1) if index<6 else '/row/'+str(index);text='evidence sample '+str(index)
        c={'id':'','label':'source '+str(index),'source_id':source['id'],'source_sha256':source['sha256'],'url':source['url'],'locator':{'kind':kind,'value':value},'text':text,
           'text_sha256':__import__('hashlib').sha256(text.encode()).hexdigest(),'start_char':0,'end_char':len(text),'complete_document':False};c['id']=returned_evidence._chunk_id(c);chunks.append(c)
        claims.append({'id':'f'+str(index),'claim':'provided claim','status':'observed','source_id':source['id'],'locator':c['locator'],'note':'fixture','locator_validation':'provided_not_verified','chunk_ids':[c['id']],'interpretation_status':'pending_scientific_interpretation'})
    packet={'schema_version':'p02-returned-evidence-v1','submission_snapshot_sha256':'c'*64,'handoff_snapshot_sha256':'d'*64,'task_id':'export_mapping','contributor':{'role':'teammate','label':'fixture'},'submission_claims':claims,'unresolved_questions':[],
            'sources':sources,'chunks':chunks,'exclusions':[],'extractor':{'pdf_worker':'knowledge_sources._extract_pdf','pdf_worker_sha256':'e'*64,'pdf_extractor_sha256':'f'*64,'pypdf_version':'fixture','warning_count':0,'json_values':'canonical','limits':'fixture'},'scientific_validation':False}
    packet['snapshot_sha256']=fingerprint(packet);returned_evidence.validate_packet(packet);return packet


def response(name,args):return {'message':{'tool_calls':[{'type':'function','function':{'name':name,'arguments':args}}]}}


def body(loop,state,remaining):return loop._request(state,remaining,[],{'reasoning_effort':'high','context_tokens':32768,'max_output_tokens':4096,'max_request_bytes':65536})


class SourceAssessmentTests(unittest.TestCase):
    def test_more_than_eight_chunks_aliases_unread_and_request_bound(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);packet=fixture();path=root/'packet.json';path.write_text(canonical(packet),encoding='utf8')
            loop=module.SourceAssessmentCloudLoop(root/'study');study=loop.study;state=study.create(path,'Review returned material',4,prior_attempt='earlier bounded study')
            def call(name,args,rid,remaining):
                current=study.observe();decision=loop._parse_decision(response(name,args),current,rid,body(loop,current,remaining));return study.apply(decision)['action']
            first=call('read_sources',{'source_ids':['paper'],'reason':'Read paper excerpts'},'read1',4)
            self.assertEqual(len(first['result']['chunks']),6);self.assertEqual(study.observe()['read_aliases'],['e01','e02','e03','e04','e05','e06'])
            answers=[{'question_id':q['id'],'status':'unresolved','answer':'Not established','evidence_ids':['e11']} for q in module.QUESTIONS]
            current=study.observe();invalid=response('record_assessment',{'answers':answers,'reason':'Preserve gap'})
            with self.assertRaises(ResearchError):loop._parse_decision(invalid,current,'invalid',body(loop,current,3))
            second=call('read_sources',{'source_ids':['inventory'],'reason':'Read inventory excerpts'},'read2',3)
            self.assertEqual(len(second['result']['chunks']),5);state=study.observe();self.assertEqual(len(state['read_aliases']),11)
            ctx=module.project_context(state,2,[]);self.assertEqual(len(ctx['read_chunks']),11);self.assertEqual(len({v['alias'] for v in ctx['read_chunks']}),11)
            answers=[{'question_id':q['id'],'status':'unresolved','answer':'Not established','evidence_ids':list(state['read_aliases'])} for q in module.QUESTIONS]
            final=call('record_assessment',{'answers':answers,'reason':'Keep uncertainties'},'record',2)
            self.assertEqual(len(final['result']['resolved_original_chunks']),11);self.assertEqual(final['result']['answers'],answers);self.assertFalse(final['result']['task_complete']);self.assertEqual(study.observe()['status'],'paused')
            oversized=fixture();base=oversized['submission_claims'][0]
            for i in range(30):
                claim=copy.deepcopy(base);claim['id']='extra'+str(i);claim['note']='x'*3000;oversized['submission_claims'].append(claim)
            oversized['snapshot_sha256']=fingerprint({k:v for k,v in oversized.items() if k!='snapshot_sha256'});huge=root/'huge.json';huge.write_text(canonical(oversized),encoding='utf8')
            other=module.SourceAssessmentStudy(root/'other');other.create(huge,'Bounded request',4);before=other.observe()
            request={'request_id':'too-large','observation_sha256':before['observation_sha256'],'action':'read_sources','reason':'Read','source_citation_ids':['p02-returned-evidence'],'evidence_action_ids':[],'parameters':{'source_ids':['paper','inventory']}}
            with self.assertRaises(ResearchError) as error:other.apply(request)
            self.assertEqual(error.exception.code,'PROMPT_TOO_LARGE');self.assertEqual(other.observe()['actions'],[])


if __name__=='__main__':unittest.main()
