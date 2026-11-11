"""Frozen method costs classify dispatch budgets without changing execution gates."""

import copy
import unittest
from unittest.mock import patch

import test_group_only_design as group_fixtures
import test_plan_readiness as readiness_fixtures
import test_project_controller_selection as selection_fixtures
from autoresearch import method_registry as registry, project_selection, source_evidence_adapter
from autoresearch import research_plan_proposal as plan_protocol
from autoresearch.contracts import ResearchError, fingerprint
from autoresearch.host_model_selection import HostModelSelection
from autoresearch.plan_readiness import assess_plan_readiness, review_plan_requests
from autoresearch.project_controller import ProjectController


class SourceBudgetCostTests(unittest.TestCase):
    setUp = selection_fixtures.ControllerSelectionTests.setUp
    bundle = selection_fixtures.ControllerSelectionTests.bundle
    stage = selection_fixtures.ControllerSelectionTests.stage
    proposal = staticmethod(selection_fixtures.ControllerSelectionTests.proposal)
    assert_code = selection_fixtures.ControllerSelectionTests.assert_code

    def prepare_plan(self):
        journal = HostModelSelection(self.project.root)
        record = journal.prepare(request_id="frozen-plan", provider="delegated", purpose="plan",
                                 expected_state_version=self.project.status()["state_version"], decision_limit=1,
                                 cli_budget_usd=0.1, reason="Read-only frozen method-budget projection fixture")
        return journal, record

    def test_exhausted_tools_preserve_only_source_candidates_and_execute_once(self):
        first, second = self.stage()
        controller = ProjectController(self.project.root)
        before = self.project.status()
        context = controller.selection_context()
        self.assertEqual(before["budget"]["local_tool_calls_used"], before["budget"]["local_tool_call_limit"])
        self.assertEqual(self.project.status(), before)
        expected = []
        for receipt in (first, second):
            candidate = {"method_id": registry.LEGACY_SOURCE,
                         "parameters": {"receipt_snapshot_sha256": receipt["receipt_snapshot_sha256"]},
                         "evaluation_ref": "source-extraction-only-not-scientific-approval"}
            expected.append({"id": "choice-" + fingerprint(candidate)[:32], **candidate})
        self.assertEqual(context["candidates"], expected)
        costs = {item["method_id"]: item["budget_cost"] for item in context["conditions"]}
        self.assertEqual(costs[registry.LEGACY_SOURCE], {"local_tool_calls": 0, "evidence_reads": 1, "estimator_fits": 0})
        self.assertEqual(costs[registry.primary_id(before)], {"local_tool_calls": 1, "evidence_reads": 0, "estimator_fits": 0})
        assessment = assess_plan_readiness({"selection_context": context})
        self.assertEqual(assessment["schema_version"], "plan-readiness-v2")
        self.assertEqual(assessment["remaining_budget"], {"local_tool_calls": 0, "evidence_reads": 8, "estimator_fits": 0})
        self.assertEqual(assessment["available_actions"], expected)
        proposal = self.proposal(context, expected[1])
        with patch.object(source_evidence_adapter, "execute", wraps=source_evidence_adapter.execute) as execute:
            result = controller.advance_selection(request_id="source-only", proposal=proposal)
            completed = self.project.status()
            replay = ProjectController(self.project.root).advance_selection(request_id="source-only", proposal=proposal)
            execute.assert_called_once()
        self.assertEqual(result["status"], "completed")
        self.assertTrue(replay["replayed"])
        self.assertEqual(replay["child_request_id"], result["child_request_id"])
        self.assertEqual(self.project.status(), completed)
        self.assertEqual(completed["actions"], before["actions"])
        self.assertEqual(completed["budget"]["evidence_reads_used"], before["budget"]["evidence_reads_used"] + 1)
        for key in ("local_tool_calls_used", "local_tool_calls_reserved", "fit_attempts_used", "fits_reserved", "new_fits"):
            self.assertEqual(completed["budget"][key], before["budget"][key])

    def test_missing_materials_stay_blocked_and_unknown_source_keeps_reservation(self):
        controller = ProjectController(self.project.root)
        missing = controller.selection_context()
        source = next(item for item in missing["conditions"] if item["method_id"] == registry.LEGACY_SOURCE)
        self.assertEqual(source["budget_cost"]["evidence_reads"], 1)
        self.assertIn("NO_UNREAD_SOURCE", source["execution_blockers"])
        self.assertFalse(any(item["method_id"] == registry.LEGACY_SOURCE for item in missing["candidates"]))
        self.stage()
        context = controller.selection_context()
        proposal = self.proposal(context, context["candidates"][0])
        with patch.object(source_evidence_adapter, "execute", side_effect=KeyboardInterrupt) as execute:
            with self.assertRaises(KeyboardInterrupt):
                controller.advance_selection(request_id="unknown-source", proposal=proposal)
            self.assertEqual(controller.advance_selection(request_id="unknown-source", proposal=proposal)["status"], "unknown")
            blocked = controller.selection_context()
            before = self.project.status()
            self.assertEqual(blocked["candidates"], [])
            self.assertIn("EXECUTION_UNKNOWN", {item["code"] for item in blocked["blockers"]})
            self.assertEqual(before["budget"]["evidence_reads_reserved"], 1)
            self.assert_code("SELECTION_BLOCKED", controller.advance_selection, request_id="bypass-cost",
                             proposal=self.proposal(blocked, context["candidates"][0]))
            execute.assert_called_once()
        self.assertEqual(self.project.status(), before)

    def test_reading_captured_costs_does_not_write_project_or_host(self):
        self.stage()
        journal, record = self.prepare_plan()
        before = self.project.status()
        frozen = {path: path.read_bytes() for path in journal.directory.rglob("*") if path.is_file()}
        original = copy.deepcopy(record)
        with patch.object(journal, "_save", side_effect=AssertionError("Projection cannot save Host records")):
            saved = journal.status(request_id=record["request_id"])
            assessment = review_plan_requests([saved])[0]["assessment"]
            expected = [{key: copy.deepcopy(condition[key]) for key in ("method_id", "evaluation_ref", "budget_cost")}
                        for condition in saved["context"]["selection_context"]["conditions"]]
            self.assertEqual(assessment["method_budget_costs"], expected)
            assessment["method_budget_costs"][0]["budget_cost"]["local_tool_calls"] = 99
            self.assertEqual(journal.status(request_id=record["request_id"]), original)
        self.assertEqual(self.project.status(), before)
        self.assertEqual({path: path.read_bytes() for path in journal.directory.rglob("*") if path.is_file()}, frozen)

    def test_legacy_host_context_is_not_backfilled_from_current_methods(self):
        self.stage()
        current_builder = plan_protocol.build_context

        def legacy_context(project, need="next_check"):
            context = current_builder(project, need)
            selection = context["selection_context"]
            selection.pop("context_sha256")
            for condition in selection["conditions"]:
                condition.pop("budget_cost")
            context["selection_context"] = project_selection.seal_context(selection)
            return context

        with patch.object(plan_protocol, "build_context", side_effect=legacy_context):
            journal, record = self.prepare_plan()
        frozen = {path: path.read_bytes() for path in journal.directory.rglob("*") if path.is_file()}
        before = self.project.status()
        self.assertTrue(project_selection.budget_cost_notice(ProjectController(self.project.root).selection_context()))
        saved = journal.status(request_id=record["request_id"])
        self.assertEqual(saved, record)
        self.assertEqual(project_selection.budget_cost_notice(saved["context"]["selection_context"]), "")
        assessment = review_plan_requests([saved])[0]["assessment"]
        self.assertEqual(assessment["schema_version"], "plan-readiness-v1")
        self.assertNotIn("method_budget_costs", assessment)
        self.assertTrue(all("budget_cost" not in item for item in saved["context"]["selection_context"]["conditions"]))
        self.assertEqual(self.project.status(), before)
        self.assertEqual({path: path.read_bytes() for path in journal.directory.rglob("*") if path.is_file()}, frozen)

    def test_cost_protocol_rejects_wrong_shapes_and_noninteger_counts(self):
        context = ProjectController(self.project.root).selection_context()
        context.pop("context_sha256")
        valid = {"local_tool_calls": 1, "evidence_reads": 0, "estimator_fits": 0}
        malformed = [None, [], {}, {**valid, "extra": 1}, {key: value for key, value in valid.items() if key != "estimator_fits"}]
        for key in valid:
            for value in (True, False, -1, 0.5, "1", [], {}):
                malformed.append({**valid, key: value})
        malformed.extend([{**valid, "local_tool_calls": None}, {**valid, "evidence_reads": None}])
        before = copy.deepcopy(context)
        for cost in malformed:
            with self.subTest(cost=cost):
                payload = copy.deepcopy(context)
                payload["conditions"][0]["budget_cost"] = cost
                with self.assertRaises(ResearchError) as caught:
                    project_selection.seal_context(payload)
                self.assertEqual(caught.exception.code, "INVALID_SELECTION_CONTEXT")
        for fits in (0, 4, None):
            payload = copy.deepcopy(context)
            payload["conditions"][0]["budget_cost"] = {**valid, "estimator_fits": fits}
            sealed = project_selection.seal_context(payload)
            project_selection.validate_proposal(sealed, self.proposal(sealed))
        self.assertEqual(context, before)


