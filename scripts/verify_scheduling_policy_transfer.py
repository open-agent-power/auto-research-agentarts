"""Independent objective oracle and saved-only verifier for a frozen policy study.

Importing this module does not execute the oracle, create inputs, measure time,
read a study, or mutate a ledger. A future caller must reserve each oracle call.
"""
import ast
import base64
import binascii
from bisect import bisect_left, bisect_right
import hashlib
import json
import math
from pathlib import Path
import sqlite3
import statistics

ORIGINAL_VERIFIER_SHA256 = "ba82a2afe5e765ccf02ac12765cbfb6f2213a0b815f6d0f4f12e539176cf2f0d"
ORACLE_SOURCE_SHA256 = "ed8da57ef6eca1061e513fc328e2c5c95084ef599099ca401808fc841bd504a9"


def fenwick_optimum(jobs):
    ends=sorted({row['end'] for row in jobs});bit=[0]*(len(ends)+1)
    for job in sorted(jobs,key=lambda row:(row['end'],row['start'],row['id'])):
        cursor=bisect_right(ends,job['start']); best=0
        while cursor:
            best=max(best,bit[cursor]);cursor-=cursor&-cursor
        value=max(0,best+job['weight']);cursor=bisect_left(ends,job['end'])+1
        while cursor<len(bit):
            bit[cursor]=max(bit[cursor],value);cursor+=cursor&-cursor
    answer=0;cursor=len(ends)
    while cursor:
        answer=max(answer,bit[cursor]);cursor-=cursor&-cursor
    return answer


class SavedVerificationError(ValueError):
    """A saved receipt is incomplete, malformed, or internally inconsistent."""


def _require(condition, message):
    if not condition:
        raise SavedVerificationError(message)


def _canonical(value):
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True,
                          separators=(",", ":"), allow_nan=False).encode("utf-8")
    except (TypeError, ValueError, UnicodeError, OverflowError, RecursionError):
        raise SavedVerificationError("Non-canonical JSON value in saved evidence.") from None


def _fingerprint(value):
    return hashlib.sha256(_canonical(value)).hexdigest()


def _int(value):
    return type(value) is int


def _digest(value):
    return (type(value) is str and len(value) == 64
            and all(c in "0123456789abcdef" for c in value))


def _verify_jobs(jobs, expected_n, expected_sha256):
    """Verify captured integer rows only; never regenerate them from seed."""
    _require(type(jobs) is list and _int(expected_n) and 0 <= expected_n <= 512
             and len(jobs) == expected_n and _digest(expected_sha256),
             "Captured workload size or identity differs.")
    lookup = {}
    for row in jobs:
        _require(type(row) is list and len(row) == 4 and all(_int(x) for x in row),
                 "Each saved job must be four exact integers.")
        start, end, weight, job_id = row
        _require(-1_000_000_000 <= start < end <= 1_000_000_000
                 and -1_000_000 <= weight <= 1_000_000
                 and 0 <= job_id <= 4095 and job_id not in lookup,
                 "Invalid job bounds, duration, or duplicate identity.")
        lookup[job_id] = row
    _require(_fingerprint(jobs) == expected_sha256, "Captured job bytes differ.")
    return lookup


def _verify_saved_run(jobs, returned, method):
    """Check one stored schedule and operation counts without running a solver.

    ``jobs`` are legacy ordered [start,end,weight,id] rows; callers first verify
    their captured input identity with :func:`_verify_jobs`. The returned value
    is the stored objective and full selected IDs for cross-arm equality checks.
    """
    _require(method in ("quadratic_scan_dp", "binary_search_dp"), "Unknown fixed method.")
    _require(type(returned) is dict and set(returned) == {
        "objective", "schedule", "full_scan_comparisons", "operations"},
        "Saved kernel-result fields differ.")
    n = len(jobs)
    lookup = {row[3]: row for row in jobs}
    _require(len(lookup) == n, "Duplicate saved input ID.")
    selected = returned["schedule"]
    _require(_int(returned["objective"]) and type(selected) is list
             and all(_int(i) and i in lookup for i in selected)
             and len(selected) == len(set(selected)),
             "Saved schedule has unknown, repeated, or non-integer IDs.")
    chosen = [lookup[i] for i in selected]
    _require(all(a[1] <= b[0] for a, b in zip(chosen, chosen[1:]))
             and sum(row[2] for row in chosen) == returned["objective"],
             "Saved schedule is infeasible or its weight differs.")
    _require(selected == [row[3] for row in sorted(chosen, key=lambda row: (row[1], row[0], row[3]))],
             "Saved schedule reconstruction order differs.")
    ops = returned["operations"]
    _require(type(ops) is dict and set(ops) == {
        "bisect_calls", "bisect_internal_comparisons", "dp_steps",
        "full_scan_comparisons", "reconstruction_steps"},
        "Saved operation-count fields differ.")
    expected_scan = n * (n - 1) // 2 if method == "quadratic_scan_dp" else 0
    _require(_int(returned["full_scan_comparisons"])
             and returned["full_scan_comparisons"] == expected_scan
             and _int(ops["full_scan_comparisons"]) and ops["full_scan_comparisons"] == expected_scan
             and _int(ops["dp_steps"]) and ops["dp_steps"] == n
             and _int(ops["bisect_calls"]) and ops["bisect_calls"] == (n if method == "binary_search_dp" else 0)
             and ops["bisect_internal_comparisons"] is None
             and _int(ops["reconstruction_steps"]), "Saved operation counts differ.")
    # Reconstruct the already-saved selected path, not an optimal schedule.
    ordered = sorted(jobs, key=lambda row: (row[1], row[0], row[3]))
    ends = [row[1] for row in ordered]
    chosen_ids = set(selected)
    position = n
    steps = 0
    while position:
        steps += 1
        row = ordered[position - 1]
        position = bisect_right(ends, row[0], 0, position - 1) if row[3] in chosen_ids else position - 1
    _require(ops["reconstruction_steps"] == steps, "Saved reconstruction path count differs.")
    return returned["objective"], selected


