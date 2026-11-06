"""Bind saved recipe-improvement decisions to an explicit project revision."""

import copy
import hashlib

from .contracts import ResearchError, canonical, fingerprint, identifier
from .research_recipe import validate_recipe


def current_recipe(state):
    revisions = state.get("recipe_revisions", [])
    return copy.deepcopy(revisions[-1]["recipe"]) if revisions else None


def preview_recipe_round(project, round_input):
    from . import recipe_change_proposal as protocol
    from .host_model_selection import HostModelSelection
    from .recipe_improvement import _assess
    from .recipe_improvement_adapter import read_recipe_validation
    from .research_project import require, safe_path
    from .source_evidence_adapter import _read_file

    result = _assess(round_input)
    require(round_input["evidence_kind"] == "saved_host_validation", "INVALID_IMPROVEMENT_ROUND",
            "Project revisions require original saved Host validation.")
    before = project.status()
    require(result["project_id"] == before["id"], "EVIDENCE_CHANGED", "The round belongs to another project.")
    journal = HostModelSelection(project.root)
    record = journal.status(request_id=round_input["request_id"])
    context = {"schema_version": "recipe-change-context-v1", "current_recipe": round_input["current_recipe"],
               "research_context": round_input["trace"], "improvement_goal": round_input["goal"]}
    require(record.get("purpose") == "recipe" and record["context"] == context
            and record["controller_request_id"] == round_input["request_id"],
            "EVIDENCE_CHANGED", "The round differs from its original Host request.")
    folder = safe_path(journal.directory / record["directory"])
    relative = folder.relative_to(project.root).as_posix()
    proposal = {"schema_version": "recipe-change-proposal-result-v1", "request_id": record["request_id"],
                "status": record["status"], "candidate": record.get("proposal"),
                "context_ref": relative + "/context.json", "prompt_ref": relative + "/prompt.json",
                "response_ref": journal.directory.name + "/" + record["response_file"]
                    if record.get("response_file") else None, "scientific_validation": False}
    require(round_input["proposal_result"] == proposal, "EVIDENCE_CHANGED", "The round proposal differs from Host evidence.")
    for name, value in (("context.json", record["context"]), ("prompt.json", record["prompt"])):
        require(_read_file(safe_path(folder / name), 4 * 1024 * 1024) == canonical(value).encode("utf-8"),
                "EVIDENCE_CHANGED", "Original Host context or prompt changed.")
    if record.get("proposal") is not None:
        raw = _read_file(safe_path(journal.directory / record["response_file"]), 4 * 1024 * 1024)
        parsed = protocol.parse_host_response(raw, record["provider"])
        require(hashlib.sha256(raw).hexdigest() == record["response_sha256"]
                and protocol.build_proposal(context, parsed["arguments"], record["proposal"]["provider"]["label"]) == record["proposal"]
                and _read_file(safe_path(folder / "proposal.json"), 4 * 1024 * 1024) == canonical(record["proposal"]).encode("utf-8"),
                "EVIDENCE_CHANGED", "Original Host answer or proposal changed.")
    view = read_recipe_validation(project.root, record["request_id"])
    if view["status"] == "invalid":
        raise ResearchError(view["error"]["code"], view["error"]["message"])
    require(view["status"] != "pending" or round_input["validation_result"] is None,
            "HOST_SELECTION_PENDING", "The original validation is being updated; inspect the same request.")
    validation = view["result"] if view["status"] in ("completed", "waiting", "failed") else None
    require(round_input["validation_result"] == validation, "EVIDENCE_CHANGED", "The round differs from the original validation receipt.")
    require(record == journal.status(request_id=record["request_id"])
            and before["snapshot_ref"] == project.status()["snapshot_ref"],
            "STALE_STATE", "Project or Host evidence changed while reading the round.")
    return result


def read_recipe_revision(project, revision):
    from .recipe_improvement import read_json, _assess
    from .research_project import require, safe_path

    artifact = read_json(safe_path(project.root / revision["artifact_ref"]))
    require(artifact["schema_version"] == "project-recipe-revision-v1"
            and artifact["project_id"] == project.status()["id"] and artifact["revision"] == revision
            and artifact["result"] == _assess(artifact["input"])
            and fingerprint(artifact["input"]) == revision["input_sha256"]
            and artifact["result"]["effective_recipe"] == revision["recipe"],
            "EVIDENCE_CHANGED", "Saved recipe revision differs from its complete round artifact.")
    return artifact


