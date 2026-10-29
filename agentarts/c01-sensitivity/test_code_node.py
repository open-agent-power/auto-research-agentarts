"""Local regression tests for the sandbox-tested C01 code node; no cloud calls.

Run: .venv/Scripts/python.exe -B agentarts/c01-sensitivity/test_code_node.py -v
The frozen-CSV check skips when the ignored local C01 evidence is unavailable.
"""

import copy
import csv
import hashlib
import json
from pathlib import Path
import unittest

from code_node import main


HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
X = "water_contact_angle_deg"
Y = "cell_seeding_efficiency_24h_pct"


class CodeNodeTests(unittest.TestCase):
    def setUp(self):
        self.public = json.loads((HERE / "public-input.json").read_text(encoding="utf-8"))

    def calculate(self, value):
        reply = main({"query": json.dumps(value, ensure_ascii=False)})
        self.assertEqual(set(reply), {"result"})
        self.assertIsInstance(reply["result"], str)
        return json.loads(reply["result"])

    def samples(self, xs, ys=None):
        if ys is None:
            ys = [index % 101 for index in range(len(xs))]
        return {"source_doi": self.public["source_doi"], "samples": [
            {"sample_id": "sample-" + str(index), X: x, Y: y}
            for index, (x, y) in enumerate(zip(xs, ys))
        ]}

    def test_public_correlations_match_independent_scipy(self):
        try:
            from scipy.stats import pearsonr
        except ImportError:
            self.skipTest("SciPy is optional for the independent numerical reference")

        result = self.calculate(self.public)
        samples = self.public["samples"]
        xs, ys = [row[X] for row in samples], [row[Y] for row in samples]
        full = float(pearsonr(xs, ys).statistic)
        self.assertAlmostEqual(result["pearson_r"], full, delta=1e-12)
        self.assertEqual(len(result["leave_one_out"]), len(samples))
        changed = []
        for index, actual in enumerate(result["leave_one_out"]):
            with self.subTest(removed=samples[index]["sample_id"]):
                expected = float(pearsonr(xs[:index] + xs[index + 1:],
                                         ys[:index] + ys[index + 1:]).statistic)
                self.assertEqual(actual["removed_sample_id"], samples[index]["sample_id"])
                self.assertAlmostEqual(actual["pearson_r"], expected, delta=1e-12)
                self.assertEqual(actual["sign_changed"], full * expected < 0)
                if full * expected < 0:
                    changed.append(samples[index]["sample_id"])
        self.assertEqual(changed, ["Alloy 4"])
        self.assertEqual(result["sign_changes"], 1)
        self.assertEqual(result["status"], "needs_review")

    def test_eight_public_samples_match_verified_frozen_csv(self):
        frozen = REPO / "runs/c01-tnzst-r10-final"
        csv_path = frozen / "cleaned_samples.csv"
        if not csv_path.is_file():
            self.skipTest("Ignored frozen C01 CSV is not present in this checkout")
        manifest = json.loads((frozen / "output-manifest.json").read_text(encoding="utf-8"))
        raw = csv_path.read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(),
                         manifest["files"]["cleaned_samples.csv"])
        with csv_path.open(encoding="utf-8-sig", newline="") as stream:
            expected = [{"sample_id": row["sample_id"], X: float(row[X]), Y: float(row[Y])}
                        for row in csv.DictReader(stream)]
        self.assertEqual(set(self.public), {"source_doi", "samples"})
        self.assertEqual(self.public["source_doi"], "10.17632/tt7gwkpck8.1")
        self.assertEqual(len(expected), 8)
        self.assertEqual(self.public["samples"], expected)

    def test_nonfinite_boolean_nonnumeric_and_out_of_domain_values_are_rejected(self):
        for field, upper in ((X, 180), (Y, 100)):
            for invalid in (float("nan"), float("inf"), -float("inf"),
                            True, False, "1.0", None, -1, upper + 1):
                with self.subTest(field=field, value=invalid):
                    data = copy.deepcopy(self.public)
                    data["samples"][0][field] = invalid
                    with self.assertRaises(ValueError):
                        self.calculate(data)

    def test_duplicate_sample_identity_is_rejected(self):
        data = copy.deepcopy(self.public)
        data["samples"][1]["sample_id"] = data["samples"][0]["sample_id"]
        with self.assertRaises(ValueError):
            self.calculate(data)

    def test_extra_top_level_or_sample_fields_are_rejected(self):
        for level in ("top", "sample"):
            with self.subTest(level=level):
                data = copy.deepcopy(self.public)
                target = data if level == "top" else data["samples"][0]
                target["path"] = "not-an-allowed-input"
                with self.assertRaises(ValueError):
                    self.calculate(data)

    def test_sample_count_is_bounded_and_128_is_accepted(self):
        for count in (3, 129):
            with self.subTest(count=count):
                with self.assertRaises(ValueError):
                    self.calculate(self.samples(list(range(count))))
        result = self.calculate(self.samples(list(range(128))))
        self.assertEqual(result["sample_count"], 128)
        self.assertEqual(len(result["leave_one_out"]), 128)

    def test_query_limit_counts_utf8_bytes(self):
        data = self.samples(list(range(128)))
        for row in data["samples"]:
            row["sample_id"] += "汉" * 60
        raw = json.dumps(data, ensure_ascii=False)
        self.assertLessEqual(len(raw), 32768)
        self.assertGreater(len(raw.encode("utf-8")), 32768)
        with self.assertRaisesRegex(ValueError, "32 KiB"):
            main({"query": raw})

    def test_constant_variable_returns_null_and_review(self):
        for xs, ys in (([1, 1, 1, 1], [1, 2, 3, 4]),
                       ([1, 2, 3, 4], [1, 1, 1, 1])):
            with self.subTest(xs=xs, ys=ys):
                result = self.calculate(self.samples(xs, ys))
                self.assertIsNone(result["pearson_r"])
                self.assertTrue(all(row["pearson_r"] is None for row in result["leave_one_out"]))
                self.assertEqual(result["status"], "needs_review")

    def test_one_undefined_omission_requires_review_without_sign_change(self):
        result = self.calculate(self.samples([0, 0, 0, 1], [1, 2, 3, 4]))
        self.assertIsNotNone(result["pearson_r"])
        self.assertIsNone(result["leave_one_out"][3]["pearson_r"])
        self.assertTrue(all(row["pearson_r"] is not None for row in result["leave_one_out"][:3]))
        self.assertEqual(result["sign_changes"], 0)
        self.assertEqual(result["status"], "needs_review")


if __name__ == "__main__":
    unittest.main()
