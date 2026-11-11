"""Research designs retain actual verification evidence across independent projects."""

import base64
import copy
from pathlib import Path
import tempfile
import unittest

from autoresearch.contracts import ResearchError, canonical
from autoresearch.local_workbench import LocalWorkbench
from autoresearch.project_controller import ProjectController
from autoresearch.prediction_checks import evaluate_prediction
from autoresearch.research_design import RESOURCE, _assessment
from autoresearch.project_report import collect_report


class ResearchDesignLibraryTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory())) / "manager"
        self.manager = LocalWorkbench(self.root)

    def create(self, name, csv):
        spec = {"schema_version": "tabular-quality-spec-v1", "file": "predictions.csv", "dataset_label": name,
                "source_url": "urn:test:" + name, "license_note": "Constructed engineering fixture",
                "sample_unit": "declared_record", "group_columns": ["batch"], "key_columns": [],
                "numeric_columns": ["observed", "predicted"], "target_column": "observed", "target_unit": "fixture_unit",
                "missing_tokens": ["", "NA"], "delimiter": ",", "provenance": {"origin_sha256": "a" * 64, "description": name}}
        result = self.manager.create({"request_id": name, "goal": "Verify saved predictions for " + name,
            "budget_ref": "isolated-design-fixture", "max_tool_calls": 8,
            "input": {"file_name": "predictions.csv", "csv_base64": base64.b64encode(csv).decode(),
                      "spec_base64": base64.b64encode(canonical(spec).encode()).decode()}})
        return result["project_id"]

    def command(self, request_id, **values):
        project, _ = self.manager.binding()
        return {"request_id": request_id, "project_id": project.status()["id"],
                "expected_state_version": project.status()["state_version"], **values}

    def bind(self, request_id, version):
        body = self.command(request_id, resource_id="saved-prediction-review", resource_version=version,
                            prediction_column="predicted", reason="Verify the saved candidate against its declared target.")
        return body, self.manager.bind_design(body)

    def step(self, request_id, method):
        project, _ = self.manager.binding()
        context = ProjectController(project.root).selection_context()
        candidate = next(item for item in context["candidates"] if item["method_id"] == method)
        return self.manager.advance(self.command(request_id, proposal={"schema_version": "project-selection-proposal-v1",
            "context_sha256": context["context_sha256"], "provider": {"kind": "human", "label": "Fixture observer"},
            "choice": {"kind": "execute", "candidate_id": candidate["id"]},
            "rationale": "Execute a qualified saved-prediction check.", "evidence_citation_ids": []}))

    def test_feedback_revision_and_second_project_reuse_keep_original_evidence(self):
        first = self.create("project-a", b"batch,observed,predicted\na,1,1\na,2,2\nb,10,10\nb,12,12\nc,20,20\nc,23,23\n")
        self.bind("bind-v1", 1)
        self.step("a-quality", "data.tabular-quality-audit")
        self.step("a-baseline", "data.prediction-baseline")
        before = copy.deepcopy(self.manager.binding()[0].status())
        body = self.command("improve", reason="The observed grouping requires group and exclusion checks.")
        improved = self.manager.improve_design(body)
        self.assertEqual(improved["resource"]["version"], 2)
        self.assertTrue(LocalWorkbench(self.root).improve_design(body)["replayed"])
        self.assertEqual(self.manager.binding()[0].status(), before)
        first_actions = before["actions"]
        self.bind("a-bind-next-version", 2)
        second = self.create("project-b", b"batch,observed,predicted\nx,2,2\nx,4,4\ny,16,16\ny,18,18\nz,30,30\nz,34,34\n")
        self.assertNotEqual(first, second)
        bind_body, _ = self.bind("b-bind-v2", 2)
        self.step("b-quality", "data.tabular-quality-audit")
        for check in ("baseline", "grouped", "sensitivity"):
            self.step("b-" + check, "data.prediction-" + check)
        view = LocalWorkbench(self.root).designs()
        self.assertEqual(view["assessment"]["status"], "review_ready")
        self.assertTrue(view["assessment"]["claim_supported"])
        version = next(item for item in view["resources"] if item["version"] == 2)
        original = next(item for item in view["resources"] if item["id"] == "saved-prediction-review" and item["version"] == 1)
        self.assertEqual(original["validation_evidence"][0]["project_id"], first)
        self.assertEqual(version["status"], "validated")
        self.assertEqual(version["validation_evidence"][0]["project_id"], second)
        budget = self.manager.binding()[0].status()["budget"]
        self.assertEqual(budget["new_fits"], 0)
        self.assertIn("预测", collect_report(self.manager.binding()[0].root)["title"])
        self.assertTrue(self.manager.bind_design(bind_body)["replayed"])
        self.manager.select({"request_id": "back-a", "project_id": first})
        self.assertEqual(self.manager.binding()[0].status()["actions"], first_actions)

    def test_catalog_browsing_and_missing_feedback_cannot_create_a_revision(self):
        self.assertIsNone(self.manager.designs()["project_id"])
        self.assertEqual(len(self.manager.designs()["resources"]), 2)
        self.create("empty-feedback", b"batch,observed,predicted\na,1,2\nb,2,1\nc,3,3\n")
        self.bind("no-result-bind", 1)
        body = self.command("no-feedback", reason="A candidate needs real feedback.")
        with self.assertRaises(ResearchError) as caught:
            self.manager.improve_design(body)
        self.assertEqual(caught.exception.code, "MISSING_FEEDBACK")
        self.assertEqual(len(self.manager.designs()["resources"]), 2)

    def test_partial_uncomputable_exclusion_does_not_approve_robustness(self):
        resource = {**RESOURCE, "checks": ["baseline", "grouped", "sensitivity"]}
        records = [evaluate_prediction([0, 2, 10, 10], [0, 2, 10, 10], groups=["a", "a", "b", "c"], check=check)
                   for check in resource["checks"]]
        self.assertIsNone(_assessment(resource, records, {"group_columns": ["batch"]})["claim_supported"])

    def test_import_replay_and_version_conflict_preserve_catalog(self):
        resource = {**copy.deepcopy(RESOURCE), "id": "team-method", "title": "Team verification design"}
        body = {"request_id": "import-method", "resource": resource}
        self.manager.import_design(body)
        self.assertIn("import-method", LocalWorkbench(self.root).designs()["completed_requests"])
        self.assertTrue(self.manager.import_design(body)["replayed"])
        self.manager.import_design({"request_id": "import-identical", "resource": resource})
        self.assertEqual(len(self.manager.designs()["resources"]), 3)
        with self.assertRaises(ResearchError) as caught:
            self.manager.import_design({"request_id": "overwrite-method", "resource": {**resource, "title": "Changed"}})
        self.assertEqual(caught.exception.code, "RESOURCE_CONFLICT")


if __name__ == "__main__":
    unittest.main()
