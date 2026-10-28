"""Durable, serial-per-campaign execution. No arbitrary code or remote calls."""

from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import sqlite3
import time
import uuid

from .contracts import Candidate, Proposal, ResearchError, canonical, fingerprint, identifier
from .fixture import DATASET_ID
from . import training, datasets

PROTOCOL = {"id": "fixed-fixture-evaluation-v1", "metric": "validation_mse", "direction": "minimize", "min_relative_gain": .01}
FIXTURE_POLICY = "deterministic_fixture_policy_v1"
AGENT_POLICY = "external_agent_proposal_v1"


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
        # Serialize additive migrations; existing fixture campaigns keep their semantics.
        with self.connection(True) as con:
            for table, column in (("campaigns", "spec_json"), ("trials", "proposal_json")):
                if column not in {row[1] for row in con.execute(f"PRAGMA table_info({table})")}:
                    con.execute(f"ALTER TABLE {table} ADD COLUMN {column} TEXT")

    @contextmanager
    def connection(self, write=False):
        con = sqlite3.connect(self.db, timeout=10, isolation_level=None)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA foreign_keys=ON")
        try:
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

    @staticmethod
    def _campaign(con, campaign_id):
        identifier(campaign_id, "campaign_id")
        row = con.execute("SELECT * FROM campaigns WHERE id=?", (campaign_id,)).fetchone()
        if row is None:
            raise ResearchError("NOT_FOUND", "campaign does not exist")
        return row

    @staticmethod
    def _spec(campaign):
        if campaign["spec_json"]:
            return json.loads(campaign["spec_json"])
        return {"dataset": datasets.descriptor(DATASET_ID), "policy_kind": FIXTURE_POLICY,
                "protocol": PROTOCOL.copy()}

    @staticmethod
    def _verify_dataset(spec):
        if fingerprint(datasets.descriptor(spec["dataset"]["dataset_id"])) != fingerprint(spec["dataset"]):
            raise ResearchError("DATASET_CHANGED", "dataset identity or split differs from the frozen campaign")

    def create(self, request_id, goal, max_trials=3, dataset_id=DATASET_ID, policy_kind=FIXTURE_POLICY):
        identifier(request_id)
        if not isinstance(goal, str) or not 1 <= len(goal.strip()) <= 500:
            raise ResearchError("INVALID_REQUEST", "goal must contain 1-500 characters")
        if type(max_trials) is not int or not 1 <= max_trials <= 20:
            raise ResearchError("INVALID_REQUEST", "max_trials must be 1-20")
        data = datasets.descriptor(dataset_id)
        if not isinstance(policy_kind, str) or policy_kind not in {FIXTURE_POLICY, AGENT_POLICY}:
            raise ResearchError("INVALID_REQUEST", "unsupported policy_kind")
        if policy_kind == FIXTURE_POLICY and dataset_id != DATASET_ID:
            raise ResearchError("INVALID_REQUEST", "public benchmark campaigns require external_agent_proposal_v1")
        protocol = PROTOCOL.copy()
        if dataset_id != DATASET_ID:
            protocol["id"] = "materials-composition-holdout-v1"
        frozen = {"dataset": data, "policy_kind": policy_kind, "protocol": protocol}
        spec = {"goal": goal, "max_trials": max_trials, "dataset_id": dataset_id, "protocol": protocol}
        if policy_kind != FIXTURE_POLICY:
            spec.update(policy_kind=policy_kind, dataset_descriptor_sha256=fingerprint(data))
        fp = fingerprint(spec)
        with self.connection(True) as con:
            old = con.execute("SELECT * FROM campaigns WHERE request_id=?", (request_id,)).fetchone()
            if old:
                if old["fingerprint"] != fp:
                    raise ResearchError("IDEMPOTENCY_CONFLICT", "request_id already belongs to a different campaign request")
                campaign_id = old["id"]
            else:
                campaign_id = uuid.uuid4().hex
                con.execute("""INSERT INTO campaigns
                    (id,request_id,fingerprint,goal,max_trials,status,best_trial_id,final_json,created,spec_json)
                    VALUES(?,?,?,?,?,'active',NULL,NULL,?,?)""",
                            (campaign_id, request_id, fp, goal, max_trials, time.time(), canonical(frozen)))
        return self.status(campaign_id)

    def status(self, campaign_id):
        with self.connection() as con:
            c = dict(self._campaign(con, campaign_id))
            rows = con.execute("SELECT * FROM trials WHERE campaign_id=? ORDER BY ordinal", (campaign_id,)).fetchall()
        trials = []
        for row in rows:
            t = {k: row[k] for k in ("id", "request_id", "ordinal", "reason", "status")}
            t["candidate"] = json.loads(row["candidate_json"])
            if row["proposal_json"]:
                t["proposal"] = json.loads(row["proposal_json"])
            if row["result_json"]:
                t.update(json.loads(row["result_json"]))
            trials.append(t)
        spec = self._spec(c)
        data = spec["dataset"]
        return {"campaign_id": c["id"], "goal": c["goal"], "status": c["status"],
                "dataset_id": data["dataset_id"], "evidence_type": data["evidence_type"], "dataset": data,
                "protocol": spec["protocol"], "policy_kind": spec["policy_kind"],
                "platform_connected": False, "scientific_status": data["scientific_status"],
                "budget": {"max_trials": c["max_trials"], "consumed_trials": len(trials)},
                "best_trial_id": c["best_trial_id"], "trials": trials,
                "final_evaluation": json.loads(c["final_json"]) if c["final_json"] else None}

    def propose(self, campaign_id):
        state = self.status(campaign_id)
        if state["policy_kind"] != FIXTURE_POLICY:
            raise ResearchError("PROPOSAL_REQUIRED", "observe the campaign and submit an external-agent proposal")
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

    def observe(self, campaign_id):
        state = self.status(campaign_id)
        # Terminal test metrics never enter the research observation used for selection.
        body = {key: state[key] for key in ("campaign_id", "goal", "status", "dataset", "protocol",
                                            "policy_kind", "budget", "best_trial_id", "trials")}
        body["proposal_contract"] = {"version": "evidence-bound-proposal-v1",
                                     "allowed_candidate": {"degree": [1, 2, 3], "alpha_range": [0, 1000000]},
                                     "producer": "external_agent_submission_not_authenticated_model_identity"}
        return {**body, "observation_sha256": fingerprint(body)}

    def submit(self, campaign_id, request_id, proposal):
        parsed = Proposal.parse(proposal)
        return self.step(campaign_id, request_id, parsed.candidate, parsed.hypothesis, proposal=parsed)

    def step(self, campaign_id, request_id, candidate=None, reason=None, *, proposal=None):
        identifier(request_id)
        with self.connection(True) as con:
            c = self._campaign(con, campaign_id)
            spec = self._spec(c)
            if spec["policy_kind"] == AGENT_POLICY and proposal is None:
                raise ResearchError("PROPOSAL_REQUIRED", "external-agent campaigns require submit_proposal")
            if proposal is not None and spec["policy_kind"] != AGENT_POLICY:
                raise ResearchError("INVALID_REQUEST", "proposals require an external-agent campaign")
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
            request_spec = {"candidate": candidate.to_dict(), "reason": reason, "protocol": spec["protocol"]}
            if proposal is not None:
                request_spec["proposal"] = proposal.to_dict()
            fp = fingerprint(request_spec)
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
            self._verify_dataset(spec)
            if proposal is not None:
                observation = self.observe(campaign_id)
                if proposal.observation_sha256 != observation["observation_sha256"]:
                    raise ResearchError("STALE_OBSERVATION", "read the current observation before proposing")
                completed = [t for t in observation["trials"] if t["status"] != "running"]
                known = {t["id"] for t in completed}
                cited = set(proposal.evidence_trial_ids)
                if not cited <= known or (completed and completed[-1]["id"] not in cited):
                    raise ResearchError("INVALID_EVIDENCE", "cite the latest completed trial and only known completed evidence")
            trial_id = uuid.uuid4().hex
            con.execute("""INSERT INTO trials
                (id,campaign_id,request_id,fingerprint,ordinal,candidate_json,reason,status,result_json,created,proposal_json)
                VALUES(?,?,?,?,?,?,?,'running',NULL,?,?)""",
                        (trial_id, campaign_id, request_id, fp, count+1, canonical(candidate.to_dict()), reason,
                         time.time(), canonical(proposal.to_dict()) if proposal else None))
        try:
            dataset_id = spec["dataset"]["dataset_id"]
            model, metrics = training.train(candidate) if dataset_id == DATASET_ID else training.train(candidate, dataset_id)
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
                accepted = baseline is None or metrics["validation_mse"] < baseline * (1-spec["protocol"]["min_relative_gain"])
                decision = "accepted" if accepted else "rejected"
                result = {"metrics": metrics, "model_artifact": artifact_path.relative_to(self.root).as_posix(),
                          "model_sha256": sha, "parent_trial_id": c["best_trial_id"],
                          "recipe_sha256": fingerprint({"candidate": candidate.to_dict(), "dataset": spec["dataset"],
                                                        "training_code_sha256": model["training_code_sha256"]}),
                          "training_code_sha256": model["training_code_sha256"],
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
                **({"proposal": json.loads(row["proposal_json"])} if row["proposal_json"] else {}),
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
            spec = self._spec(c)
            self._verify_dataset(spec)
            final = {"best_trial_id": c["best_trial_id"], "model_sha256": result["model_sha256"],
                     "evidence_type": spec["dataset"]["evidence_type"], "dataset_id": spec["dataset"]["dataset_id"],
                     "data_sha256": spec["dataset"]["data_sha256"],
                     **training.terminal_evaluation(json.loads(payload))}
            con.execute("UPDATE campaigns SET status='finalized',final_json=? WHERE id=?", (canonical(final), campaign_id))
        return final
