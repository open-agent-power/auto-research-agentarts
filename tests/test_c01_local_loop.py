"""Durability tests with scripted native replies, never genuine-model evidence."""
import copy
import json
from pathlib import Path
import sys
import threading
import time
import unittest
from unittest.mock import patch

from autoresearch import c01_research
from autoresearch.c01_local_loop import C01LocalLoop, native_request, native_schema, search_signature
from autoresearch.contracts import ResearchError, canonical, fingerprint
from autoresearch.knowledge import KINDS
from autoresearch.local_ollama import MODEL, PUBLISHER_MANIFEST_SHA256
import test_c01_research as study_fixture

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import c01_model_fixture as scripted_fixture


WEIGHTS = {'model': MODEL, 'manifest_sha256': 'b' * 64,
           'publisher_manifest_sha256': PUBLISHER_MANIFEST_SHA256,
           'native_model_digest': PUBLISHER_MANIFEST_SHA256,
           'provenance': 'SIMULATED test identity; no real weights, model, or GPU inference'}
EIGHT_B_SHA = '500a1f067a9f782620b40bee6f7b0c89e17ae61f686b92c24933e4ca4b2b8b41'
EIGHT_B_WEIGHTS = {'model': 'qwen3:8b', 'manifest_sha256': 'e' * 64,
                   'publisher_manifest_sha256': EIGHT_B_SHA, 'native_model_digest': EIGHT_B_SHA,
                   'provenance': 'SIMULATED 8B identity; no real weights, model, or GPU inference'}


def scripted_pause(context):
    return {'action': 'pause', 'observation_sha256': context['observation_sha256'],
            'reason': 'SIMULATED terminal-slot pause; not a genuine model decision.',
            'source_citation_ids': [], 'evidence_action_ids': [], 'parameters': {}}


class FakeNativeServer:
    """Only an in-memory scripted transport, with actual current tool IDs."""
    def __init__(self, policy=None, before_request=None, weights=None, response_model=None):
        self.http = self
        self.weights = copy.deepcopy(WEIGHTS if weights is None else weights)
        self.policy = policy or scripted_fixture.decision
        self.before_request = before_request
        self.response_model = self.weights['model'] if response_model is None else response_model
        self.requests = []
        self.timeouts = []
        self.owner_checks = self.acquisitions = 0

    def acquire(self):
        self.acquisitions += 1
        return copy.deepcopy(self.weights)

    def assert_owner(self): self.owner_checks += 1

    def request(self, route, body, *, timeout):
        expected_seconds = 300 if self.weights['model'] == 'qwen3:8b' else 180
        if route != '/api/chat' or timeout != expected_seconds or body.get('model') != self.weights['model']:
            raise AssertionError('unexpected simulated native request')
        self.requests.append(copy.deepcopy(body))
        self.timeouts.append(timeout)
        if self.before_request: self.before_request(body)
        context = json.loads(body['messages'][-1]['content'])['research_context']
        chosen = self.policy(context)
        content = chosen if type(chosen) is str else canonical(chosen)
        return {'model': self.response_model, 'done': True, 'prompt_eval_count': 123, 'eval_count': 37,
                'message': {'role': 'assistant', 'content': content},
                'simulation_notice': 'scripted fixture, not a genuine local model response'}


