"""Bounded evidence upload, original-byte preservation and explicit extraction."""

import base64
import copy
import http.client
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import test_local_workbench as fixtures
import test_local_workbench_http as http_fixtures
from autoresearch.contracts import ResearchError
from autoresearch.local_workbench import LocalWorkbench
from autoresearch.project_controller import ProjectController
from autoresearch import source_evidence_adapter as reader, tabular_quality_adapter as tabular


class LocalEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory())) / "workbench"
        self.manager = LocalWorkbench(self.root)
        self.manager.create(fixtures.LocalWorkbenchTests.create_body(self))
        self.project, _ = self.manager.binding()
        context = ProjectController(self.project.root).selection_context()
        self.manager.advance({"request_id": "fixture-primary", "project_id": context["project_id"],
                              "expected_state_version": context["state_version"],
                              "proposal": fixtures.LocalWorkbenchTests.proposal(self, context, tabular.TOOL_ID)})

    def body(self, request_id="upload-1"):
        state = self.project.status()
        return {"request_id": request_id, "project_id": state["id"], "expected_state_version": state["state_version"],
                "task_ref": copy.deepcopy(state["evidence_task_ref"]), "contributor": {"role": "teammate", "label": "Fixture submitter"},
                "sources": [{"id": "notes", "file_name": "notes.txt", "bytes_base64": base64.b64encode(b"Original fixture note.\nSecond line.\n").decode("ascii"),
                             "url": "urn:test:notes", "media_type": "text/plain", "license_note": "Unknown fixture declaration"}],
                "selections": [{"id": "first-line", "source_id": "notes", "locator": {"kind": "text_lines", "value": "1"},
                                "claim": "Submitter interpretation remains unreviewed."}], "remaining_questions": ["Confirm the original group definition."]}

    def assert_code(self, code, callback, *args):
        with self.assertRaises(ResearchError) as caught:
            callback(*args)
        self.assertEqual(caught.exception.code, code)

    def test_register_and_reload_replay_keep_originals_without_capture_or_extract(self):
        body = self.body(); before = self.project.status()
        with patch.object(reader, "capture_bundle", wraps=reader.capture_bundle) as capture, \
             patch.object(reader, "execute", side_effect=AssertionError("Registration must never extract")) as execute:
            result = self.manager.register_evidence(body)
            self.assertEqual((result["command"], result["status"]), ("evidence", "registered"))
            receipt_sha = result["registration"]["receipt_snapshot_sha256"]
            after = self.project.status(); core_bytes = self.project.db.read_bytes()
            self.assertEqual(after["state_version"], before["state_version"] + 1)
            self.assertEqual((len(after["evidence_sources"]), len(after["evidence_actions"]), after["budget"]["evidence_reads_used"]), (1, 0, 0))
            self.assertEqual(after["knowledge_refs"], [])
            replay = LocalWorkbench(self.root).register_evidence(body)
            self.assertTrue(replay["replayed"]); self.assertEqual(capture.call_count, 1); execute.assert_not_called()
            self.assertEqual(self.project.db.read_bytes(), core_bytes)
            receipt, assets, _ = self.project._load_evidence_input(after, receipt_sha, task_ref=body["task_ref"])
            self.assertEqual(assets["notes"], base64.b64decode(body["sources"][0]["bytes_base64"]))
            self.assertEqual(receipt["sources"][0]["license_note"], body["sources"][0]["license_note"])
            changed = copy.deepcopy(body); changed["sources"][0]["url"] = "urn:test:changed"
            self.assert_code("IDEMPOTENCY_CONFLICT", self.manager.register_evidence, changed)
            next((self.root / "evidence-uploads").glob("*/sources/*")).write_bytes(b"Changed original")
            self.assert_code("EVIDENCE_CHANGED", self.manager.register_evidence, body)

    def test_uci_text_original_suffixes_register_replay_and_index_names_coordinates(self):
        names = "Auto MPG constructed fixture\r\nHorsepower fixture values include an unknown marker.\r\n来源说明保留原行。\r\n"
        originals = {"names": ("auto-mpg.names", names.encode("utf-8")),
                     "data": ("auto-mpg.data", b"18.0 8 307.0 130.0\n"),
                     "data-original": ("auto-mpg.data-original", b"18.0 8 307.0 130.0\r\n")}
        body = self.body("uci-text-originals")
        body["sources"] = [{**body["sources"][0], "id": source_id, "file_name": name,
                            "bytes_base64": base64.b64encode(raw).decode("ascii")}
                           for source_id, (name, raw) in originals.items()]
        locator = {"kind": "text_lines", "value": "2-3"}
        body["selections"] = [{**body["selections"][0], "id": "names-definition", "source_id": "names", "locator": locator}]
        before = self.project.status()
        with patch.object(reader, "execute", side_effect=AssertionError("Registration must not extract")):
            registered = self.manager.register_evidence(body)
            after_register = self.project.status()
            self.assertEqual(after_register["budget"], before["budget"])
            self.assertEqual(after_register["knowledge_refs"], before["knowledge_refs"])
            self.assertEqual(len(after_register["evidence_actions"]), 0)
            self.assertTrue(LocalWorkbench(self.root).register_evidence(body)["replayed"])
        self.assertEqual(self.project.status(), after_register)
        stored = sorted((self.root / "evidence-uploads").glob("*/sources/*"))
        self.assertEqual({path.name: path.read_bytes() for path in stored},
                         {str(index).zfill(2) + "-" + name: raw
                          for index, (name, raw) in enumerate(originals.values(), 1)})
        sha = registered["registration"]["receipt_snapshot_sha256"]
        receipt, assets, _ = self.project._load_evidence_input(after_register, sha, task_ref=body["task_ref"])
        self.assertEqual(assets, {source_id: raw for source_id, (_, raw) in originals.items()})
        self.assertTrue(all(source["media_type"] == "text/plain" for source in receipt["sources"]))
        action = self.project.read_evidence(request_id="read-uci-names", receipt_snapshot_sha256=sha,
                                            expected_state_version=after_register["state_version"])
        self.assertEqual(action["status"], "completed")
        after_read = self.project.status()
        self.assertEqual(after_read["budget"], {**after_register["budget"], "evidence_reads_used": 1})
        selection, = json.loads(self.project._artifact(action).read_bytes())["tool_result"]["result"]["selections"]
        extraction = selection["extraction"]
        selected = "".join(names.splitlines(keepends=True)[1:3])
        self.assertEqual((extraction["line_start"], extraction["line_end"]), (2, 3))
        self.assertEqual([line["line"] for line in extraction["lines"]], [2, 3])
        self.assertEqual(extraction["text"], selected)
        self.assertEqual(names[extraction["start_char"]:extraction["end_char"]], selected)
        hit, = self.project.knowledge(need="Horsepower")["evidence"]
        self.assertEqual(hit["quote"], selected)
        self.assertEqual(hit["location"], {"line_start": 1, "line_end": 2})
        self.assertEqual(hit["source"]["metadata"]["locator"], locator)
        self.assertEqual(hit["source"]["metadata"]["selection_id"], "names-definition")
        self.assertEqual(hit["source"]["metadata"]["original_source_sha256"], selection["source"]["sha256"])
        with patch.object(reader, "execute", side_effect=AssertionError("Replay must not extract")):
            self.assertTrue(self.manager.register_evidence(body)["replayed"])
            self.assertTrue(self.project.read_evidence(request_id="read-uci-names", receipt_snapshot_sha256=sha,
                                                       expected_state_version=after_register["state_version"])["replayed"])
        self.assertEqual(self.project.status(), after_read)

    def test_html_originals_register_extract_literal_lines_and_replay_without_new_reads(self):
        original = "<!doctype html>\r\n<html>\r\n<script>window.fixture = '<b>literal</b>';</script>\r\n<p>原始 &amp; HTML</p>\r\n</html>\r\n"
        raw = original.encode("utf-8")
        body = self.body("html-originals")
        body["sources"] = [{**body["sources"][0], "id": suffix, "file_name": "saved-page." + suffix,
                            "bytes_base64": base64.b64encode(raw).decode("ascii"), "media_type": "text/html"}
                           for suffix in ("html", "htm")]
        body["selections"] = [{**body["selections"][0], "id": "lines-" + suffix, "source_id": suffix,
                               "locator": {"kind": "text_lines", "value": "3-4"}} for suffix in ("html", "htm")]
        before = self.project.status()
        registered = self.manager.register_evidence(body)
        sha = registered["registration"]["receipt_snapshot_sha256"]
        after_register = self.project.status()
        self.assertEqual(after_register["budget"], before["budget"])
        receipt, assets, _ = self.project._load_evidence_input(after_register, sha, task_ref=body["task_ref"])
        self.assertEqual(assets, {"html": raw, "htm": raw})
        self.assertTrue(all(source["media_type"] == "text/html" for source in receipt["sources"]))
        with patch.object(reader, "execute", wraps=reader.execute) as extract:
            action = self.project.read_evidence(request_id="read-html-originals", receipt_snapshot_sha256=sha,
                                                expected_state_version=after_register["state_version"])
            after_read = self.project.status()
            self.assertEqual(after_read["budget"]["evidence_reads_used"], before["budget"]["evidence_reads_used"] + 1)
            self.assertEqual(after_read["budget"]["local_tool_calls_used"], before["budget"]["local_tool_calls_used"])
            selected = "".join(original.splitlines(keepends=True)[2:4])
            result = json.loads(self.project._artifact(action).read_bytes())["tool_result"]["result"]
            for selection in result["selections"]:
                extraction = selection["extraction"]
                self.assertEqual(extraction["text"], selected)
                self.assertEqual((extraction["line_start"], extraction["line_end"]), (3, 4))
                self.assertEqual([line["line"] for line in extraction["lines"]], [3, 4])
                self.assertEqual(original[extraction["start_char"]:extraction["end_char"]], selected)
            self.assertTrue(self.manager.register_evidence(body)["replayed"])
            self.assertTrue(self.project.read_evidence(request_id="read-html-originals", receipt_snapshot_sha256=sha,
                                                       expected_state_version=after_register["state_version"])["replayed"])
            self.assertEqual(extract.call_count, 1)
        self.assertEqual(self.project.status(), after_read)

    def test_html_original_download_remains_an_octet_stream_attachment(self):
        body = self.body("html-download")
        raw = b"<html><script>window.fixture = true;</script></html>\n"
        body["sources"][0].update(file_name="saved-page.html", media_type="text/html",
                                   bytes_base64=base64.b64encode(raw).decode("ascii"))
        registered = self.manager.register_evidence(body)
        sha = registered["registration"]["receipt_snapshot_sha256"]
        before = self.project.status()
        server = http_fixtures.LocalWorkbenchHTTPTests.serve(self, local_workspace=self.manager)
        connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=5)
        self.addCleanup(connection.close)
        with patch.object(reader, "execute", side_effect=AssertionError("Download must not extract")):
            connection.request("GET", f"/api/project/evidence-source/{sha}/notes")
            response = connection.getresponse()
            self.assertEqual(response.status, 200)
            self.assertEqual(response.getheader("Content-Type"), "application/octet-stream")
            self.assertIn("attachment", response.getheader("Content-Disposition"))
            self.assertIn("notes.html", response.getheader("Content-Disposition"))
            self.assertEqual(response.read(), raw)
        self.assertEqual(self.project.status(), before)

    def test_filename_locator_task_version_unknown_code_and_size_boundaries(self):
        body = self.body()
        for field, value in (("file_name", "../outside.txt"), ("file_name", "CON.txt"), ("file_name", "bad?.txt")):
            changed = copy.deepcopy(body); changed["sources"][0][field] = value
            self.assert_code("UNSAFE_PATH", self.manager.register_evidence, changed)
        changed = copy.deepcopy(body); changed["selections"][0]["locator"]["kind"] = "python"
        self.assert_code("INVALID_LOCATOR", self.manager.register_evidence, changed)
        changed = copy.deepcopy(body); changed["selections"][0]["source_id"] = "absent"
        self.assert_code("INVALID_BUNDLE", self.manager.register_evidence, changed)
        changed = copy.deepcopy(body); changed["task_ref"]["based_on_action_id"] = "action-another"
        self.assert_code("TASK_MISMATCH", self.manager.register_evidence, changed)
        changed = copy.deepcopy(body); changed["expected_state_version"] += 1
        self.assert_code("STALE_STATE", self.manager.register_evidence, changed)
        with patch("autoresearch.research_project.code_identity", return_value="f" * 64):
            self.assert_code("CODE_CHANGED", self.manager.register_evidence, body)
        with patch.object(reader, "MAX_SOURCE_BYTES", 4):
            oversized = copy.deepcopy(body); oversized["sources"][0]["bytes_base64"] = base64.b64encode(b"12345").decode("ascii")
            self.assert_code("SOURCE_TOO_LARGE", self.manager.register_evidence, oversized)
        with patch.object(reader, "MAX_TOTAL_BYTES", 4):
            self.assert_code("SOURCE_TOO_LARGE", self.manager.register_evidence, body)
        self.assertFalse((self.root / "evidence-uploads").exists())
        with self.project._writer(), self.project._connect() as con:
            state = self.project._project(con); state["source_requests"] = [{"request_id": "fixture-unknown", "status": "unknown"}]
            state["state_version"] += 1; self.project._save(con, state)
        changed = self.body()
        self.assert_code("EXECUTION_UNKNOWN", self.manager.register_evidence, changed)
        self.assertFalse((self.root / "evidence-uploads").exists())

    def test_partial_requires_original_id_and_core_committed_registration_can_reconcile(self):
        body = self.body()
        with patch.object(self.manager, "_verify_evidence_registration", side_effect=OSError("Controlled post-registration interruption")):
            self.assert_code("WORKBENCH_OPERATION_FAILED", self.manager.register_evidence, body)
        after = self.project.status(); db_after = self.project.db.read_bytes()
        self.assertEqual(len(after["evidence_registrations"]), 1)
        self.assertEqual(self.manager.describe()["pending_requests"], [{"request_id": body["request_id"], "command": "evidence",
                                                                     "status": "incomplete", "project_id": body["project_id"]}])
        with patch.object(reader, "capture_bundle", side_effect=AssertionError("Recovery must not recapture")), \
             patch.object(reader, "execute", side_effect=AssertionError("Recovery must not extract")):
            recovered = LocalWorkbench(self.root).register_evidence(body)
        self.assertTrue(recovered["replayed"]); self.assertTrue(recovered["recovered"])
        self.assertEqual(self.project.db.read_bytes(), db_after)
        self.assertEqual(self.manager.describe()["pending_requests"], [])
        partial = self.body("upload-before-core")
        with patch("autoresearch.local_workbench.ResearchProject.register_evidence", side_effect=OSError("Controlled pre-registration interruption")) as register:
            self.assert_code("WORKBENCH_OPERATION_FAILED", self.manager.register_evidence, partial)
            self.assert_code("OPERATION_INCOMPLETE", self.manager.register_evidence, partial)
            self.assert_code("OPERATION_INCOMPLETE", self.manager.register_evidence, {**partial, "request_id": "replacement-not-allowed"})
            self.assertEqual(register.call_count, 1)
        self.assertEqual(len(self.project.status()["evidence_registrations"]), 1)
        self.assertEqual(len(self.project.status()["evidence_actions"]), 0)
        self.assertEqual(len(list((self.root / "evidence-uploads").glob("*/sources/*"))), 2)


if __name__ == "__main__":
    unittest.main()
