#!/usr/bin/env python3
"""Thin host freeze/run wrapper around the existing native project lifecycle."""
import argparse
from contextlib import ExitStack
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

REPO = Path(__file__).resolve().parents[1]
SCRIPT = Path(__file__).resolve()
PROTOCOL = REPO / 'docs/execution/g5-local/native-run-protocol.md'
CASES = {
    'retrieval': {'packet': '/workspace/work/g5-native-retrieval-packet.json',
                  'sha256': '546a09773bc8e77aa7f034ca58753394f6a75c3ecf610e3c66c3f24eea2ab51b',
                  'contract': 'docs/execution/g5-local/native-integration-contract.md',
                  'method': 'research.retrieval-fixed-pair', 'audit': 'research.retrieval-saved-error-audit'},
    'scheduling': {'packet': '/workspace/work/g5-native-scheduling-packet.json',
                   'sha256': 'c801e08c980caa8f56be6865eef149c98e3cad1c486b0abd39c37695611dcc3e',
                   'contract': 'docs/execution/g5-local/native-algorithm-contract.md',
                   'method': 'research.weighted-interval-fixed-pair', 'audit': 'research.weighted-interval-saved-audit'}}
LIMITS = {'wall_seconds': 180, 'cpu_soft_seconds': 120, 'cpu_hard_seconds': 130,
          'address_space_bytes': 1073741824, 'file_bytes': 33554432, 'threads': 1,
          'minimum_disk_free_bytes': 5368709120}
THREAD_ENV = ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS', 'NUMEXPR_NUM_THREADS')


def require(value, message):
    if not value:
        raise RuntimeError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def save(path, value):
    with path.open('xb') as stream:
        stream.write((canonical(value)+'\n').encode())
        stream.flush()
        os.fsync(stream.fileno())


def read(path, maximum=16000000, *, allow_empty=False):
    path = Path(path)
    require(path.is_file() and not any(p.is_symlink() for p in (path, *path.parents)), 'Use regular non-symlink files')
    minimum = 0 if allow_empty else 1
    require(minimum <= path.stat().st_size <= maximum, 'File exceeds fixed byte bound')
    with path.open('rb') as stream:
        raw = stream.read(maximum+1)
    require(minimum <= len(raw) <= maximum, 'Captured file exceeds byte bound')
    return raw


def parse(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, 'Duplicate JSON member')
            result[key] = value
        return result
    def constant(_):
        raise ValueError('Nonfinite JSON')
    return json.loads(raw.decode('utf-8'), object_pairs_hook=pairs, parse_constant=constant)


def git(*args):
    return subprocess.run(['git', *args], cwd=REPO, check=True, capture_output=True,
                          text=True, timeout=20).stdout.strip()


def committed_identity(commit):
    require(re.fullmatch('[0-9a-f]{40}', commit) is not None and git('rev-parse', 'HEAD') == commit,
            'Root must provide the current full committed code identity')
    # Include deleted tracked sources, which a current-filesystem rglob omits.
    subprocess.run(['git', 'diff', '--exit-code', commit, '--', 'src/autoresearch'], cwd=REPO,
                   check=True, stdout=subprocess.DEVNULL, timeout=20)
    paths = sorted((REPO/'src/autoresearch').rglob('*.py')) + [SCRIPT, PROTOCOL]
    paths += [REPO/CASES[name]['contract'] for name in CASES]
    identities = {}
    for path in paths:
        relative = str(path.relative_to(REPO))
        git('ls-files', '--error-unmatch', relative)
        subprocess.run(['git', 'diff', '--exit-code', commit, '--', relative], cwd=REPO,
                       check=True, stdout=subprocess.DEVNULL, timeout=20)
        raw = read(path)
        identities[relative] = {'bytes': len(raw), 'sha256': sha(raw)}
    return identities


