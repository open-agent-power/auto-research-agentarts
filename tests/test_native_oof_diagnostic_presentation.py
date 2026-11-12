"""Saved diagnostics supply complete useful feedback without executing estimators."""
import copy
import unittest
from unittest.mock import patch

from autoresearch.contracts import canonical
from autoresearch.plan_feedback import (MAX_INLINE_DIAGNOSTIC_GROUP_BYTES, project_observations, projection_notice)
from autoresearch.project_report import (_DIAGNOSTIC_GROUP_HEADERS, _markdown_table,
    _raw_validation_lines, _saved_diagnostic_sections)


class NativeOOFDiagnosticPresentationTests(unittest.TestCase):
    def setUp(self):
        for estimator in ("StandardScaler", "Ridge"):
            self.enterContext(patch("autoresearch.ridge_validation_adapter." + estimator + ".fit",
                                    side_effect=AssertionError("Presentation must not fit")))

    @staticmethod
    def observation(count=12):
        # A saved-value display fixture, not a newly executed research result.
        groups = [{"groups": ["geometry-" + str(index).zfill(4)], "folds": [index % 5 + 1], "n": 64,
                   "candidate_mae": 7.75 if index in (4, 11) else 2.0,
                   "reference_mae": 3.22 if index in (4, 11) else 8.0,
                   "mean_error": 1.0, "reference_mean_error": 0.5, "negative_predictions": 0}
                  for index in range(1, count + 1)]
        return {"kind": "saved_oof_diagnostic", "source_check": "group_cv", "source_ref": {
            "action_id": "source-cv", "request_id": "original-request", "method_id": "data.ridge-group-validation",
            "result_sha256": "b" * 64, "producer_code_identity": "a" * 64, "design_version": 1,
            "resource_id": "saved-geometry", "resource_version": 1,
            "target_column": "cooling_load", "target_unit": "source_scale_units_not_stated"},
            "input_n": 768, "excluded": 0,
            "row_weighted": {"n": 768, "candidate_mae": 3.702153115387885, "reference_mae": 8.784738941333913,
                             "mean_error": 0.0, "reference_mean_error": 0.0, "negative_predictions": 0},
            "row_error_counts": {"n": 768, "improved_rows": 614, "worsened_rows": 154, "tied_rows": 0},
            "group_weighted": {"group_count": count, "candidate_mae": 3.702153115387885, "reference_mae": 8.784738941333913},
            "group_error_counts": {"group_count": count, "improved_groups": count - 2, "worsened_groups": 2, "tied_groups": 0},
            "prediction_ranges": {"n": 768, "observed_min": 10.9, "observed_max": 48.03,
                "predicted_min": 8.171742089841867, "predicted_max": 43.8552438970965,
                "negative_predictions": 0, "below_observed_min": 24, "above_observed_max": 0, "scientific_validation": False},
            "fold_errors": [{"fold": 1, "train_n": 576, "test_n": 192, "train_group_count": 9,
                "test_group_count": 3, "n": 192, "candidate_mae": 3.0, "reference_mae": 8.0,
                "mean_error": 1.0, "reference_mean_error": 0.5, "negative_predictions": 0}],
            "group_errors": groups, "scientific_validation": False}

    @staticmethod
    def report(observation):
        return {"action_results": [{"status": "completed", "action_id": "new-diagnostic-action",
            "tool_result": {"observations": [observation], "result": {"diagnostic": {
                "schema_version": "saved-oof-diagnostics-v1", "check": observation["source_check"], "rows": [],
                "groups": copy.deepcopy(observation["group_errors"]), "scientific_validation": False}}}}]}

    def test_small_table_supplies_every_group_and_adverse_facts_to_model(self):
        original = [self.observation()]
        before = copy.deepcopy(original)
        projected = project_observations(original, "artifacts/diagnostic.json")[0]
        self.assertEqual(projected["group_errors"], original[0]["group_errors"])
        self.assertEqual(len(projected["group_errors"]), 12)
        self.assertEqual([g["groups"][0] for g in projected["group_errors"] if g["candidate_mae"] > g["reference_mae"]],
                         ["geometry-0004", "geometry-0011"])
        self.assertEqual(projected["row_error_counts"]["worsened_rows"], 154)
        self.assertEqual(projected["prediction_ranges"]["below_observed_min"], 24)
        self.assertNotIn("group_errors_ref", projected)
        self.assertEqual(projected["diagnostic_ref"]["path"], ["tool_result", "result", "diagnostic"])
        self.assertEqual(original, before)

    def test_large_table_is_referenced_whole_with_no_ranked_subset(self):
        original = [self.observation(300)]
        before = copy.deepcopy(original)
        self.assertGreater(len(canonical(original[0]["group_errors"]).encode()), MAX_INLINE_DIAGNOSTIC_GROUP_BYTES)
        projected = project_observations(original, "artifacts/diagnostic.json")[0]
        self.assertNotIn("group_errors", projected)
        self.assertEqual(projected["group_errors_ref"], {"kind": "action_artifact_field",
            "artifact_ref": "artifacts/diagnostic.json", "path": ["tool_result", "observations", 0, "group_errors"],
            "mode": "complete_table_not_included", "count": 300})
        self.assertEqual(projected["group_error_counts"], original[0]["group_error_counts"])
        self.assertEqual(projected["fold_errors"], original[0]["fold_errors"])
        self.assertEqual(original, before)

    def test_group_size_limit_uses_utf8_bytes_not_character_count(self):
        observation = self.observation(20)
        for group in observation["group_errors"]:
            group["groups"] = ["几何" * 100]
        text = canonical(observation["group_errors"])
        self.assertLess(len(text), MAX_INLINE_DIAGNOSTIC_GROUP_BYTES)
        self.assertGreater(len(text.encode("utf-8")), MAX_INLINE_DIAGNOSTIC_GROUP_BYTES)
        self.assertNotIn("group_errors", project_observations([observation], "x.json")[0])

    def test_missing_artifact_never_invents_a_reference_or_drops_values(self):
        observations = [self.observation(300)]
        self.assertEqual(project_observations(observations, None), observations)

    def test_existing_feedback_and_old_prompt_notice_are_unchanged(self):
        observations = [{"kind": "ridge_validation", "summary": {"n": 3}, "group_errors": [1, 2, 3]}]
        self.assertEqual(project_observations(observations, "x.json"), observations)
        old = {"schema_version": "research-plan-context-v2", "feedback": [{"observations": observations}]}
        self.assertNotIn("Saved OOF diagnostic feedback", projection_notice(old))
        current = {"schema_version": "research-plan-context-v2", "feedback": [{"observations": [self.observation()]}]}
        notice = projection_notice(current)
        for expected in ("not a new fit", "complete group table", "not included", "not additional model-read text",
                         "not a parent model"):
            self.assertIn(expected, notice)

    def test_report_keeps_source_identity_all_groups_and_reference_direction(self):
        observation = self.observation()
        report = self.report(observation)
        before = copy.deepcopy(report)
        sections = _saved_diagnostic_sections(report)
        self.assertEqual(len(sections), 1)
        section = sections[0]
        output = "\n".join(section["lines"]) + "\n" + _markdown_table(_DIAGNOSTIC_GROUP_HEADERS, section["group_rows"])
        for expected in ("new-diagnostic-action", "source-cv", "生产代码：" + "a" * 64,
                         "原验证结果身份：" + "b" * 64, "source_scale_units_not_stated", "新增拟合0", "不是新的交叉验证",
                         "训练折均值参考MAE 8.7847389", "614/154/0", "10/2/0", "0/24/0",
                         "不是父模型比较", "不证明因果、物理不可能或科学批准", "geometry-0004", "geometry-0011"):
            self.assertIn(expected, output)
        self.assertEqual(len(section["group_rows"]), 12)
        self.assertEqual(section["fold_rows"][0][:3], ["1", "576/192", "9/3"])
        self.assertEqual(_raw_validation_lines(report), [])
        self.assertEqual(report, before)

    def test_long_group_labels_are_preserved_in_complete_report_table(self):
        observation = self.observation()
        label = "long-source-group-" * 40
        observation["group_errors"][0]["groups"] = [label]
        section = _saved_diagnostic_sections(self.report(observation))[0]
        table = _markdown_table(_DIAGNOSTIC_GROUP_HEADERS, section["group_rows"], section["cell_limit"])
        self.assertIn(label, table)

    def test_failed_diagnostic_does_not_publish_numbers(self):
        report = self.report(self.observation())
        report["action_results"][0]["status"] = "failed"
        self.assertEqual(_saved_diagnostic_sections(report), [])

    def test_no_declared_groups_does_not_turn_missing_group_metrics_into_zero(self):
        observation = self.observation()
        observation.update(source_check="random_cv", group_errors=[],
            group_weighted={"group_count": 0, "candidate_mae": None, "reference_mae": None},
            group_error_counts={"group_count": 0, "improved_groups": 0, "worsened_groups": 0, "tied_groups": 0})
        section = _saved_diagnostic_sections(self.report(observation))[0]
        self.assertEqual(section["group_rows"], [])
        self.assertIn("原验证未声明拆分组，不生成组等权结论。", section["lines"])
        self.assertNotIn("组等权MAE 0", "\n".join(section["lines"]))


if __name__ == "__main__":
    unittest.main()
