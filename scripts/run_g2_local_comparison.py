"""Compare trusted task coordination on saved G1 evidence; never fits or calls models."""
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
from copy import deepcopy
from collections import defaultdict
import argparse
import hashlib
import json
import math
from pathlib import Path
import statistics
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from autoresearch.agent_tasks import AgentTaskLedger
from autoresearch.contracts import canonical, fingerprint


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(canonical(value) + "\n")


def tree_identity(root):
    result = {}
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise ValueError("Protected case contains a link")
        if path.is_file():
            result[str(path.relative_to(root))] = sha(path.read_bytes())
    return result


def load(inputs, name):
    return json.loads((inputs / (name + ".json")).read_text())


def analysis(inputs, task_id):
    started = time.perf_counter()
    if task_id in ("baseline", "candidate"):
        artifact = load(inputs, task_id)
        data = artifact["tool_result"]["result"]["analysis"]
        rows = data["oof"]
        assert len({row["logical_record"] for row in rows}) == len(rows) == 1030
        mae = math.fsum(abs(row["predicted"] - row["observed"]) for row in rows) / len(rows)
        reference = math.fsum(abs(row["reference_prediction"] - row["observed"]) for row in rows) / len(rows)
        assert math.isclose(mae, data["summary"]["candidate_mae"], abs_tol=1e-10)
        assert math.isclose(reference, data["summary"]["reference_mae"], abs_tol=1e-10)
        output = {"action_id": artifact["action_id"], "rows": len(rows), "mae": mae, "reference_mae": reference,
                  "negative_predictions": sum(row["predicted"] < 0 for row in rows),
                  "group_count": len({tuple(row["groups"]) for row in rows}), "new_fits": 0}
    elif task_id == "paired":
        parent = load(inputs, "baseline")["tool_result"]["result"]["analysis"]["oof"]
        child = load(inputs, "candidate")["tool_result"]["result"]["analysis"]["oof"]
        assert len(parent) == len(child) == 1030
        worsened, groups, group_differences = [], set(), defaultdict(list)
        for left, right in zip(parent, child):
            assert all(left[key] == right[key] for key in ("logical_record", "groups", "fold", "observed", "reference_prediction"))
            difference = abs(right["predicted"] - right["observed"]) - abs(left["predicted"] - left["observed"])
            group_differences[tuple(right["groups"])].append(difference)
            if difference > 0:
                worsened.append(right["logical_record"])
                groups.add(tuple(right["groups"]))
        output = {"matched_rows": len(parent), "worsened_rows": len(worsened),
                  "groups_with_any_worsened_row": len(groups), "worsened_groups": sum(math.fsum(deltas) > 0 for deltas in group_differences.values()),
                  "worsened_row_ids": worsened, "negative_prediction_rows": [r["logical_record"] for r in child if r["predicted"] < 0],
                  "mae_change": math.fsum(abs(r["predicted"]-r["observed"])-abs(l["predicted"]-l["observed"]) for l, r in zip(parent, child))/len(parent),
                  "scope": "Saved paired arithmetic, no causal or engineering approval", "new_fits": 0}
        assert output["worsened_rows"] == 313 and output["worsened_groups"] == 129
    elif task_id == "budget":
        state = load(inputs, "finished")
        budget = state["budget"]
        assert budget["fit_attempts_used"] == budget["fit_limit"] == 20
        assert budget["local_tool_calls_used"] == 5 and budget["evidence_reads_used"] == 1
        assert budget["new_model_requests"] == 0 and budget["fits_reserved"] == 0
        output = {"project_id": state["id"], "lineage_ref": budget["lineage_ref"],
                  "preserved_estimator_attempts": budget["fit_attempts_used"], "preserved_local_calls": budget["local_tool_calls_used"],
                  "preserved_source_reads": budget["evidence_reads_used"], "cash_settlement": budget["cash_settlement"],
                  "historical_unknowns_resolved": budget["historical_unknowns_resolved"], "new_fits": 0}
    else:
        raise ValueError("Task is not allowlisted")
    return output, time.perf_counter() - started


