"""Independent synthetic staged preregistration and saved feedback; no model or fits."""
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

import test_retrieval_holdout as fixture
from autoresearch import (hypothesis_feedback as feedback, feedback_policy, project_selection,
                          staged_relevance_adapter as staged, retrieval_holdout as holdout,
                          relevance_retrieval_adapter as relevance, retrieval_lexical as lexical,
                          host_selection_protocol, project_report, research_project)
from autoresearch.contracts import ResearchError, canonical, fingerprint
from autoresearch.project_controller import ProjectController
from autoresearch.research_project import ResearchProject


class StagedHypothesisTests(unittest.TestCase):
    fixture = fixture.RetrievalHoldoutTests.fixture

    def setup_registered(self, sign=None, op="gt", branches=None):
        project, _, raw = self.fixture(sign)
        project.register_holdout(request_id="holdout", expected_state_version=project.status()["state_version"], holdout=raw)
        controller = ProjectController(project.root)
        context = controller.selection_context()
        candidate = next(c for c in context["candidates"] if c["method_id"] == staged.TOOL_ID)
        if branches is None:
            branches = {"condition_met": {"kind": "wait"},
                        "condition_not_met": {"kind": "method", "method_id": staged.AUDIT_TOOL_ID}}
        hypothesis = {"candidate_id": candidate["id"], "controller_request_id": "future", "metric": "recall@20",
                      "operator": op, "threshold": 0, "branches": branches}
        version = context["state_version"]
        original_budget = copy.deepcopy(project.status()["budget"])
        registration = project.register_hypothesis(request_id="prediction", expected_state_version=version, hypothesis=hypothesis)
        self.assertEqual(project.status()["budget"], original_budget)
        self.assertEqual(ResearchProject(project.root).register_hypothesis(request_id="prediction", expected_state_version=version,
                                                                           hypothesis=hypothesis), registration)
        return project, candidate, registration, hypothesis, version

    def primary(self, project, candidate):
        controller = ProjectController(project.root)
        context = controller.selection_context()
        proposal = {"schema_version": "project-selection-proposal-v1", "context_sha256": context["context_sha256"],
                    "provider": {"kind": "human", "label": "Synthetic engineering fixture"},
                    "choice": {"kind": "execute", "candidate_id": candidate["id"]},
                    "rationale": "Exercise preregistered source", "evidence_citation_ids": []}
        return controller.advance_selection(request_id="future", expected_state_version=context["state_version"], proposal=proposal)

    def test_real_zero_not_met_saved_audit_private_guards_and_replay(self):
        project, candidate, registration, hypothesis, version = self.setup_registered()
        pending = feedback.feedback_context(project, project.status())["items"][0]
        self.assertEqual((pending["outcome"], pending["value"]), ("unknown", None))
        self.assertEqual(self.primary(project, candidate)["status"], "completed")
        before = project.status()
        self.assertEqual(before["budget"]["local_tool_calls_used"], 1)
        private = project.root / holdout.PRIVATE_DIR / holdout.PRIVATE_FILE
        real_open, real_os_open = Path.open, os.open
        def path_open(path, *args, **kwargs):
            if path == private:
                raise AssertionError("private holdout must not be opened")
            return real_open(path, *args, **kwargs)
        def os_open(path, *args, **kwargs):
            if not isinstance(path, int) and Path(path) == private:
                raise AssertionError("private holdout must not be opened")
            return real_os_open(path, *args, **kwargs)
        with patch.object(Path, "open", path_open), patch.object(os, "open", os_open), \
             patch.object(holdout, "_verified_private", side_effect=AssertionError("no private reader")), \
             patch.object(lexical, "build_index", side_effect=AssertionError("no index")), \
             patch.object(lexical, "metrics", side_effect=AssertionError("no scoring")), \
             patch.object(relevance, "retrieve", side_effect=AssertionError("no ranking")):
            project = ResearchProject(project.root)
            controller = ProjectController(project.root)
            context = controller.selection_context()
            item = context["hypothesis_feedback"]["items"][0]
            self.assertEqual((item["value"], item["outcome"], item["unknown_reason"]), (0, "condition_not_met", None))
            self.assertEqual(context["hypothesis_feedback"]["test_notice"], feedback.STAGED_NOTICE)
            self.assertEqual(project.status()["budget"], before["budget"])
            prompt = host_selection_protocol.build_prompt(context)
            report = project_report.collect_report(project.root)
            for value in (canonical(context), canonical(prompt), canonical(report["input"])):
                self.assertNotIn("SECRET_FINAL_QUERY", value)
                self.assertNotIn("final-q", value)
            self.assertIn("final evaluation requires separate registration", prompt["system"])
            original_version = project.status()["state_version"]
            audit = controller.advance_feedback(request_id="branch", registration_request_id="prediction",
                                                 expected_state_version=original_version)
            self.assertEqual(audit["status"], "completed")
            after = project.status()
            self.assertEqual([a["command"] for a in after["actions"]], [staged.TOOL_ID, staged.AUDIT_TOOL_ID])
            self.assertEqual(after["actions"][1]["parameters"], {"based_on_action_id": item["action_id"],
                                                                 "based_on_result_sha256": item["result_sha256"]})
            self.assertEqual(after["budget"]["local_tool_calls_used"], 2)
            self.assertEqual(after["budget"]["local_tool_call_limit"], before["budget"]["local_tool_call_limit"])
            self.assertEqual((after["budget"]["new_fits"], after["budget"]["new_model_requests"]), (0, 0))
            replay = ProjectController(project.root).advance_feedback(request_id="branch", registration_request_id="prediction",
                                                                       expected_state_version=original_version)
            self.assertTrue(replay["replayed"])
            self.assertEqual(ResearchProject(project.root).status(), after)
            child = subprocess.check_output([sys.executable, "-c",
                "import json,sys; from autoresearch.project_controller import ProjectController; "
                "print(json.dumps(ProjectController(sys.argv[1]).advance_feedback(request_id='branch', "
                "registration_request_id='prediction', expected_state_version=int(sys.argv[2]))))",
                str(project.root), str(original_version)], env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}, timeout=30)
            self.assertTrue(json.loads(child)["replayed"])
            self.assertEqual(ResearchProject(project.root).status(), after)

    def test_positive_negative_and_zero_comparisons(self):
        for sign, op, expected_value, expected_outcome in (("positive", "gt", 1, "condition_met"),
                ("negative", "gt", -1, "condition_not_met"), (None, "gte", 0, "condition_met"),
                (None, "eq", 0, "condition_met")):
            with self.subTest(sign=sign, op=op):
                project, candidate, registration, _, _ = self.setup_registered(sign, op)
                self.primary(project, candidate)
                context = ProjectController(project.root).selection_context()
                item = context["hypothesis_feedback"]["items"][0]
                self.assertEqual((item["value"], item["outcome"]), (expected_value, expected_outcome))
                choice = feedback_policy.select_from_feedback(context, registration=registration,
                         provider={"kind": "human", "label": "fixture"})["choice"]
                self.assertEqual(choice["kind"], "execute" if expected_outcome == "condition_not_met" else "wait")

    def test_resealed_foreign_qrels_produce_unknown_without_dispatch(self):
        project, candidate, registration, _, _ = self.setup_registered()
        self.primary(project, candidate)
        state = project.status()
        action = state["actions"][0]
        path = project._artifact(action)
        env = json.loads(path.read_bytes())
        for row in env["tool_result"]["result"]["per_query_metrics"]:
            if row["query_id"] == "qv":
                row["qrel_locator"]["document_grades"]["b"] = 2
        env["sha256"] = fingerprint({k: v for k, v in env.items() if k != "sha256"})
        path.write_text(canonical(env))
        action["result_sha256"] = env["sha256"]
        with project._writer(), project._connect() as con:
            stored = project._project(con)
            parent = next(p for p in stored["controller_requests"] if p["request_id"] == "future")
            parent["result"]["child"]["result_sha256"] = env["sha256"]
            con.execute("UPDATE actions SET record=? WHERE request_id=?", (canonical(action), action["request_id"]))
            project._save(con, stored)
        after = project.status()
        context = ProjectController(project.root).selection_context()
        item = context["hypothesis_feedback"]["items"][0]
        self.assertEqual((item["outcome"], item["value"]), ("unknown", None))
        choice = feedback_policy.select_from_feedback(context, registration=registration,
                     provider={"kind": "human", "label": "fixture"})["choice"]
        self.assertEqual(choice, {"kind": "wait"})
        self.assertEqual(project.status()["budget"], after["budget"])

    def test_forbidden_branches_notice_mixing_and_conflicting_request(self):
        project, candidate, registration, hypothesis, version = self.setup_registered()
        changed = {**hypothesis, "threshold": 0.5}
        with self.assertRaises(ResearchError) as caught:
            project.register_hypothesis(request_id="prediction", expected_state_version=version, hypothesis=changed)
        self.assertEqual(caught.exception.code, "IDEMPOTENCY_CONFLICT")
        for method in (holdout.FINAL_TOOL_ID, relevance.AUDIT_TOOL_ID):
            with self.subTest(method=method), self.assertRaises(ResearchError):
                feedback_policy.validate_branches({"condition_met": {"kind": "wait"},
                    "condition_not_met": {"kind": "method", "method_id": method}}, primary_method_id=staged.TOOL_ID)
        context = ProjectController(project.root).selection_context()["hypothesis_feedback"]
        altered = copy.deepcopy(context)
        altered["test_notice"] = feedback.TEST_NOTICE
        with self.assertRaises(ResearchError):
            feedback.validate_context(altered)
        other = copy.deepcopy(context["items"][0])
        other["request_id"] = "another"
        other["candidate"]["method_id"] = relevance.TOOL_ID
        other.pop("branches")
        altered = copy.deepcopy(context)
        altered["items"].append(other)
        with self.assertRaises(ResearchError):
            feedback.validate_context(altered)

    def test_interrupted_original_parent_is_unknown_and_cannot_select_audit(self):
        project, candidate, registration, _, _ = self.setup_registered()
        controller = ProjectController(project.root)
        with patch.object(ProjectController, "_dispatch", side_effect=KeyboardInterrupt("synthetic interruption")):
            with self.assertRaises(KeyboardInterrupt):
                self.primary(project, candidate)
        original = ResearchProject(project.root).status()
        self.assertEqual(original["actions"], [])
        context = ProjectController(project.root).selection_context()
        item = context["hypothesis_feedback"]["items"][0]
        self.assertEqual((item["outcome"], item["value"], item["unknown_reason"]),
                         ("unknown", None, "controller_prepared"))
        choice = feedback_policy.select_from_feedback(context, registration=registration,
                 provider={"kind": "human", "label": "fixture"})["choice"]
        self.assertEqual(choice, {"kind": "wait"})
        self.assertEqual(ResearchProject(project.root).status(), original)

    def test_future_id_claim_and_changed_code_stop_without_an_action(self):
        project, candidate, registration, hypothesis, _ = self.setup_registered()
        project.record_feedback(request_id="future", expected_state_version=project.status()["state_version"],
                                author="fixture", comment="Claim the original future ID", next_step="", action_id=None)
        before = project.status()
        item = feedback.feedback_context(project, before)["items"][0]
        self.assertEqual((item["outcome"], item["unknown_reason"], item["value"]),
                         ("unknown", "controller_id_claimed_by_other_command", None))
        self.assertEqual(before["actions"], [])
        new_request = {**hypothesis, "controller_request_id": "different-future"}
        with patch.object(research_project, "code_identity", return_value="f" * 64):
            with self.assertRaises(ResearchError) as caught:
                project.register_hypothesis(request_id="another", expected_state_version=before["state_version"],
                                            hypothesis=new_request)
        self.assertEqual(caught.exception.code, "CODE_CHANGED")
        self.assertEqual(project.status(), before)


if __name__ == "__main__":
    unittest.main()
