"""Trusted numerical observations for postrun planning and conditional memory."""
import copy
import hashlib
import json
from pathlib import Path

from . import research_memory
from .chemotopo_delivery import _safe
from .chemotopo_experiment_evidence import _safe_file
from .chemotopo_publication import read_artifacts
from .configured_iteration_view import capture_configured
from .contracts import ResearchError, canonical, fingerprint, identifier
from .research_memory import observation_id, validate_scope


def code_identity():
    return hashlib.sha256(Path(__file__).read_bytes() + Path(research_memory.__file__).read_bytes()).hexdigest()


def _require(condition, message):
    if not condition:
        raise ResearchError('EVIDENCE_CHANGED', message)


def validate_source(value):
    fields = {'schema_version', 'view', 'scope', 'facts', 'snapshot_sha256', 'preparation_notice'}
    _require(type(value) is dict and set(value) == fields and value['schema_version'] == 'postrun-source-v1',
             'Exact postrun source projection required.')
    _require(value['snapshot_sha256'] == fingerprint({k: v for k, v in value.items() if k != 'snapshot_sha256'}),
             'Postrun source snapshot changed.')
    view = value['view']; validate_scope(value['scope'])
    _require(view.get('snapshot_sha256') == fingerprint({k: v for k, v in view.items() if k != 'snapshot_sha256'}),
             'Source publication changed.')
    _require(view.get('status') in {'stopped', 'paused'} and 'protocol' in view
             and view.get('scientific_validation') is False, 'A terminal configured study is required.')
    expected = []
    for action in view['actions']:
        if action['action'] == 'run_candidate':
            comparison = next((c for c in view['comparisons'] if c['action_id'] == action['id']), None)
            _require(comparison is not None, 'Current candidate lacks checked comparison.')
            summary = action['summary']
            expected.append({'action_id': action['id'], 'candidate_id': action['parameters']['candidate_id'],
                             'alpha': summary['alpha'], 'metrics': summary['metrics'],
                             'comparisons': comparison, 'result_sha256': action['result_sha256']})
    _require(value['facts'] == expected, 'Facts must be derived from actual current candidates.')
    scope = value['scope']; prior = view['prior_evidence']
    _require(scope['inputs_sha256'] == view['inputs_sha256']
             and scope['protocol'] == 'configured-iteration-v1:' + fingerprint(view['protocol'])
             and scope['source_manifest_sha256'] == fingerprint({k: prior[k] for k in ('r54_manifest_sha256', 'r59_manifest_sha256')}),
             'Memory conditions differ from the captured study.')
    _require(_safe(value) == value, 'Postrun projection contains private path or credential text.')


def prepare_source(source_study, baseline_publication_directory):
    """Capture numerical artifacts once; do not open author workbooks or fit."""
    root = Path(baseline_publication_directory)
    publication = json.loads(_safe_file(root / 'research.json', 3_000_000))
    read_artifacts(root, publication)
    view, private = capture_configured(source_study, publication)
    prior = view['prior_evidence']
    scope = validate_scope({'source_manifest_sha256': fingerprint({k: prior[k] for k in ('r54_manifest_sha256', 'r59_manifest_sha256')}),
                            'inputs_sha256': view['inputs_sha256'],
                            'analysis_code_sha256': private['config']['code_sha256'],
                            'protocol': 'configured-iteration-v1:' + fingerprint(view['protocol'])})
    facts = []
    for action in view['actions']:
        if action['action'] != 'run_candidate':
            continue
        summary = action['summary']
        facts.append({'action_id': action['id'], 'candidate_id': action['parameters']['candidate_id'],
                      'alpha': summary['alpha'], 'metrics': copy.deepcopy(summary['metrics']),
                      'comparisons': copy.deepcopy(next(c for c in view['comparisons'] if c['action_id'] == action['id'])),
                      'result_sha256': action['result_sha256']})
    value = {'schema_version': 'postrun-source-v1', 'view': view, 'scope': scope, 'facts': facts,
             'preparation_notice': 'Original candidate artifacts and native bindings were checked at capture; '
             'this frozen numerical context is not independent scientific validation. Historical and current fits stay separate.'}
    value['snapshot_sha256'] = fingerprint(value)
    validate_source(value)
    return value


def derive_entries(source, proposal_action):
    """Derive host-owned numbers; preserve the separate, unreviewed model proposal."""
    validate_source(source)
    _require(proposal_action.get('action') == 'propose_next', 'Only an explicit next-step proposal is eligible.')
    identifier(proposal_action['id'])
    params = proposal_action['parameters']
    selected = params.get('source_action_ids')
    _require(type(selected) is list and selected and set(selected) <= {v['action_id'] for v in source['facts']},
             'Proposal must cite actual source candidates.')
    scope = source['scope']; view = source['view']; entries = []

    def add(kind, action_id, payload, references):
        record = {'schema_version': 'conditional-research-memory-v1', 'kind': kind, 'scope': copy.deepcopy(scope),
                  'review_status': 'derived_not_scientifically_reviewed', 'numerical_recomputation': kind != 'agent_decision',
                  'payload': payload,
                  'provenance': {'action_id': action_id, 'source_record_sha256': view['snapshot_sha256'],
                                 'reproduction_sha256': source['snapshot_sha256'],
                                 'origin_observation_sha256': view['study_configuration_sha256'],
                                 'source_citation_ids': ['p02-current-iteration'],
                                 'references': [{'citation_id': 'p02-current-iteration', 'source_sha256': view['snapshot_sha256']}],
                                 'evidence_action_ids': references}}
        record['id'] = observation_id(record); entries.append(record)

    for fact in source['facts']:
        add('fit_observation', fact['action_id'],
            {'candidate_id': fact['candidate_id'], 'alpha': fact['alpha'],
             'metrics': copy.deepcopy(fact['metrics']), 'comparisons': copy.deepcopy(fact['comparisons']),
             'promotion': 'not_evaluated_no_independent_holdout',
             'interpretation': 'Checked raw-red proxy arithmetic under these exact inputs and protocol; ALP unknown.'},
            [fact['action_id']])
    add('agent_decision', proposal_action['id'],
        {'action': 'propose_next', 'proposal': copy.deepcopy(params), 'reason': proposal_action['reason'],
         'interpretation': 'Unreviewed model research proposal. Not a scientific fact, an execution plan approval or budget extension.'},
        list(selected))
    return {'scope': copy.deepcopy(scope), 'entries': entries,
            'validation': {'source_snapshot_sha256': source['snapshot_sha256'],
                           'candidate_artifacts_checked_at_capture': len(source['facts']),
                           'new_fits': 0, 'scientific_validation': False}}
