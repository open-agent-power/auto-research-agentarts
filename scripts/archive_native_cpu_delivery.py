#!/usr/bin/env python3
"""Allowlisted native CPU evidence archive: inventory first, explicit create later."""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
import tempfile
import zipfile
from functools import lru_cache

REPO = Path(__file__).resolve().parents[1]
WORK = Path('/workspace/work')
OUTPUT = REPO/'runs/sprint-005-delivery'
CASES = REPO/'runs/g5-native-cases-20261113-01'
G6 = WORK/'g6-native-release-20261113-01'
G6_LIST = G6/'export-allowlist.json'
PINNED = ['8e8a206ed0b71479a6e774e36ed91fdb06e21c22', 'e638b5f3782d12a7b54bb9ede5596e5c4d9726cf']
REPO_TREES = [
    'runs/g5-native-cases-20261113-01', 'runs/g5-local-cpu-20261113-01',
    'runs/g5-native-run-reviews', 'runs/g5-native-core-review', 'runs/g5-native-driver-review',
    'runs/g5-native-final-review', 'runs/g5-native-independent-20261113-01',
    'runs/g5-native-integration-regression-20261113-01', 'runs/g5-native-retrieval-review-20261113-01',
    'runs/g5-native-algorithm-review-20261113-01', 'runs/g5-native-adapter-unit',
    'runs/g5-native-integration-unit', 'runs/g5-native-report-unit', 'docs/execution/g5-local',
    'runs/g5-native-ui-20261113-01', 'runs/g5-native-ui-20261113-02', 'runs/g5-native-ui-20261113-03',
    'runs/g5-native-ui-20261113-04', 'runs/g5-native-ui-20261113-05', 'runs/g6-native-final-review']
REPO_FILES = [
    'scripts/archive_native_cpu_delivery.py', 'scripts/run_native_cpu_cases.py',
    'scripts/verify_native_cpu_cases.py', 'scripts/verify_native_cpu_replay.py',
    'scripts/verify_native_release.py', 'scripts/run_cpu_transfer_benchmarks.py',
    'docs/execution/g6-local/native-independent-review.md', 'docs/execution/g6-local/native-release-preparation.md']
WORK_TREES = {
    'g5-cpu-inputs': 'sources/g5-original-inputs',
    'g5-native-retrieval-inputs': 'sources/native-retrieval-inputs',
    'g5-native-scheduling-inputs': 'sources/native-scheduling-inputs',
    'g5-native-host-prepare': 'evidence/retrieval-source-preparation',
    'g5-native-scheduling-host-prepare': 'evidence/scheduling-source-preparation',
    'g5-native-replay-20261113-01': 'evidence/replay', 'g5-native-ui': 'evidence/ui-helper'}
WORK_FILES = ['g5-native-source-mapping.json', 'g5-native-retrieval-preflight.json']
DENIED_COMPONENTS = {'.git', '.venv', 'venv', 'node_modules', '__pycache__', '.pytest_cache',
                     '.mypy_cache', '.cache', 'pip-cache', 'pipcache', 'reference-clones'}
DENIED_NAMES = {'.env', '.env.local', '.env.production', 'credentials.json', 'credentials',
                'secrets.json', 'id_rsa', 'id_ed25519', '.netrc', '.npmrc', '.pypirc'}
SECRET = re.compile(rb'(?:sk-(?:proj-)?[A-Za-z0-9_-]{24,}|AKIA[A-Z0-9]{16}|-----BEGIN [A-Z ]*PRIVATE KEY-----|https?://[^/\s:@]+:[^/\s@]+@)')
PLATFORM_ID = re.compile(rb'"(?:automation_id|platform_automation_id|cloud_automation_id)"\s*:\s*"[^"\s]{8,}"', re.I)
UI_DUPLICATES = {'input.json', 'report.json', 'report.md', 'report.pdf'}
SYNTHETIC_NEGATIVE_URL_TEST = {
    'a745310bb5aebbedf564e81a890a500383b38cfe':
        {'path': '.agent/skills/agentarts-china-builder/scripts/test_handoff_gate.py',
         'literal_sha256': 'c8236b24470762be7fea7c6d04dbb34a57385ec59fa0bb477c362424c0e82c1b'}}
