"""Explicit recipe adoption uses original Host receipts and preserves tool evidence."""

import copy
from unittest import TestCase
from unittest.mock import patch

import test_local_evidence as evidence_fixtures
import test_local_workbench as workbench_fixtures
import test_recipe_improvement_adapter as adapter_fixtures
from autoresearch import recipe_improvement_adapter as adapter
from autoresearch.contracts import ResearchError
from autoresearch.host_model_selection import HostModelSelection
from autoresearch.project_controller import ProjectController
from autoresearch.project_selection_view import selection_view
from autoresearch.research_project import ResearchProject


SOURCE = "research.source-selection"
GROUPED = "data.grouped-quality-profile"


class ProjectRecipeTests(TestCase):
    def setUp(self):
        self.fixture = adapter_fixtures.RecipeImprovementAdapterTests()
        self.addCleanup(self.fixture.doCleanups)
        self.fixture.setUp()
        self.fixture.options["decision_limit"] = 2
        self.project = self.fixture.project
        registration = self.fixture.manager.register_evidence(evidence_fixtures.LocalEvidenceTests.body(self.fixture))
        self.receipt = registration["registration"]["receipt_snapshot_sha256"]
        self.round_input = self.round_for(SOURCE, "source-round")

    def round_for(self, method_id, round_id):
        candidate = self.fixture.propose(method_id)
        request_id = self.fixture.options["request_id"]
        validation = adapter.validate_recipe_change(candidate, self.fixture.original, self.fixture.goal,
            workspace=self.project.root, request_id=request_id, allowed_methods=[method_id],
            allowed_receipts=[self.receipt] if method_id == SOURCE else [])
        record = HostModelSelection(self.project.root).status(request_id=request_id)
        proposal = adapter.propose_recipe_change(self.fixture.original, self.fixture.trace, self.fixture.goal,
                                                **self.fixture.options)
        selected = next(item for item in record["context"]["research_context"]["selection_context"]["conditions"]
                        if item["method_id"] == method_id)
        return {"schema_version": "recipe-improvement-input-v1", "round_id": round_id,
                "request_id": request_id, "evidence_kind": "saved_host_validation",
                "current_recipe": copy.deepcopy(self.fixture.original), "trace": copy.deepcopy(self.fixture.trace),
                "goal": self.fixture.goal, "issue": {"summary": "The fixture recipe omits an available follow-up.",
                    "feedback_action_ids": candidate["feedback_action_ids"]},
                "acceptance": {key: selected[key] for key in ("method_id", "evaluation_ref")},
                "proposal_result": proposal, "validation_result": validation, "previous_round": None,
                "next_question": "Read the effective version before choosing another fixture check."}

    def command(self, request_id="apply-recipe"):
        return {"request_id": request_id, "expected_state_version": self.project.status()["state_version"],
                "round_input": copy.deepcopy(self.round_input), "reason": "Use the recorded bounded improvement decision."}

    def assert_code(self, code, callback, *args, **kwargs):
        with self.assertRaises(ResearchError) as caught:
            callback(*args, **kwargs)
        self.assertEqual(caught.exception.code, code)

    def test_adoption_interruption_replays_and_default_uses_frozen_effective_recipe(self):
        before = self.project.status()
        command = self.command()
        with patch.object(ResearchProject, "_save", side_effect=KeyboardInterrupt("After recipe artifact publication")):
            with self.assertRaises(KeyboardInterrupt):
                self.project.apply_recipe_round(**command)
        self.assertEqual(self.project.status(), before)
        revision = self.project.apply_recipe_round(**command)
        after = self.project.status()
        self.assertEqual(revision["recipe"]["version"], 2)
        self.assertEqual(after["state_version"], before["state_version"] + 1)
        for key in ("budget", "actions", "evidence_actions", "next_decision", "code_identity"):
            self.assertEqual(after[key], before[key])
        self.assertEqual(ResearchProject(self.project.root).apply_recipe_round(**command), revision)
        self.assertEqual(self.project.status(), after)
        self.assert_code("IDEMPOTENCY_CONFLICT", self.project.apply_recipe_round, **{**command, "reason": "Changed reason"})
        controller = ProjectController(self.project.root)
        context = controller.selection_context()
        self.assertEqual(context["baseline_decision"]["policy_ref"]["kind"], "effective_recipe")
        self.assertEqual(context["baseline_decision"]["policy_ref"]["version"], 2)
        self.assertTrue(any(item["method_id"] == GROUPED for item in context["candidates"]))
        self.assertFalse(controller.next()["executable"])
        waiting = controller.advance(request_id="effective-wait")
        self.assertEqual(waiting["status"], "waiting")
        self.assertEqual(waiting["recipe_decision"]["recipe"], revision["recipe"])
        with patch("autoresearch.project_controller.current_recipe", return_value=self.fixture.original):
            replay = controller.advance(request_id="effective-wait")
        self.assertTrue(replay["replayed"])
        self.assertEqual(replay["recipe_decision"], waiting["recipe_decision"])
        context = controller.selection_context()
        proposal = workbench_fixtures.LocalWorkbenchTests.proposal(self.fixture, context, GROUPED)
        explicit = controller.advance_selection(request_id="explicit-group", proposal=proposal,
                                                 expected_state_version=context["state_version"])
        self.assertEqual(explicit["status"], "completed")
        self.assertTrue(selection_view(self.project.status())["available"])
        self.assertEqual(controller.advance(request_id="fixture-quality")["status"], "completed")

    def test_default_advance_rejects_revision_changed_before_parent_acceptance(self):
        self.project.apply_recipe_round(**self.command())
        older = self.project.status()
        # Seed the newer committed state at this controller boundary without another Host request.
        with self.project._writer(), self.project._connect() as con:
            newer = self.project._project(con)
            revision = copy.deepcopy(newer["recipe_revisions"][-1])
            revision["revision"] += 1
            revision["recipe"]["version"] += 1
            revision["recipe"]["ordered_methods"] = [{"method_id": GROUPED,
                                                       "evaluation_ref": "grouped-quality-profile-v1"}]
            newer["recipe_revisions"].append(revision)
            newer["state_version"] += 1
            self.project._save(con, newer)
        before = self.project.status()
        controller = ProjectController(self.project.root)
        original_status = controller.project.status
        reads = 0

        def status():
            nonlocal reads
            reads += 1
            return copy.deepcopy(older) if reads == 1 else original_status()

        with patch.object(controller.project, "status", side_effect=status):
            self.assert_code("STALE_RECIPE", controller.advance, request_id="racing-default")
        self.assertGreater(reads, 1)
        self.assertEqual(self.project.status(), before)

    def test_preview_is_read_only_and_rejects_detached_evidence_and_write_blockers(self):
        before = self.project.status()
        files = {path: path.read_bytes() for path in self.project.root.rglob("*") if path.is_file()}
        preview = self.project.preview_recipe_round(self.round_input)
        self.assertEqual((preview["status"], preview["decision"]), ("completed", "keep"))
        self.assertEqual(self.project.status(), before)
        self.assertEqual({path: path.read_bytes() for path in files}, files)
        changed = copy.deepcopy(self.round_input)
        changed["validation_result"]["artifact_refs"].append("artifacts/fabricated.json")
        self.assert_code("EVIDENCE_CHANGED", self.project.preview_recipe_round, changed)
        changed = copy.deepcopy(self.round_input)
        changed["evidence_kind"] = "synthetic_engineering_fixture"
        self.assert_code("INVALID_IMPROVEMENT_ROUND", self.project.preview_recipe_round, changed)
        command = self.command()
        self.assert_code("STALE_STATE", self.project.apply_recipe_round,
                         **{**command, "expected_state_version": before["state_version"] + 1})
        with patch("autoresearch.research_project.code_identity", return_value="f" * 64):
            self.assertEqual(self.project.preview_recipe_round(self.round_input), preview)
            self.assert_code("CODE_CHANGED", self.project.apply_recipe_round, **command)
        journal = HostModelSelection(self.project.root)
        with journal._writer():
            state = journal._load()
            state["requests"][self.round_input["request_id"]]["status"] = "unknown"
            journal._save(state)
        self.assert_code("HOST_SELECTION_PENDING", self.project.apply_recipe_round, **command)
        self.assertEqual(self.project.status(), before)

    def test_explicit_revert_records_original_recipe_without_undoing_validation(self):
        changed = copy.deepcopy(self.round_input)
        target = next(item for item in changed["trace"]["selection_context"]["conditions"] if item["method_id"] == GROUPED)
        changed["acceptance"] = {key: target[key] for key in ("method_id", "evaluation_ref")}
        before = self.project.status()
        revision = self.project.apply_recipe_round(**{**self.command(), "round_input": changed})
        self.assertEqual(revision["decision"], "revert")
        self.assertEqual(revision["recipe"], self.fixture.original)
        after = self.project.status()
        self.assertEqual(after["actions"], before["actions"])
        self.assertEqual(after["evidence_actions"], before["evidence_actions"])
        self.assertEqual(after["budget"], before["budget"])
        self.assert_code("RECIPE_ROUND_ALREADY_APPLIED", self.project.apply_recipe_round,
                         **{**self.command("duplicate-apply"), "round_input": changed})

    def test_round_from_old_base_cannot_replace_already_adopted_recipe(self):
        self.fixture.options["request_id"] = "second-saved-model"
        stale = self.round_for(GROUPED, "group-round")
        revision = self.project.apply_recipe_round(**self.command())
        self.assertEqual(revision["recipe"]["version"], 2)
        self.assert_code("STALE_RECIPE", self.project.apply_recipe_round,
                         **{**self.command("old-base-apply"), "round_input": stale})
