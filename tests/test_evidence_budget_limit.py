"""Explicit source-budget tightening preserves evidence, usage and original IDs."""

import base64
import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

import test_local_evidence as fixtures
from autoresearch import source_evidence_adapter as reader
from autoresearch.contracts import ResearchError
from autoresearch.project_controller import ProjectController


class EvidenceBudgetLimitTests(unittest.TestCase):
    setUp = fixtures.LocalEvidenceTests.setUp
    body = fixtures.LocalEvidenceTests.body

    def register(self, index):
        body = self.body("budget-source-" + str(index))
        body["sources"][0].update(url="urn:test:budget-source:" + str(index),
            bytes_base64=base64.b64encode(f"Original source {index}.\n".encode()).decode())
        return self.manager.register_evidence(body)["registration"]["receipt_snapshot_sha256"]

    def read_two(self):
        receipts = [self.register(index) for index in range(3)]
        for index in range(2):
            self.project.read_evidence(request_id="budget-read-" + str(index), receipt_snapshot_sha256=receipts[index],
                                       expected_state_version=self.project.status()["state_version"])
        return receipts

    def specification(self, request_id="limit-sources", **changes):
        return {"request_id": request_id, "expected_limit": 8, "new_limit": 2,
                "expected_state_version": self.project.status()["state_version"],
                "reason": "Enforce the existing cumulative two-read research authorization.", **changes}

    def assert_code(self, expected, callback, **arguments):
        with self.assertRaises(ResearchError) as caught:
            callback(**arguments)
        self.assertEqual(caught.exception.code, expected)

    def test_two_used_reads_limit_to_two_removes_source_candidates_and_blocks_new_action(self):
        receipts = self.read_two()
        before = self.project.status()
        originals = {str(path.relative_to(self.project.root)): path.read_bytes()
                     for path in self.project.root.rglob("*") if path.is_file() and path != self.project.db}
        source_candidates = [item for item in ProjectController(self.project.root).selection_context()["candidates"]
                             if item["method_id"] == "research.source-selection"]
        self.assertEqual([item["parameters"]["receipt_snapshot_sha256"] for item in source_candidates], [receipts[2]])
        specification = self.specification()
        revision = self.project.limit_evidence_budget(**specification)
        after = self.project.status()
        self.assertEqual(after["state_version"], before["state_version"] + 1)
        self.assertEqual(after["budget"], {**before["budget"], "evidence_read_limit": 2})
        for field in ("actions", "evidence_actions", "evidence_sources", "evidence_registrations", "knowledge_refs"):
            self.assertEqual(after[field], before[field])
        self.assertEqual((revision["kind"], revision["old_limit"], revision["new_limit"], revision["evidence_reads_preserved"]),
                         ("evidence_read_limit", 8, 2, 2))
        artifact, = self.project.root.glob("artifacts/evidence-budget-*.json")
        snapshot = json.loads(artifact.read_bytes())
        self.assertEqual(snapshot["revision"], revision)
        self.assertEqual(snapshot["budget_before"]["evidence_read_limit"], 8)
        self.assertEqual(revision["request"]["command"], "limit_evidence_budget")
        self.assertTrue(all((self.project.root / name).read_bytes() == raw for name, raw in originals.items()))
        self.assertFalse(any(item["method_id"] == "research.source-selection"
                             for item in ProjectController(self.project.root).selection_context()["candidates"]))
        with patch.object(reader, "execute", side_effect=AssertionError("A stopped source budget must not dispatch")):
            self.assert_code("BUDGET_EXHAUSTED", self.project.read_evidence, request_id="denied-third-read",
                             receipt_snapshot_sha256=receipts[2], expected_state_version=after["state_version"])
        self.assertEqual(self.project.status(), after)
        self.assertEqual(len(after["evidence_sources"]), 3)
        self.assertEqual(len(after["evidence_actions"]), 2)

    def test_original_receipt_replays_under_later_code_without_state_or_file_changes(self):
        specification = self.specification()
        revision = self.project.limit_evidence_budget(**specification)
        before = self.project.status()
        files = {str(path.relative_to(self.project.root)): path.read_bytes() for path in self.project.root.rglob("*") if path.is_file()}
        with patch("autoresearch.research_project.code_identity", return_value="f" * 64):
            self.assertEqual(self.project.limit_evidence_budget(**specification), revision)
            self.assert_code("CODE_CHANGED", self.project.limit_evidence_budget,
                             **self.specification(request_id="needs-current-code", expected_limit=2, new_limit=1))
        self.assertEqual(self.project.status(), before)
        self.assertEqual(files, {str(path.relative_to(self.project.root)): path.read_bytes() for path in self.project.root.rglob("*") if path.is_file()})
        self.assert_code("IDEMPOTENCY_CONFLICT", self.project.limit_evidence_budget,
                         **{**specification, "reason": "A different reason cannot replace a saved request."})

    def test_zero_read_limit_remains_stopped_through_explicit_compatible_upgrade(self):
        receipt = self.register(0)
        self.assertTrue(any(item["method_id"] == "research.source-selection"
                            for item in ProjectController(self.project.root).selection_context()["candidates"]))
        specification = self.specification(new_limit=0)
        revision = self.project.limit_evidence_budget(**specification)
        stopped = self.project.status()
        self.assertEqual((stopped["budget"]["evidence_read_limit"], stopped["budget"]["evidence_reads_used"],
                          stopped["budget"]["evidence_reads_reserved"]), (0, 0, 0))
        self.assertFalse(any(item["method_id"] == "research.source-selection"
                             for item in ProjectController(self.project.root).selection_context()["candidates"]))
        self.assert_code("BUDGET_EXHAUSTED", self.project.read_evidence, request_id="zero-cap-read",
                         receipt_snapshot_sha256=receipt, expected_state_version=stopped["state_version"])
        artifact, = self.project.root.glob("artifacts/evidence-budget-*.json")
        original_receipt_bytes = artifact.read_bytes()
        with patch("autoresearch.research_project.code_identity", return_value="c" * 64):
            upgrade = self.project.upgrade(request_id="zero-cap-compatible-upgrade",
                                           expected_code_identity=stopped["code_identity"], evidence_read_limit=0)
            upgraded = self.project.status()
            self.assertEqual(upgrade["evidence_read_limit"], 0)
            self.assertEqual(upgraded["code_identity"], "c" * 64)
            self.assertEqual(upgraded["state_version"], stopped["state_version"] + 1)
            self.assertEqual(upgraded["budget"], stopped["budget"])
            self.assertEqual(upgraded["actions"], stopped["actions"])
            self.assertEqual(upgraded["evidence_actions"], [])
            self.assertEqual(upgraded["budget_revisions"], stopped["budget_revisions"])
            self.assertEqual(self.project.limit_evidence_budget(**specification), revision)
            self.assertEqual(self.project.status(), upgraded)
        self.assertEqual(artifact.read_bytes(), original_receipt_bytes)

    def test_used_floor_increases_unchanged_caps_stale_state_and_wrong_expected_limit_are_rejected(self):
        self.read_two()
        before = self.project.status()
        for change, code in (({"new_limit": 1}, "BUDGET_EXHAUSTED"), ({"new_limit": 8}, "INVALID_REQUEST"),
                             ({"new_limit": 9}, "INVALID_REQUEST"), ({"new_limit": -1}, "INVALID_REQUEST"),
                             ({"expected_limit": 7}, "CONFIG_CHANGED"),
                             ({"expected_state_version": before["state_version"] + 1}, "STALE_STATE")):
            with self.subTest(change=change):
                self.assert_code(code, self.project.limit_evidence_budget, **self.specification(**change))
        self.assertEqual(self.project.status(), before)
        self.assertEqual(list(self.project.root.glob("artifacts/evidence-budget-*.json")), [])

    def test_new_source_command_cannot_reuse_local_budget_request_or_vice_versa(self):
        self.project.limit_evidence_budget(**self.specification(request_id="source-cap-id"))
        self.assert_code("IDEMPOTENCY_CONFLICT", self.project.extend_local_budget, request_id="source-cap-id",
                         expected_limit=2, new_limit=3, expected_state_version=self.project.status()["state_version"], reason="Wrong command identity")
        local_specification = {"request_id": "local-cap-id", "expected_limit": 2, "new_limit": 3,
                               "expected_state_version": self.project.status()["state_version"], "reason": "Original local allowance change"}
        local = self.project.extend_local_budget(**local_specification)
        before = self.project.status()
        self.assert_code("IDEMPOTENCY_CONFLICT", self.project.limit_evidence_budget,
                         **self.specification(request_id="local-cap-id", expected_limit=2, new_limit=1))
        self.assertEqual(self.project.extend_local_budget(**local_specification), local)
        self.assertEqual(self.project.status(), before)

    def test_unknown_read_keeps_reservation_and_cannot_be_bypassed_by_tightening(self):
        first, second = self.register(0), self.register(1)
        self.project.read_evidence(request_id="first-known", receipt_snapshot_sha256=first)
        with patch.object(reader, "execute", side_effect=KeyboardInterrupt("Constructed missing extraction receipt")):
            with self.assertRaises(KeyboardInterrupt):
                self.project.read_evidence(request_id="second-unknown", receipt_snapshot_sha256=second)
        self.assertEqual(self.project.resume(request_id="second-unknown")["status"], "unknown")
        before = self.project.status()
        self.assertEqual((before["budget"]["evidence_reads_used"], before["budget"]["evidence_reads_reserved"]), (1, 1))
        self.assert_code("EXECUTION_UNKNOWN", self.project.limit_evidence_budget, **self.specification(new_limit=1))
        self.assertEqual(self.project.status(), before)

    def test_cli_tightens_and_replays_the_same_original_request(self):
        self.read_two()
        before = self.project.status()
        root = Path(__file__).resolve().parents[1]
        command = [sys.executable, str(root / "scripts/run_research_project.py"), "limit-evidence-budget",
                   "--workspace", str(self.project.root), "--request-id", "cli-source-cap", "--expected-limit", "8",
                   "--new-limit", "2", "--expected-state-version", str(before["state_version"]),
                   "--reason", "Enforce two reads while preserving every prior action."]
        completed = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", cwd=root, timeout=30)
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        receipt = json.loads(completed.stdout)
        self.assertEqual((receipt["kind"], receipt["old_limit"], receipt["new_limit"]), ("evidence_read_limit", 8, 2))
        after = self.project.status()
        self.assertEqual(after["budget"], {**before["budget"], "evidence_read_limit": 2})
        replay = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", cwd=root, timeout=30)
        self.assertEqual(replay.returncode, 0, replay.stdout + replay.stderr)
        self.assertEqual(json.loads(replay.stdout), receipt)
        self.assertEqual(self.project.status(), after)


if __name__ == "__main__":
    unittest.main()
