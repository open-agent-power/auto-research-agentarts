"""Small synthetic FTS fixtures for adjacent letter/digit spellings."""

import hashlib
from pathlib import Path
import tempfile
import unittest

from autoresearch.knowledge import KnowledgeError, KnowledgeIndex, _query_tokens, build_index


def document(identifier, text):
    return {"id": identifier, "title": "Fixture", "kind": "official_doc",
            "source_url": "https://example.test/" + identifier,
            "path": identifier + ".txt", "sha256": hashlib.sha256(text.encode()).hexdigest(),
            "snapshot": "synthetic", "text": text, "page": None,
            "review_status": "synthetic", "metadata": {}}


class IdentifierAliasesTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        sources = [document("joined", "Factor47 top20"),
                   document("separated", "Factor 47 top 20"),
                   document("different", "Factor 87 top 25"),
                   document("nonadjacent", "Factor distant 47 top distant 20"),
                   document("single-joined", "x1 x12"),
                   document("single-spaced", "x 1 x 12"),
                   document("overlap-joined", "20top top10")]
        self.sources = {source["id"]: source for source in sources}
        database = Path(directory.name) / "fixture.sqlite"
        build_index(sources, database)
        self.index = KnowledgeIndex(database)

    def ids(self, query):
        result = self.index.search(query, limit=8)
        self.assertFalse(result["may_execute"])
        for hit in result["evidence"]:
            source = self.sources[hit["source"]["id"]]
            self.assertEqual(hit["source"]["sha256"], source["sha256"])
            self.assertIn(hit["quote"], source["text"])
            self.assertTrue(hit["citation_id"])
        return {hit["source"]["id"] for hit in result["evidence"]}

    def test_joined_query_adds_ordered_phrase_not_unrelated_terms(self):
        for query in ("Factor47", "top20"):
            with self.subTest(query=query):
                self.assertEqual(self.ids(query), {"joined", "separated"})

    def test_spaced_query_adds_joined_form_keeps_existing_or_behavior(self):
        for query in ("Factor 47", "top 20"):
            with self.subTest(query=query):
                self.assertEqual(self.ids(query), {"joined", "separated", "different", "nonadjacent"})

    def test_aliases_require_adjacent_boundaries(self):
        for query in ("factor / 47", "factor-47", "factor_47", "factor distant 47", "factor\t47"):
            with self.subTest(query=query):
                self.assertNotIn("factor47", _query_tokens(query))
        self.assertNotIn("top 20", _query_tokens("étop20"))
        self.assertNotIn("top 20", _query_tokens("top20后"))
        self.assertIn("factor 47", _query_tokens("Ｆａｃｔｏｒ４７"))
        self.assertEqual(self.ids("Ｆａｃｔｏｒ４７"), {"joined", "separated"})
        self.assertIn("20 top", _query_tokens("20top"))
        self.assertIn("20top", _query_tokens("20 top"))
        self.assertNotIn("joined", self.ids("top/20"))

    def test_overlapping_adjacent_pairs_are_each_available(self):
        terms = _query_tokens("20 top 10")
        self.assertIn("20top", terms)
        self.assertIn("top10", terms)
        self.assertIn("overlap-joined", self.ids("20 top 10"))

    def test_original_index_drops_single_character_parts(self):
        # Frozen index construction omits one-character tokens. Aliases do
        # not recover those missing bytes from an existing FTS index.
        self.assertEqual(self.ids("x1"), {"single-joined"})
        self.assertEqual(self.ids("x12"), {"single-joined"})
        self.assertEqual(self.ids("x 1"), {"single-joined"})

    def test_original_terms_keep_priority_and_query_stays_bounded(self):
        originals = [f"term{i}" for i in range(64)]
        self.assertEqual(_query_tokens(" ".join(originals)), originals)
        terms = _query_tokens(" ".join(originals[:63]))
        self.assertEqual(terms[:63], originals[:63])
        self.assertEqual(len(terms), 64)
        chinese_terms = _query_tokens("代码 " + " ".join(originals[:62]))
        self.assertEqual(len(chinese_terms), 64)
        self.assertEqual(chinese_terms[-1], "code")
        # A 512-character alternating token expands to at most 1,023
        # characters as a quoted phrase, not an unbounded expression.
        maximum = "a1" * 256
        aliases = _query_tokens(maximum)
        self.assertEqual(len(aliases), 2)
        self.assertEqual(len(aliases[1]), 1023)
        self.assertEqual(self.index.search(maximum)["evidence"], [])
        with self.assertRaises(KnowledgeError):
            self.index.search(maximum + "a")

    def test_query_syntax_is_still_literal_and_cannot_join_punctuation(self):
        query = 'factor" OR "47; DROP TABLE chunks -- top/20'
        self.assertNotIn("factor47", _query_tokens(query))
        self.assertNotIn("top20", _query_tokens(query))
        self.index.search(query, limit=8)
        self.assertEqual(self.ids("Factor47"), {"joined", "separated"})


if __name__ == "__main__":
    unittest.main()
