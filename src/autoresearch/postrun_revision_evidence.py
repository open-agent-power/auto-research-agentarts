"""Sealed inputs for correcting a postrun proposal, without new fits or source reads."""
import copy
import json
import math
from pathlib import Path

from .chemotopo_delivery import _safe
from .chemotopo_experiment_evidence import _safe_file
from .contracts import ResearchError, fingerprint, identifier
from .postrun_evidence import validate_source as validate_original, derive_entries as original_entries
from .postrun_view import read_postrun_artifacts
from .research_memory import observation_id


POLICY_LABELS = {
    'positive_equal_batch': '仅纳入 Count > 0 的记录；批次等权。positive 不表示正向结果。',
    'positive_equal_section': '仅纳入 Count > 0 的记录；分区等权。',
    'recorded_equal_batch': '保留原始零值记录；批次等权。',
    'recorded_equal_section': '保留原始零值记录；分区等权。',
}
PROPOSAL_FIELDS = {'choice', 'candidate_alpha', 'experiment_ids', 'supersedes_proposal_id',
                   'hypothesis', 'next_check', 'success_criterion', 'failure_criterion'}
TEXT_FIELDS = ('hypothesis', 'next_check', 'success_criterion', 'failure_criterion')


def _require(condition, message, code='EVIDENCE_CHANGED'):
    if not condition:
        raise ResearchError(code, message)


def inventory(source):
    """Actual tested settings, not a list inferred by parsing model prose."""
    prior = source['view']['prior_evidence']; baselines = prior['metrics']
    _require(set(baselines) == set(POLICY_LABELS), 'Four fixed processing rules are required.')

    def row(experiment_id, alpha, origin, metrics):
        _require(type(alpha) in (int, float) and math.isfinite(alpha), 'Finite tested alpha required.')
        _require(set(metrics) == set(POLICY_LABELS), 'Candidate rules differ from baseline rules.')
        values = {}
        for policy, metric in metrics.items():
            values[policy] = {'pooled_mae': metric['pooled_mae'],
                              'pooled_spearman_midrank': metric['pooled_spearman_midrank'],
                              'chemistry_mae': baselines[policy]['chemistry']['pooled_mae'],
                              'additive_mae': baselines[policy]['additive']['pooled_mae']}
            _require(all(type(v) in (int, float) and math.isfinite(v) for v in values[policy].values()),
                     'Finite comparison values required.')
        return {'experiment_id': experiment_id, 'alpha': float(alpha), 'origin': origin, 'metrics': values}

    result = [row('r59-interaction-alpha1', 1., 'operator_baseline_label_not_native_action',
                  {p: v['interaction'] for p, v in baselines.items()})]
    for historical in prior.get('known_iterations', []):
        for candidate in historical['completed_candidates']:
            result.append(row(candidate['action_id'], candidate['alpha'], 'historical_iteration', candidate['metrics']))
    for fact in source['facts']:
        result.append(row(fact['action_id'], fact['alpha'], 'source_iteration', fact['metrics']))
    _require(len(result) <= 12 and len({x['experiment_id'] for x in result}) == len(result),
             'A bounded, unambiguous experiment inventory is required.')
    return result


def _seed(postrun):
    proposals = [a for a in postrun['actions'] if a['action'] == 'propose_next']
    _require(len(proposals) == 1 and proposals[0]['model_selected'] is True,
             'One actual prior model proposal is required.')
    proposal = proposals[0]
    records = [e['record'] for e in postrun['memory_context']['entries']
               if e['record']['kind'] == 'agent_decision'
               and e['record']['provenance']['action_id'] == proposal['id']]
    _require(len(records) == 1 and records[0]['payload']['proposal'] == proposal['parameters']
             and records[0]['id'] == observation_id(records[0]), 'The exact superseded proposal memory is required.')
    return proposal, records[0]['id']


def validate_source(value):
    fields = {'schema_version', 'source', 'postrun', 'scope', 'seed_proposal', 'superseded_memory_id',
              'inventory', 'policy_labels', 'snapshot_sha256'}
    _require(type(value) is dict and set(value) == fields
             and value['schema_version'] == 'postrun-revision-source-v1', 'Exact revision source required.')
    _require(value['snapshot_sha256'] == fingerprint({k: v for k, v in value.items() if k != 'snapshot_sha256'}),
             'Revision source changed.')
    source = value['source']; validate_original(source); postrun = value['postrun']
    _require(postrun.get('schema_version') == 'p02-postrun-view-v1'
             and postrun.get('snapshot_sha256') == fingerprint({k: v for k, v in postrun.items() if k != 'snapshot_sha256'})
             and postrun.get('source_snapshot_sha256') == source['snapshot_sha256']
             and postrun.get('iteration_snapshot_sha256') == source['view']['snapshot_sha256']
             and postrun.get('scientific_validation') is False, 'Prior postrun must bind the same actual source.')
    proposal, memory_id = _seed(postrun)
    _require(value['seed_proposal'] == proposal and value['superseded_memory_id'] == memory_id
             and value['scope'] == source['scope'] and value['inventory'] == inventory(source)
             and value['policy_labels'] == POLICY_LABELS, 'Derived revision context differs from frozen evidence.')
    _require(_safe(value) == value, 'Revision context contains private data.')


