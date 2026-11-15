"""Fixed retrospective validation-only magnitude audit; default does not open cases."""
import argparse
import builtins
from contextlib import ExitStack
import hashlib
import io
import json
import math
import os
from pathlib import Path
import platform
import socket
import stat
import subprocess
import sys
import tempfile
import types
from unittest.mock import patch

PROTOCOL_SHA = 'bef2c9e49cb2323be5d16918703beb09b09aac19271186e059554e5685da1e70'
EPSILON = 1e-12


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_s075_source(path, expected_sha):
    """Compile only the verified source bytes; never consult an existing pyc."""
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected_sha:
        raise ValueError('The fixed S075 reader bytes changed.')
    module = types.ModuleType('s075_fixed_reader')
    module.__file__ = str(path)
    exec(compile(raw, str(path), 'exec', dont_inherit=True), module.__dict__)
    return module


def validate_output_target(repo, output, cases):
    """Bind an existing, non-linked output directory and exclude source cases."""
    if not output.is_absolute() or '..' in output.parts:
        raise ValueError('Use an absolute output path without parent traversal.')
    target = Path(os.path.abspath(output))
    allowed = repo / 'runs/s108-verification'
    if not target.is_relative_to(allowed) or target == allowed:
        raise ValueError('Output must be inside the dedicated verification directory.')
    directories = []
    for part in reversed((target.parent, *target.parent.parents)):
        info = part.lstat()
        if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
            raise ValueError('Output directory path must not contain links.')
        directories.append((str(part), info.st_dev, info.st_ino, info.st_mode))
    if os.path.lexists(target):
        raise ValueError('Existing output must never be overwritten.')
    roots = []
    for case in cases:
        workspace = (repo.parent / 'source-pins' / case['workspace']).resolve(strict=False)
        if allowed == workspace or allowed.is_relative_to(workspace) or workspace.is_relative_to(allowed):
            raise ValueError('The output directory and original case must be separate.')
        roots.append(str(workspace))
    return target, (tuple(directories), tuple(roots))


def verify_output_target(repo, output, cases, target, identity):
    checked_target, checked_identity = validate_output_target(repo, output, cases)
    if checked_target != target or checked_identity != identity:
        raise ValueError('The output directory or case identity changed during the audit.')


def summarize_cell(base, rows, saved, expected, prior):
    """Recheck the complete saved joint result before returning one suppressed cell."""
    original = base.summarize(rows, saved, expected)
    if original != prior:
        raise ValueError('The saved joint aggregate differs from the pinned prior result.')
    selected = []
    for row in rows:
        recall = row['candidate']['recall@20'] - row['baseline']['recall@20']
        mrr = row['candidate']['mrr@10'] - row['baseline']['mrr@10']
        if -EPSILON <= recall <= EPSILON and mrr < -EPSILON:
            selected.append(mrr)
    n = len(selected)
    if n != original['matrix'][1][0]:
        raise ValueError('The selected cell does not match the complete matrix.')
    if n < 5:
        return {'status': 'suppressed', 'count': None, 'mean_mrr_loss': None}
    mean = -math.fsum(selected) / n
    if not math.isfinite(mean) or not 0 < mean <= 1:
        raise ValueError('The selected loss is outside its bounded metric range.')
    return {'status': 'available', 'count': n, 'mean_mrr_loss': round(mean, 4)}


