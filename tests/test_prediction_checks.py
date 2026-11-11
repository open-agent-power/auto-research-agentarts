"""Hand-calculated checks for saved predictions, without model fitting."""
import json
import unittest

from autoresearch.prediction_checks import evaluate_prediction


class PredictionCheckTests(unittest.TestCase):
    def test_baseline_excludes_each_target_from_its_reference_mean(self):
        result = evaluate_prediction([0, 2, 4], [1, 2, 3])
        summary = result["summary"]
        self.assertEqual(result["schema_version"], "prediction-check-v1")
        self.assertAlmostEqual(summary["candidate_mae"], 2 / 3)
        self.assertAlmostEqual(summary["reference_mae"], 2)
        self.assertAlmostEqual(summary["improvement"], 2 / 3)
        self.assertTrue(summary["outperforms_reference"])
        self.assertEqual(summary["n"], 3)

    def test_group_reference_excludes_the_whole_group(self):
        result = evaluate_prediction([0, 2, 8, 10], [1, 3, 7, 9], groups=["A", "A", "B", "B"])
        self.assertAlmostEqual(result["summary"]["reference_mae"], 16 / 3)
        grouped = result["details"]["leave_group_out"]
        self.assertAlmostEqual(grouped["reference_mae"], 8)
        self.assertAlmostEqual(grouped["improvement"], 7 / 8)

    def test_grouped_retains_residual_direction_and_worst_group(self):
        result = evaluate_prediction([0, 2, 8, 10], [1, 3, 4, 6],
                                     groups=[("A",), ("A",), ("B",), ("B",)], check="grouped")
        summary, details = result["summary"], result["details"]
        self.assertAlmostEqual(summary["candidate_mae"], 2.5)
        self.assertAlmostEqual(summary["reference_mae"], 8)
        self.assertEqual([group["n"] for group in details["groups"]], [2, 2])
        self.assertEqual([group["mean_residual"] for group in details["groups"]], [1, -4])
        self.assertAlmostEqual(details["groups"][0]["improvement"], 7 / 8)
        self.assertAlmostEqual(details["groups"][1]["improvement"], 1 / 2)
        self.assertTrue(details["groups"][1]["outperforms_reference"])
        self.assertEqual(details["worst_group"]["group"], ("B",))
        self.assertAlmostEqual(details["worst_group"]["candidate_mae"], 4)
        self.assertAlmostEqual(details["worst_group_gap"], 1.5)
        json.dumps(result, allow_nan=False)

    def test_sample_sensitivity_recomputes_the_reference_and_detects_reversal(self):
        result = evaluate_prediction([0, 1, 2, 3], [0, 1, 2, 9], check="sensitivity")
        self.assertAlmostEqual(result["summary"]["improvement"], -0.125)
        details = result["details"]
        influential = details["most_influential"]
        self.assertEqual(details["unit_kind"], "row")
        self.assertEqual(influential["unit"], 4)
        self.assertAlmostEqual(influential["reference_mae"], 1)
        self.assertAlmostEqual(influential["candidate_mae"], 0)
        self.assertAlmostEqual(influential["improvement"], 1)
        self.assertTrue(influential["reverses_conclusion"])
        self.assertTrue(details["conclusion_reversed"])

    def test_group_sensitivity_removes_all_rows_of_each_unit(self):
        result = evaluate_prediction([0, 1, 2, 3], [0, 1, 2, 9],
                                     groups=["A", "A", "B", "C"], check="sensitivity")
        self.assertAlmostEqual(result["summary"]["improvement"], 0.1)
        influential = result["details"]["most_influential"]
        self.assertEqual(influential["unit"], "A")
        self.assertEqual(influential["removed_n"], 2)
        self.assertEqual(influential["remaining_n"], 2)
        self.assertAlmostEqual(influential["improvement"], -2)
        self.assertTrue(influential["reverses_conclusion"])

    def test_missing_nonfinite_and_missing_groups_remove_paired_rows(self):
        result = evaluate_prediction([0, None, 2, float("inf"), 4, 9],
                                     [1, 1, float("nan"), 3, 3, 9],
                                     groups=["A", "A", "A", "B", "B", None])
        summary = result["summary"]
        self.assertEqual((summary["n"], summary["excluded"]), (2, 4))
        self.assertEqual((summary["observed_n"], summary["predicted_n"]), (4, 5))
        self.assertEqual([item["row"] for item in result["details"]["exclusions"]], [2, 3, 4, 6])
        self.assertAlmostEqual(summary["candidate_mae"], 1)
        self.assertAlmostEqual(summary["reference_mae"], 4)
        json.dumps(result, allow_nan=False)

    def test_constant_targets_do_not_claim_relative_improvement(self):
        result = evaluate_prediction([3, 3, 3], [3, 4, 2])
        summary = result["summary"]
        self.assertEqual(summary["status"], "not_computable")
        self.assertEqual(summary["reason"], "constant_target")
        self.assertAlmostEqual(summary["candidate_mae"], 2 / 3)
        self.assertEqual(summary["reference_mae"], 0)
        self.assertIsNone(summary["improvement"])
        self.assertIsNone(summary["outperforms_reference"])

    def test_small_samples_and_single_group_retain_explicit_stop_reasons(self):
        cases = [([], [], None, "baseline", "insufficient_samples"),
                 ([2], [1], None, "sensitivity", "insufficient_samples"),
                 ([0, 2], [0, 2], ["A", "A"], "grouped", "insufficient_groups"),
                 ([0, 2], [0, 2], None, "grouped", "groups_required")]
        for observed, predicted, groups, check, reason in cases:
            with self.subTest(reason=reason):
                result = evaluate_prediction(observed, predicted, groups=groups, check=check)
                self.assertEqual(result["summary"]["status"], "not_computable")
                self.assertEqual(result["summary"]["reason"], reason)
                self.assertIsNone(result["summary"]["improvement"])
                json.dumps(result, allow_nan=False)

    def test_uncomputable_sensitivity_units_do_not_count_as_stable_evidence(self):
        result = evaluate_prediction([0, 2], [0, 2], groups=["A", "B"], check="sensitivity")
        details = result["details"]
        self.assertEqual(details["computable_units"], 0)
        self.assertIsNone(details["conclusion_reversed"])
        self.assertIsNone(details["most_influential"])

    def test_large_representable_values_remain_json_finite(self):
        result = evaluate_prediction([0, 1e300, 2e300], [1e299, 1e300, 1.9e300])
        self.assertAlmostEqual(result["summary"]["candidate_mae"] / 1e300, 1 / 15)
        self.assertAlmostEqual(result["summary"]["reference_mae"] / 1e300, 1)
        self.assertAlmostEqual(result["summary"]["improvement"], 14 / 15)
        json.dumps(result, allow_nan=False)
        with self.assertRaises(ValueError):
            evaluate_prediction([-1e308, 1e308], [1e308, -1e308])

    def test_large_offset_keeps_small_target_differences(self):
        result = evaluate_prediction([1e15, 1e15 + 2, 1e15 + 4],
                                     [1e15 + 1, 1e15 + 2, 1e15 + 3])
        self.assertAlmostEqual(result["summary"]["reference_mae"], 2)
        self.assertAlmostEqual(result["summary"]["improvement"], 2 / 3)

    def test_underflowing_reference_has_no_relative_comparison(self):
        result = evaluate_prediction([0, 0, 5e-324], [0, 0, 0])
        self.assertEqual(result["summary"]["status"], "not_computable")
        self.assertEqual(result["summary"]["reason"], "reference_mae_underflow")
        self.assertIsNone(result["summary"]["improvement"])
        json.dumps(result, allow_nan=False)

    def test_rejects_misalignment_unsupported_checks_and_nonnumeric_values(self):
        for observed, predicted, arguments in [([0], [], {}), ([0, 2], [0, 2], {"groups": ["A"]}),
                                                ([0, 2], [0, 2], {"check": "unknown"}),
                                                ([0, "invalid"], [0, 2], {}), ([False, 2], [0, 2], {})]:
            with self.subTest(observed=observed, arguments=arguments), self.assertRaises(ValueError):
                evaluate_prediction(observed, predicted, **arguments)


if __name__ == "__main__":
    unittest.main()
