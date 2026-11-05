"""Saved plan revisions use the normal manager/core path without model calls."""

import base64
import copy
from pathlib import Path
import tempfile
import unittest

from autoresearch.contracts import ResearchError, canonical
from autoresearch.host_selection_protocol import build_prompt
from autoresearch.local_workbench import LocalWorkbench
from autoresearch.project_controller import ProjectController
from autoresearch.project_selection import validate_proposal
from autoresearch.project_workbench import _projection
from autoresearch.project_report import collect_report, _markdown


class ResearchPlanTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory())) / "workbench"
        self.manager = LocalWorkbench(self.root)
        spec = {"schema_version": "tabular-quality-spec-v1", "file": "measurements.csv", "dataset_label": "Plan fixture",
                "source_url": "urn:test:research-plan", "license_note": "Fixture", "sample_unit": "declared_record",
                "group_columns": ["batch"], "key_columns": [], "numeric_columns": ["reading"], "target_column": "reading",
                "target_unit": "declared_unit", "missing_tokens": ["", "NA"], "delimiter": ",",
                "provenance": {"origin_sha256": "a" * 64, "description": "Constructed development input"}}
        self.manager.create({"request_id": "create-plan-fixture", "goal": "Inspect a constructed table",
                             "budget_ref": "plan-fixture-not-historical-spend", "max_tool_calls": 2,
                             "input": {"file_name": "measurements.csv", "csv_base64": base64.b64encode(b"batch,reading\na,1\nb,2\n").decode("ascii"),
                                       "spec_base64": base64.b64encode(canonical(spec).encode("utf-8")).decode("ascii")}})
        self.project, _ = self.manager.binding()

    def command(self, request_id="save-plan-1"):
        state = self.project.status()
        return {"request_id": request_id, "project_id": state["id"], "expected_state_version": state["state_version"],
                "plan": {"question": "Can the recorded readings be compared?", "basis": "",
                         "steps": "Inspect missing values.\nCompare the declared groups.",
                         "expected_feedback": "Decide whether group differences need more source information."},
                "reason": "Set the first explicit research route."}

    def test_save_reopen_replay_and_model_context_preserve_plan_and_budget(self):
        before = self.project.status()
        self.assertNotIn("research_plan", ProjectController(self.project.root).selection_context())
        body = self.command()
        saved = self.manager.save_plan(body)
        reopened = LocalWorkbench(self.root)
        replay = reopened.save_plan(body)
        self.assertTrue(replay["replayed"])
        self.assertEqual(saved["research_plan"], replay["research_plan"])
        state = self.project.status()
        self.assertEqual(state["state_version"], before["state_version"] + 1)
        self.assertEqual(len(state["plan_revisions"]), 1)
        self.assertEqual(state["budget"], before["budget"])
        self.assertEqual(state["actions"], before["actions"])
        context = ProjectController(self.project.root).selection_context()
        self.assertEqual(context["research_plan"], saved["research_plan"])
        self.assertIn(canonical(saved["research_plan"]), build_prompt(context)["prompt"])
        proposal = {"schema_version": "project-selection-proposal-v1", "context_sha256": context["context_sha256"],
                    "provider": {"kind": "human", "label": "Plan fixture"}, "choice": {"kind": "wait"},
                    "rationale": "Inspect the saved research route before execution.", "evidence_citation_ids": []}
        self.assertIsNone(validate_proposal(context, proposal)["candidate"])
        revised = self.command("save-plan-2")
        revised["plan"]["steps"] = "Inspect missing values first, then decide whether groups are comparable."
        revised["reason"] = "Clarify the decision before comparing groups."
        self.assertEqual(reopened.save_plan(revised)["research_plan"]["version"], 2)
        current = self.project.status()
        view = _projection(self.project, current)["research_plan"]
        self.assertEqual(view["current"], current["plan_revisions"][-1])
        self.assertEqual([item["version"] for item in view["revisions"]], [1, 2])
        self.assertEqual(self.manager.save_plan(body)["research_plan"]["version"], 1)
        with self.assertRaises(ResearchError) as caught:
            ProjectController(self.project.root).advance_selection(request_id="stale-plan-selection", proposal=proposal,
                                                                 expected_state_version=current["state_version"])
        self.assertEqual(caught.exception.code, "STALE_SELECTION_CONTEXT")
        self.assertEqual(self.project.status()["budget"], before["budget"])

    def test_researcher_feedback_preserves_legacy_reads_replay_identity_and_budget(self):
        with self.project._writer(), self.project._connect() as con:
            legacy = self.project._project(con)
            legacy.pop("researcher_feedback", None)
            self.project._save(con, legacy)
        before = self.project.status()
        raw_before = self.project.db.read_bytes()
        self.assertEqual(_projection(self.project, before)["researcher_feedback"], [])
        self.assertEqual(self.project.status(), before)
        self.assertEqual(self.project.db.read_bytes(), raw_before)
        command = {"request_id": "feedback-core", "expected_state_version": before["state_version"],
                   "author": "Fixture researcher", "comment": "Check the declared unit before interpretation.\n"
                   + str(self.project.root) + "\n" + Path(__file__).resolve().parents[1].as_posix(),
                   "next_step": "Request the original measurement definition.", "action_id": None}
        saved = self.project.record_feedback(**command)
        after = self.project.status()
        self.assertEqual(saved["id"], "feedback-feedback-core")
        self.assertIsNone(saved["plan_version"])
        self.assertEqual(saved["content_trust"], "unverified_researcher_statement")
        self.assertEqual(after["state_version"], before["state_version"] + 1)
        self.assertEqual(after["budget"], before["budget"])
        self.assertEqual(after["actions"], before["actions"])
        self.assertEqual(after["evidence_actions"], before["evidence_actions"])
        self.assertEqual(after["code_identity"], before["code_identity"])
        self.assertEqual(_projection(self.project, after)["researcher_feedback"], [saved])
        self.assertEqual(self.project.record_feedback(**command), saved)
        self.assertEqual(self.project.status(), after)
        for values, code in (({**command, "comment": "Changed under the original ID"}, "IDEMPOTENCY_CONFLICT"),
                             ({**command, "request_id": "feedback-stale"}, "STALE_STATE"),
                             ({**command, "request_id": "feedback-foreign-action", "expected_state_version": after["state_version"],
                               "action_id": "action-not-this-project"}, "INVALID_REQUEST")):
            with self.subTest(code=code), self.assertRaises(ResearchError) as caught:
                self.project.record_feedback(**values)
            self.assertEqual(caught.exception.code, code)
            self.assertEqual(self.project.status(), after)
        with self.assertRaises(ResearchError) as caught:
            self.project.save_plan(request_id=command["request_id"], expected_state_version=after["state_version"],
                                   plan=self.command()["plan"], reason="Attempt to reuse a feedback request.")
        self.assertEqual(caught.exception.code, "IDEMPOTENCY_CONFLICT")
        report = collect_report(self.project.root)
        self.assertEqual(report["project_snapshot_ref"], after["snapshot_ref"])
        self.assertEqual(report["input"]["researcher_feedback"], [saved])
        self.assertIn(saved["comment"], _markdown(report))
        self.assertIn("未核验意见", _markdown(report))
        self.assertEqual(self.project.status(), after)

    def test_stale_conflicting_and_unknown_requests_do_not_change_plan_or_usage(self):
        saved = self.command()
        self.manager.save_plan(saved)
        before = self.project.status()
        stale = {**self.command("stale-plan"), "expected_state_version": saved["expected_state_version"]}
        changed = copy.deepcopy(saved)
        changed["plan"]["question"] = "Changed under an already saved request ID"
        for body, code in ((stale, "STALE_STATE"), (changed, "IDEMPOTENCY_CONFLICT")):
            with self.subTest(code=code), self.assertRaises(ResearchError) as caught:
                self.manager.save_plan(body)
            self.assertEqual(caught.exception.code, code)
            self.assertEqual(self.project.status(), before)
        with self.assertRaises(ResearchError) as caught:
            self.project.step(request_id=saved["request_id"])
        self.assertEqual(caught.exception.code, "IDEMPOTENCY_CONFLICT")
        with self.project._writer(), self.project._connect() as con:
            raw = self.project._project(con)
            raw["source_requests"] = [{"request_id": "fixture-unknown-source", "status": "unknown"}]
            raw["state_version"] += 1
            self.project._save(con, raw)
        unknown = self.project.status()
        with self.assertRaises(ResearchError) as caught:
            self.manager.save_plan(self.command("save-while-unknown"))
        self.assertEqual(caught.exception.code, "EXECUTION_UNKNOWN")
        self.assertEqual(self.project.status(), unknown)


if __name__ == "__main__":
    unittest.main()
