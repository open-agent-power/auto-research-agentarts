"""Synthetic time-report preregistration; no model or action dispatch."""
import copy
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest
import uuid
from contextlib import ExitStack
from unittest.mock import patch

from autoresearch import tabular_quality_adapter as tabular
from autoresearch import synthetic_time_registration as time_registration
from autoresearch.contracts import ResearchError, fingerprint
from autoresearch.local_workbench import LocalWorkbench
from autoresearch.project_controller import ProjectController
from autoresearch.research_project import ResearchProject
import scripts.prepare_synthetic_time_fixture as fixture

PACKET_SHA = 'e0930f259b942f03ba044bdd3e5dcf1a75f49cf14fe764e07b2e495c1be157e9'


class SyntheticTimeRegistrationTests(unittest.TestCase):
    def report_dir(self):
        path = Path(__file__).resolve().parents[1] / 'runs' / ('s134-synthetic-time-' + uuid.uuid4().hex)
        self.assertFalse(path.exists())
        self.addCleanup(lambda: shutil.rmtree(path) if path.exists() and not path.is_symlink() else None)
        return path

    def no_dispatch(self, stack, *, allow_subprocess=False):
        targets = ['socket.socket.connect', 'socket.create_connection', 'urllib.request.urlopen']
        if not allow_subprocess: targets.append('subprocess.Popen')
        for target in targets:
            stack.enter_context(patch(target, side_effect=AssertionError('external call forbidden')))
        stack.enter_context(patch.object(ProjectController, '_dispatch', side_effect=AssertionError('dispatch forbidden')))
        stack.enter_context(patch.object(ResearchProject, 'step', side_effect=AssertionError('action forbidden')))
        stack.enter_context(patch.object(ResearchProject, 'read_evidence', side_effect=AssertionError('evidence forbidden')))
        stack.enter_context(patch.object(tabular, 'execute', side_effect=AssertionError('quality tool forbidden')))

    def stage(self, *, quality=True, tool_limit=2):
        report = self.report_dir(); fixture.prepare(report)
        self.assertEqual(hashlib.sha256((report/'source.json').read_bytes()).hexdigest(), PACKET_SHA)
        root = Path(self.enterContext(tempfile.TemporaryDirectory(prefix='s135-synthetic-')))
        project = ResearchProject(root / 'project')
        state = project.create(source=report/'source.json', goal='Only the fixed synthetic clock',
                               budget_ref='s135-synthetic-only', max_tool_calls=tool_limit, method_id=tabular.TOOL_ID)
        project.limit_evidence_budget(request_id='zero-evidence', expected_limit=8, new_limit=0,
                                      expected_state_version=state['state_version'], reason='Synthetic only')
        state = project.status()
        plan = {'question':'Synthetic clock?', 'basis':'Invented 28 hours', 'steps':'Register before any action',
                'expected_feedback':'No research dispatch'}
        project.save_plan(request_id='original-plan', expected_state_version=state['state_version'], plan=plan, reason='Synthetic')
        manager = LocalWorkbench(root/'manager')
        project_id = manager.import_project(request_id='import', workspace=str(project.root))['project_id']
        manager.select({'request_id':'select', 'project_id':project_id})
        project, _ = manager.binding(); state = project.status()
        context = ProjectController(project.root).selection_context()
        candidates = [x for x in context['candidates'] if x['method_id'] == tabular.TOOL_ID]
        self.assertEqual(len(candidates), 1)
        quality_body = {'request_id':'quality-registration', 'project_id':project_id,
                        'expected_state_version':state['state_version'], 'controller_request_id':'quality-future',
                        'candidate_id':candidates[0]['id'], 'conditions':{'schema_version':'tabular-quality-conditions-v1',
                        'conditions':[{'field':'rows', 'operator':'eq', 'value':28}]}}
        if quality:
            registration = manager.register_tabular_quality_conditions(quality_body)['registration']
            registration_sha = registration['registration_sha256']
        else:
            registration_sha = '0' * 64
        state = project.status()
        body = {'request_id':'time-registration', 'project_id':project_id, 'expected_state_version':state['state_version'],
                'registration_request_id':'quality-registration', 'registration_sha256':registration_sha,
                'report_dir':str(report)}
        return manager, project, report, body

    @staticmethod
    def db_state(project):
        with sqlite3.connect(project.db.resolve().as_uri() + '?mode=ro&immutable=1', uri=True) as con:
            return (con.execute('SELECT record FROM project WHERE id=1').fetchone()[0],
                    con.execute('SELECT * FROM actions ORDER BY request_id').fetchall(),
                    con.execute('SELECT * FROM replays ORDER BY request_id').fetchall())

    def test_registered_then_original_id_resume_without_any_dispatch(self):
        with ExitStack() as stack:
            self.no_dispatch(stack)
            manager, project, report, body = self.stage()
            before = project.status()
            result = manager.register_synthetic_time_report(body)
            self.assertEqual(result['status'], 'completed')
            after = project.status()
            self.assertEqual(after['state_version'], before['state_version'] + 1)
            self.assertEqual(after['budget'], before['budget'])
            self.assertEqual(after['actions'], [])
            self.assertEqual(after['evidence_actions'], [])
            self.assertEqual(len(after['synthetic_time_registrations']), 1)
            record = result['registration']
            self.assertEqual(record, after['synthetic_time_registrations'][0])
            self.assertEqual(record['schema_version'], 'synthetic-time-registration-v1')
            self.assertEqual(record['registration_request_id'], body['registration_request_id'])
            self.assertEqual(record['registration_sha256'], body['registration_sha256'])
            self.assertEqual(record['controller_request_id'], 'quality-future')
            self.assertEqual(record['report']['packet_sha256'], PACKET_SHA)
            self.assertEqual(record['report']['report_sha256'], hashlib.sha256((report/'report.json').read_bytes()).hexdigest())
            self.assertFalse(record['report']['scientific_validation'])
            self.assertFalse(record['report']['source_license_verified'])
            self.assertFalse(record['report']['execution_authorized'])
            self.assertEqual(hashlib.sha256((report/'source.json').read_bytes()).hexdigest(),
                             after['registration']['source_sha256'])
            replay = manager.resume_synthetic_time_report({'request_id':body['request_id'], 'project_id':body['project_id']})
            self.assertTrue(replay['replayed'])
            self.assertEqual(project.status(), after)
            changed = copy.deepcopy(body); changed['report_dir'] += '-other'
            with self.assertRaises(ResearchError): manager.register_synthetic_time_report(changed)
            self.assertEqual(project.status(), after)

    def test_resume_never_creates_missing_intent_or_core(self):
        with ExitStack() as stack:
            self.no_dispatch(stack)
            manager, project, _, body = self.stage()
            before = self.db_state(project)
            with self.assertRaises(ResearchError):
                manager.resume_synthetic_time_report({'request_id':body['request_id'], 'project_id':body['project_id']})
            self.assertEqual(self.db_state(project), before)

    def test_missing_original_quality_registration_rejected(self):
        with ExitStack() as stack:
            self.no_dispatch(stack)
            manager, project, _, body = self.stage(quality=False)
            before = self.db_state(project)
            with self.assertRaises(ResearchError): manager.register_synthetic_time_report(body)
            self.assertEqual(self.db_state(project), before)

    def test_original_quality_claim_missing_or_changed_rejected(self):
        for mode in ('missing','changed'):
            with self.subTest(mode=mode), ExitStack() as stack:
                self.no_dispatch(stack)
                manager, project, _, body = self.stage()
                with sqlite3.connect(project.db) as con:
                    if mode == 'missing':
                        cur = con.execute("DELETE FROM quality_manager_claims WHERE kind='registration' AND request_id=?",
                                          (body['registration_request_id'],))
                    else:
                        cur = con.execute("UPDATE quality_manager_claims SET core_sha256=? WHERE kind='registration' AND request_id=?",
                                          ('0'*64, body['registration_request_id']))
                    self.assertEqual(cur.rowcount, 1)
                before = self.db_state(project)
                with self.assertRaises(ResearchError): manager.register_synthetic_time_report(body)
                self.assertEqual(self.db_state(project), before)

    def test_original_report_files_missing_or_modified_cannot_be_registered(self):
        for filename in ('claim.json','source.csv','spec.json','source.json','report.json','receipt.json'):
            with self.subTest(filename=filename), ExitStack() as stack:
                self.no_dispatch(stack)
                manager, project, report, body = self.stage()
                target = report/filename; target.write_bytes(target.read_bytes()+b' ')
                before = self.db_state(project)
                with self.assertRaises((ResearchError, ValueError, OSError)): manager.register_synthetic_time_report(body)
                self.assertEqual(self.db_state(project), before)

    def test_other_report_path_and_stale_state_rejected(self):
        for mode in ('outside','stale','wrong-registration','future-id'):
            with self.subTest(mode=mode), ExitStack() as stack:
                self.no_dispatch(stack)
                manager, project, _, body = self.stage()
                changed = copy.deepcopy(body)
                if mode == 'outside': changed['report_dir'] = str(project.root)
                if mode == 'stale': changed['expected_state_version'] -= 1
                if mode == 'wrong-registration': changed['registration_sha256'] = 'f'*64
                if mode == 'future-id': changed['request_id'] = 'quality-future'
                before = self.db_state(project)
                with self.assertRaises((ResearchError, ValueError, OSError)): manager.register_synthetic_time_report(changed)
                self.assertEqual(self.db_state(project), before)

    def test_original_project_source_drift_is_rejected(self):
        with ExitStack() as stack:
            self.no_dispatch(stack)
            manager, project, _, body = self.stage()
            source = project.root/'source.json'; source.write_bytes(source.read_bytes()+b' ')
            before = self.db_state(project)
            with self.assertRaises(ResearchError): manager.register_synthetic_time_report(body)
            self.assertEqual(self.db_state(project), before)

    def test_future_parent_or_child_orphan_replay_rejected(self):
        for part in ('future','child'):
            for direction in ('request','target'):
                with self.subTest(part=part,direction=direction), ExitStack() as stack:
                    self.no_dispatch(stack)
                    manager, project, _, body = self.stage()
                    future = 'quality-future'
                    ident = future if part == 'future' else 'controller-child-' + fingerprint(
                        {'project_id':body['project_id'], 'request_id':future})[:32]
                    alias = 'unrelated-alias'
                    with sqlite3.connect(project.db) as con:
                        con.execute('INSERT INTO replays VALUES (?,?)',
                                    (ident, alias) if direction == 'request' else (alias, ident))
                    before = self.db_state(project)
                    with self.assertRaises(ResearchError): manager.register_synthetic_time_report(body)
                    self.assertEqual(self.db_state(project), before)

    def test_missing_time_registration_claim_cannot_be_recovered(self):
        with ExitStack() as stack:
            self.no_dispatch(stack)
            manager, project, _, body = self.stage()
            manager.register_synthetic_time_report(body)
            with sqlite3.connect(project.db) as con:
                cur = con.execute("DELETE FROM quality_manager_claims WHERE kind='synthetic_time_registration' AND request_id=?",
                                  (body['request_id'],))
                self.assertEqual(cur.rowcount, 1)
            before = self.db_state(project)
            with self.assertRaises(ResearchError):
                manager.resume_synthetic_time_report({'request_id':body['request_id'], 'project_id':body['project_id']})
            self.assertEqual(self.db_state(project), before)

    def test_manager_intent_without_core_does_not_recreate(self):
        with ExitStack() as stack:
            self.no_dispatch(stack)
            manager, project, _, body = self.stage()
            before = self.db_state(project)
            with patch.object(time_registration, '_create_project_record', side_effect=RuntimeError('synthetic interruption')):
                with self.assertRaises(RuntimeError): manager.register_synthetic_time_report(body)
            self.assertEqual(self.db_state(project), before)
            with patch.object(time_registration, '_create_project_record', side_effect=AssertionError('no core recreation')):
                with self.assertRaises(ResearchError):
                    manager.resume_synthetic_time_report({'request_id':body['request_id'], 'project_id':body['project_id']})
            self.assertEqual(self.db_state(project), before)

    def test_core_record_before_manager_receipt_only_recovers_original(self):
        with ExitStack() as stack:
            self.no_dispatch(stack)
            manager, project, _, body = self.stage()
            with patch.object(time_registration, '_inspect', side_effect=RuntimeError('before manager receipt')):
                with self.assertRaises(RuntimeError): manager.register_synthetic_time_report(body)
            saved = self.db_state(project)
            self.assertEqual(len(project.status()['synthetic_time_registrations']), 1)
            with patch.object(time_registration, '_create_project_record', side_effect=AssertionError('no recreation')):
                result = manager.resume_synthetic_time_report({'request_id':body['request_id'], 'project_id':body['project_id']})
            self.assertTrue(result['replayed'])
            self.assertEqual(self.db_state(project), saved)

    def test_report_changed_after_manager_accept_stops_without_core(self):
        with ExitStack() as stack:
            self.no_dispatch(stack)
            manager, project, report, body = self.stage()
            create = time_registration._create_project_record
            def drift(*args, **kwargs):
                path = report/'report.json'; path.write_bytes(path.read_bytes() + b' ')
                return create(*args, **kwargs)
            before = self.db_state(project)
            with patch.object(time_registration, '_create_project_record', side_effect=drift):
                with self.assertRaises(ResearchError): manager.register_synthetic_time_report(body)
            self.assertEqual(self.db_state(project), before)
            with patch.object(time_registration, '_create_project_record', side_effect=AssertionError('no recreation')):
                with self.assertRaises(ResearchError):
                    manager.resume_synthetic_time_report({'request_id':body['request_id'], 'project_id':body['project_id']})
            self.assertEqual(self.db_state(project), before)

    def test_future_or_child_occupied_by_existing_project_or_manager_command(self):
        for part in ('future','child'):
            for owner in ('feedback','budget','manager'):
                with self.subTest(part=part,owner=owner), ExitStack() as stack:
                    self.no_dispatch(stack)
                    manager, project, _, body = self.stage(tool_limit=1 if owner == 'budget' else 2)
                    future = 'quality-future'
                    ident = future if part == 'future' else 'controller-child-' + fingerprint(
                        {'project_id':body['project_id'], 'request_id':future})[:32]
                    if owner == 'feedback':
                        project.record_feedback(request_id=ident, expected_state_version=project.status()['state_version'],
                                                author='synthetic', comment='Test occupied ID', next_step='', action_id=None)
                    elif owner == 'budget':
                        project.extend_local_budget(request_id=ident, expected_limit=1, new_limit=2,
                                                    expected_state_version=project.status()['state_version'], reason='Synthetic test')
                    else:
                        manager.select({'request_id':ident, 'project_id':body['project_id']})
                    body['expected_state_version'] = project.status()['state_version']
                    before = self.db_state(project)
                    with self.assertRaises(ResearchError): manager.register_synthetic_time_report(body)
                    self.assertEqual(self.db_state(project), before)

    def test_new_process_different_registration_source_cannot_resume(self):
        with ExitStack() as stack:
            self.no_dispatch(stack, allow_subprocess=True)
            manager, project, _, body = self.stage()
            manager.register_synthetic_time_report(body)
            original_project = project.db.read_bytes(); original_manager = manager.db.read_bytes()
            original_state = project.status()
            temporary = Path(stack.enter_context(tempfile.TemporaryDirectory(prefix='s135-code-drift-')))
            root = Path(__file__).resolve().parents[1]
            copied_src = temporary/'src'; copied_src.mkdir()
            shutil.copytree(root/'src'/'autoresearch', copied_src/'autoresearch',
                            ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
            shutil.copytree(root/'scripts', temporary/'scripts', ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
            original_module = root/'src'/'autoresearch'/'synthetic_time_registration.py'
            copied_module = copied_src/'autoresearch'/'synthetic_time_registration.py'
            self.assertEqual(copied_module.read_bytes(), original_module.read_bytes())
            copied_module.write_bytes(copied_module.read_bytes() + b'\n# isolated synthetic source drift\n')
            source_files = {p.relative_to(root/'src'/'autoresearch') for p in (root/'src'/'autoresearch').rglob('*.py')}
            copied_files = {p.relative_to(copied_src/'autoresearch') for p in (copied_src/'autoresearch').rglob('*.py')}
            self.assertEqual(source_files, copied_files)
            for relative in source_files:
                if relative != Path('synthetic_time_registration.py'):
                    self.assertEqual((root/'src'/'autoresearch'/relative).read_bytes(),
                                     (copied_src/'autoresearch'/relative).read_bytes(), str(relative))
            cache = temporary/'cache'; cache.mkdir()
            program = '''\nimport json, sys\nfrom unittest.mock import patch\nfrom autoresearch.contracts import ResearchError\nfrom autoresearch.local_workbench import LocalWorkbench\nfrom autoresearch.project_controller import ProjectController\nfrom autoresearch.research_project import ResearchProject\nwith patch.object(ProjectController, "_dispatch", side_effect=AssertionError("dispatch")), patch.object(ResearchProject, "step", side_effect=AssertionError("action")), patch.object(ResearchProject, "read_evidence", side_effect=AssertionError("evidence")), patch("socket.socket.connect", side_effect=AssertionError("network")):\n    try:\n        LocalWorkbench(sys.argv[1]).resume_synthetic_time_report({"request_id":sys.argv[2], "project_id":sys.argv[3]})\n    except ResearchError as error:\n        print(json.dumps({"code":error.code}))\n    else:\n        raise AssertionError("source drift accepted")\n'''
            env = dict(os.environ, PYTHONPATH=str(copied_src), PYTHONPYCACHEPREFIX=str(cache), PYTHONDONTWRITEBYTECODE='1')
            result = subprocess.run([sys.executable, '-B', '-c', program, str(manager.root),
                                     body['request_id'], body['project_id']], cwd=temporary, env=env,
                                    text=True, capture_output=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn(json.loads(result.stdout)['code'], ('CODE_CHANGED','EVIDENCE_CHANGED'))
            self.assertEqual(project.db.read_bytes(), original_project)
            self.assertEqual(manager.db.read_bytes(), original_manager)
            self.assertEqual(project.status(), original_state)

    def test_claim_changed_during_inspection_cannot_finalize_receipt(self):
        with ExitStack() as stack:
            self.no_dispatch(stack)
            manager, project, _, body = self.stage()
            with patch.object(time_registration, '_inspect', side_effect=RuntimeError('before manager receipt')):
                with self.assertRaises(RuntimeError): manager.register_synthetic_time_report(body)
            original_manager = manager.db.read_bytes(); original_project = self.db_state(project)
            state = project.status(); self.assertEqual(state['budget']['local_tool_calls_used'], 0)
            with sqlite3.connect(project.db) as con:
                before = con.execute('SELECT * FROM quality_manager_claims ORDER BY kind,request_id').fetchall()
            original_claim = time_registration._manager_claim; changed = []
            def drift(con, kind, request_id, intent_sha256, core_sha256, **kwargs):
                result = original_claim(con, kind, request_id, intent_sha256, core_sha256, **kwargs)
                if kind == 'synthetic_time_registration' and not changed:
                    with sqlite3.connect(project.db) as writer:
                        cur = writer.execute('UPDATE quality_manager_claims SET core_sha256=? WHERE kind=? AND request_id=?',
                                             ('0'*64, kind, request_id))
                        self.assertEqual(cur.rowcount, 1)
                    changed.append(True)
                return result
            with patch.object(time_registration, '_manager_claim', side_effect=drift):
                with self.assertRaises(ResearchError):
                    manager.resume_synthetic_time_report({'request_id':body['request_id'], 'project_id':body['project_id']})
            self.assertEqual(changed, [True])
            self.assertEqual(manager.db.read_bytes(), original_manager)
            self.assertEqual(self.db_state(project), original_project)
            with sqlite3.connect(project.db) as con:
                after = con.execute('SELECT * FROM quality_manager_claims ORDER BY kind,request_id').fetchall()
            expected = [tuple('0'*64 if row[0] == 'synthetic_time_registration' and i == 3 else value
                              for i, value in enumerate(row)) for row in before]
            self.assertEqual(after, expected)

    def test_project_flock_held_while_manager_receipt_is_uncommitted(self):
        with ExitStack() as stack:
            self.no_dispatch(stack)
            manager, project, _, body = self.stage()
            save = manager._save; observed = []
            def inspect_before_commit(con, request_id, record):
                result = save(con, request_id, record)
                if request_id == body['request_id'] and record.get('status') == 'completed':
                    with sqlite3.connect(manager.db.resolve().as_uri() + '?mode=ro', uri=True) as other:
                        raw = other.execute('SELECT record FROM requests WHERE id=?', (request_id,)).fetchone()[0]
                    self.assertEqual(json.loads(raw)['status'], 'preparing')
                    fd = os.open(project.root/'writer.lock', os.O_RDWR)
                    try:
                        with self.assertRaises(BlockingIOError):
                            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    finally:
                        os.close(fd)
                    observed.append('uncommitted_and_project_busy')
                return result
            with patch.object(manager, '_save', side_effect=inspect_before_commit):
                result = manager.register_synthetic_time_report(body)
            self.assertEqual(result['status'], 'completed')
            self.assertEqual(observed, ['uncommitted_and_project_busy'])
            self.assertEqual(project.status()['budget']['local_tool_calls_used'], 0)


if __name__ == '__main__':
    unittest.main()
