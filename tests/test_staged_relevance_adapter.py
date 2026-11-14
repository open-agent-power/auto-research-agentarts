"""Development-only synthetic engineering fixtures; no prior study, model or fits."""
import copy
import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from autoresearch import staged_relevance_adapter as adapter, relevance_retrieval_adapter as base, retrieval_lexical as lexical
from autoresearch.contracts import ResearchError, canonical, fingerprint


def _rows(rows):
    return "\n".join(canonical(row) for row in rows) + "\n"


class StagedDevelopmentTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        docs = [{"_id": doc, "title": text, "text": text, "metadata": {}}
                for doc, text in (("a", "cat dog"), ("b", "dog"), ("c", "fish"), ("qd", "cat"))]
        queries = [{"_id": qid, "text": text, "metadata": {}} for qid, text in (("qd", "cat"), ("qv", "unknown token"))]
        (self.root / "corpus.jsonl").write_text(_rows(docs))
        (self.root / "queries.jsonl").write_text(_rows(queries))
        (self.root / "qrels.tsv").write_text("query-id\tcorpus-id\tscore\nqd\ta\t2\nqv\tb\t1\nqv\tmissing\t2\n")
        (self.root / "license.md").write_text("Synthetic engineering fixture, no external research source.\n")
        # These identifiers derive from actual fixture bytes, not asserted external provenance.
        corpus = (self.root / "corpus.jsonl").read_bytes()
        receipt = canonical({"corpus_sha256": hashlib.sha256(corpus).hexdigest()}).encode()
        selection = canonical({"dev": ["qd"], "validation": ["qv"]}).encode()
        self.spec = {"schema_version": "staged-relevance-development-spec-v1", "dataset_label": "Synthetic engineering data",
            "source_url": "https://example.invalid/local-fixture", "attribution": "Local synthetic fixture",
            "license_notes": {"corpus": "Synthetic", "queries_and_qrels": "Synthetic"},
            "source_provenance": {"archive_sha256": hashlib.sha256(corpus).hexdigest(),
                                  "source_receipt_sha256": hashlib.sha256(receipt).hexdigest(),
                                  "selection_sha256": hashlib.sha256(selection).hexdigest(), "qrels_semantics": adapter.SEMANTICS},
            "files": copy.deepcopy(adapter.FILES), "query_splits": {"dev": ["qd"], "validation": ["qv"]},
            "comparison": copy.deepcopy(adapter.COMPARISON), "limits": copy.deepcopy(adapter.LIMITS)}
        self.write_spec()

    def write_spec(self):
        (self.root / "spec.json").write_text(canonical(self.spec))

    def capture(self):
        return adapter.capture_source(self.root)

    def test_capture_never_reads_final_assets_and_result_contains_no_final_rows(self):
        (self.root / "final-queries.jsonl").write_text("SECRET_FINAL_QUERY_SENTINEL")
        (self.root / "final-qrels.tsv").write_text("SECRET_FINAL_LABEL_SENTINEL")
        reads = []
        original = base.reader._read_file
        def checked(path, maximum):
            reads.append(Path(path).name)
            self.assertIn(Path(path).name, set(adapter.FILES.values()) | {"spec.json"})
            return original(path, maximum)
        with patch.object(base.reader, "_read_file", side_effect=checked):
            packet = self.capture()
            self.assertEqual(adapter.load_source(canonical(packet).encode()), packet)
            tool = adapter.execute(packet)
        self.assertEqual(set(reads), set(adapter.FILES.values()) | {"spec.json"})
        self.assertNotIn("SECRET_FINAL", canonical(packet) + canonical(tool))
        self.assertEqual(set(packet["assets"]), {"corpus", "queries", "qrels", "license"})
        self.assertEqual(packet["stage"], tool["result"]["stage"])
        self.assertEqual(set(tool["result"]["paired_summary"]["splits"]), {"dev", "validation"})
        self.assertEqual({row["split"] for row in tool["result"]["rankings"]}, {"dev", "validation"})
        self.assertEqual(tool["result"]["usage"]["ranking_calls"], 4)
        self.assertEqual(tool["result"]["usage"]["scoring_calls"], 4)
        self.assertEqual(tool["result"]["scope"]["missing_positive_document_ids"], ["missing"])
        self.assertEqual(tool["result"]["scope"]["missing_positive_qrel_pairs"], 1)
        for row in tool["result"]["per_query_metrics"]:
            if row["query_id"] == "qv":
                self.assertEqual(row["qrel_locator"]["document_grades"], {"b": 1, "missing": 2})
                self.assertEqual(row["metrics"]["recall@20"], 0)
        self.assertEqual(tool["model_calls"], 0)
        self.assertEqual(tool["new_fits"], 0)
        self.assertFalse(tool["scientific_validation"])

    def test_extra_queries_qrels_final_splits_and_metadata_rejected(self):
        queries = self.root / "queries.jsonl"
        original = queries.read_text()
        queries.write_text(original + canonical({"_id": "final", "text": "unrelated", "metadata": {}}) + "\n")
        with self.assertRaises(ResearchError):
            self.capture()
        queries.write_text(original)
        qrels = self.root / "qrels.tsv"
        labels = qrels.read_text()
        qrels.write_text(labels + "final\ta\t1\n")
        with self.assertRaises(ResearchError):
            self.capture()
        qrels.write_text(labels)
        qrels.write_text(labels + '"unterminated')
        with self.assertRaises(ResearchError):
            self.capture()
        qrels.write_text(labels)
        self.spec["query_splits"]["test"] = ["final"]
        self.write_spec()
        with self.assertRaises(ResearchError):
            self.capture()
        del self.spec["query_splits"]["test"]
        self.write_spec()
        queries.write_text(_rows([{"_id": "qd", "text": "cat", "metadata": {"hidden": "label"}},
                                  {"_id": "qv", "text": "unknown token", "metadata": {}}]))
        with self.assertRaises(ResearchError):
            self.capture()

    def test_roundtrip_tampered_packet_and_no_fake_empty_test(self):
        packet = self.capture()
        self.assertEqual(adapter.load_source(canonical(packet).encode()), packet)
        changed = copy.deepcopy(packet)
        changed["assets"]["qrels"]["sha256"] = "a" * 64
        changed["snapshot_sha256"] = fingerprint({k: v for k, v in changed.items() if k != "snapshot_sha256"})
        with self.assertRaises(ResearchError):
            adapter.load_source(canonical(changed).encode())
        forged = copy.deepcopy(packet)
        forged["assets"]["test_qrels"] = {"file_name": "test.tsv", "sha256": "0" * 64, "bytes": 0, "bytes_base64": ""}
        forged["snapshot_sha256"] = fingerprint({k: v for k, v in forged.items() if k != "snapshot_sha256"})
        with self.assertRaises(ResearchError):
            adapter.load_source(canonical(forged).encode())

    def test_ranking_completes_before_metrics_and_same_id_exclusion(self):
        packet = self.capture()
        calls = []
        rank, metrics = base.retrieve, lexical.metrics
        def traced(*args, **kwargs):
            calls.append(args[2])
            return rank(*args, **kwargs)
        def score(*args):
            self.assertEqual(len(calls), 4)
            return metrics(*args)
        with patch.object(base, "retrieve", side_effect=traced), patch.object(lexical, "metrics", side_effect=score):
            tool = adapter.execute(packet)
        for row in tool["result"]["rankings"]:
            self.assertNotIn(row["query_id"], row["ranking"])
        self.assertEqual(tool["result"]["rankings_before_scoring_sha256"], fingerprint(tool["result"]["rankings"]))

    def test_identical_query_id_is_removed_before_top_twenty_and_replaced(self):
        docs = [{"_id": f"doc-{i:02d}", "title": "equal", "text": "equal", "metadata": {}}
                for i in range(22)]
        queries = [{"_id": "doc-00", "text": "equal", "metadata": {}},
                   {"_id": "qv", "text": "unknown token", "metadata": {}}]
        (self.root / "corpus.jsonl").write_text(_rows(docs))
        (self.root / "queries.jsonl").write_text(_rows(queries))
        (self.root / "qrels.tsv").write_text("query-id\tcorpus-id\tscore\ndoc-00\tdoc-01\t1\nqv\tdoc-02\t1\n")
        self.spec["query_splits"]["dev"] = ["doc-00"]
        corpus_sha = hashlib.sha256((self.root / "corpus.jsonl").read_bytes()).hexdigest()
        self.spec["source_provenance"].update(
            archive_sha256=corpus_sha,
            source_receipt_sha256=hashlib.sha256(canonical({"corpus_sha256": corpus_sha}).encode()).hexdigest(),
            selection_sha256=hashlib.sha256(canonical(self.spec["query_splits"]).encode()).hexdigest())
        self.write_spec()
        result = adapter.execute(self.capture())["result"]
        expected = [f"doc-{i:02d}" for i in range(1, 21)]
        for row in result["rankings"]:
            if row["query_id"] == "doc-00":
                self.assertEqual(row["ranking"], expected)

    def test_saved_audit_never_reranks_rescores_or_fits_and_rejects_tamper(self):
        tool = adapter.execute(self.capture())
        before = copy.deepcopy(tool)
        predecessor = {"based_on_action_id": "action-original", "based_on_result_sha256": hashlib.sha256(b"fixture").hexdigest()}
        with patch.object(base, "retrieve", side_effect=AssertionError("no ranking")), \
             patch.object(lexical, "metrics", side_effect=AssertionError("no rescoring")), \
             patch.object(lexical, "build_index", side_effect=AssertionError("no index")):
            self.assertTrue(adapter.AUDIT.eligible(tool))
            audit = adapter.AUDIT.execute_saved(tool, predecessor)
            self.assertEqual(adapter.AUDIT.next_decision(audit)["project_status"], "waiting")
            self.assertEqual(adapter.next_decision(tool)["next_action"]["method_id"], adapter.AUDIT_TOOL_ID)
        self.assertEqual(tool, before)
        self.assertEqual(audit["result"]["predecessor"], predecessor)
        self.assertEqual(audit["result"]["usage"]["scoring_calls"], 0)
        malformed_audit = copy.deepcopy(audit)
        malformed_audit["result"]["scope"] = []
        with self.assertRaises(ResearchError):
            adapter.AUDIT.next_decision(malformed_audit)
        for change in ("summary", "scope", "ranking", "qrel", "split"):
            damaged = copy.deepcopy(tool)
            result = damaged["result"]
            if change == "summary":
                result["paired_summary"]["splits"]["validation"]["arms"]["bm25"]["metrics"]["recall@20"] = .5
            elif change == "scope":
                result["scope"]["stage"] = "final"
            elif change == "ranking":
                result["rankings"][0]["ranking"].append("forged")
            elif change == "qrel":
                result["per_query_metrics"][0]["qrel_locator"]["document_grades"]["a"] = 1
            else:
                result["per_query_metrics"][0]["split"] = "test"
            with self.subTest(change=change):
                self.assertFalse(adapter.AUDIT.eligible(damaged))
                with self.assertRaises(ResearchError):
                    adapter.AUDIT.execute_saved(damaged, predecessor)


if __name__ == "__main__":
    unittest.main()
