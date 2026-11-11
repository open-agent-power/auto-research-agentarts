"""A parent-MAE claim must use its paired parent, not a favorable mean reference."""
import copy
import unittest

from autoresearch.feature_comparison import compare_feature_checks
from autoresearch.research_design import _assessment
import test_input_basis_comparison as fixture


class InputBasisAssessmentTests(unittest.TestCase):
    def records(self):
        records = fixture.InputBasisComparisonTests().records()
        candidate = records[1]
        candidate["design_binding"]["resource"]["checks"] = ["group_cv"]
        candidate["summary"] = {"candidate_mae": 0.5, "reference_mae": 2.0, "improvement": 0.75, "n": 4, "group_count": 2}
        return records

    def assess(self, records, comparisons):
        candidate = records[1]
        return _assessment(candidate["design_binding"]["resource"], [candidate], {}, comparisons)

    def test_improvement_over_mean_does_not_support_a_worse_parent_comparison(self):
        records = self.records()
        for row, value in zip(records[1]["oof"], [0.0, 2.0, 3.0, 10.0]):
            row["predicted"] = value
        records[1]["summary"].update(candidate_mae=1.75, improvement=0.125)
        result = self.assess(records, compare_feature_checks(records))
        self.assertEqual(result["claim_scope"], "saved_parent_mae")
        self.assertIs(result["claim_supported"], False)
        self.assertEqual(result["parent_mae_comparisons"][0]["mae_change"], 0.25)
        self.assertFalse(result["scientific_validation"])

    def test_missing_or_incomparable_parent_stays_unknown_despite_mean_advantage(self):
        records = self.records()
        for comparisons in ([], compare_feature_checks([*records[:1], {**records[1], "source_snapshot_sha256": "b" * 64}])):
            with self.subTest(comparisons=comparisons):
                result = self.assess(records, comparisons)
                self.assertIsNone(result["claim_supported"])
                self.assertEqual(result["claim_scope"], "saved_parent_mae")

    def test_only_matching_candidate_actions_can_support_parent_claim(self):
        records = self.records()
        pairs = compare_feature_checks(records)
        result = self.assess(records, pairs)
        self.assertIs(result["claim_supported"], True)
        self.assertFalse(result["scientific_validation"])
        other = copy.deepcopy(pairs)
        other[0]["candidate_ref"]["action_id"] = "a-different-completed-action"
        self.assertIsNone(self.assess(records, other)["claim_supported"])


if __name__ == "__main__":
    unittest.main()
