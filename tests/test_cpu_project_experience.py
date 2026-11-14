"""CPU experience lifecycle using hand-authored saved values; no rank, fit or solve."""
from contextlib import ExitStack
from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

import test_saved_retrieval_reader as fixtures
from autoresearch import cpu_project_experience as experience
from autoresearch import retrieval_adapter, relevance_retrieval_adapter, scheduling_adapter, retrieval_lexical, scheduling_kernel
from autoresearch.contracts import ResearchError, canonical, fingerprint


class CPUExperienceTests(unittest.TestCase):
    def setUp(self):
        self.f = fixtures.SavedRetrievalReaderTests()
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)
        self.state = self.f.state
        self.state['code_identity'] = 'd' * 64
        self.action = self.f.primary
        # Pure arithmetic over manually authored fixture metrics, never qrel scoring.
        paired, _, adverse = retrieval_adapter._paired(self.f.primary_result['per_query_metrics'])
        self.f.primary_result['paired_summary'] = paired
        self.f.primary_result['adverse_queries'] = adverse
        self.action['dimension'] = None
        self.action['method_instance'] = {'definition_ref': {'id': retrieval_adapter.TOOL_ID, 'version': retrieval_adapter.ADAPTER_VERSION},
            'input_bindings': {'source_snapshot_sha256': self.state['source_snapshot_sha256']}, 'parameters': {},
            'evaluation_ref': 'citation-retrieval-fixed-pair-v1', 'scope': deepcopy(self.state['source_scope'])}
        request = {k: self.action[k] for k in ('project_id', 'command', 'dimension', 'source_snapshot_sha256')}
        old_id = self.action['id']
        self.action['id'] = 'action-' + fingerprint({'request_id': self.action['request_id'], **request})[:32]
        self.action['artifact'] = 'artifacts/' + self.action['id'] + '.json'
        self.action['request_sha256'] = fingerprint(request)
        envelope = self.f.envelopes.pop(old_id)
        envelope['action_id'] = self.action['id']
        envelope['request_sha256'] = self.action['request_sha256']
        self.f.envelopes[self.action['id']] = envelope
        self.f.seal(self.action)
        self.memory = experience.CPUExperienceMemory(self.f.directory / 'memory')
        self.fake = self.f.project
        self.fake.status = lambda: deepcopy(self.state)
        self.project_patch = patch.object(experience, 'ResearchProject', return_value=self.fake)
        self.project_patch.start()
        self.addCleanup(self.project_patch.stop)

    def derive(self):
        return experience.derive_cpu_observation(self.fake.root, self.action['id'])

    def card(self):
        return {'schema_version': 'research-method-card-v1', 'id': 'saved-cpu-fixture', 'version': 1,
            'question': 'What do these saved fixture values show?', 'rationale': 'Inspect a constructed saved result.',
            'scope_match': {k: self.state['source_scope'][k] for k in ('domain', 'contract')},
            'method_refs': [{'method_id': self.action['command'], 'evaluation_ref': self.action['method_instance']['evaluation_ref']}],
            'applicability': {'requires': ['Check the local context.'], 'not_applicable': ['No scientific transfer claim.'],
                              'uncertain': ['Independent validity is unreviewed.']},
            'evaluation': 'Read saved values.', 'feedback_branches': [{'id': 'adverse', 'observed': 'One saved value is lower.',
                'suggested_next': 'Inspect original evidence.', 'evidence_required': ['Original result.']}],
            'sources': [{'id': 'origin', 'url': 'urn:test:cpu-experience', 'locator': self.action['id'], 'note': 'Hand-authored fixture.'}]}

    def export(self, derived):
        return self.memory.export_case(derived['scope'], derived['entries'][0]['id'], case_id='fixture-case', version=1,
            method_card=self.card(), limitations=['Engineering fixture; no generalization.'])

    def test_capture_export_exact_recall_retire_and_reimport_without_compute(self):
        before = deepcopy(self.state)
        with ExitStack() as guards:
            for module in (retrieval_adapter, relevance_retrieval_adapter, scheduling_adapter):
                guards.enter_context(patch.object(module, 'execute', side_effect=AssertionError('no execution')))
            for module, names in ((retrieval_lexical, ('retrieve', 'build_index', 'metrics')),
                                  (scheduling_kernel, ('jobs_for', 'schedule', 'brute_force'))):
                for name in names:
                    if hasattr(module, name):
                        guards.enter_context(patch.object(module, name, side_effect=AssertionError('no calculation')))
            derived = self.derive()
            result = self.memory.import_project(self.fake.root, self.action['id'])
            self.assertEqual(self.memory.import_project(self.fake.root, self.action['id'])['inserted'], 0)
            bundle = self.export(derived)
            self.assertEqual(experience.parse_bundle(canonical(bundle).encode()), bundle)
            view = experience.summary(bundle)
        self.assertEqual(self.state, before)
        self.assertEqual(result['inserted'], 1)
        self.assertIn('binding_validation', result)
        self.assertNotIn('numerical_validation', result)
        self.assertFalse(bundle['record']['numerical_recomputation'])
        self.assertEqual(bundle['record']['provenance']['artifact'], self.f.envelopes[self.action['id']])
        self.assertEqual(bundle['record']['provenance']['source']['spec'], self.f.packet['spec'])
        self.assertNotIn('bytes_base64', canonical(bundle['record']['provenance']['source']['assets']))
        self.assertEqual(view['transfer_scope'], 'analogy_not_current_evidence')
        self.assertNotIn('\"rankings\":[', canonical(view))
        self.assertEqual(view['observation']['kind'], 'saved_cpu_fixed_pair')
        self.assertLess(len(canonical(view).encode()), 65536)
        self.assertEqual(len(self.memory.recall(derived['scope'])['entries']), 1)
        self.assertEqual(self.memory.recall({**derived['scope'], 'inputs_sha256': '0'*64})['entries'], [])
        self.memory.set_status(derived['entries'][0]['id'], 'retired', 'Review', 'retire-fixture')
        self.memory.import_project(self.fake.root, self.action['id'])
        self.assertEqual(self.memory.recall(derived['scope'])['entries'], [])
        with self.assertRaises(ResearchError): self.export(derived)
        self.assertEqual(experience.validate_bundle(bundle), bundle)

    def test_reject_action_mismatch_and_unfinished_without_reading(self):
        for command, status in ((retrieval_adapter.AUDIT_TOOL_ID, 'completed'), ('unknown', 'completed'),
                                (retrieval_adapter.TOOL_ID, 'unknown'), (retrieval_adapter.TOOL_ID, 'running')):
            self.action['command'], self.action['status'] = command, status
            with patch.object(experience.source_reader, '_read_file', side_effect=AssertionError('no source read')):
                with self.assertRaises(ResearchError): self.derive()
        self.action['command'], self.action['status'] = retrieval_adapter.TOOL_ID, 'completed'
        self.action['method_instance']['parameters'] = {'extra': 1}
        with self.assertRaises(ResearchError): self.derive()

    def test_offline_rejects_changed_binding_spec_result_and_card(self):
        derived = self.derive()
        self.memory.import_project(self.fake.root, self.action['id'])
        bundle = self.export(derived)
        for mutate in ('spec', 'result', 'request', 'producer', 'card', 'kind', 'source'):
            bad = deepcopy(bundle)
            record = bad['record']
            p = record['provenance']
            if mutate == 'spec': p['source']['spec']['query_splits']['dev'].append('forged')
            if mutate == 'result': p['artifact']['tool_result']['result']['rankings'].pop()
            if mutate == 'request': p['action']['request_sha256'] = '0'*64
            if mutate == 'producer': p['origin']['producer_code_identity'] = '0'*64
            if mutate == 'card': bad['method_card']['scope_match']['domain'] = 'algorithm'
            if mutate == 'kind': record['kind'] = 'fit_observation'
            if mutate == 'source': p['source']['assets']['corpus']['sha256'] = '0'*64
            with self.subTest(mutate=mutate), self.assertRaises(ResearchError): experience.validate_bundle(bad)
        with patch.object(experience, 'MAX_BUNDLE_BYTES', 10):
            with self.assertRaises(ResearchError) as caught: experience.validate_bundle(bundle)
            self.assertEqual(caught.exception.code, 'BUNDLE_TOO_LARGE')
        with self.assertRaises(ResearchError): experience.parse_bundle(b'{"duplicate": 1, "duplicate": 2}')

    def test_request_id_cannot_be_changed_independently_of_native_action_id(self):
        derived = self.derive()
        self.memory.import_project(self.fake.root, self.action['id'])
        bundle = self.export(derived)
        bundle['record']['provenance']['action']['request_id'] = 'request-other'
        with self.assertRaises(ResearchError): experience.validate_bundle(bundle)
        self.action['request_id'] = 'request-other'
        with self.assertRaises(ResearchError): self.derive()

    def test_resealed_but_inconsistent_saved_summaries_and_coverage_are_rejected(self):
        derived = self.derive()
        self.memory.import_project(self.fake.root, self.action['id'])
        original = self.export(derived)
        for change in ('adverse', 'summary', 'coverage'):
            bundle = deepcopy(original)
            record = bundle['record']
            p = record['provenance']
            saved = p['artifact']['tool_result']['result']
            if change == 'adverse': saved['adverse_queries'].pop()
            if change == 'summary': saved['paired_summary']['splits']['dev']['arms']['bm25']['queries'] += 1
            if change == 'coverage':
                saved['rankings'].pop()
                saved['rankings_before_scoring_sha256'] = fingerprint(saved['rankings'])
            p['artifact']['sha256'] = fingerprint({k: v for k, v in p['artifact'].items() if k != 'sha256'})
            p['action']['result_sha256'] = p['artifact']['sha256']
            record['scope']['inputs_sha256'] = fingerprint({'result_sha256': p['artifact']['sha256'], 'retained_source_sha256': fingerprint(p['source'])})
            record['payload']['paired_summary'] = saved['paired_summary']
            from autoresearch.research_memory import observation_id
            record['id'] = observation_id(record)
            with self.subTest(change=change), self.assertRaises(ResearchError): experience.validate_bundle(bundle)

    def test_resealed_spec_and_asset_reference_cannot_keep_original_scope(self):
        import base64
        import hashlib
        derived = self.derive()
        self.memory.import_project(self.fake.root, self.action['id'])
        original = self.export(derived)
        for field in ('source_url', 'attribution'):
            bundle = deepcopy(original)
            source = bundle['record']['provenance']['source']
            source['spec'][field] = 'Changed but syntactically valid provenance'
            raw = canonical(source['spec']).encode()
            source['spec_source'].update(bytes=len(raw), bytes_base64=base64.b64encode(raw).decode(),
                                         sha256=hashlib.sha256(raw).hexdigest())
            with self.subTest(field=field), self.assertRaises(ResearchError): experience.validate_bundle(bundle)
        bundle = deepcopy(original)
        bundle['record']['provenance']['source']['assets']['corpus']['sha256'] = 'f'*64
        with self.assertRaises(ResearchError): experience.validate_bundle(bundle)

    def test_cli_export_validate_summary_and_exact_recall(self):
        derived = self.derive()
        self.memory.import_project(self.fake.root, self.action['id'])
        directory = self.f.directory
        for name, value in (('scope', derived['scope']), ('card', self.card()),
                            ('limitations', {'limitations': ['Constructed fixture only.']})):
            (directory / (name + '.json')).write_text(canonical(value), encoding='utf-8')
        script = Path(__file__).resolve().parents[1] / 'scripts' / 'cpu_project_experience.py'
        def run(*args):
            proc = subprocess.run([sys.executable, str(script), *map(str, args)], capture_output=True, text=True)
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            return json.loads(proc.stdout)
        case = directory / 'case.json'
        run('export', '--memory', self.memory.root, '--scope', directory/'scope.json', '--entry-id',
            derived['entries'][0]['id'], '--case-id', 'cli-fixture', '--version', '1', '--method-card',
            directory/'card.json', '--limitations', directory/'limitations.json', '--output', case)
        self.assertTrue(run('validate', '--bundle', case)['valid'])
        self.assertEqual(run('summary', '--bundle', case)['case_id'], 'cli-fixture')
        self.assertEqual(len(run('recall', '--memory', self.memory.root, '--scope', directory/'scope.json')['entries']), 1)

    def test_cli_rejects_output_above_actual_byte_limit_before_write(self):
        import importlib.util
        path = Path(__file__).resolve().parents[1] / 'scripts' / 'cpu_project_experience.py'
        spec = importlib.util.spec_from_file_location('cpu_experience_cli', path)
        cli = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cli)
        destination = self.f.directory / 'oversized.json'
        args = ['cpu_project_experience.py', 'export', '--memory', str(self.memory.root), '--scope', 'scope',
                '--entry-id', 'entry', '--case-id', 'case', '--version', '1', '--method-card', 'card',
                '--limitations', 'limitations', '--output', str(destination)]
        with patch.object(cli, 'MAX_BUNDLE_BYTES', 10), patch.object(cli, 'document', return_value={'limitations': []}), \
                patch.object(cli, 'CPUExperienceMemory') as memory, patch.object(sys, 'argv', args):
            memory.return_value.export_case.return_value = {'payload': 'more than ten bytes'}
            self.assertEqual(cli.main(), 2)
        self.assertFalse(destination.exists())

    def test_project_change_during_capture_is_rejected(self):
        calls = iter((deepcopy(self.state), {**deepcopy(self.state), 'state_version': 14}))
        self.fake.status = lambda: next(calls)
        with self.assertRaises(ResearchError) as caught: self.derive()
        self.assertEqual(caught.exception.code, 'STALE_STATE')

    def test_runtime_change_during_capture_is_rejected(self):
        with patch.object(experience, 'runtime_code_identity', side_effect=['a'*64, 'b'*64]):
            with self.assertRaises(ResearchError) as caught: self.derive()
        self.assertEqual(caught.exception.code, 'STALE_STATE')

    def test_cli_help_is_available(self):
        script = Path(__file__).resolve().parents[1] / 'scripts' / 'cpu_project_experience.py'
        result = subprocess.run([sys.executable, str(script), '--help'], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('import-project', result.stdout)


if __name__ == '__main__': unittest.main()
