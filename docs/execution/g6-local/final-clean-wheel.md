# Reviewed G4 wheel: clean installation and cross-version split finding

The reviewed G4 source checkpoint **`03f90a31f187a156cfa156fee7c0d659fcc3d5c4`** was built from exact Git objects, installed into the existing clean venv without downloading/reinstalling dependencies, and passed installed component/read-only/report smoke. Its group encoder reproduces all original IDs on three complete inputs. **Clean scikit-learn 1.9.1 does not reproduce the saved 1.8.0 fold partitions on Concrete or Real Estate.** The strict compatibility check failed and remains visible; Slump's folds match.

## Fixed source and package identity

- Capture used `git ls-tree` / `git show` at the full checkpoint, not mutable main or a working-tree glob. All **175** tracked source/build input files were copied into `/workspace/work/g6-final-g4-clean-20261113-01/source/` and hashed.
- Approved `ridge_validation_adapter.py` SHA256: `ec965e31c7b148c24f11910d93ecc03e474504333548156a23575a39cf269711`.
- Wheel SHA256: `0c75d7e05e40dadaf4a49fa73ba9071d5be75f5e2abf00fee6af3ef1186c7609`, **1,186,582 bytes**.
- Wheel: `/workspace/work/g6-final-g4-clean-20261113-01/source/dist/agentarts_autoresearch-0.1.0-py3-none-any.whl`.
- All **172** package source/resource files match both the captured checkpoint and actual installed bytes; archive CRC passed. Six resources were also read through the installed package/native HTTP paths.
- New untracked G5 retrieval/scheduling modules were explicitly absent from both archive and installed package. This checkpoint must not be presented as containing G5 integration.

The existing clean venv at `/workspace/work/g6-clean-20261113-01/venv` has `include-system-site-packages = false`. Installation used `--no-index --no-deps --force-reinstall`; non-product dependency inventories before/after are identical and `pip check` passed. CLI/module help passed. Actual installed module origin is the clean venv's `lib/python3.12/site-packages/autoresearch/ridge_validation_adapter.py`; it matches the reviewed adapter hash, independently of main's subsequent edits.

## Complete-array zero-fit compatibility

Inputs were copied read-only from the actual G4 VM baseline/evaluation/manifest. Each of the three input-file SHA256 values matches its frozen `baseline-manifest.json` payload hash. The diagnostic ran **installed native `encode_groups`** on every label tuple, compared all IDs with both the original VM baseline and an independent first-occurrence mapping, then computed only GroupKFold memberships using clean dependencies. No model fitting was attempted; Ridge/StandardScaler fit methods were blocked.

| Complete dataset | Rows / groups | All group IDs equal | Saved 1.8.0 fold memberships equal in 1.9.1 | Rows with different fold IDs | Same partitions ignoring fold labels |
|---|---:|---|---|---:|---|
| Concrete | 1,030 / 427 | Yes | **No** | **808** | **No** |
| Real Estate | 414 / 259 | Yes | **No** | **252** | **No** |
| Slump | 103 / 103 | Yes | Yes | 0 | Yes |

Actual clean versions: NumPy **2.5.4**, scikit-learn **1.9.1**. Frozen research versions: NumPy **2.5.4**, scikit-learn **1.8.0**. Thus this is an observed splitter/dependency compatibility limit, not an encoder ID change, and the first two differences are not merely fold renumbering. No saved split was discarded, relabeled, retuned or changed to make the check pass. No dependency was downgraded. All exact current/saved arrays and mismatch row indices remain in `followup-split-diagnosis/compatibility.json`.

The first strict check exited **1** at the fold-equality assertion. Its source, log and `initial-failure.json` were preserved. A separate diagnostic completed all three arrays and reported false/true results; diagnostic completion does **not** turn the strict compatibility failure into a pass. This does not refit/reproduce original model coefficients, predictions or research metrics.

## Independent component smoke and preservation

The fold mismatch does not prevent reading existing saved state. On a scratch copy only, installed native read-only binding passed at state version33; eight GETs returned the expected project/resources/four report files, and POST was rejected with405. The saved report dictionary rendered to a readable **28-page** PDF without recollecting/recomputing the research. No full-page visual review is claimed. All16 copied project files remained unchanged.

All **292 original study files** matched the G4 prefreeze integrity inventory after the work. Earlier clean-install raw results, preserved HTML-expectation failure, follow-up receipts and manifests remain intact. Main was neither committed nor reset. Exact snapshot/package/install/component/diagnostic identities and raw locations are in [final-clean-wheel.json](final-clean-wheel.json).

Program model/API calls and estimator fits: **0**. Dependency downloads in this final replacement step: **0**. Development tokens/infrastructure currency remain unknown. The native helper was the approved production code; no future/unregistered candidate was imported.

## Release implication

Package/build/install/component behavior is verified for this checkpoint, and group-ID compatibility passed. **Historical split reproducibility across the broad supported dependency range did not pass.** Reproducing the old research requires its exact pinned numerical environment or explicit immutable saved splits with a separately reviewed protocol. Do not silently resume/recompute an old study under 1.9.1 and call it the same validation.

A final clean-install claim must retain this distinction. This wheel still does not demonstrate full G6, AgentArts runtime, Docker controls, G5 integration or rerun scientific validity. A later source checkpoint needs its own package provenance; this receipt remains bound to03f90a3.