class RidgeBudgetCostTests(unittest.TestCase):
    resource = group_fixtures.GroupOnlyDesignTests.resource
    project = group_fixtures.GroupOnlyDesignTests.project

    def test_two_group_folds_cost_four_fits_and_unbound_random_is_unknown(self):
        project, controller = self.project(groups=2, fit_limit=4)
        before = project.status()
        context = controller.selection_context()
        conditions = {item["method_id"]: item for item in context["conditions"]}
        group = conditions["data.ridge-group-validation"]
        random = conditions["data.ridge-random-validation"]
        self.assertEqual(project._fit_attempts_needed(before, group["method_id"]), 4)
        self.assertEqual(group["budget_cost"], {"local_tool_calls": 1, "evidence_reads": 0, "estimator_fits": 4})
        self.assertEqual(project._fit_attempts_needed(before, random["method_id"]), 0)
        self.assertIsNone(random["budget_cost"]["estimator_fits"])
        self.assertNotIn(random["method_id"], [item["method_id"] for item in context["candidates"]])
        self.assertIn(group["method_id"], [item["method_id"] for item in context["candidates"]])
        self.assertTrue(all(item["budget_cost"]["estimator_fits"] == 0 for item in context["conditions"]
                            if item["method_id"] not in registry.RIDGE))
        self.assertEqual(project.status(), before)
        result = controller.advance(request_id="two-group-fits")
        completed = project.status()
        self.assertEqual(result["status"], "completed")
        self.assertEqual(completed["budget"]["fit_attempts_used"], 4)
        self.assertEqual([(event["estimator"], event["fold"]) for event in completed["actions"][-1]["fit_events"]],
                         [("scaler", 1), ("ridge", 1), ("scaler", 2), ("ridge", 2)])
        with patch.object(registry.RIDGE[group["method_id"]], "execute", side_effect=AssertionError("No replay fits")):
            self.assertTrue(controller.advance(request_id="two-group-fits")["replayed"])
        self.assertEqual(project.status(), completed)


