#!/usr/bin/env python3
"""Replay completed native CPU requests only, optionally from a copied manager.

No create, new IDs, computation, rendering, fitting or network. Relocation changes
receiver storage roots in memory, never saved request bodies or project identity.
File/database guards demonstrate no fallback to old storage, not OS isolation.
"""
import argparse
import builtins
from contextlib import ExitStack
import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import sqlite3
import subprocess
import sys
import traceback
from unittest.mock import patch
from urllib.parse import unquote

REPO = Path(__file__).resolve().parents[1]
ORDER = ('01-create', '02-source-cap', '03-import', '04-select', 'plan1', 'primary',
         'primary-replay', 'plan2', 'audit', 'audit-replay', 'plan3', 'wait', 'wait-replay', 'report')
METHODS = {'retrieval': ('research.retrieval-fixed-pair', 'research.retrieval-saved-error-audit'),
           'scheduling': ('research.weighted-interval-fixed-pair', 'research.weighted-interval-saved-audit')}
sys.dont_write_bytecode = True


def require(value, message):
    if not value:
        raise AssertionError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def read(path):
    require(path.is_file() and not path.is_symlink() and path.stat().st_size <= 64_000_000, 'Invalid saved file: '+str(path))
    return path.read_bytes()


def js(path):
    return json.loads(read(path))


def tree(root):
    result = {}
    for path in sorted(root.rglob('*')):
        require(not path.is_symlink(), 'Linked storage is not supported')
        if path.is_file():
            raw = read(path)
            result[str(path.relative_to(root))] = {'sha256': sha(raw), 'bytes': len(raw), 'mode': path.stat().st_mode & 0o777}
    return result


def save(path, value):
    with path.open('x', encoding='utf-8') as stream:
        stream.write(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)+'\n')


def normalize(value):
    if type(value) is dict:
        return {key: normalize(item) for key, item in value.items() if not (key == 'replayed' and type(item) is bool)}
    if type(value) is list:
        return [normalize(item) for item in value]
    return value


