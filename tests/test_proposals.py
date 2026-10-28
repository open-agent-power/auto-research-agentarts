import copy
import json
from pathlib import Path
import sqlite3
import os
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

from autoresearch.contracts import ResearchError, fingerprint
from autoresearch.engine import Engine, AGENT_POLICY, FIXTURE_POLICY, PROTOCOL
from autoresearch.fixture import DATASET_ID
from autoresearch.protocol import handle_request
from autoresearch.reports import build_report, write_report
from autoresearch import training


class ProposalTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.engine = Engine(self.root)
        self.cid = self.engine.create("create", "Evidence-driven benchmark", 5, policy_kind=AGENT_POLICY)["campaign_id"]

    def tearDown(self):
        self.tmp.cleanup()

    def proposal(self, degree=1, alpha=.01):
        observation = self.engine.observe(self.cid)
        return {"observation_sha256": observation["observation_sha256"],
                "hypothesis": "A bounded feature change can be tested against the observed baseline.",
                "expected_effect": "Lower validation error under the frozen split, or retain the prior model.",
                "candidate": {"degree": degree, "alpha": alpha},
                "evidence_trial_ids": [observation["trials"][-1]["id"]] if observation["trials"] else []}

    def error(self, code, operation):
        with self.assertRaises(ResearchError) as ctx:
            operation()
        self.assertEqual(ctx.exception.code, code)

    def test_proposal_required_and_terminal_test_not_used_in_observation(self):
        self.error("PROPOSAL_REQUIRED", lambda: self.engine.step(self.cid, "auto"))
        self.error("PROPOSAL_REQUIRED", lambda: self.engine.step(self.cid, "manual", {"degree": 1, "alpha": .01}))
        first = self.engine.submit(self.cid, "first", self.proposal())
        self.assertEqual(first["status"], "accepted")
        self.engine.finalize(self.cid)
        self.assertNotIn("test_mse", json.dumps(self.engine.observe(self.cid)))
        self.error("CAMPAIGN_NOT_ACTIVE", lambda: self.engine.submit(self.cid, "after", self.proposal(2)))

    def test_stale_unknown_missing_evidence_and_unknown_fields_do_not_consume_trials(self):
        stale = self.proposal(2)
        self.engine.submit(self.cid, "first", self.proposal())
        self.error("STALE_OBSERVATION", lambda: self.engine.submit(self.cid, "stale", stale))
        for evidence in ([], ["invented-trial"]):
            proposed = self.proposal(2)
            proposed["evidence_trial_ids"] = evidence
            self.error("INVALID_EVIDENCE", lambda: self.engine.submit(self.cid, "bad", proposed))
        for extra in ({"score": 0}, {"code": "anything"}, {"dataset_id": "changed"}, {"workspace": "../outside"}):
            request = {"schema_version": "0.1", "action": "submit_proposal", "request_id": "bad",
                       "campaign_id": self.cid, "proposal": self.proposal(2) | extra}
            reply = handle_request(request, self.root)
            self.assertFalse(reply["ok"])
            self.assertEqual(reply["error"]["code"], "INVALID_REQUEST")
        self.assertEqual(self.engine.status(self.cid)["budget"]["consumed_trials"], 1)

    def test_idempotent_retry_after_new_observations_and_conflicting_proposal(self):
        first_proposal = self.proposal()
        first = self.engine.submit(self.cid, "first", first_proposal)
        self.engine.submit(self.cid, "second", self.proposal(2))
        self.assertEqual(first, self.engine.submit(self.cid, "first", first_proposal))
        changed = copy.deepcopy(first_proposal)
        changed["expected_effect"] = "A different claim under the same request is a conflict."
        self.error("IDEMPOTENCY_CONFLICT", lambda: self.engine.submit(self.cid, "first", changed))
        self.assertEqual(self.engine.status(self.cid)["budget"]["consumed_trials"], 2)

    def test_running_duplicate_and_new_request_do_not_train_twice(self):
        proposed = self.proposal()
        entered, release = threading.Event(), threading.Event()
        original = training.train
        results = []
        def slow(*args):
            entered.set()
            if not release.wait(10):
                raise RuntimeError("test worker release timeout")
            return original(*args)
        with patch("autoresearch.training.train", side_effect=slow) as mocked:
            thread = threading.Thread(target=lambda: results.append(self.engine.submit(self.cid, "first", proposed)))
            thread.start()
            self.assertTrue(entered.wait(10))
            try:
                retry = Engine(self.root).submit(self.cid, "first", proposed)
                self.assertEqual(retry["status"], "running")
                self.error("BUSY", lambda: Engine(self.root).submit(self.cid, "other", proposed))
            finally:
                release.set()
                thread.join(10)
        self.assertFalse(thread.is_alive())
        self.assertEqual(mocked.call_count, 1)
        self.assertEqual(retry["trial_id"], results[0]["trial_id"])

    def test_pause_resume_preserves_proposal_and_dataset_change_fails_before_reservation(self):
        first = self.engine.submit(self.cid, "first", self.proposal())
        self.engine.pause(self.cid)
        next_proposal = self.proposal(2)
        self.error("CAMPAIGN_NOT_ACTIVE", lambda: self.engine.submit(self.cid, "second", next_proposal))
        fresh = Engine(self.root)
        self.assertEqual(fresh.status(self.cid)["trials"][0]["proposal"], first["proposal"])
        fresh.pause(self.cid, False)
        proposal = self.proposal(2)
        original = fresh.status(self.cid)["dataset"]
        with patch("autoresearch.datasets.descriptor", return_value=original | {"data_sha256": "0"*64}):
            self.error("DATASET_CHANGED", lambda: fresh.submit(self.cid, "second", proposal))
        self.assertEqual(fresh.status(self.cid)["budget"]["consumed_trials"], 1)
        self.assertEqual(fresh.submit(self.cid, "second", proposal)["status"], "accepted")

    def test_failed_proposal_is_durable_and_budget_is_consumed(self):
        proposed = self.proposal()
        with patch("autoresearch.training.train", side_effect=RuntimeError("test failure")):
            failed = self.engine.submit(self.cid, "failure", proposed)
        self.assertEqual(failed["status"], "failed")
        self.assertEqual(failed, Engine(self.root).submit(self.cid, "failure", proposed))
        self.assertEqual(self.engine.status(self.cid)["budget"]["consumed_trials"], 1)
        self.assertIn(failed["trial_id"], self.proposal()["evidence_trial_ids"])

    def test_report_uses_actual_metrics_and_verifies_artifacts(self):
        trial = self.engine.submit(self.cid, "first", self.proposal())
        report = build_report(self.engine, self.cid)
        self.assertEqual(report["state"]["trials"][0]["metrics"], trial["metrics"])
        self.assertTrue(report["artifact_integrity"][0]["verified"])
        self.assertIn(trial["proposal"]["hypothesis"], report["markdown"])
        paths = write_report(self.engine, self.cid)
        self.assertEqual(json.loads(Path(paths["json"]).read_text("utf-8")), report)
        (self.root/trial["model_artifact"]).write_text("{}", encoding="utf-8")
        self.error("ARTIFACT_CHANGED", lambda: build_report(self.engine, self.cid))

    def test_fixture_report_does_not_claim_external_agent_participation(self):
        cid = self.engine.create("fixture-report", "Fixed engineering policy")["campaign_id"]
        self.engine.step(cid, "fixture-first")
        report = build_report(self.engine, cid)
        self.assertIn("固定工程策略生成候选", report["markdown"])
        self.assertNotIn("本策略约定由外部研究 Agent", report["markdown"])
        self.assertNotIn("proposal", report["state"]["trials"][0])

    def test_public_materials_training_and_input_protocol_keep_identity(self):
        create = {"schema_version": "0.1", "request_id": "steel", "action": "create_campaign",
                  "goal": "Materials benchmark", "max_trials": 2, "dataset_id": "matbench-steels-v1", "policy_kind": AGENT_POLICY}
        reply = handle_request(create, self.root)
        self.assertTrue(reply["ok"])
        cid = reply["result"]["campaign_id"]
        observation = self.engine.observe(cid)
        proposal = self.proposal()
        proposal["observation_sha256"] = observation["observation_sha256"]
        result = self.engine.submit(cid, "steel-first", proposal)
        self.assertEqual(result["status"], "accepted")
        artifact = json.loads((self.root/result["model_artifact"]).read_text("utf-8"))
        self.assertEqual(artifact["training_rows"], 187)
        self.assertEqual(artifact["evidence_type"], "public_materials_benchmark")
        self.assertEqual(artifact["data_sha256"], observation["dataset"]["data_sha256"])
        self.assertEqual(self.engine.finalize(cid)["test_rows"], 63)
        self.assertEqual(self.engine.status(cid)["scientific_status"], "benchmark_only")

    def test_old_sqlite_schema_migrates_without_changing_legacy_idempotency(self):
        legacy_root = self.root / "legacy"
        legacy_root.mkdir()
        con = sqlite3.connect(legacy_root/"research.sqlite3")
        con.executescript("""
          CREATE TABLE campaigns(id TEXT PRIMARY KEY,request_id TEXT UNIQUE,fingerprint TEXT,goal TEXT,
            max_trials INTEGER,status TEXT,best_trial_id TEXT,final_json TEXT,created REAL);
          CREATE TABLE trials(id TEXT PRIMARY KEY,campaign_id TEXT,request_id TEXT,fingerprint TEXT,
            ordinal INTEGER,candidate_json TEXT,reason TEXT,status TEXT,result_json TEXT,created REAL);
        """)
        fp = fingerprint({"goal": "Legacy", "max_trials": 3, "dataset_id": DATASET_ID, "protocol": PROTOCOL})
        con.execute("INSERT INTO campaigns VALUES(?,?,?,?,?,'active',NULL,NULL,0)", ("legacy", "old-create", fp, "Legacy", 3))
        con.commit()
        con.close()
        migrated = Engine(legacy_root)
        self.assertEqual(migrated.create("old-create", "Legacy")["campaign_id"], "legacy")
        self.assertEqual(migrated.status("legacy")["policy_kind"], FIXTURE_POLICY)
        self.assertEqual(migrated.step("legacy", "first")["status"], "accepted")

    def test_cli_utf8_chinese_protocol_on_gbk_host_and_invalid_bytes(self):
        command = [sys.executable, "-m", "autoresearch", "tool", "--workspace", str(self.root)]
        request = {"schema_version": "0.1", "action": "create_campaign", "request_id": "chinese",
                   "goal": "材料成分与屈服强度预测", "policy_kind": AGENT_POLICY}
        env = os.environ | {"PYTHONIOENCODING": "gbk"}
        result = subprocess.run(command, input=json.dumps(request, ensure_ascii=False).encode("utf-8"),
                                capture_output=True, env=env, timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout.decode("utf-8"))
        self.assertEqual(json.loads(result.stdout)["result"]["goal"], request["goal"])
        invalid = subprocess.run(command, input=b"\xff", capture_output=True, env=env, timeout=30)
        self.assertEqual(invalid.returncode, 2)
        self.assertEqual(json.loads(invalid.stdout)["error"]["code"], "INVALID_REQUEST")


if __name__ == "__main__":
    unittest.main()
