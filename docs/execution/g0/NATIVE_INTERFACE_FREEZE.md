# Native interface snapshot — G0 preparation only

Baseline: `b452bf6bd9c49dd3fa212d85e79cfc75ab4772cd` (2026-11-13 UTC). This is a source-checked snapshot of existing C01/C02/C03/C04/C07/C08 interfaces, **not** a new API, Gate approval, study execution or scientific validation. Local-first execution remains pending the user's decision. This preparation created no project, fit, product model request or source fetch; no tests were run.

Prospective case ceiling: **6 local actions / 20 estimator attempts / 1 source read / 0 product model API calls**, one local worker and `OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1`. These are ceilings, not instructions to consume them. Historical runs and resource-v2 source references are not observations from this new case; retain their separate origin and never insert them into this case's baseline feedback.

## Minimal native call order, after execution is authorized

1. Preserve original CSV, field/source documents, retrieval/license notes and hashes outside the fresh project. Select either the direct `ResearchProject` route or the `LocalWorkbench` manager route below; do not create two parallel factsources.
2. Capture input; create one project with `max_tool_calls=6`; immediately tighten its default source-read allowance from 8 to 1. Keep native model allowance at 0. Save plan v1 using the exact four fields below.
3. Read a fresh `ProjectController.selection_context()`, select the exact current quality-audit candidate, then `advance_selection` once. Re-read status and its actual artifact/observations; obtain `evidence_task()` only after a task exists.
4. Register task-bound source material, then select its native source-read candidate once. Registration is capture, not a read or verification of scientific meaning. Resolve unresolved semantics explicitly; do not manufacture confirmation.
5. Bind baseline raw design to original feature/group columns with cumulative `fit_limit=20`. Read a fresh context and select eligible `data.ridge-group-validation`; retain its actual OOF, folds, metrics, ranges and fit events.
6. Revise plan v2 only from this case's saved feedback. If actual evidence supports a fixed log1p child, bind a new resource version with explicit parent and transform dictionary, then select its eligible current candidate. Otherwise stop/wait or choose another already eligible bounded action; the prewritten alternative is not a measured finding.
7. Save limitations and failed routes, export verified report, reopen the same workspace and replay the same original request/content to verify identity and unchanged cumulative usage. Independent numerical reproduction/handover is still a later acceptance task.

## C01 — intake and plan revisions

`src/autoresearch/tabular_quality_adapter.py:24` defines **exact** input-spec keys:
`schema_version,file,dataset_label,source_url,license_note,sample_unit,group_columns,key_columns,numeric_columns,target_column,target_unit,missing_tokens,delimiter,provenance`.
Use `schema_version="tabular-quality-spec-v1"`, a single safe `.csv`/`.tsv` basename, declared column arrays, `missing_tokens` including `""`, delimiter comma/tab, and `provenance={"origin_sha256":<original SHA256>,"description":<actual transformation/origin note>}`. Target is null with null unit, or a numeric-column name with a nonempty unit (`:65`). Original-origin declarations still need external verification.

Direct capture: `tabular_quality_adapter.capture_source(input_directory)` (`:174`) reads original file plus `spec.json`; persist its canonical packet to a host-selected source path. Then `ResearchProject(workspace).create(source=packet_path, goal=..., budget_ref=..., max_tool_calls=6, method_id="data.tabular-quality-audit")` (`research_project.py:135`). Source and workspace must be separate; do not reuse an existing unrelated workspace.

Manager alternative: `LocalWorkbench(root).create(body)` (`local_workbench.py:303`), exact body keys `request_id,goal,budget_ref,max_tool_calls,input`, with `input={"file_name":...,"csv_base64":...,"spec_base64":...}` from original bytes. The manager stores original bytes plus its own project mapping; `LocalWorkbench(root)` itself creates storage (`:108`), so **do not instantiate during this preparation**.

