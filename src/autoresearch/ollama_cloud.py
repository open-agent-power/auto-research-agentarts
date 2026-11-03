"""Owned official Ollama cloud transport; credits are estimates, not a provider cap.

Only Ollama itself accesses its existing opaque signing key. No sign-in, key
copying/removal, weight download, retry, or billing changes are performed here.
The caller owns the durable cross-process request journal and recovery policy.
"""
import copy
from decimal import Decimal
import math
import os
import re
from pathlib import Path
import socket
import threading
import time
import uuid
from types import SimpleNamespace
import urllib.request

from .contracts import ResearchError, canonical, fingerprint
from .local_ollama import regular, file_hash, file_info, parse_json, NoRedirect, require
from .local_process import ManagedJob
from .windows_network import listener_pid

MODEL = 'gpt-oss:120b-cloud'
THINKING = 'medium'
REMOTE_MODEL, REMOTE_HOST = 'gpt-oss:120b', 'https://ollama.com:443'
ALIAS_SHA256 = '569662207105c69bb0eca2f79a3fdf8691ad6301def477a5ec66f8e8bae237e3'
CONFIG_SHA256 = '923426e76b183456b6aaca2c0538ae96f2de390cddc543278de025f714f79a03'
ALIAS_PATH = Path('manifests/registry.ollama.ai/library/gpt-oss/120b-cloud')


def _directory(path):
    for item in (path, *path.parents):
        require(not item.is_symlink() and not getattr(item, 'is_junction', lambda: False)(), 'UNSAFE_PATH', 'task paths cannot redirect')
    require(not path.exists() or path.is_dir(), 'UNSAFE_PATH', 'task directory must be a directory')


def _number(value):
    require(type(value) in (int, float) and math.isfinite(value) and value >= 0, 'QUOTA_UNKNOWN', 'finite nonnegative account amounts required')
    return value


