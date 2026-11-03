"""Offline qualification of pinned ChemoTopoChip V1 author workbooks; no fitting.

The reader reuses C01's bounded ZIP/XML guards, never executes formulas, and
keeps cached values and exact cell identities. Qualification is not an adapter
that declares an ambiguous published column to be a biological endpoint.
"""
from collections import Counter, defaultdict
import hashlib
import lzma
import math
import os
from pathlib import Path, PurePosixPath
import re
import statistics
import zipfile
import zlib

from .archive_inventory import _regular, _stamp
from .c01 import C01Error, N, _safe_zip, _xml
from .contracts import ResearchError


SOURCES = {
    'hiMSC_Raw_Data.xlsx': ('690c8eaf745e817f99bd7f2910bb0339ac0dea3e2c8dc1df6aa2153b03c348fe', 1281702),
    'Macrophage_Raw_Data.xlsx': ('63d5b2bfbea9dace2fd582e02c8a3fab1ea93fe93c332fa50cde526d80694947', 1758608),
    'Modelling_Descriptors.xlsx': ('049e0cdb713ef182ba09f1dec7c956be56c8580d0d952dc23a030eaf5adcd066', 112840),
}
GEOMETRY_CANDIDATES = (
    'Perimeter_Area', 'Pattern_Count_Pattern', 'Pattern_Area_mean',
    'Pattern_Perimeter_mean', 'Pattern_Compactness_mean', 'Pattern_Eccentricity_mean',
    'Pattern_FormFactor_mean', 'Pattern_MajorAxisLength_mean',
    'Pattern_MinorAxisLength_mean', 'Pattern_Solidity_mean',
)
REL = '{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id'


def _require(ok, code, message):
    if not ok: raise ResearchError(code, message)


def _close(a, b):
    return (type(a) in (int, float) and type(b) in (int, float)
            and math.isfinite(a) and math.isfinite(b)
            and math.isclose(a, b, rel_tol=1e-10, abs_tol=1e-12))


def _column(number):
    text = ''
    while number:
        number, rem = divmod(number - 1, 26)
        text = chr(65 + rem) + text
    return text


def read_workbook(data):
    """Return cell caches, not evaluated expressions; bounded OOXML only."""
    try:
        with _safe_zip(data, nested=True) as archive:
            names = set(archive.namelist())
            _require(not any('vbaproject' in n.lower() or n.startswith('xl/externalLinks/') for n in names),
                     'UNSUPPORTED_WORKBOOK', 'Macros and external workbook links are not accepted.')
            shared = []
            if 'xl/sharedStrings.xml' in names:
                shared = [''.join(t.text or '' for t in item.findall('.//s:t', N))
                          for item in _xml(archive.read('xl/sharedStrings.xml')).findall('s:si', N)]
            rels = _xml(archive.read('xl/_rels/workbook.xml.rels'))
            relationships = {}
            for rel in rels:
                rid = rel.get('Id')
                _require(rid and rid not in relationships and rel.get('TargetMode') != 'External',
                         'INVALID_WORKBOOK', 'Workbook relationships are duplicate or external.')
                relationships[rid] = rel.get('Target', '')
            book = _xml(archive.read('xl/workbook.xml'))
            tables, total = {}, 0
            for sheet in book.findall('s:sheets/s:sheet', N):
                name, target = sheet.get('name'), relationships.get(sheet.get(REL), '')
                member = target.lstrip('/') if target.startswith('/xl/') else 'xl/' + target
                _require(name and name not in tables and len(tables) < 50 and target
                         and '..' not in PurePosixPath(member).parts and '\\' not in member
                         and ':' not in member and member in names,
                         'INVALID_WORKBOOK', 'Sheet identity or relationship is unsafe.')
                cells = {}
                for cell in _xml(archive.read(member)).findall('s:sheetData/s:row/s:c', N):
                    ref, kind = cell.get('r', ''), cell.get('t', 'n')
                    match = re.fullmatch(r'([A-Z]{1,3})([1-9][0-9]{0,4})', ref)
                    _require(match and int(match[2]) <= 5000 and ref not in cells
                             and len(cells) < 50000 and total < 250000,
                             'INVALID_WORKBOOK', 'Cell reference is duplicate, invalid or exceeds limits.')
                    vnode, fnode = cell.find('s:v', N), cell.find('s:f', N)
                    raw = vnode.text or '' if vnode is not None else ''
                    value, status = None, 'missing'
                    if kind == 's':
                        _require(re.fullmatch(r'[0-9]+', raw) and int(raw) < len(shared),
                                 'INVALID_WORKBOOK', 'Invalid shared-string index.')
                        value, status = shared[int(raw)], 'text'
                    elif kind == 'inlineStr':
                        value, status = ''.join(t.text or '' for t in cell.findall('s:is//s:t', N)), 'text'
                    elif kind == 'n' and raw != '':
                        try: value = float(raw)
                        except ValueError: value = None
                        if value is not None and math.isfinite(value): status = 'finite'
                        else: value, status = None, 'nonfinite_or_invalid'
                    elif raw:
                        value, status = raw, 'non_numeric'
                    cells[ref] = {'value': value, 'raw': raw, 'status': status,
                                  'formula_present': fnode is not None,
                                  'formula': fnode.text if fnode is not None else None}
                    total += 1
                tables[name] = cells
            _require(tables, 'INVALID_WORKBOOK', 'Workbook has no readable sheets.')
            return tables
    except C01Error as error:
        raise ResearchError(error.code, str(error)) from None
    except (KeyError, OSError, zipfile.BadZipFile, RuntimeError, NotImplementedError, zlib.error, lzma.LZMAError, EOFError):
        raise ResearchError('INVALID_WORKBOOK', 'Workbook package is incomplete or unreadable.') from None


