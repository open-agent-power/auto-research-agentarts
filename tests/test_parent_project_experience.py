"""Explicit saved-parent cases retain complete arithmetic and adverse outcomes."""

import copy
import json
import math
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

from sklearn.linear_model import Ridge
from sklearn.preprocessing import StandardScaler

import test_group_only_design as fixtures
import test_project_experience as case_fixtures
from autoresearch.contracts import ResearchError, canonical, fingerprint
from autoresearch.project_design import MAX_RAW_RECORDS, bind
from autoresearch.project_experience import (PARENT_PROTOCOL, PROTOCOL, ProjectExperienceMemory,
    _checked_rows, _paired_payload, _result_scope, derive_project_observation, parse_bundle, summary, validate_bundle)
from autoresearch.research_memory import observation_id


class ParentProjectExperienceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Exactly two three-fold fixtures: six scaler and six Ridge fits in total.
        cls.fixture = fixtures.GroupOnlyDesignTests()
        cls.addClassCleanup(cls.fixture.doCleanups)
        cls.project, controller = cls.fixture.project(groups=3, fit_limit=12)
        controller.advance(request_id="paired-parent")
        cls.parent_action = cls.project.status()["actions"][-1]
        state = cls.project.status()
        resource = cls.fixture.resource(version=2)
        resource["comparison_kind"] = "fixed_input_basis"
        bind(cls.project, request_id="paired-log-bind", expected_state_version=state["state_version"],
             resource=resource, prediction_column=None, reason="One fixed mapping on identical saved folds",
             training={"feature_columns": ["speed", "shape"], "split_group_columns": ["group"],
                       "fit_limit": 12, "input_transforms": {"speed": "log1p"}})
        controller.advance(request_id="paired-child")
        cls.action = cls.project.status()["actions"][-1]
        cls.derived = derive_project_observation(cls.project.root, cls.action["id"], parent_action_id=cls.parent_action["id"])
        cls.entry = cls.derived["entries"][0]
        cls.bundle_value = {"schema_version": "project-experience-bundle-v1", "id": "paired-fixture", "version": 1,
            "record": cls.entry, "method_card": case_fixtures.ProjectExperienceTests.card(cls),
            "limitations": ["Constructed fixture; arithmetic only, not research validity."],
            "source_inclusion_status": "active_at_export", "scientific_validation": False}

    def setUp(self):
        self.enterContext(patch.object(Ridge, "fit", side_effect=AssertionError("No case refit")))
        self.enterContext(patch.object(StandardScaler, "fit", side_effect=AssertionError("No case refit")))

    def reject(self, value, code="EVIDENCE_CHANGED"):
        with self.assertRaises(ResearchError) as caught:
            validate_bundle(value)
        self.assertEqual(caught.exception.code, code)

    @staticmethod
    def rehash(record, *, recompute=False):
        provenance = record["provenance"]
        for action, artifact in ((provenance["action"], provenance["artifact"]),
                                 (provenance["parent"]["action"], provenance["parent"]["artifact"])):
            artifact["sha256"] = fingerprint({key: value for key, value in artifact.items() if key != "sha256"})
            action["result_sha256"] = artifact["sha256"]
        record["scope"]["inputs_sha256"] = _result_scope(provenance["artifact"], provenance["parent"])
        provenance["recomputation_scope"] = copy.deepcopy(record["scope"])
        if recompute:
            record["payload"] = _paired_payload(provenance["action"], provenance["artifact"],
                                                provenance["parent"], provenance["origin"])
        record["id"] = observation_id(record)

    def test_complete_readonly_roundtrip_keeps_both_actions_and_mapping(self):
        before = self.project.status()
        files = case_fixtures.ProjectExperienceTests.files(self.project.root)
        derived = derive_project_observation(self.project.root, self.action["id"], parent_action_id=self.parent_action["id"])
        self.assertEqual(derived, self.derived)
        self.assertEqual(derived["scope"]["protocol"], PARENT_PROTOCOL)
        memory = ProjectExperienceMemory(self.project.root.parent / "paired-memory")
        self.assertEqual(memory.import_project(self.project.root, self.action["id"], parent_action_id=self.parent_action["id"])["inserted"], 1)
        self.assertEqual(memory.import_project(self.project.root, self.action["id"], parent_action_id=self.parent_action["id"])["inserted"], 0)
        bundle = memory.export_case(self.derived["scope"], self.entry["id"], case_id="paired-fixture", version=1,
            method_card=case_fixtures.ProjectExperienceTests.card(self), limitations=self.bundle_value["limitations"])
        self.assertEqual(parse_bundle(canonical(bundle).encode("utf-8")), self.bundle_value)
        comparison = bundle["record"]["payload"]["saved_parent_comparison"]
        self.assertEqual(comparison["baseline_ref"]["action_id"], self.parent_action["id"])
        self.assertEqual(comparison["candidate_ref"]["model_input_terms"], ["log1p(speed)", "shape"])
        self.assertEqual(self.project.status(), before)
        self.assertEqual(case_fixtures.ProjectExperienceTests.files(self.project.root), files)

    def test_compact_summary_keeps_tradeoffs_and_both_producers_without_rows(self):
        compact = summary(self.bundle_value)
        pair = compact["observation"]["saved_parent_comparison"]
        row, group = pair["row_summary"], pair["group_summary"]
        self.assertEqual(row["n"], 12)
        self.assertEqual(sum(row[key] for key in ("improved_rows", "worsened_rows", "tied_rows")), 12)
        self.assertEqual(sum(group[key] for key in ("improved_groups", "worsened_groups", "tied_groups")), 3)
        for name in ("baseline", "candidate"):
            self.assertEqual(pair["prediction_ranges"][name]["negative_predictions"], pair["metrics"][name + "_negative_predictions"])
        self.assertEqual(compact["origin_evidence"]["parent_producer_code_identity"], self.parent_action["code_identity"])
        def keys(value):
            if isinstance(value, dict):
                return set(value).union(*(keys(item) for item in value.values()))
            return set().union(*(keys(item) for item in value)) if isinstance(value, list) else set()
        self.assertTrue({"artifact", "oof", "folds", "logical_record"}.isdisjoint(keys(compact)))
        self.assertFalse(compact["scientific_validation"])

    def test_cli_explicit_parent_uses_paired_protocol_without_a_fit(self):
        command = [sys.executable, str(Path(__file__).parents[1] / "scripts/project_experience.py"), "import-project",
            "--memory", str(self.project.root.parent / "cli-paired-memory"), "--workspace", str(self.project.root),
            "--action-id", self.action["id"], "--parent-action-id", self.parent_action["id"]]
        result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", check=True)
        imported = json.loads(result.stdout)
        self.assertEqual(imported["scope"], self.derived["scope"])
        self.assertEqual(imported["numerical_validation"]["fit_calls"], 0)

    def test_adverse_negative_and_worse_rows_remain_in_offline_case(self):
        value = copy.deepcopy(self.bundle_value)
        record = value["record"]
        analysis = record["provenance"]["artifact"]["tool_result"]["result"]["analysis"]
        analysis["oof"][0]["predicted"] = -10.0
        saved = analysis["summary"]
        saved["candidate_mae"] = math.fsum(abs(row["predicted"] - row["observed"]) for row in analysis["oof"]) / len(analysis["oof"])
        saved["improvement"] = 1 - saved["candidate_mae"] / saved["reference_mae"]
        saved["outperforms_reference"] = saved["candidate_mae"] < saved["reference_mae"]
        self.rehash(record, recompute=True)
        compact = summary(value)
        comparison = compact["observation"]["saved_parent_comparison"]
        self.assertGreaterEqual(comparison["row_summary"]["worsened_rows"], 1)
        self.assertEqual(comparison["prediction_ranges"]["candidate"]["predicted_min"], -10.0)
        self.assertGreaterEqual(comparison["prediction_ranges"]["candidate"]["negative_predictions"], 1)

    def test_ungrouped_saved_comparison_has_no_invented_group_summary(self):
        value = copy.deepcopy(self.bundle_value)
        record = value["record"]
        provenance = record["provenance"]
        for action, artifact in ((provenance["action"], provenance["artifact"]),
                                 (provenance["parent"]["action"], provenance["parent"]["artifact"])):
            action["command"] = artifact["tool_result"]["tool_id"] = "data.ridge-random-validation"
            analysis = artifact["tool_result"]["result"]["analysis"]
            analysis["check"] = "random_cv"
            for binding in (action["design_binding"], analysis["design_binding"]):
                binding["training"]["split_group_columns"] = []
                binding["resource"]["checks"] = ["random_cv"]
            analysis["protocol"]["split_group_columns"] = []
            analysis["summary"]["group_count"] = None
            for row in analysis["oof"]:
                row["groups"] = None
        self.rehash(record, recompute=True)
        record_method = provenance["action"]
        value["method_card"]["method_refs"] = [{"method_id": record_method["command"], "evaluation_ref": record_method["evaluation_ref"]}]
        self.assertIsNone(summary(value)["observation"]["saved_parent_comparison"]["group_summary"])

    def test_default_single_case_retains_original_payload_and_provenance_fields(self):
        single = derive_project_observation(self.project.root, self.action["id"])
        record = single["entries"][0]
        self.assertEqual(single["scope"]["protocol"], PROTOCOL)
        self.assertEqual(single["scope"]["inputs_sha256"], self.action["result_sha256"])
        self.assertNotIn("saved_parent_comparison", record["payload"])
        self.assertNotIn("parent", record["provenance"])
        self.assertNotIn("design_binding", record["provenance"]["action"])
        value = {**self.bundle_value, "record": record}
        self.assertEqual(validate_bundle(value), value)
        self.assertNotIn("saved_parent_comparison", summary(value)["observation"])

    def test_both_results_bind_scope_and_different_valid_parent_changes_entry_id(self):
        value = copy.deepcopy(self.bundle_value)
        record = value["record"]
        parent = record["provenance"]["parent"]
        parent["action_id"] = parent["action"]["id"] = parent["artifact"]["action_id"] = "another-saved-parent"
        self.rehash(record, recompute=True)
        self.assertNotEqual(record["scope"]["inputs_sha256"], self.entry["scope"]["inputs_sha256"])
        self.assertNotEqual(record["id"], self.entry["id"])
        self.assertEqual(validate_bundle(value), value)
        record["scope"]["inputs_sha256"] = record["provenance"]["artifact"]["sha256"]
        record["provenance"]["recomputation_scope"] = copy.deepcopy(record["scope"])
        record["id"] = observation_id(record)
        self.reject(value)

    def test_missing_same_or_unregistered_parent_never_falls_back(self):
        for parent_id in (self.action["id"], "absent-parent"):
            with self.assertRaises(ResearchError):
                derive_project_observation(self.project.root, self.action["id"], parent_action_id=parent_id)
        for parent in (None, {}):
            value = copy.deepcopy(self.bundle_value)
            value["record"]["provenance"]["parent"] = parent
            self.reject(value)

    def test_changed_tradeoff_counts_are_rejected_by_offline_recomputation(self):
        for section, field in (("row_summary", "worsened_rows"), ("group_summary", "worsened_groups"),
                               ("metrics", "relative_improvement")):
            value = copy.deepcopy(self.bundle_value)
            value["record"]["payload"]["saved_parent_comparison"][section][field] += 1
            self.reject(value)

    def test_rehashed_parent_false_mae_is_rejected(self):
        value = copy.deepcopy(self.bundle_value)
        record = value["record"]
        record["provenance"]["parent"]["artifact"]["tool_result"]["result"]["analysis"]["summary"]["candidate_mae"] += 1
        self.rehash(record)
        self.reject(value)

    def test_binding_mapping_and_saved_group_count_cannot_be_redeclared(self):
        for alteration in ("mapping", "group_count", "action_binding", "lineage"):
            value = copy.deepcopy(self.bundle_value)
            record = value["record"]
            action = record["provenance"]["action"]
            analysis = record["provenance"]["artifact"]["tool_result"]["result"]["analysis"]
            if alteration == "mapping":
                analysis["protocol"]["model_input_terms"] = ["speed", "shape"]
            elif alteration == "group_count":
                analysis["summary"]["group_count"] += 1
            elif alteration == "action_binding":
                action["design_binding"]["reason"] = "Changed binding"
            else:
                action["design_binding"]["resource"]["parent_version"] = None
                analysis["design_binding"]["resource"]["parent_version"] = None
            self.rehash(record)
            with self.assertRaises(ResearchError):
                validate_bundle(value)

    def test_online_historical_binding_is_checked_independently(self):
        state = self.project.status()
        state["design_revisions"][-1]["reason"] = "Another registered revision"
        with patch.object(type(self.project), "status", return_value=state):
            with self.assertRaises(ResearchError) as caught:
                derive_project_observation(self.project.root, self.action["id"], parent_action_id=self.parent_action["id"])
        self.assertEqual(caught.exception.code, "EVIDENCE_CHANGED")

    def test_parent_producer_is_independent_of_current_child_identity(self):
        value = copy.deepcopy(self.bundle_value)
        record = value["record"]
        parent = record["provenance"]["parent"]
        parent["action"]["code_identity"] = parent["artifact"]["code_identity"] = "e" * 64
        self.rehash(record, recompute=True)
        self.assertEqual(validate_bundle(value), value)
        self.assertEqual(summary(value)["origin_evidence"]["parent_producer_code_identity"], "e" * 64)
        self.assertEqual(summary(value)["origin_evidence"]["producer_code_identity"], self.action["code_identity"])

    def test_parent_producer_requires_an_original_hash_and_group_rows_match_declaration(self):
        for invalid in (None, "short-identity"):
            value = copy.deepcopy(self.bundle_value)
            record = value["record"]
            parent = record["provenance"]["parent"]
            parent["action"]["code_identity"] = parent["artifact"]["code_identity"] = invalid
            self.rehash(record)
            self.reject(value)
        value = copy.deepcopy(self.bundle_value)
        record = value["record"]
        analysis = record["provenance"]["artifact"]["tool_result"]["result"]["analysis"]
        analysis["oof"][0]["groups"] = None
        self.rehash(record)
        self.reject(value)

    def test_raw_row_boundary_is_complete_through_2048_not_trimmed_to_512(self):
        for size in (1030, MAX_RAW_RECORDS):
            analysis = {"oof": [{"logical_record": i, "physical_line_end": i + 1, "fold": 1, "groups": ["g"],
                "observed": float(i), "predicted": float(i), "reference_prediction": 1.0} for i in range(1, size + 1)],
                "exclusions": [], "summary": {"status": "computed", "input_n": size, "n": size, "excluded": 0}}
            self.assertEqual(len(_checked_rows(analysis)[0]), size)
        analysis["summary"]["input_n"] += 1
        with self.assertRaises(ResearchError):
            _checked_rows(analysis)
        analysis["oof"].append({**analysis["oof"][-1], "logical_record": MAX_RAW_RECORDS + 1})
        with self.assertRaises(ResearchError):
            _checked_rows(analysis)


if __name__ == "__main__":
    unittest.main()
