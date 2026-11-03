"""One low-reasoning continuation with an explicit prior unknown liability.

The original native journal remains authoritative. This transport never clears
its unknown request or claims its final cost was established.
"""
import copy
from decimal import Decimal
from pathlib import Path
import time

from . import ollama_cloud
from .contracts import ResearchError, canonical, fingerprint
from .local_ollama import file_info, parse_json, require

REASONING = 'low'
MAX_OUTPUT_TOKENS = 4096
MAX_CONTEXT_TOKENS = 32768


class OwnedContinuationOllama(ollama_cloud.OwnedCloudOllama):
    def __init__(self, *args, original_identity, unknown_receipt, unknown_sha256, **kwargs):
        super().__init__(*args, **kwargs)
        self.original_identity = copy.deepcopy(original_identity)
        self.unknown_receipt = Path(unknown_receipt).absolute()
        self.unknown_sha256 = unknown_sha256
        self._prior = self._read_prior()
        self._low_verified = False

    def _read_prior(self):
        digest, _, raw = file_info(self.unknown_receipt, 2 * 1024 * 1024)
        require(digest == self.unknown_sha256, 'EVIDENCE_CHANGED', 'Prior unknown receipt changed.')
        value = parse_json(raw)
        require(value.get('status') == 'sending' and value.get('reserved_usd') == '.10'
                and value.get('request_sha256') == fingerprint(value.get('request')),
                'INVALID_REQUEST', 'Exact prior sending receipt with retained reserve required.')
        account = value.get('account', {})
        require(account.get('account_identity_sha256') == self.original_identity.get('account_identity_sha256')
                and account.get('period') == self.original_identity.get('account_period')
                and account.get('plan') == 'free' and account.get('purchased_balance_usd') == 0
                and value['request'].get('model') == self.original_identity.get('model'),
                'ACCOUNT_CHANGED', 'Unknown request must belong to the original free account and model.')
        return value

    def acquire(self):
        with self._lock:
            identity = super().acquire()
            require(identity == self.original_identity, 'IDENTITY_CHANGED', 'Continue with the exact original model/account period.')
            self._read_prior()
            if not self._low_verified:
                digest, _, raw = file_info(self.output / 'model-show.json', 2 * 1024 * 1024)
                thinking = parse_json(raw).get('thinking')
                require(type(thinking) is dict and type(thinking.get('values')) is list
                        and REASONING in thinking['values'], 'THINKING_UNVERIFIED', 'Actual model must advertise low reasoning.')
                self._write('continuation-profile.json', {
                    'schema_version': 'p02-source-continuation-transport-v1',
                    'selected_reasoning': REASONING, 'max_output_tokens': MAX_OUTPUT_TOKENS,
                    'max_context_tokens': MAX_CONTEXT_TOKENS, 'model_show_sha256': digest,
                    'prior_unknown_receipt_sha256': self.unknown_sha256,
                    'prior_unknown_request_sha256': self._prior['request_sha256'],
                    'prior_unknown_reserve_usd': '.10', 'prior_outcome': 'unknown',
                    'prior_cost_reconciled': False, 'provider_hard_cap': False,
                    'original_cash_cap_cny': 5, 'cash_settlement_status': 'unknown',
                    'paid_fallback': False, 'model_calls': 0,
                })
                self._low_verified = True
            return identity

    def configure_budget(self, identity, max_remaining_requests):
        require(type(max_remaining_requests) is int and max_remaining_requests == 1,
                'BUDGET_EXHAUSTED', 'Only one unused original request may be configured.')
        super().configure_budget(identity, max_remaining_requests)

    def prepare(self, body):
        with self._lock:
            self._read_prior()
            super().prepare(body)
            before = self._prepared['account']
            require(Decimal(str(before['included_balance_usd'])) >= Decimal('1.20'),
                    'FREE_QUOTA_REQUIRED', 'Retain floor plus one unknown and one fresh request reserve.')

    def _chat(self, route, body=None, *, timeout=90):
        with self._lock:
            require(route == '/api/chat' and type(timeout) in (int, float) and 0 < timeout <= 90,
                    'INVALID_REQUEST', 'Only bounded native chat is public.')
            require(type(body) is dict and set(body) <= {'model', 'messages', 'stream', 'think', 'keep_alive', 'options', 'tools'}
                    and body.get('model') == ollama_cloud.MODEL and body.get('stream') is False
                    and body.get('think') == REASONING, 'INVALID_REQUEST', 'Unchanged model and low reasoning required.')
            options = body.get('options')
            require(type(options) is dict and set(options) == {'temperature', 'num_ctx', 'num_predict'}
                    and type(options['num_predict']) is int and options['num_predict'] == MAX_OUTPUT_TOKENS
                    and type(options['num_ctx']) is int and options['num_ctx'] == MAX_CONTEXT_TOKENS
                    and type(options['temperature']) in (int, float) and options['temperature'] == 0
                    and type(body.get('keep_alive')) is int and body['keep_alive'] == 0,
                    'INVALID_REQUEST', 'Exact continuation output and context limits required.')
            tools = body.get('tools'); names = set()
            require(type(tools) is list and 1 <= len(tools) <= 3, 'INVALID_REQUEST', 'Only terminal source assessment tools allowed.')
            for tool in tools:
                function = tool.get('function') if type(tool) is dict else None
                require(type(function) is dict and set(tool) == {'type', 'function'} and tool['type'] == 'function'
                        and set(function) == {'name', 'description', 'parameters'}
                        and function['name'] in {'record_assessment', 'pause', 'stop'} and function['name'] not in names
                        and type(function['description']) is str and 1 <= len(function['description']) <= 2000
                        and type(function['parameters']) is dict and function['parameters'].get('type') == 'object',
                        'INVALID_REQUEST', 'Valid distinct terminal function definitions required.')
                names.add(function['name'])
            messages = body.get('messages')
            require(type(messages) is list and len(messages) == 2
                    and all(type(m) is dict and set(m) == {'role', 'content'} and type(m['content']) is str for m in messages)
                    and [m['role'] for m in messages] == ['system', 'user']
                    and len(canonical(body).encode('utf-8')) <= 65536,
                    'INVALID_REQUEST', 'Bounded exact source context required.')
            require(self._low_verified, 'THINKING_UNVERIFIED', 'Verify actual low capability first.')
            require(not self._uncertain, 'NEEDS_REVIEW', 'New unknown request is never resent.')
            require(self.credit_hold is None, 'QUOTA_REVIEW_REQUIRED', 'Received response has unresolved credit checks.')
            require(self._budget == 1 and self._used == 0, 'BUDGET_EXHAUSTED', 'One continuation request only.')
            self.assert_owner()
            self._read_prior()
            if self._prepared is None:
                self.prepare(body)
            require(self._prepared['request_sha256'] == fingerprint(body) and self._prepared['used'] == self._used
                    and time.monotonic() - self._prepared['at'] <= 10,
                    'PREFLIGHT_CHANGED', 'Exact request preflight must remain current.')
            before = self._prepared['account']
            require(Decimal(str(before['included_balance_usd'])) >= Decimal('1.20'),
                    'FREE_QUOTA_REQUIRED', 'Unknown liability buffer is still required.')
            self._write('cloud-001-sending.json', {
                'status': 'sending', 'request': body, 'request_sha256': fingerprint(body),
                'reserved_usd': '.10', 'prior_unknown_reserve_usd': '.10',
                'prior_unknown_receipt_sha256': self.unknown_sha256,
                'account': before, 'preflight_receipt': self._prepared['receipt'],
            })
            self._used += 1; self._prepared = None; self._uncertain = True
            response = self._wire('/api/chat', body, timeout=timeout, capture='cloud-001-response.raw.json')
            self._uncertain = False
            try:
                after = self._account(); self._write('cloud-001-account-after.json', after); self._check_account(after)
                require(Decimal('0') <= Decimal(str(before['included_balance_usd'])) - Decimal(str(after['included_balance_usd'])) <= Decimal('.10'),
                        'QUOTA_CHANGED', 'Unexpected credit movement; stop.')
            except (ResearchError, OSError) as error:
                self.credit_hold = {'code': getattr(error, 'code', 'QUOTA_RECEIPT_FAILED'),
                                    'ordinal': 1, 'response_received': True}
                try:
                    self._write('cloud-001-credit-hold.json', self.credit_hold)
                except OSError:
                    self.credit_hold['receipt_write_failed'] = True
            return response
