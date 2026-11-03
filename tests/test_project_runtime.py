"""One real loopback source-drift check over a disposable file and workspace."""
import http.client
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import test_local_workbench_http as http_fixtures


class ProjectRuntimeTests(unittest.TestCase):
    serve = http_fixtures.LocalWorkbenchHTTPTests.serve
    request = http_fixtures.LocalWorkbenchHTTPTests.request
    session = http_fixtures.LocalWorkbenchHTTPTests.session

    def test_changed_startup_source_blocks_previews_and_dispatch_but_keeps_reads(self):
        directory = Path(self.enterContext(tempfile.TemporaryDirectory()))
        source = directory / "loaded_module.py"
        source.write_text("loaded = 1\n", encoding="utf-8")
        workspace = http_fixtures.FakeWorkspace()
        with patch("autoresearch.project_workbench._runtime_sources", return_value={source: source.read_bytes()}):
            server = self.serve(local_workspace=workspace, allow_local_actions=True)
        headers = self.session(server)
        self.assertEqual(self.request(server, "/api/local-workbench/create", "POST", {}, headers)[0], 200)
        before = list(workspace.calls)
        self.assertEqual(before, [{}])

        source.write_text("loaded = 2\n", encoding="utf-8")
        for path in ("/api/project/selection-context.json", "/api/local-workbench/recipes", "/api/project/knowledge?need=export"):
            status, value = self.request(server, path)
            self.assertEqual((status, value["code"]), (409, "WORKBENCH_RESTART_REQUIRED"))
            self.assertIn("restart this service", value["message"])
        status, value = self.request(server, "/api/local-workbench/create", "POST", {}, headers)
        self.assertEqual((status, value["code"]), (409, "WORKBENCH_RESTART_REQUIRED"))
        self.assertIn("restart this service", value["message"])
        self.assertEqual(workspace.calls, before)
        self.assertEqual(self.request(server, "/api/local-workbench/create", "POST", {}, {**headers, "Origin": "http://external.invalid"})[0], 403)
        self.assertEqual(self.request(server, "/api/local-workbench")[0], 200)
        connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=5)
        self.addCleanup(connection.close)
        connection.request("GET", "/")
        response = connection.getresponse()
        self.assertEqual(response.status, 200)
        self.assertIn(b'data-case="local-workbench"', response.read())

        source.unlink()
        self.assertEqual(self.request(server, "/api/local-workbench/recipes")[1]["code"], "WORKBENCH_RESTART_REQUIRED")
        self.assertEqual(workspace.calls, before)


if __name__ == "__main__":
    unittest.main()
