"""Input profiles retain complete paired rows and expose local error structure."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

from autoresearch import tabular_quality_adapter as tabular
from autoresearch.contracts import ResearchError
from autoresearch.feature_comparison import compare_feature_checks
import test_feature_comparison as fixture


class PredictionProfileTests(unittest.TestCase):
    def source(self, records, speed=None, geometry=None):
        n = len(records[0]["oof"])
        root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        spec = {"schema_version": "tabular-quality-spec-v1", "file": "profiles.csv", "dataset_label": "Profile fixture",
                "source_url": "urn:test:profile", "license_note": "Synthetic test records", "sample_unit": "declared_record",
                "group_columns": ["signature"], "key_columns": [], "numeric_columns": ["geometry", "speed", "resistance"],
                "target_column": "resistance", "target_unit": "dimensionless", "missing_tokens": ["", "NA"],
                "delimiter": ",", "provenance": {"origin_sha256": "a" * 64, "description": "Synthetic records"}}
        speed = speed if speed is not None else [1, 1, 2, 2]
        geometry = geometry if geometry is not None else list(range(n))
        lines = ["geometry,speed,resistance,signature"]
        for index, row in enumerate(records[0]["oof"]):
            lines.append(",".join(map(str, [geometry[index], speed[index], row["observed"], row["groups"][0]])))
        (root / spec["file"]).write_text("\n".join(lines) + "\n", encoding="utf-8", newline="")
        (root / "spec.json").write_text(json.dumps(spec), encoding="utf-8")
        payload = tabular.capture_source(root)
        for record in records:
            record["source_snapshot_sha256"] = payload["snapshot_sha256"]
        return payload

    def test_exact_levels_describe_bias_and_paired_changes_without_mutation(self):
        records = fixture.FeatureComparisonTests().records()
        payload = self.source(records)
        original = copy.deepcopy((records, payload))
        comparison, = compare_feature_checks(records, payload)
        speed, geometry = comparison["input_profiles"]
        self.assertEqual((speed["column"], geometry["column"]), ("speed", "geometry"))
        self.assertEqual((speed["grouping"], speed["n"], speed["improved_rows"], speed["worsened_rows"], speed["tied_rows"]),
                         ("exact_values", 4, 3, 0, 1))
        first, last = speed["buckets"]
        self.assertEqual((first["logical_records"], last["logical_records"]), ([1, 2], [3, 4]))
        self.assertEqual((first["baseline_mae"], first["candidate_mae"], first["mae_change"]), (1.5, 0.5, -1.0))
        self.assertEqual((first["baseline_mean_error"], first["candidate_mean_error"]), (-0.5, -0.5))
        self.assertEqual((last["baseline_mean_error"], last["candidate_mean_error"]), (0.5, 0.5))
        self.assertEqual((first["baseline_negative_predictions"], first["candidate_negative_predictions"]), (1, 0))
        self.assertEqual((records, payload), original)

    def many_records(self, n):
        records = fixture.FeatureComparisonTests().records()
        for record in records:
            record["oof"] = [{"logical_record": index, "physical_line_end": index + 1, "observed": float(index),
                              "predicted": float(index) - 1, "groups": ["g" + str(index % 2)],
                              "fold": 1 if index % 2 else 2, "reference_prediction": 1.0} for index in range(1, n + 1)]
            record["folds"] = [{"fold": fold, "train_records": [index for index in range(1, n + 1) if (index % 2) != (fold % 2)],
                                "test_records": [index for index in range(1, n + 1) if (index % 2) == (fold % 2)],
                                "reference_prediction": 1.0, "model_params": {"alpha": 1.0}} for fold in (1, 2)]
        return records

    def test_many_levels_use_fixed_half_open_bins_covering_every_row(self):
        records = self.many_records(21)
        payload = self.source(records, list(range(21)), [5] * 21)
        comparison, = compare_feature_checks(records, payload)
        speed, geometry = comparison["input_profiles"]
        self.assertEqual(speed["grouping"], "equal_width")
        self.assertEqual([bucket["n"] for bucket in speed["buckets"]], [4, 4, 4, 4, 5])
        self.assertEqual(speed["buckets"][0]["label"], "[0.0, 4.0)")
        self.assertEqual(speed["buckets"][-1]["label"], "[16.0, 20.0]")
        self.assertEqual(sorted(index for bucket in speed["buckets"] for index in bucket["logical_records"]), list(range(1, 22)))
        self.assertEqual((geometry["grouping"], len(geometry["buckets"]), geometry["buckets"][0]["n"]), ("exact_values", 1, 21))
        for row in records[1]["oof"]:
            row["predicted"] = -1000.0
        changed, = compare_feature_checks(records, payload)
        self.assertEqual([(item["label"], item["logical_records"]) for item in changed["input_profiles"][0]["buckets"]],
                         [(item["label"], item["logical_records"]) for item in speed["buckets"]])

    def test_empty_bins_keep_zero_counts_and_undefined_means(self):
        records = self.many_records(18)
        payload = self.source(records, [*range(17), 1000], [0] * 18)
        comparison, = compare_feature_checks(records, payload)
        buckets = comparison["input_profiles"][0]["buckets"]
        self.assertEqual([bucket["n"] for bucket in buckets], [17, 0, 0, 0, 1])
        for bucket in buckets[1:4]:
            self.assertIsNone(bucket["baseline_mae"])
            self.assertIsNone(bucket["candidate_mean_error"])
            self.assertIsNone(bucket["mae_change"])
            self.assertEqual(bucket["logical_records"], [])
        json.dumps(comparison, allow_nan=False)

    def test_mismatched_evaluation_does_not_create_partial_profiles(self):
        records = fixture.FeatureComparisonTests().records()
        payload = self.source(records)
        records[1]["oof"].pop()
        result, = compare_feature_checks(records, payload)
        self.assertEqual(result["status"], "not_comparable")
        self.assertNotIn("input_profiles", result)

    def test_profiles_require_original_source_coordinates_and_targets(self):
        for key, value in (("source_snapshot_sha256", "b" * 64), ("physical_line_end", 99), ("observed", 99)):
            records = fixture.FeatureComparisonTests().records()
            payload = self.source(records)
            for record in records:
                (record if key == "source_snapshot_sha256" else record["oof"][0])[key] = value
            with self.subTest(key=key), self.assertRaises(ResearchError) as error:
                compare_feature_checks(records, payload)
            self.assertEqual(error.exception.code, "PROFILE_SOURCE_MISMATCH")


if __name__ == "__main__":
    unittest.main()
