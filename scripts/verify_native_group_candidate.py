"""One separately approved native confirmation of two exact reviewed helpers.

prepare is static: no VM execution, bytecode compilation or helper invocation.
run first qualifies six exact VM/input pairs, then compiles only the two typed
pure helper ASTs. Original candidate modules are never imported or executed.
"""
import argparse
import ast
from contextlib import ExitStack
import hashlib
from importlib.metadata import version
import json
import os
from pathlib import Path
import platform
import re
import resource
import signal
import statistics
import sys
import time
from types import CodeType, FunctionType
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
VM_ROOT = ROOT / "runs/g4-local-group-20261113-01"
PROTOCOL = ROOT / "docs/execution/g4-local/native-confirmation-protocol.md"
sys.path.insert(0, str(Path(__file__).resolve().parent))
import g4_group_capability as vm

HELPERS = {"baseline": "21d726c2bc6e9f027ee2d8525f23d069fb489f4af340523105d75a3053d10eb0",
           "candidate": "c021c1ebf275ed42e07936c0b31a675d3017b7e7bef06b2c26318d5adf41358b"}
INPUTS = {"concrete": "18fdf2174c1ba02589d828a64bd06c063014380914f477b191b75c253c0205e0",
          "real-estate": "8f04038e7fe9b7e83bbf1531064ce2dd42d063aeccc031c28193f1a71925b7fb",
          "slump": "17b1e78e8dc43064a4f069f997da67d2b5f10b7614c44e81bc1231ed96f7c25c"}
VM_PINS = {"baseline-manifest.json": "af504f90ca10d75ec7bf5207e7f5c9031650ddc4f09802c395f482daff8e19c8",
           "result.json": "090be45b48bd72dd412941c322281f69d3f9b32b936f4c5d023beed5e5df5499"}
OLD_CONTROLS = {"scripts/g4_group_capability.py": "422e57f6145e85bb384cb52b6433b81ca16a523c2b49d0371ffc6af483263e71",
                "scripts/run_g4_group_candidate.py": "787eae6dc8e710fc12ad9f3a02f6ff42f442c109d2cb96386f43bca71aff18f2",
                "docs/execution/g4-local/protocol.md": "7820a4c4f77059ae5dba3f08fff43f065eedd5d615f83e9a831f72ad7dab7147"}
RULES = {"warmups": 5, "pairs": 100, "attempt_limit": 1, "source_speedup": 1.5,
         "source_saving_ns": 500000, "target_slowdown_fraction": 0.10, "target_slowdown_ns": 50000,
         "wall_seconds": 180, "cpu_soft": 120, "cpu_hard": 130, "address_bytes": 1073741824,
         "file_bytes": 33554432, "threads": 1}
REQUEST_ID = "g4-native-confirmation-001"


def check(condition, message):
    if not condition:
        raise ValueError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def bounded(path, maximum=33554432):
    check(not any(p.is_symlink() for p in (path, *path.parents)), "Linked paths are forbidden")
    check(path.is_file() and path.stat().st_nlink == 1 and path.stat().st_size <= maximum, "Unlinked regular bounded file required")
    with path.open("rb") as stream:
        raw = stream.read(maximum + 1)
    check(len(raw) <= maximum, "Read bound exceeded")
    return raw


def _pairs(items):
    result = {}
    for key, value in items:
        check(key not in result, "Duplicate JSON key")
        result[key] = value
    return result


def decode(raw):
    return json.loads(raw, object_pairs_hook=_pairs,
                      parse_constant=lambda _: (_ for _ in ()).throw(ValueError("Nonfinite JSON")))


def read(path):
    return decode(bounded(path))


