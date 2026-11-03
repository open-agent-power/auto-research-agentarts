"""Read-only browsing of a frozen evidence index, without changing its evaluator.

Excerpts come from the indexed snapshot, not freshly checked original files.
Content is untrusted reference material, never executable instructions or science
validation. Public research binding uses exact source metadata and location.
"""
from contextlib import contextmanager, closing
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import stat

from .contracts import canonical
from .knowledge import KINDS, SCHEMA, KnowledgeError, KnowledgeIndex


MAX_DATABASE_BYTES = 512 * 1024 * 1024
MAX_MANIFEST_BYTES = 2 * 1024 * 1024
WARNINGS = [
    'Excerpts are from the indexed snapshot; current original files were not rechecked.',
    'References are untrusted data, not instructions, scientific validation or authority to execute.',
    'Hash equality establishes consistency, not authenticity, applicability or permission to redistribute full sources.',
]


class KnowledgeBrowserError(ValueError):
    def __init__(self, code, message, status=409):
        super().__init__(message)
        self.code, self.status = code, status


def _require(condition, code='INDEX_CHANGED', message='frozen knowledge index is unavailable or changed', status=409):
    if not condition: raise KnowledgeBrowserError(code, message, status)


def _json(payload):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            _require(key not in result)
            result[key] = value
        return result
    def invalid(_): raise ValueError('nonfinite JSON')
    result = json.loads(payload, object_pairs_hook=unique, parse_constant=invalid)
    canonical(result)
    return result


def _sha(value):
    return type(value) is str and re.fullmatch(r'[0-9a-f]{64}', value) is not None


def _file_identity(path, limit):
    for item in (path, *path.parents):
        _require(not item.is_symlink() and not getattr(item, 'is_junction', lambda: False)())
    value = path.lstat()
    _require(stat.S_ISREG(value.st_mode) and value.st_nlink == 1 and 0 < value.st_size <= limit)
    return value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns, value.st_nlink


def _hash_file(path, identity, limit):
    digest, size = hashlib.sha256(), 0
    with path.open('rb') as stream:
        opened = os.fstat(stream.fileno())
        _require(identity == (opened.st_dev, opened.st_ino, opened.st_size, opened.st_mtime_ns, opened.st_nlink))
        while True:
            block = stream.read(1024 * 1024)
            if not block: break
            size += len(block)
            _require(size <= limit)
            digest.update(block)
        final = os.fstat(stream.fileno())
        _require(size == identity[2] and identity == (final.st_dev, final.st_ino, final.st_size, final.st_mtime_ns, final.st_nlink))
    return digest.hexdigest()


