"""Single-claim, write-ahead ledger for bounded standalone local studies.

This is not a ResearchProject/tool ledger and does not itself authorize work.
Every operation is durably reserved before its callback; an unreceipted reserve
is unknown forever and blocks new work. Cooperating callers share one lock.
"""
from contextlib import contextmanager
import copy
import fcntl
import json
import os
from pathlib import Path
import sqlite3
import stat
import time

from .contracts import ResearchError, canonical, fingerprint, identifier

OPERATIONS = ("generate", "warmup", "timed", "correctness", "oracle", "bruteforce", "audit")
LIMIT_FIELDS = set(OPERATIONS) | {"primary", "kernel_total", "scan_comparisons", "exhaustive_subsets"}
KERNEL_OPERATIONS = {"warmup", "timed", "correctness"}
MAX_RECORD_BYTES = 32 * 1024 * 1024
MAX_ELAPSED_NS = 120_000_000_000


def _require(value, code, message):
    if not value:
        raise ResearchError(code, message)


def _path(path):
    path = Path(path).absolute()
    for item in (path, *path.parents):
        _require(not item.is_symlink() and not getattr(item, 'is_junction', lambda: False)(),
                 'UNSAFE_PATH', 'Study paths may not cross redirected locations.')
    return path


def _regular(path):
    info = path.lstat()
    _require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1,
             'UNSAFE_PATH', 'Study ledger files must be unshared regular files.')


