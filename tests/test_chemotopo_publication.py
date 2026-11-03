import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from autoresearch.chemotopo_archive import archive_evidence
from autoresearch.chemotopo_cloud import ChemoTopoCloudLoop
from autoresearch.chemotopo_publication import load_publication, read_artifacts, ARTIFACT_LIMITS
from autoresearch.contracts import ResearchError, fingerprint
from test_chemotopo_cloud import IDENTITY, ServerFixture
from test_chemotopo_study import fixture_environment


class PublicationTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup); self.base = Path(temp.name)
        env = fixture_environment(); env.__enter__(); self.addCleanup(env.__exit__, None, None, None)
        self.source = self.base / 'study'; self.shared = self.base / 'shared'; self.receipt = self.base / 'receipt.json'
        loop = ChemoTopoCloudLoop(self.source); loop.study.create('fixture-source', 'Source policy research')
        loop.configure(IDENTITY, max_requests=8)
        loop.run(ServerFixture(['inspect_source', 'compare_policies', 'pause']), max_new_requests=3, verified_weights=IDENTITY)
        archive_evidence(self.source, self.shared, self.receipt)

    def test_publication_keeps_model_and_operator_memory_distinct(self):
        value = load_publication(self.source, archive_receipt=self.receipt, memory_workspace=self.shared)
        self.assertEqual(len(value['memory']['entries']), 0)
        self.assertEqual(len(value['archive']['entries']), 2)
        self.assertFalse(value['archive']['model_selected_remember'])
        self.assertNotIn(str(self.base), json.dumps(value))
        self.assertNotIn('downloads', value)
        self.assertEqual(value['snapshot_sha256'], fingerprint({k: v for k, v in value.items() if k != 'snapshot_sha256'}))
        receipt = json.loads(self.receipt.read_text()); receipt['source_snapshot_sha256'] = '0' * 64
        self.receipt.write_text(json.dumps(receipt))
        with self.assertRaises(ResearchError):
            load_publication(self.source, archive_receipt=self.receipt, memory_workspace=self.shared)

    def test_missing_or_changed_memory_cannot_be_presented_as_archived(self):
        with self.assertRaises(ResearchError):
            load_publication(self.source, archive_receipt=self.receipt)
        receipt = json.loads(self.receipt.read_text()); receipt['entries'][0]['record_sha256'] = '0' * 64
        self.receipt.write_text(json.dumps(receipt))
        with self.assertRaises(ResearchError):
            load_publication(self.source, archive_receipt=self.receipt, memory_workspace=self.shared)

    def test_report_binding_and_bytes_must_match_the_publication(self):
        value = load_publication(self.source)
        out = self.base / 'reports'; out.mkdir()
        files = {name: b'fixture' for name in ARTIFACT_LIMITS}
        files['research.json'] = json.dumps(value).encode()
        for name, data in files.items(): (out / name).write_bytes(data)
        manifest = {'schema_version': 'p02-publication-artifacts-v1', 'snapshot_sha256': value['snapshot_sha256'],
                    'files': {n: {'bytes': len(b), 'sha256': hashlib.sha256(b).hexdigest()} for n, b in files.items()}}
        (out / 'manifest.json').write_text(json.dumps(manifest))
        self.assertEqual(read_artifacts(out, value), files)
        (out / 'report.pdf').write_bytes(b'changed')
        with self.assertRaises(ResearchError): read_artifacts(out, value)


if __name__ == '__main__': unittest.main()
