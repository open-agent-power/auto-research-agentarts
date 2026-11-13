# Separate pinned historical environment: group/split reproduction

A new environment at `/workspace/work/g6-frozen-reproduction-20261113-01/venv` reproduced **all group IDs and saved GroupKFold memberships on the three complete real inputs**, using the historical numerical versions. It does not change the earlier clean1.9 failure, refit models or establish full research/G6 reproduction.

## Exact purpose and source

This is a **separate historical-purpose venv**, created without system-site-packages. The existing clean1.9 environment was not downgraded. Its installed reviewed G4 adapter and all original failed-check/diagnostic manifests remain unchanged.

The copied [requirements-reproduction.lock](../g1-local/requirements-reproduction.lock) was installed with all **18 exact observed pins**, from official `https://pypi.org/simple`, with TLS/proxy trust retained and binary wheels only. No old environment or lock file was edited. Key versions:

| Dependency | Historical environment |
|---|---|
| NumPy | 2.5.4 |
| SciPy | 1.17.0 |
| scikit-learn | 1.8.0 |
| h5py | 3.16.0 |
| reportlab | 4.4.9 |
| matplotlib | 3.10.8 |
| pypdf | 6.21.4 |

Full installed inventory is [frozen-reproduction-versions.json](frozen-reproduction-versions.json), **21 distributions** including product/pip and the additionally resolved tzdata2026.6. The original observed-pins file was not a complete historical transitive closure; this actual resolved inventory is recorded without pretending the extra distribution was previously frozen.

Product was installed `--no-index --no-deps` from the original **0ceb2742825a9e95b373260fb39950fcbb48af1b** snapshot wheel, SHA256 `3b454d45ed7b37166cdcc74544e28e4b053c190b61cca0e305394abf2e5262c1`. The installed `ridge_validation_adapter.py` hash matches original `5c689576add16d5bd28cdf5c43a5c4599afb257a12f6b239018dcabcb0501090` and its origin is inside the new venv. This source intentionally predates the optimized helper and newer dependency-identity guard. It is for historical checks, not production promotion or new capabilities.

## Actual zero-fit verification

The script copied only the G4 frozen label-array inputs, baseline evaluation and manifest. All input SHA values match frozen payload hashes. It verified the exact installed original inline grouping expression (`dict.fromkeys`, then `list.index`) and reproduced that expression separately; the old0ceb module has **no later `encode_groups` helper**. It did not invoke the original CV execution method, which would fit models.

| Complete dataset | Rows / groups | Every first-occurrence ID equals frozen VM original | Every saved five-fold membership equals1.8 original |
|---|---:|---|---|
| Concrete | 1,030 / 427 | Yes | Yes |
| Real Estate | 414 / 259 | Yes | Yes |
| Slump | 103 / 103 | Yes | Yes |

The memberships were actually recomputed by installed **GroupKFold1.8.0** over the full group-ID arrays, with no fit or model construction/execution. All1547 row memberships and frozen input identities are retained in raw `compatibility.json`; ID dtype was checked against the original baseline record. Train/test group sets were checked disjoint for every fold.

Ridge and StandardScaler fit methods were blocked; zero fit attempts occurred. Product model/API calls and socket attempts were0. No old manager was constructed, budget/lineage reset, raw prediction overwritten, target result recomputed or original model coefficient refitted. All **292 historical study files** still match the G4 prefreeze inventory. This check is environment/data-split compatibility, not prediction/model/metric reproduction.

## Installation and preservation evidence

All seven commands exited0: new venv, exact-pin install, historical wheel install, `pip check`, `pip freeze`, product CLI help and complete-array compatibility. `pip check` reported no broken requirements. Raw pip resolver/download report, sanitized logs, full versions, lock/wheel/module/script/input hashes and manifest are in `/workspace/work/g6-frozen-reproduction-20261113-01/`; [frozen-reproduction.json](frozen-reproduction.json) binds the artifacts.

The prior clean environment remains **NumPy2.5.4 / SciPy1.18.1 / scikit-learn1.9.1**, with approved G4 adapter hash `ec965e31c7b148c24f11910d93ecc03e474504333548156a23575a39cf269711`. Its earlier Concrete808/RE252 fold differences are still strict failures, not rewritten passes. The new historical environment demonstrates the value of pinning; it does not establish cross-version compatibility.

Dependency downloads used the network. Product inference/API calls were0; infrastructure/development-token/currency costs remain unknown. No Docker/cgroup/AgentArts/full-G6 acceptance is inferred. A later saved-coefficient arithmetic check could be performed read-only on copies; **it has not been run in this environment**.

Entry point for a different new scratch path:

```sh
python scripts/verify_frozen_reproduction.py --output /workspace/work/g6-frozen-reproduction-new-attempt
```

The script refuses existing output and retains installation/check failures. It does not mutate the observed lock or substitute dependency versions to obtain success.