class C01LocalLoopTests(unittest.TestCase):
    def setUp(self):
        self.base = study_fixture.C01ResearchTests('test_terminal_decision_is_durable_and_stops_new_dispatch')
        self.base.setUp()
        self.addCleanup(self.base.doCleanups)
        self.study = self.base.study
        self.loop = C01LocalLoop(self.study.root)

    def configure(self, max_requests=8, *, weights=None):
        return self.loop.configure(copy.deepcopy(WEIGHTS if weights is None else weights), max_requests=max_requests)

    def test_native_body_selects_reviewed_model_without_changing_default_or_context(self):
        observation = self.study.observe()
        before = copy.deepcopy(observation)
        default = native_request(observation, 2)
        large = native_request(observation, 2, model='qwen3:8b')
        self.assertEqual(default['model'], 'qwen3:4b')
        self.assertEqual(large['model'], 'qwen3:8b')
        self.assertEqual({**large, 'model': MODEL}, default)
        self.assertEqual(self.study.observe(), before)
        self.assertEqual(MODEL, 'qwen3:4b')
        for model in ('qwen3:9b', 'qwen3:8b-cloud', None, True):
            with self.subTest(model=model), self.assertRaises(ResearchError) as error:
                native_request(observation, 2, model=model)
            self.assertEqual(error.exception.code, 'INVALID_MODEL')

    def test_eight_billion_requests_freeze_model_deadline_and_resume_without_budget_reset(self):
        identity = c01_research.code_identity()
        self.configure(max_requests=3, weights=EIGHT_B_WEIGHTS)
        with self.loop._connect() as con:
            spec = json.loads(con.execute('SELECT spec_json FROM project').fetchone()[0])
        self.assertEqual(spec['request_seconds'], 300)
        self.assertEqual(spec['model_identity']['model'], 'qwen3:8b')
        def policy(context):
            if len(context['actions']) >= 2: return scripted_pause(context)
            return scripted_fixture.decision(context)
        server = FakeNativeServer(weights=EIGHT_B_WEIGHTS, policy=policy)
        first = self.loop.run(server, max_new_requests=1)
        self.assertEqual(first['budget']['requests_reserved'], 1)
        restarted = C01LocalLoop(self.study.root)
        restarted.configure(copy.deepcopy(EIGHT_B_WEIGHTS), max_requests=3)
        result = restarted.run(server, max_new_requests=2)
        self.assertEqual(result['budget'], {'max_requests': 3, 'requests_reserved': 3})
        self.assertEqual([action['action'] for action in result['study']['actions']], ['search', 'fit', 'pause'])
        self.assertEqual(result['study']['budget']['fits_used'], 1)
        self.assertEqual(server.timeouts, [300, 300, 300])
        self.assertTrue(all(body['model'] == 'qwen3:8b' for body in server.requests))
        self.assertEqual(result['model_identity']['native_model_digest'], EIGHT_B_SHA)
        self.assertEqual(C01LocalLoop(self.study.root).run(), result)
        self.assertEqual(len(server.requests), 3)
        self.assertEqual(c01_research.code_identity(), identity)

    def test_models_are_per_study_and_switching_cannot_reset_existing_requests(self):
        self.configure(max_requests=3)
        small = self.loop.run(FakeNativeServer(), max_new_requests=1)
        other = c01_research.C01Research(self.base.root/'separate-eight-b-study')
        with patch('autoresearch.c01_research.c01.load_archive', return_value=self.base.inputs):
            other.create('synthetic-test-only.zip', self.base.index, 'SIMULATED separate 8B study', max_fits=2)
        large_loop = C01LocalLoop(other.root)
        large_loop.configure(copy.deepcopy(EIGHT_B_WEIGHTS), max_requests=3)
        large = large_loop.run(FakeNativeServer(weights=EIGHT_B_WEIGHTS), max_new_requests=1)
        for loop, replacement, original in ((self.loop, EIGHT_B_WEIGHTS, small), (large_loop, WEIGHTS, large)):
            with self.subTest(model=original['model_identity']['model']):
                with self.assertRaises(ResearchError) as error: loop.configure(copy.deepcopy(replacement), max_requests=3)
                self.assertEqual(error.exception.code, 'CONFIG_CHANGED')
                self.assertEqual(loop.status(), original)
                self.assertEqual(loop.status()['budget']['requests_reserved'], 1)
        self.assertEqual(self.loop.status()['model_identity']['model'], 'qwen3:4b')
        self.assertEqual(large_loop.status()['model_identity']['model'], 'qwen3:8b')
        self.assertEqual(MODEL, 'qwen3:4b')

    def test_cross_model_publisher_native_digest_and_server_identity_fail_before_dispatch(self):
        for publisher, native in ((PUBLISHER_MANIFEST_SHA256, PUBLISHER_MANIFEST_SHA256),
                                  (EIGHT_B_SHA, PUBLISHER_MANIFEST_SHA256),
                                  (PUBLISHER_MANIFEST_SHA256, EIGHT_B_SHA)):
            forged = {**EIGHT_B_WEIGHTS, 'publisher_manifest_sha256': publisher, 'native_model_digest': native}
            with self.subTest(publisher=publisher, native=native):
                with self.assertRaises(ResearchError) as error: self.configure(weights=forged)
                self.assertEqual(error.exception.code, 'MODEL_CHANGED')
                self.assertFalse(self.loop.db.exists())
        self.configure(weights=EIGHT_B_WEIGHTS)
        wrong_server = FakeNativeServer()
        with self.assertRaises(ResearchError) as error: self.loop.run(wrong_server, max_new_requests=1)
        self.assertEqual(error.exception.code, 'MODEL_CHANGED')
        self.assertEqual(wrong_server.requests, [])
        self.assertEqual(self.loop.status()['budget']['requests_reserved'], 0)

    def test_eight_billion_response_rejects_four_billion_identity_without_tool_execution(self):
        before = self.study.observe()
        self.configure(max_requests=1, weights=EIGHT_B_WEIGHTS)
        server = FakeNativeServer(weights=EIGHT_B_WEIGHTS, policy=scripted_pause, response_model='qwen3:4b')
        result = self.loop.run(server)
        self.assertEqual(server.requests[0]['model'], 'qwen3:8b')
        self.assertEqual(server.timeouts, [300])
        self.assertEqual(result['calls'][0]['status'], 'invalid')
        self.assertEqual(result['calls'][0]['error_code'], 'MODEL_RESPONSE_UNVERIFIED')
        self.assertEqual(result['budget']['requests_reserved'], 1)
        self.assertEqual(self.study.observe(), before)
        self.assertEqual(C01LocalLoop(self.study.root).run(), result)

    def test_eight_billion_received_response_recovers_offline_with_frozen_identity(self):
        self.configure(max_requests=1, weights=EIGHT_B_WEIGHTS)
        server = FakeNativeServer(weights=EIGHT_B_WEIGHTS, policy=scripted_pause)
        with patch.object(self.loop, '_consume', side_effect=RuntimeError('synthetic crash after 8B receipt')):
            with self.assertRaisesRegex(RuntimeError, '8B receipt'): self.loop.run(server)
        received = self.loop.status()
        self.assertEqual(received['calls'][0]['status'], 'received')
        recovered = C01LocalLoop(self.study.root).run(max_new_requests=0)
        self.assertEqual(recovered['model_identity'], received['model_identity'])
        self.assertEqual(recovered['calls'][0]['status'], 'applied')
        self.assertEqual(recovered['study']['status'], 'paused')
        self.assertEqual(recovered['budget']['requests_reserved'], 1)
        self.assertEqual(len(server.requests), 1)

    def test_cli_forwards_eight_billion_selection_and_auto_resumes_frozen_model(self):
        import run_local_research as cli
        instances = []
        class FakeOwned(FakeNativeServer):
            def __init__(self, *_args, **options):
                if options.get('model') != 'qwen3:8b': raise AssertionError('8B CLI selection was lost')
                super().__init__(weights=EIGHT_B_WEIGHTS)
                self.identity = {'selected_model': 'qwen3:8b', 'simulation_notice': 'no real process/model'}
                self.stopped = False
                self.generated_task_key_files_removed = 0
                instances.append(self)
            def __enter__(self): return self
            def __exit__(self, *_): self.stopped = True
            def acquire(self):
                if self.acquisitions: raise AssertionError('acquire must happen once per owned lifetime')
                return super().acquire()
        output = self.base.root/'eight-b-cli'
        arguments = ['local-loop', '--workspace', str(self.study.root), '--output', str(output),
                     '--cache', str(self.base.root/'unused-synthetic-cache'), '--model', 'qwen3:8b', '--max-new-requests', '1']
        with patch.object(cli, 'OwnedOllama', FakeOwned), patch.object(sys, 'argv', arguments):
            self.assertEqual(cli.main(), 0)
        self.assertEqual(len(instances), 1)
        self.assertEqual(instances[0].acquisitions, 1)
        self.assertEqual(instances[0].requests[0]['model'], 'qwen3:8b')
        self.assertEqual(instances[0].timeouts, [300])
        self.assertTrue(instances[0].stopped)
        self.assertEqual(self.loop.status()['model_identity']['model'], 'qwen3:8b')
        self.assertEqual(self.loop.status()['budget']['requests_reserved'], 1)
        # A later CLI process without --model must retain the frozen 8B profile.
        resumed_output = self.base.root/'eight-b-cli-auto-resume'
        resumed_arguments = ['local-loop', '--workspace', str(self.study.root), '--output', str(resumed_output),
                             '--cache', str(self.base.root/'unused-synthetic-cache'), '--max-new-requests', '1']
        with patch.object(cli, 'OwnedOllama', FakeOwned), patch.object(sys, 'argv', resumed_arguments):
            self.assertEqual(cli.main(), 0)
        self.assertEqual(len(instances), 2)
        self.assertEqual(instances[1].acquisitions, 1)
        self.assertEqual(instances[1].requests[0]['model'], 'qwen3:8b')
        self.assertEqual(instances[1].timeouts, [300])
        self.assertTrue(instances[1].stopped)
        self.assertEqual(self.loop.status()['budget']['requests_reserved'], 2)
        self.assertEqual([action['action'] for action in self.study.observe()['actions']], ['search', 'fit'])

    def test_cli_explicit_model_conflict_rejects_before_recovery_or_owned_process(self):
        import run_local_research as cli
        self.configure(max_requests=1, weights=EIGHT_B_WEIGHTS)
        server = FakeNativeServer(weights=EIGHT_B_WEIGHTS, policy=scripted_pause)
        with patch.object(self.loop, '_consume', side_effect=RuntimeError('synthetic received pending')):
            with self.assertRaisesRegex(RuntimeError, 'received pending'): self.loop.run(server)
        before = self.loop.status()
        self.assertEqual(before['calls'][0]['status'], 'received')
        output = self.base.root/'conflicting-model-cli'
        arguments = ['local-loop', '--workspace', str(self.study.root), '--output', str(output),
                     '--cache', str(self.base.root/'unused-synthetic-cache'), '--model', 'qwen3:4b', '--max-new-requests', '0']
        with patch.object(cli, 'OwnedOllama', side_effect=AssertionError('must reject before startup/download')), \
             patch.object(C01LocalLoop, 'run', side_effect=AssertionError('must reject before pending recovery')), \
             patch.object(sys, 'argv', arguments):
            self.assertEqual(cli.main(), 1)
        failure = json.loads((output/'failure.json').read_text(encoding='utf-8'))
        self.assertEqual(failure['code'], 'CONFIG_CHANGED')
        self.assertFalse(failure['automatic_retry'])
        self.assertEqual(self.loop.status(), before)
        self.assertEqual(len(server.requests), 1)

    def pending_fit(self):
        server = FakeNativeServer()
        self.configure()
        self.loop.run(server, max_new_requests=1)  # Obtain a real fixture citation first.
        with patch.object(self.loop, '_consume', side_effect=RuntimeError('crash after received fit')):
            with self.assertRaisesRegex(RuntimeError, 'received fit'):
                self.loop.run(server, max_new_requests=1)
        state = self.loop.status()
        self.assertEqual(state['calls'][-1]['status'], 'received')
        self.assertEqual(self.study.observe()['budget']['fits_used'], 0)
        return state['calls'][-1]['id'], server

    def test_scripted_five_steps_use_actual_feedback_ids_and_keep_c01_identity(self):
        before, identity = self.study.observe(), c01_research.code_identity()
        self.configure()
        self.assertEqual(self.study.observe(), before)
        server = FakeNativeServer()
        result = self.loop.run(server)
        actions = result['study']['actions']
        self.assertEqual([action['action'] for action in actions], ['search', 'fit', 'residuals', 'correlation', 'stop'])
        self.assertEqual(result['status'], 'completed')
        self.assertEqual(result['study']['status'], 'stopped')
        self.assertEqual(result['budget']['requests_reserved'], 5)
        self.assertEqual(result['study']['budget']['fits_used'], 1)
        self.assertEqual(result['native_usage'], {'prompt_tokens': 615, 'completion_tokens': 185})
        self.assertEqual(len(server.requests), 5)
        self.assertEqual(server.acquisitions, 1)
        for request, action in zip(server.requests, actions):
            context = json.loads(request['messages'][-1]['content'])['research_context']
            self.assertEqual(action['observation_sha256'], context['observation_sha256'])
            self.assertTrue(context['summary_not_full_observation'])
            self.assertLessEqual(len(canonical(request).encode('utf-8')), 65536)
        self.assertEqual(actions[2]['parameters']['fit_action_id'], actions[1]['id'])
        self.assertEqual(len(actions[1]['result']['predictions']), 32)
        self.assertFalse(result['scientific_validation'])
        self.assertFalse(result['llm_weight_training'])
        self.assertEqual(result['cloud_calls'], 0)
        self.assertEqual(c01_research.code_identity(), identity)
        self.assertEqual(C01LocalLoop(self.study.root).run(max_new_requests=0), result)

    def test_request_is_persisted_before_transport_and_count_survives_instances(self):
        self.configure(max_requests=2)
        def durable(body):
            with C01LocalLoop(self.study.root)._connect() as con:
                row = con.execute('SELECT * FROM calls ORDER BY ordinal DESC LIMIT 1').fetchone()
                self.assertEqual(row['status'], 'sending')
                self.assertEqual(row['request_sha256'], fingerprint(body))
                self.assertEqual(json.loads(row['request_json']), body)
                self.assertEqual(json.loads(row['observation_json'])['observation_sha256'],
                                 json.loads(body['messages'][-1]['content'])['research_context']['observation_sha256'])
        server = FakeNativeServer(before_request=durable)
        first = self.loop.run(server, max_new_requests=1)
        self.assertEqual(first['budget']['requests_reserved'], 1)
        restarted = C01LocalLoop(self.study.root)
        restarted.configure(copy.deepcopy(WEIGHTS), max_requests=2)
        second = restarted.run(server, max_new_requests=1)
        self.assertEqual(second['budget'], {'max_requests': 2, 'requests_reserved': 2})
        self.assertEqual(second['reason'], 'REQUEST_LIMIT')
        self.assertEqual(len(server.requests), 2)
        # Exhaustion never requires a server, model key, or fresh acquisition.
        self.assertEqual(C01LocalLoop(self.study.root).run(), second)

    def test_unknown_sending_is_never_resent_or_reset(self):
        self.configure(max_requests=1)  # Unknown final slot must win over budget exhaustion.
        server = FakeNativeServer(policy=scripted_pause)
        with patch.object(self.loop, '_received', side_effect=RuntimeError('response commit interrupted')):
            with self.assertRaisesRegex(RuntimeError, 'commit interrupted'):
                self.loop.run(server, max_new_requests=1)
        before = self.loop.status()
        self.assertEqual(before['calls'][0]['status'], 'sending')
        self.assertEqual(before['study']['actions'], [])
        restarted = C01LocalLoop(self.study.root)
        restarted.configure(copy.deepcopy(WEIGHTS), max_requests=1)
        for supplied in (None, server):
            with self.assertRaises(ResearchError) as error: restarted.run(supplied)
            self.assertEqual(error.exception.code, 'NEEDS_REVIEW')
        self.assertEqual(len(server.requests), 1)
        self.assertEqual(restarted.status()['budget'], before['budget'])

    def test_received_is_recovered_without_server_or_new_request(self):
        self.configure(max_requests=1)  # Received final slot still recovers before budget termination.
        server = FakeNativeServer(policy=scripted_pause)
        with patch.object(self.loop, '_consume', side_effect=RuntimeError('after received')):
            with self.assertRaisesRegex(RuntimeError, 'after received'):
                self.loop.run(server, max_new_requests=1)
        self.assertEqual(self.loop.status()['calls'][0]['status'], 'received')
        recovered = C01LocalLoop(self.study.root).run(max_new_requests=0)
        self.assertEqual(recovered['calls'][0]['status'], 'applied')
        self.assertEqual(recovered['study']['budget']['actions_used'], 1)
        self.assertEqual(recovered['study']['status'], 'paused')
        self.assertEqual(recovered['budget']['requests_reserved'], 1)
        self.assertEqual(len(server.requests), 1)

    def test_cli_recovers_empty_journal_and_acquires_only_once_in_owned_lifetime(self):
        import run_local_research as cli
        self.loop.db.touch()  # Exclusive creation committed, configure transaction did not.
        self.assertFalse(cli.has_configuration(self.loop))
        instances = []
        class FakeOwned(FakeNativeServer):
            def __init__(self, *_args, **_options):
                super().__init__()
                self.identity = {'simulation_notice': 'fake owned lifetime; no executable or model launched'}
                self.stopped = False
                self.generated_task_key_files_removed = 0
                instances.append(self)
            def __enter__(self): return self
            def __exit__(self, *_): self.stopped = True
            def acquire(self):
                if self.acquisitions:
                    raise FileExistsError('simulated native evidence open(x): acquire was called twice')
                return super().acquire()
        output = self.base.root / 'empty-journal-cli'
        arguments = ['local-loop', '--workspace', str(self.study.root), '--output', str(output),
                     '--cache', str(self.base.root/'unused-synthetic-cache'), '--max-new-requests', '1']
        with patch.object(cli, 'OwnedOllama', FakeOwned), patch.object(sys, 'argv', arguments):
            result = cli.main()
        self.assertEqual(result, 0)
        self.assertTrue(cli.has_configuration(self.loop))
        self.assertEqual(len(instances), 1)
        self.assertEqual(instances[0].acquisitions, 1)
        self.assertEqual(len(instances[0].requests), 1)
        self.assertTrue(instances[0].stopped)
        state = self.loop.status()
        self.assertEqual(state['budget']['requests_reserved'], 1)
        self.assertEqual([action['action'] for action in state['study']['actions']], ['search'])
        self.assertTrue(json.loads((output/'shutdown.json').read_text(encoding='utf-8'))['owned_server_stopped'])

    def test_tool_commit_before_journal_receipt_recovers_idempotently_without_refit(self):
        # The already-sent fit had two slots left; recovery now has only one.
        # Its stored schema, not a newly generated terminal-only schema, applies.
        self.configure(max_requests=3)
        server = FakeNativeServer()
        self.loop.run(server, max_new_requests=1)
        with patch.object(self.loop, '_record_applied', side_effect=RuntimeError('after actual fit commit')):
            with self.assertRaisesRegex(RuntimeError, 'actual fit commit'):
                self.loop.run(server, max_new_requests=1)
        before = self.study.observe()
        self.assertEqual(before['budget']['fits_used'], 1)
        self.assertEqual(self.loop.status()['calls'][-1]['status'], 'received')
        with patch.object(c01_research.C01Research, '_execute', side_effect=AssertionError('committed tools must not rerun')):
            recovered = C01LocalLoop(self.study.root).run(max_new_requests=0)
        self.assertEqual(self.study.observe(), before)
        self.assertEqual(recovered['calls'][-1]['status'], 'applied')
        self.assertEqual(recovered['calls'][-1]['action_id'], before['actions'][-1]['id'])
        self.assertEqual(recovered['budget']['requests_reserved'], 2)
        self.assertEqual(len(server.requests), 2)

    def test_project_protocol_progress_and_longer_quotes_preserve_the_observation(self):
        self.base.search()
        self.base.search()  # Same hit again: tool activity adds no new citation.
        observation = self.study.observe()
        before = copy.deepcopy(observation)
        body = native_request(observation, 4)
        context = json.loads(body['messages'][-1]['content'])['research_context']
        protocol = context['project_evaluation_protocol']
        self.assertIsNone(context['feedback_binding']['action_id'])  # Searches are not numerical feedback.
        self.assertIsNone(context['feedback_binding']['result_sha256'])
        self.assertIn('residuals',context['feedback_binding']['required_for_actions'])
        self.assertEqual(protocol['study_configuration_sha256'], observation['configuration_sha256'])
        self.assertEqual(protocol['n'], 8)
        self.assertEqual(protocol['sample_unit'], 'alloy_aggregate')
        self.assertEqual(protocol['targets'], observation['data']['targets'])
        self.assertEqual(len(protocol['targets']), 4)
        self.assertEqual(protocol['fits_per_recipe'], 32)
        self.assertIn('7 training', protocol['partition'])
        self.assertIn('1 held-out', protocol['partition'])
        self.assertIn('StandardScaler fitted only on training rows', protocol['estimator'])
        self.assertIn('Ridge(alpha, solver=svd)', protocol['estimator'])
        self.assertIn('alpha * ||w||_2^2', protocol['objective'])
        self.assertIn('larger alpha means stronger', protocol['alpha_semantics'])
        self.assertIn('does not guarantee lower held-out error', protocol['alpha_semantics'])
        self.assertIn('without target scaling', protocol['target_scaling'])
        self.assertIn('eight held-out predictions together', protocol['metric_aggregation'])
        self.assertIn('R2 may be negative', protocol['baseline_r2'])
        self.assertIn('strictly lower MAE', protocol['comparison_rule'])
        self.assertIn('do not by themselves prove an input error', protocol['prediction_bounds'])
        self.assertIn('No refitting', protocol['diagnostic_tools']['residuals'])
        self.assertIn('water_contact_angle_deg and cell_seeding_efficiency_24h_pct', protocol['diagnostic_tools']['correlation'])
        self.assertIn('training-fold', protocol['baseline'])
        self.assertIn('not an author-paper claim', protocol['authority'])
        self.assertIn('do not require papers', protocol['source_role'])
        self.assertNotIn('alpha', protocol)  # No controller-chosen numerical recipe.
        progress = context['research_progress']
        self.assertEqual([entry['parameters'] for entry in progress['executed_searches']],
                         [entry['parameters'] for entry in observation['actions']])
        self.assertEqual([entry['new_citations'] for entry in progress['executed_searches']], [1, 0])
        self.assertEqual(progress['distinct_citations'], 1)
        self.assertEqual(progress['last_search_new_citations'], 0)
        self.assertEqual(observation, before)

        # Projection-only fixture: verify useful quotation capacity, never alter a
        # persisted citation or its source identity to manufacture evidence.
        long_observation = copy.deepcopy(observation)
        long_observation['citations'][0]['quote'] = 'SOURCE-CONTEXT-' + 'x' * 600
        projected = json.loads(native_request(long_observation, 4)['messages'][-1]['content'])['research_context']
        reference = projected['references'][0]
        self.assertEqual(reference['quote'], long_observation['citations'][0]['quote'][:480])
        self.assertTrue(reference['quote_truncated'])
        self.assertEqual(reference['citation_id'], observation['citations'][0]['citation_id'])

    def test_search_signature_normalizes_effective_parameters_without_rewriting_them(self):
        original = {'query': '  C01   ALLOY\n', 'kinds': sorted(KINDS, reverse=True), 'limit': 4}
        frozen = copy.deepcopy(original)
        self.assertEqual(search_signature(original), search_signature({'query': 'c01 alloy'}))
        self.assertEqual(original, frozen)
        self.assertEqual(search_signature({'query': 'C01 alloy', 'kinds': ['reuse_note', 'research_paper', 'reuse_note']}),
                         search_signature({'query': 'c01  alloy', 'kinds': ['research_paper', 'reuse_note'], 'limit': 4}))
        for changed in ({'query': 'C01 method'}, {'query': 'C01 alloy', 'limit': 2},
                        {'query': 'C01 alloy', 'kinds': ['reuse_note']}):
            self.assertNotEqual(search_signature(original), search_signature(changed))
        selected={'query':'C01 alloy','document_id':'known-document','source_sha256':'a'*64}
        self.assertNotEqual(search_signature(original),search_signature(selected))
        self.assertEqual(search_signature(selected),search_signature({**selected,'query':' C01  ALLOY '}))
        self.assertNotEqual(search_signature(selected),search_signature({**selected,'document_id':'another-document'}))
        with self.assertRaises(ResearchError):search_signature({'query':'C01 alloy','document_id':'partial-pair'})

    def test_duplicate_search_spends_request_but_does_not_execute_or_rewrite_the_tool(self):
        self.configure(max_requests=3)  # Both issued requests still offer search.
        first_parameters = {'query': '  C01   ALLOY  ', 'kinds': sorted(KINDS, reverse=True), 'limit': 4}
        def choose(context):
            return {'action': 'search', 'observation_sha256': context['observation_sha256'],
                    'reason': 'SIMULATED equivalent-query retry for duplicate-search rejection.',
                    'source_citation_ids': context['known_source_citation_ids'][:1], 'evidence_action_ids': [],
                    'parameters': copy.deepcopy(first_parameters) if not context['actions'] else {'query': 'c01 alloy'}}
        server = FakeNativeServer(policy=choose)
        result = self.loop.run(server, max_new_requests=2)
        self.assertEqual([row['status'] for row in result['calls']], ['applied', 'invalid'])
        self.assertEqual(result['calls'][1]['error_code'], 'DUPLICATE_SEARCH')
        self.assertEqual(result['budget']['requests_reserved'], 2)
        self.assertEqual(result['study']['budget']['actions_used'], 1)
        self.assertEqual(result['study']['actions'][0]['parameters'], first_parameters)
        with self.loop._connect() as con:
            rows = list(con.execute('SELECT request_json,request_sha256,response_json FROM calls ORDER BY ordinal'))
        for row in rows: self.assertEqual(fingerprint(json.loads(row['request_json'])), row['request_sha256'])
        raw_first = json.loads(json.loads(rows[0]['response_json'])['message']['content'])
        self.assertEqual(raw_first['parameters'], first_parameters)
        self.assertEqual(len(server.requests), 2)

    def test_committed_first_search_replays_with_saved_scope_without_false_duplicate(self):
        self.configure(max_requests=2)
        server = FakeNativeServer()
        with patch.object(self.loop, '_record_applied', side_effect=RuntimeError('after first search commit')):
            with self.assertRaisesRegex(RuntimeError, 'first search commit'):
                self.loop.run(server, max_new_requests=1)
        before = self.study.observe()
        self.assertEqual(len(before['actions']), 1)
        self.assertEqual(self.loop.status()['calls'][0]['status'], 'received')
        with patch.object(c01_research.C01Research, '_execute', side_effect=AssertionError('replay cannot execute search again')):
            recovered = C01LocalLoop(self.study.root).run(max_new_requests=0)
        self.assertEqual(recovered['calls'][0]['status'], 'applied')
        self.assertIsNone(recovered['calls'][0]['error_code'])
        self.assertEqual(self.study.observe(), before)
        self.assertEqual(len(server.requests), 1)

    def test_terminal_request_offers_only_control_and_respects_model_chosen_pause(self):
        initial = self.study.observe()
        offered = lambda schema: {name for variant in schema['oneOf'] for name in variant['properties']['action']['enum']}
        self.assertEqual(offered(native_schema(initial, terminal_only=True)), {'pause', 'stop'})
        for remaining in (0, 1):
            self.assertEqual(offered(native_request(initial, remaining)['format']), {'pause', 'stop'})
        self.assertIn('search', offered(native_request(initial, 2)['format']))
        self.configure(max_requests=2)
        reason = 'SIMULATED model chooses pause at the final request; no mandatory fitting.'
        def choose(context):
            decision = scripted_fixture.decision(context)
            if context['remaining_model_requests'] <= 1:
                decision.update(action='pause', parameters={}, reason=reason)
            return decision
        server = FakeNativeServer(policy=choose)
        result = self.loop.run(server)
        self.assertEqual([action['action'] for action in result['study']['actions']], ['search', 'pause'])
        self.assertEqual(result['study']['actions'][-1]['reason'], reason)
        self.assertEqual(result['study']['status'], 'paused')
        self.assertEqual(result['study']['budget']['fits_used'], 0)
        self.assertEqual(result['budget']['requests_reserved'], 2)
        self.assertEqual(offered(server.requests[-1]['format']), {'pause', 'stop'})

    def test_terminal_native_fit_is_rejected_even_when_original_tool_contract_allows_it(self):
        self.base.search()  # The ordinary C01 contract would now permit a fit.
        before = self.study.observe()
        self.configure(max_requests=1)
        server = FakeNativeServer()  # Intentionally violates the offered terminal schema.
        result = self.loop.run(server)
        self.assertEqual(result['calls'][0]['status'], 'invalid')
        self.assertEqual(result['calls'][0]['error_code'], 'ACTION_NOT_AVAILABLE')
        self.assertEqual(result['budget']['requests_reserved'], 1)
        self.assertEqual(self.study.observe(), before)
        self.assertEqual(self.study.observe()['budget']['fits_used'], 0)
        self.assertEqual(len(server.requests), 1)

    def test_invalid_native_decisions_spend_only_model_requests_and_feed_errors_back(self):
        before = self.study.observe()
        self.configure(max_requests=2)
        server = FakeNativeServer(policy=lambda _: 'not a JSON decision')
        result = self.loop.run(server)
        self.assertEqual(result['reason'], 'REQUEST_LIMIT')
        self.assertEqual([call['status'] for call in result['calls']], ['invalid', 'invalid'])
        self.assertEqual(self.study.observe(), before)
        self.assertEqual(result['budget']['requests_reserved'], 2)
        second_context = json.loads(server.requests[1]['messages'][-1]['content'])['research_context']
        self.assertEqual(second_context['previous_errors'], ['INVALID_DECISION'])
        self.assertEqual(len(server.requests), 2)

    def test_frozen_model_budget_and_native_identity_cannot_be_reconfigured(self):
        initial = self.configure(max_requests=3)
        changed = {**WEIGHTS, 'manifest_sha256': 'c' * 64}
        for weights, count, expected in ((changed, 3, 'CONFIG_CHANGED'), (WEIGHTS, 4, 'CONFIG_CHANGED'),
                                         ({**WEIGHTS, 'native_model_digest': 'd'*64}, 3, 'MODEL_CHANGED')):
            with self.subTest(expected=expected, count=count):
                with self.assertRaises(ResearchError) as error:
                    C01LocalLoop(self.study.root).configure(copy.deepcopy(weights), max_requests=count)
                self.assertEqual(error.exception.code, expected)
                self.assertEqual(self.loop.status(), initial)
        wrong = FakeNativeServer(weights=changed)
        with self.assertRaises(ResearchError) as error: self.loop.run(wrong, max_new_requests=1)
        self.assertEqual(error.exception.code, 'MODEL_CHANGED')
        self.assertEqual(wrong.requests, [])
        self.assertEqual(self.loop.status()['budget']['requests_reserved'], 0)

    def test_concurrent_consumers_never_invalidate_or_repeat_a_fit(self):
        call_id, server = self.pending_fit()
        start = threading.Barrier(3)
        errors, executed = [], []
        execute = c01_research.C01Research._execute
        def counted(*args):
            if args[0] == 'fit':
                executed.append(True)
                time.sleep(.1)
            return execute(*args)
        def consume():
            try:
                start.wait(timeout=5)
                C01LocalLoop(self.study.root)._consume(call_id)
            except BaseException as error: errors.append(error)
        workers = [threading.Thread(target=consume) for _ in range(2)]
        with patch.object(c01_research.C01Research, '_execute', side_effect=counted):
            for worker in workers: worker.start()
            try: start.wait(timeout=5)
            finally:
                for worker in workers: worker.join(15)
        self.assertTrue(all(not worker.is_alive() for worker in workers))
        self.assertEqual(errors, [])
        self.assertEqual(len(executed), 1)
        result = self.loop.status()
        self.assertEqual(result['calls'][-1]['status'], 'applied')
        self.assertEqual(result['study']['budget']['fits_used'], 1)
        self.assertEqual(result['study']['budget']['actions_used'], 2)
        self.assertEqual(len(server.requests), 2)

    def test_concurrent_runs_do_not_double_reserve_or_dispatch(self):
        self.configure()
        entered, release = threading.Event(), threading.Event()
        errors = []
        def slow(_):
            entered.set()
            if not release.wait(5): raise RuntimeError('simulated dispatch timeout')
        server = FakeNativeServer(before_request=slow)
        def first():
            try: self.loop.run(server, max_new_requests=1)
            except BaseException as error: errors.append(error)
        worker = threading.Thread(target=first)
        worker.start()
        try:
            self.assertTrue(entered.wait(5))
            with self.assertRaises(ResearchError) as error:
                C01LocalLoop(self.study.root).run(server, max_new_requests=1)
            self.assertIn(error.exception.code, {'BUSY', 'NEEDS_REVIEW'})
        finally:
            release.set()
            worker.join(15)
        self.assertFalse(worker.is_alive())
        self.assertEqual(errors, [])
        self.assertEqual(len(server.requests), 1)
        self.assertEqual(self.loop.status()['budget']['requests_reserved'], 1)

    def test_schema_permissions_follow_actual_evidence_and_remaining_action_slot(self):
        initial = self.study.observe()
        actions = lambda obs: {branch['properties']['action']['enum'][0] for branch in native_schema(obs)['oneOf']}
        self.assertEqual(actions(initial), {'search', 'read_source', 'inspect_dataset', 'pause', 'stop'})
        self.base.search()
        current = self.study.observe()
        self.assertIn('fit', actions(current))
        final_slot = copy.deepcopy(current)
        final_slot['budget']['actions_used'] = final_slot['budget']['max_actions'] - 1
        self.assertEqual(actions(final_slot), {'pause', 'stop'})
        body = native_request(current, 2, ['INVALID_DECISION'])
        context = json.loads(body['messages'][-1]['content'])['research_context']
        self.assertEqual(context['observation_sha256'], current['observation_sha256'])
        self.assertEqual(context['remaining_model_requests'], 2)
        self.assertEqual(context['previous_errors'], ['INVALID_DECISION'])


if __name__ == '__main__': unittest.main()
