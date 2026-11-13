#!/usr/bin/env python3
"""Build an exact Git snapshot; install and resume saved native cases in a clean venv.

No new study, ranking/scoring, scheduling, fitting, source extraction, report
export or model request. Dependency downloads are a separate network operation.
"""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tarfile
import zipfile

REPO = Path(__file__).resolve().parents[1]
WORK = Path('/workspace/work')
KINDS = ('retrieval', 'scheduling')


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def read(path):
    assert path.is_file() and not path.is_symlink() and path.stat().st_size <= 128*1024**2, str(path)
    return path.read_bytes()


def load(path):
    return json.loads(read(path))


def save(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, indent=2, ensure_ascii=False, allow_nan=False)
        stream.write('\n')


def tree(root):
    paths = sorted(root.rglob('*'))
    assert all(not p.is_symlink() for p in paths)
    return {str(p.relative_to(root)): sha(read(p)) for p in paths if p.is_file()}


def package_files(source):
    package = source/'src/autoresearch'
    result = {}
    for path in sorted(package.rglob('*')):
        relative = path.relative_to(package)
        if path.is_file() and (path.suffix == '.py' or
                (relative.parts[0] == 'data' and path.name.endswith(('.json.gz', '.md'))) or
                (relative.parts[0] == 'web' and path.suffix in ('.html', '.css', '.js', '.txt'))):
            result['autoresearch/'+str(relative)] = sha(read(path))
    assert result and 'autoresearch/cli.py' in result
    return result


