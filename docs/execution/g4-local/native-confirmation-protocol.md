# Fixed native confirmation of the reviewed group helper

Status: **new independent stage; implementation and static qualification only**. Real native helper execution requires this stage's independent review and a frozen concrete output. This document does not modify the completed VM protocol, its controls or VM results at `7846ec5`. The VM experiment accepted the candidate for future review on interpreter latency only; its approximately 38×/24×/10× ratios are not native timing results.

## Fixed question and authorization boundary

Measure the **same single candidate's native Python microfunction** on the same three complete frozen group arrays. There is no new candidate, source search, transform, tuning, dataset, model fit, API/model send, native product-adapter invocation or production promotion. Historical cases and old VM records remain unchanged. Native execution is a stronger operation than VM interpretation: this stage explicitly compiles two reviewed function ASTs, under a separate fixed admission gate. It does not retroactively claim that the VM used compilation.

Only these exact helper byte hashes are eligible:

- baseline `21d726c2bc6e9f027ee2d8525f23d069fb489f4af340523105d75a3053d10eb0`;
- existing candidate `c021c1ebf275ed42e07936c0b31a675d3017b7e7bef06b2c26318d5adf41358b`.

The baseline builds the first-occurrence label list and uses `list.index`; the already-reviewed candidate builds the first-occurrence dictionary through `enumerate(dict.fromkeys(labels))`. Their reviewed native callsite remains outside this confirmation's execution. Files are read from `runs/g4-local-group-20261113-01/`; no CLI option selects arbitrary helper files, modules, callable names or payloads. Payload pins:

| Complete original shape | Pinned payload SHA-256 |
|---|---|
| Concrete, 1,030 rows / 427 groups | `18fdf2174c1ba02589d828a64bd06c063014380914f477b191b75c253c0205e0` |
| Real Estate, 414 / 259 | `8f04038e7fe9b7e83bbf1531064ce2dd42d063aeccc031c28193f1a71925b7fb` |
| Slump, 103 / 103 | `17b1e78e8dc43064a4f069f997da67d2b5f10b7614c44e81bc1231ed96f7c25c` |

This is a closed two-source/three-payload verifier, **not a generally available native AST executor** or product-tool-protocol feature. New helper bytes or inputs require a different reviewed stage; they cannot be passed as parameters here.

## Native capability proof and explicit compile difference

Admission first checks the immutable old VM result/manifest pins, completed VM status, every original result artifact, original VM capability/runner/protocol hashes, both helper hashes and three payload hashes. JSON is parsed from the **same captured raw bytes that passed identity checks**, including the manifest, result, artifacts, inputs and new review. Helpers remain captured bytes throughout the attempt; path changes cannot select a different function after admission. These identity checks do not claim same-user filesystem isolation.

`pure_ast` applies the existing VM syntax validator, then a deliberately narrower, typed, mutation-free native subset:

- Exactly `def encode_groups(labels)` with the already-fixed plain signature; only fresh-name single assignments followed by one return. No `For`, `If`, `Expr`/docstring/call statements, assignment to subscript/attribute, global/nonlocal, definitions/classes, decorators, defaults, imports, strings/constants as code, exception/with/async/yield, reflection or recursion.
- One-generator finite list/dict comprehensions without filters/async; temporary bindings cannot shadow input, existing locals, capabilities or the helper name. Their source types are known bounded input/private list/private dictionary, or direct `enumerate` thereof.
- Available pure calls are single-argument `list`, `len`, direct finite `enumerate`, `dict.fromkeys(sequence)` and a **statically known private list's** `index(label)`. Dictionary subscription is allowed only on a statically known private `label → int` dictionary. No append, setdefault, arbitrary attributes, keywords, unknown global names, callable values or mutable externally supplied objects.
- Static types flow from `labels: sequence[label]` through list/dictionary construction, comprehension bindings and integer lookup/index values. Return type must be `list[int]`. The current pair needs no native general expression interpreter, arithmetic or arbitrary loops.

