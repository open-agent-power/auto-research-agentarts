"""Necessary loopback command gates and real project/controller transport checks."""
import http.client
import json
from pathlib import Path
import tempfile
import threading
import unittest

import test_tabular_quality_adapter as tabular_fixtures
from autoresearch.contracts import canonical
from autoresearch.local_workbench import LocalWorkbench
from autoresearch.project_workbench import MAX_LOCAL_REQUEST_BYTES, create_project_server
from autoresearch.research_project import ResearchProject


class FakeWorkspace:
    def __init__(self):
        self.calls = []

    def describe(self):
        return {"schema_version": "local-research-workbench-v1", "active_project_id": None, "projects": []}

    def binding(self):
        return None, None

    def create(self, body):
        self.calls.append(body)
        return {"ok": True}


class LocalWorkbenchHTTPTests(unittest.TestCase):
    capture = tabular_fixtures.TabularQualityAdapterTests.capture

    def serve(self, **kwargs):
        server = create_project_server(port=0, **kwargs)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()

        def close():
            server.shutdown()
            server.server_close()
            thread.join(2)

        self.addCleanup(close)
        return server

    def request(self, server, path, method="GET", body=None, headers=None):
        connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=5)
        self.addCleanup(connection.close)
        raw = body if type(body) is bytes else canonical(body).encode("utf-8") if body is not None else None
        connection.request(method, path, body=raw, headers=headers or {})
        response = connection.getresponse()
        return response.status, json.loads(response.read())

    def session(self, server):
        status, value = self.request(server, "/api/local-workbench")
        self.assertEqual(status, 200)
        return {"Origin": f"http://127.0.0.1:{server.server_port}", "X-AutoResearch-CSRF": value["csrf_token"] or "disabled",
                "Content-Type": "application/json"}

    def input_body(self):
        payload, _ = self.capture("id,batch,x,y\na,G,0,1\nb,G,2,0\n")
        return {"request_id": "browser-intake", "goal": "Inspect grouped zeros and retain all records.",
                "budget_ref": "test-only-original-fee-unknown", "max_tool_calls": 2,
                "input": {"file_name": payload["spec"]["file"], "csv_base64": payload["source"]["bytes_base64"],
                          "spec_base64": payload["spec_source"]["bytes_base64"]}}

    def test_optin_origin_session_and_strict_framing_precede_dispatch(self):
        workspace = FakeWorkspace()
        server = self.serve(local_workspace=workspace, allow_local_actions=True)
        valid = self.session(server)
        for headers, raw, expected in [
            ({**valid, "Origin": "http://external.invalid"}, b'{}', 403),
            ({**valid, "X-AutoResearch-CSRF": "wrong"}, b'{}', 403),
            ({**valid, "Host": "external.invalid"}, b'{}', 403),
            ({**valid, "Sec-Fetch-Site": "cross-site"}, b'{}', 403),
            ({key: value for key, value in valid.items() if key != "Origin"}, b'{}', 403),
            ({**valid, "Content-Length": str(MAX_LOCAL_REQUEST_BYTES + 1)}, b'', 413),
            (valid, b'{"id":1,"id":2}', 400),
            (valid, b'{"value":NaN}', 400),
        ]:
            with self.subTest(expected=expected, raw=raw):
                status, _ = self.request(server, "/api/local-workbench/create", "POST", raw, headers)
                self.assertEqual(status, expected)
        self.assertEqual(workspace.calls, [])
        other = self.serve(local_workspace=workspace, allow_local_actions=True)
        self.assertEqual(self.request(other, "/api/local-workbench/create", "POST", b'{}',
                                     {**valid, "Origin": f"http://127.0.0.1:{other.server_port}"})[0], 403)
        self.assertEqual(self.request(server, "/api/local-workbench/create", "POST", b'{}', valid)[0], 200)
        self.assertEqual(workspace.calls, [{}])
        self.assertEqual(self.request(server, "/api/local-workbench/create", "PUT", b'{}', valid)[0], 405)

    def test_large_framed_origin_and_csrf_denials_return_json_without_dispatch(self):
        workspace = FakeWorkspace()
        server = self.serve(local_workspace=workspace, allow_local_actions=True)
        valid = self.session(server)
        raw = b'{"padding":"' + b'x' * (1024 * 1024) + b'"}'
        for headers in ({**valid, "X-AutoResearch-CSRF": "invalid"},
                        {**valid, "Origin": "http://external.invalid"}):
            for attempt in range(4):
                with self.subTest(origin=headers["Origin"], attempt=attempt):
                    status, response = self.request(server, "/api/local-workbench/create", "POST", raw, headers)
                    self.assertEqual((status, response["code"]), (403, "LOCAL_ORIGIN_REQUIRED"))
        self.assertEqual(workspace.calls, [])

    def test_valid_intake_and_explicit_choice_use_original_project_ledger(self):
        root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        server = self.serve(local_workspace=LocalWorkbench(root / "managed"), allow_local_actions=True)
        headers = self.session(server)
        self.assertEqual(self.request(server, "/api/project")[0], 404)
        status, created = self.request(server, "/api/local-workbench/create", "POST", self.input_body(), headers)
        self.assertEqual(status, 200)
        status, project = self.request(server, "/api/project")
        self.assertEqual((status, project["id"]), (200, created["project_id"]))
        status, context = self.request(server, "/api/project/selection-context.json")
        self.assertEqual(status, 200, context)
        choice = context["candidates"][0]
        proposal = {"schema_version": "project-selection-proposal-v1", "context_sha256": context["context_sha256"],
                    "provider": {"kind": "human", "label": "Local test user"},
                    "choice": {"kind": "execute", "candidate_id": choice["id"]},
                    "rationale": "Inspect the declared fields once; target and independence remain unconfirmed.",
                    "evidence_citation_ids": []}
        body = {"request_id": "browser-choice", "project_id": created["project_id"],
                "expected_state_version": context["state_version"], "proposal": proposal}
        status, selected = self.request(server, "/api/local-workbench/advance", "POST", body, headers)
        self.assertEqual((status, selected["status"]), (200, "completed"))
        _, before = self.request(server, "/api/project")
        status, replay = self.request(server, "/api/local-workbench/advance", "POST", body, headers)
        self.assertEqual((status, replay["child_request_id"]), (200, selected["child_request_id"]))
        _, after = self.request(server, "/api/project")
        self.assertEqual(before["snapshot_ref"], after["snapshot_ref"])
        self.assertEqual(after["budget"]["local_tool_calls_used"], 1)
        self.assertEqual(after["budget"]["model_requests_allowed"], 0)
        _, next_context = self.request(server, "/api/project/selection-context.json")
        self.assertEqual(next_context["candidates"][0]["method_id"], "data.grouped-quality-profile")

    def test_disabled_and_existing_readonly_services_keep_write_denial(self):
        workspace = FakeWorkspace()
        disabled = self.serve(local_workspace=workspace)
        headers = self.session(disabled)
        self.assertEqual(self.request(disabled, "/api/local-workbench/create", "POST", b'{}', headers)[0], 405)
        self.assertEqual(workspace.calls, [])
        root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        payload, _ = self.capture("id,batch,x,y\na,G,1,2\n")
        (root / "input").mkdir()
        packet = root / "input/source.json"
        packet.write_text(canonical(payload), encoding="utf-8")
        project = ResearchProject(root / "project")
        project.create(source=packet, method_id="data.tabular-quality-audit", goal="Read-only regression.", budget_ref="test-only")
        readonly = self.serve(workspace=project.root)
        self.assertEqual(self.request(readonly, "/api/project")[0], 200)
        self.assertEqual(self.request(readonly, "/api/local-workbench/create", "POST", b'{}', headers)[0], 405)
        self.assertEqual(self.request(readonly, "/api/project", "POST", b'{}', headers)[0], 405)
        self.assertEqual(project.status()["actions"], [])


if __name__ == "__main__":
    unittest.main()
