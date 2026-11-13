# Runtime versions, replay and historical reproduction

Identical source bytes and grouping IDs did not ensure identical validation folds. With NumPy2.5.4 in both environments, clean scikit-learn1.9.1 changed **808/1030 Concrete** and **252/414 Real Estate** row fold assignments relative to saved1.8.0 results; the partitions differ even after ignoring fold numbers. Slump103/103 matched. The strict1.9 check remains failed; no input, protocol or dependency was altered to relabel that attempt successful.

| Environment / source purpose | Numerical runtime | Verified scope |
|---|---|---|
| Generic clean install, reviewed03f90a3 G4 wheel | NumPy2.5.4 / SciPy1.18.1 / sklearn1.9.1 | Installed components/HTTP/report work; group IDs match, two historical split arrays fail |
| Separate historical environment, original0ceb274 wheel | NumPy2.5.4 / SciPy1.17.0 / sklearn1.8.0 | All1547 original group IDs and saved memberships match; no model refit |
| Existing research `.venv` | NumPy2.5.4 / SciPy1.17.0 / sklearn1.8.0 | Metadata rechecked; next nativeG5 case must use this environment after source/contract freeze |

The historical check is a new purpose and environment, not a downgrade of the generic clean environment. Both actual environments, earlier failures, old case identities and budgets remain intact. Neither split check reproduces model coefficients/predictions, proves cross-version support, or completes G6.

## Current runtime-identity protection

The root implementation now binds the numerical runtime as well as source identity:

- [`method_registry.py:82`](../../../src/autoresearch/method_registry.py#L82) reads **loaded** NumPy/SciPy/sklearn versions, compares them with installed distribution metadata, and raises `RUNTIME_CHANGED` if they disagree. At line98, these three versions enter the registry code-identity hash. This guards stale imports after an in-place package change; it is not a full OS/transitive-library binary attestation.
- [`research_project.py:171`](../../../src/autoresearch/research_project.py#L171) records `runtime_dependencies` when creating a new project. New dispatch still requires the registered code identity (`:254`, `:553`); [`project_controller.py:72`](../../../src/autoresearch/project_controller.py#L72) reports code-change blockers.
- A new compatible source upgrade requires the original registered numerical versions to match current versions (`research_project.py:704`). A different runtime or an old project with **unknown/missing** runtime registration is refused, rather than stamped with today's versions. Same-runtime source upgrades retain accumulated usage.
- Existing identical request IDs are checked for original content before returning/recovering their saved receipt (`research_project.py:548`; upgrade replay at`:693`). Retrieving an old receipt is not permission to execute a fresh action under a different runtime. Unknown/incomplete work must still be reconciled through its existing identity; no automatic redispatch or budget reset follows from replay.

These source references describe the **current root working-tree implementation**, separately from the already packaged03f90a3/0ceb274 wheels, which predate the new guard. Source hashes and line references are captured in [runtime-reproduction-boundary.json](runtime-reproduction-boundary.json); root owns final source freeze and independent acceptance. Do not claim either historical wheel already contains the new guard.

Existing targeted evidence: `tests/test_cpu_projects.py:156,170,192,205` covers changed-runtime dispatch, unknown/different upgrade refusal, same-runtime usage/replay and loaded-vs-installed mismatch. Saved `runs/g5-native-integration-unit/test-cpu-projects-04.log` reports9 tests passed. This documentation task read that evidence; it did not rerun CV/tests or claim independent full-product review.

## Handover rule

Keep historical cases pinned to their evidenced source and exact numerical environment. Do not add missing runtime metadata retroactively, register a source upgrade to erase a runtime mismatch, move a case to a new lineage to reset usage, or fit again merely to recreate a passing check. New nativeG5 execution belongs in the existing1.8 research environment with a newly frozen source/contract; the generic clean1.9 wheel test remains a separate compatibility result. No migration, dependency downgrade, model/CV run or old-case write was performed for this document.

Evidence identities:

| Receipt | SHA256 |
|---|---|
| [Reviewed G4 clean wheel](final-clean-wheel.json) | `7d4a9f14ebeb9ce3ff312b876e55625935789ecf0ca36b46323d5de05d93161f` |
| [Separate historical environment](frozen-reproduction.json) | `b75edfdb70dc92ffb6b5c009b49caf8253d5e7505368aecd88bdd341243a7361` |
| [Initial clean dependency install](clean-install.json) | `d125bfb5697757c8d78ecfe59babefb6403d01624de786b3f6d67da5cb13c97b` |

The cited raw manifests were revalidated, and new scripts/JSON were checked without printing suspected values for credential/private-key/userinfo shapes or credential-file paths; none were found. Local evidence/venv paths are provenance, not credentials.
