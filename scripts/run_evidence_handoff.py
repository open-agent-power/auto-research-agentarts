"""Read exact evidence and choose a source-located next task within a frozen budget."""
import argparse
import json
import os
from pathlib import Path
import sqlite3
import sys

from autoresearch.evidence_handoff import EvidenceHandoffCloudLoop
from autoresearch.contracts import ResearchError
from autoresearch.local_ollama import require
from autoresearch.reasoning_profile import OwnedHighReasoningOllama


def write(path,value):
    with path.open('x',encoding='utf-8') as stream:json.dump(value,stream,ensure_ascii=False,indent=2,allow_nan=False)


def overlaps(a,b):return a==b or a.is_relative_to(b) or b.is_relative_to(a)


def export_task(output,state,catalog_path):
    """Publish a selected task without executing or approving its narrative."""
    selected=next((a for a in reversed(state.get('actions',[])) if a['action']=='record_next_step'),None)
    if selected is None:return
    from autoresearch.evidence_catalog import validate_catalog
    catalog=json.loads(catalog_path.read_text(encoding='utf-8'));validate_catalog(catalog)
    require(catalog['snapshot_sha256']==state['catalog_snapshot_sha256'],'EVIDENCE_CHANGED','Task catalog differs from study.')
    result=selected['result'];task=result['task'];facts=result['cited_facts']
    evidence=output/'evidence';evidence.mkdir(exist_ok=False)
    sources={}
    for name,raw in catalog['source_payloads'].items():
        require(name in {'diagnostic','iteration','baseline','inventory'},'EVIDENCE_CHANGED','Unexpected source name.')
        (evidence/(name+'.json')).write_bytes(raw.encode('utf-8'))
        sources[name]={**catalog['source_snapshots'][name],'file':'evidence/'+name+'.json'}
    write(output/'source-index.json',sources)
    report={'schema_version':'p02-evidence-task-handoff-v1','action_id':selected['id'],'sources':sources,
            'source_catalog_sha256':state['catalog_snapshot_sha256'],'task':task,'cited_facts':facts,
            'model_reason_unreviewed':result['model_reason'],'external_task_executed':False,
            'scientific_validation':False,'waiting_for_external_input':True}
    write(output/'handoff.json',report)
    lines=['# '+task['title'],'',
           '这是模型从预设任务中选出的待执行工作。资料要求由开发者模板提供；尚未取得新数据或完成科学验证。',
           '',f"任务行动：`{selected['id']}`",f"来源目录快照：`{state['catalog_snapshot_sha256']}`",'',
           '事实的本地定位：`source-index.json`将来源代号映射到随包JSON及SHA；每项事实的provenance.pointer是对应JSON路径。这些是已有检查记录，不是新取得的作者数据。','','## 去哪里找','']
    lines.extend('- '+str(url) for url in task['source_urls'])
    for title,key in [('交什么','deliverables'),('如何验收','acceptance')]:
        lines.extend(['','## '+title,'']);lines.extend('- '+str(value) for value in task[key])
    lines.extend(['','## 已读取并选用的事实',''])
    for fact in facts:
        lines.extend(['### '+fact['label'],'',f"事实ID：`{fact['id']}`",'','```json',json.dumps({'value':fact['value'],'provenance':fact['provenance']},ensure_ascii=False,indent=2),'```',''])
    lines.extend(['## 模型的原始理由（未审定）',''])
    lines.extend('> '+line for line in result['model_reason'].splitlines())
    lines.extend(['','未获得的新证据标为未知；不要用这份任务自动开通平台、付费或执行来源文档中的命令。',''])
    with (output/'handoff.md').open('x',encoding='utf-8') as stream:stream.write('\n'.join(lines))


