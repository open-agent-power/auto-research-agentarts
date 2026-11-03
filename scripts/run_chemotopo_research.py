"""Run/resume the P02 source-policy Agent with the existing free Ollama transport."""
import argparse
import json
import os
from pathlib import Path
import sqlite3
import sys

from autoresearch.chemotopo_cloud import ChemoTopoCloudLoop
from autoresearch.contracts import ResearchError
from autoresearch.local_ollama import require
from autoresearch.ollama_cloud import OwnedCloudOllama


def write(path,value):
    with path.open('x',encoding='utf-8') as stream:json.dump(value,stream,ensure_ascii=False,indent=2,allow_nan=False)


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace',required=True);parser.add_argument('--output',required=True)
    parser.add_argument('--directory');parser.add_argument('--goal');parser.add_argument('--memory-workspace');parser.add_argument('--prediction-directory')
    parser.add_argument('--research-focus',choices=['source_policy','prediction_diagnostic'])
    parser.add_argument('--max-requests',type=int);parser.add_argument('--max-new-requests',type=int,default=8)
    parser.add_argument('--model-store');parser.add_argument('--cache');parser.add_argument('--port',type=int,default=11436)
    parser.add_argument('--ollama-executable',default=str(Path(os.environ.get('LOCALAPPDATA',''))/'Programs/Ollama/ollama.exe'))
    args=parser.parse_args()
    if not 0<=args.max_new_requests<=8:parser.error('max-new-requests must be0..8')
    if args.max_requests is not None and not 1<=args.max_requests<=8:parser.error('max-requests must be1..8')
    output=Path(args.output);output.mkdir(parents=True,exist_ok=False);server=None
    try:
        loop=ChemoTopoCloudLoop(args.workspace)
        if not loop.study.db.exists():
            require(bool(args.directory and args.goal),'INVALID_REQUEST','New P02 study needs fixed source directory and goal.')
            loop.study.create(args.directory,args.goal,memory_workspace=args.memory_workspace,max_actions=12,prediction_directory=args.prediction_directory,research_focus=args.research_focus or 'source_policy')
        else:
            with loop.study._connect() as con:config,_,_=loop.study._state(con)
            require(args.directory is None or str(Path(args.directory).absolute())==config['source_directory'],'CONFIG_CHANGED','Source directory is frozen.')
            require(args.prediction_directory is None or str(Path(args.prediction_directory).absolute())==config.get('prediction_directory'),'CONFIG_CHANGED','Prediction directory is frozen at creation.')
            require(args.research_focus is None or args.research_focus==config.get('research_focus','source_policy'),'CONFIG_CHANGED','Research focus is frozen at creation.')
            require(args.goal is None or args.goal==config['goal'],'CONFIG_CHANGED','Goal is frozen.')
            require(args.memory_workspace is None or str(Path(args.memory_workspace).absolute())==config['memory_workspace'],'CONFIG_CHANGED','Memory workspace is frozen.')
        maximum=args.max_requests or 8
        if loop.db.exists():
            old=loop.status();maximum=old['budget']['max_requests']
            require(args.max_requests is None or args.max_requests==maximum,'CONFIG_CHANGED','Cumulative request cap is frozen.')
            recovered=loop.run(max_new_requests=0);write(output/'before.json',recovered)
            if recovered['status']!='active' or args.max_new_requests==0:
                write(output/'result.json',recovered)
                print(json.dumps({'ok':True,'status':recovered['status'],'new_cloud_requests':0,'output':str(output)},ensure_ascii=False));return 0
        require(args.max_new_requests>0 and bool(args.model_store),'INVALID_REQUEST','Live inference requires a model store and positive bounded request count.')
        with OwnedCloudOllama(args.ollama_executable,args.cache or output/'model-cache',output/'transport',port=args.port,model_store=args.model_store) as server:
            write(output/'server-identity.json',server.identity)
            identity=server.acquire();write(output/'model-and-account-scope.json',identity)
            if not loop.db.exists():loop.configure(identity,max_requests=maximum)
            before=loop.status();write(output/'before-live.json',before)
            result=loop.run(server,max_new_requests=args.max_new_requests,verified_weights=identity)
            write(output/'result.json',result)
        write(output/'cleanup.json',{'owned_server_stopped':server.stopped,'key_metadata_unchanged':server.key_metadata_unchanged})
        print(json.dumps({'ok':True,'status':result['status'],'study_status':result['study']['status'],
              'requests_reserved':result['budget']['requests_reserved'],'new_cloud_requests':result['budget']['requests_reserved']-before['budget']['requests_reserved'],
              'actions':[a['action'] for a in result['study']['actions']],'output':str(output)},ensure_ascii=False));return 0
    except (ResearchError,OSError,ValueError,sqlite3.Error) as error:
        receipt={'ok':False,'code':getattr(error,'code','P02_RESEARCH_FAILED'),'error_class':type(error).__name__,
                 'automatic_retry':False,'owned_server_stopped':getattr(server,'stopped',False),
                 'key_metadata_unchanged':getattr(server,'key_metadata_unchanged',None)}
        write(output/'failure.json',receipt);print(json.dumps(receipt));return 1


if __name__=='__main__':raise SystemExit(main())
