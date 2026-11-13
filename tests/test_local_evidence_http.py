"""Focused evidence transport checks; registration/download never extract sources."""

import base64
from unittest.mock import patch
import unittest

import test_local_evidence as evidence_fixtures
import test_local_workbench_http as http_fixtures
from autoresearch import source_evidence_adapter as reader
from autoresearch.local_workbench import LocalWorkbench


class LocalEvidenceHTTPTests(unittest.TestCase):
    setUp = evidence_fixtures.LocalEvidenceTests.setUp
    body = evidence_fixtures.LocalEvidenceTests.body
    serve = http_fixtures.LocalWorkbenchHTTPTests.serve
    request = http_fixtures.LocalWorkbenchHTTPTests.request
    session = http_fixtures.LocalWorkbenchHTTPTests.session

    def test_projection_marks_no_evidence_task_without_changing_the_project(self):
        manager = LocalWorkbench(self.root / "unstarted")
        manager.create(evidence_fixtures.fixtures.LocalWorkbenchTests.create_body(self))
        project, _ = manager.binding()
        before = project.db.read_bytes()
        self.assertFalse(project.status().get("evidence_task_ref"))
        server = self.serve(workspace=project.root)
        status, view = self.request(server, "/api/project")
        self.assertEqual(status, 200)
        self.assertIs(view["evidence_task_available"], False)
        status, unavailable = self.request(server, "/api/project/evidence-task.json")
        self.assertEqual((status, unavailable["code"]), (409, "TASK_NOT_AVAILABLE"))
        self.assertEqual(project.db.read_bytes(), before)

    def test_projection_marks_an_actual_bound_evidence_task_available(self):
        expected = self.project.status()["evidence_task_ref"]
        before = self.project.db.read_bytes()
        server = self.serve(workspace=self.project.root)
        status, view = self.request(server, "/api/project")
        self.assertEqual(status, 200)
        self.assertIs(view["evidence_task_available"], True)
        status, task = self.request(server, "/api/project/evidence-task.json")
        self.assertEqual((status, task["task_ref"]), (200, expected))
        self.assertEqual(self.project.db.read_bytes(), before)

    def test_task_registration_receipt_and_original_are_project_bound_without_extraction(self):
        server = self.serve(local_workspace=self.manager, allow_local_actions=True)
        headers = self.session(server)
        status, task = self.request(server, "/api/project/evidence-task.json")
        self.assertEqual((status, task["task_ref"]), (200, self.project.evidence_task()["task_ref"]))
        self.assertTrue(task["required_evidence"])
        body = self.body()
        with patch.object(reader, "execute", side_effect=AssertionError("Transport must never extract")):
            status, result = self.request(server, "/api/local-workbench/evidence", "POST", body, headers)
            self.assertEqual((status, result.get("status")), (200, "registered"), result)
            sha = result["registration"]["receipt_snapshot_sha256"]
            db_after = self.project.db.read_bytes()
            status, receipt = self.request(server, f"/api/project/evidence-receipt/{sha}.json")
            self.assertEqual((status, receipt["snapshot_sha256"]), (200, sha))
            status, unread_task = self.request(server, "/api/project/evidence-task.json")
            self.assertEqual((status, unread_task["required_evidence"]), (200, task["required_evidence"]))
            connection = http_fixtures.http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=5)
            self.addCleanup(connection.close)
            connection.request("GET", f"/api/project/evidence-source/{sha}/notes")
            response = connection.getresponse()
            self.assertEqual(response.status, 200)
            self.assertIn("attachment", response.getheader("Content-Disposition"))
            self.assertEqual(response.read(), base64.b64decode(body["sources"][0]["bytes_base64"]))
            self.assertEqual(self.project.db.read_bytes(), db_after)
            self.assertEqual(self.project.status()["budget"]["evidence_reads_used"], 0)
            self.assertEqual(self.request(server, f"/api/project/evidence-receipt/{'0' * 64}.json")[0], 404)
            self.assertEqual(self.request(server, f"/api/project/evidence-source/{sha}/%2E%2E%2Foutside")[0], 400)
            self.assertEqual(self.request(server, f"/api/project/evidence-receipt/{sha}.json?extra=1")[0], 400)
            asset = self.project.root / "evidence-inputs" / sha / (receipt["sources"][0]["asset_sha256"] + ".bin")
            asset.write_bytes(b"tampered")
            self.assertEqual(self.request(server, f"/api/project/evidence-source/{sha}/notes")[0], 500)

    def test_evidence_has_dedicated_size_gate_and_retains_session_and_readonly_denial(self):
        workspace = http_fixtures.FakeWorkspace()
        workspace.register_evidence = workspace.create
        server = self.serve(local_workspace=workspace, allow_local_actions=True)
        valid = self.session(server)
        raw = b'{"padding":"1234567890"}'
        with patch("autoresearch.project_workbench.MAX_LOCAL_REQUEST_BYTES", 10), \
             patch("autoresearch.project_workbench.MAX_LOCAL_EVIDENCE_REQUEST_BYTES", 40):
            self.assertEqual(self.request(server, "/api/local-workbench/create", "POST", raw, valid)[0], 413)
            self.assertEqual(self.request(server, "/api/local-workbench/evidence", "POST", raw, valid)[0], 200)
            self.assertEqual(self.request(server, "/api/local-workbench/evidence", "POST", b"", {**valid, "Content-Length": "41"})[0], 413)
            self.assertEqual(self.request(server, "/api/local-workbench/evidence", "POST", raw, {**valid, "Origin": "http://external.invalid"})[0], 403)
            self.assertEqual(self.request(server, "/api/local-workbench/evidence", "POST", b'{"id":1,"id":2}', valid)[0], 400)
        self.assertEqual(workspace.calls, [{"padding": "1234567890"}])
        disabled = self.serve(local_workspace=workspace)
        self.assertEqual(self.request(disabled, "/api/local-workbench/evidence", "POST", b"{}", self.session(disabled))[0], 405)
        readonly = self.serve(workspace=self.project.root)
        self.assertEqual(self.request(readonly, "/api/local-workbench/evidence", "POST", b"{}", valid)[0], 405)


if __name__ == "__main__":
    unittest.main()
