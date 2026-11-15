"""Saved manager feedback handoff, using synthetic research inputs only."""
import copy
import json
import sqlite3
import unittest
from unittest.mock import patch

import test_conditional_staged_continuation as fixtures
from autoresearch import feedback_policy, staged_relevance_adapter as staged, stored_project_history as history, stored_project_summary
from autoresearch.contracts import fingerprint
from autoresearch.project_controller import ProjectController
from autoresearch.research_project import ResearchProject


class StoredFeedbackHandoffTests(unittest.TestCase):
    def setUp(self):
        self.f = fixtures.ConditionalStagedContinuationTests(methodName='runTest')
        self.addCleanup(self.f.doCleanups)
        self.manager, self.project, _ = self.f.fixture('positive')
        state = self.project.status()
        self.body = {'request_id': 'original-feedback', 'project_id': state['id'],
                     'expected_state_version': state['state_version'], 'registration_request_id': 'prediction'}
        with patch.object(staged.SavedDevelopmentAudit, 'execute_saved', side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                self.manager.advance_feedback(self.body)
            self.assertEqual(self.manager.advance_feedback(self.body)['status'], 'unknown')
        self.state = self.project.status()
        self.parent = next(p for p in self.state['controller_requests'] if p['request_id'] == self.body['request_id'])
        self.db = sqlite3.connect(':memory:')
        self.addCleanup(self.db.close)
        with self.manager._connect(readonly=True) as con:
            con.backup(self.db)

    def view(self, parent=None, project=None):
        return history._request_handoff(parent or self.parent, self.db, self.state['id'],
                                        project=self.state if project is None else project)

    def test_real_feedback_unknown_has_matching_redacted_handoff_without_dispatch(self):
        before = self.project.db.read_bytes(), self.manager.db.read_bytes()
        actions = self.state['actions'] + self.state['evidence_actions']
        with patch.object(ResearchProject, '_writer', side_effect=AssertionError('no project write')), \
             patch.object(ProjectController, '_dispatch', side_effect=AssertionError('no dispatch')), \
             patch.object(staged.SavedDevelopmentAudit, 'execute_saved', side_effect=AssertionError('no audit')):
            view = history._controller(self.parent, actions, self.db, self.state['id'], project=self.state)
        handoff = view['request_handoff']
        self.assertEqual((view['manager_receipt']['view_status'], handoff['status']), ('available', 'partial'))
        self.assertEqual((handoff['manager_command'], handoff['body_disclosed']), ('advance_feedback', False))
        self.assertEqual(handoff['semantic_match'], 'current_reader_matched')
        self.assertFalse(handoff['producer_verified'])
        self.assertEqual(handoff['manager_body_sha256'], fingerprint(self.body))
        self.assertEqual(handoff['manager_intent_sha256'], fingerprint(self.body))
        self.assertNotIn('canonical_semantic_body', handoff)
        self.assertNotIn('canonical_semantic_json', handoff)
        self.assertNotIn(self.body['registration_request_id'], json.dumps(handoff))
        self.assertEqual((self.project.db.read_bytes(), self.manager.db.read_bytes()), before)

    def test_missing_duplicate_and_overbound_registrations_never_guess(self):
        for registrations, status in ((None, 'partial'), ([], 'unavailable'),
                                      (self.state['hypothesis_registrations'] * 2, 'ambiguous'),
                                      (self.state['hypothesis_registrations'] * 17, 'partial')):
            project = copy.deepcopy(self.state)
            project['hypothesis_registrations'] = registrations
            with self.subTest(status=status):
                self.assertEqual(self.view(project=project)['status'], status)
        self.db.execute('DELETE FROM requests WHERE id=?', (self.body['request_id'],))
        self.assertEqual(self.view()['status'], 'unavailable')

    def test_missing_registration_field_is_partial(self):
        state = copy.deepcopy(self.state)
        del state['hypothesis_registrations'][0]['registration_sha256']
        self.assertEqual(self.view(project=state)['status'], 'partial')

    def test_actual_readonly_summary_does_not_write_or_return_feedback_body(self):
        before = self.project.db.read_bytes(), self.manager.db.read_bytes()
        with patch.object(ResearchProject, '_writer', side_effect=AssertionError('no project write')), \
             patch.object(ProjectController, '_dispatch', side_effect=AssertionError('no dispatch')):
            summary = stored_project_summary.read_stored_project_summary(self.manager.root)
        self.assertEqual(summary['status'], 'available')
        saved = summary['stored_history']
        parents = [p for plan in saved['plans'] for p in (plan['controllers'] or [])] + saved['unmatched_controllers']
        entry = next(p for p in parents if p['request_id'] == self.body['request_id'])
        self.assertEqual((entry['manager_receipt']['view_status'], entry['request_handoff']['status']), ('available', 'partial'))
        self.assertEqual(entry['request_handoff']['semantic_match'], 'current_reader_matched')
        self.assertNotIn('canonical_semantic_body', entry['request_handoff'])
        self.assertNotIn('canonical_semantic_json', entry['request_handoff'])
        self.assertEqual((self.project.db.read_bytes(), self.manager.db.read_bytes()), before)

    def test_record_and_order_conflicts_are_not_treated_as_missing(self):
        parent = copy.deepcopy(self.parent)
        parent['request_sha256'] = '0' * 64
        self.assertEqual(self.view(parent=parent)['status'], 'integrity_error')
        project = copy.deepcopy(self.state)
        target = next(p for p in project['controller_requests'] if p['request_id'] == 'primary')
        target['state_version_after'] = self.parent['state_version_before'] + 1
        self.assertEqual(self.view(project=project)['status'], 'integrity_error')
        row = self.db.execute('SELECT record FROM requests WHERE id=?', (self.body['request_id'],)).fetchone()
        record = json.loads(row[0]); record['intent']['request_sha256'] = '0' * 64
        self.db.execute('UPDATE requests SET record=? WHERE id=?', (json.dumps(record), self.body['request_id']))
        self.assertEqual(self.view()['status'], 'integrity_error')

    def test_manager_command_and_sealed_context_binding(self):
        parent = copy.deepcopy(self.parent)
        parent['selection_context']['context_sha256'] = '0' * 64
        self.assertEqual(self.view(parent=parent)['status'], 'integrity_error')
        self.db.execute('UPDATE requests SET command=? WHERE id=?', ('advance_recipe', self.body['request_id']))
        self.assertEqual(self.view()['status'], 'integrity_error')

    def test_old_producer_reader_difference_is_partial_not_integrity_error(self):
        with patch('autoresearch.project_controller.code_identity', return_value='f' * 64), \
             patch.object(feedback_policy, 'select_from_feedback', wraps=feedback_policy.select_from_feedback) as compile_feedback:
            self.assertEqual(self.view()['status'], 'partial')
            compile_feedback.assert_not_called()


if __name__ == '__main__':
    unittest.main()
