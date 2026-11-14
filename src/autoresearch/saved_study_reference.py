"""Read one fixed standalone study's saved evidence; never execute the study."""

import base64
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import stat

from .bounded_study_ledger import BoundedStudyLedger
from .contracts import ResearchError, canonical, fingerprint


_MAIN = Path('/workspace/auto-research-agentarts')
_SOURCE = Path('/workspace/work/scheduling-threshold-source-62f09ed')
_OUTPUT = _MAIN / 'runs/g5-scheduling-threshold-transfer-20261114-01'
_CLAIMS = _MAIN / '.agent/study-claims'
_REVIEWS = _MAIN / '.agent/study-reviews/g5-scheduling-threshold-transfer-v1'
_STUDY = 'g5-scheduling-threshold-transfer-v1'
_PREPARE = 'prepare-' + _STUDY
_PRIMARY = 'primary-' + _STUDY
_AUDIT = 'audit-' + _STUDY
_COMMIT = '62f09edbf15f90cdcd08450aab5d60199d44d63f'
_RUNTIME = 'e7310118c4af6bfad580aaef1b357019c4427d22c3189a235a8371bf7bc2711a'
_CLAIM_SHA = '8a6dd0f5a9ebd3d3439364c39bbf4b7b97e01a09652ab14c25ab85d7b206f3bb'
_PROTOCOL = 'docs/execution/g5-local/scheduling-threshold-transfer-protocol.json'
_SOURCE_SHAS = {
    'src/autoresearch/contracts.py': 'ddd701df5dc9abfd834ea92a30bc96e2b831801603ff30d0d8910155d897f778',
    'src/autoresearch/bounded_study_ledger.py': '1d39b54dd4dcc6eb1c477cc7c1d8c5f78d8a8e8fc362390189fe8a8d9ba535a4',
    'src/autoresearch/scheduling_threshold_policy.py': '0915de51b14bf16bdf399d5ae5b0ee057cf5a78d4ac9a8f9adb06c41b020eff5',
    'src/autoresearch/scheduling_kernel.py': '3a335e102279ce9e6a7a8861a3f203670fccfbfb3ea3d2941f8b9406ea92e401',
    'scripts/run_scheduling_policy_transfer.py': 'b6d9387aafe9263798857d104975c18b1c23d8d1e8256455694ab45c4d7cf10e',
    'scripts/verify_scheduling_policy_transfer.py': 'ddf0bed45734a49692399bfed5bddebb8ee1a54097647d1c81c061fc1c9bdd46',
    _PROTOCOL: '10d4776de34285549cb0ff2f7a8fbcf764c808aff81118baa47f5dd78f75cacd',
}
_EXPECTED_BYTES = {
    'marker': '8005ca608fae408613b5a12cf3935f5cebefe809be046e9869e8c7b56602ae95',
    'inputs': '41ac3517af0f7cff5917c2e614d438902198eaeb6cea5aa3fb6818f6be2b89b8',
    'result': '9d45e971b2e12448aabae5f80408dafc4c1ff3ee391bfc8f53906fd512b70f0f',
    'primary_ledger': '7bc24feb282c6c606e69eac1a7d05320466369974c3733ca89c450cabf0c7298',
    'setup_review': '986e80d6053080197985189f7e290cb35b1678a4efe122b7015453a5c1e37229',
    'input_review': '854add133d3777ecf3ad1ce9d0051874cb1bcf017e43d202a5fc4516a631045f',
}
_LIMITS = {'generate': 29, 'warmup': 162, 'timed': 972, 'correctness': 6,
           'oracle': 29, 'bruteforce': 2, 'audit': 1, 'primary': 1,
           'kernel_total': 1140, 'scan_comparisons': 6080234, 'exhaustive_subsets': 4352}
_FILES = {
    'marker': _OUTPUT / 'claim.json', 'inputs': _OUTPUT / 'inputs.json',
    'result': _OUTPUT / 'result.json', 'primary_ledger': _OUTPUT / 'primary-ledger.json',
    'global_claim': _CLAIMS / 'scheduling-threshold-transfer.claim.json',
    'ledger': _CLAIMS / 'scheduling-threshold-transfer.sqlite',
    'setup_review': _REVIEWS / 'setup-review.json', 'input_review': _REVIEWS / 'input-review.json',
    'source_head': _MAIN / '.git/worktrees/scheduling-threshold-source-62f09ed/HEAD',
    **{'source:' + key: _SOURCE / key for key in _SOURCE_SHAS},
}


