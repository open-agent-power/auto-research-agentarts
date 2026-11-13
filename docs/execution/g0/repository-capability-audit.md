# G0 Repository capability audit

- Audit baseline: `5d497c8ae22100953f66c3c5b54746ca87e09f01`.
- Audit scope: R01–R06 in the uploaded Master Execution Pack v2; source inspection only.
- Task owner: `repo_audit`; no production code or tests changed; no model calls, fits or old studies resumed.
- Date: 2026-11-12.
- Product scope: continuous research workbench, with a real tabular vertical slice before dynamic collaboration or RSI claims.

## Evidence grading

`S` means implementation read at the stated source location. `T` means relevant test source exists and was read; it does **not** mean it passed in this cloud environment. `R` is reserved for a fresh executed command plus retained output/artifact; the initial source review made no `R` claim; fresh post-audit runtime evidence is explicitly separated below. Case-study Markdown is historical reporting, not transferable cloud runtime evidence. Root/integration must append actual test/run evidence separately.

## Conclusions

The repository already has substantial reusable state, evidence, method and plan infrastructure. A rewrite is not justified by this audit. G1 should run a new real dataset through the existing `ResearchProject` / `ProjectController` / `LocalWorkbench` path, preserve two rounds of actual observations and plan revisions, and test recovery and independent handover. The missing G1 evidence is a new, traceable cloud execution, not absence of every necessary module.

The repository does **not** establish G2 dynamic multi-agent gains, G3 independently measured cross-project benefit, or G4 code-level self-modification. In particular, `recipe_improvement.py` consumes and assesses already-saved evidence; it is not an online research driver or a full RSI controller. Existing engineering candidate keep/revert logic must retain its narrow claim.

## R01 — Project / Run / Action / Observation

- `src/autoresearch/research_project.py:80`: `ResearchProject` owns `project.sqlite`; `_connect` and `_writer` at lines 86 and 98 implement transaction handling and a cross-process OS writer lock. `create:135` registers immutable goal/source/method/budget lineage and captures source bytes, with `project`, `actions`, and `replays` tables at lines 195–197. `status:203` derives actual and reserved usage rather than resetting counters. Evidence: **S**.
- `research_project.py:495`: `step` checks registered method, expected state version, code identity and original source; exact request replay at lines 544–547 recovers the old artifact, and identical completed computation reuse at lines 557–562 avoids another execution. It writes a running action before tool execution, reserves fits before dispatch, persists failed outcomes, and atomically publishes the completed artifact before committing state. Evidence: **S/T**; `tests/test_research_project.py:45`, `:67`, `:78`, `:89` cover restart, interrupted publication, unknown execution and integrity guards.
- `research_project.py:366`: `_commit_result` binds action ID, request hash, code hash, dataset snapshot, observations and artifact result hash. Execution status and scientific status are not conflated. `_recover:437` rejects changed artifacts and leaves execution without a saved complete result unknown; `resume:658` does not promise to rerun it. Evidence: **S/T**.
- `src/autoresearch/project_controller.py:50`: durable condition-selected parent requests. `_dispatch:313` checks frozen context/code/state and uses a saved child ID; `_advance:415` binds immutable input. Waiting/rejected/unknown states are explicit. Tests at `tests/test_project_controller.py:18`, `:62`, `:75`, `:94` cover once-only dispatch, saved child recovery, busy writers and stale choice. Evidence: **S/T**.
- Limits: this is a bounded local synchronous allowlisted execution path. It is not a Docker Worker supervisor, distributed task scheduler, general Agent Contract or a dynamic Agent DAG.

## R02 — Research plan and feedback-to-plan

