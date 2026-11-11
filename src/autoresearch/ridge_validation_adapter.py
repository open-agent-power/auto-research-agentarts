"""Fixed Ridge OOF protocols over captured complete-case tabular inputs."""
import copy
import hashlib
from pathlib import Path

import numpy as np
from sklearn.linear_model import Ridge
from sklearn.model_selection import GroupKFold, KFold
from sklearn.preprocessing import StandardScaler

from . import grouped_quality_adapter as grouped, numeric_association_adapter as numeric, prediction_checks, tabular_quality_adapter as tabular
from . import input_basis


ADAPTER_VERSION = "2"


def _inputs(payload):
    original = {key: value for key, value in payload.items() if key != "design_binding"}
    spec, _, (header, records, physical_end) = tabular._checked(original)
    binding = payload.get("design_binding")
    tabular._require(type(binding) is dict and binding.get("source_snapshot_sha256") == payload["snapshot_sha256"]
                     and binding.get("target_column") == spec["target_column"] and spec["target_column"] is not None,
                     "EVIDENCE_CHANGED", "Bind the captured target and source before training validation.")
    training = binding.get("training")
    tabular._require(type(training) is dict, "INVALID_TRAINING", "A frozen training declaration is required.")
    features, split_groups = training.get("feature_columns"), training.get("split_group_columns")
    tabular._require(type(features) is list and 1 <= len(features) <= 16
                     and all(type(name) is str and name in spec["numeric_columns"] for name in features)
                     and len(set(features)) == len(features) and spec["target_column"] not in features
                     and type(split_groups) is list and all(type(name) is str and name in spec["group_columns"] for name in split_groups)
                     and len(set(split_groups)) == len(split_groups)
                     and not set(features).intersection([*spec["group_columns"], *split_groups]),
                     "INVALID_TRAINING", "Select distinct numeric features excluding the target and declared grouping columns.")
    tabular._require(type(training.get("fit_limit")) is int and training["fit_limit"] >= 0,
                     "INVALID_TRAINING", "Declare a nonnegative combined scaler and Ridge fit limit.")
    tabular._require(len(records) <= 512, "UNSUPPORTED_SCOPE", "Training validation supports at most 512 captured rows.")
    positions, missing, rows, exclusions = {name: index for index, name in enumerate(header)}, set(spec["missing_tokens"]), [], []
    for logical_record, (values, line_end) in enumerate(records, 1):
        observed = numeric._finite(values[positions[spec["target_column"]]], missing)
        inputs = [numeric._finite(values[positions[name]], missing) for name in features]
        labels = tuple(values[positions[name]] for name in split_groups)
        reasons = []
        if observed is None:
            reasons.append("target_missing_or_nonfinite")
        if any(value is None for value in inputs):
            reasons.append("feature_missing_or_nonfinite")
        if any(label in missing for label in labels):
            reasons.append("split_group_missing")
        if reasons:
            exclusions.append({"logical_record": logical_record, "physical_line_end": line_end, "reasons": reasons})
        else:
            rows.append({"logical_record": logical_record, "physical_line_end": line_end,
                         "observed": observed, "features": inputs, "groups": labels})
    model_inputs = input_basis.expand(np.array([row["features"] for row in rows], dtype=float).reshape(-1, len(features)), training)
    return {"spec": spec, "binding": binding, "training": training, "rows": rows, "model_inputs": model_inputs,
            "input_n": len(records), "exclusions": exclusions, "physical_end": physical_end}


def _fold_count(data, check):
    rows = data["rows"]
    if len(rows) < (5 if check == "random_cv" else 2):
        return 0, "insufficient_samples"
    if min(row["observed"] for row in rows) == max(row["observed"] for row in rows):
        return 0, "constant_target"
    if check == "random_cv":
        return 5, None
    groups = len({row["groups"] for row in rows}) if data["training"]["split_group_columns"] else 0
    return (min(5, groups), None) if groups >= 2 else (0, "insufficient_groups")


def _fit(estimator, x, y, *, index, fold, name, observer):
    event = {"index": index, "estimator": name, "fold": fold}
    if observer is not None:
        observer({**event, "status": "started"})
    try:
        estimator.fit(x, y)
    except Exception:
        if observer is not None:
            observer({**event, "status": "failed"})
        raise
    if observer is not None:
        observer({**event, "status": "completed"})


