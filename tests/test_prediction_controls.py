"""Saved-pair controls distinguish alignment from unchanged value distributions."""
import json
import unittest

from autoresearch.prediction_controls import evaluate_negative_control


class PredictionControlTests(unittest.TestCase):
    def test_matching_predictions_separate_from_within_group_repairings(self):
        observed = list(range(20))
        result = evaluate_negative_control(observed, observed, groups=["A"] * 10 + ["B"] * 10)
        self.assertEqual(result["summary"]["original_mae"], 0)
        self.assertEqual(result["summary"]["conditional_rank"], 0.005)
        self.assertTrue(result["summary"]["alignment_supported"])
        self.assertEqual(len(result["shuffled_mae"]), 199)
        self.assertTrue(all(group["summary"]["alignment_supported"] for group in result["per_group"]))
        self.assertEqual(result, evaluate_negative_control(observed, observed, groups=["A"] * 10 + ["B"] * 10))
        json.dumps(result, allow_nan=False)

    def test_shifted_pairings_lose_record_level_support(self):
        result = evaluate_negative_control(list(range(20)), list(range(19, -1, -1)), groups=["A"] * 20)
        self.assertFalse(result["summary"]["alignment_supported"])
        self.assertGreater(result["summary"]["conditional_rank"], 0.05)

    def test_group_constant_predictions_cannot_claim_pairing_information(self):
        result = evaluate_negative_control([0, 1, 2, 10, 11, 12], [1, 1, 1, 11, 11, 11],
                                           groups=["A"] * 3 + ["B"] * 3)
        self.assertEqual(result["summary"]["conditional_rank"], 1)
        self.assertIsNone(result["summary"]["alignment_supported"])
        self.assertEqual(result["summary"]["reason"], "no_reordering_information")

    def test_singleton_groups_are_explicitly_uninformative(self):
        result = evaluate_negative_control([0, 1, 2], [0, 1, 2], groups=["A", "B", "C"])
        self.assertEqual(result["summary"]["status"], "not_computable")
        self.assertIsNone(result["summary"]["alignment_supported"])

    def test_pair_mask_retains_original_rows_and_drops_missing_group(self):
        result = evaluate_negative_control([0, None, 2, float("inf"), 4, 5], [0, 1, 2, 3, 4, 5],
                                           groups=[("A",), ("A",), ("A",), ("B",), None, ("B",)])
        self.assertEqual((result["summary"]["n"], result["summary"]["excluded"]), (3, 3))
        self.assertEqual([item["row"] for item in result["exclusions"]], [2, 4, 5])
        self.assertEqual([item["rows"] for item in result["per_group"]], [[1, 3], [6]])
        json.dumps(result, allow_nan=False)

    def test_rejects_candidate_selected_protocol_and_misalignment(self):
        for arguments in ({"seed": 12}, {"repeats": 99}, {"groups": ["A"]}):
            options = {"groups": ["A", "A"], **arguments}
            with self.subTest(options=options), self.assertRaises(ValueError):
                evaluate_negative_control([0, 1], [0, 1], **options)


if __name__ == "__main__":
    unittest.main()
