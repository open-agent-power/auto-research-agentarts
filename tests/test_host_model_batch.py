"""Two bounded-batch checks; real tiny controllers and explicitly mocked CLI transport."""
import base64
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import test_local_evidence as evidence_fixtures
import test_local_workbench as fixtures
from autoresearch.contracts import ResearchError, canonical
from autoresearch.host_model_batch import HostModelBatch
from autoresearch.host_model_report import capture_host_models
from autoresearch.host_model_selection import HostModelSelection
from autoresearch.local_workbench import LocalWorkbench


class HostModelBatchTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.number = 0
        self.contexts = []

    def fresh(self, request_id="two-decisions"):
        self.number += 1
        self.manager = LocalWorkbench(self.root / str(self.number))
        self.manager.create(fixtures.LocalWorkbenchTests.create_body(self))
        self.project, _ = self.manager.binding()
        self.contexts = []
        specification = {"request_id": request_id, "expected_state_version": 0, "max_decisions": 2,
                         "decision_limit": 2, "cli_budget_usd": 0.1, "reason": "Explicit two-decision fixture scope",
                         "executable": str(Path(__file__).absolute())}
        return HostModelBatch(self.project.root), specification

    def transport(self, *, unknown=False, **kwargs):
        context = json.loads(kwargs["prompt"].split("\n", 1)[1])
        self.contexts.append(context)
        candidate = context["candidates"][0]
        arguments = {"choice": {"kind": "execute", "candidate_id": candidate["id"]},
                     "rationale": "Use this frozen fixture candidate and its actual predecessor binding.", "evidence_citation_ids": []}
        raw = b"" if unknown else canonical({"type": "result", "subtype": "success", "is_error": False,
            "result": canonical(arguments), "modelUsage": {"fixture-route": {}}, "usage": {"input_tokens": 23, "output_tokens": 17},
            "total_cost_usd": 0.02}).encode("utf-8")
        folder, incoming = kwargs["directory"], kwargs["prompt"].encode("utf-8")
        launch = {"argv": [kwargs["executable"], "--system-prompt", kwargs["system_prompt"]],
                  "stdin_sha256": hashlib.sha256(incoming).hexdigest(), "stdin_bytes": len(incoming),
                  "configured_max_budget_usd": kwargs["max_budget_usd"]}
        (folder / "launch.json").write_text(canonical(launch), encoding="utf-8")
        (folder / "stdout.bin").write_bytes(raw)
        (folder / "stderr.bin").write_bytes(b"")
        receipt = {"status": "unknown" if unknown else "received", "exit_code": None if unknown else 0,
                   "stdout_file": "stdout.bin", "stdout_bytes": len(raw), "stdout_sha256": hashlib.sha256(raw).hexdigest()}
        (folder / "exit.json").write_text(canonical(receipt), encoding="utf-8")
        return receipt

    def tree(self):
        return {str(path.relative_to(self.project.root)): path.read_bytes() for path in self.project.root.rglob("*") if path.is_file()}

    def test_latest_feedback_drives_two_decisions_complete_replay_and_report_capture_are_readonly(self):
        batch, specification = self.fresh()
        initial_capture = capture_host_models(self.project.root)
        self.assertNotIn("batches", initial_capture)
        with patch("autoresearch.host_model_selection.run_claude_selection", side_effect=self.transport) as dispatch:
            result = batch.advance(**specification)
            self.assertEqual((result["status"], result["record_status"], len(result["steps"])), ("limit_reached", "completed", 2))
            self.assertEqual(dispatch.call_count, 2)
            self.assertEqual(len(self.contexts), 2)
            self.assertEqual(self.contexts[0]["candidates"][0]["method_id"], "data.tabular-quality-audit")
            self.assertEqual(self.contexts[1]["candidates"][0]["method_id"], "data.grouped-quality-profile")
            self.assertGreater(self.contexts[1]["state_version"], self.contexts[0]["state_version"])
            state = self.project.status()
            self.assertEqual(self.contexts[1]["candidates"][0]["parameters"]["based_on_action_id"], state["actions"][0]["id"])
            self.assertEqual((state["budget"]["local_tool_calls_used"], state["budget"]["new_model_requests"]), (2, 0))
            self.assertEqual(result["allowed_source_receipt_sha256s"], [])
            before = self.tree()
            captured = capture_host_models(self.project.root)
            self.assertNotEqual(captured["snapshot_sha256"], initial_capture["snapshot_sha256"])
            self.assertEqual(captured["batches"], [result])
            asset = next(item for item in captured["assets"] if item["name"] == "host-model-evidence/batches/batch-two-decisions.json")
            self.assertEqual(asset["role"], "host_model_batch")
            self.assertEqual(base64.b64decode(asset["bytes_base64"]), batch._path("two-decisions").read_bytes())
            self.assertEqual(self.tree(), before)
            self.assertEqual(HostModelBatch(self.project.root).advance(**specification), result)
            self.assertEqual(self.tree(), before)
            self.assertEqual(dispatch.call_count, 2)
            with self.assertRaises(ResearchError) as caught:
                batch.advance(**{**specification, "max_decisions": 1})
            self.assertEqual(caught.exception.code, "IDEMPOTENCY_CONFLICT")
            with self.assertRaises(ResearchError) as caught:
                batch.advance(**{**specification, "request_id": "cannot-reset", "expected_state_version": state["state_version"], "decision_limit": 3})
            self.assertEqual(caught.exception.code, "HOST_GRANT_CHANGED")

    def test_unknown_and_consume_interruption_resume_original_child_and_new_sources_stop_batch(self):
        batch, specification = self.fresh("unknown")
        with patch("autoresearch.host_model_selection.run_claude_selection", side_effect=lambda **kwargs: self.transport(unknown=True, **kwargs)) as dispatch:
            unknown = batch.advance(**specification)
            self.assertEqual((unknown["status"], unknown["record_status"]), ("unknown", "incomplete"))
            self.assertEqual(batch.advance(**specification), unknown)
            journal = HostModelSelection(self.project.root)
            original = journal.status(request_id=unknown["steps"][0]["host_request_id"])
            receipt = journal.directory / original["directory"] / "transport/exit.json"
            saved_receipt = receipt.read_bytes()
            receipt.write_bytes(b"")  # Fixture: observed receipt exists but its owned process did not finish it.
            incomplete_receipt = batch.advance(**specification)
            self.assertEqual((incomplete_receipt["status"], incomplete_receipt["record_status"]), ("unknown", "incomplete"))
            self.assertEqual(incomplete_receipt["steps"][0]["host_request_id"], unknown["steps"][0]["host_request_id"])
            receipt.write_bytes(saved_receipt)
            self.assertEqual(batch.advance(**specification), unknown)
            replacement = batch.advance(**{**specification, "request_id": "must-not-bypass"})
            self.assertEqual(replacement["stop"]["code"], "HOST_SELECTION_PENDING")
            self.assertEqual(self.project.status()["actions"], [])
            dispatch.assert_called_once()
        batch, specification = self.fresh("consume-interrupted")
        original_save = HostModelSelection._save
        def interrupt_applied(journal, state):
            if any(record["status"] == "applied" for record in state["requests"].values()):
                raise KeyboardInterrupt("Fixture after committed core child, before host applied save")
            original_save(journal, state)
        with patch("autoresearch.host_model_selection.run_claude_selection", side_effect=self.transport) as dispatch:
            with patch.object(HostModelSelection, "_save", interrupt_applied):
                with self.assertRaises(KeyboardInterrupt):
                    batch.advance(**specification)
            child = self.project.status()["actions"][0]["request_id"]
            resumed = HostModelBatch(self.project.root).advance(**specification)
            self.assertEqual((resumed["status"], resumed["steps"][0]["child_request_id"]), ("limit_reached", child))
            self.assertEqual(len(self.project.status()["actions"]), 2)
            self.assertEqual(dispatch.call_count, 2)
        batch, specification = self.fresh("new-source")
        original_batch_save = HostModelBatch._save
        def interrupt_after_first_step(instance, record):
            original_batch_save(instance, record)
            if len(record["steps"]) == 1 and record["steps"][0].get("snapshot_ref_after"):
                raise KeyboardInterrupt("Fixture batch pause before the second decision")
        with patch("autoresearch.host_model_selection.run_claude_selection", side_effect=self.transport) as dispatch:
            with patch.object(HostModelBatch, "_save", interrupt_after_first_step):
                with self.assertRaises(KeyboardInterrupt):
                    batch.advance(**specification)
            self.manager.register_evidence(evidence_fixtures.LocalEvidenceTests.body(self))
            stopped = batch.advance(**specification)
            self.assertEqual((stopped["status"], stopped["stop"]["code"]), ("blocked", "STALE_STATE"))
            self.assertEqual(stopped["allowed_source_receipt_sha256s"], [])
            self.assertEqual(self.project.status()["budget"]["evidence_reads_used"], 0)
            dispatch.assert_called_once()


if __name__ == "__main__":
    unittest.main()
