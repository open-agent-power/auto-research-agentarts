"""Three real loopback-fixture journal checks; never run Ollama or real model inference."""

import hashlib
import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

import test_local_workbench as fixtures
from autoresearch import local_ollama, tabular_quality_adapter as tabular
from autoresearch.contracts import ResearchError, canonical, fingerprint
from autoresearch.local_workbench import LocalWorkbench
from autoresearch.project_controller import ProjectController
from autoresearch.project_model_proposal import ProjectModelProposal


class SimulatedCrash(BaseException):
    pass


class FixtureTransport:
    def __init__(self):
        self.calls = 0
        self.choice = {"kind": "wait"}
        self.invalid = False
        outer = self
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args): pass
            def do_POST(self):
                outer.calls += 1
                outer.last_payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                arguments = {"choice": outer.choice, "rationale": "Fixture native tool call; no model inference occurred.", "evidence_citation_ids": []}
                if outer.invalid:
                    arguments["parameters"] = {"arbitrary": True}
                raw = canonical({"model": "qwen3:4b", "done": True, "done_reason": "stop", "prompt_eval_count": 32, "eval_count": 16,
                    "message": {"role": "assistant", "content": "", "tool_calls": [{"function": {
                        "name": "propose_research_selection", "arguments": arguments}}]}}).encode("utf-8")
                self.send_response(200); self.send_header("Content-Length", str(len(raw))); self.end_headers(); self.wfile.write(raw)
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True); self.thread.start()

    def close(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join(timeout=5)

    def identity(self):
        return {"schema_version": "project-local-model-identity-v1", "transport": "owned-local-ollama", "model": "qwen3:4b",
                "publisher_manifest_sha256": local_ollama.PUBLISHER_MANIFEST_SHA256, "executable_sha256": "e" * 64, "cloud_disabled": True}

    def send(self, payload, request_id):
        connection = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=5)
        connection.request("POST", "/fixture", body=canonical(payload).encode("utf-8"), headers={"Content-Type": "application/json"})
        response = connection.getresponse(); raw = response.read(); connection.close()
        return raw, {"schema_version": "project-model-transport-receipt-v1", "identity": self.identity(),
                     "request_sha256": fingerprint(payload), "response_sha256": hashlib.sha256(raw).hexdigest(),
                     "execution": "fixture", "process": {"fixture": True, "automatic_retry": False,
                                                           "model_requests": 0, "cloud_requests": 0, "new_fits": 0}}


class ProjectModelProposalTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.manager = LocalWorkbench(self.root / "manager")
        self.counter = 0
        self.transport = FixtureTransport(); self.addCleanup(self.transport.close)

    def project(self, authorize=True):
        self.counter += 1
        self.manager.create(fixtures.LocalWorkbenchTests.create_body(self, "create-" + str(self.counter)))
        project = self.manager.binding()[0]
        if authorize:
            project.authorize_local_model_budget(request_id="fixture-authorization", expected_limit=0, new_limit=1,
                reason="Isolated fixture allowance only; no real model or paid request is authorized by this test.", expected_state_version=project.status()["state_version"])
        return project, ProjectModelProposal(project.root)

    def prepare(self, project, journal, request_id="model-1", execute=True):
        prepared = journal.prepare(request_id, project.status()["state_version"], self.transport.identity())
        self.transport.choice = ({"kind": "execute", "candidate_id": prepared["context"]["candidates"][0]["id"]} if execute else {"kind": "wait"})
        return prepared

    def assert_code(self, code, callback, *args, **kwargs):
        with self.assertRaises(ResearchError) as caught:
            callback(*args, **kwargs)
        self.assertEqual(caught.exception.code, code)

    def test_fixture_send_apply_and_original_id_replay_preserve_context_and_budgets(self):
        project, journal = self.project(); original = project.status()
        prepared = self.prepare(project, journal)
        reserved = project.status()
        self.assertEqual((reserved["budget"]["model_requests_reserved"], reserved["budget"]["new_model_requests"]), (1, 0))
        self.assertEqual(prepared["context"]["snapshot_ref"], reserved["snapshot_ref"])
        with patch.object(tabular, "execute", wraps=tabular.execute) as execute:
            self.assertEqual(journal.request("model-1", self.transport)["status"], "received")
            self.assertEqual(project.status()["snapshot_ref"], reserved["snapshot_ref"])
            self.assertEqual(journal.request("model-1", self.transport)["status"], "received")
            applied = journal.consume("model-1")
            self.assertEqual(applied["status"], "applied")
            self.assertEqual(self.transport.calls, 1); execute.assert_called_once()
            self.assertEqual(applied["host_local_model_receipt"]["execution"], "fixture")
            self.assertFalse(applied["host_local_model_receipt"]["model_execution_verified"])
            parent = project.status()["controller_requests"][-1]
            self.assertFalse(parent["decision"]["selection_ref"]["model_execution_verified"])
            self.assertFalse(parent["decision"]["selection_ref"]["provider_verified"])
            after = project.status(); db_after = project.db.read_bytes()
            self.assertEqual((after["budget"]["model_requests_reserved"], after["budget"]["new_model_requests"]), (0, 1))
            self.assertEqual((after["budget"]["existing_cash_cap_cny"], after["budget"]["historical_spend_cny"], after["budget"]["new_fits"]),
                             (original["budget"]["existing_cash_cap_cny"], original["budget"]["historical_spend_cny"], 0))
            replay = ProjectModelProposal(project.root).consume("model-1")
            self.assertEqual(replay["status"], "applied"); self.assertEqual(project.db.read_bytes(), db_after)
            self.assertEqual(self.transport.calls, 1)
            self.assertEqual(journal.prepare("model-1", prepared["prepare_request"]["expected_state_version"], self.transport.identity())["status"], "applied")

    def test_received_core_commit_and_slot_finalization_interruptions_recover_offline(self):
        project, journal = self.project(); self.prepare(project, journal, execute=False)
        journal.request("model-1", self.transport)
        self.assertEqual(ProjectModelProposal(project.root).consume("model-1")["status"], "applied")
        self.assertEqual(len(project.status()["actions"]), 0)

        project, journal = self.project(); self.prepare(project, journal)
        journal.request("model-1", self.transport)
        advance = ProjectController.advance_selection
        def after_core(controller, **kwargs):
            advance(controller, **kwargs)
            raise SimulatedCrash()
        with patch.object(tabular, "execute", wraps=tabular.execute) as execute:
            with patch.object(ProjectController, "advance_selection", after_core), self.assertRaises(SimulatedCrash):
                journal.consume("model-1")
            self.assertEqual(journal.read("model-1")["status"], "received")
            recovered = ProjectModelProposal(project.root).consume("model-1")
            self.assertEqual(recovered["status"], "applied"); execute.assert_called_once()
        self.assertEqual(len(project.status()["actions"]), 1)

        project, journal = self.project(); self.prepare(project, journal, execute=False)
        journal.request("model-1", self.transport)
        finalize = journal.project.finalize_local_model_slot
        def after_finalize(**kwargs):
            finalize(**kwargs)
            raise SimulatedCrash()
        with patch.object(journal.project, "finalize_local_model_slot", side_effect=after_finalize), self.assertRaises(SimulatedCrash):
            journal.consume("model-1")
        self.assertEqual(journal.read("model-1")["status"], "consumed")
        state = project.status(); self.assertEqual(state["budget"]["new_model_requests"], 1)
        self.assertEqual(ProjectModelProposal(project.root).consume("model-1")["status"], "applied")
        self.assertEqual(project.status()["budget"]["new_model_requests"], 1)
        self.assertEqual(self.transport.calls, 3)

    def test_zero_allowance_unknown_invalid_and_stale_never_resend_or_rebind(self):
        project, journal = self.project(authorize=False)
        self.assert_code("MODEL_BUDGET_EXHAUSTED", journal.prepare, "model-1", project.status()["state_version"], self.transport.identity())
        self.assertEqual(self.transport.calls, 0)
        project.authorize_local_model_budget(request_id="fixture-authorization", expected_limit=0, new_limit=1,
            reason="Fixture-only explicit zero-to-one allowance.", expected_state_version=project.status()["state_version"])
        self.prepare(project, journal)
        with patch.object(self.transport, "send", side_effect=TimeoutError("Controlled fixture unknown")) as send:
            self.assertEqual(journal.request("model-1", self.transport)["status"], "unknown")
            self.assertEqual(journal.request("model-1", self.transport)["status"], "unknown")
            self.assertEqual(send.call_count, 1)
        self.assert_code("MODEL_RESPONSE_NOT_RECEIVED", journal.consume, "model-1")
        self.assert_code("MODEL_RESPONSE_NOT_RECEIVED", project.finalize_local_model_slot,
                         request_id="model-1", outcome="failed", receipt_sha256="0" * 64)
        self.assertEqual((project.status()["budget"]["model_requests_reserved"], project.status()["budget"]["new_model_requests"]), (1, 0))
        self.assert_code("MODEL_BUDGET_EXHAUSTED", journal.prepare, "new-id-cannot-reset", project.status()["state_version"], self.transport.identity())

        project, journal = self.project(); self.prepare(project, journal)
        self.transport.invalid = True; journal.request("model-1", self.transport); self.transport.invalid = False
        self.assertEqual(journal.consume("model-1")["status"], "invalid")
        self.assertEqual(project.status()["actions"], [])
        self.assertEqual(project.status()["budget"]["new_model_requests"], 1)

        project, journal = self.project(); self.prepare(project, journal)
        journal.request("model-1", self.transport)
        context = ProjectController(project.root).selection_context()
        ProjectController(project.root).advance_selection(request_id="explicit-other-action", expected_state_version=context["state_version"],
            proposal=fixtures.LocalWorkbenchTests.proposal(self, context))
        stale = journal.consume("model-1")
        self.assertEqual(stale["status"], "stale")
        self.assertEqual(project.status()["actions"], [])
        self.assertEqual(len(project.status()["controller_requests"]), 1)
        self.assertEqual(project.status()["budget"]["new_model_requests"], 1)
        self.assertEqual(self.transport.calls, 2)

    def test_current_preflight_proof_keeps_prepared_but_unknown_cannot_unlock(self):
        from autoresearch import project_local_model as transport_module
        project, journal = self.project(); prepared = self.prepare(project, journal)
        core_before = project.db.read_bytes()
        output = self.root / "current-preflight"; output.mkdir()
        (output / "wire-request.json").write_bytes(canonical({"port": 11449, "payload": prepared["payload"]}).encode("utf-8"))
        (output / "transport-identity.json").write_bytes(canonical(prepared["transport_identity"]).encode("utf-8"))
        proof = {"schema_version": "project-local-model-preflight-v1", "request_id": "model-1",
                 "request_sha256": prepared["payload_sha256"], "identity": prepared["transport_identity"],
                 "transport_code_identity": transport_module.code_identity(), "stage": "before_worker_spawn", "phase": "validate",
                 "worker_spawn_attempted": False, "chat_dispatched": False, "owned_server_stopped": True,
                 "owned_process_created": False, "output": str(output), "files": transport_module._preflight_files(output),
                 "failure_code": "MODEL_CHANGED"}
        path = output / "preflight-no-dispatch.json"; path.write_bytes(canonical(proof).encode("utf-8"))
        error = ResearchError("MODEL_CHANGED", "Fixture metadata preflight failure")
        error.preflight_no_dispatch = {"proof_path": str(path), "proof_sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
        with patch.object(self.transport, "send", side_effect=error) as send:
            stopped = journal.request("model-1", self.transport)
            self.assertEqual(stopped["status"], "prepared"); self.assertEqual(send.call_count, 1)
        self.assertEqual(stopped["context"], prepared["context"])
        self.assertEqual(stopped["payload"], prepared["payload"])
        self.assertEqual(stopped["slot"], prepared["slot"])
        self.assertEqual(project.db.read_bytes(), core_before)
        self.assertFalse(hasattr(journal, "reconcile_not_dispatched"))
        proof["worker_spawn_attempted"] = True
        path.write_bytes(canonical(proof).encode("utf-8"))
        error.preflight_no_dispatch["proof_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
        with patch.object(self.transport, "send", side_effect=error) as send:
            self.assertEqual(journal.request("model-1", self.transport)["status"], "unknown")
            self.assertEqual(journal.request("model-1", self.transport)["status"], "unknown")
            self.assertEqual(send.call_count, 1)
        self.assert_code("MODEL_RESPONSE_NOT_RECEIVED", journal.consume, "model-1")
        self.assertEqual(project.db.read_bytes(), core_before)
        self.assertEqual(self.transport.calls, 0)


if __name__ == "__main__":
    unittest.main()
