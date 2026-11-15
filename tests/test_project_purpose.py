"""Opt-in Project purpose is an operator claim, not an authorization."""
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from autoresearch.contracts import ResearchError, canonical
from autoresearch.local_workbench import LocalWorkbench
from autoresearch.project_controller import ProjectController
from autoresearch.project_report import collect_report
from autoresearch.research_project import ResearchProject
import test_numeric_association as numeric_fixtures

PURPOSE = 'operator_declared_descriptive_research'
LEGACY = 'isolated_adapter_regression_not_new_research'


class ProjectPurposeTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        fixture = numeric_fixtures.NumericAssociationTests(methodName='runTest')
        self.addCleanup(fixture.doCleanups)
        payload = fixture.payload('group,x,outcome\na,1,2\na,2,4\na,3,6\nb,1,1\nb,2,3\nb,3,5\n')
        (self.root/'capture').mkdir()
        self.source = self.root/'capture/source.json'
        self.source.write_text(canonical(payload), encoding='utf-8')
        self.args = {'source':self.source, 'goal':'Synthetic wire baseline', 'budget_ref':'fixture:only',
                     'max_tool_calls':2, 'method_id':'data.tabular-quality-audit'}

    def test_legacy_default_and_explicit_state_reopen_without_budget_or_method_change(self):
        old = ResearchProject(self.root/'legacy')
        legacy = old.create(**self.args)
        self.assertEqual(legacy['evidence_purpose'], LEGACY)
        self.assertNotIn('evidence_purpose', legacy['registration'])
        self.assertEqual(set(legacy['registration']), {'goal','budget_ref','max_tool_calls','source_sha256','method_id'})
        self.assertEqual(old.create(**self.args), legacy)
        new = ResearchProject(self.root/'declared')
        state = new.create(**self.args, evidence_purpose=PURPOSE)
        self.assertEqual(state['evidence_purpose'], PURPOSE)
        self.assertEqual(state['registration']['evidence_purpose'], PURPOSE)
        self.assertEqual(new.create(**self.args, evidence_purpose=PURPOSE), state)
        self.assertEqual(state['budget'],legacy['budget'])
        new_options,old_options=new.method_options(),old.method_options()
        new_options.pop('snapshot_ref');old_options.pop('snapshot_ref')
        self.assertEqual(new_options,old_options)
        self.assertEqual(state['actions'],[])
        context=ProjectController(new.root).selection_context()
        self.assertIs(context['scientific_validation'],False)
        child='import json,sys;from autoresearch.research_project import ResearchProject;print(json.dumps(ResearchProject(sys.argv[1]).status(),sort_keys=True))'
        replay=subprocess.run([sys.executable,'-B','-c',child,str(new.root)],capture_output=True,text=True,check=True)
        self.assertEqual(json.loads(replay.stdout),state)
        for obj,kwargs in ((old,{'evidence_purpose':PURPOSE}),(new,{})):
            with self.assertRaises(ResearchError) as error:obj.create(**self.args,**kwargs)
            self.assertEqual(error.exception.code,'CONFIG_CHANGED')

    def test_bad_values_and_non_tabular_declaration_never_create_directory(self):
        for index, value in enumerate((None,True,0,'','unknown',LEGACY,[],{})):
            root=self.root/('invalid-'+str(index))
            with self.subTest(value=value),self.assertRaises(ResearchError) as error:
                ResearchProject(root).create(**self.args,evidence_purpose=value)
            self.assertEqual(error.exception.code,'INVALID_REQUEST');self.assertFalse(root.exists())
        other=self.root/'non-tabular'
        with self.assertRaises(ResearchError) as error:
            ResearchProject(other).create(**{**self.args,'method_id':'p02.saved-oof-residuals'},evidence_purpose=PURPOSE)
        self.assertEqual(error.exception.code,'INVALID_REQUEST');self.assertFalse(other.exists())

    def test_import_same_id_replay_and_conflict_retain_original_declaration(self):
        project=ResearchProject(self.root/'for-import')
        original=project.create(**self.args,evidence_purpose=PURPOSE)
        manager=LocalWorkbench(self.root/'manager')
        receipt=manager.import_project(request_id='purpose-import',workspace=project.root)
        replay=manager.import_project(request_id='purpose-import',workspace=project.root)
        self.assertTrue(replay['replayed']);self.assertEqual(receipt['project_id'],original['id'])
        with self.assertRaises(ResearchError) as error:
            manager.import_project(request_id='purpose-import',workspace=self.root/'other')
        self.assertEqual(error.exception.code,'IDEMPOTENCY_CONFLICT')
        with manager._connect(readonly=True) as connection:
            _,moved=manager._project(connection,original['id'])
        state=moved.status();self.assertEqual(state['evidence_purpose'],PURPOSE)
        self.assertEqual(state['registration']['evidence_purpose'],PURPOSE)
        self.assertEqual(state['budget'],original['budget']);self.assertEqual(state['actions'],[])
        report=collect_report(moved.root)
        self.assertEqual(report['project']['evidence_purpose'],PURPOSE)
        self.assertEqual(report['project']['registration']['evidence_purpose'],PURPOSE)
        self.assertEqual(moved.status(),state)

    def test_partial_create_is_preserved_and_not_rebuilt(self):
        root=self.root/'partial';project=ResearchProject(root)
        with patch('autoresearch.research_project.sqlite3.connect',side_effect=OSError('synthetic interruption')):
            with self.assertRaises(OSError):project.create(**self.args,evidence_purpose=PURPOSE)
        raw=(root/'source.json').read_bytes();self.assertFalse((root/'project.sqlite').exists())
        with self.assertRaises(ResearchError) as error:project.create(**self.args,evidence_purpose=PURPOSE)
        self.assertEqual(error.exception.code,'WORKSPACE_EXISTS');self.assertEqual((root/'source.json').read_bytes(),raw)
        self.assertFalse((root/'project.sqlite').exists())

    def test_explicit_reopen_detects_internal_source_drift_without_writes(self):
        root=self.root/'source-drift';project=ResearchProject(root)
        before=project.create(**self.args,evidence_purpose=PURPOSE)
        source=root/'source.json';source.write_bytes(source.read_bytes()+b' ')
        corrupted=source.read_bytes();database=project.db.read_bytes()
        with self.assertRaises(ResearchError) as error:
            project.create(**self.args,evidence_purpose=PURPOSE)
        self.assertEqual(error.exception.code,'EVIDENCE_CHANGED')
        self.assertEqual(source.read_bytes(),corrupted);self.assertEqual(project.db.read_bytes(),database)
        self.assertEqual(project.status(),before)

    def test_tampering_with_either_purpose_binding_is_rejected_read_only(self):
        for index, field in enumerate(('top','registration','remove_registration')):
            with self.subTest(field=field):
                root=self.root/('tamper-'+str(index));project=ResearchProject(root)
                project.create(**self.args,evidence_purpose=PURPOSE)
                with sqlite3.connect(project.db) as connection:
                    state=json.loads(connection.execute('SELECT record FROM project WHERE id=1').fetchone()[0])
                    if field=='top':state['evidence_purpose']=LEGACY
                    elif field=='registration':state['registration']['evidence_purpose']='other'
                    else:del state['registration']['evidence_purpose']
                    connection.execute('UPDATE project SET record=? WHERE id=1',(canonical(state),))
                before=project.db.read_bytes()
                with self.assertRaises(ResearchError) as error:project.status()
                self.assertEqual(error.exception.code,'EVIDENCE_CHANGED');self.assertEqual(project.db.read_bytes(),before)


if __name__ == '__main__': unittest.main()
