"""Synthetic account, alias and process fixtures; no real Ollama/cloud calls."""
import copy
from contextlib import ExitStack
import hashlib
import json
import os
from pathlib import Path
import socket
import tempfile
import time
import unittest
from unittest.mock import patch

from autoresearch import ollama_cloud as module
from autoresearch.contracts import ResearchError, canonical, fingerprint


BODY = {'model': module.MODEL, 'messages': [{'role': 'user', 'content': 'SYNTHETIC public question'}],
        'stream': False, 'think': module.THINKING, 'keep_alive': 0,
        'options': {'num_ctx': 32768, 'num_predict': 2048, 'temperature': 0}}
ACCOUNT = {'id': 'synthetic-private-account-id', 'plan': 'free', 'balance': 2.5, 'purchased': 0,
           'period': {'from': '2026-10-18T00:00:00Z', 'until': '2026-11-18T00:00:00Z'}}
RAW = b'{ "model": "gpt-oss:120b", "done": true, "message": {"content":"SYNTHETIC only"}, "vendor_extra": [1,2] }'


class FakeProcess:
    def __init__(self, pid): self.pid, self.exited = pid, False
    def poll(self): return 0 if self.exited else None


class FakeJob:
    def __init__(self, pid): self.process, self.spawned, self.closed = FakeProcess(pid), [], False
    def spawn(self, args, **options):
        self.spawned.append((args, options))
        return self.process
    def contains(self, pid): return not self.closed and pid == self.process.pid
    def close(self): self.closed = self.process.exited = True


class FakeReply:
    status = 200
    def __init__(self, raw): self.raw = raw
    def __enter__(self): return self
    def __exit__(self, *_): pass
    def read(self, size): return self.raw[:size]


class FakeOpener:
    def __init__(self, states=None, raw=RAW):
        self.states = copy.deepcopy(states or [ACCOUNT])
        self.raw, self.account_number, self.chat_count = raw, 0, 0
        self.requests, self.on_chat, self.on_account, self.chat_error = [], None, None, None
    def open(self, request, *, timeout):
        from urllib.parse import urlsplit
        path = urlsplit(request.full_url).path
        body = None if request.data is None else json.loads(request.data)
        self.requests.append((path, body, timeout))
        state = self.states[min(self.account_number, len(self.states)-1)]
        if path == '/api/chat':
            self.chat_count += 1
            if self.on_chat: self.on_chat(body)
            if self.chat_error: raise self.chat_error
            return FakeReply(self.raw)
        if path == '/api/version': value = {'version': '0.40.11'}
        elif path == '/api/show': value = {'remote_model': module.REMOTE_MODEL, 'remote_host': module.REMOTE_HOST,
                                         'thinking':{'values':['low','medium','high'],'default':'medium'}}
        elif path == '/api/me':
            if self.on_account: self.on_account(self.account_number)
            value = {'id': state['id'], 'plan': state['plan'], 'name': 'PRIVATE_FAKE_NAME', 'email': 'private@example.invalid'}
        elif path == '/api/balance':
            value = {'included': {'balance_usd': state['balance'], 'allowance_usd': 2.5, 'period': state['period']},
                     'purchased': {'balance_usd': state['purchased']}}
        elif path == '/api/usage':
            value = {'totals': {'request_count': self.chat_count, 'usage_usd': 0, 'input_tokens': 0, 'cached_input_tokens': 0, 'output_tokens': 0,
                                'unrelated_private_field': 'PRIVATE_FAKE_NAME'}}
            self.account_number += 1
        else: raise AssertionError('unapproved fake route')
        return FakeReply(canonical(value).encode('utf-8'))


class OllamaCloudTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.root = Path(self.stack.enter_context(tempfile.TemporaryDirectory()))
        self.profile, self.store = self.root/'profile', self.root/'store'
        (self.profile/'.ollama').mkdir(parents=True)
        self.keys = [self.profile/'.ollama'/name for name in ('id_ed25519', 'id_ed25519.pub')]
        for key in self.keys: key.write_text('DO_NOT_READ_THIS_SYNTHETIC_KEY', encoding='utf-8')
        self.exe = self.root/'fake-official.exe'
        self.exe.write_bytes(b'SYNTHETIC executable; never executed')
        config = canonical({'remote_model': module.REMOTE_MODEL, 'remote_host': module.REMOTE_HOST}).encode().ljust(384, b' ')
        self.config_sha = hashlib.sha256(config).hexdigest()
        self.blob = self.store/'blobs'/('sha256-'+self.config_sha)
        self.blob.parent.mkdir(parents=True)
        self.blob.write_bytes(config)
        manifest = canonical({'schemaVersion': 2, 'layers': None, 'config': {'digest': 'sha256:'+self.config_sha, 'size': 384}}).encode()
        self.alias = self.store/module.ALIAS_PATH
        self.alias.parent.mkdir(parents=True)
        self.alias.write_bytes(manifest)
        self.alias_sha = hashlib.sha256(manifest).hexdigest()
        self.jobs, self.counter = [], 0
        def job():
            value = FakeJob(90000+len(self.jobs))
            self.jobs.append(value)
            return value
        self.owner = self.stack.enter_context(patch.object(module, 'listener_pid', side_effect=lambda _port: self.jobs[-1].process.pid))
        self.stack.enter_context(patch.object(module, 'ManagedJob', side_effect=job))
        self.stack.enter_context(patch.object(module, 'ALIAS_SHA256', self.alias_sha))
        self.stack.enter_context(patch.object(module, 'CONFIG_SHA256', self.config_sha))
        self.stack.enter_context(patch.dict(os.environ, {'USERPROFILE': str(self.profile), 'OPENAI_API_KEY': 'PRIVATE_FAKE_PROVIDER_KEY',
            'OLLAMA_API_KEY': 'PRIVATE_FAKE_PROVIDER_KEY', 'HTTP_PROXY': 'http://example.invalid', 'OLLAMA_HOST': 'https://example.invalid'}))

    def make(self, **options):
        self.counter += 1
        with socket.socket() as probe:
            probe.bind(('127.0.0.1', 0))
            port = probe.getsockname()[1]
        server = module.OwnedCloudOllama(self.exe, self.root/f'cache-{self.counter}', self.root/f'output-{self.counter}', port=port, model_store=self.store)
        server.opener = FakeOpener(**options)
        return server

    def opened(self, **options):
        server = self.make(**options)
        self.stack.enter_context(server)
        return server

    def error(self, code, operation):
        with self.assertRaises(ResearchError) as raised: operation()
        self.assertEqual(raised.exception.code, code)

    def test_acquire_copies_only_pinned_alias_and_config_without_reading_or_changing_keys(self):
        server = self.make()
        original = Path.open
        def guarded(path, mode='r', *args, **kwargs):
            if path in self.keys and 'r' in mode: raise AssertionError('agent must not read keys')
            return original(path, mode, *args, **kwargs)
        with patch.object(Path, 'open', guarded), server:
            identity = server.acquire()
            self.assertEqual(set(identity), {'model', 'remote_model', 'remote_host', 'alias_sha256', 'config_sha256', 'account_identity_sha256', 'account_period'})
            self.assertEqual(identity['account_identity_sha256'], fingerprint({'id': ACCOUNT['id']}))
            self.assertEqual(server.acquire(), identity)
            self.assertEqual(sorted(str(p.relative_to(server.cache)) for p in server.cache.rglob('*') if p.is_file()),
                             sorted([str(module.ALIAS_PATH), str(Path('blobs')/('sha256-'+self.config_sha))]))
            env = self.jobs[-1].spawned[0][1]['env']
            self.assertEqual(env['USERPROFILE'], str(self.profile))
            for key in ('OPENAI_API_KEY', 'OLLAMA_API_KEY', 'HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY', 'HOME'):
                self.assertNotIn(key, env)
        self.assertTrue(server.stopped)
        self.assertTrue(server.key_metadata_unchanged)
        logged = ''.join(p.read_text(encoding='utf-8') for p in server.output.iterdir() if p.is_file())
        for secret in (ACCOUNT['id'], 'PRIVATE_FAKE_NAME', 'private@example.invalid', 'DO_NOT_READ_THIS_SYNTHETIC_KEY', 'PRIVATE_FAKE_PROVIDER_KEY'):
            self.assertNotIn(secret, logged)

    def test_missing_auth_and_unsafe_key_fail_before_spawn(self):
        self.keys[0].unlink()
        server = self.make()
        self.error('AUTH_REQUIRED', server.__enter__)
        self.assertEqual(self.jobs, [])
        self.assertFalse(server.output.exists())
        self.keys[0].write_text('synthetic', encoding='utf-8')
        os.link(self.keys[0], self.root/'linked-test-key')
        self.error('UNSAFE_PATH', self.make().__enter__)
        self.assertEqual(self.jobs, [])

    def test_native_function_metadata_and_response_remain_unmodified(self):
        server=self.opened();identity=server.acquire();server.configure_budget(identity,1)
        body=copy.deepcopy(BODY)
        body['tools']=[{'type':'function','function':{'name':'search','description':'Synthetic native envelope only',
                       'parameters':{'type':'object','properties':{},'required':[]}}}]
        before=copy.deepcopy(body)
        result=server.http.request('/api/chat',body)
        self.assertEqual(body,before);self.assertEqual(result,json.loads(RAW))
        sent=next(request[1] for request in server.opener.requests if request[0]=='/api/chat')
        self.assertEqual(sent,body);self.assertNotIn('format',sent)

    def test_invalid_or_duplicate_native_definitions_rejected_before_inference(self):
        server=self.opened();identity=server.acquire();server.configure_budget(identity,1)
        tool={'type':'function','function':{'name':'search','description':'Synthetic only','parameters':{'type':'object'}}}
        for tools in ([],[tool,copy.deepcopy(tool)],[{'type':'function','function':{'name':'../shell'}}]):
            with self.subTest(tools=tools):
                body={**copy.deepcopy(BODY),'tools':tools}
                self.error('INVALID_REQUEST',lambda:server.http.request('/api/chat',body))
        self.assertEqual(server.opener.chat_count,0)

    def test_nonempty_cache_and_existing_output_never_start_or_modify_a_service(self):
        for kind in ('cache', 'output'):
            server = self.make()
            path = getattr(server, kind)
            path.mkdir()
            (path/'existing').write_text('preserve', encoding='utf-8')
            with self.assertRaises((ResearchError, FileExistsError)): server.__enter__()
            self.assertEqual((path/'existing').read_text(encoding='utf-8'), 'preserve')
        self.assertEqual(self.jobs, [])

    def test_tampered_public_alias_fails_without_copy_or_model_request(self):
        server = self.opened()
        self.alias.write_bytes(self.alias.read_bytes()+b' ')
        self.error('MODEL_CHANGED', server.acquire)
        self.assertFalse((server.cache/module.ALIAS_PATH).exists())
        self.assertEqual(server.opener.chat_count, 0)

    def test_durable_reservation_precedes_send_and_raw_response_precedes_quota_check(self):
        server = self.opened()
        identity = server.acquire()
        server.configure_budget(identity, 2)
        def sending(body):
            saved = json.loads((server.output/'cloud-001-sending.json').read_text(encoding='utf-8'))
            self.assertEqual(saved['request'], body)
            self.assertEqual(saved['request_sha256'], fingerprint(body))
        def account(index):
            if index >= 2: self.assertEqual((server.output/'cloud-001-response.raw.json').read_bytes(), RAW)
        server.opener.on_chat, server.opener.on_account = sending, account
        response = server.http.request('/api/chat', copy.deepcopy(BODY))
        self.assertEqual(response, json.loads(RAW))
        self.assertNotIn('native_model_digest', response)
        self.assertEqual(server._used, 1)

    def test_budget_is_required_capped_and_cannot_be_reset_after_consumption(self):
        server = self.opened()
        identity = server.acquire()
        self.error('BUDGET_EXHAUSTED', lambda: server.http.request('/api/chat', BODY))
        self.error('INVALID_REQUEST', lambda: server.configure_budget(identity, 9))
        self.error('IDENTITY_CHANGED', lambda: server.configure_budget({**identity, 'model': 'other'}, 2))
        server.configure_budget(identity, 2)
        server.http.request('/api/chat', BODY)
        server.configure_budget(identity, 2)  # Idempotent; used call remains used.
        self.error('CONFIG_CHANGED', lambda: server.configure_budget(identity, 1))
        self.error('CONFIG_CHANGED', lambda: server.configure_budget(identity, 3))
        server.opener.on_account = None
        server.http.request('/api/chat', BODY)
        self.error('BUDGET_EXHAUSTED', lambda: server.http.request('/api/chat', BODY))
        self.assertEqual(server.opener.chat_count, 2)

    def test_insufficient_credits_and_purchased_balance_block_model_calls(self):
        server = self.opened(states=[{**ACCOUNT, 'balance': 1.1}])
        identity = server.acquire()
        server.configure_budget(identity, 2)
        self.error('FREE_QUOTA_REQUIRED', lambda: server.http.request('/api/chat', BODY))
        self.assertEqual(server.opener.chat_count, 0)
        self.assertEqual(list(server.output.glob('*sending*')), [])
        other = self.opened(states=[{**ACCOUNT, 'purchased': .5}])
        self.error('FREE_QUOTA_REQUIRED', other.acquire)
        self.assertEqual(other.opener.chat_count, 0)

    def test_post_response_identity_period_or_excess_cost_changes_preserve_raw_then_stop(self):
        for changed, code in (({**ACCOUNT, 'id': 'other'}, 'ACCOUNT_CHANGED'),
                              ({**ACCOUNT, 'period': {**ACCOUNT['period'], 'until': '2026-12-18T00:00:00Z'}}, 'ACCOUNT_CHANGED'),
                              ({**ACCOUNT, 'balance': 2.39}, 'QUOTA_CHANGED')):
            with self.subTest(code=code, changed=changed):
                server = self.opened(states=[ACCOUNT, ACCOUNT, changed])
                server.configure_budget(server.acquire(), 2)
                self.assertEqual(server.http.request('/api/chat', BODY),json.loads(RAW))
                self.assertEqual((server.output/'cloud-001-response.raw.json').read_bytes(), RAW)
                self.assertEqual(server.credit_hold['code'],code)
                self.assertFalse(server._uncertain)
                self.error('QUOTA_REVIEW_REQUIRED', lambda: server.http.request('/api/chat', BODY))
                self.assertEqual(server.opener.chat_count, 1)

    def test_explicit_preflight_is_exact_prompt_bound_and_does_not_reserve_a_model_call(self):
        server=self.opened();server.configure_budget(server.acquire(),2)
        server.prepare(copy.deepcopy(BODY));number=server.opener.account_number
        server.prepare(copy.deepcopy(BODY))
        self.assertEqual(server.opener.account_number,number)
        self.assertEqual(server._used,0);self.assertEqual(list(server.output.glob('*sending*')),[])
        changed={**copy.deepcopy(BODY),'messages':[{'role':'user','content':'different synthetic request'}]}
        self.error('PREFLIGHT_CHANGED',lambda:server.http.request('/api/chat',changed))
        self.assertEqual(server.opener.chat_count,0)
        result=server.http.request('/api/chat',BODY)
        self.assertEqual(result,json.loads(RAW));self.assertEqual(server.opener.account_number,number+1)

    def test_expired_preflight_cannot_dispatch_and_received_metadata_failure_does_not_lose_response(self):
        server=self.opened();server.configure_budget(server.acquire(),2)
        server.prepare(BODY);server._prepared['at']-=11
        self.error('PREFLIGHT_CHANGED',lambda:server.http.request('/api/chat',BODY))
        self.assertEqual(server.opener.chat_count,0)
        server.prepare(BODY)
        def fail_after_response(_):
            if server.opener.chat_count:raise TimeoutError('synthetic account outage after real reply')
        server.opener.on_account=fail_after_response
        self.assertEqual(server.http.request('/api/chat',BODY),json.loads(RAW))
        self.assertEqual(server.credit_hold['code'],'CLOUD_REQUEST_UNKNOWN')
        self.assertTrue(server.credit_hold['response_received']);self.assertFalse(server._uncertain)
        self.assertEqual((server.output/'cloud-001-response.raw.json').read_bytes(),RAW)
        self.error('QUOTA_REVIEW_REQUIRED',lambda:server.prepare(BODY))

    def test_unknown_send_never_retries_even_after_identical_budget_configuration(self):
        server = self.opened()
        identity = server.acquire()
        server.configure_budget(identity, 2)
        server.opener.chat_error = TimeoutError('synthetic unknown outcome')
        self.error('CLOUD_REQUEST_UNKNOWN', lambda: server.http.request('/api/chat', BODY))
        server.configure_budget(identity, 2)
        self.error('NEEDS_REVIEW', lambda: server.http.request('/api/chat', BODY))
        self.assertEqual(server.opener.chat_count, 1)
        self.assertEqual(server._used, 1)

    def test_failed_new_preflight_revokes_old_prompt_approval(self):
        server=self.opened(states=[ACCOUNT,ACCOUNT,{**ACCOUNT,'balance':.5}])
        server.configure_budget(server.acquire(),2)
        server.prepare(BODY)
        changed={**copy.deepcopy(BODY),'messages':[{'role':'user','content':'new synthetic question'}]}
        self.error('FREE_QUOTA_REQUIRED',lambda:server.prepare(changed))
        self.assertIsNone(server._prepared)
        self.error('FREE_QUOTA_REQUIRED',lambda:server.http.request('/api/chat',BODY))
        self.assertEqual(server.opener.chat_count,0)

    def test_post_response_receipt_failures_preserve_response_and_credit_hold(self):
        for fail_hold in (False,True):
            with self.subTest(fail_hold=fail_hold):
                server=self.opened();server.configure_budget(server.acquire(),2)
                original=server._write
                def fail_receipts(name,value):
                    if name.endswith('-account-after.json') or (fail_hold and name.endswith('-credit-hold.json')):
                        raise OSError('synthetic receipt disk failure')
                    return original(name,value)
                with patch.object(server,'_write',side_effect=fail_receipts):
                    self.assertEqual(server.http.request('/api/chat',BODY),json.loads(RAW))
                self.assertEqual(server.credit_hold['code'],'QUOTA_RECEIPT_FAILED')
                self.assertTrue(server.credit_hold['response_received'])
                self.assertEqual(server.credit_hold.get('receipt_write_failed',False),fail_hold)
                self.assertFalse(server._uncertain)
                self.assertEqual((server.output/'cloud-001-response.raw.json').read_bytes(),RAW)
                self.error('QUOTA_REVIEW_REQUIRED',lambda:server.prepare(BODY))
                self.assertEqual(server.opener.chat_count,1)

    def test_replacement_service_is_rejected_before_account_or_chat_requests(self):
        server = self.opened()
        server.configure_budget(server.acquire(), 1)
        before = list(server.opener.requests)
        self.owner.side_effect = None
        self.owner.return_value = server.process.pid+1
        self.error('OWNERSHIP_UNVERIFIED', lambda: server.http.request('/api/chat', BODY))
        self.error('OWNERSHIP_UNVERIFIED', server.acquire)
        self.assertEqual(server.opener.requests, before)
        self.assertEqual(server._used, 0)

    def test_public_route_model_prompt_and_token_caps_reject_before_account_or_send(self):
        server = self.opened()
        server.configure_budget(server.acquire(), 8)
        before = list(server.opener.requests)
        for change in ({'model': 'other-cloud'}, {'format': {}}, {'stream': True},
                       {'options': {**BODY['options'], 'num_predict': 2049}},
                       {'options': {**BODY['options'], 'num_ctx': 131073}},
                       {'options': {**BODY['options'], 'num_predict': True}},
                       {'messages': [{'role': 'user', 'content': 'x'*65536}]},
                       {'messages': [{'role': [], 'content': 'invalid role'}]},
                       {'messages': [{'role': 'user', 'content': 'x', 'images': ['arbitrary-file']}]},
                       {'options': {**BODY['options'], 'temperature': float('nan')}}):
            self.error('INVALID_REQUEST', lambda: server.http.request('/api/chat', {**copy.deepcopy(BODY), **change}))
        for timeout in (91, 0, True, float('nan')):
            self.error('INVALID_REQUEST', lambda: server.http.request('/api/chat', BODY, timeout=timeout))
        self.error('INVALID_REQUEST', lambda: server.http.request('/api/me', {}))
        self.assertEqual(server.opener.requests, before)
        self.assertEqual(server._used, 0)

    def test_invalid_account_shape_and_nonfinite_numbers_fail_closed(self):
        for state in ({**ACCOUNT, 'period': None}, {**ACCOUNT, 'balance': True}, {**ACCOUNT, 'balance': -1}):
            server = self.opened(states=[state])
            self.error('QUOTA_UNKNOWN', server.acquire)
        server = self.opened()
        original = server.opener.open
        def missing(request, **kwargs):
            if request.full_url.endswith('/api/balance'): return FakeReply(b'{}')
            return original(request, **kwargs)
        server.opener.open = missing
        self.error('QUOTA_UNKNOWN', server.acquire)

    def test_selected_reasoning_must_be_advertised_before_account_or_model_use(self):
        for thinking in (None,{'values':['low']},{'values':'medium'}):
            with self.subTest(thinking=thinking):
                server=self.opened();original=server.opener.open
                def show(request,**kwargs):
                    if request.full_url.endswith('/api/show'):
                        return FakeReply(canonical({'thinking':thinking}).encode('utf-8'))
                    return original(request,**kwargs)
                server.opener.open=show
                self.error('THINKING_UNVERIFIED',server.acquire)
                self.assertFalse(any(x[0]=='/api/me' for x in server.opener.requests))
                self.assertEqual(server.opener.chat_count,0)

    def test_other_reasoning_levels_cannot_dispatch_under_frozen_medium_transport(self):
        server=self.opened();server.configure_budget(server.acquire(),2)
        for level in ('low','high',None,True):
            self.error('INVALID_REQUEST',lambda:server.http.request('/api/chat',{**copy.deepcopy(BODY),'think':level}))
        self.assertEqual(server.opener.chat_count,0);self.assertEqual(server._used,0)

    def test_total_deadline_closes_only_owned_job_and_unknown_cannot_send_again(self):
        server = self.opened()
        server.configure_budget(server.acquire(), 2)
        own_job = self.jobs[-1]
        unrelated = FakeJob(77777)
        original = server.opener.open
        class Drip(FakeReply):
            def read(self, _size):
                while not own_job.closed: time.sleep(.005)
                raise OSError('synthetic peer closes with its owned job')
        def slow(request, **kwargs):
            if request.full_url.endswith('/api/chat'):
                original(request, **kwargs)
                return Drip(b'')
            return original(request, **kwargs)
        server.opener.open = slow
        started = time.monotonic()
        self.error('CLOUD_REQUEST_UNKNOWN', lambda: server.http.request('/api/chat', BODY, timeout=.05))
        self.assertLess(time.monotonic()-started, 1)
        self.assertTrue(own_job.closed)
        self.assertFalse(unrelated.closed)
        self.error('NEEDS_REVIEW', lambda: server.http.request('/api/chat', BODY))


if __name__ == '__main__': unittest.main()
