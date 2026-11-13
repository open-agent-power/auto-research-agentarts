#!/usr/bin/env python3
"""Archive-only preparation and separately reviewed, existing-ID native recovery."""
import argparse
from contextlib import ExitStack
import hashlib
import importlib.abc
import importlib.machinery
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import unicodedata
import zipfile

REPO = Path('/workspace/auto-research-agentarts')
WORK = Path('/workspace/work')
ARCHIVE = REPO/'runs/sprint-005-delivery/native-cpu-reproduction-evidence.zip'
ARCHIVE_SHA = 'e320404532fe80fd085ec1dbe07cf6e1abda6d8212a00f8295baa3c9371a1a58'
MANIFEST_SHA = '6c35932e8a9170c868b89e198479b4c7b52670b366720bda39ee6e9ebf40f1e1'
PINS = {'final': 'e97c0a697ce641081b0a276f5dfa5d1a29762879',
        'science': '8e8a206ed0b71479a6e774e36ed91fdb06e21c22',
        'release': 'e638b5f3782d12a7b54bb9ede5596e5c4d9726cf'}
DEPS = WORK/'g6-native-release-20261113-01/venv'
PYTHON = DEPS/'bin/python'
CASE_PATH = 'repo/runs/g5-native-cases-20261113-01'
RELEASE = 'evidence/g6-release/release-attempt-02'
WHEEL = RELEASE+'/dist/agentarts_autoresearch-0.1.0-py3-none-any.whl'
WHEEL_SHA = '574a83edc7eadb7d338bb43facd5c84b423e8494598d2ac5aadd3633e9d65295'
STEPS = ('primary', 'audit', 'wait', 'report')
METHODS = {'retrieval': ['research.retrieval-fixed-pair', 'research.retrieval-saved-error-audit'],
           'scheduling': ['research.weighted-interval-fixed-pair', 'research.weighted-interval-saved-audit']}
sys.dont_write_bytecode = True


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def read(path, maximum=128*1024**2):
    path = Path(path)
    require(path.is_file() and not any(p.is_symlink() for p in (path, *path.parents)), 'Nonregular or linked input')
    require(path.stat().st_size <= maximum, 'Read size exceeds fixed cap')
    with path.open('rb') as handle:
        raw = handle.read(maximum+1)
    require(len(raw) <= maximum, 'Captured read exceeds cap')
    return raw


def parse(raw):
    def pairs(items):
        value = {}
        for key, item in items:
            require(key not in value, 'Duplicate JSON key')
            value[key] = item
        return value
    def constant(_):
        raise ValueError('Nonfinite JSON')
    value = json.loads(raw.decode('utf-8'), object_pairs_hook=pairs, parse_constant=constant)
    canonical(value)  # Also rejects finite-token float overflow to infinity.
    return value


def js(path):
    return parse(read(path))


def write(path, raw):
    with path.open('xb') as handle:
        handle.write(raw)
        handle.flush()
        os.fsync(handle.fileno())


def save(path, value):
    write(path, canonical(value)+b'\n')


def safe_name(name):
    require(type(name) is str and name and '\x00' not in name and '\\' not in name,
            'Invalid ZIP member name')
    parts = name.split('/')
    require(not PurePosixPath(name).is_absolute() and all(part not in ('', '.', '..') and ':' not in part for part in parts),
            'ZIP member traversal or alternate path syntax')
    return name


