"""Allowlisted synchronous P02 saved-OOF adapter; no fits, paths or transport."""

import copy
import hashlib
import json
import math
from pathlib import Path

from . import residual_diagnostics
from .contracts import ResearchError


TOOL_ID = "p02.saved-oof-residuals"
ADAPTER_VERSION = "1"
ENDPOINT = "p02.section-control-normalized-raw-red-proxy"
POLICIES = (
    "recorded_equal_batch", "recorded_equal_section",
    "positive_equal_batch", "positive_equal_section",
)
DIMENSIONS = ("chemistry", "topography")
MAX_SOURCE_BYTES = 25_000_000


def _require(condition, code, message):
    if not condition:
        raise ResearchError(code, message)


def _json_object(pairs):
    value = {}
    for key, item in pairs:
        _require(key not in value, "INVALID_SOURCE_JSON", "Duplicate source JSON key.")
        value[key] = item
    return value


def _reject_constant(value):
    raise ResearchError("INVALID_SOURCE_JSON", "Nonfinite source JSON number: " + value)


def _proxy_scope(payload):
    """Require the explicit P02 numerical-proxy scope, not an ALP claim."""
    try:
        gate = payload["iteration"]["endpoint_gate"]
        summary = payload["summary"]
        allowed = (
            payload["inputs"]["executor_id"] == "p02-interaction-ridge-v1"
            and gate["ALP_eligible"] is False
            and gate["biological_fit_eligible"] is False
            and gate["numerical_proxy_fit_eligible"] is True
            and summary["scientific_validation"] is False
            and type(summary["new_fits"]) is int and summary["new_fits"] == 0
        )
    except (KeyError, TypeError):
        raise ResearchError("UNSUPPORTED_SCOPE", "Explicit P02 raw-red proxy scope is required.") from None
    _require(allowed, "UNSUPPORTED_SCOPE", "Only the P02 raw-red numerical proxy is supported.")


def _validate_source(payload):
    try:
        residual_diagnostics.validate_source(payload)
    except ResearchError:
        raise
    except (KeyError, TypeError, ValueError, OverflowError, IndexError, RecursionError):
        raise ResearchError("EVIDENCE_CHANGED", "Malformed saved OOF source structure.") from None
    _proxy_scope(payload)


def load_source(raw: bytes) -> dict:
    """Parse and validate registered source bytes without touching any source path."""
    _require(type(raw) is bytes and 0 < len(raw) <= MAX_SOURCE_BYTES,
             "INVALID_SOURCE", "Source must be nonempty bytes within the size limit.")
    try:
        payload = json.loads(raw, object_pairs_hook=_json_object, parse_constant=_reject_constant)
    except ResearchError:
        raise
    except (ValueError, UnicodeError, RecursionError):
        raise ResearchError("INVALID_SOURCE_JSON", "Source is not a supported JSON document.") from None
    _validate_source(payload)
    return payload


def code_identity() -> str:
    """Identity of this adapter and its unchanged arithmetic implementation."""
    return hashlib.sha256(
        Path(__file__).read_bytes() + Path(residual_diagnostics.__file__).read_bytes()
    ).hexdigest()


def execute(payload, dimension) -> dict:
    """Compute one fixed grouping; the caller owns operation/result persistence."""
    _require(type(dimension) is str and dimension in DIMENSIONS,
             "INVALID_REQUEST", "Only chemistry or topography grouping is supported.")
    _validate_source(payload)
    try:
        diagnostic = residual_diagnostics.inspect_residuals(payload, dimension)
    except ResearchError:
        raise
    except (KeyError, TypeError, ValueError, OverflowError, IndexError, ZeroDivisionError, RecursionError):
        raise ResearchError("EVIDENCE_CHANGED", "Saved OOF arithmetic input is invalid.") from None

    evidence = {
        "source_snapshot_sha256": payload["snapshot_sha256"],
        "scope": copy.deepcopy(payload["scope"]),
    }
    observations, metrics = [], []
    for policy in POLICIES:
        methods = diagnostic["summary"]["policies"][policy]["methods"]
        candidate, baseline = methods["current_candidate"], methods["chemistry"]
        context = {
            "endpoint": ENDPOINT, "unit": "dimensionless_ratio",
            "sample_unit": "material_key", "policy": policy,
            "dimension": dimension, "n": candidate["n"],
            "candidate_id": payload["candidate"]["candidate_id"],
            "comparator": "chemistry", "evaluation": "frozen_within_policy_grouped_oof",
        }
        observations.append({
            "producer": TOOL_ID, "kind": "grouped_oof_residuals", **context,
            "values": {
                "current_candidate": copy.deepcopy(candidate),
                "chemistry": copy.deepcopy(baseline),
            },
            "evidence_refs": [copy.deepcopy(evidence)],
            "interpretation_status": "numerical_only_not_scientifically_approved",
        })
        for name, value in (
            ("mae", candidate["mae"]),
            ("comparator_mae", baseline["mae"]),
            ("delta_mae_vs_chemistry", candidate["delta_mae_vs_chemistry"]),
        ):
            metrics.append({"name": name, "value": value, **context})
    return {
        "schema_version": "p02-saved-oof-tool-result-v1",
        "tool_id": TOOL_ID, "adapter_version": ADAPTER_VERSION,
        "status": "completed", "observations": observations,
        "evidence_refs": [evidence], "artifacts": [], "metrics": metrics,
        "result": diagnostic, "failure": None,
        "new_fits": 0, "scientific_validation": False,
    }