SMOKE = r'''
import contextlib, hashlib, importlib.metadata as metadata, importlib.resources as resources
import builtins, io, json, os, pathlib, runpy, socket, sqlite3, subprocess, sys, threading
from unittest.mock import patch
from urllib.request import build_opener, ProxyHandler, Request
from urllib.error import HTTPError
from urllib.parse import unquote
root=pathlib.Path(sys.argv[1]); expected=json.loads((root/'package-files.json').read_text())
blocked=json.loads((root/'blocked-original-paths.json').read_text());storage_reads=set()
assert 'include-system-site-packages = false' in (pathlib.Path(sys.prefix)/'pyvenv.cfg').read_text()
guards={};local_calls=[]
def denied(name):
    def fail(*args,**kwargs):
        guards[name]=guards.get(name,0)+1
        raise AssertionError('Forbidden release operation: '+name)
    return fail
connect=socket.socket.connect
connect_ex=socket.socket.connect_ex
getaddrinfo=socket.getaddrinfo
def islocal(address):
    return isinstance(address,tuple) and address[0] in ('127.0.0.1','::1','localhost')
def local_connect(self,address):
    if not islocal(address):return denied('nonlocal_network')(address)
    local_calls.append('connect');return connect(self,address)
def local_connect_ex(self,address):
    if not islocal(address):return denied('nonlocal_network')(address)
    local_calls.append('connect_ex');return connect_ex(self,address)
def local_dns(host,*args,**kwargs):
    if host not in ('127.0.0.1','::1','localhost'):return denied('nonlocal_dns')(host)
    return getaddrinfo(host,*args,**kwargs)
real_open,real_path_open,real_os_open,real_sqlite=builtins.open,pathlib.Path.open,os.open,sqlite3.connect
def storage(value):
    if isinstance(value,int):return
    text=os.fsdecode(value)
    if text.startswith('file:'):text=unquote(text[5:].split('?',1)[0])
    path=pathlib.Path(os.path.abspath(text))
    if any(path==pathlib.Path(p) or path.is_relative_to(pathlib.Path(p)) for p in blocked):
        return denied('original_storage_access')(str(path))
    if path.is_relative_to(root/'cases'):storage_reads.add(str(path.relative_to(root/'cases')))
def safe_open(file,*args,**kwargs):storage(file);return real_open(file,*args,**kwargs)
def safe_path_open(path,*args,**kwargs):storage(path);return real_path_open(path,*args,**kwargs)
def safe_os_open(path,*args,**kwargs):storage(path);return real_os_open(path,*args,**kwargs)
def safe_sqlite(path,*args,**kwargs):storage(path);return real_sqlite(path,*args,**kwargs)
def normalize(value):
    if type(value) is dict:return {k:normalize(v) for k,v in value.items() if not(k=='replayed' and type(v) is bool)}
    if type(value) is list:return [normalize(v) for v in value]
    return value
with contextlib.ExitStack() as guard:
    for module,name,function in ((builtins,'open',safe_open),(pathlib.Path,'open',safe_path_open),(os,'open',safe_os_open),(sqlite3,'connect',safe_sqlite)):
        guard.enter_context(patch.object(module,name,new=function))
    guard.enter_context(patch.object(socket.socket,'connect',local_connect))
    guard.enter_context(patch.object(socket.socket,'connect_ex',local_connect_ex))
    guard.enter_context(patch.object(socket.socket,'sendto',side_effect=denied('datagram_network')))
    guard.enter_context(patch.object(socket,'getaddrinfo',local_dns))
    from sklearn.linear_model import Ridge
    from sklearn.preprocessing import StandardScaler
    guard.enter_context(patch.object(Ridge,'fit',side_effect=denied('ridge_fit')))
    guard.enter_context(patch.object(StandardScaler,'fit',side_effect=denied('scaler_fit')))
    import autoresearch
    from autoresearch import retrieval_adapter as retrieval, retrieval_lexical as lexical
    from autoresearch import scheduling_adapter as scheduling, scheduling_kernel as kernel
    from autoresearch import source_evidence_adapter, project_report, method_registry
    from autoresearch.research_project import ResearchProject,code_identity
    from autoresearch.local_workbench import LocalWorkbench
    from autoresearch.project_workbench import create_project_server,check_project_workbench
    from autoresearch.model_client import ChatClient
    from autoresearch.host_model_selection import HostModelSelection
    origin=pathlib.Path(autoresearch.__file__).resolve().parent
    assert origin.is_relative_to(pathlib.Path(sys.prefix).resolve())
    actual={str(p.relative_to(origin.parent)):hashlib.sha256(p.read_bytes()).hexdigest()
            for p in origin.rglob('*') if p.is_file() and '__pycache__' not in p.parts}
    assert actual==expected, 'Installed package differs from exact Git/wheel package bytes'
    for module,names in ((lexical,('tokens','build_index','retrieve','metrics')),
                         (kernel,('jobs_for','schedule','brute_force')),
                         (retrieval,('execute',)),(scheduling,('execute',)),
                         (source_evidence_adapter,('execute',)),(project_report,('export_report','collect_report','_pdf')),
                         (ChatClient,('complete',)),(HostModelSelection,('request',)),(subprocess,('Popen',)),
                         (ResearchProject,('create',)),(LocalWorkbench,('create',)),(scheduling.time,('perf_counter',))):
        for name in names:
            guard.enter_context(patch.object(module,name,side_effect=denied(module.__name__+'.'+name)))
    for audit in (retrieval.AUDIT,scheduling.AUDIT):
        guard.enter_context(patch.object(audit,'execute_saved',side_effect=denied(audit.TOOL_ID)))
    help_results={}
    for kind in ('console_entrypoint','module'):
        output=io.StringIO();sys.argv=['autoresearch','--help']
        with contextlib.redirect_stdout(output):
            try:
                if kind=='module':runpy.run_module('autoresearch',run_name='__main__')
                else:next(e for e in metadata.entry_points(group='console_scripts') if e.name=='autoresearch').load()()
            except SystemExit as error:assert error.code in (0,None)
        assert 'usage:' in output.getvalue().lower()
        (root/(kind+'-help.txt')).write_text(output.getvalue());help_results[kind]=True
    def inventory(path):
        return {str(p.relative_to(path)):hashlib.sha256(p.read_bytes()).hexdigest() for p in path.rglob('*') if p.is_file()}
    results={}
    for kind in ('retrieval','scheduling'):
        case=root/'cases'/kind;manager_root=case/'manager';before=inventory(manager_root)
        manager=LocalWorkbench(manager_root);project,_=manager.binding();state=project.status()
        assert len(state['actions'])==2 and state['research_status']=='waiting'
        assert state['code_identity']==code_identity()
        before_budget=state['budget'];assert before_budget['local_tool_calls_used']==2
        assert before_budget['local_tool_call_limit']==2
        assert all(before_budget[key]==0 for key in ('new_fits','fit_attempts_used','fit_limit','fits_reserved','new_model_requests',
                   'model_requests_allowed','model_requests_reserved','evidence_read_limit','evidence_reads_used','evidence_reads_reserved','local_tool_calls_reserved'))
        project._source(state)
        assert any(p.endswith('/source.json') and p.startswith(kind+'/manager/') for p in storage_reads)
        with sqlite3.connect((manager_root/'workbench.sqlite').as_uri()+'?mode=ro',uri=True) as db:
            accepted={row[0]:row[1] for row in db.execute('SELECT id,digest FROM requests')}
        responses={}
        for name in ('primary','audit','wait','report'):
            request=json.loads((case/(name+'-request.json')).read_text())
            assert request['command']==('LocalWorkbench.export' if name=='report' else 'LocalWorkbench.advance')
            from autoresearch.contracts import fingerprint
            assert accepted.get(request['body']['request_id'])==fingerprint(request['body'])
            expected_result=json.loads((case/(name+'-result.json')).read_text())['result']
            response=(manager.export if name=='report' else manager.advance)(request['body'])
            assert response.get('replayed') is True
            assert normalize(response)==normalize(expected_result)
            responses[name]={'replayed':True,'request_id':request['body']['request_id'],'status':response['status']}
        assert project.status()==state and project.status()['budget']==before_budget
        manifest=response['manifest']
        report_dirs=[p.parent for p in (manager_root/'reports').glob('*/manifest.json')
                     if json.loads(p.read_text())==manifest]
        assert len(report_dirs)==1;report=report_dirs[0]
        check=check_project_workbench(workspace=project.root,report=report)
        assert check['ok'] and check['mode']=='read_only'
        server=create_project_server(workspace=project.root,report=report,port=0)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        http=build_opener(ProxyHandler({}));base='http://127.0.0.1:'+str(server.server_port);routes={}
        try:
            for route,asset in (('/', 'web/index.html'),('/app.js','web/app.js'),('/app.css','web/app.css')):
                with http.open(base+route,timeout=15) as response:data=response.read();assert response.status==200
                want=resources.files('autoresearch').joinpath(asset).read_bytes()
                if route=='/':want=want.replace(b'<body>',b'<body data-case="project" data-active-project="true">',1)
                assert data==want;routes[route]={'status':200,'sha256':hashlib.sha256(data).hexdigest()}
            with http.open(base+'/api/project',timeout=15) as response:view=json.load(response)
            assert view['id']==state['id'] and view['budget']==state['budget'] and view['report']['available']
            routes['/api/project']={'status':200,'project_id':view['id'],'state_version':view['state_version']}
            for name,identity in manifest['files'].items():
                with http.open(base+'/api/project/'+name,timeout=15) as response:data=response.read();assert response.status==200
                assert data==(report/name).read_bytes() and len(data)==identity['bytes'] and hashlib.sha256(data).hexdigest()==identity['sha256']
                routes['/api/project/'+name]={'status':200,**identity}
            try:
                http.open(Request(base+'/api/project',data=b'{}',method='POST',headers={'Content-Type':'application/json'}),timeout=15)
                raise AssertionError('Read-only server accepted POST')
            except HTTPError as error:assert error.code==405;error.read();routes['POST /api/project']={'status':405}
        finally:
            server.shutdown();thread.join(timeout=10);server.server_close()
        from pypdf import PdfReader
        reader=PdfReader(io.BytesIO((report/'report.pdf').read_bytes()))
        assert len(reader.pages)>0 and any(page.extract_text().strip() for page in reader.pages)
        assert inventory(manager_root)==before, 'Copied manager/project/report bytes changed'
        results[kind]={'project_id':state['id'],'snapshot_ref':state['snapshot_ref'],'code_identity':state['code_identity'],
                       'budget':state['budget'],'saved_replays':responses,'readonly_http':routes,'pdf_pages':len(reader.pages),
                       'manager_files_unchanged':len(before)}
    assert not guards,guards
    print(json.dumps({'status':'installed_saved_native_cases_verified','module_origin':str(origin),'package_files':len(actual),
                      'core_code_identity':code_identity(),'runtime_dependencies':method_registry.runtime_dependencies(),
                      'cli_help':help_results,'cases':results,'forbidden_call_counts':guards,'loopback_connections':len(local_calls),
                      'copy_storage_reads':sorted(storage_reads),
                      'new_primary_or_audit_executions':0,'ranking_or_metric_recomputations':0,'production_solver_executions':0,
                      'new_report_exports':0,'fits':0,'product_model_api_calls':0,'nonlocal_product_network':0}))
'''


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--commit',required=True)
    parser.add_argument('--root',type=Path,required=True)
    parser.add_argument('--attempt',type=int,default=1)
    parser.add_argument('--cases-root',type=Path,default=REPO/'runs/g5-native-cases-20261113-01')
    args=parser.parse_args();root=args.root.resolve();cases=args.cases_root.resolve()
    assert re.fullmatch('[0-9a-f]{40}',args.commit)
    assert root.is_relative_to(WORK) and (root/'environment-result.json').is_file()
    assert 1<=args.attempt<=3
    output=root/('release-attempt-%02d'%args.attempt)
    assert not output.exists(),'Keep prior attempts; do not replace evidence'
    output.mkdir()
    env={k:v for k,v in os.environ.items() if not k.startswith(('PIP_','PYTHON'))}
    env.update(PIP_CONFIG_FILE=os.devnull,PIP_DISABLE_PIP_VERSION_CHECK='1',PIP_NO_INPUT='1',PIP_NO_CACHE_DIR='1',
               PYTHONDONTWRITEBYTECODE='1',OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',MKL_NUM_THREADS='1',MPLBACKEND='Agg',MPLCONFIGDIR=str(output/'mpl'))
    python=root/'venv/bin/python';commands=[]
    def run(label,argv,cwd=output,timeout=180):
        result=subprocess.run([str(x) for x in argv],cwd=cwd,env=env,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=timeout)
        log=output/(label+'.log');log.write_bytes(result.stdout)
        commands.append({'label':label,'argv':[str(x) for x in argv],'exitcode':result.returncode,'log_sha256':sha(result.stdout)})
        print(json.dumps(commands[-1]),flush=True)
        assert result.returncode==0,label+' failed; original log retained'
        return result.stdout
    protected=load(cases/'retrieval/freeze.json')['protected']
    assert protected==load(cases/'scheduling/freeze.json')['protected'] and len(protected)==369
    originals={kind:tree(cases/kind) for kind in KINDS}
    save(output/'original-native-before.json',originals)
    def protections(label):
        actual={name:{'bytes':Path(name).stat().st_size,'sha256':sha(read(Path(name)))} for name in protected}
        save(output/(label+'.json'),actual)
        assert actual==protected,'Frozen original file identity changed'
        for path in load(cases/'retrieval/freeze.json')['protected_tree_roots']:
            prefix=str(Path(path))+'/'
            assert {str(Path(path)/name) for name in tree(Path(path))}=={name for name in protected if name.startswith(prefix)}
        return actual
    try:
        protections('protected-before')
        archive=subprocess.run(['git','archive','--format=tar',args.commit],cwd=REPO,check=True,stdout=subprocess.PIPE).stdout
        assert len(archive)<=128*1024**2
        source=output/'source';source.mkdir()
        with tarfile.open(fileobj=io.BytesIO(archive)) as stream:
            members=stream.getmembers()
            assert all((m.isfile() or m.isdir()) and not Path(m.name).is_absolute() and '..' not in Path(m.name).parts for m in members)
            stream.extractall(source,members=members,filter='data')
        save(output/'source-snapshot.json',{'commit':args.commit,'archive_sha256':sha(archive),'files':tree(source)})
        expected=package_files(source);save(output/'package-files.json',expected)
        dist=output/'dist';dist.mkdir()
        run('build-wheel',[python,'-I','-m','pip','wheel','--no-deps','--no-build-isolation','--wheel-dir',dist,source])
        wheels=list(dist.glob('*.whl'));assert len(wheels)==1;wheel=wheels[0]
        with zipfile.ZipFile(wheel) as stream:
            names=[name for name in stream.namelist() if name.startswith('autoresearch/') and not name.endswith('/')]
            assert len(names)==len(set(names))
            packed={name:sha(stream.read(name)) for name in names};assert packed==expected
        save(output/'wheel-identity.json',{'name':wheel.name,'sha256':sha(read(wheel)),'bytes':wheel.stat().st_size,'package_files':packed})
        run('install-wheel',[python,'-I','-m','pip','install','--no-deps','--no-index','--report',output/'wheel-pip-report.json',wheel])
        run('pip-check',[python,'-I','-m','pip','check'])
        run('pip-freeze',[python,'-I','-m','pip','freeze','--all'])
        closure=run('installed-closure',[python,'-I','-c','import importlib.metadata as m,json;print(json.dumps(sorted([{ "name":d.metadata["Name"],"version":d.version,"requires":d.requires or []} for d in m.distributions()],key=lambda x:x["name"].lower())))'])
        save(output/'installed-closure.json',json.loads(closure))
        for kind in KINDS:
            case=output/'cases'/kind;case.mkdir(parents=True)
            shutil.copytree(cases/kind/'manager',case/'manager')
            assert tree(case/'manager')==tree(cases/kind/'manager')
            for stage in ('primary','audit','wait','report'):
                for suffix in ('request','result'):
                    shutil.copyfile(cases/kind/'steps'/(stage+'-'+suffix+'.json'),case/(stage+'-'+suffix+'.json'))
        save(output/'blocked-original-paths.json',[str(cases)]+[load(cases/kind/'freeze.json')['packet_original_path'] for kind in KINDS])
        helper=output/'installed-smoke.py';helper.write_text(SMOKE)
        raw=run('installed-native-smoke',[python,'-I',helper,output],timeout=180)
        save(output/'installed-smoke.json',json.loads(raw.splitlines()[-1]))
        assert {kind:tree(cases/kind) for kind in KINDS}==originals,'Original native case tree changed'
        protections('protected-completion')
        save(output/'result.json',{'status':'exact_snapshot_clean_install_saved_native_recovery_verified','source_commit':args.commit,
                                 'wheel_sha256':sha(read(wheel)),'verifier_sha256':sha(read(Path(__file__))),
                                 'protected_original_files':369,'native_originals_unchanged':True,'commands':commands,
                                 'scientific_refit_reproduction':False,'complete_G6':False,
                                 'dependency_network':'Official PyPI setup before product smoke; not zero network.',
                                 'cost':{'product_model_api_calls':0,'research_fits':0,'development_tokens':None,'currency':None}})
    except BaseException as error:
        save(output/'failure.json',{'type':type(error).__name__,'message':str(error),'commands':commands});raise
    finally:
        save(output/'original-native-after.json',{kind:tree(cases/kind) for kind in KINDS})
        protections('protected-after')
        assert load(output/'original-native-after.json')==originals,'Original native case tree changed'
        save(output/'manifest.json',{str(p.relative_to(output)):{'bytes':p.stat().st_size,'sha256':sha(read(p))} for p in sorted(output.rglob('*')) if p.is_file() and 'source' not in p.relative_to(output).parts and 'cases' not in p.relative_to(output).parts})


if __name__=='__main__':
    main()
