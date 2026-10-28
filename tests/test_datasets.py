import gzip
import hashlib
from importlib import resources
import json
from pathlib import Path
import unittest
from unittest.mock import patch

import numpy as np

from autoresearch import datasets, fixture
from autoresearch.contracts import ResearchError


ENGINEERING_ID = "engineering-polynomial-v1"
STEELS_ID = "matbench-steels-v1"
SPLITS = ("train", "validation", "test")
RAW_SHA256 = "473bc4957b2ea5e6465aef84bc29bb48ac34db27d69ea4ec5f508745c6fae252"


class DatasetTests(unittest.TestCase):
    def tearDown(self):
        datasets._steels_splits.cache_clear()

    def test_original_fixture_is_unchanged_and_wrapped_exactly(self):
        fixture_source = Path(fixture.__file__).read_bytes()
        self.assertEqual(hashlib.sha256(fixture_source).hexdigest(),
                         "8099abb4e24b02631af23491137e2c742cbfda1447c782a97a6f6bd694140878")
        for split in SPLITS:
            expected_x, expected_y = fixture.split_data(split)
            x, y = datasets.split_data(ENGINEERING_ID, split)
            np.testing.assert_array_equal(x, expected_x)
            np.testing.assert_array_equal(y, expected_y)
        info = datasets.descriptor(ENGINEERING_ID)
        self.assertIsNone(info["raw_sha256"])
        self.assertEqual(info["hash_kind"], "generated_arrays")
        self.assertEqual(info["data_sha256"],
                         "b56e07c75ad77af15f158b0cecd9aba8cd26cdd499ff374705c98d79b8922206")
        self.assertEqual(info["split_counts"], {"train": 96, "validation": 32, "test": 32})

    def test_fixed_official_bytes_and_complete_composition_parsing(self):
        raw = resources.files("autoresearch").joinpath("data", "matbench_steels.json.gz").read_bytes()
        self.assertEqual(len(raw), 8836)
        self.assertEqual(hashlib.sha256(raw).hexdigest(), RAW_SHA256)
        data = json.loads(gzip.decompress(raw))
        self.assertEqual(data["columns"], ["composition", "yield strength"])
        self.assertEqual(data["index"], list(range(312)))
        self.assertEqual(len(data["data"]), 312)
        parsed = np.stack([datasets._parse_composition(row[0]) for row in data["data"]])
        self.assertEqual(parsed.shape, (312, 14))
        self.assertTrue(np.isfinite(parsed).all())
        self.assertTrue(((parsed >= 0) & (parsed <= 1)).all())
        np.testing.assert_allclose(parsed.sum(axis=1), 1, rtol=0, atol=1e-14)
        np.testing.assert_array_equal(datasets._parse_composition("Fe2C1"),
                                      datasets._parse_composition("C2Fe4"))
        np.testing.assert_allclose(parsed[0, datasets.STEELS_ELEMENTS.index("Fe")],
                                   0.620 / 1.0000576, rtol=0, atol=1e-14)

    def test_holdout_counts_hashes_bounds_and_no_composition_overlap(self):
        expected_hashes = {
            "train": "a5cc31202b2345702ea8aa08991aeab7c1c653d5e64121d9a401e1ee076c0048",
            "validation": "fe6456433216e34b74f1598b76967b83a6dae885a36317cc5922c3094c47bb90",
            "test": "b25f3a0b08df0de699493fb1c83cbcd6c780b34f6fbe4998c4f6bd1a387c34df",
        }
        info = datasets.descriptor(STEELS_ID)
        self.assertEqual(info["split_counts"], {"train": 187, "validation": 62, "test": 63})
        self.assertEqual(info["split_data_sha256"], expected_hashes)
        groups = []
        for split in SPLITS:
            x, y = datasets.split_data(STEELS_ID, split)
            self.assertEqual(x.shape, (info["split_counts"][split], 14))
            self.assertTrue(np.isfinite(x).all() and np.isfinite(y).all())
            self.assertTrue(((x >= 0) & (x <= 1)).all())
            self.assertTrue(((y >= 1005.9) & (y <= 2510.3)).all())
            digest = hashlib.sha256(x.astype("<f8").tobytes() + y.astype("<f8").tobytes()).hexdigest()
            self.assertEqual(digest, expected_hashes[split])
            groups.append({tuple(row) for row in np.round(x, 12)})
        self.assertEqual(len(set.union(*groups)), 312)
        for left, right in ((0, 1), (0, 2), (1, 2)):
            self.assertFalse(groups[left] & groups[right])

    def test_equivalent_compositions_stay_in_one_group(self):
        rows = []
        for amount in range(1, 21):
            rows.extend((datasets._parse_composition(f"Fe{amount}C1"),
                         datasets._parse_composition(f"C2Fe{amount * 2}")))
        partitions = datasets._partition_indices(np.stack(rows))
        assignment = {int(index): split for split, indices in partitions.items() for index in indices}
        self.assertEqual(set(assignment), set(range(40)))
        for index in range(0, 40, 2):
            self.assertEqual(assignment[index], assignment[index + 1])

    def test_arrays_and_descriptors_are_independent_copies(self):
        for dataset_id in (ENGINEERING_ID, STEELS_ID):
            for split in SPLITS:
                x, y = datasets.split_data(dataset_id, split)
                expected_x, expected_y = x.copy(), y.copy()
                x[:] = -999
                y[:] = -999
                actual_x, actual_y = datasets.split_data(dataset_id, split)
                np.testing.assert_array_equal(actual_x, expected_x)
                np.testing.assert_array_equal(actual_y, expected_y)
            info = datasets.descriptor(dataset_id)
            info["feature_names"].append("bad")
            info["split_counts"]["train"] = -1
            self.assertNotIn("bad", datasets.descriptor(dataset_id)["feature_names"])
            self.assertGreater(datasets.descriptor(dataset_id)["split_counts"]["train"], 0)

    def test_allowlist_and_parser_reject_invalid_inputs(self):
        for value in ("unknown", "../matbench_steels", None, [], 1, True):
            for call in (lambda v=value: datasets.descriptor(v),
                         lambda v=value: datasets.split_data(v, "train")):
                with self.assertRaises(ResearchError) as ctx:
                    call()
                self.assertEqual(ctx.exception.code, "INVALID_REQUEST")
        for split in ("all", "Train", "", None, [], True):
            with self.assertRaises(ResearchError) as ctx:
                datasets.split_data(STEELS_ID, split)
            self.assertEqual(ctx.exception.code, "INVALID_REQUEST")
        for formula in ("", "Fe-1", "Fe1???", "(FeC)2", "Fe1e3", "U1", "Fe0", "Fe1Fe1", "9" * 513, None):
            with self.assertRaises(ResearchError) as ctx:
                datasets._parse_composition(formula)
            self.assertEqual(ctx.exception.code, "DATASET_INTEGRITY_ERROR")

    def test_descriptors_are_json_safe_and_keep_evidence_boundary(self):
        for dataset_id, evidence, status in (
            (ENGINEERING_ID, "synthetic_engineering_fixture", "engineering_only"),
            (STEELS_ID, "public_materials_benchmark", "benchmark_only"),
        ):
            info = datasets.descriptor(dataset_id)
            json.dumps(info, allow_nan=False)
            self.assertEqual(info["evidence_type"], evidence)
            self.assertEqual(info["scientific_status"], status)
            self.assertFalse(info["split_protocol"]["official_matbench_score"])
        info = datasets.descriptor(STEELS_ID)
        self.assertEqual(info["raw_sha256"], RAW_SHA256)
        self.assertEqual(info["data_sha256"], RAW_SHA256)
        self.assertEqual(info["hash_kind"], "raw_gzip")
        self.assertEqual(info["target_unit"], "MPa")

    def test_corrupted_resource_fails_before_decompression(self):
        datasets._steels_splits.cache_clear()
        with patch("autoresearch.datasets.resources.files") as files:
            files.return_value.joinpath.return_value.read_bytes.return_value = b"not the fixed data"
            with self.assertRaises(ResearchError) as ctx:
                datasets.split_data(STEELS_ID, "train")
        self.assertEqual(ctx.exception.code, "DATASET_INTEGRITY_ERROR")


if __name__ == "__main__":
    unittest.main()
