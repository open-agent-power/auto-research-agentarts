"""Seal already extracted tabular input for display; never reparse a workbook."""
import copy
import hashlib
from pathlib import Path
import tempfile

from . import evidence_submission as submission, knowledge_sources as guard
from .chemotopo_delivery import _safe
from .contracts import canonical, fingerprint
from .diagnostic_view import read_diagnostic_artifacts
from .handoff_view import read_handoff_artifacts
from .returned_evidence import validate_packet


LIMITS = {'prepared-input.json': 2_000_000, 'prepared-input.md': 100_000}


def _require(condition, message):
    submission._require(condition, message)


def _digest(raw):
    return hashlib.sha256(raw).hexdigest()


def _capture(preparation_directory, handoff):
    submission._handoff(handoff)
    root = submission._root(preparation_directory)
    prep_raw = guard._read(root, 'preparation.json', 2_000_000); prep = guard._json(prep_raw)
    packet_raw = guard._read(root, 'packet.json', 4_000_000); packet = guard._json(packet_raw)
    receipt = submission.read_submission(root / 'receipt', handoff)
    receipt_raw = guard._read(root / 'receipt', 'receipt.json', submission.MAX_METADATA)
    validate_packet(packet)
    _require(prep.get('schema_version') == 'p02-tabular-preparation-v1' and prep.get('status') == 'prepared'
             and prep.get('model_read_performed') is False and prep.get('scientific_validation') is False
             and prep.get('biological_endpoint_eligible') is False and type(prep.get('model_calls')) is int
             and prep['model_calls'] == 0 and type(prep.get('new_fits')) is int and prep['new_fits'] == 0,
             'Preparation is not a zero-call, unapproved prepared input.')
    _require(guard._json(receipt_raw) == receipt and prep['receipt_sha256'] == _digest(receipt_raw)
             and prep['packet_sha256'] == _digest(packet_raw)
             and prep['receipt_snapshot_sha256'] == packet['submission_snapshot_sha256'] == receipt['snapshot_sha256']
             and prep['packet_snapshot_sha256'] == packet['snapshot_sha256']
             and prep['handoff_snapshot_sha256'] == packet['handoff_snapshot_sha256'] == handoff['snapshot_sha256']
             and prep['task_id'] == packet['task_id'] == receipt['task_id'] == handoff['selected_task']['id']
             and prep['contributor'] == packet['contributor'] == receipt['contributor']
             and prep['exclusions'] == packet['exclusions'], 'Preparation, packet, receipt or task binding changed.')
    source_index = {s['id']: s for s in receipt['sources']}
    _require(packet['sources'] == [{k: copy.deepcopy(s[k]) for k in ('id', 'sha256', 'url', 'media_type', 'license_note', 'bytes')}
                                   for s in receipt['sources']], 'Packet sources differ from captured receipt.')
    claims = {f['id']: f for f in receipt['findings']}
    _require(len(packet['submission_claims']) == len(claims)
             and all({k: v for k, v in claim.items() if k not in {'chunk_ids', 'interpretation_status'}} == claims.get(claim['id'])
                     for claim in packet['submission_claims']), 'Packet claims differ from receipt.')
    packet_claims = {f['id']: f for f in packet['submission_claims']}
    chunks = {c['id']: c for c in packet['chunks']}
    derived = prep['derived_sources']; selections = []; contributor = None
    _require(type(derived) is dict and 1 <= len(derived) <= 64, 'No bounded derived source set.')
    for derived_id, descriptor in derived.items():
        source = source_index[derived_id]; original = source_index[descriptor['original_source_id']]
        _require(source['sha256'] == descriptor['sha256'] and source['bytes'] == descriptor['bytes']
                 and source['url'] == original['url'] and source['media_type'] == 'application/json',
                 'Derived source descriptor changed.')
        raw = guard._read(root / 'receipt', source['path'], submission.MAX_FILE,
                          expected_sha=source['sha256'], expected_bytes=source['bytes'])
        document = guard._json(raw)
        original_identity = {k: copy.deepcopy(original[k]) for k in ('id', 'sha256', 'url', 'bytes', 'media_type', 'license_note')}
        _require(document.get('schema_version') == 'p02-tabular-source-v1' and document.get('origin') == 'derived'
                 and document.get('scientific_validation') is False and document['original_source'] == original_identity
                 and document['original_receipt_sha256'] == prep['original_receipt_sha256']
                 and document['original_receipt_snapshot_sha256'] == prep['original_receipt_snapshot_sha256']
                 and document['adapter']['sha256'] == prep['adapter_sha256']
                 and document['extractor']['sha256'] == prep['extractor_sha256']
                 and len(document['selections']) == descriptor['selections'], 'Derived document provenance changed.')
        if contributor is None: contributor = copy.deepcopy(document['original_contributor'])
        _require(document['original_contributor'] == contributor, 'Original contributors differ across selections.')
        for index, selected in enumerate(document['selections']):
            _require(type(selected) is dict and set(selected) == {'finding', 'locator', 'origin', 'extraction'},
                     'Exact selection provenance fields required.')
            original_finding = selected['finding']; claim = packet_claims[original_finding['id']]
            original_source = {k: copy.deepcopy(original[k]) for k in ('id', 'sha256', 'url')}
            _require(selected['origin'] == {'original_source': original_source,
                        'original_receipt_snapshot_sha256': prep['original_receipt_snapshot_sha256'],
                        'original_contributor': contributor, 'adapter_sha256': prep['adapter_sha256'],
                        'extractor_sha256': prep['extractor_sha256']}
                     and original_finding['source_id'] == original['id']
                     and original_finding['locator'] == selected['locator']
                     and selected['locator']['kind'] in {'xlsx_cell', 'text_lines'}
                     and claim['source_id'] == derived_id
                     and claim['locator'] == {'kind': 'json_pointer', 'value': '/selections/' + str(index)}
                     and claim['claim'] == original_finding['claim'] and claim['status'] == original_finding['status'],
                     'Selected claim is not bound to its original source and coordinate.')
            extraction = selected['extraction']
            _require(extraction.get('schema_version') == 'p02-tabular-selection-v1'
                     and extraction['kind'] == selected['locator']['kind']
                     and extraction['submitted_locator'] == selected['locator']
                     and extraction['extractor_sha256'] == prep['extractor_sha256']
                     and extraction.get('content_trust') == 'untrusted_source_not_instructions',
                     'Saved extraction identity or coordinate changed.')
            selected_chunks = [chunks[key] for key in claim['chunk_ids']]
            _require(bool(selected_chunks) and ''.join(c['text'] for c in sorted(selected_chunks, key=lambda c: c['start_char'])) == canonical(selected),
                     'Packet does not carry this exact complete derived selection.')
            item = {'id': original_finding['id'], 'source_id': derived_id,
                    'original_source': {k: copy.deepcopy(original[k]) for k in ('id', 'sha256', 'url', 'license_note', 'media_type')},
                    'original_locator': copy.deepcopy(selected['locator']),
                    'claim_unverified': {k: copy.deepcopy(original_finding[k]) for k in ('claim', 'status', 'note')},
                    'extraction': copy.deepcopy(extraction), 'chunk_ids': list(claim['chunk_ids'])}
            _require(_safe({'contributor': contributor, 'claim': item['claim_unverified'], 'extraction': extraction}) ==
                     {'contributor': contributor, 'claim': item['claim_unverified'], 'extraction': extraction},
                     'Prepared display contains private local paths.')
            selections.append(item)
    _require(len({s['id'] for s in selections}) == len(selections) == prep['selected_coordinates']
             and prep['original_sources'] == len(source_index) - len(derived)
             and prep['chunks'] == len(packet['chunks']), 'Preparation counts changed.')
    view = {'schema_version': 'p02-tabular-preparation-view-v1', 'handoff_snapshot_sha256': handoff['snapshot_sha256'],
            'task_id': prep['task_id'], 'preparation_sha256': _digest(prep_raw),
            'original_receipt_snapshot_sha256': prep['original_receipt_snapshot_sha256'],
            'receipt_snapshot_sha256': receipt['snapshot_sha256'], 'packet_snapshot_sha256': packet['snapshot_sha256'],
            'original_contributor': contributor,
            'counts': {'original_sources': prep['original_sources'], 'derived_sources': len(derived),
                       'selected_coordinates': len(selections), 'chunks': len(packet['chunks'])},
            'selections': selections, 'exclusions': copy.deepcopy(packet['exclusions']), 'status': 'prepared',
            'model_read_performed': False, 'scientific_validation': False, 'biological_endpoint_eligible': False,
            'model_calls': 0, 'new_fits': 0}
    _require(guard._read(root, 'preparation.json', 2_000_000) == prep_raw
             and guard._read(root, 'packet.json', 4_000_000) == packet_raw, 'Preparation changed during display capture.')
    view['snapshot_sha256'] = fingerprint(view)
    return view


