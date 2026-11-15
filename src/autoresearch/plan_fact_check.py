"""Check a submitter-mapped plan span against its frozen comparison facts."""

import copy
from decimal import Decimal, InvalidOperation, localcontext, ROUND_HALF_UP
import math
import re

from .contracts import ResearchError, canonical, fingerprint, identifier
from . import research_plan_proposal as plan_protocol

FIELDS = {"plan.question", "plan.basis", "plan.steps", "plan.expected_feedback", "reason", "expected_improvement"}
METRICS = {"baseline_mae", "candidate_mae", "mae_change", "relative_improvement",
           "baseline_negative_predictions", "candidate_negative_predictions"}
ORDERS = {"candidate_lower", "baseline_lower", "equal"}
QUALITY_OUTCOMES = {"condition_met", "condition_not_met", "unknown"}


def _require(condition, message):
    if not condition:
        raise ResearchError("INVALID_PLAN_FACT_CHECK", message)


def _claim(value, arguments):
    _require(type(value) is dict and set(value) == {"field", "start", "end", "quote", "comparison", "assertion"},
             "Use the exact span, comparison and assertion fields.")
    field = value["field"]
    _require(type(field) is str and field in FIELDS, "Select one original plan response text field.")
    text = arguments["plan"][field[5:]] if field.startswith("plan.") else arguments[field]
    start, end, quote = value["start"], value["end"], value["quote"]
    _require(type(start) is int and type(end) is int and 0 <= start < end <= len(text)
             and type(quote) is str and text[start:end] == quote,
             "The quote must match the exact original Unicode-codepoint span, end excluded.")
    comparison = value["comparison"]
    _require(type(comparison) is dict and set(comparison) == {"check", "baseline_action_id", "candidate_action_id"},
             "Name the exact check and both saved action identities.")
    for key in comparison:
        identifier(comparison[key], key)
    assertion = value["assertion"]
    _require(type(assertion) is dict and type(assertion.get("kind")) is str
             and assertion["kind"] in {"mae_order", "metric"}, "Select a supported assertion kind.")
    if assertion["kind"] == "mae_order":
        _require(set(assertion) == {"kind", "value"} and type(assertion["value"]) is str
                 and assertion["value"] in ORDERS, "Declare one exact saved-MAE order.")
    else:
        _require(set(assertion) == {"kind", "metric", "value"} and type(assertion["metric"]) is str
                 and assertion["metric"] in METRICS, "Select a supported saved metric.")
        number = assertion["value"]
        _require(type(number) is str and len(number) <= 64
                 and re.fullmatch(r"-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?", number) is not None,
                 "Declare the displayed finite number as numeric text, retaining its rounding precision.")
        try:
            decimal = Decimal(number)
        except InvalidOperation:
            raise ResearchError("INVALID_PLAN_FACT_CHECK", "A finite decimal assertion is required.") from None
        _require(decimal.is_finite() and -324 <= decimal.as_tuple().exponent <= 308
                 and decimal.adjusted() <= 308, "The displayed decimal exceeds finite metric precision.")
        if assertion["metric"].endswith("negative_predictions"):
            _require(decimal >= 0 and decimal == decimal.to_integral_value(), "Prediction counts must be nonnegative integers.")
    return copy.deepcopy(value)


def _finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def _action_ref(comparison, key):
    reference = comparison.get(key)
    return reference.get("action_id") if type(reference) is dict else None


def _evaluate(comparison, assertion):
    if comparison is None:
        return "undetermined", None, "comparison_not_supplied"
    if comparison.get("status") != "comparable":
        return "undetermined", None, "comparison_not_comparable"
    metrics = comparison.get("metrics")
    if type(metrics) is not dict:
        return "undetermined", None, "metric_unavailable"
    if assertion["kind"] == "mae_order":
        left, right = metrics.get("baseline_mae"), metrics.get("candidate_mae")
        if not _finite(left) or not _finite(right):
            return "undetermined", None, "metric_unavailable"
        actual = "equal" if left == right else "baseline_lower" if left < right else "candidate_lower"
        matches = actual == assertion["value"]
    else:
        actual = metrics.get(assertion["metric"])
        if not _finite(actual):
            return "undetermined", None, "metric_unavailable"
        declared = Decimal(assertion["value"])
        if assertion["metric"].endswith("negative_predictions"):
            if type(actual) is not int or actual < 0:
                return "undetermined", None, "metric_unavailable"
            matches = Decimal(actual) == declared
        else:
            # The last displayed decimal place is a declaration of rounding,
            # not permission to replace an unknown or nonfinite source metric.
            with localcontext() as precision:
                precision.prec = 700
                quantum = Decimal(1).scaleb(declared.as_tuple().exponent)
                matches = Decimal(str(actual)).quantize(quantum, rounding=ROUND_HALF_UP) == declared
    return ("supported", actual, "matches_saved_fact") if matches else ("contradicted", actual, "contradicts_saved_fact")


