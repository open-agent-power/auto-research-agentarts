"""Bounded trusted analysis-task coordination; no execution or model transport.

The host attests frozen ProjectRef/source bytes and owns reconciliation. Agent
results are unverified analyses. Native project, evaluator and budget databases
are never opened. Original cloud isolation restrictions still apply.
"""
from contextlib import contextmanager
from fractions import Fraction
import json
import math
import os
from pathlib import Path
import re
import sqlite3

from .contracts import ResearchError, canonical, fingerprint, identifier


SCHEMA = "trusted-agent-tasks-v1"
DB_NAME = "agent_tasks.sqlite"
MAX_BYTES = 65536
MAX_REQUESTS = 1024
DEFAULT_POLICY = {"mode": "single", "max_parallel": 1, "attempt_limit": 64}
TASK_FIELDS = set("task_id title objective user_value workstream owner dependencies input_snapshot source_refs allowed_files prohibited_files interface_contract acceptance_criteria tests benchmark_ids budget runtime risk_class expected_artifacts docs_to_update expected_value estimated_effort".split())
RESULT_FIELDS = set("task_id role status proposal evidence_refs tool_requests artifact_refs metrics uncertainty limitations cost_usage next_actions".split())


def require(condition, code, message):
    if not condition:
        raise ResearchError(code, message)


def _object(value, keys, label):
    require(type(value) is dict and set(value) == set(keys), "INVALID_REQUEST", label + " has invalid keys.")


def _text(value, label):
    require(isinstance(value, str) and 0 < len(value.strip()) <= 4000, "INVALID_REQUEST", label + " must be bounded nonempty text.")


def _texts(value, label, nonempty=False):
    require(type(value) is list and len(value) <= 64 and (not nonempty or value), "INVALID_REQUEST", label + " must be a bounded list.")
    for item in value:
        _text(item, label)


def _number(value, label, minimum=0, positive=False):
    require(type(value) in (int, float) and abs(value) <= 1e100 and math.isfinite(value) and (value > minimum if positive else value >= minimum),
            "INVALID_REQUEST", label + " must be a finite bounded number.")


def _digest(value):
    require(isinstance(value, str) and re.fullmatch("[0-9a-f]{64}", value), "INVALID_REQUEST", "Expected SHA-256 identity.")


def _source(value):
    _object(value, ("source_id", "sha256", "locator"), "Source reference")
    identifier(value["source_id"], "source_id")
    _digest(value["sha256"])
    _text(value["locator"], "locator")


def _refs(values, nonempty=False):
    require(type(values) is list and len(values) <= 64 and (not nonempty or values), "INVALID_REQUEST", "Invalid source references.")
    for value in values:
        _source(value)
    require(len({canonical(value) for value in values}) == len(values), "INVALID_REQUEST", "Duplicate source references.")


def _project(value):
    _object(value, ("project_id", "source_snapshot_sha256", "state_snapshot_sha256"), "ProjectRef")
    identifier(value["project_id"], "project_id")
    _digest(value["source_snapshot_sha256"])
    _digest(value["state_snapshot_sha256"])


