"""Read complete saved raw-Ridge OOF evidence without executing research or fitting."""

import copy
import math
from bisect import bisect_right

from . import numeric_association_adapter as numeric, tabular_quality_adapter as tabular
from .contracts import ResearchError
from .prediction_checks import _mean
from .prediction_summary import summarize_oof_range
from .project_design import MAX_RAW_RECORDS
from .project_experience import _checked_artifact, _check_folds, _near
from .research_project import ResearchProject
from .research_recipe import parse_json


def _require(condition, message, code="EVIDENCE_CHANGED"):
    if not condition:
        raise ResearchError(code, message)


def _binding(state, action, analysis, spec):
    binding = action.get("design_binding")
    _require(type(binding) is dict and type(binding.get("version")) is int,
             "The action must retain its original registered design binding.")
    revisions = [item for item in state.get("design_revisions", []) if item.get("version") == binding["version"]]
    _require(len(revisions) == 1 and revisions[0] == binding == analysis.get("design_binding")
             and binding.get("project_id") == state["id"]
             and binding.get("source_snapshot_sha256") == state["source_snapshot_sha256"]
             and binding.get("target_column") == spec["target_column"]
             and binding.get("prediction_column") is None,
             "The saved action, analysis and registered historical design differ.")
    training, protocol = binding.get("training"), analysis.get("protocol")
    _require(type(training) is dict and type(protocol) is dict,
             "A frozen raw training declaration and saved protocol are required.")
    features, groups = training.get("feature_columns"), training.get("split_group_columns")
    _require(type(features) is list and 1 <= len(features) <= 16
             and all(type(name) is str and name in spec["numeric_columns"] for name in features)
             and len(set(features)) == len(features) and spec["target_column"] not in features
             and type(groups) is list and all(type(name) is str and name in spec["group_columns"] for name in groups)
             and len(set(groups)) == len(groups) and not set(features).intersection(spec["group_columns"])
             and protocol.get("feature_columns") == features and protocol.get("split_group_columns") == groups,
             "Saved feature or declared split-group columns differ from the original training declaration.")
    resource = binding.get("resource", {})
    _require(type(resource) is dict and analysis["check"] in resource.get("checks", [])
             and resource["checks"][0] in ("random_cv", "group_cv"),
             "The historical resource does not authorize this raw validation check.")
    return binding


def _rows(analysis, spec, header, original, training, columns):
    """Check original coordinates, targets, complete-case exclusions and declared groups."""
    saved, oof, exclusions = analysis.get("summary", {}), analysis.get("oof"), analysis.get("exclusions")
    _require(type(saved) is dict and saved.get("status") == "computed" and type(oof) is list and oof
             and type(exclusions) is list, "Require a complete computable saved OOF result.", "NO_ELIGIBLE_OOF_ACTION")
    _require(1 <= len(original) <= MAX_RAW_RECORDS, "The captured raw input exceeds the supported row boundary.")
    by_id = {}
    for row in oof:
        _require(type(row) is dict and type(row.get("logical_record")) is int
                 and 1 <= row["logical_record"] <= len(original) and row["logical_record"] not in by_id
                 and type(row.get("physical_line_end")) is int and type(row.get("fold")) is int
                 and all(type(row.get(key)) in (int, float) and math.isfinite(row[key])
                         for key in ("observed", "predicted", "reference_prediction")),
                 "OOF rows require unique original coordinates and finite saved predictions.")
        by_id[row["logical_record"]] = row
    positions, missing = {name: index for index, name in enumerate(header)}, set(spec["missing_tokens"])
    expected_exclusions, complete, rows = [], set(), []
    features, groups = training["feature_columns"], training["split_group_columns"]
    for index, (raw, physical) in enumerate(original, 1):
        observed = numeric._finite(raw[positions[spec["target_column"]]], missing)
        inputs = {name: numeric._finite(raw[positions[name]], missing) for name in features}
        labels = [raw[positions[name]] for name in groups]
        reasons = []
        if observed is None:
            reasons.append("target_missing_or_nonfinite")
        if any(value is None for value in inputs.values()):
            reasons.append("feature_missing_or_nonfinite")
        if any(label in missing for label in labels):
            reasons.append("split_group_missing")
        if reasons:
            expected_exclusions.append({"logical_record": index, "physical_line_end": physical, "reasons": reasons})
            continue
        complete.add(index)
        row = by_id.get(index)
        _require(row is not None and row["physical_line_end"] == physical and row["observed"] == observed
                 and row.get("groups") == (labels or None),
                 "OOF target, physical coordinates or declared groups differ from the captured original row.")
        rows.append({**copy.deepcopy(row), "residual": row["predicted"] - observed,
                     "input_values": {name: inputs[name] for name in columns}})
    _require(set(by_id) == complete and exclusions == expected_exclusions
             and saved.get("input_n") == len(original) and saved.get("n") == len(rows)
             and saved.get("excluded") == len(exclusions),
             "OOF and exclusions must cover every original row with the original complete-case mask.")
    return rows, by_id


