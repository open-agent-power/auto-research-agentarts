"""Bounded, non-destructive G0 Docker resource probe; never treat flags as enforcement.

No model calls, heavy allocation, process fanout, host permission changes, or
privileged containers. Raw evidence stays in ignored runs/. Uses the local
Docker socket even when an inherited Docker context points elsewhere.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess


DOCKER = ["docker", "--host=unix:///var/run/docker.sock"]
IMAGE = "alpine@sha256:d9e853e87e55526f6b2917df91a2115c36dd7c696a35be12163d44e6e2a4b6bc"
PROBE = r"""
id
for f in cpu.max memory.max pids.max; do
  printf '%s=' "$f"
  cat "/sys/fs/cgroup/$f" 2>&1
done
printf 'cgroup_membership='; cat /proc/self/cgroup
root_options="$(awk '$2 == "/" {print $4}' /proc/mounts)"
printf 'root_mount_options=%s\n' "$root_options"
printf 'root_readonly='
case ",$root_options," in *,ro,*) echo PASS ;; *) echo FAIL ;; esac
touch /root-write-probe 2>&1 || true
printf 'network_routes='; ip route | wc -l
awk '/^CapEff:/ {print "effective_capabilities=" $2} /^NoNewPrivs:/ {print "no_new_privileges=" $2}' /proc/self/status
df -k / /tmp
printf 'tmpfs_capacity_kib='; df -k /tmp | awk 'NR == 2 {print $2}'
printf 'tmpfs_overflow_probe='
if dd if=/dev/zero of=/tmp/bounded-probe.bin bs=65536 count=32; then
  echo FAIL
else
  echo PASS
fi
rm -f /tmp/bounded-probe.bin
"""


def evaluate_assertions(stdout: str, stderr: str, free_bytes: int) -> dict[str, bool]:
    """Compare full observed fields, never numeric/string prefixes.

    Duplicate fields are treated as missing so ambiguous output fails closed.
    This pure helper also permits offline revalidation of saved raw evidence.
    """
    fields: dict[str, str | None] = {}
    for line in stdout.splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            fields[key] = value.strip() if key not in fields else None
    non_root = any(re.fullmatch(
        r"uid=65534\([^)]*\) gid=65534\([^)]*\)(?: groups=.+)?", line
    ) is not None for line in stdout.splitlines())
    return {
        "worker_cpu_quota_1": fields.get("cpu.max") == "100000 100000",
        "worker_memory_512m": fields.get("memory.max") == "536870912",
        "worker_pid_limit_128": fields.get("pids.max") == "128",
        "non_root": non_root,
        "read_only_root": fields.get("root_readonly") == "PASS",
        "no_network_routes": fields.get("network_routes") == "0",
        "capabilities_dropped": fields.get("effective_capabilities") == "0000000000000000",
        "no_new_privileges": fields.get("no_new_privileges") == "1",
        "tmpfs_capacity_1m": all((fields.get("tmpfs_overflow_probe") == "PASS",
            fields.get("tmpfs_capacity_kib") == "1024", "No space left on device" in stderr)),
        "host_free_space_over_5gib": free_bytes > 5 * 1024 ** 3,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="runs/g0-resources")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    output = (root / args.output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    records = []
    env = os.environ.copy()
    for key in ("DOCKER_HOST", "DOCKER_CONTEXT", "DOCKER_TLS", "DOCKER_TLS_VERIFY", "DOCKER_CERT_PATH"):
        env.pop(key, None)

    def run(name: str, command: list[str], timeout: int = 60) -> subprocess.CompletedProcess:
        result = subprocess.run(command, text=True, capture_output=True, env=env, timeout=timeout)
        records.append({"name": name, "command": command, "exit_code": result.returncode,
                        "stdout": result.stdout, "stderr": result.stderr})
        return result

    info_result = run("local_daemon", DOCKER + ["info", "--format", "{{json .}}"])
    if info_result.returncode:
        (output / "probe.json").write_text(json.dumps({"status": "blocked", "records": records}, indent=2) + "\n")
        print("BLOCKED: local Docker daemon unavailable; see", output / "probe.json")
        return 2
    info = json.loads(info_result.stdout)
    # Avoid persisting registry/context or proxy configuration; evidence only needs capabilities.
    info_fields = ("ServerVersion", "Driver", "CgroupDriver", "CgroupVersion", "MemoryLimit",
                   "CpuCfsQuota", "CpuCfsPeriod", "PidsLimit", "SecurityOptions", "Warnings")
    records[-1]["stdout"] = json.dumps({key: info.get(key) for key in info_fields}, indent=2)
    image = run("image_identity", DOCKER + ["image", "inspect", IMAGE, "--format", "{{json .RepoDigests}}"])
    if image.returncode:
        run("pull_pinned_image", DOCKER + ["pull", IMAGE], timeout=120)

    # Explicit request metadata is retained separately from actual values read inside.
    create = run("create_bounded_probe", DOCKER + ["create", "--network", "none", "--read-only",
        "--cap-drop", "ALL", "--security-opt", "no-new-privileges:true", "--user", "65534:65534",
        "--memory=512m", "--cpus=1", "--pids-limit=128", "--tmpfs", "/tmp:rw,noexec,nosuid,size=1m,mode=1777",
        IMAGE, "sh", "-c", PROBE])
    actual = ""
    actual_error = ""
    if create.returncode == 0:
        container_id = create.stdout.strip()
        try:
            run("requested_configuration", DOCKER + ["inspect", container_id, "--format",
                '{"HostConfig":{{json .HostConfig}},"User":{{json .Config.User}}}'])
            started = run("inside_actual_enforcement", DOCKER + ["start", "--attach", container_id])
            actual = started.stdout
            actual_error = started.stderr
        finally:
            run("remove_probe", DOCKER + ["rm", "--force", container_id])

    host = {}
    for field in ("cpu.max", "memory.max", "pids.max", "cgroup.controllers", "cgroup.subtree_control"):
        file = Path("/sys/fs/cgroup") / field
        host[field] = file.read_text().strip() if file.exists() else None
    disk = shutil.disk_usage(root)
    assertions = evaluate_assertions(actual, actual_error, disk.free)
    result = {
        "observed_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": "pass" if all(assertions.values()) else "blocked",
        "host_cgroup": host,
        "host_filesystem_bytes": {"total": disk.total, "free": disk.free},
        "assertions": assertions,
        "records": records,
        "limitations": ["No allocation/OOM/fork stress was performed; cgroup files are the enforcement evidence.",
                        "Read-only root plus bounded tmpfs is tested; writable persistent artifact/bind-mount quotas are not proven.",
                        "Host cgroup limits do not establish per-worker isolation."]}
    target = output / "probe.json"
    target.write_text(json.dumps(result, indent=2) + "\n")
    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    (output / "SHA256SUMS").write_text(f"{digest}  probe.json\n")
    print(json.dumps({"status": result["status"], "assertions": result["assertions"],
                      "evidence": str(target), "sha256": digest}, indent=2))
    return 0 if result["status"] == "pass" else 2


if __name__ == "__main__":
    raise SystemExit(main())
