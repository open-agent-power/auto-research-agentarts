"""Synthetic staged purpose declaration; no external research or model calls."""
import copy
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from autoresearch import staged_relevance_adapter as staged
from autoresearch.contracts import ResearchError, canonical
from autoresearch.local_workbench import LocalWorkbench
from autoresearch.project_controller import ProjectController
from autoresearch.project_report import collect_report
from autoresearch.research_project import ResearchProject
import test_staged_relevance_adapter as staged_fixture


PURPOSE = 'operator_declared_staged_retrieval_research'
TABULAR_PURPOSE = 'operator_declared_descriptive_research'
LEGACY = 'isolated_adapter_regression_not_new_research'


class StagedProjectPurposeTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        helper = staged_fixture.StagedDevelopmentTests(methodName='runTest')
        helper.setUp()
        self.addCleanup(helper.doCleanups)
        self.packet = helper.capture()
        source_dir = self.root / 'captured'
        source_dir.mkdir()
        self.source = source_dir / 'source.json'
        self.source.write_text(canonical(self.packet), encoding='utf-8')
        self.args = {'source':self.source, 'goal':'Synthetic staged purpose',
                     'budget_ref':'synthetic-only', 'max_tool_calls':2, 'method_id':staged.TOOL_ID}

    def test_default_wire_and_explicit_declaration_do_not_change_methods_or_budget(self):
        legacy = ResearchProject(self.root / 'legacy').create(**self.args)
        project = ResearchProject(self.root / 'declared')
        declared = project.create(**self.args, evidence_purpose=PURPOSE)
        self.assertEqual(legacy['evidence_purpose'], LEGACY)
        self.assertNotIn('evidence_purpose', legacy['registration'])
        self.assertEqual(set(legacy['registration']), {'goal','budget_ref','max_tool_calls','source_sha256','method_id'})
        self.assertEqual(declared['evidence_purpose'], PURPOSE)
        self.assertEqual(declared['registration']['evidence_purpose'], PURPOSE)
        self.assertEqual({k:v for k,v in declared['registration'].items() if k != 'evidence_purpose'}, legacy['registration'])
        for key in ('budget','source_scope','source_snapshot_sha256','supported_methods','initial_decision'):
            self.assertEqual(declared[key], legacy[key])
        self.assertEqual(declared['actions'], [])
        self.assertEqual(declared['budget']['new_model_requests'], 0)
        self.assertEqual(declared['budget']['new_fits'], 0)
        self.assertIs(ProjectController(project.root).selection_context()['scientific_validation'], False)
        self.assertEqual(project.create(**self.args, evidence_purpose=PURPOSE), declared)
        with self.assertRaises(ResearchError) as error:
            project.create(**self.args)
        self.assertEqual(error.exception.code, 'CONFIG_CHANGED')
        with self.assertRaises(ResearchError) as error:
            ResearchProject(self.root / 'legacy').create(**self.args, evidence_purpose=PURPOSE)
        self.assertEqual(error.exception.code, 'CONFIG_CHANGED')

    def test_invalid_purpose_or_method_rejected_before_source_or_workspace_read(self):
        for index, value in enumerate((None, True, 0, '', 'unknown', LEGACY, TABULAR_PURPOSE, [], {})):
            with self.subTest(value=value):
                root = self.root / ('bad-purpose-' + str(index))
                args = {**self.args, 'source':self.root / 'nonexistent-source'}
                with patch('pathlib.Path.read_bytes', side_effect=AssertionError('source bytes must not be read')):
                    with self.assertRaises(ResearchError) as error:
                        ResearchProject(root).create(**args, evidence_purpose=value)
                self.assertEqual(error.exception.code, 'INVALID_REQUEST')
                self.assertFalse(root.exists())
        for method in ('data.tabular-quality-audit', 'p02.saved-oof-residuals'):
            with self.subTest(method=method):
                root = self.root / ('wrong-method-' + method.replace('.', '-'))
                with patch('pathlib.Path.read_bytes', side_effect=AssertionError('source bytes must not be read')):
                    with self.assertRaises(ResearchError) as error:
                        ResearchProject(root).create(**{**self.args, 'source':self.root / 'absent', 'method_id':method}, evidence_purpose=PURPOSE)
                self.assertEqual(error.exception.code, 'INVALID_REQUEST')
                self.assertFalse(root.exists())

    def test_exact_staged_scope_is_checked_even_if_loader_returns_wrong_scope(self):
        cases = (
            ('packet-task-kind', ('task_kind',), 'other'),
            ('packet-stage', ('stage',), 'final'),
            ('scope-domain', ('scope','domain'), 'other'),
            ('scope-stage', ('scope','stage'), 'final'),
            ('scope-contract', ('scope','contract'), 'other'),
            ('scope-qrels', ('scope','qrels_semantics'), 'other'),
            ('scope-extra-split', ('scope','query_split_counts'), {'dev':1,'validation':1,'test':1}),
            ('scope-bool-count', ('scope','query_split_counts','dev'), True),
            ('scope-zero-count', ('scope','query_split_counts','validation'), 0),
        )
        for name, keys, bad in cases:
            with self.subTest(name=name):
                root = self.root / ('wrong-' + name)
                packet = copy.deepcopy(self.packet)
                target = packet
                for key in keys[:-1]:
                    target = target[key]
                target[keys[-1]] = bad
                with patch.object(staged, 'load_source', return_value=packet):
                    with self.assertRaises(ResearchError):
                        ResearchProject(root).create(**self.args, evidence_purpose=PURPOSE)
                self.assertFalse(root.exists())

    def test_registration_top_and_scope_tamper_are_rejected_without_repair(self):
        for field in ('top','registration','remove_registration','scope_domain','scope_stage','scope_contract'):
            with self.subTest(field=field):
                project = ResearchProject(self.root / ('tamper-' + field))
                project.create(**self.args, evidence_purpose=PURPOSE)
                with sqlite3.connect(project.db) as con:
                    state = json.loads(con.execute('SELECT record FROM project WHERE id=1').fetchone()[0])
                    if field == 'top': state['evidence_purpose'] = LEGACY
                    elif field == 'registration': state['registration']['evidence_purpose'] = TABULAR_PURPOSE
                    elif field == 'remove_registration': del state['registration']['evidence_purpose']
                    else: state['source_scope'][field.removeprefix('scope_')] = 'other'
                    con.execute('UPDATE project SET record=? WHERE id=1', (canonical(state),))
                before = project.db.read_bytes()
                with self.assertRaises(ResearchError) as error:
                    project.status()
                self.assertEqual(error.exception.code, 'EVIDENCE_CHANGED')
                self.assertEqual(project.db.read_bytes(), before)

    def test_reopen_rejects_source_and_current_core_drift_without_writes(self):
        project = ResearchProject(self.root / 'reopen')
        initial = project.create(**self.args, evidence_purpose=PURPOSE)
        original_source = (project.root / 'source.json').read_bytes()
        original_db = project.db.read_bytes()
        with patch('autoresearch.research_project.code_identity', return_value='0' * 64):
            with self.assertRaises(ResearchError) as error:
                project.create(**self.args, evidence_purpose=PURPOSE)
        self.assertIn(error.exception.code, ('CODE_CHANGED','EVIDENCE_CHANGED'))
        self.assertEqual(project.db.read_bytes(), original_db)
        self.assertEqual((project.root / 'source.json').read_bytes(), original_source)
        self.assertEqual(project.status(), initial)
        (project.root / 'source.json').write_bytes(original_source + b' ')
        changed = (project.root / 'source.json').read_bytes()
        before_db = project.db.read_bytes()
        with self.assertRaises(ResearchError):
            project.create(**self.args, evidence_purpose=PURPOSE)
        self.assertEqual((project.root / 'source.json').read_bytes(), changed)
        self.assertEqual(project.db.read_bytes(), before_db)

    def test_valid_shape_scope_drift_is_detected_on_reopen_not_claimed_by_status(self):
        project = ResearchProject(self.root / 'scope-drift')
        project.create(**self.args, evidence_purpose=PURPOSE)
        with sqlite3.connect(project.db) as con:
            state = json.loads(con.execute('SELECT record FROM project WHERE id=1').fetchone()[0])
            state['source_scope']['query_split_counts']['dev'] += 1
            con.execute('UPDATE project SET record=? WHERE id=1', (canonical(state),))
        readable = project.status()
        self.assertEqual(readable['source_scope']['query_split_counts']['dev'],
                         self.packet['scope']['query_split_counts']['dev'] + 1)
        before_db = project.db.read_bytes()
        with self.assertRaises(ResearchError) as error:
            project.create(**self.args, evidence_purpose=PURPOSE)
        self.assertEqual(error.exception.code, 'EVIDENCE_CHANGED')
        self.assertEqual(project.db.read_bytes(), before_db)

    def test_partial_create_is_not_rebuilt(self):
        project = ResearchProject(self.root / 'partial')
        with patch('autoresearch.research_project.sqlite3.connect', side_effect=OSError('synthetic interruption')):
            with self.assertRaises(OSError):
                project.create(**self.args, evidence_purpose=PURPOSE)
        raw = (project.root / 'source.json').read_bytes()
        self.assertFalse(project.db.exists())
        with self.assertRaises(ResearchError) as error:
            project.create(**self.args, evidence_purpose=PURPOSE)
        self.assertEqual(error.exception.code, 'WORKSPACE_EXISTS')
        self.assertEqual((project.root / 'source.json').read_bytes(), raw)
        self.assertFalse(project.db.exists())

    def test_manager_import_original_id_and_report_preserve_declaration(self):
        project = ResearchProject(self.root / 'to-import')
        initial = project.create(**self.args, evidence_purpose=PURPOSE)
        manager = LocalWorkbench(self.root / 'manager')
        receipt = manager.import_project(request_id='purpose-import', workspace=project.root)
        replay = manager.import_project(request_id='purpose-import', workspace=project.root)
        self.assertTrue(replay['replayed'])
        self.assertEqual(receipt['project_id'], initial['id'])
        with self.assertRaises(ResearchError) as error:
            manager.import_project(request_id='purpose-import', workspace=self.root / 'different')
        self.assertEqual(error.exception.code, 'IDEMPOTENCY_CONFLICT')
        with manager._connect(readonly=True) as con:
            _, moved = manager._project(con, initial['id'])
        state = moved.status()
        self.assertEqual(state['registration']['evidence_purpose'], PURPOSE)
        self.assertEqual(state['evidence_purpose'], PURPOSE)
        self.assertEqual(state['budget'], initial['budget'])
        self.assertEqual(state['actions'], [])
        report = collect_report(moved.root)
        self.assertEqual(report['project']['evidence_purpose'], PURPOSE)
        self.assertEqual(report['project']['registration']['evidence_purpose'], PURPOSE)
        self.assertEqual(moved.status(), state)


if __name__ == '__main__':
    unittest.main()
