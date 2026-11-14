"""Independent synthetic interrupted-action source-pin regression tests.

Only Path.read_bytes is substituted in memory; no actual source is modified.
No network, model API, scientific fit, or historical research data is used.
"""
from pathlib import Path
import unittest
from unittest.mock import patch

import test_hypothesis_feedback as fixture
from autoresearch import relevance_retrieval_adapter as adapter, saved_retrieval_reader
from autoresearch.contracts import ResearchError
from autoresearch.project_controller import ProjectController
from autoresearch.research_project import ResearchProject


class PendingSourcePinTests(unittest.TestCase):
    fixture = fixture.HypothesisFeedbackTests.fixture

    def fake_reader_drift(self):
        original = Path.read_bytes
        reader = Path(saved_retrieval_reader.__file__).resolve()
        def read(path):
            content = original(path)
            if path.resolve() == reader:
                return content + b'\n# in-memory test drift only\n'
            return content
        return patch.object(Path, 'read_bytes', read)

    def prepare(self):
        project, candidate = self.fixture()
        controller = ProjectController(project.root)
        context = controller.selection_context()
        proposal = {'schema_version': 'project-selection-proposal-v1', 'context_sha256': context['context_sha256'],
                    'provider': {'kind': 'operator_assistant', 'label': 'independent source pin fixture'},
                    'choice': {'kind': 'execute', 'candidate_id': candidate['id']},
                    'rationale': 'Only constructed local fixture', 'evidence_citation_ids': []}
        kwargs = {'request_id': 'source-pin-parent', 'proposal': proposal, 'expected_state_version': context['state_version']}
        return project, controller, kwargs

    def assert_drift_blocked_without_writes(self, project, callback):
        before = project.status()
        with self.fake_reader_drift():
            with self.assertRaises(ResearchError) as caught:
                callback()
            self.assertEqual(caught.exception.code, 'CODE_CHANGED')
        self.assertEqual(project.status(), before)
        return before

    def test_parent_only_remains_resumable_under_original_pin(self):
        project, controller, kwargs = self.prepare()
        with patch.object(ProjectController, '_dispatch', side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                controller.advance_selection(**kwargs)
        before = project.status()
        self.assertEqual(before['controller_requests'][-1]['status'], 'prepared')
        self.assertEqual(before['actions'], [])
        self.assert_drift_blocked_without_writes(project, lambda: ProjectController(project.root).advance_selection(**kwargs))
        result = ProjectController(project.root).advance_selection(**kwargs)
        self.assertEqual(result['status'], 'completed')
        self.assertEqual(len(project.status()['actions']), 1)
        self.assertEqual(project.status()['budget']['local_tool_calls_used'], 1)

    def test_existing_child_without_artifact_preserves_unknown_reservation(self):
        project, controller, kwargs = self.prepare()
        with patch.object(adapter, 'execute', side_effect=KeyboardInterrupt) as execute:
            with self.assertRaises(KeyboardInterrupt):
                controller.advance_selection(**kwargs)
            before = project.status()
            child = before['actions'][0]
            self.assertEqual(child['status'], 'running')
            self.assertFalse(project._artifact(child).exists())
            self.assert_drift_blocked_without_writes(project, lambda: ProjectController(project.root).advance_selection(**kwargs))
            self.assert_drift_blocked_without_writes(project, lambda: project.step(request_id=child['request_id']))
            self.assertEqual(execute.call_count, 1)
            recovered = project.step(request_id=child['request_id'])
            self.assertEqual(recovered['status'], 'unknown')
            self.assertFalse(recovered['automatic_retry'])
            self.assertEqual(project.status()['budget']['local_tool_calls_reserved'], 1)
            self.assertEqual(execute.call_count, 1)

    def test_existing_artifact_commits_only_under_original_pin(self):
        project, controller, kwargs = self.prepare()
        original_execute = adapter.execute
        with patch.object(adapter, 'execute', wraps=original_execute) as execute:
            with patch.object(ResearchProject, '_commit_result', side_effect=KeyboardInterrupt):
                with self.assertRaises(KeyboardInterrupt):
                    controller.advance_selection(**kwargs)
            before = project.status()
            child = before['actions'][0]
            self.assertEqual(child['status'], 'running')
            artifact = project._artifact(child)
            raw = artifact.read_bytes()
            self.assert_drift_blocked_without_writes(project, lambda: ProjectController(project.root).advance_selection(**kwargs))
            self.assert_drift_blocked_without_writes(project, lambda: project.step(request_id=child['request_id']))
            self.assertEqual(artifact.read_bytes(), raw)
            result = ProjectController(project.root).advance_selection(**kwargs)
            self.assertEqual(result['status'], 'completed')
            self.assertEqual(execute.call_count, 1)
            self.assertEqual(project.status()['budget']['local_tool_calls_used'], 1)
            self.assertEqual(artifact.read_bytes(), raw)

    def test_completed_records_replay_even_after_reader_drift(self):
        project, controller, kwargs = self.prepare()
        result = controller.advance_selection(**kwargs)
        before = project.status()
        child = before['actions'][0]
        with self.fake_reader_drift():
            direct = project.step(request_id=child['request_id'])
            parent = ProjectController(project.root).advance_selection(**kwargs)
        self.assertTrue(direct['replayed'])
        self.assertTrue(parent['replayed'])
        self.assertEqual(parent['child_request_id'], result['child_request_id'])
        self.assertEqual(project.status(), before)


if __name__ == '__main__':
    unittest.main()
