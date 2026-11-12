"""Saved diagnostics verify original evidence and describe it without new execution."""

from contextlib import ExitStack, closing, redirect_stdout
import copy
import csv
import io
import json
from pathlib import Path
import runpy
import shutil
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from sklearn.linear_model import Ridge
from sklearn.preprocessing import StandardScaler

from autoresearch import source_evidence_adapter, tabular_quality_adapter as tabular
from autoresearch.contracts import ResearchError, canonical, fingerprint
from autoresearch.project_controller import ProjectController
from autoresearch.project_design import bind
from autoresearch.research_design import RAW_RESOURCE
from autoresearch.research_project import ResearchProject
from autoresearch.saved_oof_diagnostics import _within_group, inspect_saved_oof


class SavedOOFDiagnosticsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # One real 3-fold fixture for the entire suite: 3 scaler + 3 Ridge fits.
        cls.fixture = tempfile.TemporaryDirectory()
        root = Path(cls.fixture.name)
        inputs = root / "inputs"
        inputs.mkdir()
        stream = io.StringIO(newline="")
        writer = csv.writer(stream)
        writer.writerow(["group", "unused_group", "age", "x", "y"])
        for index in range(24):
            age = index if index < 21 else (index - 13) * 10
            writer.writerow(["" if index == 4 else "C" if index == 23 else "A" if index < 12 else "B",
                             "two\nlines" if index == 0 else str(index), "" if index == 2 else age,
                             index % 3, "" if index == 3 else 2 * index + index % 3])
        (inputs / "data.csv").write_bytes(stream.getvalue().encode("utf-8"))
        spec = {"schema_version": "tabular-quality-spec-v1", "file": "data.csv", "dataset_label": "Saved diagnostic fixture",
                "source_url": "urn:test:saved-diagnostic", "license_note": "Constructed fixture", "sample_unit": "declared record",
                "group_columns": ["group", "unused_group"], "key_columns": [], "numeric_columns": ["age", "x", "y"],
                "target_column": "y", "target_unit": "fixture unit", "missing_tokens": [""], "delimiter": ",",
                "provenance": {"origin_sha256": "a" * 64, "description": "Constructed fixture only"}}
        (inputs / "spec.json").write_text(canonical(spec), encoding="utf-8")
        source = inputs / "source.json"
        source.write_text(canonical(tabular.capture_source(inputs)), encoding="utf-8")
        project = ResearchProject(root / "project")
        project.create(source=source, goal="Read complete saved OOF evidence", budget_ref="test:saved-diagnostic",
                       max_tool_calls=5, method_id=tabular.TOOL_ID)
        cls.resource = {**copy.deepcopy(RAW_RESOURCE), "checks": ["group_cv"]}
        cls.training = {"feature_columns": ["age", "x"], "split_group_columns": ["group"], "fit_limit": 6}
        bind(project, request_id="initial-binding", expected_state_version=0, resource=cls.resource,
             prediction_column=None, training=cls.training, reason="Fixed fixture declaration")
        controller = ProjectController(project.root)
        controller.advance(request_id="fixture-quality")
        controller.advance(request_id="fixture-oof")
        cls.action_id = project.status()["actions"][-1]["id"]
        # An explicit historical action stays readable after a subsequent binding.
        resource = {**copy.deepcopy(cls.resource), "version": 2, "parent_version": 1, "change_reason": "Keep original evidence"}
        bind(project, request_id="later-binding", expected_state_version=project.status()["state_version"], resource=resource,
             prediction_column=None, training=cls.training, reason="Historical reader fixture")

    @classmethod
    def tearDownClass(cls):
        cls.fixture.cleanup()

    def setUp(self):
        root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.project = ResearchProject(root / "project")
        shutil.copytree(Path(self.fixture.name) / "project", self.project.root)
        self.cli = runpy.run_path(str(Path(__file__).parents[1] / "scripts/inspect_saved_oof.py"))

    @staticmethod
    def files(root):
        return {str(path.relative_to(root)): path.read_bytes() for path in root.rglob("*") if path.is_file()}

    def forbid_execution(self):
        stack = ExitStack()
        self.enterContext(stack)
        for target, name in ((Ridge, "fit"), (StandardScaler, "fit"), (source_evidence_adapter, "execute"), (tabular, "execute")):
            stack.enter_context(patch.object(target, name, side_effect=AssertionError("Reader must never execute or fit")))
        stack.enter_context(patch("autoresearch.local_workbench.LocalWorkbench.__init__",
                                  side_effect=AssertionError("Reader must not construct LocalWorkbench")))

    def read(self, columns=("age", "x")):
        return inspect_saved_oof(self.project.root, self.action_id, columns)

    def rewrite(self, change, action_change=None):
        state = self.project.status()
        action = copy.deepcopy(next(item for item in state["actions"] if item["id"] == self.action_id))
        artifact = self.project._artifact(action)
        envelope = json.loads(artifact.read_bytes())
        change(envelope["tool_result"]["result"]["analysis"])
        envelope["sha256"] = fingerprint({key: value for key, value in envelope.items() if key != "sha256"})
        action["result_sha256"] = envelope["sha256"]
        if action_change:
            action_change(action)
        artifact.write_text(canonical(envelope), encoding="utf-8")
        with closing(sqlite3.connect(self.project.db)) as connection, connection:
            connection.execute("UPDATE actions SET record=? WHERE request_id=?", (canonical(action), action["request_id"]))

    def test_original_mapping_exclusions_historical_binding_and_no_mutation(self):
        state, files = self.project.status(), self.files(self.project.root)
        self.forbid_execution()
        result = self.read()
        self.assertEqual(result["schema_version"], "saved-oof-diagnostics-v1")
        self.assertEqual((result["input_n"], len(result["rows"]), result["excluded"]), (24, 21, 3))
        self.assertEqual([row["logical_record"] for row in result["exclusions"]], [3, 4, 5])
        self.assertEqual(result["rows"][0]["physical_line_end"], 3)
        self.assertEqual(result["rows"][0]["input_values"], {"age": 0.0, "x": 0.0})
        self.assertEqual(result["group_columns"], ["group"])
        self.assertEqual(result["group_weighted"]["group_count"], 3)
        self.assertEqual(result["provenance"]["design_binding"]["version"], 1)
        self.assertEqual(state["design_revisions"][-1]["version"], 2)
        self.assertEqual(result["provenance"]["action"]["id"], self.action_id)
        self.assertFalse(result["scientific_validation"])
        self.assertEqual(result["validation"]["fit_calls"], 0)
        self.assertEqual(self.project.status(), state)
        self.assertEqual(self.files(self.project.root), files)

    def test_weighting_full_group_and_fold_membership(self):
        result = self.read()
        rows, groups = result["rows"], result["groups"]
        mean = lambda values: sum(values) / len(values)
        self.assertAlmostEqual(result["row_weighted"]["candidate_mae"], mean([abs(row["residual"]) for row in rows]))
        self.assertAlmostEqual(result["row_weighted"]["mean_error"], mean([row["residual"] for row in rows]))
        self.assertAlmostEqual(result["group_weighted"]["candidate_mae"], mean([group["candidate_mae"] for group in groups]))
        self.assertAlmostEqual(result["group_weighted"]["reference_mae"], mean([group["reference_mae"] for group in groups]))
        self.assertNotAlmostEqual(result["row_weighted"]["candidate_mae"], result["group_weighted"]["candidate_mae"])
        self.assertEqual(sorted(index for group in groups for index in group["logical_records"]), [row["logical_record"] for row in rows])
        self.assertEqual([group["n"] for group in groups], [9, 11, 1])
        self.assertEqual([item["row_weighted"]["n"] for item in result["group_strata"]], [1, 20])
        self.assertEqual([item["group_weighted"]["group_count"] for item in result["group_strata"]], [1, 2])
        by_id = {row["logical_record"]: row for row in rows}
        for fold in result["folds"]:
            self.assertEqual(set(fold["train_records"]) | set(fold["test_records"]), set(by_id))
            self.assertEqual(fold["train_n"] + fold["test_n"], 21)
            self.assertEqual(fold["test_group_count"], 1)
            self.assertEqual(fold["train_group_count"], 2)
            self.assertTrue(all(by_id[index]["fold"] == fold["fold"] for index in fold["test_records"]))

    def test_profiles_exact_continuous_boundaries_empty_bins_and_complete_coverage(self):
        result = self.read()
        continuous, exact = result["input_profiles"]
        self.assertEqual(exact["grouping"], "exact_values")
        self.assertEqual([bucket["value"] for bucket in exact["buckets"]], [0, 1, 2])
        self.assertEqual(continuous["grouping"], "equal_width")
        buckets = continuous["buckets"]
        self.assertEqual([bucket["n"] for bucket in buckets], [17, 1, 0, 0, 3])
        self.assertEqual(buckets[1]["logical_records"], [21])  # age20 enters [20,40)
        self.assertEqual(buckets[4]["logical_records"], [22, 23, 24])  # age80 and100 included
        for bucket in buckets[2:4]:
            self.assertIsNone(bucket["candidate_mae"])
            self.assertIsNone(bucket["reference_mae"])
            self.assertIsNone(bucket["mean_error"])
            self.assertEqual((bucket["fold_count"], bucket["group_count"]), (0, 0))
        for profile in result["input_profiles"]:
            self.assertEqual(sorted(index for bucket in profile["buckets"] for index in bucket["logical_records"]),
                             [row["logical_record"] for row in result["rows"]])
            for bucket in profile["buckets"]:
                self.assertEqual(sum(fold["n"] for fold in bucket["fold_counts"]), bucket["n"])
                self.assertEqual(sum(group["n"] for group in bucket["group_membership"]), bucket["n"])

    def test_optional_columns_and_invalid_untrained_columns(self):
        self.assertEqual(self.read(())["input_profiles"], [])
        self.assertTrue(all(row["input_values"] == {} for row in self.read(())["rows"]))
        self.assertEqual(self.read(("x", "x"))["requested_columns"], ["x"])
        for column in ("y", "unused_group", "unknown"):
            with self.subTest(column=column), self.assertRaises(ResearchError) as caught:
                self.read((column,))
            self.assertEqual(caught.exception.code, "INVALID_DIAGNOSTIC_COLUMN")

    def test_within_group_preserves_default_output_and_all_noncomparable_source_rows(self):
        self.forbid_execution()
        files, state = self.files(self.project.root), self.project.status()
        default = self.read(())
        explicit_none = inspect_saved_oof(self.project.root, self.action_id, (), within_group_column=None)
        self.assertEqual(json.dumps(default), json.dumps(explicit_none))
        self.assertEqual(self.cli["diagnostic_markdown"](default), self.cli["diagnostic_markdown"](explicit_none))
        self.assertNotIn("within_group", default)
        result = inspect_saved_oof(self.project.root, self.action_id, (), within_group_column="age")
        within = result.pop("within_group")
        self.assertEqual(json.dumps(result), json.dumps(default))
        self.assertEqual(within["group_columns"], ["group"])
        self.assertEqual((within["summary"]["group_count"], within["summary"]["row_count"]), (3, 21))
        self.assertEqual(within["summary"]["comparable_group_count"], 0)
        self.assertEqual(within["pair_summaries"], [])
        self.assertEqual([group["reason_codes"] for group in within["groups"]],
                         [["varying_other_features"], ["varying_other_features"], ["singleton"]])
        self.assertEqual([group["varying_other_features"] for group in within["groups"]], [["x"], ["x"], []])
        self.assertEqual(sorted(record for group in within["groups"] for level in group["levels"] for record in level["logical_records"]),
                         [row["logical_record"] for row in result["rows"]])
        self.assertTrue(all(group["adjacent_pairs"] == [] for group in within["groups"]))
        self.assertEqual(self.files(self.project.root), files)
        self.assertEqual(self.project.status(), state)

    def test_within_group_rejects_invalid_column_and_missing_declared_groups(self):
        self.forbid_execution()
        for column in ("y", "group", "unused_group", "unknown", "", [], 1):
            with self.subTest(column=column), self.assertRaises(ResearchError) as caught:
                inspect_saved_oof(self.project.root, self.action_id, within_group_column=column)
            self.assertEqual(caught.exception.code, "INVALID_DIAGNOSTIC_COLUMN")
        # Deliberately remove the saved declaration in all three binding locations:
        # this tests the explicit preflight refusal, without pretending the old OOF
        # was generated under a different model or running another estimator.
        state = self.project.status()
        action = next(item for item in state["actions"] if item["id"] == self.action_id)
        binding = copy.deepcopy(action["design_binding"])
        binding["training"]["split_group_columns"] = []
        self.rewrite(lambda value: (value.update(design_binding=binding), value["protocol"].update(split_group_columns=[])),
                     lambda saved: saved.update(design_binding=binding))
        with closing(sqlite3.connect(self.project.db)) as connection, connection:
            project = json.loads(connection.execute("SELECT record FROM project").fetchone()[0])
            project["design_revisions"][0] = binding
            connection.execute("UPDATE project SET record=?", (canonical(project),))
        with self.assertRaises(ResearchError) as caught:
            inspect_saved_oof(self.project.root, self.action_id, within_group_column="age")
        self.assertEqual(caught.exception.code, "NO_DECLARED_DIAGNOSTIC_GROUPS")

    def test_corrupt_documented_inputs_rejected_even_with_matching_artifact_fingerprint(self):
        cases = {
            "observed": lambda value: value["oof"][0].update(observed=999),
            "physical": lambda value: value["oof"][0].update(physical_line_end=2),
            "groups": lambda value: value["oof"][0].update(groups=["different"]),
            "duplicate": lambda value: value["oof"].append(copy.deepcopy(value["oof"][0])),
            "omit": lambda value: value["oof"].pop(),
            "exclusion": lambda value: value["exclusions"][0].update(reasons=["different"]),
            "fold_assignment": lambda value: value["oof"][0].update(fold=99),
            "fold_reference": lambda value: value["folds"][0].update(reference_prediction=999),
            "fold_partition": lambda value: value["folds"][0]["train_records"].pop(),
            "summary": lambda value: value["summary"].update(candidate_mae=999),
            "training": lambda value: value["protocol"].update(feature_columns=["x"]),
            "binding": lambda value: value["design_binding"].update(reason="changed"),
        }
        originals = self.files(self.project.root)
        self.forbid_execution()
        for label, change in cases.items():
            with self.subTest(case=label):
                self.rewrite(change)
                with self.assertRaises(ResearchError):
                    self.read()
                for name, raw in originals.items():
                    (self.project.root / name).write_bytes(raw)

    def test_source_snapshot_and_original_bytes_rejected(self):
        self.rewrite(lambda value: None, lambda action: action.update(source_snapshot_sha256="b" * 64))
        with self.assertRaises(ResearchError):
            self.read()
        source = self.project.root / "source.json"
        source.write_bytes(source.read_bytes() + b" ")
        with self.assertRaises(ResearchError):
            self.read()

    def test_group_cv_rejects_group_leakage_even_when_fold_partition_and_reference_match(self):
        def leak(analysis):
            left, right = analysis["folds"][:2]
            left["test_records"][0], right["test_records"][0] = right["test_records"][0], left["test_records"][0]
            by_id = {row["logical_record"]: row for row in analysis["oof"]}
            for fold in analysis["folds"]:
                fold["train_records"] = sorted(set(by_id) - set(fold["test_records"]))
                mean = sum(by_id[index]["observed"] for index in fold["train_records"]) / len(fold["train_records"])
                fold["reference_prediction"] = mean
                for index in fold["test_records"]:
                    by_id[index].update(fold=fold["fold"], reference_prediction=mean)
        self.rewrite(leak)
        with self.assertRaisesRegex(ResearchError, "Declared groups cross"):
            self.read()

    def test_changed_unhashed_artifact_and_incomplete_action_rejected_without_execution(self):
        self.forbid_execution()
        action = next(item for item in self.project.status()["actions"] if item["id"] == self.action_id)
        artifact = self.project._artifact(action)
        raw = artifact.read_bytes()
        envelope = json.loads(raw)
        envelope["tool_result"]["result"]["analysis"]["oof"][0]["predicted"] += 1
        artifact.write_text(canonical(envelope), encoding="utf-8")
        with self.assertRaises(ResearchError) as caught:
            self.read()
        self.assertEqual(caught.exception.code, "EVIDENCE_CHANGED")
        artifact.write_bytes(raw)
        self.rewrite(lambda value: None, lambda action: action.update(status="unknown"))
        with self.assertRaises(ResearchError) as caught:
            self.read()
        self.assertEqual(caught.exception.code, "NO_ELIGIBLE_OOF_ACTION")

    def test_explicit_action_selection_missing_ineligible_and_not_computable(self):
        state = self.project.status()
        for selected in (None, "missing", state["actions"][0]["id"]):
            with self.subTest(selected=selected), self.assertRaises(ResearchError) as caught:
                inspect_saved_oof(self.project.root, selected)
            self.assertEqual(caught.exception.code, "NO_ELIGIBLE_OOF_ACTION")
        self.rewrite(lambda value: value["summary"].update(status="not_computable"))
        with self.assertRaises(ResearchError) as caught:
            self.read()
        self.assertEqual(caught.exception.code, "NO_ELIGIBLE_OOF_ACTION")

    def test_cli_outputs_complete_tables_without_execution_and_rejects_existing_or_internal_output(self):
        self.forbid_execution()
        files = self.files(self.project.root)
        output = self.project.root.parent / "diagnostic"
        args = ["--workspace", str(self.project.root), "--action-id", self.action_id, "--column", "age", "--column", "x"]
        with redirect_stdout(io.StringIO()) as stdout:
            code = self.cli["main"]([*args, "--output", str(output)])
        self.assertEqual(code, 0, stdout.getvalue())
        result = json.loads((output / "diagnostic.json").read_text(encoding="utf-8"))
        self.assertEqual(result, self.read())
        markdown = (output / "diagnostic.md").read_text(encoding="utf-8")
        self.assertIn("完整折表", markdown)
        self.assertIn("完整输入表", markdown)
        for bucket in result["input_profiles"][0]["buckets"]:
            self.assertIn(self.cli["_cell"](bucket["label"]), markdown)
        for destination in (output, self.project.root / "internal", self.project.root.parent):
            with self.subTest(destination=str(destination)), redirect_stdout(io.StringIO()) as stdout:
                self.assertEqual(self.cli["main"]([*args, "--output", str(destination)]), 2)
                self.assertFalse(json.loads(stdout.getvalue())["ok"])
        self.assertEqual(self.files(self.project.root), files)

    def test_cli_within_group_flag_is_optional_readonly_and_retains_fresh_output_contract(self):
        self.forbid_execution()
        files = self.files(self.project.root)
        output = self.project.root.parent / "within-diagnostic"
        args = ["--workspace", str(self.project.root), "--action-id", self.action_id,
                "--within-group-column", "age", "--output", str(output)]
        with redirect_stdout(io.StringIO()) as stdout:
            self.assertEqual(self.cli["main"](args), 0, stdout.getvalue())
        result = json.loads((output / "diagnostic.json").read_text(encoding="utf-8"))
        self.assertEqual(result, inspect_saved_oof(self.project.root, self.action_id, within_group_column="age"))
        self.assertEqual(result["requested_columns"], [])
        self.assertTrue(all(row["input_values"] == {} for row in result["rows"]))
        markdown = (output / "diagnostic.md").read_text(encoding="utf-8")
        for text in ("组内相邻输入对照：age", "完整相邻输入对类型", "其他训练输入变化 2 组 / 20 行", "单行组 1 组 / 1 行"):
            self.assertIn(text, markdown)
        with redirect_stdout(io.StringIO()) as stdout:
            self.assertEqual(self.cli["main"](args), 2)
        self.assertEqual(json.loads(stdout.getvalue())["code"], "EVIDENCE_CONFLICT")
        self.assertEqual(self.files(self.project.root), files)