- `research_project.py:282`: `save_plan` persists append-only versions with reason, request ID and state binding. Current schema is four bounded text fields (`question`, `basis`, `steps`, `expected_feedback`); it is not a fully structured hypothesis/stop-condition/task-DAG schema. It changes no tool permission and dispatches no action. Replay/conflict handling at lines 300–307. Evidence: **S**.
- `research_project.py:324`: `record_feedback` records unverified researcher statements separately from tool observations. It can bind only a saved action; it does not promote a comment to observed fact. Evidence: **S/T**, `tests/test_research_plan_proposal.py:397`.
- `src/autoresearch/research_plan_proposal.py:114`: frozen context includes saved tool feedback, available candidates, prior plan, comparisons, remaining questions and optional supplied saved materials. Prompt at line 175 asks for competing explanations and specific feedback references and distinguishes immediate from conditional work. Validation at line 229 checks context/proposal identity and supplied action references. This ensures provenance/format, not scientific correctness. Evidence: **S/T**, `tests/test_research_plan_proposal.py:136`, `:171`, `:347`.
- `src/autoresearch/host_model_selection.py:94`, `:285`, `:318`: prepare/consume/adopt separates a proposed plan from explicit plan adoption. Original context, prompt and raw response are retained. Providers are currently `claude_cli` and `delegated`, not a native Codex CLI adapter. `import_response:270` explicitly labels delegated model, inference count and cost unknown and execution unverified. Evidence: **S**.
- `src/autoresearch/local_workbench.py:1151` has a bounded continuity controller, but it does not by itself prove fresh cloud execution or unconstrained autonomous research.
- Important separation: `src/autoresearch/research_loop.py:155` uses a separate `Engine` campaign and its configure method at line 176 fixes the campaign dataset to `matbench-steels-v1`. Its reserved request/cost accounting and live-access guards are real code, but it is **not** the general `ResearchProject` tabular controller. `tabular_research.py` is a P02 SourceAssessment wrapper, also not the new tabular entry.

## R03 — Recipe / Method registry

- `src/autoresearch/method_registry.py:8`: explicit primary/follow-up registry includes CSV quality, grouped quality, numeric association, saved prediction checks, raw Ridge random/group validation and saved OOF diagnostics. `get/get_analysis:25/32` reject unsupported methods; evaluation identities at line 52 remain domain-specific. Evidence: **S**.
- `src/autoresearch/research_methods.py:30`: eligibility derives from saved source, feedback, execution state, bound design and prior result hashes. `ProjectController._selection_context:136` additionally checks budget per candidate; remaining source-read allowance is not conflated with exhausted numeric/fit allowance. Evidence: **S/T**, `tests/test_project_multi_method.py:37`, `:87`, `:107`.
- `src/autoresearch/research_recipe.py:71` validates explanatory method cards; free-text applicability is knowledge, not executable permission. `match_method_card:135` associates exact domain/contract and method/evaluator pairs with actual host candidates. `validate_recipe:197` allows a closed ordered-method policy with `on_no_match=wait`; `compile_recipe:220` selects only an eligible frozen host candidate and records skipped options. Evidence: **S**.
- Limits: Recipe currently is a bounded priority list, not arbitrary executable methods or open-ended scientific method generation. Cards' cost/requirements/branches are not a complete validated scientific eligibility system. New domain semantics need an explicit adapter and evaluator, not a new label on an old method.
- `project_design.py:56`, `:85` validates frozen raw designs and cumulative fit budget; raw modeling has 10–2048 record scope and up to 40 fit attempts. `ridge_validation_adapter.py:87` implements deterministic fixed Ridge checks, not arbitrary algorithm search. `tabular_quality_adapter.py:17` supports up to 8 MiB CSV and 50,000 mechanical-audit rows, which must not be confused with the smaller modeling bound.

## R04 — Evidence / Source / Artifact provenance

