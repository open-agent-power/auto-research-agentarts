"""Captured method costs reach prompts and reports without inventing old facts."""

import copy
import unittest

import test_group_only_design as fixtures
from autoresearch import host_selection_protocol, research_plan_proposal, recipe_change_proposal
from autoresearch.host_model_selection import HostModelSelection
from autoresearch.project_selection import budget_cost_notice, seal_context
from autoresearch.project_report import collect_report, _markdown


class MethodBudgetProjectionTests(unittest.TestCase):
    def setUp(self):
        fixture = fixtures.GroupOnlyDesignTests()
        self.addCleanup(fixture.doCleanups)
        self.project, self.controller = fixture.project(fit_limit=4, groups=2)

    def test_all_native_prompts_explain_captured_costs_and_preserve_absent_capture(self):
        selection = self.controller.selection_context()
        plan = research_plan_proposal.build_context(self.project)
        recipe = {"schema_version": "research-recipe-v1", "id": "cost-fixture", "version": 1,
            "question": "Use only current conditions.", "scope_match": {key: selection["domain_scope"][key] for key in ("domain", "contract")},
            "need": "next_check", "ordered_methods": [{key: selection["conditions"][0][key] for key in ("method_id", "evaluation_ref")}],
            "on_no_match": "wait"}
        change = recipe_change_proposal.build_context(self.project, recipe, "Respect each budget category.")
        notice = budget_cost_notice(selection)
        self.assertIn("evidence_reads only", notice)
        self.assertIn("null is unknown, not zero", notice)
        for protocol, context in ((host_selection_protocol, selection), (research_plan_proposal, plan), (recipe_change_proposal, change)):
            prompt = protocol.build_prompt(context)
            self.assertEqual(prompt["system"].count(notice), 1)
            self.assertIn('"budget_cost"', prompt["prompt"])
        legacy = copy.deepcopy(plan)
        payload = legacy["selection_context"]
        payload.pop("context_sha256")
        for condition in payload["conditions"]:
            condition.pop("budget_cost", None)
        legacy["selection_context"] = seal_context(payload)
        self.assertEqual(budget_cost_notice(legacy["selection_context"]), "")
        self.assertEqual(research_plan_proposal.build_prompt(legacy)["system"], research_plan_proposal.build_prompt(plan)["system"].replace(notice, "", 1))

    def test_report_captures_current_context_separately_from_historical_host(self):
        before, host = self.project.status(), HostModelSelection(self.project.root).status()
        files = {str(p.relative_to(self.project.root)): p.read_bytes() for p in self.project.root.rglob("*") if p.is_file()}
        report = collect_report(self.project.root)
        context = report["input"]["selection_context"]
        self.assertEqual(context, self.controller.selection_context())
        assessment = report["execution_conditions"]
        self.assertEqual(assessment["schema_version"], "plan-readiness-v2")
        self.assertEqual(assessment["context_sha256"], context["context_sha256"])
        costs = {item["method_id"]: item["budget_cost"] for item in assessment["method_budget_costs"]}
        self.assertEqual(costs["research.source-selection"], {"local_tool_calls": 0, "evidence_reads": 1, "estimator_fits": 0})
        self.assertEqual(costs["data.ridge-group-validation"]["estimator_fits"], 4)
        self.assertIsNone(costs["data.ridge-random-validation"]["estimator_fits"])
        self.assertEqual(report["plan_reviews"], [])
        text = _markdown(report)
        self.assertIn("当前方法的额度消耗", text)
        self.assertIn("未确定，需绑定可用设计", text)
        self.assertEqual(self.project.status(), before)
        self.assertEqual(HostModelSelection(self.project.root).status(), host)
        self.assertEqual({str(p.relative_to(self.project.root)): p.read_bytes() for p in self.project.root.rglob("*") if p.is_file()}, files)


if __name__ == "__main__":
    unittest.main()