def replay(case, output, source_root, copy_to=None):
    case, output = case.absolute(), output.absolute()
    source_root = source_root.absolute()
    manager_original = case/'manager'
    manager_root = copy_to.absolute() if copy_to else manager_original
    require(not output.exists() and not output.is_relative_to(case) and not case.is_relative_to(output), 'Fresh output outside the case required')
    if copy_to:
        require(not manager_root.exists() and not manager_root.is_relative_to(case) and not case.is_relative_to(manager_root), 'Fresh, separate manager copy required')
        require(not output.is_relative_to(manager_root) and not manager_root.is_relative_to(output), 'Output and copy must not overlap')
    original_before = tree(case)  # Capture the whole case before any native object opens it.
    output.mkdir(parents=True)
    save(output/'original-before.json', original_before)
    checks, records, forbidden, storage_reads = [], [], [], set()
    def check(name, value):
        checks.append({'name': name, 'passed': bool(value)})
        require(value, name)
    def deny(label):
        def fail(*args, **kwargs):
            forbidden.append(label)
            raise AssertionError('Replay forbids '+label)
        return fail
    try:
        freeze, result, expected, relocation = (js(case/name) for name in ('freeze.json', 'result.json', 'final-project-status.json', 'project-relocation.json'))
        check('completed_real_case', result['status'] == 'completed' and result['engineering_fixture'] is False
              and js(case/'attempt-final.json')['status'] == 'completed' and freeze['case'] in METHODS)
        check('freeze_and_scope', result['freeze_sha256'] == sha(read(case/'freeze.json')) and freeze['output_root'] == str(case.resolve())
              and freeze['allowance'] == {'local_tools': 2, 'fits': 0, 'models': 0, 'evidence_reads': 0})
        check('pinned_source_HEAD', subprocess.check_output(['git', '-C', str(source_root), 'rev-parse', 'HEAD']).decode().strip() == freeze['code_commit'])
        check('pinned_source_clean', not subprocess.check_output(['git', '-C', str(source_root), 'status', '--porcelain']))
        check('frozen_code_files', all(len(read(source_root/name)) == identity['bytes'] and sha(read(source_root/name)) == identity['sha256']
                                       for name, identity in freeze['code_files'].items()))
        check('unmanaged_root_is_gone', not Path(relocation['original_project_root']).exists()
              and relocation['create_at_original_root_after_import_forbidden'] is True)
        original_project = Path(relocation['relocated_project_root'])
        relative_project = original_project.relative_to(manager_original)
        steps = {name: {'request': js(case/'steps'/(name+'-request.json')), 'result': js(case/'steps'/(name+'-result.json'))['result']}
                 for name in ORDER}
        check('complete_step_inventory', {p.name for p in (case/'steps').glob('*-request.json')} == {name+'-request.json' for name in ORDER})
        contexts = {name: js(case/'steps'/(name+'-context.json')) for name in ('primary', 'audit', 'wait')}
        if copy_to:
            shutil.copytree(manager_original, manager_root)
        manager_before = tree(manager_root)
        save(output/'manager-before.json', manager_before)
        check('complete_manager_copy', manager_before == tree(manager_original))
        project_root = manager_root/relative_project
        check('existing_databases_only', (manager_root/'workbench.sqlite').is_file() and (project_root/'project.sqlite').is_file())
        with sqlite3.connect((manager_root/'workbench.sqlite').as_uri()+'?mode=ro&immutable=1', uri=True) as db:
            accepted = {row[0]: row[1] for row in db.execute('SELECT id,digest FROM requests')}
        # Verify every replay ID before allowing public methods to run. Import's
        # internal canonical envelope includes its unchanged optional None field.
        for name in ORDER[1:]:
            request = steps[name]['request'];body = request['replay_body']
            check('unchanged_request_body:'+name, canonical(body) == canonical(request['body']) and type(body.get('request_id')) is str)
            if request['command'].startswith('LocalWorkbench.'):
                hashed = {**body, 'platform_run': None} if request['command'] == 'LocalWorkbench.import_project' else body
                check('previously_accepted_manager_ID:'+name, accepted.get(body['request_id']) == sha(canonical(hashed).encode()))
        check('no_prior_autoresearch_import', not any(name == 'autoresearch' or name.startswith('autoresearch.') for name in sys.modules))
        sys.path.insert(0, str(source_root/'src'))
        from autoresearch import retrieval_adapter, retrieval_lexical, scheduling_adapter, scheduling_kernel
        from autoresearch import research_project, method_registry, source_evidence_adapter, project_report
        from autoresearch.local_workbench import LocalWorkbench
        from autoresearch.project_controller import ProjectController
        from autoresearch.model_client import ChatClient
        from autoresearch.host_model_selection import HostModelSelection
        from sklearn.linear_model import Ridge
        from sklearn.preprocessing import StandardScaler
        real_open, real_path_open, real_os_open, real_connect = builtins.open, Path.open, os.open, sqlite3.connect
        blocked = [case, Path(freeze['packet_original_path'])] if copy_to else []
        def path_access(value):
            if isinstance(value, int):
                return
            text = os.fsdecode(value)
            if text.startswith('file:'):
                text = unquote(text[5:].split('?', 1)[0])
            path = Path(os.path.abspath(text))
            if any(path == root or path.is_relative_to(root) for root in blocked):
                forbidden.append('original-storage:'+str(path))
                raise AssertionError('Relocation attempted original file/database access: '+str(path))
            if path.is_relative_to(manager_root):
                storage_reads.add(str(path.relative_to(manager_root)))
        def guarded_open(file, *args, **kwargs):
            path_access(file);return real_open(file, *args, **kwargs)
        def guarded_path_open(path, *args, **kwargs):
            path_access(path);return real_path_open(path, *args, **kwargs)
        def guarded_os_open(path, *args, **kwargs):
            path_access(path);return real_os_open(path, *args, **kwargs)
        def guarded_connect(database, *args, **kwargs):
            path_access(database);return real_connect(database, *args, **kwargs)
        with ExitStack() as guard:
            for module, names in ((retrieval_lexical, ('tokens', 'build_index', 'retrieve', 'metrics')),
                                  (scheduling_kernel, ('schedule', 'brute_force', 'jobs_for')),
                                  (retrieval_adapter, ('execute',)), (scheduling_adapter, ('execute',)),
                                  (retrieval_adapter.AUDIT, ('execute_saved',)), (scheduling_adapter.AUDIT, ('execute_saved',)),
                                  (research_project.ResearchProject, ('create',)), (LocalWorkbench, ('create',)),
                                  (Ridge, ('fit',)), (StandardScaler, ('fit',)),
                                  (source_evidence_adapter, ('execute',)), (project_report, ('export_report',)),
                                  (ChatClient, ('complete',)), (HostModelSelection, ('request',)),
                                  (socket.socket, ('connect', 'connect_ex', 'sendto')),
                                  (socket, ('create_connection', 'getaddrinfo')), (subprocess, ('Popen',)),
                                  (scheduling_adapter.time, ('perf_counter',))):
                for attribute in names:
                    guard.enter_context(patch.object(module, attribute, side_effect=deny(str(getattr(module, '__name__', type(module).__name__))+'.'+attribute)))
            for module, name, function in ((builtins, 'open', guarded_open), (Path, 'open', guarded_path_open),
                                           (os, 'open', guarded_os_open), (sqlite3, 'connect', guarded_connect)):
                guard.enter_context(patch.object(module, name, new=function))
            manager = LocalWorkbench(manager_root)
            project, report_root = manager.binding()
            check('same_managed_project', project is not None and project.root == project_root and project.status() == expected)
            check('runtime_and_source_code_identity', research_project.code_identity() == freeze['project_code_identity'] == expected['code_identity']
                  and method_registry.runtime_dependencies() == freeze['runtime_dependencies'])
            state = project.status()
            check('waiting_three_plans_two_actions', state['research_status'] == 'waiting' and len(state['plan_revisions']) == 3
                  and len(state['actions']) == 2 and not state['evidence_actions'])
            budget = state['budget']
            check('exact_complete_budget', budget == result['budget'] and budget['local_tool_call_limit'] == budget['local_tool_calls_used'] == 2
                  and all(budget[key] == 0 for key in ('local_tool_calls_reserved', 'fit_limit', 'fit_attempts_used', 'fits_reserved',
                      'new_fits', 'new_model_requests', 'model_requests_reserved', 'evidence_read_limit', 'evidence_reads_used', 'evidence_reads_reserved')))
            payload = project._source(state)
            check('source_loaded_from_actual_manager', payload['snapshot_sha256'] == freeze['snapshot_sha256']
                  and sha((project.root/'source.json').read_bytes()) == freeze['packet_sha256'])
            check('project_and_run_identity', state['id'] == result['project_id'] == relocation['project_id'] and state['run_id'] == expected['run_id'])
            parents = {parent['request_id']: parent for parent in state['controller_requests']}
            for name in ('primary', 'audit', 'wait'):
                context = contexts[name];body = steps[name]['request']['body'];parent = parents[body['request_id']]
                check('saved_context_and_request:'+name, parent['selection_context'] == context
                      and context['context_sha256'] == sha(canonical({k:v for k,v in context.items() if k != 'context_sha256'}).encode())
                      and parent['request']['proposal'] == body['proposal'] and body['proposal']['context_sha256'] == context['context_sha256'])
            first, second = state['actions']
            check('exact_primary_audit_ancestry', [a['command'] for a in state['actions']] == list(METHODS[freeze['case']])
                  and second['parameters'] == {'based_on_action_id': first['id'], 'based_on_result_sha256': first['result_sha256']}
                  and parents['native-primary']['child_request_id'] == first['request_id']
                  and parents['native-audit']['child_request_id'] == second['request_id']
                  and all(a['status'] == 'completed' and a['project_id'] == state['id'] for a in state['actions']))
            current_context = ProjectController(project.root).selection_context()
            save(output/'next-context-before.json', current_context)
            for name in ORDER:
                request, wanted = steps[name]['request'], steps[name]['result']
                if name == '01-create':
                    check('no_ID_create_not_replayed', request['command'] == 'ResearchProject.create' and 'request_id' not in request['body'])
                    records.append({'step': name, 'status': 'skipped_non_idempotent_create'})
                    continue
                body = request['replay_body'];receiver = request['receiver_ref'];command = request['command']
                check('approved_original_receiver:'+name, receiver['project_root'] in (relocation['original_project_root'], relocation['relocated_project_root'])
                      and (receiver['workbench_root'] == str(manager_original) if command.startswith('LocalWorkbench.') else receiver['workbench_root'] is None))
                if command == 'ResearchProject.limit_evidence_budget':
                    actual = project.limit_evidence_budget(**body)
                elif command == 'LocalWorkbench.import_project':
                    actual = manager.import_project(**body)
                elif command in ('LocalWorkbench.select', 'LocalWorkbench.save_plan', 'LocalWorkbench.advance', 'LocalWorkbench.export'):
                    actual = getattr(manager, command.split('.')[1])(body)
                else:
                    raise AssertionError('Unapproved saved command: '+command)
                check('exact_saved_response:'+name, canonical(normalize(actual)) == canonical(normalize(wanted)))
                check('budget_after_replay:'+name, project.status()['budget'] == budget)
                records.append({'step': name, 'command': command, 'request_id': body['request_id'], 'response': actual,
                                'request_body_changed': False, 'receiver_project': str(project.root), 'receiver_manager': str(manager.root)})
            for action in state['actions']:
                body = {'request_id': action['request_id'], 'method_id': action['command'], 'dimension': action.get('dimension')}
                if action.get('parameters') is not None:
                    body['parameters'] = action['parameters']
                actual = project.step(**body)
                check('exact_core_child:'+action['id'], canonical(normalize(actual)) == canonical(normalize(action)))
                records.append({'command': 'ResearchProject.step', 'body': body, 'response': actual})
            for plan in state['plan_revisions']:
                body = {'request_id': plan['request_id'], 'expected_state_version': plan['based_on_state_version'],
                        'reason': plan['reason'], 'plan': {key:plan[key] for key in ('question', 'basis', 'steps', 'expected_feedback')}}
                actual = project.save_plan(**body)
                check('exact_core_plan:'+plan['request_id'], actual == plan)
                records.append({'command': 'ResearchProject.save_plan', 'body': body, 'response': actual})
            manifest = js(report_root/'manifest.json')
            check('exact_four_report_files', manifest == result['report']['manifest']
                  and set(manifest['files']) == {'report.json', 'report.md', 'report.pdf', 'input.json'})
            for name, identity in manifest['files'].items():
                raw = read(report_root/name)
                check('report_original_bytes:'+name, len(raw) == identity['bytes'] and sha(raw) == identity['sha256'])
            check('entire_final_state_unchanged', project.status() == state)
            check('same_next_context', ProjectController(project.root).selection_context() == current_context)
            check('no_forbidden_operation', not forbidden)
            check('copied_source_was_accessed', str((project_root/'source.json').relative_to(manager_root)) in storage_reads)
            module_origins = {name: str(Path(module.__file__).absolute()) for name, module in sys.modules.items()
                              if (name == 'autoresearch' or name.startswith('autoresearch.')) and getattr(module, '__file__', None)}
            check('all_autoresearch_module_origins_pinned', bool(module_origins)
                  and all(Path(path).is_relative_to(source_root/'src') for path in module_origins.values()))
            save(output/'state-before.json', state)
            save(output/'state-after.json', project.status())
    except Exception as error:
        checks.append({'name': 'replay_exception', 'passed': False, 'error': {'type': type(error).__name__, 'message': str(error), 'traceback': traceback.format_exc()}})
    manager_after = tree(manager_root) if manager_root.exists() else {}
    original_after = tree(case)
    checks.append({'name': 'whole_original_case_bytes_and_modes_unchanged', 'passed': original_before == original_after})
    checks.append({'name': 'whole_manager_bytes_and_modes_unchanged', 'passed': 'manager_before' in locals() and manager_before == manager_after})
    save(output/'original-after.json', original_after)
    save(output/'manager-after.json', manager_after)
    receipt = {'schema_version': 'native-cpu-independent-exact-replay-v1', 'passed': all(item['passed'] for item in checks),
               'case': str(case), 'manager': str(manager_root), 'source_root': str(source_root),
               'module_origins': locals().get('module_origins', {}), 'relocated': bool(copy_to), 'checks': checks, 'records': records,
               'forbidden_calls': forbidden, 'actual_manager_accesses': sorted(storage_reads), 'helper_sha256': sha(read(Path(__file__))),
               'normalization': ['boolean replayed metadata only; no request body, ID, budget, result, path or scientific field rewritten'],
               'storage_policy': 'Receiver storage roots only are mapped in memory. Relocation denies original file/database opens; path canonicalization/stat is not OS isolation.',
               'no_new_import_or_create': True, 'new_fit_rank_index_score_solve_api_calls': 0, 'real_new_native_actions': 0}
    save(output/'replay.json', receipt)
    replayed_count = sum(record.get('status') != 'skipped_non_idempotent_create' for record in records)
    print(json.dumps({'passed': receipt['passed'], 'checks': len(checks), 'replayed_requests': replayed_count, 'relocated': bool(copy_to), 'output': str(output)}))
    return 0 if receipt['passed'] else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--case', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--source-root', type=Path, required=True, help='Clean frozen source checkout, imported before any autoresearch module')
    parser.add_argument('--copy-to', type=Path, help='Fresh copy of the entire saved manager, outside the original case')
    args = parser.parse_args()
    return replay(args.case, args.output, args.source_root, args.copy_to)


if __name__ == '__main__':
    raise SystemExit(main())
