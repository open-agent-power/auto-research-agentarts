"""S134 artificial time quality action: strict ownership and no redispatch."""
import copy
import json
import sqlite3
import unittest
from contextlib import ExitStack
from unittest.mock import patch

from autoresearch import tabular_quality_adapter as tabular, synthetic_time_binding, synthetic_time_quality_core
from autoresearch.contracts import ResearchError, canonical, fingerprint
from autoresearch.local_workbench import LocalWorkbench
from autoresearch.project_controller import ProjectController
from autoresearch.research_project import ResearchProject
import test_strict_quality_primary as old_fixture
import test_synthetic_time_registration as time_fixture


class SyntheticTimeQualityPrimaryTests(unittest.TestCase):
    def stage(self, *, unknown=False):
        helper = time_fixture.SyntheticTimeRegistrationTests(methodName='runTest')
        self.addCleanup(helper.doCleanups)
        manager, project, report, time_body = helper.stage(quality=not unknown)
        if unknown:
            context = ProjectController(project.root).selection_context()
            candidate = next(c for c in context['candidates'] if c['method_id'] == tabular.TOOL_ID)
            quality_body = {'request_id':'quality-registration', 'project_id':time_body['project_id'],
                'expected_state_version':project.status()['state_version'], 'controller_request_id':'quality-future',
                'candidate_id':candidate['id'], 'conditions':{'schema_version':'tabular-quality-conditions-v1',
                    'conditions':[{'field':'group.min_group_size', 'operator':'eq', 'value':0}]}}
            quality = manager.register_tabular_quality_conditions(quality_body)['registration']
            time_body['registration_sha256'] = quality['registration_sha256']
            time_body['expected_state_version'] = project.status()['state_version']
        time_record = manager.register_synthetic_time_report(time_body)['registration']
        body = {'request_id':'quality-future', 'project_id':time_body['project_id'],
                'expected_state_version':project.status()['state_version'],
                'registration_request_id':time_body['registration_request_id'],
                'registration_sha256':time_body['registration_sha256'],
                'time_registration_request_id':time_record['request_id'],
                'time_registration_sha256':time_record['record_sha256'],
                'reason':'Explicit quality action on the fixed synthetic clock only'}
        return manager, project, report, time_body, time_record, body

    def no_external(self, stack):
        for name in ('socket.socket.connect','socket.create_connection','urllib.request.urlopen','subprocess.Popen'):
            stack.enter_context(patch(name, side_effect=AssertionError('external call forbidden')))
        stack.enter_context(patch.object(ResearchProject, 'read_evidence', side_effect=AssertionError('evidence forbidden')))

    @staticmethod
    def db_state(project):
        with sqlite3.connect(project.db.resolve().as_uri() + '?mode=ro&immutable=1', uri=True) as con:
            return (con.execute('SELECT record FROM project WHERE id=1').fetchone()[0],
                    con.execute('SELECT * FROM actions ORDER BY request_id').fetchall(),
                    con.execute('SELECT * FROM replays ORDER BY request_id').fetchall(),
                    con.execute('SELECT * FROM quality_manager_claims ORDER BY kind,request_id').fetchall())

    def test_completed_original_id_resume_and_reader(self):
        with ExitStack() as stack:
            self.no_external(stack)
            manager, project, _, _, _, body = self.stage()
            before = project.status()['budget']
            result = manager.advance_synthetic_time_quality_primary(body)
            self.assertEqual(result['status'], 'completed')
            state = project.status()
            self.assertEqual(state['budget']['local_tool_calls_used'], before['local_tool_calls_used'] + 1)
            self.assertEqual(state['budget']['local_tool_calls_reserved'], 0)
            self.assertEqual((state['budget']['new_model_requests'],state['budget']['new_fits'],state['budget']['evidence_reads_used']), (0,0,0))
            self.assertEqual(len(state['actions']), 1)
            parent = next(p for p in state['controller_requests'] if p['request_id'] == body['request_id'])
            self.assertEqual(parent['tabular_quality_primary']['schema_version'], 'tabular-quality-primary-binding-v2')
            self.assertEqual(parent['request']['command'], 'controller.advance_selection')
            feedback = project.read_tabular_quality_feedback(request_id=body['registration_request_id'])
            self.assertEqual(feedback['outcome'], 'condition_met')
            with project._writer():
                locked = project.read_tabular_quality_feedback(request_id=body['registration_request_id'])
            self.assertEqual(locked['outcome'], 'condition_met')
            with sqlite3.connect(project.db) as con:
                kinds = {row[0] for row in con.execute('SELECT kind FROM quality_manager_claims')}
            self.assertTrue({'registration','synthetic_time_registration','synthetic_time_quality_parent','synthetic_time_quality_child'} <= kinds)
            with patch.object(ProjectController, '_dispatch', side_effect=AssertionError('no redispatch')), \
                 patch.object(ResearchProject, 'step', side_effect=AssertionError('no action')):
                replay = manager.resume_synthetic_time_quality_primary({'request_id':body['request_id'], 'project_id':body['project_id']})
            self.assertTrue(replay['replayed'])
            self.assertEqual(project.status(), state)

    def test_completed_action_with_legitimate_unknown_not_replayed(self):
        with ExitStack() as stack:
            self.no_external(stack)
            manager, project, _, _, _, body = self.stage(unknown=True)
            self.assertEqual(manager.advance_synthetic_time_quality_primary(body)['status'], 'completed')
            state = project.status(); self.assertEqual(state['budget']['local_tool_calls_used'], 1)
            feedback = project.read_tabular_quality_feedback(request_id=body['registration_request_id'])
            self.assertEqual((feedback['outcome'],feedback['unknown_reason']), ('unknown','quality_values_unknown'))
            with patch.object(ProjectController, '_dispatch', side_effect=AssertionError('no redispatch')), \
                 patch.object(ResearchProject, 'step', side_effect=AssertionError('no action')):
                self.assertTrue(manager.resume_synthetic_time_quality_primary({'request_id':body['request_id'],
                                                                              'project_id':body['project_id']})['replayed'])
            self.assertEqual(project.status(), state)

    def test_missing_intent_cannot_resume_or_execute(self):
        with ExitStack() as stack:
            self.no_external(stack)
            manager, project, _, _, _, body = self.stage(); before = self.db_state(project)
            with patch.object(ProjectController, '_dispatch', side_effect=AssertionError('no dispatch')):
                with self.assertRaises(ResearchError):
                    manager.resume_synthetic_time_quality_primary({'request_id':body['request_id'],'project_id':body['project_id']})
            self.assertEqual(self.db_state(project), before)

    def test_manager_intent_without_parent_stops_original_resume(self):
        with ExitStack() as stack:
            self.no_external(stack)
            manager, project, _, _, _, body = self.stage(); before = self.db_state(project)
            with patch.object(ProjectController, '_advance_synthetic_time_quality_primary', side_effect=RuntimeError('before parent')):
                with self.assertRaises(RuntimeError): manager.advance_synthetic_time_quality_primary(body)
            self.assertEqual(self.db_state(project), before)
            with patch.object(ProjectController, '_dispatch', side_effect=AssertionError('no redispatch')):
                with self.assertRaises(ResearchError):
                    manager.resume_synthetic_time_quality_primary({'request_id':body['request_id'],'project_id':body['project_id']})
            self.assertEqual(self.db_state(project), before)

    def test_completed_core_before_manager_receipt_only_reconciles(self):
        with ExitStack() as stack:
            self.no_external(stack)
            manager, project, _, _, _, body = self.stage(); save = manager._save
            def lose_receipt(con, request_id, record):
                if request_id == body['request_id'] and record.get('status') == 'completed':
                    raise RuntimeError('before manager receipt')
                return save(con, request_id, record)
            with patch.object(manager, '_save', side_effect=lose_receipt):
                with self.assertRaises(RuntimeError): manager.advance_synthetic_time_quality_primary(body)
            saved = self.db_state(project); state = project.status()
            parent = next(p for p in state['controller_requests'] if p['request_id'] == body['request_id'])
            self.assertEqual(parent['status'], 'completed')
            self.assertEqual(state['budget']['local_tool_calls_used'], 1)
            with patch.object(ProjectController, '_dispatch', side_effect=AssertionError('no redispatch')), \
                 patch.object(ResearchProject, 'step', side_effect=AssertionError('no action')):
                result = manager.resume_synthetic_time_quality_primary({'request_id':body['request_id'],'project_id':body['project_id']})
            self.assertTrue(result['replayed'])
            self.assertEqual(self.db_state(project), saved)

    def test_wrong_authorization_bindings_fail_before_action(self):
        for field, value in (('request_id','other-future'), ('registration_sha256','0'*64),
                             ('time_registration_sha256','0'*64), ('time_registration_request_id','missing'), ('reason','')):
            with self.subTest(field=field), ExitStack() as stack:
                self.no_external(stack)
                manager, project, _, _, _, body = self.stage(); changed = copy.deepcopy(body); changed[field] = value
                before = self.db_state(project)
                with patch.object(ProjectController, '_dispatch', side_effect=AssertionError('no dispatch')):
                    with self.assertRaises(ResearchError): manager.advance_synthetic_time_quality_primary(changed)
                self.assertEqual(self.db_state(project), before)

    def test_each_time_report_original_drift_blocks_action(self):
        for filename in ('claim.json','source.csv','spec.json','source.json','report.json','receipt.json'):
            with self.subTest(filename=filename), ExitStack() as stack:
                self.no_external(stack)
                manager, project, report, _, _, body = self.stage()
                target = report/filename; target.write_bytes(target.read_bytes() + b' ')
                before = self.db_state(project)
                with patch.object(ProjectController, '_dispatch', side_effect=AssertionError('no dispatch')):
                    with self.assertRaises((ResearchError, ValueError, OSError)):
                        manager.advance_synthetic_time_quality_primary(body)
                self.assertEqual(self.db_state(project), before)

    def test_report_producer_code_drift_blocks_action_without_editing_source(self):
        for name in ('prepare_synthetic_time_fixture.py','synthetic_time_report.py'):
            with self.subTest(producer=name), ExitStack() as stack:
                self.no_external(stack)
                manager, project, _, _, _, body = self.stage()
                before = self.db_state(project); read = synthetic_time_binding._source_bytes
                def altered(path, maximum):
                    raw = read(path, maximum)
                    return raw + b'\n# synthetic producer drift' if str(path).endswith('/' + name) else raw
                with patch.object(synthetic_time_binding, '_source_bytes', side_effect=altered), \
                     patch.object(ProjectController, '_dispatch', side_effect=AssertionError('no dispatch')):
                    with self.assertRaises(ResearchError): manager.advance_synthetic_time_quality_primary(body)
                self.assertEqual(self.db_state(project), before)

    def test_original_s084_and_s135_claim_loss_blocks_action(self):
        for kind in ('registration','synthetic_time_registration'):
            with self.subTest(kind=kind), ExitStack() as stack:
                self.no_external(stack)
                manager, project, _, _, _, body = self.stage()
                with sqlite3.connect(project.db) as con:
                    cur = con.execute('DELETE FROM quality_manager_claims WHERE kind=?', (kind,))
                    self.assertEqual(cur.rowcount, 1)
                before = self.db_state(project)
                with patch.object(ProjectController, '_dispatch', side_effect=AssertionError('no dispatch')):
                    with self.assertRaises(ResearchError): manager.advance_synthetic_time_quality_primary(body)
                self.assertEqual(self.db_state(project), before)

    def test_parent_and_child_orphan_replays_never_dispatch(self):
        for part in ('parent','child'):
            for direction in ('request','target'):
                with self.subTest(part=part,direction=direction), ExitStack() as stack:
                    self.no_external(stack)
                    manager, project, _, _, _, body = self.stage()
                    ident = body['request_id'] if part == 'parent' else 'controller-child-' + fingerprint(
                        {'project_id':body['project_id'], 'request_id':body['request_id']})[:32]
                    alias = 'synthetic-orphan'
                    with sqlite3.connect(project.db) as con:
                        con.execute('INSERT INTO replays VALUES (?,?)',
                                    (ident,alias) if direction == 'request' else (alias,ident))
                    before = self.db_state(project)
                    with patch.object(ProjectController, '_dispatch', side_effect=AssertionError('no dispatch')):
                        with self.assertRaises(ResearchError): manager.advance_synthetic_time_quality_primary(body)
                    self.assertEqual(self.db_state(project), before)

    def test_interrupted_parent_stops_resume_and_old_entrypoints(self):
        with ExitStack() as stack:
            self.no_external(stack)
            manager, project, _, _, _, body = self.stage()
            with patch.object(ProjectController, '_dispatch', side_effect=RuntimeError('synthetic interruption')):
                with self.assertRaises(RuntimeError): manager.advance_synthetic_time_quality_primary(body)
            state = project.status(); parent = next(p for p in state['controller_requests'] if p['request_id'] == body['request_id'])
            self.assertEqual(parent['status'], 'prepared')
            before = self.db_state(project)
            with patch.object(ProjectController, '_dispatch', side_effect=AssertionError('no redispatch')):
                with self.assertRaises(ResearchError):
                    manager.resume_synthetic_time_quality_primary({'request_id':body['request_id'],'project_id':body['project_id']})
                with self.assertRaises(ResearchError):
                    ProjectController(project.root).advance_selection(request_id=body['request_id'], proposal=parent['request']['proposal'],
                                                                     expected_state_version=parent['request']['expected_state_version'])
                with self.assertRaises(ResearchError): project.step(request_id=parent['child_request_id'], method_id=tabular.TOOL_ID)
            self.assertEqual(self.db_state(project), before)

    def test_direct_old_parent_winner_is_never_adopted(self):
        with ExitStack() as stack:
            self.no_external(stack)
            manager, project, _, _, _, body = self.stage()
            context = ProjectController(project.root).selection_context()
            candidate = next(c for c in context['candidates'] if c['method_id'] == tabular.TOOL_ID)
            proposal = {'schema_version':'project-selection-proposal-v1', 'context_sha256':context['context_sha256'],
                        'provider':{'kind':'human','label':'synthetic direct competition'},
                        'choice':{'kind':'execute','candidate_id':candidate['id']},
                        'rationale':'Only artificial fixture.', 'evidence_citation_ids':[]}
            ProjectController(project.root).advance_selection(request_id=body['request_id'], proposal=proposal,
                                                               expected_state_version=context['state_version'])
            before = self.db_state(project); self.assertEqual(project.status()['budget']['local_tool_calls_used'], 1)
            with patch.object(ProjectController, '_dispatch', side_effect=AssertionError('no redispatch')):
                with self.assertRaises(ResearchError): manager.advance_synthetic_time_quality_primary(body)
            self.assertEqual(self.db_state(project), before)

    def test_completed_child_with_unfinished_parent_stops_without_replay(self):
        with ExitStack() as stack:
            self.no_external(stack)
            manager, project, _, _, _, body = self.stage()
            with patch.object(ProjectController, '_finish', side_effect=RuntimeError('after child before parent finish')):
                with self.assertRaises(RuntimeError): manager.advance_synthetic_time_quality_primary(body)
            state = project.status(); self.assertEqual(state['budget']['local_tool_calls_used'], 1)
            parent = next(p for p in state['controller_requests'] if p['request_id'] == body['request_id'])
            child = next(a for a in state['actions'] if a['request_id'] == parent['child_request_id'])
            self.assertEqual((parent['status'],child['status']), ('prepared','completed'))
            before = self.db_state(project)
            with patch.object(ProjectController, '_dispatch', side_effect=AssertionError('no redispatch')), \
                 patch.object(ResearchProject, '_recover', side_effect=AssertionError('no recovery')):
                with self.assertRaises(ResearchError):
                    manager.resume_synthetic_time_quality_primary({'request_id':body['request_id'],'project_id':body['project_id']})
                with self.assertRaises(ResearchError): project.resume(request_id=child['request_id'])
            self.assertEqual(self.db_state(project), before)

    def test_report_or_source_drift_at_three_acceptance_windows(self):
        for phase in ('manager_intent','parent_commit','child_commit'):
          for asset in ('report','source'):
            with self.subTest(phase=phase, asset=asset), ExitStack() as stack:
                self.no_external(stack)
                manager, project, report, _, _, body = self.stage()
                touched = []
                def corrupt():
                    path = report/'report.json' if asset == 'report' else project.root/'source.json'
                    path.write_bytes(path.read_bytes() + b' '); touched.append(True)
                if phase == 'manager_intent':
                    original = ProjectController._advance_synthetic_time_quality_primary
                    def before_parent(controller, *args, **kwargs):
                        corrupt()
                        return original(controller, *args, **kwargs)
                    stack.enter_context(patch.object(ProjectController, '_advance_synthetic_time_quality_primary',
                                                     autospec=True, side_effect=before_parent))
                elif phase == 'parent_commit':
                    original = ProjectController._dispatch
                    def before_child(controller, *args, **kwargs):
                        corrupt()
                        return original(controller, *args, **kwargs)
                    stack.enter_context(patch.object(ProjectController, '_dispatch', autospec=True, side_effect=before_child))
                else:
                    original = synthetic_time_quality_core.verify_locked
                    def after_child(proj, state, meta):
                        if any(row.get('status') == 'running' for row in state.get('actions', [])) and not touched:
                            corrupt()
                        return original(proj, state, meta)
                    stack.enter_context(patch.object(synthetic_time_quality_core, 'verify_locked', side_effect=after_child))
                calls = []
                def forbidden_adapter(*args, **kwargs):
                    calls.append(True); raise AssertionError('adapter must not start')
                stack.enter_context(patch.object(tabular, 'execute', side_effect=forbidden_adapter))
                with self.assertRaises(ResearchError): manager.advance_synthetic_time_quality_primary(body)
                self.assertEqual(touched, [True]); self.assertEqual(calls, [])
                state = project.status(); budget = state['budget']
                self.assertEqual(budget['local_tool_calls_used'], 0)
                if phase == 'child_commit':
                    self.assertEqual(budget['local_tool_calls_reserved'], 1)
                    self.assertEqual([a['status'] for a in state['actions']], ['running'])
                    with sqlite3.connect(project.db) as con:
                        self.assertEqual(con.execute("SELECT count(*) FROM quality_manager_claims WHERE kind='synthetic_time_quality_child'").fetchone()[0], 1)
                else:
                    self.assertEqual(budget['local_tool_calls_reserved'], 0)
                    self.assertEqual(state['actions'], [])
                before = self.db_state(project)
                with self.assertRaises(ResearchError):
                    manager.resume_synthetic_time_quality_primary({'request_id':body['request_id'],'project_id':body['project_id']})
                self.assertEqual(self.db_state(project), before)

    def test_public_unlocked_reader_stops_on_originals_drift_during_read(self):
        for mode in ('project','registration-claim','time-claim','report','source'):
            with self.subTest(mode=mode), ExitStack() as stack:
                self.no_external(stack)
                manager, project, report, _, _, body = self.stage()
                manager.advance_synthetic_time_quality_primary(body)
                original = synthetic_time_quality_core._verify_report_observed; touched = []
                def drift(proj, state, directory):
                    value = original(proj, state, directory)
                    if not touched:
                        touched.append(True)
                        if mode in ('report','source'):
                            path = report/'report.json' if mode == 'report' else project.root/'source.json'
                            path.write_bytes(path.read_bytes() + b' ')
                        else:
                            with sqlite3.connect(project.db) as con:
                                if mode == 'project':
                                    raw = con.execute('SELECT record FROM project WHERE id=1').fetchone()[0]
                                    stored = json.loads(raw); stored['state_version'] += 1
                                    con.execute('UPDATE project SET record=? WHERE id=1',(canonical(stored),))
                                else:
                                    kind = 'registration' if mode == 'registration-claim' else 'synthetic_time_registration'
                                    cur = con.execute('UPDATE quality_manager_claims SET core_sha256=? WHERE kind=?',('0'*64,kind))
                                    self.assertEqual(cur.rowcount, 1)
                    return value
                with patch.object(synthetic_time_quality_core, '_verify_report_observed', side_effect=drift), \
                     patch.object(ProjectController, '_dispatch', side_effect=AssertionError('no dispatch')), \
                     patch.object(ResearchProject, 'step', side_effect=AssertionError('no action')):
                    try:
                        result = project.read_tabular_quality_feedback(request_id=body['registration_request_id'])
                    except ResearchError:
                        pass
                    else:
                        self.assertEqual(result['outcome'], 'unknown')
                self.assertEqual(touched, [True])
                with sqlite3.connect(project.db) as con:
                    rows = [json.loads(row[0]) for row in con.execute('SELECT record FROM actions')]
                self.assertEqual(len(rows), 1)
                self.assertEqual(rows[0]['status'], 'completed')

    def test_claim_loss_after_action_prevents_resume(self):
        for kind in ('synthetic_time_quality_parent','synthetic_time_quality_child','synthetic_time_registration','registration'):
            with self.subTest(kind=kind), ExitStack() as stack:
                self.no_external(stack)
                manager, project, _, _, _, body = self.stage()
                manager.advance_synthetic_time_quality_primary(body)
                with sqlite3.connect(project.db) as con:
                    cur = con.execute('DELETE FROM quality_manager_claims WHERE kind=?',(kind,))
                    self.assertEqual(cur.rowcount, 1)
                before = self.db_state(project)
                with patch.object(ProjectController, '_dispatch', side_effect=AssertionError('no redispatch')):
                    with self.assertRaises(ResearchError):
                        manager.resume_synthetic_time_quality_primary({'request_id':body['request_id'],'project_id':body['project_id']})
                self.assertEqual(self.db_state(project), before)

    def test_original_four_row_fixture_does_not_bypass_time_registration(self):
        helper = old_fixture.StrictQualityPrimaryTests(methodName='runTest'); self.addCleanup(helper.doCleanups)
        with ExitStack() as stack:
            self.no_external(stack)
            _, manager, _, body = helper.stage()
            body.update(time_registration_request_id='not-existing', time_registration_sha256='0'*64)
            with patch.object(ProjectController, '_dispatch', side_effect=AssertionError('no dispatch')):
                with self.assertRaises(ResearchError): manager.advance_synthetic_time_quality_primary(body)


if __name__ == '__main__':
    unittest.main()
