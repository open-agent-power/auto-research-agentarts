# Native scheduling data preflight

Status: **prepared, no research execution**. No ResearchProject/case was created,
no dynamic program or exhaustive solver was called, and no native timing/tool,
estimator fit, model or API action was run. Host generation and source/schema
checks are preparation work; development token/currency charges remain unknown.

## Captured source

Input directory: `/workspace/work/g5-native-scheduling-inputs`. Source packet:
`/workspace/work/g5-native-scheduling-packet.json`, **1,338,429 bytes**, SHA256
`c801e08c980caa8f56be6865eef149c98e3cad1c486b0abd39c37695611dcc3e`.
Snapshot SHA256:
`08ebf6433efb414ff139197036f5fa419ffe9e0f11037954f537d5a80e8b678d`.

| Original runtime file | Bytes | SHA256 |
|---|---:|---|
| jobs.json | 999417 | `b4aecf9b3a6f595724020ccc86def14016baf96df4d8dddc694b938a529f6ff6` |
| license.md | 571 | `123c4a15a5b070596c78b9245bc27afe4e9f9bd74b923eb15b5c7dd67a22bf96` |
| spec.json | 1690 | `7e6b903ceda6e6527cba4a700a24ba9390124ed69b08aae9fc77730bfc59479b` |

These are complete synthetic integer inputs generated locally from the frozen
project definition. They are not an external scientific dataset. The inert source
URL identifies local `scripts/run_cpu_transfer_benchmarks.py#jobs_for`.
`license.md` records own-generated provenance, makes no external dataset license
claim, and grants no new rights. No top-level repository LICENSE was found in the
inspected source snapshot; this note is not a legal assurance or substitute for
source copyright review.

## Exact workload identity and representation

The original run is `runs/g5-local-cpu-20261113-01`. Bound original identities:

- Script: `f9e51cd73b3c25daa2c3c34b0748cd999be0e0c130a5c373e96b7fc63a032b1a`.
- Protocol: `2c7db01a202ea22a2d15745cf2d42d3244c99371db062efa91e2b92cf673dd8f`.
- Freeze: `759d15473a64f45f855f5c455ddb6329bac229885d077424d381df3ef25f6af8`.
- Manifest: `660bd6b2867222e51e1480fcdff3a679eff71b67723b28c9f5ff544ea904bf7d`.

The standalone module was neither imported nor executed. Its `jobs_for` AST body
is structurally identical to the new host generator's core, excluding only the
new docstring and stricter primitive seed/count guard. The original function
source SHA is `e030f601187ef1d6a4ccd6c95ff19ba0c4d4f04e81b4d1593246178419c2d2d0`;
the normalized generation-core AST SHA is
`cf436c83a68e6344ebada6e38fe807ae0ea5bbf78aa592005801e21ee6071c70`.
Exactly 16 generation calls reproduced the fixed seeds and sizes.

The legacy ordered representation is `[start,end,weight,id]` per job. The new JSON
record names these fields `id,start,end,weight`; reconstructing the ordered legacy
tuples yields the exact old canonical SHA for every workload. All values remain
exact integers, including numeric IDs `0..n-1`; no strings/floats, new seeds,
reordering, clipping or truncated jobs were substituted. Physical JSON formatting
and field names are new. Start/end use synthetic integer ticks and weights use
synthetic weight units; these are not observed real-world times or utilities.

All **72** old test timing records match the regenerated input identity and exact
method/repetition pairs. Four dev/validation identity rows match separately.
Only `split,seed,n,repeat,method,input_sha256` were used from old results; old
objectives, schedule hashes and timings were not used to choose or tune this
packet, and no objective/schedule/timing was recomputed in preparation.

