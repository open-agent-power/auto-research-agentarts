"""Preregister fixed validation conditions and read only their original saved results.

This continuation defines a new contract; it does not restore the unavailable S041
v2 contract. No controller dispatch, ranking, scoring, fit or scientific adoption
is performed here.
"""
import copy
import json
import math
import operator
import re

from . import saved_retrieval_reader as reader
from .contracts import ResearchError, canonical, fingerprint, identifier
from .research_project import require

MAX_ITEMS = 16
OPS = {"gt": operator.gt, "gte": operator.ge, "lt": operator.lt,
       "lte": operator.le, "eq": operator.eq}
TEST_NOTICE = "Existing retrieval adapters have already computed test metrics; they are not blind."


def _condition(hypothesis):
    fields = {"candidate_id", "controller_request_id", "metric", "operator", "threshold"}
    require(type(hypothesis) is dict and fields <= set(hypothesis) <= fields | {"branches"},
        "INVALID_REQUEST", "Use the exact preregistration fields; test metrics are not supported.")
    identifier(hypothesis["candidate_id"], "candidate_id")
    identifier(hypothesis["controller_request_id"], "controller_request_id")
    value = hypothesis["threshold"]
    require(type(hypothesis["metric"]) is str and hypothesis["metric"] in reader.METRICS
            and type(hypothesis["operator"]) is str and hypothesis["operator"] in OPS
            and type(value) in (int, float) and -1 <= value <= 1 and math.isfinite(value),
            "INVALID_REQUEST", "Use a saved validation metric, comparison operator and finite delta threshold in [-1, 1].")
    return {"split": "validation", "measure": "candidate_minus_baseline", "metric": hypothesis["metric"],
            "operator": hypothesis["operator"], "threshold": value}


def _branches(value, primary_method_id):
    """Permit only wait or the same family's existing saved-audit method."""
    family = reader._family(primary_method_id)
    require(primary_method_id == family.module.TOOL_ID and type(value) is dict
            and set(value) == {"condition_met", "condition_not_met"},
            "INVALID_REQUEST", "Provide exactly the two known-outcome branches; unknown always waits.")
    for branch in value.values():
        require(type(branch) is dict and (branch == {"kind": "wait"}
                or branch == {"kind": "method", "method_id": family.module.AUDIT_TOOL_ID}),
                "INVALID_REQUEST", "A branch can only wait or select this retrieval family's existing saved audit.")
    return copy.deepcopy(value)


