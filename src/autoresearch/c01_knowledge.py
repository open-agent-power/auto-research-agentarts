"""C01 primary-source index from the already audited author snapshot.

No model, network, formula execution, source rewriting or evaluator changes.
Paper text is a verbatim prefix before the References section; original bytes,
line coordinates and raw SHA remain distinct from the indexed text projection.
"""
import hashlib
import json
from pathlib import Path

from .c01_source_audit import audit_sources, _read, _load, DATASET_URL
from .contracts import ResearchError
from .knowledge import build_index


PAGES = {
    'mendeley-v1.md': {'url': DATASET_URL, 'doi': '10.17632/tt7gwkpck8.1',
        'title': 'C01 TNZST author dataset V1: primary data record', 'kind': 'reuse_note',
        'role': 'primary_author_dataset_page', 'scope': 'Dataset metadata; not a paper or independent validation.'},
    'paper-2023.md': {'url': 'https://www.sciencedirect.com/science/article/pii/S2772950823002959',
        'doi': '10.1016/j.bioadv.2023.213572', 'title': 'C01 TNZST 2023 primary paper: alloy and osteoblast methods',
        'kind': 'research_paper', 'role': 'primary_case_paper',
        'scope': 'C01 source methods. Workbook units, batch mapping and independent validation remain unresolved.'},
    'paper-2021.md': {'url': 'https://www.sciencedirect.com/science/article/pii/S1751616121004963',
        'doi': '10.1016/j.jmbbm.2021.104858', 'title': 'Related 2021 primary paper: different alloy and cell protocol',
        'kind': 'research_paper', 'role': 'primary_related_paper_not_c01_holdout',
        'scope': 'Related literature; different substrates/process/cell conditions, not eight independent C01 validation samples.'},
}


def article_prefix(text):
    lines = text.splitlines(keepends=True)
    boundaries = [i for i,line in enumerate(lines) if line.strip() == '## References']
    if len(boundaries) != 1 or not any(line.startswith('## ') and 'Conclusions' in line for line in lines[:boundaries[0]]):
        raise ResearchError('SOURCE_STRUCTURE_CHANGED', 'paper requires one explicit References boundary after Conclusions; do not guess article range')
    boundary = boundaries[0]
    return ''.join(lines[:boundary]), boundary


def collect_case_sources(archive, snapshot):
    root = Path(snapshot).absolute()
    audit = audit_sources(archive, root)
    if not audit['all_five_attachments_byte_equal']:
        raise ResearchError('SOURCE_CHANGED', 'C01 case sources require all five author attachments to match the original public archive')
    manifest_bytes = _read(root/'manifest.json', 65536)
    if hashlib.sha256(manifest_bytes).hexdigest() != audit['snapshot_manifest_sha256']:
        raise ResearchError('SOURCE_CHANGED', 'source manifest changed after byte audit')
    manifest = _load(manifest_bytes)
    checked = {page['name']: page for page in audit['pages']}
    if set(checked) != set(PAGES):
        raise ResearchError('SOURCE_CHANGED', 'case index requires the reviewed dataset and both primary paper pages')
    documents = []
    for name, specification in PAGES.items():
        record = checked[name]
        payload = _read(root/name, 2_000_000)
        if (record['url'] != specification['url'] or hashlib.sha256(payload).hexdigest() != record['sha256']
                or len(payload) != record['bytes']):
            raise ResearchError('SOURCE_CHANGED', 'primary source bytes or URL differ from the checked snapshot')
        text = payload.decode('utf-8')
        is_paper = specification['kind'] == 'research_paper'
        indexed_text, last_line = article_prefix(text) if is_paper else (text, len(text.splitlines()))
        documents.append({'id': 'c01-primary-'+name.removesuffix('.md')+'-body-v1', 'title': specification['title'],
            'kind': specification['kind'], 'source_url': specification['url'],
            'path': '08-c01-tnzst/source-verification/'+root.name+'/'+name,
            'sha256': record['sha256'], 'snapshot': manifest['fetched_at_utc'], 'text': indexed_text, 'page': None,
            'review_status': 'captured_primary_bytes_checked_not_scientific_approval',
            'metadata': {'doi': specification['doi'], 'source_role': specification['role'],
                'applicability': specification['scope'],
                'representation': 'verbatim captured-page prefix before References; header/navigation retained' if is_paper else 'verbatim author dataset page',
                'source_line_start': 1, 'source_line_end': last_line, 'raw_source_bytes': len(payload),
                'projection_version': 'article-prefix-v1' if is_paper else 'full-dataset-page-v1',
                'title_role': 'operator catalogue label, not a substituted publisher quotation',
                'dataset_license': manifest['dataset_license'] if name == 'mendeley-v1.md' else None,
                'paper_license': 'not inferred from dataset license', 'source_manifest_sha256': audit['snapshot_manifest_sha256'],
                'text_filtering': is_paper, 'manual_protocol_review_included': False}})
    return documents, audit


def build_case_index(archive, snapshot, output):
    output = Path(output).absolute()
    for path in (output, *output.parents):
        if path.is_symlink() or getattr(path,'is_junction',lambda:False)():
            raise ResearchError('UNSAFE_PATH', 'case index output cannot redirect')
    if output.exists(): raise ResearchError('ALREADY_EXISTS', 'preserve previous indexes and studies; use a new output')
    documents, audit = collect_case_sources(archive, snapshot)
    output.mkdir(parents=True)
    manifest = build_index(documents, output/'knowledge.sqlite', audit={
        'scope': 'C01 case primary sources only; global technology corpus remains separate',
        'source_manifest_sha256': audit['snapshot_manifest_sha256'], 'archive_sha256': audit['archive_sha256'],
        'all_five_author_files_byte_equal': True, 'scientific_validation': False,
        'source_bytes_unchanged': True, 'indexed_text_projection': 'article-prefix-v1; raw pages retained separately',
        'network_used': False, 'fits_performed': 0,
        'limits': ['Primary bytes are captured web representations, not authenticated signatures.',
            '2021 paper is related literature, not a compatible independent C01 matrix.',
            'Text indexing does not resolve figure-only discrepancies or workbook calibration.',
            'No manual stop decision is injected; source suggestions are untrusted reference text.']})
    (output/'source-audit.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return manifest
