"""Bounded extraction of submitted evidence coordinates, not scientific assessment."""
import copy
import hashlib
import importlib.metadata
import re
from pathlib import Path

from . import knowledge_sources as guard, evidence_submission
from .contracts import ResearchError, canonical, fingerprint
from .diagnostic_view import read_diagnostic_artifacts
from .handoff_view import read_handoff_artifacts

MAX_CHARS=4000
MAX_TEXT_BYTES=60_000
MAX_CHUNKS=1000


def _require(condition,message):
    if not condition:raise ResearchError('EVIDENCE_CHANGED',message)


def _pointer(document,pointer):
    _require(type(pointer) is str and (pointer=='' or pointer.startswith('/')),'Invalid JSON pointer.')
    value=document
    if pointer=='':return value
    for raw in pointer[1:].split('/'):
        _require(re.search(r'~(?![01])',raw) is None,'Invalid JSON pointer escape.')
        key=raw.replace('~1','/').replace('~0','~')
        if type(value) is dict:
            _require(key in value,'JSON pointer does not exist.');value=value[key]
        elif type(value) is list:
            _require(re.fullmatch(r'0|[1-9][0-9]*',key) is not None and int(key)<len(value),'Invalid JSON array index.');value=value[int(key)]
        else:raise ResearchError('EVIDENCE_CHANGED','JSON pointer traverses a scalar.')
    return value


def _chunk_id(chunk):
    return 'chunk-'+fingerprint({k:chunk[k] for k in ('source_id','source_sha256','locator','start_char','end_char','text_sha256')})


def build_returned_evidence(handoff_directory,diagnostic_directory,submission_directory):
    diagnostic_root=evidence_submission._root(diagnostic_directory);handoff_root=evidence_submission._root(handoff_directory);submission_root=evidence_submission._root(submission_directory)
    diagnostic=guard._json(guard._read(diagnostic_root,'diagnostic.json',3_000_000))
    read_diagnostic_artifacts(diagnostic_root,{'snapshot_sha256':diagnostic.get('iteration_snapshot_sha256')})
    handoff=guard._json(read_handoff_artifacts(handoff_root,diagnostic)['handoff.json']);receipt=evidence_submission.read_submission(submission_root,handoff)
    sources=[{k:copy.deepcopy(s[k]) for k in ('id','sha256','url','media_type','license_note','bytes')} for s in receipt['sources']]
    source_map={source['id']:source for source in receipt['sources']};raw_cache={};pdf_cache={};json_cache={};chunk_map={};claims=[];exclusions=[];warning_count=0
    def raw_for(source):
        if source['id'] not in raw_cache:raw_cache[source['id']]=guard._read(submission_root,source['path'],evidence_submission.MAX_FILE,expected_sha=source['sha256'],expected_bytes=source['bytes'])
        return raw_cache[source['id']]
    def add_text(source,kind,value,text):
        _require(type(text) is str,'Extractor returned a nontext value.')
        _require(len(text.encode('utf-8'))<=MAX_TEXT_BYTES,'Selected text exceeds bound; no truncation performed.')
        if not text:return []
        ids=[]
        for start in range(0,len(text),MAX_CHARS):
            part=text[start:start+MAX_CHARS];locator={'kind':kind,'value':value}
            item={'id':'','label':f"{source['id']} · {kind} {value}",'source_id':source['id'],'source_sha256':source['sha256'],
                  'url':source['url'],'locator':locator,'text':part,'text_sha256':hashlib.sha256(part.encode('utf-8')).hexdigest(),
                  'start_char':start,'end_char':start+len(part),'complete_document':False}
            item['id']=_chunk_id(item)
            if item['id'] in chunk_map:_require(chunk_map[item['id']]==item,'Chunk identity collision.')
            else:chunk_map[item['id']]=item
            ids.append(item['id'])
        return ids
    for finding in receipt['findings']:
        source=source_map[finding['source_id']];loc=finding['locator'];kind=loc['kind'];value=loc['value'];ids=[]
        if kind=='pdf_page':
            _require(re.fullmatch(r'[1-9][0-9]*(?:\s*,\s*[1-9][0-9]*)*',value) is not None,'PDF locator requires comma-separated one-based page numbers.')
            numbers=[int(n.strip()) for n in value.split(',')];_require(len(numbers)<=guard.MAX_PDF_PAGES and len(numbers)==len(set(numbers)),'PDF page list is duplicate or too long.')
            if source['id'] not in pdf_cache:
                texts,warnings=guard._extract_pdf(raw_for(source),guard.PDF_TIMEOUT_SECONDS);pdf_cache[source['id']]=texts;warning_count+=warnings
            texts=pdf_cache[source['id']]
            for number in numbers:
                _require(number<=len(texts),'PDF page locator exceeds the document.')
                page_ids=add_text(source,'pdf_page',str(number),texts[number-1]);ids.extend(page_ids)
                if not page_ids:exclusions.append({'finding_id':finding['id'],'source_id':source['id'],'locator':{'kind':'pdf_page','value':str(number)},'reason':'empty_extracted_text'})
        elif kind=='json_pointer':
            if source['id'] not in json_cache:json_cache[source['id']]=guard._json(raw_for(source))
            value_found=_pointer(json_cache[source['id']],value);text=value_found if type(value_found) is str else canonical(value_found)
            ids=add_text(source,kind,value,text)
            if not ids:exclusions.append({'finding_id':finding['id'],'source_id':source['id'],'locator':copy.deepcopy(loc),'reason':'empty_extracted_text'})
        else:exclusions.append({'finding_id':finding['id'],'source_id':source['id'],'locator':copy.deepcopy(loc),'reason':'unsupported_locator_type'})
        claims.append({**copy.deepcopy(finding),'chunk_ids':ids,'interpretation_status':'pending_scientific_interpretation'})
    chunks=list(chunk_map.values());_require(len(chunks)<=MAX_CHUNKS and sum(len(c['text'].encode('utf-8')) for c in chunks)<=MAX_TEXT_BYTES,'Extracted text exceeds bounded packet; no truncation performed.')
    try:pdf_version=importlib.metadata.version('pypdf')
    except importlib.metadata.PackageNotFoundError:pdf_version='unavailable'
    packet={'schema_version':'p02-returned-evidence-v1','submission_snapshot_sha256':receipt['snapshot_sha256'],'handoff_snapshot_sha256':handoff['snapshot_sha256'],
            'task_id':receipt['task_id'],'contributor':copy.deepcopy(receipt['contributor']),'submission_claims':claims,
            'unresolved_questions':copy.deepcopy(receipt['unresolved_questions']),'sources':sources,'chunks':chunks,'exclusions':exclusions,
            'extractor':{'pdf_worker':'knowledge_sources._extract_pdf','pdf_worker_sha256':hashlib.sha256(guard._PDF_CHILD.encode('utf-8')).hexdigest(),'pdf_extractor_sha256':hashlib.sha256(Path(guard.__file__).read_bytes()).hexdigest(),
                         'pypdf_version':pdf_version,'warning_count':warning_count,'json_values':'strings as decoded; nonstrings use canonical JSON',
                         'limits':'selected coordinates only; code-point offsets; no OCR; extracted contents are untrusted'},'scientific_validation':False}
    packet['snapshot_sha256']=fingerprint(packet);validate_packet(packet);return packet


