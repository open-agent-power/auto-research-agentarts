"""One explicit bounded CLI batch; each decision remains in the original host journal."""
import copy
import json
import math
import os
from pathlib import Path
import re

from .contracts import ResearchError, canonical
from .host_model_selection import HostModelSelection, PENDING
from .project_controller import ProjectController
from .research_project import ResearchProject, safe_path, require
from .source_evidence_adapter import _read_file

MAX_RECEIPT_BYTES = 128 * 1024


def _sources(project):
    return sorted(item["receipt_snapshot_sha256"] for item in project.get("evidence_sources", []))


class HostModelBatch:
    def __init__(self, workspace):
        self.journal = HostModelSelection(workspace)
        self.project = self.journal.project
        self.directory = safe_path(self.journal.directory / "batches")

    def _path(self, request_id):
        require(type(request_id) is str and re.fullmatch(r"[A-Za-z0-9_-]{1,60}", request_id),
                "INVALID_REQUEST", "Batch ID requires 1..60 ASCII letters, numbers, underscore or hyphen.")
        return safe_path(self.directory / ("batch-" + request_id + ".json"))

    def _load(self, request_id):
        record = json.loads(_read_file(self._path(request_id), MAX_RECEIPT_BYTES).decode("utf-8"))
        require(record["schema_version"] == "host-model-batch-v1" and record["request_id"] == request_id
                and record["implementation_version"] == 1
                and record["project_id"] == self.project.status()["id"],
                "EVIDENCE_CHANGED", "Batch receipt identity differs from its original request or project.")
        return record

    def _save(self, record):
        with self.journal._writer():
            path = self._path(record["request_id"])
            pending = safe_path(path.with_suffix(".pending.json"))
            raw = canonical(record).encode("utf-8")
            require(len(raw) <= MAX_RECEIPT_BYTES, "HOST_BATCH_FULL", "Bounded batch receipt is full.")
            with pending.open("wb") as stream:
                stream.write(raw); stream.flush(); os.fsync(stream.fileno())
            pending.replace(path)

    def status(self, *, request_id):
        path = self._path(request_id)
        require(path.is_file(), "ARTIFACT_NOT_FOUND", "No host-model batch matches this ID.")
        return copy.deepcopy(self._load(request_id))

    def _finish(self, record, status, code, reason, *, incomplete=False):
        record.update(record_status="incomplete" if incomplete else "completed", status=status,
                      stop={"code": code, "reason": reason, "automatic_retry": False})
        self._save(record)
        return copy.deepcopy(record)

    def _begin(self, body):
        path = self._path(body["request_id"])
        if path.exists():
            record = self._load(body["request_id"])
            require(record["body"] == body, "IDEMPOTENCY_CONFLICT", "Original batch parameters cannot change.")
            return record
        current = self.project.status()
        require(current["state_version"] == body["expected_state_version"], "STALE_STATE", "Initial project version differs.")
        grant = self.journal.status()["grant"]
        require(grant is None or all(grant[key] == body[key] for key in ("decision_limit", "cli_budget_usd", "reason")),
                "HOST_GRANT_CHANGED", "Batch cannot replace or reset the original global host grant.")
        context = ProjectController(self.project.root).selection_context()
        record = {"schema_version": "host-model-batch-v1", "request_id": body["request_id"],
            "body": copy.deepcopy(body), "project_id": current["id"],
            "run_id": current["run_id"], "source_snapshot_sha256": current["source_snapshot_sha256"],
            "initial_snapshot_ref": current["snapshot_ref"], "cursor_snapshot_ref": current["snapshot_ref"],
            "allowed_source_receipt_sha256s": _sources(current),
            "allowed_methods": [item["method_id"] for item in context["conditions"]],
            "implementation_version": 1, "record_status": "incomplete", "status": "prepared",
            "steps": [], "stop": None, "scientific_validation": False}
        self._save(record)
        return record

    def _prepare_step(self, record):
        state, body = self.project.status(), record["body"]
        require(state["snapshot_ref"] == record["cursor_snapshot_ref"], "STALE_STATE", "Project changed outside this batch.")
        require(_sources(state) == record["allowed_source_receipt_sha256s"],
                "SOURCE_SCOPE_CHANGED", "New sources are outside the frozen batch authorization.")
        host = self.journal.status()
        require(not any(item["status"] in PENDING for item in host["requests"]),
                "HOST_SELECTION_PENDING", "Resolve the original pending host request without creating a replacement.")
        require(host["usage"]["decision_slots_used"] < body["decision_limit"], "HOST_DECISION_LIMIT", "Global host decision limit is exhausted.")
        require(not host["usage"]["cli_cost_unknown"], "HOST_USAGE_UNKNOWN", "Earlier CLI usage is unknown, not zero.")
        require(host["usage"]["known_cli_reported_cost_usd"] < body["cli_budget_usd"],
                "HOST_CLI_BUDGET_EXHAUSTED", "Global reported CLI estimate cap is exhausted.")
        context = ProjectController(self.project.root).selection_context()
        if context["blockers"] or not context["candidates"]:
            return self._finish(record, "blocked" if context["blockers"] else "waiting", "NO_HOST_CANDIDATES",
                                "No eligible action is available; do not request a model merely to wait.")
        require(all(item["method_id"] in record["allowed_methods"]
                    and ("receipt_snapshot_sha256" not in item["parameters"]
                         or item["parameters"]["receipt_snapshot_sha256"] in record["allowed_source_receipt_sha256s"])
                    for item in context["candidates"]),
                "BATCH_SCOPE_CHANGED", "Current candidates exceed the original methods or exact source receipts.")
        ordinal = len(record["steps"]) + 1
        step = {"ordinal": ordinal, "host_request_id": "hostbatch-" + body["request_id"] + "-s" + str(ordinal),
                "expected_state_version": context["state_version"], "context_sha256": context["context_sha256"],
                "snapshot_ref_before": state["snapshot_ref"], "host_status": "prepared", "outcome_status": None}
        record["steps"].append(step)
        self._save(record)
        return None

    def _step(self, record):
        body, step = record["body"], record["steps"][-1]
        existing = self.journal._load()["requests"].get(step["host_request_id"])
        if existing is None:
            require(self.project.status()["snapshot_ref"] == step["snapshot_ref_before"],
                    "STALE_STATE", "Undispatched batch step changed; do not replace its frozen context.")
        model = self.journal.prepare(request_id=step["host_request_id"], provider="claude_cli", executable=body["executable"],
            expected_state_version=step["expected_state_version"], decision_limit=body["decision_limit"],
            cli_budget_usd=body["cli_budget_usd"], reason=body["reason"])
        require(model["context"]["context_sha256"] == step["context_sha256"],
                "EVIDENCE_CHANGED", "Host request differs from the original batch step context.")
        model = self.journal.request(request_id=step["host_request_id"])
        if model["status"] == "received":
            model = self.journal.consume(request_id=step["host_request_id"])
        outcome = model.get("outcome") or {}
        step.update(host_status=model["status"], controller_request_id=model["controller_request_id"],
                    outcome_status=outcome.get("status"), child_request_id=outcome.get("child_request_id"))
        self._save(record)
        if model["status"] in PENDING:
            return self._finish(record, "unknown", "HOST_REQUEST_PENDING", "Original host request remains unresolved; never resend it.", incomplete=True)
        if model["status"] != "applied":
            return self._finish(record, model["status"], "HOST_RESPONSE_STOP", "Original host response is terminal; no replacement decision.")
        if outcome.get("status") != "completed":
            return self._finish(record, outcome.get("status", "unknown"), "CONTROLLER_STOP", "Original controller did not complete an action.",
                                incomplete=outcome.get("status") == "unknown")
        current = self.project.status()
        parent = next(item for item in current["controller_requests"] if item["request_id"] == step["host_request_id"])
        require(current["state_version"] == parent["state_version_after"], "STALE_STATE", "Project changed after the original batch action.")
        require(_sources(current) == record["allowed_source_receipt_sha256s"],
                "SOURCE_SCOPE_CHANGED", "New sources are outside the frozen batch authorization.")
        step["snapshot_ref_after"] = current["snapshot_ref"]
        record["cursor_snapshot_ref"] = current["snapshot_ref"]
        self._save(record)
        return None

    def advance(self, *, request_id, expected_state_version, max_decisions, decision_limit, cli_budget_usd, reason, executable):
        self._path(request_id)
        require(type(expected_state_version) is int and expected_state_version >= 0
                and type(max_decisions) is int and 1 <= max_decisions <= 2
                and type(decision_limit) is int and 1 <= decision_limit <= 8
                and type(cli_budget_usd) in (int, float) and math.isfinite(cli_budget_usd) and 0 < cli_budget_usd <= .10
                and type(reason) is str and bool(reason.strip()) and len(reason) <= 1000 and "\0" not in reason,
                "INVALID_REQUEST", "Use explicit original version, one or two decisions and bounded original host limits.")
        require(executable is not None and Path(executable).is_file(), "CLI_NOT_FOUND", "Select an existing native CLI executable.")
        body = {"request_id": request_id, "expected_state_version": expected_state_version, "max_decisions": max_decisions,
                "decision_limit": decision_limit, "cli_budget_usd": cli_budget_usd, "reason": reason,
                "executable": str(Path(executable).absolute())}
        self.project.status()
        with self.journal._writer():
            self.directory.mkdir(exist_ok=True)
        with ResearchProject(self.directory)._writer():
            record = self._begin(body)
            if record["record_status"] == "completed":
                return copy.deepcopy(record)
            try:
                while True:
                    if not record["steps"] or record["steps"][-1].get("snapshot_ref_after"):
                        if len(record["steps"]) >= max_decisions:
                            return self._finish(record, "limit_reached", "MAX_DECISIONS", "The explicit batch decision limit was reached.")
                        stopped = self._prepare_step(record)
                        if stopped is not None:
                            return stopped
                    stopped = self._step(record)
                    if stopped is not None:
                        return stopped
            except ResearchError as error:
                step = record["steps"][-1] if record["steps"] else None
                original = self.journal._load()["requests"].get(step["host_request_id"]) if step else None
                if original is not None and original["status"] in PENDING:
                    step["host_status"] = original["status"]
                    return self._finish(record, "unknown", error.code, str(error), incomplete=True)
                return self._finish(record, "blocked", error.code, str(error),
                                    incomplete=error.code in ("PROJECT_BUSY", "HOST_SELECTION_PENDING", "CODE_CHANGED"))
