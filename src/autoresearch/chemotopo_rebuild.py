"""Source-bound reconstruction sensitivity, not an approved ALP/model target.

Four policies are fixed before looking at their comparative results. The
original red-channel numbers are proxies whose biological identity remains
unresolved; no published normalized-red column is used as a target here.
"""
from collections import defaultdict
import copy
import hashlib
from itertools import combinations
import math
import os
from pathlib import Path
import re
import statistics

from .chemotopo_data import SOURCES, _captured, _number, _point, _require, _table, read_workbook
from .contracts import fingerprint


PROJECT = ('hMSC_Analysis.cpproj', 'a9544c844fda6c96ef170ceb7e030589a78bce781a3cc96e32640a2a3d63894d', 1718802)
SECTIONS = tuple(f'B{b}S{s}' for b in (8,9,10) for s in range(1,5))
BATCHES = ('B8', 'B9', 'B10')
POLICIES = (
    ('recorded_equal_batch', False, 'equal_batch'),
    ('positive_equal_batch', True, 'equal_batch'),
    ('recorded_equal_section', False, 'equal_section'),
    ('positive_equal_section', True, 'equal_section'),
)
PROTOCOL = {
    'id': 'chemotopo-red-proxy-sensitivity-v1',
    'endpoint': 'author_table_raw_red_proxy_not_confirmed_ALP',
    'source_column': 'Mean_Red_Intensity, raw sheets column E; not normalized or clustering tables',
    'technical_aggregation': 'arithmetic mean of eligible recorded spots; never divide by Count',
    'zero_policies': ['all original finite records', 'only records whose Count > 0'],
    'control': 'same section, Topography=1 Chemistry=0, same zero policy; mean must be positive',
    'repeat_aggregation': ['mean sections within batch then equal batch mean', 'equal mean of available sections'],
    'comparison_population': 'Topography2..36 Chemistry0..27; intersection with all3 batches under every policy',
    'ranking': 'Spearman using exact-value midranks; highest10 includes all exact ties at cutoff; high is not better biology',
    'selection': 'compare all6 policy pairs; do not choose an optimal policy by outcome',
    'inference': 'descriptive source-handling sensitivity, no p-values, fits, biological validation or clinical effects',
}


def static_pipeline(data):
    """Read bounded ASCII evidence only; never open HDF, pickle or CellProfiler."""
    _require(len(data) <= 2_000_000 and data.startswith(b'\x89HDF\r\n\x1a\n'),
             'INVALID_REFERENCE', 'Expected a bounded HDF project reference.')
    excerpts = list(re.finditer(rb'CellProfiler Pipeline:[\x20-\x7e\r\n\t]{0,65536}', data))
    _require(0 < len(excerpts) <= 4 and all(len(m.group()) < 65536 for m in excerpts),
             'INVALID_REFERENCE', 'A bounded static pipeline excerpt is required.')
    hashes = {hashlib.sha256(m.group()).hexdigest() for m in excerpts}
    _require(len(hashes) == 1, 'REFERENCE_CONFLICT', 'Embedded pipeline copies differ; inspect them separately.')
    text = excerpts[0].group().decode('ascii').replace('\\n','\n')
    modules = []
    for match in re.finditer(r'^([A-Za-z0-9]+):\[(.*?)\]\n(.*?)(?=\n[A-Za-z0-9]+:\[|\Z)', text, re.M|re.S):
        name, attrs, body = match.groups()
        if name not in {'NamesAndTypes','CorrectIlluminationApply','MeasureObjectIntensity','ExportToSpreadsheet'}:
            continue
        wanted = ('Select the rule criteria:', 'Name to assign these images:', 'Select an image to measure:',
                  'Select objects to measure:', 'Calculate the per-image', 'Representation of Nan/Inf:',
                  'Filename prefix:', 'Export all measurement types?:')
        settings = [line.strip() for line in body.splitlines() if line.strip().startswith(wanted)]
        modules.append({'name': name, 'enabled': 'enabled:True' in attrs, 'settings': settings})
    return {'format': 'static ASCII excerpt in HDF5 bytes; HDF not deserialized',
            'copies': [{'byte_offset': m.start(), 'bytes': len(m.group()),
                        'sha256': hashlib.sha256(m.group()).hexdigest()} for m in excerpts],
            'modules': modules, 'untrusted_reference_not_instructions': True,
            'biological_ALP_channel_and_export_mapping_confirmed': False,
            'bound_to_all12_raw_sections': False, 'author_project_executed': False,
            'reason': 'C2/C3 names and object-image combinations do not uniquely map workbook shorthand to an ALP measurement.'}