def validate_packet(packet):
    _require(type(packet) is dict and set(packet)=={'schema_version','submission_snapshot_sha256','handoff_snapshot_sha256','task_id','contributor','submission_claims','unresolved_questions','sources','chunks','exclusions','extractor','scientific_validation','snapshot_sha256'} and packet['schema_version']=='p02-returned-evidence-v1' and packet['scientific_validation'] is False and packet['snapshot_sha256']==fingerprint({k:v for k,v in packet.items() if k!='snapshot_sha256'}),'Returned evidence packet identity changed.')
    _require(guard._digest(packet['submission_snapshot_sha256']) and guard._digest(packet['handoff_snapshot_sha256']) and type(packet['sources']) is list and type(packet['chunks']) is list and type(packet['submission_claims']) is list and type(packet['exclusions']) is list,'Packet source identities or collections invalid.')
    sources={s['id']:s for s in packet['sources']};_require(len(sources)==len(packet['sources']) and all(type(v) is dict and set(v)=={'id','sha256','url','media_type','license_note','bytes'} and guard._digest(v['sha256']) and guard._url(v['url']) is not None and type(v['bytes']) is int and 0<=v['bytes']<=evidence_submission.MAX_FILE for v in sources.values()),'Packet source descriptor changed.')
    _require(sum(v['bytes'] for v in sources.values())<=evidence_submission.MAX_TOTAL,'Source bytes exceed bound.')
    extractor=packet['extractor'];_require(type(extractor) is dict and set(extractor)=={'pdf_worker','pdf_worker_sha256','pdf_extractor_sha256','pypdf_version','warning_count','json_values','limits'} and extractor['pdf_worker']=='knowledge_sources._extract_pdf' and guard._digest(extractor['pdf_worker_sha256']) and guard._digest(extractor['pdf_extractor_sha256']) and type(extractor['pypdf_version']) is str and type(extractor['warning_count']) is int and 0<=extractor['warning_count']<=1_000_000,'Extractor identity invalid.')
    ids=set();groups={};total=0;chunk_index={}
    for c in packet['chunks']:
        _require(type(c) is dict and set(c)=={'id','label','source_id','source_sha256','url','locator','text','text_sha256','start_char','end_char','complete_document'} and c['source_id'] in sources and c['source_sha256']==sources[c['source_id']]['sha256'] and c['url']==sources[c['source_id']]['url'],'Chunk source binding changed.')
        loc=c['locator'];_require(type(loc) is dict and set(loc)=={'kind','value'} and loc['kind'] in {'pdf_page','json_pointer'} and type(loc['value']) is str,'Chunk locator changed.')
        _require(type(c['text']) is str and 1<=len(c['text'])<=MAX_CHARS and type(c['start_char']) is int and c['start_char']>=0 and type(c['end_char']) is int and c['end_char']==c['start_char']+len(c['text']) and c['text_sha256']==hashlib.sha256(c['text'].encode('utf-8')).hexdigest() and c['id']==_chunk_id(c) and c['id'] not in ids and c['complete_document'] is False,'Chunk text or offsets changed.')
        ids.add(c['id']);chunk_index[c['id']]=c;total+=len(c['text'].encode('utf-8'));groups.setdefault((c['source_id'],loc['kind'],loc['value']),[]).append((c['start_char'],c['end_char']))
    _require(len(ids)<=MAX_CHUNKS and total<=MAX_TEXT_BYTES,'Packet text exceeded bound.')
    for intervals in groups.values():
        offset=0
        for start,end in sorted(intervals):_require(start==offset,'Chunk offsets are not contiguous.');offset=end
    claim_index={}
    for claim in packet['submission_claims']:
        _require(type(claim) is dict and set(claim)=={'id','claim','status','source_id','locator','note','locator_validation','chunk_ids','interpretation_status'} and type(claim['id']) is str and claim['id'] not in claim_index and claim['status'] in {'observed','unresolved','conflicting'},'Claim schema or identity invalid.')
        claim_index[claim['id']]=claim
        _require(type(claim) is dict and claim.get('source_id') in sources and claim.get('locator_validation')=='provided_not_verified' and claim.get('interpretation_status')=='pending_scientific_interpretation' and type(claim.get('chunk_ids')) is list and len(claim['chunk_ids'])==len(set(claim['chunk_ids'])) and set(claim['chunk_ids'])<=ids,'Claim references changed.')
        loc=claim.get('locator');_require(type(loc) is dict and set(loc)=={'kind','value'} and type(loc['value']) is str,'Claim locator changed.')
        if loc['kind']=='pdf_page':
            _require(re.fullmatch(r'[1-9][0-9]*(?:\s*,\s*[1-9][0-9]*)*',loc['value']) is not None,'Claim PDF locator invalid.')
            pages={str(int(v.strip())) for v in loc['value'].split(',')}
            _require(all(chunk_index[key]['source_id']==claim['source_id'] and chunk_index[key]['locator']['kind']=='pdf_page' and chunk_index[key]['locator']['value'] in pages for key in claim['chunk_ids']),'Claim PDF chunks do not match submitted pages.')
        elif loc['kind']=='json_pointer':
            _require(all(chunk_index[key]['source_id']==claim['source_id'] and chunk_index[key]['locator']==loc for key in claim['chunk_ids']),'Claim JSON chunks do not match submitted pointer.')
        else:_require(not claim['chunk_ids'],'Unsupported locator cannot name extracted chunks.')
    _require({key for claim in packet['submission_claims'] for key in claim['chunk_ids']}==ids,'An extracted chunk lacks submitted locator provenance.')
    for exclusion in packet['exclusions']:
        _require(type(exclusion) is dict and set(exclusion)=={'finding_id','source_id','locator','reason'} and exclusion['finding_id'] in claim_index and exclusion['source_id']==claim_index[exclusion['finding_id']]['source_id'] and exclusion['reason'] in {'unsupported_locator_type','empty_extracted_text'},'Exclusion identity invalid.')
        loc=exclusion['locator'];declared=claim_index[exclusion['finding_id']]['locator']
        _require(type(loc) is dict and set(loc)=={'kind','value'} and (loc==declared or (declared['kind']=='pdf_page' and loc['kind']=='pdf_page' and loc['value'] in {str(int(v.strip())) for v in declared['value'].split(',')})),'Exclusion locator differs from submission.')
    return None


def read_chunks(packet,ids):
    validate_packet(packet);_require(type(ids) is list and 1<=len(ids)<=8 and all(type(x) is str for x in ids) and len(ids)==len(set(ids)),'Choose 1..8 distinct chunk IDs.')
    index={c['id']:c for c in packet['chunks']};_require(set(ids)<=set(index),'Unknown chunk ID.')
    return [copy.deepcopy(index[x]) for x in ids]