def apply_recipe_round(project, *, request_id, expected_state_version, round_input, reason):
    from .host_model_selection import HostModelSelection, PENDING
    from .recipe_improvement import MAX_ROUND_BYTES
    from .project_selection import _json_value
    from .research_project import require, safe_path, write_bytes_once

    identifier(request_id)
    require(type(expected_state_version) is int and expected_state_version >= 0, "INVALID_REQUEST", "Bind the current project version.")
    require(type(reason) is str and 0 < len(reason) <= 2000 and reason.strip() and "\x00" not in reason,
            "INVALID_REQUEST", "Record a bounded reason for applying the recipe round.")
    _json_value(round_input, MAX_ROUND_BYTES, "INVALID_IMPROVEMENT_ROUND")
    digest = fingerprint(round_input)
    with project._writer(), project._connect() as con:
        state = project._project(con)
        revisions = state.get("recipe_revisions", [])
        previous = next((item for item in revisions if item["request_id"] == request_id), None)
        if previous is not None:
            require(previous["based_on_state_version"] == expected_state_version and previous["reason"] == reason
                    and previous["input_sha256"] == digest, "IDEMPOTENCY_CONFLICT", "Original recipe adoption content differs.")
            read_recipe_revision(project, previous)
            return copy.deepcopy(previous)
        require(project._action(con, request_id) is None, "IDEMPOTENCY_CONFLICT", "ID belongs to an existing action.")
        project._require_unclaimed(state, request_id)
        project._require_fresh(state, project.status(), expected_state_version)
        require(not any(item["status"] in ("prepared", "running", "unknown", "needs_review") for item in state.get("controller_requests", []))
                and not any(item["status"] == "reserved" for item in state.get("local_model_requests", [])),
                "PROJECT_BUSY", "Reconcile accepted execution before changing the effective recipe.")
        require(not any(item["status"] in PENDING for item in HostModelSelection(project.root).status()["requests"]),
                "HOST_SELECTION_PENDING", "Reconcile the original Host request before applying its round.")
        result = preview_recipe_round(project, round_input)
        require(result["status"] == "completed", "RECIPE_ROUND_NOT_READY", "Only a completed round can change the effective recipe.")
        require(not any(item["model_request_id"] == result["request_id"] for item in revisions),
                "RECIPE_ROUND_ALREADY_APPLIED", "This Host round already has an explicit project decision.")
        effective = current_recipe(state)
        require(effective is None or effective == round_input["current_recipe"],
                "STALE_RECIPE", "The round must start from the project's actual effective recipe.")
        if round_input["previous_round"] is not None:
            prior = round_input["previous_round"]
            require(bool(revisions) and prior["round_id"] == revisions[-1]["round_id"]
                    and read_recipe_revision(project, revisions[-1])["result"] == prior["result"],
                    "STALE_RECIPE", "The predecessor must be the last applied project recipe round.")
        recipe = validate_recipe(result["effective_recipe"])
        require(all(recipe["scope_match"][key] == state["source_scope"].get(key) for key in recipe["scope_match"]),
                "STALE_RECIPE", "Effective recipe scope differs from the project.")
        revision = {"revision": len(revisions) + 1, "request_id": request_id, "round_id": result["round_id"],
                    "model_request_id": result["request_id"], "decision": result["decision"], "recipe": recipe,
                    "reason": reason, "explanation": result["explanation"], "input_sha256": digest,
                    "based_on_state_version": expected_state_version,
                    "artifact_ref": "artifacts/recipe-revision-" + request_id + ".json"}
        artifact = {"schema_version": "project-recipe-revision-v1", "project_id": state["id"],
                    "revision": revision, "input": copy.deepcopy(round_input), "result": result}
        write_bytes_once(safe_path(project.root / revision["artifact_ref"]), canonical(artifact).encode("utf-8"))
        state.setdefault("recipe_revisions", []).append(revision)
        state["state_version"] += 1
        project._save(con, state)
        return copy.deepcopy(revision)