class OwnedCloudOllama:
    def __init__(self, executable, cache, output, *, port=11436, model_store):
        require(type(port) is int and 1024 <= port <= 65535, 'INVALID_REQUEST', 'dedicated loopback port required')
        self.executable, self.cache, self.output, self.model_store = (Path(p).absolute() for p in (executable, cache, output, model_store))
        require(bool(os.environ.get('USERPROFILE')), 'AUTH_REQUIRED', 'existing Windows user profile required')
        self.profile, self.port = Path(os.environ['USERPROFILE']).absolute(), port
        self.http = SimpleNamespace(request=self._chat)
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
        self.job = self.process = self._identity = self._budget = None
        self._used, self._uncertain, self._handles = 0, False, []
        self._prepared = None
        self.credit_hold = None
        self._lock = threading.RLock()
        self.stopped = self.key_metadata_unchanged = False

    def _keys(self):
        try:
            result = []
            for name in ('id_ed25519', 'id_ed25519.pub'):
                _, s = regular(self.profile/'.ollama'/name, 16384)  # Metadata only.
                result.append((name, s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns))
            return result
        except OSError:
            raise ResearchError('AUTH_REQUIRED', 'existing signing keypair required; never generate or sign in') from None

    def _write(self, name, value):
        with (self.output/name).open('x', encoding='utf-8') as stream:
            stream.write(canonical(value))

    def __enter__(self):
        self._before_keys = self._keys()
        executable_sha, _ = file_hash(self.executable, 1_000_000_000)
        for path in (self.output, self.cache): _directory(path)
        self.output.mkdir(parents=True, exist_ok=False)
        require(not self.cache.exists() or not any(self.cache.iterdir()), 'UNSAFE_PATH', 'use a dedicated empty model cache')
        self.cache.mkdir(parents=True, exist_ok=True)
        with socket.socket() as probe:
            try: probe.bind(('127.0.0.1', self.port))
            except OSError: raise ResearchError('PORT_BUSY', 'never adopt an existing service') from None
        allowed = {'SYSTEMROOT', 'WINDIR', 'PATH', 'PATHEXT', 'COMSPEC', 'TEMP', 'TMP', 'PROGRAMFILES',
                   'PROGRAMFILES(X86)', 'PROGRAMW6432', 'PUBLIC', 'USERPROFILE', 'APPDATA', 'LOCALAPPDATA',
                   'PROCESSOR_ARCHITECTURE', 'NUMBER_OF_PROCESSORS'}
        env = {k: v for k, v in os.environ.items() if k.upper() in allowed}
        env.update(OLLAMA_HOST=f'127.0.0.1:{self.port}', OLLAMA_MODELS=str(self.cache), OLLAMA_NOPRUNE='1',
                   OLLAMA_NOHISTORY='1', OLLAMA_NUM_PARALLEL='1', OLLAMA_MAX_LOADED_MODELS='1', OLLAMA_KEEP_ALIVE='0')
        try:
            self.job = ManagedJob()
            self._handles = [(self.output/name).open('xb') for name in ('server.stdout.log', 'server.stderr.log')]
            self.process = self.job.spawn([str(self.executable), 'serve'], env=env, cwd=str(self.output), stdout=self._handles[0], stderr=self._handles[1])
            deadline = time.monotonic()+25
            while time.monotonic() < deadline:
                require(self.process.poll() is None, 'START_FAILED', 'owned server exited')
                try:
                    self.assert_owner()
                except ResearchError as error:
                    if error.code != 'OWNERSHIP_UNVERIFIED': raise
                    time.sleep(.1)
                    continue
                require(self._wire('/api/version', timeout=10).get('version') == '0.40.11', 'VERSION_CHANGED', 'reviewed Ollama version required')
                break
            else: raise ResearchError('START_FAILED', 'owned server readiness expired')
            self.identity = {'server_pid': self.process.pid, 'executable_sha256': executable_sha, 'ollama_version': '0.40.11',
                             'endpoint': f'http://127.0.0.1:{self.port}', 'cloud': True, 'local_weights': False}
            return self
        except BaseException:
            self.__exit__(None, None, None)
            raise

    def assert_owner(self):
        require(self.process is not None and self.process.poll() is None and self.job is not None
                and self.job.contains(self.process.pid) and listener_pid(self.port) == self.process.pid,
                'OWNERSHIP_UNVERIFIED', 'owned server unavailable; never adopt a replacement')

    def _wire(self, route, body=None, *, timeout=20, capture=None):
        require(route in {'/api/version', '/api/me', '/api/balance', '/api/usage', '/api/show', '/api/chat'}, 'INVALID_REQUEST', 'unsupported cloud route')
        require(type(timeout) in (int, float) and 0 < timeout <= 90, 'INVALID_REQUEST', 'bounded owned request deadline required')
        deadline = time.monotonic()+timeout
        timer = threading.Timer(timeout, self.job.close)
        timer.daemon = True
        timer.start()
        try:
            self.assert_owner()
            require(time.monotonic() < deadline, 'CLOUD_REQUEST_UNKNOWN', 'owned request deadline elapsed')
            request = urllib.request.Request(f'http://127.0.0.1:{self.port}'+route,
                data=None if body is None else canonical(body).encode('utf-8'), headers={'Content-Type': 'application/json'})
            with self.opener.open(request, timeout=max(.01, deadline-time.monotonic())) as response:
                require(response.status == 200, 'CLOUD_HTTP_FAILED', 'cloud metadata/request unavailable')
                raw = response.read(2*1024*1024+1)
            if capture is not None:
                with (self.output/capture).open('xb') as stream: stream.write(raw)
            require(time.monotonic() <= deadline, 'CLOUD_REQUEST_UNKNOWN', 'owned request reached total deadline')
            result = parse_json(raw)
            require(type(result) is dict, 'INVALID_RESPONSE', 'native response must be an object')
            return result
        except ResearchError: raise
        except Exception:
            raise ResearchError('CLOUD_REQUEST_UNKNOWN', 'cloud request failed; preserve reservation, never retry automatically') from None
        finally: timer.cancel()

    def _account(self):
        try: return self._account_read()
        except ResearchError: raise
        except (KeyError, TypeError, ValueError, OverflowError):
            raise ResearchError('QUOTA_UNKNOWN', 'account metadata is incomplete or invalid') from None

    def _account_read(self):
        me, balance, usage = self._wire('/api/me', {}), self._wire('/api/balance'), self._wire('/api/usage')
        require(me.get('plan') == 'free' and type(me.get('id')) in (str, int) and bool(me['id']), 'ACCOUNT_UNKNOWN', 'existing free account identity required')
        inc, purchased, totals = balance['included'], balance['purchased'], usage['totals']
        period = inc['period']
        require(type(period) is dict and set(period) == {'from', 'until'} and all(type(v) is str and 0 < len(v) <= 64 for v in period.values()), 'QUOTA_UNKNOWN', 'account period required')
        return {'plan': 'free', 'account_identity_sha256': fingerprint({'id': me['id']}), 'period': period,
                'included_balance_usd': _number(inc['balance_usd']), 'included_allowance_usd': _number(inc['allowance_usd']),
                'purchased_balance_usd': _number(purchased['balance_usd']),
                'usage_totals': {k: _number(totals[k]) for k in ('request_count', 'usage_usd', 'input_tokens', 'cached_input_tokens', 'output_tokens')}}

    def acquire(self):
        with self._lock:
            self.assert_owner()
            if self._identity is not None:
                return copy.deepcopy(self._identity)
            mh, _, raw = file_info(self.model_store/ALIAS_PATH, 65536)
            manifest = parse_json(raw)
            require(mh == ALIAS_SHA256 and manifest.get('layers') is None and manifest['config']['digest'] == 'sha256:'+CONFIG_SHA256, 'MODEL_CHANGED', 'only the reviewed public cloud alias is allowed')
            blob = Path('blobs')/('sha256-'+CONFIG_SHA256)
            bh, size, payload = file_info(self.model_store/blob, 65536)
            config = parse_json(payload)
            require(bh == CONFIG_SHA256 and size == manifest['config']['size'] == 384 and config.get('remote_model') == REMOTE_MODEL
                    and config.get('remote_host') == REMOTE_HOST, 'MODEL_CHANGED', 'cloud alias config changed')
            _directory(self.cache)
            for relative, content in ((ALIAS_PATH, raw), (blob, payload)):
                destination = self.cache/relative
                _directory(destination.parent)
                destination.parent.mkdir(parents=True, exist_ok=True)
                with destination.open('xb') as stream: stream.write(content)
            shown = self._wire('/api/show', {'model': MODEL})
            self._write('model-show.json', shown)
            thinking=shown.get('thinking')
            require(type(thinking) is dict and type(thinking.get('values')) is list and THINKING in thinking['values'],
                    'THINKING_UNVERIFIED','selected reasoning level must be advertised by this acquired model')
            account = self._account()
            require(account['purchased_balance_usd'] == 0 and account['included_balance_usd'] >= 1, 'FREE_QUOTA_REQUIRED', 'included credits required; no paid fallback')
            self._write('account-acquired.json', account)
            self._identity = {'model': MODEL, 'remote_model': REMOTE_MODEL, 'remote_host': REMOTE_HOST, 'alias_sha256': mh,
                              'config_sha256': bh, 'account_identity_sha256': account['account_identity_sha256'], 'account_period': account['period']}
            return copy.deepcopy(self._identity)

    def configure_budget(self, identity, max_remaining_requests):
        with self._lock:
            require(self._identity is not None and identity == self._identity, 'IDENTITY_CHANGED', 'acquired cloud identity required')
            require(type(max_remaining_requests) is int and 0 <= max_remaining_requests <= 8, 'INVALID_REQUEST', 'at most eight remaining cloud requests')
            require(self._budget is None or self._budget == max_remaining_requests, 'CONFIG_CHANGED', 'process budget cannot be reset')
            self._budget = max_remaining_requests

    def prepare(self, body):
        """Read/check credits before the controller reserves a model request.

        The short-lived approval is bound to exact request bytes and process
        usage. It never authorizes a different prompt or another model call.
        """
        with self._lock:
            require(type(body) is dict and len(canonical(body).encode('utf-8')) <= 65536,
                    'INVALID_REQUEST', 'bounded request required before credit preflight')
            require(not self._uncertain, 'NEEDS_REVIEW', 'previous native send outcome unknown')
            require(self.credit_hold is None, 'QUOTA_REVIEW_REQUIRED', 'received response has unresolved credit checks')
            require(self._budget is not None and self._used < self._budget, 'BUDGET_EXHAUSTED', 'configure remaining budget')
            self.assert_owner()
            digest = fingerprint(body)
            if (self._prepared is not None and self._prepared['request_sha256'] == digest
                    and self._prepared['used'] == self._used and time.monotonic()-self._prepared['at'] <= 10):
                return
            # A newer account observation supersedes every previous approval,
            # including when that observation or its receipt fails.
            self._prepared = None
            before = self._account()
            self._check_account(before)
            remaining = self._budget-self._used
            require(Decimal(str(before['included_balance_usd'])) >= Decimal('1')+remaining*Decimal('.10'),
                    'FREE_QUOTA_REQUIRED', 'included credit reserve insufficient')
            name = 'preflight-'+uuid.uuid4().hex+'.json'
            self._write(name, {'request_sha256':digest,'account':before,'used':self._used,'checked_at':time.time()})
            self._prepared = {'request_sha256':digest,'account':before,'used':self._used,
                              'at':time.monotonic(),'receipt':name}

    def _chat(self, route, body=None, *, timeout=90):
        with self._lock:
            require(route == '/api/chat' and type(timeout) in (int, float) and 0 < timeout <= 90, 'INVALID_REQUEST', 'only bounded native chat is public')
            require(type(body) is dict and set(body) <= {'model', 'messages', 'stream', 'think', 'keep_alive', 'options', 'tools'}
                    and body.get('model') == MODEL and body.get('stream') is False and body.get('think') == THINKING, 'INVALID_REQUEST', 'fixed model and selected reasoning level required')
            options = body.get('options')
            require(type(options) is dict and set(options) <= {'temperature', 'num_ctx', 'num_predict'}
                    and type(options.get('num_predict')) is int and 1 <= options['num_predict'] <= 2048
                    and type(options.get('num_ctx')) is int and 1 <= options['num_ctx'] <= 131072
                    and type(options.get('temperature', 0)) in (int, float) and options.get('temperature', 0) == 0
                    and type(body.get('keep_alive', 0)) is int and body.get('keep_alive', 0) == 0,
                    'INVALID_REQUEST', 'bounded output and context required')
            if 'tools' in body:
                tools, names = body['tools'], set()
                require(type(tools) is list and 1 <= len(tools) <= 16, 'INVALID_REQUEST', 'bounded native tools required')
                for tool in tools:
                    function = tool.get('function') if type(tool) is dict else None
                    require(type(function) is dict and set(tool) == {'type', 'function'} and tool['type'] == 'function'
                            and set(function) == {'name', 'description', 'parameters'}
                            and type(function['name']) is str and re.fullmatch('[a-z][a-z0-9_]{0,63}',function['name']) is not None
                            and function['name'] not in names and type(function['description']) is str
                            and 1 <= len(function['description']) <= 2000 and type(function['parameters']) is dict
                            and function['parameters'].get('type') == 'object', 'INVALID_REQUEST', 'valid distinct function definitions required')
                    names.add(function['name'])
            messages = body.get('messages')
            require(type(messages) is list and 1 <= len(messages) <= 16 and all(type(m) is dict and set(m) == {'role', 'content'}
                    and type(m['role']) is str and m['role'] in {'system', 'user', 'assistant'} and type(m['content']) is str for m in messages)
                    and len(canonical(body).encode('utf-8')) <= 65536, 'INVALID_REQUEST', 'bounded textual prompt required')
            require(not self._uncertain, 'NEEDS_REVIEW', 'previous cloud outcome requires review; no resend')
            require(self.credit_hold is None, 'QUOTA_REVIEW_REQUIRED', 'received response requires credit reconciliation')
            require(self._budget is not None and self._used < self._budget, 'BUDGET_EXHAUSTED', 'configure remaining cumulative budget before chat')
            self.assert_owner()
            if self._prepared is None: self.prepare(body)  # Direct transport callers, not the durable controller.
            require(self._prepared['request_sha256'] == fingerprint(body) and self._prepared['used'] == self._used
                    and time.monotonic()-self._prepared['at'] <= 10, 'PREFLIGHT_CHANGED', 'request approval changed or expired; never dispatch')
            ordinal, before = self._used+1, self._prepared['account']
            self._write(f'cloud-{ordinal:03}-sending.json', {'status': 'sending', 'request': body, 'request_sha256': fingerprint(body),
                'reserved_usd': '.10', 'account': before,'preflight_receipt':self._prepared['receipt']})
            self._used += 1
            self._prepared = None
            self._uncertain = True
            response = self._wire('/api/chat', body, timeout=timeout, capture=f'cloud-{ordinal:03}-response.raw.json')
            self._uncertain = False
            try:
                after = self._account()
                self._write(f'cloud-{ordinal:03}-account-after.json', after)
                self._check_account(after)
                require(Decimal('0') <= Decimal(str(before['included_balance_usd']))-Decimal(str(after['included_balance_usd'])) <= Decimal('.10'),
                        'QUOTA_CHANGED', 'unexpected credit movement; stop')
            except (ResearchError, OSError) as error:
                # Receiving is authoritative even if the subsequent account
                # query fails. Preserve the exact response, hold new spending.
                code = error.code if isinstance(error, ResearchError) else 'QUOTA_RECEIPT_FAILED'
                self.credit_hold = {'code':code,'ordinal':ordinal,'response_received':True}
                try:
                    self._write(f'cloud-{ordinal:03}-credit-hold.json',self.credit_hold)
                except OSError:
                    # The controller persists this hold atomically with the
                    # known response; an auxiliary receipt cannot discard it.
                    self.credit_hold['receipt_write_failed'] = True
            return response

    def _check_account(self, account):
        require(account['account_identity_sha256'] == self._identity['account_identity_sha256'] and account['period'] == self._identity['account_period']
                and account['purchased_balance_usd'] == 0, 'ACCOUNT_CHANGED', 'account, quota period or purchased balance changed')

    def __exit__(self, *_):
        try:
            if self.job is not None: self.job.close()
        finally:
            self.stopped = self.process is None or self.process.poll() is not None
            for handle in self._handles: handle.close()
            try: self.key_metadata_unchanged = self._keys() == self._before_keys
            except (OSError, ResearchError): self.key_metadata_unchanged = False
        return False
