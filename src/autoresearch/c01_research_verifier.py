"""Standalone numerical verification, copied into a package as verify_results.py.

Requires NumPy and scikit-learn. Never imports autoresearch or package source,
uses a network, or executes instructions from the records. Checks consistency,
not authorship, source authenticity, model identity, or scientific validity.
"""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath
import platform
import re
import stat
import sys

import numpy as np
import sklearn
from sklearn.linear_model import Ridge
from sklearn.preprocessing import StandardScaler


FEATURES = ("ecm_gpa", "yield_mpa", "water_contact_angle_deg", "sfe_owrk_total_mn_m")
TARGETS = ("cell_seeding_efficiency_24h_pct", "dna_cell_count_d21", "alp_norm_d21",
           "calcium_deposition_d21_ug_ml")
PACKAGE_FILES = frozenset({
    "research.json", "reproduction.json", "comparison.csv", "paper.pdf",
    "figures/comparison.png", "figures/comparison.svg", "verify_results.py",
    "README.md", "environment.json", "source/c01.py", "source/c01_loop.py",
    "source/knowledge.py", "source/c01_research.py", "source/contracts.py"})
RTOL, ATOL = 1e-8, 1e-8
MAX_FILE_BYTES = 64 * 1024 * 1024
MAX_PACKAGE_BYTES = 128 * 1024 * 1024
SCIENTIFIC_STATUS = "exploratory_reused_loo_no_independent_validation"
DECISION_ORIGIN = "external_agent_submission_not_authenticated_model_identity"
FIT_PROMOTION = "not_evaluated_no_independent_holdout"
MODEL_TYPE = "Ridge_coefficients_fitted_not_LLM_weight_training"


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _object(value, fields=None, label="object"):
    _require(type(value) is dict and (fields is None or set(value) == set(fields)), "invalid " + label)
    return value


def _text(value, label="text", maximum=2000):
    _require(type(value) is str and 0 < len(value.strip()) <= maximum, "invalid " + label)
    return value


def _id(value):
    _require(type(value) is str and re.fullmatch(r"[A-Za-z0-9_.:-]{1,160}", value), "invalid identifier")
    return value


def _sha(value):
    _require(type(value) is str and re.fullmatch(r"[0-9a-f]{64}", value), "invalid SHA-256")
    return value


def _number(value):
    _require(type(value) in (int, float), "expected a finite number, not a boolean")
    try:
        value = float(value)
    except (OverflowError, ValueError):
        raise ValueError("expected a finite number") from None
    _require(math.isfinite(value), "expected a finite number")
    return value


def _canonical(value):
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
                          allow_nan=False).encode("utf-8")
    except (ValueError, TypeError, OverflowError, RecursionError):
        raise ValueError("record must contain finite JSON data") from None


def _fingerprint(value):
    return hashlib.sha256(_canonical(value)).hexdigest()


def _close(saved, actual, label):
    _require(math.isclose(_number(saved), _number(float(actual)), rel_tol=RTOL, abs_tol=ATOL),
             "recomputed number differs: " + label)


def _ids(value):
    _require(type(value) is list and len(value) <= 16, "invalid evidence identifiers")
    for item in value:
        _id(item)
    _require(len(value) == len(set(value)), "duplicate evidence identifier")
    return set(value)


def _score(y, predictions):
    with np.errstate(over="raise", invalid="raise", divide="raise"):
        errors = predictions - y
        denominator = float(np.sum((y - np.mean(y)) ** 2))
        _require(denominator > 0 and math.isfinite(denominator), "constant or invalid target")
        return {"mae": float(np.mean(np.abs(errors))),
                "rmse": float(np.sqrt(np.mean(errors ** 2))),
                "r2": 1 - float(np.sum(errors ** 2)) / denominator}