class RidgeValidationAdapter:
    ADAPTER_VERSION = ADAPTER_VERSION

    def __init__(self, check):
        self.check = check
        self.TOOL_ID = "data.ridge-" + ("random-validation" if check == "random_cv" else "group-validation")

    def code_identity(self):
        raw = Path(__file__).read_bytes() + Path(prediction_checks.__file__).read_bytes() + Path(input_basis.__file__).read_bytes()
        return hashlib.sha256(raw + tabular.code_identity().encode("ascii") + numeric.code_identity().encode("ascii")).hexdigest()

    def required_fit_attempts(self, payload):
        data = _inputs(payload)
        tabular._require(self.check in data["binding"]["resource"]["checks"],
                         "CONDITION_NOT_SATISFIED", "The frozen design must allow this validation protocol.")
        return 2 * _fold_count(data, self.check)[0]

    def execute(self, payload, parameters, fit_observer=None):
        predecessor, data = grouped._parameters(parameters), _inputs(payload)
        count, reason = _fold_count(data, self.check)
        tabular._require(self.check in data["binding"]["resource"]["checks"],
                         "CONDITION_NOT_SATISFIED", "The frozen design must allow this validation protocol.")
        tabular._require(data["training"]["fit_limit"] >= 2 * count,
                         "FIT_BUDGET_EXHAUSTED", "The frozen fit limit must cover both preprocessing and estimator attempts.")
        rows, training = data["rows"], data["training"]
        x = data["model_inputs"]
        y = np.array([row["observed"] for row in rows], dtype=float)
        summary = {"n": len(rows), "input_n": data["input_n"], "excluded": len(data["exclusions"]),
                   "group_count": len({row["groups"] for row in rows}) if training["split_group_columns"] else None,
                   "candidate_mae": None, "reference_mae": None, "improvement": None, "outperforms_reference": None,
                   "status": "not_computable", "reason": reason}
        protocol = {"splitter": "KFold" if self.check == "random_cv" else "GroupKFold", "n_splits": count,
                    "shuffle": self.check == "random_cv", "random_state": 11 if self.check == "random_cv" else None,
                    "ridge_alpha": 1.0, "preprocessing": "StandardScaler.fit on training rows only",
                    "reference": "training-fold target mean", "feature_columns": training["feature_columns"],
                    "split_group_columns": training["split_group_columns"], "grouping_semantics": "operator-declared source columns",
                    **input_basis.protocol(training)}
        oof, folds = [], []
        if count:
            labels = list(dict.fromkeys(row["groups"] for row in rows))
            group_ids = np.array([labels.index(row["groups"]) for row in rows])
            splitter = KFold(5, shuffle=True, random_state=11) if self.check == "random_cv" else GroupKFold(count)
            predicted, references, membership = np.empty(len(rows)), np.empty(len(rows)), np.empty(len(rows), dtype=int)
            for fold, (train, test) in enumerate(splitter.split(x, y, group_ids) if self.check == "group_cv" else splitter.split(x), 1):
                scaler, model = StandardScaler(), Ridge(alpha=1.0)
                _fit(scaler, x[train], None, index=2 * fold - 1, fold=fold, name="scaler", observer=fit_observer)
                _fit(model, scaler.transform(x[train]), y[train], index=2 * fold, fold=fold, name="ridge", observer=fit_observer)
                predicted[test], membership[test] = model.predict(scaler.transform(x[test])), fold
                references[test] = prediction_checks._mean(y[train].tolist())
                folds.append({"fold": fold, "train_records": [rows[index]["logical_record"] for index in train],
                              "test_records": [rows[index]["logical_record"] for index in test],
                              "reference_prediction": float(references[test[0]]), "model_params": model.get_params(),
                              "scaler_mean": scaler.mean_.tolist(), "scaler_scale": scaler.scale_.tolist(),
                              "ridge_coefficients": model.coef_.tolist(), "ridge_intercept": float(model.intercept_)})
            tabular._require(np.isfinite(predicted).all() and np.isfinite(references).all(),
                             "INVALID_RESULT", "OOF predictions and reference values must be finite.")
            errors, reference_errors = np.abs(y - predicted), np.abs(y - references)
            tabular._require(np.isfinite(errors).all() and np.isfinite(reference_errors).all(),
                             "INVALID_RESULT", "OOF error metrics exceed the finite numeric range.")
            candidate, reference = prediction_checks._mean(errors.tolist()), prediction_checks._mean(reference_errors.tolist())
            improvement = 1 - candidate / reference if reference else None
            tabular._require(improvement is None or np.isfinite(improvement), "INVALID_RESULT", "Relative error comparison must be finite.")
            summary.update(candidate_mae=candidate, reference_mae=reference, improvement=improvement,
                           outperforms_reference=improvement > 0 if improvement is not None else None,
                           status="computed" if improvement is not None else "not_computable",
                           reason=None if improvement is not None else "reference_mae_zero")
            oof = [{"logical_record": row["logical_record"], "physical_line_end": row["physical_line_end"],
                    "observed": row["observed"], "predicted": float(predicted[index]), "groups": list(row["groups"]) or None,
                    "fold": int(membership[index]), "reference_prediction": float(references[index])} for index, row in enumerate(rows)]
        return self._result(payload, data, predecessor, protocol, summary, oof, folds, count)

    def _result(self, payload, data, predecessor, protocol, summary, oof, folds, count):
        spec = data["spec"]
        scope = copy.deepcopy(payload["scope"])
        scope.update(contract="ridge-" + self.check + "-v1", input_contract=payload["scope"]["contract"])
        evidence = {"source_snapshot_sha256": payload["snapshot_sha256"], "source_sha256": payload["source"]["sha256"],
                    "file_name": spec["file"], "url": spec["source_url"], "license_note": spec["license_note"],
                    "locator": {"kind": "csv_logical_records", "first": 1 if data["input_n"] else None,
                                "last": data["input_n"] or None, "physical_line_end": data["physical_end"]}}
        usage = {"ridge_fit_attempts": count, "preprocessing_fit_attempts": count, "fit_attempts": 2 * count}
        analysis = {"schema_version": "ridge-validation-v1", "check": self.check, "protocol": protocol, "summary": summary,
                    "oof": oof, "folds": folds, "usage": usage, "exclusions": data["exclusions"], "scope": scope,
                    "design_binding": copy.deepcopy(data["binding"]), "predecessor": predecessor,
                    "source_snapshot_sha256": payload["snapshot_sha256"], "target_column": spec["target_column"],
                    "target_unit": spec["target_unit"], "scientific_validation": False,
                    "limitations": ["结果限定于捕获输入、声明分组和当前固定划分。",
                                    "分组含义及样本独立性由原始材料支持，外部泛化需要独立评价。"]}
        return {"schema_version": "ridge-validation-result-v1", "tool_id": self.TOOL_ID, "adapter_version": ADAPTER_VERSION,
                "status": "completed", "observations": [{"producer": self.TOOL_ID, "kind": "ridge_validation", "check": self.check,
                    "summary": copy.deepcopy(summary), "protocol": copy.deepcopy(protocol), "usage": usage,
                    "design_binding": copy.deepcopy(data["binding"]), "scope": scope, "evidence_refs": [evidence],
                    "scientific_validation": False}],
                "metrics": [{"name": name, "value": summary[name], "unit": spec["target_unit"]}
                            for name in ("candidate_mae", "reference_mae")], "evidence_refs": [evidence],
                "result": {"analysis": analysis, "scope": scope, "predecessor": predecessor,
                           "source_snapshot_sha256": payload["snapshot_sha256"]},
                "failure": None, "scientific_validation": False, "new_fits": count, "model_calls": 0}

    def next_decision(self, result):
        tabular._require(result.get("tool_id") == self.TOOL_ID and result.get("status") == "completed",
                         "INVALID_RESULT", "A completed Ridge validation receipt is required.")
        analysis = result["result"]["analysis"]
        return {"policy_ref": {"id": self.TOOL_ID, "version": ADAPTER_VERSION}, "project_status": "waiting",
                "next_action": {"kind": "evidence_task", "method_id": "research.source-selection", "execution_status": "not_executed",
                                "required_evidence": ["Compare the fixed protocols and negative control before reusing the claim; verify declared groups and source units."]},
                "reason": "The saved OOF result is ready for the bound design's next eligible comparison.",
                "source_snapshot_sha256": analysis["source_snapshot_sha256"], "predecessor": analysis["predecessor"],
                "evidence_refs": copy.deepcopy(result["evidence_refs"]), "new_fits": result["new_fits"],
                "model_calls": 0, "scientific_validation": False}


RANDOM = RidgeValidationAdapter("random_cv")
GROUPED = RidgeValidationAdapter("group_cv")
ADAPTERS = (RANDOM, GROUPED)
