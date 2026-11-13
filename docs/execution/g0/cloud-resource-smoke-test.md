# G0 cloud and Docker resource smoke test

Status: **BLOCKED — per-worker CPU, RAM and PID limits are not enforced.**

Observed 2026-11-12 UTC in the attached Debian cloud environment. This is a real
bounded container execution, not a fixture and not a scientific research run.
It does not pass the resource acceptance criterion in
`06-roadmap/PHASE_DELIVERABLES_AND_GATES.md` of the supplied execution pack.

## Reproduce and inspect evidence

```sh
python scripts/verify_cloud_resources.py
```

The script returns **2** when the local Docker daemon is available but the
required isolation is missing, **0** only if every reported assertion passes,
including all three requested cgroup limits observed inside the actual container.
Raw commands, exit codes, stdout,
stderr and assertions are saved in ignored `runs/g0-resources/probe.json`.
`runs/g0-resources/SHA256SUMS` records that evidence file's hash. The first
completed audit record (preserved under `runs/g0-resources/initial-20261112/`) SHA256 is
`77fdc549c1267b85cb5eab7f1b236af151375e2730bd14def036df268ca84a31`.
The final reviewed probe record SHA256 is
`dabc567ddd5b6f8eb4df9211a83c85038afcb3542086320eb4ee6ce19ab639d4`.
The final parser correction compares complete `key=value` fields, rejects
duplicate keys and avoids accepting prefixes such as `pids.max=1280` as `128`.
It was validated **offline**, without another Docker execution or overwriting
the raw probe, in `runs/g0-resources/exact-parser-revalidation.json`. All 10
recomputed assertions match the saved result, and seven numeric-prefix/duplicate
negative cases reject correctly. The corresponding script SHA256 is
`1dee2921a4ccf410c025e1a094d047eed26ecc225603a1c5dac5f477cd66f5c3`.
That reviewed raw snapshot is also preserved under
`runs/g0-resources/reviewed-20261112/` so future environment recovery and fresh
probe outputs do not overwrite this historical blocked observation.

Repeatable offline safety tests are retained in
`tests/test_cloud_resource_probe.py`:

```sh
python -m unittest discover -s tests -p test_cloud_resource_probe.py -v
```

All **6 tests passed**, including the actual saved blocked record, a synthetic
expected-format all-pass control, numeric-prefix and duplicate rejection,
missing/failed isolation fields and arbitrary write errors. The raw local audit
test skips when the ignored dated evidence is absent from a clean checkout;
the remaining parser safety tests still run. No Docker was started by these
tests. Saved log: `runs/g0-resources/parser-unittest-final.log`, SHA256
`4bbbb0fb757209e0463e74ed69ef6bd8d7875b833ffc8276d96b85a906d6933c`.
Subsequent runs overwrite that local path and receive a new timestamp and hash;
archive a copy first if the initial observation must remain separately retained.

The probe uses the explicit local socket `unix:///var/run/docker.sock`, with
Docker endpoint/context/TLS selectors removed only for the subprocess. Registry
and CA configuration remain unchanged. It never starts or restarts a daemon.

## Environment observations

| Item | Actual observation |
|---|---|
| Task user | UID 1000 |
| Host CPU cgroup | `400000 100000`, equivalent to 4 CPU |
| Host RAM cgroup | `17179869184` bytes, 16 GiB |
| Host PID cgroup | `max` |
| Cgroup mount | cgroup v2; `/sys/fs/cgroup` owned by root, mode 0755 |
| Available controllers | `cpuset cpu io memory hugetlb pids` |
| Delegated subtree controllers | Empty `cgroup.subtree_control` |
| Docker | 29.9.2, rootless, storage driver `vfs`, cgroup driver `none` |
| Daemon capabilities | `MemoryLimit=false`, `CpuCfsQuota=false`, `PidsLimit=false` |
| Daemon warning | Running rootless without cgroups; systemd is required to enable cgroups in rootless mode |
| Probe image | `alpine@sha256:d9e853e87e55526f6b2917df91a2115c36dd7c696a35be12163d44e6e2a4b6bc` |

Host filesystem capacity and free bytes are captured at the time of each probe.
The environment has about 32 GB total; the exact remaining value changes as
independent audits clone repositories and install dependencies. No GPU workload
or large image build was attempted.

## Requested flags versus observed enforcement

The actual probe requests:

```text
--network none --read-only --cap-drop ALL
--security-opt no-new-privileges:true --user 65534:65534
--memory=512m --cpus=1 --pids-limit=128
--tmpfs /tmp:rw,noexec,nosuid,size=1m,mode=1777
```

Docker accepts these flags and stores them in `HostConfig`. That metadata is
not enforcement evidence. The bounded process reads the following actual
cgroup files from inside the container:

| Control | Requested | Read inside container | Result |
|---|---|---|---|
| CPU | 1 CPU | `cpu.max=400000 100000` | FAIL; only host-wide 4 CPU cap visible |
| Memory | 512 MiB | `memory.max=17179869184` | FAIL; only host-wide 16 GiB cap visible |
| PID | 128 | `pids.max=max` | FAIL; unbounded in the visible cgroup |
| Non-root user | UID/GID 65534 | `uid=65534(nobody) gid=65534(nobody)` | PASS |
| Root filesystem | Read-only | Actual `/proc/mounts` root options contain `ro`; write also rejected | PASS |
| Network | None | No routes from `ip route` | PASS for this network namespace |
| Capabilities | All dropped | `/proc/self/status` `CapEff` all zero | PASS |
| Privilege escalation | Disabled | `/proc/self/status` `NoNewPrivs=1` | PASS |
| Temporary filesystem | 1 MiB | `df` capacity 1024 KiB and 2 MiB bounded write fails with `No space left on device` | PASS |
| Host disk headroom | More than 5 GiB free | Checked from current filesystem free bytes | PASS |

No OOM allocation, CPU saturation, process fanout/fork bomb, host permission
change, privileged container or host networking was used. Container cleanup
completed after the test. The image is small and pinned by digest.

The tmpfs check verifies a bounded ephemeral scratch area. It does not prove
quotas for a persistent writable bind mount or artifact export directory. The
read-only root prevents growth through ordinary root writes; host-wide free
space remains a shared resource. Artifact capture must be bounded by the
supervisor and separately tested in any eventual Worker implementation.

## Impact and required recovery

Current user permissions do not permit creating a delegated cgroup subtree or
reconfiguring the platform-managed daemon. Existing host limits protect the
whole environment but do not reserve host headroom or isolate multiple Workers.
Do not launch untrusted, candidate-modified or heavy research code under the
assumption that Docker enforces the requested per-worker limits.

To close this criterion, the managed platform must provide a supported
rootless Docker setup with delegated `cpu`, `memory` and `pids` controllers, or
attach another authorized Worker environment that enforces the same resource
contract. After recovery, rerun the probe and verify both daemon capability
metadata and the **inside-container** values. A privileged daemon restart or
manual host permission change is not an authorized task-level workaround.

Process `rlimit` controls may help a future trusted local-process supervisor,
but they do not satisfy this pack's explicit Docker/cgroup acceptance criterion;
they are not substituted here. Read-only audits, dataset/source selection and
contract analysis may continue without claiming that G0 passed. Gate-dependent
Worker execution and RSI isolation remain blocked pending real recovery.
