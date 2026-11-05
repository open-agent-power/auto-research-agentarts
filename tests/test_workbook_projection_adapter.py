"""Two bounded candidate-projection checks, with synthetic temporary inputs only."""

import copy
import csv
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest

from autoresearch import tabular_quality_adapter as tabular, workbook_projection_adapter as adapter
from autoresearch.contracts import ResearchError
from test_chemotopo_data import cells, workbook


class WorkbookProjectionAdapterTests(unittest.TestCase):
    def payload(self, text, origin, declared_sha=None):
        root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        header = next(csv.reader(io.StringIO(text)))
        digest = hashlib.sha256(origin).hexdigest()
        spec = {"schema_version": "tabular-quality-spec-v1", "file": "observations.csv",
                "dataset_label": "Synthetic candidate projection", "source_url": "urn:test:projection",
                "license_note": "Test declaration only", "sample_unit": "declared_record", "group_columns": [],
                "key_columns": [], "numeric_columns": [header[1]], "target_column": header[1], "target_unit": "declared",
                "missing_tokens": [""], "delimiter": ",", "provenance": {"origin_sha256": declared_sha or digest,
                "description": "Unconfirmed projection declaration"}}
        (root / "observations.csv").write_bytes(text.encode("utf-8"))
        (root / "spec.json").write_text(json.dumps(spec), encoding="utf-8")
        return {"tabular_source": tabular.capture_source(root), "origin_bytes": origin,
                "origin_source": {"id": "saved-workbook", "sha256": digest, "media_type": "application/octet-stream"}}

    def parameters(self):
        return {"based_on_action_id": "action-saved-primary", "based_on_result_sha256": "b" * 64,
                "origin_receipt_sha256": "c" * 64, "origin_source_id": "saved-workbook"}

    def test_multiple_exact_candidates_cached_formulas_and_exact_text_coordinates(self):
        header = ["specimen", "reading_42", "memo"]
        data = cells(header, [["alpha", ('HYPERLINK("https://invalid/","not executed")', 2), "two\nlines"],
                              ["beta", 1.0, None]])
        variant = copy.deepcopy(data)
        variant["B3"] = 1
        origin = workbook({"First candidate": data, "Second candidate": data, "Numeric spelling": variant})
        payload = self.payload('specimen,reading_42,memo\nalpha,2,"two\nlines"\nbeta,1.0,\n', origin)
        original = copy.deepcopy(payload)
        result = adapter.execute(payload, self.parameters())
        value = result["result"]
        self.assertEqual(value["summary"], {"csv_rows": 2, "csv_columns": 3, "candidate_sheet_count": 3,
                         "exact_candidate_sheet_count": 2, "exact_candidate_sheets": ["First candidate", "Second candidate"],
                         "candidate_status": "ambiguous"})
        for candidate in value["candidates"][:2]:
            self.assertTrue(candidate["projection_candidate_exact"])
            self.assertEqual((candidate["compared_cells"], candidate["exact_matches"], candidate["formula_cells"],
                              candidate["missing_cells"]), (6, 6, 1, 1))
        candidate = value["candidates"][2]
        self.assertEqual((candidate["exact_matches"], candidate["numeric_equal_text_diff"], candidate["mismatch_cells"]), (5, 1, 0))
        self.assertFalse(candidate["projection_candidate_exact"])
        example = candidate["examples"][0]
        self.assertEqual((example["logical_record"], example["physical_line_end"], example["cell"],
                          example["csv_text"], example["workbook_raw"], example["workbook_status"]), (2, 4, "B3", "1.0", "1", "finite"))
        self.assertEqual(payload, original)
        self.assertEqual(value["formulas_executed"], 0)
        self.assertEqual(value["origin"]["conversion_status"], "unconfirmed")
        self.assertEqual(value["scope"]["target_status"], "declared_unconfirmed")
        self.assertFalse(result["scientific_validation"])
        self.assertEqual(result["observations"][0]["kind"], "workbook_projection_check")
        decision = adapter.next_decision(result)
        self.assertEqual((decision["project_status"], decision["next_action"]["method_id"]), ("waiting", "research.source-selection"))
        self.assertIn("multiple exact", " ".join(decision["next_action"]["required_evidence"]))
        self.assertNotIn("approved", json.dumps(result))
        json.dumps(result, allow_nan=False)

    def test_missing_header_wrong_rows_and_bound_origin_or_parameters(self):
        header, text = ["entity", "amplitude"], "entity,amplitude\na,1\nb,2\n"
        gap = cells(header, [["a", 1], [None, None], ["b", 2]])
        cases = {"header": cells(["different", "names"], [["a", 1], ["b", 2]]),
                 "wrong_order": cells(header, [["b", 2], ["a", 1]]), "row_gap": gap}
        for case, data in cases.items():
            with self.subTest(case=case):
                result = adapter.execute(self.payload(text, workbook({"Data": data})), self.parameters())
                self.assertEqual(result["status"], "completed")
                value = result["result"]
                self.assertEqual(value["summary"]["exact_candidate_sheet_count"], 0)
                if case == "header":
                    self.assertEqual(value["candidates"], [])
                    self.assertEqual(value["summary"]["candidate_status"], "missing_header_candidate")
                else:
                    candidate = value["candidates"][0]
                    self.assertGreater(candidate["mismatch_cells"], 0)
                    self.assertLessEqual(len(candidate["examples"]), 5)
                    self.assertEqual(candidate["compared_cells"], candidate["exact_matches"]
                                     + candidate["numeric_equal_text_diff"] + candidate["mismatch_cells"])
                    if case == "row_gap":
                        self.assertEqual(candidate["missing_workbook_rows"], [3])
                        self.assertEqual(candidate["extra_workbook_rows"], [4])
        origin = workbook({"Data": cells(header, [["a", 1], ["b", 2]])})
        payload = self.payload(text, origin)
        changed_origin = copy.deepcopy(payload)
        changed_origin["origin_source"]["sha256"] = "0" * 64
        for case, candidate, parameters, code in (
            ("origin_sha", changed_origin, self.parameters(), "EVIDENCE_CHANGED"),
            ("declared_origin", self.payload(text, origin, "a" * 64), self.parameters(), "EVIDENCE_CHANGED"),
            ("predecessor_digest", payload, {**self.parameters(), "based_on_result_sha256": "bad"}, "INVALID_REQUEST"),
            ("parameter_fields", payload, {**self.parameters(), "path": "other.xlsx"}, "INVALID_REQUEST"),
        ):
            with self.subTest(case=case), self.assertRaises(ResearchError) as caught:
                adapter.execute(candidate, parameters)
            self.assertEqual(caught.exception.code, code)


if __name__ == "__main__":
    unittest.main()
