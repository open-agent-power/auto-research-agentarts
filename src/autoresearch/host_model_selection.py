"""Durable host decisions; external usage stays distinct from native Qwen history."""
import copy
import hashlib
import json
import math
import os
from pathlib import Path
import re

from . import host_selection_protocol as protocol
from . import research_plan_proposal as plan_protocol
from . import recipe_change_proposal as recipe_protocol
from .claude_selection_transport import run_claude_selection
from .contracts import ResearchError, canonical, fingerprint, identifier
from . import project_controller, project_selection, project_selection_view, research_project
from .project_controller import ProjectController
from .research_project import ResearchProject, safe_path, write_bytes_once
from .source_evidence_adapter import _read_file
from .saved_materials import normalize_requests

PENDING = {"prepared", "sending", "unknown", "received"}
MAX_STATE_BYTES = 2 * 1024 * 1024
OBSERVED_RECONCILE = "host-observed-controller-completion-v1"


def _reconcile_code_identity():
    directory = Path(__file__).parent
    names = ("host_model_selection.py", "host_selection_protocol.py", "project_controller.py",
             "project_selection.py", "project_selection_view.py", "method_registry.py", "research_recipe.py", "research_project.py")
    return {name: hashlib.sha256((directory / name).read_bytes()).hexdigest() for name in names}


_RECONCILE_BOOT_IDENTITY = _reconcile_code_identity()


def _require(condition, code, message):
    if not condition:
        raise ResearchError(code, message)


def _cli_metadata(raw):
    try:
        return protocol.parse_cli_usage(raw)
    except ResearchError:
        return {"reported_models": None, "reported_usage": None, "reported_cost_usd": None}


def _request_protocol(purpose):
    return {"selection": protocol, "plan": plan_protocol, "recipe": recipe_protocol}[purpose]


