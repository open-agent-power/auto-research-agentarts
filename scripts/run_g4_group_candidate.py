"""Fixed, one-attempt G4-L helper evaluator; candidate source is AST data only.

prepare freezes inputs/rules before candidate authorship. inspect never executes
a helper. run requires an exact host review. replay never executes a helper.
No historical project DB is opened, fitted, migrated, or written.
"""
import argparse
import ast
from contextlib import ExitStack
import hashlib
from importlib.metadata import version
import json
import os
from pathlib import Path
import resource
import shutil
import signal
import statistics
import stat
import subprocess
import sys
import time
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from autoresearch.contracts import canonical, fingerprint, identifier
from g4_group_capability import Limits, CapabilityError, validate_group_program, execute_group_program

ADAPTER = "src/autoresearch/ridge_validation_adapter.py"
PROTOCOL = ROOT / "docs/execution/g4-local/protocol.md"
BASELINE = "def encode_groups(labels):\n    unique = list(dict.fromkeys(labels))\n    return [unique.index(label) for label in labels]\n"
CASES = {"concrete": ROOT / "runs/cloud-concrete-local-20261113-01",
         "real-estate": ROOT / "runs/g3-local-transfer-20261113-01/real-estate",
         "slump": ROOT / "runs/g3-local-transfer-20261113-01/slump"}
RULES = {"warmups_per_arm_per_dataset": 5, "paired_repetitions_per_dataset": 100,
         "alternating_pair_order": True, "source_speedup_at_least": 1.5,
         "source_saved_ns_at_least": 500000, "target_relative_slowdown_over": 0.10,
         "target_absolute_slowdown_ns_over": 50000, "candidate_attempt_limit": 1,
         "wall_seconds": 180, "cpu_soft_seconds": 120, "cpu_hard_seconds": 130,
         "address_space_bytes": 1073741824, "file_bytes": 33554432, "threads": 1}


def check(condition, message):
    if not condition:
        raise ValueError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def bounded(path, limit=33554432):
    check(path.is_file() and not path.is_symlink() and path.stat().st_size <= limit, "Oversized/nonregular source: " + str(path))
    with path.open("rb") as stream:
        raw = stream.read(limit + 1)
    check(len(raw) <= limit, "Source grew beyond its frozen read bound")
    return raw