def _plan(project_ref, tasks, policy):
    _project(project_ref)
    _object(policy, DEFAULT_POLICY, "Policy")
    require(policy["mode"] in ("single", "static", "dynamic"), "INVALID_REQUEST", "Unsupported policy mode.")
    require(type(policy["max_parallel"]) is int and 1 <= policy["max_parallel"] <= 2 and
            (policy["mode"] != "single" or policy["max_parallel"] == 1), "INVALID_REQUEST", "Invalid parallel bound.")
    require(type(policy["attempt_limit"]) is int and 1 <= policy["attempt_limit"] <= 192, "INVALID_REQUEST", "Invalid coordination attempt cap.")
    require(type(tasks) is list and 1 <= len(tasks) <= 64, "INVALID_REQUEST", "Expected 1..64 tasks.")
    ids = []
    for task in tasks:
        _object(task, TASK_FIELDS, "Task")
        ids.append(identifier(task["task_id"], "task_id"))
        for key in ("title", "objective", "user_value", "workstream", "owner", "interface_contract"):
            _text(task[key], key)
        for key in ("dependencies", "allowed_files", "prohibited_files", "acceptance_criteria", "tests", "benchmark_ids", "expected_artifacts", "docs_to_update"):
            _texts(task[key], key, nonempty=key == "acceptance_criteria")
        require(task["input_snapshot"] == project_ref["state_snapshot_sha256"], "PROJECT_MISMATCH", "Task uses another state snapshot.")
        _refs(task["source_refs"], nonempty=True)
        require(task["risk_class"] == "trusted_analysis", "INVALID_REQUEST", "Only trusted analysis is supported.")
        _object(task["budget"], ("attempt_limit", "model_requests", "tool_calls", "fits"), "Task budget")
        budget = task["budget"]
        require(type(budget["attempt_limit"]) is int and 1 <= budget["attempt_limit"] <= 3 and
                all(type(budget[k]) is int and budget[k] == 0 for k in ("model_requests", "tool_calls", "fits")),
                "INVALID_REQUEST", "Task budget cannot authorize execution or models.")
        _object(task["runtime"], ("mode", "timeout_seconds"), "Runtime")
        runtime = task["runtime"]
        require(runtime["mode"] in ("trusted_local", "delegated_analysis") and
                type(runtime["timeout_seconds"]) is int and 1 <= runtime["timeout_seconds"] <= 600,
                "INVALID_REQUEST", "Unsupported runtime. Timeout is a host obligation, never an automatic retry.")
        _number(task["expected_value"], "expected_value")
        _number(task["estimated_effort"], "estimated_effort", positive=True)
    require(len(set(ids)) == len(ids), "INVALID_DAG", "Duplicate task IDs.")
    edges = {task["task_id"]: task["dependencies"] for task in tasks}
    visited, active = set(), set()

    def visit(node):
        require(node not in active, "INVALID_DAG", "Task dependencies contain a cycle.")
        if node in visited:
            return
        active.add(node)
        deps = edges[node]
        require(len(set(deps)) == len(deps) and all(dep in edges for dep in deps), "INVALID_DAG", "Unknown or duplicate dependency.")
        for dep in deps:
            visit(dep)
        active.remove(node)
        visited.add(node)
    for node in edges:
        visit(node)


def _result(task, value):
    _object(value, RESULT_FIELDS, "AgentResult")
    require(value["task_id"] == task["task_id"] and value["role"] == task["owner"], "RESULT_MISMATCH", "Task/role mismatch.")
    require(value["status"] in ("proposed", "analysis_complete", "needs_review", "failed"), "INVALID_REQUEST", "Result cannot claim scientific verification.")
    require(type(value["proposal"]) is dict and value["tool_requests"] == [], "INVALID_REQUEST", "Proposal must be data; tool execution is disabled.")
    _refs(value["evidence_refs"])
    allowed = {canonical(ref) for ref in task["source_refs"]}
    require(all(canonical(ref) in allowed for ref in value["evidence_refs"]), "SOURCE_MISMATCH", "Evidence must use supplied source/hash/locator triples.")
    require(type(value["artifact_refs"]) is list and len(value["artifact_refs"]) <= 64, "INVALID_REQUEST", "Invalid artifacts.")
    for artifact in value["artifact_refs"]:
        _object(artifact, ("artifact_id", "sha256", "locator"), "Artifact")
        identifier(artifact["artifact_id"], "artifact_id")
        _digest(artifact["sha256"])
        _text(artifact["locator"], "locator")
    require(type(value["metrics"]) is dict and len(value["metrics"]) <= 64, "INVALID_REQUEST", "Invalid metrics.")
    for key, metric in value["metrics"].items():
        _text(key, "metric name")
        _number(metric, "metric", minimum=-1e100)
    for key in ("uncertainty", "limitations", "next_actions"):
        _texts(value[key], key, nonempty=True)
    usage = value["cost_usage"]
    _object(usage, ("tokens", "amount", "currency", "usage_status"), "Cost usage")
    require(usage["usage_status"] in ("unknown", "reported"), "INVALID_REQUEST", "Invalid usage status.")
    if usage["tokens"] is not None:
        require(type(usage["tokens"]) is int and usage["tokens"] >= 0, "INVALID_REQUEST", "Invalid token count.")
    if usage["amount"] is not None:
        _number(usage["amount"], "amount")
    if usage["currency"] is not None:
        _text(usage["currency"], "currency")
    require(usage["usage_status"] != "unknown" or (usage["tokens"] is None and usage["amount"] is None),
            "INVALID_REQUEST", "Unknown usage cannot be encoded as zero.")
    require(usage["usage_status"] != "reported" or usage["tokens"] is not None or usage["amount"] is not None,
            "INVALID_REQUEST", "Reported usage requires a known measure.")


