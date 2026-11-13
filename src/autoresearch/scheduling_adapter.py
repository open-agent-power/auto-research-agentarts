"""Bounded native weighted-interval fixed pair and saved-only arithmetic audit."""
import base64
import binascii
import copy
import hashlib
import json
import math
from pathlib import Path
import re
import statistics
import time

from . import scheduling_kernel as kernel, source_evidence_adapter as reader
from .contracts import ResearchError, canonical, fingerprint, identifier

TOOL_ID = "research.weighted-interval-fixed-pair"
AUDIT_TOOL_ID = "research.weighted-interval-saved-audit"
ADAPTER_VERSION = "1"
FILES = {"jobs": "jobs.json", "license": "license.md"}
LIMITS = {"max_cases": 32, "max_jobs_per_case": 4096, "max_total_jobs": 25000,
          "max_naive_pair_evaluations": 110000000, "jobs_bytes": 4194304,
          "license_bytes": 65536, "spec_bytes": 65536, "all_asset_bytes": 4259840,
          "packet_bytes": 16000000, "result_bytes": 4000000,
          "max_small_correctness_jobs": 12, "max_bruteforce_subsets": 131072}
COMPARISON = {"baseline": "quadratic_scan_dp", "candidate": "binary_search_dp",
              "sort_keys": ["end", "start", "id"], "compatibility": "end_lte_start",
              "tie_rule": "skip_current_on_equal_objective", "objective": "maximize_integer_weight_sum",
              "test_repetitions": 3, "other_repetitions": 1, "bruteforce_max_jobs": 12,
              "time_unit": "integer_ticks", "weight_unit": "synthetic_weight_units"}
NOTES = ["Synthetic engineering workloads and a known exact DP, not scientific data or a newly discovered algorithm.",
         "The fixed arms differ only in predecessor lookup; faster local timing is not automatic method promotion.",
         "Host provenance/licence declarations and same-user procedural checks are not sealed evaluation or OS isolation.",
         "full_scan_comparisons=0 for binary means no quadratic full scan, not zero CPU work; native bisect comparisons are unmetered."]


def _require(value, code, message):
    if not value:
        raise ResearchError(code, message)


def _object(value, keys, name):
    _require(type(value) is dict and set(value) == set(keys), "INVALID_SOURCE", "Unexpected fields in " + name)


def _text(value, maximum):
    if type(value) is not str or not value.strip() or len(value) > maximum or "\x00" in value:
        return False
    try:
        value.encode("utf-8")
        return True
    except UnicodeError:
        return False


def _digest(value):
    return type(value) is str and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _parse(raw):
    _require(type(raw) is bytes, "INVALID_SOURCE", "Original UTF-8 bytes required")
    def pairs(items):
        value = {}
        for key, item in items:
            _require(key not in value, "INVALID_SOURCE", "Duplicate JSON member")
            value[key] = item
        return value
    def nonfinite(_):
        raise ResearchError("INVALID_SOURCE", "Nonfinite JSON is forbidden")
    def finite_float(token):
        value = float(token)
        _require(math.isfinite(value), "INVALID_SOURCE", "Nonfinite JSON is forbidden")
        return value
    try:
        text = raw.decode("utf-8", errors="strict")
        _require("\x00" not in text, "INVALID_SOURCE", "NUL input is forbidden")
        return json.loads(text, object_pairs_hook=pairs, parse_constant=nonfinite, parse_float=finite_float)
    except ResearchError:
        raise
    except (ValueError, UnicodeError, RecursionError):
        raise ResearchError("INVALID_SOURCE", "Malformed strict UTF-8 JSON") from None


def _asset(name, raw):
    return {"file_name": name, "sha256": _sha(raw), "bytes": len(raw),
            "bytes_base64": base64.b64encode(raw).decode("ascii")}