def _point(book, sheet, ref):
    cell = book[sheet].get(ref, {'value': None, 'raw': '', 'status': 'missing',
                                'formula_present': False, 'formula': None})
    return {'sheet': sheet, 'cell': ref, **cell}


def _number(book, sheet, ref):
    point = _point(book, sheet, ref)
    _require(point['status'] == 'finite', 'INVALID_DATA', f'Expected finite numeric cache: {sheet}!{ref}')
    return point['value']


def _table(book, sheet, headers):
    _require(sheet in book, 'SCHEMA_MISMATCH', f'Missing sheet: {sheet}')
    for col, header in enumerate(headers, 1):
        _require(book[sheet].get(_column(col)+'1', {}).get('value') == header,
                 'SCHEMA_MISMATCH', f'Unexpected header: {sheet}!{_column(col)}1')
    rows = sorted({int(re.search(r'[0-9]+$', ref)[0]) for ref, cell in book[sheet].items()
                   if cell['status'] != 'missing'} - {1})
    return rows


def _keys(book, sheet, headers, topo='A', chem='B', label=None):
    keyed = {}
    for row in _table(book, sheet, headers):
        t, c = _number(book, sheet, topo+str(row)), _number(book, sheet, chem+str(row))
        _require(t.is_integer() and c.is_integer() and 1 <= t <= 36 and 0 <= c <= 28,
                 'INVALID_DATA', f'Invalid material identity: {sheet}!{row}')
        key = int(t), int(c)
        _require(key not in keyed, 'DUPLICATE_KEY', f'Duplicate material identity: {sheet}!{row}')
        if label:
            _require(_point(book, sheet, label+str(row))['value'] == f'{key[0]}_{key[1]}',
                     'KEY_MISMATCH', f'Text identifier disagrees with numeric identity: {sheet}!{row}')
        keyed[key] = row
    return keyed


