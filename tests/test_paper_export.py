"""Literal-text and link safety checks; PDF rendering QA is a separate step."""

import unittest

from autoresearch.paper_export import _https_url, _markup, _number, _text


class PaperExportTests(unittest.TestCase):
    def test_paragraph_input_is_literal_and_bounded(self):
        malicious = '<img src="https://example.invalid/private"/><b>并非已验证</b> & text'
        escaped = _markup(malicious)
        self.assertNotIn("<img", escaped)
        self.assertNotIn("<b>", escaped)
        self.assertIn("&lt;img", escaped)
        self.assertIn("&amp; text", escaped)
        self.assertNotIn("\x00", _text("输入\x00字段"))
        self.assertNotIn("\u2011", _text("data\u2011source"))
        long_question = "待验证问题" * 1000
        excerpt = _text(long_question, 85)
        self.assertLess(len(excerpt), 110)
        self.assertIn("全文见附件", excerpt)

    def test_only_https_references_become_links(self):
        for address in (None, "javascript:alert(1)", "file:///secret", "http://example.com",
                        "https://user:key@example.com", "https:///missing", "https://example.com/\npath",
                        "https://example.com:bad/path", "https://example.com:0/path"):
            with self.subTest(address=address):
                self.assertIsNone(_https_url(address))
        valid = "https://example.com/paper?a=1&b=2#section"
        self.assertEqual(_https_url(valid), valid)

    def test_absent_nonfinite_and_boolean_metrics_are_not_measurements(self):
        for value in (None, True, False, float("nan"), float("inf"), "43257"):
            with self.subTest(value=value):
                self.assertEqual(_number(value), "未取得")
        self.assertEqual(_number(43257.803922542305), "43,257.80")


if __name__ == "__main__":
    unittest.main()
