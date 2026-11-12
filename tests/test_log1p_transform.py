"""Selected raw log1p inputs retain dimensions, strict comparisons and fit budgets."""

import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

import test_feature_comparison as comparison_fixtures
import test_group_only_design as group_fixtures
import test_tabular_quality_adapter as tabular_fixtures
from autoresearch import input_basis, method_registry as registry
from autoresearch.contracts import ResearchError, canonical
from autoresearch.feature_comparison import compare_feature_checks
from autoresearch.project_controller import ProjectController
from autoresearch.project_design import bind
from autoresearch.research_design import _assessment
from autoresearch.research_project import ResearchProject
from autoresearch.ridge_validation_adapter import GROUPED, _inputs


class Log1pTransformTests(unittest.TestCase):
    capture = tabular_fixtures.TabularQualityAdapterTests.capture
    resource = group_fixtures.GroupOnlyDesignTests.resource
    parameters = staticmethod(group_fixtures.GroupOnlyDesignTests.parameters)

    @staticmethod
    def training(**changes):
        return {"feature_columns": ["x", "z", "age"], "split_group_columns": ["batch"], "fit_limit": 10,
                "input_transforms": {"age": "log1p"}, **changes}

    def packet(self, *, first_age=0, **training_changes):
        text = "id,batch,x,z,age,y\n" + "".join(
            f"r{index},g{index // 2},{index - 7},{index % 3},{first_age if index == 0 else index ** 2},{index * 2 + 1}\n"
            for index in range(12))
        payload, _ = self.capture(text, numeric_columns=["x", "z", "age", "y"])
        payload["design_binding"] = {"version": 1, "source_snapshot_sha256": payload["snapshot_sha256"],
                                    "target_column": "y", "resource": self.resource(),
                                    "training": self.training(**training_changes)}
        return payload

    def project(self, *, first_age=0):
        root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        payload = self.packet(first_age=first_age)
        inputs = root / "inputs"
        inputs.mkdir()
        source = inputs / "source.json"
        source.write_text(canonical({key: value for key, value in payload.items() if key != "design_binding"}), encoding="utf-8")
        project = ResearchProject(root / "project")
        project.create(source=source, goal="Constructed fixed input transform check", budget_ref="test-only:log1p",
                       max_tool_calls=4, method_id="data.tabular-quality-audit")
        raw = self.training()
        del raw["input_transforms"]
        bind(project, request_id="raw-bind", expected_state_version=0, resource=self.resource(),
             prediction_column=None, reason="Raw fixed comparator", training=raw)
        return project, ProjectController(project.root)

    @staticmethod
    def adapter_parameters():
        return {"based_on_action_id": "quality-one", "based_on_result_sha256": "a" * 64}

    def test_selected_columns_preserve_order_dimension_other_values_and_input_bytes(self):
        training = self.training(input_transforms={"age": "log1p", "z": "log1p"})
        before = copy.deepcopy(training)
        x = np.array([[-7.0, 0.0, 3.0], [-4.0, 8.0, -0.5], [2.0, 3.0, 1000.0]])
        raw = x.tobytes()
        expanded = input_basis.expand(x, training)
        self.assertEqual(expanded.shape, x.shape)
        self.assertFalse(np.shares_memory(expanded, x))
        np.testing.assert_array_equal(expanded[:, 0], x[:, 0])
        np.testing.assert_array_equal(expanded[:, 1:], np.log1p(x[:, 1:]))
        self.assertEqual(x.tobytes(), raw)
        metadata = input_basis.protocol(training)
        self.assertEqual(metadata, {
            "input_basis": {"kind": "log1p", "source_columns": ["x", "z", "age"], "transformed_columns": ["z", "age"],
                            "order": "raw_log1p_then_fold_standardization"},
            "model_input_terms": ["x", "log1p(z)", "log1p(age)"]})
        metadata["input_basis"]["source_columns"].append("cannot-mutate-training")
        self.assertEqual(training, before)
        edge = np.array([[np.nextafter(-1.0, 0.0), np.finfo(float).max]])
        result = input_basis.expand(edge, self.training(feature_columns=["x", "age"], input_transforms={"x": "log1p", "age": "log1p"}))
        self.assertTrue(np.isfinite(result).all())

    def test_invalid_declarations_and_domain_reject_before_any_fit(self):
        invalid = [{}, None, [], {"age": "log"}, {"age": "log1p(age)"}, {"age": ["log1p"]},
                   {"missing": "log1p"}, {"batch": "log1p"}, {"y": "log1p"}, {1: "log1p"}]
        packets = [self.packet(input_transforms=transform) for transform in invalid]
        packets.extend([self.packet(first_age=value) for value in (-1, -2)])
        packets.append(self.packet(input_basis="univariate_cubic"))
        with patch("autoresearch.ridge_validation_adapter.StandardScaler.fit") as scaler, \
                patch("autoresearch.ridge_validation_adapter.Ridge.fit") as ridge:
            for payload in packets:
                events = []
                with self.subTest(training=payload["design_binding"]["training"]):
                    with self.assertRaises(ResearchError) as caught:
                        GROUPED.required_fit_attempts(payload)
                    self.assertEqual(caught.exception.code, "INVALID_TRAINING")
                    with self.assertRaises(ResearchError):
                        GROUPED.execute(payload, self.adapter_parameters(), fit_observer=events.append)
                    self.assertEqual(events, [])
            scaler.assert_not_called()
            ridge.assert_not_called()
        for value in (float("nan"), float("inf"), float("-inf")):
            with self.subTest(value=value), self.assertRaises(ResearchError):
                input_basis.expand([[1, 2, value]], self.training())
        with self.assertRaises(ResearchError):
            input_basis.expand([[1, 2]], self.training())

    def test_binding_rejects_invalid_mapping_and_domain_without_state_or_budget_change(self):
        project, _ = self.project(first_age=-1)
        before = project.status()
        invalid = [self.training(), self.training(input_transforms={}), self.training(input_transforms={"y": "log1p"}),
                   self.training(input_transforms={"batch": "log1p"}), self.training(input_transforms={"age": "exp"}),
                   self.training(input_basis="univariate_cubic")]
        with patch("autoresearch.ridge_validation_adapter.StandardScaler.fit") as fitter:
            for index, training in enumerate(invalid):
                with self.subTest(training=training), self.assertRaises(ResearchError) as caught:
                    bind(project, request_id="invalid-log-bind-" + str(index), expected_state_version=before["state_version"],
                         resource={**self.resource(version=2), "comparison_kind": "fixed_input_basis"},
                         prediction_column=None, reason="Reject invalid transform before commit", training=training)
                self.assertEqual(caught.exception.code, "INVALID_TRAINING")
                self.assertEqual(project.status(), before)
            fitter.assert_not_called()

    def test_log1p_does_not_change_complete_case_mask_or_target(self):
        payload = self.packet(first_age=-2)
        # A raw invalid-domain value on a row already excluded for a missing target
        # remains an original exclusion rather than a new transform-specific mask.
        text = "id,batch,x,z,age,y\n" + "".join(
            f"r{i},g{i // 2},{i - 7},{i % 3},{-2 if i == 0 else i ** 2},{'NA' if i == 0 else i * 2 + 1}\n"
            for i in range(12))
        captured, _ = self.capture(text, numeric_columns=["x", "z", "age", "y"])
        captured["design_binding"] = {**payload["design_binding"], "source_snapshot_sha256": captured["snapshot_sha256"]}
        data = _inputs(captured)
        self.assertEqual([row["logical_record"] for row in data["rows"]], list(range(2, 13)))
        self.assertEqual(data["exclusions"], [{"logical_record": 1, "physical_line_end": 2, "reasons": ["target_missing_or_nonfinite"]}])
        self.assertEqual([row["observed"] for row in data["rows"]], [i * 2 + 1 for i in range(1, 12)])

    def test_saved_scaling_and_coefficients_reconstruct_group_oof_with_exactly_ten_fits(self):
        payload, events = self.packet(), []
        self.assertEqual(GROUPED.required_fit_attempts(payload), 10)
        analysis = GROUPED.execute(payload, self.adapter_parameters(), fit_observer=events.append)["result"]["analysis"]
        self.assertEqual(analysis["usage"], {"ridge_fit_attempts": 5, "preprocessing_fit_attempts": 5, "fit_attempts": 10})
        self.assertEqual([(event["index"], event["status"]) for event in events],
                         [(index, status) for index in range(1, 11) for status in ("started", "completed")])
        self.assertEqual({key: analysis["protocol"][key] for key in ("input_basis", "model_input_terms")},
                         input_basis.protocol(payload["design_binding"]["training"]))
        x = np.array([[i - 7, i % 3, np.log1p(i ** 2)] for i in range(12)])
        for fold in analysis["folds"]:
            train, test = np.array(fold["train_records"]) - 1, np.array(fold["test_records"]) - 1
            np.testing.assert_allclose(fold["scaler_mean"], x[train].mean(axis=0), rtol=1e-13, atol=1e-13)
            np.testing.assert_allclose(fold["scaler_scale"], x[train].std(axis=0), rtol=1e-13, atol=1e-13)
            self.assertEqual(len(fold["ridge_coefficients"]), 3)
            rebuilt = ((x[test] - fold["scaler_mean"]) / fold["scaler_scale"]) @ fold["ridge_coefficients"] + fold["ridge_intercept"]
            np.testing.assert_allclose(rebuilt, [analysis["oof"][index]["predicted"] for index in test], rtol=1e-13, atol=1e-13)
            self.assertAlmostEqual(fold["reference_prediction"], np.mean([i * 2 + 1 for i in train]))

    def test_bound_child_adds_only_ten_cumulative_fits_and_replays_without_execution(self):
        project, controller = self.project()
        controller.advance(request_id="quality")
        controller.advance(request_id="raw-group")
        before = project.status()
        originals = {action["artifact"]: (project.root / action["artifact"]).read_bytes() for action in before["actions"]}
        request = {"request_id": "log-bind", "expected_state_version": before["state_version"],
                   "resource": {**self.resource(version=2), "comparison_kind": "fixed_input_basis"},
                   "prediction_column": None, "reason": "One fixed explicit age transform",
                   "training": self.training(fit_limit=20)}
        revision = bind(project, **request)
        self.assertEqual(revision["fit_requirements"], {"group_cv": 10})
        self.assertEqual(project.status()["budget"]["fit_attempts_used"], 10)
        controller.advance(request_id="log-group")
        finished = project.status()
        self.assertEqual((finished["budget"]["fit_attempts_used"], finished["budget"]["fits_completed"], finished["budget"]["fits_reserved"]), (20, 20, 0))
        self.assertEqual(finished["actions"][:-1], before["actions"])
        self.assertTrue(all((project.root / name).read_bytes() == raw for name, raw in originals.items()))
        with patch.object(registry.RIDGE["data.ridge-group-validation"], "execute", side_effect=AssertionError("No replay fit")):
            self.assertEqual(bind(project, **request), revision)
            self.assertTrue(controller.advance(request_id="log-group")["replayed"])
            self.assertTrue(controller.advance(request_id="raw-group")["replayed"])
        self.assertEqual(project.status(), finished)


