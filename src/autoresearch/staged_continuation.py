"""Pure, read-only bindings for a staged retrieval continuation.

This module neither owns a journal nor dispatches, resumes, scores, opens the
private holdout, freezes strategy or exports reports. Workbench persists the
intent and invokes the existing native interfaces only after these checks.
"""
import copy
import hashlib
import json
from pathlib import Path

from . import method_registry as registry, project_controller, project_selection, retrieval_holdout, staged_relevance_adapter as staged
from .contracts import ResearchError, canonical, fingerprint, identifier
from .research_project import code_identity as project_identity


def _require(condition, code, message):
    if not condition:
        raise ResearchError(code, message)


def code_identity():
    return hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


def selection_proposal(context, method_id, primary_binding):
    """Compile exactly one original audit/final candidate in a sealed context."""
    _require(type(method_id) is str and method_id in (staged.AUDIT_TOOL_ID, retrieval_holdout.FINAL_TOOL_ID)
             and type(primary_binding) is dict and set(primary_binding) == {"action_id", "request_id", "result_sha256"},
             "INVALID_REQUEST", "Use the original primary and a fixed staged method.")
    identifier(primary_binding["action_id"], "primary_action_id")
    identifier(primary_binding["request_id"], "primary_request_id")
    result_sha = primary_binding["result_sha256"]
    _require(type(result_sha) is str and len(result_sha) == 64 and all(c in "0123456789abcdef" for c in result_sha),
             "INVALID_REQUEST", "The original primary result SHA is required.")
    wait = {"schema_version": "project-selection-proposal-v1", "context_sha256": context.get("context_sha256") if type(context) is dict else None,
            "provider": {"kind": "operator_assistant", "label": "staged-evaluation-continuation-v1"},
            "choice": {"kind": "wait"}, "rationale": "Check the fixed staged continuation context.", "evidence_citation_ids": []}
    project_selection.validate_proposal(context, wait)
    _require(not context["blockers"], "SELECTION_BLOCKED", "Original host blockers prohibit the next stage.")
    params = {"based_on_action_id": primary_binding["action_id"], "based_on_result_sha256": result_sha}
    matches = [candidate for candidate in context["candidates"] if candidate["method_id"] == method_id
               and candidate["parameters"] == params and candidate["evaluation_ref"] == registry.evaluation_ref(method_id)]
    _require(len(matches) == 1, "CONDITION_NOT_SATISFIED", "One exact original staged candidate is required.")
    proposal = {**wait, "choice": {"kind": "execute", "candidate_id": matches[0]["id"]},
                "rationale": "Execute the authorized fixed staged continuation using the original primary result."}
    project_selection.validate_proposal(context, proposal)
    return proposal


def _action_row(project, state, action, method, predecessor=None):
    _require(type(action) is dict and action.get("command") == method and action.get("project_id") == state["id"]
             and action.get("run_id") == state["run_id"] and action.get("code_identity") == state["code_identity"]
             and action.get("source_snapshot_sha256") == state["source_snapshot_sha256"]
             and action.get("method_instance", {}).get("evaluation_ref") == registry.evaluation_ref(method)
             and action.get("method_instance", {}).get("definition_ref") == {"id": method, "version": registry.get_analysis(method).ADAPTER_VERSION}
             and action.get("method_instance", {}).get("scope") == state["source_scope"],
             "EVIDENCE_CHANGED", "The original staged action identity differs.")
    identifier(action["request_id"], "action_request_id")
    identifier(action["id"], "action_id")
    request = {"project_id": state["id"], "command": method, "dimension": None,
               "source_snapshot_sha256": state["source_snapshot_sha256"]}
    if predecessor is not None:
        _require(action.get("parameters") == predecessor and action["method_instance"].get("parameters") == predecessor,
                 "EVIDENCE_CHANGED", "The staged action is not bound to the original primary result.")
        request.update(parameters=predecessor, evaluation_ref=registry.evaluation_ref(method))
    with project._connect(readonly=True) as con:
        row = con.execute("SELECT fingerprint, record FROM actions WHERE request_id=?", (action["request_id"],)).fetchone()
    _require(row is not None and json.loads(row["record"]) == action
             and row["fingerprint"] == action.get("request_sha256") == fingerprint(request),
             "EVIDENCE_CHANGED", "The original staged action database fingerprint changed.")
    return action


