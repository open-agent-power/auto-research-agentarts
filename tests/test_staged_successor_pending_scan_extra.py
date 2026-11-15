"""Extra isolated, synthetic checks of the bounded successor pending scan."""
import copy
import hashlib
import json
from pathlib import Path
import unittest
from urllib.parse import urlencode

from autoresearch.contracts import canonical, fingerprint
import test_local_workbench_http as http
from staged_successor_http_fixture import request as successor_request
import test_staged_feedback_successor_plan as fixtures


class SuccessorPendingScanExtraTests(unittest.TestCase):
    serve = http.LocalWorkbenchHTTPTests.serve
    request = successor_request
    session = http.LocalWorkbenchHTTPTests.session

    def fixture(self):
        manager, project, _, _, body = fixtures.StagedFeedbackSuccessorPlanTests.fixture(self, 'wait')
        server = self.serve(local_workspace=manager, allow_local_actions=True)
        return manager, project, body, server

    def query(self, project):
        state = project.status()
        return '/api/local-workbench/staged-feedback-plan-pending.json?' + urlencode({
            'project_id': state['id'], 'snapshot_ref': state['snapshot_ref']})

    def get(self, server, query):
        return self.request(server, query)

    @staticmethod
    def hashes(manager, project):
        return tuple(hashlib.sha256(path.read_bytes()).hexdigest() for path in (manager.db, project.db))

    def test_other_project_completed_and_preparing_with_old_identity_do_not_block(self):
        manager, project, body, server = self.fixture()
        other_manager, other_project, other_body, _ = self.fixture()
        other_manager.save_staged_feedback_plan(other_body)
        with other_manager._connect(readonly=True) as con:
            row = con.execute('SELECT record FROM requests WHERE id=?', (other_body['request_id'],)).fetchone()
        completed = json.loads(row['record'])
        intent = completed['intent']
        # Synthetic historical producer identities, without changing either Project.
        intent['project_code_identity'] = '1' * 64
        intent['controller_code_identity'] = '2' * 64
        intent['manager_code_identity'] = '3' * 64
        intent['intent_sha256'] = fingerprint({k: v for k, v in intent.items() if k != 'intent_sha256'})
        pending = copy.deepcopy(completed)
        pending['status'], pending['result'] = 'preparing', None
        pending_intent = pending['intent']
        pending_intent['body']['request_id'] = 'other-synthetic-pending'
        pending_intent['request_sha256'] = fingerprint(pending_intent['body'])
        pending_intent['intent_sha256'] = fingerprint({k: v for k, v in pending_intent.items() if k != 'intent_sha256'})
        with manager._connect() as con:
            con.execute('INSERT INTO projects VALUES(?,?,?,NULL)', (other_project.status()['id'], 'synthetic other', 'f' * 64))
            for record in (completed, pending):
                i = record['intent']
                con.execute('INSERT INTO requests VALUES(?,?,?,?)', (i['body']['request_id'], i['request_sha256'], i['command'], canonical(record)))
        before = self.hashes(manager, project)
        status, result = self.get(server, self.query(project))
        self.assertEqual((status, result['status'], result['total'], result['items']), (200, 'available', 0, []))
        self.assertEqual(result['verification'], 'manager_rows_only_not_project_claims')
        self.assertEqual(self.hashes(manager, project), before)

    def test_malformed_digest_intent_body_and_receipt_never_appear_clear(self):
        manager, project, body, server = self.fixture()
        manager.save_staged_feedback_plan(body)
        query = self.query(project)
        with manager._connect(readonly=True) as con:
            row = con.execute('SELECT digest,record FROM requests WHERE id=?', (body['request_id'],)).fetchone()
        original_digest, original_record = row['digest'], row['record']
        for mode in ('digest', 'intent', 'body', 'receipt'):
            with self.subTest(mode=mode):
                record = json.loads(original_record)
                digest = original_digest
                if mode == 'digest':
                    digest = '0' * 64
                elif mode == 'intent':
                    record['intent']['intent_sha256'] = '0' * 64
                elif mode == 'body':
                    record['intent']['body']['plan']['question'] = ''
                    digest = fingerprint(record['intent']['body'])
                    record['intent']['request_sha256'] = digest
                    record['intent']['intent_sha256'] = fingerprint({k: v for k, v in record['intent'].items() if k != 'intent_sha256'})
                else:
                    record['result']['research_plan']['staged_feedback_ref']['feedback_parent_request_id'] = 'incorrect'
                with manager._connect() as con:
                    con.execute('UPDATE requests SET digest=?,record=? WHERE id=?', (digest, canonical(record), body['request_id']))
                before = self.hashes(manager, project)
                status, result = self.get(server, query)
                self.assertEqual((status, result['status'], result['total'], result['items']), (200, 'unknown', None, []))
                self.assertEqual(self.hashes(manager, project), before)
        with manager._connect() as con:
            con.execute('UPDATE requests SET digest=?,record=? WHERE id=?', (original_digest, original_record, body['request_id']))

    def test_database_sidecars_including_dangling_links_fail_closed(self):
        manager, project, body, server = self.fixture()
        query = self.query(project)
        before = self.hashes(manager, project)
        for database in (manager.db, project.db):
            for suffix in ('-wal', '-shm', '-journal'):
                for dangling in (False, True):
                    with self.subTest(database=database.name, suffix=suffix, dangling=dangling):
                        sidecar = Path(str(database) + suffix)
                        if dangling:
                            sidecar.symlink_to('missing-synthetic-target')
                        else:
                            sidecar.write_bytes(b'synthetic-sidecar')
                        try:
                            status, _ = self.get(server, query)
                            self.assertNotEqual(status, 200)
                            self.assertEqual(self.hashes(manager, project), before)
                        finally:
                            sidecar.unlink()

    def test_wrong_active_project_snapshot_and_disabled_service(self):
        manager, project, body, server = self.fixture()
        state = project.status()
        before = self.hashes(manager, project)
        for project_id, snapshot in ((state['id'], '0' * 64), ('other-project', state['snapshot_ref'])):
            query = '/api/local-workbench/staged-feedback-plan-pending.json?' + urlencode({'project_id': project_id, 'snapshot_ref': snapshot})
            self.assertNotEqual(self.get(server, query)[0], 200)
            self.assertEqual(self.hashes(manager, project), before)
        disabled = self.serve(local_workspace=manager, allow_local_actions=False)
        for root in (manager.root, project.root):
            lock = root / 'writer.lock'
            if lock.exists():
                lock.unlink()
        self.assertEqual(self.get(disabled, self.query(project))[0], 405)
        for root in (manager.root, project.root):
            self.assertFalse((root / 'writer.lock').exists())
        self.assertEqual(self.hashes(manager, project), before)


if __name__ == '__main__':
    unittest.main()
