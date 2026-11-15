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
from . import staged_relevance_adapter as staged
from .contracts import ResearchError, canonical, fingerprint, identifier
from .research_project import require

MAX_ITEMS = 16
OPS = {"gt": operator.gt, "gte": operator.ge, "lt": operator.lt,
       "lte": operator.le, "eq": operator.eq}
TEST_NOTICE = "Existing retrieval adapters have already computed test metrics; they are not blind."
STAGED_NOTICE = ("This source contains only dev and validation; any final evaluation requires separate registration. "
                 "Feedback does not read final data and does not establish prior non-exposure, blindness or scientific validation.")


def _family(method_id):
    if method_id in (staged.TOOL_ID, staged.AUDIT_TOOL_ID):
        # Use only the fixed adapter identity here; its saved-result reader is separate.
        class StagedFamily:
            module = staged
        return StagedFamily()
    return reader._family(method_id)


def _metric_condition(value):
    require(type(value) is dict and set(value) == {"metric", "operator", "threshold"},
            "INVALID_REQUEST", "Use exactly a metric, comparison operator and threshold.")
    threshold = value["threshold"]
    require(type(value["metric"]) is str and value["metric"] in reader.METRICS
            and type(value["operator"]) is str and value["operator"] in OPS
            and type(threshold) in (int, float) and -1 <= threshold <= 1 and math.isfinite(threshold),
            "INVALID_REQUEST", "Use a saved validation metric, comparison operator and finite delta threshold in [-1, 1].")
    return {"split": "validation", "measure": "candidate_minus_baseline", "metric": value["metric"],
            "operator": value["operator"], "threshold": threshold}


def _condition(hypothesis):
    require(type(hypothesis) is dict, "INVALID_REQUEST", "Use the exact preregistration fields.")
    if "conditions" in hypothesis:
        fields = {"candidate_id", "controller_request_id", "conditions"}
        require(fields <= set(hypothesis) <= fields | {"branches", "leave_one_out"}
                and type(hypothesis["conditions"]) is list and len(hypothesis["conditions"]) == 2,
                "INVALID_REQUEST", "Use exactly two preregistered metric conditions, without scalar fields.")
        identifier(hypothesis["candidate_id"], "candidate_id")
        identifier(hypothesis["controller_request_id"], "controller_request_id")
        conditions = [_metric_condition(value) for value in hypothesis["conditions"]]
        require(conditions[0]["metric"] != conditions[1]["metric"],
                "INVALID_REQUEST", "The two conditions must use different validation metrics.")
        if "leave_one_out" in hypothesis:
            loo = _metric_condition(hypothesis["leave_one_out"])
            require(loo["metric"] in {item["metric"] for item in conditions}
                    and loo["operator"] in ("gt", "gte", "lt", "lte"),
                    "INVALID_REQUEST", "Leave-one-out must use one registered metric and an inequality.")
            loo["measure"] = "leave_one_out_mean"
            return {"all": conditions, "leave_one_out": loo}
        return {"all": conditions}
    fields = {"candidate_id", "controller_request_id", "metric", "operator", "threshold"}
    require(fields <= set(hypothesis) <= fields | {"branches"},
            "INVALID_REQUEST", "Use the exact preregistration fields; test metrics are not supported.")
    identifier(hypothesis["candidate_id"], "candidate_id")
    identifier(hypothesis["controller_request_id"], "controller_request_id")
    return _metric_condition({key: hypothesis[key] for key in ("metric", "operator", "threshold")})


