"""Two recipe/controller checks with real tiny tools and no model/network calls."""
import copy
import json
from pathlib import Path
import unittest
from unittest.mock import patch

import test_local_evidence as fixtures
from autoresearch import grouped_quality_adapter as grouped, source_evidence_adapter as reader
from autoresearch.contracts import ResearchError, fingerprint
from autoresearch.project_controller import ProjectController


class ProjectRecipeSelectionTests(unittest.TestCase):
    def setUp(self):
        fixtures.LocalEvidenceTests.setUp(self)
        self.manager.register_evidence(fixtures.LocalEvidenceTests.body(self))
        self.controller = ProjectController(self.project.root)
        recipe_file = Path(__file__).resolve().parents[1] / "examples/research-recipes/tabular-group-first.json"
        self.recipe = json.loads(recipe_file.read_text(encoding="utf-8"))

    def assert_code(self, code, callback, **kwargs):
        with self.assertRaises(ResearchError) as caught:
            callback(**kwargs)
        self.assertEqual(caught.exception.code, code)

    def request(self, request_id, *, recipe=None):
        return {"request_id": request_id, "recipe": self.recipe if recipe is None else recipe,
                "expected_state_version": self.project.status()["state_version"]}

    def test_recipe_selects_group_then_source_with_full_frozen_decision_and_zero_replay(self):
        context = self.controller.selection_context()
        self.assertEqual({c["method_id"] for c in context["candidates"]}, {grouped.TOOL_ID, "research.source-selection"})
        group_request = self.request("recipe-group")
        with patch.object(grouped, "execute", wraps=grouped.execute) as group, \
                patch.object(reader, "execute", wraps=reader.execute) as extract:
            selected = self.controller.advance_recipe(**group_request)
            self.assertEqual((selected["status"], selected["decision"]["next_action"]["method_id"]), ("completed", grouped.TOOL_ID))
            decision = selected["recipe_decision"]
            self.assertEqual(decision["reason"], "FIRST_MATCHING_HOST_CANDIDATE")
            self.assertEqual(decision["recipe"], self.recipe)
            self.assertEqual(decision["context_sha256"], context["context_sha256"])
            self.assertEqual(decision["proposal"], selected["selection_proposal"])
            self.assertEqual(selected["decision"]["policy_ref"], {"id": self.recipe["id"], "version": self.recipe["version"], "kind": "deterministic_recipe"})
            self.assertEqual(selected["decision"]["selection_ref"]["external_usage"], "no_model_invocation_by_recipe_compiler")
            self.assertFalse(selected["decision"]["selection_ref"]["model_execution_verified"])
            parent = self.controller._parent(self.project.status(), "recipe-group")
            self.assertEqual(parent["request"]["command"], "controller.advance_recipe")
            self.assertEqual(parent["request"]["recipe_decision"], decision)
            self.assertEqual(parent["request_sha256"], fingerprint(parent["request"]))
            self.assertEqual(parent["selection_context"], context)
            self.assertEqual(set(parent["request"]["proposal"]), {"schema_version", "context_sha256", "provider", "choice", "rationale", "evidence_citation_ids"})
            after_group = self.project.status()
            with patch.object(self.controller, "selection_context", side_effect=AssertionError("Replay must not choose from a fresh context")):
                replay = self.controller.advance_recipe(**group_request)
            self.assertTrue(replay["replayed"])
            self.assertEqual(replay["child_request_id"], selected["child_request_id"])
            self.assertEqual(self.project.status(), after_group)
            source_request = self.request("recipe-source")
            source = self.controller.advance_recipe(**source_request)
            self.assertEqual((source["status"], source["decision"]["next_action"]["method_id"]), ("completed", "research.source-selection"))
            self.assertNotEqual(source["recipe_decision"]["context_sha256"], decision["context_sha256"])
            source_parent = self.controller._parent(self.project.status(), "recipe-source")
            self.assertEqual(source_parent["request"]["recipe_decision"]["recipe"], self.recipe)
            saved = self.project.status()
            source_replay = ProjectController(self.project.root).advance_recipe(**source_request)
            self.assertTrue(source_replay["replayed"])
            self.assertEqual(source_replay["child_request_id"], source["child_request_id"])
            self.assertEqual(self.project.status(), saved)
            group.assert_called_once()
            extract.assert_called_once()
        self.assertEqual((saved["budget"]["local_tool_calls_used"], saved["budget"]["evidence_reads_used"]), (2, 1))
        self.assertEqual((saved["budget"]["new_model_requests"], saved["budget"]["new_fits"]), (0, 0))
        self.assertFalse(source["scientific_validation"])

    def test_interrupted_child_recovers_same_request_conflicts_waits_and_unknown_never_resend(self):
        original = self.request("recipe-interrupted")
        with patch.object(grouped, "execute", wraps=grouped.execute) as group:
            with patch.object(self.controller, "_finish", side_effect=KeyboardInterrupt("Fixture after child commit")):
                with self.assertRaises(KeyboardInterrupt):
                    self.controller.advance_recipe(**original)
            interrupted = self.project.status()
            parent = self.controller._parent(interrupted, original["request_id"])
            self.assertEqual(parent["status"], "prepared")
            self.assertEqual(interrupted["actions"][-1]["status"], "completed")
            recovered = ProjectController(self.project.root).advance_recipe(**original)
            self.assertEqual((recovered["status"], recovered["child_request_id"]), ("completed", parent["child_request_id"]))
            self.assertTrue(recovered["replayed"])
            self.assertEqual(len(self.project.status()["actions"]), 2)
            group.assert_called_once()
        changed = copy.deepcopy(self.recipe)
        changed["question"] += " Changed recipe identity."
        for update in ({"recipe": changed}, {"need": "different need"},
                       {"expected_state_version": original["expected_state_version"] + 1}):
            self.assert_code("IDEMPOTENCY_CONFLICT", self.controller.advance_recipe, **{**original, **update})
        self.assert_code("IDEMPOTENCY_CONFLICT", self.controller.advance_selection,
                         request_id=original["request_id"], proposal=recovered["selection_proposal"])
        for request_id, mutate, reason in (
                ("recipe-scope-wait", lambda r: r["scope_match"].update(contract="other-contract"), "SCOPE_MISMATCH"),
                ("recipe-no-match", lambda r: r.update(ordered_methods=[{"method_id": "unavailable-method", "evaluation_ref": "unavailable-evaluation"}]), "NO_MATCHING_HOST_CANDIDATE")):
            waiting_recipe = copy.deepcopy(self.recipe)
            mutate(waiting_recipe)
            before = self.project.status()
            waited = self.controller.advance_recipe(**self.request(request_id, recipe=waiting_recipe))
            self.assertEqual((waited["status"], waited["child_request_id"], waited["recipe_decision"]["reason"]), ("waiting", None, reason))
            self.assertEqual(self.project.status()["budget"], before["budget"])
        unknown_request = self.request("recipe-unknown-source")
        with patch.object(reader, "execute", side_effect=KeyboardInterrupt("Fixture extraction unknown")) as extract:
            with self.assertRaises(KeyboardInterrupt):
                self.controller.advance_recipe(**unknown_request)
            unknown = ProjectController(self.project.root).advance_recipe(**unknown_request)
            self.assertEqual(unknown["status"], "unknown")
            self.assertEqual(self.controller.advance_recipe(**unknown_request)["status"], "unknown")
            bypass = self.controller.advance_recipe(**self.request("recipe-must-not-bypass"))
            self.assertEqual((bypass["status"], bypass["child_request_id"], bypass["recipe_decision"]["reason"]), ("needs_review", None, "HOST_BLOCKERS"))
            self.assertEqual(self.project.status()["budget"]["evidence_reads_reserved"], 1)
            extract.assert_called_once()


if __name__ == "__main__":
    unittest.main()
