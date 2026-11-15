#!/usr/bin/env python3
"""S067 fixed BoolQ paired-passage preparation and native continuation; no model calls.

The public source contains eventual final questions and labels. Preparation
necessarily reads them in one trusted process; this is not a blind evaluation.
The native report contains source text and is private to the local workspace.
"""
import argparse
import base64
import copy
from datetime import datetime, timezone
import hashlib
import importlib.util
import io
import json
import math
import os
from pathlib import Path
import re
import signal
import sqlite3
import subprocess
import sys
import tempfile
import time
import unicodedata
from urllib.parse import quote
import zipfile

if __name__ == '__main__' and any(x == 'autoresearch' or x.startswith('autoresearch.') for x in sys.modules):
    raise RuntimeError('Project modules were imported before the private bytecode guard.')
_PRIVATE_CACHE = tempfile.TemporaryDirectory(prefix='s067-python-cache-')
sys.pycache_prefix = _PRIVATE_CACHE.name
sys.dont_write_bytecode = True
for _thread in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS'):
    os.environ[_thread] = '1'

from autoresearch import (method_registry, project_selection, retrieval_holdout, staged_relevance_adapter as staged,
                          hypothesis_feedback, staged_continuation, staged_feedback_reader as reader, relevance_retrieval_adapter as relevance)
from autoresearch.contracts import ResearchError, canonical, fingerprint
from autoresearch.local_workbench import LocalWorkbench
from autoresearch.project_controller import ProjectController, code_identity as controller_identity
from autoresearch.research_project import ResearchProject, code_identity as project_identity, safe_path

REPO=Path(__file__).resolve().parent.parent
SCRIPT=Path(__file__).resolve()
PROTOCOL=REPO/'docs/execution/g5-local/boolq-case-comparison-protocol-v1.json'
S046=REPO/'scripts/run_squad_paragraph_study.py'
TESTS=REPO/'tests/test_boolq_case_comparison_study.py'
STUDY='s067-boolq-paired-passage-v1'
WORKSPACE=REPO/'runs'/STUDY
CLAIM=REPO.parent/'.study-claims'/(STUDY+'.json')
SOURCE=Path('/workspace/reference-exploration-20261115/boolq/original-dev-mirror.jsonl')
SOURCE_SHA='ebc29ea3808c5c611672384b3de56e83349fe38fc1fe876fd29b674d81d0a80a'
SOURCE_BYTES=2238726
PROTOCOL_SHA='ca8e7212ed1aa1ce65e197571e0613d3ace738855470ef7c71d7b4f40efaf5c1'
LEASE=Path('/workspace/development-continuation-20261114/auto-research-agentarts/.agent/autonomy/lease.json')
SEED='s067-boolq-passage-v1:'
IDS={'plan':'s067-plan','evidence_cap':'s067-zero-evidence','holdout':'s067-holdout',
     'hypothesis':'s067-hypothesis','primary':'s067-primary','conditional':'s067-conditional',
     'import':'s067-import','select':'s067-select','case_import':'s067-case-import',
     'shadow_anchor':'s067-shadow-anchor'}
PLAN={'question':'Can a fixed S065-informed rule improve final paired-passage retrieval relative to the fixed recall-only rule?',
      'basis':'Public BoolQ development source was previously examined; the S065 case is fixed history, not model learning.',
      'steps':'Run one fixed lexical pair, then a preregistered native gate and one independent shadow rule before final.',
      'expected_feedback':'Retain all observed aggregate validation and final results, zeros, adverse outcomes and unknowns.'}
PLAN_REASON='Apply the fixed S067 paired-passage protocol.'
CAP_REASON='S067 authorizes no evidence-source actions.'
CONTINUE_REASON='Apply the original preregistered feedback audit and fixed final-method mapping.'
PROVIDER={'kind':'operator_assistant','label':'S067 fixed preregistered protocol'}
RATIONALE='Execute the original S067 validation pair under the fixed source and budget.'
CASE=Path('/workspace/development-continuation-20261114/auto-research-agentarts/runs/s066-verification/attempt-001/bundle.json')
CASE_FILE_SHA='67deff921b5a42c28d075ec84129fce6df199aa3f7d5f50ae671b42d75f3d4b2'
CASE_CANONICAL_SHA='4ff88cb1fb5c365b9cd333f9dd56035d7d2cc366b2df98a2a6ddf8ded4a7712a'



def fail(message):
    raise RuntimeError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def encoded(value):
    return canonical(value).encode('utf-8')


def _s046():
    spec=importlib.util.spec_from_file_location('s065_reused_s046',S046)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


def save_once(path,raw):
    _s046().save_once(path,raw)


def save_json(path,value):
    save_once(path,encoded(value))


def read_json(path):
    raw=safe_path(path).read_bytes();value=json.loads(raw)
    if encoded(value)!=raw:fail('Original JSON bytes are missing or noncanonical: '+str(path))
    return value


def _check_text(value, *, maximum, empty=False):
    return (type(value) is str and len(value)<=maximum and '\x00' not in value
            and (empty or bool(value.strip())) and all(not 0xd800<=ord(c)<=0xdfff for c in value))


def parse_jsonl(raw):
    """Parse strict source rows; input may include publicly exposed final examples."""
    if type(raw) is not bytes: fail('Original JSONL must be bytes.')
    lines=raw.split(b'\n')
    if lines and lines[-1]==b'': lines.pop()
    if any(not line or line.endswith(b'\r') for line in lines):
        fail('Original JSONL contains an empty or noncanonical line.')
    return [staged._parse(line) for line in lines]


def derive_source(rows, *, split_size=200, expected_rows=3270, expected_groups=2938):
    """Pure predeclared conversion; tests may use fabricated rows only."""
    if (type(rows) is not list or len(rows)!=expected_rows or type(split_size) is not int
            or split_size<1 or type(expected_groups) is not int or expected_groups<3*split_size):
        fail('Original source count, group count or split size differs.')
    seen_questions=set(); groups={}; digests={}
    for line,row in enumerate(rows,1):
        if type(row) is not dict or not {'question','title','passage'}<=set(row):
            fail('Original source row is missing required fields.')
        question,title,passage=(row[k] for k in ('question','title','passage'))
        if (not _check_text(question,maximum=staged.LIMITS['max_query_text'])
                or not _check_text(title,maximum=4096) or not _check_text(passage,maximum=131072)):
            fail('Original question, title or passage is invalid.')
        key=unicodedata.normalize('NFC',' '.join(question.split())).casefold()
        if not key or key in seen_questions: fail('Original normalized question is duplicated; stop without resampling.')
        seen_questions.add(key)
        docid='d-'+sha(passage.encode('utf-8'))
        if docid in digests and digests[docid]!=passage: fail('Original passage hash collision.')
        digests[docid]=passage
        group=groups.setdefault(docid,{'passage':passage,'titles':set(),'line':line,'question':question})
        group['titles'].add(title)
    if len(groups)!=expected_groups: fail('Original exact passage group count differs.')
    ordered=sorted(groups,key=lambda d:(sha((SEED+d).encode('utf-8')),d.encode('ascii')))
    docs={}; sidecar=[]
    for docid in sorted(groups):
        group=groups[docid];titles=sorted(group['titles'],key=lambda t:t.encode('utf-8'))
        docs[docid]={'_id':docid,'title':titles[0],'text':group['passage'],'metadata':{}}
        sidecar.append({'doc_id':docid,'titles':titles,'wikipedia_urls':[
            'https://en.wikipedia.org/wiki/'+quote(t.replace(' ','_'),safe='') for t in titles],
            'revision':'unknown','contributors':'unknown'})
    if len(docs)>staged.LIMITS['max_corpus_rows']: fail('Original corpus exceeds the native row limit.')
    split_rows={}
    for i,split in enumerate(('dev','validation','final')):
        result=[]
        for docid in ordered[i*split_size:(i+1)*split_size]:
            group=groups[docid];qid='q-boolq-dev-'+str(group['line']).zfill(8)
            result.append({'qid':qid,'original_line':group['line'],'text':group['question'],'positive_doc_ids':[docid]})
        split_rows[split]=result
    qids={r['qid'] for rows_ in split_rows.values() for r in rows_}
    if len(qids)!=3*split_size or qids.intersection(docs): fail('Query IDs collide or duplicate.')
    corpus=''.join(canonical(docs[k])+'\n' for k in sorted(docs)).encode('utf-8')
    def query_bytes(items):
        return ''.join(canonical({'_id':r['qid'],'text':r['text'],'metadata':{}})+'\n' for r in items).encode('utf-8')
    def qrel_bytes(items):
        return ('query-id\tcorpus-id\tscore\n'+''.join(
            r['qid']+'\t'+r['positive_doc_ids'][0]+'\t1\n' for r in items)).encode('utf-8')
    public=split_rows['dev']+split_rows['validation']
    return {'corpus':corpus,'queries':query_bytes(public),'qrels':qrel_bytes(public),
            'final_queries':query_bytes(split_rows['final']),'final_qrels':qrel_bytes(split_rows['final']),
            'sidecar':sidecar,'selection':split_rows,'selected_question_count':len(qids),
            'distinct_questions':len(seen_questions),'original_rows':len(rows),'document_count':len(docs)}