SYNTHETIC_NEGATIVE_URL_TEST.update({
    'bc1db39d104a4600657497239ba29543b3f07d41':
        {'path': 'tests/test_model_client.py', 'literal_sha256': '093866188144b0216fb125431572e8ac2df8980dfeeb6ebeb3d9f3987d1e4c1d'},
    '5ef4771378435a34067ff7b854defe67986ac3b3':
        {'path': 'tests/test_paper_export.py', 'literal_sha256': 'd499b22fbec7784e9f8a65d8c1ce8c8eedae17b1c606782e60ad6a53931c5468'}})


def require(value, message):
    if not value:
        raise RuntimeError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def write(path, raw):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('xb') as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())


def save(path, value):
    write(path, canonical(value)+b'\n')


def read(path, maximum=64000000):
    path = Path(path)
    require(path.is_file() and not any(p.is_symlink() for p in (path, *path.parents)), 'Reject nonregular/symlink input')
    require(path.stat().st_size <= maximum, 'Input exceeds archive per-file read bound')
    with path.open('rb') as stream:
        raw = stream.read(maximum+1)
    require(len(raw) <= maximum, 'Captured input exceeds bound')
    return raw


def safe_name(name):
    path = PurePosixPath(name)
    require(not path.is_absolute() and '..' not in path.parts and '\\' not in name, 'Unsafe ZIP name')
    require(not any(part in DENIED_COMPONENTS or part in DENIED_NAMES for part in path.parts), 'Forbidden archive path')
    require(not ('.agent' in path.parts and 'autonomy' in path.parts), 'Autonomy control files are excluded')


@lru_cache(maxsize=1)
def local_automation_ids():
    # Read only to exclude known platform IDs; neither values nor control files are exported.
    path = REPO/'.agent/autonomy/automation.json'
    if not path.is_file():
        return ()
    value = json.loads(read(path, 64000)).get('automation_id')
    return (value.encode(),) if isinstance(value, str) and len(value) >= 8 else ()


def inspect_bytes(raw, label, *, blob=None, blob_path=None):
    for match in SECRET.finditer(raw):
        fixture = SYNTHETIC_NEGATIVE_URL_TEST.get(blob)
        known_test = (fixture and fixture['path'] == blob_path
                      and fixture['literal_sha256'] == sha(match.group()))
        require(known_test, 'Credential-shaped content rejected: '+label)
    require(not PLATFORM_ID.search(raw), 'Platform automation ID field rejected: '+label)
    require(not any(value in raw for value in local_automation_ids()), 'Known platform automation ID rejected: '+label)


def git(*args, cwd=REPO):
    return subprocess.run(['git', *args], cwd=cwd, check=True, capture_output=True, timeout=120).stdout


def scan_history(commit):
    # Audit all reachable object paths, not only the final tree; the bundle has full ancestors.
    for pin in PINNED:
        git('merge-base', '--is-ancestor', pin, commit)
    objects = git('rev-list', '--objects', commit).splitlines()
    blobs, total_bytes, commit_objects = 0, 0, 0
    for row in objects:
        parts = row.split(b' ', 1)
        oid = parts[0].decode('ascii')
        blob_path = parts[1].decode('utf-8') if len(parts) == 2 else None
        if blob_path is not None:
            inspect_bytes(blob_path.encode(), 'public Git object path')
            safe_name(blob_path)
        kind = git('cat-file', '-t', oid).strip()
        if kind in (b'blob', b'commit', b'tag'):
            raw = git('cat-file', kind.decode(), oid)
            inspect_bytes(raw, 'public Git object '+oid, blob=oid, blob_path=blob_path)
        if kind == b'blob':
            blobs += 1
            total_bytes += len(raw)
        elif kind in (b'commit', b'tag'):
            commit_objects += 1
    return {'commit': commit, 'reachable_objects': len(objects), 'blob_count': blobs,
            'blob_bytes': total_bytes, 'commit_tag_objects_scanned': commit_objects,
            'unclassified_secret_shapes_found': False, 'known_runtime_automation_values_excluded': len(local_automation_ids()),
            'classified_public_negative_fixture': SYNTHETIC_NEGATIVE_URL_TEST,
            'scope': 'Mechanical public-history path/content scan; no inference that missing patterns establish legal approval.'}


