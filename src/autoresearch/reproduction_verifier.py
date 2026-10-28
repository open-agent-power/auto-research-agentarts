"""Standalone, standard-library-only verification of saved validation predictions.

Copied into the reproduction archive as verify_results.py. It never fits a model.
"""
import csv
import hashlib
import json
import math
from pathlib import Path


def verify(root):
    root = Path(root).resolve()
    manifest = json.loads((root / "package-manifest.json").read_text(encoding="utf-8"))
    if manifest["version"] != "validation-reproduction-v1":
        raise ValueError("unsupported package version")
    for name, digest in manifest["files"].items():
        path = (root / name).resolve()
        if not path.is_relative_to(root) or not path.is_file():
            raise ValueError("missing or unsafe package path")
        if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise ValueError("package checksum differs: " + name)
    project = json.loads((root / "project.json").read_text(encoding="utf-8"))
    with (root / "evidence/validation.csv").open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    features = project["dataset"]["feature_names"]
    results = []
    for trial in project["trials"]:
        if not trial.get("model_artifact"):
            continue
        trial_id = trial["id"]
        if len(trial_id) != 32 or any(c not in "0123456789abcdef" for c in trial_id):
            raise ValueError("invalid trial id")
        model_path = root / "evidence/models" / (trial_id + ".json")
        payload = model_path.read_bytes()
        if hashlib.sha256(payload).hexdigest() != trial["model_sha256"]:
            raise ValueError("model differs from original experiment record")
        model = json.loads(payload)
        if model["format"] != "polynomial-ridge-json-v1":
            raise ValueError("unsupported numeric model")
        lengths = [len(model[k]) for k in ("powers", "mean", "scale", "coef")]
        if len(set(lengths)) != 1 or not lengths[0] or any(len(p) != len(features) for p in model["powers"]):
            raise ValueError("inconsistent model dimensions")
        predictions = []
        for row in rows:
            values = [float(row[key]) for key in features]
            terms = [math.prod(v ** exponent for v, exponent in zip(values, power)) for power in model["powers"]]
            predicted = sum((term - mean) / scale * coef for term, mean, scale, coef in
                            zip(terms, model["mean"], model["scale"], model["coef"])) + model["intercept"]
            if not math.isfinite(predicted):
                raise ValueError("nonfinite prediction")
            predictions.append(predicted)
        mse = sum((float(row["target"]) - p) ** 2 for row, p in zip(rows, predictions)) / len(rows)
        expected = trial["metrics"]["validation_mse"]
        if not math.isclose(mse, expected, rel_tol=1e-9, abs_tol=1e-6):
            raise ValueError("recomputed validation MSE differs: " + trial_id)
        if trial_id == project["metrics"]["best_trial_id"]:
            with (root / "evidence/predictions.csv").open(encoding="utf-8", newline="") as stream:
                exported = list(csv.DictReader(stream))
            if len(exported) != len(rows) or any(
                not math.isclose(float(saved["observed"]), float(row["target"]), rel_tol=1e-12, abs_tol=1e-9)
                or not math.isclose(float(saved["predicted"]), actual, rel_tol=1e-9, abs_tol=1e-6)
                for saved, row, actual in zip(exported, rows, predictions)
            ):
                raise ValueError("figure predictions differ from the retained model")
        results.append({"trial_id": trial_id, "validation_mse": mse, "rows": len(rows)})
    if len(results) != project["metrics"]["trials"]:
        raise ValueError("trial count differs")
    return {"ok": True, "scope": "saved validation inference and file integrity only",
            "training_performed": False, "network_used": False, "trials": results}


if __name__ == "__main__":
    try:
        print(json.dumps(verify(Path(__file__).parent), ensure_ascii=False, indent=2))
    except (ValueError, KeyError, OSError, ZeroDivisionError, OverflowError) as exc:
        raise SystemExit("Verification failed: " + str(exc))
