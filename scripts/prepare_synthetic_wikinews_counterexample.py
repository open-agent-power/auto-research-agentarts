#!/usr/bin/env python3
"""Create a fixed white-box synthetic counterexample; never accepts source data.

The public entry point generates its own invented XML and synthetic evidence.
Private helpers accept bytes solely for local synthetic tests; this is not an OS
sandbox, a real Wikimedia parser, a rights audit, or permission to run research.
"""
import argparse
import base64
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
import unicodedata
import xml.etree.ElementTree as ET

from autoresearch import contracts as contracts_module, staged_relevance_adapter as staged
from autoresearch.contracts import canonical

ROOT = Path(__file__).resolve().parents[1]
RUNS = ROOT / 'runs'
PREFIX = 's129-synthetic-wikinews-counterexample-'
NS = 'http://www.mediawiki.org/xml/export-0.11/'
TAG = '{' + NS + '}'
UNICODE_VERSION = '15.0.0'
MAX_XML_BYTES = 2 * 1024 * 1024
MAX_PAGES = 2000
FIXTURE_PAGES = 1005
CORPUS_COUNT = 1000
DEV_COUNT = 50
VALIDATION_COUNT = 100
LICENSE = 'synthetic-fixture-only'
ATTRIBUTION = 'Invented synthetic fixture; no external content.'


def _check(ok, message):
    if not ok:
        raise ValueError(message)


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _bytes(value):
    return canonical(value).encode('utf-8')


def _display(value, *, limit):
    _check(type(value) is str, 'invalid text')
    value = unicodedata.normalize('NFC', value.replace('\r\n', '\n').replace('\r', '\n')).strip(' \t\n')
    _check(bool(value) and len(value) <= limit, 'empty or oversized text')
    _check(all(not unicodedata.category(ch).startswith('C') or ch in '\n\t' for ch in value), 'invalid control character')
    _check(not any(token in value for token in ('{{', '}}', '[[', ']]', '<', '>')), 'unsupported synthetic markup')
    return value


def _key(value):
    # Collapse exactly ASCII horizontal/vertical whitespace; Unicode tables are pinned.
    return re.sub(r'[ \t\n\r]+', ' ', unicodedata.normalize('NFC', value.casefold())).strip(' ')


def _id(value):
    _check(type(value) is str and re.fullmatch(r'[1-9][0-9]{0,17}', value) is not None, 'invalid canonical numeric ID')
    return int(value)


def _fixture(reverse=False):
    """Invent a deliberately query-designed boundary fixture, never real articles.

    Query IDs are fixed by the same original SHA salt before constructing text.
    Text deliberately favors opposite lexical orderings; it is not an unseen test
    of generalization. The expected MRR difference is theoretical, not measured.
    """
    _check(type(reverse) is bool, 'invalid synthetic fixture order')
    canonical_ids = list(range(1, 1001))
    query_ids = sorted(canonical_ids, key=lambda ident:(
        hashlib.sha256(b'wikinews-query-v1\n' + str(ident).encode('ascii')).digest(), ident))[:150]
    query_set = set(query_ids)
    nonqueries = [ident for ident in canonical_ids if ident not in query_set]
    decoys = dict(zip(nonqueries[:150], query_ids, strict=True))
    invented = {}
    for page in canonical_ids:
        if page in query_set:
            title = 'x' + str(page)
            line = ' '.join([title] * 10 + ['y' + str(page)])
        elif page in decoys:
            title = 'article' + str(page)
            line = 'x' + str(decoys[page])
        else:
            title = 'article' + str(page)
            line = 'z' + str(page)
        invented[page] = (title, title + '\n' + line)
    pages = []
    for page in range(1, FIXTURE_PAGES + 1):
        original = page if page <= 1000 else page - 1000
        title, body = invented[original]
        pages.append((str(page), str(100000 + page), title, body))
    evidence = {}
    root = ET.Element(TAG + 'mediawiki')
    for page, revision, title, body in (reversed(pages) if reverse else pages):
        element = ET.SubElement(root, TAG + 'page')
        for name, value in (('title', title), ('ns', '0'), ('id', page)):
            ET.SubElement(element, TAG + name).text = value
        rev = ET.SubElement(element, TAG + 'revision')
        ET.SubElement(rev, TAG + 'id').text = revision
        ET.SubElement(rev, TAG + 'timestamp').text = '2001-01-01T00:00:00Z'
        ET.SubElement(rev, TAG + 'text').text = body
        evidence[page] = {'page_id':page, 'revision_id':revision, 'title_sha256':_sha(title.encode('utf-8')),
                          'body_sha256':_sha(body.encode('utf-8')), 'license':LICENSE, 'attribution':ATTRIBUTION}
    xml = ET.tostring(root, encoding='utf-8', xml_declaration=True)
    return xml, evidence


