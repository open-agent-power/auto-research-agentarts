"""Frozen, retrospective validation-only joint accounting; no study execution."""
import argparse
import builtins
from contextlib import ExitStack
import hashlib
import io
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from unittest.mock import patch

PROTOCOL_SHA = '575f57346c8c0bd3c4e4f8b6c95a71eb3c70eb50bc8cfc4a467d577b414a925b'
EPSILON = 1e-12
ORDER = ('negative', 'zero', 'positive')
METRICS = ('recall@20', 'mrr@10')


def category(value):
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError('Non-finite or nonnumeric delta.')
    return 'negative' if value < -EPSILON else 'positive' if value > EPSILON else 'zero'


def summarize(rows, saved, expected):
    """Input is paired synthetic or checked saved values; output contains no identifiers."""
    if type(expected) is not int or expected < 1 or len(rows) != expected:
        raise ValueError('Invalid validation query count.')
    ids = [row['query_id'] for row in rows]
    if any(type(q) is not str or not q for q in ids) or len(set(ids)) != expected:
        raise ValueError('Missing or duplicate query identity.')
    cells = [[0] * 3 for _ in ORDER]
    deltas = {metric: [] for metric in METRICS}
    for row in rows:
        pair = []
        for metric in METRICS:
            a, b = row['baseline'][metric], row['candidate'][metric]
            if any(type(v) not in (int, float) or not math.isfinite(v) or not 0 <= v <= 1 for v in (a, b)):
                raise ValueError('Invalid paired value.')
            delta = b - a
            deltas[metric].append(delta)
            pair.append(ORDER.index(category(delta)))
        cells[pair[0]][pair[1]] += 1
    margins = {METRICS[0]: [sum(line) for line in cells],
               METRICS[1]: [sum(line[i] for line in cells) for i in range(3)]}
    checks = {}
    for metric in METRICS:
        original = saved[metric]
        mean = original['mean']
        checked = math.fsum(deltas[metric]) / expected
        if (type(mean) not in (int, float) or not math.isfinite(mean)
                or not math.isclose(mean, checked, rel_tol=0, abs_tol=EPSILON)
                or any(type(original[k]) is not int for k in ('losses', 'ties', 'wins'))
                or [original['losses'], original['ties'], original['wins']] != margins[metric]):
            raise ValueError('Saved summary differs from complete validation pairs.')
        checks[metric] = {'saved_mean': mean, 'checked_fsum_mean': checked,
                          'negative': margins[metric][0], 'zero': margins[metric][1],
                          'positive': margins[metric][2]}
    return {'queries': expected, 'rows': METRICS[0], 'columns': METRICS[1],
            'category_order': list(ORDER), 'matrix': cells, 'margins_and_means': checks}


def published(repo, commit, protocol):
    def git(*args):
        return subprocess.check_output(['git', '-C', str(repo), *args], text=True).strip()
    if len(commit) != 40 or any(c not in '0123456789abcdef' for c in commit):
        raise ValueError('Use the full published commit SHA.')
    if git('rev-parse', 'HEAD') != commit:
        raise ValueError('HEAD must equal the supplied commit.')
    if git('remote', 'get-url', 'origin') not in ('https://github.com/open-agent-power/auto-research-agentarts', 'https://github.com/open-agent-power/auto-research-agentarts.git'):
        raise ValueError('Unexpected publication repository.')
    remote = git('ls-remote', 'origin', 'refs/heads/main').split()
    if len(remote) != 2 or remote[1] != 'refs/heads/main':
        raise ValueError('Cannot verify canonical remote main.')
    subprocess.check_call(['git', '-C', str(repo), 'merge-base', '--is-ancestor', commit, remote[0]])
    paths = ['src/autoresearch', 'scripts/audit_saved_joint_validation.py', str(protocol.relative_to(repo))]
    if git('status', '--porcelain', '--untracked-files=all', '--', *paths):
        raise ValueError('Reader, script or protocol is not the clean published version.')
    for item in (Path(__file__).resolve(), protocol):
        raw = subprocess.check_output(['git', '-C', str(repo), 'show', commit + ':' + str(item.relative_to(repo))])
        if raw != item.read_bytes():
            raise ValueError('Script or protocol differs from published bytes.')
    return remote[0]


