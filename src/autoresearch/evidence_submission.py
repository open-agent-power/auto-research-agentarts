"""Immutable, task-bound evidence submission; source files are never executed."""
import copy
import hashlib
import os
from pathlib import Path
import re

from . import knowledge_sources as guard
from .chemotopo_delivery import _safe
from .contracts import ResearchError, canonical, fingerprint
from .diagnostic_view import read_diagnostic_artifacts
from .handoff_view import read_handoff_artifacts

MAX_FILE=64*1024*1024
MAX_TOTAL=128*1024*1024
MAX_METADATA=2*1024*1024
ID=re.compile(r'^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$')


def _require(condition,message):
    if not condition:raise ResearchError('INVALID_SUBMISSION',message)


def _root(path):
    value=Path(path).absolute()
    for part in (value,*value.parents):
        _require(not part.is_symlink() and not getattr(part,'is_junction',lambda:False)(),'Redirected directories are not permitted.')
    return value.resolve()


def _text(value,maximum=2000):return type(value) is str and 1<=len(value.strip())<=maximum


def _safe_metadata(value):
    # JSON pointers and HDF5 paths are source coordinates, not local paths.
    copied=copy.deepcopy(value)
    if type(copied) is dict and type(copied.get('findings')) is list:
        for finding in copied['findings']:
            if type(finding) is dict and type(finding.get('locator')) is dict:
                finding['locator']['value']='[source coordinate]'
    return _safe(copied)==copied


def _handoff(handoff):
    _require(type(handoff) is dict and handoff.get('schema_version')=='p02-handoff-view-v1' and handoff.get('snapshot_sha256')==fingerprint({k:v for k,v in handoff.items() if k!='snapshot_sha256'}) and handoff.get('scientific_validation') is False,'Intact handoff required.')
    task=handoff.get('selected_task');_require(type(task) is dict and _text(task.get('id'),64) and _text(handoff.get('selected_action_id'),160) and handoff.get('waiting_for_external_input') is True and handoff.get('external_task_executed') is False,'An actual waiting external task is required.')
    return task


def _validate_input(document,handoff):
    task=_handoff(handoff)
    _require(type(document) is dict and set(document)=={'schema_version','handoff_snapshot_sha256','selected_action_id','task_id','contributor','summary','sources','findings','unresolved_questions'} and document['schema_version']=='p02-evidence-submission-v1','Exact submission schema required.')
    _require(document['handoff_snapshot_sha256']==handoff['snapshot_sha256'] and document['selected_action_id']==handoff['selected_action_id'] and document['task_id']==task['id'],'Submission must bind the exact selected task.')
    contributor=document['contributor'];_require(type(contributor) is dict and set(contributor)=={'role','label'} and contributor['role'] in {'operator_assistant','teammate'} and _text(contributor['label'],120),'Contributor role and bounded label required.')
    _require(_text(document['summary'],4000) and type(document['sources']) is list and 1<=len(document['sources'])<=64 and type(document['findings']) is list and len(document['findings'])<=256 and type(document['unresolved_questions']) is list and len(document['unresolved_questions'])<=128 and all(_text(q,2000) for q in document['unresolved_questions']),'Bounded summary and evidence lists required.')
    sources=set();paths=set()
    for item in document['sources']:
        _require(type(item) is dict and set(item)=={'id','path','sha256','url','media_type','license_note'},'Exact source fields required.')
        _require(type(item['id']) is str and ID.fullmatch(item['id']) is not None and item['id'].casefold() not in sources,'Source IDs must be distinct safe names.')
        sources.add(item['id'].casefold());relative=guard._relative(item['path']);key=str(relative).casefold()
        _require(key not in paths and key!='submission.json' and relative.name.casefold() not in {'manifest.json','receipt.json'},'Source path is reserved or duplicated.')
        paths.add(key)
        _require(guard._digest(item['sha256']) and item['sha256']==item['sha256'].lower() and guard._url(item['url']) is not None and _text(item['media_type'],120) and _text(item['license_note'],2000),'Source hash, URL, media type and license note required.')
    found=set()
    for item in document['findings']:
        _require(type(item) is dict and set(item)=={'id','claim','status','source_id','locator','note'} and type(item['id']) is str and ID.fullmatch(item['id']) is not None and item['id'].casefold() not in found,'Exact, unique finding fields required.')
        found.add(item['id'].casefold());_require(item['status'] in {'observed','unresolved','conflicting'} and type(item['source_id']) is str and item['source_id'].casefold() in sources and any(s['id']==item['source_id'] for s in document['sources']) and _text(item['claim'],4000) and _text(item['note'],4000),'Finding must reference a declared source and bounded text.')
        loc=item['locator'];_require(type(loc) is dict and set(loc)=={'kind','value'} and loc['kind'] in {'pdf_page','json_pointer','xlsx_cell','hdf5_path','text_lines'} and _text(loc['value'],2000),'A provided locator is required.')
    _require(_safe_metadata(document),'Private local paths are not allowed in exported text.')


