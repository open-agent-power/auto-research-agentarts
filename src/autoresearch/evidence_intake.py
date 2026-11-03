"""Durable local draft intake; no model transport, executor or new budget."""
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import tempfile

from . import evidence_draft as draft, evidence_submission as submission, knowledge_sources as guard
from .contracts import ResearchError, canonical, fingerprint
from .returned_evidence import build_returned_evidence, validate_packet
from .tabular_submission import prepare_tabular_submission
from .tabular_preparation_view import _capture, export_tabular_preparation, read_tabular_preparation_artifacts


def _require(condition, message):
    if not condition: raise ResearchError('INTAKE_NEEDS_ATTENTION', message)


def _sha(raw): return hashlib.sha256(raw).hexdigest()


def _document(receipt):
    return {'schema_version': 'p02-evidence-submission-v1',
            **{k: receipt[k] for k in ('handoff_snapshot_sha256', 'selected_action_id', 'task_id', 'contributor', 'summary', 'unresolved_questions')},
            'sources': [{k: v for k, v in source.items() if k != 'bytes'} for source in receipt['sources']],
            'findings': [{k: v for k, v in finding.items() if k != 'locator_validation'} for finding in receipt['findings']]}


def _draft_identity(root, handoff):
    limits = {'task-binding.json': 20_000, 'contributor.json': 20_000, 'summary.txt': 20_000,
              'sources.csv': draft.MAX_CSV, 'findings.csv': draft.MAX_CSV, 'questions.txt': 300_000}
    raw = {name: guard._read(root, name, limit) for name, limit in limits.items()}
    binding = draft._json(raw['task-binding.json'])
    _require(binding == draft._binding(handoff), 'Draft task binding differs from selected handoff.')
    sources = draft._csv(raw['sources.csv'], draft.SOURCE_COLUMNS, 64)
    rows = draft._csv(raw['findings.csv'], draft.FINDING_COLUMNS, 256)
    files = {name: _sha(value) for name, value in raw.items()}; total = 0
    for source in sources:
        relative = guard._relative(source['path'])
        _require(len(relative.parts) >= 2 and relative.parts[0] == 'sources'
                 and source['path'].casefold() != 'sources/readme.txt', 'Source must be declared below sources/.')
        value = guard._read(root, source['path'], submission.MAX_FILE); total += len(value)
        _require(total <= submission.MAX_TOTAL, 'Draft sources exceed total bound.')
        digest = _sha(value)
        _require(source['sha256'] in ('', digest), 'Draft source hash differs from declared bytes.')
        files[source['path']] = digest; source['sha256'] = digest
    document = {'schema_version': 'p02-evidence-submission-v1',
                **{k: binding[k] for k in ('handoff_snapshot_sha256', 'selected_action_id', 'task_id')},
                'contributor': draft._json(raw['contributor.json']), 'summary': draft._text(raw['summary.txt']),
                'sources': sources,
                'findings': [{**{k: row[k] for k in ('id', 'claim', 'status', 'source_id', 'note')},
                              'locator': {'kind': row['locator_kind'], 'value': row['locator_value']}} for row in rows],
                'unresolved_questions': [line for line in draft._text(raw['questions.txt']).splitlines() if line.strip()]}
    submission._validate_input(document, handoff)
    # create_submission normalizes declared source paths to these receipt paths.
    for source in document['sources']:
        source['path'] = 'sources/' + source['id'] + '/' + guard._relative(source['path']).name
    return {'files': files, 'document_sha256': fingerprint(document)}


