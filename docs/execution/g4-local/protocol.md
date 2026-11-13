# G4-L fixed group-helper capability and evaluation protocol

Scope: one reviewed, trusted-local code-candidate experiment. This protocol and `scripts/g4_group_capability.py` define the fixed computational interface; no future worktree optimization candidate was provided or executed when the capability tests were written. The positive helper strings in `tests/test_g4_group_capability.py` are explicitly **synthetic engineering language examples**, not candidate lineage, research experiments or a performance result.

The accepted local continuation does not provide a general Python/CLI plugin capability, OS sandbox, malicious same-user isolation or sealed evaluator. The original G4 Gate remains separately limited. No new study fitting, model/API send, old-case migration or evaluator modification is authorized by a helper request. Root owns worktrees, mutation allowlist, source/data/evaluator freezes, fixed outer attempt ledger and final review; the helper owns no paths or transport.

## Exact helper/input/output contract

The source is strict UTF-8, at most **16,384 bytes**, with exactly one top-level definition:

```python
def encode_groups(labels):
    # Only capability-language statements/expressions described below.
    ...
```

There are no annotations, defaults, decorators, positional-only/keyword/variadic parameters, type parameters, nested functions or other top-level objects. Optional leading docstring is at most 512 characters; it is never treated as instructions. Ellipsis in the example is illustrative and is **not** an allowed AST constant.

Input is an exact Python `list` or `tuple` already decoded/prepared by the fixed host, containing at most **2,048** labels. Each label is an exact `list`/`tuple` of **1–4 exact strings**, each ≤**128 Unicode codepoints**, encodable as strict UTF-8. Subclasses, custom objects, numbers, bools, nulls, nested containers and lone JSON surrogates are rejected. The host input is validated before interpretation and copied into a readonly internal sequence of immutable string tuples. Empty outer input is allowed as an engineering boundary; individual labels cannot be empty. Original input objects cannot be mutated by a helper.

Output must be an exact list with one exact integer per input row; bool is not an integer here. IDs must be in `0..n-1`; empty input returns `[]`. Capability validity does **not** establish correct grouping: a correctly shaped `[0,0]` for different labels passes this boundary and must fail the independent equivalence evaluator. The fixed evaluator, outside the helper, constructs `np.array(group_ids)` and checks dtype/shape, exact first-occurrence IDs and `GroupKFold` splits. No NumPy object, model, project, evaluation labels or mutation API is exposed to the helper namespace.

## Closed AST/operation subset

The controller parses syntax with `ast.parse` and then interprets its own nodes. It does **not** call Python `eval`, `exec`, bytecode `compile`, import a candidate module, invoke a candidate native Python function, or evaluate module top-level code. `ast.parse` constructs syntax data; it does not make executable candidate bytecode. Static inspection is cached for at most 32 exact source byte strings; the AST is not returned to the helper.

Allowed statements: one-target name assignment, dictionary-cell assignment, explicit return, bounded `for`, `if/else`, fixed intrinsic call statements and the optional leading docstring. No for-else. Allowed expressions: bound names; small int/bool/None constants; bounded flat list/dict construction; list/dict comprehensions with exactly one finite generator and ≤2 filters; one membership/equality comparison (`in`, `not in`, `==`, `!=`); `not` and integer unary minus; simple-name bounded subscripting; and the fixed intrinsics below. There are at most **512 AST nodes**, **32 levels** of AST depth, **two** nested loop/comprehension levels and **64** local names. Integer constants are bounded by ±2,048. Dunder names, arbitrary strings as code constants, starred args/dict expansion and chained comparisons are rejected.

Only these calls have interpreter-defined semantics:

- `list()` or `list(sequence)`, `dict()` with no arguments, `len(sequence_or_dict)`;
- `enumerate(sequence)` **directly** as the source of a for/comprehension, with no stored iterator alias;
- `dict.fromkeys(sequence[, bounded_integer_or_None])`;
- local lists' `index(scalar_or_label)` and `append(scalar_or_label)`;
- local dictionaries' `get(label[, bounded_integer_or_None])` and `setdefault(...)`.

