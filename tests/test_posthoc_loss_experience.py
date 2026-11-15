"""Synthetic published-aggregate binding; never load original research data."""
import copy
import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from autoresearch import posthoc_loss_experience as loss, project_experience_dispatch as dispatch
from autoresearch import project_report, research_plan_proposal
from autoresearch.contracts import ResearchError, canonical
from autoresearch.project_controller import ProjectController
from autoresearch.research_project import code_identity
import test_retrieval_holdout as fixtures
import test_staged_project_experience as staged_fixtures


class PosthocLossTests(unittest.TestCase):
    def setUp(self):
        self.tmp = self.enterContext(tempfile.TemporaryDirectory())
        cases = copy.deepcopy(loss.CASES)
        for name, value in cases.items():
            value.update(project_id='project-synthetic-' + name, run_id='run-synthetic-' + name,
                         primary_action_id='action-synthetic-' + name, count=6, mean_mrr_loss=0.125)
        self.enterContext(patch.object(loss, 'CASES', cases))
        rows = [loss._projection(name) for name in cases]
        protocol = {'schema_version': 'saved-validation-unchanged-recall-mrr-loss-protocol-v1',
                    'split': 'validation', 'direction': loss.SELECTOR['direction'], 'epsilon': 1e-12,
                    'cases': [{**{k: row[k] for k in ('project_id', 'run_id', 'primary_action_id', 'primary_result_sha256',
                                                        'source_snapshot_sha256', 'source_commit', 'producer_core')},
                               'label': row['case']} for row in rows]}
        self.protocol = canonical(protocol).encode()
        self.enterContext(patch.object(loss, 'PROTOCOL_SHA256', hashlib.sha256(self.protocol).hexdigest()))
        result = {'schema_version': 'saved-unchanged-recall-mrr-loss-v1', 'cases': rows,
                  'protocol_sha256': loss.PROTOCOL_SHA256, 'script_sha256': loss.READER_SHA256,
                  'reader_commit': loss.READER_COMMIT}
        self.result = canonical(result).encode()
        self.enterContext(patch.object(loss, 'RESULT_SHA256', hashlib.sha256(self.result).hexdigest()))

    def bundle(self, name='S065'):
        memory = loss.PosthocLossExperienceMemory(Path(self.tmp) / ('memory-' + name))
        receipt = memory.import_published(self.result, self.protocol, name)
        self.assertEqual(receipt['inserted'], 1)
        self.assertEqual(memory.import_published(self.result, self.protocol, name)['inserted'], 0)
        entry = memory.recall(receipt['scope'])['entries'][0]['record']
        return memory.export_case(receipt['scope'], entry['id'], case_id='posthoc-' + name, version=1,
                                  method_card=staged_fixtures.StagedExperienceTests.card(), limitations=['Synthetic only.'])

    def test_separate_binding_and_tamper_rejected(self):
        bundle = self.bundle()
        view = dispatch.summary(dispatch.parse_bundle(canonical(bundle).encode()))
        self.assertEqual(view['observation']['cell']['count'], 6)
        self.assertEqual(view['origin_evidence']['source_commit'], loss.CASES['S065']['source_commit'])
        self.assertEqual(view['origin_evidence']['producer_core'], loss.PRODUCER_CORE)
        self.assertEqual(view['origin_evidence']['primary_artifact_sha256'], loss.CASES['S065']['primary_artifact_sha256'])
        self.assertIn('no_recomputation_or_signature', view['observation']['verification'])
        self.assertNotIn('project-synthetic-S067', canonical(bundle))
        self.assertFalse(bundle['record']['numerical_recomputation'])
        self.assertEqual(bundle['record']['provenance']['action_role'], 'upstream_primary_reference_not_audit_producer')
        self.assertEqual(bundle['record']['payload']['limitations'], [loss.NOTICE])
        self.assertEqual(view['origin_evidence']['action_role'], 'upstream_primary_reference_not_audit_producer')
        for path, value in [(['payload', 'cell', 'count'], True), (['payload', 'cell', 'mean_mrr_loss'], 0.25),
                            (['provenance', 'action_id'], 'action-other'), (['payload', 'selector', 'epsilon'], 1),
                            (['provenance', 'action_role'], 'audit_producer'), (['payload', 'limitations'], [])]:
            changed = copy.deepcopy(bundle)
            node = changed['record']
            for key in path[:-1]: node = node[key]
            node[path[-1]] = value
            with self.subTest(path=path), self.assertRaises(ResearchError): dispatch.validate_bundle(changed)
        with self.assertRaises(ResearchError): loss.derive_published(self.result + b' ', self.protocol, 'S065')
        with self.assertRaises(ResearchError): loss.derive_published(self.result, self.protocol + b' ', 'S065')

    def test_each_case_is_separately_scoped_and_published_rows_must_match(self):
        left, right = self.bundle('S065'), self.bundle('S067')
        self.assertNotEqual(left['record']['id'], right['record']['id'])
        self.assertNotEqual(left['record']['scope'], right['record']['scope'])
        self.assertNotIn('project-synthetic-S065', canonical(right))
        changed = __import__('json').loads(self.result)
        changed['cases'][0]['primary_action_id'] = 'action-other'
        raw = canonical(changed).encode()
        with patch.object(loss, 'RESULT_SHA256', hashlib.sha256(raw).hexdigest()):
            with self.assertRaises(ResearchError): loss.derive_published(raw, self.protocol, 'S065')

    def test_parser_identity_is_in_project_and_report_closure(self):
        original_read = Path.read_bytes
        original_core = code_identity()
        original_report = project_report.recovery_source_identity('tabular')
        def changed(path):
            raw = original_read(path)
            return raw + b'\n# synthetic drift' if path.resolve() == Path(loss.__file__).resolve() else raw
        with patch.object(Path, 'read_bytes', changed):
            self.assertNotEqual(code_identity(), original_core)
            self.assertNotEqual(project_report.recovery_source_identity('tabular'), original_report)

    def test_project_plan_context_report_and_replay(self):
        bundle = self.bundle()
        helper = fixtures.RetrievalHoldoutTests()
        self.addCleanup(helper.doCleanups)
        target, _, _ = helper.fixture()
        before = target.status()
        body = {'request_id': 'posthoc-import', 'expected_state_version': before['state_version'],
                'bundle': canonical(bundle).encode(), 'reason': 'Synthetic historical reference.'}
        revision = target.import_experience(**body)
        self.assertEqual(target.import_experience(**body), revision)
        after = target.status()
        self.assertEqual(after['budget'], before['budget'])
        context = ProjectController(target.root).selection_context()
        case = context['experience']['cases'][0]
        self.assertEqual(case['observation']['kind'], 'posthoc_validation_loss')
        self.assertEqual(case['bundle_sha256'], revision['bundle_sha256'])
        self.assertEqual(research_plan_proposal.build_context(target)['selection_context']['experience']['cases'][0], case)
        plan = {'question': 'Synthetic next question?', 'basis': 'Historical only.', 'steps': 'Review.',
                'expected_feedback': 'No execution.', 'experience_case_refs': {'schema_version': 'project-plan-experience-refs-v1',
                    'items': [{'case_id': bundle['id'], 'case_version': 1, 'bundle_sha256': revision['bundle_sha256'],
                               'applicability_statement': 'Operator reference; transfer not established.'}]}}
        target.save_plan(request_id='posthoc-plan', expected_state_version=after['state_version'], plan=plan, reason='Synthetic.')
        rows = project_report._experience_rows({'experience_cases': [case]})
        self.assertIn('事后', canonical(rows))
        self.assertIn('0.1250', canonical(rows))
        report = project_report.collect_report(target.root)
        self.assertIn('0.1250', project_report._markdown(report))
        self.assertTrue(project_report._pdf(report).startswith(b'%PDF'))
        self.assertEqual(target.status()['budget'], before['budget'])


if __name__ == '__main__': unittest.main()
