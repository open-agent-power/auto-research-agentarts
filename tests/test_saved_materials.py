"""Complete retained diagnostic transport fixtures; no estimator or diagnostic execution."""
import base64
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from autoresearch import research_plan_proposal as plan, recipe_change_proposal as recipe, saved_materials
from autoresearch.contracts import ResearchError, canonical, fingerprint
from autoresearch.local_workbench import LocalWorkbench
from autoresearch import method_registry as registry
from autoresearch.plan_feedback import projection_notice


def saved_project(root):
    """Install constructed saved receipts directly; this fixture never executes research."""
    manager = LocalWorkbench(Path(root) / "manager")
    spec = {"schema_version": "tabular-quality-spec-v1", "file": "readings.csv", "dataset_label": "Saved transport fixture",
            "source_url": "urn:test:saved-materials", "license_note": "Constructed engineering fixture",
            "sample_unit": "declared_record", "group_columns": ["g"], "key_columns": [], "numeric_columns": ["x", "y"],
            "target_column": "y", "target_unit": "declared_unit", "missing_tokens": ["", "NA"], "delimiter": ",",
            "provenance": {"origin_sha256": "a" * 64, "description": "Constructed saved receipts; no fits"}}
    manager.create({"request_id": "create-saved-materials", "goal": "Interpret complete saved errors",
        "budget_ref": "engineering-only", "max_tool_calls": 8, "input": {"file_name": "readings.csv",
        "csv_base64": base64.b64encode(b"g,x,y\na,1,2\na,2,3\nb,3,4\nb,4,5\n").decode(),
        "spec_base64": base64.b64encode(canonical(spec).encode()).decode()}})
    project, _ = manager.binding()
    state = project.status()
    resource = {"schema_version": "research-design-resource-v1", "id": "saved-design", "version": 1,
                "parent_version": None, "checks": ["group_cv"], "title": "Saved fixture", "question": "Saved errors?",
                "claim": "Unverified", "alternatives": ["Unverified groups"], "sources": [], "change_reason": "Fixture"}
    binding = {"project_id": state["id"], "version": 1, "request_id": "saved-binding",
               "source_snapshot_sha256": state["source_snapshot_sha256"], "target_column": "y", "prediction_column": None,
               "training": {"feature_columns": ["x"], "split_group_columns": ["g"]}, "resource": resource,
               "fit_requirements": {"group_cv": 4}}
    protocol = {"feature_columns": ["x"], "split_group_columns": ["g"], "n_splits": 2,
                "reference": "training-fold target mean"}
    rows = [{"logical_record": index, "physical_line_end": index + 1, "observed": float(index + 1),
             "predicted": float(index), "reference_prediction": 4.5 if index < 3 else 2.5,
             "fold": 1 if index < 3 else 2, "groups": ["a" if index < 3 else "b"], "input_values": {}}
            for index in range(1, 5)]
    metrics = {"n": 4, "candidate_mae": 1.0, "reference_mae": 2.0, "mean_error": -1.0,
               "reference_mean_error": 0.0, "negative_predictions": 0}
    groups = [{"groups": [name], "logical_records": indexes, "folds": [fold], **dict(metrics, n=2)}
              for name, indexes, fold in [("a", [1, 2], 1), ("b", [3, 4], 2)]]
    folds = [{"fold": fold, "train_n": 2, "test_n": 2, "train_group_count": 1, "test_group_count": 1,
              "train_records": train, "test_records": test, **dict(metrics, n=2)}
             for fold, train, test in [(1, [3, 4], [1, 2]), (2, [1, 2], [3, 4])]]
    summary = {"status": "computed", "n": 4, "input_n": 4, "excluded": 0, "candidate_mae": 1.0,
               "reference_mae": 2.0, "improvement": 0.5, "outperforms_reference": True, "group_count": 2}
    evidence = {"source_snapshot_sha256": state["source_snapshot_sha256"], "source_sha256": "b" * 64,
                "file_name": "readings.csv"}
    analysis = {"schema_version": "ridge-validation-v1", "check": "group_cv", "summary": summary,
                "source_snapshot_sha256": state["source_snapshot_sha256"], "target_column": "y", "target_unit": "declared_unit",
                "design_binding": binding, "protocol": protocol, "oof": rows, "folds": folds, "scientific_validation": False}

    def action(action_id, command, request_id):
        return {"id": action_id, "project_id": state["id"], "command": command, "request_id": request_id,
                "request_sha256": fingerprint(request_id), "source_snapshot_sha256": state["source_snapshot_sha256"],
                "code_identity": "c" * 64, "status": "completed", "artifact": "artifacts/" + action_id + ".json",
                "design_binding": copy.deepcopy(binding), "evaluation_ref": registry.evaluation_ref(command), "failure": None,
                "next_decision": None, "method_instance": {"input_bindings": {"design_revision": 1},
                                                          "parameters": {}, "evaluation_ref": registry.evaluation_ref(command)}}

    def save(action, tool):
        envelope = {"action_id": action["id"], "request_sha256": action["request_sha256"],
                    "source_snapshot_sha256": state["source_snapshot_sha256"], "code_identity": action["code_identity"],
                    "tool_result": tool}
        envelope["sha256"] = fingerprint(envelope)
        action["result_sha256"] = envelope["sha256"]
        action["observations"] = [dict(item, id=action["id"] + ":observation:" + str(index), action_id=action["id"])
                                  for index, item in enumerate(tool["observations"])]
        project._artifact(action).write_text(canonical(envelope), encoding="utf-8")

    source = action("source-cv", "data.ridge-group-validation", "source-request")
    save(source, {"schema_version": "ridge-validation-result-v1", "tool_id": source["command"], "status": "completed",
                  "scientific_validation": False, "failure": None, "result": {"analysis": analysis}, "evidence_refs": [evidence],
                  "observations": [{"kind": "ridge_validation", "check": "group_cv", "summary": summary,
                                    "design_binding": binding, "scientific_validation": False}]})
    diagnostic_action = action("saved-diagnostic", "data.saved-oof-group-diagnostics", "diagnostic-request")
    diagnostic_action["parameters"] = {"based_on_action_id": source["id"], "based_on_result_sha256": source["result_sha256"]}
    diagnostic_action["method_instance"]["parameters"] = copy.deepcopy(diagnostic_action["parameters"])
    source_ref = {"action_id": source["id"], "request_id": source["request_id"], "method_id": source["command"],
                  "result_sha256": source["result_sha256"], "producer_code_identity": source["code_identity"],
                  "design_version": 1, "resource_id": resource["id"], "resource_version": 1,
                  "target_column": "y", "target_unit": "declared_unit"}
    ranges = {"n": 4, "observed_min": 2.0, "observed_max": 5.0, "predicted_min": 1.0, "predicted_max": 4.0,
              "negative_predictions": 0, "below_observed_min": 1, "above_observed_max": 0, "scientific_validation": False}
    diagnostic = {"schema_version": "saved-oof-diagnostics-v1", "check": "group_cv", "scientific_validation": False,
        "provenance": {"project_id": state["id"], "source_scope": state["source_scope"],
            "source_snapshot_sha256": state["source_snapshot_sha256"], "current_project_code_identity": diagnostic_action["code_identity"],
            "design_binding": binding, "artifact_sha256": source["result_sha256"], "source_sha256": "b" * 64,
            "source_file": "readings.csv", "action": {key: source[key] for key in ("id", "request_id", "command", "status",
                "request_sha256", "source_snapshot_sha256", "code_identity", "result_sha256", "evaluation_ref")}},
        "protocol": protocol, "target_column": "y", "target_unit": "declared_unit", "rows": rows, "folds": folds,
        "groups": groups, "input_n": 4, "excluded": 0, "group_columns": ["g"], "row_weighted": metrics,
        "group_weighted": {"group_count": 2, "candidate_mae": 1.0, "reference_mae": 2.0}, "prediction_ranges": ranges}
    metric_names = ("n", "candidate_mae", "reference_mae", "mean_error", "reference_mean_error", "negative_predictions")
    observation = {"kind": "saved_oof_diagnostic", "producer": diagnostic_action["command"], "source_check": "group_cv",
                   "source_ref": source_ref, "scientific_validation": False,
                   **{key: copy.deepcopy(diagnostic[key]) for key in
                      ("input_n", "excluded", "group_columns", "row_weighted", "group_weighted", "prediction_ranges")},
                   "fold_errors": [{key: value[key] for key in ("fold", "train_n", "test_n", "train_group_count", "test_group_count", *metric_names)}
                                   for value in folds],
                   "group_errors": [{key: value[key] for key in ("groups", "folds", *metric_names)} for value in groups]}
    save(diagnostic_action, {"schema_version": "saved-oof-diagnostic-result-v1", "tool_id": diagnostic_action["command"],
        "status": "completed", "scientific_validation": False, "failure": None, "new_fits": 0, "model_calls": 0,
        "result": {"diagnostic": diagnostic}, "observations": [observation],
        "evidence_refs": [{"source_snapshot_sha256": state["source_snapshot_sha256"], "source_sha256": "b" * 64,
            "producer": source_ref, "locator": {"kind": "saved_oof_action", "action_id": source["id"], "result_sha256": source["result_sha256"]}}]})
    with project._connect() as con:
        record = project._project(con)
        record.update(design_revisions=[binding], state_version=3)
        project._save(con, record)
        for saved in (source, diagnostic_action):
            con.execute("INSERT INTO actions VALUES(?,?,?)", (saved["request_id"], saved["request_sha256"], canonical(saved)))
    return manager, project, {"action_id": diagnostic_action["id"], "result_sha256": diagnostic_action["result_sha256"],
                              "fields": ["groups"]}


