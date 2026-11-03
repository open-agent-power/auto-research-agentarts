"""Four necessary bounded-input/mechanical-statistics checks; no fit or network."""

import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from autoresearch import tabular_quality_adapter as adapter
from autoresearch.contracts import ResearchError, canonical, fingerprint


class TabularQualityAdapterTests(unittest.TestCase):
    def capture(self, text, **changes):
        root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        spec = {"schema_version": "tabular-quality-spec-v1", "file": "observations.csv",
                "dataset_label": "Unverified test observations", "source_url": "urn:local:observations",
                "license_note": "Unknown; test declaration only", "sample_unit": "declared_record",
                "group_columns": ["batch"], "key_columns": ["id"], "numeric_columns": ["x", "y"],
                "target_column": "y", "target_unit": "declared_unit", "missing_tokens": ["", "NA"],
                "delimiter": ",", "provenance": {"origin_sha256": "a" * 64, "description": "Unverified origin declaration"}}
        spec.update(changes)
        raw = text.encode("utf-8")
        (root / spec["file"]).write_bytes(raw)
        (root / "spec.json").write_text(json.dumps(spec, ensure_ascii=False), encoding="utf-8")
        return adapter.capture_source(root), raw

    def test_numeric_missing_duplicate_and_group_counts_preserve_originals(self):
        payload, raw = self.capture("id,batch,x,y\na,G,0,1\na,G,0,1\na,G,1,NaN\nb,H,,inf\nc,H,NA,bad\nd,,2,3\n")
        payload = adapter.load_source(canonical(payload).encode("utf-8"))
        result = adapter.execute(payload)
        profile = result["result"]["profile"]
        self.assertEqual((profile["rows"], profile["columns"], profile["exact_duplicate_rows"]), (6, 4, 1))
        self.assertEqual(profile["key_columns"], {"complete_rows": 6, "incomplete_rows": 0,
                         "duplicate_groups": 1, "duplicate_rows": 2, "conflict_groups": 1})
        self.assertEqual(profile["group_columns"], {"group_count": 2, "singletons": 0, "repeated_groups": 2,
                         "rows_in_repeated_groups": 5, "min_group_size": 2, "max_group_size": 3, "incomplete_group_rows": 1})
        x, y = profile["numeric_columns"]
        self.assertEqual(x["counts"], {"finite": 4, "zero": 2, "empty": 1, "declared_missing": 1,
                                      "invalid_numeric": 0, "nonfinite": 0})
        self.assertEqual(y["counts"]["nonfinite"], 2)
        self.assertEqual(y["counts"]["invalid_numeric"], 1)
        self.assertEqual((x["min"], x["max"]), (0, 2))
        self.assertLessEqual(len(profile["examples"]), 5)
        self.assertEqual([item for item in profile["examples"] if item["kind"] == "exact_duplicate_row"],
                         [{"kind": "exact_duplicate_row", "logical_record": 2, "physical_line_end": 3,
                           "first_logical_record": 1, "first_physical_line_end": 2}])
        self.assertEqual(profile["mechanical_status"], "needs_data_review")
        self.assertEqual(result["evidence_refs"][0]["source_sha256"], hashlib.sha256(raw).hexdigest())
        self.assertEqual(adapter.next_decision(result)["project_status"], "waiting")
        self.assertEqual(result["result"]["scope"]["target_status"], "declared_unconfirmed")
        self.assertEqual((result["new_fits"], result["model_calls"], result["scientific_validation"]), (0, 0, False))
        json.dumps(result, allow_nan=False)

    def test_distinct_tsv_schema_and_logical_vs_physical_coordinates(self):
        payload, _ = self.capture('\ufeffsample\treading\tnote\nA\t2\t"two\nlines"\nB\tNA\tok\n',
                                  file="another.tsv", delimiter="\t", group_columns=[], key_columns=[],
                                  numeric_columns=["reading"], target_column=None, target_unit=None)
        profile = adapter.execute(payload)["result"]["profile"]
        self.assertEqual((profile["rows"], profile["columns"]), (2, 3))
        self.assertIsNone(profile["group_columns"]["group_count"])
        self.assertIsNone(profile["key_columns"]["duplicate_groups"])
        self.assertEqual(profile["examples"][0]["logical_record"], 2)
        self.assertEqual(profile["examples"][0]["physical_line_end"], 4)
        clean, _ = self.capture("identifier,measurement\na,1\nb,2\n", group_columns=[], key_columns=[],
                                numeric_columns=["measurement"], target_column=None, target_unit=None)
        self.assertEqual(adapter.execute(clean)["result"]["profile"]["mechanical_status"], "no_flags_in_selected_checks")

    def test_packet_hash_original_byte_hash_and_scope_are_bound(self):
        payload, _ = self.capture("id,batch,x,y\na,G,1,2\n")
        for changed in ("packet", "bytes", "scope"):
            candidate = copy.deepcopy(payload)
            if changed == "packet":
                candidate["spec"]["dataset_label"] = "changed"
            elif changed == "bytes":
                candidate["source"]["sha256"] = "0" * 64
                candidate["snapshot_sha256"] = fingerprint({key: value for key, value in candidate.items() if key != "snapshot_sha256"})
            else:
                candidate["scope"]["target_unit"] = "invented"
                candidate["snapshot_sha256"] = fingerprint({key: value for key, value in candidate.items() if key != "snapshot_sha256"})
            with self.subTest(changed=changed), self.assertRaises(ResearchError) as caught:
                adapter.load_source(canonical(candidate).encode("utf-8"))
            self.assertEqual(caught.exception.code, "EVIDENCE_CHANGED")
        for raw in (b'{"a":1,"a":2}', b'{"a":NaN}', b'{"a":Infinity}', b'\xff'):
            with self.subTest(raw=raw), self.assertRaises(ResearchError) as caught:
                adapter.load_source(raw)
            self.assertEqual(caught.exception.code, "INVALID_SOURCE_JSON")

    def test_ambiguous_headers_width_schema_and_unsafe_path_reject(self):
        for text in ("id,batch,x,x\na,G,1,2\n", "id,batch,x,Y\na,G,1,2\n",
                     "id,batch,x, y\na,G,1,2\n", "id,batch,x,y\na,G,1\n",
                     'id,batch,x,y\na,G,1,"unterminated\n'):
            with self.subTest(text=text), self.assertRaises(ResearchError):
                self.capture(text)
        with self.assertRaises(ResearchError) as caught:
            self.capture("id,batch,x,y\na,G,1,2\n", missing_tokens=["NA"])
        self.assertEqual(caught.exception.code, "INVALID_SPEC")
        with self.assertRaises(ResearchError) as caught:
            adapter._filename("../outside.csv")
        self.assertEqual(caught.exception.code, "UNSAFE_PATH")


if __name__ == "__main__":
    unittest.main()
