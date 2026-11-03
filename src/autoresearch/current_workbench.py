"""Explicit local pointer to one sealed read-only workbench, never latest-by-time."""
import hashlib
import json
import os
from pathlib import Path
import re
import uuid

from . import snapshot_viewer as viewer


DEFAULT_PORT = 18784
PRODUCT_ROOT = Path(__file__).absolute().parents[2]
SCHEMA = 'p02-current-workbench-v1'


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _root(product_root):
    root = Path(product_root).absolute() if product_root is not None else PRODUCT_ROOT
    viewer._no_redirect(root)
    return root


def _profile(root):
    path = root / '.agent' / 'current-workbench.json'
    viewer._no_redirect(path)
    return path


def _snapshots(manifest):
    values = {key: value for key, value in manifest.items() if key.endswith('_snapshot_sha256')}
    _valid_snapshots(values)
    return values


def _valid_snapshots(values):
    _require(type(values) is dict and {'baseline_snapshot_sha256', 'iteration_snapshot_sha256'} <= set(values)
             and all(type(key) is str and re.fullmatch(r'[a-z_]+_snapshot_sha256', key)
                     and ((key == 'iteration_snapshot_sha256' and value is None) or viewer._hash(value))
                     for key, value in values.items()), 'Malformed pinned snapshot identifiers.')


def _load_selection(root):
    path = _profile(root)
    _require(path.exists(), 'No workbench selected. Run workbench.py select --bundle <sealed-directory>.')
    value = viewer._json(viewer._read(path, 20_000))
    _require(type(value) is dict and set(value) == {'schema_version', 'bundle_directory', 'manifest_sha256',
                                                   'snapshots', 'label', 'scientific_validation'}
             and value['schema_version'] == SCHEMA and viewer._hash(value['manifest_sha256'])
             and type(value['bundle_directory']) is str and Path(value['bundle_directory']).is_absolute()
             and type(value['label']) is str and 1 <= len(value['label']) <= 200
             and value['scientific_validation'] is False, 'Malformed current workbench selection.')
    _valid_snapshots(value['snapshots'])
    viewer._no_redirect(Path(value['bundle_directory']))
    return value


def _pinned(selection):
    bundle = Path(selection['bundle_directory'])
    raw = viewer._read(bundle / 'bundle-manifest.json', viewer.MAX_MANIFEST)
    _require(hashlib.sha256(raw).hexdigest() == selection['manifest_sha256'],
             'Selected bundle manifest changed. Preserve it and explicitly select a verified sealed bundle.')
    manifest = viewer._json(raw)
    _require(type(manifest) is dict and manifest.get('schema_version') == 'p02-handoff-bundle-v1'
             and _snapshots(manifest) == selection['snapshots'], 'Pinned manifest snapshots differ from the local selection.')
    return raw


def select_bundle(bundle, *, label=None, product_root=None):
    """Full validation, then atomic local pointer save. Relative paths use product root."""
    root = _root(product_root); selected = Path(bundle)
    if not selected.is_absolute(): selected = root / selected
    selected = selected.absolute(); viewer._no_redirect(selected)
    before = viewer._read(selected / 'bundle-manifest.json', viewer.MAX_MANIFEST)
    viewer.load_bundle(selected)
    after = viewer._read(selected / 'bundle-manifest.json', viewer.MAX_MANIFEST)
    _require(before == after, 'Bundle manifest changed during full validation.')
    label = selected.name if label is None else label
    _require(type(label) is str and 1 <= len(label.strip()) <= 200
             and not any(ord(char) < 32 for char in label), 'Use a plain display label of 1..200 characters; labels do not approve science.')
    value = {'schema_version': SCHEMA, 'bundle_directory': str(selected),
             'manifest_sha256': hashlib.sha256(after).hexdigest(),
             'snapshots': _snapshots(viewer._json(after)), 'label': label, 'scientific_validation': False}
    path = _profile(root)
    if path.exists(): _load_selection(root)  # Refuse malformed or redirected existing profiles.
    path.parent.mkdir(parents=True, exist_ok=True); viewer._no_redirect(path.parent)
    temporary = path.with_name('.current-workbench-' + uuid.uuid4().hex + '.tmp')
    try:
        with temporary.open('x', encoding='utf-8') as stream:
            json.dump(value, stream, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)
            stream.write('\n'); stream.flush(); os.fsync(stream.fileno())
        viewer._no_redirect(path)
        os.replace(temporary, path)
    finally:
        if temporary.exists(): temporary.unlink()
    return {'selection': value, 'verification': 'full_sealed_bundle_check', 'research_artifacts_changed': False,
            'model_calls': 0, 'new_fits': 0}


def status(*, product_root=None, port=DEFAULT_PORT):
    """Cheap manifest check only; neither starts nor probes a server."""
    _require(type(port) is int and 1 <= port <= 65535, 'Port must be 1..65535.')
    selection = _load_selection(_root(product_root)); _pinned(selection)
    return {'selection': selection, 'local_url': 'http://127.0.0.1:%d/' % port,
            'server_status': 'not_checked', 'verification': 'manifest_identity_only_not_full_file_check',
            'scientific_validation': False, 'model_calls': 0, 'new_fits': 0}


def create_current_server(*, product_root=None, port=DEFAULT_PORT):
    """Full viewer validation of the exact pin; caller owns serving and closing."""
    _require(type(port) is int and 1 <= port <= 65535, 'Port must be 1..65535; no automatic port changes.')
    root = _root(product_root); selection = _load_selection(root); before = _pinned(selection)
    server = viewer.create_server(selection['bundle_directory'], port)
    try:
        _require(_load_selection(root) == selection and _pinned(selection) == before,
                 'Selection or manifest changed while creating the server.')
    except Exception:
        server.server_close()
        raise
    return server
