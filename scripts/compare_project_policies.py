"""Run one frozen three-domain fixed/adaptive comparison; never retry failed runs."""

import time
_IMPORT_STARTED = time.perf_counter()
import argparse
from contextlib import contextmanager
import copy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sys

sys.dont_write_bytecode = True
REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))
from autoresearch import knowledge, method_registry as registry, project_knowledge, source_evidence_adapter
from autoresearch.contracts import ResearchError, canonical, fingerprint
from autoresearch.project_controller import ProjectController, code_identity as controller_identity
from autoresearch.research_project import ResearchProject, code_identity as core_identity, safe_path
from autoresearch.project_workbench import _artifact
_IMPORT_SECONDS = time.perf_counter() - _IMPORT_STARTED

ORDER = (("p02.saved-oof-residuals", ("fixed", "adaptive")),
         ("materials.saved-steel-audit", ("adaptive", "fixed")),
         ("software.source-integrity-check", ("fixed", "adaptive")))
GOALS = {
    ORDER[0][0]: "保存OOF中候选相对化学基线的误差支持什么下一步，哪些原始映射仍缺失？",
    ORDER[1][0]: "保存的五个钢材组成方案是否达到原采用门槛，后续还缺哪些加工或微结构来源？",
    ORDER[2][0]: "原件捕获怎样避免Windows时间语义误判并保留一致性，哪些跨环境证据仍缺失？",
}


def require(value, code, message):
    if not value:
        raise ResearchError(code, message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def write_json(path, value, *, fresh=False):
    raw = canonical(value).encode("utf-8")
    with path.open("xb" if fresh else "wb") as stream:
        stream.write(raw)
        stream.flush()
        import os
        os.fsync(stream.fileno())


def code_ids():
    return {"core": core_identity(), "controller": controller_identity(), "runner": sha(Path(__file__).read_bytes())}


def normalized_manifest(value):
    return {key: item for key, item in value.items() if key != "task_ref"}


def load_cases(path, output):
    raw = source_evidence_adapter._read_file(path, 1_000_000)
    value = json.loads(raw, object_pairs_hook=source_evidence_adapter._json_object,
                       parse_constant=source_evidence_adapter._reject_constant)
    require(type(value) is dict and set(value) == {"cases"} and type(value["cases"]) is list
            and len(value["cases"]) == 3, "INVALID_CASES", "Use {cases:[three allowlisted cases]}.")
    cases, ids, methods = [], set(), set()
    for case in value["cases"]:
        require(type(case) is dict and set(case) == {"id", "method", "source", "evidence_bundle"},
                "INVALID_CASES", "Case fields are id, method, source and evidence_bundle only.")
        case_id, method = case["id"], case["method"]
        require(type(case_id) is str and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,47}", case_id)
                and case_id not in ids and method in registry.PRIMARY and method not in methods,
                "INVALID_CASES", "Use unique path-safe case IDs and exactly the three current primary methods.")
        ids.add(case_id); methods.add(method)
        item = dict(case)
        for key in ("source", "evidence_bundle"):
            require(type(case[key]) is str and case[key], "INVALID_CASES", "Input paths must be nonempty strings.")
            chosen = Path(case[key])
            chosen = safe_path(chosen.absolute() if chosen.is_absolute() else (path.parent / chosen).absolute()).resolve()
            boundary = chosen.parent if key == "source" else chosen
            require(not output.is_relative_to(boundary) and not boundary.is_relative_to(output),
                    "INPUT_OUTPUT_OVERLAP", "Comparison output must not overlap any original source directory or bundle.")
            item[key] = chosen
        cases.append(item)
    require(methods == set(registry.PRIMARY), "INVALID_CASES", "All three allowlisted methods must appear exactly once.")
    return cases, sha(raw)


def copy_bundle(root, manifest, assets, task=None):
    root.mkdir(parents=True, exist_ok=False)
    document = copy.deepcopy(manifest)
    if task is not None:
        document["task_ref"] = copy.deepcopy(task)
    for source in document["sources"]:
        path = root.joinpath(*source_evidence_adapter._source_parts(source["path"]))
        path.parent.mkdir(parents=True, exist_ok=True)
        raw = assets[source["id"]]
        if path.exists():
            require(path.read_bytes() == raw, "EVIDENCE_CHANGED", "Aliased source paths contain different bytes.")
        else:
            with path.open("xb") as stream:
                stream.write(raw)
    write_json(root / "manifest.json", document, fresh=True)
    return document


