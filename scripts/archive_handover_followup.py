#!/usr/bin/env python3
"""Inventory/create the small Sprint 006 follow-up; parent study archive remains required."""
import argparse
import importlib.util
import json
from pathlib import Path
import stat
import tempfile
import zipfile

REPO=Path(__file__).resolve().parents[1]
WORK=Path('/workspace/work')
OUT=REPO/'runs/sprint-006-delivery'
PARENT=REPO/'runs/sprint-005-delivery/native-cpu-reproduction-evidence.zip'
PARENT_SHA='e320404532fe80fd085ec1dbe07cf6e1abda6d8212a00f8295baa3c9371a1a58'
SUPPLEMENT=REPO/'runs/sprint-006-originals/uci-original-downloads-supplement.zip'
SUPPLEMENT_SHA='1930516373006e6cb44b00d8d43fc512dcc82e44890680b066560f0b013a1cc7'
BASE_COMMIT='e97c0a697ce641081b0a276f5dfa5d1a29762879'
module=importlib.util.spec_from_file_location('prior_delivery',REPO/'scripts/archive_native_cpu_delivery.py')
base=importlib.util.module_from_spec(module);module.loader.exec_module(base)
base.PINNED=[*base.PINNED,BASE_COMMIT]  # Existing bundle verifier, with all three historical pins.
read,sha,save,git,require=base.read,base.sha,base.save,base.git,base.require

MATH=['concrete-v1-rows.jsonl','concrete-v1-summary.json','concrete-v2-rows.jsonl','concrete-v2-summary.json',
      'real-estate-v1-rows.jsonl','real-estate-v1-summary.json','real-estate-v2-rows.jsonl','real-estate-v2-summary.json',
      'slump-v1-rows.jsonl','slump-v1-summary.json','protected-before.json','protected-after.json','manifest.json','result.json']
MATH_REVIEWS=['decision.json','initial-frozen-source-preflight.json','final/author-hand-fixtures.json',
              'final/independent-small-checks.json','final/protected-before.json','final/protected-after.json','final/receipt.json',
              'actual/model-output-audit.json','actual/originals-current.json','actual/receipt.json']
SOURCE_AUDIT=['cases-before.json','cases-after.json','decision.json','receipt.json','reference-heads.json',
              'remote-head.json','saved-artifact-schema.json','supplemental-bindings.json']
REOPEN_COMMON=['archive-validation.json','attempt.json','attempt-final.json','bundle-heads-command.json','bundle-heads.log',
               'host-helper.py','independent-review.json','install-archive-wheel-target-command.json',
               'install-archive-wheel-target.log','prepared.json','recovery-subprocess-command.json',
               'recovery-subprocess.log','target-install.json']
REOPEN_COMMON += [f'{role}-{stage}{suffix}' for role in ('final','release','science')
                  for stage in ('bundle-verify','checkout','clean','clone','head') for suffix in ('-command.json','.log')]
PRECHECK=['bootstrap-fixture-receipt.json','bootstrap-fixture.py','bootstrap-fixture.stderr.log','bootstrap-fixture.stdout.log',
          'failed-recover-protection-receipt.json','outer-protection-before.json','outer-protection-before-02.json',
          'prepare-protection-receipt.json','prepare-02-protection-receipt.json','recover-02-protection-receipt.json',
          'recovery-review.json','recovery-02-review.json','recovery-02-package-origins.json','targeted-checks.json']
PRECHECK += [name+suffix for name in ('prepare','prepare-02','recover','recover-02') for suffix in ('.stderr.log','.stdout.log')]
REOPEN_REVIEWS=['bootstrap-static-review.json','dependency-review.json','static-review.json','prepared-review.json',
                'prepared-02-review.json','recovery-02-independent-results.json','final-review.json',
                'saved-recovery-review-failure-01.json','saved-recovery-review-failure-02.json','saved-recovery-review-failure-03.json',
                'verify_saved_recovery-v1.py','verify_saved_recovery-v2.py','verify_saved_recovery-v3.py','verify_saved_recovery.py']
