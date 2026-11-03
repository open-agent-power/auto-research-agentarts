"""Two read-only host-report checks; mocked CLI bytes and real tiny controllers."""
import base64
import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import test_local_workbench as fixtures
from autoresearch.contracts import ResearchError, canonical
from autoresearch.host_model_report import capture_host_models, host_model_report_current, host_model_snapshot_sha256
from autoresearch.host_model_selection import HostModelSelection
from autoresearch.local_workbench import LocalWorkbench
from autoresearch.project_controller import ProjectController


class HostModelReportTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.number = 0

    def project(self):
        self.number += 1
        manager = LocalWorkbench(self.root / str(self.number))
        manager.create(fixtures.LocalWorkbenchTests.create_body(self))
        project, _ = manager.binding()
        return project, HostModelSelection(project.root)

    def prepare(self, project, journal, *, provider="delegated"):
        return journal.prepare(request_id="host-1", provider=provider,
            expected_state_version=project.status()["state_version"], decision_limit=1,
            cli_budget_usd=0.1, reason="Read-only report fixture scope",
            executable=str(Path(__file__).absolute()) if provider == "claude_cli" else None)

    def tree_bytes(self, root):
        return {str(path.relative_to(root)): path.read_bytes() for path in root.rglob("*") if path.is_file()}

    def test_original_cli_bytes_usage_and_completed_child_are_captured_without_execution(self):
        for outcome in ("completed", "unknown", "invalid"):
            with self.subTest(outcome=outcome):
                project, journal = self.project()
                prepared = self.prepare(project, journal, provider="claude_cli")
                candidate = next(c for c in prepared["context"]["candidates"]
                                 if c["method_id"] == "data.tabular-quality-audit")
                arguments = {"choice": {"kind": "execute", "candidate_id": candidate["id"]},
                             "rationale": "保留原始零值，先核对冻结表格。", "evidence_citation_ids": []}
                envelope = {"type": "result", "subtype": "success", "is_error": False,
                            "result": canonical(arguments), "modelUsage": {"fixture-route": {"costUSD": 0.02}},
                            "usage": {"input_tokens": 23, "output_tokens": 17}, "total_cost_usd": 0.02}
                raw = canonical(envelope).encode("utf-8") + b"\r\n"
                if outcome == "unknown":
                    raw = b"\xffunfinished original response"
                elif outcome == "invalid":
                    raw = b"not valid JSON\r\n"
                def transport(**kwargs):
                    folder, prompt = kwargs["directory"], kwargs["prompt"].encode("utf-8")
                    launch = {"argv": [kwargs["executable"], "--system-prompt", kwargs["system_prompt"]],
                              "stdin_sha256": hashlib.sha256(prompt).hexdigest(), "stdin_bytes": len(prompt),
                              "configured_max_budget_usd": kwargs["max_budget_usd"]}
                    (folder / "launch.json").write_text(canonical(launch), encoding="utf-8")
                    (folder / "stdout.bin").write_bytes(raw)
                    (folder / "stderr.bin").write_bytes(b"")
                    if outcome == "unknown":
                        (folder / "exit.json").write_bytes(b"")
                        raise OSError("Fixture interrupted before the final receipt")
                    receipt = {"status": "received", "exit_code": 0, "stdout_file": "stdout.bin",
                               "stdout_bytes": len(raw), "stdout_sha256": hashlib.sha256(raw).hexdigest()}
                    (folder / "exit.json").write_text(canonical(receipt), encoding="utf-8")
                    return receipt
                with patch("autoresearch.host_model_selection.run_claude_selection", side_effect=transport) as dispatch:
                    received = journal.request(request_id="host-1")
                    dispatch.assert_called_once()
                if outcome == "completed":
                    applied = journal.consume(request_id="host-1")
                    self.assertEqual(applied["outcome"]["status"], "completed")
                    self.assertEqual(len(project.status()["actions"]), 1)
                else:
                    self.assertEqual(received["status"], outcome)
                    self.assertEqual(project.status()["actions"], [])
                before = self.tree_bytes(project.root)
                with patch.object(HostModelSelection, "request", side_effect=AssertionError("No requests during export")), \
                        patch.object(HostModelSelection, "consume", side_effect=AssertionError("No consume during export")):
                    captured = capture_host_models(project.root)
                    self.assertEqual(host_model_snapshot_sha256(project.root), captured["snapshot_sha256"])
                    self.assertTrue(host_model_report_current(project.root,
                        {"host_model_snapshot_sha256": captured["snapshot_sha256"]}))
                self.assertEqual(self.tree_bytes(project.root), before)
                self.assertEqual(captured["records"], [journal.status(request_id="host-1")])
                self.assertEqual(captured["status"], journal.status())
                assets = {asset["name"]: asset for asset in captured["assets"]}
                for asset in assets.values():
                    original = base64.b64decode(asset["bytes_base64"])
                    relative = asset["name"].removeprefix("host-model-evidence/")
                    self.assertEqual(original, (journal.directory / relative).read_bytes())
                    self.assertEqual(asset["bytes"], len(original))
                    self.assertEqual(asset["sha256"], hashlib.sha256(original).hexdigest())
                self.assertEqual(base64.b64decode(assets["host-model-evidence/requests/0001/transport/stdout.bin"]["bytes_base64"]), raw)
                self.assertEqual(assets["host-model-evidence/requests/0001/transport/stderr.bin"]["bytes"], 0)
                usage = captured["status"]["usage"]
                self.assertEqual(usage["cli_launch_attempts"], 1)
                self.assertEqual(usage["cli_cost_unknown"], outcome != "completed")
                if outcome == "completed":
                    self.assertEqual(usage["known_cli_reported_cost_usd"], 0.02)
                    self.assertEqual(captured["records"][0]["reported_models"], ["fixture-route"])
                    (journal.directory / "requests/0001/transport/stdout.bin").write_bytes(b"changed original response")
                    with self.assertRaises(ResearchError) as caught:
                        capture_host_models(project.root)
                    self.assertEqual(caught.exception.code, "EVIDENCE_CHANGED")
                    self.assertFalse(host_model_report_current(project.root,
                        {"host_model_snapshot_sha256": captured["snapshot_sha256"]}))
                elif outcome == "unknown":
                    self.assertEqual(assets["host-model-evidence/requests/0001/transport/exit.json"]["bytes"], 0)

    def test_no_journal_is_created_and_new_host_or_old_external_decisions_make_reports_stale(self):
        project, journal = self.project()
        before = self.tree_bytes(project.root)
        empty = capture_host_models(project.root)
        self.assertEqual(empty["records"], [])
        self.assertEqual(empty["assets"], [])
        self.assertFalse(journal.directory.exists())
        self.assertTrue(host_model_report_current(project.root, {}))
        self.assertEqual(self.tree_bytes(project.root), before)
        original_version = project.status()["state_version"]
        prepared = self.prepare(project, journal)
        self.assertEqual(project.status()["state_version"], original_version)
        current = capture_host_models(project.root)
        self.assertEqual(current["records"], [prepared])
        self.assertNotEqual(current["snapshot_sha256"], empty["snapshot_sha256"])
        self.assertFalse(host_model_report_current(project.root, {"host_model_snapshot_sha256": empty["snapshot_sha256"]}))
        self.assertFalse(host_model_report_current(project.root, {}))
        other, other_journal = self.project()
        context = ProjectController(other.root).selection_context()
        proposal = fixtures.LocalWorkbenchTests.proposal(self, context, "data.tabular-quality-audit")
        proposal["provider"] = {"kind": "external_model", "label": "Original external fixture without a host receipt"}
        ProjectController(other.root).advance_selection(request_id="old-external", proposal=proposal,
                                                         expected_state_version=context["state_version"])
        prior = capture_host_models(other.root)
        self.assertFalse(other_journal.directory.exists())
        self.assertEqual(prior["status"]["usage"]["unlinked_external_selection_count"], 1)
        self.assertEqual(prior["status"]["usage"]["prior_external_usage"], "unknown_not_zero")
        self.assertEqual(prior["status"]["usage"]["cash_settlement"], "unknown")
        self.assertFalse(host_model_report_current(other.root, {}))


if __name__ == "__main__":
    unittest.main()
