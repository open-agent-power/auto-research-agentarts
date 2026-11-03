"""A separate, read-only numerical-iteration projection with native provenance.

The original publication and operator archive retain their existing identities.
No dispatch, model call, fit or semantic approval of model prose occurs here.
"""
import copy
import hashlib
import json
import math
from pathlib import Path

from .c01_research import ACTION_FIELDS
from .chemotopo_delivery import _safe
from .chemotopo_experiment_evidence import _safe_file
from .chemotopo_iteration_cloud import IterationCloudLoop, project_context
from .chemotopo_iteration_study import CANDIDATES
from .contracts import ResearchError, fingerprint


POLICIES = ('recorded_equal_batch', 'positive_equal_batch',
            'recorded_equal_section', 'positive_equal_section')


def _require(condition, message):
    if not condition:
        raise ResearchError('EVIDENCE_CHANGED', message)


def _database_identities(root):
    # Hash committed SQLite files as well as any WAL; disallow changing snapshots.
    values = {}
    for name in ('iteration-study.sqlite', 'iteration-cloud.sqlite'):
        for suffix in ('', '-wal'):
            path = root / (name + suffix)
            if suffix and not path.exists():
                values[name + suffix] = None
            else:
                values[name + suffix] = hashlib.sha256(_safe_file(path, 12000000)).hexdigest()
    return values


def _bind_native(loop, state, spec, rows, context_builder=project_context, scope_fields=('prior_evidence',)):
    """Check captured observations, explicit native calls and persisted actions."""
    actions = {a['id']: a for a in state['actions']}
    _require(len(actions) == len(state['actions']), 'Duplicate action identity.')
    bound, trace = set(), []
    _require(len(rows) <= spec['max_requests'], 'Native request budget exceeded.')
    for ordinal, row in enumerate(rows, 1):
        _require(row['ordinal'] == ordinal and row['status'] in {'sending', 'received', 'applied', 'invalid'},
                 'Invalid native request sequence or status.')
        observation = json.loads(row['observation_json'])
        body = json.loads(row['request_json'])
        _require(fingerprint(body) == row['request_sha256'], 'Native request identity changed.')
        _require(fingerprint({k: v for k, v in observation.items() if k != 'observation_sha256'}) == observation['observation_sha256'],
                 'Captured observation identity changed.')
        _require(observation['configuration_sha256'] == state['configuration_sha256']
                 and all(observation[field] == state[field] for field in scope_fields), 'Captured study scope changed.')
        previous = observation['actions']
        _require(previous == state['actions'][:len(previous)], 'Captured feedback is not a current action prefix.')
        context = json.loads(body['messages'][1]['content'])
        expected = context_builder(observation, spec['max_requests'] - ordinal + 1, context.get('previous_rejections', []))
        _require(context == expected, 'Actual native input differs from captured numerical feedback.')
        response = None
        if row['response_json'] is not None:
            response = json.loads(row['response_json'])
            _require(fingerprint(response) == row['response_sha256'], 'Native response identity changed.')
        if row['status'] == 'applied':
            action = actions.get(row['action_id'])
            _require(action is not None and action['id'] not in bound and response is not None,
                     'Applied native response lacks a unique action.')
            loop._validate_response(response, spec)
            decision = loop._parse_decision(response, observation, row['request_id'], body)
            _require(json.loads(row['decision_json']) == decision == {k: action[k] for k in ACTION_FIELDS},
                     'Explicit native call and committed action differ.')
            _require(action['ordinal'] == len(previous) + 1, 'Action does not follow its observed feedback.')
            bound.add(action['id'])
        trace.append({'ordinal': ordinal, 'status': row['status'], 'action_id': row['action_id'],
                      'request_sha256': row['request_sha256'], 'response_sha256': row['response_sha256'],
                      'feedback_action_ids': [a['id'] for a in previous]})
    return bound, trace


def _comparisons(actions, candidate_actions=CANDIDATES):
    comparisons = []
    for action in actions:
        if action['action'] not in candidate_actions:
            continue
        summary = action['summary']
        item = {'action_id': action['id'], 'alpha': summary['alpha'], 'policies': [],
                'improved_vs_alpha1': [], 'worse_vs_alpha1': [],
                'improved_vs_additive': [], 'improved_vs_chemistry': []}
        for policy in POLICIES:
            metric = summary['metrics'][policy]
            mae = metric['pooled_mae']
            row = {'policy': policy, 'mae': mae, 'spearman': metric['pooled_spearman_midrank'],
                   'alpha1_mae': metric['r59_alpha1_mae'], 'additive_mae': metric['r54_additive_mae'],
                   'chemistry_mae': metric['r54_chemistry_mae']}
            for label in ('alpha1', 'additive', 'chemistry'):
                row['delta_vs_' + label] = mae - row[label + '_mae']
                if not math.isclose(mae, row[label + '_mae'], rel_tol=1e-12, abs_tol=1e-12):
                    if mae < row[label + '_mae']:
                        item['improved_vs_' + label].append(policy)
                    elif label == 'alpha1':
                        item['worse_vs_alpha1'].append(policy)
            item['policies'].append(row)
        comparisons.append(item)
    return comparisons