def _saved_elapsed(result):
    """Return positive saved nanoseconds, or None for an explicit invalid clock.

    Preserve the original marker in the source receipt. Invalid measurements
    make their comparison uninterpretable; they are never silently discarded.
    """
    _require(type(result) is dict and set(result) == {
        "returned", "elapsed_ns", "timing_status", "elapsed_raw"}, "Timing receipt fields differ.")
    status, raw, elapsed = result["timing_status"], result["elapsed_raw"], result["elapsed_ns"]
    if status == "ok":
        _require(_int(raw) and 0 < raw <= 2**63 - 1 and _int(elapsed) and elapsed == raw,
                 "Positive timing receipt is inconsistent.")
        return elapsed
    _require(elapsed is None, "Invalid timing must not masquerade as a duration.")
    if status == "zero":
        _require(_int(raw) and raw == 0, "Zero timing marker differs.")
    elif status == "negative":
        _require(_int(raw) and -(2**63) <= raw < 0, "Negative timing marker differs.")
    elif status == "nonfinite":
        _require(type(raw) is str and raw in ("NaN", "Infinity", "-Infinity"),
                 "Nonfinite timing marker differs.")
    else:
        raise SavedVerificationError("Unknown timing status.")
    return None


STUDY_ID = "g5-scheduling-threshold-transfer-v1"
SIZES = (16, 24, 31, 32, 33, 34, 64, 128, 512)
SEEDS = (601, 602, 603)
ARMS = ("fixed_binary", "fixed_scan", "threshold32")
PERMUTATIONS = (("fixed_binary", "fixed_scan", "threshold32"),
                ("fixed_binary", "threshold32", "fixed_scan"),
                ("fixed_scan", "fixed_binary", "threshold32"),
                ("fixed_scan", "threshold32", "fixed_binary"),
                ("threshold32", "fixed_binary", "fixed_scan"),
                ("threshold32", "fixed_scan", "fixed_binary"))
EXPECTED_LIMITS = {"generate": 29, "warmup": 162, "timed": 972, "correctness": 6,
                   "oracle": 29, "bruteforce": 2, "audit": 1, "primary": 1,
                   "kernel_total": 1140, "scan_comparisons": 6080234,
                   "exhaustive_subsets": 4352}


def _verify_event_chain(claim, claim_sha256, events):
    """Verify each immutable write-ahead reservation and its saved receipt.

    This checks mechanical consistency of saved records, not a signature or an
    OS boundary against a party able to rewrite all files under the same UID.
    """
    _require(type(claim) is dict and _digest(claim_sha256)
             and _fingerprint(claim) == claim_sha256 and type(events) is list,
             "Claim or event collection differs.")
    previous = claim_sha256
    operations = []
    seen = set()
    pending = None
    boot_id = None
    previous_clock = None
    fields = {"ordinal", "previous_sha256", "event", "op_id", "operation", "spec",
              "reservation_sha256", "result", "result_sha256", "boot_id", "monotonic_ns"}
    for ordinal, item in enumerate(events, 1):
        _require(type(item) is dict and set(item) == {"event", "sha256"}
                 and type(item["event"]) is dict and _digest(item["sha256"]), "Malformed event wrapper.")
        e = item["event"]
        _require(set(e) == fields and _int(e["ordinal"]) and e["ordinal"] == ordinal
                 and e["previous_sha256"] == previous and _fingerprint(e) == item["sha256"]
                 and type(e["op_id"]) is str and type(e["operation"]) is str and type(e["spec"]) is dict,
                 "Event sequence, identity or digest differs.")
        _require(type(e["boot_id"]) is str and 0 < len(e["boot_id"]) <= 128
                 and _int(e["monotonic_ns"]) and e["monotonic_ns"] >= 0
                 and (boot_id is None or e["boot_id"] == boot_id)
                 and (previous_clock is None or e["monotonic_ns"] >= previous_clock),
                 "Saved event boot identity or monotonic ordering differs.")
        boot_id, previous_clock = e["boot_id"], e["monotonic_ns"]
        if e["event"] == "reserved":
            _require(pending is None and e["op_id"] not in seen
                     and e["reservation_sha256"] is None and e["result"] is None
                     and e["result_sha256"] is None, "Duplicate or overlapping reservation.")
            pending = (e, item["sha256"])
            seen.add(e["op_id"])
        else:
            _require(e["event"] == "completed" and pending is not None,
                     "Incomplete, failed or unreserved operation cannot form a completed audit.")
            reservation, reservation_sha256 = pending
            _require(e["op_id"] == reservation["op_id"]
                     and e["operation"] == reservation["operation"]
                     and _canonical(e["spec"]) == _canonical(reservation["spec"])
                     and e["reservation_sha256"] == reservation_sha256
                     and _digest(e["result_sha256"]) and _fingerprint(e["result"]) == e["result_sha256"],
                     "Completion does not bind the exact reservation and result.")
            operations.append({"op_id": e["op_id"], "operation": e["operation"],
                               "spec": e["spec"], "result": e["result"],
                               "reservation_sha256": reservation_sha256,
                               "completion_sha256": item["sha256"]})
            pending = None
        previous = item["sha256"]
    _require(pending is None, "An operation remains unknown; do not retry it.")
    return operations


def _expected_cases():
    """Frozen case descriptors only; this does not generate any jobs."""
    cases = [("correctness", n, 601) for n in (8, 12)]
    cases += [("performance", n, seed) for n in SIZES for seed in SEEDS]
    return [(f"{'correct' if kind == 'correctness' else 'perf'}-n{n}-seed{seed}", kind, n, seed)
            for kind, n, seed in cases]


