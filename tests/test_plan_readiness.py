"""Plan readiness distinguishes execution constraints from scientific review."""

import copy
import unittest

from autoresearch.plan_readiness import assess_plan_readiness, review_plan_requests


class PlanReadinessTests(unittest.TestCase):
    def context(self):
        # The exhausted local/fit budgets and absent source selection reproduce
        # the constraints exposed by the real rejected A107 response.
        return {
            "schema_version": "research-plan-context-v1", "feedback": [],
            "selection_context": {
                "project_id": "project-plan-fixture", "snapshot_ref": "snapshot-fixture",
                "state_version": 17,
                "context_sha256": "a" * 64,
                "budget": {
                    "local_tool_call_limit": 4, "local_tool_calls_used": 4, "local_tool_calls_reserved": 0,
                    "evidence_read_limit": 8, "evidence_reads_used": 0, "evidence_reads_reserved": 0,
                    "fit_limit": 16, "fit_attempts_used": 16, "fits_reserved": 0,
                },
                "candidates": [], "blockers": [],
                "conditions": [
                    {"method_id": "data.ridge-random-validation", "evaluation_ref": "ridge-validation-v1",
                     "execution_blockers": ["BUDGET_EXHAUSTED", "FIT_BUDGET_EXHAUSTED"],
                     "missing_information": []},
                    {"method_id": "research.source-selection", "evaluation_ref": "source-extraction-only-not-scientific-approval",
                     "execution_blockers": ["CONDITION_NOT_SATISFIED", "NO_UNREAD_SOURCE"],
                     "missing_information": ["Register an original source with a selection."]},
                ],
            },
        }

    def test_exhausted_execution_and_absent_sources_remain_blocked_with_read_budget(self):
        readiness = assess_plan_readiness(self.context())
        self.assertEqual(readiness["execution_status"], "blocked")
        self.assertEqual(readiness["remaining_budget"], {"local_tool_calls": 0, "evidence_reads": 8, "estimator_fits": 0})
        self.assertEqual(readiness["available_actions"], [])
        self.assertIn("NO_UNREAD_SOURCE", readiness["blocked_methods"][1]["execution_blockers"])
        self.assertEqual(readiness["blocked_methods"][1]["missing_information"], ["Register an original source with a selection."])
        self.assertEqual(readiness["scientific_review"], "required")
        self.assertIs(readiness["scientific_validation"], False)

    def test_source_candidate_can_remain_available_when_local_and_fit_budgets_are_exhausted(self):
        context = self.context()
        selection = context["selection_context"]
        selection["conditions"][1]["execution_blockers"] = []
        selection["conditions"][1]["missing_information"] = []
        candidate = {"id": "source-choice", "method_id": "research.source-selection",
                     "parameters": {"receipt_snapshot_sha256": "b" * 64},
                     "evaluation_ref": "source-extraction-only-not-scientific-approval"}
        selection["candidates"] = [candidate]
        readiness = assess_plan_readiness(context)
        self.assertEqual(readiness["execution_status"], "available")
        self.assertEqual(readiness["available_actions"], [candidate])
        self.assertEqual([item["method_id"] for item in readiness["blocked_methods"]], ["data.ridge-random-validation"])

    def test_reserved_unknown_executions_reduce_budget_and_missing_counts_stay_unknown(self):
        context = self.context()
        budget = context["selection_context"]["budget"]
        budget.update(local_tool_calls_used=1, local_tool_calls_reserved=2, fits_reserved=2,
                      fit_attempts_used=12, evidence_reads_reserved=8)
        readiness = assess_plan_readiness(context)
        self.assertEqual(readiness["remaining_budget"], {"local_tool_calls": 1, "evidence_reads": 0, "estimator_fits": 2})
        del budget["fit_limit"]
        budget["local_tool_calls_reserved"] = None
        self.assertEqual(assess_plan_readiness(context)["remaining_budget"],
                         {"local_tool_calls": None, "evidence_reads": 0, "estimator_fits": None})
        budget["evidence_reads_reserved"] = 9
        self.assertEqual(assess_plan_readiness(context)["remaining_budget"]["evidence_reads"], 0)

    def test_global_blockers_cover_methods_without_local_blockers(self):
        context = self.context()
        selection = context["selection_context"]
        selection["conditions"][1]["execution_blockers"] = []
        selection["blockers"] = [{"code": "PROJECT_BUSY", "message": "Resolve the original unknown execution."}]
        readiness = assess_plan_readiness(context)
        self.assertEqual(readiness["execution_status"], "blocked")
        self.assertEqual(readiness["blockers"], selection["blockers"])
        self.assertEqual(len(readiness["blocked_methods"]), 2)
        self.assertEqual(readiness["blocked_methods"][1]["execution_blockers"], [])

    def test_reading_and_mutating_projection_leave_frozen_context_unchanged(self):
        context = self.context()
        selection = context["selection_context"]
        selection["candidates"] = [{"id": "fixture-choice", "parameters": {"dimension": "batch"}}]
        selection["blockers"] = [{"code": "PROJECT_BUSY"}]
        before = copy.deepcopy(context)
        readiness = assess_plan_readiness(context)
        self.assertEqual(context, before)
        self.assertEqual(readiness["context_sha256"], selection["context_sha256"])
        self.assertEqual(readiness["snapshot_ref"], selection["snapshot_ref"])
        self.assertEqual(readiness["state_version"], 17)
        readiness["available_actions"][0]["parameters"]["dimension"] = "changed"
        readiness["blocked_methods"][0]["execution_blockers"].clear()
        readiness["blockers"][0]["code"] = "changed"
        self.assertEqual(context, before)

    def test_request_review_is_empty_without_plans_and_uses_all_plan_states(self):
        self.assertEqual(review_plan_requests([]), [])
        records = [{"request_id": "selection", "purpose": "selection"},
                   {"request_id": "recipe", "purpose": "recipe"}]
        self.assertEqual(review_plan_requests(records), [])
        for status in ("prepared", "unknown", "invalid"):
            records.append({"request_id": "plan-" + status, "purpose": "plan", "status": status,
                            "context": self.context(), "arguments": {"reason": "Unreviewed model prose"}})
        before = copy.deepcopy(records)
        reviews = review_plan_requests(records)
        self.assertEqual([item["request_id"] for item in reviews], ["plan-prepared", "plan-unknown", "plan-invalid"])
        self.assertTrue(all(item["assessment"]["scientific_review"] == "required" for item in reviews))
        self.assertTrue(all(item["assessment"] == assess_plan_readiness(self.context()) for item in reviews))
        self.assertTrue(all("arguments" not in item and "status" not in item for item in reviews))
        reviews[0]["assessment"]["blocked_methods"][0]["execution_blockers"].clear()
        self.assertEqual(records, before)


if __name__ == "__main__":
    unittest.main()
