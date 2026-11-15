"""Engineering-only conditional wait capture and offline consumption."""
import base64
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from autoresearch import project_experience_dispatch as dispatch, retrieval_holdout, staged_relevance_adapter as staged
from autoresearch import staged_wait_experience as waiting
from autoresearch import project_report, research_plan_proposal
from autoresearch.contracts import ResearchError, canonical, fingerprint
from autoresearch.host_model_selection import HostModelSelection
from autoresearch.local_workbench import LocalWorkbench
from autoresearch.project_controller import ProjectController
from autoresearch.research_project import ResearchProject
import test_conditional_staged_continuation as conditional_fixtures
import test_staged_project_experience as experience_fixtures
import test_retrieval_holdout as holdout_fixtures
import test_local_workbench_http as http_fixtures


class StagedWaitExperienceTests(unittest.TestCase):
    fixture = conditional_fixtures.ConditionalStagedContinuationTests.fixture
    serve = http_fixtures.LocalWorkbenchHTTPTests.serve
    request = http_fixtures.LocalWorkbenchHTTPTests.request
    session = http_fixtures.LocalWorkbenchHTTPTests.session

    def source(self, sign=None, *, execute=True, met_audit=True):
        manager, project, body = self.fixture(sign, execute_primary=execute, met_audit=met_audit)
        before = project.status()
        result = manager.continue_staged(body)
        self.assertEqual(result['phase'], 'waiting')
        self.assertEqual(project.status(), before)
        return manager, project, body

    def memory(self):
        return waiting.StagedWaitExperienceMemory(Path(self.enterContext(tempfile.TemporaryDirectory())) / 'memory')

    def case(self, memory, imported):
        entry = memory.recall(imported['scope'])['entries'][0]['record']
        return memory.export_case(imported['scope'], entry['id'], case_id='wait-case', version=1,
                                  method_card=experience_fixtures.StagedExperienceTests.card(), limitations=['Synthetic case only.'])

    def test_known_negative_zero_met_and_unknown_are_captured_without_actions(self):
        for sign, execute, met_audit, outcome in [('negative', True, True, 'condition_not_met'),
                                                   (None, True, True, 'condition_not_met'),
                                                   ('positive', True, False, 'condition_met'),
                                                   (None, False, True, 'unknown')]:
            with self.subTest(sign=sign, execute=execute):
                manager, project, body = self.source(sign, execute=execute, met_audit=met_audit)
                before = project.status()
                original_open = Path.open
                def no_private(path, *args, **kwargs):
                    if 'private_evaluation' in path.parts:
                        raise AssertionError('capture must not open the private evaluation')
                    return original_open(path, *args, **kwargs)
                memory = self.memory()
                with patch.object(Path, 'open', no_private), \
                     patch.object(ProjectController, 'advance_selection', side_effect=AssertionError('no dispatch')), \
                     patch.object(staged, 'execute', side_effect=AssertionError('no rerun')), \
                     patch.object(retrieval_holdout, '_verified_private', side_effect=AssertionError('no final')):
                    imported = memory.import_wait(manager.root, body['request_id'])
                    self.assertEqual(memory.import_wait(manager.root, body['request_id'])['inserted'], 0)
                    bundle = self.case(memory, imported)
                    view = dispatch.summary(dispatch.parse_bundle(canonical(bundle).encode()))
                self.assertEqual(project.status(), before)
                self.assertEqual(view['observation']['feedback']['outcome'], outcome)
                self.assertEqual(view['observation']['final_status'], 'unmeasured_at_wait')
                self.assertIn('offline_wait_binding_unverifiable_without_origin', canonical(view))
                if not execute:
                    self.assertIsNone(view['observation']['primary'])
                    self.assertIsNone(view['origin_evidence']['action_id'])
                    self.assertIsNone(view['observation']['feedback']['value'])
                elif sign is None:
                    self.assertEqual(view['observation']['feedback']['value'], 0)
                self.assertNotIn('SECRET_FINAL_QUERY', canonical(bundle))
                self.assertEqual(before['budget']['new_fits'], 0)
                self.assertEqual(before['budget']['new_model_requests'], 0)

    def test_wait_snapshot_drift_and_source_artifact_damage_are_rejected(self):
        manager, project, body = self.source('negative')
        action = project.status()['actions'][0]
        artifact = project._artifact(action)
        raw = artifact.read_bytes()
        damaged = json.loads(raw); damaged['tool_result']['result']['rankings'][0]['query_line'] += 1
        artifact.write_text(canonical(damaged))
        with self.assertRaises(ResearchError):
            waiting.derive_wait_observation(manager.root, body['request_id'])
        artifact.write_bytes(raw)
        state = project.status()
        project.extend_local_budget(request_id='later-budget', expected_state_version=state['state_version'],
                                    expected_limit=state['budget']['local_tool_call_limit'],
                                    new_limit=state['budget']['local_tool_call_limit'] + 1, reason='Later engineering route.')
        with self.assertRaises(ResearchError):
            waiting.derive_wait_observation(manager.root, body['request_id'])

    def test_resealed_context_scope_and_holdout_count_are_rejected(self):
        for mutation in ('scope', 'count', 'controller'):
            with self.subTest(mutation=mutation):
                manager, project, body = self.source(None)
                state = project.status()
                with manager._connect() as con:
                    row = con.execute('SELECT record FROM requests WHERE id=?', (body['request_id'],)).fetchone()
                    record = json.loads(row['record'])
                    if mutation == 'controller':
                        record['intent']['controller_code_identity'] = 'a' * 64
                    else:
                        context = record['conditional']['context']
                        if mutation == 'scope': context['domain_scope']['dataset_label'] = 'Resealed wrong source'
                        if mutation == 'count': context['staged_evaluation']['query_count'] += 1
                        context['context_sha256'] = fingerprint({k:v for k,v in context.items() if k != 'context_sha256'})
                        record['conditional'] = waiting.staged_continuation.conditional_policy(
                            state, body['registration_request_id'], body['primary_action_id'], context)
                    record['record_sha256'] = fingerprint({k:v for k,v in record.items() if k != 'record_sha256'})
                    con.execute('UPDATE requests SET record=? WHERE id=?', (canonical(record), body['request_id']))
                with self.assertRaises(ResearchError) as error:
                    waiting.derive_wait_observation(manager.root, body['request_id'])
                self.assertEqual(error.exception.code, 'EVIDENCE_CHANGED')
                self.assertEqual(project.status(), state)
    def test_future_primary_manager_and_host_collisions_reject_without_project_change(self):
        for field in ('manager', 'host'):
            with self.subTest(field=field):
                manager, project, body = self.source(execute=False)
                before = project.status()
                if field == 'manager':
                    with manager._connect() as con:
                        con.execute('INSERT INTO requests VALUES(?,?,?,?)', (body['primary_action_id'], 'a'*64, 'unrelated', '{}'))
                    with self.assertRaises(ResearchError) as error:
                        waiting.derive_wait_observation(manager.root, body['request_id'])
                else:
                    original = HostModelSelection.status
                    def occupied(host, **kwargs):
                        value = original(host, **kwargs)
                        value['requests'].append({'request_id': body['primary_action_id'], 'controller_request_id': 'different', 'status':'completed'})
                        return value
                    with patch.object(HostModelSelection, 'status', occupied), self.assertRaises(ResearchError) as error:
                        waiting.derive_wait_observation(manager.root, body['request_id'])
                self.assertEqual(error.exception.code, 'EVIDENCE_CHANGED')
                self.assertEqual(project.status(), before)

    def test_offline_tampering_and_explicit_route(self):
        manager, _, body = self.source(None)
        memory = self.memory(); imported = memory.import_wait(manager.root, body['request_id'])
        bundle = self.case(memory, imported)
        self.assertEqual(dispatch.parse_bundle(canonical(bundle).encode()), bundle)
        for mutation in ('outcome', 'bool_value', 'final', 'branch'):
            bad = copy.deepcopy(bundle); record = bad['record']; payload = record['payload']
            if mutation == 'outcome': payload['feedback']['outcome'] = 'condition_met'
            if mutation == 'bool_value': payload['feedback']['value'] = False
            if mutation == 'final': payload['final_status'] = 'unmeasured_forever'
            if mutation == 'branch': payload['feedback']['branches']['condition_not_met'] = {'kind':'method','method_id':staged.AUDIT_TOOL_ID}
            record['id'] = waiting.observation_id(record)
            with self.subTest(mutation=mutation), self.assertRaises(ResearchError):
                dispatch.validate_bundle(bad)

    def test_standalone_report_identity_includes_wait_parser(self):
        expected = project_report.recovery_source_identity('staged_relevance')
        original = Path.read_bytes
        parser = Path(waiting.__file__)
        def changed(path):
            data = original(path)
            return data + b'\n# independent parser drift\n' if path == parser else data
        with patch.object(Path, 'read_bytes', changed):
            self.assertNotEqual(project_report.recovery_source_identity('staged_relevance'), expected)

    def test_new_target_project_gets_case_in_selection_and_report_without_tool_use(self):
        manager, source, body = self.source('negative')
        source_before = source.status()
        memory = self.memory(); imported = memory.import_wait(manager.root, body['request_id'])
        bundle = self.case(memory, imported)
        helper = holdout_fixtures.RetrievalHoldoutTests(); self.addCleanup(helper.doCleanups)
        target, _, _ = helper.fixture()
        before = target.status(); raw = canonical(bundle).encode()
        request = {'request_id': 'wait-import', 'expected_state_version': before['state_version'],
                   'bundle': raw, 'reason': 'Review the earlier waiting feedback.'}
        first = target.import_experience(**request)
        self.assertEqual(first, target.import_experience(**request))
        context = ProjectController(target.root).selection_context()
        case = context['experience']['cases'][0]
        self.assertEqual(case['observation']['feedback']['outcome'], 'condition_not_met')
        self.assertEqual(case['observation']['final_status'], 'unmeasured_at_wait')
        plan = research_plan_proposal.build_context(target)
        self.assertEqual(plan['selection_context']['experience']['cases'][0]['observation']['feedback'],
                         case['observation']['feedback'])
        self.assertIn('condition_not_met', research_plan_proposal.build_prompt(plan)['prompt'])
        rows = project_report._experience_rows({'experience_cases': [case]})
        self.assertIn('当时 final 未测', rows[0][3])
        self.assertIn('不限制后续路线', rows[0][3])
        self.assertEqual(target.status()['budget'], before['budget'])
        self.assertEqual(target.status()['actions'], before['actions'])
        self.assertEqual(source.status(), source_before)

    def test_known_and_unknown_bundle_reach_target_through_http_with_same_id_replay(self):
        for execute, outcome in ((True, 'condition_not_met'), (False, 'unknown')):
            with self.subTest(outcome=outcome):
                source_manager, source, body = self.source('negative', execute=execute)
                source_before = source.status()
                memory = self.memory(); imported = memory.import_wait(source_manager.root, body['request_id'])
                raw = canonical(self.case(memory, imported)).encode()
                helper = holdout_fixtures.RetrievalHoldoutTests(); self.addCleanup(helper.doCleanups)
                original, _, _ = helper.fixture()
                manager = LocalWorkbench(Path(self.enterContext(tempfile.TemporaryDirectory())) / 'target-manager')
                project_id = manager.import_project(request_id='target-import', workspace=original.root)['project_id']
                manager.select({'request_id':'target-select', 'project_id':project_id})
                target, _ = manager.binding(); before = target.status()
                server = self.serve(local_workspace=manager, allow_local_actions=True); headers = self.session(server)
                request = {'request_id':'case-import', 'project_id':project_id, 'expected_state_version':before['state_version'],
                           'bundle_base64':base64.b64encode(raw).decode(), 'reason':'Review the saved waiting case.'}
                status, response = self.request(server, '/api/local-workbench/experience-import', 'POST', request, headers)
                self.assertEqual(status, 200); self.assertFalse(response['replayed'])
                status, replay = self.request(server, '/api/local-workbench/experience-import', 'POST', request, headers)
                self.assertEqual(status, 200); self.assertTrue(replay['replayed'])
                plan = research_plan_proposal.build_context(target)
                case = plan['selection_context']['experience']['cases'][0]
                self.assertEqual(case['observation']['feedback']['outcome'], outcome)
                if not execute:
                    self.assertIsNone(case['origin_evidence']['action_id'])
                    self.assertIsNone(case['observation']['feedback']['value'])
                self.assertEqual(target.status()['actions'], before['actions'])
                self.assertEqual(target.status()['budget'], before['budget'])
                self.assertEqual(source.status(), source_before)


if __name__ == '__main__':
    unittest.main()