def register(project, *, request_id, expected_state_version, hypothesis):
    """Persist one prediction before its explicitly named controller request exists."""
    identifier(request_id)
    require(type(expected_state_version) is int and expected_state_version >= 0,
            "INVALID_REQUEST", "An exact state version is required.")
    condition = _condition(hypothesis)
    target = hypothesis["controller_request_id"]
    require(target != request_id, "INVALID_REQUEST", "Registration and controller request IDs must differ.")
    request = {"request_id": request_id, "expected_state_version": expected_state_version,
               "hypothesis": copy.deepcopy(hypothesis)}
    with project._writer(), project._connect() as con:
        stored = project._project(con)
        records = stored.get("hypothesis_registrations", [])
        previous = next((item for item in records if item["request_id"] == request_id), None)
        if previous is not None:
            require(previous["request_sha256"] == fingerprint(request), "IDEMPOTENCY_CONFLICT", "Preregistration ID has different content.")
            _check_record(previous)
            project._source(stored)
            require(stored["registration"]["source_sha256"] == previous["source_sha256"]
                    and stored["source_snapshot_sha256"] == previous["source_snapshot_sha256"]
                    and fingerprint(stored["source_scope"]) == previous["scope_sha256"],
                    "EVIDENCE_CHANGED", "The registered source binding changed.")
            return copy.deepcopy(previous)
        require(len(records) < MAX_ITEMS, "LIMIT_EXCEEDED", "At most sixteen predictions may be registered per project.")
        require(project._action(con, request_id) is None and project._action(con, target) is None,
                "IDEMPOTENCY_CONFLICT", "An ID belongs to an existing action.")
        project._require_unclaimed(stored, request_id, except_collection="hypothesis_registrations")
        project._require_unclaimed(stored, target)
        require(not any(item["controller_request_id"] == target for item in records),
                "IDEMPOTENCY_CONFLICT", "The future controller ID is already bound to a prediction.")
        current = project.status()
        project._require_fresh(stored, current, expected_state_version)
        require(not any(item["status"] in ("prepared", "running", "unknown") for item in stored.get("controller_requests", []))
                and not any(item["status"] == "reserved" for item in stored.get("local_model_requests", [])),
                "PROJECT_BUSY", "Reconcile the existing request before registering a prediction.")
        from .host_model_selection import HostModelSelection, PENDING
        require(not any(item["status"] in PENDING for item in HostModelSelection(project.root).status()["requests"]),
                "HOST_SELECTION_PENDING", "Reconcile the existing host request first.")
        project._source(stored)  # Verify the actual pinned bytes before accepting a registration.
        plans = stored.get("plan_revisions", [])
        require(bool(plans), "CONDITION_NOT_SATISFIED", "Save a research plan before registering a prediction.")
        from .project_controller import ProjectController
        context = ProjectController(project.root)._selection_context(current, "next_check")
        matches = [item for item in context["candidates"] if item["id"] == hypothesis["candidate_id"]]
        require(len(matches) == 1 and not context["blockers"], "CONDITION_NOT_SATISFIED", "Choose one currently eligible candidate.")
        candidate = matches[0]
        family = reader._family(candidate["method_id"])
        require(candidate["method_id"] == family.module.TOOL_ID and not candidate["parameters"]
                and candidate["method_id"] == stored["registration"]["method_id"],
                "CONDITION_NOT_SATISFIED", "Only the existing primary citation or relevance pair can be predicted.")
        branches = _branches(hypothesis["branches"], candidate["method_id"]) if "branches" in hypothesis else None
        record = {"schema_version": "hypothesis-registration-v1", "request_id": request_id,
                  "request_sha256": fingerprint(request), "request": request, "controller_request_id": target,
                  "project_id": stored["id"], "run_id": stored["run_id"],
                  "state_version_before": expected_state_version, "candidate": copy.deepcopy(candidate),
                  "condition": condition, "source_sha256": stored["registration"]["source_sha256"],
                  "source_snapshot_sha256": stored["source_snapshot_sha256"],
                  "scope_sha256": fingerprint(stored["source_scope"]),
                  "protocol_sha256": fingerprint(family.module.COMPARISON),
                  "plan_sha256": fingerprint(plans[-1]), "plan_version": plans[-1]["version"],
                  "project_code_identity": stored["code_identity"],
                  "controller_code_identity": context["controller_code_identity"],
                  "selection_context_sha256": context["context_sha256"], "scientific_validation": False}
        if branches is not None:
            record["branches"] = branches
        record["registration_sha256"] = fingerprint(record)
        stored.setdefault("hypothesis_registrations", []).append(record)
        stored["state_version"] += 1
        project._save(con, stored)
        return copy.deepcopy(record)


def _check_record(record):
    require(type(record) is dict and record.get("schema_version") == "hypothesis-registration-v1"
            and record.get("scientific_validation") is False
            and record.get("registration_sha256") == fingerprint({k: v for k, v in record.items() if k != "registration_sha256"})
            and record.get("request_sha256") == fingerprint(record.get("request"))
            and record.get("condition") == _condition(record["request"]["hypothesis"])
            and record.get("controller_request_id") == record["request"]["hypothesis"]["controller_request_id"]
            and record.get("request_id") == record["request"]["request_id"]
            and record.get("state_version_before") == record["request"]["expected_state_version"]
            and record.get("candidate", {}).get("id") == record["request"]["hypothesis"]["candidate_id"],
            "EVIDENCE_CHANGED", "Saved prediction registration changed.")
    hypothesis = record["request"]["hypothesis"]
    require(("branches" in record) == ("branches" in hypothesis),
            "EVIDENCE_CHANGED", "Registered branch presence changed.")
    if "branches" in hypothesis:
        require(record["branches"] == hypothesis["branches"]
                and record["branches"] == _branches(hypothesis["branches"], record["candidate"]["method_id"]),
                "EVIDENCE_CHANGED", "Registered branch content changed.")


