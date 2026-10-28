"""Run a labeled HTTP model fixture and real training across fresh CLI processes."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

from loopback_model_fixture import configuration, model_fixture, KEY_ENV, FIXTURE_KEY


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", required=True)
    args = parser.parse_args()
    root = Path(args.workspace).resolve()
    if root.exists() and any(root.iterdir()):
        raise SystemExit("Choose an empty workspace; prior evidence will not be overwritten")
    root.mkdir(parents=True, exist_ok=True)
    repo = Path(__file__).resolve().parents[1]
    digest = hashlib.sha256()
    for path in sorted((repo / "src/autoresearch").glob("*.py")):
        digest.update(path.name.encode())
        digest.update(path.read_bytes())
    records = []
    env = dict(os.environ, **{KEY_ENV: FIXTURE_KEY, "PYTHONIOENCODING": "utf-8"})

    def invoke(arguments):
        command = [sys.executable, "-m", "autoresearch", *arguments]
        before = time.time()
        process = subprocess.Popen(command, cwd=repo, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
        timed_out = False
        try:
            stdout, stderr = process.communicate(timeout=60)
        except subprocess.TimeoutExpired:
            timed_out = True
            process.kill()  # Only the probe's own child process.
            stdout, stderr = process.communicate()
        record = {"ordinal": len(records)+1, "pid": process.pid, "arguments": arguments,
                  "exit_code": process.returncode, "stdout": stdout.decode("utf-8"),
                  "stderr": stderr.decode("utf-8"), "elapsed_seconds": time.time()-before,
                  "source_fingerprint": digest.hexdigest(), "real_model_calls": 0, "fixture": True}
        record["timed_out"] = timed_out
        records.append(record)
        (root / f"cli-{len(records):03}.json").write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
        if process.returncode != 0:
            raise RuntimeError("CLI probe failed; original output preserved")
        return json.loads(record["stdout"])

    with model_fixture() as (endpoint, requests):
        config = root / "fixture-config.json"
        config.write_text(json.dumps(configuration(endpoint), ensure_ascii=False, indent=2), encoding="utf-8")
        common = ["--workspace", str(root), "--config", str(config)]
        first = invoke(["research", *common, "--goal", "R4 engineering verification: scripted HTTP decisions and real materials fitting.", "--steps", "1"])
        assert first["state"]["status"] == "paused"
        result = invoke(["research", *common, "--resume"])
        stopped = invoke(["research", *common])
        status = invoke(["research-status", "--workspace", str(root)])
        assert len(requests) == 4
        assert result["state"]["status"] == "stopped"
        assert status["budget"] == stopped["state"]["budget"] == result["state"]["budget"]
        assert status["campaign"]["budget"]["consumed_trials"] == 3
        assert first["state"]["campaign"]["trials"][0]["id"] == status["campaign"]["trials"][0]["id"]
        assert status["fixture"] and status["live_model_responses_received"] == 0
        assert all(c["status"] == "applied" for c in status["model_calls"])
        (root / "fixture-http-records.json").write_text(json.dumps(requests, ensure_ascii=False, indent=2), encoding="utf-8")
    integrity = result["experiment_report"]["artifact_integrity"]
    assert len(integrity) == 3 and all(item["verified"] for item in integrity)
    summary = {"source_fingerprint": digest.hexdigest(), "campaign_id": status["campaign_id"],
               "fixture_model_responses": 4, "real_model_calls": 0, "cloud_calls": 0, "real_training_trials": 3,
               "separate_cli_processes": len(records), "final_status": status["status"], "budget": status["budget"],
               "trial_decisions": [t["status"] for t in status["campaign"]["trials"]],
               "validation_mse": [t["metrics"]["validation_mse"] for t in status["campaign"]["trials"]],
               "model_hashes_verified": integrity, "recovery_verified": True, "stopped_run_did_not_dispatch": True,
               "real_external_cost_cny": 0, "accounting_is_fixture_simulation": True,
               "scientific_discovery_claimed": False, "platform_deployed": False,
               "exports": result["exports"]}
    (root / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
