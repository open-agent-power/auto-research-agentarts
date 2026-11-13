# First research task — Concrete cloud reproduction

Task: `P0-CONCRETE-CLOUD-001`. Scope: G1 candidate, **not authorization to bypass G0**. Source and license proof: [research-data-selection.md](research-data-selection.md). Evaluation: [evaluation-protocol.md](evaluation-protocol.md).

## Question, hypotheses and scope

For the 1,030 published laboratory mixture/age records, how does a fixed additive linear Ridge predict compressive strength when entire ingredient signatures are held out? What adverse local results justify changing the next research plan? If saved diagnostics support it, does the sole `age → log1p(age)` expression candidate improve same-fold error while retaining local failures?

- H1: the fixed raw-eight-input baseline has lower pooled held-out-signature MAE than its training-fold target-mean reference.
- H2: some residual pattern is compatible with inadequate additive linear age representation; a fixed log1p-age candidate changes the same-fold saved MAE relative to the explicit parent. This is an expression comparison, not causal identification of an age law.
- Competing explanation: unrecorded specimen/batch/laboratory conditions, duplicates, unequal groups, restricted mixture coverage or other nonlinearities explain errors; aggregate gain can coexist with negative predictions and worsened groups.
- This reproduction has already known historical outcomes in the repository. It validates current execution/evidence/continuity and can retain a negative result, but cannot establish new autonomous scientific discovery, out-of-distribution validity, or model/policy improvement on an unseen task.

## Field mapping and immutable inputs

| Original field | Project name | Role and unit |
|---|---|---|
| Cement | `cement` | Input, kg/m³ |
| Blast Furnace Slag | `blast_furnace_slag` | Input, kg/m³; retain noninteger original tokens despite UI type label |
| Fly Ash | `fly_ash` | Input, kg/m³ |
| Water | `water` | Input, kg/m³ |
| Superplasticizer | `superplasticizer` | Input, kg/m³ |
| Coarse Aggregate | `coarse_aggregate` | Input, kg/m³ |
| Fine Aggregate | `fine_aggregate` | Input, kg/m³ |
| Age | `age` | Input, day |
| Concrete compressive strength | `strength` | Target, MPa, raw/not scaled per original readme |
| Derived | `source_row` | One-based original row; provenance only, never training input |
| Derived | `mixture_signature` | First-appearance ID of exact Decimal tuple of seven ingredient values; grouping only |

Preserve all raw bytes and SHA-256s. Derivative adds the two metadata fields and renames headers; all nine numeric tokens, rows and their order remain unchanged. Store mapping and conversion receipt. Do not round, deduplicate, impute, remove zero ingredient values, normalize target, or equate signatures with true batches. Missing/nonfinite data or source drift causes a precise wait and protocol amendment rather than silent exclusion.

## Freeze before first fit

1. After G0 review permits G1, create a **new** ignored cloud run workspace, e.g. `runs/cloud-concrete-20261112/manager`. Do not reconstruct historical project IDs, budgets or lost artifacts.
2. Freeze source manifest, this protocol, baseline resource v1, code identity and dependency versions. Record the known-outcome status above.
3. Set cumulative allowance initially to **6 local tools, 20 estimator fits total, 1 project-source extraction, 0 model/API sends**. These are a bounded Agent choice for a new project, not reset/extension of any old allowance. No second candidate, parameter search or extra fit without a separate decision. Scaler and Ridge each consume one fit.
4. Register/read the original readme and official field/license snapshot through the existing evidence path. Registration does not mean read/extracted, and source capture does not itself establish domain approval.
5. Save plan v1: quality check → fixed grouped baseline → inspect all saved errors → revise from actual observations, or stop on invalid assumptions.

## Round 1: actual computation

Use `data.tabular-quality-audit`, then the existing resource `examples/research-designs/concrete-mixture-transfer.json` (`group_cv`, optional zero-fit saved negative control) and `training={feature_columns:[the eight mapped inputs], split_group_columns:["mixture_signature"], fit_limit:20}`. Run deterministic `GroupKFold(5)`, per-fold `StandardScaler`, `Ridge(alpha=1, fit_intercept=True)`. This costs 5 scaler + 5 Ridge fits, stores all OOF predictions, coefficients, fold memberships and reference predictions. No random CV rerun or target clipping.

Use `data.saved-oof-group-diagnostics` to inspect existing results (1 tool, 0 fits). Offline `saved_oof_diagnostics.inspect_saved_oof(..., columns=("age",), within_group_column="age")` can expose within-signature adjacent-age differences while preserving exact CV identity. Any offline output must be labeled derived arithmetic with original action/artifact refs, not a native method observation unless executed through the registered adapter.

