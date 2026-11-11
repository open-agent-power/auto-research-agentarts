"""Plan proposals use actual saved feedback and retain its host binding."""

import base64
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from autoresearch import research_plan_proposal as protocol
from autoresearch import host_selection_protocol, recipe_change_proposal, research_recipe
from autoresearch.contracts import ResearchError, canonical
from autoresearch.feature_comparison import compare_feature_checks
from autoresearch.host_model_selection import HostModelSelection
from autoresearch.local_workbench import LocalWorkbench
from autoresearch.plan_feedback import project_observations
from autoresearch.project_controller import ProjectController
from autoresearch.project_selection import seal_context, validate_proposal


class ResearchPlanProposalTests(unittest.TestCase):
    def setUp(self):
        root = Path(self.enterContext(tempfile.TemporaryDirectory())) / "workbench"
        manager = LocalWorkbench(root)
        spec = {"schema_version": "tabular-quality-spec-v1", "file": "readings.csv",
                "dataset_label": "Plan feedback fixture", "source_url": "urn:test:plan-feedback",
                "license_note": "Constructed development input", "sample_unit": "declared_record",
                "group_columns": ["batch"], "key_columns": [], "numeric_columns": ["reading"],
                "target_column": "reading", "target_unit": "declared_unit", "missing_tokens": ["", "NA"],
                "delimiter": ",", "provenance": {"origin_sha256": "a" * 64, "description": "Constructed input"}}
        manager.create({"request_id": "create-plan-feedback", "goal": "Identify information needed before group comparison",
                        "budget_ref": "plan-feedback-test-only", "max_tool_calls": 2,
                        "input": {"file_name": "readings.csv",
                                  "csv_base64": base64.b64encode(b"batch,reading\na,1\nb,\n").decode("ascii"),
                                  "spec_base64": base64.b64encode(canonical(spec).encode("utf-8")).decode("ascii")}})
        self.project, _ = manager.binding()

    def source_feedback(self, line_count=28, selection_count=1):
        self.project.step(request_id="quality-for-source-plan")
        folder = self.project.root.parent / "source-plan-bundle"
        (folder / "sources").mkdir(parents=True)
        line = ("dataset columns target unit group key independence duplicates numeric_columns missing_tokens "
                "group_columns reading batch original source definitions remain unverified. 研究资料 μ.\n")
        raw = (line * line_count * selection_count).encode("utf-8")
        (folder / "sources/source.txt").write_bytes(raw)
        document = {"schema_version": "project-evidence-bundle-v1", "task_ref": self.project.evidence_task()["task_ref"],
                    "contributor": {"role": "operator_assistant", "label": "Plan context fixture"},
                    "sources": [{"id": "fixture", "path": "sources/source.txt", "sha256": hashlib.sha256(raw).hexdigest(),
                                 "url": "urn:test:plan-source-context", "media_type": "text/plain", "license_note": "Constructed fixture"}],
                    "selections": [{"id": "definitions-" + str(index), "source_id": "fixture",
                                    "locator": {"kind": "text_lines", "value":
                                                f"{index * line_count + 1}-{(index + 1) * line_count}"},
                                    "claim": "Definitions remain unverified after extraction."}
                                   for index in range(selection_count)],
                    "remaining_questions": ["Confirm reading target unit and batch group independence."]}
        (folder / "manifest.json").write_text(canonical(document), encoding="utf-8")
        return self.project.attach_evidence(request_id="source-for-plan", bundle=folder)

    def legacy_context(self, selection, state=None):
        state = state or self.project.status()
        return {"schema_version": "research-plan-context-v1", "selection_context": copy.deepcopy(selection),
                "feedback": [{"action_id": action["id"], "request_id": action["request_id"],
                              "method_id": action["command"], "status": action["status"],
                              "observations": copy.deepcopy(action.get("observations", [])),
                              "next_decision": copy.deepcopy(action.get("next_decision")),
                              "failure": copy.deepcopy(action.get("failure")), "artifact_ref": action.get("artifact")}
                             for action in state["actions"] + state["evidence_actions"]]}

    def assert_decision_reference(self, reference, action, project_id):
        if action.get("next_decision") is None:
            self.assertIsNone(reference)
        else:
            self.assertEqual(reference, {"kind": "saved_action_record", "project_id": project_id,
                                         "action_id": action["id"], "request_id": action["request_id"],
                                         "field": "next_decision"})
            state = self.project.status()
            saved = next(item for item in state["actions"] + state["evidence_actions"]
                         if item["id"] == reference["action_id"] and item["request_id"] == reference["request_id"])
            self.assertEqual(state["id"], reference["project_id"])
            self.assertEqual(saved[reference["field"]], action["next_decision"])

    def assert_artifact_reference(self, reference, artifact_ref, field, original):
        self.assertEqual(reference["kind"], "action_artifact_field")
        self.assertEqual(reference["artifact_ref"], artifact_ref)
        self.assertEqual(reference["path"], field)
        value = json.loads((self.project.root / reference["artifact_ref"]).read_bytes())
        for key in reference["path"]:
            value = value[key]
        self.assertEqual(value, original)

    def saved_checks(self, fixed_basis=False):
        baseline = {"action_id": "saved-parent", "check": "group_cv", "status": "completed",
                    "source_snapshot_sha256": "a" * 64, "target_column": "reading", "target_unit": "declared_unit",
                    "design_binding": {"version": 1, "project_id": self.project.status()["id"],
                                       "training": {"feature_columns": ["speed"] if fixed_basis else ["shape", "speed"]},
                                       "resource": {"id": "plan-comparison-fixture", "version": 1,
                                                    "parent_version": None, "checks": ["group_cv"],
                                                    "title": "Saved parent fixture", "claim": "An unverified design claim"}},
                    "protocol": {"splitter": "GroupKFold", "n_splits": 2, "shuffle": False, "random_state": None,
                                 "ridge_alpha": 1.0, "preprocessing": "StandardScaler.fit on training rows only",
                                 "reference": "training-fold target mean", "split_group_columns": ["signature"],
                                 "feature_columns": ["speed"] if fixed_basis else ["shape", "speed"]},
                    "oof": [{"logical_record": index, "physical_line_end": index + 1, "observed": float(index),
                             "predicted": prediction, "groups": ["a" if index <= 2 else "b"],
                             "fold": 1 if index <= 2 else 2, "reference_prediction": 3.5 if index <= 2 else 1.5}
                            for index, prediction in enumerate([-1.0, 3.0, 2.0, 6.0], 1)],
                    "folds": [{"fold": fold, "train_records": train, "test_records": test,
                               "reference_prediction": reference, "model_params": {"alpha": 1.0, "fit_intercept": True}}
                              for fold, train, test, reference in [(1, [3, 4], [1, 2], 3.5), (2, [1, 2], [3, 4], 1.5)]]}
        candidate = copy.deepcopy(baseline)
        candidate["action_id"] = "saved-candidate"
        candidate["design_binding"]["version"] = 2
        candidate["design_binding"]["resource"].update(version=2, parent_version=1)
        candidate["design_binding"]["training"]["feature_columns"] = ["speed"]
        candidate["protocol"]["feature_columns"] = ["speed"]
        for row, prediction in zip(candidate["oof"], [0.0, 2.0, 4.0, 4.0]):
            row["predicted"] = prediction
        if fixed_basis:
            from autoresearch.input_basis import protocol as basis_protocol
            candidate["design_binding"]["resource"]["comparison_kind"] = "fixed_input_basis"
            candidate["design_binding"]["training"]["input_basis"] = "univariate_cubic"
            candidate["protocol"].update(basis_protocol(candidate["design_binding"]["training"]))
        return [baseline, candidate]

    @staticmethod
    def arguments(context):
        return {"plan": {"question": "Which readings need source information?", "basis": "Saved quality feedback",
                         "steps": "Inspect missing records before comparing the groups.",
                         "expected_feedback": "A source explanation determines the next comparison."},
                "reason": "Make the recorded data-quality issue determine the next step.",
                "feedback_action_ids": [item["action_id"] for item in context["feedback"]],
                "expected_improvement": "The next step addresses the observed information gap."}

    def test_context_reads_saved_feedback_without_advancing_and_retains_proposal_binding(self):
        initial = protocol.build_context(self.project)
        self.assertEqual(initial["schema_version"], "research-plan-context-v2")
        self.assertEqual(initial["saved_comparisons"], [])
        self.assertEqual(initial["remaining_questions"], [])
        initial_proposal = protocol.build_proposal(initial, self.arguments(initial), "Delegated fixture")
        self.assertEqual(initial_proposal["feedback_action_ids"], [])
        self.project.step(request_id="quality-for-plan")
        before = self.project.status()
        selection = ProjectController(self.project.root).selection_context()
        context = protocol.build_context(self.project)
        self.assertEqual(self.project.status(), before)
        self.assertEqual(context["selection_context"], selection)
        self.assertEqual(context["remaining_questions"], (before.get("next_decision") or {}).get("remaining_questions", []))
        action = before["actions"][0]
        feedback = context["feedback"][0]
        self.assertEqual(feedback["action_id"], action["id"])
        self.assertEqual(feedback["observations"], action["observations"])
        self.assert_decision_reference(feedback["next_decision"], action, before["id"])
        self.assertEqual(feedback["artifact_ref"], action["artifact"])
        self.assertIn(canonical(context), protocol.build_prompt(context)["prompt"])
        self.assertEqual(json.loads(protocol.build_prompt(context)["prompt"].split("\n", 1)[1]), context)
        response = canonical(self.arguments(context)).encode("utf-8")
        parsed = protocol.parse_host_response(response, "delegated")
        proposal = protocol.build_proposal(context, parsed["arguments"], "Delegated fixture")
        self.assertEqual(proposal["context_sha256"], context["selection_context"]["context_sha256"])
        self.assertEqual(protocol.validate_proposal(context, proposal), proposal)
        self.assertIsNone(parsed["reported_cost_usd"])
        envelope = {"type": "result", "subtype": "success", "is_error": False, "result": response.decode("utf-8"),
                    "modelUsage": {"declared-model": {}}, "usage": {"output_tokens": 5}, "total_cost_usd": 0.01}
        cli = protocol.parse_host_response(canonical(envelope).encode("utf-8"), "claude_cli")
        self.assertEqual(cli["arguments"], parsed["arguments"])
        self.assertEqual(cli["reported_models"], ["declared-model"])
        self.assertEqual(cli["reported_cost_usd"], 0.01)

    def test_rejects_unknown_feedback_changed_binding_and_oversized_context(self):
        self.project.step(request_id="quality-for-plan")
        context = protocol.build_context(self.project)
        arguments = self.arguments(context)
        for references in ([], ["unknown-action"]):
            invalid = {**arguments, "feedback_action_ids": references}
            with self.subTest(references=references), self.assertRaises(ResearchError) as caught:
                protocol.build_proposal(context, invalid, "Delegated fixture")
            self.assertEqual(caught.exception.code, "INVALID_PLAN_PROPOSAL")
        proposal = protocol.build_proposal(context, arguments, "Delegated fixture")
        proposal["context_sha256"] = "0" * 64
        with self.assertRaises(ResearchError) as caught:
            protocol.validate_proposal(context, proposal)
        self.assertEqual(caught.exception.code, "STALE_SELECTION_CONTEXT")
        changed = copy.deepcopy(context)
        changed["selection_context"]["goal"] = "Changed outside the frozen host context"
        with self.assertRaises(ResearchError) as caught:
            protocol.build_prompt(changed)
        self.assertEqual(caught.exception.code, "INVALID_SELECTION_CONTEXT")
        oversized = copy.deepcopy(context)
        oversized["feedback"][0]["observations"].append({"statement": "x" * protocol.MAX_CONTEXT_BYTES})
        with self.assertRaises(ResearchError) as caught:
            protocol.build_prompt(oversized)
        self.assertEqual(caught.exception.code, "INVALID_PLAN_CONTEXT")
        for invalid in ({key: value for key, value in context.items() if key != "saved_comparisons"},
                        {key: value for key, value in context.items() if key != "remaining_questions"},
                        {**context, "schema_version": "research-plan-context-v1"},
                        {**context, "saved_comparisons": [{"scientific_validation": True}]}):
            with self.subTest(schema=invalid["schema_version"]), self.assertRaises(ResearchError) as caught:
                protocol._context(invalid)
            self.assertEqual(caught.exception.code, "INVALID_PLAN_CONTEXT")
        with self.assertRaises(ResearchError):
            protocol.parse_host_response(b'{"plan":{},"plan":{}}', "delegated")

    def test_large_multiselection_feedback_uses_traceable_references_without_changing_saved_facts(self):
        source = self.source_feedback(line_count=90, selection_count=7)
        before = self.project.status()
        self.assertEqual(len(source["next_decision"]["knowledge_contexts"]), 4)
        files_before = {str(path.relative_to(self.project.root)): path.read_bytes()
                        for path in self.project.root.rglob("*") if path.is_file()}
        selection = ProjectController(self.project.root).selection_context()
        context = protocol.build_context(self.project)
        self.assertEqual(context["schema_version"], "research-plan-context-v2")
        self.assertEqual(context["selection_context"], selection)
        self.assertEqual(context["saved_comparisons"], [])
        self.assertTrue(before["next_decision"]["remaining_questions"])
        self.assertEqual(context["remaining_questions"], before["next_decision"]["remaining_questions"])
        self.assertEqual(protocol.MAX_CONTEXT_BYTES, 65536)
        self.assertLessEqual(len(canonical(context).encode("utf-8")), protocol.MAX_CONTEXT_BYTES)
        actions = {action["id"]: action for action in before["actions"] + before["evidence_actions"]}
        for feedback in context["feedback"]:
            action = actions[feedback["action_id"]]
            self.assertEqual(set(feedback), protocol.FEEDBACK_FIELDS)
            self.assert_decision_reference(feedback["next_decision"], action, before["id"])
            for key, original in (("request_id", action["request_id"]), ("method_id", action["command"]),
                                  ("status", action["status"]), ("failure", action.get("failure")),
                                  ("artifact_ref", action.get("artifact"))):
                self.assertEqual(feedback[key], original)
            for index, (projected, original) in enumerate(zip(feedback["observations"], action["observations"])):
                expected = copy.deepcopy(original)
                if original.get("kind") == "source_observed":
                    text = expected.pop("exact_text")
                    reference = projected["exact_text_ref"]
                    self.assertEqual(reference["characters"], len(text))
                    self.assertGreater(len(text.encode("utf-8")), reference["characters"])
                    self.assert_artifact_reference(reference, action["artifact"],
                                                   ["tool_result", "observations", index, "exact_text"], text)
                    expected["exact_text_ref"] = reference
                    self.assertEqual(projected["mapping_status"], "unresolved")
                    self.assertEqual(projected["submitted_claim"]["status"], "submitter_claim_unreviewed")
                    self.assertEqual(projected["interpretation_status"], "extraction_only_not_scientific_approval")
                self.assertEqual(projected, expected)
            self.assertEqual(len(feedback["observations"]), len(action["observations"]))
        artifact = json.loads((self.project.root / source["artifact"]).read_bytes())
        self.assertNotIn("next_decision", artifact)
        self.assertNotIn("next_decision", artifact["tool_result"])
        self.assertTrue(context["selection_context"]["evidence"])
        self.assertFalse(context["selection_context"]["scientific_validation"])
        original = self.legacy_context(selection, before)
        self.assertGreater(len(canonical(original).encode("utf-8")), 3 * protocol.MAX_CONTEXT_BYTES)
        with self.assertRaises(ResearchError) as caught:
            protocol._context(original)
        self.assertEqual(caught.exception.code, "INVALID_PLAN_CONTEXT")
        system = protocol.build_prompt(context)["system"]
        self.assertIn("original text is not included or established as model-read", system)
        self.assertIn("Only supplied excerpts are source text", system)
        self.assertEqual(self.project.status(), before)
        self.assertEqual({str(path.relative_to(self.project.root)): path.read_bytes()
                          for path in self.project.root.rglob("*") if path.is_file()}, files_before)

    def test_saved_design_resource_reference_retains_all_other_observation_data(self):
        record = self.saved_checks(fixed_basis=True)[1]
        observation = {"kind": "ridge_validation", "design_binding": record["design_binding"],
                       "protocol": record["protocol"], "scientific_validation": False,
                       "summary": {"candidate_mae": 0.5, "reference_mae": 1.75, "n": 4,
                                   "prediction_range": {"negative_predictions": 0, "minimum": 0.0, "maximum": 4.0}},
                       "usage": {"fit_attempts": 4, "ridge_fit_attempts": 2, "preprocessing_fit_attempts": 2}}
        artifact_ref = "artifacts/saved-resource-fixture.json"
        path = self.project.root / artifact_ref
        path.parent.mkdir(exist_ok=True)
        path.write_text(canonical({"tool_result": {"observations": [observation]}}), encoding="utf-8")
        before, original_bytes = copy.deepcopy(observation), path.read_bytes()
        state = self.project.status()
        projected, = project_observations([observation], artifact_ref)
        resource = observation["design_binding"]["resource"]
        reference = projected["design_binding"]["resource_ref"]
        self.assert_artifact_reference(reference, artifact_ref,
                                       ["tool_result", "observations", 0, "design_binding", "resource"], resource)
        expected = copy.deepcopy(observation)
        expected["design_binding"]["resource"] = {key: resource[key] for key in
                                                  ("id", "version", "parent_version", "title", "comparison_kind")}
        expected["design_binding"]["resource_ref"] = reference
        self.assertEqual(projected, expected)
        self.assertEqual(observation, before)
        self.assertEqual(path.read_bytes(), original_bytes)
        self.assertEqual(self.project.status(), state)
        projected["summary"]["candidate_mae"] = 999.0
        self.assertEqual(observation, before)

    def test_context_supplies_strict_parent_comparisons_without_diagnostic_tables(self):
        selection = ProjectController(self.project.root).selection_context()
        state = self.project.status()
        state["design_revisions"] = [{"version": 1}, {"version": 2}]
        questions = ["  Preserve the unresolved target definition exactly.\nIncluding its scope.  ", "原生船型编号仍未映射。"]
        state["next_decision"] = {"remaining_questions": copy.deepcopy(questions)}
        project_before = self.project.status()
        for case in ("matched_features", "matched_basis", "worse_candidate", "different_observation"):
            with self.subTest(case=case):
                records = self.saved_checks(fixed_basis=case == "matched_basis")
                if case == "different_observation":
                    records[1]["oof"][0]["observed"] = 999.0
                elif case == "worse_candidate":
                    for row, prediction in zip(records[1]["oof"], [-2.0, 4.0, 1.0, 7.0]):
                        row["predicted"] = prediction
                records_before = copy.deepcopy(records)
                strict, = compare_feature_checks(records)
                # Retain the actual strict comparison, but exercise the optional catalog-table boundary.
                with_profiles = {**strict, "input_profiles": [{"column": "speed", "rows": ["not plan context"]}]}
                by_version = {index: [record] for index, record in enumerate(records, 1)}
                with patch.object(self.project, "status", return_value=state), \
                        patch.object(ProjectController, "selection_context", return_value=copy.deepcopy(selection)), \
                        patch("autoresearch.research_design._records",
                              side_effect=lambda project, saved, revision: copy.deepcopy(by_version[revision["version"]])), \
                        patch("autoresearch.feature_comparison.compare_feature_checks", return_value=[with_profiles]) as compare:
                    context = protocol.build_context(self.project)
                compare.assert_called_once_with(records)
                self.assertEqual(context["saved_comparisons"], [strict])
                self.assertNotIn("input_profiles", context["saved_comparisons"][0])
                self.assertEqual(context["selection_context"], selection)
                self.assertEqual(context["remaining_questions"], questions)
                self.assertEqual(records, records_before)
                self.assertFalse(strict["scientific_validation"])
                if case == "different_observation":
                    self.assertEqual(strict["status"], "not_comparable")
                    self.assertEqual(strict["reason_codes"], ["OBSERVED_MISMATCH"])
                    self.assertNotIn("metrics", strict)
                else:
                    self.assertEqual(strict["matched_rows"], 4)
                    self.assertEqual(strict["metrics"]["baseline_mae"], 1.5)
                    self.assertEqual(strict["metrics"]["candidate_mae"], 2.5 if case == "worse_candidate" else 0.5)
                    self.assertEqual(strict["metrics"]["mae_change"], 1.0 if case == "worse_candidate" else -1.0)
                    self.assertEqual(strict["baseline_ref"]["action_id"], "saved-parent")
                    self.assertEqual(strict["candidate_ref"]["resource_version"], 2)
                    if case == "matched_basis":
                        self.assertEqual(strict["comparison_kind"], "fixed_input_basis")
                        self.assertEqual(strict["changed_protocol_fields"], ["input_basis", "model_input_terms"])
                prompt = protocol.build_prompt(context)
                self.assertIn(canonical(context), prompt["prompt"])
                self.assertIn("candidate MAE minus parent MAE", prompt["system"])
                self.assertIn("Noncomparable records support no numerical advantage", prompt["system"])
                context["saved_comparisons"][0]["baseline_ref"]["action_id"] = "changed in memory"
                self.assertEqual(strict["baseline_ref"]["action_id"], "saved-parent")
                context["remaining_questions"].append("Cannot change the retained questions")
                self.assertEqual(state["next_decision"]["remaining_questions"], questions)
        self.assertEqual(self.project.status(), project_before)

    def test_source_plan_context_freezes_and_replays_without_repeating_source_reads(self):
        self.source_feedback()
        before = self.project.status()
        context = protocol.build_context(self.project)
        journal = HostModelSelection(self.project.root)
        specification = {"request_id": "source-feedback-plan", "provider": "delegated", "purpose": "plan",
                         "expected_state_version": before["state_version"], "decision_limit": 1,
                         "cli_budget_usd": 0.1, "reason": "One protocol fixture; no model launch"}
        prepared = journal.prepare(**specification)
        self.assertEqual(prepared["context"], context)
        self.assertEqual(context["remaining_questions"], before["next_decision"]["remaining_questions"])
        saved = journal.directory / prepared["directory"] / "context.json"
        self.assertEqual(saved.read_bytes(), canonical(context).encode("utf-8"))
        response = self.project.root.parent / "source-plan-response.json"
        response.write_bytes(canonical(self.arguments(context)).encode("utf-8"))
        journal.import_response(request_id="source-feedback-plan", response_file=response)
        proposed = journal.consume(request_id="source-feedback-plan")
        self.assertEqual(proposed["status"], "proposed")
        self.assertEqual(proposed["context"], context)
        rejected = journal.reject_plan(request_id="source-feedback-plan", reason="Retain original route for this fixture.")
        host_before = journal.status()
        saved_bytes = saved.read_bytes()
        self.assertEqual(journal.prepare(**specification), rejected)
        self.assertEqual(journal.import_response(request_id="source-feedback-plan", response_file=response), rejected)
        self.assertEqual(journal.consume(request_id="source-feedback-plan"), rejected)
        self.assertEqual(journal.reject_plan(request_id="source-feedback-plan", reason=rejected["rejection_reason"]), rejected)
        self.assertEqual(journal.status(), host_before)
        self.assertEqual(self.project.status(), before)
        self.assertEqual(saved.read_bytes(), saved_bytes)
        self.assertEqual(protocol.build_context(self.project), context)

    def test_existing_bounded_source_context_keeps_its_original_feedback_representation(self):
        source = self.source_feedback(line_count=1)
        selection = ProjectController(self.project.root).selection_context()
        legacy = self.legacy_context(selection)
        self.assertEqual(set(legacy), {"schema_version", "selection_context", "feedback"})
        self.assertNotIn("saved_comparisons", legacy)
        self.assertEqual(legacy["schema_version"], "research-plan-context-v1")
        source_feedback = next(item for item in legacy["feedback"] if item["action_id"] == source["id"])
        self.assertIn("knowledge_contexts", source_feedback["next_decision"])
        self.assertIn("exact_text", source_feedback["observations"][0])
        self.assertLess(len(canonical(legacy).encode("utf-8")), protocol.MAX_CONTEXT_BYTES)
        frozen = canonical(legacy).encode("utf-8")
        legacy = json.loads(frozen)
        self.assertEqual(protocol._context(legacy), legacy)
        proposal = protocol.build_proposal(legacy, self.arguments(legacy), "Saved bounded source fixture")
        self.assertEqual(protocol.validate_proposal(legacy, proposal), proposal)
        self.assertIn(canonical(legacy), protocol.build_prompt(legacy)["prompt"])
        self.assertEqual(canonical(legacy).encode("utf-8"), frozen)

    def test_researcher_feedback_extends_context_without_becoming_tool_feedback(self):
        self.project.save_plan(request_id="plan-before-note", expected_state_version=0,
                               plan=self.arguments({"feedback": []})["plan"], reason="Record the initial route.")
        before = self.project.status()
        old_research = self.legacy_context(ProjectController(self.project.root).selection_context())
        old_selection = old_research["selection_context"]
        self.assertNotIn("researcher_feedback", old_selection)
        old_plan_proposal = protocol.build_proposal(old_research, self.arguments(old_research), "Protocol fixture")
        recipe = {"schema_version": "research-recipe-v1", "id": "note-contract", "version": 1,
                  "question": "Select the next eligible method.", "need": "next_check",
                  "scope_match": {"domain": "data", "contract": "tabular-quality-v1"},
                  "ordered_methods": [{"method_id": "data.tabular-quality-audit", "evaluation_ref": "tabular-quality-v1"}],
                  "on_no_match": "wait"}
        old_decision = research_recipe.compile_recipe(recipe, old_selection)
        # This failed record is a pure protocol fixture. No tool action is dispatched.
        old_recipe_research = copy.deepcopy(old_research)
        old_recipe_research["feedback"] = [{"action_id": "fixture-failed-action", "request_id": "fixture-request",
            "method_id": "fixture-method", "status": "failed", "observations": [], "next_decision": None,
            "failure": {"code": "PROTOCOL_FIXTURE_ONLY"}, "artifact_ref": None}]
        old_recipe_context = {"schema_version": "recipe-change-context-v1", "research_context": old_recipe_research,
                              "current_recipe": recipe, "improvement_goal": "Keep trace identities distinct."}
        candidate = dict(copy.deepcopy(recipe), version=2)
        recipe_arguments = {"candidate": candidate, "reason": "Protocol fixture", "feedback_action_ids": ["fixture-failed-action"],
                            "expected_improvement": "Preserve the intended evidence scope.", "validation_plan": "Check frozen bindings."}
        old_recipe_proposal = recipe_change_proposal.build_proposal(old_recipe_context, recipe_arguments, "Protocol fixture")
        comment = "  Preserve this self-reported statement exactly.\nIts interpretation remains unverified.  "
        note = self.project.record_feedback(request_id="user-note-context", expected_state_version=before["state_version"],
            author="Researcher fixture", comment=comment,
            next_step="Review the declared grouping before extending the research route.", action_id=None)
        current = self.project.status()
        research = protocol.build_context(self.project)
        selection = research["selection_context"]
        self.assertEqual(current["budget"], before["budget"])
        self.assertEqual(current["actions"], before["actions"])
        self.assertEqual(current["evidence_actions"], before["evidence_actions"])
        self.assertEqual(selection["researcher_feedback"], [note])
        self.assertEqual(note["comment"], comment)
        self.assertEqual(note["plan_version"], 1)
        self.assertEqual(note["content_trust"], "unverified_researcher_statement")
        self.assertEqual(research["feedback"], [])
        self.assertEqual(selection, seal_context({key: value for key, value in selection.items() if key != "context_sha256"}))
        self.assertNotEqual(selection["context_sha256"], old_selection["context_sha256"])
        self.assertIn(canonical(note), host_selection_protocol.build_prompt(selection)["prompt"])
        self.assertIn(canonical(note), protocol.build_prompt(research)["prompt"])
        recipe_context = copy.deepcopy(old_recipe_context)
        recipe_context["research_context"]["selection_context"] = selection
        self.assertIn(canonical(note), recipe_change_proposal.build_prompt(recipe_context)["prompt"])
        bad_plan_arguments = {**self.arguments(research), "feedback_action_ids": [note["id"]]}
        with self.assertRaises(ResearchError) as caught:
            protocol.build_proposal(research, bad_plan_arguments, "Protocol fixture")
        self.assertEqual(caught.exception.code, "INVALID_PLAN_PROPOSAL")
        with self.assertRaises(ResearchError) as caught:
            recipe_change_proposal.build_proposal(recipe_context,
                {**recipe_arguments, "feedback_action_ids": [note["id"]]}, "Protocol fixture")
        self.assertEqual(caught.exception.code, "INVALID_RECIPE_CHANGE_PROPOSAL")
        changed = copy.deepcopy(selection)
        changed["researcher_feedback"][0]["comment"] = "Changed outside the frozen context"
        proposal = {**old_decision["proposal"], "context_sha256": selection["context_sha256"]}
        with self.assertRaises(ResearchError) as caught:
            validate_proposal(changed, proposal)
        self.assertEqual(caught.exception.code, "INVALID_SELECTION_CONTEXT")
        validate_proposal(old_selection, old_decision["proposal"])
        self.assertEqual(research_recipe.compile_recipe(recipe, old_selection), old_decision)
        self.assertEqual(protocol.validate_proposal(old_research, old_plan_proposal), old_plan_proposal)
        self.assertEqual(recipe_change_proposal.validate_proposal(old_recipe_context, old_recipe_proposal), old_recipe_proposal)
        self.assertEqual(self.project.status(), current)


if __name__ == "__main__":
    unittest.main()