def _outcome(project, state, record):
    """Observe the named original parent/child; never perform recovery or rerun."""
    try:
        project._source(state)
        if (state["id"] != record["project_id"] or state["run_id"] != record["run_id"]
                or state["registration"]["source_sha256"] != record["source_sha256"]
                or state["source_snapshot_sha256"] != record["source_snapshot_sha256"]
                or fingerprint(state["source_scope"]) != record["scope_sha256"]):
            return None, "source_binding_changed", None, None
        plans = [p for p in state.get("plan_revisions", []) if p.get("version") == record["plan_version"]]
        if len(plans) != 1 or fingerprint(plans[0]) != record["plan_sha256"]:
            return None, "plan_binding_changed", None, None
        parents = [p for p in state.get("controller_requests", []) if p["request_id"] == record["controller_request_id"]]
        if not parents:
            target = record["controller_request_id"]
            with project._connect(readonly=True) as con:
                claimed_action = project._action(con, target) is not None
            claimed_record = any(type(rows) is list and any(type(row) is dict and row.get("request_id") == target for row in rows)
                                 for key, rows in state.items() if key != "controller_requests")
            if claimed_action or claimed_record:
                return None, "controller_id_claimed_by_other_command", None, None
            return None, "controller_not_started", None, None
        if len(parents) != 1:
            return None, "controller_binding_changed", None, None
        parent = parents[0]
        if parent["status"] != "completed":
            return None, "controller_" + parent["status"], None, None
        child_id = "controller-child-" + fingerprint({"project_id": state["id"], "request_id": parent["request_id"]})[:32]
        decision = parent["decision"]
        context = parent.get("selection_context")
        plan = context.get("research_plan") if type(context) is dict else None
        candidate = record["candidate"]
        selection = decision.get("selection_ref", {})
        from .project_selection import validate_proposal
        selected = validate_proposal(context, parent["request"]["proposal"])
        request = parent["request"]
        if (parent["project_id"] != record["project_id"] or parent["state_version_before"] <= record["state_version_before"]
                or parent["code_identity"] != record["project_code_identity"]
                or parent["controller_code_identity"] != record["controller_code_identity"]
                or parent["source_snapshot_sha256"] != record["source_snapshot_sha256"]
                or set(request) != {"project_id", "command", "need", "expected_state_version", "proposal"}
                or request["project_id"] != record["project_id"] or request["command"] != "controller.advance_selection"
                or request["need"] != "next_check" or request["need"] != context.get("need")
                or (request["expected_state_version"] is not None
                    and (type(request["expected_state_version"]) is not int
                         or request["expected_state_version"] != context.get("state_version")))
                or parent["request_sha256"] != fingerprint(parent["request"])
                or parent["decision_sha256"] != fingerprint(decision)
                or parent["dispatch_state_version"] != parent["state_version_before"] + 1
                or type(parent.get("state_version_after")) is not int
                or not parent["dispatch_state_version"] < parent["state_version_after"] <= state["state_version"]
                or parent["child_request_id"] != child_id
                or type(context) is not dict or context.get("context_sha256") != fingerprint({k: v for k, v in context.items() if k != "context_sha256"})
                or context.get("project_id") != record["project_id"] or context.get("run_id") != record["run_id"]
                or context.get("source_snapshot_sha256") != record["source_snapshot_sha256"]
                or context.get("project_code_identity") != record["project_code_identity"]
                or context.get("controller_code_identity") != record["controller_code_identity"]
                or context.get("state_version") != parent["state_version_before"]
                or fingerprint(plan) != record["plan_sha256"]
                or selection.get("context_sha256") != context["context_sha256"]
                or selection.get("candidate_id") != candidate["id"]
                or candidate not in context["candidates"] or selected.get("candidate") != candidate
                or decision["next_action"].get("method_id") != candidate["method_id"]
                or decision["next_action"].get("parameters", {}) != candidate["parameters"]):
            return None, "controller_binding_changed", None, None
        actions = [a for a in state["actions"] if a["request_id"] == child_id]
        if len(actions) != 1:
            return None, "original_child_unavailable", None, None
        action = actions[0]
        result = parent.get("result")
        parent_child = result.get("child") if type(result) is dict else None
        fields = ("id", "request_id", "command", "status", "artifact", "result_sha256", "failure")
        original_request = {"project_id": state["id"], "command": candidate["method_id"], "dimension": None,
                            "source_snapshot_sha256": record["source_snapshot_sha256"]}
        with project._connect(readonly=True) as con:
            row = con.execute("SELECT fingerprint, record FROM actions WHERE request_id=?", (child_id,)).fetchone()
        if (action["status"] != "completed" or action["command"] != candidate["method_id"]
                or row is None or json.loads(row["record"]) != action or row["fingerprint"] != action["request_sha256"]
                or action["request_sha256"] != fingerprint(original_request)
                or action["code_identity"] != record["project_code_identity"]
                or action["source_snapshot_sha256"] != record["source_snapshot_sha256"]
                or action["method_instance"]["evaluation_ref"] != candidate["evaluation_ref"]
                or action["method_instance"]["parameters"] != candidate["parameters"]
                or any(key not in action for key in fields) or action["failure"] is not None
                or action["project_id"] != state["id"] or action["run_id"] != state["run_id"]
                or action["artifact"] != "artifacts/" + action["id"] + ".json"
                or type(result) is not dict or set(result) != {"child", "recovered", "reused"}
                or type(result["recovered"]) is not bool or result["reused"] is not False
                or parent_child != {key: action[key] for key in fields}):
            return None, "child_binding_changed", None, None
        family, binding, _, _, metric_rows, *_ = reader._bundle(project, state, action["id"])
        if (family.module.TOOL_ID != candidate["method_id"] or fingerprint(family.module.COMPARISON) != record["protocol_sha256"]
                or binding["primary_action_id"] != action["id"]):
            return None, "protocol_binding_changed", None, None
        # Check the previously saved aggregate against the adapter's paired arithmetic;
        # this reads saved numbers only and performs no ranking or qrel scoring.
        result = reader._envelope(project, state, action, family)
        summary, _, _ = family.module._paired(list(metric_rows.values()))
        if canonical(result["paired_summary"]) != canonical(summary):
            return None, "saved_summary_changed", None, None
        metric = record["condition"]["metric"]
        value = result["paired_summary"]["splits"]["validation"]["paired_candidate_minus_baseline"][metric]["mean"]
        if type(value) not in (int, float) or not math.isfinite(value) or not -1 <= value <= 1:
            return None, "invalid_saved_metric", None, None
        return value, None, action["id"], action["result_sha256"]
    except ResearchError as exc:
        return None, "saved_evidence_" + exc.code.lower(), None, None
    except (KeyError, TypeError, ValueError, OSError, OverflowError, RecursionError):
        return None, "saved_evidence_unavailable_or_malformed", None, None