def _verify_manifest(manifest):
    _require(type(manifest) is dict and set(manifest) == {"schema_version", "study_id", "cases",
                 "generation_after_ordinal", "generation_previous_event_sha256"}
             and manifest["schema_version"] == "scheduling-threshold-inputs-v1"
             and manifest["study_id"] == STUDY_ID and type(manifest["cases"]) is list
             and type(manifest["generation_after_ordinal"]) is int
             and manifest["generation_after_ordinal"] == 58
             and _digest(manifest["generation_previous_event_sha256"]),
             "Invalid fixed study input manifest.")
    expected = _expected_cases()
    _require(len(manifest["cases"]) == len(expected), "Input manifest lacks complete case coverage.")
    result = {}
    for case, descriptor in zip(manifest["cases"], expected):
        _require(type(case) is dict and set(case) == {"case_id", "kind", "n", "seed", "jobs", "jobs_sha256"}
                 and (case["case_id"], case["kind"], case["n"], case["seed"]) == descriptor
                 and _int(case["n"]) and _int(case["seed"]), "Case order or frozen parameters differ.")
        _verify_jobs(case["jobs"], case["n"], case["jobs_sha256"])
        n = case["n"]
        for index, row in enumerate(case["jobs"]):
            start, end, weight, job_id = row
            _require(job_id == index and 0 <= start <= 10 * n and 1 <= end - start <= max(2, n // 4)
                     and 1 <= weight <= 100, "Saved job violates the frozen generator's allowed structure.")
        result[case["case_id"]] = case
    _require(sum(c["n"] for c in result.values()) == 2642, "Complete saved job count differs.")
    return result


def _fixed_method(arm, n):
    _require(arm in ARMS, "Unknown frozen strategy arm.")
    return "quadratic_scan_dp" if arm == "fixed_scan" or (arm == "threshold32" and n <= 32) else "binary_search_dp"


def _expected_operations(cases):
    """Yield the complete fixed call sequence/specification, without executing it."""
    for case_id, kind, n, seed in _expected_cases():
        yield "gen-" + case_id, "generate", {"case_id": case_id, "kind": kind, "n": n, "seed": seed}
    for case_id, kind, n, seed in _expected_cases():
        sha = cases[case_id]["jobs_sha256"]
        fixed = {"case_id": case_id, "n": n, "seed": seed, "jobs_sha256": sha}
        yield "oracle-" + case_id, "oracle", fixed
        if kind == "correctness":
            for position, arm in enumerate(ARMS):
                spec = {**fixed, "phase": "correctness", "position": position, "arm": arm}
                yield f"correct-{case_id}-{position:02d}", "correctness", spec
            yield "brute-" + case_id, "bruteforce", fixed
            continue
        warm = (*ARMS, *tuple(reversed(ARMS)))
        for position, arm in enumerate(warm):
            spec = {**fixed, "phase": "warmup", "position": position, "arm": arm}
            yield f"warm-{case_id}-{position:02d}", "warmup", spec
        for block in range(2):
            for perm_index, permutation in enumerate(PERMUTATIONS):
                for within, arm in enumerate(permutation):
                    position = block * 18 + perm_index * 3 + within
                    spec = {**fixed, "phase": "timed", "position": position, "arm": arm,
                            "block": block, "permutation_index": perm_index}
                    yield f"timed-{case_id}-{position:02d}", "timed", spec


def _saved_exhaustive_charge(spec):
    """Account for a saved reservation, without enumerating subsets."""
    _require(type(spec) is dict and _int(spec.get("n")) and 0 <= spec["n"] <= 12,
             "Saved exhaustive reservation has an invalid size.")
    return 1 << spec["n"]


def _verify_completed_operations(cases, operations):
    """Check fixed coverage and all stored outcomes, without invoking an oracle."""
    expected = list(_expected_operations(cases))
    _require(len(operations) == len(expected) == 1200, "Incomplete fixed-operation coverage.")
    observations = {case_id: {"oracle": None, "bruteforce": None, "reference": None,
                              "timed": {arm: [] for arm in ARMS}, "invalid_warmups": []}
                    for case_id in cases}
    counts = {key: 0 for key in ("generate", "warmup", "timed", "correctness", "oracle", "bruteforce", "audit")}
    scan_total = 0
    exhaustive_total = 0
    for saved, (op_id, kind, spec) in zip(operations, expected):
        _require(saved["op_id"] == op_id and saved["operation"] == kind
                 and _canonical(saved["spec"]) == _canonical(spec),
                 "A saved operation does not match its fixed position and specification.")
        counts[kind] += 1
        result = saved["result"]
        case = cases[spec["case_id"]]
        entry = observations[spec["case_id"]]
        if kind == "generate":
            _require(type(result) is dict and set(result) == {"jobs"}
                     and result["jobs"] == case["jobs"] and _fingerprint(result["jobs"]) == case["jobs_sha256"],
                     "Generation receipt differs from the reviewed complete input.")
        elif kind in ("oracle", "bruteforce"):
            _require(type(result) is dict and set(result) == {"objective"} and _int(result["objective"]),
                     "Malformed saved independent objective.")
            entry[kind] = result["objective"]
            if kind == "bruteforce":
                exhaustive_total += _saved_exhaustive_charge(saved["spec"])
        else:
            if kind == "correctness":
                _require(type(result) is dict and set(result) == {"returned"}, "Malformed correctness receipt.")
                elapsed = None
            else:
                elapsed = _saved_elapsed(result)
            method = _fixed_method(spec["arm"], spec["n"])
            pair = _verify_saved_run(case["jobs"], result["returned"], method)
            _require(entry["oracle"] is not None and pair[0] == entry["oracle"],
                     "A saved run differs from its reserved, completed independent objective.")
            if entry["reference"] is None:
                entry["reference"] = pair
            _require(pair == entry["reference"], "Saved full schedules/objectives differ across arms or runs.")
            scan_total += result["returned"]["full_scan_comparisons"]
            if kind == "timed":
                entry["timed"][spec["arm"]].append(elapsed)
            elif kind == "warmup" and elapsed is None:
                entry["invalid_warmups"].append(op_id)
    _require(counts == {"generate": 29, "warmup": 162, "timed": 972, "correctness": 6,
                        "oracle": 29, "bruteforce": 2, "audit": 0}
             and scan_total == 6080234 and exhaustive_total == 4352,
             "Saved operation counts, comparison charges or exhaustive charges differ.")
    for case_id, case in cases.items():
        entry = observations[case_id]
        _require(entry["reference"] is not None and entry["oracle"] is not None, "Missing complete case result.")
        if case["kind"] == "correctness":
            _require(entry["bruteforce"] == entry["oracle"], "Saved exhaustive and independent objectives differ.")
        else:
            _require(entry["bruteforce"] is None and all(len(entry["timed"][a]) == 12 for a in ARMS),
                     "Stored timing repetitions or oracle coverage differ.")
    return observations, {**counts, "kernel_total": 1140, "scan_comparisons": scan_total,
                          "exhaustive_subsets": exhaustive_total}


def _case_timing_medians(times, invalid_warmups):
    """A clock error in any run makes this case's timing ratio uninterpretable."""
    medians = {arm: (statistics.median(times[arm]) if all(x is not None for x in times[arm]) else None)
               for arm in ARMS}
    a, b = medians["threshold32"], medians["fixed_binary"]
    valid = not invalid_warmups and all(v is not None for v in medians.values())
    ratio = a / b if valid and b > 0 else None
    _require(ratio is None or math.isfinite(ratio), "Saved timing ratio is not finite.")
    return medians, ratio


def _summarize_saved(cases, observations):
    """Calculate only the predeclared arithmetic over all saved timing values."""
    rows = []
    for case_id, _, n, seed in _expected_cases():
        case = cases[case_id]
        if case["kind"] != "performance":
            continue
        times = observations[case_id]["timed"]
        medians, ratio = _case_timing_medians(times, observations[case_id]["invalid_warmups"])
        outcome = ("uninterpretable" if ratio is None else "faster" if ratio < 1
                   else "slower" if ratio > 1 else "tie")
        rows.append({"case_id": case_id, "n": n, "seed": seed, "median_ns": medians,
                     "policy_over_binary": ratio, "outcome": outcome,
                     "invalid_warmups": observations[case_id]["invalid_warmups"]})
    small = [r for r in rows if r["n"] <= 32]
    _require(len(rows) == 27 and len(small) == 12, "Primary case coverage differs.")
    ratios = [r["policy_over_binary"] for r in small]
    primary = statistics.median(ratios) if all(v is not None for v in ratios) else None
    _require(primary is None or math.isfinite(primary), "Primary timing ratio is not finite.")
    return {"primary_case_count": 12, "primary_policy_over_binary": primary,
            "primary_timing_interpretable": primary is not None,
            "performance_cases": rows,
            "scientific_validation": False,
            "scope": "saved timing arithmetic; no solver rerun or generalization"}


_SOURCE_FILES = (
    "src/autoresearch/contracts.py",
    "src/autoresearch/bounded_study_ledger.py",
    "src/autoresearch/scheduling_threshold_policy.py",
    "src/autoresearch/scheduling_kernel.py",
    "scripts/run_scheduling_policy_transfer.py",
    "scripts/verify_scheduling_policy_transfer.py",
    "docs/execution/g5-local/scheduling-threshold-transfer-protocol.json",
)
_PROTOCOL = _SOURCE_FILES[-1]
_EXPECTED_BUDGET = {"generation": 29, "kernel_warmup": 162, "kernel_timed": 972,
                    "kernel_correctness": 6, "kernel_total": 1140, "fenwick": 29,
                    "brute": 2, "exhaustive_subsets": 4352, "scan_comparisons": 6080234,
                    "primary_attempts": 1, "saved_audit_attempts": 1, "maximum_elapsed_seconds": 120,
                    "research_concurrency": 1, "estimator_fits": 0, "model_sends": 0,
                    "external_API": 0, "source_extraction": 0}
_REVIEW_FIELDS = {"schema_version", "status", "reviewer", "study_id", "request_id", "protocol_sha256",
                  "code_commit", "output_root", "budget_sha256", "source_fingerprints", "runtime",
                  "allowed_phase", "limitations"}
_CLAIM_BINDING_FIELDS = {"study_id", "output_root", "request_id", "protocol_sha256", "code_commit",
                         "setup_review_sha256", "budget_sha256", "source_fingerprints", "runtime"}
_OUTPUT_ROOT = "/workspace/auto-research-agentarts/runs/g5-scheduling-threshold-transfer-20261114-01"


def _verify_runtime(runtime):
    _require(type(runtime) is dict and set(runtime) == {
        "python_version", "python_executable", "python_implementation", "dependencies", "native_code_identity",
        "boot_id", "perf_counter", "gc_enabled", "cpu_affinity", "thread_environment"}, "Runtime metadata differs.")
    _require(all(type(runtime[k]) is str and bool(runtime[k].strip())
                 for k in ("python_version", "python_executable", "python_implementation"))
             and runtime["python_executable"].startswith("/") and _digest(runtime["native_code_identity"])
             and type(runtime["boot_id"]) is str and len(runtime["boot_id"]) == 36
             and all(c in "0123456789abcdef-" for c in runtime["boot_id"])
             and type(runtime["gc_enabled"]) is bool, "Runtime identity differs.")
    dependencies, affinity, threads, timer = (runtime[k] for k in
                                               ("dependencies", "cpu_affinity", "thread_environment", "perf_counter"))
    _require(type(dependencies) is dict and set(dependencies) == {"numpy", "scipy", "scikit-learn"}
             and all(type(v) is str and bool(v.strip()) for v in dependencies.values())
             and type(affinity) is list and bool(affinity) and all(_int(x) and x >= 0 for x in affinity)
             and affinity == sorted(set(affinity))
             and type(threads) is dict and set(threads) == {"OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS",
                                                          "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"}
             and all(v == "1" for v in threads.values()), "Dependencies, CPU affinity or thread settings differ.")
    _require(type(timer) is dict and set(timer) == {"implementation", "monotonic", "adjustable", "resolution"}
             and type(timer["implementation"]) is str and bool(timer["implementation"])
             and timer["monotonic"] is True and timer["adjustable"] is False
             and type(timer["resolution"]) in (int, float) and math.isfinite(timer["resolution"])
             and timer["resolution"] > 0, "Recorded timer metadata differs.")


def _strict_json(raw):
    """Reject duplicate keys and all nonfinite numbers at any nesting depth."""
    def pairs(items):
        obj = {}
        for key, value in items:
            if key in obj:
                raise SavedVerificationError("Duplicate stored JSON key.")
            obj[key] = value
        return obj
    def nonfinite(_):
        raise SavedVerificationError("Stored JSON has a nonfinite value.")
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=pairs, parse_constant=nonfinite)
        _canonical(value)  # Also rejects a finite-looking exponent that overflows to infinity.
        return value
    except (ValueError, UnicodeError, RecursionError):
        raise SavedVerificationError("Malformed stored JSON bytes.") from None


