"""OOF fits retain train-only preprocessing, grouping and failure accounting."""
import json
from unittest.mock import patch
import unittest

import test_tabular_quality_adapter as fixtures
from autoresearch.contracts import ResearchError
from autoresearch.ridge_validation_adapter import RANDOM, GROUPED


class RidgeValidationAdapterTests(unittest.TestCase):
    capture = fixtures.TabularQualityAdapterTests.capture

    def packet(self, text=None, *, limit=10):
        text = text or "id,batch,x,y\n" + "".join(f"r{i},g{i // 2},{i},{2 * i}\n" for i in range(10))
        payload, _ = self.capture(text, numeric_columns=["x", "y"], target_column="y")
        payload["design_binding"] = {"version": 1, "source_snapshot_sha256": payload["snapshot_sha256"],
            "target_column": "y", "resource": {"checks": ["random_cv", "group_cv", "negative_control"]},
            "training": {"feature_columns": ["x"], "split_group_columns": ["batch"], "fit_limit": limit}}
        return payload

    @staticmethod
    def parameters():
        return {"based_on_action_id": "quality-one", "based_on_result_sha256": "a" * 64}

    def test_random_oof_uses_fixed_folds_and_training_mean_references(self):
        events = []
        result = RANDOM.execute(self.packet(), self.parameters(), fit_observer=events.append)
        analysis = result["result"]["analysis"]
        self.assertEqual([fold["test_records"] for fold in analysis["folds"]], [[8, 9], [3, 7], [5, 6], [2, 4], [1, 10]])
        self.assertEqual([row["logical_record"] for row in analysis["oof"]], list(range(1, 11)))
        for fold in analysis["folds"]:
            train = fold["train_records"]
            mean = sum(2 * (record - 1) for record in train) / len(train)
            self.assertAlmostEqual(fold["reference_prediction"], mean)
            self.assertAlmostEqual(fold["scaler_mean"][0], mean / 2)
            self.assertTrue(set(train).isdisjoint(fold["test_records"]))
        self.assertEqual([(event["index"], event["status"]) for event in events],
                         [(index, status) for index in range(1, 11) for status in ("started", "completed")])
        self.assertEqual(analysis["usage"], {"ridge_fit_attempts": 5, "preprocessing_fit_attempts": 5, "fit_attempts": 10})
        self.assertEqual(result["new_fits"], 5)
        self.assertEqual(result["model_calls"], 0)
        json.dumps(result, allow_nan=False)

    def test_group_validation_holds_out_entire_declared_groups(self):
        result = GROUPED.execute(self.packet(), self.parameters())
        analysis = result["result"]["analysis"]
        labels = {row["logical_record"]: tuple(row["groups"]) for row in analysis["oof"]}
        for fold in analysis["folds"]:
            self.assertTrue({labels[row] for row in fold["train_records"]}.isdisjoint(
                            {labels[row] for row in fold["test_records"]}))
        self.assertEqual(analysis["summary"]["n"], 10)
        self.assertEqual(analysis["protocol"]["n_splits"], 5)

    def test_required_fits_match_effective_groups_before_any_fit(self):
        payload = self.packet("id,batch,x,y\n" + "".join(f"r{i},g{i//5},{i},{i}\n" for i in range(10)))
        self.assertEqual(RANDOM.required_fit_attempts(payload), 10)
        self.assertEqual(GROUPED.required_fit_attempts(payload), 4)

    def test_both_arms_use_one_complete_case_mask(self):
        payload = self.packet("id,batch,x,y\nr0,a,0,0\nr1,a,,2\nr2,a,2,4\nr3,,3,6\nr4,b,4,8\nr5,b,5,NA\nr6,b,6,12\nr7,b,7,14\nr8,c,8,16\nr9,c,9,18\n")
        results = [adapter.execute(payload, self.parameters())["result"]["analysis"] for adapter in (RANDOM, GROUPED)]
        self.assertEqual([row["logical_record"] for row in results[0]["oof"]], [1, 3, 5, 7, 8, 9, 10])
        self.assertEqual([row["logical_record"] for row in results[0]["oof"]],
                         [row["logical_record"] for row in results[1]["oof"]])
        self.assertEqual([row["logical_record"] for row in results[0]["exclusions"]], [2, 4, 6])

    def test_invalid_roles_and_insufficient_grant_never_start_a_fit(self):
        for column, limit in (("y", 10), ("batch", 10), ("x", 9)):
            payload, events = self.packet(limit=limit), []
            payload["design_binding"]["training"]["feature_columns"] = [column]
            with self.subTest(column=column, limit=limit), self.assertRaises(ResearchError):
                RANDOM.execute(payload, self.parameters(), fit_observer=events.append)
            self.assertEqual(events, [])

    def test_constant_target_and_one_group_return_uncomputable_without_fit(self):
        fixtures = [(RANDOM, "id,batch,x,y\n" + "".join(f"r{i},g{i//2},{i},3\n" for i in range(10)), "constant_target"),
                    (GROUPED, "id,batch,x,y\n" + "".join(f"r{i},one,{i},{i}\n" for i in range(10)), "insufficient_groups")]
        for adapter, text, reason in fixtures:
            events = []
            with self.subTest(reason=reason):
                analysis = adapter.execute(self.packet(text), self.parameters(), fit_observer=events.append)["result"]["analysis"]
                self.assertEqual(analysis["summary"]["status"], "not_computable")
                self.assertEqual(analysis["summary"]["reason"], reason)
                self.assertEqual(analysis["usage"]["fit_attempts"], 0)
                self.assertEqual(events, [])

    def test_failed_ridge_reports_started_and_failed_after_completed_scaler(self):
        events = []
        with patch("autoresearch.ridge_validation_adapter.Ridge.fit", side_effect=ValueError("Controlled estimator failure")):
            with self.assertRaisesRegex(ValueError, "Controlled estimator failure"):
                RANDOM.execute(self.packet(), self.parameters(), fit_observer=events.append)
        self.assertEqual(events, [{"index": 1, "estimator": "scaler", "fold": 1, "status": "started"},
                                  {"index": 1, "estimator": "scaler", "fold": 1, "status": "completed"},
                                  {"index": 2, "estimator": "ridge", "fold": 1, "status": "started"},
                                  {"index": 2, "estimator": "ridge", "fold": 1, "status": "failed"}])

    def test_observer_rejection_prevents_estimator_start(self):
        def reject(event):
            raise RuntimeError("Ledger rejected start")
        with patch("autoresearch.ridge_validation_adapter.StandardScaler.fit") as fitter:
            with self.assertRaisesRegex(RuntimeError, "Ledger rejected start"):
                RANDOM.execute(self.packet(), self.parameters(), fit_observer=reject)
            fitter.assert_not_called()


if __name__ == "__main__":
    unittest.main()
