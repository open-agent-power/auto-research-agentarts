"""Plan host requests use real fixture feedback and explicit adoption without model transport."""

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import test_local_workbench as fixtures
from autoresearch.contracts import ResearchError, canonical
from autoresearch.host_model_report import capture_host_models
from autoresearch.host_model_selection import HostModelSelection
from autoresearch.local_workbench import LocalWorkbench
from autoresearch.project_controller import ProjectController


class HostPlanSelectionTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        manager = LocalWorkbench(self.root / "workbench")
        body = fixtures.LocalWorkbenchTests.create_body(self)
        body["max_tool_calls"] = 1
        manager.create(body)
        self.project, _ = manager.binding()
        self.plan = {"question": "How should the declared readings be interpreted?", "basis": "Constructed table input",
                     "steps": "Inspect table quality before comparing groups.", "expected_feedback": "Identify missing and zero values."}
        self.project.save_plan(request_id="original-plan", expected_state_version=self.project.status()["state_version"],
                               plan=self.plan, reason="Record the fixture's initial route.")
        self.project.step(request_id="actual-fixture-quality", expected_state_version=self.project.status()["state_version"])
        self.journal = HostModelSelection(self.project.root)

    def specification(self, request_id="plan-one"):
        return {"request_id": request_id, "provider": "delegated", "purpose": "plan",
                "expected_state_version": self.project.status()["state_version"], "decision_limit": 2,
                "cli_budget_usd": 0.1, "reason": "Two prospective fixture plan requests"}

    def propose(self, specification):
        record = self.journal.prepare(**specification)
        arguments = {"plan": {**self.plan, "steps": "Review the recorded zero value and source provenance before interpreting group differences."},
                     "reason": "The actual quality feedback distinguishes zero values from missing readings.",
                     "feedback_action_ids": [self.project.status()["actions"][0]["id"]],
                     "expected_improvement": "Keep the next interpretation tied to the observed quality result."}
        response = self.root / (specification["request_id"] + ".json")
        response.write_bytes(canonical(arguments).encode("utf-8"))
        self.assertEqual(self.journal.import_response(request_id=record["request_id"], response_file=response)["status"], "received")
        return self.journal.consume(request_id=record["request_id"])

    def test_plan_proposal_adoption_recovers_committed_revision_and_preserves_usage(self):
        before = self.project.status()
        self.assertEqual(ProjectController(self.project.root).selection_context()["candidates"], [])
        specification = self.specification()
        proposed = self.propose(specification)
        self.assertEqual(proposed["status"], "proposed")
        self.assertEqual(self.project.status(), before)
        self.assertEqual(self.journal.consume(request_id="plan-one"), proposed)
        original_save = self.journal._save

        def interrupt_after_plan_commit(state):
            if state["requests"]["plan-one"]["status"] == "applied":
                raise KeyboardInterrupt("Constructed interruption after the plan was committed")
            original_save(state)

        with patch.object(self.journal, "_save", side_effect=interrupt_after_plan_commit):
            with self.assertRaises(KeyboardInterrupt):
                self.journal.adopt_plan(request_id="plan-one")
        committed = self.project.status()
        self.assertEqual(len(committed["plan_revisions"]), 2)
        self.assertEqual(self.journal.status(request_id="plan-one")["status"], "proposed")
        with self.assertRaises(ResearchError) as caught:
            self.journal.reject_plan(request_id="plan-one", reason="Attempt rejection after committed adoption")
        self.assertEqual(caught.exception.code, "PLAN_ALREADY_ADOPTED")
        reloaded = HostModelSelection(self.project.root)
        applied = reloaded.adopt_plan(request_id="plan-one")
        self.assertEqual((applied["status"], applied["outcome"]["kind"]), ("applied", "plan_revision"))
        self.assertTrue(applied["outcome"]["replayed"])
        self.assertEqual(reloaded.adopt_plan(request_id="plan-one"), applied)
        self.assertEqual(reloaded.prepare(**specification), applied)
        self.assertEqual(self.project.status(), committed)
        self.assertEqual(committed["actions"], before["actions"])
        self.assertEqual(committed["budget"], before["budget"])
        self.assertEqual(reloaded.status()["usage"]["decision_slots_used"], 1)
        captured = capture_host_models(self.project.root)
        self.assertEqual(captured["records"][0]["proposal"], proposed["proposal"])
        self.assertEqual(captured["records"][0]["outcome"]["research_plan"], committed["plan_revisions"][-1])

    def test_rejection_stale_adoption_and_grant_exhaustion_preserve_records(self):
        before = self.project.status()
        proposed = self.propose(self.specification())
        rejected = self.journal.reject_plan(request_id="plan-one", reason="Keep the current route for this fixture.")
        self.assertEqual(rejected["status"], "rejected")
        self.assertEqual(rejected["proposal"], proposed["proposal"])
        self.assertEqual(self.journal.reject_plan(request_id="plan-one", reason=rejected["rejection_reason"]), rejected)
        self.assertEqual(self.project.status(), before)
        self.propose(self.specification("another-plan"))
        self.assertEqual([record["request_id"] for record in self.journal.status()["requests"]], ["plan-one", "another-plan"])
        self.project.save_plan(request_id="operator-revision", expected_state_version=before["state_version"],
                               plan={**self.plan, "steps": "The operator chose to request source information first."},
                               reason="Record a different explicit operator decision.")
        manual = self.project.status()
        self.assertEqual(self.journal.adopt_plan(request_id="another-plan")["status"], "stale")
        self.assertEqual(self.project.status(), manual)
        self.assertEqual(manual["budget"], before["budget"])
        with self.assertRaises(ResearchError) as caught:
            self.journal.prepare(**{**self.specification("new-grant"), "decision_limit": 3})
        self.assertEqual(caught.exception.code, "HOST_GRANT_CHANGED")
        with self.assertRaises(ResearchError) as caught:
            self.journal.prepare(**self.specification("after-exhaustion"))
        self.assertEqual(caught.exception.code, "HOST_DECISION_LIMIT")
        self.assertEqual(self.project.status(), manual)


if __name__ == "__main__":
    unittest.main()
