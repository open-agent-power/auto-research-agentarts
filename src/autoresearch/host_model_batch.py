"""One explicit bounded CLI batch; each decision remains in the original host journal."""
import copy
import hashlib
import json
import math
import os
from pathlib import Path
import re

from .contracts import ResearchError, canonical, fingerprint
from .host_model_selection import HostModelSelection, PENDING
from .project_controller import ProjectController
from .research_project import ResearchProject, safe_path, require
from .source_evidence_adapter import _read_file

MAX_RECEIPT_BYTES = 128 * 1024


def _delegated_code_identity():
    """Bind the implementation files used by delegated batch scheduling and preparation."""
    directory = Path(__file__).parent
    names = ("host_model_batch.py", "host_model_selection.py", "host_selection_protocol.py",
             "research_plan_proposal.py", "plan_feedback.py", "saved_materials.py",
             "project_controller.py", "project_selection.py", "research_recipe.py", "research_project.py")
    return {name: hashlib.sha256((directory / name).read_bytes()).hexdigest() for name in names}


_DELEGATED_BOOT_IDENTITY = _delegated_code_identity()


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
        require((record["schema_version"], record["implementation_version"]) in
                (("host-model-batch-v1", 1), ("host-model-batch-v2", 2)) and record["request_id"] == request_id
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

    def _begin_delegated(self, body):
        path = self._path(body["request_id"])
        if path.exists():
            record = self._load(body["request_id"])
            require(record["schema_version"] == "host-model-batch-v2" and record["body"] == body,
                    "IDEMPOTENCY_CONFLICT", "Original delegated batch parameters cannot change.")
            return record
        require(_delegated_code_identity() == _DELEGATED_BOOT_IDENTITY, "CODE_CHANGED", "Restart with the original delegated batch implementation.")
        current = self.project.status()
        require(current["state_version"] == body["expected_state_version"], "STALE_STATE", "Initial project version differs.")
        grant = self.journal.status()["grant"]
        require(grant is None or all(grant[key] == body[key] for key in ("decision_limit", "cli_budget_usd", "reason")),
                "HOST_GRANT_CHANGED", "Batch cannot replace or reset the original global host grant.")
        context = ProjectController(self.project.root).selection_context()
        record = {"schema_version": "host-model-batch-v2", "request_id": body["request_id"],
                  "body": copy.deepcopy(body), "project_id": current["id"], "run_id": current["run_id"],
                  "source_snapshot_sha256": current["source_snapshot_sha256"],
                  "initial_snapshot_ref": current["snapshot_ref"], "cursor_snapshot_ref": current["snapshot_ref"],
                  "allowed_source_receipt_sha256s": _sources(current),
                  "allowed_methods": [item["method_id"] for item in context["conditions"]],
                  "implementation_version": 2, "record_status": "incomplete", "status": "prepared",
                  "steps": [], "plan_step": None, "stop": None, "scientific_validation": False,
                  "delegated_inference_and_cost": "unknown", "code_identity": copy.deepcopy(_DELEGATED_BOOT_IDENTITY)}
        self._save(record)
        return record

    def _prepare_delegated(self, record, purpose):
        from . import host_selection_protocol, research_plan_proposal
        state, body = self.project.status(), record["body"]
        require(state["snapshot_ref"] == record["cursor_snapshot_ref"], "STALE_STATE", "Project changed outside this batch.")
        require(_sources(state) == record["allowed_source_receipt_sha256s"], "SOURCE_SCOPE_CHANGED", "Source receipts changed.")
        host = self.journal.status()
        require(not any(item["status"] in PENDING for item in host["requests"]),
                "HOST_SELECTION_PENDING", "Resolve the original pending host request without replacement.")
        require(host["usage"]["decision_slots_used"] < body["decision_limit"], "HOST_DECISION_LIMIT", "Global host decision limit is exhausted.")
        require(not host["usage"]["cli_cost_unknown"], "HOST_USAGE_UNKNOWN", "Earlier CLI usage is unknown, not zero.")
        require(host["usage"]["known_cli_reported_cost_usd"] < body["cli_budget_usd"],
                "HOST_CLI_BUDGET_EXHAUSTED", "Global reported CLI estimate cap is exhausted.")
        selection = ProjectController(self.project.root).selection_context()
        if selection["blockers"]:
            return self._finish(record, "blocked", "HOST_BLOCKED", "Host blockers prevent the next request.")
        if purpose == "selection" and not selection["candidates"]:
            return self._finish(record, "waiting", "NO_HOST_CANDIDATES", "No eligible action is available.")
        require(all(item["method_id"] in record["allowed_methods"]
                    and ("receipt_snapshot_sha256" not in item["parameters"]
                         or item["parameters"]["receipt_snapshot_sha256"] in record["allowed_source_receipt_sha256s"])
                    for item in selection["candidates"]), "BATCH_SCOPE_CHANGED", "Current candidates exceed the frozen scope.")
        context = selection if purpose == "selection" else research_plan_proposal.build_context(self.project)
        require((context if purpose == "selection" else context["selection_context"]) == selection,
                "STALE_STATE", "Project changed while preparing the original context.")
        prompt = (host_selection_protocol.build_prompt(context) if purpose == "selection"
                  else research_plan_proposal.build_prompt(context))
        ordinal = len(record["steps"]) + 1
        request_id = "hostbatch-" + body["request_id"] + ("-s" + str(ordinal) if purpose == "selection" else "-plan")
        step = {"purpose": purpose, "host_request_id": request_id, "expected_state_version": state["state_version"],
                "context_sha256": fingerprint(context), "prompt_sha256": fingerprint(prompt),
                "snapshot_ref_before": state["snapshot_ref"], "host_status": "preparing", "outcome_status": None}
        if purpose == "selection":
            step["ordinal"] = ordinal
            record["steps"].append(step)
        else:
            record["plan_step"] = step
        self._save(record)  # Preserve the original Host ID and frozen identities before Host preparation.
        return None

    def _step_delegated(self, record, step):
        body, purpose = record["body"], step["purpose"]
        existing = self.journal._load()["requests"].get(step["host_request_id"])
        if existing is None:
            require(self.project.status()["snapshot_ref"] == step["snapshot_ref_before"],
                    "STALE_STATE", "Undispatched batch step changed; do not replace its frozen context.")
        model = self.journal.prepare(request_id=step["host_request_id"], provider="delegated",
            expected_state_version=step["expected_state_version"], decision_limit=body["decision_limit"],
            cli_budget_usd=body["cli_budget_usd"], reason=body["reason"], purpose=purpose,
            reconcile_completed=purpose == "selection")
        require(model.get("request_id") == step["host_request_id"]
                and model.get("controller_request_id") == step["host_request_id"]
                and model.get("provider") == "delegated" and model.get("purpose", "selection") == purpose,
                "EVIDENCE_CHANGED", "Host request identity differs from the original delegated step.")
        require(fingerprint(model.get("context")) == step["context_sha256"]
                and fingerprint(model.get("prompt")) == step["prompt_sha256"],
                "EVIDENCE_CHANGED", "Host request differs from the original batch context or prompt.")
        host_status = model.get("status")
        if (host_status not in ("prepared", "received", "sending", "unknown", "applied", "invalid", "stale", "failed", "rejected", "proposed")
                or (purpose == "selection" and host_status in ("proposed", "rejected"))):
            return self._finish(record, "needs_review", "HOST_STATUS_UNKNOWN",
                                "Inspect the original Host request; no replacement request was prepared.", incomplete=True)
        if model["status"] == "received":
            model = self.journal.consume(request_id=step["host_request_id"])
        if (purpose == "selection" and model.get("status") == "applied"
                and type(model.get("outcome")) is dict and model["outcome"].get("status") == "unknown"):
            try:
                model = self.journal.reconcile_outcome(request_id=step["host_request_id"])
            except ResearchError as error:
                return self._finish(record, "needs_review", error.code, str(error), incomplete=True)
        outcome = model.get("outcome")
        if not isinstance(outcome, dict):
            outcome = {}
        step.update(host_status=model["status"], controller_request_id=model["controller_request_id"],
                    outcome_status=outcome.get("status"), child_request_id=outcome.get("child_request_id"))
        self._save(record)
        if model["status"] == "prepared":
            return self._finish(record, "awaiting_external_response", "HOST_RESPONSE_REQUIRED",
                                "Import the original delegated response; no model was dispatched.", incomplete=True)
        if model["status"] in ("sending", "unknown"):
            return self._finish(record, "needs_review", "HOST_REQUEST_UNKNOWN",
                                "Reconcile the original Host request; no automatic resend.", incomplete=True)
        if purpose == "plan":
            if model["status"] == "proposed":
                return self._finish(record, "awaiting_adoption", "PLAN_ADOPTION_REQUIRED",
                                    "Explicitly adopt or reject the original proposed plan.", incomplete=True)
            if model["status"] == "applied":
                current = self.project.status()
                plan = outcome.get("research_plan")
                if (type(plan) is not dict or outcome.get("status") != "completed"
                        or outcome.get("kind") != "plan_revision"
                        or outcome.get("state_version") != step["expected_state_version"] + 1):
                    return self._finish(record, "needs_review", "PLAN_RESULT_UNKNOWN",
                                        "Inspect the original plan request and saved revision; no replacement request was prepared.", incomplete=True)
                if not (type(current.get("plan_revisions")) is list and bool(current["plan_revisions"])
                        and current["plan_revisions"][-1] == plan
                        and plan.get("request_id") == model["controller_request_id"]
                        and plan.get("based_on_state_version") == step["expected_state_version"]
                        and current.get("state_version") == step["expected_state_version"] + 1):
                    return self._finish(record, "needs_review", "PLAN_RESULT_CHANGED",
                                        "The adopted plan does not match the original saved revision and project state.", incomplete=True)
                step["snapshot_ref_after"] = current["snapshot_ref"]
                record["cursor_snapshot_ref"] = current["snapshot_ref"]
                return self._finish(record, "plan_adopted", "PLAN_ADOPTED", "The original plan was explicitly adopted.")
            return self._finish(record, model["status"], "PLAN_RESPONSE_STOP", "The original plan request stopped.")
        if model["status"] != "applied":
            return self._finish(record, model["status"], "HOST_RESPONSE_STOP", "Original Host response is terminal.")
        if outcome.get("status") not in ("completed", "failed", "rejected", "waiting", "needs_review"):
            return self._finish(record, "needs_review", "CONTROLLER_UNKNOWN",
                                "Inspect the original Controller ID; the cached Host outcome does not automatically converge or resend.", incomplete=True)
        if outcome.get("status") != "completed":
            return self._finish(record, outcome.get("status", "unknown"), "CONTROLLER_STOP",
                                "Original controller did not complete an action.", incomplete=outcome.get("status") == "unknown")
        current = self.project.status()
        result = outcome.get("result")
        if (type(result) is not dict or type(result.get("child")) is not dict
                or any(type(current.get(key)) is not list for key in ("controller_requests", "actions", "evidence_actions"))
                or any(type(item) is not dict for key in ("controller_requests", "actions", "evidence_actions") for item in current[key])):
            return self._finish(record, "needs_review", "CONTROLLER_RESULT_UNKNOWN",
                                "Inspect the original Controller and child records; no replacement was prepared.", incomplete=True)
        parents = [item for item in current["controller_requests"] if item.get("request_id") == step["host_request_id"]]
        child = result["child"]
        stored_children = [item for item in current.get("actions", []) + current.get("evidence_actions", [])
                           if item.get("request_id") == outcome.get("child_request_id")]
        require(len(parents) == 1 and parents[0].get("status") == "completed"
                and outcome.get("project_id") == current["id"] and outcome.get("request_id") == step["host_request_id"]
                and parents[0].get("child_request_id") == outcome.get("child_request_id")
                and outcome.get("child_request_id") is not None
                and child.get("status") == "completed" and child.get("request_id") == outcome.get("child_request_id")
                and len(stored_children) == 1 and stored_children[0].get("status") == "completed"
                and stored_children[0].get("id") == child.get("id")
                and stored_children[0].get("project_id") == current["id"]
                and stored_children[0].get("run_id") == current["run_id"]
                and current["state_version"] == parents[0].get("state_version_after"),
                "STALE_STATE", "The original completed controller child or project state differs.")
        child_fields = ("id", "request_id", "command", "status", "artifact", "result_sha256", "failure")
        if (parents[0].get("result") != result
                or child != {key: stored_children[0][key] for key in child_fields if key in stored_children[0]}):
            return self._finish(record, "needs_review", "CONTROLLER_RESULT_CHANGED",
                                "The Host result differs from the original saved Controller or child result.", incomplete=True)
        require(_sources(current) == record["allowed_source_receipt_sha256s"], "SOURCE_SCOPE_CHANGED", "Source receipts changed.")
        step["snapshot_ref_after"] = current["snapshot_ref"]
        record["cursor_snapshot_ref"] = current["snapshot_ref"]
        self._save(record)
        return None

    def advance_delegated(self, *, request_id, expected_state_version, max_decisions, decision_limit,
                          cli_budget_usd, reason, post_action_plan=False):
        """Prepare/resume delegated selections; never dispatch a model or adopt a plan.

        max_decisions counts selection steps; an optional plan uses one additional original Host slot.
        """
        self._path(request_id)
        require(type(expected_state_version) is int and expected_state_version >= 0
                and type(max_decisions) is int and 1 <= max_decisions <= 2
                and type(decision_limit) is int and 1 <= decision_limit <= 8
                and type(cli_budget_usd) in (int, float) and math.isfinite(cli_budget_usd) and 0 < cli_budget_usd <= .10
                and type(reason) is str and bool(reason.strip()) and len(reason) <= 1000 and "\0" not in reason
                and type(post_action_plan) is bool, "INVALID_REQUEST", "Use bounded original Host limits and an explicit plan choice.")
        body = {"request_id": request_id, "expected_state_version": expected_state_version, "max_decisions": max_decisions,
                "decision_limit": decision_limit, "cli_budget_usd": cli_budget_usd, "reason": reason,
                "provider": "delegated", "post_action_plan": post_action_plan}
        self.project.status()
        with self.journal._writer():
            self.directory.mkdir(exist_ok=True)
        with ResearchProject(self.directory)._writer():
            record = self._begin_delegated(body)
            if record["record_status"] == "completed":
                return copy.deepcopy(record)
            require(record.get("code_identity") == _DELEGATED_BOOT_IDENTITY == _delegated_code_identity(),
                    "CODE_CHANGED", "Resume the original batch using its original implementation; do not replace its requests.")
            try:
                while True:
                    if record["plan_step"] is not None:
                        return self._step_delegated(record, record["plan_step"])
                    if record["steps"] and not record["steps"][-1].get("snapshot_ref_after"):
                        stopped = self._step_delegated(record, record["steps"][-1])
                        if stopped is not None:
                            return stopped
                        continue
                    reached_limit = len(record["steps"]) >= max_decisions
                    current = ProjectController(self.project.root).selection_context()
                    if reached_limit or (record["steps"] and not current["candidates"] and not current["blockers"]):
                        if post_action_plan and record["steps"]:
                            stopped = self._prepare_delegated(record, "plan")
                            if stopped is not None:
                                return stopped
                            continue
                        return self._finish(record, "limit_reached" if reached_limit else "waiting", "MAX_DECISIONS" if reached_limit else "NO_HOST_CANDIDATES",
                                            "The original selection limit was reached." if reached_limit else "No eligible action is available.")
                    stopped = self._prepare_delegated(record, "selection")
                    if stopped is not None:
                        return stopped
            except ResearchError as error:
                return self._finish(record, "blocked", error.code, str(error),
                                    incomplete=error.code in ("PROJECT_BUSY", "HOST_SELECTION_PENDING", "CODE_CHANGED", "HOST_RESPONSE_NOT_READY"))
