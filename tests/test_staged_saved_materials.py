"""Saved staged query material in an independent synthetic engineering project."""
from contextlib import ExitStack
import copy
import os
import json
import subprocess
import sys
from pathlib import Path
import unittest
from unittest.mock import patch
from sklearn.linear_model import Ridge
from sklearn.preprocessing import StandardScaler

import test_retrieval_holdout as fixtures
from autoresearch import (saved_materials as materials, staged_feedback_reader as reader,
    staged_relevance_adapter as staged, research_plan_proposal as plan, recipe_change_proposal as recipe,
    retrieval_holdout as holdout, retrieval_lexical as lexical, relevance_retrieval_adapter as relevance,
    host_model_report, host_model_selection, method_registry, project_report)
from autoresearch.contracts import ResearchError, canonical
from autoresearch.project_controller import ProjectController
from autoresearch.research_project import ResearchProject


class StagedSavedMaterialsTests(unittest.TestCase):
    fixture = fixtures.RetrievalHoldoutTests.fixture

    def setUp(self):
        self.project, _, raw = self.fixture("negative")
        self.project.register_holdout(request_id='holdout', expected_state_version=self.project.status()['state_version'], holdout=raw)
        self.action = self.project.step(request_id='primary', expected_state_version=self.project.status()['state_version'])
        self.state = self.project.status()
        self.selector = {'kind': 'staged_retrieval_adverse_query', 'action_id': self.action['id'],
                         'result_sha256': self.action['result_sha256'], 'split': 'validation', 'query_id': 'qv'}

    def guards(self):
        stack = ExitStack(); self.addCleanup(stack.close)
        path_open, os_open = Path.open, os.open
        blocked = [self.project.root / 'private_evaluation', self.project.root / 'host-model-selections']
        def check(path):
            if isinstance(path, int): return
            path = Path(os.fsdecode(path)).absolute()
            if any(path == x or path.is_relative_to(x) for x in blocked): raise AssertionError('private access')
        def read_path(path, *a, **kw): check(path); return path_open(path, *a, **kw)
        def read_os(path, *a, **kw): check(path); return os_open(path, *a, **kw)
        stack.enter_context(patch.object(Path, 'open', read_path))
        stack.enter_context(patch.object(os, 'open', read_os))
        for obj, name in ((holdout, '_verified_private'), (staged, 'execute'), (lexical, 'build_index'),
                          (lexical, 'retrieve'), (lexical, 'metrics'), (relevance, 'retrieve'),
                          (ResearchProject, 'step'), (ResearchProject, 'resume'), (ResearchProject, '_recover'),
                          (ProjectController, 'advance_selection'), (host_model_selection, 'run_claude_selection'),
                          (host_model_selection.HostModelSelection, 'request'), (Ridge, 'fit'), (StandardScaler, 'fit')):
            stack.enter_context(patch.object(obj, name, side_effect=AssertionError('no execution')))
        return stack

    def test_real_v3_contains_saved_query_and_three_excerpts_only(self):
        with self.guards(), patch.object(reader, 'read_adverse_query', wraps=reader.read_adverse_query) as source:
            context = plan.build_context(self.project, saved_materials=[self.selector])
            self.assertEqual(source.call_count, 1)
            self.assertEqual(context['schema_version'], 'research-plan-context-v3')
            material = context['supplied_materials'][0]
            self.assertEqual(material['query']['text'], 'amber blue cyan')
            self.assertTrue(material['source_text_included'])
            self.assertEqual([a['method'] for a in material['arms']], ['bm25', 'tfidf_cosine'])
            self.assertEqual(material['arms'][0]['qrel']['grades'], {'36': 1})
            self.assertEqual(material['arms'][0]['qrel']['missing_doc_ids'], [])
            for arm in material['arms']:
                self.assertEqual(len(arm['top_documents']), min(3, len(arm['ranking'])))
                self.assertEqual([d['id'] for d in arm['top_documents']], [d['id'] for d in arm['ranking'][:3]])
            self.assertEqual(plan._context(context), context)
            self.assertIn('first three document excerpts', plan.build_prompt(context)['system'])
            self.assertNotIn('SECRET_FINAL_QUERY', canonical(context))
            self.assertNotIn('final-q', canonical(context))
        self.assertEqual(self.project.status(), self.state)

    def test_selection_limits_and_frozen_value_tampering(self):
        old = {**self.selector, 'kind': materials.RETRIEVAL_KIND}
        with self.assertRaises(ResearchError): materials.normalize_requests([old, self.selector])
        selectors = [{**self.selector, 'query_id': f'q{i}'} for i in range(5)]
        self.assertEqual(len(materials.normalize_requests(selectors[:4])), 4)
        with self.assertRaises(ResearchError): materials.normalize_requests(selectors)
        for split in ('test', 'final'):
            with self.assertRaises(ResearchError): materials.normalize_requests([{**self.selector, 'split': split}])
        context = plan.build_context(self.project, saved_materials=[self.selector])
        for alter in ('snapshot', 'grade', 'rank', 'excerpt', 'bool_rank', 'bool_line', 'bool_grade', 'contract_bool', 'source', 'producer', 'coverage'):
            bad = copy.deepcopy(context); item = bad['supplied_materials'][0]
            if alter == 'snapshot': item['binding']['snapshot_ref'] = 'f'*64
            if alter == 'grade': item['arms'][0]['qrel']['grades']['36'] = 2
            if alter == 'rank': item['arms'][0]['ranking'][0]['line'] += 1
            if alter == 'excerpt': item['arms'][0]['top_documents'][0]['line'] += 1
            if alter == 'bool_rank': item['arms'][0]['top_documents'][0]['rank'] = True
            if alter == 'bool_line':
                item['arms'][0]['ranking'][0]['line'] = 1
                item['arms'][0]['top_documents'][0]['line'] = True
            if alter == 'bool_grade':
                doc = item['arms'][0]['top_documents'][0]
                doc['relevant'] = True; doc['original_grade'] = True
                for arm in item['arms']:
                    arm['qrel']['grades'][doc['id']] = 1
                    arm['qrel']['doc_ids'] = sorted(arm['qrel']['grades'])
            if alter == 'contract_bool': item['contract']['ignore_identical_ids'] = 1
            if alter == 'source': item['query']['source_sha256'] = 'f'*64
            if alter == 'producer': item['origin']['producer_code_identity'] = 'f'*64
            if alter == 'coverage': item['coverage'] = 'complete_everything'
            with self.subTest(alter=alter), self.assertRaises(ResearchError): plan._context(bad)
        oversized = copy.deepcopy(context)
        oversized['remaining_questions'] = ['x' * 65536]
        with self.assertRaises(ResearchError): plan._context(oversized)
        before = self.project.status()
        with self.assertRaises(ResearchError): plan.build_context(self.project, saved_materials=[{**self.selector, 'result_sha256':'f'*64}])
        self.assertEqual(before, self.project.status())

    def test_missing_positive_labels_preserved(self):
        project, _, raw = self.fixture()
        project.register_holdout(request_id='holdout', expected_state_version=project.status()['state_version'], holdout=raw)
        action = project.step(request_id='primary', expected_state_version=project.status()['state_version'])
        state = project.status()
        selector = {**self.selector, 'action_id': action['id'], 'result_sha256': action['result_sha256']}
        material = plan.build_context(project, saved_materials=[selector])['supplied_materials'][0]
        self.assertEqual(material['arms'][0]['qrel']['grades'], {'b': 1, 'missing': 2})
        self.assertEqual(material['arms'][0]['qrel']['missing_doc_ids'], ['missing'])
        self.assertEqual(material['arms'][0]['metrics']['recall@20'], 0)
        self.assertEqual(project.status(), state)

    def test_default_and_legacy_prompt_match_published_7c_pin(self):
        import test_saved_retrieval_plan_materials as legacy_fixture
        fixture = legacy_fixture.SavedRetrievalPlanMaterialTests()
        fixture.setUp()
        try:
            old_context = fixture.context([fixture.selector])
        finally:
            fixture.doCleanups()
        default = plan.build_context(self.project)
        old_src = '/workspace/development-continuation-20261114/source-pins/7c60095/src'
        for context in (default, old_context):
            environment = {**os.environ, 'PYTHONPATH': old_src, 'PYTHONDONTWRITEBYTECODE': '1'}
            command = [sys.executable, '-c',
                       'import json,sys;from autoresearch.research_plan_proposal import build_prompt;'
                       'print(json.dumps(build_prompt(json.load(sys.stdin)),sort_keys=True,ensure_ascii=False))']
            result = subprocess.run(command, input=json.dumps(context), text=True, capture_output=True,
                                    check=True, env=environment)
            self.assertEqual(json.loads(result.stdout), plan.build_prompt(context))

    def test_recipe_rejects_both_build_and_frozen_context(self):
        item = {'schema_version':'research-recipe-v1', 'id':'recipe-test', 'version':1,
                'question':'Inspect synthetic results?', 'scope_match':{'domain':'retrieval','contract':staged.CONTRACT},
                'need':'next_check','ordered_methods':[{'method_id':staged.TOOL_ID,'evaluation_ref':method_registry.evaluation_ref(staged.TOOL_ID)}],
                'on_no_match':'wait'}
        with self.assertRaises(ResearchError) as error:
            recipe.build_context(self.project, item, 'Inspect evidence', saved_materials=[self.selector])
        self.assertEqual(error.exception.code, 'INVALID_RECIPE_CHANGE_CONTEXT')
        context = plan.build_context(self.project, saved_materials=[self.selector])
        value = {'schema_version':'recipe-change-context-v1', 'research_context':context,
                 'current_recipe':item, 'improvement_goal':'Inspect evidence'}
        with self.assertRaises(ResearchError) as error: recipe._context(value)
        self.assertEqual(error.exception.code, 'INVALID_RECIPE_CHANGE_CONTEXT')

    def test_synthetic_host_freezes_same_id_and_summary_omits_text(self):
        journal = host_model_selection.HostModelSelection(self.project.root)
        specification = {'request_id':'plan-material', 'provider':'delegated', 'purpose':'plan',
                         'expected_state_version':self.state['state_version'], 'decision_limit':1,
                         'cli_budget_usd':0.1, 'reason':'Synthetic engineering material fixture',
                         'saved_materials':[self.selector]}
        with patch.object(host_model_selection, 'run_claude_selection', side_effect=AssertionError('no model')):
            record = journal.prepare(**specification)
            with patch.object(plan, 'build_context', side_effect=AssertionError('replay must not rematerialize')):
                self.assertEqual(journal.prepare(**specification), record)
                with self.assertRaises(ResearchError):
                    journal.prepare(**{**specification, 'saved_materials':[{**self.selector, 'query_id':'qd'}]})
        self.assertEqual(record['prepare_specification']['saved_materials'], [self.selector])
        self.assertIn('amber blue cyan', record['prompt']['prompt'])
        summaries = host_model_report.supplied_material_summaries(record)
        self.assertEqual(len(summaries), 1)
        self.assertEqual(summaries[0]['query']['id'], 'qv')
        self.assertNotIn('amber blue cyan', canonical(summaries))
        self.assertNotIn('top_documents', canonical(summaries))
        rows = project_report._supplied_material_rows({'host_models': {'records': [record]}})
        self.assertIn('qv', canonical(rows))
        self.assertNotIn('amber blue cyan', canonical(rows))
        legacy = copy.deepcopy(record)
        legacy_item = legacy['context']['supplied_materials'][0]
        legacy_item['kind'] = 'retrieval_adverse_query'
        self.assertIn('qv', canonical(project_report._supplied_material_rows({'host_models': {'records': [legacy]}})))
        self.assertNotIn('amber blue cyan', canonical(project_report._supplied_material_rows({'host_models': {'records': [legacy]}})))
        self.assertEqual(self.project.status(), self.state)
