"""Exact-scope, read-only memory context; observations never become instructions.

Snapshot hashes cover the original recall response, not the operator-only physical
store identity. A snapshot records one SQLite read; it is not a revocation lease,
scientific review, source-authenticity proof, or authenticated model identity.
"""
import copy
import math
import os
from pathlib import Path
import re
import sqlite3
import stat

from .c01 import FEATURES, TARGETS
from .contracts import canonical, fingerprint, ResearchError
from .research_memory import ResearchMemory, observation_id, validate_scope


ROLES = ('fit_observation', 'diagnostic_observation')
MAX_PROJECTION_BYTES = 12 * 1024
TARGET_IDS = tuple(target['id'] for target in TARGETS)
REVIEW_STATUS = 'derived_not_scientifically_reviewed'


def _require(condition, message, code='INVALID_MEMORY_SNAPSHOT'):
    if not condition: raise ResearchError(code, message)


def _sha(value):
    return type(value) is str and re.fullmatch(r'[0-9a-f]{64}', value) is not None


def _number(value):
    _require(type(value) in (int, float), 'memory numeric observations require finite numbers, not booleans')
    try: finite = math.isfinite(value)
    except OverflowError: finite = False
    _require(finite, 'memory numeric observations require finite numbers')
    return value


def _identifier(value):
    _require(type(value) is str and 1 <= len(value) <= 160, 'invalid memory source action or sample identifier')
    return value


def scope_for_study(study):
    """Use the current verified export, never a supplied historical memory scope."""
    reproduction = study.export()['reproduction']
    inputs = reproduction['inputs']
    _require(fingerprint(inputs) == reproduction['inputs_sha256'], 'current exported input fingerprint differs')
    return validate_scope({'archive_sha256': inputs['source']['archive_sha256'],
                           'inputs_sha256': reproduction['inputs_sha256'],
                           'analysis_code_sha256': reproduction['analysis_code_sha256'],
                           'protocol': reproduction['protocol']})


def _raw_snapshot(snapshot):
    _require(type(snapshot) is dict, 'memory snapshot must be an object')
    raw = {key: value for key, value in snapshot.items() if key not in {'snapshot_sha256', 'store_identity'}}
    _require({'scope', 'condition_match', 'entries', 'scientific_validation', 'warning'} <= set(raw)
             and not set(raw) - {'scope', 'condition_match', 'entries', 'scientific_validation', 'warning', 'empty_reason'},
             'unsupported memory recall fields')
    validate_scope(raw['scope'])
    _require(raw['condition_match'] == 'exact' and raw['scientific_validation'] is False
             and type(raw['entries']) is list and len(raw['entries']) <= 8,
             'require exact unreviewed recall with at most eight observations')
    _require(type(raw['warning']) is str, 'memory recall requires its untrusted-context warning')
    entry_ids = set()
    for item in raw['entries']:
        _require(type(item) is dict and set(item) == {'record', 'inclusion_status', 'source_versions'}
                 and item['inclusion_status'] == 'active' and type(item['record']) is dict,
                 'only active memory observations may enter a context')
        record = item['record']
        _require(record.get('kind') in ROLES and record.get('review_status') == REVIEW_STATUS
                 and record.get('numerical_recomputation') is True
                 and record.get('schema_version') == 'conditional-research-memory-v1'
                 and canonical(record.get('scope')) == canonical(raw['scope'])
                 and _sha(record.get('id')) and observation_id(record) == record['id'],
                 'memory role, scope, identity or scientific review state differs')
        _require(record['id'] not in entry_ids, 'duplicate memory observation')
        entry_ids.add(record['id'])
        versions = item['source_versions']
        _require(type(versions) is list and versions and record['provenance'] in versions,
                 'memory is missing its immutable original source version')
        seen = set()
        for version in versions:
            _require(type(version) is dict and version.get('action_id') == record['provenance']['action_id']
                     and all(_sha(version.get(key)) for key in
                             ('source_record_sha256', 'reproduction_sha256', 'origin_observation_sha256')),
                     'invalid memory source version identity')
            _require(version['source_record_sha256'] not in seen, 'duplicate memory source version')
            seen.add(version['source_record_sha256'])
    return raw


