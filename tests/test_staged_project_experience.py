"""Synthetic staged experience: original native lifecycle, then read-only capture."""
from contextlib import ExitStack
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from autoresearch import relevance_retrieval_adapter as relevance, retrieval_lexical as lexical
from autoresearch import retrieval_holdout as holdout, staged_relevance_adapter as staged
from autoresearch.contracts import ResearchError, canonical, fingerprint
from autoresearch.project_controller import ProjectController
from autoresearch.research_project import ResearchProject
import test_retrieval_holdout as fixtures

from autoresearch import staged_project_experience as experience


class StagedExperienceTests(unittest.TestCase):
    def setup_source(self, sign='negative'):
        helper = fixtures.RetrievalHoldoutTests()
        project, _, raw = helper.fixture(sign)
        self.addCleanup(helper.doCleanups)
        helper.register(project, raw)
        controller = ProjectController(project.root)
        def advance(method, request):
            context = controller.selection_context()
            candidate = next(c for c in context['candidates'] if c['method_id'] == method)
            proposal = {'schema_version': 'project-selection-proposal-v1', 'context_sha256': context['context_sha256'],
                        'provider': {'kind': 'human', 'label': 'Synthetic fixture'},
                        'choice': {'kind': 'execute', 'candidate_id': candidate['id']},
                        'rationale': 'Synthetic engineering test', 'evidence_citation_ids': []}
            return controller.advance_selection(request_id=request, proposal=proposal, expected_state_version=context['state_version'])
        self.assertEqual(advance(staged.TOOL_ID, 'primary')['status'], 'completed')
        primary = project.status()['actions'][0]
        self.assertEqual(advance(staged.AUDIT_TOOL_ID, 'audit')['status'], 'completed')
        holdout.freeze_strategy(project, request_id='freeze', expected_state_version=project.status()['state_version'], primary_action_id=primary['id'])
        self.assertEqual(advance(holdout.FINAL_TOOL_ID, 'final')['status'], 'completed')
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        return project, primary, experience.StagedExperienceMemory(Path(tmp.name) / 'memory')

    @staticmethod
    def card():
        return {'schema_version': 'research-method-card-v1', 'id': 'staged-fixture', 'version': 1,
                'question': 'What did the fixed fixture show?', 'rationale': 'A saved engineering comparison.',
                'scope_match': {'domain': 'retrieval', 'contract': staged.CONTRACT},
                'method_refs': [{'method_id': staged.TOOL_ID, 'evaluation_ref': experience.EVALUATION}],
                'applicability': {'requires': ['Check task alignment.'], 'not_applicable': ['Not evidence for the new task.'],
                                  'uncertain': ['External validity is unreviewed.']},
                'evaluation': 'Saved validation and final aggregate.',
                'feedback_branches': [{'id': 'bad', 'observed': 'A saved candidate loss.', 'suggested_next': 'Inspect evidence.',
                                       'evidence_required': ['Original saved action.']}],
                'sources': [{'id': 'source', 'url': 'urn:test:fixture', 'locator': 'synthetic', 'note': 'Fixture only.'}]}

    def case(self, memory, derived):
        return memory.export_case(derived['scope'], derived['entries'][0]['id'], case_id='case-1', version=1,
                                  method_card=self.card(), limitations=['Synthetic fixture; not independently reviewed.'])

    def test_real_native_source_to_binding_memory_without_research_or_final_data(self):
        project, primary, memory = self.setup_source()
        before = project.status()
        initial_db = hashlib.sha256(project.db.read_bytes()).hexdigest()
        with ExitStack() as guards:
            original_open = Path.open
            def refuse_private(path, *args, **kwargs):
                if 'private_evaluation' in path.parts:
                    raise AssertionError('no private file reads during capture')
                return original_open(path, *args, **kwargs)
            guards.enter_context(patch.object(Path, 'open', refuse_private))
            for obj, name in ((relevance, 'retrieve'), (lexical, 'retrieve'), (lexical, 'metrics'),
                              (lexical, 'build_index'), (staged, 'execute'), (holdout, '_verified_private'),
                              (ResearchProject, 'step'), (ProjectController, 'advance_selection')):
                guards.enter_context(patch.object(obj, name, side_effect=AssertionError('no new execution or private read')))
            derived = experience.derive_staged_observation(project.root, primary['id'])
            imported = memory.import_project(project.root, primary['id'])
            self.assertEqual(memory.import_project(project.root, primary['id'])['inserted'], 0)
            bundle = self.case(memory, derived)
            self.assertEqual(experience.parse_bundle(canonical(bundle).encode()), bundle)
            view = experience.summary(bundle)
        self.assertEqual(project.status(), before)
        self.assertEqual(hashlib.sha256(project.db.read_bytes()).hexdigest(), initial_db)
        self.assertEqual(imported['inserted'], 1)
        self.assertEqual(view['transfer_scope'], 'analogy_not_current_evidence')
        self.assertEqual(view['observation']['kind'], 'saved_staged_retrieval')
        self.assertEqual(view['observation']['paired_summary']['splits']['validation']['paired_candidate_minus_baseline']['recall@20']['mean'], -1)
        final = view['observation']['final']
        self.assertEqual(final['selected_method'], 'bm25')
        self.assertEqual(final['comparison_status'], 'selected_equals_baseline_single_computation')
        self.assertIn('offline_final_binding_unverifiable_without_origin', final['verification'])
        all_text = canonical(bundle)
        for forbidden in ('SECRET_FINAL_QUERY', 'final-q', hashlib.sha256(b'final-q').hexdigest(), 'queries_jsonl', 'qrels_tsv', 'per_query":'):
            self.assertNotIn(forbidden, all_text)
        self.assertNotIn('bytes_base64', canonical(bundle['record']['provenance']['source']['assets']))
        self.assertLess(len(canonical(view).encode()), 64 * 1024)
        self.assertEqual(len(memory.recall(derived['scope'])['entries']), 1)
        memory.set_status(derived['entries'][0]['id'], 'retired', 'review', 'retire-1')
        self.assertEqual(memory.import_project(project.root, primary['id'])['inserted'], 0)
        self.assertEqual(memory.recall(derived['scope'])['entries'], [])
        with self.assertRaises(ResearchError):
            self.case(memory, derived)

    def test_positive_and_zero_preserve_observed_final_semantics(self):
        for sign, expected_method, expected_status in (('positive','tfidf_cosine','distinct_selected_and_baseline'),
                                                        (None,'bm25','selected_equals_baseline_single_computation')):
            with self.subTest(sign=sign):
                project, primary, memory = self.setup_source(sign)
                result = experience.derive_staged_observation(project.root, primary['id'])
                memory.import_project(project.root, primary['id'])
                final = experience.summary(self.case(memory, result))['observation']['final']
                self.assertEqual((final['selected_method'], final['comparison_status']), (expected_method, expected_status))
                self.assertEqual(final['usage']['ranking_calls'], 2 if sign == 'positive' else 1)

    def test_original_tamper_and_incomplete_are_rejected(self):
        project, primary, _ = self.setup_source()
        before = project.status()
        for action in before['actions']:
            artifact = project._artifact(action)
            original = artifact.read_bytes()
            data = json.loads(original)
            data['tool_result']['status'] = 'failed'
            artifact.write_text(canonical(data))
            with self.subTest(stage=action['command']), self.assertRaises(ResearchError):
                experience.derive_staged_observation(project.root, primary['id'])
            artifact.write_bytes(original)
        with self.assertRaises(ResearchError):
            experience.derive_staged_observation(project.root, 'no-such-action')

    def test_offline_rejects_corruption_extra_final_rows_and_bad_card(self):
        project, primary, memory = self.setup_source()
        derived = experience.derive_staged_observation(project.root, primary['id'])
        memory.import_project(project.root, primary['id'])
        original = self.case(memory, derived)
        for mutation in ('artifact','summary','freeze','request','parent','final_rows','card','kind'):
            bundle = copy.deepcopy(original)
            record = bundle['record']
            p = record['provenance']
            if mutation == 'artifact': p['artifacts']['primary']['tool_result']['result']['rankings'].pop()
            if mutation == 'summary': record['payload']['paired_summary']['splits']['validation']['paired_candidate_minus_baseline']['recall@20']['mean'] = 1
            if mutation == 'freeze': p['freeze']['selected_method'] = 'tfidf_cosine'
            if mutation == 'request': p['actions']['audit']['request_sha256'] = '0' * 64
            if mutation == 'parent': p['parent_bindings']['final']['child_request_id'] = 'other'
            if mutation == 'final_rows': record['payload']['final']['per_query'] = [{'query_id_sha256': '0' * 64}]
            if mutation == 'card': bundle['method_card']['scope_match']['domain'] = 'other'
            if mutation == 'kind': record['kind'] = 'fit_observation'
            with self.subTest(mutation=mutation), self.assertRaises(ResearchError):
                experience.validate_bundle(bundle)
        with patch.object(experience, 'MAX_BUNDLE_BYTES', 10):
            with self.assertRaises(ResearchError): experience.validate_bundle(original)
        with self.assertRaises(ResearchError): experience.parse_bundle(b'{"a":1,"a":2}')

    def test_old_producer_pin_can_be_captured_with_a_different_runtime(self):
        project, primary, memory = self.setup_source()
        original_identity = project.status()['code_identity']
        with patch.object(experience, 'runtime_code_identity', return_value='e' * 64):
            result = experience.derive_staged_observation(project.root, primary['id'])
        origin = result['entries'][0]['provenance']['origin']
        self.assertEqual(origin['producer_code_identity'], original_identity)
        self.assertEqual(origin['registered_project_code_identity'], original_identity)
        self.assertEqual(origin['capture_runtime_code_identity'], 'e' * 64)
        self.assertEqual(project.status()['code_identity'], original_identity)

    def test_rehashed_injected_metadata_rejected_offline(self):
        project, primary, memory = self.setup_source()
        result = experience.derive_staged_observation(project.root, primary['id'])
        memory.import_project(project.root, primary['id'])
        original = self.case(memory, result)
        for target in ('registration_extra', 'registration_nested', 'freeze_request', 'final_action_extra', 'audit_tool_extra'):
            bundle = copy.deepcopy(original)
            p = bundle['record']['provenance']
            reg, frozen = p['holdout_registration'], p['freeze']
            if target == 'registration_extra': reg['leak'] = ['hidden']
            if target == 'registration_nested': reg['bytes'] = {'content': 'hidden'}
            if target == 'freeze_request': frozen['request']['extra'] = ['hidden']
            if target == 'final_action_extra': p['actions']['final']['leak'] = {'qid': 'hidden'}
            if target == 'audit_tool_extra': p['artifacts']['audit']['tool_result']['result']['leak'] = ['hidden']
            if target.startswith('registration'):
                reg['record_sha256'] = fingerprint({k: v for k, v in reg.items() if k != 'record_sha256'})
                frozen['holdout_record_sha256'] = reg['record_sha256']
            frozen['request_sha256'] = fingerprint(frozen['request'])
            frozen['record_sha256'] = fingerprint({k: v for k, v in frozen.items() if k != 'record_sha256'})
            with self.subTest(target=target), self.assertRaises(ResearchError):
                experience.validate_bundle(bundle)

    def test_rehashed_wrong_parent_context_rejected_during_capture(self):
        project, primary, _ = self.setup_source()
        before = project.status()
        forged = copy.deepcopy(before)
        parent = forged['controller_requests'][0]
        parent['decision']['selection_ref']['candidate_id'] = 'choice-forged'
        parent['decision_sha256'] = fingerprint(parent['decision'])
        with patch.object(experience.ResearchProject, 'status', return_value=forged):
            with self.assertRaises(ResearchError):
                experience.derive_staged_observation(project.root, primary['id'])

    def test_resealed_audit_and_freeze_injection_fail_validation(self):
        from autoresearch.research_memory import observation_id
        project, primary, memory = self.setup_source()
        derived = experience.derive_staged_observation(project.root, primary['id'])
        memory.import_project(project.root, primary['id'])
        original = self.case(memory, derived)
        for mutation in ('audit_extra', 'freeze_extra'):
            bundle = copy.deepcopy(original)
            record, p = bundle['record'], bundle['record']['provenance']
            if mutation == 'audit_extra':
                env = p['artifacts']['audit']
                env['tool_result']['result']['forged_final_query'] = 'hidden'
                env['sha256'] = fingerprint({k: v for k, v in env.items() if k != 'sha256'})
                p['actions']['audit']['result_sha256'] = env['sha256']
                p['artifact_file_sha256']['audit'] = hashlib.sha256(canonical(env).encode()).hexdigest()
            else:
                p['freeze']['forged_final_query'] = 'hidden'
                p['freeze']['record_sha256'] = fingerprint({k: v for k, v in p['freeze'].items() if k != 'record_sha256'})
            scope = record['scope']
            scope['inputs_sha256'] = fingerprint({'primary': p['actions']['primary']['result_sha256'],
                'audit': p['actions']['audit']['result_sha256'], 'final': p['actions']['final']['result_sha256'],
                'source': fingerprint(p['source']), 'freeze': p['freeze']['record_sha256']})
            record['id'] = observation_id(record)
            with self.subTest(mutation=mutation), self.assertRaises(ResearchError):
                experience.validate_bundle(bundle)

    def test_each_action_database_fingerprint_column_is_required(self):
        import sqlite3
        project, primary, _ = self.setup_source()
        before = project.status()
        source = project.root / 'source.json'
        source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
        artifacts = {a['id']: hashlib.sha256(project._artifact(a).read_bytes()).hexdigest() for a in before['actions']}
        for action in before['actions']:
            with self.subTest(action=action['command']):
                with sqlite3.connect(project.db) as con:
                    con.execute('UPDATE actions SET fingerprint=? WHERE request_id=?', ('0' * 64, action['request_id']))
                self.assertEqual(project.status(), before)  # status alone does not project the fingerprint column.
                tampered_db_hash = hashlib.sha256(project.db.read_bytes()).hexdigest()
                with patch.object(relevance, 'retrieve', side_effect=AssertionError('no ranking')), \
                     patch.object(lexical, 'metrics', side_effect=AssertionError('no scoring')), \
                     patch.object(holdout, '_verified_private', side_effect=AssertionError('no private read')):
                    with self.assertRaises(ResearchError) as error:
                        experience.derive_staged_observation(project.root, primary['id'])
                self.assertEqual(error.exception.code, 'EVIDENCE_CHANGED')
                self.assertEqual(project.status(), before)
                self.assertEqual(hashlib.sha256(project.db.read_bytes()).hexdigest(), tampered_db_hash)
                self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(), source_hash)
                self.assertEqual({a['id']: hashlib.sha256(project._artifact(a).read_bytes()).hexdigest() for a in before['actions']}, artifacts)
                with sqlite3.connect(project.db) as con:
                    con.execute('UPDATE actions SET fingerprint=? WHERE request_id=?', (action['request_sha256'], action['request_id']))

    def test_resealed_parent_context_must_match_original_registration_and_freeze(self):
        project, primary, _ = self.setup_source()
        before = project.status()
        targets = (('primary', 'holdout'), ('audit', 'holdout'), ('final', 'holdout'),
                   ('primary', 'query_count'), ('primary', 'snapshot'), ('primary', 'plan'),
                   ('primary', 'scope'), ('final', 'freeze_sha'), ('final', 'frozen_choice'))
        for phase, mutation in targets:
            forged = copy.deepcopy(before)
            parent = next(p for p in forged['controller_requests'] if p['request_id'] == phase)
            ctx = parent['selection_context']
            if mutation == 'holdout': ctx['staged_evaluation']['holdout_sha256'] = '0' * 64
            if mutation == 'query_count': ctx['staged_evaluation']['query_count'] += 1
            if mutation == 'snapshot': ctx['snapshot_ref'] = '1' * 64
            if mutation == 'plan': ctx['research_plan']['question'] = 'Different but valid question?'
            if mutation == 'scope': ctx['domain_scope']['dataset_label'] = 'Different but valid dataset'
            if mutation == 'freeze_sha': ctx['staged_evaluation']['freeze']['freeze_sha256'] = '2' * 64
            if mutation == 'frozen_choice':
                ctx['staged_evaluation']['freeze']['validation_delta_recall20'] = 0.5
                ctx['staged_evaluation']['freeze']['selected_method'] = 'tfidf_cosine'
            ctx['context_sha256'] = fingerprint({k: v for k, v in ctx.items() if k != 'context_sha256'})
            parent['request']['proposal']['context_sha256'] = ctx['context_sha256']
            parent['request_sha256'] = fingerprint(parent['request'])
            parent['decision']['selection_ref']['context_sha256'] = ctx['context_sha256']
            parent['decision_sha256'] = fingerprint(parent['decision'])
            with self.subTest(phase=phase, mutation=mutation), \
                 patch.object(experience.ResearchProject, 'status', return_value=forged):
                with self.assertRaises(ResearchError) as error:
                    experience.derive_staged_observation(project.root, primary['id'])
                self.assertEqual(error.exception.code, 'EVIDENCE_CHANGED')
