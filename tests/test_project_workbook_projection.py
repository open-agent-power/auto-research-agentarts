"""Two captured-origin/controller checks; all input and workspaces are disposable."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from test_chemotopo_data import cells, workbook
import test_tabular_quality_adapter as tabular_fixtures
from autoresearch import tabular_quality_adapter as tabular, workbook_projection_adapter as projection
from autoresearch.contracts import ResearchError, canonical
from autoresearch.project_controller import ProjectController
from autoresearch.project_report import collect_report, _markdown
from autoresearch.research_project import ResearchProject


class ProjectWorkbookProjectionTests(unittest.TestCase):
    capture = tabular_fixtures.TabularQualityAdapterTests.capture

    def prepare(self, limit=2):
        self.book = workbook({"Original": cells(["id", "x"], [["a", 0], ["b", 2]])})
        self.digest = hashlib.sha256(self.book).hexdigest()
        payload, _ = self.capture("id,x\na,0\nb,2\n", group_columns=[], key_columns=["id"],
                                  numeric_columns=["x"], target_column=None, target_unit=None,
                                  provenance={"origin_sha256": self.digest, "description": "Fixture declaration, unconfirmed conversion"})
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        (self.root / "input").mkdir()
        source = self.root / "input/source.json"
        source.write_text(canonical(payload), encoding="utf-8")
        project = ResearchProject(self.root / "project")
        project.create(source=source, goal="Check captured workbook candidate projections.",
                       budget_ref="fixture only; no providers", max_tool_calls=limit, method_id=tabular.TOOL_ID)
        project.step(request_id="quality")
        state = project.status()
        self.task = copy.deepcopy(state["evidence_task_ref"])
        self.required = copy.deepcopy(state["next_decision"]["next_action"]["required_evidence"])
        bundle = self.root / "bundle"
        (bundle / "sources").mkdir(parents=True)
        (bundle / "sources/origin.xlsx").write_bytes(self.book)
        manifest = {"schema_version": "project-evidence-bundle-v1", "task_ref": self.task,
                    "contributor": {"role": "operator_assistant", "label": "Explicit temporary fixture"},
                    "sources": [{"id": "original", "path": "sources/origin.xlsx", "sha256": self.digest,
                                 "url": "urn:fixture:original", "media_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                 "license_note": "Constructed fixture, not author data"}],
                    "selections": [{"id": "header", "source_id": "original", "locator": {"kind": "xlsx_cell", "value": "Original!A1:B3"},
                                    "claim": "Fixture workbook cells; not confirmed acquisition"}],
                    "remaining_questions": ["Actual acquisition and conversion still unconfirmed."]}
        (bundle / "manifest.json").write_text(canonical(manifest), encoding="utf-8")
        self.registration = project.register_evidence(request_id="capture-origin", bundle=bundle,
                                                     expected_state_version=state["state_version"])
        return project

    def error(self, code, callback, **kwargs):
        with self.assertRaises(ResearchError) as caught:
            callback(**kwargs)
        self.assertEqual(caught.exception.code, code)

    def test_actual_captured_origin_drives_controller_replay_and_report_without_source_extraction(self):
        project = self.prepare()
        controller = ProjectController(project.root)
        context = controller.selection_context()
        choice = next(item for item in context["candidates"] if item["method_id"] == projection.TOOL_ID)
        self.assertEqual(choice["parameters"]["origin_receipt_sha256"], self.registration["receipt_snapshot_sha256"])
        proposal = {"schema_version": "project-selection-proposal-v1", "context_sha256": context["context_sha256"],
                    "provider": {"kind": "operator_assistant", "label": "Explicit fixture selection"},
                    "choice": {"kind": "execute", "candidate_id": choice["id"]},
                    "rationale": "Compare captured origin caches without approving the declared conversion.", "evidence_citation_ids": []}
        with patch.object(projection, "execute", wraps=projection.execute) as tool:
            result = controller.advance_selection(request_id="projection", proposal=proposal,
                                                  expected_state_version=context["state_version"])
            state = project.status()
            replay = controller.advance_selection(request_id="projection", proposal=proposal,
                                                  expected_state_version=context["state_version"])
            self.assertEqual(tool.call_count, 1)
        self.assertEqual(result["child_request_id"], replay["child_request_id"])
        self.assertEqual(project.status(), state)
        self.assertEqual(state["budget"]["local_tool_calls_used"], 2)
        self.assertEqual((state["budget"]["evidence_reads_used"], state["budget"]["new_model_requests"], state["budget"]["new_fits"]), (0, 0, 0))
        self.assertEqual(state["evidence_task_ref"], self.task)
        self.assertEqual(state["knowledge_refs"], [])
        action = state["actions"][-1]
        self.assertEqual(action["method_instance"]["input_bindings"]["origin_source_id"], "original")
        observed = action["observations"][0]
        self.assertEqual(observed["summary"]["exact_candidate_sheets"], ["Original"])
        self.assertEqual(observed["scope"]["conversion_status"], "unconfirmed")
        for requirement in self.required:
            self.assertIn(requirement, state["next_decision"]["next_action"]["required_evidence"])
        report = collect_report(project.root)
        markdown = _markdown(report)
        self.assertIn("工作簿候选投影核对", markdown)
        self.assertIn(self.digest, markdown)
        self.assertIn("Original", markdown)
        self.assertFalse(observed["scientific_validation"])

    def test_explicit_upgrade_preserves_budget_and_rejects_foreign_binding_or_changed_origin(self):
        project = self.prepare(limit=1)
        with project._connect() as con:
            old = project._project(con)
            old.pop("source_provenance")
            for entry in old["evidence_sources"]:
                entry.pop("source_metadata")
            old["code_identity"] = "0" * 64
            project._save(con, old)
        before = project.status()
        source_bytes = (project.root / "source.json").read_bytes()
        project.upgrade(request_id="upgrade", expected_code_identity=before["code_identity"])
        upgraded = project.status()
        self.assertEqual(upgraded["budget"], before["budget"])
        self.assertEqual(upgraded["actions"], before["actions"])
        self.assertEqual((project.root / "source.json").read_bytes(), source_bytes)
        self.assertEqual(upgraded["source_provenance"]["origin_sha256"], self.digest)
        option = next(item for item in project.method_options()["options"] if item["method_id"] == projection.TOOL_ID)
        self.assertEqual(option["condition"], "satisfied")
        parameters = option["parameters"]
        self.error("BUDGET_EXHAUSTED", project.step, request_id="no-budget", method_id=projection.TOOL_ID,
                   parameters=parameters, expected_state_version=upgraded["state_version"])
        self.assertEqual(project.status(), upgraded)
        project.extend_local_budget(request_id="fixture-allowance", expected_limit=1, new_limit=2,
                                    reason="One disposable integration check", expected_state_version=upgraded["state_version"])
        allowed = project.status()
        with patch.object(projection, "execute", side_effect=AssertionError("Invalid input must not dispatch")):
            for key, value in (("based_on_result_sha256", "f" * 64), ("origin_receipt_sha256", "e" * 64), ("origin_source_id", "foreign")):
                self.error("CONDITION_NOT_SATISFIED", project.step, request_id="wrong-" + key, method_id=projection.TOOL_ID,
                           parameters={**parameters, key: value}, expected_state_version=allowed["state_version"])
                self.assertEqual(project.status(), allowed)
            asset = project.root / "evidence-inputs" / parameters["origin_receipt_sha256"] / (self.digest + ".bin")
            asset.write_bytes(b"changed original fixture")
            self.error("EVIDENCE_CHANGED", project.step, request_id="changed", method_id=projection.TOOL_ID,
                       parameters=parameters, expected_state_version=allowed["state_version"])
        self.assertEqual(project.status(), allowed)


if __name__ == "__main__":
    unittest.main()
