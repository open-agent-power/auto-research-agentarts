"""Synthetic saved-reference checks; no study callback or project is run."""
import copy
import contextlib
import hashlib
import inspect
import io
import json
from pathlib import Path
import runpy
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch

from autoresearch import saved_study_reference as ref
from autoresearch.contracts import ResearchError, canonical, fingerprint


def raw(value):
    return canonical(value).encode()


def fixture(include_source=True):
    data = {'source_head': (ref._COMMIT + '\n').encode()}
    protocol = {'budget': {'synthetic': 3}, 'limitations': ['synthetic only']}
    if include_source:
        protocol.update(source_basis={'old_source_project_id': 'fixture-source-project',
                                     'source_counterevidence': 'fixture opposite single timings',
                                     'source_informed_rule_choices': 1},
                        policy={'threshold': 7, 'allowed_arm_ids': ['fixture-threshold7']})
    sources = {name: ('source:' + name).encode() for name in ref._SOURCE_SHAS}
    sources[ref._PROTOCOL] = raw(protocol)
    data.update({'source:' + name: value for name, value in sources.items()})
    source_shas = {name: hashlib.sha256(value).hexdigest() for name, value in sources.items()}
    binding = {'study_id': ref._STUDY, 'request_id': ref._PREPARE, 'output_root': str(ref._OUTPUT),
               'code_commit': ref._COMMIT, 'runtime': {'native_code_identity': ref._RUNTIME},
               'source_fingerprints': source_shas, 'protocol_sha256': source_shas[ref._PROTOCOL],
               'budget_sha256': fingerprint(protocol['budget'])}
    review_common = {key: binding[key] for key in ('protocol_sha256', 'code_commit', 'output_root', 'budget_sha256', 'source_fingerprints', 'runtime')}
    setup = {**review_common, 'schema_version': 'scheduling-policy-setup-review-v1', 'status': 'approved',
             'study_id': ref._STUDY, 'request_id': ref._PREPARE, 'allowed_phase': 'generate_only', 'reviewer': 'fixture'}
    data['setup_review'] = raw(setup)
    binding['setup_review_sha256'] = hashlib.sha256(data['setup_review']).hexdigest()
    claim = {'schema_version': 'bounded-study-claim-v1', 'limits': ref._LIMITS, 'binding': binding}
    claim_sha = fingerprint(claim)
    data['global_claim'] = raw(claim)
    data['marker'] = raw({'study_id': ref._STUDY, 'claim_sha256': claim_sha})
    events = [{'sha256': hashlib.sha256(str(n).encode()).hexdigest(), 'event': {'ordinal': n + 1}} for n in range(2400)]
    manifest = {'generation_after_ordinal': 58, 'generation_previous_event_sha256': events[57]['sha256']}
    data['inputs'] = raw(manifest)
    input_review = {**review_common, 'schema_version': 'scheduling-policy-input-review-v1', 'status': 'approved',
                    'study_id': ref._STUDY, 'request_id': ref._PRIMARY, 'allowed_phase': 'primary_and_saved_audit',
                    'reviewer': 'fixture', 'inputs_sha256': hashlib.sha256(data['inputs']).hexdigest(),
                    'shared_claim_sha256': claim_sha}
    data['input_review'] = raw(input_review)
    counts = {key: value for key, value in ref._LIMITS.items() if key != 'primary'}
    counts['audit'] = 0
    usage = {kind: {'reserved': count, 'completed': count, 'failed': 0, 'unknown': 0}
             for kind, count in counts.items() if kind in ('generate', 'warmup', 'timed', 'correctness', 'oracle', 'bruteforce', 'audit')}
    phases = {'generation': {}, 'generation_result': {'manifest_sha256': hashlib.sha256(data['inputs']).hexdigest()},
              'input_review': {'review_sha256': hashlib.sha256(data['input_review']).hexdigest()},
              'primary': {}, 'primary_result': None}
    ledger = {'claim': claim, 'claim_sha256': claim_sha, 'events': events, 'phases': phases,
              'counts': counts, 'usage': usage, 'unknown': [], 'failed': [], 'halted': None}
    summary = {'performance_cases': [{'case_id': f'fake-{i}'} for i in range(27)]}
    result = {'schema_version': 'scheduling-threshold-study-result-v1', 'study_id': ref._STUDY,
              'binding': binding, 'input_manifest': manifest, 'ledger': ledger, 'summary': summary,
              'limitations': protocol['limitations'], 'reviews': {}}
    import base64
    for name in ('setup', 'input'):
        review = data[name + '_review']
        result['reviews'][name] = {'raw_base64': base64.b64encode(review).decode(), 'raw_sha256': hashlib.sha256(review).hexdigest()}
    data['result'] = raw(result)
    primary = copy.deepcopy(ledger)
    primary['phases']['primary_result'] = {'bundle_sha256': hashlib.sha256(data['result']).hexdigest(),
                                          'after_ordinal': 2400, 'previous_event_sha256': events[-1]['sha256']}
    data['primary_ledger'] = raw(primary)
    spec = {'request_id': ref._AUDIT, 'bundle_sha256': hashlib.sha256(data['result']).hexdigest(),
            'primary_snapshot_sha256': hashlib.sha256(data['primary_ledger']).hexdigest()}
    audit = {'schema_version': 'scheduling-threshold-primary-receipt-verification-v1', 'status': 'passed',
             'bundle_sha256': spec['bundle_sha256'], 'saved_verification': {'status': 'passed',
             'scientific_validation': False, 'summary': summary, 'counts': counts,
             'oracle_scope': 'saved only', 'integrity_scope': 'not signed'}}
    live = copy.deepcopy(primary)
    live['events'].extend([{'sha256': 'a' * 64, 'event': {'event': 'reserved', 'operation': 'audit', 'op_id': ref._AUDIT, 'spec': spec}},
                           {'sha256': 'b' * 64, 'event': {'event': 'completed', 'operation': 'audit', 'op_id': ref._AUDIT, 'spec': spec, 'result': audit}}])
    live['counts']['audit'] = 1
    live['usage']['audit'] = {'reserved': 1, 'completed': 1, 'failed': 0, 'unknown': 0}
    expected = {key: hashlib.sha256(data[key]).hexdigest() for key in ref._EXPECTED_BYTES}
    return data, live, expected, source_shas, claim_sha


