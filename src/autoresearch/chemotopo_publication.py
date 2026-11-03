"""Public research delivery with explicitly separate operator archival provenance."""
import copy
import hashlib
import json
from pathlib import Path

from .chemotopo_delivery import load_delivery, _safe
from .chemotopo_experiment_evidence import _safe_file
from .chemotopo_study import ChemoTopoMemory
from .contracts import ResearchError, fingerprint


def load_publication(workspace, *, archive_receipt=None, memory_workspace=None):
    base = load_delivery(workspace)
    result = copy.deepcopy(base)
    result['base_snapshot_sha256'] = base['snapshot_sha256']
    result['prediction'] = next((a['summary'] for a in base['actions'] if a['action'] == 'inspect_prediction'), None)
    result['archive'] = None
    if (archive_receipt is None) != (memory_workspace is None):
        raise ResearchError('INVALID_REQUEST', 'Archive receipt and separate memory store must be supplied together.')
    if archive_receipt is not None:
        raw = _safe_file(Path(archive_receipt).absolute(), 100000)
        receipt = json.loads(raw)
        actions = [{'id': a['id'], 'action': a['action'], 'result_sha256': a['result_sha256']} for a in base['actions']]
        selected = any(a['action'] == 'remember_evidence' and a['model_selected'] for a in base['actions'])
        if (receipt.get('schema_version') != 'p02-operator-archive-v1' or receipt.get('status') != 'completed'
                or receipt.get('persistence_trigger') != 'operator_postrun_workflow'
                or receipt.get('source_snapshot_sha256') != base['snapshot_sha256']
                or receipt.get('scope') != base['scope'] or receipt.get('source_actions') != actions
                or receipt.get('model_selected_remember') is not selected):
            raise ResearchError('EVIDENCE_CHANGED', 'Archive receipt does not belong to this frozen research.')
        wanted = receipt.get('entries')
        if not isinstance(wanted, list) or not 1 <= len(wanted) <= 8 or len({e['id'] for e in wanted}) != len(wanted):
            raise ResearchError('EVIDENCE_CHANGED', 'Unexpected archive entry list.')
        memory = ChemoTopoMemory(memory_workspace)
        entries = []
        with memory._connect() as con:
            if con is None:
                raise ResearchError('EVIDENCE_CHANGED', 'Archive memory is missing.')
            for item in wanted:
                row = con.execute('SELECT * FROM entries WHERE id=?', (item['id'],)).fetchone()
                if row is None:
                    raise ResearchError('EVIDENCE_CHANGED', 'Archived observation is missing.')
                record = memory._verify(con, row)
                versions = memory._versions(con, row['id'])
                if (row['record_sha256'] != item['record_sha256'] or record['scope'] != base['scope']
                        or record['payload'].get('type') != item['type']
                        or record['provenance']['action_id'] not in {a['id'] for a in actions}
                        or _safe(record) != record or _safe(versions) != versions):
                    raise ResearchError('EVIDENCE_CHANGED', 'Archived observation differs from its receipt or source.')
                entries.append({'record': record, 'record_sha256': row['record_sha256'],
                                'inclusion_status': row['status'], 'source_versions': versions})
        result['archive'] = {'persistence_trigger': receipt['persistence_trigger'],
                             'model_selected_remember': selected, 'receipt_sha256': hashlib.sha256(raw).hexdigest(),
                             'entries': entries, 'scope': base['scope']}
    result.pop('snapshot_sha256')
    result['snapshot_sha256'] = fingerprint(result)
    return result


ARTIFACT_LIMITS = {'report.pdf': 15000000, 'prediction.png': 5000000, 'prediction.svg': 3000000,
                   'research.json': 3000000, 'reproduction.zip': 30000000}


def read_artifacts(directory, snapshot):
    """Read fixed filenames only; verify publication identity and immutable bytes."""
    root = Path(directory).absolute()
    manifest = json.loads(_safe_file(root / 'manifest.json', 100000))
    if (manifest.get('schema_version') != 'p02-publication-artifacts-v1'
            or manifest.get('snapshot_sha256') != snapshot['snapshot_sha256']
            or set(manifest.get('files', {})) != set(ARTIFACT_LIMITS)):
        raise ResearchError('EVIDENCE_CHANGED', 'Report belongs to a different publication or has unexpected files.')
    files = {}
    for name, limit in ARTIFACT_LIMITS.items():
        payload = _safe_file(root / name, limit)
        expected = manifest['files'][name]
        if expected != {'sha256': hashlib.sha256(payload).hexdigest(), 'bytes': len(payload)}:
            raise ResearchError('EVIDENCE_CHANGED', 'Report artifact bytes differ from the frozen manifest.')
        files[name] = payload
    if json.loads(files['research.json']) != snapshot:
        raise ResearchError('EVIDENCE_CHANGED', 'Report research projection differs from current publication.')
    return files
