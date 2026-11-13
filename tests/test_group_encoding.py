"""Native group-ID equivalence only: no estimator fitting or research actions.

Run after the reviewed encode_groups helper is integrated into the adapter.
Inputs match its existing caller: ordered lists of tuple[str, ...] labels.
"""
from copy import deepcopy
import random
import unittest

import numpy as np
from sklearn.model_selection import GroupKFold

from autoresearch.ridge_validation_adapter import encode_groups


def original_ids(labels):
    unique = list(dict.fromkeys(labels))
    return [unique.index(label) for label in labels]


class GroupEncodingTests(unittest.TestCase):
    def test_first_appearance_order_is_not_lexicographic(self):
        labels = [("z",), ("a",), ("z",), ("m",), ("a",), ("b",)]
        self.assertEqual(encode_groups(labels), [0, 1, 0, 2, 1, 3])

    def test_unicode_and_multi_field_identity(self):
        labels = [("α", "水"), ("水", "α"), ("α", "水"), ("α水", ""), ("α", "水", "")]
        self.assertEqual(encode_groups(labels), [0, 1, 0, 2, 3])
        # Product random-CV can have zero grouping columns; the product binding
        # also permits eight fields. Native microbenchmarks used narrower data.
        for product_labels, expected in [([(), (), ()], [0, 0, 0]),
                ([("z",) * 8, ("a",) * 8, ("z",) * 8], [0, 1, 0])]:
            with self.subTest(group_fields=len(product_labels[0])):
                self.assertEqual(encode_groups(product_labels), expected)
                self.assertEqual(encode_groups(product_labels), original_ids(product_labels))

    def test_empty_input_retains_empty_list(self):
        result = encode_groups([])
        self.assertIs(type(result), list)
        self.assertEqual(result, [])

    def test_all_unique_2048_row_boundary(self):
        labels = [("group-" + str(index),) for index in reversed(range(2048))]
        actual = encode_groups(labels)
        self.assertEqual(actual, list(range(2048)))
        self.assertTrue(all(type(value) is int for value in actual))

    def test_all_repeated_2048_row_boundary(self):
        labels = [("same", "group")] * 2048
        self.assertEqual(encode_groups(labels), [0] * len(labels))

    def test_fixed_randomized_differential_and_input_preservation(self):
        rng = random.Random(20261113)
        pool = [(str(index), "α" if index % 2 else "水", "nonlex-" + str(63-index)) for index in range(64)]
        for size in (0, 1, 2, 17, 103, 414, 1030, 2048):
            labels = [rng.choice(pool) for _ in range(size)]
            before = deepcopy(labels)
            with self.subTest(size=size):
                self.assertEqual(encode_groups(labels), original_ids(labels))
                self.assertEqual(labels, before)

    def test_controller_numpy_shape_and_dtype_are_unchanged(self):
        for labels in ([], [("z",), ("a",), ("z",)], [(str(index),) for index in range(2048)]):
            with self.subTest(size=len(labels)):
                actual = np.array(encode_groups(labels))
                expected = np.array(original_ids(labels))
                self.assertEqual(actual.shape, expected.shape)
                self.assertEqual(actual.dtype, expected.dtype)
                np.testing.assert_array_equal(actual, expected)

    def test_groupkfold_exact_train_test_membership_and_no_leakage(self):
        # Unequal groups, tied group sizes, nonlexical first appearances and
        # multiple fields expose ID-order changes that can alter tied splits.
        labels = [(name, "site-" + str(index % 2))
                  for index, (name, count) in enumerate((("z", 7), ("a", 7), ("q", 5), ("b", 5), ("m", 3), ("c", 3), ("x", 2)))
                  for _ in range(count)]
        data = np.zeros((len(labels), 1))
        expected_groups = np.array(original_ids(labels))
        actual_groups = np.array(encode_groups(labels))
        for folds in (2, 3, 5):
            expected = list(GroupKFold(folds).split(data, groups=expected_groups))
            actual = list(GroupKFold(folds).split(data, groups=actual_groups))
            covered = []
            for index, ((train, test), (old_train, old_test)) in enumerate(zip(actual, expected)):
                with self.subTest(folds=folds, fold=index):
                    np.testing.assert_array_equal(train, old_train)
                    np.testing.assert_array_equal(test, old_test)
                    self.assertFalse(set(actual_groups[train]).intersection(actual_groups[test]))
                    covered.extend(test.tolist())
            self.assertEqual(sorted(covered), list(range(len(labels))))


if __name__ == "__main__":
    unittest.main()
