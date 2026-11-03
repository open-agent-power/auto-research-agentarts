import copy
import json
from pathlib import Path
import unittest

from autoresearch import experiment_protocol as module
from autoresearch.contracts import ResearchError


def snapshot():
    rows = [{'topography': t, 'chemistry': c, 'fold': t - 1, 'geometry': [float(t)] * 10,
             'target': 1., 'chemistry_prediction': .9, 'additive_prediction': 1.1,
             'interaction_prediction': 1.2}
            for t in range(2, 37) for c in range(25 if t < 32 else 24)]
    folds = [{'fold': t - 1, 'held_out_topography': t,
              'train_keys': [[r['topography'], r['chemistry']] for r in rows if r['topography'] != t],
              'test_keys': [[r['topography'], r['chemistry']] for r in rows if r['topography'] == t]}
             for t in range(2, 37)]
    return {'schema_version': 'p02-configured-inputs-v1', 'executor_id': module.EXECUTOR,
            'policies': list(module.POLICIES), 'rows_by_policy': {p: copy.deepcopy(rows) for p in module.POLICIES},
            'folds_by_policy': {p: copy.deepcopy(folds) for p in module.POLICIES},
            'prior_evidence': {}, 'limits': ['synthetic only'], 'preparation_code_sha256': 'a' * 64}


class ProtocolTests(unittest.TestCase):
    def protocol(self):
        return json.loads((Path(__file__).parents[1] / 'examples/p02-iteration-protocol.json').read_text(encoding='utf-8'))

    def test_finite_protocol_and_execution_escape_rejected(self):
        original = self.protocol()
        self.assertEqual(module.validate_protocol(original), original)
        changes = [dict(executor_id='python'), dict(command='echo arbitrary'), dict(max_requests=True),
                   dict(max_fits=141), dict(max_fits=420), dict(max_requests=7), dict(goal=' ')]
        for change in changes:
            with self.subTest(change=change), self.assertRaises(ResearchError):
                module.validate_protocol({**original, **change})
        for alpha in (True, float('nan'), float('inf'), 0, 1001, '3'):
            value = copy.deepcopy(original); value['candidates'][0]['alpha'] = alpha
            with self.subTest(alpha=alpha), self.assertRaises(ResearchError):
                module.validate_protocol(value)
        for candidate in ({'id': '../file', 'alpha': 3}, {'id': 'alpha3', 'alpha': 30},
                          {'id': 'alpha30', 'alpha': 3}, {'id': 'alpha3', 'alpha': 3, 'code': 'x'}):
            value = copy.deepcopy(original); value['candidates'][0] = candidate
            with self.subTest(candidate=candidate), self.assertRaises(ResearchError):
                module.validate_protocol(value)

    def test_snapshot_requires_same_cohort_finite_values_and_whole_groups(self):
        original = snapshot(); module.validate_inputs(original)
        policy = module.POLICIES[0]
        corruptions = (
            lambda v: v['rows_by_policy'][policy][0]['geometry'].__setitem__(0, float('nan')),
            lambda v: v['rows_by_policy'][policy].__setitem__(1, copy.deepcopy(v['rows_by_policy'][policy][0])),
            lambda v: v['folds_by_policy'][policy][0]['train_keys'].append([2, 0]),
            lambda v: v['rows_by_policy'][policy][0].__setitem__('fold', 2),
        )
        for corrupt in corruptions:
            changed = copy.deepcopy(original); corrupt(changed)
            with self.assertRaises(ResearchError):
                module.validate_inputs(changed)


if __name__ == '__main__':
    unittest.main()
