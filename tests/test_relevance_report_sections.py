"""Saved dictionaries only: no target corpus, ranker, scorer, fit or model."""
import base64
from copy import deepcopy
import hashlib
import unittest
from unittest.mock import patch

from autoresearch import cpu_report_sections as cpu, project_report, retrieval_lexical
from autoresearch.contracts import ResearchError, canonical, fingerprint


def asset(name, raw):
    return {"file_name": name, "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw),
            "bytes_base64": base64.b64encode(raw).decode("ascii")}


def packet():
    # Reporting validates byte identities and semantic declarations, not the
    # truth of externally supplied provenance or permission to use the data.
    spec = {"schema_version": "relevance-retrieval-spec-v1", "files": cpu.FILES["relevance"],
            "source_url": "urn:fixture:relevance-report", "attribution": "Synthetic reporting fixture",
            "license_notes": {"corpus": "Corpus fixture licence", "queries_and_qrels": "Judgments fixture licence"},
            "source_provenance": {"qrels_semantics": "positive_relevance_binary_projection"}}
    assets = {role: asset(name, ("report fixture " + role).encode("utf-8")) for role, name in cpu.FILES["relevance"].items()}
    value = {"schema_version": "cpu-research-source-v1", "task_kind": "relevance_retrieval", "spec": spec,
             "spec_source": asset("spec.json", canonical(spec).encode("utf-8")), "assets": assets,
             "scope": {"contract": "relevance-retrieval-fixed-pair-v1", "qrels_semantics": "positive_relevance_binary_projection",
                       "input_identities": {role: {key: entry[key] for key in ("sha256", "bytes")} for role, entry in assets.items()}}}
    return reseal(value)


def reseal(value):
    value["spec_source"] = asset("spec.json", canonical(value["spec"]).encode("utf-8"))
    value["snapshot_sha256"] = fingerprint({key: child for key, child in value.items() if key != "snapshot_sha256"})
    return value


def saved_entry():
    # BM25 baseline .75, TF-IDF candidate .25: reversed from the citation pair.
    baseline = {name: .75 for name in retrieval_lexical.METRICS}
    candidate = {name: .25 for name in retrieval_lexical.METRICS}
    split = {"arms": {"bm25": {"queries": 13, "metrics": baseline}, "tfidf_cosine": {"queries": 13, "metrics": candidate}},
             "paired_candidate_minus_baseline": {name: {"mean": -.5, "wins": 1, "ties": 2, "losses": 10}
                                                   for name in retrieval_lexical.METRICS}}
    rankings = [{"query_id": "q" + str(index), "method": method, "ranking": ["doc-a"]}
                for index in range(13) for method in ("bm25", "tfidf_cosine")]
    body = {"paired_summary": {"splits": {name: deepcopy(split) for name in ("dev", "validation", "test")}},
            "rankings": rankings, "rankings_before_scoring_sha256": fingerprint(rankings),
            "per_query_metrics": [{"saved": True} for _ in rankings],
            "adverse_queries": [{"query_id": "q" + str(index), "split": "test", "loss_metrics": ["recall@5"],
                                 "baseline": baseline, "candidate": candidate} for index in range(13)]}
    return {"action_id": "saved-fixture-action", "command": cpu.PRIMARY["relevance"], "status": "completed", "tool_result": {"result": body}}