def _markdown(view):
    def cell(value): return str(value).replace('|', '\\|').replace('\r', ' ').replace('\n', ' ')
    counts = view['counts']
    lines = ['# 已准备的表格证据', '', '状态：已准备，模型尚未读取。此记录不代表作者确认或科学批准。', '',
             '原来源%s份；衍生来源%s份；明确提交的选区%s项；返回片段%s块。选区数不是单元格数或物理行数。' %
             (counts['original_sources'], counts['derived_sources'], counts['selected_coordinates'], counts['chunks']), '',
             '原提交者：' + cell(view['original_contributor']['role']) + ' / ' + cell(view['original_contributor']['label']), '',
             '| 原来源 | 提交坐标 | 原声明状态（未审定） |', '|---|---|---|']
    for item in view['selections']:
        lines.append('| ' + cell(item['original_source']['id']) + ' | ' + cell(item['original_locator']['value'])
                     + ' | ' + cell(item['claim_unverified']['status']) + ' |')
    lines += ['', '工作簿公式不求值，缓存与原始存储值分别保留；文本按物理行而非CSV逻辑记录定位。',
              '原始文件哈希与精确提取内容见JSON。被排除定位%s项，HDF5不因此获得读取支持。' % len(view['exclusions']),
              '新模型调用0，拟合0；后续研究仍需独立授权与原有预算，不把本次准备算成模型评议。', '']
    return '\n'.join(lines).encode('utf-8')