def _review_document(wrapper):
    """Strictly decode the exact, byte-hashed saved review without network or execution."""
    _require(type(wrapper) is dict and set(wrapper) == {"raw_base64", "raw_sha256"}
             and type(wrapper["raw_base64"]) is str and _digest(wrapper["raw_sha256"]),
             "Review byte wrapper differs.")
    try:
        raw = base64.b64decode(wrapper["raw_base64"], validate=True)
        _require(0 < len(raw) <= 65536 and base64.b64encode(raw).decode("ascii") == wrapper["raw_base64"]
                 and hashlib.sha256(raw).hexdigest() == wrapper["raw_sha256"], "Review raw bytes differ.")
        value = _strict_json(raw)
    except (binascii.Error, ValueError, UnicodeError, RecursionError):
        raise SavedVerificationError("Malformed stored review bytes.") from None
    _require(type(value) is dict, "Review must be an object.")
    return value


def _verify_original_source(protocol):
    """Check only protected saved source identity and the original read-only ledger."""
    root = Path("/workspace/auto-research-agentarts")
    protected = protocol.get("protected")
    manifest_path = root / "runs/sprint-014-setup-20261114/protected-before.json"
    paths_path = root / "runs/sprint-014-setup-20261114/old-path-sets-before.json"
    _require(type(protected) is dict and protected.get("manifest") == str(manifest_path)
             and protected.get("old_paths") == str(paths_path)
             and _digest(protected.get("manifest_sha256")) and _digest(protected.get("old_paths_sha256"))
             and protected.get("old_case_and_claims_immutable") is True,
             "Protected original-source manifest identity differs.")
    try:
        manifest_raw, paths_raw = manifest_path.read_bytes(), paths_path.read_bytes()
        _require(hashlib.sha256(manifest_raw).hexdigest() == protected["manifest_sha256"]
                 and hashlib.sha256(paths_raw).hexdigest() == protected["old_paths_sha256"],
                 "Protected original-source index bytes differ.")
        manifest = _strict_json(manifest_raw)
        paths = _strict_json(paths_raw)
        _require(type(manifest) is dict and type(paths) is dict
                 and type(protected.get("file_count")) is int and len(manifest) == protected["file_count"],
                 "Protected file index is incomplete.")
        project_root = root / ("runs/g5-native-cases-20261113-01/scheduling/manager/projects/"
                               "e2e6a30f9183cdeb834ea4dc5380a66f4e1a6d1e03a61f800d209ea22d4af659")
        db = project_root / "project.sqlite"
        artifact = project_root / "artifacts/action-60d069e0125cdd173de796b10ab8f17f.json"
        source = project_root / "source.json"
        old_claim = root / ".agent/autonomy/studies/g5-arguana-source-arm-transfer-v1.json"
        expected = {
            db: (110592, "e2a5509f30dd3ff61d14363061d667d8335998b4b4d855bbbfe2a6ded5caa9e1"),
            artifact: (1100725, "97a931f22681f50b5887e01b6e82a551da35516c8d4d3e2f0eead1a7c5748482"),
            source: (1338429, "c801e08c980caa8f56be6865eef149c98e3cad1c486b0abd39c37695611dcc3e"),
            old_claim: (551, "f2f0bf94d3181cb307f6de870c66853d03e2661249838cbeadd46a0314a5bb94"),
        }
        raw = {}
        for path, (size, digest) in expected.items():
            value = path.read_bytes()
            _require(len(value) == size and hashlib.sha256(value).hexdigest() == digest
                     and _canonical(manifest.get(str(path))) == _canonical({"bytes": size, "sha256": digest}),
                     "Original source project bytes or protected entry differ.")
            raw[path] = value
        con = sqlite3.connect(db.as_uri() + "?mode=ro", uri=True)
        try:
            project_row = con.execute("SELECT record FROM project").fetchone()
            action_rows = con.execute("SELECT record FROM actions ORDER BY rowid").fetchall()
        finally:
            con.close()
        _require(project_row is not None and len(action_rows) == 2, "Original source ledger coverage differs.")
        project = _strict_json(project_row[0].encode("utf-8"))
        actions = [_strict_json(row[0].encode("utf-8")) for row in action_rows]
        matches = [a for a in actions if a.get("id") == "action-60d069e0125cdd173de796b10ab8f17f"]
        _require(len(matches) == 1 and all(a.get("status") == "completed" for a in actions),
                 "Original source actions or reservations differ.")
        action = matches[0]
        envelope = _strict_json(raw[artifact])
        origin_sha = "08ebf6433efb414ff139197036f5fa419ffe9e0f11037954f537d5a80e8b678d"
        producer = "3945ed0f5ec85b0ce42af0bb9ac0d0c27034bf932dac27fee9f7008ec2d3707e"
        result_sha = "4eeda3def5e6002a39ed20fcd5208b086cdd78202c646bca1014c5ce427c6490"
        _require(project.get("id") == "project-148dac5d531144008498449cb16a54ea"
                 and type(project.get("state_version")) is int and project["state_version"] == 13
                 and project.get("research_status") == "waiting" and project.get("code_identity") == producer
                 and project.get("source_snapshot_sha256") == origin_sha
                 and project.get("registration", {}).get("source_sha256") == expected[source][1]
                 and project.get("budget", {}).get("local_tool_call_limit") == 2
                 and project.get("budget", {}).get("model_requests_allowed") == 0
                 and action.get("project_id") == project["id"] and action.get("code_identity") == producer
                 and action.get("command") == "research.weighted-interval-fixed-pair"
                 and action.get("source_snapshot_sha256") == origin_sha and action.get("result_sha256") == result_sha
                 and action.get("method_instance", {}).get("evaluation_ref") == "weighted-interval-fixed-pair-v1"
                 and action.get("method_instance", {}).get("scope") == project.get("source_scope"),
                 "Original project, action, producer, or budget identity differs.")
        _require(type(envelope) is dict and set(envelope) == {
            "action_id", "code_identity", "request_sha256", "sha256", "source_snapshot_sha256", "tool_result"}
            and envelope["action_id"] == action["id"] and envelope["code_identity"] == producer
            and envelope["request_sha256"] == action["request_sha256"]
            and envelope["source_snapshot_sha256"] == origin_sha and envelope["sha256"] == result_sha
            and _fingerprint({k: v for k, v in envelope.items() if k != "sha256"}) == result_sha,
            "Original saved action envelope differs.")
    except (OSError, sqlite3.Error):
        raise SavedVerificationError("Protected original source cannot be read safely.") from None


