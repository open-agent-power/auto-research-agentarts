# Native weighted-interval fixed pair — implementation contract

Status: implementation contract for new modules; **no full native workload executed**. Reuse ResearchProject, ProjectController, action/result/budget/report/recovery services and explicit registry dispatch. Do not shell out to or modify the frozen standalone script/results. This second task kind shares only the CPU packet/lifecycle with retrieval, not its scientific semantics. Root owns public registration, core/report integration and separately frozen real execution.

## Exact APIs and identity

- Primary module `scheduling_adapter`: `TOOL_ID="research.weighted-interval-fixed-pair"`, `ADAPTER_VERSION="1"`, `capture_source(host_directory)`, `load_source(raw_bytes)`, `execute(payload, dimension=None)`, `next_decision(tool_result)`, `code_identity()`.
- `scheduling_adapter.AUDIT` exposes `TOOL_ID="research.weighted-interval-saved-audit"`, `ADAPTER_VERSION="1"`, `eligible(original)`, `execute_saved(original, parameters)`, `next_decision(result)`, `code_identity()`.
- `original` is the verified original **ToolResult body**, not its enclosing action envelope. Root first checks actual predecessor project/action/result SHA, source/code/evaluator and current identity; parameters are exactly `based_on_action_id,based_on_result_sha256`. Audit preserves these actual references and never interprets them as file paths.
- Primary evaluation ref: `weighted-interval-fixed-pair-v1`; saved audit: `weighted-interval-saved-audit-v1`. Both cost **one local tool**, **zero fit/model/API/source-extraction calls**. Root grants a new cumulative **2-tool** lineage; no previous study allowance is reset.

## Packet and fixed files

Exact top-level keys: `schema_version,task_kind,spec_source,assets,spec,scope,snapshot_sha256`.
`schema_version="cpu-research-source-v1"`, `task_kind="weighted_interval"`.
`snapshot_sha256` is canonical SHA-256 of the other six fields. `assets` has exactly `jobs,license`; spec and each asset use exact `file_name,sha256,bytes,bytes_base64`. Preserve original bytes, strict UTF-8, duplicate-key/nonfinite rejection. Scope is recomputed from checked originals/spec, never independently trusted.

Host intake reads only `spec.json`, `jobs.json`, `license.md` beneath its selected regular unlinked directory. Spec `files` is exactly `{jobs:"jobs.json",license:"license.md"}`. No path/URL fetching, archives, pickle, commands, expressions, modules or dynamic candidate code enters this interface.

Spec exact keys: `schema_version,dataset_label,source_url,attribution,license_notes,source_provenance,files,comparison,limits`. Schema is `weighted-interval-spec-v1`. Metadata text bounds: nonempty label ≤300, source URL ≤2000, attribution/license notes ≤4000; URL is inert provenance text. `source_provenance` exact keys are `origin_script_sha256,origin_protocol_sha256,origin_manifest_sha256,generator,workload_kind`. Digests are lowercase SHA-256; generator is `weighted-interval-random-v1` or `explicit-engineering-fixture-v1`; workload_kind is always `synthetic_engineering`. Embedded metadata is not upstream verification or permission to fetch/execute a generator.

`jobs.json` is exactly `{schema_version:"weighted-interval-jobs-v1",cases:[...]}`. Each case has exactly `case_id,split,seed,jobs_sha256,jobs`:

- case_id: unique opaque ASCII identifier ≤80 characters; split: `correctness|dev|validation|test`; seed: null or exact int 0..1,000,000 (metadata only).
- jobs is a complete array of `{id,start,end,weight}`. IDs are unique exact integers **0..4095**, preserving the old numerical tie ordering; ID is not a semantic feature or executable name. Numeric bools/floats are rejected.
- start/end are exact integer ticks in ±1,000,000,000 with **start < end**. **Zero-duration is rejected**: the original brute-force stable start ordering is not a defined general zero-duration endpoint convention. Do not silently expand the frozen experiment's supported domain.
- weight is an exact integer in ±1,000,000, including zero. Negative weights are permitted because the original strict-improvement recurrence and empty optimum 0 naturally skip them; explicit small fixtures verify this. Frozen generated test weights remain 1..100, and the old zero-weight edge remains supported. Weights/ticks have synthetic engineering units, not scientific/operational measurement units.
- jobs_sha256 hashes the ordered legacy representation `[[start,end,weight,id],...]` in canonical JSON. This intentionally matches the old `value_hash(jobs)` for integer tuples. The adapter checks it against the provided jobs. Reordering, clipping, truncation, ID string conversion or selecting new seeds changes identity.

## Fixed definitions and preflight budgets

Comparison exact fields/values:

```json
{"baseline":"quadratic_scan_dp","candidate":"binary_search_dp","sort_keys":["end","start","id"],"compatibility":"end_lte_start","tie_rule":"skip_current_on_equal_objective","objective":"maximize_integer_weight_sum","test_repetitions":3,"other_repetitions":1,"bruteforce_max_jobs":12,"time_unit":"integer_ticks","weight_unit":"synthetic_weight_units"}
```