def _recompute(samples, recipe):
    _object(recipe, {"alpha", "features"}, "recipe")
    alpha, features = _number(recipe["alpha"]), recipe["features"]
    _require(0.001 <= alpha <= 10000 and type(features) is list and 1 <= len(features) <= 4
             and all(type(name) is str and name in FEATURES for name in features)
             and len(features) == len(set(features)), "invalid bounded recipe")
    _require(features == [name for name in FEATURES if name in features], "recipe feature order differs")
    x = np.asarray([[row[name] for name in features] for row in samples], dtype=float)
    result = {}
    for target in TARGETS:
        y = np.asarray([row[target] for row in samples], dtype=float)
        predictions, baseline = [], []
        for held_out in range(8):
            train = [index for index in range(8) if index != held_out]
            scaler = StandardScaler().fit(x[train])
            model = Ridge(alpha=alpha, solver="svd").fit(scaler.transform(x[train]), y[train])
            predictions.append(float(model.predict(scaler.transform(x[held_out:held_out + 1]))[0]))
            baseline.append(float(np.mean(y[train])))
        predictions, baseline = np.asarray(predictions), np.asarray(baseline)
        metrics, base = _score(y, predictions), _score(y, baseline)
        _require(base["mae"] > 0, "undefined baseline relative change")
        metrics.update({"baseline_" + name: value for name, value in base.items()})
        metrics.update(mae_relative_change_vs_baseline=(metrics["mae"] - base["mae"]) / base["mae"],
                       better_than_baseline=metrics["mae"] < base["mae"])
        result[target] = {"observed": y, "predicted": predictions, "baseline": baseline, "metrics": metrics}
    return result


def _check_fit(fit, samples):
    _object(fit, {"id", "recipe", "summary", "predictions", "reason", "source_citation_ids", "evidence_action_ids"}, "fit")
    calculated = _recompute(samples, fit["recipe"])
    summary = _object(fit["summary"], label="fit summary")
    _require(summary.get("id") == fit["id"] and summary.get("status") == "executed"
             and summary.get("method") == "leave_one_alloy_out / fold_fitted_StandardScaler_Ridge_svd"
             and summary.get("feature_names") == fit["recipe"]["features"], "fit summary identity differs")
    _require(_number(summary.get("alpha")) == _number(fit["recipe"]["alpha"]), "summary alpha differs")
    metrics = summary.get("metrics")
    _require(type(metrics) is list and len(metrics) == 4, "require four target metrics")
    seen = set()
    for metric in metrics:
        _object(metric, label="target metric")
        target = metric.get("target")
        _require(type(target) is str and target in TARGETS and target not in seen, "duplicate or unknown metric target")
        seen.add(target)
        _require(type(metric.get("n")) is int and metric["n"] == 8
                 and metric.get("feature_names") == fit["recipe"]["features"], "metric sample or feature identity differs")
        _require(_number(metric.get("alpha")) == _number(fit["recipe"]["alpha"]), "metric alpha differs")
        for name, value in calculated[target]["metrics"].items():
            if type(value) is bool:
                _require(type(metric.get(name)) is bool and metric[name] == value, "baseline comparison differs")
            else:
                _close(metric.get(name), value, target + "." + name)
    predictions = fit["predictions"]
    _require(type(predictions) is list and len(predictions) == 32, "require 32 held-out predictions")
    sample_index = {row["sample_id"]: index for index, row in enumerate(samples)}
    seen, maximum_error, violations = set(), 0.0, []
    for row in predictions:
        _object(row, {"round_id", "target", "sample_id", "observed", "predicted", "baseline_predicted",
                      "training_n", "training_sample_ids", "domain_flag"}, "prediction")
        target, sample = row["target"], row["sample_id"]
        _require(type(target) is str and target in TARGETS and type(sample) is str and sample in sample_index,
                 "unknown prediction target or sample")
        _require((target, sample) not in seen, "duplicate held-out prediction")
        seen.add((target, sample))
        index = sample_index[sample]
        _require(row["round_id"] == "R1" and type(row["training_n"]) is int and row["training_n"] == 7
                 and row["training_sample_ids"] == ";".join(r["sample_id"] for r in samples if r["sample_id"] != sample),
                 "held-out fold membership differs")
        actual = calculated[target]
        for field, key in (("observed", "observed"), ("predicted", "predicted"), ("baseline_predicted", "baseline")):
            _close(row[field], actual[key][index], target + "." + field)
        maximum_error = max(maximum_error, abs(row["predicted"] - actual["predicted"][index]))
        flag = ("cell_seeding_efficiency_outside_0_100_percent" if target == TARGETS[0] and not 0 <= row["predicted"] <= 100
                else "alp_reported_value_below_zero" if target == TARGETS[2] and row["predicted"] < 0 else "")
        _require(row["domain_flag"] == flag, "numerical domain warning differs")
        if flag:
            violations.append((target, sample, row["predicted"], flag))
    saved_violations = summary.get("domain_violations")
    _require(type(saved_violations) is list and len(saved_violations) == len(violations), "domain warning count differs")
    warnings = {(v["target"], v["sample_id"]): v for v in saved_violations if type(v) is dict and "target" in v and "sample_id" in v}
    _require(len(warnings) == len(violations), "duplicate or malformed domain warning")
    for target, sample, value, flag in violations:
        warning = warnings.get((target, sample), {})
        _require(warning.get("rule") == flag and warning.get("handling") == "not_clipped_not_valid_biological_prediction", "domain warning handling differs")
        _close(warning.get("predicted"), value, "domain warning prediction")
    return calculated, maximum_error


