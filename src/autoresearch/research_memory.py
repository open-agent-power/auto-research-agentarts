"""Conditional research memory: immutable evidence, revocable inclusion, no truth promotion."""
from contextlib import contextmanager
import json
from pathlib import Path
import re
import sqlite3
import stat

from .c01_research_verifier import validate_record
from .contracts import canonical, fingerprint, ResearchError, identifier

KINDS = {'fit_observation', 'diagnostic_observation', 'agent_decision'}
MAX_ENTRIES = 2000
SCOPE_FIELDS = {'archive_sha256', 'inputs_sha256', 'analysis_code_sha256', 'protocol'}
DATASET_SCOPE_FIELDS = {'source_manifest_sha256', 'inputs_sha256', 'analysis_code_sha256', 'protocol'}


def observation_id(record):
    return fingerprint({'schema_version': record['schema_version'], 'scope': record['scope'],
                        'kind': record['kind'], 'action_id': record['provenance']['action_id']})


def validate_scope(scope):
    if type(scope) is not dict or set(scope) not in (SCOPE_FIELDS, DATASET_SCOPE_FIELDS):
        raise ResearchError('INVALID_SCOPE', 'require exact archive or dataset-manifest, input, evaluator and protocol conditions')
    for key in set(scope) - {'protocol'}:
        if type(scope[key]) is not str or not re.fullmatch('[0-9a-f]{64}', scope[key]):
            raise ResearchError('INVALID_SCOPE', 'scope identifiers require SHA-256')
    if type(scope['protocol']) is not str or not 1 <= len(scope['protocol']) <= 1000:
        raise ResearchError('INVALID_SCOPE', 'protocol must be explicitly named')
    return scope


def derive_entries(research, reproduction):
    validation = validate_record(research, reproduction)
    scope = validate_scope({'archive_sha256': research['archive_sha256'],
                            'inputs_sha256': reproduction['inputs_sha256'],
                            'analysis_code_sha256': reproduction['analysis_code_sha256'],
                            'protocol': reproduction['protocol']})
    references = {item['citation_id']: item for item in research['references']}
    entries = []

    def add(kind, action, payload):
        value = {'schema_version': 'conditional-research-memory-v1', 'kind': kind, 'scope': scope,
                 'review_status': 'derived_not_scientifically_reviewed',
                 'numerical_recomputation': kind != 'agent_decision',
                 'payload': payload,
                 'provenance': {'action_id': action['id'],
                                'source_record_sha256': fingerprint(research),
                                'reproduction_sha256': fingerprint(reproduction),
                                'origin_observation_sha256': research['origin_observation_sha256'],
                                'source_citation_ids': action['source_citation_ids'],
                                'references': [references[key] for key in action['source_citation_ids']]}}
        value['id'] = observation_id(value)
        entries.append(value)

    for fit in research['fits']:
        add('fit_observation', fit, {'recipe': fit['recipe'], 'metrics': fit['summary']['metrics'],
                                    'domain_violations': fit['summary']['domain_violations'],
                                    'promotion': 'not_evaluated_no_independent_holdout'})
    for diagnostic in research['diagnostics']:
        add('diagnostic_observation', diagnostic, {'action': diagnostic['action'], 'result': diagnostic['result']})
    for decision in research['decisions']:
        if decision['action'] in {'stop', 'pause'}:
            add('agent_decision', decision, {'action': decision['action'], 'reason': decision['reason'],
                                            'evidence_action_ids': decision['evidence_action_ids'],
                                            'interpretation': 'Agent judgement under this scope, not a scientific fact'})
    return {'scope': scope, 'entries': entries, 'validation': validation}