class WithinGroupArithmeticTests(unittest.TestCase):
    """Frozen raw-input/OOF arithmetic examples; these are not fitted project evidence."""

    @staticmethod
    def projection(samples):
        rows, inputs = [], {}
        for record, (labels, age, x, fold, observed, predicted) in enumerate(samples, 1):
            rows.append({"logical_record": record, "groups": labels, "fold": fold,
                         "observed": observed, "predicted": predicted, "reference_prediction": 3.0,
                         "input_values": {}})
            inputs[record] = {"age": age, "x": x}
        return _within_group(rows, inputs, {"feature_columns": ["age", "x"],
                                           "split_group_columns": ["batch", "kind"]}, "age")

    def test_repeated_raw_levels_sorted_adjacency_and_exact_pair_equal_group_averages(self):
        result = self.projection([
            (["A", "one"], 40, 7, 1, 15, 19),
            (["A", "one"], 10, 7, 1, 0, 1), (["A", "one"], 20, 7, 1, 8, 10),
            (["A", "one"], 10, 7, 1, 4, 7), (["A", "one"], 20, 7, 1, 10, 14),
            (["A", "one"], 20, 7, 1, 12, 15),
            (["A", "two"], 20, 9, 2, 16, 19), (["A", "two"], 10, 9, 2, 20, 15),
            (["B", "one"], 40, 2, 3, 5, 6), (["B", "one"], 10, 2, 3, 5, 5),
        ])
        self.assertFalse(result["scientific_validation"])
        self.assertEqual(result["group_columns"], ["batch", "kind"])
        summary = result["summary"]
        self.assertEqual((summary["comparable_group_count"], summary["comparable_row_count"],
                          summary["adjacent_pair_count"], summary["pair_type_count"]), (3, 10, 4, 3))
        group = result["groups"][0]
        self.assertEqual(group["fixed_other_features"], {"x": 7})
        self.assertEqual(group["fold"], 1)
        self.assertEqual([level["value"] for level in group["levels"]], [10, 20, 40])
        self.assertEqual([level["n"] for level in group["levels"]], [2, 3, 1])
        self.assertEqual([level["observed_mean"] for level in group["levels"]], [2, 10, 15])
        self.assertEqual([level["predicted_mean"] for level in group["levels"]], [4, 13, 19])
        self.assertEqual([level["reference_mean"] for level in group["levels"]], [3, 3, 3])
        self.assertEqual([level["candidate_mae"] for level in group["levels"]], [2, 3, 4])
        self.assertEqual([level["mean_error"] for level in group["levels"]], [2, 3, 4])
        self.assertEqual([(pair["low_value"], pair["high_value"]) for pair in group["adjacent_pairs"]], [(10, 20), (20, 40)])
        first = group["adjacent_pairs"][0]
        self.assertEqual((first["low_n"], first["high_n"]), (2, 3))
        self.assertEqual((first["low_logical_records"], first["high_logical_records"]), ([2, 4], [3, 5, 6]))
        self.assertEqual((first["observed_change"], first["predicted_change"], first["mean_error_change"]), (8, 9, 1))
        pairs = result["pair_summaries"]
        self.assertEqual([(pair["low_value"], pair["high_value"]) for pair in pairs], [(10, 20), (10, 40), (20, 40)])
        self.assertEqual((pairs[0]["group_count"], pairs[0]["low_n"], pairs[0]["high_n"]), (2, 3, 4))
        self.assertEqual((pairs[0]["mean_observed_change"], pairs[0]["mean_predicted_change"], pairs[0]["mean_error_change"]), (2, 6.5, 4.5))
        self.assertEqual((pairs[0]["observed_increase_groups"], pairs[0]["observed_decrease_groups"], pairs[0]["observed_tie_groups"]), (1, 1, 0))
        self.assertEqual(pairs[1]["observed_tie_groups"], 1)
        self.assertEqual(pairs[0]["group_membership"], [["A", "one"], ["A", "two"]])
        self.assertEqual(sorted(record for item in result["groups"] for level in item["levels"] for record in level["logical_records"]), list(range(1, 11)))

    def test_noncomparable_groups_keep_every_level_member_and_reason_without_contrasts(self):
        result = self.projection([
            (["D", "one"], 10, 1, 1, 1, 2),
            (["E", "one"], 10, 1, 1, 1, 2), (["E", "one"], 10, 1, 1, 2, 3),
            (["F", "one"], 10, 1, 1, 1, 2), (["F", "one"], 10, 2, 1, 2, 3),
            (["F", "one"], 20, 1, 1, 3, 4),
            (["G", "one"], 10, 1, 1, 1, 2), (["G", "one"], 20, 1, 2, 2, 3),
        ])
        groups = result["groups"]
        self.assertEqual([group["reason_codes"] for group in groups],
                         [["singleton"], ["single_input_level"], ["varying_other_features"], ["mixed_evaluation_folds"]])
        self.assertEqual(groups[2]["varying_other_features"], ["x"])
        self.assertEqual(groups[2]["fixed_other_features"], {})
        self.assertEqual(groups[3]["folds"], [1, 2])
        self.assertIsNone(groups[3]["fold"])
        self.assertEqual([len(group["levels"]) for group in groups], [1, 1, 2, 2])
        self.assertTrue(all(group["status"] == "not_comparable" and group["adjacent_pairs"] == [] for group in groups))
        self.assertEqual(result["pair_summaries"], [])
        self.assertEqual((result["summary"]["noncomparable_group_count"], result["summary"]["noncomparable_row_count"]), (4, 8))
        self.assertEqual(sorted(record for group in groups for level in group["levels"] for record in level["logical_records"]), list(range(1, 9)))


if __name__ == "__main__":
    unittest.main()