## Feedback branch and Round 2

- If baseline is invalid, has incomplete identity/coverage, or observations cannot support the candidate: save plan v2 with those action/evidence refs, retain the failure, and enter a precise wait. Do not force an improvement experiment to satisfy a checklist.
- If the actual saved feedback warrants the predeclared expression comparison: save plan v2 citing baseline and diagnostic action IDs, explicitly state why `log1p(age)` is worth the remaining fixed experiment, bind `examples/research-designs/concrete-mixture-transfer-v2.json` with identical feature order, signatures, target, five folds and cumulative `fit_limit:20`, plus `input_transforms={"age":"log1p"}`. Execute one grouped CV (10 fits), compare strict parent/child full coverage, preserve all worsened rows/groups and negative values. Historical results must not be inserted as fresh observations.
- A zero-fit saved permutation control is optional within the 6-tool cap; it is a conditional saved-prediction check, not an independent-sample significance test. It must not substitute for parent/child comparison or external validation.
- Save final plan and explicit stop/wait. No automatic promotion, causal conclusion or engineering deployment.

## Existing reusable entry points

- Input capture and source-bound schema: `src/autoresearch/tabular_quality_adapter.py:174`, `scripts/run_research_project.py prepare-source/create`.
- Native manager intake with uploaded bytes: `LocalWorkbench.create` at `src/autoresearch/local_workbench.py:303`; CLI is not a generic table-runner replacement.
- Design binding and cumulative fit preservation: `src/autoresearch/project_design.py:85`.
- Fixed actual fit path and saved models: `src/autoresearch/ridge_validation_adapter.py:104`.
- Controller selection/action receipts: `ProjectController.selection_context/advance`; use unique saved request IDs and replay them verbatim after interruption.
- Plan v1/v2: `ResearchProject.save_plan` at `src/autoresearch/research_project.py:282` (exact fields `question`, `basis`, `steps`, `expected_feedback`). These are operator/Agent-authored plans; do not label as a standalone LLM-runtime call.
- Strict saved comparison: `src/autoresearch/feature_comparison.py:42`; standalone saved audit: `scripts/inspect_saved_oof.py`.
- Keep the normal workbench/report/export path so the topic can be reopened, rather than emitting only a one-off analysis report.

## Suggested commands after G0

```sh
python scripts/run_research_project.py prepare-source --method data.tabular-quality-audit --input runs/cloud-concrete-20261112/inputs --output runs/cloud-concrete-20261112/source.json
python scripts/run_research_project.py create --workspace runs/cloud-concrete-20261112/project --source runs/cloud-concrete-20261112/source.json --goal 'Concrete held-out mixture-signature reproduction' --budget-ref cloud-P0-CONCRETE-001 --max-tool-calls 6 --method data.tabular-quality-audit
python scripts/run_research_project.py status --workspace runs/cloud-concrete-20261112/project
python scripts/serve_local_workbench.py --help
python scripts/inspect_saved_oof.py --help
```

The first two commands require the actual derived CSV/spec and successful Gate review. Bind the design using the native `project_design.bind` API or manager HTTP endpoint before fits. `run_tabular_research.py` is a historical task-specific continuation with required old artifacts and must **not** be used for this new cloud task. Root owns the executable runner and exact API integration; this task specifies behavior without inventing a nonexistent all-in-one command.

## Minimum deliverables

Raw originals/license notice and hashes; conversion/row/signature mapping; baseline and candidate definitions; plan v1/v2/diff and actual reasons; method eligibility and cost records; actual actions/observations/full OOF/models/logs; complete bad-result table; independent arithmetic audit; report and reproduction bundle; another agent's read-only reopen/replay receipt. A no-benefit or wait outcome is valid when evidence justifies it, but G1 still requires at least two meaningful rounds and an observation-driven revision; stopping after one invalid round leaves G1 unpassed. A static report with fabricated model activity is not.

For downstream use, an exact-token derivative CSV/spec and conversion receipt have been prepared under `/workspace/work/g0-data-research/inputs/` and `/workspace/work/g0-data-research/conversion-receipt.json`. This is input preparation only (0 fits, 0 model sends, 0 native research actions), not G1 execution. Derived CSV SHA-256 is `768a123975d7f56ddaef8f2965594614aa7a015b2719d545266e4965bd5b25aa`; spec SHA-256 is `6d0859af90ce37c5b02842702c585164da15d22b2d1663ccd56f87de0263ba70`.
