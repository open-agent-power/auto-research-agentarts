"""Descriptive comparisons of paired saved targets and predictions."""
import math


def _mean(values):
    if not values:
        return None
    scale = max(abs(value) for value in values)
    result = math.fsum(value / scale for value in values) / len(values) * scale if scale else 0.0
    if not math.isfinite(result):
        raise ValueError("Prediction metrics exceed the finite numeric range.")
    return result


def _number(value):
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("Targets and predictions must contain numbers or missing values.")
    try:
        value = float(value)
    except OverflowError:
        raise ValueError("Input exceeds the finite numeric range.") from None
    return value if math.isfinite(value) else None


def _missing_group(value):
    if isinstance(value, tuple):
        return not value or any(_missing_group(part) for part in value)
    if not isinstance(value, (str, int, float, type(None))):
        raise ValueError("Groups must be text, numbers or tuples of these values.")
    return value is None or value == "" or isinstance(value, float) and not math.isfinite(value)


def _partition(rows, grouped):
    parts = {}
    for row in rows:
        parts.setdefault(row[3] if grouped else row[0], []).append(row)
    return parts


def _comparison(rows, grouped=False):
    observed = [row[1] for row in rows]
    errors = [abs(row[2] - row[1]) for row in rows]
    if not all(math.isfinite(error) for error in errors):
        raise ValueError("Prediction errors exceed the finite numeric range.")
    summary = {"n": len(rows), "candidate_mae": _mean(errors), "reference_mae": None,
               "improvement": None, "outperforms_reference": None,
               "reference_kind": "leave_group_out_mean" if grouped else "leave_one_out_mean",
               "status": "not_computable", "reason": None}
    if len(rows) < 2:
        summary["reason"] = "insufficient_samples"
        return summary, []
    parts = _partition(rows, grouped)
    if len(parts) < 2:
        summary["reason"] = "insufficient_groups"
        return summary, []
    anchor = observed[0]
    centered = [value - anchor for value in observed]
    if not all(math.isfinite(value) for value in centered):
        raise ValueError("Target differences exceed the finite numeric range.")
    scale = max(abs(value) for value in centered) or 1.0
    total = math.fsum(value / scale for value in centered)
    sums = {key: math.fsum((row[1] - anchor) / scale for row in part) for key, part in parts.items()}
    references = [(total - sums[row[3] if grouped else row[0]]) /
                  (len(rows) - len(parts[row[3] if grouped else row[0]])) * scale + anchor for row in rows]
    reference_errors = [abs(row[1] - reference) for row, reference in zip(rows, references)]
    if not all(math.isfinite(error) for error in reference_errors):
        raise ValueError("Reference errors exceed the finite numeric range.")
    summary["reference_mae"] = _mean(reference_errors)
    if min(observed) == max(observed):
        summary["reason"] = "constant_target"
    elif summary["reference_mae"] == 0:
        summary["reason"] = "reference_mae_underflow"
    else:
        improvement = 1 - summary["candidate_mae"] / summary["reference_mae"]
        if not math.isfinite(improvement):
            raise ValueError("Relative improvement exceeds the finite numeric range.")
        summary.update(status="computed", improvement=improvement,
                       outperforms_reference=improvement > 0)
    return summary, references


def _group_details(rows, summary, references):
    groups = []
    reference_by_row = dict(zip((row[0] for row in rows), references))
    for label, part in _partition(rows, True).items():
        candidate = _mean([abs(row[2] - row[1]) for row in part])
        reference = _mean([abs(row[1] - reference_by_row[row[0]]) for row in part]) if references else None
        improvement = 1 - candidate / reference if reference else None
        if improvement is not None and not math.isfinite(improvement):
            raise ValueError("Group improvement exceeds the finite numeric range.")
        groups.append({"group": label, "n": len(part), "candidate_mae": candidate,
                       "mean_residual": _mean([row[2] - row[1] for row in part]),
                       "reference_mae": reference, "improvement": improvement,
                       "outperforms_reference": improvement > 0 if improvement is not None else None})
    worst = max(groups, key=lambda group: group["candidate_mae"]) if groups else None
    return {"groups": groups, "worst_group": worst,
            "worst_group_gap": worst["candidate_mae"] - summary["candidate_mae"] if worst else None}


