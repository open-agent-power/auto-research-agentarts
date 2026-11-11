"""Historical cases inform sealed context without becoming local evidence or permission."""
import copy
from pathlib import Path
import unittest

import test_group_only_design as group_fixtures
import test_project_experience_binding as case_fixtures
from autoresearch.contracts import ResearchError, canonical
from autoresearch import host_selection_protocol, research_plan_proposal, recipe_change_proposal, research_recipe
from autoresearch.project_selection import seal_context, validate_proposal
from autoresearch.project_report import collect_report


class ProjectExperienceControllerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        case_fixtures.ProjectExperienceBindingTests.setUpClass()
        cls.addClassCleanup(case_fixtures.ProjectExperienceBindingTests.doClassCleanups)
        cls.bundle = copy.deepcopy(case_fixtures.ProjectExperienceBindingTests.bundle)

    def setUp(self):
        fixture = group_fixtures.GroupOnlyDesignTests()
        self.addCleanup(fixture.doCleanups)
        self.project, self.controller = fixture.project(fit_limit=4, groups=2)

    def attach(self, request_id="import-controller-case"):
        return self.project.import_experience(request_id=request_id,
            expected_state_version=self.project.status()["state_version"], bundle=canonical(self.bundle).encode("utf-8"),
            reason="Use an explicitly marked constructed historical example without changing research authority.")

    def test_context_keeps_candidates_budget_and_evidence_separate_from_cases(self):
        before = self.controller.selection_context()
        self.assertNotIn("experience", before)
        revision = self.attach()
        after = self.controller.selection_context()
        for key in ("budget", "candidates", "conditions", "evidence", "baseline_decision"):
            self.assertEqual(after[key], before[key], key)
        case, = after["experience"]["cases"]
        self.assertEqual(case["case_id"], self.bundle["id"])
        self.assertEqual(case["transfer_scope"], "analogy_not_current_evidence")
        self.assertEqual(case["association"]["status"], "applicable")
        self.assertEqual(case["association"]["matching_candidate_ids"],
                         [item["id"] for item in after["candidates"] if item["method_id"] == self.bundle["record"]["payload"]["method_id"]])
        self.assertNotIn("artifact", case["origin_evidence"])
        self.assertNotIn("oof", case["observation"])
        self.assertEqual(after["state_version"], revision["based_on_state_version"] + 1)

    def test_case_ids_cannot_become_current_citations_or_feedback_actions(self):
        self.attach()
        context = self.controller.selection_context()
        proposal = {"schema_version": "project-selection-proposal-v1", "context_sha256": context["context_sha256"],
            "provider": {"kind": "operator_assistant", "label": "Case boundary fixture"}, "choice": {"kind": "wait"},
            "rationale": "Use a historical case only as a reminder.", "evidence_citation_ids": [self.bundle["id"]]}
        with self.assertRaises(ResearchError):
            validate_proposal(context, proposal)
        plan_context = research_plan_proposal.build_context(self.project)
        arguments = {"plan": {"question": "Which local evidence is still needed?", "basis": "Historical case is advisory.",
            "steps": "Review current evidence and retain the existing scope.", "expected_feedback": "Record unresolved conditions."},
            "reason": "No cross-project outcome transfer.", "feedback_action_ids": [self.bundle["record"]["provenance"]["action_id"]],
            "expected_improvement": "No claimed improvement in this fixture."}
        with self.assertRaises(ResearchError):
            research_plan_proposal.build_proposal(plan_context, arguments, "Declared external fixture")

    def test_all_prompt_purposes_explain_case_scope_without_changing_answer_contracts(self):
        self.attach()
        selection = self.controller.selection_context()
        plan = research_plan_proposal.build_context(self.project)
        recipe = {"schema_version": "research-recipe-v1", "id": "case-recipe", "version": 1,
            "question": "Keep the existing local eligibility.", "scope_match": {key: selection["domain_scope"][key] for key in ("domain", "contract")},
            "need": "next_check", "ordered_methods": [{key: item[key] for key in ("method_id", "evaluation_ref")}
                                                        for item in selection["conditions"][:1]], "on_no_match": "wait"}
        research_recipe.validate_recipe(recipe)
        changed = recipe_change_proposal.build_context(self.project, recipe, "Use only target evidence.")
        for prompt in (host_selection_protocol.build_prompt(selection), research_plan_proposal.build_prompt(plan),
                       recipe_change_proposal.build_prompt(changed)):
            self.assertIn("Historical experience cases", prompt["system"])
            self.assertIn("not current", prompt["system"])
            self.assertIn(self.bundle["id"], prompt["prompt"])
        bad = copy.deepcopy(selection)
        bad.pop("context_sha256")
        bad["experience"]["cases"][0]["association"]["matching_candidate_ids"] = ["invented-permission"]
        with self.assertRaises(ResearchError):
            seal_context(bad)

    def test_retirement_and_original_import_replay_do_not_restore_case(self):
        revision = self.attach()
        old = self.controller.selection_context()
        self.project.set_experience_status(request_id="retire-controller-case",
            expected_state_version=self.project.status()["state_version"], case_id=self.bundle["id"], status="retired", reason="Retire this target snapshot.")
        self.assertNotIn("experience", self.controller.selection_context())
        self.assertEqual(self.project.import_experience(request_id="import-controller-case",
            expected_state_version=revision["based_on_state_version"], bundle=canonical(self.bundle).encode("utf-8"),
            reason="Use an explicitly marked constructed historical example without changing research authority."), revision)
        self.assertNotIn("experience", self.controller.selection_context())
        proposal = {"schema_version": "project-selection-proposal-v1", "context_sha256": old["context_sha256"],
            "provider": {"kind": "operator_assistant", "label": "Old client fixture"}, "choice": {"kind": "wait"},
            "rationale": "Old pre-retirement client context.", "evidence_citation_ids": []}
        with self.assertRaises(ResearchError) as caught:
            self.controller.advance_selection(request_id="old-context-case", expected_state_version=old["state_version"], proposal=proposal)
        self.assertIn(caught.exception.code, {"STALE_STATE", "STALE_SELECTION_CONTEXT"})

    def test_report_retains_case_snapshots_and_retired_history_without_new_research(self):
        self.attach()
        before = self.project.status()
        report = collect_report(self.project.root)
        case, = report["experience_cases"]
        self.assertEqual(case["inclusion_status"], "active")
        self.assertEqual(report["input"]["experience_revisions"], before["experience_revisions"])
        source, = [item for item in report["source_manifest"] if item["role"] == "historical_method_case_snapshot"]
        self.assertEqual(source["transfer_scope"], "analogy_not_current_evidence")
        asset, = [item for item in report["input"]["assets"] if item["name"] == source["name"]]
        self.assertGreater(asset["bytes"], 0)
        self.assertEqual(self.project.status(), before)
