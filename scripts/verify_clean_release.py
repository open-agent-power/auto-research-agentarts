#!/usr/bin/env python3
"""Install a local wheel into a fresh non-inheriting venv; record partial failures, no research."""
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
INDEX = "https://pypi.org/simple"
CASE = ROOT / "runs/g3-local-transfer-20261113-01/real-estate/manager"


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def clean(text):
    def url(match):
        value = urlsplit(match.group())
        return urlunsplit((value.scheme, value.hostname or "redacted", value.path, "", ""))
    return re.sub(r"https?://[^\s<>\"']+", url, text)


def save(path, data):
    with Path(path).open("x") as f:
        json.dump(data, f, indent=2)
        f.write("\n")


def inventory(root):
    return {str(p.relative_to(ROOT)): sha(p) for p in root.rglob("*") if p.is_file()}


SMOKE = r'''
import contextlib, hashlib, importlib.metadata as md, importlib.resources as resources, io, json, pathlib, socket, sys, threading
from urllib.request import build_opener, ProxyHandler, Request
from urllib.error import HTTPError
output = pathlib.Path(sys.argv[1]); project = output / "native-project-copy"; report_dir = output / "saved-report-copy"
attempts = []; original = socket.socket.connect
def local_only(self, address):
    if not isinstance(address, tuple) or address[0] not in ("127.0.0.1", "::1", "localhost"):
        attempts.append("nonlocal_connection"); raise RuntimeError("external network forbidden in product smoke")
    return original(self, address)
socket.socket.connect = local_only
from sklearn.linear_model import Ridge
from sklearn.preprocessing import StandardScaler
fit_attempts = []
def nofit(*a, **k):
    fit_attempts.append("fit"); raise RuntimeError("fitting forbidden in release smoke")
Ridge.fit = StandardScaler.fit = nofit
from autoresearch import agent_tasks, project_workbench, project_report
from autoresearch.research_project import ResearchProject
origin = pathlib.Path(agent_tasks.__file__).resolve(); assert origin.is_relative_to(pathlib.Path(sys.prefix).resolve())
assert "include-system-site-packages = false" in (pathlib.Path(sys.prefix) / "pyvenv.cfg").read_text()
versions = {d.metadata["Name"]: d.version for d in md.distributions() if d.metadata.get("Name")}
assets = {name: hashlib.sha256(resources.files("autoresearch").joinpath(name).read_bytes()).hexdigest() for name in ("data/README.md", "data/matbench_steels.json.gz", "web/index.html", "web/app.css", "web/app.js", "web/vendor-licenses.txt")}
before = {p.relative_to(project).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in project.rglob("*") if p.is_file()}
check = project_workbench.check_project_workbench(workspace=project, report=report_dir); assert check["ok"] and check["mode"] == "read_only"
server = project_workbench.create_project_server(workspace=project, report=report_dir, port=0)
thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
http = build_opener(ProxyHandler({})); base = "http://127.0.0.1:" + str(server.server_port)
responses = {}
try:
    for route, expected in (("/", "web/index.html"), ("/app.js", "web/app.js"), ("/app.css", "web/app.css")):
        with http.open(base + route, timeout=10) as r: data=r.read(); assert r.status==200
        expected_bytes=resources.files("autoresearch").joinpath(expected).read_bytes()
        if route == "/":
            expected_bytes=expected_bytes.replace(b"<body>",b'<body data-case="project" data-active-project="true">',1)
        assert data==expected_bytes; responses[route]={"status":200,"sha256":hashlib.sha256(data).hexdigest(),"html_binding_injection_expected":route=="/"}
    with http.open(base + "/api/project", timeout=10) as r: view=json.load(r)
    assert view["id"] == check["project_id"] and view["report"]["available"]
    responses["/api/project"]={"status":200,"project_id":view["id"],"state_version":view["state_version"],"budget":view["budget"]}
    for name in ("report.json", "report.md", "report.pdf", "input.json"):
        with http.open(base + "/api/project/"+name, timeout=10) as r: data=r.read(); assert r.status==200
        assert data==(report_dir/name).read_bytes(); responses["/api/project/"+name]={"status":200,"sha256":hashlib.sha256(data).hexdigest()}
    try:
        http.open(Request(base+"/api/project",data=b"{}",method="POST",headers={"Content-Type":"application/json"}),timeout=10)
        raise AssertionError("write unexpectedly accepted")
    except HTTPError as e:
        assert e.code==405; responses["POST /api/project"]={"status":405,"body":e.read().decode()}
finally:
    server.shutdown(); thread.join(timeout=10); server.server_close()
after = {p.relative_to(project).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in project.rglob("*") if p.is_file()}
assert before==after and not fit_attempts and not attempts
# Render an already exported report dict, never recollect/open original project/manager.
render = {"status":"not_run_reports_dependency_unavailable"}
try:
    import reportlab, matplotlib, pypdf, h5py
except ImportError as error:
    render["missing_module"]=error.name
else:
    from io import BytesIO
    old=json.loads((report_dir/"report.json").read_text()); data=project_report._pdf(old)
    assert data.startswith(b"%PDF"); path=output/"regenerated-from-saved-report.pdf"; path.write_bytes(data)
    reader=pypdf.PdfReader(BytesIO(data)); assert len(reader.pages)>0
    render={"status":"rendered_saved_dict_only","pages":len(reader.pages),"sha256":hashlib.sha256(data).hexdigest(),"h5py_import":True,"matplotlib_import":True}
assert not fit_attempts and not attempts
print(json.dumps({"venv":sys.prefix,"inherits_system_site_packages":False,"module_origin":str(origin),"assets":assets,"versions":versions,"native_readonly":check,"http":responses,"copied_project_files_unchanged":len(before),"report_render":render,"new_fits":0,"program_model_api_calls":0,"nonlocal_network_attempts_during_smoke":len(attempts)}))
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wheel", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    wheel, output = args.wheel.resolve(), args.output.resolve()
    assert wheel.is_file() and wheel.suffix == ".whl"
    assert output.is_relative_to(ROOT.parent / "work") and not output.exists()
    assert shutil.disk_usage(ROOT).free >= 5*1024**3
    output.mkdir(parents=True)
    originals = {**inventory(ROOT / "runs/cloud-concrete-local-20261113-01"), **inventory(CASE)}
    env = {k:v for k,v in os.environ.items() if k in ("PATH", "HOME", "LANG", "LC_ALL", "TZ", "TMPDIR", "HTTP_PROXY", "HTTPS_PROXY", "NO_PROXY", "http_proxy", "https_proxy", "no_proxy", "SSL_CERT_FILE", "REQUESTS_CA_BUNDLE", "PIP_CERT")}
    env.update(PIP_CONFIG_FILE=os.devnull,PIP_DISABLE_PIP_VERSION_CHECK="1",PIP_NO_INPUT="1",PIP_NO_CACHE_DIR="1",
               OMP_NUM_THREADS="1", OPENBLAS_NUM_THREADS="1", MKL_NUM_THREADS="1",PYTHONDONTWRITEBYTECODE="1",MPLBACKEND="Agg",MPLCONFIGDIR=str(output/"mpl-config"))
    commands=[]
    def execute(label, argv, timeout=240):
        try:
            result=subprocess.run([str(x) for x in argv],cwd=output,env=env,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,timeout=timeout)
            code, text=result.returncode,result.stdout
        except subprocess.TimeoutExpired as error:
            code,text=124,(error.stdout or b"").decode(errors="replace") if isinstance(error.stdout,bytes) else (error.stdout or "")
        text=clean(text)
        assert len(text.encode())<4*1024**2
        path=output/(label+".txt");path.write_text(text)
        row={"label":label,"argv":[clean(str(x)) for x in argv],"exit_code":code,"log":path.name,"log_sha256":sha(path)}
        commands.append(row);print(json.dumps({"stage":label,"exit_code":code}),flush=True)
        return code,text
    statuses={}
    try:
        code,_=execute("create-clean-venv",[sys.executable,"-I","-m","venv",str(output/"venv")]);assert code==0
        python=output/"venv/bin/python"
        assert "include-system-site-packages = false" in (output/"venv/pyvenv.cfg").read_text()
        for stage,extra in (("base",""),("sources","[sources]"),("reports","[reports]")):
            report=output/(stage+"-pip-report.json")
            code,text=execute("install-"+stage,[python,"-I","-m","pip","install","--index-url",INDEX,"--only-binary=:all:","--no-cache-dir","--report",report,str(wheel)+extra])
            statuses[stage]={"exit_code":code,"success":code==0,"pip_report":report.name if report.exists() else None,"network_download_indicated":"Downloading " in text,"resolution_failure":"No matching distribution" in text or "Could not find a version" in text}
            if stage=="base" and code!=0:
                break
        if statuses["base"]["success"]:
            execute("pip-check",[python,"-I","-m","pip","check"])
            execute("pip-freeze",[python,"-I","-m","pip","freeze","--all"])
            execute("cli-help",[output/"venv/bin/autoresearch","--help"])
            execute("module-help",[python,"-I","-m","autoresearch","--help"])
            project=list((CASE/"projects").iterdir());assert len(project)==1
            shutil.copytree(project[0],output/"native-project-copy")
            reports=list((CASE/"reports").iterdir());assert len(reports)==1
            shutil.copytree(reports[0],output/"saved-report-copy")
            helper=output/"smoke-clean.py";helper.write_text(SMOKE)
            code,text=execute("native-report-smoke",[python,"-I",helper,output],timeout=120)
            statuses["native_smoke"]={"exit_code":code,"success":code==0}
            if code==0:
                save(output/"native-smoke.json",json.loads(text.strip().splitlines()[-1]))
        after={**inventory(ROOT/"runs/cloud-concrete-local-20261113-01"),**inventory(CASE)}
        assert after==originals,"original project assets changed"
        save(output/"result.json",{"status":"complete_with_per_stage_results","started_from_local_wheel":str(wheel),"wheel_sha256":sha(wheel),"wheel_source_snapshot":"0ceb274; not final release wheel","system_site_packages":False,"pip_index":INDEX,"statuses":statuses,"commands":commands,"original_files_unchanged":len(originals),"script_sha256":sha(Path(__file__)),"completed_utc":datetime.now(timezone.utc).isoformat(),"network_scope":"Python dependency downloads only; product inference/model APIs not called","study_reproduction":"not attempted; original frozen research versions unchanged","cost":{"product_model_api_calls":0,"new_fits":0,"dependency_network_used":any(s.get("network_download_indicated") for s in statuses.values()),"currency":None,"tokens":None}})
    except BaseException as error:
        save(output/"failure.json",{"type":type(error).__name__,"message":clean(str(error)),"commands":commands,"statuses":statuses})
        raise
    finally:
        save(output/"manifest.json",{p.name:sha(p) for p in output.iterdir() if p.is_file() and p.name!="manifest.json"})


if __name__=="__main__":
    main()
