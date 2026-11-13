# G0 independent review

Reviewer: `independent_review`, separate from repository/resource/data implementers.
Baseline inspected: `5d497c8ae22100953f66c3c5b54746ca87e09f01`.
Date: 2026-11-12 (Asia/Shanghai; raw evidence timestamps retain UTC).

Decision: **G0 remains BLOCKED. No G1–G6 completion or research-benefit claim is approved.**

This review checks source/evidence consistency and acceptance boundaries. It is
independence of judgment in a shared workspace, not a sealed evaluator or a
qualified scientific-domain review. The reviewer did not modify product code,
rerun historical studies, call a model API, or run a second full test suite.

## Findings and disposition

| Severity | Finding | Disposition |
|---|---|---|
| Blocking | Docker accepts per-worker CPU/RAM/PID settings but exposes only the parent limits: `400000 100000`, `17179869184`, `max`. | Open. Actual inside-container evidence supports BLOCKED. Require platform-supported resource enforcement, then rerun the probe. Host limits and Docker inspect fields cannot substitute. |
| Medium | Initial probe status considered only three resource assertions; non-root, read-only, network and disk failures could have been ignored. | Corrected by resource owner: all ten assertions now determine status. |
| Medium | A non-root failed write to `/` alone cannot prove a read-only mount; any failed `dd` cannot prove an enforced tmpfs capacity. | Corrected: actual `/proc/mounts` `ro`, `df` 1024-KiB capacity and explicit ENOSPC are required; `CapEff=0` and `NoNewPrivs=1` are also observed. |
| Medium | Raw substring matching could accept `pids.max=1280` as `128`, or a larger memory/tmpfs value sharing the expected prefix. | Corrected: `evaluate_assertions` compares complete parsed values and rejects duplicate fields. Offline revalidation agrees with all ten saved assertions; seven prefix/duplicate negative cases reject. No additional Docker run was needed. |
| Medium | Existing Concrete log1p results are already visible in repository documents and cannot serve as an unseen scientific-discovery benchmark. | Corrected/explicit: all three task/data/evaluation documents label this as a known-outcome cloud reproduction and continuity test. No performance result has been produced by this G0 task. |
| Medium | A valid wait after one failed round could be misread as satisfying G1's two-round acceptance. | Corrected: evaluation protocol explicitly retains at least two meaningful rounds; a precise wait is a legitimate stop but does not automatically pass G1. |
| Informational | Initial baseline test invocation had 113 errors, principally missing optional `h5py`, across 725 discovered tests. | Original log retained. Root owns the environment correction and the final retry result; initial errors must not disappear from the account. |
| Medium | After source dependencies were installed, the full baseline ran 1,105 tests with two errors and 18 skips: one missing historical `hMSC_Analysis.cpproj`, one Windows-only `.venv/Scripts/python.exe` test invocation. | Corrected with narrow test changes: use `sys.executable`; missing undistributed default asset is an explicit skip, while explicit invalid/empty asset configuration fails. All original metadata/content/CLI comparison assertions remain. Targeted verification: 16 tests, 15 pass/1 disclosed skip; explicit bad and empty configurations fail without skips. Final full regression is recorded separately below. |
| Open verification | Upstream isolated runtime smoke tests requested by the clone/audit guide have not run. | Explicitly retained in upstream smoke receipts. Static AST/TOML/JSON inspection does not satisfy runtime compatibility. Source-audit-only/no-integration decisions are reasonable, but cannot be described as upstream runtime acceptance. |

## Evidence inspected

- [Repository audit](repository-capability-audit.md) and
  [capability matrix](implemented-vs-planned-matrix.csv): distinguish source/test
  inspection from fresh runtime proof. Spot-checked source and test line
  references, including Project persistence, plan revisions, controller,
  evidence capture, Ridge methods, memory and offline recipe-improvement.
  `recipe_improvement.py` is correctly not labeled code-level RSI.
- [Resource audit](cloud-resource-smoke-test.md),
  `scripts/verify_cloud_resources.py`, and ignored
  `runs/g0-resources/probe.json`. Reviewed observed assertion set and raw
  `inside_actual_enforcement` stdout/stderr. At this checkpoint, evidence SHA-256
  is `dabc567ddd5b6f8eb4df9211a83c85038afcb3542086320eb4ee6ce19ab639d4`;
  CPU/RAM/PID fail and seven other bounded checks pass. Later exact-parsing
  helper changes were revalidated offline against these same raw bytes. The
  reviewed script SHA-256 is
  `1dee2921a4ccf410c025e1a094d047eed26ecc225603a1c5dac5f477cd66f5c3`;
  receipt is `runs/g0-resources/exact-parser-revalidation.json`.
