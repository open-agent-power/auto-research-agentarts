import copy
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
from autoresearch import chemotopo_interaction, chemotopo_iteration_study as study, chemotopo_iteration_cloud as cloud
from autoresearch.contracts import ResearchError, fingerprint
from test_chemotopo_cloud import IDENTITY


def rows():
    return [{'topography':t,'chemistry':c,'geometry':[float(t*(j+1)) for j in range(10)],'target':float(t*.4+c),
             'fold':t-1,'chemistry_prediction':1.0,'additive_prediction':1.1} for t in (2,3,4,5) for c in (0,1)]


def fixture_evidence(*args):
    return {'manifest_sha256':'a'*64,'protocol_sha256':'b'*64,'baseline_manifest_sha256':'c'*64,
            'metrics':{'fixture':{'interaction':{'pooled_mae':1}}},'primary_rule':{'result':'no_support'}}


def fake_compute(config,request):
    return {'request_sha256':fingerprint(request),'configuration_sha256':config['configuration_sha256'],'action':request['action'],
            'summary':{'alpha':study.CANDIDATES[request['action']],'fit_count':140,'metric':'synthetic'}}


def decision(study_instance,action,rid):
    state=study_instance.observe()
    return {'request_id':rid,'observation_sha256':state['observation_sha256'],'action':action,'reason':'Synthetic test decision',
            'source_citation_ids':['p02-r54','p02-r59'],'evidence_action_ids':[state['actions'][-1]['id']] if state['actions'] else [],'parameters':{}}


class Server:
    def __init__(self,actions):self.actions=iter(actions);self.bodies=[];self.credit_hold=None;self.http=SimpleNamespace(request=self.call)
    def assert_owner(self):pass
    def configure_budget(self,identity,remaining):pass
    def prepare(self,body):pass
    def call(self,route,body,timeout):
        self.bodies.append(copy.deepcopy(body));context=json.loads(body['messages'][1]['content']); action=next(self.actions)
        args={'observation_sha256':context['observation_sha256'],'reason':'Synthetic model decision',
              'source_citation_ids':['p02-r54','p02-r59'],'evidence_action_ids':[context['latest_action_id']] if context['latest_action_id'] else []}
        return {'model':IDENTITY['remote_model'],'done':True,'prompt_eval_count':100,'eval_count':50,'message':{'role':'assistant','content':'','tool_calls':[{'type':'function','function':{'name':action,'arguments':args}}]}}


class IterationTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup);self.root=Path(tmp.name)/'study'
        for target,value in [(study.evidence,'inspect'),(study.evidence,'checked_files'),(study.chemotopo_experiment_evidence,'attachment')]:
            return_value=fixture_evidence() if value=='inspect' else ({'protocol_sha256':'b'*64} if value=='attachment' else {})
            patcher=patch.object(target,value,return_value=return_value);patcher.start();self.addCleanup(patcher.stop)
        self.verify_original=study._verify_complete
        patcher=patch.object(study,'_verify_complete',return_value=None);patcher.start();self.addCleanup(patcher.stop)
        self.loop=cloud.IterationCloudLoop(self.root);self.loop.study.create('source','baseline','interaction','Conditional numeric work')
        self.loop.configure(IDENTITY,max_requests=6)

    def test_alpha1_synthetic_matches_r59_features_and_predictions(self):
        data=rows();expected=chemotopo_interaction.grouped_interactions(data)
        actual,folds=study.candidate_predictions(data,1.0)
        np.testing.assert_allclose(actual,[r['interaction_prediction'] for r in expected['records']],rtol=0,atol=0)
        self.assertEqual(folds[0]['train_keys'],expected['folds'][0]['train_keys'])
        self.assertEqual(folds[0]['geometry_scaler'],expected['folds'][0]['geometry_scaler'])

    def test_partial_reservation_never_repeats_and_blocks_other_candidate(self):
        req=decision(self.loop.study,'fit_alpha10','one')
        with patch.object(study,'_calculate',side_effect=RuntimeError('interruption')) as compute:
            with self.assertRaises(ResearchError) as error:self.loop.study.apply(req)
            self.assertEqual(error.exception.code,'EVIDENCE_CHANGED')
            with self.assertRaises(ResearchError):self.loop.study.apply(req)
            self.assertEqual(compute.call_count,1)
        state=self.loop.study.observe();self.assertEqual(state['budget']['fits_reserved'],140)
        with self.loop._connect() as con:_,spec,_=self.loop._state(con)
        with self.assertRaises(ResearchError):self.loop._request(state,5,[],spec)
        with self.assertRaises(ResearchError):self.loop.study.apply(decision(self.loop.study,'fit_alpha100','other'))

    def test_complete_artifact_recovers_without_refit_and_replays(self):
        req=decision(self.loop.study,'fit_alpha10','one');original=self.loop.study._write_complete
        def crash_after_complete(*args):original(*args);raise RuntimeError('after manifest')
        with patch.object(study,'_calculate',side_effect=fake_compute) as compute,patch.object(self.loop.study,'_write_complete',side_effect=crash_after_complete):
            with self.assertRaises(ResearchError):self.loop.study.apply(req)
            result=self.loop.study.apply(req)
            self.assertEqual(compute.call_count,1);self.assertEqual(result['action']['action'],'fit_alpha10')
            self.assertTrue(self.loop.study.apply(req)['replayed'])
        self.assertEqual(self.loop.study.observe()['budget']['fits_reserved'],140)

    def test_recovery_artifact_rechecks_coverage_and_metric_arithmetic_without_fit(self):
        base=[{'topography':t,'chemistry':c,'fold':t-1,'target':float(t+c)} for t in range(2,37) for c in range(25) if not (t<7 and c==24)]
        self.assertEqual(len(base),870)
        refs=[]
        for t in range(2,37):
            refs.append({'fold':t-1,'held_out_topography':t,
                'test_keys':[[r['topography'],r['chemistry']] for r in base if r['topography']==t],
                'train_keys':[[r['topography'],r['chemistry']] for r in base if r['topography']!=t]})
        names=[p[0] for p in study.chemotopo_rebuild.POLICIES]
        prior={name:{'interaction':{'pooled_mae':2.},'additive':{'pooled_mae':3.},'chemistry':{'pooled_mae':4.}} for name in names}
        verified={'metrics':prior,'geometry':{},'baseline_verified':{'verified_folds':{name:refs for name in names}}}
        summary={'alpha':10.,'fit_count':140,'model_weight_training':False,'scientific_validation':False,
                 'metrics':{name:{'pooled_mae':1.,'pooled_rmse':1.,'pooled_spearman_midrank':1.,'macro_fold_mae':1.,'r59_alpha1_mae':2.,'r54_additive_mae':3.,'r54_chemistry_mae':4.} for name in names}}
        artifact={'action':'fit_alpha10','alpha':10.,'r59_manifest':'a'*64,'summary':summary,
                  'folds':{name:refs for name in names},'predictions':[{'policy':name,**r,'prediction':r['target']+1} for name in names for r in base]}
        config={'r59_manifest':'a'*64,'source':'source','baseline':'baseline','interaction':'interaction'}
        with patch.object(study.evidence,'inspect',return_value=verified),patch.object(study.chemotopo_interaction,'_baseline_rows',return_value=base):
            self.verify_original(artifact,config)
            altered=copy.deepcopy(artifact);altered['predictions'][0]['prediction']+=1
            with self.assertRaises(ResearchError):self.verify_original(altered,config)

    def test_native_journal_binding_menu_budget_and_feedback(self):
        server=Server(['fit_alpha10','fit_alpha100','pause'])
        with patch.object(study,'_calculate',side_effect=fake_compute):result=self.loop.run(server,max_new_requests=3,verified_weights=IDENTITY)
        self.assertEqual(result['study']['status'],'paused');self.assertEqual(result['study']['budget']['fits_reserved'],280)
        self.assertEqual([a['action'] for a in result['study']['actions']],['fit_alpha10','fit_alpha100','pause'])
        self.assertTrue(all(c['status']=='applied' for c in result['calls']))
        names=[{t['function']['name'] for t in b['tools']} for b in server.bodies]
        self.assertIn('fit_alpha10',names[0]);self.assertNotIn('fit_alpha10',names[1]);self.assertEqual(names[2],{'pause','stop'})
        state=result['study'];with_bad=decision(self.loop.study,'fit_alpha10','forged');with_bad['source_citation_ids']=['p02-r54']
        original=copy.deepcopy(with_bad)
        with self.assertRaises(ResearchError):study.validate_request(with_bad,state)
        self.assertEqual(with_bad,original)
        with self.assertRaises(ResearchError):self.loop.configure(IDENTITY,max_requests=7)


if __name__=='__main__':unittest.main()