def create_submission(handoff_directory,diagnostic_directory,input_directory,output_directory):
    handoff_root=_root(handoff_directory);diagnostic_root=_root(diagnostic_directory);input_root=_root(input_directory);target=_root(output_directory)
    for source in (handoff_root,diagnostic_root,input_root):
        _require(not(target==source or target.is_relative_to(source) or source.is_relative_to(target)),'Output must be separate from input and publications.')
    _require(not target.exists(),'Output must be a fresh exclusive directory.')
    diagnostic=guard._json(guard._read(diagnostic_root,'diagnostic.json',3_000_000))
    read_diagnostic_artifacts(diagnostic_root,{'snapshot_sha256':diagnostic.get('iteration_snapshot_sha256')})
    verified=read_handoff_artifacts(handoff_root,diagnostic);handoff=guard._json(verified['handoff.json']);_handoff(handoff)
    document=guard._json(guard._read(input_root,'submission.json',MAX_METADATA));_validate_input(document,handoff)
    captured=[];total=0
    for source in document['sources']:
        raw=guard._read(input_root,source['path'],MAX_FILE,expected_sha=source['sha256']);total+=len(raw)
        _require(total<=MAX_TOTAL,'Total declared source bytes exceed the bound.')
        basename=guard._relative(source['path']).name;path='sources/'+source['id']+'/'+basename
        normalized={**copy.deepcopy(source),'path':path,'bytes':len(raw)};captured.append((normalized,raw))
    findings=[{**copy.deepcopy(f),'locator_validation':'provided_not_verified'} for f in document['findings']]
    receipt={'schema_version':'p02-evidence-submission-receipt-v1','handoff_snapshot_sha256':handoff['snapshot_sha256'],
             'diagnostic_snapshot_sha256':handoff['diagnostic_snapshot_sha256'],'selected_action_id':document['selected_action_id'],
             'task_id':document['task_id'],'contributor':copy.deepcopy(document['contributor']),'summary':document['summary'],
             'sources':[v for v,_ in captured],'findings':findings,'unresolved_questions':copy.deepcopy(document['unresolved_questions']),
             'interpretation_status':'pending_scientific_interpretation','scientific_validation':False,'biological_endpoint_eligible':False}
    receipt['snapshot_sha256']=fingerprint(receipt);receipt_raw=(canonical(receipt)+'\n').encode('utf-8')
    files={v['path']:{'sha256':v['sha256'],'bytes':len(raw)} for v,raw in captured}
    manifest={'schema_version':'p02-evidence-submission-manifest-v1','handoff_snapshot_sha256':handoff['snapshot_sha256'],
              'receipt_sha256':hashlib.sha256(receipt_raw).hexdigest(),'receipt_bytes':len(receipt_raw),'files':files}
    manifest['manifest_sha256']=fingerprint(manifest);manifest_raw=(canonical(manifest)+'\n').encode('utf-8')
    target.mkdir(parents=True,exist_ok=False)
    for item,raw in captured:
        path=target.joinpath(*guard._relative(item['path']).parts);path.parent.mkdir(parents=True,exist_ok=True)
        with path.open('xb') as stream:stream.write(raw)
    with (target/'receipt.json').open('xb') as stream:stream.write(receipt_raw)
    with (target/'manifest.json').open('xb') as stream:stream.write(manifest_raw)
    return receipt