def _quality_claim(value, arguments):
    _require(type(value) is dict and set(value) == {"field", "start", "end", "quote", "quality", "assertion"},
             "Use the exact span, quality registration and assertion fields.")
    field = value["field"]
    _require(type(field) is str and field in FIELDS, "Select one original plan response text field.")
    text = arguments["plan"][field[5:]] if field.startswith("plan.") else arguments[field]
    start, end, quote = value["start"], value["end"], value["quote"]
    _require(type(start) is int and type(end) is int and 0 <= start < end <= len(text)
             and type(quote) is str and text[start:end] == quote,
             "The quote must match the exact original Unicode-codepoint span, end excluded.")
    ref, assertion = value["quality"], value["assertion"]
    _require(type(ref) is dict and set(ref) == {"registration_request_id", "registration_sha256"},
             "Select one original quality registration and SHA.")
    identifier(ref["registration_request_id"], "registration_request_id")
    _require(type(ref["registration_sha256"]) is str and re.fullmatch(r"[0-9a-f]{64}", ref["registration_sha256"]) is not None,
             "Use the original registration SHA.")
    _require(type(assertion) is dict and type(assertion.get("kind")) is str,
             "Select a bounded quality assertion.")
    kind = assertion["kind"]
    if kind == "overall_outcome":
        _require(set(assertion) == {"kind", "value"} and type(assertion["value"]) is str
                 and assertion["value"] in QUALITY_OUTCOMES, "Use an exact saved overall outcome.")
    elif kind == "condition_outcome":
        _require(set(assertion) == {"kind", "index", "value"} and type(assertion["index"]) is int
                 and 0 <= assertion["index"] < 32 and type(assertion["value"]) is str
                 and assertion["value"] in QUALITY_OUTCOMES, "Use an exact indexed condition outcome.")
    elif kind == "condition_value":
        _require(set(assertion) == {"kind", "index", "field", "value"} and type(assertion["index"]) is int
                 and 0 <= assertion["index"] < 32 and type(assertion["field"]) is str
                 and assertion["field"] in ("actual", "expected")
                 and ((type(assertion["value"]) is int and 0 <= assertion["value"] <= 50000)
                      or (type(assertion["value"]) is str and assertion["value"] in ("empty", "nonempty"))),
                 "Use an indexed actual or expected integer or flags state.")
    else:
        raise ResearchError("INVALID_PLAN_FACT_CHECK", "Select a bounded quality assertion.")
    return copy.deepcopy(value)


