"""Compare explicitly related feature checks using saved OOF records only."""

import copy
from bisect import bisect_right

from .prediction_checks import _mean
from .project_design import family


def _reference(record):
    binding = record["design_binding"]
    resource = binding["resource"]
    return {"action_id": record["action_id"], "design_version": binding["version"],
            "resource_id": resource["id"], "resource_version": resource["version"],
            "feature_columns": copy.deepcopy(record["protocol"]["feature_columns"])}


def _fixed_basis_protocols_match(baseline, candidate):
    from .input_basis import protocol

    left, right = baseline["protocol"], candidate["protocol"]
    columns = left["feature_columns"]
    left_training = baseline["design_binding"].get("training", {})
    right_training = candidate["design_binding"].get("training", {})
    if (len(columns) != 1 or right["feature_columns"] != columns
            or left_training.get("feature_columns") != columns or "input_basis" in left_training
            or right_training.get("feature_columns") != columns or right_training.get("input_basis") != "univariate_cubic"):
        return False
    expected = protocol(right_training)
    fields = ("input_basis", "model_input_terms")
    if any(key in left or right.get(key) != expected[key] for key in fields):
        return False
    return left == {key: value for key, value in right.items() if key not in fields}


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
    fixed_basis = right_resource.get("comparison_kind") == "fixed_input_basis"
    protocols = [{key: value for key, value in record["protocol"].items() if key != "feature_columns"}
                 for record in (baseline, candidate)]
    if (fixed_basis and not _fixed_basis_protocols_match(baseline, candidate)) or (not fixed_basis and protocols[0] != protocols[1]):
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
    if fixed_basis:
        result.update(comparison_kind="fixed_input_basis", changed_protocol_fields=[key for key in ("input_basis", "model_input_terms")
                      if baseline["protocol"].get(key) != candidate["protocol"].get(key)])
        for name, record in (("baseline_ref", baseline), ("candidate_ref", candidate)):
            saved = record["protocol"]
            result[name]["input_basis"] = copy.deepcopy(saved.get("input_basis", {"kind": "raw", "source_columns": saved["feature_columns"]}))
            if "model_input_terms" in saved or "input_basis" not in saved:
                result[name]["model_input_terms"] = copy.deepcopy(saved.get("model_input_terms", saved["feature_columns"]))
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


def _paired_errors(pairs):
    errors = [[row["predicted"] - row["observed"] for row in side] for side in zip(*pairs)]
    absolute = [[abs(value) for value in side] for side in errors]
    lower = sum(right < left for left, right in zip(*absolute)) if pairs else 0
    higher = sum(right > left for left, right in zip(*absolute)) if pairs else 0
    result = {"n": len(pairs), "improved_rows": lower, "worsened_rows": higher,
              "tied_rows": len(pairs) - lower - higher}
    for index, label in enumerate(("baseline", "candidate")):
        result[label + "_mae"] = _mean(absolute[index]) if pairs else None
        result[label + "_mean_error"] = _mean(errors[index]) if pairs else None
        result[label + "_negative_predictions"] = sum(pair[index]["predicted"] < 0 for pair in pairs)
    result["mae_change"] = result["candidate_mae"] - result["baseline_mae"] if pairs else None
    return result


def _input_profiles(baseline, candidate, source):
    """Describe the complete matched OOF set; bucket boundaries use inputs only."""
    from . import tabular_quality_adapter as tabular, numeric_association_adapter as numeric

    spec, _, (header, original, _) = tabular._checked(source)
    columns = list(dict.fromkeys(candidate["protocol"]["feature_columns"] + baseline["protocol"]["feature_columns"]))
    tabular._require(source["snapshot_sha256"] == baseline["source_snapshot_sha256"]
                     and spec["target_column"] == baseline["target_column"]
                     and set(columns) <= set(spec["numeric_columns"]) - {spec["target_column"]},
                     "PROFILE_SOURCE_MISMATCH", "Input profiles require the original captured numeric fields and target.")
    positions, missing = {name: index for index, name in enumerate(header)}, set(spec["missing_tokens"])
    right = {row["logical_record"]: row for row in candidate["oof"]}
    pairs, values = [], {column: [] for column in columns}
    for row in sorted(baseline["oof"], key=lambda item: item["logical_record"]):
        index = row["logical_record"]
        tabular._require(1 <= index <= len(original), "PROFILE_SOURCE_MISMATCH", "OOF record is absent from the captured input.")
        raw, physical = original[index - 1]
        tabular._require(physical == row["physical_line_end"]
                         and numeric._finite(raw[positions[spec["target_column"]]], missing) == row["observed"],
                         "PROFILE_SOURCE_MISMATCH", "OOF target or original coordinates differ from the captured input.")
        pairs.append((row, right[index]))
        for column in columns:
            value = numeric._finite(raw[positions[column]], missing)
            tabular._require(value is not None, "PROFILE_SOURCE_MISMATCH", "A matched trained input is missing or nonfinite.")
            values[column].append(value)
    profiles = []
    totals = _paired_errors(pairs)
    for column, inputs in values.items():
        levels = sorted(set(inputs))
        exact = len(levels) <= 16
        edges = levels if exact else [levels[0] * (1 - step / 5) + levels[-1] * (step / 5) for step in range(6)]
        buckets = [[] for _ in range(len(levels) if exact else 5)]
        for value, pair in zip(inputs, pairs):
            index = levels.index(value) if exact else bisect_right(edges[1:-1], value)
            buckets[index].append(pair)
        result = {"column": column, "grouping": "exact_values" if exact else "equal_width",
                  "n": len(pairs), "buckets": [],
                  **{name: totals[name] for name in ("improved_rows", "worsened_rows", "tied_rows")}}
        for index, bucket in enumerate(buckets):
            label = str(edges[index]) if exact else "[" + str(edges[index]) + ", " + str(edges[index + 1]) + ("]" if index == 4 else ")")
            result["buckets"].append({"label": label, **_paired_errors(bucket),
                                      "logical_records": [left["logical_record"] for left, _ in bucket]})
        profiles.append(result)
    return profiles


def compare_feature_checks(records, source=None):
    """Pair only completed raw checks connected by an explicit resource parent."""
    eligible = [record for record in records if record.get("status") == "completed"
                and record.get("check") in ("random_cv", "group_cv")
                and family(record["design_binding"]["resource"]) == "raw"]
    results = []
    for candidate in eligible:
        for baseline in eligible:
            if (candidate["check"] != baseline["check"]
                    or candidate["design_binding"]["resource"]["id"] != baseline["design_binding"]["resource"]["id"]
                    or candidate["design_binding"]["resource"].get("parent_version") != baseline["design_binding"]["resource"]["version"]):
                continue
            comparison = compare_feature_pair(baseline, candidate)
            if source is not None and comparison["status"] == "comparable":
                comparison["input_profiles"] = _input_profiles(baseline, candidate, source)
            results.append(comparison)
    return results