def prepare_source(source_file, postrun_directory):
    source = json.loads(_safe_file(Path(source_file), 5_000_000)); validate_original(source)
    postrun = json.loads(read_postrun_artifacts(postrun_directory, source['view'])['postrun.json'])
    proposal, memory_id = _seed(postrun)
    value = {'schema_version': 'postrun-revision-source-v1', 'source': source, 'postrun': postrun,
             'scope': copy.deepcopy(source['scope']), 'seed_proposal': copy.deepcopy(proposal),
             'superseded_memory_id': memory_id, 'inventory': inventory(source), 'policy_labels': POLICY_LABELS}
    value['snapshot_sha256'] = fingerprint(value); validate_source(value)
    return value


def validate_proposal(params, source):
    _require(type(params) is dict and set(params) == PROPOSAL_FIELDS
             and params['choice'] in {'continue_regularization', 'change_hypothesis', 'stop_direction'},
             'Exact structured proposal required.', 'INVALID_REQUEST')
    _require(all(type(params[k]) is str and 1 <= len(params[k].strip()) <= 1000 for k in TEXT_FIELDS),
             'Bounded hypothesis and criteria required.', 'INVALID_REQUEST')
    identifier(params['supersedes_proposal_id'])
    chosen = params['experiment_ids']; available = {r['experiment_id'] for r in source['inventory']}
    _require(type(chosen) is list and 1 <= len(chosen) <= 5 and all(type(v) is str for v in chosen)
             and len(chosen) == len(set(chosen)) and set(chosen) <= available,
             'Use exact inventory experiment IDs, separate from current action IDs.', 'INVALID_EVIDENCE')
    alpha = params['candidate_alpha']
    if params['choice'] == 'continue_regularization':
        _require(type(alpha) in (int, float) and math.isfinite(alpha) and .01 <= alpha <= 1000,
                 'A finite candidate_alpha in .01..1000 is required.', 'INVALID_REQUEST')
        _require(alpha not in {r['alpha'] for r in source['inventory']},
                 'This setting already ran under these inputs; use its recorded results.', 'DUPLICATE_EXPERIMENT')
    else:
        _require(alpha is None, 'Only a regularization proposal can set candidate_alpha.', 'INVALID_REQUEST')


def derive_entries(source, revision_action):
    validate_source(source)
    _require(revision_action.get('action') == 'revise_proposal', 'An explicit applied revision is required.')
    identifier(revision_action['id']); params = revision_action['parameters']; validate_proposal(params, source)
    # Reuse the exact host observations: same scope, numerical payload and IDs.
    original = original_entries(source['source'], source['seed_proposal'])
    entries = [e for e in original['entries'] if e['kind'] != 'agent_decision']
    record = {'schema_version': 'conditional-research-memory-v1', 'kind': 'agent_decision',
              'scope': copy.deepcopy(source['scope']), 'review_status': 'derived_not_scientifically_reviewed',
              'numerical_recomputation': False,
              'payload': {'action': 'revise_proposal', 'proposal': copy.deepcopy(params),
                          'reason': revision_action['reason'],
                          'interpretation': 'Unreviewed revised proposal. A nonduplicate typed setting is not scientific approval, execution authority, or a proven improvement.'},
              'provenance': {'action_id': revision_action['id'], 'source_record_sha256': source['snapshot_sha256'],
                             'reproduction_sha256': source['source']['snapshot_sha256'],
                             'origin_observation_sha256': revision_action['observation_sha256'],
                             'source_citation_ids': ['p02-revision-source'],
                             'references': [{'citation_id': 'p02-revision-source', 'source_sha256': source['snapshot_sha256']}],
                             'evidence_action_ids': copy.deepcopy(revision_action['evidence_action_ids']),
                             'source_experiment_ids': copy.deepcopy(params['experiment_ids'])}}
    record['id'] = observation_id(record); entries.append(record)
    return {'scope': copy.deepcopy(source['scope']), 'entries': entries,
            'validation': {'source_snapshot_sha256': source['snapshot_sha256'],
                           'numerical_observations_preserved': len(entries) - 1, 'new_fits': 0,
                           'scientific_validation': False}}