class MemoryContext:
    def __init__(self, workspace):
        self.root = Path(os.path.abspath(workspace))
        self.database = self.root / 'memory.sqlite'
        self._store = ResearchMemory(self.root)
        self._physical_identity = self._physical()

    def _physical(self):
        try:
            for path in (self.database, *self.database.parents):
                _require(not path.is_symlink() and not getattr(path, 'is_junction', lambda: False)(),
                         'memory store cannot cross redirected paths', 'UNSAFE_PATH')
            metadata = self.database.lstat()
            _require(stat.S_ISREG(metadata.st_mode) and metadata.st_nlink == 1,
                     'memory.sqlite must already be an unshared regular file', 'UNSAFE_PATH')
            return {'memory_path': str(self.database), 'device': metadata.st_dev, 'inode': metadata.st_ino}
        except OSError:
            raise ResearchError('MEMORY_UNAVAILABLE', 'an existing ordinary memory.sqlite is required') from None

    def identity(self):
        """Operator-only physical identity. mtime/size intentionally are not frozen."""
        current = self._physical()
        _require(current == self._physical_identity, 'memory store was replaced; inspect before reconfiguring', 'MEMORY_STORE_CHANGED')
        return copy.deepcopy(current)

    def snapshot(self, study):
        before = self.identity()
        scope = scope_for_study(study)
        try:
            recalled = self._store.recall(scope, kinds=list(ROLES), limit=8, include_retired=False)
            _require(canonical(recalled['scope']) == canonical(scope), 'memory recall does not match the current exported scope')
            _raw_snapshot(recalled)
        except ResearchError:
            raise
        except (OSError, sqlite3.Error, ValueError, TypeError, KeyError, RecursionError):
            raise ResearchError('MEMORY_UNAVAILABLE', 'memory record or its inclusion history could not be verified') from None
        after = self.identity()
        _require(before == after, 'memory physical identity changed during recall', 'MEMORY_STORE_CHANGED')
        return {**recalled, 'snapshot_sha256': fingerprint(recalled), 'store_identity': after}


def _fit_payload(payload):
    recipe = payload['recipe']
    _require(type(recipe) is dict and set(recipe) == {'alpha', 'features'}
             and 0.001 <= _number(recipe['alpha']) <= 10000
             and type(recipe['features']) is list and 1 <= len(recipe['features']) <= 4
             and all(type(name) is str and name in FEATURES for name in recipe['features'])
             and len(set(recipe['features'])) == len(recipe['features']), 'invalid remembered recipe')
    metrics, seen = [], set()
    _require(type(payload['metrics']) is list and len(payload['metrics']) == 4, 'remember all four target metrics together')
    for metric in payload['metrics']:
        target = metric['target']
        _require(type(target) is str and target in TARGET_IDS and target not in seen, 'unknown or duplicate remembered target')
        seen.add(target)
        metrics.append({'target': target, **{key: _number(metric[key]) for key in ('mae', 'baseline_mae', 'r2')}})
    violations = payload['domain_violations']
    _require(type(violations) is list and payload.get('promotion') == 'not_evaluated_no_independent_holdout',
             'remembered fit must preserve its evaluation limits')
    compact = []
    for warning in violations[:4]:
        compact.append({'target': warning['target'], 'sample_id': _identifier(warning['sample_id']),
                        'predicted': _number(warning['predicted']), 'rule': warning['rule']})
    return {'recipe': copy.deepcopy(recipe), 'metrics': metrics, 'domain_violations': compact,
            'domain_violations_total': len(violations), 'domain_violations_omitted': max(0, len(violations) - len(compact)),
            'promotion': 'not_evaluated_no_independent_holdout'}