def _parse_fixture(xml, evidence):
    """Strict bounded synthetic MediaWiki-shaped subset; unsupported syntax stops."""
    _check(unicodedata.unidata_version == UNICODE_VERSION, 'Unicode version differs')
    _check(type(xml) is bytes and 0 < len(xml) <= MAX_XML_BYTES, 'XML size outside synthetic limit')
    text = xml.decode('utf-8', errors='strict')
    _check('\x00' not in text and '<!DOCTYPE' not in text and '<!ENTITY' not in text, 'DTD/entities forbidden')
    _check(type(evidence) is dict and len(evidence) <= MAX_PAGES, 'invalid synthetic evidence')
    root = ET.fromstring(text)
    _check(root.tag == TAG + 'mediawiki' and not root.attrib and len(root) <= MAX_PAGES, 'invalid synthetic root')
    _check(root.text is None or not root.text.strip(), 'unexpected root text')
    records, seen = [], set()
    for page in root:
        _check(page.tag == TAG + 'page' and not page.attrib and [x.tag for x in page] == [TAG+'title', TAG+'ns', TAG+'id', TAG+'revision'], 'unsupported page structure')
        _check((page.text is None or not page.text.strip()) and (page.tail is None or not page.tail.strip())
               and all(node.tail is None or not node.tail.strip() for node in page), 'unexpected page text')
        title_node, namespace, ident, revision = list(page)
        _check(all(not x.attrib and len(x) == 0 for x in (title_node, namespace, ident)), 'unsupported page fields')
        _check(namespace.text == '0' and not revision.attrib and [x.tag for x in revision] == [TAG+'id', TAG+'timestamp', TAG+'text'], 'unsupported namespace or revision')
        rid, timestamp, body_node = list(revision)
        _check(all(not x.attrib and len(x) == 0 for x in (rid, timestamp, body_node)) and timestamp.text == '2001-01-01T00:00:00Z', 'invalid synthetic revision')
        _check((revision.text is None or not revision.text.strip())
               and all(node.tail is None or not node.tail.strip() for node in revision), 'unexpected revision text')
        page_id, revision_id = _id(ident.text), _id(rid.text)
        _check(page_id not in seen, 'duplicate page ID'); seen.add(page_id)
        title_raw, body_raw = title_node.text, body_node.text
        _check(type(title_raw) is str and type(body_raw) is str, 'missing synthetic text')
        declared = evidence.get(str(page_id))
        _check(type(declared) is dict and set(declared) == {'page_id','revision_id','title_sha256','body_sha256','license','attribution'}
               and declared['page_id'] == str(page_id) and declared['revision_id'] == str(revision_id)
               and declared['license'] == LICENSE and declared['attribution'] == ATTRIBUTION
               and declared['title_sha256'] == _sha(title_raw.encode('utf-8')) and declared['body_sha256'] == _sha(body_raw.encode('utf-8')),
               'synthetic evidence missing or inconsistent')
        title = _display(title_raw, limit=4096)
        body = _display(body_raw, limit=131072)
        first, separator, remainder = body.partition('\n')
        if separator and first.strip(' \t') == title:
            body = _display(remainder, limit=131072)
        _check(len(title) <= staged.LIMITS['max_query_text'], 'query too long')
        records.append({'page_id':page_id, 'revision_id':revision_id, 'title':title, 'body':body})
    _check(len(records) > 0 and set(evidence) == {str(v) for v in seen}, 'synthetic evidence coverage differs')
    return records


