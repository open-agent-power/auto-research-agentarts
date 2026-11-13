# G3-L independent method-transfer evaluation protocol

Status: protocol prepared before target outcomes; not a G3 benefit claim. Source tree at preparation: `5c8dff5`. Runs use trusted local allowlisted native execution under the user's local continuation decision; the original Docker isolation gate remains blocked. No product API/model sends; old Concrete project and its exhausted 20-fit ledger remain unchanged. Root freezes this protocol, target data manifests/configuration and evaluator hash before target fitting.

## Question and predeclared comparisons

Source experience is the actual cloud Concrete child `action-d093cfe1b49ae1365c9126ade64dd0b5` paired with parent `action-3a4d3c93d9dae8a943a22e7757e03b8b`, read from the original cloud workspace. It is historical context for targets, never a target observation. Native export must include the paired result, both artifacts, original source/method/evaluator/code identities and adverse results. Do not reuse the repository's older Concrete method-card numbers or old project IDs.

1. **Real Estate, 414 rows:** fixed raw-feature grouped Ridge baseline, then at most the single predeclared selected-column `log1p` house-age candidate if semantic/execution conditions permit. Source age is days; target house age is years. `log1p(years)` and `log1p(days)` are different representations with different effective regularization; no age-unit or coefficient/performance transfer is implied. Freeze target feature names, grouping rule and units from published documentation before fitting; no target clipping, silently added features, transform search or revised split after outcomes.
2. **Slump, 103 rows:** fixed native tabular baseline when valid; no age field exists. The age-transform candidate must be ineligible by target semantics. Preserve the explicit rejection/wait and do not synthesize an age feature. Its concrete source experience may still be retained as a warning about aggregate/local error tradeoffs, not as permission to apply an age transform.
3. Importing a case, retrieving it, or reporting its numbers does not prove decision quality or benefit. These two targeted transfer cases can yield a local numerical benefit, no benefit or negative transfer; they do not establish cross-domain RSI, unseen-task statistical significance or a causal effect of memory. Without a no-memory decision arm, do not claim that memory caused a numerical improvement.

Model/agent API arms are absent. Each target ceiling is 6 local actions / 20 estimator attempts / 1 source read / 0 model sends; root freezes these or tighter numbers in each config. Two targets together cannot exceed 40 estimator attempts. Two five-fold designs cost 20 combined scaler/Ridge attempts; one five-fold baseline costs 10. Experience import, arithmetic verification and report reading do not fit. No execution is authorized by this document alone.

## C05 existing native experience contract

Source export (trusted host; fresh memory store outside the Concrete source):

```python
from autoresearch.project_experience import ProjectExperienceMemory, derive_project_observation
child = "action-d093cfe1b49ae1365c9126ade64dd0b5"
parent = "action-3a4d3c93d9dae8a943a22e7757e03b8b"
derived = derive_project_observation(source_workspace, child, parent_action_id=parent)
memory = ProjectExperienceMemory(new_memory_root)
memory.import_project(source_workspace, child, parent_action_id=parent)
bundle = memory.export_case(derived["scope"], derived["entries"][0]["id"],
    case_id="cloud-concrete-age-tradeoff", version=1,
    method_card=card, limitations=limitations)
```

`project_experience.py:210` rechecks source OOF and exact parent; `:335` imports into new memory and exports. No source fit or source migration is needed. `bundle` exact keys: `schema_version="project-experience-bundle-v1",id,version,record,method_card,limitations,source_inclusion_status="active_at_export",scientific_validation=False` (`:289`). Keep original canonical bytes/hash; 4 MiB bound. A new memory database is not an extension of the source project's resource ledger.

Card exact keys (`research_recipe.py:71`): `schema_version="research-method-card-v1",id,version,question,rationale,scope_match,method_refs,applicability,evaluation,feedback_branches,sources`. Bind `scope_match` exactly to source `record.payload.source_scope` domain/contract and `method_refs=[{method_id:record.payload.method_id,evaluation_ref:record.payload.evaluation_ref}]`; for this source these are data/tabular-quality-v1 and data.ridge-group-validation/ridge-validation-group_cv-v1. `applicability` is `{requires:[...],not_applicable:[...],uncertain:[...]}`. Each branch is `{id,observed,suggested_next,evidence_required:[...]}`; each source is `{id,url,locator,note}`. Text is advisory, not executable permission.

Template wording: question “When does one fixed age mapping justify comparison under a target's own units and grouping?”; rationale cites the **actual new source bundle**: MAE 8.383388056181742→5.702072514528065 MPa, 313 rows/129 groups worsened, negative predictions 0→1; source age days. Requires target age semantic/unit confirmation, explicit parent, matching target rows/groups/folds/reference and remaining native budget. Not applicable to a target without age, borrowing Concrete's error/units/thresholds, or equating derived signatures with independent batches. Uncertain: target transfer benefit and validity outside saved evaluation. Branch directs inspect target-native adverse results and reject/wait on missing semantics. Cite both actual source action URNs and UCI source references; never the older repository case IDs.

