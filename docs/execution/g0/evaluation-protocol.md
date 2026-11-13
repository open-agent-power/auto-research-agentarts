# G0 independent evaluation protocol

Applies to `P0-CONCRETE-CLOUD-001`. This is a frozen review protocol, **not a record that evaluation already ran**. Root supplies run path and implementing code identity to an independent reviewer after actual execution.

## Evaluation layers and claims

1. **Arithmetic/reproducibility**: original CSV, exact transformation, folds, saved parameters, predictions and metrics agree; no extra fits during verification.
2. **Research continuity**: observations precede and are explicitly cited by plan revision; actual next action follows conditions and budget; replay/reopen changes no prior results or expenditure.
3. **Domain validity**: field semantics are source-backed; limitations about missing batch/specimen/laboratory IDs and data coverage remain visible. No qualified concrete-materials reviewer is present. Expert review of engineering use, causal interpretations and external validity remains **unfulfilled**, not implicitly delegated to an LLM.
4. **Autonomous-runtime evidence**: separately count developer-agent activity, operator-authored project plans, native Host runtime sends and tool computations. Absence of model API calls cannot be reported as a real standalone autonomous LLM run. Unknown developer model costs/tokens remain unknown, not zero.

## Fixed evaluator responsibilities

Before first run, archive/hash the baseline protocol, data-source manifest, evaluation checklist and candidate scope. The candidate has no write access to evaluator, hidden tasks/labels, ledger, security policy or promotion control. An Agent reviewing a mutable shared workspace is useful independence of judgment but **not security isolation**. G4 sealed-evaluation acceptance requires later actual OS/workspace isolation; this G1 exercise cannot certify it.

| Check | Required evidence / rejection condition |
|---|---|
| Provenance | Verify current source files against recorded SHA-256s; preserve author, DOI, CC BY 4.0 and original copyright/citation notice. Capture timestamps do not independently prove preregistration order; retain before-fit protocol commit or receipt. |
| Input preservation | All 1,030 rows, nine numeric tokens and order preserved; added source-row/signature fields independently recomputed with Decimal. 427 signatures, 246 singleton signatures and 25 extra exact duplicates must be disclosed if current source hashes match. |
| Group split | Same declared signature never appears in both training and held-out portion of one fold; every original complete row evaluated exactly once. Derived signatures are not verified experimental batches. |
| Preprocessing | Recompute fold means and population SD from training rows only. Do not fit StandardScaler in evaluator. Reject target/group/provenance columns in model input or normalization using held-out rows. |
| Prediction reconstruction | Rebuild all OOF from original numeric inputs plus saved scaler mean/scale, Ridge coefficients and intercept; candidate only applies `math.log1p(age)` before fold scaling. Compare with explicit absolute/relative float tolerance (e.g. 1e-9 MPa absolute, with all max discrepancies reported); reject missing parameters or mismatched coverage. |
| Metrics | Independently recompute pooled row-weighted MAE and corresponding training-fold target-mean MAE. Also report fold metrics, group-equal MAE, all local improvements/worsenings, negative predictions and extrema. Mean of fold MAEs is not automatically pooled MAE. |
| Parent/child identity | Exact same project/source/target/unit; full row sets, grouping, fold IDs, train/test memberships and reference predictions. Reject rather than compare an intersection if any differ. Only input-basis change is allowed. |
| Feedback chronology | Baseline and diagnostics must exist before plan v2, with concrete action IDs/hash refs and changed rationale/next step. A prewritten historical answer does not count as newly observed evidence. |
| Budget | Reconcile native attempted/completed scaler and Ridge events, reserved/unknown events, source reads, local calls and model sends. Preserve failed attempts and unresolved unknowns. Candidate binding retains 10 already spent and cannot reset the 20-fit allowance. |
| Restart/idempotency | Independent reviewer opens original project/manager and saved requests; replay exact successful IDs with estimator execution patched to fail if called. Require unchanged full project state, artifact bytes and all counters. Do not fake continuation by recreating a project. |
| Handover | Reviewer locates question, current plan, failures, evidence, remaining budget and precise next eligible action/wait from files and original runtime, without relying on conversation summary. Record actual commands and exit codes. |

## Metrics and interpretation

For N same-fold OOF pairs, report `MAE = sum(abs(y_i - pred_i))/N`; parent/child delta is `MAE_child - MAE_parent`. Lower pooled MAE can coexist with worsened groups or negative strengths. A candidate better than the fold-mean reference is not automatically better than its parent. Training mean is a transparent reference, not the MAE-optimal constant. Report group-equal results separately and do not treat rows or 427 signatures as certified independent repetitions.

If a saved permutation control is used, preserve its exact seed/permutation count/fold restrictions and independently recompute all permutation MAEs without fits. Its rank is conditional on the saved prediction/target matching scheme; no causal or population-significance claim follows.

## Development vs held-out evaluation

All five current public study families and their existing outcomes are already visible in repository docs. They can support reproduction and explicit transfer experiments, **not sealed unseen-task claims**. For G2/G3 later compare fixed/single/fixed-multi/dynamic methods under identical task/model/tool/budget conditions, with adverse and unknown-cost cases retained. Before G4/G5, select and seal separate task families/query sets under the evaluator's ownership; record policy and evaluator hashes before candidate generation. Do not relabel another split of an already inspected study as a truly unseen domain or independent laboratory validation.

G1 passes only when at least two actual meaningful research rounds, an observation-driven plan change, traceability and independent handover exist. A precise evidence-based wait is a valid stop but does **not** replace the two-round Gate: if the first round is invalid and no meaningful second round occurs, G1 remains unpassed. A second round may gather needed evidence or perform a justified zero-fit saved-result check before entering wait, provided the observed progress and revision are real. Code tests alone, generated prose, count of agents, or a historical number copied into a new report cannot satisfy those gates. Domain scientific validation, G2 collaboration benefit, G3 transfer benefit and G4 RSI remain separate unpassed claims.