After a **new independent review**, and only after all six fresh VM qualifications below succeed, `native_function` revalidates the captured helper bytes and calls `compile` on that helper-only AST. It **does not execute the compiled module code**: it takes its sole top-level `encode_groups` code constant and constructs `FunctionType` in a private fixed namespace. `__builtins__` contains only actual `list`, `dict`, `len`, `enumerate`; there are no ambient locals, module imports, project handles, paths, credentials, evaluation objects or other globals. The AST admits no way to load those objects' general attributes.

Compiled module names/constants and function signatures are checked. Recursive code-constant checks permit only compiler-created list/dict comprehensions, bounded int/None constants, the known intrinsic names (`list`, `dict`, `len`, `enumerate`, `fromkeys`, `index`) and expected lexical locals; helper free variables must be empty. Unsupported compiler output fails closed before function construction/invocation. Compiler-created comprehension closures, where applicable to the frozen Python version, can reference only the helper's private locals. This is explicitly **native bytecode compilation of two fixed audited functions**, not VM interpretation and not execution of any original candidate module top-level code.

Input to native calls is a readonly tuple-of-tuples copy containing exact primitive strings from the pinned JSON arrays. Exact types, UTF-8, maximum 2,048 rows / 4 fields / 128 codepoints are rechecked. There is no custom `__eq__`, `__hash__`, iterator or attribute behavior supplied by candidate data. Both known functions create private bounded containers and return fresh integer lists; their source has no mutation capability or external effect. A conservative logical-cell estimate `8*n + 8*groups + sum(field_counts) + 64` is checked against 262,144 before either native function exists. It is a bound/estimate on this pair's private computational containers, **not Python allocator bytes or per-native-instruction accounting**.

These restrictions, exact-source identity and bounded primitive inputs close the reviewed microfunction's operation surface. They do not provide an OS sandbox, protection from malicious same-user host code, sealed hidden tests, an evaluator-write firewall for arbitrary Python, or permission to run a different code candidate. If static typing, hashes, compiler checks, input bounds or qualification cannot be established, preserve the rejection and **do not compile/invoke** the helper.

## Prepare, new review and single attempt

Fixed host implementation: `scripts/verify_native_group_candidate.py`. Do not alter the old VM scripts/protocol to add native operations.

1. Independent code/capability review happens before concrete preparation/execution. `prepare --output <fresh direct child of repository runs/>` performs source/input/evidence identity and pure static checks only; no VM helper execution, native `compile`, `FunctionType` or invocation. It captures protected VM/history hashes and writes new `freeze.json`, `integrity-before.json`, and a pending `review-request.json`.
2. Freeze binds this script/protocol hashes, old VM evidence pins, helper/payload identities, Python/platform/dependency versions, fixed rules/VM ceilings, the **original output's absolute path**, and **SHA-256 of integrity-before bytes**. Snapshot links and redirected source paths are rejected. Current historical cases must match the approved VM's original preserved-case snapshot, not a newly invented before-image.
3. Independent reviewer supplies exact `g4-native-confirmation-review-v1`, status `approved_for_fixed_native_confirmation`, reviewer/reason, freeze SHA and exact helpers/inputs/controls. The old VM diff-review is **not** native permission. Preserve the actual review bytes in `independent-native-review.json`; result/attempt/replay bind its SHA. If the review was already written at that archive path, reuse the identical bytes; reject an existing conflicting archive **before claiming an attempt**.
4. `run` must target the original output path; one approval cannot authorize a second empty ledger or copied output. An exclusive `attempt.json` is written **before** resource setup, VM requalification or compilation. It binds fixed request `g4-native-confirmation-001`, freeze, review and attempt 1. Concurrent/repeated admission cannot create another attempt. A completed same request returns the verified receipt; an unresolved/failed attempt cannot be rerun through a new request ID or directory under this review.
5. New process safeguards are the same fixed **180s wall**, **120s soft / 130s hard CPU**, **1 GiB address space**, **32 MiB file**, one worker and numerical threads **1**. Resource setup failure leaves an unresolved attempt. These process safeguards are not cgroups, filesystem containment or per-native-operation metering. Run uses a dedicated CLI process, since limits are process-wide.
6. Within that one new epoch, perform baseline and candidate VM evaluation on **all three exact captured inputs**: six calls total, with existing 5,000,000-step / 262,144-cell / 64,000,000 abstract-scalar-work ceilings. Check each output's exact IDs, dtype/shape and saved group-fold identity, and retain every usage receipt. **All six checks must finish before either native compilation.** Old VM results alone do not substitute for this stage's fresh qualification.
7. Compile/define exactly two audited pure microfunctions. Perform six native correctness calls, 30 warmup calls and 600 paired timed calls, **636 native calls total** on a successful complete batch. Failed attempts record the phase, VM calls attempted, native compilations attempted and native helper calls; they do not invent completed counters or reset an epoch.

