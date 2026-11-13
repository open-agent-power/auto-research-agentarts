#!/usr/bin/env python3
"""Offline wheel/install smoke in disposable work/; never runs research or model transports."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
PROTECTED_CASE = ROOT / "runs/cloud-concrete-local-20261113-01"


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, data):
    with Path(path).open("x") as f:
        json.dump(data, f, indent=2)
        f.write("\n")


def git(*args):
    return subprocess.check_output(["git", "-C", str(ROOT), *args], text=True).strip()


def inventory(paths):
    return {str(p.relative_to(ROOT)): sha(p) for p in paths if p.is_file()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True, help="New scratch directory below workspace work/")
    args = parser.parse_args()
    output = args.output.resolve()
    work = ROOT.parent / "work"
    if not output.is_relative_to(work) or output == work:
        parser.error("output must be a new subdirectory below " + str(work))
    if output.exists():
        parser.error("refusing existing output; preserve previous attempt")
    if shutil.disk_usage(ROOT).free < 5 * 1024**3:
        parser.error("less than 5 GiB disk headroom")
    output.mkdir(parents=True)
    source = output / "source"
    source.mkdir()
    head = git("rev-parse", "HEAD")
    tracked = subprocess.check_output(["git", "-C", str(ROOT), "ls-files", "-z", "--", "src", "pyproject.toml", "README.md", "THIRD_PARTY_NOTICES.md"]).decode().split("\0")
    paths = [ROOT / p for p in tracked if p]
    before = inventory(paths)
    old_case_before = inventory(PROTECTED_CASE.rglob("*")) if PROTECTED_CASE.exists() else {}
    save(output / "source-before.json", {"head": head, "files": before})
    save(output / "protected-case-before.json", old_case_before)
    for path in paths:
        assert path.is_file() and not path.is_symlink(), "tracked snapshot requires ordinary files"
        dest = source / path.relative_to(ROOT)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, dest)
    environment = {k: v for k, v in os.environ.items() if k in ("PATH", "HOME", "LANG", "LC_ALL", "TZ", "TMPDIR", "SSL_CERT_FILE", "REQUESTS_CA_BUNDLE")}
    environment.update(PIP_NO_INDEX="1", PIP_NO_INPUT="1", PIP_DISABLE_PIP_VERSION_CHECK="1",
                       PYTHONDONTWRITEBYTECODE="1", OMP_NUM_THREADS="1", OPENBLAS_NUM_THREADS="1", MKL_NUM_THREADS="1")
    commands = []
    def execute(label, command, cwd=output, timeout=90):
        result = subprocess.run(command, cwd=cwd, env=environment, stdin=subprocess.DEVNULL,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=timeout)
        data = result.stdout.encode()
        assert len(data) < 2 * 1024**2, "unexpectedly large smoke log"
        log = output / (label + ".txt")
        log.write_bytes(data)
        commands.append({"label": label, "argv": [str(x) for x in command], "cwd": str(cwd),
                         "exit_code": result.returncode, "log": log.name, "log_sha256": sha(log)})
        assert result.returncode == 0, label + " failed; retained log at " + str(log)
        return result.stdout
    try:
        # setuptools and wheel are already installed. Calling the backend directly
        # avoids a missing `build` frontend and any isolated dependency download.
        execute("build-wheel", [sys.executable, "-I", "-c", "from setuptools.build_meta import build_wheel; print(build_wheel('dist'))"], cwd=source)
        wheels = list((source / "dist").glob("*.whl"))
        assert len(wheels) == 1, "expected exactly one wheel"
        wheel = wheels[0]
        with zipfile.ZipFile(wheel) as archive:
            assert archive.testzip() is None
            names = archive.namelist()
            assert "autoresearch/agent_tasks.py" in names
            packed = {p.relative_to(source / "src").as_posix(): sha(p)
                      for p in (source / "src/autoresearch").rglob("*") if p.is_file()}
            for name, expected in packed.items():
                assert name in names and hashlib.sha256(archive.read(name)).hexdigest() == expected, name
            entries = archive.read("agentarts_autoresearch-0.1.0.dist-info/entry_points.txt").decode()
            metadata = archive.read("agentarts_autoresearch-0.1.0.dist-info/METADATA").decode()
            assert "autoresearch = autoresearch.cli:main" in entries
        save(output / "wheel-content.json", {"wheel": str(wheel.relative_to(output)), "sha256": sha(wheel),
                                               "bytes": wheel.stat().st_size, "packed_source_files": packed,
                                               "all_archive_entries": names, "entry_points": entries,
                                               "requires_dist": [line for line in metadata.splitlines() if line.startswith("Requires-Dist:")]})
        venv = output / "venv"
        execute("create-venv", [sys.executable, "-I", "-m", "venv", "--system-site-packages", str(venv)])
        python = venv / "bin/python"
        execute("install-wheel", [str(python), "-I", "-m", "pip", "install", "--no-index", "--no-deps", "--force-reinstall", str(wheel)])
        execute("cli-help", [str(venv / "bin/autoresearch"), "--help"])
        execute("module-help", [str(python), "-I", "-m", "autoresearch", "--help"])
        # `agent_tasks` deliberately has no CLI. Verify its installed module/class
        # and packaged resources instead of calling its no-op module with --help.
        smoke = output / "smoke-installed.py"
        smoke.write_text('''import hashlib, importlib.metadata as md, importlib.resources as resources, json, pathlib, socket, sys
attempted = []
def deny(*a, **k):
    attempted.append("network_attempt")
    raise RuntimeError("network is prohibited in release smoke")
socket.socket.connect = deny
socket.create_connection = deny
import autoresearch
from autoresearch import agent_tasks
from autoresearch.agent_tasks import AgentTaskLedger
import autoresearch.protocol
import autoresearch.reports
origin = pathlib.Path(agent_tasks.__file__).resolve()
assert origin.is_relative_to(pathlib.Path(sys.prefix).resolve()), str(origin)
assert AgentTaskLedger.__module__ == "autoresearch.agent_tasks"
assets = {}
for name in ("data/README.md", "data/matbench_steels.json.gz", "web/index.html", "web/app.css", "web/app.js", "web/vendor-licenses.txt"):
    data = resources.files("autoresearch").joinpath(name).read_bytes()
    assert data
    assets[name] = {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}
assert not attempted
print(json.dumps({"module_origin": str(origin), "prefix": sys.prefix, "agent_tasks_sha256": hashlib.sha256(origin.read_bytes()).hexdigest(), "AgentTaskLedger_import": True, "assets": assets, "dependencies": {name: md.version(name) for name in ("numpy", "scikit-learn", "agentarts-autoresearch")}, "network_attempts_during_import": len(attempted), "fits": 0, "product_model_calls": 0}))
''')
        imported = json.loads(execute("installed-import-resources", [str(python), "-I", str(smoke)]))
        assert imported["agent_tasks_sha256"] == before["src/autoresearch/agent_tasks.py"]
        for name, row in imported["assets"].items():
            assert row["sha256"] == before["src/autoresearch/" + name]
        after = inventory(paths)
        old_case_after = inventory(PROTECTED_CASE.rglob("*")) if PROTECTED_CASE.exists() else {}
        assert before == after and old_case_before == old_case_after
        assert git("rev-parse", "HEAD") == head, "HEAD moved during build"
        save(output / "source-after.json", {"head": head, "files": after})
        save(output / "protected-case-after.json", old_case_after)
        save(output / "result.json", {"status": "passed_limited_offline_release_smoke", "head": head,
                                       "wheel": str(wheel), "wheel_sha256": sha(wheel), "imported": imported,
                                       "source_files_unchanged": len(before), "protected_case_files_unchanged": len(old_case_before),
                                       "source_root_unchanged": True, "commands": commands,
                                       "limitations": ["New venv inherits system site packages", "No clean dependency installation or optional extras/runtime verification", "No fitting, model/API or research-state mutation", "Wheel snapshot has no standalone algorithm/retrieval runner integration", "No tag, commit, deployment or full G6 acceptance"],
                                       "cost": {"product_model_calls": 0, "fits": 0, "currency": None, "development_tokens": None},
                                       "completed_utc": datetime.now(timezone.utc).isoformat()})
        print(json.dumps({"status": "passed_limited_offline_release_smoke", "wheel_sha256": sha(wheel),
                          "packed_files": len(packed), "source_unchanged": len(before), "old_case_unchanged": len(old_case_before)}))
    except BaseException as error:
        save(output / "failure.json", {"type": type(error).__name__, "message": str(error), "commands": commands})
        raise
    finally:
        save(output / "manifest.json", {p.relative_to(output).as_posix(): sha(p) for p in output.iterdir() if p.is_file() and p.name != "manifest.json"})


if __name__ == "__main__":
    main()
