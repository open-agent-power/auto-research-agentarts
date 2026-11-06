"""Assess saved recipe validation; never dispatch a model or research action."""

import copy
from pathlib import Path

from . import recipe_change_proposal as protocol
from .contracts import ResearchError, canonical, fingerprint, identifier
from .project_selection import _json_value, _text
from .research_project import ResearchProject, safe_path, write_bytes_once
from .research_recipe import compile_recipe, parse_json
from .source_evidence_adapter import _read_file


MAX_ROUND_BYTES = 4 * 1024 * 1024
INPUT_FIELDS = {"schema_version", "round_id", "request_id", "evidence_kind", "current_recipe",
                "trace", "goal", "issue", "acceptance", "proposal_result", "validation_result",
                "previous_round", "next_question"}
PROPOSAL_FIELDS = {"schema_version", "request_id", "status", "candidate", "context_ref",
                   "prompt_ref", "response_ref", "scientific_validation"}
VALIDATION_FIELDS = {"schema_version", "request_id", "status", "baseline_decision", "candidate_decision",
                     "selection_changed", "controller_outcome", "artifact_refs", "scientific_validation"}
TERMINAL = {"completed", "waiting", "failed", "rejected"}
PENDING = {"pending", "unknown", "needs_review", "prepared", "sending", "received"}


def _require(condition, message, code="INVALID_IMPROVEMENT_ROUND"):
    if not condition:
        raise ResearchError(code, message)


def read_json(path):
    """Bounded strict JSON; no links, commands, deserialization hooks or URLs."""
    return parse_json(_read_file(safe_path(Path(path).absolute()), MAX_ROUND_BYTES),
                      maximum=MAX_ROUND_BYTES, code="INVALID_IMPROVEMENT_ROUND")


def _round_id(value):
    identifier(value, "round_id")
    _require(value not in (".", "..") and ":" not in value, "Use a portable round directory identity.")
    return value


def _selected_pair(decision, selection):
    selected = next((item for item in selection["candidates"]
                     if item["id"] == decision["selected_candidate_id"]), None)
    return None if selected is None else {key: selected[key] for key in ("method_id", "evaluation_ref")}