## Correctness and fixed timing

Independent host constructs `np.array` from returned lists and checks exact int elements, output length/order, dtype/shape, equality to an independent first-occurrence reference and fresh VM result SHA. Fixed `GroupKFold` assignments must match the saved original folds and have no group leakage. Retain the actual native IDs and fold vectors in `correctness.json`; no estimator is refitted or coefficient re-solved. Explicit estimator-fit guards cover the native correctness/timing block; the prior VM and split-only host qualification have no fitting operation.

Timing for each of the three inputs: five warmup calls **per arm**, followed by **100 paired repetitions**, baseline/candidate order alternating each pair. The timed region is **only the native helper function call on preconstructed readonly labels**. It excludes source parsing, VM qualification, compilation, input conversion, NumPy construction, fold checks, output validation/hashing and file IO. Every duration and output hash is retained in `timings.jsonl`. No adaptive repeats, additional candidate, post-result threshold changes or rerun-to-improve-results are allowed.

Selection thresholds are unchanged from the VM protocol: source Concrete median speedup ≥1.5× **and** median saving ≥0.5ms; neither target may be simultaneously >10% **and** >0.05ms slower. Correctness and integrity are hard gates. Report absolute timings, paired median savings and all adverse cases. A correct candidate missing latency criteria is rejected for this stage; failure/uncertainty is valid and retained. No significance or full-workbench benefit follows from repeated calls on three known inputs.

## Evidence, errors and read-only recovery

Required new outputs: frozen controls/rules/input identities; independent native review original; exclusive attempt; `vm-prequalification.json`; full native ID/fold correctness; all 600 timing records; protected before/after hashes; exact criterion decisions; observed resources and actual call counts; model/API/fit counters zero; measured wall/CPU times; final artifact manifest and result hash linked from the attempt.

Write `integrity-after.json` **before** checking equality, so an integrity failure retains the concrete changed-file hashes. Failure additionally tries `failure-integrity-after.json` and preserves structured `error.json` with phase/counters; hard kills leave the original running attempt unresolved. No missing error can be treated as success. If result exists but completion bookkeeping was interrupted, this implementation remains fail-closed pending explicit investigation; it does not repeat compilation/timing or manufacture completion.

`replay --execution-disabled` revalidates freezes, review-original hash, all completed artifacts, VM evidence and protected history. It must not invoke VM helpers, compile bytecode, create functions or repeat timings. Read-only replay may inspect a copied **completed** output; copies cannot become a new execution root under the same approval. File hashes detect changes; they are not same-user filesystem prevention.

The result is `accepted_for_future_review` or `rejected` for this **native confirmation** only. It does not alter the VM decision, merge/activate the candidate, modify product code identities, migrate old projects, spend their exhausted budgets, prove full native adapter/CV acceleration, improve scientific predictions, or complete protected/sealed/multigeneration RSI. Developer-agent token/currency cost remains unknown, distinct from the program's zero product model/API sends.

## Review-time checks without executing the real helpers

Allowed before independent execution approval: `--help`; static parser/type validation of the two pinned sources; static rejection tests through `pure_ast` for forbidden constructs; invalid primitive-input/cell checks; inspection of compilation code and namespace; mocked compile/invoke-denial checks of prepare/admission. **Do not call `native_function` or `run` on real helpers** before the new review. Independent review should test swapped captured bytes, wrong SHA/source/payload, wrong schema/status/output, before-image tampering, missing/changed review original, extra execution attempt and unresolved-receipt behavior. This protocol is a plan and fixed implementation contract, not a record that native confirmation already ran.