def producer_pins(repo, protocol, remote_head):
    """Check producer checkout identities before opening any study workspace."""
    allowed_origins = ('https://github.com/open-agent-power/auto-research-agentarts',
                       'https://github.com/open-agent-power/auto-research-agentarts.git')
    for case in protocol['cases']:
        pin_name = case['workspace'].split('/', 1)[0]
        pin = (repo.parent / 'source-pins' / pin_name).resolve(strict=True)
        def git(*args):
            return subprocess.check_output(['git', '-C', str(pin), *args], text=True).strip()
        if (git('rev-parse', 'HEAD') != case['source_commit']
                or git('remote', 'get-url', 'origin') not in allowed_origins
                or git('status', '--porcelain', '--untracked-files=all', '--', 'src/autoresearch')):
            raise ValueError('Producer pin HEAD, origin or source tree changed.')
        subprocess.check_call(['git', '-C', str(repo), 'merge-base', '--is-ancestor',
                               case['source_commit'], remote_head])


def verify_finish(reader, project, state, action, checked, initial_reader_sha, initial_core, current_core):
    """Recheck the exact public source, primary, SQL row and reader at the end."""
    source_sha, _, _ = reader.evidence._dev_source(project, state)
    _, artifact_sha = reader.evidence._read(project, action)
    reader.evidence._verify_action_rows(project, [action])
    if (source_sha != checked['source_sha'] or artifact_sha != checked['artifact_sha']
            or hashlib.sha256(Path(reader.__file__).read_bytes()).hexdigest() != initial_reader_sha
            or current_core() != initial_core or project.status() != state):
        raise ValueError('The original source, primary, reader or Project changed during audit.')


