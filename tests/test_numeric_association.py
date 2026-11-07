"""Pairwise arithmetic and the existing saved-project/controller execution path."""

import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from autoresearch import method_registry as registry, numeric_association_adapter as numeric, tabular_quality_adapter as tabular
from autoresearch.contracts import ResearchError, canonical, fingerprint
from autoresearch.project_controller import ProjectController
from autoresearch.research_project import ResearchProject


class NumericAssociationTests(unittest.TestCase):
    def payload(self, text, **changes):
        root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        spec = {"schema_version": "tabular-quality-spec-v1", "file": "data.csv", "dataset_label": "Arithmetic fixture",
                "source_url": "urn:test:numeric-association", "license_note": "Fixture only", "sample_unit": "declared_record",
                "group_columns": ["group"], "key_columns": [], "numeric_columns": ["x", "outcome"],
                "target_column": "outcome", "target_unit": "declared_unit", "missing_tokens": ["", "NA"],
                "delimiter": ",", "provenance": {"origin_sha256": "a" * 64, "description": "Unverified fixture declaration"}}
        spec.update(changes)
        (root / spec["file"]).write_text(text, encoding="utf-8", newline="")
        (root / "spec.json").write_text(json.dumps(spec), encoding="utf-8")
        return tabular.capture_source(root)

    def parameters(self):
        return {"based_on_action_id": "action-quality", "based_on_result_sha256": "b" * 64}

    def test_pairwise_missing_constants_and_group_coordinates(self):
        payload = self.payload('group,x,outcome,constant,note\na,1,2,7,"two\nlines"\na,2,4,7,n\na,3,6,7,n\n'
                               'b,1,6,7,n\nb,2,4,7,n\nb,3,2,7,n\n,4,8,7,n\nNA,5,10,7,n\n'
                               'a,,12,7,n\na,NA,14,7,n\na,bad,16,7,n\na,NaN,18,7,n\na,inf,20,7,n\na,7,NA,7,n\n',
                               numeric_columns=["x", "constant", "outcome"])
        original = copy.deepcopy(payload)
        envelope = numeric.execute(payload, self.parameters())
        result = envelope["result"]
        self.assertEqual(result["summary"], {"rows": 14, "complete_group_rows": 12, "incomplete_group_rows": 2, "group_count": 2})
        first, second = result["groups"]
        self.assertEqual(first["group_id"], "group-" + fingerprint(["a"]))
        self.assertEqual(first["first_coordinate"], {"logical_record": 1, "physical_line_end": 3})
        self.assertEqual({key: value for key, value in first["associations"][0].items() if key != "pearson_r"},
                         {"predictor": "x", "n": 3, "excluded": 6, "reason": None})
        self.assertAlmostEqual(first["associations"][0]["pearson_r"], 1.0)
        self.assertAlmostEqual(second["associations"][0]["pearson_r"], -1.0)
        self.assertEqual((result["overall"][0]["n"], result["overall"][0]["excluded"]), (8, 6))
        self.assertAlmostEqual(result["overall"][0]["pearson_r"], 79 / 111)
        self.assertEqual(result["overall"][1]["reason"], "constant_predictor")
        self.assertEqual(result["incomplete_group"]["associations"][0],
                         {"predictor": "x", "n": 2, "excluded": 0, "pearson_r": None, "reason": "insufficient_pairs"})
        self.assertEqual(result["predecessor"], self.parameters())
        self.assertEqual(result["scope"]["input_contract"], "tabular-quality-v1")
        self.assertEqual(envelope["observations"][0]["kind"], "numeric_association")
        self.assertEqual(envelope["observations"][0]["overall"], result["overall"])
        self.assertEqual((envelope["new_fits"], envelope["model_calls"], envelope["scientific_validation"]), (0, 0, False))
        self.assertEqual(numeric.next_decision(envelope)["project_status"], "waiting")
        self.assertEqual(payload, original)
        self.assertTrue(all(set(group) == {"group_id", "rows", "first_coordinate", "associations"} for group in result["groups"]))
        json.dumps(envelope, allow_nan=False)
        for text, reason in (("1,4\n2,4\n3,4\n", "constant_target"), ("2,4\n2,4\n2,4\n", "constant_both"),
                             ("1,2\n2,4\n", "insufficient_pairs")):
            with self.subTest(reason=reason):
                value = numeric.execute(self.payload("x,outcome\n" + text, group_columns=[]), self.parameters())["result"]
                self.assertEqual(value["overall"][0]["reason"], reason)
                self.assertIsNone(value["overall"][0]["pearson_r"])
        value = numeric.execute(self.payload("x,outcome\n-1e308,1e308\n0,0\n1e308,-1e308\n", group_columns=[]), self.parameters())["result"]
        self.assertAlmostEqual(value["overall"][0]["pearson_r"], -1.0)

    def test_quality_predecessor_controller_and_original_request_replay(self):
        payload = self.payload("group,x,outcome\na,1,2\na,2,4\na,3,6\nb,4,8\nb,5,10\nb,6,12\n")
        root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        source = root / "captured" / "source.json"
        source.parent.mkdir()
        source.write_text(canonical(payload), encoding="utf-8")
        project = ResearchProject(root / "project")
        initial = project.create(source=source, goal="Describe saved numeric association", budget_ref="fixture:original", max_tool_calls=2,
                                 method_id=tabular.TOOL_ID)
        controller = ProjectController(project.root)
        before = next(option for option in project.method_options()["options"] if option["method_id"] == numeric.TOOL_ID)
        self.assertEqual(before["condition"], "uncertain")
        quality = controller.advance(request_id="quality", expected_state_version=initial["state_version"])
        self.assertEqual(quality["status"], "completed")
        state = project.status()
        self.assertEqual(state["actions"][0]["observations"][0]["profile"]["flags"], [])
        candidate = next(item for item in controller.selection_context()["candidates"] if item["method_id"] == numeric.TOOL_ID)
        self.assertEqual(candidate["evaluation_ref"], "numeric-association-v1")
        self.assertEqual(candidate["parameters"], {"based_on_action_id": state["actions"][0]["id"],
                                                 "based_on_result_sha256": state["actions"][0]["result_sha256"]})
        association = controller.advance(request_id="association", expected_state_version=state["state_version"])
        self.assertEqual(association["status"], "completed")
        completed = project.status()
        self.assertEqual(completed["actions"][-1]["command"], numeric.TOOL_ID)
        self.assertEqual(completed["actions"][-1]["method_instance"]["evaluation_ref"], registry.evaluation_ref(numeric.TOOL_ID))
        self.assertEqual(completed["actions"][-1]["observations"][0]["predecessor"], candidate["parameters"])
        self.assertEqual((completed["budget"]["local_tool_calls_used"], completed["budget"]["new_fits"],
                          completed["budget"]["new_model_requests"], completed["budget"]["evidence_reads_used"]), (2, 0, 0, 0))
        self.assertEqual(completed["budget"]["lineage_ref"], "fixture:original")
        with patch.object(numeric, "execute", side_effect=AssertionError("Original request must not execute again")):
            replay = ProjectController(project.root).advance(request_id="association", expected_state_version=state["state_version"])
            direct = ResearchProject(project.root).step(request_id=completed["actions"][-1]["request_id"],
                method_id=numeric.TOOL_ID, parameters=candidate["parameters"], expected_state_version=0)
        self.assertEqual(replay["status"], "completed")
        self.assertTrue(direct["replayed"])
        self.assertEqual(project.status(), completed)
        self.assertFalse(any(item["method_id"] == numeric.TOOL_ID for item in controller.selection_context()["candidates"]))
        absent = self.payload("group,x,outcome\na,1,2\n", target_column=None, target_unit=None)
        with self.assertRaises(ResearchError) as caught:
            numeric.execute(absent, self.parameters())
        self.assertEqual(caught.exception.code, "UNSUPPORTED_SCOPE")


if __name__ == "__main__":
    unittest.main()