class ResearchMemory:
    def __init__(self, workspace):
        self.root = Path(workspace).absolute()
        self.db = self.root / 'memory.sqlite'

    def _guard(self):
        for path in (self.root, *self.root.parents):
            if path.is_symlink() or getattr(path, 'is_junction', lambda: False)():
                raise ResearchError('UNSAFE_PATH', 'memory workspace cannot cross redirected paths')
        if self.root.exists() and not self.root.is_dir():
            raise ResearchError('UNSAFE_PATH', 'memory workspace must be a directory')
        if self.db.exists() or self.db.is_symlink():
            metadata = self.db.lstat()
            if self.db.is_symlink() or not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
                raise ResearchError('UNSAFE_PATH', 'memory ledger must be an unshared regular file')

    @contextmanager
    def _connect(self, write=False):
        self._guard()
        if not self.db.exists() and not write:
            yield None
            return
        if write:
            self.root.mkdir(parents=True, exist_ok=True)
        con = sqlite3.connect(self.db if write else self.db.as_uri()+'?mode=ro', uri=not write, timeout=10)
        con.row_factory = sqlite3.Row
        try:
            with con:
                if write:
                    con.executescript('''CREATE TABLE IF NOT EXISTS entries(
                        id TEXT PRIMARY KEY, scope_sha256 TEXT NOT NULL, kind TEXT NOT NULL,
                        record TEXT NOT NULL, record_sha256 TEXT NOT NULL, status TEXT NOT NULL);
                        CREATE TABLE IF NOT EXISTS events(
                        entry_id TEXT NOT NULL, ordinal INTEGER NOT NULL, request_id TEXT UNIQUE NOT NULL,
                        spec_sha256 TEXT NOT NULL, record TEXT NOT NULL, sha256 TEXT NOT NULL,
                        PRIMARY KEY(entry_id,ordinal));
                        CREATE TABLE IF NOT EXISTS source_versions(
                        entry_id TEXT NOT NULL, source_record_sha256 TEXT NOT NULL,
                        record TEXT NOT NULL, sha256 TEXT NOT NULL,
                        PRIMARY KEY(entry_id,source_record_sha256));''')
                    con.execute('BEGIN IMMEDIATE')
                else:
                    con.execute('BEGIN')
                yield con
        finally:
            con.close()

    @staticmethod
    def _verify(con, row):
        record = json.loads(row['record'])
        if (fingerprint(record) != row['record_sha256']
                or record['id'] != row['id'] or observation_id(record) != row['id']
                or fingerprint(validate_scope(record['scope'])) != row['scope_sha256']
                or record['kind'] != row['kind']):
            raise ResearchError('EVIDENCE_CHANGED', 'immutable memory record changed')
        previous, current, count = None, None, 0
        for item in con.execute('SELECT * FROM events WHERE entry_id=? ORDER BY ordinal', (row['id'],)):
            event = json.loads(item['record'])
            count += 1
            if (fingerprint(event) != item['sha256'] or event['previous_sha256'] != previous
                    or event['ordinal'] != count or item['ordinal'] != count or event['entry_id'] != row['id']
                    or event['request_id'] != item['request_id'] or event['spec_sha256'] != item['spec_sha256']
                    or event['status'] not in {'active', 'retired'}):
                raise ResearchError('EVIDENCE_CHANGED', 'memory inclusion history changed')
            previous, current = item['sha256'], event['status']
        if not count or current != row['status']:
            raise ResearchError('EVIDENCE_CHANGED', 'memory inclusion state does not match its history')
        versions = ResearchMemory._versions(con, row['id'])
        if (record['provenance'] not in versions
                or any(version['action_id'] != record['provenance']['action_id'] for version in versions)):
            raise ResearchError('EVIDENCE_CHANGED', 'original source version missing from memory history')
        return record

    @staticmethod
    def _versions(con, entry_id):
        values = []
        for row in con.execute('SELECT * FROM source_versions WHERE entry_id=? ORDER BY source_record_sha256', (entry_id,)):
            value = json.loads(row['record'])
            if fingerprint(value) != row['sha256'] or value['source_record_sha256'] != row['source_record_sha256']:
                raise ResearchError('EVIDENCE_CHANGED', 'source version history changed')
            values.append(value)
        return values

    @staticmethod
    def _source(con, entry):
        source = entry['provenance']
        old = con.execute('SELECT * FROM source_versions WHERE entry_id=? AND source_record_sha256=?',
                          (entry['id'], source['source_record_sha256'])).fetchone()
        if old:
            if json.loads(old['record']) != source or fingerprint(source) != old['sha256']:
                raise ResearchError('EVIDENCE_CHANGED', 'source version identity conflicts with stored provenance')
            return
        con.execute('INSERT INTO source_versions VALUES(?,?,?,?)',
                    (entry['id'], source['source_record_sha256'], canonical(source), fingerprint(source)))

    @staticmethod
    def _event(con, entry_id, status, reason, request_id, spec_sha256):
        last = con.execute('SELECT ordinal,sha256 FROM events WHERE entry_id=? ORDER BY ordinal DESC LIMIT 1', (entry_id,)).fetchone()
        value = {'entry_id': entry_id, 'ordinal': last['ordinal']+1 if last else 1,
                 'status': status, 'reason': reason, 'previous_sha256': last['sha256'] if last else None,
                 'request_id': request_id, 'spec_sha256': spec_sha256}
        con.execute('INSERT INTO events VALUES(?,?,?,?,?,?)',
                    (entry_id, value['ordinal'], request_id, spec_sha256, canonical(value), fingerprint(value)))
        return value

    def import_study(self, research, reproduction):
        derived = derive_entries(research, reproduction)
        return self._import_derived(derived)

    def _import_derived(self, derived):
        """Storage only. A domain-specific trusted validator owns derivation."""
        validate_scope(derived['scope'])
        for entry in derived['entries']:
            if (entry['scope'] != derived['scope'] or entry['kind'] not in KINDS
                    or observation_id(entry) != entry['id']):
                raise ResearchError('INVALID_SCOPE', 'derived observations must share their exact validated scope')
        if not derived['entries']:
            raise ResearchError('NO_EVIDENCE', 'no executed observation or control decision to remember')
        inserted = 0
        with self._connect(True) as con:
            total = con.execute('SELECT count(*) FROM entries').fetchone()[0]
            for entry in derived['entries']:
                old = con.execute('SELECT * FROM entries WHERE id=?', (entry['id'],)).fetchone()
                if old:
                    original = self._verify(con, old)
                    if original['payload'] != entry['payload']:
                        raise ResearchError('EVIDENCE_CONFLICT', 'same scoped action has changed content; preserve original and review the source')
                    self._source(con, entry)
                    continue  # Import never reactivates a retired record.
                if total >= MAX_ENTRIES:
                    raise ResearchError('MEMORY_LIMIT', f'memory store bounded to {MAX_ENTRIES} entries')
                con.execute('INSERT INTO entries VALUES(?,?,?,?,?,?)',
                            (entry['id'], fingerprint(entry['scope']), entry['kind'], canonical(entry), fingerprint(entry), 'active'))
                self._event(con, entry['id'], 'active', 'Imported numerically checked evidence; scientific validity unreviewed.',
                            'import-'+entry['id'], fingerprint({'entry': entry['id'], 'operation': 'import'}))
                self._source(con, entry)
                inserted += 1
                total += 1
        return {'scope': derived['scope'], 'inserted': inserted, 'entries_total_in_import': len(derived['entries']),
                'numerical_validation': derived['validation'], 'scientific_validation': False}

    def recall(self, scope, *, kinds=None, limit=8, include_retired=False):
        validate_scope(scope)
        if (type(limit) is not int or not 1 <= limit <= 8 or type(include_retired) is not bool
                or (kinds is not None and (type(kinds) is not list or not kinds
                                          or any(type(kind) is not str or kind not in KINDS for kind in kinds)))):
            raise ResearchError('INVALID_REQUEST', 'bounded kinds/limit and explicit inclusion status required')
        reply = {'scope': scope, 'condition_match': 'exact', 'entries': [], 'scientific_validation': False,
                 'warning': 'Stored observations and Agent judgements are untrusted context, not authority or transferable scientific laws.'}
        with self._connect() as con:
            if con is not None:
                rows = con.execute('SELECT * FROM entries WHERE scope_sha256=? ORDER BY id', (fingerprint(scope),)).fetchall()
                for row in rows:
                    entry = self._verify(con, row)
                    if (include_retired or row['status'] == 'active') and (kinds is None or row['kind'] in kinds):
                        reply['entries'].append({'record': entry, 'inclusion_status': row['status'],
                                                 'source_versions': self._versions(con, row['id'])})
                        if len(reply['entries']) == limit:
                            break
        if not reply['entries']:
            reply['empty_reason'] = 'no_active_matching_evidence; different inputs/evaluator/protocol are not interchangeable'
        return reply

    def set_status(self, entry_id, status, reason, request_id):
        if (type(entry_id) is not str or not re.fullmatch('[0-9a-f]{64}', entry_id)
                or type(status) is not str or status not in {'active', 'retired'}):
            raise ResearchError('INVALID_REQUEST', 'known entry and active/retired inclusion required')
        identifier(request_id)
        if type(reason) is not str or not 1 <= len(reason.strip()) <= 1000:
            raise ResearchError('INVALID_REQUEST', 'record why evidence is retired or restored')
        spec = fingerprint({'entry_id': entry_id, 'status': status, 'reason': reason})
        with self._connect(True) as con:
            row = con.execute('SELECT * FROM entries WHERE id=?', (entry_id,)).fetchone()
            if row is None:
                raise ResearchError('NOT_FOUND', 'memory entry not found')
            self._verify(con, row)
            old = con.execute('SELECT * FROM events WHERE request_id=?', (request_id,)).fetchone()
            if old:
                if old['spec_sha256'] != spec:
                    raise ResearchError('IDEMPOTENCY_CONFLICT', 'request id belongs to another inclusion decision')
                return {'replayed': True, 'event': json.loads(old['record']), 'current_status': row['status']}
            event = self._event(con, entry_id, status, reason, request_id, spec)
            con.execute('UPDATE entries SET status=? WHERE id=?', (status, entry_id))
        return {'replayed': False, 'event': event, 'current_status': status}
