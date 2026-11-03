"""Audit five sealed steel-model predictions; never fit, execute code or use a network."""
import copy
import hashlib
from importlib import resources
import json
import math
from pathlib import Path
import re

import numpy as np

from . import datasets, training
from .contracts import ResearchError, canonical, fingerprint

TOOL_ID = "materials.saved-steel-audit"
ADAPTER_VERSION = "1"
CAMPAIGN_ID = "91765be348a14699845aeacb773fe12b"
MAX_PACKET_BYTES = 8_000_000
SOURCE_SCHEMA = "materials-saved-steel-source-v1"
RESULT_SCHEMA = "materials-saved-steel-audit-result-v1"


def _require(condition, code, message):
    if not condition:
        raise ResearchError(code, message)


def _finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def _object(pairs):
    value = {}
    for key, item in pairs:
        _require(key not in value, "INVALID_SOURCE_JSON", "Duplicate JSON member.")
        value[key] = item
    return value


def _parse(raw):
    def reject(value):
        raise ValueError("Nonfinite JSON: " + value)
    return json.loads(raw, object_pairs_hook=_object, parse_constant=reject)


def _read(path):
    for part in (path, *path.parents):
        _require(not part.is_symlink() and not getattr(part, "is_junction", lambda: False)(),
                 "UNSAFE_PATH", "Source paths cannot redirect through links.")
    _require(path.is_file() and 0 < path.stat().st_size <= MAX_PACKET_BYTES,
             "MISSING_SOURCE", "A bounded sealed source file is required.")
    return path.read_bytes()


def _dataset():
    raw = resources.files("autoresearch").joinpath("data", "matbench_steels.json.gz").read_bytes()
    _require(len(raw) == 8836 and hashlib.sha256(raw).hexdigest() == datasets.STEELS_RAW_SHA256,
             "DATASET_INTEGRITY_ERROR", "Bundled steel data differs from the frozen source.")
    return datasets.descriptor(datasets.STEELS_ID)


def _scope(state, descriptor):
    return {"dataset_id": datasets.STEELS_ID, "target": "yield strength", "unit": "MPa",
            "metric": "MSE", "metric_unit": "MPa^2", "sample_unit": "composition_record",
            "data_sha256": descriptor["data_sha256"],
            "split_protocol": copy.deepcopy(descriptor["split_protocol"]),
            "split_counts": copy.deepcopy(descriptor["split_counts"]),
            "evaluation": copy.deepcopy(state["protocol"]), "source_campaign_id": state["campaign_id"],
            "source_state_sha256": fingerprint(state), "official_matbench_score": False}


