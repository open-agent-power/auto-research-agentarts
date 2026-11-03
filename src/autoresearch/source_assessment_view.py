"""Publish actual source selections and model assessments without approving them."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile

from .chemotopo_experiment_evidence import _safe_file
from .chemotopo_iteration_view import _bind_native, _require
from .contracts import canonical, fingerprint
from .diagnostic_view import _native_entries
from .handoff_view import _public_text
from .postrun_view import _identities
from .returned_evidence import validate_packet
from .source_assessment import SourceAssessmentCloudLoop, project_context


LIMITS = {'assessment.json': 3_000_000, 'assessment.md': 100_000}


def _capture(workspace, progress_only=False, *, controller_class=SourceAssessmentCloudLoop):
    loop = controller_class(workspace)
    paths = [loop.db, loop.study.db, loop.study.root / 'packet.json']
    before = _identities(paths)
    _require(all(before[str(p)] is not None for p in paths), 'Study, controller and source packet required.')
    with loop._connect() as con:
        project, spec, state = loop._state(con)
        rows = [dict(row) for row in con.execute('SELECT * FROM calls ORDER BY ordinal')]
    unfinished = [r for r in rows if r['status'] in {'sending', 'received'}]
    if not progress_only:
        _require(not unfinished, 'Unresolved requests block publication.')
        _require(project['status'] != 'active' or state['status'] != 'active', 'Publish only a bounded terminal outcome.')
    bound, trace = _bind_native(loop, state, spec, rows, context_builder=project_context,
                                scope_fields=('source_snapshot_sha256',))
    _require(bound == {a['id'] for a in state['actions']}, 'Every action must bind an actual native request.')
    with loop.study._connect() as con:
        config, current, originals = loop.study._state(con)
    _require(current == state, 'Study changed during publication.')
    packet = loop.study._source(config)
    validate_packet(packet)
    fields = ('id', 'ordinal', 'action', 'parameters', 'reason', 'result_sha256',
              'source_citation_ids', 'evidence_action_ids')
    actions = []
    for a in originals:
        _public_text({'reason': a['reason'], 'parameters': a['parameters']})
        actions.append({**{k: copy.deepcopy(a[k]) for k in fields},
                        'result': copy.deepcopy(a['result']), 'model_selected': a['id'] in bound})
    entries = []
    for row, item in zip(rows, trace):
        if row['status'] in {'sending', 'received'}:
            entries.append({**item, 'error_code': row['error_code'], 'content': None, 'tool_calls': [],
                            'response_received': row['response_json'] is not None,
                            'outcome_unknown': row['status'] == 'sending'})
        else:
            entry = _native_entries([row], [item])[0]
            response = json.loads(row['response_json'])
            entry['response_metadata'] = {k: response[k] for k in ('done_reason', 'eval_count', 'prompt_eval_count') if k in response}
            entries.append(entry)
    _public_text({'goal': state['goal'], 'native_trace': entries})
    assessments = [a for a in actions if a['action'] == 'record_assessment']
    _require(len(assessments) <= 1, 'A workflow has at most one submitted assessment.')
    assessment = assessments[0] if assessments else None
    view = {
        'schema_version': 'p02-source-assessment-progress-v1' if progress_only else 'p02-source-assessment-view-v1',
        'source_snapshot_sha256': packet['snapshot_sha256'],
        'submission_snapshot_sha256': packet['submission_snapshot_sha256'],
        'handoff_snapshot_sha256': packet['handoff_snapshot_sha256'],
        'task_id': packet['task_id'], 'contributor': copy.deepcopy(packet['contributor']),
        'goal': state['goal'], 'study_status': state['status'],
        'controller_status': project['status'], 'controller_reason': project['reason'],
        'actions': actions, 'native_trace': entries,
        'assessment_action_id': assessment['id'] if assessment else None,
        'answers': copy.deepcopy(assessment['parameters']['answers']) if assessment else [],
        'interpretation_status': 'unreviewed_model_assessment' if assessment else 'no_valid_assessment',
        'sources': copy.deepcopy(packet['sources']), 'chunks': copy.deepcopy(packet['chunks']),
        'alias_map': copy.deepcopy(state['alias_map']), 'read_aliases': list(state['read_aliases']),
        'read_source_ids': list(state['read_source_ids']),
        'submission_claims_unverified': copy.deepcopy(packet['submission_claims']),
        'unresolved_questions': list(packet['unresolved_questions']),
        'extractor': copy.deepcopy(packet['extractor']), 'exclusions': copy.deepcopy(packet['exclusions']),
        'execution': {'model': spec['model_identity']['model'], 'requests_reserved': len(rows),
                      'max_requests': spec['max_requests'], 'applied_calls': len(bound),
                      'invalid_calls': sum(r['status'] == 'invalid' for r in rows), 'new_fits': 0},
        'notice': 'Source IDs and citation aliases are model selections. Expansion to the submitted chunks is host execution. Source locators establish extraction coordinates, not the truth of an interpretation.',
        'task_complete': False, 'scientific_validation': False, 'biological_endpoint_eligible': False,
    }
    if progress_only:
        view.update(publication_eligible=False, unfinished_requests=len(unfinished),
                    progress_only=True, automatic_retry=False)
    _require(_identities(paths) == before, 'Journal or source packet changed during capture.')
    view['snapshot_sha256'] = fingerprint(view)
    return view


def capture_source_assessment(workspace):
    return _capture(workspace)


def _markdown(view):
    labels = {'antibody_channel': '抗体与图像通道', 'object_export': '对象与导出字段',
              'aggregation': '对照与聚合', 'zero_objects': '零对象与缺失转换'}
    statuses = {'supported': '模型认为有支持', 'unresolved': '模型认为仍未决', 'conflicting': '模型认为有冲突'}
    aliases = {a['alias']: a for a in view['alias_map']}
    sources = {s['id']: s for s in view['sources']}
    lines = ['# 回传资料与剩余研究问题', '',
             '这份记录保存实际来源选择和模型判断；判断未审定，任务与生物终点尚未放行。', '',
             '提交者：' + view['contributor']['role'] + ' / ' + view['contributor']['label'],
             '来源快照：`' + view['source_snapshot_sha256'] + '`', '',
             '本轮模型请求：' + str(view['execution']['requests_reserved']),
             '新增拟合：0', '']
    if not view['answers']:
        lines += ['尚无有效评议。保留原始错误和控制行动，不从暂停理由倒推研究已完成。', '']
    for answer in view['answers']:
        lines += ['## ' + labels[answer['question_id']], '', statuses[answer['status']], '', answer['answer'], '', '引用：']
        for alias in answer['evidence_ids']:
            item = aliases[alias]; source = sources[item['source_id']]
            lines += ['- `' + alias + '`：' + source['url'] + '；' + item['locator']['kind'] + ' ' + item['locator']['value']
                      + '；字符 ' + str(item['start_char']) + '–' + str(item['end_char'])
                      + '；原文件 SHA256 `' + item['source_sha256'] + '`']
        lines.append('')
    lines += ['## 提交时仍需补充', '', *['- ' + q for q in view['unresolved_questions']], '',
              '以上缺项来自提交时的记录；模型答案单列，不能自动覆盖来源或升级资格。', '']
    return '\n'.join(lines).encode('utf-8')


def _manifest(view, files):
    return {'schema_version': 'p02-source-assessment-artifacts-v1', 'snapshot_sha256': view['snapshot_sha256'],
            'source_snapshot_sha256': view['source_snapshot_sha256'],
            'files': {name: {'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw)} for name, raw in files.items()}}


def export_source_assessment(workspace, output):
    target = Path(output).absolute()
    for path in (target, *target.parents):
        _require(not path.is_symlink() and not getattr(path, 'is_junction', lambda: False)(), 'Output cannot redirect.')
    loop = SourceAssessmentCloudLoop(workspace)
    with loop.study._connect() as con:
        config, _, _ = loop.study._state(con)
    for location in [loop.study.root, *config['private_sources'].values()]:
        source = Path(location).absolute().resolve(); resolved = target.resolve()
        _require(not (resolved == source or resolved.is_relative_to(source) or source.is_relative_to(resolved)), 'Output overlaps evidence or study.')
    _require(not target.exists(), 'Use a fresh publication directory.')
    view = capture_source_assessment(workspace)
    files = {'assessment.json': (canonical(view) + '\n').encode('utf-8'), 'assessment.md': _markdown(view)}
    _require(all(len(raw) <= LIMITS[name] for name, raw in files.items()), 'Publication exceeds bounds.')
    manifest = _manifest(view, files)
    target.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix='.' + target.name + '-publishing-', dir=target.parent))
    for name, raw in files.items():
        with (staging / name).open('xb') as stream:
            stream.write(raw)
    with (staging / 'manifest.json').open('xb') as stream:
        stream.write((canonical(manifest) + '\n').encode('utf-8'))
    _require(not target.exists(), 'Publication target appeared during export.')
    staging.rename(target)
    return manifest


def read_source_assessment_artifacts(directory, expected_source_snapshot=None):
    root = Path(directory).absolute()
    manifest = json.loads(_safe_file(root / 'manifest.json', 100_000))
    files = {name: _safe_file(root / name, limit) for name, limit in LIMITS.items()}
    view = json.loads(files['assessment.json'])
    _require(view.get('schema_version') == 'p02-source-assessment-view-v1'
             and view.get('snapshot_sha256') == fingerprint({k: v for k, v in view.items() if k != 'snapshot_sha256'})
             and view.get('scientific_validation') is False and view.get('biological_endpoint_eligible') is False
             and view.get('task_complete') is False and view.get('execution', {}).get('new_fits') == 0,
             'Assessment identity or qualification changed.')
    _require(expected_source_snapshot is None or view['source_snapshot_sha256'] == expected_source_snapshot,
             'Published assessment belongs to another source packet.')
    _require(manifest == _manifest(view, files) and files['assessment.md'] == _markdown(view), 'Published assessment changed.')
    return files


def _progress_markdown(view):
    lines = ['# 回传原文读取进度', '',
             '这是中途进度记录，不能替代完成的评议或解除未知请求。原请求不自动重发。', '',
             '研究状态：' + view['study_status'],
             '控制器状态：' + str(view['controller_status']) + ' / ' + str(view['controller_reason']),
             '已预留请求：' + str(view['execution']['requests_reserved']),
             '未完成请求：' + str(view['unfinished_requests']),
             '实际读取来源：' + '、'.join(view['read_source_ids']),
             '实际返回片段：' + str(len(view['read_aliases'])), '', '## 实际请求记录', '']
    for entry in view['native_trace']:
        lines.append('- 请求 ' + str(entry['ordinal']) + '：' + entry['status'] + '；' + str(entry.get('error_code') or '无错误码'))
        if entry.get('response_metadata'):
            lines.append('  - 响应元数据：`' + canonical(entry['response_metadata']) + '`')
    lines += ['', '尚未完成的判断保持空缺；已读原文可继续核对，但它不自动证明生物端点或任务完成。', '']
    return '\n'.join(lines).encode('utf-8')


def _progress_manifest(view, files):
    return {'schema_version': 'p02-source-progress-artifacts-v1', 'snapshot_sha256': view['snapshot_sha256'],
            'source_snapshot_sha256': view['source_snapshot_sha256'],
            'files': {name: {'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw)} for name, raw in files.items()}}


def export_source_progress(workspace, output):
    """A separate diagnostic snapshot; never a successful assessment publication."""
    target = Path(output).absolute(); source = Path(workspace).absolute().resolve()
    for path in (target, *target.parents):
        _require(not path.is_symlink() and not getattr(path, 'is_junction', lambda: False)(), 'Progress output cannot redirect.')
    resolved = target.resolve()
    _require(not (resolved == source or resolved.is_relative_to(source) or source.is_relative_to(resolved)), 'Progress overlaps study.')
    _require(not target.exists(), 'Use a fresh progress snapshot directory.')
    view = _capture(workspace, progress_only=True)
    files = {'progress.json': (canonical(view) + '\n').encode('utf-8'), 'progress.md': _progress_markdown(view)}
    _require(len(files['progress.json']) <= LIMITS['assessment.json'] and len(files['progress.md']) <= LIMITS['assessment.md'], 'Progress exceeds bounds.')
    manifest = _progress_manifest(view, files)
    target.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix='.' + target.name + '-publishing-', dir=target.parent))
    for name, raw in files.items():
        with (staging / name).open('xb') as stream:
            stream.write(raw)
    with (staging / 'manifest.json').open('xb') as stream:
        stream.write((canonical(manifest) + '\n').encode('utf-8'))
    _require(not target.exists(), 'Progress target appeared during export.')
    staging.rename(target)
    return manifest


def read_source_progress_artifacts(directory, expected_source_snapshot=None):
    root = Path(directory).absolute()
    manifest = json.loads(_safe_file(root / 'manifest.json', 100_000))
    files = {name: _safe_file(root / name, LIMITS['assessment.json' if name.endswith('.json') else 'assessment.md'])
             for name in ('progress.json', 'progress.md')}
    view = json.loads(files['progress.json'])
    _require(view.get('schema_version') == 'p02-source-assessment-progress-v1'
             and view.get('snapshot_sha256') == fingerprint({k: v for k, v in view.items() if k != 'snapshot_sha256'})
             and view.get('progress_only') is True and view.get('publication_eligible') is False
             and view.get('automatic_retry') is False and view.get('task_complete') is False
             and view.get('scientific_validation') is False and view.get('biological_endpoint_eligible') is False,
             'Progress identity or qualification changed.')
    _require(expected_source_snapshot is None or view['source_snapshot_sha256'] == expected_source_snapshot, 'Progress belongs to another source packet.')
    _require(manifest == _progress_manifest(view, files) and files['progress.md'] == _progress_markdown(view), 'Progress artifacts changed.')
    return files