- [Data selection](research-data-selection.md),
  [first task](initial-research-task-spec.md), and
  [evaluation protocol](evaluation-protocol.md). Independently recomputed all
  five local source-manifest SHA-256 values; all agree. The official CSV and
  XLS are correctly not claimed identical. CC BY 4.0, original attribution,
  duplicate rows, missing batch identity and expert-review limitations remain
  explicit.
- [Execution entry](../README.md), original tracked pack, provenance and
  `docs/project/current.md`: G0 is active, dependent phases blocked, no
  unattended background research is falsely claimed. User authorization to push
  this repository does not make unreviewed third-party source redistributable.
- [Upstream manifest](upstream/upstream-manifest.json), all eight Git source
  notes, AIDE² paper notes, reuse matrix, static receipts and license/security
  review: independently checked all eight local HEADs against recorded commits
  and recomputed all 27 recorded dependency/license/README file hashes; all
  match. Three core implementations have specific execution-path evidence.
  Checked custom AI-Scientist license against its actual file and Karpathy's
  missing standalone license against its source tree. No upstream source or
  full paper is embedded in the product. GPU/API/unsafe execution and optional
  SDK/BEIR/Ragas PoCs remain unexecuted; this is correctly disclosed.
- [G0 ADR](G0-ADR.md), [Gate review](G0-review.md),
  [local-assets handoff](local-assets-handoff.md), and
  [baseline verification](baseline-verification.md): reviewed after integration.
  They preserve both resource and upstream-runtime blockers, distinguish missing
  historical assets from a fresh project, and do not make a G1 or unattended-run
  claim. The test-only portability fixes do not weaken retained content
  assertions or change production method/controller semantics.
- Final full regression inspected directly from
  `runs/g0-baseline/final-regression.log`: **1,111 tests in 163.424 seconds,
  OK (19 skipped), 1,092 passed**. This includes the six new offline resource
  parser methods. Skips are retained unavailable/optional coverage, including
  the undistributed real `.cpproj` asset; no skipped scientific-source assertion
  is called passed. Root recorded exit code 0. This result verifies the current
  engineering suite, not G0 resource enforcement or a real G1 research run.
- `tests/test_cloud_resource_probe.py`: six offline test methods cover complete
  control format, seven numeric-prefix/duplicate subcases, failed/missing
  isolation fields, misleading write errors, host headroom and an archived real
  blocked observation. The synthetic all-pass control is explicitly labeled an
  engineering fixture. The recorded six-test run passes; the archived raw
  observation is kept separate from future environment recovery. No extra
  Docker run or scientific experiment is claimed.

## Remaining closure checks

1. Source/commit/license review is complete for the eight recorded repositories;
   isolated upstream runtime smoke is still open/deferred and must remain
   distinguishable from static source checks.
2. Root's handoff, ADR and Gate review are integrated and their conclusions are
   consistent with inspected evidence. Final full regression passes with
   disclosed skips; original failures and unavailable-asset coverage remain
   visible. Reviewed test-only portability changes and resource-parser tests
   have no unresolved blocking implementation finding.
   Missing local historical runs are not reproduced by historical Markdown.
3. Resolve the resource-enforcement blocker without weakening the original Gate.
   Per-worker artifact export and persistent writable-volume bounds also require
   explicit implementation evidence before a Worker is trusted.
4. Only after actual G0 acceptance, run the real-data project and independently
   verify two-round progress, observation-driven revision, replay and handover.

## Task receipt

- Files owned/changed: this review only.
- Checks: source reads, line-reference spot checks, source SHA-256 recomputation,
  raw resource-evidence inspection; no second Docker or full-suite run.
- Product model/API sends and scientific fits by this review: 0.
- Developer-agent model identity/tokens/cost: unknown, not counted as zero.
- Next: close documented corrections, attach final upstream/root evidence, retain
  BLOCKED until resource limits are demonstrated in the actual Worker environment.