class AgentTaskLedger:
    """Host-only ledger in a fresh experiment directory, detached from native cases."""

    def __init__(self, workspace):
        self.root = Path(workspace).absolute()
        self.db = self.root / DB_NAME
        self._safe_root()

    def _safe_root(self):
        for path in (self.root, *self.root.parents):
            require(not path.is_symlink() and not getattr(path, "is_junction", lambda: False)(), "UNSAFE_PATH", "Ledger paths cannot contain links.")
            require(not any((path / name).exists() for name in ("project.sqlite", "workbench.sqlite")),
                    "PROTECTED_WORKSPACE", "Ledger must be outside native project/manager roots.")
        if self.root.exists():
            require(self.root.is_dir(), "UNSAFE_PATH", "Expected a workspace directory.")
            allowed = {DB_NAME, DB_NAME + "-journal", DB_NAME + "-wal", DB_NAME + "-shm"}
            for path in self.root.iterdir():
                # SQLite journals may disappear after directory enumeration
                # when another connection commits; that is not an unsafe file.
                require(path.name in allowed and not path.is_symlink() and
                        (path.is_file() or (path.name != DB_NAME and not path.exists())),
                        "PROTECTED_WORKSPACE", "Use a fresh directory or an existing task ledger only.")
            require(self.db.exists() or not any(self.root.iterdir()), "LEDGER_INVALID", "Task ledger is missing.")

    @contextmanager
    def _connect(self, readonly=False):
        self._safe_root()
        require(self.db.is_file() and not self.db.is_symlink(), "LEDGER_NOT_FOUND", "Plan the ledger first.")
        con = sqlite3.connect(self.db.as_uri() + ("?mode=ro" if readonly else "?mode=rw"), uri=True, timeout=5)
        try:
            con.execute("BEGIN" if readonly else "BEGIN IMMEDIATE")
            row = con.execute("SELECT snapshot FROM coordination WHERE id=1").fetchone()
            require(row is not None, "LEDGER_INVALID", "Missing task ledger state.")
            state = json.loads(row[0])
            require(state.get("schema_version") == SCHEMA, "LEDGER_INVALID", "Not a recognized task ledger.")
            yield con, state
            if not readonly:
                con.commit()
        except (sqlite3.Error, json.JSONDecodeError) as error:
            con.rollback()
            raise ResearchError("LEDGER_INVALID", "Unable to read a recognized coordination ledger.") from error
        except BaseException:
            con.rollback()
            raise
        finally:
            con.close()

    def _payload(self, command, request_id, arguments):
        identifier(request_id)
        try:
            raw = canonical({"command": command, "arguments": arguments})
        except (ValueError, TypeError, RecursionError):
            raise ResearchError("INVALID_REQUEST", "Expected finite JSON payload.") from None
        require(len(raw.encode("utf-8")) <= MAX_BYTES, "INVALID_REQUEST", "Command exceeds 64 KiB.")
        return json.loads(raw), fingerprint(json.loads(raw))

    @staticmethod
    def _receipt(con, state, command, request_id, digest, **fields):
        receipt = {"schema_version": SCHEMA, "command": command, "request_id": request_id,
                   "project_ref": state["project_ref"], "plan_sha256": state["plan_sha256"],
                   "state_version": state["state_version"], **fields}
        con.execute("UPDATE coordination SET snapshot=? WHERE id=1", (canonical(state),))
        con.execute("INSERT INTO receipts VALUES (?,?,?)", (request_id, digest, canonical(receipt)))
        return receipt

    @staticmethod
    def _replay(con, request_id, digest):
        row = con.execute("SELECT fingerprint,receipt FROM receipts WHERE request_id=?", (request_id,)).fetchone()
        if row:
            require(row[0] == digest, "IDEMPOTENCY_CONFLICT", "Request ID already binds another payload/command.")
            return json.loads(row[1])
        require(con.execute("SELECT count(*) FROM receipts").fetchone()[0] < MAX_REQUESTS, "JOURNAL_LIMIT", "Coordination journal is full.")
        return None

    @staticmethod
    def _find(state, task_id):
        identifier(task_id, "task_id")
        task = next((task for task in state["tasks"] if task["spec"]["task_id"] == task_id), None)
        require(task is not None, "TASK_NOT_FOUND", "Unknown task ID.")
        return task

    @staticmethod
    def _ready(state):
        completed = {task["spec"]["task_id"] for task in state["tasks"] if task["status"] == "completed"}
        return [task for task in state["tasks"] if task["status"] in ("ready", "blocked", "rejected")
                and len(task["attempts"]) < task["spec"]["budget"]["attempt_limit"]
                and set(task["spec"]["dependencies"]) <= completed
                and (state["policy"]["mode"] != "dynamic" or task["spec"]["expected_value"] > 0)]

    def plan(self, request_id, project_ref, tasks, policy=None):
        arguments, digest = self._payload("plan", request_id, {"project_ref": project_ref, "tasks": tasks,
                                                              "policy": DEFAULT_POLICY if policy is None else policy})
        arguments = arguments["arguments"]
        self._safe_root()
        if self.db.exists():
            with self._connect() as (con, state):
                replay = self._replay(con, request_id, digest)
                require(replay is not None, "PLAN_FROZEN", "An existing ledger cannot be replanned or rebound.")
                return replay
        _plan(**arguments)
        self.root.mkdir(parents=True, exist_ok=True)
        fd = os.open(self.db, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        os.close(fd)
        con = sqlite3.connect(self.db)
        try:
            con.execute("BEGIN IMMEDIATE")
            con.execute("CREATE TABLE coordination (id INTEGER PRIMARY KEY CHECK(id=1),snapshot TEXT NOT NULL)")
            con.execute("CREATE TABLE receipts (request_id TEXT PRIMARY KEY,fingerprint TEXT NOT NULL,receipt TEXT NOT NULL)")
            state = {"schema_version": SCHEMA, "project_ref": arguments["project_ref"], "policy": arguments["policy"],
                     "plan_sha256": fingerprint(arguments), "state_version": 0, "attempts_used": 0,
                     "tasks": [{"spec": spec, "status": "blocked" if spec["dependencies"] else "ready", "attempts": []} for spec in arguments["tasks"]]}
            con.execute("INSERT INTO coordination VALUES(1,?)", (canonical(state),))
            receipt = self._receipt(con, state, "plan", request_id, digest, status="planned",
                                    task_ids=[task["spec"]["task_id"] for task in state["tasks"]])
            con.commit()
            return receipt
        except BaseException:
            con.rollback()
            raise
        finally:
            con.close()

    def claim(self, request_id, agent_id, task_id=None):
        identifier(agent_id, "agent_id")
        if task_id is not None:
            identifier(task_id, "task_id")
        _, digest = self._payload("claim", request_id, {"agent_id": agent_id, "task_id": task_id})
        with self._connect() as (con, state):
            replay = self._replay(con, request_id, digest)
            if replay is not None:
                return replay
            require(state["attempts_used"] < state["policy"]["attempt_limit"], "ATTEMPT_LIMIT", "Shared coordination attempts exhausted.")
            active = [task for task in state["tasks"] if task["status"] in ("claimed", "submitted", "unknown")]
            require(len(active) < state["policy"]["max_parallel"], "CLAIM_CONFLICT", "Parallel slots are occupied, including unknown claims.")
            ready = self._ready(state)
            if task_id is not None:
                task = self._find(state, task_id)
                require(task in ready, "TASK_NOT_READY", "Task is blocked, claimed, unknown, complete or exhausted.")
            elif ready:
                task = sorted(ready, key=lambda item: (-Fraction(item["spec"]["expected_value"]) / Fraction(item["spec"]["estimated_effort"]), item["spec"]["task_id"]))[0] if state["policy"]["mode"] == "dynamic" else ready[0]
            else:
                return self._receipt(con, state, "claim", request_id, digest, status="waiting", reason="No positive-value runnable task under this frozen policy.")
            attempt = {"attempt": len(task["attempts"]) + 1, "agent_id": agent_id, "status": "claimed", "claim_request_id": request_id}
            task["attempts"].append(attempt)
            task["status"] = "claimed"
            state["attempts_used"] += 1
            state["state_version"] += 1
            return self._receipt(con, state, "claim", request_id, digest, status="claimed", task_id=task["spec"]["task_id"],
                                 agent_id=agent_id, attempt=attempt["attempt"], task_contract=task["spec"])

    def submit(self, request_id, task_id, agent_id, attempt, result):
        identifier(agent_id, "agent_id")
        require(type(attempt) is int and 1 <= attempt <= 3, "INVALID_REQUEST", "Invalid attempt identity.")
        payload, digest = self._payload("submit", request_id, {"task_id": task_id, "agent_id": agent_id, "attempt": attempt, "result": result})
        result = payload["arguments"]["result"]
        with self._connect() as (con, state):
            replay = self._replay(con, request_id, digest)
            if replay is not None:
                return replay
            task = self._find(state, task_id)
            require(task["status"] in ("claimed", "unknown"), "TASK_NOT_CLAIMED", "Task cannot accept a new result.")
            current = task["attempts"][-1]
            require(current["agent_id"] == agent_id and current["attempt"] == attempt, "CLAIM_MISMATCH", "Result is not from the original claim/attempt.")
            _result(task["spec"], result)
            current.update(status="submitted", result=result, result_sha256=fingerprint(result), submit_request_id=request_id)
            task["status"] = "submitted"
            state["state_version"] += 1
            return self._receipt(con, state, "submit", request_id, digest, status="submitted", task_id=task_id, attempt=attempt,
                                 result_sha256=current["result_sha256"], interpretation_status="unverified_agent_analysis")

    def reconcile(self, request_id, task_id, resolution, reason, *, expected_attempt, result_sha256=None):
        _text(reason, "Host reconciliation reason")
        require(resolution in ("completed", "rejected", "unknown"), "INVALID_REQUEST", "Invalid host resolution.")
        require(type(expected_attempt) is int and 1 <= expected_attempt <= 3, "INVALID_REQUEST", "Expected an explicit attempt identity.")
        if resolution == "unknown":
            require(result_sha256 is None, "INVALID_REQUEST", "Unknown claims cannot identify an unseen result.")
        else:
            _digest(result_sha256)
        _, digest = self._payload("reconcile", request_id, {"task_id": task_id, "resolution": resolution, "reason": reason,
                                 "expected_attempt": expected_attempt, "result_sha256": result_sha256})
        with self._connect() as (con, state):
            replay = self._replay(con, request_id, digest)
            if replay is not None:
                return replay
            task = self._find(state, task_id)
            require(task["status"] == ("claimed" if resolution == "unknown" else "submitted"), "RECONCILIATION_CONFLICT", "Host must reconcile the current claim or submitted analysis.")
            current = task["attempts"][-1]
            require(current["attempt"] == expected_attempt and (resolution == "unknown" or current["result_sha256"] == result_sha256),
                    "RECONCILIATION_CONFLICT", "Host review is stale or binds a different result.")
            current.update(status=resolution, reconciliation={"request_id": request_id, "reason": reason, "resolution": resolution})
            task["status"] = resolution
            state["state_version"] += 1
            return self._receipt(con, state, "reconcile", request_id, digest, status=resolution, task_id=task_id,
                                 attempt=current["attempt"], result_sha256=result_sha256, reason=reason, scientific_status="unchanged")

    def status(self):
        with self._connect(readonly=True) as (con, state):
            active = sum(task["status"] in ("claimed", "submitted", "unknown") for task in state["tasks"])
            capacity = state["attempts_used"] < state["policy"]["attempt_limit"] and active < state["policy"]["max_parallel"]
            ready_ids = {task["spec"]["task_id"] for task in self._ready(state)} if capacity else set()
            for task in state["tasks"]:
                task["runnable"] = task["spec"]["task_id"] in ready_ids
            return {**state, "native_budget_authority": "none", "transport": "not_implemented",
                    "receipts": [json.loads(row[0]) for row in con.execute("SELECT receipt FROM receipts ORDER BY rowid")]}
