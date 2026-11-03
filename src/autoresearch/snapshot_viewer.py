"""Standalone offline P02 snapshot viewer; standard library only, no inference."""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import re
import socket
import stat
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


REQUIRED={'serve.py','README.md','AGENT-START.md','web/index.html','web/app.js','web/app.css','web/vendor-licenses.txt',
          'data/research.json','data/memory.json','reports/baseline-report.pdf','reports/baseline-reproduction.zip'}
OPTIONAL={'data/archive.json','data/iteration.json','figures/prediction.svg','figures/policy-comparison.svg',
          'figures/iteration-comparison.svg','reports/iteration-report.pdf','reports/iteration-reproduction.zip'}
POSTRUN_FILES={'data/postrun.json'}
DIAGNOSTIC_FILES={'data/diagnostic.json','figures/diagnostic-comparison.svg'}
HANDOFF_FILES={'data/handoff.json','reports/evidence-handoff.md'}
SOURCE_PROGRESS_FILES={'data/source-progress.json','reports/source-progress.md'}
PREPARED_INPUT_FILES={'data/prepared-input.json','reports/prepared-input.md'}
SOURCE_CONTINUATION_FILES={'data/source-continuation.json','reports/source-continuation.md'}
PIPELINE_INPUT_FILES={'data/pipeline-input.json','reports/pipeline-input.md'}
PIPELINE_RESEARCH_FILES={'data/pipeline-research.json','reports/pipeline-research.md'}
TABULAR_RESEARCH_FILES={'data/tabular-research.json','reports/tabular-research.md'}
DOSSIER_FILES={'data/research-dossier.json','data/research-dossier-manifest.json','reports/research-dossier.md','reports/research-dossier.pdf'}
RETURN_TEMPLATE='reports/evidence-return-template.zip'
ALLOWED=REQUIRED|OPTIONAL|POSTRUN_FILES|DIAGNOSTIC_FILES|HANDOFF_FILES|SOURCE_PROGRESS_FILES|PREPARED_INPUT_FILES|SOURCE_CONTINUATION_FILES|PIPELINE_INPUT_FILES|PIPELINE_RESEARCH_FILES|TABULAR_RESEARCH_FILES|DOSSIER_FILES|{RETURN_TEMPLATE}
MAX_POSTRUN=3_000_000
MAX_FILE=30_000_000
MAX_TOTAL=60_000_000
MAX_MANIFEST=100_000


def _no_redirect(path):
    for item in (path,*path.parents):
        if item.is_symlink() or getattr(item,'is_junction',lambda:False)():raise ValueError('redirected paths are not accepted')


def _no_alternate_streams(path):
    if os.name!='nt':return
    import ctypes
    from ctypes import wintypes
    class StreamData(ctypes.Structure):
        _fields_=[('size',ctypes.c_longlong),('name',wintypes.WCHAR*296)]
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.FindFirstStreamW.argtypes=[wintypes.LPCWSTR,ctypes.c_int,ctypes.POINTER(StreamData),wintypes.DWORD]
    kernel.FindFirstStreamW.restype=wintypes.HANDLE
    kernel.FindNextStreamW.argtypes=[wintypes.HANDLE,ctypes.POINTER(StreamData)]
    kernel.FindNextStreamW.restype=wintypes.BOOL
    kernel.FindClose.argtypes=[wintypes.HANDLE];kernel.FindClose.restype=wintypes.BOOL
    info=StreamData();handle=kernel.FindFirstStreamW(str(path),0,ctypes.byref(info),0)
    if handle==ctypes.c_void_p(-1).value:
        if ctypes.get_last_error()==38:return
        raise ValueError('cannot verify alternate data streams')
    try:
        while True:
            if info.name.casefold() not in {'::$data',':zone.identifier:$data'}:raise ValueError('alternate data streams are not accepted')
            if not kernel.FindNextStreamW(handle,ctypes.byref(info)):
                if ctypes.get_last_error()!=38:raise ValueError('cannot verify alternate data streams')
                break
    finally:kernel.FindClose(handle)


def _stamp(info):return (info.st_dev,info.st_ino,info.st_size,info.st_mtime_ns)