def _assess(value):
    """Recompute a decision from the complete frozen bundle, including on replay."""
    _json_value(value, MAX_ROUND_BYTES, "INVALID_IMPROVEMENT_ROUND")
    _require(type(value) is dict and set(value) == INPUT_FIELDS
             and value["schema_version"] == "recipe-improvement-input-v1", "Use the complete round input.")
    _round_id(value["round_id"])
    identifier(value["request_id"])
    _require(value["evidence_kind"] in ("synthetic_engineering_fixture", "saved_host_validation"),
             "Declare fixture or saved Host evidence; neither establishes scientific benefit.")
    context = {"schema_version": "recipe-change-context-v1", "current_recipe": value["current_recipe"],
               "research_context": value["trace"], "improvement_goal": value["goal"]}
    protocol._context(context)
    issue = value["issue"]
    _require(type(issue) is dict and set(issue) == {"summary", "feedback_action_ids"}
             and _text(issue["summary"], 2000), "Identify one concrete feedback problem.")
    refs = issue["feedback_action_ids"]
    _require(type(refs) is list and bool(refs) and all(_text(item, 160) for item in refs)
             and len(set(refs)) == len(refs) and set(refs) <= protocol._feedback_ids(context),
             "The issue must reference supplied completed or failed actions.")
    _require(_text(value["next_question"], 4000), "Save one explicit next-round question.")
    selection = value["trace"]["selection_context"]
    target = value["acceptance"]
    _require(type(target) is dict and set(target) == {"method_id", "evaluation_ref"}
             and all(_text(target[key], 1000) for key in target)
             and target in [{key: item[key] for key in target} for item in selection["conditions"]],
             "Acceptance must name one frozen method/evaluation pair.")
    previous = value["previous_round"]
    if previous is not None:
        _require(type(previous) is dict and set(previous) == {"round_id", "result_sha256", "result"},
                 "Use a complete prior round receipt.")
        prior = previous["result"]
        _require(type(prior) is dict and prior.get("schema_version") == "recipe-improvement-result-v1"
                 and prior.get("status") == "completed" and prior.get("round_id") == previous["round_id"]
                 and fingerprint(prior) == previous["result_sha256"]
                 and prior.get("effective_recipe") == value["current_recipe"]
                 and prior.get("evidence_kind") == value["evidence_kind"]
                 and prior.get("project_id") == selection["project_id"],
                 "Continue the same project and evidence kind from its actual effective recipe.")
    proposal = value["proposal_result"]
    _require(type(proposal) is dict and set(proposal) == PROPOSAL_FIELDS
             and proposal["schema_version"] == "recipe-change-proposal-result-v1"
             and proposal["request_id"] == value["request_id"] and proposal["scientific_validation"] is False
             and all(_text(proposal[key], 1000) for key in ("context_ref", "prompt_ref"))
             and (proposal["response_ref"] is None or _text(proposal["response_ref"], 1000)),
             "Use the original adapter proposal result and request identity.")
    result = {"schema_version": "recipe-improvement-result-v1", "round_id": value["round_id"],
              "request_id": value["request_id"], "project_id": selection["project_id"],
              "input_sha256": fingerprint(value), "evidence_kind": value["evidence_kind"],
              "status": "pending", "decision": "pending", "reason": "PROPOSAL_NOT_READY",
              "explanation": "提案尚未就绪，保留当前有效配方；先核对原请求，不重新派发。",
              "issue": copy.deepcopy(issue), "goal": value["goal"], "acceptance": copy.deepcopy(target),
              "checks": {}, "base_version": value["current_recipe"]["version"], "candidate_version": None,
              "effective_recipe": copy.deepcopy(value["current_recipe"]),
              "previous_round_id": previous["round_id"] if previous else None,
              "previous_decision": previous["result"]["decision"] if previous else None,
              "next_question": value["next_question"], "scientific_validation": False}
    if proposal["status"] != "proposed":
        _require(type(proposal["status"]) is str and proposal["status"] in PENDING | {"failed", "rejected"}
                 and proposal["candidate"] is None
                 and value["validation_result"] is None, "Unready proposals cannot be validated or adopted.")
        if proposal["status"] in ("failed", "rejected"):
            result.update(status="completed", decision="revert", reason="PROPOSAL_FAILED",
                          explanation="原提案失败或被拒绝，没有可采用候选；当前有效配方不变。")
        return result
    candidate = protocol.validate_proposal(context, proposal["candidate"])
    _require(set(refs) <= set(candidate["feedback_action_ids"]), "The candidate must address this issue's feedback.")
    result["candidate_version"] = candidate["candidate"]["version"]
    validation = value["validation_result"]
    result["reason"] = "VALIDATION_NOT_READY"
    result["explanation"] = "候选已保存，但没有完整验证结果；保留原版，先核对同一原请求。"
    if validation is None:
        return result
    baseline = compile_recipe(value["current_recipe"], selection)
    proposed = compile_recipe(candidate["candidate"], selection)
    _require(type(validation) is dict and set(validation) == VALIDATION_FIELDS
             and validation["schema_version"] == "recipe-change-validation-v1"
             and validation["request_id"] == value["request_id"] and validation["scientific_validation"] is False
             and validation["baseline_decision"] == baseline and validation["candidate_decision"] == proposed
             and type(validation["selection_changed"]) is bool
             and validation["selection_changed"] == (baseline["proposal"]["choice"] != proposed["proposal"]["choice"])
             and type(validation["artifact_refs"]) is list
             and all(_text(item, 1000) for item in validation["artifact_refs"]),
             "Saved validation must match the original request and both recomputed decisions.")
    outcome = validation["controller_outcome"]
    _require(type(outcome) is dict and outcome.get("schema_version") == "project-controller-advance-v1"
             and outcome.get("project_id") == selection["project_id"]
             and outcome.get("request_id") == value["request_id"]
             and outcome.get("status") == validation["status"]
             and outcome.get("selection_context_sha256") == selection["context_sha256"]
             and outcome.get("selection_proposal") == proposed["proposal"]
             and outcome.get("recipe_decision") == proposed and outcome.get("scientific_validation") is False,
             "The controller receipt must bind this request, context and candidate.")
    _require(type(validation["status"]) is str and validation["status"] in TERMINAL | PENDING,
             "Unsupported validation status.")
    if validation["status"] not in TERMINAL:
        result["reason"] = "EXECUTION_UNRESOLVED"
        result["explanation"] = "原验证执行状态未决；不能采用、不能认定失败，也不能自动重发。"
        return result
    checks = {"baseline_misses_target": _selected_pair(baseline, selection) != target,
              "candidate_selects_target": _selected_pair(proposed, selection) == target,
              "controller_completed": validation["status"] == "completed",
              "completed_artifact_recorded": bool(validation["artifact_refs"])
                  and _text(outcome.get("child_request_id"), 160)}
    keep = all(checks.values())
    result.update(status="completed", decision="keep" if keep else "revert", checks=checks,
                  reason="BOUNDED_ACCEPTANCE_MET" if keep else "BOUNDED_ACCEPTANCE_NOT_MET")
    failures = {"baseline_misses_target": "原版已满足目标，没有证明本轮改善",
                "candidate_selects_target": "候选没有选择目标方法与评价",
                "controller_completed": "原控制器未完成验证",
                "completed_artifact_recorded": "缺少完成行动身份或工件引用"}
    result["explanation"] = ("采用候选：原版未满足目标，候选选择了指定方法与评价，原控制器验证完成且记录工件。"
                             if keep else "保留原版：" + "；".join(failures[key] for key, passed in checks.items() if not passed))
    result["explanation"] += " 仅为本轮工程验收，不代表科学收益，也不撤销既有验证行动。"
    if keep:
        result["effective_recipe"] = copy.deepcopy(candidate["candidate"])
    return result