`project.save_plan(request_id=..., expected_state_version=fresh_status["state_version"], plan=..., reason=...)` (`research_project.py:282`): exact plan keys `question,basis,steps,expected_feedback`, plain text with character limits 4000/6000/12000/4000. `basis` may be empty; other fields may not. Reason is nonempty, ≤2000 characters. Plans dispatch nothing. Manager wrapper `save_plan(body)` (`local_workbench.py:393`) additionally requires `project_id`.

## C02/C08 — design, transform and evaluation identity

`project_design.bind(project, request_id=..., expected_state_version=..., resource=..., prediction_column=None, reason=..., training=...)` (`project_design.py:85`). Raw resource **exact required keys** (`:16`, `:29`):
`schema_version,id,version,title,question,claim,alternatives,checks,sources,parent_version,change_reason`.
Use `research-design-resource-v1`, an integer version, nonempty alternatives, explicit source references and raw `checks` beginning `group_cv` or `random_cv` (a group-only case may use `["group_cv"]`). Baseline `parent_version=None`. A fixed-input child declares its actual prior resource version and optional `comparison_kind="fixed_input_basis"`; it cannot inherit nonexistent case results from a historical resource.

Baseline training: `{"feature_columns":[<original numeric names>],"split_group_columns":[<declared group names>],"fit_limit":20}`. Target must not be an input; feature and declared group columns must be disjoint. Raw scope is 10–2048 captured rows, ≥10 complete cases and ≥2 groups (`project_design.py:56`). The fit limit preserves already consumed/reserved attempts; rebinding never refunds them.

Optional child training adds **a dictionary**, e.g. `"input_transforms":{"Age":"log1p"}` for an actually present feature named Age, **not** a list, nested transform object or general expression. Only selected original feature names and value `"log1p"` are supported; it is mutually exclusive with `input_basis` (`input_basis.py:8`). Complete-case selected values must be finite and >−1 (`:35`); mapping precedes training-fold scaling. If another name is used in the actual CSV, use that exact declared name.

Group validation is fixed Ridge alpha=1 with training-fold StandardScaler and training-fold target-mean reference (`ridge_validation_adapter.py:87`). Each fold costs two attempts (scaler + Ridge); five-fold baseline + five-fold child consumes all 20. Actual fold count/eligibility/cost comes from current binding/context, not that example. Grouped fold identity, row set, target, original source and evaluation protocol must match before any parent/child comparison; reused evaluation is exploratory, not independent holdout evidence.

Manager binding route: `import_design({request_id,resource})`, then `bind_design({request_id,project_id,expected_state_version,resource_id,resource_version,prediction_column,reason,training})`; wrappers at `local_workbench.py:538`, `:544` call `research_design.py:165`, `:250`. This imports a design resource, not execution observations.

## C03 — exact candidate selection and action receipt

`ctx=ProjectController(workspace).selection_context(need="next_check")` (`project_controller.py:238`): inspect `blockers,conditions,candidates,budget,state_version,context_sha256`. Match exactly one intended method/evaluation and current parameter binding; do not select the first loosely matching name or fabricate a candidate.

Proposal has exactly (`project_selection.py:231`):
`{"schema_version":"project-selection-proposal-v1","context_sha256":ctx["context_sha256"],"provider":{"kind":"operator_assistant","label":<actual origin>},"choice":{"kind":"execute","candidate_id":candidate["id"]},"rationale":<specific reason>,"evidence_citation_ids":[<IDs actually in ctx.evidence>]}`.
`choice={"kind":"wait"}` is the alternative. Provider label is an unverified declaration, not an API/CLI/model receipt. Execute choice contains **only** kind/candidate ID, never injected method/parameters.

Call `controller.advance_selection(request_id=..., proposal=proposal, need="next_check", expected_state_version=ctx["state_version"])` (`project_controller.py:396`). Frozen candidate supplies exact method, evaluator and parameters. For numerical follow-ups these bind `based_on_action_id,based_on_result_sha256`; source reads bind `receipt_snapshot_sha256`; arbitrary overrides are rejected (`research_project.py:495`, `project_controller.py:313`). The manager `advance(body)` (`local_workbench.py:378`) accepts exactly request_id/project_id/expected_state_version/proposal.