def _diagnostic_result(diagnostic, fits, recomputed, samples):
    action, params, saved = diagnostic["action"], diagnostic["parameters"], diagnostic["result"]
    _object(params, label="diagnostic parameters")
    _object(saved, label="diagnostic result")
    if action == "residuals":
        _require(set(params) == {"fit_action_id"} and params["fit_action_id"] in fits, "unknown residual fit")
        _require(saved.get("kind") == "held_out_error_influence" and saved.get("fit_action_id") == params["fit_action_id"]
                 and type(saved.get("n")) is int and saved["n"] == 8, "residual identity differs")
        targets = saved.get("targets")
        _require(type(targets) is list and len(targets) == 4, "invalid residual targets")
        for target, record in zip(TARGETS, targets):
            _object(record, label="residual target")
            values = recomputed[params["fit_action_id"]][target]
            errors = [abs(float(p - y)) for p, y in zip(values["predicted"], values["observed"])]
            largest = max(range(8), key=errors.__getitem__)
            _require(record.get("target") == target and record.get("sample_id") == samples[largest]["sample_id"], "residual sample identity differs")
            _close(record.get("largest_error"), errors[largest], "largest residual")
            _close(record.get("share_of_absolute_error"), errors[largest] / sum(errors) if sum(errors) else 0.0, "residual share")
            all_errors = record.get("all_errors")
            _require(type(all_errors) is list and len(all_errors) == 8, "invalid residual sample count")
            for row, sample, error in zip(all_errors, samples, errors):
                _object(row, {"sample_id", "absolute_error"}, "residual sample")
                _require(row["sample_id"] == sample["sample_id"], "residual sample differs")
                _close(row["absolute_error"], error, "sample residual")
    elif action == "correlation":
        _require(not params and saved.get("kind") == "pair_correlation_influence"
                 and saved.get("predictor") == FEATURES[2] and saved.get("outcome") == TARGETS[0]
                 and type(saved.get("n")) is int and saved["n"] == 8, "correlation identity differs")
        x, y = [row[FEATURES[2]] for row in samples], [row[TARGETS[0]] for row in samples]
        def pearson(a, b):
            centered_a, centered_b = np.asarray(a) - np.mean(a), np.asarray(b) - np.mean(b)
            denominator = float(np.sqrt(np.dot(centered_a, centered_a) * np.dot(centered_b, centered_b)))
            _require(denominator > 0 and math.isfinite(denominator), "undefined correlation")
            return float(np.dot(centered_a, centered_b)) / denominator
        full = pearson(x, y)
        _close(saved.get("pearson_r"), full, "full correlation")
        omitted = saved.get("leave_one_out")
        _require(type(omitted) is list and len(omitted) == 8, "invalid correlation sensitivity count")
        changes = 0
        for index, row in enumerate(omitted):
            _object(row, {"sample_id", "pearson_r"}, "correlation sensitivity")
            _require(row["sample_id"] == samples[index]["sample_id"], "correlation omitted sample differs")
            actual = pearson(x[:index] + x[index + 1:], y[:index] + y[index + 1:])
            _close(row["pearson_r"], actual, "leave-one-out correlation")
            changes += actual * full < 0
        _require(type(saved.get("sign_changes")) is int and saved["sign_changes"] == changes, "correlation sign changes differ")
    else:
        raise ValueError("unsupported diagnostic")


