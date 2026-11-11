"""Fixed conditional re-pairing controls for saved predictions."""
import math

import numpy as np

from .prediction_checks import _mean, _missing_group, _number


def _loss(observed, predicted):
    with np.errstate(over="ignore", invalid="ignore"):
        errors = np.abs(observed - predicted)
    if not np.isfinite(errors).all():
        raise ValueError("Re-pairing errors exceed the finite numeric range.")
    return _mean(errors.tolist())


def _summary(original, controls, n):
    result = {"n": n, "original_mae": original, "candidate_mae": original,
              "reference_mae": None, "improvement": None, "permutation_median": None,
              "permutation_p05": None, "permutation_p95": None, "conditional_rank": None,
              "alignment_supported": None, "status": "not_computable", "reason": "insufficient_samples"}
    if not controls:
        return result
    median = float(np.median(controls))
    lower, upper = (float(value) for value in np.quantile(controls, [0.05, 0.95]))
    tolerance = 1e-12 * max(1.0, abs(original), max(abs(value) for value in controls))
    rank = (1 + sum(value <= original + tolerance for value in controls)) / (len(controls) + 1)
    improvement = 1 - original / median if median else None
    if improvement is not None and not math.isfinite(improvement):
        raise ValueError("Control improvement exceeds the finite numeric range.")
    result.update(reference_mae=median, improvement=improvement, permutation_median=median,
                  permutation_p05=lower, permutation_p95=upper, conditional_rank=rank)
    if all(abs(value - original) <= tolerance for value in controls):
        result["reason"] = "no_reordering_information"
    else:
        result.update(status="computed", reason=None, alignment_supported=rank <= 0.05 and original < median)
    return result


def evaluate_negative_control(observed, predicted, *, groups, seed=11, repeats=199):
    """Re-pair saved predictions inside fixed declared groups using a frozen protocol.

    The rank includes ties. Its reference range describes this re-pairing process
    on the saved table and carries no external-population interval semantics.
    """
    if type(seed) is not int or seed != 11 or type(repeats) is not int or repeats != 199:
        raise ValueError("The fixed control protocol requires seed=11 and repeats=199.")
    if groups is None or len(observed) != len(predicted) or len(groups) != len(observed):
        raise ValueError("Targets, predictions and declared groups must have equal lengths.")
    rows, exclusions, parts = [], [], {}
    for index, (actual, prediction, label) in enumerate(zip(observed, predicted, groups), 1):
        actual, prediction = _number(actual), _number(prediction)
        label = tuple(label) if isinstance(label, list) else label
        reasons = []
        if actual is None:
            reasons.append("observed_missing_or_nonfinite")
        if prediction is None:
            reasons.append("predicted_missing_or_nonfinite")
        if _missing_group(label):
            reasons.append("group_missing_or_nonfinite")
        if reasons:
            exclusions.append({"row": index, "reasons": reasons})
        else:
            parts.setdefault(label, []).append(len(rows))
            rows.append((index, actual, prediction))
    actual = np.array([row[1] for row in rows])
    predictions = np.array([row[2] for row in rows])
    original = _loss(actual, predictions) if rows else None
    controls, per_group = [], [[] for _ in parts]
    rng = np.random.default_rng(seed)
    if len(rows) >= 2:
        for _ in range(repeats):
            shuffled = predictions.copy()
            for indices in parts.values():
                shuffled[indices] = rng.permutation(predictions[indices])
            controls.append(_loss(actual, shuffled))
            for scores, indices in zip(per_group, parts.values()):
                scores.append(_loss(actual[indices], shuffled[indices]))
    summary = _summary(original, controls, len(rows))
    summary.update(input_n=len(observed), excluded=len(exclusions), group_count=len(parts))
    group_results = [{"group": label, "rows": [rows[index][0] for index in indices],
                      "summary": _summary(_loss(actual[indices], predictions[indices]), scores, len(indices))}
                     for (label, indices), scores in zip(parts.items(), per_group)]
    return {"schema_version": "prediction-negative-control-v1", "summary": summary,
            "protocol": {"seed": seed, "repeats": repeats, "loss": "MAE", "grouping": "within_declared_groups",
                         "conditional_rank_threshold": 0.05, "ties": "included_with_numeric_tolerance"},
            "shuffled_mae": controls, "per_group": group_results, "exclusions": exclusions,
            "findings": [{"code": summary["reason"] or ("record_pairing_supported" if summary["alignment_supported"]
                                                         else "record_pairing_not_supported")}],
            "limitations": ["重排参考范围描述当前保存表和声明分组内的配对诊断。",
                            "训练划分稳健性、样本独立性和外部泛化需要各自的评价协议。"],
            "scientific_validation": False}
