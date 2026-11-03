import copy
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from autoresearch.c01_research import C01Research, code_identity
from autoresearch.c01_memory_context import MemoryContext, MAX_PROJECTION_BYTES, projection, scope_for_study
from autoresearch.contracts import canonical, fingerprint, ResearchError
from autoresearch.knowledge import build_index
from autoresearch.research_memory import ResearchMemory, observation_id
import test_c01_research_outputs as record_fixture
import test_knowledge as knowledge_fixture


class C01MemoryContextTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        record_fixture.C01ResearchOutputsTests.setUpClass()

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.research = copy.deepcopy(record_fixture.C01ResearchOutputsTests.record)
        self.reproduction = copy.deepcopy(record_fixture.C01ResearchOutputsTests.reproduction)
        self.memory = ResearchMemory(self.root / 'memory')
        self.memory.import_study(self.research, self.reproduction)
        self.index = self.root / 'knowledge.sqlite'
        build_index([knowledge_fixture.doc('test', 'Synthetic prior evidence only.', kind='reuse_note')], self.index)
        self.study = C01Research(self.root / 'study')
        with patch('autoresearch.c01_research.c01.load_archive', return_value=self.reproduction['inputs']):
            self.study.create('synthetic fixture archive', self.index, 'Current exact-scope mechanism fixture')
        self.context = MemoryContext(self.memory.root)

    def reseal(self, snapshot):
        snapshot['snapshot_sha256'] = fingerprint({key: value for key, value in snapshot.items()
                                                   if key not in {'snapshot_sha256', 'store_identity'}})

    def test_scope_comes_only_from_current_exported_reproduction(self):
        exported = self.study.export()['reproduction']
        with patch.object(self.study, 'export', wraps=self.study.export) as export:
            scope = scope_for_study(self.study)
        export.assert_called_once_with()
        self.assertEqual(scope, {'archive_sha256': exported['inputs']['source']['archive_sha256'],
                                 'inputs_sha256': exported['inputs_sha256'], 'analysis_code_sha256': code_identity(),
                                 'protocol': exported['protocol']})
        self.assertEqual(set(scope), {'archive_sha256', 'inputs_sha256', 'analysis_code_sha256', 'protocol'})

    def test_snapshot_filters_judgements_is_stable_and_does_not_change_bytes(self):
        before = self.memory.db.read_bytes()
        study_before = self.study.db.read_bytes()
        first = self.context.snapshot(self.study)
        second = self.context.snapshot(self.study)
        self.assertEqual(first, second)
        self.assertEqual(len(first['entries']), 4)
        self.assertEqual({item['record']['kind'] for item in first['entries']}, {'fit_observation', 'diagnostic_observation'})
        self.assertTrue(all(item['inclusion_status'] == 'active' for item in first['entries']))
        self.assertEqual(self.memory.db.read_bytes(), before)
        self.assertEqual(self.study.db.read_bytes(), study_before)
        self.assertEqual(first['store_identity'], self.context.identity())
        self.assertEqual(first['store_identity']['inode'], self.memory.db.stat().st_ino)
        self.assertFalse(first['scientific_validation'])

    def test_other_evaluator_scope_is_empty_without_rebinding_historical_memory(self):
        historical = copy.deepcopy(self.reproduction)
        historical['analysis_code_sha256'] = '0' * 64
        other = ResearchMemory(self.root / 'historical')
        other.import_study(self.research, historical)
        before = other.db.read_bytes()
        snapshot = MemoryContext(other.root).snapshot(self.study)
        self.assertEqual(snapshot['scope'], scope_for_study(self.study))
        self.assertEqual(snapshot['entries'], [])
        self.assertIn('not interchangeable', snapshot['empty_reason'])
        self.assertEqual(projection(snapshot)['entries'], [])
        self.assertEqual(other.db.read_bytes(), before)

    def test_retirement_restore_and_normal_sqlite_updates_keep_physical_identity(self):
        initial = self.context.snapshot(self.study)
        entry_id = initial['entries'][0]['record']['id']
        identity = self.context.identity()
        self.memory.set_status(entry_id, 'retired', 'Review eligibility', 'withdraw-context')
        retired = self.context.snapshot(self.study)
        self.assertNotIn(entry_id, [item['record']['id'] for item in retired['entries']])
        self.assertNotEqual(initial['snapshot_sha256'], retired['snapshot_sha256'])
        self.assertEqual(self.context.identity(), identity)
        # Saved snapshots remain saved data, not claims about instantaneous eligibility.
        with patch.object(ResearchMemory, 'recall', side_effect=AssertionError('projection must not reread a mutable store')):
            self.assertIn(entry_id, [item['id'] for item in projection(initial)['entries']])
        self.memory.set_status(entry_id, 'active', 'Explicit restoration, no scientific promotion', 'restore-context')
        restored = self.context.snapshot(self.study)
        self.assertIn(entry_id, [item['record']['id'] for item in restored['entries']])
        self.assertEqual(self.context.identity(), identity)

    def test_source_version_ids_and_complete_four_target_metrics_survive_projection(self):
        prefix = copy.deepcopy(self.research)
        prefix.update(fits=prefix['fits'][:1], diagnostics=[], decisions=prefix['decisions'][:2],
                      status='active', origin_observation_sha256='6' * 64)
        self.memory.import_study(prefix, self.reproduction)
        snapshot = self.context.snapshot(self.study)
        result = projection(snapshot)
        first_fit = next(item for item in result['entries'] if item['source_action_id'] == 'fit-1')
        self.assertEqual(set(first_fit['source_version_ids']), {fingerprint(prefix), fingerprint(self.research)})
        self.assertEqual(first_fit['source_versions_total'], 2)
        self.assertEqual(len(first_fit['payload']['metrics']), 4)
        original = self.research['fits'][0]
        self.assertEqual(first_fit['payload']['recipe'], original['recipe'])
        for projected, metric in zip(first_fit['payload']['metrics'], original['summary']['metrics']):
            self.assertEqual(projected, {key: metric[key] for key in ('target', 'mae', 'baseline_mae', 'r2')})
        encoded = canonical(result)
        self.assertNotIn(str(self.memory.db), encoded)
        self.assertNotIn('store_identity', encoded)
        self.assertNotIn(self.research['decisions'][-1]['reason'], encoded)
        self.assertTrue(result['ids_are_not_current_action_or_source_citation_ids'])
        self.assertFalse(result['scientific_validation'])
        self.assertFalse(result['may_execute'])

    def test_missing_linked_or_redirected_store_is_never_created_or_read(self):
        missing = self.root / 'missing'
        with self.assertRaises(ResearchError): MemoryContext(missing)
        self.assertFalse(missing.exists())
        alias = self.root / 'alias.sqlite'
        os.link(self.memory.db, alias)
        with self.assertRaises(ResearchError): self.context.identity()
        with self.assertRaises(ResearchError): MemoryContext(self.memory.root)
        alias.unlink()
        redirected = self.root / 'redirected'
        try: redirected.symlink_to(self.memory.root, target_is_directory=True)
        except OSError: return
        with self.assertRaises(ResearchError): MemoryContext(redirected)

    def test_corrupt_record_and_non_sqlite_store_fail_closed(self):
        with closing(sqlite3.connect(self.memory.db)) as con:
            with con: con.execute("UPDATE entries SET record_sha256='corrupted'")
        with self.assertRaises(ResearchError): self.context.snapshot(self.study)
        invalid = self.root / 'invalid'
        invalid.mkdir()
        (invalid / 'memory.sqlite').write_bytes(b'not a SQLite memory ledger')
        with self.assertRaises(ResearchError): MemoryContext(invalid).snapshot(self.study)

    def test_store_replacement_during_recall_is_detected_even_with_equal_bytes(self):
        original = self.context._store.recall
        def replace(*args, **kwargs):
            result = original(*args, **kwargs)
            payload = self.memory.db.read_bytes()
            self.memory.db.rename(self.root / 'retained-original.sqlite')
            self.memory.db.write_bytes(payload)
            return result
        with patch.object(self.context._store, 'recall', side_effect=replace):
            with self.assertRaises(ResearchError) as error: self.context.snapshot(self.study)
        self.assertEqual(error.exception.code, 'MEMORY_STORE_CHANGED')

    def test_projection_rejects_hash_tampering_and_automatic_judgements(self):
        snapshot = self.context.snapshot(self.study)
        snapshot['entries'][0]['record']['payload']['extra'] = 'unsealed change'
        with self.assertRaises(ResearchError): projection(snapshot)
        snapshot = self.context.snapshot(self.study)
        judgement = self.memory.recall(snapshot['scope'], kinds=['agent_decision'])['entries'][0]
        snapshot['entries'] = [judgement]
        self.reseal(snapshot)
        with self.assertRaises(ResearchError): projection(snapshot)

    def test_projection_byte_bound_reports_whole_entry_omission(self):
        snapshot = self.context.snapshot(self.study)
        base = next(item for item in snapshot['entries']
                    if item['record']['payload'].get('action') == 'correlation')
        entries = []
        for index in range(8):
            item = copy.deepcopy(base)
            action = 'prior-' + str(index)
            item['record']['provenance']['action_id'] = action
            for version in item['source_versions']: version['action_id'] = action
            for position, row in enumerate(item['record']['payload']['result']['leave_one_out']):
                row['sample_id'] = 'x' * 159 + str(position)
            item['record']['id'] = observation_id(item['record'])
            entries.append(item)
        snapshot['entries'] = entries
        self.reseal(snapshot)
        result = projection(snapshot)
        self.assertLessEqual(len(canonical(result).encode('utf-8')), MAX_PROJECTION_BYTES)
        self.assertGreater(result['entries_omitted'], 0)
        self.assertEqual(len(result['entries']) + result['entries_omitted'], 8)
        for item in result['entries']:
            self.assertEqual(len(item['payload']['leave_one_out']), 8)


if __name__ == '__main__': unittest.main()
