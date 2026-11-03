import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from autoresearch.chemotopo_iteration_report import ARTIFACT_LIMITS, POLICIES, _report, export_iteration, read_iteration_artifacts
from autoresearch.contracts import ResearchError


class IterationReportBoundaries(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup);self.root=Path(temp.name)
        self.view={'schema_version':'p02-iteration-view-v1','snapshot_sha256':'a'*64}

    def artifacts(self):
        out=self.root/'report';out.mkdir()
        files={name:b'fixture' for name in ARTIFACT_LIMITS};files['iteration.json']=json.dumps(self.view).encode()
        for name,raw in files.items():(out/name).write_bytes(raw)
        manifest={'schema_version':'p02-iteration-artifacts-v1','snapshot_sha256':self.view['snapshot_sha256'],
                  'files':{name:{'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw)} for name,raw in files.items()}}
        (out/'manifest.json').write_text(json.dumps(manifest))
        return out,files,manifest

    def test_exact_bytes_then_tampered_download_is_rejected(self):
        out,files,_=self.artifacts();self.assertEqual(read_iteration_artifacts(out,self.view),files)
        (out/'report.pdf').write_bytes(b'changed')
        with self.assertRaises(ResearchError):read_iteration_artifacts(out,self.view)

    def test_snapshot_and_rehashed_wrong_json_are_rejected(self):
        out,_,manifest=self.artifacts()
        with self.assertRaises(ResearchError):read_iteration_artifacts(out,{**self.view,'snapshot_sha256':'b'*64})
        wrong=json.dumps({**self.view,'goal':'different'}).encode();(out/'iteration.json').write_bytes(wrong)
        manifest['files']['iteration.json']={'sha256':hashlib.sha256(wrong).hexdigest(),'bytes':len(wrong)}
        (out/'manifest.json').write_text(json.dumps(manifest))
        with self.assertRaises(ResearchError):read_iteration_artifacts(out,self.view)

    def test_fresh_output_cannot_overlap_study_or_overwrite_directory(self):
        study=self.root/'study';study.mkdir()
        for target in (study,study/'nested',self.root):
            with self.assertRaises(ResearchError):export_iteration(study,{},target)
        existing=self.root/'existing';existing.mkdir()
        with self.assertRaises(ResearchError):export_iteration(study,{},existing)

    def test_zero_fit_report_does_not_invent_task_or_exhausted_candidates(self):
        from reportlab.platypus import Spacer
        view={**self.view,'baseline_publication_sha256':'b'*64,'goal':'自由停止检查目标',
              'execution':{'model':'fixture','requests_reserved':1,'applied_calls':1,'invalid_calls':0,
                           'completed_candidates':0,'completed_fits':0,'max_fits':280},
              'prior_evidence':{'metrics':{p:{r:{'pooled_mae':.1} for r in ('chemistry','additive','interaction')} for p in POLICIES}},
              'actions':[{'id':'stop','ordinal':1,'action':'stop','reason':'原始自由停止理由','model_selected':True}],
              'comparisons':[],'interpretation_notice':'模型理由未审定'}
        captured=[]
        def build(story,**_):captured.extend(item.getPlainText() for item in story if hasattr(item,'getPlainText'))
        with patch('autoresearch.chemotopo_iteration_report._font_name',return_value='Helvetica'), \
             patch('reportlab.platypus.Image',return_value=Spacer(1,1)), \
             patch('reportlab.platypus.SimpleDocTemplate.build',side_effect=build):
            _report(view,b'not-rendered')
        text='\n'.join(captured)
        self.assertIn(view['goal'],text)
        self.assertIn('本轮已完成0次CPU拟合',text)
        self.assertIn('本轮没有已完成的候选拟合',text)
        self.assertNotIn('至少检验一次',text)
        self.assertNotIn('候选耗尽后停止',text)
        self.assertNotIn('两个固定候选均已完成',text)
        self.assertNotIn('本轮280次',text)


if __name__=='__main__':unittest.main()
