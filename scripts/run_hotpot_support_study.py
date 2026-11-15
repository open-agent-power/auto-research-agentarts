#!/usr/bin/env python3
"""S065 fixed HotpotQA preparation and native continuation; no model calls.

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
_PRIVATE_CACHE = tempfile.TemporaryDirectory(prefix='s065-python-cache-')
sys.pycache_prefix = _PRIVATE_CACHE.name
sys.dont_write_bytecode = True
for _thread in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS'):
    os.environ[_thread] = '1'

from autoresearch import (method_registry, project_selection, retrieval_holdout, staged_relevance_adapter as staged,
                          hypothesis_feedback, staged_continuation, relevance_retrieval_adapter as relevance)
from autoresearch.contracts import ResearchError, canonical, fingerprint
from autoresearch.local_workbench import LocalWorkbench
from autoresearch.project_controller import ProjectController, code_identity as controller_identity
from autoresearch.research_project import ResearchProject, code_identity as project_identity, safe_path

REPO=Path(__file__).resolve().parent.parent
SCRIPT=Path(__file__).resolve()
PROTOCOL=REPO/'docs/execution/g5-local/hotpot-support-protocol-v1.json'
S046=REPO/'scripts/run_squad_paragraph_study.py'
S054=REPO/'scripts/run_squad_train_conditional_study.py'
STUDY='s065-hotpot-support-v1'
WORKSPACE=REPO/'runs'/STUDY
CLAIM=REPO.parent/'.study-claims'/(STUDY+'.json')
SOURCE=Path('/workspace/reference-exploration-20261115/hotpotqa/hotpot-dev-distractor-v1-raglab-original-bytes.json')
SOURCE_SHA='4e9ecb5c8d3b719f624d66b60f8d56bf227f03914f5f0753d6fa1b359d7104ea'
SOURCE_BYTES=46320117
PROTOCOL_SHA='3772acf2ba1a458a0bae834205b77b840deaeae70fb33d5a1e64b23aeb0f5fef'
LEASE=Path('/workspace/development-continuation-20261114/auto-research-agentarts/.agent/autonomy/lease.json')
SEED='s065-hotpot-question-v1:'
IDS={'plan':'s065-plan','evidence_cap':'s065-zero-evidence','holdout':'s065-holdout',
     'hypothesis':'s065-hypothesis','primary':'s065-primary','conditional':'s065-conditional',
     'import':'s065-import','select':'s065-select'}
PLAN={'question':'Does fixed HotpotQA validation support-document retrieval satisfy the preregistered joint stability condition?',
      'basis':'Public HotpotQA distractor development data, procedural splits and shared corpus; no blindness claim.',
      'steps':'Run the fixed lexical pair; either known preregistered outcome selects its saved audit and mapped final method.',
      'expected_feedback':'Preserve validation recall and MRR deltas, leave-one-out bound, adverse results, zeros and unknowns.'}
PLAN_REASON='Apply the fixed S065 supporting-document protocol.'
CAP_REASON='S065 authorizes no evidence-source actions.'
CONTINUE_REASON='Apply the original preregistered feedback audit and fixed final-method mapping.'
PROVIDER={'kind':'operator_assistant','label':'S065 fixed preregistered protocol'}
RATIONALE='Execute the original S065 validation pair under the fixed source and budget.'


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


def derive_source(rows, *, split_size=100, expected_rows=7405):
    """Pure structural conversion. Only synthetic rows may be used before publication.

    Returns development assets, private final data and source attribution sidecar.
    No ranking, scoring, fitting, model, Project or network operations.
    """
    if type(rows) is not list or len(rows)!=expected_rows or type(split_size) is not int or split_size<1:
        fail('Original source count or fixed split size differs.')
    ids=set();groups={}
    for row in rows:
        if type(row) is not dict or not {'_id','question','context','supporting_facts'}<=set(row):
            fail('Original source row is missing required fields.')
        qid=row['_id'];question=row['question']
        if type(qid) is not str or re.fullmatch(r'[A-Za-z0-9_.:-]{1,78}',qid) is None or qid in ids:
            fail('Original query ID is invalid, duplicated or too long.')
        if not _check_text(question,maximum=staged.LIMITS['max_query_text']):
            fail('Original question is invalid or too long.')
        ids.add(qid);key=unicodedata.normalize('NFC',' '.join(question.split())).casefold()
        old=groups.get(key)
        if old is None or qid.encode('utf-8')<old['_id'].encode('utf-8'):groups[key]=row
    ordered=sorted(groups.values(),key=lambda r:(sha((SEED+r['_id']).encode('utf-8')),r['_id'].encode('utf-8')))
    if len(ordered)<3*split_size:fail('Insufficient distinct normalized questions; do not replace or reseed.')
    chosen=ordered[:3*split_size]
    sections={'dev':chosen[:split_size],'validation':chosen[split_size:2*split_size],
              'final':chosen[2*split_size:]}
    docs={};titles={};context_by_qid={}
    # All corpus membership is fixed solely from contexts before reading support facts.
    for row in chosen:
        context=row['context']
        if type(context) is not list or not context:fail('Selected original context is invalid.')
        mapped={}
        for entry in context:
            if type(entry) is not list or len(entry)!=2:fail('Original context entry is malformed.')
            title,sentences=entry
            if not _check_text(title,maximum=4096) or type(sentences) is not list or not sentences:
                fail('Original title or sentence list is invalid.')
            if any(not _check_text(s,maximum=131072,empty=True) for s in sentences):
                fail('Original context contains an invalid sentence.')
            if title in mapped:fail('Duplicate title within a context is ambiguous.')
            immutable=tuple(sentences)
            if title in titles and titles[title]!=immutable:
                fail('Same original title has different sentence content across selected contexts.')
            titles[title]=immutable
            docid='d-'+sha(encoded([title,sentences]))
            value={'_id':docid,'title':title,'text':' '.join(sentences),'metadata':{}}
            if not _check_text(value['text'],maximum=131072,empty=True):fail('Original joined document is too long.')
            if docid in docs and docs[docid]!=value:fail('Document hash collision.')
            docs[docid]=value;mapped[title]=(docid,sentences)
        context_by_qid[row['_id']]=mapped
    if len(docs)>staged.LIMITS['max_corpus_rows']:fail('Selected corpus exceeds the original native row limit.')
    split_rows={};sidecar=[]
    for docid,doc in sorted(docs.items()):
        sidecar.append({'doc_id':docid,'title':doc['title'],
                        'wikipedia_url':'https://en.wikipedia.org/wiki/'+quote(doc['title'].replace(' ','_'),safe=''),
                        'wikipedia_dump':'2017-10-01','revision':'unknown'})
    for split,selected in sections.items():
        converted=[]
        for row in selected:
            qid='q-'+row['_id'];facts=row['supporting_facts'];original=context_by_qid[row['_id']]
            if type(facts) is not list or not facts:fail('Original supporting facts are missing.')
            positive=set()
            for fact in facts:
                if (type(fact) is not list or len(fact)!=2 or type(fact[0]) is not str or type(fact[1]) is not int
                        or fact[0] not in original or not 0<=fact[1]<len(original[fact[0]][1])):
                    fail('Original supporting title or strict sentence coordinate is invalid.')
                positive.add(original[fact[0]][0])
            if not positive or qid in positive:fail('Original positive documents are invalid.')
            converted.append({'qid':qid,'original_id':row['_id'],'text':row['question'],'positive_doc_ids':sorted(positive)})
        split_rows[split]=converted
    qids={r['qid'] for rows_ in split_rows.values() for r in rows_}
    if len(qids)!=3*split_size or qids.intersection(docs):fail('Query and document IDs are not disjoint.')
    corpus=''.join(canonical(docs[k])+'\n' for k in sorted(docs)).encode('utf-8')
    def query_bytes(rows_):return ''.join(canonical({'_id':r['qid'],'text':r['text'],'metadata':{}})+'\n' for r in rows_).encode('utf-8')
    def qrel_bytes(rows_):
        output=io.StringIO(newline='');output.write('query-id\tcorpus-id\tscore\n')
        for r in rows_:
            for docid in r['positive_doc_ids']:output.write(r['qid']+'\t'+docid+'\t1\n')
        return output.getvalue().encode('utf-8')
    public_rows=split_rows['dev']+split_rows['validation']
    return {'corpus':corpus,'queries':query_bytes(public_rows),'qrels':qrel_bytes(public_rows),
            'final_queries':query_bytes(split_rows['final']),'final_qrels':qrel_bytes(split_rows['final']),
            'sidecar':sidecar,'selection':split_rows,'selected_question_count':len(chosen),
            'distinct_questions':len(groups),'original_rows':len(rows),'document_count':len(docs)}


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
    for path in (SCRIPT,PROTOCOL,S046):
        if git('show',commit+':'+path.relative_to(REPO).as_posix())!=path.read_bytes():
            fail('Published driver, protocol or helper bytes changed.')
    publication=_s046().verify_publication(commit)
    raw=safe_path(PROTOCOL).read_bytes()
    if sha(raw)!=PROTOCOL_SHA:fail('The published fixed protocol differs.')
    protocol=staged._parse(raw)
    runtime=method_registry.runtime_dependencies()
    if (protocol.get('schema_version')!='s065-hotpot-support-protocol-v1' or protocol.get('study_id')!=STUDY
            or protocol.get('ids')!=IDS or protocol.get('source',{}).get('path')!=str(SOURCE)
            or protocol['source'].get('bytes')!=SOURCE_BYTES or protocol['source'].get('sha256')!=SOURCE_SHA
            or protocol.get('preparation',{}).get('order_seed')!=SEED
            or protocol['preparation'].get('splits')!={'dev':100,'validation':100,'final':100}
            or protocol['preparation'].get('select_total')!=300
            or protocol.get('budget',{}).get('native_tool_limit')!=3
            or any(protocol['budget'].get(k)!=0 for k in ('model_limit','fit_limit','evidence_action_limit'))
            or protocol['budget'].get('research_concurrency')!=1 or protocol['budget'].get('maximum_wall_seconds')!=1800
            or protocol.get('selection',{}).get('comparisons')!=[{'metric':'recall@20','operator':'gt','threshold':0},
                                                                  {'metric':'mrr@10','operator':'gte','threshold':0}]
            or protocol['selection'].get('leave_one_out')!={'metric':'recall@20','operator':'gt','threshold':0}
            or {k:protocol.get('policy',{}).get(k) for k in ('kind','registration_request_id','condition_met','condition_not_met','unknown')}
               !={'kind':'registered_feedback','registration_request_id':IDS['hypothesis'],
                  'condition_met':'tfidf_cosine','condition_not_met':'bm25','unknown':'stop'}
            or protocol['policy'].get('both_known_branches')!=staged.AUDIT_TOOL_ID
            or '.'.join(map(str,sys.version_info[:3]))!=protocol['runtime']['python']
            or unicodedata.unidata_version!=protocol['runtime']['unicode']
            or runtime!={'numpy':protocol['runtime']['numpy'],'scipy':protocol['runtime']['scipy'],
                         'scikit-learn':protocol['runtime']['sklearn']}):
        fail('Fixed protocol, numerical runtime, budget or policy differs.')
    for module in (staged,retrieval_holdout,method_registry,hypothesis_feedback):
        if not Path(module.__file__).resolve().is_relative_to((REPO/'src').resolve()):
            fail('A project module is not from this source pin.')
    return ({'source_commit':commit,'publication':publication,'protocol_sha256':sha(raw),'driver_sha256':sha(SCRIPT.read_bytes()),
             'helper_sha256':sha(S046.read_bytes()),'project_code_identity':project_identity(),
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
        info=zipfile.ZipInfo('hotpot_dev_distractor_v1.json',(2020,1,1,0,0,0));info.compress_type=zipfile.ZIP_STORED
        archive.writestr(info,raw)
    return stream.getvalue()


def _verify_assets(packet,holdout,selection):
    spec,docs,queries,qrels,_,_=staged._checked(packet)
    if set(selection)!={'dev','validation','final'} or any(len(selection[k])!=100 for k in selection):
        fail('Original selection must retain fixed 100/100/100 rows.')
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


def prepare(identity,protocol):
    # Protocol/source-pin publication is checked before this function is called.
    original_path=safe_path(SOURCE)
    if original_path.stat().st_size!=SOURCE_BYTES:fail('Original source size differs.')
    raw=original_path.read_bytes()
    if len(raw)!=SOURCE_BYTES or sha(raw)!=SOURCE_SHA:fail('Original source bytes or identity differ.')
    safe_path(CLAIM.parent).mkdir(mode=0o700,parents=True,exist_ok=True)
    claim={'schema_version':'s065-study-claim-v1','study_id':STUDY,'workspace':str(WORKSPACE),
           'source_commit':identity['source_commit'],'protocol_sha256':PROTOCOL_SHA,'original_source_sha256':SOURCE_SHA,
           'created_by_owner':current_owner()}
    if WORKSPACE.exists():fail('Original study workspace already exists; never prepare another.')
    save_json(CLAIM,claim)
    WORKSPACE.mkdir(mode=0o700,parents=True,exist_ok=False)
    for name in ('private','development','requests'): (WORKSPACE/name).mkdir(mode=0o700)
    save_json(WORKSPACE/'start.json',{'schema_version':'s065-start-v1','study_id':STUDY,'workspace':str(WORKSPACE),
              'claim_sha256':sha(encoded(claim)),'created_at_utc':datetime.now(timezone.utc).isoformat(),**identity})
    save_once(WORKSPACE/'private/original.json',raw)
    try:
        rows=staged._parse(raw)
        derived=derive_source(rows)
        archive=local_archive(raw);save_once(WORKSPACE/'private/original-local.zip',archive)
        save_json(WORKSPACE/'private/selection.json',derived['selection'])
        sidecar=encoded({'schema_version':'s065-document-attribution-v1','documents':derived['sidecar']})
        save_once(WORKSPACE/'private/document-attribution.json',sidecar)
        receipt={'schema_version':'s065-source-receipt-v1','original_sha256':SOURCE_SHA,'original_bytes':SOURCE_BYTES,
                 'mirror_url':protocol['source']['mirror_url'],'author_expected_metadata':protocol['source']['author_expected_metadata'],
                 'local_archive_sha256':sha(archive),'local_archive_bytes':len(archive),
                 'local_archive_description':'ZIP_STORED generated locally from original JSON; not an upstream ZIP',
                 'document_attribution_sha256':sha(sidecar),'author_license':protocol['license']['dataset'],
                 'wikipedia_dump':protocol['license']['wikipedia_dump'],'revision_and_contributors':'unknown'}
        save_json(WORKSPACE/'private/source-receipt.json',receipt)
        for name,key in (('corpus.jsonl','corpus'),('queries.jsonl','queries'),('qrels.tsv','qrels')):
            save_once(WORKSPACE/'development'/name,derived[key])
        license_text=('HotpotQA dataset: CC BY-SA 4.0, Yang et al.; '+protocol['license']['dataset_author_readme']+'\n'
                      'English Wikipedia 2017-10-01 dump; processed data CC BY-SA 4.0, original Wikipedia CC BY-SA 3.0; '
                      'https://hotpotqa.github.io/wiki-readme.html ; individual revisions and contributors unknown.\n')
        save_once(WORKSPACE/'development/license.md',license_text.encode('utf-8'))
        public_selection={k:derived['selection'][k] for k in ('dev','validation')}
        spec={'schema_version':'staged-relevance-development-spec-v1','dataset_label':'HotpotQA distractor dev fixed supporting-document cohort',
              'source_url':protocol['source']['mirror_url'],
              'attribution':'HotpotQA authors; English Wikipedia 2017-10-01; per-article revisions unknown',
              'license_notes':{'corpus':license_text,'queries_and_qrels':'HotpotQA CC BY-SA 4.0; original annotated supporting titles; unjudged is not nonrelevant.'},
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
        save_json(WORKSPACE/'prepared.json',{'schema_version':'s065-prepared-v1','files':inventory,
                  'source_snapshot_sha256':packet['snapshot_sha256'],'source_sha256':SOURCE_SHA,'claim':claim})
    except BaseException as exc:
        save_json(WORKSPACE/'preparation-failure.json',{'schema_version':'s065-preparation-failure-v1','study_id':STUDY,
                   'error_type':type(exc).__name__,'message':str(exc)[:1000],'claim_sha256':sha(encoded(claim))})
        raise
    return {'status':'prepared','workspace':str(WORKSPACE),'project_created':False,'research_actions':0,'model_calls':0}


def verify_prepared(identity,protocol):
    claim=read_json(CLAIM);start=read_json(WORKSPACE/'start.json');prepared=read_json(WORKSPACE/'prepared.json')
    owner=claim.get('created_by_owner')
    if type(owner) is not str or re.fullmatch(r'[A-Za-z0-9_.:-]{1,120}',owner) is None:fail('Original claim owner is invalid.')
    expected={'schema_version':'s065-study-claim-v1','study_id':STUDY,'workspace':str(WORKSPACE),
              'source_commit':identity['source_commit'],'protocol_sha256':PROTOCOL_SHA,'original_source_sha256':SOURCE_SHA,
              'created_by_owner':owner}
    names={'private/original.json','private/original-local.zip','private/selection.json','private/document-attribution.json',
           'private/source-receipt.json','private/holdout.json','development/corpus.jsonl','development/queries.jsonl',
           'development/qrels.tsv','development/license.md','development/spec.json','development/source.json'}
    if (claim!=expected or start.get('schema_version')!='s065-start-v1' or start.get('study_id')!=STUDY
            or start.get('workspace')!=str(WORKSPACE) or start.get('claim_sha256')!=sha(encoded(claim))
            or any(start.get(k)!=v for k,v in identity.items()) or prepared.get('schema_version')!='s065-prepared-v1'
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
    expected_sidecar={'schema_version':'s065-document-attribution-v1','documents':[
        {'doc_id':docid,'title':docs[docid]['title'],
         'wikipedia_url':'https://en.wikipedia.org/wiki/'+quote(docs[docid]['title'].replace(' ','_'),safe=''),
         'wikipedia_dump':'2017-10-01','revision':'unknown'} for docid in sorted(docs)]}
    if sidecar!=encoded(expected_sidecar):fail('Original document title or attribution sidecar differs from the corpus.')
    # Re-derive only for read-only identity comparison, never to replace an
    # accepted selection. Parsing the original public source again necessarily
    # exposes eventual final rows in this same trusted process.
    original=derive_source(staged._parse(raw))
    if (canonical(original['selection'])!=canonical(selection)
            or original['corpus']!=(WORKSPACE/'development/corpus.jsonl').read_bytes()
            or original['queries']!=(WORKSPACE/'development/queries.jsonl').read_bytes()
            or original['qrels']!=(WORKSPACE/'development/qrels.tsv').read_bytes()
            or original['final_queries']!=holdout['queries_jsonl'].encode('utf-8')
            or original['final_qrels']!=holdout['qrels_tsv'].encode('utf-8')
            or encoded({'schema_version':'s065-document-attribution-v1','documents':original['sidecar']})!=sidecar):
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
            or start['schema_version']!='s065-run-start-v1' or start['study_id']!=STUDY
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
           'conditions':copy.deepcopy(protocol['selection']['comparisons']),
           'leave_one_out':copy.deepcopy(protocol['selection']['leave_one_out']),
           'branches':{'condition_met':copy.deepcopy(branch),'condition_not_met':copy.deepcopy(branch)}}
    fixed={'request_id':IDS['hypothesis'],'hypothesis':value}
    body=request_body('hypothesis',lambda:{**fixed,'expected_state_version':state['state_version']},accepted=old is not None)
    require_body(body,fixed,old['state_version_before'] if old else state['state_version'])
    if old:
        if canonical(old['request'])!=canonical(body) or old['candidate']['method_id']!=staged.TOOL_ID:
            fail('Saved hypothesis differs from its original body.')
    else:project.register_hypothesis(**body)


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
                  'rationale':RATIONALE,'evidence_citation_ids':[]}
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


def make_summary(project,state,continuation,identity,prepared,protocol):
    """Allowlisted aggregates only; native report/input remains private."""
    no_unknown(state);check_budget(state,True)
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
        report_sha=fingerprint(continuation['result']['manifest'])
    else:fail('Original continuation has no verified terminal outcome.')
    visible_feedback={'registration_request_id':feedback['request_id'],'registration_sha256':feedback['registration_sha256'],
                      'condition':copy.deepcopy(feedback['condition']),'outcome':feedback['outcome'],
                      'value':copy.deepcopy(feedback['value']),'unknown_reason':feedback['unknown_reason']}
    return {'schema_version':'s065-study-summary-v1','study_id':STUDY,'source_commit':identity['source_commit'],
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
            'source_license':copy.deepcopy(protocol['license']),
            'limitations':['Public data and shared corpus; not blind or OS-isolated.',
                 'Before protocol publication, one public data-viewer row was loaded in memory for schema only; no ranking or scoring.',
                 'Preparation and input verification parse the entire public source including eventual final questions and labels in the trusted process.',
                 'Annotated supporting documents are incomplete; unjudged does not prove irrelevance.',
                 'Recall and MRR do not establish question answering or multi-hop reasoning.',
                 'BM25 selected-vs-baseline zero is structural and does not measure final TF-IDF.',
                 'Original native report and source packet contain text and remain private.'],
            'scientific_validation':False}


def terminal_replay(identity,protocol):
    prepared=verify_prepared(identity,protocol)
    if not (WORKSPACE/'manager/workbench.sqlite').is_file() or not (WORKSPACE/'project-identity.json').is_file():
        fail('Original terminal manager or project identity is missing.')
    manager=LocalWorkbench.open_readonly(WORKSPACE/'manager');saved=read_json(WORKSPACE/'project-identity.json')
    body=read_json(WORKSPACE/'requests/conditional.json')
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
        save_json(WORKSPACE/'run-start.json',{'schema_version':'s065-run-start-v1','study_id':STUDY,
                  'started_unix':started,'deadline_unix':started+1800,'max_wall_seconds':1800})
        save_json(WORKSPACE/'project-create.json',{'study_id':STUDY,'workspace':str(seed),
                  'source_sha256':sha((WORKSPACE/'development/source.json').read_bytes()),'budget_ref':STUDY,
                  'method_id':staged.TOOL_ID,'max_tool_calls':3})
        project=ResearchProject(seed)
        state=project.create(source=WORKSPACE/'development/source.json',goal='S065 fixed HotpotQA supporting-document retrieval',
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
    deadline_check();plan_cap_holdout(project,manager)
    deadline_check();hypothesis(project,protocol)
    deadline_check();original=primary(project)
    state=project.status();no_unknown(state);check_budget(state,True)
    existing=None
    with manager._connect(readonly=True) as con:
        row=con.execute("SELECT 1 FROM requests WHERE id=? AND command='continue_staged'",(IDS['conditional'],)).fetchone()
    if row is not None:existing=manager.staged_continuation_record(IDS['conditional'])
    fixed={'request_id':IDS['conditional'],'project_id':state['id'],'primary_action_id':original['id'],
           'reason':CONTINUE_REASON,'registration_request_id':IDS['hypothesis']}
    body=request_body('conditional',lambda:{**fixed,'expected_state_version':state['state_version']},accepted=existing is not None)
    require_body(body,fixed,existing['body']['expected_state_version'] if existing else state['state_version'])
    if existing and canonical(existing['body'])!=canonical(body):fail('Original conditional body changed.')
    stop_path=WORKSPACE/'stopped.json'
    if stop_path.exists():
        read_json(stop_path)
        fail('Original continuation was recorded incomplete; preserve its stop and never redispatch it.')
    deadline_check();continuation=manager.continue_staged(body);state=project.status()
    if continuation['status']!='completed':
        stop={'schema_version':'s065-stopped-v1','study_id':STUDY,'request_id':IDS['conditional'],
              'phase':continuation.get('phase'),'stop':continuation.get('stop'),'project_snapshot_ref':state['snapshot_ref'],
              'final_summary':None,'final_status':'unmeasured'}
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
