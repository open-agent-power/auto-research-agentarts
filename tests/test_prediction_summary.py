"""Saved OOF ranges describe observed values without changing research evidence."""

import base64
import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from autoresearch.contracts import canonical
from autoresearch.local_workbench import LocalWorkbench
from autoresearch.prediction_summary import summarize_oof_range
from autoresearch.project_controller import ProjectController
from autoresearch.research_design import RAW_RESOURCE


class PredictionSummaryTests(unittest.TestCase):
    def test_positive_targets_retain_negative_and_outside_range_predictions(self):
        rows = [{"observed": actual, "predicted": prediction}
                for actual, prediction in [(1, -2), (2, 0), (3, 1), (4, 4), (5, 6)]]
        before = copy.deepcopy(rows)
        self.assertEqual(summarize_oof_range(rows), {
            "n": 5, "observed_min": 1, "observed_max": 5, "predicted_min": -2, "predicted_max": 6,
            "negative_predictions": 1, "below_observed_min": 2, "above_observed_max": 1,
            "scientific_validation": False})
        self.assertEqual(rows, before)

    def test_negative_observations_and_equal_boundaries_remain_descriptive(self):
        rows = [{"observed": actual, "predicted": prediction}
                for actual, prediction in [(-5, -5), (-2, -3), (0, 0)]]
        result = summarize_oof_range(rows)
        self.assertEqual(result, {
            "n": 3, "observed_min": -5, "observed_max": 0, "predicted_min": -5, "predicted_max": 0,
            "negative_predictions": 2, "below_observed_min": 0, "above_observed_max": 0,
            "scientific_validation": False})
        self.assertNotIn("valid", result)

    def test_empty_predictions_have_no_range_summary(self):
        self.assertIsNone(summarize_oof_range([]))

    def test_design_view_projects_real_saved_oof_without_writes_or_refitting(self):
        root = Path(self.enterContext(tempfile.TemporaryDirectory())) / "manager"
        manager = LocalWorkbench(root)
        spec = {"schema_version": "tabular-quality-spec-v1", "file": "readings.csv",
                "dataset_label": "OOF range fixture", "source_url": "urn:test:oof-range", "license_note": "Constructed fixture",
                "sample_unit": "declared_record", "group_columns": ["batch"], "key_columns": [],
                "numeric_columns": ["x", "target"], "target_column": "target", "target_unit": "fixture_unit",
                "missing_tokens": [""], "delimiter": ",", "provenance": {"origin_sha256": "a" * 64, "description": "Fixture"}}
        raw = ("batch,x,target\n" + "".join(f"g{index // 4},{index},{2 * index + index // 4}\n" for index in range(12))).encode()
        manager.create({"request_id": "range-create", "goal": "Inspect the saved prediction range", "budget_ref": "test-range-only",
                        "max_tool_calls": 2, "input": {"file_name": "readings.csv", "csv_base64": base64.b64encode(raw).decode(),
                        "spec_base64": base64.b64encode(canonical(spec).encode()).decode()}})
        project, _ = manager.binding()
        manager.bind_design({"request_id": "range-bind", "project_id": project.status()["id"], "expected_state_version": 0,
                             "resource_id": RAW_RESOURCE["id"], "resource_version": 1, "prediction_column": None,
                             "reason": "Describe actual saved OOF outputs", "training": {
                                 "feature_columns": ["x"], "split_group_columns": ["batch"], "fit_limit": 10}})
        controller = ProjectController(project.root)
        controller.advance(request_id="range-quality")
        controller.advance(request_id="range-random")
        before = project.status()
        original = {str(path.relative_to(root)): path.read_bytes() for path in root.rglob("*") if path.is_file()}
        with patch("autoresearch.ridge_validation_adapter.StandardScaler.fit", side_effect=AssertionError("Read-only projection must not fit")), \
             patch("autoresearch.ridge_validation_adapter.Ridge.fit", side_effect=AssertionError("Read-only projection must not fit")):
            view = manager.designs()
        check = view["checks"][0]
        self.assertEqual(check["check"], "random_cv")
        self.assertEqual(check["prediction_range"], summarize_oof_range(check["oof"]))
        self.assertEqual(check["prediction_range"]["n"], 12)
        self.assertNotIn("prediction_range", before["actions"][-1]["observations"][0]["summary"])
        self.assertEqual(project.status(), before)
        self.assertEqual({str(path.relative_to(root)): path.read_bytes() for path in root.rglob("*") if path.is_file()}, original)


if __name__ == "__main__":
    unittest.main()
