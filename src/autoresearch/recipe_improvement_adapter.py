"""Model proposal and permitted execution callbacks for the recipe improvement loop."""

import copy
import hashlib

from . import recipe_change_proposal as protocol
from .contracts import ResearchError, canonical, identifier
from .host_model_selection import HostModelSelection
from .project_controller import ProjectController
from .project_selection import _hash, _text
from .research_project import ResearchProject, safe_path, write_bytes_once
from .research_recipe import compile_recipe, parse_json
from .source_evidence_adapter import _read_file
from .saved_materials import normalize_requests

MAX_VALIDATION_BYTES = 2 * 1024 * 1024


def _require(condition, code, message):
    if not condition:
        raise ResearchError(code, message)


def propose_recipe_change(current_version, trace, goal, *, workspace, request_id,
                          decision_limit, cli_budget_usd, reason, provider="delegated",
                          executable=None, response_file=None, saved_materials=None):
    """Prepare or resume one original Host request and return its saved recipe candidate.

    Delegated requests return prepared until the caller supplies the original answer.
    CLI requests use the existing transport and its cumulative grant.
    """
    identifier(request_id)
    _require(response_file is None or provider == "delegated", "INVALID_REQUEST",
             "CLI requests use their original transport response.")
    journal = HostModelSelection(workspace)
    try:
        previous = journal.status(request_id=request_id)
    except ResearchError as error:
        if error.code != "ARTIFACT_NOT_FOUND":
            raise
        previous = None
    if previous is None:
        selectors = normalize_requests(saved_materials)
        materials = {"saved_materials": selectors} if selectors else {}
        context = protocol.build_context(journal.project, current_version, goal, **materials)
    else:
        _require(previous.get("purpose") == "recipe", "IDEMPOTENCY_CONFLICT",
                 "The original request belongs to another model purpose.")
        context = previous["context"]
        original = previous["prepare_specification"].get("saved_materials", [])
        _require(saved_materials is None or normalize_requests(saved_materials) == original,
                 "IDEMPOTENCY_CONFLICT", "The original saved material selectors are fixed.")
        materials = {"saved_materials": original} if original else {}
    _require(trace == context["research_context"], "STALE_SELECTION_CONTEXT",
             "Use the actual complete research feedback frozen for this request.")
    record = journal.prepare(request_id=request_id, provider=provider,
        expected_state_version=context["research_context"]["selection_context"]["state_version"],
        decision_limit=decision_limit, cli_budget_usd=cli_budget_usd, reason=reason,
        executable=executable, purpose="recipe", current_recipe=current_version,
        improvement_goal=goal, **materials)
    if provider == "delegated":
        if response_file is not None:
            record = journal.import_response(request_id=request_id, response_file=response_file)
    else:
        record = journal.request(request_id=request_id)
    if record["status"] == "received":
        record = journal.consume(request_id=request_id)
    folder = (journal.directory / record["directory"]).relative_to(journal.project.root).as_posix()
    response = record.get("response_file")
    return {"schema_version": "recipe-change-proposal-result-v1", "request_id": request_id,
            "status": record["status"], "candidate": copy.deepcopy(record.get("proposal")),
            "context_ref": folder + "/context.json", "prompt_ref": folder + "/prompt.json",
            "response_ref": journal.directory.name + "/" + response if response else None,
            "scientific_validation": False}


def _allowed(values, *, receipts=False):
    _require(type(values) in (list, tuple) and len(values) <= 16
             and all(_hash(value) if receipts else _text(value, 160) for value in values)
             and len(set(values)) == len(values), "INVALID_REQUEST",
             "Use distinct allowed method IDs or exact source receipt identities.")
    return sorted(values)