def write(path, value, replace=False):
    raw = canonical(value) + b"\n"
    target = path.with_suffix(".pending") if replace else path
    with target.open("xb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    if replace:
        target.replace(path)


def pure_ast(raw):
    """Type-check a mutation-free native subset; does not compile or run code."""
    vm_validation = vm.validate_group_program(raw)
    module = ast.parse(raw.decode("utf-8"))
    fn = module.body[0]
    allowed = {ast.Module, ast.FunctionDef, ast.arguments, ast.arg, ast.Assign, ast.Return,
               ast.Name, ast.Load, ast.Store, ast.Call, ast.Attribute, ast.ListComp,
               ast.DictComp, ast.comprehension, ast.Tuple, ast.Subscript}
    check(all(type(n) in allowed for n in ast.walk(module)), "Native syntax is not in the pure subset")
    env = {"labels": "sequence_label"}
    builtins = {"list", "len", "enumerate", "dict"}

    def expression(node, scope, iterator=False):
        if type(node) is ast.Name:
            check(node.id in scope, "Unknown native local/global")
            return scope[node.id]
        if type(node) is ast.Call:
            check(not node.keywords, "Native keywords forbidden")
            if type(node.func) is ast.Name:
                name = node.func.id
                check(name in {"list", "len", "enumerate"} and len(node.args) == 1, "Native intrinsic arity/name rejected")
                arg = expression(node.args[0], scope)
                check(arg in {"sequence_label", "list_label", "dictionary_none", "dictionary_int"}, "Native intrinsic operand rejected")
                if name == "enumerate":
                    check(iterator, "enumerate must be consumed directly by a finite comprehension")
                    return "enumerated_label"
                return "list_label" if name == "list" else "int"
            check(type(node.func) is ast.Attribute and type(node.func.value) is ast.Name,
                  "Native attribute chain rejected")
            receiver, method = node.func.value.id, node.func.attr
            if receiver == "dict":
                check(method == "fromkeys" and len(node.args) == 1, "Only pure dict.fromkeys is exposed")
                check(expression(node.args[0], scope) in {"sequence_label", "list_label", "dictionary_none", "dictionary_int"}, "Invalid fromkeys operand")
                return "dictionary_none"
            check(method == "index" and scope.get(receiver) == "list_label" and len(node.args) == 1
                  and expression(node.args[0], scope) == "label", "Only a private list's index(label) is exposed")
            return "int"
        if type(node) is ast.Subscript:
            check(type(node.value) is ast.Name and scope.get(node.value.id) == "dictionary_int"
                  and expression(node.slice, scope) == "label", "Only private integer-dictionary label lookup is exposed")
            return "int"
        check(type(node) in (ast.ListComp, ast.DictComp) and len(node.generators) == 1, "Native expression rejected")
        generator = node.generators[0]
        check(not generator.ifs and not generator.is_async, "Native filters/async rejected")
        source_type = expression(generator.iter, scope, iterator=True)
        local = scope.copy()
        names = [generator.target] if type(generator.target) is ast.Name else generator.target.elts
        types = ["int", "label"] if source_type == "enumerated_label" else ["label"]
        check(source_type in {"enumerated_label", "sequence_label", "list_label", "dictionary_none", "dictionary_int"}
              and len(names) == len(types) and all(type(n) is ast.Name for n in names), "Native comprehension binding rejected")
        for name, data_type in zip(names, types):
            check(name.id not in builtins | set(scope) | {"encode_groups"}, "Native comprehension shadowing rejected")
            local[name.id] = data_type
        if type(node) is ast.DictComp:
            check(expression(node.key, local) == "label" and expression(node.value, local) == "int", "Native dictionary element types rejected")
            return "dictionary_int"
        check(expression(node.elt, local) == "int", "Native list elements must be integers")
        return "list_int"

    check(type(fn.body[-1]) is ast.Return, "Native helper must end in one return")
    for statement in fn.body[:-1]:
        check(type(statement) is ast.Assign and len(statement.targets) == 1
              and type(statement.targets[0]) is ast.Name, "Native helper permits name assignment only")
        name = statement.targets[0].id
        check(name not in env and name not in builtins | {"encode_groups"}, "Native locals are single-assignment and cannot shadow capabilities")
        env[name] = expression(statement.value, env)
    check(expression(fn.body[-1].value, env) == "list_int", "Native return must be list[int]")
    return module, {**vm_validation, "native_type_check": "pure_labels_to_list_int", "native_compiled": False}


def approved_ast(arm, raw):
    check(arm in HELPERS and sha(raw) == HELPERS[arm], "Only the two previously reviewed exact helper hashes are permitted")
    return pure_ast(raw)


def load_vm():
    for relative, digest in OLD_CONTROLS.items():
        check(sha(bounded(ROOT / relative)) == digest, "Original frozen VM control changed")
    captures = {relative: bounded(VM_ROOT / relative) for relative in VM_PINS}
    for relative, digest in VM_PINS.items():
        check(sha(captures[relative]) == digest, "Original approved VM evidence changed")
    manifest, result = decode(captures["baseline-manifest.json"]), decode(captures["result.json"])
    attempt = read(VM_ROOT / "attempt.json")
    check(result["status"] == "accepted_for_future_review" and result["execution_mode"] == "closed_AST_interpreter"
          and attempt["status"] == "completed" and attempt["result_sha256"] == VM_PINS["result.json"], "Original VM qualification absent")
    artifact_bytes = {}
    for name, entry in result["artifacts"].items():
        raw = bounded(VM_ROOT / name)
        check(sha(raw) == entry["sha256"] and len(raw) == entry["bytes"], "Original VM artifact changed")
        artifact_bytes[name] = raw
    sources, data, validation = {}, {}, {}
    for arm in HELPERS:
        sources[arm] = bounded(VM_ROOT / (arm + "-helper.py"), vm.MAX_SOURCE_BYTES)
        _, validation[arm] = approved_ast(arm, sources[arm])
    for name, digest in INPUTS.items():
        raw = bounded(VM_ROOT / "inputs" / (name + ".json"))
        check(sha(raw) == digest == manifest["inputs"][name]["payload_sha256"], "Only the three frozen input payloads are permitted")
        data[name] = decode(raw)
    return manifest, sources, data, validation, decode(artifact_bytes["integrity-after.json"])


def snapshot(manifest):
    roots = {"original_vm": VM_ROOT, **{name: Path(item["path"]) for name, item in manifest["inputs"].items()}}
    result = {}
    for label, root in roots.items():
        entries = sorted(root.rglob("*"))
        check(not any(p.is_symlink() for p in (root, *root.parents, *entries)), "Protected tree links are forbidden")
        result[label] = {str(p.relative_to(root)): sha(bounded(p)) for p in entries if p.is_file()}
    return result


def controls():
    return {str(p.relative_to(ROOT)): sha(bounded(p)) for p in (Path(__file__).resolve(), PROTOCOL)}


def prepare(output):
    check(output.parent == ROOT / "runs" and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,100}", output.name)
          and not output.exists() and not output.is_symlink()
          and not any(p.is_symlink() for p in output.parents), "Use a fresh directly contained runs directory")
    manifest, _, _, validation, protected_reference = load_vm()
    integrity = snapshot(manifest)
    check({k: v for k, v in integrity.items() if k != "original_vm"} == protected_reference,
          "Historical cases no longer match the approved VM before-image")
    frozen = {"schema_version": "g4-fixed-native-confirmation-freeze-v1", "request_id": REQUEST_ID,
              "output_root": str(output),
              "vm_root": str(VM_ROOT), "vm_evidence": VM_PINS, "helpers": HELPERS, "inputs": INPUTS,
              "controls": controls(), "rules": RULES, "vm_limits": vm.Limits().__dict__,
              "integrity_before_sha256": sha(canonical(integrity) + b"\n"),
              "python": sys.version, "platform": platform.platform(),
              "dependencies": {name: version(name) for name in ("numpy", "scikit-learn")},
              "validation": validation, "fits": 0, "product_model_calls": 0,
              "trust_scope": "Two exact reviewed pure native microfunctions; not OS isolation, general execution or production promotion"}
    check(frozen["dependencies"] == manifest["dependencies"], "Dependency drift from original VM")
    output.mkdir()
    write(output / "integrity-before.json", integrity)
    write(output / "freeze.json", frozen)
    write(output / "review-request.json", {"schema_version": "g4-native-confirmation-review-v1", "status": "pending_independent_review",
          "reviewer": None, "freeze_sha256": sha(bounded(output / "freeze.json")), "helpers": HELPERS,
          "inputs": INPUTS, "controls": frozen["controls"], "reason": "New explicit compile/native capability requires independent review; prepare has not compiled or executed helpers."})
    return {"status": "prepared_not_compiled_or_executed", "freeze_sha256": sha(bounded(output / "freeze.json")), "validation": validation}