Both arms are the **same known weighted-interval DP**, differing only in predecessor lookup. Sort by `(end,start,id)`; baseline scans all previous ends, binary arm uses `bisect_right(ends,start,0,i)`; choose the job only if `pick > previous_optimum`, preserving the exact skip-on-tie schedule. Reconstruct the entire selected ID sequence. This is implementation complexity optimization, not algorithm invention, RSI or scientific discovery.

Limits exact object: `{max_cases:32,max_jobs_per_case:4096,max_total_jobs:25000,max_naive_pair_evaluations:110000000,jobs_bytes:4194304,license_bytes:65536,spec_bytes:65536,all_asset_bytes:4259840,packet_bytes:16000000,result_bytes:4000000,max_small_correctness_jobs:12,max_bruteforce_subsets:131072}`. Specs cannot raise/change these caps. Empty individual cases are allowed; total input case count is 1..32. All source/row/type/hash/aggregate-cost bounds are checked **before solving**.

For each case let repetitions = 3 for test, else 1. Preflight requires `sum(repetitions*n*(n-1)//2) ≤110,000,000`; that is the exact number of baseline predecessor comparisons for declared runs, excluding sorting/verification/bruteforce. Correctness independently enumerates subsets once for each n≤12 case; `sum(2**n) ≤131,072` bounds that work (32×4096 at most). These are logical workload bounds, not an OS isolation or precise CPU-instruction claim. Root freezes/records the supported single-worker/thread/resource safeguards before real execution.

The real native case must contain all **12 old test workloads**: sizes 128/512/2048/4096 × seeds 303/404/505, generated originally by `Random(seed*100000+n)`, original integer IDs/order and per-case legacy hashes. Total n is 20,352 and three-repetition naive comparisons are 95,594,688, within the caps. The adapter accepts smaller valid engineering inputs generically; **the host must independently compare these real-case hashes, seeds and original frozen evidence before capture**. Runtime does not trust a seed to regenerate or certify data. No full old workload is run during module unit tests.

## Native action result and saved audit

Primary returns the existing ToolResult envelope, with `model_calls=0,new_fits=0,scientific_validation=false`. `result` exact body includes `scope,source_snapshot_sha256,comparison,cases,paired_summary,usage,limitations`. Each case preserves its case ID/split/seed/input hash, **all original jobs**, correctness status and all actual run records. Each run retains arm/repetition, raw seconds, integer objective, **full selected schedule**, schedule SHA and operation counters. Three test repeats alternate baseline/candidate order as in the frozen script; other cases run once per arm. No schedules or slower/tied cases are dropped.

Operation counters retain original `full_scan_comparisons` (n(n−1)/2 for scan, **0 meaning no full scan** for binary, not zero CPU work), and identify bisect calls/DP steps/reconstruction steps separately. Native `bisect` internal comparisons are not falsely counted as zero or exact known CPU work. Feasibility verifies all selected IDs, no duplication, endpoint compatibility, and exact selected-weight sum. Both arms/repeats must have exactly the same objective **and selected ID schedule**. Small-case brute force is an independent correctness check; it is not run for large cases.

Observation kind is `weighted_interval_fixed_pair`; objective is in synthetic weight units, times in seconds. Paired summaries retain every case median, absolute differences, speedups where measurable, ties/slowdowns and all raw timings. No minimum speedup is required for correct computation, and a faster run is not auto-promotion. Evidence refs identify original jobs asset SHA and exact JSON case/job IDs; computational results do not become scientific evidence by renaming them.

Saved AUDIT receives only the original ToolResult and exact predecessor parameters. It validates the saved source/scope/comparison, cases/jobs identities, complete records, feasibility/objective/operation counters and recomputes summaries from the **stored** schedules/timings. It must not call DP, `bisect` scheduling, brute force, a generator, a clock or a model. Thus the second action addresses observed correctness/cost/timing tradeoffs without re-solving or re-timing. It retains explicit `not_resolved_again` provenance, original action/result refs, all slower/tied cases and uncertainty. Missing/tampered saved results cause rejection, not hidden new computation.

Primary next decision requests its saved audit when the action is completed; root supplies actual eligible predecessor identity. Saved audit next decision is `waiting`, preserving limitations and asking for another independently characterized workload/task before broader effectiveness claims. Root saves v1→actual-feedback v2→audit/final wait and exports using the existing native project/report services. Root handles unknown reservations, exact-ID replay, freshness and recovery; adapters do not add their own controller, side ledger or public command endpoint.

## Required focused verification

Pure small engineering fixtures: fixed objective/tie semantics, reversed input IDs and ordering, empty/adjacent/overlap/zero-weight/negative-weight cases, duplicate/invalid IDs and duration rejection, DP vs exhaustive optimum at n≤12, exact full schedule equality, kernel identity/hash/source parsing and aggregate-cost/path/byte rejection. Saved audit must succeed with solve/bruteforce/timing functions patched to fail and reject changed jobs, schedule, objective, repeat/arm/cost and source linkage. All snapshots keep failed attempts; core integration separately tests real project/action/report/recovery and old-case byte preservation.

This contract implements no new registration or real research execution by itself. Root owns explicit registry/method/evaluator/report hooks, source-release freeze, old services pinned to their original code, one real new two-action algorithm project and independent acceptance. The data remain synthetic engineering workloads with a known exact algorithm, not a new real-world scientific dataset.
