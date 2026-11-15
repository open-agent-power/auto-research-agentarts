"""Synthetic manager/Host/Project quality adoption; no real model or data."""
import json
import multiprocessing
import sqlite3
import unittest
from unittest.mock import patch

import test_quality_plan_workbench as fixture
from autoresearch.contracts import ResearchError, canonical, fingerprint
from autoresearch.host_model_selection import HostModelSelection
from autoresearch.local_workbench import LocalWorkbench
from autoresearch.project_controller import ProjectController
from autoresearch.research_project import ResearchProject


def worker(root, body, entered, release, results, stall):
    original = HostModelSelection.adopt_quality_plan
    def gate(host, **kwargs):
        if stall and kwargs.get("_manager_binding"):
            entered.set()
            if not release.wait(15): raise RuntimeError("fence timeout")
        return original(host, **kwargs)
    try:
        with patch.object(HostModelSelection, "adopt_quality_plan", new=gate):
            result = LocalWorkbench(root).model_quality_plan_adopt(body)
        results.put(("ok", result["status"]))
    except Exception as error:
        results.put(("error", getattr(error, "code", type(error).__name__)))


def direct_host_worker(project_root, results):
    try:
        result = HostModelSelection(project_root).adopt_quality_plan(request_id="host-plan", registration_request_id="reg")
        results.put(("direct", result["status"]))
    except Exception as error:
        results.put(("direct-error", getattr(error, "code", type(error).__name__)))


