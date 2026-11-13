# Saved Ridge model arithmetic: predeclared protocol

Status: implementation and hand fixtures only; real arithmetic awaits root code freeze and independent review. This is a new read-only host verifier, not another research action or a change to the original G1/G3 reports.

## Exact evidence and scope

The immutable input is `runs/sprint-005-delivery/native-cpu-reproduction-evidence.zip`, 77,407,847 bytes, SHA-256 `e320404532fe80fd085ec1dbe07cf6e1abda6d8212a00f8295baa3c9371a1a58`. Its `archive-manifest.json` SHA-256 is `6c35932e8a9170c868b89e198479b4c7b52670b366720bda39ee6e9ebf40f1e1`. Read captured source packets, SQLite records and CV artifacts directly from this manifested archive; do not load original product code or fall back to original live case/source data. SQLite payloads are deserialized into an in-memory database with query-only access. Source declarations are data, never instructions or proof of provenance/licence facts.

Expected inventory is five grouped-CV results and 25 saved fold models: Concrete raw/log1p-age, each 1,030 rows × 8 inputs; Real Estate raw/log1p-house-age, each 414 × 6; Slump raw, 103 × 7. Total held-out row predictions: 2,991. No exclusions are expected. Compare typed source/spec echoes and canonical fingerprints, original raw CSV/spec bytes, project/action/envelope/request/source identities, original frozen design and resource parent versions, method parameters and the already completed fit-event lineage. The CV predecessor is its original quality action; the raw-to-log1p CV relationship is the design resource parent version, not that quality predecessor.

## Independent formula

Inputs come exclusively from the embedded captured CSV: strict UTF-8 (optional BOM), declared delimiter/missing tokens, logical records counted after the header, and physical CSV line-end locators. Keep declared feature order and exact string group tuples. Recreate complete-case exclusions from source cells and compare them to the saved exclusion list.

For each held-out row and saved fold:

1. Use original numeric inputs directly. Only explicitly selected `training.input_transforms={column: "log1p"}` is supported, applied with standard-library `math.log1p` and domain x > −1. No cubic basis or implicit transformation is supported.
2. Standardize each value using the saved fold's `scaler_mean` and strictly positive `scaler_scale`: z[j] = (mapped_x[j] − saved_mean[j]) / saved_scale[j].
3. Compute `math.fsum(z[j] * saved_coefficient[j]) + saved_intercept` using independent formula code. Saved predictions are read only as comparison outputs after reconstruction; they are never reconstruction inputs.
4. Independently compute the reference as `math.fsum(original_training_targets) / n_train`. Recompute pooled candidate/reference MAE and the saved relative MAE improvement from reconstructed predictions and original targets.

Saved scaler statistics and coefficients are used unchanged; this does not re-estimate them, establish coefficient optimality, or demonstrate retraining equivalence. Vector dimensions, finite scalars, positive scales and exact Ridge configuration are checked: alpha 1.0, fit_intercept true, solver auto, tol 0.0001, copy_X true, max_iter/random_state null, positive false.

## Predeclared acceptance limits

Absolute tolerance is **1e-10** and relative tolerance **1e-12**, fixed before any real reconstruction. Each arithmetic comparison passes only when `abs(actual − saved) <= max(1e-10, 1e-12 * max(abs(actual), abs(saved)))`. Apply the same rule to predictions, training-target reference means, pooled MAE and relative improvement. Record every actual value, saved value, signed/absolute difference, applied numerical limit and pass flag. A failure retains the original evidence and fails this check; do not widen limits after seeing results. Report any unsuitable numerical scale to root.

Source row IDs, original observed targets, physical locators, groups, fold membership, hyperparameters and hash/identity links require exact agreement, not numerical tolerance. Each fold must have unique sorted train/test IDs, disjoint train/test sets whose union is all complete records, and disjoint source-declared groups. Every complete record must be tested exactly once across the saved folds. Raw and candidate versions retain the same declared source, group columns and saved partition. This verifies stored partition integrity, not a fresh splitter execution or a proof of real-world group independence.

## Outputs and guards

Validate the exact ZIP/manifest and derive protected locations before creating an output directory. Reject output paths using symlinks or `..`, or overlapping in either direction with the archive, any frozen protected tree/file, either native case outer root, or the repository's source/scripts/docs/frontend and related source trees. Invalid preflight paths create no output. Otherwise write a fresh output directory only. Emit all 2,991 rows in five JSONL files, five summaries with per-fold maximum errors and actual limits, full metrics, all negative-prediction row IDs, original source/model hashes and design/training identities, plus before/after protection and artifact manifests. Structural or arithmetic failures remain visible. No sampled subset substitutes for complete row coverage.

Deny imports of the product, NumPy/SciPy/scikit-learn, estimator/joblib/model API packages, and guard socket calls. Consequently original adapter/mapper calls, Ridge fit/predict, scaler fit/transform and model transport are unavailable. Only standard-library arithmetic and read-only archive/SQLite parsing run; product or captured source code is never executed. New fit/predict-via-estimator/model/API/socket counts must be zero. This guard is a trusted-host verification boundary, not OS isolation.

Hash the original ZIP before/after and compare all 494 protected old/native files to the archive's original identities, including complete recorded tree inventories. Never write old source packets, cases, SQLite databases, budgets, controls or published reports. Historical 50 estimator attempts remain historical usage, separate from zero new fit calls. Record host I/O/arithmetic work honestly; zero product API is not zero CPU cost.

## Initial engineering validation

Before root freeze, run only small hand-computed fixtures: direct two-feature predictions including a negative output; one selected log1p input; finite/shape/positive-scale/log-domain rejection; exact tolerance boundaries; duplicate JSON rejection; blocked product import; and a complete small saved-OOF fixture exercising source parsing, fold coverage/reference/MAE and failure retention. Pure path preflights reject nested old-case/source/archive paths and parent traversal, allow an unrelated fresh scratch target, and create none of those directories. These fixtures do not reconstruct any of the 2,991 real predictions. After review, root fixes the script/protocol commit and authorizes the single real saved-arithmetic pass separately. This result, if it passes, remains saved-parameter arithmetic verification, not scientific refit reproduction or complete G6.
