"""Continue a bounded numerical study from sealed inputs and published feedback."""
import copy
import hashlib
import json
import os
from pathlib import Path

from . import configured_iteration as execution, experiment_protocol
from .chemotopo_experiment_evidence import _safe_file
from .chemotopo_iteration_report import read_iteration_artifacts
from .contracts import ResearchError, canonical, fingerprint


def _require(condition, message):
    if not condition:
        raise ResearchError('EVIDENCE_CHANGED', message)


def extend_inputs(inputs, state, publication):
    """Add verified historical summaries; never edit numerical rows or folds."""
    _require(publication.get('schema_version') == 'p02-iteration-view-v1'
             and publication.get('snapshot_sha256') == fingerprint({k: v for k, v in publication.items() if k != 'snapshot_sha256'}),
             'An intact iteration publication is required.')
    _require(publication.get('inputs_sha256') == state['inputs_sha256']
             and publication.get('study_configuration_sha256') == state['configuration_sha256']
             and publication.get('status') == state['status'] and state['status'] in {'paused', 'stopped'}
             and publication.get('protocol') == state['protocol']
             and publication.get('prior_evidence') == inputs['prior_evidence'], 'Published iteration differs from prepared study.')
    source_actions = {a['id']: a for a in state['actions']}
    _require(len(source_actions) == len(publication['actions']), 'Published actions differ from source study.')
    completed = []
    for action in publication['actions']:
        actual = source_actions.get(action['id'])
        _require(actual is not None and action['action'] == actual['action']
                 and action['parameters'] == actual['parameters'] and action['result_sha256'] == actual['result_sha256'],
                 'Published action identity differs.')
        if actual['action'] == 'run_candidate':
            summary = actual['result']['summary']
            _require(action['summary'] == summary, 'Published numerical feedback differs.')
            completed.append({'action_id': action['id'], 'alpha': summary['alpha'],
                              'result_sha256': action['result_sha256'], 'metrics': copy.deepcopy(summary['metrics']),
                              'model_selected': action['model_selected']})
    result = copy.deepcopy(inputs)
    history = result['prior_evidence'].setdefault('known_iterations', [])
    _require(len(history) < 8 and not any(item['snapshot_sha256'] == publication['snapshot_sha256'] for item in history),
             'Historical iteration is already included or history is full.')
    history.append({'snapshot_sha256': publication['snapshot_sha256'], 'task_origin': publication['task_origin'],
                    'goal': publication['goal'], 'status': publication['status'], 'completed_candidates': completed,
                    'interpretation_notice': 'Historical numerical feedback copied from the sealed source iteration. '
                    'No new fits; original model reasons are not numerical evidence or scientific approval.'})
    _require(result['rows_by_policy'] == inputs['rows_by_policy']
             and result['folds_by_policy'] == inputs['folds_by_policy'], 'Continuation cannot alter numerical inputs.')
    return result


def create_continuation(workspace, source_study, iteration_directory, protocol):
    protocol = experiment_protocol.validate_protocol(protocol)
    study = execution.ConfiguredStudy(workspace); study._guard(); target = study.root.resolve()
    sources = [Path(source_study).absolute().resolve(), Path(iteration_directory).absolute().resolve()]
    for source in sources:
        if target == source or target.is_relative_to(source) or source.is_relative_to(target):
            raise ResearchError('UNSAFE_PATH', 'Continuation must use a separate new workspace.')
    if target.exists() and any(target.iterdir()):
        raise ResearchError('ALREADY_EXISTS', 'Use a fresh continuation workspace; do not reset a study.')
    previous = execution.ConfiguredStudy(sources[0])
    with previous._connect() as connection:
        source_config, state, _ = previous._state(connection)
    inputs = previous._inputs(source_config)
    publication = json.loads(_safe_file(sources[1] / 'iteration.json', 3_000_000))
    read_iteration_artifacts(sources[1], publication)
    extended = extend_inputs(inputs, state, publication)
    tested = {1.} | {item['alpha'] for history in extended['prior_evidence']['known_iterations']
                     for item in history['completed_candidates']}
    if any(candidate['alpha'] in tested for candidate in protocol['candidates']):
        raise ResearchError('DUPLICATE_EXPERIMENT', 'Protocol repeats a tested setting under the same numerical inputs.')
    experiment_protocol.validate_inputs(extended); execution._validate_plan(extended)
    raw = canonical(extended).encode('utf-8')
    _require(0 < len(raw) <= execution.MAX_INPUT_BYTES, 'Prepared continuation exceeds its input bound.')
    config = {'schema': 'configured-iteration-study-v1', 'protocol': protocol,
              'inputs_sha256': hashlib.sha256(raw).hexdigest(), 'inputs_bytes': len(raw),
              'code_sha256': execution.code_identity(),
              'private_sources': {'source_study': str(sources[0]), 'iteration_directory': str(sources[1])},
              'preparation': {'method': 'sealed_continuation',
                              'base_inputs_sha256': state['inputs_sha256'],
                              'source_study_configuration_sha256': state['configuration_sha256'],
                              'iteration_snapshot_sha256': publication['snapshot_sha256'],
                              'preparation_code_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}}
    study.root.mkdir(parents=True, exist_ok=True)
    with (study.root / 'inputs.json').open('xb') as stream:
        stream.write(raw); stream.flush(); os.fsync(stream.fileno())
    with study.db.open('xb'):
        pass
    with study._connect(True) as connection:
        connection.executescript('CREATE TABLE meta(config TEXT NOT NULL,sha256 TEXT NOT NULL,status TEXT NOT NULL);'
            'CREATE TABLE actions(ordinal INTEGER PRIMARY KEY,id TEXT UNIQUE,request_id TEXT UNIQUE,request_sha256 TEXT,record TEXT);'
            'CREATE TABLE reservations(request_id TEXT PRIMARY KEY,request_sha256 TEXT NOT NULL,request_json TEXT NOT NULL,candidate_id TEXT UNIQUE NOT NULL,status TEXT NOT NULL);')
        connection.execute('INSERT INTO meta VALUES(?,?,?)', (canonical(config), fingerprint(config), 'active'))
    return study.observe()