class Log1pComparisonTests(unittest.TestCase):
    def records(self):
        records = comparison_fixtures.FeatureComparisonTests().records()
        for record in records:
            record["protocol"]["feature_columns"] = ["geometry", "speed"]
            record["design_binding"]["training"] = {"feature_columns": ["geometry", "speed"],
                "split_group_columns": ["signature"], "fit_limit": 20}
        candidate = records[1]
        candidate["design_binding"]["resource"].update(comparison_kind="fixed_input_basis", checks=["group_cv"])
        candidate["design_binding"]["training"]["input_transforms"] = {"speed": "log1p"}
        candidate["protocol"].update(input_basis.protocol(candidate["design_binding"]["training"]))
        candidate["summary"] = {"candidate_mae": 0.5, "reference_mae": 2.0, "improvement": 0.75, "n": 4, "group_count": 2}
        return records

    def test_explicit_selected_transform_uses_saved_parent_assessment_without_mutation(self):
        records = self.records()
        before = copy.deepcopy(records)
        comparison, = compare_feature_checks(records)
        self.assertEqual(comparison["status"], "comparable")
        self.assertEqual(comparison["candidate_ref"]["model_input_terms"], ["geometry", "log1p(speed)"])
        self.assertEqual(comparison["baseline_ref"]["input_basis"], {"kind": "raw", "source_columns": ["geometry", "speed"]})
        candidate = records[1]
        result = _assessment(candidate["design_binding"]["resource"], [candidate], {}, [comparison])
        self.assertEqual(result["claim_scope"], "saved_parent_mae")
        self.assertIs(result["claim_supported"], True)
        self.assertFalse(result["scientific_validation"])
        self.assertEqual(records, before)

    def test_frozen_metadata_mapping_order_other_protocol_and_raw_parent_are_required(self):
        changes = [lambda left, right: right["protocol"]["input_basis"].update(transformed_columns=["geometry"]),
                   lambda left, right: right["protocol"]["input_basis"].update(source_columns=["speed", "geometry"]),
                   lambda left, right: right["protocol"]["input_basis"].update(order="fold_standardization_then_log1p"),
                   lambda left, right: right["protocol"].update(model_input_terms=["log1p(speed)", "geometry"]),
                   lambda left, right: right["protocol"].pop("model_input_terms"),
                   lambda left, right: right["protocol"].update(feature_columns=["speed", "geometry"]),
                   lambda left, right: right["design_binding"]["training"].update(feature_columns=["speed", "geometry"]),
                   lambda left, right: right["design_binding"]["training"].update(input_transforms={"geometry": "log1p"}),
                   lambda left, right: right["design_binding"]["training"].update(input_transforms={"speed": "exp"}),
                   lambda left, right: right["design_binding"]["training"].update(input_basis="univariate_cubic"),
                   lambda left, right: left["design_binding"]["training"].update(input_transforms={}),
                   lambda left, right: left["design_binding"]["training"].update(input_basis="univariate_cubic"),
                   lambda left, right: left["protocol"].update(model_input_terms=["geometry", "speed"]),
                   lambda left, right: right["protocol"].update(ridge_alpha=2.0),
                   lambda left, right: right["protocol"].update(preprocessing="global standardization"),
                   lambda left, right: right["protocol"].update(n_splits=4)]
        for index, change in enumerate(changes):
            records = self.records()
            change(*records)
            with self.subTest(change=index):
                result, = compare_feature_checks(records)
                self.assertEqual(result["status"], "not_comparable")
                self.assertIn("PROTOCOL_MISMATCH", result["reason_codes"])
                self.assertNotIn("metrics", result)

    def test_ordinary_feature_comparison_and_raw_to_raw_cannot_use_transform_contrast(self):
        records = self.records()
        del records[1]["design_binding"]["resource"]["comparison_kind"]
        self.assertEqual(compare_feature_checks(records)[0]["status"], "not_comparable")
        records = self.records()
        del records[1]["design_binding"]["training"]["input_transforms"]
        for key in ("input_basis", "model_input_terms"):
            del records[1]["protocol"][key]
        self.assertEqual(compare_feature_checks(records)[0]["status"], "not_comparable")

    def test_transform_contrast_preserves_every_saved_evaluation_gate(self):
        changes = {"SOURCE_SNAPSHOT_MISMATCH": lambda item: item.update(source_snapshot_sha256="b" * 64),
                   "TARGET_MISMATCH": lambda item: item.update(target_column="another-target"),
                   "ROW_COVERAGE_MISMATCH": lambda item: item["oof"].pop(),
                   "ROW_COORDINATES_MISMATCH": lambda item: item["oof"][0].update(physical_line_end=20),
                   "OBSERVED_MISMATCH": lambda item: item["oof"][0].update(observed=100.0),
                   "GROUPS_MISMATCH": lambda item: item["oof"][0].update(groups=["another"]),
                   "FOLD_ASSIGNMENT_MISMATCH": lambda item: item["oof"][0].update(fold=2),
                   "FOLD_RECORDS_MISMATCH": lambda item: item["folds"][0].update(train_records=[2, 4]),
                   "REFERENCE_PREDICTION_MISMATCH": lambda item: item["oof"][0].update(reference_prediction=9.0),
                   "MODEL_PARAMETERS_MISMATCH": lambda item: item["folds"][0]["model_params"].update(alpha=2.0)}
        for reason, change in changes.items():
            records = self.records()
            change(records[1])
            with self.subTest(reason=reason):
                result, = compare_feature_checks(records)
                self.assertEqual(result["status"], "not_comparable")
                self.assertIn(reason, result["reason_codes"])
                self.assertNotIn("metrics", result)


if __name__ == "__main__":
    unittest.main()