def published(repo, commit, files):
    """Verify every executable/dependency blob against the actual published source pin."""
    def git(*args, text=True):
        return subprocess.check_output(['git', '-C', str(repo), *args], text=text)
    if len(commit) != 40 or any(c not in '0123456789abcdef' for c in commit):
        raise ValueError('An exact published commit is required.')
    if git('rev-parse', 'HEAD').strip() != commit:
        raise ValueError('Reader HEAD differs from its exact commit.')
    if git('remote', 'get-url', 'origin').strip() not in ('https://github.com/open-agent-power/auto-research-agentarts', 'https://github.com/open-agent-power/auto-research-agentarts.git'):
        raise ValueError('Publication origin differs.')
    remote = git('ls-remote', 'origin', 'refs/heads/main').split()
    if len(remote) != 2 or remote[1] != 'refs/heads/main':
        raise ValueError('Canonical remote main is unavailable.')
    subprocess.check_call(['git', '-C', str(repo), 'merge-base', '--is-ancestor', commit, remote[0]])
    tracked = [str(p.relative_to(repo)) for p in files]
    if git('status', '--porcelain', '--untracked-files=all', '--', 'src/autoresearch', *tracked).strip():
        raise ValueError('Reader source or frozen audit dependencies are not clean.')
    tree = git('ls-tree', '-r', '--name-only', commit, '--', 'src/autoresearch').splitlines()
    expected = {x for x in tree if x.endswith('.py')}
    actual = {str(p.relative_to(repo)) for p in (repo / 'src/autoresearch').rglob('*.py')}
    if not expected or actual != expected:
        raise ValueError('Reader package source inventory differs from the commit.')
    manifest = {}
    for path in sorted(expected | set(tracked)):
        local = repo / path
        original = git('show', commit + ':' + path, text=False)
        if local.read_bytes() != original:
            raise ValueError('A frozen source blob differs from the published commit.')
        if local.resolve(strict=True) != local:
            raise ValueError('A frozen source or audit dependency uses a linked path.')
        manifest[path] = hashlib.sha256(original).hexdigest()
    return remote[0], manifest


def check_modules(repo, manifest):
    """All loaded autoresearch modules must be Python source in the pinned package."""
    package = (repo / 'src/autoresearch').resolve(strict=True)
    for name, module in list(sys.modules.items()):
        if name != 'autoresearch' and not name.startswith('autoresearch.'):
            continue
        path = getattr(module, '__file__', None)
        if not isinstance(path, str):
            raise ValueError('A loaded product module lacks a source location.')
        resolved = Path(path).resolve(strict=True)
        if not resolved.is_relative_to(package):
            raise ValueError('A loaded product module lies outside the published package.')
        relative = str(resolved.relative_to(repo))
        if relative not in manifest or digest(resolved) != manifest[relative]:
            raise ValueError('A loaded product module differs from the published source.')


def check_source_tree(repo, manifest, base=None, base_path=None):
    current = {str(p.relative_to(repo)) for p in (repo / 'src/autoresearch').rglob('*.py')}
    sources = {name for name in manifest if name.startswith('src/autoresearch/')}
    if (current != sources or any((repo / name).resolve(strict=True) != repo / name or digest(repo / name) != sha
                                  for name, sha in manifest.items())):
        raise ValueError('The product package or frozen audit dependency changed during the audit.')
    if base is not None and (base_path is None or Path(base.__file__).resolve(strict=True) != base_path):
        raise ValueError('The loaded S075 module location changed.')
    check_modules(repo, manifest)


def validate_prior(protocol, prior, old_protocol):
    if (old_protocol.get('cases') != protocol['cases'] or old_protocol.get('epsilon') != EPSILON
            or prior.get('schema_version') != 'saved-joint-validation-audit-v1'
            or prior.get('protocol_sha256') != protocol['s075_dependencies']['protocol_sha256']
            or prior.get('script_sha256') != protocol['s075_dependencies']['script_sha256']):
        raise ValueError('The fixed prior protocol or public aggregate differs.')
    entries = prior.get('cases')
    if type(entries) is not list or len(entries) != len(protocol['cases']):
        raise ValueError('The fixed prior case list differs.')
    mapped = {}
    identity = ('project_id', 'run_id', 'producer_core', 'source_snapshot_sha256', 'primary_action_id', 'primary_result_sha256')
    for case in protocol['cases']:
        found = [entry for entry in entries if type(entry) is dict and entry.get('case') == case['label']]
        if len(found) != 1 or any(found[0].get(k) != case[k] for k in identity):
            raise ValueError('The fixed prior case identity differs.')
        aggregate = found[0].get('aggregate')
        if type(aggregate) is not dict or aggregate.get('queries') != case['validation_queries']:
            raise ValueError('The fixed prior coverage differs.')
        if case['validation_queries'] in mapped:
            raise ValueError('Fixed case coverage must distinguish the cases.')
        mapped[case['validation_queries']] = found[0]
    return mapped