def _frozen_protocol_and_sources(source_fingerprints):
    """Bind the seven exact local source files, never a supplied filesystem path."""
    _require(type(source_fingerprints) is dict and set(source_fingerprints) == set(_SOURCE_FILES)
             and all(_digest(v) for v in source_fingerprints.values()), "Frozen source manifest differs.")
    root = Path(__file__).resolve().parent.parent
    contents = {}
    try:
        for relative in _SOURCE_FILES:
            path = root / relative
            _require(path.is_file() and not path.is_symlink() and path.stat().st_size <= 5 * 1024 * 1024,
                     "A fixed source file is missing, redirected or oversized.")
            raw = path.read_bytes()
            _require(hashlib.sha256(raw).hexdigest() == source_fingerprints[relative],
                     "A frozen source file changed.")
            if relative in (_PROTOCOL, "scripts/verify_scheduling_policy_transfer.py"):
                contents[relative] = raw
    except OSError:
        raise SavedVerificationError("A frozen source file cannot be read.") from None
    _require(source_fingerprints["src/autoresearch/scheduling_kernel.py"]
             == "3a335e102279ce9e6a7a8861a3f203670fccfbfb3ea3d2941f8b9406ea92e401",
             "Original fixed scheduling kernel differs.")
    original = Path("/workspace/auto-research-agentarts/work/native-cpu-source-8e8a206/scripts/verify_native_cpu_cases.py")
    try:
        original_raw = original.read_bytes()
        _require(hashlib.sha256(original_raw).hexdigest() == ORIGINAL_VERIFIER_SHA256,
                 "Original independent-verifier file differs.")
        def oracle_segment(raw):
            text = raw.decode("utf-8")
            nodes = [node for node in ast.parse(text).body
                     if isinstance(node, ast.FunctionDef) and node.name == "fenwick_optimum"]
            _require(len(nodes) == 1, "Exactly one original oracle function is required.")
            return ast.get_source_segment(text, nodes[0]).encode("utf-8")
        saved_oracle = oracle_segment(contents["scripts/verify_scheduling_policy_transfer.py"])
        original_oracle = oracle_segment(original_raw)
        _require(len(saved_oracle) == 620 and saved_oracle == original_oracle
                 and hashlib.sha256(saved_oracle).hexdigest() == ORACLE_SOURCE_SHA256,
                 "Independent oracle source is not the exact frozen function.")
    except (OSError, SyntaxError, UnicodeError):
        raise SavedVerificationError("Original or current independent-oracle source cannot be read.") from None
    protocol = _strict_json(contents[_PROTOCOL])
    _require(type(protocol) is dict and protocol.get("schema_version") == "scheduling-policy-transfer-protocol-v1"
             and protocol.get("study_id") == STUDY_ID and protocol.get("source_files") == list(_SOURCE_FILES)
             and _canonical(protocol.get("budget")) == _canonical(_EXPECTED_BUDGET),
             "Frozen protocol or its operation budget differs.")
    source = protocol.get("source_basis", {})
    _require(type(source) is dict
             and source.get("old_source_commit") == "8e8a206ed0b71479a6e774e36ed91fdb06e21c22"
             and source.get("old_source_project_id") == "project-148dac5d531144008498449cb16a54ea"
             and source.get("old_source_primary_action") == "action-60d069e0125cdd173de796b10ab8f17f"
             and source.get("old_source_producer") == "3945ed0f5ec85b0ce42af0bb9ac0d0c27034bf932dac27fee9f7008ec2d3707e"
             and source.get("old_result_sha256") == "4eeda3def5e6002a39ed20fcd5208b086cdd78202c646bca1014c5ce427c6490"
             and type(source.get("source_informed_rule_choices")) is int
             and source["source_informed_rule_choices"] == 1, "Original source observation differs.")
    policy = protocol.get("policy", {})
    _require(type(policy) is dict and policy.get("id") == "source-small-n-scan-v1"
             and type(policy.get("threshold")) is int and policy["threshold"] == 32
             and policy.get("if_n_le_threshold") == "quadratic_scan_dp"
             and policy.get("otherwise") == "binary_search_dp"
             and policy.get("allowed_arm_ids") == list(ARMS)
             and policy.get("controls") == {"fixed_binary": "binary_search_dp", "fixed_scan": "quadratic_scan_dp"}
             and policy.get("candidate_changes_after_target_input_or_scores") is False,
             "Fixed strategy, threshold or control arms differ.")
    protocol_cases = [{"id": case_id, "phase": kind, "n": n, "seed": seed}
                      for case_id, kind, n, seed in _expected_cases()]
    _require(_canonical(protocol.get("cases_in_generation_and_primary_order")) == _canonical(protocol_cases),
             "Fixed case roster differs from the reviewed protocol.")
    measurement = protocol.get("measurement", {})
    _require(type(measurement) is dict and type(measurement.get("performance_cases")) is int
             and measurement["performance_cases"] == 27 and type(measurement.get("correctness_cases")) is int
             and measurement["correctness_cases"] == 2
             and measurement.get("warmup_arm_orders") == [list(ARMS), list(reversed(ARMS))]
             and measurement.get("timed_arm_permutations_per_block") == [list(x) for x in PERMUTATIONS]
             and type(measurement.get("identical_ordered_blocks")) is int and measurement["identical_ordered_blocks"] == 2
             and type(measurement.get("timed_repetitions_each_arm_case")) is int
             and measurement["timed_repetitions_each_arm_case"] == 12 and measurement.get("clock") == "time.perf_counter_ns",
             "Fixed timing order or coverage differs.")
    correctness = protocol.get("correctness", {})
    _require(type(correctness) is dict and correctness.get("old_oracle_file_sha256") == ORIGINAL_VERIFIER_SHA256
             and correctness.get("oracle_function_sha256") == ORACLE_SOURCE_SHA256
             and type(correctness.get("oracle_function_source_bytes")) is int
             and correctness["oracle_function_source_bytes"] == 620
             and correctness.get("old_kernel_sha256") == source_fingerprints["src/autoresearch/scheduling_kernel.py"]
             and _canonical(correctness.get("brute_small_cases_only")) == _canonical([8, 12]),
             "Frozen independent oracle identity differs.")
    return protocol