def _metrics(rows):
    return {"n": len(rows), "candidate_mae": _mean([abs(row["predicted"] - row["observed"]) for row in rows]),
            "reference_mae": _mean([abs(row["reference_prediction"] - row["observed"]) for row in rows]),
            "mean_error": _mean([row["predicted"] - row["observed"] for row in rows]),
            "reference_mean_error": _mean([row["reference_prediction"] - row["observed"] for row in rows]),
            "negative_predictions": sum(row["predicted"] < 0 for row in rows)}


def _groups(rows, declared):
    grouped = {}
    if declared:
        for row in rows:
            grouped.setdefault(tuple(row["groups"]), []).append(row)
    return [{"groups": list(labels), **_metrics(members), "logical_records": [row["logical_record"] for row in members],
             "folds": sorted({row["fold"] for row in members})} for labels, members in sorted(grouped.items())]


def _group_weighted(groups):
    return {"group_count": len(groups), "candidate_mae": _mean([group["candidate_mae"] for group in groups]),
            "reference_mae": _mean([group["reference_mae"] for group in groups])}


def _coverage(rows, declared):
    groups = _groups(rows, declared)
    return {"fold_count": len({row["fold"] for row in rows}),
            "fold_counts": [{"fold": fold, "n": sum(row["fold"] == fold for row in rows)}
                            for fold in sorted({row["fold"] for row in rows})],
            "group_count": len(groups) if declared else None,
            "group_membership": [{key: group[key] for key in ("groups", "n", "logical_records", "folds")} for group in groups]}


def _profiles(rows, columns, declared):
    """Use raw trained source inputs only, matching feature_comparison bucket boundaries."""
    profiles = []
    for column in columns:
        levels = sorted({row["input_values"][column] for row in rows})
        exact = len(levels) <= 16
        edges = levels if exact else [levels[0] * (1 - step / 5) + levels[-1] * (step / 5) for step in range(6)]
        buckets = [[] for _ in range(len(levels) if exact else 5)]
        for row in rows:
            value = row["input_values"][column]
            index = levels.index(value) if exact else bisect_right(edges[1:-1], value)
            buckets[index].append(row)
        profile = {"column": column, "input_scale": "raw_source_column", "grouping": "exact_values" if exact else "equal_width",
                   "boundary_basis": "evaluated_complete_case_inputs_only", "n": len(rows), "buckets": []}
        for index, members in enumerate(buckets):
            bounds = {"value": edges[index]} if exact else {"lower": edges[index], "upper": edges[index + 1],
                                                            "lower_inclusive": True, "upper_inclusive": index == 4}
            label = str(edges[index]) if exact else f"[{edges[index]}, {edges[index + 1]}" + ("]" if index == 4 else ")")
            profile["buckets"].append({"label": label, **bounds, **_metrics(members),
                "logical_records": [row["logical_record"] for row in members], **_coverage(members, declared)})
        profiles.append(profile)
    return profiles


def _folds(analysis, rows, declared):
    by_id = {row["logical_record"]: row for row in rows}
    folds = []
    for fold in analysis["folds"]:
        train, test = ([by_id[index] for index in fold[key]] for key in ("train_records", "test_records"))
        folds.append({"fold": fold["fold"], "train_n": len(train), "test_n": len(test),
                      "train_group_count": len(_groups(train, declared)) if declared else None,
                      "test_group_count": len(_groups(test, declared)) if declared else None,
                      "train_records": copy.deepcopy(fold["train_records"]), "test_records": copy.deepcopy(fold["test_records"]),
                      "reference_prediction": fold["reference_prediction"], **_metrics(test)})
    return folds


