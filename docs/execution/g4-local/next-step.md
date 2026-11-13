# G4-L next step: one bounded code-candidate experiment

Status: **proposal / source inspection only**. This task did not run a candidate, fit, model/API request, migration or project mutation. It did not modify the old Concrete case or frozen G3 inputs. Baseline source observed at inspection: `5c8dff5cdcaf9205ca1b979fef53c1111d272116`; Sprint 003 changes are still in the shared working tree, so this SHA alone is **not** the final candidate baseline. Root must finish/review and freeze the intended source tree before creating worktrees.

## Decision and original Gate boundary

Continue under [the accepted trusted-local route](../local-continuation.json). The next useful unit is a **reviewed, pure-function source-code change in a separate worktree**, evaluated by an independent fixed controller without new study fits. This does not require repeating the unavailable Worker request. It does require implementing the narrow execution-capability boundary below **before** executing any candidate bytes.

The original [G4 Gate](../pack-v2/06-roadmap/PHASE_DELIVERABLES_AND_GATES.md) requires baseline freeze, real code modification, independent evaluation, promotion/rejection and candidate inability to modify evaluator/hidden tests/budget/security/promotion. [Two-level RSI](../pack-v2/02-architecture/TWO_LEVEL_RSI.md) explicitly protects these objects. The current shared-user environment cannot establish whole-worktree hostile-code containment or OS-protected hidden evaluation. A worktree, hashes, `timeout`, monkeypatch or process limit alone does not establish it.

Therefore report **G4-L trusted-local code-candidate result**, with explicit local selection/rejection and lineage; do not mark full G4/sealed RSI passed. User acceptance of missing Worker controls authorizes bounded trusted work, not invented isolation evidence. Unknown developer model/token/currency usage remains unknown; the experiment itself has model/API/fitting allowances **0**.

## What current code actually supports

| Existing entry | Reuse | Boundary |
|---|---|---|
| `recipe_improvement.py:261` `run_improvement_round`, `:365` `run_improvement_sequence` | Immutable staged receipts, pending/keep/revert semantics, parent SHA chain and recovery design | Evaluates already-saved JSON Recipe/Host/controller evidence. It does **not** create code worktrees, mutate Harness code, supply independent code evaluation or protect hidden tests. A completed fixture is not code RSI. |
| `research_recipe.py:220` `compile_recipe`; `:119/135` method-card parse/match | Closed JSON condition/candidate selection, explicit method/evaluation identity | Textual age applicability is not automatically understood; changing selections does not prove improved research. Do not fake a Host model proposal to force this API to accept the new experiment. |
| `method_registry.py:25/32/69` | Explicit allowlisted primary/follow-up adapters and version hash | Registry is a fixed local dispatch table, not a general plugin/candidate Python execution hook. |
| `project_controller.py:13/72` and `research_project.py:26/257/555` | Controller/application code identities and `CODE_CHANGED` refusal | Narrow source changes can invalidate old execution identities. Do not bypass, strip or update these checks to make old cases appear unchanged. |
| `ridge_validation_adapter.py:94/104/126` | Adapter identity, fixed Ridge protocol and the real group-encoding code below | Whole `execute()` fits estimators; initial G4-L must not invoke it as a new study or reset a consumed ledger. |
| `feature_comparison.py:42`, `saved_oof_diagnostics.py:259` | Strict existing-result comparison / saved arithmetic | Useful correctness references, not a code-promotion evaluator or independent unseen task set. |
| `research_project.py:669` `upgrade` | Explicit compatibility registration retaining history/budgets | **Do not call on any old G1/G3 case in this slice.** No migration is required to evaluate a code candidate outside the product project. |
| `runtime.py:90`, `protocol.py` | Existing AgentArts request/body/allowlist boundaries | AgentArts runtime has optional SDK/auth/deployment requirements and no verified local code-candidate containment. It is unnecessary for this slice. |

Existing meaningful test locations include `tests/test_ridge_validation_adapter.py`, `test_raw_validation_project.py`, `test_group_only_design.py`, `test_project_controller.py`, `test_recipe_improvement.py`. Several of these perform real fits: do **not** run their full suites under the proposed zero-fit experimental allowance. Select/add pure grouping and code-boundary checks; distinguish future separately authorized fit regression from the present replay-equivalence scope.

## Recommended first candidate

**Hypothesis:** replace repeated linear group-label lookup in the fixed Ridge adapter with a stable dictionary index, preserving every group ID and evaluation split while reducing the encoding overhead.

Actual current source at `ridge_validation_adapter.py:126-127`:

```python
labels = list(dict.fromkeys(row["groups"] for row in rows))
group_ids = np.array([labels.index(row["groups"]) for row in rows])
```

Its encoding cost is O(n × g) in the number of complete rows and distinct groups. The real frozen inputs already include 1,030/427 source rows/groups, 414/259 Real Estate rows/groups and 103/103 Slump rows/groups. This is a **static complexity finding**, not yet a measured bottleneck or claimed speedup. The source change can introduce a tiny pure helper and use a first-appearance dictionary lookup with the same `np.array` behavior. No split logic, model configuration, source fields, statistical metric, parameter or budget changes are needed.

