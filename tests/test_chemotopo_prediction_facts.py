import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from autoresearch import chemotopo_cloud as cloud, chemotopo_study as study
from autoresearch.chemotopo_experiment_evidence import derived_prediction_facts
from autoresearch.contracts import ResearchError
from test_chemotopo_cloud import IDENTITY, response
from test_chemotopo_study import fixture_environment, request


def metrics():
    return {name:{'chemistry_ridge':{'pooled_mae':0.1+i*.01,'pooled_spearman_midrank':0.5},
                  'chemistry_geometry_ridge':{'pooled_mae':0.11+i*.01,'pooled_spearman_midrank':0.6}}
            for i,(name,_,_) in enumerate(study.rebuild.POLICIES)}


class PredictionFactsTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup)
        env=fixture_environment();env.__enter__();self.addCleanup(env.__exit__,None,None,None)
        patcher=patch.object(study.experiment,'attachment',return_value={'manifest_sha256':'a'*64,'protocol_sha256':'b'*64});patcher.start();self.addCleanup(patcher.stop)
        self.loop=cloud.ChemoTopoCloudLoop(Path(tmp.name)/'study')
        self.loop.study.create('fixture-source','Investigate input comparison',prediction_directory='fixture',research_focus='prediction_diagnostic')
        self.loop.configure(IDENTITY,max_requests=8)
        self.facts=derived_prediction_facts(metrics(),'a'*64,'b'*64)
        full={'summary':{'metrics':metrics(),'prediction_facts':self.facts,'fits_actor':'operator_script','metric_arithmetic_rechecked':True,'prediction_refit':False},
              'manifest_sha256':'a'*64,'protocol_sha256':'b'*64,'sources':[]}
        patcher=patch.object(study.experiment,'inspect_experiment',return_value=full);patcher.start();self.addCleanup(patcher.stop)

    def setup_prediction(self):
        self.loop.study.apply(request(self.loop.study,'inspect_source','source'))
        self.loop.study.apply(request(self.loop.study,'inspect_prediction','prediction'))
        return self.loop.study.observe()

    def test_r55_mixup_facts_are_on_model_input_axis_and_bound_to_scope(self):
        self.assertEqual(self.facts['comparison_axis'],'model_inputs');self.assertEqual(self.facts['primary_metric'],'pooled_mae')
        primary=self.facts['facts'][0]; secondary=self.facts['facts'][-1]
        self.assertEqual((primary['geometry_worse_policy_count'],primary['policy_count']),(4,4))
        self.assertEqual((secondary['geometry_higher_policy_count'],secondary['policy_count']),(4,4))
        self.assertEqual(self.facts,derived_prediction_facts(metrics(),'a'*64,'b'*64))
        self.assertNotEqual(primary['id'],derived_prediction_facts(metrics(),'c'*64,'b'*64)['facts'][0]['id'])
        changed=copy.deepcopy(metrics());changed['recorded_equal_batch']['chemistry_geometry_ridge']['pooled_mae']=0.01
        self.assertEqual(derived_prediction_facts(changed,'a'*64,'b'*64)['facts'][0]['geometry_worse_policy_count'],3)
        changed['recorded_equal_batch']['chemistry_geometry_ridge']['pooled_spearman_midrank']=None
        changed['positive_equal_batch']['chemistry_geometry_ridge']['pooled_mae']=changed['positive_equal_batch']['chemistry_ridge']['pooled_mae']+1e-14
        missing=derived_prediction_facts(changed,'a'*64,'b'*64)
        self.assertEqual(missing['facts'][-1]['uncomparable_count'],1)
        self.assertEqual(missing['facts'][0]['tie_count'],1)

    def test_focus_schema_fact_binding_rejects_wrong_namespaces_and_preserves_arguments(self):
        state=self.setup_prediction(); tools=cloud.affordances(state)['available_tools']
        self.assertIn('review_prediction',tools)
        self.assertTrue({'compare_policies','review_evidence','check_training_gate'}.isdisjoint(tools))
        self.assertEqual(state['research_focus'],'prediction_diagnostic')
        with self.loop._connect() as con:_,spec,_=self.loop._state(con)
        body=self.loop._request(state,6,[],spec)
        registry=json.loads(body['messages'][1]['content'])['id_registry']
        self.assertEqual({f['id'] for f in registry['prediction_facts']},{f['id'] for f in self.facts['facts']})
        primary=self.facts['facts'][0]['id']; prediction=state['actions'][-1]['id']
        reply=response(body,'review_prediction'); args=reply['message']['tool_calls'][0]['function']['arguments']
        args.update(fact_ids=[primary],decision='revise',hypothesis='Geometry may not improve MAE.',next_check='Check grouped uncertainty.')
        args['evidence_action_ids']=[prediction]
        decision=self.loop._parse_decision(reply,state,'review',body)
        self.assertEqual(decision['parameters']['fact_ids'],[primary])
        for bad in ([self.facts['facts'][1]['id']],['p02-workbook'],['p02-memory-fake']):
            forged=copy.deepcopy(reply);forged['message']['tool_calls'][0]['function']['arguments']['fact_ids']=bad
            before=copy.deepcopy(forged)
            with self.assertRaises(ResearchError):self.loop._parse_decision(forged,state,'bad',body)
            self.assertEqual(forged,before)
        result=self.loop.study.apply(decision)['action']['result']
        self.assertEqual(result['verified_metric_facts'][0]['geometry_worse_policy_count'],4)
        self.assertFalse(result['assertion_verified']);self.assertEqual(result['model_assertion']['decision'],'revise')
        self.assertLess(len(json.dumps(self.loop._request(self.loop.study.observe(),5,[],spec)).encode()),65536)

    def test_later_project_requires_prediction_and_latest_action_and_primary_fact(self):
        state=self.setup_prediction(); pred=state['actions'][-1]['id']
        fake={'inventory':{'object_count':1,'measurements':[]},'ome_filelist':[],'limitations':['fixture']}
        with patch.object(study.chemotopo_project,'inspect_project',return_value=fake):
            project_request=request(self.loop.study,'inspect_project','project'); project_request['evidence_action_ids']=[pred]
            self.loop.study.apply(project_request)
        state=self.loop.study.observe(); latest=state['actions'][-1]['id']
        with self.loop._connect() as con:_,spec,_=self.loop._state(con)
        body=self.loop._request(state,4,[],spec)
        tool=next(t['function'] for t in body['tools'] if t['function']['name']=='review_prediction')
        props=tool['parameters']['properties']; primary=self.facts['facts'][0]['id']
        self.assertEqual(props['fact_ids']['allOf'][0]['contains'],{'enum':[primary]})
        self.assertEqual(props['evidence_action_ids']['contains'],{'enum':[latest]})
        self.assertEqual(props['evidence_action_ids']['allOf'][0]['contains'],{'enum':[pred]})
        answer=response(body,'review_prediction'); args=answer['message']['tool_calls'][0]['function']['arguments']
        args.update(fact_ids=[primary],decision='pause',hypothesis='Unresolved',next_check='Inspect evidence',evidence_action_ids=[pred,latest])
        for evidence in ([latest],[pred]):
            bad=copy.deepcopy(answer);bad['message']['tool_calls'][0]['function']['arguments']['evidence_action_ids']=evidence
            with self.assertRaises(ResearchError):self.loop._parse_decision(bad,state,'bad',body)
        decision=self.loop._parse_decision(answer,state,'review',body)
        self.loop.study.apply(decision)
        self.assertEqual(self.loop.study.observe()['status'],'active')

    def test_native_context_bounds_chinese_prose_and_keeps_observation_unchanged(self):
        state=self.setup_prediction(); prose='研'*2000
        state['goal']=prose
        state['actions'][0]['reason']=prose; state['actions'][1]['reason']=prose
        for index in range(2,10):
            if index%2:
                action='review_prediction'; result={'verified_metric_facts':[self.facts['facts'][0]],'comparison_axis':'model_inputs',
                    'prediction_action_id':state['actions'][1]['id'],'model_assertion':{'decision':'continue','hypothesis':prose,'next_check':prose},
                    'assertion_verified':False,'scientific_approval':False}
            else:
                action='review_evidence'; result={'field':'zero_policy','finding':prose,'next_check':prose,'status':'unresolved','scientific_approval':False}
            state['actions'].append({'id':'p02-'+str(index),'ordinal':index+1,'action':action,'reason':prose,
                                     'result':result,'result_sha256':'c'*64})
        state['memory_context']['entries']=[{'id':'memory-'+str(i),'record_sha256':'d'*64,'payload':{'facts':self.facts},'source_versions':[]} for i in range(2)]
        before=copy.deepcopy(state)
        with self.loop._connect() as con:_,spec,_=self.loop._state(con)
        body=self.loop._request(state,4,[],spec)
        context=json.loads(body['messages'][1]['content'])
        self.assertLessEqual(len(json.dumps(body,ensure_ascii=False).encode('utf-8')),65536)
        self.assertEqual(context['goal'],prose)
        for action in context['actions'][2:]:
            result=action['result']; content=result.get('model_assertion',result)
            for field in (('hypothesis','next_check') if action['action']=='review_prediction' else ('finding','next_check')):
                self.assertTrue(content[field+'_truncated']);self.assertLessEqual(len(content[field+'_excerpt'].encode()),512)
        self.assertTrue(context['actions'][-1]['reason_truncated'])
        self.assertLessEqual(len(context['actions'][-1]['reason_excerpt'].encode()),768)
        self.assertEqual(state,before)

    def test_focus_is_frozen_and_default_source_mode_remains(self):
        with self.loop.study._connect() as con: config,state,_=self.loop.study._state(con)
        self.assertNotEqual(study.scope_for_source(config['prediction_attachment'],'prediction_diagnostic'),study.scope_for_source(config['prediction_attachment'],'source_policy'))
        old={**state,'research_focus':'source_policy'}
        self.assertNotIn('review_prediction',cloud.affordances(old)['available_tools'])
        self.assertIn('check_training_gate',cloud.affordances(old)['available_tools'])
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ResearchError):study.ChemoTopoStudy(Path(directory)/'x').create('fixture-source','missing attachment',research_focus='prediction_diagnostic')
        before=self.loop.study.observe(); req=request(self.loop.study,'compare_policies','forbidden')
        with self.assertRaises(ResearchError):self.loop.study.apply(req)
        self.assertEqual(before,self.loop.study.observe())


if __name__=='__main__':unittest.main()
