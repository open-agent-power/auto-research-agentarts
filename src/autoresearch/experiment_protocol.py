"""Strict experiment configuration and one-time preparation of checked P02 inputs."""
import copy
import hashlib
import json
import math
from pathlib import Path
import platform
import re

import numpy
import sklearn

from . import chemotopo_data, chemotopo_rebuild, chemotopo_prediction
from . import chemotopo_interaction, chemotopo_iteration_evidence, chemotopo_experiment_evidence
from .contracts import ResearchError, canonical, fingerprint

EXECUTOR = 'p02-interaction-ridge-v1'
POLICIES = [item[0] for item in chemotopo_rebuild.POLICIES]


def _require(condition, message):
    if not condition:
        raise ResearchError('INVALID_PROTOCOL', message)


def validate_protocol(value):
    """Normalize a finite allowlist; never repair IDs, add keys or accept code."""
    fields = {'schema_version', 'executor_id', 'goal', 'candidates', 'max_fits', 'max_requests'}
    _require(type(value) is dict and set(value) == fields, 'Exact protocol fields required.')
    _require(value['schema_version'] == 'configured-iteration-protocol-v1' and value['executor_id'] == EXECUTOR,
             'Only the fixed P02 interaction executor is supported.')
    _require(type(value['goal']) is str and 1 <= len(value['goal'].strip()) <= 2000 and len(value['goal']) <= 2000,
             'A bounded operator goal is required.')
    candidates = value['candidates']
    _require(type(candidates) is list and 1 <= len(candidates) <= 4, 'One to four candidates required.')
    ids, alphas = set(), set()
    for item in candidates:
        _require(type(item) is dict and set(item) == {'id', 'alpha'}, 'Exact candidate fields required.')
        _require(type(item['id']) is str and re.fullmatch(r'[a-z][a-z0-9_]{0,31}', item['id']) is not None,
                 'Candidate ID must be a bounded identifier.')
        alpha = item['alpha']
        _require(type(alpha) in (int, float) and math.isfinite(alpha) and 0.01 <= alpha <= 1000,
                 'Alpha must be finite and between 0.01 and 1000.')
        _require(item['id'] not in ids and alpha not in alphas, 'Candidate IDs and alphas must be unique.')
        ids.add(item['id']); alphas.add(alpha)
    _require(type(value['max_fits']) is int and 140 <= value['max_fits'] <= 140 * len(candidates)
             and value['max_fits'] % 140 == 0, 'Fit cap must be whole 140-fit candidates within the menu.')
    _require(type(value['max_requests']) is int and 2 <= value['max_requests'] <= 6, 'Request cap must be 2..6.')
    normalized = copy.deepcopy(value)
    for item in normalized['candidates']:
        item['alpha'] = float(item['alpha'])
    return normalized


def code_identity():
    modules = (chemotopo_data, chemotopo_rebuild, chemotopo_prediction, chemotopo_interaction,
               chemotopo_iteration_evidence, chemotopo_experiment_evidence)
    files = [Path(__file__), *(Path(module.__file__) for module in modules)]
    identity = {'files': {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in files},
                'versions': {'python': platform.python_version(), 'numpy': numpy.__version__,
                             'scikit_learn': sklearn.__version__}}
    return fingerprint(identity)


def _prior_iteration(directory, checked):
    if directory is None:
        return []
    # Consume a previously sealed public artifact, not private responses or model reasoning.
    from .chemotopo_iteration_report import read_iteration_artifacts
    raw = chemotopo_experiment_evidence._safe_file(Path(directory) / 'iteration.json', 1_000_000)
    view = json.loads(raw)
    _require(view.get('schema_version') == 'p02-iteration-view-v1'
             and view.get('snapshot_sha256') == fingerprint({k: v for k, v in view.items() if k != 'snapshot_sha256'}),
             'Prior publication snapshot identity differs.')
    read_iteration_artifacts(directory, view)
    prior = view['prior_evidence']
    _require(prior['r54_manifest_sha256'] == checked['baseline_manifest_sha256']
             and prior['r59_manifest_sha256'] == checked['manifest_sha256']
             and prior['r59_protocol_sha256'] == checked['protocol_sha256']
             and prior['metrics'] == checked['metrics'], 'Prior publication belongs to different inputs.')
    candidates = []
    for action in view['actions']:
        if action['action'] not in {'fit_alpha10', 'fit_alpha100'}:
            continue
        summary = action['summary']
        _require(summary['fit_count'] == 140 and summary['scientific_validation'] is False
                 and summary['model_weight_training'] is False, 'Prior candidate scope differs.')
        candidates.append({'action_id': action['id'], 'alpha': summary['alpha'],
                           'result_sha256': action['result_sha256'], 'metrics': copy.deepcopy(summary['metrics']),
                           'model_selected': action['model_selected']})
    return [{'snapshot_sha256': view['snapshot_sha256'], 'task_origin': view['task_origin'],
             'goal': view['goal'], 'status': view['status'], 'completed_candidates': candidates,
             'interpretation_notice': 'Source-bound historical numbers; model reasons are excluded. '
             'This consistency check is not independent scientific validation.'}]


