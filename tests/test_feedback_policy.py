"""Synthetic local routing checks; no model, network, or estimator fits."""
import copy
import tempfile
import unittest
from pathlib import Path

import test_relevance_retrieval_adapter as fixture
from autoresearch import feedback_policy, hypothesis_feedback, project_selection
from autoresearch import relevance_retrieval_adapter as family
from autoresearch.contracts import ResearchError, canonical
from autoresearch.project_controller import ProjectController
from autoresearch.research_project import ResearchProject


class FeedbackPolicyTests(unittest.TestCase):
    def setup_project(self, op="gt"):
        helper = fixture.RelevanceRetrievalAdapterTests()
        helper.setUp()
        self.addCleanup(helper.doCleanups)
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        input_dir = Path(temp.name) / "input"
        input_dir.mkdir()
        source = input_dir / "packet.json"
        source.write_text(canonical(helper.captured()))
        project = ResearchProject(Path(temp.name) / "project")
        project.create(source=source, goal="Synthetic routing fixture", budget_ref="fixture", max_tool_calls=2, method_id=family.TOOL_ID)
        project.save_plan(request_id="plan", expected_state_version=project.status()["state_version"],
                          plan={"question": "Fixture?", "basis": "synthetic", "steps": "Fixed pair then audit",
                                "expected_feedback": "Compare validation delta"}, reason="test")
        controller = ProjectController(project.root)
        context = controller.selection_context()
        candidate = next(c for c in context["candidates"] if c["method_id"] == family.TOOL_ID)
        branches = {"condition_met": {"kind": "wait"},
                    "condition_not_met": {"kind": "method", "method_id": family.AUDIT_TOOL_ID}}
        hypothesis = {"candidate_id": candidate["id"], "controller_request_id": "target", "metric": "recall@20",
                      "operator": op, "threshold": 0, "branches": branches}
        registration = hypothesis_feedback.register(project, request_id="prediction", expected_state_version=context["state_version"], hypothesis=hypothesis)
        return project, controller, registration, candidate

    def compile(self, controller, registration, context=None):
        return feedback_policy.select_from_feedback(context or controller.selection_context(), registration=registration,
                                                   provider={"kind": "operator_assistant", "label": "test policy"})

    def execute_primary(self, controller, candidate):
        context = controller.selection_context()
        proposal = {"schema_version": "project-selection-proposal-v1", "context_sha256": context["context_sha256"],
                    "provider": {"kind": "human", "label": "fixture"},
                    "choice": {"kind": "execute", "candidate_id": candidate["id"]},
                    "rationale": "Run the preregistered fixture", "evidence_citation_ids": []}
        self.assertEqual(controller.advance_selection(request_id="target", proposal=proposal,
                                                      expected_state_version=context["state_version"])["status"], "completed")

    def test_known_zero_routes_exact_audit_and_unknown_waits(self):
        project, controller, registration, candidate = self.setup_project()
        self.assertEqual(self.compile(controller, registration)["choice"], {"kind": "wait"})
        self.execute_primary(controller, candidate)
        context = controller.selection_context()
        feedback = context["hypothesis_feedback"]["items"][0]
        self.assertEqual((feedback["value"], feedback["outcome"]), (0, "condition_not_met"))
        proposal = self.compile(controller, registration, context)
        selected = project_selection.validate_proposal(context, proposal)["candidate"]
        self.assertEqual(selected["method_id"], family.AUDIT_TOOL_ID)
        self.assertEqual(selected["parameters"], {"based_on_action_id": feedback["action_id"],
                                                  "based_on_result_sha256": feedback["result_sha256"]})
        # The compiler itself has no action side effects.
        self.assertEqual(project.status()["budget"]["local_tool_calls_used"], 1)

    def test_met_waits_and_invalid_or_absent_candidates_wait(self):
        project, controller, registration, candidate = self.setup_project(op="gte")
        self.execute_primary(controller, candidate)
        self.assertEqual(self.compile(controller, registration)["choice"], {"kind": "wait"})
        project2, controller2, registration2, candidate2 = self.setup_project()
        self.execute_primary(controller2, candidate2)
        context = controller2.selection_context()
        payload = copy.deepcopy(context)
        del payload["context_sha256"]
        payload["candidates"] = []
        self.assertEqual(self.compile(controller2, registration2, project_selection.seal_context(payload))["choice"], {"kind": "wait"})
        payload = copy.deepcopy(context)
        del payload["context_sha256"]
        audit = next(c for c in payload["candidates"] if c["method_id"] == family.AUDIT_TOOL_ID)
        audit["parameters"]["based_on_result_sha256"] = "f" * 64
        self.assertEqual(self.compile(controller2, registration2, project_selection.seal_context(payload))["choice"], {"kind": "wait"})
        payload["blockers"] = [{"code": "EXECUTION_UNKNOWN", "reason": "fixture"}]
        self.assertEqual(self.compile(controller2, registration2, project_selection.seal_context(payload))["choice"], {"kind": "wait"})

    def test_hash_tampering_and_forbidden_branch_fail_closed(self):
        project, controller, registration, candidate = self.setup_project()
        for branches in ({"condition_met": {"kind": "wait"}, "condition_not_met": {"kind": "wait"}, "unknown": {"kind": "wait"}},
                         {"condition_met": {"kind": "method", "method_id": "other"}, "condition_not_met": {"kind": "wait"}},
                         {"condition_met": {"kind": "method", "method_id": family.AUDIT_TOOL_ID, "parameters": {}}, "condition_not_met": {"kind": "wait"}}):
            with self.assertRaises(ResearchError):
                feedback_policy.validate_branches(branches, primary_method_id=family.TOOL_ID)
        changed = copy.deepcopy(registration)
        changed["branches"]["condition_met"] = {"kind": "method", "method_id": family.AUDIT_TOOL_ID}
        with self.assertRaises(ResearchError):
            self.compile(controller, changed)
        context = controller.selection_context()
        context["state_version"] += 1
        with self.assertRaises(ResearchError):
            self.compile(controller, registration, context)