class SavedMaterialsTests(unittest.TestCase):
    def setUp(self):
        for target in ("autoresearch.ridge_validation_adapter.Ridge.fit", "autoresearch.ridge_validation_adapter.StandardScaler.fit",
                       "autoresearch.saved_oof_diagnostics.inspect_saved_oof", "autoresearch.source_evidence_adapter.execute"):
            self.enterContext(patch(target, side_effect=AssertionError("Saved material transport must never execute research")))
        root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.manager, self.project, self.request = saved_project(root)
        self.recipe = {"schema_version": "research-recipe-v1", "id": "saved-route", "version": 1,
                       "question": "Interpret saved errors", "scope_match": {"domain": "data", "contract": "tabular-quality-v1"},
                       "need": "next_check", "ordered_methods": [{"method_id": "data.saved-oof-group-diagnostics",
                           "evaluation_ref": registry.evaluation_ref("data.saved-oof-group-diagnostics")}], "on_no_match": "wait"}

    def test_complete_fields_copy_exact_original_without_any_execution(self):
        before = self.project.status()
        request = dict(self.request, fields=["groups", "folds", "rows"])
        context = plan.build_context(self.project, saved_materials=[request])
        supplied = context["supplied_materials"][0]
        action = before["actions"][-1]
        diagnostic = json.loads(self.project._artifact(action).read_bytes())["tool_result"]["result"]["diagnostic"]
        self.assertEqual(context["schema_version"], "research-plan-context-v3")
        for name in request["fields"]:
            self.assertEqual(supplied["fields"][name], {"path": ["tool_result", "result", "diagnostic", name],
                                                      "count": len(diagnostic[name]), "value": diagnostic[name]})
        self.assertEqual(supplied["producer"]["code_identity"], "c" * 64)
        self.assertTrue(all(row["input_values"] == {} for row in supplied["fields"]["rows"]["value"]))
        self.assertEqual(self.project.status(), before)
        notice = projection_notice(context)
        self.assertIn("Only fields actually included", notice)
        self.assertIn("remain unread references", notice)
        self.assertIn("missing original inputs", notice)
        self.assertIn(canonical(context), plan.build_prompt(context)["prompt"])

    def test_empty_requests_keep_original_v2_context_prompt_and_notice_bytes(self):
        original = plan.build_context(self.project)
        for option in (None, []):
            current = plan.build_context(self.project, saved_materials=option)
            self.assertEqual(canonical(current).encode(), canonical(original).encode())
            self.assertEqual(plan.build_prompt(current), plan.build_prompt(original))
            self.assertEqual(projection_notice(current), projection_notice(original))
            self.assertNotIn("supplied_materials", current)
        self.assertEqual(saved_materials.normalize_requests(None), [])
        self.assertEqual(saved_materials.normalize_requests([]), [])

    def test_reject_bad_selectors_duplicates_and_arbitrary_paths(self):
        bad = [{}, self.request, [self.request, self.request], [dict(self.request, fields=[])],
               [dict(self.request, fields=["groups", "groups"])], [dict(self.request, fields=["input_profiles"])],
               [dict(self.request, fields=["tool_result.result.diagnostic.rows"])],
               [dict(self.request, result_sha256="x")], [dict(self.request, path=["rows"])]]
        for value in bad:
            with self.subTest(value=value), self.assertRaises(ResearchError) as error:
                saved_materials.normalize_requests(value)
            self.assertEqual(error.exception.code, "INVALID_SAVED_MATERIALS")

    def test_history_binding_is_allowed_and_unchanged(self):
        with self.project._connect() as con:
            record = self.project._project(con)
            new_binding = copy.deepcopy(record["design_revisions"][0]); new_binding["version"] = 2
            new_binding["resource"].update(version=2, parent_version=1)
            record["design_revisions"].append(new_binding)
            self.project._save(con, record)
        before = self.project.status()
        context = plan.build_context(self.project, saved_materials=[self.request])
        self.assertEqual(context["supplied_materials"][0]["producer"]["design_version"], 1)
        self.assertEqual(self.project.status(), before)

    def test_source_result_sha_artifact_and_state_observations_are_checked(self):
        before = self.project.status()
        changes = [("sha256", "f" * 64), ("code_identity", "f" * 64), ("source_snapshot_sha256", "f" * 64)]
        for action in before["actions"]:
            path = self.project._artifact(action); raw = path.read_bytes()
            for key, value in changes:
                envelope = json.loads(raw); envelope[key] = value
                path.write_text(canonical(envelope), encoding="utf-8")
                with self.subTest(action=action["id"], key=key), self.assertRaises(ResearchError):
                    saved_materials.materialize(self.project, before, [self.request])
                path.write_bytes(raw)
            state = copy.deepcopy(before)
            next(a for a in state["actions"] if a["id"] == action["id"])["observations"][0]["id"] = "wrong"
            with self.assertRaises(ResearchError):
                saved_materials.materialize(self.project, state, [self.request])

    def test_resigned_diagnostic_still_requires_native_schema_source_producer_and_design(self):
        before = self.project.status()
        action = before["actions"][-1]
        path = self.project._artifact(action); raw = path.read_bytes()
        for mutate in (
            lambda tool: tool.update(schema_version="other-result-v1"),
            lambda tool: tool["result"]["diagnostic"].update(schema_version="other-diagnostic-v1"),
            lambda tool: tool["result"]["diagnostic"].update(check="random_cv"),
            lambda tool: tool["result"]["diagnostic"]["provenance"].update(project_id="other-project"),
            lambda tool: tool["result"]["diagnostic"]["provenance"].update(current_project_code_identity="f" * 64),
            lambda tool: tool["result"]["diagnostic"]["provenance"].update(source_snapshot_sha256="f" * 64),
            lambda tool: tool["result"]["diagnostic"]["provenance"]["action"].update(result_sha256="f" * 64),
            lambda tool: tool["result"]["diagnostic"]["provenance"]["design_binding"].update(version=9),
            lambda tool: tool["observations"][0]["source_ref"].update(producer_code_identity="f" * 64),
            lambda tool: tool["evidence_refs"][0].update(source_sha256="f" * 64),
            lambda tool: tool["result"]["diagnostic"]["rows"].pop(),
        ):
            state = copy.deepcopy(before); envelope = json.loads(raw)
            mutate(envelope["tool_result"])
            envelope["sha256"] = fingerprint({key: value for key, value in envelope.items() if key != "sha256"})
            state["actions"][-1]["result_sha256"] = envelope["sha256"]
            state["actions"][-1]["observations"] = [dict(item, id=action["id"] + ":observation:" + str(index),
                action_id=action["id"]) for index, item in enumerate(envelope["tool_result"]["observations"])]
            path.write_text(canonical(envelope), encoding="utf-8")
            request = dict(self.request, result_sha256=envelope["sha256"])
            with self.assertRaises(ResearchError):
                saved_materials.materialize(self.project, state, [request])
            path.write_bytes(raw)

    def test_resigned_original_cv_schema_and_scope_are_checked(self):
        before = self.project.status()
        action = before["actions"][0]
        path = self.project._artifact(action); raw = path.read_bytes()
        for mutate in (
            lambda tool: tool.update(schema_version="not-ridge-result"),
            lambda tool: tool["result"]["analysis"].update(schema_version="not-ridge-analysis"),
            lambda tool: tool["result"]["analysis"].update(target_column="other"),
            lambda tool: tool["result"]["analysis"].update(source_snapshot_sha256="f" * 64),
            lambda tool: tool["result"]["analysis"]["summary"].update(status="not_computable"),
        ):
            state = copy.deepcopy(before); envelope = json.loads(raw)
            mutate(envelope["tool_result"])
            envelope["sha256"] = fingerprint({key: value for key, value in envelope.items() if key != "sha256"})
            state["actions"][0]["result_sha256"] = envelope["sha256"]
            path.write_text(canonical(envelope), encoding="utf-8")
            with self.assertRaises(ResearchError):
                saved_materials.materialize(self.project, state, [self.request])
            path.write_bytes(raw)

    def test_reject_failed_non_native_wrong_binding_and_missing_result(self):
        before = self.project.status()
        for key, value in [("status", "failed"), ("command", "data.ridge-group-validation"),
                           ("source_snapshot_sha256", "f" * 64), ("design_binding", {"version": 9})]:
            state = copy.deepcopy(before); state["actions"][-1][key] = value
            with self.subTest(key=key), self.assertRaises(ResearchError):
                saved_materials.materialize(self.project, state, [self.request])
        for request in [dict(self.request, action_id="missing"), dict(self.request, result_sha256="f" * 64)]:
            with self.assertRaises(ResearchError):
                saved_materials.materialize(self.project, before, [request])

    def test_pure_frozen_validator_checks_path_count_coverage_and_feedback_identity(self):
        context = plan.build_context(self.project, saved_materials=[self.request])
        for mutate in (
            lambda m: m.update(coverage="partial"), lambda m: m.update(scientific_validation=True),
            lambda m: m["fields"]["groups"].update(count=1),
            lambda m: m["fields"]["groups"].update(path=["groups"]),
            lambda m: m["fields"]["groups"]["value"].pop(),
            lambda m: m["producer"].update(request_id="wrong"), lambda m: m["producer"].update(design_version=2),
            lambda m: m.update(artifact_ref="other.json"), lambda m: m["source_ref"].update(result_sha256="f" * 64),
            lambda m: m["fields"]["groups"]["value"][0].update(candidate_mae=999),
        ):
            changed = copy.deepcopy(context); mutate(changed["supplied_materials"][0])
            with self.assertRaises(ResearchError):
                saved_materials.validate_supplied(changed)
        with patch.object(Path, "read_bytes", side_effect=AssertionError("Frozen validation cannot read live files")):
            self.assertEqual(saved_materials.validate_supplied(copy.deepcopy(context)), context)

    def test_recipe_uses_nested_v3_with_original_outer_schema(self):
        context = recipe.build_context(self.project, self.recipe, "Read complete saved errors", saved_materials=[self.request])
        self.assertEqual(context["schema_version"], "recipe-change-context-v1")
        self.assertEqual(context["research_context"]["schema_version"], "research-plan-context-v3")
        self.assertIn(canonical(context), recipe.build_prompt(context)["prompt"])

    def test_full_plan_and_recipe_utf8_limits_reject_without_partial_supply(self):
        context = plan.build_context(self.project, saved_materials=[self.request])
        context["supplied_materials"][0]["fields"]["groups"]["value"][0]["logical_records"] = ["测" * 22000]
        size = len(canonical(context).encode())
        with self.assertRaises(ResearchError) as error:
            plan._context(context)
        self.assertIn(str(size), str(error.exception)); self.assertIn("Nothing was supplied partially", str(error.exception))
        context = recipe.build_context(self.project, self.recipe, "Read complete saved errors", saved_materials=[self.request])
        research = context["research_context"]
        padding = 65536 - len(canonical(context).encode()) + 1
        research["supplied_materials"][0]["fields"]["groups"]["value"][0]["saved_extra"] = "x" * padding
        self.assertLess(len(canonical(research).encode()), 65536)
        self.assertGreater(len(canonical(context).encode()), 65536)
        with self.assertRaises(ResearchError) as error:
            recipe._context(context)
        self.assertEqual(error.exception.code, "INVALID_RECIPE_CHANGE_CONTEXT")
        self.assertIn("Nothing was supplied partially", str(error.exception))


if __name__ == "__main__":
    unittest.main()