DOCS=['docs/execution/g6-local/archive-reopen-guide.md','docs/execution/g6-local/archive-reopen-results.json',
      'docs/execution/g6-local/originals-supplement.json','docs/execution/g6-local/archive-reopen-independent-review.md',
      'docs/execution/g6-local/saved-model-arithmetic-protocol.md','docs/execution/g6-local/saved-model-arithmetic-results.md',
      'docs/execution/g6-local/saved-model-arithmetic-results.json','docs/execution/g6-local/saved-model-arithmetic-review.md']


def identity(path):
    import hashlib
    path=Path(path)
    require(path.is_file() and not any(p.is_symlink() for p in (path,*path.parents)),'Regular nonlinked file required')
    with path.open('rb') as stream:value=hashlib.file_digest(stream,'sha256').hexdigest()
    return {'bytes':path.stat().st_size,'sha256':value}


def protections():
    parent=identity(PARENT);require(parent=={'bytes':77407847,'sha256':PARENT_SHA},'Original 77MB parent archive changed')
    supplement=identity(SUPPLEMENT);require(supplement=={'bytes':209918,'sha256':SUPPLEMENT_SHA},'Original UCI supplement changed')
    with zipfile.ZipFile(PARENT) as stream:expected=json.loads(stream.read('delivery-inventory.json'))['protected']
    observed=base.protected();require(len(observed)==494 and observed==expected,'Original 494 live identities changed')
    control_dir=WORK/'g6-archive-reopen-20261113-01'
    expected_controls=json.loads(read(WORK/'g6-archive-reopen-precheck/outer-protection-before-02.json'))['old01_failure_control_sha256']
    require(len(expected_controls)==6,'Exactly six original failed-attempt controls')
    controls={name:identity(control_dir/name) for name in expected_controls}
    require({name:value['sha256'] for name,value in controls.items()}==expected_controls,'Original 01 failure controls changed')
    return {'parent_archive':parent,'uci_supplement':supplement,'original_files':observed,'failure_01_controls':controls}


def inspect(raw,label):
    base.inspect_bytes(raw,label)  # Specified credential shapes + known private runtime ID only.


def entries():
    rows={}
    def add(path,name,role):
        path=Path(path);base.safe_name(name)
        require('.agent' not in path.parts,'Private agent configuration/checkpoints are excluded')
        require(not any(v in name.split('/') for v in ('payload','target','venv','final-source','science-source','release-source')),'No duplicate recovery payload/environment/source checkout')
        raw=read(path,16*1024**2);inspect(raw,str(path));require(name not in rows,'Duplicate explicit archive member')
        rows[name]={'path':name,'source_path':str(path),'bytes':len(raw),'sha256':sha(raw),
                    'mode':path.stat().st_mode&0o777,'role':role}
    def group(root,names,prefix,role):
        for name in names:add(root/name,prefix+'/'+name,role)
    group(REPO/'runs/sprint-006-originals',['uci-original-downloads-supplement.zip','supplement-manifest.json','create-receipt.json'],
          'evidence/uci-originals','Original supplementary package, not rewritten')
    add(REPO/'runs/g6-originals-supplement-review/review.json','evidence/uci-originals/current-readonly-review.json','New dated read-only confirmation, not backdated')
    group(WORK/'g6-saved-model-arithmetic-20261113-01',MATH,'evidence/saved-model-arithmetic','Complete saved arithmetic outputs; no recomputation')
    add(REPO/'runs/sprint-006-arithmetic-execution-20261113-01/frozen-command.json','evidence/saved-model-arithmetic/frozen-command.json','Original pre-execution command')
    group(REPO/'runs/sprint006-saved-model-arithmetic-review-20261113-01',MATH_REVIEWS,'evidence/math-review','Pre/post independent review')
    group(REPO/'runs/sprint006-prediction-reconstruction-audit-20261113-01',SOURCE_AUDIT,'evidence/model-source-audit','Read-only source/schema audit')
    group(WORK,[f'saved-model-arithmetic-hand-fixtures-{i:02d}.json' for i in range(1,5)]+
          ['saved-model-arithmetic-script-f3a9abbd.py','saved-model-arithmetic-script-cb0ff447.py'],
          'evidence/math-preparation','Preserved engineering chronology')
    for number,extra in ((1,['recovery-error.json']),(2,['dependency-bootstrap.json','recovery.json'])):
        group(WORK/f'g6-archive-reopen-20261113-{number:02d}',REOPEN_COMMON+extra,
              f'evidence/archive-reopen-{number:02d}','Recovery controls/logs only; no payload/target/checkouts')
    group(WORK/'g6-archive-reopen-precheck',PRECHECK,'evidence/archive-reopen-observer','Bootstrap/origins/full tree and original ZIP/494 preservation proof')
    group(REPO/'runs/g6-archive-reopen-review',REOPEN_REVIEWS,'evidence/archive-reopen-review','Preserved review failures and completed review')
    group(REPO/'runs/sprint-006-start-20261113-01',
          ['automation-observation.json','push-receipt.json','readonly-services-restart.json','services-protected-before.json'],
          'evidence/startup','Public sanitized observation only; focus/checkpoint/config excluded')
    add(Path(__file__),'evidence/host/archive_handover_followup.py','Exact new packer source')
    return [rows[name] for name in sorted(rows)]