def run_guarded(base, repo, protocol, old_protocol, args, prior, manifest):
    """Reuse S075's checked reader; outer guard closes path aliases during analysis."""
    workspaces = [((repo.parent / 'source-pins' / c['workspace']).resolve(strict=True), c['primary_action_id'] + '.json')
                  for c in protocol['cases']]
    real_io, real_open, real_os = io.open, builtins.open, os.open
    def check(file, mode='r', dir_fd=None):
        if isinstance(file, int):
            return
        if dir_fd is not None:
            raise AssertionError('Relative descriptor opens are forbidden during audit.')
        path = Path(os.path.abspath(os.fsdecode(file)))
        resolved = path.resolve(strict=False)
        for workspace, primary in workspaces:
            if path == workspace or path.is_relative_to(workspace) or resolved == workspace or resolved.is_relative_to(workspace):
                if path != resolved:
                    raise AssertionError('Linked case paths are forbidden.')
                relative = path.relative_to(workspace)
                if any(part in ('private', 'private_evaluation', 'host-model-selections') for part in relative.parts):
                    raise AssertionError('Private or Host case paths are forbidden.')
                if 'artifacts' in relative.parts and path.name != primary:
                    raise AssertionError('Only the original primary artifact is permitted.')
                if any(flag in str(mode) for flag in 'wax+'):
                    raise AssertionError('Original case writes are forbidden.')
    def guarded_io(file, mode='r', *a, **kw):
        check(file, mode); return real_io(file, mode, *a, **kw)
    def guarded_open(file, mode='r', *a, **kw):
        check(file, mode); return real_open(file, mode, *a, **kw)
    def guarded_os(file, flags, *a, **kw):
        write = flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND)
        check(file, 'w' if write else 'r', kw.get('dir_fd')); return real_os(file, flags, *a, **kw)
    def no(*a, **kw):
        raise AssertionError('Network or external process forbidden during analysis.')
    original_summary, original_finish = base.summarize, base.verify_finish
    def summary(rows, saved, expected):
        return summarize_cell(base_original, rows, saved, expected, prior[expected]['aggregate'])
    class Original:
        summarize = staticmethod(original_summary)
    base_original = Original()
    def finish(*a, **kw):
        original_finish(*a, **kw)
        check_source_tree(repo, manifest, base, repo / protocol['s075_dependencies']['script'])
    with ExitStack() as guards:
        guards.enter_context(patch.object(io, 'open', guarded_io))
        guards.enter_context(patch.object(builtins, 'open', guarded_open))
        guards.enter_context(patch.object(os, 'open', guarded_os))
        guards.enter_context(patch.object(socket, 'socket', side_effect=no))
        guards.enter_context(patch.object(subprocess, 'Popen', side_effect=no))
        guards.enter_context(patch.object(base, 'summarize', side_effect=summary))
        guards.enter_context(patch.object(base, 'verify_finish', side_effect=finish))
        result = base.perform(repo, old_protocol, args)
    check_source_tree(repo, manifest, base, repo / protocol['s075_dependencies']['script'])
    if len(result['cases']) != len(protocol['cases']):
        raise ValueError('The original case count differs.')
    output = []
    for item in result['cases']:
        case_spec = next((c for c in protocol['cases'] if c['label'] == item['case']), None)
        fixed = prior.get(case_spec['validation_queries'] if case_spec else None)
        if fixed is None:
            raise ValueError('Unknown original case.')
        for key in ('case','project_id','run_id','producer_core','source_snapshot_sha256','primary_action_id','primary_result_sha256','primary_artifact_sha256'):
            if item.get(key) != fixed.get(key):
                raise ValueError('The original case or artifact identity changed.')
        output.append({k:item[k] for k in ('case','project_id','run_id','producer_core','source_snapshot_sha256','primary_action_id','primary_result_sha256','primary_artifact_sha256')} | {'source_commit':case_spec['source_commit'], 'cell':item['aggregate']})
    return result, output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--source-commit')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[1]
    protocol_path = repo / 'docs/execution/g5-local/saved-unchanged-recall-mrr-loss-protocol-v1.json'
    if digest(protocol_path) != PROTOCOL_SHA:
        raise ValueError('The fixed protocol bytes changed.')
    protocol = json.loads(protocol_path.read_text())
    if not args.execute:
        print(json.dumps({'status':'draft_only_no_analysis','protocol_sha256':PROTOCOL_SHA})); return
    if not args.source_commit or args.output is None or not args.output.is_absolute():
        raise ValueError('Execution requires an exact published commit and an absolute new output.')
    target, output_identity = validate_output_target(repo, args.output, protocol['cases'])
    dependencies = protocol['s075_dependencies']
    old_script, old_protocol_path, old_results = (repo / dependencies[k] for k in ('script','protocol','published_results'))
    for path, key in ((old_script,'script_sha256'),(old_protocol_path,'protocol_sha256'),(old_results,'results_sha256')):
        if digest(path) != dependencies[key]:
            raise ValueError('A fixed S075 dependency changed.')
    files = [Path(__file__).resolve(), protocol_path, repo/'tests/test_unchanged_recall_mrr_loss.py', old_script, old_protocol_path, old_results]
    remote, manifest = published(repo, args.source_commit, files)
    old_protocol, prior_raw = json.loads(old_protocol_path.read_text()), json.loads(old_results.read_text())
    prior = validate_prior(protocol, prior_raw, old_protocol)
    if any(name == 'autoresearch' or name.startswith('autoresearch.') for name in sys.modules):
        raise ValueError('The product package was imported before source isolation.')
    sys.pycache_prefix = tempfile.mkdtemp(prefix='s108-private-pycache-')
    sys.dont_write_bytecode = True
    base = load_s075_source(old_script, dependencies['script_sha256'])
    if base.PROTOCOL_SHA != dependencies['protocol_sha256']: raise ValueError('S075 protocol binding changed.')
    base.producer_pins(repo, old_protocol, remote)
    src = (repo / 'src').resolve(strict=True)
    sys.path = [str(src)] + [p for p in sys.path if p and Path(p).resolve(strict=False) != src]
    from autoresearch import staged_feedback_reader, staged_relevance_adapter, retrieval_holdout, retrieval_lexical, relevance_retrieval_adapter, host_model_selection
    from autoresearch.local_workbench import LocalWorkbench
    from autoresearch.project_controller import ProjectController
    from autoresearch.research_project import ResearchProject, code_identity
    from sklearn.linear_model import Ridge
    from sklearn.preprocessing import StandardScaler
    import numpy, scipy, sklearn
    _ = (staged_feedback_reader, staged_relevance_adapter, retrieval_holdout, retrieval_lexical, relevance_retrieval_adapter,
         host_model_selection, LocalWorkbench, ProjectController, ResearchProject, Ridge, StandardScaler)
    check_source_tree(repo, manifest, base, old_script)
    before_core = code_identity()
    result, cases = run_guarded(base, repo, protocol, old_protocol, args, prior, manifest)
    if result['reader_core'] != before_core or code_identity() != before_core:
        raise ValueError('The loaded reader identity changed.')
    output = {'schema_version':'saved-unchanged-recall-mrr-loss-v1','protocol_sha256':PROTOCOL_SHA,
              'script_sha256':manifest[str(Path(__file__).resolve().relative_to(repo))],'reader_commit':args.source_commit,
              'reader_core':before_core,'reader_implementation_sha256':result['reader_implementation_sha256'],
              'reader_and_audit_manifest_sha256':hashlib.sha256(json.dumps(manifest, sort_keys=True, separators=(',', ':')).encode()).hexdigest(),
              'runtime':{'python':platform.python_version(),'numpy':numpy.__version__,'scipy':scipy.__version__,'scikit_learn':sklearn.__version__},
              's075_protocol_sha256':dependencies['protocol_sha256'],'s075_script_sha256':dependencies['script_sha256'],
              's075_results_sha256':dependencies['results_sha256'],'verified_remote_head_at_execution':remote,
              'cases':cases,'limitations':protocol['limitations'],'guard_scope':protocol['guard_scope'],
              'new_research_actions':0,'new_models':0,'new_fits':0,'development_cost':'unknown','read_and_compute_cost':'unknown'}
    check_source_tree(repo, manifest, base, old_script)
    verify_output_target(repo, args.output, protocol['cases'], target, output_identity)
    base.publish_new(target, output)
    print(json.dumps({'status':'completed','output_sha256':digest(target)}))


if __name__ == '__main__':
    try:
        main()
    except Exception:
        # Never serialize raw rows, query identities, paths from row keys, or tracebacks.
        print('Audit failed or publication durability is unknown. If a target exists, preserve and inspect it; do not overwrite.', file=sys.stderr)
        raise SystemExit(1)