def _select(records):
    _check(unicodedata.unidata_version == UNICODE_VERSION, 'Unicode version differs')
    _check(type(records) is list and 0 < len(records) <= MAX_PAGES, 'invalid synthetic records')
    rows = {}
    for record in records:
        _check(type(record) is dict and set(record) == {'page_id','revision_id','title','body'}
               and type(record['page_id']) is int and 0 < record['page_id'] < 10**18
               and type(record['revision_id']) is int and record['revision_id'] > 0
               and record['page_id'] not in rows, 'duplicate or malformed synthetic record')
        _check(_display(record['title'], limit=4096) == record['title'] and _display(record['body'], limit=131072) == record['body'], 'noncanonical record')
        rows[record['page_id']] = copy.deepcopy(record)
    parent = {ident:ident for ident in rows}
    def find(ident):
        while parent[ident] != ident:
            parent[ident] = parent[parent[ident]]; ident = parent[ident]
        return ident
    def merge(a, b):
        a, b = find(a), find(b)
        if a != b: parent[max(a,b)] = min(a,b)
    titles, bodies = {}, {}
    for ident in sorted(rows):
        for value, index in ((_key(rows[ident]['title']), titles), (_key(rows[ident]['body']), bodies)):
            if value in index: merge(ident, index[value])
            else: index[value] = ident
    components = {}
    for ident in sorted(rows): components.setdefault(find(ident), []).append(ident)
    groups = sorted(components.values(), key=lambda group:group[0])
    eligible = [rows[group[0]] for group in groups]
    _check(len(eligible) >= CORPUS_COUNT, 'insufficient deduplicated synthetic articles')
    def ordering(prefix, row):
        ident = row['page_id']
        return (hashlib.sha256(prefix + b'\n' + str(ident).encode('ascii')).digest(), ident)
    corpus = sorted(eligible, key=lambda row:ordering(b'wikinews-sample-v1', row))[:CORPUS_COUNT]
    queries = sorted(corpus, key=lambda row:ordering(b'wikinews-query-v1', row))
    return {'corpus':corpus, 'dev':queries[:DEV_COUNT], 'validation':queries[DEV_COUNT:DEV_COUNT+VALIDATION_COUNT],
            'components':groups}


def _write(path, raw):
    _check(type(raw) is bytes, 'invalid output bytes')
    with path.open('xb') as stream:
        stream.write(raw); stream.flush(); os.fsync(stream.fileno())


