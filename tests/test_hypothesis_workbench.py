"""Real loopback/persistence wiring for tiny engineering data, not research gains."""
import copy
import json
import unittest

import test_hypothesis_feedback as fixtures
import test_local_workbench_http as http
import test_feedback_policy as policy_fixtures
from autoresearch.contracts import ResearchError, canonical
from autoresearch.host_selection_protocol import build_prompt
from autoresearch.local_workbench import LocalWorkbench
from autoresearch.project_controller import ProjectController
from autoresearch.project_model_protocol import build_request


class HypothesisWorkbenchTests(unittest.TestCase):
    fixture = fixtures.HypothesisFeedbackTests.fixture
    serve = http.LocalWorkbenchHTTPTests.serve
    request = http.LocalWorkbenchHTTPTests.request
    session = http.LocalWorkbenchHTTPTests.session

    def stage(self):
        original, candidate = self.fixture()
        manager = LocalWorkbench(original.root.parent / "manager")
        imported = manager.import_project(request_id="import", workspace=original.root)
        manager.select({"request_id": "activate", "project_id": imported["project_id"]})
        project, _ = manager.binding()
        body = {"request_id": "prediction", "project_id": imported["project_id"],
                "expected_state_version": project.status()["state_version"],
                "hypothesis": {"candidate_id": candidate["id"], "controller_request_id": "future",
                               "metric": "recall@20", "operator": "gt", "threshold": 0}}
        return manager, project, candidate, body

    def test_http_register_execute_reopen_feedback_and_report(self):
        manager, project, candidate, body = self.stage()
        server = self.serve(local_workspace=manager, allow_local_actions=True)
        headers = self.session(server)
        route = "/api/local-workbench/hypothesis"
        before = project.status()["budget"]
        denied, _ = self.request(server, route, "POST", body, {**headers, "Origin": "http://invalid.example"})
        self.assertEqual(denied, 403)
        status, accepted = self.request(server, route, "POST", body, headers)
        self.assertEqual(status, 200, accepted)
        replay_status, replay = self.request(server, route, "POST", body, headers)
        self.assertEqual(replay_status, 200, replay)
        self.assertEqual(replay["hypothesis"], accepted["hypothesis"])
        self.assertEqual(project.status()["budget"], before)
        bad = copy.deepcopy(body)
        bad["hypothesis"]["threshold"] = 0.1
        status, response = self.request(server, route, "POST", bad, headers)
        self.assertEqual((status, response["code"]), (409, "IDEMPOTENCY_CONFLICT"))
        context = ProjectController(project.root).selection_context()
        self.assertEqual(context["hypothesis_feedback"]["items"][0]["outcome"], "unknown")
        self.assertIn("not scientific approval", build_prompt(context)["system"])
        proposal = {"schema_version": "project-selection-proposal-v1", "context_sha256": context["context_sha256"],
                    "provider": {"kind": "operator_assistant", "label": "Engineering fixture, no model"},
                    "choice": {"kind": "execute", "candidate_id": candidate["id"]},
                    "rationale": "Execute the original fixed comparison", "evidence_citation_ids": []}
        advance = {"request_id": "future", "project_id": body["project_id"],
                   "expected_state_version": context["state_version"], "proposal": proposal}
        status, response = self.request(server, "/api/local-workbench/advance", "POST", advance, headers)
        self.assertEqual(status, 200, response)
        self.assertEqual(response["status"], "completed")
        restarted = LocalWorkbench(manager.root)
        project, _ = restarted.binding()
        context = ProjectController(project.root).selection_context()
        item = context["hypothesis_feedback"]["items"][0]
        self.assertEqual((item["value"], item["outcome"]), (0, "condition_not_met"))
        status, view = self.request(server, "/api/project")
        self.assertEqual(status, 200, view)
        self.assertEqual(view["hypothesis_feedback"], context["hypothesis_feedback"])
        saved = project.status()
        exported = restarted.export({"request_id": "report", "project_id": body["project_id"],
                                     "expected_state_version": saved["state_version"]})
        self.assertEqual(exported["status"], "exported")
        report = json.loads(next((manager.root / "reports").glob("*/report.json")).read_bytes())
        self.assertEqual(report["input"]["hypothesis_registrations"], saved["hypothesis_registrations"])
        self.assertEqual(report["input"]["selection_context"]["hypothesis_feedback"], context["hypothesis_feedback"])
        self.assertEqual(project.status()["budget"]["local_tool_calls_used"], 1)
        self.assertEqual(project.status()["budget"]["new_model_requests"], 0)
        self.assertEqual(project.status()["budget"]["new_fits"], 0)

    def test_manager_receipt_loss_resumes_same_registration(self):
        from unittest.mock import patch
        manager, project, _, body = self.stage()
        original = manager._save
        def lost(con, request_id, record):
            if record.get("status") == "completed":
                raise KeyboardInterrupt("synthetic outer receipt loss")
            return original(con, request_id, record)
        with patch.object(manager, "_save", side_effect=lost):
            with self.assertRaises(KeyboardInterrupt):
                manager.register_hypothesis(body)
        state = project.status()
        self.assertEqual(len(state["hypothesis_registrations"]), 1)
        resumed = LocalWorkbench(manager.root).register_hypothesis(body)
        self.assertEqual(resumed["status"], "completed")
        self.assertEqual(project.status(), state)