def validate_zip(raw, *, expected_sha=ARCHIVE_SHA):
    require(len(raw) <= 128*1024**2 and sha(raw) == expected_sha, 'Archive identity differs')
    with zipfile.ZipFile(io.BytesIO(raw)) as stream:
        infos = stream.infolist()
        require(1 <= len(infos) <= 1200, 'Archive member count exceeds cap')
        names, normalized = set(), set()
        total = 0
        for info in infos:
            safe_name(info.filename)
            folded = unicodedata.normalize('NFC', info.filename).casefold()
            require(info.filename not in names and folded not in normalized, 'Duplicate/colliding ZIP member')
            names.add(info.filename)
            normalized.add(folded)
            kind = stat.S_IFMT(info.external_attr >> 16)
            require(not info.is_dir() and kind in (0, stat.S_IFREG) and not (info.flag_bits & 1),
                    'ZIP links, special files, directories or encryption are forbidden')
            require(0 <= info.file_size <= 32*1024**2, 'Archive per-file size cap')
            total += info.file_size
        require(total <= 256*1024**2 and 'archive-manifest.json' in names, 'Archive total size/manifest constraint')
        manifest = parse(stream.read('archive-manifest.json'))
        require(manifest['schema_version'] == 'g5-native-delivery-manifest-v1' and manifest['source_commit'] == PINS['final'],
                'Wrong delivery manifest identity')
        expected = {}
        for entry in manifest['entries']:
            name = safe_name(entry['path'])
            require(name not in expected and type(entry['bytes']) is int and 0 <= entry['bytes'] <= 32*1024**2
                    and type(entry['sha256']) is str and re.fullmatch('[0-9a-f]{64}', entry['sha256']),
                    'Invalid or duplicate manifest member')
            expected[name] = entry
        require(names == set(expected)|{'archive-manifest.json'}, 'ZIP/manifest membership mismatch')
        identities = {}
        for info in infos:
            data = stream.read(info)  # Full reads also verify the member CRC.
            identity = {'bytes': len(data), 'sha256': sha(data)}
            if info.filename != 'archive-manifest.json':
                entry = expected[info.filename]
                require(identity == {key: entry[key] for key in ('bytes', 'sha256')}, 'Archive member SHA/size mismatch')
            identities[info.filename] = identity
        require(stream.testzip() is None, 'ZIP CRC validation failed')
    return manifest, identities


def tree(root):
    result = {}
    for path in sorted(root.rglob('*')):
        require(not path.is_symlink(), 'Linked storage is forbidden')
        if path.is_file():
            raw = read(path)
            result[str(path.relative_to(root))] = {'sha256': sha(raw), 'bytes': len(raw)}
    return result


def validate_root(path):
    root = Path(path).absolute()
    require('..' not in root.parts and root.parent == WORK and re.fullmatch(r'g6-archive-reopen-[A-Za-z0-9_.-]+', root.name),
            'Use a new /workspace/work/g6-archive-reopen-<unique> root')
    require(not any(p.is_symlink() for p in (root, *root.parents)), 'Scratch path cannot have symlink ancestors')
    return root


def package_tree(root):
    result = {}
    package = root/'autoresearch'
    for path in sorted(package.rglob('*')):
        relative = path.relative_to(package)
        if path.is_file() and (path.suffix == '.py' or
                relative.parts[0] == 'data' and path.name.endswith(('.json.gz', '.md')) or
                relative.parts[0] == 'web' and path.suffix in ('.html', '.css', '.js', '.txt')):
            result['autoresearch/'+str(relative)] = sha(read(path))
    return result


def command(argv, *, cwd, root, name):
    environment = {key: value for key, value in os.environ.items() if not key.startswith(('PIP_', 'PYTHON'))}
    environment.update(PYTHONDONTWRITEBYTECODE='1', PIP_NO_INDEX='1', PIP_NO_CACHE_DIR='1',
                       PIP_DISABLE_PIP_VERSION_CHECK='1', PIP_CONFIG_FILE=os.devnull,
                       OMP_NUM_THREADS='1', OPENBLAS_NUM_THREADS='1', MKL_NUM_THREADS='1', NUMEXPR_NUM_THREADS='1')
    save(root/(name+'-command.json'), {'argv': list(map(str, argv)), 'cwd': str(cwd), 'network_dependency_install': False})
    result = subprocess.run(list(map(str, argv)), cwd=cwd, env=environment, check=False,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=180)
    write(root/(name+'.log'), result.stdout)
    require(result.returncode == 0, 'Fixed preparation command failed: '+name)
    return result.stdout


