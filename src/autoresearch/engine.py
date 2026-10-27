"""Durable, serial-per-campaign execution. No arbitrary code or remote calls."""

from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import sqlite3
import time
import uuid

from .contracts import Candidate, ResearchError, canonical, fingerprint, identifier
from .fixture import DATASET_ID, EVIDENCE_TYPE
from . import training

PROTOCOL = {"id": "fixed-fixture-evaluation-v1", "metric": "validation_mse", "direction": "minimize", "min_relative_gain": .01}


class Engine:
    def __init__(self, workspace):
        self.root = Path(workspace).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.db = self.root / "research.sqlite3"
        with self.connection() as con:
            con.executescript("""
            CREATE TABLE IF NOT EXISTS campaigns(
              id TEXT PRIMARY KEY, request_id TEXT UNIQUE NOT NULL, fingerprint TEXT NOT NULL,
              goal TEXT NOT NULL, max_trials INTEGER NOT NULL, status TEXT NOT NULL,
              best_trial_id TEXT, final_json TEXT, created REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS trials(
              id TEXT PRIMARY KEY, campaign_id TEXT NOT NULL REFERENCES campaigns(id),
              request_id TEXT NOT NULL, fingerprint TEXT NOT NULL, ordinal INTEGER NOT NULL,
              candidate_json TEXT NOT NULL, reason TEXT NOT NULL, status TEXT NOT NULL,
              result_json TEXT, created REAL NOT NULL,
              UNIQUE(campaign_id, request_id), UNIQUE(campaign_id, ordinal));
            """)

    @contextmanager
    def connection(self, write=False):
        con = sqlite3.connect(self.db, timeout=10, isolation_level=None)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA foreign_keys=ON")
        try:
            if write:
                con.execute("BEGIN IMMEDIATE")
            yield con
            if write:
                con.commit()
        except BaseException:
            if write:
                con.rollback()
            raise
        finally:
            con.close()

    @staticmethod
    def _campaign(con, campaign_id):
        identifier(campaign_id, "campaign_id")
        row = con.execute("SELECT * FROM campaigns WHERE id=?", (campaign_id,)).fetchone()
        if row is None:
            raise ResearchError("NOT_FOUND", "campaign does not exist")
        return row

    def create(self, request_id, goal, max_trials=3):
        identifier(request_id)
        if not isinstance(goal, str) or not 1 <= len(goal.strip()) <= 500:
            raise ResearchError("INVALID_REQUEST", "goal must contain 1-500 characters")
        if type(max_trials) is not int or not 1 <= max_trials <= 20:
            raise ResearchError("INVALID_REQUEST", "max_trials must be 1-20")
        spec = {"goal": goal, "max_trials": max_trials, "dataset_id": DATASET_ID, "protocol": PROTOCOL}
        fp = fingerprint(spec)
        with self.connection(True) as con:
            old = con.execute("SELECT * FROM campaigns WHERE request_id=?", (request_id,)).fetchone()
            if old:
                if old["fingerprint"] != fp:
                    raise ResearchError("IDEMPOTENCY_CONFLICT", "request_id already belongs to a different campaign request")
                campaign_id = old["id"]
            else:
                campaign_id = uuid.uuid4().hex
                con.execute("INSERT INTO campaigns VALUES(?,?,?,?,?,'active',NULL,NULL,?)",
                            (campaign_id, request_id, fp, goal, max_trials, time.time()))
        return self.status(campaign_id)

    def status(self, campaign_id):
        with self.connection() as con:
            c = dict(self._campaign(con, campaign_id))
            rows = con.execute("SELECT * FROM trials WHERE campaign_id=? ORDER BY ordinal", (campaign_id,)).fetchall()
        trials = []
        for row in rows:
            t = {k: row[k] for k in ("id", "request_id", "ordinal", "reason", "status")}
            t["candidate"] = json.loads(row["candidate_json"])
            if row["result_json"]:
                t.update(json.loads(row["result_json"]))
            trials.append(t)
        return {"campaign_id": c["id"], "goal": c["goal"], "status": c["status"],
                "dataset_id": DATASET_ID, "evidence_type": EVIDENCE_TYPE,
                "protocol": PROTOCOL.copy(), "policy_kind": "deterministic_fixture_policy_v1",
                "platform_connected": False, "scientific_status": "engineering_only",
                "budget": {"max_trials": c["max_trials"], "consumed_trials": len(trials)},
                "best_trial_id": c["best_trial_id"], "trials": trials,
                "final_evaluation": json.loads(c["final_json"]) if c["final_json"] else None}

    def propose(self, campaign_id):
        state = self.status(campaign_id)
        if not state["trials"]:
            return Candidate(1, .01), "Establish a first-order baseline before adding interaction features."
        good = next((t for t in state["trials"] if t["id"] == state["best_trial_id"]), None)
        if good is None:
            raise ResearchError("NEEDS_REVIEW", "all prior trials failed; inspect execution before proposing another model")
        done = {(t["candidate"]["degree"], t["candidate"]["alpha"]) for t in state["trials"]}
        if good["candidate"]["degree"] == 1 and (2, .01) not in done:
            return Candidate(2, .01), f"Baseline validation MSE={good['metrics']['validation_mse']:.6g}; test interactions under the same split."
        if (2, 1_000_000.) not in done:
            return Candidate(2, 1_000_000.), "Probe whether stronger regularization preserves the measured validation gain; reject if it does not."
        raise ResearchError("POLICY_EXHAUSTED", "bounded fixture policy exhausted; keep current model and review the next research action")

    def step(self, campaign_id, request_id, candidate=None, reason=None):
        identifier(request_id)
        with self.connection(True) as con:
            c = self._campaign(con, campaign_id)
            old = con.execute("SELECT * FROM trials WHERE campaign_id=? AND request_id=?", (campaign_id, request_id)).fetchone()
            # Proposal resolution and request reservation share the write lock.
            if candidate is None:
                if old:
                    candidate = Candidate.parse(json.loads(old["candidate_json"]))
                    reason = old["reason"] if reason is None else reason
                else:
                    candidate, proposed_reason = self.propose(campaign_id)
                    reason = proposed_reason if reason is None else reason
            elif not isinstance(candidate, Candidate):
                candidate = Candidate.parse(candidate)
            candidate = Candidate.parse(candidate.to_dict())
            reason = reason if reason is not None else "Caller proposed a bounded candidate; evaluator remains fixed."
            if not isinstance(reason, str) or not 1 <= len(reason) <= 1000:
                raise ResearchError("INVALID_REQUEST", "reason must contain 1-1000 characters")
            fp = fingerprint({"candidate": candidate.to_dict(), "reason": reason, "protocol": PROTOCOL})
            if old:
                if old["fingerprint"] != fp:
                    raise ResearchError("IDEMPOTENCY_CONFLICT", "request_id already belongs to a different trial request")
                return self._trial_reply(old)
            if c["status"] != "active":
                raise ResearchError("CAMPAIGN_NOT_ACTIVE", "resume the campaign or use a new campaign after finalization")
            if con.execute("SELECT 1 FROM trials WHERE campaign_id=? AND status='running'", (campaign_id,)).fetchone():
                raise ResearchError("BUSY", "a trial is already running; inspect its outcome instead of retrying with a new id")
            count = con.execute("SELECT count(*) FROM trials WHERE campaign_id=?", (campaign_id,)).fetchone()[0]
            if count >= c["max_trials"]:
                raise ResearchError("BUDGET_EXHAUSTED", "campaign trial budget exhausted")
            trial_id = uuid.uuid4().hex
            con.execute("INSERT INTO trials VALUES(?,?,?,?,?,?,?,'running',NULL,?)",
                        (trial_id, campaign_id, request_id, fp, count+1, canonical(candidate.to_dict()), reason, time.time()))
        try:
            model, metrics = training.train(candidate)
            artifact_path = self.root / campaign_id / f"{trial_id}.model.json"
            artifact_path.parent.mkdir(exist_ok=True)
            payload = canonical(model).encode("utf-8")
            temp = artifact_path.with_suffix(".tmp")
            temp.write_bytes(payload)
            temp.replace(artifact_path)
            sha = hashlib.sha256(payload).hexdigest()
            with self.connection(True) as con:
                c = self._campaign(con, campaign_id)
                current = con.execute("SELECT * FROM trials WHERE id=?", (trial_id,)).fetchone()
                if current["status"] != "running":
                    # An explicitly reconciled job cannot promote a late result.
                    return self._trial_reply(current)
                best = con.execute("SELECT result_json FROM trials WHERE id=?", (c["best_trial_id"],)).fetchone()
                baseline = json.loads(best[0])["metrics"]["validation_mse"] if best else None
                accepted = baseline is None or metrics["validation_mse"] < baseline * (1-PROTOCOL["min_relative_gain"])
                decision = "accepted" if accepted else "rejected"
                result = {"metrics": metrics, "model_artifact": artifact_path.relative_to(self.root).as_posix(),
                          "model_sha256": sha, "parent_trial_id": c["best_trial_id"],
                          "decision_reason": "fixed validation improvement gate passed" if accepted else "no required validation improvement; previous model retained"}
                con.execute("UPDATE trials SET status=?,result_json=? WHERE id=?", (decision, canonical(result), trial_id))
                if accepted:
                    con.execute("UPDATE campaigns SET best_trial_id=? WHERE id=?", (trial_id, campaign_id))
        except BaseException as exc:
            # Unknown in-flight jobs are never automatically retrained on restart.
            with self.connection(True) as con:
                con.execute("UPDATE trials SET status='failed',result_json=? WHERE id=? AND status='running'",
                            (canonical({"error": {"code": "TRAINING_FAILED", "type": type(exc).__name__}}), trial_id))
            if not isinstance(exc, Exception):
                raise
        with self.connection() as con:
            return self._trial_reply(con.execute("SELECT * FROM trials WHERE id=?", (trial_id,)).fetchone())

    @staticmethod
    def _trial_reply(row):
        return {"trial_id": row["id"], "request_id": row["request_id"], "status": row["status"],
                "candidate": json.loads(row["candidate_json"]),
                **(json.loads(row["result_json"]) if row["result_json"] else {})}

    def pause(self, campaign_id, paused=True):
        with self.connection(True) as con:
            c = self._campaign(con, campaign_id)
            if c["status"] == "finalized":
                raise ResearchError("CAMPAIGN_FINALIZED", "final evaluation locks this campaign")
            if con.execute("SELECT 1 FROM trials WHERE campaign_id=? AND status='running'", (campaign_id,)).fetchone():
                raise ResearchError("BUSY", "cannot pause an in-flight fixed training job")
            con.execute("UPDATE campaigns SET status=? WHERE id=?", ("paused" if paused else "active", campaign_id))
        return self.status(campaign_id)

    def reconcile_interrupted(self, campaign_id, trial_id, *, confirm_stopped=False):
        """Operator-only reconciliation, not a model-callable tool or process killer."""
        if confirm_stopped is not True:
            raise ResearchError("RECONCILIATION_REQUIRED", "operator must first verify that the worker has stopped")
        identifier(trial_id, "trial_id")
        with self.connection(True) as con:
            self._campaign(con, campaign_id)
            row = con.execute("SELECT * FROM trials WHERE id=? AND campaign_id=?", (trial_id, campaign_id)).fetchone()
            if row is None:
                raise ResearchError("NOT_FOUND", "trial does not exist in this campaign")
            if row["status"] == "running":
                con.execute("UPDATE trials SET status='failed',result_json=? WHERE id=?",
                            (canonical({"error": {"code": "INTERRUPTED_RECONCILED", "budget_consumed": True}}), trial_id))
                row = con.execute("SELECT * FROM trials WHERE id=?", (trial_id,)).fetchone()
            return self._trial_reply(row)

    def finalize(self, campaign_id):
        with self.connection(True) as con:
            c = self._campaign(con, campaign_id)
            if c["final_json"]:
                return json.loads(c["final_json"])
            if con.execute("SELECT 1 FROM trials WHERE campaign_id=? AND status='running'", (campaign_id,)).fetchone():
                raise ResearchError("BUSY", "wait for the running trial before final evaluation")
            if not c["best_trial_id"]:
                raise ResearchError("NO_MODEL", "no accepted trained model exists")
            row = con.execute("SELECT result_json FROM trials WHERE id=?", (c["best_trial_id"],)).fetchone()
            result = json.loads(row[0])
            artifact_path = (self.root / result["model_artifact"]).resolve()
            if not artifact_path.is_relative_to(self.root):
                raise ResearchError("INVALID_ARTIFACT", "artifact path escapes workspace")
            payload = artifact_path.read_bytes()
            if hashlib.sha256(payload).hexdigest() != result["model_sha256"]:
                raise ResearchError("ARTIFACT_CHANGED", "model artifact changed after training")
            final = {"best_trial_id": c["best_trial_id"], "model_sha256": result["model_sha256"],
                     "evidence_type": EVIDENCE_TYPE, **training.terminal_evaluation(json.loads(payload))}
            con.execute("UPDATE campaigns SET status='finalized',final_json=? WHERE id=?", (canonical(final), campaign_id))
        return final
