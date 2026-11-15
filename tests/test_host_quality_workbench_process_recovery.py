"""Four manager/Host/Project SIGKILL fences on isolated synthetic projects.

These process-termination checks do not demonstrate power-loss recovery.
"""
import base64
import hashlib
import json
import os
from pathlib import Path
import selectors
import signal
import sqlite3
import subprocess
import sys
import unittest
from unittest.mock import patch

import test_host_quality_workbench as fixture
from autoresearch.contracts import ResearchError, canonical, fingerprint
from autoresearch.host_model_selection import HostModelSelection, _quality_adoption_identity
from autoresearch.local_workbench import LocalWorkbench
from autoresearch.project_controller import ProjectController
from autoresearch.research_project import ResearchProject


def fence(point):
    print(json.dumps({"event":"fence", "point":point, "pid":os.getpid(),
                      "source_identity":_quality_adoption_identity()}), flush=True)
    sys.stdin.read(1)
    raise RuntimeError("Parent did not SIGKILL the fenced process")


def worker(mode, point, root, encoded):
    body = json.loads(base64.b64decode(encoded).decode("utf-8"))
    manager = LocalWorkbench(root)
    if mode == "kill":
        if point == "before-host":
            original = HostModelSelection.adopt_quality_plan
            def adopt(host, **kwargs):
                if kwargs.get("_manager_binding"): fence(point)
                return original(host, **kwargs)
            gate = patch.object(HostModelSelection, "adopt_quality_plan", new=adopt)
        elif point == "before-project":
            original = ResearchProject.save_plan
            def save(project, **kwargs):
                if kwargs.get("_host_quality_intent_sha256"): fence(point)
                return original(project, **kwargs)
            gate = patch.object(ResearchProject, "save_plan", new=save)
        elif point == "before-host-receipt":
            original = HostModelSelection._save
            def save(host, state):
                if state["requests"][body["host_request_id"]]["status"] == "applied": fence(point)
                return original(host, state)
            gate = patch.object(HostModelSelection, "_save", new=save)
        else:
            original = manager._save
            def save(con, request_id, record):
                if request_id == body["request_id"] and record.get("status") == "completed": fence(point)
                return original(con, request_id, record)
            gate = patch.object(manager, "_save", side_effect=save)
        with gate, patch.object(ResearchProject, "step", side_effect=AssertionError("step")), \
             patch.object(ResearchProject, "read_evidence", side_effect=AssertionError("evidence")), \
             patch.object(ProjectController, "_dispatch", side_effect=AssertionError("dispatch")), \
             patch("autoresearch.host_model_selection.run_claude_selection", side_effect=AssertionError("model")):
            manager.model_quality_plan_adopt(body)
        raise RuntimeError("Operation unexpectedly passed its fence")
    original = ResearchProject.save_plan
    def readonly(project, **kwargs):
        if not kwargs.get("_validate_only"): raise AssertionError("recovery attempted Project write")
        return original(project, **kwargs)
    host_gate = (patch.object(HostModelSelection, "_save", side_effect=AssertionError("Host write"))
                 if point == "before-manager-receipt" else
                 patch.object(HostModelSelection, "adopt_quality_plan", side_effect=AssertionError("Host retry")))
    try:
        with host_gate, patch.object(ResearchProject, "save_plan", new=readonly), \
             patch.object(ResearchProject, "step", side_effect=AssertionError("step")), \
             patch.object(ResearchProject, "read_evidence", side_effect=AssertionError("evidence")), \
             patch.object(ProjectController, "_dispatch", side_effect=AssertionError("dispatch")), \
             patch("autoresearch.host_model_selection.run_claude_selection", side_effect=AssertionError("model")):
            result = manager.model_quality_plan_adopt(body)
        event = {"event":"recovery", "pid":os.getpid(), "status":result["status"],
                 "replayed":result["replayed"], "source_identity":_quality_adoption_identity()}
    except ResearchError as error:
        event = {"event":"recovery", "pid":os.getpid(), "error":error.code,
                 "source_identity":_quality_adoption_identity()}
    print(json.dumps(event), flush=True)


