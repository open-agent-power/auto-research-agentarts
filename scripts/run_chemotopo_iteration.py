"""Create or resume an isolated P02 native numerical iteration."""
import argparse
import json
import os
from pathlib import Path
import sqlite3
import sys

from autoresearch.chemotopo_iteration_cloud import IterationCloudLoop
from autoresearch.contracts import ResearchError
from autoresearch.local_ollama import require
from autoresearch.ollama_cloud import OwnedCloudOllama


def write(path,value):
    with path.open('x',encoding='utf-8') as stream:json.dump(value,stream,ensure_ascii=False,indent=2,allow_nan=False)


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace',required=True);parser.add_argument('--output',required=True)
    parser.add_argument('--source');parser.add_argument('--baseline');parser.add_argument('--interaction');parser.add_argument('--goal')
    parser.add_argument('--max-requests',type=int);parser.add_argument('--max-new-requests',type=int,default=6)
    parser.add_argument('--model-store');parser.add_argument('--cache');parser.add_argument('--port',type=int,default=11436)
    parser.add_argument('--ollama-executable',default=str(Path(os.environ.get('LOCALAPPDATA',''))/'Programs/Ollama/ollama.exe'))
    args=parser.parse_args()
    if not 0<=args.max_new_requests<=6 or (args.max_requests is not None and not 1<=args.max_requests<=6):parser.error('request budget must be 0..6 and cumulative cap 1..6')
    output=Path(args.output).absolute();workspace=Path(args.workspace).absolute()
    for part in (output,*output.parents):
        if part.is_symlink() or getattr(part,'is_junction',lambda:False)():parser.error('receipt path cannot redirect')
    loop=IterationCloudLoop(workspace)
    protected=[workspace]
    if loop.study.db.exists():
        with loop.study._connect() as con:previous,_,_=loop.study._state(con)
        protected.extend(Path(previous[name]).absolute() for name in ('source','baseline','interaction'))
    else:
        protected.extend(Path(value).absolute() for value in (args.source,args.baseline,args.interaction) if value)
    if any(output==path or output.is_relative_to(path) or path.is_relative_to(output) for path in protected):parser.error('receipt output must be separate from study and evidence')
    output.mkdir(parents=True,exist_ok=False);server=None
    try:
        if not loop.study.db.exists():
            require(bool(args.source and args.baseline and args.interaction and args.goal),'INVALID_REQUEST','New iteration requires source, R54, R59 and goal.')
            for location in (args.source,args.baseline,args.interaction):
                protected=Path(location).absolute()
                require(not(output==protected or output.is_relative_to(protected) or protected.is_relative_to(output)),'UNSAFE_PATH','Receipt must be separate from inputs.')
            loop.study.create(args.source,args.baseline,args.interaction,args.goal)
        else:
            with loop.study._connect() as con:config,_,_=loop.study._state(con)
            for name in ('source','baseline','interaction'):
                supplied=getattr(args,name)
                require(supplied is None or str(Path(supplied).absolute())==config[name],'CONFIG_CHANGED','Evidence directory is frozen.')
                protected=Path(config[name]);require(not(output==protected or output.is_relative_to(protected) or protected.is_relative_to(output)),'UNSAFE_PATH','Receipt must be separate from inputs.')
            require(args.goal is None or args.goal==config['goal'],'CONFIG_CHANGED','Goal is frozen.')
        if not loop.db.exists() and args.max_new_requests==0:
            result=loop.study.observe();write(output/'study.json',result)
            print(json.dumps({'ok':True,'status':'study_created_no_native_calls','new_cloud_requests':0}));return 0
        maximum=args.max_requests or 6
        if loop.db.exists():
            old=loop.status();maximum=old['budget']['max_requests']
            require(args.max_requests is None or args.max_requests==maximum,'CONFIG_CHANGED','Cumulative request cap frozen.')
            recovered=loop.run(max_new_requests=0);write(output/'before.json',recovered)
            if recovered['status']!='active' or args.max_new_requests==0:
                write(output/'result.json',recovered);print(json.dumps({'ok':True,'status':recovered['status'],'new_cloud_requests':0}));return 0
        require(args.max_new_requests>0 and bool(args.model_store),'INVALID_REQUEST','Live inference requires model store and positive request budget.')
        with OwnedCloudOllama(args.ollama_executable,args.cache or output/'model-cache',output/'transport',port=args.port,model_store=args.model_store) as server:
            write(output/'server-identity.json',server.identity);identity=server.acquire();write(output/'model-and-account-scope.json',identity)
            if not loop.db.exists():loop.configure(identity,max_requests=maximum)
            before=loop.status();write(output/'before-live.json',before)
            result=loop.run(server,max_new_requests=args.max_new_requests,verified_weights=identity);write(output/'result.json',result)
        write(output/'cleanup.json',{'owned_server_stopped':server.stopped,'key_metadata_unchanged':server.key_metadata_unchanged})
        print(json.dumps({'ok':True,'status':result['status'],'study_status':result['study']['status'],
             'requests_reserved':result['budget']['requests_reserved'],'new_cloud_requests':result['budget']['requests_reserved']-before['budget']['requests_reserved']}));return 0
    except (ResearchError,OSError,ValueError,sqlite3.Error) as error:
        write(output/'failure.json',{'ok':False,'code':getattr(error,'code','ITERATION_FAILED'),'error_class':type(error).__name__,
             'automatic_retry':False,'owned_server_stopped':getattr(server,'stopped',False),'key_metadata_unchanged':getattr(server,'key_metadata_unchanged',None)})
        print(json.dumps({'ok':False,'code':getattr(error,'code','ITERATION_FAILED')}));return 1


if __name__=='__main__':raise SystemExit(main())