class RelevanceReportTests(unittest.TestCase):
    def test_registration_and_empty_summary_use_relevance_semantics(self):
        self.assertEqual(project_report.KINDS["research.relevance-fixed-pair"], "relevance")
        self.assertEqual(project_report._report_title("relevance", []), "文档相关性检索对照与保存错误诊断报告")
        value = project_report._summary("relevance", {}, [])
        self.assertFalse(value["has_completed_primary_result"])
        self.assertEqual(value["rows"], [])
        self.assertIn("grade>0", value["result_notice"])
        self.assertIn("缺失", value["result_notice"])
        self.assertIn("因果收益", value["result_notice"])
        self.assertNotIn("cited_doc_ids", value["result_notice"])

    def test_saved_macro_values_keep_bm25_baseline_and_tfidf_candidate(self):
        entry = saved_entry()
        before = deepcopy(entry)
        with patch.object(retrieval_lexical, "build_index", side_effect=AssertionError("no indexing")), \
             patch.object(retrieval_lexical, "retrieve", side_effect=AssertionError("no ranking")), \
             patch.object(retrieval_lexical, "metrics", side_effect=AssertionError("no scoring")):
            value = cpu.summary("relevance", {"source_scope": {"document_count": 23}}, [entry])
        self.assertEqual(len(value["rows"]), 15)
        self.assertEqual(value["headers"][2:4], ["BM25 基线", "TF-IDF 候选"])
        self.assertEqual(next(row for row in value["rows"] if row[:2] == ["test", "recall@5"])[2:], ["0.75", "0.25", "-0.5", "1/2/10"])
        self.assertEqual(entry, before)

    def test_source_manifest_verifies_each_asset_and_correct_licence_objects(self):
        value = packet()
        rows, provenance = cpu.source_manifest(value, "relevance")
        self.assertEqual(len(rows), 6)
        self.assertEqual(next(row for row in rows if row.get("asset_role") == "corpus")["license_note"], "Corpus fixture licence")
        self.assertEqual(next(row for row in rows if row.get("asset_role") == "test_qrels")["license_note"], "Judgments fixture licence")
        self.assertEqual(provenance["verification"], "embedded_bytes_checked_declarations_unverified")
        self.assertEqual(provenance["source_provenance"]["qrels_semantics"], "positive_relevance_binary_projection")

    def test_semantic_substitution_and_changed_asset_identity_reject(self):
        for mode in ("task", "spec", "contract", "provenance", "licence", "bytes", "scope"):
            value = packet()
            if mode == "task": value["task_kind"] = "citation_retrieval"
            elif mode == "spec": value["spec"]["schema_version"] = "citation-retrieval-spec-v1"
            elif mode == "contract": value["scope"]["contract"] = "citation-retrieval-fixed-pair-v1"
            elif mode == "provenance": value["spec"]["source_provenance"]["qrels_semantics"] = "cited_doc_ids_not_support_refute"
            elif mode == "licence": value["spec"]["license_notes"] = {"abstracts": "wrong", "claims_and_qrels": "wrong"}
            elif mode == "bytes": value["assets"]["corpus"]["sha256"] = "0" * 64
            else: value["scope"]["input_identities"]["queries"]["bytes"] += 1
            reseal(value)
            with self.subTest(mode=mode), self.assertRaises(ResearchError):
                cpu.source_manifest(value, "relevance")

    def test_adverse_sample_keeps_complete_saved_array_and_coordinates_pointer(self):
        entry = saved_entry()
        before = deepcopy(entry)
        value = {"kind": "relevance", "action_results": [entry]}
        sections = cpu.sections(value)
        section = next(item for item in sections if item["title"] == "检索覆盖损失与完整排名")
        self.assertEqual(len(section["rows"]), 12)
        self.assertTrue(any("12/13" in line for line in section["paragraphs"]))
        self.assertTrue(any("action_results[0].tool_result.result.rankings" in line for line in section["paragraphs"]))
        self.assertEqual(len(entry["tool_result"]["result"]["adverse_queries"]), 13)
        self.assertEqual(entry, before)

    def test_saved_audit_section_is_linked_without_recomputation(self):
        entry = {"action_id": "saved-audit", "command": cpu.AUDITS["relevance"], "status": "completed",
                 "tool_result": {"result": {"predecessor": {"based_on_action_id": "saved-primary", "based_on_result_sha256": "f" * 64}}}}
        before = deepcopy(entry)
        sections = cpu.sections({"kind": "relevance", "action_results": [entry]})
        self.assertEqual(len(sections), 1)
        self.assertIn("saved-primary", " ".join(sections[0]["paragraphs"]))
        self.assertIn("不重新排名", " ".join(sections[0]["paragraphs"]))
        self.assertEqual(entry, before)


if __name__ == "__main__":
    unittest.main()