def prepare(args):
    root = validate_root(args.root)
    require(not root.exists(), 'Never overwrite a previous preparation')
    archive_raw = read(args.archive)
    manifest, identities = validate_zip(archive_raw)  # Every member passes before any member is written.
    require('include-system-site-packages = false' in read(DEPS/'pyvenv.cfg').decode(), 'External clean dependency environment missing')
    root.mkdir()
    save(root/'archive-validation.json', {'archive_sha256': sha(archive_raw), 'archive_bytes': len(archive_raw),
                                        'members': len(identities), 'zip_crc': 'all_passed', 'manifest': 'all_members_sha_size_matched'})
    write(root/'input.zip', archive_raw)
    payload = root/'payload'
    payload.mkdir()
    try:
        with zipfile.ZipFile(io.BytesIO(archive_raw)) as stream:
            for info in stream.infolist():
                target = payload.joinpath(*safe_name(info.filename).split('/'))
                target.parent.mkdir(parents=True, exist_ok=True)
                write(target, stream.read(info))
                target.chmod((info.external_attr >> 16) & 0o777 or 0o600)
        require(tree(payload) == identities, 'Extracted payload differs from captured archive')
        bundle = payload/'source/native-cpu-public-history.bundle'
        heads = command(['git', 'bundle', 'list-heads', bundle], cwd=root, root=root, name='bundle-heads').decode().splitlines()
        require(heads == [PINS['final']+' HEAD'], 'Bundle advertised tip differs')
        sources = {}
        for label, pin in PINS.items():
            checkout = root/(label+'-source')
            command(['git', 'clone', '--quiet', '--no-checkout', bundle, checkout], cwd=root, root=root, name=label+'-clone')
            command(['git', '-C', checkout, 'bundle', 'verify', bundle], cwd=root, root=root, name=label+'-bundle-verify')
            command(['git', '-C', checkout, 'checkout', '--detach', pin], cwd=root, root=root, name=label+'-checkout')
            actual = command(['git', '-C', checkout, 'rev-parse', 'HEAD'], cwd=root, root=root, name=label+'-head').decode().strip()
            require(actual == pin, 'Cloned source pin differs')
            require(not command(['git', '-C', checkout, 'status', '--porcelain'], cwd=root, root=root, name=label+'-clean'), 'Cloned source is dirty')
            sources[label] = {'commit': pin, 'path': str(checkout)}
        cases = payload/CASE_PATH
        for kind in METHODS:
            frozen = js(cases/kind/'freeze.json')
            require(frozen['code_commit'] == PINS['science'], 'Scientific case source differs')
            for relative, identity in frozen['code_files'].items():
                path = root/'science-source'/safe_name(relative)
                raw = read(path)
                require({'bytes': len(raw), 'sha256': sha(raw)} == identity, 'Frozen scientific source file differs')
        expected = js(payload/(RELEASE+'/package-files.json'))
        require(type(expected) is dict and len(expected) == 177 and package_tree(root/'release-source/src') == expected,
                'Archived release source/package identity differs')
        wheel = payload/WHEEL
        require(sha(read(wheel)) == WHEEL_SHA, 'Archive wheel differs from exact release')
        with zipfile.ZipFile(wheel) as stream:
            require(not any(name.endswith('.pth') for name in stream.namelist()), 'No executable path hooks allowed')
            wheel_files = {name: sha(stream.read(name)) for name in stream.namelist() if name.startswith('autoresearch/') and not name.endswith('/')}
        require(wheel_files == expected, 'Archive wheel package differs from source')
        target = root/'target'
        command([PYTHON, '-I', '-m', 'pip', 'install', '--no-index', '--no-deps', '--no-compile',
                 '--no-cache-dir', '--ignore-installed', '--target', target, '--report', root/'target-install.json', wheel],
                cwd=root, root=root, name='install-archive-wheel-target')
        require(package_tree(target) == expected, 'Fresh target package differs from archived source/wheel')
        require(not list(target.rglob('__pycache__')), 'No bytecode side effects expected')
        helper_raw = read(Path(__file__))
        write(root/'host-helper.py', helper_raw)
        prepared = {'schema_version': 'g6-native-archive-reopen-prepared-v1', 'status': 'prepared_not_replayed',
                    'root': str(root), 'archive_original_path': str(Path(args.archive).absolute()),
                    'archive_sha256': sha(archive_raw), 'archive_bytes': len(archive_raw),
                    'payload_files': identities, 'archive_manifest_sha256': identities['archive-manifest.json']['sha256'],
                    'sources': sources, 'wheel_sha256': WHEEL_SHA, 'package_files': expected,
                    'target_tree': tree(target),
                    'helper_sha256': sha(helper_raw), 'dependency_environment': str(DEPS),
                    'dependency_environment_reused': True, 'dependencies_installed_from_archive': False,
                    'scope': 'Archive supplies source/cases/requests/reports/licenses and wheel; existing clean1.8 dependency environment is external. Not offline dependency installation, scientific refit or full G6.'}
        save(root/'prepared.json', prepared)
        print(json.dumps({'status': prepared['status'], 'prepared_sha256': sha(read(root/'prepared.json')), 'members': len(identities), 'package_files': 177}))
    except BaseException as error:
        save(root/'prepare-error.json', {'type': type(error).__name__, 'message': str(error), 'no_research_replay': True})
        raise