def source_pin(commit):
    if re.fullmatch(r'[0-9a-f]{40}',commit or '') is None or REPO!=Path('/workspace/development-continuation-20261114/source-pins')/commit[:7]:
        fail('Use only the canonical checkout of the exact published commit.')
    def git(*args):
        return subprocess.run(['git',*args],cwd=REPO,check=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE).stdout
    if git('rev-parse','HEAD').decode().strip()!=commit or git('status','--porcelain','--untracked-files=no').strip():
        fail('The exact published checkout must remain clean.')
    if git('remote','get-url','origin').decode().strip()!='https://github.com/open-agent-power/auto-research-agentarts.git':
        fail('Origin does not identify the designated GitHub repository.')
    untracked=git('ls-files','--others','--','src').decode().splitlines()
    if any(Path(p).suffix in {'.py','.pyc','.so','.pyd'} and '__pycache__' not in Path(p).parts for p in untracked):
        fail('Untracked importable files could shadow pinned source.')
    for path in (SCRIPT,PROTOCOL,S046,TESTS):
        if git('show',commit+':'+path.relative_to(REPO).as_posix())!=path.read_bytes():
            fail('Published driver, protocol or helper bytes changed.')
    publication=_s046().verify_publication(commit)
    raw=safe_path(PROTOCOL).read_bytes()
    if sha(raw)!=PROTOCOL_SHA:fail('The published fixed protocol differs.')
    protocol=staged._parse(raw)
    runtime=method_registry.runtime_dependencies()
    if (protocol.get('schema_version')!='s067-boolq-case-comparison-protocol-v1' or protocol.get('study_id')!=STUDY
            or protocol.get('ids')!=IDS or protocol.get('source',{}).get('path')!=str(SOURCE)
            or protocol['source'].get('bytes')!=SOURCE_BYTES or protocol['source'].get('sha256')!=SOURCE_SHA
            or protocol.get('preparation',{}).get('seed')!=SEED
            or protocol['preparation'].get('splits')!={'dev':200,'validation':200,'final':200}
            or protocol.get('budget',{}).get('native_tools')!=3
            or any(protocol['budget'].get(k)!=0 for k in ('model_calls','fits','evidence_actions'))
            or protocol['budget'].get('concurrency')!=1 or protocol['runtime'].get('wall_seconds')!=1800
            or protocol['policy'].get('native_A')!={'metric':'recall@20','operator':'gt','threshold':0}
            or protocol['policy'].get('shadow_B')!={'conditions':[{'metric':'recall@20','operator':'gt','threshold':0},
                                                                  {'metric':'mrr@10','operator':'gte','threshold':0}],
                 'leave_one_out':{'metric':'recall@20','operator':'gt','threshold':0}}
            or protocol['policy'].get('native_holdout')!={'kind':'registered_feedback',
                 'registration_request_id':IDS['hypothesis'],'condition_met':'tfidf_cosine',
                 'condition_not_met':'bm25','unknown':'stop'}
            or protocol['policy'].get('known_branches')!=staged.AUDIT_TOOL_ID
            or protocol['case'].get('file_sha256')!=CASE_FILE_SHA or protocol['case'].get('canonical_sha256')!=CASE_CANONICAL_SHA
            or '.'.join(map(str,sys.version_info[:3]))!=protocol['runtime']['python']
            or unicodedata.unidata_version!=protocol['runtime']['unicode']
            or runtime!={'numpy':protocol['runtime']['numpy'],'scipy':protocol['runtime']['scipy'],
                         'scikit-learn':protocol['runtime']['sklearn']}):
        fail('Fixed protocol, numerical runtime, budget or policy differs.')
    for module in (staged,retrieval_holdout,method_registry,hypothesis_feedback):
        if not Path(module.__file__).resolve().is_relative_to((REPO/'src').resolve()):
            fail('A project module is not from this source pin.')
    return ({'source_commit':commit,'publication':publication,'protocol_sha256':sha(raw),'driver_sha256':sha(SCRIPT.read_bytes()),
             'helper_sha256':sha(S046.read_bytes()),'test_sha256':sha(TESTS.read_bytes()),'project_code_identity':project_identity(),
             'controller_code_identity':controller_identity(),'runtime_dependencies':runtime,
             'python':sys.version,'unicode':unicodedata.unidata_version},protocol)


def current_owner():
    lease=json.loads(safe_path(LEASE).read_bytes());owner=lease.get('owner')
    if (lease.get('schema_version')!='project-autonomy-lease-v1' or lease.get('status')!='active'
            or type(owner) is not str or re.fullmatch(r'[A-Za-z0-9_.:-]{1,120}',owner) is None
            or type(lease.get('expires')) not in (int,float) or lease['expires']<=time.time()):
        fail('No active cooperating coordinator lease was found.')
    return owner


def local_archive(raw):
    stream=io.BytesIO()
    with zipfile.ZipFile(stream,'w',compression=zipfile.ZIP_STORED) as archive:
        info=zipfile.ZipInfo('boolq_dev_original.jsonl',(2020,1,1,0,0,0));info.compress_type=zipfile.ZIP_STORED
        archive.writestr(info,raw)
    return stream.getvalue()


def _verify_assets(packet,holdout,selection):
    spec,docs,queries,qrels,_,_=staged._checked(packet)
    if set(selection)!={'dev','validation','final'} or any(len(selection[k])!=200 for k in selection):
        fail('Original selection must retain fixed 200/200/200 rows.')
    for split in ('dev','validation'):
        if spec['query_splits'][split]!=[r['qid'] for r in selection[split]]:fail('Original public split changed.')
        for row in selection[split]:
            if (queries.get(row['qid'],{}).get('text')!=row['text']
                    or qrels.get(row['qid'])!={doc:1 for doc in row['positive_doc_ids']}):
                fail('Original public query text or qrels changed.')
    final,_=relevance._jsonl(holdout['queries_jsonl'].encode(),False)
    final_qrels=relevance._qrels(holdout['qrels_tsv'].encode(),docs,final)
    if (holdout['schema_version']!='retrieval-holdout-v1' or holdout['corpus_sha256']!=packet['assets']['corpus']['sha256']
            or list(final)!=[r['qid'] for r in selection['final']] or set(final)&set(queries)
            or any(final.get(r['qid'],{}).get('text')!=r['text']
                   or final_qrels.get(r['qid'])!={doc:1 for doc in r['positive_doc_ids']} for r in selection['final'])):
        fail('Original private final queries or positives changed.')


def case_bytes(protocol):
    """Validate exact historical case identity; source remains read-only."""
    from autoresearch import project_experience_dispatch
    raw=safe_path(CASE).read_bytes()
    if len(raw)!=protocol['case']['file_bytes'] or sha(raw)!=CASE_FILE_SHA:
        fail('Original historical case file changed.')
    bundle=project_experience_dispatch.parse_bundle(raw)
    packed=encoded(bundle)
    if (len(packed)!=protocol['case']['canonical_bytes'] or sha(packed)!=CASE_CANONICAL_SHA
            or bundle['id']!=protocol['case']['case_id'] or bundle['version']!=protocol['case']['case_version']
            or bundle['record']['id']!=protocol['case']['entry_id']):
        fail('Historical case canonical identity changed.')
    condition=bundle['record']['provenance']['feedback_history']['registration']['condition']
    if condition!={'all':[{'split':'validation','measure':'candidate_minus_baseline','metric':'recall@20','operator':'gt','threshold':0},
                          {'split':'validation','measure':'candidate_minus_baseline','metric':'mrr@10','operator':'gte','threshold':0}],
                   'leave_one_out':{'split':'validation','measure':'leave_one_out_mean','metric':'recall@20','operator':'gt','threshold':0}}:
        fail('Historical case condition differs from the fixed shadow policy.')
    return packed