class _ReferenceFailure(Exception):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status


def _require(condition, message):
    if not condition:
        raise _ReferenceFailure('integrity_error', message)


def _read_regular(path):
    """Read a fixed regular file without following symlinks or accepting races."""
    try:
        for part in (path, *path.parents):
            if part.is_symlink():
                raise _ReferenceFailure('integrity_error', 'A fixed path contains a symlink.')
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        with os.fdopen(fd, 'rb') as stream:
            before = os.fstat(stream.fileno())
            if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or before.st_size > 32 * 1024 * 1024:
                raise _ReferenceFailure('integrity_error', 'A fixed evidence file is not a bounded regular file.')
            data = stream.read(32 * 1024 * 1024 + 1)
            after = os.fstat(stream.fileno())
        current = path.stat(follow_symlinks=False)
        if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (
                after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns) or (
                after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns) != (
                current.st_dev, current.st_ino, current.st_size, current.st_mtime_ns, current.st_ctime_ns):
            raise _ReferenceFailure('unknown', 'Evidence changed while it was read.')
        return data
    except FileNotFoundError:
        raise _ReferenceFailure('unavailable', 'A required original evidence file is missing.') from None
    except OSError:
        raise _ReferenceFailure('unavailable', 'A required original evidence file cannot be read.') from None


