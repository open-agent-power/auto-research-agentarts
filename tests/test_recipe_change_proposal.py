"""Recipe change proposals stay within actual feedback and frozen method declarations."""

import base64
import copy
from pathlib import Path
import tempfile
import unittest

from autoresearch import recipe_change_proposal as protocol
from autoresearch.contracts import ResearchError, canonical
from autoresearch.local_workbench import LocalWorkbench


class RecipeChangeProposalTests(unittest.TestCase):
    def setUp(self):
        root = Path(self.enterContext(tempfile.TemporaryDirectory())) / "workbench"
        manager = LocalWorkbench(root)
        spec = {"schema_version": "tabular-quality-spec-v1", "file": "readings.csv",
                "dataset_label": "Recipe feedback fixture", "source_url": "urn:test:recipe-feedback",
                "license_note": "Constructed development input", "sample_unit": "declared_record",
                "group_columns": ["batch"], "key_columns": [], "numeric_columns": ["reading"],
                "target_column": "reading", "target_unit": "declared_unit", "missing_tokens": ["", "NA"],
                "delimiter": ",", "provenance": {"origin_sha256": "a" * 64, "description": "Constructed input"}}
        manager.create({"request_id": "create-recipe-feedback", "goal": "Check the next route after actual quality feedback",
                        "budget_ref": "recipe-feedback-test-only", "max_tool_calls": 2,
                        "input": {"file_name": "readings.csv",
                                  "csv_base64": base64.b64encode(b"batch,reading\na,1\nb,\n").decode("ascii"),
                                  "spec_base64": base64.b64encode(canonical(spec).encode("utf-8")).decode("ascii")}})
        self.project, _ = manager.binding()
        self.recipe = {"schema_version": "research-recipe-v1", "id": "feedback-route", "version": 1,
                       "question": "Which next step addresses the saved feedback?",
                       "scope_match": {"domain": "data", "contract": "tabular-quality-v1"}, "need": "next_check",
                       "ordered_methods": [{"method_id": "data.grouped-quality-profile", "evaluation_ref": "grouped-quality-profile-v1"},
                                           {"method_id": "research.source-selection", "evaluation_ref": "source-extraction-only-not-scientific-approval"}],
                       "on_no_match": "wait"}

    @staticmethod
    def arguments(context):
        candidate = copy.deepcopy(context["current_recipe"])
        candidate["version"] += 1
        candidate["question"] = "Prioritize source interpretation after the quality feedback."
        candidate["ordered_methods"].reverse()
        return {"candidate": candidate, "reason": "The saved feedback raises source interpretation questions.",
                "feedback_action_ids": [context["research_context"]["feedback"][0]["action_id"]],
                "expected_improvement": "The next route addresses the recorded unresolved conditions.",
                "validation_plan": "Compare both recipe decisions on the frozen context and check candidate membership."}

    def test_actual_feedback_and_recipe_need_bind_the_candidate_and_provider_parsing(self):
        with self.assertRaises(ResearchError) as caught:
            protocol.build_context(self.project, self.recipe, "Use saved feedback to improve method order.")
        self.assertEqual(caught.exception.code, "INVALID_RECIPE_CHANGE_CONTEXT")
        self.project.step(request_id="quality-for-recipe")
        self.recipe["need"] = "review_next_route"
        before = self.project.status()
        context = protocol.build_context(self.project, self.recipe, "Use saved feedback to improve method order.")
        self.assertEqual(self.project.status(), before)
        selection = context["research_context"]["selection_context"]
        self.assertEqual(selection["need"], "review_next_route")
        self.assertEqual(context["research_context"]["feedback"][0]["observations"], before["actions"][0]["observations"])
        self.assertIn(canonical(context), protocol.build_prompt(context)["prompt"])
        arguments = self.arguments(context)
        delegated = protocol.parse_host_response(canonical(arguments).encode("utf-8"), "delegated")
        proposal = protocol.build_proposal(context, delegated["arguments"], "Delegated fixture")
        self.assertEqual(protocol.validate_proposal(context, proposal), proposal)
        self.assertEqual(proposal["context_sha256"], selection["context_sha256"])
        envelope = {"type": "result", "subtype": "success", "is_error": False,
                    "result": canonical(arguments), "modelUsage": {"declared-model": {}},
                    "usage": {"output_tokens": 5}, "total_cost_usd": 0.01}
        cli = protocol.parse_host_response(canonical(envelope).encode("utf-8"), "claude_cli")
        self.assertEqual(cli["arguments"], delegated["arguments"])
        self.assertEqual(cli["reported_cost_usd"], 0.01)

    def test_rejects_fabricated_feedback_evaluations_and_changes_outside_the_original_recipe(self):
        self.project.step(request_id="quality-for-recipe")
        context = protocol.build_context(self.project, self.recipe, "Use saved feedback to improve method order.")
        arguments = self.arguments(context)
        invalid = []
        changed = copy.deepcopy(arguments)
        changed["feedback_action_ids"] = ["invented-action"]
        invalid.append(changed)
        changed = copy.deepcopy(arguments)
        changed["candidate"]["ordered_methods"][0]["evaluation_ref"] = "invented-evaluation"
        invalid.append(changed)
        changed = copy.deepcopy(arguments)
        changed["candidate"]["version"] = self.recipe["version"]
        invalid.append(changed)
        changed = copy.deepcopy(arguments)
        changed["candidate"]["need"] = "unrelated_need"
        invalid.append(changed)
        for value in invalid:
            with self.subTest(candidate=value["candidate"]), self.assertRaises(ResearchError) as caught:
                protocol.build_proposal(context, value, "Delegated fixture")
            self.assertEqual(caught.exception.code, "INVALID_RECIPE_CHANGE_PROPOSAL")
        proposal = protocol.build_proposal(context, arguments, "Delegated fixture")
        proposal["context_sha256"] = "0" * 64
        with self.assertRaises(ResearchError) as caught:
            protocol.validate_proposal(context, proposal)
        self.assertEqual(caught.exception.code, "STALE_SELECTION_CONTEXT")


if __name__ == "__main__":
    unittest.main()
