"""Arithmetic boundaries for the offline audit, no research execution."""
import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('stability_audit', Path(__file__).parents[1] / 'scripts/audit_saved_validation_stability.py')
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


class StabilityArithmeticTests(unittest.TestCase):
    def rows(self):
        return [{'query_id': str(i), 'baseline': 0.0, 'candidate': 0.0} for i in range(100)]

    def test_one_positive_pair_removed_reaches_zero(self):
        rows = self.rows(); rows[0]['candidate'] = 1.0
        result = audit.summarize_pairs(rows, {'mean': .01, 'wins': 1, 'losses': 0, 'ties': 99})
        a = result['aggregate']
        self.assertEqual(a['leave_one_out_min'], 0)
        self.assertAlmostEqual(a['leave_one_out_max'], 1/99)
        self.assertEqual(a['leave_one_out_near_zero_count'], 1)
        self.assertEqual(a['leave_one_out_opposite_sign_count'], 0)

    def test_opposite_sign_and_original_near_zero_are_distinct(self):
        rows = self.rows(); rows[0]['candidate'] = .5; rows[1]['baseline'] = .2
        a = audit.summarize_pairs(rows, {'mean': .003, 'wins': 1, 'losses': 1, 'ties': 98})['aggregate']
        self.assertEqual(a['leave_one_out_opposite_sign_count'], 1)
        rows[1]['baseline'] = .5
        a = audit.summarize_pairs(rows, {'mean': 0, 'wins': 1, 'losses': 1, 'ties': 98})['aggregate']
        self.assertIsNone(a['leave_one_out_near_zero_count'])
        self.assertIsNone(a['leave_one_out_opposite_sign_count'])
        self.assertEqual(a['leave_one_out_sign_counts'], {'positive': 1, 'negative': 1, 'near_zero': 98})

    def test_missing_duplicate_invalid_and_saved_disagreement_fail(self):
        rows = self.rows(); summary = {'mean': 0, 'wins': 0, 'losses': 0, 'ties': 100}
        for change in ('short', 'duplicate', 'bool', 'nan', 'summary'):
            data = [dict(row) for row in rows]; saved = dict(summary)
            if change == 'short': data.pop()
            if change == 'duplicate': data[0]['query_id'] = data[1]['query_id']
            if change == 'bool': data[0]['candidate'] = True
            if change == 'nan': data[0]['candidate'] = float('nan')
            if change == 'summary': saved['mean'] = .01
            with self.subTest(change=change), self.assertRaises(ValueError):
                audit.summarize_pairs(data, saved)
