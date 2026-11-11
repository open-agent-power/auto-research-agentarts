"""Group-only raw designs reuse original execution, budgets and saved evidence."""

import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from autoresearch import method_registry as registry, tabular_quality_adapter as tabular
from autoresearch.contracts import ResearchError, canonical
from autoresearch.project_controller import ProjectController
from autoresearch.project_design import bind, check_eligible, family, preferred_checks, validate_resource
from autoresearch.research_design import RAW_RESOURCE, RESOURCE, _assessment, _records
from autoresearch.research_project import ResearchProject


class GroupOnlyDesignTests(unittest.TestCase):
    def resource(self, checks=("group_cv",), version=1):
        return {**copy.deepcopy(RAW_RESOURCE), "id": "group-only-fixture", "version": version,
                "checks": list(checks), "parent_version": version - 1 if version > 1 else None,
                "change_reason": "Compare declared feature roles on the same group split"}

    def project(self, checks=("group_cv",), fit_limit=10, groups=6):
        root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        inputs = root / "inputs"
        inputs.mkdir()
        raw = "group,speed,shape,target\n" + "".join(
            f"g{index % groups},{index % 2 + 1},{index // 2},{3 * (index // 2) + index % 2 + 1}\n"
            for index in range(12))
        (inputs / "data.csv").write_text(raw, encoding="utf-8")
        spec = {"schema_version": "tabular-quality-spec-v1", "file": "data.csv", "dataset_label": "Group-only fixture",
                "source_url": "urn:test:group-only", "license_note": "Constructed fixture", "sample_unit": "declared record",
                "group_columns": ["group"], "key_columns": [], "numeric_columns": ["speed", "shape", "target"],
                "target_column": "target", "target_unit": "fixture unit", "missing_tokens": [""], "delimiter": ",",
                "provenance": {"origin_sha256": "a" * 64, "description": "Constructed bounded input"}}
        (inputs / "spec.json").write_text(canonical(spec), encoding="utf-8")
        source = inputs / "source.json"
        source.write_text(canonical(tabular.capture_source(inputs)), encoding="utf-8")
        project = ResearchProject(root / "project")
        project.create(source=source, goal="Check a feature subset without repeating random CV", budget_ref="test-only:group",
                       max_tool_calls=8, method_id=tabular.TOOL_ID)
        bind(project, request_id="bind-group", expected_state_version=0, resource=self.resource(checks),
             prediction_column=None, training={"feature_columns": ["speed", "shape"], "split_group_columns": ["group"],
                                               "fit_limit": fit_limit}, reason="Initial fixed group comparison")
        controller = ProjectController(project.root)
        controller.advance(request_id="quality")
        return project, controller

    @staticmethod
    def parameters(project):
        action = project.status()["actions"][0]
        return {"based_on_action_id": action["id"], "based_on_result_sha256": action["result_sha256"]}

    def test_group_only_control_and_subset_revision_preserve_cumulative_fits_and_original_replay(self):
        project, controller = self.project(checks=("group_cv", "negative_control"))
        context = controller.selection_context()
        candidates = {item["method_id"] for item in context["candidates"]}
        self.assertIn("data.ridge-group-validation", candidates)
        self.assertNotIn("data.ridge-random-validation", candidates)
        self.assertNotIn("data.prediction-negative-control", candidates)
        self.assertFalse(check_eligible(project.status(), "negative_control"))
        result = controller.advance(request_id="group-original")
        self.assertEqual(result["result"]["child"]["command"], "data.ridge-group-validation")
        group_action = project.status()["actions"][-1]
        self.assertEqual(project.status()["budget"]["fit_attempts_used"], 10)
        self.assertEqual(len(group_action["fit_events"]), 10)
        self.assertTrue(check_eligible(project.status(), "negative_control"))
        controller.advance(request_id="control-original")
        before = project.status()
        self.assertEqual(before["actions"][-1]["generated_prediction_ref"]["action_id"], group_action["id"])
        original_results = {action["artifact"]: (project.root / action["artifact"]).read_bytes() for action in before["actions"]}
        original_actions = copy.deepcopy(before["actions"])
        request = {"request_id": "bind-subset", "expected_state_version": before["state_version"],
                   "resource": self.resource(version=2), "prediction_column": None, "reason": "Inspect the speed-only comparator",
                   "training": {"feature_columns": ["speed"], "split_group_columns": ["group"], "fit_limit": 20}}
        revision = bind(project, **request)
        rebound = project.status()
        self.assertEqual(rebound["actions"], original_actions)
        self.assertEqual((rebound["budget"]["fit_attempts_used"], rebound["budget"]["fit_limit"]), (10, 20))
        self.assertEqual(rebound["budget_revisions"][-1]["fit_attempts_preserved"], 10)
        self.assertEqual(preferred_checks(rebound), ["group_cv"])
        self.assertFalse(check_eligible(rebound, "negative_control"))
        result = controller.advance(request_id="group-subset")
        self.assertEqual(result["result"]["child"]["command"], "data.ridge-group-validation")
        finished = project.status()
        self.assertEqual((finished["budget"]["fit_attempts_used"], finished["budget"]["fits_reserved"]), (20, 0))
        self.assertEqual(finished["actions"][:len(original_actions)], original_actions)
        self.assertTrue(all((project.root / name).read_bytes() == raw for name, raw in original_results.items()))
        records = _records(project, finished)
        self.assertEqual([item["check"] for item in records], ["group_cv"])
        assessment = _assessment(revision["resource"], records, finished["source_scope"])
        self.assertNotIn("random_cv_mae", assessment["comparison"])
        self.assertNotIn("group_to_random_mae_ratio", assessment["comparison"])
        self.assertNotIn("conditional_rank", assessment["comparison"])
        with patch.object(registry.RIDGE["data.ridge-group-validation"], "execute", side_effect=AssertionError("No replay fit")):
            self.assertEqual(bind(project, **request), revision)
            self.assertTrue(project.step(request_id=group_action["request_id"], method_id=group_action["command"],
                                         parameters=self.parameters(project))["replayed"])
            self.assertTrue(controller.advance(request_id="group-subset")["replayed"])
        self.assertEqual(project.status(), finished)

    def test_default_full_design_keeps_random_before_group_and_control(self):
        project, controller = self.project(checks=("random_cv", "group_cv", "negative_control"), fit_limit=20)
        self.assertEqual(preferred_checks(project.status()), ["random_cv", "group_cv", "negative_control"])
        self.assertTrue(check_eligible(project.status(), "group_cv"))
        self.assertEqual(controller.advance(request_id="default-first")["result"]["child"]["command"], "data.ridge-random-validation")
        self.assertEqual(controller.next()["decision"]["next_action"]["method_id"], "data.ridge-group-validation")
        self.assertEqual(project.status()["budget"]["fit_attempts_used"], 10)

    def test_group_only_insufficient_fit_budget_is_blocked_before_dispatch(self):
        project, controller = self.project(fit_limit=9)
        before = project.status()
        self.assertNotIn("data.ridge-group-validation", [item["method_id"] for item in controller.selection_context()["candidates"]])
        with patch.object(registry.RIDGE["data.ridge-group-validation"], "execute", side_effect=AssertionError("No over-budget fit")):
            with self.assertRaises(ResearchError) as caught:
                project.step(request_id="over-budget", method_id="data.ridge-group-validation", parameters=self.parameters(project))
        self.assertEqual(caught.exception.code, "FIT_BUDGET_EXHAUSTED")
        self.assertEqual(project.status(), before)

    def test_missing_groups_and_negative_only_are_rejected_without_fitting(self):
        self.assertEqual(family(validate_resource(self.resource())), "raw")
        self.assertEqual(family(validate_resource(RESOURCE)), "saved")
        with self.assertRaises(ResearchError) as caught:
            validate_resource(self.resource(checks=("negative_control",)))
        self.assertEqual(caught.exception.code, "INVALID_DESIGN")
        with self.assertRaises(ResearchError) as caught:
            self.project(groups=1)
        self.assertEqual(caught.exception.code, "UNSUPPORTED_SCOPE")

    def test_unknown_group_execution_retains_reservation_and_blocks_rebinding(self):
        project, controller = self.project()
        def interrupt(payload, parameters, fit_observer=None):
            fit_observer({"index": 1, "estimator": "scaler", "fold": 1, "status": "started"})
            raise KeyboardInterrupt("Constructed interruption before a completed estimator result")
        with patch.object(registry.RIDGE["data.ridge-group-validation"], "execute", side_effect=interrupt):
            with self.assertRaises(KeyboardInterrupt):
                project.step(request_id="unknown-group", method_id="data.ridge-group-validation", parameters=self.parameters(project))
        self.assertEqual(project.resume(request_id="unknown-group")["status"], "unknown")
        before = project.status()
        self.assertEqual((before["budget"]["fit_attempts_used"], before["budget"]["fits_reserved"]), (1, 9))
        self.assertEqual(controller.selection_context()["candidates"], [])
        with self.assertRaises(ResearchError) as caught:
            bind(project, request_id="cannot-rebind-unknown", expected_state_version=before["state_version"],
                 resource=self.resource(version=2), prediction_column=None, reason="An unknown execution cannot be bypassed",
                 training={"feature_columns": ["speed"], "split_group_columns": ["group"], "fit_limit": 20})
        self.assertEqual(caught.exception.code, "EXECUTION_UNKNOWN")
        self.assertEqual(project.status(), before)

    def test_assessment_uses_only_configured_checks_without_fabricated_comparisons(self):
        group = {"check": "group_cv", "summary": {"candidate_mae": 2.0, "improvement": 0.25, "group_count": 6, "n": 12}}
        ignored = [{"check": "random_cv", "summary": {"candidate_mae": 10.0, "improvement": -1.0}},
                   {"check": "negative_control", "summary": {"alignment_supported": False, "conditional_rank": 0.9}}]
        resource = self.resource()
        result = _assessment(resource, [group, *ignored], {})
        self.assertTrue(result["claim_supported"])
        self.assertFalse(result["scientific_validation"])
        self.assertEqual(result["comparison"], {"group_cv_mae": 2.0, "group_count": 6,
                                               "all_groups_singleton": False, "train_sizes": {"group_cv": []}})
        self.assertNotIn("重排", result["reason"])
        missing = _assessment(self.resource(checks=("group_cv", "negative_control")), [group], {})
        self.assertIsNone(missing["claim_supported"])
        self.assertEqual(missing["missing_checks"], ["negative_control"])
        failed = _assessment(self.resource(checks=("group_cv", "negative_control")), [group, ignored[-1]], {})
        self.assertFalse(failed["claim_supported"])


if __name__ == "__main__":
    unittest.main()
