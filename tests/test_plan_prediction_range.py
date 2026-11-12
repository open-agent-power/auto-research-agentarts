"""New plan/recipe captures preserve saved OOF facts and legacy Host originals."""

import copy
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

import test_group_only_design as group_fixtures
import test_recipe_improvement as improvement_fixtures
import test_recipe_improvement_adapter as adapter_fixtures
from autoresearch import recipe_change_proposal as recipe_protocol, research_plan_proposal as plan_protocol
from autoresearch import recipe_improvement as improvement, ridge_validation_adapter as ridge
from autoresearch.contracts import ResearchError, canonical
from autoresearch.host_model_selection import HostModelSelection
from autoresearch.plan_feedback import project_observations
from autoresearch.prediction_summary import summarize_oof_range
from autoresearch.project_design import bind
from autoresearch.project_report import collect_report
from autoresearch.project_selection import budget_cost_notice
from autoresearch.research_design import _records
from autoresearch.research_project import ResearchProject


def files(root):
    return {path.relative_to(root).as_posix(): path.read_bytes() for path in root.rglob("*") if path.is_file()}


class PlanPredictionRangeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixture = group_fixtures.GroupOnlyDesignTests()
        cls.addClassCleanup(fixture.doCleanups)
        cls.project, controller = fixture.project(groups=2, fit_limit=4)
        cls.legacy = plan_protocol.build_context(cls.project)
        cls.specification = {"request_id": "before-oof", "provider": "delegated", "purpose": "plan",
            "expected_state_version": cls.project.status()["state_version"], "decision_limit": 1,
            "cli_budget_usd": 0.1, "reason": "Freeze an engineering request; no model dispatch"}
        cls.old_host = HostModelSelection(cls.project.root).prepare(**cls.specification)
        cls.old_host_bytes = files(cls.project.root / "host-model-selections")
        calls = []
        scaler_fit, ridge_fit = ridge.StandardScaler.fit, ridge.Ridge.fit

        def fit_scaler(estimator, *args, **kwargs):
            calls.append("StandardScaler")
            return scaler_fit(estimator, *args, **kwargs)

        def fit_ridge(estimator, *args, **kwargs):
            calls.append("Ridge")
            return ridge_fit(estimator, *args, **kwargs)

        with patch.object(ridge.StandardScaler, "fit", fit_scaler), patch.object(ridge.Ridge, "fit", fit_ridge):
            result = controller.advance(request_id="saved-oof-group")
        if result["result"]["child"]["command"] != "data.ridge-group-validation" or calls != ["StandardScaler", "Ridge"] * 2:
            raise AssertionError((result, calls))
        print("A122 new engineering CV: one 12-row/two-group native run; actual fit calls=" + repr(calls), flush=True)
        cls.state = cls.project.status()
        cls.saved_files = files(cls.project.root)
        cls.recipe = json.loads((Path(__file__).resolve().parents[1] /
                               "examples/research-recipes/tabular-group-first.json").read_bytes())

    def setUp(self):
        self.addCleanup(lambda: self.assertEqual(self.project.status(), self.state))
        self.addCleanup(lambda: self.assertEqual(files(self.project.root), self.saved_files))

    def test_current_capture_matches_saved_oof_report_and_preserves_original_observations(self):
        with patch.object(ridge.StandardScaler, "fit", side_effect=AssertionError("A range capture must not fit")), \
             patch.object(ridge.Ridge, "fit", side_effect=AssertionError("A range capture must not fit")):
            context = plan_protocol.build_context(self.project)
            change = recipe_protocol.build_context(self.project, self.recipe, "Inspect saved ranges before revising.")
            report = collect_report(self.project.root)
        record, = _records(self.project, self.state)
        rows = record["oof"]
        observed, predicted = [row["observed"] for row in rows], [row["predicted"] for row in rows]
        expected = {"n": len(rows), "observed_min": min(observed), "observed_max": max(observed),
            "predicted_min": min(predicted), "predicted_max": max(predicted),
            "negative_predictions": sum(value < 0 for value in predicted),
            "below_observed_min": sum(value < min(observed) for value in predicted),
            "above_observed_max": sum(value > max(observed) for value in predicted), "scientific_validation": False}
        ranges = [{"action_id": record["action_id"], "check": "group_cv", "summary": expected}]
        self.assertEqual(context["prediction_ranges"], ranges)
        self.assertEqual(change["research_context"], context)
        self.assertEqual(report["prediction_ranges"], ranges)
        for feedback, action in zip(context["feedback"], self.state["actions"]):
            self.assertEqual(feedback["observations"], project_observations(action["observations"], action["artifact"]))
            self.assertEqual(feedback["artifact_ref"], action["artifact"])
            for observation in feedback["observations"]:
                self.assertNotIn("prediction_range", observation)
                self.assertNotIn("prediction_range", observation.get("summary", {}))
        matching = next(item for item in context["feedback"] if item["action_id"] == record["action_id"])
        self.assertEqual(matching["observations"][0]["design_binding"]["version"], self.state["design_revisions"][-1]["version"])
        context["prediction_ranges"][0]["summary"]["n"] = 999
        self.assertEqual(plan_protocol.build_context(self.project)["prediction_ranges"], ranges)
        self.assertEqual(self.state["budget"]["fit_attempts_used"], 4)

    def test_rebinding_excludes_historical_cv_without_refitting(self):
        root = Path(self.enterContext(tempfile.TemporaryDirectory())) / "project"
        shutil.copytree(self.project.root, root, ignore=shutil.ignore_patterns("host-model-selections"))
        project = ResearchProject(root)
        fixture = group_fixtures.GroupOnlyDesignTests()
        bind(project, request_id="range-next-binding", expected_state_version=project.status()["state_version"],
             resource=fixture.resource(version=2), prediction_column=None,
             training={"feature_columns": ["speed"], "split_group_columns": ["group"], "fit_limit": 4},
             reason="The old OOF belongs to the previous binding; do not retrain")
        before, original = project.status(), files(root)
        with patch.object(ridge.Ridge, "fit", side_effect=AssertionError("Rebinding must not train")):
            context = plan_protocol.build_context(project)
        self.assertNotIn("prediction_ranges", context)
        self.assertEqual(len([item for item in context["feedback"] if item["method_id"] == "data.ridge-group-validation"]), 1)
        self.assertEqual(project.status(), before)
        self.assertEqual(files(root), original)

    def test_zero_negative_and_null_ranges_remain_descriptive_in_both_prompts(self):
        context = plan_protocol.build_context(self.project)
        rows = [{"observed": actual, "predicted": predicted} for actual, predicted in [(-5, -6), (-2, 0), (0, 1)]]
        summary = summarize_oof_range(rows)
        self.assertEqual(summary, {"n": 3, "observed_min": -5, "observed_max": 0, "predicted_min": -6,
            "predicted_max": 1, "negative_predictions": 1, "below_observed_min": 1,
            "above_observed_max": 1, "scientific_validation": False})
        zero = summarize_oof_range([{"observed": 0, "predicted": 0}])
        for value in (summary, zero, None):
            with self.subTest(summary=value):
                record, = _records(self.project, self.state)
                record["prediction_range"] = value
                with patch("autoresearch.research_design._records", return_value=[record]):
                    captured = plan_protocol.build_context(self.project)
                self.assertEqual(captured["prediction_ranges"][0]["summary"], value)
                self.assertEqual(plan_protocol._context(captured), captured)
                change = {"schema_version": "recipe-change-context-v1", "research_context": captured,
                          "current_recipe": self.recipe, "improvement_goal": "Keep unknown and zero separate."}
                notice = plan_protocol.prediction_range_notice(captured)
                for protocol, payload in ((plan_protocol, captured), (recipe_protocol, change)):
                    prompt = protocol.build_prompt(payload)
                    self.assertEqual(prompt["system"].count(notice), 1)
                    self.assertIn("absent or null summary is unknown, not zero", prompt["system"])
                    self.assertIn("a count of 0 is an actual zero count", prompt["system"])
                    self.assertIn("not physical or engineering limits", prompt["system"])
                    self.assertIn("do not change saved observations or fit models", prompt["system"])
                    self.assertIn("no scientific approval", prompt["system"])
                    budget_notice = budget_cost_notice(captured["selection_context"])
                    self.assertTrue(budget_notice)
                    self.assertEqual(prompt["system"].count(budget_notice), 1)
                    self.assertIn(canonical(payload), prompt["prompt"])
        self.assertIsNone(summarize_oof_range([]))
        self.assertEqual(context, plan_protocol.build_context(self.project))

    def test_optional_field_checks_saved_action_check_summary_shape_and_false_scientific_flag(self):
        context = plan_protocol.build_context(self.project)
        mutations = [lambda c: c.update(prediction_ranges=None), lambda c: c.update(prediction_ranges=[]),
            lambda c: c["prediction_ranges"][0].update(extra="unknown"),
            lambda c: c["prediction_ranges"][0].update(action_id="unrecorded"),
            lambda c: c["prediction_ranges"][0].update(check="negative_control"),
            lambda c: c["prediction_ranges"][0].update(check="random_cv"),
            lambda c: c["prediction_ranges"].append(copy.deepcopy(c["prediction_ranges"][0])),
            lambda c: c["feedback"][-1].update(status="failed"),
            lambda c: c["feedback"][-1].update(artifact_ref=None),
            lambda c: c["feedback"][-1]["observations"][0].update(check="random_cv"),
            lambda c: c["prediction_ranges"][0]["summary"].update(scientific_validation=True),
            lambda c: c["prediction_ranges"][0]["summary"].update(n=True),
            lambda c: c["prediction_ranges"][0]["summary"].update(negative_predictions=None),
            lambda c: c["prediction_ranges"][0]["summary"].update(negative_predictions=-1),
            lambda c: c["prediction_ranges"][0]["summary"].update(observed_min="unknown"),
            lambda c: c["prediction_ranges"][0]["summary"].pop("above_observed_max")]
        for index, mutate in enumerate(mutations):
            with self.subTest(mutation=index):
                invalid = copy.deepcopy(context)
                mutate(invalid)
                with self.assertRaises(ResearchError) as caught:
                    plan_protocol._context(invalid)
                self.assertEqual(caught.exception.code, "INVALID_PLAN_CONTEXT")
        invalid = {**copy.deepcopy(context), "schema_version": "research-plan-context-v1"}
        for name in ("saved_comparisons", "remaining_questions"):
            invalid.pop(name)
        with self.assertRaises(ResearchError):
            plan_protocol._context(invalid)

    def test_absent_ranges_leave_v1_v2_complete_prompts_and_old_host_bytes_unchanged(self):
        self.assertNotIn("prediction_ranges", self.legacy)
        v1 = {key: copy.deepcopy(self.legacy[key]) for key in ("schema_version", "selection_context", "feedback")}
        v1["schema_version"] = "research-plan-context-v1"
        for research in (v1, self.legacy):
            self.assertEqual(plan_protocol.prediction_range_notice(research), "")
            change = {"schema_version": "recipe-change-context-v1", "research_context": research,
                      "current_recipe": self.recipe, "improvement_goal": "Review the frozen quality result."}
            for protocol, payload in ((plan_protocol, research), (recipe_protocol, change)):
                raw = canonical(payload).encode("utf-8")
                prompt = protocol.build_prompt(payload)
                with patch.object(plan_protocol, "prediction_range_notice", return_value=""):
                    self.assertEqual(protocol.build_prompt(json.loads(raw)), prompt)
                self.assertNotIn("prediction_ranges", canonical(prompt))
                self.assertEqual(canonical(payload).encode("utf-8"), raw)
        journal = HostModelSelection(self.project.root)
        self.assertEqual(journal.prepare(**self.specification), self.old_host)
        self.assertEqual(plan_protocol.build_prompt(self.old_host["context"]), self.old_host["prompt"])
        self.assertEqual(files(journal.directory), self.old_host_bytes)

    def test_old_v2_received_context_stays_stale_and_retains_originals_without_resending(self):
        root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        project_root = root / "project"
        shutil.copytree(self.project.root, project_root, ignore=shutil.ignore_patterns("host-model-selections"))
        project = ResearchProject(project_root)
        journal = HostModelSelection(project_root)
        original_builder = plan_protocol.build_context

        def previous_v2(project, need="next_check"):
            context = original_builder(project, need)
            context.pop("prediction_ranges")
            return context

        specification = {**self.specification, "request_id": "old-v2-with-cv",
                         "expected_state_version": project.status()["state_version"]}
        with patch.object(plan_protocol, "build_context", previous_v2):
            prepared = journal.prepare(**specification)
        frozen = files(journal.directory / prepared["directory"])
        response = root / "constructed-plan.json"
        response.write_bytes(canonical({"plan": {"question": "Inspect saved predictions.", "basis": "Saved CV feedback.",
            "steps": "Review the recorded result.", "expected_feedback": "Confirm the interpretation boundary."},
            "reason": "Engineering protocol fixture, without model dispatch.",
            "feedback_action_ids": [project.status()["actions"][-1]["id"]],
            "expected_improvement": "Preserve the original frozen request."}).encode("utf-8"))
        received = journal.import_response(request_id=specification["request_id"], response_file=response)
        before, usage = project.status(), journal.status()["usage"]
        raw_path = journal.directory / received["response_file"]
        raw = raw_path.read_bytes()
        stale = journal.consume(request_id=specification["request_id"])
        self.assertEqual(stale["status"], "stale")
        self.assertEqual(stale["error"]["code"], "STALE_SELECTION_CONTEXT")
        self.assertEqual(stale["context"], prepared["context"])
        self.assertEqual(stale["prompt"], prepared["prompt"])
        for relative, content in frozen.items():
            self.assertEqual((journal.directory / prepared["directory"] / relative).read_bytes(), content)
        terminal_bytes = files(project_root)
        self.assertEqual(journal.prepare(**specification), stale)
        self.assertEqual(journal.import_response(request_id=specification["request_id"], response_file=response), stale)
        self.assertEqual(files(project_root), terminal_bytes)
        self.assertEqual(raw_path.read_bytes(), raw)
        self.assertEqual(journal.status()["usage"], usage)
        self.assertEqual(project.status(), before)
        self.assertFalse(stale["cli_launch_attempted"])

    def test_new_range_recipe_export_is_consumed_by_original_offline_rsi_reader(self):
        fixture = improvement_fixtures.RecipeImprovementTests()
        self.addCleanup(fixture.doCleanups)
        fixture.setUp()
        original_setup = adapter_fixtures.RecipeImprovementAdapterTests.setUp

        def setup_with_saved_cv(adapter_fixture):
            original_setup(adapter_fixture)
            clone = adapter_fixture.root / "saved-cv-clone"
            shutil.copytree(self.project.root, clone, ignore=shutil.ignore_patterns("host-model-selections"))
            imported = adapter_fixture.manager.import_project(request_id="import-saved-cv", workspace=clone)
            adapter_fixture.manager.select({"request_id": "select-saved-cv", "project_id": imported["project_id"]})
            adapter_fixture.project, _ = adapter_fixture.manager.binding()
            adapter_fixture.options["workspace"] = adapter_fixture.project.root

        with patch.object(adapter_fixtures.RecipeImprovementAdapterTests, "setUp", setup_with_saved_cv), \
             patch.object(ridge.Ridge, "fit", side_effect=AssertionError("Reuse the one saved engineering CV")):
            adapter_fixture, exported, record, candidate, _ = fixture.saved_export_fixture()
        ranges = record["context"]["research_context"]["prediction_ranges"]
        self.assertEqual(ranges, plan_protocol.build_context(self.project)["prediction_ranges"])
        before, host_before = adapter_fixture.project.status(), HostModelSelection(adapter_fixture.project.root).status()
        originals, project_originals = files(exported), files(adapter_fixture.project.root)
        inputs = improvement.load_saved_export(exported)
        self.assertEqual(inputs["trace"]["prediction_ranges"], ranges)
        self.assertEqual(inputs["trace"]["feedback"], record["context"]["research_context"]["feedback"])
        result = improvement.run_improvement_round(**inputs, directory=fixture.directory, round_id="saved-oof-range",
            evidence_kind="saved_export_validation", issue={"summary": "Saved CV motivates a source review.",
            "feedback_action_ids": candidate["feedback_action_ids"]}, acceptance=improvement_fixtures.SOURCE,
            next_question="Review the source definitions before making a scientific claim.")
        self.assertEqual(result["decision"], "keep")
        self.assertEqual(improvement.read_improvement_round(fixture.directory, "saved-oof-range"), result)
        self.assertEqual(adapter_fixture.project.status(), before)
        self.assertEqual(HostModelSelection(adapter_fixture.project.root).status(), host_before)
        self.assertEqual(files(exported), originals)
        self.assertEqual(files(adapter_fixture.project.root), project_originals)


if __name__ == "__main__":
    unittest.main()
