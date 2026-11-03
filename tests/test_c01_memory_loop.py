import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import threading
import unittest
from unittest.mock import patch

from autoresearch import c01_research
from autoresearch.c01_memory_context import MemoryContext, projection
from autoresearch.c01_memory_loop import C01MemoryLoop
from autoresearch.c01_model_loop import C01ModelLoop, SYSTEM, build_context, _decision
from autoresearch.c01_research_outputs import public_record
from autoresearch.contracts import ResearchError, canonical, fingerprint
from autoresearch.model_client import ChatClient
from autoresearch.research_memory import ResearchMemory
import test_c01_research as study_fixture

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import c01_model_fixture as fixture


class C01MemoryLoopTests(unittest.TestCase):
    def setUp(self):
        self.base = study_fixture.C01ResearchTests('test_terminal_decision_is_durable_and_stops_new_dispatch')
        self.base.setUp()
        self.addCleanup(self.base.doCleanups)
        self.base.search()
        self.base.fit()
        self.base.study.apply(self.base.request('residuals', {'fit_action_id': self.base.study.observe()['actions'][-1]['id']}))
        self.base.study.apply(self.base.request('correlation'))
        self.base.study.apply(self.base.request('stop'))
        exported = self.base.study.export()
        self.memory = ResearchMemory(self.base.root / 'memory')
        self.memory.import_study(public_record(exported['state']), exported['reproduction'])
        self.study = c01_research.C01Research(self.base.root / 'subsequent-study')
        with patch('autoresearch.c01_research.c01.load_archive', return_value=self.base.inputs):
            self.study.create('fixture-only', self.base.index, 'Exact-scope memory mechanism test', max_fits=1)
        self.loop = C01MemoryLoop(self.study.root)
        self.env = patch.dict(os.environ, {fixture.KEY_ENV: fixture.FIXTURE_KEY})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.fit_id = next(item['record']['id'] for item in MemoryContext(self.memory.root).snapshot(self.study)['entries']
                           if item['record']['kind'] == 'fit_observation')

    def configure(self, endpoint, **options):
        self.config = fixture.configuration(endpoint)
        return self.loop.configure(self.config, memory_workspace=self.memory.root, **options)

    def retire(self):
        self.memory.set_status(self.fit_id, 'retired', 'Controlled withdrawal, not a scientific judgement.', 'withdraw-test')

    def test_full_snapshot_and_bounded_projection_persist_before_network(self):
        complete = ChatClient.complete
        def inspect(client, messages, request_id):
            with self.study._connect() as con:
                row = con.execute('SELECT * FROM c01_runner_calls WHERE request_id=?', (request_id,)).fetchone()
                snapshot, sent = self.loop._use(con, row['id'])
                self.assertEqual(row['status'], 'sending')
                self.assertEqual(json.loads(row['messages_json']), messages)
            context = json.loads(messages[-1]['content'])
            self.assertEqual(context['conditional_memory'], sent)
            self.assertEqual(projection(snapshot), sent)
            self.assertEqual(len(snapshot['entries']), 3)
            self.assertEqual(len(sent['entries']), 3)
            self.assertLessEqual(len(canonical(sent).encode()), 12288)
            self.assertNotIn(str(self.memory.root), canonical(sent))
            self.assertEqual(context['observation_sha256'], json.loads(row['observation_json'])['observation_sha256'])
            if row['ordinal'] == 1:
                self.assertEqual(context['known_source_citation_ids'], [])
                self.assertEqual(context['actions'], [])
            return complete(client, messages, request_id)
        with fixture.model_fixture() as (endpoint, records):
            self.configure(endpoint)
            with patch.object(ChatClient, 'complete', new=inspect): result = self.loop.run()
        self.assertEqual(len(records), 5)
        self.assertEqual(result['status'], 'completed')
        self.assertEqual(len(result['memory']['uses']), 5)
        self.assertEqual(result['study']['budget']['fits_used'], 1)
        self.assertTrue(all(call['status'] == 'applied' for call in result['calls']))

    def test_received_recovery_withdrawal_rejects_uncommitted_response_without_refund(self):
        with fixture.model_fixture() as (endpoint, records):
            self.configure(endpoint)
            with patch.object(self.loop, '_consume', side_effect=RuntimeError('received crash')):
                with self.assertRaises(RuntimeError): self.loop.run(max_new_requests=1)
            before = self.loop.status()
            self.retire()
            with patch.dict(os.environ, {}, clear=True): result = C01MemoryLoop(self.study.root).run(max_new_requests=0)
            self.assertEqual(len(records), 1)
            self.assertEqual(result['calls'][0]['error_code'], 'MEMORY_CONTEXT_CHANGED')
            self.assertEqual(result['calls'][0]['status'], 'invalid')
            self.assertEqual(result['budget'], before['budget'])
            self.assertEqual(result['study']['actions'], [])
            self.loop.run(max_new_requests=1)
            sent = json.loads(records[-1]['payload']['messages'][-1]['content'])['conditional_memory']
            self.assertEqual(len(sent['entries']), 2)
            self.assertNotIn(self.fit_id, [entry['id'] for entry in sent['entries']])

    def test_post_fit_crash_then_withdrawal_recovers_actual_action_without_refit(self):
        with fixture.model_fixture() as (endpoint, records):
            self.configure(endpoint)
            self.loop.run(max_new_requests=1)
            with patch.object(self.loop, '_record_applied', side_effect=RuntimeError('after fit commit')):
                with self.assertRaises(RuntimeError): self.loop.run(max_new_requests=1)
            self.retire()
            with patch.object(c01_research.C01Research, '_execute', side_effect=AssertionError('no refit')):
                with patch.dict(os.environ, {}, clear=True): result = C01MemoryLoop(self.study.root).run(max_new_requests=0)
            self.assertEqual(len(records), 2)
            self.assertEqual(result['calls'][-1]['status'], 'applied')
            self.assertEqual(result['study']['budget']['fits_used'], 1)

    def test_received_restart_uses_saved_snapshot_with_no_new_key_or_http(self):
        with fixture.model_fixture() as (endpoint, records):
            self.configure(endpoint)
            with patch.object(self.loop, '_consume', side_effect=RuntimeError('received crash')):
                with self.assertRaises(RuntimeError): self.loop.run(max_new_requests=1)
            environment = os.environ.copy()
            environment.pop(fixture.KEY_ENV, None)
            environment['PYTHONPATH'] = str(Path(__file__).resolve().parents[1] / 'src')
            result = subprocess.run([sys.executable, '-B', 'scripts/c01_memory_loop.py', 'run',
                '--workspace', str(self.study.root), '--max-new-requests', '0'], env=environment,
                capture_output=True, text=True, encoding='utf-8', timeout=30)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            state = json.loads(result.stdout)['result']
            self.assertEqual(state['calls'][0]['status'], 'applied')
            self.assertEqual(len(records), 1)

    def test_commit_during_memory_check_is_recovered_as_applied(self):
        with fixture.model_fixture() as (endpoint, records):
            self.configure(endpoint)
            self.loop.run(max_new_requests=1)
            with patch.object(self.loop, '_consume', side_effect=RuntimeError('received fit crash')):
                with self.assertRaises(RuntimeError): self.loop.run(max_new_requests=1)
            with self.study._connect() as con:
                row = dict(con.execute("SELECT * FROM c01_runner_calls WHERE status='received'").fetchone())
            request = _decision(json.loads(row['response_json'])['content'], json.loads(row['observation_json']), row['request_id'])
            original = MemoryContext.snapshot
            def committed_elsewhere(source, study):
                # Reproduce the precise review race: the first committed read was
                # false, but actual C01 work commits before the invalidation write.
                self.study.apply(request)
                self.retire()
                return original(source, study)
            with patch.object(MemoryContext, 'snapshot', new=committed_elsewhere):
                self.loop._consume(row['id'])
            result = self.loop.status()
            self.assertEqual(result['calls'][-1]['status'], 'applied')
            self.assertIsNotNone(result['calls'][-1]['action_id'])
            self.assertEqual(result['study']['budget']['fits_used'], 1)
            self.assertEqual(len(records), 2)

    def test_pending_response_has_cross_process_single_consumer_lock(self):
        with fixture.model_fixture() as (endpoint, records):
            self.configure(endpoint)
            with patch.object(self.loop, '_consume', side_effect=RuntimeError('received crash')):
                with self.assertRaises(RuntimeError): self.loop.run(max_new_requests=1)
            environment = os.environ.copy()
            environment['PYTHONPATH'] = str(Path(__file__).resolve().parents[1] / 'src')
            with self.loop._consumer_lock():
                process = subprocess.run([sys.executable, '-B', 'scripts/c01_memory_loop.py', 'run',
                    '--workspace', str(self.study.root), '--max-new-requests', '0'], env=environment,
                    capture_output=True, text=True, encoding='utf-8', timeout=30)
                self.assertEqual(process.returncode, 1, process.stdout + process.stderr)
                self.assertEqual(json.loads(process.stdout)['error']['code'], 'BUSY')
            # Existing lock file is not a stale lease and requires no manual reset.
            result = self.loop.run(max_new_requests=0)
            self.assertEqual(result['calls'][0]['status'], 'applied')
            self.assertEqual(len(records), 1)

    def test_missing_receipt_unknown_dispatch_never_resends(self):
        original = self.loop._reserve
        def interrupted(*args):
            call_id, _ = original(*args)
            with self.study._connect(True) as con:
                con.execute('DELETE FROM c01_memory_uses WHERE call_id=?', (call_id,))
            raise RuntimeError('crash before HTTP')
        with fixture.model_fixture() as (endpoint, records):
            self.configure(endpoint)
            with patch.object(self.loop, '_reserve', side_effect=interrupted):
                with self.assertRaises(RuntimeError): self.loop.run(max_new_requests=1)
            self.assertEqual(records, [])
            self.assertEqual(self.loop.status()['budget']['requests_reserved'], 1)
            with self.assertRaises(ResearchError) as error: self.loop.run()
            self.assertEqual(error.exception.code, 'NEEDS_REVIEW')

    def test_changed_persisted_projection_blocks_received_response(self):
        with fixture.model_fixture() as (endpoint, records):
            self.configure(endpoint)
            with patch.object(self.loop, '_consume', side_effect=RuntimeError('received crash')):
                with self.assertRaises(RuntimeError): self.loop.run(max_new_requests=1)
            with self.study._connect(True) as con:
                con.execute("UPDATE c01_memory_uses SET projection_json='{}'")
            with self.assertRaises(ResearchError) as error: self.loop.run(max_new_requests=0)
            self.assertEqual(error.exception.code, 'MEMORY_EVIDENCE_CHANGED')
            self.assertEqual(self.study.observe()['actions'], [])
            self.assertEqual(len(records), 1)

    def test_process_death_releases_consumer_lock_without_deleting_file(self):
        environment = os.environ.copy()
        environment['PYTHONPATH'] = str(Path(__file__).resolve().parents[1] / 'src')
        program = ('import sys,time\nfrom autoresearch.c01_memory_loop import C01MemoryLoop\n'
                   'with C01MemoryLoop(sys.argv[1])._consumer_lock():\n'
                   ' print("locked",flush=True)\n time.sleep(30)\n')
        worker = subprocess.Popen([sys.executable, '-B', '-c', program, str(self.study.root)],
                                  env=environment, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                  text=True, encoding='utf-8')
        try:
            self.assertEqual(worker.stdout.readline().strip(), 'locked')
            with self.assertRaises(ResearchError) as error:
                with self.loop._consumer_lock(): pass
            self.assertEqual(error.exception.code, 'BUSY')
        finally:
            if worker.poll() is None: worker.terminate()
            worker.communicate(timeout=10)
        self.assertTrue((self.study.root / '.c01-memory-consumer.lock').is_file())
        with self.loop._consumer_lock(): pass

    def test_corrupt_or_replaced_store_blocks_new_requests_and_preserves_history(self):
        with fixture.model_fixture() as (endpoint, records):
            self.configure(endpoint)
            self.loop.run(max_new_requests=1)
            db = self.memory.root / 'memory.sqlite'
            saved = db.read_bytes()
            db.write_bytes(b'not sqlite')
            self.assertFalse(self.loop.status()['memory']['current_readable'])
            with self.assertRaises(ResearchError): self.loop.run(max_new_requests=1)
            db.write_bytes(saved)
            replacement = self.memory.root / 'replacement.sqlite'
            replacement.write_bytes(saved)
            os.replace(replacement, db)
            self.assertEqual(self.loop.status()['memory']['error_code'], 'MEMORY_STORE_CHANGED')
            with self.assertRaises(ResearchError): self.loop.run(max_new_requests=1)
            self.assertEqual(len(records), 1)
            self.assertEqual(self.loop.status()['calls'][0]['status'], 'applied')

    def test_final_augmented_prompt_limit_checked_before_reservation(self):
        with fixture.model_fixture() as (endpoint, records):
            config = fixture.configuration(endpoint)
            context = build_context(self.study.observe(), remaining_requests=8)
            plain = [{'role': 'system', 'content': SYSTEM}, {'role': 'user', 'content': canonical(context)}]
            # Plain parent prompt fits. Adding memory must fail before a request slot or HTTP.
            config['connection']['max_prompt_bytes'] = len(json.dumps(ChatClient(config['connection']).prepare(plain), ensure_ascii=False).encode()) + 500
            self.loop.configure(config, memory_workspace=self.memory.root)
            with self.assertRaises(ResearchError): self.loop.run(max_new_requests=1)
            self.assertEqual(records, [])
            self.assertEqual(self.loop.status()['budget']['requests_reserved'], 0)

    def test_source_limits_and_mode_cannot_be_retrofitted_or_reset(self):
        with fixture.model_fixture() as (endpoint, _):
            self.configure(endpoint)
            self.loop.run(max_new_requests=1)
            self.assertEqual(self.loop.configure(self.config, memory_workspace=self.memory.root)['budget']['requests_reserved'], 1)
            other = self.base.root / 'other-memory'
            shutil.copytree(self.memory.root, other)
            for kwargs in ({'memory_workspace': other}, {'memory_workspace': self.memory.root, 'max_requests': 9}):
                with self.assertRaises(ResearchError): self.loop.configure(self.config, **kwargs)
            plain_study = c01_research.C01Research(self.base.root / 'plain-controller')
            with patch('autoresearch.c01_research.c01.load_archive', return_value=self.base.inputs):
                plain_study.create('fixture-only', self.base.index, 'Old mode cannot be silently retrofitted')
            plain = C01ModelLoop(plain_study.root)
            plain.configure(self.config)
            plain.run(max_new_requests=1)
            with self.assertRaises(ResearchError) as error:
                C01MemoryLoop(plain_study.root).configure(self.config, memory_workspace=self.memory.root)
            self.assertEqual(error.exception.code, 'MEMORY_CONFIG_CHANGED')
            old = C01ModelLoop(self.study.root).status()
            self.assertEqual(old['budget']['requests_reserved'], 1)
            live = fixture.configuration('https://api.deepseek.com/v1/chat/completions')
            with self.assertRaises(ResearchError): self.loop.run(live, allow_live=True)

    def test_historical_action_ids_cannot_authorize_a_current_experiment(self):
        source_action = next(entry['record']['provenance']['action_id']
                             for entry in MemoryContext(self.memory.root).snapshot(self.study)['entries']
                             if entry['record']['kind'] == 'fit_observation')
        def wrong_evidence(context):
            chosen = fixture.decision(context)
            if chosen['action'] == 'fit': chosen['evidence_action_ids'] = [source_action]
            return chosen
        with fixture.model_fixture(policy=wrong_evidence) as (endpoint, records):
            self.configure(endpoint, max_requests=2)
            result = self.loop.run()
            self.assertEqual(len(records), 2)
            self.assertEqual(result['calls'][-1]['status'], 'invalid')
            self.assertEqual(result['calls'][-1]['error_code'], 'INVALID_EVIDENCE')
            self.assertEqual(result['study']['budget']['fits_used'], 0)

    def test_oversized_full_snapshot_is_rejected_before_request_budget(self):
        with fixture.model_fixture() as (endpoint, records):
            self.configure(endpoint)
            snapshot = MemoryContext(self.memory.root).snapshot(self.study)
            snapshot['warning'] = 'x' * (512 * 1024)
            raw = {key: value for key, value in snapshot.items() if key not in {'snapshot_sha256', 'store_identity'}}
            snapshot['snapshot_sha256'] = fingerprint(raw)
            with patch.object(MemoryContext, 'snapshot', return_value=snapshot):
                with self.assertRaises(ResearchError) as error: self.loop.run(max_new_requests=1)
            self.assertEqual(error.exception.code, 'MEMORY_CONTEXT_TOO_LARGE')
            self.assertEqual(records, [])
            self.assertEqual(self.loop.status()['budget']['requests_reserved'], 0)

    def test_concurrent_memory_workers_reserve_only_one_request(self):
        entered, release, errors = threading.Event(), threading.Event(), []
        original = ChatClient.complete
        def slow(client, messages, request_id):
            entered.set()
            if not release.wait(10): raise RuntimeError('test timeout')
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
                    self.assertTrue(entered.wait(10))
                    with self.assertRaises(ResearchError) as error: C01MemoryLoop(self.study.root).run(max_new_requests=1)
                    self.assertIn(error.exception.code, {'BUSY', 'NEEDS_REVIEW'})
                finally:
                    release.set()
                    worker.join(15)
            self.assertFalse(worker.is_alive())
            self.assertEqual(errors, [])
            self.assertEqual(len(records), 1)


if __name__ == '__main__': unittest.main()
