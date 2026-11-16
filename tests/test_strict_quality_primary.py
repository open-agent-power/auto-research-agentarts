"""Strict quality-primary ownership on one fixed artificial packet only."""
import copy
import hashlib
import json
import sqlite3
import unittest
from contextlib import ExitStack
from unittest.mock import patch

from autoresearch import tabular_quality_adapter as tabular
from autoresearch.contracts import ResearchError, canonical, fingerprint
from autoresearch.project_controller import ProjectController
from autoresearch.research_project import ResearchProject
import test_tabular_quality_workbench as quality_fixture
import test_numeric_association as numeric_fixture

PACKET_SHA = 'dd88f02f49fd94c830ac3ef12ed307f437d52cc12c9b1b298a9585d8082ac799'
SNAPSHOT_SHA = 'b4097316500039827e13d11c86691eaef349da52558828600157d3df63f84c29'
CSV_SHA = '818e6a04275b98acdc370992df05508e5ee3f0c6b9330a2839eeb09159c8cbbe'
SPEC_SHA = '5e81dbb327ce24784c9a29309e4d145d013366554bfb6b5910f434bbcd62dbd4'


class StrictQualityPrimaryTests(unittest.TestCase):
    def stage(self, *, fixed=True, conditions=None):
        helper = quality_fixture.QualityWorkbenchTests(methodName='runTest')
        self.addCleanup(helper.doCleanups)
        fixture, manager, registration_body = helper.stage()
        raw = (fixture.project.root / 'source.json').read_bytes()
        packet = tabular.load_source(raw)
        if fixed:
            self.assertEqual(hashlib.sha256(raw).hexdigest(), PACKET_SHA)
            self.assertEqual(packet['snapshot_sha256'], SNAPSHOT_SHA)
            self.assertEqual(packet['source']['sha256'], CSV_SHA)
            self.assertEqual(packet['spec_source']['sha256'], SPEC_SHA)
        else:
            self.assertNotEqual(hashlib.sha256(raw).hexdigest(), PACKET_SHA)
        if conditions is not None:
            registration_body['conditions'] = conditions
        registration = manager.register_tabular_quality_conditions(registration_body)['registration']
        state = fixture.project.status()
        body = {'request_id':registration['controller_request_id'], 'project_id':state['id'],
                'expected_state_version':state['state_version'], 'registration_request_id':registration['request_id'],
                'registration_sha256':registration['registration_sha256'], 'reason':'Explicit artificial quality action'}
        return fixture, manager, registration, body

    def forbid_external(self, stack):
        stack.enter_context(patch('socket.socket.connect', side_effect=AssertionError('network forbidden')))
        stack.enter_context(patch('urllib.request.urlopen', side_effect=AssertionError('network forbidden')))
        stack.enter_context(patch('subprocess.Popen', side_effect=AssertionError('subprocess forbidden')))
        stack.enter_context(patch.object(ResearchProject, 'read_evidence', side_effect=AssertionError('evidence forbidden')))

    def test_first_completion_resume_and_reader_compatibility(self):
        f, manager, reg, body = self.stage()
        before = f.project.status()['budget']
        with ExitStack() as stack:
            self.forbid_external(stack)
            result = manager.advance_tabular_quality_primary(body)
        self.assertEqual(result['status'], 'completed')
        state = f.project.status()
        self.assertEqual(state['budget']['local_tool_calls_used'], before['local_tool_calls_used'] + 1)
        self.assertEqual(state['budget']['local_tool_calls_reserved'], 0)
        self.assertEqual((state['budget']['new_model_requests'], state['budget']['new_fits'],
                          state['budget']['evidence_reads_used']), (0, 0, 0))
        feedback = f.project.read_tabular_quality_feedback(request_id=reg['request_id'])
        self.assertEqual(feedback['outcome'], 'condition_met')
        self.assertIsNotNone(feedback['action_id'])
        with patch.object(ProjectController, '_dispatch', side_effect=AssertionError('no redispatch')), \
             patch.object(ResearchProject, 'step', side_effect=AssertionError('no second tool')):
            replay = manager.resume_tabular_quality_primary({'request_id':body['request_id'], 'project_id':body['project_id']})
        self.assertTrue(replay['replayed'])
        self.assertEqual(f.project.status(), state)
        changed = copy.deepcopy(body); changed['reason'] += ' changed'
        with self.assertRaises(ResearchError):
            manager.advance_tabular_quality_primary(changed)
        self.assertEqual(f.project.status(), state)

    def test_resume_never_creates_missing_intent(self):
        f, manager, _, body = self.stage()
        before = f.project.status()
        with patch.object(ProjectController, '_dispatch', side_effect=AssertionError('no dispatch')):
            with self.assertRaises(ResearchError):
                manager.resume_tabular_quality_primary({'request_id':body['request_id'], 'project_id':body['project_id']})
        self.assertEqual(f.project.status(), before)

    def test_nonterminal_original_parent_cannot_recover_or_dispatch(self):
        f, manager, _, body = self.stage()
        with patch.object(ProjectController, '_dispatch', side_effect=RuntimeError('synthetic interruption')):
            with self.assertRaises(RuntimeError): manager.advance_tabular_quality_primary(body)
        before = f.project.status()
        self.assertEqual(before['budget']['local_tool_calls_used'], 0)
        parent = next(p for p in before['controller_requests'] if p['request_id'] == body['request_id'])
        self.assertEqual(parent['status'], 'prepared')
        with patch.object(ProjectController, '_dispatch', side_effect=AssertionError('no redispatch')):
            with self.assertRaises(ResearchError):
                manager.resume_tabular_quality_primary({'request_id':body['request_id'], 'project_id':body['project_id']})
            with self.assertRaises(ResearchError):
                manager.advance_tabular_quality_primary(body)
            with self.assertRaises(ResearchError):
                f.controller.advance_selection(request_id=body['request_id'],
                    proposal=parent['request']['proposal'], expected_state_version=parent['request']['expected_state_version'])
            with self.assertRaises(ResearchError):
                f.project.step(request_id=parent['child_request_id'], method_id=tabular.TOOL_ID,
                               expected_state_version=before['state_version'])
        self.assertEqual(f.project.status(), before)

    def test_direct_original_parent_preoccupation_is_not_adopted(self):
        f, manager, _, body = self.stage()
        f.execute(target=body['request_id'])
        before = f.project.status()
        with patch.object(ProjectController, '_dispatch', side_effect=AssertionError('no redispatch')):
            with self.assertRaises(ResearchError): manager.advance_tabular_quality_primary(body)
        self.assertEqual(f.project.status(), before)
        self.assertEqual(before['budget']['local_tool_calls_used'], 1)

    def test_orphan_replay_identifiers_block_first_acceptance(self):
        for origin in ('parent', 'child'):
            for direction in ('key', 'target'):
                with self.subTest(origin=origin, direction=direction):
                    f, manager, _, body = self.stage()
                    state = f.project.status()
                    ident = body['request_id'] if origin == 'parent' else 'controller-child-' + fingerprint(
                        {'project_id':state['id'], 'request_id':body['request_id']})[:32]
                    row = (ident, 'missing-action') if direction == 'key' else ('orphan-alias', ident)
                    with sqlite3.connect(f.project.db) as con:
                        con.execute('INSERT INTO replays VALUES (?,?)', row)
                    before = f.project.status()
                    with patch.object(ProjectController, '_dispatch', side_effect=AssertionError('no dispatch')):
                        with self.assertRaises(ResearchError): manager.advance_tabular_quality_primary(body)
                    self.assertEqual(f.project.status(), before)
                    self.assertEqual(before['budget']['local_tool_calls_used'], 0)

    def test_source_drift_rejected_without_tool(self):
        f, manager, _, body = self.stage()
        path = f.project.root / 'source.json'; path.write_bytes(path.read_bytes() + b' ')
        before = f.project.status()
        with patch.object(ProjectController, '_dispatch', side_effect=AssertionError('no dispatch')):
            with self.assertRaises(ResearchError): manager.advance_tabular_quality_primary(body)
        self.assertEqual(f.project.status(), before)
        self.assertEqual(before['budget']['local_tool_calls_used'], 0)

    def test_unlisted_artificial_packet_cannot_be_admitted_by_its_label(self):
        generator = numeric_fixture.NumericAssociationTests(methodName='runTest')
        self.addCleanup(generator.doCleanups)
        other = generator.payload('group,x,outcome\na,1,2\na,2,4\nb,3,6\nb,4,999\n')
        with patch.object(numeric_fixture.NumericAssociationTests, 'payload', return_value=other):
            f, manager, _, body = self.stage(fixed=False)
        before = f.project.status()
        with patch.object(ProjectController, '_dispatch', side_effect=AssertionError('no dispatch')):
            with self.assertRaises(ResearchError): manager.advance_tabular_quality_primary(body)
        self.assertEqual(f.project.status(), before)
        self.assertEqual(before['budget']['local_tool_calls_used'], 0)

    def test_core_completed_before_manager_receipt_can_only_reconcile(self):
        f, manager, _, body = self.stage()
        with patch.object(manager, '_inspect_quality_primary', side_effect=RuntimeError('before manager receipt')):
            with self.assertRaises(RuntimeError): manager.advance_tabular_quality_primary(body)
        state = f.project.status()
        self.assertEqual(state['budget']['local_tool_calls_used'], 1)
        self.assertEqual(next(p for p in state['controller_requests'] if p['request_id'] == body['request_id'])['status'], 'completed')
        with patch.object(ProjectController, '_dispatch', side_effect=AssertionError('no redispatch')), \
             patch.object(ResearchProject, 'step', side_effect=AssertionError('no extra action')):
            replay = manager.resume_tabular_quality_primary({'request_id':body['request_id'], 'project_id':body['project_id']})
        self.assertTrue(replay['replayed'])
        self.assertEqual(f.project.status(), state)

    def test_missing_parent_or_child_claim_stops_resume_and_reader(self):
        for kind in ('quality_primary_parent', 'quality_primary_child'):
            with self.subTest(kind=kind):
                f, manager, reg, body = self.stage()
                manager.advance_tabular_quality_primary(body)
                before = f.project.status()
                with sqlite3.connect(f.project.db) as con:
                    cur = con.execute('DELETE FROM quality_manager_claims WHERE kind=?', (kind,))
                    self.assertEqual(cur.rowcount, 1)
                def persisted():
                    with sqlite3.connect(f.project.db.resolve().as_uri() + '?mode=ro&immutable=1', uri=True) as con:
                        return (con.execute('SELECT record FROM project WHERE id=1').fetchone()[0],
                                con.execute('SELECT * FROM actions ORDER BY request_id').fetchall(),
                                con.execute('SELECT * FROM replays ORDER BY request_id').fetchall(),
                                con.execute('SELECT * FROM quality_manager_claims ORDER BY kind,request_id').fetchall())
                damaged = persisted()
                self.assertEqual(json.loads(damaged[0])['budget']['local_tool_call_limit'],
                                 before['budget']['local_tool_call_limit'])
                action_records = [json.loads(row[-1]) for row in damaged[1]]
                self.assertEqual(sum(a['status'] in ('completed', 'failed') for a in action_records),
                                 before['budget']['local_tool_calls_used'])
                with patch.object(ProjectController, '_dispatch', side_effect=AssertionError('no redispatch')), \
                     patch.object(ResearchProject, 'step', side_effect=AssertionError('no extra action')):
                    with self.assertRaises(ResearchError):
                        f.project.status()
                    with self.assertRaises(ResearchError):
                        manager.resume_tabular_quality_primary({'request_id':body['request_id'], 'project_id':body['project_id']})
                    try:
                        result = f.project.read_tabular_quality_feedback(request_id=reg['request_id'])
                    except ResearchError:
                        pass
                    else:
                        self.assertEqual(result['outcome'], 'unknown')
                self.assertEqual(persisted(), damaged)

    def test_future_request_id_preclaimed_by_another_manager_command(self):
        f, manager, _, body = self.stage()
        manager.select({'request_id':body['request_id'], 'project_id':body['project_id']})
        before = f.project.status()
        with patch.object(ProjectController, '_dispatch', side_effect=AssertionError('no dispatch')):
            with self.assertRaises(ResearchError): manager.advance_tabular_quality_primary(body)
        self.assertEqual(f.project.status(), before)
        self.assertEqual(before['budget']['local_tool_calls_used'], 0)

    def test_completed_quality_can_report_legitimate_unknown_without_repeat(self):
        # The immutable fixture declares no key columns. Its quality action can
        # complete normally, while a valid condition on key counts is unknown.
        conditions = {'schema_version':'tabular-quality-conditions-v1', 'conditions':[
            {'field':'key.incomplete_rows', 'operator':'eq', 'value':0}]}
        f, manager, reg, body = self.stage(conditions=conditions)
        result = manager.advance_tabular_quality_primary(body)
        self.assertEqual(result['status'], 'completed')
        state = f.project.status()
        self.assertEqual(state['budget']['local_tool_calls_used'], 1)
        feedback = f.project.read_tabular_quality_feedback(request_id=reg['request_id'])
        self.assertEqual(feedback['outcome'], 'unknown')
        self.assertEqual(feedback['unknown_reason'], 'quality_values_unknown')
        with patch.object(ProjectController, '_dispatch', side_effect=AssertionError('no redispatch')), \
             patch.object(ResearchProject, 'step', side_effect=AssertionError('no extra action')):
            replay = manager.resume_tabular_quality_primary({'request_id':body['request_id'], 'project_id':body['project_id']})
        self.assertTrue(replay['replayed'])
        self.assertEqual(f.project.status(), state)

    def test_marker_removed_with_claims_present_cannot_bypass_old_entrypoints(self):
        f, manager, _, body = self.stage()
        manager.advance_tabular_quality_primary(body)
        state = f.project.status()
        parent = next(p for p in state['controller_requests'] if p['request_id'] == body['request_id'])
        self.assertIn('tabular_quality_primary', parent)
        with sqlite3.connect(f.project.db) as con:
            kinds = {row[0] for row in con.execute('SELECT kind FROM quality_manager_claims')}
            self.assertTrue({'quality_primary_parent', 'quality_primary_child'} <= kinds)
            project = json.loads(con.execute('SELECT record FROM project WHERE id=1').fetchone()[0])
            saved_parent = next(p for p in project['controller_requests'] if p['request_id'] == body['request_id'])
            del saved_parent['tabular_quality_primary']
            con.execute('UPDATE project SET record=? WHERE id=1', (canonical(project),))
        def persisted():
            with sqlite3.connect(f.project.db) as con:
                return (con.execute('SELECT record FROM project WHERE id=1').fetchone()[0],
                        con.execute('SELECT * FROM actions ORDER BY request_id').fetchall(),
                        con.execute('SELECT * FROM replays ORDER BY request_id').fetchall(),
                        con.execute('SELECT * FROM quality_manager_claims ORDER BY kind,request_id').fetchall())
        before = persisted()
        with patch.object(ProjectController, '_dispatch', side_effect=AssertionError('no redispatch')), \
             patch.object(ResearchProject, '_recover', side_effect=AssertionError('no recovery')):
            with self.assertRaises(ResearchError):
                f.controller.advance_selection(request_id=body['request_id'],
                    proposal=parent['request']['proposal'], expected_state_version=parent['request']['expected_state_version'])
            with self.assertRaises(ResearchError):
                f.project.step(request_id=parent['child_request_id'], method_id=tabular.TOOL_ID,
                               expected_state_version=state['state_version'])
            with self.assertRaises(ResearchError):
                f.project.resume(request_id=parent['child_request_id'])
            with self.assertRaises(ResearchError):
                manager.resume_tabular_quality_primary({'request_id':body['request_id'], 'project_id':body['project_id']})
        self.assertEqual(persisted(), before)


if __name__ == '__main__':
    unittest.main()