def publish_new(target, result):
    """Publish a complete JSON file without overwriting a prior result."""
    descriptor, temp_name = tempfile.mkstemp(prefix='.' + target.name + '.', suffix='.tmp', dir=target.parent)
    temp = Path(temp_name)
    try:
        with os.fdopen(descriptor, 'w', encoding='utf-8') as stream:
            json.dump(result, stream, indent=2, sort_keys=True)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temp, target)
        directory = os.open(target.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        temp.unlink(missing_ok=True)


def perform(repo, protocol, args):
    # A fresh private cache namespace must precede any project import.
    sys.pycache_prefix = tempfile.mkdtemp(prefix='joint-validation-import-')
    sys.dont_write_bytecode = True
    from autoresearch import staged_feedback_reader as reader, staged_relevance_adapter as staged
    from autoresearch import retrieval_holdout as holdout, retrieval_lexical as lexical
    from autoresearch import relevance_retrieval_adapter as relevance, host_model_selection as host
    from autoresearch.local_workbench import LocalWorkbench
    from autoresearch.project_controller import ProjectController
    from autoresearch.research_project import ResearchProject, code_identity
    from sklearn.linear_model import Ridge
    from sklearn.preprocessing import StandardScaler

    initial_core = code_identity()
    initial_reader_sha = hashlib.sha256(Path(reader.__file__).read_bytes()).hexdigest()
    observations = []
    for case in protocol['cases']:
        workspace = (repo.parent / 'source-pins' / case['workspace']).resolve(strict=True)
        manager = LocalWorkbench.open_readonly(workspace / 'manager')
        with manager._connect(readonly=True) as con:
            _, project = manager._project(con, case['project_id'])
        root = project.root.resolve(strict=True)
        allowed_artifact = root / 'artifacts' / (case['primary_action_id'] + '.json')
        denied = [workspace / 'private', root / 'private_evaluation', root / 'host-model-selections']
        real_io_open, real_open, real_os_open = io.open, builtins.open, os.open

        def check(file, mode='r'):
            if isinstance(file, int):
                return
            if any(flag in str(mode) for flag in 'wax+'):
                raise AssertionError('Write forbidden while reading originals.')
            path = Path(os.fsdecode(file)).absolute()
            if any(path == p or path.is_relative_to(p) for p in denied):
                raise AssertionError('Private path access forbidden.')
            if path.is_relative_to(root / 'artifacts') and path != allowed_artifact:
                raise AssertionError('Only the original primary artifact may be read.')

        def guarded_io(file, mode='r', *a, **kw):
            check(file, mode); return real_io_open(file, mode, *a, **kw)
        def guarded_open(file, mode='r', *a, **kw):
            check(file, mode); return real_open(file, mode, *a, **kw)
        def guarded_os(file, flags, *a, **kw):
            if flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND):
                raise AssertionError('Write forbidden while reading originals.')
            check(file); return real_os_open(file, flags, *a, **kw)
        def no(*a, **kw):
            raise AssertionError('New computation, dispatch, Host, recovery or project writes forbidden.')

        with ExitStack() as guards:
            guards.enter_context(patch.object(io, 'open', guarded_io))
            guards.enter_context(patch.object(builtins, 'open', guarded_open))
            guards.enter_context(patch.object(os, 'open', guarded_os))
            for obj, name in ((holdout, '_verified_private'), (staged, 'execute'),
                    (lexical, 'build_index'), (lexical, 'retrieve'), (lexical, 'metrics'),
                    (relevance, 'retrieve'), (ResearchProject, 'step'), (ResearchProject, 'resume'),
                    (ResearchProject, '_recover'), (ResearchProject, '_writer'),
                    (ProjectController, 'advance_selection'), (host.HostModelSelection, 'prepare'),
                    (host.HostModelSelection, 'request'), (host, 'run_claude_selection'),
                    (Ridge, 'fit'), (StandardScaler, 'fit')):
                guards.enter_context(patch.object(obj, name, side_effect=no))
            state = project.status()
            if (state['id'] != case['project_id'] or state['run_id'] != case['run_id']
                    or state['code_identity'] != case['producer_core']
                    or state['source_snapshot_sha256'] != case['source_snapshot_sha256']
                    or state['budget']['local_tool_calls_used'] != 3
                    or state['budget']['local_tool_call_limit'] != 3):
                raise ValueError('Project identity or original budget changed.')
            matches = [a for a in state['actions'] if a['id'] == case['primary_action_id']]
            if len(matches) != 1 or matches[0]['result_sha256'] != case['primary_result_sha256']:
                raise ValueError('Original primary identity changed.')
            checked = reader._checked_primary(project, state, matches[0])
            qids = checked['source']['spec']['query_splits']['validation']
            if len(qids) != case['validation_queries'] or len(set(qids)) != len(qids):
                raise ValueError('Validation coverage changed.')
            rows = [{'query_id': qid,
                     'baseline': checked['metrics'][('validation', qid, 'bm25')]['metrics'],
                     'candidate': checked['metrics'][('validation', qid, 'tfidf_cosine')]['metrics']}
                    for qid in qids]
            saved = checked['summary']['splits']['validation']['paired_candidate_minus_baseline']
            aggregate = summarize(rows, saved, case['validation_queries'])
            verify_finish(reader, project, state, matches[0], checked,
                          initial_reader_sha, initial_core, code_identity)
        observations.append({'case': case['label'], 'project_id': case['project_id'], 'run_id': case['run_id'],
            'producer_core': case['producer_core'], 'source_snapshot_sha256': case['source_snapshot_sha256'],
            'primary_action_id': case['primary_action_id'], 'primary_result_sha256': case['primary_result_sha256'],
            'primary_artifact_sha256': checked['artifact_sha'], 'aggregate': aggregate})
    return {'schema_version': 'saved-joint-validation-audit-v1', 'protocol_sha256': PROTOCOL_SHA,
            'script_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            'reader_core': initial_core, 'reader_implementation_sha256': initial_reader_sha,
            'reader_commit': args.source_commit,
            'cases': observations, 'limitations': protocol['limitations'], 'guard_scope': protocol['guard_scope'],
            'new_research_actions': 0, 'new_models': 0, 'new_fits': 0, 'development_cost': 'unknown'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--source-commit')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[1]
    protocol_path = repo / 'docs/execution/g5-local/saved-joint-validation-protocol-v1.json'
    raw = protocol_path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != PROTOCOL_SHA:
        raise ValueError('Protocol bytes differ from the fixed contract.')
    protocol = json.loads(raw)
    if not args.execute:
        print(json.dumps({'status': 'draft_only_no_analysis', 'protocol_sha256': PROTOCOL_SHA})); return
    if not args.source_commit or args.output is None or not args.output.is_absolute():
        raise ValueError('Execution requires an exact published commit and absolute new output.')
    target = args.output.resolve()
    permitted = (repo / 'runs/s075-verification').resolve()
    if not target.is_relative_to(permitted) or not target.parent.is_dir() or target.exists():
        raise ValueError('Output must be new and inside the dedicated verification directory.')
    remote = published(repo, args.source_commit, protocol_path)
    producer_pins(repo, protocol, remote)
    result = perform(repo, protocol, args)
    result['verified_remote_head_at_execution'] = remote
    publish_new(target, result)
    print(json.dumps({'status': 'completed', 'output_sha256': hashlib.sha256(target.read_bytes()).hexdigest()}))


if __name__ == '__main__':
    main()
