"""Three isolated move/recovery/boundary checks; no model, research tool or real project."""
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

import test_tabular_quality_adapter as fixtures
import test_local_workbench as manager_fixtures
from autoresearch.contracts import ResearchError, canonical
from autoresearch.host_model_selection import HostModelSelection
from autoresearch.local_workbench import LocalWorkbench
from autoresearch.research_project import ResearchProject


class LocalProjectImportTests(unittest.TestCase):
    capture = fixtures.TabularQualityAdapterTests.capture
    create_body = manager_fixtures.LocalWorkbenchTests.create_body

    def setUp(self):
        self.base = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.manager = LocalWorkbench(self.base / "manager")
        self.original_active = self.manager.create(self.create_body())["project_id"]

    def external(self, name="external", phase="applied"):
        payload, _ = self.capture("id,batch,x,y\na,G,0,1\nb,G,,2\nc,H,3,0\n", target_column=None, target_unit=None)
        source = self.base / (name + "-source") / "source.json"
        source.parent.mkdir()
        source.write_text(canonical(payload), encoding="utf-8")
        project = ResearchProject(self.base / name)
        project.create(source=source, goal="Synthetic import fixture", budget_ref="shared-test:cap5;cost-unknown",
                       max_tool_calls=1, method_id="data.tabular-quality-audit")
        journal = HostModelSelection(project.root)
        journal.prepare(request_id="plan-one", provider="delegated", purpose="plan", expected_state_version=0,
                        decision_limit=1, cli_budget_usd=0.01, reason="Isolated fixture response, no model execution.")
        if phase == "prepared":
            return project, journal
        response = self.base / (name + "-response.json")
        response.write_text(canonical({"plan": {"question": "Inspect the synthetic table", "basis": "Three constructed records.",
            "steps": "Retain blank and zero values; request one eligible quality check.",
            "expected_feedback": "Use the saved result to decide the next step."}, "reason": "Define the fixture route.",
            "feedback_action_ids": [], "expected_improvement": "Tie the next choice to the declared input."}), encoding="utf-8")
        journal.import_response(request_id="plan-one", response_file=response)
        if phase == "received":
            return project, journal
        journal.consume(request_id="plan-one")
        if phase != "proposed":
            journal.adopt_plan(request_id="plan-one")
        return project, journal

    @staticmethod
    def excerpt():
        return {"host_request_id": "plan-one", "provider": "AgentArts", "model": "Constructed fixture model",
                "started_at": "2026-11-08T12:00:00+08:00", "ended_at": "2026-11-08T12:00:01+08:00",
                "input_tokens": 10, "output_tokens": 20, "total_tokens": 30,
                "record_source": "console_excerpt", "verification": "operator_supplied"}

    @staticmethod
    def original_bytes(project):
        names = ["project.sqlite", "source.json", "host-model-selections/state.json"]
        names += ["host-model-selections/requests/0001/" + name
                  for name in ("context.json", "prompt.json", "delegated.bin", "proposal.json")]
        return {name: (project.root / name).read_bytes() for name in names}

    def assert_code(self, code, callback, **kwargs):
        with self.assertRaises(ResearchError) as caught:
            callback(**kwargs)
        self.assertEqual(caught.exception.code, code)

    def test_move_replay_and_console_projection_preserve_original_project_and_host(self):
        project, journal = self.external()
        before, host, raw = project.status(), journal.status(), self.original_bytes(project)
        host_record = journal.status(request_id="plan-one")
        excerpt = self.excerpt()
        arguments = {"request_id": "import-one", "workspace": str(project.root), "platform_run": excerpt}
        self.assert_code("INVALID_REQUEST", self.manager.import_project,
                         **{**arguments, "platform_run": {**excerpt, "total_tokens": 99}})
        self.assert_code("ARTIFACT_NOT_FOUND", self.manager.import_project,
                         **{**arguments, "platform_run": {**excerpt, "host_request_id": "missing"}})
        imported = self.manager.import_project(**arguments)
        self.assertFalse(imported["replayed"])
        self.assertFalse(project.root.exists())
        moved = ResearchProject(imported["workspace"])
        self.assertEqual(moved.status(), before)
        self.assertEqual(HostModelSelection(moved.root).status(), host)
        self.assertEqual(self.original_bytes(moved), raw)
        self.assertEqual(self.manager.describe()["active_project_id"], self.original_active)
        self.assertEqual(len(self.manager.describe()["projects"]), 2)
        self.assertTrue(LocalWorkbench(self.manager.root).import_project(**arguments)["replayed"])
        self.assertEqual(self.manager.import_record("import-one")["result"], imported)
        self.manager.select({"request_id": "select-imported", "project_id": imported["project_id"]})
        view = self.manager.model_view()
        self.assertEqual(view["platform_runs"], [excerpt])
        self.assertEqual(view["records"][0], host_record)
        self.assertFalse(view["records"][0]["execution_declaration"]["execution_verified"])
        self.assertEqual(view["journal"]["usage"]["decision_slots_used"], 1)
        self.assertEqual(self.original_bytes(moved), raw)
        self.assertEqual(moved.status()["budget"], before["budget"])
        extra, _ = self.external("over-limit")
        with patch("autoresearch.local_workbench.MAX_PROJECTS", 2):
            self.assert_code("PROJECT_LIMIT", self.manager.create, body=self.create_body("over-limit-create"))
            self.assert_code("PROJECT_LIMIT", self.manager.import_project, request_id="over-limit-import", workspace=extra.root)
        self.assertTrue(extra.root.is_dir())
        self.assertEqual(len(self.manager.describe()["projects"]), 2)

    def test_explicit_same_id_recovers_before_and_after_rename_without_a_second_ledger(self):
        project, _ = self.external()
        before, raw = project.status(), self.original_bytes(project)
        arguments = {"request_id": "recover-import", "workspace": str(project.root)}
        with patch.object(Path, "rename", side_effect=OSError("Constructed pre-move interruption")):
            self.assert_code("WORKBENCH_OPERATION_FAILED", self.manager.import_project, **arguments)
        saved = self.manager.import_record(arguments["request_id"])
        self.assertEqual(saved["status"], "incomplete")
        self.assertTrue(project.root.is_dir())
        target = Path(saved["intent"]["target_workspace"])
        self.assertFalse(target.exists())
        rename = Path.rename

        def interrupt_after_rename(path, destination):
            rename(path, destination)
            raise KeyboardInterrupt("Constructed interruption after the directory moved")

        with patch.object(Path, "rename", interrupt_after_rename):
            with self.assertRaises(KeyboardInterrupt):
                self.manager.import_project(**arguments)
        self.assertFalse(project.root.exists())
        self.assertTrue(target.is_dir())
        self.assertIn(arguments["request_id"], [item["request_id"] for item in self.manager.describe()["pending_requests"]])
        recovered = LocalWorkbench(self.manager.root).import_project(**arguments)
        self.assertTrue(recovered["replayed"])
        moved = ResearchProject(recovered["workspace"])
        self.assertEqual(moved.status(), before)
        self.assertEqual(self.original_bytes(moved), raw)
        self.assertEqual(self.manager.describe()["active_project_id"], self.original_active)
        self.assertEqual(self.manager.describe()["pending_requests"], [])
        duplicate = self.base / "duplicate-fixture"
        shutil.copytree(target, duplicate)
        self.assert_code("PROJECT_EXISTS", self.manager.import_project, request_id="duplicate", workspace=duplicate)
        self.assert_code("WORKBENCH_OVERLAP", self.manager.import_project, request_id="overlap", workspace=target)
        self.assert_code("WORKBENCH_OVERLAP", self.manager.import_project, request_id="ancestor", workspace=self.base)
        self.assert_code("IDEMPOTENCY_CONFLICT", self.manager.import_project,
                         **{**arguments, "platform_run": self.excerpt()})

    def test_pending_tool_host_and_unadopted_proposal_are_rejected_before_any_move(self):
        for phase in ("prepared", "received", "proposed"):
            with self.subTest(phase=phase):
                project, journal = self.external("pending-" + phase, phase)
                before, host = project.status(), journal.status()
                self.assert_code("HOST_SELECTION_PENDING", self.manager.import_project,
                                 request_id="reject-" + phase, workspace=project.root)
                self.assertEqual(project.status(), before)
                self.assertEqual(journal.status(), host)
        project, _ = self.external("unknown-tool")
        with project._writer(), project._connect() as con:
            con.execute("INSERT INTO actions VALUES(?,?,?)", ("unknown-action", "fixture", canonical(
                {"id": "action-fixture", "request_id": "unknown-action", "command": "data.tabular-quality-audit", "status": "unknown"})))
        before = project.status()
        self.assert_code("PROJECT_BUSY", self.manager.import_project, request_id="reject-tool", workspace=project.root)
        self.assertEqual(project.status(), before)
        self.assertEqual(len(self.manager.describe()["projects"]), 1)
        self.assertEqual(self.manager.describe()["pending_requests"], [])


if __name__ == "__main__":
    unittest.main()
