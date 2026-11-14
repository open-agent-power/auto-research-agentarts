"""Staged history uses existing target references without granting authority."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import test_staged_project_experience as source_fixtures
import test_retrieval_holdout as target_fixtures
from autoresearch import project_experience_dispatch as dispatch, project_selection, project_report
from autoresearch import staged_project_experience as staged_history, retrieval_lexical
from autoresearch.contracts import ResearchError, canonical
from autoresearch.project_controller import ProjectController


class StagedExperienceBindingTests(unittest.TestCase):
    setup_source = source_fixtures.StagedExperienceTests.setup_source
    card = staticmethod(source_fixtures.StagedExperienceTests.card)

    def test_native_target_import_reference_report_and_retirement_preserve_authority(self):
        source, primary, memory = self.setup_source()
        source_before = source.status()
        imported = memory.import_project(source.root, primary['id'])
        record = memory.recall(imported['scope'])['entries'][0]['record']
        bundle = memory.export_case(imported['scope'], record['id'], case_id='staged-history', version=1,
                                   method_card=self.card(), limitations=['Synthetic source, historical analogy only.'])
        raw = canonical(bundle).encode()
        self.assertEqual(dispatch.parse_bundle(raw), bundle)
        self.assertEqual(dispatch.summary(bundle)['observation']['kind'], 'saved_staged_retrieval')
        helper = target_fixtures.RetrievalHoldoutTests()
        self.addCleanup(helper.doCleanups)
        target, _, _ = helper.fixture()
        controller = ProjectController(target.root)
        before = controller.selection_context()
        body = {'request_id': 'include-history', 'expected_state_version': target.status()['state_version'],
                'bundle': raw, 'reason': 'Advisory source example, no target scientific claim.'}
        revision = target.import_experience(**body)
        after_import = target.status()
        self.assertEqual(target.import_experience(**body), revision)
        context = controller.selection_context()
        for key in ('budget', 'candidates', 'conditions', 'evidence', 'baseline_decision'):
            self.assertEqual(context[key], before[key], key)
        case, = context['experience']['cases']
        self.assertEqual(case['association']['status'], 'applicable')
        self.assertEqual(case['transfer_scope'], 'analogy_not_current_evidence')
        refs = project_selection.active_experience_case_refs(context)
        proposal = {'schema_version': 'project-selection-proposal-v1', 'context_sha256': context['context_sha256'],
                    'provider': {'kind': 'operator_assistant', 'label': 'Engineering reference validation'},
                    'choice': {'kind': 'wait'}, 'rationale': 'Retain historical negative result without dispatch.',
                    'evidence_citation_ids': [], 'experience_case_refs': refs}
        project_selection.validate_proposal(context, proposal)
        with patch.object(retrieval_lexical, 'retrieve', side_effect=AssertionError('No new retrieval')):
            output = Path(self.enterContext(tempfile.TemporaryDirectory())) / 'report'
            manifest = project_report.export_report(workspace=target.root, output=output)
        report = json.loads((output / 'report.json').read_bytes())
        self.assertEqual(report['experience_cases'][0]['observation']['kind'], 'saved_staged_retrieval')
        text = (output / 'report.md').read_text()
        self.assertIn('最终为基线单臂一次计算', text)
        self.assertIn('历史参照', text)
        self.assertEqual(target.status(), after_import)
        self.assertEqual(manifest['project_id'], target.status()['id'])
        target.set_experience_status(request_id='retire-history', expected_state_version=target.status()['state_version'],
                                     case_id='staged-history', status='retired', reason='Explicit local retirement.')
        retired = target.status()
        self.assertNotIn('experience', controller.selection_context())
        self.assertEqual(target.import_experience(**body), revision)
        self.assertEqual(target.status(), retired)
        self.assertEqual(target.status()['budget'], after_import['budget'])
        self.assertEqual(source.status(), source_before)
        with self.assertRaises(ResearchError):
            target.import_experience(**{**body, 'reason': 'Changed original request.'})


if __name__ == '__main__':
    unittest.main()
