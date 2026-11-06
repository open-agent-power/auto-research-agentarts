"""Saved-result outer-loop decisions; constructed evidence is never a model claim."""

import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "examples/recipe-improvement"))

from demo_saved_rounds import GROUPED, SOURCE, fixture_inputs
from autoresearch.contracts import ResearchError, canonical
from autoresearch import recipe_improvement as improvement


class RecipeImprovementTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.directory = self.root / "rounds"

    def run_round(self, inputs=None, round_id="round-1", previous=None):
        return improvement.run_improvement_round(**(inputs or fixture_inputs()), directory=self.directory,
            round_id=round_id, previous_round_id=previous, evidence_kind="synthetic_engineering_fixture")

    def test_keep_replay_and_failed_next_round_use_actual_effective_version(self):
        inputs = fixture_inputs()
        original = copy.deepcopy(inputs)
        first = self.run_round(inputs)
        self.assertEqual((first["decision"], first["effective_recipe"]["version"]), ("keep", 2))
        self.assertTrue(all(first["checks"].values()))
        self.assertFalse(first["scientific_validation"])
        self.assertEqual(inputs, original)
        before = {path: path.read_bytes() for path in self.directory.rglob("*.json")}
        self.assertEqual(self.run_round(inputs), first)
        self.assertEqual({path: path.read_bytes() for path in before}, before)
        second_input = fixture_inputs(first["effective_recipe"], request_id="second", target=SOURCE, failed=True)
        second = self.run_round(second_input, "round-2", "round-1")
        self.assertEqual((second["decision"], second["base_version"], second["candidate_version"]), ("revert", 2, 3))
        self.assertEqual(second["effective_recipe"], first["effective_recipe"])
        self.assertEqual((second["previous_round_id"], second["previous_decision"]), ("round-1", "keep"))
        third = self.run_round(fixture_inputs(second["effective_recipe"], request_id="third", target=SOURCE),
                               "round-3", "round-2")
        self.assertEqual((third["previous_decision"], third["effective_recipe"]["version"]), ("revert", 3))

    def test_choice_changed_alone_and_already_satisfied_target_do_not_promote(self):
        changed = fixture_inputs()
        changed["acceptance"] = SOURCE
        self.assertTrue(changed["validation_result"]["selection_changed"])
        self.assertEqual(self.run_round(changed)["decision"], "revert")
        current = fixture_inputs()["proposal_result"]["candidate"]["candidate"]
        unchanged = self.run_round(fixture_inputs(current), "unchanged")
        self.assertEqual(unchanged["decision"], "revert")
        self.assertFalse(unchanged["checks"]["baseline_misses_target"])

    def test_failed_waiting_rejected_and_missing_artifacts_preserve_original(self):
        for status in ("failed", "waiting", "rejected", "completed"):
            with self.subTest(status=status):
                inputs = fixture_inputs()
                validation = inputs["validation_result"]
                validation["status"] = validation["controller_outcome"]["status"] = status
                if status == "completed":
                    validation["artifact_refs"] = []
                result = self.run_round(inputs, status)
                self.assertEqual(result["decision"], "revert")
                self.assertEqual(result["effective_recipe"], inputs["current_version"])

    def test_prepared_missing_validation_and_unknown_stay_pending(self):
        prepared = fixture_inputs()
        prepared["proposal_result"].update(status="prepared", candidate=None, response_ref=None)
        prepared["validation_result"] = None
        no_validation = fixture_inputs()
        no_validation["validation_result"] = None
        unknown = fixture_inputs()
        unknown["validation_result"]["status"] = unknown["validation_result"]["controller_outcome"]["status"] = "unknown"
        for index, inputs in enumerate((prepared, no_validation, unknown)):
            result = self.run_round(inputs, f"pending-{index}")
            self.assertEqual((result["status"], result["decision"]), ("pending", "pending"))
            self.assertEqual(result["effective_recipe"], inputs["current_version"])
        with self.assertRaises(ResearchError):
            self.run_round(fixture_inputs(), "next", "pending-0")

    def test_failed_proposal_never_changes_effective_recipe(self):
        inputs = fixture_inputs()
        inputs["proposal_result"].update(status="failed", candidate=None)
        inputs["validation_result"] = None
        result = self.run_round(inputs)
        self.assertEqual((result["status"], result["decision"], result["reason"]),
                         ("completed", "revert", "PROPOSAL_FAILED"))
        self.assertEqual(result["effective_recipe"], inputs["current_version"])

    def test_stale_original_and_changed_round_id_inputs_are_rejected(self):
        self.run_round()
        with self.assertRaises(ResearchError):
            self.run_round(fixture_inputs(request_id="different"))
        with self.assertRaises(ResearchError):
            self.run_round(fixture_inputs(request_id="next"), "next", "round-1")
        with self.assertRaises(ResearchError):
            self.run_round(round_id="..")
        with self.assertRaises(ResearchError):
            self.run_round(round_id="round-1", previous="round-1")

    def test_rejects_mismatched_context_proposal_feedback_and_validation(self):
        mutations = [lambda x: x["trace"]["selection_context"].update(state_version=100),
            lambda x: x["issue"].update(feedback_action_ids=["not-an-action"]),
            lambda x: x["proposal_result"]["candidate"]["candidate"].update(version=10),
            lambda x: x["validation_result"].update(request_id="different"),
            lambda x: x["validation_result"].update(selection_changed=False),
            lambda x: x["validation_result"]["controller_outcome"].update(project_id="different"),
            lambda x: x["validation_result"]["controller_outcome"].update(request_id="different"),
            lambda x: x["validation_result"]["controller_outcome"].update(selection_context_sha256="0" * 64),
            lambda x: x["validation_result"]["candidate_decision"].update(recipe_version=100),
            lambda x: x["validation_result"]["controller_outcome"].update(recipe_decision={})]
        for index, mutate in enumerate(mutations):
            with self.subTest(index=index):
                inputs = fixture_inputs()
                mutate(inputs)
                with self.assertRaises(ResearchError):
                    self.run_round(inputs, f"invalid-{index}")

    def test_recompute_predecessor_rejects_changed_receipt(self):
        first = self.run_round()
        path = self.directory / "round-1/result.json"
        changed = copy.deepcopy(first)
        changed["decision"] = "revert"
        path.write_bytes(canonical(changed).encode("utf-8"))
        with self.assertRaises(ResearchError) as caught:
            self.run_round(fixture_inputs(first["effective_recipe"]), "next", "round-1")
        self.assertEqual(caught.exception.code, "EVIDENCE_CHANGED")

    def test_atomic_publication_interruption_replays_identical_input(self):
        original = improvement.write_bytes_once

        def interrupt(path, raw):
            if path.name == "effective-recipe.json":
                raise KeyboardInterrupt("Constructed interruption during outer receipt publication")
            return original(path, raw)

        with patch.object(improvement, "write_bytes_once", side_effect=interrupt):
            with self.assertRaises(KeyboardInterrupt):
                self.run_round()
        result = self.run_round()
        self.assertEqual(improvement.read_improvement_round(self.directory, "round-1"), result)

    def test_cli_two_round_demo_is_explicit_fixture_and_replays(self):
        command = [sys.executable, "-B", str(ROOT / "examples/recipe-improvement/demo_saved_rounds.py"),
                   "--output", str(self.directory)]
        for _ in range(2):
            completed = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", timeout=30)
            self.assertEqual(completed.returncode, 0, completed.stderr + completed.stdout)
            outputs = [json.loads(line) for line in completed.stdout.splitlines()]
            self.assertEqual([item["decision"] for item in outputs], ["keep", "revert"])
            self.assertTrue(all(item["evidence_kind"] == "synthetic_engineering_fixture" for item in outputs))

    def test_saved_host_cli_uses_verified_original_receipt_without_dispatch(self):
        import test_recipe_improvement_adapter as adapter_fixtures
        from autoresearch import recipe_improvement_adapter as adapter
        from autoresearch.host_model_selection import HostModelSelection

        fixture = adapter_fixtures.RecipeImprovementAdapterTests()
        self.addCleanup(fixture.doCleanups)
        fixture.setUp()
        proposal = fixture.propose(GROUPED["method_id"])
        request_id = fixture.options["request_id"]
        adapter.validate_recipe_change(proposal, fixture.original, fixture.goal,
            workspace=fixture.project.root, request_id=request_id, allowed_methods=[GROUPED["method_id"]], allowed_receipts=[])
        before = fixture.project.status()
        host_before = HostModelSelection(fixture.project.root).status(request_id=request_id)
        snapshot = {path: path.read_bytes() for path in fixture.project.root.rglob("*") if path.is_file()}
        spec = {"issue": {"summary": "Constructed quality feedback has an omitted follow-up.",
                          "feedback_action_ids": proposal["feedback_action_ids"]},
                "acceptance": GROUPED, "next_question": "Review source conditions next."}
        path = self.root / "spec.json"
        path.write_bytes(canonical(spec).encode("utf-8"))
        command = [sys.executable, "-B", str(ROOT / "scripts/run_recipe_improvement.py"), "saved-host",
            "--workspace", str(fixture.project.root), "--request-id", request_id, "--spec", str(path),
            "--output", str(self.directory), "--round-id", "saved-fixture-host"]
        result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertEqual(json.loads(result.stdout)["decision"], "keep")
        self.assertEqual(fixture.project.status(), before)
        self.assertEqual(HostModelSelection(fixture.project.root).status(request_id=request_id), host_before)
        self.assertEqual({path: path.read_bytes() for path in snapshot}, snapshot)
        receipt = HostModelSelection(fixture.project.root).directory / host_before["directory"] / "validation-result.json"
        altered = json.loads(receipt.read_bytes())
        altered["controller_outcome"]["child_request_id"] = "forged-child"
        receipt.write_bytes(canonical(altered).encode("utf-8"))
        rejected = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", timeout=30)
        self.assertEqual(rejected.returncode, 2, rejected.stdout)
        self.assertFalse(json.loads(rejected.stdout)["ok"])

    def test_reader_rejects_links_and_round_effective_recipe_tampering(self):
        self.run_round()
        path = self.directory / "round-1/effective-recipe.json"
        path.write_bytes(canonical(fixture_inputs()["current_version"]).encode("utf-8"))
        with self.assertRaises(ResearchError):
            improvement.read_improvement_round(self.directory, "round-1")
        with patch.object(Path, "is_symlink", return_value=True):
            with self.assertRaises(ResearchError) as caught:
                improvement.read_json(path)
        self.assertEqual(caught.exception.code, "UNSAFE_PATH")


if __name__ == "__main__":
    unittest.main()
