"""Verify and project saved imported choices without dispatching research."""

import copy

from . import method_registry, project_selection
from .contracts import ResearchError, fingerprint, identifier


def _require(condition):
    if not condition:
        raise ResearchError("EVIDENCE_CHANGED", "Saved selection identities could not be verified.")


def _imported(parent):
    return ("selection_context" in parent
            or parent.get("request", {}).get("command") == "controller.advance_selection")


def _verify(state, parent):
    try:
        request, decision = parent["request"], parent["decision"]
        context = parent["selection_context"]
        selected = project_selection.validate_proposal(context, request["proposal"])
        candidate = selected["candidate"]
        identifier(parent["request_id"])
        _require(parent["schema_version"] == "project-controller-request-v1"
                 and set(request) == {"project_id", "command", "need", "expected_state_version", "proposal"}
                 and request["command"] == "controller.advance_selection"
                 and parent["request_sha256"] == fingerprint(request)
                 and parent["decision_sha256"] == fingerprint(decision)
                 and parent["project_id"] == request["project_id"] == context["project_id"] == state["id"]
                 and context["run_id"] == state["run_id"]
                 and parent["source_snapshot_sha256"] == context["source_snapshot_sha256"] == state["source_snapshot_sha256"]
                 and parent["snapshot_ref_before"] == context["snapshot_ref"]
                 and parent["state_version_before"] == context["state_version"]
                 and parent["dispatch_state_version"] == context["state_version"] + 1
                 and parent["dispatch_state_version"] <= state["state_version"]
                 and request["expected_state_version"] in (None, context["state_version"])
                 and request["need"] == context["need"]
                 and parent["code_identity"] == context["project_code_identity"]
                 and parent["controller_code_identity"] == context["controller_code_identity"]
                 and parent["blockers"] == context["blockers"]
                 and decision["reason"] == selected["rationale"]
                 and decision["scientific_validation"] is False)
        action = decision["next_action"]
        _require(action.get("execution_status") == "not_executed")
        if candidate is None:
            _require(action == {"kind": "external_wait", "execution_status": "not_executed"}
                     and parent["child_request_id"] is None and parent["result"] is None
                     and parent["status"] in ("waiting", "needs_review"))
        else:
            _require(action == {"kind": "conditional_proposal", "method_id": candidate["method_id"],
                                "parameters": candidate["parameters"], "execution_status": "not_executed"}
                     and parent["child_request_id"] == "controller-child-" + fingerprint(
                         {"project_id": state["id"], "request_id": parent["request_id"]})[:32])
            matches = [item for item in state.get("actions", []) + state.get("evidence_actions", [])
                       if item["request_id"] == parent["child_request_id"]]
            _require(len(matches) <= 1)
            child = matches[0] if matches else None
            result_child = (parent.get("result") or {}).get("child")
            if child is not None:
                params = candidate["parameters"]
                child_request = {"project_id": state["id"], "command": candidate["method_id"],
                                 "source_snapshot_sha256": state["source_snapshot_sha256"]}
                if method_registry.is_source(candidate["method_id"]):
                    child_request["receipt_snapshot_sha256"] = params["receipt_snapshot_sha256"]
                    _require(child["receipt_snapshot_sha256"] == params["receipt_snapshot_sha256"]
                             and child["method_instance"]["input_bindings"]["receipt_snapshot_sha256"] == params["receipt_snapshot_sha256"])
                else:
                    child_request["dimension"] = params.get("dimension")
                    _require(child["method_instance"]["parameters"] == params
                             and child.get("dimension") == params.get("dimension"))
                    if candidate["method_id"] in method_registry.FOLLOWUP:
                        child_request.update(parameters=params, evaluation_ref=candidate["evaluation_ref"])
                        _require(child["parameters"] == params
                                 and child["method_instance"]["evaluation_ref"] == candidate["evaluation_ref"]
                                 and all(child["method_instance"]["input_bindings"].get(key) == value
                                         for key, value in params.items()))
                _require(child["project_id"] == state["id"] and child["run_id"] == state["run_id"]
                         and child["code_identity"] == parent["code_identity"]
                         and child["command"] == child["method_instance"]["definition_ref"]["id"] == candidate["method_id"]
                         and child["source_snapshot_sha256"] == state["source_snapshot_sha256"]
                         and child["request_sha256"] == fingerprint(child_request)
                         and child["id"] == "action-" + fingerprint(
                             {"request_id": parent["child_request_id"], **child_request})[:32])
            if result_child is not None:
                _require(child is not None and result_child == {key: child[key] for key in
                    ("id", "request_id", "command", "status", "artifact", "result_sha256", "failure") if key in child}
                         and parent["status"] == child["status"])
            else:
                _require(parent["status"] in ("prepared", "running", "rejected"))
        # selection_ref is redundant display metadata, but must agree when saved.
        ref = decision.get("selection_ref")
        if ref is not None:
            _require(ref["context_sha256"] == context["context_sha256"]
                     and ref["candidate_id"] == (candidate["id"] if candidate else None)
                     and ref["provider_claim"] == selected["provider"]
                     and ref["evidence_citation_ids"] == selected["evidence_citation_ids"]
                     and ref["provider_verified"] is False and ref["model_execution_verified"] is False)
        return selected
    except ResearchError as error:
        if error.code == "EVIDENCE_CHANGED":
            raise
        raise ResearchError("EVIDENCE_CHANGED", "Saved selection identities could not be verified.") from None
    except (KeyError, TypeError, ValueError, AttributeError):
        raise ResearchError("EVIDENCE_CHANGED", "Saved selection record is incomplete or inconsistent.") from None


def _parents(state):
    parents = [item for item in state.get("controller_requests", []) if _imported(item)]
    _require(len({item["request_id"] for item in parents}) == len(parents))
    return parents


def selection_view(state) -> dict:
    parents = _parents(state)
    records = []
    # Verify every imported record, including those omitted from the bounded view.
    for parent in parents:
        selected = _verify(state, parent)
        candidate, context = selected["candidate"], parent["selection_context"]
        cited = set(selected["evidence_citation_ids"])
        records.append({
            "request_id": parent["request_id"], "status": parent["status"],
            "decision_kind": parent["decision"]["next_action"]["kind"],
            "method_id": candidate["method_id"] if candidate else None,
            "parameters": copy.deepcopy(candidate["parameters"] if candidate else {}),
            "rationale": selected["rationale"], "provider_claim": selected["provider"],
            "provider_verified": False, "model_execution_verified": False,
            "evidence": copy.deepcopy([item for item in context["evidence"] if item["citation_id"] in cited]),
            "context_sha256": context["context_sha256"], "snapshot_ref_before": parent["snapshot_ref_before"],
            "state_version_before": parent["state_version_before"],
            "controller_code_identity": parent["controller_code_identity"], "project_code_identity": parent["code_identity"],
            "baseline_decision": copy.deepcopy(context["baseline_decision"]),
            "child": copy.deepcopy((parent.get("result") or {}).get("child")),
            "request_sha256": parent["request_sha256"], "decision_sha256": parent["decision_sha256"],
        })
    records.sort(key=lambda item: item["state_version_before"], reverse=True)
    return {"schema_version": "project-selection-view-v1", "available": True,
            "records": records[:12], "total": len(records), "omitted": max(0, len(records) - 12)}


def read_selection_request(state, request_id) -> dict:
    identifier(request_id)
    parent = next((item for item in _parents(state) if item["request_id"] == request_id), None)
    if parent is None:
        raise ResearchError("ARTIFACT_NOT_FOUND", "No imported selection matches this request.")
    _verify(state, parent)
    return copy.deepcopy(parent)
