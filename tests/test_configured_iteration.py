import copy
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
from autoresearch import configured_iteration as module
from autoresearch.contracts import ResearchError,fingerprint
from test_chemotopo_cloud import IDENTITY


POLICIES=('recorded_equal_batch','positive_equal_batch','recorded_equal_section','positive_equal_section')


def protocol(candidates=None,max_fits=280,max_requests=4):
    return {'schema_version':'configured-iteration-protocol-v1','executor_id':'p02-interaction-ridge-v1','goal':'Synthetic bounded iteration',
            'candidates':candidates or [{'id':'light','alpha':10.0},{'id':'strong','alpha':100.0}],'max_fits':max_fits,'max_requests':max_requests}


def inputs():
    rows=[{'topography':t,'chemistry':c,'geometry':[float(t*(j+1)) for j in range(10)],'target':float(t*.4+c),
           'fold':t-1,'chemistry_prediction':1.,'additive_prediction':1.1,'interaction_prediction':1.2} for t in (2,3,4,5) for c in (0,1)]
    prior={p:{'interaction':{'pooled_mae':1.},'additive':{'pooled_mae':.9},'chemistry':{'pooled_mae':.8}} for p in POLICIES}
    return {'schema_version':'p02-configured-inputs-v1','executor_id':'p02-interaction-ridge-v1','policies':list(POLICIES),
            'rows_by_policy':{p:copy.deepcopy(rows) for p in POLICIES},'folds_by_policy':{p:[] for p in POLICIES},
            'prior_evidence':{'r54_manifest_sha256':'a'*64,'r59_manifest_sha256':'b'*64,'r59_protocol_sha256':'c'*64,
                              'metrics':prior,'primary_rule':{'result':'no_support'},'known_iterations':[{'snapshot_sha256':'d'*64}]},
            'limits':['synthetic only'],'preparation_code_sha256':'e'*64}


def req(study,action,rid,candidate_id=None):
    state=study.observe();return {'request_id':rid,'observation_sha256':state['observation_sha256'],'action':action,
        'reason':'Synthetic decision','source_citation_ids':['p02-r54','p02-r59'],
        'evidence_action_ids':[state['actions'][-1]['id']] if state['actions'] else [],
        'parameters':{'candidate_id':candidate_id} if action=='run_candidate' else {}}


def fake_compute(snapshot,config,request,candidate):
    return {'schema_version':'configured-candidate-result-v1','request_sha256':fingerprint(request),'configuration_sha256':fingerprint(config),
            'inputs_sha256':config['inputs_sha256'],'candidate_id':candidate['id'],'alpha':candidate['alpha'],
            'summary':{'candidate_id':candidate['id'],'alpha':candidate['alpha'],'fit_count':140,'metrics':{'fixture':candidate['alpha']},
                       'scientific_validation':False,'model_weight_training':False}}


class Server:
    def __init__(self,steps):self.steps=iter(steps);self.bodies=[];self.credit_hold=None;self.http=SimpleNamespace(request=self.call)
    def assert_owner(self):pass
    def configure_budget(self,identity,remaining):pass
    def prepare(self,body):pass
    def call(self,route,body,timeout):
        self.bodies.append(copy.deepcopy(body));context=json.loads(body['messages'][1]['content']);action,candidate=next(self.steps)
        args={'observation_sha256':context['observation_sha256'],'reason':'Synthetic model decision','source_citation_ids':['p02-r54','p02-r59'],
              'evidence_action_ids':[context['latest_action_id']] if context['latest_action_id'] else []}
        if candidate is not None:args['candidate_id']=candidate
        return {'model':IDENTITY['remote_model'],'done':True,'prompt_eval_count':100,'eval_count':50,
                'message':{'role':'assistant','content':'','tool_calls':[{'type':'function','function':{'name':action,'arguments':args}}]}}


class ConfiguredIterationTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup);self.base=Path(tmp.name)
        patcher=patch.object(module.experiment_protocol,'prepare_inputs',return_value=inputs());self.prepare=patcher.start();self.addCleanup(patcher.stop)
        patcher=patch.object(module,'_validate_plan',return_value=None);patcher.start();self.addCleanup(patcher.stop)
        self.verify_original=module._verify_output
        patcher=patch.object(module,'_verify_output',return_value=None);patcher.start();self.addCleanup(patcher.stop)
        self.loop=module.ConfiguredCloudLoop(self.base/'study')
        self.loop.study.create('source','baseline','interaction',protocol())
        self.loop.configure(IDENTITY)

    def test_two_protocols_and_small_numeric_alpha_effect_without_source_rereads(self):
        other=module.ConfiguredStudy(self.base/'other');different=protocol([{'id':'mild','alpha':1.0},{'id':'heavier','alpha':30.0}])
        state=other.create('source','baseline','interaction',different)
        self.assertEqual([c['id'] for c in state['protocol']['candidates']],['mild','heavier'])
        rows=inputs()['rows_by_policy'][POLICIES[0]]
        a,_=module.chemotopo_iteration_study.candidate_predictions(rows,1.0)
        b,_=module.chemotopo_iteration_study.candidate_predictions(rows,30.0)
        self.assertGreater(max(abs(x-y) for x,y in zip(a,b)),1e-8)
        self.prepare.side_effect=AssertionError('original evidence must not be reread')
        self.assertEqual(self.loop.study.observe()['inputs_sha256'],fingerprint(inputs()))
        path=self.root_inputs();path.write_bytes(path.read_bytes()+b' ')
        with self.assertRaises(ResearchError):self.loop.study.observe()

    def root_inputs(self):return self.loop.study.root/'inputs.json'

    def test_partial_reservation_blocks_retry_and_other_work(self):
        request=req(self.loop.study,'run_candidate','one','light')
        with patch.object(module,'_compute',side_effect=RuntimeError('crash')) as compute:
            with self.assertRaises(ResearchError):self.loop.study.apply(request)
            with self.assertRaises(ResearchError):self.loop.study.apply(request)
            self.assertEqual(compute.call_count,1)
        state=self.loop.study.observe();self.assertEqual(state['budget']['fits_reserved'],140)
        with self.loop._connect() as con:_,spec,_=self.loop._state(con)
        with self.assertRaises(ResearchError):self.loop._request(state,3,[],spec)
        with self.assertRaises(ResearchError):self.loop.study.apply(req(self.loop.study,'run_candidate','two','strong'))

    def test_complete_artifact_recovers_without_refit(self):
        request=req(self.loop.study,'run_candidate','one','light');original=self.loop.study._write_complete
        def crash(*args):original(*args);raise RuntimeError('after complete manifest')
        with patch.object(module,'_compute',side_effect=fake_compute) as compute,patch.object(self.loop.study,'_write_complete',side_effect=crash):
            with self.assertRaises(ResearchError):self.loop.study.apply(request)
            result=self.loop.study.apply(request)
            self.assertEqual(result['action']['result']['summary']['candidate_id'],'light');self.assertEqual(compute.call_count,1)
            self.assertTrue(self.loop.study.apply(request)['replayed'])
        self.assertEqual(self.loop.study.observe()['budget']['fits_reserved'],140)

    def test_completed_artifact_rechecks_metrics_and_targets_without_refit(self):
        rows=[{'topography':t,'chemistry':c,'fold':t-1,'target':float(t+c)} for t in range(2,37) for c in range(25) if not(t<7 and c==24)]
        self.assertEqual(len(rows),870)
        folds=[{'fold':t-1,'held_out_topography':t,'test_keys':[[r['topography'],r['chemistry']] for r in rows if r['topography']==t],
                'train_keys':[[r['topography'],r['chemistry']] for r in rows if r['topography']!=t]} for t in range(2,37)]
        prior={p:{'interaction':{'pooled_mae':2.},'additive':{'pooled_mae':3.},'chemistry':{'pooled_mae':4.}} for p in POLICIES}
        frozen={'policies':list(POLICIES),'rows_by_policy':{p:rows for p in POLICIES},'folds_by_policy':{p:folds for p in POLICIES},'prior_evidence':{'metrics':prior}}
        config={'protocol':protocol(),'inputs_sha256':'a'*64}
        request={'request_id':'artifact','parameters':{'candidate_id':'light'}}
        metrics={p:module._metrics(rows,[r['target']+1 for r in rows],prior[p]) for p in POLICIES}
        artifact={'schema_version':'configured-candidate-result-v1','request_sha256':fingerprint(request),'configuration_sha256':fingerprint(config),
                  'inputs_sha256':'a'*64,'candidate_id':'light','alpha':10.,'summary':{'candidate_id':'light','alpha':10.,'fit_count':140,
                  'scientific_validation':False,'model_weight_training':False,'metrics':metrics},'folds':{p:folds for p in POLICIES},
                  'predictions':[{'policy':p,**row,'prediction':row['target']+1} for p in POLICIES for row in rows]}
        self.verify_original(artifact,frozen,config,request)
        tampered=copy.deepcopy(artifact);tampered['predictions'][0]['prediction']+=1
        with self.assertRaises(ResearchError):self.verify_original(tampered,frozen,config,request)

    def test_native_menu_feedback_duplicate_and_budget(self):
        server=Server([('run_candidate','light'),('run_candidate','strong'),('pause',None)])
        with patch.object(module,'_compute',side_effect=fake_compute):result=self.loop.run(server,max_new_requests=3,verified_weights=IDENTITY)
        self.assertEqual(result['study']['status'],'paused');self.assertEqual(result['study']['budget']['fits_reserved'],280)
        self.assertEqual([a['parameters'].get('candidate_id') for a in result['study']['actions'][:2]],['light','strong'])
        self.assertTrue(all(a['status']=='applied' for a in result['calls']))
        first=next(t for t in server.bodies[0]['tools'] if t['function']['name']=='run_candidate')
        second=next(t for t in server.bodies[1]['tools'] if t['function']['name']=='run_candidate')
        self.assertEqual(first['function']['parameters']['properties']['candidate_id']['enum'],['light','strong'])
        self.assertEqual(second['function']['parameters']['properties']['candidate_id']['enum'],['strong'])
        self.assertEqual({t['function']['name'] for t in server.bodies[2]['tools']},{'pause','stop'})
        self.assertEqual(json.loads(server.bodies[1]['messages'][1]['content'])['actions'][-1]['summary']['alpha'],10.)
        with self.assertRaises(ResearchError):self.loop.configure(IDENTITY,max_requests=6)


if __name__=='__main__':unittest.main()