def feedback_context(project, state):
    records = state.get("hypothesis_registrations", [])
    if not records:
        return None
    require(type(records) is list and len(records) <= MAX_ITEMS, "EVIDENCE_CHANGED", "Invalid saved prediction collection.")
    items = []
    for record in records:
        try:
            _check_record(record)
        except (KeyError, TypeError, ValueError, RecursionError):
            raise ResearchError("EVIDENCE_CHANGED", "Saved prediction registration is malformed.") from None
        value, reason, action_id, result_sha = _outcome(project, state, record)
        outcome = "unknown" if reason else ("condition_met" if OPS[record["condition"]["operator"]](value, record["condition"]["threshold"]) else "condition_not_met")
        item = {"request_id": record["request_id"], "controller_request_id": record["controller_request_id"],
                      "registration_sha256": record["registration_sha256"], "candidate": copy.deepcopy(record["candidate"]),
                      "condition": copy.deepcopy(record["condition"]), "outcome": outcome, "value": value,
                      "unknown_reason": reason, "action_id": action_id, "result_sha256": result_sha}
        if "branches" in record:
            item["branches"] = copy.deepcopy(record["branches"])
        items.append(item)
    value = {"schema_version": "hypothesis-feedback-context-v1", "items": items,
             "scientific_validation": False, "test_notice": TEST_NOTICE}
    return validate_context(value)


