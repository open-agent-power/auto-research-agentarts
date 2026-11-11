"""PDF boundaries and original page coordinates in extracted project knowledge."""
import copy
import hashlib
from io import BytesIO
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from autoresearch import project_knowledge, tabular_source
from autoresearch.contracts import ResearchError


class ProjectPdfSelectionTests(unittest.TestCase):
    def test_real_pdf_whole_and_partial_selections_keep_original_page_in_project_fts(self):
        from reportlab.pdfgen.canvas import Canvas
        buffer = BytesIO()
        pdf = Canvas(buffer)
        pdf.drawString(50, 750, "First page control text.")
        pdf.showPage()
        pdf.drawString(50, 750, "Froude coefficient reference.")
        pdf.drawString(50, 730, "Published scale remains unreviewed.")
        pdf.save()
        raw = buffer.getvalue()
        whole_locator = {"kind": "pdf_page", "value": "2"}
        whole = tabular_source.extract_selection(raw, whole_locator)
        start = whole["text"].index("coefficient")
        end = start + len("coefficient reference")
        partial_locator = {"kind": "pdf_page", "value": f"2:{start}-{end}"}
        partial = tabular_source.extract_selection(raw, partial_locator)
        source = {"id": "paper", "url": "urn:test:original-two-page-pdf", "asset_sha256": hashlib.sha256(raw).hexdigest(),
                  "sha256": hashlib.sha256(raw).hexdigest(), "license_note": "Constructed local PDF fixture"}
        selections = [{"id": name, "source": source, "locator": locator, "extraction": extraction}
                      for name, locator, extraction in (("whole-page", whole_locator, whole), ("partial-page", partial_locator, partial))]
        result = {"result": {"selections": selections}}
        unchanged = copy.deepcopy(result)
        root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        reference = project_knowledge.build(root, {"id": "action-pdf-fixture", "receipt_snapshot_sha256": "d" * 64}, result)
        hits = project_knowledge.query(root, {"knowledge_refs": [reference]}, need="coefficient", limit=5)["evidence"]
        self.assertEqual(len(hits), 2)
        expected = {name: (locator, extraction) for name, locator, extraction in
                    (("whole-page", whole_locator, whole), ("partial-page", partial_locator, partial))}
        for hit in hits:
            metadata = hit["source"]["metadata"]
            locator, extraction = expected[metadata["selection_id"]]
            self.assertEqual(hit["location"], {"page": 2})
            self.assertEqual(hit["source"]["page"], 2)
            self.assertEqual(hit["quote"], extraction["text"])
            self.assertEqual(metadata["locator"], locator)
            self.assertEqual(metadata["extraction"], {key: extraction[key] for key in
                ("kind", "page", "document_pages", "start_char", "end_char", "offset_basis", "page_text_sha256", "text_sha256")})
            self.assertNotIn("text", metadata["extraction"])
            self.assertNotIn("parser", metadata["extraction"])
            self.assertEqual(hit["source"]["sha256"], source["sha256"])
            self.assertEqual(metadata["action_id"], "action-pdf-fixture")
        self.assertEqual(partial["text"], whole["text"][start:end])
        self.assertEqual(partial["page_text_sha256"], whole["page_text_sha256"])
        self.assertEqual(result, unchanged)

    def test_non_pdf_project_text_preserves_original_metadata_and_chunk_line_location(self):
        raw = b"Before\nFroude coefficient is a recorded term.\nAfter\n"
        locator = {"kind": "text_lines", "value": "2"}
        extraction = tabular_source.extract_selection(raw, locator)
        digest = hashlib.sha256(raw).hexdigest()
        source = {"id": "text", "url": "urn:test:original-text", "asset_sha256": digest,
                  "sha256": digest, "license_note": "Constructed local text fixture"}
        root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        ref = project_knowledge.build(root, {"id": "action-text-fixture", "receipt_snapshot_sha256": "e" * 64},
            {"result": {"selections": [{"id": "line", "source": source, "locator": locator, "extraction": extraction}]}})
        hit, = project_knowledge.query(root, {"knowledge_refs": [ref]}, need="coefficient")["evidence"]
        self.assertEqual(hit["location"], {"line_start": 1, "line_end": 1})
        self.assertIsNone(hit["source"]["page"])
        self.assertEqual(hit["quote"], extraction["text"])
        self.assertEqual(hit["source"]["metadata"], {
            "source_role": "project_source_selection", "locator": locator, "license_note": source["license_note"],
            "action_id": "action-text-fixture", "selection_id": "line", "source_id": "text",
            "original_source_sha256": digest, "endpoint_eligibility": "unknown"})

    def test_exact_page_and_invalid_coordinates(self):
        with patch.object(tabular_source.knowledge_sources, "_extract_pdf", return_value=(["first", "second\npage"], 2)) as parse:
            result = tabular_source.extract_selection(b"pdf fixture", {"kind": "pdf_page", "value": "2"})
            self.assertEqual((result["page"], result["document_pages"], result["text"]), (2, 2, "second\npage"))
            self.assertEqual(result["parser"]["warnings"], 2)
            self.assertIn("no OCR", result["offset_basis"])
            self.assertEqual(parse.call_args.args, (b"pdf fixture", 30))
            selected = tabular_source.extract_selection(b"pdf fixture", {"kind": "pdf_page", "value": "2:7-11"})
            self.assertEqual((selected["text"], selected["start_char"], selected["end_char"]), ("page", 7, 11))
            for value in ("0", "01", "-1", "1-2", "1,2", "501", "1:1-1", "1:4-2"):
                with self.subTest(value=value), self.assertRaises(ResearchError) as caught:
                    tabular_source.extract_selection(b"pdf fixture", {"kind": "pdf_page", "value": value})
                self.assertEqual(caught.exception.code, "INVALID_LOCATOR")
            self.assertEqual(parse.call_count, 2)

    def test_failed_empty_oversized_and_missing_pages_never_become_partial_evidence(self):
        for texts, page, code in ((["only"], "2", "INVALID_LOCATOR"), (["  \n"], "1", "EMPTY_PDF_PAGE"),
                                  (["x" * 60001], "1", "SELECTION_TOO_LARGE"), (["a\x00b"], "1", "INVALID_TEXT"),
                                  (["abc"], "1:0-4", "INVALID_LOCATOR")):
            with self.subTest(code=code), patch.object(tabular_source.knowledge_sources, "_extract_pdf", return_value=(texts, 0)):
                with self.assertRaises(ResearchError) as caught:
                    tabular_source.extract_selection(b"pdf fixture", {"kind": "pdf_page", "value": page})
                self.assertEqual(caught.exception.code, code)
        with patch.object(tabular_source.knowledge_sources, "_extract_pdf", side_effect=tabular_source.knowledge_sources._Problem("pdf_parse_timeout")):
            with self.assertRaises(ResearchError) as caught:
                tabular_source.extract_selection(b"pdf fixture", {"kind": "pdf_page", "value": "1"})
            self.assertEqual(caught.exception.code, "PDF_EXTRACTION_FAILED")


if __name__ == "__main__":
    unittest.main()
