"""Raw-data resource assessments keep split comparison and control scope explicit."""

import unittest

from autoresearch.research_design import RAW_RESOURCE, _assessment
from autoresearch.project_report import _design_rows, _raw_validation_lines


class RawDesignCatalogTests(unittest.TestCase):
    def checks(self, grouped=0.2, rank=0.005):
        return [
            {"check": "random_cv", "summary": {"n": 20, "candidate_mae": 2.0, "reference_mae": 4.0,
                "improvement": 0.5, "status": "computed"}},
            {"check": "group_cv", "summary": {"n": 20, "candidate_mae": 3.0, "reference_mae": 3.75,
                "improvement": grouped, "status": "computed"}},
            {"check": "negative_control", "summary": {"n": 20, "status": "computed",
                "conditional_rank": rank, "alignment_supported": rank <= 0.05}},
        ]

    def test_raw_design_requires_all_checks_and_retains_split_comparison(self):
        missing = _assessment(RAW_RESOURCE, self.checks()[:1], {"group_columns": ["batch"]})
        self.assertEqual(missing["missing_checks"], ["group_cv", "negative_control"])
        result = _assessment(RAW_RESOURCE, self.checks(), {"group_columns": ["batch"]})
        self.assertTrue(result["claim_supported"])
        self.assertEqual(result["comparison"]["group_to_random_mae_ratio"], 1.5)
        self.assertFalse(result["scientific_validation"])

    def test_unfavorable_group_split_or_control_does_not_approve_claim(self):
        for checks in (self.checks(grouped=-0.2), self.checks(rank=0.7)):
            self.assertFalse(_assessment(RAW_RESOURCE, checks, {"group_columns": ["batch"]})["claim_supported"])

    def test_unknown_control_cannot_be_treated_as_success(self):
        checks = self.checks()
        checks[-1]["summary"].update(status="not_computable", conditional_rank=None, alignment_supported=None)
        self.assertIsNone(_assessment(RAW_RESOURCE, checks, {"group_columns": ["batch"]})["claim_supported"])

    def test_report_supports_raw_fields_and_records_adverse_metrics(self):
        binding = {"resource": RAW_RESOURCE, "version": 1, "target_column": "observed",
                   "prediction_column": None, "reason": "Question requires unseen groups",
                   "training": {"feature_columns": ["x"], "split_group_columns": ["batch"], "fit_limit": 20}}
        self.assertIn(["原CSV输入列", "x"], _design_rows({"design_revisions": [binding]}))
        checks = self.checks(grouped=-0.2, rank=0.7)
        checks[-1]["summary"].update(excluded=0, original_mae=3.0, permutation_median=2.5,
            permutation_p05=1.0, permutation_p95=4.0)
        checks[-1]["protocol"] = {"seed": 11, "repeats": 199}
        for check in checks[:2]:
            check["summary"]["excluded"] = 0
            check["protocol"] = {}
            check["oof"] = []
        for check in checks:
            check["design_binding"] = binding
        report = {"action_results": [{"status": "completed", "action_id": item["check"],
            "tool_result": {"result": {"analysis": item}}} for item in checks]}
        lines = "\n".join(_raw_validation_lines(report))
        for text in ("-20%", "0.7", "199", "未见组/随机划分MAE比 1.5", "不证明总体显著性"):
            self.assertIn(text, lines)
        checks[0]["design_binding"] = {**binding, "version": 2}
        self.assertNotIn("未见组/随机划分MAE比", "\n".join(_raw_validation_lines(report)))


if __name__ == "__main__":
    unittest.main()
