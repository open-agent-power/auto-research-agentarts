"""Bounded routing over preregistered feedback and current host candidates.

This pure compiler does not read evidence, authorize or dispatch an action. Its
caller must obtain the registration and sealed context from the original project.
"""
import copy

from . import method_registry, project_selection, retrieval_adapter, relevance_retrieval_adapter
from .contracts import ResearchError, fingerprint


_AUDITS = {
    retrieval_adapter.TOOL_ID: retrieval_adapter.AUDIT_TOOL_ID,
    relevance_retrieval_adapter.TOOL_ID: relevance_retrieval_adapter.AUDIT_TOOL_ID,
}


def validate_branches(branches, *, primary_method_id):
    """Validate the two frozen branches; unknown is implicitly always wait."""
    if type(primary_method_id) is not str or primary_method_id not in _AUDITS:
        raise ResearchError("INVALID_REQUEST", "Feedback routing supports only a registered retrieval pair.")
    if type(branches) is not dict or set(branches) != {"condition_met", "condition_not_met"}:
        raise ResearchError("INVALID_REQUEST", "Provide exactly the met and not-met branches; unknown always waits.")
    for branch in branches.values():
        if type(branch) is not dict or not (
            branch == {"kind": "wait"}
            or branch == {"kind": "method", "method_id": _AUDITS[primary_method_id]}
        ):
            raise ResearchError("INVALID_REQUEST", "A branch must wait or select this pair's saved audit.")
    return copy.deepcopy(branches)


def select_from_feedback(context, *, registration, provider):
    """Compile an existing sealed context and saved registration into a proposal.

    The registration must be loaded from the original trusted project. A valid
    hash alone does not prove that an arbitrary caller-supplied record existed
    before the target action. The controller rechecks freshness and dispatch.
    """
    from .hypothesis_feedback import _check_record

    try:
        _check_record(registration)
        candidate = registration["candidate"]
        # Check required binding fields before the selection code uses them.
        for key in ("project_id", "run_id", "source_snapshot_sha256", "project_code_identity",
                    "controller_code_identity", "plan_sha256", "request_id", "registration_sha256",
                    "controller_request_id", "condition"):
            if key not in registration:
                raise KeyError(key)
    except (KeyError, TypeError, ValueError, RecursionError):
        raise ResearchError("EVIDENCE_CHANGED", "Saved feedback registration is malformed.") from None
    branches = validate_branches(registration.get("branches"), primary_method_id=candidate["method_id"])
    if registration.get("request", {}).get("hypothesis", {}).get("branches") != branches:
        raise ResearchError("EVIDENCE_CHANGED", "Frozen policy differs from the original registration request.")

    proposal = {
        "schema_version": "project-selection-proposal-v1",
        "context_sha256": context.get("context_sha256") if type(context) is dict else None,
        "provider": copy.deepcopy(provider),
        "choice": {"kind": "wait"},
        "rationale": "Feedback policy waits: original bound feedback is unavailable or changed.",
        "evidence_citation_ids": [],
    }
    # This verifies the whole seal and schema, including provider and feedback.
    project_selection.validate_proposal(context, proposal)
    feedback = context.get("hypothesis_feedback", {}).get("items", [])
    items = [item for item in feedback if item["request_id"] == registration["request_id"]]
    if len(items) != 1:
        return proposal
    item = items[0]
    if (context["project_id"] != registration["project_id"]
            or context["run_id"] != registration["run_id"]
            or context["source_snapshot_sha256"] != registration["source_snapshot_sha256"]
            or context["project_code_identity"] != registration["project_code_identity"]
            or context["controller_code_identity"] != registration["controller_code_identity"]
            or fingerprint(context.get("research_plan")) != registration["plan_sha256"]
            or item["registration_sha256"] != registration["registration_sha256"]
            or item["controller_request_id"] != registration["controller_request_id"]
            or item["candidate"] != candidate or item["condition"] != registration["condition"]
            or item.get("branches") != branches):
        return proposal
    if item["outcome"] == "unknown":
        proposal["rationale"] = "Feedback policy waits: the registered result is unknown (" + item["unknown_reason"] + ")."
        return proposal
    branch = branches[item["outcome"]]
    if branch["kind"] == "wait":
        proposal["rationale"] = "Feedback policy waits: the frozen " + item["outcome"] + " branch requires waiting."
        return proposal
    if context["blockers"]:
        proposal["rationale"] = "Feedback policy waits: the host reports execution blockers."
        return proposal
    expected = {"based_on_action_id": item["action_id"], "based_on_result_sha256": item["result_sha256"]}
    matching = [c for c in context["candidates"] if c["method_id"] == branch["method_id"]
                and c["parameters"] == expected and c["evaluation_ref"] == method_registry.evaluation_ref(branch["method_id"])]
    if len(matching) != 1:
        proposal["rationale"] = "Feedback policy waits: the exact saved-result audit candidate is unavailable or ambiguous."
        return proposal
    proposal["choice"] = {"kind": "execute", "candidate_id": matching[0]["id"]}
    proposal["rationale"] = "Frozen " + item["outcome"] + " branch selects the eligible audit of the registered saved result."
    project_selection.validate_proposal(context, proposal)
    return proposal