def _validate(payload):
    _require(type(payload) is dict and set(payload) == {"schema_version", "state", "models", "source_state_sha256",
                "source_export", "scope", "evidence_purpose", "snapshot_sha256"}
             and payload.get("schema_version") == SOURCE_SCHEMA
             and payload.get("snapshot_sha256") == fingerprint({k: v for k, v in payload.items() if k != "snapshot_sha256"}),
             "EVIDENCE_CHANGED", "Steel source snapshot changed.")
    origin = payload["source_export"]
    _require(origin["name"] == "exports/" + CAMPAIGN_ID + ".json"
             and type(origin["sha256"]) is str and re.fullmatch(r"[a-f0-9]{64}", origin["sha256"])
             and type(origin["bytes"]) is int and 0 < origin["bytes"] <= MAX_PACKET_BYTES
             and payload["evidence_purpose"] == "saved_prediction_audit_not_new_fit_or_scientific_evidence",
             "INVALID_SOURCE", "Complete original export identity and audit purpose are required.")
    state, descriptor = payload["state"], _dataset()
    _require(state["campaign_id"] == CAMPAIGN_ID and state["status"] == "finalized"
             and state["dataset_id"] == datasets.STEELS_ID
             and payload["source_state_sha256"] == fingerprint(state),
             "UNSUPPORTED_SCOPE", "The sealed five-candidate R3 steel campaign is required.")
    for key in ("data_sha256", "raw_sha256", "target", "target_unit", "feature_names",
                "split_protocol", "split_counts", "split_data_sha256"):
        _require(state["dataset"][key] == descriptor[key], "DATASET_INTEGRITY_ERROR", "Saved dataset protocol differs: " + key)
    _require(state["protocol"] == {"direction": "minimize", "id": "materials-composition-holdout-v1",
                                   "metric": "validation_mse", "min_relative_gain": .01},
             "UNSUPPORTED_SCOPE", "The original validation-MSE and one-percent adoption gate are required.")
    _require(payload["scope"] == _scope(state, descriptor), "EVIDENCE_CHANGED", "Steel scope or units changed.")
    trials, entries = state["trials"], payload["models"]
    _require(type(trials) is list and len(trials) == 5 and type(entries) is list and len(entries) == 5
             and sorted(t["ordinal"] for t in trials) == [1, 2, 3, 4, 5],
             "INVALID_SOURCE", "Exactly five ordered trials and their saved JSON models are required.")
    by_id = {entry["trial_id"]: entry for entry in entries}
    _require(len(by_id) == 5 and set(by_id) == {trial["id"] for trial in trials},
             "EVIDENCE_CHANGED", "Model and trial identities differ.")
    for trial in trials:
        _require(type(trial["id"]) is str and re.fullmatch(r"[a-f0-9]{32}", trial["id"]),
                 "INVALID_SOURCE", "A frozen hexadecimal trial identity is required.")
        entry, candidate = by_id[trial["id"]], trial["candidate"]
        model = entry["model"]
        raw = canonical(model).encode("utf-8")
        source_name = CAMPAIGN_ID + "/" + trial["id"] + ".model.json"
        _require(trial["model_artifact"] == entry["source_name"] == source_name
                 and hashlib.sha256(raw).hexdigest() == entry["sha256"] == trial["model_sha256"]
                 and entry["bytes"] == len(raw), "EVIDENCE_CHANGED", "Saved model bytes or binding changed.")
        _require(candidate == model["candidate"] and candidate["degree"] in (1, 2)
                 and _finite(candidate["alpha"]) and candidate["alpha"] >= 0
                 and model["format"] == "polynomial-ridge-json-v1" and model["dataset_id"] == datasets.STEELS_ID
                 and model["data_sha256"] == descriptor["data_sha256"]
                 and model["split_protocol"] == descriptor["split_protocol"]
                 and model["training_data_sha256"] == descriptor["split_data_sha256"]["train"]
                 and model["training_rows"] == descriptor["split_counts"]["train"]
                 and model["training_code_sha256"] == trial["training_code_sha256"],
                 "EVIDENCE_CHANGED", "Model data, training version or candidate scope changed.")
        width = 14 if candidate["degree"] == 1 else 119
        _require(all(type(model[key]) is list and len(model[key]) == width for key in ("powers", "mean", "scale", "coef"))
                 and all(type(row) is list and len(row) == 14 and all(type(v) is int and 0 <= v <= 2 for v in row)
                         and 1 <= sum(row) <= candidate["degree"] for row in model["powers"])
                 and all(_finite(v) for key in ("mean", "scale", "coef") for v in model[key])
                 and all(v > 0 for v in model["scale"]) and _finite(model["intercept"])
                 and all(_finite(trial["metrics"][key]) and trial["metrics"][key] >= 0
                         for key in ("training_mse", "validation_mse")),
                 "INVALID_SOURCE", "Saved numeric model parameters or metrics are invalid.")
    final = state["final_evaluation"]
    _require(state["best_trial_id"] in by_id and final["best_trial_id"] == state["best_trial_id"]
             and final["model_sha256"] == by_id[state["best_trial_id"]]["sha256"]
             and final["dataset_id"] == datasets.STEELS_ID and final["data_sha256"] == descriptor["data_sha256"]
             and final["test_rows"] == descriptor["split_counts"]["test"] and _finite(final["test_mse"]),
             "EVIDENCE_CHANGED", "Original selected baseline and terminal evaluation are required.")


def _checked(payload):
    try:
        _validate(payload)
    except ResearchError:
        raise
    except (KeyError, TypeError, ValueError, OverflowError, RecursionError, OSError):
        raise ResearchError("INVALID_SOURCE", "Malformed or unavailable saved steel source.") from None


def code_identity() -> str:
    return hashlib.sha256(Path(__file__).read_bytes() + Path(training.__file__).read_bytes()
                          + Path(datasets.__file__).read_bytes()).hexdigest()


