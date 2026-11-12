import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from autoresearch.chemotopo_bundle import build_handoff
from autoresearch.chemotopo_publication import ARTIFACT_LIMITS
from autoresearch.chemotopo_iteration_report import ARTIFACT_LIMITS as ITERATION_LIMITS
from autoresearch.contracts import ResearchError, canonical, fingerprint
from autoresearch.snapshot_viewer import load_bundle


class HandoffTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name); self.baseline = self.root / 'baseline'; self.baseline.mkdir()
        self.publication = {'schema_version': 'p02-workbench-v1', 'case_id': 'P02-ChemoTopoChip',
                            'scientific_validation': False, 'prediction': None, 'comparison': None,
                            'archive': None, 'memory': {'entries': []}}
        self.publication['snapshot_sha256'] = fingerprint(self.publication)
        self.files = {name: b'sealed fixture' for name in ARTIFACT_LIMITS}
        self.files['research.json'] = canonical(self.publication).encode()
        for name, raw in self.files.items(): (self.baseline / name).write_bytes(raw)
        manifest = {'schema_version': 'p02-publication-artifacts-v1', 'snapshot_sha256': self.publication['snapshot_sha256'],
                    'files': {name: {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()} for name, raw in self.files.items()}}
        (self.baseline / 'manifest.json').write_text(json.dumps(manifest), encoding='utf-8')

    def test_postrun_bundle_binds_iteration_and_preserves_existing_downloads(self):
        directory=self.root/'iteration';directory.mkdir();postdir=self.root/'postrun';postdir.mkdir()
        view={'schema_version':'p02-iteration-view-v1','scientific_validation':False,
              'baseline_publication_sha256':self.publication['snapshot_sha256']}
        view['snapshot_sha256']=fingerprint(view)
        files={name:b'iteration fixture' for name in ITERATION_LIMITS};files['iteration.json']=canonical(view).encode()
        for name,raw in files.items():(directory/name).write_bytes(raw)
        manifest={'schema_version':'p02-iteration-artifacts-v1','snapshot_sha256':view['snapshot_sha256'],
                  'files':{name:{'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw)} for name,raw in files.items()}}
        (directory/'manifest.json').write_text(json.dumps(manifest))
        post={'schema_version':'p02-postrun-view-v1','iteration_snapshot_sha256':view['snapshot_sha256'],'scientific_validation':False}
        post['snapshot_sha256']=fingerprint(post);raw=canonical(post).encode()
        with patch('autoresearch.postrun_view.read_postrun_artifacts',side_effect=lambda path,iteration:{'postrun.json':raw}), \
             patch('autoresearch.chemotopo_bundle.render_iteration_comparison',return_value=b'<svg/>'):
            result=build_handoff(self.baseline,directory,self.root/'postrun-handoff',postrun_directory=postdir)
            values=load_bundle(result['directory'])
            self.assertEqual(values['data/postrun.json'],raw)
            self.assertEqual(result['postrun_snapshot_sha256'],post['snapshot_sha256'])
            self.assertEqual(values['reports/iteration-report.pdf'],files['report.pdf'])
            self.assertEqual(values['reports/baseline-reproduction.zip'],self.files['reproduction.zip'])
            self.assertIn(b'REQUEST_LIMIT',values['AGENT-START.md'])
            with self.assertRaises(ResearchError):build_handoff(self.baseline,None,self.root/'without-iteration',postrun_directory=postdir)
            post['iteration_snapshot_sha256']='a'*64;post.pop('snapshot_sha256');post['snapshot_sha256']=fingerprint(post)
            raw=canonical(post).encode()
            with self.assertRaises(ResearchError):build_handoff(self.baseline,directory,self.root/'wrong-postrun',postrun_directory=postdir)
            self.assertFalse((self.root/'wrong-postrun').exists())

    def test_sealed_only_build_preserves_downloads_without_opening_scientific_sources(self):
        with patch('autoresearch.chemotopo_experiment_evidence.attachment', side_effect=AssertionError('must not reconstruct sources')):
            result = build_handoff(self.baseline, None, self.root / 'handoff')
        values = load_bundle(result['directory'])
        self.assertEqual(values['reports/baseline-report.pdf'], self.files['report.pdf'])
        self.assertEqual(values['reports/baseline-reproduction.zip'], self.files['reproduction.zip'])
        self.assertIsNone(result['iteration_snapshot_sha256'])
        self.assertFalse(result['scientific_sources_reconstructed'])
        with zipfile.ZipFile(result['archive']) as z:
            self.assertEqual(set(z.namelist()), set(values) | {'bundle-manifest.json'})
            self.assertEqual(z.read('web/app.js'), values['web/app.js'])
        self.assertEqual((self.baseline / 'research.json').read_bytes(), self.files['research.json'])
        with self.assertRaises(ResearchError):
            build_handoff(self.baseline, None, self.root / 'handoff')

    def test_output_overlap_and_wrong_iteration_baseline_fail_before_writing(self):
        with self.assertRaises(ResearchError):
            build_handoff(self.baseline, None, self.baseline / 'nested')
        self.assertFalse((self.baseline / 'nested').exists())
        source = self.root / 'iteration'; source.mkdir()
        value = {'schema_version': 'p02-iteration-view-v1', 'baseline_publication_sha256': 'f' * 64}
        value['snapshot_sha256'] = fingerprint(value)
        (source / 'iteration.json').write_text(canonical(value), encoding='utf-8')
        with self.assertRaises(ResearchError):
            build_handoff(self.baseline, source, self.root / 'wrong')
        self.assertFalse((self.root / 'wrong').exists())


if __name__ == '__main__': unittest.main()
