"""A declared basis contrast changes only raw single-column versus fixed cubic input."""
import copy
import unittest

from autoresearch import input_basis
from autoresearch.feature_comparison import compare_feature_checks
import test_feature_comparison as fixture


class InputBasisComparisonTests(unittest.TestCase):
    def records(self):
        records = fixture.FeatureComparisonTests().records()
        for record in records:
            record["protocol"]["feature_columns"] = ["speed"]
            record["design_binding"]["training"] = {
                "feature_columns": ["speed"], "split_group_columns": ["signature"], "fit_limit": 30}
        candidate = records[1]
        candidate["design_binding"]["resource"]["comparison_kind"] = "fixed_input_basis"
        candidate["design_binding"]["training"].update(input_basis="univariate_cubic", fit_limit=40)
        candidate["protocol"].update(input_basis.protocol(candidate["design_binding"]["training"]))
        return records

    def test_declared_basis_contrast_reports_actual_changed_inputs_and_keeps_results_immutable(self):
        records = self.records()
        before = copy.deepcopy(records)
        comparison, = compare_feature_checks(records)
        self.assertEqual(comparison["status"], "comparable")
        self.assertEqual(comparison["comparison_kind"], "fixed_input_basis")
        self.assertEqual(comparison["changed_protocol_fields"], ["input_basis", "model_input_terms"])
        self.assertEqual(comparison["baseline_ref"]["input_basis"], {"kind": "raw", "source_columns": ["speed"]})
        self.assertEqual(comparison["baseline_ref"]["model_input_terms"], ["speed"])
        self.assertEqual(comparison["candidate_ref"]["model_input_terms"], ["speed", "speed^2", "speed^3"])
        self.assertEqual(comparison["metrics"]["mae_change"], -1.0)
        self.assertFalse(comparison["scientific_validation"])
        self.assertEqual(records, before)

    def test_transform_difference_without_declared_contrast_remains_incomparable(self):
        records = self.records()
        del records[1]["design_binding"]["resource"]["comparison_kind"]
        result, = compare_feature_checks(records)
        self.assertEqual(result["status"], "not_comparable")
        self.assertIn("PROTOCOL_MISMATCH", result["reason_codes"])
        self.assertNotIn("metrics", result)

    def test_declaration_does_not_allow_other_protocols_or_unrecorded_basis_terms(self):
        changes = [lambda item: item["protocol"].update(ridge_alpha=2.0),
                   lambda item: item["protocol"].update(preprocessing="standardize before powers"),
                   lambda item: item["protocol"]["input_basis"].update(powers=[1, 3, 2]),
                   lambda item: item["protocol"]["input_basis"].update(include_bias=True),
                   lambda item: item["protocol"]["input_basis"].update(source_columns=["geometry"]),
                   lambda item: item["protocol"].update(model_input_terms=["speed", "speed^3", "speed^2"]),
                   lambda item: item["protocol"].pop("model_input_terms"),
                   lambda item: item["protocol"].update(feature_columns=["geometry"]),
                   lambda item: item["design_binding"]["training"].pop("input_basis")]
        for index, change in enumerate(changes):
            with self.subTest(change=index):
                records = self.records()
                change(records[1])
                result, = compare_feature_checks(records)
                self.assertEqual(result["status"], "not_comparable")
                self.assertIn("PROTOCOL_MISMATCH", result["reason_codes"])
                self.assertNotIn("metrics", result)

    def test_basis_declaration_keeps_all_evaluation_and_model_parameter_gates(self):
        changes = {"SOURCE_SNAPSHOT_MISMATCH": lambda item: item.update(source_snapshot_sha256="b" * 64),
                   "ROW_COVERAGE_MISMATCH": lambda item: item["oof"].pop(),
                   "ROW_COORDINATES_MISMATCH": lambda item: item["oof"][0].update(physical_line_end=20),
                   "OBSERVED_MISMATCH": lambda item: item["oof"][0].update(observed=100.0),
                   "GROUPS_MISMATCH": lambda item: item["oof"][0].update(groups=["another"]),
                   "FOLD_ASSIGNMENT_MISMATCH": lambda item: item["oof"][0].update(fold=2),
                   "FOLD_RECORDS_MISMATCH": lambda item: item["folds"][0].update(train_records=[2, 4]),
                   "REFERENCE_PREDICTION_MISMATCH": lambda item: item["oof"][0].update(reference_prediction=9.0),
                   "MODEL_PARAMETERS_MISMATCH": lambda item: item["folds"][0]["model_params"].update(alpha=2.0)}
        for reason, change in changes.items():
            with self.subTest(reason=reason):
                records = self.records()
                change(records[1])
                result, = compare_feature_checks(records)
                self.assertEqual(result["status"], "not_comparable")
                self.assertIn(reason, result["reason_codes"])
                self.assertNotIn("metrics", result)


if __name__ == "__main__":
    unittest.main()