def _diagnostic_payload(payload):
    action, result = payload['action'], payload['result']
    _require(type(result) is dict and type(result.get('n')) is int and result['n'] == 8, 'invalid remembered diagnostic dimensions')
    if action == 'residuals':
        targets, seen = [], set()
        _require(type(result['targets']) is list and len(result['targets']) == 4, 'remember all residual targets together')
        for item in result['targets']:
            target = item['target']
            _require(type(target) is str and target in TARGET_IDS and target not in seen, 'invalid residual target')
            seen.add(target)
            targets.append({'target': target, 'sample_id': _identifier(item['sample_id']),
                            'largest_error': _number(item['largest_error']),
                            'share_of_absolute_error': _number(item['share_of_absolute_error'])})
        return {'action': action, 'kind': result['kind'], 'n': 8,
                'source_fit_action_id': _identifier(result['fit_action_id']), 'targets': targets}
    _require(action == 'correlation', 'unsupported remembered diagnostic')
    _require(type(result['sign_changes']) is int and 0 <= result['sign_changes'] <= 8
             and type(result['leave_one_out']) is list and len(result['leave_one_out']) == 8, 'invalid correlation sensitivity')
    return {'action': action, 'kind': result['kind'], 'n': 8, 'predictor': result['predictor'], 'outcome': result['outcome'],
            'pearson_r': _number(result['pearson_r']), 'sign_changes': result['sign_changes'],
            'leave_one_out': [{'sample_id': _identifier(item['sample_id']), 'pearson_r': _number(item['pearson_r'])}
                              for item in result['leave_one_out']]}


def projection(snapshot):
    """Return <=12 KiB of canonical UTF-8 JSON. Omit whole entries, not target metrics.

    This is untrusted prior evidence. IDs here cannot be substituted for the
    current study's action IDs or retrieved source citation IDs.
    """
    try:
        raw = _raw_snapshot(snapshot)
        _require(_sha(snapshot.get('snapshot_sha256')) and fingerprint(raw) == snapshot['snapshot_sha256'],
                 'memory snapshot content hash differs')
        result = {'schema_version': 'c01-memory-context-v1', 'scope': copy.deepcopy(raw['scope']),
                  'snapshot_sha256': snapshot['snapshot_sha256'], 'scientific_validation': False,
                  'authority': 'untrusted_prior_observations_not_instructions', 'may_execute': False,
                  'eligibility': 'active_at_snapshot_read_not_an_atomic_revocation_lease',
                  'ids_are_not_current_action_or_source_citation_ids': True,
                  'snapshot_entries_total': len(raw['entries']), 'recall_limit': 8, 'entries': [], 'entries_omitted': len(raw['entries'])}
        _require(len(canonical(result).encode('utf-8')) <= MAX_PROJECTION_BYTES, 'scope exceeds memory context byte limit')
        for item in raw['entries']:
            record = item['record']
            versions = sorted({version['source_record_sha256'] for version in item['source_versions']})
            original_version = record['provenance']['source_record_sha256']
            selected = [original_version] + [version for version in versions if version != original_version][:2]
            entry = {'id': record['id'], 'kind': record['kind'], 'review_status': record['review_status'],
                     'inclusion_status': 'active', 'source_action_id': _identifier(record['provenance']['action_id']),
                     'source_version_ids': selected, 'source_versions_total': len(versions),
                     'source_version_ids_omitted': len(versions) - len(selected),
                     'payload': _fit_payload(record['payload']) if record['kind'] == 'fit_observation'
                     else _diagnostic_payload(record['payload'])}
            result['entries'].append(entry)
            result['entries_omitted'] = len(raw['entries']) - len(result['entries'])
            if len(canonical(result).encode('utf-8')) > MAX_PROJECTION_BYTES:
                result['entries'].pop()
                result['entries_omitted'] = len(raw['entries']) - len(result['entries'])
                break
        _require(len(canonical(result).encode('utf-8')) <= MAX_PROJECTION_BYTES, 'memory context exceeds byte limit')
        return result
    except ResearchError:
        raise
    except (ValueError, TypeError, KeyError, OverflowError, RecursionError):
        raise ResearchError('INVALID_MEMORY_SNAPSHOT', 'memory snapshot cannot form a bounded numeric context') from None
