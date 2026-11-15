"""Synthetic manager-owned staged preregistration; no study actions or models."""
import copy
import importlib.util
import marshal
import os
from pathlib import Path
import py_compile
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from autoresearch.contracts import ResearchError
from autoresearch.local_workbench import LocalWorkbench
from autoresearch.project_controller import ProjectController
from autoresearch import hypothesis_feedback as hypotheses, staged_relevance_adapter as staged
import test_retrieval_holdout as fixtures


class StagedHypothesisWorkbenchTests(unittest.TestCase):
    def fixture(self):
        helper = fixtures.RetrievalHoldoutTests()
        self.addCleanup(helper.doCleanups)
        source, _, _ = helper.fixture()
        tmp = self.enterContext(tempfile.TemporaryDirectory())
        manager = LocalWorkbench(Path(tmp) / 'manager')
        imported = manager.import_project(request_id='manager-import', workspace=str(source.root))
        manager.select({'request_id': 'manager-select', 'project_id': imported['project_id']})
        project, _ = manager.binding()
        state = project.status()
        context = ProjectController(project.root).selection_context()
        candidate = next(c for c in context['candidates'] if c['method_id'] == staged.TOOL_ID)
        body = {'request_id':'hypothesis-register', 'project_id':state['id'], 'expected_state_version':state['state_version'],
                'hypothesis':{'candidate_id':candidate['id'], 'controller_request_id':'hypothesis-future-primary',
                    'conditions':[{'metric':'recall@20','operator':'gt','threshold':0},
                                  {'metric':'mrr@10','operator':'gte','threshold':0}],
                    'branches':{'condition_met':{'kind':'wait'}, 'condition_not_met':{'kind':'wait'}}}}
        return manager, project, body

    def test_success_replay_and_historical_plan(self):
        manager, project, body = self.fixture()
        before = project.status()
        answer = manager.register_staged_hypothesis(body)
        self.assertEqual(answer['registration']['schema_version'], 'hypothesis-registration-v2')
        self.assertFalse(answer['replayed'])
        self.assertEqual(manager.resume_staged_hypothesis({'request_id':body['request_id'],'project_id':body['project_id']})['registration'],answer['registration'])
        self.assertTrue(manager.register_staged_hypothesis(body)['replayed'])
        with self.assertRaises(ResearchError) as conflict: manager.register_hypothesis(body)
        self.assertEqual(conflict.exception.code, 'IDEMPOTENCY_CONFLICT')
        changed = copy.deepcopy(body); changed['hypothesis']['conditions'][0]['threshold'] = 0.2
        with self.assertRaises(ResearchError) as conflict: manager.register_staged_hypothesis(changed)
        self.assertEqual(conflict.exception.code, 'IDEMPOTENCY_CONFLICT')
        after = project.status()
        self.assertEqual(after['budget'],before['budget']); self.assertEqual(after['actions'],[])
        feedback = hypotheses.feedback_context(project, after)['items'][0]
        self.assertEqual(feedback['outcome'], 'unknown')
        self.assertIsNone(feedback['value'])
        project.save_plan(request_id='later-plan',expected_state_version=after['state_version'],
                          plan={'question':'Later?', 'basis':'synthetic', 'steps':'wait', 'expected_feedback':'none'}, reason='fixture')
        self.assertTrue(manager.resume_staged_hypothesis({'request_id':body['request_id'],'project_id':body['project_id']})['replayed'])

    def test_missing_core_never_recreates_and_pending_blocks(self):
        manager, project, body = self.fixture()
        before = project.status()
        with self.assertRaises(ResearchError) as missing:
            manager.resume_staged_hypothesis({'request_id':body['request_id'],'project_id':body['project_id']})
        self.assertEqual(missing.exception.code, 'OPERATION_INCOMPLETE')
        with patch.object(hypotheses, '_register_with_created', side_effect=RuntimeError('interruption')):
            with self.assertRaises(RuntimeError): manager.register_staged_hypothesis(body)
        self.assertEqual(project.status(),before)
        self.assertTrue(any(x['request_id']==body['request_id'] for x in manager.describe()['pending_requests']))
        with patch.object(hypotheses, '_register_with_created', side_effect=AssertionError('must not create')):
            with self.assertRaises(ResearchError) as error:
                manager.resume_staged_hypothesis({'request_id':body['request_id'],'project_id':body['project_id']})
            self.assertEqual(error.exception.code,'OPERATION_INCOMPLETE')
            with self.assertRaises(ResearchError): manager.register_staged_hypothesis(body)
        with self.assertRaises(ResearchError): manager.register_hypothesis(body)
        self.assertEqual(project.status(),before)

    def test_core_committed_manager_interruption_and_claim_tamper(self):
        manager, project, body = self.fixture()
        with patch.object(manager,'_finish_staged_hypothesis',side_effect=RuntimeError('interruption')):
            with self.assertRaises(RuntimeError): manager.register_staged_hypothesis(body)
        before = project.status()
        with patch.object(hypotheses,'_register_with_created',side_effect=AssertionError('must not dispatch')):
            answer=manager.resume_staged_hypothesis({'request_id':body['request_id'],'project_id':body['project_id']})
        self.assertTrue(answer['replayed']);self.assertEqual(project.status(),before)
        with project._connect() as con:
            con.execute("DELETE FROM quality_manager_claims WHERE kind='hypothesis_registration'")
        with self.assertRaises(ResearchError): manager.resume_staged_hypothesis({'request_id':body['request_id'],'project_id':body['project_id']})

    def test_direct_core_cannot_be_adopted_and_conflicting_bodies_reject(self):
        manager, project, body = self.fixture()
        original = hypotheses._register_with_created
        def competitor(*args, **kwargs):
            original(project, **{k:v for k,v in body.items() if k != 'project_id'})
            return original(*args, **kwargs)
        with patch.object(hypotheses, '_register_with_created', side_effect=competitor):
            with self.assertRaises(ResearchError) as error: manager.register_staged_hypothesis(body)
        self.assertEqual(error.exception.code,'OPERATION_INCOMPLETE')
        with self.assertRaises(ResearchError): manager.resume_staged_hypothesis({'request_id':body['request_id'],'project_id':body['project_id']})
        changed=copy.deepcopy(body);changed['hypothesis']['conditions'][0]['threshold']=0.1
        with self.assertRaises(ResearchError): manager.register_staged_hypothesis(changed)
        self.assertEqual(project.status()['actions'],[])

    def test_drift_and_preexisting_cached_module_are_rejected(self):
        manager, project, body = self.fixture()
        before = project.status()
        with patch('autoresearch.local_workbench._staged_source_tree_identity', return_value='changed'):
            with self.assertRaises(ResearchError) as error: manager.register_staged_hypothesis(body)
        self.assertEqual(error.exception.code, 'CODE_CHANGED')
        self.assertEqual(project.status(), before)
        tmp = Path(self.enterContext(tempfile.TemporaryDirectory()))
        source = Path(__file__).resolve().parents[1] / 'src' / 'autoresearch'
        shutil.copytree(source, tmp / 'autoresearch', ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
        pyfile = tmp / 'autoresearch' / 'hypothesis_feedback.py'
        cachedir = tmp / 'cache'
        oldprefix = sys.pycache_prefix
        try:
            sys.pycache_prefix = str(cachedir)
            cache = Path(importlib.util.cache_from_source(str(pyfile)))
        finally:
            sys.pycache_prefix = oldprefix
        cache.parent.mkdir(parents=True)
        py_compile.compile(str(pyfile), cfile=str(cache), doraise=True)
        header = cache.read_bytes()[:16]
        cache.write_bytes(header + marshal.dumps(compile('SENTINEL = True\n', str(pyfile), 'exec')))
        env = {**os.environ, 'PYTHONPATH': str(tmp), 'PYTHONPYCACHEPREFIX': str(cachedir), 'PYTHONDONTWRITEBYTECODE': '1'}
        script = ("from autoresearch import hypothesis_feedback as h\n"
                  "from autoresearch.local_workbench import _check_staged_runtime\n"
                  "from autoresearch.contracts import ResearchError\n"
                  "assert h.SENTINEL\n"
                  "try: _check_staged_runtime()\n"
                  "except ResearchError as e: assert e.code == 'CODE_CHANGED'\n"
                  "else: raise AssertionError('cached module accepted')\n")
        result = subprocess.run([sys.executable, '-B', '-c', script], cwd=tmp, env=env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_source_identity_drift_after_core_commit_stops_receipt(self):
        from autoresearch import local_workbench
        manager, project, body = self.fixture()
        original = local_workbench._STAGED_BOOT_SOURCE_IDENTITY
        with patch.object(local_workbench, '_staged_source_tree_identity', side_effect=[original,original,original,'changed']):
            with self.assertRaises(ResearchError) as error: manager.register_staged_hypothesis(body)
        self.assertEqual(error.exception.code, 'CODE_CHANGED')
        state = project.status()
        self.assertEqual(len(state['hypothesis_registrations']), 1)
        self.assertEqual(state['actions'], [])
        self.assertTrue(any(item['request_id'] == body['request_id'] for item in manager.describe()['pending_requests']))
        with patch.object(hypotheses, '_register_with_created', side_effect=AssertionError('must not create again')):
            answer = manager.resume_staged_hypothesis({'request_id':body['request_id'],'project_id':body['project_id']})
        self.assertEqual(answer['registration']['request_id'], body['request_id'])

    def test_preflight_late_cached_module_stops_before_manager_intent(self):
        manager, project, body = self.fixture()
        before = project.status()
        cached = Path(self.enterContext(tempfile.TemporaryDirectory())) / 'late.pyc'
        cached.write_bytes(b'synthetic cached module')
        original_preflight = manager._preflight_staged_hypothesis
        original_cached = hypotheses.__cached__
        def late(*args, **kwargs):
            context = original_preflight(*args, **kwargs)
            hypotheses.__cached__ = str(cached)
            return context
        try:
            with patch.object(manager, '_preflight_staged_hypothesis', side_effect=late):
                with self.assertRaises(ResearchError) as error: manager.register_staged_hypothesis(body)
            self.assertEqual(error.exception.code, 'CODE_CHANGED')
        finally:
            hypotheses.__cached__ = original_cached
        with manager._connect(readonly=True) as con:
            self.assertIsNone(con.execute('SELECT 1 FROM requests WHERE id=?', (body['request_id'],)).fetchone())
        self.assertEqual(project.status(), before)


if __name__ == '__main__': unittest.main()
