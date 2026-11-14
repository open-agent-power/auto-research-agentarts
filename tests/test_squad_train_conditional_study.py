"""Synthetic driver checks only; never use the real S054 source or model."""
import base64
import hashlib
import importlib.util
import json
from pathlib import Path
import random
import sqlite3
import tempfile
import time
import unittest
from unittest.mock import patch

from autoresearch.contracts import canonical
from autoresearch import staged_relevance_adapter as staged
from autoresearch.local_workbench import LocalWorkbench
from autoresearch.project_controller import ProjectController


SCRIPT = Path(__file__).resolve().parents[1] / "scripts/run_squad_train_conditional_study.py"
spec = importlib.util.spec_from_file_location("s054_driver_fixture", SCRIPT)
driver = importlib.util.module_from_spec(spec)
spec.loader.exec_module(driver)


class S054DriverTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.inputs = self.root / "input"
        (self.inputs / "development").mkdir(parents=True)
        (self.inputs / "private").mkdir()
        self.workspace = self.root / "pin/runs" / driver.STUDY
        self.claim = self.root / "claims" / (driver.STUDY + ".json")
        self.enterContext(patch.object(driver, "INPUT", self.inputs))
        self.enterContext(patch.object(driver, "WORKSPACE", self.workspace))
        self.enterContext(patch.object(driver, "CLAIM", self.claim))
        self.enterContext(patch.object(driver, "current_owner", return_value="synthetic-fixture-owner"))
        def put(name, raw):
            path = self.inputs / name
            path.write_bytes(raw)
            return {"path":name,"bytes":len(raw),"sha256":hashlib.sha256(raw).hexdigest()}
        row = lambda value: (canonical(value) + "\n").encode()
        signed = self._testMethodName in {"test_positive_complete_and_expired_terminal_replay", "test_negative_wait_retains_saved_summary"}
        positive = self._testMethodName == "test_positive_complete_and_expired_terminal_replay"
        if signed:
            rng = random.Random(108)
            words = ["amber", "blue", "cyan", "denim", "ecru"]
            docs = [{"_id":str(i),"title":"","text":" ".join(w for w in words for _ in range(rng.randint(0,5))),"metadata":{}}
                    for i in range(40)]
            docs += [{"_id":str(i),"title":"","text":"filler","metadata":{}} for i in range(40,2200)]
        else:
            docs = [{"_id":"doc-"+str(i),"title":"","text":"apple","metadata":{}} for i in range(2200)]
        corpus = b"".join(row(d) for d in docs)
        selection = {"splits":{name:[{"qid":name+str(i),"document_id":("1" if name == "dev" else "11" if positive else "20") if signed else "doc-0"} for i in range(100)]
                               for name in ("dev","validation","final")}}
        dev = selection["splits"]["dev"] + selection["splits"]["validation"]
        queries = b"".join(row({"_id":x["qid"],"text":("amber" if x["qid"].startswith("dev") else "amber blue cyan") if signed else "zebra","metadata":{}}) for x in dev)
        def qrels(items):
            return ("query-id\tcorpus-id\tscore\n" + "".join(x["qid"]+"\t"+x["document_id"]+"\t1\n" for x in items)).encode()
        final_queries = b"".join(row({"_id":x["qid"],"text":"amber blue cyan" if signed else "zebra","metadata":{}}) for x in selection["splits"]["final"])
        holdout = {"schema_version":"retrieval-holdout-v1","corpus_sha256":hashlib.sha256(corpus).hexdigest(),
                   "queries_jsonl":final_queries.decode(),"qrels_tsv":qrels(selection["splits"]["final"]).decode()}
        assets = [put("development/corpus.jsonl",corpus),put("development/queries.jsonl",queries),
                  put("development/qrels.tsv",qrels(dev)),put("development/license.md",b"Synthetic fixture.\n")]
        source = put("train-v1.1.json",b"Synthetic source bytes, not SQuAD.")
        entries = {"source":source,"source_head":put("source-head.txt",b"fixture"),
                   "official_site":put("official-site.html",b"fixture"),"derivation_script":put("prepare_source.py",b"fixture"),
                   "corpus_selection":put("corpus-selection.json",canonical({"selected_document_ids":[d["_id"] for d in docs]}).encode()),
                   "question_selection":put("question-selection.json",canonical(selection).encode()),
                   "holdout":put("private/holdout.json",canonical(holdout).encode())}
        license_file = put("cc-by-sa-4.0-legalcode.html",b"Synthetic license fixture.")
        helper_sha = "a"*64
        manifest = {"schema_version":"s054-fixed-source-preparation-v1","status":"prepared_only_protocol_not_frozen_no_project",
                    "created_at_utc":"synthetic","source_url":"urn:synthetic", **entries,
                    "development_assets":assets,"license":{"legalcode":license_file},
                    "source_data_reused":{"script_sha256":helper_sha},"split_counts":{"dev":100,"validation":100,"final":100},
                    "document_count":2200}
        manifest_raw = canonical(manifest).encode()
        (self.inputs / "fixed-input-manifest.json").write_bytes(manifest_raw)
        self.enterContext(patch.object(driver, "INPUT_MANIFEST_SHA", hashlib.sha256(manifest_raw).hexdigest()))
        self.protocol = {"input":{"manifest_sha256":driver.INPUT_MANIFEST_SHA,"source_url":"urn:synthetic",
          "source_sha256":source["sha256"],"source_bytes":source["bytes"],
          "corpus_selection_sha256":entries["corpus_selection"]["sha256"],
          "question_selection_sha256":entries["question_selection"]["sha256"],"development_assets":assets,
          "holdout":entries["holdout"],"source_data_helper_sha256":helper_sha},
          "selection":{"splits":{"dev":100,"validation":100,"final":100}},
          "hypothesis":{"branches":{"condition_met":{"kind":"method","method_id":staged.AUDIT_TOOL_ID},
                                     "condition_not_met":{"kind":"wait"}}},"limitations":["Synthetic engineering fixture only."]}
        self.identity = {"source_commit":"a"*40,"protocol_sha256":"b"*64,"driver_sha256":"c"*64,
                         "project_code_identity":driver.project_identity()}

    def test_prepare_only_creates_no_project_and_original_claim_is_exclusive(self):
        result = driver.prepare(self.identity, self.protocol)
        self.assertEqual(result["status"], "prepared")
        self.assertFalse((self.workspace / "project-seed").exists())
        self.assertFalse((self.workspace / "manager").exists())
        driver.verify_prepared(self.identity, self.protocol)
        other = self.root / "another-pin/runs" / driver.STUDY
        with patch.object(driver, "WORKSPACE", other), self.assertRaises(FileExistsError):
            driver.prepare(self.identity, self.protocol)
        self.assertFalse(other.exists())

    def test_zero_wait_and_expired_terminal_replay_do_not_add_actions(self):
        driver.prepare(self.identity, self.protocol)
        result = driver.run(self.identity, self.protocol, resume=False)
        self.assertEqual((result["feedback"]["value"], result["feedback"]["outcome"]), (0, "condition_not_met"))
        self.assertEqual((result["final_status"], result["final_summary"]), ("unmeasured", None))
        self.assertEqual(set(result["primary"]["paired_summary"]["splits"]), {"dev", "validation"})
        self.assertIsInstance(result["primary"]["adverse_query_count"], int)
        self.assertEqual(len(result["actions"]), 1)
        self.assertEqual((result["budget"]["local_tool_calls_used"], result["budget"]["new_model_requests"], result["budget"]["new_fits"]), (1,0,0))
        before = (self.workspace / "manager/workbench.sqlite").read_bytes()
        with patch.object(driver.time, "time", return_value=time.time() + 10000):
            replay = driver.terminal_replay(self.identity, self.protocol)
        self.assertEqual(replay, result)
        self.assertEqual((self.workspace / "manager/workbench.sqlite").read_bytes(), before)

    def test_changed_prepared_source_and_missing_database_stop_without_recreate(self):
        driver.prepare(self.identity, self.protocol)
        path = self.workspace / "development/qrels.tsv"
        path.write_bytes(path.read_bytes() + b"tamper")
        with self.assertRaisesRegex(RuntimeError, "changed"):
            driver.verify_prepared(self.identity, self.protocol)
        self.assertFalse((self.workspace / "manager").exists())

    def test_positive_complete_and_expired_terminal_replay(self):
        driver.prepare(self.identity, self.protocol)
        result = driver.run(self.identity, self.protocol, resume=False)
        self.assertEqual((result["feedback"]["value"], result["feedback"]["outcome"]), (1, "condition_met"))
        self.assertEqual(result["final_status"], "measured")
        self.assertEqual(set(result["primary"]["paired_summary"]["splits"]), {"dev", "validation"})
        self.assertIsInstance(result["final_summary"], dict)
        self.assertEqual([a["command"] for a in result["actions"]],
                         [staged.TOOL_ID, staged.AUDIT_TOOL_ID, "research.relevance-final-evaluation"])
        self.assertEqual(result["budget"]["local_tool_calls_used"], 3)
        self.assertEqual(set(result["report_manifest"]["files"]), {"report.json","report.md","report.pdf","input.json"})
        before = (self.workspace / "manager/workbench.sqlite").read_bytes()
        with patch.object(driver.time, "time", return_value=time.time() + 10000):
            self.assertEqual(driver.terminal_replay(self.identity, self.protocol), result)
        self.assertEqual((self.workspace / "manager/workbench.sqlite").read_bytes(), before)

    def test_negative_wait_retains_saved_summary(self):
        driver.prepare(self.identity, self.protocol)
        result = driver.run(self.identity, self.protocol, resume=False)
        self.assertEqual((result["feedback"]["value"], result["feedback"]["outcome"]), (-1, "condition_not_met"))
        self.assertEqual((result["final_status"], result["final_summary"]), ("unmeasured", None))
        self.assertEqual(result["primary"]["paired_summary"]["splits"]["validation"]
                         ["paired_candidate_minus_baseline"]["recall@20"]["mean"], -1)
        self.assertEqual(len(result["actions"]), 1)

    def test_unknown_saved_primary_waits_without_fabricated_summary_or_final(self):
        driver.prepare(self.identity, self.protocol)
        original = LocalWorkbench.continue_staged
        def corrupt_original(manager, body):
            project, _ = manager.binding()
            action = project.status()["actions"][0]
            path = project._artifact(action)
            path.write_bytes(path.read_bytes() + b"tampered")
            return original(manager, body)
        with patch.object(LocalWorkbench, "continue_staged", corrupt_original):
            result = driver.run(self.identity, self.protocol, resume=False)
        self.assertEqual((result["feedback"]["outcome"], result["feedback"]["value"]), ("unknown", None))
        self.assertEqual((result["primary"]["paired_summary"], result["primary"]["adverse_query_count"]), (None, None))
        self.assertEqual((result["final_status"], result["final_summary"]), ("unmeasured", None))
        self.assertEqual(len(result["actions"]), 1)

    def test_resume_empty_or_missing_table_database_preserves_original_bytes(self):
        driver.prepare(self.identity, self.protocol)
        started = time.time()
        driver.save_json(self.workspace / "run-start.json", {"schema_version":"s054-run-start-v1", "study_id":driver.STUDY,
            "started_unix":started,"deadline_unix":started+1800,"max_wall_seconds":1800})
        driver.save_json(self.workspace / "project-identity.json", {"project_id":"synthetic-project"})
        manager = self.workspace / "manager"
        manager.mkdir()
        database = manager / "workbench.sqlite"
        database.write_bytes(b"")
        before = database.read_bytes()
        with self.assertRaises((RuntimeError, sqlite3.Error)):
            driver.run(self.identity, self.protocol, resume=True)
        self.assertEqual(database.read_bytes(), before)
        with sqlite3.connect(database) as con:
            con.execute("CREATE TABLE metadata(key TEXT PRIMARY KEY, value TEXT NOT NULL)")
            con.execute("INSERT INTO metadata VALUES('schema_version','local-research-workbench-v1')")
        before = database.read_bytes()
        with self.assertRaisesRegex(RuntimeError, "schema"):
            driver.run(self.identity, self.protocol, resume=True)
        self.assertEqual(database.read_bytes(), before)

    def test_expired_active_window_blocks_before_project_creation(self):
        driver.prepare(self.identity, self.protocol)
        self.workspace.joinpath("run-start.json").write_bytes(canonical({"schema_version":"s054-run-start-v1",
            "study_id":driver.STUDY,"started_unix":1,"deadline_unix":1801,"max_wall_seconds":1800}).encode())
        with self.assertRaisesRegex(RuntimeError, "expired"):
            driver.deadline_check()
        self.assertFalse((self.workspace / "manager").exists())
        self.assertFalse((self.workspace / "project-seed").exists())

    def test_resume_missing_manager_database_is_never_recreated(self):
        driver.prepare(self.identity, self.protocol)
        started = time.time()
        driver.save_json(self.workspace / "run-start.json", {"schema_version":"s054-run-start-v1", "study_id":driver.STUDY,
            "started_unix":started,"deadline_unix":started+1800,"max_wall_seconds":1800})
        driver.save_json(self.workspace / "project-identity.json", {"project_id":"missing"})
        with self.assertRaisesRegex(RuntimeError, "manager database is missing"):
            driver.run(self.identity, self.protocol, resume=True)
        self.assertFalse((self.workspace / "manager/workbench.sqlite").exists())

    def test_interrupted_primary_remains_original_unknown_and_expired_resume_stops(self):
        driver.prepare(self.identity, self.protocol)
        with patch.object(ProjectController, "_dispatch", side_effect=KeyboardInterrupt("fixture interruption")):
            with self.assertRaises(KeyboardInterrupt):
                driver.run(self.identity, self.protocol, resume=False)
        manager = LocalWorkbench(self.workspace / "manager")
        project, _ = manager.binding()
        before = project.status()
        self.assertEqual(before["actions"], [])
        self.assertEqual(before["controller_requests"][-1]["status"], "prepared")
        with patch.object(ProjectController, "_dispatch", side_effect=AssertionError("never redispatch")):
            with self.assertRaisesRegex(RuntimeError, "unfinished"):
                driver.run(self.identity, self.protocol, resume=True)
            with patch.object(driver.time, "time", return_value=time.time() + 10000):
                with self.assertRaisesRegex(RuntimeError, "expired"):
                    driver.run(self.identity, self.protocol, resume=True)
            path = self.workspace / "run-start.json"
            window = json.loads(path.read_bytes()); window["deadline_unix"] += 1
            path.write_bytes(canonical(window).encode())
            with self.assertRaisesRegex(RuntimeError, "window metadata changed"):
                driver.run(self.identity, self.protocol, resume=True)
        self.assertEqual(project.status(), before)


if __name__ == "__main__":
    unittest.main()