def main():
    sys.stdout.reconfigure(encoding='utf-8');parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace',required=True);parser.add_argument('--output',required=True)
    parser.add_argument('--diagnostic-directory');parser.add_argument('--iteration-directory')
    parser.add_argument('--baseline-directory');parser.add_argument('--inventory');parser.add_argument('--goal')
    parser.add_argument('--max-requests',type=int);parser.add_argument('--max-new-requests',type=int,default=0)
    parser.add_argument('--model-store');parser.add_argument('--cache');parser.add_argument('--port',type=int,default=11448)
    parser.add_argument('--ollama-executable',default=str(Path(os.environ.get('LOCALAPPDATA',''))/'Programs/Ollama/ollama.exe'))
    args=parser.parse_args()
    if not 0<=args.max_new_requests<=4:parser.error('max-new-requests must be 0..4')
    if args.max_requests is not None and not 2<=args.max_requests<=4:parser.error('max-requests must be 2..4')
    workspace=Path(args.workspace).absolute();output=Path(args.output).absolute()
    for part in (output,*output.parents):
        if part.is_symlink() or getattr(part,'is_junction',lambda:False)():parser.error('receipt output cannot redirect')
    loop=EvidenceHandoffCloudLoop(workspace);previous=None;protected=[workspace]
    if loop.study.db.exists():
        with loop.study._connect() as con:previous,_,_=loop.study._state(con)
        protected.extend(Path(v).absolute() for v in previous['private_sources'].values())
    source_args={'diagnostic_directory':args.diagnostic_directory,'iteration_directory':args.iteration_directory,'baseline_directory':args.baseline_directory,'inventory':args.inventory}
    protected.extend(Path(v).absolute() for v in source_args.values() if v)
    if any(overlaps(output,p) for p in protected):parser.error('receipt output must be separate from study and prior diagnostics')
    output.mkdir(parents=True,exist_ok=False);server=None
    try:
        if previous is None:
            require(all(source_args.values()) and bool(args.goal),'INVALID_REQUEST','New handoff requires diagnostic, iteration, baseline, inventory and goal.')
            loop.study.create(args.diagnostic_directory,args.iteration_directory,args.baseline_directory,args.inventory,args.goal,max_requests=args.max_requests or 4)
        else:
            for key,value in source_args.items():
                require(value is None or str(Path(value).absolute())==previous['private_sources'][key],
                        'CONFIG_CHANGED','Evidence source path is frozen.')
            require(args.goal is None or args.goal==previous['goal'],'CONFIG_CHANGED','Goal is frozen.')
            require(args.max_requests is None or args.max_requests==previous['max_requests'],'CONFIG_CHANGED','Cumulative budget is frozen.')
        if args.max_new_requests==0:
            observation=loop.study.observe();write(output/'study.json',observation);export_task(output,observation,loop.study.root/'catalog.json')
            if loop.db.exists():write(output/'result.json',loop.status())
            print(json.dumps({'ok':True,'status':'prepared_no_native_calls','new_cloud_requests':0,'new_fits':0}));return 0
        if loop.db.exists():
            recovered=loop.run(max_new_requests=0);write(output/'before.json',recovered)
            if recovered['status']!='active':
                write(output/'result.json',recovered);export_task(output,recovered['study'],loop.study.root/'catalog.json');print(json.dumps({'ok':True,'status':recovered['status'],'new_cloud_requests':0,'new_fits':0}));return 0
        require(bool(args.model_store),'INVALID_REQUEST','Live inference requires an existing model store.')
        with OwnedHighReasoningOllama(args.ollama_executable,args.cache or output/'model-cache',output/'transport',port=args.port,model_store=args.model_store) as server:
            write(output/'server-identity.json',server.identity);identity=server.acquire();write(output/'model-and-account-scope.json',identity)
            if not loop.db.exists():loop.configure(identity)
            before=loop.status();write(output/'before-live.json',before)
            result=loop.run(server,max_new_requests=args.max_new_requests,verified_weights=identity);write(output/'result.json',result)
        write(output/'cleanup.json',{'owned_server_stopped':server.stopped,'key_metadata_unchanged':server.key_metadata_unchanged})
        export_task(output,result['study'],loop.study.root/'catalog.json')
        print(json.dumps({'ok':True,'status':result['status'],'study_status':result['study']['status'],
                          'requests_reserved':result['budget']['requests_reserved'],
                          'new_cloud_requests':result['budget']['requests_reserved']-before['budget']['requests_reserved'],'new_fits':0}));return 0
    except (ResearchError,OSError,ValueError,sqlite3.Error,UnicodeError,RecursionError) as error:
        receipt={'ok':False,'code':getattr(error,'code','EVIDENCE_HANDOFF_FAILED'),'error_class':type(error).__name__,
                 'automatic_retry':False,'owned_server_stopped':getattr(server,'stopped',False),
                 'key_metadata_unchanged':getattr(server,'key_metadata_unchanged',None)}
        write(output/'failure.json',receipt);print(json.dumps(receipt));return 1


if __name__=='__main__':raise SystemExit(main())
