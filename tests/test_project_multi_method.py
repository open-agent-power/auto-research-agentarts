"""Necessary continuing-project lineage, allowance and no-redispatch checks."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import test_tabular_quality_adapter as tabular_fixtures
from autoresearch import grouped_quality_adapter, tabular_quality_adapter
from autoresearch.contracts import ResearchError, canonical
from autoresearch.project_controller import ProjectController
from autoresearch.project_selection_view import selection_view
from autoresearch.research_project import ResearchProject


class ProjectMultiMethodTests(unittest.TestCase):
    capture = tabular_fixtures.TabularQualityAdapterTests.capture

    def project(self, limit=1):
        payload, _ = self.capture("id,batch,x,y\na,G,0,1\nb,G,2,0\nc,H,4,5\n")
        root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        (root / "input").mkdir()
        packet = root / "input/source.json"
        packet.write_text(canonical(payload), encoding="utf-8")
        project = ResearchProject(root / "project")
        project.create(source=packet, method_id=tabular_quality_adapter.TOOL_ID,
                       goal="Locate grouped zeros while retaining unknown scientific qualification.",
                       budget_ref="test-only-no-model-no-cash", max_tool_calls=limit)
        return project

    def error(self, code, callback, **kwargs):
        with self.assertRaises(ResearchError) as caught:
            callback(**kwargs)
        self.assertEqual(caught.exception.code, code)

    def test_same_project_second_method_shared_limit_and_exact_replay(self):
        project = self.project()
        primary = project.step(request_id="quality")
        before = project.status()
        task_ref = copy.deepcopy(before["evidence_task_ref"])
        controller = ProjectController(project.root)
        self.assertFalse(controller.next()["executable"])
        self.assertEqual(controller.selection_context()["candidates"], [])
        revision = dict(request_id="extend", expected_limit=1, new_limit=2,
                        reason="Inspect the saved grouped zero feedback once.", expected_state_version=before["state_version"])
        project.extend_local_budget(**revision)
        extended = project.status()
        self.assertEqual(project.extend_local_budget(**revision)["old_limit"], 1)
        self.assertEqual(project.status()["snapshot_ref"], extended["snapshot_ref"])
        self.error("IDEMPOTENCY_CONFLICT", project.extend_local_budget, **dict(revision, reason="changed"))
        context = controller.selection_context()
        choice = next(c for c in context["candidates"] if c["method_id"] == grouped_quality_adapter.TOOL_ID)
        self.assertEqual(choice["parameters"]["based_on_result_sha256"], primary["result_sha256"])
        self.assertNotEqual(choice["evaluation_ref"], primary["method_instance"]["evaluation_ref"])
        proposal = {"schema_version": "project-selection-proposal-v1", "context_sha256": context["context_sha256"],
                    "provider": {"kind": "operator_assistant", "label": "Test operator declaration"},
                    "choice": {"kind": "execute", "candidate_id": choice["id"]},
                    "rationale": "Saved zero counts qualify this bounded grouping inspection; target remains unknown.",
                    "evidence_citation_ids": []}
        with patch.object(tabular_quality_adapter, "execute", wraps=tabular_quality_adapter.execute) as old_tool, \
             patch.object(grouped_quality_adapter, "execute", wraps=grouped_quality_adapter.execute) as tool:
            result = controller.advance_selection(request_id="grouped", proposal=proposal,
                                                  expected_state_version=context["state_version"])
            state = project.status()
            replay = controller.advance_selection(request_id="grouped", proposal=proposal,
                                                  expected_state_version=context["state_version"])
            self.assertEqual(replay["child_request_id"], result["child_request_id"])
            self.assertEqual(project.status()["snapshot_ref"], state["snapshot_ref"])
            reused = project.step(request_id="reuse-grouped", method_id=choice["method_id"], parameters=choice["parameters"])
            self.assertEqual(reused["id"], state["actions"][1]["id"])
            self.assertTrue(reused["reused"])
            self.assertEqual(project.step(request_id="quality")["id"], primary["id"])
            old_tool.assert_not_called()
            tool.assert_called_once()
        self.assertEqual((state["id"], state["run_id"]), (before["id"], before["run_id"]))
        self.assertEqual(state["evidence_task_ref"], task_ref)
        self.assertTrue(set(before["next_decision"]["next_action"]["required_evidence"]).issubset(
            state["next_decision"]["retained_unresolved_requirements"]))
        self.assertEqual(state["budget"]["local_tool_calls_used"], 2)
        self.assertEqual(state["registration"]["max_tool_calls"], 1)
        for key in ("existing_cash_cap_cny", "cash_settlement", "model_requests_allowed", "evidence_read_limit", "historical_spend_cny"):
            self.assertEqual(state["budget"][key], before["budget"][key])
        self.assertEqual(len(selection_view(state)["records"]), 1)
        self.assertFalse(controller.next()["executable"])

    def test_predecessor_and_artifact_guards_precede_new_dispatch(self):
        project = self.project(limit=2)
        params = {"based_on_action_id": "action-absent", "based_on_result_sha256": "0" * 64}
        self.error("CONDITION_NOT_SATISFIED", project.step, request_id="too-early",
                   method_id=grouped_quality_adapter.TOOL_ID, parameters=params)
        primary = project.step(request_id="quality")
        params = {"based_on_action_id": primary["id"], "based_on_result_sha256": primary["result_sha256"]}
        self.error("CONDITION_NOT_SATISFIED", project.step, request_id="forged-result",
                   method_id=grouped_quality_adapter.TOOL_ID, parameters=dict(params, based_on_result_sha256="0" * 64))
        self.error("INVALID_REQUEST", project.step, request_id="extra-parameter",
                   method_id=grouped_quality_adapter.TOOL_ID, parameters=dict(params, delete_zero=True))
        before = project.status()
        artifact = project.root / primary["artifact"]
        value = json.loads(artifact.read_bytes())
        value["tool_result"]["result"]["profile"]["rows"] += 1
        artifact.write_text(canonical(value), encoding="utf-8")
        self.error("EVIDENCE_CHANGED", project.step, request_id="changed-artifact",
                   method_id=grouped_quality_adapter.TOOL_ID, parameters=params)
        self.assertEqual(project.status()["snapshot_ref"], before["snapshot_ref"])

    def test_unknown_followup_blocks_new_work_and_allowance_change(self):
        project = self.project(limit=2)
        project.step(request_id="quality")
        controller = ProjectController(project.root)
        with patch.object(grouped_quality_adapter, "execute", side_effect=KeyboardInterrupt) as tool:
            with self.assertRaises(KeyboardInterrupt):
                controller.advance(request_id="interrupted")
            self.assertEqual(controller.advance(request_id="interrupted")["status"], "unknown")
            self.assertFalse(controller.next()["executable"])
            self.assertIsNone(controller.advance(request_id="do-not-bypass")["child_request_id"])
            self.error("EXECUTION_UNKNOWN", project.extend_local_budget, request_id="no-extension",
                       expected_limit=2, new_limit=3, reason="Cannot bypass unknown execution.")
            tool.assert_called_once()
        state = project.status()
        self.assertEqual((state["budget"]["local_tool_calls_used"], state["budget"]["local_tool_calls_reserved"]), (1, 1))
        self.assertEqual(state["budget"]["local_tool_call_limit"], 2)


if __name__ == "__main__":
    unittest.main()