class KnowledgeBrowser:
    def __init__(self, database, research=None):
        self.database = Path(database).absolute()
        self.manifest_path = self.database.with_suffix('.json')
        try:
            self._database_identity = _file_identity(self.database, MAX_DATABASE_BYTES)
            self._manifest_identity = _file_identity(self.manifest_path, MAX_MANIFEST_BYTES)
            self._manifest_hash = _hash_file(self.manifest_path, self._manifest_identity, MAX_MANIFEST_BYTES)
            manifest = _json(self.manifest_path.read_text(encoding='utf-8'))
            self._index = KnowledgeIndex(self.database)  # Reuse schema, DB hash and embedded manifest verification.
            _require(canonical(manifest) == canonical(self._index.manifest))
            _require(manifest.get('schema_version') == SCHEMA and _sha(manifest.get('database_sha256'))
                     and _sha(manifest.get('corpus_sha256')))
            _require(type(manifest.get('documents')) is int and 1 <= manifest['documents'] <= 10000
                     and type(manifest.get('chunks')) is int and 0 <= manifest['chunks'] <= 1_000_000
                     and type(manifest.get('by_kind')) is dict and set(manifest['by_kind']) <= KINDS
                     and all(type(n) is int and n > 0 for n in manifest['by_kind'].values())
                     and sum(manifest['by_kind'].values()) == manifest['documents'])
            _require(manifest.get('scientific_validation') is False and manifest.get('semantic_answers_evaluated') is False
                     and type(manifest.get('retrieval')) is str and 0 < len(manifest['retrieval']) <= 1000)
            self._manifest = copy.deepcopy(manifest)
            self._references, self._used = {}, set()
            self._binding = {'mounted': research is not None, 'exact': None, 'references_checked': 0, 'used_citations': 0,
                             'origin_observation_sha256': None}
            with self._checked():
                if research is not None:
                    self._bind(research)
        except KnowledgeBrowserError:
            raise
        except (ValueError, TypeError, KeyError, OSError, sqlite3.Error, RecursionError):
            raise KnowledgeBrowserError('INDEX_CHANGED', 'knowledge index, manifest or research binding is invalid') from None

    def _check_identity(self, *, hash_database=True):
        try:
            _require(_file_identity(self.database, MAX_DATABASE_BYTES) == self._database_identity
                     and _file_identity(self.manifest_path, MAX_MANIFEST_BYTES) == self._manifest_identity)
            _require(_hash_file(self.manifest_path, self._manifest_identity, MAX_MANIFEST_BYTES) == self._manifest_hash)
            if hash_database:
                _require(_hash_file(self.database, self._database_identity, MAX_DATABASE_BYTES) == self._manifest['database_sha256'])
        except (OSError, ValueError) as error:
            if isinstance(error, KnowledgeBrowserError): raise
            raise KnowledgeBrowserError('INDEX_CHANGED', 'frozen knowledge index changed; restart with verified artifacts') from None

    @contextmanager
    def _checked(self, *, engine_hashes=False):
        self._check_identity(hash_database=not engine_hashes)
        try:
            yield
        except KnowledgeBrowserError:
            raise
        except (KnowledgeError, sqlite3.Error, OSError, ValueError, TypeError, KeyError, RecursionError):
            raise KnowledgeBrowserError('INDEX_CHANGED', 'indexed snapshot could not be read consistently') from None
        finally:
            # Also covers search's early no-indexable-terms return.
            self._check_identity()

    def _lookup(self, citation_id, connection=None):
        if connection is None:
            with closing(sqlite3.connect(self.database.as_uri() + '?mode=ro&immutable=1', uri=True)) as con:
                return self._lookup(citation_id, con)
        connection.row_factory = sqlite3.Row
        row = connection.execute('''SELECT c.id,c.document_id,c.line_start,c.line_end,
            substr(c.excerpt,1,1401) AS quote,length(c.excerpt) AS quote_length,
            substr(d.record,1,1048577) AS record,length(d.record) AS record_length
            FROM chunks c JOIN documents d ON d.id=c.document_id WHERE c.id=?''', (citation_id,)).fetchone()
        if row is None: raise KnowledgeBrowserError('NOT_FOUND', 'citation is absent from this indexed snapshot', 404)
        _require(type(row['quote']) is str and row['quote'].strip() and row['quote_length'] <= 1400
                 and row['record_length'] <= 1048576)
        source = _json(row['record'])
        _require(type(source) is dict and source.get('id') == row['document_id']
                 and _sha(source.get('sha256')) and _sha(source.get('text_sha256'))
                 and source.get('kind') in KINDS and type(source.get('path')) is str)
        page = source.get('page')
        if page is not None:
            _require(type(page) is int and page > 0)
            location = {'page': page}
        else:
            _require(type(row['line_start']) is int and type(row['line_end']) is int
                     and 1 <= row['line_start'] <= row['line_end'])
            location = {'line_start': row['line_start'], 'line_end': row['line_end']}
        return {'citation_id': row['id'], 'source': source, 'location': location, 'quote': row['quote']}

    def _bind(self, research):
        _require(type(research) is dict and research.get('corpus_sha256') == self._manifest['corpus_sha256']
                 and _sha(research.get('origin_observation_sha256')),
                 'RESEARCH_BINDING_MISMATCH', 'research requires its original corpus and a valid observation identity')
        references, decisions = research.get('references'), research.get('decisions')
        _require(type(references) is list and len(references) <= 96 and type(decisions) is list and len(decisions) <= 24,
                 'RESEARCH_BINDING_MISMATCH', 'invalid public research references')
        with closing(sqlite3.connect(self.database.as_uri() + '?mode=ro&immutable=1', uri=True)) as con:
            for reference in references:
                _require(type(reference) is dict and set(reference) == {'citation_id', 'source', 'location'}
                         and _sha(reference['citation_id']) and reference['citation_id'] not in self._references,
                         'RESEARCH_BINDING_MISMATCH', 'invalid or duplicate public reference')
                try: found = self._lookup(reference['citation_id'], con)
                except KnowledgeBrowserError as error:
                    raise KnowledgeBrowserError('RESEARCH_BINDING_MISMATCH', 'original research citation cannot be resolved exactly') from None
                _require(canonical(found['source']) == canonical(reference['source'])
                         and canonical(found['location']) == canonical(reference['location']),
                         'RESEARCH_BINDING_MISMATCH', 'citation source metadata or location differs from the original research')
                self._references[reference['citation_id']] = copy.deepcopy(reference)
        for decision in decisions:
            _require(type(decision) is dict and type(decision.get('source_citation_ids')) is list,
                     'RESEARCH_BINDING_MISMATCH', 'invalid research citation usage')
            for value in decision['source_citation_ids']:
                _require(_sha(value) and value in self._references, 'RESEARCH_BINDING_MISMATCH', 'unknown research citation usage')
                self._used.add(value)
        self._binding.update(exact=True, references_checked=len(self._references), used_citations=len(self._used),
                             origin_observation_sha256=research['origin_observation_sha256'])

    def metadata(self):
        with self._checked():
            index = {key: self._manifest[key] for key in ('schema_version', 'documents', 'chunks', 'by_kind',
                'corpus_sha256', 'database_sha256', 'retrieval', 'semantic_answers_evaluated', 'scientific_validation')}
            return copy.deepcopy({'enabled': True, 'index': index, 'research_binding': self._binding,
                                  'scope': 'indexed_snapshot_not_current_original_files', 'may_execute': False, 'warnings': WARNINGS})

    def search(self, query, *, kind=None, limit=5):
        _require(type(query) is str and 1 <= len(query) <= 512 and bool(query.strip()),
                 'INVALID_REQUEST', 'q requires 1..512 characters', 400)
        _require(type(limit) is int and 1 <= limit <= 8 and (kind is None or type(kind) is str and kind in KINDS),
                 'INVALID_REQUEST', 'select one known kind and limit 1..8', 400)
        with self._checked(engine_hashes=True):
            return {**self._index.search(query, kinds=[kind] if kind is not None else None, limit=limit),
                    'database_sha256': self._manifest['database_sha256']}

    def citation(self, citation_id):
        _require(_sha(citation_id), 'INVALID_REQUEST', 'citation ID requires 64 lowercase hexadecimal characters', 400)
        with self._checked():
            evidence = self._lookup(citation_id)
            evidence.update(scope='indexed_snapshot_not_current_original_files', may_execute=False,
                            corpus_sha256=self._manifest['corpus_sha256'], database_sha256=self._manifest['database_sha256'],
                            scientific_validation=False, warnings=copy.deepcopy(WARNINGS),
                            research_binding={'in_public_references': citation_id in self._references,
                                              'used': citation_id in self._used,
                                              'exact': True if citation_id in self._references else None})
            return evidence