No keyword arguments. Intrinsic attribute receivers must be simple names; attribute values cannot be loaded, chained or passed around. Dictionary keys must be primitive group-label tuples; values can only be bounded int/None. Scratch lists can only contain bounded int/None or immutable group-label tuples; no containers, function objects, reflection handles or custom objects can be stored as cells. The input wrapper has no exposed append/assignment operation. Subscript access is only to local dictionary cells or in-range integer cells of bounded lists/input; arbitrary object attributes, tuple/string slicing and negative output IDs are unavailable.

Loop sources are the fixed input, already bounded lists/dictionaries or direct finite enumerate values. Sequence snapshots are bounded to 2,048 members. Mutation of a list/dictionary currently being iterated is rejected, including alias access. This is a deliberately limited language, not compatibility with every legal Python iteration/mutation pattern. There is no `while`, recursion, function/class/lambda definition, exception/with/global/nonlocal operation, `range`, arbitrary arithmetic, sequence multiplication, power operation, generator escape, import, IO, filesystem, network, subprocess, reflection or dynamic call operation.

## Hard accounting and failure behavior

Fixed defaults / hard maxima:

| Counter | Maximum | Charged before the operation |
|---|---:|---|
| `steps` | 5,000,000 | Each interpreted statement/expression and bounded loop iteration, plus every list-scan comparison |
| `allocated_cells` | 262,144 | Normalized input references, newly created containers, list appends, new dictionary key/value cells, finite snapshots, enumerate pairs and comprehension-environment copies |
| `scalar_work` | 64,000,000 | Abstract label hashing/key-operation and scalar-comparison work, weighted by participating string codepoint lengths |

The fixed host can lower these via exact `Limits(steps=..., allocated_cells=..., scalar_work=...)`, never raise them, set nonpositive values or pass bools. Debit checks happen before the charged primitive; exhausted counters do not overshoot their ceiling. Input-copy debit is within the failure-receipt boundary, so even a cap too small for input references returns usage. Counts include cumulative transient allocations, not only final live objects. Container length and AST/source limits apply independently.

These are **abstract interpreter/operand accounting counters**, not exact CPU instructions, Python allocator bytes or every native dictionary collision probe. Native dict hashing/collision equality is additionally bounded by the fixed primitive-label/row/container limits; counters do not claim precise native collision CPU accounting or OS protection. The independent host runner additionally records available process safeguards: **180s wall**, **120s soft / 130s hard CPU**, **1 GiB address space**, **32 MiB output file limit**, one worker and numerical thread settings **1**. Unsupported limits must remain reported as unsupported; they cannot be relabeled cgroup or filesystem enforcement. No heavy study workload or process-limit test is needed to validate this language module itself.

`CapabilityError.code` distinguishes structural rejection, wrong input/type/output, missing lookup, mutation during iteration and budget exhaustion. Runtime rejections carry `error.usage` for all counters; invalid source/input/limits rejected before interpreter entry can have `usage=None`. The outer runner must preserve the original error, phase and attempt identity in a fresh receipt, never replace failure with a successful retry. This module has no retry, persistent attempt ledger, production promotion or project-write entrypoint.

## Public fixed-host API

```python
validate_group_program(source: str | bytes)
# Metadata only: source_sha256, ast_sha256, ast_nodes, executed=False.

execute_group_program(source, labels, *, limits=None)
# g4-group-capability-execution-v1 receipt: group_ids, source/AST/input/output SHA,
# usage, limits, product_model_calls=0, fit_calls=0 and explicit trust boundary.
```

The API receives source text/bytes and primitive data, **not candidate-selected file paths or commands**. A successful repeat is deterministic for the same exact source, labels and limits, but this does not debit or reconcile a persistent outer experiment. Idempotent recovery/attempt accounting is the fixed runner's separate responsibility. Native group-code callers and the original module outside the helper must be independently diff-reviewed; a helper validation receipt does not approve an arbitrary native callsite or source release.

## Baseline and future candidate review order

