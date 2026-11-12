"""Bounded saved-selection and read-only route checks; no research dispatch."""

import copy
import http.client
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from autoresearch.contracts import ResearchError, fingerprint
from autoresearch import method_registry
from autoresearch.project_selection import seal_context
from autoresearch.research_recipe import compile_recipe
from autoresearch.project_selection_view import read_selection_request, selection_view
from autoresearch.project_workbench import create_project_server


class ProjectSelectionViewTests(unittest.TestCase):
    def context(self, version=1):
        return seal_context({
            "schema_version": "project-selection-context-v1", "project_id": "project-test", "run_id": "run-test",
            "snapshot_ref": "1" * 64, "state_version": version, "source_snapshot_sha256": "2" * 64,
            "project_code_identity": "3" * 64, "controller_code_identity": "4" * 64,
            "need": "next_check", "goal": "Check saved method choices.", "domain_scope": {}, "budget": {},
            "conditions": [], "blockers": [], "baseline_decision": {"next_action": {"kind": "evidence_task"}},
            "candidates": [{"id": "primary", "method_id": "materials.saved-steel-audit", "parameters": {},
                            "evaluation_ref": "materials-composition-holdout-v1"}],
            "evidence": [{"citation_id": key, "source": {"sha256": "5" * 64}, "quote": "Actual saved excerpt " + key,
                          "location": {"line": 1}} for key in ("cited", "uncited")], "scientific_validation": False,
        })

    def state(self, execute=False):
        context = self.context()
        proposal = {"schema_version": "project-selection-proposal-v1", "context_sha256": context["context_sha256"],
                    "provider": {"kind": "operator_assistant", "label": "Unverified declaration"},
                    "choice": {"kind": "execute", "candidate_id": "primary"} if execute else {"kind": "wait"},
                    "rationale": "Preserve the remaining source question.", "evidence_citation_ids": ["cited"]}
        request = {"project_id": "project-test", "command": "controller.advance_selection", "need": "next_check",
                   "expected_state_version": 1, "proposal": proposal}
        next_action = ({"kind": "conditional_proposal", "method_id": "materials.saved-steel-audit", "parameters": {},
                        "execution_status": "not_executed"} if execute else {"kind": "external_wait", "execution_status": "not_executed"})
        decision = {"next_action": next_action, "reason": proposal["rationale"], "scientific_validation": False}
        child_id = "controller-child-" + fingerprint({"project_id": "project-test", "request_id": "selection-1"})[:32]
        parent = {"schema_version": "project-controller-request-v1", "project_id": "project-test", "request_id": "selection-1",
                  "request": request, "request_sha256": fingerprint(request), "decision": decision,
                  "decision_sha256": fingerprint(decision), "selection_context": context,
                  "source_snapshot_sha256": "2" * 64, "snapshot_ref_before": "1" * 64, "state_version_before": 1,
                  "dispatch_state_version": 2, "code_identity": "3" * 64, "controller_code_identity": "4" * 64,
                  "blockers": [], "status": "prepared" if execute else "waiting", "result": None,
                  "child_request_id": child_id if execute else None}
        return {"id": "project-test", "run_id": "run-test", "snapshot_ref": "1" * 64, "state_version": 20,
                "code_identity": "3" * 64, "source_snapshot_sha256": "2" * 64, "source_scope": {},
                "registration": {"goal": "Check saved method choices.", "method_id": "materials.saved-steel-audit"},
                "actions": [], "evidence_actions": [], "evidence_sources": [], "controller_requests": [parent]}

    def test_projection_is_bounded_cited_only_and_excludes_fixed_parents(self):
        state = self.state()
        state["controller_requests"] += [{"request_id": "fixed", "request": {"command": "controller.advance"}}]
        view = selection_view(state)
        self.assertEqual(view["total"], 1)
        self.assertEqual([x["citation_id"] for x in view["records"][0]["evidence"]], ["cited"])
        self.assertFalse(view["records"][0]["model_execution_verified"])
        view["records"][0]["evidence"][0]["quote"] = "changed"
        self.assertNotEqual(state["controller_requests"][0]["selection_context"]["evidence"][0]["quote"], "changed")
        state["controller_requests"] = state["controller_requests"][1:]
        self.assertEqual(selection_view(state), {"schema_version": "project-selection-view-v1", "available": True,
                                                "records": [], "total": 0, "omitted": 0})

    def diagnostic_state(self, method="data.saved-oof-group-diagnostics"):
        """An immutable historical controller fixture; no estimator is executed."""
        state = self.state(execute=True); parent = state["controller_requests"][0]
        source_method = ("data.ridge-random-validation" if method_registry.DIAGNOSTICS[method].check == "random_cv"
                         else "data.ridge-group-validation")
        binding = {"project_id": state["id"], "version": 1, "source_snapshot_sha256": state["source_snapshot_sha256"],
                   "resource": {"id": "saved-diagnostic-fixture", "version": 1}, "prediction_column": None,
                   "training": {"feature_columns": ["x"], "split_group_columns": ["group"], "fit_limit": 10}}
        producer = {"id": "source-cv", "request_id": "source-validation", "status": "completed", "command": source_method,
                    "source_snapshot_sha256": state["source_snapshot_sha256"], "result_sha256": "6" * 64,
                    "design_binding": binding, "method_instance": {"evaluation_ref": method_registry.evaluation_ref(source_method)}}
        params = {"based_on_action_id": producer["id"], "based_on_result_sha256": producer["result_sha256"]}
        candidate = {"id": "diagnostic-choice", "method_id": method, "parameters": params,
                     "evaluation_ref": method_registry.evaluation_ref(method)}
        context = parent["selection_context"]
        context = seal_context({**{k: v for k, v in context.items() if k != "context_sha256"},
                                "domain_scope": {"domain": "data", "contract": "tabular-quality-v1"}, "candidates": [candidate]})
        parent["selection_context"] = context
        parent["request"]["proposal"].update(context_sha256=context["context_sha256"],
                                             choice={"kind": "execute", "candidate_id": candidate["id"]})
        parent["request_sha256"] = fingerprint(parent["request"])
        parent["decision"]["next_action"].update(method_id=method, parameters=params)
        parent["decision_sha256"] = fingerprint(parent["decision"])
        child_request = {"project_id": state["id"], "command": method, "dimension": None,
                         "source_snapshot_sha256": state["source_snapshot_sha256"], "parameters": params,
                         "evaluation_ref": candidate["evaluation_ref"], "design_binding": binding}
        child = {**child_request, "request_id": parent["child_request_id"], "request_sha256": fingerprint(child_request),
                 "id": "action-" + fingerprint({"request_id": parent["child_request_id"], **child_request})[:32],
                 "run_id": state["run_id"], "code_identity": parent["code_identity"], "status": "completed",
                 "artifact": "artifacts/saved-diagnostic.json", "result_sha256": "7" * 64, "failure": None,
                 "method_instance": {"definition_ref": {"id": method, "version": "1"}, "parameters": params,
                     "evaluation_ref": candidate["evaluation_ref"], "input_bindings": {**params, "design_revision": 1,
                        "resource_id": binding["resource"]["id"], "resource_version": 1, "prediction_column": None,
                        "training": binding["training"]}}}
        state["actions"] = [producer, child]
        # A later binding is legal; history verification must not consult only the current one.
        state["design_revisions"] = [binding, {**copy.deepcopy(binding), "version": 2}]
        parent.update(status="completed", result={"child": {key: child[key] for key in
                      ("id", "request_id", "command", "status", "artifact", "result_sha256", "failure")}})
        return state

    def test_diagnostic_selection_history_retains_frozen_binding_for_both_checks(self):
        for method in method_registry.DIAGNOSTICS:
            with self.subTest(method=method):
                state = self.diagnostic_state(method)
                record = selection_view(state)["records"][0]
                self.assertEqual(record["method_id"], method)
                self.assertEqual(read_selection_request(state, "selection-1"), state["controller_requests"][0])
                self.assertEqual(state["actions"][-1]["design_binding"]["version"], 1)

    def test_diagnostic_history_rejects_changed_frozen_binding_and_producer_identity(self):
        mutations = [
            lambda s: s["actions"][-1]["method_instance"]["input_bindings"].update(design_revision=2),
            lambda s: s["actions"][0].update(command="data.ridge-random-validation"),
            lambda s: s["actions"][0].update(status="failed"),
            lambda s: s["actions"][0].update(result_sha256="8" * 64),
            lambda s: s["actions"][0].update(source_snapshot_sha256="9" * 64),
            lambda s: s["actions"][0].update(design_binding=s["design_revisions"][-1]),
            lambda s: s["actions"][0]["method_instance"].update(evaluation_ref="wrong-cv"),
        ]
        for mutate in mutations:
            state = self.diagnostic_state(); mutate(state)
            with self.assertRaises(ResearchError) as caught:
                selection_view(state)
            self.assertEqual(caught.exception.code, "EVIDENCE_CHANGED")

    def test_download_preserves_original_hash_bound_parent(self):
        state = self.state()
        parent = read_selection_request(state, "selection-1")
        self.assertEqual(parent, state["controller_requests"][0])
        self.assertEqual(parent["request_sha256"], fingerprint(parent["request"]))
        parent["request"]["proposal"]["rationale"] = "changed"
        self.assertNotEqual(parent, state["controller_requests"][0])
        with self.assertRaises(ResearchError) as caught:
            read_selection_request(state, "missing")
        self.assertEqual(caught.exception.code, "ARTIFACT_NOT_FOUND")

    def test_recipe_parent_keeps_compilation_bound_to_original_context_and_proposal(self):
        original = self.state()
        self.assertNotIn("recipe_decision", selection_view(original)["records"][0])
        self.assertEqual(read_selection_request(original, "selection-1"), original["controller_requests"][0])
        recipe = {"schema_version": "research-recipe-v1", "id": "saved-choice-order", "version": 1,
                  "question": "Check the matching saved method without calling a model.",
                  "scope_match": {"domain": "materials", "contract": "steel-saved-evaluation-v1"},
                  "need": "next_check", "on_no_match": "wait",
                  "ordered_methods": [{"method_id": "research.source-selection", "evaluation_ref": "source-check-v1"},
                                      {"method_id": "materials.saved-steel-audit", "evaluation_ref": "materials-composition-holdout-v1"}]}
        for execute in (False, True):
            with self.subTest(execute=execute):
                state = self.state(execute=execute); parent = state["controller_requests"][0]
                context = parent["selection_context"]
                if execute:
                    context = seal_context({**{key: value for key, value in context.items() if key != "context_sha256"},
                                            "domain_scope": recipe["scope_match"]})
                    parent["selection_context"] = context
                compiled = compile_recipe(recipe, context)
                parent["request"].update(command="controller.advance_recipe", recipe_decision=compiled,
                                         proposal=copy.deepcopy(compiled["proposal"]))
                parent["decision"]["reason"] = compiled["proposal"]["rationale"]
                parent["decision"]["policy_ref"] = {"id": recipe["id"], "version": recipe["version"], "kind": "deterministic_recipe"}
                parent["decision"]["selection_ref"] = {"context_sha256": context["context_sha256"],
                    "candidate_id": compiled["selected_candidate_id"], "provider_claim": compiled["proposal"]["provider"],
                    "evidence_citation_ids": [], "provider_verified": False, "model_execution_verified": False,
                    "external_usage": "no_model_invocation_by_recipe_compiler"}
                parent["request_sha256"] = fingerprint(parent["request"])
                parent["decision_sha256"] = fingerprint(parent["decision"])
                record = selection_view(state)["records"][0]
                self.assertEqual(record["recipe_decision"], compiled)
                self.assertEqual(record["provider_claim"]["kind"], "operator_assistant")
                self.assertEqual(compiled["selected_candidate_id"], "primary" if execute else None)
                self.assertEqual(read_selection_request(state, "selection-1"), parent)
                record["recipe_decision"]["recipe"]["version"] = 9
                self.assertEqual(parent["request"]["recipe_decision"]["recipe"]["version"], 1)
                for mutate in (
                    lambda request: request["recipe_decision"]["recipe"].update(version=2),
                    lambda request: request["recipe_decision"].update(context_sha256="0" * 64),
                    lambda request: request["recipe_decision"]["method_decisions"][0].update(reason="invented"),
                    lambda request: request["proposal"]["provider"].update(label="changed policy"),
                ):
                    changed = copy.deepcopy(state); saved = changed["controller_requests"][0]
                    mutate(saved["request"]); saved["request_sha256"] = fingerprint(saved["request"])
                    with self.assertRaises(ResearchError) as caught:
                        selection_view(changed)
                    self.assertEqual(caught.exception.code, "EVIDENCE_CHANGED")
                for marker, value in (("policy_ref", {"id": "external-proposal", "version": "1"}),
                                      ("external_usage", "unknown_not_counted_as_zero")):
                    changed = copy.deepcopy(state); saved = changed["controller_requests"][0]
                    if marker == "policy_ref":
                        saved["decision"][marker] = value
                    else:
                        saved["decision"]["selection_ref"][marker] = value
                    saved["decision_sha256"] = fingerprint(saved["decision"])
                    with self.assertRaises(ResearchError) as caught:
                        selection_view(changed)
                    self.assertEqual(caught.exception.code, "EVIDENCE_CHANGED")

    def test_changed_bindings_and_existing_child_parameters_are_rejected(self):
        for mutate in (
            lambda p: p["request"].update(need="changed"),
            lambda p: p["decision"].update(reason="changed"),
            lambda p: p["selection_context"].update(run_id="another-run"),
        ):
            state = self.state(); mutate(state["controller_requests"][0])
            with self.assertRaises(ResearchError) as caught:
                selection_view(state)
            self.assertEqual(caught.exception.code, "EVIDENCE_CHANGED")
        state = self.state(execute=True); parent = state["controller_requests"][0]
        request = {"project_id": state["id"], "command": "materials.saved-steel-audit", "dimension": None,
                   "source_snapshot_sha256": state["source_snapshot_sha256"]}
        child = {**request, "request_id": parent["child_request_id"], "request_sha256": fingerprint(request),
                 "id": "action-" + fingerprint({"request_id": parent["child_request_id"], **request})[:32],
                 "run_id": state["run_id"], "code_identity": state["code_identity"], "status": "unknown",
                 "method_instance": {"definition_ref": {"id": request["command"]}, "parameters": {}}}
        state["actions"] = [child]
        self.assertEqual(selection_view(state)["total"], 1)
        child["method_instance"]["parameters"] = {"injected": True}
        with self.assertRaises(ResearchError) as caught:
            selection_view(state)
        self.assertEqual(caught.exception.code, "EVIDENCE_CHANGED")

    def test_http_context_download_staleness_and_read_only_boundary(self):
        state = self.state(); current = self.context(version=state["state_version"])
        state["evidence_sources"] = [{"receipt_snapshot_sha256": "6" * 64, "source_count": 1, "selection_count": 2}]
        class Project:
            root = Path(tempfile.gettempdir()) / "selection-view-fixture"
            def status(self): return copy.deepcopy(state)
        project = Project()
        with patch("autoresearch.project_workbench._binding", return_value=(project, None, state)), \
             patch("autoresearch.project_workbench.research_methods.match_methods", return_value=[]), \
             patch("autoresearch.project_workbench.ProjectController") as controller:
            controller.return_value.selection_context.return_value = current
            server = create_project_server(workspace="unused", port=0)
            thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
            def get(path, method="GET", host=None):
                connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=5)
                connection.request(method, path, headers={"Host": host} if host else {})
                response = connection.getresponse(); raw = response.read(); connection.close()
                return response.status, json.loads(raw)
            try:
                status, view = get("/api/project")
                self.assertEqual(status, 200); self.assertEqual(view["selection_history"]["total"], 1)
                self.assertEqual(view["registered_evidence"][0]["read_status"], "unread")
                status, downloaded = get("/api/project/selection-request/selection%2D1.json")
                self.assertEqual(status, 200); self.assertEqual(downloaded, state["controller_requests"][0])
                self.assertEqual(get("/api/project/selection-context.json?snapshot_ref=" + "1" * 64), (200, current))
                status, error = get("/api/project/selection-context.json?snapshot_ref=" + "0" * 64)
                self.assertEqual((status, error["code"]), (409, "STALE_STATE"))
                self.assertEqual(get("/api/project", method="POST")[0], 405)
                self.assertEqual(get("/api/project", host="example.com")[0], 403)
                state["controller_requests"][0]["request_sha256"] = "0" * 64
                status, error = get("/api/project")
                self.assertEqual((status, error["code"]), (500, "EVIDENCE_CHANGED"))
                controller.return_value.advance_selection.assert_not_called()
            finally:
                server.shutdown(); server.server_close(); thread.join(timeout=5)


if __name__ == "__main__":
    unittest.main()
