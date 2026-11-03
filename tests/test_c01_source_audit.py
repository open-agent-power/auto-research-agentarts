import hashlib
import json
import os
from pathlib import Path
import unittest
from unittest.mock import patch

from autoresearch import c01
from autoresearch.c01_source_audit import audit_sources, DATASET_URL, file_url
from autoresearch.contracts import ResearchError
import test_c01 as fixtures


class C01SourceAuditTests(unittest.TestCase):
    def setUp(self):
        self.base = fixtures.C01Tests('test_loads_raw_workbook_caches_and_preserves_provenance')
        self.base.setUp()
        self.addCleanup(self.base.doCleanups)
        self.snapshot = self.base.root / 'snapshot'
        self.snapshot.mkdir()
        bundle = c01.load_archive(self.base.archive)
        rows = []
        for name in c01.ATTACHMENTS:
            payload = bundle['files'][name]
            (self.snapshot / name).write_bytes(payload)
            rows.append({'name': name, 'url': file_url(name), 'bytes': len(payload), 'sha256': hashlib.sha256(payload).hexdigest()})
        page = b'Synthetic test metadata, not an actual author-page verification.'
        (self.snapshot / 'mendeley-v1.md').write_bytes(page)
        self.manifest = {'schema_version': 'c01-upstream-snapshot-v1', 'fetched_at_utc': 'synthetic-test-only',
                         'dataset_url': DATASET_URL, 'dataset_doi': c01.DOI, 'dataset_version': 1,
                         'dataset_license': 'CC BY 4.0', 'license_check': 'fixture statement, not legal validation',
                         'files': rows, 'pages': [{'name': 'mendeley-v1.md', 'url': DATASET_URL,
                             'bytes': len(page), 'sha256': hashlib.sha256(page).hexdigest()}]}
        self.save()

    def save(self):
        (self.snapshot / 'manifest.json').write_text(json.dumps(self.manifest), encoding='utf-8')

    def run_audit(self): return audit_sources(self.base.archive, self.snapshot)

    def test_offline_comparison_keeps_formula_text_and_original_bytes(self):
        before = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in self.snapshot.iterdir()}
        with patch('socket.create_connection', side_effect=AssertionError('auditor must not access network')):
            result = self.run_audit()
        self.assertTrue(result['all_five_attachments_byte_equal'])
        self.assertEqual(len(result['files']), 5)
        self.assertFalse(result['scientific_validation'])
        self.assertEqual(result['sample_count_remains'], 8)
        self.assertEqual(result['fits_performed'], 0)
        self.assertEqual(before, {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in self.snapshot.iterdir()})
        # The original c01 parser exposes formula text; this audit never evaluates it.
        self.assertEqual(self.base.archive.read_bytes(), self.base.payload)
        self.assertTrue(any(cell['cell'] == 'L7' for cell in result['selected_upstream_cells']))
        self.assertEqual(next(cell for cell in result['selected_upstream_cells']
                              if cell['source'] == c01.MAIN and cell['cell'] == 'P5')['formula'],
                         'do_not_execute_this_formula()')

    def test_changed_capture_is_not_silently_compared_or_accepted(self):
        (self.snapshot / c01.MAIN).write_bytes(b'different bytes')
        with self.assertRaises(ResearchError) as error: self.run_audit()
        self.assertEqual(error.exception.code, 'SOURCE_CHANGED')

    def test_resealed_different_upstream_bytes_report_mismatch_not_pass(self):
        name = 'TNZST_Eng_Stress_vs_Eng_Strain.csv'
        payload = b'different upstream content'
        (self.snapshot / name).write_bytes(payload)
        row = next(row for row in self.manifest['files'] if row['name'] == name)
        row.update(bytes=len(payload), sha256=hashlib.sha256(payload).hexdigest())
        self.save()
        result = self.run_audit()
        self.assertFalse(result['all_five_attachments_byte_equal'])
        self.assertEqual(sum(not row['byte_equal'] for row in result['files']), 1)

    def test_missing_duplicate_or_redirecting_source_records_are_rejected(self):
        original = json.loads(json.dumps(self.manifest))
        for rows in (original['files'][:-1], original['files'][:-1] + [original['files'][0]]):
            self.manifest = {**original, 'files': rows}
            self.save()
            with self.assertRaises(ResearchError): self.run_audit()
        self.manifest = original
        self.manifest['pages'][0]['name'] = '../mendeley-v1.md'
        self.save()
        with self.assertRaises(ResearchError): self.run_audit()

    def test_hardlinked_source_and_wrong_author_dataset_url_rejected(self):
        alias = self.base.root / 'source-alias'
        os.link(self.snapshot / c01.MAIN, alias)
        with self.assertRaises(ResearchError) as error: self.run_audit()
        self.assertEqual(error.exception.code, 'UNSAFE_PATH')
        alias.unlink()
        self.manifest['files'][0]['url'] = 'https://example.invalid/looks-like-a-dataset'
        self.save()
        with self.assertRaises(ResearchError): self.run_audit()

    def test_changed_metadata_and_duplicate_json_keys_fail_closed(self):
        (self.snapshot / 'mendeley-v1.md').write_text('Changed license page', encoding='utf-8')
        with self.assertRaises(ResearchError) as error: self.run_audit()
        self.assertEqual(error.exception.code, 'SOURCE_CHANGED')
        (self.snapshot / 'manifest.json').write_text('{"files":[],"files":[]}', encoding='utf-8')
        with self.assertRaises(ResearchError): self.run_audit()


if __name__ == '__main__': unittest.main()
