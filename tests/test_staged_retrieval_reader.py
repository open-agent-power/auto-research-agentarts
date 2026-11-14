"""Bounded saved development views; synthetic project and no later evaluation."""
from contextlib import ExitStack
import copy
import hashlib
import json
import os
import sqlite3
from pathlib import Path
from threading import Thread
import unittest
from unittest.mock import patch
from urllib.parse import urlencode
from urllib.request import urlopen
from urllib.error import HTTPError

import test_retrieval_holdout as fixtures
from autoresearch import (staged_feedback_reader as reader, staged_relevance_adapter as staged,
                          retrieval_holdout as holdout, retrieval_lexical as lexical,
                          relevance_retrieval_adapter as relevance, project_workbench)
from autoresearch.contracts import ResearchError, canonical
from autoresearch.project_controller import ProjectController
from autoresearch.research_project import ResearchProject


class StagedRetrievalReaderTests(unittest.TestCase):
    fixture = fixtures.RetrievalHoldoutTests.fixture

    def setUp(self):
        self.project, _, raw = self.fixture()
        self.project.register_holdout(request_id='holdout', expected_state_version=self.project.status()['state_version'], holdout=raw)
        self.action = self.project.step(request_id='primary', expected_state_version=self.project.status()['state_version'])
        self.state = self.project.status()

    def guarded(self):
        stack = ExitStack()
        self.addCleanup(stack.close)
        real_open, real_os_open = Path.open, os.open
        private = self.project.root / 'private_evaluation'
        host = self.project.root / 'host-model-selections'
        def check(path):
            if isinstance(path, int): return
            path = Path(os.fsdecode(path)).absolute()
            if path == private or path.is_relative_to(private) or path == host or path.is_relative_to(host):
                raise AssertionError('private data was accessed')
        def path_open(path, *a, **kw): check(path); return real_open(path, *a, **kw)
        def os_open(path, *a, **kw): check(path); return real_os_open(path, *a, **kw)
        stack.enter_context(patch.object(Path, 'open', path_open))
        stack.enter_context(patch.object(os, 'open', os_open))
        for obj, name in ((holdout, '_verified_private'), (staged, 'execute'), (lexical, 'build_index'),
                          (lexical, 'retrieve'), (lexical, 'metrics'), (relevance, 'retrieve'),
                          (ResearchProject, 'step'), (ResearchProject, 'resume'), (ResearchProject, '_recover'),
                          (ProjectController, 'advance_selection')):
            stack.enter_context(patch.object(obj, name, side_effect=AssertionError('no execution')))
        return stack

    def test_saved_page_detail_and_missing_positives_under_guards(self):
        before = copy.deepcopy(self.project.status())
        with self.guarded():
            page = reader.read_adverse_page(self.project, before, action_id=self.action['id'])
            self.assertEqual(page['schema_version'], 'saved-staged-relevance-adverse-page-v1')
            row = next(x for x in page['items'] if x['query_id'] == 'qv')
            detail = reader.read_adverse_query(self.project, before, action_id=self.action['id'], split='validation', query_id='qv')
            self.assertEqual(detail['schema_version'], 'saved-staged-relevance-query-v1')
            self.assertEqual(detail['query']['text'], 'unknown token')
            self.assertEqual(detail['binding']['primary_result_sha256'], self.action['result_sha256'])
            self.assertEqual([arm['method'] for arm in detail['arms']], ['bm25', 'tfidf_cosine'])
            self.assertEqual(detail['arms'][0]['qrel']['grades'], {'b': 1, 'missing': 2})
            self.assertEqual(detail['arms'][0]['qrel']['missing_doc_ids'], ['missing'])
            self.assertEqual(detail['arms'][0]['metrics'], row['metrics']['bm25'])
            self.assertEqual(reader.read_validation_delta(self.project, before, self.action, 'recall@20'), 0)
            self.assertNotIn('SECRET_FINAL_QUERY', canonical(detail))
        self.assertEqual(self.project.status(), before)
        self.assertEqual(before['budget']['local_tool_calls_used'], 1)

    def test_rejects_wrong_split_action_bounds_and_stale_snapshot(self):
        for kwargs in ({'action_id': 'action-other', 'split': 'validation', 'query_id': 'qv'},
                       {'action_id': self.action['id'], 'split': 'test', 'query_id': 'qv'},
                       {'action_id': self.action['id'], 'split': 'final', 'query_id': 'qv'},
                       {'action_id': self.action['id'], 'split': 'validation', 'query_id': 'absent'}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ResearchError):
                reader.read_adverse_query(self.project, self.state, **kwargs)
        for offset, limit in ((-1, 1), (0, 26), (True, 1), (999, 1)):
            with self.assertRaises(ResearchError):
                reader.read_adverse_page(self.project, self.state, action_id=self.action['id'], offset=offset, limit=limit)
        stale = copy.deepcopy(self.state)
        stale['snapshot_ref'] = 'f' * 64
        with self.assertRaises(ResearchError) as error:
            reader.read_adverse_page(self.project, stale, action_id=self.action['id'])
        self.assertEqual(error.exception.code, 'STALE_STATE')
        with patch.object(reader.legacy, 'MAX_RESPONSE_BYTES', 50):
            with self.assertRaises(ResearchError) as error:
                reader.read_adverse_page(self.project, self.state, action_id=self.action['id'])
            self.assertEqual(error.exception.code, 'READER_RESPONSE_TOO_LARGE')

    def test_source_and_artifact_tampering_rejected(self):
        for path in (self.project.root / 'source.json', self.project._artifact(self.action)):
            original = path.read_bytes()
            try:
                if path.name == 'source.json':
                    path.write_bytes(original + b' ')
                else:
                    altered = json.loads(original)
                    altered['tool_result']['result']['rankings'][0]['query_line'] += 1
                    path.write_text(canonical(altered))
                with self.subTest(path=path), self.assertRaises(ResearchError):
                    reader.read_adverse_page(self.project, self.state, action_id=self.action['id'])
            finally:
                path.write_bytes(original)

    def test_sql_fingerprint_and_midread_change_reject(self):
        with sqlite3.connect(self.project.db) as con:
            original = con.execute('SELECT fingerprint FROM actions WHERE request_id=?', (self.action['request_id'],)).fetchone()[0]
            con.execute('UPDATE actions SET fingerprint=? WHERE request_id=?', ('f' * 64, self.action['request_id']))
        try:
            with self.assertRaises(ResearchError):
                reader.read_adverse_page(self.project, self.state, action_id=self.action['id'])
        finally:
            with sqlite3.connect(self.project.db) as con:
                con.execute('UPDATE actions SET fingerprint=? WHERE request_id=?', (original, self.action['request_id']))
        other = copy.deepcopy(self.state)
        other['snapshot_ref'] = 'e' * 64
        with patch.object(self.project, 'status', side_effect=[self.state, other]):
            with self.assertRaises(ResearchError) as error:
                reader.read_adverse_page(self.project, self.state, action_id=self.action['id'])
        self.assertEqual(error.exception.code, 'STALE_STATE')

    def test_http_existing_routes_bind_real_staged_project(self):
        server = project_workbench.create_project_server(workspace=self.project.root, port=0)
        thread = Thread(target=lambda: server.serve_forever(poll_interval=.01), daemon=True)
        thread.start()
        def close():
            server.shutdown(); server.server_close(); thread.join(2)
        self.addCleanup(close)
        base = f'http://127.0.0.1:{server.server_port}'
        selector = {'project_id': self.state['id'], 'snapshot_ref': self.state['snapshot_ref'], 'action_id': self.action['id']}
        def get(route, values):
            try:
                with urlopen(base + route + '?' + urlencode(values), timeout=10) as response:
                    return response.status, json.loads(response.read())
            except HTTPError as e:
                return e.code, json.loads(e.read())
        with self.guarded():
            status, page = get('/api/project/retrieval-adverse.json', selector)
            self.assertEqual(status, 200, page)
            self.assertEqual(page['schema_version'], 'saved-staged-relevance-adverse-page-v1')
            status, detail = get('/api/project/retrieval-query.json', {**selector, 'split':'validation', 'query_id':'qv'})
            self.assertEqual(status, 200, detail)
            self.assertEqual(detail['query']['text'], 'unknown token')
            self.assertEqual(get('/api/project/retrieval-query.json', {**selector, 'split':'test', 'query_id':'qv'})[0], 400)
            self.assertEqual(get('/api/project/retrieval-query.json', {**selector, 'snapshot_ref':'f'*64, 'split':'validation', 'query_id':'qv'})[0], 409)
        self.assertEqual(self.project.status(), self.state)
