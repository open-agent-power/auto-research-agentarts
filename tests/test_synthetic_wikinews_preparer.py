"""Isolated synthetic preparation only; never touch a real Wikinews input."""
import csv
import copy
import hashlib
import io
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unicodedata
import unittest
import uuid
import xml.etree.ElementTree as ET
from contextlib import ExitStack, redirect_stderr
from unittest.mock import patch

from autoresearch import (relevance_retrieval_adapter as relevance, retrieval_lexical as lexical,
                          staged_relevance_adapter as staged)
from autoresearch.contracts import ResearchError, canonical
from autoresearch.project_controller import ProjectController
from autoresearch.research_project import ResearchProject
import scripts.prepare_synthetic_wikinews as preparer


class SyntheticWikinewsPreparerTests(unittest.TestCase):
    def setUp(self):
        self.runs = Path(__file__).resolve().parents[1] / 'runs'

    def output(self):
        path = self.runs / ('s127-synthetic-wikinews-' + uuid.uuid4().hex)
        self.assertFalse(path.exists())
        self.addCleanup(lambda: shutil.rmtree(path) if path.exists() and not path.is_symlink() else None)
        return path

    def no_research(self, stack):
        stack.enter_context(patch('socket.socket.connect', side_effect=AssertionError('network forbidden')))
        stack.enter_context(patch('urllib.request.urlopen', side_effect=AssertionError('network forbidden')))
        stack.enter_context(patch('subprocess.Popen', side_effect=AssertionError('subprocess forbidden')))
        stack.enter_context(patch.object(ResearchProject, 'create', side_effect=AssertionError('project forbidden')))
        stack.enter_context(patch.object(ResearchProject, 'step', side_effect=AssertionError('step forbidden')))
        stack.enter_context(patch.object(ResearchProject, 'read_evidence', side_effect=AssertionError('evidence forbidden')))
        stack.enter_context(patch.object(ProjectController, '_dispatch', side_effect=AssertionError('dispatch forbidden')))
        stack.enter_context(patch.object(staged, 'execute', side_effect=AssertionError('ranking and scoring forbidden')))
        stack.enter_context(patch.object(staged.AUDIT, 'execute_saved', side_effect=AssertionError('audit forbidden')))
        stack.enter_context(patch.object(relevance, 'retrieve', side_effect=AssertionError('ranking forbidden')))
        for name in ('build_index', 'retrieve', 'metrics'):
            stack.enter_context(patch.object(lexical, name, side_effect=AssertionError(name + ' forbidden')))

    def test_internal_fixture_produces_exact_mappings_and_native_packet(self):
        output = self.output()
        with ExitStack() as stack:
            self.no_research(stack)
            preparer.prepare(output)
            packet = json.loads((output / 'source.json').read_bytes())
            captured = staged.capture_source(output / 'development')
            loaded = staged.load_source(canonical(packet).encode('utf-8'))
        self.assertEqual(packet, captured)
        self.assertEqual(loaded, packet)
        self.assertEqual(packet['task_kind'], 'staged_relevance_development')
        self.assertEqual(packet['stage'], 'development')
        self.assertEqual(packet['scope']['document_count'], 1000)
        self.assertEqual(packet['scope']['query_count'], 150)
        self.assertEqual(packet['scope']['query_split_counts'], {'dev':50, 'validation':100})
        self.assertEqual(packet['scope']['missing_positive_document_count'], 0)
        self.assertEqual(packet['scope']['missing_positive_qrel_pairs'], 0)
        self.assertEqual(packet['spec']['comparison'], staged.COMPARISON)
        self.assertEqual(packet['spec']['limits'], staged.LIMITS)
        receipt = json.loads((output / 'receipt.json').read_bytes())
        self.assertEqual(receipt['contracts_sha256'], hashlib.sha256(Path(preparer.contracts_module.__file__).read_bytes()).hexdigest())
        dev = output / 'development'
        docs = [json.loads(line) for line in (dev / 'corpus.jsonl').read_text('utf-8').split('\n') if line]
        queries = [json.loads(line) for line in (dev / 'queries.jsonl').read_text('utf-8').split('\n') if line]
        self.assertEqual(len(docs), 1000)
        self.assertEqual(len(queries), 150)
        self.assertTrue(all(row['title'] == '' and row['metadata'] == {} and row['text'].strip() for row in docs))
        self.assertTrue(all(row['metadata'] == {} and row['text'].strip() for row in queries))
        doc_ids = {row['_id'] for row in docs}
        query_ids = {row['_id'] for row in queries}
        self.assertEqual((len(doc_ids), len(query_ids)), (1000, 150))
        self.assertTrue(doc_ids.isdisjoint(query_ids))
        with (dev / 'qrels.tsv').open(encoding='utf-8', newline='') as stream:
            rows = list(csv.reader(stream, delimiter='\t', strict=True))
        self.assertEqual(rows[0], ['query-id','corpus-id','score'])
        self.assertEqual(len(rows) - 1, 150)
        pairs = {}
        for query_id, doc_id, score in rows[1:]:
            self.assertNotIn(query_id, pairs)
            self.assertIn(query_id, query_ids)
            self.assertIn(doc_id, doc_ids)
            self.assertEqual(score, '1')
            self.assertTrue(query_id.startswith('q-') and doc_id.startswith('d-'))
            self.assertEqual(query_id.removeprefix('q-'), doc_id.removeprefix('d-'))
            pairs[query_id] = doc_id
        self.assertEqual(set(pairs), query_ids)
        self.assertEqual(len(set(pairs.values())), 150)

    def test_same_internal_fixture_produces_identical_native_assets(self):
        left, right = self.output(), self.output()
        with ExitStack() as stack:
            self.no_research(stack)
            preparer.prepare(left)
            preparer.prepare(right)
        for name in ('corpus.jsonl','queries.jsonl','qrels.tsv','license.md','spec.json'):
            self.assertEqual((left / 'development' / name).read_bytes(), (right / 'development' / name).read_bytes(), name)
        for name in ('claim.json','fixture.xml','source.json','selection.json','source-receipt.json','receipt.json'):
            self.assertEqual((left / name).read_bytes(), (right / name).read_bytes(), name)

    def test_transitive_components_seed_order_unicode_and_input_order(self):
        raw, evidence = preparer._fixture()
        reversed_raw, reversed_evidence = preparer._fixture(reverse=True)
        self.assertNotEqual(raw, reversed_raw)
        with ExitStack() as stack:
            self.no_research(stack)
            records = preparer._parse_fixture(raw, evidence)
            selected = preparer._select(records)
            reversed_selected = preparer._select(preparer._parse_fixture(reversed_raw, reversed_evidence))
        self.assertEqual(len(records), 1005)
        self.assertTrue(all(unicodedata.is_normalized('NFC', row['title']) and
                            unicodedata.is_normalized('NFC', row['body']) for row in records))
        groups = [set(group) for group in selected['components']]
        self.assertIn({1, 2, 3}, groups)
        self.assertIn({10, 11}, groups)
        representatives = {row['page_id'] for row in records} - {2, 3, 11}
        def key(prefix, page_id):
            return hashlib.sha256((prefix + '\n' + str(page_id)).encode('utf-8')).digest(), page_id
        corpus = sorted(representatives, key=lambda page_id: key('wikinews-sample-v1', page_id))[:1000]
        query_order = sorted(corpus, key=lambda page_id: key('wikinews-query-v1', page_id))
        self.assertEqual([row['page_id'] for row in selected['corpus']], corpus)
        self.assertEqual([row['page_id'] for row in selected['dev']], query_order[:50])
        self.assertEqual([row['page_id'] for row in selected['validation']], query_order[50:150])
        self.assertEqual(selected, reversed_selected)

    def test_reordered_fixture_preserves_selection_but_changes_source_identity(self):
        left, right = self.output(), self.output()
        reverse = preparer._fixture(reverse=True)
        with ExitStack() as stack:
            self.no_research(stack)
            preparer.prepare(left)
            with patch.object(preparer, '_fixture', return_value=reverse):
                preparer.prepare(right)
        for name in ('corpus.jsonl','queries.jsonl','qrels.tsv','license.md'):
            self.assertEqual((left / 'development' / name).read_bytes(), (right / 'development' / name).read_bytes(), name)
        self.assertEqual((left / 'selection.json').read_bytes(), (right / 'selection.json').read_bytes())
        self.assertNotEqual((left / 'claim.json').read_bytes(), (right / 'claim.json').read_bytes())
        self.assertNotEqual((left / 'source-receipt.json').read_bytes(), (right / 'source-receipt.json').read_bytes())
        self.assertNotEqual((left / 'development' / 'spec.json').read_bytes(), (right / 'development' / 'spec.json').read_bytes())
        self.assertNotEqual((left / 'source.json').read_bytes(), (right / 'source.json').read_bytes())

    def test_existing_output_is_preserved_without_overwrite(self):
        output = self.output()
        with ExitStack() as stack:
            self.no_research(stack)
            preparer.prepare(output)
            before = {str(path.relative_to(output)): path.read_bytes() for path in output.rglob('*') if path.is_file()}
            with self.assertRaises((ResearchError, FileExistsError, ValueError)):
                preparer.prepare(output)
        after = {str(path.relative_to(output)): path.read_bytes() for path in output.rglob('*') if path.is_file()}
        self.assertTrue(before)
        self.assertEqual(after, before)

    def test_missing_conflicting_synthetic_licence_and_evidence_fail_closed(self):
        raw, evidence = preparer._fixture()
        first = next(iter(evidence))
        variants = []
        missing = copy.deepcopy(evidence); del missing[first]; variants.append(missing)
        for key, value in (('license','unknown'), ('attribution',''), ('title_sha256','0'*64),
                           ('body_sha256','0'*64), ('revision_id',True)):
            altered = copy.deepcopy(evidence); altered[first][key] = value; variants.append(altered)
        with ExitStack() as stack:
            self.no_research(stack)
            for altered in variants:
                with self.subTest(altered=altered.get(first)):
                    with self.assertRaises((ValueError, ET.ParseError, ResearchError)):
                        preparer._parse_fixture(raw, altered)

    def test_duplicate_page_id_and_dtd_or_entity_fail_closed(self):
        raw, evidence = preparer._fixture()
        root = ET.fromstring(raw)
        page = next(item for item in root if item.tag.rsplit('}', 1)[-1] == 'page')
        root.append(copy.deepcopy(page))
        duplicate = ET.tostring(root, encoding='utf-8', xml_declaration=True)
        malicious = (b'<?xml version="1.0" encoding="UTF-8"?>'
                     b'<!DOCTYPE mediawiki [<!ENTITY payload SYSTEM "file:///nonexistent-s127-synthetic-entity">]>'
                     b'<mediawiki>&payload;</mediawiki>')
        with ExitStack() as stack:
            self.no_research(stack)
            for xml in (duplicate, malicious):
                with self.assertRaises((ValueError, ET.ParseError, ResearchError)):
                    preparer._parse_fixture(xml, evidence)

    def test_insufficient_records_are_not_resampled_or_replaced(self):
        raw, evidence = preparer._fixture()
        with ExitStack() as stack:
            self.no_research(stack)
            records = preparer._parse_fixture(raw, evidence)
            with self.assertRaises((ValueError, ET.ParseError, ResearchError)):
                preparer._select(records[:500])

    def test_xml_byte_limit_rejects_before_output(self):
        _, evidence = preparer._fixture()
        with ExitStack() as stack:
            self.no_research(stack)
            with self.assertRaises((ValueError, ET.ParseError, ResearchError)):
                preparer._parse_fixture(b'x' * (preparer.MAX_XML_BYTES + 1), evidence)

    def test_output_drift_before_capture_keeps_partial_and_no_success_receipt(self):
        original_capture = staged.capture_source
        for mode in ('valid-corpus-replacement', 'corpus-symlink', 'claim', 'selection', 'source-receipt'):
            with self.subTest(mode=mode):
                output = self.output()
                def corrupt_before_capture(development):
                    development = Path(development)
                    corpus = development / 'corpus.jsonl'
                    if mode == 'valid-corpus-replacement':
                        lines = corpus.read_text('utf-8').splitlines()
                        row = json.loads(lines[0])
                        row['text'] += ' changed synthetic content'
                        lines[0] = canonical(row)
                        corpus.write_text('\n'.join(lines) + '\n', encoding='utf-8')
                    elif mode == 'corpus-symlink':
                        copy_path = output / 'synthetic-corpus-copy.jsonl'
                        copy_path.write_bytes(corpus.read_bytes())
                        corpus.unlink()
                        corpus.symlink_to(copy_path)
                    else:
                        path = output / {'claim':'claim.json', 'selection':'selection.json',
                                         'source-receipt':'source-receipt.json'}[mode]
                        path.write_bytes(path.read_bytes() + b' ')
                    return original_capture(development)
                with ExitStack() as stack:
                    self.no_research(stack)
                    stack.enter_context(patch.object(staged, 'capture_source', side_effect=corrupt_before_capture))
                    with self.assertRaises((ValueError, ET.ParseError, ResearchError, OSError)):
                        preparer.prepare(output)
                self.assertTrue(output.is_dir())
                self.assertTrue((output / 'claim.json').exists())
                self.assertFalse((output / 'receipt.json').exists())

    def test_selection_or_receipt_drift_after_capture_keeps_original_attempt(self):
        original_capture = staged.capture_source
        for name in ('selection.json', 'source-receipt.json'):
            with self.subTest(name=name):
                output = self.output()
                def corrupt_after_capture(development):
                    packet = original_capture(development)
                    target = output / name
                    target.write_bytes(target.read_bytes() + b' ')
                    return packet
                with ExitStack() as stack:
                    self.no_research(stack)
                    stack.enter_context(patch.object(staged, 'capture_source', side_effect=corrupt_after_capture))
                    with self.assertRaises((ValueError, ET.ParseError, ResearchError, OSError)):
                        preparer.prepare(output)
                self.assertTrue(output.is_dir())
                self.assertTrue((output / 'claim.json').exists())
                self.assertFalse((output / 'receipt.json').exists())
                before = {str(path.relative_to(output)): path.read_bytes() for path in output.rglob('*') if path.is_file()}
                with ExitStack() as stack:
                    self.no_research(stack)
                    with self.assertRaises((ValueError, FileExistsError, ResearchError)):
                        preparer.prepare(output)
                after = {str(path.relative_to(output)): path.read_bytes() for path in output.rglob('*') if path.is_file()}
                self.assertEqual(after, before)

    def test_cli_rejects_external_input_options_before_prepare(self):
        for option in ('--source', '--input'):
            with self.subTest(option=option):
                output = self.output()
                argv = ['prepare_synthetic_wikinews.py', '--output', str(output), option, 'invented-input']
                with ExitStack() as stack:
                    self.no_research(stack)
                    prepare = stack.enter_context(patch.object(preparer, 'prepare', side_effect=AssertionError('must not prepare')))
                    stack.enter_context(patch.object(sys, 'argv', argv))
                    stack.enter_context(redirect_stderr(io.StringIO()))
                    with self.assertRaises(SystemExit) as error:
                        preparer.main()
                self.assertEqual(error.exception.code, 2)
                prepare.assert_not_called()
                self.assertFalse(output.exists())

    def test_output_symlink_rejected_without_touching_its_target(self):
        target, link = self.output(), self.output()
        target.mkdir()
        sentinel = target / 'synthetic-sentinel'
        sentinel.write_bytes(b'unchanged synthetic bytes')
        link.symlink_to(target, target_is_directory=True)
        try:
            with ExitStack() as stack:
                self.no_research(stack)
                with self.assertRaises((ValueError, ResearchError, OSError)):
                    preparer.prepare(link)
            self.assertTrue(link.is_symlink())
            self.assertEqual(sentinel.read_bytes(), b'unchanged synthetic bytes')
            self.assertEqual(sorted(p.name for p in target.iterdir()), ['synthetic-sentinel'])
        finally:
            link.unlink()

    def test_fsync_failures_preserve_original_attempt_and_reject_retry(self):
        original_sync = preparer._sync_directory
        for phase in ('before-receipt', 'after-receipt'):
            with self.subTest(phase=phase):
                output = self.output()
                def interrupted(path):
                    if (phase == 'before-receipt' and Path(path) == output / 'development') or (
                            phase == 'after-receipt' and Path(path) == output):
                        raise OSError('synthetic directory fsync failure')
                    return original_sync(path)
                with ExitStack() as stack:
                    self.no_research(stack)
                    stack.enter_context(patch.object(preparer, '_sync_directory', side_effect=interrupted))
                    with self.assertRaises(OSError):
                        preparer.prepare(output)
                self.assertTrue(output.is_dir())
                self.assertTrue((output / 'claim.json').is_file())
                receipt_path = output / 'receipt.json'
                self.assertEqual(receipt_path.is_file(), phase == 'after-receipt')
                if receipt_path.is_file():
                    self.assertTrue(json.loads(receipt_path.read_bytes())['synthetic_only'])
                before = {str(p.relative_to(output)):p.read_bytes() for p in output.rglob('*') if p.is_file()}
                with ExitStack() as stack:
                    self.no_research(stack)
                    with self.assertRaises((ValueError, FileExistsError, ResearchError)):
                        preparer.prepare(output)
                after = {str(p.relative_to(output)):p.read_bytes() for p in output.rglob('*') if p.is_file()}
                self.assertEqual(after, before)
                # When a receipt exists, its directory durability remains unknown.

    def test_contracts_file_identity_and_mid_capture_drift(self):
        directory = Path(self.enterContext(tempfile.TemporaryDirectory(prefix='s127-fake-contracts-')))
        fake_contracts = directory / 'synthetic-contracts.py'
        original_bytes = b'# invented test identity; never loaded as code\n'
        fake_contracts.write_bytes(original_bytes)
        successful = self.output()
        with ExitStack() as stack:
            self.no_research(stack)
            stack.enter_context(patch.object(preparer.contracts_module, '__file__', str(fake_contracts)))
            receipt = preparer.prepare(successful)
        self.assertEqual(receipt['contracts_sha256'], hashlib.sha256(original_bytes).hexdigest())
        self.assertEqual(json.loads((successful / 'receipt.json').read_bytes())['contracts_sha256'], receipt['contracts_sha256'])
        output = self.output()
        original_capture = staged.capture_source
        def drift(development):
            packet = original_capture(development)
            fake_contracts.write_bytes(original_bytes + b'# synthetic drift\n')
            return packet
        with ExitStack() as stack:
            self.no_research(stack)
            stack.enter_context(patch.object(preparer.contracts_module, '__file__', str(fake_contracts)))
            stack.enter_context(patch.object(staged, 'capture_source', side_effect=drift))
            with self.assertRaises((ValueError, ResearchError, OSError)):
                preparer.prepare(output)
        self.assertTrue((output / 'claim.json').is_file())
        self.assertFalse((output / 'receipt.json').exists())
        before = {str(p.relative_to(output)):p.read_bytes() for p in output.rglob('*') if p.is_file()}
        with ExitStack() as stack:
            self.no_research(stack)
            with self.assertRaises((ValueError, FileExistsError, ResearchError)):
                preparer.prepare(output)
        self.assertEqual({str(p.relative_to(output)):p.read_bytes() for p in output.rglob('*') if p.is_file()}, before)


if __name__ == '__main__':
    unittest.main()
