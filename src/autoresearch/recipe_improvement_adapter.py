"""Model proposal and permitted execution callbacks for the recipe improvement loop."""

import copy
import hashlib

from . import recipe_change_proposal as protocol
from .contracts import ResearchError, canonical, identifier
from .host_model_selection import HostModelSelection
from .project_controller import ProjectController
from .project_selection import _hash, _text
from .research_project import safe_path, write_bytes_once
from .research_recipe import compile_recipe, parse_json
from .source_evidence_adapter import _read_file

MAX_VALIDATION_BYTES = 2 * 1024 * 1024


def _require(condition, code, message):
    if not condition:
        raise ResearchError(code, message)


def propose_recipe_change(current_version, trace, goal, *, workspace, request_id,
                          decision_limit, cli_budget_usd, reason, provider="delegated",
                          executable=None, response_file=None):
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
        context = protocol.build_context(journal.project, current_version, goal)
    else:
        _require(previous.get("purpose") == "recipe", "IDEMPOTENCY_CONFLICT",
                 "The original request belongs to another model purpose.")
        context = previous["context"]
    _require(trace == context["research_context"], "STALE_SELECTION_CONTEXT",
             "Use the actual complete research feedback frozen for this request.")
    record = journal.prepare(request_id=request_id, provider=provider,
        expected_state_version=context["research_context"]["selection_context"]["state_version"],
        decision_limit=decision_limit, cli_budget_usd=cli_budget_usd, reason=reason,
        executable=executable, purpose="recipe", current_recipe=current_version,
        improvement_goal=goal)
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