class FrozenBudgetCostTests(unittest.TestCase):
    def test_legacy_readiness_remains_exact_v1_and_notice_is_empty(self):
        context = readiness_fixtures.PlanReadinessTests.context(self)
        selection = context["selection_context"]
        before = copy.deepcopy(context)
        self.assertEqual(assess_plan_readiness(context), {
            "schema_version": "plan-readiness-v1", "project_id": "project-plan-fixture", "snapshot_ref": "snapshot-fixture",
            "state_version": 17, "context_sha256": "a" * 64, "execution_status": "blocked",
            "remaining_budget": {"local_tool_calls": 0, "evidence_reads": 8, "estimator_fits": 0},
            "available_actions": [], "blocked_methods": copy.deepcopy(selection["conditions"]), "blockers": [],
            "scientific_review": "required", "scientific_validation": False,
        })
        self.assertEqual(project_selection.budget_cost_notice(selection), "")
        self.assertEqual(context, before)

    def test_mixed_frozen_context_projects_only_captured_costs(self):
        context = readiness_fixtures.PlanReadinessTests.context(self)
        condition = context["selection_context"]["conditions"][0]
        condition["budget_cost"] = {"local_tool_calls": 1, "evidence_reads": 0, "estimator_fits": None}
        before = copy.deepcopy(context)
        costs = assess_plan_readiness(context)["method_budget_costs"]
        self.assertEqual(costs, [{key: copy.deepcopy(condition[key]) for key in ("method_id", "evaluation_ref", "budget_cost")}])
        notice = project_selection.budget_cost_notice(context["selection_context"])
        for phrase in ("one new dispatch", "evidence_reads only", "Scaler and Ridge", "not zero", "must not be guessed",
                       "eligibility", "refill budgets", "unknown-execution"):
            self.assertIn(phrase, notice)
        costs[0]["budget_cost"]["estimator_fits"] = 0
        self.assertEqual(context, before)


if __name__ == "__main__":
    unittest.main()
