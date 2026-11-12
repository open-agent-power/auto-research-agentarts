"""Read complete supplied v3 fields through a real offline RSI handoff."""
import copy
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from test_saved_materials import saved_project
from autoresearch import recipe_change_proposal, recipe_improvement, recipe_improvement_adapter
from autoresearch.contracts import ResearchError, canonical
from autoresearch.host_model_selection import HostModelSelection
from autoresearch.method_registry import evaluation_ref


class SavedMaterialsRSITests(unittest.TestCase):
    def setUp(self):
        for target in ("autoresearch.ridge_validation_adapter.Ridge.fit", "autoresearch.ridge_validation_adapter.StandardScaler.fit",
                       "autoresearch.saved_oof_diagnostics.inspect_saved_oof", "autoresearch.source_evidence_adapter.execute"):
            self.enterContext(patch(target, side_effect=AssertionError("RSI saved export must never execute research")))
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.manager, self.project, selector = saved_project(self.root)
        self.selectors = [dict(selector, fields=["groups", "folds", "rows"])]
        self.recipe = {"schema_version": "research-recipe-v1", "id": "saved-route", "version": 1,
            "question": "Interpret retained diagnostic errors", "scope_match": {"domain": "data", "contract": "tabular-quality-v1"},
            "need": "next_check", "ordered_methods": [{"method_id": "data.saved-oof-group-diagnostics",
                "evaluation_ref": evaluation_ref("data.saved-oof-group-diagnostics")}], "on_no_match": "wait"}

    def export_fixture(self):
        goal = "Keep all supplied saved diagnostic fields while waiting for independent evidence"
        context = recipe_change_proposal.build_context(self.project, self.recipe, goal, saved_materials=self.selectors)
        trace = context["research_context"]
        options = {"workspace": self.project.root, "request_id": "saved-rsi", "decision_limit": 1,
                   "cli_budget_usd": 0.1, "reason": "Constructed saved export round trip", "saved_materials": self.selectors}
        recipe_improvement_adapter.propose_recipe_change(self.recipe, trace, goal, **options)
        candidate = dict(self.recipe, version=2, question="Retain complete diagnostic details and unresolved evidence")
        response = self.root / "constructed-response.json"
        response.write_text(canonical({"candidate": candidate, "reason": "Keep the complete saved evidence visible",
            "feedback_action_ids": [self.selectors[0]["action_id"]], "expected_improvement": "Retain every saved field",
            "validation_plan": "Wait on the frozen completed method without new execution"}), encoding="utf-8")
        proposed = recipe_improvement_adapter.propose_recipe_change(self.recipe, trace, goal, response_file=response, **options)
        validation = recipe_improvement_adapter.validate_recipe_change(proposed["candidate"], self.recipe, goal,
            workspace=self.project.root, request_id="saved-rsi", allowed_methods=[], allowed_receipts=[])
        self.assertEqual(validation["status"], "waiting")
        record = HostModelSelection(self.project.root).status(request_id="saved-rsi")
        exported = self.root / "offline-export"
        shutil.copytree(self.project.root, exported / "project", ignore=shutil.ignore_patterns("*.sqlite*", "writer.lock"))
        (exported / "derived").mkdir()
        for name, value in {"current-recipe.json": self.recipe, "candidate-recipe.json": candidate,
                            "selection-context.json": trace["selection_context"], "proposal-result.json": proposed}.items():
            (exported / "derived" / name).write_text(canonical(value), encoding="utf-8")
        (exported / "handoff.json").write_text(canonical({"schema_version": "a64-rsi-evidence-handoff-v1",
            "request_id": "saved-rsi", "project_id": trace["selection_context"]["project_id"]}), encoding="utf-8")
        return exported, record, trace, validation

    def test_actual_handoff_load_preserves_all_original_fields_prompt_and_coverage(self):
        exported, record, trace, validation = self.export_fixture()
        self.assertFalse(list(exported.rglob("*.sqlite*")))
        before = {path: path.read_bytes() for path in exported.rglob("*") if path.is_file()}
        state = self.project.status()
        loaded = recipe_improvement.load_saved_export(exported)
        self.assertEqual(loaded["trace"], trace)
        self.assertEqual(loaded["validation_result"], validation)
        supplied = loaded["trace"]["supplied_materials"][0]
        self.assertEqual(supplied["coverage"], "complete_saved_fields")
        self.assertEqual({key: field["count"] for key, field in supplied["fields"].items()},
                         {"groups": 2, "folds": 2, "rows": 4})
        context = record["context"]
        self.assertEqual(recipe_change_proposal.build_prompt(context), record["prompt"])
        frozen_prompt = exported / "project/host-model-selections" / record["directory"] / "prompt.json"
        self.assertEqual(json.loads(frozen_prompt.read_bytes()), record["prompt"])
        original = json.loads((exported / "project" / supplied["artifact_ref"]).read_bytes())
        for name, field in supplied["fields"].items():
            self.assertEqual(field["value"], original["tool_result"]["result"]["diagnostic"][name])
        self.assertEqual({path: path.read_bytes() for path in exported.rglob("*") if path.is_file()}, before)
        self.assertEqual(self.project.status(), state)

    def test_actual_loader_rejects_changed_complete_values_or_producer_identities(self):
        exported, record, _, _ = self.export_fixture()
        host_path = exported / "project/host-model-selections/state.json"
        context_path = exported / "project/host-model-selections" / record["directory"] / "context.json"
        host_raw, context_raw = host_path.read_bytes(), context_path.read_bytes()
        for mutate in (
            lambda material: material["fields"]["rows"]["value"][0].update(input_values={"invented": 123}),
            lambda material: material["fields"]["groups"]["value"][0].update(logical_records=[99]),
            lambda material: material["producer"].update(code_identity="f" * 64),
            lambda material: material.update(result_sha256="f" * 64),
        ):
            host, context = json.loads(host_raw), json.loads(context_raw)
            mutate(context["research_context"]["supplied_materials"][0])
            host["requests"][record["request_id"]]["context"] = context
            host_path.write_text(canonical(host), encoding="utf-8")
            context_path.write_text(canonical(context), encoding="utf-8")
            with self.assertRaisesRegex(ResearchError, "Export supplied materials differ from the original complete saved fields"):
                recipe_improvement.load_saved_export(exported)
            host_path.write_bytes(host_raw); context_path.write_bytes(context_raw)


if __name__ == "__main__":
    unittest.main()
