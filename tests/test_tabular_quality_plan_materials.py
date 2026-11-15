"""Explicit saved quality feedback material, isolated synthetic projects only."""
import copy
from pathlib import Path
import sqlite3
import unittest
from unittest.mock import patch

import test_tabular_quality_feedback as fixture
from autoresearch import saved_materials, research_plan_proposal as plan, recipe_change_proposal as recipe
from autoresearch.contracts import ResearchError, canonical
from autoresearch.host_model_selection import HostModelSelection
from autoresearch.project_controller import ProjectController
from autoresearch.research_project import ResearchProject


class QualityPlanMaterialsTests(unittest.TestCase):
    def stage(self, *, rules=None, execute=True, canary=False, no_groups=False):
        f = fixture.QualityFeedbackTests(methodName="runTest")
        if canary or no_groups:
            original = fixture.fixtures.NumericAssociationTests.payload
            def altered(instance, csv, **kwargs):
                if no_groups:
                    return original(instance, "x,outcome\n1,2\n2,4\n3,6\n4,8\n", group_columns=[])
                return original(instance, csv.replace("a,1,2", "a,SYNTHETIC_SECRET_CANARY,2"), **kwargs)
            with patch.object(fixture.fixtures.NumericAssociationTests, "payload", new=altered): f.setUp()
        else: f.setUp()
        self.addCleanup(f.doCleanups)
        registration = f.register(reg=rules if rules is not None else fixture.rules(
            fixture.condition("rows", "eq", 4), fixture.condition("exact_duplicate_rows", "eq", 0)))
        if execute: f.execute()
        selector = {"kind":saved_materials.QUALITY_KIND, "registration_request_id":"reg",
                    "registration_sha256":registration["registration_sha256"]}
        return f, registration, selector

    def test_known_met_notmet_and_zero_are_exact_saved_results(self):
        for met in (True, False):
            with self.subTest(met=met):
                rules = fixture.rules(fixture.condition("rows", "eq" if met else "gt", 4),
                                      fixture.condition("exact_duplicate_rows", "eq", 0))
                f, reg, selector = self.stage(rules=rules)
                before, db = f.project.status(), f.project.db.read_bytes()
                with patch.object(ResearchProject,"step",side_effect=AssertionError("step")), \
                     patch.object(ProjectController,"_dispatch",side_effect=AssertionError("dispatch")):
                    context = plan.build_context(f.project, saved_materials=[selector])
                material = context["supplied_materials"][0]
                self.assertEqual(context["schema_version"], "research-plan-context-v3")
                self.assertEqual(material["conditions"], reg["conditions"])
                self.assertEqual(material["feedback"], f.project.read_tabular_quality_feedback(request_id="reg"))
                self.assertEqual(material["feedback"]["outcome"], "condition_met" if met else "condition_not_met")
                self.assertEqual(material["feedback"]["evaluation"]["items"][1]["actual"], 0)
                self.assertIn("untrusted data", plan.build_prompt(context)["system"])
                self.assertEqual(f.project.status(), before); self.assertEqual(f.project.db.read_bytes(), db)

    def test_unknown_before_action_and_after_plan_change_is_not_known(self):
        f, _, selector = self.stage(execute=False)
        material = plan.build_context(f.project, saved_materials=[selector])["supplied_materials"][0]
        self.assertEqual((material["feedback"]["outcome"], material["feedback"]["unknown_reason"]),
                         ("unknown", "controller_not_started"))
        self.assertIsNone(material["feedback"]["action_id"])
        prompt = plan.build_prompt(plan.build_context(f.project, saved_materials=[selector]))["system"]
        self.assertIn("does not prove no action occurred", prompt)
        self.assertIn("authenticate unread parent, child, SQL or artifacts", prompt)
        f.execute()
        later = {"question":"Later", "basis":"Synthetic", "steps":"Wait", "expected_feedback":"Unknown"}
        f.project.save_plan(request_id="later", expected_state_version=f.project.status()["state_version"], plan=later, reason="Synthetic")
        with self.assertRaises(ResearchError) as caught:
            plan.build_context(f.project, saved_materials=[selector])
        self.assertIn("registered plan changed", str(caught.exception))

    def test_plan_change_with_original_sql_or_artifact_drift_rejects(self):
        for kind in ("sql", "artifact"):
            with self.subTest(kind=kind):
                f, _, selector = self.stage()
                action = f.project.status()["actions"][0]
                later = {"question":"Later", "basis":"Synthetic", "steps":"Wait", "expected_feedback":"Unknown"}
                f.project.save_plan(request_id="later", expected_state_version=f.project.status()["state_version"], plan=later, reason="Synthetic")
                if kind == "sql":
                    with sqlite3.connect(f.project.db) as con:
                        con.execute("update actions set fingerprint=? where request_id=?", ("f" * 64, action["request_id"]))
                else:
                    artifact = f.project.root / action["artifact"]
                    artifact.write_bytes(artifact.read_bytes() + b" ")
                with self.assertRaises(ResearchError):
                    plan.build_context(f.project, saved_materials=[selector])

    def test_unknown_value_wins_over_known_failure_and_preserves_null(self):
        rules = fixture.rules(fixture.condition("rows", "gt", 4), fixture.condition("group.group_count", "gte", 1))
        f, _, selector = self.stage(no_groups=True, rules=rules)
        result = plan.build_context(f.project, saved_materials=[selector])["supplied_materials"][0]["feedback"]
        self.assertEqual((result["outcome"], result["unknown_reason"]), ("unknown", "quality_values_unknown"))
        self.assertEqual([item["outcome"] for item in result["evaluation"]["items"]], ["condition_not_met", "unknown"])
        self.assertIsNone(result["evaluation"]["items"][1]["actual"])
        self.assertIsNone(result["action_id"])

    def test_material_excludes_raw_canary_even_if_old_observation_contains_it(self):
        f, _, selector = self.stage(canary=True, rules=fixture.rules(fixture.condition("rows", "eq", 4)))
        context = plan.build_context(f.project, saved_materials=[selector])
        self.assertIn("SYNTHETIC_SECRET_CANARY", canonical(context["feedback"]))
        self.assertNotIn("SYNTHETIC_SECRET_CANARY", canonical(context["supplied_materials"]))
        self.assertNotIn("examples", canonical(context["supplied_materials"]))

    def test_source_artifact_sql_and_code_drift_rejects_without_supplying(self):
        for kind in ("source", "artifact", "sql", "code"):
            with self.subTest(kind=kind):
                f, _, selector = self.stage(); action = f.project.status()["actions"][0]
                if kind == "source": path = f.project.root / "source.json"
                elif kind == "artifact": path = f.project.root / action["artifact"]
                elif kind == "code":
                    from autoresearch import tabular_quality_conditions
                    path = Path(tabular_quality_conditions.__file__).resolve()
                if kind == "sql":
                    with sqlite3.connect(f.project.db) as con:
                        con.execute("update actions set fingerprint=? where request_id=?", ("f" * 64, action["request_id"]))
                elif kind != "code": path.write_bytes(path.read_bytes() + b" ")
                if kind == "code":
                    original = Path.read_bytes
                    def drift(path_value):
                        raw = original(path_value)
                        return raw + b"# synthetic drift" if path_value.resolve() == path else raw
                    manager = patch.object(Path, "read_bytes", drift)
                else: manager = patch.object(ResearchProject,"step",side_effect=AssertionError("step"))
                with manager, self.assertRaises(ResearchError): plan.build_context(f.project, saved_materials=[selector])

    def test_sql_drift_after_initial_materialization_is_rechecked(self):
        f, _, selector = self.stage(); original = saved_materials._quality_material; calls = []
        action = f.project.status()["actions"][0]
        def changed(*args):
            result = original(*args); calls.append(1)
            if len(calls) == 1:
                with sqlite3.connect(f.project.db) as con:
                    con.execute("update actions set fingerprint=? where request_id=?", ("a" * 64, action["request_id"]))
            return result
        with patch.object(saved_materials,"_quality_material",side_effect=changed), self.assertRaises(ResearchError):
            plan.build_context(f.project, saved_materials=[selector])

    def test_frozen_host_plan_and_idempotency_do_not_dispatch(self):
        f, _, selector = self.stage(); host = HostModelSelection(f.project.root)
        body = {"request_id":"selected-plan", "provider":"delegated", "purpose":"plan",
                "expected_state_version":f.project.status()["state_version"], "decision_limit":1,
                "cli_budget_usd":0.1, "reason":"Synthetic material test", "saved_materials":[selector]}
        with patch("autoresearch.host_model_selection.run_claude_selection",side_effect=AssertionError("model")), \
             patch.object(ResearchProject,"step",side_effect=AssertionError("step")):
            record = host.prepare(**body); self.assertEqual(host.prepare(**body),record)
            self.assertEqual(record["context"]["supplied_materials"][0]["feedback"]["outcome"],"condition_met")
            changed = {**body, "saved_materials":[{**selector,"registration_sha256":"0" * 64}]}
            with self.assertRaises(ResearchError) as error: host.prepare(**changed)
            self.assertEqual(error.exception.code,"IDEMPOTENCY_CONFLICT")
            self.assertEqual(f.project.status()["budget"]["local_tool_calls_used"],1)

    def test_selector_and_frozen_result_validation_are_strict(self):
        f, _, selector = self.stage(); context = plan.build_context(f.project, saved_materials=[selector])
        for value in ([selector, selector], [{**selector,"extra":1}], [{**selector,"registration_sha256":"0"*64}]):
            with self.subTest(value=value), self.assertRaises(ResearchError): plan.build_context(f.project,saved_materials=value)
        for changed in (0, True, -1):
            bad = copy.deepcopy(context); bad["supplied_materials"][0]["feedback"]["evaluation"]["items"][0]["actual"] = changed
            with self.subTest(changed=changed), self.assertRaises(ResearchError): plan._context(bad)

    def test_recipe_rejects_selector_and_material_in_nested_context(self):
        f, _, selector = self.stage(); context = plan.build_context(f.project, saved_materials=[selector])
        current = {"schema_version":"research-recipe-v1", "id":"fixture", "version":1, "question":"Wait",
                   "scope_match":{"domain":"data", "contract":"tabular-quality-v1"}, "need":"next_check",
                   "ordered_methods":[{"method_id":"data.grouped-quality-profile", "evaluation_ref":"grouped-quality-profile-v1"}],
                   "on_no_match":"wait"}
        with self.assertRaises(ResearchError): recipe.build_context(f.project,current,"Synthetic",saved_materials=[selector])
        nested = {"schema_version":"recipe-change-context-v1", "research_context":context,
                  "current_recipe":current, "improvement_goal":"Synthetic"}
        with self.assertRaises(ResearchError): recipe._context(nested)

    def test_rows_reference_and_actuals_must_match_the_supplied_profile(self):
        rules = fixture.rules(fixture.condition("numeric.finite", "eq", {"ref":"rows"}, column="x"))
        f, _, selector = self.stage(rules=rules); context = plan.build_context(f.project, saved_materials=[selector])
        for field in ("actual", "expected"):
            bad = copy.deepcopy(context); result = bad["supplied_materials"][0]["feedback"]
            result["evaluation"]["items"][0][field] = 3
            result["evaluation"]["items"][0]["outcome"] = "condition_not_met"
            result["evaluation"]["outcome"] = result["outcome"] = "condition_not_met"
            with self.subTest(field=field), self.assertRaises(ResearchError): plan._context(bad)

    def test_host_frozen_material_cannot_be_consumed_after_sql_drift(self):
        f, _, selector = self.stage(); host = HostModelSelection(f.project.root)
        body = {"request_id":"frozen-plan", "provider":"delegated", "purpose":"plan",
                "expected_state_version":f.project.status()["state_version"], "decision_limit":1,
                "cli_budget_usd":0.1, "reason":"Synthetic freeze", "saved_materials":[selector]}
        record = host.prepare(**body); before = host.state_file.read_bytes()
        action = f.project.status()["actions"][0]
        with sqlite3.connect(f.project.db) as con:
            con.execute("update actions set fingerprint=? where request_id=?", ("f"*64, action["request_id"]))
        with patch("autoresearch.host_model_selection.run_claude_selection",side_effect=AssertionError("model")):
            with self.assertRaises(ResearchError): host._fresh(record)
        self.assertEqual(host.state_file.read_bytes(), before)

    def test_complete_context_size_limit_and_no_partial_output(self):
        f, _, selector = self.stage()
        for index in range(6):
            f.project.record_feedback(request_id="long-note-"+str(index),
                expected_state_version=f.project.status()["state_version"], author="Synthetic",
                comment='\n"\\' * 1600, next_step="Review", action_id=None)
        before = f.project.db.read_bytes()
        with self.assertRaises(ResearchError) as error: plan.build_context(f.project, saved_materials=[selector])
        self.assertEqual(error.exception.code, "INVALID_PLAN_CONTEXT")
        self.assertEqual(f.project.db.read_bytes(), before)

    def test_report_summary_contains_only_bounded_quality_identity(self):
        from autoresearch import host_model_report, project_report
        f, _, selector = self.stage(canary=True, rules=fixture.rules(fixture.condition("rows", "eq", 4)))
        context = plan.build_context(f.project, saved_materials=[selector])
        record = {"request_id":"report-fixture", "context":context}
        summary = host_model_report.supplied_material_summaries(record)
        self.assertEqual(len(summary),1); self.assertEqual(summary[0]["outcome"],"condition_met")
        self.assertNotIn("conditions", summary[0]); self.assertNotIn("SYNTHETIC_SECRET_CANARY", canonical(summary))
        rows = project_report._supplied_material_rows({"host_models":{"records":[record]}})
        self.assertTrue(rows); self.assertNotIn("SYNTHETIC_SECRET_CANARY", canonical(rows))