def _read(path,limit,strict_less=False):
    _no_redirect(path);_no_alternate_streams(path)
    before=path.stat()
    if not stat.S_ISREG(before.st_mode) or before.st_nlink!=1 or before.st_size<0 or (before.st_size>=limit if strict_less else before.st_size>limit):
        raise ValueError('unsafe or oversized bundle file')
    with path.open('rb') as stream:
        if _stamp(os.fstat(stream.fileno()))!=_stamp(before):raise ValueError('bundle file changed before reading')
        value=stream.read(limit+1)
        if len(value)!=before.st_size or _stamp(os.fstat(stream.fileno()))!=_stamp(before):raise ValueError('bundle file changed while reading')
    _no_redirect(path)
    if _stamp(path.stat())!=_stamp(before):raise ValueError('bundle file changed after reading')
    return value


def _object(pairs):
    result={}
    for key,value in pairs:
        if key in result:raise ValueError('duplicate JSON key')
        result[key]=value
    return result


def _json(raw):
    return json.loads(raw.decode('utf-8'),object_pairs_hook=_object,parse_constant=lambda _:(_ for _ in ()).throw(ValueError('nonfinite JSON')))


def _fingerprint(value):
    return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode('utf-8')).hexdigest()


def _hash(value):return isinstance(value,str) and re.fullmatch(r'[0-9a-f]{64}',value) is not None


