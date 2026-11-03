"""Create or resume a bounded protocol-configured numerical study."""
import argparse
import json
import os
from pathlib import Path
import sqlite3
import sys

from autoresearch.compact_iteration import CompactCloudLoop
from autoresearch.prepared_continuation import create_continuation
from autoresearch.contracts import ResearchError
from autoresearch.local_ollama import require
from autoresearch.ollama_cloud import OwnedCloudOllama


def write(path,value):
    with path.open('x',encoding='utf-8') as stream:
        json.dump(value,stream,ensure_ascii=False,indent=2,allow_nan=False)


def protocol_json(path):
    """No duplicate keys, nonfinite values or unbounded protocol payloads."""
    from autoresearch.chemotopo_experiment_evidence import _safe_file
    def unique(pairs):
        result={}
        for key,value in pairs:
            if key in result:raise ValueError('Duplicate protocol key.')
            result[key]=value
        return result
    def invalid(_):raise ValueError('Nonfinite protocol value.')
    value=json.loads(_safe_file(Path(path).absolute(),65536).decode('utf-8'),
                     object_pairs_hook=unique,parse_constant=invalid)
    require(type(value) is dict,'INVALID_PROTOCOL','Protocol must be a JSON object.')
    return value


def overlaps(left,right):
    return left==right or left.is_relative_to(right) or right.is_relative_to(left)


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace',required=True);parser.add_argument('--output',required=True)
    parser.add_argument('--source-study');parser.add_argument('--iteration-directory');parser.add_argument('--protocol')
    parser.add_argument('--max-new-requests',type=int,default=0)
    parser.add_argument('--model-store');parser.add_argument('--cache');parser.add_argument('--port',type=int,default=11448)
    parser.add_argument('--ollama-executable',default=str(Path(os.environ.get('LOCALAPPDATA',''))/'Programs/Ollama/ollama.exe'))
    args=parser.parse_args()
    if not 0<=args.max_new_requests<=6:parser.error('max-new-requests must be 0..6')
    output=Path(args.output).absolute();workspace=Path(args.workspace).absolute()
    for item in (output,*output.parents):
        if item.is_symlink() or getattr(item,'is_junction',lambda:False)():parser.error('receipt path cannot redirect')
    loop=CompactCloudLoop(workspace);previous=None
    protected=[workspace]
    if loop.study.db.exists():
        with loop.study._connect() as con:previous,_,_=loop.study._state(con)
        protected.extend(Path(value).absolute() for value in previous['private_sources'].values() if value is not None)
    protected.extend(Path(value).absolute() for value in
                     (args.source_study,args.iteration_directory,args.protocol) if value is not None)
    if any(overlaps(output,path) for path in protected):parser.error('receipt output must be separate from study, protocol and evidence')
    output.mkdir(parents=True,exist_ok=False);server=None
    try:
        supplied_protocol=protocol_json(args.protocol) if args.protocol is not None else None
        if previous is None:
            require(bool(args.source_study and args.iteration_directory and supplied_protocol),
                    'INVALID_REQUEST','New study requires a source study, sealed iteration directory and protocol JSON.')
            create_continuation(workspace,args.source_study,args.iteration_directory,supplied_protocol)
        else:
            frozen=previous['private_sources']
            for name in ('source_study','iteration_directory'):
                supplied=getattr(args,name)
                require(supplied is None or str(Path(supplied).absolute())==frozen[name],
                        'CONFIG_CHANGED','Evidence location is frozen; create a new study to change it.')
            require(supplied_protocol is None or supplied_protocol==previous['protocol'],
                    'CONFIG_CHANGED','Protocol and cumulative budgets are frozen.')
        if args.max_new_requests==0:
            state=loop.study.observe();write(output/'study.json',state)
            if loop.db.exists():write(output/'result.json',loop.status())
            print(json.dumps({'ok':True,'status':'prepared_no_native_calls','new_cloud_requests':0,'new_fits':0},ensure_ascii=False));return 0
        if loop.db.exists():
            recovered=loop.run(max_new_requests=0);write(output/'before.json',recovered)
            if recovered['status']!='active':
                write(output/'result.json',recovered)
                print(json.dumps({'ok':True,'status':recovered['status'],'new_cloud_requests':0},ensure_ascii=False));return 0
        require(bool(args.model_store),'INVALID_REQUEST','Live inference requires an existing model store.')
        with OwnedCloudOllama(args.ollama_executable,args.cache or output/'model-cache',output/'transport',
                              port=args.port,model_store=args.model_store) as server:
            write(output/'server-identity.json',server.identity)
            identity=server.acquire();write(output/'model-and-account-scope.json',identity)
            if not loop.db.exists():loop.configure(identity)
            before=loop.status();write(output/'before-live.json',before)
            result=loop.run(server,max_new_requests=args.max_new_requests,verified_weights=identity)
            write(output/'result.json',result)
        write(output/'cleanup.json',{'owned_server_stopped':server.stopped,'key_metadata_unchanged':server.key_metadata_unchanged})
        print(json.dumps({'ok':True,'status':result['status'],'study_status':result['study']['status'],
                          'requests_reserved':result['budget']['requests_reserved'],
                          'new_cloud_requests':result['budget']['requests_reserved']-before['budget']['requests_reserved']},ensure_ascii=False));return 0
    except (ResearchError,OSError,ValueError,sqlite3.Error,UnicodeError,RecursionError) as error:
        receipt={'ok':False,'code':getattr(error,'code','COMPACT_ITERATION_FAILED'),'error_class':type(error).__name__,
                 'automatic_retry':False,'owned_server_stopped':getattr(server,'stopped',False),
                 'key_metadata_unchanged':getattr(server,'key_metadata_unchanged',None)}
        write(output/'failure.json',receipt);print(json.dumps(receipt,ensure_ascii=False));return 1


if __name__=='__main__':raise SystemExit(main())
