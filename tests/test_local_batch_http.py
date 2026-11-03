"""One focused loopback batch route check; real orchestration is tested separately."""

import unittest

import test_local_workbench_http as fixtures
from autoresearch.contracts import ResearchError
from autoresearch.project_workbench import MAX_LOCAL_REQUEST_BYTES


class BatchWorkspace(fixtures.FakeWorkspace):
    def batch(self, body):
        self.calls.append(body)
        return {"command": "batch", "status": "waiting", "request_id": body["request_id"]}

    def batch_record(self, request_id):
        if request_id != "batch-fixture":
            raise ResearchError("ARTIFACT_NOT_FOUND", "No saved batch.")
        return {"schema_version": "local-workbench-batch-v1", "body": self.calls[0], "steps": []}


class LocalBatchHTTPTests(unittest.TestCase):
    serve = fixtures.LocalWorkbenchHTTPTests.serve
    request = fixtures.LocalWorkbenchHTTPTests.request
    session = fixtures.LocalWorkbenchHTTPTests.session

    def test_batch_uses_original_gate_and_small_body_limit_with_readonly_record_download(self):
        workspace = BatchWorkspace()
        server = self.serve(local_workspace=workspace, allow_local_actions=True)
        headers = self.session(server)
        body = {"request_id": "batch-fixture", "project_id": "fixture-project", "expected_state_version": 0,
                "max_actions": 2, "allowed_methods": ["data.tabular-quality-audit"],
                "source_receipt_sha256s": [], "reason": "Fixture explicit grant."}
        self.assertEqual(self.request(server, "/api/local-workbench/batch", "POST", body,
                                     {**headers, "Origin": "http://external.invalid"})[0], 403)
        self.assertEqual(self.request(server, "/api/local-workbench/batch", "POST", b"",
                                     {**headers, "Content-Length": str(MAX_LOCAL_REQUEST_BYTES + 1)})[0], 413)
        self.assertEqual(workspace.calls, [])
        status, result = self.request(server, "/api/local-workbench/batch", "POST", body, headers)
        self.assertEqual((status, result["status"]), (200, "waiting"))
        status, record = self.request(server, "/api/local-workbench/batch/batch-fixture.json")
        self.assertEqual((status, record["body"]), (200, body))
        self.assertEqual(self.request(server, "/api/local-workbench/batch/absent.json")[0], 404)
        self.assertEqual(self.request(server, "/api/local-workbench/batch/%2E%2E%2Foutside.json")[0], 400)
        self.assertEqual(self.request(server, "/api/local-workbench/batch/batch-fixture.json?extra=1")[0], 400)
        self.assertEqual(workspace.calls, [body])
        disabled = self.serve(local_workspace=workspace)
        self.assertEqual(self.request(disabled, "/api/local-workbench/batch", "POST", body, self.session(disabled))[0], 405)


if __name__ == "__main__":
    unittest.main()
