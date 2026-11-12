"""Explicit saved-result diagnostics reuse native accounting and recovery."""
from contextlib import ExitStack
import copy
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from sklearn.linear_model import Ridge
from sklearn.preprocessing import StandardScaler

import test_group_only_design as fixtures
from autoresearch import method_registry as registry, research_methods, source_evidence_adapter
from autoresearch.contracts import ResearchError
from autoresearch.project_controller import ProjectController, _compact_decision
from autoresearch.project_design import bind
from autoresearch.project_selection import CONDITION_PROJECTION_FIELDS
from autoresearch.research_design import _records
from autoresearch.research_project import ResearchProject

RANDOM = "data.saved-oof-random-diagnostics"
GROUP = "data.saved-oof-group-diagnostics"


class NativeOOFDiagnosticTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Shared setup only: 5-fold random + 3-fold group = 8 Scaler + 8 Ridge fits.
        cls.fixture = fixtures.GroupOnlyDesignTests()
        cls.addClassCleanup(cls.fixture.doCleanups)
        project, controller = cls.fixture.project(checks=("random_cv", "group_cv", "negative_control"),
                                                  fit_limit=16, groups=3)
        project.limit_evidence_budget(request_id="no-source-budget", expected_limit=8, new_limit=0,
                                     expected_state_version=project.status()["state_version"], reason="No source execution in this fixture.")
        cls.snapshots = Path(cls.fixture.enterContext(tempfile.TemporaryDirectory()))
        shutil.copytree(project.root, cls.snapshots / "quality_test")
        controller.advance(request_id="random-cv")
        controller.advance(request_id="group-cv")
        cls.base = project
        cls.original_actions = copy.deepcopy(project.status()["actions"])
        cls.random = next(a for a in cls.original_actions if a["command"] == "data.ridge-random-validation")
        cls.group = next(a for a in cls.original_actions if a["command"] == "data.ridge-group-validation")

    def setUp(self):
        temporary = tempfile.TemporaryDirectory(); self.addCleanup(temporary.cleanup)
        self.copy_root = Path(temporary.name)
        shutil.copytree(self.base.root, self.copy_root / "project_test")
        self.project = ResearchProject(self.copy_root / "project_test")
        self.controller = ProjectController(self.project.root)
        self.guard = self.enterContext(ExitStack())
        self.guard.enter_context(patch.object(Ridge, "fit", side_effect=AssertionError("Diagnostics cannot fit Ridge")))
        self.guard.enter_context(patch.object(StandardScaler, "fit", side_effect=AssertionError("Diagnostics cannot fit Scaler")))
        self.guard.enter_context(patch.object(source_evidence_adapter, "execute", side_effect=AssertionError("Diagnostics cannot read sources")))

    @staticmethod
    def params(action):
        return {"based_on_action_id": action["id"], "based_on_result_sha256": action["result_sha256"]}

    def execute(self, method=GROUP, source=None, request_id="diagnostic"):
        return self.project.step(request_id=request_id, method_id=method,
                                 parameters=self.params(source or self.group))

    def test_candidates_bind_distinct_original_check_and_zero_fit_source_cost(self):
        context = self.controller.selection_context()
        candidates = {c["method_id"]: c for c in context["candidates"]}
        self.assertEqual(candidates[RANDOM]["parameters"], self.params(self.random))
        self.assertEqual(candidates[GROUP]["parameters"], self.params(self.group))
        self.assertNotIn(RANDOM, registry.DESIGN_METHODS)
        self.assertNotIn(GROUP, registry.RIDGE)
        for condition in context["conditions"]:
            if condition["method_id"] in registry.DIAGNOSTICS:
                self.assertEqual(condition["budget_cost"], {"local_tool_calls": 1, "estimator_fits": 0, "evidence_reads": 0})
        self.assertEqual(self.controller.next()["decision"]["next_action"]["method_id"], "data.prediction-negative-control")

    def test_missing_producer_has_no_candidate_or_dispatch(self):
        root = self.copy_root / "quality_only_test"
        shutil.copytree(self.snapshots / "quality_test", root)
        project = ResearchProject(root); before = project.status()
        self.assertFalse({RANDOM, GROUP}.intersection(c["method_id"] for c in ProjectController(root).selection_context()["candidates"]))
        with self.assertRaises(ResearchError):
            project.step(request_id="missing-producer", method_id=GROUP, parameters=self.params(before["actions"][0]))
        self.assertEqual(project.status(), before)

    def test_completed_but_noncomputable_cv_is_not_a_diagnostic_candidate(self):
        state = copy.deepcopy(self.project.status())
        action = next(a for a in state["actions"] if a["id"] == self.group["id"])
        action["observations"][0]["summary"].update(status="not_computable", reason="reference_mae_zero",
                                                   reference_mae=0, improvement=None)
        option = next(o for o in research_methods.match_methods(state) if o["method_id"] == GROUP)
        self.assertEqual(option["condition"], "not_applicable")
        self.assertTrue(option["missing_information"])

    def test_complete_native_result_retains_source_all_rows_folds_groups(self):
        before = self.project.status(); result = self.execute()
        action = self.project.status()["actions"][-1]
        tool = json.loads(self.project._artifact(action).read_bytes())["tool_result"]
        diagnostic, observation = tool["result"]["diagnostic"], tool["observations"][0]
        self.assertNotIn("analysis", tool["result"])
        self.assertEqual(observation["kind"], "saved_oof_diagnostic")
        self.assertEqual(observation["source_check"], "group_cv")
        self.assertEqual(observation["group_columns"], ["group"])
        self.assertEqual(observation["source_ref"]["action_id"], self.group["id"])
        self.assertEqual(observation["source_ref"]["result_sha256"], self.group["result_sha256"])
        self.assertEqual(observation["source_ref"]["producer_code_identity"], self.group["code_identity"])
        self.assertEqual((len(diagnostic["rows"]), len(diagnostic["folds"]), len(diagnostic["groups"])), (12, 3, 3))
        self.assertEqual(len(observation["group_errors"]), 3)
        self.assertEqual(len(observation["fold_errors"]), 3)
        self.assertFalse(any("logical_records" in g for g in observation["group_errors"]))
        self.assertEqual(sum(observation["row_error_counts"][key] for key in ("improved_rows", "worsened_rows", "tied_rows")), 12)
        self.assertEqual(sum(observation["group_error_counts"][key] for key in ("improved_groups", "worsened_groups", "tied_groups")), 3)
        self.assertEqual(action["design_binding"], self.group["design_binding"])
        self.assertEqual(action["method_instance"]["input_bindings"]["design_revision"], self.group["design_binding"]["version"])
        self.assertEqual(tool["new_fits"], 0); self.assertEqual(tool["model_calls"], 0)
        self.assertIs(tool["scientific_validation"], False)
        after = self.project.status()
        self.assertEqual(after["actions"][:-1], before["actions"])
        self.assertEqual(after["budget"]["fit_attempts_used"], 16)
        self.assertEqual(after["budget"]["evidence_reads_used"], 0)
        self.assertEqual(after["budget"]["local_tool_calls_used"], before["budget"]["local_tool_calls_used"] + 1)

    def test_random_diagnostic_uses_random_oof_without_changing_group_result(self):
        self.execute(RANDOM, self.random)
        action = self.project.status()["actions"][-1]
        observation = action["observations"][0]
        self.assertEqual(observation["source_check"], "random_cv")
        self.assertEqual(observation["source_ref"]["action_id"], self.random["id"])
        self.assertEqual(len(observation["fold_errors"]), 5)
        self.assertEqual(len(observation["group_errors"]), 3)
        self.assertTrue(any(len(group["folds"]) > 1 for group in observation["group_errors"]))

    def test_wrong_quality_or_other_check_source_is_rejected_before_action(self):
        before = self.project.status()
        for source in (before["actions"][0], self.random):
            with self.assertRaises(ResearchError):
                self.execute(source=source)
            self.assertEqual(self.project.status(), before)

    def test_changed_source_sha_is_rejected_without_accounting(self):
        before = self.project.status(); parameters = self.params(self.group); parameters["based_on_result_sha256"] = "f" * 64
        with self.assertRaises(ResearchError):
            self.project.step(request_id="wrong-sha", method_id=GROUP, parameters=parameters)
        self.assertEqual(self.project.status(), before)

    def test_corrupted_original_artifact_is_rejected_before_new_action(self):
        path = self.project._artifact(self.group); path.write_bytes(path.read_bytes().replace(b'"computed"', b'"invented"', 1))
        before = self.project.status()
        with self.assertRaises(ResearchError) as error:
            self.execute()
        self.assertEqual(error.exception.code, "EVIDENCE_CHANGED")
        self.assertEqual(self.project.status(), before)

    def test_original_and_equivalent_request_replay_reuse_exact_result(self):
        first = self.execute(); before = self.project.status()
        with patch.object(registry.DIAGNOSTICS[GROUP], "execute", side_effect=AssertionError("Replay cannot derive again")):
            self.assertTrue(self.execute()["replayed"])
            reused = self.execute(request_id="equivalent-id")
            self.assertTrue(reused["reused"])
            self.assertEqual(reused["id"], first["id"])
        self.assertEqual(self.project.status(), before)

    def test_rebind_blocks_old_source_new_id_but_preserves_original_replay(self):
        self.execute(); state = self.project.status()
        binding = state["design_revisions"][-1]
        resource = copy.deepcopy(binding["resource"])
        resource.update(version=2, parent_version=1, change_reason="A distinct test binding without a new fit")
        bind(self.project, request_id="rebind", expected_state_version=state["state_version"], resource=resource,
             prediction_column=None, training=binding["training"], reason="Do not reuse a previous design as the current diagnostic.")
        before = self.project.status()
        with patch.object(registry.DIAGNOSTICS[GROUP], "execute", side_effect=AssertionError("No execution on stale source")):
            self.assertTrue(self.execute()["replayed"])
            with self.assertRaises(ResearchError): self.execute(request_id="new-id-stale-source")
        self.assertEqual(self.project.status(), before)

    def test_unknown_without_saved_result_is_not_reexecuted(self):
        with patch.object(registry.DIAGNOSTICS[GROUP], "execute", side_effect=KeyboardInterrupt("Interrupt native diagnostic")):
            with self.assertRaises(KeyboardInterrupt): self.execute()
        self.assertEqual(self.project.resume(request_id="diagnostic")["status"], "unknown")
        before = self.project.status()
        self.assertEqual(before["budget"]["fits_reserved"], 0)
        self.assertEqual(before["budget"]["local_tool_calls_reserved"], 1)
        with patch.object(registry.DIAGNOSTICS[GROUP], "execute", side_effect=AssertionError("Unknown cannot retry")):
            self.assertEqual(self.project.resume(request_id="diagnostic")["status"], "unknown")
            self.assertEqual(self.controller.selection_context()["candidates"], [])
        self.assertEqual(self.project.status(), before)

    def test_saved_result_is_committed_on_resume_without_rederivation(self):
        with patch.object(self.project, "_commit_result", side_effect=RuntimeError("Observer stops before commit")):
            with self.assertRaises(RuntimeError): self.execute()
        with patch.object(registry.DIAGNOSTICS[GROUP], "execute", side_effect=AssertionError("Saved artifact cannot be recomputed")):
            result = self.project.resume(request_id="diagnostic")
        self.assertTrue(result["recovered"]); self.assertEqual(result["status"], "completed")
        self.assertEqual(self.project.status()["budget"]["fit_attempts_used"], 16)

    def test_controller_parent_replay_and_cv_catalog_remain_distinct(self):
        context = self.controller.selection_context(); candidate = next(c for c in context["candidates"] if c["method_id"] == GROUP)
        proposal = {"schema_version": "project-selection-proposal-v1", "context_sha256": context["context_sha256"],
                    "provider": {"kind": "operator_assistant", "label": "native diagnostic fixture"},
                    "choice": {"kind": "execute", "candidate_id": candidate["id"]}, "rationale": "Inspect the explicit saved group result.", "evidence_citation_ids": []}
        self.controller.advance_selection(request_id="parent-diagnostic", proposal=proposal)
        before = self.project.status()
        with patch.object(registry.DIAGNOSTICS[GROUP], "execute", side_effect=AssertionError("Parent cannot derive twice")):
            self.assertTrue(self.controller.advance_selection(request_id="parent-diagnostic", proposal=proposal)["replayed"])
        self.assertEqual(self.project.status(), before)
        self.assertEqual(sorted(record["check"] for record in _records(self.project, before)), ["group_cv", "random_cv"])

    def test_identical_baseline_conditions_are_referenced_and_reconstructable(self):
        context = self.controller.selection_context(); baseline = context["baseline_decision"]
        self.assertNotIn("conditions", baseline)
        ref = baseline["conditions_ref"]
        self.assertEqual(ref, {"kind": "provided_selection_context_field", "path": ["conditions"], "fields": list(CONDITION_PROJECTION_FIELDS)})
        expected = [{k: copy.deepcopy(o[k]) for k in CONDITION_PROJECTION_FIELDS if k in o} for o in context["conditions"]]
        original = self.controller._base_plan(self.project.status(), "next_check", include_knowledge=True)["decision"]
        self.assertEqual(expected, _compact_decision(original)["conditions"])

    def test_distinct_recipe_condition_outcome_or_order_is_preserved(self):
        state = self.project.status(); base = self.controller._base_plan(state, "next_check", include_knowledge=True)
        for kind in ("outcome", "order"):
            changed = copy.deepcopy(base)
            if kind == "outcome":
                changed["decision"]["conditions"][0]["outcome"] = "recipe-specific-condition"
            else:
                changed["decision"]["conditions"] = list(reversed(changed["decision"]["conditions"]))
            context = self.controller._selection_context(state, "next_check", base_plan=changed)
            self.assertIn("conditions", context["baseline_decision"])
            self.assertNotIn("conditions_ref", context["baseline_decision"])