def next_decision(result: dict) -> dict:
    """Propose an unexecuted next check from saved feedback; never promote a claim."""
    try:
        _require(result["schema_version"] == "p02-saved-oof-tool-result-v1"
                 and result["tool_id"] == TOOL_ID and result["adapter_version"] == ADAPTER_VERSION
                 and result["status"] == "completed" and result["scientific_validation"] is False
                 and type(result["new_fits"]) is int and result["new_fits"] == 0,
                 "INVALID_RESULT", "A completed numerical-proxy adapter result is required.")
        diagnostic = result["result"]
        dimension = diagnostic["dimension"]
        policies = diagnostic["summary"]["policies"]
        source_snapshot = diagnostic["source_snapshot_sha256"]
        evidence_refs = result["evidence_refs"]
        _require(diagnostic["schema_version"] == "p02-residual-diagnostics-v1"
                 and dimension in DIMENSIONS and set(policies) == set(POLICIES)
                 and type(evidence_refs) is list and len(evidence_refs) == 1
                 and evidence_refs[0]["source_snapshot_sha256"] == source_snapshot,
                 "INVALID_RESULT", "Expected the complete four-policy residual result.")
        feedback = []
        for policy in POLICIES:
            methods = policies[policy]["methods"]
            candidate, baseline = methods["current_candidate"], methods["chemistry"]
            counts = {name: candidate[name] for name in (
                "worse_groups", "better_groups", "tied_groups", "group_count")}
            _require(all(type(value) is int and value >= 0 for value in counts.values())
                     and counts["group_count"] > 0
                     and sum(counts[name] for name in ("worse_groups", "better_groups", "tied_groups"))
                     == counts["group_count"],
                     "INVALID_RESULT", "Residual group counts are inconsistent.")
            _require(all(type(value) in (int, float) and math.isfinite(value) for value in (
                candidate["mae"], baseline["mae"], candidate["delta_mae_vs_chemistry"])),
                "INVALID_RESULT", "Residual comparisons must be finite.")
            feedback.append({
                "policy": policy, **counts,
                "delta_mae_vs_chemistry": candidate["delta_mae_vs_chemistry"],
                "majority_worse": counts["worse_groups"] * 2 > counts["group_count"],
            })
    except ResearchError:
        raise
    except (KeyError, TypeError, ValueError, IndexError):
        raise ResearchError("INVALID_RESULT", "Malformed saved OOF adapter result.") from None

    negative_policies = [item["policy"] for item in feedback if item["majority_worse"]]
    if negative_policies:
        next_action = {
            "method_id": "p02.source-mapping-check", "parameters": {},
            "execution_status": "not_executed", "kind": "evidence_task",
            "required_evidence": ["author object/channel/export-column/batch mapping"],
        }
        status = "waiting"
        reason = (
            "The candidate is worse than chemistry in a majority of observed groups "
            "under the listed processing policies. Preserve the negative feedback and "
            "request source/target mapping before deciding further numerical work. "
            "This does not establish measurement error or an ALP effect."
        )
    else:
        next_action = {
            "method_id": TOOL_ID,
            "parameters": {"dimension": "topography" if dimension == "chemistry" else "chemistry"},
            "execution_status": "not_executed", "kind": "conditional_proposal",
            "conditions": ["matching source remains eligible", "no saved observation for that grouping"],
        }
        status = "active"
        reason = (
            "No processing policy has a majority of observed groups worse than chemistry. "
            "Propose the other grouping only if eligible and not already observed; "
            "this feedback does not establish improvement or biological validity."
        )
    return {
        "policy_ref": {"id": "p02.residual_first", "version": ADAPTER_VERSION},
        "project_status": status, "next_action": next_action, "reason": reason,
        "feedback": feedback, "negative_policies": negative_policies,
        "source_snapshot_sha256": source_snapshot,
        "evidence_refs": copy.deepcopy(evidence_refs),
        "scientific_validation": False,
    }