| Case | Jobs | Legacy ordered input SHA256 |
|---|---:|---|
| dev-n32-seed101 | 32 | `5793840a12e3589b09251de753deed4ee298c8f54bf4e0caf7f59eb954af28ff` |
| dev-n32-seed102 | 32 | `6b521e77a21141dc1a0cdf6c0c81afb8ccbb608a6535d984987d180445042dfd` |
| validation-n64-seed201 | 64 | `e71fd3d684af148d9cc5a982300cfe47b370b9a16d00c990c68b47c554ec99ae` |
| validation-n64-seed202 | 64 | `b69b80732378ed69cb0782762f8dff7a0487d5725eb101ab8733ddddf8a8edfe` |
| test-n128-seed303 | 128 | `f159d2127a923fbd48d517c283a2daed264af0d422f0b68aef2a8c86131beb2b` |
| test-n128-seed404 | 128 | `d728048fbca36a4f452487991ea4974c4ef2e75e4b635cf96eb8165856fbfb2e` |
| test-n128-seed505 | 128 | `dd005df6a0bc0dd00caa30685af9e3e5622e19026547652f8e83a2a6f8c7948e` |
| test-n512-seed303 | 512 | `c67dfedd0f7df397ba7acc10656a9769fff93575ef09bd34c08d9c1ad3d2dc0f` |
| test-n512-seed404 | 512 | `67b3b53c5378944c0d9c1bd1b0a85147e23ffd6148d18f56c2576cf3ed561bc0` |
| test-n512-seed505 | 512 | `382bf99de2f9e530f7f9b0d10b3942a29216bd2b6864005b59f207fd84652699` |
| test-n2048-seed303 | 2048 | `84a10cdf8cedf27f2e83d02c74025c5819fd011ed5c14763274277b5ec7ee12d` |
| test-n2048-seed404 | 2048 | `b6a26f1849d656c6808d931f590035a9fc8411a59ef988f57f7765c0ea2e5089` |
| test-n2048-seed505 | 2048 | `7c128fbbe5f0f34256342cafe96b93eaaa1e38384505e271f8f5b5245891069a` |
| test-n4096-seed303 | 4096 | `0b097f306ee2ee6d60eb523e81ffc2d4c46415d02b6c83f0d998f4dc57027108` |
| test-n4096-seed404 | 4096 | `987cb8802d0509bd5c0c7ebb8d2990b42144773ae48b08359f7c7d56e97d1b29` |
| test-n4096-seed505 | 4096 | `71b6a8fcb37a5dd084d1ce675a3db3fda6998da70d0027174095ce6a648c799e` |

This packet contains **16 cases / 20,544 jobs**: four dev/validation and all twelve
test workloads. Planned test repetitions are exactly three per arm and other
repetitions exactly one: **80 native solver calls, not yet executed**. Preflight
cost is **95,599,712 naive predecessor comparisons** if later executed, within
the 110,000,000 cap; exhaustive subset work is **0** because the smallest case
has 32 jobs. The old 4 edge + 24 n=12 exhaustive cases are not in this packet.
The unit fixtures and old correctness evidence are separate; this is not a replay
of all 44 old workloads or a new exhaustive correctness validation.

## Evidence, retained error and final checks

Host scripts and receipts are in
`/workspace/work/g5-native-scheduling-host-prepare/`. The initial `prepare_inputs.py`
successfully wrote and validated the packet and preflight receipt, then its final
console summary referenced a budget field absent from public scope and raised
`KeyError`. Original script, traceback and `error.json` are retained. Only that
console expression was corrected; neither inputs nor packet were regenerated or
overwritten. `verify_prepared.py` performed a fresh read-only recapture and schema
check; final receipt SHA is
`dd8244af16867ea4b7ba3cb2ab6ad4c1e98cdc723fe5e11fbd25e0e6daf4ed9b`.

Independent module review then found two small source-schema defects: Python
numeric equality accepted a `3.0` echo of spec integer `3`, and JSON `1e309` was not
classified as ResearchError during capture. Canonical spec equality and a finite
JSON-float check repaired them; 20 small fixture tests pass. The data packet did
not change. `verify_source_reviewed.py` reloaded and recaptured the same packet
with adapter SHA `86f653b0bfbc9cb6c9b596c09a02ddb4252871ced1ed70a530091deaff04a098`;
receipt `source-reviewed-preflight.json` SHA is
`c6b06dc8f280271de5a1962418f58d1fca1223e1c9e96bf498b2521cd15bcecf`.
Kernel remains `3a335e102279ce9e6a7a8861a3f203670fccfbfb3ea3d2941f8b9406ea92e401`.

During preparation, schedule, brute-force, saved schedule verifier, wall-clock
timer and primary execute were patched to reject; all call counts were **0**.
During both read-only finalizations the generator was also patched; all six
forbidden counts were **0**. Source bytes/caps/SHA/strict schema alone were checked.
These guards do not claim OS isolation or a general arbitrary-code boundary.

All **7 old input files and 11 old run files**, plus the frozen script/protocol,
retain identical full-file SHA/size entries before and after preparation and both
finalizations. `protected-before.json` and `protected-after.json` both hash to
`f8f7b8f3a2a3068b1a638681b57806428093dc6aaf0af3b42229f5fc3706c2bd`.
This protects old evidence procedurally on the same host; it is not an atomic
cross-file snapshot or protection from another process with the same UID.

Root must still bind reviewed source, protocol, packet and host controls in a new
native-case freeze before the separately authorized two local actions. The first
action runs the fixed pair and retains every actual timing/full schedule; the
second only audits saved data, then waits. Faster timing, if observed, remains a
known engineering optimization on these synthetic workloads, with no new-science,
new-algorithm, production promotion or broader scheduling-quality claim.
