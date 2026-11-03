"""Two usage regressions with explicitly fake CLI transport and real host journals."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import test_local_workbench as fixtures
from autoresearch.contracts import ResearchError, canonical
from autoresearch.host_model_report import capture_host_models
from autoresearch.host_model_selection import HostModelSelection
from autoresearch.host_selection_protocol import parse_cli_usage
from autoresearch.local_workbench import LocalWorkbench
from autoresearch.project_controller import ProjectController
from autoresearch.project_report import _host_model_rows, _host_request_rows


class HostFailedUsageTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.number = 0

    def fresh(self):
        self.number += 1
        manager = LocalWorkbench(self.root / str(self.number))
        manager.create(fixtures.LocalWorkbenchTests.create_body(self))
        project, _ = manager.binding()
        return project, HostModelSelection(project.root)

    def prepare(self, project, journal, request_id):
        return journal.prepare(request_id=request_id, provider="claude_cli", executable=str(Path(__file__).absolute()),
            expected_state_version=project.status()["state_version"], decision_limit=3, cli_budget_usd=0.1,
            reason="Explicit fixture-only CLI budget observation")

    @staticmethod
    def envelope(cost, *, failed=False, invalid=False):
        envelope = {"type": "result", "subtype": "error_max_budget_usd" if failed else "success", "is_error": failed,
                    "modelUsage": {"fixture-route": {}}, "usage": {"input_tokens": 23, "output_tokens": 17}, "total_cost_usd": cost}
        if not failed:
            envelope["result"] = "not a JSON proposal" if invalid else canonical({"choice": {"kind": "wait"},
                "rationale": "Wait in this fixture without executing research.", "evidence_citation_ids": []})
        return envelope

    @staticmethod
    def transport(raw, *, failed=False):
        def run(**kwargs):
            folder, prompt = kwargs["directory"], kwargs["prompt"].encode("utf-8")
            launch = {"argv": [kwargs["executable"], "--system-prompt", kwargs["system_prompt"]],
                      "stdin_sha256": hashlib.sha256(prompt).hexdigest(), "stdin_bytes": len(prompt),
                      "configured_max_budget_usd": kwargs["max_budget_usd"]}
            (folder / "launch.json").write_text(canonical(launch), encoding="utf-8")
            (folder / "stdout.bin").write_bytes(raw)
            (folder / "stderr.bin").write_bytes(b"")
            receipt = {"status": "failed" if failed else "received", "exit_code": 1 if failed else 0,
                       "stdout_file": "stdout.bin", "stdout_bytes": len(raw), "stdout_sha256": hashlib.sha256(raw).hexdigest()}
            (folder / "exit.json").write_text(canonical(receipt), encoding="utf-8")
            return receipt
        return run

    def test_terminal_budget_failure_reconciles_original_usage_idempotently_and_blocks_further_spend(self):
        project, journal = self.fresh()
        first_raw = canonical(self.envelope(0.06301000000000001)).encode("utf-8")
        failed_raw = canonical(self.envelope(0.061024999999999996, failed=True)).encode("utf-8")
        self.prepare(project, journal, "first")
        with patch("autoresearch.host_model_selection.run_claude_selection", side_effect=self.transport(first_raw)):
            journal.request(request_id="first")
        self.assertEqual(journal.consume(request_id="first")["status"], "applied")
        self.prepare(project, journal, "budget-failed")
        with patch("autoresearch.host_model_selection.run_claude_selection", side_effect=self.transport(failed_raw, failed=True)):
            failed = journal.request(request_id="budget-failed")
        self.assertEqual((failed["status"], failed["reported_cost_usd"]), ("failed", 0.061024999999999996))
        self.assertNotIn("arguments", failed)
        with journal._writer():
            legacy = journal._load()
            legacy["requests"]["budget-failed"]["reported_cost_usd"] = None
            for key in ("reported_models", "reported_usage", "response_file", "response_sha256"):
                legacy["requests"]["budget-failed"].pop(key, None)
            journal._save(legacy)  # Fixture: state written by the old implementation, same original transport.
        original_core = project.db.read_bytes()
        transport_folder = journal.directory / failed["directory"] / "transport"
        originals = {path.name: path.read_bytes() for path in transport_folder.iterdir()}
        with patch("autoresearch.host_model_selection.run_claude_selection", side_effect=AssertionError("No CLI reconciliation")) as dispatch, \
                patch.object(ProjectController, "advance_selection", side_effect=AssertionError("No research reconciliation")):
            fixed = journal.reconcile_usage(request_id="budget-failed")
            self.assertEqual((fixed["status"], fixed["reported_cost_usd"], fixed["reported_models"]), ("failed", 0.061024999999999996, ["fixture-route"]))
            self.assertNotIn("arguments", fixed)
            after_reconcile = journal.state_file.read_bytes()
            self.assertEqual(journal.reconcile_usage(request_id="budget-failed"), fixed)
            self.assertEqual(journal.state_file.read_bytes(), after_reconcile)
            self.assertEqual(project.db.read_bytes(), original_core)
            self.assertEqual({path.name: path.read_bytes() for path in transport_folder.iterdir()}, originals)
            captured = capture_host_models(project.root)
            self.assertAlmostEqual(captured["status"]["usage"]["known_cli_reported_cost_usd"], 0.124035)
            self.assertFalse(captured["status"]["usage"]["cli_cost_unknown"])
            rows = dict(_host_model_rows({"host_models": captured}))
            self.assertEqual(rows["CLI配置预算阈值 / USD"], "0.1")
            self.assertEqual(rows["已知CLI报告估值超出配置阈值"], "是")
            with journal._writer():
                corrupted = journal._load()
                corrupted["requests"]["budget-failed"]["reported_cost_usd"] = 0.001
                journal._save(corrupted)
            try:
                with self.assertRaises(ResearchError):
                    capture_host_models(project.root)
            finally:
                journal.state_file.write_bytes(after_reconcile)
            self.prepare(project, journal, "third-must-not-send")
            with self.assertRaises(ResearchError) as caught:
                journal.request(request_id="third-must-not-send")
            self.assertEqual(caught.exception.code, "HOST_CLI_BUDGET_EXHAUSTED")
            dispatch.assert_not_called()

    def test_invalid_proposal_keeps_reported_cost_and_partial_missing_bad_metadata_stay_unknown(self):
        missing = self.envelope(None, failed=True)
        missing.pop("total_cost_usd")
        cases = [(canonical(self.envelope(0.02, invalid=True)).encode(), False, "invalid", 0.02),
                 (canonical(missing).encode(), True, "failed", None),
                 (b'{"type":"result","total_cost_usd":0.02', True, "failed", None),
                 (canonical(self.envelope("0.02", failed=True)).encode(), True, "failed", None)]
        for raw, terminal_failed, expected_status, cost in cases:
            with self.subTest(expected_status=expected_status, raw=raw[:40]):
                project, journal = self.fresh()
                self.prepare(project, journal, "response")
                with patch("autoresearch.host_model_selection.run_claude_selection", side_effect=self.transport(raw, failed=terminal_failed)) as dispatch:
                    received = journal.request(request_id="response")
                    self.assertEqual((received["status"], received["reported_cost_usd"]), (expected_status, cost))
                    self.assertNotIn("arguments", received)
                    self.assertEqual(journal.reconcile_usage(request_id="response"), received)
                    self.assertEqual(journal.request(request_id="response"), received)
                    with self.assertRaises(ResearchError) as caught:
                        journal.consume(request_id="response")
                    self.assertEqual(caught.exception.code, "HOST_RESPONSE_NOT_READY")
                    dispatch.assert_called_once()
                captured = capture_host_models(project.root)
                self.assertEqual(captured["status"]["usage"]["cli_cost_unknown"], cost is None)
                self.assertEqual(len(_host_request_rows({"host_models": captured})), 1)
                self.assertEqual(project.status()["actions"], [])
                self.assertEqual(project.status().get("controller_requests", []), [])
                if raw.startswith(b'{"type":"result","total_cost_usd"') or b'"total_cost_usd":"0.02"' in raw:
                    with self.assertRaises(ResearchError):
                        parse_cli_usage(raw)


if __name__ == "__main__":
    unittest.main()
