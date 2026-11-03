"""Three necessary grouped-count/source-binding checks without fits or network."""

import copy
import json
from pathlib import Path
import tempfile
import unittest

from autoresearch import grouped_quality_adapter as grouped, method_registry as registry, tabular_quality_adapter as tabular
from autoresearch.contracts import ResearchError, fingerprint


class GroupedQualityAdapterTests(unittest.TestCase):
    def payload(self, text, **changes):
        root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        spec = {"schema_version": "tabular-quality-spec-v1", "file": "measurements.csv", "dataset_label": "Test declarations",
                "source_url": "urn:test:measurements", "license_note": "Unknown test declaration", "sample_unit": "declared_record",
                "group_columns": ["batch"], "key_columns": [], "numeric_columns": ["reading"],
                "target_column": "reading", "target_unit": "declared_unit", "missing_tokens": ["", "NA"],
                "delimiter": ",", "provenance": {"origin_sha256": "a" * 64, "description": "Unverified original declaration"}}
        spec.update(changes)
        (root / spec["file"]).write_text(text, encoding="utf-8", newline="")
        (root / "spec.json").write_text(json.dumps(spec), encoding="utf-8")
        return tabular.capture_source(root)

    def parameters(self):
        return {"based_on_action_id": "action-saved-primary", "based_on_result_sha256": "b" * 64}

    def test_complete_group_concentration_and_compact_counts(self):
        payload = self.payload("batch,reading,note\na,0,one\na,0,two\nb,1,three\nb,0,four\nc,2,five\n")
        original = copy.deepcopy(payload)
        result = grouped.execute(payload, self.parameters())
        value = result["result"]; summary = value["summary"]
        self.assertEqual((summary["rows"], summary["complete_group_rows"], summary["incomplete_group_rows"], summary["group_count"]), (5, 5, 0, 3))
        reading = summary["numeric_columns"][0]
        self.assertEqual(reading["totals"], {"finite": 5, "zero": 3, "empty": 0, "declared_missing": 0, "invalid_numeric": 0, "nonfinite": 0})
        zero = reading["concentration"]["zero"]
        self.assertEqual((zero["total"], zero["affected_groups"], zero["max_group_count"]), (3, 2, 2))
        self.assertAlmostEqual(zero["max_group_share"], 2 / 3)
        first = next(item for item in value["groups"] if item["group_id"] == "group-" + fingerprint(["a"]))
        self.assertEqual(first["numeric_counts"], [[2, 2, 0, 0, 0, 0]])
        self.assertEqual(first["first_coordinate"], {"logical_record": 1, "physical_line_end": 2})
        self.assertEqual(set(first), {"group_id", "rows", "first_coordinate", "numeric_counts"})
        self.assertEqual(value["predecessor"], self.parameters())
        self.assertEqual(value["scope"]["input_contract"], "tabular-quality-v1")
        self.assertEqual(payload, original)
        self.assertEqual((result["model_calls"], result["new_fits"], result["scientific_validation"]), (0, 0, False))
        self.assertEqual(grouped.next_decision(result)["project_status"], "waiting")
        json.dumps(result, allow_nan=False)

    def test_exact_tokens_incomplete_groups_and_physical_coordinates(self):
        payload = self.payload('batch,reading,note\na,0,"two\nlines"\na,,empty\nb,NA,missing\nb,NaN,declared\n,inf,incomplete\nc,bad,invalid\nc,nan,nonfinite\n',
                               missing_tokens=["", "NA", "NaN"])
        value = grouped.execute(payload, self.parameters())["result"]
        summary = value["summary"]; reading = summary["numeric_columns"][0]
        self.assertEqual((summary["complete_group_rows"], summary["incomplete_group_rows"], summary["group_count"]), (6, 1, 3))
        self.assertEqual(reading["totals"], {"finite": 1, "zero": 1, "empty": 1, "declared_missing": 2, "invalid_numeric": 1, "nonfinite": 2})
        self.assertEqual(reading["incomplete_group_totals"]["nonfinite"], 1)
        self.assertEqual(reading["concentration"]["nonfinite"]["total"], 1)
        for kind in grouped.COUNTS_ORDER:
            self.assertEqual(reading["totals"][kind], reading["complete_group_totals"][kind] + reading["incomplete_group_totals"][kind])
        self.assertEqual(value["incomplete_group"]["numeric_counts"], [[0, 0, 0, 0, 0, 1]])
        self.assertEqual(value["examples"][0], {"kind": "zero", "column": "reading", "group_id": "group-" + fingerprint(["a"]),
                                               "logical_record": 1, "physical_line_end": 3})
        self.assertLessEqual(len(value["examples"]), 5)
        self.assertTrue(all("token" not in item and "row" not in item for item in value["examples"]))

    def test_parameter_source_scope_and_primary_registry_boundaries(self):
        payload = self.payload("batch,reading\na,1\n")
        for parameters in ({}, {**self.parameters(), "path": "arbitrary.csv"},
                           {**self.parameters(), "based_on_result_sha256": "bad"},
                           {**self.parameters(), "based_on_action_id": "../outside"}):
            with self.subTest(parameters=parameters), self.assertRaises(ResearchError) as caught:
                grouped.execute(payload, parameters)
            self.assertEqual(caught.exception.code, "INVALID_REQUEST")
        absent = self.payload("batch,reading\na,1\n", group_columns=[])
        with self.assertRaises(ResearchError) as caught:
            grouped.execute(absent, self.parameters())
        self.assertEqual(caught.exception.code, "UNSUPPORTED_SCOPE")
        payload["source"]["sha256"] = "0" * 64
        with self.assertRaises(ResearchError) as caught:
            grouped.execute(payload, self.parameters())
        self.assertEqual(caught.exception.code, "EVIDENCE_CHANGED")
        with self.assertRaises(ResearchError) as caught:
            registry.get(grouped.TOOL_ID)
        self.assertEqual(caught.exception.code, "METHOD_NOT_SUPPORTED")
        self.assertIs(registry.get_analysis(grouped.TOOL_ID), grouped)
        self.assertEqual(registry.followup_ids(tabular.TOOL_ID), [grouped.TOOL_ID])
        self.assertEqual(registry.followup_ids("p02.saved-oof-residuals"), [])
        self.assertEqual(registry.evaluation_ref(grouped.TOOL_ID), "grouped-quality-profile-v1")


if __name__ == "__main__":
    unittest.main()
