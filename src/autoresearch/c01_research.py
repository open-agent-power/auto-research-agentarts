"""Evidence-bound C01 tools for an external research Agent, with durable feedback.

This module performs no model/network calls. The caller chooses each next action.
Only verified public inputs and the existing fixed C01 evaluator are executable.
"""
import copy
import csv
from contextlib import contextmanager
import hashlib
import io
import json
import math
import re
from pathlib import Path
import sqlite3
import stat
import time
import uuid

from . import c01, c01_loop, knowledge
from .contracts import ResearchError, canonical, fingerprint, identifier
from .knowledge import KnowledgeIndex, KnowledgeError, SourceSelectionError

ACTION_FIELDS = {'request_id', 'observation_sha256', 'action', 'reason',
                 'source_citation_ids', 'evidence_action_ids', 'parameters'}
ACTIONS = {'search', 'read_source', 'inspect_dataset', 'review_evidence', 'propose_control', 'fit', 'residuals', 'correlation', 'pause', 'stop'}
EXPERIMENTS = {'fit', 'residuals', 'correlation'}
REVIEW_FIELDS = set(c01.FEATURES) | {item['id'] for item in c01.TARGETS} | {'sample_mapping', 'cell_protocol', 'control_rationale'}


def control_review_state(observation):
    """Locate an exact current proposal/review, without endorsing either claim."""
    actions = observation['actions']
    experiment = next((item for item in reversed(actions) if item['action'] in EXPERIMENTS), None)
    proposal = next((item for item in reversed(actions) if item['action'] == 'propose_control'), None)
    current = proposal is not None and (experiment is None or proposal['ordinal'] > experiment['ordinal'])
    review = None if proposal is None else next((item for item in reversed(actions)
        if item['action'] == 'review_evidence' and item['parameters']['field'] == 'control_rationale'
        and proposal['id'] in item['evidence_action_ids']), None)
    return {'proposal_action_id': None if proposal is None else proposal['id'],
            'proposed_decision': None if proposal is None else proposal['parameters']['decision'],
            'proposal_reason': None if proposal is None else proposal['reason'],
            'current': current, 'reviewed': current and review is not None,
            'review_action_id': None if review is None else review['id'],
            'latest_experiment_id': None if experiment is None else experiment['id']}


def code_identity():
    return hashlib.sha256(b''.join(Path(module.__file__).read_bytes()
                                   for module in (c01, c01_loop, knowledge)) + Path(__file__).read_bytes()).hexdigest()


def _csv_bytes(rows):
    stream = io.StringIO(newline='')
    writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode('utf-8')


