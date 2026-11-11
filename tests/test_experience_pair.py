"""Offline experience pairs preserve current evidence and reject changed artifacts."""

import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

import test_project_experience_controller as fixtures
from autoresearch import research_plan_proposal as protocol
from autoresearch.contracts import ResearchError
from autoresearch.host_model_selection import HostModelSelection


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "prepare_experience_pair.py"
SPEC = importlib.util.spec_from_file_location("prepare_experience_pair", SCRIPT)
pair = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(pair)


class ExperiencePairTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixtures.ProjectExperienceControllerTests.setUpClass()
        cls.addClassCleanup(fixtures.ProjectExperienceControllerTests.doClassCleanups)

    def setUp(self):
        self.fixture = fixtures.ProjectExperienceControllerTests()
        self.addCleanup(self.fixture.doCleanups)
        self.fixture.setUp()
        self.project = self.fixture.project
        self.host = HostModelSelection(self.project.root)
        self.output = self.project.root.parent / "pair"

    @staticmethod
    def tree_bytes(root):
        return {str(path.relative_to(root)): path.read_bytes() for path in root.rglob("*") if path.is_file()}

    def assert_code(self, code, callback, *args):
        with self.assertRaises(ResearchError) as caught:
            callback(*args)
        self.assertEqual(caught.exception.code, code)

    def test_pair_and_cli_preserve_native_prompts_all_other_values_and_source_bytes(self):
        self.fixture.attach()
        before, host_before = self.project.status(), self.host.status()
        original_context = protocol.build_context(self.project)
        original_files = self.tree_bytes(self.project.root)
        manifest = pair.prepare_pair(self.project.root, self.output)
        self.assertEqual(pair.verify_pair(self.output), manifest)
        current = json.loads((self.output / "current-context.json").read_bytes())
        control = json.loads((self.output / "control-context.json").read_bytes())
        self.assertEqual(current, original_context)
        current_payload, control_payload = copy.deepcopy(current), copy.deepcopy(control)
        current_payload["selection_context"].pop("experience")
        current_sha = current_payload["selection_context"].pop("context_sha256")
        control_sha = control_payload["selection_context"].pop("context_sha256")
        self.assertNotEqual(current_sha, control_sha)
        self.assertEqual(current_payload, control_payload)
        for arm, context in (("current", current), ("control", control)):
            self.assertEqual(json.loads((self.output / (arm + "-prompt.json")).read_bytes()), protocol.build_prompt(context))
        self.assertEqual(manifest["arms"]["control"]["mode"], "offline_ablation")
        self.assertEqual(manifest["case_ids"], [self.fixture.bundle["id"]])
        self.assertFalse(manifest["scientific_validation"])
        completed = subprocess.run([sys.executable, str(SCRIPT), "--workspace", str(self.project.root),
                                    "--output", str(self.output.parent / "cli-pair")],
                                   capture_output=True, text=True, encoding="utf-8", check=False)
        self.assertEqual(completed.returncode, 0, completed.stderr + completed.stdout)
        self.assertTrue(json.loads(completed.stdout)["ok"])
        self.assertEqual(self.project.status(), before)
        self.assertEqual(self.host.status(), host_before)
        self.assertEqual(self.tree_bytes(self.project.root), original_files)

    def test_missing_active_case_and_conflicting_outputs_fail_without_source_writes(self):
        before = self.tree_bytes(self.project.root)
        self.assert_code("NO_ACTIVE_EXPERIENCE", pair.prepare_pair, self.project.root, self.output)
        self.assertFalse(self.output.exists())
        self.assertEqual(self.tree_bytes(self.project.root), before)
        self.fixture.attach()
        before = self.tree_bytes(self.project.root)
        for output in (self.project.root, self.project.root / "pair", self.project.root.parent):
            with self.subTest(output=output):
                self.assert_code("INVALID_OUTPUT_PATH", pair.prepare_pair, self.project.root, output)
        self.output.mkdir()
        self.assert_code("OUTPUT_EXISTS", pair.prepare_pair, self.project.root, self.output)
        self.assertEqual(self.tree_bytes(self.project.root), before)
        self.assertFalse((self.project.root / "host-model-selections").exists())

    def test_verifier_rejects_changed_raw_bytes_even_when_json_values_are_identical(self):
        self.fixture.attach()
        pair.prepare_pair(self.project.root, self.output)
        path = self.output / "current-prompt.json"
        original = path.read_bytes()
        path.write_bytes(original + b"\n")
        self.assertEqual(json.loads(path.read_bytes()), json.loads(original))
        self.assert_code("EVIDENCE_CHANGED", pair.verify_pair, self.output)

    def test_snapshot_or_host_change_during_publication_stops_and_retains_artifacts(self):
        self.fixture.attach()
        native_write = pair.write_bytes_once
        for change in ("project", "host"):
            with self.subTest(change=change):
                if change == "host":
                    self.project.set_experience_status(request_id="restore-pair-case",
                        expected_state_version=self.project.status()["state_version"], case_id=self.fixture.bundle["id"],
                        status="active", reason="Restore only this constructed test case.")
                output = self.output.with_name(change + "-changed-pair")
                mutations = []

                def write_and_change(path, raw):
                    native_write(path, raw)
                    if mutations:
                        return
                    mutations.append(change)
                    if change == "project":
                        self.project.set_experience_status(request_id="retire-pair-case",
                            expected_state_version=self.project.status()["state_version"], case_id=self.fixture.bundle["id"],
                            status="retired", reason="Simulate a concurrent project change in this fixture.")
                    else:
                        self.host.prepare(request_id="concurrent-pair-host", provider="delegated", purpose="plan",
                            expected_state_version=self.project.status()["state_version"], decision_limit=1,
                            cli_budget_usd=0.1, reason="Constructed concurrent Host preparation; no model is called.")

                with patch.object(pair, "write_bytes_once", side_effect=write_and_change):
                    self.assert_code("STALE_STATE" if change == "project" else "HOST_STATE_CHANGED",
                                     pair.prepare_pair, self.project.root, output)
                self.assertEqual(mutations, [change])
                self.assertEqual({path.name for path in output.iterdir()}, pair.FROZEN_FILES)
                self.assertFalse((output / "manifest.json").exists())


if __name__ == "__main__":
    unittest.main()