def check_quality_plan_fact(record, claim):
    """Compare a selected span with frozen material; caller verifies the Host originals."""
    _require(record.get("purpose") == "plan", "Only a saved research-plan response can be checked.")
    if "arguments" not in record or "response_sha256" not in record or "proposal" not in record:
        raise ResearchError("PLAN_RESPONSE_NOT_READY", "Receive the original parsed plan response first.")
    context = plan_protocol._context(record["context"])
    if type(record.get("prompt")) is not dict or canonical(record["prompt"]) != canonical(plan_protocol.build_prompt(context)):
        raise ResearchError("EVIDENCE_CHANGED", "The saved prompt differs from the current compilation of its frozen context.")
    arguments = plan_protocol._arguments(record["arguments"])
    proposal = plan_protocol.validate_proposal(context, record["proposal"])
    _require(all(proposal[key] == arguments[key] for key in plan_protocol.ARGUMENT_FIELDS),
             "The saved proposal differs from its original parsed response.")
    value = _quality_claim(claim, arguments)
    ref, assertion = value["quality"], value["assertion"]
    matches = [m for m in context.get("supplied_materials", [])
               if m.get("kind") == "tabular_quality_feedback"
               and m.get("registration_request_id") == ref["registration_request_id"]
               and m.get("registration_sha256") == ref["registration_sha256"]]
    _require(len(matches) <= 1, "The frozen quality registration is ambiguous.")
    material = matches[0] if matches else None
    actual, reason = None, "quality_material_not_supplied"
    overall, item, condition, unknown_reason = None, None, None, None
    if material is not None:
        feedback = material["feedback"]
        overall = feedback["outcome"]
        unknown_reason = feedback["unknown_reason"]
        reason = "evaluation_not_supplied"
        if assertion["kind"] == "overall_outcome":
            actual = overall
        else:
            index = assertion["index"]
            conditions = material["conditions"]["conditions"]
            _require(index < len(conditions), "Condition index is outside the frozen registration.")
            condition = conditions[index]
            if assertion["kind"] == "condition_value":
                is_flags = condition["field"] == "flags"
                _require((type(assertion["value"]) is str) == is_flags,
                         "The assertion value type must match the saved condition.")
            if feedback["evaluation"] is not None:
                item = feedback["evaluation"]["items"][index]
                if assertion["kind"] == "condition_outcome":
                    actual = item["outcome"]
                else:
                    actual = item[assertion["field"]]
                    reason = "condition_value_unknown"
    status = "undetermined"
    if actual is not None:
        if assertion["kind"] in ("overall_outcome", "condition_outcome") and actual == "unknown" and assertion["value"] != "unknown":
            reason = "condition_outcome_unknown"
        else:
            status = "supported" if actual == assertion["value"] else "contradicted"
            reason = "matches_saved_fact" if status == "supported" else "contradicts_saved_fact"
    selection = context["selection_context"]
    return {"schema_version": "plan-quality-fact-check-v1", "project_id": selection["project_id"],
            "host_request_id": record["request_id"], "context_sha256": fingerprint(context),
            "selection_context_sha256": selection["context_sha256"], "source_state_version": selection["state_version"],
            "snapshot_ref": selection["snapshot_ref"], "source_snapshot_sha256": selection["source_snapshot_sha256"],
            "response_sha256": record["response_sha256"],
            "material_sha256": fingerprint(material) if material is not None else None,
            "feedback_sha256": fingerprint(material["feedback"]) if material is not None else None,
            "quote_span": {key: value[key] for key in ("field", "start", "end", "quote")},
            "quality": ref, "assertion": assertion, "status": status, "actual": actual,
            "overall_outcome": overall, "feedback_unknown_reason": unknown_reason,
            "condition": copy.deepcopy(condition), "condition_result": copy.deepcopy(item),
            "reason_code": reason, "semantic_mapping": "submitter_declared", "coverage": "selected_span_only",
            "binding_scope": "frozen_host_context_only_not_live_source_reverification",
            "notice": "Only the submitter-declared assertion is compared with frozen material. "
                      "A recorded unknown does not establish that execution did not occur or that evidence is complete. "
                      "This comparison does not prove that a model saw or understood the material.",
            "scientific_validation": False}


def check_plan_fact(record, claim):
    """The caller supplies a record whose original Host bytes were verified."""
    _require(record.get("purpose") == "plan", "Only a saved research-plan response can be checked.")
    if "arguments" not in record or "response_sha256" not in record:
        raise ResearchError("PLAN_RESPONSE_NOT_READY", "Receive an original parsed plan response before checking a span.")
    context = plan_protocol._context(record["context"])
    arguments = plan_protocol._arguments(record["arguments"])
    if "proposal" in record:
        proposal = plan_protocol.validate_proposal(context, record["proposal"])
        if not all(proposal[key] == arguments[key] for key in plan_protocol.ARGUMENT_FIELDS):
            raise ResearchError("EVIDENCE_CHANGED", "The saved proposal differs from its original parsed response.")
    value = _claim(claim, arguments)
    ref = value["comparison"]
    comparisons = [item for item in context.get("saved_comparisons", [])
                   if item.get("check") == ref["check"]
                   and _action_ref(item, "baseline_ref") == ref["baseline_action_id"]
                   and _action_ref(item, "candidate_ref") == ref["candidate_action_id"]]
    _require(len(comparisons) <= 1, "The frozen comparison identity is ambiguous.")
    comparison = comparisons[0] if comparisons else None
    status, actual, reason = _evaluate(comparison, value["assertion"])
    comparison_status = comparison.get("status") if comparison is not None else None
    metrics = comparison.get("metrics") if comparison_status == "comparable" else None
    selection = context["selection_context"]
    return {"schema_version": "plan-fact-check-v1", "project_id": selection["project_id"],
            "host_request_id": record["request_id"], "context_sha256": selection["context_sha256"],
            "source_state_version": selection["state_version"], "snapshot_ref": selection["snapshot_ref"],
            "response_sha256": record["response_sha256"],
            "quote_span": {key: value[key] for key in ("field", "start", "end", "quote")},
            "comparison": ref, "assertion": value["assertion"], "status": status, "actual": actual,
            "comparison_status": comparison_status, "saved_metrics": copy.deepcopy(metrics),
            "reason_code": reason, "semantic_mapping": "submitter_declared", "coverage": "selected_span_only",
            "scientific_validation": False}