Scope: one reviewed code candidate, not a search over many implementations. First freeze the exact baseline extraction/helper wrapper without changing its original encoding expression; then permit only the helper body and its exact native callsite in `ridge_validation_adapter.py` to differ. Record the baseline-wrapper adaptation separately from the optimization diff. If the measured overhead is immaterial, reject the candidate rather than promoting a pointless change. The candidate is an engineering-efficiency hypothesis informed by actual input size, **not** a remedy for adverse scientific predictions, a demonstrated error in the baseline, or an age-transfer discovery.

This is preferable as the first local code-execution slice to automatically interpreting natural-language method applicability: Slump's lack of age is a real semantic boundary, but a machine-checkable semantic adapter would need a separately frozen contract and counterexamples first. Do not create an artificial “baseline applies age to cement” failure that the real system never emitted.

## Worktree, capability and ownership contract

1. Root freezes completed Sprint 003 source/dependencies/configs and readonly evidence hashes. Use a clean committed baseline or an explicit complete-tree content manifest; never identify a dirty tree by HEAD alone. Preserve its Git bundle/commit and exact Python/NumPy/scikit-learn versions. No new external dependencies or network are needed.
2. Create sibling baseline/candidate worktrees beneath a new `work/g4-local/` area. Do not copy the old mutable manager into the candidate directory, reset the main checkout, or reuse an existing candidate output directory. The candidate author owns only the allowed helper/change; root owns outer state, evaluator, input manifest, allowlist, budget and selection controller; an independent reviewer owns acceptance and withheld engineering cases.
3. Candidate payload is **code-as-data in a diff/source file**, never a shell command, import path, plugin name, arbitrary expression or callable submitted through the product tool protocol. Fixed controller paths/entrypoints are host-owned; candidate JSON cannot choose filesystem targets, executable arguments or environment variables.
4. Before any candidate execution, the controller verifies the complete file diff is confined to the frozen helper/callsite, the rest of the tree is identical, and a reviewer accepts the change. Candidate is denied writes to evaluator/config/data/ledger/promotion files by the controller's closed mutation API. File hashes before/after remain tamper-detection evidence, **not filesystem prevention**.
5. Execute **only the reviewed pure helper**, not candidate module import/top-level code or full `execute()`. Implement a closed AST/operation gate: allow bounded first-appearance/list/dictionary indexing and construction, `enumerate`, and the fixed injected `np.array`; reject imports, arbitrary attributes/calls, globals/nonlocals, dunder names, reflection, `open`, `eval`, `exec`, subprocess/network/path APIs, class/lambda/while/recursion and unbounded sequence construction. Verify all loop sources are the finite captured rows/labels. Do not claim a blacklist or empty `__builtins__` alone is containment.
6. Fixed input consists solely of JSON-decoded primitive group-label arrays, checked against the captured case's actual complete rows. For this microtask freeze a ≤2,048-row, ≤4-string-fields-per-group, ≤128-codepoints-per-field envelope, covering all selected cases; reject larger/other-type inputs rather than changing the envelope after candidate feedback. Plain values must not carry custom Python behavior. Fixed namespace/input/output and syntactically bounded loops provide a real narrow **computational capability** restriction; it is not permission for arbitrary full Python or an OS sandbox.
7. One worker; bound wall deadline (30s), CPU (20s soft/25s hard), file output (32 MiB), and reasonable process address space after checking the installed runtime (e.g. 2 GiB), using already-supported host limits only. Thread counts one. Do not represent unavailable limits as enforced; preserve setup rejection/failure. The operation/loop bounds must hold even if an OS resource limit is unsupported. No credentials or network capability is included in the helper namespace.
8. Independent controller refuses any extra modified path, source/config mismatch, malformed output, cap violation or unresolved attempt. An interrupted attempt remains unresolved until original evidence is reconciled; restarting with a new candidate ID does not erase it.

If the closed capability gate is not yet implemented or reviewed, continue building/verifying that fixed controller and writing the candidate diff **without executing candidate code**. This is useful authorized progress, not another request for a Worker.

## Freeze and evaluation order

Use explicit local states:

`baseline_frozen → baseline_evaluated → diagnosis_recorded → candidate_diff_ready → reviewed → capability_checked → candidate_tested → independently_evaluated → accepted_for_future_review/rejected → restart_checked`

Never label the shared-user evaluation `sealed_evaluation`. The measured sequence is finite (one candidate / one evaluation batch); no unattended self-edit/run loop.

Before candidate authoring, freeze evaluator code, case/input hashes, correctness checks, timing repetitions/order, acceptance thresholds, resource bounds and source-worktree identities in a baseline manifest. Include `model:null`, `product_model_sends:0`, `fits:0`, actual trust scope and unknown development cost. Candidate receives public development group arrays, **not target values, model metrics or mutable evaluator state**. Reviewer can add frozen withheld engineering label arrays after authoring, while declaring that same-UID confidentiality is not OS-enforced. Previously observed G1/G3 datasets are public regression inputs, not newly unseen research.

### Correctness / capability tests

