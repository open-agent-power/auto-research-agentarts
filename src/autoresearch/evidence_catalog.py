"""Small host-curated facts from sealed publications, never original sources.

Source text is retained so byte identities and every derived fact can be checked
without reopening a workbook, a model transport, or a scientific executor.
"""
import copy
import hashlib
import json
import math
from pathlib import Path

from .contracts import ResearchError, fingerprint


SCHEMA = 'p02-evidence-catalog-v1'
POLICIES = ('positive_equal_batch', 'positive_equal_section',
            'recorded_equal_batch', 'recorded_equal_section')
LIMITS = {'diagnostic': 300_000, 'iteration': 600_000,
          'baseline': 600_000, 'inventory': 3_000_000}
SOURCE_URLS = ['https://data.mendeley.com/datasets/57nrc49stj/1',
               'https://doi.org/10.17639/nott.7080',
               'https://doi.org/10.1016/j.biomaterials.2021.120740']
LIMITATIONS = [
    'Host-curated facts and task templates; not model-generated research or scientific approval.',
    'Only sealed saved views are checked; original images, workbooks and author exports are not reconstructed.',
    'Positive delta MAE means worse than chemistry within that same processing policy; Count > 0 is not a positive biological response.',
    'Previously viewed exploratory grouped predictions and known within-section controls are not an independent final test.',
    'The old source-policy fit gate is not a ban on the separately allowed numerical raw-proxy exploration.',
    'Inventory absence applies only to this captured project; channel names do not prove an ALP marker or export mapping.',
    'Hash and pointer consistency preserve sealed evidence, not scientific truth or external authenticity.',
]


def _require(condition, message):
    if not condition:
        raise ResearchError('EVIDENCE_CHANGED', message)


def _pairs(items):
    result = {}
    for key, value in items:
        _require(key not in result, 'Duplicate source JSON key.')
        result[key] = value
    return result


def _decode(text, limit):
    _require(type(text) is str and 0 < len(text.encode('utf-8')) <= limit,
             'Source JSON exceeds catalog bounds.')
    try:
        value = json.loads(text, object_pairs_hook=_pairs,
                           parse_constant=lambda _: (_ for _ in ()).throw(ValueError('nonfinite')))
    except (ValueError, TypeError, RecursionError) as error:
        raise ResearchError('EVIDENCE_CHANGED', 'Invalid bounded source JSON.') from error
    _require(type(value) is dict, 'Source JSON must be an object.')
    return value


def _pointer(document, pointer):
    value = document
    if pointer:
        _require(pointer.startswith('/'), 'Invalid fact pointer.')
        for token in pointer[1:].split('/'):
            token = token.replace('~1', '/').replace('~0', '~')
            value = value[int(token)] if type(value) is list else value[token]
    return copy.deepcopy(value)


def _snapshot(document, schema):
    _require(document.get('schema_version') == schema
             and document.get('scientific_validation') is False
             and document.get('snapshot_sha256') == fingerprint(
                 {k: v for k, v in document.items() if k != 'snapshot_sha256'}),
             'Source view snapshot changed.')


def _tasks():
    common = {'source_urls': SOURCE_URLS, 'requires_external_data': True,
              'origin': 'host_curated_template'}
    return [
        dict(common, id='export_mapping', title='核对作者导出列、对象、染色与图像批次映射',
             required_fact_ids=['source_gate', 'candidate_vs_chem.positive_equal_batch',
                                'project_source', 'measurement_groups', 'ome_file.0'],
             deliverables=['mapping.csv：原始URL、文件SHA256、页/表/单元格、对象名、测量字段、染色/通道、图像/批次、工作簿列与聚合规则。',
                           'evidence-index.csv：逐项证据定位及仍缺少的作者原始导出/映射文件。'],
             acceptance=['逐条保留原始URL、文件哈希与精确坐标；明确已证实、未证实和所缺材料。',
                         '用作者记录连接工作簿列→对象测量→染色/通道→图像批次；不凭文件名、红通道或荧光染料名认定ALP。',
                         '区分mean/integrated intensity、归一化与聚合；元数据不当作测量结果。']),
        dict(common, id='zero_object_rule', title='核对零对象、缺失值与归一化转换规则',
             required_fact_ids=['source_gate', 'candidate_vs_chem.recorded_equal_batch',
                                'topography_counts.recorded_equal_batch', 'source_manifest'],
             deliverables=['zero-rule.csv：原始文件SHA256、工作表与单元格/行坐标、对象Count、原始值、空值/NaN/零、转换、同section控制及证据。',
                           'handoff.md：可核对样例、作者规则、冲突和明确未知项。'],
             acceptance=['必须取得原始记录并给出精确文件/工作表/单元格坐标；不能只提交汇总数。',
                         '分别说明Count=0、真实测量零、缺失与占位符；不把保留零/仅正计数与等批次/等section混为一轴。',
                         '说明转换及控制分母来源；不能以某一规则预测误差更低作为生物规则成立的证据。']),
    ]