def frozen(output):
    raw = bounded(output / "freeze.json")
    value = decode(raw)
    check(value["schema_version"] == "g4-fixed-native-confirmation-freeze-v1" and value["rules"] == RULES
          and value["helpers"] == HELPERS and value["inputs"] == INPUTS and value["vm_evidence"] == VM_PINS
          and value["controls"] == controls() and value["request_id"] == REQUEST_ID
          and value["vm_limits"] == vm.Limits().__dict__ and value["vm_root"] == str(VM_ROOT)
          and value["python"] == sys.version
          and value["integrity_before_sha256"] == sha(bounded(output / "integrity-before.json"))
          and value["dependencies"] == {n: version(n) for n in ("numpy", "scikit-learn")}, "Native freeze/control/environment mismatch")
    return value, sha(raw)


def resources():
    for name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS", "VECLIB_MAXIMUM_THREADS"):
        os.environ[name] = "1"
    for kind, values in ((resource.RLIMIT_CPU, (120, 130)), (resource.RLIMIT_AS, (1073741824, 1073741824)), (resource.RLIMIT_FSIZE, (33554432, 33554432))):
        resource.setrlimit(kind, values)
        check(resource.getrlimit(kind) == values, "Process safeguard not enforced")
    def deadline(*_):
        raise TimeoutError("Native-confirmation deadline reached")
    signal.signal(signal.SIGALRM, deadline)
    signal.signal(signal.SIGXCPU, deadline)
    signal.alarm(180)
    return {"wall_seconds": 180, "cpu": list(resource.getrlimit(resource.RLIMIT_CPU)),
            "address_space": list(resource.getrlimit(resource.RLIMIT_AS)), "file_bytes": list(resource.getrlimit(resource.RLIMIT_FSIZE)), "threads": 1}


