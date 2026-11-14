"""Hand-authored saved engineering records; zero ranking, label scoring or fits."""
from contextlib import ExitStack
from copy import deepcopy
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import test_relevance_retrieval_adapter as fixture
import test_saved_retrieval_reader as legacy_fixture
from autoresearch import relevance_retrieval_adapter as adapter, retrieval_adapter as citation, retrieval_lexical as lexical
from autoresearch import saved_retrieval_reader as reader
from autoresearch.contracts import ResearchError, canonical, fingerprint


class SavedRelevanceReaderTests(unittest.TestCase):
    def setUp(self):
        helper = fixture.RelevanceRetrievalAdapterTests()
        helper.setUp()
        self.addCleanup(helper.doCleanups)
        self.directory = helper.root
        helper.spec["query_splits"]["dev"].extend(["qn", "qg"])
        helper.write_json("spec.json", helper.spec)
        rows = [json.loads(line) for line in (helper.root / "queries.jsonl").read_text().splitlines()]
        rows[0]["text"] = "query" * 1100
        rows[0]["metadata"] = {"opaque_annotation": "do not expose"}
        rows.extend([{"_id": "qn", "text": "complete", "metadata": {}},
                     {"_id": "qg", "text": "candidate gain", "metadata": {}}])
        helper.write_rows("queries.jsonl", rows)
        qrels = helper.root / "qrels-train.tsv"
        qrels.write_text(qrels.read_text() + "qn\ta\t1\nqg\tc\t1\n")
        rows = [json.loads(line) for line in (helper.root / "corpus.jsonl").read_text().splitlines()]
        rows[0].update(title="<b>literal title</b>" * 40, text="<script>literal text</script>" + "x" * 5000)
        helper.write_rows("corpus.jsonl", rows)
        self.packet = helper.captured()
        self.project = SimpleNamespace(root=helper.root / "project")
        (self.project.root / "artifacts").mkdir(parents=True)
        source = canonical(self.packet).encode()
        (self.project.root / "source.json").write_bytes(source)
        self.state = {"id": "project-relevance-fixture", "run_id": "run-relevance-fixture", "state_version": 13,
                      "snapshot_ref": "f" * 64, "source_snapshot_sha256": self.packet["snapshot_sha256"],
                      "source_scope": deepcopy(self.packet["scope"]), "registration": {
                          "source_sha256": hashlib.sha256(source).hexdigest(), "method_id": adapter.TOOL_ID},
                      "actions": [], "evidence_actions": [], "budget": {"local_tool_calls_used": 2, "new_fits": 0}}
        self.envelopes = {}
        metrics, ranks = [], []
        plans = [("dev", "qd", 1, ["a", "b"], ["b", "c"], .8, .2, {"a": 2}),
                 ("validation", "qv", 2, [], [], 0, 0, {"b": 1}),
                 ("test", "qt", 3, ["c", "a"], ["c"], .4, .5, {"c": 1, "missing": 2}),
                 ("dev", "qn", 4, ["a"], ["a"], 1, 1, {"a": 1}),
                 ("dev", "qg", 5, ["a"], ["c"], 0, 1, {"c": 1})]
        for split, qid, line, baseline, candidate, before, after, grades in plans:
            role = "test_qrels" if split == "test" else "train_qrels"
            for method, ranking, value in (("bm25", baseline, before), ("tfidf_cosine", candidate, after)):
                ranks.append({"split": split, "query_id": qid, "method": method, "query_line": line,
                              "ranking": ranking, "ranked_doc_lines": ["abc".index(doc) + 1 for doc in ranking], "ranking_seconds": 0})
                metrics.append({"split": split, "query_id": qid, "method": method,
                                "metrics": {name: value for name in lexical.METRICS}, "qrel_locator": {
                                    "kind": "tsv_query_documents", "role": role, "query_id": qid,
                                    "source_sha256": self.packet["assets"][role]["sha256"],
                                    "document_ids": sorted(grades), "document_grades": deepcopy(grades)}})
        # Arithmetic of authored saved metric values only, never scoring labels.
        summary, deltas, adverse = adapter._paired(metrics)
        self.primary_result = {"scope": deepcopy(self.packet["scope"]), "source_snapshot_sha256": self.packet["snapshot_sha256"],
            "comparison": deepcopy(adapter.COMPARISON), "rankings": ranks, "rankings_before_scoring_sha256": fingerprint(ranks),
            "per_query_metrics": metrics, "paired_summary": summary, "adverse_queries": adverse,
            "usage": {"index_builds": 1, "ranking_calls": 10, "scoring_calls": 10, "query_pairs": 5,
                      "corpus_records": 4, "index_seconds": 0, "native_fits": 0, "model_calls": 0}, "limitations": deepcopy(adapter.NOTES)}
        self.primary = self.add_action("action-primary", adapter.TOOL_ID, self.primary_result)
        self.audit_result = {"scope": deepcopy(self.packet["scope"]), "source_snapshot_sha256": self.packet["snapshot_sha256"],
            "predecessor": {"based_on_action_id": self.primary["id"], "based_on_result_sha256": self.primary["result_sha256"]},
            "rankings_sha256": fingerprint(ranks), "adverse_queries": deepcopy(adverse), "per_query_deltas": deltas,
            "summary": deepcopy(summary), "usage": {"query_pairs": 5, "index_builds": 0, "ranking_calls": 0,
                "scoring_calls": 0, "native_fits": 0, "model_calls": 0}, "limitations": deepcopy(adapter.NOTES)}
        self.audit = self.add_action("action-audit", adapter.AUDIT_TOOL_ID, self.audit_result)

    def add_action(self, action_id, command, result):
        request = {"project_id": self.state["id"], "command": command, "dimension": None,
                   "source_snapshot_sha256": self.packet["snapshot_sha256"]}
        primary = command == adapter.TOOL_ID
        evaluation = "relevance-retrieval-fixed-pair-v1" if primary else "relevance-retrieval-saved-error-audit-v1"
        parameters = {} if primary else deepcopy(result["predecessor"])
        if not primary:
            request.update(parameters=deepcopy(parameters), evaluation_ref=evaluation)
        tool = {"tool_id": command, "schema_version": "relevance-retrieval-result-v1" if primary else "relevance-saved-error-result-v1",
                "adapter_version": "1", "status": "completed", "new_fits": 0, "model_calls": 0,
                "scientific_validation": False, "result": result, "observations": [],
                "evidence_refs": [{"source_sha256": self.packet["assets"]["corpus"]["sha256"]}], "metrics": [], "failure": None}
        envelope = {"action_id": action_id, "request_sha256": fingerprint(request), "code_identity": "c" * 64,
                    "source_snapshot_sha256": self.packet["snapshot_sha256"], "tool_result": tool}
        action = {**request, "id": action_id, "run_id": self.state["run_id"], "status": "completed",
                  "request_id": "request-" + action_id, "artifact": "artifacts/" + action_id + ".json",
                  **{key: envelope[key] for key in ("request_sha256", "code_identity")},
                  "method_instance": {"definition_ref": {"id": command, "version": "1"}, "parameters": deepcopy(parameters),
                      "input_bindings": {"source_snapshot_sha256": self.packet["snapshot_sha256"], **parameters},
                      "evaluation_ref": evaluation, "scope": deepcopy(self.packet["scope"])}}
        self.state["actions"].append(action)
        self.envelopes[action_id] = envelope
        self.seal(action)
        return action

    def seal(self, action):
        envelope = self.envelopes[action["id"]]
        envelope["sha256"] = fingerprint({key: value for key, value in envelope.items() if key != "sha256"})
        action["result_sha256"] = envelope["sha256"]
        (self.project.root / action["artifact"]).write_text(canonical(envelope))

    def page(self, action=None, **kwargs):
        return reader.read_adverse_page(self.project, self.state, action_id=(action or self.primary)["id"], **kwargs)

    def query(self, qid="qd", split="dev", action=None):
        return reader.read_adverse_query(self.project, self.state, action_id=(action or self.primary)["id"], query_id=qid, split=split)

    def reject(self, call, *args, **kwargs):
        with self.assertRaises(ResearchError):
            call(*args, **kwargs)

    def test_page_schema_contract_counts_and_true_method_binding(self):
        page = self.page(limit=2)
        self.assertEqual(page["schema_version"], "saved-relevance-adverse-page-v1")
        self.assertEqual(page["contract"], {"id": "relevance-retrieval-fixed-pair-v1", "qrels_semantics": "positive_relevance_binary_projection",
            "baseline": "bm25", "candidate": "tfidf_cosine", "ignore_identical_ids": True, "missing_document_policy": "retain_in_denominator"})
        self.assertIs(page["contract"]["ignore_identical_ids"], True)
        self.assertEqual([row["query_id"] for row in page["items"]], ["qd", "qv"])
        self.assertEqual(page["items"][0]["metrics"]["bm25"]["recall@20"], .8)
        self.assertEqual(page["items"][0]["metrics"]["tfidf_cosine"]["recall@20"], .2)
        self.assertAlmostEqual(page["items"][0]["delta"]["recall@20"], -.6)
        self.assertEqual(page["counts"], {"metric_loss": 1, "no_metric_loss_both_incomplete": 2,
            "no_metric_loss_baseline_only_incomplete": 1, "no_metric_loss_other": 0, "total": 4, "no_metric_loss_total": 3})
        self.assertEqual(page["pagination"]["next_offset"], 2)

    def test_detail_retains_grade_two_missing_positives_and_unjudged_null(self):
        value = self.query()
        self.assertEqual(value["schema_version"], "saved-relevance-query-v1")
        self.assertEqual([arm["method"] for arm in value["arms"]], ["bm25", "tfidf_cosine"])
        self.assertEqual(value["arms"][0]["qrel"]["grades"], {"a": 2})
        self.assertEqual(value["arms"][0]["documents"][0]["original_grade"], 2)
        self.assertIsNone(value["arms"][0]["documents"][1]["original_grade"])
        missing = self.query("qt", "test")
        for arm in missing["arms"]:
            self.assertEqual(arm["qrel"]["doc_ids"], ["c", "missing"])
            self.assertEqual(arm["qrel"]["grades"], {"c": 1, "missing": 2})
            self.assertEqual(arm["qrel"]["missing_doc_ids"], ["missing"])
            self.assertNotIn("missing", [doc["id"] for doc in arm["documents"]])

    def test_large_text_has_explicit_bounds_without_losing_label_metadata(self):
        value = self.query()
        self.assertEqual(len(value["query"]["text"]), 4096)
        self.assertTrue(value["query"]["text_truncated"])
        self.assertEqual(value["query"]["source_sha256"], self.packet["assets"]["queries"]["sha256"])
        doc = value["arms"][0]["documents"][0]
        self.assertEqual(len(doc["title"]), 512)
        self.assertEqual(len(doc["text"]), 4096)
        self.assertTrue(doc["title_truncated"])
        self.assertTrue(doc["text_truncated"])
        self.assertEqual(value["arms"][0]["qrel"]["grades"], {"a": 2})
        self.assertNotIn("opaque_annotation", canonical(value))
        self.assertNotIn("bytes_base64", canonical(value))

    def test_audit_resolves_exact_registered_primary(self):
        page = self.page(self.audit)
        self.assertEqual(page["binding"]["action_id"], self.audit["id"])
        self.assertEqual(page["binding"]["primary_action_id"], self.primary["id"])
        self.assertEqual(page["binding"]["primary_result_sha256"], self.primary["result_sha256"])
        self.assertEqual(self.query(action=self.audit)["arms"], self.query()["arms"])

    def test_schema_comparison_scope_and_cross_family_tampering_reject(self):
        tool = self.envelopes[self.primary["id"]]["tool_result"]
        tool["schema_version"] = "citation-retrieval-result-v1"
        self.seal(self.primary)
        self.reject(self.page)
        tool["schema_version"] = "relevance-retrieval-result-v1"
        self.primary_result["comparison"]["ignore_identical_ids"] = 1
        self.seal(self.primary)
        self.reject(self.page)
        self.primary_result["comparison"]["ignore_identical_ids"] = True
        self.primary_result["scope"]["qrels_semantics"] = citation.SEMANTICS
        self.seal(self.primary)
        self.reject(self.page)

    def test_locator_grades_must_match_original_and_keep_missing_ids(self):
        locator = self.primary_result["per_query_metrics"][0]["qrel_locator"]
        for bad in (1, True, 0, 3, None):
            locator["document_grades"]["a"] = bad
            self.seal(self.primary)
            self.reject(self.page)
        locator["document_grades"]["a"] = 2
        missing = next(row["qrel_locator"] for row in self.primary_result["per_query_metrics"] if row["query_id"] == "qt")
        missing["document_ids"] = ["c"]
        missing["document_grades"] = {"c": 1}
        self.seal(self.primary)
        self.reject(self.page)

    def test_self_id_cannot_reappear_in_saved_relevance_ranking(self):
        row = self.primary_result["rankings"][0]
        row["ranking"][0], row["ranked_doc_lines"][0] = "qd", 4
        self.primary_result["rankings_before_scoring_sha256"] = fingerprint(self.primary_result["rankings"])
        self.seal(self.primary)
        self.reject(self.page)

    def test_reversed_delta_and_incomplete_adverse_union_reject(self):
        adverse = self.primary_result["adverse_queries"]
        original = deepcopy(adverse[0])
        adverse[0]["delta"] = {name: .6 for name in lexical.METRICS}
        adverse[0]["loss_metrics"] = []
        self.seal(self.primary)
        self.reject(self.page)
        adverse[0] = original
        adverse.pop()
        self.seal(self.primary)
        self.reject(self.page)

    def test_audit_registered_parameters_predecessor_and_family_must_agree(self):
        self.audit["method_instance"]["parameters"]["based_on_action_id"] = "wrong"
        self.reject(self.page, self.audit)
        self.audit["method_instance"]["parameters"] = deepcopy(self.audit_result["predecessor"])
        self.audit_result["predecessor"]["based_on_action_id"] = "wrong"
        self.seal(self.audit)
        self.reject(self.page, self.audit)
        self.audit_result["predecessor"]["based_on_action_id"] = self.primary["id"]
        self.seal(self.audit)
        self.primary["command"] = citation.TOOL_ID
        self.reject(self.page, self.audit)

    def test_reads_never_evaluate_create_upgrade_or_mutate_records(self):
        before = {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in self.project.root.rglob("*") if path.is_file()}
        state = deepcopy(self.state)
        with ExitStack() as guards:
            for module, names in ((lexical, ("build_index", "retrieve", "metrics")), (adapter, ("execute", "retrieve")), (citation, ("execute",))):
                for name in names:
                    guards.enter_context(patch.object(module, name, side_effect=AssertionError("No evaluation")))
            guards.enter_context(patch.object(adapter.AUDIT, "execute_saved", side_effect=AssertionError("No new audit")))
            for name in ("create", "upgrade", "step"):
                guards.enter_context(patch("autoresearch.research_project.ResearchProject." + name, side_effect=AssertionError("No project mutation")))
            guards.enter_context(patch("sklearn.linear_model.Ridge.fit", side_effect=AssertionError("No fits")))
            self.page()
            self.query()
            self.page(self.audit)
            self.query("qt", "test", self.audit)
        self.assertEqual(self.state, state)
        self.assertEqual(before, {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in self.project.root.rglob("*") if path.is_file()})

    def test_family_descriptor_is_per_request_and_legacy_payload_stays_unchanged(self):
        old = legacy_fixture.SavedRetrievalReaderTests()
        old.setUp()
        self.addCleanup(old.doCleanups)
        before_page, before_query = canonical(old.page()), canonical(old.query())
        new = self.page()
        new["contract"]["ignore_identical_ids"] = False
        self.assertEqual(canonical(old.page()), before_page)
        self.assertEqual(canonical(old.query()), before_query)
        self.assertNotIn("contract", old.page())
        self.assertEqual([arm["method"] for arm in old.query()["arms"]], ["tfidf_cosine", "bm25"])
        self.assertIs(self.page()["contract"]["ignore_identical_ids"], True)

    def test_bounded_requests_and_integrity_failures_reject(self):
        for kwargs in ({"offset": True}, {"limit": 26}, {"offset": 5}):
            self.reject(self.page, **kwargs)
        with patch.object(reader, "MAX_RESPONSE_BYTES", 32):
            self.reject(self.query)
        self.primary["request_sha256"] = "0" * 64
        self.reject(self.page)

    def test_project_registration_family_rejects_before_any_artifact_read(self):
        for method in (citation.TOOL_ID, "research.unsupported"):
            self.state["registration"]["method_id"] = method
            with patch.object(reader, "_read", side_effect=AssertionError("Registration must reject before any file read")):
                self.reject(self.page)
                self.reject(self.page, self.audit)


if __name__ == "__main__":
    unittest.main()