def _unpack(asset, name, maximum):
    _object(asset, ("file_name", "sha256", "bytes", "bytes_base64"), "asset")
    _require(asset["file_name"] == name and _digest(asset["sha256"])
             and type(asset["bytes"]) is int and 0 < asset["bytes"] <= maximum
             and type(asset["bytes_base64"]) is str and len(asset["bytes_base64"]) <= 4 * ((maximum+2)//3),
             "INVALID_SOURCE", "Invalid bounded asset metadata")
    try:
        raw = base64.b64decode(asset["bytes_base64"], validate=True)
    except (ValueError, binascii.Error):
        raise ResearchError("INVALID_SOURCE", "Invalid original asset base64") from None
    _require(len(raw) == asset["bytes"] and _sha(raw) == asset["sha256"], "EVIDENCE_CHANGED", "Original asset identity changed")
    return raw


def _spec(value):
    _object(value, ("schema_version", "dataset_label", "source_url", "attribution", "license_notes",
                    "source_provenance", "files", "comparison", "limits"), "scheduling spec")
    _require(value["schema_version"] == "weighted-interval-spec-v1"
             and _text(value["dataset_label"], 300) and _text(value["source_url"], 2000)
             and _text(value["attribution"], 4000) and _text(value["license_notes"], 4000),
             "INVALID_SOURCE", "Invalid scheduling identity/provenance text")
    _object(value["files"], FILES, "files")
    _object(value["comparison"], COMPARISON, "comparison")
    _object(value["limits"], LIMITS, "limits")
    _require(value["files"] == FILES and canonical(value["comparison"]) == canonical(COMPARISON)
             and canonical(value["limits"]) == canonical(LIMITS), "INVALID_SOURCE", "Fixed methods/limits cannot be changed")
    origin = value["source_provenance"]
    _object(origin, ("origin_script_sha256", "origin_protocol_sha256", "origin_manifest_sha256", "generator", "workload_kind"), "source provenance")
    _require(all(_digest(origin[key]) for key in ("origin_script_sha256", "origin_protocol_sha256", "origin_manifest_sha256"))
             and origin["generator"] in ("weighted-interval-random-v1", "explicit-engineering-fixture-v1")
             and origin["workload_kind"] == "synthetic_engineering", "INVALID_SOURCE", "Exact synthetic workload provenance required")
    return value


def _case(case):
    _object(case, ("case_id", "split", "seed", "jobs_sha256", "jobs"), "scheduling case")
    identifier(case["case_id"], "case_id")
    _require(case["split"] in ("correctness", "dev", "validation", "test")
             and (case["seed"] is None or type(case["seed"]) is int and 0 <= case["seed"] <= 1000000)
             and _digest(case["jobs_sha256"]) and type(case["jobs"]) is list
             and len(case["jobs"]) <= LIMITS["max_jobs_per_case"], "INVALID_SOURCE", "Invalid bounded case metadata")
    tuples, ids = [], set()
    for job in case["jobs"]:
        _object(job, ("id", "start", "end", "weight"), "job")
        _require(all(type(job[k]) is int for k in job) and 0 <= job["id"] <= 4095 and job["id"] not in ids
                 and -1000000000 <= job["start"] < job["end"] <= 1000000000
                 and -1000000 <= job["weight"] <= 1000000, "INVALID_SOURCE", "Invalid ID/time/duration/weight or duplicate job")
        ids.add(job["id"])
        tuples.append((job["start"], job["end"], job["weight"], job["id"]))
    _require(kernel.value_hash(tuples) == case["jobs_sha256"], "EVIDENCE_CHANGED", "Complete ordered job identity changed")
    return tuples


def _cases(document):
    _object(document, ("schema_version", "cases"), "jobs document")
    _require(document["schema_version"] == "weighted-interval-jobs-v1" and type(document["cases"]) is list
             and 1 <= len(document["cases"]) <= LIMITS["max_cases"], "WORKLOAD_LIMIT", "Invalid case count")
    ids, total, comparisons, subsets = set(), 0, 0, 0
    for case in document["cases"]:
        tuples = _case(case)
        _require(case["case_id"] not in ids, "INVALID_SOURCE", "Duplicate case ID")
        ids.add(case["case_id"])
        n = len(tuples)
        total += n
        comparisons += (3 if case["split"] == "test" else 1) * n * (n-1) // 2
        subsets += (1 << n) if n <= 12 else 0
    _require(total <= LIMITS["max_total_jobs"] and comparisons <= LIMITS["max_naive_pair_evaluations"]
             and subsets <= LIMITS["max_bruteforce_subsets"], "WORKLOAD_LIMIT", "Aggregate solve/correctness workload exceeds bounds")
    return {"case_count": len(ids), "job_count": total, "naive_pair_evaluations": comparisons, "bruteforce_subsets": subsets}


def _scope(spec, assets, counts):
    return {"domain": "algorithm", "contract": "weighted-interval-fixed-pair-v1", "dataset_label": spec["dataset_label"],
            "case_count": counts["case_count"], "job_count": counts["job_count"], "workload_kind": "synthetic_engineering",
            "input_identities": {role: {k: value[k] for k in ("sha256", "bytes")} for role, value in assets.items()},
            "comparison_sha256": fingerprint(COMPARISON)}


def _checked(payload):
    _object(payload, ("schema_version", "task_kind", "spec_source", "assets", "spec", "scope", "snapshot_sha256"), "CPU source packet")
    _require(payload["schema_version"] == "cpu-research-source-v1" and payload["task_kind"] == "weighted_interval"
             and len(canonical(payload).encode()) <= LIMITS["packet_bytes"] and _digest(payload["snapshot_sha256"])
             and payload["snapshot_sha256"] == fingerprint({k: v for k, v in payload.items() if k != "snapshot_sha256"}),
             "EVIDENCE_CHANGED", "CPU source packet identity or size differs")
    spec_raw = _unpack(payload["spec_source"], "spec.json", LIMITS["spec_bytes"])
    spec = _spec(_parse(spec_raw))
    _require(canonical(spec) == canonical(payload["spec"]), "EVIDENCE_CHANGED", "Parsed original spec differs")
    _object(payload["assets"], FILES, "assets")
    originals = {role: _unpack(payload["assets"][role], name, LIMITS[role+"_bytes"]) for role, name in FILES.items()}
    _require(sum(map(len, originals.values())) <= LIMITS["all_asset_bytes"], "WORKLOAD_LIMIT", "Asset byte sum exceeds bound")
    try:
        license_text = originals["license"].decode("utf-8", errors="strict")
    except UnicodeError:
        raise ResearchError("INVALID_SOURCE", "Original licence must be strict UTF-8") from None
    _require(_text(license_text, LIMITS["license_bytes"]), "INVALID_SOURCE", "Original licence text must be strict UTF-8")
    jobs = _parse(originals["jobs"])
    counts = _cases(jobs)
    _require(canonical(payload["scope"]) == canonical(_scope(spec, payload["assets"], counts)), "EVIDENCE_CHANGED", "Derived scheduling scope changed")
    return spec, jobs, counts


def code_identity():
    return _sha(Path(__file__).read_bytes() + Path(kernel.__file__).read_bytes() + reader.code_identity().encode())


def capture_source(directory):
    root = Path(directory).absolute()
    reader._guard_path(root, directory=True)
    spec_raw = reader._read_file(root/"spec.json", LIMITS["spec_bytes"])
    spec = _spec(_parse(spec_raw))
    assets = {role: _asset(name, reader._read_file(root/name, LIMITS[role+"_bytes"])) for role, name in FILES.items()}
    jobs = _parse(base64.b64decode(assets["jobs"]["bytes_base64"], validate=True))
    counts = _cases(jobs)
    payload = {"schema_version": "cpu-research-source-v1", "task_kind": "weighted_interval",
               "spec_source": _asset("spec.json", spec_raw), "assets": assets, "spec": spec,
               "scope": _scope(spec, assets, counts)}
    payload["snapshot_sha256"] = fingerprint(payload)
    _checked(payload)
    return payload


def load_source(raw):
    _require(type(raw) is bytes and 0 < len(raw) <= LIMITS["packet_bytes"], "INVALID_SOURCE", "Bounded source bytes required")
    try:
        payload = _parse(raw)
        _checked(payload)
        return payload
    except ResearchError:
        raise
    except (KeyError, TypeError, ValueError, UnicodeError, OverflowError, RecursionError):
        raise ResearchError("INVALID_SOURCE", "Malformed scheduling source packet") from None


def _paired(records):
    rows = []
    for case in records:
        medians = {method: statistics.median(r["seconds"] for r in case["runs"] if r["method"] == method) for method in kernel.METHODS}
        base, candidate = (medians[m] for m in kernel.METHODS)
        rows.append({"case_id": case["case_id"], "split": case["split"], "seed": case["seed"], "jobs": len(case["jobs"]),
                     "median_seconds": medians, "candidate_minus_baseline_seconds": candidate-base,
                     "speedup_baseline_over_candidate": base/candidate if candidate else None,
                     "candidate_timing": "faster" if candidate < base else "slower" if candidate > base else "tie",
                     "objective": case["runs"][0]["objective"], "exact_schedule_equal": True})
    splits = {split: {"cases": sum(r["split"] == split for r in rows),
                     **{outcome: sum(r["split"] == split and r["candidate_timing"] == outcome for r in rows)
                        for outcome in ("faster", "slower", "tie")}}
              for split in sorted({r["split"] for r in rows})}
    return {"per_case": rows, "by_split": splits,
            "adverse_cases": [r["case_id"] for r in rows if r["candidate_timing"] in ("slower", "tie")]}


def _references(payload):
    return [{"source_snapshot_sha256": payload["snapshot_sha256"], "source_sha256": payload["assets"]["jobs"]["sha256"],
             "file_name": FILES["jobs"], "url": payload["spec"]["source_url"], "license_note": payload["spec"]["license_notes"],
             "locator": {"kind": "json_cases", "case_ids": [c["case_id"] for c in _parse(base64.b64decode(payload["assets"]["jobs"]["bytes_base64"]))["cases"]]}}]


def _tool(tool_id, result, kind, summary, refs):
    value = {"schema_version": "weighted-interval-result-v1", "tool_id": tool_id, "adapter_version": ADAPTER_VERSION,
             "status": "completed", "observations": [{"producer": tool_id, "kind": kind, "summary": summary,
                 "scope": copy.deepcopy(result["scope"]), "evidence_refs": copy.deepcopy(refs), "scientific_validation": False}],
             "evidence_refs": refs, "metrics": [{"name": "cases", "value": result["scope"]["case_count"], "unit": "count"}],
             "result": result, "failure": None, "new_fits": 0, "model_calls": 0, "scientific_validation": False}
    _require(len(canonical(value).encode()) <= LIMITS["result_bytes"], "RESULT_TOO_LARGE", "Complete scheduling result exceeds artifact ceiling")
    return value


def _execute(payload, dimension=None):
    _require(dimension is None, "INVALID_REQUEST", "Fixed scheduling pair accepts no runtime parameters")
    _, document, counts = _checked(payload)
    records, solver_calls, exhaustive_calls = [], 0, 0
    started = time.perf_counter()
    for case in document["cases"]:
        jobs = _case(case)
        optimum = kernel.brute_force(jobs) if len(jobs) <= 12 else None
        exhaustive_calls += int(optimum is not None)
        runs = []
        repetitions = 3 if case["split"] == "test" else 1
        for repeat in range(repetitions):
            order = kernel.METHODS if repeat % 2 == 0 else tuple(reversed(kernel.METHODS))
            for method in order:
                before = time.perf_counter()
                computed = kernel.schedule(jobs, method)
                seconds = time.perf_counter() - before
                solver_calls += 1
                kernel.verify_schedule(jobs, computed)
                _require(optimum is None or computed["objective"] == optimum, "INVALID_RESULT", "Independent small-case optimum differs")
                runs.append({"method": method, "repeat": repeat, "seconds": seconds, **computed,
                             "schedule_sha256": kernel.value_hash(computed["schedule"])})
        _require(all(r["objective"] == runs[0]["objective"] and r["schedule"] == runs[0]["schedule"] for r in runs),
                 "INVALID_RESULT", "Fixed DP arms or repetitions disagree")
        records.append({**copy.deepcopy(case), "runs": runs,
                        "correctness": {"bruteforce_performed": optimum is not None, "exhaustive_optimum": optimum,
                                        "paired_objective_and_schedule_equal": True}})
    summary = _paired(records)
    result = {"scope": copy.deepcopy(payload["scope"]), "source_snapshot_sha256": payload["snapshot_sha256"],
              "comparison": copy.deepcopy(COMPARISON), "cases": records, "paired_summary": summary,
              "usage": {**counts, "solver_calls": solver_calls, "bruteforce_calls": exhaustive_calls,
                        "wall_seconds": time.perf_counter()-started, "native_fits": 0, "model_calls": 0},
              "limitations": copy.deepcopy(NOTES)}
    value = _tool(TOOL_ID, result, "weighted_interval_fixed_pair", summary, _references(payload))
    _saved(value)
    return value


def execute(payload, dimension=None):
    try:
        return _execute(payload, dimension)
    except ResearchError:
        raise
    except (KeyError, TypeError, ValueError, UnicodeError, OverflowError, RecursionError):
        raise ResearchError("INVALID_RESULT", "Scheduling fixed-pair computation did not satisfy its contract") from None


def _saved(original):
    try:
        return _saved_checked(original)
    except ResearchError:
        raise
    except (KeyError, TypeError, ValueError, UnicodeError, OverflowError, RecursionError):
        raise ResearchError("INVALID_RESULT", "Malformed saved scheduling ToolResult") from None


def _saved_checked(original):
    _require(type(original) is dict and original.get("schema_version") == "weighted-interval-result-v1"
             and original.get("tool_id") == TOOL_ID and original.get("adapter_version") == ADAPTER_VERSION
             and original.get("status") == "completed" and original.get("scientific_validation") is False
             and all(type(original.get(k)) is int and original[k] == 0 for k in ("new_fits", "model_calls"))
             and len(canonical(original).encode()) <= LIMITS["result_bytes"], "INVALID_RESULT", "Completed bounded scheduling ToolResult required")
    result = original["result"]
    _object(result, ("scope", "source_snapshot_sha256", "comparison", "cases", "paired_summary", "usage", "limitations"), "saved result")
    _require(_digest(result["source_snapshot_sha256"]) and canonical(result["comparison"]) == canonical(COMPARISON),
             "EVIDENCE_CHANGED", "Saved scheduling source/comparison changed")
    cases = result["cases"]
    _require(type(cases) is list and 1 <= len(cases) <= 32, "INVALID_RESULT", "Bounded complete saved cases required")
    inputs, solver_calls, brute_calls = [], 0, 0
    for case in cases:
        _object(case, ("case_id", "split", "seed", "jobs_sha256", "jobs", "runs", "correctness"), "saved case")
        prior = {k: case[k] for k in ("case_id", "split", "seed", "jobs_sha256", "jobs")}
        jobs = _case(prior)
        inputs.append(prior)
        reps = 3 if case["split"] == "test" else 1
        runs, seen = case["runs"], set()
        _require(type(runs) is list and len(runs) == 2*reps, "INVALID_RESULT", "Incomplete saved run coverage")
        for index, run in enumerate(runs):
            _object(run, ("method", "repeat", "seconds", "objective", "schedule", "full_scan_comparisons", "operations", "schedule_sha256"), "saved run")
            method = run["method"]
            repeat = index//2
            expected_method = (kernel.METHODS if repeat % 2 == 0 else tuple(reversed(kernel.METHODS)))[index % 2]
            _require(method == expected_method and type(run["repeat"]) is int and run["repeat"] == repeat
                     and (method, repeat) not in seen and type(run["seconds"]) in (int, float)
                     and math.isfinite(run["seconds"]) and run["seconds"] >= 0
                     and run["schedule_sha256"] == kernel.value_hash(run["schedule"]), "INVALID_RESULT", "Invalid run order/timing/schedule identity")
            seen.add((method, repeat))
            kernel.verify_schedule(jobs, run)
            expected_scan = len(jobs)*(len(jobs)-1)//2 if method == kernel.METHODS[0] else 0
            _object(run["operations"], ("dp_steps", "full_scan_comparisons", "bisect_calls", "bisect_internal_comparisons", "reconstruction_steps"), "operation counts")
            ops = run["operations"]
            _require(type(run["full_scan_comparisons"]) is int and run["full_scan_comparisons"] == expected_scan
                     and all(type(ops[k]) is int for k in ("dp_steps", "full_scan_comparisons", "bisect_calls", "reconstruction_steps"))
                     and ops["dp_steps"] == len(jobs) and ops["full_scan_comparisons"] == expected_scan
                     and ops["bisect_calls"] == (len(jobs) if method == kernel.METHODS[1] else 0)
                     and ops["bisect_internal_comparisons"] is None
                     and ops["reconstruction_steps"] == kernel.saved_reconstruction_steps(jobs, run["schedule"]),
                     "INVALID_RESULT", "Saved fixed operation counts differ")
        _require(all(r["objective"] == runs[0]["objective"] and r["schedule"] == runs[0]["schedule"] for r in runs),
                 "INVALID_RESULT", "Saved arms/repeats disagree")
        check = case["correctness"]
        _object(check, ("bruteforce_performed", "exhaustive_optimum", "paired_objective_and_schedule_equal"), "saved correctness")
        small = len(jobs) <= 12
        _require(check["bruteforce_performed"] is small and check["paired_objective_and_schedule_equal"] is True
                 and (type(check["exhaustive_optimum"]) is int and check["exhaustive_optimum"] == runs[0]["objective"] if small else check["exhaustive_optimum"] is None),
                 "INVALID_RESULT", "Saved correctness declaration differs")
        solver_calls += len(runs)
        brute_calls += int(small)
    counts = _cases({"schema_version": "weighted-interval-jobs-v1", "cases": inputs})
    scope = result["scope"]
    _object(scope, ("domain", "contract", "dataset_label", "case_count", "job_count", "workload_kind", "input_identities", "comparison_sha256"), "saved scope")
    _object(scope["input_identities"], FILES, "saved input identities")
    _require(scope["domain"] == "algorithm" and scope["contract"] == "weighted-interval-fixed-pair-v1"
             and _text(scope["dataset_label"], 300) and scope["workload_kind"] == "synthetic_engineering"
             and type(scope["case_count"]) is int and scope["case_count"] == counts["case_count"]
             and type(scope["job_count"]) is int and scope["job_count"] == counts["job_count"]
             and scope["comparison_sha256"] == fingerprint(COMPARISON), "EVIDENCE_CHANGED", "Saved source scope differs")
    for role, identity in scope["input_identities"].items():
        _object(identity, ("sha256", "bytes"), "saved asset identity")
        _require(_digest(identity["sha256"]) and type(identity["bytes"]) is int and 0 < identity["bytes"] <= LIMITS[role+"_bytes"], "INVALID_RESULT", "Saved source asset identity invalid")
    refs = original["evidence_refs"]
    _require(type(refs) is list and len(refs) == 1 and refs[0]["source_snapshot_sha256"] == result["source_snapshot_sha256"]
             and refs[0]["source_sha256"] == scope["input_identities"]["jobs"]["sha256"]
             and refs[0]["file_name"] == FILES["jobs"]
             and refs[0]["locator"] == {"kind": "json_cases", "case_ids": [c["case_id"] for c in cases]},
             "EVIDENCE_CHANGED", "Saved source/case evidence linkage differs")
    usage = result["usage"]
    _object(usage, (*counts, "solver_calls", "bruteforce_calls", "wall_seconds", "native_fits", "model_calls"), "saved usage")
    _require(all(type(usage[k]) is int and usage[k] == v for k, v in {**counts, "solver_calls": solver_calls, "bruteforce_calls": brute_calls, "native_fits": 0, "model_calls": 0}.items())
             and type(usage["wall_seconds"]) in (int, float) and math.isfinite(usage["wall_seconds"]) and usage["wall_seconds"] >= 0,
             "INVALID_RESULT", "Saved workload counts changed")
    _require(_paired(cases) == result["paired_summary"], "EVIDENCE_CHANGED", "Saved paired timing arithmetic differs")
    observations = original["observations"]
    _require(type(observations) is list and len(observations) == 1 and observations[0]["producer"] == TOOL_ID
             and observations[0]["kind"] == "weighted_interval_fixed_pair" and observations[0]["summary"] == result["paired_summary"]
             and observations[0]["scope"] == scope and observations[0]["evidence_refs"] == refs
             and observations[0]["scientific_validation"] is False and original["failure"] is None,
             "EVIDENCE_CHANGED", "Saved observation projection differs")
    return result


def _decision(tool_id, original, waiting):
    return {"policy_ref": {"id": tool_id, "version": ADAPTER_VERSION}, "project_status": "waiting" if waiting else "active",
            "next_action": {"kind": "review_saved_evidence" if waiting else "conditional_proposal", "execution_status": "not_executed",
                            **({} if waiting else {"method_id": AUDIT_TOOL_ID}),
                            "required_evidence": ["Review all saved feasibility/objective/timing tradeoffs; another task family is needed before broader optimization claims."]},
            "reason": "Audit complete saved schedules without re-solving or re-timing; retain adverse and tied cases.",
            "source_snapshot_sha256": original["result"]["source_snapshot_sha256"], "evidence_refs": copy.deepcopy(original["evidence_refs"]),
            "scientific_validation": False, "new_fits": 0, "model_calls": 0}


def next_decision(result):
    _saved(result)
    return _decision(TOOL_ID, result, False)


class SavedSchedulingAudit:
    TOOL_ID = AUDIT_TOOL_ID
    ADAPTER_VERSION = ADAPTER_VERSION
    code_identity = staticmethod(code_identity)

    @staticmethod
    def eligible(original):
        try:
            _saved(original)
            return True
        except (ResearchError, ValueError, TypeError, KeyError, OverflowError, RecursionError):
            return False

    def execute_saved(self, original, parameters):
        _object(parameters, ("based_on_action_id", "based_on_result_sha256"), "predecessor")
        identifier(parameters["based_on_action_id"], "based_on_action_id")
        _require(_digest(parameters["based_on_result_sha256"]), "INVALID_REQUEST", "Exact predecessor SHA required")
        prior = _saved(original)
        summary = _paired(prior["cases"])
        result = {"scope": copy.deepcopy(prior["scope"]), "source_snapshot_sha256": prior["source_snapshot_sha256"],
                  "predecessor": copy.deepcopy(parameters), "summary": summary,
                  "case_checks": [{"case_id": c["case_id"], "jobs_sha256": c["jobs_sha256"], "runs_verified": len(c["runs"]),
                                   "objective": c["runs"][0]["objective"], "feasible": True,
                                   "schedule_sha256": c["runs"][0]["schedule_sha256"]} for c in prior["cases"]],
                  "usage": {"cases_audited": len(prior["cases"]), "saved_runs_verified": prior["usage"]["solver_calls"],
                            "solver_calls": 0, "bruteforce_calls": 0, "new_timing_calls": 0, "native_fits": 0, "model_calls": 0},
                  "limitations": copy.deepcopy(NOTES) + ["Saved feasibility/objective/timing arithmetic only; optimum and timings are not resolved again."]}
        refs = copy.deepcopy(original["evidence_refs"])
        refs.append({"source_snapshot_sha256": prior["source_snapshot_sha256"], "producer": copy.deepcopy(parameters),
                     "locator": {"kind": "saved_weighted_interval_action", **parameters}})
        return _tool(self.TOOL_ID, result, "saved_weighted_interval_audit", summary, refs)

    def next_decision(self, result):
        _require(type(result) is dict and result.get("tool_id") == self.TOOL_ID and result.get("status") == "completed"
                 and result.get("scientific_validation") is False and result.get("new_fits") == 0 and result.get("model_calls") == 0,
                 "INVALID_RESULT", "Completed saved scheduling audit required")
        return _decision(self.TOOL_ID, result, True)


AUDIT = SavedSchedulingAudit()
