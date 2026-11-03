"""Sealed, read-only external handoff with actual native selection provenance."""
import copy
import hashlib
import json
from pathlib import Path

from .chemotopo_delivery import _safe
from .chemotopo_experiment_evidence import _safe_file
from .chemotopo_iteration_view import _bind_native, _require
from .contracts import ResearchError, canonical, fingerprint
from .diagnostic_view import _native_entries
from .evidence_handoff import EvidenceHandoffCloudLoop, project_context
from .postrun_view import _identities


LIMITS = {'handoff.json': 1_000_000, 'handoff.md': 300_000}
NOTICE = ('Observation/source/latest-action IDs are host-bound execution metadata; '
          'fact IDs and task ID are native model selections. Task templates are host-curated; '
          'model reasons remain unreviewed and external work has not been executed.')


def _diagnostic(diagnostic):
    _require(type(diagnostic) is dict and diagnostic.get('schema_version') == 'p02-diagnostic-view-v1'
             and diagnostic.get('scientific_validation') is False
             and diagnostic.get('snapshot_sha256') == fingerprint(
                 {k: v for k, v in diagnostic.items() if k != 'snapshot_sha256'}),
             'An intact sealed diagnostic is required.')


def _public_text(value):
    # Scientific JSON pointers and indexed HDF dataset coordinates in checked
    # catalog facts must remain exact. Only model text/arguments are subject to
    # the local-path check, not replaced or silently repaired.
    _require(_safe(value) == value, 'Original model text contains local paths; publication would alter it.')


def _selection(actions, status):
    selected = [a for a in actions if a['action'] == 'record_next_step']
    _require(len(selected) <= 1, 'More than one external task was recorded.')
    if not selected:
        return None, None, [], None, False
    action = selected[0]; result = action['result']
    _require(action['model_selected'] and result['external_task_executed'] is False
             and result['scientific_validation'] is False
             and result['model_reason'] == action['reason']
             and result['task']['id'] == action['parameters']['task_id']
             and [f['id'] for f in result['cited_facts']] == action['parameters']['fact_ids'],
             'Selected handoff differs from its exact native action.')
    return (copy.deepcopy(result['task']), action['id'], copy.deepcopy(result['cited_facts']),
            result['model_reason'], status == 'paused')


def capture_handoff(workspace, diagnostic):
    _diagnostic(diagnostic)
    loop = EvidenceHandoffCloudLoop(workspace)
    paths = [loop.db, loop.study.db, loop.study.root / 'catalog.json']
    before = _identities(paths)
    _require(all(before[str(p)] is not None for p in paths), 'Study, controller and frozen catalog required.')
    with loop._connect() as con:
        project, spec, state = loop._state(con)
        rows = [dict(row) for row in con.execute('SELECT * FROM calls ORDER BY ordinal')]
    _require(not any(row['status'] in {'sending', 'received'} for row in rows),
             'Unfinished native requests block handoff publication.')
    bound, trace = _bind_native(loop, state, spec, rows, context_builder=project_context,
                                scope_fields=('catalog_snapshot_sha256',))
    _require(bound == {a['id'] for a in state['actions']}, 'All actions require an actual native binding.')
    with loop.study._connect() as con:
        config, current, original = loop.study._state(con)
    _require(current == state, 'Handoff state changed during capture.')
    catalog = loop.study._catalog(config)
    _require(catalog['snapshot_sha256'] == state['catalog_snapshot_sha256']
             and catalog['source_snapshots']['diagnostic']['snapshot_sha256'] == diagnostic['snapshot_sha256'],
             'Frozen catalog belongs to a different diagnostic.')
    fields = ('id', 'ordinal', 'action', 'parameters', 'reason', 'result_sha256',
              'source_citation_ids', 'evidence_action_ids')
    actions = []
    for action in original:
        _public_text({'reason': action['reason'], 'parameters': action['parameters']})
        actions.append({**{k: copy.deepcopy(action[k]) for k in fields},
                        'result': copy.deepcopy(action['result']), 'model_selected': action['id'] in bound})
    entries = _native_entries(rows, trace)
    _public_text({'goal': state['goal'], 'native_trace': entries})
    task, selected_id, facts, reason, waiting = _selection(actions, state['status'])
    view = {'schema_version': 'p02-handoff-view-v1',
            'diagnostic_snapshot_sha256': diagnostic['snapshot_sha256'],
            'catalog_snapshot_sha256': catalog['snapshot_sha256'], 'goal': state['goal'],
            'study_status': state['status'], 'controller_status': project['status'],
            'controller_reason': project['reason'], 'actions': actions, 'native_trace': entries,
            'selected_task': task, 'selected_action_id': selected_id, 'cited_facts': facts,
            'model_reason_unreviewed': reason, 'source_snapshots': copy.deepcopy(catalog['source_snapshots']),
            'execution': {'model': spec['model_identity']['model'], 'requests_reserved': len(rows),
                          'max_requests': spec['max_requests'], 'applied_calls': len(bound),
                          'invalid_calls': sum(r['status'] == 'invalid' for r in rows), 'new_fits': 0},
            'waiting_for_external_input': waiting, 'external_task_executed': False,
            'host_metadata_notice': NOTICE, 'scientific_validation': False}
    _require(_identities(paths) == before, 'Handoff journal or catalog changed during capture.')
    view['snapshot_sha256'] = fingerprint(view)
    return view