def _verify_reviews(reviews, binding, claim_sha256, manifest_sha256):
    _require(type(reviews) is dict and set(reviews) == {"setup", "input"}, "Both original reviews are required.")
    setup = _review_document(reviews["setup"])
    input_review = _review_document(reviews["input"])
    for review, schema, request, phase, additional in (
        (setup, "scheduling-policy-setup-review-v1", "prepare-g5-scheduling-threshold-transfer-v1", "generate_only", set()),
        (input_review, "scheduling-policy-input-review-v1", "primary-g5-scheduling-threshold-transfer-v1",
         "primary_and_saved_audit", {"inputs_sha256", "shared_claim_sha256"}),
    ):
        _require(set(review) == _REVIEW_FIELDS | additional and review["schema_version"] == schema
                 and review["status"] == "approved" and review["study_id"] == STUDY_ID
                 and review["request_id"] == request and review["allowed_phase"] == phase
                 and type(review["reviewer"]) is str and 0 < len(review["reviewer"].strip()) <= 200
                 and type(review["limitations"]) is list and 1 <= len(review["limitations"]) <= 20
                 and all(type(x) is str and 0 < len(x.strip()) <= 4000 for x in review["limitations"]),
                 "A stored review does not approve the exact phase and study.")
        for key in ("protocol_sha256", "code_commit", "output_root", "budget_sha256", "source_fingerprints", "runtime"):
            _require(_canonical(review[key]) == _canonical(binding[key]), "Review and claim binding differ.")
    _require(reviews["setup"]["raw_sha256"] == binding["setup_review_sha256"]
             and input_review["shared_claim_sha256"] == claim_sha256
             and input_review["inputs_sha256"] == manifest_sha256,
             "Review does not bind the exact claim and complete input manifest.")
    return setup, input_review


