"""Fixed cubic inputs preserve raw protocols, fold isolation and durable budgets."""

import copy
from pathlib import Path
import unittest
from unittest.mock import patch

import numpy as np

import test_group_only_design as group_fixtures
import test_tabular_quality_adapter as tabular_fixtures
from autoresearch import input_basis, method_registry as registry
from autoresearch.contracts import ResearchError
from autoresearch.project_design import bind, validate_resource
from autoresearch.research_design import RESOURCE
from autoresearch.research_project import code_identity
from autoresearch.ridge_validation_adapter import GROUPED


class InputBasisTests(unittest.TestCase):
    capture = tabular_fixtures.TabularQualityAdapterTests.capture
    resource = group_fixtures.GroupOnlyDesignTests.resource
    project = group_fixtures.GroupOnlyDesignTests.project
    parameters = staticmethod(group_fixtures.GroupOnlyDesignTests.parameters)

    def training(self, **changes):
        return {"feature_columns": ["x"], "split_group_columns": ["batch"], "fit_limit": 10, **changes}

    def packet(self, *, basis=None, limit=10, large=False):
        text = "id,batch,x,y\n" + "".join(
            f"r{index},g{index // 2},{'1e200' if large else index - 4},{(index - 4) ** 3 + 2 * index}\n"
            for index in range(10))
        payload, _ = self.capture(text)
        training = self.training(fit_limit=limit)
        if basis is not None:
            training["input_basis"] = basis
        payload["design_binding"] = {"version": 1, "source_snapshot_sha256": payload["snapshot_sha256"],
                                    "target_column": "y", "resource": {"checks": ["group_cv"]}, "training": training}
        return payload

    @staticmethod
    def adapter_parameters():
        return {"based_on_action_id": "quality-one", "based_on_result_sha256": "a" * 64}

    def test_math_order_is_original_scale_powers_without_bias_and_raw_metadata_is_empty(self):
        training = self.training(input_basis="univariate_cubic")
        before = copy.deepcopy(training)
        x = np.array([[-2.0], [0.0], [3.0]])
        np.testing.assert_array_equal(input_basis.expand(x, training), [[-2, 4, -8], [0, 0, 0], [3, 9, 27]])
        np.testing.assert_array_equal(x, [[-2], [0], [3]])
        self.assertEqual(input_basis.protocol(training), {
            "input_basis": {"kind": "univariate_cubic", "source_columns": ["x"], "powers": [1, 2, 3],
                            "include_bias": False, "order": "raw_powers_then_fold_standardization"},
            "model_input_terms": ["x", "x^2", "x^3"]})
        self.assertEqual(input_basis.protocol(self.training()), {})
        np.testing.assert_array_equal(input_basis.expand(x, self.training()), x)
        self.assertEqual(training, before)

    def test_unknown_basis_multiple_columns_and_overflow_are_explicitly_rejected(self):
        invalid = [self.training(input_basis="polynomial"), self.training(input_basis=None),
                   self.training(input_basis={"kind": "univariate_cubic"}),
                   self.training(input_basis="univariate_cubic", feature_columns=["x", "z"])]
        for training in invalid:
            with self.subTest(training=training), self.assertRaises(ResearchError) as caught:
                input_basis.protocol(training)
            self.assertEqual(caught.exception.code, "INVALID_TRAINING")
        with self.assertRaises(ResearchError) as caught:
            input_basis.expand([[1e200]], self.training(input_basis="univariate_cubic"))
        self.assertEqual(caught.exception.code, "INVALID_TRAINING")

    def test_cubic_scaler_and_saved_coefficients_use_three_training_fold_terms_with_ten_fits(self):
        payload = self.packet(basis="univariate_cubic")
        events = []
        result = GROUPED.execute(payload, self.adapter_parameters(), fit_observer=events.append)
        analysis = result["result"]["analysis"]
        self.assertEqual(result["adapter_version"], "2")
        self.assertEqual({key: analysis["protocol"][key] for key in ("input_basis", "model_input_terms")},
                         input_basis.protocol(payload["design_binding"]["training"]))
        self.assertEqual(analysis["protocol"]["feature_columns"], ["x"])
        self.assertEqual(analysis["usage"]["fit_attempts"], 10)
        self.assertEqual([(event["index"], event["status"]) for event in events],
                         [(index, status) for index in range(1, 11) for status in ("started", "completed")])
        model_inputs = np.array([[x, x ** 2, x ** 3] for x in range(-4, 6)], dtype=float)
        for fold in analysis["folds"]:
            train = np.array(fold["train_records"]) - 1
            test = np.array(fold["test_records"]) - 1
            self.assertTrue(set(train).isdisjoint(test))
            np.testing.assert_allclose(fold["scaler_mean"], model_inputs[train].mean(axis=0), rtol=1e-13, atol=1e-13)
            np.testing.assert_allclose(fold["scaler_scale"], model_inputs[train].std(axis=0), rtol=1e-13, atol=1e-13)
            self.assertEqual(len(fold["ridge_coefficients"]), 3)
            rebuilt = ((model_inputs[test] - fold["scaler_mean"]) / fold["scaler_scale"]) @ np.array(fold["ridge_coefficients"]) + fold["ridge_intercept"]
            saved = [analysis["oof"][index]["predicted"] for index in test]
            np.testing.assert_allclose(rebuilt, saved, rtol=1e-13, atol=1e-13)

    def test_raw_protocol_stays_exact_and_invalid_cubic_never_starts_an_estimator(self):
        raw = GROUPED.execute(self.packet(), self.adapter_parameters())["result"]["analysis"]
        self.assertEqual(raw["protocol"], {
            "splitter": "GroupKFold", "n_splits": 5, "shuffle": False, "random_state": None,
            "ridge_alpha": 1.0, "preprocessing": "StandardScaler.fit on training rows only", "reference": "training-fold target mean",
            "feature_columns": ["x"], "split_group_columns": ["batch"], "grouping_semantics": "operator-declared source columns"})
        cases = [self.packet(basis="univariate_cubic", large=True), self.packet(basis="unsupported"),
                 self.packet(basis="univariate_cubic", limit=9)]
        with patch("autoresearch.ridge_validation_adapter.StandardScaler.fit", side_effect=AssertionError("Rejected before fitting")):
            for payload in cases:
                events = []
                with self.subTest(training=payload["design_binding"]["training"]), self.assertRaises(ResearchError):
                    GROUPED.execute(payload, self.adapter_parameters(), fit_observer=events.append)
                self.assertEqual(events, [])
            with self.assertRaises(ResearchError):
                GROUPED.required_fit_attempts(self.packet(basis="univariate_cubic", large=True))

    def test_comparison_kind_is_optional_and_requires_a_raw_explicit_child(self):
        original = self.resource()
        self.assertEqual(validate_resource(original), original)
        child = {**self.resource(version=2), "comparison_kind": "fixed_input_basis"}
        self.assertEqual(validate_resource(child), child)
        for resource in ({**self.resource(), "comparison_kind": "fixed_input_basis"},
                         {**self.resource(version=2), "comparison_kind": "arbitrary_mapping"},
                         {**RESOURCE, "version": 2, "parent_version": 1, "comparison_kind": "fixed_input_basis"},
                         {**child, "other_transform": "x^4"}):
            with self.subTest(resource=resource), self.assertRaises(ResearchError) as caught:
                validate_resource(resource)
            self.assertEqual(caught.exception.code, "INVALID_DESIGN")

    def test_cubic_revision_preserves_used_thirty_then_uses_ten_and_replays_without_fitting(self):
        project, controller = self.project(checks=("random_cv", "group_cv"), fit_limit=20)
        controller.advance(request_id="raw-random")
        controller.advance(request_id="raw-group")
        bind(project, request_id="raw-subset-bind", expected_state_version=project.status()["state_version"],
             resource=self.resource(version=2), prediction_column=None, reason="A single original input comparator",
             training={"feature_columns": ["speed"], "split_group_columns": ["group"], "fit_limit": 30})
        controller.advance(request_id="raw-subset-group")
        before = project.status()
        originals = {action["artifact"]: (project.root / action["artifact"]).read_bytes() for action in before["actions"]}
        self.assertEqual(before["budget"]["fit_attempts_used"], 30)
        self.assertNotIn("input_basis", before["design_revisions"][-1]["training"])
        invalid = {"request_id": "bad-basis-bind", "expected_state_version": before["state_version"],
                   "resource": {**self.resource(version=3), "comparison_kind": "fixed_input_basis"}, "prediction_column": None,
                   "reason": "Reject undocumented transforms", "training": {
                       "feature_columns": ["speed"], "split_group_columns": ["group"], "fit_limit": 40, "input_basis": "arbitrary"}}
        with self.assertRaises(ResearchError) as caught:
            bind(project, **invalid)
        self.assertEqual(caught.exception.code, "INVALID_TRAINING")
        self.assertEqual(project.status(), before)
        request = {**invalid, "request_id": "cubic-bind", "training": {**invalid["training"], "input_basis": "univariate_cubic"}}
        revision = bind(project, **request)
        self.assertEqual((project.status()["budget"]["fit_attempts_used"], project.status()["budget"]["fit_limit"]), (30, 40))
        self.assertEqual(project.status()["budget_revisions"][-1]["fit_attempts_preserved"], 30)
        controller.advance(request_id="cubic-group")
        finished = project.status()
        self.assertEqual((finished["budget"]["fit_attempts_used"], finished["budget"]["fits_completed"], finished["budget"]["fits_reserved"]), (40, 40, 0))
        self.assertEqual(finished["actions"][:-1], before["actions"])
        self.assertTrue(all((project.root / name).read_bytes() == raw for name, raw in originals.items()))
        with patch.object(registry.RIDGE["data.ridge-group-validation"], "execute", side_effect=AssertionError("No replay fit")):
            self.assertEqual(bind(project, **request), revision)
            self.assertTrue(controller.advance(request_id="cubic-group")["replayed"])
            self.assertTrue(controller.advance(request_id="raw-subset-group")["replayed"])
        self.assertEqual(project.status(), finished)

    def test_unknown_cubic_execution_reserves_original_attempts_and_prevents_rebinding(self):
        project, controller = self.project()
        bind(project, request_id="unknown-cubic-bind", expected_state_version=project.status()["state_version"],
             resource={**self.resource(version=2), "comparison_kind": "fixed_input_basis"}, prediction_column=None,
             reason="Fixed cubic unknown-execution fixture", training={"feature_columns": ["speed"],
                 "split_group_columns": ["group"], "fit_limit": 10, "input_basis": "univariate_cubic"})
        def interrupt(payload, parameters, fit_observer=None):
            fit_observer({"index": 1, "estimator": "scaler", "fold": 1, "status": "started"})
            raise KeyboardInterrupt("Constructed missing estimator receipt")
        with patch.object(registry.RIDGE["data.ridge-group-validation"], "execute", side_effect=interrupt) as execute:
            with self.assertRaises(KeyboardInterrupt):
                project.step(request_id="cubic-unknown", method_id="data.ridge-group-validation", parameters=self.parameters(project))
            self.assertEqual(project.resume(request_id="cubic-unknown")["status"], "unknown")
            before = project.status()
            self.assertEqual((before["budget"]["fit_attempts_used"], before["budget"]["fits_reserved"]), (1, 9))
            self.assertEqual(controller.selection_context()["candidates"], [])
            self.assertEqual(project.resume(request_id="cubic-unknown")["status"], "unknown")
            self.assertEqual(execute.call_count, 1)
        with self.assertRaises(ResearchError) as caught:
            bind(project, request_id="cannot-reset-cubic", expected_state_version=before["state_version"],
                 resource={**self.resource(version=3), "comparison_kind": "fixed_input_basis"}, prediction_column=None,
                 reason="Unknown execution must retain its identity", training={"feature_columns": ["speed"],
                     "split_group_columns": ["group"], "fit_limit": 20, "input_basis": "univariate_cubic"})
        self.assertEqual(caught.exception.code, "EXECUTION_UNKNOWN")
        self.assertEqual(project.status(), before)

    def test_basis_helper_source_participates_in_adapter_and_core_code_identity(self):
        original_read = Path.read_bytes
        helper = Path(input_basis.__file__).resolve()
        adapter_before, core_before = GROUPED.code_identity(), code_identity()
        def changed(path):
            raw = original_read(path)
            return raw + b"\n# changed fixed mapping\n" if path.resolve() == helper else raw
        with patch.object(Path, "read_bytes", new=changed):
            self.assertNotEqual(GROUPED.code_identity(), adapter_before)
            self.assertNotEqual(code_identity(), core_before)


if __name__ == "__main__":
    unittest.main()