def prepare(case, output):
    started = time.perf_counter()
    raw = source_evidence_adapter._read_file(case["source"], 16_000_000)
    packet = registry.get(case["method"]).load_source(raw)
    manifest_raw = source_evidence_adapter._read_file(case["evidence_bundle"] / "manifest.json", 1_000_000)
    manifest = json.loads(manifest_raw, object_pairs_hook=source_evidence_adapter._json_object,
                          parse_constant=source_evidence_adapter._reject_constant)
    receipt, assets = source_evidence_adapter.capture_bundle(case["evidence_bundle"], manifest["task_ref"])
    norm = normalized_manifest(manifest)
    destination = output / "inputs" / case["id"]
    destination.mkdir(parents=True, exist_ok=False)
    with (destination / "source.json").open("xb") as stream:
        stream.write(raw)
    copy_bundle(destination / "original-bundle", manifest, assets)
    frozen = {"id": case["id"], "method": case["method"], "goal": GOALS[case["method"]],
              "source_sha256": sha(raw), "source_bytes": len(raw), "source_snapshot_sha256": packet["snapshot_sha256"],
              "source_schema_version": packet["schema_version"], "source_scope": copy.deepcopy(packet["scope"]),
              "primary_parameters": {"dimension": "chemistry"} if case["method"] == ORDER[0][0] else {},
              "source_bundle_manifest": norm, "source_bundle_manifest_sha256": fingerprint(norm),
              "bundle_sources": [{"id": source["id"], "sha256": source["sha256"], "bytes": len(assets[source["id"]])}
                                 for source in receipt["sources"]],
              "source_path": str(case["source"]), "bundle_path": str(case["evidence_bundle"]),
              "frozen_source": (destination / "source.json").relative_to(output).as_posix(),
              "frozen_bundle": (destination / "original-bundle").relative_to(output).as_posix(),
              "shared_preparation_elapsed_seconds": time.perf_counter() - started}
    if case["method"] == ORDER[1][0]:
        dataset = packet["state"]["dataset"]
        frozen["bundled_dataset_dependency"] = {key: copy.deepcopy(dataset[key]) for key in (
            "dataset_id", "data_sha256", "raw_sha256", "split_protocol", "split_counts", "split_data_sha256") if key in dataset}
        frozen["bundled_dataset_dependency"].update(
            dataset_id=packet["scope"]["dataset_id"],
            resource="autoresearch/data/matbench_steels.json.gz",
            notice="The packet contains saved models and descriptors, not the complete raw dataset archive. load_source/execute verify the bundled dataset SHA and split protocol.")
    return frozen, manifest, assets


@contextmanager
def instrument(primary):
    counts = {"primary_execute_calls": 0, "source_execute_calls": 0, "knowledge_query_calls": 0,
              "fts_search_calls": 0, "controller_advance_calls": 0, "controller_next_calls": 0}
    elapsed = {key: 0.0 for key in ("primary_execute_calls", "source_execute_calls", "knowledge_query_calls", "fts_search_calls")}
    originals = []

    def wrap(owner, attribute, key):
        original = getattr(owner, attribute)
        originals.append((owner, attribute, original))
        def called(*args, **kwargs):
            counts[key] += 1
            started = time.perf_counter()
            try:
                return original(*args, **kwargs)
            finally:
                elapsed[key] += time.perf_counter() - started
        setattr(owner, attribute, called)

    wrap(primary, "execute", "primary_execute_calls")
    wrap(source_evidence_adapter, "execute", "source_execute_calls")
    wrap(project_knowledge, "query", "knowledge_query_calls")
    wrap(knowledge.KnowledgeIndex, "search", "fts_search_calls")
    try:
        yield counts, elapsed
    finally:
        for owner, attribute, original in reversed(originals):
            setattr(owner, attribute, original)


def semantic_task(decision):
    value = (decision or {}).get("next_action", {})
    result = {key: copy.deepcopy(value[key]) for key in ("method_id", "kind", "execution_status", "required_evidence") if key in value}
    parameters = {key: item for key, item in value.get("parameters", {}).items() if key != "receipt_snapshot_sha256"}
    if parameters:
        result["parameters"] = parameters
    if (decision or {}).get("remaining_questions") is not None:
        result["remaining_questions"] = decision["remaining_questions"]
    return result


