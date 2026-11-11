"""Saved feature comparisons require matched rows, partitions and provenance."""

import copy
import unittest

from autoresearch.feature_comparison import compare_feature_checks


class FeatureComparisonTests(unittest.TestCase):
    def records(self):
        baseline = {"action_id": "six-feature-check", "check": "group_cv", "status": "completed",
                    "source_snapshot_sha256": "a" * 64, "target_column": "resistance", "target_unit": "dimensionless",
                    "design_binding": {"version": 1, "project_id": "fixture-project", "resource": {
                        "id": "feature-fixture", "version": 1, "parent_version": None,
                        "checks": ["random_cv", "group_cv", "negative_control"]}},
                    "protocol": {"splitter": "GroupKFold", "n_splits": 2, "shuffle": False, "random_state": None,
                                 "ridge_alpha": 1.0, "preprocessing": "StandardScaler.fit on training rows only",
                                 "reference": "training-fold target mean", "feature_columns": ["geometry", "speed"],
                                 "split_group_columns": ["signature"], "grouping_semantics": "operator-declared source columns"},
                    "oof": [{"logical_record": index, "physical_line_end": index + 1, "observed": float(index),
                             "predicted": prediction, "groups": ["g" + str((index - 1) // 2)],
                             "fold": 1 if index <= 2 else 2, "reference_prediction": 3.5 if index <= 2 else 1.5}
                            for index, prediction in enumerate([-1.0, 3.0, 2.0, 6.0], 1)],
                    "folds": [{"fold": 1, "train_records": [3, 4], "test_records": [1, 2], "reference_prediction": 3.5,
                               "model_params": {"alpha": 1.0, "fit_intercept": True}, "ridge_coefficients": [0.5, 2.0]},
                              {"fold": 2, "train_records": [1, 2], "test_records": [3, 4], "reference_prediction": 1.5,
                               "model_params": {"alpha": 1.0, "fit_intercept": True}, "ridge_coefficients": [1.0, 2.5]}]}
        candidate = copy.deepcopy(baseline)
        candidate["action_id"] = "speed-only-check"
        candidate["design_binding"].update(version=3)
        candidate["design_binding"]["resource"].update(version=2, parent_version=1)
        candidate["protocol"]["feature_columns"] = ["speed"]
        for row, prediction in zip(candidate["oof"], [0.0, 2.0, 4.0, 4.0]):
            row["predicted"] = prediction
        for fold in candidate["folds"]:
            fold["ridge_coefficients"] = [2.0]
        return [baseline, candidate]

    def test_matched_saved_predictions_report_error_change_without_clipping_or_mutation(self):
        records = self.records()
        before = copy.deepcopy(records)
        comparison, = compare_feature_checks(records)
        self.assertEqual(comparison, {
            "schema_version": "feature-comparison-v1", "check": "group_cv", "status": "comparable",
            "baseline_ref": {"action_id": "six-feature-check", "design_version": 1, "resource_id": "feature-fixture",
                             "resource_version": 1, "feature_columns": ["geometry", "speed"]},
            "candidate_ref": {"action_id": "speed-only-check", "design_version": 3, "resource_id": "feature-fixture",
                              "resource_version": 2, "feature_columns": ["speed"]},
            "matched_rows": 4, "metrics": {"baseline_mae": 1.5, "candidate_mae": 0.5, "mae_change": -1.0,
                                           "relative_improvement": 1 - 0.5 / 1.5,
                                           "baseline_negative_predictions": 1, "candidate_negative_predictions": 0},
            "reason_codes": [], "scientific_validation": False})
        comparison["baseline_ref"]["feature_columns"].append("cannot-mutate-original")
        self.assertEqual(records, before)

    def test_reordered_rows_folds_and_partition_members_are_equivalent(self):
        records = self.records()
        expected = compare_feature_checks(records)
        records[1]["oof"].reverse()
        records[1]["folds"].reverse()
        for fold in records[1]["folds"]:
            fold["train_records"].reverse()
            fold["test_records"].reverse()
        before = copy.deepcopy(records)
        self.assertEqual(compare_feature_checks(records), expected)
        self.assertEqual(records, before)

    def test_mismatches_do_not_emit_comparison_metrics(self):
        cases = {
            "SOURCE_SNAPSHOT_MISMATCH": lambda item: item.update(source_snapshot_sha256="b" * 64),
            "PROJECT_MISMATCH": lambda item: item["design_binding"].update(project_id="another-project"),
            "TARGET_MISMATCH": lambda item: item.update(target_column="another-target"),
            "TARGET_UNIT_MISMATCH": lambda item: item.update(target_unit="another-unit"),
            "PROTOCOL_MISMATCH": lambda item: item["protocol"].update(random_state=17),
            "ROW_COVERAGE_MISMATCH": lambda item: item["oof"].pop(),
            "ROW_COORDINATES_MISMATCH": lambda item: item["oof"][0].update(physical_line_end=99),
            "OBSERVED_MISMATCH": lambda item: item["oof"][0].update(observed=5.0),
            "GROUPS_MISMATCH": lambda item: item["oof"][0].update(groups=["different-signature"]),
            "FOLD_ASSIGNMENT_MISMATCH": lambda item: item["oof"][0].update(fold=2),
            "REFERENCE_PREDICTION_MISMATCH": lambda item: item["oof"][0].update(reference_prediction=99.0),
            "FOLD_RECORDS_MISMATCH": lambda item: item["folds"][0].update(train_records=[2, 4]),
            "MODEL_PARAMETERS_MISMATCH": lambda item: item["folds"][0]["model_params"].update(alpha=2.0),
            "DUPLICATE_OOF_RECORD": lambda item: item["oof"].append(copy.deepcopy(item["oof"][0])),
            "DUPLICATE_FOLD_RECORD": lambda item: item["folds"].append(copy.deepcopy(item["folds"][0])),
            "DUPLICATE_SPLIT_RECORD": lambda item: item["folds"][0]["train_records"].append(3),
            "EMPTY_OOF": lambda item: item.update(oof=[]),
        }
        for reason, change in cases.items():
            with self.subTest(reason=reason):
                records = self.records()
                change(records[1])
                before = copy.deepcopy(records)
                result, = compare_feature_checks(records)
                self.assertEqual(result["status"], "not_comparable")
                self.assertIn(reason, result["reason_codes"])
                self.assertNotIn("metrics", result)
                self.assertFalse(result["scientific_validation"])
                self.assertEqual(records, before)

    def test_zero_baseline_mae_keeps_absolute_change_and_has_no_relative_improvement(self):
        records = self.records()
        for row in records[0]["oof"]:
            row["predicted"] = row["observed"]
        comparison, = compare_feature_checks(records)
        self.assertEqual(comparison["status"], "comparable")
        self.assertEqual(comparison["metrics"]["baseline_mae"], 0.0)
        self.assertEqual(comparison["metrics"]["mae_change"], 0.5)
        self.assertIsNone(comparison["metrics"]["relative_improvement"])

    def test_only_explicit_same_family_parent_and_check_pairs_are_compared(self):
        for change in (lambda item: item["design_binding"]["resource"].update(parent_version=None),
                       lambda item: item["design_binding"]["resource"].update(parent_version=7),
                       lambda item: item["design_binding"]["resource"].update(id="unrelated-resource"),
                       lambda item: item["design_binding"]["resource"].update(checks=["baseline"]),
                       lambda item: item.update(check="random_cv"),
                       lambda item: item.update(status="failed")):
            records = self.records()
            change(records[1])
            self.assertEqual(compare_feature_checks(records), [])
        records = self.records()
        for item in records:
            item["check"] = "random_cv"
            item["protocol"].update(splitter="KFold", shuffle=True, random_state=11)
        self.assertEqual(compare_feature_checks(records)[0]["check"], "random_cv")

    def test_group_only_child_is_the_same_raw_family_and_compares_with_its_parent(self):
        records = self.records()
        records[1]["design_binding"]["resource"]["checks"] = ["group_cv"]
        result, = compare_feature_checks(records)
        self.assertEqual(result["status"], "comparable")
        self.assertEqual(result["check"], "group_cv")


if __name__ == "__main__":
    unittest.main()
