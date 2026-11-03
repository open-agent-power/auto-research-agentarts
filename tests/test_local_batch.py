"""Three bounded batch checks using tiny real core fixtures; no model, fit or PDF."""

import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import test_local_workbench as fixtures
from autoresearch import grouped_quality_adapter as grouped, tabular_quality_adapter as tabular, method_registry as registry
from autoresearch.contracts import ResearchError
from autoresearch.local_workbench import LocalWorkbench
from autoresearch.project_controller import ProjectController


class SimulatedCrash(BaseException):
    pass


class LocalBatchTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.manager = LocalWorkbench(self.root / "manager")
        self.counter = 0

    def project(self, limit=2):
        self.counter += 1
        body = fixtures.LocalWorkbenchTests.create_body(self, "create-" + str(self.counter))
        body["max_tool_calls"] = limit
        self.manager.create(body)
        return self.manager.binding()[0]

    def body(self, project, request_id, methods=None, receipts=None, maximum=2):
        state = project.status()
        return {"request_id": request_id, "project_id": state["id"], "expected_state_version": state["state_version"],
                "max_actions": maximum, "allowed_methods": methods if methods is not None else [tabular.TOOL_ID, grouped.TOOL_ID],
                "source_receipt_sha256s": receipts or [], "reason": "Explicit tiny-fixture batch authorization."}

    def assert_code(self, code, callback, *args):
        with self.assertRaises(ResearchError) as caught:
            callback(*args)
        self.assertEqual(caught.exception.code, code)

    def stage_source(self, project):
        folder = self.root / ("bundle-" + str(self.counter)); (folder / "sources").mkdir(parents=True)
        original = b"The reading field remains an unconfirmed declaration.\n"
        (folder / "sources" / "note.txt").write_bytes(original)
        import hashlib
        manifest = {"schema_version": "project-evidence-bundle-v1", "task_ref": project.evidence_task()["task_ref"],
                    "contributor": {"role": "teammate", "label": "Fixture contributor"},
                    "sources": [{"id": "note", "path": "sources/note.txt", "sha256": hashlib.sha256(original).hexdigest(),
                                 "url": "urn:test:batch-note", "media_type": "text/plain", "license_note": "Unknown fixture declaration"}],
                    "selections": [{"id": "one", "source_id": "note", "locator": {"kind": "text_lines", "value": "1"},
                                    "claim": "Unverified fixture interpretation"}], "remaining_questions": ["Confirm original collection records."]}
        (folder / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        return project.register_evidence(request_id="stage-source", bundle=folder)["receipt_snapshot_sha256"]

    def test_feedback_executes_two_methods_and_completed_replay_stays_frozen(self):
        project = self.project(); body = self.body(project, "batch-feedback")
        with patch.object(tabular, "execute", wraps=tabular.execute) as primary, patch.object(grouped, "execute", wraps=grouped.execute) as followup:
            result = self.manager.batch(body)
            self.assertEqual(result["status"], "waiting")
            self.assertEqual([step["method_id"] for step in result["batch"]["steps"]], [tabular.TOOL_ID, grouped.TOOL_ID])
            state = project.status()
            self.assertEqual((len(state["actions"]), len(state["controller_requests"]), state["budget"]["local_tool_calls_used"]), (2, 2, 2))
            self.assertEqual(state["actions"][1]["method_instance"]["parameters"]["based_on_action_id"], state["actions"][0]["id"])
            before = project.db.read_bytes()
            replay = LocalWorkbench(self.manager.root).batch(body)
            self.assertTrue(replay["replayed"]); self.assertEqual(replay["batch"], result["batch"])
            self.assertEqual(project.db.read_bytes(), before)
            self.assertEqual((primary.call_count, followup.call_count), (1, 1))
            # A later project selection cannot turn historical replay into continuation.
            self.project()
            self.assertEqual(self.manager.batch(body)["batch"], result["batch"])
            downloaded = self.manager.batch_record(body["request_id"])
            self.assertEqual(downloaded["body"], body); self.assertEqual(downloaded["status"], "completed")
            self.assertNotIn(str(self.root), json.dumps(downloaded))
            self.assert_code("IDEMPOTENCY_CONFLICT", self.manager.batch, {**body, "reason": "Changed grant"})

    def test_method_exact_receipt_and_cumulative_budget_authorization(self):
        identity_project = self.project()
        identity_body = self.body(identity_project, "orchestrator-identity")
        with patch("autoresearch.local_workbench.batch_code_identity", side_effect=["1" * 64, "2" * 64]):
            changed = self.manager.batch(identity_body)
        self.assertEqual((changed["status"], changed["batch"]["stop"]["code"]), ("needs_review", "CODE_CHANGED"))
        self.assertEqual(identity_project.status()["actions"], [])
        self.assertEqual(self.manager.batch_record(identity_body["request_id"])["status"], "incomplete")
        project = self.project()
        denied = self.manager.batch(self.body(project, "primary-only", [tabular.TOOL_ID]))
        self.assertEqual((denied["status"], len(denied["batch"]["steps"])), ("not_authorized", 1))
        self.assertEqual(len(project.status()["actions"]), 1)
        project = self.project(limit=1)
        limited = self.manager.batch(self.body(project, "budget-one", maximum=8))
        self.assertEqual((limited["status"], limited["batch"]["stop"]["code"]), ("blocked", "BUDGET_EXHAUSTED"))
        self.assertEqual(project.status()["budget"]["local_tool_call_limit"], 1)
        project = self.project()
        self.assert_code("METHOD_NOT_SUPPORTED", self.manager.batch, self.body(project, "arbitrary-method", ["arbitrary.shell"]))
        self.assert_code("SOURCE_NOT_REGISTERED", self.manager.batch, self.body(project, "unregistered", receipts=["f" * 64]))
        self.manager.batch(self.body(project, "one-action", maximum=1))
        self.assertEqual(len(project.status()["actions"]), 1)
        receipt = self.stage_source(project)
        before = project.status()
        unauthorized = self.manager.batch(self.body(project, "no-receipt-grant", [registry.SOURCE], []))
        self.assertEqual(unauthorized["status"], "not_authorized")
        self.assertEqual(project.status()["evidence_actions"], [])
        allowed = self.manager.batch(self.body(project, "exact-receipt-grant", [registry.SOURCE], [receipt]))
        self.assertEqual(len(allowed["batch"]["steps"]), 1)
        self.assertEqual(allowed["batch"]["steps"][0]["parameters"], {"receipt_snapshot_sha256": receipt})
        after = project.status()
        self.assertEqual((len(after["evidence_actions"]), after["budget"]["evidence_reads_used"]), (1, 1))
        self.assertEqual(after["budget"]["local_tool_calls_used"], before["budget"]["local_tool_calls_used"])

    def test_saved_intent_and_core_result_recovery_never_resend_unknown(self):
        project = self.project(); body = self.body(project, "pre-dispatch")
        save = self.manager._save_batch
        def stop_after_intent(record):
            save(record)
            if record["steps"] and record["steps"][-1]["parent"] is None:
                raise SimulatedCrash()
        with patch.object(self.manager, "_save_batch", side_effect=stop_after_intent), self.assertRaises(SimulatedCrash):
            self.manager.batch(body)
        context = ProjectController(project.root).selection_context()
        ProjectController(project.root).advance_selection(request_id="external-wait", expected_state_version=context["state_version"],
            proposal=fixtures.LocalWorkbenchTests.proposal(self, context))
        with patch.object(ProjectController, "advance", side_effect=AssertionError("Stale intent must not dispatch")):
            stale = self.manager.batch(body)
        self.assertEqual((stale["status"], stale["batch"]["stop"]["code"]), ("blocked", "STALE_STATE"))
        self.assertEqual(project.status()["actions"], [])

        project = self.project(); body = self.body(project, "core-committed")
        advance = ProjectController.advance
        def stop_after_core(controller, **kwargs):
            advance(controller, **kwargs)
            raise SimulatedCrash()
        with patch.object(tabular, "execute", wraps=tabular.execute) as primary:
            with patch.object(ProjectController, "advance", stop_after_core), self.assertRaises(SimulatedCrash):
                self.manager.batch(body)
            self.assertEqual(len(project.status()["actions"]), 1)
            self.assert_code("OPERATION_INCOMPLETE", self.manager.batch, {**body, "request_id": "cannot-replace"})
            recovered = LocalWorkbench(self.manager.root).batch(body)
            self.assertEqual(recovered["status"], "waiting"); self.assertEqual(primary.call_count, 1)
            self.assertEqual(len(project.status()["actions"]), 2)

        project = self.project(); body = self.body(project, "unknown-child")
        with patch.object(tabular, "execute", wraps=tabular.execute) as primary:
            with patch("autoresearch.research_project.write_once", side_effect=OSError("Controlled missing artifact")):
                unknown = self.manager.batch(body)
            self.assertEqual(unknown["status"], "needs_review")
            state = project.status(); parent = state["controller_requests"][-1]
            project.resume(request_id=parent["child_request_id"])
            self.assertEqual(project.status()["actions"][0]["status"], "unknown")
            with patch.object(ProjectController, "advance", side_effect=AssertionError("Unknown must not dispatch")):
                replay = self.manager.batch(body)
            self.assertEqual(replay["status"], "needs_review"); self.assertEqual(primary.call_count, 1)
            self.assertEqual(project.status()["budget"]["local_tool_calls_reserved"], 1)
            self.assert_code("OPERATION_INCOMPLETE", self.manager.batch, {**body, "request_id": "new-id-not-a-retry"})
            history = self.manager.describe()
            self.assertEqual(history["batches"][0]["record_status"], "incomplete")
            self.assertIn("batch", [item["command"] for item in history["pending_requests"]])


if __name__ == "__main__":
    unittest.main()