Worker receipt—not proposal prose—establishes execution status: inspect saved parent child_request_id/status/result and child action `id,request_id,command,status,artifact,result_sha256,observations,method_instance,source_snapshot_sha256,code_identity` (`research_project.py:366`). Failed/unknown attempts remain visible and counted. No native model or delegated Host call is required for this local-first route; no claims of model autonomy follow from operator plans.

## C04 — native source request, capture and read are distinct

`project.evidence_task()` (`research_project.py:935`) returns its actual `task_ref={project_id,based_on_action_id,method_id}` and empty manifest template; `TASK_NOT_AVAILABLE` means wait, not invent a task. Manifest exact keys: `schema_version="project-evidence-bundle-v1",task_ref,contributor,sources,selections` plus optional `remaining_questions` (`source_evidence_adapter.py:46`).

Each source: `id,path,sha256,url,media_type,license_note`; paths must be safe `sources/...` paths. Each selection: `id,source_id,locator={kind,value},claim`; use exact supported coordinates from real source bytes. Claims and contributor are not scientific approval. One manifest may contain 1–8 sources and 1–32 selections, so **one read is one receipt execution**, not necessarily one source.

`project.register_evidence(request_id=..., bundle=host_bundle_directory, expected_state_version=...)` (`research_project.py:1062`) captures originals and returns `receipt_snapshot_sha256` with read_performed=False. Then choose the corresponding current `research.source-selection` candidate through the controller, or call native `read_evidence(request_id=..., receipt_snapshot_sha256=..., expected_state_version=...)` (`:1131`); do not invoke both as separate intended reads.

Optional native external lookup is **separate**: `EuropePmcSource(workspace).fetch(request_id, doi, separate_output_directory)` (`europe_pmc.py:244`), fixed DOI endpoint, 30s, 2 MiB, fixed eight-request network ledger (`:22`). It needs a completed primary action and actual evidence task; unknown network outcomes are never resent. `source_connector_bundle.build_bundle(workspace=...,request_id=...,output=...)` (`:126`) converts an existing saved response offline, then ordinary register/read applies. A 1-read limit does **not** reduce that network request limit or authorize fetching; this preparation performs neither.

## C07 — budget, persistence and reopening

Immediately after authorized create: `project.limit_evidence_budget(request_id=...,expected_limit=8,new_limit=1,expected_state_version=...,reason=...)` (`research_project.py:783`). Native create grants model_requests_allowed=0 and default evidence_read_limit=8 (`:182`); do not call model authorization, Host preparation or expand allowances. Keep the prospective 6/20/1/0 envelope explicitly in the case's local decision/lineage; native stored historical cash metadata is not a fresh spending grant.

Re-read status before each new mutation; retain request IDs and exact original arguments for replay. `ResearchProject(existing_workspace).status()` (`:203`) reopens without creating a new project; `resume(request_id=...)` (`:658`) only collects the original result and never reruns unknown execution. OS writer lock and cumulative usage are native (`:98`, `:212`). Manager reopen uses its existing root and `select({request_id,project_id})` (`local_workbench.py:364`); do not rebuild its mapping or reset budgets.

C07 currently provides local allowlisted synchronous adapters, not an independent protected Docker worker. If local-first is approved, record this narrower isolation boundary and preserve disabled arbitrary-command/model/network execution; this document does not bypass the outstanding G0 decision.

## C04/C08 — export and handover boundary

`project_report.export_report(workspace=...,output=fresh_separate_directory)` (`project_report.py:1381`) verifies completed artifacts and frozen source/context identity and exports `report.json,report.md,report.pdf,input.json,manifest.json`. Manager `export({request_id,project_id,expected_state_version})` (`local_workbench.py:1379`) persists/rechecks its manifest. Keep optional PDF dependency installation separate from research execution.

Reopen uses the original project SQLite + artifacts + source inputs + manager mapping if used, **not report JSON as an automatically resumable database**. Preserve manifests, hashes, all plan revisions, actual baseline/child feedback and failures for independent handover. Report export alone is not a reproduction bundle, numerical re-computation, clean-environment acceptance or Gate completion.