def native_function(arm, raw):
    module, validation = approved_ast(arm, raw)
    # NEW PHASE: executable native compilation is explicitly gated/reviewed.
    # Module code is never executed: extract only the validated function code.
    code = compile(module, "<fixed-reviewed-" + arm + ">", "exec", dont_inherit=True, optimize=0)
    functions = [item for item in code.co_consts if type(item) is CodeType]
    check(code.co_names == ("encode_groups",) and all(item is None or type(item) is CodeType for item in code.co_consts),
          "Unexpected top-level compiled names/constants")
    check(len(functions) == 1 and functions[0].co_name == "encode_groups" and not functions[0].co_freevars
          and functions[0].co_argcount == 1 and functions[0].co_kwonlyargcount == 0,
          "Unexpected compiled function/closure")
    pending = [functions[0]]
    lexical = set(functions[0].co_varnames) | set(functions[0].co_cellvars)
    while pending:
        part = pending.pop()
        check(set(part.co_names) <= {"list", "dict", "len", "enumerate", "fromkeys", "index"}
              and set(part.co_freevars) <= lexical, "Unexpected compiled global/free-variable access")
        for item in part.co_consts:
            if type(item) is CodeType:
                check(item.co_name in {"<listcomp>", "<dictcomp>"}, "Unexpected nested native function")
                pending.append(item)
            else:
                check(item is None or type(item) is int and abs(item) <= vm.MAX_ROWS, "Unexpected compiled literal/object")
    namespace = {"__builtins__": {"list": list, "dict": dict, "len": len, "enumerate": enumerate}}
    return FunctionType(functions[0], namespace, "encode_groups"), validation


