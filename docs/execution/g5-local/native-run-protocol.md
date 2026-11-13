# Native CPU project host execution

Status: draft pending independent review and root code commit/freeze. No real
native retrieval or scheduling case has been run by writing this driver.
Root fills the reviewed full commit SHA after code/protocol review; no placeholder
commit authorizes execution. Previously published standalone outcomes are known.
This stage checks native lifecycle integration and new measured fixed-pair outputs,
not unseen evaluation, new science/algorithm discovery or automatic promotion.

`scripts/run_native_cpu_cases.py` is a thin host wrapper around ResearchProject,
LocalWorkbench and ProjectController. It adds no public endpoint/tool/controller,
invokes no old standalone benchmark and accepts no candidate code/commands.

## Freeze, then separately authorize one case

Use the installed repository `.venv/bin/python`. Prepare requires
`--case retrieval|scheduling`, explicit fresh `--output` and
`--code-commit <root-reviewed-full-HEAD>`. It verifies committed source/protocol/
contracts, reads the existing prepared source packet, performs adapter schema-only
validation with research compute patched to reject, and captures original-file
identities. No project, source extraction, ranking, solving or model call occurs.
The selected packet is copied as original bytes to `frozen/source.json`. The
actual free disk space must be at least5GiB at prepare, run and child start;
prepare/child observations are saved. Interpreter path/version is also frozen.
Real output must be a fresh
`REPO/runs/g5-native-cases-<unique>/{retrieval|scheduling}` directory, with no
symlink ancestor or traversal. Engineering outputs must be explicit scratch
directories under `/workspace/work` or `/tmp`. Both modes reject overlap with
protected case/source trees; the fixture flag cannot create an output inside
source code or old evidence.

Real packet identities are fixed: retrieval
`546a09773bc8e77aa7f034ca58753394f6a75c3ecf610e3c66c3f24eea2ab51b`
(460 selected queries:80/80/300), scheduling
`c801e08c980caa8f56be6865eef149c98e3cad1c486b0abd39c37695611dcc3e`
(16 cases/20,544 jobs:4 dev/validation+12 test). Source preflights and contracts
retain provenance, exact original hashes, public-label and synthetic-data limits.
`--engineering-fixture --packet <small-packet>` is explicit, restricted to ≤20
documents/queries or ≤4 cases/32 jobs, and cannot relabel either real packet.

`run --output <same-root> --review <new-review.json>` checks exact frozen output
root, current committed code/runtime, packet, protected originals and review.
The review has exactly schema_version,status,freeze_sha256,code_commit,output_root,
case,reviewer,limitations. Schema is `g5-native-cpu-run-review-v1`, status approved;
digest/commit/root/case must match this freeze. It is archived before one exclusive
`attempt.json` claim. The same review cannot execute a copied freeze in a new root.
An existing attempt is never retried or replaced. Direct `_worker` use is internal
and also requires the original attempt/review/freeze identities; same-UID files
are procedural controls, not OS authorization/sealing.

## Execution and evidence

One case runs in a separate Python subprocess. Only the child sets wall alarm180s,
CPU120s soft/130s hard, address space1GiB, individual file32MiB and numeric-library
thread environment1. The parent additionally stops the child at180s; parent/root
session resource limits are unchanged. These are host limits, not cgroup isolation,
a total disk quota or an exact per-operation CPU meter. A timeout/nonzero worker
status is unknown and must not auto-retry; core reservations/artifacts are retained.

The child follows existing native APIs: create a new 2-tool project; lower source
read allowance8→0; same-filesystem import into a new LocalWorkbench; explicitly
select; save plan1; submit exact controller candidate/context primary proposal;
save plan2 from actual action/result SHA, saved observations and adverse count;
execute saved-only audit; save plan3 from the actual audit and wait; export the
existing four native report files. No estimator fits, model sends, source reads,
parameter search, auto-promotion or old-case writes are allowed. Saved-only audit,
exact completed-action replay and report export run with primary ranking/DP/
brute-force/generation/timing patched to reject. Full compute remains only in the
one primary tool action. Scheduling preserves80 actual runs at fixed repetitions;
retrieval preserves every selected query/arm and actual adverse metrics.

Every API step persists command/body and same-ID replay body before dispatch,
result and before/after budget afterward. The driver verifies completed primary,
audit and wait replay without another tool charge. Plan2 points to complete actual
feedback, never injected historical scores. Final status must have2 actions,
3 plan revisions, waiting, tools used2/reserved0, fits0/models0/source reads0.
Report uses native exporter/manifests and retains actual full raw evidence.

Freeze protects both prepared packets/input directories, original7 inputs/11
standalone outputs, old frozen script/protocol, mapping/preflight receipts,
three complete old case roots (including the292 manager research-file subset),
five G4 controls and both complete G4 VM/native trees. Exact protected tree roots
are frozen; each verification and final check re-enumerates their full path sets
and checks every full-file identity, detecting added/deleted files as well as
changed bytes. Full-file before/after
identities are retained; mismatch prevents success. No claim of atomic directory
snapshot, independent sealed labels, protection from same UID, user satisfaction,
scientific validity or competitive state-of-the-art scheduling is made.

On interruption, preserve `attempt.json`, command/replay bodies, core reservations,
artifacts/stdout/stderr and any worker error. This driver never resumes automatically.
Root may inspect/replay only the exact already-persisted original request through
native recovery after independent review, without re-running the batch or creating
a replacement budget. Development cost remains unknown, distinct from measured
zero product model/API/fit usage.
Each step saves its receiver path, and `project-relocation.json` records the
same-filesystem move from `unmanaged-project` to the import's existing managed
target. Create has no request ID: never replay it into the now-absent original
root after import, which would create another lineage. Before any reviewed manual
recovery require the relocated target DB to exist, bind that existing project,
then replay only its exact original IDs/bodies. Interrupted import uses the
original workbench import intent/ID, not another create/import.
