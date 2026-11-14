"""Synthetic original report publication/receipt interruption recovery."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import test_local_workbench as fixtures
from autoresearch import project_report, retrieval_lexical
from autoresearch.contracts import ResearchError, canonical, fingerprint
from autoresearch.local_workbench import LocalWorkbench


class ReportRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.manager = LocalWorkbench(self.root / 'manager')
        created = self.manager.create(fixtures.LocalWorkbenchTests.create_body(self))
        self.project_id = created['project_id']
        self.project, _ = self.manager.binding()
        self.body = {'request_id': 'report-original', 'project_id': self.project_id,
                     'expected_state_version': self.project.status()['state_version']}
        self.slot = fingerprint(self.body)
        self.enterContext(patch('sklearn.linear_model.Ridge.fit', side_effect=AssertionError('No fit')))
        self.enterContext(patch('sklearn.preprocessing.StandardScaler.fit', side_effect=AssertionError('No fit')))
        self.enterContext(patch('autoresearch.host_model_selection.run_claude_selection', side_effect=AssertionError('No model')))

    def assert_code(self, code, fn, *args):
        with self.assertRaises(ResearchError) as caught:
            fn(*args)
        self.assertEqual(caught.exception.code, code)

    def unfinished_complete_files(self):
        original_save = self.manager._save
        def interrupt(con, request_id, record):
            if request_id == self.body['request_id'] and record['status'] == 'completed':
                raise KeyboardInterrupt('Synthetic: files published, original receipt missing')
            return original_save(con, request_id, record)
        with patch.object(self.manager, '_save', side_effect=interrupt):
            with self.assertRaises(KeyboardInterrupt):
                self.manager.export(self.body)
        with self.manager._connect(readonly=True) as con:
            row = con.execute('SELECT record FROM requests WHERE id=?', (self.body['request_id'],)).fetchone()
            record = json.loads(row['record'])
        self.assertEqual(record['status'], 'preparing')
        self.assertEqual(record['intent']['recovery_version'], 'local-export-recovery-v1')
        root = self.manager.root / 'reports' / self.slot
        self.assertEqual(hashlib.sha256((root / 'manifest.json').read_bytes()).hexdigest(), record['intent']['prepared_manifest_sha256'])
        return root

    def test_same_id_adopts_original_files_without_any_recomputation(self):
        output = self.unfinished_complete_files()
        before_files = {p.name: p.read_bytes() for p in output.iterdir()}
        before_project = self.project.status()
        with patch.object(project_report, 'export_report', side_effect=AssertionError('No re-export')), \
             patch.object(project_report, 'collect_report', side_effect=AssertionError('No report collection')), \
             patch.object(project_report, '_pdf', side_effect=AssertionError('No render')), \
             patch.object(retrieval_lexical, 'metrics', side_effect=AssertionError('No scoring')):
            recovered = LocalWorkbench(self.manager.root).export(self.body)
            self.assertTrue(recovered['replayed'])
            self.assertEqual(recovered['status'], 'exported')
            self.assertTrue(self.manager.export(self.body)['replayed'])
        self.assertEqual({p.name: p.read_bytes() for p in output.iterdir()}, before_files)
        self.assertEqual(self.project.status(), before_project)
        self.assertEqual(len(list((self.manager.root / 'reports').iterdir())), 1)

    def test_unsealed_or_legacy_pending_never_adopts_and_blocks_new_id(self):
        self.unfinished_complete_files()
        with self.manager._connect() as con:
            row = con.execute('SELECT record FROM requests WHERE id=?', (self.body['request_id'],)).fetchone()
            record = json.loads(row['record'])
            del record['intent']['recovery_version']
            self.manager._save(con, self.body['request_id'], record)
        with patch.object(project_report, 'export_report', side_effect=AssertionError('No rerender')):
            self.assert_code('OPERATION_INCOMPLETE', self.manager.export, self.body)
            self.assert_code('OPERATION_INCOMPLETE', self.manager.export, {**self.body, 'request_id': 'new-slot'})
        self.assertEqual(len(list((self.manager.root / 'reports').iterdir())), 1)

    def test_prepared_version_without_manifest_digest_never_adopts(self):
        self.unfinished_complete_files()
        with self.manager._connect() as con:
            row = con.execute('SELECT record FROM requests WHERE id=?', (self.body['request_id'],)).fetchone()
            record = json.loads(row['record'])
            del record['intent']['prepared_manifest_sha256']
            self.manager._save(con, self.body['request_id'], record)
        with patch.object(project_report, 'export_report', side_effect=AssertionError('No rerender')):
            self.assert_code('OPERATION_INCOMPLETE', self.manager.export, self.body)
            self.assert_code('OPERATION_INCOMPLETE', self.manager.export, {**self.body, 'request_id': 'new-slot'})
        self.assertEqual(len(list((self.manager.root / 'reports').iterdir())), 1)

    def test_interruption_before_preparation_never_creates_second_attempt(self):
        with patch.object(project_report, '_pdf', side_effect=KeyboardInterrupt('Before preparing manifest')):
            with self.assertRaises(KeyboardInterrupt):
                self.manager.export(self.body)
        with self.manager._connect(readonly=True) as con:
            row = con.execute('SELECT record FROM requests WHERE id=?', (self.body['request_id'],)).fetchone()
            record = json.loads(row['record'])
        self.assertNotIn('prepared_manifest_sha256', record['intent'])
        self.assertFalse((self.manager.root / 'reports' / self.slot).exists())
        with patch.object(project_report, 'export_report', side_effect=AssertionError('No rerender')):
            self.assert_code('OPERATION_INCOMPLETE', self.manager.export, self.body)
            self.assert_code('OPERATION_INCOMPLETE', self.manager.export, {**self.body, 'request_id': 'new-slot'})

    def test_prepared_but_unpublished_slot_is_never_regenerated(self):
        output = self.manager.root / 'reports' / self.slot
        original_mkdir = Path.mkdir
        def interrupted(path, *args, **kwargs):
            if path == output:
                raise KeyboardInterrupt('After preparing digest before publication')
            return original_mkdir(path, *args, **kwargs)
        with patch.object(Path, 'mkdir', interrupted):
            with self.assertRaises(KeyboardInterrupt):
                self.manager.export(self.body)
        with self.manager._connect(readonly=True) as con:
            row = con.execute('SELECT record FROM requests WHERE id=?', (self.body['request_id'],)).fetchone()
            record = json.loads(row['record'])
        self.assertIn('prepared_manifest_sha256', record['intent'])
        self.assertFalse(output.exists())
        with patch.object(project_report, 'export_report', side_effect=AssertionError('No rerender')):
            self.assert_code('EVIDENCE_CHANGED', self.manager.export, self.body)
            self.assert_code('OPERATION_INCOMPLETE', self.manager.export, {**self.body, 'request_id': 'new-slot'})

    def test_incomplete_file_or_self_consistent_rewritten_manifest_is_rejected(self):
        output = self.unfinished_complete_files()
        original = (output / 'report.md').read_bytes()
        (output / 'report.md').unlink()
        self.assert_code('EVIDENCE_CHANGED', self.manager.export, self.body)
        (output / 'report.md').write_bytes(original + b'altered')
        manifest = json.loads((output / 'manifest.json').read_bytes())
        raw = (output / 'report.md').read_bytes()
        manifest['files']['report.md'] = {'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw)}
        (output / 'manifest.json').write_text(canonical(manifest))
        self.assert_code('EVIDENCE_CHANGED', self.manager.export, self.body)
        self.assert_code('OPERATION_INCOMPLETE', self.manager.export, {**self.body, 'request_id': 'replacement'})

    def test_code_identity_and_project_snapshot_drift_never_adopt(self):
        self.unfinished_complete_files()
        with patch('autoresearch.local_workbench.batch_code_identity', return_value='changed'):
            self.assert_code('CODE_CHANGED', self.manager.export, self.body)
        state = self.project.status()
        self.project.save_plan(request_id='later-plan', expected_state_version=state['state_version'],
            plan={'question': 'Fixture?', 'basis': 'Synthetic.', 'steps': 'Inspect.', 'expected_feedback': 'None.'}, reason='Fixture')
        self.assert_code('EVIDENCE_CHANGED', self.manager.export, self.body)

    def test_host_snapshot_drift_never_adopts(self):
        from autoresearch.host_model_selection import HostModelSelection
        self.unfinished_complete_files()
        host = HostModelSelection(self.project.root)
        host.prepare(request_id='later-host', provider='delegated', expected_state_version=self.project.status()['state_version'],
                     decision_limit=1, cli_budget_usd=.1, reason='Synthetic Host snapshot drift fixture.')
        with patch.object(project_report, 'export_report', side_effect=AssertionError('No rerender')):
            self.assert_code('EVIDENCE_CHANGED', self.manager.export, self.body)

    def test_old_completed_receipt_still_replays(self):
        result = self.manager.export(self.body)
        with self.manager._connect() as con:
            row = con.execute('SELECT record FROM requests WHERE id=?', (self.body['request_id'],)).fetchone()
            record = json.loads(row['record'])
            record['intent'] = {key: record['intent'][key] for key in ('project_id', 'snapshot_ref', 'state_version', 'report_slot')}
            self.manager._save(con, self.body['request_id'], record)
        with patch.object(project_report, 'export_report', side_effect=AssertionError('No rerender')):
            replay = self.manager.export(self.body)
        self.assertEqual(replay['manifest'], result['manifest'])
        self.assertTrue(replay['replayed'])

    def test_report_producer_callback_receives_copies(self):
        target = self.root / 'direct-report'
        def mutate(manifest, report):
            manifest['project_id'] = 'changed'
            report['project_id'] = 'changed'
        manifest = project_report.export_report(workspace=self.project.root, output=target, before_publish=mutate)
        report = json.loads((target / 'report.json').read_bytes())
        self.assertEqual(manifest['project_id'], self.project_id)
        self.assertEqual(report['project_id'], self.project_id)
        self.assertEqual((target / 'manifest.json').read_bytes(), canonical(manifest).encode())


if __name__ == '__main__':
    unittest.main()