def runtime():
    for key in THREAD_ENV:
        os.environ[key] = '1'
    sys.path.insert(0, str(REPO/'src'))
    from autoresearch import retrieval_adapter, retrieval_lexical, scheduling_adapter, scheduling_kernel
    from autoresearch import research_project, project_controller, local_workbench, method_registry
    return retrieval_adapter, retrieval_lexical, scheduling_adapter, scheduling_kernel, research_project, project_controller, local_workbench, method_registry


def disabled(modules, *, source_only=False):
    from unittest.mock import patch
    retrieval, lexical, scheduling, kernel, *_ = modules
    guard = ExitStack()
    def deny(*args, **kwargs):
        raise AssertionError('Research computation is forbidden in this phase')
    for module, names in ((lexical, ('tokens', 'build_index', 'retrieve', 'metrics')),
                          (kernel, ('schedule', 'brute_force', 'jobs_for')),
                          (retrieval, ('execute',)), (scheduling, ('execute',))):
        for name in names:
            if hasattr(module, name):
                guard.enter_context(patch.object(module, name, side_effect=deny))
    if source_only:
        guard.enter_context(patch.object(kernel, 'verify_schedule', side_effect=deny))
    # The adapters share Python's time module; saved-only audit must not retime.
    guard.enter_context(patch.object(scheduling.time, 'perf_counter', side_effect=deny))
    return guard


def protected_tree_roots():
    return [REPO/name for name in (
        'runs/cloud-concrete-local-20261113-01',
        'runs/g3-local-transfer-20261113-01/real-estate',
        'runs/g3-local-transfer-20261113-01/slump',
        'runs/g4-local-group-20261113-01', 'runs/g4-native-confirmation-20261113-01')
    ] + [Path('/workspace/work/g5-native-retrieval-inputs'),
         Path('/workspace/work/g5-native-scheduling-inputs'), Path('/workspace/work/g5-cpu-inputs')]


def validate_output(path, case, fixture):
    root = Path(path).absolute()
    require('..' not in root.parts and not any(p.is_symlink() for p in (root, *root.parents)),
            'Output cannot use traversal or symlink ancestors')
    if not fixture:
        require(root.name == case and root.parent.parent == REPO/'runs'
                and re.fullmatch(r'g5-native-cases-[A-Za-z0-9][A-Za-z0-9_.-]{0,64}', root.parent.name),
                'Real output must be runs/g5-native-cases-<unique>/<case>')
    else:
        require(any(root != scratch and root.is_relative_to(scratch)
                    for scratch in (Path('/workspace/work'), Path('/tmp'))),
                'Explicit engineering output must use scratch space')
    protected = protected_tree_roots()+[REPO/'runs/g5-local-cpu-20261113-01']
    protected += [Path(value['packet']) for value in CASES.values()]
    protected += [REPO/'src', REPO/'scripts', REPO/'docs']
    for original in protected:
        require(not root.is_relative_to(original) and not original.is_relative_to(root),
                'Output overlaps a protected case/source tree')
    return root


def protected_paths():
    old = REPO/'runs/g5-local-cpu-20261113-01'
    freeze = parse(read(old/'freeze.json'))
    paths = [REPO/'scripts/run_cpu_transfer_benchmarks.py', REPO/'docs/execution/g5-local/protocol.md']
    paths += [Path(freeze['input_dir'])/name for name in freeze['inputs']]
    paths += sorted(p for p in old.rglob('*') if p.is_file())
    paths += [Path(value['packet']) for value in CASES.values()]
    paths += [Path('/workspace/work/g5-native-source-mapping.json'),
              Path('/workspace/work/g5-native-retrieval-preflight.json'),
              Path('/workspace/work/g5-native-scheduling-host-prepare/source-reviewed-preflight.json')]
    paths += [REPO/name for name in (
        'scripts/g4_group_capability.py', 'scripts/run_g4_group_candidate.py',
        'docs/execution/g4-local/protocol.md', 'scripts/verify_native_group_candidate.py',
        'docs/execution/g4-local/native-confirmation-protocol.md')]
    for tree in protected_tree_roots():
        require(tree.is_dir(), 'Original protected tree is missing')
        paths += sorted(p for p in tree.rglob('*') if p.is_file())
    return sorted(set(paths))


