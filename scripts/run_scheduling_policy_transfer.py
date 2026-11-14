#!/usr/bin/env python3
"""One reviewed, bounded standalone scheduling study; no ResearchProject ledger.

This host-only CLI has no user-selected study, paths, code, inputs or strategy.
It will not generate inputs without an exact setup review and shared claim, and
will not execute a primary without the separate reviewed complete input manifest.
All locks and review records are cooperative trusted-local controls, not OS
isolation or protection from a party able to rewrite this user's files.
"""
import argparse
import base64
from contextlib import contextmanager
import gc
import hashlib
import importlib.metadata
import importlib.util
import inspect
import itertools
import json
import math
import os
from pathlib import Path
import platform
import signal
import stat
import statistics
import subprocess
import sys
import time

SOURCE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SOURCE_ROOT / 'src'))
from autoresearch.contracts import ResearchError, canonical, fingerprint
from autoresearch.bounded_study_ledger import BoundedStudyLedger, MAX_ELAPSED_NS
from autoresearch import scheduling_kernel as kernel, scheduling_threshold_policy as policy, research_project

MAIN_ROOT = Path('/workspace/auto-research-agentarts')
STUDY_ID = 'g5-scheduling-threshold-transfer-v1'
OUTPUT = MAIN_ROOT / 'runs/g5-scheduling-threshold-transfer-20261114-01'
CLAIMS = MAIN_ROOT / '.agent/study-claims'
WORKER = MAIN_ROOT / '.agent/autonomy/research-worker.lock'
REVIEWS = MAIN_ROOT / '.agent/study-reviews' / STUDY_ID
PROTOCOL_RELATIVE = 'docs/execution/g5-local/scheduling-threshold-transfer-protocol.json'
SOURCE_FILES = ('src/autoresearch/contracts.py', 'src/autoresearch/bounded_study_ledger.py',
                'src/autoresearch/scheduling_threshold_policy.py', 'src/autoresearch/scheduling_kernel.py',
                'scripts/run_scheduling_policy_transfer.py', 'scripts/verify_scheduling_policy_transfer.py', PROTOCOL_RELATIVE)
PREPARE_ID = 'prepare-g5-scheduling-threshold-transfer-v1'
PRIMARY_ID = 'primary-g5-scheduling-threshold-transfer-v1'
AUDIT_ID = 'audit-g5-scheduling-threshold-transfer-v1'
SIZES = (16, 24, 31, 32, 33, 34, 64, 128, 512)
SEEDS = (601, 602, 603)
ARMS = ('fixed_binary', 'fixed_scan', 'threshold32')
PERMUTATIONS = tuple(itertools.permutations(ARMS))
LIMITS = {'generate': 29, 'warmup': 162, 'timed': 972, 'correctness': 6, 'oracle': 29,
          'bruteforce': 2, 'audit': 1, 'primary': 1, 'kernel_total': 1140, 'scan_comparisons': 6080234,
          'exhaustive_subsets': 4352}
EXPECTED_BUDGET = {'generation': 29, 'kernel_warmup': 162, 'kernel_timed': 972, 'kernel_correctness': 6,
                   'kernel_total': 1140, 'fenwick': 29, 'brute': 2, 'exhaustive_subsets': 4352,
                   'scan_comparisons': 6080234, 'primary_attempts': 1, 'saved_audit_attempts': 1,
                   'maximum_elapsed_seconds': 120, 'research_concurrency': 1, 'estimator_fits': 0,
                   'model_sends': 0, 'external_API': 0, 'source_extraction': 0}
REVIEW_FIELDS = {'schema_version','status','reviewer','study_id','request_id','protocol_sha256','code_commit',
                 'output_root','budget_sha256','source_fingerprints','runtime','allowed_phase','limitations'}
THREAD_KEYS = ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS')


def _require(value, code, message):
    if not value:
        raise ResearchError(code, message)


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _safe(path):
    path = Path(path).absolute()
    for item in (path, *path.parents):
        _require(not item.is_symlink() and not getattr(item, 'is_junction', lambda: False)(),
                 'UNSAFE_PATH', 'Fixed study paths may not cross redirected locations.')
    return path


def _read(path, maximum, *, allow_empty=False):
    path = _safe(path)
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    except FileNotFoundError:
        raise ResearchError('STUDY_NOT_REVIEWED', 'A required fixed study file is unavailable.') from None
    with os.fdopen(fd, 'rb') as stream:
        info = os.fstat(stream.fileno())
        _require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1 and 0 <= info.st_size <= maximum
                 and (allow_empty or info.st_size > 0),
                 'EVIDENCE_CHANGED', 'A fixed study file is not a bounded unshared regular file.')
        raw = stream.read(maximum+1)
    _require(len(raw) <= maximum, 'EVIDENCE_CHANGED', 'A fixed study file exceeds its bound.')
    return raw