def prepare(identity,protocol):
    # Protocol/source-pin publication is checked before this function is called.
    original_path=safe_path(SOURCE)
    if original_path.stat().st_size!=SOURCE_BYTES:fail('Original source size differs.')
    raw=original_path.read_bytes()
    if len(raw)!=SOURCE_BYTES or sha(raw)!=SOURCE_SHA:fail('Original source bytes or identity differ.')
    case_raw=case_bytes(protocol)
    safe_path(CLAIM.parent).mkdir(mode=0o700,parents=True,exist_ok=True)
    claim={'schema_version':'s067-study-claim-v1','study_id':STUDY,'workspace':str(WORKSPACE),
           'source_commit':identity['source_commit'],'protocol_sha256':PROTOCOL_SHA,'original_source_sha256':SOURCE_SHA,
           'case_sha256':CASE_CANONICAL_SHA,
           'created_by_owner':current_owner()}
    if WORKSPACE.exists():fail('Original study workspace already exists; never prepare another.')
    save_json(CLAIM,claim)
    WORKSPACE.mkdir(mode=0o700,parents=True,exist_ok=False)
    for name in ('private','development','requests'): (WORKSPACE/name).mkdir(mode=0o700)
    save_json(WORKSPACE/'start.json',{'schema_version':'s067-start-v1','study_id':STUDY,'workspace':str(WORKSPACE),
              'claim_sha256':sha(encoded(claim)),'created_at_utc':datetime.now(timezone.utc).isoformat(),**identity})
    save_once(WORKSPACE/'private/original.json',raw)
    save_once(WORKSPACE/'private/case.canonical.json',case_raw)
    try:
        rows=parse_jsonl(raw)
        derived=derive_source(rows)
        archive=local_archive(raw);save_once(WORKSPACE/'private/original-local.zip',archive)
        save_json(WORKSPACE/'private/selection.json',derived['selection'])
        sidecar=encoded({'schema_version':'s067-document-attribution-v1','documents':derived['sidecar']})
        save_once(WORKSPACE/'private/document-attribution.json',sidecar)
        receipt={'schema_version':'s067-source-receipt-v1','original_sha256':SOURCE_SHA,'original_bytes':SOURCE_BYTES,
                 'mirror_url':protocol['source']['mirror_url'],'author_expected_metadata':protocol['source']['recorded_original_checksum'],
                 'local_archive_sha256':sha(archive),'local_archive_bytes':len(archive),
                 'local_archive_description':'ZIP_STORED generated locally from original JSONL; not an upstream ZIP',
                 'document_attribution_sha256':sha(sidecar),'author_license':protocol['source']['license'],
                 'revision_and_contributors':'unknown'}
        save_json(WORKSPACE/'private/source-receipt.json',receipt)
        for name,key in (('corpus.jsonl','corpus'),('queries.jsonl','queries'),('qrels.tsv','qrels')):
            save_once(WORKSPACE/'development'/name,derived[key])
        license_text=('BoolQ author dataset CC BY-SA 3.0: '+protocol['source']['author_readme']+'\n'
                      'Wikipedia source titles and URLs are recorded in a local sidecar; revisions and contributors unknown.\n')
        save_once(WORKSPACE/'development/license.md',license_text.encode('utf-8'))
        public_selection={k:derived['selection'][k] for k in ('dev','validation')}
        spec={'schema_version':'staged-relevance-development-spec-v1','dataset_label':'BoolQ dev fixed paired-passage cohort',
              'source_url':protocol['source']['mirror_url'],
              'attribution':'BoolQ authors; Wikipedia original titles and URLs in local sidecar; revisions unknown',
              'license_notes':{'corpus':license_text,'queries_and_qrels':'BoolQ CC BY-SA 3.0; author-paired passage only; unjudged is not nonrelevant.'},
              'source_provenance':{'archive_sha256':sha(archive),'source_receipt_sha256':sha(encoded(receipt)),
                                   'selection_sha256':sha(encoded(public_selection)),'qrels_semantics':staged.SEMANTICS},
              'files':copy.deepcopy(staged.FILES),'query_splits':{k:[r['qid'] for r in derived['selection'][k]] for k in ('dev','validation')},
              'comparison':copy.deepcopy(staged.COMPARISON),'limits':copy.deepcopy(staged.LIMITS)}
        save_json(WORKSPACE/'development/spec.json',spec)
        packet=staged.capture_source(WORKSPACE/'development')
        holdout={'schema_version':'retrieval-holdout-v1','corpus_sha256':packet['assets']['corpus']['sha256'],
                 'queries_jsonl':derived['final_queries'].decode('utf-8'),'qrels_tsv':derived['final_qrels'].decode('utf-8')}
        holdout_raw=encoded(holdout)
        if len(holdout_raw)>retrieval_holdout.MAX_HOLDOUT_BYTES:fail('Original private holdout exceeds its limit.')
        _verify_assets(packet,holdout,derived['selection'])
        save_once(WORKSPACE/'private/holdout.json',holdout_raw)
        save_json(WORKSPACE/'development/source.json',packet)
        files=sorted(p for directory in (WORKSPACE/'private',WORKSPACE/'development') for p in directory.iterdir() if p.is_file())
        inventory={p.relative_to(WORKSPACE).as_posix():{'bytes':p.stat().st_size,'sha256':sha(p.read_bytes())} for p in files}
        save_json(WORKSPACE/'prepared.json',{'schema_version':'s067-prepared-v1','files':inventory,
                  'source_snapshot_sha256':packet['snapshot_sha256'],'source_sha256':SOURCE_SHA,'claim':claim})
    except BaseException as exc:
        save_json(WORKSPACE/'preparation-failure.json',{'schema_version':'s067-preparation-failure-v1','study_id':STUDY,
                   'error_type':type(exc).__name__,'message':str(exc)[:1000],'claim_sha256':sha(encoded(claim))})
        raise
    return {'status':'prepared','workspace':str(WORKSPACE),'project_created':False,'research_actions':0,'model_calls':0}