def identities(paths):
    result = {}
    for path in paths:
        raw = read(path, 64000000, allow_empty=True)
        result[str(path)] = {'bytes': len(raw), 'sha256': sha(raw)}
    return result


def disk_headroom(path):
    existing = next(part for part in (path, *path.parents) if part.exists())
    free = shutil.disk_usage(existing).free
    require(free >= LIMITS['minimum_disk_free_bytes'], 'At least 5 GiB disk headroom is required')
    return {'path': str(existing), 'free_bytes': free, 'minimum_bytes': LIMITS['minimum_disk_free_bytes']}


def source_mode(case_name, fixture, raw, payload):
    require(type(fixture) is bool, 'Source mode must be exact boolean')
    case = CASES[case_name]
    require(payload['task_kind'] == ('citation_retrieval' if case_name == 'retrieval' else 'weighted_interval'),
            'Case and source task kind differ')
    if not fixture:
        require(sha(raw) == case['sha256'], 'Real case must use the exact prepared packet')
    else:
        require(sha(raw) != case['sha256'], 'Real source cannot be relabeled a fixture')
        scope = payload['scope']
        require((scope.get('document_count', 0) <= 20 and scope.get('query_count', 0) <= 20)
                if case_name == 'retrieval' else (scope['case_count'] <= 4 and scope['job_count'] <= 32),
                'Engineering fixtures must be small')


def prepare(args):
    root = validate_output(args.output, args.case, args.engineering_fixture)
    require(not root.exists(), 'Use a fresh output; existing evidence is never replaced')
    disk = disk_headroom(root)
    code = committed_identity(args.code_commit)
    case = CASES[args.case]
    packet = Path(args.packet or case['packet']).absolute()
    raw = read(packet)
    modules = runtime()
    adapter = modules[0 if args.case == 'retrieval' else 2]
    with disabled(modules, source_only=True):
        payload = adapter.load_source(raw)
    source_mode(args.case, args.engineering_fixture, raw, payload)
    protection = identities(protected_paths())
    root.mkdir(parents=True)
    (root/'frozen').mkdir()
    with (root/'frozen/source.json').open('xb') as stream:
        stream.write(raw)
    freeze = {'schema_version': 'g5-native-cpu-freeze-v1', 'output_root': str(root.resolve()),
              'case': args.case, 'engineering_fixture': args.engineering_fixture,
              'code_commit': args.code_commit, 'code_files': code,
              'project_code_identity': modules[4].code_identity(),
              'runtime_dependencies': modules[7].runtime_dependencies(),
              'packet_original_path': str(packet), 'packet_sha256': sha(raw),
              'packet_bytes': len(raw), 'snapshot_sha256': payload['snapshot_sha256'],
              'scope': payload['scope'], 'limits': LIMITS, 'protected': protection,
              'protected_tree_roots': [str(path) for path in protected_tree_roots()],
              'disk_preflight': disk, 'python_executable': str(Path(sys.executable).absolute()),
              'python_version': sys.version,
              'allowance': {'local_tools': 2, 'fits': 0, 'models': 0, 'evidence_reads': 0},
              'budget_ref': 'g5-native-'+args.case+':'+root.name,
              'known_results': 'Public standalone outcomes already visible; native lifecycle replication, no new unseen evaluation or automatic promotion.',
              'review_required': 'New review binding this freeze SHA, output root, case and committed code before run.'}
    save(root/'freeze.json', freeze)
    save(root/'preflight.json', {'status': 'frozen_not_executed', 'freeze_sha256': sha(read(root/'freeze.json')),
                               'research_actions': 0, 'fits': 0, 'models': 0, 'api_calls': 0,
                               'schema_only': True})
    print(canonical({'status': 'frozen_not_executed', 'freeze_sha256': sha(read(root/'freeze.json'))}))


