"""Two workbench recipe checks: read-only previews/gates and real feedback steps."""
import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import test_local_evidence as evidence_fixtures
import test_local_workbench as manager_fixtures
import test_local_workbench_http as http_fixtures
from autoresearch import grouped_quality_adapter as grouped, source_evidence_adapter as reader, tabular_quality_adapter as tabular
from autoresearch.local_workbench import LocalWorkbench
from autoresearch.project_controller import ProjectController


class LocalRecipeWorkbenchTests(unittest.TestCase):
    serve = http_fixtures.LocalWorkbenchHTTPTests.serve
    request = http_fixtures.LocalWorkbenchHTTPTests.request
    session = http_fixtures.LocalWorkbenchHTTPTests.session

    def setUp(self):
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.manager = LocalWorkbench(self.root / "managed")

    def populate(self):
        self.manager.create(manager_fixtures.LocalWorkbenchTests.create_body(self))
        self.project, _ = self.manager.binding()
        context = ProjectController(self.project.root).selection_context()
        self.manager.advance({"request_id": "bootstrap-quality", "project_id": context["project_id"],
            "expected_state_version": context["state_version"],
            "proposal": manager_fixtures.LocalWorkbenchTests.proposal(self, context, tabular.TOOL_ID)})
        self.manager.register_evidence(evidence_fixtures.LocalEvidenceTests.body(self))

    def body(self, preview, request_id="browser-recipe", *, recipe=None):
        return {"request_id": request_id, "project_id": preview["project_id"],
                "expected_state_version": preview["state_version"],
                "recipe": preview["recipes"][0]["recipe"] if recipe is None else recipe}

    @staticmethod
    def selected_method(entry):
        return next((item["method_id"] for item in entry["decision"]["method_decisions"] if item["outcome"] == "selected"), None)

    def test_fixed_previews_are_readonly_and_write_session_active_pending_gates_hold(self):
        disabled = self.serve(local_workspace=self.manager)
        empty_db = self.manager.db.read_bytes()
        status, empty = self.request(disabled, "/api/local-workbench/recipes")
        self.assertEqual((status, empty), (200, {"schema_version": "local-research-recipes-v1", "project_id": None,
                                              "state_version": None, "context_sha256": None, "recipes": []}))
        self.assertEqual(self.manager.db.read_bytes(), empty_db)
        self.populate()
        core_bytes, manager_bytes = self.project.db.read_bytes(), self.manager.db.read_bytes()
        enabled = self.serve(local_workspace=self.manager, allow_local_actions=True)
        headers = self.session(enabled)
        with patch.object(grouped, "execute", side_effect=AssertionError("Preview cannot execute tools")), \
                patch.object(reader, "execute", side_effect=AssertionError("Preview cannot read selections")), \
                patch("autoresearch.host_model_selection.run_claude_selection") as model:
            status, preview = self.request(disabled, "/api/local-workbench/recipes")
            self.assertEqual((status, preview["project_id"], preview["state_version"]), (200, self.project.status()["id"], self.project.status()["state_version"]))
            self.assertEqual([entry["recipe"]["id"] for entry in preview["recipes"]], ["tabular-group-first", "tabular-source-first"])
            self.assertEqual([self.selected_method(entry) for entry in preview["recipes"]], [grouped.TOOL_ID, "research.source-selection"])
            self.assertEqual({entry["decision"]["context_sha256"] for entry in preview["recipes"]}, {preview["context_sha256"]})
            self.assertEqual((self.project.db.read_bytes(), self.manager.db.read_bytes()), (core_bytes, manager_bytes))
            body = self.body(preview)
            self.assertEqual(self.request(disabled, "/api/local-workbench/advance-recipe", "POST", body, self.session(disabled))[0], 405)
            for wrong in ({**headers, "Origin": "http://external.invalid"}, {**headers, "X-AutoResearch-CSRF": "wrong"}):
                status, error = self.request(enabled, "/api/local-workbench/advance-recipe", "POST", body, wrong)
                self.assertEqual((status, error["code"]), (403, "LOCAL_ORIGIN_REQUIRED"))
            status, error = self.request(enabled, "/api/local-workbench/advance-recipe", "POST", {**body, "path": "outside.json"}, headers)
            self.assertEqual((status, error["code"]), (400, "INVALID_REQUEST"))
            self.assertEqual(self.request(enabled, "/api/local-workbench/recipes?path=outside.json")[0], 400)
            self.assertEqual((self.project.db.read_bytes(), self.manager.db.read_bytes()), (core_bytes, manager_bytes))
            with self.manager._connect() as con:
                self.manager._accept(con, {"request_id": "pending-evidence"}, "fixture", "evidence", {"project_id": body["project_id"]})
            status, error = self.request(enabled, "/api/local-workbench/advance-recipe", "POST", body, headers)
            self.assertEqual((status, error["code"]), (409, "OPERATION_INCOMPLETE"))
            self.manager.create(manager_fixtures.LocalWorkbenchTests.create_body(self, "other-project"))
            status, error = self.request(enabled, "/api/local-workbench/advance-recipe", "POST", body, headers)
            self.assertEqual((status, error["code"]), (409, "STALE_STATE"))
            model.assert_not_called()

    def test_recipe_post_preserves_original_id_changes_with_feedback_then_waits(self):
        self.populate()
        server = self.serve(local_workspace=self.manager, allow_local_actions=True)
        headers = self.session(server)
        _, preview = self.request(server, "/api/local-workbench/recipes")
        first = self.body(preview)
        with patch.object(grouped, "execute", wraps=grouped.execute) as group, \
                patch.object(reader, "execute", wraps=reader.execute) as extract, \
                patch("autoresearch.host_model_selection.run_claude_selection") as model:
            status, grouped_result = self.request(server, "/api/local-workbench/advance-recipe", "POST", first, headers)
            self.assertEqual((status, grouped_result["status"], grouped_result["decision"]["next_action"]["method_id"]), (200, "completed", grouped.TOOL_ID))
            self.assertEqual(grouped_result["recipe_decision"]["recipe"], first["recipe"])
            after_group = self.project.status()
            status, replay = self.request(server, "/api/local-workbench/advance-recipe", "POST", first, headers)
            self.assertEqual((status, replay["replayed"], replay["child_request_id"]), (200, True, grouped_result["child_request_id"]))
            self.assertEqual(self.project.status(), after_group)
            changed = copy.deepcopy(first)
            changed["recipe"]["question"] += " Changed recipe content."
            status, error = self.request(server, "/api/local-workbench/advance-recipe", "POST", changed, headers)
            self.assertEqual((status, error["code"]), (409, "IDEMPOTENCY_CONFLICT"))
            _, feedback = self.request(server, "/api/local-workbench/recipes")
            self.assertNotEqual(feedback["context_sha256"], preview["context_sha256"])
            self.assertEqual(self.selected_method(feedback["recipes"][0]), "research.source-selection")
            second = self.body(feedback, "browser-recipe-source")
            status, source = self.request(server, "/api/local-workbench/advance-recipe", "POST", second, headers)
            self.assertEqual((status, source["status"], source["decision"]["next_action"]["method_id"]), (200, "completed", "research.source-selection"))
            _, exhausted = self.request(server, "/api/local-workbench/recipes")
            self.assertTrue(all(entry["decision"]["proposal"]["choice"] == {"kind": "wait"} for entry in exhausted["recipes"]))
            wait_body = self.body(exhausted, "browser-recipe-wait")
            status, waiting = self.request(server, "/api/local-workbench/advance-recipe", "POST", wait_body, headers)
            self.assertEqual((status, waiting["status"], waiting["child_request_id"]), (200, "waiting", None))
            after_wait = self.project.status()
            _, replay_wait = self.request(server, "/api/local-workbench/advance-recipe", "POST", wait_body, headers)
            self.assertTrue(replay_wait["replayed"])
            self.assertEqual(self.project.status(), after_wait)
            group.assert_called_once()
            extract.assert_called_once()
            model.assert_not_called()
        self.assertEqual((after_wait["budget"]["local_tool_calls_used"], after_wait["budget"]["evidence_reads_used"]), (2, 1))
        self.assertEqual((after_wait["budget"]["new_model_requests"], after_wait["budget"]["new_fits"]), (0, 0))


if __name__ == "__main__":
    unittest.main()