def validate_context(value):
    code = "INVALID_SELECTION_CONTEXT"
    require(type(value) is dict and set(value) == {"schema_version", "items", "scientific_validation", "test_notice"}
            and value["schema_version"] == "hypothesis-feedback-context-v1" and value["scientific_validation"] is False
            and value["test_notice"] == TEST_NOTICE and type(value["items"]) is list and 1 <= len(value["items"]) <= MAX_ITEMS,
            code, "Invalid prediction feedback context.")
    ids = set()
    for item in value["items"]:
        fields = {"request_id", "controller_request_id", "registration_sha256", "candidate", "condition", "outcome", "value", "unknown_reason", "action_id", "result_sha256"}
        require(type(item) is dict and fields <= set(item) <= fields | {"branches"}
                and type(item["request_id"]) is str and 0 < len(item["request_id"]) <= 80 and item["request_id"] not in ids
                and type(item["controller_request_id"]) is str and 0 < len(item["controller_request_id"]) <= 80
                and type(item["registration_sha256"]) is str and re.fullmatch(r"[0-9a-f]{64}", item["registration_sha256"]) is not None
                and type(item["candidate"]) is dict and set(item["candidate"]) == {"id", "method_id", "parameters", "evaluation_ref"}
                and all(type(item["candidate"][key]) is str and 0 < len(item["candidate"][key]) <= 160 for key in ("id", "method_id"))
                and type(item["candidate"]["parameters"]) is dict
                and type(item["candidate"]["evaluation_ref"]) in (str, dict)
                and type(item["condition"]) is dict and set(item["condition"]) == {"split", "measure", "metric", "operator", "threshold"}
                and item["condition"]["split"] == "validation" and item["condition"]["measure"] == "candidate_minus_baseline"
                and type(item["condition"]["metric"]) is str and item["condition"]["metric"] in reader.METRICS
                and type(item["condition"]["operator"]) is str and item["condition"]["operator"] in OPS
                and type(item["condition"]["threshold"]) in (int, float) and -1 <= item["condition"]["threshold"] <= 1
                and math.isfinite(item["condition"]["threshold"]) and item["outcome"] in ("unknown", "condition_met", "condition_not_met"),
                code, "Invalid prediction feedback item.")
        if "branches" in item:
            try:
                _branches(item["branches"], item["candidate"]["method_id"])
            except ResearchError:
                raise ResearchError(code, "Invalid frozen prediction branches.") from None
        ids.add(item["request_id"])
        if item["outcome"] == "unknown":
            require(item["value"] is None and type(item["unknown_reason"]) is str and 0 < len(item["unknown_reason"]) <= 120
                    and item["action_id"] is None and item["result_sha256"] is None, code, "Unknown must retain its reason without a fabricated result.")
        else:
            n = item["value"]
            require(type(n) in (int, float) and -1 <= n <= 1 and math.isfinite(n)
                    and item["unknown_reason"] is None and type(item["action_id"]) is str
                    and type(item["result_sha256"]) is str and re.fullmatch(r"[0-9a-f]{64}", item["result_sha256"]) is not None
                    and (item["outcome"] == "condition_met") == OPS[item["condition"]["operator"]](n, item["condition"]["threshold"]),
                    code, "Known feedback must preserve its exact comparison and evidence identity.")
    return value