def _verify_saved_phases(phases, claim_sha256, anchor, manifest_sha256, input_review_sha256, completion):
    """Check recorded same-boot deadline arithmetic without consulting a clock."""
    _require(type(phases) is dict and set(phases) == {
        "generation", "generation_result", "input_review", "primary", "primary_result"}
        and phases["primary_result"] is None and type(completion) is dict
        and set(completion) == {"boot_id", "operations_finished_monotonic_ns"},
        "The primary bundle must preserve all phases before its own result receipt.")
    generation, generated, review, primary = (phases[k] for k in
                                               ("generation", "generation_result", "input_review", "primary"))
    _require(type(generation) is dict and set(generation) == {
        "schema_version", "study_id", "boot_id", "started_monotonic_ns", "deadline_monotonic_ns",
        "after_ordinal", "previous_event_sha256"}
        and generation["schema_version"] == "bounded-study-generation-v1"
        and generation["study_id"] == STUDY_ID and type(generation["boot_id"]) is str
        and 0 < len(generation["boot_id"]) <= 128
        and _int(generation["started_monotonic_ns"]) and generation["started_monotonic_ns"] >= 0
        and _int(generation["deadline_monotonic_ns"])
        and generation["deadline_monotonic_ns"] == generation["started_monotonic_ns"] + 120_000_000_000
        and _int(generation["after_ordinal"]) and generation["after_ordinal"] == 0
        and generation["previous_event_sha256"] == claim_sha256, "Generation start or deadline differs.")
    _require(type(generated) is dict and set(generated) == {
        "schema_version", "manifest_sha256", "boot_id", "finished_monotonic_ns", "elapsed_ns",
        "after_ordinal", "previous_event_sha256"}
        and generated["schema_version"] == "bounded-study-generation-result-v1"
        and generated["manifest_sha256"] == manifest_sha256 and generated["boot_id"] == generation["boot_id"]
        and _int(generated["finished_monotonic_ns"]) and _int(generated["elapsed_ns"])
        and generated["elapsed_ns"] == generated["finished_monotonic_ns"] - generation["started_monotonic_ns"]
        and 0 <= generated["elapsed_ns"] < 120_000_000_000
        and generated["finished_monotonic_ns"] <= generation["deadline_monotonic_ns"]
        and _int(generated["after_ordinal"]) and generated["after_ordinal"] == 58
        and generated["previous_event_sha256"] == anchor, "Generation finish, budget or event anchor differs.")
    expected_review = {"schema_version": "bounded-study-input-review-v1", "manifest_sha256": manifest_sha256,
                       "review_sha256": input_review_sha256, "after_ordinal": 58, "previous_event_sha256": anchor}
    _require(_canonical(review) == _canonical(expected_review), "Input review does not bind the complete input.")
    _require(type(primary) is dict and set(primary) == {
        "schema_version", "study_id", "input_review_sha256", "boot_id", "started_monotonic_ns",
        "deadline_monotonic_ns", "after_ordinal", "previous_event_sha256"}
        and primary["schema_version"] == "bounded-study-primary-v1" and primary["study_id"] == STUDY_ID
        and primary["input_review_sha256"] == _fingerprint(expected_review)
        and primary["boot_id"] == generation["boot_id"]
        and _int(primary["started_monotonic_ns"]) and primary["started_monotonic_ns"] >= generated["finished_monotonic_ns"]
        and _int(primary["deadline_monotonic_ns"])
        and primary["deadline_monotonic_ns"] == primary["started_monotonic_ns"] + 120_000_000_000 - generated["elapsed_ns"]
        and _int(primary["after_ordinal"]) and primary["after_ordinal"] == 58
        and primary["previous_event_sha256"] == anchor, "Primary start or remaining deadline differs.")
    _require(completion["boot_id"] == primary["boot_id"] and _int(completion["operations_finished_monotonic_ns"])
             and primary["started_monotonic_ns"] <= completion["operations_finished_monotonic_ns"]
             < primary["deadline_monotonic_ns"], "Saved primary operation finish exceeds the recorded deadline.")


def _verify_event_clock_bounds(events, phases, completion):
    """Check saved event clocks against their phase boundaries, without a clock read."""
    _require(type(events) is list and len(events) > 58, "Both event phases are required.")
    generation, generated, primary = (phases[k] for k in ("generation", "generation_result", "primary"))
    boot = generation["boot_id"]
    for index, item in enumerate(events):
        event = item["event"]
        lower, upper = ((generation["started_monotonic_ns"], generated["finished_monotonic_ns"])
                        if index < 58 else
                        (primary["started_monotonic_ns"], completion["operations_finished_monotonic_ns"]))
        _require(event["boot_id"] == boot and _int(event["monotonic_ns"])
                 and lower <= event["monotonic_ns"] <= upper,
                 "Saved event falls outside its recorded same-boot phase.")


