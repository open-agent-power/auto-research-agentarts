"""Read-only projection of a completed child with its still-unknown parent."""
import copy
import json
import unittest
from unittest.mock import patch

from autoresearch import project_report, project_workbench, tabular_quality_adapter
from autoresearch.contracts import ResearchError
from autoresearch.project_controller import ProjectController
from autoresearch.project_selection_view import read_selection_request, selection_view
from autoresearch.research_project import ResearchProject
import test_unknown_controller_parent as fixture


class SelectionUnknownRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixture.UnknownParentTests('runTest')
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.state = self.fixture.make_unknown_parent_with_completed_child()
        self.project = self.fixture.project

    def test_readers_preserve_frozen_unknown_and_do_not_dispatch(self):
        state = copy.deepcopy(self.state)
        before = self.project.db.read_bytes()
        with patch.object(ResearchProject, 'step', side_effect=AssertionError('step')), \
             patch.object(ProjectController, '_dispatch', side_effect=AssertionError('dispatch')), \
             patch.object(tabular_quality_adapter, 'execute', side_effect=AssertionError('execute')):
            view = selection_view(state)
            raw = read_selection_request(state, 'original-parent')
            workbench = project_workbench._projection(self.project, state)
            report = project_report.collect_report(self.project.root)
        parent = state['controller_requests'][-1]
        self.assertEqual(raw, parent)
        self.assertEqual(view['records'][0]['status'], 'unknown')
        self.assertEqual(view['records'][0]['child'], parent['result']['child'])
        self.assertEqual(view['records'][0]['child']['status'], 'unknown')
        self.assertEqual(workbench['selection_history'], view)
        self.assertEqual(report['selection_history'], view)
        self.assertEqual([b['code'] for b in report['execution_conditions']['blockers']], ['EXECUTION_UNKNOWN'])
        self.assertEqual(self.project.status(), self.state)
        self.assertEqual(self.project.db.read_bytes(), before)
        self.assertEqual(state, self.state)
        self.assertEqual(self.state['budget']['local_tool_calls_used'], 1)

    def test_report_rejects_changed_completed_artifact(self):
        artifact = self.project.root / self.state['actions'][0]['artifact']
        original = artifact.read_bytes()
        try:
            changed = json.loads(original)
            changed['tool_result']['status'] = 'tampered'
            artifact.write_text(json.dumps(changed))
            with self.assertRaises(ResearchError) as error:
                project_report.collect_report(self.project.root)
            self.assertEqual(error.exception.code, 'EVIDENCE_CHANGED')
        finally:
            artifact.write_bytes(original)
        self.assertEqual(self.project.status(), self.state)

    def test_divergent_and_illegal_history_rejected(self):
        def mutate_frozen(field, value):
            def mutate(s): s['controller_requests'][-1]['result']['child'][field] = value
            return mutate
        def mutate_child(field, value):
            def mutate(s): s['actions'][0][field] = value
            return mutate
        changes = [
            mutate_frozen('id', 'action-other'),
            mutate_frozen('request_id', 'other'),
            mutate_frozen('command', 'data.other'),
            mutate_frozen('status', 'running'),
            mutate_frozen('failure', {'code':'EXECUTION_UNKNOWN', 'automatic_retry':0}),
            mutate_frozen('artifact', 'artifacts/fake.json'),
            mutate_child('request_sha256', 'a' * 64),
            mutate_child('source_snapshot_sha256', 'a' * 64),
            mutate_child('code_identity', 'a' * 64),
            mutate_child('status', 'failed'),
            mutate_child('failure', {'code':'other'}),
            mutate_child('artifact', 'artifacts/other.json'),
            mutate_child('result_sha256', 'not-a-hash'),
            lambda s: s['controller_requests'][-1].update(status='completed'),
            lambda s: s['controller_requests'][-1].update(state_version_after=s['state_version']),
            lambda s: s['controller_requests'][-1].update(state_version_after=s['state_version'] + 1),
            lambda s: s['controller_requests'][-1].update(state_version_after=s['controller_requests'][-1]['dispatch_state_version']),
            lambda s: s['controller_requests'][-1].update(state_version_after=True),
        ]
        for change in changes:
            with self.subTest(change=change):
                state = copy.deepcopy(self.state)
                change(state)
                with self.assertRaises(ResearchError) as error: selection_view(state)
                self.assertEqual(error.exception.code, 'EVIDENCE_CHANGED')

    def test_reconciled_parent_uses_original_wire_shape(self):
        with patch.object(tabular_quality_adapter, 'execute', side_effect=AssertionError('execute')):
            self.fixture.controller.advance_selection(request_id='original-parent', proposal=self.fixture.proposal,
                expected_state_version=self.fixture.before_version)
        state = self.project.status()
        parent = state['controller_requests'][-1]
        result = selection_view(state)
        self.assertEqual(result['schema_version'], 'project-selection-view-v1')
        self.assertEqual(result['records'][0]['status'], 'completed')
        self.assertEqual(result['records'][0]['child'], parent['result']['child'])
        self.assertEqual(state['budget']['local_tool_calls_used'], 1)


if __name__ == '__main__': unittest.main()
