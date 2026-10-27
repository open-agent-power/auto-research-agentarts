import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

from autoresearch.contracts import Candidate, ResearchError
from autoresearch.engine import Engine
from autoresearch import training
from autoresearch.protocol import handle_request


class CampaignTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.engine = Engine(self.root)
        self.cid = self.engine.create("create-1", "Engineering fixture", 6)["campaign_id"]

    def tearDown(self):
        self.tmp.cleanup()

    def error(self, code, call):
        with self.assertRaises(ResearchError) as ctx:
            call()
        self.assertEqual(ctx.exception.code, code)

    def test_real_training_improvement_rejection_and_parameter_artifact(self):
        first = self.engine.step(self.cid, "first")
        second = self.engine.step(self.cid, "second")
        third = self.engine.step(self.cid, "third")
        self.assertEqual([first["status"], second["status"], third["status"]], ["accepted", "accepted", "rejected"])
        self.assertLess(second["metrics"]["validation_mse"], first["metrics"]["validation_mse"]*.01)
        self.assertEqual(self.engine.status(self.cid)["best_trial_id"], second["trial_id"])
        model = json.loads((self.root/second["model_artifact"]).read_text(encoding="utf-8"))
        self.assertGreater(len(model["coef"]), 2)
        self.assertEqual(model["training_rows"], 96)
        self.assertIsNone(self.engine.status(self.cid)["final_evaluation"])

    def test_idempotent_retry_and_conflicting_candidate(self):
        first = self.engine.step(self.cid, "first")
        self.assertEqual(first, self.engine.step(self.cid, "first"))
        self.assertEqual(self.engine.status(self.cid)["budget"]["consumed_trials"], 1)
        self.error("IDEMPOTENCY_CONFLICT", lambda: self.engine.step(self.cid, "first", {"degree": 2, "alpha": .01}))
        self.error("IDEMPOTENCY_CONFLICT", lambda: self.engine.create("create-1", "different goal", 6))

    def test_fresh_engine_resumes_completed_progress(self):
        first = self.engine.step(self.cid, "first")
        self.engine.pause(self.cid)
        fresh = Engine(self.root)
        self.error("CAMPAIGN_NOT_ACTIVE", lambda: fresh.step(self.cid, "second"))
        fresh.pause(self.cid, False)
        second = fresh.step(self.cid, "second")
        self.assertEqual(second["parent_trial_id"], first["trial_id"])
        self.assertEqual(fresh.status(self.cid)["budget"]["consumed_trials"], 2)

    def test_budget_remains_consumed_after_failure(self):
        cid = self.engine.create("limited", "bounded", 1)["campaign_id"]
        with patch("autoresearch.training.train", side_effect=RuntimeError("test failure")):
            result = self.engine.step(cid, "failed")
        self.assertEqual(result["status"], "failed")
        self.assertEqual(self.engine.step(cid, "failed"), result)
        self.error("BUDGET_EXHAUSTED", lambda: self.engine.step(cid, "next", Candidate(1, .01)))
        self.assertIsNone(self.engine.status(cid)["best_trial_id"])

    def test_finalization_locks_further_optimization(self):
        self.engine.step(self.cid, "first")
        final = self.engine.finalize(self.cid)
        self.assertEqual(final, self.engine.finalize(self.cid))
        self.assertIn("test_mse", final)
        self.error("CAMPAIGN_NOT_ACTIVE", lambda: self.engine.step(self.cid, "next", Candidate(2, .01)))
        self.error("CAMPAIGN_FINALIZED", lambda: self.engine.pause(self.cid, False))

    def test_tampered_parameters_cannot_receive_terminal_evaluation(self):
        trial = self.engine.step(self.cid, "first")
        (self.root/trial["model_artifact"]).write_text("{}", encoding="utf-8")
        self.error("ARTIFACT_CHANGED", lambda: self.engine.finalize(self.cid))
        self.assertIsNone(self.engine.status(self.cid)["final_evaluation"])

    def test_concurrent_duplicate_returns_same_reservation_without_training_twice(self):
        entered, release = threading.Event(), threading.Event()
        original = training.train
        output = []
        def slow(candidate):
            entered.set()
            if not release.wait(10):
                raise RuntimeError("test release timeout")
            return original(candidate)
        with patch("autoresearch.training.train", side_effect=slow) as mock:
            worker = threading.Thread(target=lambda: output.append(self.engine.step(self.cid, "same")))
            worker.start()
            self.assertTrue(entered.wait(10))
            try:
                retry = Engine(self.root).step(self.cid, "same")
                self.assertEqual(retry["status"], "running")
                self.error("BUSY", lambda: Engine(self.root).step(self.cid, "different", Candidate(2, .01)))
            finally:
                release.set()
                worker.join(10)
        self.assertFalse(worker.is_alive())
        self.assertEqual(retry["trial_id"], output[0]["trial_id"])
        self.assertEqual(mock.call_count, 1)
        self.assertEqual(self.engine.status(self.cid)["budget"]["consumed_trials"], 1)

    def test_killed_process_requires_explicit_reconciliation_and_does_not_retrain(self):
        script = """
import os,sys
from autoresearch.engine import Engine
from autoresearch import training
training.train=lambda candidate: os._exit(17)
Engine(sys.argv[1]).step(sys.argv[2], 'killed')
"""
        child = subprocess.run([sys.executable, "-c", script, str(self.root), self.cid], timeout=30)
        self.assertEqual(child.returncode, 17)
        fresh = Engine(self.root)
        old = fresh.step(self.cid, "killed")
        self.assertEqual(old["status"], "running")
        self.error("RECONCILIATION_REQUIRED", lambda: fresh.reconcile_interrupted(self.cid, old["trial_id"]))
        recovered = fresh.reconcile_interrupted(self.cid, old["trial_id"], confirm_stopped=True)
        self.assertEqual(recovered["status"], "failed")
        self.assertEqual(fresh.step(self.cid, "killed"), recovered)
        next_trial = fresh.step(self.cid, "retry-new", Candidate(1, .01))
        self.assertEqual(next_trial["status"], "accepted")
        self.assertEqual(fresh.status(self.cid)["budget"]["consumed_trials"], 2)

    def test_late_result_after_reconciliation_does_not_promote(self):
        entered, release = threading.Event(), threading.Event()
        original = training.train
        def slow(candidate):
            entered.set()
            release.wait(10)
            return original(candidate)
        with patch("autoresearch.training.train", side_effect=slow):
            worker = threading.Thread(target=lambda: self.engine.step(self.cid, "late"))
            worker.start()
            self.assertTrue(entered.wait(10))
            trial = self.engine.status(self.cid)["trials"][0]
            try:
                self.engine.reconcile_interrupted(self.cid, trial["id"], confirm_stopped=True)
            finally:
                release.set()
                worker.join(10)
        self.assertFalse(worker.is_alive())
        self.assertIsNone(self.engine.status(self.cid)["best_trial_id"])
        self.assertEqual(self.engine.status(self.cid)["trials"][0]["status"], "failed")

    def test_protocol_rejects_commands_paths_evaluator_changes_and_invalid_numbers(self):
        base = {"schema_version": "0.1", "request_id": "tool-1", "action": "run_trial", "campaign_id": self.cid}
        for extra in [{"command": "anything"}, {"workspace": "../outside"}, {"score": 0}, {"evaluator": "changed"}]:
            self.assertFalse(handle_request(base | extra, self.root)["ok"])
        for degree, alpha in [(True, 1), (0, 1), (4, 1), (2, float("nan")), (2, float("inf")), (2, -1)]:
            result = handle_request(base | {"candidate": {"degree": degree, "alpha": alpha}}, self.root)
            self.assertEqual(result["error"]["code"], "INVALID_REQUEST")
        self.assertEqual(self.engine.status(self.cid)["budget"]["consumed_trials"], 0)

    def test_operator_reconciliation_is_not_a_model_callable_action(self):
        request = {"schema_version": "0.1", "request_id": "unsafe", "action": "reconcile_interrupted", "campaign_id": self.cid}
        self.assertEqual(handle_request(request, self.root)["error"]["code"], "INVALID_REQUEST")

    def test_real_json_cli_request_and_invalid_json_exit_status(self):
        request = {"schema_version": "0.1", "request_id": "cli", "action": "campaign_status", "campaign_id": self.cid}
        command = [sys.executable, "-m", "autoresearch", "tool", "--workspace", str(self.root)]
        result = subprocess.run(command, input=json.dumps(request), capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["result"]["campaign_id"], self.cid)
        bad = subprocess.run(command, input="{", capture_output=True, text=True, timeout=30)
        self.assertEqual(bad.returncode, 2)
        self.assertEqual(json.loads(bad.stdout)["error"]["code"], "INVALID_REQUEST")
        nonfinite = subprocess.run(command, input='{"request_id":NaN}', capture_output=True, text=True, timeout=30)
        self.assertEqual(nonfinite.returncode, 2)
        self.assertEqual(json.loads(nonfinite.stdout)["error"]["code"], "INVALID_REQUEST")

    def test_invalid_request_identifier_is_not_echoed_as_an_arbitrary_object(self):
        result = handle_request({"schema_version": "0.1", "request_id": {"x": float("nan")}}, self.root)
        self.assertIsNone(result["request_id"])
        json.dumps(result, allow_nan=False)


if __name__ == "__main__":
    unittest.main()
