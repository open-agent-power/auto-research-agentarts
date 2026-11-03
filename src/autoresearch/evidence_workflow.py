"""One durable child assessment and publication; never reset a native budget."""
from contextlib import contextmanager, nullcontext
import hashlib
import json
import os
from pathlib import Path
import sqlite3

from .chemotopo_experiment_evidence import _safe_file
from .contracts import ResearchError, canonical, fingerprint
from .local_ollama import require


def assessment_module():
    from . import source_assessment
    return source_assessment


def publication_module():
    from . import source_assessment_view
    return source_assessment_view


def _path(value):
    path = Path(value).absolute()
    for part in (path, *path.parents):
        require(not part.is_symlink() and not getattr(part, 'is_junction', lambda: False)(),
                'UNSAFE_PATH', 'Workflow paths cannot redirect.')
    return path.resolve()


def _overlap(a, b):
    return a == b or a.is_relative_to(b) or b.is_relative_to(a)


def _write(path, value):
    with path.open('x', encoding='utf-8') as stream:
        stream.write(canonical(value) + '\n'); stream.flush(); os.fsync(stream.fileno())


class EvidenceWorkflow:
    def __init__(self, root):
        self.root = _path(root)
        self.config_path = self.root / 'config.json'
        self.child = self.root / 'assessment'
        self.publication = self.root / 'publication'

    @contextmanager
    def _lock(self):
        path = self.root / 'advance.lock'
        try:
            descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            raise ResearchError('WORKFLOW_BUSY', 'Workflow lock exists; no stale lock is automatically removed.') from None
        owned = os.fstat(descriptor)
        try:
            os.write(descriptor, (str(os.getpid()) + '\n').encode('ascii')); os.fsync(descriptor)
            yield
        finally:
            os.close(descriptor)
            current = path.stat(follow_symlinks=False)
            if (owned.st_dev, owned.st_ino) == (current.st_dev, current.st_ino):
                path.unlink()

    def create(self, source_packet, goal, max_requests=4, prior_attempt=None, protocol_change_reason=None):
        require(type(goal) is str and 1 <= len(goal.strip()) <= 2000
                and type(max_requests) is int and 2 <= max_requests <= 4
                and type(protocol_change_reason) is str and 1 <= len(protocol_change_reason.strip()) <= 2000,
                'INVALID_REQUEST', 'Goal, protocol change purpose and frozen 2..4 requests required.')
        packet_path = _path(source_packet)
        previous = _path(prior_attempt) if prior_attempt is not None else None
        for source in (packet_path, previous):
            require(source is None or not _overlap(self.root, source), 'UNSAFE_PATH', 'Workflow overlaps source or prior study.')
        raw = _safe_file(packet_path, 4_000_000)
        config = {'schema_version': 'p02-evidence-workflow-v1', 'goal': goal, 'max_requests': max_requests,
                  'source_packet': str(packet_path), 'source_packet_sha256': hashlib.sha256(raw).hexdigest(),
                  'source_packet_bytes': len(raw), 'prior_attempt': str(previous) if previous else None,
                  'protocol_change_reason': protocol_change_reason}
        config['configuration_sha256'] = fingerprint(config)
        self.root.mkdir(parents=True, exist_ok=True)
        with self._lock():
            if self.config_path.exists():
                require(self._config() == config, 'CONFIG_CHANGED', 'Existing workflow goal, packet, purpose and cumulative budget are frozen.')
                return config
            require({p.name for p in self.root.iterdir()} == {'advance.lock'},
                    'NEEDS_REVIEW', 'Unrecognized or partially initialized workflow; do not overwrite it.')
            with (self.root / 'packet.json').open('xb') as stream:
                stream.write(raw); stream.flush(); os.fsync(stream.fileno())
            _write(self.config_path, config)
        return config

    def _config(self):
        config = json.loads(_safe_file(self.config_path, 20_000))
        require(config.get('schema_version') == 'p02-evidence-workflow-v1'
                and config.get('configuration_sha256') == fingerprint({k: v for k, v in config.items() if k != 'configuration_sha256'}),
                'CONFIG_CHANGED', 'Workflow configuration changed.')
        raw = _safe_file(self.root / 'packet.json', 4_000_000)
        require(len(raw) == config['source_packet_bytes'] and hashlib.sha256(raw).hexdigest() == config['source_packet_sha256'],
                'EVIDENCE_CHANGED', 'Frozen workflow packet changed.')
        return config

    def _prepare(self, config):
        module = assessment_module(); loop = module.SourceAssessmentCloudLoop(self.child)
        if not loop.study.db.exists():
            require(not self.child.exists() or not any(self.child.iterdir()),
                    'NEEDS_REVIEW', 'Partial child study cannot be silently replaced.')
            loop.study.create(self.root / 'packet.json', config['goal'], max_requests=config['max_requests'],
                              prior_attempt=config['prior_attempt'])
        with loop.study._connect() as con:
            child_config, state, _ = loop.study._state(con)
        require(child_config['goal'] == config['goal'] and child_config['max_requests'] == config['max_requests']
                and child_config['private_sources']['packet_path'] == str(self.root / 'packet.json')
                and child_config.get('prior_attempt') == config['prior_attempt'],
                'CONFIG_CHANGED', 'Child study does not match the one frozen workflow.')
        return loop, state

    @staticmethod
    def _unknown(result):
        return any(c['status'] in {'sending', 'received'} for c in result.get('calls', []))

    def _publication(self, loop, result):
        state = result['study']
        terminal = state['status'] in {'paused', 'stopped'} or result['status'] == 'completed'
        if self._unknown(result) or not terminal:
            require(not self.publication.exists(), 'NEEDS_REVIEW', 'Existing publication conflicts with an unfinished child.')
            return None
        module = publication_module()
        if not self.publication.exists():
            module.export_source_assessment(self.child, self.publication)
        files = module.read_source_assessment_artifacts(self.publication,
                                                        expected_source_snapshot=state['source_snapshot_sha256'])
        view = json.loads(files['assessment.json'])
        require(view['source_snapshot_sha256'] == state['source_snapshot_sha256']
                and [(a['id'], a['result_sha256']) for a in view['actions']] ==
                    [(a['id'], a['result_sha256']) for a in state['actions']]
                and view['execution']['requests_reserved'] == result['budget']['requests_reserved'],
                'EVIDENCE_CHANGED', 'Existing publication does not match the exact terminal child.')
        return {'directory': str(self.publication), 'snapshot_sha256': view['snapshot_sha256'],
                'source_snapshot_sha256': view['source_snapshot_sha256']}

    def _summary(self, result, publication=None, error=None):
        state = result['study']
        recorded = [a for a in state['actions'] if a['action'] == 'record_assessment']
        if error or self._unknown(result) or result['status'] not in {'active', 'completed', 'not_configured'}:
            status = 'needs_attention'
        elif recorded:
            answers = recorded[-1]['result']['answers']
            status = ('awaiting_external_input' if any(a['status'] in {'unresolved', 'conflicting'} for a in answers)
                      else 'pending_scientific_interpretation')
        elif state['status'] == 'paused': status = 'paused_unassessed'
        elif state['status'] == 'stopped': status = 'stopped'
        elif result.get('reason') == 'REQUEST_LIMIT': status = 'request_limit'
        else: status = 'prepared'
        return {'schema_version': 'p02-evidence-workflow-status-v1', 'workflow_status': status,
                'workflow': str(self.root), 'child_workspace': str(self.child),
                'study_status': state['status'], 'controller_status': result['status'],
                'controller_reason': result.get('reason'), 'budget': result['budget'],
                'assessment_action_id': recorded[-1]['id'] if recorded else None,
                'publication': publication, 'progress': None, 'attention_code': error, 'child': result,
                'external_task_executed': False, 'scientific_validation': False, 'new_fits': 0}

    def _progress(self, result):
        """A separate incomplete record, never a substitute for publication."""
        if not any(c['status'] == 'applied' for c in result.get('calls', [])):
            return None
        state = result['study']; count = result['budget']['requests_reserved']
        # Counts alone cannot identify a journal: reconciliation can change a
        # request while keeping its ordinal. Preserve each distinct capture.
        target = self.root / 'history' / ('progress-%d-%s' % (count, fingerprint(result)[:24]))
        module = publication_module()
        if not target.exists():
            module.export_source_progress(self.child, target)
        files = module.read_source_progress_artifacts(target,
                                                      expected_source_snapshot=state['source_snapshot_sha256'])
        view = json.loads(files['progress.json'])
        require(view.get('schema_version') == 'p02-source-assessment-progress-v1'
                and view.get('publication_eligible') is False
                and view['source_snapshot_sha256'] == state['source_snapshot_sha256']
                and [(a['id'], a['result_sha256']) for a in view['actions']] ==
                    [(a['id'], a['result_sha256']) for a in state['actions']]
                and view['execution']['requests_reserved'] == count,
                'EVIDENCE_CHANGED', 'Incomplete progress record differs from the current child journal.')
        return {'directory': str(target), 'snapshot_sha256': view['snapshot_sha256'],
                'source_snapshot_sha256': view['source_snapshot_sha256'], 'publication_eligible': False}

    def advance(self, max_new_requests=0, transport=None, identity=None):
        """Continue this child only. A callable transport factory is entered lazily.

        A factory receives a fresh workflow-owned receipt directory. Unknown sends
        never reach it. Existing owned transport objects can also be supplied.
        """
        require(type(max_new_requests) is int and 0 <= max_new_requests <= 4,
                'INVALID_REQUEST', 'At most four new requests per advance; frozen child cap still applies.')
        with self._lock():
            config = self._config(); loop, state = self._prepare(config)
            history = self.root / 'history'; history.mkdir(exist_ok=True)
            ordinal = 1
            while ((history / ('advance-%06d.json' % ordinal)).exists()
                   or (history / ('transport-%06d' % ordinal)).exists()): ordinal += 1
            receipt = history / ('advance-%06d.json' % ordinal)
            result = {'status': 'not_configured', 'reason': None, 'study': state, 'calls': [],
                      'budget': {'max_requests': config['max_requests'], 'requests_reserved': 0}}
            error = None; server = None
            try:
                if loop.db.exists():
                    # Recovery consumes only an already captured response. A
                    # sending row raises NEEDS_REVIEW without a transport call.
                    result = loop.run(max_new_requests=0)
                if max_new_requests and result['status'] in {'active', 'not_configured'} and result['study']['status'] == 'active':
                    require(transport is not None, 'LOCAL_SERVER_REQUIRED', 'Live continuation needs the existing guarded owned transport.')
                    if callable(transport):
                        directory = history / ('transport-%06d' % ordinal)
                        require(not directory.exists(), 'NEEDS_REVIEW', 'Transport receipt directory already exists.')
                        manager = transport(directory)
                    else: manager = nullcontext(transport)
                    with manager as server:
                        verified = identity if identity is not None else server.acquire()
                        if not loop.db.exists(): loop.configure(verified)
                        result = loop.run(server, max_new_requests=max_new_requests, verified_weights=verified)
                publication = self._publication(loop, result)
            except (ResearchError, OSError, ValueError, sqlite3.Error) as failure:
                error = getattr(failure, 'code', 'WORKFLOW_OPERATION_FAILED')
                if loop.db.exists(): result = loop.status()
                publication = None
            summary = self._summary(result, publication, error)
            if summary['workflow_status'] == 'needs_attention' and loop.db.exists():
                try:
                    summary['progress'] = self._progress(result)
                except (ResearchError, OSError, ValueError) as failure:
                    summary['progress_error_code'] = getattr(failure, 'code', 'PROGRESS_CAPTURE_FAILED')
            if server is not None:
                summary['transport_cleanup'] = {'owned_server_stopped': getattr(server, 'stopped', None),
                                                'key_metadata_unchanged': getattr(server, 'key_metadata_unchanged', None)}
            _write(receipt, summary)
            return summary
