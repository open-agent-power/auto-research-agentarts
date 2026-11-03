import copy
import hashlib
import json
import math
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from autoresearch import c01
from autoresearch.c01_research import C01Research, control_review_state
from autoresearch.contracts import ResearchError, canonical, fingerprint
from autoresearch.knowledge import build_index
from autoresearch.knowledge import KnowledgeIndex
from test_knowledge import doc


class C01ResearchTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.index = self.root / 'index.sqlite'
        build_index([doc('note', 'C01 aggregate alloy records are exploratory; failed predictions require review.', kind='reuse_note')], self.index)
        samples = []
        for i in range(8):
            row = {'sample_id': 'Alloy ' + str(i+1)}
            row.update({feature: float((i+1)**(j%2+1)) for j, feature in enumerate(c01.FEATURES)})
            row.update({target['id']: float((i+2)*(j+1)+(i%3)) for j, target in enumerate(c01.TARGETS)})
            samples.append(row)
        self.inputs = {'samples': samples, 'source': {'archive_sha256': 'a'*64},
                       'audit': [], 'provenance': [], 'bio_mapping': []}
        self.study = C01Research(self.root / 'study')
        with patch('autoresearch.c01_research.c01.load_archive', return_value=self.inputs):
            self.study.create('synthetic-test-only.zip', self.index, 'Synthetic persistence/contract test', max_fits=2)

    def inspection_inputs(self):
        """Complete synthetic provenance; no actual workbook or biological claim."""
        inputs = copy.deepcopy(self.inputs)
        fields = [*c01.FEATURES, *[target['id'] for target in c01.TARGETS]]
        workbook = 'synthetic-main.xlsx'
        inputs['source']['files'] = [
            {'member': 'synthetic/attachments/' + workbook, 'sha256': hashlib.sha256(b'synthetic workbook identity').hexdigest()},
            {'member': 'synthetic/not-referenced.xlsx', 'sha256': 'b' * 64}]
        inputs['provenance'] = [
            {'sample_id': row['sample_id'], 'field': field, 'source': workbook, 'sheet': 'FixtureSheet',
             'cell': f'{chr(65 + column)}{number + 2}', 'raw': repr(row[field]),
             'formula': 'A1+B1' if column == 3 and number == 0 else None}
            for number, row in enumerate(inputs['samples']) for column, field in enumerate(fields)]
        inputs['bio_mapping'] = [
            {'sample_id': row['sample_id'], 'bio_label': f'SYNTHETIC-B{number + 1}', 'shared_fields_compared': 6,
             'max_abs_difference': 0.0, 'consistent_with_row_mapping': True}
            for number, row in enumerate(inputs['samples'])]
        return inputs

    def prepare_inspection_fixture(self, inputs=None):
        self.inputs = self.inspection_inputs() if inputs is None else inputs
        self.study = C01Research(self.root / 'inspection-study')
        with patch('autoresearch.c01_research.c01.load_archive', return_value=self.inputs):
            self.study.create('synthetic-inspection-only.zip', self.index, 'Synthetic frozen dataset inspection', max_fits=2)
        return self.inputs

    def request(self, action, parameters=None, **changes):
        state = self.study.observe()
        experiments = [item for item in state['actions'] if item['action'] in {'fit', 'residuals', 'correlation'}]
        value = {'request_id': 'request-' + str(len(state['actions'])+1),
                 'observation_sha256': state['observation_sha256'], 'action': action,
                 'reason': 'Observe actual feedback before this controlled action.',
                 'source_citation_ids': [state['citations'][0]['citation_id']] if state['citations'] else [],
                 'evidence_action_ids': [experiments[-1]['id']] if experiments else [],
                 'parameters': parameters or {}}
        return {**value, **changes}

    def search(self):
        return self.study.apply(self.request('search', {'query': 'C01 alloy', 'kinds': ['reuse_note']}))

    def fit(self, alpha=1, features=None):
        params = {'alpha': alpha, 'features': features or list(c01.FEATURES),
                  'hypothesis': 'Regularization may reduce unstable held-out errors.',
                  'expected_effect': 'Compare per-target MAE to the fold-mean baseline; failure remains evidence.'}
        return self.study.apply(self.request('fit', params))

    def propose(self, decision='pause'):
        return self.study.apply(self.request('propose_control', {'decision': decision}))

    def control_review_request(self, **changes):
        state = self.study.observe(); control = control_review_state(state)
        ids = [control['proposal_action_id']] if control['proposal_action_id'] else []
        if control['latest_experiment_id']: ids.append(control['latest_experiment_id'])
        params = {'field': 'control_rationale', 'question': 'Does the actual evidence support this control rationale?',
                  'finding': 'SYNTHETIC contract test assertion, not a scientific review.',
                  'status': 'unresolved', 'next_check': 'Choose a justified check or control; no forced positive result.'}
        return self.request('review_evidence', params, **{'evidence_action_ids': ids, **changes})

    def test_control_proposal_and_review_preserve_active_state_original_rationale_and_science_flags(self):
        self.search();fit = self.fit()['action'];before = self.study.observe()
        proposed = self.propose()['action'];state = self.study.observe()
        self.assertEqual(state['status'], 'active');self.assertEqual(state['budget']['fits_used'], 1)
        self.assertEqual(state['scientific_status'], before['scientific_status'])
        self.assertFalse(proposed['result']['control_applied']);self.assertFalse(proposed['result']['scientific_approval'])
        self.assertEqual(control_review_state(state)['latest_experiment_id'], fit['id'])
        review = self.study.apply(self.control_review_request())['action']
        self.assertFalse(review['result']['interpretation_verified']);self.assertFalse(review['result']['scientific_approval'])
        self.assertEqual(self.study.observe()['actions'][-2], proposed)
        self.assertTrue(control_review_state(self.study.observe())['reviewed'])
        self.assertEqual(self.study.observe()['status'], 'active')
        self.study.apply(self.request('residuals', {'fit_action_id': fit['id']}))
        self.assertFalse(control_review_state(self.study.observe())['current'])
        next_proposal = self.propose('stop')['action']
        self.assertNotEqual(next_proposal['id'], proposed['id'])
        self.study.apply(self.control_review_request())
        final = self.study.apply(self.request('stop'))['state']
        self.assertEqual(final['status'], 'stopped')
        self.assertEqual(final['actions'][2], proposed)

    def test_control_review_requires_exact_current_proposal_and_actual_latest_experiment(self):
        self.search()
        self.assert_error('INVALID_CONTROL_REVIEW', self.control_review_request())
        fit = self.fit()['action'];proposal = self.propose()['action']
        good = self.control_review_request()
        for ids in ([], [fit['id']], [proposal['id']]):
            self.assert_error('INVALID_CONTROL_REVIEW', {**good, 'evidence_action_ids': ids})
        self.assert_error('INVALID_EVIDENCE', {**good, 'evidence_action_ids': ['unknown']})
        self.study.apply(good)
        changed = self.control_review_request();changed['parameters']['finding'] = 'A distinct unapproved assertion.'
        self.assert_error('INVALID_CONTROL_REVIEW', changed)
        self.assert_error('DUPLICATE_CONTROL_PROPOSAL', self.request('propose_control', {'decision': 'stop'}))
        self.study.apply(self.request('residuals', {'fit_action_id': fit['id']}))
        self.assert_error('INVALID_CONTROL_REVIEW', self.control_review_request())
        self.propose('stop')
        stale = self.control_review_request();stale['evidence_action_ids'] = [proposal['id'], fit['id']]
        self.assert_error('INVALID_CONTROL_REVIEW', stale)

    def test_control_proposal_params_and_evidence_are_bounded_without_data_or_evaluator_mutation(self):
        self.assert_error('INVALID_EVIDENCE', self.request('propose_control', {'decision': 'pause'}))
        self.search();fit = self.fit()['action']
        self.assert_error('INVALID_EVIDENCE', self.request('propose_control', {'decision': 'pause'}, evidence_action_ids=[]))
        for parameters in ({}, {'decision': True}, {'decision': 'continue'}, {'decision': 'pause', 'path': '../x'}):
            self.assert_error('INVALID_REQUEST', self.request('propose_control', parameters))
        original = self.study.observe()
        self.propose()
        self.assertEqual(self.study.observe()['actions'][:len(original['actions'])], original['actions'])
        self.assertEqual(self.study.observe()['actions'][1], fit)

    def test_control_records_replay_idempotently_and_cannot_reopen_terminal_state(self):
        self.search();self.fit()
        request = self.request('propose_control', {'decision': 'pause'})
        original = self.study.apply(request)['action']
        with patch.object(C01Research, '_execute', side_effect=AssertionError('must replay original proposal')):
            replay = self.study.apply(request)
        self.assertTrue(replay['replayed']);self.assertEqual(replay['action'], original)
        review_request = self.control_review_request();review = self.study.apply(review_request)['action']
        with patch.object(C01Research, '_review', side_effect=AssertionError('must replay original review')):
            self.assertEqual(self.study.apply(review_request)['action'], review)
        self.study.apply(self.request('pause'))
        self.assert_error('NOT_ACTIVE', self.request('fit', {'alpha':2, 'features':list(c01.FEATURES),
            'hypothesis':'Synthetic test only','expected_effect':'No forced positive result'}))

    def test_control_proposal_reserves_three_tool_action_slots(self):
        other = C01Research(self.root/'small-budget')
        with patch('autoresearch.c01_research.c01.load_archive', return_value=self.inputs):
            other.create('synthetic.zip', self.index, 'Synthetic action budget', max_actions=3)
        self.study = other;self.search()
        self.assert_error('BUDGET_EXHAUSTED', self.request('propose_control', {'decision':'pause'}))
        self.assertEqual(self.study.apply(self.request('pause'))['state']['status'], 'paused')

    def assert_error(self, code, request):
        before = self.study.observe()
        with self.assertRaises(ResearchError) as error:
            self.study.apply(request)
        self.assertEqual(error.exception.code, code)
        self.assertEqual(self.study.observe(), before)

    def test_real_fit_feedback_resume_and_negative_result_recording(self):
        self.search()
        output = self.fit()
        result = output['action']['result']
        self.assertEqual(len(result['predictions']), 32)
        self.assertEqual(result['fold_fits'], 32)
        expected, predictions = c01._round(self.inputs['samples'], 1, 1, list(c01.FEATURES))
        self.assertEqual(result['summary']['metrics'], expected['metrics'])
        self.assertEqual(result['predictions'], predictions)
        for prediction in predictions:
            self.assertNotIn(prediction['sample_id'], prediction['training_sample_ids'].split(';'))
        restarted = C01Research(self.study.root)
        self.assertEqual(restarted.observe(), output['state'])
        self.assertFalse(restarted.observe()['unattended_model_loop_verified'])

    def test_read_before_search_has_original_citeable_chunks_and_idempotent_recovery(self):
        initial = self.study.observe()
        card = initial['source_catalogue']['documents'][0]
        params = {key: card[key] for key in ('document_id', 'source_sha256')}
        params.update(start_chunk=0, count=1)
        request = self.request('read_source', params)
        output = self.study.apply(request)
        expected = KnowledgeIndex(self.index).read_source(**params)
        self.assertEqual(output['action']['result'], expected)
        self.assertEqual(output['state']['citations'], expected['evidence'])
        self.assertEqual(output['state']['budget']['fits_used'], 0)
        self.assertEqual(output['state']['data']['audit'], initial['data']['audit'])
        self.assertEqual(output['state']['scientific_status'], initial['scientific_status'])
        replay = C01Research(self.study.root).apply(request)
        self.assertTrue(replay['replayed']);self.assertEqual(replay['action']['id'], output['action']['id'])
        self.assertEqual(len(replay['state']['actions']), 1)
        self.assert_error('DUPLICATE_READ', self.request('read_source', params))
        review = {'field': 'cell_protocol', 'question': 'What does this synthetic note establish?',
                  'finding': 'This fixture note calls aggregate records exploratory.',
                  'status': 'supported', 'next_check': 'Obtain domain-specific methods; this is a contract test.'}
        result = self.study.apply(self.request('review_evidence', review))
        self.assertEqual(result['action']['result']['evidence'], [
            {key: expected['evidence'][0][key] for key in ('citation_id','source','location','quote')}])
        self.assertFalse(result['action']['result']['scientific_approval'])

    def test_inspection_returns_exact_frozen_data_provenance_and_referenced_hash_only(self):
        inputs = self.prepare_inspection_fixture()
        before = self.study.export()['reproduction']
        with patch('autoresearch.c01_research.c01.load_archive', side_effect=AssertionError('must not reload workbook')):
            output = self.study.apply(self.request('inspect_dataset', source_citation_ids=[], evidence_action_ids=[]))
        result = output['action']['result']
        self.assertEqual(result['schema_version'], 'c01-dataset-inspection-v1')
        self.assertEqual(result['inputs_sha256'], fingerprint(inputs))
        self.assertEqual(result['archive_sha256'], inputs['source']['archive_sha256'])
        for key in ('samples', 'provenance', 'bio_mapping'):
            self.assertEqual(result[key], inputs[key])
        self.assertEqual(result['source_files'], [inputs['source']['files'][0]])
        self.assertEqual(result['features'], list(c01.FEATURES))
        self.assertEqual(result['targets'], [target['id'] for target in c01.TARGETS])
        self.assertFalse(result['scientific_approval']);self.assertFalse(result['interpretation_verified'])
        self.assertLessEqual(len(canonical(result).encode('utf-8')), 24576)
        self.assertEqual(output['state']['citations'], [])
        self.assertEqual(output['state']['budget']['fits_used'], 0)
        self.assertEqual(output['state']['data']['audit'], inputs['audit'])
        exported = self.study.export()
        self.assertEqual(exported['reproduction'], before)
        self.assertIn('64条缓存单元格出处', exported['markdown'])
        result['samples'][0][c01.FEATURES[0]] = 999
        self.assertEqual(self.study.export()['reproduction'], before)

    def test_inspection_summary_matches_independent_column_calculations_and_preserves_precision(self):
        inputs = self.inspection_inputs()
        special = [1.0000000000000002, -0.0, -3.25, 7.5, 1e-11, 2, 18.125, 4.5]
        for number, row in enumerate(inputs['samples']):
            row[c01.FEATURES[0]] = special[number]
            row[c01.FEATURES[1]] = 7.25
        for entry in inputs['provenance']:
            row = next(row for row in inputs['samples'] if row['sample_id'] == entry['sample_id'])
            entry['raw'] = repr(row[entry['field']])
        config = {'inputs': inputs, 'inputs_sha256': fingerprint(inputs)}
        before = canonical(config)
        result = C01Research._inspect_dataset(config)
        self.assertEqual(canonical(config), before)
        self.assertEqual(canonical(result['samples']), canonical(inputs['samples']))
        for summary in result['column_summary']:
            column = [row[summary['field']] for row in inputs['samples']]
            self.assertEqual(summary['role'], 'feature' if summary['field'] in c01.FEATURES else 'target')
            self.assertEqual((summary['count'], summary['finite_count'], summary['missing_count'], summary['nonfinite_count']), (8, 8, 0, 0))
            self.assertEqual((summary['min'], summary['max']), (min(column), max(column)))
            self.assertAlmostEqual(summary['mean'], sum(column) / len(column), places=14)
            self.assertEqual(summary['unique_count'], len(set(column)))
            self.assertEqual(summary['constant'], all(value == column[0] for value in column))
        self.assertTrue(result['column_summary'][1]['constant'])

    def test_inspection_can_reread_without_new_scientific_identity_and_replay_without_reinspection(self):
        self.prepare_inspection_fixture()
        request = self.request('inspect_dataset', source_citation_ids=[], evidence_action_ids=[])
        first = self.study.apply(request)
        with patch.object(C01Research, '_inspect_dataset', side_effect=AssertionError('must replay saved result')):
            replay = C01Research(self.study.root).apply(request)
        self.assertTrue(replay['replayed']);self.assertEqual(first['action'], replay['action'])
        second = self.study.apply(self.request('inspect_dataset', source_citation_ids=[], evidence_action_ids=[]))
        self.assertEqual(second['action']['result'], first['action']['result'])
        self.assertEqual(second['state']['budget']['actions_used'], 2)
        self.assertEqual(second['state']['budget']['fits_used'], 0)
        self.assertEqual(second['state']['scientific_status'], first['state']['scientific_status'])

    def test_inspection_rejects_path_field_and_sample_mutation_parameters(self):
        self.prepare_inspection_fixture()
        for params in ({'path': '../outside.xlsx'}, {'features': [c01.FEATURES[0]]},
                       {'samples': []}, {'inputs_sha256': 'f' * 64}, {'source': {}}):
            self.assert_error('INVALID_REQUEST', self.request('inspect_dataset', params))

    def test_inspection_requires_complete_samples_provenance_mapping_and_exact_source_hash_linkage(self):
        valid = self.inspection_inputs()
        mutations = [lambda x: x['samples'].pop(),
                     lambda x: x.update(audit={}),
                     lambda x: x['samples'][0].pop(c01.FEATURES[0]),
                     lambda x: x['samples'][0].update(hidden_label=1),
                     lambda x: x['samples'][0].update({c01.FEATURES[0]: True}),
                     lambda x: x['samples'][1].update(sample_id=x['samples'][0]['sample_id']),
                     lambda x: x['provenance'].pop(),
                     lambda x: x['provenance'].__setitem__(1, copy.deepcopy(x['provenance'][0])),
                     lambda x: x['provenance'][0].update(raw='9999'),
                     lambda x: x['provenance'][0].update(raw='<1'),
                     lambda x: x['provenance'][0].update(source='../outside.xlsx'),
                     lambda x: x['provenance'][0].update(formula='x' * 513),
                     lambda x: x['source']['files'][0].update(sha256='invalid'),
                     lambda x: x['source']['files'].pop(0),
                     lambda x: x['source']['files'].append({**x['source']['files'][0], 'member': 'different/synthetic-main.xlsx'}),
                     lambda x: x['bio_mapping'].pop(),
                     lambda x: x['bio_mapping'][1].update(sample_id=x['bio_mapping'][0]['sample_id']),
                     lambda x: x['bio_mapping'][0].update(consistent_with_row_mapping='true'),
                     lambda x: x['bio_mapping'][0].update(max_abs_difference=-1)]
        for mutation in mutations:
            inputs = copy.deepcopy(valid);mutation(inputs)
            with self.subTest(mutation=mutation), self.assertRaises(ResearchError) as caught:
                C01Research._inspect_dataset({'inputs': inputs, 'inputs_sha256': fingerprint(inputs)})
            self.assertEqual(caught.exception.code, 'INVALID_DATASET')

    def test_inspection_preserves_flagged_mapping_without_claiming_scientific_qualification(self):
        inputs = self.inspection_inputs()
        inputs['bio_mapping'][0].update(consistent_with_row_mapping=False, max_abs_difference=.25)
        inputs['bio_mapping'][0]['bio_label'] += '*'
        result = C01Research._inspect_dataset({'inputs': inputs, 'inputs_sha256': fingerprint(inputs)})
        self.assertEqual(result['bio_mapping'], inputs['bio_mapping'])
        self.assertFalse(result['scientific_approval'])
        self.assertTrue(any('independent samples' in value for value in result['caveats']))

    def test_inspection_nonfinite_values_fail_with_static_error_and_large_finite_means_remain_finite(self):
        for value in (float('nan'), float('inf'), -float('inf'), 10 ** 400):
            inputs = self.inspection_inputs();inputs['samples'][0][c01.FEATURES[0]] = value
            try:expected = fingerprint(inputs)
            except ValueError:expected = 'a' * 64
            with self.subTest(value=repr(value)), self.assertRaises(ResearchError) as caught:
                C01Research._inspect_dataset({'inputs': inputs, 'inputs_sha256': expected})
            self.assertEqual(caught.exception.code, 'INVALID_DATASET')
        inputs = self.inspection_inputs()
        for row in inputs['samples']:row[c01.FEATURES[0]] = 1e308
        for cell in inputs['provenance']:
            if cell['field'] == c01.FEATURES[0]:cell['raw'] = '1e308'
        result = C01Research._inspect_dataset({'inputs': inputs, 'inputs_sha256': fingerprint(inputs)})
        self.assertTrue(math.isfinite(result['column_summary'][0]['mean']))
        self.assertEqual(result['column_summary'][0]['mean'], 1e308)

    def test_inspection_rejects_utf8_oversize_without_truncation_or_input_edits(self):
        inputs = self.inspection_inputs()
        for cell in inputs['provenance']:cell['formula'] = '字' * 300
        config = {'inputs': inputs, 'inputs_sha256': fingerprint(inputs)};before = canonical(config)
        with self.assertRaises(ResearchError) as caught:C01Research._inspect_dataset(config)
        self.assertEqual(caught.exception.code, 'DATASET_INSPECTION_TOO_LARGE')
        self.assertEqual(canonical(config), before)

    def test_inspection_does_not_load_sources_fit_or_evaluate_formula_text(self):
        inputs = self.inspection_inputs()
        inputs['provenance'][0]['formula'] = "__import__('os').environ.clear()"
        for number in range(150):
            inputs['source']['files'].append({'member': f'unreferenced/item{number}.xlsx', 'sha256': 'c' * 64})
        config = {'inputs': inputs, 'inputs_sha256': fingerprint(inputs)}
        with patch('autoresearch.c01_research.c01.load_archive', side_effect=AssertionError('no archive read')), \
             patch('autoresearch.c01_research.c01._round', side_effect=AssertionError('no fit')), \
             patch.object(Path, 'open', side_effect=AssertionError('no filesystem reads')):
            result = C01Research._inspect_dataset(config)
        self.assertEqual(result['provenance'][0]['formula'], inputs['provenance'][0]['formula'])
        self.assertEqual(result['source_files'], [inputs['source']['files'][0]])

    def test_inspection_refuses_tampered_frozen_inputs_before_recording_an_action(self):
        self.prepare_inspection_fixture()
        request = self.request('inspect_dataset')
        con = sqlite3.connect(self.study.db)
        try:
            config = json.loads(con.execute('SELECT config FROM meta').fetchone()[0])
            config['inputs']['samples'][0][c01.FEATURES[0]] += 1
            con.execute('UPDATE meta SET config=?', (canonical(config),));con.commit()
        finally:con.close()
        with self.assertRaises(ResearchError) as caught:self.study.apply(request)
        self.assertEqual(caught.exception.code, 'INPUT_CHANGED')
        con = sqlite3.connect(self.study.db)
        try:self.assertEqual(con.execute('SELECT count(*) FROM actions').fetchone()[0], 0)
        finally:con.close()

    def test_scoped_search_and_read_require_the_current_document_hash_pair(self):
        card = self.study.observe()['source_catalogue']['documents'][0]
        pair = {key: card[key] for key in ('document_id', 'source_sha256')}
        for action, extra in (('search', {'query':'alloy'}), ('read_source', {'start_chunk':0,'count':1})):
            for bad in ({'document_id': card['document_id']},
                        {**pair,'source_sha256':'f'*64}, {**pair,'document_id':'../../unavailable.md'}):
                self.assert_error('INVALID_SOURCE_SELECTION', self.request(action,{**extra,**bad}))
        result = self.study.apply(self.request('search', {'query':'alloy',**pair}))['action']['result']
        self.assertEqual(result['source_scope']['document_id'],card['document_id'])
        self.assertEqual(result['source_scope']['source_sha256'],card['source_sha256'])
        self.assertTrue(all(hit['source']['id']==card['document_id'] for hit in result['evidence']))

    def test_later_reread_refreshes_bounded_context_without_new_citation_identity(self):
        from autoresearch.c01_model_loop import build_context
        from autoresearch.c01_local_loop import research_progress
        source = doc('long-note', '# Context\n' + ('original paragraph content ' * 650), kind='reuse_note')
        index = self.root/'long-index.sqlite';build_index([source],index)
        self.study = C01Research(self.root/'long-study')
        with patch('autoresearch.c01_research.c01.load_archive', return_value=self.inputs):
            self.study.create('synthetic-only.zip', index, 'Synthetic context recovery')
        pair={'document_id':source['id'],'source_sha256':source['sha256']}
        for start in (0,2,4):self.study.apply(self.request('read_source',{**pair,'start_chunk':start,'count':2}))
        before=self.study.observe();old_ids={x['citation_id'] for x in before['citations']}
        expected=KnowledgeIndex(index).read_source(**pair,start_chunk=0,count=1)['evidence'][0]
        after=self.study.apply(self.request('read_source',{**pair,'start_chunk':0,'count':1}))['state']
        self.assertEqual({x['citation_id'] for x in after['citations']},old_ids)
        context=build_context(after,remaining_requests=4,references_limit=1,text_limit=1400)
        self.assertEqual(context['references'][0]['citation_id'],expected['citation_id'])
        self.assertEqual(context['references'][0]['quote'],expected['quote'])
        self.assertEqual(context['reading_navigation']['window']['start_chunk'],0)
        self.assertEqual(research_progress(after)['executed_read_windows'][-1]['new_citations'],0)
        self.assertEqual(C01Research(self.study.root).observe(),after)

    def test_real_residual_and_pair_tools_have_durable_feedback(self):
        self.search()
        fit = self.fit()['action']
        residuals = self.study.apply(self.request('residuals', {'fit_action_id': fit['id']}))
        self.assertEqual(residuals['action']['result']['n'], 8)
        self.assertEqual(len(residuals['action']['result']['targets']), 4)
        pair = self.study.apply(self.request('correlation'))
        self.assertEqual(len(pair['action']['result']['leave_one_out']), 8)
        self.assertEqual(pair['state']['scientific_status'], 'exploratory_reused_loo_no_independent_validation')

    def test_sources_current_observation_and_latest_experiment_are_required(self):
        self.assert_error('INVALID_EVIDENCE', self.request('correlation'))
        stale = self.request('search', {'query': 'alloy'})
        stale['request_id'] = 'old-observation-newid'
        self.search()
        self.assert_error('STALE_OBSERVATION', stale)
        self.assert_error('INVALID_EVIDENCE', self.request('stop', source_citation_ids=['forged']))
        self.fit()
        self.assert_error('INVALID_EVIDENCE', self.request('correlation', evidence_action_ids=[]))

    def test_no_evidence_and_empty_searches_cannot_prevent_a_safe_stop(self):
        other = C01Research(self.root / 'empty-evidence')
        with patch('autoresearch.c01_research.c01.load_archive', return_value=self.inputs):
            other.create('fixture', self.index, 'empty evidence fixture', max_actions=3)
        self.study = other
        self.study.apply(self.request('search', {'query': 'unmatchedzqxv7319'}))
        self.study.apply(self.request('search', {'query': 'anotherunmatchedzqxv7319'}))
        self.assertEqual(self.study.observe()['citations'], [])
        self.study.apply(self.request('stop', source_citation_ids=[], evidence_action_ids=[]))
        self.assertEqual(self.study.observe()['status'], 'stopped')

    def test_idempotency_replay_does_not_refit_or_change_state(self):
        self.search()
        params = {'alpha': 1, 'features': list(c01.FEATURES), 'hypothesis': 'test', 'expected_effect': 'test'}
        request = self.request('fit', params)
        original = self.study.apply(request)
        with patch('autoresearch.c01_research.c01._round', side_effect=AssertionError('must not refit')):
            replay = self.study.apply(request)
        self.assertTrue(replay['replayed'])
        self.assertEqual(replay['state'], original['state'])
        self.assert_error('IDEMPOTENCY_CONFLICT', {**request, 'reason': 'different'})

    def test_duplicate_recipe_feature_permutations_and_fit_budget(self):
        self.search()
        self.fit()
        with self.assertRaises(ResearchError) as error:
            self.fit(features=list(reversed(c01.FEATURES)))
        self.assertEqual(error.exception.code, 'DUPLICATE_RECIPE')
        self.fit(100)
        with self.assertRaises(ResearchError) as error:
            self.fit(1000)
        self.assertEqual(error.exception.code, 'BUDGET_EXHAUSTED')
        self.study.apply(self.request('stop'))
        self.assertEqual(self.study.observe()['status'], 'stopped')

    def test_terminal_decision_is_durable_and_stops_new_dispatch(self):
        self.search()
        request = self.request('stop')
        self.study.apply(request)
        self.assert_error('NOT_ACTIVE', self.request('search', {'query': 'alloy'}))
        self.assertTrue(self.study.apply(request)['replayed'])
        self.assertEqual(C01Research(self.study.root).observe()['status'], 'stopped')

    def test_last_action_slot_is_reserved_for_control(self):
        other = C01Research(self.root / 'bounded')
        with patch('autoresearch.c01_research.c01.load_archive', return_value=self.inputs):
            other.create('fixture', self.index, 'bounded fixture', max_actions=3)
        self.study = other
        self.search()
        self.fit()
        self.assert_error('BUDGET_EXHAUSTED', self.request('correlation'))
        self.study.apply(self.request('stop'))

    def test_no_commands_paths_or_changed_source_fields_enter_tool(self):
        self.search()
        self.assert_error('INVALID_REQUEST', {**self.request('stop'), 'shell': 'ignored command'})
        for params in ({'alpha': 1, 'features': ['secret_label'], 'hypothesis': 'x', 'expected_effect': 'x'},
                       {'alpha': True, 'features': list(c01.FEATURES), 'hypothesis': 'x', 'expected_effect': 'x'},
                       {'alpha': 1, 'features': list(c01.FEATURES)},
                       {'alpha': float('inf'), 'features': list(c01.FEATURES), 'hypothesis': 'x', 'expected_effect': 'x'}):
            # non-finite JSON is rejected at the canonical request boundary.
            with self.assertRaises((ResearchError, ValueError)):
                self.study.apply(self.request('fit', params))

    def test_tampered_result_and_code_identity_fail_closed(self):
        self.search()
        with patch('autoresearch.c01_research.code_identity', return_value='changed'):
            with self.assertRaises(ResearchError) as error:
                self.study.observe()
            self.assertEqual(error.exception.code, 'CODE_CHANGED')
        with sqlite3.connect(self.study.db) as con:
            record = json.loads(con.execute('SELECT record FROM actions').fetchone()[0])
            record['result']['evidence'] = []
            con.execute('UPDATE actions SET record=?', (json.dumps(record),))
        con.close()
        with self.assertRaises(ResearchError) as error:
            self.study.observe()
        self.assertEqual(error.exception.code, 'EVIDENCE_CHANGED')

    def test_exports_include_exact_source_locations_inputs_and_all_proposals(self):
        self.search()
        self.fit()
        self.study.apply(self.request('stop'))
        exported = self.study.export()
        self.assertEqual(exported['reproduction']['inputs'], self.inputs)
        self.assertIn('SHA256', exported['markdown'])
        self.assertIn('stop', exported['markdown'])
        self.assertEqual(len(exported['state']['actions']), 3)

    def test_export_uses_one_snapshot_when_stop_commits_during_read(self):
        self.search()
        before = self.study.observe()
        stop = self.request('stop')
        with sqlite3.connect(self.study.db) as con:
            con.execute('PRAGMA journal_mode=WAL')
        con.close()
        injected = False

        def concurrent_stop(index_path):
            nonlocal injected
            if not injected:
                injected = True
                C01Research(self.study.root).apply(stop)
            return KnowledgeIndex(index_path)

        with patch('autoresearch.c01_research.KnowledgeIndex', side_effect=concurrent_stop):
            exported = self.study.export()['state']
        self.assertEqual(exported, before)
        self.assertEqual(self.study.observe()['status'], 'stopped')


if __name__ == '__main__':
    unittest.main()