def _validate_record(research, reproduction):
    _canonical(research)
    _canonical(reproduction)
    _object(research, {"schema_version", "goal", "status", "origin_observation_sha256", "archive_sha256",
                       "corpus_sha256", "scientific_status", "decision_origin", "fits", "diagnostics", "decisions", "references"}, "research")
    _object(reproduction, {"inputs", "inputs_sha256", "analysis_code_sha256", "protocol", "model_weight_training"}, "reproduction")
    _require(research["schema_version"] == "c01-public-research-v1" and research["scientific_status"] == SCIENTIFIC_STATUS
             and research["decision_origin"] == DECISION_ORIGIN, "unsupported research scope or origin")
    _text(research["goal"])
    for field in ("origin_observation_sha256", "archive_sha256", "corpus_sha256"):
        _sha(research[field])
    _sha(reproduction["inputs_sha256"])
    _sha(reproduction["analysis_code_sha256"])
    _text(reproduction["protocol"])
    _text(reproduction["model_weight_training"])
    inputs = _object(reproduction["inputs"], {"samples", "source", "audit", "provenance", "bio_mapping"}, "inputs")
    _require(_fingerprint(inputs) == reproduction["inputs_sha256"], "input fingerprint differs")
    source = _object(inputs["source"], label="input source")
    _require(source.get("archive_sha256") == research["archive_sha256"], "archive identity differs")
    samples = inputs["samples"]
    _require(type(samples) is list and len(samples) == 8, "require eight alloy aggregate samples")
    sample_ids = []
    for row in samples:
        _object(row, {"sample_id", *FEATURES, *TARGETS}, "sample")
        _text(row["sample_id"], "sample id", 80)
        _require(";" not in row["sample_id"], "ambiguous sample id")
        sample_ids.append(row["sample_id"])
        for field in (*FEATURES, *TARGETS):
            _number(row[field])
    _require(len(set(sample_ids)) == 8, "duplicate sample id")
    for key in ("audit", "provenance", "bio_mapping"):
        _require(type(inputs[key]) is list, "invalid input annotation list")
    for key, maximum in (("fits", 6), ("diagnostics", 7), ("decisions", 24), ("references", 96)):
        _require(type(research[key]) is list and len(research[key]) <= maximum, "invalid bounded " + key)
    references = {}
    for reference in research["references"]:
        _object(reference, {"citation_id", "source", "location"}, "reference")
        key = _id(reference["citation_id"])
        _require(key not in references, "duplicate citation id")
        source = _object(reference["source"], label="citation source")
        _sha(source.get("sha256"))
        _text(source.get("path"), "citation path", 2048)
        location = _object(reference["location"], label="citation location")
        if set(location) == {"page"}:
            _require(type(location["page"]) is int and location["page"] > 0 and source.get("page") == location["page"], "invalid source page")
        else:
            _require(set(location) == {"line_start", "line_end"} and all(type(v) is int for v in location.values())
                     and 1 <= location["line_start"] <= location["line_end"] and source.get("page") is None, "invalid source line range")
        references[key] = reference
    decisions, previous, latest_experiment, terminal = {}, set(), None, None
    latest_experiment_ordinal, latest_control, control_reviewed = 0, None, False
    request_ids = set()
    for ordinal, decision in enumerate(research["decisions"], 1):
        _object(decision, {"id", "ordinal", "action", "request_id", "observation_sha256", "reason", "parameters",
                           "source_citation_ids", "evidence_action_ids", "result_sha256"}, "decision")
        key = _id(decision["id"])
        request_id = _id(decision["request_id"])
        _require(key not in previous and request_id not in request_ids and type(decision["ordinal"]) is int
                 and decision["ordinal"] == ordinal and terminal is None, "decision order or identity differs")
        _sha(decision["observation_sha256"])
        _sha(decision["result_sha256"])
        _text(decision["reason"])
        _object(decision["parameters"], label="decision parameters")
        cited = _ids(decision["source_citation_ids"])
        evidence = _ids(decision["evidence_action_ids"])
        _require(cited <= set(references) and evidence <= previous, "unbound or future decision evidence")
        action = decision["action"]
        _require(type(action) is str and action in {"search", "read_source", "inspect_dataset", "review_evidence", "propose_control", "fit", "residuals", "correlation", "pause", "stop"}, "unsupported decision")
        if action == "propose_control":
            _object(decision["parameters"], {"decision"}, "control proposal parameters")
            _require(type(decision["parameters"]["decision"]) is str and decision["parameters"]["decision"] in {"pause", "stop"}, "invalid proposed control")
            _require(cited and (latest_experiment is None or latest_experiment in evidence), "control proposal lacks source or latest experimental feedback")
            _require(latest_control is None or latest_control[1] < latest_experiment_ordinal, "duplicate current control proposal")
            latest_control, control_reviewed = (key, ordinal), False
            # The omitted payload is a nonterminal proposal, not an approval.
        if action == "inspect_dataset":
            _require(not decision["parameters"], "dataset inspection accepts no parameters")
            # Inspection payload stays in the original ledger. This projection
            # verifies numerical fits against attached inputs, not the read event
            # or physical units, sample mapping or scientific qualification.
        if action == "read_source":
            params = decision["parameters"]
            _object(params, {"document_id", "source_sha256", "start_chunk", "count"}, "read parameters")
            _text(params["document_id"], "document ID", 160)
            _sha(params["source_sha256"])
            _require(type(params["start_chunk"]) is int and 0 <= params["start_chunk"] <= 4095
                     and type(params["count"]) is int and 1 <= params["count"] <= 2, "invalid bounded read range")
            _require(any(ref["source"].get("id") == params["document_id"]
                         and ref["source"]["sha256"] == params["source_sha256"]
                         for ref in references.values()), "read source is not bound to projected original references")
            # This numerical projection excludes original chunks and navigation.
            # Its shape/source binding does not verify actual reading coverage.
        if action == "review_evidence":
            params = decision["parameters"]
            _object(params, {"field", "question", "finding", "status", "next_check"}, "review parameters")
            _require(type(params["field"]) is str and params["field"] in set(FEATURES) | set(TARGETS) | {"sample_mapping", "cell_protocol", "control_rationale"}, "unknown review field")
            if params["field"] == "control_rationale":
                _require(latest_control is not None and latest_control[1] > latest_experiment_ordinal
                         and not control_reviewed and latest_control[0] in evidence
                         and (latest_experiment is None or latest_experiment in evidence), "review is not bound to current unreviewed control and latest experiment")
                control_reviewed = True
            _require(type(params["status"]) is str and params["status"] in {"supported", "unresolved", "conflicting"}, "invalid model-asserted review status")
            _require(1 <= len(cited) <= 4, "review requires retrieved source references")
            for field, maximum in (("question", 500), ("finding", 1000), ("next_check", 500)):
                _text(params[field], "review " + field, maximum)
                _require(len(params[field]) <= maximum, "review text exceeds raw character limit")
            # Excerpts stay in the original ledger. This standalone numerical
            # verifier checks the projection's shape, not the claim or source.
        if action in {"fit", "residuals", "correlation"}:
            _require(cited and (latest_experiment is None or latest_experiment in evidence), "missing source or latest experimental feedback")
            latest_experiment = key
            latest_experiment_ordinal = ordinal
        if action in {"pause", "stop"}:
            _require(not decision["parameters"], "control decision has parameters")
            terminal = "paused" if action == "pause" else "stopped"
        decisions[key] = decision
        previous.add(key)
        request_ids.add(request_id)
    _require(research["status"] == (terminal or "active"), "research status differs from decisions")
    fits, recomputed, recipes, maximum_error = {}, {}, set(), 0.0
    for fit in research["fits"]:
        _require(type(fit) is dict, "invalid fit")
        key = _id(fit.get("id"))
        _require(key not in fits and key in decisions and decisions[key]["action"] == "fit", "fit action identity differs")
        decision = decisions[key]
        for field in ("reason", "source_citation_ids", "evidence_action_ids"):
            _require(fit.get(field) == decision[field], "fit decision binding differs")
        recomputed[key], error = _check_fit(fit, samples)
        maximum_error = max(maximum_error, error)
        recipe = _canonical({**fit["recipe"], "alpha": float(fit["recipe"]["alpha"])})
        _require(recipe not in recipes, "duplicate fit recipe")
        recipes.add(recipe)
        params = decision["parameters"]
        _require(set(params) == {"alpha", "features", "hypothesis", "expected_effect"}
                 and type(params["features"]) is list and all(type(v) is str for v in params["features"])
                 and len(params["features"]) == len(set(params["features"]))
                 and set(params["features"]) == set(fit["recipe"]["features"]), "fit parameters differ")
        _require(_number(params["alpha"]) == _number(fit["recipe"]["alpha"]), "decision alpha differs")
        _text(params["hypothesis"], "hypothesis", 1000)
        _text(params["expected_effect"], "expected effect", 1000)
        original_result = {"recipe": fit["recipe"], "summary": fit["summary"], "predictions": fit["predictions"],
                           "fold_fits": 32, "promotion": FIT_PROMOTION, "model_type": MODEL_TYPE}
        _require(_fingerprint(original_result) == decision["result_sha256"], "fit result fingerprint differs")
        fits[key] = fit
    _require(set(fits) == {key for key, value in decisions.items() if value["action"] == "fit"}, "missing executed fit")
    diagnostics, residual_fits, correlations = set(), set(), 0
    for diagnostic in research["diagnostics"]:
        _object(diagnostic, {"id", "action", "parameters", "reason", "result", "result_sha256",
                             "source_citation_ids", "evidence_action_ids"}, "diagnostic")
        key = _id(diagnostic["id"])
        _require(key not in diagnostics and key in decisions, "diagnostic action identity differs")
        decision = decisions[key]
        for field in ("action", "parameters", "reason", "result_sha256", "source_citation_ids", "evidence_action_ids"):
            _require(diagnostic[field] == decision[field], "diagnostic decision binding differs")
        _require(_fingerprint(diagnostic["result"]) == diagnostic["result_sha256"], "diagnostic fingerprint differs")
        _diagnostic_result(diagnostic, fits, recomputed, samples)
        if diagnostic["action"] == "residuals":
            fit_id = diagnostic["parameters"]["fit_action_id"]
            _require(decisions[fit_id]["ordinal"] < decision["ordinal"] and fit_id not in residual_fits, "repeated or future residual fit")
            residual_fits.add(fit_id)
        else:
            correlations += 1
            _require(correlations == 1, "repeated fixed correlation")
        diagnostics.add(key)
    _require(diagnostics == {key for key, value in decisions.items() if value["action"] in {"residuals", "correlation"}}, "missing executed diagnostic")
    return {"ok": True, "scope": "independent numerical recomputation and record consistency",
            "recipes_checked": len(fits), "fold_fits_performed": len(fits) * 32,
            "diagnostics_checked": len(diagnostics), "max_abs_prediction_error": float(maximum_error),
            "numerical_results_present": bool(fits or diagnostics), "relative_tolerance": RTOL, "absolute_tolerance": ATOL,
            "network_used": False, "package_source_executed": False, "scientific_validation": False,
            "llm_identity_verified": False, "origin_observation_reconstructed": False,
            "raw_archive_independently_verified": False,
            "environment": {"python": platform.python_version(), "numpy": np.__version__, "scikit_learn": sklearn.__version__},
            "limitations": ["Hashes are consistency checks, not signatures or proof of source authenticity.",
                            "Search excerpts and the original observation are not reconstructed.",
                            "Repeated leave-one-alloy-out feedback is not independent scientific validation."]}


