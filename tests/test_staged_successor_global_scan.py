"""Synthetic manager-only successor pending scans, without real research."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from autoresearch.contracts import canonical, fingerprint
from autoresearch.local_workbench import LocalWorkbench
import test_local_workbench_http as http
from staged_successor_http_fixture import request as successor_request
import test_staged_feedback_successor_plan as fixtures


ROUTE = '/api/local-workbench/staged-feedback-plan-global-pending.json'


class SuccessorGlobalScanTests(unittest.TestCase):
    serve = http.LocalWorkbenchHTTPTests.serve
    request = successor_request

    def empty_manager(self):
        root = Path(self.enterContext(tempfile.TemporaryDirectory())) / 'synthetic-manager'
        return LocalWorkbench(root)

    @staticmethod
    def digest(path):
        return hashlib.sha256(path.read_bytes()).hexdigest()

    def test_empty_active_and_disabled_routes_do_not_change_database(self):
        manager = self.empty_manager()
        enabled = self.serve(local_workspace=manager, allow_local_actions=True)
        disabled = self.serve(local_workspace=manager, allow_local_actions=False)
        before = self.digest(manager.db)
        status, view = self.request(enabled, ROUTE)
        self.assertEqual((status, view['status'], view['total'], view['shown'], view['project_ids']),
                         (200, 'available', 0, 0, []))
        self.assertEqual(view['verification'], 'manager_rows_only_not_project_claims')
        self.assertFalse(view['truncated'])
        self.assertEqual(self.digest(manager.db), before)
        self.assertNotEqual(self.request(enabled, ROUTE + '?extra=1')[0], 200)
        with manager._connect() as con:
            con.execute("INSERT OR REPLACE INTO metadata VALUES('active_project_id','synthetic-active')")
        before = self.digest(manager.db)
        self.assertNotEqual(self.request(enabled, ROUTE)[0], 200)
        self.assertEqual(self.digest(manager.db), before)
        lock = manager.root / 'writer.lock'
        lock.unlink()
        self.assertEqual(self.request(disabled, ROUTE)[0], 405)
        self.assertFalse(lock.exists())
        self.assertEqual(self.digest(manager.db), before)
        for suffix in ('-wal', '-shm', '-journal'):
            self.assertFalse(Path(str(manager.db) + suffix).exists())

    def test_completed_pending_project_identity_and_nine_row_truncation(self):
        manager, project, _, _, body = fixtures.StagedFeedbackSuccessorPlanTests.fixture(self, 'wait')
        manager.save_staged_feedback_plan(body)
        with manager._connect() as con:
            row = con.execute('SELECT record FROM requests WHERE id=?', (body['request_id'],)).fetchone()
            completed = json.loads(row['record'])
            con.execute("DELETE FROM metadata WHERE key='active_project_id'")
            con.execute('INSERT INTO projects VALUES(?,?,?,NULL)', ('other-synthetic-project', 'unrelated', 'f' * 64))
        server = self.serve(local_workspace=manager, allow_local_actions=True)
        project_id = project.status()['id']
        before = (self.digest(manager.db), self.digest(project.db))
        status, view = self.request(server, ROUTE)
        self.assertEqual((status, view['status'], view['total'], view['project_ids']), (200, 'available', 0, []))
        self.assertEqual(before, (self.digest(manager.db), self.digest(project.db)))
        with manager._connect() as con:
            for index in range(9):
                record = copy.deepcopy(completed)
                record['status'], record['result'] = 'preparing', None
                intent = record['intent']
                intent['body']['request_id'] = 'synthetic-global-pending-' + str(index)
                intent['request_sha256'] = fingerprint(intent['body'])
                intent['intent_sha256'] = fingerprint({k: v for k, v in intent.items() if k != 'intent_sha256'})
                con.execute('INSERT INTO requests VALUES(?,?,?,?)',
                            (intent['body']['request_id'], intent['request_sha256'], intent['command'], canonical(record)))
        before = (self.digest(manager.db), self.digest(project.db))
        status, view = self.request(server, ROUTE)
        self.assertEqual((status, view['status'], view['total'], view['shown'], view['truncated']), (200, 'available', 9, 8, True))
        self.assertEqual(view['project_ids'], [project_id])
        self.assertNotIn('other-synthetic-project', view['project_ids'])
        self.assertNotIn('synthetic-global-pending-', json.dumps(view))
        self.assertEqual(before, (self.digest(manager.db), self.digest(project.db)))
        with manager._connect() as con:
            con.execute("DELETE FROM requests WHERE id LIKE 'synthetic-global-pending-%' AND id != 'synthetic-global-pending-0'")
        status, view = self.request(server, ROUTE)
        self.assertEqual((status, view['total'], view['project_ids']), (200, 1, [project_id]))
        with manager._connect() as con:
            row = con.execute("SELECT record FROM requests WHERE id='synthetic-global-pending-0'").fetchone()
            malformed = json.loads(row['record'])
            del malformed['intent']['body']['project_id']
            con.execute("UPDATE requests SET record=? WHERE id='synthetic-global-pending-0'", (canonical(malformed),))
        before = (self.digest(manager.db), self.digest(project.db))
        status, view = self.request(server, ROUTE)
        self.assertEqual((status, view['status'], view['total'], view['project_ids']), (200, 'unknown', None, []))
        self.assertEqual(before, (self.digest(manager.db), self.digest(project.db)))
        with manager._connect() as con:
            con.execute("UPDATE requests SET record='{' WHERE id='synthetic-global-pending-0'")
        self.assertEqual(self.request(server, ROUTE)[1]['status'], 'unknown')

    def test_sidecars_including_dangling_links_fail_closed(self):
        manager = self.empty_manager()
        server = self.serve(local_workspace=manager, allow_local_actions=True)
        before = self.digest(manager.db)
        for suffix in ('-wal', '-shm', '-journal'):
            for dangling in (False, True):
                with self.subTest(suffix=suffix, dangling=dangling):
                    sidecar = Path(str(manager.db) + suffix)
                    if dangling:
                        sidecar.symlink_to('missing-synthetic-target')
                    else:
                        sidecar.write_bytes(b'synthetic-sidecar')
                    try:
                        self.assertNotEqual(self.request(server, ROUTE)[0], 200)
                        self.assertEqual(self.digest(manager.db), before)
                    finally:
                        sidecar.unlink()


if __name__ == '__main__':
    unittest.main()