def _assemble(texts):
    _require(type(texts) is dict and set(texts) == set(LIMITS), 'Exact four catalog sources required.')
    docs = {name: _decode(texts[name], limit) for name, limit in LIMITS.items()}
    diagnostic, iteration, baseline, inventory = (docs[n] for n in LIMITS)
    _snapshot(diagnostic, 'p02-diagnostic-view-v1')
    _snapshot(iteration, 'p02-iteration-view-v1')
    _snapshot(baseline, 'p02-workbench-v1')
    _require(diagnostic['iteration_snapshot_sha256'] == iteration['snapshot_sha256']
             and iteration['baseline_publication_sha256'] == baseline['snapshot_sha256'],
             'Catalog publication chain differs.')
    _require(inventory.get('schema_version') == 'chemotopo-project-inventory-v1'
             and inventory.get('source') in baseline['source_manifest'],
             'Project inventory is not the captured baseline source.')
    facts = []

    def fact(identifier, kind, label, source, pointer, value=None, derived=False):
        facts.append({'id': identifier, 'kind': kind, 'label': label,
                      'value': copy.deepcopy(value) if derived else _pointer(docs[source], pointer),
                      'provenance': {'source': source, 'pointer': pointer}})

    policies = diagnostic['candidate_facts']['policies']
    _require(type(policies) is list and len(policies) == 4
             and {p['policy'] for p in policies} == set(POLICIES), 'Four unique candidate policies required.')
    for policy in POLICIES:
        i = next(i for i, row in enumerate(policies) if row['policy'] == policy)
        row = policies[i]
        _require(all(type(row[k]) in (int, float) and math.isfinite(row[k])
                     for k in ('candidate_mae', 'chemistry_mae', 'delta_mae'))
                 and math.isclose(row['candidate_mae'] - row['chemistry_mae'], row['delta_mae'], abs_tol=1e-12)
                 and row['comparison'] == ('worse' if row['delta_mae'] > 0 else 'better' if row['delta_mae'] < 0 else 'tied'),
                 'Candidate comparison arithmetic or direction changed.')
        fact('candidate_vs_chem.' + policy, 'within_policy_metric',
             policy + '：候选减化学MAE，正值更差', 'diagnostic', '/candidate_facts/policies/' + str(i))
        fact('topography_counts.' + policy, 'within_policy_group_counts',
             policy + '：已保存拓扑分组计数', 'diagnostic',
             '/topography/summary/policies/' + policy + '/methods/current_candidate')
    fact('source_gate', 'source_scope_gate', '历史来源策略门：不具生物端点资格', 'baseline', '/endpoint_gate')
    fact('numerical_scope', 'numerical_scope_gate', '独立数值代理探索范围', 'iteration', '/endpoint_gate')
    fact('source_manifest', 'source_identity', '基线原始文件名、字节数与SHA256', 'baseline', '/source_manifest')
    fact('project_source', 'source_identity', '本次捕获的HDF5项目身份', 'inventory', '/source')
    measurements = inventory['inventory']['measurements']
    _require(type(measurements) is list and len(measurements) == 1, 'One captured measurement group required.')
    fact('measurement_groups', 'captured_project_inventory', '此项目实际测量组；不是实验日期声明',
         'inventory', '/inventory/measurements/0/groups')
    fact('measurement_features', 'captured_project_inventory', '此项目实际存储的测量字段',
         'inventory', '/inventory/measurements/0/features')
    ome = inventory['ome_filelist']
    _require(type(ome) is list and len(ome) == 4, 'Four indexed OME file records required.')
    for i in range(4):
        fact('ome_file.' + str(i), 'stored_image_metadata',
             'OME索引行' + str(i) + '：文件、维度与染料；不认定生物标记', 'inventory', '/ome_filelist/' + str(i))
    analyses = []
    supported = {'inspect_residuals', 'compare_policies', 'inspect_topography'}
    controls = {'pause', 'stop', 'investigate_data_mapping', 'investigate_target_definition',
                'investigate_feature_representation', 'recommend_stop_direction'}
    for collection in ('prior_diagnostics', 'actions'):
        rows = diagnostic[collection]
        _require(type(rows) is list and len(rows) <= 20, 'Diagnostic action scope exceeds bounds.')
        for index, action in enumerate(rows):
            _require(action['action'] in supported | controls, 'Unrecognized diagnostic tool scope.')
            if action['action'] in supported:
                analyses.append({'id': action['id'], 'action': action['action'],
                                 'pointer': '/' + collection + '/' + str(index)})
    fact('diagnostic_statistics_scope', 'host_tool_scope', '仅这些已执行诊断工具：没有p值检验',
         'diagnostic', '', {'analyses': analyses, 'statistical_tests_in_these_tools': [],
                            'scope': 'Only the saved applied diagnostic tools; model prose and unrelated studies are not statistical test evidence.'}, True)
    result = {'schema_version': SCHEMA,
              'source_snapshots': {name: {'file_sha256': hashlib.sha256(texts[name].encode('utf-8')).hexdigest(),
                                          'snapshot_sha256': doc.get('snapshot_sha256')}
                                   for name, doc in docs.items()},
              'source_payloads': copy.deepcopy(texts), 'facts': facts, 'tasks': _tasks(),
              'limitations': LIMITATIONS[:], 'scientific_validation': False}
    result['snapshot_sha256'] = fingerprint(result)
    return result