class C01Research:
    def __init__(self, workspace):
        self.root = Path(workspace).absolute()
        self.db = self.root / 'research.sqlite'

    def _guard(self):
        for path in (self.root, *self.root.parents):
            if path.is_symlink() or getattr(path, 'is_junction', lambda: False)():
                raise ResearchError('UNSAFE_PATH', 'research workspace must not cross redirected paths')
        if self.root.exists() and not self.root.is_dir():
            raise ResearchError('UNSAFE_PATH', 'research workspace must be a directory')
        if self.db.exists():
            metadata = self.db.lstat()
            if self.db.is_symlink() or not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
                raise ResearchError('UNSAFE_PATH', 'research ledger must be an unshared regular file')

    @contextmanager
    def _connect(self, write=False):
        self._guard()
        if not self.db.is_file():
            raise ResearchError('NOT_INITIALIZED', 'create a research study first')
        con = sqlite3.connect(self.db if write else self.db.as_uri() + '?mode=ro', uri=not write, timeout=10)
        con.row_factory = sqlite3.Row
        try:
            with con:
                if not write:
                    con.execute('BEGIN')
                yield con
        finally:
            con.close()

    def create(self, archive, index, goal, *, max_actions=12, max_fits=4):
        if type(goal) is not str or not 1 <= len(goal.strip()) <= 2000:
            raise ResearchError('INVALID_REQUEST', 'goal requires 1..2000 characters')
        if type(max_actions) is not int or not 3 <= max_actions <= 24 or type(max_fits) is not int or not 1 <= max_fits <= 6:
            raise ResearchError('INVALID_REQUEST', 'bounded action and fit limits required')
        self._guard()
        if self.root.exists() and any(self.root.iterdir()):
            raise ResearchError('ALREADY_EXISTS', 'create requires a new or empty study directory')
        bundle = c01.load_archive(archive)
        library = KnowledgeIndex(index)
        inputs = {key: bundle[key] for key in ('samples', 'source', 'audit', 'provenance', 'bio_mapping')}
        config = {'schema_version': 'c01-evidence-study-v1', 'goal': goal,
                  'max_actions': max_actions, 'max_fits': max_fits,
                  'index_path': str(Path(index).resolve()), 'index_sha256': library.manifest['database_sha256'],
                  'corpus_sha256': library.manifest['corpus_sha256'], 'analysis_code_sha256': code_identity(),
                  'inputs_sha256': fingerprint(inputs), 'inputs': inputs,
                  'decision_origin': 'external_agent_submission_not_authenticated_model_identity'}
        self.root.mkdir(parents=True, exist_ok=True)
        # Exclusive creation prevents replacing a concurrent study.
        with self.db.open('xb'):
            pass
        with self._connect(True) as con:
            con.executescript('''CREATE TABLE meta(config TEXT NOT NULL, sha256 TEXT NOT NULL, status TEXT NOT NULL);
                CREATE TABLE actions(ordinal INTEGER PRIMARY KEY, id TEXT UNIQUE NOT NULL,
                request_id TEXT UNIQUE NOT NULL, request_sha256 TEXT NOT NULL, record TEXT NOT NULL);''')
            con.execute('INSERT INTO meta VALUES (?,?,?)', (canonical(config), fingerprint(config), 'active'))
        return self.observe()

    def _state(self, con):
        row = con.execute('SELECT * FROM meta').fetchone()
        config = json.loads(row['config'])
        if fingerprint(config) != row['sha256'] or fingerprint(config['inputs']) != config['inputs_sha256']:
            raise ResearchError('INPUT_CHANGED', 'frozen study configuration or input changed')
        if config['analysis_code_sha256'] != code_identity():
            raise ResearchError('CODE_CHANGED', 'study code identity changed; preserve the old run')
        library = KnowledgeIndex(config['index_path'])
        if library.manifest['database_sha256'] != config['index_sha256']:
            raise ResearchError('CORPUS_CHANGED', 'study is bound to its original evidence index')
        actions = []
        for item in con.execute('SELECT * FROM actions ORDER BY ordinal'):
            record = json.loads(item['record'])
            if (record['id'] != item['id'] or record['ordinal'] != len(actions) + 1
                    or fingerprint(record['result']) != record['result_sha256']
                    or fingerprint({key: record[key] for key in ACTION_FIELDS}) != item['request_sha256']):
                raise ResearchError('EVIDENCE_CHANGED', 'stored research decision or result changed')
            actions.append(record)
        citations = {}
        for action in actions:
            if action['action'] in {'search', 'read_source'}:
                for hit in action['result']['evidence']:
                    if action['action'] == 'read_source':
                        citations.pop(hit['citation_id'], None)  # Refresh an old excerpt in bounded prompts without a new identity.
                    citations[hit['citation_id']] = hit
        body = {'schema_version': config['schema_version'], 'goal': config['goal'], 'status': row['status'],
                'decision_origin': config['decision_origin'], 'configuration_sha256': row['sha256'],
                'corpus_sha256': config['corpus_sha256'], 'archive_sha256': config['inputs']['source']['archive_sha256'],
                'budget': {'actions_used': len(actions), 'max_actions': config['max_actions'],
                           'fits_used': sum(a['action'] == 'fit' for a in actions), 'max_fits': config['max_fits']},
                'data': {'n': 8, 'unit': 'alloy_aggregate', 'features': list(c01.FEATURES),
                         'targets': [target['id'] for target in c01.TARGETS], 'audit': config['inputs']['audit']},
                'actions': actions, 'citations': list(citations.values()),
                'source_catalogue': library.catalogue(limit=8),
                'scientific_status': 'exploratory_reused_loo_no_independent_validation',
                'cloud_calls': 0, 'backend_model_calls': 0, 'unattended_model_loop_verified': False}
        return config, {**body, 'observation_sha256': fingerprint(body)}, citations

    def observe(self):
        with self._connect() as con:
            return self._state(con)[1]

    @staticmethod
    def _validate(request, state, citations):
        if type(request) is not dict or set(request) != ACTION_FIELDS:
            raise ResearchError('INVALID_REQUEST', 'unsupported action fields; paths, code and evaluators are fixed')
        identifier(request['request_id'])
        if type(request['action']) is not str or request['action'] not in ACTIONS:
            raise ResearchError('INVALID_REQUEST', 'unsupported research action')
        if type(request['reason']) is not str or not 1 <= len(request['reason'].strip()) <= 2000 or type(request['parameters']) is not dict:
            raise ResearchError('INVALID_REQUEST', 'provide a bounded research reason and parameters')
        for key in ('source_citation_ids', 'evidence_action_ids'):
            items = request[key]
            if type(items) is not list or len(items) > 16 or any(type(item) is not str for item in items) or len(items) != len(set(items)):
                raise ResearchError('INVALID_EVIDENCE', 'cite distinct known source and action identifiers')
        if not set(request['source_citation_ids']) <= set(citations):
            raise ResearchError('INVALID_EVIDENCE', 'source citation was not retrieved in this study')
        if request['action'] in {'search', 'read_source'}:
            scope = C01Research._source_scope(request['parameters'])
            if scope:
                known_sources = {item['document_id']: item['source_sha256']
                                 for item in state['source_catalogue']['documents']}
                known_sources.update({hit['source']['id']: hit['source']['sha256'] for hit in state['citations']})
                if known_sources.get(scope['document_id']) != scope['source_sha256']:
                    raise ResearchError('INVALID_SOURCE_SELECTION', 'select a document and matching source SHA known in this observation')
        if request['action'] == 'review_evidence':
            C01Research._review(request['parameters'], state, request['source_citation_ids'])
        known = {action['id'] for action in state['actions']}
        if not set(request['evidence_action_ids']) <= known:
            raise ResearchError('INVALID_EVIDENCE', 'unknown research action evidence')
        if request['action'] in EXPERIMENTS | {'propose_control'}:
            experiments = [action for action in state['actions'] if action['action'] in EXPERIMENTS]
            if not request['source_citation_ids'] or (experiments and experiments[-1]['id'] not in request['evidence_action_ids']):
                raise ResearchError('INVALID_EVIDENCE', 'cite retrieved sources and latest experiment before deciding')
        if request['action'] == 'review_evidence' and request['parameters']['field'] == 'control_rationale':
            control = control_review_state(state)
            required = {control['proposal_action_id']}
            if control['latest_experiment_id'] is not None:
                required.add(control['latest_experiment_id'])
            if (not control['current'] or control['reviewed']
                    or not required <= set(request['evidence_action_ids'])):
                raise ResearchError('INVALID_CONTROL_REVIEW', 'review the exact current unreviewed proposal and its latest experimental feedback')
        if request['observation_sha256'] != state['observation_sha256']:
            raise ResearchError('STALE_OBSERVATION', 'read current feedback before choosing the next action')
        if state['status'] != 'active':
            raise ResearchError('NOT_ACTIVE', 'stopped or paused studies do not dispatch more work')
        maximum = state['budget']['max_actions'] - (0 if request['action'] in {'stop', 'pause'} else 1)
        if state['budget']['actions_used'] >= maximum:
            raise ResearchError('BUDGET_EXHAUSTED', 'reserve the final action slot for a stop or pause decision')

    def apply(self, request):
        if type(request) is not dict:
            raise ResearchError('INVALID_REQUEST', 'request must be an object')
        identifier(request.get('request_id'))
        with self._connect(True) as con:
            con.execute('BEGIN IMMEDIATE')
            config, state, citations = self._state(con)
            digest = fingerprint(request)
            old = con.execute('SELECT request_sha256,record FROM actions WHERE request_id=?', (request['request_id'],)).fetchone()
            if old:
                if old['request_sha256'] != digest:
                    raise ResearchError('IDEMPOTENCY_CONFLICT', 'request id already belongs to another research decision')
                return {'replayed': True, 'action': json.loads(old['record']), 'state': state}
            self._validate(request, state, citations)
            action, params = request['action'], request['parameters']
            record_id = uuid.uuid4().hex
            result = (self._review(params, state, request['source_citation_ids']) if action == 'review_evidence'
                      else self._execute(action, params, config, state, record_id))
            record = {'id': record_id, 'ordinal': len(state['actions']) + 1, **request,
                      'result': result, 'created': time.time(), 'result_sha256': fingerprint(result),
                      'analysis_code_sha256': config['analysis_code_sha256'],
                      'scientific_status': state['scientific_status']}
            con.execute('INSERT INTO actions VALUES (?,?,?,?,?)',
                        (record['ordinal'], record_id, request['request_id'], digest, canonical(record)))
            if action in {'pause', 'stop'}:
                con.execute('UPDATE meta SET status=?', ('paused' if action == 'pause' else 'stopped',))
            return {'replayed': False, 'action': record, 'state': self._state(con)[1]}

    @staticmethod
    def _review(params, state, source_ids):
        """Bind a model's interpretation to original chunks, without approving it.

        The caller supplies citation IDs, never paths, quote replacements, audit
        edits or qualification flags. Source linkage does not establish meaning.
        """
        required = {'field', 'question', 'finding', 'status', 'next_check'}
        if type(params) is not dict or set(params) != required:
            raise ResearchError('INVALID_REVIEW', 'review requires field, question, finding, status and next_check')
        if type(params['field']) is not str or params['field'] not in REVIEW_FIELDS:
            raise ResearchError('INVALID_REVIEW', 'review field must name an existing feature, target or protocol condition')
        if type(params['status']) is not str or params['status'] not in {'supported', 'unresolved', 'conflicting'}:
            raise ResearchError('INVALID_REVIEW_STATUS', 'status must be supported, unresolved or conflicting; partial knowledge remains unresolved')
        for key, maximum in (('question', 500), ('finding', 1000), ('next_check', 500)):
            if type(params[key]) is not str or not params[key].strip() or len(params[key]) > maximum:
                raise ResearchError('INVALID_REVIEW', 'review text and next check must be nonempty and bounded')
        citations = {item['citation_id']: item for item in state['citations']}
        if (type(source_ids) is not list or not 1 <= len(source_ids) <= 4
                or any(type(value) is not str for value in source_ids)
                or len(set(source_ids)) != len(source_ids) or not set(source_ids) <= set(citations)):
            raise ResearchError('INVALID_EVIDENCE', 'review requires one to four distinct retrieved citations')
        for old in state['actions']:
            if (params['field'] != 'control_rationale' and old['action'] == 'review_evidence' and old['parameters'] == params
                    and set(old['source_citation_ids']) == set(source_ids)):
                raise ResearchError('DUPLICATE_REVIEW', 'this exact interpretation and evidence were already recorded')
        evidence = []
        for key in source_ids:
            hit = citations[key]
            evidence.append({name: hit[name] for name in ('citation_id', 'source', 'location', 'quote')})
        return {**params, 'evidence': evidence, 'source_linkage_verified': True,
                'interpretation_verified': False, 'scientific_approval': False,
                'qualification': 'model_assertion_with_original_source_chunks_not_expert_review'}

    @staticmethod
    def _source_scope(params):
        present = {'document_id', 'source_sha256'} & set(params)
        if not present:
            return {}
        if (present != {'document_id', 'source_sha256'} or type(params['document_id']) is not str
                or not 1 <= len(params['document_id']) <= 160 or type(params['source_sha256']) is not str
                or re.fullmatch('[0-9a-f]{64}', params['source_sha256']) is None):
            raise ResearchError('INVALID_SOURCE_SELECTION', 'select the exact document ID and matching source SHA together')
        return {key: params[key] for key in ('document_id', 'source_sha256')}

    @staticmethod
    def _inspect_dataset(config):
        """Expose frozen cached values and their recorded origins, never load files."""
        def check(condition):
            if not condition:
                raise ResearchError('INVALID_DATASET', 'frozen dataset inspection requires coherent bounded inputs and provenance')

        def text(value, maximum):
            return type(value) is str and bool(value.strip()) and len(value) <= maximum and '\x00' not in value

        def number(value):
            return type(value) in (int, float) and math.isfinite(value)

        try:
            inputs = config['inputs']
            check(type(inputs) is dict and set(inputs) == {'samples', 'source', 'audit', 'provenance', 'bio_mapping'})
            check(type(inputs['audit']) is list)
            check(fingerprint(inputs) == config['inputs_sha256'])
            features, targets = list(c01.FEATURES), [item['id'] for item in c01.TARGETS]
            fields = features + targets
            samples = inputs['samples']
            check(type(samples) is list and len(samples) == 8)
            for row in samples:
                check(type(row) is dict and set(row) == {'sample_id', *fields}
                      and text(row['sample_id'], 80) and all(number(row[field]) for field in fields))
            sample_ids = [row['sample_id'] for row in samples]
            check(len(set(sample_ids)) == 8)
            values = {row['sample_id']: row for row in samples}
            provenance = inputs['provenance']
            check(type(provenance) is list and len(provenance) == 64)
            pairs, workbooks = set(), set()
            for cell in provenance:
                check(type(cell) is dict and set(cell) == {'sample_id', 'field', 'source', 'sheet', 'cell', 'raw', 'formula'})
                check(text(cell['sample_id'], 80) and cell['sample_id'] in values
                      and type(cell['field']) is str and cell['field'] in fields)
                pair = (cell['sample_id'], cell['field'])
                check(pair not in pairs)
                pairs.add(pair)
                check(text(cell['source'], 160) and '/' not in cell['source'] and '\\' not in cell['source']
                      and ':' not in cell['source'] and cell['source'].lower().endswith(('.xlsx', '.xls'))
                      and text(cell['sheet'], 160) and type(cell['cell']) is str
                      and re.fullmatch(r'[A-Z]{1,3}[1-9][0-9]{0,6}', cell['cell']) is not None)
                check(text(cell['raw'], 256) and (cell['formula'] is None or text(cell['formula'], 512)))
                parsed = c01.parse_measurement(cell['raw'])
                check(parsed['status'] == 'numeric' and parsed['value'] == values[cell['sample_id']][cell['field']])
                workbooks.add(cell['source'])
            check(pairs == {(sample, field) for sample in sample_ids for field in fields})
            mappings = inputs['bio_mapping']
            check(type(mappings) is list and len(mappings) == 8)
            mapped, labels = set(), set()
            for mapping in mappings:
                check(type(mapping) is dict and set(mapping) == {'sample_id', 'bio_label', 'shared_fields_compared',
                                                                 'max_abs_difference', 'consistent_with_row_mapping'})
                check(text(mapping['sample_id'], 80) and mapping['sample_id'] in values
                      and mapping['sample_id'] not in mapped and text(mapping['bio_label'], 80)
                      and mapping['bio_label'] not in labels and type(mapping['shared_fields_compared']) is int
                      and mapping['shared_fields_compared'] == 6 and number(mapping['max_abs_difference'])
                      and mapping['max_abs_difference'] >= 0 and type(mapping['consistent_with_row_mapping']) is bool
                      and mapping['consistent_with_row_mapping'] == (mapping['max_abs_difference'] <= 1e-6))
                mapped.add(mapping['sample_id'])
                labels.add(mapping['bio_label'])
            source = inputs['source']
            check(type(source) is dict and type(source.get('archive_sha256')) is str
                  and re.fullmatch('[0-9a-f]{64}', source['archive_sha256']) is not None
                  and type(source.get('files')) is list and 1 <= len(source['files']) <= 4096)
            matched = {name: [] for name in workbooks}
            for item in source['files']:
                check(type(item) is dict and text(item.get('member'), 1024))
                name = item['member'].rsplit('/', 1)[-1]
                if name in matched:
                    check(not item['member'].startswith('/') and '\\' not in item['member']
                          and ':' not in item['member'] and '..' not in item['member'].split('/')
                          and type(item.get('sha256')) is str and re.fullmatch('[0-9a-f]{64}', item['sha256']) is not None)
                    matched[name].append({'member': item['member'], 'sha256': item['sha256']})
            check(all(len(items) == 1 for items in matched.values()))
            summaries = []
            for field in fields:
                column = [row[field] for row in samples]
                summaries.append({'field': field, 'role': 'feature' if field in features else 'target',
                                  'count': 8, 'finite_count': 8, 'missing_count': 0, 'nonfinite_count': 0,
                                  'unique_count': len(set(column)), 'min': min(column), 'max': max(column),
                                  'mean': math.fsum(value / 8 for value in column), 'constant': len(set(column)) == 1})
            result = {'schema_version': 'c01-dataset-inspection-v1', 'inputs_sha256': config['inputs_sha256'],
                      'archive_sha256': source['archive_sha256'], 'row_unit': 'alloy_aggregate',
                      'features': features, 'targets': targets, 'samples': copy.deepcopy(samples),
                      'column_summary': summaries, 'provenance': copy.deepcopy(provenance),
                      'source_files': [matched[name][0] for name in sorted(matched)], 'bio_mapping': copy.deepcopy(mappings),
                      'scientific_approval': False, 'interpretation_verified': False,
                      'caveats': [
                          'Computational presence of cached numeric values does not verify physical units, assay normalization or scientific validity.',
                          'Provenance records and workbook hashes are frozen input metadata, not a new read or independent validation of those files.',
                          'Raw Excel text and formula text are retained separately from cached numeric values; no formula is evaluated.',
                          'Row-mapping agreement does not establish biological identities, independent samples or experimental batches.',
                          'Rereading the same inputs preserves identity and does not constitute new evidence or scientific progress.']}
            encoded = canonical(result).encode('utf-8')
        except ResearchError:
            raise
        except (KeyError, IndexError, TypeError, ValueError, OverflowError, RecursionError):
            raise ResearchError('INVALID_DATASET', 'frozen dataset inspection requires coherent bounded inputs and provenance') from None
        if len(encoded) > 24576:
            raise ResearchError('DATASET_INSPECTION_TOO_LARGE', 'frozen dataset inspection exceeds its 24576-byte result limit')
        return result

    @staticmethod
    def _execute(action, params, config, state, record_id):
        if action == 'propose_control':
            if set(params) != {'decision'} or type(params['decision']) is not str or params['decision'] not in {'pause', 'stop'}:
                raise ResearchError('INVALID_REQUEST', 'control proposal requires exactly decision=pause or stop')
            if state['budget']['max_actions'] - state['budget']['actions_used'] < 3:
                raise ResearchError('BUDGET_EXHAUSTED', 'reserve proposal, review and terminal decision action slots')
            if control_review_state(state)['current']:
                raise ResearchError('DUPLICATE_CONTROL_PROPOSAL', 'use the current proposal/review or obtain new experimental feedback before proposing again')
            return {'proposed_decision': params['decision'], 'control_applied': False,
                    'interpretation_verified': False, 'scientific_approval': False,
                    'qualification': 'pending_model_control_rationale_review_not_a_terminal_decision'}
        if action == 'inspect_dataset':
            if type(params) is not dict or params:
                raise ResearchError('INVALID_REQUEST', 'inspect_dataset accepts no parameters or paths')
            return C01Research._inspect_dataset(config)
        if action == 'search':
            if set(params) - {'query', 'kinds', 'limit', 'document_id', 'source_sha256'} or 'query' not in params:
                raise ResearchError('INVALID_REQUEST', 'search accepts query, optional kinds/limit and paired document ID/source SHA')
            limit = params.get('limit', 4)
            if (type(limit) is not int or not 1 <= limit <= 4 or type(params['query']) is not str
                    or not 1 <= len(params['query'].strip()) <= 512):
                raise ResearchError('INVALID_REQUEST', 'search query requires1..512 characters and limit1..4')
            kinds = params.get('kinds')
            if kinds is not None and (type(kinds) is not list or not 1 <= len(kinds) <= len(knowledge.KINDS)
                                      or any(type(k) is not str or k not in knowledge.KINDS for k in kinds)):
                raise ResearchError('INVALID_SEARCH_KIND', 'select offered source kinds or omit the filter')
            scope = C01Research._source_scope(params)
            try:
                return KnowledgeIndex(config['index_path']).search(params['query'], kinds=kinds, limit=limit, **scope)
            except SourceSelectionError as error:
                raise ResearchError(error.code, str(error)) from None
            except KnowledgeError:
                raise ResearchError('CORPUS_CHANGED', 'frozen source index could not be read consistently') from None
        if action == 'read_source':
            if set(params) != {'document_id', 'source_sha256', 'start_chunk', 'count'}:
                raise ResearchError('INVALID_SOURCE_SELECTION', 'read_source requires document ID, source SHA, start_chunk and count')
            C01Research._source_scope(params)
            if (type(params['start_chunk']) is not int or params['start_chunk'] < 0
                    or type(params['count']) is not int or not 1 <= params['count'] <= 2):
                raise ResearchError('INVALID_SOURCE_RANGE', 'read_source uses a zero-based chunk offset and count1..2')
            if state['actions'] and state['actions'][-1]['action'] == 'read_source' and state['actions'][-1]['parameters'] == params:
                raise ResearchError('DUPLICATE_READ', 'this current window was just read; use its original excerpts or choose another range')
            try:
                return KnowledgeIndex(config['index_path']).read_source(**params)
            except SourceSelectionError as error:
                raise ResearchError(error.code, str(error)) from None
            except KnowledgeError:
                raise ResearchError('CORPUS_CHANGED', 'frozen source chunks could not be read consistently') from None
        if action == 'fit':
            if set(params) != {'alpha', 'features', 'hypothesis', 'expected_effect'}:
                raise ResearchError('INVALID_REQUEST', 'fit requires a testable hypothesis, expected effect and bounded recipe')
            for key in ('hypothesis', 'expected_effect'):
                if type(params[key]) is not str or not 1 <= len(params[key].strip()) <= 1000:
                    raise ResearchError('INVALID_REQUEST', 'fit hypotheses and expectations require 1..1000 characters')
            alpha, features = params['alpha'], params['features']
            if (type(alpha) not in (int, float) or not math.isfinite(alpha) or not 0.001 <= alpha <= 10000
                    or type(features) is not list or not 1 <= len(features) <= 4
                    or any(type(feature) is not str or feature not in c01.FEATURES for feature in features)
                    or len(features) != len(set(features))):
                raise ResearchError('INVALID_REQUEST', 'invalid Ridge recipe; source fields and evaluator are fixed')
            features = [feature for feature in c01.FEATURES if feature in features]
            recipe = {'alpha': float(alpha), 'features': features}
            for previous in state['actions']:
                if previous['action'] == 'fit' and previous['result']['recipe'] == recipe:
                    raise ResearchError('DUPLICATE_RECIPE', 'this exact recipe has already been evaluated')
            if state['budget']['fits_used'] >= state['budget']['max_fits']:
                raise ResearchError('BUDGET_EXHAUSTED', 'cumulative fit budget exhausted')
            summary, predictions = c01._round(config['inputs']['samples'], 1, float(alpha), features)
            summary.update(id=record_id, title='受控Ridge留一比较')
            return {'recipe': recipe, 'summary': summary, 'predictions': predictions,
                    'fold_fits': 32, 'promotion': 'not_evaluated_no_independent_holdout',
                    'model_type': 'Ridge_coefficients_fitted_not_LLM_weight_training'}
        if action == 'residuals':
            if set(params) != {'fit_action_id'}:
                raise ResearchError('INVALID_REQUEST', 'residuals requires one previous fit action id')
            fit = next((item for item in state['actions'] if item['id'] == params['fit_action_id'] and item['action'] == 'fit'), None)
            if fit is None:
                raise ResearchError('INVALID_EVIDENCE', 'residuals requires an executed fit')
            if any(item['action'] == 'residuals' and item['parameters'] == params for item in state['actions']):
                raise ResearchError('DUPLICATE_ANALYSIS', 'residual analysis for this fit was already executed')
            return {'fit_action_id': fit['id'], **c01_loop.residual_influence(_csv_bytes(fit['result']['predictions']))}
        if params:
            raise ResearchError('INVALID_REQUEST', 'this action accepts no parameters')
        if action == 'correlation':
            if any(item['action'] == action for item in state['actions']):
                raise ResearchError('DUPLICATE_ANALYSIS', 'fixed pair sensitivity was already executed')
            return c01_loop.correlation_influence(_csv_bytes(config['inputs']['samples']))
        return {'decision': action, 'interpretation': 'Agent control decision; not an independent scientific result'}

    def export(self):
        with self._connect() as con:
            config, state, _ = self._state(con)
        lines = ['# C01 研究记录', '', state['goal'], '',
                 f"状态：{state['status']}。8个合金汇总样本；重复使用留一反馈，不是独立验证。", '',
                 '本记录保存逐步提交的决策与本地工具结果；模型身份、原生调用和额度需另查控制器账本。', '']
        for action in state['actions']:
            lines += [f"## {action['ordinal']}. {action['action']}", '', action['reason'], '',
                      '来源引用：' + ', '.join(action['source_citation_ids']),
                      '观察：' + action['observation_sha256'], '']
            if action['action'] == 'fit':
                for metric in action['result']['summary']['metrics']:
                    lines.append(f"- {metric['target']}: MAE={metric['mae']:.6g}, R²={metric['r2']:.6g}, 均值基线MAE={metric['baseline_mae']:.6g}")
                lines.append('')
            elif action['action'] in {'correlation', 'residuals'}:
                lines += ['```json', json.dumps(action['result'], ensure_ascii=False, indent=2), '```', '']
            elif action['action'] == 'read_source':
                window = action['result']['window']
                lines += [f"文档：{window['document_id']} / SHA256 {window['source_sha256']}", '',
                          f"实际读取：从零基片段{window['start_chunk']}读取{window['returned_chunks']}段；索引片段总数{window['total_chunks']}。", '',
                          '目录只导航，当前窗口不是全文覆盖证明；重读保留原引用身份。', '']
            elif action['action'] == 'inspect_dataset':
                value = action['result']
                lines += [f"冻结输入：{value['inputs_sha256']}；8个合金汇总行，4特征、4终点及64条缓存单元格出处。", '',
                          '仅核对冻结数值的计算可用性；不认证物理单位、映射、生物独立性或科学含义，也未重新读取工作簿或执行公式。', '']
            elif action['action'] == 'propose_control':
                lines += ['控制提议：' + action['parameters']['decision'] + '；尚未暂停或停止，不代表科研批准。', '']
            elif action['action'] == 'review_evidence':
                value = action['parameters']
                lines += [f"字段：{value['field']}；模型判断：{value['status']}（未获科学复核）", '',
                          value['question'], '', value['finding'], '', '下一项核验：' + value['next_check'], '']
        lines += ['## 引用位置', '']
        for citation in state['citations']:
            source = citation['source']
            lines += [f"- {citation['citation_id']}: {source['path']} / {citation['location']} / SHA256 {source['sha256']}"]
        return {'state': state, 'markdown': '\n'.join(lines) + '\n',
                'reproduction': {'inputs': config['inputs'], 'inputs_sha256': config['inputs_sha256'],
                                 'analysis_code_sha256': config['analysis_code_sha256'],
                                 'protocol': 'existing C01 fold-fitted scaler/Ridge_svd; all eight alloy groups held out once',
                                 'model_weight_training': '32 actual Ridge fits per recipe; no LLM weight training'}}
