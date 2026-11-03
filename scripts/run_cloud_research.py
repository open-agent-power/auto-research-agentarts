"""Run/resume C01 using the reviewed existing Ollama cloud alias and included credits.

No login, key creation, purchases, weight downloads or automatic inference retries.
"""
import argparse
import json
import os
from pathlib import Path
import sqlite3
import sys

from autoresearch.c01_cloud_loop import C01CloudLoop
from autoresearch.c01_cloud_memory import C01CloudMemoryLoop
from autoresearch.contracts import ResearchError
from autoresearch.local_ollama import require
from autoresearch.ollama_cloud import OwnedCloudOllama


def write(path,value):
    with path.open('x',encoding='utf-8') as f:json.dump(value,f,indent=2,ensure_ascii=False,allow_nan=False)


def configured(runner):
    if not runner.db.exists():return False
    with runner._connect() as con:
        tables={r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")}
        if not tables:return False
        require(tables==runner.journal_tables and con.execute('SELECT count(*) FROM project').fetchone()[0]==1,
                'CONFIG_CHANGED','preserve the unrecognized nonempty cloud journal')
    return True


def loop_for(workspace, *, tool_profile='general', memory_workspace=None):
    """Resume the frozen mode; a model cannot choose or replace its memory source."""
    probe=C01CloudLoop(workspace,tool_profile=tool_profile)
    saved_memory=False
    if probe.db.exists():
        with probe._connect() as con:
            exists=con.execute("SELECT 1 FROM sqlite_master WHERE name='project' AND type='table'").fetchone()
            row=None if not exists else con.execute('SELECT spec_json FROM project WHERE singleton=1').fetchone()
            if row is not None:saved_memory='conditional_memory' in json.loads(row[0])
    if memory_workspace is not None or saved_memory:
        return C01CloudMemoryLoop(workspace,tool_profile=tool_profile,memory_workspace=memory_workspace)
    return probe


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--workspace',required=True)
    p.add_argument('--output',required=True,help='New invocation evidence directory')
    p.add_argument('--model-store',help='Operator-owned existing Ollama metadata store; never from model decisions')
    p.add_argument('--cache',help='New/empty task model metadata cache; defaults inside output')
    p.add_argument('--ollama-executable',default=str(Path(os.environ.get('LOCALAPPDATA',''))/'Programs/Ollama/ollama.exe'))
    p.add_argument('--port',type=int,default=11436)
    p.add_argument('--archive');p.add_argument('--index');p.add_argument('--goal')
    p.add_argument('--memory-workspace',help='Opt-in existing exact-scope numerical memory; frozen at first configuration and resumed when omitted')
    p.add_argument('--max-requests',type=int,help='Frozen on first configuration; default8 for new study')
    p.add_argument('--tool-profile',choices=['general','as_reported_modeler','reviewed_modeler'],
                   help='Frozen role permissions; omitted resumes the saved profile, general for a new controller')
    p.add_argument('--max-new-requests',type=int,default=3,help='This invocation only;0 recovers received decisions offline')
    a=p.parse_args()
    if not 0<=a.max_new_requests<=8:p.error('max-new-requests must be0..8')
    if a.max_requests is not None and not 1<=a.max_requests<=8:p.error('max-requests must be1..8')
    output=Path(a.output).absolute();output.mkdir(parents=True,exist_ok=False)
    server=None
    try:
        loop=loop_for(a.workspace,tool_profile=a.tool_profile or 'general',memory_workspace=a.memory_workspace)
        if not loop.study.db.exists():
            require(bool(a.archive and a.index and a.goal),'INVALID_REQUEST','new study requires archive/index/goal')
            loop.study.create(a.archive,a.index,a.goal,max_actions=12,max_fits=3)
        maximum=a.max_requests or 8
        if configured(loop):
            old=loop.status();maximum=old['budget']['max_requests']
            profile=old['tool_profile']
            require(a.tool_profile is None or a.tool_profile==profile,
                    'CONFIG_CHANGED','existing cloud tool profile is frozen')
            loop=loop_for(a.workspace,tool_profile=profile,memory_workspace=a.memory_workspace)
            require(a.max_requests is None or a.max_requests==maximum,'CONFIG_CHANGED','cumulative cloud request limit is frozen')
            recovered=loop.run(max_new_requests=0);write(output/'before.json',recovered)
            if recovered['status']!='active' or a.max_new_requests==0:
                write(output/'result.json',recovered)
                print(json.dumps({'ok':True,'status':recovered['status'],'new_cloud_requests':0,'output':str(output)}))
                return 0
        require(a.max_new_requests>0,'NOT_CONFIGURED','new cloud controller needs a verified account identity')
        require(bool(a.model_store),'INVALID_REQUEST','live calls require explicit operator model-store')
        with OwnedCloudOllama(a.ollama_executable,a.cache or output/'model-cache',output/'transport',
                              port=a.port,model_store=a.model_store) as server:
            write(output/'server-identity.json',server.identity)
            identity=server.acquire();write(output/'model-and-account-scope.json',identity)
            loop.configure(identity,max_requests=maximum)
            before=loop.status();write(output/'configured.json',before)
            result=loop.run(server,max_new_requests=a.max_new_requests,verified_weights=identity)
            write(output/'result.json',result)
        write(output/'shutdown.json',{'owned_server_stopped':server.stopped,
                                      'key_metadata_unchanged':server.key_metadata_unchanged})
        print(json.dumps({'ok':True,'status':result['status'],'study_status':result['study']['status'],
              'requests_reserved':result['budget']['requests_reserved'],
              'new_cloud_requests':result['budget']['requests_reserved']-before['budget']['requests_reserved'],
              'actions':[x['action'] for x in result['study']['actions']],'output':str(output)},ensure_ascii=False))
        return 0
    except (ResearchError,OSError,ValueError,sqlite3.Error) as e:
        error={'ok':False,'code':getattr(e,'code','CLOUD_RESEARCH_FAILED'),'error_class':type(e).__name__,
               'automatic_retry':False,'owned_server_stopped':getattr(server,'stopped',False),
               'key_metadata_unchanged':getattr(server,'key_metadata_unchanged',None)}
        write(output/'failure.json',error);print(json.dumps(error));return 1


if __name__=='__main__':raise SystemExit(main())