def incremental_scan(commit):
    for pin in base.PINNED:git('merge-base','--is-ancestor',pin,commit)
    objects=git('rev-list','--objects',commit,'^'+BASE_COMMIT).splitlines();counts={};size=0
    for row in objects:
        parts=row.split(b' ',1);oid=parts[0].decode();path=parts[1].decode() if len(parts)==2 else None
        if path is not None:base.safe_name(path);inspect(path.encode(),'new Git path')
        kind=git('cat-file','-t',oid).strip().decode()
        if kind in ('blob','commit','tag'):
            raw=git('cat-file',kind,oid);inspect(raw,'new Git '+kind+' '+oid);size+=len(raw)
        counts[kind]=counts.get(kind,0)+1
    return {'base':BASE_COMMIT,'head':commit,'new_objects':len(objects),'types':counts,'inspected_bytes':size,
            'prior_public_history_repeated':False,'unclassified_secret_shapes_found':False,
            'scope':'Only newly reachable Git objects and explicit current evidence scanned; original three public negative fixtures not rescanned.'}


def source_metadata(commit):
    documents={}
    for name in DOCS:
        current=identity(REPO/name)
        try:raw=git('show',commit+':'+name)
        except Exception:documents[name]={'committed':False,**current};continue
        documents[name]={'committed':sha(raw)==current['sha256'],**current}
    name='scripts/archive_handover_followup.py'
    try:contains=sha(git('show',commit+':'+name))==identity(Path(__file__))['sha256']
    except Exception:contains=False
    return {'packer_committed':contains,'documents':documents,'all_documents_committed':all(v['committed'] for v in documents.values())}


def plan(path):
    path=Path(path).absolute();require(path.parent==WORK and not path.exists(),'Inventory must be a fresh top-level /workspace/work file')
    commit=git('rev-parse','HEAD').decode().strip();files=entries();before=protections()
    scan=incremental_scan(commit);source=source_metadata(commit)
    result={'schema_version':'sprint006-followup-inventory-v1','status':'inventory_only_no_zip_created',
            'source_commit':commit,'source':source,'fixed_pins':base.PINNED,'packer_sha256':identity(Path(__file__))['sha256'],
            'base_helper_sha256':identity(REPO/'scripts/archive_native_cpu_delivery.py')['sha256'],
            'files':files,'file_count':len(files),'uncompressed_evidence_bytes':sum(r['bytes'] for r in files),
            'git_object_disk_bytes_estimate':int(git('rev-list','--disk-usage','--objects',commit).strip()),
            'estimated_zip_bytes_range':[8*1024**2,12*1024**2],
            'parent_required':{'path':str(PARENT),**before['parent_archive']},'protected':before,'incremental_scan':scan,
            'excluded':['parent 77MB ZIP','payload930','target187','source checkouts','venv/dependency cache','private focus/config','platform identifiers/credentials'],
            'generated_at_create':['source/public-history.bundle','README.md','followup-inventory.json','archive-manifest.json']}
    inspect(base.canonical(result),'inventory metadata');require(protections()==before,'Protection changed during inventory')
    save(path,result);print(json.dumps({k:result[k] for k in ('status','source_commit','file_count','uncompressed_evidence_bytes','estimated_zip_bytes_range','source')}))