def audit_sections(book, sections, *, himsc):
    """Recompute raw means/SD and test candidate denominators without choosing one."""
    reports, normalized = [], {}
    for section in sections:
        raw_headers = (['Topo', 'Chem', 'Coordinate', 'Count', 'Mean_Red_Intensity', 'Mean_Green_Intensity']
                       if himsc else ['Topography', 'Chemistry', 'Topo_Chem', 'Cell_Count', '546_MFI', '647_MFI', 'M2/M1_Ratio'])
        groups = defaultdict(list)
        for row in _table(book, section, raw_headers):
            t, c = _number(book, section, 'A'+str(row)), _number(book, section, 'B'+str(row))
            _require(t.is_integer() and c.is_integer() and 1 <= t <= 36 and 0 <= c <= 28,
                     'INVALID_DATA', 'Invalid raw material identity.')
            key = int(t), int(c)
            _require(_point(book, section, 'C'+str(row))['value'] == f'{key[0]}_{key[1]}',
                     'KEY_MISMATCH', 'Raw text identifier disagrees with material identity.')
            groups[key].append(row)
        sn = section+'_SNR'
        nn = section+'_Normalised'
        response = 'Red Intensity' if himsc else 'M2M1'
        snr = _keys(book, sn, ['Topography', 'Chemistry', 'Topo_Chem', 'Avg Cell Count',
                              'Std Cell Count', 'SNR Cell Count', 'Avg '+response,
                              'Std '+response, 'SNR '+response], label='C')
        norm = _keys(book, nn, ['Topography', 'Chemistry', 'Topo_Chem', 'Avg Cell Count', 'Avg '+response], label='C')
        _require(set(groups) == set(snr) == set(norm) and (1, 0) in snr,
                 'KEY_MISMATCH', 'Raw, SNR, normalized or flat-base keys disagree.')
        _require(all((1,c) in snr for _,c in snr), 'KEY_MISMATCH', 'A chemistry has no explicit flat control.')
        stats, records = Counter(), []
        base = snr[1, 0]
        for key, raw_rows in sorted(groups.items()):
            sr, nr = snr[key], norm[key]
            count = [_number(book, section, 'D'+str(r)) for r in raw_rows]
            signal_points = [_point(book, section, ('E' if himsc else 'G')+str(r)) for r in raw_rows]
            signal = [p['value'] for p in signal_points if p['status'] == 'finite']
            if not himsc:
                for row in raw_rows:
                    numerator, denominator = (_point(book, section, col+str(row)) for col in ('F','E'))
                    ratio = _point(book, section, 'G'+str(row))
                    if numerator['status'] == denominator['status'] == ratio['status'] == 'finite' and denominator['value'] != 0:
                        stats['raw_ratio_comparable_rows'] += 1
                        stats['raw_ratio_F_over_E_matches'] += _close(numerator['value']/denominator['value'], ratio['value'])
                    else:
                        stats['raw_ratio_not_comparable_rows'] += 1
            _require(len(raw_rows) >= 2, 'INVALID_DATA', 'Technical SD needs at least two recorded spots.')
            stats['keys'] += 1
            stats['raw_rows'] += len(raw_rows)
            stats['zero_count_rows'] += count.count(0)
            stats['raw_mean_count_matches_snr'] += _close(statistics.mean(count), _number(book, sn, 'D'+str(sr)))
            stats['raw_sd_count_matches_snr'] += _close(statistics.stdev(count), _number(book, sn, 'E'+str(sr)))
            stats['raw_signal_nonfinite_or_missing_rows'] += len(signal_points)-len(signal)
            stats['raw_mean_signal_matches_snr'] += _close(statistics.mean(signal) if signal else None, _number(book, sn, 'G'+str(sr)))
            stats['raw_sd_signal_matches_snr'] += _close(statistics.stdev(signal) if len(signal) >= 2 else None, _number(book, sn, 'H'+str(sr)))
            actual = _number(book, nn, 'E'+str(nr))
            signal_avg = _number(book, sn, 'G'+str(sr))
            count_sd = _number(book, sn, 'E'+str(sr))
            candidates = {
                'signal_mean_over_flat_base_signal_mean': (signal_avg, 'G'+str(base)),
                'count_sd_over_flat_base_count_sd': (count_sd, 'E'+str(base)),
                'signal_mean_over_same_chemistry_flat_signal_mean': (signal_avg, 'G'+str(snr[1, key[1]])),
            }
            comparisons = {}
            for candidate, (num, denominator_ref) in candidates.items():
                den = _number(book, sn, denominator_ref)
                expected = num/den if den != 0 else None
                match = _close(expected, actual)
                stats[candidate+'_matches'] += match
                stats[candidate+'_zero_denominators'] += den == 0
                comparisons[candidate] = {'expected': expected, 'matches': match,
                                          'denominator': _point(book, sn, denominator_ref)}
            stats['count_unchanged_matches'] += _close(_number(book, sn, 'D'+str(sr)), _number(book, nn, 'D'+str(nr)))
            records.append({'topography': key[0], 'chemistry': key[1], 'raw_rows': raw_rows,
                            'raw_count_column': 'D', 'raw_signal_column': 'E' if himsc else 'G',
                            'raw_signal_nonfinite_or_missing': [p for p in signal_points if p['status'] != 'finite'],
                            'snr_mean_signal': _point(book, sn, 'G'+str(sr)),
                            'snr_sd_count': _point(book, sn, 'E'+str(sr)),
                            'normalized_labeled_signal': _point(book, nn, 'E'+str(nr)),
                            'candidate_comparisons': comparisons})
        reports.append({'section': section, 'batch_label_not_proven_donor': section.split('S')[0],
                        'technical_rows_per_key': dict(sorted(Counter(len(v) for v in groups.values()).items())),
                        'checks': dict(stats), 'records': records})
        normalized[section] = norm
    return reports, normalized