def primitive_labels(payload):
    labels = payload["labels"]
    check(type(labels) is list and len(labels) <= vm.MAX_ROWS, "Native input row/type limit")
    for label in labels:
        check(type(label) is list and 1 <= len(label) <= vm.MAX_GROUP_FIELDS
              and all(type(x) is str and len(x) <= vm.MAX_LABEL_CHARS for x in label), "Native primitive label type/shape limit")
        for value in label:
            value.encode("utf-8", errors="strict")
    groups = len({tuple(label) for label in labels})
    cells = 8 * len(labels) + 8 * groups + sum(map(len, labels)) + 64
    check(cells <= vm.MAX_ALLOCATED_CELLS, "Native private-container cell estimate exceeds the fixed allowance")
    return tuple(tuple(value for value in label) for label in labels), cells


def split_check(ids, data):
    import numpy as np
    from sklearn.model_selection import GroupKFold
    expected, known = [], {}
    for label in data["labels"]:
        key = tuple(label)
        known.setdefault(key, len(known))
        expected.append(known[key])
    check(type(ids) is list and all(type(x) is int for x in ids) and ids == expected, "Native IDs/type/order differ")
    array, reference = np.array(ids), np.array(expected)
    check(array.dtype == reference.dtype and array.shape == reference.shape, "Array dtype/shape differ")
    folds = np.zeros(len(ids), dtype=np.int64)
    for fold, (train, test) in enumerate(GroupKFold(data["n_splits"]).split(np.zeros((len(ids), 1)), groups=array), 1):
        check(not set(array[train]).intersection(array[test]), "Native group leakage")
        folds[test] = fold
    check(folds.tolist() == data["saved_folds"], "Saved fold assignment differs")
    return {"ids_sha256": sha(canonical(ids)), "group_ids": ids.copy(), "dtype": str(array.dtype),
            "rows": len(ids), "folds": folds.tolist(), "folds_unchanged": True}


def replay(output):
    _, freeze_sha = frozen(output)
    manifest, _, _, _, _ = load_vm()
    attempt = read(output / "attempt.json")
    result_raw = bounded(output / "result.json")
    check(attempt["status"] == "completed" and attempt["request_id"] == REQUEST_ID
          and attempt["freeze_sha256"] == freeze_sha
          and attempt["result_sha256"] == sha(result_raw), "Original native attempt unresolved/changed")
    result = decode(result_raw)
    check(sha(bounded(output / "independent-native-review.json")) == attempt["review_sha256"], "Native review original changed/missing")
    for name, item in result["artifacts"].items():
        raw = bounded(output / name)
        check(sha(raw) == item["sha256"] and len(raw) == item["bytes"], "Native completion artifact changed")
    check(snapshot(manifest) == read(output / "integrity-before.json"), "Protected history changed after native completion")
    return result


