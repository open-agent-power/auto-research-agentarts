import copy
import tempfile
import unittest

from autoresearch import postrun_evidence as module
from autoresearch.contracts import ResearchError, fingerprint
from autoresearch.research_memory import ResearchMemory


def source():
    metrics = {'synthetic_policy': {'pooled_mae': 2., 'r54_chemistry_mae': 1.}}
    comparison = {'action_id': 'candidate-1', 'alpha': 3., 'policies': []}
    view = {'actions': [{'id': 'candidate-1', 'action': 'run_candidate', 'parameters': {'candidate_id': 'alpha3'},
                         'summary': {'alpha': 3., 'metrics': metrics}, 'result_sha256': 'c' * 64}],
            'comparisons': [comparison], 'prior_evidence': {'r54_manifest_sha256': 'a' * 64, 'r59_manifest_sha256': 'b' * 64},
            'protocol': {'candidate': 'synthetic'}, 'inputs_sha256': 'd' * 64, 'scientific_validation': False,
            'status': 'stopped', 'study_configuration_sha256': 'e' * 64}
    view['snapshot_sha256'] = fingerprint(view)
    scope = {'source_manifest_sha256': fingerprint(view['prior_evidence']), 'inputs_sha256': view['inputs_sha256'],
             'analysis_code_sha256': 'f' * 64, 'protocol': 'configured-iteration-v1:' + fingerprint(view['protocol'])}
    value = {'schema_version': 'postrun-source-v1', 'view': view, 'scope': scope,
             'facts': [{'action_id': 'candidate-1', 'candidate_id': 'alpha3', 'alpha': 3., 'metrics': metrics,
                        'comparisons': comparison, 'result_sha256': 'c' * 64}], 'preparation_notice': 'synthetic only'}
    value['snapshot_sha256'] = fingerprint(value)
    return value


def proposal():
    return {'id': 'proposal-1', 'action': 'propose_next', 'reason': 'Unverified claim: MAE is zero.',
            'parameters': {'choice': 'change_hypothesis', 'source_action_ids': ['candidate-1'],
                           'hypothesis': 'Model prose', 'next_check': 'Test', 'success_criterion': 'Better', 'failure_criterion': 'Worse'}}


class PostrunEvidenceTests(unittest.TestCase):
    def test_host_numbers_stay_separate_from_model_claim_and_scope(self):
        payload = source(); derived = module.derive_entries(payload, proposal())
        with tempfile.TemporaryDirectory() as temp:
            memory = ResearchMemory(temp); memory._import_derived(derived)
            entries = memory.recall(payload['scope'])['entries']
            fact = next(e['record'] for e in entries if e['record']['kind'] == 'fit_observation')
            claim = next(e['record'] for e in entries if e['record']['kind'] == 'agent_decision')
            self.assertEqual(fact['payload']['metrics']['synthetic_policy']['pooled_mae'], 2.)
            self.assertIn('zero', claim['payload']['reason']); self.assertFalse(claim['numerical_recomputation'])
            other = {**payload['scope'], 'protocol': 'another protocol'}
            self.assertEqual(memory.recall(other)['entries'], [])
            self.assertEqual(memory._import_derived(derived)['inserted'], 0)

    def test_facts_cannot_drift_from_source_or_cite_another_action(self):
        payload = source(); payload['facts'][0]['alpha'] = 30.
        payload['snapshot_sha256'] = fingerprint({k: v for k, v in payload.items() if k != 'snapshot_sha256'})
        with self.assertRaises(ResearchError):
            module.derive_entries(payload, proposal())
        change = proposal(); change['parameters']['source_action_ids'] = ['unknown']
        with self.assertRaises(ResearchError):
            module.derive_entries(source(), change)


if __name__ == '__main__':
    unittest.main()
