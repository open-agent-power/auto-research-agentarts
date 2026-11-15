"""Read-only controller unknown projection; synthetic inputs and no external transport."""
import copy
import json
import unittest
from unittest.mock import patch

import test_local_workbench as fixture
import test_local_workbench_http as http
from autoresearch import research_project, tabular_quality_adapter as tabular
from autoresearch.contracts import ResearchError, fingerprint
from autoresearch.local_workbench import LocalWorkbench
from autoresearch.project_controller import ProjectController
from autoresearch.research_project import ResearchProject


class UnknownControllerProjectionTests(unittest.TestCase):
    setUp = fixture.LocalWorkbenchTests.setUp
    create_body = fixture.LocalWorkbenchTests.create_body
    proposal = fixture.LocalWorkbenchTests.proposal
    serve = http.LocalWorkbenchHTTPTests.serve
    request = http.LocalWorkbenchHTTPTests.request

    def unknown(self, *, complete_child=False):
        created = self.manager.create(self.create_body())
        project, _ = self.manager.binding()
        context = ProjectController(project.root).selection_context()
        body = {"request_id": "unknown-parent", "project_id": created["project_id"],
                "expected_state_version": context["state_version"],
                "proposal": self.proposal(context, tabular.TOOL_ID)}
        pending = []
        def interrupt(path, value):
            pending.append((path, value))
            raise KeyboardInterrupt("synthetic result publication interruption")
        with patch.object(research_project, "write_once", side_effect=interrupt):
            with self.assertRaises(KeyboardInterrupt):
                self.manager.advance(body)
        self.assertEqual(len(pending), 1)
        self.assertEqual(self.manager.advance(body)["status"], "unknown")
        parent = project.status()["controller_requests"][-1]
        if complete_child:
            research_project.write_once(*pending[0])
            with patch.object(tabular, "execute", side_effect=AssertionError("no additional compute")):
                self.assertEqual(project.step(request_id=parent["child_request_id"])["status"], "completed")
        return project, body

    def test_real_unknown_and_recovered_child_are_visible_without_mutation(self):
        project, body = self.unknown(complete_child=True)
        before, manager_before = project.db.read_bytes(), self.manager.db.read_bytes()
        state = project.status()
        old_wire = self.manager.describe()
        self.assertFalse(any(x["request_id"] == body["request_id"] for x in old_wire["pending_requests"]))
        with patch.object(ProjectController, "_dispatch", side_effect=AssertionError("no dispatch")), \
             patch.object(ResearchProject, "step", side_effect=AssertionError("no step")), \
             patch.object(ResearchProject, "resume", side_effect=AssertionError("no recovery")):
            result = self.manager.read_unknown_controller_requests(project_id=state["id"], snapshot_ref=state["snapshot_ref"])
        self.assertEqual((result["total"], result["shown"], result["truncated"]), (1, 1, False))
        item = result["items"][0]
        self.assertEqual((item["request_id"], item["status"], item["child_status"]),
                         (body["request_id"], "unknown", "completed"))
        self.assertFalse(result["recovery_verified"])
        self.assertFalse(result["request_body_included"])
        self.assertEqual(result["binding_scope"], "limited_state_fields_only_not_sql_or_artifacts")
        serialized = json.dumps(result)
        self.assertNotIn(body["proposal"]["rationale"], serialized)
        self.assertEqual(self.manager.describe(), old_wire)
        self.assertEqual((project.db.read_bytes(), self.manager.db.read_bytes()), (before, manager_before))
        self.assertEqual(project.status()["budget"], state["budget"])

    def test_http_exact_selectors_active_binding_and_readonly_host(self):
        project, body = self.unknown()
        state = project.status()
        server = self.serve(local_workspace=self.manager, allow_local_actions=True)
        path = "/api/local-workbench/unknown-controller-requests.json"
        query = "?project_id=" + state["id"] + "&snapshot_ref=" + state["snapshot_ref"]
        before = project.db.read_bytes(), self.manager.db.read_bytes()
        status, view = self.request(server, path + query)
        self.assertEqual((status, view["total"], view["items"][0]["request_id"]), (200, 1, body["request_id"]))
        self.assertEqual(self.request(server, path + query + "&project_id=duplicate")[0], 400)
        self.assertEqual(self.request(server, path + "?project_id=" + state["id"] + "&snapshot_ref=" + "0"*64)[0], 409)
        self.assertEqual((project.db.read_bytes(), self.manager.db.read_bytes()), before)
        other = self.manager.create(self.create_body("other-project"))
        self.assertNotEqual(other["project_id"], state["id"])
        self.assertEqual(self.request(server, path + query)[0], 409)
        readonly = self.serve(local_workspace=LocalWorkbench.open_readonly(self.manager.root), allow_local_actions=False)
        self.assertEqual(self.request(readonly, path + query)[0], 404)

    def test_malformed_parent_and_midread_snapshot_change_rejected(self):
        project, _ = self.unknown()
        state = project.status()
        corrupted = copy.deepcopy(state)
        corrupted["controller_requests"][-1]["request_sha256"] = "0" * 64
        with patch.object(ResearchProject, "status", return_value=corrupted):
            item = self.manager.read_unknown_controller_requests(project_id=state["id"], snapshot_ref=state["snapshot_ref"])["items"][0]
        self.assertEqual((item["request_id"], item["record_binding"], item["child_request_id"]), ("unknown-parent", "malformed", None))
        drift = copy.deepcopy(state)
        drift["controller_requests"][-1]["code_identity"] = "f" * 64
        with patch.object(ResearchProject, "status", return_value=drift):
            item = self.manager.read_unknown_controller_requests(project_id=state["id"], snapshot_ref=state["snapshot_ref"])["items"][0]
        self.assertEqual((item["identity_binding"], item["record_binding"]), ("mismatch", "limited_fields_match"))
        changed = copy.deepcopy(state)
        changed["snapshot_ref"] = "1" * 64
        with patch.object(ResearchProject, "status", side_effect=[state, changed]), self.assertRaises(ResearchError) as error:
            self.manager.read_unknown_controller_requests(project_id=state["id"], snapshot_ref=state["snapshot_ref"])
        self.assertEqual(error.exception.code, "STALE_STATE")

    def test_legacy_persisted_code_drift_does_not_hide_original_id(self):
        project, body = self.unknown(complete_child=True)
        before = project.status()
        original_core = before["controller_requests"][-1]["code_identity"]
        # Engineering-only stand-in for an old version having upgraded an
        # unknown-parent project; it is not a valid current upgrade operation.
        with project._writer(), project._connect() as con:
            saved = project._project(con)
            saved["code_identity"] = "f" * 64
            saved["state_version"] += 1
            project._save(con, saved)
        state = project.status()
        before_db = project.db.read_bytes(), self.manager.db.read_bytes()
        result = self.manager.read_unknown_controller_requests(project_id=state["id"], snapshot_ref=state["snapshot_ref"])
        item = result["items"][0]
        self.assertEqual((item["request_id"], item["identity_binding"], item["record_binding"]),
                         (body["request_id"], "mismatch", "limited_fields_match"))
        self.assertEqual((item["project_code_identity"], item["current_project_code_identity"]), (original_core, "f" * 64))
        self.assertFalse(result["recovery_verified"])
        self.assertEqual((project.db.read_bytes(), self.manager.db.read_bytes()), before_db)

    def test_limit_counts_all_unique_parent_records(self):
        project, _ = self.unknown()
        state = project.status()
        many = copy.deepcopy(state)
        original = many["controller_requests"][-1]
        source_child = many["actions"][-1]
        many["controller_requests"] = []
        many["actions"] = []
        for n in range(9):
            parent, child = copy.deepcopy(original), copy.deepcopy(source_child)
            parent["request_id"] = "example-" + str(n)
            child_id = "controller-child-" + fingerprint({"project_id": state["id"], "request_id": parent["request_id"]})[:32]
            parent["child_request_id"] = child_id
            parent["result"]["child"]["request_id"] = child_id
            child["request_id"] = child_id
            many["controller_requests"].append(parent)
            many["actions"].append(child)
        with patch.object(ResearchProject, "status", return_value=many):
            result = self.manager.read_unknown_controller_requests(project_id=state["id"], snapshot_ref=state["snapshot_ref"])
        self.assertEqual((result["total"], result["shown"], result["truncated"], len(result["items"])), (9, 8, True, 8))
        many["controller_requests"].append(copy.deepcopy(many["controller_requests"][0]))
        with patch.object(ResearchProject, "status", return_value=many):
            duplicate = self.manager.read_unknown_controller_requests(project_id=state["id"], snapshot_ref=state["snapshot_ref"])
        self.assertEqual((duplicate["total"], duplicate["observed_total"], duplicate["history_complete"]), (None, 9, False))
        self.assertEqual(duplicate["items"][0]["record_binding"], "malformed")


if __name__ == "__main__":
    unittest.main()
