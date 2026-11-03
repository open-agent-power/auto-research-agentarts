"""Use the existing medium native transport while retaining a prior unknown charge."""
import copy
from decimal import Decimal
from pathlib import Path

from .ollama_cloud import OwnedCloudOllama
from .contracts import fingerprint
from .local_ollama import file_info, parse_json, require


class OwnedPipelineResearchOllama(OwnedCloudOllama):
    def __init__(self, *args, original_identity, unknown_receipt, unknown_sha256,
                 unknown_request_sha256, **kwargs):
        super().__init__(*args, **kwargs)
        self.original_identity = copy.deepcopy(original_identity)
        self.unknown_receipt = Path(unknown_receipt).absolute()
        self.unknown_sha256 = unknown_sha256
        self.unknown_request_sha256 = unknown_request_sha256
        self._profile_saved = False
        self._read_prior()

    def _read_prior(self):
        digest, _, raw = file_info(self.unknown_receipt, 2 * 1024 * 1024)
        value = parse_json(raw)
        account = value.get('account', {})
        require(digest == self.unknown_sha256 and value.get('status') == 'sending'
                and value.get('reserved_usd') == '.10'
                and value.get('request_sha256') == self.unknown_request_sha256
                and fingerprint(value.get('request')) == self.unknown_request_sha256,
                'EVIDENCE_CHANGED', 'Keep the exact prior unknown request and reserve.')
        require(account.get('account_identity_sha256') == self.original_identity.get('account_identity_sha256')
                and account.get('period') == self.original_identity.get('account_period')
                and account.get('plan') == 'free' and account.get('purchased_balance_usd') == 0
                and value['request'].get('model') == self.original_identity.get('model'),
                'ACCOUNT_CHANGED', 'Prior unknown belongs to the same free account and model.')
        return value

    def acquire(self):
        with self._lock:
            identity = super().acquire()
            require(identity == self.original_identity, 'IDENTITY_CHANGED', 'Keep the original model/account period.')
            self._read_prior()
            if not self._profile_saved:
                self._write('pipeline-research-profile.json', {
                    'schema_version': 'p02-pipeline-research-transport-v1',
                    'reasoning': 'medium', 'max_new_task_requests': 4,
                    'prior_unknown_receipt_sha256': self.unknown_sha256,
                    'prior_unknown_request_sha256': self.unknown_request_sha256,
                    'prior_unknown_reserve_usd': '.10', 'prior_cost_reconciled': False,
                    'original_cash_cap_cny': 5, 'cash_settlement_status': 'unknown',
                    'paid_fallback': False, 'provider_hard_cap': False,
                    'old_task_budget_reset': False,
                })
                self._profile_saved = True
            return identity

    def configure_budget(self, identity, max_remaining_requests):
        require(type(max_remaining_requests) is int and 0 <= max_remaining_requests <= 4,
                'BUDGET_EXHAUSTED', 'This new-source task has at most four requests.')
        return super().configure_budget(identity, max_remaining_requests)

    def prepare(self, body):
        with self._lock:
            self._read_prior()
            super().prepare(body)
            required = Decimal('1.10') + Decimal('.10') * (self._budget - self._used)
            if Decimal(str(self._prepared['account']['included_balance_usd'])) < required:
                self._prepared = None
                require(False, 'FREE_QUOTA_REQUIRED', 'Retain floor, prior unknown and remaining new-task reserves.')

    def _chat(self, route, body=None, *, timeout=90):
        with self._lock:
            self._read_prior()
            return super()._chat(route, body, timeout=timeout)