def _sensitivity(rows, summary, grouped):
    removals = []
    for label, part in _partition(rows, grouped).items():
        remaining = [row for row in rows if (row[3] if grouped else row[0]) != label]
        metrics, _ = _comparison(remaining, grouped)
        comparable = metrics["improvement"] is not None and summary["improvement"] is not None
        removals.append({"unit": label, "removed_n": len(part), "remaining_n": len(remaining),
                         **metrics, "reverses_conclusion":
                         metrics["outperforms_reference"] != summary["outperforms_reference"] if comparable else None})
    comparable = [item for item in removals if item["reverses_conclusion"] is not None]
    most = max(comparable, key=lambda item: abs(item["improvement"] - summary["improvement"])) if comparable else None
    return {"unit_kind": "group" if grouped else "row", "removals": removals,
            "computable_units": len(comparable), "conclusion_reversed":
            any(item["reverses_conclusion"] for item in comparable) if comparable else None,
            "most_influential": most}


def evaluate_prediction(observed, predicted, *, groups=None, check="baseline"):
    """Compare saved values using paired exclusions and held-out mean references.

    Improvement is 1 - candidate MAE / reference MAE. Residuals are predicted
    minus observed. Row numbers are one-based positions in the original input.
    Missing or nonfinite values exclude the entire paired row; provided groups
    participate in the same exclusion. Invalid types and unrepresentable metrics
    raise ValueError. Constant targets retain MAE but have no relative comparison.
    """
    if check not in {"baseline", "grouped", "sensitivity"}:
        raise ValueError("Check must be baseline, grouped or sensitivity.")
    if len(observed) != len(predicted) or groups is not None and len(groups) != len(observed):
        raise ValueError("Targets, predictions and supplied groups must have equal lengths.")
    rows, exclusions = [], []
    observed_n = predicted_n = 0
    for index, (actual, prediction) in enumerate(zip(observed, predicted), 1):
        actual, prediction = _number(actual), _number(prediction)
        observed_n += actual is not None
        predicted_n += prediction is not None
        group = groups[index - 1] if groups is not None else None
        reasons = []
        if actual is None:
            reasons.append("observed_missing_or_nonfinite")
        if prediction is None:
            reasons.append("predicted_missing_or_nonfinite")
        if groups is not None and _missing_group(group):
            reasons.append("group_missing_or_nonfinite")
        if reasons:
            exclusions.append({"row": index, "reasons": reasons})
        else:
            rows.append((index, actual, prediction, group))
    grouped = groups is not None and check in {"grouped", "sensitivity"}
    summary, references = _comparison(rows, grouped)
    summary.update(excluded=len(exclusions), observed_n=observed_n, predicted_n=predicted_n,
                   input_n=len(observed), group_count=len(_partition(rows, True)) if groups is not None else None)
    details = {"exclusions": exclusions}
    if check == "baseline" and groups is not None:
        details["leave_group_out"], _ = _comparison(rows, True)
    if check == "grouped":
        if groups is None:
            summary.update(status="not_computable", reason="groups_required", reference_kind="leave_group_out_mean",
                           reference_mae=None, improvement=None, outperforms_reference=None)
            details.update(groups=[], worst_group=None, worst_group_gap=None)
        else:
            details.update(_group_details(rows, summary, references))
    if check == "sensitivity":
        details.update(_sensitivity(rows, summary, grouped))
    findings = [{"code": summary["reason"] or ("lower_mae_than_reference" if summary["outperforms_reference"]
                                              else "no_lower_mae_than_reference")}]
    if check == "sensitivity" and details["conclusion_reversed"]:
        findings.append({"code": "improvement_conclusion_reversed_on_removal"})
    return {"schema_version": "prediction-check-v1", "check": check, "summary": summary,
            "findings": findings, "details": details,
            "limitations": ["结果描述已保存样本的预测误差比较，科学解释仍依赖数据和评价设计。",
                            "参考均值排除当前样本或整个组，其他样本的目标仍参与参考值计算。",
                            "敏感性检查沿用已保存预测，删除单位后重新计算剩余样本与参考均值。"]}
