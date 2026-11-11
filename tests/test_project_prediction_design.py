"""Saved prediction checks retain design, original requests and cumulative usage."""

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from autoresearch import tabular_quality_adapter as tabular
from autoresearch.contracts import ResearchError, canonical
from autoresearch.project_controller import ProjectController
from autoresearch.research_project import ResearchProject


class ProjectPredictionDesignTests(unittest.TestCase):
    def project(self, csv_text=None):
        root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        inputs = root / "inputs"
        inputs.mkdir()
        (inputs / "data.csv").write_text(csv_text or
            "group,observed,prediction,other\na,1,1.1,0\na,2,2.1,0\nb,5,5.1,0\nb,6,6.1,0\nc,9,9.1,0\nc,10,10.1,0\n",
            encoding="utf-8")
        spec = {"schema_version": "tabular-quality-spec-v1", "file": "data.csv", "dataset_label": "Saved predictions",
                "source_url": "urn:test:predictions", "license_note": "Test fixture", "sample_unit": "one saved prediction",
                "group_columns": ["group"], "key_columns": [], "numeric_columns": ["observed", "prediction", "other"],
                "target_column": "observed", "target_unit": "test units", "missing_tokens": ["", "NA"], "delimiter": ",",
                "provenance": {"origin_sha256": "a" * 64, "description": "Fixture declaration"}}
        (inputs / "spec.json").write_text(json.dumps(spec), encoding="utf-8")
        source = inputs / "source.json"
        source.write_text(canonical(tabular.capture_source(inputs)), encoding="utf-8")
        project = ResearchProject(root / "project")
        project.create(source=source, goal="Check saved predictions", budget_ref="fixture:original", max_tool_calls=2,
                       method_id=tabular.TOOL_ID)
        return project

    def resource(self, version=1):
        return {"schema_version": "research-design-resource-v1", "id": "saved-prediction-validation", "version": version,
                "title": "Saved prediction validation", "question": "Do the saved predictions beat a reference?",
                "claim": "A bounded saved-prediction comparison", "alternatives": ["row reference", "group reference"],
                "checks": ["baseline", "grouped", "sensitivity"], "sources": ["urn:test:protocol"],
                "parent_version": version - 1 if version > 1 else None, "change_reason": "Initial design"}

    def bind(self, project, **changes):
        from autoresearch.project_design import bind
        values = {"request_id": "bind-design", "expected_state_version": project.status()["state_version"],
                  "resource": self.resource(), "prediction_column": "prediction", "reason": "Validate existing predictions"}
        values.update(changes)
        return bind(project, **values)

    def test_binding_replays_original_revision_without_spending_or_mutating_resource(self):
        project = self.project()
        original = project.status()
        resource = self.resource()
        revision = self.bind(project, resource=resource)
        self.assertEqual(resource, self.resource())
        self.assertEqual(revision["version"], 1)
        self.assertEqual(revision["prediction_column"], "prediction")
        self.assertEqual(project.status()["state_version"], 1)
        self.assertEqual(project.status()["budget"], original["budget"])
        self.assertEqual(self.bind(project, resource=resource, expected_state_version=0), revision)
        self.assertEqual(project.status()["state_version"], 1)
        with self.assertRaises(ResearchError) as caught:
            self.bind(project, prediction_column="other", expected_state_version=0)
        self.assertEqual(caught.exception.code, "IDEMPOTENCY_CONFLICT")
        with self.assertRaises(ResearchError):
            self.bind(project, request_id="bad-column", prediction_column="observed")
        with self.assertRaises(ResearchError) as caught:
            self.bind(project, request_id="stale", expected_state_version=0)
        self.assertEqual(caught.exception.code, "STALE_STATE")

    def test_saved_feedback_selects_baseline_then_grouped_and_replay_keeps_frozen_design(self):
        from autoresearch import prediction_adapter
        project = self.project()
        controller = ProjectController(project.root)
        self.assertFalse(any(item["method_id"].startswith("data.prediction-")
                             for item in controller.selection_context()["candidates"]))
        self.bind(project)
        controller.advance(request_id="quality", expected_state_version=project.status()["state_version"])
        state = project.status()
        context = controller.selection_context()
        prediction_choices = [item["method_id"] for item in context["candidates"]
                              if item["method_id"].startswith("data.prediction-")]
        self.assertEqual(prediction_choices, ["data.prediction-baseline"])
        baseline = controller.advance(request_id="baseline", expected_state_version=state["state_version"])
        self.assertEqual(baseline["result"]["child"]["command"], "data.prediction-baseline")
        saved = project.status()
        action = saved["actions"][-1]
        observation = action["observations"][0]
        self.assertAlmostEqual(observation["summary"]["candidate_mae"], 0.1)
        self.assertTrue(observation["summary"]["outperforms_reference"])
        self.assertEqual(action["design_binding"]["version"], 1)
        self.assertEqual(action["method_instance"]["input_bindings"]["prediction_column"], "prediction")
        self.assertEqual(saved["budget"]["new_fits"], 0)
        self.assertEqual(saved["budget"]["local_tool_calls_used"], 2)
        project.extend_local_budget(request_id="continue-checks", expected_limit=2, new_limit=4,
                                    reason="Fixture second check", expected_state_version=saved["state_version"])
        next_state = project.status()
        grouped = controller.advance(request_id="grouped", expected_state_version=next_state["state_version"])
        self.assertEqual(grouped["result"]["child"]["command"], "data.prediction-grouped")
        self.assertIn(action["id"], grouped["decision"]["reason"])
        revision = self.bind(project, request_id="bind-next", resource=self.resource(2), prediction_column="other")
        self.assertEqual(revision["version"], 2)
        before_replay = project.status()
        with patch.object(prediction_adapter.BASELINE, "execute", side_effect=AssertionError("Replay must use its artifact")):
            replay = project.step(request_id=action["request_id"], method_id=action["command"],
                                  parameters=action["method_instance"]["parameters"], expected_state_version=0)
        self.assertTrue(replay["replayed"])
        self.assertEqual(project.status(), before_replay)
        context = controller.selection_context()
        self.assertTrue(any(item["method_id"] == "data.prediction-baseline" for item in context["candidates"]))
        self.assertEqual(context["baseline_decision"]["next_action"]["method_id"], "data.prediction-baseline")

    def test_adverse_baseline_can_be_group_checked_and_sensitivity_is_saved_without_fits(self):
        project = self.project()
        self.bind(project, prediction_column="other")
        controller = ProjectController(project.root)
        controller.advance(request_id="quality")
        controller.advance(request_id="baseline")
        state = project.status()
        self.assertFalse(state["actions"][-1]["observations"][0]["summary"]["outperforms_reference"])
        project.extend_local_budget(request_id="check-all", expected_limit=2, new_limit=4, reason="Complete fixture checks")
        self.assertTrue(any(item["method_id"] == "data.prediction-grouped" for item in controller.selection_context()["candidates"]))
        final = controller.advance(request_id="sensitivity")
        self.assertEqual(final["result"]["child"]["command"], "data.prediction-sensitivity")
        self.assertIn(state["actions"][-1]["id"], final["decision"]["reason"])
        self.assertEqual(controller.advance(request_id="grouped")["result"]["child"]["command"], "data.prediction-grouped")
        state = project.status()
        self.assertEqual(state["budget"]["local_tool_calls_used"], 4)
        self.assertEqual(state["budget"]["new_fits"], 0)
        artifact = json.loads((project.root / state["actions"][-2]["artifact"]).read_bytes())
        analysis = artifact["tool_result"]["result"]["analysis"]
        self.assertEqual(analysis["schema_version"], "prediction-check-v1")
        self.assertTrue(analysis["details"]["removals"])
        json.dumps(artifact, allow_nan=False)
        project.extend_local_budget(request_id="spare", expected_limit=4, new_limit=5, reason="Observe completed design stop")
        self.assertEqual(controller.next()["status"], "waiting")
        self.assertFalse(controller.next()["executable"])

    def test_bound_design_takes_precedence_over_a_saved_effective_recipe(self):
        project = self.project()
        recipe_path = Path(__file__).resolve().parents[1] / "examples/research-recipes/tabular-group-first.json"
        recipe = json.loads(recipe_path.read_bytes())
        with project._writer(), project._connect() as con:
            state = project._project(con)
            state["recipe_revisions"] = [{"revision": 1, "request_id": "old-recipe", "recipe": recipe}]
            project._save(con, state)
        self.bind(project)
        controller = ProjectController(project.root)
        controller.advance(request_id="quality")
        context = controller.selection_context()
        self.assertEqual(context["baseline_decision"]["next_action"]["method_id"], "data.prediction-baseline")
        self.assertEqual(controller.advance(request_id="design-check")["result"]["child"]["command"], "data.prediction-baseline")

    def test_large_table_stays_available_for_quality_but_prediction_candidates_are_bounded(self):
        text = "group,observed,prediction,other\n" + "".join(f"a,{i},{i},0\n" for i in range(513))
        project = self.project(text)
        self.bind(project)
        controller = ProjectController(project.root)
        self.assertEqual(controller.advance(request_id="quality")["status"], "completed")
        self.assertFalse(any(item["method_id"].startswith("data.prediction-")
                             for item in controller.selection_context()["candidates"]))


if __name__ == "__main__":
    unittest.main()