class HostQualityWorkbenchTests(unittest.TestCase):
    serve = fixture.QualityPlanWorkbenchTests.serve
    request = fixture.QualityPlanWorkbenchTests.request
    session = fixture.QualityPlanWorkbenchTests.session

    def stage(self):
        helper = fixture.QualityPlanWorkbenchTests(methodName="runTest")
        f, manager, _ = helper.stage(); self.addCleanup(helper.doCleanups)
        host = HostModelSelection(f.project.root)
        record = host.prepare(request_id="host-plan", provider="delegated", purpose="plan",
                              expected_state_version=f.project.status()["state_version"], decision_limit=2,
                              cli_budget_usd=0.1, reason="Synthetic bounded fixture")
        action = f.project.status()["actions"][0]["id"]
        args = {"plan":{"question":"Synthetic question", "basis":"Quality observation", "steps":"Inspect association",
                        "expected_feedback":"Retain uncertainty"}, "reason":"Synthetic", "expected_improvement":"Review",
                "feedback_action_ids":[action]}
        path = f.root / "delegated.json"; path.write_text(canonical(args))
        host.import_response(request_id="host-plan", response_file=path)
        proposed = host.consume(request_id="host-plan")
        self.assertEqual(proposed["status"], "proposed")
        body = {"request_id":"manager-adopt", "project_id":f.project.status()["id"],
                "expected_state_version":f.project.status()["state_version"],
                "host_request_id":"host-plan", "registration_request_id":"reg"}
        return f, manager, host, body, args

    def test_opt_in_adopts_and_replays_without_model_or_research(self):
        f, manager, host, body, args = self.stage(); before = f.project.status()
        with patch.object(ResearchProject, "step", side_effect=AssertionError("step")), \
             patch.object(ProjectController, "_dispatch", side_effect=AssertionError("dispatch")), \
             patch("autoresearch.host_model_selection.run_claude_selection", side_effect=AssertionError("model")):
            result = manager.model_quality_plan_adopt(body)
            replay = LocalWorkbench(manager.root).model_quality_plan_adopt(body)
        self.assertEqual(result["status"], "applied"); self.assertTrue(replay["replayed"])
        self.assertEqual(set(result), {"schema_version","command","request_id","project_id","replayed",
                                       "status","host_request_id","plan_version","plan_sha256"})
        current = f.project.status(); plan = current["plan_revisions"][-1]
        self.assertEqual({k:plan[k] for k in args["plan"]}, args["plan"])
        self.assertEqual(plan["request_id"], "host-plan"); self.assertEqual(result["plan_sha256"], fingerprint(plan))
        self.assertEqual(current["budget"], before["budget"])
        self.assertEqual(host.status(request_id="host-plan")["quality_adoption"]["schema_version"], "host-quality-adoption-v2")

    def test_explicit_quality_policy_can_consume_adopted_plan(self):
        f, manager, _, body, _ = self.stage()
        adopted = manager.model_quality_plan_adopt(body)
        policy = {"request_id":"follow", "project_id":body["project_id"], "registration_request_id":"reg",
                  "plan_request_id":body["host_request_id"], "plan_sha256":adopted["plan_sha256"],
                  "expected_state_version":f.project.status()["state_version"]}
        result = manager.advance_tabular_quality_feedback_v2(policy)
        self.assertEqual(result["status"], "completed")
        budget = f.project.status()["budget"]
        self.assertEqual((budget["local_tool_calls_used"], budget["new_model_requests"], budget["new_fits"],
                          budget["evidence_reads_used"]), (2, 0, 0, 0))

    def test_four_interruption_windows(self):
        for phase in ("manager", "host", "project", "receipt"):
            with self.subTest(phase=phase):
                f, manager, host, body, _ = self.stage()
                if phase == "manager":
                    context = patch.object(HostModelSelection, "adopt_quality_plan", side_effect=KeyboardInterrupt("before Host"))
                elif phase == "host":
                    save = ResearchProject.save_plan
                    def cut(project, **kwargs):
                        if kwargs.get("_host_quality_intent_sha256"): raise KeyboardInterrupt("before Project")
                        return save(project, **kwargs)
                    context = patch.object(ResearchProject, "save_plan", new=cut)
                elif phase == "project":
                    save = HostModelSelection._save
                    def cut(journal, state):
                        if state["requests"]["host-plan"]["status"] == "applied": raise KeyboardInterrupt("before Host receipt")
                        return save(journal, state)
                    context = patch.object(HostModelSelection, "_save", new=cut)
                else:
                    save = manager._save
                    def cut(con, request_id, record):
                        if request_id == "manager-adopt" and record["status"] == "completed": raise KeyboardInterrupt("before manager receipt")
                        return save(con, request_id, record)
                    context = patch.object(manager, "_save", side_effect=cut)
                with context, self.assertRaises(KeyboardInterrupt): manager.model_quality_plan_adopt(body)
                project_before = f.project.db.read_bytes(); host_before = host.state_file.read_bytes()
                with patch.object(ProjectController, "_dispatch", side_effect=AssertionError("dispatch")), \
                     patch.object(ResearchProject, "step", side_effect=AssertionError("step")):
                    if phase == "receipt":
                        original = ResearchProject.save_plan
                        def readonly(project, **kwargs):
                            if not kwargs.get("_validate_only"): raise AssertionError("Project write")
                            return original(project, **kwargs)
                        with patch.object(ResearchProject, "save_plan", new=readonly):
                            result = LocalWorkbench(manager.root).model_quality_plan_adopt(body)
                        self.assertTrue(result["replayed"]); self.assertEqual(result["status"], "applied")
                    else:
                        with patch.object(HostModelSelection, "adopt_quality_plan", side_effect=AssertionError("Host retry")):
                            with self.assertRaises(ResearchError) as caught:
                                LocalWorkbench(manager.root).model_quality_plan_adopt(body)
                        self.assertEqual(caught.exception.code, "OPERATION_INCOMPLETE")
                        self.assertEqual(host.state_file.read_bytes(), host_before)
                        with self.assertRaises(ResearchError) as pending:
                            manager.model_quality_plan_adopt({**body, "request_id":"new-manager"})
                        self.assertEqual(pending.exception.code, "OPERATION_INCOMPLETE")
                self.assertEqual(f.project.db.read_bytes(), project_before)
                self.assertEqual(f.project.status()["budget"]["local_tool_calls_used"], 1)

    def test_direct_host_race_never_adopted(self):
        f, manager, host, body, _ = self.stage(); original = HostModelSelection.adopt_quality_plan
        def race(journal, **kwargs):
            if kwargs.get("_manager_binding"):
                original(journal, request_id=kwargs["request_id"], registration_request_id=kwargs["registration_request_id"])
            return original(journal, **kwargs)
        with patch.object(HostModelSelection, "adopt_quality_plan", new=race):
            with self.assertRaises(ResearchError) as caught: manager.model_quality_plan_adopt(body)
        self.assertEqual(caught.exception.code, "OPERATION_INCOMPLETE")
        self.assertEqual(host.status(request_id="host-plan")["quality_adoption"]["schema_version"], "host-quality-adoption-v1")
        before = f.project.db.read_bytes()
        with self.assertRaises(ResearchError) as retry: manager.model_quality_plan_adopt(body)
        self.assertEqual(retry.exception.code, "OPERATION_INCOMPLETE"); self.assertEqual(f.project.db.read_bytes(), before)

    def test_direct_core_race_never_adopted(self):
        for different in (False, True):
            with self.subTest(different=different):
                f, manager, _, body, _ = self.stage(); original = ResearchProject.save_plan
                def race(project, **kwargs):
                    if kwargs.get("_host_quality_intent_sha256"):
                        direct = {k:v for k,v in kwargs.items() if not k.startswith("_")}
                        if different: direct["reason"] = "Different synthetic reason"
                        original(project, **direct)
                    return original(project, **kwargs)
                with patch.object(ResearchProject, "save_plan", new=race):
                    with self.assertRaises(ResearchError) as caught: manager.model_quality_plan_adopt(body)
                self.assertEqual(caught.exception.code, "IDEMPOTENCY_CONFLICT" if different else "OPERATION_INCOMPLETE")
                before = f.project.db.read_bytes()
                with self.assertRaises(ResearchError) as retry: manager.model_quality_plan_adopt(body)
                self.assertEqual(retry.exception.code, "OPERATION_INCOMPLETE"); self.assertEqual(f.project.db.read_bytes(), before)

    def test_invalid_or_cross_caller_ids_do_not_write(self):
        f, manager, host, body, _ = self.stage(); before = (manager.db.read_bytes(), f.project.db.read_bytes(), host.state_file.read_bytes())
        for changed, code in (({**body,"request_id":"host-plan"}, "INVALID_REQUEST"),
                              ({**body,"expected_state_version":True}, "INVALID_REQUEST"),
                              ({**body,"expected_state_version":body["expected_state_version"]+1}, "STALE_STATE")):
            with self.subTest(code=code), self.assertRaises(ResearchError) as caught: manager.model_quality_plan_adopt(changed)
            self.assertEqual(caught.exception.code, code)
            self.assertEqual(before, (manager.db.read_bytes(), f.project.db.read_bytes(), host.state_file.read_bytes()))
        manager.model_quality_plan_adopt(body)
        with self.assertRaises(ResearchError) as direct: host.adopt_quality_plan(request_id="host-plan", registration_request_id="reg")
        self.assertEqual(direct.exception.code, "OPERATION_INCOMPLETE")
        with self.assertRaises(ResearchError) as changed: manager.model_quality_plan_adopt({**body,"registration_request_id":"different"})
        self.assertEqual(changed.exception.code, "IDEMPOTENCY_CONFLICT")

    def test_two_processes_same_manager_id(self):
        f, manager, _, body, _ = self.stage(); ctx = multiprocessing.get_context("fork")
        entered, release, results = ctx.Event(), ctx.Event(), ctx.Queue()
        first = ctx.Process(target=worker, args=(manager.root,body,entered,release,results,True))
        second = ctx.Process(target=worker, args=(manager.root,body,entered,release,results,False))
        first.start()
        try:
            self.assertTrue(entered.wait(15)); second.start(); second.join(15)
            self.assertFalse(second.is_alive()); self.assertEqual(results.get(timeout=5), ("error","PROJECT_BUSY"))
        finally:
            release.set(); first.join(15)
            if first.is_alive(): first.terminate(); first.join(5)
            if second.is_alive(): second.terminate(); second.join(5)
        self.assertEqual(first.exitcode, 0); self.assertEqual(results.get(timeout=5), ("ok","applied"))
        self.assertEqual(len([p for p in f.project.status()["plan_revisions"] if p["request_id"] == "host-plan"]), 1)

    def test_http_boundary_security_redaction_and_old_wire(self):
        f, manager, _, body, _ = self.stage()
        server = self.serve(local_workspace=manager, allow_local_actions=True); headers = self.session(server)
        path = "/api/local-workbench/model-quality-plan-adopt"
        before = (manager.db.read_bytes(), f.project.db.read_bytes())
        for altered in ({**headers,"Origin":"http://evil.invalid"}, {**headers,"X-AutoResearch-CSRF":"bad"},
                        {**headers,"Host":"external.invalid"}, {**headers,"Sec-Fetch-Site":"cross-site"}):
            self.assertEqual(self.request(server,path,"POST",body,altered)[0], 403)
        self.assertEqual(self.request(server,"/api/local-workbench/model-plan-adopt","POST",body,headers)[0], 400)
        self.assertEqual(before, (manager.db.read_bytes(), f.project.db.read_bytes()))
        status, result = self.request(server,path,"POST",body,headers)
        self.assertEqual(status, 200, result); self.assertEqual(result["status"], "applied")
        self.assertNotIn("nonce", canonical(result)); self.assertNotIn("prompt", canonical(result))
        self.assertNotIn("proposal", canonical(result)); self.assertNotIn(str(manager.root), canonical(result))
        self.assertEqual(self.request(server,path,"POST",body,headers)[0], 200)
        readonly = self.serve(local_workspace=LocalWorkbench.open_readonly(manager.root), allow_local_actions=False)
        self.assertEqual(self.request(readonly,path,"POST",body,headers)[0], 405)

    def test_missing_or_altered_manager_host_and_core_ownership_stops(self):
        for kind in ("missing_manager", "manager_nonce", "host_binding", "core_claim"):
            with self.subTest(kind=kind):
                f, manager, host, body, _ = self.stage(); manager.model_quality_plan_adopt(body)
                if kind == "missing_manager":
                    with sqlite3.connect(manager.db) as con:
                        con.execute("delete from requests where id=?", (body["request_id"],))
                elif kind == "manager_nonce":
                    with sqlite3.connect(manager.db) as con:
                        saved = json.loads(con.execute("select record from requests where id=?", (body["request_id"],)).fetchone()[0])
                        saved["intent"]["nonce"] = "0" * 64
                        con.execute("update requests set record=? where id=?", (canonical(saved), body["request_id"]))
                elif kind == "host_binding":
                    state = json.loads(host.state_file.read_text())
                    state["requests"]["host-plan"]["quality_adoption"]["manager_binding"]["intent_sha256"] = "0" * 64
                    host.state_file.write_text(canonical(state))
                else:
                    with sqlite3.connect(f.project.db) as con:
                        con.execute("update quality_manager_claims set core_sha256=? where kind='plan' and request_id='host-plan'", ("0"*64,))
                before = (manager.db.read_bytes(), f.project.db.read_bytes(), host.state_file.read_bytes())
                with patch.object(ProjectController,"_dispatch",side_effect=AssertionError("dispatch")), \
                     patch.object(ResearchProject,"step",side_effect=AssertionError("step")):
                    with self.assertRaises(ResearchError): manager.model_quality_plan_adopt(body)
                self.assertEqual(before, (manager.db.read_bytes(), f.project.db.read_bytes(), host.state_file.read_bytes()))

    def test_pending_projection_and_project_switch_are_guarded(self):
        f, manager, _, body, _ = self.stage()
        with patch.object(HostModelSelection,"adopt_quality_plan",side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt): manager.model_quality_plan_adopt(body)
        info = manager.describe()
        item = next(x for x in info["pending_requests"] if x["request_id"] == body["request_id"])
        self.assertEqual(item["command"], "model_quality_plan_adopt")
        self.assertNotIn("nonce", canonical(item)); self.assertNotIn("body", item)
        with self.assertRaises(ResearchError) as caught:
            manager.select({"request_id":"switch", "project_id":"other-project"})
        self.assertEqual(caught.exception.code, "OPERATION_INCOMPLETE")

    def test_quality_drift_before_manager_acceptance_fails_without_intent(self):
        f, manager, _, body, _ = self.stage()
        artifact = f.project.root / f.project.status()["actions"][0]["artifact"]
        original = HostModelSelection._preflight_manager_quality_adoption; calls = []
        def drift(host, *args):
            result = original(host, *args); calls.append(1)
            if len(calls) == 1: artifact.write_bytes(artifact.read_bytes() + b" ")
            return result
        before = (manager.db.read_bytes(), f.project.db.read_bytes())
        with patch.object(HostModelSelection, "_preflight_manager_quality_adoption", new=drift):
            with self.assertRaises(ResearchError): manager.model_quality_plan_adopt(body)
        self.assertEqual(before, (manager.db.read_bytes(), f.project.db.read_bytes()))
        self.assertFalse(any(x["request_id"] == body["request_id"] for x in manager.describe()["pending_requests"]))

    def test_direct_host_process_wins_after_manager_intent_without_being_adopted(self):
        f, manager, host, body, _ = self.stage(); ctx = multiprocessing.get_context("fork")
        entered, release, results = ctx.Event(), ctx.Event(), ctx.Queue()
        first = ctx.Process(target=worker, args=(manager.root,body,entered,release,results,True))
        direct = ctx.Process(target=direct_host_worker, args=(f.project.root,results))
        first.start()
        try:
            self.assertTrue(entered.wait(15)); direct.start(); direct.join(15)
            self.assertFalse(direct.is_alive()); self.assertEqual(results.get(timeout=5), ("direct", "applied"))
        finally:
            release.set(); first.join(15)
            if first.is_alive(): first.terminate(); first.join(5)
            if direct.is_alive(): direct.terminate(); direct.join(5)
        self.assertEqual(first.exitcode, 0)
        self.assertEqual(results.get(timeout=5), ("error", "OPERATION_INCOMPLETE"))
        self.assertEqual(host.status(request_id="host-plan")["quality_adoption"]["schema_version"], "host-quality-adoption-v1")
        self.assertEqual(f.project.status()["budget"]["local_tool_calls_used"], 1)
