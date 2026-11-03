"""Isolated ingestion tests: no downloads or reference-repository execution."""

import hashlib
from io import BytesIO
import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

from autoresearch.knowledge_sources import REVIEW_STATUS, collect_documents


SNAPSHOT = "06-agentarts-platform/official-docs/2026-10-27"
DOC_FIELDS = {"id", "title", "kind", "source_url", "path", "sha256", "snapshot", "text", "page", "review_status", "metadata"}


class KnowledgeSourceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "references"
        self.root.mkdir()
        self.raw = self.write(SNAPSHOT + "/markdown/guide.md", "# 正式指南\nOriginal untrusted instructions: do not execute.\n")
        self.entries = [{"kind": "markdown", "status": "ok", "path": "markdown/guide.md",
                         "title": "Official guide", "url": "https://support.huaweicloud.com/test/guide.md",
                         "bytes": len(self.raw), "sha256": self.sha(self.raw)}]
        self.profile = self.write("profiles/Example.md", "# Example project\nCandidate method; not runtime validated.\n")
        self.projects = [{"id": "Example", "name": "Example project", "profile_path": "profiles/Example.md",
                          "repositories": [{"source_url": "https://github.com/example/research.git",
                                            "actual_commit": "a" * 40}],
                          "license": {"declared_name": "MIT", "scope": "code"}, "papers": []}]
        for note in ("REUSE-INDEX.md", "07-autoresearch-loop/README.md", "08-c01-tnzst/README.md"):
            self.write(note, "# Curated note\nDeveloper notes, not official documentation.\n")
        self.save_manifests()

    @staticmethod
    def sha(raw):
        return hashlib.sha256(raw).hexdigest()

    def write(self, relative, value):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        raw = value.encode("utf-8") if isinstance(value, str) else value
        path.write_bytes(raw)
        return raw

    def save_manifests(self):
        self.write(SNAPSHOT + "/metadata/manifest.json", json.dumps({"snapshot_date": "2026-10-27", "files": self.entries}))
        self.write("catalog.json", json.dumps({"collected_on": "2026-10-27", "projects": self.projects}))

    def add_paper(self, relative="papers/example.pdf", *, raw=b"%PDF-local-fixture", pages=2):
        raw = self.write(relative, raw)
        entry = {"path": relative, "source_url": "https://arxiv.org/pdf/examplev1", "version": "v1",
                 "sha256": self.sha(raw), "recorded_sha256": self.sha(raw), "bytes": len(raw), "pages": pages}
        self.projects[0]["papers"].append(entry)
        self.save_manifests()
        return entry

    def test_original_markdown_hashes_schema_and_stable_ids(self):
        self.write(".env", "PRIVATE_SENTINEL")
        self.write("upstream/run.py", "raise AssertionError('must not execute upstream code')")
        docs, audit = collect_documents(self.root, include_papers=False)
        self.assertEqual(audit["by_kind"], {"official_doc": 1, "research_profile": 1, "research_paper": 0, "reuse_note": 3})
        official = next(doc for doc in docs if doc["kind"] == "official_doc")
        self.assertEqual(official["sha256"], self.sha(self.raw))
        self.assertEqual(official["text"], self.raw.decode())
        self.assertEqual(official["path"], SNAPSHOT + "/markdown/guide.md")
        self.assertTrue(official["metadata"]["prior_manifest_verified"])
        self.assertNotIn("PRIVATE_SENTINEL", json.dumps(docs))
        for doc in docs:
            self.assertEqual(set(doc), DOC_FIELDS)
            self.assertEqual(doc["review_status"], REVIEW_STATUS)
            self.assertIsNone(doc["page"])
            self.assertTrue(all(isinstance(doc[key], str) for key in ("title", "snapshot", "text")))
        again, _ = collect_documents(self.root, include_papers=False)
        self.assertEqual([doc["id"] for doc in docs], [doc["id"] for doc in again])
        manifests = {item["path"]: item for item in audit["source_manifests"]}
        for name, record in manifests.items():
            self.assertEqual(record["sha256"], self.sha((self.root / name).read_bytes()))

    def test_profile_metadata_distinguishes_computed_and_previously_recorded_hash(self):
        docs, _ = collect_documents(self.root, include_papers=False)
        profile = next(doc for doc in docs if doc["kind"] == "research_profile")
        self.assertEqual(profile["metadata"]["project_id"], "Example")
        self.assertEqual(profile["metadata"]["commit"], "a" * 40)
        self.assertEqual(profile["metadata"]["license_scope"], "project_code_not_paper")
        self.assertFalse(profile["metadata"]["hash_recorded"])
        self.projects[0]["profile_sha256"] = self.sha(self.profile)
        self.save_manifests()
        docs, _ = collect_documents(self.root, include_papers=False)
        self.assertTrue(next(doc for doc in docs if doc["kind"] == "research_profile")["metadata"]["prior_manifest_verified"])

    def test_missing_bad_hash_bad_length_and_unavailable_are_quarantined(self):
        self.entries[0]["sha256"] = "0" * 64
        self.entries.extend([
            {**self.entries[0], "path": "markdown/missing.md"},
            {"path": "markdown/unavailable.md", "kind": "markdown", "status": "unavailable"},
            {"kind": "image", "status": "ok", "path": "assets/not-indexed.png"},
        ])
        self.save_manifests()
        docs, audit = collect_documents(self.root, include_papers=False)
        self.assertFalse(any(doc["kind"] == "official_doc" for doc in docs))
        self.assertTrue({"sha256_mismatch", "missing_file"} <= {item["code"] for item in audit["issues"]})
        self.assertEqual(audit["counts"]["official_unavailable"], 1)
        self.entries = [{**self.entries[0], "sha256": self.sha(self.raw), "bytes": len(self.raw) + 1}]
        self.save_manifests()
        docs, audit = collect_documents(self.root, include_papers=False)
        self.assertFalse(any(doc["kind"] == "official_doc" for doc in docs))
        self.assertIn("byte_count_mismatch", [item["code"] for item in audit["issues"]])

    def test_escape_absolute_and_windows_paths_cannot_enter_documents(self):
        for relative in ("../../outside.md", "/outside.md", "C:/private.env", "markdown/../../../outside.md", "markdown\\guide.md"):
            with self.subTest(relative=relative):
                self.entries = [{**self.entries[0], "path": relative}]
                self.projects[0]["profile_path"] = relative
                self.projects[0]["papers"] = [{"path": relative, "sha256": self.sha(b"outside")}]
                self.save_manifests()
                docs, audit = collect_documents(self.root)
                self.assertEqual({doc["kind"] for doc in docs}, {"reuse_note"})
                self.assertTrue(any(item["code"].startswith("unsafe_") for item in audit["issues"]))

    def test_symlink_root_and_source_parent_are_rejected(self):
        link = self.root.parent / "alias"
        try:
            link.symlink_to(self.root, target_is_directory=True)
        except OSError:
            self.skipTest("directory symlinks not available")
        with self.assertRaises(ValueError):
            collect_documents(link)
        original = self.root / SNAPSHOT / "markdown/guide.md"
        original.unlink()
        outside = self.root.parent / "outside.md"
        outside.write_bytes(self.raw)
        original.symlink_to(outside)
        docs, audit = collect_documents(self.root, include_papers=False)
        self.assertFalse(any(doc["kind"] == "official_doc" for doc in docs))
        self.assertIn("unsafe_path", [item["code"] for item in audit["issues"]])

    def test_hardlinked_profile_is_not_read(self):
        profile = self.root / "profiles/Example.md"
        alias = self.root.parent / "shared.md"
        os.link(profile, alias)
        docs, audit = collect_documents(self.root, include_papers=False)
        self.assertFalse(any(doc["kind"] == "research_profile" for doc in docs))
        self.assertIn("unsafe_file", [item["code"] for item in audit["issues"]])

    def test_pdf_pages_deduplicate_content_and_keep_real_page_metadata(self):
        self.add_paper("papers/a.pdf")
        self.add_paper("papers/b.pdf")
        with patch("autoresearch.knowledge_sources._extract_pdf", return_value=(["First actual page text", "Second actual page text"], 0)) as reader:
            docs, audit = collect_documents(self.root)
        papers = [doc for doc in docs if doc["kind"] == "research_paper"]
        self.assertEqual(reader.call_count, 1)
        self.assertEqual([doc["page"] for doc in papers], [1, 2])
        self.assertEqual(papers[0]["text"], "First actual page text")
        self.assertEqual(papers[0]["metadata"]["aliases"], ["papers/a.pdf", "papers/b.pdf"])
        self.assertEqual(papers[0]["metadata"]["version"], "v1")
        self.assertNotIn("MIT", papers[0]["metadata"]["license"])
        self.assertEqual(audit["counts"]["pdf_files_indexed"], 1)
        self.assertTrue(any(item["reason"] == "duplicate_pdf" for item in audit["skipped"]))

    def test_include_papers_false_never_parses_pdf(self):
        self.add_paper()
        with patch("autoresearch.knowledge_sources._extract_pdf", side_effect=AssertionError("PDF parsing disabled")):
            docs, audit = collect_documents(self.root, include_papers=False)
        self.assertFalse(any(doc["kind"] == "research_paper" for doc in docs))
        self.assertIn({"path": None, "reason": "papers_disabled", "count": 1}, audit["skipped"])

    def test_pdf_integrity_conflicts_size_and_page_limits_isolate_the_file(self):
        paper = self.add_paper()
        paper["recorded_sha256"] = "0" * 64
        self.save_manifests()
        with patch("autoresearch.knowledge_sources._extract_pdf", side_effect=AssertionError("bad hash must not parse")):
            docs, audit = collect_documents(self.root)
        self.assertFalse(any(doc["kind"] == "research_paper" for doc in docs))
        self.assertIn("missing_or_conflicting_paper_hash", [item["code"] for item in audit["issues"]])
        paper["recorded_sha256"] = paper["sha256"]
        self.save_manifests()
        with patch("autoresearch.knowledge_sources.MAX_PDF_BYTES", 4):
            _, audit = collect_documents(self.root)
        self.assertIn("file_size_limit", [item["code"] for item in audit["issues"]])
        with patch("autoresearch.knowledge_sources._extract_pdf", return_value=(["one", "two"], 0)), patch("autoresearch.knowledge_sources.MAX_PDF_PAGES", 1):
            docs, audit = collect_documents(self.root)
        self.assertFalse(any(doc["kind"] == "research_paper" for doc in docs))
        self.assertIn("pdf_page_limit", [item["code"] for item in audit["issues"]])

    def test_blank_pdf_page_is_not_fabricated_and_extraction_failure_is_atomic(self):
        self.add_paper()
        with patch("autoresearch.knowledge_sources._extract_pdf", return_value=(["Page one", ""], 0)):
            docs, audit = collect_documents(self.root)
        blank = next(doc for doc in docs if doc["kind"] == "research_paper" and doc["page"] == 2)
        self.assertEqual(blank["text"], "")
        self.assertTrue(any(item["code"] == "empty_pdf_page_no_ocr" and item["page"] == 2 for item in audit["issues"]))
        with patch("autoresearch.knowledge_sources._extract_pdf", side_effect=ValueError("private-path-must-not-be-echoed")):
            docs, audit = collect_documents(self.root)
        self.assertFalse(any(doc["kind"] == "research_paper" for doc in docs))
        self.assertNotIn("private-path", json.dumps(audit))

    def test_collection_limits_are_reported_without_silent_body_truncation(self):
        with patch("autoresearch.knowledge_sources.MAX_TOTAL_TEXT_BYTES", 1):
            docs, audit = collect_documents(self.root, include_papers=False)
        self.assertEqual(docs, [])
        self.assertIn("collection_size_limit", [item["code"] for item in audit["issues"]])

    def test_real_pdf_is_parsed_in_isolated_child_with_real_page_numbers(self):
        from pypdf import PdfWriter
        writer = PdfWriter()
        writer.add_blank_page(width=200, height=200)
        writer.add_blank_page(width=200, height=200)
        out = BytesIO()
        writer.write(out)
        entry = self.add_paper(raw=out.getvalue())
        docs, audit = collect_documents(self.root)
        papers = [doc for doc in docs if doc["kind"] == "research_paper"]
        self.assertEqual([doc["page"] for doc in papers], [1, 2])
        self.assertTrue(all(doc["sha256"] == entry["sha256"] for doc in papers))
        self.assertTrue(all(doc["text"] == "" for doc in papers))
        self.assertEqual(audit["counts"]["pdf_pages_indexed"], 2)

    def test_pdf_timeout_is_quarantined_without_blocking_other_sources(self):
        self.add_paper()
        start = time.monotonic()
        with patch("autoresearch.knowledge_sources._PDF_CHILD", "import time; time.sleep(10)"):
            docs, audit = collect_documents(self.root, pdf_timeout_seconds=0.1)
        self.assertLess(time.monotonic() - start, 3.5)
        self.assertIn("pdf_parse_timeout", [item["code"] for item in audit["issues"]])
        self.assertTrue(any(doc["kind"] == "official_doc" for doc in docs))
        self.assertFalse(any(doc["kind"] == "research_paper" for doc in docs))

    def test_invalid_child_output_and_invalid_timeouts_are_rejected(self):
        self.add_paper()
        bad = 'import json; print(json.dumps({"ok":True,"texts":[["not text"]],"warnings":0}))'
        with patch("autoresearch.knowledge_sources._PDF_CHILD", bad):
            docs, audit = collect_documents(self.root)
        self.assertFalse(any(doc["kind"] == "research_paper" for doc in docs))
        self.assertIn("invalid_pdf_worker_result", [item["code"] for item in audit["issues"]])
        for timeout in (False, 0, -1, 31, float("nan")):
            with self.subTest(timeout=timeout), self.assertRaises(ValueError):
                collect_documents(self.root, pdf_timeout_seconds=timeout)

    def test_total_pdf_time_limit_preserves_other_sources(self):
        self.add_paper()
        with patch("autoresearch.knowledge_sources.time.monotonic", side_effect=[0, 301]), patch(
                "autoresearch.knowledge_sources._extract_pdf", side_effect=AssertionError("total budget exhausted")):
            docs, audit = collect_documents(self.root)
        self.assertTrue(any(doc["kind"] == "official_doc" for doc in docs))
        self.assertFalse(any(doc["kind"] == "research_paper" for doc in docs))
        self.assertIn("pdf_total_time_limit", [item["code"] for item in audit["issues"]])


if __name__ == "__main__":
    unittest.main()