def _json(data):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError('duplicate key')
            result[key] = value
        return result
    try:
        return json.loads(data, object_pairs_hook=unique,
                          parse_constant=lambda _: (_ for _ in ()).throw(ValueError('nonfinite')))
    except (ValueError, UnicodeError, RecursionError):
        raise _ReferenceFailure('integrity_error', 'An original JSON file is malformed.') from None


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _validate_evidence(raw, snapshot, expected_bytes, source_shas, claim_sha):
    """Pure saved-binding checks; private parameters support synthetic tests."""
    for name, digest in expected_bytes.items():
        _require(_sha(raw[name]) == digest, 'An original evidence fingerprint differs: ' + name)
    for path, digest in source_shas.items():
        _require(_sha(raw['source:' + path]) == digest, 'A frozen source fingerprint differs: ' + path)
    _require(raw['source_head'].decode('ascii').strip() == _COMMIT, 'The original source checkout commit differs.')
    claim, marker = _json(raw['global_claim']), _json(raw['marker'])
    manifest, result = _json(raw['inputs']), _json(raw['result'])
    primary_snapshot = _json(raw['primary_ledger'])
    setup, input_review = _json(raw['setup_review']), _json(raw['input_review'])
    protocol = _json(raw['source:' + _PROTOCOL])
    _require(snapshot['claim'] == claim and snapshot['claim_sha256'] == fingerprint(claim) == claim_sha,
             'The live ledger and original claim differ.')
    _require(marker == {'study_id': _STUDY, 'claim_sha256': claim_sha}, 'The original output marker differs.')
    _require(claim['schema_version'] == 'bounded-study-claim-v1' and claim['limits'] == _LIMITS,
             'The original claim or planned limits differ.')
    binding = claim['binding']
    _require(binding['study_id'] == _STUDY and binding['request_id'] == _PREPARE
             and binding['output_root'] == str(_OUTPUT) and binding['code_commit'] == _COMMIT
             and binding['runtime']['native_code_identity'] == _RUNTIME
             and binding['source_fingerprints'] == source_shas
             and binding['protocol_sha256'] == source_shas[_PROTOCOL]
             and binding['budget_sha256'] == fingerprint(protocol['budget'])
             and binding['setup_review_sha256'] == _sha(raw['setup_review']),
             'The reviewed claim, original code, protocol or budget differs.')
    review_keys = ('protocol_sha256', 'code_commit', 'output_root', 'budget_sha256', 'source_fingerprints', 'runtime')
    for review, name, request, phase in ((setup, 'setup', _PREPARE, 'generate_only'),
                                          (input_review, 'input', _PRIMARY, 'primary_and_saved_audit')):
        _require(review['schema_version'] == 'scheduling-policy-' + name + '-review-v1'
                 and review['status'] == 'approved' and review['study_id'] == _STUDY
                 and review['request_id'] == request and review['allowed_phase'] == phase
                 and type(review['reviewer']) is str and bool(review['reviewer'].strip())
                 and all(review[k] == binding[k] for k in review_keys), 'An original review differs from the claim.')
    _require(input_review['inputs_sha256'] == _sha(raw['inputs']) and input_review['shared_claim_sha256'] == claim_sha,
             'The input review does not bind the original inputs and claim.')
    _require(canonical(manifest).encode() == raw['inputs'] and canonical(result).encode() == raw['result']
             and canonical(primary_snapshot).encode() == raw['primary_ledger'], 'An original saved document is not canonical.')
    _require(result['schema_version'] == 'scheduling-threshold-study-result-v1' and result['study_id'] == _STUDY
             and result['binding'] == binding and result['input_manifest'] == manifest
             and result['limitations'] == protocol['limitations'], 'The saved result binding differs.')
    for name, source in (('setup', 'setup_review'), ('input', 'input_review')):
        _require(result['reviews'][name] == {'raw_base64': base64.b64encode(raw[source]).decode('ascii'),
                                             'raw_sha256': _sha(raw[source])}, 'A saved original review differs.')
    if snapshot['failed'] or snapshot['halted'] is not None:
        raise _ReferenceFailure('failed', 'The original ledger records failed or halted work.')
    if snapshot['unknown']:
        raise _ReferenceFailure('unknown', 'The original ledger contains an unresolved reservation.')
    events = snapshot['events']
    if len(events) != 2402 or snapshot['phases']['primary_result'] is None:
        raise _ReferenceFailure('unknown', 'The primary result or its single audit is incomplete.')
    _require(snapshot['counts'] == {k: v for k, v in _LIMITS.items() if k != 'primary'},
             'Actual operation counts do not match the fixed completed study.')
    for kind in ('generate', 'warmup', 'timed', 'correctness', 'oracle', 'bruteforce', 'audit'):
        _require(snapshot['usage'][kind] == {'reserved': _LIMITS[kind], 'completed': _LIMITS[kind],
                                            'failed': 0, 'unknown': 0}, 'Operation usage differs.')
    saved_ledger = result['ledger']
    _require(len(saved_ledger['events']) == 2400 and saved_ledger['phases']['primary_result'] is None
             and saved_ledger['events'] == events[:2400], 'The result does not contain the original primary event prefix.')
    for key in ('claim', 'claim_sha256', 'events', 'counts', 'usage', 'unknown', 'failed', 'halted'):
        _require(primary_snapshot[key] == saved_ledger[key], 'The post-primary snapshot changed saved evidence.')
    for key in ('generation', 'generation_result', 'input_review', 'primary'):
        _require(primary_snapshot['phases'][key] == saved_ledger['phases'][key] == snapshot['phases'][key],
                 'The original phase bindings differ.')
    _require(primary_snapshot['phases'] == snapshot['phases'], 'The primary completion receipt differs.')
    _require(snapshot['phases']['generation_result']['manifest_sha256'] == _sha(raw['inputs'])
             and snapshot['phases']['input_review']['review_sha256'] == _sha(raw['input_review'])
             and manifest['generation_after_ordinal'] == 58
             and manifest['generation_previous_event_sha256'] == events[57]['sha256'],
             'The input manifest or its review anchor differs.')
    receipt = snapshot['phases']['primary_result']
    _require(receipt['bundle_sha256'] == _sha(raw['result']) and receipt['after_ordinal'] == 2400
             and receipt['previous_event_sha256'] == events[2399]['sha256'], 'The primary completion receipt differs.')
    reservation, completion = (events[2400]['event'], events[2401]['event'])
    spec = {'request_id': _AUDIT, 'bundle_sha256': _sha(raw['result']),
            'primary_snapshot_sha256': _sha(raw['primary_ledger'])}
    _require(reservation['event'] == 'reserved' and completion['event'] == 'completed'
             and reservation['operation'] == completion['operation'] == 'audit'
             and reservation['op_id'] == completion['op_id'] == _AUDIT
             and reservation['spec'] == completion['spec'] == spec, 'The final audit is not bound to the original files.')
    audit = completion['result']
    _require(audit['schema_version'] == 'scheduling-threshold-primary-receipt-verification-v1'
             and audit['status'] == 'passed' and audit['bundle_sha256'] == _sha(raw['result'])
             and audit['saved_verification']['status'] == 'passed'
             and audit['saved_verification']['scientific_validation'] is False
             and audit['saved_verification']['summary'] == result['summary']
             and audit['saved_verification']['counts'] == saved_ledger['counts'], 'The saved audit result differs.')
    summary = result['summary']
    _require(type(summary['performance_cases']) is list and len(summary['performance_cases']) == 27,
             'The saved result does not contain all 27 case summaries.')
    return {'schema_version': 'saved-standalone-study-reference-v1', 'status': 'completed',
            'study_id': _STUDY, 'request_ids': {'prepare': _PREPARE, 'primary': _PRIMARY, 'audit': _AUDIT},
            'source_commit': _COMMIT, 'original_producer_runtime_identity': _RUNTIME, 'claim_sha256': claim_sha,
            'standalone': True, 'binding_only': True, 'numerical_recomputation': False, 'raw_data_included': False,
            'current_project_budget_unchanged': True, 'scientific_validation': False, 'may_execute': False,
            'planned_budget': protocol['budget'], 'actual_spent': {**snapshot['counts'], 'primary': 1},
            'saved_summary': summary,
            'saved_audit': {'status': audit['status'], 'schema_version': audit['schema_version'],
                            'oracle_scope': audit['saved_verification']['oracle_scope'],
                            'integrity_scope': audit['saved_verification']['integrity_scope']},
            'limitations': result['limitations'],
            'notice': 'Saved summary only; complete inputs and events remain in the referenced original files. This reader does not access or write project budgets and makes no assertion about concurrent project changes. Hashes and local reviews are not independent source authentication or scientific validation. No solver, oracle or formal audit was rerun. Development cost unknown.'}