def _envelope(project, state, action):
    _require(action["status"] == "completed" and action.get("failure") is None
             and action.get("artifact") == "artifacts/" + action["id"] + ".json",
             "EVIDENCE_CHANGED", "An original completed artifact is required.")
    envelope = json.loads(project._artifact(action).read_bytes())
    _require(type(envelope) is dict and set(envelope) == {"action_id", "request_sha256", "code_identity", "source_snapshot_sha256", "sha256", "tool_result"}
             and envelope["sha256"] == action["result_sha256"] == fingerprint({key: value for key, value in envelope.items() if key != "sha256"})
             and envelope["action_id"] == action["id"] and envelope["request_sha256"] == action["request_sha256"]
             and envelope["code_identity"] == state["code_identity"]
             and envelope["source_snapshot_sha256"] == state["source_snapshot_sha256"],
             "EVIDENCE_CHANGED", "The original staged result envelope changed.")
    return envelope["tool_result"]


def _parent(state, action, method, predecessor):
    """Verify the original selection parent, never resume it or dispatch a child."""
    matches = [parent for parent in state.get("controller_requests", []) if parent.get("child_request_id") == action["request_id"]]
    _require(len(matches) == 1, "EVIDENCE_CHANGED", "The original controller parent is missing or ambiguous.")
    parent = matches[0]
    context, request, decision = parent["selection_context"], parent["request"], parent["decision"]
    _require(parent.get("project_id") == state["id"] and parent.get("code_identity") == state["code_identity"]
             and parent.get("controller_code_identity") == project_controller.code_identity()
             and parent.get("source_snapshot_sha256") == state["source_snapshot_sha256"]
             and parent.get("request_sha256") == fingerprint(request) and parent.get("decision_sha256") == fingerprint(decision)
             and type(request) is dict and set(request) == {"project_id", "command", "need", "expected_state_version", "proposal"}
             and request.get("command") == "controller.advance_selection" and request.get("project_id") == state["id"]
             and request.get("need") == "next_check" and context.get("need") == request["need"]
             and action["request_id"] == "controller-child-" + fingerprint({"project_id": state["id"], "request_id": parent["request_id"]})[:32]
             and context.get("project_id") == state["id"] and context.get("run_id") == state["run_id"]
             and context.get("source_snapshot_sha256") == state["source_snapshot_sha256"]
             and context.get("project_code_identity") == state["code_identity"]
             and context.get("controller_code_identity") == parent.get("controller_code_identity")
             and fingerprint(context.get("research_plan")) == state["private_evaluation"]["plan_sha256"]
             and context.get("staged_evaluation", {}).get("holdout_sha256") == state["private_evaluation"]["sha256"]
             and type(parent.get("state_version_before")) is int
             and context.get("state_version") == parent.get("state_version_before")
             and context.get("snapshot_ref") == parent.get("snapshot_ref_before")
             and parent.get("dispatch_state_version") == parent["state_version_before"] + 1
             and (request.get("expected_state_version") is None or
                  type(request["expected_state_version"]) is int and request["expected_state_version"] == context["state_version"]),
             "EVIDENCE_CHANGED", "The original controller request/context binding changed.")
    selected = project_selection.validate_proposal(context, request["proposal"])["candidate"]
    _require(type(selected) is dict and selected["method_id"] == method and selected["parameters"] == predecessor
             and selected["evaluation_ref"] == registry.evaluation_ref(method)
             and decision.get("next_action", {}).get("method_id") == method
             and decision["next_action"].get("parameters", {}) == predecessor
             and decision.get("selection_ref", {}).get("candidate_id") == selected["id"]
             and decision["selection_ref"].get("context_sha256") == context["context_sha256"],
             "EVIDENCE_CHANGED", "The original controller did not select the bound staged candidate.")
    if action["status"] == "completed":
        fields = ("id", "request_id", "command", "status", "artifact", "result_sha256", "failure")
        result = parent.get("result")
        _require(parent.get("status") == "completed" and type(result) is dict and set(result) == {"child", "recovered", "reused"}
                 and type(result["recovered"]) is bool and result["reused"] is False
                 and all(field in action for field in fields) and result["child"] == {key: action[key] for key in fields}
                 and type(parent.get("state_version_after")) is int
                 and parent["dispatch_state_version"] < parent["state_version_after"] <= state["state_version"],
                 "EVIDENCE_CHANGED", "The original completed parent and child do not match.")
    return parent


