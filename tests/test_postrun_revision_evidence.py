import copy
import unittest

from autoresearch import postrun_revision_evidence as module
from autoresearch.postrun_evidence import derive_entries
from autoresearch.contracts import ResearchError, fingerprint
from test_postrun_evidence import source as original_source, proposal as original_proposal


def source():
    original = original_source(); policies = module.POLICY_LABELS
    metrics = {p: {'pooled_mae': 2., 'pooled_spearman_midrank': .5} for p in policies}
    original['facts'][0]['metrics'] = copy.deepcopy(metrics)
    original['view']['actions'][0]['summary']['metrics'] = copy.deepcopy(metrics)
    original['view']['prior_evidence']['metrics'] = {
        p: {m: {'pooled_mae': 1., 'pooled_spearman_midrank': .6}
            for m in ('interaction', 'chemistry', 'additive')} for p in policies}
    original['view']['prior_evidence']['known_iterations'] = [{'completed_candidates': [
        {'action_id': 'historical-alpha100', 'alpha': 100., 'metrics': copy.deepcopy(metrics)}]}]
    original['view']['snapshot_sha256'] = fingerprint({k: v for k, v in original['view'].items() if k != 'snapshot_sha256'})
    original['snapshot_sha256'] = fingerprint({k: v for k, v in original.items() if k != 'snapshot_sha256'})
    seed = {**original_proposal(), 'model_selected': True}
    entries = derive_entries(original, seed)['entries']
    postrun = {'schema_version': 'p02-postrun-view-v1', 'scientific_validation': False,
               'source_snapshot_sha256': original['snapshot_sha256'],
               'iteration_snapshot_sha256': original['view']['snapshot_sha256'],
               'actions': [seed], 'memory_context': {'entries': [{'record': r, 'inclusion_status': 'active'} for r in entries]}}
    postrun['snapshot_sha256'] = fingerprint(postrun)
    value = {'schema_version': 'postrun-revision-source-v1', 'source': original, 'postrun': postrun,
             'scope': original['scope'], 'seed_proposal': seed,
             'superseded_memory_id': next(r['id'] for r in entries if r['kind'] == 'agent_decision'),
             'inventory': module.inventory(original), 'policy_labels': module.POLICY_LABELS}
    value['snapshot_sha256'] = fingerprint(value)
    return value


def proposal():
    return {'choice': 'change_hypothesis', 'candidate_alpha': None, 'experiment_ids': ['candidate-1'],
            'supersedes_proposal_id': 'proposal-1', 'hypothesis': 'Do not repeat alpha100.',
            'next_check': 'Read measurement definition', 'success_criterion': 'Mapping is supported',
            'failure_criterion': 'Mapping remains unresolved'}


class RevisionEvidenceTests(unittest.TestCase):
    def test_typed_duplicate_guard_does_not_parse_prose_or_guess_new_candidates(self):
        payload = source(); module.validate_source(payload); params = proposal()
        module.validate_proposal(params, payload)  # A negative textual mention is not a duplicate plan.
        for alpha in (1, 3, 100):
            with self.assertRaises(ResearchError) as error:
                module.validate_proposal({**params, 'choice': 'continue_regularization', 'candidate_alpha': alpha}, payload)
            self.assertEqual(error.exception.code, 'DUPLICATE_EXPERIMENT')
        module.validate_proposal({**params, 'choice': 'continue_regularization', 'candidate_alpha': 30}, payload)
        for change in ({'candidate_alpha': True, 'choice': 'continue_regularization'}, {'experiment_ids': ['unknown']}):
            with self.assertRaises(ResearchError): module.validate_proposal({**params, **change}, payload)

    def test_source_binding_and_exact_host_observations_survive_revision(self):
        payload = source(); action = {'id': 'revision-1', 'action': 'revise_proposal',
            'parameters': proposal(), 'reason': 'Reconsider the rejected direction.',
            'observation_sha256': 'f' * 64, 'evidence_action_ids': []}
        actual = module.derive_entries(payload, action)
        old = derive_entries(payload['source'], payload['seed_proposal'])
        self.assertEqual([e for e in actual['entries'] if e['kind'] == 'fit_observation'],
                         [e for e in old['entries'] if e['kind'] == 'fit_observation'])
        revised = next(e for e in actual['entries'] if e['kind'] == 'agent_decision')
        self.assertNotEqual(revised['id'], payload['superseded_memory_id'])
        self.assertFalse(revised['numerical_recomputation'])
        for key in ('superseded_memory_id', 'inventory'):
            changed = copy.deepcopy(payload); changed[key] = 'a' * 64 if key.endswith('_id') else []
            changed['snapshot_sha256'] = fingerprint({k: v for k, v in changed.items() if k != 'snapshot_sha256'})
            with self.assertRaises(ResearchError): module.validate_source(changed)


if __name__ == '__main__': unittest.main()
