"""Recipe callbacks bind actual feedback, permitted tools and original recovery."""

import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import test_local_evidence as evidence_fixtures
import test_local_workbench as fixtures
from autoresearch import recipe_improvement_adapter as adapter
from autoresearch.contracts import ResearchError, canonical
from autoresearch.host_model_report import capture_host_models
from autoresearch.host_model_selection import HostModelSelection
from autoresearch.local_workbench import LocalWorkbench
from autoresearch.project_controller import ProjectController
from autoresearch.research_plan_proposal import build_context


class RecipeImprovementAdapterTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.manager = LocalWorkbench(self.root / "workbench")
        self.manager.create(fixtures.LocalWorkbenchTests.create_body(self))
        self.project, _ = self.manager.binding()
        controller = ProjectController(self.project.root)
        self.assertEqual(controller.advance(request_id="fixture-quality")["status"], "completed")
        recipe_path = Path(__file__).resolve().parents[1] / "examples/research-recipes/tabular-group-first.json"
        self.original = json.loads(recipe_path.read_text(encoding="utf-8"))
        self.original["id"] = "completed-quality-only-fixture"
        primary = next(item for item in controller.selection_context()["conditions"]
                       if item["method_id"] == "data.tabular-quality-audit")
        self.original["ordered_methods"] = [{key: primary[key] for key in ("method_id", "evaluation_ref")}]
        self.goal = "Use the saved result to select an available follow-up instead of waiting."
        self.options = {"workspace": self.project.root, "request_id": "recipe-callback",
                        "decision_limit": 1, "cli_budget_usd": 0.1,
                        "reason": "One constructed callback integration decision", "provider": "delegated"}

    def propose(self, method_id):
        self.trace = build_context(self.project)
        before = self.project.status()
        prepared = adapter.propose_recipe_change(self.original, self.trace, self.goal, **self.options)
        self.assertEqual(prepared["status"], "prepared")
        method = next(item for item in self.trace["selection_context"]["conditions"] if item["method_id"] == method_id)
        candidate = copy.deepcopy(self.original)
        candidate["version"] += 1
        candidate["ordered_methods"] = [{key: method[key] for key in ("method_id", "evaluation_ref")}]
        arguments = {"candidate": candidate, "reason": "The original recipe omits an actual follow-up candidate.",
                     "feedback_action_ids": [self.project.status()["actions"][0]["id"]],
                     "expected_improvement": "Select the available follow-up on the frozen fixture input.",
                     "validation_plan": "Compare frozen choices and execute only the explicitly allowed method."}
        self.response = self.root / "constructed-provider-response.json"
        self.response.write_bytes(canonical(arguments).encode("utf-8"))
        proposed = adapter.propose_recipe_change(self.original, self.trace, self.goal,
                                                response_file=self.response, **self.options)
        self.assertEqual(proposed["status"], "proposed")
        self.assertEqual(self.project.status(), before)
        return proposed["candidate"]

    def test_committed_tool_interruption_recovers_original_validation_and_proposal(self):
        candidate = self.propose("data.grouped-quality-profile")
        options = {"workspace": self.project.root, "request_id": self.options["request_id"],
                   "allowed_methods": ["data.grouped-quality-profile"], "allowed_receipts": []}
        original_write = adapter.write_bytes_once

        def interrupt_result(path, raw):
            if path.name == "validation-result.json":
                raise KeyboardInterrupt("Constructed interruption after the original controller completed")
            return original_write(path, raw)

        with patch.object(adapter, "write_bytes_once", side_effect=interrupt_result):
            with self.assertRaises(KeyboardInterrupt):
                adapter.validate_recipe_change(candidate, self.original, self.goal, **options)
        completed = self.project.status()
        self.assertEqual(completed["budget"]["local_tool_calls_used"], 2)
        result = adapter.validate_recipe_change(candidate, self.original, self.goal, **options)
        self.assertEqual(result["status"], "completed")
        self.assertTrue(result["selection_changed"])
        self.assertTrue(result["controller_outcome"]["replayed"])
        self.assertTrue(result["artifact_refs"])
        self.assertEqual(adapter.validate_recipe_change(candidate, self.original, self.goal, **options), result)
        replayed = adapter.propose_recipe_change(self.original, self.trace, self.goal,
                                                response_file=self.response, **self.options)
        self.assertEqual(replayed["candidate"], candidate)
        self.assertEqual(self.project.status(), completed)
        self.assertEqual(HostModelSelection(self.project.root).status()["usage"]["decision_slots_used"], 1)
        roles = {item["role"] for item in capture_host_models(self.project.root)["assets"]}
        self.assertTrue({"host_recipe_validation_input", "host_recipe_validation_result"} <= roles)

    def test_method_and_exact_source_permissions_are_bound_before_execution(self):
        registered = self.manager.register_evidence(evidence_fixtures.LocalEvidenceTests.body(self))
        receipt = registered["registration"]["receipt_snapshot_sha256"]
        candidate = self.propose("research.source-selection")
        options = {"workspace": self.project.root, "request_id": self.options["request_id"],
                   "allowed_methods": [], "allowed_receipts": []}
        before = self.project.status()
        with self.assertRaises(ResearchError) as caught:
            adapter.validate_recipe_change(candidate, self.original, self.goal, **options)
        self.assertEqual(caught.exception.code, "METHOD_NOT_AUTHORIZED")
        options["allowed_methods"] = ["research.source-selection"]
        with self.assertRaises(ResearchError) as caught:
            adapter.validate_recipe_change(candidate, self.original, self.goal, **options)
        self.assertEqual(caught.exception.code, "SOURCE_NOT_AUTHORIZED")
        self.assertEqual(self.project.status(), before)
        options["allowed_receipts"] = [receipt]
        result = adapter.validate_recipe_change(candidate, self.original, self.goal, **options)
        self.assertEqual(result["status"], "completed")
        after = self.project.status()
        self.assertEqual(after["budget"]["evidence_reads_used"], 1)
        changed = {**options, "allowed_methods": ["research.source-selection", "data.grouped-quality-profile"]}
        with self.assertRaises(ResearchError) as caught:
            adapter.validate_recipe_change(candidate, self.original, self.goal, **changed)
        self.assertEqual(caught.exception.code, "IDEMPOTENCY_CONFLICT")
        self.assertEqual(self.project.status(), after)

    def test_validation_reader_reports_receipt_state_and_preserves_all_saved_bytes(self):
        candidate = self.propose("data.grouped-quality-profile")
        journal = HostModelSelection(self.project.root)
        record = journal.status(request_id=self.options["request_id"])
        folder = journal.directory / record["directory"]
        result_path, input_path = folder / "validation-result.json", folder / "validation-input.json"

        def snapshot():
            return (self.project.status(), journal.status(request_id=record["request_id"]),
                    {path.relative_to(self.root).as_posix(): path.read_bytes() for path in self.root.rglob("*") if path.is_file()})

        def read_and_check(status):
            before = snapshot()
            with patch.object(adapter, "validate_recipe_change", side_effect=AssertionError("A reader must not run validation")):
                view = adapter.read_recipe_validation(self.project.root, record["request_id"])
                models = self.manager.model_view()
            self.assertEqual(view["status"], status)
            self.assertEqual(models["recipe_validations"], [view])
            self.assertEqual(models["records"], [before[1]])
            self.assertEqual(snapshot(), before)
            return view

        not_started = read_and_check("not_started")
        self.assertIsNone(not_started["input"])
        self.assertIsNone(not_started["result"])
        result = adapter.validate_recipe_change(candidate, self.original, self.goal, workspace=self.project.root,
            request_id=record["request_id"], allowed_methods=["data.grouped-quality-profile"], allowed_receipts=[])
        completed = read_and_check("completed")
        self.assertEqual(completed["result"], result)
        original_result = result_path.read_bytes()
        replayed_result = json.loads(original_result)
        replayed_result["controller_outcome"]["replayed"] = True
        result_path.write_bytes(canonical(replayed_result).encode("utf-8"))
        read_and_check("completed")
        result_path.unlink()
        missing = read_and_check("recovery_required")
        self.assertIsNone(missing["result"])
        self.assertEqual(missing["error"]["code"], "VALIDATION_RECEIPT_MISSING")
        changed = json.loads(original_result)
        changed["controller_outcome"]["child_request_id"] = "different-child"
        result_path.write_bytes(canonical(changed).encode("utf-8"))
        self.assertEqual(read_and_check("invalid")["error"]["code"], "EVIDENCE_CHANGED")
        result_path.write_bytes(original_result)
        changed_input = json.loads(input_path.read_bytes())
        changed_input["context_sha256"] = "0" * 64
        input_path.write_bytes(canonical(changed_input).encode("utf-8"))
        self.assertEqual(read_and_check("invalid")["error"]["code"], "EVIDENCE_CHANGED")


if __name__ == "__main__":
    unittest.main()