def audit_aggregate(book, normalized, *, himsc):
    columns = ('B', 'C') if himsc else ('A', 'B')
    headers = (['Topo_Chem', 'Polymer', 'Topography', 'Chemistry', 'AVG Cell Count', 'STD Cell Count',
                'SNR Cell Count', 'AVG Red Intensity', 'STD Red Intensity', 'SNR Red Intensity']
               if himsc else ['Polymer', 'Topography', 'Chemistry', 'AVG Cell Count', 'STD Cell Count',
                              'SNR Cell Count', 'AVG M2M1', 'STD M2M1', 'SNR M2M1'])
    cluster = _keys(book, 'DataForClustering', headers, topo='C' if himsc else 'B',
                    chem='D' if himsc else 'C', label='A' if himsc else None)
    reports, records = [], {}
    for sheet, norm_col, avg_col, sd_col in [('CellCountAllBatches', 'D', 'E' if himsc else 'D', 'F' if himsc else 'E'),
        ('RedIntensityAllBatches' if himsc else 'M2M1AllBatches', 'E', 'H' if himsc else 'G', 'I' if himsc else 'H')]:
        sections = list(normalized)
        allrows = _keys(book, sheet, ['Topo_Chem', 'Topography', 'Chemistry', *sections], topo='B', chem='C', label='A')
        _require(set(cluster) <= set(allrows), 'KEY_MISMATCH', 'Aggregate contains keys absent from batch table.')
        checks, row_reports = Counter(), []
        for key, row in sorted(allrows.items()):
            vals, batch_values, points = [], defaultdict(list), []
            for col, section in enumerate(sections, 4):
                ref = _column(col)+str(row)
                point = _point(book, sheet, ref)
                sr = normalized[section].get(key)
                if sr is None:
                    _require(point['status'] == 'missing', 'KEY_MISMATCH', 'Nonempty batch cell has no normalized source.')
                    checks['structural_absence_cells'] += 1
                    continue
                value = _number(book, sheet, ref)
                checks['mapped_cells'] += 1
                checks['mapped_equal'] += _close(value, _number(book, section+'_Normalised', norm_col+str(sr)))
                vals.append(value)
                batch_values[section.split('S')[0]].append(value)
                points.append({'section': section, 'source': point,
                               'normalized_source': _point(book, section+'_Normalised', norm_col+str(sr))})
            if key not in cluster: continue
            _require(vals, 'INVALID_DATA', 'Aggregate key has no finite observed sections.')
            cr = cluster[key]
            checks['aggregate_rows'] += 1
            checks['mean_matches'] += _close(statistics.mean(vals), _number(book, 'DataForClustering', avg_col+str(cr)))
            checks['sd_matches'] += len(vals) >= 2 and _close(statistics.stdev(vals), _number(book, 'DataForClustering', sd_col+str(cr)))
            batch_means = [statistics.mean(v) for v in batch_values.values()]
            checks['equal_batch_mean_matches'] += _close(statistics.mean(batch_means), _number(book, 'DataForClustering', avg_col+str(cr)))
            row_reports.append({'topography': key[0], 'chemistry': key[1],
                                'available_sections_by_batch': {k: len(v) for k,v in batch_values.items()},
                                'observed_section_mean': statistics.mean(vals),
                                'equal_batch_mean': statistics.mean(batch_means), 'sources': points})
            records.setdefault(key, {})[sheet] = {'mean': _point(book, 'DataForClustering', avg_col+str(cr)),
                                                 'sd': _point(book, 'DataForClustering', sd_col+str(cr)),
                                                 'available_sections_by_batch': {k: len(v) for k,v in batch_values.items()}}
        reports.append({'sheet': sheet, 'checks': dict(checks), 'rows': row_reports,
                        'keys_excluded_from_clustering': [list(k) for k in sorted(set(allrows)-set(cluster))]})
    polymers = {k: _point(book, 'DataForClustering', columns[0]+str(row))['value'] for k,row in cluster.items()}
    return cluster, polymers, reports, records


