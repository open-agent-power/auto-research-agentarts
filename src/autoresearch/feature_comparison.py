"""Compare explicitly related feature checks using saved OOF records only."""

import copy

from .prediction_checks import _mean
from .project_design import family


def _reference(record):
    binding = record["design_binding"]
    resource = binding["resource"]
    return {"action_id": record["action_id"], "design_version": binding["version"],
            "resource_id": resource["id"], "resource_version": resource["version"],
            "feature_columns": copy.deepcopy(record["protocol"]["feature_columns"])}


def compare_feature_pair(baseline, candidate):
    """Require the same saved evaluation before describing prediction changes."""
    reasons = []
    left_binding, right_binding = baseline["design_binding"], candidate["design_binding"]
    left_resource, right_resource = left_binding["resource"], right_binding["resource"]
    if (left_resource["id"] != right_resource["id"]
            or right_resource.get("parent_version") != left_resource["version"]):
        reasons.append("RESOURCE_LINEAGE_MISMATCH")
    if left_binding.get("project_id") != right_binding.get("project_id"):
        reasons.append("PROJECT_MISMATCH")
    for key, reason in (("check", "CHECK_MISMATCH"), ("source_snapshot_sha256", "SOURCE_SNAPSHOT_MISMATCH"),
                        ("target_column", "TARGET_MISMATCH"), ("target_unit", "TARGET_UNIT_MISMATCH")):
        if baseline[key] != candidate[key]:
            reasons.append(reason)
    protocols = [{key: value for key, value in record["protocol"].items() if key != "feature_columns"}
                 for record in (baseline, candidate)]
    if protocols[0] != protocols[1]:
        reasons.append("PROTOCOL_MISMATCH")
    row_maps = [{row["logical_record"]: row for row in record["oof"]} for record in (baseline, candidate)]
    if any(len(rows) != len(record["oof"]) for rows, record in zip(row_maps, (baseline, candidate))):
        reasons.append("DUPLICATE_OOF_RECORD")
    if not all(row_maps):
        reasons.append("EMPTY_OOF")
    if row_maps[0].keys() != row_maps[1].keys():
        reasons.append("ROW_COVERAGE_MISMATCH")
    for key, reason in (("physical_line_end", "ROW_COORDINATES_MISMATCH"), ("observed", "OBSERVED_MISMATCH"),
                        ("groups", "GROUPS_MISMATCH"), ("fold", "FOLD_ASSIGNMENT_MISMATCH"),
                        ("reference_prediction", "REFERENCE_PREDICTION_MISMATCH")):
        if any(row_maps[0][row][key] != row_maps[1][row][key] for row in row_maps[0].keys() & row_maps[1].keys()):
            reasons.append(reason)
    fold_maps = [{fold["fold"]: fold for fold in record["folds"]} for record in (baseline, candidate)]
    if any(len(folds) != len(record["folds"]) for folds, record in zip(fold_maps, (baseline, candidate))):
        reasons.append("DUPLICATE_FOLD_RECORD")
    if not all(fold_maps) or fold_maps[0].keys() != fold_maps[1].keys():
        reasons.append("FOLD_RECORDS_MISMATCH")
    for folds in fold_maps:
        if any(len(fold[key]) != len(set(fold[key])) for fold in folds.values() for key in ("train_records", "test_records")):
            reasons.append("DUPLICATE_SPLIT_RECORD")
    for fold_id in fold_maps[0].keys() & fold_maps[1].keys():
        left, right = fold_maps[0][fold_id], fold_maps[1][fold_id]
        if any(set(left[key]) != set(right[key]) for key in ("train_records", "test_records")):
            reasons.append("FOLD_RECORDS_MISMATCH")
        if left["reference_prediction"] != right["reference_prediction"]:
            reasons.append("REFERENCE_PREDICTION_MISMATCH")
        if left["model_params"] != right["model_params"]:
            reasons.append("MODEL_PARAMETERS_MISMATCH")
    result = {"schema_version": "feature-comparison-v1", "check": candidate["check"],
              "baseline_ref": _reference(baseline), "candidate_ref": _reference(candidate),
              "status": "not_comparable" if reasons else "comparable", "reason_codes": list(dict.fromkeys(reasons)),
              "scientific_validation": False}
    if reasons:
        return result
    errors = [_mean([abs(row["predicted"] - row["observed"]) for row in record["oof"]])
              for record in (baseline, candidate)]
    result.update(matched_rows=len(row_maps[0]), metrics={
        "baseline_mae": errors[0], "candidate_mae": errors[1], "mae_change": errors[1] - errors[0],
        "relative_improvement": 1 - errors[1] / errors[0] if errors[0] else None,
        "baseline_negative_predictions": sum(row["predicted"] < 0 for row in baseline["oof"]),
        "candidate_negative_predictions": sum(row["predicted"] < 0 for row in candidate["oof"]),
    })
    return result


def compare_feature_checks(records):
    """Pair only completed raw checks connected by an explicit resource parent."""
    eligible = [record for record in records if record.get("status") == "completed"
                and record.get("check") in ("random_cv", "group_cv")
                and family(record["design_binding"]["resource"]) == "raw"]
    return [compare_feature_pair(baseline, candidate) for candidate in eligible for baseline in eligible
            if candidate["check"] == baseline["check"]
            and candidate["design_binding"]["resource"]["id"] == baseline["design_binding"]["resource"]["id"]
            and candidate["design_binding"]["resource"].get("parent_version") == baseline["design_binding"]["resource"]["version"]]
