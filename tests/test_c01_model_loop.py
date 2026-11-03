import copy
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import threading
import unittest
from unittest.mock import patch

from autoresearch import c01_research
from autoresearch.c01_model_loop import C01ModelLoop, SYSTEM, build_context
from autoresearch.contracts import ResearchError, canonical
from autoresearch.model_client import ChatClient
import test_c01_research as study_fixture

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import c01_model_fixture as fixture


class C01ModelLoopTests(unittest.TestCase):
    def setUp(self):
        self.base = study_fixture.C01ResearchTests('test_terminal_decision_is_durable_and_stops_new_dispatch')
        self.base.setUp()
        self.addCleanup(self.base.doCleanups)
        self.loop = C01ModelLoop(self.base.study.root)
        self.env = patch.dict(os.environ, {fixture.KEY_ENV: fixture.FIXTURE_KEY})
        self.env.start()
        self.addCleanup(self.env.stop)

    def configure(self, endpoint, **options):
        self.config = fixture.configuration(endpoint)
        return self.loop.configure(self.config, **options)

    def cli(self, *args, key=True):
        environment = os.environ.copy()
        environment['PYTHONPATH'] = str(Path(__file__).resolve().parents[1] / 'src')
        if not key: environment.pop(fixture.KEY_ENV, None)
        command = [sys.executable, '-B', str(Path(__file__).resolve().parents[1] / 'scripts/c01_model_loop.py'), *args,
                   '--workspace', str(self.base.study.root)]
        completed = subprocess.run(command, env=environment, capture_output=True, text=True, encoding='utf-8', timeout=30)
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        return json.loads(completed.stdout)['result']

    def test_five_http_actions_use_actual_ids_and_unchanged_c01_identity(self):
        code_sha = c01_research.code_identity()
        observation = self.base.study.observe()
        with fixture.model_fixture() as (endpoint, records):
            self.configure(endpoint)
            self.assertEqual(self.base.study.observe(), observation)
            result = self.loop.run()
            self.assertEqual([row['action'] for row in result['study']['actions']], ['search', 'fit', 'residuals', 'correlation', 'stop'])
            self.assertEqual(result['study']['status'], 'stopped')
            self.assertEqual(result['status'], 'completed')
            self.assertEqual(result['budget']['requests_reserved'], 5)
            self.assertEqual(len(records), 5)
            self.assertEqual([row['request_id'] for row in records], [row['request_id'] for row in result['calls']])
            for record, action in zip(records, result['study']['actions']):
                context = json.loads(record['payload']['messages'][-1]['content'])
                self.assertEqual(action['observation_sha256'], context['observation_sha256'])
                self.assertTrue(context['summary_not_full_observation'])
            self.assertEqual(result['study']['actions'][2]['parameters']['fit_action_id'], result['study']['actions'][1]['id'])
            self.assertFalse(result['scientific_validation'])
            self.assertEqual(result['cloud_calls'], 0)
            self.assertEqual(len(result['study']['actions'][1]['result']['predictions']), 32)
        self.assertEqual(c01_research.code_identity(), code_sha)

    def test_independent_process_step_limit_continues_without_reset(self):
        with fixture.model_fixture() as (endpoint, records):
            self.configure(endpoint)
            first = self.cli('run', '--max-new-requests', '2')
            self.assertEqual(first['status'], 'active')
            self.assertEqual(first['budget']['requests_reserved'], 2)
            second = self.cli('run', '--max-new-requests', '8')
            self.assertEqual(second['status'], 'completed')
            self.assertEqual(second['budget']['requests_reserved'], 5)
            self.assertEqual(len(records), 5)
            self.assertEqual(len(second['study']['actions']), 5)

    def test_received_is_consumed_in_another_process_without_key_or_http(self):
        with fixture.model_fixture() as (endpoint, records):
            self.configure(endpoint)
            with patch.object(self.loop, '_consume', side_effect=RuntimeError('crash after received commit')):
                with self.assertRaises(RuntimeError): self.loop.run(max_new_requests=1)
            self.assertEqual(self.loop.status()['calls'][0]['status'], 'received')
            recovered = self.cli('run', '--max-new-requests', '0', key=False)
            self.assertEqual(len(records), 1)
            self.assertEqual(recovered['calls'][0]['status'], 'applied')
            self.assertEqual(len(recovered['study']['actions']), 1)

    def test_crash_after_actual_fit_before_runner_receipt_never_refits(self):
        with fixture.model_fixture() as (endpoint, records):
            self.configure(endpoint)
            self.loop.run(max_new_requests=1)
            with patch.object(self.loop, '_record_applied', side_effect=RuntimeError('crash after actual fit commit')):
                with self.assertRaises(RuntimeError): self.loop.run(max_new_requests=1)
            self.assertEqual(self.base.study.observe()['budget']['fits_used'], 1)
            self.assertEqual(self.loop.status()['calls'][-1]['status'], 'received')
            with patch.object(c01_research.C01Research, '_execute', side_effect=AssertionError('must not repeat committed work')):
                recovered = C01ModelLoop(self.base.study.root).run(max_new_requests=0)
            self.assertEqual(recovered['study']['budget']['fits_used'], 1)
            self.assertEqual(recovered['calls'][-1]['status'], 'applied')
            self.assertEqual(len(records), 2)

    def test_unknown_sending_never_resends_or_refunds_without_reconciliation(self):
        with fixture.model_fixture() as (endpoint, records):
            self.configure(endpoint)
            with patch.object(self.loop, '_received', side_effect=RuntimeError('crash before response commit')):
                with self.assertRaises(RuntimeError): self.loop.run(max_new_requests=1)
            before = self.loop.status()
            with self.assertRaises(ResearchError) as error: self.loop.run()
            self.assertEqual(error.exception.code, 'NEEDS_REVIEW')
            self.assertEqual(len(records), 1)
            call_id = before['calls'][0]['id']
            with self.assertRaises(ResearchError): self.loop.reconcile(call_id)
            recovered = self.loop.reconcile(call_id, confirm_worker_stopped=True)
            self.assertEqual(recovered['budget'], before['budget'])
            self.loop.run(max_new_requests=1)
            self.assertEqual(len(records), 2)
            self.assertNotEqual(records[0]['request_id'], records[1]['request_id'])
            self.assertEqual(self.loop.status()['calls'][0]['accounted_micros'], None)

    def test_concurrent_runners_reserve_only_one_network_request(self):
        entered, release, errors = threading.Event(), threading.Event(), []
        original = ChatClient.complete
        def slow(client, messages, request_id):
            entered.set()
            if not release.wait(5): raise RuntimeError('test timeout')
            return original(client, messages, request_id)
        def run():
            try: self.loop.run(max_new_requests=1)
            except Exception as error: errors.append(error)
        with fixture.model_fixture() as (endpoint, records):
            self.configure(endpoint)
            with patch.object(ChatClient, 'complete', new=slow):
                worker = threading.Thread(target=run)
                worker.start()
                try:
                    self.assertTrue(entered.wait(5))
                    with self.assertRaises(ResearchError) as error: C01ModelLoop(self.base.study.root).run(max_new_requests=1)
                    self.assertIn(error.exception.code, {'BUSY', 'NEEDS_REVIEW'})
                finally:
                    release.set(); worker.join(10)
            self.assertFalse(worker.is_alive())
            self.assertEqual(errors, [])
            self.assertEqual(len(records), 1)
            self.assertEqual(self.loop.status()['budget']['requests_reserved'], 1)

    def test_invalid_responses_use_request_budget_but_no_action(self):
        observation = self.base.study.observe()
        with fixture.model_fixture('always_invalid') as (endpoint, records):
            self.configure(endpoint, max_requests=2)
            result = self.loop.run()
            self.assertEqual(len(records), 2)
            self.assertEqual(result['status'], 'completed')
            self.assertEqual(result['reason'], 'MODEL_BUDGET_EXHAUSTED')
            self.assertTrue(all(row['status'] == 'invalid' for row in result['calls']))
            self.assertEqual(self.base.study.observe(), observation)
            with patch.dict(os.environ, {}, clear=True):
                self.assertEqual(self.loop.run()['budget']['requests_reserved'], 2)

    def test_virtual_budget_exhaustion_needs_no_key_and_no_http(self):
        with fixture.model_fixture() as (endpoint, records):
            self.configure(endpoint, max_cost_cny='0.000001')
            with patch.dict(os.environ, {}, clear=True): result = self.loop.run()
            self.assertEqual(result['status'], 'completed')
            self.assertEqual(result['budget']['requests_reserved'], 0)
            self.assertEqual(records, [])

    def test_live_localhost_and_real_credential_env_are_rejected_before_writes(self):
        before = hashlib.sha256(self.base.study.db.read_bytes()).hexdigest()
        for endpoint in ('https://api.deepseek.com/v1/chat/completions', 'http://localhost:8000/chat',
                         'https://127.0.0.1.example.invalid/chat', 'https://[::ffff:127.0.0.1]/chat'):
            config = fixture.configuration(endpoint)
            with patch.object(ChatClient, 'preflight', side_effect=AssertionError('no credential read')):
                with self.assertRaises(ResearchError): self.loop.configure(config)
            self.assertEqual(hashlib.sha256(self.base.study.db.read_bytes()).hexdigest(), before)
        config = fixture.configuration('http://127.0.0.1:9/chat')
        config['connection']['api_key_env'] = 'AUTORESEARCH_API_KEY'
        with self.assertRaises(ResearchError): self.loop.configure(config)
        self.assertEqual(hashlib.sha256(self.base.study.db.read_bytes()).hexdigest(), before)
        self.configure('http://127.0.0.1:9/chat')
        with self.assertRaises(ResearchError) as error:
            self.loop.run(fixture.configuration('https://api.deepseek.com/v1/chat/completions'), allow_live=True)
        self.assertEqual(error.exception.code, 'LIVE_ACCESS_DISABLED')
        self.assertEqual(self.loop.status()['budget']['requests_reserved'], 0)

    def test_prompt_limit_fails_before_reservation(self):
        with fixture.model_fixture() as (endpoint, records):
            config = fixture.configuration(endpoint)
            config['connection']['max_prompt_bytes'] = 32
            self.loop.configure(config)
            with self.assertRaises(ResearchError): self.loop.run()
            self.assertEqual(records, [])
            self.assertEqual(self.loop.status()['budget']['requests_reserved'], 0)

    def test_context_preserves_true_hash_metrics_ids_and_late_target_audit(self):
        with fixture.model_fixture() as (endpoint, _):
            self.configure(endpoint)
            self.loop.run(max_new_requests=2)
            observation = self.base.study.observe()
        sample = copy.deepcopy(observation)
        sample['actions'] += [copy.deepcopy(sample['actions'][-1]) for _ in range(3)]
        audit = [{'field': 'missing_measurement', 'issue': 'repeated nonnumeric value', 'handling': 'excluded'} for _ in range(20)]
        audit.append({'field': 'alp_norm_d21', 'issue': 'original normalization/unit audit remains unresolved here', 'handling': 'do not silently resolve'})
        sample['data']['audit'] = audit
        context = build_context(sample, remaining_requests=3)
        self.assertEqual(context['observation_sha256'], observation['observation_sha256'])
        self.assertNotIn('"predictions":', canonical(context))
        self.assertEqual(context['known_source_citation_ids'], [item['citation_id'] for item in observation['citations']])
        self.assertTrue(any(item['field'] == 'alp_norm_d21' for item in context['audit_summary']))
        self.assertEqual(context['audit_items_omitted'], 19)
        self.assertFalse(context['audit_summary_is_complete'])
        self.assertEqual(context['actions'][1]['metrics'][0]['r2'], observation['actions'][1]['result']['summary']['metrics'][0]['r2'])
        payload = ChatClient(self.config['connection']).prepare([{'role': 'system', 'content': SYSTEM}, {'role': 'user', 'content': canonical(context)}])
        self.assertLessEqual(len(json.dumps(payload, ensure_ascii=False).encode()), 64000)

    def test_usage_overrun_preserves_accounting_and_stops_dispatch(self):
        with fixture.model_fixture('over_input') as (endpoint, records):
            self.configure(endpoint)
            with self.assertRaises(ResearchError) as error: self.loop.run()
            self.assertEqual(error.exception.code, 'COST_BOUND_EXCEEDED')
            state = self.loop.status()
            self.assertEqual(state['status'], 'needs_review')
            self.assertEqual(state['budget']['requests_reserved'], 1)
            self.assertGreater(state['calls'][0]['accounted_micros'], state['calls'][0]['reserved_micros'])
            self.loop.run()
            self.assertEqual(len(records), 1)

    def test_http_failure_retains_full_reservation_and_never_auto_retries(self):
        with fixture.model_fixture('http_error') as (endpoint, records):
            self.configure(endpoint)
            state = self.loop.run()
            self.assertEqual(state['status'], 'needs_review')
            self.assertEqual(state['calls'][0]['status'], 'failed')
            self.assertIsNone(state['calls'][0]['accounted_micros'])
            self.assertEqual(state['budget']['accounted_or_reserved_micros'], state['calls'][0]['reserved_micros'])
            self.loop.run()
            self.assertEqual(len(records), 1)
            self.assertEqual(self.base.study.observe()['budget']['actions_used'], 0)

    def test_stale_decisions_and_model_owned_request_ids_are_rejected(self):
        for field, value in (('observation_sha256', 'f' * 64), ('request_id', 'model-cannot-own-this')):
            with self.subTest(field=field), fixture.model_fixture() as (endpoint, records):
                # Each rejected response is tried in a fresh bounded study.
                other = c01_research.C01Research(self.base.root / field)
                with patch('autoresearch.c01_research.c01.load_archive', return_value=self.base.inputs):
                    other.create('synthetic-only', self.base.index, 'Invalid fixture decision contract')
                runner = C01ModelLoop(other.root)
                runner.configure(fixture.configuration(endpoint), max_requests=1)
                original = fixture.decision
                def altered(context): return {**original(context), field: value}
                with patch.object(fixture, 'decision', side_effect=altered): result = runner.run()
                self.assertEqual(len(records), 1)
                self.assertEqual(result['calls'][0]['status'], 'invalid')
                self.assertEqual(other.observe()['budget']['actions_used'], 0)

    def test_config_and_limits_cannot_reset_cumulative_work(self):
        with fixture.model_fixture() as (endpoint, _):
            self.configure(endpoint)
            self.loop.run(max_new_requests=1)
            for options in ({'max_requests': 9}, {'max_cost_cny': '4'}):
                with self.assertRaises(ResearchError): self.loop.configure(self.config, **options)
            with self.assertRaises(ResearchError): self.loop.run(max_new_requests=9)
            self.assertEqual(self.loop.configure(self.config)['budget']['requests_reserved'], 1)
            self.assertEqual(self.base.study.observe()['budget']['actions_used'], 1)


if __name__ == '__main__': unittest.main()