def verify_prepared(identity,protocol):
    claim=read_json(CLAIM);start=read_json(WORKSPACE/'start.json');prepared=read_json(WORKSPACE/'prepared.json')
    owner=claim.get('created_by_owner')
    if type(owner) is not str or re.fullmatch(r'[A-Za-z0-9_.:-]{1,120}',owner) is None:fail('Original claim owner is invalid.')
    expected={'schema_version':'s067-study-claim-v1','study_id':STUDY,'workspace':str(WORKSPACE),
              'source_commit':identity['source_commit'],'protocol_sha256':PROTOCOL_SHA,'original_source_sha256':SOURCE_SHA,
           'case_sha256':CASE_CANONICAL_SHA,
              'created_by_owner':owner}
    names={'private/original.json','private/case.canonical.json','private/original-local.zip','private/selection.json','private/document-attribution.json',
           'private/source-receipt.json','private/holdout.json','development/corpus.jsonl','development/queries.jsonl',
           'development/qrels.tsv','development/license.md','development/spec.json','development/source.json'}
    if (claim!=expected or start.get('schema_version')!='s067-start-v1' or start.get('study_id')!=STUDY
            or start.get('workspace')!=str(WORKSPACE) or start.get('claim_sha256')!=sha(encoded(claim))
            or any(start.get(k)!=v for k,v in identity.items()) or prepared.get('schema_version')!='s067-prepared-v1'
            or prepared.get('claim')!=claim or prepared.get('source_sha256')!=SOURCE_SHA or set(prepared.get('files',{}))!=names):
        fail('Original claim, source identity or prepared inventory changed.')
    for name,expected_file in prepared['files'].items():
        path=Path(name)
        if path.is_absolute() or '..' in path.parts:fail('Prepared inventory path is unsafe.')
        path=safe_path(WORKSPACE/path);raw=path.read_bytes()
        if expected_file!={'bytes':len(raw),'sha256':sha(raw)}:fail('Original prepared file changed: '+name)
    raw=(WORKSPACE/'private/original.json').read_bytes();archive=(WORKSPACE/'private/original-local.zip').read_bytes()
    sidecar=(WORKSPACE/'private/document-attribution.json').read_bytes();receipt=read_json(WORKSPACE/'private/source-receipt.json')
    if (len(raw)!=SOURCE_BYTES or sha(raw)!=SOURCE_SHA or local_archive(raw)!=archive
            or receipt.get('original_sha256')!=SOURCE_SHA or receipt.get('original_bytes')!=SOURCE_BYTES
            or receipt.get('local_archive_sha256')!=sha(archive) or receipt.get('local_archive_bytes')!=len(archive)
            or receipt.get('document_attribution_sha256')!=sha(sidecar)
            or receipt.get('mirror_url')!=protocol['source']['mirror_url']):
        fail('Original source, local archive or attribution receipt changed.')
    packet=staged.load_source((WORKSPACE/'development/source.json').read_bytes())
    if packet!=staged.capture_source(WORKSPACE/'development') or packet['snapshot_sha256']!=prepared['source_snapshot_sha256']:
        fail('Development packet differs from original captured files.')
    selection=read_json(WORKSPACE/'private/selection.json');holdout=read_json(WORKSPACE/'private/holdout.json')
    docs=staged._checked(packet)[1]
    saved_case=(WORKSPACE/'private/case.canonical.json').read_bytes()
    if saved_case!=case_bytes(protocol): fail('Fixed source case differs from the prepared original.')
    # Re-derive only for read-only identity comparison, never to replace an
    # accepted selection. Parsing the original public source again necessarily
    # exposes eventual final rows in this same trusted process.
    original=derive_source(parse_jsonl(raw))
    if (canonical(original['selection'])!=canonical(selection)
            or original['corpus']!=(WORKSPACE/'development/corpus.jsonl').read_bytes()
            or original['queries']!=(WORKSPACE/'development/queries.jsonl').read_bytes()
            or original['qrels']!=(WORKSPACE/'development/qrels.tsv').read_bytes()
            or original['final_queries']!=holdout['queries_jsonl'].encode('utf-8')
            or original['final_qrels']!=holdout['qrels_tsv'].encode('utf-8')
            or encoded({'schema_version':'s067-document-attribution-v1','documents':original['sidecar']})!=sidecar):
        fail('Prepared corpus, selection, questions, qrels or attribution differs from original source.')
    provenance=packet['spec']['source_provenance']
    if (provenance['archive_sha256']!=sha(archive) or provenance['source_receipt_sha256']!=sha(encoded(receipt))
            or provenance['selection_sha256']!=sha(encoded({k:selection[k] for k in ('dev','validation')}))):
        fail('Source receipt, archive or public selection identity changed.')
    _verify_assets(packet,holdout,selection)
    return prepared


def request_body(name,build,*,accepted=False):
    path=WORKSPACE/'requests'/(name+'.json')
    if path.exists():return read_json(path)
    if accepted:fail('Original accepted request body is missing; do not reconstruct it.')
    value=build();save_json(path,value);return value


def require_body(body,fixed,version):
    if (type(body) is not dict or set(body)!=set(fixed)|{'expected_state_version'}
            or canonical({k:body[k] for k in fixed})!=canonical(fixed)
            or type(body['expected_state_version']) is not int or body['expected_state_version']!=version):
        fail('Original request body, fixed fields or state version changed.')


def check_budget(state,cap):
    b=state['budget']
    if (b['lineage_ref']!=STUDY or b['local_tool_call_limit']!=3 or b['local_tool_calls_used']>3
            or b['local_tool_calls_reserved']!=0 or b['evidence_read_limit']!=(0 if cap else 8)
            or b['evidence_reads_used']!=0 or b['evidence_reads_reserved']!=0
            or b['model_requests_allowed']!=0 or b['new_model_requests']!=0 or b['model_requests_reserved']!=0
            or b['fit_limit']!=0 or b['fit_attempts_used']!=0 or b['new_fits']!=0 or state['evidence_actions']):
        fail('Original tool, source, model or fit budget changed or is reserved.')
    expected=[staged.TOOL_ID,staged.AUDIT_TOOL_ID,retrieval_holdout.FINAL_TOOL_ID]
    if [a['command'] for a in state['actions']]!=expected[:len(state['actions'])]:
        fail('Original research action order or count changed.')


def no_unknown(state):
    if (any(a['status']!='completed' for a in state['actions']+state['evidence_actions'])
            or any(p['status'] in ('prepared','running','unknown','failed','rejected','needs_review')
                   for p in state.get('controller_requests',[]))):
        fail('Original action or controller is unfinished, failed or unknown; never redispatch it.')


def deadline_check():
    start=read_json(WORKSPACE/'run-start.json')
    if (type(start) is not dict or set(start)!={'schema_version','study_id','started_unix','deadline_unix','max_wall_seconds'}
            or start['schema_version']!='s067-run-start-v1' or start['study_id']!=STUDY
            or type(start['max_wall_seconds']) is not int or start['max_wall_seconds']!=1800
            or any(type(start[k]) not in (int,float) or not math.isfinite(start[k]) or not 0<=start[k]<=100000000000
                   for k in ('started_unix','deadline_unix')) or start['deadline_unix']!=start['started_unix']+1800):
        fail('Original absolute research window metadata changed.')
    if time.time()>=start['deadline_unix']:fail('Original research window expired; no new action may start.')


def plan_cap_holdout(project,manager):
    state=project.status();no_unknown(state)
    plans=state.get('plan_revisions',[])
    if len(plans)>1 or (plans and plans[0].get('request_id')!=IDS['plan']):fail('Original study plan changed.')
    old=plans[0] if plans else None
    fixed={'request_id':IDS['plan'],'plan':PLAN,'reason':PLAN_REASON}
    body=request_body('plan',lambda:{**fixed,'expected_state_version':state['state_version']},accepted=old is not None)
    require_body(body,fixed,old['based_on_state_version'] if old else state['state_version'])
    if old:
        if any(old.get(k)!=v for k,v in PLAN.items()) or old.get('reason')!=PLAN_REASON:fail('Saved plan differs from original body.')
    else:project.save_plan(**body)
    state=project.status();revisions=state.get('budget_revisions',[])
    if len(revisions)>1 or (revisions and revisions[0].get('request_id')!=IDS['evidence_cap']):fail('Original evidence cap changed.')
    old=revisions[0] if revisions else None
    fixed={'request_id':IDS['evidence_cap'],'expected_limit':8,'new_limit':0,'reason':CAP_REASON}
    body=request_body('evidence-cap',lambda:{**fixed,'expected_state_version':state['state_version']},accepted=old is not None)
    require_body(body,fixed,old['state_version_before'] if old else state['state_version'])
    if old:
        if old.get('request')!={'command':'limit_evidence_budget',**body}:fail('Saved evidence cap differs.')
    else:project.limit_evidence_budget(**body)
    state=project.status();check_budget(state,True)
    original=(WORKSPACE/'private/holdout.json').read_bytes();old=state.get('private_evaluation')
    policy={'kind':'registered_feedback','registration_request_id':IDS['hypothesis'],
            'condition_met':'tfidf_cosine','condition_not_met':'bm25','unknown':'stop'}
    fixed={'request_id':IDS['holdout'],'project_id':state['id'],'holdout_base64':base64.b64encode(original).decode('ascii'),
           'selection_policy':policy}
    with manager._connect(readonly=True) as con:
        manager_row=con.execute('SELECT digest,command,record FROM requests WHERE id=?',(IDS['holdout'],)).fetchone()
    body=request_body('holdout',lambda:{**fixed,'expected_state_version':state['state_version']},
                      accepted=old is not None or manager_row is not None)
    require_body(body,fixed,old['state_version_before'] if old else state['state_version'])
    manager_record=None
    if manager_row is not None:
        manager_record=json.loads(manager_row['record'])
        if (manager_row['command']!='register_holdout' or manager_row['digest']!=fingerprint(body)
                or manager_record.get('status') not in ('preparing','completed')
                or manager_record.get('intent')!={'project_id':state['id'],'request_sha256':fingerprint(body)}):
            fail('Original holdout manager intent or body changed.')
    if old:
        expected={'request_id':IDS['holdout'],'expected_state_version':body['expected_state_version'],
                  'holdout_sha256':sha(original),'holdout_bytes':len(original),'selection_policy':policy}
        if canonical(old.get('request'))!=canonical(expected):fail('Original holdout registration differs.')
        retrieval_holdout.validate_metadata(state)
        if manager_record is None:fail('Original holdout manager intent is missing; never recreate it.')
        if manager_record['status']=='completed':
            if canonical(manager_record.get('result',{}).get('private_evaluation'))!=canonical(old):
                fail('Original holdout manager receipt differs from the Project registration.')
        else:
            manager.register_holdout(body)  # Same ID completes a saved half-finished receipt only.
    else:
        if manager_record is not None:fail('Original holdout intent is unfinished; never redispatch it.')
        manager.register_holdout(body)