def load_bundle(root):
    root=Path(os.path.abspath(root));_no_redirect(root)
    if not root.is_dir():raise ValueError('bundle directory required')
    _no_alternate_streams(root)
    manifest_bytes=_read(root/'bundle-manifest.json',MAX_MANIFEST)
    manifest=_json(manifest_bytes)
    fields={'schema_version','baseline_snapshot_sha256','iteration_snapshot_sha256','files'}
    if (type(manifest) is not dict or not fields<=set(manifest)<=fields|{'postrun_snapshot_sha256','diagnostic_snapshot_sha256','handoff_snapshot_sha256','source_progress_snapshot_sha256','prepared_input_snapshot_sha256','source_continuation_snapshot_sha256','pipeline_input_snapshot_sha256','pipeline_research_snapshot_sha256','tabular_research_snapshot_sha256','dossier_snapshot_sha256'}
        or manifest['schema_version']!='p02-handoff-bundle-v1' or not _hash(manifest['baseline_snapshot_sha256'])
        or not (manifest['iteration_snapshot_sha256'] is None or _hash(manifest['iteration_snapshot_sha256']))
        or type(manifest['files']) is not dict):raise ValueError('invalid bundle manifest')
    names=set(manifest['files'])
    if not REQUIRED<=names or not names<=ALLOWED:raise ValueError('unexpected or missing bundle file')
    has_postrun=bool(names&POSTRUN_FILES)
    if has_postrun!=('postrun_snapshot_sha256' in manifest):raise ValueError('postrun snapshot or file missing')
    if has_postrun and (manifest['iteration_snapshot_sha256'] is None or not _hash(manifest['postrun_snapshot_sha256'])):
        raise ValueError('postrun requires an iteration and valid snapshot')
    has_diagnostic='data/diagnostic.json' in names
    if has_diagnostic!=('diagnostic_snapshot_sha256' in manifest) or (not has_diagnostic and bool(names&DIAGNOSTIC_FILES)):
        raise ValueError('diagnostic snapshot or file missing')
    if has_diagnostic and (manifest['iteration_snapshot_sha256'] is None or not _hash(manifest['diagnostic_snapshot_sha256'])):
        raise ValueError('diagnostic requires an iteration and valid snapshot')
    has_handoff=bool(names&HANDOFF_FILES)
    if RETURN_TEMPLATE in names and not has_handoff:raise ValueError('return template requires handoff')
    if has_handoff!=('handoff_snapshot_sha256' in manifest) or (has_handoff and (not HANDOFF_FILES<=names or not has_diagnostic or not _hash(manifest['handoff_snapshot_sha256']))):
        raise ValueError('handoff files, snapshot or diagnostic missing')
    has_source_progress=bool(names&SOURCE_PROGRESS_FILES)
    if (has_source_progress!=('source_progress_snapshot_sha256' in manifest)
        or (has_source_progress and (not SOURCE_PROGRESS_FILES<=names or not has_handoff
            or not has_diagnostic or not _hash(manifest['source_progress_snapshot_sha256'])))):
        raise ValueError('source progress files, snapshot, handoff or diagnostic missing')
    has_prepared_input=bool(names&PREPARED_INPUT_FILES)
    if (has_prepared_input!=('prepared_input_snapshot_sha256' in manifest)
        or (has_prepared_input and (not PREPARED_INPUT_FILES<=names or not has_handoff or not _hash(manifest['prepared_input_snapshot_sha256'])))):
        raise ValueError('prepared input requires matching files, snapshot and handoff')
    has_source_continuation=bool(names&SOURCE_CONTINUATION_FILES)
    if (has_source_continuation!=('source_continuation_snapshot_sha256' in manifest)
        or (has_source_continuation and (not SOURCE_CONTINUATION_FILES<=names or not has_source_progress
            or not _hash(manifest['source_continuation_snapshot_sha256'])))):
        raise ValueError('source continuation requires matching files, snapshot and original progress')
    has_pipeline_input=bool(names&PIPELINE_INPUT_FILES)
    if (has_pipeline_input!=('pipeline_input_snapshot_sha256' in manifest)
        or (has_pipeline_input and (not PIPELINE_INPUT_FILES<=names or not has_handoff
            or not _hash(manifest['pipeline_input_snapshot_sha256'])))):
        raise ValueError('pipeline input requires matching files, snapshot and handoff')
    has_pipeline_research=bool(names&PIPELINE_RESEARCH_FILES)
    if (has_pipeline_research!=('pipeline_research_snapshot_sha256' in manifest)
        or (has_pipeline_research and (not PIPELINE_RESEARCH_FILES<=names or not has_pipeline_input
            or not _hash(manifest['pipeline_research_snapshot_sha256'])))):
        raise ValueError('pipeline research requires matching files, snapshot and pipeline input')
    has_tabular_research=bool(names&TABULAR_RESEARCH_FILES)
    if (has_tabular_research!=('tabular_research_snapshot_sha256' in manifest)
        or (has_tabular_research and (not TABULAR_RESEARCH_FILES<=names or not has_prepared_input
            or not _hash(manifest['tabular_research_snapshot_sha256'])))):
        raise ValueError('tabular research requires matching files, snapshot and prepared input')
    has_dossier=bool(names&DOSSIER_FILES)
    if has_dossier!=('dossier_snapshot_sha256' in manifest) or (has_dossier and (not DOSSIER_FILES<=names or not _hash(manifest['dossier_snapshot_sha256']))):
        raise ValueError('dossier files or snapshot missing')
    allowed_dirs={str(Path(name).parent).replace('\\','/') for name in names if '/' in name}
    actual=set()
    for current,dirs,files in os.walk(root,followlinks=False):
        base=Path(current);_no_redirect(base)
        for name in dirs:
            path=base/name;relative=path.relative_to(root).as_posix()
            if relative not in allowed_dirs or ':' in name:raise ValueError('unexpected bundle directory')
            _no_redirect(path);_no_alternate_streams(path)
        for name in files:
            path=base/name;relative=path.relative_to(root).as_posix()
            if ':' in name or relative not in names|{'bundle-manifest.json'}:raise ValueError('unexpected bundle path')
            _no_redirect(path);actual.add(relative)
    if actual!=names|{'bundle-manifest.json'}:raise ValueError('missing bundle path')
    result={};total=len(manifest_bytes)
    for name in sorted(names):
        info=manifest['files'][name]
        if type(info) is not dict or set(info)!={'sha256','bytes'} or not _hash(info['sha256']) or type(info['bytes']) is not int or not 0<=info['bytes']<MAX_FILE:
            raise ValueError('invalid bundle file identity')
        if name in POSTRUN_FILES|{'data/diagnostic.json','data/handoff.json','data/source-progress.json','data/prepared-input.json','data/source-continuation.json','data/pipeline-input.json','data/pipeline-research.json','data/tabular-research.json','data/research-dossier.json'} and info['bytes']>MAX_POSTRUN:raise ValueError('postrun JSON exceeds limit')
        raw=_read(root.joinpath(*name.split('/')),MAX_POSTRUN if name in POSTRUN_FILES else MAX_FILE,
                  strict_less=name not in POSTRUN_FILES);total+=len(raw)
        if total>=MAX_TOTAL or len(raw)!=info['bytes'] or hashlib.sha256(raw).hexdigest()!=info['sha256']:raise ValueError('bundle bytes differ from manifest')
        result[name]=raw
    research=_json(result['data/research.json'])
    if (type(research) is not dict or research.get('schema_version')!='p02-workbench-v1' or research.get('case_id')!='P02-ChemoTopoChip'
        or research.get('scientific_validation') is not False or research.get('snapshot_sha256')!=manifest['baseline_snapshot_sha256']
        or _fingerprint({k:v for k,v in research.items() if k!='snapshot_sha256'})!=manifest['baseline_snapshot_sha256']):raise ValueError('baseline snapshot identity differs')
    if _json(result['data/memory.json'])!=research.get('memory'):raise ValueError('model memory differs from baseline snapshot')
    archive=research.get('archive')
    if (archive is None)!=('data/archive.json' not in names):raise ValueError('archive presence differs from baseline snapshot')
    if archive is not None and _json(result['data/archive.json'])!=archive:raise ValueError('archive differs from baseline snapshot')
    if (research.get('prediction') is not None) and 'figures/prediction.svg' not in names:raise ValueError('prediction figure missing')
    iteration_files={'data/iteration.json','figures/iteration-comparison.svg','reports/iteration-report.pdf','reports/iteration-reproduction.zip'}
    if manifest['iteration_snapshot_sha256'] is None:
        if names & iteration_files:raise ValueError('iteration files require an iteration snapshot')
    else:
        if not iteration_files<=names:raise ValueError('iteration bundle is incomplete')
        iteration=_json(result['data/iteration.json'])
        if (type(iteration) is not dict or iteration.get('schema_version')!='p02-iteration-view-v1' or iteration.get('scientific_validation') is not False
            or iteration.get('snapshot_sha256')!=manifest['iteration_snapshot_sha256']
            or _fingerprint({k:v for k,v in iteration.items() if k!='snapshot_sha256'})!=manifest['iteration_snapshot_sha256']
            or iteration.get('baseline_publication_sha256')!=manifest['baseline_snapshot_sha256']):raise ValueError('iteration snapshot or baseline binding differs')
    if has_postrun:
        allowed_iterations={iteration['snapshot_sha256']}
        prior=iteration.get('prior_evidence',{})
        if type(prior) is not dict:raise ValueError('invalid historical evidence')
        history=prior.get('known_iterations',[])
        if type(history) is not list or len(history)>8:raise ValueError('invalid known iteration list')
        for item in history:
            if type(item) is not dict or not _hash(item.get('snapshot_sha256')):raise ValueError('invalid historical iteration identity')
            allowed_iterations.add(item['snapshot_sha256'])
        postrun=_json(result['data/postrun.json'])
        if (type(postrun) is not dict or postrun.get('schema_version')!='p02-postrun-view-v1' or postrun.get('scientific_validation') is not False
            or postrun.get('snapshot_sha256')!=manifest['postrun_snapshot_sha256']
            or _fingerprint({k:v for k,v in postrun.items() if k!='snapshot_sha256'})!=manifest['postrun_snapshot_sha256']
            or postrun.get('iteration_snapshot_sha256') not in allowed_iterations):raise ValueError('postrun snapshot or iteration binding differs')
    if has_diagnostic:
        diagnostic=_json(result['data/diagnostic.json'])
        if (type(diagnostic) is not dict or diagnostic.get('schema_version')!='p02-diagnostic-view-v1'
            or diagnostic.get('scientific_validation') is not False or diagnostic.get('llm_weight_training') is not False
            or diagnostic.get('snapshot_sha256')!=manifest['diagnostic_snapshot_sha256']
            or _fingerprint({k:v for k,v in diagnostic.items() if k!='snapshot_sha256'})!=manifest['diagnostic_snapshot_sha256']
            or diagnostic.get('iteration_snapshot_sha256')!=manifest['iteration_snapshot_sha256']
            or type(diagnostic.get('topography_chart')) is not list):raise ValueError('diagnostic snapshot or iteration binding differs')
        if bool(diagnostic['topography_chart'])!=('figures/diagnostic-comparison.svg' in names):raise ValueError('diagnostic figure presence differs')
    if has_handoff:
        handoff=_json(result['data/handoff.json'])
        if (type(handoff) is not dict or handoff.get('schema_version')!='p02-handoff-view-v1'
            or handoff.get('scientific_validation') is not False or handoff.get('external_task_executed') is not False
            or handoff.get('snapshot_sha256')!=manifest['handoff_snapshot_sha256']
            or _fingerprint({k:v for k,v in handoff.items() if k!='snapshot_sha256'})!=manifest['handoff_snapshot_sha256']
            or handoff.get('diagnostic_snapshot_sha256')!=manifest['diagnostic_snapshot_sha256']):raise ValueError('handoff snapshot or diagnostic binding differs')
        if RETURN_TEMPLATE in names:
            if not handoff.get('selected_task'):raise ValueError('return template requires selected task')
            with zipfile.ZipFile(io.BytesIO(result[RETURN_TEMPLATE])) as archive:
                entries=archive.infolist()
                if len(entries)>12 or sum(i.file_size for i in entries)>256_000:raise ValueError('return template exceeds limits')
                if len({i.filename for i in entries})!=len(entries):raise ValueError('duplicate template file')
                if {i.filename for i in entries}!={'task-binding.json','contributor.json','summary.txt','sources.csv','findings.csv','questions.txt','sources/README.txt','README.md'}:raise ValueError('unexpected return template file')
                binding=_json(archive.read('task-binding.json'))
            if (binding.get('schema_version')!='p02-evidence-draft-v1'
                or binding.get('handoff_snapshot_sha256')!=handoff['snapshot_sha256']
                or binding.get('selected_action_id')!=handoff['selected_action_id']
                or binding.get('task_id')!=handoff['selected_task']['id']):raise ValueError('return template task binding differs')
    if has_source_progress:
        progress=_json(result['data/source-progress.json'])
        if (type(progress) is not dict or progress.get('schema_version')!='p02-source-assessment-progress-v1'
            or progress.get('scientific_validation') is not False or progress.get('progress_only') is not True
            or progress.get('publication_eligible') is not False or progress.get('automatic_retry') is not False
            or progress.get('task_complete') is not False or progress.get('biological_endpoint_eligible') is not False
            or progress.get('snapshot_sha256')!=manifest['source_progress_snapshot_sha256']
            or _fingerprint({k:v for k,v in progress.items() if k!='snapshot_sha256'})!=manifest['source_progress_snapshot_sha256']
            or not _hash(progress.get('source_snapshot_sha256')) or not _hash(progress.get('submission_snapshot_sha256'))
            or progress.get('handoff_snapshot_sha256')!=manifest['handoff_snapshot_sha256']
            or type(progress.get('execution')) is not dict or progress['execution'].get('new_fits')!=0):
            raise ValueError('source progress identity, qualification or handoff binding differs')
    if has_source_continuation:
        continuation=_json(result['data/source-continuation.json'])
        if (type(continuation) is not dict or continuation.get('schema_version')!='p02-source-continuation-view-v1'
            or continuation.get('scientific_validation') is not False or continuation.get('task_complete') is not False
            or continuation.get('automatic_retry') is not False
            or continuation.get('snapshot_sha256')!=manifest['source_continuation_snapshot_sha256']
            or _fingerprint({k:v for k,v in continuation.items() if k!='snapshot_sha256'})!=manifest['source_continuation_snapshot_sha256']
            or continuation.get('source_progress_snapshot_sha256')!=progress['snapshot_sha256']
            or continuation.get('source_snapshot_sha256')!=progress['source_snapshot_sha256']
            or continuation.get('handoff_snapshot_sha256')!=manifest['handoff_snapshot_sha256']):
            raise ValueError('source continuation identity or original progress binding differs')
    if has_prepared_input:
        prepared=_json(result['data/prepared-input.json'])
        if (type(prepared) is not dict or prepared.get('schema_version')!='p02-tabular-preparation-view-v1'
            or prepared.get('model_read_performed') is not False or prepared.get('scientific_validation') is not False
            or prepared.get('biological_endpoint_eligible') is not False or prepared.get('status')!='prepared'
            or prepared.get('snapshot_sha256')!=manifest['prepared_input_snapshot_sha256']
            or _fingerprint({k:v for k,v in prepared.items() if k!='snapshot_sha256'})!=manifest['prepared_input_snapshot_sha256']
            or prepared.get('handoff_snapshot_sha256')!=manifest['handoff_snapshot_sha256']
            or prepared.get('model_calls')!=0 or prepared.get('new_fits')!=0):raise ValueError('prepared input identity or qualification differs')
    if has_pipeline_input:
        pipeline=_json(result['data/pipeline-input.json'])
        if (type(pipeline) is not dict or pipeline.get('schema_version')!='p02-pipeline-preparation-view-v1'
            or pipeline.get('status')!='prepared' or pipeline.get('configured_settings_only') is not True
            or pipeline.get('execution_proven') is not False or pipeline.get('model_read_performed') is not False
            or pipeline.get('scientific_validation') is not False or pipeline.get('biological_endpoint_eligible') is not False
            or pipeline.get('model_calls')!=0 or pipeline.get('new_fits')!=0
            or pipeline.get('snapshot_sha256')!=manifest['pipeline_input_snapshot_sha256']
            or _fingerprint({k:v for k,v in pipeline.items() if k!='snapshot_sha256'})!=manifest['pipeline_input_snapshot_sha256']
            or pipeline.get('handoff_snapshot_sha256')!=manifest['handoff_snapshot_sha256']):
            raise ValueError('pipeline input identity or configured-only qualification differs')
    if has_pipeline_research:
        view=_json(result['data/pipeline-research.json'])
        if (type(view) is not dict or view.get('schema_version')!='p02-pipeline-research-view-v1'
            or view.get('snapshot_sha256')!=manifest['pipeline_research_snapshot_sha256']
            or _fingerprint({k:v for k,v in view.items() if k!='snapshot_sha256'})!=manifest['pipeline_research_snapshot_sha256']
            or view.get('pipeline_input_snapshot_sha256')!=manifest['pipeline_input_snapshot_sha256']
            or view.get('handoff_snapshot_sha256')!=manifest['handoff_snapshot_sha256']
            or view.get('configured_settings_only') is not True
            or any(view.get(k) is not False for k in ('execution_proven','scientific_validation','biological_endpoint_eligible'))
            or view.get('new_fits')!=0 or view.get('execution',{}).get('new_fits')!=0):
            raise ValueError('pipeline research identity or scope differs')
    if has_tabular_research:
        view=_json(result['data/tabular-research.json'])
        if (type(view) is not dict or view.get('schema_version')!='p02-tabular-research-view-v1'
            or view.get('snapshot_sha256')!=manifest['tabular_research_snapshot_sha256']
            or _fingerprint({k:v for k,v in view.items() if k!='snapshot_sha256'})!=manifest['tabular_research_snapshot_sha256']
            or view.get('prepared_input_snapshot_sha256')!=manifest['prepared_input_snapshot_sha256']
            or view.get('source_snapshot_sha256')!=prepared['packet_snapshot_sha256']
            or view.get('handoff_snapshot_sha256')!=manifest['handoff_snapshot_sha256']
            or any(view.get(k) is not False for k in ('task_complete','scientific_validation','biological_endpoint_eligible'))
            or view.get('execution',{}).get('new_fits')!=0):
            raise ValueError('tabular research identity or prepared source binding differs')
    if has_dossier:
        dossier=_json(result['data/research-dossier.json']);dm=_json(result['data/research-dossier-manifest.json'])
        actual_snapshots={k:v for k,v in manifest.items() if k.endswith('_snapshot_sha256') and k!='dossier_snapshot_sha256'}
        names_map={'research-dossier.json':'data/research-dossier.json','research-dossier.md':'reports/research-dossier.md','research-dossier.pdf':'reports/research-dossier.pdf'}
        identities={k:{'sha256':hashlib.sha256(result[v]).hexdigest(),'bytes':len(result[v])} for k,v in names_map.items()}
        if (type(dossier) is not dict or dossier.get('schema_version')!='p02-research-dossier-v1' or dossier.get('snapshot_sha256')!=manifest['dossier_snapshot_sha256']
            or _fingerprint({k:v for k,v in dossier.items() if k!='snapshot_sha256'})!=manifest['dossier_snapshot_sha256']
            or dossier.get('source_snapshots')!=actual_snapshots or dossier.get('scientific_validation') is not False
            or type(dm) is not dict or dm.get('schema_version')!='p02-research-dossier-export-v1' or dm.get('snapshot_sha256')!=dossier['snapshot_sha256']
            or dm.get('bundle_manifest_sha256')!=dossier.get('bundle_manifest_sha256') or not _hash(dm.get('bundle_manifest_sha256'))
            or dm.get('files')!=identities or dm.get('model_calls')!=0 or dm.get('new_fits')!=0):raise ValueError('dossier source identities or artifacts differ')
    return result