def normalize(value):
    if type(value) is dict:
        return {key: normalize(item) for key, item in value.items() if not (key == 'replayed' and type(item) is bool)}
    if type(value) is list:
        return [normalize(item) for item in value]
    return value


def check_prepared(root):
    raw = read(root/'prepared.json')
    prepared = parse(raw)
    require(prepared['schema_version'] == 'g6-native-archive-reopen-prepared-v1' and prepared['root'] == str(root), 'Prepared root differs')
    require(prepared['archive_sha256'] == ARCHIVE_SHA and prepared['wheel_sha256'] == WHEEL_SHA
            and prepared['dependency_environment'] == str(DEPS), 'Fixed archive/dependency identities differ')
    require(sha(read(root/'host-helper.py')) == prepared['helper_sha256'], 'Reviewed helper changed')
    require(sha(read(root/'input.zip')) == ARCHIVE_SHA, 'Captured input ZIP changed')
    manifest_raw = read(root/'payload/archive-manifest.json')
    require(sha(manifest_raw) == MANIFEST_SHA, 'Archive manifest identity differs')
    manifest = parse(manifest_raw)
    declared = {entry['path']: {key: entry[key] for key in ('bytes', 'sha256')} for entry in manifest['entries']}
    declared['archive-manifest.json'] = {'bytes': len(manifest_raw), 'sha256': MANIFEST_SHA}
    require(prepared['payload_files'] == declared, 'Prepared payload index is not the fixed archive manifest')
    require(tree(root/'payload') == prepared['payload_files'] and tree(root/'target') == prepared['target_tree']
            and package_tree(root/'target') == prepared['package_files'], 'Prepared source material changed')
    require(prepared['package_files'] == js(root/'payload'/(RELEASE+'/package-files.json'))
            and len(prepared['package_files']) == 177, 'Package manifest is not the archived release manifest')
    return raw, prepared


def recover(args):
    root = validate_root(args.root)
    prepared_raw, prepared = check_prepared(root)
    require(sha(read(Path(__file__))) == prepared['helper_sha256'], 'Host helper differs from reviewed prepared helper')
    review_raw = read(args.review, 64000)
    review = parse(review_raw)
    require(set(review) == {'schema_version', 'status', 'root', 'prepared_sha256', 'helper_sha256', 'reviewer', 'limitations'}
            and review['schema_version'] == 'g6-native-archive-reopen-review-v1' and review['status'] == 'approved'
            and review['root'] == str(root) and review['prepared_sha256'] == sha(prepared_raw)
            and review['helper_sha256'] == prepared['helper_sha256'] and bool(review['reviewer']), 'New exact recovery review is required')
    archived = root/'independent-review.json'
    if archived.exists():
        require(read(archived) == review_raw, 'Archived review differs')
    else:
        write(archived, review_raw)
    save(root/'attempt.json', {'schema_version': 'g6-native-archive-reopen-attempt-v1', 'status': 'running',
                              'prepared_sha256': sha(prepared_raw), 'review_sha256': sha(review_raw), 'automatic_retry': False})
    argv = [PYTHON, '-I', '-B', root/'host-helper.py', '_recover', '--root', root]
    try:
        command(argv, cwd=root, root=root, name='recovery-subprocess')
        result = js(root/'recovery.json')
        require(result['status'] == 'saved_archive_recovery_verified', 'Recovery did not pass')
        require(sha(read(Path(prepared['archive_original_path']))) == ARCHIVE_SHA, 'Original ZIP changed')
        save(root/'attempt-final.json', {'status': 'completed', 'original_archive_unchanged': True,
                                       'recovery_sha256': sha(read(root/'recovery.json')), 'automatic_retry': False})
        print(json.dumps({'status': 'completed', 'recovery_sha256': sha(read(root/'recovery.json')), 'saved_replays': result['saved_replays']}))
    except BaseException as error:
        save(root/'attempt-final.json', {'status': 'unknown_preserve_no_retry', 'type': type(error).__name__,
                                        'message': str(error), 'automatic_retry': False})
        raise


