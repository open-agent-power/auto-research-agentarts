"""Strict adoption of a sealed quality material; synthetic fixtures only."""
import copy
import sqlite3
import unittest
from unittest.mock import patch

import test_tabular_quality_feedback as fixture
from autoresearch.contracts import ResearchError, canonical, fingerprint
from autoresearch.host_model_selection import HostModelSelection
from autoresearch.research_project import ResearchProject


class SuppliedQualityAdoptionTests(unittest.TestCase):
    def stage(self, *, supplied=True, met=True, cite=True):
        f = fixture.QualityFeedbackTests(methodName="runTest")
        f.setUp(); self.addCleanup(f.doCleanups)
        reg = f.register(reg=f.valid if met else fixture.rules(fixture.condition("rows", "gt", 4)))
        f.execute()
        selector = {"kind":"tabular_quality_feedback", "registration_request_id":"reg",
                    "registration_sha256":reg["registration_sha256"]}
        host = HostModelSelection(f.project.root)
        host.prepare(request_id="strict-host", provider="delegated", purpose="plan",
                     expected_state_version=f.project.status()["state_version"], decision_limit=1,
                     cli_budget_usd=0.1, reason="Synthetic", saved_materials=[selector] if supplied else None)
        args = {"plan":{"question":"Synthetic", "basis":"Original material", "steps":"Consider results",
                        "expected_feedback":"Preserve uncertainty"}, "reason":"Synthetic revision",
                "expected_improvement":"Review", "feedback_action_ids":[f.project.status()["actions"][0]["id"]] if cite else []}
        path = f.root / "strict-response.json"; path.write_text(canonical(args), encoding="utf-8")
        host.import_response(request_id="strict-host", response_file=path)
        host.consume(request_id="strict-host")
        return f, host, args

    def test_exact_material_adopts_and_replays_without_model_or_research(self):
        for met in (True, False):
            with self.subTest(met=met):
                f, host, args = self.stage(met=met); budget = copy.deepcopy(f.project.status()["budget"])
                with patch.object(ResearchProject,"step",side_effect=AssertionError("step")), \
                     patch("autoresearch.host_model_selection.run_claude_selection",side_effect=AssertionError("model")):
                    result = host.adopt_supplied_quality_plan(request_id="strict-host", registration_request_id="reg")
                    replay = host.adopt_supplied_quality_plan(request_id="strict-host", registration_request_id="reg")
                self.assertEqual(result, replay)
                self.assertEqual(result["quality_adoption"]["schema_version"], "host-quality-adoption-v3")
                revision = result["outcome"]["research_plan"]
                self.assertEqual({key:revision[key] for key in args["plan"]}, args["plan"])
                self.assertEqual(revision["quality_feedback_ref"]["registration_request_id"], "reg")
                self.assertEqual(f.project.status()["budget"], budget)

    def test_missing_material_or_action_citation_does_not_write(self):
        for supplied, cite in ((False, True), (True, False)):
            with self.subTest(supplied=supplied, cite=cite):
                f, host, _ = self.stage(supplied=supplied, cite=cite)
                before, ledger = f.project.db.read_bytes(), host.state_file.read_bytes()
                with self.assertRaises(ResearchError):
                    host.adopt_supplied_quality_plan(request_id="strict-host", registration_request_id="reg")
                self.assertEqual(f.project.db.read_bytes(), before); self.assertEqual(host.state_file.read_bytes(), ledger)

    def test_old_and_new_entry_do_not_adopt_each_others_intent(self):
        for strict_first in (True, False):
            with self.subTest(strict_first=strict_first):
                f, host, _ = self.stage(); first = host.adopt_supplied_quality_plan if strict_first else host.adopt_quality_plan
                other = host.adopt_quality_plan if strict_first else host.adopt_supplied_quality_plan
                first(request_id="strict-host", registration_request_id="reg")
                before, ledger = f.project.db.read_bytes(), host.state_file.read_bytes()
                with self.assertRaises(ResearchError) as caught: other(request_id="strict-host", registration_request_id="reg")
                self.assertEqual(caught.exception.code, "OPERATION_INCOMPLETE")
                self.assertEqual(f.project.db.read_bytes(), before); self.assertEqual(host.state_file.read_bytes(), ledger)

    def test_before_project_commit_stops_without_retry(self):
        f, host, _ = self.stage()
        with patch.object(ResearchProject,"save_plan",side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt): host.adopt_supplied_quality_plan(request_id="strict-host", registration_request_id="reg")
        before, ledger = f.project.db.read_bytes(), host.state_file.read_bytes()
        with patch.object(ResearchProject,"save_plan",side_effect=AssertionError("retry")):
            with self.assertRaises(ResearchError) as caught: host.adopt_supplied_quality_plan(request_id="strict-host", registration_request_id="reg")
        self.assertEqual(caught.exception.code, "OPERATION_INCOMPLETE")
        self.assertEqual(f.project.db.read_bytes(), before); self.assertEqual(host.state_file.read_bytes(), ledger)

    def test_after_project_commit_only_replays_original_claim(self):
        f, host, _ = self.stage(); save = host._save
        def interrupt(state):
            if state["requests"]["strict-host"]["status"] == "applied": raise KeyboardInterrupt
            return save(state)
        with patch.object(host,"_save",side_effect=interrupt):
            with self.assertRaises(KeyboardInterrupt): host.adopt_supplied_quality_plan(request_id="strict-host", registration_request_id="reg")
        before, budget = f.project.db.read_bytes(), copy.deepcopy(f.project.status()["budget"])
        with patch.object(ResearchProject,"step",side_effect=AssertionError("step")):
            result = HostModelSelection(f.project.root).adopt_supplied_quality_plan(request_id="strict-host", registration_request_id="reg")
        self.assertEqual(result["status"], "applied"); self.assertEqual(f.project.db.read_bytes(), before)
        self.assertEqual(f.project.status()["budget"], budget)

    def test_original_sql_drift_rejects_without_adoption(self):
        f, host, _ = self.stage(); action = f.project.status()["actions"][0]
        with sqlite3.connect(f.project.db) as con:
            con.execute("update actions set fingerprint=? where request_id=?", ("f"*64, action["request_id"]))
        before, ledger = f.project.db.read_bytes(), host.state_file.read_bytes()
        with self.assertRaises(ResearchError): host.adopt_supplied_quality_plan(request_id="strict-host", registration_request_id="reg")
        self.assertEqual(f.project.db.read_bytes(), before); self.assertEqual(host.state_file.read_bytes(), ledger)


    def test_forged_sealed_selector_or_material_cannot_match_reference(self):
        f, host, _ = self.stage()
        record = host.status(request_id="strict-host")
        ref = f.project.prepare_tabular_quality_plan_ref(registration_request_id="reg")
        state = f.project.status()
        for kind in ("selector", "different_registration_same_action", "conditions", "feedback"):
            with self.subTest(kind=kind):
                altered = copy.deepcopy(record)
                material = altered["context"]["supplied_materials"][0]
                if kind == "selector": altered["prepare_specification"]["saved_materials"][0]["registration_sha256"] = "f"*64
                elif kind == "different_registration_same_action": material["registration_request_id"] = "forged-reg"
                elif kind == "conditions": material["conditions"]["conditions"][0]["value"] = 17
                else: material["feedback"]["outcome"] = "condition_not_met"
                with self.assertRaises(ResearchError): host._check_supplied_quality(altered, ref, state)

    def test_sql_change_after_host_writer_check_rolls_back_project(self):
        from autoresearch import tabular_quality_plan
        f, host, _ = self.stage(); action = f.project.status()["actions"][0]
        original = tabular_quality_plan.check_reference; calls = []
        def drift(*args, **kwargs):
            result = original(*args, **kwargs); calls.append(1)
            if len(calls) == 2:
                with sqlite3.connect(f.project.db) as con:
                    con.execute("update actions set fingerprint=? where request_id=?", ("f"*64, action["request_id"]))
            return result
        budget = copy.deepcopy(f.project.status()["budget"])
        with patch.object(tabular_quality_plan, "check_reference", side_effect=drift):
            with self.assertRaises(ResearchError): host.adopt_supplied_quality_plan(request_id="strict-host", registration_request_id="reg")
        self.assertFalse(any(p["request_id"] == "strict-host" for p in f.project.status()["plan_revisions"]))
        self.assertEqual(f.project.status()["budget"], budget)
        self.assertEqual(len(calls), 2)

    def test_terminal_replay_after_later_plan_authenticates_original(self):
        f, host, _ = self.stage()
        result = host.adopt_supplied_quality_plan(request_id="strict-host", registration_request_id="reg")
        later = {"question":"Later", "basis":"Synthetic", "steps":"Wait", "expected_feedback":"Unknown"}
        f.project.save_plan(request_id="later", expected_state_version=f.project.status()["state_version"], plan=later, reason="Synthetic")
        before, budget = f.project.db.read_bytes(), copy.deepcopy(f.project.status()["budget"])
        with patch.object(ResearchProject,"step",side_effect=AssertionError("step")):
            replay = host.adopt_supplied_quality_plan(request_id="strict-host", registration_request_id="reg")
        self.assertEqual(replay, result); self.assertEqual(f.project.db.read_bytes(), before)
        self.assertEqual(f.project.status()["budget"], budget)

    def test_response_prompt_and_material_file_drift_stop_adoption(self):
        for kind in ("response", "prompt", "artifact", "source"):
            with self.subTest(kind=kind):
                f, host, _ = self.stage(); record = host.status(request_id="strict-host")
                action = f.project.status()["actions"][0]
                path = (host.directory / record["response_file"] if kind == "response" else
                        host.directory / record["directory"] / "prompt.json" if kind == "prompt" else
                        f.project.root / action["artifact"] if kind == "artifact" else f.project.root / "source.json")
                path.write_bytes(path.read_bytes() + b" ")
                before, ledger = f.project.db.read_bytes(), host.state_file.read_bytes()
                with self.assertRaises(ResearchError): host.adopt_supplied_quality_plan(request_id="strict-host", registration_request_id="reg")
                self.assertEqual(f.project.db.read_bytes(), before); self.assertEqual(host.state_file.read_bytes(), ledger)

    def test_controller_unknown_does_not_create_adoption(self):
        f = fixture.QualityFeedbackTests(methodName="runTest"); f.setUp(); self.addCleanup(f.doCleanups)
        reg = f.register(reg=f.valid); host = HostModelSelection(f.project.root)
        selector = {"kind":"tabular_quality_feedback", "registration_request_id":"reg", "registration_sha256":reg["registration_sha256"]}
        host.prepare(request_id="strict-host", provider="delegated", purpose="plan",
                     expected_state_version=f.project.status()["state_version"], decision_limit=1,
                     cli_budget_usd=0.1, reason="Synthetic", saved_materials=[selector])
        args = {"plan":{"question":"Synthetic", "basis":"Unknown", "steps":"Wait", "expected_feedback":"Unknown"},
                "reason":"Synthetic", "expected_improvement":"Review", "feedback_action_ids":[]}
        path = f.root / "unknown-response.json"; path.write_text(canonical(args), encoding="utf-8")
        host.import_response(request_id="strict-host", response_file=path); host.consume(request_id="strict-host")
        before, ledger = f.project.db.read_bytes(), host.state_file.read_bytes()
        with self.assertRaises(ResearchError): host.adopt_supplied_quality_plan(request_id="strict-host", registration_request_id="reg")
        self.assertEqual(f.project.db.read_bytes(), before); self.assertEqual(host.state_file.read_bytes(), ledger)

    def test_missing_claim_prevents_replay(self):
        f, host, _ = self.stage(); host.adopt_supplied_quality_plan(request_id="strict-host", registration_request_id="reg")
        with sqlite3.connect(f.project.db) as con:
            con.execute("delete from quality_manager_claims where kind='plan' and request_id='strict-host'")
        before, ledger = f.project.db.read_bytes(), host.state_file.read_bytes()
        with self.assertRaises(ResearchError): host.adopt_supplied_quality_plan(request_id="strict-host", registration_request_id="reg")
        self.assertEqual(f.project.db.read_bytes(), before); self.assertEqual(host.state_file.read_bytes(), ledger)


if __name__ == "__main__": unittest.main()