def hypothesis(project,protocol):
    state=project.status();records=state.get('hypothesis_registrations',[])
    if len(records)>1 or (records and records[0].get('request_id')!=IDS['hypothesis']):fail('Original hypothesis ledger changed.')
    old=records[0] if records else None
    if old:
        hypothesis_feedback._check_record(old);candidate_id=old['candidate']['id']
    else:
        context=ProjectController(project.root).selection_context()
        candidates=[c for c in context['candidates'] if c['method_id']==staged.TOOL_ID and c['parameters']=={}]
        if context['blockers'] or len(candidates)!=1:fail('The original primary candidate is unavailable.')
        candidate_id=candidates[0]['id']
    branch={'kind':'method','method_id':staged.AUDIT_TOOL_ID}
    value={'candidate_id':candidate_id,'controller_request_id':IDS['primary'],
           **copy.deepcopy(protocol['policy']['native_A']),
           'branches':{'condition_met':copy.deepcopy(branch),'condition_not_met':copy.deepcopy(branch)}}
    fixed={'request_id':IDS['hypothesis'],'hypothesis':value}
    body=request_body('hypothesis',lambda:{**fixed,'expected_state_version':state['state_version']},accepted=old is not None)
    require_body(body,fixed,old['state_version_before'] if old else state['state_version'])
    if old:
        if canonical(old['request'])!=canonical(body) or old['candidate']['method_id']!=staged.TOOL_ID:
            fail('Saved hypothesis differs from its original body.')
    else:project.register_hypothesis(**body)


def import_case(project):
    state=project.status();records=state.get('experience_revisions',[])
    if len(records)>1 or (records and records[0].get('request_id')!=IDS['case_import']):
        fail('Original historical case inclusion changed.')
    old=records[0] if records else None
    raw=(WORKSPACE/'private/case.canonical.json').read_bytes()
    if sha(raw)!=CASE_CANONICAL_SHA: fail('Prepared historical case changed.')
    fixed={'request_id':IDS['case_import'],'bundle_base64':base64.b64encode(raw).decode('ascii'),
           'reason':'Bind the fixed S065 historical case as an untrusted, human-selected comparison premise.'}
    body=request_body('case-import',lambda:{**fixed,'expected_state_version':state['state_version']},accepted=old is not None)
    require_body(body,fixed,old['based_on_state_version'] if old else state['state_version'])
    expected={'case_id':'s065-hotpot-support-history','case_version':1,'bundle_sha256':CASE_CANONICAL_SHA,
              'entry_id':'266a07d2f8af2e40a208a6c7d3382265e62700225ad4b5ade8078b3d4a92b363',
              'inclusion_status':'active'}
    if old and any(old.get(k)!=v for k,v in expected.items()):fail('Original case import differs from its fixed identity.')
    revision=project.import_experience(request_id=body['request_id'],expected_state_version=body['expected_state_version'],
                                       bundle=raw,reason=body['reason'])
    if any(revision.get(k)!=v for k,v in expected.items()):fail('Imported case identity differs.')


def primary(project):
    state=project.status();no_unknown(state);check_budget(state,True);controller=ProjectController(project.root)
    parents=[p for p in state.get('controller_requests',[]) if p['request_id']==IDS['primary']]
    if len(parents)>1:fail('Original primary parent is ambiguous.')
    old=parents[0] if parents else None
    def expected(context):
        candidates=[c for c in context['candidates'] if c['method_id']==staged.TOOL_ID and c['parameters']=={}]
        if context['blockers'] or len(candidates)!=1:fail('Original sealed context lacks the unique primary candidate.')
        proposal={'schema_version':'project-selection-proposal-v1','context_sha256':context['context_sha256'],
                  'provider':PROVIDER,'choice':{'kind':'execute','candidate_id':candidates[0]['id']},
                  'rationale':RATIONALE,'evidence_citation_ids':[],
                  'experience_case_refs':project_selection.active_experience_case_refs(context)}
        expected_ref={'case_id':'s065-hotpot-support-history','case_version':1,'bundle_sha256':CASE_CANONICAL_SHA}
        if proposal['experience_case_refs']!=[expected_ref]:fail('Fixed historical case is unavailable in the original sealed context.')
        project_selection.validate_proposal(context,proposal)
        return {'request_id':IDS['primary'],'expected_state_version':context['state_version'],'proposal':proposal}
    body=request_body('primary',lambda:expected(controller.selection_context()),accepted=old is not None)
    context=old['selection_context'] if old else controller.selection_context()
    if canonical(body)!=canonical(expected(context)):fail('Original primary body differs from its sealed context.')
    if old:
        request={'project_id':state['id'],'command':'controller.advance_selection','need':'next_check',
                 'expected_state_version':body['expected_state_version'],'proposal':body['proposal']}
        if old['status']!='completed' or canonical(old['request'])!=canonical(request):
            fail('Original primary is not completed; never redispatch it.')
    else:
        if controller.advance_selection(**body)['status']!='completed':fail('Original primary did not complete.')
    state=project.status();no_unknown(state);check_budget(state,True)
    parent=next(p for p in state['controller_requests'] if p['request_id']==IDS['primary'])
    actions=[a for a in state['actions'] if a['request_id']==parent['child_request_id']]
    if len(actions)!=1 or actions[0]['command']!=staged.TOOL_ID or actions[0]['status']!='completed':
        fail('Original primary child is unavailable or changed.')
    return actions[0]


def atomic_publish_json(path,value):
    """Publish one canonical record without overwriting or accepting partial output."""
    path=safe_path(path);tmp=path.with_name('.'+path.name+'.partial')
    if tmp.exists() or path.exists():fail('Original shadow publication already exists or is incomplete.')
    save_once(tmp,encoded(value))
    os.link(tmp,path,follow_symlinks=False)
    fd=os.open(path.parent,os.O_RDONLY|getattr(os,'O_DIRECTORY',0))
    try:os.fsync(fd)
    finally:os.close(fd)
    tmp.unlink()
    fd=os.open(path.parent,os.O_RDONLY|getattr(os,'O_DIRECTORY',0))
    try:os.fsync(fd)
    finally:os.close(fd)


def shadow_inputs(project,state,action,condition):
    """Read both arms from one already validated primary, without rank or scoring."""
    checked=reader._checked_primary(project,state,action)
    qids=sorted(checked['source']['spec']['query_splits']['validation'])
    if len(qids)!=200 or len(set(qids))!=200:fail('Saved validation coverage differs from the fixed 200.')
    rows=[]
    for qid in qids:
        record={'query_id':qid}
        for method in ('bm25','tfidf_cosine'):
            metrics=checked['metrics'][('validation',qid,method)]['metrics']
            record[method]={k:metrics[k] for k in ('recall@20','mrr@10')}
        rows.append(record)
    pair=checked['summary']['splits']['validation']['paired_candidate_minus_baseline']
    deltas=[r['tfidf_cosine']['recall@20']-r['bm25']['recall@20'] for r in rows]
    aggregate=reader._stability_aggregate(deltas,pair['recall@20'])
    value={'means':[pair[k]['mean'] for k in ('recall@20','mrr@10')],
           'leave_one_out':{'minimum':aggregate['leave_one_out']['minimum'],
                            'maximum':aggregate['leave_one_out']['maximum'],'queries':len(qids)}}
    if not hypothesis_feedback._valid_loo_value(value,condition):fail('Fixed shadow inputs are invalid or incomplete.')
    if project.status()!=state:fail('Project changed while reading fixed validation evidence.')
    return rows,value