def create_server(bundle,port=0):
    if type(port) is not int or not 0<=port<=65535:raise ValueError('invalid port')
    files=load_bundle(bundle)
    index=files['web/index.html']
    if b'<body>' not in index:raise ValueError('unexpected workbench entrypoint')
    index=index.replace(b'<body>',b'<body data-case="p02">',1)
    routes={'/':(index,'text/html; charset=utf-8',None),'/app.js':(files['web/app.js'],'text/javascript; charset=utf-8',None),
            '/app.css':(files['web/app.css'],'text/css; charset=utf-8',None),'/vendor-licenses.txt':(files['web/vendor-licenses.txt'],'text/plain; charset=utf-8',None)}
    mapped={'/api/p02/research-dossier':('data/research-dossier.json','application/json; charset=utf-8',None),
            '/api/p02/research-dossier.json':('data/research-dossier.json','application/json; charset=utf-8','p02-research-dossier.json'),
            '/api/p02/research-dossier.md':('reports/research-dossier.md','text/markdown; charset=utf-8','p02-research-dossier.md'),
            '/api/p02/research-dossier.pdf':('reports/research-dossier.pdf','application/pdf','p02-research-dossier.pdf'),
            '/api/p02/tabular-research':('data/tabular-research.json','application/json; charset=utf-8',None),
            '/api/p02/tabular-research.json':('data/tabular-research.json','application/json; charset=utf-8','p02-tabular-research.json'),
            '/api/p02/tabular-research.md':('reports/tabular-research.md','text/markdown; charset=utf-8','p02-tabular-research.md'),
            '/api/p02/pipeline-research':('data/pipeline-research.json','application/json; charset=utf-8',None),
            '/api/p02/pipeline-research.json':('data/pipeline-research.json','application/json; charset=utf-8','p02-pipeline-research.json'),
            '/api/p02/pipeline-research.md':('reports/pipeline-research.md','text/markdown; charset=utf-8','p02-pipeline-research.md'),
            '/api/p02/research':('data/research.json','application/json; charset=utf-8',None),
            '/api/p02/research.json':('data/research.json','application/json; charset=utf-8','p02-research.json'),
            '/api/p02/memory.json':('data/memory.json','application/json; charset=utf-8','p02-memory.json'),
            '/api/p02/archive.json':('data/archive.json','application/json; charset=utf-8','p02-operator-archive.json'),
            '/api/p02/iteration':('data/iteration.json','application/json; charset=utf-8',None),
            '/api/p02/iteration.json':('data/iteration.json','application/json; charset=utf-8','p02-iteration.json'),
            '/api/p02/handoff':('data/handoff.json','application/json; charset=utf-8',None),
            '/api/p02/handoff.json':('data/handoff.json','application/json; charset=utf-8','p02-evidence-handoff.json'),
            '/api/p02/handoff.md':('reports/evidence-handoff.md','text/markdown; charset=utf-8','p02-evidence-handoff.md'),
            '/api/p02/evidence-return-template.zip':(RETURN_TEMPLATE,'application/zip','p02-evidence-return-template.zip'),
            '/api/p02/source-progress':('data/source-progress.json','application/json; charset=utf-8',None),
            '/api/p02/source-progress.json':('data/source-progress.json','application/json; charset=utf-8','p02-source-progress.json'),
            '/api/p02/source-progress.md':('reports/source-progress.md','text/markdown; charset=utf-8','p02-source-progress.md'),
            '/api/p02/source-continuation':('data/source-continuation.json','application/json; charset=utf-8',None),
            '/api/p02/source-continuation.json':('data/source-continuation.json','application/json; charset=utf-8','p02-source-continuation.json'),
            '/api/p02/source-continuation.md':('reports/source-continuation.md','text/markdown; charset=utf-8','p02-source-continuation.md'),
            '/api/p02/pipeline-input':('data/pipeline-input.json','application/json; charset=utf-8',None),
            '/api/p02/pipeline-input.json':('data/pipeline-input.json','application/json; charset=utf-8','p02-pipeline-input.json'),
            '/api/p02/pipeline-input.md':('reports/pipeline-input.md','text/markdown; charset=utf-8','p02-pipeline-input.md'),
            '/api/p02/prepared-input':('data/prepared-input.json','application/json; charset=utf-8',None),
            '/api/p02/prepared-input.json':('data/prepared-input.json','application/json; charset=utf-8','p02-prepared-input.json'),
            '/api/p02/prepared-input.md':('reports/prepared-input.md','text/markdown; charset=utf-8','p02-prepared-input.md'),
            '/api/p02/diagnostic':('data/diagnostic.json','application/json; charset=utf-8',None),
            '/api/p02/diagnostic.json':('data/diagnostic.json','application/json; charset=utf-8','p02-diagnostic.json'),
            '/api/p02/diagnostic-comparison.svg':('figures/diagnostic-comparison.svg','image/svg+xml',None),
            '/api/p02/postrun':('data/postrun.json','application/json; charset=utf-8',None),
            '/api/p02/postrun.json':('data/postrun.json','application/json; charset=utf-8','p02-postrun.json'),
            '/api/p02/prediction.svg':('figures/prediction.svg','image/svg+xml',None),
            '/api/p02/policy-comparison.svg':('figures/policy-comparison.svg','image/svg+xml',None),
            '/api/p02/iteration-comparison.svg':('figures/iteration-comparison.svg','image/svg+xml',None),
            '/api/p02/report.pdf':('reports/baseline-report.pdf','application/pdf','p02-research-report.pdf'),
            '/api/p02/reproduction.zip':('reports/baseline-reproduction.zip','application/zip','p02-reproduction.zip'),
            '/api/p02/iteration-report.pdf':('reports/iteration-report.pdf','application/pdf','p02-iteration-report.pdf'),
            '/api/p02/iteration-reproduction.zip':('reports/iteration-reproduction.zip','application/zip','p02-iteration-reproduction.zip')}
    routes.update({url:(files[name],mime,download) for url,(name,mime,download) in mapped.items() if name in files})
    capabilities={'report_pdf':True,'reproduction_zip':True,'iteration_report_pdf':'reports/iteration-report.pdf' in files,'iteration_reproduction_zip':'reports/iteration-reproduction.zip' in files,'research_dossier_pdf':'reports/research-dossier.pdf' in files,'research_dossier_md':'reports/research-dossier.md' in files,'research_dossier_json':'data/research-dossier.json' in files}
    routes['/api/p02/downloads']=(json.dumps(capabilities,separators=(',',':')).encode(),'application/json; charset=utf-8',None)
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def host_ok(self):return self.headers.get_all('Host',[]) in [[f'127.0.0.1:{self.server.server_port}'],[f'localhost:{self.server.server_port}']]
        def send_data(self,status,body,mime,filename=None):
            self.send_response(status);self.send_header('Content-Type',mime);self.send_header('Content-Length',str(len(body)))
            self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff');self.send_header('Referrer-Policy','no-referrer')
            self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'")
            if filename:self.send_header('Content-Disposition',f'attachment; filename="{filename}"')
            self.end_headers();self.wfile.write(body)
        def do_GET(self):
            if not self.host_ok():return self.send_error(403)
            if self.path=='/favicon.ico':self.send_response(204);self.end_headers();return
            if self.path not in routes:return self.send_error(404)
            self.send_data(200,*routes[self.path])
        def deny(self):
            self.close_connection=True
            if not self.host_ok():return self.send_error(403)
            self.send_data(405,b'{"error":"read-only"}','application/json; charset=utf-8')
        do_POST=do_PUT=do_PATCH=do_DELETE=do_OPTIONS=do_HEAD=do_TRACE=do_CONNECT=deny
    class Server(ThreadingHTTPServer):
        allow_reuse_address=False
        def server_bind(self):
            if hasattr(socket,'SO_EXCLUSIVEADDRUSE'):self.socket.setsockopt(socket.SOL_SOCKET,socket.SO_EXCLUSIVEADDRUSE,1)
            super().server_bind()
    server=Server(('127.0.0.1',port),Handler);server.daemon_threads=True
    return server


def main():
    parser=argparse.ArgumentParser(description='Offline, read-only P02 handoff viewer')
    parser.add_argument('--bundle',default=str(Path(__file__).absolute().parent));parser.add_argument('--port',type=int,default=18773)
    parser.add_argument('--check',action='store_true');args=parser.parse_args()
    if args.check:
        load_bundle(args.bundle);print('Bundle verified: read-only snapshot; hashes do not establish scientific validity.');return
    server=create_server(args.bundle,args.port)
    print(f'Read-only snapshot: http://127.0.0.1:{server.server_port}/ (hashes do not establish scientific validity)',flush=True)
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:server.server_close()


if __name__=='__main__':main()
