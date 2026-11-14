"""Memory's binding-only path must not claim numerical validation or undo retirement."""
import copy
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from autoresearch.contracts import ResearchError, fingerprint
from autoresearch.research_memory import ResearchMemory, observation_id


class BindingMemoryTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.memory = ResearchMemory(self.root / "knowledge")
        self.scope = {"source_manifest_sha256": "1" * 64, "inputs_sha256": "2" * 64,
                      "analysis_code_sha256": "3" * 64, "protocol": "test-saved-byte-binding-v1"}
        entry = {"schema_version": "conditional-research-memory-v1", "kind": "diagnostic_observation",
                 "scope": self.scope, "review_status": "derived_not_scientifically_reviewed",
                 "numerical_recomputation": False, "payload": {"saved_value": 0.5},
                 "provenance": {"action_id": "saved-primary", "source_record_sha256": "4" * 64}}
        entry["id"] = observation_id(entry)
        self.entry = entry
        self.derived = {"scope": self.scope, "entries": [entry],
                        "validation": {"binding_checked": True, "numerical_recomputation": False}}

    def test_binding_receipt_and_event_do_not_claim_numerical_check(self):
        result = self.memory._import_derived(self.derived, verification="binding")
        self.assertIn("binding_validation", result)
        self.assertNotIn("numerical_validation", result)
        self.assertFalse(result["scientific_validation"])
        self.assertEqual(self.memory.recall(self.scope)["entries"][0]["record"], self.entry)
        with sqlite3.connect(self.memory.db) as con:
            event = json.loads(con.execute("SELECT record FROM events").fetchone()[0])
        self.assertIn("numerical correctness and scientific validity unreviewed", event["reason"])

    def test_existing_default_receipt_and_event_remain_compatible(self):
        result = self.memory._import_derived(self.derived)
        self.assertIn("numerical_validation", result)
        self.assertNotIn("binding_validation", result)
        with sqlite3.connect(self.memory.db) as con:
            event = json.loads(con.execute("SELECT record FROM events").fetchone()[0])
        self.assertEqual(event["reason"], "Imported numerically checked evidence; scientific validity unreviewed.")

    def test_binding_import_is_idempotent_and_never_restores_retired_record(self):
        self.memory._import_derived(self.derived, verification="binding")
        retired = self.memory.set_status(self.entry["id"], "retired", "Needs review", "retire-saved")
        self.assertEqual(retired["current_status"], "retired")
        repeated = self.memory._import_derived(self.derived, verification="binding")
        self.assertEqual(repeated["inserted"], 0)
        self.assertEqual(self.memory.recall(self.scope)["entries"], [])
        historical = self.memory.recall(self.scope, include_retired=True)["entries"]
        self.assertEqual(historical[0]["inclusion_status"], "retired")
        self.assertEqual(historical[0]["record"], self.entry)

    def test_binding_rejects_fit_kind_or_numerical_claim_before_store_creation(self):
        for update in ({"kind": "fit_observation"}, {"numerical_recomputation": True},
                       {"numerical_recomputation": 0}):
            with self.subTest(update=update):
                changed = copy.deepcopy(self.derived)
                changed["entries"][0].update(update)
                changed["entries"][0]["id"] = observation_id(changed["entries"][0])
                with self.assertRaises(ResearchError):
                    self.memory._import_derived(changed, verification="binding")
                self.assertFalse(self.memory.root.exists())

    def test_unknown_mode_rejected_before_store_creation(self):
        for mode in ("trust", None, True, []):
            with self.subTest(mode=mode), self.assertRaises(ResearchError):
                self.memory._import_derived(self.derived, verification=mode)
        self.assertFalse(self.memory.root.exists())

    def test_foreign_scope_is_not_current_evidence(self):
        self.memory._import_derived(self.derived, verification="binding")
        other = {**self.scope, "inputs_sha256": fingerprint("another saved result")}
        self.assertEqual(self.memory.recall(other)["entries"], [])

    def test_same_record_cannot_cross_verification_modes_in_either_direction(self):
        for first, second in (("numerical", "binding"), ("binding", "numerical")):
            memory = ResearchMemory(self.root / (first + "-first"))
            memory._import_derived(self.derived, verification=first)
            before = memory.db.read_bytes()
            with self.assertRaises(ResearchError) as error:
                memory._import_derived(self.derived, verification=second)
            self.assertEqual(error.exception.code, "EVIDENCE_CONFLICT")
            self.assertEqual(memory.db.read_bytes(), before)

    def test_changed_numerical_or_review_claim_cannot_reuse_scoped_action_id(self):
        numerical = copy.deepcopy(self.derived)
        numerical["entries"][0]["numerical_recomputation"] = True
        self.memory._import_derived(numerical)
        before = self.memory.db.read_bytes()
        for update, mode in (({"numerical_recomputation": False}, "binding"),
                             ({"review_status": "scientifically_approved"}, "numerical")):
            changed = copy.deepcopy(numerical)
            changed["entries"][0].update(update)
            self.assertEqual(changed["entries"][0]["id"], observation_id(changed["entries"][0]))
            with self.assertRaises(ResearchError):
                self.memory._import_derived(changed, verification=mode)
            self.assertEqual(self.memory.db.read_bytes(), before)

    def test_new_provenance_version_keeps_original_record_and_verification(self):
        self.memory._import_derived(self.derived, verification="binding")
        later = copy.deepcopy(self.derived)
        later["entries"][0]["provenance"]["source_record_sha256"] = "5" * 64
        result = self.memory._import_derived(later, verification="binding")
        self.assertEqual(result["inserted"], 0)
        recalled = self.memory.recall(self.scope)["entries"][0]
        self.assertEqual(recalled["record"], self.entry)
        self.assertEqual(len(recalled["source_versions"]), 2)


if __name__ == "__main__":
    unittest.main()