def capture_source(campaign_directory) -> dict:
    """Host-only registration from a trusted directory, never an execution parameter."""
    try:
        root = Path(campaign_directory).absolute()
        path = root / "exports" / (CAMPAIGN_ID + ".json")
        exported_raw = _read(path)
        exported = _parse(exported_raw)
        state = exported["state"]
        _require(exported["state_sha256"] == fingerprint(state), "EVIDENCE_CHANGED", "Frozen export state hash differs.")
        models, originals = [], {path: exported_raw}
        for trial in state["trials"]:
            _require(type(trial["id"]) is str and re.fullmatch(r"[a-f0-9]{32}", trial["id"]),
                     "UNSAFE_PATH", "Unexpected saved trial identity.")
            name = CAMPAIGN_ID + "/" + trial["id"] + ".model.json"
            _require(trial["model_artifact"] == name and "/" not in trial["id"] and "\\" not in trial["id"],
                     "UNSAFE_PATH", "Unexpected saved model path.")
            model_path = root / CAMPAIGN_ID / (trial["id"] + ".model.json")
            raw = _read(model_path)
            _require(hashlib.sha256(raw).hexdigest() == trial["model_sha256"], "EVIDENCE_CHANGED", "Saved model hash differs.")
            originals[model_path] = raw
            models.append({"trial_id": trial["id"], "source_name": name, "sha256": trial["model_sha256"],
                           "bytes": len(raw), "model": _parse(raw)})
        payload = {"schema_version": SOURCE_SCHEMA, "state": state, "models": models,
                   "source_state_sha256": exported["state_sha256"],
                   "source_export": {"name": "exports/" + CAMPAIGN_ID + ".json", "sha256": hashlib.sha256(exported_raw).hexdigest(),
                                     "bytes": len(exported_raw)}, "scope": _scope(state, _dataset()),
                   "evidence_purpose": "saved_prediction_audit_not_new_fit_or_scientific_evidence"}
        payload["snapshot_sha256"] = fingerprint(payload)
        _checked(payload)
        _require(all(_read(name) == raw for name, raw in originals.items()), "EVIDENCE_CHANGED", "Sealed source changed during capture.")
        return payload
    except ResearchError:
        raise
    except (KeyError, TypeError, ValueError, OverflowError, RecursionError, OSError):
        raise ResearchError("INVALID_SOURCE", "Cannot capture the sealed steel campaign.") from None


def load_source(raw: bytes) -> dict:
    _require(type(raw) is bytes and 0 < len(raw) <= MAX_PACKET_BYTES, "INVALID_SOURCE", "A bounded steel source packet is required.")
    try:
        payload = _parse(raw)
        _checked(payload)
        return payload
    except ResearchError:
        raise
    except (ValueError, TypeError, RecursionError):
        raise ResearchError("INVALID_SOURCE_JSON", "Invalid steel source JSON.") from None


