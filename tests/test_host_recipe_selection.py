"""Recipe proposals share the original host journal and do not dispatch tools."""

import copy
import json
from pathlib import Path
import tempfile
import unittest

import test_local_workbench as fixtures
from autoresearch.contracts import ResearchError, canonical
from autoresearch.host_model_report import capture_host_models
from autoresearch.host_model_selection import HostModelSelection
from autoresearch.local_workbench import LocalWorkbench
from autoresearch.project_controller import ProjectController


class HostRecipeSelectionTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        manager = LocalWorkbench(self.root / "workbench")
        manager.create(fixtures.LocalWorkbenchTests.create_body(self))
        self.project, _ = manager.binding()
        self.journal = HostModelSelection(self.project.root)
        recipe = Path(__file__).resolve().parents[1] / "examples/research-recipes/tabular-group-first.json"
        self.recipe = json.loads(recipe.read_text(encoding="utf-8"))

    def specification(self, request_id, *, purpose="selection"):
        specification = {"request_id": request_id, "provider": "delegated", "expected_state_version": self.project.status()["state_version"],
                         "decision_limit": 2, "cli_budget_usd": 0.1, "reason": "Two prospective fixture host decisions"}
        if purpose == "recipe":
            specification.update(purpose=purpose, current_recipe=self.recipe,
                                 improvement_goal="Use the actual quality feedback to improve the next-step ordering.")
        return specification

    def import_arguments(self, request_id, arguments):
        path = self.root / (request_id + "-response.json")
        path.write_bytes(canonical(arguments).encode("utf-8"))
        self.journal.import_response(request_id=request_id, response_file=path)
        return path

    def complete_quality_selection(self):
        prepared = self.journal.prepare(**self.specification("quality-selection"))
        self.assertNotIn("purpose", prepared["prepare_specification"])
        candidate = next(item for item in prepared["context"]["candidates"] if item["method_id"] == "data.tabular-quality-audit")
        self.import_arguments("quality-selection", {"choice": {"kind": "execute", "candidate_id": candidate["id"]},
            "rationale": "Obtain the actual fixture table quality result.", "evidence_citation_ids": []})
        self.assertEqual(self.journal.consume(request_id="quality-selection")["outcome"]["status"], "completed")

    def recipe_arguments(self):
        candidate = copy.deepcopy(self.recipe)
        candidate["version"] += 1
        candidate["question"] = "Should the saved quality feedback lead to source reading before further analysis?"
        candidate["ordered_methods"].reverse()
        return {"candidate": candidate, "reason": "Consider the recorded table quality feedback before interpreting groups.",
                "feedback_action_ids": [self.project.status()["actions"][0]["id"]],
                "expected_improvement": "Make the choice respond to the actual saved result.",
                "validation_plan": "Compile both recipes on the frozen context and verify the explicitly allowed next step."}

    def test_recipe_proposal_shares_grant_replays_and_collects_validation_originals(self):
        self.complete_quality_selection()
        before = self.project.status()
        specification = self.specification("recipe-one", purpose="recipe")
        prepared = self.journal.prepare(**specification)
        self.assertEqual(prepared["purpose"], "recipe")
        response = self.import_arguments("recipe-one", self.recipe_arguments())
        proposed = self.journal.consume(request_id="recipe-one")
        self.assertEqual(proposed["status"], "proposed")
        self.assertEqual(proposed["proposal"]["candidate"]["version"], self.recipe["version"] + 1)
        reloaded = HostModelSelection(self.project.root)
        self.assertEqual(reloaded.consume(request_id="recipe-one"), proposed)
        self.assertEqual(reloaded.prepare(**specification), proposed)
        self.assertEqual(reloaded.import_response(request_id="recipe-one", response_file=response), proposed)
        self.assertEqual(self.project.status(), before)
        self.assertEqual(reloaded.status()["usage"]["decision_slots_used"], 2)
        self.assertEqual(reloaded.status()["usage"]["cli_launch_attempts"], 0)
        with self.assertRaises(ResearchError) as caught:
            reloaded.prepare(**{**specification, "request_id": "recipe-over-limit"})
        self.assertEqual(caught.exception.code, "HOST_DECISION_LIMIT")
        with self.assertRaises(ResearchError) as caught:
            reloaded.prepare(**{**specification, "request_id": "recipe-new-grant", "decision_limit": 3})
        self.assertEqual(caught.exception.code, "HOST_GRANT_CHANGED")
        folder = reloaded.directory / proposed["directory"]
        for name in ("validation-input.json", "validation-result.json"):
            (folder / name).write_bytes(canonical({"data_kind": "synthetic_collection_fixture", "status": "pending"}).encode("utf-8"))
        captured = capture_host_models(self.project.root)
        roles = {asset["role"] for asset in captured["assets"]}
        self.assertTrue({"host_recipe_validation_input", "host_recipe_validation_result"} <= roles)
        self.assertEqual(captured["records"][-1]["proposal"], proposed["proposal"])

    def test_stale_recipe_response_cannot_dispatch_or_replace_original_specification(self):
        self.complete_quality_selection()
        specification = self.specification("recipe-stale", purpose="recipe")
        prepared = self.journal.prepare(**specification)
        changed = copy.deepcopy(specification)
        changed["current_recipe"]["question"] = "Changed under the original request ID"
        with self.assertRaises(ResearchError) as caught:
            self.journal.prepare(**changed)
        self.assertEqual(caught.exception.code, "IDEMPOTENCY_CONFLICT")
        self.import_arguments("recipe-stale", self.recipe_arguments())
        self.project.step(request_id="explicit-other-step", method_id="data.grouped-quality-profile",
                          expected_state_version=self.project.status()["state_version"],
                          parameters=next(item["parameters"] for item in ProjectController(self.project.root).selection_context()["candidates"]
                                          if item["method_id"] == "data.grouped-quality-profile"))
        after_other_step = self.project.status()
        stale = self.journal.consume(request_id="recipe-stale")
        self.assertEqual(stale["status"], "stale")
        self.assertEqual(self.project.status(), after_other_step)
        self.assertEqual(self.journal.status()["usage"]["decision_slots_used"], 2)
        self.assertEqual(self.journal.status(request_id=prepared["request_id"])["response_sha256"], stale["response_sha256"])


if __name__ == "__main__":
    unittest.main()
