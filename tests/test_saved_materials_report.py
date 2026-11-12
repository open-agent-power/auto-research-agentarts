"""Pure frozen-value presentation checks; no research, model or fitted fixtures."""
import copy
import unittest

from autoresearch.host_model_report import supplied_material_summaries
from autoresearch.project_report import _supplied_material_rows


class SavedMaterialsReportTests(unittest.TestCase):
    def context(self):
        return {"schema_version": "research-plan-context-v3", "supplied_materials": [{
            "action_id": "diagnostic-17", "result_sha256": "a" * 64,
            "artifact_ref": "artifacts/diagnostic-17.json",
            "producer": {"request_id": "diagnostic-request", "method_id": "data.saved-oof-group-diagnostics",
                         "code_identity": "b" * 64, "source_snapshot_sha256": "c" * 64, "design_version": 2},
            "source_ref": {"action_id": "validation-8", "request_id": "source-request", "result_sha256": "d" * 64,
                           "design_version": 1},
            "fields": {"groups": {"path": ["tool_result", "result", "diagnostic", "groups"], "count": 1,
                                  "value": [{"groups": ["do-not-repeat-complete-value"], "n": 7}]},
                       "rows": {"path": ["tool_result", "result", "diagnostic", "rows"], "count": 1,
                                "value": [{"input_values": [], "observed": 4, "predicted": 5}]}},
            "coverage": "complete_saved_fields", "scientific_validation": False}]}

    def test_summary_preserves_only_actual_fields_counts_and_provenance(self):
        context = self.context()
        record = {"request_id": "host-1", "context": context}
        before = copy.deepcopy(record)
        summary = supplied_material_summaries(record)
        material = summary[0]
        self.assertEqual(set(material["fields"]), {"groups", "rows"})
        self.assertEqual(material["fields"]["rows"], {"path": ["tool_result", "result", "diagnostic", "rows"], "count": 1})
        self.assertEqual(material["producer"], context["supplied_materials"][0]["producer"])
        self.assertEqual(material["source_ref"], context["supplied_materials"][0]["source_ref"])
        self.assertEqual(material["coverage"], "complete_saved_fields")
        self.assertIs(material["scientific_validation"], False)
        self.assertNotIn("value", str(material["fields"]))
        material["producer"]["design_version"] = 99
        self.assertEqual(record, before)

    def test_plan_and_nested_recipe_report_use_same_frozen_materials(self):
        context = self.context()
        plan = {"request_id": "host-1", "context": context}
        recipe = {"request_id": "host-1", "context": {"schema_version": "recipe-change-context-v1", "research_context": context}}
        self.assertEqual(supplied_material_summaries(plan), supplied_material_summaries(recipe))
        rows = _supplied_material_rows({"host_models": {"records": [recipe]}})
        rendered = str(rows)
        for expected in ("host-1", "diagnostic-17", "groups: 1", "rows: 1", "validation-8", "a" * 64, "b" * 64, "c" * 64):
            self.assertIn(expected, rendered)
        for excluded in ("do-not-repeat-complete-value", "input_values", "folds:", "observed", "predicted"):
            self.assertNotIn(excluded, rendered)

    def test_legacy_context_or_references_do_not_invent_supplied_materials(self):
        contexts = [None, {}, {"schema_version": "research-plan-context-v2", "feedback": [{"artifact_ref": "artifacts/x.json"}]},
                    {"schema_version": "recipe-change-context-v1", "research_context": {"schema_version": "research-plan-context-v2"}},
                    {"supplied_materials": [], "research_context": self.context()}]
        for context in contexts:
            with self.subTest(context=context):
                record = {"request_id": "old-host", "context": context, "saved_materials": [{"action_id": "x", "fields": ["rows"]}]}
                before = copy.deepcopy(record)
                self.assertEqual(supplied_material_summaries(record), [])
                self.assertEqual(_supplied_material_rows({"host_models": {"records": [record]}}), [])
                self.assertEqual(record, before)


if __name__ == "__main__":
    unittest.main()