def execute(payload, dimension=None) -> dict:
    _require(dimension is None, "INVALID_REQUEST", "Steel audit has no P02 grouping dimension.")
    _checked(payload)
    try:
        state = payload["state"]
        models = {entry["trial_id"]: entry["model"] for entry in payload["models"]}
        splits = {name: datasets.split_data(datasets.STEELS_ID, name) for name in ("train", "validation", "test")}
        rows, observations, metrics, retained, retained_mse = [], [], [], None, None
        evidence = {"source_snapshot_sha256": payload["snapshot_sha256"], "source_campaign_id": CAMPAIGN_ID,
                    "data_sha256": payload["scope"]["data_sha256"], "source_state_sha256": payload["source_state_sha256"]}
        for trial in sorted(state["trials"], key=lambda item: item["ordinal"]):
            scores, differences = {}, {}
            for name, metric_name in (("train", "training_mse"), ("validation", "validation_mse")):
                x, y = splits[name]
                predictions = training.predict(models[trial["id"]], x)
                _require(np.isfinite(predictions).all(), "INVALID_RESULT", "Nonfinite saved-model predictions.")
                value = math.fsum((float(a) - float(b)) ** 2 for a, b in zip(y, predictions)) / len(y)
                expected = trial["metrics"][metric_name]
                _require(math.isclose(value, expected, rel_tol=1e-10, abs_tol=1e-8),
                         "EVIDENCE_CHANGED", "Saved steel MSE differs from prediction recomputation.")
                scores[metric_name], differences[metric_name] = value, value - expected
                metrics.append({"name": metric_name, "value": value, "unit": "MPa^2", "endpoint": "yield strength",
                                "n": len(y), "sample_unit": "composition_record", "split": name,
                                "trial_id": trial["id"], "comparator": retained,
                                "evaluation": copy.deepcopy(state["protocol"])})
            accepted = retained_mse is None or scores["validation_mse"] < retained_mse * .99
            decision = "accepted" if accepted else "rejected"
            _require(decision == trial["status"], "EVIDENCE_CHANGED", "Original one-percent adoption decision differs.")
            row = {"trial_id": trial["id"], "candidate": copy.deepcopy(trial["candidate"]), "metrics": scores,
                   "saved_metrics": {key: trial["metrics"][key] for key in scores}, "mse_differences": differences,
                   "comparator_trial_id": retained, "one_percent_threshold_mse": retained_mse * .99 if retained_mse is not None else None,
                   "relative_gain": 1 - scores["validation_mse"] / retained_mse if retained_mse else None,
                   "decision": decision, "model_sha256": trial["model_sha256"]}
            rows.append(row)
            observations.append({"producer": TOOL_ID, "kind": "saved_steel_mse_audit", "endpoint": "yield strength",
                                 "unit": "MPa^2", "sample_unit": "composition_record",
                                 "sample_counts": {"train": len(splits["train"][1]), "validation": len(splits["validation"][1])},
                                 "comparator": retained, "values": copy.deepcopy(row), "evidence_refs": [copy.deepcopy(evidence)],
                                 "interpretation_status": "numeric_audit_not_scientific_approval"})
            if accepted:
                retained, retained_mse = trial["id"], scores["validation_mse"]
        _require(retained == state["best_trial_id"], "EVIDENCE_CHANGED", "Audit changed the retained baseline.")
        x, y = splits["test"]
        predictions = training.predict(models[retained], x)
        test_mse = math.fsum((float(a) - float(b)) ** 2 for a, b in zip(y, predictions)) / len(y)
        _require(math.isclose(test_mse, state["final_evaluation"]["test_mse"], rel_tol=1e-10, abs_tol=1e-8),
                 "EVIDENCE_CHANGED", "Original baseline test result differs.")
        metrics.append({"name": "test_mse", "value": test_mse, "unit": "MPa^2", "endpoint": "yield strength",
                        "n": len(y), "sample_unit": "composition_record", "split": "test", "trial_id": retained,
                        "comparator": "original_already_selected_baseline", "candidate_reranking": False})
        result = {"schema_version": RESULT_SCHEMA, "source_snapshot_sha256": payload["snapshot_sha256"],
                  "scope": copy.deepcopy(payload["scope"]), "trials": rows, "retained_trial_id": retained,
                  "baseline_only_test_check": {"trial_id": retained, "test_mse": test_mse, "n": len(y), "reranked": False},
                  "new_fits": 0, "scientific_validation": False}
        return {"schema_version": RESULT_SCHEMA, "tool_id": TOOL_ID, "adapter_version": ADAPTER_VERSION,
                "status": "completed", "observations": observations, "metrics": metrics,
                "evidence_refs": [evidence], "result": result, "failure": None,
                "new_fits": 0, "model_calls": 0, "scientific_validation": False}
    except ResearchError:
        raise
    except (KeyError, TypeError, ValueError, IndexError, OverflowError, ZeroDivisionError):
        raise ResearchError("INVALID_RESULT", "Saved steel model prediction audit failed.") from None


def next_decision(result) -> dict:
    try:
        _require(result["tool_id"] == TOOL_ID and result["status"] == "completed"
                 and result["new_fits"] == 0 and result["scientific_validation"] is False,
                 "INVALID_RESULT", "A completed steel prediction audit is required.")
        audited = result["result"]
        rows = audited["trials"]
        _require(audited["schema_version"] == RESULT_SCHEMA and len(rows) == 5
                 and audited["retained_trial_id"] == rows[0]["trial_id"]
                 and rows[0]["candidate"]["degree"] == 1 and all(row["decision"] == "rejected" for row in rows[1:]),
                 "INVALID_RESULT", "Expected the verified retained linear baseline and four rejected candidates.")
        return {"policy_ref": {"id": "materials.saved-steel-audit", "version": ADAPTER_VERSION},
                "project_status": "waiting", "next_action": {"method_id": "research.source-selection", "kind": "evidence_task",
                    "execution_status": "not_executed", "required_evidence": [
                        "加工与热处理条件的原始记录", "与组成记录可对应的微结构信息", "可比的独立外部验证来源"]},
                "reason": "保存模型的五方案MSE和1%采用门槛已复核。三个二阶方案未改善验证MSE，另一线性方案的改善未达到原门槛；保留原线性基线，先补加工、热处理与微结构来源，不继续刷交互参数。此结论只适用于当前固定划分。",
                "retained_trial_id": audited["retained_trial_id"], "feedback": copy.deepcopy(rows),
                "source_snapshot_sha256": audited["source_snapshot_sha256"],
                "evidence_refs": copy.deepcopy(result["evidence_refs"]), "scientific_validation": False,
                "user_value_evaluated": False, "new_fits": 0}
    except ResearchError:
        raise
    except (KeyError, TypeError, ValueError, IndexError):
        raise ResearchError("INVALID_RESULT", "Malformed saved steel audit feedback.") from None