Target import:

```python
raw = canonical_bundle_bytes  # the exact previously exported immutable bytes
project.import_experience(request_id=..., expected_state_version=current_version,
                          bundle=raw, reason="Historical analogy; not target evidence")
# Or the manager wrapper with exactly:
manager.import_experience({"request_id":...,"project_id":...,"expected_state_version":...,
    "bundle_base64":base64.b64encode(raw).decode(),"reason":...})
```

Native source: `research_project.py:272`, `local_workbench.py:449`, `project_experience_binding.py:64`. `manager.experiences()` and controller `selection_context().experience` expose a separate case field. Engineering association checks method/evaluator/domain/contract; **it does not automatically understand that Slump lacks age or that Real Estate uses years**. Root must preserve the semantic negative-control receipt, not pretend the generic association rejects it. Source and target inclusion history are distinct; replay never silently reactivates retired records.

## Frozen verifier configuration (data only)

`scripts/verify_tabular_transfer.py --config <frozen.json> --manager <existing-root> [--project-id <id>] --output <fresh-external-directory>` (or `--project` instead). Config exact top-level keys:

- `schema_version="tabular-transfer-verifier-config-v1"`, `dataset_id` in `real-estate`/`slump`, `expected_rows` (414/103), `original_csv` absolute path, `original_sha256`, `original_columns` ordered original field names.
- `mapping`: complete ordered list of `{source,target}` original column names; preserve every numeric/input token and original row order. Metadata fields must not become model features accidentally.
- `source_row_column`, `grouping={kind:"decimal_columns"|"unique_rows",columns:[original mapped names],target_column,id_prefix,id_width}`. Decimal grouping preserves exact source equality; IDs use first-appearance order. Unique rows are grouping IDs only, not a claim of independence. Freeze one rule per dataset before execution.
- `feature_columns`, `target_column`, `target_unit`, `split_group_columns`, `candidate_transform` (only `{<one selected declared feature>:"log1p"}` or null), `expected_fit_actions` (1 or 2), `budget={local_tool_calls,fit_attempts,source_reads,model_calls:0}`.
- `experience={bundle_sha256,source_project_id,source_action_id,source_parent_action_id,source_age_unit,target_age_unit,transform_semantically_applicable}`. Concrete source action IDs above are fixed; target age unit is years for Real Estate, null for Slump. The Slump null-transform, one-fit-action condition is predeclared.

Reject extra schema keys, unknown transform values, arbitrary expressions/callables, inconsistent column binding, incorrect rows or hashes, or allowances above 6/20/1/0. The verifier binds Real Estate to the published six X1–X6 inputs, Y price target and X2 house-age-only transform; Slump binds exactly the seven ingredient inputs and 28-day strength target, excluding SLUMP/FLOW/ID from features. Configuration is a frozen declarative input, not Python/code or a means to change native budgets. A configuration amendment requires a new version/receipt before the affected experiment; don't change expected values to match results.

## Independent read-only acceptance

The independent verifier imports no product mutation API, uses SQLite `mode=ro`/`query_only`, patches `Ridge.fit` and `StandardScaler.fit` to raise, reconstructs predictions with NumPy arithmetic and checks the input tree is unchanged. No fitting, parameter solving or model/provider calls. Preserve all failures in a fresh output; don't overwrite a failing receipt.

Verify raw→derived mapping, original CSV SHA/packet/spec binding, complete row and Decimal grouping identity; independently reconstruct size-balanced GroupKFold; ensure no group leakage or test overlap and exact train/test coverage. Recompute training means/scales, training target-mean references, saved coefficient predictions and Ridge stationarity residuals without fitting; compare every saved OOF value and reported MAE. Retain full rows/groups/folds, negative predictions and groups worse than reference.

For a two-design case verify explicit same-project source/target/unit parent lineage, raw-parent versus declared log1p-child only, equal row/group/fold/reference partitions and fixed model parameters, then paired pooled MAE, improved/worsened/tied rows and groups, adverse local results and predictive ranges. For Slump require only the baseline and semantic non-applicability; absence of an age candidate is a valid intended negative-control outcome, not a missing paired experiment to conceal.

Verify the immutable imported bundle bytes/origin/paired adverse summary and its separation from target observations. Generic mechanical association alone is not semantic validation. Report raw native receipts, independent arithmetic and protocol limitations separately. No minimum improvement is required to pass reproduction integrity; scientific/transfer benefit is a separate outcome.