def build_catalog(diagnostic_directory, iteration_directory, baseline_directory, inventory_path):
    """Read sealed artifact contracts once, never load live studies or raw sources."""
    from .chemotopo_experiment_evidence import _safe_file
    from .chemotopo_publication import read_artifacts
    from .chemotopo_iteration_report import read_iteration_artifacts
    from .diagnostic_view import read_diagnostic_artifacts

    iteration_raw = _safe_file(Path(iteration_directory).absolute() / 'iteration.json', LIMITS['iteration'])
    baseline_raw = _safe_file(Path(baseline_directory).absolute() / 'research.json', LIMITS['baseline'])
    iteration = _decode(iteration_raw.decode('utf-8'), LIMITS['iteration'])
    baseline = _decode(baseline_raw.decode('utf-8'), LIMITS['baseline'])
    baseline_files = read_artifacts(baseline_directory, baseline)
    iteration_files = read_iteration_artifacts(iteration_directory, iteration)
    diagnostic_files = read_diagnostic_artifacts(diagnostic_directory, iteration)
    _require(baseline_files['research.json'] == baseline_raw
             and iteration_files['iteration.json'] == iteration_raw, 'Publication changed during catalog capture.')
    inventory_raw = _safe_file(Path(inventory_path).absolute(), LIMITS['inventory'])
    return _assemble({'diagnostic': diagnostic_files['diagnostic.json'].decode('utf-8'),
                      'iteration': iteration_raw.decode('utf-8'), 'baseline': baseline_raw.decode('utf-8'),
                      'inventory': inventory_raw.decode('utf-8')})


def validate_catalog(payload):
    """Rebuild pointer values and host templates, not just the outer hash."""
    try:
        _require(type(payload) is dict and payload.get('schema_version') == SCHEMA,
                 'Invalid catalog schema.')
        _require(_assemble(payload['source_payloads']) == payload,
                 'Catalog facts, source identities or host tasks changed.')
    except (KeyError, TypeError, IndexError, ValueError, RecursionError) as error:
        raise ResearchError('EVIDENCE_CHANGED', 'Malformed catalog evidence.') from error


def read_facts(catalog, ids):
    """Return exact requested facts in order; no free-text fact repair."""
    validate_catalog(catalog)
    _require(type(ids) is list and 1 <= len(ids) <= len(catalog['facts'])
             and all(type(i) is str for i in ids) and len(set(ids)) == len(ids),
             'Distinct known fact IDs required.')
    by_id = {fact['id']: fact for fact in catalog['facts']}
    _require(all(i in by_id for i in ids), 'Unknown catalog fact ID.')
    return copy.deepcopy([by_id[i] for i in ids])