def _json(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            _require(key not in result, 'EVIDENCE_CHANGED', 'Duplicate JSON keys are not allowed.')
            result[key] = value
        return result
    def nonfinite(_):
        raise ResearchError('EVIDENCE_CHANGED', 'Nonfinite JSON is not allowed.')
    try:
        value = json.loads(raw.decode('utf-8'), object_pairs_hook=pairs, parse_constant=nonfinite)
        canonical(value)
        return value
    except (ValueError, TypeError, UnicodeError, RecursionError, OverflowError):
        raise ResearchError('EVIDENCE_CHANGED', 'Malformed fixed study JSON.') from None


def _write_once(path, value):
    path = _safe(path)
    raw = canonical(value).encode('utf-8')
    _require(len(raw) <= 32 * 1024 * 1024, 'STUDY_LIMIT', 'Saved study artifact is too large.')
    if path.exists():
        _require(_read(path, 32 * 1024 * 1024) == raw, 'STUDY_CONFLICT', 'An immutable study artifact already differs.')
        return False
    pending = path.with_name('.' + path.name + '.pending')
    _require(not pending.exists(), 'STUDY_UNKNOWN', 'A partial artifact exists; preserve it for review.')
    fd = os.open(pending, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'wb') as stream:
        stream.write(raw); stream.flush(); os.fsync(stream.fileno())
    # Exclusive link never replaces an existing artifact, even after a crash/race.
    os.link(pending, path, follow_symlinks=False)
    fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
        pending.unlink()
        os.fsync(fd)
    finally:
        os.close(fd)
    return True


def case_descriptors():
    result = [{'case_id': f'correct-n{n}-seed601', 'kind':'correctness', 'n':n, 'seed':601} for n in (8,12)]
    result += [{'case_id':f'perf-n{n}-seed{seed}', 'kind':'performance', 'n':n, 'seed':seed} for n in SIZES for seed in SEEDS]
    return result


def operation_plan(cases=None):
    """Return fixed operation IDs/specs; never generate inputs or call a solver."""
    descriptors = case_descriptors()
    result = [('gen-'+c['case_id'], 'generate', dict(c)) for c in descriptors]
    if cases is None:
        return result
    _require(type(cases) is list and len(cases) == len(descriptors), 'EVIDENCE_CHANGED', 'Fixed input case count differs.')
    for case, descriptor in zip(cases, descriptors):
        _require(all(case.get(k) == v for k,v in descriptor.items()), 'EVIDENCE_CHANGED', 'Input case order differs.')
        fixed = {k:case[k] for k in ('case_id','n','seed','jobs_sha256')}
        cid = case['case_id']
        result.append(('oracle-'+cid, 'oracle', fixed))
        if case['kind'] == 'correctness':
            for position, arm in enumerate(ARMS):
                result.append((f'correct-{cid}-{position:02d}', 'correctness', {**fixed,'phase':'correctness','position':position,'arm':arm}))
            result.append(('brute-'+cid, 'bruteforce', fixed))
        else:
            for position, arm in enumerate((*ARMS,*reversed(ARMS))):
                result.append((f'warm-{cid}-{position:02d}', 'warmup', {**fixed,'phase':'warmup','position':position,'arm':arm}))
            for block in range(2):
                for permutation_index, permutation in enumerate(PERMUTATIONS):
                    for within, arm in enumerate(permutation):
                        position = block*18 + permutation_index*3 + within
                        result.append((f'timed-{cid}-{position:02d}', 'timed', {**fixed,'phase':'timed',
                                       'position':position,'arm':arm,'block':block,'permutation_index':permutation_index}))
    return result


def validate_review(review, expected, stage, *, inputs_sha256=None, shared_claim_sha256=None):
    """Pure structural/binding validation; review identities are not signatures."""
    _require(stage in ('setup','input') and type(expected) is dict
             and set(expected) == {'protocol_sha256','code_commit','output_root','budget_sha256','source_fingerprints','runtime'},
             'INVALID_STUDY', 'Fixed review expectation is malformed.')
    extra = set() if stage == 'setup' else {'inputs_sha256','shared_claim_sha256'}
    schema = 'scheduling-policy-setup-review-v1' if stage == 'setup' else 'scheduling-policy-input-review-v1'
    request = PREPARE_ID if stage == 'setup' else PRIMARY_ID
    allowed = 'generate_only' if stage == 'setup' else 'primary_and_saved_audit'
    _require(type(review) is dict and set(review) == REVIEW_FIELDS | extra and review['schema_version'] == schema
             and review['status'] == 'approved' and review['study_id'] == STUDY_ID and review['request_id'] == request
             and review['allowed_phase'] == allowed and type(review['reviewer']) is str and 0 < len(review['reviewer'].strip()) <= 200
             and type(review['limitations']) is list and 1 <= len(review['limitations']) <= 20
             and all(type(x) is str and 0 < len(x.strip()) <= 4000 for x in review['limitations']),
             'STUDY_NOT_REVIEWED', 'Review does not approve the exact fixed phase and study.')
    for key, value in expected.items():
        _require(canonical(review[key]) == canonical(value), 'STUDY_NOT_REVIEWED', 'Review does not match fixed '+key+'.')
    if stage == 'input':
        _require(review['inputs_sha256'] == inputs_sha256 and review['shared_claim_sha256'] == shared_claim_sha256
                 and all(type(x) is str and len(x)==64 and all(c in '0123456789abcdef' for c in x)
                         for x in (inputs_sha256,shared_claim_sha256)),
                 'STUDY_NOT_REVIEWED', 'Input review does not bind the exact manifest and shared claim.')
    return True


def _git(*args):
    try:
        return subprocess.check_output(('git','-C',str(SOURCE_ROOT),*args), text=True, stderr=subprocess.DEVNULL).strip()
    except (OSError, subprocess.CalledProcessError):
        raise ResearchError('STUDY_CODE_CHANGED', 'The fixed source checkout cannot be verified.') from None


def _boot():
    try:
        value = _read('/proc/sys/kernel/random/boot_id', 128, allow_empty=True).decode('ascii').strip()
        _require(len(value) == 36 and all(c in '0123456789abcdef-' for c in value),
                 'STUDY_CLOCK_CHANGED', 'The local boot identity is malformed.')
        return value
    except (OSError, UnicodeError):
        raise ResearchError('STUDY_CLOCK_CHANGED', 'The local boot identity is unavailable.') from None


def _runtime():
    threads = {key:os.environ.get(key) for key in THREAD_KEYS}
    _require(all(value == '1' for value in threads.values()), 'STUDY_RUNTIME_CHANGED', 'Set all frozen thread variables to 1.')
    try:
        timer = time.get_clock_info('perf_counter')
        affinity = sorted(os.sched_getaffinity(0))
        packages = {name:importlib.metadata.version(name) for name in ('numpy','scipy','scikit-learn')}
    except (OSError, AttributeError, importlib.metadata.PackageNotFoundError):
        raise ResearchError('STUDY_RUNTIME_CHANGED', 'The fixed local runtime cannot be identified.') from None
    _require(timer.monotonic and not timer.adjustable and bool(affinity), 'STUDY_RUNTIME_CHANGED', 'Monotonic clock and CPU affinity are required.')
    return {'python_version':sys.version, 'python_executable':str(Path(sys.executable).absolute()),
            'python_implementation':platform.python_implementation(), 'dependencies':packages,
            'native_code_identity':research_project.code_identity(), 'boot_id':_boot(),
            'perf_counter':{'implementation':timer.implementation, 'monotonic':timer.monotonic,
                            'adjustable':timer.adjustable, 'resolution':timer.resolution},
            'gc_enabled':gc.isenabled(), 'cpu_affinity':affinity, 'thread_environment':threads}


def _fingerprints():
    return {relative:_sha(_read(SOURCE_ROOT/relative, 5*1024*1024)) for relative in SOURCE_FILES}


def _fixed_protocol():
    raw = _read(SOURCE_ROOT/PROTOCOL_RELATIVE, 1024*1024)
    protocol = _json(raw)
    _require(type(protocol) is dict and protocol.get('schema_version') == 'scheduling-policy-transfer-protocol-v1'
             and protocol.get('study_id') == STUDY_ID and protocol.get('main_repository') == str(MAIN_ROOT)
             and protocol.get('output_relative') == str(OUTPUT.relative_to(MAIN_ROOT))
             and protocol.get('global_ledger_relative') == '.agent/study-claims/scheduling-threshold-transfer.sqlite'
             and protocol.get('reviews_relative') == '.agent/study-reviews/'+STUDY_ID
             and protocol.get('requests') == {'prepare':PREPARE_ID,'primary':PRIMARY_ID,'audit':AUDIT_ID}
             and protocol.get('source_files') == list(SOURCE_FILES)
             and canonical(protocol.get('budget')) == canonical(EXPECTED_BUDGET), 'EVIDENCE_CHANGED', 'Fixed protocol or budget differs.')
    expected_cases = [{'id':c['case_id'],'phase':c['kind'],'n':c['n'],'seed':c['seed']} for c in case_descriptors()]
    expected_policy = {'id':'source-small-n-scan-v1','threshold':32,'if_n_le_threshold':'quadratic_scan_dp',
                       'otherwise':'binary_search_dp','allowed_arm_ids':list(ARMS),
                       'controls':{'fixed_binary':'binary_search_dp','fixed_scan':'quadratic_scan_dp'},
                       'candidate_changes_after_target_input_or_scores':False}
    measurement = protocol.get('measurement',{})
    _require(protocol.get('cases_in_generation_and_primary_order') == expected_cases
             and canonical(protocol.get('policy')) == canonical(expected_policy)
             and measurement.get('warmup_arm_orders') == [list(ARMS),list(reversed(ARMS))]
             and measurement.get('timed_arm_permutations_per_block') == [list(p) for p in PERMUTATIONS]
             and type(measurement.get('identical_ordered_blocks')) is int and measurement['identical_ordered_blocks'] == 2
             and type(measurement.get('timed_repetitions_each_arm_case')) is int and measurement['timed_repetitions_each_arm_case'] == 12
             and measurement.get('clock') == 'time.perf_counter_ns'
             and protocol.get('host_generator',{}).get('implementation') == 'autoresearch.scheduling_kernel.jobs_for(seed,n)'
             and protocol.get('elapsed_budget_policy',{}).get('maximum_active_seconds_total') == 120,
             'EVIDENCE_CHANGED', 'Fixed case roster, policy or permutation order differs.')
    return protocol, raw


def _environment():
    # All source worktrees must resolve to the same trusted main Git common dir.
    _require(SOURCE_ROOT == Path(_git('rev-parse','--show-toplevel')).resolve()
             and Path(_git('rev-parse','--path-format=absolute','--git-common-dir')).resolve() == (MAIN_ROOT/'.git').resolve(),
             'STUDY_CODE_CHANGED', 'Only a worktree of the fixed main repository may run this study.')
    _require(not _git('status','--porcelain','--untracked-files=normal'), 'STUDY_CODE_CHANGED', 'A clean frozen source checkout is required.')
    commit = _git('rev-parse','HEAD')
    _require(len(commit) == 40 and all(c in '0123456789abcdef' for c in commit), 'STUDY_CODE_CHANGED', 'Exact code commit is required.')
    protocol, raw = _fixed_protocol()
    sources = _fingerprints()
    _require(sources[PROTOCOL_RELATIVE] == _sha(raw)
             and sources['src/autoresearch/scheduling_kernel.py'] == '3a335e102279ce9e6a7a8861a3f203670fccfbfb3ea3d2941f8b9406ea92e401',
             'STUDY_CODE_CHANGED', 'Frozen protocol or original kernel differs.')
    expected = {'protocol_sha256':_sha(raw), 'code_commit':commit, 'output_root':str(OUTPUT),
                'budget_sha256':fingerprint(protocol['budget']), 'source_fingerprints':sources, 'runtime':_runtime()}
    return protocol, expected


def _same_environment(expected):
    protocol, current = _environment()
    _require(canonical(current) == canonical(expected), 'STUDY_CODE_CHANGED', 'Frozen source, commit or runtime changed.')
    return protocol


def _review(stage, expected, *, inputs_sha256=None, shared_claim_sha256=None):
    raw = _read(REVIEWS/('setup-review.json' if stage == 'setup' else 'input-review.json'), 65536)
    doc = _json(raw)
    validate_review(doc, expected, stage, inputs_sha256=inputs_sha256, shared_claim_sha256=shared_claim_sha256)
    return {'raw_base64':base64.b64encode(raw).decode('ascii'), 'raw_sha256':_sha(raw)}


def _ledger():
    return BoundedStudyLedger(CLAIMS, STUDY_ID, file_stem='scheduling-threshold-transfer', worker_path=WORKER)


def _protected(protocol):
    protected = protocol['protected']
    manifest_raw = _read(protected['manifest'], 4*1024*1024)
    paths_raw = _read(protected['old_paths'], 4*1024*1024)
    _require(_sha(manifest_raw) == protected['manifest_sha256'] and _sha(paths_raw) == protected['old_paths_sha256'],
             'EVIDENCE_CHANGED', 'Protected baseline identities differ.')
    manifest, sets = _json(manifest_raw), _json(paths_raw)
    _require(type(manifest) is dict and type(sets) is dict, 'EVIDENCE_CHANGED', 'Protected baseline is malformed.')
    for name, expected in manifest.items():
        raw = _read(name, 32*1024*1024, allow_empty=True)
        _require(type(expected) is dict and expected == {'bytes':len(raw),'sha256':_sha(raw)},
                 'EVIDENCE_CHANGED', 'A protected original file differs.')
    for name, expected in sets.items():
        root = _safe(name)
        _require(root.is_dir() and type(expected) is list, 'EVIDENCE_CHANGED', 'A protected original tree is missing.')
        actual = sorted(str(p.relative_to(root)) for p in root.rglob('*') if p.is_file())
        _require(actual == expected, 'EVIDENCE_CHANGED', 'A protected original path set differs.')


def _validator():
    path = SOURCE_ROOT/'scripts/verify_scheduling_policy_transfer.py'
    spec = importlib.util.spec_from_file_location('_fixed_scheduling_policy_verifier', path)
    _require(spec is not None and spec.loader is not None, 'STUDY_CODE_CHANGED', 'Fixed saved verifier cannot be loaded.')
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    original = MAIN_ROOT/'work/native-cpu-source-8e8a206/scripts/verify_native_cpu_cases.py'
    raw = _read(original, 5*1024*1024)
    _require(_sha(raw) == 'ba82a2afe5e765ccf02ac12765cbfb6f2213a0b815f6d0f4f12e539176cf2f0d',
             'STUDY_CODE_CHANGED', 'The original verifier source differs.')
    source = inspect.getsource(module.fenwick_optimum).rstrip('\n').encode()
    _require(len(source) == 620 and _sha(source) == 'ed8da57ef6eca1061e513fc328e2c5c95084ef599099ca401808fc841bd504a9',
             'STUDY_CODE_CHANGED', 'The fixed independent oracle source differs.')
    return module


def _expect_prefix(snapshot, plan):
    _require(not snapshot['unknown'] and not snapshot['failed'] and snapshot['halted'] is None,
             'STUDY_UNKNOWN', 'An earlier operation is unknown, failed or halted.')
    events = snapshot['events']
    _require(len(events)%2 == 0 and len(events)//2 <= len(plan), 'EVIDENCE_CHANGED', 'Operation history is incomplete or oversized.')
    for index in range(len(events)//2):
        reserved, receipt = events[2*index]['event'], events[2*index+1]['event']
        op_id, operation, spec = plan[index]
        _require(reserved['event']=='reserved' and receipt['event']=='completed'
                 and (reserved['op_id'],reserved['operation'],reserved['spec']) == (op_id,operation,spec),
                 'EVIDENCE_CHANGED', 'Stored operation order or specification differs from the fixed plan.')


@contextmanager
def _deadline(deadline_ns):
    remaining = (deadline_ns-time.monotonic_ns())/1_000_000_000
    _require(remaining > 0, 'STUDY_TIMEOUT', 'The original study time budget is exhausted.')
    def expired(_signum, _frame):
        raise TimeoutError('Original study deadline expired')
    _require(signal.getitimer(signal.ITIMER_REAL) == (0.0,0.0), 'STUDY_BUSY', 'An existing process timer cannot be replaced.')
    old_handler = signal.signal(signal.SIGALRM, expired)
    signal.setitimer(signal.ITIMER_REAL, remaining)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, old_handler)


def _latch_clock_failure(ledger, phase, error):
    snapshot = ledger.snapshot()
    if snapshot['halted'] is None:
        ledger.halt(reason='Study phase clock or deadline failed',
                    context={'phase':phase,'error_type':type(error).__name__,'message':str(error)[:1000]})


def _phase_start(ledger, phase, callback):
    try:
        return callback()
    except ResearchError as error:
        if error.code in ('STUDY_CLOCK_CHANGED','STUDY_TIMEOUT'):
            _latch_clock_failure(ledger,phase,error)
        raise


@contextmanager
def _phase_deadline(ledger, phase, deadline_ns):
    try:
        with _deadline(deadline_ns):
            yield
    except TimeoutError as error:
        _latch_clock_failure(ledger,phase,error)
        raise ResearchError('STUDY_TIMEOUT', 'The original study deadline expired; partial evidence is retained.') from error
    except ResearchError as error:
        if error.code in ('STUDY_CLOCK_CHANGED','STUDY_TIMEOUT'):
            _latch_clock_failure(ledger,phase,error)
        raise


def _create_output(claim, replayed):
    _safe(OUTPUT)
    if replayed:
        _require(OUTPUT.is_dir(), 'STUDY_UNKNOWN', 'Claim exists without its original output directory.')
        marker = _json(_read(OUTPUT/'claim.json', 65536))
        _require(marker == {'study_id':STUDY_ID,'claim_sha256':claim['claim_sha256']}, 'STUDY_CONFLICT', 'Output directory claim differs.')
    else:
        _require(not OUTPUT.exists(), 'STUDY_CONFLICT', 'Fixed study output already exists without this claim.')
        OUTPUT.mkdir(parents=True, exist_ok=False)
        _write_once(OUTPUT/'claim.json', {'study_id':STUDY_ID,'claim_sha256':claim['claim_sha256']})


def prepare():
    protocol, expected = _environment()
    setup = _review('setup', expected)
    _protected(protocol)
    _validator()  # Source identity only; never calls the independent oracle here.
    ledger = _ledger()
    if OUTPUT.exists() and not ledger.claim_file.exists():
        raise ResearchError('STUDY_CONFLICT', 'Fixed output exists without its shared claim.')
    binding = {'study_id':STUDY_ID, 'output_root':str(OUTPUT), 'request_id':PREPARE_ID, **expected,
               'setup_review_sha256':setup['raw_sha256']}
    claim = ledger.claim(binding, LIMITS)
    _create_output(claim, claim['replayed'])
    with ledger.worker():
        snapshot = ledger.snapshot()
        _require(snapshot['claim']['binding'] == binding, 'STUDY_CONFLICT', 'Stored claim does not match the reviewed setup.')
        existing = snapshot['phases']['generation_result']
        if existing is not None:
            raw = _read(OUTPUT/'inputs.json',32*1024*1024)
            _require(_sha(raw) == existing['manifest_sha256'], 'EVIDENCE_CHANGED', 'Original input manifest differs.')
            _require(existing['elapsed_ns'] < MAX_ELAPSED_NS, 'STUDY_TIMEOUT', 'Generation consumed the full original study time budget.')
            return {'status':'prepared','inputs_sha256':existing['manifest_sha256'],'claim_sha256':claim['claim_sha256'],'replayed':True}
        _expect_prefix(snapshot, operation_plan())
        phase = _phase_start(ledger,'generation',lambda:ledger.start_generation(
            now_ns=time.monotonic_ns(), boot_id=expected['runtime']['boot_id']))['phase']
        with _phase_deadline(ledger,'generation',phase['deadline_monotonic_ns']):
            cases=[]
            for case in case_descriptors():
                _same_environment(expected)
                _require(_review('setup',expected) == setup, 'STUDY_NOT_REVIEWED', 'The original setup review changed.')
                n, seed = case['n'], case['seed']
                receipt = ledger.perform('gen-'+case['case_id'], 'generate', case,
                    lambda n=n,seed=seed: {'jobs':[list(row) for row in kernel.jobs_for(seed,n)]},
                    boot_id=expected['runtime']['boot_id'])
                jobs = receipt['result']['jobs']
                _require(type(jobs) is list and len(jobs)==n and all(type(row) is list and len(row)==4 and all(type(v) is int for v in row) for row in jobs),
                         'EVIDENCE_CHANGED', 'Generated jobs differ from their fixed case.')
                cases.append({**case,'jobs':jobs,'jobs_sha256':fingerprint(jobs)})
            snapshot = ledger.snapshot()
            _expect_prefix(snapshot, operation_plan())
            _require(snapshot['counts']['generate']==29 and len(snapshot['events'])==58, 'STUDY_INCOMPLETE', 'Complete generation receipts required.')
            manifest = {'schema_version':'scheduling-threshold-inputs-v1','study_id':STUDY_ID,'cases':cases,
                        'generation_after_ordinal':len(snapshot['events']), 'generation_previous_event_sha256':snapshot['events'][-1]['sha256']}
            _write_once(OUTPUT/'inputs.json', manifest)
            _protected(protocol)
            _same_environment(expected)
            _require(_review('setup',expected) == setup, 'STUDY_NOT_REVIEWED', 'The original setup review changed.')
            finished = ledger.finish_generation(fingerprint(manifest), now_ns=time.monotonic_ns(), boot_id=expected['runtime']['boot_id'])
            _require(finished['phase']['elapsed_ns'] < MAX_ELAPSED_NS, 'STUDY_TIMEOUT', 'Generation used the complete study time budget.')
            return {'status':'prepared','inputs_sha256':fingerprint(manifest),'claim_sha256':claim['claim_sha256'],'replayed':False}


def _manifest(raw, snapshot):
    manifest = _json(raw)
    _require(canonical(manifest).encode() == raw and type(manifest) is dict
             and set(manifest) == {'schema_version','study_id','cases','generation_after_ordinal','generation_previous_event_sha256'}
             and manifest['schema_version'] == 'scheduling-threshold-inputs-v1' and manifest['study_id'] == STUDY_ID
             and type(manifest['cases']) is list and len(manifest['cases']) == 29
             and manifest['generation_after_ordinal'] == 58 and len(snapshot['events']) >= 58
             and manifest['generation_previous_event_sha256'] == snapshot['events'][57]['sha256'],
             'EVIDENCE_CHANGED', 'Reviewed input manifest or generation anchor differs.')
    for case, descriptor in zip(manifest['cases'],case_descriptors()):
        _require(type(case) is dict and set(case) == {'case_id','kind','n','seed','jobs','jobs_sha256'}
                 and all(case[k] == v for k,v in descriptor.items()) and type(case['jobs']) is list
                 and len(case['jobs']) == descriptor['n'] and fingerprint(case['jobs']) == case['jobs_sha256'],
                 'EVIDENCE_CHANGED', 'Reviewed complete case or job hash differs.')
        n = case['n']
        for index, row in enumerate(case['jobs']):
            _require(type(row) is list and len(row)==4 and all(type(v) is int for v in row)
                     and row[3] == index and 0 <= row[0] <= 10*n and 1 <= row[1]-row[0] <= max(2,n//4)
                     and 1 <= row[2] <= 100, 'EVIDENCE_CHANGED', 'A saved job is outside its fixed generator structure.')
    _require(sum(c['n'] for c in manifest['cases']) == 2642, 'EVIDENCE_CHANGED', 'Input job count differs.')
    for index, case in enumerate(manifest['cases']):
        event = snapshot['events'][index*2+1]['event']
        _require(event['event'] == 'completed' and event['operation'] == 'generate'
                 and event['result'] == {'jobs':case['jobs']}, 'EVIDENCE_CHANGED', 'Generation receipt and input manifest differ.')
    return manifest


def _check_run(jobs, returned, arm, oracle, reference):
    _require(type(returned) is dict and set(returned) == {'objective','schedule','full_scan_comparisons','operations'},
             'EVIDENCE_CHANGED', 'The saved scheduling result is malformed.')
    try:
        kernel.verify_schedule(jobs, returned)  # Saved-only feasibility/weight arithmetic, no solving.
        method = policy.method_for(arm, len(jobs))
        operations = returned['operations']
        scan = len(jobs)*(len(jobs)-1)//2 if method == 'quadratic_scan_dp' else 0
        _require(type(operations) is dict and set(operations) == {'dp_steps','full_scan_comparisons','bisect_calls','bisect_internal_comparisons','reconstruction_steps'}
                 and type(returned['objective']) is int and returned['objective'] == oracle
                 and type(returned['full_scan_comparisons']) is int and returned['full_scan_comparisons'] == scan
                 and all(type(operations[k]) is int for k in ('dp_steps','full_scan_comparisons','bisect_calls','reconstruction_steps'))
                 and operations['dp_steps'] == len(jobs) and operations['full_scan_comparisons'] == scan
                 and operations['bisect_calls'] == (len(jobs) if method == 'binary_search_dp' else 0)
                 and operations['bisect_internal_comparisons'] is None
                 and operations['reconstruction_steps'] == kernel.saved_reconstruction_steps(jobs,returned['schedule']),
                 'EVIDENCE_CHANGED', 'Saved schedule objective or operation counts differ.')
        pair = {'objective':returned['objective'],'schedule':returned['schedule']}
        _require(reference is None or pair == reference, 'EVIDENCE_CHANGED', 'Fixed arms or repeats disagree on the complete saved schedule.')
        return pair
    except (KeyError, TypeError, ValueError, OverflowError):
        raise ResearchError('EVIDENCE_CHANGED', 'Saved schedule feasibility or structure differs.') from None


def _check_timing(result):
    _require(type(result) is dict and set(result) == {'returned','elapsed_ns','timing_status','elapsed_raw'},
             'EVIDENCE_CHANGED', 'Saved timing receipt fields differ.')
    status, raw, elapsed = result['timing_status'], result['elapsed_raw'], result['elapsed_ns']
    if status == 'ok':
        _require(type(raw) is int and raw > 0 and type(elapsed) is int and elapsed == raw,
                 'EVIDENCE_CHANGED', 'Saved positive timing differs.')
    elif status == 'zero':
        _require(type(raw) is int and raw == 0 and elapsed is None, 'EVIDENCE_CHANGED', 'Saved zero timing differs.')
    elif status == 'negative':
        _require(type(raw) is int and raw < 0 and elapsed is None, 'EVIDENCE_CHANGED', 'Saved negative timing differs.')
    elif status == 'nonfinite':
        _require(raw in ('NaN','Infinity','-Infinity') and elapsed is None, 'EVIDENCE_CHANGED', 'Saved nonfinite timing differs.')
    else:
        raise ResearchError('EVIDENCE_CHANGED', 'Unknown saved timing state.')


def _halt_on_error(ledger, op_id, error):
    ledger.halt(reason='Saved result verification failed', context={'op_id':op_id,'error_type':type(error).__name__, 'message':str(error)[:1000]})
    raise ResearchError('STUDY_FAILED', 'A saved result failed its fixed check; study stopped without retry.') from error


def _run_case(ledger, case, verifier, boot_id):
    cid, jobs, n, seed = case['case_id'], case['jobs'], case['n'], case['seed']
    _require(len(jobs)==n and fingerprint(jobs)==case['jobs_sha256'], 'EVIDENCE_CHANGED', 'Case and reserved input identity differ.')
    fixed = {'case_id':cid,'n':n,'seed':seed,'jobs_sha256':case['jobs_sha256']}
    oracle_id = 'oracle-'+cid
    oracle = ledger.perform(oracle_id,'oracle',fixed,
        lambda:{'objective':verifier.fenwick_optimum([{'start':r[0],'end':r[1],'weight':r[2],'id':r[3]} for r in jobs])}, boot_id=boot_id)['result']
    if type(oracle) is not dict or set(oracle) != {'objective'} or type(oracle['objective']) is not int:
        _halt_on_error(ledger, oracle_id, ValueError('Independent saved objective is malformed'))
    objective = oracle['objective']
    reference = None
    if case['kind'] == 'correctness':
        specifications = [(f'correct-{cid}-{position:02d}','correctness',
                           {**fixed,'phase':'correctness','position':position,'arm':arm}) for position,arm in enumerate(ARMS)]
    else:
        specifications = [(f'warm-{cid}-{position:02d}','warmup',
                           {**fixed,'phase':'warmup','position':position,'arm':arm}) for position,arm in enumerate((*ARMS,*reversed(ARMS)))]
        specifications += [(f'timed-{cid}-{block*18+permutation_index*3+within:02d}','timed',
                           {**fixed,'phase':'timed','position':block*18+permutation_index*3+within,'arm':arm,
                            'block':block,'permutation_index':permutation_index})
                           for block in range(2) for permutation_index, permutation in enumerate(PERMUTATIONS)
                           for within,arm in enumerate(permutation)]
    for op_id, kind, spec in specifications:
        arm = spec['arm']
        # The callback is fixed here: spec arm and input hash are not user supplied.
        result = ledger.perform(op_id,kind,spec,
            (lambda arm=arm: {'returned':policy.dispatch(jobs,arm)}) if kind == 'correctness'
            else (lambda arm=arm: policy.measured(jobs,arm)), boot_id=boot_id)['result']
        try:
            _require(type(result) is dict and 'returned' in result, 'EVIDENCE_CHANGED', 'Saved run receipt is malformed.')
            if kind == 'correctness':
                _require(set(result) == {'returned'}, 'EVIDENCE_CHANGED', 'Saved correctness fields differ.')
            else:
                _check_timing(result)
            reference = _check_run(jobs,result['returned'],arm,objective,reference)
        except (ResearchError, TypeError, ValueError, KeyError) as error:
            _halt_on_error(ledger,op_id,error)
    if case['kind'] == 'correctness':
        op_id='brute-'+cid
        brute=ledger.perform(op_id,'bruteforce',fixed,lambda:{'objective':kernel.brute_force(jobs)},boot_id=boot_id)['result']
        if type(brute) is not dict or set(brute) != {'objective'} or type(brute['objective']) is not int or brute['objective'] != objective:
            _halt_on_error(ledger,op_id,ValueError('Saved exhaustive and independent objectives differ'))


def _summarize(cases, events):
    """Only the frozen arithmetic on complete saved times, with no new compute runs."""
    rows=[]
    completed = [item['event'] for item in events if item['event']['event']=='completed']
    by_case = {}
    for event in completed:
        cid = event['spec'].get('case_id')
        by_case.setdefault(cid,[]).append(event)
    for case in cases:
        if case['kind'] != 'performance':
            continue
        timings={arm:[] for arm in ARMS};invalid=[]
        for event in by_case.get(case['case_id'],[]):
            if event['operation'] not in ('warmup','timed'): continue
            result=event['result']; status=result['timing_status']
            if event['operation']=='warmup' and status != 'ok': invalid.append(event['op_id'])
            if event['operation']=='timed': timings[event['spec']['arm']].append(result['elapsed_ns'] if status=='ok' else None)
        _require(all(len(values)==12 for values in timings.values()), 'STUDY_INCOMPLETE', 'Stored timing coverage differs.')
        medians={arm:(statistics.median(values) if all(v is not None for v in values) else None) for arm,values in timings.items()}
        valid=not invalid and all(value is not None for value in medians.values())
        ratio=medians['threshold32']/medians['fixed_binary'] if valid and medians['fixed_binary']>0 else None
        _require(ratio is None or math.isfinite(ratio), 'EVIDENCE_CHANGED', 'Saved timing ratio is nonfinite.')
        rows.append({'case_id':case['case_id'],'n':case['n'],'seed':case['seed'],'median_ns':medians,
                     'policy_over_binary':ratio,'outcome':'uninterpretable' if ratio is None else 'faster' if ratio<1 else 'slower' if ratio>1 else 'tie',
                     'invalid_warmups':invalid})
    small=[row['policy_over_binary'] for row in rows if row['n']<=32]
    _require(len(rows)==27 and len(small)==12, 'STUDY_INCOMPLETE', 'Saved primary cases differ.')
    primary=statistics.median(small) if all(value is not None for value in small) else None
    return {'primary_case_count':12,'primary_policy_over_binary':primary,'primary_timing_interpretable':primary is not None,
            'performance_cases':rows,'scientific_validation':False,'scope':'saved timing arithmetic; no solver rerun or generalization'}


def _make_bundle(protocol, manifest, snapshot, setup, input_review, completion_clock):
    return {'schema_version':'scheduling-threshold-study-result-v1','study_id':STUDY_ID,
            'binding':snapshot['claim']['binding'],'reviews':{'setup':setup,'input':input_review},
            'input_manifest':manifest,'ledger':snapshot,'summary':_summarize(manifest['cases'],snapshot['events']),
            'limitations':protocol['limitations'],'completion_clock':completion_clock}


def _load_bound_inputs(ledger, expected):
    snapshot=ledger.snapshot()
    setup=_review('setup',expected)
    expected_binding={'study_id':STUDY_ID,'output_root':str(OUTPUT),'request_id':PREPARE_ID,**expected,
                      'setup_review_sha256':setup['raw_sha256']}
    _require(canonical(snapshot['claim']['binding']) == canonical(expected_binding)
             and snapshot['claim']['limits'] == LIMITS,
             'STUDY_CONFLICT', 'Original claim, source, runtime or budget differs from the reviewed setup.')
    raw=_read(OUTPUT/'inputs.json',32*1024*1024)
    manifest=_manifest(raw,snapshot)
    _require(snapshot['phases']['generation_result'] is not None
             and snapshot['phases']['generation_result']['manifest_sha256'] == _sha(raw), 'EVIDENCE_CHANGED', 'Generation completion does not bind the original manifest.')
    input_review=_review('input',expected,inputs_sha256=_sha(raw),shared_claim_sha256=snapshot['claim_sha256'])
    return snapshot,manifest,setup,input_review


def run_primary():
    protocol,expected=_environment()
    _protected(protocol)
    verifier=_validator()
    ledger=_ledger()
    with ledger.worker():
        snapshot,manifest,setup,input_review=_load_bound_inputs(ledger,expected)
        completed=snapshot['phases']['primary_result']
        if completed is not None:
            raw=_read(OUTPUT/'result.json',32*1024*1024)
            _require(_sha(raw)==completed['bundle_sha256'], 'EVIDENCE_CHANGED', 'Original primary result differs.')
            # Recovery of a missing derived snapshot never dispatches a research operation.
            if not (OUTPUT/'primary-ledger.json').exists():
                _write_once(OUTPUT/'primary-ledger.json',snapshot)
            return {'status':'completed','result_sha256':completed['bundle_sha256'],'replayed':True}
        plan=operation_plan(manifest['cases'])
        _expect_prefix(snapshot,plan)
        ledger.seal_inputs(fingerprint(manifest),input_review['raw_sha256'])
        phase=_phase_start(ledger,'primary',lambda:ledger.start_primary(
            now_ns=time.monotonic_ns(),boot_id=expected['runtime']['boot_id']))['phase']
        with _phase_deadline(ledger,'primary',phase['deadline_monotonic_ns']):
            saved_result = OUTPUT/'result.json'
            if not saved_result.exists():
                for case in manifest['cases']:
                    _same_environment(expected)
                    _require(_review('setup',expected) == setup
                             and _review('input',expected,inputs_sha256=fingerprint(manifest),
                                         shared_claim_sha256=snapshot['claim_sha256']) == input_review,
                             'STUDY_NOT_REVIEWED', 'A frozen review changed during primary execution.')
                    _run_case(ledger,case,verifier,expected['runtime']['boot_id'])
            snapshot=ledger.snapshot()
            _expect_prefix(snapshot,plan)
            _require(len(snapshot['events'])==2400 and all(snapshot['counts'][k]==LIMITS[k]
                     for k in ('generate','warmup','timed','correctness','oracle','bruteforce','kernel_total','scan_comparisons','exhaustive_subsets'))
                     and snapshot['counts']['audit']==0, 'STUDY_INCOMPLETE', 'Complete fixed primary receipts required.')
            if saved_result.exists():
                raw = _read(saved_result,32*1024*1024)
                previous = _json(raw)
                completion = previous.get('completion_clock') if type(previous) is dict else None
                _require(type(completion) is dict and set(completion) == {'boot_id','operations_finished_monotonic_ns'}
                         and completion['boot_id'] == expected['runtime']['boot_id']
                         and type(completion['operations_finished_monotonic_ns']) is int
                         and max(phase['started_monotonic_ns'], snapshot['events'][-1]['event']['monotonic_ns'])
                             <= completion['operations_finished_monotonic_ns'] < phase['deadline_monotonic_ns'],
                         'EVIDENCE_CHANGED', 'Saved primary completion clock differs.')
                bundle = _make_bundle(protocol,manifest,snapshot,setup,input_review,completion)
                _require(canonical(bundle).encode() == raw, 'EVIDENCE_CHANGED', 'Existing primary bundle differs from its original complete receipts.')
            else:
                finished_ns=time.monotonic_ns()
                _require(max(phase['started_monotonic_ns'], snapshot['events'][-1]['event']['monotonic_ns'])
                         <= finished_ns < phase['deadline_monotonic_ns'], 'STUDY_TIMEOUT', 'Primary operation deadline expired or clock reversed.')
                bundle=_make_bundle(protocol,manifest,snapshot,setup,input_review,
                                    {'boot_id':expected['runtime']['boot_id'],'operations_finished_monotonic_ns':finished_ns})
                _write_once(saved_result,bundle)
            _protected(protocol)
            _same_environment(expected)
            _require(_review('setup',expected) == setup
                     and _review('input',expected,inputs_sha256=fingerprint(manifest),
                                 shared_claim_sha256=snapshot['claim_sha256']) == input_review,
                     'STUDY_NOT_REVIEWED', 'A frozen review changed before primary completion.')
            result=ledger.finish_primary(fingerprint(bundle),now_ns=time.monotonic_ns(),boot_id=expected['runtime']['boot_id'])
        final_snapshot=ledger.snapshot()
        _write_once(OUTPUT/'primary-ledger.json',final_snapshot)
        return {'status':'completed','result_sha256':result['phase']['bundle_sha256'],'replayed':False}


def verify():
    protocol,expected=_environment()
    _protected(protocol)
    verifier=_validator()
    ledger=_ledger()
    with ledger.worker():
        snapshot,_,_,_=_load_bound_inputs(ledger,expected)
        _require(snapshot['phases']['primary_result'] is not None, 'STUDY_INCOMPLETE', 'The original primary result is not completed.')
        bundle=_json(_read(OUTPUT/'result.json',32*1024*1024))
        final_snapshot=_json(_read(OUTPUT/'primary-ledger.json',32*1024*1024))
        spec={'request_id':AUDIT_ID,'bundle_sha256':fingerprint(bundle),'primary_snapshot_sha256':fingerprint(final_snapshot)}
        receipt=ledger.perform(AUDIT_ID,'audit',spec,lambda:verifier.verify_primary_result(bundle,final_snapshot),boot_id=expected['runtime']['boot_id'])
        return {'status':'completed','audit':receipt['result'],'replayed':receipt['replayed']}


def status():
    ledger=_ledger()
    if not ledger.claim_file.exists() and not ledger.db.exists():
        return {'status':'not_claimed','study_id':STUDY_ID}
    snapshot=ledger.snapshot()
    return {'study_id':STUDY_ID,'claim_sha256':snapshot['claim_sha256'],'phases':snapshot['phases'],
            'counts':snapshot['counts'],'usage':snapshot['usage'],'unknown':snapshot['unknown'],
            'failed':snapshot['failed'],'halted':snapshot['halted']}


def resume():
    """Resume only the original phase, never infer completion from a file alone."""
    ledger = _ledger()
    snapshot = ledger.snapshot()
    _require(not snapshot['unknown'] and not snapshot['failed'] and snapshot['halted'] is None,
             'STUDY_UNKNOWN', 'An original operation is unknown, failed or halted; do not resume it.')
    generated = snapshot['phases']['generation_result']
    if generated is None:
        return prepare()
    _require(generated['elapsed_ns'] < MAX_ELAPSED_NS, 'STUDY_TIMEOUT', 'Generation consumed the full original study time budget.')
    _require((OUTPUT/'inputs.json').is_file(), 'STUDY_UNKNOWN', 'The original prepared input manifest is missing.')
    _require(_sha(_read(OUTPUT/'inputs.json',32*1024*1024)) == generated['manifest_sha256'],
             'EVIDENCE_CHANGED', 'The original prepared input manifest differs.')
    if not (REVIEWS/'input-review.json').is_file():
        _require(snapshot['phases']['input_review'] is None, 'EVIDENCE_CHANGED', 'The original accepted input review is missing.')
        return {'status':'awaiting_input_review','study_id':STUDY_ID,
                'inputs_sha256':generated['manifest_sha256'],'claim_sha256':snapshot['claim_sha256']}
    return run_primary()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=('prepare','run','status','resume','verify'))
    args=parser.parse_args()
    try:
        if args.command=='status': result=status()
        elif args.command=='prepare': result=prepare()
        elif args.command=='run': result=run_primary()
        elif args.command=='verify': result=verify()
        else: result=resume()
        print(json.dumps(result,ensure_ascii=False,allow_nan=False))
        return 0
    except (ResearchError,OSError,ValueError,TimeoutError) as error:
        print(json.dumps({'ok':False,'code':getattr(error,'code','STUDY_FAILED'),'message':str(error)},ensure_ascii=False))
        return 2


if __name__=='__main__':
    raise SystemExit(main())
