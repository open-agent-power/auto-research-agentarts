"""Report fixed log1p mappings from saved declarations and OOF evidence, with no fits."""

import copy
import unittest
from unittest.mock import patch

from autoresearch import input_basis
from autoresearch.project_report import _design_rows, _feature_comparison_lines, _raw_validation_lines
from autoresearch.research_design import RAW_RESOURCE


class Log1pReportTests(unittest.TestCase):
    def setUp(self):
        for estimator in ("StandardScaler", "Ridge"):
            self.enterContext(patch("autoresearch.ridge_validation_adapter." + estimator + ".fit",
                                    side_effect=AssertionError("Report presentation must not fit estimators")))

    @staticmethod
    def binding(training):
        return {"resource": copy.deepcopy(RAW_RESOURCE), "version": 2, "target_column": "strength",
                "prediction_column": None, "reason": "Compare a declared age transform",
                "training": {"feature_columns": ["cement", "age"], "split_group_columns": ["mix"],
                             "fit_limit": 40, **training}}

    def analysis(self, check="group_cv", **training):
        binding = self.binding(training)
        return {"check": check, "design_binding": binding,
                "summary": {"n": 2, "excluded": 0, "candidate_mae": 1.0, "reference_mae": 2.0,
                            "improvement": 0.5, "group_count": 1},
                "protocol": {"feature_columns": binding["training"]["feature_columns"],
                             **input_basis.protocol(binding["training"])},
                "oof": [{"observed": 2.0, "predicted": -1.0}, {"observed": 4.0, "predicted": 3.0}],
                "folds": []}

    @staticmethod
    def report(analysis):
        return {"action_results": [{"status": "completed", "action_id": "saved-ridge-check",
                                    "tool_result": {"result": {"analysis": analysis}}}]}

    def comparison(self, **training):
        binding = self.binding(training)
        columns = binding["training"]["feature_columns"]
        baseline = {"design_version": 1, "resource_id": "age-transform", "resource_version": 1,
                    "feature_columns": columns, "action_id": "raw-check",
                    "input_basis": {"kind": "raw", "source_columns": columns}, "model_input_terms": columns}
        candidate = {**copy.deepcopy(baseline), "design_version": 2, "resource_version": 2,
                     "action_id": "log-check", **input_basis.protocol(binding["training"])}
        return {"baseline_ref": baseline, "candidate_ref": candidate, "comparison_kind": "fixed_input_basis",
                "status": "comparable", "matched_rows": 2, "reason_codes": [],
                "metrics": {"baseline_mae": 2.0, "candidate_mae": 1.0, "mae_change": -1.0,
                            "relative_improvement": 0.5, "baseline_negative_predictions": 1,
                            "candidate_negative_predictions": 0}}

    def test_bound_design_names_original_columns_selected_transforms_and_actual_model_terms(self):
        state = {"design_revisions": [self.binding({"input_transforms": {"age": "log1p"}})]}
        before = copy.deepcopy(state)
        rows = dict(_design_rows(state))
        self.assertEqual(rows["原CSV输入列"], "cement、age")
        self.assertEqual(rows["模型输入项"], "cement、log1p(age)")
        for expected in ("固定log1p变换", "age → log1p(age)", "其余原CSV列直接输入", "输入维数不变",
                         "先按原尺度变换", "各训练折内拟合标准化", "x > -1"):
            self.assertIn(expected, rows["固定输入映射"])
        self.assertNotIn("三次", rows["固定输入映射"])
        self.assertEqual(state, before)

    def test_multiple_transform_columns_follow_training_feature_order(self):
        rows = dict(_design_rows({"design_revisions": [self.binding({
            "input_transforms": {"age": "log1p", "cement": "log1p"}})]}))
        self.assertEqual(rows["模型输入项"], "log1p(cement)、log1p(age)")
        self.assertIn("cement → log1p(cement)、age → log1p(age)", rows["固定输入映射"])

    def test_oof_report_reads_saved_protocol_without_recomputing_mapping_or_changing_predictions(self):
        for check in ("random_cv", "group_cv"):
            with self.subTest(check=check):
                report = self.report(self.analysis(check, input_transforms={"age": "log1p"}))
                before = copy.deepcopy(report)
                with patch.object(input_basis, "protocol", side_effect=AssertionError("Read saved protocol only")):
                    output = "\n".join(_raw_validation_lines(report))
                for expected in ("原CSV输入列：cement、age", "固定log1p变换：age → log1p(age)",
                                 "保存的模型输入项：cement、log1p(age)", "x > -1", "各训练折内拟合标准化",
                                 "负预测 1/2", "未裁剪预测或变换目标"):
                    self.assertIn(expected, output)
                self.assertNotIn("三次", output)
                self.assertEqual(report, before)

    def test_paired_report_distinguishes_raw_parent_from_fixed_log1p_candidate(self):
        comparison = self.comparison(input_transforms={"age": "log1p"})
        report = {"feature_comparisons": [comparison]}
        before = copy.deepcopy(report)
        with patch.object(input_basis, "protocol", side_effect=AssertionError("Read saved comparison only")):
            output = "\n".join(_feature_comparison_lines(report))
        for expected in ("父版本输入映射：直接输入", "候选版本输入映射：固定log1p变换：age → log1p(age)",
                         "父版本保存的模型输入项：cement、age", "候选版本保存的模型输入项：cement、log1p(age)",
                         "输入维数不变", "输入尺度及有效正则化随之改变", "候选−父版本 -1"):
            self.assertIn(expected, output)
        self.assertNotIn("三次", output)
        self.assertNotIn("原单列输入", output)
        self.assertEqual(report, before)

    def test_incomparable_log1p_pair_keeps_mapping_and_reason_without_scores(self):
        comparison = self.comparison(input_transforms={"age": "log1p"})
        comparison.update(status="not_comparable", reason_codes=["FOLD_ASSIGNMENT_MISMATCH"])
        del comparison["metrics"]
        output = "\n".join(_feature_comparison_lines({"feature_comparisons": [comparison]}))
        self.assertIn("候选版本保存的模型输入项：cement、log1p(age)", output)
        self.assertIn("FOLD_ASSIGNMENT_MISMATCH", output)
        self.assertIn("未生成误差比较成绩", output)
        self.assertNotIn("父版本MAE", output)

    def test_raw_and_cubic_report_copy_remains_unchanged_and_does_not_claim_log1p(self):
        raw = self.binding({})
        raw_rows = dict(_design_rows({"design_revisions": [raw]}))
        self.assertNotIn("固定输入映射", raw_rows)
        self.assertNotIn("模型输入项", raw_rows)
        raw_output = "\n".join(_raw_validation_lines(self.report(self.analysis())))
        cubic = self.binding({"feature_columns": ["age"], "input_basis": "univariate_cubic"})
        cubic_rows = dict(_design_rows({"design_revisions": [cubic]}))
        self.assertEqual(cubic_rows["固定输入映射"], "原尺度单列展开为一次、二次、三次项，无常数列；之后按训练折标准化")
        self.assertEqual(cubic_rows["模型输入项"], "age、age^2、age^3")
        cubic_output = "\n".join(_raw_validation_lines(self.report(self.analysis(
            feature_columns=["age"], input_basis="univariate_cubic"))))
        self.assertIn("原尺度单列先展开一次、二次、三次项，无常数列，再在训练折拟合标准化", cubic_output)
        comparison_output = "\n".join(_feature_comparison_lines({"feature_comparisons": [self.comparison(
            feature_columns=["age"], input_basis="univariate_cubic")]}))
        self.assertIn("固定Ridge超参数与评价划分，明确比较原单列输入和一次/二次/三次基；输入空间及有效正则化随之改变。", comparison_output)
        self.assertNotIn("输入映射：", comparison_output)
        self.assertNotIn("log1p", raw_output + cubic_output + comparison_output)


if __name__ == "__main__":
    unittest.main()