def capture_iteration(workspace, publication):
    """Return (public view, private checked numerical evidence) in one load.

    Private paths/configuration are solely for an allowlisted report exporter.
    Native responses, account data and reasoning traces are never returned.
    """
    _require(publication.get('snapshot_sha256') == fingerprint({k: v for k, v in publication.items() if k != 'snapshot_sha256'}),
             'Baseline publication identity changed.')
    prediction = publication.get('prediction')
    _require(isinstance(prediction, dict), 'A checked prediction baseline is required.')
    root = Path(workspace).absolute()
    before = _database_identities(root)
    loop = IterationCloudLoop(root)
    with loop._connect() as con:
        project, spec, state = loop._state(con)
        rows = [dict(r) for r in con.execute('SELECT * FROM calls ORDER BY ordinal')]
    _require(state['prior_evidence']['r54_manifest_sha256'] == prediction['manifest_sha256'],
             'Iteration baseline does not match the displayed original publication.')
    bound, trace = _bind_native(loop, state, spec, rows)
    with loop.study._connect() as con:
        meta = con.execute('SELECT * FROM meta').fetchone()
        config = json.loads(meta['config'])
    _require(fingerprint(config) == meta['sha256'] == state['configuration_sha256'],
             'Study configuration changed while capturing evidence.')
    # _state already checked complete artifacts and numerical arithmetic. Capture
    # the exact same verified bytes without repeating workbook reconstruction.
    candidate_artifacts = {}
    for action in state['actions']:
        if action['action'] not in CANDIDATES:
            continue
        payload = _safe_file(loop.study._path(action['request_id']) / 'result.json', 10000000)
        _require(action['result']['artifact'] == {'bytes': len(payload), 'sha256': hashlib.sha256(payload).hexdigest()},
                 'Candidate changed after verification.')
        candidate_artifacts[action['id']] = json.loads(payload)
    _require(_database_identities(root) == before, 'Study changed while capturing the public snapshot.')
    actions = [_safe({**{k: a[k] for k in ('id', 'ordinal', 'action', 'reason', 'parameters',
                                         'source_citation_ids', 'evidence_action_ids', 'result_sha256')},
                      'summary': copy.deepcopy(a['result'].get('summary', a['result'])),
                      'model_selected': a['id'] in bound}) for a in state['actions']]
    completed = [a for a in actions if a['action'] in CANDIDATES]
    view = _safe({'schema_version': 'p02-iteration-view-v1',
        'baseline_publication_sha256': publication['snapshot_sha256'],
        'study_configuration_sha256': state['configuration_sha256'],
        'controller_configuration_sha256': fingerprint(spec), 'status': state['status'],
        'controller_status': project['status'], 'goal': state['goal'],
        'task_origin': 'operator_assigned_research_goal', 'citations': state['citations'],
        'prior_evidence': state['prior_evidence'], 'actions': actions,
        'reservations': state['reservations'], 'native_trace': trace,
        'execution': {'model': spec['model_identity']['model'], 'requests_reserved': len(rows),
                      'max_requests': spec['max_requests'], 'applied_calls': len(bound),
                      'invalid_calls': sum(r['status'] == 'invalid' for r in rows),
                      'unknown_requests': sum(r['status'] in {'sending', 'received'} for r in rows),
                      'fits_reserved': state['budget']['fits_reserved'],
                      'completed_fits': sum(a['summary']['fit_count'] for a in completed),
                      'max_fits': state['budget']['max_fits'], 'completed_candidates': len(completed),
                      'fit_count_basis': 'Verified complete candidate artifacts; not a separate runtime profiler.'},
        'comparisons': _comparisons(actions), 'endpoint_gate': state['endpoint_gate'],
        'interpretation_notice': '模型理由是原文记录，未经科学审定；请按每种处理规则核对指标。任务由操作者提出，候选选择以原生调用绑定为准。',
        'limits': ['已查看来源与探索折上的固定候选比较，不是独立盲测或未来批次效果。',
                   '只评价字面红通道代理；ALP身份未确认，不支持临床或因果推断。',
                   'Ridge拟合不属于LLM权重训练；原有R54/R59操作者实验不计入本轮候选拟合。'],
        'scientific_validation': False, 'llm_weight_training': False})
    view['snapshot_sha256'] = fingerprint(view)
    return view, {'config': config, 'candidate_artifacts': candidate_artifacts, 'source_db_sha256': before}


def load_iteration_view(workspace, publication):
    return capture_iteration(workspace, publication)[0]
