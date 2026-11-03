import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from autoresearch import chemotopo_cloud as cloud
from autoresearch import chemotopo_study as study
from autoresearch.contracts import ResearchError
from test_chemotopo_study import fixture_environment, request
from test_chemotopo_cloud import IDENTITY


class FollowupTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        env=fixture_environment(); env.__enter__(); self.addCleanup(env.__exit__,None,None,None)
        attachment={'manifest_sha256':'a'*64,'protocol_sha256':'b'*64}
        self.patcher=patch.object(study.experiment,'attachment',return_value=attachment);self.patcher.start();self.addCleanup(self.patcher.stop)
        self.root=Path(tmp.name)/'study';self.loop=cloud.ChemoTopoCloudLoop(self.root)
        self.loop.study.create('fixture-source','Follow up',prediction_directory='fixture-prediction')
        self.loop.configure(IDENTITY,max_requests=8)
        self.full={'summary':{'metrics':{'fixture':1},'fits_actor':'operator_script','prior_fits':420,'metric_arithmetic_rechecked':True,'prediction_refit':False},
                   'manifest_sha256':'a'*64,'protocol_sha256':'b'*64,'sources':[]}
        self.predpatch=patch.object(study.experiment,'inspect_experiment',return_value=self.full);self.predpatch.start();self.addCleanup(self.predpatch.stop)

    def apply(self,name):
        req=request(self.loop.study,name,name); state=self.loop.study.observe()
        relevant=[a['id'] for a in state['actions'] if a['action'] in {'inspect_source','inspect_project','inspect_prediction','compare_policies'}]
        req['evidence_action_ids']=relevant[-1:]
        return self.loop.study.apply(req)

    def test_source_prediction_memory_without_compare_and_compact_native_context(self):
        initial=self.loop.study.observe(); self.assertNotIn('inspect_prediction',cloud.affordances(initial)['available_tools'])
        self.apply('inspect_source'); state=self.loop.study.observe()
        self.assertIn('inspect_prediction',cloud.affordances(state)['available_tools'])
        self.apply('inspect_prediction'); state=self.loop.study.observe()
        self.assertIn('remember_evidence',cloud.affordances(state)['available_tools'])
        self.assertEqual(cloud.feedback_binding(state)['action'],'inspect_prediction')
        self.assertIn('p02-descriptors',[c['citation_id'] for c in state['citations']])
        with self.loop._connect() as con:_,spec,_=self.loop._state(con)
        body=self.loop._request(state,5,[],spec)
        self.assertLess(len(str(body).encode()),65536)
        self.apply('remember_evidence');state=self.loop.study.observe()
        self.assertEqual({e['payload']['type'] for e in state['memory_context']['entries']},{'source_qualification','prediction_diagnostic'})
        payload=next(e['payload'] for e in state['memory_context']['entries'] if e['payload']['type']=='prediction_diagnostic')
        self.assertFalse(payload['prediction_refit']);self.assertTrue(payload['metric_arithmetic_rechecked'])
        self.assertEqual(state['budget']['fits_used'],0)

    def test_full_action_context_after_project_prediction_and_memory_is_bounded(self):
        import json
        self.apply('inspect_source')
        metrics={policy:{recipe:{'pooled_mae':0.1,'pooled_rmse':0.2,'pooled_spearman_midrank':0.3,'macro_fold_mae':0.1,'skill_vs_oof_train_mean_mae':0.2}
                         for recipe in ('train_mean','chemistry_ridge','chemistry_geometry_ridge')}
                 for policy in ('recorded_equal_batch','positive_equal_batch','recorded_equal_section','positive_equal_section')}
        self.full['summary'].update({'metrics':metrics,
            'limits':['post hoc common coverage','known measured controls','not independent validation'],
            'keys':870,'folds':35,'prediction_rows':10440})
        channels=[{'Name':v,'ExcitationWavelength':'123.0'} for v in ('TL Brightfield','DAPI','Alexa Fluor 488','Alexa Fluor 546')]
        fake={'inventory':{'object_count':247,'measurements':[{'name':'test','groups':['Image','Experiment'],
              'features':{'Image':['X']*62,'Experiment':['Y']*14}}]},
              'ome_filelist':[{'filename':str(i)+'.czi','channels':channels,'dimensions':{'SizeX':'1500'}} for i in range(4)],'limitations':['fixture']}
        with patch.object(study.chemotopo_project,'inspect_project',return_value=fake):self.apply('inspect_project')
        self.apply('inspect_prediction'); self.apply('remember_evidence')
        state=self.loop.study.observe()
        with self.loop._connect() as con:_,spec,_=self.loop._state(con)
        body=self.loop._request(state,3,[],spec)
        self.assertLess(len(json.dumps(body,ensure_ascii=False).encode('utf-8')),65536)
        self.assertEqual(len(state['memory_context']['entries']),2)
        project=next(a for a in state['actions'] if a['action']=='inspect_project')
        self.assertIn('X',project['result']['summary']['measurement_groups'][0]['features']['Image'])

    def test_prediction_review_field_native_and_domain(self):
        self.apply('inspect_source'); self.apply('inspect_prediction')
        state=self.loop.study.observe()
        schema=cloud.schema_for(state)
        variant=next(v for v in schema['oneOf'] if v['properties']['action']['enum']==['review_evidence'])
        self.assertIn('prediction_diagnostic',variant['properties']['parameters']['properties']['field']['enum'])
        req=request(self.loop.study,'review_evidence','prediction-review',field='prediction_diagnostic',finding='Conditional proxy result',status='unresolved',next_check='Confirm endpoint')
        req['evidence_action_ids']=[state['actions'][-1]['id']]
        self.assertEqual(self.loop.study.apply(req)['action']['result']['field'],'prediction_diagnostic')

    def test_project_feedback_and_frozen_attachment_rechecked(self):
        self.apply('inspect_source')
        fake={'inventory':{'object_count':1,'measurements':[]},'ome_filelist':[],'limitations':['fixture']}
        with patch.object(study.chemotopo_project,'inspect_project',return_value=fake):self.apply('inspect_project')
        state=self.loop.study.observe();self.assertEqual(cloud.feedback_binding(state)['action'],'inspect_project')
        self.patcher.stop()
        with patch.object(study.experiment,'attachment',side_effect=ResearchError('EVIDENCE_CHANGED','tamper')):
            with self.assertRaises(ResearchError):self.loop.study.observe()


if __name__=='__main__':unittest.main()
