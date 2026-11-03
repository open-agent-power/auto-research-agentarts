"""One offline fixture for distinct manifests and a strictly undispatched preflight."""
import copy
import hashlib
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import test_local_workbench as fixtures
import test_project_selection as selection_fixtures
from autoresearch import local_ollama, project_local_model as local
from autoresearch import project_model_protocol as protocol
from autoresearch.contracts import ResearchError, canonical, fingerprint
from autoresearch.local_workbench import LocalWorkbench
from autoresearch.project_model_proposal import ProjectModelProposal


class ProjectLocalModelTests(unittest.TestCase):
    def test_wrapper_identity_and_known_preflight_keep_original_slot_prepared(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            weights = {"manifest_sha256": "b" * 64, "manifest_bytes": 10, "blobs": [],
                       "publisher_manifest_sha256": local_ollama.PUBLISHER_MANIFEST_SHA256}
            identity = {"schema_version": "project-local-model-identity-v1", "transport": "owned-local-ollama",
                        "model": "qwen3:4b", "publisher_manifest_sha256": weights["publisher_manifest_sha256"],
                        "executable_sha256": "e" * 64, "cloud_disabled": True}
            native = local._OfflineOllama(root / "ollama.exe", root / "cache", root / "native")
            native.output.mkdir()
            calls = []
            def response(route, body=None):
                calls.append(route)
                return {"details": {"family": "qwen3"}, "capabilities": ["tools", "thinking"],
                        "thinking": {"values": [True, False]}} if route == "/api/show" else {
                    "models": [{"name": "qwen3:4b", "digest": weights["manifest_sha256"]}]}
            native.http = SimpleNamespace(request=response)
            with patch.object(native, "assert_owner"), patch.object(local_ollama, "verify_weights", return_value=weights):
                acquired = native.acquire()
            self.assertEqual(acquired["manifest_sha256"], "b" * 64)
            self.assertEqual(acquired["publisher_manifest_sha256"], local_ollama.PUBLISHER_MANIFEST_SHA256)
            self.assertNotEqual(acquired["manifest_sha256"], acquired["publisher_manifest_sha256"])
            self.assertEqual(calls, ["/api/show", "/api/tags"])

            manager = LocalWorkbench(root / "workbench")
            manager.create(fixtures.LocalWorkbenchTests.create_body(self, "fixture-create"))
            project, _ = manager.binding()
            project.authorize_local_model_budget(request_id="fixture-budget", expected_limit=0, new_limit=1,
                reason="Temporary fixture only; no real model inference is authorized or executed.",
                expected_state_version=project.status()["state_version"])
            journal = ProjectModelProposal(project.root)
            prepared = journal.prepare("fixture-model", project.status()["state_version"], identity)
            before = project.status()
            actual_acquire = local._OfflineOllama.acquire
            class PreflightFailure:
                def __init__(self, executable, cache, output, **kwargs):
                    self.cache, self.output, self.identity = cache, output, copy.deepcopy(identity)
                    self.process, self.stopped, self.generated_task_key_files_removed = object(), False, 0
                    self.http = SimpleNamespace(request=lambda route, body=None: {
                        "details": {"family": "qwen3"}, "capabilities": ["tools", "thinking"],
                        "thinking": {"values": [True]}} if route == "/api/show" else {
                        "models": [{"name": "qwen3:4b", "digest": weights["manifest_sha256"]}]})
                def assert_owner(self):
                    pass
                def __enter__(self):
                    (self.output / "server.stdout.log").write_bytes(b'GET /api/version\nPOST /api/show\nGET /api/tags\n')
                    (self.output / "server.stderr.log").write_bytes(b'')
                    return self
                def acquire(self):
                    return actual_acquire(self)
                def __exit__(self, *_):
                    self.stopped = True
            def offline_identity(transport):
                transport._verified_weights = copy.deepcopy(weights)
                transport._last_identity = copy.deepcopy(identity)
                return copy.deepcopy(identity)
            transport = local.ProjectLocalModel(cache=root / "cache", executable=root / "ollama.exe", output=root / "attempt")
            with patch.object(local.ProjectLocalModel, "identity", offline_identity), patch.object(local, "_copy"), \
                 patch.object(local, "_OfflineOllama", PreflightFailure), \
                 patch.object(local_ollama, "verify_weights", return_value=weights), \
                 patch.object(local.local_process, "ManagedJob") as worker_job:
                result = journal.request("fixture-model", transport)
            worker_job.assert_not_called()
            self.assertEqual(result["status"], "prepared")
            reference = {"proof_path": str(root / "attempt/preflight-no-dispatch.json")}
            reference["proof_sha256"] = hashlib.sha256(Path(reference["proof_path"]).read_bytes()).hexdigest()
            proof = local.validate_preflight_no_dispatch(reference, "fixture-model", prepared["payload_sha256"], identity)
            self.assertFalse(proof["worker_spawn_attempted"])
            self.assertFalse(proof["chat_dispatched"])
            self.assertEqual(proof["failure_code"], "MODEL_PROTOCOL_INCOMPATIBLE")
            self.assertTrue(proof["owned_server_stopped"])
            self.assertEqual(project.status()["snapshot_ref"], before["snapshot_ref"])
            self.assertFalse((root / "attempt/worker.stdout.log").exists())
            self.assertFalse((root / "attempt/response.bin").exists())
            (root / "attempt/response.bin").write_bytes(b"possible response")
            with self.assertRaises(ResearchError):
                local.validate_preflight_no_dispatch(reference, "fixture-model", prepared["payload_sha256"], identity)

    def test_saved_protocol_inspection_reports_failure_and_rejects_changed_evidence(self):
        context = selection_fixtures.ProjectSelectionTests.context(self)
        identity = {"schema_version": "project-local-model-identity-v1", "transport": "owned-local-ollama",
                    "model": "qwen3:4b", "publisher_manifest_sha256": local_ollama.PUBLISHER_MANIFEST_SHA256,
                    "executable_sha256": "e" * 64, "cloud_disabled": True}
        payload = protocol.build_request(context, identity)
        response = {"model": "qwen3:4b", "done": True, "done_reason": "length", "eval_count": 768,
                    "message": {"role": "assistant", "content": "Synthetic incomplete reasoning; no native tool call."}}
        raw = canonical(response).encode("utf-8")
        receipt = {"schema_version": "project-model-transport-receipt-v1", "identity": identity,
                   "request_sha256": fingerprint(payload), "response_sha256": hashlib.sha256(raw).hexdigest(),
                   "execution": "local_model", "process": {"synthetic_saved_evidence_fixture": True}}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "server").mkdir()
            files = {"wire-request.json": {"port": 11449, "payload": payload},
                     "transport-receipt.json": receipt,
                     "response-metadata.json": {"http_status": 200, "raw_sha256": receipt["response_sha256"], "raw_bytes": len(raw)},
                     "server/native-show-evidence.json": {"capabilities": ["tools", "thinking"], "thinking": {"values": [True]}}}
            for name, value in files.items():
                (root / name).write_text(canonical(value), encoding="utf-8")
            (root / "response.bin").write_bytes(raw)
            before = {p: p.read_bytes() for p in root.rglob("*") if p.is_file()}
            with patch.object(local_ollama, "verify_weights", side_effect=AssertionError("Must not read weights")), \
                 patch.object(local.local_process, "ManagedJob", side_effect=AssertionError("Must not start a process")):
                report = local.inspect_protocol_evidence(root)
            self.assertFalse(report["ok"])
            self.assertTrue(report["inspection_completed"])
            self.assertIn("THINK_SETTING_UNSUPPORTED", report["compatibility"]["reason_codes"])
            self.assertEqual(report["proposal_validation"]["code"], "INVALID_MODEL_RESPONSE")
            self.assertEqual(report["observed_response"]["reason_codes"], ["OUTPUT_LIMIT_REACHED", "NATIVE_TOOL_CALL_ABSENT"])
            self.assertEqual(before, {p: p.read_bytes() for p in root.rglob("*") if p.is_file()})
            (root / "response.bin").write_bytes(raw + b" ")
            with self.assertRaises(ResearchError) as caught:
                local.inspect_protocol_evidence(root)
            self.assertEqual(caught.exception.code, "EVIDENCE_CHANGED")