def entries(video_allowlist=None):
    selected, omitted = {}, []
    def add(path, archive_path, role):
        inspect_bytes(archive_path.encode(), 'archive entry path')
        inspect_bytes(str(path).encode(), 'archive entry source path')
        safe_name(archive_path)
        raw = read(path)
        inspect_bytes(raw, 'allowlisted file content')
        entry = {'path': archive_path, 'source_path': str(path), 'bytes': len(raw), 'sha256': sha(raw),
                 'mode': stat.S_IMODE(path.stat().st_mode), 'role': role}
        if archive_path in selected:
            require(all(selected[archive_path][key] == entry[key] for key in ('source_path', 'bytes', 'sha256', 'mode')),
                    'Archive path collision')
            return
        selected[archive_path] = entry
    for relative in REPO_TREES:
        root = REPO/relative
        require(root.is_dir(), 'Required evidence directory missing: '+relative)
        for path in sorted(root.rglob('*')):
            if path.is_file():
                if 'g5-native-ui-' in relative and path.name in UI_DUPLICATES:
                    omitted.append({'path': str(path.relative_to(REPO)),
                                    'reason': 'Duplicate downloaded original; SHA/download evidence retained, originals included in complete managed case reports.'})
                    continue
                add(path, 'repo/'+str(path.relative_to(REPO)), relative)
    for relative in REPO_FILES:
        add(REPO/relative, 'repo/'+relative, 'reviewed host/checker script')
    for relative, destination in WORK_TREES.items():
        root = WORK/relative
        require(root.is_dir(), 'Required source/evidence directory missing: '+relative)
        for path in sorted(root.rglob('*')):
            if path.is_file():
                add(path, destination+'/'+str(path.relative_to(root)), 'original source or preparation/replay evidence')
    for relative in WORK_FILES:
        add(WORK/relative, 'evidence/source-preparation/'+relative, 'source mapping/preflight')
    release_raw = read(G6_LIST)
    release = json.loads(release_raw)
    require(release['schema_version'] == 'g6-native-release-export-allowlist-v1' and release['source_commit'] == PINNED[1], 'Unsupported G6 allowlist')
    for value in release['files']:
        path = Path(value['path'])
        require(path.is_relative_to(G6) or path.is_relative_to(REPO/'docs/execution/g6-local')
                or path == REPO/'scripts/verify_native_release.py', 'G6 file is outside its explicit evidence roots')
        raw = read(path)
        require(len(raw) == value['bytes'] and sha(raw) == value['sha256'], 'G6 allowlist identity changed')
        archive_path = 'repo/'+str(path.relative_to(REPO)) if path.is_relative_to(REPO) else 'evidence/g6-release/'+str(path.relative_to(G6))
        add(path, archive_path, 'G6 exact export allowlist')
    add(G6_LIST, 'evidence/g6-release/export-allowlist.json', 'G6 export list')
    if video_allowlist is not None:
        listing_path = Path(video_allowlist).absolute()
        require(listing_path.is_relative_to(WORK) or listing_path.is_relative_to(REPO/'runs'), 'Video allowlist must be owned delivery evidence')
        video = json.loads(read(listing_path, 64000))
        require(video['schema_version'] == 'g5-native-demo-export-v1' and type(video['files']) is list, 'Unsupported demo allowlist')
        for value in video['files']:
            path = Path(value['path']).absolute()
            demo_doc = REPO/'docs/execution/g6-local/native-demo.md'
            require(path.is_relative_to(WORK) or path.is_relative_to(REPO/'runs') or path == demo_doc,
                    'Video entry outside declared evidence roots')
            require(path.suffix.lower() in ('.webm', '.mp4', '.json', '.md', '.py', '.log', '.txt', '.png'), 'Unsupported demo evidence suffix')
            raw = read(path)
            require(len(raw) == value['bytes'] and sha(raw) == value['sha256'], 'Video allowlist identity changed')
            if path == demo_doc:
                archive_path = 'repo/'+str(path.relative_to(REPO))
            else:
                relative = path.relative_to(WORK) if path.is_relative_to(WORK) else path.relative_to(REPO/'runs')
                archive_path = 'evidence/readonly-demo/'+str(relative)
            add(path, archive_path, 'root-supplied exact demo allowlist')
        add(listing_path, 'evidence/readonly-demo/export-allowlist.json', 'demo export allowlist')
    # Supply the raw old ledgers/data/control bytes required by the frozen protection map.
    by_source = {entry['source_path']: entry for entry in selected.values()}
    for name in protected():
        if name in by_source:
            continue
        path = Path(name)
        if path.is_relative_to(REPO):
            archive_path = 'repo/'+str(path.relative_to(REPO))
        else:
            require(path.is_relative_to(WORK), 'Protected original outside the two declared source roots')
            archive_path = 'sources/protected-work/'+str(path.relative_to(WORK))
        add(path, archive_path, 'frozen original protection: raw data/ledger/control')
    return sorted(selected.values(), key=lambda value: value['path']), omitted, sha(release_raw)