def validate_record(research, reproduction):
    """Return a report, or raise ValueError on malformed/inconsistent numeric data."""
    try:
        return _validate_record(research, reproduction)
    except (KeyError, TypeError, IndexError, OverflowError, FloatingPointError, ZeroDivisionError,
            np.linalg.LinAlgError):
        raise ValueError("malformed or nonrecomputable research record") from None


def _read_regular(path, limit=MAX_FILE_BYTES):
    metadata = path.lstat()
    _require(not path.is_symlink() and not getattr(path, "is_junction", lambda: False)()
             and stat.S_ISREG(metadata.st_mode) and metadata.st_nlink == 1
             and metadata.st_size <= limit, "unsafe or oversized package file")
    with path.open("rb") as stream:
        opened = os.fstat(stream.fileno())
        _require((opened.st_dev, opened.st_ino, opened.st_size, opened.st_mtime_ns, opened.st_nlink)
                 == (metadata.st_dev, metadata.st_ino, metadata.st_size, metadata.st_mtime_ns, 1), "package file changed while opening")
        payload = stream.read(limit + 1)
        final = os.fstat(stream.fileno())
    _require(len(payload) == opened.st_size and len(payload) <= limit
             and (opened.st_dev, opened.st_ino, opened.st_size, opened.st_mtime_ns, opened.st_nlink)
             == (final.st_dev, final.st_ino, final.st_size, final.st_mtime_ns, final.st_nlink), "package file changed while reading")
    return payload


