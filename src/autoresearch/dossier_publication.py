"""Validate an immutable dossier and its exact scientific source snapshots."""
import hashlib
from pathlib import Path
from .chemotopo_experiment_evidence import _safe_file
from .contracts import ResearchError, fingerprint
from .knowledge_sources import _json

LIMITS={'research-dossier.json':3_000_000,'research-dossier.md':1_000_000,'research-dossier.pdf':15_000_000}


def read_dossier_artifacts(directory,source_snapshots):
    root=Path(directory).absolute();manifest_raw=_safe_file(root/'manifest.json',100_000);manifest=_json(manifest_raw)
    files={name:_safe_file(root/name,limit) for name,limit in LIMITS.items()};view=_json(files['research-dossier.json'])
    expected={name:{'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw)} for name,raw in files.items()}
    if (type(manifest) is not dict or manifest.get('schema_version')!='p02-research-dossier-export-v1'
        or manifest.get('files')!=expected or type(view) is not dict or view.get('schema_version')!='p02-research-dossier-v1'
        or view.get('snapshot_sha256')!=fingerprint({k:v for k,v in view.items() if k!='snapshot_sha256'})
        or manifest.get('snapshot_sha256')!=view['snapshot_sha256'] or manifest.get('bundle_manifest_sha256')!=view.get('bundle_manifest_sha256')
        or view.get('source_snapshots')!=source_snapshots or view.get('scientific_validation') is not False
        or manifest.get('model_calls')!=0 or manifest.get('new_fits')!=0):
        raise ResearchError('EVIDENCE_CHANGED','Dossier files, snapshot or scientific source identities differ.')
    return {**files,'manifest.json':manifest_raw}
