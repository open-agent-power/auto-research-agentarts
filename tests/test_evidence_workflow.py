import copy
import json
import tempfile
import unittest
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from autoresearch import evidence_workflow as workflow
from autoresearch.contracts import ResearchError


class EvidenceWorkflowTests(unittest.TestCase):
    def test_single_child_idempotent_publication_budget_mismatch_and_unknown_not_resent(self):
        counters = {'create': 0, 'send': 0, 'export': 0}

        class Study:
            def __init__(self, root):
                self.root = Path(root); self.db = self.root / 'source-assessment-study.sqlite'

            def create(self, packet_path, goal, max_requests=4, prior_attempt=None):
                counters['create'] += 1; self.root.mkdir()
                self.db.write_text(json.dumps({'config': {'goal': goal, 'max_requests': max_requests,
                    'private_sources': {'packet_path': str(packet_path)}, 'prior_attempt': prior_attempt},
                    'state': {'status': 'active', 'source_snapshot_sha256': 'a' * 64, 'actions': []}}))

            def _connect(self): return nullcontext(None)

            def _state(self, con):
                value = json.loads(self.db.read_text()); return value['config'], value['state'], value['state']['actions']

        class Loop:
            def __init__(self, root):
                self.study = Study(root); self.db = Path(root) / 'source-assessment-cloud.sqlite'

            def configure(self, identity):
                self.db.write_text(json.dumps({'status': 'active', 'reason': None, 'calls': []}))

            def status(self):
                value = json.loads(self.db.read_text()); config, state, _ = self.study._state(None)
                return {**value, 'study': state, 'budget': {'max_requests': config['max_requests'], 'requests_reserved': len(value['calls'])}}

            def run(self, server=None, max_new_requests=0, verified_weights=None):
                result = self.status()
                if any(c['status'] == 'sending' for c in result['calls']):
                    raise ResearchError('NEEDS_REVIEW', 'Unknown sending must not be retried')
                if max_new_requests and result['study']['status'] == 'active':
                    counters['send'] += 1
                    result['calls'].append({'status': 'applied'})
                    stored = json.loads(self.study.db.read_text())
                    stored['state']['status'] = 'paused'
                    stored['state']['actions'] = [{'id': 'assessment', 'action': 'record_assessment',
                        'result_sha256': 'b' * 64, 'result': {'answers': [{'status': 'unresolved'}]}}]
                    self.study.db.write_text(json.dumps(stored))
                    self.db.write_text(json.dumps({'status': 'completed', 'reason': 'STUDY_NOT_ACTIVE', 'calls': result['calls']}))
                return self.status()

        def export(child, output):
            counters['export'] += 1; output.mkdir()
            result = Loop(child).status()
            view = {'source_snapshot_sha256': 'a' * 64, 'snapshot_sha256': 'c' * 64,
                    'actions': result['study']['actions'], 'execution': {'requests_reserved': len(result['calls'])}}
            (output / 'assessment.json').write_text(json.dumps(view))
            (output / 'assessment.md').write_text('Unreviewed; not a completed external task')

        def read(directory, expected_source_snapshot=None):
            self.assertEqual(expected_source_snapshot, 'a' * 64)
            return {p.name: p.read_bytes() for p in Path(directory).iterdir()}

        progress_exports = []
        def export_progress(child, output):
            progress_exports.append(output); output.mkdir()
            result = Loop(child).status()
            view = {'schema_version': 'p02-source-assessment-progress-v1',
                    'publication_eligible': False, 'source_snapshot_sha256': 'a' * 64,
                    'snapshot_sha256': 'e' * 64, 'actions': result['study']['actions'],
                    'execution': {'requests_reserved': len(result['calls'])}}
            (output / 'progress.json').write_text(json.dumps(view))
            (output / 'progress.md').write_text('Unknown sending; not a completed assessment')

        module = SimpleNamespace(SourceAssessmentCloudLoop=Loop)
        publication = SimpleNamespace(export_source_assessment=export, read_source_assessment_artifacts=read,
                                      export_source_progress=export_progress, read_source_progress_artifacts=read)
        with tempfile.TemporaryDirectory() as temp, patch.object(workflow, 'assessment_module', return_value=module), \
             patch.object(workflow, 'publication_module', return_value=publication):
            root = Path(temp); source = root / 'source.json'; source.write_text('{}')
            run = workflow.EvidenceWorkflow(root / 'workflow')
            args = {'source_packet': source, 'goal': 'Assess returned evidence', 'max_requests': 4,
                    'protocol_change_reason': 'Use source selection aliases without resetting prior study'}
            initial = run.create(**args); self.assertEqual(initial, run.create(**args))
            with self.assertRaises(ResearchError): run.create(**{**args, 'max_requests': 3})
            for _ in range(2):
                status = run.advance()
                self.assertEqual(status['workflow_status'], 'prepared')
                self.assertEqual(status['budget'], {'max_requests': 4, 'requests_reserved': 0})
            self.assertEqual(counters['create'], 1)
            server = SimpleNamespace(acquire=lambda: {'model': 'fixture'})
            status = run.advance(1, transport=server)
            self.assertEqual(status['workflow_status'], 'awaiting_external_input')
            self.assertFalse(status['scientific_validation']); self.assertFalse(status['external_task_executed'])
            original = (run.publication / 'assessment.json').read_bytes()
            def forbidden(directory): self.fail('Terminal or unknown child must never open transport')
            repeated = workflow.EvidenceWorkflow(run.root).advance(4, transport=forbidden)
            self.assertEqual(repeated['budget'], {'max_requests': 4, 'requests_reserved': 1})
            self.assertEqual((run.publication / 'assessment.json').read_bytes(), original)
            self.assertEqual(counters, {'create': 1, 'send': 1, 'export': 1})
            (run.root / 'advance.lock').write_text('operator must investigate stale lock')
            with self.assertRaises(ResearchError): run.advance()
            (run.root / 'advance.lock').unlink()
            unknown = workflow.EvidenceWorkflow(root / 'unknown')
            unknown.create(**args); unknown.advance()
            loop = Loop(unknown.child); loop.configure({})
            saved = json.loads(loop.study.db.read_text())
            saved['state']['actions'] = [{'id': 'read', 'action': 'read_sources', 'result_sha256': 'd' * 64}]
            loop.study.db.write_text(json.dumps(saved))
            loop.db.write_text(json.dumps({'status': 'needs_review', 'reason': 'UNKNOWN_NATIVE_REQUEST',
                                           'calls': [{'status': 'applied'}, {'status': 'sending'}]}))
            held = unknown.advance(4, transport=forbidden)
            self.assertEqual(held['workflow_status'], 'needs_attention')
            self.assertEqual(held['budget']['requests_reserved'], 2)
            self.assertFalse(unknown.publication.exists()); self.assertEqual(counters['send'], 1)
            self.assertIsNone(held['publication']); self.assertFalse(held['progress']['publication_eligible'])
            repeated = unknown.advance(4, transport=forbidden)
            self.assertEqual(repeated['progress'], held['progress'])
            self.assertEqual(len(progress_exports), 1)
            self.assertEqual(counters['export'], 1)


if __name__ == '__main__':
    unittest.main()