def _branches(value, primary_method_id):
    """Permit only wait or the same family's existing saved-audit method."""
    family = _family(primary_method_id)
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
        quality_records = stored.get("tabular_quality_registrations", [])
        require(type(quality_records) is list and all(type(item) is dict and type(item.get("controller_request_id")) is str
                for item in quality_records), "EVIDENCE_CHANGED", "The quality registration collection is malformed.")
        require(not any(item["controller_request_id"] in (request_id, target) for item in quality_records),
                "IDEMPOTENCY_CONFLICT", "A request ID collides with a future tabular quality controller ID.")
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
        family = _family(candidate["method_id"])
        require(candidate["method_id"] == family.module.TOOL_ID and not candidate["parameters"]
                and candidate["method_id"] == stored["registration"]["method_id"],
                "CONDITION_NOT_SATISFIED", "Only the existing primary citation or relevance pair can be predicted.")
        if "all" in condition:
            require(candidate["method_id"] == staged.TOOL_ID, "CONDITION_NOT_SATISFIED",
                    "Two-condition feedback requires the staged development primary.")
        branches = _branches(hypothesis["branches"], candidate["method_id"]) if "branches" in hypothesis else None
        version = ("hypothesis-registration-v3" if "leave_one_out" in condition else
                   "hypothesis-registration-v2" if "all" in condition else "hypothesis-registration-v1")
        record = {"schema_version": version, "request_id": request_id,
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
    require(type(record) is dict and record.get("schema_version") in ("hypothesis-registration-v1", "hypothesis-registration-v2", "hypothesis-registration-v3")
            and record.get("scientific_validation") is False
            and record.get("registration_sha256") == fingerprint({k: v for k, v in record.items() if k != "registration_sha256"})
            and record.get("request_sha256") == fingerprint(record.get("request"))
            and (canonical(record.get("condition")) == canonical(_condition(record["request"]["hypothesis"]))
                 if record.get("schema_version") in ("hypothesis-registration-v2", "hypothesis-registration-v3")
                 else record.get("condition") == _condition(record["request"]["hypothesis"]))
            and (record.get("schema_version") == "hypothesis-registration-v1") == ("all" not in record.get("condition", {}))
            and (record.get("schema_version") == "hypothesis-registration-v3") == ("leave_one_out" in record.get("condition", {}))
            and (record.get("schema_version") == "hypothesis-registration-v1" or record.get("candidate", {}).get("method_id") == staged.TOOL_ID)
            and (record.get("schema_version") != "hypothesis-registration-v3"
                 or (type(record.get("scope_sha256")) is str and re.fullmatch(r"[0-9a-f]{64}", record["scope_sha256"]) is not None))
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
        condition = record["condition"]
        joint = "all" in condition
        robust = "leave_one_out" in condition
        if candidate["method_id"] == staged.TOOL_ID:
            if fingerprint(staged.COMPARISON) != record["protocol_sha256"]:
                return None, "protocol_binding_changed", None, None
            if robust:
                from .staged_feedback_reader import read_validation_deltas_and_loo
                value = read_validation_deltas_and_loo(project, state, action,
                    [item["metric"] for item in condition["all"]], condition["leave_one_out"]["metric"])
                if value is None:
                    return None, "insufficient_validation_queries", None, None
            elif joint:
                from .staged_feedback_reader import read_validation_deltas
                value = read_validation_deltas(project, state, action, [item["metric"] for item in condition["all"]])
            else:
                from .staged_feedback_reader import read_validation_delta
                value = read_validation_delta(project, state, action, condition["metric"])
        else:
            if joint:
                return None, "unsupported_joint_family", None, None
            metric = condition["metric"]
            family, binding, _, _, metric_rows, *_ = reader._bundle(project, state, action["id"])
            if (family.module.TOOL_ID != candidate["method_id"] or fingerprint(family.module.COMPARISON) != record["protocol_sha256"]
                    or binding["primary_action_id"] != action["id"]):
                return None, "protocol_binding_changed", None, None
            result = reader._envelope(project, state, action, family)
            summary, _, _ = family.module._paired(list(metric_rows.values()))
            if canonical(result["paired_summary"]) != canonical(summary):
                return None, "saved_summary_changed", None, None
            value = result["paired_summary"]["splits"]["validation"]["paired_candidate_minus_baseline"][metric]["mean"]
        if robust:
            if not _valid_loo_value(value, condition):
                return None, "invalid_saved_metric", None, None
            values = value["means"]
        else:
            values = value if joint and type(value) is list and len(value) == 2 else [value] if not joint else []
        if len(values) != (2 if joint else 1) or any(type(v) not in (int, float) or not -1 <= v <= 1 or not math.isfinite(v) for v in values):
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
        condition = record["condition"]
        if reason:
            matched = None
        elif "leave_one_out" in condition:
            matched = _loo_matches(condition, value)
        elif "all" in condition:
            matched = all(OPS[item["operator"]](v, item["threshold"]) for item, v in zip(condition["all"], value))
        else:
            matched = OPS[condition["operator"]](value, condition["threshold"])
        outcome = "unknown" if reason else ("condition_met" if matched else "condition_not_met")
        item = {"request_id": record["request_id"], "controller_request_id": record["controller_request_id"],
                      "registration_sha256": record["registration_sha256"], "candidate": copy.deepcopy(record["candidate"]),
                      "condition": copy.deepcopy(record["condition"]), "outcome": outcome, "value": value,
                      "unknown_reason": reason, "action_id": action_id, "result_sha256": result_sha}
        if "branches" in record:
            item["branches"] = copy.deepcopy(record["branches"])
        items.append(item)
    staged_items = [item["candidate"]["method_id"] == staged.TOOL_ID for item in items]
    require(all(staged_items) or not any(staged_items), "EVIDENCE_CHANGED", "Feedback families cannot be mixed.")
    version = ("hypothesis-feedback-context-v3" if any("leave_one_out" in item["condition"] for item in items)
               else "hypothesis-feedback-context-v2" if any("all" in item["condition"] for item in items)
               else "hypothesis-feedback-context-v1")
    value = {"schema_version": version, "items": items,
             "scientific_validation": False, "test_notice": STAGED_NOTICE if all(staged_items) else TEST_NOTICE}
    return validate_context(value)


def _valid_normalized_condition(value):
    """Require the exact normalized scalar representation, including numeric types."""
    try:
        if type(value) is not dict or set(value) != {"split", "measure", "metric", "operator", "threshold"}:
            return False
        normalized = _metric_condition({key: value[key] for key in ("metric", "operator", "threshold")})
        return canonical(value) == canonical(normalized)
    except (ResearchError, KeyError, TypeError, ValueError, OverflowError):
        return False


def _valid_loo_condition(value):
    try:
        if type(value) is not dict or set(value) != {"split", "measure", "metric", "operator", "threshold"}:
            return False
        normalized = _metric_condition({key: value[key] for key in ("metric", "operator", "threshold")})
        normalized["measure"] = "leave_one_out_mean"
        return value["operator"] in ("gt", "gte", "lt", "lte") and canonical(value) == canonical(normalized)
    except (ResearchError, KeyError, TypeError, ValueError, OverflowError):
        return False


def _valid_loo_value(value, condition):
    try:
        if type(value) is not dict or set(value) != {"means", "leave_one_out"}:
            return False
        means, loo = value["means"], value["leave_one_out"]
        if (type(means) is not list or len(means) != 2
                or any(type(x) not in (int, float) or not -1 <= x <= 1 or not math.isfinite(x) for x in means)
                or type(loo) is not dict or set(loo) != {"minimum", "maximum", "queries"}
                or type(loo["queries"]) is not int or not 2 <= loo["queries"] <= staged.LIMITS["max_queries"]
                or any(type(loo[k]) not in (int, float) or not -1 <= loo[k] <= 1 or not math.isfinite(loo[k])
                       for k in ("minimum", "maximum")) or loo["minimum"] > loo["maximum"]):
            return False
        index = next(i for i, part in enumerate(condition["all"]) if part["metric"] == condition["leave_one_out"]["metric"])
        # This tolerance only checks independently rounded aggregate consistency;
        # the registered predicate below always compares the extrema strictly.
        return loo["minimum"] - 1e-12 <= means[index] <= loo["maximum"] + 1e-12
    except (KeyError, TypeError, ValueError, OverflowError, StopIteration):
        return False


def _loo_matches(condition, value):
    if not all(OPS[part["operator"]](v, part["threshold"]) for part, v in zip(condition["all"], value["means"])):
        return False
    condition_loo = condition["leave_one_out"]
    bound = "minimum" if condition_loo["operator"] in ("gt", "gte") else "maximum"
    return OPS[condition_loo["operator"]](value["leave_one_out"][bound], condition_loo["threshold"])


def validate_context(value):
    code = "INVALID_SELECTION_CONTEXT"
    require(type(value) is dict and set(value) == {"schema_version", "items", "scientific_validation", "test_notice"}
            and value["schema_version"] in ("hypothesis-feedback-context-v1", "hypothesis-feedback-context-v2", "hypothesis-feedback-context-v3")
            and value["scientific_validation"] is False
            and value["test_notice"] in (TEST_NOTICE, STAGED_NOTICE) and type(value["items"]) is list and 1 <= len(value["items"]) <= MAX_ITEMS,
            code, "Invalid prediction feedback context.")
    ids, joint_count, robust_count = set(), 0, 0
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
                and type(item["condition"]) is dict
                and item["outcome"] in ("unknown", "condition_met", "condition_not_met"),
                code, "Invalid prediction feedback item.")
        condition = item["condition"]
        joint = set(condition) in ({"all"}, {"all", "leave_one_out"})
        robust = set(condition) == {"all", "leave_one_out"}
        if joint:
            require(value["schema_version"] in ("hypothesis-feedback-context-v2", "hypothesis-feedback-context-v3")
                    and item["candidate"]["method_id"] == staged.TOOL_ID
                    and type(condition["all"]) is list and len(condition["all"]) == 2
                    and all(_valid_normalized_condition(part) for part in condition["all"])
                    and condition["all"][0]["metric"] != condition["all"][1]["metric"],
                    code, "Invalid two-metric staged prediction condition.")
            joint_count += 1
            if robust:
                require(value["schema_version"] == "hypothesis-feedback-context-v3"
                        and _valid_loo_condition(condition["leave_one_out"])
                        and condition["leave_one_out"]["metric"] in {part["metric"] for part in condition["all"]},
                        code, "Invalid leave-one-out prediction condition.")
                robust_count += 1
        else:
            require(_valid_normalized_condition(condition), code, "Invalid scalar prediction condition.")
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
            if robust:
                require(_valid_loo_value(n, condition), code, "Invalid leave-one-out feedback values.")
                values = n["means"]
            else:
                values = n if joint and type(n) is list and len(n) == 2 else [n] if not joint else []
            require(len(values) == (2 if joint else 1)
                    and all(type(v) in (int, float) and -1 <= v <= 1 and math.isfinite(v) for v in values)
                    and item["unknown_reason"] is None and type(item["action_id"]) is str
                    and type(item["result_sha256"]) is str and re.fullmatch(r"[0-9a-f]{64}", item["result_sha256"]) is not None,
                    code, "Known feedback must preserve its exact values and evidence identity.")
            matched = (_loo_matches(condition, n) if robust
                       else all(OPS[part["operator"]](v, part["threshold"]) for part, v in zip(condition["all"], values))
                       if joint else OPS[condition["operator"]](n, condition["threshold"]))
            require((item["outcome"] == "condition_met") == matched, code, "Known feedback must preserve its exact comparison.")
    staged_items = [item["candidate"]["method_id"] == staged.TOOL_ID for item in value["items"]]
    require((all(staged_items) and value["test_notice"] == STAGED_NOTICE)
            or (not any(staged_items) and value["test_notice"] == TEST_NOTICE),
            code, "Prediction notice must match its unmixed retrieval family.")
    expected_version = ("hypothesis-feedback-context-v3" if robust_count else
                        "hypothesis-feedback-context-v2" if joint_count else "hypothesis-feedback-context-v1")
    require(value["schema_version"] == expected_version, code, "Context version must match its registered conditions.")
    return value
