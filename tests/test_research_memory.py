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

from autoresearch.contracts import ResearchError, fingerprint
from autoresearch.research_memory import ResearchMemory, derive_entries
import test_c01_research_outputs as fixture_module


class ResearchMemoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Reuse the explicitly synthetic numerical record fixture, not real case materials.
        fixture_module.C01ResearchOutputsTests.setUpClass()
        cls.record = copy.deepcopy(fixture_module.C01ResearchOutputsTests.record)
        cls.reproduction = copy.deepcopy(fixture_module.C01ResearchOutputsTests.reproduction)

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.memory = ResearchMemory(self.root/'memory')
        self.imported = self.memory.import_study(self.record, self.reproduction)
        self.scope = self.imported['scope']

    def test_import_preserves_provenance_roles_and_idempotency(self):
        result = self.memory.recall(self.scope)
        self.assertEqual(len(result['entries']), 5)
        self.assertEqual({entry['record']['kind'] for entry in result['entries']},
                         {'fit_observation', 'diagnostic_observation', 'agent_decision'})
        for entry in result['entries']:
            self.assertEqual(entry['record']['review_status'], 'derived_not_scientifically_reviewed')
            self.assertTrue(entry['record']['provenance']['references'])
        repeated = self.memory.import_study(self.record, self.reproduction)
        self.assertEqual(repeated['inserted'], 0)
        self.assertFalse(repeated['scientific_validation'])

    def test_lookup_is_read_only_and_bounded(self):
        before = hashlib.sha256(self.memory.db.read_bytes()).hexdigest()
        result = self.memory.recall(self.scope, kinds=['fit_observation'], limit=1)
        self.assertEqual(len(result['entries']), 1)
        self.assertEqual(result['entries'][0]['record']['kind'], 'fit_observation')
        self.assertEqual(hashlib.sha256(self.memory.db.read_bytes()).hexdigest(), before)
        self.assertFalse(self.memory.db.with_name('memory.sqlite-wal').exists())

    def test_scope_mismatch_cannot_reuse_numeric_observations(self):
        for key in self.scope:
            scope = {**self.scope, key: 'unmatched protocol' if key=='protocol' else '9'*64}
            with self.subTest(key=key):
                self.assertEqual(self.memory.recall(scope)['entries'], [])
        for scope in ({}, {**self.scope, 'extra': 'implied compatibility'}):
            with self.assertRaises(ResearchError):
                self.memory.recall(scope)

    def test_retirement_restore_history_and_old_request_replay(self):
        entry = self.memory.recall(self.scope)['entries'][0]['record']
        self.memory.set_status(entry['id'], 'retired', 'Needs source review', 'retire-one')
        self.assertNotIn(entry['id'], [e['record']['id'] for e in self.memory.recall(self.scope)['entries']])
        # Reimporting a source must not undo a deliberate withdrawal.
        self.memory.import_study(self.record, self.reproduction)
        retired = [e for e in self.memory.recall(self.scope, include_retired=True)['entries'] if e['record']['id']==entry['id']][0]
        self.assertEqual(retired['inclusion_status'], 'retired')
        self.assertEqual(retired['record'], entry)
        self.memory.set_status(entry['id'], 'active', 'Restore inclusion, no scientific promotion', 'restore-one')
        replay = self.memory.set_status(entry['id'], 'retired', 'Needs source review', 'retire-one')
        self.assertTrue(replay['replayed'])
        self.assertEqual(replay['current_status'], 'active')
        with self.assertRaises(ResearchError) as error:
            self.memory.set_status(entry['id'], 'retired', 'Different reason', 'retire-one')
        self.assertEqual(error.exception.code, 'IDEMPOTENCY_CONFLICT')

    def test_forged_numerical_inputs_do_not_create_memory(self):
        forged = copy.deepcopy(self.record)
        forged['fits'][0]['predictions'][0]['predicted'] += 100
        other = ResearchMemory(self.root/'forged')
        with self.assertRaises(ValueError):
            other.import_study(forged, self.reproduction)
        self.assertFalse(other.db.exists())

    def test_tampered_record_or_inclusion_history_is_rejected(self):
        for sql in ("UPDATE entries SET record_sha256='changed'", "UPDATE entries SET status='retired'",
                    "UPDATE events SET request_id=request_id || '-changed' WHERE ordinal=1"):
            with self.subTest(sql=sql):
                # Each tamper is rolled back after verification, preserving independent cases.
                original = self.memory.db.read_bytes()
                with closing(sqlite3.connect(self.memory.db)) as con:
                    with con:
                        con.execute(sql)
                with self.assertRaises(ResearchError):
                    self.memory.recall(self.scope)
                self.memory.db.write_bytes(original)

    def test_no_automatic_store_creation_for_empty_lookup(self):
        other = ResearchMemory(self.root/'not-created')
        self.assertEqual(other.recall(self.scope)['entries'], [])
        self.assertFalse(other.root.exists())

    def test_limits_and_unknown_inclusion_targets(self):
        for options in ({'limit': True}, {'limit': 9}, {'kinds': ['unverified_law']}, {'include_retired': 1}):
            with self.subTest(options=options), self.assertRaises(ResearchError):
                self.memory.recall(self.scope, **options)
        with self.assertRaises(ResearchError):
            self.memory.set_status('8'*64, 'active', 'not found', 'unknown')

    def test_capacity_does_not_break_idempotent_import_and_rolls_back_partial_import(self):
        with patch('autoresearch.research_memory.MAX_ENTRIES', 5):
            self.assertEqual(self.memory.import_study(self.record, self.reproduction)['inserted'], 0)
            revised = copy.deepcopy(self.record)
            reproduction = copy.deepcopy(self.reproduction)
            revised['archive_sha256'] = '7'*64
            reproduction['inputs']['source']['archive_sha256'] = '7'*64
            reproduction['inputs_sha256'] = fingerprint(reproduction['inputs'])
            with self.assertRaises(ResearchError) as error:
                self.memory.import_study(revised, reproduction)
            self.assertEqual(error.exception.code, 'MEMORY_LIMIT')
        self.assertEqual(len(self.memory.recall(self.scope)['entries']), 5)

    def test_extending_a_study_does_not_reactivate_retired_earlier_observations(self):
        prefix = copy.deepcopy(self.record)
        prefix.update(status='active', fits=prefix['fits'][:1], diagnostics=[], decisions=prefix['decisions'][:2])
        prefix['origin_observation_sha256'] = '6'*64
        memory = ResearchMemory(self.root/'incremental')
        imported = memory.import_study(prefix, self.reproduction)
        original = memory.recall(imported['scope'])['entries'][0]['record']
        memory.set_status(original['id'], 'retired', 'Withdraw while reviewing this observation', 'withdraw-prefix')
        memory.import_study(self.record, self.reproduction)
        all_entries = memory.recall(imported['scope'], include_retired=True)['entries']
        versions = [item for item in all_entries if item['record']['provenance']['action_id']=='fit-1']
        self.assertEqual(len(versions), 1)
        self.assertEqual(versions[0]['inclusion_status'], 'retired')
        self.assertEqual(len(versions[0]['source_versions']), 2)
        self.assertNotIn(original['id'], [item['record']['id'] for item in memory.recall(imported['scope'])['entries']])

    def test_altered_sql_history_ordinal_is_rejected_before_another_event(self):
        entry = self.memory.recall(self.scope)['entries'][0]['record']
        with closing(sqlite3.connect(self.memory.db)) as con:
            with con:
                con.execute('UPDATE events SET ordinal=11 WHERE entry_id=?', (entry['id'],))
        with self.assertRaises(ResearchError):
            self.memory.recall(self.scope)
        before = self.memory.db.read_bytes()
        with self.assertRaises(ResearchError):
            self.memory.set_status(entry['id'], 'retired', 'must fail before writing', 'after-corrupt-ordinal')
        self.assertEqual(self.memory.db.read_bytes(), before)

    def test_same_scoped_action_cannot_replace_its_immutable_payload(self):
        revised = copy.deepcopy(self.record)
        fit = revised['fits'][0]
        fit['summary']['metrics'][0]['target_label'] = 'Changed description of the same observation'
        # A resealed export with unchanged valid numeric results is still a conflicting observation.
        result = copy.deepcopy(fixture_module.C01ResearchOutputsTests.fit_results['fit-1'])
        result['summary'] = fit['summary']
        next(d for d in revised['decisions'] if d['id']=='fit-1')['result_sha256'] = fingerprint(result)
        with self.assertRaises(ResearchError) as error:
            self.memory.import_study(revised, self.reproduction)
        self.assertEqual(error.exception.code, 'EVIDENCE_CONFLICT')
        self.assertEqual(len(self.memory.recall(self.scope)['entries']), 5)

    def test_hardlinked_ledger_is_not_read_or_written(self):
        alias = self.root/'alias.sqlite'
        os.link(self.memory.db, alias)
        with self.assertRaises(ResearchError):
            self.memory.recall(self.scope)
        self.assertEqual(alias.read_bytes(), self.memory.db.read_bytes())
        alias.unlink()


if __name__ == '__main__':
    unittest.main()