def check_live_identity(identity):
    """Check original inputs and active implementation immediately before a shadow decision."""
    if (sha(SCRIPT.read_bytes())!=identity['driver_sha256'] or sha(S046.read_bytes())!=identity['helper_sha256']
            or sha(TESTS.read_bytes())!=identity['test_sha256'] or sha(PROTOCOL.read_bytes())!=PROTOCOL_SHA
            or project_identity()!=identity['project_code_identity'] or controller_identity()!=identity['controller_code_identity']):
        fail('Original driver, protocol, helper, tests or Project/Controller code changed.')
    original=safe_path(SOURCE)
    if original.stat().st_size!=SOURCE_BYTES or sha(original.read_bytes())!=SOURCE_SHA:
        fail('Original public source changed before decision.')
    protocol=staged._parse(PROTOCOL.read_bytes())
    if case_bytes(protocol)!=(WORKSPACE/'private/case.canonical.json').read_bytes():
        fail('Original historical case source changed before decision.')


def shadow_and_anchor(project,action,identity,*,readonly=False):
    """Seal the shadow comparison and add its hash as an unverified Project statement."""
    from autoresearch import project_experience_dispatch, project_experience_binding
    check_live_identity(identity)
    state=project.status(); raw=safe_path(WORKSPACE/'private/case.canonical.json').read_bytes()
    if len(raw)!=1180182 or sha(raw)!=CASE_CANONICAL_SHA:fail('Original shadow case bytes changed before decision.')
    case=project_experience_dispatch.parse_bundle(raw)
    if encoded(case)!=raw or (case['id'],case['version'],case['record']['id'])!=(
            's065-hotpot-support-history',1,'266a07d2f8af2e40a208a6c7d3382265e62700225ad4b5ade8078b3d4a92b363'):
        fail('Original shadow case identity changed before decision.')
    revisions=state.get('experience_revisions',[])
    if len(revisions)!=1 or revisions[0].get('bundle_sha256')!=CASE_CANONICAL_SHA or revisions[0].get('inclusion_status')!='active':
        fail('Original active Project case binding changed before decision.')
    _,bound=project_experience_binding._load(project.root,revisions[0])
    if bound!=raw:fail('Original Project case bytes changed before decision.')
    condition=copy.deepcopy(case['record']['provenance']['feedback_history']['registration']['condition'])
    rows,value=shadow_inputs(project,state,action,condition)
    items=hypothesis_feedback.feedback_context(project,state)['items']
    if len(items)!=1 or items[0]['request_id']!=IDS['hypothesis']:fail('Original A feedback binding changed.')
    item=items[0]
    if item['outcome']=='unknown':fail('Original native hypothesis is unknown; do not dispatch continuation.')
    if item['action_id']!=action['id'] or encoded(item['value'])!=encoded(value['means'][0]):
        fail('Original A feedback and same-primary shadow input differ.')
    a='tfidf_cosine' if item['outcome']=='condition_met' else 'bm25'
    b='tfidf_cosine' if hypothesis_feedback._loo_matches(condition,value) else 'bm25'
    if a=='bm25' and b!='bm25':fail('Impossible fixed policy comparison.')
    inputs={'schema_version':'s067-shadow-validation-inputs-v1','rows':rows,'case_sha256':CASE_CANONICAL_SHA,
            'primary_action_id':action['id'],'primary_result_sha256':action['result_sha256']}
    ipath=WORKSPACE/'private/shadow-inputs.json';dpath=WORKSPACE/'private/shadow-decision.json'
    for p in (ipath,dpath):
        if p.with_name('.'+p.name+'.partial').exists():fail('Original shadow publication is incomplete.')
    if ipath.exists()!=dpath.exists():fail('Original shadow records are incomplete; preserve them.')
    saved=read_json(dpath) if dpath.exists() else None
    parent=[p for p in state['controller_requests'] if p['request_id']==IDS['primary']]
    if len(parent)!=1 or parent[0]['status']!='completed':fail('Original primary parent is unavailable.')
    source={'schema_version':'s067-shadow-decision-v1','study_id':STUDY,
            'source_commit':identity['source_commit'],'driver_sha256':identity['driver_sha256'],
            'protocol_sha256':PROTOCOL_SHA,'case_sha256':CASE_CANONICAL_SHA,
            'project_id':state['id'],'run_id':state['run_id'],'source_snapshot_sha256':state['source_snapshot_sha256'],
            'primary_parent_request_sha256':parent[0]['request_sha256'],
            'primary_action_id':action['id'],'primary_result_sha256':action['result_sha256'],
            'registration_sha256':item['registration_sha256'],
            'plan_sha256':state['hypothesis_registrations'][0]['plan_sha256'],
            'plan_version':state['hypothesis_registrations'][0]['plan_version'],
            'native_A_condition':item['condition'],
            'native_A_value':item['value'],'native_A_outcome':item['outcome'],'native_A_method':a,
            'shadow_B_condition':condition,'shadow_B_value':value,'shadow_B_method':b,
            'validation_inputs_sha256':sha(encoded(inputs)),
            'state_version':saved['state_version'] if saved else state['state_version'],
            'snapshot_ref':saved['snapshot_ref'] if saved else state['snapshot_ref']}
    if saved:
        if canonical(read_json(ipath))!=canonical(inputs) or canonical(saved)!=canonical(source):
            fail('Original shadow inputs, decision or binding changed.')
    else:
        if readonly:fail('Original shadow decision is missing.')
        if len(state['actions'])!=1 or any(x.get('request_id')==IDS['shadow_anchor'] for x in state.get('researcher_feedback',[])):
            fail('Cannot reconstruct a missing original shadow decision after subsequent work.')
        atomic_publish_json(ipath,inputs)
        atomic_publish_json(dpath,source)
    feedbacks=[x for x in state.get('researcher_feedback',[]) if x['request_id']==IDS['shadow_anchor']]
    if len(feedbacks)>1:fail('Original shadow anchor is ambiguous.')
    fixed={'request_id':IDS['shadow_anchor'],'author':'S067 fixed driver',
           'comment':'sha256:'+sha(encoded(source)),
           'next_step':'Unverified host statement: apply the original native conditional request.',
           'action_id':action['id']}
    if readonly and (not feedbacks or not (WORKSPACE/'requests/shadow-anchor.json').is_file()):
        fail('Original shadow anchor or body is missing.')
    body=request_body('shadow-anchor',lambda:{**fixed,'expected_state_version':source['state_version']},accepted=bool(feedbacks))
    require_body(body,fixed,source['state_version'])
    if not feedbacks and (state['state_version']!=source['state_version'] or state['snapshot_ref']!=source['snapshot_ref']):
        fail('Original pre-anchor snapshot changed; do not recreate or dispatch.')
    if feedbacks:
        result=feedbacks[0]
        if (result['based_on_state_version']!=body['expected_state_version']
                or any(result.get(k)!=body[k] for k in ('request_id','author','comment','next_step','action_id'))):
            fail('Original shadow anchor differs from its saved request.')
    else:
        if readonly:fail('Original shadow anchor is missing.')
        result=project.record_feedback(**body)
    if result['content_trust']!='unverified_researcher_statement':fail('Original shadow anchor trust changed.')
    return source


def verify_resume_manager(manager_path,seed,identity):
    """Reject missing/corrupt original SQLite before constructing any writer."""
    try:
        manager=LocalWorkbench.open_readonly(manager_path)
        import_body={'request_id':IDS['import'],'workspace':str(seed),'platform_run':None}
        digest=fingerprint(import_body);target=manager_path/'projects'/digest
        with manager._connect(readonly=True) as con:
            for table,columns in {'metadata':['key','value'],'projects':['id','goal','slot','report'],
                                  'requests':['id','digest','command','record']}.items():
                if [r[1] for r in con.execute('PRAGMA table_info('+table+')')]!=columns:
                    fail('Original manager schema is missing or changed.')
            projects=list(con.execute('SELECT id,slot FROM projects'))
            if len(projects)>1 or any(r['id']!=identity['project_id'] or r['slot']!=digest for r in projects):
                fail('Original manager project binding changed.')
            active=manager._active(con)
            if active is not None and active!=identity['project_id']:fail('Original active project changed.')
            row=con.execute('SELECT digest,command,record FROM requests WHERE id=?',(IDS['import'],)).fetchone()
            if row is None:
                if projects or not seed.is_dir():fail('Original import intent is missing.')
            else:
                record=json.loads(row['record'])
                if (row['digest']!=digest or row['command']!='import'
                        or record.get('intent',{}).get('project_id')!=identity['project_id']
                        or record.get('intent',{}).get('workspace')!=str(seed)
                        or record.get('intent',{}).get('target_workspace')!=str(target)
                        or record.get('status') not in {'preparing','incomplete','completed'}):
                    fail('Original manager import intent changed.')
                if record['status']=='completed' and (not projects or record.get('result',{}).get('project_id')!=identity['project_id']):
                    fail('Original completed import receipt changed.')
        if seed.is_dir()==target.is_dir():fail('Original seed and managed project are missing or ambiguous.')
        root=seed if seed.is_dir() else target
        if not (root/'project.sqlite').is_file():fail('Original project database is missing; never recreate it.')
        state=ResearchProject(root).status()
        if (state['id']!=identity['project_id'] or state['run_id']!=identity['run_id']
                or state['registration']['source_sha256']!=identity['source_sha256']
                or state['source_snapshot_sha256']!=identity['source_snapshot_sha256']
                or state['code_identity']!=identity['project_code_identity']
                or state['budget']['lineage_ref']!=identity['budget_lineage']):
            fail('Original project database identity changed.')
    except (sqlite3.Error,KeyError,TypeError,ValueError) as exc:
        raise RuntimeError('Original manager or project database is corrupt; preserve its bytes.') from exc