def recovery_child(root):
    import builtins
    import socket
    import sqlite3
    from urllib.parse import unquote
    from unittest.mock import patch
    require(Path(__file__).absolute() == root/'host-helper.py' and Path(sys.prefix).resolve() == DEPS.resolve(), 'Use copied helper and explicit external clean venv')
    prepared_raw, prepared = check_prepared(root)
    attempt = js(root/'attempt.json')
    require(attempt['prepared_sha256'] == sha(prepared_raw) and attempt['review_sha256'] == sha(read(root/'independent-review.json')), 'Original approved attempt differs')
    require(not any(name == 'autoresearch' or name.startswith('autoresearch.') for name in sys.modules), 'No prior product import allowed')
    payload, target = root/'payload', root/'target'
    before = tree(payload)
    guards = {name: 0 for name in ('original_repository_case_packet_or_product_storage', 'network_or_subprocess',
                                  'fit', 'new_compute_create_export_or_model')}
    accesses, imports, records = set(), {}, []
    def deny(name):
        def fail(*args, **kwargs):
            guards[name] = guards.get(name, 0)+1
            raise AssertionError('Archive recovery forbids '+name)
        return fail
    def storage(value):
        if isinstance(value, int):
            return
        text = os.fsdecode(value)
        if text.startswith('file:'):
            text = unquote(text[5:].split('?', 1)[0])
        if text == ':memory:':
            return
        path = Path(os.path.realpath(text))
        old_product = any(path.is_relative_to(site/'autoresearch') or
                          path.is_relative_to(site/'agentarts_autoresearch-0.1.0.dist-info') for site in (DEPS/'lib').glob('python*/site-packages'))
        if path.is_relative_to(REPO) or old_product or (path.is_relative_to(WORK) and not path.is_relative_to(root) and not path.is_relative_to(DEPS)):
            return deny('original_repository_case_packet_or_product_storage')()
        if path.is_relative_to(payload/CASE_PATH):
            accesses.add(str(path.relative_to(payload)))
    actual_open, actual_path_open, actual_os_open, actual_connect = builtins.open, Path.open, os.open, sqlite3.connect
    def guarded_open(file, *args, **kwargs):
        storage(file); return actual_open(file, *args, **kwargs)
    def guarded_path_open(path, *args, **kwargs):
        storage(path); return actual_path_open(path, *args, **kwargs)
    def guarded_os_open(path, *args, **kwargs):
        storage(path); return actual_os_open(path, *args, **kwargs)
    def guarded_connect(database, *args, **kwargs):
        storage(database); return actual_connect(database, *args, **kwargs)
    class ProductOrigin(importlib.abc.MetaPathFinder):
        def find_spec(self, fullname, path=None, target_module=None):
            if fullname != 'autoresearch' and not fullname.startswith('autoresearch.'):
                return None
            spec = importlib.machinery.PathFinder.find_spec(fullname, path)
            require(spec is not None and spec.origin and Path(spec.origin).resolve().is_relative_to(target/'autoresearch'), 'Product import attempted fallback outside archive target')
            imports[fullname] = spec.origin
            return spec
    finder = ProductOrigin()
    sys.path.insert(0, str(target))
    sys.meta_path.insert(0, finder)
    try:
        with ExitStack() as guard:
            for module, name, function in ((builtins, 'open', guarded_open), (Path, 'open', guarded_path_open),
                                           (os, 'open', guarded_os_open), (sqlite3, 'connect', guarded_connect)):
                guard.enter_context(patch.object(module, name, new=function))
            for module, names in ((socket.socket, ('connect', 'connect_ex', 'sendto')),
                                  (socket, ('create_connection', 'getaddrinfo')), (subprocess, ('Popen',))):
                for name in names:
                    guard.enter_context(patch.object(module, name, side_effect=deny('network_or_subprocess')))
            from sklearn.linear_model import Ridge
            from sklearn.preprocessing import StandardScaler
            guard.enter_context(patch.object(Ridge, 'fit', side_effect=deny('fit')))
            guard.enter_context(patch.object(StandardScaler, 'fit', side_effect=deny('fit')))
            from autoresearch import retrieval_adapter, retrieval_lexical, scheduling_adapter, scheduling_kernel
            from autoresearch import research_project, method_registry, source_evidence_adapter, project_report
            from autoresearch.local_workbench import LocalWorkbench
            from autoresearch.model_client import ChatClient
            from autoresearch.host_model_selection import HostModelSelection
            for module, names in ((retrieval_lexical, ('tokens', 'build_index', 'retrieve', 'metrics')),
                                  (scheduling_kernel, ('schedule', 'brute_force', 'jobs_for')),
                                  (retrieval_adapter, ('execute',)), (scheduling_adapter, ('execute',)),
                                  (retrieval_adapter.AUDIT, ('execute_saved',)), (scheduling_adapter.AUDIT, ('execute_saved',)),
                                  (research_project.ResearchProject, ('create',)), (LocalWorkbench, ('create',)),
                                  (source_evidence_adapter, ('execute',)), (project_report, ('collect_report', 'export_report', '_pdf', '_markdown')),
                                  (ChatClient, ('complete',)), (HostModelSelection, ('request',)),
                                  (scheduling_adapter.time, ('perf_counter',))):
                for name in names:
                    guard.enter_context(patch.object(module, name, side_effect=deny('new_compute_create_export_or_model')))
            results = {}
            for kind, methods in METHODS.items():
                case = payload/CASE_PATH/kind
                frozen, expected, result, relocation = (js(case/name) for name in ('freeze.json', 'final-project-status.json', 'result.json', 'project-relocation.json'))
                original_manager = Path(frozen['output_root'])/'manager'
                relative_project = Path(relocation['relocated_project_root']).relative_to(original_manager)
                manager_root = case/'manager'
                require((manager_root/'workbench.sqlite').is_file() and (manager_root/relative_project/'project.sqlite').is_file(), 'Existing archive databases required')
                manager = LocalWorkbench(manager_root)
                project, report = manager.binding()
                state = project.status()
                require(project.root == manager_root/relative_project and state == expected, 'Reopened project state differs from archive')
                require(state['id'] == result['project_id'] == relocation['project_id']
                        and state['run_id'] == expected['run_id'], 'Saved project/run identity differs')
                require(state['code_identity'] == research_project.code_identity() == frozen['project_code_identity']
                        and method_registry.runtime_dependencies() == frozen['runtime_dependencies'], 'Archived package/dependency identity differs')
                require(state['research_status'] == 'waiting' and len(state['plan_revisions']) == 3 and len(state['actions']) == 2 and not state['evidence_actions'], 'Wrong saved lifecycle')
                budget = state['budget']
                require(budget == result['budget'] and budget['local_tool_call_limit'] == budget['local_tool_calls_used'] == 2
                        and all(budget[key] == 0 for key in ('local_tool_calls_reserved', 'fit_limit', 'fit_attempts_used', 'fits_reserved', 'new_fits',
                            'new_model_requests', 'model_requests_reserved', 'evidence_read_limit', 'evidence_reads_used', 'evidence_reads_reserved')), 'Budget differs')
                require(project._source(state)['snapshot_sha256'] == frozen['snapshot_sha256'] and state['source_scope'] == frozen['scope'], 'Source scope/snapshot differs')
                first, second = state['actions']
                require([a['command'] for a in state['actions']] == methods and all(a['status'] == 'completed' for a in state['actions'])
                        and second['parameters'] == {'based_on_action_id': first['id'], 'based_on_result_sha256': first['result_sha256']}, 'Saved ancestry differs')
                parents = {p['request_id']: p for p in state['controller_requests']}
                require(all(p['status'] not in ('unknown', 'prepared', 'running') for p in parents.values()), 'Unknown original request: preserve its original ID; no dispatch')
                for step, action in (('primary', first), ('audit', second), ('wait', None)):
                    context = js(case/'steps'/(step+'-context.json'))
                    body = js(case/'steps'/(step+'-request.json'))['body']
                    parent = parents[body['request_id']]
                    require(parent['selection_context'] == context and parent['request']['proposal'] == body['proposal']
                            and context['context_sha256'] == sha(canonical({k:v for k,v in context.items() if k != 'context_sha256'}))
                            and body['proposal']['context_sha256'] == context['context_sha256'], 'Saved selection context differs')
                    if action is not None:
                        require(parent['child_request_id'] == action['request_id'], 'Saved parent/child ancestry differs')
                with sqlite3.connect((manager_root/'workbench.sqlite').as_uri()+'?mode=ro&immutable=1', uri=True) as db:
                    accepted = {row[0]: row[1] for row in db.execute('SELECT id,digest FROM requests')}
                for step in STEPS:
                    request = js(case/'steps'/(step+'-request.json'))
                    wanted = js(case/'steps'/(step+'-result.json'))['result']
                    body = request['body']
                    require(body == request['replay_body'] and accepted.get(body['request_id']) == sha(canonical(body)), 'Only existing exact IDs/bodies may be replayed')
                    require(request['command'] == ('LocalWorkbench.export' if step == 'report' else 'LocalWorkbench.advance'), 'Unapproved saved request')
                    response = (manager.export if step == 'report' else manager.advance)(body)
                    require(response.get('replayed') is True and normalize(response) == normalize(wanted), 'Saved response mismatch')
                    require(project.status() == state, 'Recovery changed saved state/budget')
                    records.append({'case': kind, 'step': step, 'request_id': body['request_id'], 'response': response})
                manifest = js(report/'manifest.json')
                require(manifest == result['report']['manifest'] and set(manifest['files']) == {'input.json', 'report.json', 'report.md', 'report.pdf'}, 'Report manifest differs')
                for name, identity in manifest['files'].items():
                    raw = read(report/name)
                    require(len(raw) == identity['bytes'] and sha(raw) == identity['sha256'], 'Original report attachment differs')
                results[kind] = {'project_id': state['id'], 'run_id': state['run_id'], 'snapshot_ref': state['snapshot_ref'],
                                 'source_scope': state['source_scope'], 'budget': budget, 'existing_manager': str(manager_root),
                                 'original_path_metadata_unchanged': True, 'report_manifest': manifest, 'saved_replays': 4}
            require(not any(guards.values()) and tree(payload) == before, 'Forbidden operation or changed archive payload')
            require(tree(target) == prepared['target_tree'] and package_tree(target) == prepared['package_files'], 'Archive package bytes changed')
            origins = {name: str(Path(module.__file__).resolve()) for name, module in sys.modules.items()
                       if (name == 'autoresearch' or name.startswith('autoresearch.')) and getattr(module, '__file__', None)}
            require(origins and all(Path(path).is_relative_to(target/'autoresearch') for path in origins.values()), 'Product module origin outside new archive target')
        save(root/'recovery.json', {'schema_version': 'g6-native-archive-recovery-v1', 'status': 'saved_archive_recovery_verified',
                                   'archive_sha256': ARCHIVE_SHA, 'saved_replays': len(records), 'cases': results,
                                   'records': records, 'module_origins': origins, 'import_finder_origins': imports,
                                   'package_file_count': 177, 'package_sha256_matches_archive_wheel_and_git': True,
                                   'guard_call_counts': guards, 'actual_archive_case_accesses': sorted(accesses),
                                   'archive_payload_unchanged': tree(payload) == before,
                                   'dependency_environment': str(DEPS), 'dependencies_supplied_by_zip': False,
                                   'new_scientific_compute_fit_model_source_network_or_report': 0,
                                   'limitations': 'Same-host cooperative file/import/API guards, not OS isolation; existing external clean dependencies reused; saved recovery is not scientific refit reproduction or full G6.'})
    except BaseException as error:
        save(root/'recovery-error.json', {'type': type(error).__name__, 'message': str(error), 'guards': guards,
                                         'completed_saved_replays': len(records), 'automatic_retry': False})
        raise
    finally:
        sys.meta_path.remove(finder)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_subparsers(dest='mode', required=True)
    prep = modes.add_parser('prepare')
    prep.add_argument('--archive', type=Path, default=ARCHIVE)
    prep.add_argument('--root', type=Path, required=True)
    run = modes.add_parser('recover')
    run.add_argument('--root', type=Path, required=True)
    run.add_argument('--review', type=Path, required=True)
    child = modes.add_parser('_recover')
    child.add_argument('--root', type=Path, required=True)
    args = parser.parse_args()
    if args.mode == 'prepare':
        prepare(args)
    elif args.mode == 'recover':
        recover(args)
    else:
        recovery_child(validate_root(args.root))


if __name__ == '__main__':
    main()
