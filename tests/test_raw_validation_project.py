"""Raw-table fits share the original project ledger and saved-result recovery."""

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from autoresearch import tabular_quality_adapter as tabular
from autoresearch.contracts import ResearchError, canonical
from autoresearch.project_controller import ProjectController
from autoresearch.research_project import ResearchProject


class RawValidationProjectTests(unittest.TestCase):
    def project(self, fit_limit=20, groups=3, constant_target=False):
        from autoresearch.project_design import bind
        root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        inputs = root / "inputs"
        inputs.mkdir()
        group_size = 12 // groups
        text = "group,x,target\n" + "".join(f"g{i // group_size},{i},{5 if constant_target else 2 * i + (i // group_size)}\n" for i in range(12))
        (inputs / "data.csv").write_text(text, encoding="utf-8")
        spec = {"schema_version": "tabular-quality-spec-v1", "file": "data.csv", "dataset_label": "Raw validation fixture",
                "source_url": "urn:test:raw", "license_note": "Fixture", "sample_unit": "declared record",
                "group_columns": ["group"], "key_columns": [], "numeric_columns": ["x", "target"],
                "target_column": "target", "target_unit": "fixture unit", "missing_tokens": [""], "delimiter": ",",
                "provenance": {"origin_sha256": "a" * 64, "description": "Constructed fixture"}}
        (inputs / "spec.json").write_text(json.dumps(spec), encoding="utf-8")
        source = inputs / "source.json"
        source.write_text(canonical(tabular.capture_source(inputs)), encoding="utf-8")
        project = ResearchProject(root / "project")
        project.create(source=source, goal="Compare fixed split designs", budget_ref="fixture:raw", max_tool_calls=8, method_id=tabular.TOOL_ID)
        resource = {"schema_version": "research-design-resource-v1", "id": "ridge-validation-design", "version": 1,
                    "title": "Fixed Ridge comparison", "question": "Does group holdout change error?", "claim": "The split design affects validation",
                    "alternatives": ["random folds", "group folds"], "checks": ["random_cv", "group_cv", "negative_control"],
                    "sources": ["urn:test:fixed-protocol"], "parent_version": None, "change_reason": "Initial raw design"}
        bind(project, request_id="bind-raw", expected_state_version=0, resource=resource, prediction_column=None,
             training={"feature_columns": ["x"], "split_group_columns": ["group"], "fit_limit": fit_limit}, reason="Compare fixed designs")
        controller = ProjectController(project.root)
        controller.advance(request_id="quality")
        return project, controller

    def parameters(self, project):
        quality = project.status()["actions"][0]
        return {"based_on_action_id": quality["id"], "based_on_result_sha256": quality["result_sha256"]}

    def test_raw_split_fits_and_negative_control_use_one_budget_and_replay_without_fits(self):
        from autoresearch import method_registry as registry
        project, controller = self.project()
        original_csv = (project.root / "source.json").read_bytes()
        random_result = controller.advance(request_id="random")
        self.assertEqual(random_result["result"]["child"]["command"], "data.ridge-random-validation")
        random_action = project.status()["actions"][-1]
        self.assertEqual(len(random_action["fit_events"]), 10)
        grouped = controller.advance(request_id="group")
        self.assertEqual(grouped["result"]["child"]["command"], "data.ridge-group-validation")
        group_action = project.status()["actions"][-1]
        self.assertIn(random_action["id"], grouped["decision"]["reason"])
        self.assertEqual(controller.advance(request_id="control")["result"]["child"]["command"], "data.prediction-negative-control")
        state = project.status()
        self.assertEqual(state["actions"][-1]["generated_prediction_ref"]["action_id"], group_action["id"])
        self.assertEqual(state["budget"]["fit_attempts_used"], 16)
        self.assertEqual((state["budget"]["new_fits"], state["budget"]["preprocessing_fits"], state["budget"]["fits_reserved"]), (8, 8, 0))
        self.assertEqual((project.root / "source.json").read_bytes(), original_csv)
        with patch.object(registry.RIDGE["data.ridge-random-validation"], "execute", side_effect=AssertionError("No repeat fit")):
            self.assertTrue(project.step(request_id=random_action["request_id"], method_id=random_action["command"],
                                         parameters=self.parameters(project))["replayed"])
        self.assertEqual(project.status(), state)
        self.assertIn("random_cv", controller.next()["decision"]["reason"])
        self.assertIn("group_cv", controller.next()["decision"]["reason"])

    def test_two_group_design_uses_precise_four_fit_reservation(self):
        project, controller = self.project(fit_limit=14, groups=2)
        controller.advance(request_id="random")
        self.assertTrue(any(item["method_id"] == "data.ridge-group-validation" for item in controller.selection_context()["candidates"]))
        controller.advance(request_id="group")
        state = project.status()
        self.assertEqual(state["actions"][-1]["fit_reservation"], 4)
        self.assertEqual((state["budget"]["fit_attempts_used"], state["budget"]["fits_reserved"]), (14, 0))

    def test_constant_target_has_no_executable_fitting_candidate(self):
        project, controller = self.project(constant_target=True)
        self.assertEqual(project.status()["design_revisions"][-1]["fit_requirements"]["random_cv"], 0)
        self.assertFalse(any(item["method_id"].startswith("data.ridge-") for item in controller.selection_context()["candidates"]))
        self.assertEqual(project.status()["budget"]["fit_attempts_used"], 0)

    def test_negative_control_source_change_blocks_old_project_execution(self):
        from autoresearch import prediction_controls
        project, controller = self.project()
        original_read = Path.read_bytes
        controls_path = Path(prediction_controls.__file__).resolve()
        def changed_source(path):
            raw = original_read(path)
            return raw + b"\n# changed protocol identity\n" if path.resolve() == controls_path else raw
        with patch.object(Path, "read_bytes", changed_source):
            preview = controller.next()
        self.assertIn("CODE_CHANGED", [item["code"] for item in preview["blockers"]])
        self.assertFalse(preview["executable"])

    def test_fit_limit_blocks_second_design_in_context_and_direct_step(self):
        project, controller = self.project(fit_limit=10)
        controller.advance(request_id="random")
        self.assertFalse(any(item["method_id"] == "data.ridge-group-validation" for item in controller.selection_context()["candidates"]))
        with self.assertRaises(ResearchError) as caught:
            project.step(request_id="over-budget", method_id="data.ridge-group-validation", parameters=self.parameters(project))
        self.assertEqual(caught.exception.code, "FIT_BUDGET_EXHAUSTED")
        self.assertEqual(project.status()["budget"]["fit_attempts_used"], 10)

    def test_known_fit_failure_keeps_attempt_and_releases_unused_reservation(self):
        from autoresearch import method_registry as registry
        project, _ = self.project()
        def fail(payload, parameters, fit_observer=None):
            fit_observer({"index": 1, "estimator": "scaler", "fold": 1, "status": "started"})
            raise ResearchError("FIXTURE_FAILURE", "Known failure")
        with patch.object(registry.RIDGE["data.ridge-random-validation"], "execute", side_effect=fail):
            with self.assertRaises(ResearchError):
                project.step(request_id="failed-fit", method_id="data.ridge-random-validation", parameters=self.parameters(project))
        state = project.status()
        self.assertEqual(state["actions"][-1]["status"], "failed")
        self.assertEqual((state["budget"]["fit_attempts_used"], state["budget"]["fits_reserved"]), (1, 0))

    def test_unknown_fit_retains_reservation_and_complete_artifact_recovers_without_training(self):
        from autoresearch import method_registry as registry
        project, _ = self.project()
        def interrupted(payload, parameters, fit_observer=None):
            fit_observer({"index": 1, "estimator": "scaler", "fold": 1, "status": "started"})
            raise KeyboardInterrupt()
        with patch.object(registry.RIDGE["data.ridge-random-validation"], "execute", side_effect=interrupted):
            with self.assertRaises(KeyboardInterrupt):
                project.step(request_id="interrupted-fit", method_id="data.ridge-random-validation", parameters=self.parameters(project))
        self.assertEqual(project.resume(request_id="interrupted-fit")["status"], "unknown")
        self.assertEqual((project.status()["budget"]["fit_attempts_used"], project.status()["budget"]["fits_reserved"]), (1, 9))
        second, _ = self.project()
        with patch.object(second, "_commit_result", side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                second.step(request_id="complete-artifact", method_id="data.ridge-random-validation", parameters=self.parameters(second))
        with patch.object(registry.RIDGE["data.ridge-random-validation"], "execute", side_effect=AssertionError("No recovery fit")):
            self.assertEqual(second.resume(request_id="complete-artifact")["status"], "completed")
        self.assertEqual((second.status()["budget"]["fit_attempts_used"], second.status()["budget"]["fits_reserved"]), (10, 0))


if __name__ == "__main__":
    unittest.main()
