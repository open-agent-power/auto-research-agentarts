"""Exercise the SDK through real loopback HTTP and a server-process restart."""

import argparse
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
from urllib.error import URLError
from urllib.request import ProxyHandler, Request, build_opener


@contextmanager
def server(workspace, log_path):
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    env = os.environ.copy()
    env.update(AUTORESEARCH_WORKSPACE=str(workspace), AUTORESEARCH_BIND_HOST="127.0.0.1",
               AGENT_RUN_PORT=str(port))
    opener = build_opener(ProxyHandler({}))
    with log_path.open("ab") as log:
        process = subprocess.Popen([sys.executable, "-m", "autoresearch.runtime"],
                                   env=env, stdout=log, stderr=subprocess.STDOUT)
        try:
            end = time.monotonic() + 20
            while True:
                if process.poll() is not None:
                    raise RuntimeError(f"local runtime exited: {process.returncode}; inspect operator log")
                try:
                    with opener.open(f"http://127.0.0.1:{port}/ping", timeout=1) as response:
                        if response.status == 200:
                            break
                except (URLError, TimeoutError):
                    pass
                if time.monotonic() >= end:
                    raise TimeoutError("local SDK server did not become ready")
                time.sleep(.1)
            yield opener, f"http://127.0.0.1:{port}/invocations", process.pid
        finally:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)


def run_probe(workspace):
    workspace = Path(workspace).resolve()
    if workspace.exists():
        raise ValueError("choose a new workspace; existing evidence is never overwritten")
    workspace.mkdir(parents=True)
    records = []

    def call(connection, action, rid, **fields):
        opener, url, pid = connection
        payload = {"schema_version": "0.1", "action": action, "request_id": rid, **fields}
        request = Request(url, data=json.dumps(payload).encode("utf-8"), method="POST", headers={
            "Content-Type": "application/json",
            "x-hw-agentarts-session-id": "local-r2-engineering",
            "X-Request-Id": "local-http-" + rid,
        })
        with opener.open(request, timeout=30) as response:
            result = json.load(response)
        records.append({"server_pid": pid, "input": payload, "output": result})
        if not result["ok"]:
            raise RuntimeError(f"{action} failed: {result['error']['code']}")
        return result

    with server(workspace / "state", workspace / "server.log") as connection:
        created = call(connection, "create_campaign", "create", goal="Real loopback SDK HTTP engineering probe", max_trials=3)
        campaign_id = created["result"]["campaign_id"]
        first = call(connection, "run_trial", "first", campaign_id=campaign_id)
        retry = call(connection, "run_trial", "first", campaign_id=campaign_id)
        assert first["result"] == retry["result"]
        call(connection, "pause_campaign", "pause", campaign_id=campaign_id)
    with server(workspace / "state", workspace / "server.log") as connection:
        call(connection, "resume_campaign", "resume", campaign_id=campaign_id)
        second = call(connection, "run_trial", "second", campaign_id=campaign_id)
        third = call(connection, "run_trial", "third", campaign_id=campaign_id)
        call(connection, "finalize_campaign", "final", campaign_id=campaign_id)
        state = call(connection, "campaign_status", "status", campaign_id=campaign_id)
    decisions = [item["result"]["status"] for item in (first, second, third)]
    assert decisions == ["accepted", "accepted", "rejected"]
    assert second["result"]["parent_trial_id"] == first["result"]["trial_id"]
    assert state["result"]["budget"]["consumed_trials"] == 3
    session_root = workspace / "state/sessions" / first["transport"]["session_fingerprint"]
    for trial in (first, second, third):
        artifact = session_root / trial["result"]["model_artifact"]
        assert hashlib.sha256(artifact.read_bytes()).hexdigest() == trial["result"]["model_sha256"]
    repo = Path(__file__).resolve().parents[1]
    sources = sorted((repo / "src/autoresearch").glob("*.py"))
    code_identity = hashlib.sha256(b"".join(p.name.encode()+b"\0"+p.read_bytes() for p in sources)).hexdigest()
    report = {"transport": "real_loopback_http", "sdk_version": "0.1.8",
              "code_fingerprint": code_identity, "cloud_calls_made": 0,
              "platform_deployed": False, "platform_trace_verified": False,
              "scientific_status": "engineering_only", "decisions": decisions,
              "validation_mse": [t["result"]["metrics"]["validation_mse"] for t in (first, second, third)],
              "campaign": state["result"], "requests": records}
    (workspace / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return {key: report[key] for key in ("transport", "code_fingerprint", "cloud_calls_made", "platform_deployed", "decisions", "validation_mse")}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", required=True)
    args = parser.parse_args()
    print(json.dumps(run_probe(args.workspace), indent=2))
