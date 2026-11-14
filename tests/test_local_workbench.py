"""Local-manager checks with tiny core fixtures and no network."""

import base64
import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from autoresearch.contracts import ResearchError, canonical
from autoresearch.local_workbench import LocalWorkbench
from autoresearch.project_controller import ProjectController
from autoresearch import tabular_quality_adapter as tabular, grouped_quality_adapter as grouped


class LocalWorkbenchTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory())) / "workbench"
        self.manager = LocalWorkbench(self.root)

    def create_body(self, request_id="create-1"):
        csv = b"batch,reading\na,0\na,2\nb,3\n"
        spec = {"schema_version": "tabular-quality-spec-v1", "file": "measurements.csv", "dataset_label": "Tiny manager fixture",
                "source_url": "urn:test:local-manager", "license_note": "Unknown fixture declaration", "sample_unit": "declared_record",
                "group_columns": ["batch"], "key_columns": [], "numeric_columns": ["reading"], "target_column": "reading",
                "target_unit": "declared_unit", "missing_tokens": ["", "NA"], "delimiter": ",",
                "provenance": {"origin_sha256": "a" * 64, "description": "Unverified fixture declaration"}}
        return {"request_id": request_id, "goal": "Check a tiny uploaded table", "budget_ref": "fixture-not-historical-spend",
                "max_tool_calls": 2, "input": {"file_name": "measurements.csv", "csv_base64": base64.b64encode(csv).decode("ascii"),
                                                "spec_base64": base64.b64encode(canonical(spec).encode("utf-8")).decode("ascii")}}

    def proposal(self, context, method_id=None):
        choice = {"kind": "wait"}
        if method_id:
            candidate = next(item for item in context["candidates"] if item["method_id"] == method_id)
            choice = {"kind": "execute", "candidate_id": candidate["id"]}
        return {"schema_version": "project-selection-proposal-v1", "context_sha256": context["context_sha256"],
                "provider": {"kind": "human", "label": "Explicit fixture selection"}, "choice": choice,
                "rationale": "Keep the frozen fixture input and original evaluation.", "evidence_citation_ids": []}

    def assert_code(self, code, callback, *args):
        with self.assertRaises(ResearchError) as caught:
            callback(*args)
        self.assertEqual(caught.exception.code, code)

    def test_create_replay_preserves_original_bytes_and_rejects_conflict_path(self):
        body = self.create_body(); created = self.manager.create(body)
        project, report = self.manager.binding()
        self.assertIsNone(report)
        packet = project._source(project.status())
        self.assertEqual(base64.b64decode(packet["source"]["bytes_base64"]), base64.b64decode(body["input"]["csv_base64"]))
        self.assertEqual(base64.b64decode(packet["spec_source"]["bytes_base64"]), base64.b64decode(body["input"]["spec_base64"]))
        replay = LocalWorkbench(self.root).create(body)
        self.assertEqual(replay["project_id"], created["project_id"]); self.assertTrue(replay["replayed"])
        self.assertEqual(len(self.manager.describe()["projects"]), 1)
        changed = copy.deepcopy(body); changed["goal"] = "Changed request"
        self.assert_code("IDEMPOTENCY_CONFLICT", self.manager.create, changed)
        unsafe = self.create_body("unsafe"); unsafe["input"]["file_name"] = "../outside.csv"
        self.assert_code("UNSAFE_PATH", self.manager.create, unsafe)
        self.assertFalse((self.root.parent / "outside.csv").exists())
        self.assertNotIn(str(self.root), canonical(self.manager.describe()))
        state = project.status()
        self.assertEqual((state["budget"]["model_requests_allowed"], state["budget"]["existing_cash_cap_cny"]), (0, 5))
        self.assertIsNone(state["budget"]["historical_spend_cny"])
        next((self.root / "inputs").glob("*/measurements.csv")).write_bytes(b"changed original")
        self.assert_code("EVIDENCE_CHANGED", self.manager.create, body)

    def test_advance_true_core_chain_replay_active_stale_and_unknown(self):
        created = self.manager.create(self.create_body()); project, _ = self.manager.binding()
        for request_id, method in (("advance-primary", tabular.TOOL_ID), ("advance-grouped", grouped.TOOL_ID)):
            context = ProjectController(project.root).selection_context()
            body = {"request_id": request_id, "project_id": created["project_id"], "expected_state_version": context["state_version"],
                    "proposal": self.proposal(context, method)}
            result = self.manager.advance(body)
            self.assertEqual(result["status"], "completed")
            self.assertTrue(self.manager.advance(body)["replayed"])
        state = project.status()
        self.assertEqual([item["command"] for item in state["actions"]], [tabular.TOOL_ID, grouped.TOOL_ID])
        self.assertEqual(state["budget"]["local_tool_calls_used"], 2)
        context = ProjectController(project.root).selection_context()
        stale = {"request_id": "stale", "project_id": state["id"], "expected_state_version": 0, "proposal": self.proposal(context)}
        self.assert_code("STALE_STATE", self.manager.advance, stale)
        second = self.manager.create(self.create_body("create-2"))
        self.assert_code("STALE_STATE", self.manager.advance, {**stale, "request_id": "old-form"})
        self.manager.select({"request_id": "select-original", "project_id": state["id"]})
        with project._writer(), project._connect() as con:
            raw = project._project(con)
            raw["source_requests"] = [{"request_id": "fixture-unknown", "status": "unknown"}]
            raw["state_version"] += 1
            project._save(con, raw)
        blocked = ProjectController(project.root).selection_context()
        self.assertIn("EXECUTION_UNKNOWN", [item["code"] for item in blocked["blockers"]])
        proposal = self.proposal(blocked); proposal["choice"] = {"kind": "execute", "candidate_id": "cannot-invent"}
        self.assert_code("SELECTION_BLOCKED", self.manager.advance,
                         {"request_id": "blocked", "project_id": state["id"], "expected_state_version": blocked["state_version"], "proposal": proposal})
        self.assertEqual(len(project.status()["actions"]), 2)
        self.assertNotEqual(second["project_id"], state["id"])

    def test_researcher_feedback_recovers_core_commit_and_preserves_project_binding(self):
        created = self.manager.create(self.create_body())
        project, _ = self.manager.binding()
        self.manager.save_plan({"request_id": "feedback-plan", "project_id": created["project_id"],
            "expected_state_version": project.status()["state_version"],
            "plan": {"question": "What does the declared unit mean?", "basis": "", "steps": "Read the measurement definition.",
                     "expected_feedback": "Confirm the declared scale before comparison."}, "reason": "Define the fixture route."})
        before = project.status()
        body = {"request_id": "feedback-manager", "project_id": created["project_id"], "expected_state_version": before["state_version"],
                "author": "Fixture teammate", "comment": "The definition needs source confirmation.", "next_step": "", "action_id": None}
        original_save = self.manager._save

        def interrupt_manager_receipt(con, request_id, record):
            if request_id == body["request_id"] and record["status"] == "completed":
                raise KeyboardInterrupt("Constructed interruption after durable feedback commit")
            return original_save(con, request_id, record)

        with patch.object(self.manager, "_save", side_effect=interrupt_manager_receipt):
            with self.assertRaises(KeyboardInterrupt):
                self.manager.record_feedback(body)
        committed = project.status()
        self.assertEqual(len(committed["researcher_feedback"]), 1)
        self.assertEqual(committed["researcher_feedback"][0]["plan_version"], 1)
        self.assertEqual(committed["budget"], before["budget"])
        recovered = LocalWorkbench(self.root).record_feedback(body)
        self.assertTrue(recovered["replayed"])
        self.assertEqual(recovered["feedback"], committed["researcher_feedback"][0])
        self.assertEqual(self.manager.record_feedback(body), recovered)
        self.assertEqual(project.status(), committed)
        changed = {**body, "comment": "Different feedback under the same ID"}
        self.assert_code("IDEMPOTENCY_CONFLICT", self.manager.record_feedback, changed)
        self.manager.create(self.create_body("feedback-second-project"))
        self.assert_code("STALE_STATE", self.manager.record_feedback, body)
        self.assertEqual(project.status(), committed)

    def test_export_replay_hash_verification_and_reload_binding(self):
        from autoresearch.project_report import export_report
        created = self.manager.create(self.create_body()); project, _ = self.manager.binding()
        body = {"request_id": "export-1", "project_id": created["project_id"], "expected_state_version": project.status()["state_version"]}
        db_before = project.db.read_bytes()
        with patch("autoresearch.project_report.export_report", wraps=export_report) as exporter:
            result = self.manager.export(body)
            self.assertEqual(result["status"], "exported")
            self.assertTrue(self.manager.export(body)["replayed"])
            self.assertEqual(exporter.call_count, 1)
            reloaded, report = LocalWorkbench(self.root).binding()
            self.assertEqual(reloaded.root, project.root); self.assertTrue((report / "manifest.json").is_file())
            self.assertEqual(project.db.read_bytes(), db_before)
            (report / "report.md").write_bytes(b"changed")
            self.assert_code("EVIDENCE_CHANGED", self.manager.export, body)
            self.assertEqual(exporter.call_count, 1)

    def test_interrupted_create_and_export_remain_pending_without_automatic_retry(self):
        created = self.manager.create(self.create_body()); project, _ = self.manager.binding()
        body = {"request_id": "export-partial", "project_id": created["project_id"], "expected_state_version": project.status()["state_version"]}
        def partial(*, workspace, output, before_publish=None):
            Path(output).mkdir(); (Path(output) / "report.json").write_bytes(b"partial")
            raise OSError("Controlled fixture interruption")
        with patch("autoresearch.project_report.export_report", side_effect=partial) as exporter:
            self.assert_code("WORKBENCH_OPERATION_FAILED", self.manager.export, body)
            self.assert_code("OPERATION_INCOMPLETE", self.manager.export, body)
            self.assertEqual(exporter.call_count, 1)
        creation = self.create_body("create-partial")
        with patch("autoresearch.local_workbench.ResearchProject.create", side_effect=OSError("Controlled fixture interruption")) as creator:
            self.assert_code("WORKBENCH_OPERATION_FAILED", self.manager.create, creation)
            self.assert_code("OPERATION_INCOMPLETE", self.manager.create, creation)
            self.assertEqual(creator.call_count, 1)
        description = LocalWorkbench(self.root).describe()
        self.assertEqual({item["request_id"] for item in description["pending_requests"]}, {"create-partial", "export-partial"})
        self.assertTrue(all(set(item) == {"request_id", "command", "status", "project_id"} for item in description["pending_requests"]))
        self.assertEqual(description["active_project_id"], created["project_id"])
        self.assertEqual(len(description["projects"]), 1)
        self.assertEqual(len(list((self.root / "inputs").glob("*/measurements.csv"))), 2)
        self.assertTrue(any((path / "report.json").read_bytes() == b"partial" for path in (self.root / "reports").iterdir()))


if __name__ == "__main__":
    unittest.main()
