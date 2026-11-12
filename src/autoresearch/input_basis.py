"""Explicit fixed raw-input mappings, applied before training-fold scaling."""

import numpy as np

from .contracts import ResearchError


def protocol(training):
    """Describe the declared fixed mapping, or no additions for direct inputs."""
    if "input_transforms" in training:
        columns, transforms = training["feature_columns"], training["input_transforms"]
        if ("input_basis" in training or type(columns) is not list or not columns
                or any(type(name) is not str or not name for name in columns)
                or len(set(columns)) != len(columns) or type(transforms) is not dict or not transforms
                or any(type(name) is not str or name not in columns or function != "log1p"
                       for name, function in transforms.items())):
            raise ResearchError("INVALID_TRAINING", "Declare log1p for explicit selected raw input columns, without another input basis.")
        selected = [name for name in columns if name in transforms]
        return {"input_basis": {"kind": "log1p", "source_columns": list(columns), "transformed_columns": selected,
                                "order": "raw_log1p_then_fold_standardization"},
                "model_input_terms": ["log1p(" + name + ")" if name in transforms else name for name in columns]}
    if "input_basis" not in training:
        return {}
    columns = training["feature_columns"]
    if (training["input_basis"] != "univariate_cubic" or type(columns) is not list
            or len(columns) != 1 or type(columns[0]) is not str or not columns[0]):
        raise ResearchError("INVALID_TRAINING", "The fixed univariate_cubic basis requires exactly one original numeric input column.")
    name = columns[0]
    return {"input_basis": {"kind": "univariate_cubic", "source_columns": [name], "powers": [1, 2, 3],
                            "include_bias": False, "order": "raw_powers_then_fold_standardization"},
            "model_input_terms": [name, name + "^2", name + "^3"]}


def expand(x, training):
    """Apply the fixed mapping without fitting or modifying original inputs."""
    metadata = protocol(training)
    values = np.asarray(x, dtype=float)
    if not metadata:
        return values
    if metadata["input_basis"]["kind"] == "log1p":
        columns = training["feature_columns"]
        if values.ndim != 2 or values.shape[1] != len(columns):
            raise ResearchError("INVALID_TRAINING", "The fixed log1p mapping consumes the declared original input columns.")
        selected = [index for index, name in enumerate(columns) if name in training["input_transforms"]]
        raw = values[:, selected]
        if not (np.isfinite(raw).all() and (raw > -1).all()):
            raise ResearchError("INVALID_TRAINING", "Every complete-case log1p input must be finite and greater than -1; no fit was started.")
        expanded = values.copy()
        with np.errstate(over="ignore", invalid="ignore", divide="ignore"):
            expanded[:, selected] = np.log1p(raw)
        if not np.isfinite(expanded).all():
            raise ResearchError("INVALID_TRAINING", "Fixed log1p inputs exceed the finite numeric range; no fit was started.")
        return expanded
    if values.ndim != 2 or values.shape[1] != 1:
        raise ResearchError("INVALID_TRAINING", "The fixed cubic basis consumes one original input column.")
    with np.errstate(over="ignore", invalid="ignore"):
        expanded = np.column_stack([values[:, 0] ** power for power in (1, 2, 3)])
    if not np.isfinite(expanded).all():
        raise ResearchError("INVALID_TRAINING", "Fixed cubic input powers exceed the finite numeric range; no fit was started.")
    return expanded