class HostModelSelection:
    def __init__(self, workspace):
        self.project = ResearchProject(workspace)
        self.directory = safe_path(self.project.root / "host-model-selections")
        self.state_file = safe_path(self.directory / "state.json")

    def _writer(self):
        self.directory.mkdir(exist_ok=True)
        return ResearchProject(self.directory)._writer()

    def _load(self):
        project = self.project.status()
        if not self.state_file.exists():
            return {"schema_version": "host-model-selections-v1", "project_id": project["id"],
                    "grant": None, "requests": {}}
        state = json.loads(_read_file(self.state_file, MAX_STATE_BYTES).decode("utf-8"))
        _require(state["schema_version"] == "host-model-selections-v1" and state["project_id"] == project["id"],
                 "EVIDENCE_CHANGED", "Host request ledger belongs to a different project.")
        return state

    def _save(self, state):
        self.directory.mkdir(parents=True, exist_ok=True)
        temporary = safe_path(self.directory / "state.pending.json")
        raw = canonical(state).encode("utf-8")
        _require(len(raw) <= MAX_STATE_BYTES, "HOST_LEDGER_FULL", "Bounded host request ledger is full.")
        with temporary.open("wb") as stream:
            stream.write(raw); stream.flush(); os.fsync(stream.fileno())
        temporary.replace(self.state_file)

    @staticmethod
    def _record(state, request_id):
        identifier(request_id)
        record = state["requests"].get(request_id)
        _require(record is not None, "ARTIFACT_NOT_FOUND", "No prepared host-model request matches this ID.")
        return record

    def _fresh(self, record):
        purpose = record.get("purpose", "selection")
        specification = record["prepare_specification"]
        materials = {"saved_materials": specification["saved_materials"]} if specification.get("saved_materials") else {}
        if purpose == "recipe":
            current = recipe_protocol.build_context(self.project, specification["current_recipe"], specification["improvement_goal"], **materials)
        elif purpose == "plan":
            current = plan_protocol.build_context(self.project, **materials)
        else:
            current = ProjectController(self.project.root).selection_context()
        _require(current == record["context"], "STALE_SELECTION_CONTEXT",
                 "The frozen host context changed; do not request a model on a new context under this ID.")

    def _materialize(self, record):
        folder = safe_path(self.directory / record["directory"])
        folder.mkdir(parents=True, exist_ok=True)
        write_bytes_once(folder / "context.json", canonical(record["context"]).encode("utf-8"))
        write_bytes_once(folder / "prompt.json", canonical(record["prompt"]).encode("utf-8"))

    def prepare(self, *, request_id, provider, expected_state_version, decision_limit, cli_budget_usd,
                reason, executable=None, purpose="selection", current_recipe=None, improvement_goal=None,
                saved_materials=None, reconcile_completed=False):
        identifier(request_id)
        _require(type(reconcile_completed) is bool and (not reconcile_completed or (provider == "delegated" and purpose == "selection")),
                 "INVALID_REQUEST", "Observed completion reconciliation is limited to explicitly enabled delegated selections.")
        _require(purpose in ("selection", "plan", "recipe"), "INVALID_REQUEST", "Choose a selection, plan or recipe request purpose.")
        _require(purpose == "recipe" or (current_recipe is None and improvement_goal is None),
                 "INVALID_REQUEST", "Recipe input and improvement goal belong to recipe requests.")
        selectors = normalize_requests(saved_materials)
        _require(purpose != "selection" or not selectors, "INVALID_REQUEST", "Saved materials belong to plan or recipe requests.")
        _require(provider in ("claude_cli", "delegated") and type(decision_limit) is int and 1 <= decision_limit <= 8,
                 "INVALID_REQUEST", "Choose claude_cli/delegated and a prospective decision limit from 1 to 8.")
        _require(type(cli_budget_usd) in (int, float) and math.isfinite(cli_budget_usd) and 0 < cli_budget_usd <= 0.10,
                 "INVALID_REQUEST", "Set a configured cumulative CLI estimate threshold, at most 0.10 USD; reported usage may exceed it.")
        _require(type(reason) is str and bool(reason.strip()) and len(reason) <= 1000 and "\0" not in reason,
                 "INVALID_REQUEST", "Record the actual operator-authorized scope; this declaration grants no permission.")
        _require(type(expected_state_version) is int and expected_state_version >= 0,
                 "INVALID_REQUEST", "Bind the expected project version.")
        if provider == "claude_cli":
            _require(executable is not None and Path(executable).is_file(), "CLI_NOT_FOUND", "Select an existing Claude CLI executable.")
            executable = str(Path(executable).absolute())
        else:
            _require(executable is None, "INVALID_REQUEST", "Delegated imports do not launch an executable.")
        grant = {"decision_limit": decision_limit, "cli_budget_usd": cli_budget_usd, "reason": reason,
                 "cash_settlement": "unknown", "scope": "prospective host requests; native and previous external history is not reset"}
        specification = {"request_id": request_id, "provider": provider, "expected_state_version": expected_state_version,
                         "grant": grant, "executable": executable}
        if purpose != "selection":
            specification["purpose"] = purpose
        if purpose == "recipe":
            specification.update(current_recipe=copy.deepcopy(current_recipe), improvement_goal=improvement_goal)
        if selectors:
            specification["saved_materials"] = selectors
        if reconcile_completed:
            _require(_RECONCILE_BOOT_IDENTITY == _reconcile_code_identity(), "CODE_CHANGED", "Restart with the original Host implementation.")
            specification["observed_reconciliation"] = {"schema_version": OBSERVED_RECONCILE,
                                                         "code_identity": copy.deepcopy(_RECONCILE_BOOT_IDENTITY)}
        with self._writer():
            state = self._load()
            old = state["requests"].get(request_id)
            if old is not None:
                _require(old["prepare_specification"] == specification, "IDEMPOTENCY_CONFLICT", "Original host preparation differs.")
                self._materialize(old)
                return copy.deepcopy(old)
            _require(state["grant"] is None or state["grant"] == grant,
                     "HOST_GRANT_CHANGED", "The original prospective host limit cannot be replaced or reset.")
            _require(len(state["requests"]) < decision_limit, "HOST_DECISION_LIMIT", "The cumulative host decision limit is exhausted.")
            _require(not any(r["status"] in PENDING for r in state["requests"].values()),
                     "HOST_SELECTION_PENDING", "Resolve the original pending/unknown request; do not start another decision.")
            materials = {"saved_materials": selectors} if selectors else {}
            if purpose == "recipe":
                context = recipe_protocol.build_context(self.project, current_recipe, improvement_goal, **materials)
                selection = context["research_context"]["selection_context"]
            elif purpose == "plan":
                context = plan_protocol.build_context(self.project, **materials)
                selection = context["selection_context"]
            else:
                context = ProjectController(self.project.root).selection_context()
                selection = context
            _require(selection["state_version"] == expected_state_version, "STALE_STATE", "Project version differs.")
            if purpose != "selection":
                _require(not selection["blockers"], "SELECTION_BLOCKED", "Resolve the saved execution or code blocker before requesting a proposal.")
                _require(not self.project.status()["budget"].get("model_requests_reserved", 0),
                         "PROJECT_BUSY", "Complete the reserved native model request before requesting a proposal.")
            else:
                _require(not selection["blockers"] and bool(selection["candidates"]), "NO_HOST_CANDIDATES",
                         "No eligible action is available; preserve the evidence task instead of spending a model call.")
            prompt = _request_protocol(purpose).build_prompt(context)
            relative = "requests/" + str(len(state["requests"]) + 1).zfill(4)
            record = {"request_id": request_id, "provider": provider, "prepare_specification": specification,
                      "directory": relative, "context": context, "prompt": prompt, "status": "prepared",
                      "controller_request_id": request_id, "cli_launch_attempted": False,
                      "scientific_validation": False}
            if purpose != "selection":
                record["purpose"] = purpose
            state["grant"] = grant
            state["requests"][request_id] = record
            self._save(state)
            self._materialize(record)
            return copy.deepcopy(record)

    def _receive(self, state, record, raw, response_file):
        record.update(response_file=response_file, response_sha256=hashlib.sha256(raw).hexdigest())
        record.update(_cli_metadata(raw) if record["provider"] == "claude_cli" else {"reported_cost_usd": None})
        try:
            response_protocol = _request_protocol(record.get("purpose", "selection"))
            parsed = (response_protocol.parse_host_response(raw, record["provider"], context=record["context"])
                      if record.get("purpose", "selection") == "selection"
                      else response_protocol.parse_host_response(raw, record["provider"]))
            record.update(parsed, status="received")
        except ResearchError as error:
            record.update(status="invalid", error={"code": error.code, "message": str(error)})
        self._save(state)
        return copy.deepcopy(record)

    def _read_transport(self, record):
        folder = safe_path(self.directory / record["directory"] / "transport")
        receipt = json.loads(_read_file(folder / "exit.json", 65536).decode("utf-8"))
        _require(receipt.get("status") in ("received", "failed", "unknown"), "EVIDENCE_CHANGED", "Invalid saved transport outcome.")
        launch = json.loads(_read_file(folder / "launch.json", 100000).decode("utf-8"))
        prompt = record["prompt"]["prompt"].encode("utf-8")
        _require(launch.get("stdin_sha256") == hashlib.sha256(prompt).hexdigest()
                 and launch.get("stdin_bytes") == len(prompt) and launch.get("argv", [None])[0] == record["prepare_specification"]["executable"]
                 and launch["argv"][-1] == record["prompt"]["system"]
                 and launch.get("configured_max_budget_usd") == record["cli_budget_at_launch_usd"],
                 "EVIDENCE_CHANGED", "Saved CLI launch does not bind the frozen prompt, executable and limit.")
        output = safe_path(folder / "stdout.bin")
        raw = output.read_bytes() if receipt.get("stdout_bytes") == 0 and output.stat().st_size == 0 else _read_file(output, protocol.MAX_RESPONSE_BYTES)
        _require(receipt.get("stdout_file") == "stdout.bin" and receipt.get("stdout_bytes") == len(raw)
                 and receipt.get("stdout_sha256") == hashlib.sha256(raw).hexdigest(),
                 "EVIDENCE_CHANGED", "Original transport output and receipt differ.")
        if receipt["status"] == "received":
            _require(receipt.get("exit_code") == 0, "EVIDENCE_CHANGED", "Received CLI result must have exit code zero.")
        return receipt, raw, record["directory"] + "/transport/stdout.bin"

    def _recover_transport(self, state, record):
        receipt, raw, response_file = self._read_transport(record)
        record["transport"] = receipt
        if receipt["status"] == "received":
            return self._receive(state, record, raw, response_file)
        record.update(status=receipt["status"], reported_cost_usd=None)
        if receipt["status"] == "failed":
            record.update(_cli_metadata(raw), response_file=response_file, response_sha256=hashlib.sha256(raw).hexdigest())
        self._save(state)
        return copy.deepcopy(record)

    def reconcile_usage(self, *, request_id):
        """Verify original CLI evidence and reconcile metadata only; never dispatch or consume."""
        with self._writer():
            state = self._load(); record = self._record(state, request_id)
            _require(record["provider"] == "claude_cli" and record["cli_launch_attempted"],
                     "INVALID_REQUEST", "Only an original launched CLI request has transport usage to reconcile.")
            receipt, raw, response_file = self._read_transport(record)
            _require("transport" not in record or record["transport"] == receipt,
                     "EVIDENCE_CHANGED", "Saved original CLI receipt differs from the host record.")
            response_sha256 = hashlib.sha256(raw).hexdigest()
            _require("response_file" not in record or (record["response_file"] == response_file
                     and record["response_sha256"] == response_sha256),
                     "EVIDENCE_CHANGED", "Saved original CLI response identity changed.")
            update = (_cli_metadata(raw) if receipt["status"] in ("received", "failed") else
                      {"reported_models": None, "reported_usage": None, "reported_cost_usd": None})
            if receipt["status"] in ("received", "failed"):
                update.update(response_file=response_file, response_sha256=response_sha256)
            if any(record.get(key) != value for key, value in update.items()):
                record.update(update)
                self._save(state)
            return copy.deepcopy(record)

    def request(self, *, request_id):
        with self._writer():
            state = self._load(); record = self._record(state, request_id)
            _require(record["provider"] == "claude_cli", "INVALID_REQUEST", "Use import-response for delegated decisions.")
            receipt_path = self.directory / record["directory"] / "transport/exit.json"
            if record["status"] in ("sending", "unknown") and receipt_path.exists():
                return self._recover_transport(state, record)
            if record["status"] != "prepared":
                return copy.deepcopy(record)
            try:
                self._fresh(record)
            except ResearchError as error:
                if error.code == "STALE_SELECTION_CONTEXT":
                    record.update(status="stale", error={"code": error.code, "message": str(error)})
                    self._save(state)
                raise
            previous = [r for r in state["requests"].values() if r["cli_launch_attempted"]]
            _require(all(r.get("reported_cost_usd") is not None for r in previous), "HOST_USAGE_UNKNOWN",
                     "Previous CLI usage is unknown; do not count it as zero or send again.")
            remaining = state["grant"]["cli_budget_usd"] - sum(r["reported_cost_usd"] for r in previous)
            _require(remaining > 0, "HOST_CLI_BUDGET_EXHAUSTED", "The configured cumulative CLI estimate threshold was reached; do not send another request.")
            folder = safe_path(self.directory / record["directory"] / "transport"); folder.mkdir(exist_ok=True)
            _require(not any(folder.iterdir()), "EVIDENCE_CHANGED", "Prepared transport evidence must be empty; do not overwrite or resend it.")
            record.update(status="sending", cli_launch_attempted=True, cli_budget_at_launch_usd=remaining)
            self._save(state)
            try:
                run_claude_selection(executable=record["prepare_specification"]["executable"], directory=folder,
                    system_prompt=record["prompt"]["system"], prompt=record["prompt"]["prompt"], max_budget_usd=remaining)
            except (OSError, ValueError, ResearchError) as error:
                record.update(status="unknown", error={"code": getattr(error, "code", type(error).__name__),
                              "message": "Transport may have started; preserve original evidence and never resend."})
                self._save(state)
                return copy.deepcopy(record)
            return self._recover_transport(state, record)

    def import_response(self, *, request_id, response_file):
        raw = _read_file(Path(response_file).absolute(), protocol.MAX_RESPONSE_BYTES)
        with self._writer():
            state = self._load(); record = self._record(state, request_id)
            _require(record["provider"] == "delegated", "INVALID_REQUEST", "Only a delegated response can be imported.")
            if record["status"] != "prepared":
                _require(record.get("response_sha256") == hashlib.sha256(raw).hexdigest(),
                         "IDEMPOTENCY_CONFLICT", "The original delegated output cannot be replaced.")
                return copy.deepcopy(record)
            relative = record["directory"] + "/delegated.bin"
            write_bytes_once(safe_path(self.directory / relative), raw)
            record["execution_declaration"] = {"kind": "operator_imported_delegated_output",
                "model": "unknown", "inference_count": "unknown", "cost": "unknown", "execution_verified": False}
            return self._receive(state, record, raw, relative)

    def consume(self, *, request_id):
        with self._writer():
            state = self._load(); record = self._record(state, request_id)
            if record["status"] in ("applied", "proposed", "rejected"):
                return copy.deepcopy(record)
            _require(record["status"] == "received", "HOST_RESPONSE_NOT_READY", "Only a complete received response may be consumed.")
            raw = _read_file(safe_path(self.directory / record["response_file"]), protocol.MAX_RESPONSE_BYTES)
            _require(hashlib.sha256(raw).hexdigest() == record["response_sha256"],
                     "EVIDENCE_CHANGED", "Original model response changed after receipt.")
            proposal_request = record.get("purpose") in ("plan", "recipe")
            response_protocol = _request_protocol(record.get("purpose", "selection"))
            parsed = (response_protocol.parse_host_response(raw, record["provider"], context=record["context"])
                      if record.get("purpose", "selection") == "selection"
                      else response_protocol.parse_host_response(raw, record["provider"]))
            label = ("Claude CLI; reported route " + (", ".join(parsed["reported_models"]) or "unknown")
                     if record["provider"] == "claude_cli" else "Operator-imported delegated decision; execution/model/usage unverified")
            try:
                proposal = response_protocol.build_proposal(record["context"], parsed["arguments"], label[:200])
                if proposal_request:
                    self._fresh(record)
                else:
                    outcome = ProjectController(self.project.root).advance_selection(request_id=record["controller_request_id"],
                        proposal=proposal, expected_state_version=record["context"]["state_version"])
            except ResearchError as error:
                record.update(status="stale" if error.code in ("STALE_STATE", "STALE_SELECTION_CONTEXT", "CODE_CHANGED") else "invalid",
                              error={"code": error.code, "message": str(error)})
                self._save(state)
                return copy.deepcopy(record)
            write_bytes_once(self.directory / record["directory"] / "proposal.json", canonical(proposal).encode("utf-8"))
            record.update(status="proposed" if proposal_request else "applied", proposal=proposal)
            if not proposal_request:
                record["outcome"] = outcome
            self._save(state)
            return copy.deepcopy(record)

    def reconcile_outcome(self, *, request_id):
        """Observe an already-completed original Controller; never resume or dispatch it.

        The Host ledger is updated; project locking may touch its lock file and SQLite
        may touch sidecars. No project database, action, or budget is written here.
        """
        identifier(request_id)
        _require(self.directory.is_dir() and self.state_file.is_file(), "ARTIFACT_NOT_FOUND", "The original Host ledger must already exist.")
        with self._writer():
            state = self._load()
            record = self._record(state, request_id)
            specification = record.get("prepare_specification")
            capability = specification.get("observed_reconciliation") if type(specification) is dict else None
            _require(type(capability) is dict and capability.get("schema_version") == OBSERVED_RECONCILE,
                     "HOST_RECONCILE_NOT_ENABLED", "The original request did not enable observed reconciliation.")
            _require(capability == {"schema_version": OBSERVED_RECONCILE, "code_identity": _RECONCILE_BOOT_IDENTITY}
                     and _RECONCILE_BOOT_IDENTITY == _reconcile_code_identity(), "CODE_CHANGED",
                     "Use the original reconciliation implementation; old requests are not upgraded.")
            _require(record.get("request_id") == record.get("controller_request_id") == request_id
                     and record.get("provider") == specification.get("provider") == "delegated"
                     and record.get("purpose", "selection") == "selection"
                     and specification.get("request_id") == request_id
                     and set(specification) == {"request_id", "provider", "expected_state_version", "grant", "executable", "observed_reconciliation"}
                     and specification.get("executable") is None
                     and specification.get("grant") == state.get("grant") and record.get("status") == "applied",
                     "EVIDENCE_CHANGED", "The original Host request or grant differs.")
            outcome = record.get("outcome")
            _require(type(outcome) is dict, "EVIDENCE_CHANGED", "The original Host outcome is missing.")
            previous = outcome if outcome.get("status") == "unknown" else record.get("previous_unknown")
            observation = record.get("outcome_observation")
            _require(type(previous) is dict and previous.get("status") == "unknown"
                     and (outcome.get("status") == "unknown" or
                          (outcome.get("status") == "completed" and type(observation) is dict
                           and observation.get("schema_version") == OBSERVED_RECONCILE)),
                     "EVIDENCE_CHANGED", "Only an original unknown outcome can be reconciled.")
            folder = record.get("directory")
            _require(type(folder) is str and re.fullmatch(r"requests/[0-9]{4}", folder) is not None
                     and record.get("response_file") == folder + "/delegated.bin",
                     "EVIDENCE_CHANGED", "The response must use the original controlled Host folder.")
            for name, key in (("context.json", "context"), ("prompt.json", "prompt"), ("proposal.json", "proposal")):
                _require(_read_file(safe_path(self.directory / folder / name), MAX_STATE_BYTES)
                         == canonical(record.get(key)).encode("utf-8"), "EVIDENCE_CHANGED", "The original Host evidence changed.")
            raw = _read_file(safe_path(self.directory / record["response_file"]), protocol.MAX_RESPONSE_BYTES)
            _require(hashlib.sha256(raw).hexdigest() == record.get("response_sha256"), "EVIDENCE_CHANGED", "The original response changed.")
            context = record["context"]
            parsed = protocol.parse_host_response(raw, "delegated", context=context)
            _require(all(record.get(key) == value for key, value in parsed.items())
                     and specification.get("expected_state_version") == context.get("state_version")
                     and record["prompt"] == protocol.build_prompt(context)
                     and record["proposal"] == protocol.build_proposal(context, parsed["arguments"],
                         "Operator-imported delegated decision; execution/model/usage unverified"),
                     "EVIDENCE_CHANGED", "Original response, context, prompt or proposal does not match.")
            with self.project._writer():
                current = self.project.status()
                parents = [item for item in current.get("controller_requests", [])
                           if type(item) is dict and item.get("request_id") == request_id]
                if len(parents) != 1 or parents[0].get("status") != "completed":
                    return copy.deepcopy(record)
                parent = parents[0]
                request = {"project_id": current["id"], "command": "controller.advance_selection", "need": "next_check",
                           "expected_state_version": context["state_version"], "proposal": record["proposal"]}
                _require(parent.get("project_id") == current["id"] == context.get("project_id")
                         and current["run_id"] == context.get("run_id")
                         and current["source_snapshot_sha256"] == context.get("source_snapshot_sha256") == parent.get("source_snapshot_sha256")
                         and parent.get("code_identity") == current["code_identity"] == context.get("project_code_identity") == research_project.code_identity()
                         and parent.get("controller_code_identity") == context.get("controller_code_identity") == project_controller.code_identity()
                         and parent.get("request") == request and parent.get("request_sha256") == fingerprint(request)
                         and parent.get("selection_context") == context
                         and parent.get("decision_sha256") == fingerprint(parent.get("decision")),
                         "EVIDENCE_CHANGED", "The original Controller input, identity or decision differs.")
                child_id = parent.get("child_request_id")
                children = [item for item in current.get("actions", []) + current.get("evidence_actions", [])
                            if type(item) is dict and item.get("request_id") == child_id]
                if type(child_id) is not str or len(children) != 1 or children[0].get("status") != "completed":
                    return copy.deepcopy(record)
                child = children[0]
                project_selection_view._verify(current, parent)
                with self.project._connect(readonly=True) as con:
                    row = con.execute("SELECT fingerprint, record FROM actions WHERE request_id=?", (child_id,)).fetchone()
                _require(row is not None and json.loads(row["record"]) == child
                         and row["fingerprint"] == child.get("request_sha256"),
                         "EVIDENCE_CHANGED", "The original child ledger binding differs.")
                fields = ("id", "request_id", "command", "status", "artifact", "result_sha256", "failure")
                result = parent.get("result")
                selection = project_selection.validate_proposal(context, record["proposal"])
                candidate = selection.get("candidate")
                frozen = (parent.get("decision") or {}).get("next_action") or {}
                _require(all(key in child for key in fields) and type(child.get("id")) is str
                         and child.get("artifact") == "artifacts/" + child["id"] + ".json"
                         and type(child.get("result_sha256")) is str and re.fullmatch(r"[a-f0-9]{64}", child["result_sha256"]) is not None
                         and child.get("failure") is None
                         and child.get("project_id") == current["id"] and child.get("run_id") == current["run_id"]
                         and type(candidate) is dict and candidate.get("method_id") == frozen.get("method_id")
                         and candidate.get("parameters") == frozen.get("parameters", {})
                         and type(parent.get("state_version_after")) is int
                         and parent["dispatch_state_version"] < parent["state_version_after"] <= current["state_version"]
                         and type(result) is dict and set(result) == {"child", "recovered", "reused"}
                         and type(result.get("recovered")) is bool and type(result.get("reused")) is bool
                         and result.get("child") == {k: child[k] for k in fields if k in child},
                         "EVIDENCE_CHANGED", "The original Controller child binding differs.")
                observed = ProjectController._response(parent, replayed=True)
                stable = lambda value: {k: v for k, v in value.items() if k not in ("status", "result", "replayed")}
                _require(stable(previous) == stable(observed), "EVIDENCE_CHANGED", "The original unknown receipt identity differs.")
                proof = {"schema_version": OBSERVED_RECONCILE, "source": "stored_controller_and_child_records",
                         "controller_request_sha256": parent["request_sha256"], "child_request_id": child_id,
                         "controller_state_version_after": parent.get("state_version_after"), "artifact_revalidated": False}
                if outcome.get("status") == "completed":
                    _require(outcome == observed and record.get("outcome_observation") == proof,
                             "EVIDENCE_CHANGED", "The saved observation differs from the original completed records.")
                    return copy.deepcopy(record)
                _require("previous_unknown" not in record and "outcome_observation" not in record,
                         "EVIDENCE_CHANGED", "Original unknown history cannot be overwritten.")
                record.update(previous_unknown=copy.deepcopy(previous), outcome=observed, outcome_observation=proof)
                self._save(state)
                return copy.deepcopy(record)

    def adopt_plan(self, *, request_id):
        with self._writer():
            state = self._load(); record = self._record(state, request_id)
            _require(record.get("purpose") == "plan", "INVALID_REQUEST", "Only a plan proposal can be adopted.")
            if record["status"] == "applied":
                return copy.deepcopy(record)
            _require(record["status"] == "proposed", "HOST_RESPONSE_NOT_READY", "Consume the saved plan response before adopting it.")
            proposal = record["proposal"]
            plan_protocol.validate_proposal(record["context"], proposal)
            raw = _read_file(safe_path(self.directory / record["response_file"]), protocol.MAX_RESPONSE_BYTES)
            _require(hashlib.sha256(raw).hexdigest() == record["response_sha256"],
                     "EVIDENCE_CHANGED", "Original plan response changed after receipt.")
            parsed = plan_protocol.parse_host_response(raw, record["provider"])
            _require(plan_protocol.build_proposal(record["context"], parsed["arguments"], proposal["provider"]["label"]) == proposal
                     and _read_file(safe_path(self.directory / record["directory"] / "proposal.json"), protocol.MAX_RESPONSE_BYTES)
                     == canonical(proposal).encode("utf-8"), "EVIDENCE_CHANGED", "Saved plan proposal differs from its original response.")
            saved = next((item for item in self.project.status().get("plan_revisions", [])
                          if item["request_id"] == record["controller_request_id"]), None)
            selection = record["context"]["selection_context"]
            try:
                if saved is None:
                    self._fresh(record)
                revision = self.project.save_plan(request_id=record["controller_request_id"],
                    expected_state_version=selection["state_version"], plan=proposal["plan"], reason=proposal["reason"])
            except ResearchError as error:
                if error.code not in ("STALE_STATE", "STALE_SELECTION_CONTEXT", "CODE_CHANGED"):
                    raise
                record.update(status="stale", error={"code": error.code, "message": str(error)})
                self._save(state)
                return copy.deepcopy(record)
            record.update(status="applied", outcome={"status": "completed", "kind": "plan_revision", "research_plan": revision,
                          "state_version": revision["based_on_state_version"] + 1, "replayed": saved is not None})
            self._save(state)
            return copy.deepcopy(record)

    def reject_plan(self, *, request_id, reason):
        _require(type(reason) is str and bool(reason.strip()) and len(reason) <= 2000 and "\x00" not in reason,
                 "INVALID_REQUEST", "Record a bounded reason for rejecting this plan.")
        with self._writer():
            state = self._load(); record = self._record(state, request_id)
            _require(record.get("purpose") == "plan", "INVALID_REQUEST", "Only a plan proposal can be rejected.")
            if record["status"] == "rejected":
                _require(record["rejection_reason"] == reason, "IDEMPOTENCY_CONFLICT", "The original rejection reason is fixed.")
                return copy.deepcopy(record)
            _require(record["status"] == "proposed", "HOST_RESPONSE_NOT_READY", "Only a pending plan proposal can be rejected.")
            _require(not any(item["request_id"] == record["controller_request_id"] for item in self.project.status().get("plan_revisions", [])),
                     "PLAN_ALREADY_ADOPTED", "Replay the original adoption to recover its committed plan.")
            record.update(status="rejected", rejection_reason=reason)
            self._save(state)
            return copy.deepcopy(record)

    def status(self, *, request_id=None):
        state = self._load()
        if request_id is not None:
            return copy.deepcopy(self._record(state, request_id))
        project = self.project.status()
        records = sorted(state["requests"].values(), key=lambda record: record["directory"])
        linked = {r["controller_request_id"] for r in records}
        unlinked = sum(p.get("request", {}).get("proposal", {}).get("provider", {}).get("kind") == "external_model"
                       and p["request_id"] not in linked for p in project.get("controller_requests", []))
        return {"schema_version": "host-model-selections-status-v1", "project_id": state["project_id"], "grant": state["grant"],
            "requests": [{k: r.get(k) for k in ("request_id", "provider", "purpose", "status", "controller_request_id", "reported_models",
                         "reported_cost_usd", "transport", "error")} for r in records],
            "usage": {"decision_slots_used": len(records), "cli_launch_attempts": sum(r["cli_launch_attempted"] for r in records),
                "delegated_outputs_received": sum(r["provider"] == "delegated" and "response_file" in r for r in records),
                "known_cli_reported_cost_usd": sum(r.get("reported_cost_usd") or 0 for r in records),
                "cli_cost_unknown": any(r["cli_launch_attempted"] and r.get("reported_cost_usd") is None for r in records),
                "unlinked_external_selection_count": unlinked, "prior_external_usage": "unknown_not_zero" if unlinked else "not_established",
                "delegated_inferences_and_cost": "unknown", "cash_settlement": project["budget"].get("cash_settlement", "unknown")},
            "native_local_model_budget": {k: project["budget"].get(k) for k in
                ("model_requests_allowed", "new_model_requests", "model_requests_reserved", "existing_cash_cap_cny")},
            "scientific_validation": False}
