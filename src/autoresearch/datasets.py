"""Allowlisted, local-only datasets with fixed provenance and holdout protocols."""

from functools import lru_cache
import gzip
import hashlib
from importlib import resources
import json
import re

import numpy as np

from .contracts import ResearchError
from . import fixture


STEELS_ID = "matbench-steels-v1"
STEELS_RAW_SHA256 = "473bc4957b2ea5e6465aef84bc29bb48ac34db27d69ea4ec5f508745c6fae252"
STEELS_ELEMENTS = ("Al", "C", "Co", "Cr", "Fe", "Mn", "Mo", "N", "Nb", "Ni", "Si", "Ti", "V", "W")
_SPLITS = ("train", "validation", "test")
_TOKEN = re.compile(r"([A-Z][a-z]?)([0-9]+(?:\.[0-9]*)?|\.[0-9]+)?")


def _validate_id(dataset_id):
    if not isinstance(dataset_id, str) or dataset_id not in (fixture.DATASET_ID, STEELS_ID):
        raise ResearchError("INVALID_REQUEST", "unknown dataset_id")


def descriptor(dataset_id):
    """Return a fresh, JSON-serializable description; never retrieve network data."""
    _validate_id(dataset_id)
    if dataset_id == fixture.DATASET_ID:
        digest = hashlib.sha256()
        for split in _SPLITS:
            x, y = fixture.split_data(split)
            for values in (x, y):
                digest.update(np.asarray(values, dtype="<f8").tobytes(order="C"))
        return {
            "dataset_id": fixture.DATASET_ID,
            "evidence_type": fixture.EVIDENCE_TYPE,
            "scientific_status": "engineering_only",
            "target": "synthetic_polynomial_response", "target_unit": "arbitrary",
            "raw_sha256": None, "data_sha256": digest.hexdigest(),
            "hash_kind": "generated_arrays",
            "hash_protocol": "train,validation,test; each X then y; little-endian float64 C-order bytes",
            "feature_names": ["x0", "x1"],
            "split_protocol": {
                "name": "original_fixture_independent_fixed_seeds_v1",
                "seeds": {"train": 731, "validation": 941, "test": 1151},
                "official_matbench_score": False,
            },
            "split_counts": {"train": 96, "validation": 32, "test": 32},
        }
    splits = _steels_splits()
    return {
        "dataset_id": STEELS_ID,
        "evidence_type": "public_materials_benchmark",
        "scientific_status": "benchmark_only",
        "target": "yield strength", "target_unit": "MPa",
        "raw_sha256": STEELS_RAW_SHA256, "data_sha256": STEELS_RAW_SHA256,
        "hash_kind": "raw_gzip", "raw_bytes": 8836,
        "feature_names": list(STEELS_ELEMENTS),
        "feature_transform": "positive formula amounts normalized to atomic fractions summing to one",
        "split_protocol": {
            "name": "project_composition_group_holdout_v1", "seed": 20261028,
            "group_key": "normalized fractions in feature_names order, rounded to 12 decimals",
            "allocation": "sorted groups, numpy default_rng permutation; floor(0.6*g), floor(0.2*g), remainder",
            "within_split_order": "original source row order",
            "uses_target_for_split": False, "official_matbench_score": False,
        },
        "split_counts": {split: len(splits[split][1]) for split in _SPLITS},
        "split_data_sha256": {
            split: hashlib.sha256(np.asarray(x, dtype="<f8").tobytes(order="C")
                                  + np.asarray(y, dtype="<f8").tobytes(order="C")).hexdigest()
            for split, (x, y) in splits.items()
        },
        "source_url": "https://ml.materialsproject.org/projects/matbench_steels.json.gz",
        "source_reference": "Citrine Informatics, Mechanical properties of some steels, dataset 153092",
        "original_source_url": "https://citrination.com/datasets/153092/",
        "license": "CC-BY-4.0",
        "license_url": "https://creativecommons.org/licenses/by/4.0/",
        "source_terms_url": "https://next-gen.materialsproject.org/about/mpcontribs-terms",
        "limitations": [
            "Custom project holdout, not the official Matbench five-fold protocol or leaderboard score.",
            "Composition-only inputs omit processing, heat treatment and microstructure conditions.",
            "Public benchmark engineering evidence; no biomedical or materials discovery claim.",
        ],
    }


def split_data(dataset_id, split):
    """Return independent numpy X/y copies for one fixed split."""
    _validate_id(dataset_id)
    if not isinstance(split, str) or split not in _SPLITS:
        raise ResearchError("INVALID_REQUEST", "unknown dataset split")
    if dataset_id == fixture.DATASET_ID:
        x, y = fixture.split_data(split)
    else:
        x, y = _steels_splits()[split]
    return x.copy(), y.copy()


def _integrity_error(message):
    return ResearchError("DATASET_INTEGRITY_ERROR", message)


def _parse_composition(formula):
    if not isinstance(formula, str) or not 1 <= len(formula) <= 512:
        raise _integrity_error("invalid steel composition")
    amounts = {}
    cursor = 0
    for match in _TOKEN.finditer(formula):
        element, value = match.groups()
        amount = float(value or 1)
        if (match.start() != cursor or element not in STEELS_ELEMENTS or element in amounts
                or not np.isfinite(amount) or amount <= 0):
            raise _integrity_error("unsupported steel composition")
        amounts[element] = amount
        cursor = match.end()
    if cursor != len(formula):
        raise _integrity_error("unparsed steel composition text")
    values = np.array([amounts.get(element, 0.0) for element in STEELS_ELEMENTS], dtype=np.float64)
    total = values.sum()
    if not np.isfinite(total) or total <= 0:
        raise _integrity_error("invalid steel composition total")
    return values / total


def _partition_indices(x):
    """Group only normalized composition features; targets are not an input."""
    groups = {}
    for index, row in enumerate(x):
        groups.setdefault(tuple(np.round(row, 12)), []).append(index)
    keys = sorted(groups)
    order = np.random.default_rng(20261028).permutation(len(keys))
    train_end = int(0.6 * len(keys))
    validation_end = train_end + int(0.2 * len(keys))
    selections = (order[:train_end], order[train_end:validation_end], order[validation_end:])
    return {
        split: np.array(sorted(index for group in selection for index in groups[keys[int(group)]]), dtype=int)
        for split, selection in zip(_SPLITS, selections)
    }


@lru_cache(maxsize=1)
def _steels_splits():
    try:
        raw = resources.files("autoresearch").joinpath("data", "matbench_steels.json.gz").read_bytes()
    except OSError as exc:
        raise _integrity_error("packaged steel dataset is unavailable") from exc
    if len(raw) != 8836 or hashlib.sha256(raw).hexdigest() != STEELS_RAW_SHA256:
        raise _integrity_error("steel dataset SHA256 or size differs from the fixed source")
    data = json.loads(gzip.decompress(raw))
    if (data.get("columns") != ["composition", "yield strength"]
            or data.get("index") != list(range(312)) or len(data.get("data", [])) != 312):
        raise _integrity_error("steel dataset schema or source order changed")
    x = np.stack([_parse_composition(row[0]) for row in data["data"]])
    y = np.array([row[1] for row in data["data"]], dtype=np.float64)
    if not np.isfinite(y).all():
        raise _integrity_error("nonfinite steel targets")
    splits = {}
    for split, indices in _partition_indices(x).items():
        sx, sy = x[indices], y[indices]
        sx.setflags(write=False)
        sy.setflags(write=False)
        splits[split] = (sx, sy)
    return splits
