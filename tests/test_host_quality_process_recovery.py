"""Real process SIGKILL at two Host adoption commit fences, synthetic data only.

These selected process-death windows do not demonstrate power-loss recovery.
"""
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

import test_host_quality_adoption as fixture
from autoresearch.contracts import ResearchError, fingerprint
from autoresearch.host_model_selection import HostModelSelection, _quality_adoption_identity
from autoresearch.project_controller import ProjectController
from autoresearch.research_project import ResearchProject


def _fence(point):
    print(json.dumps({"event":"fence", "point":point, "pid":os.getpid(),
                      "source_identity":_quality_adoption_identity()}), flush=True)
    sys.stdin.read(1)
    raise RuntimeError("Parent did not SIGKILL the fenced process")


def _worker(mode, point, workspace):
    host = HostModelSelection(workspace)
    request = {"request_id":"host-plan", "registration_request_id":"reg"}
    if mode == "kill":
        if point == "before-core":
            original = ResearchProject.save_plan
            def save(project, **kwargs):
                if kwargs.get("_host_quality_intent_sha256"):
                    _fence(point)
                return original(project, **kwargs)
            context = patch.object(ResearchProject, "save_plan", new=save)
        else:
            original = host._save
            def save(state):
                if state["requests"]["host-plan"]["status"] == "applied":
                    _fence(point)
                return original(state)
            context = patch.object(host, "_save", side_effect=save)
        with context, patch.object(ResearchProject, "step", side_effect=AssertionError("unexpected step")), \
             patch.object(ResearchProject, "read_evidence", side_effect=AssertionError("unexpected evidence")), \
             patch.object(ProjectController, "_dispatch", side_effect=AssertionError("unexpected dispatch")), \
             patch("autoresearch.host_model_selection.run_claude_selection", side_effect=AssertionError("unexpected model")):
            host.adopt_quality_plan(**request)
        raise RuntimeError("Operation unexpectedly passed its fence")
    original = ResearchProject.save_plan
    def readonly(project, **kwargs):
        if not kwargs.get("_validate_only"):
            raise AssertionError("recovery attempted a Project write")
        return original(project, **kwargs)
    try:
        with patch.object(ResearchProject, "save_plan", new=readonly), \
             patch.object(ResearchProject, "step", side_effect=AssertionError("unexpected step")), \
             patch.object(ResearchProject, "read_evidence", side_effect=AssertionError("unexpected evidence")), \
             patch.object(ProjectController, "_dispatch", side_effect=AssertionError("unexpected dispatch")), \
             patch("autoresearch.host_model_selection.run_claude_selection", side_effect=AssertionError("unexpected model")):
            result = host.adopt_quality_plan(**request)
        event = {"event":"recovery", "pid":os.getpid(), "status":result["status"],
                 "replayed":result["outcome"]["replayed"], "source_identity":_quality_adoption_identity()}
    except ResearchError as exc:
        event = {"event":"recovery", "pid":os.getpid(), "error":exc.code,
                 "source_identity":_quality_adoption_identity()}
    print(json.dumps(event), flush=True)


