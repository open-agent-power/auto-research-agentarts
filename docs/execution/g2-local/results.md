# G2-L task coordination results

The product now has an explicit trusted analysis-task DAG, durable claim/result
receipts, reconciliation and recovery. A real saved-evidence comparison completed
the **same four tasks in all nine arms**, with identical analysis hashes and 101
historical case files unchanged. On this small workload, multiple threads brought
no median wall-time benefit; **single remains the default**. This does not pass
the original full G2 Gate or establish LLM agent, research-quality or cost benefit.

## Identity, execution and preserved budgets

- Contract: [frozen v1](contract.md), with independent-review amendments requiring
  an explicit reviewed attempt/result SHA and consistent SQLite read snapshots.
- Protocol: [comparison-protocol.md](comparison-protocol.md); runner:
  `scripts/run_g2_local_comparison.py`. Native mechanism:
  `src/autoresearch/agent_tasks.py`.
- Raw completed comparison: `runs/g2-local-comparison-20261113-02/`.
  Freeze SHA256 `7d0585b6abc67ccc5a581aa4f1d5fcceadce70c52dd56e01189f34955013636d`;
  summary SHA256 `d31bdae932ec2b983611b2eac112a616525512b2bc8413dc66f914c1cc393427`.
- Project: `project-431366b59dac432dabb315d82dee6eae`; original source snapshot
  `93a0abd645c1bd50bc4cbb6ae3864c62526baff19bf6e3ec6e722c7da1670243`;
  frozen final-state file SHA256
  `6525efc88e42c7006112fe8098f93510e560093f1e16b32a9344d6267c56efdb`.
- Read-only source snapshots and original Action references are in the freeze,
  copied inputs, task contracts, submitted result records and per-arm SQLite
  ledger. Every reconciliation binds its exact task/attempt/result digest.
- Each arm used four **coordination attempts**, zero native tool dispatches,
  zero estimator fits and zero product model/API sends. The original project's
  5 local calls, 20/20 estimator attempts, 1/1 source extraction, waiting state
  and unknown historical cash settlement were preserved. These are not reset
  allowances. Development tokens and infrastructure currency cost remain unknown.

## Same-work comparison

Fixed tasks recomputed baseline OOF arithmetic, candidate OOF arithmetic, complete
paired adverse outcomes, and frozen allowance/unknown-cost facts. The paired task
depended on host acceptance of both OOF tasks. Each analysis ran once per arm,
using the same copied input bytes and functions. All tasks had positive host
value estimates; dynamic did not gain by omitting work.

One common unmeasured warmup preceded the three rotated arm orders. There were
no sleeps or artificial inner loops. Single used one analysis thread; static
and dynamic used at most two. The host serialized actual ledger mutations.

| Repetition and execution order | Single wall ms | Static wall ms | Dynamic wall ms |
|---|---:|---:|---:|
| 1: single → static → dynamic | 54.541 | 63.735 | 101.875 |
| 2: static → dynamic → single | 53.912 | 57.268 | 54.123 |
| 3: dynamic → single → static | 61.873 | 54.698 | 56.150 |
| Median | **54.541** | 57.268 | 56.150 |

All four per-task output hashes match across all arms. The trace records actual
analysis and elapsed orchestration times; summaries include process CPU times.
Small cached JSON/Python work, SQLite bookkeeping, the GIL, other host activity
and three repetitions limit timing interpretation. No statistical significance,
representative concurrency speedup, research quality gain or model-cost saving
is claimed. Preserve this negative result and retain the simpler single default.

## Adverse evidence and initial failure

Fresh arithmetic over saved OOF confirms 1,030 paired rows, baseline/candidate
MAE 8.3833880562/5.7020725145 MPa, and the candidate's negative prediction at row
689. **313 rows worsen; 233 groups contain at least one worsened row; 129 groups
have worse group-mean absolute error.** These are distinct quantities.

The first attempt, `runs/g2-local-comparison-20261113-01/`, failed during shared
warmup before any comparison arm: the new audit incorrectly equated the last
two group definitions. Its original freeze/inputs and `failure.json` are retained,
with unchanged-case evidence. The correction separately computes both quantities;
the complete comparison uses a new output directory and new freeze. No G1 record,
historical metric or exhausted allowance was modified to make the check pass.

## Recovery and independent review

`tests/test_agent_tasks.py` has **16 passing tests**. In addition to DAG gating,
concurrent claim serialization, exact replay, attempts, unknown late results and
old project/manager protection, review exposed and corrected two real races:

- A delayed first-attempt approval could otherwise hit a second result. Host
  reconciliation now requires `expected_attempt` and, for acceptance/rejection,
  `result_sha256`; both enter the request fingerprint. A threaded interleaving
  rejects the stale review while preserving exact earlier receipt replay.
- Read-only status could otherwise combine old state with new receipts. A SQLite
  `BEGIN` fixes one read snapshot; a WAL/event-coordinated concurrent writer test
  confirms consistent old state and receipts even after its actual commit.

Original 14-test output remains preserved; reviewed log:
`runs/g2-local-unit/test-agent-tasks-reviewed.log`. Reconciliation is a host API
convention in trusted Python, not process authentication or OS isolation. Timeouts
remain host obligations; this module does not dispatch, auto-expire, or reassign
unknown tasks. Original cgroup failure and G4 prohibition remain unchanged.
