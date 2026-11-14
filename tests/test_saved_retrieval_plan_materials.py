"""Hand-authored saved retrieval records; no reranking, scoring, fits or model calls."""
import copy
import json
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import test_saved_retrieval_reader as reader_fixture
import test_project_selection_view as selection_fixture
from autoresearch import host_model_report, method_registry, plan_feedback, recipe_change_proposal
from autoresearch import research_plan_proposal as plan, saved_materials
from autoresearch.contracts import ResearchError, canonical, fingerprint
from autoresearch.project_selection import seal_context


class SavedRetrievalPlanMaterialTests(unittest.TestCase):
    def setUp(self):
        fixture = reader_fixture.SavedRetrievalReaderTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.fixture, self.state = fixture, fixture.state
        self._bind(fixture.primary)
        fixture.audit_result["predecessor"] = {"based_on_action_id": fixture.primary["id"],
                                              "based_on_result_sha256": fixture.primary["result_sha256"]}
        fixture.envelopes[fixture.audit["id"]]["tool_result"]["result"]["predecessor"] = copy.deepcopy(fixture.audit_result["predecessor"])
        self._bind(fixture.audit, fixture.primary)
        self.project = SimpleNamespace(root=fixture.project.root, status=lambda: copy.deepcopy(self.state))
        self.state["design_revisions"] = []
        self.state["next_decision"] = None
        self.state["actions"] = [fixture.primary, fixture.audit]
        context = selection_fixture.ProjectSelectionViewTests().context()
        payload = {k: copy.deepcopy(v) for k, v in context.items() if k != "context_sha256"}
        payload.update(project_id=self.state["id"], run_id=self.state["run_id"], snapshot_ref=self.state["snapshot_ref"],
                       state_version=self.state["state_version"], source_snapshot_sha256=self.state["source_snapshot_sha256"],
                       domain_scope=copy.deepcopy(self.state["source_scope"]), candidates=[], conditions=[], evidence=[])
        self.selection = seal_context(payload)
        self.selector = {"kind": "retrieval_adverse_query", "action_id": fixture.audit["id"],
                         "result_sha256": fixture.audit["result_sha256"], "split": "validation", "query_id": "qv"}
        for name in ("build_index", "retrieve", "metrics"):
            self.enterContext(patch("autoresearch.retrieval_lexical." + name, side_effect=AssertionError("No ranking or scoring")))
        for module in ("retrieval_adapter", "relevance_retrieval_adapter"):
            self.enterContext(patch("autoresearch." + module + ".execute", side_effect=AssertionError("No research execution")))
            self.enterContext(patch("autoresearch." + module + ".AUDIT.execute_saved", side_effect=AssertionError("No audit execution")))
        for target in ("sklearn.linear_model.Ridge.fit", "sklearn.preprocessing.StandardScaler.fit",
                       "autoresearch.project_local_model.ProjectLocalModel.send",
                       "autoresearch.host_model_selection.HostModelSelection.request", "subprocess.Popen"):
            self.enterContext(patch(target, side_effect=AssertionError("No fit, model or CLI")))
        self.enterContext(patch("socket.socket", side_effect=AssertionError("No network")))

    def _bind(self, action, predecessor=None):
        old = action["id"]
        envelope = self.fixture.envelopes.pop(old)
        method = action["command"]
        request = {"project_id": self.state["id"], "command": method, "dimension": None,
                   "source_snapshot_sha256": self.state["source_snapshot_sha256"]}
        parameters = {}
        if predecessor:
            parameters = {"based_on_action_id": predecessor["id"], "based_on_result_sha256": predecessor["result_sha256"]}
            request.update(parameters=parameters, evaluation_ref=method_registry.evaluation_ref(method))
        action.update(request, id="action-" + fingerprint({"request_id": action["request_id"], **request})[:32],
                      request_sha256=fingerprint(request), method_instance={
                          "definition_ref": {"id": method, "version": "1"},
                          "input_bindings": {"source_snapshot_sha256": self.state["source_snapshot_sha256"], **parameters},
                          "parameters": parameters, "evaluation_ref": method_registry.evaluation_ref(method),
                          "scope": copy.deepcopy(self.state["source_scope"])})
        action["artifact"] = "artifacts/" + action["id"] + ".json"
        envelope.update(action_id=action["id"], request_sha256=action["request_sha256"])
        self.fixture.envelopes[action["id"]] = envelope
        self.fixture.seal(action)

    def context(self, selectors=None):
        with patch.object(plan.ProjectController, "selection_context", return_value=self.selection):
            return plan.build_context(self.project, saved_materials=selectors)

    def test_explicit_empty_rankings_and_positive_label_reach_plan_without_text(self):
        context = self.context([self.selector])
        material, = context["supplied_materials"]
        self.assertEqual(context["schema_version"], "research-plan-context-v3")
        self.assertEqual(material["query"]["id"], "qv")
        self.assertEqual(material["binding"]["primary_result_sha256"], self.fixture.primary["result_sha256"])
        self.assertEqual([arm["ranking"] for arm in material["arms"]], [[], []])
        self.assertEqual([arm["qrel"]["doc_ids"] for arm in material["arms"]], [["b"], ["b"]])
        self.assertEqual([arm["qrel"]["role"] for arm in material["arms"]], ["train_qrels", "train_qrels"])
        self.assertTrue(all(all(value == 0 for value in arm["metrics"].values()) for arm in material["arms"]))
        self.assertFalse(material["source_text_included"])
        self.assertNotIn("unknown token", canonical(context))
        self.assertNotIn("<script>", canonical(context))
        self.assertIn("Query and document original text is not supplied", plan_feedback.projection_notice(context))
        self.assertEqual(saved_materials.validate_supplied(copy.deepcopy(context)), context)
        summary, = host_model_report.supplied_material_summaries({"context": context})
        self.assertEqual(summary["query"]["id"], "qv")
        self.assertNotIn("arms", summary)

    def test_default_old_context_has_no_query_or_new_notice(self):
        context = self.context()
        self.assertEqual(context["schema_version"], "research-plan-context-v2")
        self.assertNotIn("supplied_materials", context)
        self.assertNotIn("Explicitly selected retrieval", plan_feedback.projection_notice(context))

    def test_bad_selectors_duplicate_bound_and_absent_query_fail(self):
        for request in ({**self.selector, "result_sha256": "f" * 64},
                        {**self.selector, "query_id": "qn", "split": "dev"},
                        {**self.selector, "split": "missing"}, {**self.selector, "path": "/tmp/anything"}):
            with self.subTest(request=request), self.assertRaises(ResearchError):
                self.context([request])
        with self.assertRaises(ResearchError):
            self.context([self.selector, self.selector])
        with self.assertRaises(ResearchError):
            saved_materials.normalize_requests([{**self.selector, "query_id": f"q{i}"} for i in range(5)])

    def test_distinct_queries_from_the_same_primary_can_be_selected(self):
        primary = {**self.selector, "action_id": self.fixture.primary["id"],
                   "result_sha256": self.fixture.primary["result_sha256"]}
        materials = self.context([primary, {**primary, "query_id": "qd", "split": "dev"}])["supplied_materials"]
        self.assertEqual([m["query"]["id"] for m in materials], ["qv", "qd"])

    def test_changed_audit_primary_binding_and_bytes_fail_closed(self):
        original = copy.deepcopy(self.fixture.audit)
        for field, value in (("parameters", {"based_on_action_id": "wrong", "based_on_result_sha256": "a" * 64}),
                             ("request_sha256", "a" * 64), ("run_id", "wrong")):
            self.fixture.audit[field] = value
            with self.subTest(field=field), self.assertRaises(ResearchError):
                self.context([self.selector])
            self.fixture.audit.clear(); self.fixture.audit.update(copy.deepcopy(original))
        path = self.project.root / self.fixture.primary["artifact"]
        path.write_bytes(path.read_bytes() + b" ")
        # Whitespace is permitted in the JSON artifact; corrupt an actual value instead.
        data = json.loads(path.read_bytes()); data["code_identity"] = "e" * 64
        path.write_text(canonical(data))
        with self.assertRaises(ResearchError):
            self.context([self.selector])

    def test_context_tamper_size_and_recipe_rejection(self):
        context = self.context([self.selector])
        changed = copy.deepcopy(context); changed["supplied_materials"][0]["source_text_included"] = True
        with self.assertRaises(ResearchError):
            saved_materials.validate_supplied(changed)
        changed = copy.deepcopy(context)
        changed["selection_context"]["domain_scope"]["input_identities"]["train_qrels"]["sha256"] = None
        for arm in changed["supplied_materials"][0]["arms"]:
            arm["qrel"]["source_sha256"] = None
        with self.assertRaises(ResearchError):
            saved_materials.validate_supplied(changed)
        changed = copy.deepcopy(context); changed["supplied_materials"][0]["category"] = "metric_loss"
        with self.assertRaises(ResearchError):
            saved_materials.validate_supplied(changed)
        changed = copy.deepcopy(context); changed["supplied_materials"][0]["padding"] = "x" * 70000
        with self.assertRaises(ResearchError) as caught:
            plan._context(changed)
        self.assertIn("limit", str(caught.exception).lower())
        with patch.object(recipe_change_proposal.research_recipe, "validate_recipe", return_value={}), self.assertRaises(ResearchError):
            recipe_change_proposal.build_context(self.project, {}, "Fixture only", saved_materials=[self.selector])


if __name__ == "__main__":
    unittest.main()