def compare_rules(a,b,final_summary):
    """Predeclared target: same arm and unavailable counterfactual stay unknown."""
    if a not in ('bm25','tfidf_cosine') or b not in ('bm25','tfidf_cosine'):
        return {'outcome':'unknown','reason':'policy_unknown','B_minus_A':None}
    if a==b:
        return {'outcome':'unknown','reason':'same_arm','B_minus_A':None}
    if a!='tfidf_cosine' or b!='bm25':fail('Fixed B cannot choose TFIDF when A chooses BM25.')
    if final_summary is None:return {'outcome':'unknown','reason':'final_unmeasured','B_minus_A':None}
    baseline=final_summary['baseline'];selected=final_summary['selected']
    delta={}
    for metric in ('recall@5','recall@10','recall@20','mrr@10','ndcg@10'):
        x,y=baseline[metric],selected[metric]
        if any(type(v) not in (int,float) or not math.isfinite(v) for v in (x,y)):
            fail('Original final aggregate is invalid.')
        delta[metric]=x-y
    return {'outcome':'condition_met' if delta['mrr@10']>0 and delta['recall@20']>=0 else 'condition_not_met',
            'reason':'different_arms_measured','B_minus_A':delta}


def make_summary(project,state,continuation,identity,prepared,protocol):
    """Allowlisted aggregates only; native report/input remains private."""
    no_unknown(state);check_budget(state,True)
    shadow=shadow_and_anchor(project,state['actions'][0],identity,readonly=True)
    feedback=continuation['conditional']['feedback']
    if not state['actions'] or state['actions'][0]['command']!=staged.TOOL_ID:
        fail('Original primary is unavailable for the summary.')
    action=state['actions'][0]
    try:
        tool=_s046().saved_tool(project,action);saved=staged._saved(tool)
        if saved['source_snapshot_sha256']!=state['source_snapshot_sha256'] or saved['scope']!=state['source_scope']:
            fail('Original primary summary differs from its source.')
    except (ResearchError,RuntimeError,OSError,KeyError,ValueError,TypeError):
        if feedback['outcome']!='unknown':raise
        saved=None
    primary_summary={'action_id':action['id'],'request_id':action['request_id'],'result_sha256':action['result_sha256'],
                     'paired_summary':None if saved is None else copy.deepcopy(saved['paired_summary']),
                     'adverse_query_count':None if saved is None else len(saved['adverse_queries'])}
    if continuation['phase']=='waiting':
        if continuation['result']['status']!='waiting' or len(state['actions'])!=1:
            fail('Original wait does not match its one-action state.')
        final_summary=None;final_status='unmeasured';final_usage=None;final_query_count=None;frozen=None;report_sha=None
    elif continuation['phase']=='done':
        if feedback['outcome'] not in ('condition_met','condition_not_met') or len(state['actions'])!=3:
            fail('Completed final does not match the original known feedback and budget.')
        final_tool=_s046().saved_tool(project,state['actions'][-1]);result=retrieval_holdout.validate_final_result(final_tool)
        verified=retrieval_holdout.verify_holdout(project,state)  # Only after original final completed.
        if verified['sha256']!=state['private_evaluation']['sha256']:fail('Original private holdout changed after final.')
        frozen=state['frozen_evaluation_strategy'];final_summary=copy.deepcopy(result['summary']);final_status='measured'
        final_usage=copy.deepcopy(result['usage']);final_query_count=result['scope']['query_count']
        expected_calls=200 if frozen['selected_method']=='bm25' else 400
        if final_query_count!=200 or final_usage['ranking_calls']!=expected_calls or final_usage['scoring_calls']!=expected_calls:
            fail('Original final coverage or execution usage differs.')
        report_sha=fingerprint(continuation['result']['manifest'])
    else:fail('Original continuation has no verified terminal outcome.')
    visible_feedback={'registration_request_id':feedback['request_id'],'registration_sha256':feedback['registration_sha256'],
                      'condition':copy.deepcopy(feedback['condition']),'outcome':feedback['outcome'],
                      'value':copy.deepcopy(feedback['value']),'unknown_reason':feedback['unknown_reason']}
    return {'schema_version':'s067-study-summary-v1','study_id':STUDY,'source_commit':identity['source_commit'],
            'created_by_owner':prepared['claim']['created_by_owner'],'protocol_sha256':identity['protocol_sha256'],
            'driver_sha256':identity['driver_sha256'],'project_id':state['id'],'run_id':state['run_id'],
            'project_code_identity':state['code_identity'],'project_snapshot_ref':state['snapshot_ref'],
            'original_source_sha256':SOURCE_SHA,'source_snapshot_sha256':state['source_snapshot_sha256'],
            'primary':primary_summary,'feedback':visible_feedback,'conditional_request_id':IDS['conditional'],
            'continuation_phase':continuation['phase'],'selected_method':None if frozen is None else frozen['selected_method'],
            'final_status':final_status,'final_summary':final_summary,'final_query_count':final_query_count,
            'final_usage':final_usage,'internal_report_manifest_sha256':report_sha,
            'actions':[{k:a[k] for k in ('id','request_id','command','status','result_sha256')} for a in state['actions']],
            'budget':copy.deepcopy(state['budget']),'development_usage':{'tokens':'unknown','cost':'unknown'},
            'source_license':protocol['source']['license'],
            'comparison':compare_rules(shadow['native_A_method'],shadow['shadow_B_method'],final_summary),
            'shadow_policy':{'case_sha256':CASE_CANONICAL_SHA,'decision_sha256':sha(encoded(shadow)),
                             'condition':shadow['shadow_B_condition'],'value':shadow['shadow_B_value'],
                             'method':shadow['shadow_B_method'],'native_A_method':shadow['native_A_method']},
            'limitations':['Public input, prior full source and yes/no label exposure, shared corpus; not blind or OS-isolated.',
                 'Full original JSONL including eventual final questions and answer labels is parsed in prepare and verification.',
                 'One author-paired passage is not an exhaustive set of relevant passages; yes/no answer is not a relevance label.',
                 'The fixed historical case informed a human-authored rule, not model learning or a causal effect of memory.',
                 'Both rules on the same arm give an unknown comparison; BM25-only final leaves TFIDF unmeasured.',
                 'Native report, source, historical case and per-query inputs remain private to the local workspace.'],
            'scientific_validation':False}


def terminal_replay(identity,protocol):
    prepared=verify_prepared(identity,protocol)
    if not (WORKSPACE/'manager/workbench.sqlite').is_file() or not (WORKSPACE/'project-identity.json').is_file():
        fail('Original terminal manager or project identity is missing.')
    manager=LocalWorkbench.open_readonly(WORKSPACE/'manager');saved=read_json(WORKSPACE/'project-identity.json')
    body=read_json(WORKSPACE/'requests/conditional.json')
    shadow=read_json(WORKSPACE/'private/shadow-decision.json')
    if type(shadow.get('state_version')) is not int or body.get('expected_state_version')!=shadow['state_version']+1:
        fail('Original conditional version differs from the shadow anchor.')
    with manager._connect(readonly=True) as con:
        row=con.execute("SELECT digest,record FROM requests WHERE id=? AND command='continue_staged'",(IDS['conditional'],)).fetchone()
        if row is None or row['digest']!=fingerprint(body):fail('Original terminal conditional receipt changed.')
        continuation=json.loads(row['record']);_,project=manager._project(con,saved['project_id'])
    manager._check_staged_continuation(continuation,row['digest'])
    if continuation['status']!='completed' or continuation['body']!=body:fail('Original continuation is not terminal.')
    state=project.status()
    if (state['id']!=saved['project_id'] or state['run_id']!=saved['run_id']
            or state['code_identity']!=saved['project_code_identity'] or state['source_snapshot_sha256']!=saved['source_snapshot_sha256']):
        fail('Original terminal project identity changed.')
    if continuation['phase']=='waiting':staged_continuation.verify_conditional_policy(state,body,continuation['conditional'])
    else:manager._verify_completed_staged(continuation,project,row['digest'])
    actual=make_summary(project,state,continuation,identity,prepared,protocol)
    if read_json(WORKSPACE/'summary.json')!=actual:fail('Original terminal summary changed.')
    return actual


