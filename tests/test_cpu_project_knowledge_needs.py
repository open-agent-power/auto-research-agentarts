"""CPU knowledge needs from hand-authored state; no source, study, ranking or model."""
from contextlib import ExitStack
from copy import deepcopy
import unittest
from unittest.mock import patch

from sklearn.linear_model import Ridge
from sklearn.preprocessing import StandardScaler

from autoresearch import knowledge, project_knowledge, retrieval_adapter, relevance_retrieval_adapter
from autoresearch import scheduling_adapter, retrieval_lexical, scheduling_kernel
from autoresearch.contracts import canonical


class CPUProjectKnowledgeNeedsTests(unittest.TestCase):
    FAMILIES = {
        "research.retrieval-fixed-pair": {
            "clarification": ("citation", "cited", "qrels"),
            "design": ("tfidf cosine baseline", "tfidf_cosine", "bm25 candidate", "query_splits", "dev validation test"),
            "preparation": ("corpus", "queries", "qrels"),
            "interpretation": ("recall", "mrr", "ndcg", "unretrieved citations"),
        },
        "research.relevance-fixed-pair": {
            "clarification": ("relevance", "positive grades", "binary projection"),
            "design": ("bm25 baseline", "tfidf cosine candidate", "tfidf_cosine", "query_splits", "dev validation test"),
            "preparation": ("identical query document id exclusion", "ignore_identical_ids", "qrels"),
            "interpretation": ("recall", "ndcg", "missing positive denominator", "missing_positive_document_ids"),
        },
        "research.weighted-interval-fixed-pair": {
            "clarification": ("synthetic", "weighted interval", "objective"),
            "design": ("quadratic scan dp baseline", "quadratic_scan_dp", "binary search dp candidate", "binary_search_dp"),
            "preparation": ("start end weight", "compatibility", "tie rule"),
            "interpretation": ("saved schedule feasibility", "objective", "timing", "slower"),
        },
    }

    def state(self, method):
        return {"registration": {"method_id": method}, "source_scope": {"dataset_label": "Unreviewed source"},
                "next_decision": {}, "actions": [{"id": "action-existing", "status": "completed"}],
                "budget": {"local_tool_calls_used": 2, "fit_attempts_used": 0, "fits_reserved": 0}}

    def assert_bounded(self, needs):
        self.assertEqual(set(needs), set(project_knowledge.POINTS))
        for need in needs.values():
            self.assertIs(type(need), str)
            self.assertTrue(need.strip())
            self.assertLessEqual(len(need), 512)
            self.assertLessEqual(len(set(knowledge.tokens(need))), 64)

    def test_three_registered_primaries_have_distinct_bounded_domain_needs_without_computation(self):
        with ExitStack() as guard:
            guard.enter_context(patch.object(Ridge, "fit", side_effect=AssertionError("No fit")))
            guard.enter_context(patch.object(StandardScaler, "fit", side_effect=AssertionError("No fit")))
            for module in (retrieval_adapter, relevance_retrieval_adapter, scheduling_adapter):
                guard.enter_context(patch.object(module, "execute", side_effect=AssertionError("No study execution")))
                guard.enter_context(patch.object(module, "capture_source", side_effect=AssertionError("No source capture")))
            for module, names in ((retrieval_lexical, ("retrieve", "build_index", "metrics")),
                                  (scheduling_kernel, ("jobs_for", "schedule", "brute_force")),
                                  (knowledge, ("build_index",)), (project_knowledge, ("query",))):
                for name in names:
                    guard.enter_context(patch.object(module, name, side_effect=AssertionError("No retrieval or computation")))
            for method, points in self.FAMILIES.items():
                with self.subTest(method=method):
                    state = self.state(method)
                    before = canonical(state)
                    needs = project_knowledge.decision_needs(state)
                    self.assert_bounded(needs)
                    for point, terms in points.items():
                        for term in terms:
                            self.assertIn(term, needs[point])
                    self.assertNotIn("ALP", canonical(needs))
                    self.assertNotIn("chemistry", canonical(needs))
                    self.assertNotIn("refute", canonical(needs))
                    self.assertEqual(canonical(state), before)

    def test_existing_bounded_remaining_question_is_preserved_for_each_cpu_family(self):
        for method in self.FAMILIES:
            state = self.state(method)
            base = project_knowledge.decision_needs(state)
            state["next_decision"] = {"remaining_questions": ["", "?", "x" * 513, "Does Factor47 occur?"]}
            needs = project_knowledge.decision_needs(state)
            self.assert_bounded(needs)
            self.assertEqual(needs["interpretation"], "Does Factor47 occur? Factor 47")
            for point in ("clarification", "design", "preparation"):
                self.assertEqual(needs[point], base[point])
            long_question = "x" * 504 + "Factor47"
            state["next_decision"]["remaining_questions"] = [long_question]
            self.assertEqual(project_knowledge.decision_needs(state)["interpretation"], long_question)
            state["next_decision"]["remaining_questions"] = ["x" * 513]
            self.assertEqual(project_knowledge.decision_needs(state)["interpretation"], base["interpretation"])

    def test_unrelated_and_near_match_methods_keep_existing_fallbacks(self):
        self.assertEqual(project_knowledge.decision_needs({})["interpretation"], "CropRed NaN batch export mapping")
        for method in ("research.retrieval-fixed-pair-extra", "research.relevance-saved-audit", "RESEARCH.retrieval-fixed-pair", [], {}):
            self.assertEqual(project_knowledge.decision_needs(self.state(method))["interpretation"],
                             "CropRed NaN batch export mapping")
        self.assertEqual(project_knowledge.decision_needs(self.state("materials.saved-steel-audit"))["interpretation"],
                         "validation MSE threshold external validation")
        self.assertEqual(project_knowledge.decision_needs(self.state("software.source-integrity-check"))["interpretation"],
                         "mutation file identity filesystem")
        state = self.state("data.tabular-quality-audit")
        state["source_scope"] = {"target_column": "Signal_Total", "numeric_columns": ["Panel"]}
        self.assertEqual(project_knowledge.decision_needs(state)["interpretation"],
                         "missing invalid nonfinite group target_unit Signal_Total Panel")
        state["next_decision"] = {"remaining_questions": ["Factor47"]}
        self.assertEqual(project_knowledge.decision_needs(state)["interpretation"], "Factor47 Factor 47")


if __name__ == "__main__":
    unittest.main()
