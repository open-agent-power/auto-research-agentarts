"""Raw capacity uses captured records; saved-column checks keep their own bound."""

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from autoresearch import prediction_adapter, project_design, ridge_validation_adapter as ridge, tabular_quality_adapter as tabular
from autoresearch.contracts import ResearchError, canonical
from autoresearch.project_controller import ProjectController
from autoresearch.research_project import ResearchProject


class RawRowCapacityTests(unittest.TestCase):
    def project(self, rows):
        root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        inputs = root / "inputs"
        inputs.mkdir()
        # Five declared groups exercise ten real estimator attempts at 1030 rows.
        text = "id,batch,x,y,prediction\n" + "".join(
            f"r{i},g{i % 5},{i + 1},{2 * (i + 1) + i % 5},{2 * (i + 1)}\n" for i in range(rows))
        (inputs / "data.csv").write_text(text, encoding="utf-8")
        spec = {"schema_version": "tabular-quality-spec-v1", "file": "data.csv",
                "dataset_label": "Constructed row-capacity fixture", "source_url": "urn:test:row-capacity",
                "license_note": "Test fixture", "sample_unit": "declared record", "group_columns": ["batch"],
                "key_columns": ["id"], "numeric_columns": ["x", "y", "prediction"], "target_column": "y",
                "target_unit": "fixture unit", "missing_tokens": [""], "delimiter": ",",
                "provenance": {"origin_sha256": "a" * 64, "description": "Constructed capacity fixture"}}
        (inputs / "spec.json").write_text(canonical(spec), encoding="utf-8")
        payload = tabular.capture_source(inputs)
        source = inputs / "source.json"
        source.write_text(canonical(payload), encoding="utf-8")
        project = ResearchProject(root / "project")
        project.create(source=source, goal="Check fixed raw row capacity", budget_ref="test-only:capacity",
                       max_tool_calls=4, method_id=tabular.TOOL_ID)
        return project, payload

    @staticmethod
    def resource(checks=("group_cv", "negative_control")):
        return {"schema_version": "research-design-resource-v1", "id": "row-capacity-design", "version": 1,
                "title": "Fixed row capacity", "question": "Can the complete captured table be evaluated?",
                "claim": "All complete rows retain the fixed protocol", "alternatives": ["declared group holdout"],
                "checks": list(checks), "sources": ["urn:test:row-capacity"], "parent_version": None,
                "change_reason": "Exercise the declared row bound"}

    def bind(self, project, checks=("group_cv", "negative_control")):
        return project_design.bind(project, request_id="bind-capacity", expected_state_version=0,
                                   resource=self.resource(checks), prediction_column=None,
                                   training={"feature_columns": ["x"], "split_group_columns": ["batch"], "fit_limit": 10},
                                   reason="Validate the complete captured table")

    def raw_payload(self, payload):
        return {**payload, "design_binding": {"version": 1, "source_snapshot_sha256": payload["snapshot_sha256"],
                "target_column": "y", "prediction_column": None, "resource": self.resource(("random_cv", "group_cv", "negative_control")),
                "training": {"feature_columns": ["x"], "split_group_columns": ["batch"], "fit_limit": 10}}}

    @staticmethod
    def parameters():
        return {"based_on_action_id": "quality", "based_on_result_sha256": "a" * 64}

    def test_1030_rows_save_complete_group_oof_and_control_without_repeat_fits(self):
        project, _ = self.project(1030)
        original_source = (project.root / "source.json").read_bytes()
        binding = self.bind(project)
        self.assertEqual(binding["fit_requirements"], {"group_cv": 10})
        controller = ProjectController(project.root)
        self.assertFalse(any(item["method_id"].startswith("data.ridge-")
                             for item in controller.selection_context()["candidates"]))
        controller.advance(request_id="quality")
        quality = project.status()["actions"][0]
        self.assertEqual(quality["observations"][0]["profile"]["rows"], 1030)
        candidates = {item["method_id"] for item in controller.selection_context()["candidates"]}
        self.assertIn(ridge.GROUPED.TOOL_ID, candidates)
        self.assertNotIn(prediction_adapter.NEGATIVE_CONTROL.TOOL_ID, candidates)
        controller.advance(request_id="group-capacity")
        state = project.status()
        action = state["actions"][-1]
        artifact = json.loads((project.root / action["artifact"]).read_bytes())
        analysis = artifact["tool_result"]["result"]["analysis"]
        self.assertEqual((analysis["summary"]["input_n"], analysis["summary"]["n"], analysis["summary"]["excluded"]),
                         (1030, 1030, 0))
        self.assertEqual([row["logical_record"] for row in analysis["oof"]], list(range(1, 1031)))
        self.assertEqual([row["physical_line_end"] for row in analysis["oof"]], list(range(2, 1032)))
        labels = {row["logical_record"]: tuple(row["groups"]) for row in analysis["oof"]}
        self.assertEqual(len(analysis["folds"]), 5)
        for fold in analysis["folds"]:
            self.assertTrue({labels[row] for row in fold["train_records"]}.isdisjoint(
                            {labels[row] for row in fold["test_records"]}))
        self.assertEqual((len(action["fit_events"]), action["fit_reservation"]), (10, 10))
        self.assertEqual((state["budget"]["fit_attempts_used"], state["budget"]["new_fits"],
                          state["budget"]["preprocessing_fits"], state["budget"]["fits_reserved"]), (10, 5, 5, 0))
        self.assertIn(prediction_adapter.NEGATIVE_CONTROL.TOOL_ID,
                      {item["method_id"] for item in controller.selection_context()["candidates"]})
        with patch.object(ridge.StandardScaler, "fit", side_effect=AssertionError("No control or replay fit")), \
                patch.object(ridge.Ridge, "fit", side_effect=AssertionError("No control or replay fit")):
            controller.advance(request_id="control-capacity")
            finished = project.status()
            control = finished["actions"][-1]
            self.assertEqual(control["observations"][0]["summary"]["n"], 1030)
            self.assertEqual(control["generated_prediction_ref"]["action_id"], action["id"])
            self.assertEqual(finished["budget"]["fit_attempts_used"], 10)
            self.assertEqual(finished["budget"]["local_tool_calls_used"], 3)
            reopened = ResearchProject(project.root)
            parameters = {"based_on_action_id": quality["id"], "based_on_result_sha256": quality["result_sha256"]}
            self.assertEqual(self.bind(reopened), binding)
            for saved_action in (action, control):
                self.assertTrue(reopened.step(request_id=saved_action["request_id"], method_id=saved_action["command"],
                                             parameters=parameters)["replayed"])
            for request_id in ("group-capacity", "control-capacity"):
                self.assertTrue(ProjectController(project.root).advance(request_id=request_id)["replayed"])
            self.assertEqual(reopened.status(), finished)
        self.assertEqual((project.root / "source.json").read_bytes(), original_source)

    def test_2048_boundary_binds_and_calculates_both_fit_requirements_without_training(self):
        project, payload = self.project(2048)
        with patch.object(ridge.StandardScaler, "fit", side_effect=AssertionError("Boundary checks cannot fit")), \
                patch.object(ridge.Ridge, "fit", side_effect=AssertionError("Boundary checks cannot fit")):
            binding = self.bind(project, checks=("random_cv", "group_cv", "negative_control"))
            self.assertEqual(binding["fit_requirements"], {"random_cv": 10, "group_cv": 10})
            self.assertEqual(len(ridge._inputs({**payload, "design_binding": binding})["rows"]), 2048)
        self.assertEqual(project.status()["budget"]["fit_attempts_used"], 0)

    def test_2049_binding_and_direct_ridge_reject_before_any_fit(self):
        project, payload = self.project(2049)
        before = project.status()
        with patch.object(ridge.StandardScaler, "fit", side_effect=AssertionError("Oversized input cannot fit")), \
                patch.object(ridge.Ridge, "fit", side_effect=AssertionError("Oversized input cannot fit")):
            with self.assertRaises(ResearchError) as caught:
                self.bind(project)
            self.assertEqual(caught.exception.code, "UNSUPPORTED_SCOPE")
            self.assertIn("2048", str(caught.exception))
            for adapter in ridge.ADAPTERS:
                with self.subTest(adapter=adapter.TOOL_ID):
                    events = []
                    with self.assertRaises(ResearchError) as caught:
                        adapter.required_fit_attempts(self.raw_payload(payload))
                    self.assertEqual(caught.exception.code, "UNSUPPORTED_SCOPE")
                    with self.assertRaises(ResearchError) as caught:
                        adapter.execute(self.raw_payload(payload), self.parameters(), fit_observer=events.append)
                    self.assertEqual(caught.exception.code, "UNSUPPORTED_SCOPE")
                    self.assertEqual(events, [])
        self.assertEqual(project.status(), before)

    def test_negative_control_rejects_2049_captured_records_or_saved_oof_rows(self):
        for captured, oof_rows in ((2049, 1030), (1030, 2049)):
            with self.subTest(captured=captured, oof_rows=oof_rows):
                project, payload = self.project(captured)
                packet = self.raw_payload(payload)
                packet["generated_prediction"] = {"action_id": "saved-group", "result_sha256": "a" * 64,
                    "analysis": {"schema_version": "ridge-validation-v1", "source_snapshot_sha256": payload["snapshot_sha256"],
                                 "oof": [{}] * oof_rows}}
                with patch("autoresearch.prediction_controls.evaluate_negative_control",
                           side_effect=AssertionError("Reject before reading oversized OOF")):
                    with self.assertRaises(ResearchError) as caught:
                        prediction_adapter.NEGATIVE_CONTROL.execute(packet, self.parameters())
                self.assertEqual(caught.exception.code, "UNSUPPORTED_SCOPE")
                self.assertIn("2048", str(caught.exception))
                self.assertEqual(project.status()["budget"]["fit_attempts_used"], 0)

    def test_saved_column_candidates_and_direct_adapter_keep_512_limit(self):
        for rows in (512, 513, 1030):
            with self.subTest(rows=rows):
                project, payload = self.project(rows)
                binding = project_design.bind(project, request_id="bind-saved", expected_state_version=0,
                    resource=self.resource(("baseline", "grouped", "sensitivity")), prediction_column="prediction",
                    reason="Check bounded saved columns")
                controller = ProjectController(project.root)
                controller.advance(request_id="quality")
                context = controller.selection_context()
                candidates = {item["method_id"] for item in context["candidates"]}
                self.assertEqual(prediction_adapter.BASELINE.TOOL_ID in candidates, rows == 512)
                conditions = {item["method_id"]: item for item in context["conditions"]}
                raw_gap = conditions[ridge.GROUPED.TOOL_ID]["missing_information"][0]
                self.assertIn("raw-table", raw_gap)
                self.assertIn("2048", raw_gap)
                packet = {**payload, "design_binding": binding}
                if rows == 512:
                    self.assertEqual(prediction_adapter.BASELINE.execute(packet, self.parameters())["status"], "completed")
                else:
                    saved_gap = conditions[prediction_adapter.BASELINE.TOOL_ID]["missing_information"][0]
                    self.assertIn("saved-prediction", saved_gap)
                    self.assertIn("512", saved_gap)
                    for adapter in (prediction_adapter.BASELINE, prediction_adapter.GROUPED, prediction_adapter.SENSITIVITY):
                        with self.assertRaises(ResearchError) as caught:
                            adapter.execute(packet, self.parameters())
                        self.assertEqual(caught.exception.code, "UNSUPPORTED_SCOPE")
                        self.assertIn("512", str(caught.exception))
                self.assertEqual(project.status()["budget"]["fit_attempts_used"], 0)


if __name__ == "__main__":
    unittest.main()