def read_improvement_round(directory, round_id):
    """Read and recheck one immutable receipt; no project/Host dispatch or recovery."""
    folder = safe_path(Path(directory).absolute() / _round_id(round_id))
    value, result = read_json(folder / "input.json"), read_json(folder / "result.json")
    _require(value["round_id"] == round_id and result == _assess(value),
             "Round evidence differs from its recomputed decision.", "EVIDENCE_CHANGED")
    _require(read_json(folder / "effective-recipe.json") == result["effective_recipe"],
             "Effective recipe differs from its round receipt.", "EVIDENCE_CHANGED")
    return result


def run_improvement_round(current_version, trace, goal, proposal_result, validation_result, *,
                          directory, round_id, request_id, issue, acceptance, next_question,
                          evidence_kind, previous_round_id=None):
    """Assess already-saved callbacks' outputs. Keep/revert is not tool execution.

    A pending snapshot remains immutable; after reconciliation use a new round ID
    with the SAME Host request, not a new model/tool request. Full resume is a later task.
    """
    root = safe_path(Path(directory).absolute())
    _round_id(round_id)
    _require(previous_round_id != round_id, "A round cannot be its own predecessor.")
    root.mkdir(parents=True, exist_ok=True)
    with ResearchProject(root)._writer():
        prior = None
        if previous_round_id is not None:
            saved = read_improvement_round(root, previous_round_id)
            prior = {"round_id": previous_round_id, "result_sha256": fingerprint(saved), "result": saved}
        value = copy.deepcopy({"schema_version": "recipe-improvement-input-v1", "round_id": round_id,
            "request_id": request_id, "evidence_kind": evidence_kind, "current_recipe": current_version,
            "trace": trace, "goal": goal, "issue": issue, "acceptance": acceptance,
            "proposal_result": proposal_result, "validation_result": validation_result,
            "previous_round": prior, "next_question": next_question})
        result = _assess(value)
        folder = safe_path(root / round_id)
        folder.mkdir(exist_ok=True)
        for name, content in (("input.json", value), ("result.json", result),
                              ("effective-recipe.json", result["effective_recipe"])):
            write_bytes_once(folder / name, canonical(content).encode("utf-8"))
        return result