class SavedStudyReferenceTests(unittest.TestCase):
    def setUp(self):
        self.data, self.live, self.expected, self.sources, self.claim_sha = fixture()

    def validate(self):
        return ref._validate_evidence(self.data, self.live, self.expected, self.sources, self.claim_sha)

    def test_complete_saved_view_is_bounded_and_does_not_invent_project(self):
        view = self.validate()
        self.assertEqual(view['status'], 'completed')
        self.assertEqual(len(view['saved_summary']['performance_cases']), 27)
        self.assertFalse(view['numerical_recomputation'])
        self.assertFalse(view['raw_data_included'])
        self.assertTrue(view['current_project_budget_unchanged'])
        self.assertNotIn('project_id', view)
        self.assertNotIn('action_id', view)
        self.assertLess(len(raw(view)), 65536)
        self.assertEqual(len(inspect.signature(ref.read_saved_study_reference).parameters), 0)
        self.assertEqual(view['hypothesis_source']['source_basis'], {'old_source_project_id': 'fixture-source-project',
                         'source_counterevidence': 'fixture opposite single timings', 'source_informed_rule_choices': 1})
        self.assertEqual(view['hypothesis_source']['protocol_sha256'], self.sources[ref._PROTOCOL])
        self.assertEqual(view['hypothesis_source']['policy']['threshold'], 7)

    def test_missing_hypothesis_source_is_preserved_as_unrecorded(self):
        self.data, self.live, self.expected, self.sources, self.claim_sha = fixture(include_source=False)
        source = self.validate()['hypothesis_source']
        self.assertIsNone(source['source_basis'])
        self.assertIsNone(source['policy'])
        self.assertEqual(source['protocol_sha256'], self.sources[ref._PROTOCOL])

    def test_final_response_still_enforces_bound_after_source_and_raw_references(self):
        with tempfile.TemporaryDirectory() as d:
            with patch.object(ref, '_FILES', {'ledger': Path(d) / 'ledger.sqlite'}), \
                    patch.object(ref, '_read_regular', return_value=b'fixture'), \
                    patch.object(ref, 'BoundedStudyLedger'), \
                    patch.object(ref, '_validate_evidence', return_value={
                        'status': 'completed', 'hypothesis_source': {'source_basis': 'x' * 65536}}):
                view = ref.read_saved_study_reference()
                self.assertEqual(view['status'], 'integrity_error')
                self.assertNotIn('hypothesis_source', view)

    def test_incomplete_failed_and_unknown_are_not_completed(self):
        for key, value, expected in [('unknown', ['pending'], 'unknown'), ('failed', ['failed'], 'failed'), ('halted', {'reason': 'stop'}, 'failed')]:
            with self.subTest(key=key):
                old = self.live[key]
                self.live[key] = value
                with self.assertRaises(ref._ReferenceFailure) as error:
                    self.validate()
                self.assertEqual(error.exception.status, expected)
                self.live[key] = old
        self.live['events'].pop()
        with self.assertRaises(ref._ReferenceFailure) as error:
            self.validate()
        self.assertEqual(error.exception.status, 'unknown')

    def test_tampered_audit_spec_or_prefix_is_rejected(self):
        self.live['events'][-1]['event']['spec']['primary_snapshot_sha256'] = '0' * 64
        with self.assertRaises(ref._ReferenceFailure):
            self.validate()

    def test_primary_receipt_and_audit_conclusion_are_required(self):
        self.live['phases']['primary_result']['bundle_sha256'] = '0' * 64
        with self.assertRaises(ref._ReferenceFailure):
            self.validate()
        self.data, self.live, self.expected, self.sources, self.claim_sha = fixture()
        self.live['events'][-1]['event']['result']['status'] = 'failed'
        with self.assertRaises(ref._ReferenceFailure):
            self.validate()
        self.data, self.live, self.expected, self.sources, self.claim_sha = fixture()
        self.live['events'][10]['sha256'] = '0' * 64
        with self.assertRaises(ref._ReferenceFailure):
            self.validate()

    def test_original_review_source_and_result_fingerprint_fail_closed(self):
        for name in ('input_review', 'result', 'source:' + ref._PROTOCOL):
            with self.subTest(name=name):
                old = self.data[name]
                self.data[name] += b' '
                with self.assertRaises(ref._ReferenceFailure):
                    self.validate()
                self.data[name] = old

    def test_missing_file_and_symlink_are_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'missing'
            with self.assertRaises(ref._ReferenceFailure) as error:
                ref._read_regular(path)
            self.assertEqual(error.exception.status, 'unavailable')
            target = Path(d) / 'target'
            target.write_text('x')
            path.symlink_to(target)
            with self.assertRaises(ref._ReferenceFailure) as error:
                ref._read_regular(path)
            self.assertEqual(error.exception.status, 'integrity_error')

    def test_fixed_public_reader_treats_absence_and_sidecar_as_unavailable(self):
        with tempfile.TemporaryDirectory() as d:
            with patch.dict(ref._FILES, {'ledger': Path(d) / 'missing.sqlite'}):
                result = ref.read_saved_study_reference()
                self.assertEqual(result['status'], 'unavailable')
                (Path(d) / 'missing.sqlite-wal').write_bytes(b'x')
                result = ref.read_saved_study_reference()
                self.assertEqual(result['status'], 'unknown')

    def test_ledger_unknown_and_missing_have_distinct_fail_closed_states(self):
        with tempfile.TemporaryDirectory() as d:
            with patch.dict(ref._FILES, {'ledger': Path(d) / 'ledger.sqlite'}), \
                    patch.object(ref, '_read_regular', return_value=b''), \
                    patch.object(ref, 'BoundedStudyLedger') as ledger:
                for code, status in (('STUDY_UNKNOWN', 'unknown'), ('STUDY_NOT_FOUND', 'unavailable'),
                                     ('EVIDENCE_CHANGED', 'integrity_error')):
                    with self.subTest(code=code):
                        ledger.return_value.snapshot.side_effect = ResearchError(code, 'synthetic')
                        view = ref.read_saved_study_reference()
                        self.assertEqual(view['status'], status)
                        self.assertNotIn('actual_spent', view)
                        self.assertNotIn('planned_budget', view)
                        self.assertNotIn('hypothesis_source', view)

    def test_sqlite_failures_return_explicit_noncompleted_states(self):
        with tempfile.TemporaryDirectory() as d:
            with patch.dict(ref._FILES, {'ledger': Path(d) / 'ledger.sqlite'}), \
                    patch.object(ref, '_read_regular', return_value=b''), \
                    patch.object(ref, 'BoundedStudyLedger') as ledger:
                for error, status in ((sqlite3.OperationalError('locked'), 'unknown'),
                                      (sqlite3.DatabaseError('corrupt'), 'integrity_error')):
                    with self.subTest(status=status):
                        ledger.return_value.snapshot.side_effect = error
                        view = ref.read_saved_study_reference()
                        self.assertEqual(view['status'], status)
                        self.assertNotIn('actual_spent', view)

    def test_cli_has_only_fixed_summary_and_status(self):
        namespace = runpy.run_path(str(Path(__file__).resolve().parents[1] / 'scripts/read_saved_study_reference.py'))
        with patch.dict(namespace['main'].__globals__, {'read_saved_study_reference': lambda: {'status': 'completed'}}):
            for command in ('status', 'summary'):
                with patch.object(sys, 'argv', ['reader', command]), contextlib.redirect_stdout(io.StringIO()) as output:
                    self.assertEqual(namespace['main'](), 0)
                    self.assertEqual(json.loads(output.getvalue()), {'status': 'completed'})
            with patch.object(sys, 'argv', ['reader', 'summary', '--root', '/tmp']), contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit):
                    namespace['main']()


if __name__ == '__main__':
    unittest.main()
