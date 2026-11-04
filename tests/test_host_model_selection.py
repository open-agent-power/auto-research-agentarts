"""Three host-journal checks using real tiny projects and mocked CLI transport."""
import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import test_local_workbench as fixtures
from autoresearch.contracts import ResearchError, canonical
from autoresearch.host_model_selection import HostModelSelection
from autoresearch.local_workbench import LocalWorkbench
from autoresearch.project_controller import ProjectController


class HostModelSelectionTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.project_number = 0

    def project(self):
        self.project_number += 1
        manager = LocalWorkbench(self.root / str(self.project_number))
        manager.create(fixtures.LocalWorkbenchTests.create_body(self))
        project, _ = manager.binding()
        return project, HostModelSelection(project.root)

    def specification(self, project, *, provider="delegated", request_id="host-1"):
        return {"request_id": request_id, "provider": provider,
                "expected_state_version": project.status()["state_version"], "decision_limit": 1,
                "cli_budget_usd": 0.1, "reason": "Explicit bounded fixture validation",
                "executable": str(Path(__file__).absolute()) if provider == "claude_cli" else None}

    def arguments(self, record):
        candidate = next(c for c in record["context"]["candidates"]
                         if c["method_id"] == "data.tabular-quality-audit")
        return {"choice": {"kind": "execute", "candidate_id": candidate["id"]},
                "rationale": "Check declared missing and zero values before interpreting the table.",
                "evidence_citation_ids": []}

    def response(self, journal, record):
        response = self.root / (str(self.project_number) + "-response.json")
        response.write_bytes(canonical(self.arguments(record)).encode("utf-8"))
        return journal.import_response(request_id=record["request_id"], response_file=response), response

    def assert_code(self, code, callback, **kwargs):
        with self.assertRaises(ResearchError) as caught:
            callback(**kwargs)
        self.assertEqual(caught.exception.code, code)

    def test_delegated_apply_interruption_recovers_core_child_and_preserves_original_limit(self):
        project, journal = self.project()
        specification = self.specification(project)
        prepared = journal.prepare(**specification)
        self.assertEqual(journal.prepare(**specification), prepared)
        received, response = self.response(journal, prepared)
        self.assertEqual(received["status"], "received")
        self.assertEqual(journal.import_response(request_id="host-1", response_file=response), received)
        self.assertFalse(received["execution_declaration"]["execution_verified"])
        self.assertEqual(received["execution_declaration"]["inference_count"], "unknown")
        original_save = journal._save
        def interrupt_after_core_commit(state):
            if state["requests"]["host-1"]["status"] == "applied":
                raise KeyboardInterrupt("Fixture interruption after durable controller completion")
            original_save(state)
        with patch.object(journal, "_save", side_effect=interrupt_after_core_commit):
            with self.assertRaises(KeyboardInterrupt):
                journal.consume(request_id="host-1")
        before = project.status()
        self.assertEqual(len(before["actions"]), 1)
        child_id = before["controller_requests"][0]["child_request_id"]
        self.assertEqual(before["actions"][0]["request_id"], child_id)
        reloaded = HostModelSelection(project.root)
        self.assertEqual(reloaded.status(request_id="host-1")["status"], "received")
        applied = reloaded.consume(request_id="host-1")
        self.assertEqual((applied["status"], applied["outcome"]["status"]), ("applied", "completed"))
        self.assertTrue(applied["outcome"]["replayed"])
        self.assertEqual(applied["outcome"]["child_request_id"], child_id)
        self.assertEqual(reloaded.consume(request_id="host-1"), applied)
        self.assertEqual(reloaded.prepare(**specification), applied)
        self.assertEqual(project.status()["actions"], before["actions"])
        self.assert_code("HOST_DECISION_LIMIT", reloaded.prepare, **{**specification, "request_id": "new-id"})
        self.assert_code("HOST_GRANT_CHANGED", reloaded.prepare,
                         **{**specification, "request_id": "new-id", "decision_limit": 2})
        self.assert_code("IDEMPOTENCY_CONFLICT", reloaded.prepare, **{**specification, "decision_limit": 2})
        response.write_bytes(b'{"changed":true}')
        self.assert_code("IDEMPOTENCY_CONFLICT", reloaded.import_response, request_id="host-1", response_file=response)
        usage = reloaded.status()["usage"]
        self.assertEqual((usage["decision_slots_used"], usage["cli_launch_attempts"],
                          usage["delegated_outputs_received"]), (1, 0, 1))
        self.assertEqual(usage["delegated_inferences_and_cost"], "unknown")

    def test_cli_receipts_replay_unknown_and_invalid_never_dispatch_twice(self):
        for outcome in ("received", "unknown", "invalid", "interrupted"):
            with self.subTest(outcome=outcome):
                project, journal = self.project()
                prepared = journal.prepare(**self.specification(project, provider="claude_cli"))
                envelope = {"type": "result", "subtype": "success", "is_error": False,
                            "result": canonical(self.arguments(prepared)), "modelUsage": {"fixture-route": {}},
                            "usage": {"input_tokens": 23, "output_tokens": 17}, "total_cost_usd": 0.02}
                raw = (b"incomplete JSON" if outcome == "invalid" else b"" if outcome == "unknown"
                       else canonical(envelope).encode("utf-8"))
                def transport(**kwargs):
                    directory = kwargs["directory"]
                    prompt = kwargs["prompt"].encode("utf-8")
                    launch = {"argv": [kwargs["executable"], "--system-prompt", kwargs["system_prompt"]],
                              "stdin_sha256": hashlib.sha256(prompt).hexdigest(), "stdin_bytes": len(prompt),
                              "configured_max_budget_usd": kwargs["max_budget_usd"]}
                    (directory / "launch.json").write_text(canonical(launch), encoding="utf-8")
                    (directory / "stdout.bin").write_bytes(raw)
                    (directory / "stderr.bin").write_bytes(b"")
                    if outcome == "interrupted":
                        raise OSError("Fixture lost transport receipt after possible dispatch")
                    receipt = {"status": "unknown" if outcome == "unknown" else "received",
                               "exit_code": None if outcome == "unknown" else 0, "stdout_file": "stdout.bin",
                               "stdout_bytes": len(raw), "stdout_sha256": hashlib.sha256(raw).hexdigest()}
                    (directory / "exit.json").write_text(canonical(receipt), encoding="utf-8")
                    return receipt
                with patch("autoresearch.host_model_selection.run_claude_selection", side_effect=transport) as dispatch:
                    received = journal.request(request_id="host-1")
                    self.assertEqual(journal.request(request_id="host-1"), received)
                    self.assertEqual(HostModelSelection(project.root).request(request_id="host-1"), received)
                    dispatch.assert_called_once()
                expected = "unknown" if outcome == "interrupted" else outcome
                self.assertEqual(received["status"], expected)
                usage = journal.status()["usage"]
                self.assertEqual(usage["cli_launch_attempts"], 1)
                self.assertEqual(usage["cli_cost_unknown"], outcome != "received")
                if outcome == "received":
                    applied = journal.consume(request_id="host-1")
                    self.assertEqual(applied["outcome"]["status"], "completed")
                    self.assertEqual(len(project.status()["actions"]), 1)
                    self.assertEqual(usage["known_cli_reported_cost_usd"], 0.02)
                else:
                    self.assert_code("HOST_RESPONSE_NOT_READY", journal.consume, request_id="host-1")
                    self.assertEqual(project.status()["actions"], [])
                    self.assertEqual(project.status().get("controller_requests", []), [])

    def test_stale_context_and_changed_raw_evidence_cannot_execute_host_proposal(self):
        for change in ("context", "response", "before-cli"):
            with self.subTest(change=change):
                project, journal = self.project()
                specification = self.specification(
                    project, provider="claude_cli" if change == "before-cli" else "delegated")
                if change == "before-cli":
                    specification["decision_limit"] = 2
                prepared = journal.prepare(**specification)
                if change != "before-cli":
                    received, _ = self.response(journal, prepared)
                if change == "response":
                    (journal.directory / received["response_file"]).write_bytes(b'{"changed":true}')
                    self.assert_code("EVIDENCE_CHANGED", journal.consume, request_id="host-1")
                    self.assertEqual(project.status()["actions"], [])
                else:
                    context = prepared["context"]
                    human = fixtures.LocalWorkbenchTests.proposal(self, context, "data.tabular-quality-audit")
                    ProjectController(project.root).advance_selection(request_id="human-change", proposal=human,
                                                                       expected_state_version=context["state_version"])
                    before = project.status()
                    if change == "before-cli":
                        with patch("autoresearch.host_model_selection.run_claude_selection") as dispatch:
                            self.assert_code("STALE_SELECTION_CONTEXT", journal.request, request_id="host-1")
                            stale = journal.status(request_id="host-1")
                            self.assertEqual(stale["status"], "stale")
                            self.assertFalse(stale["cli_launch_attempted"])
                            next_request = journal.prepare(**{**specification, "request_id": "new-context",
                                "expected_state_version": before["state_version"]})
                            self.assertEqual(next_request["status"], "prepared")
                            self.assertEqual(next_request["context"]["state_version"], before["state_version"])
                            self.assertFalse(next_request["cli_launch_attempted"])
                            dispatch.assert_not_called()
                    else:
                        self.assertEqual(journal.consume(request_id="host-1")["status"], "stale")
                    after = project.status()
                    self.assertEqual(after["actions"], before["actions"])
                    self.assertEqual(after["controller_requests"], before["controller_requests"])


if __name__ == "__main__":
    unittest.main()