def _json(payload):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            _require(key not in result, "duplicate JSON key")
            result[key] = value
        return result
    def invalid(_):
        raise ValueError("nonfinite JSON number")
    try:
        result = json.loads(payload.decode("utf-8"), object_pairs_hook=unique, parse_constant=invalid)
    except (UnicodeError, RecursionError):
        raise ValueError("invalid package JSON") from None
    _canonical(result)
    return result


def verify_package(root):
    """Verify one extracted package; never extracts or executes any archive/code."""
    root = Path(root).absolute()
    for path in (root, *root.parents):
        _require(not path.is_symlink() and not getattr(path, "is_junction", lambda: False)(), "redirected package path")
    _require(root.is_dir(), "package root must be a directory")
    manifest = _json(_read_regular(root / "package-manifest.json", 65536))
    _object(manifest, {"schema_version", "files"}, "package manifest")
    _require(manifest["schema_version"] == "c01-reproduction-package-v1", "unsupported package schema")
    files = _object(manifest["files"], label="manifest files")
    for name, digest in files.items():
        _require(type(name) is str and name in PACKAGE_FILES and "\\" not in name
                 and PurePosixPath(name).as_posix() == name and not PurePosixPath(name).is_absolute()
                 and all(part not in {"", ".", ".."} for part in name.split("/")), "unsafe or unsupported package name")
        _sha(digest)
    _require(set(files) == PACKAGE_FILES, "package manifest has missing or extra members")
    found, payloads, total = set(), {}, 0
    def visit(directory, prefix=""):
        nonlocal total
        for path in directory.iterdir():
            name = prefix + path.name
            metadata = path.lstat()
            _require(not path.is_symlink() and not getattr(path, "is_junction", lambda: False)(), "redirected package member")
            if stat.S_ISDIR(metadata.st_mode):
                _require(name in {"source", "figures"}, "unexpected package directory")
                visit(path, name + "/")
            else:
                _require(name in PACKAGE_FILES or name == "package-manifest.json", "unexpected package member")
                if name == "package-manifest.json":
                    continue
                payload = _read_regular(path)
                total += len(payload)
                _require(total <= MAX_PACKAGE_BYTES, "package exceeds byte limit")
                _require(hashlib.sha256(payload).hexdigest() == files[name], "package checksum differs: " + name)
                found.add(name)
                payloads[name] = payload
    visit(root)
    _require(found == PACKAGE_FILES, "missing package file")
    research, reproduction = _json(payloads["research.json"]), _json(payloads["reproduction.json"])
    _object(reproduction, label="reproduction")
    code = b"".join(payloads["source/" + name + ".py"] for name in ("c01", "c01_loop", "knowledge", "c01_research"))
    _require(hashlib.sha256(code).hexdigest() == reproduction.get("analysis_code_sha256"), "bundled analysis code identity differs")
    report = validate_record(research, reproduction)
    report.update(package_files_checked=len(found), package_manifest_is_signature=False,
                  presentation_content_independently_verified=False)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", nargs="?", type=Path, default=Path(__file__).parent)
    args = parser.parse_args(argv)
    try:
        result = verify_package(args.root)
    except (ValueError, OSError, KeyError, TypeError, FloatingPointError, OverflowError) as error:
        print(json.dumps({"ok": False, "error": "verification_failed", "message": str(error)}, ensure_ascii=False))
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
