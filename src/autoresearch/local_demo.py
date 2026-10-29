"""Opt-in, independent local script execution. No network or model client calls.

Only explicit step() initializes storage. Unknown pending jobs remain pending and
block further work; this module never infers that a different worker has stopped.
"""

from contextlib import contextmanager
import json
import math
from pathlib import Path
import re
import sqlite3
import stat
import threading
import time
import uuid

from .contracts import ResearchError, canonical, identifier
from .datasets import STEELS_ID
from .engine import AGENT_POLICY, Engine
from .research_loop import parse_decision
from .studio_project import ReadOnlyEvidence

DIRECTORY = ".local-demo-v1"
ORIGIN = "local_script_not_llm"
MAX_TRIALS = 2
VERSION = "studio-local-demo-v1"


def scripted_decision(observation):
    """The bounded choice uses only the supplied completed experiment feedback."""
    trials = observation["trials"]
    if not trials:
        candidate = {"degree": 1, "alpha": 1.0}
        hypothesis = "本地脚本基线：先测量一阶配方。"
    elif len(trials) == 1:
        last = trials[-1]
        metrics = last.get("metrics", {})
        train, validation = metrics.get("training_mse"), metrics.get("validation_mse")
        if not all(type(value) in (int, float) and math.isfinite(value) for value in (train, validation)):
            raise ResearchError("LOCAL_DEMO_NEEDS_REVIEW", "首步缺少有效指标，不能继续脚本比较。")
        interactions = last["status"] == "accepted" and validation <= train * 1.25
        candidate = {"degree": 2, "alpha": 1.0} if interactions else {"degree": 1, "alpha": 1000.0}
        hypothesis = (f"本地脚本读取首步验证 MSE={validation:.6g}、训练 MSE={train:.6g}；"
                      + ("验证误差未明显高于训练误差，比较二阶交互配方。" if interactions else "验证反馈触发更强正则化的一阶比较。"))
    else:
        raise ResearchError("LOCAL_DEMO_BUDGET_EXHAUSTED", "两次本地试验额度已使用。")
    return {"action": "propose", "proposal": {
        "observation_sha256": observation["observation_sha256"],
        "hypothesis": hypothesis,
        "expected_effect": "在固定公开数据与评价规则下比较验证误差，候选可能被拒绝；不作科研发现结论。",
        "candidate": candidate,
        "evidence_trial_ids": [trials[-1]["id"]] if trials else [],
    }}


