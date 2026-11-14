"""Two report binding checks using real host/core state and fixture PDF bytes."""
import http.client
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import test_local_workbench_http as fixtures
from autoresearch.contracts import ResearchError, canonical
from autoresearch.host_model_report import host_model_snapshot_sha256
from autoresearch.host_model_selection import HostModelSelection
from autoresearch.local_workbench import LocalWorkbench
from autoresearch.project_report import export_report
from autoresearch.project_workbench import check_project_workbench


class HostModelReportHTTPTests(unittest.TestCase):
    serve = fixtures.LocalWorkbenchHTTPTests.serve
    request = fixtures.LocalWorkbenchHTTPTests.request
    session = fixtures.LocalWorkbenchHTTPTests.session
    input_body = fixtures.LocalWorkbenchHTTPTests.input_body
    capture = fixtures.LocalWorkbenchHTTPTests.capture

    def setUp(self):
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.manager = LocalWorkbench(self.root / "managed")
        self.manager.create(self.input_body())
        self.project, _ = self.manager.binding()

    def prepare(self, project, request_id):
        return HostModelSelection(project.root).prepare(request_id=request_id, provider="delegated",
            expected_state_version=project.status()["state_version"], decision_limit=2, cli_budget_usd=0.1,
            reason="Two bounded fixture decisions, no actual delegated dispatch")

    def download(self, server, name):
        connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=5)
        self.addCleanup(connection.close)
        connection.request("GET", "/api/project/" + name)
        response = connection.getresponse()
        return response.status, response.read()

    def legacy_copy(self, source, name):
        target = self.root / name
        target.mkdir()
        manifest = json.loads((source / "manifest.json").read_text(encoding="utf-8"))
        manifest.pop("host_model_snapshot_sha256", None)
        for filename in manifest["files"]:
            (target / filename).write_bytes((source / filename).read_bytes())
        (target / "manifest.json").write_text(canonical(manifest), encoding="utf-8")
        return target

    def test_host_snapshot_change_alone_stales_report_download_and_preserves_cached_export(self):
        journal = HostModelSelection(self.project.root)
        prepared = self.prepare(self.project, "delegated-first")
        arguments = {"choice": {"kind": "execute", "candidate_id": prepared["context"]["candidates"][0]["id"]},
                     "rationale": "Inspect the fixture table without accepting scientific claims.", "evidence_citation_ids": []}
        response = self.root / "delegated.json"
        response.write_text(canonical(arguments), encoding="utf-8")
        journal.import_response(request_id="delegated-first", response_file=response)
        self.assertEqual(journal.consume(request_id="delegated-first")["outcome"]["status"], "completed")
        server = self.serve(local_workspace=self.manager, allow_local_actions=True)
        headers = self.session(server)
        state = self.project.status()
        body = {"request_id": "report-with-host", "project_id": state["id"], "expected_state_version": state["state_version"]}
        with patch("autoresearch.project_report._pdf", return_value=b"%PDF fixture"), \
                patch("autoresearch.host_model_selection.run_claude_selection") as dispatch:
            status, result = self.request(server, "/api/local-workbench/report", "POST", body, headers)
            self.assertEqual((status, result["status"]), (200, "exported"))
            manifest = result["manifest"]
            self.assertEqual(set(manifest["files"]), {"report.json", "report.md", "report.pdf", "input.json"})
            self.assertEqual(manifest["host_model_snapshot_sha256"], host_model_snapshot_sha256(self.project.root))
            _, report = self.manager.binding()
            originals = {p.name: p.read_bytes() for p in report.iterdir()}
            _, projection = self.request(server, "/api/project")
            self.assertEqual((projection["report"]["available"], projection["report"]["stale"]), (True, False))
            for name in manifest["files"]:
                status, raw = self.download(server, name)
                self.assertEqual((status, raw), (200, originals[name]))
            payload = json.loads(originals["report.json"])
            self.assertEqual(payload["host_models"]["status"]["usage"]["delegated_outputs_received"], 1)
            self.assertEqual(json.loads(originals["input.json"])["host_models"]["snapshot_sha256"], manifest["host_model_snapshot_sha256"])
            legacy = self.legacy_copy(report, "legacy-with-external")
            with self.assertRaises(ResearchError) as caught:
                check_project_workbench(workspace=self.project.root, report=legacy)
            self.assertEqual(caught.exception.code, "REPORT_STALE")
            before = self.project.status()
            self.prepare(self.project, "delegated-second")
            self.assertEqual(self.project.status(), before)
            self.assertNotEqual(host_model_snapshot_sha256(self.project.root), manifest["host_model_snapshot_sha256"])
            _, projection = self.request(server, "/api/project")
            self.assertEqual((projection["report"]["available"], projection["report"]["stale"]), (False, True))
            for name in manifest["files"]:
                status, raw = self.download(server, name)
                self.assertEqual((status, json.loads(raw)["code"]), (409, "REPORT_STALE"))
            with self.assertRaises(ResearchError) as caught:
                check_project_workbench(workspace=self.project.root, report=report)
            self.assertEqual(caught.exception.code, "REPORT_STALE")
            cached = self.manager.export(body)
            self.assertTrue(cached["replayed"])
            self.assertEqual(cached["manifest"], manifest)
            self.assertEqual({p.name: p.read_bytes() for p in report.iterdir()}, originals)
            dispatch.assert_not_called()

    def test_legacy_without_external_remains_readable_and_publish_rechecks_host_state(self):
        with patch("autoresearch.project_report._pdf", return_value=b"%PDF fixture"):
            export_report(workspace=self.project.root, output=self.root / "new-report")
            legacy = self.legacy_copy(self.root / "new-report", "legacy-without-external")
            server = self.serve(workspace=self.project.root, report=legacy)
            self.assertTrue(check_project_workbench(workspace=self.project.root, report=legacy)["ok"])
            _, projection = self.request(server, "/api/project")
            self.assertEqual((projection["report"]["available"], projection["report"]["stale"]), (True, False))
            self.assertFalse((self.project.root / "host-model-selections").exists())
            self.assertEqual(self.download(server, "report.pdf"), (200, b"%PDF fixture"))
            (legacy / "report.md").write_bytes(b"changed report evidence")
            status, raw = self.download(server, "report.md")
            self.assertEqual((status, json.loads(raw)["code"]), (500, "EVIDENCE_CHANGED"))
            _, projection = self.request(server, "/api/project")
            self.assertFalse(projection["report"]["available"])
            self.assertEqual(projection["report"]["error"], "REPORT_UNAVAILABLE")

            def mutate_host_after_export(*, workspace, output, before_publish=None):
                manifest = export_report(workspace=workspace, output=output, before_publish=before_publish)
                self.prepare(self.project, "prepared-during-publication")
                return manifest

            body = {"request_id": "report-race", "project_id": self.project.status()["id"],
                    "expected_state_version": self.project.status()["state_version"]}
            before = self.project.status()
            with patch("autoresearch.project_report.export_report", side_effect=mutate_host_after_export), \
                    patch("autoresearch.host_model_selection.run_claude_selection") as dispatch:
                with self.assertRaises(ResearchError) as caught:
                    self.manager.export(body)
                self.assertEqual(caught.exception.code, "STALE_STATE")
                dispatch.assert_not_called()
            self.assertEqual(self.project.status(), before)
            self.assertIsNone(self.manager.binding()[1])
            pending = self.manager.describe()["pending_requests"]
            self.assertEqual((pending[0]["request_id"], pending[0]["status"]), ("report-race", "incomplete"))


if __name__ == "__main__":
    unittest.main()