def read_submission(output_directory,handoff):
    task=_handoff(handoff);root=_root(output_directory)
    manifest=guard._json(guard._read(root,'manifest.json',MAX_METADATA))
    _require(type(manifest) is dict and set(manifest)=={'schema_version','handoff_snapshot_sha256','receipt_sha256','receipt_bytes','files','manifest_sha256'} and manifest['schema_version']=='p02-evidence-submission-manifest-v1' and manifest['manifest_sha256']==fingerprint({k:v for k,v in manifest.items() if k!='manifest_sha256'}) and manifest['handoff_snapshot_sha256']==handoff['snapshot_sha256'],'Submission manifest changed.')
    raw=guard._read(root,'receipt.json',MAX_METADATA,expected_sha=manifest['receipt_sha256'],expected_bytes=manifest['receipt_bytes']);receipt=guard._json(raw)
    _require(type(receipt) is dict and receipt.get('schema_version')=='p02-evidence-submission-receipt-v1' and receipt.get('snapshot_sha256')==fingerprint({k:v for k,v in receipt.items() if k!='snapshot_sha256'}) and receipt.get('handoff_snapshot_sha256')==handoff['snapshot_sha256'] and receipt.get('diagnostic_snapshot_sha256')==handoff['diagnostic_snapshot_sha256'] and receipt.get('selected_action_id')==handoff['selected_action_id'] and receipt.get('task_id')==task['id'] and receipt.get('interpretation_status')=='pending_scientific_interpretation' and receipt.get('scientific_validation') is False and receipt.get('biological_endpoint_eligible') is False and _safe_metadata(receipt),'Receipt identity or task changed.')
    receipt_fields={'schema_version','handoff_snapshot_sha256','diagnostic_snapshot_sha256','selected_action_id','task_id','contributor','summary','sources','findings','unresolved_questions','interpretation_status','scientific_validation','biological_endpoint_eligible','snapshot_sha256'}
    _require(set(receipt)==receipt_fields and type(receipt['sources']) is list and type(receipt['findings']) is list,'Exact receipt fields required.')
    source_fields={'id','path','sha256','url','media_type','license_note','bytes'}
    finding_fields={'id','claim','status','source_id','locator','note','locator_validation'}
    _require(all(type(item) is dict and set(item)==source_fields for item in receipt['sources']) and all(type(item) is dict and set(item)==finding_fields and item['locator_validation']=='provided_not_verified' for item in receipt['findings']),'Exact receipt source and finding fields required.')
    reconstructed={'schema_version':'p02-evidence-submission-v1','handoff_snapshot_sha256':receipt['handoff_snapshot_sha256'],
                   'selected_action_id':receipt['selected_action_id'],'task_id':receipt['task_id'],
                   'contributor':receipt['contributor'],'summary':receipt['summary'],
                   'sources':[{k:v for k,v in item.items() if k!='bytes'} for item in receipt['sources']],
                   'findings':[{k:v for k,v in item.items() if k!='locator_validation'} for item in receipt['findings']],
                   'unresolved_questions':receipt['unresolved_questions']}
    _validate_input(reconstructed,handoff)
    _require(type(manifest['files']) is dict and type(receipt.get('sources')) is list and len(manifest['files'])==len(receipt['sources']),'Declared source manifest changed.')
    expected={'manifest.json','receipt.json'};total=0
    for source in receipt['sources']:
        path=source['path'];relative=guard._relative(path)
        _require(len(relative.parts)==3 and relative.parts[0]=='sources' and relative.parts[1]==source['id'] and path in manifest['files'],'Invalid normalized source path.')
        file_info=manifest['files'][path];_require(type(file_info) is dict and set(file_info)=={'sha256','bytes'} and file_info['sha256']==source['sha256'] and file_info['bytes']==source['bytes'],'Source descriptor changed.')
        data=guard._read(root,path,MAX_FILE,expected_sha=file_info['sha256'],expected_bytes=file_info['bytes']);total+=len(data);_require(total<=MAX_TOTAL,'Source total exceeded.');expected.add(path)
    for directory,dirs,files in os.walk(root,followlinks=False):
        for name in dirs+files:
            item=Path(directory)/name;_require(not item.is_symlink() and not getattr(item,'is_junction',lambda:False)(),'Redirected output entry.')
        for name in files:_require((Path(directory)/name).relative_to(root).as_posix() in expected,'Unexpected output file.')
    _require(all(f.get('locator_validation')=='provided_not_verified' for f in receipt.get('findings',[])),'Locator verification status changed.')
    return receipt
