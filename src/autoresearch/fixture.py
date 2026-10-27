"""Public mathematical engineering fixture; not biomedical or materials evidence.

The fixed split is an execution test, not a secret scientific benchmark. The
controller receives validation results; the terminal test is evaluated on finalize.
"""

import numpy as np

DATASET_ID = "engineering-polynomial-v1"
EVIDENCE_TYPE = "synthetic_engineering_fixture"


def split_data(split):
    if split not in {"train", "validation", "test"}:
        raise ValueError("unknown split")
    seed = {"train": 731, "validation": 941, "test": 1151}[split]
    count = {"train": 96, "validation": 32, "test": 32}[split]
    rng = np.random.default_rng(seed)
    x = rng.uniform(-2, 2, (count, 2))
    y = 2 + 1.5*x[:, 0] - .5*x[:, 1] + 2.2*x[:, 0]*x[:, 1] + .7*x[:, 0]**2
    y = y + rng.normal(0, .05, count)
    return x, y
