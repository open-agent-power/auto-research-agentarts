"""Actual loopback preview/import/continue with a constructed external reply."""
import base64
import unittest

import test_local_delegated_batch as delegated
import test_local_workbench_http as http
from autoresearch.contracts import canonical
from autoresearch.local_workbench import LocalWorkbench


class DelegatedWorkbenchHTTPTests(unittest.TestCase):
    setUp = delegated.LocalDelegatedBatchTests.setUp
    plan = staticmethod(delegated.LocalDelegatedBatchTests.plan)
    body = delegated.LocalDelegatedBatchTests.body
    answer = delegated.LocalDelegatedBatchTests.answer
    seed_grant = delegated.LocalDelegatedBatchTests.seed_grant
    new_body = delegated.LocalDelegatedBatchTests.new_body
    serve = http.LocalWorkbenchHTTPTests.serve
    request = http.LocalWorkbenchHTTPTests.request
    session = http.LocalWorkbenchHTTPTests.session

    def test_preview_import_and_restart_use_original_http_ids_without_model_transport(self):
        body = self.new_body()
        server = self.serve(local_workspace=self.manager, allow_local_actions=True)
        headers = self.session(server)
        before = self.manager.describe()
        status, preview = self.request(server, "/api/local-workbench/continuation-preview", "POST", body, headers)
        self.assertEqual(status, 200, preview)
        self.assertEqual((preview["status"], preview["preparation_state"]), ("identifiers_computed", "unknown_not_checked"))
        self.assertEqual(self.manager.describe(), before)
        status, pending = self.request(server, "/api/local-workbench/continue", "POST", body, headers)
        self.assertEqual(status, 200, pending)
        self.assertEqual(pending["status"], "awaiting_external_response")
        host_id = pending["steps"][-1]["request_id"]
        self.assertEqual(preview["steps"][0]["host_request_id"], host_id)
        reply = canonical({"choice": {"kind": "wait"}, "rationale": "Synthetic external reply; no research claim.",
                           "evidence_citation_ids": []}).encode()
        command = {"request_id": body["request_id"], "project_id": body["project_id"],
                   "host_request_id": host_id, "response_base64": base64.b64encode(reply).decode()}
        status, _ = self.request(server, "/api/local-workbench/delegated-response", "POST", command,
                                 {**headers, "Origin": "http://invalid.example"})
        self.assertEqual(status, 403)
        self.assertEqual(self.journal.status(request_id=host_id)["status"], "prepared")
        status, received = self.request(server, "/api/local-workbench/delegated-response", "POST", command, headers)
        self.assertEqual(status, 200, received)
        self.assertEqual(received["status"], "received")
        status, finished = self.request(server, "/api/local-workbench/continue", "POST", body, headers)
        self.assertEqual(status, 200, finished)
        self.assertEqual((finished["status"], finished["record_status"]), ("waiting", "completed"))
        original = self.project.status()
        self.assertEqual(LocalWorkbench(self.manager.root).continue_research(body), finished)
        self.assertEqual(self.project.status(), original)
        self.assertEqual(original["actions"], [])
        self.assertEqual(original["budget"]["new_model_requests"], 0)
        self.assertEqual(original["budget"]["new_fits"], 0)
        self.assertEqual(self.journal.status()["grant"], self.grant)


if __name__ == "__main__":
    unittest.main()
