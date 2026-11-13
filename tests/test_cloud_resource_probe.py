"""Offline safety checks for the G0 resource parser; never starts Docker.

Synthetic all-pass observations are engineering fixtures, not evidence that
this cloud environment has enforced isolation. The saved-real-run check uses
the ignored local G0 audit record when it is present.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "cloud_resource_probe", ROOT / "scripts/verify_cloud_resources.py"
)
PROBE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PROBE)


class CloudResourceProbeTests(unittest.TestCase):
    # Intentionally synthetic: this is the expected-format control, not a run.
    VALID_STDOUT = "\n".join([
        "uid=65534(nobody) gid=65534(nobody) groups=65534(nobody)",
        "cpu.max=100000 100000", "memory.max=536870912", "pids.max=128",
        "root_readonly=PASS", "network_routes=0",
        "effective_capabilities=0000000000000000", "no_new_privileges=1",
        "tmpfs_capacity_kib=1024", "tmpfs_overflow_probe=PASS",
    ])
    VALID_STDERR = "dd: error writing '/tmp/bounded-probe.bin': No space left on device\n"
    FREE_BYTES = 10 * 1024 ** 3

    def evaluate(self, stdout=None, stderr=None, free_bytes=None):
        return PROBE.evaluate_assertions(
            self.VALID_STDOUT if stdout is None else stdout,
            self.VALID_STDERR if stderr is None else stderr,
            self.FREE_BYTES if free_bytes is None else free_bytes,
        )

    def test_expected_format_all_pass_control(self):
        assertions = self.evaluate()
        self.assertEqual(len(assertions), 10)
        self.assertTrue(all(assertions.values()))

    def test_actual_saved_environment_remains_blocked(self):
        # Use the dated audit snapshot so a later genuine environment recovery
        # and a new probe do not invalidate this historical blocked observation.
        path = ROOT / "runs/g0-resources/reviewed-20261112/probe.json"
        if not path.exists():
            self.skipTest("Ignored raw G0 evidence is not shipped with source checkouts.")
        saved = json.loads(path.read_text())
        observed = next(r for r in saved["records"] if r["name"] == "inside_actual_enforcement")
        assertions = PROBE.evaluate_assertions(
            observed["stdout"], observed["stderr"], saved["host_filesystem_bytes"]["free"]
        )
        self.assertEqual(assertions, saved["assertions"])
        self.assertEqual(saved["status"], "blocked")
        for key in ("worker_cpu_quota_1", "worker_memory_512m", "worker_pid_limit_128"):
            self.assertFalse(assertions[key])

    def test_numeric_prefixes_and_duplicate_keys_fail_closed(self):
        cases = [
            ("memory.max=536870912", "memory.max=5368709120", "worker_memory_512m"),
            ("pids.max=128", "pids.max=1280", "worker_pid_limit_128"),
            ("cpu.max=100000 100000", "cpu.max=100000 1000000", "worker_cpu_quota_1"),
            ("tmpfs_capacity_kib=1024", "tmpfs_capacity_kib=10240", "tmpfs_capacity_1m"),
            ("network_routes=0", "network_routes=01", "no_network_routes"),
            ("no_new_privileges=1", "no_new_privileges=10", "no_new_privileges"),
            ("memory.max=536870912", "memory.max=536870912\nmemory.max=536870912", "worker_memory_512m"),
        ]
        for before, after, key in cases:
            with self.subTest(after=after):
                assertions = self.evaluate(self.VALID_STDOUT.replace(before, after))
                self.assertFalse(assertions[key])
                self.assertFalse(all(assertions.values()))

    def test_any_missing_or_failed_isolation_requirement_blocks(self):
        cases = [
            ("root_readonly=PASS", "root_readonly=FAIL", "read_only_root"),
            ("network_routes=0", "network_routes=1", "no_network_routes"),
            ("tmpfs_capacity_kib=1024", "tmpfs_capacity_kib=2048", "tmpfs_capacity_1m"),
            ("tmpfs_overflow_probe=PASS", "tmpfs_overflow_probe=FAIL", "tmpfs_capacity_1m"),
            ("effective_capabilities=0000000000000000", "effective_capabilities=0000000000000001", "capabilities_dropped"),
            ("no_new_privileges=1", "no_new_privileges=0", "no_new_privileges"),
            ("uid=65534(nobody) gid=65534(nobody)", "uid=0(root) gid=0(root)", "non_root"),
        ]
        for before, after, key in cases:
            with self.subTest(requirement=key, failure=after):
                assertions = self.evaluate(self.VALID_STDOUT.replace(before, after))
                self.assertFalse(assertions[key])
                self.assertFalse(all(assertions.values()))
            with self.subTest(requirement=key, failure="missing"):
                assertions = self.evaluate(self.VALID_STDOUT.replace(before, ""))
                self.assertFalse(assertions[key])
                self.assertFalse(all(assertions.values()))

    def test_arbitrary_write_error_does_not_prove_tmpfs_capacity(self):
        for stderr in ("", "dd: Permission denied", "dd: Read-only file system"):
            with self.subTest(stderr=stderr):
                assertions = self.evaluate(stderr=stderr)
                self.assertFalse(assertions["tmpfs_capacity_1m"])
                self.assertFalse(all(assertions.values()))

    def test_missing_output_and_insufficient_host_headroom_block(self):
        self.assertFalse(all(self.evaluate(stdout="").values()))
        self.assertFalse(self.evaluate(free_bytes=5 * 1024 ** 3)["host_free_space_over_5gib"])
        self.assertFalse(self.evaluate(free_bytes=1)["host_free_space_over_5gib"])


if __name__ == "__main__":
    unittest.main()