class FeedbackAdvanceTests(unittest.TestCase):
    setup_project = policy_fixtures.FeedbackPolicyTests.setup_project
    execute_primary = policy_fixtures.FeedbackPolicyTests.execute_primary
    serve = http.LocalWorkbenchHTTPTests.serve
    request = http.LocalWorkbenchHTTPTests.request
    session = http.LocalWorkbenchHTTPTests.session

    def test_bound_branch_executes_original_audit_and_replays_after_restart(self):
        project, _, registration, candidate = self.setup_project()
        manager = LocalWorkbench(project.root.parent / "manager")
        project_id = project.status()["id"]
        manager.import_project(request_id="import", workspace=project.root)
        manager.select({"request_id": "activate", "project_id": project_id})
        project, _ = manager.binding()
        self.execute_primary(ProjectController(project.root), candidate)
        state = project.status()
        server = self.serve(local_workspace=manager, allow_local_actions=True)
        body = {"request_id": "branch", "project_id": project_id,
                "expected_state_version": state["state_version"], "registration_request_id": registration["request_id"]}
        status, response = self.request(server, "/api/local-workbench/advance-feedback", "POST", body, self.session(server))
        self.assertEqual(status, 200, response)
        self.assertEqual(response["status"], "completed")
        after = project.status()
        self.assertEqual(len(after["actions"]), 2)
        primary, audit = after["actions"]
        self.assertEqual(audit["parameters"], {"based_on_action_id": primary["id"], "based_on_result_sha256": primary["result_sha256"]})
        replay = LocalWorkbench(manager.root).advance_feedback(body)
        self.assertEqual(replay["child_request_id"], response["child_request_id"])
        self.assertEqual(project.status(), after)
        self.assertEqual(after["budget"]["local_tool_calls_used"], 2)
        self.assertEqual(after["budget"]["local_tool_call_limit"], 2)
        self.assertEqual(after["budget"]["new_model_requests"], 0)
        self.assertEqual(after["budget"]["new_fits"], 0)

    def test_unknown_wait_is_frozen_to_original_decision(self):
        project, controller, registration, _ = self.setup_project()
        before = project.status()
        result = controller.advance_feedback(request_id="branch", registration_request_id=registration["request_id"],
                                             expected_state_version=before["state_version"])
        self.assertEqual(result["status"], "waiting")
        after = project.status()
        self.assertEqual(after["actions"], [])
        self.assertEqual(after["budget"], before["budget"])
        replay = ProjectController(project.root).advance_feedback(request_id="branch", registration_request_id=registration["request_id"],
                                                                 expected_state_version=before["state_version"])
        self.assertEqual(replay["status"], "waiting")
        self.assertEqual(project.status(), after)


if __name__ == "__main__":
    unittest.main()
