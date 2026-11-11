"""Plan condition projections preserve frozen requests and original evidence."""

import copy
from pathlib import Path
import tempfile
import unittest

import test_local_workbench as fixtures
from autoresearch.contracts import canonical
from autoresearch.host_model_selection import HostModelSelection
from autoresearch.local_workbench import LocalWorkbench
from autoresearch.project_report import collect_report


class PlanReviewProjectionTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.manager = LocalWorkbench(self.root / "workbench")
        self.number = 0
        self.plan = {"question": "Which source definitions are still needed?", "basis": "Saved fixture feedback",
                     "steps": "Review saved results and request the missing source definitions before further execution.",
                     "expected_feedback": "Document unresolved target and grouping definitions."}

    def create_project(self, *, execute_quality=True):
        self.number += 1
        body = fixtures.LocalWorkbenchTests.create_body(self, "create-" + str(self.number))
        body["max_tool_calls"] = 1
        self.manager.create(body)
        project, _ = self.manager.binding()
        if execute_quality:
            project.step(request_id="actual-fixture-quality")
        return project, HostModelSelection(project.root)

    def specification(self, project):
        return {"request_id": "plan-review", "provider": "delegated", "purpose": "plan",
                "expected_state_version": project.status()["state_version"], "decision_limit": 1,
                "cli_budget_usd": 0.1, "reason": "One local protocol fixture; no model transport"}

    def propose(self, project, journal):
        specification = self.specification(project)
        prepared = journal.prepare(**specification)
        arguments = {"plan": self.plan, "reason": "Use saved feedback without promising unavailable execution.",
                     "feedback_action_ids": [item["id"] for item in project.status()["actions"]],
                     "expected_improvement": "Make the missing evidence and current execution limits explicit."}
        response = self.root / ("response-" + str(self.number) + ".json")
        response.write_bytes(canonical(arguments).encode("utf-8"))
        self.assertEqual(journal.import_response(request_id="plan-review", response_file=response)["status"], "received")
        proposed = journal.consume(request_id="plan-review")
        self.assertEqual(proposed["status"], "proposed")
        return specification, prepared, proposed, response

    @staticmethod
    def tree_bytes(root):
        return {str(path.relative_to(root)): path.read_bytes() for path in root.rglob("*") if path.is_file()}

    def assert_readonly_projection(self, project, journal, record):
        project_before, host_before = project.status(), journal.status()
        files_before = self.tree_bytes(project.root)
        view = self.manager.model_view()
        report = collect_report(project.root)
        self.assertEqual(view["records"], [record])
        self.assertEqual(report["host_models"]["records"], [record])
        self.assertEqual(view["plan_reviews"], report["plan_reviews"])
        review = view["plan_reviews"][0]
        self.assertEqual(review["request_id"], record["request_id"])
        selection = record["context"]["selection_context"]
        assessment = review["assessment"]
        for key in ("project_id", "snapshot_ref", "state_version", "context_sha256"):
            self.assertEqual(assessment[key], selection[key])
        self.assertEqual(assessment["scientific_review"], "required")
        self.assertFalse(assessment["scientific_validation"])
        self.assertEqual(project.status(), project_before)
        self.assertEqual(journal.status(), host_before)
        self.assertEqual(journal.status(request_id=record["request_id"]), record)
        self.assertEqual(self.tree_bytes(project.root), files_before)
        return review

    def test_proposed_request_projects_the_same_frozen_constraints_in_workbench_and_report(self):
        project, journal = self.create_project()
        prepared_only = journal.prepare(**self.specification(project))
        self.assertNotIn("proposal", prepared_only)
        prepared_review = self.assert_readonly_projection(project, journal, prepared_only)
        _, prepared, proposed, _ = self.propose(project, journal)
        frozen = copy.deepcopy(prepared["context"])
        prompt = prepared["prompt"]
        self.assertIn(canonical(frozen), prompt["prompt"])
        self.assertIn('"execution_conditions":', prompt["prompt"])
        self.assertIn('"local_tool_calls":0', prompt["prompt"])
        self.assertIn("BUDGET_EXHAUSTED", prompt["prompt"])
        self.assertIn("NO_UNREAD_SOURCE", prompt["prompt"])
        self.assertIn("remaining budget alone does not establish eligibility", prompt["system"])
        self.assertIn("do not infer overfitting", prompt["system"])
        review = self.assert_readonly_projection(project, journal, proposed)
        self.assertEqual(review["assessment"]["execution_status"], "blocked")
        self.assertEqual(review["assessment"]["available_actions"], [])
        self.assertEqual(review["assessment"]["remaining_budget"]["local_tool_calls"], 0)
        self.assertEqual(review, prepared_review)
        self.assertEqual(proposed["context"], frozen)

    def test_later_project_revision_does_not_rewrite_a_request_condition_review(self):
        project, journal = self.create_project()
        _, _, proposed, _ = self.propose(project, journal)
        frozen_review = self.assert_readonly_projection(project, journal, proposed)
        project.save_plan(request_id="operator-later-plan", expected_state_version=project.status()["state_version"],
                          plan=self.plan, reason="Record a later explicit operator plan.")
        self.assertGreater(project.status()["state_version"], frozen_review["assessment"]["state_version"])
        current_review = self.assert_readonly_projection(project, journal, proposed)
        self.assertEqual(current_review, frozen_review)
        self.assertNotEqual(current_review["assessment"]["snapshot_ref"], project.status()["snapshot_ref"])

    def test_terminal_request_replays_keep_original_records_and_condition_reviews(self):
        for outcome in ("rejected", "applied"):
            with self.subTest(outcome=outcome):
                project, journal = self.create_project()
                specification, _, proposed, response = self.propose(project, journal)
                if outcome == "rejected":
                    terminal = journal.reject_plan(request_id="plan-review", reason="Keep the current fixture route.")
                else:
                    terminal = journal.adopt_plan(request_id="plan-review")
                self.assertEqual(terminal["status"], outcome)
                self.assertEqual(terminal["context"], proposed["context"])
                review = self.assert_readonly_projection(project, journal, terminal)
                project_before, host_before = project.status(), journal.status()
                files_before = self.tree_bytes(project.root)
                self.assertEqual(journal.prepare(**specification), terminal)
                self.assertEqual(journal.import_response(request_id="plan-review", response_file=response), terminal)
                self.assertEqual(journal.consume(request_id="plan-review"), terminal)
                replay = (journal.reject_plan(request_id="plan-review", reason=terminal["rejection_reason"])
                          if outcome == "rejected" else journal.adopt_plan(request_id="plan-review"))
                self.assertEqual(replay, terminal)
                self.assertEqual(self.assert_readonly_projection(project, journal, terminal), review)
                self.assertEqual(project.status(), project_before)
                self.assertEqual(journal.status(), host_before)
                self.assertEqual(self.tree_bytes(project.root), files_before)

    def test_empty_manager_and_project_views_do_not_create_a_host_journal(self):
        manager_before = self.tree_bytes(self.manager.root)
        empty = self.manager.model_view()
        self.assertIsNone(empty["project_id"])
        self.assertEqual(empty["plan_reviews"], [])
        self.assertEqual(self.tree_bytes(self.manager.root), manager_before)
        project, journal = self.create_project(execute_quality=False)
        project_before = project.status()
        files_before = self.tree_bytes(project.root)
        self.assertFalse(journal.directory.exists())
        self.assertEqual(self.manager.model_view()["plan_reviews"], [])
        self.assertEqual(collect_report(project.root)["plan_reviews"], [])
        self.assertFalse(journal.directory.exists())
        self.assertEqual(project.status(), project_before)
        self.assertEqual(self.tree_bytes(project.root), files_before)


if __name__ == "__main__":
    unittest.main()