def validate_recipe_change(candidate, original, goal, *, workspace, request_id,
                           allowed_methods, allowed_receipts):
    """Compare frozen decisions and run at most one permitted original controller action.

    The outer loop owns the keep/revert decision. Completed validations replay their
    saved result. Interrupted validations resume the same controller request.
    """
    identifier(request_id)
    methods, receipts = _allowed(allowed_methods), _allowed(allowed_receipts, receipts=True)
    journal = HostModelSelection(workspace)
    with journal._writer():
        record = journal.status(request_id=request_id)
        _require(record.get("purpose") == "recipe" and record["status"] == "proposed",
                 "HOST_RESPONSE_NOT_READY", "Consume the original recipe response before validation.")
        context = record["context"]
        _require(candidate == record.get("proposal") and original == context["current_recipe"]
                 and goal == context["improvement_goal"], "IDEMPOTENCY_CONFLICT",
                 "Validate the saved candidate, original recipe and improvement goal.")
        protocol.validate_proposal(context, candidate)
        folder = safe_path(journal.directory / record["directory"])
        raw = _read_file(safe_path(journal.directory / record["response_file"]), MAX_VALIDATION_BYTES)
        _require(hashlib.sha256(raw).hexdigest() == record["response_sha256"],
                 "EVIDENCE_CHANGED", "Original recipe response changed after receipt.")
        parsed = protocol.parse_host_response(raw, record["provider"])
        rebuilt = protocol.build_proposal(context, parsed["arguments"], candidate["provider"]["label"])
        _require(rebuilt == candidate and _read_file(folder / "proposal.json", MAX_VALIDATION_BYTES)
                 == canonical(candidate).encode("utf-8"), "EVIDENCE_CHANGED",
                 "The candidate differs from the original model answer.")
        selection = context["research_context"]["selection_context"]
        baseline = compile_recipe(original, selection)
        proposed = compile_recipe(candidate["candidate"], selection)
        selected = next((item for item in selection["candidates"]
                         if item["id"] == proposed["selected_candidate_id"]), None)
        if selected is not None:
            _require(selected["method_id"] in methods, "METHOD_NOT_AUTHORIZED",
                     "The candidate method is outside this validation's allowed methods.")
            receipt = selected["parameters"].get("receipt_snapshot_sha256")
            _require(receipt is None or receipt in receipts, "SOURCE_NOT_AUTHORIZED",
                     "The exact source receipt is outside this validation's allowed sources.")
        validation_input = {"schema_version": "recipe-change-validation-input-v1",
            "request_id": request_id, "context_sha256": selection["context_sha256"],
            "allowed_methods": methods, "allowed_receipts": receipts,
            "baseline_decision": baseline, "candidate_decision": proposed}
        input_path, result_path = folder / "validation-input.json", folder / "validation-result.json"
        if input_path.exists():
            _require(_read_file(input_path, MAX_VALIDATION_BYTES) == canonical(validation_input).encode("utf-8"),
                     "IDEMPOTENCY_CONFLICT", "The original validation inputs and permissions are fixed.")
        write_bytes_once(input_path, canonical(validation_input).encode("utf-8"))
        if result_path.exists():
            result = parse_json(_read_file(result_path, MAX_VALIDATION_BYTES),
                                maximum=MAX_VALIDATION_BYTES, code="EVIDENCE_CHANGED")
            _require(result.get("request_id") == request_id and result.get("baseline_decision") == baseline
                     and result.get("candidate_decision") == proposed, "EVIDENCE_CHANGED",
                     "Saved validation result differs from its frozen decisions.")
            return result
        controller = ProjectController(journal.project.root)
        previous = controller._parent(journal.project.status(), record["controller_request_id"])
        if previous is None:
            _require(controller.selection_context(need=original["need"]) == selection,
                     "STALE_SELECTION_CONTEXT", "The project changed before candidate validation.")
        outcome = controller.advance_recipe(request_id=record["controller_request_id"],
            recipe=candidate["candidate"], need=original["need"], expected_state_version=selection["state_version"])
        state = journal.project.status()
        artifacts = [item["artifact"] for item in state["actions"] + state["evidence_actions"]
                     if item["request_id"] == outcome.get("child_request_id") and item.get("artifact")]
        result = {"schema_version": "recipe-change-validation-v1", "request_id": request_id,
            "status": outcome["status"], "baseline_decision": baseline, "candidate_decision": proposed,
            "selection_changed": baseline["proposal"]["choice"] != proposed["proposal"]["choice"],
            "controller_outcome": outcome, "artifact_refs": artifacts, "scientific_validation": False}
        if outcome["status"] in ("completed", "waiting", "failed", "rejected"):
            write_bytes_once(result_path, canonical(result).encode("utf-8"))
        return result


