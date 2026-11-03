"""Create or resume bounded post-run proposal and exact-scope memory work."""
import argparse
import json
import os
from pathlib import Path
import sqlite3
import sys

from autoresearch.postrun_revision import RevisionCloudLoop
from autoresearch.contracts import ResearchError
from autoresearch.local_ollama import require
from autoresearch.ollama_cloud import OwnedCloudOllama


def write(path,value):
    with path.open('x',encoding='utf-8') as stream:
        json.dump(value,stream,ensure_ascii=False,indent=2,allow_nan=False)


def overlaps(left,right):
    return left==right or left.is_relative_to(right) or right.is_relative_to(left)


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace',required=True);parser.add_argument('--output',required=True)
    parser.add_argument('--source-file');parser.add_argument('--postrun-directory')
    parser.add_argument('--memory-workspace');parser.add_argument('--goal')
    parser.add_argument('--max-requests',type=int);parser.add_argument('--max-new-requests',type=int,default=0)
    parser.add_argument('--model-store');parser.add_argument('--cache');parser.add_argument('--port',type=int,default=11448)
    parser.add_argument('--ollama-executable',default=str(Path(os.environ.get('LOCALAPPDATA',''))/'Programs/Ollama/ollama.exe'))
    args=parser.parse_args()
    if not 0<=args.max_new_requests<=6:parser.error('max-new-requests must be 0..6')
    if args.max_requests is not None and not 2<=args.max_requests<=6:parser.error('max-requests must be 2..6')
    output=Path(args.output).absolute();workspace=Path(args.workspace).absolute()
    for path in (output,*output.parents):
        if path.is_symlink() or getattr(path,'is_junction',lambda:False)():parser.error('receipt output cannot redirect')
    loop=RevisionCloudLoop(workspace);previous=None;protected=[workspace]
    if loop.study.db.exists():
        with loop.study._connect() as con:previous,_,_=loop.study._state(con)
        protected.extend(Path(p).absolute() for p in previous['private_sources'].values() if p is not None)
        protected.append(Path(previous['memory_workspace']).absolute())
    protected.extend(Path(p).absolute() for p in (args.source_file,args.postrun_directory,args.memory_workspace) if p)
    if any(overlaps(output,p) for p in protected):parser.error('receipt output must be separate from study, evidence and memory')
    output.mkdir(parents=True,exist_ok=False);server=None
    try:
        if previous is None:
            require(bool(args.source_file and args.postrun_directory and args.memory_workspace and args.goal),
                    'INVALID_REQUEST','New post-run study requires source file, postrun publication, separate memory and goal.')
            maximum=args.max_requests if args.max_requests is not None else 6
            loop.study.create(args.source_file,args.postrun_directory,args.memory_workspace,args.goal,max_requests=maximum)
        else:
            frozen={'source_file':previous['private_sources']['source_file'],
                    'postrun_directory':previous['private_sources']['postrun_directory'],
                    'memory_workspace':previous['memory_workspace']}
            for name in frozen:
                supplied=getattr(args,name)
                require(supplied is None or str(Path(supplied).absolute())==frozen[name],
                        'CONFIG_CHANGED','Evidence and memory locations are frozen.')
            require(args.goal is None or args.goal==previous['goal'],'CONFIG_CHANGED','Goal is frozen.')
            require(args.max_requests is None or args.max_requests==previous['max_requests'],
                    'CONFIG_CHANGED','Cumulative request budget is frozen.')
        if args.max_new_requests==0:
            write(output/'study.json',loop.study.observe())
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
                          'new_cloud_requests':result['budget']['requests_reserved']-before['budget']['requests_reserved'],
                          'new_fits':0},ensure_ascii=False));return 0
    except (ResearchError,OSError,ValueError,sqlite3.Error,UnicodeError,RecursionError) as error:
        receipt={'ok':False,'code':getattr(error,'code','POSTRUN_REVISION_FAILED'),'error_class':type(error).__name__,
                 'automatic_retry':False,'owned_server_stopped':getattr(server,'stopped',False),
                 'key_metadata_unchanged':getattr(server,'key_metadata_unchanged',None)}
        write(output/'failure.json',receipt);print(json.dumps(receipt,ensure_ascii=False));return 1


if __name__=='__main__':raise SystemExit(main())