def frozen(root, *, execution):
    raw = read(root/'freeze.json')
    value = parse(raw)
    require(value['schema_version'] == 'g5-native-cpu-freeze-v1' and value['case'] in CASES
            and canonical(value['limits']) == canonical(LIMITS)
            and canonical(value['allowance']) == canonical({'local_tools': 2, 'fits': 0, 'models': 0, 'evidence_reads': 0}),
            'Unsupported freeze/limits/allowance')
    if execution:
        require(value['output_root'] == str(root.resolve()), 'A copied freeze cannot start a new batch')
    validate_output(root, value['case'], value['engineering_fixture'])
    require(value['protected_tree_roots'] == [str(path) for path in protected_tree_roots()],
            'Fixed protected tree roots changed')
    disk_headroom(root)
    require(value['python_executable'] == str(Path(sys.executable).absolute()) and value['python_version'] == sys.version,
            'Use the frozen Python interpreter/version')
    require(committed_identity(value['code_commit']) == value['code_files'], 'Frozen source changed')
    require(identities(protected_paths()) == value['protected'], 'Protected originals/inventory changed')
    packet = read(root/'frozen/source.json')
    require(sha(packet) == value['packet_sha256'] and len(packet) == value['packet_bytes'], 'Frozen packet changed')
    modules = runtime()
    adapter = modules[0 if value['case'] == 'retrieval' else 2]
    with disabled(modules, source_only=True):
        payload = adapter.load_source(packet)
    source_mode(value['case'], value['engineering_fixture'], packet, payload)
    require(payload['snapshot_sha256'] == value['snapshot_sha256']
            and canonical(payload['scope']) == canonical(value['scope']), 'Frozen derived source identity changed')
    return raw, value


def run(args):
    root = args.output.absolute()
    freeze_raw, freeze = frozen(root, execution=True)
    review_raw = read(args.review, 64000)
    review = parse(review_raw)
    require(set(review) == {'schema_version', 'status', 'freeze_sha256', 'code_commit', 'output_root', 'case', 'reviewer', 'limitations'}
            and review['schema_version'] == 'g5-native-cpu-run-review-v1' and review['status'] == 'approved'
            and review['freeze_sha256'] == sha(freeze_raw) and review['code_commit'] == freeze['code_commit']
            and review['output_root'] == freeze['output_root'] and review['case'] == freeze['case']
            and type(review['reviewer']) is str and bool(review['reviewer'].strip()), 'A new exact approved review is required')
    archive = root/'independent-native-review.json'
    if archive.exists():
        require(read(archive) == review_raw, 'Archived review differs')
    else:
        with archive.open('xb') as stream:
            stream.write(review_raw)
    save(root/'attempt.json', {'schema_version': 'g5-native-cpu-attempt-v1', 'status': 'running',
                              'freeze_sha256': sha(freeze_raw), 'review_sha256': sha(review_raw),
                              'automatic_retry': False})
    command = [sys.executable, '-B', str(SCRIPT), '_worker', '--output', str(root)]
    save(root/'subprocess-command.json', {'argv': command, 'limits': LIMITS})
    env = {**os.environ, **{name: '1' for name in THREAD_ENV}, 'PYTHONDONTWRITEBYTECODE': '1'}
    try:
        with (root/'worker.stdout').open('xb') as out, (root/'worker.stderr').open('xb') as err:
            process = subprocess.run(command, cwd=REPO, env=env, stdout=out, stderr=err,
                                     timeout=LIMITS['wall_seconds'], check=False)
        complete = process.returncode == 0 and (root/'result.json').is_file()
        status = 'completed' if complete else 'unknown_preserve_no_retry'
        save(root/'attempt-final.json', {'status': status, 'returncode': process.returncode,
                                       'automatic_retry': False})
        require(complete, 'Worker did not complete; preserve the original requests, do not retry')
    except subprocess.TimeoutExpired:
        save(root/'attempt-final.json', {'status': 'unknown_wall_timeout', 'automatic_retry': False})
        raise
    print(canonical(parse(read(root/'result.json'))))