def prepare_inputs(source, baseline, interaction, prior_publication=None):
    """Verify original evidence once; future execution reads this captured snapshot."""
    checked = chemotopo_iteration_evidence.inspect(source, baseline, interaction)
    rows_by_policy = {}
    for policy in POLICIES:
        rows = chemotopo_interaction._baseline_rows(checked['baseline_verified'], checked['geometry'], policy)
        previous = {(row['topography'], row['chemistry']): row for row in checked['rows_by_policy'][policy]}
        for row in rows:
            old = previous[(row['topography'], row['chemistry'])]
            _require(all(row[key] == old[key] for key in ('target', 'fold', 'chemistry_prediction', 'additive_prediction')),
                     'Prepared baseline and interaction inputs differ.')
            row['interaction_prediction'] = old['interaction_prediction']
        rows_by_policy[policy] = rows
    payload = {'schema_version': 'p02-configured-inputs-v1', 'executor_id': EXECUTOR,
               'policies': list(POLICIES), 'rows_by_policy': rows_by_policy,
               'folds_by_policy': copy.deepcopy(checked['baseline_verified']['verified_folds']),
               'prior_evidence': {'r54_manifest_sha256': checked['baseline_manifest_sha256'],
                                  'r59_manifest_sha256': checked['manifest_sha256'],
                                  'r59_protocol_sha256': checked['protocol_sha256'],
                                  'metrics': checked['metrics'], 'primary_rule': checked['primary_rule'],
                                  'known_iterations': _prior_iteration(prior_publication, checked)},
               'limits': [*('Historical R59 scope: ' + item for item in checked['limits']),
                          'Future iterations use this immutable snapshot; changes to original source directories do not update it.',
                          'New penalty selection is exploratory tuning, not the untuned R59 experiment or a final blind test.'],
               'preparation_code_sha256': code_identity()}
    validate_inputs(payload)
    return payload


def validate_inputs(payload):
    """One-time structural validation of fixed rows and complete grouped splits."""
    fields = {'schema_version', 'executor_id', 'policies', 'rows_by_policy', 'folds_by_policy',
              'prior_evidence', 'limits', 'preparation_code_sha256'}
    _require(type(payload) is dict and set(payload) == fields, 'Exact input snapshot fields required.')
    _require(payload['schema_version'] == 'p02-configured-inputs-v1' and payload['executor_id'] == EXECUTOR
             and payload['policies'] == POLICIES, 'Fixed P02 snapshot and policies required.')
    _require(set(payload['rows_by_policy']) == set(POLICIES) and set(payload['folds_by_policy']) == set(POLICIES),
             'All four policies required.')
    cohort = None
    row_fields = {'topography', 'chemistry', 'fold', 'geometry', 'target', 'chemistry_prediction',
                  'additive_prediction', 'interaction_prediction'}
    for policy in POLICIES:
        rows = payload['rows_by_policy'][policy]; folds = payload['folds_by_policy'][policy]
        _require(type(rows) is list and len(rows) == 870 and type(folds) is list and len(folds) == 35,
                 'Fixed 870 materials and 35 folds required.')
        for row in rows:
            _require(type(row) is dict and set(row) == row_fields, 'Exact numerical row required.')
            _require(type(row['topography']) is int and 2 <= row['topography'] <= 36
                     and type(row['chemistry']) is int and 0 <= row['chemistry'] <= 27
                     and type(row['fold']) is int and row['fold'] == row['topography'] - 1,
                     'Invalid material or grouped-fold identity.')
            _require(type(row['geometry']) is list and len(row['geometry']) == 10, 'Ten geometry features required.')
            numbers = [*row['geometry'], *(row[key] for key in ('target', 'chemistry_prediction', 'additive_prediction', 'interaction_prediction'))]
            _require(all(type(v) in (int, float) and math.isfinite(v) for v in numbers), 'Finite numerical inputs required.')
        keys = [(row['topography'], row['chemistry']) for row in rows]
        _require(len(set(keys)) == 870 and keys == sorted(keys), 'Unique sorted material keys required.')
        _require(cohort is None or keys == cohort, 'Policy material cohorts must match.')
        cohort = keys
        _require({row['topography'] for row in rows} == set(range(2, 37)), 'All 35 topographies required.')
        for number, fold in enumerate(folds, 1):
            test = [list(key) for key in keys if key[0] == number + 1]
            train = [list(key) for key in keys if key[0] != number + 1]
            _require(fold['fold'] == number and fold['held_out_topography'] == number + 1
                     and fold['test_keys'] == test and fold['train_keys'] == train
                     and {key[1] for key in test} <= {key[1] for key in train}, 'Grouped split or known-chemistry rule differs.')
    # Encoding here also rejects non-finite numbers hidden in metadata; no normalization after hashing.
    canonical(payload)