def normalized_outcome(project):
    state = project.status()
    with project._connect(readonly=True) as con:
        actions = [json.loads(row[0]) for row in con.execute("SELECT record FROM actions ORDER BY rowid")]
    primary_metrics, software_checks, selections, eligibility = [], [], [], []
    for action in actions:
        if action["status"] != "completed":
            continue
        tool = json.loads(_artifact(project, state, action["id"]))["tool_result"]
        require(tool["scientific_validation"] is False and tool["new_fits"] == 0,
                "UNEXPECTED_CLAIM", "Saved results must retain their no-new-fit and unapproved boundary.")
        if not registry.is_source(action["command"]):
            primary_metrics.extend(tool.get("metrics", []))
            for check in tool.get("result", {}).get("checks", []):
                software_checks.append({key: check[key] for key in (
                    "id", "classification", "passed", "expected_code", "actual_code",
                    "same_api_lstat_stable", "same_api_fstat_stable") if key in check})
        else:
            for selected in tool["result"]["selections"]:
                selections.append({"id": selected["id"], "source": selected["source"],
                                   "locator": selected["locator"], "submitted_claim": selected["submitted_claim"],
                                   "extraction": selected["extraction"]})
            eligibility.append({"mapping_status": tool.get("mapping_status"), "endpoint_eligibility": tool.get("endpoint_eligibility")})
    return {"action_order": [{"method": item["command"], "dimension": item.get("dimension"), "status": item["status"]} for item in actions],
            "primary_metrics": primary_metrics, "software_checks": software_checks,
            "source_selections": selections, "source_eligibility": eligibility,
            "research_status": state["research_status"], "execution_status": state["execution_status"],
            "next_task": semantic_task(state.get("next_decision") or state.get("initial_decision")),
            "budget": state["budget"], "scientific_validation": False}


def directory_bytes(path):
    return sum(item.stat().st_size for item in path.rglob("*") if item.is_file()) if path.exists() else 0


def run_arm(frozen, manifest, assets, arm, output, protocol, record):
    primary = registry.get(frozen["method"])
    root = output / "arms" / frozen["id"] / arm
    root.mkdir(parents=True, exist_ok=False)
    workspace = root / "project"
    project, controller = ResearchProject(workspace), ProjectController(workspace)
    record.update(case_id=frozen["id"], arm=arm, workspace=workspace.relative_to(output).as_posix(), stages={})
    started = time.perf_counter()

    def stage(name, callback):
        clock = time.perf_counter()
        try:
            return callback()
        finally:
            record["stages"][name] = {"elapsed_seconds": time.perf_counter() - clock}

    def completed(response):
        require(response.get("status") not in ("unknown", "running", "pending", "failed", "rejected", "needs_review")
                and not response.get("blockers"),
                "ARM_STOPPED", "An unresolved or failed execution stops this run without retry.")
        return response.get("status") == "completed"

    with instrument(primary) as (counts, nested_elapsed):
        record["counts"], record["nested_call_elapsed_seconds"] = counts, nested_elapsed
        try:
            require(code_ids() == protocol["code_identities"], "CODE_CHANGED", "Frozen comparison implementation changed.")
            source = output / frozen["frozen_source"]
            require(sha(source.read_bytes()) == frozen["source_sha256"], "EVIDENCE_CHANGED", "Frozen primary packet changed.")
            stage("create", lambda: project.create(source=source, goal=frozen["goal"], method_id=frozen["method"],
                  budget_ref="A10:" + frozen["id"] + ":existing-history-not-reset", max_tool_calls=1))
            if arm == "fixed":
                first = stage("primary_step", lambda: project.step(request_id="fixed-primary", **frozen["primary_parameters"],
                                      expected_state_version=project.status()["state_version"]))
            else:
                counts["controller_advance_calls"] += 1
                first = stage("primary_advance", lambda: controller.advance(request_id="adaptive-primary", expected_state_version=project.status()["state_version"]))
            if completed(first):
                task = project.evidence_task()["task_ref"]
                bundle = root / "evidence-bundle"
                rebound = stage("prepare_bound_bundle", lambda: copy_bundle(bundle, manifest, assets, task))
                require(fingerprint(normalized_manifest(rebound)) == frozen["source_bundle_manifest_sha256"],
                        "EVIDENCE_CHANGED", "Only the task binding may differ across source bundles.")
                registration = stage("register", lambda: project.register_evidence(request_id="register-same-sources", bundle=bundle,
                                       expected_state_version=project.status()["state_version"]))
                if arm == "fixed":
                    second = stage("source_read", lambda: project.read_evidence(request_id="fixed-source",
                                         receipt_snapshot_sha256=registration["receipt_snapshot_sha256"],
                                         expected_state_version=project.status()["state_version"]))
                else:
                    counts["controller_advance_calls"] += 1
                    second = stage("source_advance", lambda: controller.advance(request_id="adaptive-source",
                                            expected_state_version=project.status()["state_version"]))
                completed(second)
            terminal_before = project.status()
            terminal_db_sha = sha(project.db.read_bytes())
            if arm == "adaptive":
                counts["controller_next_calls"] += 1
                plan = stage("terminal_readonly_next", controller.next)
                record["terminal_plan"] = {"executable": plan["executable"], "status": plan["status"],
                                            "next_task": semantic_task(plan["decision"]), "blockers": plan["blockers"]}
            else:
                stage("terminal_readonly_status", project.status)
            require(sha(project.db.read_bytes()) == terminal_db_sha and project.status()["snapshot_ref"] == terminal_before["snapshot_ref"],
                    "READ_MUTATED_PROJECT", "Terminal observation changed project state.")
            state = project.status()
            require(len(state["actions"]) + len(state["evidence_actions"]) <= 2
                    and state["budget"]["new_model_requests"] == state["budget"]["new_fits"] == 0
                    and state["budget"]["local_tool_call_limit"] == 1 and state["budget"]["evidence_read_limit"] == 8,
                    "PROTOCOL_CHANGED", "Execution exceeded the frozen action or resource boundaries.")
            record["normalized_outcome"] = normalized_outcome(project)
            record["project_snapshot_ref"] = state["snapshot_ref"]
            record["project_id"] = state["id"]
            record["completed_real_actions"] = sum(item["status"] == "completed" for item in state["actions"] + state["evidence_actions"])
            record["controller_parent_count"] = len(state.get("controller_requests", []))
            record["controller_record_bytes"] = len(canonical(state.get("controller_requests", [])).encode("utf-8"))
            record["status"] = "recorded"
        finally:
            record.update(elapsed_seconds=time.perf_counter() - started, output_total_bytes=directory_bytes(root),
                          project_output_bytes=directory_bytes(workspace), db_bytes=project.db.stat().st_size if project.db.exists() else None,
                          cpu_seconds=None, total_os_io_bytes=None, human_time_seconds=None, historical_cost_cny=None)


