"""Selected plan assertions use original response spans and frozen comparisons."""

import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import test_local_workbench as fixtures
import test_local_workbench_http as http_fixtures
from autoresearch import plan_fact_check, research_plan_proposal as protocol
from autoresearch.contracts import ResearchError, canonical
from autoresearch.host_model_selection import HostModelSelection
from autoresearch.local_workbench import LocalWorkbench


class PlanFactCheckTests(unittest.TestCase):
    serve = http_fixtures.LocalWorkbenchHTTPTests.serve
    request = http_fixtures.LocalWorkbenchHTTPTests.request
    session = http_fixtures.LocalWorkbenchHTTPTests.session

    def setUp(self):
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.manager = LocalWorkbench(self.root / "manager")
        body = fixtures.LocalWorkbenchTests.create_body(self, "create-fact-fixture")
        body["max_tool_calls"] = 1
        self.manager.create(body)
        self.project, _ = self.manager.binding()
        self.project.step(request_id="quality-fact-fixture")
        self.host = HostModelSelection(self.project.root)
        self.ref = {"check": "group_cv", "baseline_action_id": "fixture-parent", "candidate_action_id": "fixture-child"}
        self.comparison = {"schema_version": "feature-comparison-v1", "status": "comparable", "check": "group_cv",
            "baseline_ref": {"action_id": "fixture-parent"}, "candidate_ref": {"action_id": "fixture-child"},
            "metrics": {"baseline_mae": 3.680200622894369, "candidate_mae": 5.28581661484824,
                        "mae_change": 1.6056159919538713, "relative_improvement": -0.43628490848172885,
                        "baseline_negative_predictions": 2, "candidate_negative_predictions": 0},
            "scientific_validation": False}
        self.arguments = {"plan": {"question": "🧪 Candidate has lower MAE than the parent?",
            "basis": "Both versions beat the training mean MAE9.148626; that does not compare child with parent.",
            "steps": "Review candidate MAE5.2858, parent MAE3.6802 and2 negative parent predictions.",
            "expected_feedback": "Keep adverse rows and source uncertainty."},
            "reason": "Selected arithmetic fixture, not a new research or model result.",
            "feedback_action_ids": [self.project.status()["actions"][0]["id"]],
            "expected_improvement": "Correct the reference and retain the saved results."}

    @staticmethod
    def tree_bytes(root):
        return {str(path.relative_to(root)): path.read_bytes() for path in root.rglob("*") if path.is_file()}

    def saved_plan(self, *, comparisons=None, legacy=False, outcome=None, receive=True):
        context = protocol.build_context(self.project)
        context["saved_comparisons"] = copy.deepcopy([self.comparison] if comparisons is None else comparisons)
        if legacy:
            context = {key: value for key, value in context.items() if key not in {"saved_comparisons", "remaining_questions"}}
            context["schema_version"] = "research-plan-context-v1"
        specification = {"request_id": "fact-plan", "provider": "delegated", "purpose": "plan",
            "expected_state_version": self.project.status()["state_version"], "decision_limit": 1,
            "cli_budget_usd": 0.1, "reason": "One constructed frozen protocol fixture; no model launch"}
        with patch.object(protocol, "build_context", return_value=context):
            record = self.host.prepare(**specification)
            if receive:
                path = self.root / "response.json"
                path.write_text(canonical(self.arguments), encoding="utf-8")
                self.host.import_response(request_id="fact-plan", response_file=path)
                record = self.host.consume(request_id="fact-plan")
                self.assertEqual(record["status"], "proposed")
                if outcome == "applied":
                    record = self.host.adopt_plan(request_id="fact-plan")
                elif outcome == "rejected":
                    record = self.host.reject_plan(request_id="fact-plan", reason="Keep this adverse fixture plan out of adoption.")
        return record

    def body(self, assertion=None, *, field="plan.question", quote="Candidate has lower MAE than the parent?"):
        text = self.arguments["plan"][field[5:]] if field.startswith("plan.") else self.arguments[field]
        start = text.index(quote)
        return {"project_id": self.project.status()["id"], "host_request_id": "fact-plan",
                "claim": {"field": field, "start": start, "end": start + len(quote), "quote": quote,
                          "comparison": copy.deepcopy(self.ref),
                          "assertion": assertion or {"kind": "mae_order", "value": "candidate_lower"}}}

    def check_readonly(self, body):
        before, host_before = self.project.status(), self.host.status()
        files = self.tree_bytes(self.manager.root)
        result = self.manager.check_plan_fact(body)
        self.assertEqual(self.project.status(), before)
        self.assertEqual(self.host.status(), host_before)
        self.assertEqual(self.tree_bytes(self.manager.root), files)
        self.assertFalse(result["scientific_validation"])
        self.assertEqual(result["semantic_mapping"], "submitter_declared")
        self.assertEqual(result["coverage"], "selected_span_only")
        return result

    def assert_code(self, code, body):
        with self.assertRaises(ResearchError) as caught:
            self.manager.check_plan_fact(body)
        self.assertEqual(caught.exception.code, code)

    def test_order_contradiction_uses_parent_not_training_mean_and_unicode_codepoints(self):
        record = self.saved_plan()
        body = self.body()
        self.assertEqual(body["claim"]["start"], 2)  # emoji is one codepoint, not two UTF-16 units
        result = self.check_readonly(body)
        self.assertEqual((result["status"], result["actual"]), ("contradicted", "baseline_lower"))
        self.assertEqual(result["context_sha256"], record["context"]["selection_context"]["context_sha256"])
        self.assertEqual(result["response_sha256"], record["response_sha256"])
        self.assertEqual(result["comparison_status"], "comparable")
        self.assertEqual(result["saved_metrics"], self.comparison["metrics"])
        self.assertIsNot(result["saved_metrics"], self.comparison["metrics"])
        body["claim"]["assertion"]["value"] = "baseline_lower"
        self.assertEqual(self.check_readonly(body)["status"], "supported")
        # Mapping a different sentence does not magically verify its semantics.
        selected = self.body(field="plan.basis", quote=self.arguments["plan"]["basis"])
        self.assertEqual(self.check_readonly(selected)["status"], "contradicted")

    def test_original_crlf_and_lone_cr_with_emoji_keep_exact_codepoint_spans(self):
        self.arguments["plan"]["basis"] = "🧪首行\r\n第二行父版MAE更低\r尾行"
        self.saved_plan()
        quote = "第二行父版MAE更低\r尾行"
        body = self.body({"kind": "mae_order", "value": "baseline_lower"}, field="plan.basis", quote=quote)
        self.assertEqual(body["claim"]["start"], 5)
        result = self.check_readonly(body)
        self.assertEqual(result["status"], "supported")
        self.assertEqual(result["quote_span"]["quote"], quote)
        body["claim"]["quote"] = quote.replace("\r", "\n")
        self.assert_code("INVALID_PLAN_FACT_CHECK", body)

    def test_displayed_decimal_precision_and_exact_counts(self):
        self.saved_plan()
        for metric, value, expected in [("candidate_mae", "5.2858", "supported"),
                                         ("candidate_mae", "5.28", "contradicted"),
                                         ("candidate_mae", "5.2857", "contradicted"),
                                         ("candidate_mae", "5.29", "supported"),
                                         ("mae_change", "1.605616", "supported"),
                                         ("relative_improvement", "-0.436285", "supported"),
                                         ("baseline_negative_predictions", "2", "supported"),
                                         ("candidate_negative_predictions", "1", "contradicted")]:
            with self.subTest(metric=metric, value=value):
                body = self.body({"kind": "metric", "metric": metric, "value": value})
                self.assertEqual(self.check_readonly(body)["status"], expected)
        self.assert_code("INVALID_PLAN_FACT_CHECK", self.body({"kind": "metric", "metric": "baseline_negative_predictions", "value": "2.1"}))
        for value in ("NaN", "Infinity", "5_2858", "1e9999999999999999999999", 5.28):
            self.assert_code("INVALID_PLAN_FACT_CHECK", self.body({"kind": "metric", "metric": "candidate_mae", "value": value}))

    def test_unknown_reference_does_not_borrow_current_comparisons(self):
        self.saved_plan()
        body = self.body()
        body["claim"]["comparison"]["candidate_action_id"] = "not-supplied-action"
        with patch.object(protocol, "build_context", side_effect=AssertionError("Only frozen facts may be checked")):
            result = self.check_readonly(body)
        self.assertEqual((result["status"], result["actual"], result["reason_code"]),
                         ("undetermined", None, "comparison_not_supplied"))
        self.assertIsNone(result["saved_metrics"])
        self.assertIsNone(result["comparison_status"])

    def test_noncomparable_and_missing_metrics_remain_undetermined(self):
        for comparison in ({**self.comparison, "status": "not_comparable", "metrics": {}},
                           {**self.comparison, "metrics": {}},
                           {**self.comparison, "metrics": {"candidate_mae": None}}):
            status, actual, _ = plan_fact_check._evaluate(comparison, {"kind": "metric", "metric": "candidate_mae", "value": "5.2858"})
            self.assertEqual((status, actual), ("undetermined", None))
        for value in (float("inf"), float("nan"), True):
            comparison = {**self.comparison, "metrics": {"baseline_mae": 3.68, "candidate_mae": value}}
            self.assertEqual(plan_fact_check._evaluate(comparison, {"kind": "mae_order", "value": "candidate_lower"})[:2],
                             ("undetermined", None))
        self.saved_plan(comparisons=[{**self.comparison, "status": "not_comparable", "metrics": {}}])
        result = self.check_readonly(self.body())
        self.assertEqual(result["reason_code"], "comparison_not_comparable")
        self.assertEqual(result["comparison_status"], "not_comparable")
        self.assertIsNone(result["saved_metrics"])

    def test_frozen_legacy_context_does_not_gain_new_fact_coverage(self):
        self.saved_plan(legacy=True)
        self.assertEqual(self.check_readonly(self.body())["reason_code"], "comparison_not_supplied")

    def test_terminal_answers_and_later_project_changes_keep_frozen_fact_result(self):
        self.saved_plan(outcome="applied")
        first = self.check_readonly(self.body())
        self.project.save_plan(request_id="later-operator-plan", expected_state_version=self.project.status()["state_version"],
                               plan=self.arguments["plan"], reason="Later fixture revision must not rewrite a frozen review.")
        self.assertEqual(self.check_readonly(self.body()), first)
        self.assertLess(first["source_state_version"], self.project.status()["state_version"])

    def test_rejected_answer_remains_checkable_without_changing_decision(self):
        record = self.saved_plan(outcome="rejected")
        self.assertEqual(self.check_readonly(self.body())["status"], "contradicted")
        self.assertEqual(self.host.status(request_id="fact-plan"), record)

    def test_bad_span_or_structure_is_rejected_and_original_response_tampering_is_detected(self):
        record = self.saved_plan()
        for change in ({"quote": "invented quote"}, {"start": 3}, {"start": True},
                       {"field": "plan.hidden"}, {"assertion": {"kind": []}}, {"extra": True}):
            body = self.body()
            body["claim"].update(change)
            self.assert_code("INVALID_PLAN_FACT_CHECK", body)
        (self.host.directory / record["response_file"]).write_bytes(b"changed")
        self.assert_code("EVIDENCE_CHANGED", self.body())

    def test_absent_and_prepared_responses_fail_without_creating_or_changing_a_journal(self):
        files = self.tree_bytes(self.manager.root)
        self.assertFalse(self.host.directory.exists())
        self.assert_code("ARTIFACT_NOT_FOUND", self.body())
        self.assertEqual(self.tree_bytes(self.manager.root), files)
        self.assertFalse(self.host.directory.exists())
        self.saved_plan(receive=False)
        files = self.tree_bytes(self.manager.root)
        self.assert_code("PLAN_RESPONSE_NOT_READY", self.body())
        self.assertEqual(self.tree_bytes(self.manager.root), files)

    def test_http_previews_reuse_csrf_and_readonly_optin_without_a_request_ledger_entry(self):
        self.saved_plan()
        server = self.serve(local_workspace=self.manager, allow_local_actions=True)
        headers = self.session(server)
        before = self.tree_bytes(self.manager.root)
        path = "/api/local-workbench/plan-fact-check"
        self.assertEqual(self.request(server, path, "POST", self.body(), {**headers, "X-AutoResearch-CSRF": "invalid"})[0], 403)
        status, result = self.request(server, path, "POST", self.body(), headers)
        self.assertEqual((status, result["status"]), (200, "contradicted"))
        self.assertEqual(self.tree_bytes(self.manager.root), before)
        disabled = self.serve(local_workspace=self.manager, allow_local_actions=False)
        self.assertEqual(self.request(disabled, path, "POST", self.body(), {"Content-Type": "application/json"})[0], 405)


if __name__ == "__main__":
    unittest.main()
