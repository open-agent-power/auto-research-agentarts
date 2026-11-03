"""Selection integration only; provider labels and fixture evidence are unverified."""
import copy
import json
import shutil
import unittest
from unittest.mock import patch

import test_research_project as fixtures
from autoresearch import source_evidence_adapter
from autoresearch.project_controller import ProjectController
from autoresearch.research_project import ResearchProject


class ControllerSelectionTests(unittest.TestCase):
    setUp = fixtures.ResearchProjectTests.setUp
    bundle = fixtures.ResearchProjectTests.bundle
    assert_code = fixtures.ResearchProjectTests.assert_code

    def stage(self):
        folder, manifest = self.bundle()
        first = self.project.register_evidence(request_id="first-input", bundle=folder)
        other = self.root / "other-bundle"
        shutil.copytree(folder, other)
        manifest["selections"][0]["id"] = "other-selection"
        (other / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        second = self.project.register_evidence(request_id="second-input", bundle=other)
        return first, second

    @staticmethod
    def proposal(context, candidate=None):
        return {"schema_version": "project-selection-proposal-v1", "context_sha256": context["context_sha256"],
                "provider": {"kind": "operator_assistant", "label": "integration fixture"},
                "choice": {"kind": "execute", "candidate_id": candidate["id"]} if candidate else {"kind": "wait"},
                "rationale": "Read the later registered fixture, or wait without execution.",
                "evidence_citation_ids": []}

    def test_later_candidate_and_wait_replay_stay_frozen(self):
        first, second = self.stage()
        controller = ProjectController(self.project.root)
        before = self.project.status()
        context = controller.selection_context()
        self.assertEqual(self.project.status(), before)
        chosen = next(item for item in context["candidates"] if item["parameters"].get("receipt_snapshot_sha256") == second["receipt_snapshot_sha256"])
        self.assertEqual(context["baseline_decision"]["next_action"]["parameters"]["receipt_snapshot_sha256"], first["receipt_snapshot_sha256"])
        proposal = self.proposal(context, chosen)
        with patch.object(source_evidence_adapter, "execute", wraps=source_evidence_adapter.execute) as execute:
            accepted = controller.advance_selection(request_id="selected", proposal=proposal)
            replay = ProjectController(self.project.root).advance_selection(request_id="selected", proposal=proposal)
            execute.assert_called_once()
        self.assertEqual(accepted["child_request_id"], replay["child_request_id"])
        self.assertEqual(self.project.status()["evidence_actions"][-1]["receipt_snapshot_sha256"], second["receipt_snapshot_sha256"])
        context = controller.selection_context()
        waiting = self.proposal(context)
        self.assertEqual(controller.advance_selection(request_id="wait", proposal=waiting)["status"], "waiting")
        self.assertEqual(controller.advance_selection(request_id="wait", proposal=waiting)["status"], "waiting")
        self.assertEqual(self.project.status()["budget"]["evidence_reads_used"], 1)
        bad = copy.deepcopy(waiting); bad["rationale"] = "changed"
        self.assert_code("IDEMPOTENCY_CONFLICT", controller.advance_selection, request_id="wait", proposal=bad)

    def test_stale_context_and_injected_parameters_do_not_create_requests(self):
        self.stage()
        controller = ProjectController(self.project.root)
        context = controller.selection_context()
        proposal = self.proposal(context, context["candidates"][0])
        controller.advance_selection(request_id="wait-first", proposal=self.proposal(context))
        before = self.project.status()
        self.assert_code("STALE_SELECTION_CONTEXT", controller.advance_selection, request_id="stale", proposal=proposal)
        current = controller.selection_context()
        forged = self.proposal(current, current["candidates"][0]); forged["choice"]["parameters"] = {"command": "arbitrary"}
        self.assert_code("INVALID_SELECTION_PROPOSAL", controller.advance_selection, request_id="forged", proposal=forged)
        self.assertEqual(self.project.status(), before)

    def test_saved_result_recovery_and_unknown_never_extract_twice(self):
        self.stage()
        controller = ProjectController(self.project.root)
        context = controller.selection_context(); proposal = self.proposal(context, context["candidates"][0])
        with patch.object(source_evidence_adapter, "execute", wraps=source_evidence_adapter.execute) as execute:
            with patch.object(ResearchProject, "_commit_result", side_effect=KeyboardInterrupt):
                with self.assertRaises(KeyboardInterrupt):
                    controller.advance_selection(request_id="recover", proposal=proposal)
            self.assertEqual(ProjectController(self.project.root).advance_selection(request_id="recover", proposal=proposal)["status"], "completed")
            execute.assert_called_once()
        context = controller.selection_context(); proposal = self.proposal(context, context["candidates"][0])
        with patch.object(source_evidence_adapter, "execute", side_effect=KeyboardInterrupt) as execute:
            with self.assertRaises(KeyboardInterrupt):
                controller.advance_selection(request_id="unknown", proposal=proposal)
            self.assertEqual(controller.advance_selection(request_id="unknown", proposal=proposal)["status"], "unknown")
            blocked = controller.selection_context()
            forged = self.proposal(blocked, context["candidates"][0])
            self.assert_code("SELECTION_BLOCKED", controller.advance_selection, request_id="bypass", proposal=forged)
            execute.assert_called_once()
        self.assertEqual(self.project.status()["budget"]["evidence_reads_reserved"], 1)


if __name__ == "__main__":
    unittest.main()