class HostQualityProcessRecoveryTests(unittest.TestCase):
    def stage(self):
        helper = fixture.HostQualityAdoptionTests(methodName="runTest")
        f, host, record, args = helper.stage()
        self.addCleanup(helper.doCleanups)
        return f, host, record, args

    def spawn(self, mode, point, host):
        env = {**os.environ, "PYTHONDONTWRITEBYTECODE":"1"}
        proc = subprocess.Popen([sys.executable, "-B", str(Path(__file__).resolve()), "--worker", mode, point,
                                 str(host.project.root)], env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
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
            _, err = proc.communicate(timeout=10)
            self.fail("Worker exited before event: " + err)
        event = json.loads(line)
        self.assertEqual(event["pid"], proc.pid)
        return event

    @staticmethod
    def sha(path):
        return hashlib.sha256(path.read_bytes()).hexdigest()

    @staticmethod
    def claims(project):
        with sqlite3.connect(project.db.as_uri() + "?mode=ro", uri=True) as con:
            exists = con.execute("select 1 from sqlite_master where type='table' and name='quality_manager_claims'").fetchone()
            return [] if not exists else con.execute(
                "select intent_sha256,core_sha256 from quality_manager_claims where kind='plan' and request_id='host-plan'").fetchall()

    def originals(self, f, host, record):
        state = f.project.status()
        self.assertEqual(len(state["actions"]), 1)
        action = state["actions"][0]
        self.assertEqual(action["status"], "completed")
        self.assertTrue(action.get("artifact"))
        artifact = f.project.root / action["artifact"]
        envelope = json.loads(artifact.read_bytes())
        self.assertEqual(envelope["sha256"], action["result_sha256"])
        self.assertEqual(envelope["sha256"], fingerprint({k:v for k,v in envelope.items() if k != "sha256"}))
        with sqlite3.connect(f.project.db.as_uri() + "?mode=ro", uri=True) as con:
            row = con.execute("select fingerprint,record from actions where request_id=?", (action["request_id"],)).fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row[0], action["request_sha256"])
        self.assertEqual(json.loads(row[1]), action)
        parent = next(p for p in state["controller_requests"] if p["child_request_id"] == action["request_id"])
        self.assertEqual(parent["result"]["child"]["id"], action["id"])
        self.assertEqual(parent["result"]["child"]["result_sha256"], action["result_sha256"])
        folder = host.directory / record["directory"]
        files = {"source":f.project.root / "source.json", "artifact":artifact,
                 "context":folder / "context.json", "prompt":folder / "prompt.json",
                 "proposal":folder / "proposal.json", "response":host.directory / record["response_file"]}
        return state, {key:self.sha(path) for key,path in files.items()}

    def run_cut(self, point):
        f, host, proposal, args = self.stage()
        identity = _quality_adoption_identity()
        original, original_files = self.originals(f, host, proposal)
        before_db = f.project.db.read_bytes()
        self.assertEqual((original["budget"]["local_tool_calls_used"], original["budget"]["new_model_requests"],
                          original["budget"]["new_fits"], original["budget"]["evidence_reads_used"]), (1, 0, 0, 0))
        proc = self.spawn("kill", point, host)
        self.assertEqual(self.event(proc), {"event":"fence", "point":point, "pid":proc.pid, "source_identity":identity})
        at_record = host.status(request_id="host-plan")
        self.assertEqual(at_record["status"], "proposed")
        self.assertEqual(at_record["proposal"], proposal["proposal"])
        intent = at_record["quality_adoption"]
        self.assertEqual(intent["request_id"], "host-plan")
        self.assertEqual(intent["quality_feedback_ref"]["registration_request_id"], "reg")
        self.assertEqual(intent["intent_sha256"], fingerprint({k:v for k,v in intent.items() if k != "intent_sha256"}))
        at_state, at_files = self.originals(f, host, at_record)
        self.assertEqual(at_files, original_files)
        self.assertEqual(at_state["budget"], original["budget"])
        claim = self.claims(f.project)
        if point == "before-core":
            self.assertEqual(at_state, original)
            self.assertEqual(f.project.db.read_bytes(), before_db)
            self.assertEqual(claim, [])
        else:
            self.assertEqual(len(at_state["plan_revisions"]), len(original["plan_revisions"]) + 1)
            revision = at_state["plan_revisions"][-1]
            self.assertEqual(revision["request_id"], "host-plan")
            self.assertEqual({k:revision[k] for k in args["plan"]}, args["plan"])
            self.assertEqual(revision["reason"], args["reason"])
            self.assertEqual(revision["quality_feedback_ref"], intent["quality_feedback_ref"])
            self.assertEqual(claim, [(intent["intent_sha256"], fingerprint(revision))])
        self.assertEqual(_quality_adoption_identity(), identity)
        os.kill(proc.pid, signal.SIGKILL); proc.wait(timeout=15)
        self.assertEqual(proc.returncode, -signal.SIGKILL)
        frozen_db, frozen_host = f.project.db.read_bytes(), host.state_file.read_bytes()
        self.assertEqual(host.status(request_id="host-plan"), at_record)
        self.assertEqual(self.originals(f, host, at_record), (at_state, at_files))
        resumed = self.spawn("recover", point, host)
        reply = self.event(resumed); resumed.wait(timeout=30)
        self.assertEqual(resumed.returncode, 0)
        self.assertNotEqual(resumed.pid, proc.pid)
        if point == "before-core":
            self.assertEqual(reply, {"event":"recovery", "pid":resumed.pid, "error":"OPERATION_INCOMPLETE", "source_identity":identity})
            self.assertEqual(host.state_file.read_bytes(), frozen_host)
            self.assertEqual(host.status(request_id="host-plan"), at_record)
        else:
            self.assertEqual(reply, {"event":"recovery", "pid":resumed.pid, "status":"applied", "replayed":True, "source_identity":identity})
            final = host.status(request_id="host-plan")
            self.assertEqual(final["quality_adoption"], intent)
            self.assertEqual(final["proposal"], at_record["proposal"])
            self.assertEqual(final["outcome"]["research_plan"], revision)
        self.assertEqual(f.project.db.read_bytes(), frozen_db)
        self.assertEqual(self.originals(f, host, at_record), (at_state, at_files))
        self.assertEqual(self.claims(f.project), claim)
        self.assertEqual(_quality_adoption_identity(), identity)
        print(json.dumps({"point":point, "killed_pid":proc.pid, "kill_returncode":proc.returncode,
                          "recovery_pid":resumed.pid, "recovery":reply, "source_identity":identity,
                          "project_db_sha256":hashlib.sha256(frozen_db).hexdigest(), "original_sha256":at_files,
                          "intent_sha256":intent["intent_sha256"], "quality_ref_sha256":fingerprint(intent["quality_feedback_ref"]),
                          "quality_parent_request_id":intent["quality_feedback_ref"]["quality_parent_request_id"],
                          "quality_child_request_id":intent["quality_feedback_ref"]["quality_child_request_id"],
                          "quality_action_id":intent["quality_feedback_ref"]["quality_action_id"],
                          "quality_result_sha256":intent["quality_feedback_ref"]["quality_result_sha256"],
                          "claim":claim, "local_tool_calls_used":at_state["budget"]["local_tool_calls_used"]}), flush=True)

    def test_before_project_commit(self): self.run_cut("before-core")
    def test_after_project_commit(self): self.run_cut("after-core")


if __name__ == "__main__":
    if len(sys.argv) == 5 and sys.argv[1] == "--worker": _worker(*sys.argv[2:])
    else: unittest.main()