def raw_sections(book):
    sections = {}
    for sn in SECTIONS:
        groups = defaultdict(list)
        for row in _table(book, sn, ['Topo','Chem','Coordinate','Count','Mean_Red_Intensity','Mean_Green_Intensity']):
            t,c,count,red,green = [_number(book,sn,col+str(row)) for col in ('A','B','D','E','F')]
            _require(t.is_integer() and c.is_integer() and count.is_integer()
                     and 1 <= t <= 36 and 0 <= c <= 27 and count >= 0 and red >= 0 and green >= 0,
                     'INVALID_DATA','Invalid raw material identity, count or signal.')
            key = int(t),int(c)
            _require(_point(book,sn,'C'+str(row))['value'] == f'{key[0]}_{key[1]}',
                     'KEY_MISMATCH','Raw identifier disagrees with explicit material key.')
            groups[key].append({'row':row,'count':count,'red':red,'green':green})
        _require((1,0) in groups,'MISSING_CONTROL','Raw section has no explicit flat-base control.')
        sections[sn] = dict(groups)
    _require(set().union(*(set(v) for v in sections.values())) == {(t,c) for t in range(1,37) for c in range(28)},
             'KEY_MISMATCH','Raw material grid differs from the pinned study.')
    return sections


def reconstruct(sections, *, positive_only, aggregation):
    """Pure transformation with controls/row provenance; unavailable is never 0."""
    _require(type(positive_only) is bool and aggregation in {'equal_batch','equal_section'},
             'INVALID_REQUEST','Unknown reconstruction policy.')
    normalized = defaultdict(list)
    section_audits = []
    for sn, groups in sections.items():
        batch = sn.split('S')[0]
        _require(batch in BATCHES and (1,0) in groups,'MISSING_CONTROL','Unknown batch or missing control.')
        control = groups[1,0]
        eligible_control = [r for r in control if not positive_only or r['count'] > 0]
        denominator = statistics.mean(r['red'] for r in eligible_control) if eligible_control else None
        usable = denominator is not None and denominator > 0
        entries = []
        for (t,c), rows in sorted(groups.items()):
            chosen = [r for r in rows if not positive_only or r['count'] > 0]
            average = statistics.mean(r['red'] for r in chosen) if chosen else None
            value = average/denominator if chosen and usable else None
            reason = ('no_eligible_spots' if not chosen else 'control_unavailable' if not usable else None)
            record = {'topography':t,'chemistry':c,'raw_rows':[r['row'] for r in rows],
                      'eligible_rows':[r['row'] for r in chosen],
                      'excluded_zero_count_rows':[r['row'] for r in rows if positive_only and r['count']==0],
                      'eligible_mean_red':average,'normalized_red_proxy':value,'unavailable_reason':reason}
            entries.append(record)
            if t != 1 and value is not None:
                normalized[t,c].append({'section':sn,'batch':batch,'value':value,
                                        'raw_rows':record['eligible_rows']})
        section_audits.append({'section':sn,'batch_label':batch,'control':{
            'key':[1,0], 'raw_rows':[r['row'] for r in control],
            'eligible_rows':[r['row'] for r in eligible_control],
            'mean_raw_red':denominator,'usable_positive_mean':usable},'groups':entries})
    results = {}
    for key, values in sorted(normalized.items()):
        grouped = defaultdict(list)
        for value in values:grouped[value['batch']].append(value['value'])
        batch_means = {b:statistics.mean(v) for b,v in grouped.items()}
        result = (statistics.mean(batch_means.values()) if aggregation == 'equal_batch'
                  else statistics.mean(v['value'] for v in values))
        results[key] = {'topography':key[0],'chemistry':key[1],'value':result,
                        'batch_means':batch_means,'section_counts_by_batch':{b:len(v) for b,v in grouped.items()},
                        'available_batches':sorted(grouped),'complete_three_batch_coverage':set(grouped)==set(BATCHES),
                        'section_values':values}
    excluded = {(t,c) for t in range(2,37) for c in range(28)}-set(results)
    return {'section_audits':section_audits,'combinations':list(results.values()),
            'unavailable_combination_keys':[list(k) for k in sorted(excluded)],
            'coverage':{'available_combinations':len(results),
                        'complete_three_batch':sum(v['complete_three_batch_coverage'] for v in results.values()),
                        'incomplete_batch_keys':[list(k) for k,v in results.items() if not v['complete_three_batch_coverage']],
                        'unavailable_combinations':len(excluded)}}