def run(output, review_path):
    freeze, freeze_sha = frozen(output)
    check(freeze["output_root"] == str(output), "Native approval binds the original one-attempt output root; copies are replay-only")
    manifest, sources, data, _, _ = load_vm()
    review_raw = bounded(review_path)
    review = decode(review_raw)
    expected = {"schema_version", "status", "reviewer", "freeze_sha256", "helpers", "inputs", "controls", "reason"}
    check(set(review) == expected and review["schema_version"] == "g4-native-confirmation-review-v1"
          and review["status"] == "approved_for_fixed_native_confirmation"
          and review["freeze_sha256"] == freeze_sha
          and review["helpers"] == HELPERS and review["inputs"] == INPUTS and review["controls"] == freeze["controls"]
          and type(review["reviewer"]) is str and review["reviewer"].strip()
          and type(review["reason"]) is str and review["reason"].strip(), "New independent native review is required")
    request = {"request_id": REQUEST_ID, "freeze_sha256": freeze_sha, "review_sha256": sha(review_raw)}
    if (output / "attempt.json").exists():
        old = read(output / "attempt.json")
        check(all(old[k] == v for k, v in request.items()), "Native attempt identity conflict")
        return replay(output)
    review_archive = output / "independent-native-review.json"
    review_already_captured = review_archive.exists()
    check(not review_archive.is_symlink(), "Native review archive cannot be redirected")
    if review_already_captured:
        check(bounded(review_archive) == review_raw, "Existing native review archive conflicts before attempt claim")
    check(snapshot(manifest) == read(output / "integrity-before.json"), "Protected VM/cases changed before native attempt")
    write(output / "attempt.json", {**request, "status": "running", "attempt": 1})
    wall, cpu = time.perf_counter(), time.process_time()
    native_calls, vm_calls, compilations = 0, 0, 0
    phase = "process_setup"
    try:
        observations = resources()
        if not review_already_captured:
            with review_archive.open("xb") as review_copy:
                review_copy.write(review_raw)
                review_copy.flush()
                os.fsync(review_copy.fileno())
        qualification, labels = {}, {}
        phase = "vm_prequalification"
        # All six exact-input VM checks finish before either native compile.
        for name, payload in data.items():
            labels[name], cells = primitive_labels(payload)
            qualification[name] = {"native_private_cell_estimate": cells, "arms": {}}
            for arm, raw in sources.items():
                vm_calls += 1
                value = vm.execute_group_program(raw, payload["labels"], limits=vm.Limits(**freeze["vm_limits"]))
                qualification[name]["arms"][arm] = {"usage": value["usage"], "output_sha256": value["output_sha256"],
                                           "split": split_check(value["group_ids"], payload)}
        write(output / "vm-prequalification.json", qualification)
        phase = "native_compilation"
        functions = {}
        for arm, raw in sources.items():
            compilations += 1
            functions[arm] = native_function(arm, raw)[0]
        summaries, correctness = {}, {}
        phase = "native_correctness_and_timing"
        with ExitStack() as stack:
            stack.enter_context(patch("sklearn.linear_model.Ridge.fit", side_effect=AssertionError("Fitting forbidden")))
            stack.enter_context(patch("sklearn.preprocessing.StandardScaler.fit", side_effect=AssertionError("Fitting forbidden")))
            with (output / "timings.jsonl").open("x") as timings:
                for name, payload in data.items():
                    correctness[name] = {}
                    expected_ids = None
                    for arm, function in functions.items():
                        native_calls += 1
                        ids = function(labels[name])
                        if arm == "baseline":
                            expected_ids = ids
                        correctness[name][arm] = split_check(ids, payload)
                        check(sha(canonical(ids)) == qualification[name]["arms"][arm]["output_sha256"], "Native/VM output differs")
                    for _ in range(5):
                        for function in functions.values():
                            native_calls += 1
                            function(labels[name])
                    durations = {arm: [] for arm in HELPERS}
                    for pair in range(100):
                        order = ("baseline", "candidate") if pair % 2 == 0 else ("candidate", "baseline")
                        for arm in order:
                            native_calls += 1
                            start = time.perf_counter_ns()
                            ids = functions[arm](labels[name])
                            elapsed = time.perf_counter_ns() - start
                            check(ids == expected_ids, "Timed native IDs drifted")
                            durations[arm].append(elapsed)
                            timings.write(canonical({"dataset": name, "pair": pair, "arm": arm,
                                                    "nanoseconds": elapsed, "output_sha256": sha(canonical(ids))}).decode() + "\n")
                    base, candidate = (statistics.median(durations[a]) for a in HELPERS)
                    summaries[name] = {"baseline_median_ns": base, "candidate_median_ns": candidate,
                                       "speedup": base / candidate if candidate else None, "median_saved_ns": base - candidate,
                                       "paired_saving_median_ns": statistics.median(a-b for a, b in zip(durations["baseline"], durations["candidate"]))}
        phase = "integrity_finalization"
        after = snapshot(manifest)
        write(output / "integrity-after.json", after)
        check(after == read(output / "integrity-before.json"), "Protected VM/cases changed")
        check(frozen(output)[1] == freeze_sha, "Native freeze changed during execution")
        check(sha(bounded(review_archive)) == request["review_sha256"], "Native review archive changed during execution")
        load_vm()
        source = summaries["concrete"]
        criteria = {"correctness": True, "integrity": True,
                    "source_latency": source["speedup"] is not None and source["speedup"] >= 1.5 and source["median_saved_ns"] >= 500000,
                    "target_no_adverse_slowdown": all(not (v["candidate_median_ns"] > v["baseline_median_ns"] * 1.1
                        and v["candidate_median_ns"] - v["baseline_median_ns"] > 50000) for n, v in summaries.items() if n != "concrete")}
        write(output / "correctness.json", correctness)
        names = ("vm-prequalification.json", "correctness.json", "timings.jsonl", "integrity-after.json", "independent-native-review.json")
        result = {"schema_version": "g4-native-confirmation-result-v1", "status": "accepted_for_future_review" if all(criteria.values()) else "rejected",
                  "request": request, "execution_mode": "exact_reviewed_native_pure_microfunctions", "criteria": criteria,
                  "timing_summary": summaries, "vm_prequalification_calls": vm_calls, "native_compilations": compilations,
                  "native_helper_calls": native_calls, "fits": 0, "product_model_calls": 0, "candidate_searches": 0,
                  "wall_seconds": time.perf_counter()-wall, "cpu_seconds": time.process_time()-cpu,
                  "resources": observations, "artifacts": {n: {"sha256": sha(bounded(output/n)), "bytes": len(bounded(output/n))} for n in names},
                  "limitation": "Single-host native helper timing only, not full adapter/CV/research benefit, OS isolation, sealed RSI or production promotion"}
        write(output / "result.json", result)
        write(output / "attempt.json", {**request, "status": "completed", "attempt": 1, "result_sha256": sha(bounded(output / "result.json"))}, replace=True)
        return result
    except BaseException as error:
        failure = {"status": "unresolved_attempt_no_retry", "type": type(error).__name__,
                   "message": str(error), "code": getattr(error, "code", None), "usage": getattr(error, "usage", None),
                   "phase": phase, "vm_prequalification_calls": vm_calls, "native_compilations_attempted": compilations,
                   "native_helper_calls": native_calls}
        try:
            after = snapshot(manifest)
            write(output / "failure-integrity-after.json", after)
            failure["protected_files_unchanged"] = after == read(output / "integrity-before.json")
        except BaseException as integrity_error:
            failure["integrity_error"] = str(integrity_error)
        write(output / "error.json", failure)
        raise
    finally:
        signal.alarm(0)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("prepare", "run", "replay"))
    parser.add_argument("--output", required=True)
    parser.add_argument("--review")
    parser.add_argument("--execution-disabled", action="store_true")
    args = parser.parse_args()
    output = Path(args.output).absolute()
    if args.command == "prepare":
        value = prepare(output)
    elif args.command == "run":
        check(args.review is not None, "Explicit independent native review path required")
        value = run(output, Path(args.review).absolute())
    else:
        check(args.execution_disabled, "Replay must explicitly disable execution")
        with patch(__name__ + ".native_function", side_effect=AssertionError("Native compilation forbidden")), patch.object(vm, "execute_group_program", side_effect=AssertionError("VM execution forbidden")):
            value = replay(output)
    print(json.dumps(value, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
