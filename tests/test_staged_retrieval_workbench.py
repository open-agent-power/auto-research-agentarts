"""Synthetic staged retrieval through native workbench, SQLite, files and report."""
import base64
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import test_relevance_retrieval_adapter as legacy_fixture
from autoresearch import retrieval_holdout, staged_relevance_adapter as staged
from autoresearch.contracts import ResearchError, canonical, fingerprint
from autoresearch.local_workbench import LocalWorkbench
from autoresearch.project_controller import ProjectController
from autoresearch.project_report import collect_report
from autoresearch.research_project import ResearchProject


class StagedRetrievalWorkbenchTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        fixture = legacy_fixture.RelevanceRetrievalAdapterTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        spec = copy.deepcopy(fixture.spec)
        spec.update(schema_version='staged-relevance-development-spec-v1', files=copy.deepcopy(staged.FILES),
                    query_splits={'dev': ['qd'], 'validation': ['qv']})
        fixture.write_json('spec.json', spec)
        fixture.write_rows('queries.jsonl', [{'_id': 'qd', 'text': 'cat', 'metadata': {}},
                                            {'_id': 'qv', 'text': 'unseen token', 'metadata': {}}])
        (fixture.root / 'qrels.tsv').write_text('query-id\tcorpus-id\tscore\nqd\ta\t2\nqv\tb\t1\n')
        packet = staged.capture_source(fixture.root)
        (self.root / 'input').mkdir()
        source = self.root / 'input' / 'source.json'
        source.write_text(canonical(packet))
        project = ResearchProject(self.root / 'project')
        project.create(source=source, goal='Synthetic stage integration', budget_ref='fixture', max_tool_calls=2, method_id=staged.TOOL_ID)
        self.manager = LocalWorkbench(self.root / 'manager')
        imported = self.manager.import_project(request_id='import', workspace=project.root)
        self.project_id = imported['project_id']
        self.manager.select({'request_id': 'select', 'project_id': self.project_id})
        self.project, _ = self.manager.binding()
        plan = {'question': 'What does this fixture show?', 'basis': 'Synthetic only.',
                'steps': 'Compare validation, freeze, evaluate final once.', 'expected_feedback': 'Inspect computed metrics.'}
        self.manager.save_plan({'request_id': 'plan', 'project_id': self.project_id, 'expected_state_version': 0,
                                'plan': plan, 'reason': 'Synthetic preregistration.'})
        self.secret_query_id = 'private-query-secret-marker-7824'
        self.secret_text = 'private query text sentinel 44729'
        queries = canonical({'_id': self.secret_query_id, 'text': self.secret_text, 'metadata': {}}) + '\n'
        qrels = 'query-id\tcorpus-id\tscore\n' + self.secret_query_id + '\ta\t2\n'
        self.private_fields = (queries.encode(), qrels.encode())
        self.holdout = canonical({'schema_version': 'retrieval-holdout-v1', 'corpus_sha256': packet['assets']['corpus']['sha256'],
                                  'queries_jsonl': queries, 'qrels_tsv': qrels}).encode()
        self.enterContext(patch('sklearn.linear_model.Ridge.fit', side_effect=AssertionError('no fit')))
        self.enterContext(patch('sklearn.preprocessing.StandardScaler.fit', side_effect=AssertionError('no fit')))
        self.enterContext(patch('autoresearch.host_model_selection.run_claude_selection', side_effect=AssertionError('no model')))

    def register_body(self):
        return {'request_id': 'register-final', 'project_id': self.project_id,
                'expected_state_version': self.project.status()['state_version'],
                'holdout_base64': base64.b64encode(self.holdout).decode()}

    def execute(self, request_id, method):
        context = ProjectController(self.project.root).selection_context()
        candidate = next(item for item in context['candidates'] if item['method_id'] == method)
        proposal = {'schema_version': 'project-selection-proposal-v1', 'context_sha256': context['context_sha256'],
                    'provider': {'kind': 'operator_assistant', 'label': 'Synthetic fixture'},
                    'choice': {'kind': 'execute', 'candidate_id': candidate['id']},
                    'rationale': 'Test original bounded synthetic project.', 'evidence_citation_ids': []}
        body = {'request_id': request_id, 'project_id': self.project_id,
                'expected_state_version': context['state_version'], 'proposal': proposal}
        return self.manager.advance(body), body

    def assert_code(self, code, callback, *args):
        with self.assertRaises(ResearchError) as caught:
            callback(*args)
        self.assertEqual(caught.exception.code, code)

    def test_real_registration_resume_freeze_final_and_private_report(self):
        body = self.register_body()
        before = self.project.status()['budget']
        registered = self.manager.register_holdout(body)
        self.assertEqual(registered['private_evaluation']['sha256'], hashlib.sha256(self.holdout).hexdigest())
        self.assertEqual(self.manager.register_holdout(body)['private_evaluation'], registered['private_evaluation'])
        self.assertTrue(LocalWorkbench(self.manager.root).register_holdout(body)['replayed'])
        changed = {**body, 'holdout_base64': base64.b64encode(b'{}').decode()}
        self.assert_code('IDEMPOTENCY_CONFLICT', self.manager.register_holdout, changed)
        self.assertNotIn(self.secret_text.encode(), self.manager.db.read_bytes())
        self.assertNotIn(body['holdout_base64'].encode(), self.manager.db.read_bytes())
        self.assertEqual(self.project.status()['budget'], before)
        with self.project._writer(), self.project._connect() as con:
            state = self.project._project(con)
            original = copy.deepcopy(state['private_evaluation'])
            altered = state['private_evaluation']
            altered['request']['request_id'] = [self.secret_text]
            altered['request_sha256'] = fingerprint(altered['request'])
            altered['record_sha256'] = fingerprint({k: v for k, v in altered.items() if k != 'record_sha256'})
            self.project._save(con, state)
        self.assert_code('EVIDENCE_CHANGED', collect_report, self.project.root)
        with self.project._writer(), self.project._connect() as con:
            state = self.project._project(con)
            state['private_evaluation'] = original
            self.project._save(con, state)
        primary, _ = self.execute('primary', staged.TOOL_ID)
        self.assertEqual(primary['status'], 'completed')
        action = next(a for a in self.project.status()['actions'] if a['command'] == staged.TOOL_ID)
        freeze = {'request_id': 'freeze', 'project_id': self.project_id,
                  'expected_state_version': self.project.status()['state_version'], 'primary_action_id': action['id']}
        frozen = self.manager.freeze_retrieval_strategy(freeze)
        self.assertEqual(self.manager.freeze_retrieval_strategy(freeze)['frozen_evaluation_strategy'], frozen['frozen_evaluation_strategy'])
        self.assertTrue(LocalWorkbench(self.manager.root).freeze_retrieval_strategy(freeze)['replayed'])
        self.assert_code('IDEMPOTENCY_CONFLICT', self.manager.freeze_retrieval_strategy, {**freeze, 'primary_action_id': 'other'})
        with self.project._writer(), self.project._connect() as con:
            state = self.project._project(con)
            original = copy.deepcopy(state['frozen_evaluation_strategy'])
            altered = state['frozen_evaluation_strategy']
            altered['request']['primary_action_id'] = [self.secret_text]
            altered['request_sha256'] = fingerprint(altered['request'])
            altered['record_sha256'] = fingerprint({k: v for k, v in altered.items() if k != 'record_sha256'})
            self.project._save(con, state)
        self.assert_code('EVIDENCE_CHANGED', collect_report, self.project.root)
        with self.project._writer(), self.project._connect() as con:
            state = self.project._project(con)
            state['frozen_evaluation_strategy'] = original
            self.project._save(con, state)
        private_path = self.project.root / retrieval_holdout.PRIVATE_DIR / retrieval_holdout.PRIVATE_FILE
        original_read = Path.read_bytes
        def no_early_holdout(path):
            if path == private_path:
                raise AssertionError('Report must not read final data before final execution')
            return original_read(path)
        with patch.object(Path, 'read_bytes', no_early_holdout):
            preview_report = collect_report(self.project.root)
        self.assertNotIn(self.secret_text, canonical(preview_report))
        self.assertNotIn(self.secret_query_id, canonical(preview_report))
        context = ProjectController(self.project.root).selection_context()
        self.assertNotIn(self.secret_query_id, canonical(context))
        self.assertNotIn(self.secret_text, canonical(context))
        final, final_body = self.execute('final', retrieval_holdout.FINAL_TOOL_ID)
        self.assertEqual(final['status'], 'completed')
        self.assertTrue(self.manager.advance(final_body)['replayed'])
        status = self.project.status()
        self.assertEqual(status['budget']['local_tool_calls_used'], 2)
        self.assertEqual((status['budget']['new_fits'], status['budget']['new_model_requests']), (0, 0))
        from autoresearch import project_workbench
        original_artifact = project_workbench._artifact
        final_action = next(a for a in status['actions'] if a['command'] == retrieval_holdout.FINAL_TOOL_ID)
        def leaked_artifact(project, state, action_id):
            raw = original_artifact(project, state, action_id)
            if action_id != final_action['id']:
                return raw
            envelope = json.loads(raw)
            envelope['tool_result']['result']['private_query'] = self.secret_text
            envelope['sha256'] = fingerprint({key: value for key, value in envelope.items() if key != 'sha256'})
            return canonical(envelope).encode()
        with patch.object(project_workbench, '_artifact', side_effect=leaked_artifact):
            self.assert_code('INVALID_RESULT', collect_report, self.project.root)
        self.manager.export({'request_id': 'report', 'project_id': self.project_id,
                             'expected_state_version': status['state_version']})
        report_dir = next((self.manager.root / 'reports').iterdir())
        for name in ('report.json', 'input.json', 'report.md', 'report.pdf'):
            raw = (report_dir / name).read_bytes()
            self.assertNotIn(self.secret_text.encode(), raw, name)
            self.assertNotIn(self.secret_query_id.encode(), raw, name)
            self.assertNotIn(base64.b64encode(self.holdout), raw, name)
            for private_field in self.private_fields:
                self.assertNotIn(base64.b64encode(private_field), raw, name)
        report = json.loads((report_dir / 'report.json').read_bytes())
        self.assertEqual(report['kind'], 'staged_relevance')
        self.assertEqual(report['project']['private_evaluation']['sha256'], hashlib.sha256(self.holdout).hexdigest())
        final_result = next(x for x in report['action_results'] if x['command'] == retrieval_holdout.FINAL_TOOL_ID)['tool_result']['result']
        self.assertEqual(final_result['scope']['query_count'], 1)
        self.assertEqual(final_result['freeze_sha256'], frozen['frozen_evaluation_strategy']['record_sha256'])
        self.assertEqual(len(final_result['per_query'][0]['query_id_sha256']), 64)

    def test_manager_crash_after_registration_preserves_original_and_tamper_fails(self):
        body = self.register_body()
        original = self.manager._save
        def interrupted(con, request_id, record):
            if request_id == body['request_id'] and record['status'] == 'completed':
                raise KeyboardInterrupt('fixture after project commit')
            return original(con, request_id, record)
        with patch.object(self.manager, '_save', side_effect=interrupted):
            with self.assertRaises(KeyboardInterrupt):
                self.manager.register_holdout(body)
        version = self.project.status()['state_version']
        self.assert_code('OPERATION_INCOMPLETE', self.execute, 'must-not-bypass', staged.TOOL_ID)
        self.assertEqual(self.project.status()['actions'], [])
        resumed = LocalWorkbench(self.manager.root).register_holdout(body)
        self.assertTrue(resumed['replayed'])
        self.assertEqual(self.project.status()['state_version'], version)
        private_path = self.project.root / retrieval_holdout.PRIVATE_DIR / retrieval_holdout.PRIVATE_FILE
        private_path.write_bytes(b'{}')
        self.assert_code('EVIDENCE_CHANGED', self.manager.register_holdout, body)


if __name__ == '__main__':
    unittest.main()