def protected():
    expected = {}
    for kind in ('retrieval', 'scheduling'):
        freeze = json.loads(read(CASES/kind/'freeze.json'))
        expected.update(freeze['protected'])
    require(len(expected) == 369, 'Unexpected old protected-file set')
    for name, identity in expected.items():
        raw = read(Path(name))
        require(len(raw) == identity['bytes'] and sha(raw) == identity['sha256'], 'Old protected evidence changed')
    # Re-enumerate the original tree roots too: additions/deletions must be visible.
    roots = json.loads(read(CASES/'retrieval/freeze.json'))['protected_tree_roots']
    original_tree_names = {name for name in expected if any(Path(name).is_relative_to(Path(root)) for root in roots)}
    actual_names = {str(path) for root in roots for path in Path(root).rglob('*') if path.is_file()}
    require(original_tree_names == actual_names, 'Old protected tree inventory changed')
    actual = {name: {'bytes': len(raw := read(Path(name))), 'sha256': sha(raw)} for name in expected}
    for path in sorted(CASES.rglob('*')):
        if path.is_file():
            raw = read(path)
            actual[str(path)] = {'bytes': len(raw), 'sha256': sha(raw)}
    return actual


def plan(args):
    current = git('rev-parse', 'HEAD').decode().strip()
    files, omitted, g6_sha = entries(args.video_allowlist)
    protect = protected()
    history = scan_history(current)
    inventory = {'schema_version': 'g5-native-delivery-inventory-v1', 'source_commit': current,
                 'fixed_source_commits': PINNED, 'files': files, 'omitted_duplicates': omitted,
                 'g6_allowlist_sha256': g6_sha, 'protected': protect, 'public_history_scan': history,
                 'video_allowlist_path': str(args.video_allowlist.absolute()) if args.video_allowlist else None,
                 'video_allowlist_sha256': sha(read(args.video_allowlist)) if args.video_allowlist else None,
                 'protected_original_archive_paths': {name: next(entry['path'] for entry in files if entry['source_path'] == name) for name in protect},
                 'file_count': len(files), 'uncompressed_file_bytes': sum(x['bytes'] for x in files),
                 'git_object_disk_bytes_estimate': int(git('rev-list', '--disk-usage', '--objects', current).strip()),
                 'generated_at_create': ['source/native-cpu-public-history.bundle', 'README.md', 'delivery-inventory.json'],
                 'excluded': ['.agent/autonomy', 'platform automation identifiers', 'credentials', 'virtual environments',
                              'node_modules', 'pip cache', 'reference clones', 'raw .git', 'duplicate UI downloads'],
                 'status': 'dry_run_only_no_archive_created',
                 'boundary': 'Offline source/evidence inspection and purpose-specific saved recovery evidence; not scientific refit reproduction, sealed execution or a full dependency mirror.'}
    inspect_bytes(canonical(inventory), 'generated inventory metadata')
    save(args.inventory, inventory)
    print(json.dumps({k: inventory[k] for k in ('status', 'source_commit', 'file_count', 'uncompressed_file_bytes', 'git_object_disk_bytes_estimate')}))


def bundle_checks(path, expected_commit):
    heads = git('bundle', 'list-heads', str(path)).decode().splitlines()
    require(heads == [expected_commit+' HEAD'], 'Bundle tip differs from the reviewed source commit')
    header = read(path).split(b'\n\n', 1)[0].splitlines()
    require(not any(line.startswith(b'-') for line in header), 'Bundle must have no external prerequisites')
    with tempfile.TemporaryDirectory(prefix='native-delivery-bundle-') as temporary:
        bare = Path(temporary)/'verify.git'
        git('init', '--bare', str(bare))
        output = git('bundle', 'verify', str(path), cwd=bare)
        checkout = Path(temporary)/'checkout'
        git('clone', '--quiet', '--no-checkout', str(path), str(checkout))
        for commit in PINNED:
            git('cat-file', '-e', commit+'^{commit}', cwd=checkout)
    return {'self_contained': True, 'git_bundle_verify': True, 'exact_bundle_tip': expected_commit,
            'exact_fixed_source_commits_available': PINNED,
            'verify_stdout': output.decode('utf-8', errors='replace')}