class EvidenceIntake:
    def __init__(self, workspace):
        self.root = submission._root(workspace)
        self.config_path = self.root / 'config.json'
        self.state_path = self.root / 'state.json'

    @contextmanager
    def _lock(self):
        path = self.root / 'advance.lock'
        try: fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError: raise ResearchError('INTAKE_BUSY', 'Intake lock exists; no automatic stale-lock removal.') from None
        stamp = os.fstat(fd)
        try:
            os.write(fd, str(os.getpid()).encode('ascii')); os.fsync(fd); yield
        finally:
            os.close(fd)
            current = path.stat(follow_symlinks=False)
            if (stamp.st_dev, stamp.st_ino) == (current.st_dev, current.st_ino): path.unlink()

    def _atomic(self, path, value):
        submission._root(path.parent)
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent, prefix='.intake-', delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(canonical(value) + '\n'); stream.flush(); os.fsync(stream.fileno())
        try:
            submission._root(path)
            if path.exists(): guard._read(path.parent, path.name, 2_000_000)
            os.replace(temporary, path)
        finally:
            if temporary.exists(): temporary.unlink()

    def create(self, draft_directory, handoff_directory, diagnostic_directory):
        paths = {key: str(submission._root(value)) for key, value in
                 [('draft_directory', draft_directory), ('handoff_directory', handoff_directory), ('diagnostic_directory', diagnostic_directory)]}
        for value in paths.values():
            source = Path(value)
            _require(not (self.root == source or self.root.is_relative_to(source) or source.is_relative_to(self.root)),
                     'Intake workspace overlaps draft or sealed input.')
        handoff = draft._handoff(paths['handoff_directory'], paths['diagnostic_directory'])
        identity = _draft_identity(Path(paths['draft_directory']), handoff)
        config = {'schema_version': 'p02-evidence-intake-v1', 'private_sources': paths,
                  'handoff_snapshot_sha256': handoff['snapshot_sha256'], 'selected_action_id': handoff['selected_action_id'],
                  'task_id': handoff['selected_task']['id'], 'draft_identity': identity}
        config['snapshot_sha256'] = fingerprint(config)
        self.root.mkdir(parents=True, exist_ok=True)
        with self._lock():
            _require({p.name for p in self.root.iterdir()} == {'advance.lock'}, 'Use a fresh intake workspace.')
            self._atomic(self.config_path, config)
            self._save({'status': 'initialized', 'stage': 'draft', 'intent': None, 'artifacts': {}, 'counts': {}}, config)
        return self.status()

    def _config(self):
        value = guard._json(guard._read(self.root, 'config.json', 2_000_000))
        _require(value.get('schema_version') == 'p02-evidence-intake-v1'
                 and value.get('snapshot_sha256') == fingerprint({k: v for k, v in value.items() if k != 'snapshot_sha256'}),
                 'Intake configuration changed.')
        return value

    def _save(self, state, config):
        value = {**{k: v for k, v in state.items() if k != 'snapshot_sha256'},
                 'schema_version': 'p02-evidence-intake-status-v1', 'configuration_sha256': config['snapshot_sha256'],
                 'model_read_performed': False, 'model_calls': 0, 'new_fits': 0, 'budget_created': False}
        value['snapshot_sha256'] = fingerprint(value)
        self._atomic(self.state_path, value)
        return value

    def status(self):
        config = self._config(); value = guard._json(guard._read(self.root, 'state.json', 2_000_000))
        _require(value.get('configuration_sha256') == config['snapshot_sha256']
                 and value.get('snapshot_sha256') == fingerprint({k: v for k, v in value.items() if k != 'snapshot_sha256'})
                 and value.get('model_read_performed') is False and value.get('budget_created') is False
                 and value.get('model_calls') == 0 and value.get('new_fits') == 0, 'Intake state changed.')
        return value

    def _intent(self, state, config, name, output):
        if name in state['artifacts']:
            _require(output.exists(), 'Previously completed stage is missing; it will not be recreated.')
            return
        _require(state.get('intent') in {None, name}, 'Another incomplete stage needs attention first.')
        _require(not output.exists() or state.get('intent') == name,
                 'Unrecognized existing stage output; no adoption or overwrite.')
        state['intent'] = name; self._save(state, config)

    def _record_artifact(self, state, name, value):
        if name in state['artifacts']:
            _require(state['artifacts'][name] == value, 'Previously pinned ' + name + ' artifact changed.')
        else:
            state['artifacts'][name] = value

    def advance(self, stop_after='prepared'):
        _require(stop_after in {'receipt', 'prepared'}, 'stop_after must be receipt or prepared.')
        with self._lock():
            config = self._config(); state = self.status()
            if state['status'] == 'needs_attention': return state
            try:
                paths = config['private_sources']; handoff = draft._handoff(paths['handoff_directory'], paths['diagnostic_directory'])
                _require(handoff['snapshot_sha256'] == config['handoff_snapshot_sha256']
                         and handoff['selected_action_id'] == config['selected_action_id'], 'Frozen handoff changed.')
                receipt_root = self.root / 'receipt'
                self._intent(state, config, 'receipt', receipt_root)
                if not receipt_root.exists():
                    _require(_draft_identity(Path(paths['draft_directory']), handoff) == config['draft_identity'],
                             'Draft changed before compilation; start a new intake for changed input.')
                    draft.compile_draft(paths['draft_directory'], paths['handoff_directory'], paths['diagnostic_directory'], receipt_root)
                receipt = submission.read_submission(receipt_root, handoff)
                _require(fingerprint(_document(receipt)) == config['draft_identity']['document_sha256'],
                         'Receipt is not the exact originally frozen draft submission.')
                self._record_artifact(state, 'receipt', {'directory': str(receipt_root), 'snapshot_sha256': receipt['snapshot_sha256'],
                    'receipt_sha256': _sha(guard._read(receipt_root, 'receipt.json', submission.MAX_METADATA))})
                if state['stage'] in {'draft', 'receipt'}:
                    state.update(status='receipt_ready', stage='receipt')
                if state.get('intent') == 'receipt': state['intent'] = None
                self._save(state, config)
                if stop_after == 'receipt': return self.status()
                tabular = any(f['locator']['kind'] in {'xlsx_cell', 'text_lines'} for f in receipt['findings'])
                if tabular:
                    preparation_root = self.root / 'preparation'
                    self._intent(state, config, 'preparation', preparation_root)
                    if not preparation_root.exists():
                        prepare_tabular_submission(paths['handoff_directory'], paths['diagnostic_directory'], receipt_root, preparation_root)
                    prep = guard._json(guard._read(preparation_root, 'preparation.json', 2_000_000))
                    _require(prep['original_receipt_snapshot_sha256'] == receipt['snapshot_sha256']
                             and prep['original_receipt_sha256'] == state['artifacts']['receipt']['receipt_sha256'],
                             'Preparation is not derived from this intake receipt.')
                    prepared_view = _capture(preparation_root, handoff)
                    packet_root = preparation_root
                    self._record_artifact(state, 'preparation', {'directory': str(preparation_root),
                        'preparation_sha256': prepared_view['preparation_sha256'], 'receipt_snapshot_sha256': prep['receipt_snapshot_sha256']})
                    if state.get('intent') == 'preparation': state['intent'] = None
                    self._save(state, config)
                    publication_root = self.root / 'publication'
                    self._intent(state, config, 'publication', publication_root)
                    if not publication_root.exists():
                        export_tabular_preparation(preparation_root, paths['handoff_directory'], paths['diagnostic_directory'], publication_root)
                    files = read_tabular_preparation_artifacts(publication_root, handoff)
                    view = guard._json(files['prepared-input.json'])
                    _require(view == prepared_view, 'Publication is not this exact prepared tabular input.')
                    self._record_artifact(state, 'publication', {'directory': str(publication_root), 'snapshot_sha256': view['snapshot_sha256']})
                else:
                    packet_root = self.root
                    self._intent(state, config, 'packet', self.root / 'packet.json')
                    if not (self.root / 'packet.json').exists():
                        packet = build_returned_evidence(paths['handoff_directory'], paths['diagnostic_directory'], receipt_root)
                        self._atomic(self.root / 'packet.json', packet)
                packet_raw = guard._read(packet_root, 'packet.json', 4_000_000); packet = guard._json(packet_raw)
                validate_packet(packet)
                expected_receipt = (prep['receipt_snapshot_sha256'] if tabular else receipt['snapshot_sha256'])
                _require(packet['submission_snapshot_sha256'] == expected_receipt
                         and packet['handoff_snapshot_sha256'] == handoff['snapshot_sha256'], 'Prepared packet belongs to another receipt or task.')
                if not tabular:
                    _require(packet['sources'] == [{k: s[k] for k in ('id', 'sha256', 'url', 'media_type', 'license_note', 'bytes')} for s in receipt['sources']]
                             and [{k: v for k, v in c.items() if k not in {'chunk_ids', 'interpretation_status'}} for c in packet['submission_claims']] == receipt['findings'],
                             'Packet source descriptors or submitted claims changed.')
                self._record_artifact(state, 'packet', {'path': str(packet_root / 'packet.json'), 'sha256': _sha(packet_raw), 'snapshot_sha256': packet['snapshot_sha256']})
                state['counts'] = {'sources': len(packet['sources']), 'chunks': len(packet['chunks']), 'exclusions': len(packet['exclusions'])}
                state.update(status='prepared' if packet['chunks'] else 'needs_input', stage='prepared', intent=None)
                state['exclusions'] = packet['exclusions']
                return self._save(state, config)
            except (ResearchError, ValueError, OSError, KeyError, TypeError) as error:
                state.update(status='needs_attention', error={'code': getattr(error, 'code', 'INTAKE_STAGE_FAILED'),
                    'message': str(error)[:500], 'automatic_retry': False})
                return self._save(state, config)
