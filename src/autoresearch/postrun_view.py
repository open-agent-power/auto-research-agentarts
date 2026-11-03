"""Read-only postrun evidence: proposals, actual calls, and conditional memory."""
import copy
import hashlib
import json
import re
from pathlib import Path

from .chemotopo_delivery import _safe
from .chemotopo_experiment_evidence import _safe_file
from .chemotopo_iteration_view import _require, _bind_native
from .contracts import ResearchError, canonical, fingerprint
from .postrun_research import PostrunCloudLoop, project_context


def _identities(paths):
    result = {}
    for path in paths:
        for suffix in ('', '-wal'):
            p = Path(str(path) + suffix)
            result[str(p)] = hashlib.sha256(_safe_file(p, 12_000_000)).hexdigest() if p.exists() else None
    return result


def _assessment(annotation, state, source):
    proposals = {a['id'] for a in state['actions'] if a['action'] in {'propose_next','revise_proposal'}}
    if annotation is None:
        return {'status': 'unreviewed', 'origin': 'no_assessment', 'notes': [], 'proposal_action_id': None}
    fields = {'schema_version', 'source_snapshot_sha256', 'proposal_action_id', 'status', 'origin', 'notes'}
    _require(type(annotation) is dict and set(annotation) == fields
             and annotation['schema_version'] == 'postrun-assessment-v1'
             and annotation['source_snapshot_sha256'] == source['snapshot_sha256']
             and annotation['proposal_action_id'] in proposals
             and annotation['status'] in {'unreviewed', 'needs_revision'}
             and annotation['origin'] == 'operator_assistant_inspection', 'Assessment must bind this source and actual proposal.')
    notes = annotation['notes']
    _require(type(notes) is list and 1 <= len(notes) <= 5
             and all(type(note) is str and 1 <= len(note) <= 500 for note in notes), 'Bounded inspection notes required.')
    _require(_safe(annotation) == annotation, 'Assessment contains private text.')
    return copy.deepcopy(annotation)


def capture_postrun(workspace, iteration, annotation=None):
    _require(iteration.get('schema_version') == 'p02-iteration-view-v1'
             and iteration.get('snapshot_sha256') == fingerprint({k: v for k, v in iteration.items() if k != 'snapshot_sha256'}),
             'An intact sealed iteration is required.')
    loop = PostrunCloudLoop(workspace)
    with loop.study._connect() as con:
        config = json.loads(con.execute('SELECT * FROM meta').fetchone()['config'])
    paths = [loop.db, loop.study.db, Path(config['memory_workspace']) / 'memory.sqlite']
    before = _identities(paths)
    with loop._connect() as con:
        project, spec, state = loop._state(con)
        calls = [dict(row) for row in con.execute('SELECT * FROM calls ORDER BY ordinal')]
    source = loop.study._source(config)
    _require(source['view'] == iteration, 'Postrun source differs from displayed iteration.')
    bound, trace = _bind_native(loop, state, spec, calls, context_builder=project_context)
    actions = [_safe({**{k: a[k] for k in ('id', 'ordinal', 'action', 'parameters', 'reason', 'result_sha256',
                                         'source_citation_ids', 'evidence_action_ids')},
                      'result': copy.deepcopy(a['result']), 'model_selected': a['id'] in bound}) for a in state['actions']]
    unapplied = []; recalled_in_later_request = set()
    recalls = {a['id']: a for a in state['actions'] if a['action'] == 'recall_observations'}
    for row in calls:
        body = json.loads(row['request_json']); context = json.loads(body['messages'][1]['content'])
        for item in context['actions']:
            if item['id'] in recalls:
                _require(item['result'] == recalls[item['id']]['result'], 'Recalled values differ in later native request.')
                recalled_in_later_request.update(e['record']['id'] for e in item['result']['entries'])
        if row['status'] != 'applied':
            entry = {'ordinal': row['ordinal'], 'error_code': row['error_code'], 'tool_name': None, 'reason_excerpt': None}
            response = json.loads(row['response_json']) if row['response_json'] else {}
            tools = response.get('message', {}).get('tool_calls', [])
            if type(tools) is list and len(tools) == 1 and type(tools[0]) is dict:
                function = tools[0].get('function', {})
                entry['tool_name'] = str(function.get('name', ''))[:80]
                reason = function.get('arguments', {}).get('reason') if type(function.get('arguments')) is dict else None
                entry['reason_excerpt'] = reason[:700] if type(reason) is str else None
            unapplied.append(_safe(entry))
    assessment = _assessment(annotation, state, source)
    view = _safe({'schema_version': 'p02-postrun-view-v1', 'iteration_snapshot_sha256': iteration['snapshot_sha256'],
        'source_snapshot_sha256': source['snapshot_sha256'], 'study_configuration_sha256': state['configuration_sha256'],
        'controller_configuration_sha256': fingerprint(spec), 'goal': state['goal'],
        'study_status': state['status'], 'controller_status': project['status'], 'controller_reason': project['reason'],
        'actions': actions, 'native_trace': trace, 'unapplied_requests': unapplied,
        'memory_context': copy.deepcopy(state['memory_context']), 'assessment': assessment,
        'execution': {'model': spec['model_identity']['model'], 'requests_reserved': len(calls), 'max_requests': spec['max_requests'],
                      'applied_calls': len(bound), 'invalid_calls': sum(c['status'] == 'invalid' for c in calls),
                      'unknown_requests': sum(c['status'] in {'sending', 'received'} for c in calls),
                      'explicit_remembers': sum(a['action'] == 'remember_observations' and a['id'] in bound for a in actions),
                      'explicit_recalls': sum(a['action'] == 'recall_observations' and a['id'] in bound for a in actions),
                      'recalled_entries_in_later_request': len(recalled_in_later_request),
                      'native_terminal_control_applied': any(a['action'] in {'pause', 'stop'} and a['id'] in bound for a in actions),
                      'new_fits': 0},
        'limits': ['Model proposals and active memory are not scientific approval or authority to execute new experiments.',
                   'Invalid requests are not applied actions; request-limit completion does not prove an autonomous stop.',
                   'Memory readback and subsequent prompt inclusion do not establish improved research judgement.',
                   'Inspection notes are supplied by the development assistant, not the research model or a scientific reviewer.'],
        'scientific_validation': False, 'llm_weight_training': False})
    _require(_identities(paths) == before, 'Postrun or memory changed during capture.')
    view['snapshot_sha256'] = fingerprint(view)
    return view