- `src/autoresearch/source_evidence_adapter.py:46`, `:187`: strict task-bound manifest, source URL/license note, SHA-256, explicit locator, contributor and open questions; original bytes are captured and hashed. Path guards at lines 110–167 reject traversal, redirected/hardlinked sources, changed bytes, excess sizes and duplicate keys. `execute:227` extracts selections without scientific approval. Evidence: **S**.
- `research_project.py:984`, `:1010`, `:1069` separates source capture/registration from source reading and charges the proper cumulative allowance. The controller will not treat merely registered bytes as read evidence. `project_knowledge` indexes extracted selections, not model reading or author confirmation. Evidence: **S/T**, `tests/test_project_controller.py:18`.
- `src/autoresearch/project_report.py:178` verifies source and every completed artifact, captures original source assets and manifests, and separates unread receipts from extracted ones. `export_report:1381` freezes report JSON/Markdown/PDF/input with hashes and checks that the project and Host ledger did not change. Evidence: **S**.
- Limits: original CSV origin/license/provenance fields remain submitter declarations in `project_report.py:209`; independent original-source and license verification is still required by G0. Report packaging is not proof that the scientific interpretations are correct. A fresh G1 reproduction bundle and clean handover are not present merely because exporters exist.

## R05 — Memory and cross-project reuse

- `src/autoresearch/research_memory.py:23`: exact SHA-bound input/evaluator/protocol scope. `derive_entries:34` creates numerically checked observations or explicitly untrusted Agent judgments. SQLite store at line 88 has source versions and hash-chained inclusion events. `_import_derived:180` does not reactivate retired observations. `recall:212` is exact-scoped, bounded and read-only. Evidence: **S/T**, `tests/test_research_memory.py:33`, `:53`, `:62`, `:87`.
- `src/autoresearch/project_experience.py:210` rechecks saved OOF artifacts; `ProjectExperienceMemory:335` derives cases from actual source study results. `project_experience_binding.py` records explicit target-project import/status history. `project_controller.py:217` adds active cases as a separate context field rather than mixing them with current-project evidence. Evidence: **S**.
- Limits: exact recall and explicit case transfer are mechanisms; similarity, imported cases or a reference in a response do not establish benefit. Need independent tasks, a frozen baseline/candidate protocol, negative-transfer analysis and actual model/behavior outcomes for G3. Existing records stay candidate/unverified where benefit is not measured.

## R06 — Recipe improvement and real RSI gap

- `src/autoresearch/recipe_improvement.py:1` explicitly says it assesses saved validation and never dispatches a model or research action. `_assess:78` reconstitutes frozen baseline/candidate decisions and tests a bounded acceptance target. At lines 174–189 keep requires baseline missing target, candidate choosing it, completed controller receipt and recorded artifact; output explicitly denies scientific benefit. Evidence: **S/T**, `tests/test_recipe_improvement.py:157`, `:177`, `:187`.
- `run_improvement_round:261` saves immutable staged input/result/effective-recipe snapshots, detects changed predecessors and supports same-ID recovery. `run_improvement_sequence:365` consumes a bounded queue of existing evidence, stops on pending/missing input and never proposes/validates/adopts online. Evidence: **S/T**, `tests/test_recipe_improvement.py:31`, `:94`, `:252`, `:323`.
- Missing for G4: real code-modifying candidate in a separate worktree, trusted external worker isolation, protected evaluator/hidden-task/budget/promotion authority, independent sealed evaluation, promotion/reject receipt with rollback and real lineage. Existing fixed Candidate hyperparameter trials and recipe keep/revert are narrower and must not be renamed full RSI. No multi-generation or held-out benefit claim is justified by this source review.

## G1 minimum viable route — reuse before extension

1. Preserve the supplied Master Pack, original public dataset, retrieval date/URL/license and field dictionary separately; create a new cloud run lineage rather than reconstructing absent local runs.
2. Use `scripts/run_research_project.py prepare-source --method data.tabular-quality-audit --input <host-owned-input-directory> --output <separate-source.json>` then `create --method data.tabular-quality-audit --source ... --workspace ... --goal ... --budget-ref ... --max-tool-calls ...`; alternatively `LocalWorkbench.create` at line 303 accepts original CSV/spec bytes and retains them for the UI. The `autoresearch` entrypoint primarily addresses older Engine campaigns.
3. Save initial plan with `ResearchProject.save_plan` or `LocalWorkbench.save_plan:393`. Include two competing explanations, evaluation protocol and stops explicitly in the existing text fields. Do not inflate schema work before the first case demands it.
4. Use `ProjectController.selection_context` / `advance` or `advance_selection`; all execution goes through the registered adapter and ledger. Record actual data-quality observations and read task-bound source excerpts. Reuse `project_design.bind` and current Ridge/numeric methods only if their semantic/input conditions fit the selected problem.
5. After actual feedback, freeze a plan context, obtain a real delegated Host proposal or an authorized runtime response, independently check it, adopt v2 and execute one justified next step or a precise wait. Any delegated output retains unverified product runtime/cost metadata; do not fabricate API/CLI receipts.
6. Export via `scripts/export_project_report.py`, add a reproduction command/environment lock and raw dataset/code/evaluator hashes, then have another agent reopen and recompute key numbers with identical inputs. Replay the same request and show no extra tool/fit charge; preserve unknown execution and negative findings.

