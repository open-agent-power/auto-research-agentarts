"""Local-demo boundary tests. Every training call is mocked; no CPU fitting/cloud."""
from contextlib import contextmanager
import hashlib
from http.client import HTTPConnection
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

import numpy as np

from autoresearch import datasets, training
from autoresearch.cli import main
from autoresearch.contracts import ResearchError
from autoresearch.engine import AGENT_POLICY, Engine
from autoresearch.local_demo import DIRECTORY, LocalDemo, scripted_decision
from autoresearch.studio import create_server
from autoresearch.studio_project import prepare_project


PARENT = "a" * 64


def no_fit(candidate, dataset_id=datasets.STEELS_ID):
    """Zero coefficients, with actual validation error but no fitting."""
    data = datasets.descriptor(dataset_id)
    x, y = datasets.split_data(dataset_id, "train")
    _, vy = datasets.split_data(dataset_id, "validation")
    width = x.shape[1]
    return {"format": "polynomial-ridge-json-v1", "dataset_id": dataset_id,
            "evidence_type": data["evidence_type"], "candidate": candidate.to_dict(),
            "data_sha256": data["data_sha256"], "split_protocol": data["split_protocol"],
            "training_code_sha256": training.code_identity(), "powers": np.eye(width, dtype=int).tolist(),
            "mean": [0.] * width, "scale": [1.] * width, "coef": [0.] * width, "intercept": 0.,
            "libraries": {"fixture": "unit-test-zero-coefficients-no-fit"}}, {
            "training_mse": float(np.mean(y ** 2)), "validation_mse": float(np.mean(vy ** 2)),
            "num_features": width, "training_seconds": 0.}


def hashes(root):
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in root.rglob("*") if p.is_file()}


def wait_finished(demo):
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        state = demo.status()
        if state["status"] != "running":
            return state
        time.sleep(.01)
    raise AssertionError("mocked local job did not finish")


class LocalDemoTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.mock_train = patch("autoresearch.training.train", side_effect=no_fit).start()
        self.addCleanup(patch.stopall)
        patch("autoresearch.model_client.ChatClient.complete", side_effect=AssertionError("model calls forbidden")).start()
        self.demo = LocalDemo(self.root, PARENT, enabled=True)

    def error(self, code, call):
        with self.assertRaises(ResearchError) as caught:
            call()
        self.assertEqual(caught.exception.code, code)

    def test_disabled_and_idle_get_create_no_resources(self):
        before = list(self.root.iterdir())
        with patch("autoresearch.local_demo.Engine", side_effect=AssertionError("GET must not initialize Engine")):
            for demo, status in ((self.demo, "idle"), (LocalDemo(self.root, PARENT), "disabled")):
                for _ in range(2):
                    value = demo.status()
                    self.assertEqual(value["status"], status)
                    self.assertEqual(value["parent_snapshot_sha256"], PARENT)
                    self.assertEqual(value["origin"], "local_script_not_llm")
                    self.assertTrue(value["independent_run"])
                    self.assertEqual(value["max_trials"], 2)
                    self.assertEqual(value["trials"], [])
                    self.assertEqual(value["jobs"], [])
                    self.assertEqual(value["cloud_calls"] + value["model_calls"], 0)
            self.error("LOCAL_DEMO_DISABLED", lambda: LocalDemo(self.root, PARENT).step("one"))
        self.assertEqual(list(self.root.iterdir()), before)
        self.mock_train.assert_not_called()

    def test_idempotency_restart_budget_and_proposals(self):
        first = self.demo.step("one")
        state = wait_finished(self.demo)
        self.assertEqual(state["status"], "paused")
        self.assertEqual(state["consumed"], 1)
        again = self.demo.step("one")
        self.assertTrue(again["replayed"])
        self.assertEqual(first["job_id"], again["job_id"])
        self.assertEqual(self.mock_train.call_count, 1)
        before = hashes(self.demo.root)
        fresh = LocalDemo(self.root, PARENT, enabled=True)
        self.assertEqual(fresh.status()["status"], "paused")
        self.assertEqual(hashes(self.demo.root), before)
        fresh.step("two")
        state = wait_finished(fresh)
        self.assertEqual(state["status"], "completed")
        self.assertEqual(state["consumed"], 2)
        self.assertEqual(self.mock_train.call_count, 2)
        self.assertEqual(state["trials"][0]["candidate"], {"degree": 1, "alpha": 1.0})
        proposal = state["trials"][1]["proposal"]
        self.assertEqual(proposal["evidence_trial_ids"], [state["trials"][0]["id"]])
        self.assertEqual(len(proposal["observation_sha256"]), 64)
        self.error("LOCAL_DEMO_BUDGET_EXHAUSTED", lambda: fresh.step("three"))
        self.assertTrue(fresh.step("one")["replayed"])
        self.assertEqual(self.mock_train.call_count, 2)
        self.assertEqual(LocalDemo(self.root, PARENT, enabled=True).status()["status"], "completed")

    def test_concurrent_worker_and_other_process_fail_closed(self):
        entered, release = threading.Event(), threading.Event()
        def blocking(candidate, dataset_id):
            entered.set()
            if not release.wait(8):
                raise RuntimeError("unit-test timeout")
            return no_fit(candidate, dataset_id)
        self.mock_train.side_effect = blocking
        try:
            first = self.demo.step("one")
            self.assertTrue(entered.wait(5))
            for _ in range(30):
                self.assertEqual(self.demo.status()["status"], "running")
            self.error("LOCAL_DEMO_BUSY", lambda: self.demo.step("two"))
            other = LocalDemo(self.root, PARENT, enabled=True)
            self.assertEqual(other.status()["status"], "needs_review")
            self.error("LOCAL_DEMO_NEEDS_REVIEW", lambda: other.step("three"))
            self.assertEqual(other.step("one")["job_id"], first["job_id"])
            script = """import sys,json
from unittest.mock import patch
from autoresearch.local_demo import LocalDemo
from autoresearch.contracts import ResearchError
with patch('autoresearch.training.train',side_effect=AssertionError('no fitting in child')):
 d=LocalDemo(sys.argv[1],sys.argv[2],enabled=True)
 try: d.step('child-new')
 except ResearchError as e: print(json.dumps({'code':e.code,'status':d.status()['status']}))
"""
            child = subprocess.run([sys.executable, "-c", script, str(self.root), PARENT], capture_output=True, text=True, timeout=10)
            self.assertEqual(child.returncode, 0, child.stderr)
            self.assertEqual(json.loads(child.stdout), {"code": "LOCAL_DEMO_NEEDS_REVIEW", "status": "needs_review"})
            self.assertEqual(self.demo.status()["jobs"][0]["status"], "running")
            self.assertEqual(self.mock_train.call_count, 1)
        finally:
            release.set()
            wait_finished(self.demo)

    def test_hard_exit_after_reservation_does_not_resend_or_reset(self):
        script = """import os,sys
from unittest.mock import patch
from autoresearch.local_demo import LocalDemo
with patch('autoresearch.training.train',side_effect=AssertionError('no fitting in child')):
 d=LocalDemo(sys.argv[1],sys.argv[2],enabled=True)
 d._start_worker=lambda *args:os._exit(17)
 d.step('interrupted')
"""
        child = subprocess.run([sys.executable, "-c", script, str(self.root), PARENT], capture_output=True, timeout=10)
        self.assertEqual(child.returncode, 17)
        fresh = LocalDemo(self.root, PARENT, enabled=True)
        before = hashes(fresh.root)
        self.assertEqual(fresh.status()["status"], "needs_review")
        self.assertEqual(fresh.status()["jobs"][0]["status"], "reserved")
        with patch.object(fresh, "_start_worker", side_effect=AssertionError("must not resend")):
            self.assertTrue(fresh.step("interrupted")["replayed"])
            self.error("LOCAL_DEMO_NEEDS_REVIEW", lambda: fresh.step("new"))
        self.assertEqual(hashes(fresh.root), before)
        self.mock_train.assert_not_called()

    def test_training_failure_is_sanitized_and_blocks_new_work(self):
        self.mock_train.side_effect = RuntimeError("private/path secret https://private.invalid")
        self.demo.step("fail")
        state = wait_finished(self.demo)
        self.assertEqual(state["status"], "failed")
        self.assertEqual(state["consumed"], 1)
        self.assertNotIn("private", json.dumps(state))
        self.error("LOCAL_DEMO_NEEDS_REVIEW", lambda: self.demo.step("new"))
        self.assertTrue(self.demo.step("fail")["replayed"])
        self.assertEqual(self.mock_train.call_count, 1)

    def test_thread_launch_failure_is_durable_and_not_retried(self):
        with patch("autoresearch.local_demo.threading.Thread", side_effect=RuntimeError("private launch detail")):
            self.error("LOCAL_DEMO_NEEDS_REVIEW", lambda: self.demo.step("launch-failed"))
        state = self.demo.status()
        self.assertEqual(state["status"], "failed")
        self.assertEqual(state["jobs"][0]["error_code"], "LOCAL_DEMO_LAUNCH_FAILED")
        self.assertNotIn("private", json.dumps(state))
        with patch.object(self.demo, "_start_worker", side_effect=AssertionError("no relaunch")):
            self.assertTrue(self.demo.step("launch-failed")["replayed"])
        self.error("LOCAL_DEMO_NEEDS_REVIEW", lambda: self.demo.step("new"))
        self.mock_train.assert_not_called()

    def test_changed_parent_cannot_reinitialize_existing_budget(self):
        self.demo.step("first")
        wait_finished(self.demo)
        changed = LocalDemo(self.root, "c"*64, enabled=True)
        before = hashes(self.demo.root)
        self.assertEqual(changed.status()["status"], "needs_review")
        self.error("LOCAL_DEMO_UNSAFE", lambda: changed.step("new-parent"))
        self.assertEqual(hashes(self.demo.root), before)
        self.assertEqual(self.mock_train.call_count, 1)

    def test_foreign_directory_is_not_adopted(self):
        self.demo.root.mkdir()
        private = self.demo.root / "unrelated.txt"
        private.write_text("do not overwrite", encoding="utf-8")
        self.assertEqual(self.demo.status()["status"], "needs_review")
        self.error("LOCAL_DEMO_UNSAFE", lambda: self.demo.step("new"))
        self.assertEqual(private.read_text(), "do not overwrite")
        self.mock_train.assert_not_called()

    def test_symlink_escape_is_rejected(self):
        outside = self.root / "outside"
        outside.mkdir()
        try:
            self.demo.root.symlink_to(outside, target_is_directory=True)
        except OSError:
            self.skipTest("directory symlink creation unavailable")
        self.assertEqual(self.demo.status()["status"], "needs_review")
        self.error("LOCAL_DEMO_UNSAFE", lambda: self.demo.step("new"))
        self.assertEqual(list(outside.iterdir()), [])

    def test_database_hardlinks_fail_closed_without_writing_external_files(self):
        for index, relative in enumerate(("engine/research.sqlite3", "jobs.sqlite3")):
            with self.subTest(relative=relative):
                workspace = self.root / ("hardlink-case-" + str(index))
                workspace.mkdir()
                demo = LocalDemo(workspace, PARENT, enabled=True)
                demo._initialize()
                target = demo.root / relative
                outside = self.root / ("external-" + str(index) + ".sqlite3")
                shutil.copyfile(target, outside)
                target.unlink()  # Only the freshly generated temporary test DB.
                try:
                    os.link(outside, target)
                except OSError:
                    self.skipTest("hard links unavailable on this filesystem")
                self.assertGreater(target.stat().st_nlink, 1)
                self.assertGreater(outside.stat().st_nlink, 1)
                before = hashlib.sha256(outside.read_bytes()).hexdigest()
                local_before = hashes(demo.root)
                self.assertEqual(demo.status()["status"], "needs_review")
                self.error("LOCAL_DEMO_UNSAFE", lambda: demo.step("blocked-hardlink"))
                self.assertEqual(hashlib.sha256(outside.read_bytes()).hexdigest(), before)
                self.assertEqual(hashes(demo.root), local_before)
                self.mock_train.assert_not_called()

    def test_second_choice_depends_on_actual_feedback(self):
        def observation(train, validation):
            return {"observation_sha256": "b"*64, "trials": [{"id": "first", "status": "accepted", "metrics": {
                "training_mse": train, "validation_mse": validation}}]}
        self.assertEqual(scripted_decision(observation(100, 110))["proposal"]["candidate"], {"degree": 2, "alpha": 1.0})
        self.assertEqual(scripted_decision(observation(100, 200))["proposal"]["candidate"], {"degree": 1, "alpha": 1000.0})
        self.mock_train.assert_not_called()

    def test_disappearing_temporary_entry_is_not_an_unsafe_path(self):
        self.demo._initialize()
        transient = self.demo.engine_root / "research.sqlite3-journal"
        transient.touch()
        original = Path.resolve
        def disappearing(path, *args, **kwargs):
            if path == transient:
                raise AssertionError("temporary files must not require realpath resolution")
            return original(path, *args, **kwargs)
        with patch.object(Path, "resolve", disappearing):
            self.demo._guard()
        transient.unlink()
        self.assertEqual(self.demo.status()["status"], "idle")
        self.mock_train.assert_not_called()

    def test_disappearing_temporary_metadata_is_not_an_unsafe_path(self):
        self.demo._initialize()
        transient = self.demo.engine_root / "research.sqlite3-journal"
        transient.touch()
        original = Path.lstat
        def disappearing(path, *args, **kwargs):
            if path == transient:
                transient.unlink(missing_ok=True)
                raise FileNotFoundError("temporary journal disappeared before lstat")
            return original(path, *args, **kwargs)
        with patch.object(Path, "lstat", disappearing):
            self.demo._guard()
        self.assertEqual(self.demo.status()["status"], "idle")
        self.mock_train.assert_not_called()


class LocalDemoHttpTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source, self.output = self.root / "source", self.root / "studio"
        self.patcher = patch("autoresearch.training.train", side_effect=no_fit)
        self.mock_train = self.patcher.start()
        self.addCleanup(self.patcher.stop)
        engine = Engine(self.source)
        cid = engine.create("source-case", "Unit fixture, no training", 2, datasets.STEELS_ID, AGENT_POLICY)["campaign_id"]
        observation = engine.observe(cid)
        engine.submit(cid, "source-one", scripted_decision(observation)["proposal"])
        self.project = prepare_project(self.source, cid, self.output)
        self.parent = self.project["snapshot"]["sha256"]
        self.mock_train.reset_mock()
        self.source_before = hashes(self.source)
        self.frozen_before = {name: (self.output / name).read_bytes() for name in ("project.json", "evidence-manifest.json")}

    @contextmanager
    def server(self, enabled=False):
        server = create_server(self.output, port=0, local_demo=enabled)
        thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": .01}, daemon=True)
        thread.start()
        try:
            yield server
        finally:
            server.shutdown()
            server.server_close()
            thread.join(5)

    def request(self, server, method, route, value=None, headers=None, raw=None):
        connection = HTTPConnection("127.0.0.1", server.server_port, timeout=10)
        try:
            body = raw if raw is not None else json.dumps(value).encode() if value is not None else None
            connection.request(method, route, body=body, headers=headers or {})
            response = connection.getresponse()
            return response.status, json.loads(response.read())
        finally:
            connection.close()

    def headers(self, server):
        _, project = self.request(server, "GET", "/api/project")
        return {"Content-Type": "application/json", "X-Research-CSRF": project["csrf_token"],
                "Origin": f"http://127.0.0.1:{server.server_port}"}

    def test_default_disabled_get_and_cli_flag(self):
        with self.server() as server:
            status, state = self.request(server, "GET", "/api/local-demo")
            self.assertEqual(status, 200)
            self.assertFalse(state["enabled"])
            self.assertEqual(state["parent_snapshot_sha256"], self.parent)
            status, value = self.request(server, "POST", "/api/local-demo/step", {"request_id": "one"}, self.headers(server))
            self.assertEqual((status, value["error"]["code"]), (403, "LOCAL_DEMO_DISABLED"))
        self.assertFalse((self.output / DIRECTORY).exists())
        self.mock_train.assert_not_called()
        for flag in ([], ["--local-demo"]):
            with patch("autoresearch.studio.serve") as serve:
                self.assertEqual(main(["studio", "--workspace", str(self.output), *flag]), 0)
                self.assertEqual(serve.call_args.kwargs, {"local_demo": bool(flag)})

    def test_http_guards_reject_untrusted_inputs_before_initialization(self):
        with self.server(True) as server:
            valid = self.headers(server)
            status, _ = self.request(server, "GET", "/api/local-demo", headers={"Host": "attacker.invalid"})
            self.assertEqual(status, 403)
            for changed in ({"Origin": "https://attacker.invalid"}, {"X-Research-CSRF": "bad"}, {"Host": "attacker.invalid"}):
                status, _ = self.request(server, "POST", "/api/local-demo/step", {"request_id": "one"}, {**valid, **changed})
                self.assertEqual(status, 403)
            for value in ({}, {"request_id": "../escape"}, {"request_id": None}, {"request_id": 1},
                          {"request_id": "x"*81}, {"request_id": "one", "candidate": {}},
                          {"request_id": "one", "path": "elsewhere"}, {"request_id": "one", "url": "https://external.invalid"}):
                status, _ = self.request(server, "POST", "/api/local-demo/step", value, valid)
                self.assertEqual(status, 400, value)
            for raw in (b'{"request_id":"a","request_id":"b"}', b'{"request_id":NaN}', b'[]', b'{'):
                status, _ = self.request(server, "POST", "/api/local-demo/step", headers=valid, raw=raw)
                self.assertEqual(status, 400)
            self.assertFalse((self.output / DIRECTORY).exists())
        self.mock_train.assert_not_called()

    def test_mocked_http_steps_preserve_source_and_frozen_snapshot(self):
        with self.server(True) as server:
            headers = self.headers(server)
            status, first = self.request(server, "POST", "/api/local-demo/step", {"request_id": "studio-one"}, headers)
            self.assertEqual(status, 202)
            self.assertEqual(wait_finished(server.local_demo)["status"], "paused")
            status, replay = self.request(server, "POST", "/api/local-demo/step", {"request_id": "studio-one"}, headers)
            self.assertEqual(status, 200)
            self.assertEqual(replay["job_id"], first["job_id"])
            status, _ = self.request(server, "POST", "/api/local-demo/step", {"request_id": "studio-two"}, headers)
            self.assertEqual(status, 202)
            self.assertEqual(wait_finished(server.local_demo)["status"], "completed")
            status, _ = self.request(server, "POST", "/api/local-demo/step", {"request_id": "studio-three"}, headers)
            self.assertEqual(status, 409)
            status, result = self.request(server, "GET", "/api/local-demo")
            self.assertEqual(result["consumed"], 2)
            self.assertIn("proposal", result["trials"][1])
        self.assertEqual(self.mock_train.call_count, 2)
        self.assertEqual(hashes(self.source), self.source_before)
        self.assertEqual({name: (self.output / name).read_bytes() for name in self.frozen_before}, self.frozen_before)


if __name__ == "__main__":
    unittest.main()
