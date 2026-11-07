"""Descriptive pairwise Pearson associations over unchanged captured CSV records."""

import copy
import hashlib
import math
from pathlib import Path

from . import grouped_quality_adapter as grouped, tabular_quality_adapter as tabular
from .contracts import ResearchError, fingerprint

TOOL_ID = "data.numeric-association"
ADAPTER_VERSION = "1"


def code_identity() -> str:
    return hashlib.sha256(Path(__file__).read_bytes() + tabular.code_identity().encode("ascii")
                          + grouped.code_identity().encode("ascii")).hexdigest()


def _finite(token, missing):
    if token in missing:
        return None
    try:
        value = float(token)
        return value if math.isfinite(value) else None
    except (ValueError, OverflowError):
        return None


def _pearson(pairs):
    if len(pairs) < 3:
        return None, "insufficient_pairs"
    xs, ys = zip(*pairs)
    constant_x = all(value == xs[0] for value in xs)
    constant_y = all(value == ys[0] for value in ys)
    if constant_x or constant_y:
        return None, "constant_both" if constant_x and constant_y else "constant_predictor" if constant_x else "constant_target"
    # Scale before centering to avoid overflow for finite inputs of large magnitude.
    scale_x, scale_y = max(map(abs, xs)), max(map(abs, ys))
    xs, ys = [value / scale_x for value in xs], [value / scale_y for value in ys]
    mean_x, mean_y = math.fsum(xs) / len(xs), math.fsum(ys) / len(ys)
    dx, dy = [value - mean_x for value in xs], [value - mean_y for value in ys]
    denominator = math.sqrt(math.fsum(value * value for value in dx)) * math.sqrt(math.fsum(value * value for value in dy))
    value = math.fsum(x * y for x, y in zip(dx, dy)) / denominator
    return max(-1.0, min(1.0, value)), None


def _associations(records, positions, spec):
    missing = set(spec["missing_tokens"])
    target = positions[spec["target_column"]]
    associations = []
    for name in spec["numeric_columns"]:
        if name == spec["target_column"]:
            continue
        pairs = []
        for row, _ in records:
            predictor, outcome = _finite(row[positions[name]], missing), _finite(row[target], missing)
            if predictor is not None and outcome is not None:
                pairs.append((predictor, outcome))
        value, reason = _pearson(pairs)
        associations.append({"predictor": name, "n": len(pairs), "excluded": len(records) - len(pairs),
                             "pearson_r": value, "reason": reason})
    return associations


def _group_results(records, positions, spec):
    groups, incomplete = {}, []
    if not spec["group_columns"]:
        return [], incomplete
    missing = set(spec["missing_tokens"])
    for logical_record, record in enumerate(records, 1):
        row, physical_line = record
        key = tuple(row[positions[name]] for name in spec["group_columns"])
        if any(token in missing for token in key):
            incomplete.append(record)
            continue
        if key not in groups:
            groups[key] = {"group_id": "group-" + fingerprint(list(key)), "records": [],
                           "first_coordinate": {"logical_record": logical_record, "physical_line_end": physical_line}}
        groups[key]["records"].append(record)
    result = []
    for group in groups.values():
        selected = group.pop("records")
        result.append({**group, "rows": len(selected), "associations": _associations(selected, positions, spec)})
    return result, incomplete


def execute(payload, parameters) -> dict:
    """ResearchProject verifies the saved quality predecessor before dispatch."""
    predecessor = grouped._parameters(parameters)
    spec, _, (header, records, physical_end) = tabular._checked(payload)
    if spec["target_column"] is None or len(spec["numeric_columns"]) < 2:
        raise ResearchError("UNSUPPORTED_SCOPE", "Declare a numeric target and at least one other numeric column.")
    positions = {name: index for index, name in enumerate(header)}
    groups, incomplete = _group_results(records, positions, spec)
    summary = {"rows": len(records), "complete_group_rows": len(records) - len(incomplete),
               "incomplete_group_rows": len(incomplete), "group_count": len(groups)}
    scope = copy.deepcopy(payload["scope"])
    scope.update(contract="numeric-association-v1", input_contract=payload["scope"]["contract"])
    reference = {"source_snapshot_sha256": payload["snapshot_sha256"], "source_sha256": payload["source"]["sha256"],
                 "file_name": spec["file"], "url": spec["source_url"], "license_note": spec["license_note"],
                 "predecessor": copy.deepcopy(predecessor),
                 "locator": {"kind": "csv_logical_records", "first": 1 if records else None,
                             "last": len(records) or None, "physical_line_end": physical_end}}
    analysis = {"summary": summary, "target_column": spec["target_column"],
                "predictor_columns": [name for name in spec["numeric_columns"] if name != spec["target_column"]],
                "group_columns": copy.deepcopy(spec["group_columns"]),
                "overall": _associations(records, positions, spec), "groups": groups,
                "incomplete_group": {"rows": len(incomplete),
                                     "associations": _associations(incomplete, positions, spec) if incomplete else []}}
    result = {"schema_version": "numeric-association-v1", "source_snapshot_sha256": payload["snapshot_sha256"],
              "scope": scope, "predecessor": predecessor, **analysis, "scientific_validation": False}
    observation = {"producer": TOOL_ID, "kind": "numeric_association", **copy.deepcopy(analysis),
                   "scope": copy.deepcopy(scope), "predecessor": copy.deepcopy(predecessor),
                   "evidence_refs": [copy.deepcopy(reference)],
                   "interpretation_status": "descriptive_association_not_causation_or_clinical_validation",
                   "scientific_validation": False}
    return {"schema_version": "numeric-association-result-v1", "tool_id": TOOL_ID, "adapter_version": ADAPTER_VERSION,
            "status": "completed", "observations": [observation],
            "metrics": [{"name": name, "value": summary[name], "unit": "count"} for name in summary],
            "evidence_refs": [reference], "result": result, "failure": None,
            "scientific_validation": False, "new_fits": 0, "model_calls": 0}


def next_decision(result) -> dict:
    try:
        tabular._require(result["tool_id"] == TOOL_ID and result["status"] == "completed"
                         and result["scientific_validation"] is False and result["new_fits"] == 0 and result["model_calls"] == 0
                         and result["result"]["schema_version"] == "numeric-association-v1",
                         "INVALID_RESULT", "A completed descriptive numeric association result is required.")
        required = ["Confirm the original target meaning, units, provenance and sampling definitions.",
                    "Interpret saved pairwise exclusions and group coding against original records before drawing research conclusions."]
        if result["result"]["summary"]["incomplete_group_rows"]:
            required.append("Resolve grouping fields for the separately recorded incomplete-group rows.")
        return {"policy_ref": {"id": TOOL_ID, "version": ADAPTER_VERSION}, "project_status": "waiting",
                "next_action": {"kind": "evidence_task", "method_id": "research.source-selection", "execution_status": "not_executed",
                                "required_evidence": required},
                "reason": "Pairwise Pearson associations and exclusions are saved; sampling uncertainty, causal and clinical meaning remain unconfirmed.",
                "source_snapshot_sha256": result["result"]["source_snapshot_sha256"],
                "predecessor": copy.deepcopy(result["result"]["predecessor"]),
                "evidence_refs": copy.deepcopy(result["evidence_refs"]), "scientific_validation": False, "new_fits": 0, "model_calls": 0}
    except ResearchError:
        raise
    except (KeyError, TypeError, ValueError):
        raise ResearchError("INVALID_RESULT", "Malformed numeric association feedback.") from None
