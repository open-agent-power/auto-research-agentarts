import copy
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from autoresearch import postrun_revision as revision, research_memory
from autoresearch.contracts import ResearchError, fingerprint

SCOPE={'source_manifest_sha256':'a'*64,'inputs_sha256':'b'*64,'analysis_code_sha256':'c'*64,'protocol':'configured-iteration-v1:test'}


def entry(kind,action,payload):
    record={'schema_version':'conditional-research-memory-v1','kind':kind,'scope':SCOPE,'payload':payload,'provenance':{'action_id':action,'source_record_sha256':fingerprint({'action':action})}}
    record['id']=research_memory.observation_id(record);return record

OLD=entry('agent_decision','seed-action',{'decision':'old'})
NUMERIC=entry('fit_observation','current-alpha3',{'alpha':3})
PAYLOAD={'schema_version':'postrun-revision-source-v1','scope':SCOPE,'snapshot_sha256':'d'*64,'source':{'view':{'snapshot_sha256':'e'*64}},'postrun':{'assessment':{'notes':['fixture']}},'seed_proposal':{'id':'seed-action','parameters':{'choice':'continue_regularization'}},'superseded_memory_id':OLD['id'],'inventory':[{'experiment_id':'current-alpha3','alpha':3,'origin':'current','metrics':{}},{'experiment_id':'historical-alpha100','alpha':100,'origin':'historical','metrics':{}}],'policy_labels':{'positive_equal_batch':'Count > 0'}}


def validate_proposal(params,payload):
    required={'choice','candidate_alpha','hypothesis','next_check','success_criterion','failure_criterion','experiment_ids','supersedes_proposal_id'}
    if type(params) is not dict or set(params)!=required or params['choice'] not in revision.CHOICES:raise ResearchError('INVALID_REQUEST','Invalid fixture proposal')
    if not params['experiment_ids'] or not set(params['experiment_ids'])<={x['experiment_id'] for x in payload['inventory']}:raise ResearchError('INVALID_EVIDENCE','Invalid fixture experiment ID')
    if params['choice']=='continue_regularization' and params['candidate_alpha'] in [x['alpha'] for x in payload['inventory']]:raise ResearchError('DUPLICATE_EXPERIMENT','Already tested')
    if params['choice']!='continue_regularization' and params['candidate_alpha'] is not None:raise ResearchError('INVALID_REQUEST','Must be null')


def derive(payload,action):
    return {'scope':SCOPE,'entries':[copy.deepcopy(NUMERIC),entry('agent_decision',action['id'],{'proposal':action['parameters']})],'validation':{'scientific_validation':False}}


def params(alpha=10,supersedes='seed-action'):
    return {'choice':'continue_regularization','candidate_alpha':alpha,'hypothesis':'h','next_check':'check','success_criterion':'s','failure_criterion':'f','experiment_ids':['current-alpha3'],'supersedes_proposal_id':supersedes}


def request(study,action,rid,parameters=None):
    state=study.observe()
    return {'request_id':rid,'action':action,'observation_sha256':state['observation_sha256'],'reason':'Synthetic model reason','source_citation_ids':['p02-revision-source'],'evidence_action_ids':[state['actions'][-1]['id']] if state['actions'] else [],'parameters':parameters or {}}


class RevisionTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup);self.root=Path(temp.name)
        fake=SimpleNamespace(__file__=__file__,prepare_source=lambda *args:copy.deepcopy(PAYLOAD),validate_source=lambda payload:None,validate_proposal=validate_proposal,derive_entries=derive)
        patcher=patch.object(revision,'evidence_module',return_value=fake);patcher.start();self.addCleanup(patcher.stop)
        self.memory=research_memory.ResearchMemory(self.root/'memory')
        self.memory._import_derived({'scope':SCOPE,'entries':[copy.deepcopy(OLD),copy.deepcopy(NUMERIC)],'validation':{'fixture':True}})
        self.study=revision.RevisionStudy(self.root/'revision');self.study.create(self.root/'source.json',self.root/'publication',self.root/'memory','Revise the proposal',max_requests=6)

    def test_native_revision_duplicate_and_three_id_namespaces(self):
        state=self.study.observe();loop=revision.RevisionCloudLoop(self.root/'revision')
        body=loop._request(state,6,[],{'reasoning_effort':'low','context_tokens':32768,'max_output_tokens':2048,'max_request_bytes':65536})
        p=params();args={'observation_sha256':state['observation_sha256'],'reason':'revision reasoning','source_citation_ids':['p02-revision-source'],'evidence_action_ids':[],**p}
        response={'message':{'tool_calls':[{'type':'function','function':{'name':'revise_proposal','arguments':args}}]}}
        parsed=loop._parse_decision(response,state,'revision-1',body);first=self.study.apply(parsed)['action']
        duplicate=request(self.study,'revise_proposal','duplicate',params(100,first['id']))
        with self.assertRaises(ResearchError) as error:self.study.apply(duplicate)
        self.assertEqual(error.exception.code,'DUPLICATE_EXPERIMENT')
        wrong=request(self.study,'revise_proposal','wrong',params(12,first['id']));wrong['evidence_action_ids']=['current-alpha3']
        with self.assertRaises(ResearchError):self.study.apply(wrong)
        second=self.study.apply(request(self.study,'revise_proposal','revision-2',params(12,first['id'])))['action']
        with self.assertRaises(ResearchError):self.study.apply(request(self.study,'revise_proposal','revision-3',params(14,second['id'])))

    def test_memory_pending_replay_retirement_and_recall(self):
        self.study.apply(request(self.study,'revise_proposal','revision-1',params()))
        remember=request(self.study,'remember_revision','remember-1',{'superseded_memory_id':OLD['id']})
        with patch.object(research_memory.ResearchMemory,'set_status',side_effect=OSError('interrupt after import')):
            with self.assertRaises(ResearchError):self.study.apply(remember)
        self.assertTrue(self.study.observe()['pending_import'])
        with self.assertRaises(ResearchError):self.study.apply(request(self.study,'pause','blocked'))
        self.assertTrue(self.study.apply(remember)['replayed']);self.study.apply(remember)
        entries=self.memory.recall(SCOPE,include_retired=True)['entries']
        self.assertEqual(next(x for x in entries if x['record']['id']==OLD['id'])['inclusion_status'],'retired')
        self.assertEqual(next(x for x in entries if x['record']['id']==NUMERIC['id'])['inclusion_status'],'active')
        recalled=self.study.apply(request(self.study,'recall_observations','recall'))['action']['result']
        self.assertNotIn(OLD['id'],[x['record']['id'] for x in recalled['entries']]);self.assertEqual(len(recalled['entries']),2)
        with self.assertRaises(ResearchError):self.study.apply(request(self.study,'revise_proposal','late',params()))

    def test_source_configuration_budget_and_terminal_schema(self):
        loop=revision.RevisionCloudLoop(self.root/'revision');state=self.study.observe()
        self.assertEqual({v['properties']['action']['enum'][0] for v in revision.schema_for(state,True)['oneOf']},{'pause','stop'})
        with self.assertRaises(ResearchError):loop.configure({},max_requests=5)
        self.study.apply(request(self.study,'stop','stop'))
        with self.assertRaises(ResearchError):self.study.apply(request(self.study,'revise_proposal','later',params()))
        (self.root/'revision'/'source.json').write_text('{}')
        with self.assertRaises(ResearchError):self.study.observe()


if __name__=='__main__':unittest.main()