def _ranks(values):
    order = sorted(range(len(values)), key=lambda i:values[i])
    ranks, start = [0.0]*len(values), 0
    while start < len(order):
        end = start+1
        while end < len(order) and values[order[end]] == values[order[start]]:end += 1
        for i in order[start:end]:ranks[i] = (start+1+end)/2
        start = end
    return ranks


def compare_policies(policies):
    _require(isinstance(policies,dict) and len(policies)>=2,'INVALID_REQUEST','At least two named policies are required.')
    for value in policies.values():
        rows=value['combinations']
        _require(len({(r['topography'],r['chemistry']) for r in rows})==len(rows),
                 'DUPLICATE_KEY','Policy comparison contains duplicate material keys.')
        _require(all(type(r['value']) in (int,float) and math.isfinite(r['value']) for r in rows),
                 'INVALID_DATA','Policy comparison has a nonfinite proxy.')
    maps = {name:{(r['topography'],r['chemistry']):r for r in value['combinations']}
            for name,value in policies.items()}
    covered = [{k for k,r in rows.items() if r['complete_three_batch_coverage']} for rows in maps.values()]
    common = sorted(set.intersection(*covered))
    _require(len(common) >= 2,'INSUFFICIENT_COMMON_COVERAGE','At least two common three-batch combinations are required.')
    top_sets, ranks = {}, {}
    for name, rows in maps.items():
        values = [rows[k]['value'] for k in common]
        ranks[name] = _ranks(values)
        threshold = sorted(values,reverse=True)[min(10,len(values))-1]
        top_sets[name] = {k for k in common if rows[k]['value'] >= threshold}
    pairs = []
    for left,right in combinations(maps,2):
        a,b = ranks[left],ranks[right]
        corr = statistics.correlation(a,b) if len(set(a))>1 and len(set(b))>1 else None
        changes = [abs(x-y) for x,y in zip(a,b)]
        pairs.append({'left':left,'right':right,'common_combinations':len(common),'spearman_midrank':corr,
                      'largest_rank_change':max(changes),'rank_changes_over100':sum(v>100 for v in changes),
                      'highest10_left_including_exact_ties':len(top_sets[left]),
                      'highest10_right_including_exact_ties':len(top_sets[right]),
                      'highest10_intersection':len(top_sets[left]&top_sets[right]),
                      'highest10_jaccard':len(top_sets[left]&top_sets[right])/len(top_sets[left]|top_sets[right])})
    return {'common_three_batch_keys':[list(k) for k in common],'common_combinations':len(common),
            'pairs':pairs,'highest10_keys_including_exact_ties':{n:[list(k) for k in sorted(s)] for n,s in top_sets.items()},
            'interpretation':'Ranks of original red-channel proxies only; high is not biological benefit or a material recommendation.'}