def inspect_saved_oof(workspace, action_id, columns=()):
    """Derive a standalone diagnostic of an explicit completed registered raw Ridge action.

    This reader preserves the producer identity and permits an unchanged historical
    binding. It verifies saved arithmetic and documented source mappings; it never
    re-fits estimators, reconstructs training parameters or dispatches source tools.
    """
    project = ResearchProject(workspace)
    state = project.status()
    action = next((item for item in state["actions"] if item["id"] == action_id), None)
    _require(action is not None and action.get("status") == "completed"
             and action.get("command") in ("data.ridge-random-validation", "data.ridge-group-validation"),
             "Select an explicit completed registered raw Ridge validation action.", "NO_ELIGIBLE_OOF_ACTION")
    source = project._source(state)
    spec, _, (header, original, _) = tabular._checked(source)
    _require(source["snapshot_sha256"] == state["source_snapshot_sha256"]
             and source["scope"] == state["source_scope"]
             and action.get("source_snapshot_sha256") == state["source_snapshot_sha256"],
             "Captured source and registered action source differ.")
    raw = project._artifact(action).read_bytes()
    envelope = parse_json(raw, maximum=len(raw), code="EVIDENCE_CHANGED")
    analysis = _checked_artifact(action, envelope, state)
    binding = _binding(state, action, analysis, spec)
    _require(type(columns) in (tuple, list) and all(type(name) is str and name in binding["training"]["feature_columns"]
             for name in columns), "Profiles require raw numeric source columns used by this action's training.", "INVALID_DIAGNOSTIC_COLUMN")
    columns = list(dict.fromkeys(columns))
    rows, by_id = _rows(analysis, spec, header, original, binding["training"], columns)
    _check_folds(analysis, by_id)
    metrics, saved = _metrics(rows), analysis["summary"]
    for key in ("candidate_mae", "reference_mae"):
        _near(saved.get(key), metrics[key], "Saved OOF arithmetic differs: " + key)
    _require(metrics["reference_mae"] > 0, "Require a computable training-fold mean reference.")
    _near(saved.get("improvement"), 1 - metrics["candidate_mae"] / metrics["reference_mae"], "Saved improvement differs.")
    _require(saved.get("outperforms_reference") is (metrics["candidate_mae"] < metrics["reference_mae"]),
             "Saved reference comparison differs.")
    declared = bool(binding["training"]["split_group_columns"])
    groups = _groups(rows, declared)
    _require(saved.get("group_count") == (len(groups) if declared else None), "Saved declared group count differs.")
    strata = []
    for label, selected in (("singleton", [group for group in groups if group["n"] == 1]),
                            ("repeated", [group for group in groups if group["n"] > 1])):
        records = sorted(index for group in selected for index in group["logical_records"])
        strata.append({"stratum": label, "logical_records": records,
                       "row_weighted": _metrics([by_id[index] for index in records]), "group_weighted": _group_weighted(selected)})
    result = {"schema_version": "saved-oof-diagnostics-v1", "scientific_validation": False,
              "provenance": {"project_id": state["id"], "state_version": state["state_version"], "snapshot_ref": state["snapshot_ref"],
                  "source_snapshot_sha256": state["source_snapshot_sha256"], "source_scope": copy.deepcopy(state["source_scope"]),
                  "source_sha256": source["source"]["sha256"], "source_file": spec["file"],
                  "action": {key: copy.deepcopy(action[key]) for key in ("id", "request_id", "command", "status", "request_sha256",
                               "source_snapshot_sha256", "code_identity", "result_sha256", "evaluation_ref")},
                  "artifact_sha256": envelope["sha256"], "artifact_schema_version": envelope.get("schema_version"),
                  "current_project_code_identity": state["code_identity"], "design_binding": copy.deepcopy(binding)},
              "check": analysis["check"], "protocol": copy.deepcopy(analysis["protocol"]),
              "target_column": analysis["target_column"], "target_unit": analysis["target_unit"],
              "input_n": len(original), "excluded": len(analysis["exclusions"]), "exclusions": copy.deepcopy(analysis["exclusions"]),
              "requested_columns": columns, "rows": rows, "row_weighted": metrics, "saved_summary": copy.deepcopy(saved),
              "prediction_ranges": summarize_oof_range(rows),
              "group_columns": copy.deepcopy(binding["training"]["split_group_columns"]),
              "group_weighted": _group_weighted(groups), "groups": groups, "folds": _folds(analysis, rows, declared),
              "group_strata": strata, "input_profiles": _profiles(rows, columns, declared),
              "validation": {"scope": "saved_oof_arithmetic_and_original_source_mapping", "fit_calls": 0,
                             "model_dispatches": 0, "source_dispatches": 0},
              "limitations": ["诊断仅派生自完整保存 OOF，未重拟合或重算训练参数，未修改原项目。",
                  "分组来自训练时声明的 split_group_columns，不等于原生独立实验单位。",
                  "逐行平均与逐组等权平均回答不同的加权问题，均不能建立科学有效性。",
                  "输入分桶只描述已评价完整行；边界由原尺度输入决定，不按残差筛选、裁剪或删除行。",
                  *copy.deepcopy(analysis.get("limitations", []))]}
    _require(project.status() == state, "Source project changed during diagnostic reading.", "STALE_STATE")
    return result