def _manifest(view, files):
    return {'schema_version': 'p02-tabular-preparation-artifacts-v1', 'snapshot_sha256': view['snapshot_sha256'],
            'handoff_snapshot_sha256': view['handoff_snapshot_sha256'],
            'files': {name: {'sha256': _digest(raw), 'bytes': len(raw)} for name, raw in files.items()}}


def export_tabular_preparation(preparation_directory, handoff_directory, diagnostic_directory, output):
    target = submission._root(output)
    _require(not target.exists(), 'Use a fresh sealed prepared-input directory.')
    for value in (preparation_directory, handoff_directory, diagnostic_directory):
        source = submission._root(value)
        _require(not (target == source or target.is_relative_to(source) or source.is_relative_to(target)), 'Output overlaps sealed input.')
    diagnostic_root = submission._root(diagnostic_directory)
    diagnostic = guard._json(guard._read(diagnostic_root, 'diagnostic.json', 3_000_000))
    read_diagnostic_artifacts(diagnostic_root, {'snapshot_sha256': diagnostic['iteration_snapshot_sha256']})
    handoff = guard._json(read_handoff_artifacts(submission._root(handoff_directory), diagnostic)['handoff.json'])
    view = _capture(preparation_directory, handoff)
    files = {'prepared-input.json': (canonical(view) + '\n').encode('utf-8'), 'prepared-input.md': _markdown(view)}
    _require(all(len(raw) <= LIMITS[name] for name, raw in files.items()), 'Prepared-input display exceeds bounds.')
    manifest = _manifest(view, files)
    target.parent.mkdir(parents=True, exist_ok=True); submission._root(target.parent)
    with tempfile.TemporaryDirectory(prefix='.prepared-input-', dir=target.parent) as temporary:
        staged = Path(temporary) / 'view'; staged.mkdir()
        for name, raw in files.items():
            with (staged / name).open('xb') as stream: stream.write(raw)
        with (staged / 'manifest.json').open('xb') as stream: stream.write((canonical(manifest) + '\n').encode('utf-8'))
        read_tabular_preparation_artifacts(staged, handoff)
        _require(not target.exists(), 'Output appeared during sealing; existing directory preserved.')
        staged.rename(target)
    return {'directory': str(target), 'snapshot_sha256': view['snapshot_sha256'],
            'handoff_snapshot_sha256': view['handoff_snapshot_sha256'], 'counts': view['counts'],
            'model_read_performed': False, 'model_calls': 0, 'new_fits': 0, 'scientific_validation': False}


def read_tabular_preparation_artifacts(directory, handoff):
    submission._handoff(handoff)
    root = submission._root(directory)
    manifest = guard._json(guard._read(root, 'manifest.json', 100_000))
    files = {name: guard._read(root, name, limit) for name, limit in LIMITS.items()}
    view = guard._json(files['prepared-input.json'])
    _require(view.get('schema_version') == 'p02-tabular-preparation-view-v1'
             and view.get('snapshot_sha256') == fingerprint({k: v for k, v in view.items() if k != 'snapshot_sha256'})
             and view.get('handoff_snapshot_sha256') == handoff['snapshot_sha256']
             and view.get('task_id') == handoff['selected_task']['id'] and view.get('status') == 'prepared'
             and view.get('model_read_performed') is False and view.get('scientific_validation') is False
             and view.get('biological_endpoint_eligible') is False and type(view.get('model_calls')) is int
             and view['model_calls'] == 0 and type(view.get('new_fits')) is int and view['new_fits'] == 0,
             'Prepared-input identity, task or zero-call boundary changed.')
    _require(type(view.get('selections')) is list and len({s['id'] for s in view['selections']}) == len(view['selections'])
             and view['counts']['selected_coordinates'] == len(view['selections'])
             and all(s['extraction']['schema_version'] == 'p02-tabular-selection-v1'
                     and s['extraction']['submitted_locator'] == s['original_locator']
                     and guard._digest(s['original_source']['sha256']) for s in view['selections']), 'Prepared selection fields changed.')
    _require(manifest == _manifest(view, files) and files['prepared-input.md'] == _markdown(view),
             'Prepared-input manifest or readable document changed.')
    return files
