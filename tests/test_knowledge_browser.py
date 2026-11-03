import copy
from contextlib import closing, contextmanager
import hashlib
import http.client
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import threading
import unittest
from unittest.mock import patch

from autoresearch import c01_research
from autoresearch.c01_studio import create_server
from autoresearch.knowledge import KnowledgeIndex, build_index
from autoresearch.knowledge_browser import KnowledgeBrowser, KnowledgeBrowserError
import test_c01_studio as legacy_fixture
import test_knowledge as knowledge_fixture


class KnowledgeBrowserTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.database = self.root / 'knowledge.sqlite'
        self.documents = [
            knowledge_fixture.doc('official', '# Code node\n代码节点 shared evidence budget', title='Code node'),
            knowledge_fixture.doc('note', '# C01 note\n' + 'C01 alloy condition shared reference evidence\n' * 65,
                                  kind='reuse_note', title='C01 source note'),
            knowledge_fixture.doc('paper-page-4', 'Theory shared evidence from a real page-numbered fixture.',
                                  kind='research_paper', page=4, path='papers/method.pdf', title='Theory'),
            knowledge_fixture.doc('profile', 'Profile shared method and reuse boundary.', kind='research_profile'),
        ]
        self.manifest = build_index(self.documents, self.database)
        engine = KnowledgeIndex(self.database)
        hits = engine.search('note', kinds=['reuse_note'], limit=2)['evidence']
        hits += engine.search('Theory', kinds=['research_paper'], limit=1)['evidence']
        self.assertEqual(len(hits), 3)
        self.references = [{key: hit[key] for key in ('citation_id', 'source', 'location')} for hit in hits]
        self.research = {'corpus_sha256': self.manifest['corpus_sha256'], 'origin_observation_sha256': 'e' * 64,
                         'references': self.references,
                         'decisions': [{'source_citation_ids': [hit['citation_id'] for hit in hits]}]}
        self.browser = KnowledgeBrowser(self.database, self.research)

    def error_status(self, status, call):
        with self.assertRaises(KnowledgeBrowserError) as error: call()
        self.assertEqual(error.exception.status, status)

    def hashes(self):
        return {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in self.root.iterdir() if path.is_file()}

    @contextmanager
    def server(self, *, mount=True, research=False):
        legacy = legacy_fixture.C01StudioTests('test_routes_are_read_only_and_exports_belong_to_c01')
        legacy.setUp()
        try:
            mounted = {'research': self.research, 'memory': None, 'validation': {}, 'files': {}}
            with patch('autoresearch.c01_studio.render_report', return_value=b'%PDF historical'), \
                 patch('autoresearch.c01_studio.reproduction', return_value=b'historical ZIP'), \
                 patch('autoresearch.c01_studio.load_research_delivery', return_value=mounted):
                server = create_server(legacy.root, legacy.source, 0,
                                       knowledge_index=self.database if mount else None,
                                       research_delivery='operator-mount-fixture' if research else None)
            worker = threading.Thread(target=server.serve_forever, daemon=True)
            worker.start()
            try: yield server, legacy
            finally:
                server.shutdown(); server.server_close(); worker.join(3)
        finally: legacy.tearDown()

    def request(self, server, path, *, method='GET', headers=None, body=None):
        con = http.client.HTTPConnection('127.0.0.1', server.server_port, timeout=5)
        try:
            con.request(method, path, body=body, headers=headers or {})
            response = con.getresponse()
            return response.status, response.read()
        finally: con.close()

    def test_original_search_engine_and_exact_citation_excerpt_are_reused(self):
        original = KnowledgeIndex(self.database).search('shared evidence', kinds=['research_paper'], limit=3)
        result = self.browser.search('shared evidence', kind='research_paper', limit=3)
        self.assertEqual({key: value for key, value in result.items() if key != 'database_sha256'}, original)
        self.assertEqual(result['database_sha256'], self.manifest['database_sha256'])
        for reference in self.references:
            found = self.browser.citation(reference['citation_id'])
            self.assertEqual(found['source'], reference['source'])
            self.assertEqual(found['location'], reference['location'])
            self.assertTrue(found['quote'])
            self.assertEqual(found['research_binding'], {'in_public_references': True, 'used': True, 'exact': True})
            self.assertEqual(found['corpus_sha256'], self.manifest['corpus_sha256'])
            self.assertEqual(found['database_sha256'], self.manifest['database_sha256'])
            self.assertFalse(found['may_execute'])
        paper = self.browser.citation(self.references[-1]['citation_id'])
        self.assertEqual(paper['location'], {'page': 4})
        self.assertEqual(paper['quote'], self.documents[2]['text'])

    def test_metadata_counts_binding_and_readonly_identity(self):
        before, code = self.hashes(), c01_research.code_identity()
        metadata = self.browser.metadata()
        self.assertTrue(metadata['enabled'])
        self.assertEqual(metadata['index']['documents'], 4)
        self.assertEqual(metadata['index']['by_kind'], {kind: 1 for kind in ('official_doc', 'reuse_note', 'research_paper', 'research_profile')})
        self.assertEqual(metadata['research_binding'], {'mounted': True, 'exact': True, 'references_checked': 3, 'used_citations': 3,
                                                       'origin_observation_sha256': self.research['origin_observation_sha256']})
        self.assertIsNone(KnowledgeBrowser(self.database).metadata()['research_binding']['origin_observation_sha256'])
        metadata['index']['by_kind']['official_doc'] = 999
        self.assertEqual(self.browser.metadata()['index']['by_kind']['official_doc'], 1)
        self.browser.search('代码节点')
        self.browser.citation(self.references[0]['citation_id'])
        self.assertEqual(self.hashes(), before)
        self.assertEqual(c01_research.code_identity(), code)
        self.assertFalse(self.database.with_name(self.database.name + '-wal').exists())

    def test_binding_rejects_corpus_source_text_hash_location_and_missing_id(self):
        mutations = (lambda r: r.update(corpus_sha256='f' * 64),
                     lambda r: r.update(origin_observation_sha256='invalid'),
                     lambda r: r.pop('origin_observation_sha256'),
                     lambda r: r['references'][0]['source'].update(sha256='f' * 64),
                     lambda r: r['references'][0]['source'].update(text_sha256='f' * 64),
                     lambda r: r['references'][0]['source'].update(title='different version'),
                     lambda r: r['references'][0]['location'].update(line_start=999),
                     lambda r: r['references'][0].update(citation_id='0' * 64))
        for index, mutate in enumerate(mutations):
            with self.subTest(case=index):
                research = copy.deepcopy(self.research)
                mutate(research)
                with self.assertRaises(KnowledgeBrowserError) as error: KnowledgeBrowser(self.database, research)
                self.assertEqual(error.exception.code, 'RESEARCH_BINDING_MISMATCH')

    def test_invalid_input_unknown_ids_and_no_sql_execution(self):
        for query in ('', ' ', 'x' * 513, None): self.error_status(400, lambda: self.browser.search(query))
        for options in ({'limit': True}, {'limit': 9}, {'kind': 'all'}, {'kind': ['official_doc']}):
            self.error_status(400, lambda: self.browser.search('shared', **options))
        for identifier in ('../source', 'A' * 64, '0' * 63, "'; DROP TABLE chunks; --"):
            self.error_status(400, lambda: self.browser.citation(identifier))
        self.error_status(404, lambda: self.browser.citation('0' * 64))
        self.browser.search("'); DROP TABLE chunks; --")
        self.assertTrue(self.browser.search('shared')['evidence'])
        self.assertEqual(self.browser.search('？！')['empty_reason'], 'no_indexable_terms')

    def test_changed_db_and_manifest_are_rejected_after_mount(self):
        manifest = self.database.with_suffix('.json')
        original = manifest.read_bytes()
        manifest.write_bytes(original + b' ')
        for call in (self.browser.metadata, lambda: self.browser.search('shared'),
                     lambda: self.browser.citation(self.references[0]['citation_id'])):
            self.error_status(409, call)
        manifest.write_bytes(original)
        # Reopen a properly pinned instance, then alter the DB without resealing it.
        browser = KnowledgeBrowser(self.database)
        with closing(sqlite3.connect(self.database)) as con:
            with con: con.execute("UPDATE chunks SET excerpt='tampered'")
        self.error_status(409, lambda: browser.citation(self.references[0]['citation_id']))
        with self.assertRaises(KnowledgeBrowserError): KnowledgeBrowser(self.database)

    def test_same_corpus_different_extraction_has_different_database_identity(self):
        # Raw source IDs/hash/page stay fixed while extracted text/metadata changes.
        changed = self.root / 'changed.sqlite'
        changed.write_bytes(self.database.read_bytes())
        manifest = copy.deepcopy(self.manifest)
        with closing(sqlite3.connect(changed)) as con:
            with con:
                row = con.execute("SELECT record FROM documents WHERE id='paper-page-4'").fetchone()
                source = json.loads(row[0])
                source['text_sha256'] = hashlib.sha256(b'new extraction').hexdigest()
                con.execute("UPDATE documents SET record=? WHERE id='paper-page-4'", (json.dumps(source),))
                con.execute("UPDATE chunks SET excerpt='new extraction' WHERE document_id='paper-page-4'")
        manifest['database_sha256'] = hashlib.sha256(changed.read_bytes()).hexdigest()
        changed.with_suffix('.json').write_text(json.dumps(manifest), encoding='utf-8')
        browser = KnowledgeBrowser(changed)
        found = browser.citation(self.references[-1]['citation_id'])
        self.assertEqual(found['corpus_sha256'], self.manifest['corpus_sha256'])
        self.assertNotEqual(found['database_sha256'], self.manifest['database_sha256'])
        self.assertEqual(found['quote'], 'new extraction')
        with self.assertRaises(KnowledgeBrowserError): KnowledgeBrowser(changed, self.research)

    def test_manifest_db_hardlinks_parent_redirects_and_size_limit_are_rejected(self):
        alias = self.root / 'alias'
        os.link(self.database.with_suffix('.json'), alias)
        with self.assertRaises(KnowledgeBrowserError): KnowledgeBrowser(self.database)
        alias.unlink()
        os.link(self.database, alias)
        with self.assertRaises(KnowledgeBrowserError): KnowledgeBrowser(self.database)
        alias.unlink()
        with patch('autoresearch.knowledge_browser.MAX_DATABASE_BYTES', 1):
            with self.assertRaises(KnowledgeBrowserError): KnowledgeBrowser(self.database)
        redirected = self.root / 'redirected'
        try: redirected.symlink_to(self.root, target_is_directory=True)
        except OSError: return
        with self.assertRaises(KnowledgeBrowserError): KnowledgeBrowser(redirected / self.database.name)

    def test_http_search_citation_binding_and_old_routes_remain_readonly(self):
        before = self.hashes()
        with self.server(research=True) as (server, legacy):
            status, raw = self.request(server, '/api/c01/knowledge')
            self.assertEqual(status, 200)
            self.assertTrue(json.loads(raw)['research_binding']['exact'])
            status, raw = self.request(server, '/api/c01/knowledge/search?q=shared&kind=research_paper&limit=1')
            self.assertEqual(status, 200)
            self.assertEqual(len(json.loads(raw)['evidence']), 1)
            self.assertEqual(json.loads(raw)['database_sha256'], self.manifest['database_sha256'])
            citation = '/api/c01/knowledge/citation/' + self.references[-1]['citation_id']
            self.assertEqual(json.loads(self.request(server, citation)[1])['quote'], self.documents[2]['text'])
            self.assertEqual(json.loads(self.request(server, '/api/c01')[1]), legacy.summary)
            self.assertEqual(self.request(server, '/api/c01/report.pdf')[1], b'%PDF historical')
            self.assertEqual(self.request(server, '/api/c01/reproduction.zip')[1], b'historical ZIP')
            self.assertEqual(json.loads(self.request(server, '/api/c01/continuation')[1]), {'enabled': False})
            for path in ('/api/c01/knowledge', '/api/c01/knowledge/search?q=shared', citation):
                self.assertEqual(self.request(server, path, method='POST', body=b'{}')[0], 405)
            self.assertEqual(self.request(server, '/api/c01/knowledge', headers={'Host': 'attacker.example'})[0], 403)
            self.assertEqual(self.request(server, '/api/c01/knowledge', method='POST', headers={'Origin': 'https://attacker.example'})[0], 403)
        self.assertEqual(self.hashes(), before)

    def test_http_query_validation_disabled_and_index_change_statuses(self):
        invalid = ('/api/c01/knowledge/search', '/api/c01/knowledge/search?q=a&q=b',
                   '/api/c01/knowledge/search?q=a&unknown=b', '/api/c01/knowledge/search?q=a&limit=9',
                   '/api/c01/knowledge/search?q=a&kind=invalid', '/api/c01/knowledge/search?q=%FF',
                   '/api/c01/knowledge/search?q=%GG', '/api/c01/knowledge?path=secret',
                   '/api/c01/knowledge/citation/not-a-hash', '/api/c01/knowledge/search?q=' + 'x' * 8192)
        with self.server() as (server, _):
            for path in invalid:
                with self.subTest(path=path[:100]): self.assertEqual(self.request(server, path)[0], 400)
            self.assertEqual(self.request(server, '/api/c01/knowledge/citation/' + '0' * 64)[0], 404)
            self.database.with_suffix('.json').write_bytes(b'changed')
            self.assertEqual(self.request(server, '/api/c01/knowledge/search?q=shared')[0], 409)
            self.assertEqual(self.request(server, '/api/c01')[0], 200)
        with self.server(mount=False) as (server, _):
            self.assertEqual(json.loads(self.request(server, '/api/c01/knowledge')[1]), {'enabled': False})
            self.assertEqual(self.request(server, '/api/c01/knowledge/search?q=shared')[0], 503)
            self.assertEqual(self.request(server, '/api/c01/knowledge/citation/' + '0' * 64)[0], 503)


if __name__ == '__main__': unittest.main()