def worker(root):
    # Limits apply only in this newly spawned interpreter, never the host session.
    import resource
    import signal
    for name in THREAD_ENV:
        os.environ[name] = '1'
    resource.setrlimit(resource.RLIMIT_CPU, (LIMITS['cpu_soft_seconds'], LIMITS['cpu_hard_seconds']))
    resource.setrlimit(resource.RLIMIT_AS, (LIMITS['address_space_bytes'], LIMITS['address_space_bytes']))
    resource.setrlimit(resource.RLIMIT_FSIZE, (LIMITS['file_bytes'], LIMITS['file_bytes']))
    signal.alarm(LIMITS['wall_seconds'])
    freeze_raw, freeze = frozen(root, execution=True)
    attempt = parse(read(root/'attempt.json'))
    require(attempt['freeze_sha256'] == sha(freeze_raw)
            and attempt['review_sha256'] == sha(read(root/'independent-native-review.json')),
            'Original approved attempt identity differs')
    modules = runtime()
    retrieval, lexical, scheduling, kernel, core, controller, workbench, registry = modules
    require(core.code_identity() == freeze['project_code_identity']
            and registry.runtime_dependencies() == freeze['runtime_dependencies'], 'Runtime identity changed')
    save(root/'host-start.json', {'disk': disk_headroom(root), 'limits': LIMITS,
                                 'python_executable': sys.executable, 'python_version': sys.version})
    from unittest.mock import patch
    import socket
    from sklearn.linear_model import Ridge
    from sklearn.preprocessing import StandardScaler
    from autoresearch import source_evidence_adapter
    guard_calls = {'ridge_fit': 0, 'scaler_fit': 0, 'network': 0, 'source_extraction': 0}
    guards = ExitStack()
    def forbidden(name):
        def fail(*args, **kwargs):
            guard_calls[name] += 1
            raise AssertionError('Forbidden native case operation: '+name)
        return fail
    for target, name in ((Ridge, 'ridge_fit'), (StandardScaler, 'scaler_fit')):
        guards.enter_context(patch.object(target, 'fit', side_effect=forbidden(name)))
    for target, attribute in ((socket.socket, 'connect'), (socket.socket, 'connect_ex'),
                              (socket.socket, 'sendto'), (socket, 'create_connection'), (socket, 'getaddrinfo')):
        guards.enter_context(patch.object(target, attribute, side_effect=forbidden('network')))
    guards.enter_context(patch.object(source_evidence_adapter, 'execute', side_effect=forbidden('source_extraction')))
    case = CASES[freeze['case']]
    project = core.ResearchProject(root/'unmanaged-project')
    current = [project]
    (root/'steps').mkdir()
    def budget():
        return current[0].status()['budget'] if current[0].db.exists() else None
    def stage(name, command, body, function):
        before = budget()
        save(root/'steps'/ (name+'-request.json'), {'command': command, 'body': body,
                                                  'replay_body': body, 'budget_before': before,
                                                  'receiver_ref': {'project_root': str(current[0].root),
                                                                   'workbench_root': str(root/'manager') if command.startswith('LocalWorkbench.') else None},
                                                  'replay_policy': 'Never replay create into a vanished pre-import root; use exact original IDs only against the existing relocated DB.'})
        result = function()
        save(root/'steps'/ (name+'-result.json'), {'result': result, 'budget_after': budget()})
        return result
    try:
        body = {'source': str(root/'frozen/source.json'), 'goal': 'Native fixed CPU pair and saved-only audit; already-known standalone outcomes, no automatic promotion.',
                'budget_ref': freeze['budget_ref'], 'max_tool_calls': 2, 'method_id': case['method']}
        stage('01-create', 'ResearchProject.create', body, lambda: project.create(**body))
        cap = {'request_id': 'native-source-cap', 'expected_limit': 8, 'new_limit': 0,
               'expected_state_version': project.status()['state_version'], 'reason': 'No source extraction in this separately scoped native integration'}
        stage('02-source-cap', 'ResearchProject.limit_evidence_budget', cap, lambda: project.limit_evidence_budget(**cap))
        manager = workbench.LocalWorkbench(root/'manager')
        project_id = project.status()['id']
        intake = {'request_id': 'native-import', 'workspace': str(project.root)}
        def import_project():
            result = manager.import_project(**intake)
            current[0] = core.ResearchProject(result['workspace'])
            save(root/'project-relocation.json', {'project_id': project_id,
                                                'original_project_root': str(project.root),
                                                'relocated_project_root': result['workspace'],
                                                'import_request_id': intake['request_id'],
                                                'import_body': intake,
                                                'recovery_requires_existing_target_db': True,
                                                'create_at_original_root_after_import_forbidden': True})
            return result
        stage('03-import', 'LocalWorkbench.import_project', intake, import_project)
        select = {'request_id': 'native-select', 'project_id': project_id}
        stage('04-select', 'LocalWorkbench.select', select, lambda: manager.select(select))
        project, _ = manager.binding()
        current[0] = project
        plan = {'question': 'What does this exact fixed pair show through the native project lifecycle?',
                'basis': freeze['known_results'], 'steps': 'Run both frozen arms once as one primary action; inspect actual output; audit saved results; wait.',
                'expected_feedback': 'Keep complete results, adverse outcomes, source identity and zero fit/model/source budgets; no promotion.'}
        def save_plan(number, basis, steps):
            body = {'request_id': 'native-plan-'+str(number), 'project_id': project_id,
                    'expected_state_version': project.status()['state_version'],
                    'plan': {**plan, 'basis': basis, 'steps': steps}, 'reason': 'Actual observation-driven revision '+str(number)}
            return stage('plan'+str(number), 'LocalWorkbench.save_plan', body, lambda: manager.save_plan(body))
        def advance(name, method):
            context = controller.ProjectController(project.root).selection_context()
            save(root/'steps'/(name+'-context.json'), context)
            if method is None:
                choice = {'kind': 'wait'}
            else:
                matches = [c for c in context['candidates'] if c['method_id'] == method]
                require(len(matches) == 1, 'Expected one exact eligible native candidate')
                choice = {'kind': 'execute', 'candidate_id': matches[0]['id']}
            body = {'request_id': 'native-'+name, 'project_id': project_id,
                    'expected_state_version': context['state_version'], 'proposal': {
                        'schema_version': 'project-selection-proposal-v1', 'context_sha256': context['context_sha256'],
                        'provider': {'kind': 'operator_assistant', 'label': 'Predeclared host fixed pair; no model send'},
                        'choice': choice, 'rationale': 'Use this exact saved context and fixed method; preserve adverse results and scope.',
                        'evidence_citation_ids': []}}
            response = stage(name, 'LocalWorkbench.advance', body, lambda: manager.advance(body))
            require(response['status'] == 'completed' or method is None, 'Unknown/failed action; never replace or retry')
            with disabled(modules):
                old_budget = budget()
                replay = stage(name+'-replay', 'LocalWorkbench.advance', body, lambda: manager.advance(body))
                require(replay.get('replayed') and budget() == old_budget, 'Replay changed budget or was not recognized')
            return response
        save_plan(1, plan['basis'], plan['steps'])
        advance('primary', case['method'])
        primary = project.status()['actions'][0]
        artifact_raw = project._artifact(primary).read_bytes()
        envelope = parse(artifact_raw)
        require(envelope['sha256'] == primary['result_sha256']
                and sha(canonical({k: v for k, v in envelope.items() if k != 'sha256'}).encode()) == envelope['sha256'],
                'Actual primary result identity changed')
        actual = envelope['tool_result']
        feedback = {'action_id': primary['id'], 'result_sha256': primary['result_sha256'],
                    'observations': actual['observations'], 'paired_summary_sha256': sha(canonical(actual['result']['paired_summary']).encode()),
                    'adverse_count': len(actual['result'].get('adverse_queries', actual['result']['paired_summary'].get('adverse_cases', [])))}
        save(root/'actual-primary-feedback.json', feedback)
        basis = 'Actual completed action '+primary['id']+' result sha256:'+primary['result_sha256']+'. Feedback sha256:'+sha(read(root/'actual-primary-feedback.json'))+'. Adverse count '+str(feedback['adverse_count'])+'. Inspect the saved evidence without a new solve/ranking or default promotion.'
        save_plan(2, basis, 'Saved-only arithmetic/identity/feasibility audit of this exact completed action; no new primary execution.')
        with disabled(modules):
            advance('audit', case['audit'])
        audit = project.status()['actions'][1]
        save_plan(3, 'Actual saved-only audit '+audit['id']+' result sha256:'+audit['result_sha256']+'. '+freeze['known_results'],
                  'Wait. Preserve both fixed arms, adverse results and all source/result identities; broader claims need a separately characterized task.')
        advance('wait', None)
        state = project.status()
        require(len(state['actions']) == 2 and state['research_status'] == 'waiting'
                and len(state['plan_revisions']) == 3, 'Unexpected final lifecycle')
        b = state['budget']
        require(b['local_tool_calls_used'] == 2 and b['local_tool_calls_reserved'] == 0
                and b['new_fits'] == 0 and b['fit_attempts_used'] == 0
                and b['new_model_requests'] == 0 and b['evidence_reads_used'] == 0, 'Budget mismatch')
        export = {'request_id': 'native-report', 'project_id': project_id, 'expected_state_version': state['state_version']}
        with disabled(modules):
            report = stage('report', 'LocalWorkbench.export', export, lambda: manager.export(export))
        require(not any(guard_calls.values()), 'A forbidden fit/network/source operation was attempted')
        after = identities(protected_paths())
        save(root/'protected-after.json', after)
        require(after == freeze['protected'], 'Original protected evidence changed')
        save(root/'final-project-status.json', project.status())
        save(root/'result.json', {'schema_version': 'g5-native-cpu-result-v1', 'status': 'completed',
                                 'case': freeze['case'], 'engineering_fixture': freeze['engineering_fixture'],
                                 'project_id': project_id, 'project_root': str(project.root),
                                 'freeze_sha256': sha(freeze_raw), 'budget': b, 'plan_revisions': 3,
                                 'research_status': 'waiting', 'report': report, 'protected_originals_equal': True,
                                 'known_results': freeze['known_results'], 'automatic_promotion': False,
                                 'guard_call_counts': guard_calls,
                                 'api_calls': 0, 'development_token_currency_costs': None})
    except BaseException as error:
        if not (root/'protected-after.json').exists():
            save(root/'protected-after.json', identities(protected_paths()))
        save(root/'worker-error.json', {'type': type(error).__name__, 'message': str(error),
                                       'budget': budget(), 'guard_call_counts': guard_calls,
                                       'automatic_retry': False})
        raise
    finally:
        guards.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_subparsers(dest='mode', required=True)
    prep = modes.add_parser('prepare')
    prep.add_argument('--case', choices=CASES, required=True)
    prep.add_argument('--output', type=Path, required=True)
    prep.add_argument('--packet', type=Path)
    prep.add_argument('--code-commit', required=True)
    prep.add_argument('--engineering-fixture', action='store_true')
    execute = modes.add_parser('run')
    execute.add_argument('--output', type=Path, required=True)
    execute.add_argument('--review', type=Path, required=True)
    child = modes.add_parser('_worker', help=argparse.SUPPRESS)
    child.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.mode == 'prepare':
        prepare(args)
    elif args.mode == 'run':
        run(args)
    else:
        worker(args.output.absolute())


if __name__ == '__main__':
    main()