### G1 work that may require a bounded change

- A host-written case runner/reproduction command may be needed to execute the existing interfaces repeatably and collect G1 acceptance evidence. Put reusable run examples under `examples/`, actual artifacts in ignored `runs/`; root owns contracts/persistence.
- A native Codex runtime adapter is currently absent. It can be a later explicit bounded integration; a manual/delegated valid plan already exercises the existing Host contract. Do not route arbitrary shell/code through the untrusted tool protocol to obtain autonomy.
- Additional data-cleaning, model, causal or RAG methods only after a concrete need is demonstrated, not to fill all roadmap boxes in advance.

## Recommended verification batch for root

Run once after dependency setup and retain full command/stdout/exit status:

```sh
PYTHONPATH=src:tests python -m unittest test_research_project test_project_controller test_project_multi_method test_research_plan_proposal test_research_recipe test_research_memory test_recipe_improvement test_recipe_improvement_sequence test_ridge_validation_adapter
```

These are necessary state/permission/recovery and method checks, using engineering fixtures; passing them does not satisfy the fresh real G1 research case. Report/export runtime needs its declared optional PDF dependencies. A full repository test run may be appropriate as an initial baseline, but avoid repeated historical fits or live calls without a new reason.

## Task receipt

- Task: R01–R06 / repository audit.
- Status: source audit complete; runtime verification delegated to root.
- Input: commit above + uploaded Master Pack.
- Changed files: this report and `implemented-vs-planned-matrix.csv` only.
- Commands: source reads and `rg`; no tests run by this subagent.
- Models/tools/fits dispatched by product: 0.
- Limitations: absent ignored/local historical runs were not transferred; no credentials read; no independent scientific review; no new cloud real-data execution by this audit task.
- Next: integrate fresh resource/source/runtime evidence into G0 review, then run the existing vertical slice with explicit assumptions and real observations.

## Fresh G0 Linux portability evidence (R)

After the source audit, root reported an initial Linux baseline of 1,105 tests with two errors and 18 skips. The two errors were test-environment assumptions: a Windows-only subprocess interpreter path and an undistributed external pinned CellProfiler asset. The historical failing run remains evidence; this targeted repair does not imply a complete full-suite rerun.

Changed only `tests/test_project_experience.py` and `tests/test_chemotopo_project.py`: the export subprocess now uses `sys.executable`; the pinned-asset integration test accepts `CHEMOTOPO_PINNED_PROJECT`, skips only when the unspecified legacy default is absent, and fails for an explicitly missing or empty configured path. All existing real-source metadata assertions and the underlying pinned-byte/hash validation remain unchanged. No substitute fixture was used for the real-source test and no production source changed.

Executed: `PYTHONPATH=src:tests OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 .venv/bin/python -m unittest test_project_experience test_chemotopo_project -v`. Exit 0; 16 tests, 15 passed, 1 skipped because the external real asset is absent. Log: `runs/g0-baseline/portability-regression.log`. Additional in-memory runs verified both an explicitly missing path and an explicitly empty path produce one real failure and zero skips. These checks verify portable CLI export and the missing-asset contract; they do not establish that the private real dataset was inspected, scientific validity, or cross-project transfer benefit.
