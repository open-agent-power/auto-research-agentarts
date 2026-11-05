"""Plan proposals use actual saved feedback and retain its host binding."""

import base64
import copy
from pathlib import Path
import tempfile
import unittest

from autoresearch import research_plan_proposal as protocol
from autoresearch.contracts import ResearchError, canonical
from autoresearch.local_workbench import LocalWorkbench


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


if __name__ == "__main__":
    unittest.main()
