"""Public projection of a frozen configurable study, without reopening original data."""
import copy
import hashlib
import json
from pathlib import Path

from .chemotopo_delivery import _safe
from .chemotopo_experiment_evidence import _safe_file
from .chemotopo_iteration_view import _require, _bind_native, _comparisons
from .configured_iteration import ConfiguredCloudLoop, project_context
from .contracts import fingerprint


def _database_identities(root):
    values = {}
    for name in ('configured-study.sqlite', 'configured-cloud.sqlite'):
        for suffix in ('', '-wal'):
            path = root / (name + suffix)
            values[name + suffix] = hashlib.sha256(_safe_file(path, 12_000_000)).hexdigest() if path.exists() else None
    _require(values['configured-study.sqlite'] is not None, 'Prepared study required.')
    return values


def capture_configured(workspace, publication, *, native_interface='legacy'):
    """Return the common public view and private captured numeric artifacts once."""
    _require(native_interface in ('legacy','compact-v1'),'Unknown native interface.')
    loop_class=ConfiguredCloudLoop;context_builder=project_context
    if native_interface=='compact-v1':
        from .compact_iteration import CompactCloudLoop, project_context as compact_context
        loop_class=CompactCloudLoop;context_builder=compact_context
    _require(publication.get('snapshot_sha256') == fingerprint({k: v for k, v in publication.items() if k != 'snapshot_sha256'}),
             'Baseline publication identity changed.')
    prediction = publication.get('prediction')
    _require(type(prediction) is dict, 'A sealed prediction baseline is required.')
    root = Path(workspace).absolute(); before = _database_identities(root)
    loop = loop_class(root); spec = None; rows = []; bound = set(); trace = []
    if loop.db.exists():
        with loop._connect() as con:
            project, spec, state = loop._state(con)
            rows = [dict(row) for row in con.execute('SELECT * FROM calls ORDER BY ordinal')]
        bound, trace = _bind_native(loop, state, spec, rows, context_builder=context_builder)
        with loop.study._connect() as con:
            meta = con.execute('SELECT * FROM meta').fetchone()
            config = json.loads(meta['config'])
        _require(fingerprint(config) == meta['sha256'] == state['configuration_sha256'], 'Study changed while capturing.')
    else:
        with loop.study._connect() as con:
            config, state, _ = loop.study._state(con)
        project = {'status': 'not_started'}
    _require(state['prior_evidence']['r54_manifest_sha256'] == prediction['manifest_sha256'],
             'Configured study belongs to a different baseline.')
    inputs_bytes = _safe_file(root / 'inputs.json', 10_000_000)
    _require(len(inputs_bytes) == config['inputs_bytes'] and hashlib.sha256(inputs_bytes).hexdigest() == config['inputs_sha256'],
             'Frozen inputs changed after verification.')
    inputs = json.loads(inputs_bytes); artifacts = {}
    for action in state['actions']:
        if action['action'] != 'run_candidate':
            continue
        raw = _safe_file(loop.study._artifact_path(action['request_id']) / 'result.json', 10_000_000)
        _require(action['result']['artifact'] == {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()},
                 'Candidate changed after numerical verification.')
        artifacts[action['id']] = json.loads(raw)
    _require(_database_identities(root) == before, 'Study changed while capturing public evidence.')
    actions = [_safe({**{k: a[k] for k in ('id', 'ordinal', 'action', 'reason', 'parameters',
                                         'source_citation_ids', 'evidence_action_ids', 'result_sha256')},
                      'summary': copy.deepcopy(a['result'].get('summary', a['result'])),
                      'model_selected': a['id'] in bound}) for a in state['actions']]
    completed = [a for a in actions if a['action'] == 'run_candidate']
    view = _safe({'schema_version': 'p02-iteration-view-v1',
        'baseline_publication_sha256': publication['snapshot_sha256'],
        'study_configuration_sha256': state['configuration_sha256'],
        'controller_configuration_sha256': fingerprint(spec) if spec else None,
        'status': state['status'], 'controller_status': project['status'],
        'goal': state['protocol']['goal'], 'protocol': copy.deepcopy(state['protocol']),
        'inputs_sha256': config['inputs_sha256'], 'task_origin': 'operator_assigned_research_goal',
        'citations': state['citations'], 'prior_evidence': state['prior_evidence'],
        'actions': actions, 'reservations': state['reservations'], 'native_trace': trace,
        'execution': {'model': spec['model_identity']['model'] if spec else None,
                      'requests_reserved': len(rows), 'max_requests': state['protocol']['max_requests'],
                      'applied_calls': len(bound), 'invalid_calls': sum(r['status'] == 'invalid' for r in rows),
                      'unknown_requests': sum(r['status'] in {'sending', 'received'} for r in rows),
                      'fits_reserved': state['budget']['fits_reserved'],
                      'completed_fits': sum(a['summary']['fit_count'] for a in completed),
                      'max_fits': state['budget']['max_fits'], 'completed_candidates': len(completed),
                      'fit_count_basis': 'Verified complete candidate artifacts; not a separate runtime profiler.'},
        'comparisons': _comparisons(actions, candidate_actions={'run_candidate'}),
        'endpoint_gate': {**state['endpoint_gate'], 'numerical_fit_eligible': state['endpoint_gate']['numerical_proxy_fit_eligible']},
        'interpretation_notice': '模型显式理由未经科学审定。候选和预算以固定协议与行动账本为准；耗尽拟合预算不等于耗尽模型请求。历史研究只作为已保存输入，不计为本轮行动或新拟合。',
        'limits': ['固定协议由操作者定义；模型选择候选，未自主生成研究目标或新算法。',
                   '只评价字面红通道代理；ALP未知，没有独立生物、临床或因果验证。',
                   '反复使用已查看的870材料组合与35折，是探索性比较，不能称为最终盲测。',
                   '继承R61公开数值摘要；没有把未经审定的模型理由转换为研究事实。',
                   'Ridge拟合不是LLM权重训练；历史实验与本轮分别计数。'],
        'scientific_validation': False, 'llm_weight_training': False})
    if native_interface=='compact-v1':
        view['execution']['native_interface']='compact-v1'
        view['execution']['native_metadata_binding']={
            'origin':'host_bound_from_saved_observation',
            'fields':['observation_sha256','source_citation_ids','evidence_action_ids'],
            'model_choice':'candidate or pause/stop, plus reason',
            'notice':'执行元数据由宿主绑定；model_selected不代表模型主动引用来源或已阅读证据。'}
    view['snapshot_sha256'] = fingerprint(view)
    return view, {'config': config, 'inputs': inputs, 'inputs_bytes': inputs_bytes,
                  'candidate_artifacts': artifacts, 'source_db_sha256': before}


def load_configured_view(workspace, publication, *, native_interface='legacy'):
    return capture_configured(workspace, publication,native_interface=native_interface)[0]
