"""Synthetic Host proposal adoption; no external model or real research."""
import copy
import json
import multiprocessing
from pathlib import Path
import sqlite3
import unittest
from unittest.mock import patch

import test_tabular_quality_feedback as fixture
from autoresearch.contracts import ResearchError, canonical, fingerprint
from autoresearch.host_model_selection import HostModelSelection
from autoresearch.project_controller import ProjectController
from autoresearch.research_project import ResearchProject


def adoption_worker(root, entered, release, results, stall):
    save = ResearchProject.save_plan
    def gate(project, **kwargs):
        if stall and kwargs.get("_host_quality_intent_sha256"):
            entered.set()
            if not release.wait(15): raise RuntimeError("synthetic fence timed out")
        return save(project, **kwargs)
    try:
        with patch.object(ResearchProject, "save_plan", new=gate):
            result = HostModelSelection(root).adopt_quality_plan(request_id="host-plan", registration_request_id="reg")
        results.put(("ok", result["status"]))
    except Exception as exc:
        results.put(("error", getattr(exc, "code", type(exc).__name__)))


class HostQualityAdoptionTests(unittest.TestCase):
    def stage(self, met=True, cite=True, large=False):
        f = fixture.QualityFeedbackTests(methodName="runTest")
        f.setUp(); self.addCleanup(f.doCleanups)
        f.register(reg=f.valid if met else fixture.rules(fixture.condition("rows", "gt", 4)))
        f.execute()
        if large:
            for index in range(5):
                f.project.record_feedback(request_id="long-note-" + str(index),
                    expected_state_version=f.project.status()["state_version"], author="Synthetic",
                    comment='\n"\\' * 1600, next_step="Review", action_id=None)
        if not cite:
            context = f.controller.selection_context()
            candidate = next(c for c in context["candidates"] if c["method_id"] == "data.numeric-association")
            proposal = {"schema_version":"project-selection-proposal-v1", "context_sha256":context["context_sha256"],
                        "provider":{"kind":"human", "label":"synthetic"},
                        "choice":{"kind":"execute", "candidate_id":candidate["id"]},
                        "rationale":"Synthetic second action", "evidence_citation_ids":[]}
            f.controller.advance_selection(request_id="different-action", proposal=proposal,
                                           expected_state_version=context["state_version"])
        host = HostModelSelection(f.project.root)
        record = host.prepare(request_id="host-plan", provider="delegated", purpose="plan",
                              expected_state_version=f.project.status()["state_version"], decision_limit=2,
                              cli_budget_usd=0.1, reason="Synthetic bounded fixture")
        action = f.project.status()["actions"][0 if cite else -1]["id"]
        args = {"plan": {"question": "Synthetic new question", "basis": "Saved quality observation",
                         "steps": "Consider the association", "expected_feedback": "Keep uncertainty"},
                "reason": "Synthetic feedback revision", "expected_improvement": "Inspect association",
                "feedback_action_ids": [action]}
        response = f.root / "host-response.json"; response.write_text(canonical(args), encoding="utf-8")
        host.import_response(request_id="host-plan", response_file=response)
        proposal = host.consume(request_id="host-plan")
        self.assertEqual(proposal["status"], "proposed")
        return f, host, proposal, args

    def test_adopts_original_plan_and_policy_uses_reference(self):
        f, host, proposal, args = self.stage()
        before = f.project.status()
        with patch.object(ResearchProject, "step", side_effect=AssertionError("adoption dispatched")), \
             patch("autoresearch.host_model_selection.run_claude_selection", side_effect=AssertionError("model invoked")):
            result = host.adopt_quality_plan(request_id="host-plan", registration_request_id="reg")
            repeated = host.adopt_quality_plan(request_id="host-plan", registration_request_id="reg")
        plan = result["outcome"]["research_plan"]
        self.assertEqual({key: plan[key] for key in args["plan"]}, args["plan"])
        self.assertEqual(plan["reason"], args["reason"])
        self.assertEqual(result, repeated)
        self.assertEqual(f.project.status()["budget"], before["budget"])
        body = {"request_id":"follow", "registration_request_id":"reg", "plan_request_id":"host-plan",
                "plan_sha256":fingerprint(plan), "expected_state_version":f.project.status()["state_version"]}
        actual = f.controller.advance_tabular_quality_feedback_v2(**body)
        self.assertEqual(actual["status"], "completed")
        self.assertEqual(f.project.status()["budget"]["local_tool_calls_used"], 2)

    def test_not_met_adopts_but_policy_waits(self):
        f, host, _, _ = self.stage(met=False)
        plan = host.adopt_quality_plan(request_id="host-plan", registration_request_id="reg")["outcome"]["research_plan"]
        with patch.object(ResearchProject, "step", side_effect=AssertionError("not-met dispatch")):
            result = f.controller.advance_tabular_quality_feedback_v2(request_id="follow", registration_request_id="reg",
                plan_request_id="host-plan", plan_sha256=fingerprint(plan), expected_state_version=f.project.status()["state_version"])
        self.assertEqual(result["status"], "waiting")

    def test_before_core_interruption_stops_without_retry(self):
        f, host, _, _ = self.stage()
        with patch.object(ResearchProject, "save_plan", side_effect=KeyboardInterrupt("before core")):
            with self.assertRaises(KeyboardInterrupt): host.adopt_quality_plan(request_id="host-plan", registration_request_id="reg")
        before = f.project.db.read_bytes()
        host_before = host.state_file.read_bytes()
        with self.assertRaises(ResearchError) as rejected:
            host.reject_plan(request_id="host-plan", reason="Do not replace the pending original")
        self.assertEqual(rejected.exception.code, "OPERATION_INCOMPLETE")
        self.assertEqual(host_before, host.state_file.read_bytes())
        with self.assertRaises(ResearchError) as new_request:
            host.prepare(request_id="other", provider="delegated", purpose="plan",
                         expected_state_version=f.project.status()["state_version"], decision_limit=2,
                         cli_budget_usd=0.1, reason="Synthetic bounded fixture")
        self.assertEqual(new_request.exception.code, "OPERATION_INCOMPLETE")
        self.assertEqual(host_before, host.state_file.read_bytes())
        with patch.object(ResearchProject, "save_plan", side_effect=AssertionError("retry core")):
            with self.assertRaises(ResearchError) as caught: host.adopt_quality_plan(request_id="host-plan", registration_request_id="reg")
        self.assertEqual(caught.exception.code, "OPERATION_INCOMPLETE")
        self.assertEqual(before, f.project.db.read_bytes())

    def test_after_core_interruption_recovers_claim_without_dispatch(self):
        f, host, _, _ = self.stage()
        save = host._save
        def interrupt(state):
            if state["requests"]["host-plan"]["status"] == "applied": raise KeyboardInterrupt("after core")
            return save(state)
        with patch.object(host, "_save", side_effect=interrupt):
            with self.assertRaises(KeyboardInterrupt): host.adopt_quality_plan(request_id="host-plan", registration_request_id="reg")
        before = f.project.db.read_bytes()
        with patch.object(ResearchProject, "step", side_effect=AssertionError("redispatch")):
            result = HostModelSelection(f.project.root).adopt_quality_plan(request_id="host-plan", registration_request_id="reg")
        self.assertTrue(result["outcome"]["replayed"])
        self.assertEqual(before, f.project.db.read_bytes())

    def test_missing_claim_stops_recovery_and_old_entry(self):
        f, host, _, _ = self.stage()
        save = host._save
        def interrupt(state):
            if state["requests"]["host-plan"]["status"] == "applied": raise KeyboardInterrupt()
            return save(state)
        with patch.object(host, "_save", side_effect=interrupt):
            with self.assertRaises(KeyboardInterrupt): host.adopt_quality_plan(request_id="host-plan", registration_request_id="reg")
        with sqlite3.connect(f.project.db) as con: con.execute("delete from quality_manager_claims where kind='plan' and request_id='host-plan'")
        for fn, kwargs in ((host.adopt_quality_plan, {"registration_request_id":"reg"}), (host.adopt_plan, {})):
            with self.assertRaises(ResearchError) as caught: fn(request_id="host-plan", **kwargs)
            self.assertEqual(caught.exception.code, "OPERATION_INCOMPLETE")

    def test_joint_prompt_and_state_tampering_cannot_become_adoption(self):
        f, host, _, _ = self.stage()
        state = json.loads(host.state_file.read_text())
        record = state["requests"]["host-plan"]
        record["prompt"]["system"] = "Synthetic forged instructions"
        (host.directory / record["directory"] / "prompt.json").write_text(canonical(record["prompt"]))
        host.state_file.write_text(canonical(state))
        before = f.project.db.read_bytes()
        with self.assertRaises(ResearchError) as caught:
            host.adopt_quality_plan(request_id="host-plan", registration_request_id="reg")
        self.assertEqual(caught.exception.code, "EVIDENCE_CHANGED")
        self.assertEqual(before, f.project.db.read_bytes())

    def test_core_preemption_never_adopts_another_callers_plan(self):
        for different in (False, True):
            with self.subTest(different=different):
                f, host, _, _ = self.stage()
                save = ResearchProject.save_plan
                def preempt(project, **kwargs):
                    if kwargs.get("_host_quality_intent_sha256"):
                        other = {k:v for k,v in kwargs.items() if not k.startswith("_")}
                        if different:
                            other["plan"] = {**other["plan"], "question": "A different plan"}
                        save(project, **other)
                    return save(project, **kwargs)
                with patch.object(ResearchProject, "save_plan", new=preempt):
                    with self.assertRaises(ResearchError) as caught:
                        host.adopt_quality_plan(request_id="host-plan", registration_request_id="reg")
                self.assertIn(caught.exception.code, ("OPERATION_INCOMPLETE", "IDEMPOTENCY_CONFLICT"))
                before = f.project.db.read_bytes()
                with self.assertRaises(ResearchError) as again:
                    host.adopt_quality_plan(request_id="host-plan", registration_request_id="reg")
                self.assertEqual(again.exception.code, "OPERATION_INCOMPLETE")
                self.assertEqual(before, f.project.db.read_bytes())

    def test_quality_sql_drift_during_host_verification_rolls_back(self):
        f, host, _, _ = self.stage()
        import autoresearch.host_model_selection as module
        check = module._check_quality_adoption_in_project
        def drift(project, *args):
            check(project, *args)
            action = f.project.status()["actions"][0]
            with sqlite3.connect(project.db) as con:
                con.execute("update actions set fingerprint=? where request_id=?", ("f" * 64, action["request_id"]))
        with patch.object(module, "_check_quality_adoption_in_project", side_effect=drift):
            with self.assertRaises(ResearchError):
                host.adopt_quality_plan(request_id="host-plan", registration_request_id="reg")
        self.assertFalse(any(p["request_id"] == "host-plan" for p in f.project.status()["plan_revisions"]))

    def test_host_source_drift_after_last_quality_read_stops_before_save(self):
        from autoresearch import tabular_quality_plan, host_selection_protocol
        f, host, _, _ = self.stage()
        original = tabular_quality_plan.check_reference
        read = Path.read_bytes
        target = Path(host_selection_protocol.__file__).resolve()
        calls = []
        def check(*args, **kwargs):
            result = original(*args, **kwargs)
            calls.append(1)
            return result
        def drift(path):
            raw = read(path)
            return raw + b"# synthetic drift" if len(calls) >= 2 and path.resolve() == target else raw
        before = f.project.db.read_bytes(); budget = f.project.status()["budget"]
        with patch.object(tabular_quality_plan, "check_reference", side_effect=check), patch.object(Path, "read_bytes", drift):
            with self.assertRaises(ResearchError): host.adopt_quality_plan(request_id="host-plan", registration_request_id="reg")
        self.assertEqual(len(calls), 2)
        self.assertEqual(before, f.project.db.read_bytes())
        self.assertEqual(budget, f.project.status()["budget"])

    def test_proposal_must_reference_the_supplied_quality_action(self):
        f, host, _, _ = self.stage(cite=False)
        before = f.project.db.read_bytes(); before_host = host.state_file.read_bytes()
        with self.assertRaises(ResearchError) as caught:
            host.adopt_quality_plan(request_id="host-plan", registration_request_id="reg")
        self.assertEqual(caught.exception.code, "INVALID_PLAN_PROPOSAL")
        self.assertEqual(before, f.project.db.read_bytes())
        self.assertEqual(before_host, host.state_file.read_bytes())

    def test_two_processes_same_original_id_accept_once(self):
        f, _, _, _ = self.stage()
        ctx = multiprocessing.get_context("fork")
        entered, release, results = ctx.Event(), ctx.Event(), ctx.Queue()
        first = ctx.Process(target=adoption_worker, args=(f.project.root, entered, release, results, True))
        second = ctx.Process(target=adoption_worker, args=(f.project.root, entered, release, results, False))
        first.start()
        try:
            self.assertTrue(entered.wait(15))
            second.start(); second.join(15)
            self.assertFalse(second.is_alive())
            self.assertEqual(results.get(timeout=5), ("error", "PROJECT_BUSY"))
        finally:
            release.set(); first.join(15)
            if first.is_alive(): first.terminate(); first.join(5)
            if second.is_alive(): second.terminate(); second.join(5)
        self.assertEqual(first.exitcode, 0)
        self.assertEqual(results.get(timeout=5), ("ok", "applied"))
        self.assertEqual(len([p for p in f.project.status()["plan_revisions"] if p["request_id"] == "host-plan"]), 1)

    def test_response_and_source_drift_do_not_save_plan(self):
        for kind in ("response", "source", "artifact", "code"):
            with self.subTest(kind=kind):
                f, host, proposal, _ = self.stage()
                if kind == "response": path = host.directory / proposal["response_file"]
                elif kind == "source": path = f.project.root / "source.json"
                elif kind == "artifact": path = f.project.root / f.project.status()["actions"][0]["artifact"]
                else: path = Path(__import__("autoresearch.plan_readiness", fromlist=["__file__"]).__file__)
                before = f.project.db.read_bytes()
                if kind == "code":
                    read = Path.read_bytes
                    def drift(p):
                        raw = read(p)
                        return raw + b"# synthetic drift" if p.resolve() == path.resolve() else raw
                    context = patch.object(Path, "read_bytes", drift)
                else:
                    path.write_bytes(path.read_bytes() + b" ")
                    context = patch.object(ProjectController, "_dispatch", side_effect=AssertionError("dispatch"))
                with context:
                    with self.assertRaises(ResearchError):
                        host.adopt_quality_plan(request_id="host-plan", registration_request_id="reg")
                self.assertEqual(before, f.project.db.read_bytes())

    def test_terminal_replay_detects_receipt_or_claim_drift(self):
        for kind in ("receipt", "claim"):
            with self.subTest(kind=kind):
                f, host, _, _ = self.stage()
                host.adopt_quality_plan(request_id="host-plan", registration_request_id="reg")
                if kind == "receipt":
                    state = json.loads(host.state_file.read_text())
                    state["requests"]["host-plan"]["outcome"]["state_version"] += 1
                    host.state_file.write_text(canonical(state))
                else:
                    with sqlite3.connect(f.project.db) as con:
                        con.execute("update quality_manager_claims set core_sha256=? where kind='plan' and request_id='host-plan'", ("0"*64,))
                before = f.project.db.read_bytes()
                with self.assertRaises(ResearchError): host.adopt_quality_plan(request_id="host-plan", registration_request_id="reg")
                self.assertEqual(before, f.project.db.read_bytes())

    def test_large_escaped_prompt_with_valid_context_adopts(self):
        from autoresearch import host_selection_protocol
        f, host, proposal, _ = self.stage(large=True)
        context_size = len(canonical(proposal["context"]).encode("utf-8"))
        prompt_size = len(canonical(proposal["prompt"]).encode("utf-8"))
        self.assertGreater(context_size, 60000)
        self.assertLessEqual(context_size, host_selection_protocol.MAX_CONTEXT_BYTES)
        self.assertGreater(prompt_size, host_selection_protocol.MAX_CONTEXT_BYTES)
        adopted = host.adopt_quality_plan(request_id="host-plan", registration_request_id="reg")
        self.assertEqual(adopted["status"], "applied")
        self.assertEqual(f.project.status()["budget"]["local_tool_calls_used"], 1)

    def test_oversized_prompt_file_is_rejected_before_intent(self):
        from autoresearch.host_model_selection import MAX_STATE_BYTES
        f, host, proposal, _ = self.stage()
        (host.directory / proposal["directory"] / "prompt.json").write_bytes(b"x" * (MAX_STATE_BYTES + 1))
        before, host_before = f.project.db.read_bytes(), host.state_file.read_bytes()
        with self.assertRaises(ResearchError): host.adopt_quality_plan(request_id="host-plan", registration_request_id="reg")
        self.assertEqual(before, f.project.db.read_bytes())
        self.assertEqual(host_before, host.state_file.read_bytes())

    def test_oversized_context_is_rejected_before_host_preparation(self):
        f = fixture.QualityFeedbackTests(methodName="runTest")
        f.setUp(); self.addCleanup(f.doCleanups)
        f.register(); f.execute()
        for index in range(6):
            f.project.record_feedback(request_id="oversize-note-" + str(index),
                expected_state_version=f.project.status()["state_version"], author="Synthetic",
                comment='\n"\\' * 1600, next_step="Review", action_id=None)
        host = HostModelSelection(f.project.root); before = f.project.db.read_bytes()
        with self.assertRaises(ResearchError):
            host.prepare(request_id="host-plan", provider="delegated", purpose="plan",
                         expected_state_version=f.project.status()["state_version"], decision_limit=2,
                         cli_budget_usd=0.1, reason="Synthetic bounded fixture")
        self.assertFalse(host.state_file.exists())
        self.assertEqual(before, f.project.db.read_bytes())