def _captured(path, sha, size):
    before = _regular(path)
    _require(before.st_size == size, 'SOURCE_CHANGED', 'Workbook size differs from pinned author version.')
    with path.open('rb') as stream:
        _require(_stamp(os.fstat(stream.fileno())) == _stamp(before), 'SOURCE_CHANGED', 'File changed before reading.')
        data = stream.read(size+1)
        _require(len(data) == size and hashlib.sha256(data).hexdigest() == sha
                 and _stamp(os.fstat(stream.fileno())) == _stamp(before)
                 and _stamp(_regular(path)) == _stamp(before), 'SOURCE_CHANGED', 'Workbook differs from pinned author version.')
    return data


def inspect_chemotopo(directory):
    root = Path(os.path.abspath(directory))
    books, manifests = {}, []
    for name, (sha, size) in SOURCES.items():
        books[name] = read_workbook(_captured(root/name, sha, size))
        manifests.append({'file': name, 'sha256': sha, 'bytes': size,
                          'sheets': [{'name': sn, 'cell_count': len(cells),
                                      'formula_cache_cells': sum(c['formula_present'] for c in cells.values()),
                                      'status_counts': dict(Counter(c['status'] for c in cells.values())),
                                      'headers': {r:c['value'] for r,c in cells.items() if re.fullmatch('[A-Z]+1', r)}}
                                     for sn,cells in books[name].items()]})
    hm, mp = books['hiMSC_Raw_Data.xlsx'], books['Macrophage_Raw_Data.xlsx']
    hs = [f'B{b}S{s}' for b in (8,9,10) for s in range(1,5)]
    ms = [f'B{b}S{s}' for b in (4,6) for s in range(1,5)]
    hsections, hn = audit_sections(hm, hs, himsc=True)
    msections, mn = audit_sections(mp, ms, himsc=False)
    hk, hp, ha, hr = audit_aggregate(hm, hn, himsc=True)
    mk, mpnames, ma, mr = audit_aggregate(mp, mn, himsc=False)
    _require(set(hk) == set(mk), 'KEY_MISMATCH', 'Cell assays have unmatched aggregate keys.')
    expected = {(t,c) for t in range(2,37) for c in range(28)}
    _require(set(hk) == expected and all(hp[k] == mpnames[k] for k in hk),
             'KEY_MISMATCH', 'Assay material grid or explicit polymer mapping changed.')
    db = books['Modelling_Descriptors.xlsx']
    rows = _table(db, 'Sheet1', ['Topography'])
    descriptors, ids = [], set()
    for row in rows:
        t = _number(db, 'Sheet1', 'A'+str(row))
        _require(t.is_integer() and int(t) not in ids, 'DUPLICATE_KEY', 'Duplicate/invalid descriptor topography.')
        ids.add(int(t))
    _require(ids == set(range(2,37)), 'KEY_MISMATCH', 'Descriptor topography keys differ from biological grid.')
    descriptor_columns = sorted([ref[:-1] for ref in db['Sheet1'] if re.fullmatch('[A-Z]+1', ref) and ref != 'A1'], key=lambda s:(len(s),s))
    names = [_point(db, 'Sheet1', c+'1')['value'] for c in descriptor_columns]
    _require(len(names) == len(set(names)) and set(GEOMETRY_CANDIDATES) <= set(names),
             'SCHEMA_MISMATCH', 'Descriptor names are duplicate or candidate geometry is missing.')
    for col in descriptor_columns:
        values = [_number(db, 'Sheet1', col+str(r)) for r in rows]
        header = _point(db, 'Sheet1', col+'1')['value']
        descriptors.append({'header': header, 'column': col, 'constant': len(set(values)) == 1,
                            'candidate_material_feature': header in GEOMETRY_CANDIDATES,
                            'values': [{'topography': int(_number(db,'Sheet1','A'+str(r))),
                                        'source': _point(db,'Sheet1',col+str(r))} for r in rows]})
    for name, (sha, size) in SOURCES.items(): _captured(root/name, sha, size)
    conflict = all(r['checks']['count_sd_over_flat_base_count_sd_matches'] == r['checks']['keys'] for r in hsections)
    problems = [
        {'code': 'HIMSC_ENDPOINT_ROLE_CONFLICT', 'observed': conflict,
         'message': 'The column labeled normalized Avg Red Intensity matches cell-count SD / flat-base cell-count SD. This does not establish ALP signal identity or the direction of a possible label/copy error.'},
        {'code': 'METHODS_NORMALIZATION_AND_TIME_CONFLICT', 'observed': True,
         'message': 'Paper normalization descriptions differ; macrophage culture is described as both day6 and day9. Published workbook cache matches are arithmetic checks, not an adjudication.'},
        {'code': 'UNEQUAL_REPEAT_COVERAGE', 'observed': True,
         'message': 'Section/batch coverage is unequal. B labels are not individually verified donors. Technical spots, repeated sections and cell assays are not independent materials.'},
        {'code': 'DESCRIPTOR_SELECTION_UNRESOLVED', 'observed': True,
         'message': 'Author workbook contains 243 descriptors; paper describes 65. The ten geometry candidates are prospective, not selected by response scores.'},
    ]
    return {'schema_version': 'chemotopo-qualification-v1',
            'source_version': '10.17632/57nrc49stj.1', 'source_license': 'CC BY 4.0 (repository metadata)',
            'paper_doi': '10.1016/j.biomaterials.2021.120740', 'paper_cited_dataset': '10.17639/nott.7080',
            'qualification': 'pending_endpoint_and_protocol_review', 'scientific_validation': False,
            'model_fits': 0, 'model_calls': 0, 'network_used': False, 'formulas_executed': 0,
            'workbooks': manifests, 'join': {'matched_combinations': len(hk), 'topographies': len(ids),
                                            'chemistries_including_base': 28, 'unmatched_assay_keys': [],
                                            'descriptor_ids': sorted(ids)},
            'combinations': [{'topography': t, 'chemistry': c, 'polymer': hp[t,c],
                              'group_for_unseen_topography': t, 'himsc_reported': hr[t,c],
                              'macrophage_reported': mr[t,c]} for t,c in sorted(hk)],
            'himsc_sections': hsections, 'macrophage_sections': msections,
            'himsc_aggregation': ha, 'macrophage_aggregation': ma, 'descriptors': descriptors,
            'issues': problems,
            'next_protocol': {'status': 'not_executed_not_blind', 'question': 'Known chemistries on held-out topographies under fixed hiMSC culture conditions',
                              'target': 'Unresolved; do not use the published normalized-red aggregate as ALP',
                              'group': 'All chemistry combinations and repeats of a topography stay in the same fold',
                              'candidate_geometry': list(GEOMETRY_CANDIDATES),
                              'forbidden_predictors': ['biological responses', 'cell-count SD', 'SNR', 'batch/spot location treated as material geometry'],
                              'scope': 'Independent workflow case; not C01 external biological validation, new chemistry extrapolation or clinical efficacy'}}
