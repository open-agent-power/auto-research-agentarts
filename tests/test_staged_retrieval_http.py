"""Real loopback gates for a synthetic staged project; no model or research fit."""
import unittest

import test_local_workbench_http as http
import test_staged_retrieval_workbench as fixtures
from autoresearch import staged_relevance_adapter as staged, retrieval_holdout
from autoresearch.contracts import canonical
from autoresearch.local_workbench import LocalWorkbench
from autoresearch.project_controller import ProjectController


class StagedRetrievalHTTPTests(unittest.TestCase):
    setUp = fixtures.StagedRetrievalWorkbenchTests.setUp
    register_body = fixtures.StagedRetrievalWorkbenchTests.register_body
    execute = fixtures.StagedRetrievalWorkbenchTests.execute
    serve = http.LocalWorkbenchHTTPTests.serve
    request = http.LocalWorkbenchHTTPTests.request
    session = http.LocalWorkbenchHTTPTests.session

    def test_registered_private_input_freeze_and_final_share_original_http_budget(self):
        server = self.serve(local_workspace=self.manager, allow_local_actions=True)
        headers = self.session(server)
        body = self.register_body()
        status, _ = self.request(server, "/api/local-workbench/retrieval-holdout", "POST", body,
                                 {**headers, "Origin": "http://untrusted.invalid"})
        self.assertEqual(status, 403)
        self.assertNotIn("private_evaluation", self.project.status())
        status, registered = self.request(server, "/api/local-workbench/retrieval-holdout", "POST", body, headers)
        self.assertEqual(status, 200, registered)
        self.assertNotIn(self.secret_text, canonical(registered))
        self.assertNotIn(body["holdout_base64"], canonical(registered))
        self.assertNotIn(self.secret_text.encode(), self.manager.db.read_bytes())
        primary, _ = self.execute("primary", staged.TOOL_ID)
        self.assertEqual(primary["status"], "completed")
        action = self.project.status()["actions"][0]
        freeze = {"request_id": "freeze", "project_id": self.project_id,
                  "expected_state_version": self.project.status()["state_version"], "primary_action_id": action["id"]}
        status, frozen = self.request(server, "/api/local-workbench/retrieval-freeze", "POST", freeze, headers)
        self.assertEqual(status, 200, frozen)
        context = ProjectController(self.project.root).selection_context()
        self.assertEqual(context["staged_evaluation"]["freeze"]["selected_method"], "bm25")
        self.assertNotIn(self.secret_text, canonical(context))
        self.assertNotIn(self.secret_query_id, canonical(context))
        selected = next(row for row in context["candidates"] if row["method_id"] == retrieval_holdout.FINAL_TOOL_ID)
        final = {"request_id": "final", "project_id": self.project_id, "expected_state_version": context["state_version"],
                 "proposal": {"schema_version": "project-selection-proposal-v1", "context_sha256": context["context_sha256"],
                    "provider": {"kind": "operator_assistant", "label": "Synthetic HTTP only"},
                    "choice": {"kind": "execute", "candidate_id": selected["id"]},
                    "rationale": "Evaluate the original frozen synthetic strategy once", "evidence_citation_ids": []}}
        status, completed = self.request(server, "/api/local-workbench/advance", "POST", final, headers)
        self.assertEqual(status, 200, completed)
        self.assertEqual(completed["status"], "completed")
        state = self.project.status()
        self.assertTrue(LocalWorkbench(self.manager.root).advance(final)["replayed"])
        self.assertEqual(self.project.status(), state)
        self.assertEqual((state["budget"]["local_tool_calls_used"], state["budget"]["local_tool_call_limit"]), (2, 2))
        self.assertEqual((state["budget"]["new_fits"], state["budget"]["new_model_requests"]), (0, 0))


if __name__ == "__main__":
    unittest.main()