def allowed_iteration_snapshots(iteration):
    """Only the displayed snapshot and its explicitly sealed one-level history."""
    def valid(value):return type(value) is str and re.fullmatch(r'[0-9a-f]{64}',value) is not None
    _require(type(iteration) is dict and valid(iteration.get('snapshot_sha256')),'Valid current iteration snapshot required.')
    prior=iteration.get('prior_evidence',{})
    _require(type(prior) is dict,'Iteration history must be an object.')
    known=prior.get('known_iterations',[])
    _require(type(known) is list,'Iteration history must be a list.')
    snapshots={iteration['snapshot_sha256']}
    for record in known:
        _require(type(record) is dict and valid(record.get('snapshot_sha256')),'Invalid sealed historical iteration identity.')
        snapshots.add(record['snapshot_sha256'])
    return snapshots


def read_postrun_artifacts(directory, iteration):
    root = Path(directory)
    manifest = json.loads(_safe_file(root / 'manifest.json', 100_000))
    raw = _safe_file(root / 'postrun.json', 3_000_000); view = json.loads(raw)
    _require(view.get('schema_version') == 'p02-postrun-view-v1' and view.get('scientific_validation') is False
             and view.get('snapshot_sha256') == fingerprint({k: v for k, v in view.items() if k != 'snapshot_sha256'})
             and view.get('iteration_snapshot_sha256') in allowed_iteration_snapshots(iteration) and _safe(view) == view,
             'Postrun view identity or iteration binding changed.')
    _require(manifest == {'schema_version': 'p02-postrun-artifacts-v1', 'snapshot_sha256': view['snapshot_sha256'],
                          'iteration_snapshot_sha256': view['iteration_snapshot_sha256'],
                          'files': {'postrun.json': {'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw)}}},
             'Postrun manifest differs from exact view bytes.')
    return {'postrun.json': raw}


def export_postrun(workspace, iteration, output, annotation=None):
    target = Path(output).absolute()
    for path in (target, *target.parents):
        _require(not path.is_symlink() and not getattr(path, 'is_junction', lambda: False)(), 'Redirected output forbidden.')
    study = PostrunCloudLoop(workspace).study
    with study._connect() as con:
        config = json.loads(con.execute('SELECT * FROM meta').fetchone()['config'])
    for path in [study.root, Path(config['memory_workspace']), *(Path(v) for v in config['private_sources'].values())]:
        _require(not (target == path or target.is_relative_to(path) or path.is_relative_to(target)), 'Output overlaps source or memory.')
    if target.exists():
        raise ResearchError('ALREADY_EXISTS', 'Use a fresh output directory.')
    view = capture_postrun(workspace, iteration, annotation)
    raw = (canonical(view) + '\n').encode('utf-8')
    _require(len(raw) <= 3_000_000, 'Postrun view exceeds bound.')
    manifest = {'schema_version': 'p02-postrun-artifacts-v1', 'snapshot_sha256': view['snapshot_sha256'],
                'iteration_snapshot_sha256': iteration['snapshot_sha256'],
                'files': {'postrun.json': {'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw)}}}
    target.mkdir(parents=True, exist_ok=False)
    (target / 'postrun.json').write_bytes(raw)
    (target / 'manifest.json').write_text(canonical(manifest) + '\n', encoding='utf-8')
    return manifest