def read_saved_study_reference():
    """Return a bounded read-only view of the one fixed original standalone study."""
    try:
        # A WAL or hot journal could change the logical database independently of
        # its main file; never infer a completed state from that situation.
        for suffix in ('-wal', '-shm', '-journal'):
            if Path(str(_FILES['ledger']) + suffix).exists():
                raise _ReferenceFailure('unknown', 'The original ledger has an active or unresolved SQLite sidecar.')
        _read_regular(_CLAIMS / 'scheduling-threshold-transfer.lock')
        raw = {key: _read_regular(path) for key, path in _FILES.items()}
        ledger = BoundedStudyLedger(_CLAIMS, _STUDY, file_stem='scheduling-threshold-transfer')
        snapshot = ledger.snapshot()
        for key, path in _FILES.items():
            if _read_regular(path) != raw[key]:
                raise _ReferenceFailure('unknown', 'Original evidence changed during the read.')
        for suffix in ('-wal', '-shm', '-journal'):
            if Path(str(_FILES['ledger']) + suffix).exists():
                raise _ReferenceFailure('unknown', 'The original ledger changed during the read.')
        result = _validate_evidence(raw, snapshot, _EXPECTED_BYTES, _SOURCE_SHAS, _CLAIM_SHA)
        result['raw_references'] = {key: {'path': str(_FILES[key]), 'bytes': len(value), 'sha256': _sha(value)}
                                    for key, value in raw.items()}
        if len(canonical(result).encode()) > 65536:
            raise _ReferenceFailure('integrity_error', 'The saved reference exceeds 64 KiB.')
        return result
    except _ReferenceFailure as error:
        return {'schema_version': 'saved-standalone-study-reference-v1', 'study_id': _STUDY,
                'status': error.status, 'reason': str(error), 'may_execute': False}
    except ResearchError as error:
        status = {'STUDY_NOT_FOUND': 'unavailable', 'STUDY_UNKNOWN': 'unknown'}.get(error.code, 'integrity_error')
        return {'schema_version': 'saved-standalone-study-reference-v1', 'study_id': _STUDY,
                'status': status, 'reason': 'The original ledger could not be verified: ' + error.code,
                'may_execute': False}
    except sqlite3.OperationalError:
        return {'schema_version': 'saved-standalone-study-reference-v1', 'study_id': _STUDY,
                'status': 'unknown', 'reason': 'The original ledger could not be read consistently.',
                'may_execute': False}
    except sqlite3.Error:
        return {'schema_version': 'saved-standalone-study-reference-v1', 'study_id': _STUDY,
                'status': 'integrity_error', 'reason': 'The original ledger is invalid or unreadable.',
                'may_execute': False}
    except (KeyError, IndexError, TypeError, ValueError, UnicodeError, RecursionError):
        return {'schema_version': 'saved-standalone-study-reference-v1', 'study_id': _STUDY,
                'status': 'integrity_error', 'reason': 'The original saved evidence is malformed.',
                'may_execute': False}