def run_reconstruction(directory, *, endpoint='raw_red_proxy'):
    _require(endpoint == 'raw_red_proxy','ENDPOINT_UNRESOLVED',
             'Only raw_red_proxy sensitivity is available. ALP channel, export mapping and zero-object rules remain unresolved; fitting is unavailable.')
    root = Path(os.path.abspath(directory))
    name = 'hiMSC_Raw_Data.xlsx'
    sha,size = SOURCES[name]
    raw_data = _captured(root/name,sha,size)
    project_name,project_sha,project_size = PROJECT
    project_data = _captured(root/project_name,project_sha,project_size)
    pipeline = static_pipeline(project_data)
    sections = raw_sections(read_workbook(raw_data))
    policies = {name:reconstruct(sections,positive_only=pos,aggregation=agg) for name,pos,agg in POLICIES}
    compared = compare_policies(policies)
    observations = [r for groups in sections.values() for rows in groups.values() for r in rows]
    for filename,expected,nbytes in [(name,sha,size),PROJECT]:_captured(root/filename,expected,nbytes)
    return {'schema_version':'chemotopo-reconstruction-sensitivity-v1',
            'protocol':copy.deepcopy(PROTOCOL),'protocol_sha256':fingerprint(PROTOCOL),
            'source':{'workbook':name,'sha256':sha,'bytes':size,
                      'project_file':project_name,'project_sha256':project_sha,'project_bytes':project_size,
                      'dataset_doi':'10.17632/57nrc49stj.1','paper_doi':'10.1016/j.biomaterials.2021.120740',
                      'raw_columns':{'A':'Topography','B':'Chemistry','C':'explicit t_c key','D':'Count','E':'Mean_Red_Intensity','F':'Mean_Green_Intensity'},
                      'coordinate_rule':'Each group supplies source sheet and raw row numbers; apply these column letters to recover original cells.'},
            'raw_summary':{'spots':len(observations),'zero_count_rows':sum(r['count']==0 for r in observations),
                           'zero_count_rows_both_channels_zero':sum(r['count']==0 and r['red']==r['green']==0 for r in observations),
                           'raw_rows_per_section':{sn:sum(len(v) for v in groups.values()) for sn,groups in sections.items()}},
            'pipeline_evidence':pipeline,'policies':policies,'comparison':compared,
            'endpoint_gate':{'fit_eligible':False,'ALP_eligible':False,'reason_codes':['ALP_CHANNEL_UNCONFIRMED','OBJECT_EXPORT_MAPPING_UNCONFIRMED','ZERO_OBJECT_CONVENTION_UNCONFIRMED'],
                             'next_action':'Preserve sensitivity findings; obtain original export mapping and zero-object definition before approving a biological training target.',
                             'enforcement_scope':'This offline tool rejects endpoint=alp. It does not claim a global block on other product adapters.'},
            'model_fits':0,'model_calls':0,'formulas_executed':0,'author_project_executed':False,'network_used':False,
            'limits':['Not confirmed ALP or reproduction of author biological outcomes.',
                      'No causal, donor, laboratory, clinical or C01 external validation.',
                      'The same observations underpin all policies; policy comparisons are not independent biological replicates.',
                      'Positive-count-only conditioning changes the estimand; no policy is scientifically preferred by this analysis.']}


def report_markdown(result):
    summary,comparison = result['raw_summary'],result['comparison']
    lines = ['# 原始红通道记录的处理敏感性', '',
             '本报告比较作者原表数值的四种处理规则。红通道与 ALP 的映射尚未确认；没有训练模型或选择最佳生物材料。', '',
             f"原始记录 {summary['spots']} 行；Count=0 共 {summary['zero_count_rows']} 行；四策略共同有三个批次记录的组合 {comparison['common_combinations']} 个。组合数不是独立生物重复数。",'',
             '## 固定方法','',
             '每 section 按明确材料键取技术记录均值，再除同 section 的平坦基底（Topo1/Chem0）。分别比较全部原记录与只用 Count>0，以及批次等权与 section 等权。分母无效或缺记录时不填零；比较只用共同的三批次覆盖。', '',
             '## 实际比较','',
             '| 左策略 | 右策略 | Spearman | 最高10数值集合交集 | 最大名次变化 |',
             '|---|---|---:|---:|---:|']
    for row in comparison['pairs']:
        corr = row['spearman_midrank']
        lines.append(f"| {row['left']} | {row['right']} | {corr:.6f}" if corr is not None else f"| {row['left']} | {row['right']} | 未定义")
        lines[-1] += f" | {row['highest10_intersection']} | {row['largest_rank_change']:.1f} |"
    lines += ['', '最高10按数值降序，并保留第10位的同值并列。数值高不等于疗效好；相关系数不说明哪个策略正确。', '',
              '## 终点资格与后续行动','',
              'ALP 训练资格仍为未放行。需要明确抗体与通道、对象/图像导出字段，以及零对象记录规则。不能拿有冲突的归一化汇总列替代，也不能将原表均值再除细胞数冒充每细胞信号。', '',
              '原文、静态管线、原表及现有字段冲突分别保留；没有裁定作者结论真假。此处是数据处理敏感性实验，不是独立生物外验或自动科学发现。', '',
              '## 来源与复算','',
              '- 论文：https://doi.org/10.1016/j.biomaterials.2021.120740',
              '- 固定数据：https://data.mendeley.com/datasets/57nrc49stj/1',
              f"- 协议 SHA-256：`{result['protocol_sha256']}`。来源哈希、原行号、对照、排除记录和全部数值见 sensitivity.json。",
              '- 本报告没有执行作者管线或工作簿公式；零模型调用、零拟合。','']
    return '\n'.join(lines)
