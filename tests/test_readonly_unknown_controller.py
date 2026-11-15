"""Read-only host inspection of synthetic pending parents; no external requests."""
import copy
import hashlib
import os
from pathlib import Path
import sqlite3
import unittest
from unittest.mock import patch

import test_workbench_unknown_projection as fixture
import test_local_workbench as manager_fixture
import test_local_workbench_http as http
from autoresearch import stored_project_summary
from autoresearch.contracts import ResearchError, fingerprint
from autoresearch.local_workbench import LocalWorkbench, _InspectionProject
from autoresearch.project_controller import ProjectController
from autoresearch.research_project import ResearchProject


class ReadOnlyUnknownTests(unittest.TestCase):
    setUp = manager_fixture.LocalWorkbenchTests.setUp
    create_body = manager_fixture.LocalWorkbenchTests.create_body
    proposal = manager_fixture.LocalWorkbenchTests.proposal
    unknown = fixture.UnknownControllerProjectionTests.unknown
    serve = http.LocalWorkbenchHTTPTests.serve
    request = http.LocalWorkbenchHTTPTests.request

    def snapshot(self):
        result = {}
        for path in self.root.rglob('*'):
            key = str(path.relative_to(self.root))
            if path.is_symlink(): result[key] = ('link', os.readlink(path))
            elif path.is_dir(): result[key] = ('directory',)
            else: result[key] = ('file', hashlib.sha256(path.read_bytes()).hexdigest())
        return result

    def test_http_saved_unknown_has_immutable_database_reads_and_zero_writes(self):
        project, body = self.unknown(complete_child=True)
        state = project.status()
        before = self.snapshot()
        manager = LocalWorkbench.open_readonly(self.root)
        server = self.serve(local_workspace=manager, allow_local_actions=False)
        path = ('/api/local-workbench/unknown-controller-requests.json?project_id=' + state['id']
                + '&snapshot_ref=' + state['snapshot_ref'])
        with patch('sqlite3.connect', wraps=sqlite3.connect) as connect, \
             patch.object(ResearchProject, '_writer', side_effect=AssertionError('no lock or write')), \
             patch.object(ResearchProject, 'step', side_effect=AssertionError('no step')), \
             patch.object(ProjectController, '_dispatch', side_effect=AssertionError('no dispatch')):
            status, result = self.request(server, path)
            self.assertEqual(status, 200)
            self.assertTrue(connect.call_args_list)
            for call in connect.call_args_list:
                self.assertIn('?mode=ro&immutable=1', str(call.args[0]))
            self.assertEqual((result['items'][0]['request_id'], result['items'][0]['child_status']),
                             (body['request_id'], 'completed'))
            self.assertFalse(result['recovery_verified'])
            self.assertEqual(self.request(server, '/api/local-workbench/advance', 'POST', b'{}')[0], 405)
            self.assertEqual(self.request(server, path + '&project_id=extra')[0], 400)
            stale = path.replace(state['snapshot_ref'], '0' * 64)
            self.assertEqual(self.request(server, stale)[0], 409)
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(project.status()['budget'], state['budget'])

    def test_database_sidecars_including_dangling_links_are_rejected(self):
        project, _ = self.unknown()
        state = project.status()
        manager = LocalWorkbench.open_readonly(self.root)
        original = self.snapshot()
        for db in (manager.db, project.db):
            for suffix in ('-wal', '-shm', '-journal'):
                for dangling in (False, True):
                    sidecar = Path(str(db) + suffix)
                    with self.subTest(db=db.name, suffix=suffix, dangling=dangling):
                        if dangling: sidecar.symlink_to('missing-target')
                        else: sidecar.write_bytes(b'synthetic-unresolved-sidecar')
                        try:
                            with self.assertRaises(ResearchError) as error:
                                manager.read_unknown_controller_requests(project_id=state['id'], snapshot_ref=state['snapshot_ref'])
                            self.assertEqual(error.exception.code, 'WORKBENCH_CHANGED')
                            self.assertTrue(sidecar.is_symlink() if dangling else sidecar.is_file())
                        finally:
                            sidecar.unlink()
        self.assertEqual(self.snapshot(), original)

    def test_factory_rejects_dangling_manager_sidecars(self):
        self.unknown()
        original = self.snapshot()
        for suffix in ('-wal', '-shm', '-journal'):
            sidecar = Path(str(self.manager.db) + suffix)
            with self.subTest(suffix=suffix):
                sidecar.symlink_to('missing-target')
                try:
                    with self.assertRaises(ResearchError) as error:
                        LocalWorkbench.open_readonly(self.root)
                    self.assertEqual(error.exception.code, 'WORKBENCH_CHANGED')
                    self.assertTrue(sidecar.is_symlink())
                finally:
                    sidecar.unlink()
        self.assertEqual(self.snapshot(), original)

    def test_project_file_identity_change_during_read_fails_closed(self):
        project, _ = self.unknown()
        state = project.status()
        manager = LocalWorkbench.open_readonly(self.root)
        original = self.snapshot()
        identity = stored_project_summary._identity
        observed = []
        def changing(path):
            value = identity(path)
            if path == project.db:
                observed.append(value)
                if len(observed) == 2:
                    return (*value[:-1], value[-1] + 1)
            return value
        with patch.object(stored_project_summary, '_identity', side_effect=changing):
            with self.assertRaises(ResearchError) as error:
                manager.read_unknown_controller_requests(project_id=state['id'], snapshot_ref=state['snapshot_ref'])
        self.assertEqual(error.exception.code, 'WORKBENCH_CHANGED')
        self.assertEqual(len(observed), 2)
        self.assertEqual(self.snapshot(), original)

    def test_readonly_http_preserves_mismatched_original_identity(self):
        project, body = self.unknown(complete_child=True)
        with project._writer(), project._connect() as con:
            saved = project._project(con)
            saved['code_identity'] = 'f' * 64
            saved['state_version'] += 1
            project._save(con, saved)
        state = project.status()
        before = self.snapshot()
        manager = LocalWorkbench.open_readonly(self.root)
        server = self.serve(local_workspace=manager, allow_local_actions=False)
        path = ('/api/local-workbench/unknown-controller-requests.json?project_id=' + state['id']
                + '&snapshot_ref=' + state['snapshot_ref'])
        status, view = self.request(server, path)
        self.assertEqual((status, view['items'][0]['request_id'], view['items'][0]['identity_binding']),
                         (200, body['request_id'], 'mismatch'))
        self.assertEqual(view['items'][0]['current_project_code_identity'], 'f' * 64)
        self.assertFalse(view['recovery_verified'])
        self.assertEqual(self.snapshot(), before)

    def test_readonly_http_reports_limited_synthetic_projection(self):
        project, _ = self.unknown()
        state = project.status()
        many = copy.deepcopy(state)
        parent, child = many['controller_requests'][-1], many['actions'][-1]
        many['controller_requests'], many['actions'] = [], []
        for n in range(9):
            p, c = copy.deepcopy(parent), copy.deepcopy(child)
            p['request_id'] = 'limited-example-' + str(n)
            child_id = 'controller-child-' + fingerprint({'project_id': state['id'], 'request_id': p['request_id']})[:32]
            p['child_request_id'] = p['result']['child']['request_id'] = c['request_id'] = child_id
            many['controller_requests'].append(p)
            many['actions'].append(c)
        before = self.snapshot()
        manager = LocalWorkbench.open_readonly(self.root)
        server = self.serve(local_workspace=manager, allow_local_actions=False)
        path = ('/api/local-workbench/unknown-controller-requests.json?project_id=' + state['id']
                + '&snapshot_ref=' + state['snapshot_ref'])
        # Synthetic state injection checks projection limits; it is not a
        # claim that nine unresolved operations were created or executed.
        with patch.object(_InspectionProject, 'status', return_value=many):
            status, view = self.request(server, path)
        self.assertEqual((status, view['total'], view['shown'], view['truncated']), (200, 9, 8, True))
        self.assertEqual(self.snapshot(), before)


if __name__ == '__main__':
    unittest.main()
