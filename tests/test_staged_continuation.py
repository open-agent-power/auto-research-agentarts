"""Synthetic staged continuation evidence checks; no models, external data or fits."""
import copy
import json
from pathlib import Path
import unittest
from unittest.mock import patch

import test_retrieval_holdout as holdout_fixtures
from autoresearch import project_selection, retrieval_holdout, staged_continuation, staged_relevance_adapter as staged
from autoresearch.contracts import ResearchError, canonical, fingerprint
from autoresearch.project_controller import ProjectController
from autoresearch.research_project import ResearchProject


class StagedContinuationTests(unittest.TestCase):
    fixture = holdout_fixtures.RetrievalHoldoutTests.fixture
    register = holdout_fixtures.RetrievalHoldoutTests.register
    primary = holdout_fixtures.RetrievalHoldoutTests.primary
    freeze = holdout_fixtures.RetrievalHoldoutTests.freeze

    def start(self):
        project, packet, raw = self.fixture()
        self.register(project, raw)
        primary = self.primary(project)
        return project, primary

    def observe(self, project, primary):
        with patch.object(retrieval_holdout, "_verified_private", side_effect=AssertionError("do not read final bytes")):
            return staged_continuation.inspect(project, project.status(), primary["id"])

    def execute(self, project, primary, method, request_id):
        context = ProjectController(project.root).selection_context()
        binding = {"action_id": primary["id"], "request_id": primary["request_id"], "result_sha256": primary["result_sha256"]}
        proposal = staged_continuation.selection_proposal(context, method, binding)
        response = ProjectController(project.root).advance_selection(request_id=request_id, proposal=proposal,
                      expected_state_version=context["state_version"])
        self.assertEqual(response["status"], "completed")
        return next(action for action in project.status()["actions"] if action["request_id"] == response["child_request_id"])

    def test_real_completed_stages_are_bound_read_only_without_redispatch(self):
        project, primary = self.start()
        before = project.status()
        value = self.observe(project, primary)
        self.assertEqual(value["primary"]["action_id"], primary["id"])
        self.assertEqual((value["audit"], value["freeze"], value["final"], value["required_tool_calls"]), (None, None, None, 2))
        self.assertEqual(value["blockers"], [])
        self.assertEqual(project.status(), before)
        audit = self.execute(project, primary, staged.AUDIT_TOOL_ID, "audit-parent")
        inspected = self.observe(project, primary)
        self.assertEqual(inspected["audit"]["action_id"], audit["id"])
        self.assertEqual(inspected["audit"]["parent_request_id"], "audit-parent")
        self.assertEqual(inspected["required_tool_calls"], 1)
        frozen, _ = self.freeze(project, primary)
        inspected = self.observe(project, primary)
        self.assertEqual(inspected["freeze"]["record_sha256"], frozen["record_sha256"])
        self.assertEqual(inspected["freeze"]["validation_delta_recall20"], 0)
        final = self.execute(project, primary, retrieval_holdout.FINAL_TOOL_ID, "final-parent")
        final_state = project.status()
        with patch.object(staged.AUDIT, "execute_saved", side_effect=AssertionError("no re-audit")), \
             patch.object(retrieval_holdout.FINAL, "execute_project", side_effect=AssertionError("no re-final")):
            inspected = self.observe(ResearchProject(project.root), primary)
        self.assertEqual(inspected["final"]["action_id"], final["id"])
        self.assertEqual(inspected["final"]["parent_request_id"], "final-parent")
        self.assertEqual(inspected["required_tool_calls"], 0)
        self.assertEqual(inspected["blockers"], [])
        self.assertEqual(project.status(), final_state)
        self.assertEqual((final_state["budget"]["local_tool_calls_used"], final_state["budget"]["new_fits"],
                          final_state["budget"]["new_model_requests"]), (3, 0, 0))

    def test_unknown_parent_is_read_only_and_blocking(self):
        project, primary = self.start()
        context = ProjectController(project.root).selection_context()
        binding = self.observe(project, primary)["primary"]
        proposal = staged_continuation.selection_proposal(context, staged.AUDIT_TOOL_ID, binding)
        with patch.object(staged.AUDIT, "execute_saved", side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                ProjectController(project.root).advance_selection(request_id="audit-parent", proposal=proposal,
                    expected_state_version=context["state_version"])
        before = project.status()
        with patch.object(ProjectController, "advance_selection", side_effect=AssertionError("never retry")):
            inspection = self.observe(project, primary)
        self.assertEqual(inspection["audit"]["status"], "running")
        self.assertTrue(any(row["code"] == "EXECUTION_UNKNOWN" for row in inspection["blockers"]))
        self.assertEqual(project.status(), before)
        self.assertEqual(before["budget"]["local_tool_calls_reserved"], 1)

    def test_unknown_final_never_reopens_private_or_dispatches(self):
        project, primary = self.start()
        self.execute(project, primary, staged.AUDIT_TOOL_ID, "audit-parent")
        self.freeze(project, primary)
        context = ProjectController(project.root).selection_context()
        proposal = staged_continuation.selection_proposal(context, retrieval_holdout.FINAL_TOOL_ID, self.observe(project, primary)["primary"])
        with patch.object(retrieval_holdout.FINAL, "execute_project", side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                ProjectController(project.root).advance_selection(request_id="final-parent", proposal=proposal,
                    expected_state_version=context["state_version"])
        before = project.status()
        with patch.object(ProjectController, "advance_selection", side_effect=AssertionError("no redispatch")):
            value = self.observe(project, primary)
        self.assertEqual(value["final"]["status"], "running")
        self.assertTrue(any(row["code"] == "EXECUTION_UNKNOWN" for row in value["blockers"]))
        self.assertEqual(project.status(), before)

    def test_existing_freeze_before_audit_is_not_reordered(self):
        project, primary = self.start()
        self.freeze(project, primary)
        self.execute(project, primary, staged.AUDIT_TOOL_ID, "late-audit")
        before = project.status()
        with self.assertRaises(ResearchError) as error:
            self.observe(project, primary)
        self.assertEqual(error.exception.code, "EVIDENCE_CHANGED")
        self.assertEqual(project.status(), before)

    def test_changed_artifact_and_changed_source_pin_are_rejected(self):
        project, primary = self.start()
        audit = self.execute(project, primary, staged.AUDIT_TOOL_ID, "audit-parent")
        artifact = project._artifact(audit)
        value = json.loads(artifact.read_bytes())
        value["tool_result"]["result"]["summary"]["splits"]["validation"]["arms"]["bm25"]["metrics"]["recall@20"] = 1
        artifact.write_text(canonical(value))
        with self.assertRaises(ResearchError):
            self.observe(project, primary)
        with patch.object(staged_continuation, "project_identity", return_value="0" * 64):
            with self.assertRaises(ResearchError) as error:
                self.observe(project, primary)
        self.assertEqual(error.exception.code, "CODE_CHANGED")

    def test_helper_only_code_drift_changes_project_identity_without_writes(self):
        project, primary = self.start()
        before = project.status()
        original = Path.read_bytes
        helper = Path(staged_continuation.__file__)
        def drift(path):
            content = original(path)
            return content + b"\n# synthetic helper drift\n" if path == helper else content
        with patch.object(Path, "read_bytes", drift):
            with self.assertRaises(ResearchError) as error:
                staged_continuation.inspect(project, project.status(), primary["id"])
        self.assertEqual(error.exception.code, "CODE_CHANGED")
        self.assertEqual(project.status(), before)

    def test_parent_and_sqlite_fingerprint_tampering_are_rejected(self):
        for change in ("parent_id", "decision", "database_fingerprint"):
            with self.subTest(change=change):
                project, primary = self.start()
                audit = self.execute(project, primary, staged.AUDIT_TOOL_ID, "audit-parent")
                with project._writer(), project._connect() as con:
                    if change == "database_fingerprint":
                        con.execute("UPDATE actions SET fingerprint=? WHERE request_id=?", ("f" * 64, audit["request_id"]))
                    else:
                        state = project._project(con)
                        parent = next(p for p in state["controller_requests"] if p["request_id"] == "audit-parent")
                        if change == "parent_id":
                            parent["request_id"] = "different-parent"
                        else:
                            parent["decision"]["selection_ref"]["candidate_id"] = "choice-foreign"
                            parent["decision_sha256"] = fingerprint(parent["decision"])
                        project._save(con, state)
                with self.assertRaises(ResearchError):
                    self.observe(project, primary)

    def test_wrong_candidate_tampered_context_and_budget_exhaustion(self):
        project, primary = self.start()
        state = project.status()
        binding = self.observe(project, primary)["primary"]
        context = ProjectController(project.root).selection_context()
        with self.assertRaises(ResearchError):
            staged_continuation.selection_proposal(context, retrieval_holdout.FINAL_TOOL_ID, binding)
        damaged = copy.deepcopy(context)
        damaged["state_version"] += 1
        with self.assertRaises(ResearchError):
            staged_continuation.selection_proposal(damaged, staged.AUDIT_TOOL_ID, binding)
        forged_state = copy.deepcopy(state)
        forged_state["budget"]["local_tool_call_limit"] = 999
        with self.assertRaises(ResearchError) as stale:
            staged_continuation.inspect(project, forged_state, primary["id"])
        self.assertEqual(stale.exception.code, "STALE_STATE")
        modified = copy.deepcopy(context)
        del modified["context_sha256"]
        audit = next(row for row in modified["candidates"] if row["method_id"] == staged.AUDIT_TOOL_ID)
        audit["parameters"]["based_on_result_sha256"] = "f" * 64
        modified = project_selection.seal_context(modified)
        with self.assertRaises(ResearchError):
            staged_continuation.selection_proposal(modified, staged.AUDIT_TOOL_ID, binding)
        # Simulate a legitimate single-tool allowance; no new project action or allowance is created.
        with project._writer(), project._connect() as con:
            stored = project._project(con)
            stored["budget"]["local_tool_call_limit"] = 2
            project._save(con, stored)
        value = self.observe(project, primary)
        self.assertEqual((value["available_tool_calls"], value["required_tool_calls"]), (1, 2))
        self.assertTrue(any(row["code"] == "BUDGET_EXHAUSTED" for row in value["blockers"]))


if __name__ == "__main__":
    unittest.main()
