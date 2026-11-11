"""One fixed raw-scale input basis, expanded before training-fold scaling."""

import numpy as np

from .contracts import ResearchError


def protocol(training):
    """Return explicit cubic metadata, or no additions for original direct inputs."""
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
    """Expand original x into x, x², x³ without fitting or modifying input values."""
    metadata = protocol(training)
    values = np.asarray(x, dtype=float)
    if not metadata:
        return values
    if values.ndim != 2 or values.shape[1] != 1:
        raise ResearchError("INVALID_TRAINING", "The fixed cubic basis consumes one original input column.")
    with np.errstate(over="ignore", invalid="ignore"):
        expanded = np.column_stack([values[:, 0] ** power for power in (1, 2, 3)])
    if not np.isfinite(expanded).all():
        raise ResearchError("INVALID_TRAINING", "Fixed cubic input powers exceed the finite numeric range; no fit was started.")
    return expanded