def compare(left, right):
    fixed, adaptive = left["normalized_outcome"], right["normalized_outcome"]
    same = fixed == adaptive
    return {"same_normalized_outcome": same, "different_fields": [key for key in fixed if fixed[key] != adaptive[key]],
            "conclusion": "no_observed_advantage" if same else "observed_difference_requires_domain_judgment",
            "counter_delta_adaptive_minus_fixed": {key: right["counts"][key] - left["counts"][key] for key in left["counts"]},
            "elapsed_seconds": {"fixed": left["elapsed_seconds"], "adaptive": right["elapsed_seconds"]},
            "notice": "One paired run per task; wall time is observational and cannot establish a policy performance advantage."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", required=True, help="JSON {cases:[{id,method,source,evidence_bundle}]}; relative paths use this file's directory.")
    parser.add_argument("--output", required=True, help="Fresh directory, separate from all source directories and bundles.")
    args = parser.parse_args()
    output = safe_path(Path(args.output).absolute()).resolve()
    created, progress, active = False, {"arms": {}}, None
    try:
        require(not output.exists(), "OUTPUT_EXISTS", "Comparison output already exists; it will not be reused or overwritten.")
        cases_path = safe_path(Path(args.cases).absolute()).resolve()
        require(not output.is_relative_to(cases_path.parent) and not cases_path.parent.is_relative_to(output),
                "INPUT_OUTPUT_OVERLAP", "Output must remain separate from the cases input directory.")
        prep_started = time.perf_counter()
        cases, cases_sha = load_cases(cases_path, output)
        output.mkdir(parents=True, exist_ok=False); created = True
        prepared = {case["method"]: prepare(case, output) for case in cases}
        protocol = {"schema_version": "project-policy-comparison-protocol-v1", "created_at_utc": datetime.now(timezone.utc).isoformat(),
                    "cases_file_sha256": cases_sha, "code_identities": code_ids(),
                    "cases": [prepared[method][0] for method, _ in ORDER],
                    "order": [{"case_id": prepared[method][0]["id"], "arms": list(order)} for method, order in ORDER],
                    "limits": {"primary_calls": 1, "source_read_limit": 8, "horizon_real_actions": 2,
                               "new_model_requests": 0, "new_fits": 0, "network_calls": 0},
                    "stop_rules": ["Stop after at most two actual actions or an explicit nonexecutable wait.",
                                   "Any error, unknown, pending, failed or rejected execution stops the entire run; no retry or replacement workspace.",
                                   "Changed code/input, invalid binding, source hash mismatch or broken read-only state is a protocol failure."],
                    "comparison_fields": ["action_order", "primary_metrics", "software_checks", "source_selections", "source_eligibility",
                                          "research_status", "execution_status", "next_task", "budget"],
                    "measurement": {"knowledge_query_calls": "Actual project_knowledge.query calls, including calls with no indexes.",
                                    "fts_search_calls": "Actual KnowledgeIndex.search calls; separate from empty-index query calls.",
                                    "output_total_bytes": "All files below the arm directory, including its project and prepared bundle; aggregate records are outside this scope.",
                                    "nested_elapsed": "Wrapper durations are nested inside stage wall time, not additive.",
                                    "cpu_seconds": None, "total_os_io_bytes": None, "human_time_seconds": None, "historical_cost_cny": None},
                    "shared_preparation_elapsed_seconds": time.perf_counter() - prep_started,
                    "module_import_elapsed_seconds": _IMPORT_SECONDS,
                    "interpretation_boundary": "Both arms use identical core extraction, FTS and result interpretation; this is not independent scientific reasoning or a user-value trial.",
                    "design_limitations": ["The one-primary-plus-source horizon checks dispatch and overhead, not open-ended adaptive strategy benefits.",
                                           "Existing archived materials are rebound, not newly acquired author evidence; three paired tasks do not establish generality.",
                                           "Steel uses a verified bundled dataset dependency in addition to its captured model/descriptor packet."],
                    "decision_rule": "Identical normalized outcomes imply no_observed_advantage; a single wall-time sample cannot establish superiority."}
        protocol["snapshot_sha256"] = fingerprint(protocol)
        write_json(output / "protocol.json", protocol, fresh=True)
        protocol_bytes_sha = sha((output / "protocol.json").read_bytes())
        progress.update(protocol_snapshot_sha256=protocol["snapshot_sha256"], protocol_bytes_sha256=protocol_bytes_sha)
        write_json(output / "progress.json", progress)
        for method, order in ORDER:
            frozen, manifest, assets = prepared[method]
            progress["arms"][frozen["id"]] = {}
            for arm in order:
                active = {"case_id": frozen["id"], "arm": arm}
                require(sha((output / "protocol.json").read_bytes()) == protocol_bytes_sha and code_ids() == protocol["code_identities"],
                        "PROTOCOL_CHANGED", "Frozen protocol or implementation changed before dispatch.")
                record = {}; progress["arms"][frozen["id"]][arm] = record
                run_arm(frozen, manifest, assets, arm, output, protocol, record)
                write_json(output / "progress.json", progress)
        comparisons = {case_id: compare(arms["fixed"], arms["adaptive"]) for case_id, arms in progress["arms"].items()}
        result = {"schema_version": "project-policy-comparison-result-v1", **progress, "comparisons": comparisons,
                  "conclusion": "no_observed_advantage" if all(item["same_normalized_outcome"] for item in comparisons.values()) else "observed_difference_requires_domain_judgment",
                  "scientific_validation": False, "user_value_evaluated": False, "history_cost_cny": None}
        require(code_ids() == protocol["code_identities"] and sha((output / "protocol.json").read_bytes()) == protocol_bytes_sha,
                "PROTOCOL_CHANGED", "Implementation or frozen protocol changed during the run.")
        write_json(output / "results.json", result, fresh=True)
        print(json.dumps({"ok": True, "conclusion": result["conclusion"], "cases": comparisons}, ensure_ascii=False))
        return 0
    except BaseException as error:
        failure = {"ok": False, "code": getattr(error, "code", type(error).__name__), "message": str(error),
                   "active_arm": active, "preserved": "Existing inputs, project ledgers and partial results are retained; no automatic retry.", "progress": progress}
        if created:
            write_json(output / "failure.json", failure, fresh=True)
        print(json.dumps({key: value for key, value in failure.items() if key != "progress"}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
