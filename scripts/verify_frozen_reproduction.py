#!/usr/bin/env python3
"""Prepare a separate pinned historical venv and check saved group arrays, never refit."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from urllib.parse import urlsplit, urlunsplit

ROOT = Path(__file__).resolve().parents[1]
WHEEL = Path('/workspace/work/g6-local-release-20261113-01/source/dist/agentarts_autoresearch-0.1.0-py3-none-any.whl')
WHEEL_SHA = '3b454d45ed7b37166cdcc74544e28e4b053c190b61cca0e305394abf2e5262c1'
ADAPTER_SHA = '5c689576add16d5bd28cdf5c43a5c4599afb257a12f6b239018dcabcb0501090'
LOCK = ROOT / 'docs/execution/g1-local/requirements-reproduction.lock'
OUTER = ROOT / 'runs/g4-local-group-20261113-01'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def sanitize(text):
    def replace(match):
        p = urlsplit(match.group())
        return urlunsplit((p.scheme, p.hostname or 'redacted', p.path, '', ''))
    return re.sub(r'https?://[^\s<>\"\']+', replace, text)


CHECK = r'''
import hashlib, importlib.metadata as md, json
from pathlib import Path
import socket, sys
root=Path(sys.argv[1]); data_root=root/'inputs'
attempts=[]; fits=[]
def deny(*a,**k):
    attempts.append('connect');raise RuntimeError('network prohibited during pinned compatibility check')
socket.socket.connect=socket.create_connection=deny
import numpy as np
from sklearn.model_selection import GroupKFold
from sklearn.linear_model import Ridge
from sklearn.preprocessing import StandardScaler
def nofit(*a,**k):
    fits.append('fit');raise RuntimeError('fit prohibited in historical compatibility check')
Ridge.fit=StandardScaler.fit=nofit
from autoresearch import ridge_validation_adapter as module
origin=Path(module.__file__).resolve()
assert origin.is_relative_to(Path(sys.prefix).resolve())
raw=origin.read_bytes();assert hashlib.sha256(raw).hexdigest()=="5c689576add16d5bd28cdf5c43a5c4599afb257a12f6b239018dcabcb0501090"
assert not hasattr(module,'encode_groups'), '0ceb source has inline baseline, not later optimized helper'
source=raw.decode()
assert 'labels = list(dict.fromkeys(row["groups"] for row in rows))' in source
assert 'group_ids = np.array([labels.index(row["groups"]) for row in rows])' in source
assert 'GroupKFold(count)' in source
expected_versions={line.split('==')[0]:line.split('==')[1] for line in (root/'requirements-reproduction.lock').read_text().splitlines() if line and not line.startswith('#')}
assert all(md.version(name)==version for name,version in expected_versions.items())
assert md.version('numpy')=='2.5.4' and md.version('scipy')=='1.17.0' and md.version('scikit-learn')=='1.8.0'
assert 'include-system-site-packages = false' in (Path(sys.prefix)/'pyvenv.cfg').read_text()
baseline=json.loads((data_root/'baseline-evaluation.json').read_text()); manifest=json.loads((data_root/'baseline-manifest.json').read_text()); results={}
for name in ('concrete','real-estate','slump'):
    p=data_root/(name+'.json');assert hashlib.sha256(p.read_bytes()).hexdigest()==manifest['inputs'][name]['payload_sha256']
    data=json.loads(p.read_text()); rows=[{'groups':tuple(label)} for label in data['labels']]
    # Exact original inline expression, independently checked against frozen VM IDs.
    labels=list(dict.fromkeys(row['groups'] for row in rows))
    group_ids=np.array([labels.index(row['groups']) for row in rows])
    assert group_ids.tolist()==baseline['datasets'][name]['group_ids']
    assert str(group_ids.dtype)==baseline['datasets'][name]['split_check']['dtype']
    membership=np.zeros(len(rows),dtype=int)
    for number,(train,test) in enumerate(GroupKFold(data['n_splits']).split(np.zeros((len(rows),1)),groups=group_ids),1):
        membership[test]=number;assert set(group_ids[train]).isdisjoint(set(group_ids[test]))
    assert membership.tolist()==data['saved_folds']
    results[name]={'rows':len(rows),'groups':len(labels),'group_ids':group_ids.tolist(),'fold_membership':membership.tolist(),'all_ids_equal_vm_original':True,'all_folds_equal_frozen_1_8':True,'input_sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'new_fits':0}
assert not fits and not attempts
versions={d.metadata['Name']:d.version for d in md.distributions() if d.metadata.get('Name')}
result={'status':'all_three_complete_frozen_arrays_exact','module_origin':str(origin),'adapter_sha256':hashlib.sha256(raw).hexdigest(),'source_commit':'0ceb2742825a9e95b373260fb39950fcbb48af1b','versions':versions,'observed_pins_exact':expected_versions,'datasets':results,'fit_calls':0,'product_model_api_calls':0,'socket_attempts':0,'scope':'Historical inline group expression and GroupKFold memberships only, no model refit/numerical metric reproduction'}
(root/'compatibility.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps({'status':result['status'],'versions':{name:md.version(name) for name in ('numpy','scipy','scikit-learn','h5py','reportlab')},'module_origin':str(origin),'rows':{n:r['rows'] for n,r in results.items()},'fit_calls':0,'product_model_api_calls':0}))
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=Path('/workspace/work/g6-frozen-reproduction-20261113-01'))
    args = parser.parse_args()
    out = args.output.resolve()
    assert out.is_relative_to(ROOT.parent/'work') and not out.exists()
    assert WHEEL.is_file() and sha(WHEEL) == WHEEL_SHA
    assert shutil.disk_usage(ROOT).free >= 5*1024**3
    out.mkdir(parents=True)
    shutil.copyfile(LOCK, out/'requirements-reproduction.lock')
    inputs = out/'inputs'; inputs.mkdir()
    for name in ('baseline-manifest.json','baseline-evaluation.json'):
        shutil.copyfile(OUTER/name,inputs/name)
    for name in ('concrete','real-estate','slump'):
        shutil.copyfile(OUTER/'inputs'/(name+'.json'),inputs/(name+'.json'))
    env={k:v for k,v in os.environ.items() if k in ('PATH','HOME','LANG','LC_ALL','TZ','TMPDIR','HTTP_PROXY','HTTPS_PROXY','NO_PROXY','http_proxy','https_proxy','no_proxy','SSL_CERT_FILE','REQUESTS_CA_BUNDLE','PIP_CERT')}
    env.update(PIP_CONFIG_FILE=os.devnull,PIP_DISABLE_PIP_VERSION_CHECK='1',PIP_NO_INPUT='1',PIP_NO_CACHE_DIR='1',PYTHONDONTWRITEBYTECODE='1',OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',MKL_NUM_THREADS='1',MPLBACKEND='Agg',MPLCONFIGDIR=str(out/'mpl-config'))
    commands=[]
    def execute(label,argv,timeout=240):
        p=out/(label+'.txt')
        r=subprocess.run([str(a) for a in argv],cwd=out,env=env,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,timeout=timeout)
        text=sanitize(r.stdout);assert len(text.encode())<4*1024**2;p.write_text(text)
        commands.append({'stage':label,'argv':[sanitize(str(a)) for a in argv],'exit_code':r.returncode,'log':p.name,'log_sha256':sha(p)})
        print(json.dumps({'stage':label,'exit_code':r.returncode}),flush=True)
        assert r.returncode==0,label+' failed; retain this attempt'
    try:
        execute('create-pinned-venv',[sys.executable,'-I','-m','venv',out/'venv'])
        python=out/'venv/bin/python'
        execute('install-observed-exact-pins',[python,'-I','-m','pip','install','--index-url','https://pypi.org/simple','--only-binary=:all:','--no-cache-dir','--report',out/'pip-report.json','-r',out/'requirements-reproduction.lock'])
        execute('install-historical-wheel',[python,'-I','-m','pip','install','--no-index','--no-deps',WHEEL])
        execute('pip-check',[python,'-I','-m','pip','check'])
        execute('pip-freeze',[python,'-I','-m','pip','freeze','--all'])
        execute('cli-help',[out/'venv/bin/autoresearch','--help'])
        helper=out/'check-frozen-groups.py';helper.write_text(CHECK)
        execute('zero-fit-complete-array-compatibility',[python,'-I',helper,out])
        original=json.loads((OUTER/'integrity-before.json').read_text()); original_manifest=json.loads((OUTER/'baseline-manifest.json').read_text());count=0
        for name,files in original.items():
            path=Path(original_manifest['inputs'][name]['path'])
            for filename,digest in files.items():assert sha(path/filename)==digest;count+=1
        result={'status':'separate_historical_pinned_environment_verified_for_ids_and_splits','source_commit':'0ceb2742825a9e95b373260fb39950fcbb48af1b','wheel_path':str(WHEEL),'wheel_sha256':WHEEL_SHA,'original_inline_adapter_sha256':ADAPTER_SHA,'lock_sha256':sha(out/'requirements-reproduction.lock'),'script_sha256':sha(Path(__file__)),'clean_venv':str(out/'venv'),'system_site_packages':False,'fit_calls':0,'product_model_api_calls':0,'original_case_files_match_prefreeze':count,'dependency_network_downloads':True,'commands':commands,'completed_utc':datetime.now(timezone.utc).isoformat(),'limits':['Separate frozen-purpose env; previous 1.9 strict failure unchanged','No model refit/prediction/metric reproduction claimed','Original0ceb source lacks later helper and current dependency-identity guard','Transitive package inventory observed and recorded, not previously fully locked','No production-code promotion or fullG6 acceptance']}
        (out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    except BaseException as error:
        (out/'failure.json').write_text(json.dumps({'type':type(error).__name__,'message':sanitize(str(error)),'commands':commands},indent=2)+'\n')
        raise
    finally:
        (out/'manifest.json').write_text(json.dumps({p.name:sha(p) for p in out.iterdir() if p.is_file() and p.name!='manifest.json'},indent=2)+'\n')


if __name__=='__main__':
    main()
