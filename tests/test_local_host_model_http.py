"""Two HTTP checks: explicit host gates and durable original-request recovery."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import test_local_workbench_http as fixtures
from autoresearch.contracts import ResearchError, canonical
from autoresearch.host_model_selection import HostModelSelection
from autoresearch.local_workbench import LocalWorkbench
from autoresearch.project_workbench import create_project_server


class LocalHostModelHTTPTests(unittest.TestCase):
    serve = fixtures.LocalWorkbenchHTTPTests.serve
    request = fixtures.LocalWorkbenchHTTPTests.request
    session = fixtures.LocalWorkbenchHTTPTests.session
    input_body = fixtures.LocalWorkbenchHTTPTests.input_body
    capture = fixtures.LocalWorkbenchHTTPTests.capture

    def setUp(self):
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.manager = LocalWorkbench(self.root / "managed")
        self.executable = str(Path(__file__).absolute())

    def model_body(self, project, request_id="browser-model-1"):
        return {"request_id": request_id, "project_id": project.status()["id"],
                "expected_state_version": project.status()["state_version"], "decision_limit": 1,
                "cli_budget_usd": 0.1, "reason": "Explicit one-decision fixture scope"}

    def transport(self, **kwargs):
        context = json.loads(kwargs["prompt"].split("\n", 1)[1])
        arguments = {"choice": {"kind": "execute", "candidate_id": context["candidates"][0]["id"]},
                     "rationale": "Check the real fixture table and retain its original values.", "evidence_citation_ids": []}
        raw = canonical({"type": "result", "subtype": "success", "is_error": False,
                         "result": canonical(arguments), "modelUsage": {"fixture-route": {}},
                         "usage": {"input_tokens": 23, "output_tokens": 17}, "total_cost_usd": 0.02}).encode("utf-8")
        folder = kwargs["directory"]
        prompt = kwargs["prompt"].encode("utf-8")
        launch = {"argv": [kwargs["executable"], "--system-prompt", kwargs["system_prompt"]],
                  "stdin_sha256": hashlib.sha256(prompt).hexdigest(), "stdin_bytes": len(prompt),
                  "configured_max_budget_usd": kwargs["max_budget_usd"]}
        (folder / "launch.json").write_text(canonical(launch), encoding="utf-8")
        (folder / "stdout.bin").write_bytes(raw)
        (folder / "stderr.bin").write_bytes(b"")
        receipt = {"status": "received", "exit_code": 0, "stdout_file": "stdout.bin",
                   "stdout_bytes": len(raw), "stdout_sha256": hashlib.sha256(raw).hexdigest()}
        (folder / "exit.json").write_text(canonical(receipt), encoding="utf-8")
        return receipt

    def test_default_disabled_origin_active_and_host_path_gates_precede_dispatch(self):
        with self.assertRaises(ResearchError) as caught:
            create_project_server(local_workspace=self.manager, claude_executable=self.executable, port=0)
        self.assertEqual(caught.exception.code, "INVALID_REQUEST")
        disabled = self.serve(local_workspace=self.manager, allow_local_actions=True)
        self.assertEqual(self.request(disabled, "/api/local-workbench/model")[1], {
            "schema_version": "local-host-model-view-v1", "enabled": False, "project_id": None,
            "journal": None, "records": []})
        self.manager.create(self.input_body())
        project, _ = self.manager.binding()
        body = self.model_body(project)
        enabled = self.serve(local_workspace=self.manager, allow_local_actions=True, claude_executable=self.executable)
        headers = self.session(enabled)
        with patch("autoresearch.host_model_selection.run_claude_selection") as dispatch:
            status, error = self.request(disabled, "/api/local-workbench/model-advance", "POST", body, self.session(disabled))
            self.assertEqual((status, error["code"]), (405, "MODEL_DISABLED"))
            status, error = self.request(enabled, "/api/local-workbench/model-advance", "POST", body,
                                         {**headers, "Origin": "http://external.invalid"})
            self.assertEqual((status, error["code"]), (403, "LOCAL_ORIGIN_REQUIRED"))
            for extra in ({"executable": self.executable}, {"provider": "delegated"}, {"commands": ["whoami"]}):
                status, error = self.request(enabled, "/api/local-workbench/model-advance", "POST", {**body, **extra}, headers)
                self.assertEqual((status, error["code"]), (400, "INVALID_REQUEST"))
            self.manager.create({**self.input_body(), "request_id": "second-project"})
            status, error = self.request(enabled, "/api/local-workbench/model-advance", "POST", body, headers)
            self.assertEqual((status, error["code"]), (409, "STALE_STATE"))
            current, _ = self.manager.binding()
            with self.manager._connect() as con:
                self.manager._accept(con, {"request_id": "unfinished-evidence"}, "fixture", "evidence",
                                     {"project_id": current.status()["id"]})
            status, error = self.request(enabled, "/api/local-workbench/model-advance", "POST", self.model_body(current), headers)
            self.assertEqual((status, error["code"]), (409, "OPERATION_INCOMPLETE"))
            with self.manager._connect() as con:
                self.manager._save(con, "unfinished-evidence", {"status": "completed", "intent": {"project_id": current.status()["id"]}})
            with current._writer(), current._connect() as con:
                saved = current._project(con)
                saved["source_requests"] = [{"request_id": "unresolved-source", "status": "unknown"}]
                saved["state_version"] += 1
                current._save(con, saved)
            status, error = self.request(enabled, "/api/local-workbench/model-advance", "POST", self.model_body(current), headers)
            self.assertEqual((status, error["code"]), (409, "NO_HOST_CANDIDATES"))
            dispatch.assert_not_called()
        self.assertFalse((project.root / "host-model-selections/state.json").exists())

    def test_http_reopen_after_core_commit_recovers_original_child_and_get_never_dispatches(self):
        self.manager.create(self.input_body())
        project, _ = self.manager.binding()
        body = self.model_body(project)
        server = self.serve(local_workspace=self.manager, allow_local_actions=True, claude_executable=self.executable)
        headers = self.session(server)
        original_save = HostModelSelection._save

        def interrupt_after_commit(journal, state):
            if state["requests"][body["request_id"]]["status"] == "applied":
                raise OSError("Fixture interruption after committed core result")
            original_save(journal, state)

        with patch("autoresearch.host_model_selection.run_claude_selection", side_effect=self.transport) as dispatch:
            status, empty = self.request(server, "/api/local-workbench/model")
            self.assertEqual((status, empty["enabled"], empty["records"]), (200, True, []))
            self.assertFalse((project.root / "host-model-selections").exists())
            with patch.object(HostModelSelection, "_save", interrupt_after_commit):
                status, error = self.request(server, "/api/local-workbench/model-advance", "POST", body, headers)
            self.assertEqual((status, error["code"]), (500, "LOCAL_COMMAND_FAILED"))
            saved = project.status()
            self.assertEqual(len(saved["actions"]), 1)
            child = saved["controller_requests"][0]["child_request_id"]
            _, view = self.request(server, "/api/local-workbench/model")
            self.assertEqual(view["records"][0]["status"], "received")
            self.assertEqual(view["journal"]["usage"]["cli_launch_attempts"], 1)
            reopened = self.serve(local_workspace=LocalWorkbench(self.manager.root), allow_local_actions=True,
                                  claude_executable=self.executable)
            resume = {"request_id": body["request_id"], "project_id": body["project_id"]}
            status, result = self.request(reopened, "/api/local-workbench/model-resume", "POST", resume, self.session(reopened))
            self.assertEqual((status, result["status"], result["model_record"]["outcome"]["status"]), (200, "applied", "completed"))
            self.assertEqual(result["model_record"]["outcome"]["child_request_id"], child)
            self.assertTrue(result["model_record"]["outcome"]["replayed"])
            status, replay = self.request(server, "/api/local-workbench/model-advance", "POST", body, headers)
            self.assertEqual((status, replay["model_record"]), (200, result["model_record"]))
            _, again = self.request(reopened, "/api/local-workbench/model")
            self.assertEqual((again["journal"]["usage"]["cli_launch_attempts"], again["journal"]["usage"]["known_cli_reported_cost_usd"]), (1, 0.02))
            self.assertEqual(again["journal"]["native_local_model_budget"]["new_model_requests"], 0)
            self.assertEqual(project.status()["snapshot_ref"], saved["snapshot_ref"])
            readonly = self.serve(local_workspace=self.manager)
            _, historical = self.request(readonly, "/api/local-workbench/model")
            self.assertEqual((historical["enabled"], historical["records"]), (False, again["records"]))
            changed = self.serve(local_workspace=self.manager, allow_local_actions=True, claude_executable=fixtures.__file__)
            status, error = self.request(changed, "/api/local-workbench/model-resume", "POST", resume, self.session(changed))
            self.assertEqual((status, error["code"]), (409, "CONFIG_CHANGED"))
            status, error = self.request(server, "/api/local-workbench/model-resume", "POST", {**resume, "request_id": "not-prepared"}, headers)
            self.assertEqual((status, error["code"]), (400, "ARTIFACT_NOT_FOUND"))
            for updates, code in (({"request_id": "new-id"}, "HOST_DECISION_LIMIT"),
                                  ({"request_id": "new-id", "decision_limit": 2}, "HOST_GRANT_CHANGED")):
                status, error = self.request(server, "/api/local-workbench/model-advance", "POST", {**body, **updates}, headers)
                self.assertEqual((status, error["code"]), (409, code))
            dispatch.assert_called_once()


if __name__ == "__main__":
    unittest.main()
