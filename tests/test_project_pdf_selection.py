"""Only PDF selection boundaries; the real author PDF is exercised by the project trial."""
import unittest
from unittest.mock import patch

from autoresearch import tabular_source
from autoresearch.contracts import ResearchError


class ProjectPdfSelectionTests(unittest.TestCase):
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
