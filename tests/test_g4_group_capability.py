"""Capability-language engineering examples, not a future worktree candidate."""
import ast
import copy
import json
from pathlib import Path
import random
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import g4_group_capability as gate


BASELINE_EXAMPLE = '''def encode_groups(labels):
    unique = list(dict.fromkeys(labels))
    return [unique.index(label) for label in labels]
'''
DICTIONARY_EXAMPLE = '''def encode_groups(labels):
    lookup = {}
    output = []
    for label in labels:
        if label not in lookup:
            lookup[label] = len(lookup)
        output.append(lookup[label])
    return output
'''
COMPREHENSION_EXAMPLE = '''def encode_groups(labels):
    unique = list(dict.fromkeys(labels))
    lookup = {label: index for index, label in enumerate(unique)}
    return [lookup[label] for label in labels]
'''
SETDEFAULT_EXAMPLE = '''def encode_groups(labels):
    lookup = dict()
    result = list()
    for label in labels:
        result.append(lookup.setdefault(label, len(lookup)))
    return result
'''


def helper(body):
    return "def encode_groups(labels):\n" + "\n".join("    " + line for line in body.splitlines()) + "\n"


class GroupCapabilityTests(unittest.TestCase):
    def denied(self, source, labels=(), code=None, limits=None):
        with self.assertRaises(gate.CapabilityError) as caught:
            gate.execute_group_program(source, labels, limits=limits)
        if code is not None:
            self.assertEqual(caught.exception.code, code)
        return caught.exception

    def test_known_ordered_duplicate_and_unicode_cases(self):
        labels = [["z"], ["a"], ["z"], ["汉", "x"], ["a"], ["汉", "x"]]
        original = copy.deepcopy(labels)
        for source in (BASELINE_EXAMPLE, DICTIONARY_EXAMPLE, COMPREHENSION_EXAMPLE, SETDEFAULT_EXAMPLE):
            receipt = gate.execute_group_program(source, labels)
            self.assertEqual(receipt["group_ids"], [0, 1, 0, 2, 1, 2])
            self.assertEqual(receipt["status"], "completed")
            self.assertEqual((receipt["fit_calls"], receipt["product_model_calls"]), (0, 0))
            self.assertTrue(all(receipt["usage"][k] <= v for k, v in receipt["limits"].items()))
        self.assertEqual(labels, original)

    def test_empty_singleton_and_tuple_input(self):
        for source in (BASELINE_EXAMPLE, DICTIONARY_EXAMPLE, COMPREHENSION_EXAMPLE):
            self.assertEqual(gate.execute_group_program(source, [])['group_ids'], [])
            self.assertEqual(gate.execute_group_program(source, (("x",),))['group_ids'], [0])
            self.assertEqual(gate.execute_group_program(source, [("x",)] * 15)['group_ids'], [0] * 15)

    def test_multiple_equivalent_sources_against_first_occurrence_reference(self):
        rng = random.Random(117)
        for count in (0, 1, 17, 64):
            labels = [[str(rng.randrange(11)), str(rng.randrange(3))] for _ in range(count)]
            first_positions = [labels.index(label) for label in labels]
            ordered = sorted(set(first_positions))
            expected = [ordered.index(position) for position in first_positions]
            for source in (BASELINE_EXAMPLE, DICTIONARY_EXAMPLE, COMPREHENSION_EXAMPLE, SETDEFAULT_EXAMPLE):
                self.assertEqual(gate.execute_group_program(source, labels)['group_ids'], expected)

    def test_receipts_deterministic_and_json_serializable(self):
        labels = [["b"], ["a"], ["b"]]
        a = gate.execute_group_program(BASELINE_EXAMPLE, labels)
        b = gate.execute_group_program(BASELINE_EXAMPLE.encode(), tuple(map(tuple, labels)))
        self.assertEqual(a, b)
        self.assertEqual(json.loads(json.dumps(a)), a)
        self.assertNotEqual(a['source_sha256'], gate.execute_group_program(BASELINE_EXAMPLE + '\n', labels)['source_sha256'])

    def test_validation_runs_no_interpreter_statements(self):
        with patch.object(gate._Interpreter, 'statements', side_effect=AssertionError('No validation execution')):
            validated = gate.validate_group_program(BASELINE_EXAMPLE)
        self.assertFalse(validated['executed'])
        self.assertEqual(validated['function'], 'encode_groups')
        self.assertEqual(len(validated['source_sha256']), 64)

    def test_source_module_and_signature_are_closed(self):
        sources = [BASELINE_EXAMPLE + 'x = 1\n', 'x = 1\n' + BASELINE_EXAMPLE,
                   BASELINE_EXAMPLE + BASELINE_EXAMPLE, BASELINE_EXAMPLE.replace('encode_groups', 'other'),
                   BASELINE_EXAMPLE.replace('(labels)', '(labels, other)'),
                   BASELINE_EXAMPLE.replace('(labels)', '(labels=[])'),
                   BASELINE_EXAMPLE.replace('(labels)', '(labels: list)'),
                   BASELINE_EXAMPLE.replace('(labels):', '(labels) -> list:'),
                   '@list\n' + BASELINE_EXAMPLE]
        for source in sources:
            with self.subTest(source=source[:60]):
                with self.assertRaises(gate.CapabilityError):
                    gate.validate_group_program(source)

    def test_nested_function_is_statically_rejected(self):
        source = helper('def hidden():\n    return []\nreturn []')
        with self.assertRaises(gate.CapabilityError) as caught:
            gate.validate_group_program(source)
        self.assertEqual(caught.exception.code, 'FORBIDDEN_SYNTAX')

    def test_import_io_reflection_and_arbitrary_calls_rejected_before_execution(self):
        bodies = ['import os\nreturn []', 'return open(labels)', 'return eval(labels)',
                  'return exec(labels)', 'return compile(labels)', 'return getattr(labels)',
                  'return __import__(labels)', 'return labels.__class__', 'return labels.pop()',
                  'return labels.index.__call__(labels)', 'return encode_groups(labels)',
                  'return (lambda x: x)(labels)', 'global labels\nreturn []',
                  'with labels:\n    return []', 'try:\n    return []\nexcept:\n    return []']
        for body in bodies:
            with self.subTest(body=body):
                with patch.object(gate._Interpreter, 'statements', side_effect=AssertionError('Unvalidated execution')):
                    self.denied(helper(body))

    def test_no_unbounded_sequence_arithmetic_loops_or_expansion(self):
        for body in ['while True:\n    labels = labels\nreturn []', 'return [0] * 2048',
                     'return [0 ** 2048]', 'return list(range(2048))', 'return list(*labels)',
                     'return dict(**labels)', 'return [x for x in labels for y in labels]',
                     'a = {}\nb = {**a}\nreturn []']:
            self.denied(helper(body))

    def test_nested_loop_depth_capped_statically(self):
        self.denied(helper('for a in labels:\n    for b in labels:\n        for c in labels:\n            len(labels)\nreturn []'), code='LOOP_DEPTH')

    def test_rebinding_input_builtin_and_dunder_names_rejected(self):
        for body in ['labels = []\nreturn labels', 'list = []\nreturn list',
                     '__value = []\nreturn __value', 'for labels in labels:\n    len(labels)\nreturn []']:
            self.denied(helper(body))

    def test_exact_primitive_input_types(self):
        class FakeList(list):
            pass
        class FakeString(str):
            pass
        for value in ['x', {'x': 1}, FakeList(), [[1]], [[True]], [[None]], [[FakeString('x')]], [[]], [[[]]]]:
            with self.subTest(value=repr(value)):
                self.denied(BASELINE_EXAMPLE, value)

    def test_input_shape_and_codepoint_limits(self):
        self.denied(BASELINE_EXAMPLE, [['a']] * 2049, code='INPUT_ROWS')
        self.denied(BASELINE_EXAMPLE, [['a'] * 5], code='INPUT_LABEL')
        self.denied(BASELINE_EXAMPLE, [['汉' * 129]], code='INPUT_LABEL')
        out = gate.execute_group_program(DICTIONARY_EXAMPLE, [['汉' * 128] * 4] * 2048)
        self.assertEqual(out['group_ids'], [0] * 2048)

    def test_json_surrogates_are_rejected_before_interpretation(self):
        labels = json.loads('[["\\ud800"]]')
        with patch.object(gate._Interpreter, 'statements', side_effect=AssertionError('No invalid-label execution')):
            self.denied(BASELINE_EXAMPLE, labels, code='INPUT_LABEL_ENCODING')

    def test_caller_inputs_cannot_be_mutated(self):
        labels = [['a'], ['b']]
        self.denied(helper('labels.append(labels)\nreturn []'), labels, code='INTRINSIC')
        self.denied(helper('labels[0] = 0\nreturn []'), labels, code='WRITE_TYPE')
        self.assertEqual(labels, [['a'], ['b']])

    def test_iteration_mutation_rejected(self):
        self.denied(helper('a = list(labels)\nfor item in a:\n    a.append(item)\nreturn []'), [['a']], code='ITERATION_MUTATION')
        self.denied(helper('a = dict.fromkeys(labels)\nfor item in a:\n    a[item] = 0\nreturn []'), [['a']], code='ITERATION_MUTATION')

    def test_enumerate_cannot_be_stored_for_later_mutation(self):
        self.denied(helper('a = list(labels)\ne = enumerate(a)\na.append(labels[0])\nreturn []'), [['a']], code='ENUMERATE_POSITION')

    def test_subscripts_do_not_expose_labels_or_containers_as_callable_objects(self):
        self.denied(helper('return labels[0].index(labels)'), [['a']], code='FORBIDDEN_ATTRIBUTE')
        self.denied(helper('return labels[True]'), [['a']], code='SUBSCRIPT_TYPE')
        self.denied(helper('a = []\na.append(a)\nreturn a'), [], code='LIST_CELL_TYPE')

    def test_non_label_dictionary_keys_and_nested_values_rejected(self):
        self.denied(helper('a = {0: 1}\nreturn []'), [], code='DICT_KEY_TYPE')
        self.denied(helper('a = {}\na[labels[0]] = []\nreturn []'), [['a']], code='DICT_VALUE_TYPE')

    def test_wrong_output_is_rejected_without_semantic_claim(self):
        for body in ['return labels', 'return dict()', 'return [None]', 'return [-1]',
                     'return [2048]', 'return []', 'a = []']:
            self.denied(helper(body), [['a']])
        self.denied(helper('return [True]'), [['a']])
        # Correct shape but wrong grouping is left to the independent evaluator.
        self.assertEqual(gate.execute_group_program(helper('return [0, 0]'), [['a'], ['b']])['group_ids'], [0, 0])

    def test_empty_input_truth_matches_sequence_semantics(self):
        source = helper('if labels:\n    return [0]\nelse:\n    return []')
        self.assertEqual(gate.execute_group_program(source, [])['group_ids'], [])
        self.assertEqual(gate.execute_group_program(source, [['a']])['group_ids'], [0])

    def test_operation_exhaustion_has_bounded_usage_receipt(self):
        error = self.denied(BASELINE_EXAMPLE, [['a'], ['b']], limits=gate.Limits(steps=1), code='BUDGET_EXHAUSTED')
        self.assertIsNotNone(error.usage)
        self.assertLessEqual(error.usage['steps'], 1)

    def test_input_cell_charge_is_before_normalized_copy_and_has_usage(self):
        error = self.denied(BASELINE_EXAMPLE, [['a']], limits=gate.Limits(allocated_cells=1), code='BUDGET_EXHAUSTED')
        self.assertEqual(error.usage['allocated_cells'], 0)
        self.assertEqual(error.usage['steps'], 0)

    def test_allocation_budget_accounts_for_comprehension_environment_copies(self):
        error = self.denied(BASELINE_EXAMPLE, [['a'], ['b']] * 8,
                            limits=gate.Limits(allocated_cells=40), code='BUDGET_EXHAUSTED')
        self.assertLessEqual(error.usage['allocated_cells'], 40)

    def test_hashing_and_list_scan_comparisons_charge_scalar_work(self):
        error = self.denied(BASELINE_EXAMPLE, [['x' * 128]], limits=gate.Limits(scalar_work=128), code='BUDGET_EXHAUSTED')
        self.assertLessEqual(error.usage['scalar_work'], 128)
        labels = [[str(i)] for i in range(12)]
        baseline = gate.execute_group_program(BASELINE_EXAMPLE, labels)
        dictionary = gate.execute_group_program(DICTIONARY_EXAMPLE, labels)
        self.assertGreater(baseline['usage']['scalar_work'], dictionary['usage']['scalar_work'])

    def test_host_cannot_raise_or_mistype_ceiling(self):
        for limit in [gate.Limits(steps=gate.MAX_STEPS + 1), gate.Limits(steps=True),
                      gate.Limits(allocated_cells=0), gate.Limits(scalar_work=-1), {}]:
            self.denied(BASELINE_EXAMPLE, [], limits=limit, code='INVALID_LIMIT')

    def test_source_size_ast_depth_nodes_and_name_bounds(self):
        self.denied(BASELINE_EXAMPLE + '#' * gate.MAX_SOURCE_BYTES, code='SOURCE_LIMIT')
        self.denied(b'\xff', code='INVALID_SOURCE')
        self.denied(helper('x = 0\n' * 200 + 'return []'), code='AST_LIMIT')
        self.denied(helper('return ' + 'not ' * 40 + 'labels'), code='AST_LIMIT')
        self.denied(helper('x' * 65 + ' = []\nreturn []'), code='FORBIDDEN_NAME')

    def test_intrinsic_receiver_arity_and_lookup_failures(self):
        self.denied(helper('a = []\nreturn [a.index(0)]'), [['a']], code='INDEX_MISSING')
        self.denied(helper('a = {}\nreturn [a[labels[0]]]'), [['a']], code='KEY_MISSING')
        self.denied(helper('a = {}\na.append(0)\nreturn []'), [], code='INTRINSIC')
        self.denied(helper('return len()'), [], code='ARITY')

    def test_fixed_host_has_no_direct_python_execution_calls(self):
        module = ast.parse(Path(gate.__file__).read_text())
        prohibited = {'eval', 'exec', 'compile', '__import__', 'import_module'}
        calls = [n for n in ast.walk(module) if type(n) is ast.Call]
        for call in calls:
            name = call.func.id if type(call.func) is ast.Name else call.func.attr if type(call.func) is ast.Attribute else None
            self.assertNotIn(name, prohibited)


if __name__ == '__main__':
    unittest.main()
