"""Tiny engineering fixtures only: no real target ranking, fitting or API calls."""
from copy import deepcopy
import hashlib
import math
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from autoresearch import relevance_retrieval_adapter as adapter, retrieval_adapter as citation, retrieval_lexical as lexical
from autoresearch.contracts import ResearchError, canonical, fingerprint


def fixture_spec():
    return {"schema_version": "relevance-retrieval-spec-v1", "dataset_label": "Synthetic engineering fixture",
            "source_url": "https://example.invalid/fixture", "attribution": "Synthetic fixture, no source verification",
            "license_notes": {"corpus": "Synthetic", "queries_and_qrels": "Synthetic"},
            "source_provenance": {"archive_sha256": "a"*64, "source_receipt_sha256": "b"*64,
                                  "selection_sha256": "c"*64, "qrels_semantics": adapter.SEMANTICS},
            "files": deepcopy(adapter.FILES), "query_splits": {"dev": ["qd"], "validation": ["qv"], "test": ["qt"]},
            "comparison": deepcopy(adapter.COMPARISON), "limits": deepcopy(adapter.LIMITS)}


class RelevanceRetrievalAdapterTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.spec = fixture_spec()
        self.write_json("spec.json", self.spec)
        docs = [{"_id": doc, "title": text, "text": text, "metadata": {}}
                for doc, text in (("a", "cat dog"), ("b", "dog"), ("c", "fish"), ("qd", "cat cat cat"))]
        queries = [{"_id": qid, "text": text, "metadata": {}}
                   for qid, text in (("qd", "cat"), ("qv", "unseen token"), ("qt", "fish"))]
        self.write_rows("corpus.jsonl", docs)
        self.write_rows("queries.jsonl", queries)
        (self.root / "qrels-train.tsv").write_text("query-id\tcorpus-id\tscore\nqd\ta\t2\nqv\tb\t1\n")
        (self.root / "qrels-test.tsv").write_text("query-id\tcorpus-id\tscore\nqt\tc\t1\nqt\tmissing\t2\n")
        (self.root / "license.md").write_text("Synthetic engineering license notice.\n")

    def write_json(self, name, value):
        (self.root / name).write_text(canonical(value))

    def write_rows(self, name, rows):
        (self.root / name).write_text("\n".join(canonical(row) for row in rows) + "\n")

    def captured(self):
        return adapter.capture_source(self.root)

    def test_roundtrip_keeps_raw_grades_missing_positive_and_separate_identity(self):
        before = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in self.root.iterdir()}
        packet = self.captured()
        self.assertEqual(adapter.load_source(canonical(packet).encode()), packet)
        self.assertEqual(packet["scope"]["missing_positive_document_ids"], ["missing"])
        self.assertEqual(packet["scope"]["missing_positive_document_count"], 1)
        self.assertEqual(packet["scope"]["missing_positive_qrel_pairs"], 1)
        self.assertEqual(adapter._checked(packet)[3]["test"]["qt"], {"c": 1, "missing": 2})
        self.assertEqual(before, {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in self.root.iterdir()})
        with self.assertRaises(ResearchError):
            citation.load_source(canonical(packet).encode())

    def test_binary_metrics_keep_missing_grade_two_in_denominator(self):
        tool = adapter.execute(self.captured())
        result = tool["result"]
        for row in result["per_query_metrics"]:
            if row["query_id"] == "qt":
                self.assertEqual(row["metrics"]["recall@20"], .5)
                self.assertAlmostEqual(row["metrics"]["ndcg@10"], 1 / (1 + 1 / math.log2(3)))
                self.assertEqual(row["qrel_locator"]["document_grades"], {"c": 1, "missing": 2})
        self.assertEqual(result["comparison"]["baseline"], "bm25")
        self.assertEqual(result["comparison"]["candidate"], "tfidf_cosine")
        self.assertTrue(any("not canonical graded" in note for note in result["limitations"]))
        self.assertEqual(tool["new_fits"], 0)
        self.assertEqual(tool["model_calls"], 0)
        self.assertFalse(tool["scientific_validation"])
        self.assertTrue(any(row["query_id"] == "qv" for row in result["adverse_queries"]))

    def test_candidate_delta_orientation_is_tfidf_minus_bm25(self):
        rows = [{"split": split, "query_id": split, "method": method,
                 "metrics": {name: value for name in lexical.METRICS}}
                for split in ("dev", "validation", "test")
                for method, value in (("bm25", .8), ("tfidf_cosine", .2))]
        summary, deltas, adverse = adapter._paired(rows)
        self.assertEqual(len(adverse), 3)
        for row in deltas:
            self.assertEqual(row["loss_metrics"], list(lexical.METRICS))
            self.assertAlmostEqual(row["delta"]["recall@20"], -.6)
        self.assertEqual(summary["splits"]["test"]["paired_candidate_minus_baseline"]["recall@20"]["losses"], 1)

    def test_identical_ids_excluded_before_top_twenty_with_stable_ties(self):
        docs = {f"doc-{i:02d}": {"title": "equal", "text": "equal"} for i in range(22)}
        index = lexical.build_index(docs)
        for method in lexical.METHODS:
            rank = adapter.retrieve("equal", index, method, exclude_doc_id="doc-00")
            self.assertEqual(rank, [f"doc-{i:02d}" for i in range(1, 21)])
            expected = lexical.retrieve("equal", index, method)
            self.assertEqual(adapter.retrieve("equal", index, method, exclude_doc_id="absent"), expected)
        tool = adapter.execute(self.captured())
        self.assertTrue(all(row["query_id"] not in row["ranking"] for row in tool["result"]["rankings"]))

    def test_rankings_complete_before_first_label_score(self):
        calls = []
        original_rank, original_score = adapter.retrieve, lexical.metrics
        def rank(*args, **kwargs):
            calls.append(args[2])
            return original_rank(*args, **kwargs)
        def score(*args):
            self.assertEqual(len(calls), 6)
            return original_score(*args)
        with patch.object(adapter, "retrieve", side_effect=rank), patch.object(lexical, "metrics", side_effect=score):
            tool = adapter.execute(self.captured())
        self.assertEqual(tool["result"]["rankings_before_scoring_sha256"], fingerprint(tool["result"]["rankings"]))

    def test_saved_audit_never_ranks_scores_or_rebuilds_and_rejects_citation(self):
        tool = adapter.execute(self.captured())
        before = deepcopy(tool)
        parameters = {"based_on_action_id": "action-fixture", "based_on_result_sha256": "f"*64}
        with patch.object(adapter, "retrieve", side_effect=AssertionError("No new rank")), \
             patch.object(lexical, "retrieve", side_effect=AssertionError("No legacy rank")), \
             patch.object(lexical, "build_index", side_effect=AssertionError("No new index")), \
             patch.object(lexical, "metrics", side_effect=AssertionError("No qrel rescoring")):
            self.assertTrue(adapter.AUDIT.eligible(tool))
            audit = adapter.AUDIT.execute_saved(tool, parameters)
        self.assertEqual(tool, before)
        self.assertEqual(audit["result"]["usage"]["ranking_calls"], 0)
        self.assertEqual(audit["result"]["usage"]["scoring_calls"], 0)
        self.assertEqual(audit["result"]["predecessor"], parameters)
        self.assertEqual(adapter.AUDIT.next_decision(audit)["project_status"], "waiting")
        disguised = deepcopy(audit)
        disguised["result"]["scope"]["qrels_semantics"] = citation.SEMANTICS
        with self.assertRaises(ResearchError):
            adapter.AUDIT.next_decision(disguised)
        malformed = deepcopy(audit)
        del malformed["result"]["source_snapshot_sha256"]
        with self.assertRaises(ResearchError):
            adapter.AUDIT.next_decision(malformed)
        malformed = deepcopy(audit)
        del malformed["evidence_refs"]
        with self.assertRaises(ResearchError):
            adapter.AUDIT.next_decision(malformed)
        old = deepcopy(tool)
        old["tool_id"] = citation.TOOL_ID
        old["schema_version"] = "citation-retrieval-result-v1"
        self.assertFalse(adapter.AUDIT.eligible(old))

    def test_tampered_scope_semantics_rank_summary_and_grades_rejected(self):
        packet = self.captured()
        packet["scope"]["qrels_semantics"] = citation.SEMANTICS
        packet["snapshot_sha256"] = fingerprint({k: v for k, v in packet.items() if k != "snapshot_sha256"})
        with self.assertRaises(ResearchError):
            adapter.load_source(canonical(packet).encode())
        tool = adapter.execute(self.captured())
        variants = []
        for key, value in (("qrels_semantics", citation.SEMANTICS), ("contract", "citation-retrieval-fixed-pair-v1"),
                           ("missing_positive_document_count", 0)):
            value_tool = deepcopy(tool)
            value_tool["result"]["scope"][key] = value
            variants.append(value_tool)
        changed = deepcopy(tool)
        changed["result"]["rankings"][0]["ranking"].append("qd")
        variants.append(changed)
        changed = deepcopy(tool)
        changed["result"]["per_query_metrics"][0]["qrel_locator"]["document_grades"]["a"] = 3
        variants.append(changed)
        changed = deepcopy(tool)
        changed["result"]["usage"]["index_builds"] = True
        variants.append(changed)
        for value in variants:
            self.assertFalse(adapter.AUDIT.eligible(value))
        changed = deepcopy(tool)
        changed["result"]["paired_summary"]["splits"]["dev"]["arms"]["bm25"]["queries"] = 8
        with self.assertRaises(ResearchError):
            adapter.AUDIT.execute_saved(changed, {"based_on_action_id": "a", "based_on_result_sha256": "a"*64})

    def test_extended_query_and_corpus_caps_do_not_change_old_contract(self):
        self.assertEqual(citation.LIMITS["max_corpus_rows"], 6000)
        self.assertEqual(citation.LIMITS["packet_bytes"], 16000000)
        rows = [{"_id": str(i), "title": "", "text": "", "metadata": {}} for i in range(6001)]
        raw = ("\n".join(canonical(row) for row in rows) + "\n").encode()
        self.assertEqual(len(adapter._jsonl(raw, True)[0]), 6001)
        for size in (4097, 32768):
            row = {"_id": "q", "text": "x"*size, "metadata": {}}
            self.assertEqual(len(adapter._jsonl(canonical(row).encode(), False)[0]), 1)
        row = {"_id": "q", "text": "x"*32769, "metadata": {}}
        with self.assertRaises(ResearchError):
            adapter._jsonl(canonical(row).encode(), False)
        self.spec["comparison"]["ignore_identical_ids"] = 1
        self.write_json("spec.json", self.spec)
        with self.assertRaises(ResearchError):
            self.captured()

    def test_unknown_query_duplicate_and_nonpositive_or_unregistered_grades_rejected(self):
        for row in ("unknown\tc\t1\n", "qt\tc\t0\n", "qt\tc\t3\n", "qt\tc\t1.0\n", "qt\tc\t1\nqt\tc\t2\n"):
            (self.root / "qrels-test.tsv").write_text("query-id\tcorpus-id\tscore\n" + row)
            with self.assertRaises(ResearchError):
                self.captured()


if __name__ == "__main__":
    unittest.main()
