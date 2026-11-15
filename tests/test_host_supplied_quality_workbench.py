"""Three-layer strict adoption; isolated synthetic projects and delegated responses."""
import copy
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


def process_worker(root, body, entered, release, results, stall):
    original = HostModelSelection._adopt_manager_supplied_quality_plan
    def gate(host, **kwargs):
        if stall:
            entered.set()
            if not release.wait(15): raise RuntimeError("fence timeout")
        return original(host, **kwargs)
    try:
        with patch.object(HostModelSelection, "_adopt_manager_supplied_quality_plan", new=gate):
            result = LocalWorkbench(root).model_supplied_quality_plan_adopt(body)
        results.put(("ok", result["status"]))
    except Exception as error:
        results.put(("error", getattr(error, "code", type(error).__name__)))


class SuppliedQualityWorkbenchTests(unittest.TestCase):
    serve = fixture.QualityPlanWorkbenchTests.serve
    request = fixture.QualityPlanWorkbenchTests.request
    session = fixture.QualityPlanWorkbenchTests.session

    def stage(self, *, supplied=True):
        helper = fixture.QualityPlanWorkbenchTests(methodName="runTest")
        f, manager, _ = helper.stage(); self.addCleanup(helper.doCleanups)
        reg = f.project.status()["tabular_quality_registrations"][0]
        selector = {"kind":"tabular_quality_feedback", "registration_request_id":"reg", "registration_sha256":reg["registration_sha256"]}
        host = HostModelSelection(f.project.root)
        host.prepare(request_id="host-plan", provider="delegated", purpose="plan",
                     expected_state_version=f.project.status()["state_version"], decision_limit=1,
                     cli_budget_usd=0.1, reason="Synthetic", saved_materials=[selector] if supplied else None)
        args = {"plan":{"question":"Synthetic", "basis":"Original material", "steps":"Consider results",
                        "expected_feedback":"Preserve uncertainty"}, "reason":"Synthetic revision",
                "expected_improvement":"Review", "feedback_action_ids":[f.project.status()["actions"][0]["id"]]}
        path = f.root / "strict-response.json"; path.write_text(canonical(args), encoding="utf-8")
        host.import_response(request_id="host-plan", response_file=path); host.consume(request_id="host-plan")
        body = {"request_id":"manager-adopt", "project_id":f.project.status()["id"],
                "expected_state_version":f.project.status()["state_version"], "host_request_id":"host-plan",
                "registration_request_id":"reg"}
        return f, manager, host, body, args

    def test_strict_adopts_and_replays_with_bound_three_layers(self):
        f, manager, host, body, args = self.stage(); budget = copy.deepcopy(f.project.status()["budget"])
        with patch.object(ResearchProject,"step",side_effect=AssertionError("step")), \
             patch.object(ProjectController,"_dispatch",side_effect=AssertionError("dispatch")), \
             patch("autoresearch.host_model_selection.run_claude_selection",side_effect=AssertionError("model")):
            result = manager.model_supplied_quality_plan_adopt(body)
            repeated = LocalWorkbench(manager.root).model_supplied_quality_plan_adopt(body)
        self.assertTrue(repeated["replayed"]); self.assertEqual(result["status"], "applied")
        self.assertEqual(set(result), {"schema_version","command","request_id","project_id","replayed","status","host_request_id","plan_version","plan_sha256"})
        record = host.status(request_id="host-plan"); self.assertEqual(record["quality_adoption"]["schema_version"], "host-quality-adoption-v4")
        revision = f.project.status()["plan_revisions"][-1]
        self.assertEqual({k:revision[k] for k in args["plan"]}, args["plan"])
        self.assertEqual(result["plan_sha256"], fingerprint(revision)); self.assertEqual(f.project.status()["budget"], budget)

    def test_no_selected_material_leaves_no_manager_intent(self):
        f, manager, _, body, _ = self.stage(supplied=False)
        before = (manager.db.read_bytes(), f.project.db.read_bytes())
        with self.assertRaises(ResearchError): manager.model_supplied_quality_plan_adopt(body)
        self.assertEqual((manager.db.read_bytes(), f.project.db.read_bytes()), before)

    def test_actual_http_security_and_bounded_receipt(self):
        f, manager, _, body, _ = self.stage(); server = self.serve(local_workspace=manager,allow_local_actions=True)
        headers = self.session(server); route = "/api/local-workbench/model-supplied-quality-plan-adopt"
        for h in ({**headers,"Origin":"http://evil.invalid"}, {**headers,"X-AutoResearch-CSRF":"bad"},
                  {**headers,"Host":"external.invalid"}, {**headers,"Sec-Fetch-Site":"cross-site"}):
            self.assertEqual(self.request(server,route,"POST",body,h)[0],403)
        status, result = self.request(server,route,"POST",body,headers); self.assertEqual(status,200,result)
        for text in ("prompt", "response", "nonce", "material", "quality_adoption"):
            self.assertNotIn(text, canonical(result))
        self.assertEqual(self.request(server,route,"POST",body,headers)[0],200)
        readonly = self.serve(local_workspace=LocalWorkbench.open_readonly(manager.root), allow_local_actions=False)
        self.assertEqual(self.request(readonly,route,"POST",body,headers)[0],405)
        self.assertEqual(f.project.status()["budget"]["local_tool_calls_used"],1)


    def test_four_commit_windows_recover_only_terminal_bound_host(self):
        for phase in ("manager", "host", "project", "receipt"):
            with self.subTest(phase=phase):
                f, manager, host, body, _ = self.stage()
                if phase == "manager":
                    context = patch.object(HostModelSelection, "_adopt_manager_supplied_quality_plan", side_effect=KeyboardInterrupt)
                elif phase == "host":
                    save = ResearchProject.save_plan
                    def cut(project, **kwargs):
                        if kwargs.get("_host_quality_intent_sha256"): raise KeyboardInterrupt
                        return save(project, **kwargs)
                    context = patch.object(ResearchProject, "save_plan", new=cut)
                elif phase == "project":
                    save = HostModelSelection._save
                    def cut(journal, state):
                        if state["requests"]["host-plan"]["status"] == "applied": raise KeyboardInterrupt
                        return save(journal, state)
                    context = patch.object(HostModelSelection, "_save", new=cut)
                else:
                    save = manager._save
                    def cut(con, request_id, record):
                        if request_id == "manager-adopt" and record["status"] == "completed": raise KeyboardInterrupt
                        return save(con, request_id, record)
                    context = patch.object(manager, "_save", side_effect=cut)
                with context, self.assertRaises(KeyboardInterrupt): manager.model_supplied_quality_plan_adopt(body)
                project_before, host_before = f.project.db.read_bytes(), host.state_file.read_bytes()
                with patch.object(ProjectController, "_dispatch", side_effect=AssertionError("dispatch")), \
                     patch.object(ResearchProject, "step", side_effect=AssertionError("step")):
                    if phase == "receipt":
                        original = ResearchProject.save_plan
                        def readonly(project, **kwargs):
                            if not kwargs.get("_validate_only"): raise AssertionError("Project write")
                            return original(project, **kwargs)
                        with patch.object(ResearchProject, "save_plan", new=readonly):
                            result = LocalWorkbench(manager.root).model_supplied_quality_plan_adopt(body)
                        self.assertTrue(result["replayed"]); self.assertEqual(result["status"], "applied")
                    else:
                        with patch.object(HostModelSelection, "_adopt_manager_supplied_quality_plan", side_effect=AssertionError("Host retry")):
                            with self.assertRaises(ResearchError) as caught: LocalWorkbench(manager.root).model_supplied_quality_plan_adopt(body)
                        self.assertEqual(caught.exception.code,"OPERATION_INCOMPLETE")
                        self.assertEqual(host.state_file.read_bytes(), host_before)
                        with self.assertRaises(ResearchError) as pending:
                            manager.model_supplied_quality_plan_adopt({**body,"request_id":"other"})
                        self.assertEqual(pending.exception.code,"OPERATION_INCOMPLETE")
                self.assertEqual(f.project.db.read_bytes(),project_before)
                self.assertEqual(f.project.status()["budget"]["local_tool_calls_used"],1)

    def test_direct_host_preemption_and_cross_entry_never_adopted(self):
        for direct in ("old", "strict"):
            with self.subTest(direct=direct):
                f, manager, host, body, _ = self.stage(); original = HostModelSelection._adopt_manager_supplied_quality_plan
                def race(journal, **kwargs):
                    method = journal.adopt_quality_plan if direct == "old" else journal.adopt_supplied_quality_plan
                    method(request_id=kwargs["request_id"], registration_request_id=kwargs["registration_request_id"])
                    return original(journal, **kwargs)
                with patch.object(HostModelSelection, "_adopt_manager_supplied_quality_plan", new=race):
                    with self.assertRaises(ResearchError): manager.model_supplied_quality_plan_adopt(body)
                before = f.project.db.read_bytes()
                with self.assertRaises(ResearchError) as retry: manager.model_supplied_quality_plan_adopt(body)
                self.assertEqual(retry.exception.code,"OPERATION_INCOMPLETE"); self.assertEqual(f.project.db.read_bytes(),before)
        f, manager, _, body, _ = self.stage(); manager.model_supplied_quality_plan_adopt(body)
        with self.assertRaises(ResearchError): manager.model_quality_plan_adopt(body)
        f, manager, _, body, _ = self.stage(); manager.model_quality_plan_adopt(body)
        with self.assertRaises(ResearchError): manager.model_supplied_quality_plan_adopt(body)

    def test_missing_or_changed_three_layer_binding_stops(self):
        for kind in ("manager", "nonce", "host", "claim"):
            with self.subTest(kind=kind):
                f, manager, host, body, _ = self.stage(); manager.model_supplied_quality_plan_adopt(body)
                if kind == "manager":
                    with sqlite3.connect(manager.db) as con: con.execute("delete from requests where id=?",(body["request_id"],))
                elif kind == "nonce":
                    with sqlite3.connect(manager.db) as con:
                        row = con.execute("select record from requests where id=?",(body["request_id"],)).fetchone()
                        saved = json.loads(row[0]); saved["intent"]["nonce"] = "f"*64
                        con.execute("update requests set record=? where id=?",(canonical(saved),body["request_id"]))
                elif kind == "host":
                    saved = json.loads(host.state_file.read_text()); saved["requests"]["host-plan"]["quality_adoption"]["manager_binding"]["intent_sha256"] = "f"*64
                    host.state_file.write_text(canonical(saved))
                else:
                    with sqlite3.connect(f.project.db) as con: con.execute("delete from quality_manager_claims where kind='plan' and request_id='host-plan'")
                before = f.project.db.read_bytes()
                with self.assertRaises(ResearchError): manager.model_supplied_quality_plan_adopt(body)
                self.assertEqual(f.project.db.read_bytes(),before)

    def test_direct_project_same_and_different_body_never_adopted(self):
        for different in (False, True):
            with self.subTest(different=different):
                f, manager, _, body, _ = self.stage(); original = ResearchProject.save_plan
                def race(project, **kwargs):
                    if kwargs.get("_host_quality_intent_sha256"):
                        direct = {k:v for k,v in kwargs.items() if not k.startswith("_")}
                        if different: direct["reason"] = "Different synthetic reason"
                        original(project, **direct)
                    return original(project, **kwargs)
                with patch.object(ResearchProject,"save_plan",new=race):
                    with self.assertRaises(ResearchError): manager.model_supplied_quality_plan_adopt(body)
                before = f.project.db.read_bytes()
                with self.assertRaises(ResearchError) as caught: manager.model_supplied_quality_plan_adopt(body)
                self.assertEqual(caught.exception.code,"OPERATION_INCOMPLETE"); self.assertEqual(f.project.db.read_bytes(),before)

    def test_deleted_manager_intent_never_recreated_with_new_nonce(self):
        f, manager, host, body, _ = self.stage(); manager.model_supplied_quality_plan_adopt(body)
        with sqlite3.connect(manager.db) as con: con.execute("delete from requests where id=?",(body["request_id"],))
        before = (manager.db.read_bytes(),host.state_file.read_bytes(),f.project.db.read_bytes())
        with self.assertRaises(ResearchError): manager.model_supplied_quality_plan_adopt(body)
        self.assertEqual(before,(manager.db.read_bytes(),host.state_file.read_bytes(),f.project.db.read_bytes()))
        with sqlite3.connect(manager.db) as con:
            self.assertIsNone(con.execute("select id from requests where id=?",(body["request_id"],)).fetchone())

    def test_pending_gate_checks_all_records_not_only_display_eight(self):
        f, manager, _, body, _ = self.stage()
        with patch.object(HostModelSelection,"_adopt_manager_supplied_quality_plan",side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt): manager.model_supplied_quality_plan_adopt(body)
        with sqlite3.connect(manager.db) as con:
            for i in range(10):
                record = {"status":"preparing", "intent":{"project_id":"unrelated"}, "result":None}
                con.execute("insert into requests values(?,?,?,?)", ("foreign-"+str(i),"0"*64,"model_supplied_quality_plan_adopt",canonical(record)))
        with manager._connect(readonly=True) as con:
            with self.assertRaises(ResearchError) as caught: manager._no_pending_batch(con,body["project_id"],except_id="new",evidence=True)
        self.assertEqual(caught.exception.code,"OPERATION_INCOMPLETE")

    def test_two_processes_cannot_accept_same_manager_id_twice(self):
        f, manager, _, body, _ = self.stage(); ctx = multiprocessing.get_context("fork")
        entered, release, results = ctx.Event(), ctx.Event(), ctx.Queue()
        first = ctx.Process(target=process_worker,args=(manager.root,body,entered,release,results,True))
        second = ctx.Process(target=process_worker,args=(manager.root,body,entered,release,results,False))
        first.start()
        try:
            self.assertTrue(entered.wait(15)); second.start(); second.join(15)
            self.assertFalse(second.is_alive()); self.assertEqual(results.get(timeout=5),("error","PROJECT_BUSY"))
        finally:
            release.set(); first.join(15)
            if first.is_alive(): first.terminate(); first.join(5)
            if second.is_alive(): second.terminate(); second.join(5)
        self.assertEqual(first.exitcode,0); self.assertEqual(results.get(timeout=5),("ok","applied"))
        self.assertEqual(len([p for p in f.project.status()["plan_revisions"] if p["request_id"] == "host-plan"]),1)

    def test_source_and_prompt_drift_between_preflights_stop_before_intent(self):
        for kind in ("source", "prompt"):
            with self.subTest(kind=kind):
                f, manager, host, body, _ = self.stage(); record = host.status(request_id="host-plan")
                path = f.project.root / "source.json" if kind == "source" else host.directory / record["directory"] / "prompt.json"
                original = HostModelSelection._preflight_manager_supplied_quality_adoption; calls = []
                def drift(journal, *args):
                    result = original(journal, *args); calls.append(1)
                    if len(calls) == 1: path.write_bytes(path.read_bytes()+b" ")
                    return result
                before = manager.db.read_bytes()
                with patch.object(HostModelSelection,"_preflight_manager_supplied_quality_adoption",new=drift):
                    with self.assertRaises(ResearchError): manager.model_supplied_quality_plan_adopt(body)
                self.assertEqual(manager.db.read_bytes(),before)

    def test_preflight_quality_drift_leaves_no_manager_intent(self):
        f, manager, _, body, _ = self.stage(); original = HostModelSelection._preflight_manager_supplied_quality_adoption; calls = []
        def drift(host, *args):
            result = original(host, *args); calls.append(1)
            if len(calls) == 1:
                action = f.project.status()["actions"][0]
                with sqlite3.connect(f.project.db) as con: con.execute("update actions set fingerprint=? where request_id=?", ("f"*64,action["request_id"]))
            return result
        before = manager.db.read_bytes()
        with patch.object(HostModelSelection, "_preflight_manager_supplied_quality_adoption", new=drift):
            with self.assertRaises(ResearchError): manager.model_supplied_quality_plan_adopt(body)
        self.assertEqual(manager.db.read_bytes(), before)


if __name__ == "__main__": unittest.main()
