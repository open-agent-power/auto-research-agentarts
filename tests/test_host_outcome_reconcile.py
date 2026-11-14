"""Temporary Host recovery fixtures. No model or research adapter is executed."""
import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import test_local_workbench as fixtures
from autoresearch.contracts import ResearchError, canonical, fingerprint
from autoresearch.host_model_batch import HostModelBatch
from autoresearch.host_model_selection import HostModelSelection
from autoresearch.local_workbench import LocalWorkbench
from autoresearch.project_controller import ProjectController


class ObservedOutcomeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(self.enterContext(tempfile.TemporaryDirectory()))
        manager = LocalWorkbench(self.tmp / 'manager')
        manager.create(fixtures.LocalWorkbenchTests.create_body(self))
        self.project, _ = manager.binding()
        self.batch = HostModelBatch(self.project.root)
        self.journal = self.batch.journal
        self.batch_args = dict(request_id='engineering', expected_state_version=0, max_decisions=1,
                               decision_limit=1, cli_budget_usd=.1, reason='temporary engineering fixture')
        first = self.batch.advance_delegated(**self.batch_args)
        self.assertEqual(first['status'], 'awaiting_external_response')
        self.prepared = self.journal.status(request_id='hostbatch-engineering-s1')
        candidate = self.prepared['context']['candidates'][0]
        response = {'choice': {'kind': 'execute', 'candidate_id': candidate['id']},
                    'rationale': 'Synthetic fixture selection.', 'evidence_citation_ids': []}
        self.response = self.tmp / 'response.json'
        self.response.write_bytes(canonical(response).encode())
        self.journal.import_response(request_id='hostbatch-engineering-s1', response_file=self.response)
        with patch.object(ProjectController, '_dispatch', self.fake_unknown):
            self.unknown = self.journal.consume(request_id='hostbatch-engineering-s1')
        self.assertEqual(self.unknown['outcome']['status'], 'unknown')

    def fake_unknown(self, parent, *, replayed):
        current = self.project.status()
        action = parent['decision']['next_action']
        params = action['parameters']
        request = {'project_id': parent['project_id'], 'command': action['method_id'],
                   'source_snapshot_sha256': current['source_snapshot_sha256'], 'dimension': params.get('dimension')}
        child = {**request, 'id': 'action-' + fingerprint({'request_id': parent['child_request_id'], **request})[:32],
                 'request_id': parent['child_request_id'], 'run_id': current['run_id'],
                 'code_identity': parent['code_identity'], 'status': 'unknown', 'failure': None,
                 'method_instance': {'definition_ref': {'id': action['method_id']}, 'parameters': params},
                 'request_sha256': fingerprint(request)}
        with self.project._writer(), self.project._connect() as con:
            project = self.project._project(con)
            saved = next(item for item in project['controller_requests'] if item['request_id'] == 'hostbatch-engineering-s1')
            result = {'child': {key: child[key] for key in ('id', 'request_id', 'command', 'status', 'artifact', 'result_sha256', 'failure') if key in child},
                      'recovered': False, 'reused': False}
            saved.update(status='unknown', result=result)
            project['state_version'] += 1
            saved['state_version_after'] = project['state_version']
            con.execute('INSERT INTO actions VALUES(?,?,?)', (child['request_id'], child['request_sha256'], canonical(child)))
            self.project._save(con, project)
            return ProjectController._response(saved, replayed=False)

    def complete_fixture(self):
        with self.project._writer(), self.project._connect() as con:
            project = self.project._project(con)
            parent = next(item for item in project['controller_requests'] if item['request_id'] == 'hostbatch-engineering-s1')
            child = self.project._action(con, parent['child_request_id'])
            child.update(status='completed', artifact='artifacts/' + child['id'] + '.json', result_sha256='1' * 64)
            con.execute('UPDATE actions SET record=? WHERE request_id=?', (canonical(child), child['request_id']))
            parent.update(status='completed', result={'child': {key: child[key] for key in ('id', 'request_id', 'command', 'status', 'artifact', 'result_sha256', 'failure') if key in child},
                                                      'recovered': True, 'reused': False})
            project['state_version'] += 1
            parent['state_version_after'] = project['state_version']
            self.project._save(con, project)

    def guards(self):
        for target in ('autoresearch.project_controller.ProjectController.advance_selection',
                       'autoresearch.project_controller.ProjectController._dispatch',
                       'autoresearch.research_project.ResearchProject.step',
                       'autoresearch.research_project.ResearchProject.read_evidence',
                       'autoresearch.research_project.ResearchProject._recover',
                       'autoresearch.research_project.ResearchProject._commit_result',
                       'autoresearch.host_model_selection.run_claude_selection'):
            self.enterContext(patch(target, side_effect=AssertionError('forbidden dispatch or recovery: ' + target)))

    def test_same_id_observation_updates_host_only_and_is_idempotent(self):
        self.complete_fixture()
        before = self.project.status()
        original_db = self.project.db.read_bytes()
        usage = self.journal.status()['usage']
        self.guards()
        result = self.journal.reconcile_outcome(request_id='hostbatch-engineering-s1')
        self.assertEqual(result['outcome']['status'], 'completed')
        self.assertEqual(result['previous_unknown'], self.unknown['outcome'])
        self.assertFalse(result['outcome_observation']['artifact_revalidated'])
        self.assertEqual(self.journal.reconcile_outcome(request_id='hostbatch-engineering-s1'), result)
        self.assertEqual(self.project.status(), before)
        self.assertEqual(self.project.db.read_bytes(), original_db)
        self.assertEqual(self.journal.status()['usage'], usage)

    def test_unknown_parent_never_resumes(self):
        before = self.project.status()
        self.guards()
        self.assertEqual(self.journal.reconcile_outcome(request_id='hostbatch-engineering-s1'), self.unknown)
        self.assertEqual(self.project.status(), before)

    def test_missing_capability_refuses_without_mutation(self):
        self.complete_fixture()
        state = self.journal._load()
        del state['requests']['hostbatch-engineering-s1']['prepare_specification']['observed_reconciliation']
        self.journal._save(state)
        before = self.journal.state_file.read_bytes()
        self.guards()
        with self.assertRaises(ResearchError):
            self.journal.reconcile_outcome(request_id='hostbatch-engineering-s1')
        self.assertEqual(self.journal.state_file.read_bytes(), before)

    def test_changed_response_is_rejected_before_host_write(self):
        self.complete_fixture()
        before = self.journal.state_file.read_bytes()
        record = self.journal.status(request_id='hostbatch-engineering-s1')
        (self.journal.directory / record['response_file']).write_bytes(b'{}')
        self.guards()
        with self.assertRaises(ResearchError):
            self.journal.reconcile_outcome(request_id='hostbatch-engineering-s1')
        self.assertEqual(self.journal.state_file.read_bytes(), before)

    def test_interruption_before_host_save_reconciles_same_id_once(self):
        self.complete_fixture()
        before_host = self.journal.state_file.read_bytes()
        before_project = self.project.status()
        self.guards()
        with patch.object(self.journal, '_save', side_effect=KeyboardInterrupt('before Host save')):
            with self.assertRaises(KeyboardInterrupt):
                self.journal.reconcile_outcome(request_id='hostbatch-engineering-s1')
        self.assertEqual(self.journal.state_file.read_bytes(), before_host)
        result = self.journal.reconcile_outcome(request_id='hostbatch-engineering-s1')
        self.assertEqual(result['previous_unknown'], self.unknown['outcome'])
        self.assertEqual(self.project.status(), before_project)
        self.assertEqual(self.journal.reconcile_outcome(request_id='hostbatch-engineering-s1'), result)

    def test_missing_child_remains_unknown_without_write(self):
        self.complete_fixture()
        with self.project._writer(), self.project._connect() as con:
            con.execute('DELETE FROM actions')
        before_host, before_project = self.journal.state_file.read_bytes(), self.project.status()
        self.guards()
        self.assertEqual(self.journal.reconcile_outcome(request_id='hostbatch-engineering-s1'), self.unknown)
        self.assertEqual(self.journal.state_file.read_bytes(), before_host)
        self.assertEqual(self.project.status(), before_project)

    def test_parent_digest_conflict_is_rejected_without_host_write(self):
        self.complete_fixture()
        with self.project._writer(), self.project._connect() as con:
            project = self.project._project(con)
            project['controller_requests'][0]['request_sha256'] = 'corrupted'
            self.project._save(con, project)
        before = self.journal.state_file.read_bytes()
        self.guards()
        with self.assertRaises(ResearchError):
            self.journal.reconcile_outcome(request_id='hostbatch-engineering-s1')
        self.assertEqual(self.journal.state_file.read_bytes(), before)

    def test_incomplete_parent_result_is_rejected_without_host_write(self):
        self.complete_fixture()
        with self.project._writer(), self.project._connect() as con:
            project = self.project._project(con)
            del project['controller_requests'][0]['result']['recovered']
            self.project._save(con, project)
        before = self.journal.state_file.read_bytes()
        self.guards()
        with self.assertRaises(ResearchError):
            self.journal.reconcile_outcome(request_id='hostbatch-engineering-s1')
        self.assertEqual(self.journal.state_file.read_bytes(), before)

    def test_changed_context_prompt_or_proposal_bytes_are_rejected(self):
        self.complete_fixture()
        record = self.journal.status(request_id='hostbatch-engineering-s1')
        before = self.journal.state_file.read_bytes()
        self.guards()
        for name in ('context.json', 'prompt.json', 'proposal.json'):
            with self.subTest(name=name):
                path = self.journal.directory / record['directory'] / name
                raw = path.read_bytes()
                path.write_bytes(b'{}')
                with self.assertRaises(ResearchError):
                    self.journal.reconcile_outcome(request_id='hostbatch-engineering-s1')
                path.write_bytes(raw)
                self.assertEqual(self.journal.state_file.read_bytes(), before)

    def test_original_unknown_history_cannot_be_overwritten(self):
        self.complete_fixture()
        state = self.journal._load()
        state['requests']['hostbatch-engineering-s1']['previous_unknown'] = {'status': 'unknown', 'other': 'conflict'}
        self.journal._save(state)
        before = self.journal.state_file.read_bytes()
        self.guards()
        with self.assertRaises(ResearchError):
            self.journal.reconcile_outcome(request_id='hostbatch-engineering-s1')
        self.assertEqual(self.journal.state_file.read_bytes(), before)

    def test_batch_automatically_observes_completed_same_id_once(self):
        self.complete_fixture()
        before = self.project.status()
        self.guards()
        result = self.batch.advance_delegated(**self.batch_args)
        self.assertEqual((result['status'], result['record_status']), ('limit_reached', 'completed'))
        self.assertEqual(len(result['steps']), 1)
        self.assertEqual(result['cursor_snapshot_ref'], before['snapshot_ref'])
        self.assertEqual(self.project.status(), before)
        self.assertEqual(self.journal.status()['usage']['decision_slots_used'], 1)
        self.assertEqual(self.batch.advance_delegated(**self.batch_args), result)

    def test_interruption_after_host_save_before_batch_save_reuses_observation(self):
        self.complete_fixture()
        before_project = self.project.status()
        self.guards()
        original_save = self.batch._save
        def interrupt(record):
            if record['steps'][-1].get('outcome_status') == 'completed':
                raise KeyboardInterrupt('after Host save before batch save')
            return original_save(record)
        with patch.object(self.batch, '_save', side_effect=interrupt):
            with self.assertRaises(KeyboardInterrupt):
                self.batch.advance_delegated(**self.batch_args)
        self.assertEqual(self.journal.status(request_id='hostbatch-engineering-s1')['outcome']['status'], 'completed')
        result = self.batch.advance_delegated(**self.batch_args)
        self.assertEqual(result['status'], 'limit_reached')
        self.assertEqual(self.project.status(), before_project)
        self.assertEqual(self.journal.status()['usage']['decision_slots_used'], 1)

    def test_project_change_after_completion_stops_batch(self):
        self.complete_fixture()
        with self.project._writer(), self.project._connect() as con:
            project = self.project._project(con)
            project['state_version'] += 1
            self.project._save(con, project)
        self.guards()
        stopped = self.batch.advance_delegated(**self.batch_args)
        self.assertEqual(stopped['status'], 'blocked')
        self.assertEqual(stopped['stop']['code'], 'STALE_STATE')
        self.assertEqual(self.journal.status()['usage']['decision_slots_used'], 1)

    def test_changed_reconciliation_code_identity_refuses(self):
        self.complete_fixture()
        before = self.journal.state_file.read_bytes()
        self.guards()
        with patch('autoresearch.host_model_selection._reconcile_code_identity', return_value={'changed': 'yes'}):
            with self.assertRaises(ResearchError) as caught:
                self.journal.reconcile_outcome(request_id='hostbatch-engineering-s1')
        self.assertEqual(caught.exception.code, 'CODE_CHANGED')
        self.assertEqual(self.journal.state_file.read_bytes(), before)

    def test_busy_project_does_not_write_host_record(self):
        self.complete_fixture()
        before = self.journal.state_file.read_bytes()
        self.guards()
        with self.project._writer():
            with self.assertRaises(ResearchError) as caught:
                self.journal.reconcile_outcome(request_id='hostbatch-engineering-s1')
        self.assertEqual(caught.exception.code, 'PROJECT_BUSY')
        self.assertEqual(self.journal.state_file.read_bytes(), before)

    def test_old_prepare_specification_has_no_capability_marker(self):
        manager = LocalWorkbench(self.tmp / 'legacy-manager')
        manager.create(fixtures.LocalWorkbenchTests.create_body(self))
        project, _ = manager.binding()
        legacy = HostModelSelection(project.root).prepare(request_id='legacy', provider='delegated',
            expected_state_version=0, decision_limit=1, cli_budget_usd=.1, reason='legacy fixture')
        self.assertEqual(set(legacy['prepare_specification']),
                         {'request_id', 'provider', 'expected_state_version', 'grant', 'executable'})
        self.assertNotIn('observed_reconciliation', legacy['prepare_specification'])

    def test_bad_child_identity_and_inputs_are_rejected(self):
        self.complete_fixture()
        with self.project._connect(readonly=True) as con:
            original_project = self.project._project(con)
            original_child = self.project._action(con, original_project['controller_requests'][0]['child_request_id'])
        before = self.journal.state_file.read_bytes()
        self.guards()
        for field in ('command', 'parameters', 'source', 'producer', 'request_sha', 'result_sha', 'missing_result_sha'):
            with self.subTest(field=field):
                project, child = copy.deepcopy(original_project), copy.deepcopy(original_child)
                parent = project['controller_requests'][0]
                if field == 'command': child['command'] = 'not-the-selected-method'
                if field == 'parameters': child['method_instance']['parameters'] = {'different': True}
                if field == 'source': child['source_snapshot_sha256'] = 'different'
                if field == 'producer': child['code_identity'] = 'different'
                if field == 'request_sha': child['request_sha256'] = 'different'
                if field == 'result_sha': child['result_sha256'] = 'different'
                if field == 'missing_result_sha': del child['result_sha256']
                # Keep the parent projection aligned except in the result-SHA mismatch test.
                if field != 'result_sha':
                    parent['result']['child'] = {key: child[key] for key in ('id', 'request_id', 'command', 'status', 'artifact', 'result_sha256', 'failure') if key in child}
                with self.project._writer(), self.project._connect() as con:
                    con.execute('UPDATE actions SET fingerprint=?, record=? WHERE request_id=?',
                                (child['request_sha256'], canonical(child), child['request_id']))
                    self.project._save(con, project)
                with self.assertRaises(ResearchError):
                    self.journal.reconcile_outcome(request_id='hostbatch-engineering-s1')
                self.assertEqual(self.journal.state_file.read_bytes(), before)
