"""Synthetic conditional continuation through original project/manager actions."""
import base64
import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import test_retrieval_holdout as fixtures
from autoresearch import staged_relevance_adapter as staged, retrieval_holdout as holdout
from autoresearch.contracts import ResearchError, fingerprint
from autoresearch.local_workbench import LocalWorkbench
from autoresearch.project_controller import ProjectController


class ConditionalStagedContinuationTests(unittest.TestCase):
    def fixture(self, sign=None, *, execute_primary=True, met_audit=True, notmet_audit=False):
        temp = self.enterContext(tempfile.TemporaryDirectory())
        helper = fixtures.RetrievalHoldoutTests()
        self.addCleanup(helper.doCleanups)
        project, _, private = helper.fixture(sign)
        manager = LocalWorkbench(Path(temp) / "manager")
        imported = manager.import_project(request_id="import", workspace=project.root)
        project_id = imported["project_id"]
        manager.select({"request_id": "select", "project_id": project_id})
        project, _ = manager.binding()
        manager.register_holdout({"request_id": "holdout", "project_id": project_id,
            "expected_state_version": project.status()["state_version"], "holdout_base64": base64.b64encode(private).decode()})
        controller = ProjectController(project.root)
        context = controller.selection_context()
        candidate = next(c for c in context["candidates"] if c["method_id"] == staged.TOOL_ID)
        branches = {"condition_met": {"kind": "method", "method_id": staged.AUDIT_TOOL_ID} if met_audit else {"kind": "wait"},
                    "condition_not_met": {"kind": "method", "method_id": staged.AUDIT_TOOL_ID} if notmet_audit else {"kind": "wait"}}
        hypothesis = {"candidate_id": candidate["id"], "controller_request_id": "primary", "metric": "recall@20",
                      "operator": "gt", "threshold": 0, "branches": branches}
        project.register_hypothesis(request_id="prediction", expected_state_version=context["state_version"], hypothesis=hypothesis)
        context = controller.selection_context()
        proposal = {"schema_version": "project-selection-proposal-v1", "context_sha256": context["context_sha256"],
                    "provider": {"kind": "human", "label": "Synthetic fixture"},
                    "choice": {"kind": "execute", "candidate_id": candidate["id"]},
                    "rationale": "Run the original preregistered synthetic primary.", "evidence_citation_ids": []}
        if execute_primary:
            controller.advance_selection(request_id="primary", expected_state_version=context["state_version"], proposal=proposal)
            primary_id = project.status()["actions"][0]["id"]
        else:
            primary_id = "not-yet-available"
        body = {"request_id": "conditional", "project_id": project_id, "expected_state_version": project.status()["state_version"],
                "primary_action_id": primary_id, "reason": "Authorize conditional staged engineering continuation.",
                "registration_request_id": "prediction"}
        return manager, project, body

    def test_positive_runs_original_policy_audit_then_final_and_report(self):
        manager, project, body = self.fixture("positive")
        result = manager.continue_staged(body)
        self.assertEqual((result["schema_version"], result["status"], result["phase"]),
                         ("local-staged-continuation-v2", "completed", "done"))
        self.assertEqual(result["conditional"]["decision"], "audit")
        state = project.status()
        self.assertEqual([x["command"] for x in state["actions"]],
                         [staged.TOOL_ID, staged.AUDIT_TOOL_ID, holdout.FINAL_TOOL_ID])
        self.assertEqual((state["budget"]["local_tool_calls_used"], state["budget"]["new_model_requests"], state["budget"]["new_fits"]), (3, 0, 0))
        audit_id = result["steps"]["audit"]["body"]["request_id"]
        parent = ProjectController._parent(state, audit_id)
        self.assertEqual(parent["selection_context"], result["conditional"]["context"])
        self.assertEqual(parent["request"]["proposal"], result["conditional"]["proposal"])
        self.assertEqual(LocalWorkbench(manager.root).continue_staged(body), result)
        self.assertEqual(project.status(), state)

    def test_negative_zero_and_unknown_are_terminal_wait_without_lock(self):
        for sign, completed in (("negative", True), (None, True), (None, False)):
            with self.subTest(sign=sign, completed=completed):
                manager, project, body = self.fixture(sign, execute_primary=completed)
                before = project.status()
                result = manager.continue_staged(body)
                self.assertEqual((result["status"], result["phase"], result["result"]["status"]), ("completed", "waiting", "waiting"))
                self.assertEqual(result["steps"], {})
                self.assertEqual(result["conditional"]["feedback"]["outcome"], "condition_not_met" if completed else "unknown")
                self.assertEqual(project.status(), before)
                self.assertEqual(LocalWorkbench(manager.root).continue_staged(body), result)
                self.assertFalse((manager.root / "reports").exists())
                # A terminal wait must not keep the manager's pending gate locked.
                manager.select({"request_id": "still-selectable", "project_id": body["project_id"]})

    def test_already_completed_audit_is_not_reused_by_v2(self):
        manager, project, body = self.fixture("positive")
        context = ProjectController(project.root).selection_context()
        ProjectController(project.root).advance_feedback(request_id="previous-audit", registration_request_id="prediction",
                                                         expected_state_version=context["state_version"])
        body["expected_state_version"] = project.status()["state_version"]
        before = project.status()
        with self.assertRaises(ResearchError) as caught:
            manager.continue_staged(body)
        self.assertEqual(caught.exception.code, "CONDITION_NOT_SATISFIED")
        self.assertEqual(project.status(), before)
        self.assertFalse((manager.root / "reports").exists())

    def test_known_feedback_rejects_different_primary_for_wait_and_audit(self):
        for sign, met_audit, notmet_audit in (("positive", False, False), ("positive", True, False),
                                               ("negative", True, False), ("negative", True, True)):
            with self.subTest(sign=sign, met_audit=met_audit, notmet_audit=notmet_audit):
                manager, project, body = self.fixture(sign, met_audit=met_audit, notmet_audit=notmet_audit)
                body["primary_action_id"] = "action-other"
                before = project.status()
                with self.assertRaises(ResearchError) as caught:
                    manager.continue_staged(body)
                self.assertEqual(caught.exception.code, "EVIDENCE_CHANGED")
                self.assertEqual(project.status(), before)
                with manager._connect(readonly=True) as con:
                    self.assertIsNone(con.execute("SELECT 1 FROM requests WHERE id=?", (body["request_id"],)).fetchone())
                self.assertFalse((manager.root / "reports").exists())

    def test_interruption_after_original_audit_resumes_frozen_parent_without_redispatch(self):
        manager, project, body = self.fixture("positive")
        original = manager._save_staged_continuation
        def crash(record):
            if record["phase"] == "freeze" and record["steps"]["audit"]["status"] == "completed":
                raise KeyboardInterrupt("synthetic interruption")
            return original(record)
        with patch.object(manager, "_save_staged_continuation", side_effect=crash):
            with self.assertRaises(KeyboardInterrupt):
                manager.continue_staged(body)
        saved = manager.staged_continuation_record(body["request_id"])
        audit_id = saved["steps"]["audit"]["body"]["request_id"]
        self.assertEqual(ProjectController._parent(project.status(), audit_id)["status"], "completed")
        with patch.object(staged.AUDIT, "execute_saved", side_effect=AssertionError("must not re-audit")):
            resumed = LocalWorkbench(manager.root).continue_staged(body)
        self.assertEqual((resumed["status"], resumed["phase"]), ("completed", "done"))
        self.assertEqual(resumed["steps"]["audit"]["reference"]["parent_request_id"], audit_id)
        self.assertEqual(len([a for a in project.status()["actions"] if a["command"] == staged.AUDIT_TOOL_ID]), 1)

    def test_incomplete_primary_is_persisted_as_unknown_wait_without_action(self):
        manager, project, body = self.fixture(execute_primary=False)
        context = ProjectController(project.root).selection_context()
        candidate = next(c for c in context["candidates"] if c["method_id"] == staged.TOOL_ID)
        proposal = {"schema_version": "project-selection-proposal-v1", "context_sha256": context["context_sha256"],
                    "provider": {"kind": "human", "label": "Fixture"},
                    "choice": {"kind": "execute", "candidate_id": candidate["id"]},
                    "rationale": "Original primary request.", "evidence_citation_ids": []}
        with patch.object(ProjectController, "_dispatch", side_effect=KeyboardInterrupt("synthetic interruption")):
            with self.assertRaises(KeyboardInterrupt):
                ProjectController(project.root).advance_selection(request_id="primary", proposal=proposal,
                                                                   expected_state_version=context["state_version"])
        before = project.status()
        body["expected_state_version"] = before["state_version"]
        result = manager.continue_staged(body)
        self.assertEqual((result["status"], result["phase"], result["conditional"]["feedback"]["outcome"]),
                         ("completed", "waiting", "unknown"))
        self.assertEqual(project.status(), before)
        self.assertEqual(before["actions"], [])
        self.assertEqual(manager.continue_staged(body), result)

    def test_resealed_wrong_audit_parent_never_reaches_freeze(self):
        manager, project, body = self.fixture("positive")
        original = manager._save_staged_continuation
        def crash(record):
            if record["phase"] == "freeze" and record["steps"]["audit"]["status"] == "completed":
                raise KeyboardInterrupt("synthetic interruption")
            return original(record)
        with patch.object(manager, "_save_staged_continuation", side_effect=crash):
            with self.assertRaises(KeyboardInterrupt):
                manager.continue_staged(body)
        saved = manager.staged_continuation_record(body["request_id"])
        audit_id = saved["steps"]["audit"]["body"]["request_id"]
        with project._writer(), project._connect() as con:
            state = project._project(con)
            parent = next(item for item in state["controller_requests"] if item["request_id"] == audit_id)
            parent["request"]["proposal"]["provider"]["label"] = "Different resealed provider"
            parent["request_sha256"] = fingerprint(parent["request"])
            project._save(con, state)
        before = project.status()
        stopped = LocalWorkbench(manager.root).continue_staged(body)
        self.assertEqual((stopped["status"], stopped["phase"], stopped["stop"]["code"]),
                         ("incomplete", "audit", "EVIDENCE_CHANGED"))
        self.assertEqual(project.status(), before)
        self.assertNotIn("frozen_evaluation_strategy", before)
        self.assertFalse((manager.root / "reports").exists())


if __name__ == "__main__":
    unittest.main()