def contracts(project_ref, refs):
    tasks = []
    for task_id, depends, names, value, effort in (
        ("baseline", [], ["baseline"], 2, 2), ("candidate", [], ["candidate"], 2, 2),
        ("paired", ["baseline", "candidate"], ["baseline", "candidate"], 3, 3),
        ("budget", [], ["finished"], 1, 0.5),
    ):
        tasks.append({"task_id": task_id, "title": "Saved " + task_id + " audit", "objective": "Verify frozen saved research evidence",
            "user_value": "Retain adverse evidence and original allowance", "workstream": "saved_evidence", "owner": "trusted_evidence_analyst",
            "dependencies": depends, "input_snapshot": project_ref["state_snapshot_sha256"], "source_refs": [refs[name] for name in names],
            "allowed_files": ["Frozen supplied input snapshots"], "prohibited_files": ["Native project/manager/evaluator writes"],
            "interface_contract": "Unverified analysis, no scientific-state or budget mutation", "acceptance_criteria": ["Same exact arithmetic on complete saved rows"],
            "tests": ["paired identity and saved summary checks"], "benchmark_ids": ["G2-L-saved-evidence-001"],
            "budget": {"attempt_limit": 1, "model_requests": 0, "tool_calls": 0, "fits": 0},
            "runtime": {"mode": "trusted_local", "timeout_seconds": 30}, "risk_class": "trusted_analysis",
            "expected_artifacts": [task_id + " analysis JSON"], "docs_to_update": [], "expected_value": value, "estimated_effort": effort})
    return tasks