Root prepared an explicit baseline adaptation in a separate worktree (commit `37b70c2`, parent `0ceb274`): original list/linear-index grouping factored into `encode_groups`, native callsite performs fixed `np.array` around its returned list. `work/g4-local/baseline-helper.py` was accepted by **pure validation only**, source SHA `21d726c2bc6e9f027ee2d8525f23d069fb489f4af340523105d75a3053d10eb0`, AST SHA `d34af3fc1811723c094638f8a78c72addc4c084470e07490af0dc02f7db73790`, 31 nodes. Root preserves the baseline adaptation diff separately from the future optimization diff. No worktree helper was interpreted in the capability-test task.

Before creating/running a future candidate: independently review this interpreter/tests/protocol, freeze their exact hashes and the fixed evaluator; freeze the baseline commit/module/callsite, the three full real group-input arrays and saved-fold identities, synthetic engineering correctness cases and timing rules. The candidate's valid subset is structural and operation-based, **not equality with one hardcoded helper template**. Multiple dictionary/list formulations are accepted; semantic errors still fail independent evaluation.

The separate fixed runner must reject changes outside the allowed helper: only the named adapter file may differ, and the full module after replacing the helper region must match the adapted baseline byte-for-byte. It extracts only the helper source; no candidate module import. Review receives an immutable diff/source hash before execution. Candidate is denied arbitrary paths and control writes by the closed host mutation interface, while before/after file hashes provide tamper detection rather than a same-user filesystem guarantee. Never call `upgrade` on old Concrete/G3 projects or change their frozen config/budgets.

## Frozen independent comparison

- Root/independent evaluator owns `scripts/run_g4_group_candidate.py` and its freeze, candidate review and one-attempt ledger. Capability author owns this fixed interpreter, tests and protocol; candidate author owns only a later separate worktree helper. Independent reviewer authors neither candidate nor acceptance outputs.
- Compare first-occurrence IDs to an independent reference on complete source Concrete/Real Estate/Slump group arrays plus explicit synthetic edge/counterexamples; array dtype/shape and every `GroupKFold` train/test membership must match the saved baseline. Patch estimator `.fit` methods to raise if accidentally reached; no target-model recomputation or fit is allowed.
- Negative tests include forbidden operations/names/top-level code, input dimensions/types, mutated iteration sources, nested containers, step/cell/scalar exhaustion, invalid returns, extra module/path changes, altered evaluator/freeze/control file, conflicting identity, incomplete result and retry. Capability tests do not replace runner integrity/recovery tests.
- Timing is at most **five warmups per arm** and **100 paired repetitions per dataset**, arm order alternating by pair; three full real data shapes, fixed limits, one evaluation batch/attempt. Retain every duration/counter and loss, not only aggregates. No post-result source/threshold/repetition tuning; unresolved/error stays visible.
- Timing is specifically **this fixed interpreter's helper evaluation plus its documented receipt/guard overhead** as delimited by the runner. If it measures only a narrower stage, record that exact stage. It is **not** automatically native Python/NumPy grouping speed, full-CV latency, research quality, scientific gain or evidence of better model decisions. Abstract operation/cell counts and exact output equivalence are useful even when timing is slower or inconclusive.
- Local decision is `accepted_for_future_review`, `rejected`, `inconclusive` or explicit failure, bound to actual hashes/criteria; never automatic main/source/Recipe/production promotion. Preserve actual negative results. Correctness plus no observed speedup can yield a legitimate rejection. Full protected/sealed G4 and sustained RSI remain unpassed.

## Actual verification of the capability module

Run only the targeted engineering security tests:

```sh
python -B -m unittest discover -s tests -p 'test_g4_group_capability.py' -v
```

They exercise distinct allowed baseline/list/dictionary/comprehension formulations, empty/duplicate/Unicode/boundary labels, exact primitive types, output contracts, deny-before-execution syntax/IO/reflection payloads, mutation and allocation boundaries, and error accounting. They do not load a future candidate or perform study fits, model calls, timing research or modify any old case. Independent reviewer tests and frozen-runner tests must be reported separately. This protocol is not itself a claim that the later candidate experiment ran.