def write(path, value, once=False):
    raw = (canonical(value) + "\n").encode()
    if once:
        with path.open("xb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
    else:
        temporary = path.with_suffix(path.suffix + ".pending")
        with temporary.open("wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(path)


def read(path):
    return json.loads(path.read_text())


def git(worktree, *arguments):
    return subprocess.run(["git", "-C", str(worktree), *arguments], check=True,
                          capture_output=True, text=True).stdout.strip()


def tree(worktree):
    check(not any(path.is_symlink() for path in (worktree, *worktree.parents)), "Worktree directory links are forbidden")
    files = git(worktree, "ls-files", "-z").split("\0")
    paths = [worktree / name for name in files if name]
    check(sum(path.stat().st_size for path in paths) <= 134217728, "Tracked tree exceeds host review bound")
    modes = {entry.split("\t",1)[1]: entry.split()[0] for entry in git(worktree,"ls-files","--stage","-z").split("\0") if entry}
    return {name: {"sha256": sha(bounded(worktree / name)), "git_mode": modes[name],
                   "filesystem_mode": stat.S_IMODE((worktree/name).stat().st_mode)} for name in files if name}


def case_identity(case):
    result = {}
    for path in sorted(case.rglob("*")):
        check(not path.is_symlink(), "Protected cases cannot contain links")
        if path.is_file():
            result[str(path.relative_to(case))] = sha(path.read_bytes())
    return result


def helper(module):
    check(len(module) <= 65536, "Candidate module exceeds the pre-AST byte ceiling")
    source = module.decode("utf-8")
    functions = [node for node in ast.parse(source).body if isinstance(node, ast.FunctionDef) and node.name == "encode_groups"]
    check(len(functions) == 1 and not functions[0].decorator_list, "Expected one plain encode_groups helper")
    node = functions[0]
    lines = source.splitlines(keepends=True)
    extracted = "".join(lines[node.lineno - 1:node.end_lineno])
    outside = "".join(lines[:node.lineno-1]) + "<fixed-helper>\n" + "".join(lines[node.end_lineno:])
    validate_group_program(extracted)
    return extracted, sha(outside.encode())


def expected_ids(labels):
    known, output = {}, []
    for parts in labels:
        label = tuple(parts)
        if label not in known:
            known[label] = len(known)
        output.append(known[label])
    return output


def prepare(root, baseline_worktree):
    check(not root.exists(), "Use a new outer directory")
    check(not any(root.is_relative_to(case) for case in CASES.values()) and not root.is_relative_to(baseline_worktree), "Outer evidence must stay outside historical cases and worktrees")
    check(not git(baseline_worktree, "status", "--porcelain"), "Baseline worktree must be clean")
    check(not git(baseline_worktree, "ls-files", "--others"), "Baseline cannot contain untracked/ignored additions")
    module = bounded(baseline_worktree / ADAPTER, 65536)
    source, outside_sha = helper(module)
    check(ast.dump(ast.parse(source)) == ast.dump(ast.parse(BASELINE)), "Baseline must retain the original first-appearance list/index semantics")
    check(PROTOCOL.is_file(), "Freeze the reviewed protocol before preparing the evaluator")
    root.mkdir(parents=True)
    (root / "inputs").mkdir()
    inputs, protected = {}, {}
    for name, case in CASES.items():
        protected[name] = case_identity(case)
        snapshot = read(case / "snapshots/finished.json")
        actions = [a for a in snapshot["actions"] if a["command"] == "data.ridge-group-validation"
                   and a["design_binding"]["resource"]["version"] == 1]
        check(len(actions) == 1, "Expected one saved raw baseline action per case")
        action = actions[0]
        projects = list((case / "manager/projects").glob("*"))
        check(len(projects) == 1, "Expected one native project")
        artifact_path = projects[0] / action["artifact"]
        envelope = read(artifact_path)
        check(envelope["action_id"] == action["id"] and envelope["source_snapshot_sha256"] == action["source_snapshot_sha256"]
              and envelope["sha256"] == action["result_sha256"] == fingerprint({k: v for k,v in envelope.items() if k != "sha256"}), "Saved action/artifact identity mismatch")
        analysis = envelope["tool_result"]["result"]["analysis"]
        rows = analysis["oof"]
        check([row["logical_record"] for row in rows] == list(range(1, len(rows)+1)), "OOF must retain complete original row order")
        data = {"labels": [row["groups"] for row in rows], "saved_folds": [row["fold"] for row in rows],
                "n_splits": len(analysis["folds"]), "logical_records": [row["logical_record"] for row in rows]}
        check(all(type(label) is list and label and all(type(x) is str for x in label) for label in data["labels"]), "Only primitive string group tuples are exposed")
        write(root / "inputs" / (name + ".json"), data, once=True)
        inputs[name] = {"path": str(case), "project_id": snapshot["id"], "action_id": action["id"],
            "source_snapshot_sha256": action["source_snapshot_sha256"], "artifact_sha256": sha(artifact_path.read_bytes()),
            "payload_sha256": sha((root / "inputs" / (name + ".json")).read_bytes()), "rows": len(rows),
            "groups": len({tuple(label) for label in data["labels"]})}
    (root / "baseline-helper.py").write_text(source)
    write(root / "baseline-tree.json", tree(baseline_worktree), once=True)
    write(root / "integrity-before.json", protected, once=True)
    controls = {str(path.relative_to(ROOT)): sha(path.read_bytes()) for path in
                (Path(__file__).resolve(), ROOT / "scripts/g4_group_capability.py", PROTOCOL)}
    manifest = {"schema_version": "g4-local-group-baseline-v1", "baseline_commit": git(baseline_worktree, "rev-parse", "HEAD"),
        "baseline_worktree": str(baseline_worktree), "baseline_tree_sha256": fingerprint(tree(baseline_worktree)),
        "baseline_tree_file_sha256": sha((root/"baseline-tree.json").read_bytes()),
        "module_sha256": sha(module), "helper_sha256": sha(source.encode()), "outside_helper_sha256": outside_sha,
        "allowed_modified_paths": [ADAPTER], "controls": controls, "inputs": inputs, "rules": RULES,
        "capability_limits": Limits().__dict__, "dependencies": {name: version(name) for name in ("numpy", "scikit-learn")},
        "model": None, "product_model_sends": 0, "fits": 0, "development_cost": None,
        "trust_scope": "Shared-user trusted reviewed AST interpreter; no OS isolation, sealed labels or production promotion"}
    write(root / "baseline-manifest.json", manifest, once=True)
    return {"status": "baseline_frozen_no_candidate_executed", "baseline_manifest_sha256": sha((root / "baseline-manifest.json").read_bytes()), "inputs": inputs}


def frozen(root):
    manifest = read(root / "baseline-manifest.json")
    check(manifest["rules"] == RULES and manifest["capability_limits"] == Limits().__dict__, "Frozen control policy changed")
    check(manifest["dependencies"] == {name: version(name) for name in ("numpy", "scikit-learn")}, "Frozen dependency versions changed")
    baseline_worktree = Path(manifest["baseline_worktree"])
    check(git(baseline_worktree,"rev-parse","HEAD") == manifest["baseline_commit"]
          and fingerprint(tree(baseline_worktree)) == manifest["baseline_tree_sha256"]
          and sha((root/"baseline-tree.json").read_bytes()) == manifest["baseline_tree_file_sha256"], "Frozen baseline worktree/code identity changed")
    for name, digest in manifest["controls"].items():
        check(sha((ROOT / name).read_bytes()) == digest, "Protected evaluator/capability/protocol changed: " + name)
    check(sha((root / "baseline-helper.py").read_bytes()) == manifest["helper_sha256"], "Frozen baseline helper changed")
    for name, item in manifest["inputs"].items():
        check(sha((root / "inputs" / (name + ".json")).read_bytes()) == item["payload_sha256"], "Frozen group payload changed")
    return manifest


def inspect(root, candidate_worktree):
    manifest = frozen(root)
    modified = git(candidate_worktree, "diff", "--name-only", manifest["baseline_commit"], "--").splitlines()
    check(modified == [ADAPTER] and not git(candidate_worktree, "ls-files", "--others"), "Only the reviewed helper module may change; untracked/ignored files are forbidden")
    module = bounded(candidate_worktree / ADAPTER, 65536)
    source, outside_sha = helper(module)
    check(outside_sha == manifest["outside_helper_sha256"], "Changes outside the encode_groups helper are forbidden")
    current_tree, original_tree = tree(candidate_worktree), read(root/"baseline-tree.json")
    check(set(current_tree) == set(original_tree) and all(current_tree[k] == v for k,v in original_tree.items() if k != ADAPTER)
          and all(current_tree[ADAPTER][k] == original_tree[ADAPTER][k] for k in ("git_mode","filesystem_mode")), "Unreviewed tracked-tree or mode change")
    return {"schema_version": "g4-helper-review-binding-v1", "baseline_manifest_sha256": sha((root/"baseline-manifest.json").read_bytes()),
        "baseline_evaluation_sha256": sha((root/"baseline-evaluation.json").read_bytes()), "diagnosis_sha256": sha((root/"diagnosis.json").read_bytes()),
        "candidate_module_sha256": sha(module), "candidate_helper_sha256": sha(source.encode()),
        "candidate_tree_sha256": fingerprint(current_tree), "allowed_modified_paths": [ADAPTER]}


def setup_limits():
    for name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS", "VECLIB_MAXIMUM_THREADS"):
        os.environ[name] = "1"
    for kind, wanted in ((resource.RLIMIT_CPU, (120, 130)), (resource.RLIMIT_AS, (1073741824, 1073741824)),
                         (resource.RLIMIT_FSIZE, (33554432, 33554432))):
        resource.setrlimit(kind, wanted)
        check(resource.getrlimit(kind) == wanted, "Requested process resource bounds did not take effect")
    def timeout(*_):
        raise TimeoutError("Frozen wall/CPU limit reached")
    signal.signal(signal.SIGALRM, timeout)
    signal.signal(signal.SIGXCPU, timeout)
    signal.alarm(RULES["wall_seconds"])
    check(shutil.disk_usage(ROOT).free > 5 * 1024 ** 3, "Insufficient host disk headroom")
    return {"cpu_seconds": list(resource.getrlimit(resource.RLIMIT_CPU)), "address_space_bytes": list(resource.getrlimit(resource.RLIMIT_AS)),
            "file_bytes": list(resource.getrlimit(resource.RLIMIT_FSIZE)), "wall_alarm_seconds": signal.alarm(0), "threads": 1}


def split_check(ids, data):
    import numpy as np
    from sklearn.model_selection import GroupKFold
    array = np.asarray(ids, dtype=np.int64)
    check(array.shape == (len(data["labels"]),) and ids == expected_ids(data["labels"]), "Group IDs/shape/order mismatch")
    folds = np.zeros(len(ids), dtype=np.int64)
    for fold, (train, test) in enumerate(GroupKFold(data["n_splits"]).split(np.zeros((len(ids), 1)), groups=array), 1):
        check(not set(array[train]).intersection(array[test]), "Group leakage")
        folds[test] = fold
    check(folds.tolist() == data["saved_folds"], "Saved original train/test membership changed")
    return {"rows": len(ids), "dtype": str(array.dtype), "shape": list(array.shape), "saved_folds_exact": True}


def baseline(root):
    """Three fixed baseline-only calls after freeze, before candidate authorship."""
    manifest = frozen(root)
    if (root / "baseline-evaluation.json").exists():
        check(read(root / "baseline-attempt.json")["baseline_evaluation_sha256"] == sha((root/"baseline-evaluation.json").read_bytes()), "Saved baseline evaluation changed")
        return read(root / "baseline-evaluation.json")
    check(not (root / "baseline-attempt.json").exists(), "Baseline phase unresolved; do not repeat")
    observations = setup_limits()
    signal.alarm(RULES["wall_seconds"])
    write(root / "baseline-attempt.json", {"status": "running", "baseline_manifest_sha256": sha((root/"baseline-manifest.json").read_bytes())}, once=True)
    try:
        results = {}
        source = (root / "baseline-helper.py").read_text()
        with patch("sklearn.linear_model.Ridge.fit", side_effect=AssertionError("Fits forbidden")), patch("sklearn.preprocessing.StandardScaler.fit", side_effect=AssertionError("Fits forbidden")):
            for name in manifest["inputs"]:
                data = read(root / "inputs" / (name + ".json"))
                started = time.perf_counter_ns()
                result = execute_group_program(source, data["labels"], limits=Limits(**manifest["capability_limits"]))
                elapsed = time.perf_counter_ns() - started
                results[name] = {**result, "one_call_nanoseconds": elapsed, "split_check": split_check(result["group_ids"], data)}
        after = {name: case_identity(Path(item["path"])) for name, item in manifest["inputs"].items()}
        write(root / "baseline-integrity-after.json", after, once=True)
        check(after == read(root/"integrity-before.json"), "Historical case changed during baseline evaluation")
        receipt = {"status": "baseline_evaluated_before_candidate", "baseline_manifest_sha256": sha((root/"baseline-manifest.json").read_bytes()),
            "execution_mode": "closed_AST_interpreter", "resource_observations": observations, "datasets": results,
            "helper_calls": 3, "candidate_calls": 0, "fits": 0, "product_model_sends": 0}
        write(root / "baseline-evaluation.json", receipt, once=True)
        write(root / "diagnosis.json", {"status": "diagnosis_recorded_before_candidate", "baseline_evaluation_sha256": sha((root/"baseline-evaluation.json").read_bytes()),
            "observation": "Fixed baseline repeats list.index over first-appearance unique labels; interpreter work counters and row/group sizes are preserved",
            "hypothesis": "A reviewed bounded label-to-ID map may lower closed-interpreter encoding latency while preserving every ID and saved fold",
            "falsification": "Any ID/fold/preservation/capability failure, insufficient frozen source gain or adverse target slowdown rejects",
            "limitation": "These baseline-only single timings are descriptive; formal paired batch is later and does not measure native full CV"}, once=True)
        write(root / "baseline-attempt.json", {"status": "completed", "baseline_evaluation_sha256": sha((root/"baseline-evaluation.json").read_bytes())})
        return receipt
    except BaseException as error:
        failure = {"type": type(error).__name__, "code": getattr(error, "code", None), "message": str(error),
                   "usage": getattr(error, "usage", None), "status": "unresolved_baseline_no_retry"}
        try:
            after = {name: case_identity(Path(item["path"])) for name, item in manifest["inputs"].items()}
            write(root / "baseline-failure-integrity-after.json", after)
            failure["historical_files_unchanged"] = after == read(root / "integrity-before.json")
        except Exception as integrity_error:
            failure["integrity_check_error"] = str(integrity_error)
        write(root / "baseline-error.json", failure)
        raise
    finally:
        signal.alarm(0)


def run(root, candidate_worktree, review_path, request_id):
    identifier(request_id)
    manifest = frozen(root)
    check((root / "diagnosis.json").is_file() and read(root / "baseline-attempt.json")["status"] == "completed", "Evaluate the fixed baseline and record diagnosis before candidate authorship")
    binding = inspect(root, candidate_worktree)
    review = read(review_path)
    check(set(review) == set(binding) | {"status", "reviewer", "reason"} and all(review[k] == v for k, v in binding.items())
          and review["status"] == "approved_for_capability_evaluation" and review["reviewer"] and review["reason"], "Exact independent host review is required")
    request = {"request_id": request_id, "binding": binding, "review_sha256": sha(review_path.read_bytes())}
    attempt_path = root / "attempt.json"
    if attempt_path.exists():
        attempt = read(attempt_path)
        check(attempt["request_fingerprint"] == fingerprint(request), "One candidate attempt cannot be replaced or reset by another ID/source")
        check(attempt["status"] == "completed", "Original attempt unresolved; no automatic re-execution")
        return replay(root)
    check({name: case_identity(Path(item["path"])) for name, item in manifest["inputs"].items()} == read(root/"integrity-before.json"), "Historical case files changed before evaluation")
    baseline = (root / "baseline-helper.py").read_text()
    candidate_module = bounded(candidate_worktree / ADAPTER, 65536)
    candidate = helper(candidate_module)[0]
    check(sha(candidate_module) == binding["candidate_module_sha256"] and sha(candidate.encode()) == binding["candidate_helper_sha256"], "Reviewed candidate changed before capture")
    observations = setup_limits()
    # setup_limits reports then disarms the alarm; arm it for the actual batch.
    signal.alarm(RULES["wall_seconds"])
    write(attempt_path, {**request, "request_fingerprint": fingerprint(request), "attempt": 1, "status": "running", "resource_observations": observations}, once=True)
    wall, cpu = time.perf_counter(), time.process_time()
    correctness, outcomes, decisions = [], {}, {}
    try:
        with (root / "candidate-helper.py").open("x") as source_file:
            source_file.write(candidate)
        with ExitStack() as stack:
            stack.enter_context(patch("sklearn.linear_model.Ridge.fit", side_effect=AssertionError("Fits forbidden")))
            stack.enter_context(patch("sklearn.preprocessing.StandardScaler.fit", side_effect=AssertionError("Fits forbidden")))
            for name, labels in {"empty": [], "one_group": [["x"]]*3, "order_unicode": [["z"], ["α"], ["z"], ["a"]],
                                 "multi_field": [["a", "b"], ["b", "a"], ["a", "b"]], "maximum_unique": [[str(i)] for i in range(2048)]}.items():
                for arm, source in (("baseline", baseline), ("candidate", candidate)):
                    result = execute_group_program(source, labels, limits=Limits(**manifest["capability_limits"]))
                    check(result["group_ids"] == expected_ids(labels), "Synthetic engineering IDs differ: " + name)
                    correctness.append({"engineering_case": name, "arm": arm, "output_sha256": result["output_sha256"], "usage": result["usage"]})
            with (root / "timings.jsonl").open("x") as timing_file:
                for name in manifest["inputs"]:
                    data = read(root / "inputs" / (name + ".json"))
                    sources = {"baseline": baseline, "candidate": candidate}
                    results = {arm: execute_group_program(source, data["labels"], limits=Limits(**manifest["capability_limits"])) for arm, source in sources.items()}
                    outcomes[name] = {arm: {"group_ids": result["group_ids"], "output_sha256": result["output_sha256"],
                        "usage": result["usage"], "split_check": split_check(result["group_ids"], data)} for arm, result in results.items()}
                    for _ in range(5):
                        for source in sources.values():
                            execute_group_program(source, data["labels"], limits=Limits(**manifest["capability_limits"]))
                    durations = {"baseline": [], "candidate": []}
                    for pair in range(100):
                        order = ("baseline", "candidate") if pair % 2 == 0 else ("candidate", "baseline")
                        for arm in order:
                            started = time.perf_counter_ns()
                            result = execute_group_program(sources[arm], data["labels"], limits=Limits(**manifest["capability_limits"]))
                            elapsed = time.perf_counter_ns() - started
                            check(result["group_ids"] == results["baseline"]["group_ids"], "Timed result drift")
                            durations[arm].append(elapsed)
                            timing_file.write(canonical({"dataset": name, "pair": pair, "arm": arm, "nanoseconds": elapsed,
                                "output_sha256": result["output_sha256"], "usage": result["usage"]}) + "\n")
                    base, changed = (statistics.median(durations[arm]) for arm in ("baseline", "candidate"))
                    decisions[name] = {"baseline_median_ns": base, "candidate_median_ns": changed, "speedup": base/changed,
                        "median_saved_ns": base-changed, "paired_saving_median_ns": statistics.median(a-b for a,b in zip(durations["baseline"],durations["candidate"]))}
        after = {name: case_identity(Path(item["path"])) for name, item in manifest["inputs"].items()}
        write(root / "integrity-after.json", after, once=True)
        check(after == read(root/"integrity-before.json"), "Historical case changed")
        frozen(root)
        check(inspect(root, candidate_worktree) == binding, "Candidate changed during its fixed evaluation")
        source_pass = decisions["concrete"]["speedup"] >= 1.5 and decisions["concrete"]["median_saved_ns"] >= 500000
        targets_pass = all(not (v["candidate_median_ns"] > v["baseline_median_ns"] * 1.1 and
            v["candidate_median_ns"] - v["baseline_median_ns"] > 50000) for k,v in decisions.items() if k != "concrete")
        write(root / "correctness.json", correctness, once=True)
        write(root / "dataset-results.json", outcomes, once=True)
        artifact_names = ("timings.jsonl", "correctness.json", "dataset-results.json", "integrity-after.json", "candidate-helper.py", "baseline-evaluation.json", "diagnosis.json")
        receipt = {"request": request, "attempt": 1, "status": "accepted_for_future_review" if source_pass and targets_pass else "rejected",
            "criteria": {"source_latency": source_pass, "target_no_adverse_slowdown": targets_pass, "correctness": True, "historical_files_unchanged": True},
            "timing_summary": decisions, "wall_seconds": time.perf_counter()-wall, "cpu_seconds": time.process_time()-cpu,
            "fits": 0, "product_model_sends": 0, "candidate_attempts": 1, "trust_scope": manifest["trust_scope"],
            "execution_mode": "closed_AST_interpreter", "artifacts": {name: {"sha256": sha((root/name).read_bytes()), "bytes": (root/name).stat().st_size} for name in artifact_names},
            "limitation": "Interpreter-helper latency only; not native Python, full CV, scientific benefit, OS isolation or production promotion"}
        write(root / "result.json", receipt, once=True)
        write(attempt_path, {**read(attempt_path), "status": "completed", "result_sha256": sha((root/"result.json").read_bytes())})
        return receipt
    except BaseException as error:
        failure = {"type": type(error).__name__, "code": getattr(error, "code", None),
            "message": str(error), "usage": getattr(error, "usage", None), "status": "unresolved_attempt_no_retry"}
        try:
            after = {name: case_identity(Path(item["path"])) for name, item in manifest["inputs"].items()}
            write(root / "failure-integrity-after.json", after)
            failure["historical_files_unchanged"] = after == read(root / "integrity-before.json")
        except Exception as integrity_error:
            failure["integrity_check_error"] = str(integrity_error)
        write(root / "error.json", failure)
        raise
    finally:
        signal.alarm(0)


def replay(root):
    frozen(root)
    attempt = read(root / "attempt.json")
    check(attempt["status"] == "completed", "Original attempt unresolved")
    check(sha((root/"baseline-manifest.json").read_bytes()) == attempt["binding"]["baseline_manifest_sha256"], "Frozen manifest changed")
    check(sha((root/"result.json").read_bytes()) == attempt["result_sha256"], "Original receipt changed")
    receipt = read(root / "result.json")
    for name, metadata in receipt["artifacts"].items():
        check(sha((root/name).read_bytes()) == metadata["sha256"] and (root/name).stat().st_size == metadata["bytes"], "Completed evidence changed: " + name)
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for command in ("prepare", "baseline", "inspect", "run", "replay"):
        sub = commands.add_parser(command)
        sub.add_argument("--root", required=True)
        if command == "prepare":
            sub.add_argument("--baseline-worktree", required=True)
        if command in ("inspect", "run"):
            sub.add_argument("--candidate-worktree", required=True)
        if command == "run":
            sub.add_argument("--review", required=True)
            sub.add_argument("--request-id", required=True)
        if command == "replay":
            sub.add_argument("--execution-disabled", action="store_true", required=True)
    args = parser.parse_args()
    root = Path(args.root).resolve()
    if args.command == "prepare":
        result = prepare(root, Path(args.baseline_worktree).resolve())
    elif args.command == "baseline":
        result = baseline(root)
    elif args.command == "inspect":
        result = inspect(root, Path(args.candidate_worktree).absolute())
    elif args.command == "run":
        result = run(root, Path(args.candidate_worktree).absolute(), Path(args.review).absolute(), args.request_id)
    else:
        with patch(__name__ + ".execute_group_program", side_effect=AssertionError("Replay execution forbidden")):
            result = replay(root)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