def validate_saved(bundle):
    """Validate a completed saved three-arm study without rerunning any research.

    This checks local source bytes, review/ledger consistency, saved feasibility,
    retained independent objectives and saved timing arithmetic. It neither
    computes an optimum nor proves provenance against an adversary who can
    rewrite all local files; review identities are not cryptographic signatures.
    """
    try:
        _require(type(bundle) is dict and set(bundle) == {"schema_version", "study_id", "binding", "reviews",
                 "input_manifest", "ledger", "summary", "limitations", "completion_clock"}
                 and bundle["schema_version"] == "scheduling-threshold-study-result-v1"
                 and bundle["study_id"] == STUDY_ID, "Invalid saved study bundle.")
        binding = bundle["binding"]
        _require(type(binding) is dict and set(binding) == _CLAIM_BINDING_FIELDS
                 and binding["study_id"] == STUDY_ID and binding["output_root"] == _OUTPUT_ROOT
                 and binding["request_id"] == "prepare-g5-scheduling-threshold-transfer-v1"
                 and _digest(binding["protocol_sha256"]) and _digest(binding["setup_review_sha256"])
                 and _digest(binding["budget_sha256"])
                 and type(binding["code_commit"]) is str and len(binding["code_commit"]) == 40
                 and all(c in "0123456789abcdef" for c in binding["code_commit"])
                 and type(binding["runtime"]) is dict and bool(binding["runtime"]), "Claim binding differs.")
        _verify_runtime(binding["runtime"])
        protocol = _frozen_protocol_and_sources(binding["source_fingerprints"])
        _verify_original_source(protocol)
        _require(binding["protocol_sha256"] == binding["source_fingerprints"][_PROTOCOL]
                 and binding["budget_sha256"] == _fingerprint(protocol["budget"]),
                 "Protocol or budget identity differs.")
        ledger = bundle["ledger"]
        _require(type(ledger) is dict and set(ledger) == {"claim", "claim_sha256", "events", "phases",
                 "counts", "unknown", "failed", "usage", "halted"}
                 and ledger["unknown"] == [] and ledger["failed"] == [] and ledger["halted"] is None,
                 "A completed saved audit requires a complete ledger.")
        claim = ledger["claim"]
        _require(type(claim) is dict and set(claim) == {"schema_version", "binding", "limits"}
                 and claim["schema_version"] == "bounded-study-claim-v1"
                 and _canonical(claim["binding"]) == _canonical(binding)
                 and _canonical(claim["limits"]) == _canonical(EXPECTED_LIMITS), "Claim or limits differ.")
        operations = _verify_event_chain(claim, ledger["claim_sha256"], ledger["events"])
        cases = _verify_manifest(bundle["input_manifest"])
        manifest_sha256 = _fingerprint(bundle["input_manifest"])
        _verify_reviews(bundle["reviews"], binding, ledger["claim_sha256"], manifest_sha256)
        phases = ledger["phases"]
        _require(len(ledger["events"]) == 2400, "Complete primary receipts are required.")
        anchor = ledger["events"][57]["sha256"]
        _verify_saved_phases(phases, ledger["claim_sha256"], anchor, manifest_sha256,
                             bundle["reviews"]["input"]["raw_sha256"], bundle["completion_clock"])
        _verify_event_clock_bounds(ledger["events"], phases, bundle["completion_clock"])
        _require(phases["generation"]["boot_id"] == binding["runtime"]["boot_id"],
                 "Recorded operation phases do not use the reviewed runtime boot.")
        _require(bundle["input_manifest"]["generation_previous_event_sha256"] == anchor,
                 "Input manifest does not bind the generation boundary.")
        observations, actual_counts = _verify_completed_operations(cases, operations)
        _require(_canonical(ledger["counts"]) == _canonical(actual_counts), "Ledger counters differ from receipts.")
        usage = {kind: {"reserved": actual_counts[kind], "completed": actual_counts[kind],
                        "failed": 0, "unknown": 0}
                 for kind in ("generate", "warmup", "timed", "correctness", "oracle", "bruteforce", "audit")}
        _require(_canonical(ledger["usage"]) == _canonical(usage), "Saved reservation/completion usage differs.")
        summary = _summarize_saved(cases, observations)
        _require(_canonical(bundle["summary"]) == _canonical(summary), "Saved summary differs from all stored timings.")
        _require(type(bundle["limitations"]) is list and 1 <= len(bundle["limitations"]) <= 20
                 and all(type(x) is str and 0 < len(x.strip()) <= 4000 for x in bundle["limitations"]),
                 "Saved limitations are required.")
        _require(_canonical(bundle["limitations"]) == _canonical(protocol.get("limitations")),
                 "The complete frozen limitations must be retained.")
        return {"schema_version": "scheduling-threshold-saved-verification-v1", "status": "passed",
                "scientific_validation": False, "summary": summary, "counts": actual_counts,
                "oracle_scope": "stored independently computed objectives compared, not recalculated",
                "integrity_scope": "hash, chain and recorded-time consistency; same-UID history, clock and review identity are not independently authenticated"}
    except SavedVerificationError:
        raise
    except (KeyError, IndexError, TypeError, ValueError, UnicodeError, OverflowError, RecursionError):
        raise SavedVerificationError("Malformed saved study evidence.") from None


def _verify_primary_receipt(receipt, bundle_sha256, completion, deadline, last_event_sha256):
    _require(type(receipt) is dict and set(receipt) == {
        "schema_version", "bundle_sha256", "boot_id", "finished_monotonic_ns", "after_ordinal", "previous_event_sha256"}
        and receipt["schema_version"] == "bounded-study-primary-result-v1"
        and receipt["bundle_sha256"] == bundle_sha256
        and receipt["boot_id"] == completion["boot_id"]
        and _int(receipt["finished_monotonic_ns"])
        and completion["operations_finished_monotonic_ns"] <= receipt["finished_monotonic_ns"] < deadline
        and _int(receipt["after_ordinal"]) and receipt["after_ordinal"] == 2400
        and receipt["previous_event_sha256"] == last_event_sha256,
        "Primary bundle receipt, last event, or recorded finish time differs.")


def verify_primary_result(bundle, final_snapshot):
    """Bind canonical saved bundle to the post-write primary receipt, before audit.

    This checks recorded timing arithmetic only. The timestamps and event
    history are cooperative same-UID records, not OS-enforced attestations.
    """
    verified = validate_saved(bundle)
    original = bundle["ledger"]
    _require(type(final_snapshot) is dict and set(final_snapshot) == set(original)
             and final_snapshot["unknown"] == [] and final_snapshot["failed"] == []
             and final_snapshot["halted"] is None, "Final primary ledger snapshot is incomplete.")
    for key in ("claim", "claim_sha256", "events", "counts", "usage", "unknown", "failed", "halted"):
        _require(_canonical(final_snapshot[key]) == _canonical(original[key]),
                 "Final primary snapshot changed a saved claim, event, or count.")
    final_phases = final_snapshot["phases"]
    _require(type(final_phases) is dict and set(final_phases) == set(original["phases"]),
             "Final primary phase set differs.")
    for key in ("generation", "generation_result", "input_review", "primary"):
        _require(_canonical(final_phases[key]) == _canonical(original["phases"][key]),
                 "A frozen phase changed after the primary bundle was recorded.")
    receipt = final_phases["primary_result"]
    _verify_primary_receipt(receipt, _fingerprint(bundle), bundle["completion_clock"],
                            original["phases"]["primary"]["deadline_monotonic_ns"],
                            original["events"][-1]["sha256"])
    return {"schema_version": "scheduling-threshold-primary-receipt-verification-v1", "status": "passed",
            "bundle_sha256": receipt["bundle_sha256"], "saved_verification": verified,
            "time_scope": "recorded same-boot timing arithmetic only; no clock or solver rerun"}