def run(identity,protocol,*,resume):
    prepared=verify_prepared(identity,protocol);seed=WORKSPACE/'project-seed';manager_path=WORKSPACE/'manager'
    identity_path=WORKSPACE/'project-identity.json'
    if resume:
        if not (WORKSPACE/'run-start.json').is_file() or not identity_path.is_file() or not (manager_path/'workbench.sqlite').is_file():
            fail('Original project identity or manager database is missing; never recreate it.')
    else:
        if any(p.exists() for p in (WORKSPACE/'run-start.json',identity_path,seed,manager_path)):
            fail('Original study execution already started; use the same project with --resume.')
        started=time.time()
        save_json(WORKSPACE/'run-start.json',{'schema_version':'s067-run-start-v1','study_id':STUDY,
                  'started_unix':started,'deadline_unix':started+1800,'max_wall_seconds':1800})
        save_json(WORKSPACE/'project-create.json',{'study_id':STUDY,'workspace':str(seed),
                  'source_sha256':sha((WORKSPACE/'development/source.json').read_bytes()),'budget_ref':STUDY,
                  'method_id':staged.TOOL_ID,'max_tool_calls':3})
        project=ResearchProject(seed)
        state=project.create(source=WORKSPACE/'development/source.json',goal='S067 fixed BoolQ paired-passage rule comparison',
                             budget_ref=STUDY,max_tool_calls=3,method_id=staged.TOOL_ID)
        save_json(identity_path,{'project_id':state['id'],'run_id':state['run_id'],
                  'source_sha256':state['registration']['source_sha256'],'source_snapshot_sha256':state['source_snapshot_sha256'],
                  'project_code_identity':state['code_identity'],'budget_lineage':STUDY})
    deadline_check();saved_identity=read_json(identity_path)
    if resume:verify_resume_manager(manager_path,seed,saved_identity)
    manager=LocalWorkbench(manager_path)
    import_fixed={'request_id':IDS['import'],'workspace':str(seed),'platform_run':None}
    import_body=request_body('import',lambda:import_fixed,accepted=not seed.exists())
    if import_body!=import_fixed:fail('Original import body changed.')
    deadline_check();imported=manager.import_project(**import_body)
    if imported['project_id']!=saved_identity['project_id']:fail('Original managed import changed identity.')
    select_fixed={'request_id':IDS['select'],'project_id':saved_identity['project_id']}
    select_body=request_body('select',lambda:select_fixed)
    if select_body!=select_fixed:fail('Original selection body changed.')
    deadline_check();manager.select(select_body)
    project,_=manager.binding();state=project.status()
    expected={'project_id':state['id'],'run_id':state['run_id'],'source_sha256':state['registration']['source_sha256'],
              'source_snapshot_sha256':state['source_snapshot_sha256'],'project_code_identity':state['code_identity'],'budget_lineage':STUDY}
    if (saved_identity!=expected or state['registration']['method_id']!=staged.TOOL_ID
            or state['registration']['source_sha256']!=sha((WORKSPACE/'development/source.json').read_bytes())
            or state['source_snapshot_sha256']!=prepared['source_snapshot_sha256']
            or state['code_identity']!=identity['project_code_identity']):
        fail('Original project, source, code or budget lineage changed.')
    project._source(state);no_unknown(state);check_budget(state,bool(state.get('budget_revisions')))
    deadline_check();import_case(project)
    deadline_check();plan_cap_holdout(project,manager)
    deadline_check();hypothesis(project,protocol)
    deadline_check();original=primary(project)
    stop_path=WORKSPACE/'stopped.json'
    if stop_path.exists():fail('Original study was stopped; never redispatch it.')
    try:
        deadline_check();shadow=shadow_and_anchor(project,original,identity)
    except (ResearchError,RuntimeError,OSError,ValueError,TypeError,KeyError) as exc:
        save_json(stop_path,{'schema_version':'s067-stopped-v1','study_id':STUDY,'phase':'shadow',
                             'error_type':type(exc).__name__,'final_status':'unmeasured','final_summary':None,
                             'comparison':{'outcome':'unknown','reason':'shadow_unavailable','B_minus_A':None}})
        raise
    state=project.status();no_unknown(state);check_budget(state,True)
    existing=None
    with manager._connect(readonly=True) as con:
        row=con.execute("SELECT 1 FROM requests WHERE id=? AND command='continue_staged'",(IDS['conditional'],)).fetchone()
    if row is not None:existing=manager.staged_continuation_record(IDS['conditional'])
    fixed={'request_id':IDS['conditional'],'project_id':state['id'],'primary_action_id':original['id'],
           'reason':CONTINUE_REASON,'registration_request_id':IDS['hypothesis']}
    if type(shadow.get('state_version')) is not int:fail('Original shadow state version is invalid.')
    anchor_version=shadow['state_version']+1
    if existing is None and state['state_version']!=anchor_version:
        save_json(stop_path,{'schema_version':'s067-stopped-v1','study_id':STUDY,'phase':'conditional',
                            'error_type':'STATE_CHANGED','final_status':'unmeasured','final_summary':None,
                            'comparison':{'outcome':'unknown','reason':'state_changed','B_minus_A':None}})
        fail('Project state changed after shadow anchor; never dispatch a new conditional.')
    body=request_body('conditional',lambda:{**fixed,'expected_state_version':anchor_version},accepted=existing is not None)
    require_body(body,fixed,anchor_version)
    if existing and canonical(existing['body'])!=canonical(body):fail('Original conditional body changed.')
    stop_path=WORKSPACE/'stopped.json'
    if stop_path.exists():
        read_json(stop_path)
        fail('Original continuation was recorded incomplete; preserve its stop and never redispatch it.')
    deadline_check();continuation=manager.continue_staged(body);state=project.status()
    if continuation['status']!='completed':
        stop={'schema_version':'s067-stopped-v1','study_id':STUDY,'request_id':IDS['conditional'],
              'phase':continuation.get('phase'),'stop':continuation.get('stop'),'project_snapshot_ref':state['snapshot_ref'],
              'final_summary':None,'final_status':'unmeasured',
              'comparison':{'outcome':'unknown','reason':'continuation_incomplete','B_minus_A':None}}
        if not stop_path.exists():save_json(stop_path,stop)
        fail('Original continuation is incomplete; preserve its stop and never substitute a request.')
    summary=make_summary(project,state,continuation,identity,prepared,protocol);output=WORKSPACE/'summary.json'
    if output.exists():
        if read_json(output)!=summary:fail('Original terminal summary changed; never replace it.')
    else:save_json(output,summary)
    return summary


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-commit',required=True)
    mode=parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--prepare',action='store_true');mode.add_argument('--run',action='store_true');mode.add_argument('--resume',action='store_true')
    args=parser.parse_args();identity,protocol=source_pin(args.source_commit)
    if args.prepare:result=prepare(identity,protocol)
    elif args.resume and (WORKSPACE/'summary.json').is_file():result=terminal_replay(identity,protocol)
    else:
        if args.resume:deadline_check()
        elif not (WORKSPACE/'prepared.json').is_file():fail('Prepare the one original source before starting research.')
        if args.resume:
            start=read_json(WORKSPACE/'run-start.json')
            signal.alarm(max(1,int(start['deadline_unix']-time.time())))
        else:signal.alarm(1800)
        try:result=run(identity,protocol,resume=args.resume)
        finally:signal.alarm(0)
    print(canonical(result))


if __name__=='__main__':main()
