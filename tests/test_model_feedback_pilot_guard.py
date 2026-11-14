"""Temporary-only cooperative pilot guard tests; no model or research calls."""
import hashlib
import json
import multiprocessing
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import model_feedback_pilot_guard as pilot


def reserve_in_child(paths, manifest, queue):
    try:
        queue.put(pilot._Guard(paths, manifest).reserve("selection")["status"])
    except pilot.GuardError as error:
        queue.put(error.code)


class ModelFeedbackPilotGuardTests(unittest.TestCase):
    def setUp(self):
        self.enterContext(patch("socket.socket", side_effect=AssertionError("Network is forbidden")))
        self.enterContext(patch("subprocess.Popen", side_effect=AssertionError("No child CLI or model")))
        self.temp = self.enterContext(tempfile.TemporaryDirectory())
        root = Path(self.temp)
        tree = root / "pin"; tree.mkdir(); (tree / "module.py").write_text("fixture\n")
        proposal = root / "proposal.md"; proposal.write_text("fixture proposal\n")
        head = root / "HEAD"; head.write_text("f" * 40 + "\n")
        inputs = tuple(root / f"input-{n}" for n in range(3))
        for i, path in enumerate(inputs): path.write_text(f"fixture-{i}\n")
        self.paths = pilot._Paths(root / "authorization.json", root / "claim.json", root / "ledger.jsonl",
                                  root / "lock", root / "target", proposal, head, tree, inputs)
        self.manifest = pilot._Manifest("fixture-study", "f" * 40, self.sha(proposal), pilot._tree_sha(tree),
                                        tuple(self.sha(path) for path in inputs))
        self.guard = pilot._Guard(self.paths, self.manifest)

    @staticmethod
    def sha(path):
        return hashlib.sha256(path.read_bytes()).hexdigest()

    def authorize(self, delegations=3, tools=2):
        value = {"schema_version": "model-feedback-pilot-authorization-v1", "authorized_by": "user",
                 "statement": pilot.AUTH_STATEMENT, "study": self.manifest.study,
                 "proposal_sha256": self.manifest.proposal_sha, "pin": self.manifest.pin,
                 "workspace": str(self.paths.target), "target": str(self.paths.target / "project"),
                 "delegation_limit": delegations, "tool_limit": tools,
                 "paid_api_allowed": False}
        self.paths.authorization.write_text(json.dumps(value))

    def assert_error(self, code, callback, *args):
        with self.assertRaises(pilot.GuardError) as error:
            callback(*args)
        self.assertEqual(error.exception.code, code)

    def artifact(self, phase, content=b'{"fixture":true}'):
        directory = self.paths.target / "artifacts"
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / (phase + ".json")
        path.write_bytes(content)
        return self.sha(path)

    def request(self, phase, content=b'{"fixture_request":true}'):
        directory = self.paths.target / "artifacts"
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / (phase + ".request.json")
        path.write_bytes(content)
        return self.sha(path)

    def finish(self, phase):
        self.request(phase)
        self.guard.reserve(phase)
        digest = self.artifact(phase)
        self.guard.complete(phase, digest)
        return digest

    def test_missing_authorization_creates_nothing(self):
        self.assert_error("AUTHORIZATION_REQUIRED", self.guard.initialize)
        self.assert_error("AUTHORIZATION_REQUIRED", self.guard.reserve, "selection")
        for path in (self.paths.claim, self.paths.ledger, self.guard._anchor_path(), self.paths.lock, self.paths.target):
            self.assertFalse(path.exists())

    def test_invalid_authorization_and_budget_are_not_approval(self):
        for bad in (4, True, -1):
            self.authorize(delegations=bad)
            self.assert_error("AUTHORIZATION_INVALID", self.guard.initialize)
        self.authorize()
        auth = json.loads(self.paths.authorization.read_text())
        auth["target"] = str(self.paths.target)  # Workspace is not the project directory.
        self.paths.authorization.write_text(json.dumps(auth))
        self.assert_error("AUTHORIZATION_INVALID", self.guard.initialize)
        self.assertFalse(self.paths.claim.exists())
        self.assertFalse(self.paths.lock.exists())

    def test_initialize_exclusive_and_never_creates_target(self):
        self.authorize()
        calls = []
        real_open = os.open
        def capture(path, flags, *args, **kwargs):
            calls.append((str(path), flags))
            return real_open(path, flags, *args, **kwargs)
        with patch.object(pilot.os, "open", side_effect=capture):
            self.guard.initialize()
        self.assertTrue(any(path == str(self.paths.claim) and flags & os.O_EXCL for path, flags in calls))
        self.assertFalse(self.paths.target.exists())
        self.assert_error("CLAIM_EXISTS", self.guard.initialize)
        self.assertIn(b'"event":"initialized"', self.paths.ledger.read_bytes())
        self.assertTrue(self.guard._anchor_path().is_file())

    def test_existing_target_or_orphan_ledger_fails_closed(self):
        self.authorize(); self.paths.target.mkdir()
        self.assert_error("CLAIM_EXISTS", self.guard.initialize)
        self.assertFalse(self.paths.claim.exists())
        self.paths.target.rmdir(); self.paths.ledger.write_bytes(b"orphan")
        self.assert_error("CLAIM_EXISTS", self.guard.initialize)
        self.assertFalse(self.paths.claim.exists())

    def test_exclusive_create_never_overwrites_and_interrupted_init_cannot_restart(self):
        self.authorize()
        self.paths.claim.write_bytes(b"original")
        self.assert_error("CLAIM_EXISTS", pilot._create, self.paths.claim, b"replacement")
        self.assertEqual(self.paths.claim.read_bytes(), b"original")
        self.assert_error("CLAIM_EXISTS", self.guard.initialize)
        self.assertFalse(self.paths.ledger.exists())

    def test_durable_unknown_stops_any_redelivery(self):
        self.authorize(); self.guard.initialize()
        self.request("selection")
        outcome = self.guard.reserve("selection")
        self.assertEqual(outcome["status"], "unknown_do_not_redispatch")
        self.assertIn(b'"event":"reserved"', self.paths.ledger.read_bytes())
        self.assert_error("ALREADY_RESERVED", self.guard.reserve, "selection")
        self.assert_error("OUTCOME_UNKNOWN", self.guard.reserve, "fixed-pair")
        self.assertEqual(self.guard.status()["states"]["selection"]["status"], "unknown")

    def test_full_ticket_sequence_response_binding_and_conflict(self):
        self.authorize(); self.guard.initialize()
        first = self.finish("selection")
        self.assertTrue(self.guard.complete("selection", first)["replayed"])
        self.assert_error("RESPONSE_CONFLICT", self.guard.complete, "selection", "f" * 64)
        self.finish("fixed-pair"); self.finish("saved-audit"); self.finish("plan-revision"); self.finish("independent-review")
        status = self.guard.status()
        self.assertEqual((status["delegation_limit"], status["tool_limit"]), (3, 2))
        self.assertEqual(len(status["states"]), 5)
        self.artifact("selection", b"changed")
        self.assert_error("RESPONSE_CHANGED", self.guard.complete, "selection", first)

    def test_budget_is_upper_bound_not_default_refill(self):
        self.authorize(delegations=1, tools=1); self.guard.initialize()
        self.finish("selection"); self.finish("fixed-pair")
        self.assert_error("LIMIT_EXHAUSTED", self.guard.reserve, "saved-audit")
        self.assert_error("LIMIT_EXHAUSTED", self.guard.reserve, "plan-revision")
        self.authorize(delegations=3, tools=2)
        self.assert_error("CLAIM_INVALID", self.guard.reserve, "plan-revision")

    def test_concurrent_reservation_has_one_winner(self):
        self.authorize(); self.guard.initialize()
        self.request("selection")
        ctx = multiprocessing.get_context("fork"); queue = ctx.Queue()
        processes = [ctx.Process(target=reserve_in_child, args=(self.paths, self.manifest, queue)) for _ in range(2)]
        for process in processes: process.start()
        for process in processes: process.join(5); self.assertEqual(process.exitcode, 0)
        self.assertEqual(sorted(queue.get(timeout=2) for _ in processes), ["ALREADY_RESERVED", "unknown_do_not_redispatch"])
        self.assertEqual(len(self.paths.ledger.read_bytes().splitlines()), 2)

    def test_bad_ledger_and_changed_provenance_fail_closed(self):
        self.authorize(); self.guard.initialize()
        initial = self.paths.ledger.read_bytes()
        self.paths.ledger.write_bytes(b'{"truncated":')
        self.assert_error("LEDGER_INVALID", self.guard.reserve, "selection")
        self.paths.ledger.write_bytes(initial)
        self.paths.inputs[0].write_text("changed")
        self.assert_error("INPUT_CHANGED", self.guard.reserve, "selection")
        self.assertEqual(self.paths.ledger.read_bytes(), initial)

    def test_artifact_symlink_is_rejected(self):
        self.authorize(); self.guard.initialize(); self.request("selection"); self.guard.reserve("selection")
        directory = self.paths.target / "artifacts"
        (directory / "selection.json").symlink_to(self.paths.proposal)
        self.assert_error("UNSAFE_PATH", self.guard.complete, "selection", self.sha(self.paths.proposal))
        self.assertEqual(self.guard.status()["states"]["selection"]["status"], "unknown")

    def test_empty_or_unanchored_ledger_and_incomplete_init_fail_closed(self):
        self.authorize(); self.guard.initialize()
        original = self.paths.ledger.read_bytes()
        self.paths.ledger.write_bytes(b"")
        self.assert_error("LEDGER_INVALID", self.guard.reserve, "selection")
        self.paths.ledger.write_bytes(original)
        self.guard._anchor_path().unlink()
        self.assert_error("FILE_UNAVAILABLE", self.guard.reserve, "selection")
        self.assert_error("CLAIM_EXISTS", self.guard.initialize)

    def test_request_bytes_bound_before_reserve_and_rechecked_on_complete(self):
        self.authorize(); self.guard.initialize()
        self.assert_error("FILE_UNAVAILABLE", self.guard.reserve, "selection")
        request_sha = self.request("selection")
        result = self.guard.reserve("selection")
        self.assertEqual(result["request_sha256"], request_sha)
        digest = self.artifact("selection")
        self.request("selection", b"changed")
        self.assert_error("REQUEST_CHANGED", self.guard.complete, "selection", digest)
        self.assert_error("REQUEST_CHANGED", self.guard.reserve, "fixed-pair")
        self.assertIn(b'"event":"reserved"', self.paths.ledger.read_bytes())

    def test_changed_prior_response_prevents_next_reservation(self):
        self.authorize(); self.guard.initialize(); self.finish("selection")
        self.request("fixed-pair")
        self.artifact("selection", b"different")
        self.assert_error("RESPONSE_CHANGED", self.guard.reserve, "fixed-pair")


if __name__ == "__main__":
    unittest.main()
