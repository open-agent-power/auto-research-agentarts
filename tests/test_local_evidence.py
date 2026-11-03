"""Three bounded upload/registration checks; fixture text is never extracted."""

import base64
import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import test_local_workbench as fixtures
from autoresearch.contracts import ResearchError
from autoresearch.local_workbench import LocalWorkbench
from autoresearch.project_controller import ProjectController
from autoresearch import source_evidence_adapter as reader, tabular_quality_adapter as tabular


class LocalEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory())) / "workbench"
        self.manager = LocalWorkbench(self.root)
        self.manager.create(fixtures.LocalWorkbenchTests.create_body(self))
        self.project, _ = self.manager.binding()
        context = ProjectController(self.project.root).selection_context()
        self.manager.advance({"request_id": "fixture-primary", "project_id": context["project_id"],
                              "expected_state_version": context["state_version"],
                              "proposal": fixtures.LocalWorkbenchTests.proposal(self, context, tabular.TOOL_ID)})

    def body(self, request_id="upload-1"):
        state = self.project.status()
        return {"request_id": request_id, "project_id": state["id"], "expected_state_version": state["state_version"],
                "task_ref": copy.deepcopy(state["evidence_task_ref"]), "contributor": {"role": "teammate", "label": "Fixture submitter"},
                "sources": [{"id": "notes", "file_name": "notes.txt", "bytes_base64": base64.b64encode(b"Original fixture note.\nSecond line.\n").decode("ascii"),
                             "url": "urn:test:notes", "media_type": "text/plain", "license_note": "Unknown fixture declaration"}],
                "selections": [{"id": "first-line", "source_id": "notes", "locator": {"kind": "text_lines", "value": "1"},
                                "claim": "Submitter interpretation remains unreviewed."}], "remaining_questions": ["Confirm the original group definition."]}

    def assert_code(self, code, callback, *args):
        with self.assertRaises(ResearchError) as caught:
            callback(*args)
        self.assertEqual(caught.exception.code, code)

    def test_register_and_reload_replay_keep_originals_without_capture_or_extract(self):
        body = self.body(); before = self.project.status()
        with patch.object(reader, "capture_bundle", wraps=reader.capture_bundle) as capture, \
             patch.object(reader, "execute", side_effect=AssertionError("Registration must never extract")) as execute:
            result = self.manager.register_evidence(body)
            self.assertEqual((result["command"], result["status"]), ("evidence", "registered"))
            receipt_sha = result["registration"]["receipt_snapshot_sha256"]
            after = self.project.status(); core_bytes = self.project.db.read_bytes()
            self.assertEqual(after["state_version"], before["state_version"] + 1)
            self.assertEqual((len(after["evidence_sources"]), len(after["evidence_actions"]), after["budget"]["evidence_reads_used"]), (1, 0, 0))
            self.assertEqual(after["knowledge_refs"], [])
            replay = LocalWorkbench(self.root).register_evidence(body)
            self.assertTrue(replay["replayed"]); self.assertEqual(capture.call_count, 1); execute.assert_not_called()
            self.assertEqual(self.project.db.read_bytes(), core_bytes)
            receipt, assets, _ = self.project._load_evidence_input(after, receipt_sha, task_ref=body["task_ref"])
            self.assertEqual(assets["notes"], base64.b64decode(body["sources"][0]["bytes_base64"]))
            self.assertEqual(receipt["sources"][0]["license_note"], body["sources"][0]["license_note"])
            changed = copy.deepcopy(body); changed["sources"][0]["url"] = "urn:test:changed"
            self.assert_code("IDEMPOTENCY_CONFLICT", self.manager.register_evidence, changed)
            next((self.root / "evidence-uploads").glob("*/sources/*")).write_bytes(b"Changed original")
            self.assert_code("EVIDENCE_CHANGED", self.manager.register_evidence, body)

    def test_filename_locator_task_version_unknown_code_and_size_boundaries(self):
        body = self.body()
        for field, value in (("file_name", "../outside.txt"), ("file_name", "CON.txt"), ("file_name", "bad?.txt")):
            changed = copy.deepcopy(body); changed["sources"][0][field] = value
            self.assert_code("UNSAFE_PATH", self.manager.register_evidence, changed)
        changed = copy.deepcopy(body); changed["selections"][0]["locator"]["kind"] = "python"
        self.assert_code("INVALID_LOCATOR", self.manager.register_evidence, changed)
        changed = copy.deepcopy(body); changed["selections"][0]["source_id"] = "absent"
        self.assert_code("INVALID_BUNDLE", self.manager.register_evidence, changed)
        changed = copy.deepcopy(body); changed["task_ref"]["based_on_action_id"] = "action-another"
        self.assert_code("TASK_MISMATCH", self.manager.register_evidence, changed)
        changed = copy.deepcopy(body); changed["expected_state_version"] += 1
        self.assert_code("STALE_STATE", self.manager.register_evidence, changed)
        with patch("autoresearch.research_project.code_identity", return_value="f" * 64):
            self.assert_code("CODE_CHANGED", self.manager.register_evidence, body)
        with patch.object(reader, "MAX_SOURCE_BYTES", 4):
            oversized = copy.deepcopy(body); oversized["sources"][0]["bytes_base64"] = base64.b64encode(b"12345").decode("ascii")
            self.assert_code("SOURCE_TOO_LARGE", self.manager.register_evidence, oversized)
        with patch.object(reader, "MAX_TOTAL_BYTES", 4):
            self.assert_code("SOURCE_TOO_LARGE", self.manager.register_evidence, body)
        self.assertFalse((self.root / "evidence-uploads").exists())
        with self.project._writer(), self.project._connect() as con:
            state = self.project._project(con); state["source_requests"] = [{"request_id": "fixture-unknown", "status": "unknown"}]
            state["state_version"] += 1; self.project._save(con, state)
        changed = self.body()
        self.assert_code("EXECUTION_UNKNOWN", self.manager.register_evidence, changed)
        self.assertFalse((self.root / "evidence-uploads").exists())

    def test_partial_requires_original_id_and_core_committed_registration_can_reconcile(self):
        body = self.body()
        with patch.object(self.manager, "_verify_evidence_registration", side_effect=OSError("Controlled post-registration interruption")):
            self.assert_code("WORKBENCH_OPERATION_FAILED", self.manager.register_evidence, body)
        after = self.project.status(); db_after = self.project.db.read_bytes()
        self.assertEqual(len(after["evidence_registrations"]), 1)
        self.assertEqual(self.manager.describe()["pending_requests"], [{"request_id": body["request_id"], "command": "evidence",
                                                                     "status": "incomplete", "project_id": body["project_id"]}])
        with patch.object(reader, "capture_bundle", side_effect=AssertionError("Recovery must not recapture")), \
             patch.object(reader, "execute", side_effect=AssertionError("Recovery must not extract")):
            recovered = LocalWorkbench(self.root).register_evidence(body)
        self.assertTrue(recovered["replayed"]); self.assertTrue(recovered["recovered"])
        self.assertEqual(self.project.db.read_bytes(), db_after)
        self.assertEqual(self.manager.describe()["pending_requests"], [])
        partial = self.body("upload-before-core")
        with patch("autoresearch.local_workbench.ResearchProject.register_evidence", side_effect=OSError("Controlled pre-registration interruption")) as register:
            self.assert_code("WORKBENCH_OPERATION_FAILED", self.manager.register_evidence, partial)
            self.assert_code("OPERATION_INCOMPLETE", self.manager.register_evidence, partial)
            self.assert_code("OPERATION_INCOMPLETE", self.manager.register_evidence, {**partial, "request_id": "replacement-not-allowed"})
            self.assertEqual(register.call_count, 1)
        self.assertEqual(len(self.project.status()["evidence_registrations"]), 1)
        self.assertEqual(len(self.project.status()["evidence_actions"]), 0)
        self.assertEqual(len(list((self.root / "evidence-uploads").glob("*/sources/*"))), 2)


if __name__ == "__main__":
    unittest.main()