- On complete frozen source Concrete, Real Estate and Slump arrays, baseline and candidate must yield byte-/element-identical group IDs, dtype/shape and first-appearance order. Include repeated labels, permuted occurrence order, nonlexicographic labels, Unicode, multiple columns, all-unique/one-group/empty boundary behavior, and the exact 2,048-row bound. Engineering cases are synthetic and labeled as such.
- Independently recompute expected IDs without relying on candidate code. Use fixed `GroupKFold` on those IDs and compare every train/test record to the baseline and already saved original splits. No estimator is fitted or coefficient solved. Enforce complete row coverage and zero group leakage.
- Patch `Ridge.fit` and `StandardScaler.fit` to fail if accidentally called; explicit fitting counters must remain zero. Reject any attempt to call a full study/controller action or modify old source packets/artifacts. Guard correctness is evaluated separately from performance.
- Negative capability cases: forbidden import/call/attribute, extra file diff, changed evaluator/budget/manifest, oversized input, bad field type, malformed/oversized output, repeated candidate ID with different bytes, incomplete result, interruption and timeout. Every prohibited candidate must be rejected **before its code executes** where structurally rejectable.
- Rehash old case/input/evaluator/control files before/after, reopen the outer ledger read-only and replay the same completed attempt with helper execution disabled. Expect identical receipts/no extra timing batch or execution debit. Do not migrate the old cases for replay.

### Performance comparison / decision

Primary measurement is **group-ID encoding latency**, excluding file reads, data preparation and model fitting. It is not full-CV latency or time-to-research-outcome. Freeze, for example, five warmup calls per arm followed by 100 paired repetitions per real-input shape, alternating arm order by pair; run one batch, retain every raw duration and failure, use `perf_counter_ns`, and report paired medians plus absolute microseconds/milliseconds. No hidden repeat/seed selection after results.

Suggested predeclared engineering selection rule: all correctness/capability/preservation checks pass; at least 1.5× median encoding speedup and ≥0.5ms absolute median saving on the 1,030-row/427-group source workload; neither target workload has >10% slowdown **and** >0.05ms absolute slowdown. These are proposed thresholds, to be frozen by the independent evaluator before timing, not claimed measured results. If they are too small for reliable host timing, reject/inconclusive is a valid outcome. Publish small-input overhead and all adverse cases. Do not turn 100 timings on one input into 100 independent research tasks or a significance claim.

Candidate acceptance means **eligible for a separate future source review**, not production promotion, new data fit, scientific improvement or full G4 approval. Root may instead reject for low end-to-end value even when the microbenchmark is faster; keep that criterion explicit before final selection. No automatic changes to main, deployed services or a default Recipe occur in this experiment.

## Required artifacts and rollback

New isolated outer directory `runs/g4-local-<identity>/` must contain:

- `baseline-manifest.json`: commit/tree/module/helper/config/dependency/evaluator/input hashes, fixed allowance, explicit trust boundary;
- `hypothesis.json`: observed source code/input scale, expected effect, falsification conditions, owner, same-data/known-code limits;
- `candidate.diff` and `candidate-manifest.json`: actual code modification, parent baseline and candidate tree/helper hashes, exact allowed paths;
- `independent-diff-review.json`, `capability-check.json`, negative tests and actual limit observations;
- `baseline-results.json`, `candidate-results.json`, every correctness check and raw `timings.jsonl`; no metric summaries without raw attempts;
- `integrity-before.json` / `integrity-after.json`, error/unknown-attempt receipts, model/fit/action counters and measured runtime metadata;
- `decision.json`: `accepted_for_future_review`, `rejected` or `inconclusive`, criterion-by-criterion result, hashes, reviewer and reason; never fabricated Host/Recipe validation;
- `lineage.json`: baseline → candidate → local decision; `restart-replay.json`, `next-generation-input.json`, limitations and next question.

Rollback is pointer/selection rollback to the immutable baseline commit/helper and preserved original ledger. Never undo old scientific actions, refund estimator attempts, delete a failing candidate's receipts or rewrite its lineage. Archive rejected candidate worktree/diff until artifacts are secure; cleanup must be scoped to its exact disposable directory, not broad reset/removal commands.

Changing `ridge_validation_adapter.py` changes its `code_identity`, then registry/application identity. Keep old G1/G3 workbenches pinned to their original source snapshot and report evidence. Do not force their identities to match, auto-call `upgrade`, or re-fit them. Any later product integration is a new reviewed source release with backward-compatibility/replay verification and a concrete deployment decision; it is not necessary for this local candidate result.

## What a successful result would and would not establish

It can establish one real reviewed code diff, actual bounded pure-helper execution, independently checked split equivalence, measured local encoding speed (or a useful rejection), immutable local decision/lineage and recovery. It can exercise a narrower code-level outer loop without spending study fits or model API budget.

It cannot establish whole-system autonomous self-modification, malicious-code/credential/evaluator isolation, sealed hidden-test protection, default production promotion, new research accuracy, cross-domain scientific transfer, end-to-end efficiency without measuring it, or sustained/multigeneration RSI. The original G4 Gate remains partially unpassed for those reasons while authorized trusted-local work continues.