def verify_archive(path):
    with zipfile.ZipFile(path) as stream:
        require(stream.testzip() is None, 'ZIP CRC failure')
        names = stream.namelist()
        require(len(names) == len(set(names)), 'Duplicate ZIP member')
        manifest = json.loads(stream.read('archive-manifest.json'))
        require(set(names) == {entry['path'] for entry in manifest['entries']}|{'archive-manifest.json'}, 'ZIP/manifest set differs')
        for entry in manifest['entries']:
            safe_name(entry['path'])
            raw = stream.read(entry['path'])
            require(len(raw) == entry['bytes'] and sha(raw) == entry['sha256'], 'ZIP entry identity mismatch')
        with tempfile.TemporaryDirectory(prefix='native-delivery-check-') as temporary:
            bundle = Path(temporary)/'source.bundle'
            bundle.write_bytes(stream.read('source/native-cpu-public-history.bundle'))
            proof = bundle_checks(bundle, manifest['source_commit'])
    return {'status': 'verified', 'entries': len(manifest['entries']), 'zip_crc': 'all_passed',
            'entry_sha256_and_bytes': 'all_matched', 'manifest_members_one_to_one': True, 'bundle': proof}


def create(args):
    inventory_raw = read(args.inventory)
    inspect_bytes(inventory_raw, 'delivery inventory metadata')
    inventory = json.loads(inventory_raw)
    require(inventory['schema_version'] == 'g5-native-delivery-inventory-v1', 'Wrong inventory schema')
    current = git('rev-parse', 'HEAD').decode().strip()
    require(current == args.final_commit == inventory['source_commit'], 'Wait for root final committed source; regenerate final inventory first')
    git('diff', '--exit-code', current, '--', 'src', 'scripts', 'docs', 'frontend', 'pyproject.toml')
    git('ls-files', '--error-unmatch', 'scripts/archive_native_cpu_delivery.py')
    require(inventory.get('video_allowlist_path') and inventory.get('video_allowlist_sha256'), 'Wait for final read-only video allowlist')
    require(sha(read(Path(inventory['video_allowlist_path']))) == inventory['video_allowlist_sha256'], 'Video allowlist changed')
    files, omitted, g6_sha = entries(inventory['video_allowlist_path'])
    require(files == inventory['files'] and omitted == inventory['omitted_duplicates'] and g6_sha == inventory['g6_allowlist_sha256'], 'Final allowlist material changed')
    before = protected()
    require(before == inventory['protected'], 'Protection changed since final plan')
    scan_history(current)
    require(not OUTPUT.exists(), 'Fresh delivery directory required; never overwrite')
    OUTPUT.mkdir(parents=True)
    save(OUTPUT/'protected-before.json', before)
    bundle = OUTPUT/'native-cpu-public-history.bundle'
    git('bundle', 'create', str(bundle), 'HEAD')
    bundle_proof = bundle_checks(bundle, current)
    readme = ('# Native CPU evidence delivery\n\n'
              'Complete two native cases, known public citation/synthetic sources, independent saved checks, failures, recovery, UI and purpose-specific clean wheel evidence.\n'
              'Clone source/native-cpu-public-history.bundle locally; exact frozen research source is '+PINNED[0]+', presentation/release source '+PINNED[1]+'. Final documentation HEAD is '+current+'.\n'
              'Archive case declarations retain original absolute paths and budgets. delivery-inventory.json protected_original_archive_paths maps every original absolute protected path to its archive member; no declaration is silently rebased. Old raw cases, ledgers, data and actual frozen control bytes are supplied.\n'
              'Extraction does not authorize create/new native research or rewriting declarations. Existing attempt batches must never be run again. Existing-ID recovery requires the already-existing relocated DB and the pinned source/runtime, following replay/relocation protocols; never create at a vanished unmanaged-project root.\n'
              'Public SciFact/BEIR originals and separate license notices remain under sources and case input/report manifests. Synthetic jobs are own-generated; no new external data license is invented.\n'
              'UI duplicate downloaded files are excluded; download hashes and complete original reports remain in managed cases. Full omission list is in delivery-inventory.json.\n'
              'Credential files, .agent/autonomy, venv/cache/node_modules/reference clones and raw .git are excluded by explicit path rules. Contents and reachable public Git objects are scanned for the specified credential shapes and the known local platform automation ID. This mechanical check is not a universal secret-proof guarantee. Three public negative-URL test fixtures are classified by exact blob/path/literal SHA, not treated as runtime credentials.\n'
              'G5 original/relocated replay evidence records144 original-ID calls. G6 purpose-specific clean-wheel smoke records8 additional saved-ID calls. These are separate suites, not a combined single recovery test.\n'
              'This is not a dependency-wheel mirror, universal clean install, scientific refit reproduction, sealed environment or automatic method promotion. Development/API currency costs remain unknown.\n')
    payload = [(entry, read(Path(entry['source_path']))) for entry in files]
    for name, raw in [('source/native-cpu-public-history.bundle', read(bundle)), ('README.md', readme.encode()), ('delivery-inventory.json', inventory_raw)]:
        if name != 'source/native-cpu-public-history.bundle':
            inspect_bytes(raw, 'generated delivery metadata')
        payload.append(({'path': name, 'source_path': None, 'bytes': len(raw), 'sha256': sha(raw), 'mode': 0o644, 'role': 'generated delivery metadata/source'}, raw))
    manifest = {'schema_version': 'g5-native-delivery-manifest-v1', 'source_commit': current,
                'inventory_sha256': sha(inventory_raw), 'entries': [entry for entry, _ in payload], 'bundle_verification': bundle_proof}
    manifest_raw = canonical(manifest)+b'\n'
    inspect_bytes(manifest_raw, 'generated archive manifest metadata')
    archive = OUTPUT/'native-cpu-reproduction-evidence.zip'
    with zipfile.ZipFile(archive, 'x', compression=zipfile.ZIP_DEFLATED, compresslevel=6) as stream:
        for entry, raw in payload:
            require(len(raw) == entry['bytes'] and sha(raw) == entry['sha256'], 'Source changed before ZIP write')
            info = zipfile.ZipInfo(entry['path'], date_time=(2026, 11, 13, 0, 0, 0))
            info.create_system = 3
            info.external_attr = (stat.S_IFREG|entry['mode']) << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            stream.writestr(info, raw)
        stream.writestr('archive-manifest.json', manifest_raw)
    verification = verify_archive(archive)
    after = protected()
    save(OUTPUT/'protected-after.json', after)
    require(before == after, 'Old/case protection changed during archiving')
    require(entries(inventory['video_allowlist_path'])[0] == files, 'Allowlisted sources changed during archiving')
    save(OUTPUT/'archive-manifest.json', manifest)
    save(OUTPUT/'verification.json', verification)
    receipt = {'status': 'allowlisted_archive_created_and_verified', 'archive': str(archive),
               'archive_bytes': archive.stat().st_size, 'archive_sha256': sha(read(archive, 512000000)),
               'manifest_sha256': sha(read(OUTPUT/'archive-manifest.json')),
               'inventory_sha256': sha(inventory_raw), 'source_commit': current,
               'old_protected_file_count': 369, 'old_plus_native_case_file_count': len(before),
               'protected_unchanged': True, 'verification': verification}
    save(OUTPUT/'delivery-receipt.json', receipt)
    print(json.dumps(receipt))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_subparsers(dest='mode', required=True)
    dry = modes.add_parser('plan')
    dry.add_argument('--inventory', type=Path, required=True)
    dry.add_argument('--video-allowlist', type=Path)
    execute = modes.add_parser('create')
    execute.add_argument('--inventory', type=Path, required=True)
    execute.add_argument('--final-commit', required=True)
    check = modes.add_parser('verify')
    check.add_argument('--archive', type=Path, required=True)
    args = parser.parse_args()
    if args.mode == 'plan':
        plan(args)
    elif args.mode == 'create':
        create(args)
    else:
        print(json.dumps(verify_archive(args.archive)))


if __name__ == '__main__':
    main()