class LocalDemo:
    def __init__(self, workspace, parent_snapshot_sha256, *, enabled=False):
        if type(enabled) is not bool or not re.fullmatch(r"[0-9a-f]{64}", parent_snapshot_sha256 or ""):
            raise ResearchError("INVALID_REQUEST", "本地演示配置无效。")
        self.workspace = Path(workspace).resolve()
        self.root = self.workspace / DIRECTORY
        self.db = self.root / "jobs.sqlite3"
        self.engine_root = self.root / "engine"
        self.parent = parent_snapshot_sha256
        self.enabled = enabled
        self.owner = uuid.uuid4().hex
        self._lock = threading.RLock()
        self._workers = {}

    @staticmethod
    def _unsafe():
        return ResearchError("LOCAL_DEMO_UNSAFE", "本地演示目录不完整、不受管理或路径不安全；未覆盖现有内容。")

    def _guard(self):
        """Reject redirected directories and shared regular-file identities."""
        def visit(path, depth=0):
            try:
                if path.is_symlink() or getattr(path, "is_junction", lambda: False)():
                    raise self._unsafe()
                metadata = path.lstat()
                if stat.S_ISREG(metadata.st_mode) and metadata.st_nlink > 1:
                    # SQLite writes through a hard link even when its path is
                    # lexically inside this directory. Do not adopt shared files.
                    raise self._unsafe()
                if depth > 4:
                    raise self._unsafe()
                if path.is_dir():
                    # Resolve directories only. Every descendant is reached from
                    # these checked parents and links are rejected above. A
                    # disappearing Windows SQLite sidecar can otherwise resolve
                    # to an equivalent \\?\ path even with strict=True.
                    if not path.resolve(strict=True).is_relative_to(self.workspace):
                        raise self._unsafe()
                    children = list(path.iterdir())
                    if len(children) > 64:
                        raise self._unsafe()
                    for child in children:
                        visit(child, depth + 1)
            except FileNotFoundError:
                # SQLite journals and atomic model .tmp files may disappear after
                # enumeration. Nothing at this vanished entry will be opened.
                # Required persistent files are checked separately by _identity.
                return
        visit(self.root)

    def _identity(self):
        self._guard()
        marker = self.root / "identity.json"
        if not marker.is_file() or marker.stat().st_size > 8192 or not self.db.is_file():
            raise self._unsafe()
        try:
            value = json.loads(marker.read_text(encoding="utf-8"))
            expected = {"version": VERSION, "origin": ORIGIN, "parent_snapshot_sha256": self.parent,
                        "dataset_id": STEELS_ID, "policy_kind": AGENT_POLICY, "max_trials": MAX_TRIALS}
            if set(value) != set(expected) | {"campaign_id"} or any(value[key] != item for key, item in expected.items()):
                raise ValueError("identity")
            identifier(value["campaign_id"], "campaign_id")
            if not (self.engine_root / "research.sqlite3").is_file():
                raise ValueError("engine missing")
        except (OSError, ValueError, TypeError, KeyError, ResearchError):
            raise self._unsafe() from None
        return value

    def _initialize(self):
        self._guard()
        if self.root.exists():
            return self._identity()
        try:
            # Atomic mkdir elects one initializer. A partial directory is never adopted.
            self.root.mkdir()
        except FileExistsError:
            return self._identity()
        engine = Engine(self.engine_root)
        state = engine.create("local-demo-project-v1", "独立本地脚本策略钢材配方比较，不是 LLM 或跨域研究。",
                              MAX_TRIALS, STEELS_ID, AGENT_POLICY)
        engine.pause(state["campaign_id"])
        con = sqlite3.connect(self.db)
        try:
            con.execute("""CREATE TABLE jobs(
                id TEXT PRIMARY KEY,request_id TEXT UNIQUE NOT NULL,ordinal INTEGER UNIQUE NOT NULL,
                owner TEXT NOT NULL,status TEXT NOT NULL,trial_id TEXT,error_code TEXT,
                observation_json TEXT,decision_json TEXT,created REAL NOT NULL)""")
            con.commit()
        finally:
            con.close()
        identity = {"version": VERSION, "origin": ORIGIN, "parent_snapshot_sha256": self.parent,
                    "dataset_id": STEELS_ID, "policy_kind": AGENT_POLICY, "max_trials": MAX_TRIALS,
                    "campaign_id": state["campaign_id"]}
        with (self.root / "identity.json").open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(canonical(identity))
        return identity

    @contextmanager
    def _connection(self, write=False):
        self._guard()
        con = sqlite3.connect(self.db.as_uri() + ("?mode=rw" if write else "?mode=ro"),
                              uri=True, timeout=10, isolation_level=None)
        con.row_factory = sqlite3.Row
        try:
            if not write:
                con.execute("PRAGMA query_only=ON")
            con.execute("BEGIN IMMEDIATE" if write else "BEGIN")
            yield con
            if write:
                con.commit()
        except BaseException:
            if write:
                con.rollback()
            raise
        finally:
            con.close()

    def _base(self):
        return {"enabled": self.enabled, "status": "idle" if self.enabled else "disabled",
                "origin": ORIGIN, "parent_snapshot_sha256": self.parent, "independent_run": True,
                "consumed": 0, "max_trials": MAX_TRIALS, "cloud_calls": 0, "model_calls": 0,
                "can_step": self.enabled, "job_id": None, "reason": None, "jobs": [], "trials": []}

    def status(self):
        result = self._base()
        if not self.enabled:
            return result
        with self._lock:
            try:
                self._guard()
                if not self.root.exists():
                    return result
                identity = self._identity()
                with self._connection() as con:
                    jobs = [dict(row) for row in con.execute("SELECT * FROM jobs ORDER BY ordinal")]
                state = ReadOnlyEvidence(self.engine_root).status(identity["campaign_id"])
                if state["dataset_id"] != STEELS_ID or state["budget"]["max_trials"] != MAX_TRIALS or state["policy_kind"] != AGENT_POLICY:
                    raise self._unsafe()
                result["consumed"] = len(state["trials"])
                result["trials"] = [{"id": trial["id"], "ordinal": trial["ordinal"], "status": trial["status"],
                    "candidate": trial["candidate"], **({"metrics": trial["metrics"]} if "metrics" in trial else {}),
                    **({"decision_reason": trial["decision_reason"]} if "decision_reason" in trial else {}),
                    **({"proposal": trial["proposal"]} if "proposal" in trial else {}),
                    **({"error_code": trial["error"].get("code", "TRAINING_FAILED")} if "error" in trial else {})}
                    for trial in state["trials"]]
                result["jobs"] = [{"job_id": job["id"], **{key: job[key] for key in
                    ("request_id", "status", "trial_id", "error_code")}} for job in jobs]
                result["job_id"] = jobs[-1]["id"] if jobs else None
                pending = next((job for job in jobs if job["status"] in {"reserved", "running"}), None)
                if pending:
                    worker = self._workers.get(pending["id"])
                    owned = pending["owner"] == self.owner and worker is not None and worker.is_alive()
                    result.update(status="running" if owned else "needs_review", can_step=False,
                                  reason="step_in_progress" if owned else "pending_worker_state_unconfirmed")
                elif any(job["status"] == "failed" for job in jobs) or any(trial["status"] == "failed" for trial in state["trials"]):
                    result.update(status="failed", can_step=False, reason="execution_failed_requires_review")
                elif any(trial["status"] == "running" for trial in state["trials"]):
                    result.update(status="needs_review", can_step=False, reason="trial_state_unconfirmed")
                elif result["consumed"] >= MAX_TRIALS or len(jobs) >= MAX_TRIALS:
                    result.update(status="completed", can_step=False, reason="trial_budget_exhausted")
                elif jobs:
                    result.update(status="paused", reason="step_finished")
                return result
            except (ResearchError, OSError, ValueError, KeyError, TypeError, sqlite3.Error):
                result.update(status="needs_review", can_step=False, reason="local_storage_requires_review")
                return result

    def step(self, request_id):
        if not self.enabled:
            raise ResearchError("LOCAL_DEMO_DISABLED", "本地演示未启用。")
        identifier(request_id)
        with self._lock:
            identity = self._initialize()
            with self._connection(True) as con:
                old = con.execute("SELECT * FROM jobs WHERE request_id=?", (request_id,)).fetchone()
                if old:
                    job_id, replayed = old["id"], True
                else:
                    jobs = con.execute("SELECT * FROM jobs ORDER BY ordinal").fetchall()
                    pending = next((job for job in jobs if job["status"] in {"reserved", "running"}), None)
                    if pending:
                        worker = self._workers.get(pending["id"])
                        owned = pending["owner"] == self.owner and worker is not None and worker.is_alive()
                        raise ResearchError("LOCAL_DEMO_BUSY" if owned else "LOCAL_DEMO_NEEDS_REVIEW",
                                            "已有任务未确认完成，不能派发新试验。")
                    if any(job["status"] != "finished" for job in jobs):
                        raise ResearchError("LOCAL_DEMO_NEEDS_REVIEW", "已有失败任务需要核查。")
                    if len(jobs) >= MAX_TRIALS:
                        raise ResearchError("LOCAL_DEMO_BUDGET_EXHAUSTED", "两次独立本地试验额度已使用。")
                    state = ReadOnlyEvidence(self.engine_root).status(identity["campaign_id"])
                    if any(trial["status"] in {"running", "failed"} for trial in state["trials"]):
                        raise ResearchError("LOCAL_DEMO_NEEDS_REVIEW", "已有试验状态需要核查。")
                    if len(state["trials"]) >= MAX_TRIALS:
                        raise ResearchError("LOCAL_DEMO_BUDGET_EXHAUSTED", "两次独立本地试验额度已使用。")
                    job_id, replayed = uuid.uuid4().hex, False
                    con.execute("""INSERT INTO jobs(id,request_id,ordinal,owner,status,created)
                                VALUES(?,?,?,?,'reserved',?)""", (job_id, request_id, len(jobs)+1, self.owner, time.time()))
            if not replayed:
                self._start_worker(job_id, identity["campaign_id"])
            return {"ok": True, "replayed": replayed, "job_id": job_id, "result": self.status()}

    def _start_worker(self, job_id, campaign_id):
        try:
            worker = threading.Thread(target=self._run, args=(job_id, campaign_id), daemon=True,
                                      name="local-demo-" + job_id[:8])
            self._workers[job_id] = worker
            worker.start()
        except BaseException:
            self._finish(job_id, "failed", error_code="LOCAL_DEMO_LAUNCH_FAILED")
            raise ResearchError("LOCAL_DEMO_NEEDS_REVIEW", "任务已占位但未能启动，需要核查。") from None

    def _finish(self, job_id, status, *, trial_id=None, error_code=None):
        with self._lock:
            with self._connection(True) as con:
                con.execute("UPDATE jobs SET status=?,trial_id=?,error_code=? WHERE id=? AND owner=? AND status IN ('reserved','running')",
                            (status, trial_id, error_code, job_id, self.owner))
            self._workers.pop(job_id, None)

    def _run(self, job_id, campaign_id):
        try:
            with self._connection(True) as con:
                count = con.execute("UPDATE jobs SET status='running' WHERE id=? AND owner=? AND status='reserved'",
                                    (job_id, self.owner)).rowcount
            if count != 1:
                return
            engine = Engine(self.engine_root)
            engine.pause(campaign_id, False)
            observation = engine.observe(campaign_id)
            decision = parse_decision(canonical(scripted_decision(observation)), observation)
            with self._connection(True) as con:
                con.execute("UPDATE jobs SET observation_json=?,decision_json=? WHERE id=? AND status='running' AND owner=?",
                            (canonical(observation), canonical(decision), job_id, self.owner))
            trial = engine.submit(campaign_id, "local-demo-" + job_id, decision["proposal"])
            if trial["status"] == "running":
                raise ResearchError("LOCAL_DEMO_NEEDS_REVIEW", "试验结果仍待核查。")
            engine.pause(campaign_id)
            failed = trial["status"] not in {"accepted", "rejected"}
            self._finish(job_id, "failed" if failed else "finished", trial_id=trial["trial_id"],
                         error_code="TRAINING_FAILED" if failed else None)
        except BaseException:
            # No traceback, paths or exception messages enter HTTP or console output.
            # If recording this failure also fails, the durable pending slot stays blocked.
            try:
                self._finish(job_id, "failed", error_code="LOCAL_DEMO_EXECUTION_FAILED")
            except BaseException:
                pass
        finally:
            with self._lock:
                self._workers.pop(job_id, None)