def _fsync_directory(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _read_json(path):
    _regular(path)
    raw = path.read_bytes()
    _require(0 < len(raw) <= MAX_RECORD_BYTES, 'EVIDENCE_CHANGED', 'Ledger record size changed.')
    try:
        value = json.loads(raw)
        _require(canonical(value).encode() == raw, 'EVIDENCE_CHANGED', 'Ledger record encoding changed.')
        return value
    except (ValueError, TypeError, UnicodeError, RecursionError):
        raise ResearchError('EVIDENCE_CHANGED', 'Malformed ledger record.') from None


def _create_once(path, value):
    raw = canonical(value).encode()
    _require(0 < len(raw) <= MAX_RECORD_BYTES, 'STUDY_LIMIT', 'Study record exceeds its bound.')
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        _fsync_directory(path.parent)
    except BaseException:
        # Keep any partial claim: it must never be silently replaced or retried.
        raise


def _limits(value):
    _require(type(value) is dict and set(value) == LIMIT_FIELDS
             and all(type(v) is int and 0 <= v <= 2**31 - 1 for v in value.values())
             and value['primary'] == 1 and value['audit'] <= 1,
             'INVALID_STUDY', 'Exact bounded operation limits and one primary are required.')
    _require(value['kernel_total'] == sum(value[key] for key in KERNEL_OPERATIONS),
             'INVALID_STUDY', 'Kernel limit must equal the declared operation limits.')
    return value


def _charge(operation, spec):
    if operation not in KERNEL_OPERATIONS:
        return 0
    _require(type(spec) is dict and type(spec.get('n')) is int and 0 <= spec['n'] <= 4096
             and spec.get('arm') in ('fixed_binary', 'fixed_scan', 'threshold32'),
             'INVALID_STUDY', 'A fixed arm and bounded job count are required.')
    n, arm = spec['n'], spec['arm']
    return n * (n - 1) // 2 if arm == 'fixed_scan' or (arm == 'threshold32' and n <= 32) else 0


def _subsets(operation, spec):
    if operation != 'bruteforce':
        return 0
    _require(type(spec) is dict and type(spec.get('n')) is int and 0 <= spec['n'] <= 12,
             'INVALID_STUDY', 'Exhaustive checking requires an explicit bounded job count.')
    return 1 << spec['n']


class BoundedStudyLedger:
    """Durable shared claim and append-only operation history under a host path."""

    def __init__(self, claims_directory, study_id, *, file_stem=None, worker_path=None):
        identifier(study_id, 'study_id')
        file_stem = study_id if file_stem is None else identifier(file_stem, 'file_stem')
        self.root = _path(claims_directory)
        self.study_id = study_id
        self.claim_file = self.root / (file_stem + '.claim.json')
        self.db = self.root / (file_stem + '.sqlite')
        self.lock_file = self.root / (file_stem + '.lock')
        # One shared cooperative heavy-research slot across all study stems.
        self.worker_file = _path(worker_path) if worker_path is not None else self.root / 'research-worker.lock'
        self._worker_fd = None
        self._worker_pid = None
        self._history_cache = None

    @contextmanager
    def _locked(self, *, create=False):
        _path(self.root)
        if create:
            self.root.mkdir(parents=True, exist_ok=True)
        _require(self.root.is_dir(), 'STUDY_NOT_FOUND', 'No shared study claim directory exists.')
        flags = os.O_RDWR | os.O_NOFOLLOW | (os.O_CREAT if create else 0)
        try:
            fd = os.open(self.lock_file, flags, 0o600)
        except FileNotFoundError:
            raise ResearchError('STUDY_NOT_FOUND', 'No shared study claim exists.') from None
        with os.fdopen(fd, 'r+b') as lock:
            info = os.fstat(lock.fileno())
            _require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1, 'UNSAFE_PATH', 'Invalid study lock file.')
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(lock.fileno(), fcntl.LOCK_UN)

    @contextmanager
    def _connect(self, *, create=False, readonly=False):
        _path(self.db)
        if not create:
            _require(self.db.exists(), 'STUDY_UNKNOWN', 'Claim exists without its ledger; preserve and review.')
            _regular(self.db)
        con = sqlite3.connect(self.db if create else self.db.as_uri() + ('?mode=ro' if readonly else '?mode=rw'),
                              uri=not create, timeout=10)
        con.row_factory = sqlite3.Row
        try:
            if not readonly:
                con.execute('PRAGMA synchronous=FULL')
                con.execute('PRAGMA journal_mode=DELETE')
            if create:
                con.executescript('''CREATE TABLE meta (key TEXT PRIMARY KEY, record TEXT NOT NULL, sha256 TEXT NOT NULL);
                    CREATE TABLE events (ordinal INTEGER PRIMARY KEY, record TEXT NOT NULL, sha256 TEXT NOT NULL);
                    CREATE TRIGGER meta_no_update BEFORE UPDATE ON meta BEGIN SELECT RAISE(ABORT,'immutable metadata'); END;
                    CREATE TRIGGER meta_no_delete BEFORE DELETE ON meta BEGIN SELECT RAISE(ABORT,'immutable metadata'); END;
                    CREATE TRIGGER events_no_update BEFORE UPDATE ON events BEGIN SELECT RAISE(ABORT,'immutable events'); END;
                    CREATE TRIGGER events_no_delete BEFORE DELETE ON events BEGIN SELECT RAISE(ABORT,'immutable events'); END;''')
                _fsync_directory(self.root)
            con.execute('BEGIN' if readonly else 'BEGIN IMMEDIATE')
            yield con
            con.commit()
        except BaseException:
            con.rollback()
            raise
        finally:
            con.close()

    @staticmethod
    def _meta(con, key):
        row = con.execute('SELECT record,sha256 FROM meta WHERE key=?', (key,)).fetchone()
        if row is None:
            return None
        try:
            value = json.loads(row['record'])
            _require(canonical(value) == row['record'] and fingerprint(value) == row['sha256'],
                     'EVIDENCE_CHANGED', 'Immutable study metadata changed.')
            return value
        except (ValueError, TypeError, UnicodeError, RecursionError):
            raise ResearchError('EVIDENCE_CHANGED', 'Malformed study metadata.') from None

    @staticmethod
    def _put_meta(con, key, value):
        old = BoundedStudyLedger._meta(con, key)
        if old is not None:
            _require(old == value, 'STUDY_CONFLICT', 'Study phase is already bound to different content.')
            return False
        con.execute('INSERT INTO meta VALUES(?,?,?)', (key, canonical(value), fingerprint(value)))
        return True

    def claim(self, binding, limits):
        _require(type(binding) is dict and binding.get('study_id') == self.study_id,
                 'INVALID_STUDY', 'The shared claim must bind this exact study identity.')
        _limits(limits)
        claim = {'schema_version': 'bounded-study-claim-v1', 'binding': binding, 'limits': limits}
        _require(len(canonical(claim).encode()) <= 65536, 'INVALID_STUDY', 'Claim metadata is too large.')
        with self._locked(create=True):
            claim_exists, db_exists = self.claim_file.exists(), self.db.exists()
            _require(not db_exists or claim_exists, 'STUDY_UNKNOWN', 'Ledger exists without its immutable claim.')
            if claim_exists:
                _require(_read_json(self.claim_file) == claim, 'STUDY_CONFLICT', 'Study identity already binds different content or output root.')
                _require(db_exists, 'STUDY_UNKNOWN', 'Claim exists without its ledger; preserve and review.')
                with self._connect() as con:
                    _require(self._meta(con, 'claim') == claim, 'EVIDENCE_CHANGED', 'Ledger and global claim differ.')
                    self._history(con, claim)
                return {'claim_sha256': fingerprint(claim), 'replayed': True}
            _create_once(self.claim_file, claim)
            with self._connect(create=True) as con:
                self._put_meta(con, 'claim', claim)
            return {'claim_sha256': fingerprint(claim), 'replayed': False}

    @contextmanager
    def worker(self):
        """One cooperating study worker across the full prepare or primary loop."""
        _require(self._worker_fd is None, 'STUDY_BUSY', 'This ledger already owns a worker slot.')
        with self._locked():
            with self._connect(readonly=True) as con:
                claim = self._claimed(con)
                _, operations, _ = self._history(con, claim, refresh=True)
                _require(self._meta(con, 'halt') is None, 'STUDY_FAILED', 'Study has a recorded terminal failure.')
                _require(all(item['status'] == 'completed' for item in operations.values()),
                         'STUDY_UNKNOWN', 'An earlier operation is unfinished or failed; stop.')
            _path(self.worker_file)
            fd = os.open(self.worker_file, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
            info = os.fstat(fd)
            _require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1, 'UNSAFE_PATH', 'Invalid worker lock file.')
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                os.close(fd)
                raise ResearchError('STUDY_BUSY', 'Another worker owns the one-study execution slot.') from None
            self._worker_fd = fd
            self._worker_pid = os.getpid()
        try:
            yield
        finally:
            self._worker_fd = None
            self._worker_pid = None
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)

    def _require_worker(self):
        _require(self._worker_fd is not None and self._worker_pid == os.getpid(),
                 'STUDY_WORKER_REQUIRED', 'The shared study worker slot must be held before changes.')
        try:
            current, expected = os.fstat(self._worker_fd), self.worker_file.lstat()
            _require(stat.S_ISREG(current.st_mode) and current.st_nlink == 1
                     and (current.st_dev, current.st_ino) == (expected.st_dev, expected.st_ino),
                     'STUDY_WORKER_REQUIRED', 'Shared worker lock identity differs.')
        except OSError:
            raise ResearchError('STUDY_WORKER_REQUIRED', 'Shared worker lock is no longer held.') from None

    def _claimed(self, con):
        _require(self.claim_file.exists(), 'STUDY_UNKNOWN', 'Immutable global study claim is missing.')
        claim = _read_json(self.claim_file)
        _require(self._meta(con, 'claim') == claim and claim['binding']['study_id'] == self.study_id,
                 'EVIDENCE_CHANGED', 'Global claim and ledger differ.')
        _limits(claim['limits'])
        return claim

    def _history(self, con, claim, *, refresh=False):
        triggers = {row[0] for row in con.execute("SELECT name FROM sqlite_master WHERE type='trigger'")}
        _require(triggers == {'meta_no_update', 'meta_no_delete', 'events_no_update', 'events_no_delete'},
                 'EVIDENCE_CHANGED', 'Append-only ledger protection differs.')
        identity = (fingerprint(claim), self.db.stat().st_ino, self.db.stat().st_dev)
        if not refresh and self._history_cache is not None and self._history_cache[0] == identity:
            events = list(self._history_cache[1])
            operations = {key: dict(value) for key, value in self._history_cache[2].items()}
        else:
            events, operations = [], {}
        previous = events[-1]['sha256'] if events else fingerprint(claim)
        for row in con.execute('SELECT ordinal,record,sha256 FROM events WHERE ordinal>? ORDER BY ordinal', (len(events),)):
            try:
                event = json.loads(row['record'])
                _require(canonical(event) == row['record'] and fingerprint(event) == row['sha256']
                         and type(event) is dict and set(event) == {'ordinal','previous_sha256','event','op_id','operation','spec','reservation_sha256','result','result_sha256','boot_id','monotonic_ns'}
                         and event['ordinal'] == row['ordinal'] == len(events)+1 and event['previous_sha256'] == previous
                         and event['operation'] in OPERATIONS and type(event['spec']) is dict,
                         'EVIDENCE_CHANGED', 'Study event chain differs.')
                identifier(event['op_id'], 'op_id')
                old = operations.get(event['op_id'])
                if event['event'] == 'reserved':
                    _require(old is None and event['reservation_sha256'] is None and event['result'] is None and event['result_sha256'] is None,
                             'EVIDENCE_CHANGED', 'Duplicate or malformed reservation.')
                    _charge(event['operation'], event['spec'])
                    _subsets(event['operation'], event['spec'])
                    operations[event['op_id']] = {'reserved': event, 'reservation_sha256': row['sha256'], 'status': 'unknown', 'result': None}
                else:
                    _require(event['event'] in ('completed','failed') and old is not None and old['status'] == 'unknown'
                             and event['operation'] == old['reserved']['operation'] and event['spec'] == old['reserved']['spec']
                             and event['reservation_sha256'] == old['reservation_sha256']
                             and event['result_sha256'] == fingerprint(event['result']), 'EVIDENCE_CHANGED', 'Receipt differs from its reservation.')
                    old.update(status=event['event'], result=event['result'])
                events.append({'event': event, 'sha256': row['sha256']})
                previous = row['sha256']
            except (ValueError, TypeError, KeyError, UnicodeError, RecursionError):
                raise ResearchError('EVIDENCE_CHANGED', 'Malformed study event history.') from None
        _require(con.execute('SELECT count(*) FROM events').fetchone()[0] == len(events),
                 'EVIDENCE_CHANGED', 'Study event history is missing or duplicated.')
        counts = {kind: sum(item['reserved']['operation'] == kind for item in operations.values()) for kind in OPERATIONS}
        counts['kernel_total'] = sum(counts[kind] for kind in KERNEL_OPERATIONS)
        counts['scan_comparisons'] = sum(_charge(item['reserved']['operation'], item['reserved']['spec']) for item in operations.values())
        counts['exhaustive_subsets'] = sum(_subsets(item['reserved']['operation'], item['reserved']['spec']) for item in operations.values())
        _require(all(counts[k] <= claim['limits'][k] for k in counts), 'EVIDENCE_CHANGED', 'Study history exceeds its frozen budget.')
        review = BoundedStudyLedger._meta(con, 'input_review')
        generation = BoundedStudyLedger._meta(con, 'generation')
        generation_result = BoundedStudyLedger._meta(con, 'generation_result')
        primary = BoundedStudyLedger._meta(con, 'primary')
        completed = BoundedStudyLedger._meta(con, 'primary_result')
        halted = BoundedStudyLedger._meta(con, 'halt')

        def anchor(phase):
            ordinal = phase.get('after_ordinal')
            _require(type(ordinal) is int and 0 <= ordinal <= len(events)
                     and phase.get('previous_event_sha256') == (events[ordinal-1]['sha256'] if ordinal else fingerprint(claim)),
                     'EVIDENCE_CHANGED', 'Study phase no longer anchors its event history.')

        if generation is not None:
            _require(type(generation) is dict and set(generation) == {'schema_version','study_id','boot_id','started_monotonic_ns','deadline_monotonic_ns','after_ordinal','previous_event_sha256'}
                     and generation['schema_version'] == 'bounded-study-generation-v1'
                     and generation['study_id'] == claim['binding']['study_id'] and type(generation['boot_id']) is str and generation['boot_id']
                     and type(generation['started_monotonic_ns']) is int and generation['started_monotonic_ns'] >= 0
                     and generation['deadline_monotonic_ns'] == generation['started_monotonic_ns'] + MAX_ELAPSED_NS
                     and generation['after_ordinal'] == 0, 'EVIDENCE_CHANGED', 'Generation timing metadata differs.')
            anchor(generation)
            previous_clock = generation['started_monotonic_ns']
            for index, item in enumerate(events):
                event = item['event']
                _require(event['boot_id'] == generation['boot_id'], 'EVIDENCE_CHANGED', 'Study event boot identity differs.')
                value = event['monotonic_ns']
                if event['event'] == 'failed':
                    _require(index == len(events)-1 and (value is None or type(value) is int),
                             'EVIDENCE_CHANGED', 'Failure clock evidence differs or work followed failure.')
                else:
                    _require(type(value) is int and value >= previous_clock, 'EVIDENCE_CHANGED', 'Study monotonic event clock reversed.')
                if type(value) is int:
                    previous_clock = value
        if generation_result is not None:
            _require(generation is not None and type(generation_result) is dict
                     and set(generation_result) == {'schema_version','manifest_sha256','boot_id','finished_monotonic_ns','elapsed_ns','after_ordinal','previous_event_sha256'}
                     and generation_result['schema_version'] == 'bounded-study-generation-result-v1'
                     and generation_result['boot_id'] == generation['boot_id']
                     and type(generation_result['finished_monotonic_ns']) is int
                     and generation_result['elapsed_ns'] == generation_result['finished_monotonic_ns'] - generation['started_monotonic_ns'] >= 0
                     and generation_result['after_ordinal'] == 2 * claim['limits']['generate'],
                     'EVIDENCE_CHANGED', 'Generation completion timing differs.')
            anchor(generation_result)
        if review is not None:
            _require(type(review) is dict and set(review) == {'schema_version','manifest_sha256','review_sha256','after_ordinal','previous_event_sha256'}
                     and review['schema_version'] == 'bounded-study-input-review-v1' and generation_result is not None
                     and review['manifest_sha256'] == generation_result['manifest_sha256']
                     and generation_result['elapsed_ns'] < MAX_ELAPSED_NS, 'EVIDENCE_CHANGED', 'Input review metadata differs.')
            anchor(review)
            _require(review['after_ordinal'] == 2 * claim['limits']['generate']
                     and all(item['event']['operation'] == 'generate' for item in events[:review['after_ordinal']]),
                     'EVIDENCE_CHANGED', 'Input review must follow all generation receipts.')
        if primary is not None:
            _require(review is not None and type(primary) is dict and set(primary) == {'schema_version','study_id','input_review_sha256','boot_id','started_monotonic_ns','deadline_monotonic_ns','after_ordinal','previous_event_sha256'}
                     and primary['schema_version'] == 'bounded-study-primary-v1'
                     and primary['study_id'] == claim['binding']['study_id']
                     and primary['input_review_sha256'] == fingerprint(review)
                     and primary['boot_id'] == generation['boot_id']
                     and type(primary['started_monotonic_ns']) is int and primary['started_monotonic_ns'] >= generation_result['finished_monotonic_ns']
                     and primary['deadline_monotonic_ns'] == primary['started_monotonic_ns'] + MAX_ELAPSED_NS - generation_result['elapsed_ns']
                     and primary['after_ordinal'] == review['after_ordinal'], 'EVIDENCE_CHANGED', 'Primary phase differs from input review.')
            anchor(primary)
        if completed is not None:
            _require(primary is not None and type(completed) is dict and set(completed) == {'schema_version','bundle_sha256','boot_id','finished_monotonic_ns','after_ordinal','previous_event_sha256'}
                     and completed['schema_version'] == 'bounded-study-primary-result-v1'
                     and completed['boot_id'] == primary['boot_id']
                     and type(completed['finished_monotonic_ns']) is int
                     and primary['started_monotonic_ns'] <= completed['finished_monotonic_ns'] < primary['deadline_monotonic_ns'],
                     'EVIDENCE_CHANGED', 'Primary result metadata differs.')
            anchor(completed)
        if halted is not None:
            _require(type(halted) is dict and set(halted) == {'schema_version','reason','context','after_ordinal','previous_event_sha256'}
                     and halted['schema_version'] == 'bounded-study-halt-v1' and type(halted['reason']) is str
                     and 0 < len(halted['reason']) <= 1000 and type(halted['context']) is dict,
                     'EVIDENCE_CHANGED', 'Terminal failure metadata differs.')
            anchor(halted)
            _require(halted['after_ordinal'] == len(events), 'EVIDENCE_CHANGED', 'Operations followed a terminal failure.')
        for item in events:
            event = item['event']
            if event['operation'] == 'generate':
                _require(generation is not None and (generation_result is None or event['ordinal'] <= generation_result['after_ordinal']),
                         'EVIDENCE_CHANGED', 'Generation operation is outside its frozen phase.')
            if event['operation'] != 'generate':
                _require(primary is not None and event['ordinal'] > primary['after_ordinal'],
                         'EVIDENCE_CHANGED', 'Primary operation precedes the reviewed phase.')
            if event['operation'] == 'audit':
                _require(completed is not None and event['ordinal'] > completed['after_ordinal'],
                         'EVIDENCE_CHANGED', 'Audit operation precedes the primary result.')
        self._history_cache = (identity, events, operations)
        return events, operations, counts

    @staticmethod
    def _append(con, claim, events, op_id, operation, spec, event_type, reservation_sha=None, result=None, *, boot_id, monotonic_ns):
        event = {'ordinal': len(events)+1, 'previous_sha256': events[-1]['sha256'] if events else fingerprint(claim),
                 'event': event_type, 'op_id': op_id, 'operation': operation, 'spec': spec,
                 'reservation_sha256': reservation_sha, 'result': result, 'boot_id': boot_id, 'monotonic_ns': monotonic_ns,
                 'result_sha256': fingerprint(result) if event_type != 'reserved' else None}
        raw = canonical(event)
        _require(len(raw.encode()) <= MAX_RECORD_BYTES, 'STUDY_LIMIT', 'Operation receipt exceeds its byte limit.')
        digest = fingerprint(event)
        con.execute('INSERT INTO events VALUES(?,?,?)', (event['ordinal'], raw, digest))
        return digest

    def start_generation(self, *, now_ns, boot_id):
        self._require_worker()
        _require(type(now_ns) is int and now_ns >= 0 and type(boot_id) is str and 0 < len(boot_id) <= 128,
                 'INVALID_STUDY', 'Monotonic start and boot identity are required.')
        with self._locked(), self._connect() as con:
            claim = self._claimed(con)
            events, _, _ = self._history(con, claim)
            old = self._meta(con, 'generation')
            if old is not None:
                _require(old['boot_id'] == boot_id and now_ns >= (events[-1]['event']['monotonic_ns'] if events else old['started_monotonic_ns']),
                         'STUDY_CLOCK_CHANGED', 'Generation cannot resume across boots or a reversed monotonic clock.')
                return {'phase': old, 'sha256': fingerprint(old), 'replayed': True}
            _require(not events, 'STUDY_UNKNOWN', 'Generation cannot begin after any operation.')
            value = {'schema_version': 'bounded-study-generation-v1', 'study_id': self.study_id, 'boot_id': boot_id,
                     'started_monotonic_ns': now_ns, 'deadline_monotonic_ns': now_ns + MAX_ELAPSED_NS,
                     'after_ordinal': 0, 'previous_event_sha256': fingerprint(claim)}
            self._put_meta(con, 'generation', value)
            return {'phase': value, 'sha256': fingerprint(value), 'replayed': False}

    def finish_generation(self, manifest_sha256, *, now_ns, boot_id):
        self._require_worker()
        _require(type(manifest_sha256) is str and len(manifest_sha256) == 64 and all(c in '0123456789abcdef' for c in manifest_sha256)
                 and type(now_ns) is int and now_ns >= 0 and type(boot_id) is str,
                 'INVALID_STUDY', 'Generation completion requires its manifest and monotonic clock.')
        with self._locked(), self._connect() as con:
            claim = self._claimed(con)
            events, operations, counts = self._history(con, claim)
            generation = self._meta(con, 'generation')
            _require(generation is not None and boot_id == generation['boot_id']
                     and now_ns >= (events[-1]['event']['monotonic_ns'] if events else generation['started_monotonic_ns']),
                     'STUDY_CLOCK_CHANGED', 'Generation boot or monotonic clock changed.')
            old = self._meta(con, 'generation_result')
            if old is not None:
                _require(old['manifest_sha256'] == manifest_sha256 and old['boot_id'] == boot_id,
                         'STUDY_CONFLICT', 'Generation result is already bound to another manifest.')
                return {'phase': old, 'sha256': fingerprint(old), 'replayed': True}
            _require(counts['generate'] == claim['limits']['generate'] and all(x['status'] == 'completed' for x in operations.values()),
                     'STUDY_INCOMPLETE', 'Generation receipts are incomplete.')
            value = {'schema_version': 'bounded-study-generation-result-v1', 'manifest_sha256': manifest_sha256,
                     'boot_id': boot_id, 'finished_monotonic_ns': now_ns,
                     'elapsed_ns': now_ns - generation['started_monotonic_ns'], 'after_ordinal': len(events),
                     'previous_event_sha256': events[-1]['sha256'] if events else fingerprint(claim)}
            self._put_meta(con, 'generation_result', value)
            return {'phase': value, 'sha256': fingerprint(value), 'replayed': False}

    def seal_inputs(self, manifest_sha256, review_sha256):
        self._require_worker()
        _hashes = (manifest_sha256, review_sha256)
        _require(all(type(v) is str and len(v) == 64 and all(ch in '0123456789abcdef' for ch in v) for v in _hashes),
                 'INVALID_STUDY', 'Exact input-manifest and review SHA-256 are required.')
        with self._locked(), self._connect() as con:
            claim = self._claimed(con)
            events, operations, counts = self._history(con, claim)
            old = self._meta(con, 'input_review')
            if old is not None:
                _require(old['manifest_sha256'] == manifest_sha256 and old['review_sha256'] == review_sha256,
                         'STUDY_CONFLICT', 'Input review is already bound to different content.')
                return {'phase': old, 'sha256': fingerprint(old), 'replayed': True}
            generated = self._meta(con, 'generation_result')
            _require(generated is not None and generated['manifest_sha256'] == manifest_sha256
                     and generated['elapsed_ns'] < MAX_ELAPSED_NS,
                     'STUDY_TIMEOUT', 'The original generation phase is incomplete or consumed its full time budget.')
            _require(counts['generate'] == claim['limits']['generate']
                     and all(x['status'] == 'completed' for x in operations.values()),
                     'STUDY_INCOMPLETE', 'All fixed generation receipts must complete before input review.')
            value = {'schema_version': 'bounded-study-input-review-v1', 'manifest_sha256': manifest_sha256,
                     'review_sha256': review_sha256, 'after_ordinal': len(events),
                     'previous_event_sha256': events[-1]['sha256'] if events else fingerprint(claim)}
            inserted = self._put_meta(con, 'input_review', value)
            return {'phase': value, 'sha256': fingerprint(value), 'replayed': not inserted}

    def start_primary(self, *, now_ns, boot_id):
        self._require_worker()
        _require(type(now_ns) is int and now_ns >= 0 and type(boot_id) is str and 0 < len(boot_id) <= 128,
                 'INVALID_STUDY', 'Monotonic primary start and boot identity are required.')
        with self._locked(), self._connect() as con:
            claim = self._claimed(con)
            events, operations, _ = self._history(con, claim)
            _require(self._meta(con, 'input_review') is not None, 'STUDY_NOT_REVIEWED', 'Input review is required before primary work.')
            _require(all(x['status'] == 'completed' for x in operations.values()), 'STUDY_UNKNOWN', 'An operation is unfinished or failed.')
            old = self._meta(con, 'primary')
            if old is not None:
                _require(old['input_review_sha256'] == fingerprint(self._meta(con, 'input_review')),
                         'EVIDENCE_CHANGED', 'Primary phase no longer matches input review.')
                _require(old['boot_id'] == boot_id and now_ns >= (events[-1]['event']['monotonic_ns'] if events else old['started_monotonic_ns']),
                         'STUDY_CLOCK_CHANGED', 'Primary cannot resume across boots or a reversed monotonic clock.')
                return {'phase': old, 'sha256': fingerprint(old), 'replayed': True}
            generated = self._meta(con, 'generation_result')
            _require(generated['boot_id'] == boot_id and now_ns >= generated['finished_monotonic_ns'],
                     'STUDY_CLOCK_CHANGED', 'Primary boot or monotonic clock changed.')
            value = {'schema_version': 'bounded-study-primary-v1', 'study_id': self.study_id,
                     'input_review_sha256': fingerprint(self._meta(con, 'input_review')),
                     'boot_id': boot_id, 'started_monotonic_ns': now_ns,
                     'deadline_monotonic_ns': now_ns + MAX_ELAPSED_NS - generated['elapsed_ns'],
                     'after_ordinal': len(events),
                     'previous_event_sha256': events[-1]['sha256'] if events else fingerprint(claim)}
            inserted = self._put_meta(con, 'primary', value)
            return {'phase': value, 'sha256': fingerprint(value), 'replayed': not inserted}

    def finish_primary(self, bundle_sha256, *, now_ns, boot_id):
        self._require_worker()
        _require(type(bundle_sha256) is str and len(bundle_sha256) == 64 and all(c in '0123456789abcdef' for c in bundle_sha256),
                 'INVALID_STUDY', 'Primary bundle SHA-256 required.')
        with self._locked(), self._connect() as con:
            claim = self._claimed(con)
            events, operations, counts = self._history(con, claim)
            old = self._meta(con, 'primary_result')
            if old is not None:
                _require(old['bundle_sha256'] == bundle_sha256, 'STUDY_CONFLICT', 'Primary result is already bound to another bundle.')
                return {'phase': old, 'sha256': fingerprint(old), 'replayed': True}
            _require(self._meta(con, 'halt') is None, 'STUDY_FAILED', 'Study has a recorded terminal failure.')
            primary = self._meta(con, 'primary')
            _require(primary is not None and boot_id == primary['boot_id'] and type(now_ns) is int
                     and max(primary['started_monotonic_ns'], events[-1]['event']['monotonic_ns'] if events else 0)
                         <= now_ns < primary['deadline_monotonic_ns'],
                     'STUDY_TIMEOUT', 'Primary completion is outside its original time budget or boot.')
            _require(self._meta(con, 'primary') is not None and all(x['status'] == 'completed' for x in operations.values())
                     and all(counts[k] == claim['limits'][k] for k in ('generate','warmup','timed','correctness','oracle','bruteforce',
                                                                       'kernel_total','scan_comparisons','exhaustive_subsets')),
                     'STUDY_INCOMPLETE', 'Primary operation receipts are incomplete.')
            value = {'schema_version': 'bounded-study-primary-result-v1', 'bundle_sha256': bundle_sha256,
                     'boot_id': boot_id, 'finished_monotonic_ns': now_ns,
                     'after_ordinal': len(events),
                     'previous_event_sha256': events[-1]['sha256'] if events else fingerprint(claim)}
            inserted = self._put_meta(con, 'primary_result', value)
            return {'phase': value, 'sha256': fingerprint(value), 'replayed': not inserted}

    @staticmethod
    def _clock_halt(con, claim, events, reason, context):
        value = {'schema_version': 'bounded-study-halt-v1', 'reason': reason, 'context': context,
                 'after_ordinal': len(events),
                 'previous_event_sha256': events[-1]['sha256'] if events else fingerprint(claim)}
        BoundedStudyLedger._put_meta(con, 'halt', value)

    def perform(self, op_id, operation, spec, callback, *, boot_id=None, clock=None):
        self._require_worker()
        identifier(op_id, 'op_id')
        _require(operation in OPERATIONS and type(spec) is dict and callable(callback), 'INVALID_STUDY', 'Use a fixed bounded operation.')
        _require(len(canonical(spec).encode()) <= 65536, 'INVALID_STUDY', 'Operation specification is too large.')
        spec = json.loads(canonical(spec))
        charge, subsets = _charge(operation, spec), _subsets(operation, spec)
        clock = time.monotonic_ns if clock is None else clock
        with self._locked():
            pre_error = None
            with self._connect() as con:
                claim = self._claimed(con)
                events, operations, counts = self._history(con, claim)
                old = operations.get(op_id)
                if old is not None:
                    _require(old['reserved']['operation'] == operation and old['reserved']['spec'] == spec,
                             'STUDY_CONFLICT', 'The original operation ID is already bound to different content.')
                    _require(old['status'] == 'completed', 'STUDY_UNKNOWN' if old['status'] == 'unknown' else 'STUDY_FAILED',
                             'The original operation is unknown or failed; never repeat it.')
                    return {'replayed': True, 'result': copy.deepcopy(old['result']), 'reservation_sha256': old['reservation_sha256']}
                _require(self._meta(con, 'halt') is None, 'STUDY_FAILED', 'Study has a recorded terminal failure.')
                _require(all(item['status'] == 'completed' for item in operations.values()), 'STUDY_UNKNOWN', 'An earlier operation is unfinished or failed; stop.')
                primary = self._meta(con, 'primary')
                _require((operation == 'generate' and primary is None and self._meta(con, 'input_review') is None
                          and self._meta(con, 'generation_result') is None)
                         or (operation in KERNEL_OPERATIONS | {'oracle','bruteforce'} and primary is not None and self._meta(con, 'primary_result') is None)
                         or (operation == 'audit' and self._meta(con, 'primary_result') is not None),
                         'STUDY_PHASE', 'Operation is outside its reviewed phase.')
                timing = self._meta(con, 'generation') if operation == 'generate' else primary
                expected_boot = timing['boot_id'] if timing is not None else None
                floor = max(timing['started_monotonic_ns'] if timing is not None else 0,
                            events[-1]['event']['monotonic_ns'] if events else 0)
                if operation == 'audit':
                    floor = max(floor, self._meta(con, 'primary_result')['finished_monotonic_ns'])
                try:
                    now = clock()
                    valid_clock = (timing is not None and type(boot_id) is str and boot_id == expected_boot
                                   and type(now) is int and now >= floor
                                   and (operation == 'audit' or now < timing['deadline_monotonic_ns']))
                except Exception as error:
                    now, valid_clock = repr(error)[:200], False
                if not valid_clock:
                    self._clock_halt(con, claim, events, 'Clock or boot identity invalid before reservation',
                                     {'op_id':op_id, 'observed_clock':repr(now)[:200], 'boot_id':str(boot_id)[:128]})
                    pre_error = ('STUDY_CLOCK_CHANGED' if type(now) is not int or now < floor or boot_id != expected_boot
                                 else 'STUDY_TIMEOUT')
                else:
                    _require(counts[operation] < claim['limits'][operation], 'STUDY_BUDGET', 'Operation allowance is exhausted.')
                    _require(operation not in KERNEL_OPERATIONS or (counts['kernel_total'] < claim['limits']['kernel_total']
                             and counts['scan_comparisons'] + charge <= claim['limits']['scan_comparisons']),
                             'STUDY_BUDGET', 'Kernel or scan-comparison allowance is exhausted.')
                    _require(counts['exhaustive_subsets'] + subsets <= claim['limits']['exhaustive_subsets'],
                             'STUDY_BUDGET', 'Exhaustive subset allowance is exhausted.')
                    reservation = self._append(con, claim, events, op_id, operation, spec, 'reserved',
                                               boot_id=boot_id, monotonic_ns=now)
            if pre_error:
                raise ResearchError(pre_error, 'Original phase clock or boot identity changed; study stopped.')
            observed = now
            returned = False
            result = None
            try:
                observed = clock()
                if (type(observed) is not int or observed < now
                        or (operation != 'audit' and observed >= timing['deadline_monotonic_ns'])):
                    raise ResearchError('STUDY_CLOCK_CHANGED', 'Clock changed after reservation before callback.')
                result = callback()
                returned = True
                canonical(result)
                previous = observed
                observed = clock()
                if (type(observed) is not int or observed < previous
                        or (operation != 'audit' and observed >= timing['deadline_monotonic_ns'])):
                    raise ResearchError('STUDY_CLOCK_CHANGED', 'Clock changed or deadline expired after callback.')
            except Exception as error:
                if isinstance(error, ResearchError) and error.code == 'STUDY_CLOCK_CHANGED':
                    with self._connect() as con:
                        actual = self._claimed(con)
                        current, operations, _ = self._history(con, actual)
                        _require(actual == claim and operations[op_id]['status'] == 'unknown', 'EVIDENCE_CHANGED', 'Reservation changed during operation.')
                        context = {'op_id':op_id, 'observed_clock':repr(observed)[:200], 'callback_returned':returned}
                        if returned:
                            context['returned_result'] = result
                        self._clock_halt(con, claim, current, str(error), context)
                    raise
                try:
                    error_clock = clock()
                except Exception:
                    error_clock = None
                with self._connect() as con:
                    actual = self._claimed(con)
                    current, operations, _ = self._history(con, actual)
                    _require(actual == claim and operations[op_id]['status'] == 'unknown', 'EVIDENCE_CHANGED', 'Reservation changed during operation.')
                    failure = {'error_type': type(error).__name__[:200], 'message': str(error)[:4000]}
                    if returned:
                        try:
                            canonical(result)
                            failure['returned_result'] = result
                        except (TypeError, ValueError, OverflowError, RecursionError):
                            failure['returned_result_repr'] = repr(result)
                    self._append(con, claim, current, op_id, operation, spec, 'failed', reservation, failure,
                                 boot_id=boot_id, monotonic_ns=error_clock if type(error_clock) is int else None)
                raise ResearchError('STUDY_FAILED', 'Operation failed after reservation; preserve its receipt and stop.') from error
            with self._connect() as con:
                actual = self._claimed(con)
                current, operations, _ = self._history(con, actual)
                _require(actual == claim and operations[op_id]['status'] == 'unknown', 'EVIDENCE_CHANGED', 'Reservation changed during operation.')
                self._append(con, claim, current, op_id, operation, spec, 'completed', reservation, result,
                             boot_id=boot_id, monotonic_ns=observed)
            return {'replayed': False, 'result': result, 'reservation_sha256': reservation}

    def halt(self, *, reason, context):
        """Persist a non-dispatch terminal verification/timeout failure."""
        self._require_worker()
        _require(type(reason) is str and 0 < len(reason) <= 1000 and type(context) is dict,
                 'INVALID_STUDY', 'A bounded terminal reason and context are required.')
        with self._locked(), self._connect() as con:
            claim = self._claimed(con)
            events, _, _ = self._history(con, claim)
            value = {'schema_version': 'bounded-study-halt-v1', 'reason': reason, 'context': context,
                     'after_ordinal': len(events),
                     'previous_event_sha256': events[-1]['sha256'] if events else fingerprint(claim)}
            self._put_meta(con, 'halt', value)
            return value

    def snapshot(self):
        with self._locked(), self._connect(readonly=True) as con:
            claim = self._claimed(con)
            events, operations, counts = self._history(con, claim, refresh=True)
            usage = {kind: {'reserved': sum(item['reserved']['operation'] == kind for item in operations.values()),
                            'completed': sum(item['reserved']['operation'] == kind and item['status'] == 'completed' for item in operations.values()),
                            'failed': sum(item['reserved']['operation'] == kind and item['status'] == 'failed' for item in operations.values()),
                            'unknown': sum(item['reserved']['operation'] == kind and item['status'] == 'unknown' for item in operations.values())}
                     for kind in OPERATIONS}
            return {'claim': claim, 'claim_sha256': fingerprint(claim), 'events': copy.deepcopy(events),
                    'phases': {key: self._meta(con, key) for key in ('generation','generation_result','input_review','primary','primary_result')},
                    'counts': counts, 'usage': usage, 'halted': self._meta(con, 'halt'),
                    'unknown': [key for key,item in operations.items() if item['status'] == 'unknown'],
                    'failed': [key for key,item in operations.items() if item['status'] == 'failed']}
