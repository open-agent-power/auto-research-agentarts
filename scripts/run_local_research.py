"""Execute/resume bounded C01 research with the verified owned local Qwen model."""
import argparse
import json
import os
from pathlib import Path
import sqlite3
import sys
import traceback

from autoresearch.c01_local_loop import C01LocalLoop
from autoresearch.contracts import ResearchError
from autoresearch.local_ollama import OwnedOllama, MODEL, require


def write(path, value):
    with path.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, allow_nan=False, indent=2)


def has_configuration(runner):
    if not runner.db.exists(): return False
    with runner._connect() as con:
        tables = {row[0] for row in con.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")}
        if not tables: return False  # Exclusive file creation may precede a rolled-back schema transaction.
        if tables != {'project','calls'} or con.execute('SELECT count(*) FROM project').fetchone()[0] != 1:
            raise ResearchError('CONFIG_CHANGED', 'nonempty local journal is not a recognized configured study; preserve it')
    return True


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace', required=True)
    parser.add_argument('--output', required=True, help='New process/evidence directory for this invocation')
    parser.add_argument('--cache', required=True)
    parser.add_argument('--ollama-executable', default=str(Path(os.environ.get('LOCALAPPDATA',''))/'Programs/Ollama/ollama.exe'))
    parser.add_argument('--port', type=int, default=11435)
    parser.add_argument('--model', choices=[MODEL,'qwen3:8b'], help='Defaults to the frozen study model, or4b for a new study')
    parser.add_argument('--archive')
    parser.add_argument('--index')
    parser.add_argument('--goal')
    parser.add_argument('--max-requests', type=int, default=8)
    parser.add_argument('--max-new-requests', type=int, default=8)
    args = parser.parse_args()
    output = Path(args.output).absolute()
    output.mkdir(parents=True, exist_ok=False)
    runner, server = C01LocalLoop(args.workspace), None
    try:
        selected_model = args.model or MODEL
        if not runner.study.db.exists():
            if not (args.archive and args.index and args.goal): parser.error('new study requires --archive, --index and --goal')
            runner.study.create(args.archive, args.index, args.goal, max_actions=12, max_fits=3)
        if has_configuration(runner):
            selected_model = runner.status()['model_identity']['model']
            require(args.model is None or args.model == selected_model, 'CONFIG_CHANGED', 'existing study model is frozen; use a new study to compare models')
            recovered = runner.run(max_new_requests=0)
            write(output/'before.json', recovered)
            if recovered['status'] != 'active' or args.max_new_requests == 0:
                write(output/'result.json', recovered)
                print(json.dumps({'ok':True,'status':recovered['status'],'requests_reserved':recovered['budget']['requests_reserved'],'new_native_requests':0,'output':str(output)}))
                return 0
        print('Starting owned local model; frozen study, sources and cumulative limits.', flush=True)
        with OwnedOllama(args.ollama_executable, args.cache, output, port=args.port, model=selected_model) as server:
            write(output/'server-identity.json', server.identity)
            weights = server.acquire()
            write(output/'weights.json', weights)
            runner.configure(weights, max_requests=args.max_requests)
            before = runner.status()
            write(output/'configured.json', before)
            result = runner.run(server, max_new_requests=args.max_new_requests, verified_weights=weights)
            write(output/'result.json', result)
        write(output/'shutdown.json', {'owned_server_stopped':server.stopped,
            'generated_task_key_files_removed_without_reading':server.generated_task_key_files_removed})
        print(json.dumps({'ok':True,'status':result['status'],'study_status':result['study']['status'],
            'requests_reserved':result['budget']['requests_reserved'],
            'new_native_requests':result['budget']['requests_reserved']-before['budget']['requests_reserved'],
            'actions':[action['action'] for action in result['study']['actions']], 'output':str(output)}, ensure_ascii=False))
        return 0
    except (ResearchError, ValueError, OSError, sqlite3.Error) as error:
        receipt={'ok':False,'code':getattr(error,'code','LOCAL_RESEARCH_FAILED'),
            'error_type':type(error).__name__, 'errno':getattr(error,'errno',None), 'winerror':getattr(error,'winerror',None),
            'frames':[{'file':frame.filename,'line':frame.lineno,'function':frame.name} for frame in traceback.extract_tb(error.__traceback__)],
            'message':str(error) if isinstance(error,ResearchError) else 'Local research failed; preserve its journal and evidence.',
            'owned_server_stopped':getattr(server,'stopped',False),'automatic_retry':False,
            'generated_task_key_files_removed_without_reading':getattr(server,'generated_task_key_files_removed',0)}
        write(output/'failure.json',receipt)
        print(json.dumps(receipt,ensure_ascii=False))
        return 1


if __name__ == '__main__': raise SystemExit(main())
