"""Bounded plan references to an authenticated saved tabular quality action.

This module does not dispatch research, validate scientific meaning or change
the existing quality feedback policy. Historical views authenticate evidence;
they are never selection contexts.
"""
import copy
import re

from .contracts import ResearchError, canonical, fingerprint, identifier
from .research_project import require
from . import tabular_quality_feedback as feedback

SCHEMA = "tabular-quality-plan-reference-v1"
FIELDS = {"schema_version", "registration_request_id", "registration_sha256", "original_plan_version",
          "original_plan_sha256", "quality_parent_request_id", "quality_parent_request_sha256",
          "quality_child_request_id", "quality_action_id", "quality_result_sha256", "feedback_sha256",
          "source_snapshot_sha256"}
_HASH_FIELDS = {"registration_sha256", "original_plan_sha256", "quality_parent_request_sha256",
                "quality_result_sha256", "feedback_sha256", "source_snapshot_sha256"}


def validate_reference(ref, *, code="INVALID_REQUEST"):
    require(type(ref) is dict and set(ref) == FIELDS and ref["schema_version"] == SCHEMA,
            code, "Use the exact bounded quality plan reference.")
    require(type(ref["original_plan_version"]) is int and ref["original_plan_version"] >= 1
            and all(type(ref[k]) is str and re.fullmatch(r"[a-f0-9]{64}", ref[k]) is not None for k in _HASH_FIELDS),
            code, "The quality plan reference identities are malformed.")
    try:
        for key in ("registration_request_id", "quality_parent_request_id", "quality_child_request_id", "quality_action_id"):
            identifier(ref[key], key)
    except ResearchError:
        raise ResearchError(code, "The quality plan reference identifiers are malformed.") from None
    return ref


def reference_for_state(project, state, request_id, *, initial):
    """Authenticate original quality result within the caller's saved snapshot."""
    identifier(request_id, "registration_request_id")
    records = state.get("tabular_quality_registrations", [])
    feedback._checked_collection(records)
    found = [r for r in records if r["request_id"] == request_id]
    require(len(found) == 1, "INVALID_REQUEST", "Use one original quality registration.")
    record = found[0]
    plans = state.get("plan_revisions", [])
    require(type(plans) is list and all(type(p) is dict and type(p.get("version")) is int and p["version"] == i
            for i,p in enumerate(plans, 1)), "EVIDENCE_CHANGED", "The original plan chain is malformed.")
    version = record["plan_version"]
    require(1 <= version <= len(plans) and fingerprint(plans[version - 1]) == record["plan_sha256"],
            "EVIDENCE_CHANGED", "The registered original plan is unavailable or changed.")
    if initial:
        require(len(plans) == version, "CONDITION_NOT_SATISFIED", "The referenced plan must be the current original plan.")
    parents = [p for p in state.get("controller_requests", []) if p.get("request_id") == record["controller_request_id"]]
    require(len(parents) == 1 and parents[0].get("status") == "completed",
            "CONDITION_NOT_SATISFIED", "The original quality controller request is not complete.")
    parent = parents[0]
    require(type(parent.get("state_version_before")) is int and type(parent.get("state_version_after")) is int
            and record["state_version_before"] < parent["state_version_before"] < parent["state_version_after"] <= state["state_version"],
            "EVIDENCE_CHANGED", "The original quality action order is inconsistent.")
    historical = copy.deepcopy(state)
    historical["plan_revisions"] = [copy.deepcopy(plans[version - 1])]
    outcome = feedback._outcome(project, historical, record)
    require(outcome.get("outcome") in ("condition_met", "condition_not_met")
            and type(outcome.get("action_id")) is str and type(outcome.get("result_sha256")) is str,
            "CONDITION_NOT_SATISFIED", "The original quality feedback is unavailable or unknown.")
    full_feedback = {**outcome, "request_id": record["request_id"],
                     "registration_sha256": record["registration_sha256"],
                     "controller_request_id": record["controller_request_id"]}
    result = {"schema_version": SCHEMA, "registration_request_id": record["request_id"],
              "registration_sha256": record["registration_sha256"], "original_plan_version": version,
              "original_plan_sha256": record["plan_sha256"], "quality_parent_request_id": parent["request_id"],
              "quality_parent_request_sha256": parent["request_sha256"], "quality_child_request_id": parent["child_request_id"],
              "quality_action_id": outcome["action_id"], "quality_result_sha256": outcome["result_sha256"],
              "feedback_sha256": fingerprint(full_feedback), "source_snapshot_sha256": record["source_snapshot_sha256"]}
    validate_reference(result, code="EVIDENCE_CHANGED")
    require(project.status()["snapshot_ref"] == state["snapshot_ref"], "STALE_STATE", "The project changed while reading quality evidence.")
    # The project snapshot does not include changes to the loaded/disk code.
    # Recheck the complete registered producer closure after reading evidence.
    from .research_project import code_identity as project_code_identity
    from .project_controller import code_identity as controller_code_identity
    feedback._check_loaded_code()
    require(state["code_identity"] == record["project_code_identity"] == project_code_identity()
            and record["controller_code_identity"] == controller_code_identity()
            and record["reader_sha256"] == feedback._reader_sha()
            and record["conditions_sha256"] == feedback._conditions_sha(),
            "CODE_CHANGED", "The original quality producer code changed during reference verification.")
    return result, parent["state_version_after"], full_feedback


def read_reference(project, *, registration_request_id):
    """Read a reference for a direct successor plan; never write or dispatch."""
    state = project.status()
    ref, _, _ = reference_for_state(project, state, registration_request_id, initial=True)
    return ref


def check_reference(project, state, ref, *, based_on_state_version, revision=None):
    validate_reference(ref)
    expected, finished_at, verified_feedback = reference_for_state(project, state, ref["registration_request_id"], initial=revision is None)
    require(canonical(ref) == canonical(expected), "EVIDENCE_CHANGED", "The original quality reference changed.")
    require(type(based_on_state_version) is int and finished_at <= based_on_state_version <= state["state_version"],
            "EVIDENCE_CHANGED", "The quality result must precede the saved plan.")
    if revision is not None:
        require(revision.get("version") == ref["original_plan_version"] + 1
                and based_on_state_version < state["state_version"]
                and state["plan_revisions"][ref["original_plan_version"]] == revision,
                "EVIDENCE_CHANGED", "The quality plan is not the direct original successor.")
    return verified_feedback