def verify_zip(path):
    with zipfile.ZipFile(path) as stream:
        require(stream.testzip() is None,'ZIP CRC failed');names=stream.namelist()
        require(len(names)==len(set(names)),'Duplicate ZIP member');manifest=json.loads(stream.read('archive-manifest.json'))
        require(len(manifest['entries'])==len({r['path'] for r in manifest['entries']}),'Duplicate manifest member')
        require(set(names)=={r['path'] for r in manifest['entries']}|{'archive-manifest.json'},'Manifest/member bijection')
        require(all(stat.S_IFMT(info.external_attr>>16) in (0,stat.S_IFREG) for info in stream.infolist()),'Special ZIP member')
        for row in manifest['entries']:
            base.safe_name(row['path']);raw=stream.read(row['path'])
            require(len(raw)==row['bytes'] and sha(raw)==row['sha256'],'ZIP member bytes/SHA mismatch')
        with tempfile.TemporaryDirectory(prefix='followup-bundle-check-') as temporary:
            bundle=Path(temporary)/'source.bundle';bundle.write_bytes(stream.read('source/public-history.bundle'))
            proof=base.bundle_checks(bundle,manifest['source_commit'])
    return {'crc':'all_passed','entry_sha256_and_bytes':'all_matched','manifest_members_one_to_one':True,'bundle':proof,'members':len(names)}


