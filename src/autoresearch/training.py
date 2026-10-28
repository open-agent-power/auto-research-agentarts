"""Real CPU fitting with scikit-learn, serializing numeric parameters as JSON."""

import hashlib
import time
from pathlib import Path
import numpy as np
import sklearn
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_squared_error
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import PolynomialFeatures, StandardScaler

from .contracts import Candidate, ResearchError
from .fixture import DATASET_ID
from . import datasets


def code_identity():
    names = ("contracts.py", "datasets.py", "fixture.py", "training.py")
    return hashlib.sha256(b"".join(name.encode() + b"\0" + Path(__file__).with_name(name).read_bytes()
                                   for name in names)).hexdigest()


def train(candidate: Candidate, dataset_id=DATASET_ID):
    started = time.perf_counter()
    data = datasets.descriptor(dataset_id)
    x, y = datasets.split_data(dataset_id, "train")
    vx, vy = datasets.split_data(dataset_id, "validation")
    model = make_pipeline(PolynomialFeatures(degree=candidate.degree, include_bias=False),
                          StandardScaler(), Ridge(alpha=candidate.alpha))
    model.fit(x, y)
    poly, scaler, ridge = model.steps[0][1], model.steps[1][1], model.steps[2][1]
    artifact = {
        "format": "polynomial-ridge-json-v1", "dataset_id": dataset_id,
        "evidence_type": data["evidence_type"], "candidate": candidate.to_dict(),
        "data_sha256": data["data_sha256"], "split_protocol": data["split_protocol"],
        "training_code_sha256": code_identity(),
        "powers": poly.powers_.tolist(), "mean": scaler.mean_.tolist(),
        "scale": scaler.scale_.tolist(), "coef": ridge.coef_.tolist(),
        "intercept": float(ridge.intercept_), "training_rows": len(y),
        "training_data_sha256": hashlib.sha256(x.tobytes() + y.tobytes()).hexdigest(),
        "libraries": {"numpy": np.__version__, "scikit-learn": sklearn.__version__},
    }
    pred = predict(artifact, vx)
    if not np.allclose(pred, model.predict(vx), rtol=1e-10, atol=1e-10):
        raise ResearchError("MODEL_EXPORT_FAILED", "JSON parameter reconstruction differs from trained model")
    mse = float(mean_squared_error(vy, pred))
    if not np.isfinite(mse):
        raise ResearchError("NONFINITE_METRIC", "training returned a nonfinite metric")
    return artifact, {"validation_mse": mse, "training_mse": float(mean_squared_error(y, predict(artifact, x))),
                      "num_features": int(len(ridge.coef_)), "training_seconds": time.perf_counter()-started}


def predict(artifact, x):
    if artifact["format"] != "polynomial-ridge-json-v1":
        raise ResearchError("INVALID_ARTIFACT", "unknown model format")
    powers = np.asarray(artifact["powers"], dtype=int)
    features = np.prod(np.asarray(x)[:, None, :] ** powers[None, :, :], axis=2)
    return ((features - np.asarray(artifact["mean"])) / np.asarray(artifact["scale"])) @ np.asarray(artifact["coef"]) + artifact["intercept"]


def terminal_evaluation(artifact):
    x, y = datasets.split_data(artifact["dataset_id"], "test")
    return {"test_mse": float(mean_squared_error(y, predict(artifact, x))), "test_rows": len(y)}