def _projection(action, parent):
    return {"action_id": action["id"], "request_id": action["request_id"], "result_sha256": action.get("result_sha256"),
            "status": action["status"], "parent_request_id": parent["request_id"]}


def _inspect(project, state, primary_action_id):
    identifier(primary_action_id, "primary_action_id")
    current = project.status()
    _require(current["snapshot_ref"] == state["snapshot_ref"]
             and fingerprint({key: value for key, value in state.items() if key != "snapshot_ref"}) == state["snapshot_ref"],
             "STALE_STATE", "Use the current saved project snapshot.")
    _require(state["code_identity"] == project_identity(), "CODE_CHANGED", "Use the project's registered source implementation.")
    _require(state["registration"]["method_id"] == staged.TOOL_ID,
             "METHOD_NOT_SUPPORTED", "A staged development project is required.")
    project._source(state)
    metadata = retrieval_holdout.validate_metadata(state)
    _require(metadata is not None and metadata.get("private_evaluation") is not None,
             "CONDITION_NOT_SATISFIED", "The original preregistered holdout is required.")
    primary, original, primary_result = retrieval_holdout._original(project, state, primary_action_id)
    _action_row(project, state, primary, staged.TOOL_ID)
    primary_binding = {"action_id": primary["id"], "request_id": primary["request_id"], "result_sha256": primary["result_sha256"]}
    predecessor = {"based_on_action_id": primary["id"], "based_on_result_sha256": primary["result_sha256"]}
    holdout = metadata["private_evaluation"]
    _require(holdout["project_id"] == state["id"] and holdout["run_id"] == state["run_id"]
             and holdout["source_snapshot_sha256"] == state["source_snapshot_sha256"]
             and holdout["project_code_identity"] == state["code_identity"] and state.get("plan_revisions")
             and fingerprint(state["plan_revisions"][-1]) == holdout["plan_sha256"],
             "EVIDENCE_CHANGED", "The original holdout, plan, source or code changed.")
    blockers = []
    for action in state["actions"] + state["evidence_actions"]:
        if action.get("status") in ("running", "pending", "unknown"):
            blockers.append({"code": "EXECUTION_UNKNOWN", "reason": "An original project action remains unresolved."})
        elif action.get("status") == "failed":
            blockers.append({"code": "ACTION_FAILED", "reason": "An original project action failed; do not substitute another request."})
    for parent in state.get("controller_requests", []):
        if parent.get("status") in ("prepared", "running", "unknown"):
            blockers.append({"code": "EXECUTION_UNKNOWN", "reason": "An original controller request remains unresolved."})
        elif parent.get("status") in ("failed", "rejected"):
            blockers.append({"code": "ACTION_FAILED", "reason": "An original controller request failed; do not substitute another request."})
    if any(item.get("status") in ("sending", "unknown") for item in state.get("source_requests", [])):
        blockers.append({"code": "EXECUTION_UNKNOWN", "reason": "An original source request remains unresolved."})
    if any(item.get("status") == "reserved" for item in state.get("local_model_requests", [])):
        blockers.append({"code": "EXECUTION_UNKNOWN", "reason": "An original model request remains reserved."})
    stages = {}
    parents = {}
    for name, method in (("audit", staged.AUDIT_TOOL_ID), ("final", retrieval_holdout.FINAL_TOOL_ID)):
        actions = [a for a in state["actions"] if a.get("command") == method]
        _require(len(actions) <= 1, "EVIDENCE_CHANGED", "The staged method has multiple original actions.")
        if not actions:
            stages[name], parents[name] = None, None
            continue
        action = _action_row(project, state, actions[0], method, predecessor)
        _require(action.get("status") in ("running", "pending", "unknown", "failed", "completed"),
                 "EVIDENCE_CHANGED", "The original staged action status is invalid.")
        parent = _parent(state, action, method, predecessor)
        stages[name], parents[name] = _projection(action, parent), parent
        if action["status"] != "completed":
            continue
        tool = _envelope(project, state, action)
        if name == "audit":
            staged.AUDIT.next_decision(tool)
            audit = tool["result"]
            summary, deltas, adverse = staged._paired(primary_result["per_query_metrics"])
            _require(audit.get("stage") == "development" and audit.get("scope") == state["source_scope"]
                     and audit.get("source_snapshot_sha256") == state["source_snapshot_sha256"]
                     and audit.get("predecessor") == predecessor
                     and audit.get("rankings_sha256") == primary_result["rankings_before_scoring_sha256"]
                     and canonical(audit.get("summary")) == canonical(summary)
                     and canonical(audit.get("per_query_deltas")) == canonical(deltas)
                     and canonical(audit.get("adverse_queries")) == canonical(adverse)
                     and audit.get("usage") == {"query_pairs": len(deltas), "index_builds": 0, "ranking_calls": 0,
                                                "scoring_calls": 0, "native_fits": 0, "model_calls": 0},
                     "EVIDENCE_CHANGED", "The original saved audit does not match its primary result.")
        else:
            retrieval_holdout.validate_final_result(tool)
            stages[name]["freeze_sha256"] = tool["result"]["freeze_sha256"]
            stages[name]["holdout_sha256"] = tool["result"]["holdout_sha256"]
            stages[name]["selected_method"] = tool["result"]["selected_method"]
    frozen = state.get("frozen_evaluation_strategy")
    freeze_projection = None
    if frozen is not None:
        retrieval_holdout._check_frozen(project, state, frozen)
        _require(frozen["primary_action_id"] == primary["id"] and frozen["primary_result_sha256"] == primary["result_sha256"],
                 "EVIDENCE_CHANGED", "The original freeze targets another primary result.")
        freeze_version = frozen["request"]["expected_state_version"]
        freeze_projection = {"request_id": frozen["request_id"], "record_sha256": frozen["record_sha256"],
                             "selected_method": frozen["selected_method"], "validation_delta_recall20": frozen["validation_delta_recall20"],
                             "state_version_before": freeze_version}
        audit_parent = parents["audit"]
        _require(stages["audit"] is not None and stages["audit"]["status"] == "completed" and audit_parent is not None
                 and type(audit_parent.get("state_version_after")) is int and audit_parent["state_version_after"] <= freeze_version,
                 "EVIDENCE_CHANGED", "Audit-before-freeze order is missing or cannot be proven.")
    if stages["final"] is not None:
        _require(frozen is not None and parents["final"] is not None
                 and type(parents["final"].get("state_version_before")) is int
                 and parents["final"]["state_version_before"] >= frozen["request"]["expected_state_version"] + 1
                 and parents["final"]["selection_context"].get("staged_evaluation", {}).get("freeze", {}).get("freeze_sha256") == frozen["record_sha256"],
                 "EVIDENCE_CHANGED", "Freeze-before-final order is missing or cannot be proven.")
        if stages["final"]["status"] == "completed":
            _require(stages["final"]["freeze_sha256"] == frozen["record_sha256"]
                     and stages["final"]["holdout_sha256"] == holdout["sha256"]
                     and stages["final"]["selected_method"] == frozen["selected_method"],
                     "EVIDENCE_CHANGED", "The original final result differs from the frozen strategy or holdout.")
    budget = state["budget"]
    available = budget["local_tool_call_limit"] - budget["local_tool_calls_used"] - budget["local_tool_calls_reserved"]
    needed = sum(stages[name] is None for name in ("audit", "final"))
    if available < needed:
        blockers.append({"code": "BUDGET_EXHAUSTED", "reason": "The original tool allowance cannot cover the remaining fixed stages."})
    _require(project.status()["snapshot_ref"] == state["snapshot_ref"], "STALE_STATE", "The project changed while inspecting saved stages.")
    return {"schema_version": "staged-continuation-inspection-v1", "primary": primary_binding,
            "audit": stages["audit"], "freeze": freeze_projection, "final": stages["final"],
            "required_tool_calls": needed, "available_tool_calls": available, "blockers": blockers, "scientific_validation": False}


def inspect(project, state, primary_action_id):
    try:
        return _inspect(project, state, primary_action_id)
    except ResearchError:
        raise
    except (KeyError, TypeError, ValueError, OSError, UnicodeError, OverflowError, RecursionError, AttributeError):
        raise ResearchError("EVIDENCE_CHANGED", "Original staged continuation evidence is unavailable or malformed.") from None
