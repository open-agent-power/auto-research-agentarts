"""White-box synthetic source preparation; no ranking, scoring, or Project."""
import copy
import csv
import hashlib
import json
import math
from pathlib import Path
import re
import shutil
import unittest
import uuid
import xml.etree.ElementTree as ET
from contextlib import ExitStack
from unittest.mock import patch

from autoresearch import relevance_retrieval_adapter as relevance
from autoresearch import retrieval_lexical as lexical
from autoresearch import staged_relevance_adapter as staged
from autoresearch.contracts import ResearchError, canonical
from autoresearch.project_controller import ProjectController
from autoresearch.research_project import ResearchProject
import scripts.prepare_synthetic_wikinews_counterexample as preparer


class SyntheticWikinewsCounterexampleTests(unittest.TestCase):
    def output(self):
        root = Path(__file__).resolve().parents[1] / 'runs'
        path = root / ('s129-synthetic-wikinews-counterexample-' + uuid.uuid4().hex)
        self.assertFalse(path.exists())
        self.addCleanup(lambda: shutil.rmtree(path) if path.exists() and not path.is_symlink() else None)
        return path

    def forbid_research(self, stack):
        stack.enter_context(patch('socket.socket.connect', side_effect=AssertionError('network forbidden')))
        stack.enter_context(patch('urllib.request.urlopen', side_effect=AssertionError('network forbidden')))
        stack.enter_context(patch('subprocess.Popen', side_effect=AssertionError('subprocess forbidden')))
        for method in ('create', 'step', 'read_evidence'):
            stack.enter_context(patch.object(ResearchProject, method, side_effect=AssertionError(method + ' forbidden')))
        stack.enter_context(patch.object(ProjectController, '_dispatch', side_effect=AssertionError('dispatch forbidden')))
        stack.enter_context(patch.object(staged, 'execute', side_effect=AssertionError('execute forbidden')))
        stack.enter_context(patch.object(staged.AUDIT, 'execute_saved', side_effect=AssertionError('audit forbidden')))
        stack.enter_context(patch.object(relevance, 'retrieve', side_effect=AssertionError('ranking forbidden')))
        for method in ('build_index', 'retrieve', 'metrics'):
            stack.enter_context(patch.object(lexical, method, side_effect=AssertionError(method + ' forbidden')))

    @staticmethod
    def tokens(value):
        return re.findall(r'[a-z0-9]+', value.lower())

    def test_fixed_selection_and_white_box_construction(self):
        with ExitStack() as stack:
            self.forbid_research(stack)
            raw, evidence = preparer._fixture()
            records = preparer._parse_fixture(raw, evidence)
            chosen = preparer._select(records)
            reverse_raw, reverse_evidence = preparer._fixture(reverse=True)
            reverse = preparer._select(preparer._parse_fixture(reverse_raw, reverse_evidence))
        self.assertNotEqual(raw, reverse_raw)
        self.assertEqual(chosen, reverse)
        self.assertEqual(len(records), 1005)
        self.assertEqual(len(chosen['components']), 1000)
        groups = {frozenset(group) for group in chosen['components']}
        for page_id in range(1, 6):
            self.assertIn(frozenset((page_id, page_id + 1000)), groups)
        corpus = chosen['corpus']
        dev, validation = chosen['dev'], chosen['validation']
        self.assertEqual((len(corpus), len(dev), len(validation)), (1000, 50, 100))
        key = lambda page_id: (hashlib.sha256(('wikinews-query-v1\n' + str(page_id)).encode()).digest(), page_id)
        ordered = sorted((row['page_id'] for row in corpus), key=key)
        self.assertEqual([row['page_id'] for row in dev], ordered[:50])
        self.assertEqual([row['page_id'] for row in validation], ordered[50:150])
        query_ids = set(ordered[:150])
        query_words = set()
        documents_by_token = {}
        lengths = 0
        for row in corpus:
            words = self.tokens(row['body'])
            lengths += len(words)
            for word in set(words):
                documents_by_token.setdefault(word, []).append(row['page_id'])
            if row['page_id'] in query_ids:
                title = self.tokens(row['title'])
                self.assertEqual(len(title), 1)
                term = title[0]
                self.assertRegex(term, r'^x[0-9]+$')
                self.assertNotIn(term, query_words)
                query_words.add(term)
                self.assertEqual(words.count(term), 10)
                self.assertEqual(len(words), 11)
                remainder = [word for word in words if word != term]
                self.assertEqual(len(remainder), 1)
                self.assertRegex(remainder[0], r'^y[0-9]+$')
        self.assertEqual(lengths, 2500)
        non_query = {row['page_id']: self.tokens(row['body']) for row in corpus if row['page_id'] not in query_ids}
        distractors = [words[0] for words in non_query.values() if len(words) == 1 and words[0] in query_words]
        self.assertCountEqual(distractors, list(query_words))
        self.assertEqual(len(non_query) - len(distractors), 700)
        for term in query_words:
            self.assertEqual(len(documents_by_token[term]), 2)
        for row in corpus:
            if row['page_id'] in query_ids:
                filler = [word for word in self.tokens(row['body']) if word not in query_words]
                self.assertEqual(len(documents_by_token[filler[0]]), 1)

    def test_theoretical_order_uses_fixed_formula_without_retrieval(self):
        # x occurs in two documents; y occurs only in the target. No ranking is run.
        n, avgdl = 1000, 2.5
        idf_x = 1 + math.log((n + 1) / (2 + 1))
        idf_y = 1 + math.log((n + 1) / (1 + 1))
        weighted_x = (1 + math.log(10)) * idf_x
        target_cos = weighted_x / math.sqrt(weighted_x ** 2 + idf_y ** 2)
        distractor_cos = 1.0
        target_bm25 = 22 / (10 + 0.3 + 0.9 * 11 / avgdl)
        distractor_bm25 = 2.2 / (1 + 0.3 + 0.9 / avgdl)
        self.assertGreater(target_bm25, distractor_bm25)
        self.assertLess(target_cos, distractor_cos)
        self.assertAlmostEqual(1 / 2 - 1, -0.5)
        self.assertEqual(1 - 1, 0)

    def test_assets_packet_and_fixed_qrels(self):
        output = self.output()
        with ExitStack() as stack:
            self.forbid_research(stack)
            preparer.prepare(output)
            packet = json.loads((output / 'source.json').read_bytes())
            self.assertEqual(staged.capture_source(output / 'development'), packet)
            self.assertEqual(staged.load_source(canonical(packet).encode()), packet)
        self.assertEqual(packet['task_kind'], 'staged_relevance_development')
        self.assertEqual(packet['scope']['document_count'], 1000)
        self.assertEqual(packet['scope']['query_split_counts'], {'dev': 50, 'validation': 100})
        development = output / 'development'
        docs = [json.loads(line) for line in (development / 'corpus.jsonl').read_text().splitlines()]
        queries = [json.loads(line) for line in (development / 'queries.jsonl').read_text().splitlines()]
        self.assertEqual((len(docs), len(queries)), (1000, 150))
        self.assertTrue(all(doc['title'] == '' for doc in docs))
        docids = {doc['_id'] for doc in docs}
        qids = {query['_id'] for query in queries}
        self.assertEqual((len(docids), len(qids)), (1000, 150))
        self.assertTrue(docids.isdisjoint(qids))
        with (development / 'qrels.tsv').open(encoding='utf-8', newline='') as stream:
            rows = list(csv.reader(stream, delimiter='\t', strict=True))
        self.assertEqual(rows[0], ['query-id', 'corpus-id', 'score'])
        self.assertEqual(len(rows), 151)
        self.assertEqual({q for q, _, _ in rows[1:]}, qids)
        self.assertEqual(len({d for _, d, _ in rows[1:]}), 150)
        for query_id, doc_id, score in rows[1:]:
            self.assertEqual(score, '1')
            self.assertIn(doc_id, docids)
            self.assertEqual(query_id.removeprefix('q-'), doc_id.removeprefix('d-'))

    def test_deterministic_bytes_and_no_overwrite(self):
        left, right = self.output(), self.output()
        with ExitStack() as stack:
            self.forbid_research(stack)
            preparer.prepare(left)
            preparer.prepare(right)
            before = {str(p.relative_to(left)): p.read_bytes() for p in left.rglob('*') if p.is_file()}
            after = {str(p.relative_to(right)): p.read_bytes() for p in right.rglob('*') if p.is_file()}
            self.assertTrue(before)
            self.assertEqual(before, after)
            with self.assertRaises((ResearchError, ValueError, FileExistsError)):
                preparer.prepare(left)
        self.assertEqual(before, {str(p.relative_to(left)): p.read_bytes() for p in left.rglob('*') if p.is_file()})

    def test_evidence_corruption_and_duplicate_ids_fail(self):
        raw, evidence = preparer._fixture()
        bad = copy.deepcopy(evidence)
        del bad[next(iter(bad))]
        root = ET.fromstring(raw)
        root.append(copy.deepcopy(root[0]))
        duplicate = ET.tostring(root, encoding='utf-8', xml_declaration=True)
        with ExitStack() as stack:
            self.forbid_research(stack)
            with self.assertRaises((ResearchError, ValueError, ET.ParseError)):
                preparer._parse_fixture(raw, bad)
            with self.assertRaises((ResearchError, ValueError, ET.ParseError)):
                preparer._parse_fixture(duplicate, evidence)

    def test_drift_during_capture_fails_and_preserves_attempt(self):
        output = self.output()
        capture = staged.capture_source
        def corrupt(development):
            corpus = Path(development) / 'corpus.jsonl'
            lines = corpus.read_text(encoding='utf-8').splitlines()
            row = json.loads(lines[0]); row['text'] += ' syntheticchanged'
            lines[0] = canonical(row)
            corpus.write_text('\n'.join(lines) + '\n', encoding='utf-8')
            return capture(development)
        with ExitStack() as stack:
            self.forbid_research(stack)
            stack.enter_context(patch.object(staged, 'capture_source', side_effect=corrupt))
            with self.assertRaises((ResearchError, ValueError, OSError)):
                preparer.prepare(output)
        self.assertTrue(output.is_dir())
        self.assertFalse((output / 'receipt.json').exists())
        with self.assertRaises((ResearchError, ValueError, FileExistsError)):
            preparer.prepare(output)


if __name__ == '__main__':
    unittest.main()
