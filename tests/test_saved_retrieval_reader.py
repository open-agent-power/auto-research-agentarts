"""Saved-record reader engineering fixtures; no ranking, scoring, fitting or APIs."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import test_retrieval_adapter as fixture
from autoresearch import retrieval_adapter as adapter, retrieval_lexical as lexical
from autoresearch import saved_retrieval_reader as reader
from autoresearch.contracts import ResearchError, canonical, fingerprint


class SavedRetrievalReaderTests(unittest.TestCase):
    def setUp(self):
        helper = fixture.RetrievalAdapterTests()
        helper.setUp()
        self.addCleanup(helper.doCleanups)
        self.directory = helper.root
        # Capture a bounded source, then hand-author saved results. Never call
        # execute/audit_execute or a ranking/metric implementation to build it.
        helper.spec["query_splits"]["dev"].append("qn")
        helper.write_json("spec.json", helper.spec)
        query_file = helper.root / "queries.jsonl"
        query_file.write_text(query_file.read_text() + canonical({"_id": "qn", "text": "already complete", "metadata": {}}) + "\n")
        qrels_file = helper.root / "qrels-train.tsv"
        qrels_file.write_text(qrels_file.read_text() + "qn\ta\t1\n")
        docs_path = helper.root / "corpus.jsonl"
        docs = [json.loads(line) for line in docs_path.read_text().splitlines()]
        docs[0].update(title="<b>literal title</b>" * 40, text="<script>literal text</script>" + "x" * 5000,
                       metadata={"opaque_note": "do not expose opaque source metadata"})
        docs_path.write_text("".join(canonical(doc) + "\n" for doc in docs))
        self.packet = helper.captured()
        root = helper.root / "project"
        (root / "artifacts").mkdir(parents=True)
        self.project = SimpleNamespace(root=root)
        source = canonical(self.packet).encode()
        (root / "source.json").write_bytes(source)
        self.state = {"id": "project-fixture", "run_id": "run-fixture", "state_version": 13,
                      "snapshot_ref": "f" * 64, "source_snapshot_sha256": self.packet["snapshot_sha256"],
                      "source_scope": deepcopy(self.packet["scope"]),
                      "registration": {"source_sha256": hashlib.sha256(source).hexdigest(), "method_id": adapter.TOOL_ID},
                      "actions": [], "evidence_actions": [], "budget": {"local_tool_calls_used": 2, "new_fits": 0}}
        self.envelopes = {}
        self.metric_keys = list(lexical.METRICS)
        metrics, ranks, adverse = [], [], []
        plans = [("dev", "qd", 1, ["a", "b"], ["b", "c"], 1, 0, "a"),
                 ("validation", "qv", 2, [], [], 0, 0, "b"),
                 ("test", "qt", 3, ["a"], ["c"], 0, 1, "c"),
                 ("dev", "qn", 4, ["a"], ["a"], 1, 1, "a")]
        for split, qid, query_line, baseline_rank, candidate_rank, baseline_value, candidate_value, relevant in plans:
            values = {}
            role = "test_qrels" if split == "test" else "train_qrels"
            for method, ranking, value in [("tfidf_cosine", baseline_rank, baseline_value), ("bm25", candidate_rank, candidate_value)]:
                saved_metrics = {key: value for key in self.metric_keys}
                values[method] = saved_metrics
                ranks.append({"split": split, "query_id": qid, "method": method, "query_line": query_line,
                              "ranking": ranking, "ranked_doc_lines": ["abc".index(doc) + 1 for doc in ranking],
                              "ranking_seconds": 0})
                metrics.append({"split": split, "query_id": qid, "method": method, "metrics": saved_metrics,
                                "qrel_locator": {"kind": "tsv_query_documents", "role": role,
                                    "source_sha256": self.packet["assets"][role]["sha256"],
                                    "query_id": qid, "document_ids": [relevant]}})
            delta = {key: candidate_value - baseline_value for key in self.metric_keys}
            if qid != "qn":
                adverse.append({"split": split, "query_id": qid, "baseline": values["tfidf_cosine"],
                    "candidate": values["bm25"], "delta": delta,
                    "loss_metrics": self.metric_keys if candidate_value < baseline_value else [],
                    "gain_metrics": self.metric_keys if candidate_value > baseline_value else [],
                    "tie_metrics": self.metric_keys if candidate_value == baseline_value else []})
        self.primary_result = {"scope": deepcopy(self.packet["scope"]),
            "source_snapshot_sha256": self.packet["snapshot_sha256"], "comparison": deepcopy(adapter.COMPARISON),
            "rankings": ranks, "rankings_before_scoring_sha256": fingerprint(ranks), "per_query_metrics": metrics,
            "paired_summary": {"splits": {}}, "adverse_queries": adverse,
            "usage": {"index_builds": 1, "ranking_calls": 8, "scoring_calls": 8, "query_pairs": 4,
                      "corpus_records": 3, "index_seconds": 0, "native_fits": 0, "model_calls": 0},
            "limitations": deepcopy(adapter.NOTES)}
        self.primary = self.add_action("action-primary", adapter.TOOL_ID, self.primary_result)
        self.audit_result = {"scope": deepcopy(self.packet["scope"]),
            "source_snapshot_sha256": self.packet["snapshot_sha256"],
            "predecessor": {"based_on_action_id": self.primary["id"], "based_on_result_sha256": self.primary["result_sha256"]},
            "rankings_sha256": fingerprint(ranks), "adverse_queries": deepcopy(adverse), "per_query_deltas": [],
            "summary": {"splits": {}}, "usage": {"query_pairs": 4, "index_builds": 0, "ranking_calls": 0,
                                                   "scoring_calls": 0, "native_fits": 0, "model_calls": 0},
            "limitations": deepcopy(adapter.NOTES)}
        self.audit = self.add_action("action-audit", adapter.AUDIT_TOOL_ID, self.audit_result)

    def add_action(self, action_id, command, result):
        tool = {"tool_id": command, "schema_version": "citation-retrieval-result-v1" if command == adapter.TOOL_ID else "retrieval-saved-error-result-v1",
                "adapter_version": "1", "status": "completed", "new_fits": 0, "model_calls": 0,
                "scientific_validation": False, "result": result, "observations": [], "evidence_refs": [], "metrics": [], "failure": None}
        envelope = {"action_id": action_id, "request_sha256": fingerprint({"request": action_id}),
                    "code_identity": "c" * 64, "source_snapshot_sha256": self.packet["snapshot_sha256"], "tool_result": tool}
        action = {"id": action_id, "project_id": self.state["id"], "run_id": self.state["run_id"],
                  "command": command, "status": "completed", "request_id": "request-" + action_id,
                  "artifact": "artifacts/" + action_id + ".json",
                  **{key: envelope[key] for key in ["request_sha256", "code_identity", "source_snapshot_sha256"]}}
        self.state["actions"].append(action)
        self.envelopes[action_id] = envelope
        self.seal(action)
        return action

    def seal(self, action):
        envelope = self.envelopes[action["id"]]
        envelope["sha256"] = fingerprint({k: v for k, v in envelope.items() if k != "sha256"})
        action["result_sha256"] = envelope["sha256"]
        (self.project.root / action["artifact"]).write_text(canonical(envelope))

    def page(self, **kwargs):
        return reader.read_adverse_page(self.project, self.state, action_id=self.primary["id"], **kwargs)

    def query(self, query_id="qd", split="dev", **kwargs):
        return reader.read_adverse_query(self.project, self.state, action_id=kwargs.pop("action_id", self.primary["id"]),
                                         query_id=query_id, split=split, **kwargs)

    def rejected(self, call, *args, **kwargs):
        with self.assertRaises(ResearchError):
            call(*args, **kwargs)

    def test_page_preserves_order_zero_metrics_and_category_counts(self):
        page = self.page(limit=2)
        self.assertEqual(page["schema_version"], "saved-retrieval-adverse-page-v1")
        self.assertEqual([item["query_id"] for item in page["items"]], ["qd", "qv"])
        self.assertEqual(page["pagination"], {"offset": 0, "limit": 2, "total": 3, "next_offset": 2})
        self.assertEqual(page["items"][0]["metrics"]["bm25"]["recall@20"], 0)
        self.assertEqual(page["counts"]["metric_loss"], 1)
        self.assertEqual(page["counts"]["no_metric_loss_both_incomplete"], 1)
        self.assertEqual(page["counts"]["no_metric_loss_baseline_only_incomplete"], 1)
        last = self.page(offset=2, limit=2)
        self.assertEqual(last["items"][0]["query_id"], "qt")
        self.assertIsNone(last["pagination"]["next_offset"])

    def test_completed_audit_resolves_exact_registered_primary(self):
        page = reader.read_adverse_page(self.project, self.state, action_id=self.audit["id"])
        self.assertEqual(page["binding"]["action_id"], self.audit["id"])
        self.assertEqual(page["binding"]["primary_action_id"], self.primary["id"])
        self.assertEqual(page["binding"]["primary_result_sha256"], self.primary["result_sha256"])
        self.assertEqual([item["query_id"] for item in page["items"]], ["qd", "qv", "qt"])

    def test_query_returns_original_text_rank_locators_and_explicit_truncation(self):
        value = self.query()
        self.assertEqual(value["query"]["id"], "qd")
        self.assertEqual(value["query"]["line"], 1)
        self.assertEqual([arm["method"] for arm in value["arms"]], ["tfidf_cosine", "bm25"])
        first = value["arms"][0]["documents"][0]
        self.assertEqual((first["rank"], first["id"], first["line"], first["relevant"]), (1, "a", 1, True))
        self.assertTrue(first["title"].startswith("<b>literal"))
        self.assertTrue(first["text"].startswith("<script>literal"))
        self.assertTrue(first["text_truncated"])
        self.assertTrue(first["title_truncated"])
        self.assertLessEqual(len(first["text"]), 4096)
        self.assertLessEqual(len(first["title"]), 512)
        self.assertEqual(value["arms"][0]["qrel"]["doc_ids"], ["a"])
        serialized = canonical(value)
        self.assertNotIn("opaque_note", serialized)
        self.assertNotIn('"score"', serialized)
        self.assertNotIn("bytes_base64", serialized)

    def test_query_rejects_nonadverse_missing_wrong_split_and_path_input(self):
        for qid, split in [("qn", "dev"), ("missing", "dev"), ("qd", "test"), ("../../source.json", "dev"), ("qd", "unknown")]:
            with self.subTest(qid=qid, split=split):
                self.rejected(self.query, qid, split)

    def test_pagination_accepts_only_bounded_exact_integers(self):
        for kwargs in [{"offset": -1}, {"offset": True}, {"offset": "0"}, {"limit": 0}, {"limit": 26}, {"limit": 1.0}, {"limit": False}]:
            with self.subTest(kwargs=kwargs):
                self.rejected(self.page, **kwargs)

    def test_missing_unknown_and_unrelated_actions_are_not_read(self):
        self.rejected(reader.read_adverse_page, self.project, self.state, action_id="missing")
        self.primary["status"] = "unknown"
        self.rejected(self.page)
        self.primary["status"] = "completed"
        self.primary["command"] = "research.weighted-interval-fixed-pair"
        self.rejected(self.page)

    def test_hash_binding_and_registered_artifact_path_mismatch(self):
        self.primary["result_sha256"] = "d" * 64
        self.rejected(self.page)
        self.seal(self.primary)
        self.primary["artifact"] = "../../elsewhere.json"
        self.rejected(self.page)

    def test_project_source_or_request_identity_mismatch_is_rejected(self):
        for field, wrong in [("project_id", "different-project"), ("request_sha256", "0" * 64), ("source_snapshot_sha256", "1" * 64)]:
            old = self.primary[field]
            self.primary[field] = wrong
            with self.subTest(field=field):
                self.rejected(self.page)
            self.primary[field] = old

    def test_audit_cannot_bind_unknown_changed_or_unrelated_parent(self):
        predecessor = self.audit_result["predecessor"]
        for field, wrong in [("based_on_action_id", "missing"), ("based_on_result_sha256", "2" * 64)]:
            old = predecessor[field]
            predecessor[field] = wrong
            self.seal(self.audit)
            with self.subTest(field=field):
                self.rejected(reader.read_adverse_page, self.project, self.state, action_id=self.audit["id"])
            predecessor[field] = old
        self.seal(self.audit)
        self.audit_result["adverse_queries"] = []
        self.seal(self.audit)
        self.rejected(reader.read_adverse_page, self.project, self.state, action_id=self.audit["id"])

    def test_source_bytes_changed_or_missing_fail_before_lookup(self):
        source = self.project.root / "source.json"
        source.write_bytes(source.read_bytes() + b" ")
        self.rejected(self.page)
        source.unlink()
        self.rejected(self.page)

    def test_artifact_symlink_or_oversized_file_is_rejected(self):
        artifact = self.project.root / self.primary["artifact"]
        other = self.directory / "other.json"
        other.write_bytes(artifact.read_bytes())
        artifact.unlink()
        artifact.symlink_to(other)
        self.rejected(self.page)
        artifact.unlink()
        artifact.write_bytes(other.read_bytes())
        with patch.object(reader, "MAX_ARTIFACT_BYTES", 32):
            self.rejected(self.page)

    def test_saved_query_doc_and_qrel_locators_cannot_drift(self):
        rank = self.primary_result["rankings"][0]
        old = rank["query_line"]
        rank["query_line"] = 3
        self.primary_result["rankings_before_scoring_sha256"] = fingerprint(self.primary_result["rankings"])
        self.seal(self.primary)
        self.rejected(self.query)
        rank["query_line"] = old
        rank["ranked_doc_lines"][0] = 3
        self.primary_result["rankings_before_scoring_sha256"] = fingerprint(self.primary_result["rankings"])
        self.seal(self.primary)
        self.rejected(self.query)
        rank["ranked_doc_lines"][0] = 1
        self.primary_result["rankings_before_scoring_sha256"] = fingerprint(self.primary_result["rankings"])
        self.primary_result["per_query_metrics"][0]["qrel_locator"]["document_ids"] = ["c"]
        self.seal(self.primary)
        self.rejected(self.query)

    def test_missing_or_null_metrics_do_not_become_zero(self):
        value = self.primary_result["per_query_metrics"][0]["metrics"]
        old = value.pop("recall@20")
        self.seal(self.primary)
        self.rejected(self.page)
        value["recall@20"] = old
        self.primary_result["adverse_queries"][0]["baseline"] = {key: None for key in self.metric_keys}
        self.seal(self.primary)
        self.rejected(self.page)

    def test_complete_pair_cannot_be_omitted_from_source_declared_coverage(self):
        self.primary_result["rankings"] = [r for r in self.primary_result["rankings"] if r["query_id"] != "qn"]
        self.primary_result["per_query_metrics"] = [r for r in self.primary_result["per_query_metrics"] if r["query_id"] != "qn"]
        self.primary_result["rankings_before_scoring_sha256"] = fingerprint(self.primary_result["rankings"])
        self.seal(self.primary)
        self.rejected(self.page)

    def test_loss_classification_must_match_saved_negative_delta(self):
        self.primary_result["adverse_queries"][0]["loss_metrics"] = []
        self.seal(self.primary)
        self.rejected(self.page)

    def test_duplicate_or_nonfinite_json_and_oversized_response_are_rejected(self):
        path = self.project.root / self.primary["artifact"]
        raw = path.read_text()
        path.write_text('{"action_id":"duplicate",' + raw[1:])
        self.rejected(self.page)
        self.assertIn('"recall@20":1', raw)
        path.write_text(raw.replace('"recall@20":1', '"recall@20":NaN', 1))
        self.rejected(self.page)
        path.write_text(raw)
        with patch.object(reader, "MAX_RESPONSE_BYTES", 32):
            self.rejected(self.page)

    def test_reads_never_compute_or_mutate_state_source_and_artifacts(self):
        before = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in self.project.root.rglob("*") if p.is_file()}
        state = deepcopy(self.state)
        with patch.object(lexical, "build_index", side_effect=AssertionError("index forbidden")), \
             patch.object(lexical, "retrieve", side_effect=AssertionError("rank forbidden")), \
             patch.object(lexical, "metrics", side_effect=AssertionError("score forbidden")), \
             patch.object(adapter, "execute", side_effect=AssertionError("execute forbidden")):
            self.page()
            self.query()
        self.assertEqual(self.state, state)
        after = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in self.project.root.rglob("*") if p.is_file()}
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
