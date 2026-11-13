# G2-L trusted task coordination — contract v1 (frozen_by_root)

This is local/delegated **analysis task coordination**, not an LLM transport,
code executor, scientific evaluator, or proof of multi-agent benefit. Original
G0 isolation failures and G4 prohibition remain. Single-task mode is the default.
No fit, product API/model send, arbitrary command, or old case mutation occurs.

## Ownership and immutable project binding

New module: `src/autoresearch/agent_tasks.py`; tests: `tests/test_agent_tasks.py`.
`AgentTaskLedger(workspace)` stores only `workspace/agent_tasks.sqlite` in a new
experiment directory. It refuses `project.sqlite` or `workbench.sqlite` in any
ancestor or itself, symlink ancestors, and nonempty roots without its own ledger;
it never opens or creates tables in a ResearchProject or manager DB.
Host supplies `ProjectRef={project_id,source_snapshot_sha256,state_snapshot_sha256}`.
The two hashes identify frozen read-only inputs, not a live project lookup.
Changing the ProjectRef or plan under the same ledger is forbidden. The host
must verify supplied snapshot/source bytes before planning; this module validates
identities and locators but cannot attest external bytes or scientific truth.

## Public host API (all mutations return durable receipts)

```python
ledger.plan(request_id, project_ref, tasks, policy=None)
ledger.claim(request_id, agent_id, task_id=None)
ledger.submit(request_id, task_id, agent_id, attempt, result)
ledger.reconcile(request_id, task_id, resolution, reason, *, expected_attempt, result_sha256=None)
ledger.status()  # pure read; reopening never dispatches or expires work
```

Status fixes one SQLite read snapshot. At most 1024 mutation receipts are
stored per ledger. JSON payloads are size-bounded,
strict-key schemas with finite numbers. Request fingerprint binds command and
all arguments, including ProjectRef, agent and attempt. Same ID/same payload
returns the exact original receipt even after later transitions; changed payload
or command conflicts. SQLite `BEGIN IMMEDIATE` serializes claims and results.
No mutable files beside the new SQLite ledger are used as task state.

## Task specification (host-authored)

Required keys: `task_id,title,objective,user_value,workstream,owner,dependencies,
input_snapshot,source_refs,allowed_files,prohibited_files,interface_contract,
acceptance_criteria,tests,benchmark_ids,budget,runtime,risk_class,
expected_artifacts,docs_to_update,expected_value,estimated_effort`.
`input_snapshot` equals the bound `state_snapshot_sha256`.
`source_refs` is a nonempty array of `{source_id,sha256,locator}`; locator is a
nonempty descriptive string, never loaded or interpreted as an executable/path.
File lists and interface/acceptance text are declarative descriptions only.
`dependencies` must refer to other frozen tasks, with no duplicate/self/cycle.
`risk_class` must be `trusted_analysis`; no untrusted/runtime execution mode.
`budget={attempt_limit:1..3,model_requests:0,tool_calls:0,fits:0}`.
`runtime={mode:trusted_local|delegated_analysis,timeout_seconds:1..600}`.
Numeric `expected_value>=0`, `estimated_effort>0` are host estimates, not measured
benefits or agent authority. Up to 64 tasks and 64 KiB per command.

Policy defaults to `{mode:single,max_parallel:1,attempt_limit:64}`.
Modes are `single|static|dynamic`; max_parallel is 1..2 (single requires 1).
The shared attempt cap is fixed at plan creation, 1..192, separately named
coordination attempts; it neither creates nor resets project/fit/API budgets.
There is no allowance extension command in v1.

## DAG, claims, recovery and exact replay

Task states: `ready|blocked|claimed|submitted|completed|rejected|unknown`.
Dependencies unlock only after host reconciliation marks predecessors completed.
`claim` reserves one task attempt and one shared coordination attempt atomically.
Claim conflicts, exhausted task/shared attempts, or full parallel slots reject.
Repeated same claim ID never consumes again; new IDs cannot steal a claim.
`task_id=None` selects ready tasks: frozen order in single/static; dynamic chooses
highest expected_value/estimated_effort, stable task-ID tie break, excluding zero
value tasks. An explicit dynamic claim must also have positive expected value.
No runnable work returns a saved `waiting` receipt, with reason and no attempt.
There is no dispatcher, model call, clock-driven retry, automatic lease expiry,
or task reassignment. `reconcile(...,resolution=unknown,reason=...)` marks uncertain
claims, keeping their attempt spent and the slot occupied; unknown is never
reclaimed. Only the original agent/attempt may submit its late original result.
Rejected tasks may return ready only with remaining frozen attempts and a new
claim; completed tasks cannot rerun. No new ID bypasses exhausted accounting.

## Agent result: proposals are not execution observations

Exact required keys: `task_id,role,status,proposal,evidence_refs,tool_requests,
artifact_refs,metrics,uncertainty,limitations,cost_usage,next_actions`.
`task_id` must match; `role` must match frozen task owner; status is
`proposed|analysis_complete|needs_review|failed` (never scientific verified).
`proposal` is an object; `tool_requests` must be empty in this transport-free v1.
Evidence refs have `{source_id,sha256,locator}`, matching an allowed exact triple;
artifacts have `{artifact_id,sha256,locator}` and remain unverified references.
`metrics` is an object of finite numbers, scoped descriptive metrics only.
`uncertainty,limitations,next_actions` are nonempty arrays of nonempty strings.
`cost_usage={tokens:null|nonnegative_int,amount:null|nonnegative_number,
currency:null|string,usage_status:unknown|reported}`; unknown requires tokens and
amount null and remains unknown, never converted to zero or budget authority.
Neither proposal content nor result fields can alter permissions, policy,
evaluator, hidden truth, budget ledger, ProjectRef, or native research status.

## Host reconciliation and acceptance

`reconcile` is host-only Python API, not exposed to result import or model tools.
All reconciliations bind expected_attempt; completed/rejected also bind the
reviewed result_sha256; unknown requires a claimed attempt and no result hash.
Stale reviews reject; completion accepts analysis, not science. Attempts remain spent.
Every reconciliation is journaled; status includes tasks, claims/results,
request receipts, immutable input identities and attempt totals.
Tests must cover DAG gates, conflicting claims, concurrent claim serialization,
exact replay after transitions/reopen, attempt caps, unknown late-result recovery,
source/result schema rejection and unchanged old-case bytes. Experiments compare
single/static/dynamic under identical inputs; no measured benefit means retain
single as default. Full original G2 remains unpassed until its evidence exists.

Host CLI example (host-supplied `plan.json` contains project_ref/tasks/policy):
```sh
.venv/bin/python - <<'PY'
import json
from autoresearch.agent_tasks import AgentTaskLedger
ledger = AgentTaskLedger("runs/new-g2-experiment/tasks")
print(ledger.plan("plan-1", **json.load(open("/workspace/work/g2-plan.json"))))
print(ledger.claim("claim-1", "trusted-analyst"))
PY
```
