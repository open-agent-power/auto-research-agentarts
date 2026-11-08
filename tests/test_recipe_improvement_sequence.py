"""Bounded consumption of saved RSI evidence, not autonomous research execution."""

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

from demo_saved_rounds import SOURCE, GROUPED, fixture_inputs
from autoresearch import recipe_improvement as improvement
from autoresearch.contracts import ResearchError, canonical


class RecipeImprovementSequenceTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.directory = self.root / "sequence"
        self.first = fixture_inputs()
        self.second = fixture_inputs(self.first["proposal_result"]["candidate"]["candidate"],
                                     request_id="synthetic-second", target=SOURCE, failed=True)
        self.put("first.json", self.first)
        self.put("second.json", self.second)
        self.manifest = {"schema_version": "recipe-improvement-sequence-v1", "mode": "fixture",
                         "rounds": [{"round_id": "one", "input": "first.json"},
                                    {"round_id": "two", "input": "second.json"}]}

    def put(self, name, value):
        path = self.root / name
        path.write_bytes(canonical(value).encode("utf-8"))
        return path

    def run_sequence(self, *, limit=1, manifest=None, directory=None):
        return improvement.run_improvement_sequence(manifest or self.manifest,
            directory=directory or self.directory, base_directory=self.root, max_rounds=limit)

    def files(self):
        return {path: path.read_bytes() for path in self.directory.rglob("*") if path.is_file()}

    def test_limit_resume_keep_then_revert_and_completed_replay_preserve_bytes(self):
        source_bytes = {self.root / name: (self.root / name).read_bytes() for name in ("first.json", "second.json")}
        first = self.run_sequence()
        self.assertEqual((first["status"], first["stop"]["round_id"], first["current_version"]["version"]),
                         ("paused_round_limit", "two", 2))
        self.assertEqual(first["evaluated_this_call"], 1)
        original_round = {path: path.read_bytes() for path in (self.directory / "rounds/one").rglob("*.json")}
        self.assertFalse((self.directory / "rounds/two").exists())
        with patch.object(improvement, "_sequence_inputs", wraps=improvement._sequence_inputs) as loader:
            second = self.run_sequence()
        self.assertEqual(loader.call_count, 1)
        self.assertEqual(loader.call_args.args[1]["round_id"], "two")
        self.assertEqual((second["status"], second["current_version"]["version"]), ("queue_consumed", 2))
        self.assertEqual([item["decision"] for item in second["rounds"]], ["keep", "revert"])
        self.assertEqual(second["previous_result"]["previous_round_id"], "one")
        self.assertEqual(second["previous_result"]["candidate_version"], 3)
        self.assertEqual({path: path.read_bytes() for path in original_round}, original_round)
        before = self.files()
        with patch.object(improvement, "_sequence_inputs", side_effect=AssertionError("Do not reload completed originals")):
            replay = self.run_sequence()
        self.assertEqual(replay["evaluated_this_call"], 0)
        self.assertEqual(replay["checkpoint_path"], second["checkpoint_path"])
        self.assertEqual(self.files(), before)
        self.assertEqual({path: path.read_bytes() for path in source_bytes}, source_bytes)
        self.assertFalse(list(self.directory.rglob("*.sqlite*")))

    def test_pending_stops_before_later_round_and_saved_stage_resumes(self):
        prepared = copy.deepcopy(self.first)
        prepared["proposal_result"].update(status="prepared", candidate=None, response_ref=None)
        prepared["validation_result"] = None
        self.put("first.json", prepared)
        pending = self.run_sequence(limit=2)
        self.assertEqual((pending["status"], pending["stop"]["round_id"]), ("pending_original_request", "one"))
        self.assertEqual(pending["current_version"]["version"], 1)
        self.assertFalse((self.directory / "rounds/two").exists())
        original = {path: path.read_bytes() for path in (self.directory / "rounds/one").glob("*.json")}
        before = self.files()
        self.assertEqual(self.run_sequence(limit=2)["checkpoint_path"], pending["checkpoint_path"])
        self.assertEqual(self.files(), before)
        (self.root / "first.json").rename(self.root / "temporarily-unavailable.json")
        try:
            missing = self.run_sequence(limit=2)
            self.assertEqual((missing["status"], missing["current_version"]["version"]), ("awaiting_input", 1))
            self.assertEqual(missing["rounds"][0]["status"], "pending")
        finally:
            (self.root / "temporarily-unavailable.json").rename(self.root / "first.json")
        self.put("first.json", self.first)
        resumed = self.run_sequence(limit=2)
        self.assertEqual(resumed["status"], "queue_consumed")
        self.assertTrue(Path(resumed["rounds"][0]["input_path"]).as_posix().endswith("stages/0001/input.json"))
        self.assertEqual({path: path.read_bytes() for path in original}, original)

    def test_missing_next_input_saves_position_and_later_continues(self):
        missing = copy.deepcopy(self.manifest)
        missing["rounds"][1]["input"] = "not-yet-saved.json"
        waiting = self.run_sequence(limit=2, manifest=missing)
        self.assertEqual(waiting["status"], "awaiting_input")
        self.assertEqual(waiting["stop"]["code"], "FILE_NOT_FOUND")
        self.assertEqual(waiting["next_entry"]["round_id"], "two")
        self.assertEqual(waiting["current_version"]["version"], 2)
        self.assertFalse((self.directory / "rounds/two").exists())
        self.assertTrue(Path(waiting["checkpoint_path"]).is_file())
        self.put("not-yet-saved.json", self.second)
        finished = self.run_sequence(limit=2, manifest=missing)
        self.assertEqual((finished["status"], finished["evaluated_this_call"]), ("queue_consumed", 1))

    def test_invalid_manifest_changed_identity_and_wrong_predecessor_do_not_continue(self):
        for value in (0, 33, True):
            with self.subTest(limit=value), self.assertRaises(ResearchError):
                self.run_sequence(limit=value)
        self.assertFalse(self.directory.exists())
        duplicate = copy.deepcopy(self.manifest)
        duplicate["rounds"][1]["round_id"] = "one"
        with self.assertRaises(ResearchError):
            self.run_sequence(manifest=duplicate)
        self.run_sequence()
        before = self.files()
        changed = copy.deepcopy(self.manifest)
        changed["rounds"].reverse()
        with self.assertRaises(ResearchError) as caught:
            self.run_sequence(manifest=changed)
        self.assertEqual(caught.exception.code, "IDEMPOTENCY_CONFLICT")
        self.assertEqual(self.files(), before)
        self.put("second.json", fixture_inputs(request_id="stale-version", target=SOURCE))
        with self.assertRaises(ResearchError):
            self.run_sequence()
        self.assertFalse((self.directory / "rounds/two").exists())
        self.put("second.json", self.second)
        self.run_sequence()
        path = self.directory / "rounds/one/result.json"
        damaged = improvement.read_json(path)
        damaged["decision"] = "revert"
        path.write_bytes(canonical(damaged).encode("utf-8"))
        with self.assertRaises(ResearchError):
            self.run_sequence()

    def test_initial_snapshot_and_checkpoint_interruptions_recover_without_repeating_rounds(self):
        original_write = improvement.write_bytes_once
        for name in ("initial", "checkpoint"):
            directory = self.root / name

            def interrupt(path, raw):
                if ((name == "initial" and path.parent.name == "one" and path.name == "effective-recipe.json")
                        or (name == "checkpoint" and path.parent.name == "checkpoints")):
                    raise KeyboardInterrupt("Constructed saved-output publication interruption")
                return original_write(path, raw)

            with self.subTest(stage=name):
                with patch.object(improvement, "write_bytes_once", side_effect=interrupt):
                    with self.assertRaises(KeyboardInterrupt):
                        self.run_sequence(directory=directory)
                result = self.run_sequence(limit=2, directory=directory)
                self.assertEqual(result["status"], "queue_consumed")
                self.assertEqual([item["decision"] for item in result["rounds"]], ["keep", "revert"])
                self.assertFalse((directory / "rounds/one/stages").exists())

    def test_saved_host_queue_reads_original_ledger_and_waits_for_missing_request(self):
        import test_recipe_improvement_adapter as adapter_fixtures
        from autoresearch import recipe_improvement_adapter as adapter

        fixture = adapter_fixtures.RecipeImprovementAdapterTests()
        self.addCleanup(fixture.doCleanups)
        fixture.setUp()
        candidate = fixture.propose(GROUPED["method_id"])
        adapter.validate_recipe_change(candidate, fixture.original, fixture.goal, workspace=fixture.project.root,
            request_id=fixture.options["request_id"], allowed_methods=[GROUPED["method_id"]], allowed_receipts=[])
        spec = {"issue": {"summary": "Original saved fixture feedback omits an available method.",
                          "feedback_action_ids": candidate["feedback_action_ids"]},
                "acceptance": GROUPED, "next_question": "Use saved feedback for another bounded decision."}
        spec_path = self.put("spec.json", spec)
        manifest = {"schema_version": "recipe-improvement-sequence-v1", "mode": "saved-host", "rounds": [
            {"round_id": "one", "workspace": str(fixture.project.root),
             "request_id": fixture.options["request_id"], "spec": str(spec_path)},
            {"round_id": "two", "workspace": str(fixture.project.root),
             "request_id": "not-prepared", "spec": str(spec_path)}]}
        original = {path: path.read_bytes() for path in fixture.project.root.rglob("*") if path.is_file()}
        result = self.run_sequence(limit=2, manifest=manifest)
        self.assertEqual(result["evidence_kind"], "saved_host_validation")
        self.assertEqual(result["status"], "awaiting_input")
        self.assertEqual(result["stop"]["code"], "ARTIFACT_NOT_FOUND")
        self.assertEqual(result["current_version"]["version"], 2)
        self.assertEqual({path: path.read_bytes() for path in fixture.project.root.rglob("*") if path.is_file()}, original)
        with self.assertRaises(ResearchError) as caught:
            self.run_sequence(manifest=manifest, directory=fixture.project.root / "not-an-output")
        self.assertEqual(caught.exception.code, "UNSAFE_PATH")
        self.assertFalse((fixture.project.root / "not-an-output").exists())
        with self.assertRaises(ResearchError) as caught:
            self.run_sequence(manifest=manifest, directory=fixture.project.root.parent)
        self.assertEqual(caught.exception.code, "UNSAFE_PATH")
        with self.assertRaises(ResearchError) as caught:
            self.run_sequence(manifest=manifest, directory=fixture.project.root / "unused/.." / "nested")
        self.assertEqual(caught.exception.code, "UNSAFE_PATH")

    def test_actual_sequence_cli_resolves_inputs_relative_to_manifest_and_reads_effective_version(self):
        manifest_path = self.put("queue.json", self.manifest)
        command = [sys.executable, "-B", str(ROOT / "scripts/run_recipe_improvement.py"), "sequence",
                   "--manifest", str(manifest_path), "--output", str(self.directory), "--max-rounds", "1"]
        for status in ("paused_round_limit", "queue_consumed"):
            result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, encoding="utf-8", timeout=30)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            value = json.loads(result.stdout)
            self.assertEqual(value["status"], status)
            self.assertEqual(value["current_version"]["version"], 2)
            self.assertFalse(value["scientific_validation"])
        next_result = subprocess.run([sys.executable, "-B", str(ROOT / "scripts/run_recipe_improvement.py"),
            "next-input", "--output", str(self.directory / "rounds"), "--round-id", "two"], cwd=ROOT,
            capture_output=True, text=True, encoding="utf-8", timeout=30)
        self.assertEqual(next_result.returncode, 0, next_result.stdout + next_result.stderr)
        value = json.loads(next_result.stdout)
        self.assertEqual((value["status"], value["current_version"]["version"]), ("awaiting_next_feedback", 2))


if __name__ == "__main__":
    unittest.main()
