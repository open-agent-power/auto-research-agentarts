"""Plan proposals use actual saved feedback and retain its host binding."""

import base64
import copy
import json
from pathlib import Path
import tempfile
import unittest

from autoresearch import research_plan_proposal as protocol
from autoresearch import host_selection_protocol, recipe_change_proposal, research_recipe
from autoresearch.contracts import ResearchError, canonical
from autoresearch.local_workbench import LocalWorkbench
from autoresearch.project_controller import ProjectController
from autoresearch.project_selection import seal_context, validate_proposal


class ResearchPlanProposalTests(unittest.TestCase):
    def setUp(self):
        root = Path(self.enterContext(tempfile.TemporaryDirectory())) / "workbench"
        manager = LocalWorkbench(root)
        spec = {"schema_version": "tabular-quality-spec-v1", "file": "readings.csv",
                "dataset_label": "Plan feedback fixture", "source_url": "urn:test:plan-feedback",
                "license_note": "Constructed development input", "sample_unit": "declared_record",
                "group_columns": ["batch"], "key_columns": [], "numeric_columns": ["reading"],
                "target_column": "reading", "target_unit": "declared_unit", "missing_tokens": ["", "NA"],
                "delimiter": ",", "provenance": {"origin_sha256": "a" * 64, "description": "Constructed input"}}
        manager.create({"request_id": "create-plan-feedback", "goal": "Identify information needed before group comparison",
                        "budget_ref": "plan-feedback-test-only", "max_tool_calls": 2,
                        "input": {"file_name": "readings.csv",
                                  "csv_base64": base64.b64encode(b"batch,reading\na,1\nb,\n").decode("ascii"),
                                  "spec_base64": base64.b64encode(canonical(spec).encode("utf-8")).decode("ascii")}})
        self.project, _ = manager.binding()

    @staticmethod
    def arguments(context):
        return {"plan": {"question": "Which readings need source information?", "basis": "Saved quality feedback",
                         "steps": "Inspect missing records before comparing the groups.",
                         "expected_feedback": "A source explanation determines the next comparison."},
                "reason": "Make the recorded data-quality issue determine the next step.",
                "feedback_action_ids": [item["action_id"] for item in context["feedback"]],
                "expected_improvement": "The next step addresses the observed information gap."}

    def test_context_reads_saved_feedback_without_advancing_and_retains_proposal_binding(self):
        initial = protocol.build_context(self.project)
        initial_proposal = protocol.build_proposal(initial, self.arguments(initial), "Delegated fixture")
        self.assertEqual(initial_proposal["feedback_action_ids"], [])
        self.project.step(request_id="quality-for-plan")
        before = self.project.status()
        context = protocol.build_context(self.project)
        self.assertEqual(self.project.status(), before)
        action = before["actions"][0]
        feedback = context["feedback"][0]
        self.assertEqual(feedback["action_id"], action["id"])
        self.assertEqual(feedback["observations"], action["observations"])
        self.assertEqual(feedback["next_decision"], action["next_decision"])
        self.assertEqual(feedback["artifact_ref"], action["artifact"])
        self.assertIn(canonical(context), protocol.build_prompt(context)["prompt"])
        self.assertEqual(json.loads(protocol.build_prompt(context)["prompt"].split("\n", 1)[1]), context)
        response = canonical(self.arguments(context)).encode("utf-8")
        parsed = protocol.parse_host_response(response, "delegated")
        proposal = protocol.build_proposal(context, parsed["arguments"], "Delegated fixture")
        self.assertEqual(proposal["context_sha256"], context["selection_context"]["context_sha256"])
        self.assertEqual(protocol.validate_proposal(context, proposal), proposal)
        self.assertIsNone(parsed["reported_cost_usd"])
        envelope = {"type": "result", "subtype": "success", "is_error": False, "result": response.decode("utf-8"),
                    "modelUsage": {"declared-model": {}}, "usage": {"output_tokens": 5}, "total_cost_usd": 0.01}
        cli = protocol.parse_host_response(canonical(envelope).encode("utf-8"), "claude_cli")
        self.assertEqual(cli["arguments"], parsed["arguments"])
        self.assertEqual(cli["reported_models"], ["declared-model"])
        self.assertEqual(cli["reported_cost_usd"], 0.01)

    def test_rejects_unknown_feedback_changed_binding_and_oversized_context(self):
        self.project.step(request_id="quality-for-plan")
        context = protocol.build_context(self.project)
        arguments = self.arguments(context)
        for references in ([], ["unknown-action"]):
            invalid = {**arguments, "feedback_action_ids": references}
            with self.subTest(references=references), self.assertRaises(ResearchError) as caught:
                protocol.build_proposal(context, invalid, "Delegated fixture")
            self.assertEqual(caught.exception.code, "INVALID_PLAN_PROPOSAL")
        proposal = protocol.build_proposal(context, arguments, "Delegated fixture")
        proposal["context_sha256"] = "0" * 64
        with self.assertRaises(ResearchError) as caught:
            protocol.validate_proposal(context, proposal)
        self.assertEqual(caught.exception.code, "STALE_SELECTION_CONTEXT")
        changed = copy.deepcopy(context)
        changed["selection_context"]["goal"] = "Changed outside the frozen host context"
        with self.assertRaises(ResearchError) as caught:
            protocol.build_prompt(changed)
        self.assertEqual(caught.exception.code, "INVALID_SELECTION_CONTEXT")
        oversized = copy.deepcopy(context)
        oversized["feedback"][0]["observations"].append({"statement": "x" * protocol.MAX_CONTEXT_BYTES})
        with self.assertRaises(ResearchError) as caught:
            protocol.build_prompt(oversized)
        self.assertEqual(caught.exception.code, "INVALID_PLAN_CONTEXT")
        with self.assertRaises(ResearchError):
            protocol.parse_host_response(b'{"plan":{},"plan":{}}', "delegated")

    def test_researcher_feedback_extends_context_without_becoming_tool_feedback(self):
        self.project.save_plan(request_id="plan-before-note", expected_state_version=0,
                               plan=self.arguments({"feedback": []})["plan"], reason="Record the initial route.")
        before = self.project.status()
        old_research = protocol.build_context(self.project)
        old_selection = old_research["selection_context"]
        self.assertNotIn("researcher_feedback", old_selection)
        old_plan_proposal = protocol.build_proposal(old_research, self.arguments(old_research), "Protocol fixture")
        recipe = {"schema_version": "research-recipe-v1", "id": "note-contract", "version": 1,
                  "question": "Select the next eligible method.", "need": "next_check",
                  "scope_match": {"domain": "data", "contract": "tabular-quality-v1"},
                  "ordered_methods": [{"method_id": "data.tabular-quality-audit", "evaluation_ref": "tabular-quality-v1"}],
                  "on_no_match": "wait"}
        old_decision = research_recipe.compile_recipe(recipe, old_selection)
        # This failed record is a pure protocol fixture. No tool action is dispatched.
        old_recipe_research = copy.deepcopy(old_research)
        old_recipe_research["feedback"] = [{"action_id": "fixture-failed-action", "request_id": "fixture-request",
            "method_id": "fixture-method", "status": "failed", "observations": [], "next_decision": None,
            "failure": {"code": "PROTOCOL_FIXTURE_ONLY"}, "artifact_ref": None}]
        old_recipe_context = {"schema_version": "recipe-change-context-v1", "research_context": old_recipe_research,
                              "current_recipe": recipe, "improvement_goal": "Keep trace identities distinct."}
        candidate = dict(copy.deepcopy(recipe), version=2)
        recipe_arguments = {"candidate": candidate, "reason": "Protocol fixture", "feedback_action_ids": ["fixture-failed-action"],
                            "expected_improvement": "Preserve the intended evidence scope.", "validation_plan": "Check frozen bindings."}
        old_recipe_proposal = recipe_change_proposal.build_proposal(old_recipe_context, recipe_arguments, "Protocol fixture")
        comment = "  Preserve this self-reported statement exactly.\nIts interpretation remains unverified.  "
        note = self.project.record_feedback(request_id="user-note-context", expected_state_version=before["state_version"],
            author="Researcher fixture", comment=comment,
            next_step="Review the declared grouping before extending the research route.", action_id=None)
        current = self.project.status()
        research = protocol.build_context(self.project)
        selection = research["selection_context"]
        self.assertEqual(current["budget"], before["budget"])
        self.assertEqual(current["actions"], before["actions"])
        self.assertEqual(current["evidence_actions"], before["evidence_actions"])
        self.assertEqual(selection["researcher_feedback"], [note])
        self.assertEqual(note["comment"], comment)
        self.assertEqual(note["plan_version"], 1)
        self.assertEqual(note["content_trust"], "unverified_researcher_statement")
        self.assertEqual(research["feedback"], [])
        self.assertEqual(selection, seal_context({key: value for key, value in selection.items() if key != "context_sha256"}))
        self.assertNotEqual(selection["context_sha256"], old_selection["context_sha256"])
        self.assertIn(canonical(note), host_selection_protocol.build_prompt(selection)["prompt"])
        self.assertIn(canonical(note), protocol.build_prompt(research)["prompt"])
        recipe_context = copy.deepcopy(old_recipe_context)
        recipe_context["research_context"]["selection_context"] = selection
        self.assertIn(canonical(note), recipe_change_proposal.build_prompt(recipe_context)["prompt"])
        bad_plan_arguments = {**self.arguments(research), "feedback_action_ids": [note["id"]]}
        with self.assertRaises(ResearchError) as caught:
            protocol.build_proposal(research, bad_plan_arguments, "Protocol fixture")
        self.assertEqual(caught.exception.code, "INVALID_PLAN_PROPOSAL")
        with self.assertRaises(ResearchError) as caught:
            recipe_change_proposal.build_proposal(recipe_context,
                {**recipe_arguments, "feedback_action_ids": [note["id"]]}, "Protocol fixture")
        self.assertEqual(caught.exception.code, "INVALID_RECIPE_CHANGE_PROPOSAL")
        changed = copy.deepcopy(selection)
        changed["researcher_feedback"][0]["comment"] = "Changed outside the frozen context"
        proposal = {**old_decision["proposal"], "context_sha256": selection["context_sha256"]}
        with self.assertRaises(ResearchError) as caught:
            validate_proposal(changed, proposal)
        self.assertEqual(caught.exception.code, "INVALID_SELECTION_CONTEXT")
        validate_proposal(old_selection, old_decision["proposal"])
        self.assertEqual(research_recipe.compile_recipe(recipe, old_selection), old_decision)
        self.assertEqual(protocol.validate_proposal(old_research, old_plan_proposal), old_plan_proposal)
        self.assertEqual(recipe_change_proposal.validate_proposal(old_recipe_context, old_recipe_proposal), old_recipe_proposal)
        self.assertEqual(self.project.status(), current)


if __name__ == "__main__":
    unittest.main()