def _markdown(view):
    lines = ['# 研究证据交接', '', '这是已封存记录；没有执行外部任务，也不是科学批准。',
             '模型理由未审定；任务模板由宿主提供，所选事实与任务ID来自原生调用。', '',
             '- 研究状态：' + view['study_status'],
             '- 控制器状态：' + str(view['controller_status']) + ' / ' + str(view['controller_reason']),
             '- 诊断快照：`' + view['diagnostic_snapshot_sha256'] + '`',
             '- 目录快照：`' + view['catalog_snapshot_sha256'] + '`', '']
    task = view['selected_task']
    if task is None:
        lines += ['尚无有效的任务交接。模型未记录所选模板；不能据此宣称队员已有待执行任务。', '']
    else:
        lines += ['## ' + task['title'], '',
                  '等待外部输入：' + ('是' if view['waiting_for_external_input'] else '否'), '',
                  '### 原始来源', '', *['- ' + url for url in task['source_urls']], '',
                  '### 交付物', '', *['- ' + text for text in task['deliverables']], '',
                  '### 验收条件', '', *['- ' + text for text in task['acceptance']], '',
                  '### 模型原始理由（未审定）', '',
                  *['> ' + line for line in view['model_reason_unreviewed'].splitlines()], '',
                  '### 所选事实', '']
        for fact in view['cited_facts']:
            source = fact['provenance']['source']
            lines += ['- **' + fact['id'] + '**：' + fact['label'],
                      '  - 来源：`' + source + '`；JSON指针：`' + fact['provenance']['pointer'] + '`',
                      '  - 来源快照：`' + str(view['source_snapshots'][source]['snapshot_sha256']) + '`',
                      '  - 来源文件SHA256：`' + view['source_snapshots'][source]['file_sha256'] + '`',
                      '  - 原值：`' + canonical(fact['value']) + '`']
        lines += ['', '请反馈原始URL、文件哈希、精确坐标、映射/零值规则及未知项；不要把本交接当作外部工作已完成。', '']
    return '\n'.join(lines).encode('utf-8')


def _manifest(view, files):
    return {'schema_version': 'p02-handoff-artifacts-v1', 'snapshot_sha256': view['snapshot_sha256'],
            'diagnostic_snapshot_sha256': view['diagnostic_snapshot_sha256'],
            'files': {name: {'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw)}
                      for name, raw in files.items()}}


def export_handoff(workspace, diagnostic, output):
    target = Path(output).absolute()
    for path in (target, *target.parents):
        _require(not path.is_symlink() and not getattr(path, 'is_junction', lambda: False)(),
                 'Output cannot redirect.')
    loop = EvidenceHandoffCloudLoop(workspace)
    with loop.study._connect() as con:
        config = json.loads(con.execute('SELECT * FROM meta').fetchone()['config'])
    for path in [loop.study.root, *(Path(v) for v in config['private_sources'].values())]:
        source = path.absolute().resolve(); resolved = target.resolve()
        _require(not (resolved == source or resolved.is_relative_to(source) or source.is_relative_to(resolved)),
                 'Output overlaps study or frozen evidence location.')
    if target.exists():
        raise ResearchError('ALREADY_EXISTS', 'Use a fresh handoff publication directory.')
    view = capture_handoff(workspace, diagnostic)
    files = {'handoff.json': (canonical(view) + '\n').encode('utf-8'), 'handoff.md': _markdown(view)}
    _require(all(len(raw) <= LIMITS[name] for name, raw in files.items()), 'Public handoff exceeds bounds.')
    manifest = _manifest(view, files)
    target.mkdir(parents=True, exist_ok=False)
    for name, raw in files.items():
        with (target / name).open('xb') as stream:
            stream.write(raw)
    with (target / 'manifest.json').open('xb') as stream:
        stream.write((canonical(manifest) + '\n').encode('utf-8'))
    return manifest


def read_handoff_artifacts(directory, diagnostic):
    _diagnostic(diagnostic)
    root = Path(directory).absolute()
    manifest = json.loads(_safe_file(root / 'manifest.json', 100_000))
    files = {name: _safe_file(root / name, limit) for name, limit in LIMITS.items()}
    view = json.loads(files['handoff.json'])
    _require(view.get('schema_version') == 'p02-handoff-view-v1'
             and view.get('snapshot_sha256') == fingerprint({k: v for k, v in view.items() if k != 'snapshot_sha256'})
             and view.get('diagnostic_snapshot_sha256') == diagnostic['snapshot_sha256']
             and view.get('source_snapshots', {}).get('diagnostic', {}).get('snapshot_sha256') == diagnostic['snapshot_sha256']
             and view.get('scientific_validation') is False and view.get('external_task_executed') is False
             and view.get('execution', {}).get('new_fits') == 0,
             'Handoff identity or diagnostic binding changed.')
    task, selected_id, facts, reason, waiting = _selection(view['actions'], view['study_status'])
    _require((task, selected_id, facts, reason, waiting) ==
             (view['selected_task'], view['selected_action_id'], view['cited_facts'],
              view['model_reason_unreviewed'], view['waiting_for_external_input']), 'Handoff selection changed.')
    _public_text({'goal': view['goal'], 'native_trace': view['native_trace'],
                  'reasons': [a['reason'] for a in view['actions']]})
    _require(manifest == _manifest(view, files) and files['handoff.md'] == _markdown(view),
             'Handoff manifest or teammate document changed.')
    return files