def _sync_directory(path):
    descriptor = os.open(path, os.O_RDONLY | getattr(os, 'O_DIRECTORY', 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _read_exact(path, expected):
    for part in (path, *path.parents):
        _check(not part.is_symlink(), 'symlink input path is forbidden')
    descriptor = os.open(path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0))
    try:
        before = os.fstat(descriptor)
        _check(stat.S_ISREG(before.st_mode) and before.st_size == len(expected), 'synthetic file size changed')
        chunks, remaining = [], len(expected) + 1
        while remaining:
            chunk = os.read(descriptor, min(65536, remaining))
            if not chunk: break
            chunks.append(chunk); remaining -= len(chunk)
        after = os.fstat(descriptor)
        current = os.stat(path, follow_symlinks=False)
        _check((before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns)
               == (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns)
               == (current.st_dev, current.st_ino, current.st_size, current.st_mtime_ns, current.st_ctime_ns)
               and b''.join(chunks) == expected, 'synthetic file bytes changed')
    finally:
        os.close(descriptor)


def _output_path(output_dir):
    path = Path(output_dir).absolute()
    _check(path.parent == RUNS and path.name.startswith(PREFIX) and path.name != PREFIX, 'use a new synthetic output directly under runs')
    for ancestor in (path, *path.parents):
        _check(not ancestor.is_symlink(), 'symlink output path is forbidden')
    _check(not path.exists(), 'synthetic output already exists')
    return path


def prepare(output_dir):
    """Generate the fixed internal synthetic fixture; no caller-supplied source."""
    output = _output_path(output_dir)
    script_raw = Path(__file__).read_bytes()
    contracts_path = Path(contracts_module.__file__).absolute()
    contracts_raw = contracts_path.read_bytes()
    _read_exact(contracts_path, contracts_raw)
    adapter_identity = staged.code_identity()
    xml, evidence = _fixture()
    records = _parse_fixture(xml, evidence)
    selected = _select(records)
    corpus, dev, validation = selected['corpus'], selected['dev'], selected['validation']
    # Check the frozen design structurally. This does not execute retrieval or scoring.
    by_id = {row['page_id']:row for row in corpus}
    expected_queries = sorted(range(1, 1001), key=lambda ident:(
        hashlib.sha256(b'wikinews-query-v1\n' + str(ident).encode('ascii')).digest(), ident))[:150]
    _check(set(by_id) == set(range(1, 1001)) and
           [row['page_id'] for row in dev + validation] == expected_queries,
           'fixed synthetic query identity changed')
    remaining = [ident for ident in range(1, 1001) if ident not in set(expected_queries)]
    for query, decoy in zip(expected_queries, remaining[:150], strict=True):
        word = 'x' + str(query)
        _check(by_id[query]['title'] == word and by_id[query]['body'] ==
               ' '.join([word] * 10 + ['y' + str(query)]) and by_id[decoy]['body'] == word,
               'white-box synthetic pair changed')
    _check(all(by_id[ident]['body'] == 'z' + str(ident) for ident in remaining[150:]),
           'white-box synthetic filler changed')
    doc_ids = ['d-' + str(row['page_id']) for row in corpus]
    query_rows = dev + validation
    query_ids = ['q-' + str(row['page_id']) for row in query_rows]
    _check(len(doc_ids) == len(set(doc_ids)) == CORPUS_COUNT and len(query_ids) == len(set(query_ids)) == DEV_COUNT+VALIDATION_COUNT
           and not set(doc_ids) & set(query_ids) and all('d-' + str(row['page_id']) in doc_ids for row in query_rows), 'synthetic positive mapping invalid')
    def jsonl(values): return b''.join(_bytes(value) + b'\n' for value in values)
    assets = {
        'corpus.jsonl': jsonl({'_id':'d-'+str(row['page_id']), 'title':'', 'text':row['body'], 'metadata':{}} for row in corpus),
        'queries.jsonl': jsonl({'_id':'q-'+str(row['page_id']), 'text':row['title'], 'metadata':{}} for row in query_rows),
        'qrels.tsv': ('query-id\tcorpus-id\tscore\n' + ''.join('q-'+str(row['page_id'])+'\td-'+str(row['page_id'])+'\t1\n' for row in query_rows)).encode('utf-8'),
        'license.md': b'Invented synthetic fixture only. No external article, licence, or scientific claim.\n',
    }
    selection = {'schema_version':'synthetic-wikinews-selection-v1', 'synthetic_only':True,
                 'fixture_kind':'white_box_query_designed_counterexample',
                 'corpus_ids':doc_ids, 'dev_ids':['q-'+str(row['page_id']) for row in dev],
                 'validation_ids':['q-'+str(row['page_id']) for row in validation], 'components':selected['components']}
    source_receipt = {'schema_version':'synthetic-wikinews-source-receipt-v1', 'synthetic_only':True,
                      'fixture_kind':'white_box_query_designed_counterexample',
                      'original_xml_sha256':_sha(xml), 'evidence':{key:evidence[key] for key in sorted(evidence, key=int)}}
    selection_raw, source_receipt_raw = _bytes(selection), _bytes(source_receipt)
    spec = {'schema_version':'staged-relevance-development-spec-v1', 'dataset_label':'Invented white-box counterexample fixture only',
            'source_url':'urn:autoresearch:synthetic-wikinews-counterexample-s129', 'attribution':ATTRIBUTION,
            'license_notes':{'corpus':'Invented white-box fixture; not external authorization.', 'queries_and_qrels':'Query split intentionally determines distractors; synthetic, not blind.'},
            'source_provenance':{'archive_sha256':_sha(xml), 'source_receipt_sha256':_sha(source_receipt_raw),
                                 'selection_sha256':_sha(selection_raw), 'qrels_semantics':staged.SEMANTICS},
            'files':copy.deepcopy(staged.FILES), 'query_splits':{'dev':selection['dev_ids'], 'validation':selection['validation_ids']},
            'comparison':copy.deepcopy(staged.COMPARISON), 'limits':copy.deepcopy(staged.LIMITS)}
    spec_raw = _bytes(spec)
    _check(sum(len(value) for value in assets.values()) <= staged.LIMITS['all_asset_bytes'], 'synthetic assets too large')
    output.mkdir(mode=0o700, parents=False, exist_ok=False)
    claim_raw = _bytes({'schema_version':'synthetic-wikinews-claim-v1','synthetic_only':True,'xml_sha256':_sha(xml)})
    _write(output/'claim.json', claim_raw)
    _write(output/'fixture.xml', xml)
    development = output/'development'; development.mkdir(mode=0o700)
    for name, raw in assets.items(): _write(development/name, raw)
    _write(development/'spec.json', spec_raw)
    _write(output/'selection.json', selection_raw)
    _write(output/'source-receipt.json', source_receipt_raw)
    generated = {output/'claim.json':claim_raw, output/'fixture.xml':xml, output/'selection.json':selection_raw,
                 output/'source-receipt.json':source_receipt_raw, development/'spec.json':spec_raw,
                 **{development/name:raw for name,raw in assets.items()}}
    for path, raw in generated.items(): _read_exact(path, raw)
    packet = staged.capture_source(development)
    packet_raw = _bytes(packet)
    _check(len(packet_raw) <= staged.LIMITS['packet_bytes'] and staged.load_source(packet_raw) == packet, 'synthetic packet mismatch')
    _check(packet['spec'] == spec and base64.b64decode(packet['spec_source']['bytes_base64'], validate=True) == spec_raw
           and all(base64.b64decode(packet['assets'][role]['bytes_base64'], validate=True) == assets[name]
                   for role,name in staged.FILES.items()), 'captured packet differs from invented assets')
    _write(output/'source.json', packet_raw)
    for path, raw in {**generated, output/'source.json':packet_raw}.items(): _read_exact(path, raw)
    _read_exact(contracts_path, contracts_raw)
    _check(Path(__file__).read_bytes() == script_raw and staged.code_identity() == adapter_identity,
           'synthetic source or reader identity changed')
    _sync_directory(development)
    receipt = {'schema_version':'synthetic-wikinews-counterexample-preparation-v1', 'synthetic_only':True,
               'fixture_kind':'white_box_query_designed_counterexample',
               'theoretical_prediction_not_measured':{'recall20_candidate_minus_baseline':0, 'mrr10_candidate_minus_baseline':-0.5},
               'verification':'generated_fixture_and_host_declared_evidence_not_external_license_authentication',
               'archive_representation':'synthetic_uncompressed_xml_not_wikimedia_archive',
               'unicode_version':unicodedata.unidata_version, 'python_version':sys.version.split()[0],
               'script_sha256':_sha(script_raw), 'contracts_sha256':_sha(contracts_raw),
               'staged_adapter_sha256':_sha(Path(staged.__file__).read_bytes()),
               'adapter_identity':adapter_identity,
               'xml_sha256':_sha(xml), 'claim_sha256':_sha(claim_raw), 'selection_sha256':_sha(selection_raw), 'source_receipt_sha256':_sha(source_receipt_raw),
               'spec_sha256':_sha(spec_raw), 'assets_sha256':{name:_sha(raw) for name,raw in assets.items()},
               'packet_sha256':_sha(packet_raw), 'source_snapshot_sha256':packet['snapshot_sha256'],
               'counts':{'fixture_pages':len(records), 'corpus':len(corpus), 'dev':len(dev), 'validation':len(validation)},
               'research_dispatches':0, 'model_calls':0, 'fits':0,
               'limitations':['The query split was used to design synthetic distractors: white-box engineering fixture, not a blind or real study.',
                              'The expected paired difference is theoretical and has not been measured by this preparation.',
                              'Synthetic fixture and synthetic evidence only; no external content or licence authentication.',
                              'Source identities do not authenticate loaded memory or the complete runtime environment.',
                              'No ranking, scoring or Project is performed by this preparation.']}
    _write(output/'receipt.json', _bytes(receipt))
    _sync_directory(output)
    _sync_directory(RUNS)
    return receipt


def main():
    parser = argparse.ArgumentParser(description='Prepare only the fixed invented white-box S129 counterexample.')
    parser.add_argument('--output', required=True, help='New s129-synthetic-wikinews-counterexample-* directory directly below runs.')
    args = parser.parse_args()
    result = prepare(args.output)
    print(json.dumps({'schema_version':result['schema_version'], 'synthetic_only':True,
                      'packet_sha256':result['packet_sha256'], 'counts':result['counts']}, sort_keys=True))


if __name__ == '__main__':
    main()