def create(inventory_path):
    inventory_raw=read(inventory_path);inspect(inventory_raw,'frozen followup inventory');inventory=json.loads(inventory_raw)
    require(inventory['schema_version']=='sprint006-followup-inventory-v1','Inventory schema')
    commit=git('rev-parse','HEAD').decode().strip()
    require(commit==inventory['source_commit'],'Final source changed; create a new reviewed inventory')
    require(inventory['packer_sha256']==identity(Path(__file__))['sha256'],'Packer source changed')
    require(inventory['base_helper_sha256']==identity(REPO/'scripts/archive_native_cpu_delivery.py')['sha256']
            ==sha(git('show',commit+':scripts/archive_native_cpu_delivery.py')),'Original reused helper identity changed')
    require(source_metadata(commit)==inventory['source'] and inventory['source']['packer_committed']
            and inventory['source']['all_documents_committed'],'Wait for final committed packer and documents')
    require(entries()==inventory['files'],'Allowlisted evidence changed')
    before=protections();require(before==inventory['protected'],'Original protections changed')
    require(not OUT.exists() and not any(p.is_symlink() for p in (OUT,*OUT.parents)),'Fresh nonlinked delivery root required')
    OUT.mkdir(parents=True)
    try:
        save(OUT/'protected-before.json',before)
        bundle=OUT/'public-history.bundle';git('bundle','create',str(bundle),'HEAD');proof=base.bundle_checks(bundle,commit)
        scan=incremental_scan(commit)
        readme=('Sprint 006 follow-up evidence: independent saved-model arithmetic and archive-only saved recovery.\n'
                'The original 77,407,847-byte parent ZIP is still required for study data/cases and was not modified or repeated.\n'
                'Parent SHA-256: '+PARENT_SHA+'\n'
                'The unchanged 209,918-byte UCI original-download supplement and dated review are included.\n'
                'Clone source/public-history.bundle for the exact final HEAD '+commit+'; GUIDE and this round docs are in that source tree.\n'
                'Exact historical 8e8a206/e638b5f/e97c0a6 commits remain available. Original identities and prior failed attempts are preserved.\n'
                'No research action/reconstruction/replay is executed by this packer. Source scripts are supplied for inspection, not auto-execution.\n'
                'No complete offline dependency mirror, venv, cache or duplicate recovery payload/target is included.\n'
                'Private .agent controls/focus/platform identifiers and credentials are excluded. Source/evidence credential-shape scanning is mechanical, not a universal secret-proof guarantee.\n').encode()
        generated={'source/public-history.bundle':read(bundle),'README.md':readme,'followup-inventory.json':inventory_raw}
        rows=list(inventory['files'])
        for name,raw in generated.items():
            base.safe_name(name)
            if name!='source/public-history.bundle':inspect(raw,name)
            rows.append({'path':name,'bytes':len(raw),'sha256':sha(raw),'mode':0o600,'role':'Generated source/metadata'})
        require(len({r['path'] for r in rows})==len(rows),'Unique final member names')
        manifest={'schema_version':'sprint006-followup-manifest-v1','source_commit':commit,'inventory_sha256':sha(inventory_raw),
                  'entries':rows,'bundle_verification':proof,'parent_archive_sha256':PARENT_SHA}
        raw_manifest=base.canonical(manifest)+b'\n';inspect(raw_manifest,'final manifest')
        destination=OUT/'sprint006-handover-followup.zip'
        with zipfile.ZipFile(destination,'x',compression=zipfile.ZIP_DEFLATED) as stream:
            for row in rows:
                name=row['path'];raw=generated[name] if name in generated else read(Path(row['source_path']),16*1024**2)
                require(len(raw)==row['bytes'] and sha(raw)==row['sha256'],'Input changed while archiving')
                info=zipfile.ZipInfo(name);info.compress_type=zipfile.ZIP_DEFLATED
                info.external_attr=(stat.S_IFREG|row['mode'])<<16;stream.writestr(info,raw)
            stream.writestr('archive-manifest.json',raw_manifest)
        verification=verify_zip(destination)
        after=protections();save(OUT/'protected-after.json',after)
        require(before==after and entries()==inventory['files'],'Original or allowlisted evidence changed during create')
        save(OUT/'archive-manifest.json',manifest)
        save(OUT/'create-receipt.json',{'schema_version':'sprint006-followup-create-v1','status':'created_and_verified',
              'source_commit':commit,'archive':str(destination),**identity(destination),'manifest_sha256':sha(raw_manifest),
              'verification':verification,'incremental_scan':scan,'protected_originals':494,'failed_01_controls':6,
              'parent_and_supplement_unchanged':True,'new_research_compute_fit_model_requests':0,
              'dependency_downloads':0,'source_bundle_is_dependency_mirror':False})
        print(json.dumps({'status':'created_and_verified','archive':str(destination),**identity(destination),'members':verification['members']}))
    except BaseException as error:
        save(OUT/'failure.json',{'type':type(error).__name__,'message':str(error),'automatic_retry':False});raise
    finally:
        if not (OUT/'protected-after.json').exists():save(OUT/'protected-after.json',protections())


def main():
    parser=argparse.ArgumentParser(description=__doc__);sub=parser.add_subparsers(dest='operation',required=True)
    p=sub.add_parser('plan');p.add_argument('--inventory',type=Path,required=True)
    c=sub.add_parser('create');c.add_argument('--inventory',type=Path,required=True)
    v=sub.add_parser('verify');v.add_argument('--archive',type=Path,required=True)
    args=parser.parse_args()
    if args.operation=='plan':plan(args.inventory)
    elif args.operation=='create':create(args.inventory)
    else:print(json.dumps(verify_zip(args.archive)))


if __name__=='__main__':
    main()
