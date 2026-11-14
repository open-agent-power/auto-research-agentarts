"""Independent tiny synthetic projects; no historical study, model, API or fit."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import test_relevance_retrieval_adapter as relevance_fixture
import test_retrieval_adapter as citation_fixture
from autoresearch import hypothesis_feedback as feedback
from autoresearch import relevance_retrieval_adapter as relevance, retrieval_adapter as citation, retrieval_lexical
from autoresearch.contracts import ResearchError, canonical, fingerprint
from autoresearch.project_controller import ProjectController
from autoresearch.research_project import ResearchProject


class HypothesisFeedbackTests(unittest.TestCase):
    def fixture(self, family=relevance):
        helper = (relevance_fixture.RelevanceRetrievalAdapterTests() if family is relevance
                  else citation_fixture.RetrievalAdapterTests())
        helper.setUp()
        self.addCleanup(helper.doCleanups)
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        source_dir = root / "input"
        source_dir.mkdir()
        source = source_dir / "source.json"
        source.write_text(canonical(helper.captured()))
        project = ResearchProject(root / "project")
        project.create(source=source, goal="Tiny synthetic fixture; no scientific evidence", budget_ref="fixture", max_tool_calls=1,
                       method_id=family.TOOL_ID)
        project.save_plan(request_id="plan", expected_state_version=project.status()["state_version"],
                          plan={"question": "Fixture?", "basis": "Synthetic only", "steps": "Fixed pair",
                                "expected_feedback": "Compare paired validation means"}, reason="Test only")
        context = ProjectController(project.root).selection_context()
        candidate = next(x for x in context["candidates"] if x["method_id"] == family.TOOL_ID)
        return project, candidate

    def register(self, project, candidate, op="gt", request_id="prediction", controller_id="future"):
        hypothesis = {"candidate_id": candidate["id"], "controller_request_id": controller_id,
                      "metric": "recall@20", "operator": op, "threshold": 0}
        version = project.status()["state_version"]
        record = feedback.register(project, request_id=request_id, expected_state_version=version, hypothesis=hypothesis)
        return record, hypothesis, version

    def execute(self, project, candidate, request_id="future"):
        controller = ProjectController(project.root)
        context = controller.selection_context()
        proposal = {"schema_version": "project-selection-proposal-v1", "context_sha256": context["context_sha256"],
                    "provider": {"kind": "operator_assistant", "label": "Synthetic fixture"},
                    "choice": {"kind": "execute", "candidate_id": candidate["id"]},
                    "rationale": "Exercise the preregistered engineering fixture", "evidence_citation_ids": []}
        return controller.advance_selection(request_id=request_id, proposal=proposal, expected_state_version=context["state_version"])

    def test_both_families_real_restart_zero_and_tamper(self):
        for family, op, expected in ((relevance, "gt", "condition_not_met"), (citation, "gte", "condition_met")):
            with self.subTest(family=family.TOOL_ID):
                project, candidate = self.fixture(family)
                before = project.status()["budget"]
                record, hypothesis, version = self.register(project, candidate, op)
                self.assertEqual(project.status()["budget"], before)
                reopened = ResearchProject(project.root)
                self.assertEqual(feedback.register(reopened, request_id="prediction", expected_state_version=version,
                                                   hypothesis=hypothesis), record)
                changed = dict(hypothesis, operator="lt")
                with self.assertRaises(ResearchError) as failure:
                    feedback.register(reopened, request_id="prediction", expected_state_version=version, hypothesis=changed)
                self.assertEqual(failure.exception.code, "IDEMPOTENCY_CONFLICT")
                waiting = feedback.feedback_context(reopened, reopened.status())["items"][0]
                self.assertEqual((waiting["outcome"], waiting["unknown_reason"]), ("unknown", "controller_not_started"))
                outcome = self.execute(reopened, candidate)
                self.assertEqual(outcome["status"], "completed")
                after = reopened.status()["budget"]
                with patch.object(retrieval_lexical, "metrics", side_effect=AssertionError("no rescoring")), \
                     patch.object(retrieval_lexical, "build_index", side_effect=AssertionError("no index")), \
                     patch.object(retrieval_lexical, "retrieve", side_effect=AssertionError("no retrieval")):
                    reopened = ResearchProject(project.root)
                    result = feedback.feedback_context(reopened, reopened.status())["items"][0]
                    self.assertEqual((result["outcome"], result["value"], result["unknown_reason"]), (expected, 0, None))
                    self.assertEqual(reopened.status()["budget"], after)
                    self.assertEqual(after["local_tool_calls_used"], 1)
                    self.assertEqual(after["local_tool_call_limit"], before["local_tool_call_limit"])
                    self.assertEqual(after["new_model_requests"], 0)
                    self.assertEqual(after["new_fits"], 0)
                action = reopened.status()["actions"][0]
                path = reopened._artifact(action)
                artifact = json.loads(path.read_text())
                artifact["tool_result"]["result"]["paired_summary"]["splits"]["validation"]["arms"][family.COMPARISON["candidate"]]["metrics"]["recall@20"] = 1
                path.write_text(canonical(artifact))
                damaged = feedback.feedback_context(reopened, reopened.status())["items"][0]
                self.assertEqual(damaged["outcome"], "unknown")
                self.assertIn("evidence", damaged["unknown_reason"])
                self.assertIsNone(damaged["value"])

    def test_source_pin_test_rejection_and_pending_gate(self):
        project, candidate = self.fixture()
        version = project.status()["state_version"]
        base = {"candidate_id": candidate["id"], "controller_request_id": "later", "metric": "recall@20", "operator": "gt", "threshold": 0}
        for bad in (dict(base, split="test"), dict(base, metric="test/recall@20"), dict(base, threshold=float("nan")),
                    dict(base, metric=[]), dict(base, metric={}), dict(base, operator=[]), dict(base, operator={}),
                    dict(base, threshold=10**1000), dict(base, threshold=True),
                    dict(base, threshold=float("inf")), dict(base, candidate_id={"nested": []}),
                    dict(base, controller_request_id=["not-an-id"])):
            with self.assertRaises(ResearchError):
                feedback.register(project, request_id="invalid", expected_state_version=version, hypothesis=bad)
        source = project.root / "source.json"
        original = source.read_bytes()
        source.write_bytes(original + b" ")
        with self.assertRaises(ResearchError) as failure:
            feedback.register(project, request_id="invalid", expected_state_version=version, hypothesis=base)
        self.assertEqual(failure.exception.code, "EVIDENCE_CHANGED")
        source.write_bytes(original)
        _, hypothesis, original_version = self.register(project, candidate)
        source.write_bytes(original + b" ")
        with self.assertRaises(ResearchError) as replay_failure:
            feedback.register(project, request_id="prediction", expected_state_version=original_version, hypothesis=hypothesis)
        self.assertEqual(replay_failure.exception.code, "EVIDENCE_CHANGED")
        item = feedback.feedback_context(project, project.status())["items"][0]
        self.assertEqual(item["outcome"], "unknown")
        self.assertIn("evidence_changed", item["unknown_reason"])

    def test_wrong_controller_or_changed_plan_cannot_become_a_known_result(self):
        project, candidate = self.fixture()
        self.register(project, candidate)
        project.save_plan(request_id="changed-plan", expected_state_version=project.status()["state_version"],
                          plan={"question": "Different?", "basis": "", "steps": "Fixed pair",
                                "expected_feedback": "Compare validation"}, reason="Change")
        self.execute(project, candidate)
        result = feedback.feedback_context(project, project.status())["items"][0]
        self.assertEqual((result["outcome"], result["unknown_reason"]), ("unknown", "controller_binding_changed"))

    def test_context_rejects_claim_that_zero_gt_zero_is_met(self):
        project, candidate = self.fixture()
        self.register(project, candidate)
        self.execute(project, candidate)
        value = feedback.feedback_context(project, project.status())
        bad = copy.deepcopy(value)
        bad["items"][0]["outcome"] = "condition_met"
        with self.assertRaises(ResearchError):
            feedback.validate_context(bad)
        for invalid in ([], {}, True, None):
            malformed = copy.deepcopy(value)
            malformed["items"][0]["condition"]["operator"] = invalid
            with self.subTest(invalid=invalid), self.assertRaises(ResearchError):
                feedback.validate_context(malformed)

    def test_interrupted_original_stays_unknown_and_blocks_new_registration(self):
        project, candidate = self.fixture()
        self.register(project, candidate)
        with patch.object(relevance, "execute", side_effect=KeyboardInterrupt) as execute:
            with self.assertRaises(KeyboardInterrupt):
                self.execute(project, candidate)
            state = ResearchProject(project.root).status()
            item = feedback.feedback_context(project, state)["items"][0]
            self.assertEqual(item["outcome"], "unknown")
            self.assertIn(item["unknown_reason"], ("controller_prepared", "controller_running", "controller_unknown"))
            proposed = {"candidate_id": candidate["id"], "controller_request_id": "other",
                        "metric": "recall@20", "operator": "gt", "threshold": 0}
            with self.assertRaises(ResearchError):
                feedback.register(project, request_id="second", expected_state_version=state["state_version"], hypothesis=proposed)
            execute.assert_called_once()
            self.assertEqual(project.status()["budget"]["local_tool_calls_reserved"], 1)

    def test_future_id_claimed_by_another_command_is_unknown(self):
        project, candidate = self.fixture()
        self.register(project, candidate)
        project.record_feedback(request_id="future", expected_state_version=project.status()["state_version"],
                                author="Fixture", comment="A different command claimed the ID.", next_step="", action_id=None)
        item = feedback.feedback_context(ResearchProject(project.root), project.status())["items"][0]
        self.assertEqual((item["outcome"], item["unknown_reason"]), ("unknown", "controller_id_claimed_by_other_command"))
        self.assertEqual(project.status()["budget"]["local_tool_calls_used"], 0)

    def test_named_controller_wait_does_not_supply_a_result(self):
        project, candidate = self.fixture()
        self.register(project, candidate)
        controller = ProjectController(project.root)
        context = controller.selection_context()
        proposal = {"schema_version": "project-selection-proposal-v1", "context_sha256": context["context_sha256"],
                    "provider": {"kind": "human", "label": "Fixture"}, "choice": {"kind": "wait"},
                    "rationale": "Do not execute the candidate", "evidence_citation_ids": []}
        self.assertEqual(controller.advance_selection(request_id="future", proposal=proposal)["status"], "waiting")
        item = feedback.feedback_context(project, project.status())["items"][0]
        self.assertEqual((item["outcome"], item["unknown_reason"]), ("unknown", "controller_waiting"))

    def test_observation_rejects_changed_parent_child_and_protocol_bindings(self):
        project, candidate = self.fixture()
        self.register(project, candidate)
        self.execute(project, candidate)
        original = project.status()
        self.assertEqual(feedback.feedback_context(project, original)["items"][0]["outcome"], "condition_not_met")
        altered = []
        changed = copy.deepcopy(original)
        changed["controller_requests"][0]["decision"]["selection_ref"]["candidate_id"] = "choice-other"
        changed["controller_requests"][0]["decision_sha256"] = fingerprint(changed["controller_requests"][0]["decision"])
        altered.append(changed)
        changed = copy.deepcopy(original)
        changed["controller_requests"][0]["controller_code_identity"] = "f" * 64
        altered.append(changed)
        changed = copy.deepcopy(original)
        changed["actions"][0]["method_instance"]["evaluation_ref"] = "different-protocol"
        altered.append(changed)
        changed = copy.deepcopy(original)
        changed["actions"][0]["request_id"] = "other-child"
        altered.append(changed)
        for state in altered:
            with self.subTest(state=state):
                self.assertEqual(feedback.feedback_context(project, state)["items"][0]["outcome"], "unknown")

    def test_rehashed_wrong_parent_request_and_inconsistent_child_receipt_are_unknown(self):
        project, candidate = self.fixture()
        self.register(project, candidate)
        self.execute(project, candidate)
        original = project.status()
        for field, value in (("project_id", "project-other"), ("command", "controller.advance"),
                             ("need", "other"), ("expected_state_version", 999)):
            state = copy.deepcopy(original)
            parent = state["controller_requests"][0]
            parent["request"][field] = value
            parent["request_sha256"] = fingerprint(parent["request"])
            with self.subTest(field=field):
                self.assertEqual(feedback.feedback_context(project, state)["items"][0]["outcome"], "unknown")
        for field, value in (("command", "other"), ("artifact", "artifacts/other.json"), ("failure", {"code": "FAILED"})):
            state = copy.deepcopy(original)
            state["controller_requests"][0]["result"]["child"][field] = value
            with self.subTest(field=field):
                self.assertEqual(feedback.feedback_context(project, state)["items"][0]["outcome"], "unknown")

    def test_child_database_fingerprint_disagreement_is_unknown(self):
        project, candidate = self.fixture()
        self.register(project, candidate)
        self.execute(project, candidate)
        before = project.status()
        action = before["actions"][0]
        with project._writer(), project._connect() as con:
            con.execute("UPDATE actions SET fingerprint=? WHERE request_id=?", ("f" * 64, action["request_id"]))
        item = feedback.feedback_context(ResearchProject(project.root), project.status())["items"][0]
        self.assertEqual((item["outcome"], item["unknown_reason"]), ("unknown", "child_binding_changed"))

    def test_optional_branches_are_bound_before_execution_and_preserved(self):
        for family in (relevance, citation):
            with self.subTest(family=family.TOOL_ID):
                project, candidate = self.fixture(family)
                version = project.status()["state_version"]
                branches = {"condition_met": {"kind": "wait"},
                            "condition_not_met": {"kind": "method", "method_id": family.AUDIT_TOOL_ID}}
                hypothesis = {"candidate_id": candidate["id"], "controller_request_id": "future", "metric": "recall@20",
                              "operator": "gt", "threshold": 0, "branches": branches}
                record = feedback.register(project, request_id="prediction", expected_state_version=version, hypothesis=hypothesis)
                self.assertEqual(record["branches"], branches)
                self.assertEqual(feedback.feedback_context(project, project.status())["items"][0]["branches"], branches)
                changed = copy.deepcopy(hypothesis)
                changed["branches"]["condition_not_met"] = {"kind": "wait"}
                with self.assertRaises(ResearchError) as error:
                    feedback.register(project, request_id="prediction", expected_state_version=version, hypothesis=changed)
                self.assertEqual(error.exception.code, "IDEMPOTENCY_CONFLICT")
                self.execute(project, candidate)
                result = feedback.feedback_context(ResearchProject(project.root), project.status())["items"][0]
                self.assertEqual((result["outcome"], result["branches"]), ("condition_not_met", branches))
                self.assertEqual(project.status()["budget"]["local_tool_calls_used"], 1)

    def test_branch_rejects_unknown_arbitrary_methods_or_parameters(self):
        project, candidate = self.fixture()
        version = project.status()["state_version"]
        hypothesis = {"candidate_id": candidate["id"], "controller_request_id": "future", "metric": "recall@20",
                      "operator": "gt", "threshold": 0}
        cases = [
            {"condition_met": {"kind": "wait"}, "condition_not_met": {"kind": "wait"}, "unknown": {"kind": "wait"}},
            {"condition_met": {"kind": "method", "method_id": citation.AUDIT_TOOL_ID}, "condition_not_met": {"kind": "wait"}},
            {"condition_met": {"kind": "method", "method_id": relevance.AUDIT_TOOL_ID, "parameters": {}}, "condition_not_met": {"kind": "wait"}},
            {"condition_met": {"kind": "wait"}},
        ]
        for branches in cases:
            with self.subTest(branches=branches), self.assertRaises(ResearchError):
                feedback.register(project, request_id="invalid", expected_state_version=version,
                                  hypothesis={**hypothesis, "branches": branches})
        self.assertEqual(project.status()["state_version"], version)
        self.assertEqual(project.status()["budget"]["local_tool_calls_used"], 0)


if __name__ == "__main__":
    unittest.main()