class HostQualityWorkbenchProcessTests(unittest.TestCase):
    def stage(self):
        helper = fixture.HostQualityWorkbenchTests(methodName="runTest")
        f, manager, host, body, args = helper.stage(); self.addCleanup(helper.doCleanups)
        return f, manager, host, body, args

    def spawn(self, mode, point, manager, body):
        encoded = base64.b64encode(canonical(body).encode("utf-8")).decode("ascii")
        env = {**os.environ, "PYTHONDONTWRITEBYTECODE":"1"}
        proc = subprocess.Popen([sys.executable, "-B", str(Path(__file__).resolve()), "--worker", mode, point,
                                 str(manager.root), encoded], env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, text=True, bufsize=1)
        def cleanup():
            if proc.poll() is None: proc.kill()
            proc.communicate(timeout=15)
        self.addCleanup(cleanup)
        return proc

    def event(self, proc):
        with selectors.DefaultSelector() as selector:
            selector.register(proc.stdout, selectors.EVENT_READ)
            ready = selector.select(30)
        if not ready:
            proc.kill(); out, err = proc.communicate(timeout=10)
            self.fail("Worker did not reach fence: " + out + " " + err)
        line = proc.stdout.readline()
        if not line:
            _, err = proc.communicate(timeout=10); self.fail("Worker exited before event: " + err)
        event = json.loads(line); self.assertEqual(event["pid"], proc.pid)
        return event

    @staticmethod
    def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()

    @staticmethod
    def manager_record(manager, request_id):
        with sqlite3.connect(manager.db.as_uri() + "?mode=ro", uri=True) as con:
            row = con.execute("select command,digest,record from requests where id=?", (request_id,)).fetchone()
        return None if row is None else (row[0], row[1], json.loads(row[2]))

    @staticmethod
    def plan_claim(project, request_id):
        with sqlite3.connect(project.db.as_uri() + "?mode=ro", uri=True) as con:
            exists = con.execute("select 1 from sqlite_master where type='table' and name='quality_manager_claims'").fetchone()
            return [] if not exists else con.execute(
                "select intent_sha256,core_sha256 from quality_manager_claims where kind='plan' and request_id=?",
                (request_id,)).fetchall()

    def originals(self, f, host, record):
        state = f.project.status(); self.assertEqual(len(state["actions"]), 1)
        action = state["actions"][0]; self.assertEqual(action["status"], "completed"); self.assertTrue(action.get("artifact"))
        artifact = f.project.root / action["artifact"]; envelope = json.loads(artifact.read_bytes())
        self.assertEqual(envelope["sha256"], action["result_sha256"])
        self.assertEqual(envelope["sha256"], fingerprint({k:v for k,v in envelope.items() if k != "sha256"}))
        with sqlite3.connect(f.project.db.as_uri() + "?mode=ro", uri=True) as con:
            row = con.execute("select fingerprint,record from actions where request_id=?", (action["request_id"],)).fetchone()
        self.assertIsNotNone(row); self.assertEqual(row[0], action["request_sha256"]); self.assertEqual(json.loads(row[1]), action)
        parent = next(p for p in state["controller_requests"] if p["child_request_id"] == action["request_id"])
        self.assertEqual((parent["result"]["child"]["id"], parent["result"]["child"]["result_sha256"]),
                         (action["id"], action["result_sha256"]))
        folder = host.directory / record["directory"]
        files = {"source":f.project.root / "source.json", "artifact":artifact,
                 "context":folder / "context.json", "prompt":folder / "prompt.json",
                 "proposal":folder / "proposal.json", "response":host.directory / record["response_file"]}
        return state, {key:self.sha(path) for key,path in files.items()}

    def run_cut(self, point):
        f, manager, host, body, args = self.stage()
        original_host = host.status(request_id=body["host_request_id"])
        initial, initial_files = self.originals(f, host, original_host)
        original_project_db = f.project.db.read_bytes(); identity = _quality_adoption_identity()
        budget = initial["budget"]
        self.assertEqual((budget["local_tool_calls_used"], budget["new_model_requests"], budget["new_fits"],
                          budget["evidence_reads_used"]), (1, 0, 0, 0))
        proc = self.spawn("kill", point, manager, body)
        self.assertEqual(self.event(proc), {"event":"fence", "point":point, "pid":proc.pid, "source_identity":identity})
        command, digest, manager_record = self.manager_record(manager, body["request_id"])
        self.assertEqual(command, "model_quality_plan_adopt"); self.assertEqual(digest, fingerprint(body))
        self.assertEqual(manager_record["status"], "preparing"); manager_intent = manager_record["intent"]
        self.assertEqual(manager_intent["body"], body)
        self.assertEqual(manager_intent["intent_sha256"], fingerprint({k:v for k,v in manager_intent.items() if k != "intent_sha256"}))
        saved_host = host.status(request_id=body["host_request_id"])
        at_state, files = self.originals(f, host, saved_host)
        self.assertEqual(files, initial_files); self.assertEqual(at_state["budget"], budget)
        claim = self.plan_claim(f.project, body["host_request_id"])
        if point == "before-host":
            self.assertNotIn("quality_adoption", saved_host); self.assertEqual(saved_host["status"], "proposed")
            self.assertEqual(at_state, initial); self.assertEqual(claim, [])
        else:
            host_intent = saved_host["quality_adoption"]
            self.assertEqual(host_intent["schema_version"], "host-quality-adoption-v2")
            self.assertEqual(host_intent["manager_binding"], {"manager_root":str(manager.root.resolve()),
                             "request_id":body["request_id"], "intent_sha256":manager_intent["intent_sha256"]})
            self.assertEqual(host_intent["intent_sha256"], fingerprint({k:v for k,v in host_intent.items() if k != "intent_sha256"}))
            self.assertEqual(manager_intent["quality_ref_sha256"], fingerprint(host_intent["quality_feedback_ref"]))
            self.assertEqual(saved_host["status"], "applied" if point == "before-manager-receipt" else "proposed")
            if point == "before-project":
                self.assertEqual(at_state, initial); self.assertEqual(claim, [])
            else:
                revision = at_state["plan_revisions"][-1]
                self.assertEqual(len(at_state["plan_revisions"]), len(initial["plan_revisions"]) + 1)
                self.assertEqual(revision["request_id"], body["host_request_id"])
                self.assertEqual({key:revision[key] for key in args["plan"]}, args["plan"])
                self.assertEqual(revision["quality_feedback_ref"], host_intent["quality_feedback_ref"])
                self.assertEqual(claim, [(host_intent["intent_sha256"], fingerprint(revision))])
        if point in ("before-host", "before-project"):
            self.assertEqual(f.project.db.read_bytes(), original_project_db)
        self.assertEqual(_quality_adoption_identity(), identity)
        os.kill(proc.pid, signal.SIGKILL); proc.wait(timeout=15); self.assertEqual(proc.returncode, -signal.SIGKILL)
        frozen_manager, frozen_host, frozen_project = manager.db.read_bytes(), host.state_file.read_bytes(), f.project.db.read_bytes()
        self.assertEqual(self.manager_record(manager, body["request_id"])[2], manager_record)
        self.assertEqual(host.status(request_id=body["host_request_id"]), saved_host)
        self.assertEqual(self.originals(f, host, saved_host), (at_state, files))
        resumed = self.spawn("recover", point, manager, body); reply = self.event(resumed); resumed.wait(timeout=30)
        self.assertEqual(resumed.returncode, 0); self.assertNotEqual(resumed.pid, proc.pid)
        if point == "before-manager-receipt":
            self.assertEqual(reply, {"event":"recovery", "pid":resumed.pid, "status":"applied", "replayed":True, "source_identity":identity})
            final = self.manager_record(manager, body["request_id"])[2]
            self.assertEqual(final["status"], "completed"); self.assertEqual(final["intent"], manager_intent)
            self.assertEqual(final["result"]["host_request_id"], body["host_request_id"])
            self.assertEqual(final["result"]["plan_sha256"], fingerprint(revision))
        else:
            self.assertEqual(reply, {"event":"recovery", "pid":resumed.pid, "error":"OPERATION_INCOMPLETE", "source_identity":identity})
            self.assertEqual(manager.db.read_bytes(), frozen_manager)
            self.assertEqual(self.manager_record(manager, body["request_id"])[2], manager_record)
        self.assertEqual(host.state_file.read_bytes(), frozen_host); self.assertEqual(f.project.db.read_bytes(), frozen_project)
        self.assertEqual(self.originals(f, host, saved_host), (at_state, files)); self.assertEqual(self.plan_claim(f.project, body["host_request_id"]), claim)
        self.assertEqual(_quality_adoption_identity(), identity)
        print(json.dumps({"point":point, "killed_pid":proc.pid, "kill_returncode":proc.returncode,
                          "recovery_pid":resumed.pid, "recovery":reply, "source_identity":identity,
                          "manager_request_id":body["request_id"], "host_request_id":body["host_request_id"],
                          "registration_request_id":body["registration_request_id"], "manager_intent_sha256":manager_intent["intent_sha256"],
                          "host_intent_sha256":None if point == "before-host" else host_intent["intent_sha256"],
                          "claim":claim, "project_db_sha256":hashlib.sha256(frozen_project).hexdigest(),
                          "host_state_sha256":hashlib.sha256(frozen_host).hexdigest(), "manager_before_sha256":hashlib.sha256(frozen_manager).hexdigest(),
                          "manager_after_sha256":self.sha(manager.db), "original_sha256":files,
                          "local_tool_calls_used":at_state["budget"]["local_tool_calls_used"]}), flush=True)

    def test_manager_intent_before_host(self): self.run_cut("before-host")
    def test_host_intent_before_project(self): self.run_cut("before-project")
    def test_project_before_host_receipt(self): self.run_cut("before-host-receipt")
    def test_host_applied_before_manager_receipt(self): self.run_cut("before-manager-receipt")


if __name__ == "__main__":
    if len(sys.argv) == 6 and sys.argv[1] == "--worker": worker(*sys.argv[2:])
    else: unittest.main()
