"""Trusted coordination contracts, not model-agent or scientific validation."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
import threading
import unittest
from unittest.mock import patch

from autoresearch.agent_tasks import AgentTaskLedger
from autoresearch.contracts import ResearchError, fingerprint


PROJECT = {"project_id": "project-frozen", "source_snapshot_sha256": "a" * 64,
           "state_snapshot_sha256": "b" * 64}
SOURCE = {"source_id": "source-1", "sha256": "c" * 64, "locator": "saved-action-1:rows[0:10]"}


def task(task_id="analysis", dependencies=None, attempts=1, value=1, effort=1):
    return {"task_id": task_id, "title": "Read supplied observations", "objective": "Analyze frozen results",
            "user_value": "Understand uncertainty", "workstream": "evidence", "owner": "evidence_analyst",
            "dependencies": dependencies or [], "input_snapshot": PROJECT["state_snapshot_sha256"],
            "source_refs": [deepcopy(SOURCE)], "allowed_files": ["supplied snapshot only"], "prohibited_files": ["native ledgers"],
            "interface_contract": "Return analysis only", "acceptance_criteria": ["Preserve uncertainty"],
            "tests": [], "benchmark_ids": [], "budget": {"attempt_limit": attempts, "model_requests": 0, "tool_calls": 0, "fits": 0},
            "runtime": {"mode": "delegated_analysis", "timeout_seconds": 30}, "risk_class": "trusted_analysis",
            "expected_artifacts": ["analysis reference"], "docs_to_update": [], "expected_value": value, "estimated_effort": effort}


def result(task_id="analysis"):
    return {"task_id": task_id, "role": "evidence_analyst", "status": "analysis_complete", "proposal": {"summary": "Scoped analysis"},
            "evidence_refs": [deepcopy(SOURCE)], "tool_requests": [], "artifact_refs": [], "metrics": {"covered_records": 10},
            "uncertainty": ["Supplied evidence does not establish causality"], "limitations": ["No independent domain review"],
            "cost_usage": {"tokens": None, "amount": None, "currency": None, "usage_status": "unknown"},
            "next_actions": ["Host reviews the saved analysis"]}


class AgentTaskTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.ledger = AgentTaskLedger(self.root / "new-experiment")

    def assert_code(self, code, call, *args, **kwargs):
        with self.assertRaises(ResearchError) as caught:
            call(*args, **kwargs)
        self.assertEqual(caught.exception.code, code)

    def plan(self, tasks=None, policy=None):
        return self.ledger.plan("plan", PROJECT, [task()] if tasks is None else tasks, policy)

    def complete(self, task_id="analysis", agent_id="agent-1", prefix="first"):
        claim = self.ledger.claim(prefix + "-claim", agent_id, task_id)
        self.ledger.submit(prefix + "-submit", task_id, agent_id, claim["attempt"], result(task_id))
        return self.ledger.reconcile(prefix + "-review", task_id, "completed", "Host accepted scoped analysis", expected_attempt=claim["attempt"], result_sha256=fingerprint(result(task_id)))

    def test_plan_freeze_and_exact_replay_after_reopen_and_transitions(self):
        planned = self.plan()
        claim = self.ledger.claim("claim", "agent-1")
        submitted = self.ledger.submit("submit", "analysis", "agent-1", 1, result())
        reconciled = self.ledger.reconcile("review", "analysis", "completed", "Accepted analysis", expected_attempt=1, result_sha256=fingerprint(result()))
        reopened = AgentTaskLedger(self.ledger.root)
        self.assertEqual(reopened.plan("plan", PROJECT, [task()]), planned)
        self.assertEqual(reopened.claim("claim", "agent-1"), claim)
        self.assertEqual(reopened.submit("submit", "analysis", "agent-1", 1, result()), submitted)
        self.assertEqual(reopened.reconcile("review", "analysis", "completed", "Accepted analysis", expected_attempt=1, result_sha256=fingerprint(result())), reconciled)
        self.assertEqual(reopened.status()["attempts_used"], 1)
        self.assertEqual(len(reopened.status()["receipts"]), 4)
        self.assert_code("IDEMPOTENCY_CONFLICT", reopened.claim, "claim", "another-agent")
        self.assert_code("IDEMPOTENCY_CONFLICT", reopened.reconcile, "submit", "analysis", "completed", "Changed command", expected_attempt=1, result_sha256=fingerprint(result()))
        self.assert_code("PLAN_FROZEN", reopened.plan, "new-plan", {**PROJECT, "project_id": "another"}, [task()])

    def test_dependency_requires_host_reconciliation_and_precise_source_locator(self):
        self.plan([task(), task("dependent", ["analysis"])])
        self.assert_code("TASK_NOT_READY", self.ledger.claim, "early", "agent-1", "dependent")
        self.ledger.claim("claim", "agent-1", "analysis")
        wrong = result()
        wrong["evidence_refs"][0]["locator"] = "unsupplied selection"
        self.assert_code("SOURCE_MISMATCH", self.ledger.submit, "bad-locator", "analysis", "agent-1", 1, wrong)
        self.ledger.submit("submit", "analysis", "agent-1", 1, result())
        self.assertFalse(any(t["runnable"] for t in self.ledger.status()["tasks"]))
        self.assert_code("CLAIM_CONFLICT", self.ledger.claim, "before-review", "agent-2", "dependent")
        self.ledger.reconcile("review", "analysis", "completed", "Host accepted", expected_attempt=1, result_sha256=fingerprint(result()))
        self.assertEqual(self.ledger.claim("next", "agent-2")["task_id"], "dependent")

    def test_unknown_never_reassigned_and_only_original_late_result_resolves(self):
        self.plan([task(attempts=3), task("other")])
        self.ledger.claim("claim", "agent-1")
        unknown = self.ledger.reconcile("uncertain", "analysis", "unknown", "Host cannot establish dispatch outcome", expected_attempt=1)
        reopened = AgentTaskLedger(self.ledger.root)
        self.assert_code("CLAIM_CONFLICT", reopened.claim, "different-id", "agent-2")
        self.assert_code("CLAIM_MISMATCH", reopened.submit, "steal", "analysis", "agent-2", 1, result())
        self.assert_code("CLAIM_MISMATCH", reopened.submit, "wrong-attempt", "analysis", "agent-1", 2, result())
        reopened.submit("original-late", "analysis", "agent-1", 1, result())
        reopened.reconcile("review", "analysis", "completed", "Original late analysis reviewed", expected_attempt=1, result_sha256=fingerprint(result()))
        self.assertEqual(reopened.reconcile("uncertain", "analysis", "unknown", "Host cannot establish dispatch outcome", expected_attempt=1), unknown)
        self.assertEqual(reopened.status()["attempts_used"], 1)
        self.assertEqual(reopened.claim("next", "agent-2")["task_id"], "other")

    def test_task_attempt_cap_rejection_and_shared_cap_do_not_reset(self):
        self.plan([task(attempts=2), task("other")], {"mode": "static", "max_parallel": 1, "attempt_limit": 2})
        for attempt in (1, 2):
            claim = self.ledger.claim("claim-" + str(attempt), "agent-1", "analysis")
            self.assertEqual(claim["attempt"], attempt)
            self.ledger.submit("submit-" + str(attempt), "analysis", "agent-1", attempt, result())
            self.ledger.reconcile("reject-" + str(attempt), "analysis", "rejected", "Insufficient interpretation", expected_attempt=attempt, result_sha256=fingerprint(result()))
        self.assertEqual(self.ledger.status()["attempts_used"], 2)
        self.assert_code("ATTEMPT_LIMIT", self.ledger.claim, "new-id", "agent-2", "other")
        self.assertEqual(self.ledger.status()["tasks"][0]["status"], "rejected")
        second = AgentTaskLedger(self.root / "task-cap")
        second.plan("plan", PROJECT, [task()], {"mode": "single", "max_parallel": 1, "attempt_limit": 10})
        second.claim("claim", "agent-1")
        second.submit("submit", "analysis", "agent-1", 1, result())
        second.reconcile("review", "analysis", "rejected", "Insufficient", expected_attempt=1, result_sha256=fingerprint(result()))
        self.assert_code("TASK_NOT_READY", second.claim, "new-id", "agent-2", "analysis")

    def test_concurrent_claims_serialize_without_duplicate_attempt(self):
        self.plan()
        barrier = threading.Barrier(2)

        def claim(agent_id):
            barrier.wait()
            try:
                return AgentTaskLedger(self.ledger.root).claim("claim-" + agent_id, agent_id)
            except ResearchError as error:
                return error.code
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(claim, ("agent-1", "agent-2")))
        self.assertEqual(sum(isinstance(item, dict) for item in results), 1)
        self.assertIn("CLAIM_CONFLICT", results)
        self.assertEqual(self.ledger.status()["attempts_used"], 1)

    def test_concurrent_exact_request_returns_one_identical_receipt(self):
        self.plan()
        with ThreadPoolExecutor(max_workers=2) as pool:
            receipts = list(pool.map(lambda _: AgentTaskLedger(self.ledger.root).claim("same-request", "agent-1"), range(2)))
        self.assertEqual(receipts[0], receipts[1])
        self.assertEqual(self.ledger.status()["attempts_used"], 1)

    def test_dynamic_selects_positive_value_ready_tasks_only(self):
        self.plan([task("zero", value=0), task("low", value=1, effort=10), task("high", value=2), task("blocked-high", ["high"], value=100)],
                  {"mode": "dynamic", "max_parallel": 2, "attempt_limit": 4})
        self.assert_code("TASK_NOT_READY", self.ledger.claim, "zero", "agent-z", "zero")
        self.assertEqual(self.ledger.claim("first", "agent-1")["task_id"], "high")
        self.assertEqual(self.ledger.claim("second", "agent-2")["task_id"], "low")
        self.assert_code("CLAIM_CONFLICT", self.ledger.claim, "third", "agent-3")
        self.assertEqual(self.ledger.status()["policy"]["max_parallel"], 2)

    def test_single_default_static_order_waiting_receipt_and_no_usage(self):
        self.plan([task("zero", value=0)])
        self.assertEqual(self.ledger.status()["policy"]["mode"], "single")
        self.complete("zero")
        waited = self.ledger.claim("waiting", "agent-1")
        self.assertEqual(waited["status"], "waiting")
        self.assertEqual(self.ledger.claim("waiting", "agent-1"), waited)
        self.assertEqual(self.ledger.status()["attempts_used"], 1)
        self.assertEqual(self.ledger.status()["native_budget_authority"], "none")

    def test_dag_invalid_nodes_cycles_duplicate_and_state_mismatch_are_rejected(self):
        cases = [[task("a", ["missing"])], [task("a", ["a"])], [task("a", ["b"]), task("b", ["a"])], [task("a"), task("a")],
                 [task("a"), task("b", ["a", "a"])]]
        for index, tasks in enumerate(cases):
            with self.subTest(index=index):
                ledger = AgentTaskLedger(self.root / str(index))
                self.assert_code("INVALID_DAG", ledger.plan, "plan", PROJECT, tasks)
                self.assertFalse(ledger.root.exists())
        mismatch = task()
        mismatch["input_snapshot"] = "d" * 64
        self.assert_code("PROJECT_MISMATCH", self.ledger.plan, "plan", PROJECT, [mismatch])

    def test_untrusted_runtime_budget_extra_keys_and_excess_parallel_are_rejected(self):
        changes = [("budget", {"attempt_limit": 1, "model_requests": 1, "tool_calls": 0, "fits": 0}),
                   ("runtime", {"mode": "arbitrary_python", "timeout_seconds": 10}), ("risk_class", "untrusted"),
                   ("permission", "write evaluator"), ("expected_value", True)]
        for key, value in changes:
            changed = task()
            changed[key] = value
            with self.subTest(key=key):
                self.assert_code("INVALID_REQUEST", self.ledger.plan, "bad-plan", PROJECT, [changed])
        self.assert_code("INVALID_REQUEST", self.ledger.plan, "bad-parallel", PROJECT, [task()],
                         {"mode": "dynamic", "max_parallel": 3, "attempt_limit": 1})

    def test_agent_result_cannot_modify_controls_or_claim_scientific_status(self):
        self.plan()
        self.ledger.claim("claim", "agent-1")
        changes = [("evaluator", "replace truth"), ("policy", {"fits": 999}), ("budget", {"fits": 999}),
                   ("status", "verified"), ("tool_requests", [{"command": "python"}]), ("role", "another-role"),
                   ("cost_usage", {"tokens": 0, "amount": 0, "currency": None, "usage_status": "unknown"}),
                   ("metrics", {"invalid": float("nan")}), ("proposal", "not an object")]
        for index, (key, value) in enumerate(changes):
            changed = result()
            changed[key] = value
            with self.subTest(key=key):
                with self.assertRaises(ResearchError):
                    self.ledger.submit("bad-" + str(index), "analysis", "agent-1", 1, changed)
        valid = result()
        valid["proposal"] = {"budget": "opaque untrusted proposal text, never authority"}
        self.ledger.submit("submit", "analysis", "agent-1", 1, valid)
        state = self.ledger.status()
        self.assertEqual(state["tasks"][0]["spec"]["budget"]["fits"], 0)
        self.assertIsNone(state["tasks"][0]["attempts"][0]["result"]["cost_usage"]["tokens"])

    def test_oversized_and_nonfinite_payloads_do_not_consume_attempts(self):
        self.plan()
        self.ledger.claim("claim", "agent-1")
        oversized = result()
        oversized["proposal"] = {"text": "x" * 65536}
        self.assert_code("INVALID_REQUEST", self.ledger.submit, "too-large", "analysis", "agent-1", 1, oversized)
        self.assertEqual(self.ledger.status()["tasks"][0]["status"], "claimed")
        self.assertEqual(self.ledger.status()["attempts_used"], 1)

    def test_fresh_workspace_guards_and_old_case_bytes_unchanged(self):
        for name in ("project.sqlite", "workbench.sqlite"):
            protected = self.root / name.replace(".", "-")
            protected.mkdir()
            original = protected / name
            original.write_bytes(b"protected original database bytes")
            before = hashlib.sha256(original.read_bytes()).hexdigest()
            self.assert_code("PROTECTED_WORKSPACE", AgentTaskLedger, protected / "nested")
            self.assert_code("PROTECTED_WORKSPACE", AgentTaskLedger, protected)
            self.assertEqual(hashlib.sha256(original.read_bytes()).hexdigest(), before)
            self.assertEqual(list(protected.iterdir()), [original])
        unrelated = self.root / "unrelated"
        unrelated.mkdir()
        (unrelated / "other.sqlite").write_bytes(b"not ours")
        self.assert_code("PROTECTED_WORKSPACE", AgentTaskLedger, unrelated)
        impostor = self.root / "impostor"
        impostor.mkdir()
        with sqlite3.connect(impostor / "agent_tasks.sqlite") as con:
            con.execute("CREATE TABLE unrelated(id)")
        self.assert_code("LEDGER_INVALID", AgentTaskLedger(impostor).plan, "plan", PROJECT, [task()])
        link = self.root / "redirect"
        link.symlink_to(unrelated, target_is_directory=True)
        self.assert_code("UNSAFE_PATH", AgentTaskLedger, link / "nested")

    def test_status_is_readonly_and_unknown_has_no_automatic_expiry(self):
        self.plan()
        self.ledger.claim("claim", "agent-1")
        self.ledger.reconcile("unknown", "analysis", "unknown", "No definitive result", expected_attempt=1)
        before = self.ledger.db.read_bytes()
        first = self.ledger.status()
        second = AgentTaskLedger(self.ledger.root).status()
        self.assertEqual(first, second)
        self.assertEqual(self.ledger.db.read_bytes(), before)
        self.assertEqual(first["tasks"][0]["status"], "unknown")
        self.assertFalse(first["tasks"][0]["runnable"])

    def test_delayed_host_review_cannot_approve_a_newer_attempt(self):
        self.plan([task(attempts=2)])
        self.ledger.claim("claim-1", "agent-1")
        original = self.ledger.submit("submit-1", "analysis", "agent-1", 1, result())
        review_captured, newer_submitted = threading.Event(), threading.Event()

        def stale_review():
            review_captured.set()
            self.assertTrue(newer_submitted.wait(5))
            return self.ledger.reconcile("late-approve", "analysis", "completed", "Delayed review of attempt one",
                                         expected_attempt=1, result_sha256=original["result_sha256"])
        with ThreadPoolExecutor(max_workers=1) as pool:
            delayed = pool.submit(stale_review)
            self.assertTrue(review_captured.wait(5))
            rejected = self.ledger.reconcile("reject-1", "analysis", "rejected", "Need revised analysis",
                                             expected_attempt=1, result_sha256=original["result_sha256"])
            self.ledger.claim("claim-2", "agent-2")
            changed = result()
            changed["proposal"] = {"summary": "A different second analysis"}
            current = self.ledger.submit("submit-2", "analysis", "agent-2", 2, changed)
            newer_submitted.set()
            with self.assertRaises(ResearchError) as caught:
                delayed.result(timeout=5)
            self.assertEqual(caught.exception.code, "RECONCILIATION_CONFLICT")
        self.assertEqual(self.ledger.status()["tasks"][0]["status"], "submitted")
        self.assert_code("RECONCILIATION_CONFLICT", self.ledger.reconcile, "wrong-result", "analysis", "completed", "Wrong hash",
                         expected_attempt=2, result_sha256=original["result_sha256"])
        self.assertEqual(self.ledger.reconcile("reject-1", "analysis", "rejected", "Need revised analysis",
                                               expected_attempt=1, result_sha256=original["result_sha256"]), rejected)
        self.assert_code("IDEMPOTENCY_CONFLICT", self.ledger.reconcile, "reject-1", "analysis", "rejected", "Need revised analysis",
                         expected_attempt=2, result_sha256=current["result_sha256"])
        self.ledger.reconcile("approve-2", "analysis", "completed", "Current result reviewed",
                              expected_attempt=2, result_sha256=current["result_sha256"])

    def test_status_state_and_receipts_share_one_snapshot_during_commit(self):
        self.plan()
        # WAL permits the writer's commit while the status read transaction is
        # open; a missing BEGIN would mix the old state with new receipts.
        with sqlite3.connect(self.ledger.db) as con:
            con.execute("PRAGMA journal_mode=WAL")
        snapshot_read, writer_committed = threading.Event(), threading.Event()
        real_connect = sqlite3.connect

        class Cursor:
            def __init__(self, cursor):
                self.cursor = cursor

            def fetchone(self):
                saved = self.cursor.fetchone()
                snapshot_read.set()
                if not writer_committed.wait(5):
                    raise AssertionError("Writer did not commit during the status read")
                return saved

        class ReadConnection:
            def __init__(self, con):
                self.con = con

            def execute(self, sql, *args):
                cursor = self.con.execute(sql, *args)
                return Cursor(cursor) if sql.startswith("SELECT snapshot") else cursor

            def __getattr__(self, name):
                return getattr(self.con, name)

        def connect(database, *args, **kwargs):
            con = real_connect(database, *args, **kwargs)
            return ReadConnection(con) if "?mode=ro" in str(database) else con

        def write():
            self.assertTrue(snapshot_read.wait(5))
            claimed = AgentTaskLedger(self.ledger.root).claim("concurrent-claim", "agent-1")
            writer_committed.set()
            return claimed
        with patch("autoresearch.agent_tasks.sqlite3.connect", side_effect=connect):
            with ThreadPoolExecutor(max_workers=1) as pool:
                writer = pool.submit(write)
                snapshot = self.ledger.status()
                self.assertEqual(writer.result(timeout=5)["state_version"], 1)
        self.assertEqual(snapshot["state_version"], 0)
        self.assertEqual(len(snapshot["receipts"]), 1)
        self.assertEqual(snapshot["tasks"][0]["status"], "ready")
        self.assertEqual(self.ledger.status()["state_version"], 1)


if __name__ == "__main__":
    unittest.main()