def arm(root, inputs, project_ref, tasks, mode):
    ledger = AgentTaskLedger(root / "ledger")
    parallel = 1 if mode == "single" else 2
    wall, cpu = time.perf_counter(), time.process_time()
    ledger.plan("plan", project_ref, tasks, {"mode": mode, "max_parallel": parallel, "attempt_limit": 4})
    trace, active, outputs, index = [], {}, {}, 0
    with ThreadPoolExecutor(max_workers=parallel) as pool:
        while len(outputs) < len(tasks):
            state = ledger.status()
            while len(active) < parallel and any(t["runnable"] for t in state["tasks"]):
                index += 1
                claimed = ledger.claim("claim-" + str(index), "trusted-" + str(index))
                assert claimed["status"] == "claimed"
                active[pool.submit(analysis, inputs, claimed["task_id"])] = claimed
                trace.append({"event": "claimed", "task_id": claimed["task_id"], "agent_id": claimed["agent_id"],
                              "attempt": claimed["attempt"], "elapsed_seconds": time.perf_counter() - wall})
                state = ledger.status()
            if not active:
                raise RuntimeError("No progress under the frozen DAG")
            done, _ = wait(active, timeout=30, return_when=FIRST_COMPLETED)
            if not done:
                raise TimeoutError("Trusted local analysis did not finish within the host timeout")
            for future in sorted(done, key=lambda f: active[f]["task_id"]):
                claimed = active.pop(future)
                task_id = claimed["task_id"]
                output, seconds = future.result()
                outputs[task_id] = output
                raw = canonical(output).encode()
                artifact_sha = sha(raw)
                artifact = root / "analyses" / (task_id + ".json")
                artifact.parent.mkdir(parents=True, exist_ok=True)
                artifact.write_bytes(raw)
                response = {"task_id": task_id, "role": "trusted_evidence_analyst", "status": "analysis_complete",
                    "proposal": output, "evidence_refs": claimed["task_contract"]["source_refs"], "tool_requests": [],
                    "artifact_refs": [{"artifact_id": task_id + "-analysis", "sha256": artifact_sha, "locator": "analyses/" + task_id + ".json:whole_file"}],
                    "metrics": {k: v for k, v in output.items() if type(v) in (int, float)},
                    "uncertainty": ["Saved evidence arithmetic does not establish independent scientific validity"],
                    "limitations": ["Fixed host analysis functions; no autonomous model agent or native tool dispatch"],
                    "cost_usage": {"tokens": None, "amount": None, "currency": None, "usage_status": "unknown"},
                    "next_actions": ["Host reconciles this precise attempt and result, preserves adverse cases"]}
                submitted = ledger.submit("submit-" + task_id, task_id, claimed["agent_id"], claimed["attempt"], response)
                ledger.reconcile("review-" + task_id, task_id, "completed", "Host accepted the fixed saved arithmetic checks",
                                 expected_attempt=claimed["attempt"], result_sha256=submitted["result_sha256"])
                trace.append({"event": "reconciled", "task_id": task_id, "agent_id": claimed["agent_id"], "attempt": claimed["attempt"],
                              "analysis_sha256": artifact_sha, "result_sha256": submitted["result_sha256"], "analysis_seconds": seconds,
                              "elapsed_seconds": time.perf_counter() - wall})
    duration, cpu_duration = time.perf_counter()-wall, time.process_time()-cpu
    final = ledger.status()
    assert final["attempts_used"] == 4 and all(t["status"] == "completed" for t in final["tasks"])
    save(root / "trace.json", trace)
    save(root / "status.json", final)
    summary = {"mode": mode, "max_parallel": parallel, "wall_seconds": duration, "cpu_seconds": cpu_duration,
        "task_output_hashes": {key: fingerprint(value) for key, value in sorted(outputs.items())},
        "coordination_attempts": final["attempts_used"], "task_count": len(outputs), "trace_sha256": sha((root / "trace.json").read_bytes()),
        "ledger_sha256": sha(ledger.db.read_bytes()), "native_fits": 0, "native_tool_dispatches": 0, "product_model_sends": 0}
    save(root / "summary.json", summary)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    case, output = Path(args.case).absolute(), Path(args.output).absolute()
    assert case.is_dir() and not output.exists() and not output.is_relative_to(case)
    before = tree_identity(case)
    output.mkdir(parents=True)
    inputs = output / "inputs"
    inputs.mkdir()
    final_path = case / "snapshots/finished.json"
    final = json.loads(final_path.read_text())
    ridge = [a for a in final["actions"] if a["command"] == "data.ridge-group-validation"]
    assert len(ridge) == 2
    project_dirs = list((case / "manager/projects").glob("*"))
    assert len(project_dirs) == 1
    originals = {"finished": final_path, "baseline": project_dirs[0] / ridge[0]["artifact"], "candidate": project_dirs[0] / ridge[1]["artifact"]}
    refs = {}
    for name, source in originals.items():
        raw = source.read_bytes()
        (inputs / (name + ".json")).write_bytes(raw)
        refs[name] = {"source_id": name, "sha256": sha(raw), "locator": "full frozen JSON"}
    project_ref = {"project_id": final["id"], "source_snapshot_sha256": final["source_snapshot_sha256"],
                   "state_snapshot_sha256": refs["finished"]["sha256"]}
    tasks = contracts(project_ref, refs)
    freeze = {"schema_version": "g2-local-saved-evidence-comparison-v1", "project_ref": project_ref, "source_refs": refs, "tasks": tasks,
              "script_sha256": sha(Path(__file__).read_bytes()), "module_sha256": sha((ROOT / "src/autoresearch/agent_tasks.py").read_bytes()),
              "protocol_sha256": sha((ROOT / "docs/execution/g2-local/comparison-protocol.md").read_bytes()),
              "arm_orders": [["single", "static", "dynamic"], ["static", "dynamic", "single"], ["dynamic", "single", "static"]]}
    save(output / "freeze.json", freeze)
    save(output / "protected-before.json", before)
    for item in tasks:
        analysis(inputs, item["task_id"])
    summaries = []
    for repeat, order in enumerate(freeze["arm_orders"]):
        for mode in order:
            summaries.append({"repeat": repeat + 1, **arm(output / (str(repeat+1) + "-" + mode), inputs, project_ref, tasks, mode)})
    after = tree_identity(case)
    save(output / "protected-after.json", after)
    assert before == after, "Protected historical case changed"
    assert all(item["task_output_hashes"] == summaries[0]["task_output_hashes"] for item in summaries)
    assert all(sha((inputs / (name+".json")).read_bytes()) == ref["sha256"] for name, ref in refs.items())
    summary = {"status": "local_coordination_verified_full_G2_unpassed", "freeze_sha256": sha((output/"freeze.json").read_bytes()),
        "arms": summaries, "median_wall_seconds": {mode: statistics.median(s["wall_seconds"] for s in summaries if s["mode"] == mode) for mode in ("single", "static", "dynamic")},
        "identical_outputs": True, "protected_case_files_unchanged": len(before), "protected_case_identity_sha256": fingerprint(before),
        "default_policy": "single", "decision": "Small cached trusted tasks do not establish representative multi-agent benefit; retain single default",
        "native_fits": 0, "native_tool_dispatches": 0, "product_model_sends": 0, "external_api_sends": 0,
        "development_tokens": None, "currency_cost": None}
    save(output / "summary.json", summary)
    print(json.dumps({"output": str(output), "status": summary["status"], "median_wall_seconds": summary["median_wall_seconds"],
                      "protected_case_files_unchanged": len(before), "identical_outputs": True}, indent=2))


if __name__ == "__main__":
    main()
