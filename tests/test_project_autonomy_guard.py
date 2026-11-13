"""Cooperative lease tests use temporary metadata only; no research execution."""
from contextlib import redirect_stdout
import importlib.util
import io
import json
import multiprocessing
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location("project_autonomy_guard", Path(__file__).resolve().parents[1] / "scripts/project_autonomy_guard.py")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
Guard, GuardError = MODULE.Guard, MODULE.GuardError


def concurrent_claim(directory, owner, barrier, queue):
    barrier.wait(timeout=10)
    try:
        state = Guard(directory, clock=lambda: 100).claim(owner)
        queue.put((owner, "claimed", state["owner"]))
    except GuardError as exc:
        queue.put((owner, exc.code, None))


class ProjectAutonomyGuardTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.now = 100.0
        self.guard = Guard(self.root / ".agent/autonomy", clock=lambda: self.now)

    def rejected(self, code, function, *args, **kwargs):
        with self.assertRaises(GuardError) as error:
            function(*args, **kwargs)
        self.assertEqual(error.exception.code, code)

    def test_real_concurrent_claims_have_exactly_one_owner(self):
        context = multiprocessing.get_context("fork")
        barrier, queue = context.Barrier(5), context.Queue()
        processes = [context.Process(target=concurrent_claim, args=(self.guard.directory, f"worker-{i}", barrier, queue)) for i in range(4)]
        try:
            for process in processes: process.start()
            barrier.wait(timeout=10)
            results = [queue.get(timeout=10) for _ in processes]
            for process in processes:
                process.join(timeout=10)
                self.assertEqual(process.exitcode, 0)
            winners = [item for item in results if item[1] == "claimed"]
            self.assertEqual(len(winners), 1)
            self.assertEqual(sum(item[1] == "LEASE_BUSY" for item in results), 3)
            state = self.guard.status()
            self.assertEqual(state["owner"], winners[0][0])
            self.assertEqual(len(state["events"]), 1)
            self.assertFalse(state["available"])
        finally:
            for process in processes:
                if process.is_alive(): process.terminate()
                process.join(timeout=10)
            queue.close()

    def test_conflicts_idempotent_claim_and_heartbeat_ttl_without_event_noise(self):
        state = self.guard.claim("current")
        self.assertEqual(state["expires"], self.now + 1200)
        self.now += 1
        self.rejected("LEASE_BUSY", self.guard.claim, "scheduled")
        self.rejected("OWNER_MISMATCH", self.guard.heartbeat, "scheduled")
        original = self.guard.path.read_bytes()
        self.assertEqual(self.guard.claim("current")["expires"], state["expires"])
        self.assertEqual(self.guard.path.read_bytes(), original)
        state = self.guard.heartbeat("current", ttl=3600)
        self.assertEqual(state["expires"], self.now + 3600)
        self.assertEqual([event["kind"] for event in state["events"]], ["claim"])
        for ttl in (0, 3601, True, 1.5): self.rejected("INVALID_TTL", self.guard.claim, "current", ttl=ttl)
        self.rejected("INVALID_OWNER", self.guard.claim, "../other")

    def test_expiry_takeover_and_stale_owner_cannot_heartbeat_or_release(self):
        self.guard.claim("old", ttl=10)
        self.now += 10
        self.assertTrue(self.guard.status()["available"])
        self.rejected("LEASE_EXPIRED", self.guard.heartbeat, "old")
        state = self.guard.claim("new", ttl=20)
        self.assertEqual(state["events"][-1], {"kind":"takeover", "owner":"new", "at":self.now, "previous_owner":"old"})
        original = self.guard.path.read_bytes()
        self.rejected("OWNER_MISMATCH", self.guard.heartbeat, "old")
        self.rejected("OWNER_MISMATCH", self.guard.release, "old")
        self.assertEqual(self.guard.path.read_bytes(), original)

    def test_owner_release_is_idempotent_then_new_claim_and_cli_share_state(self):
        self.guard.claim("first")
        self.rejected("OWNER_MISMATCH", self.guard.release, "other")
        self.now += 1
        state = self.guard.release("first")
        self.assertEqual(state["status"], "released")
        self.assertTrue(state["available"])
        self.assertEqual(state["expires"], self.now)
        original = self.guard.path.read_bytes()
        self.guard.release("first")
        self.assertEqual(self.guard.path.read_bytes(), original)
        self.rejected("LEASE_EXPIRED", self.guard.heartbeat, "first")
        with patch.object(MODULE, "Guard", return_value=self.guard), redirect_stdout(io.StringIO()) as output:
            self.assertEqual(MODULE.main(["claim", "--owner", "second", "--ttl", "10"]), 0)
        self.assertEqual(json.loads(output.getvalue())["owner"], "second")
        self.assertEqual([item["kind"] for item in self.guard.status()["events"]], ["claim", "release", "claim"])

    def test_malformed_state_fails_closed_and_source_and_budgets_are_untouched(self):
        source, budget = self.root/"src/sentinel.py", self.root/"cases/study/budget.json"
        source.parent.mkdir(); budget.parent.mkdir(parents=True)
        source.write_bytes(b"unchanged source\n"); budget.write_bytes(b'{"used_fits":20,"limit":20}\n')
        originals = {source:source.read_bytes(), budget:budget.read_bytes()}
        self.guard.claim("owner")
        valid = json.loads(self.guard.path.read_text())
        changed = dict(valid, status="unknown")
        wrong_owner = dict(valid, owner=None)
        unknown_key = dict(valid, budget_reset=True)
        variants = [b"", b"not json", b'{"owner":"a","owner":"b"}', b'\xff',
                    json.dumps(changed).encode(), json.dumps(wrong_owner).encode(), json.dumps(unknown_key).encode(),
                    json.dumps(dict(valid, expires=float("nan"))).encode(),
                    json.dumps(dict(valid, expires=valid["updated_at"]+3601)).encode()]
        for raw in variants:
            self.guard.path.write_bytes(raw)
            for function, args in ((self.guard.status,()),(self.guard.claim,("new",)),(self.guard.heartbeat,("owner",)),(self.guard.release,("owner",))):
                with self.subTest(raw=raw, action=function.__name__):
                    self.rejected("STATE_INVALID", function, *args)
                    self.assertEqual(self.guard.path.read_bytes(), raw)
        self.guard.path.write_text(json.dumps(valid))
        self.now -= 1
        self.rejected("INVALID_CLOCK", self.guard.status)
        self.now = 10**1000
        self.rejected("INVALID_CLOCK", self.guard.status)
        self.assertEqual({path:path.read_bytes() for path in originals}, originals)


if __name__ == "__main__":
    unittest.main()
