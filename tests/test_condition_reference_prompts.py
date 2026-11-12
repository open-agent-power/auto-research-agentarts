"""Shared-condition references are explained across all three prompt protocols."""
import copy
import unittest

import test_project_selection as fixtures
from autoresearch import host_selection_protocol as selection
from autoresearch import research_plan_proposal as plan
from autoresearch import recipe_change_proposal as recipe
from autoresearch.contracts import canonical
from autoresearch.project_selection import CONDITION_PROJECTION_FIELDS, condition_reference_notice, seal_context


class ConditionReferencePromptTests(unittest.TestCase):
    def contexts(self, referenced):
        context = fixtures.ProjectSelectionTests.context(self)
        context.pop("context_sha256")
        context["domain_scope"] = {"domain": "data", "contract": "tabular-quality-v1"}
        context["conditions"][0]["evaluation_ref"] = "source-only-v1"
        context["conditions"][0].update(execution_blockers=[], reasons=[], missing_information=[], completed=False)
        if referenced:
            context["baseline_decision"]["conditions_ref"] = {
                "kind": "provided_selection_context_field", "path": ["conditions"],
                "fields": list(CONDITION_PROJECTION_FIELDS)}
        context = seal_context(context)
        research = {"schema_version": "research-plan-context-v2", "selection_context": context,
            "feedback": [{"action_id": "action-test", "request_id": "request-test",
                "method_id": "research.source-selection", "status": "completed", "observations": [],
                "next_decision": None, "failure": None, "artifact_ref": "artifacts/action-test.json"}],
            "saved_comparisons": [], "remaining_questions": []}
        change = {"schema_version": "recipe-change-context-v1", "research_context": research,
            "current_recipe": {"schema_version": "research-recipe-v1", "id": "condition-ref-test", "version": 1,
                "question": "Choose the next evidenced action.", "scope_match": copy.deepcopy(context["domain_scope"]),
                "need": context["need"], "ordered_methods": [{"method_id": "research.source-selection",
                    "evaluation_ref": "source-only-v1"}], "on_no_match": "wait"},
            "improvement_goal": "Clarify the next justified source action."}
        return context, research, change

    def test_all_prompt_channels_explain_supplied_reference_without_mutating_context(self):
        legacy, current = self.contexts(False), self.contexts(True)
        for build, old, new in zip((selection.build_prompt, plan.build_prompt, recipe.build_prompt), legacy, current):
            with self.subTest(channel=build.__module__):
                before = copy.deepcopy(new)
                original = build(old)
                projected = build(new)
                self.assertNotIn("conditions_ref", original["system"])
                self.assertIn("supplied conditions", projected["system"])
                self.assertIn("not unread artifact content", projected["system"])
                self.assertEqual(projected["system"], original["system"] + condition_reference_notice(current[0]))
                self.assertIn(canonical(new), projected["prompt"])
                self.assertEqual(new, before)

    def test_legacy_context_has_no_new_notice_or_inferred_reference(self):
        context = self.contexts(False)[0]
        before = copy.deepcopy(context)
        self.assertEqual(condition_reference_notice(context), "")
        self.assertEqual(context, before)
