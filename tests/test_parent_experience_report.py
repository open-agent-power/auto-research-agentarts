"""Display both saved-case outcomes without fitting or treating analogy as evidence."""

import copy
import unittest
from unittest.mock import patch

from autoresearch.project_report import _experience_comparison_lines, _experience_rows


class ParentExperienceReportTests(unittest.TestCase):
    def setUp(self):
        for estimator in ("StandardScaler", "Ridge"):
            self.enterContext(patch("autoresearch.ridge_validation_adapter." + estimator + ".fit",
                                    side_effect=AssertionError("Case presentation must not fit estimators")))

    @staticmethod
    def case(paired=True):
        """Saved-value presentation fixture; no source project or new research result."""
        case = {"case_id": "saved-age-case", "case_version": 1, "inclusion_status": "active",
                "origin_evidence": {"project_id": "original-project", "action_id": "candidate-check",
                                    "producer_code_identity": "b" * 64},
                "source_scope": {"target_column": "strength", "target_unit": "MPa"},
                "observation": {"numerical_summary": {
                    "n": 1030, "excluded": 0, "candidate_mae": 5.5, "reference_mae": 13.0,
                    "negative_predictions": 2, "observed_min": 2.0, "observed_max": 82.0,
                    "predicted_min": -2.5, "predicted_max": 83.0}}}
        if not paired:
            return case
        case["origin_evidence"].update(parent_action_id="parent-check", parent_producer_code_identity="a" * 64)
        baseline = {"action_id": "parent-check", "design_version": 1, "resource_id": "saved-age",
                    "resource_version": 1, "feature_columns": ["cement", "age"],
                    "input_basis": {"kind": "raw", "source_columns": ["cement", "age"]},
                    "model_input_terms": ["cement", "age"]}
        candidate = {**copy.deepcopy(baseline), "action_id": "candidate-check", "design_version": 2,
                     "resource_version": 2,
                     "input_basis": {"kind": "log1p", "source_columns": ["cement", "age"],
                                     "transformed_columns": ["age"]},
                     "model_input_terms": ["cement", "log1p(age)"]}
        case["observation"]["saved_parent_comparison"] = {
            "schema_version": "feature-comparison-v1", "status": "comparable", "comparison_kind": "fixed_input_basis",
            "baseline_ref": baseline, "candidate_ref": candidate, "matched_rows": 1030,
            "metrics": {"baseline_mae": 8.0, "candidate_mae": 5.5, "mae_change": -2.5,
                        "relative_improvement": 0.3125, "baseline_negative_predictions": 0,
                        "candidate_negative_predictions": 2},
            "row_summary": {"n": 1030, "improved_rows": 712, "worsened_rows": 318, "tied_rows": 0},
            "group_summary": {"group_count": 427, "improved_groups": 296, "worsened_groups": 131, "tied_groups": 0},
            "prediction_ranges": {
                "baseline": {"predicted_min": 9.0, "predicted_max": 79.0, "negative_predictions": 0,
                             "below_observed_min": 0, "above_observed_max": 0},
                "candidate": {"predicted_min": -2.5, "predicted_max": 83.0, "negative_predictions": 2,
                              "below_observed_min": 5, "above_observed_max": 1}},
            "reason_codes": [], "scientific_validation": False}
        return case

    def test_parent_improvement_keeps_worse_rows_groups_and_new_negative_predictions(self):
        case = self.case()
        before = copy.deepcopy(case)
        output = "\n".join(_experience_comparison_lines(case))
        for value in ("父版本MAE 8，候选MAE 5.5", "候选−父版本 -2.5", "相对误差降低 31.25%",
                      "712 改善、318 恶化、0 持平（共 1030 行）", "296 改善、131 恶化、0 持平（共 427 组）",
                      "父版预测 9 至 79；负预测 0", "候选预测 -2.5 至 83；负预测 2",
                      "低于／高于原观察范围 5／1", "不是本项目的结果", "不能据此确认本项目收益或科学结论"):
            self.assertIn(value, output)
        self.assertEqual(case, before)

    def test_parent_reference_is_distinct_from_training_mean_and_retains_both_producers(self):
        case = self.case()
        observation = _experience_rows({"experience_cases": [case]})[0][3]
        output = "\n".join(_experience_comparison_lines(case))
        self.assertIn("训练均值参考 MAE 13", observation)
        self.assertIn("父版本MAE 8", output)
        self.assertNotIn("父版本MAE 13", output)
        for value in ("行动 parent-check", "行动 candidate-check", "父版生产代码：" + "a" * 64,
                      "候选生产代码：" + "b" * 64):
            self.assertIn(value, output)

    def test_saved_mapping_and_model_terms_are_printed_without_reconstructing_design(self):
        case = self.case()
        with patch("autoresearch.input_basis.protocol", side_effect=AssertionError("Use saved model terms")):
            output = "\n".join(_experience_comparison_lines(case))
        for value in ("父版本保存的模型输入项：cement、age", "候选版本保存的模型输入项：cement、log1p(age)",
                      "固定log1p变换：age → log1p(age)", "输入维数不变"):
            self.assertIn(value, output)

    def test_undefined_relative_change_and_no_declared_groups_are_not_invented(self):
        case = self.case()
        comparison = case["observation"]["saved_parent_comparison"]
        comparison["metrics"]["relative_improvement"] = None
        comparison["group_summary"] = None
        output = "\n".join(_experience_comparison_lines(case))
        self.assertIn("相对误差降低 未计算", output)
        self.assertNotIn("按声明组 MAE", output)
        self.assertIn("318 恶化", output)

    def test_single_case_keeps_original_summary_and_has_no_invented_parent(self):
        case = self.case(paired=False)
        self.assertEqual(_experience_comparison_lines(case), [])
        self.assertEqual(_experience_rows({"experience_cases": [case]}), [[
            "saved-age-case v1", "用于后续参考", "original-project / candidate-check；原目标 strength，单位 MPa",
            "评价 1030 行；排除 0；MAE 5.5；训练均值参考 MAE 13；负预测 2；观察范围 2 至 82；预测范围 -2.5 至 83"]])


if __name__ == "__main__":
    unittest.main()