def _read_validation_sidecars(record, state, folder, view):
    for key, name in (("input", "validation-input.json"), ("result", "validation-result.json")):
        path = safe_path(folder / name)
        if path.exists():
            view[key] = parse_json(_read_file(path, MAX_VALIDATION_BYTES),
                                   maximum=MAX_VALIDATION_BYTES, code="EVIDENCE_CHANGED")
    parent = ProjectController._parent(state, record["controller_request_id"])
    if view["input"] is None and view["result"] is None and parent is None:
        return view
    context, proposal = record["context"], record.get("proposal")
    protocol.validate_proposal(context, proposal)
    selection = context["research_context"]["selection_context"]
    _require(selection["project_id"] == state["id"] and record["controller_request_id"] == record["request_id"],
             "EVIDENCE_CHANGED", "Validation context and controller identity differ from the original Host project.")
    baseline = compile_recipe(context["current_recipe"], selection)
    candidate = compile_recipe(proposal["candidate"], selection)
    selected = next((item for item in selection["candidates"] if item["id"] == candidate["selected_candidate_id"]), None)
    validation_input, result = view["input"], view["result"]
    if validation_input is not None:
        _require(set(validation_input) == {"schema_version", "request_id", "context_sha256", "allowed_methods",
                                         "allowed_receipts", "baseline_decision", "candidate_decision"}
                 and validation_input["schema_version"] == "recipe-change-validation-input-v1"
                 and validation_input["request_id"] == record["request_id"]
                 and validation_input["context_sha256"] == selection["context_sha256"]
                 and validation_input["baseline_decision"] == baseline and validation_input["candidate_decision"] == candidate,
                 "EVIDENCE_CHANGED", "Validation inputs differ from the original Host context and recipe decisions.")
        methods = _allowed(validation_input["allowed_methods"])
        receipts = _allowed(validation_input["allowed_receipts"], receipts=True)
        _require(methods == validation_input["allowed_methods"] and receipts == validation_input["allowed_receipts"]
                 and (selected is None or (selected["method_id"] in methods
                      and (selected["parameters"].get("receipt_snapshot_sha256") is None
                           or selected["parameters"]["receipt_snapshot_sha256"] in receipts))),
                 "EVIDENCE_CHANGED", "Validation permissions do not cover the frozen candidate.")
    if parent is not None:
        _require(parent["project_id"] == state["id"] and parent["request"]["command"] == "controller.advance_recipe"
                 and parent["request"]["expected_state_version"] == selection["state_version"]
                 and parent["selection_context"] == selection and parent["request"]["recipe_decision"] == candidate,
                 "EVIDENCE_CHANGED", "The saved controller request differs from this recipe validation.")
    if result is not None:
        _require(set(result) == {"schema_version", "request_id", "status", "baseline_decision", "candidate_decision",
                               "selection_changed", "controller_outcome", "artifact_refs", "scientific_validation"}
                 and result["schema_version"] == "recipe-change-validation-v1"
                 and result["request_id"] == record["request_id"] and result["baseline_decision"] == baseline
                 and result["candidate_decision"] == candidate and result["scientific_validation"] is False
                 and type(result["selection_changed"]) is bool
                 and result["selection_changed"] == (baseline["proposal"]["choice"] != candidate["proposal"]["choice"])
                 and parent is not None and type(result["controller_outcome"]) is dict,
                 "EVIDENCE_CHANGED", "Validation result identity or decisions differ from the original records.")
        outcome = ProjectController._response(parent)
        original_outcome = {key: value for key, value in result["controller_outcome"].items() if key != "replayed"}
        expected_outcome = {key: value for key, value in outcome.items() if key != "replayed"}
        artifacts = [item["artifact"] for item in state["actions"] + state["evidence_actions"]
                     if item["request_id"] == outcome.get("child_request_id") and item.get("artifact")]
        _require(original_outcome == expected_outcome and result["status"] == outcome["status"]
                 and result["artifact_refs"] == artifacts and result["status"] in ("completed", "waiting", "failed", "rejected"),
                 "EVIDENCE_CHANGED", "Validation result does not match the original controller outcome and artifacts.")
        if validation_input is not None:
            view["status"] = "failed" if result["status"] == "rejected" else result["status"]
            return view
    if parent is not None and parent["status"] in ("completed", "waiting", "failed", "rejected"):
        view.update(status="recovery_required", error={"code": "VALIDATION_RECEIPT_MISSING",
                    "message": "The controller finished but a validation receipt is missing; explicitly reconcile the original request."})
    elif parent is not None and parent["status"] in ("unknown", "needs_review"):
        view.update(status="unknown", error={"code": "EXECUTION_UNKNOWN", "message": "The original validation execution needs inspection."})
    else:
        view["status"] = "pending"
    return view


def read_recipe_validation(workspace, request_id):
    """Verify saved validation receipts without dispatch, recovery or state writes."""
    view = {"schema_version": "recipe-change-validation-view-v1", "project_id": None, "request_id": request_id,
            "status": "not_started", "input": None, "result": None, "error": None}
    try:
        identifier(request_id)
        journal = HostModelSelection(workspace)
        view["project_id"] = journal.project.status()["id"]
        lock_path = safe_path(journal.directory / "writer.lock")
        _require(journal.directory.is_dir() and lock_path.is_file() and lock_path.stat().st_size > 0,
                 "EVIDENCE_CHANGED", "The original Host request lock is missing.")
        with ResearchProject(journal.directory)._writer():
            record = journal.status(request_id=request_id)
            _require(record.get("purpose") == "recipe" and record["request_id"] == request_id,
                     "INVALID_REQUEST", "Select an original recipe request.")
            return _read_validation_sidecars(record, journal.project.status(), safe_path(journal.directory / record["directory"]), view)
    except ResearchError as error:
        view.update(status="pending" if error.code == "PROJECT_BUSY" else "invalid",
                    error={"code": error.code, "message": str(error)})
    except (OSError, ValueError, TypeError, KeyError):
        view.update(status="invalid", error={"code": "EVIDENCE_CHANGED", "message": "Saved validation data is missing or malformed."})
    return view
