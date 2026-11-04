"""Equal column zero counts cannot establish same-row co-occurrence."""
import csv
import importlib.util
import io
from pathlib import Path
import tempfile
import unittest

from test_chemotopo_data import cells, workbook

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/inspect_himsc_source_linkage.py"
SPEC = importlib.util.spec_from_file_location("inspect_himsc_source_linkage", SCRIPT)
audit_module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(audit_module)


class HiMSCSourceLinkageTests(unittest.TestCase):
    def test_equal_zero_totals_are_disjoint_and_row_two_mapping_and_cache_text_are_explicit(self):
        root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        rows = [[1, 1, "1_1", 0, 4, 5], [2, 1, "2_1", 6, 0, 7], [3, 1, "3_1", 8, 9, 0]]
        buffer = io.StringIO(newline="")
        writer = csv.writer(buffer)
        writer.writerow(audit_module.HEADERS)
        writer.writerows(rows)
        csv_path, xlsx_path = root / "data.csv", root / "source.xlsx"
        csv_path.write_bytes(buffer.getvalue().encode("utf-8"))
        xlsx_path.write_bytes(workbook({"B8S1": cells(audit_module.HEADERS, rows)}))
        audit = audit_module.inspect_linkage(csv_path.read_bytes(), xlsx_path.read_bytes())
        self.assertTrue(audit["coverage"]["complete_projection_match"])
        self.assertEqual(audit["coverage"]["exact_projection_matches"], 18)
        joint = audit["zero_cooccurrence"]
        self.assertEqual(set(joint["per_column_zero_counts"].values()), {1})
        self.assertEqual((joint["any_zero_rows"], joint["all_three_zero_rows"], joint["partial_zero_rows"]), (3, 0, 3))
        self.assertEqual({mask: count for mask, count in joint["joint_masks"].items() if count}, {"001": 1, "010": 1, "100": 1})
        self.assertEqual([(row["logical_record"], row["workbook_row"], row["zero_mask"]) for row in audit["zero_rows"]],
                         [(1, 2, "100"), (2, 3, "010"), (3, 4, "001")])
        self.assertEqual(audit["rows"][0]["cells"][3]["workbook_cell"], "B8S1!D2")
        self.assertEqual(audit["rows"][2]["cells"][5]["workbook_cell"], "B8S1!F4")
        changed = csv_path.read_bytes().replace(b"1,1,1_1,0,4,5", b"1,1,1_1,0.0,4,5")
        different_text = audit_module.inspect_linkage(changed, xlsx_path.read_bytes())
        self.assertFalse(different_text["coverage"]["complete_projection_match"])
        mismatch = different_text["mismatches"][0]
        self.assertEqual((mismatch["logical_record"], mismatch["workbook_cell"], mismatch["comparison"]),
                         (1, "B8S1!D2", "numeric_value_equal_text_diff"))
        self.assertTrue(mismatch["numeric_value_match"])
        self.assertEqual(different_text["zero_cooccurrence"], joint)
        metadata_rows = [[0, 2, 1, 1], [1, 1, 1, 1], [1, 1, 1, 1]]
        metadata = workbook({"iMSC_B8S1": cells(audit_module.METADATA_HEADERS, metadata_rows)})
        linked = audit_module.inspect_metadata(audit, metadata)
        self.assertFalse(linked["layout_position_correspondence_complete"])
        self.assertEqual(linked["checks"]["same_position_topo_chem_matches"], 0)
        self.assertEqual(linked["rows"][0]["Topo_Chem_candidate_metadata_rows"], [3, 4])
        self.assertEqual(linked["rows"][0]["correspondence_status"], "not_established")
        self.assertEqual(linked["rows"][0]["join_basis"], [])
        self.assertEqual(linked["keys"]["Topo_Chem"]["max_candidate_rows"], 2)
        self.assertEqual(linked["keys"]["Topo_Chem_Row"]["max_candidate_rows"], 2)
        self.assertEqual(linked["keys"]["Series"]["duplicate_keys"], 1)
        self.assertTrue(all(not row["unique_image_or_observation_join"] for row in linked["rows"]))


if __name__ == "__main__":
    unittest.main()
