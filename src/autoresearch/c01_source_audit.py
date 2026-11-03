"""Offline byte/provenance audit against an operator-captured author snapshot.

No downloads, formulas, fits or scientific compatibility decisions are executed.
The snapshot's web provenance is an operator record, not an authenticated signature.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import stat

from . import c01
from .contracts import ResearchError


DATASET_URL = 'https://data.mendeley.com/datasets/tt7gwkpck8/1'
FILE_IDS = {
    c01.MAIN: '315caad2-91d0-4656-8a32-50fa968569a8',
    c01.BIO: 'ca338618-b0de-4b9b-a411-0b6172efbad3',
    'TNZST_SFE calculation ver 3.xlsx': '540ac025-6957-4c04-bde8-36adf37a28a5',
    'TNZST_XRD.xlsx': 'f13d5fef-1997-4606-a209-8caa874fe6b2',
    'TNZST_Eng_Stress_vs_Eng_Strain.csv': 'ef8a0924-39ec-4f5e-8bb2-28c630ee2507',
}


def file_url(name):
    return 'https://data.mendeley.com/public-files/datasets/tt7gwkpck8/files/' + FILE_IDS[name] + '/file_downloaded'


def _require(condition, message, code='INVALID_SOURCE_MANIFEST'):
    if not condition: raise ResearchError(code, message)


def _read(path, limit):
    path = Path(os.path.abspath(path))
    for item in (path, *path.parents):
        _require(not item.is_symlink() and not getattr(item, 'is_junction', lambda: False)(),
                 'source audit cannot cross redirected paths', 'UNSAFE_PATH')
    metadata = path.stat()
    _require(stat.S_ISREG(metadata.st_mode) and metadata.st_nlink == 1,
             'source audit requires an unshared regular file', 'UNSAFE_PATH')
    _require(metadata.st_size <= limit, 'source audit file exceeds its byte cap', 'SOURCE_TOO_LARGE')
    with path.open('rb') as stream: payload = stream.read(limit + 1)
    _require(len(payload) <= limit, 'source audit file exceeds its byte cap', 'SOURCE_TOO_LARGE')
    return payload


def _load(payload):
    def unique(pairs):
        value = {}
        for key, item in pairs:
            _require(key not in value, 'duplicate source manifest field')
            value[key] = item
        return value
    def invalid(_): raise ResearchError('INVALID_SOURCE_MANIFEST', 'nonfinite source manifest')
    try:
        return json.loads(payload.decode('utf-8-sig'), object_pairs_hook=unique, parse_constant=invalid)
    except (ValueError, RecursionError):
        raise ResearchError('INVALID_SOURCE_MANIFEST', 'source manifest must be bounded valid JSON') from None


def audit_sources(archive, snapshot):
    """Check captured bytes; never turn matching files into a scientific approval."""
    root = Path(snapshot).absolute()
    manifest_bytes = _read(root / 'manifest.json', 65536)
    manifest = _load(manifest_bytes)
    _require(type(manifest) is dict and manifest.get('schema_version') == 'c01-upstream-snapshot-v1'
             and manifest.get('dataset_url') == DATASET_URL and manifest.get('dataset_doi') == c01.DOI
             and type(manifest.get('dataset_version')) is int and manifest['dataset_version'] == 1,
             'require the specific C01 author dataset V1 snapshot')
    _require(type(manifest.get('fetched_at_utc')) is str and manifest['fetched_at_utc']
             and manifest.get('dataset_license') == 'CC BY 4.0' and type(manifest.get('license_check')) is str,
             'keep capture time and manually checked license provenance')
    records = manifest.get('files')
    _require(type(records) is list and len(records) == 5 and all(type(row) is dict for row in records),
             'require exactly five upstream attachment records')
    names = [row.get('name') for row in records]
    _require(all(type(name) is str for name in names) and set(names) == set(FILE_IDS),
             'upstream attachment names must match the fixed five-file inventory')
    pages = manifest.get('pages')
    _require(type(pages) is list and 1 <= len(pages) <= 8 and all(type(page) is dict for page in pages),
             'require captured source pages')
    page_names = [page.get('name') for page in pages]
    _require(all(type(name) is str and re.fullmatch(r'[A-Za-z0-9_-]+\.md', name) for name in page_names)
             and len(set(page_names)) == len(page_names) and 'mendeley-v1.md' in page_names,
             'source page names must be distinct local markdown basenames')
    archive_capture = _read(archive, 8_000_000)
    bundle = c01.load_archive(archive)  # Original archive identity, safe ZIP/XML and cached values.
    _require(bundle['archive'] == archive_capture, 'archive changed while checking its provenance', 'SOURCE_CHANGED')
    official, comparison = {}, []
    for row in records:
        name = row['name']
        _require(row.get('url') == file_url(name), 'source file URL differs from the captured official inventory')
        payload = _read(root / name, 8_000_000)
        digest = hashlib.sha256(payload).hexdigest()
        _require(type(row.get('bytes')) is int and row['bytes'] == len(payload) and row.get('sha256') == digest,
                 'captured source file no longer matches its receipt', 'SOURCE_CHANGED')
        archived = bundle['files'][name]
        official[name] = payload
        comparison.append({'name': name, 'url': row['url'], 'upstream_bytes': len(payload), 'upstream_sha256': digest,
                           'archive_bytes': len(archived), 'archive_sha256': hashlib.sha256(archived).hexdigest(),
                           'byte_equal': payload == archived})
    checked_pages = []
    for page in pages:
        payload = _read(root / page['name'], 2_000_000)
        digest = hashlib.sha256(payload).hexdigest()
        _require(type(page.get('bytes')) is int and len(payload) == page['bytes'] and digest == page.get('sha256'),
                 'source page snapshot no longer matches its receipt', 'SOURCE_CHANGED')
        _require(type(page.get('url')) is str and page['url'].startswith('https://'), 'source page requires original HTTPS URL')
        if page['name'] == 'mendeley-v1.md':
            _require(page['url'] == DATASET_URL, 'dataset page URL differs from V1 source')
        checked_pages.append({'name': page['name'], 'url': page['url'], 'sha256': digest, 'bytes': len(payload)})
    coordinates = {c01.MAIN: ('W3', 'X3', 'Y3', 'Z3', 'AA3', 'AB3', 'W4', 'Y4', 'AA4',
                              'AP3', 'BJ4', 'BV4', 'BX2', 'BX3', 'BX4', 'P5', 'V5'),
                   c01.BIO: ('B7', 'B8', 'B9', 'B10', 'B11', 'B12', 'B13', 'B14', 'L5', 'L7')}
    cells = []
    for name, refs in coordinates.items():
        book = c01._workbook(official[name])
        for ref in refs:
            cells.append({'source': name, 'source_sha256': hashlib.sha256(official[name]).hexdigest(),
                          'sheet': book['sheet'], 'cell': ref, 'present': ref in book['cells'],
                          **book['cells'].get(ref, {'raw': '', 'formula': None})})
    equal = all(row['byte_equal'] for row in comparison)
    return {'schema_version': 'c01-source-audit-v1', 'all_five_attachments_byte_equal': equal,
            'archive_sha256': bundle['source']['archive_sha256'],
            'snapshot_manifest_sha256': hashlib.sha256(manifest_bytes).hexdigest(),
            'captured_at_utc': manifest['fetched_at_utc'], 'dataset_url': DATASET_URL,
            'dataset_doi': c01.DOI, 'dataset_version': 1, 'files': comparison, 'pages': checked_pages,
            'license': {'statement': manifest['dataset_license'], 'check': manifest['license_check'],
                        'automatic_legal_review': False},
            'selected_upstream_cells': cells, 'sample_count_remains': len(bundle['samples']),
            'original_scope_or_evaluator_changed': False, 'formulas_executed': False, 'fits_performed': 0,
            'network_used_by_auditor': False, 'scientific_validation': False,
            'interpretation': 'Captured source byte identity only. Method/endpoint compatibility, biological independence, label mapping and scientific validity remain separate checks. The manifest is an operator provenance record, not a signature.'}
