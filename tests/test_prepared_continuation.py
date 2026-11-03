import copy
import unittest

from autoresearch.prepared_continuation import extend_inputs
from autoresearch.contracts import ResearchError, fingerprint


class ContinuationTests(unittest.TestCase):
    def test_history_does_not_rewrite_numeric_inputs_or_accept_another_study(self):
        inputs = {'prior_evidence': {'known_iterations': []}, 'rows_by_policy': {'fixture': [1, 2]},
                  'folds_by_policy': {'fixture': [3, 4]}}
        action = {'id': 'a1', 'action': 'run_candidate', 'parameters': {'candidate_id': 'a3'},
                  'result_sha256': 'a' * 64, 'result': {'summary': {'alpha': 3., 'metrics': {'fixture': {'pooled_mae': 2.}}}}}
        state = {'inputs_sha256': 'b' * 64, 'configuration_sha256': 'c' * 64, 'status': 'stopped',
                 'protocol': {'fixture': True}, 'actions': [action]}
        view = {'schema_version': 'p02-iteration-view-v1', 'inputs_sha256': state['inputs_sha256'],
                'study_configuration_sha256': state['configuration_sha256'], 'status': 'stopped',
                'protocol': state['protocol'], 'prior_evidence': copy.deepcopy(inputs['prior_evidence']),
                'actions': [{k: v for k, v in action.items() if k != 'result'} | {'summary': action['result']['summary'], 'model_selected': True}],
                'goal': 'fixture', 'task_origin': 'operator_assigned_research_goal'}
        view['snapshot_sha256'] = fingerprint(view); original = copy.deepcopy(inputs)
        result = extend_inputs(inputs, state, view)
        self.assertEqual(inputs, original)
        self.assertEqual(result['rows_by_policy'], original['rows_by_policy'])
        self.assertEqual(result['folds_by_policy'], original['folds_by_policy'])
        self.assertEqual(result['prior_evidence']['known_iterations'][0]['completed_candidates'][0]['alpha'], 3.)
        for key, value in [('study_configuration_sha256', 'd' * 64), ('inputs_sha256', 'e' * 64)]:
            changed = copy.deepcopy(view); changed[key] = value
            changed['snapshot_sha256'] = fingerprint({k: v for k, v in changed.items() if k != 'snapshot_sha256'})
            with self.assertRaises(ResearchError): extend_inputs(inputs, state, changed)
        with self.assertRaises(ResearchError): extend_inputs(result, state, view)


if __name__ == '__main__': unittest.main()
