"""Resume-only S101 entry point: never create a replacement intent."""
import json
import sqlite3
import unittest
from unittest.mock import patch
from autoresearch.contracts import ResearchError, canonical, fingerprint
from autoresearch.host_model_selection import HostModelSelection
import test_host_supplied_quality_workbench as fixtures


class SuppliedQualityResumeTests(unittest.TestCase):
    def stage(self):
        helper = fixtures.SuppliedQualityWorkbenchTests('runTest')
        result = helper.stage()
        self.addCleanup(helper.doCleanups)
        return result

    def test_absent_or_deleted_original_never_creates_intent(self):
        for removed in (False, True):
            with self.subTest(removed=removed):
                f, manager, host, body, _ = self.stage()
                if removed:
                    manager.model_supplied_quality_plan_adopt(body)
                    with sqlite3.connect(manager.db) as con:
                        con.execute('DELETE FROM requests WHERE id=?', (body['request_id'],))
                before = (manager.db.read_bytes(), f.project.db.read_bytes(), host.state_file.read_bytes())
                with self.assertRaises(ResearchError) as error:
                    manager.resume_supplied_quality_plan_adopt(body)
                self.assertEqual(error.exception.code, 'OPERATION_INCOMPLETE')
                self.assertEqual(before, (manager.db.read_bytes(), f.project.db.read_bytes(), host.state_file.read_bytes()))

    def test_same_body_wrong_command_is_rejected(self):
        f, manager, host, body, _ = self.stage()
        with sqlite3.connect(manager.db) as con:
            con.execute('INSERT INTO requests(id,digest,command,record) VALUES(?,?,?,?)', (body['request_id'], fingerprint(body), 'save_plan',
                        canonical({'status':'preparing','intent':{},'result':None})))
        before = (manager.db.read_bytes(), f.project.db.read_bytes(), host.state_file.read_bytes())
        with self.assertRaises(ResearchError) as error:
            manager.resume_supplied_quality_plan_adopt(body)
        self.assertEqual(error.exception.code, 'OPERATION_INCOMPLETE')
        self.assertEqual(before, (manager.db.read_bytes(), f.project.db.read_bytes(), host.state_file.read_bytes()))

    def test_same_id_different_body_is_rejected(self):
        f, manager, host, body, _ = self.stage()
        with sqlite3.connect(manager.db) as con:
            con.execute('INSERT INTO requests(id,digest,command,record) VALUES(?,?,?,?)',
                        (body['request_id'], fingerprint(body), 'model_supplied_quality_plan_adopt',
                         canonical({'status':'preparing','intent':{},'result':None})))
        before = (manager.db.read_bytes(), f.project.db.read_bytes(), host.state_file.read_bytes())
        with self.assertRaises(ResearchError) as error:
            manager.resume_supplied_quality_plan_adopt({**body, 'registration_request_id':'other'})
        self.assertEqual(error.exception.code, 'IDEMPOTENCY_CONFLICT')
        self.assertEqual(before, (manager.db.read_bytes(), f.project.db.read_bytes(), host.state_file.read_bytes()))

    def test_unfinished_host_stops_but_terminal_replays(self):
        f, manager, host, body, _ = self.stage()
        with patch.object(HostModelSelection, '_adopt_manager_supplied_quality_plan', side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt): manager.model_supplied_quality_plan_adopt(body)
        before = (manager.db.read_bytes(), f.project.db.read_bytes(), host.state_file.read_bytes())
        with self.assertRaises(ResearchError) as error: manager.resume_supplied_quality_plan_adopt(body)
        self.assertEqual(error.exception.code, 'OPERATION_INCOMPLETE')
        self.assertEqual(before, (manager.db.read_bytes(), f.project.db.read_bytes(), host.state_file.read_bytes()))
        f2, manager2, host2, body2, _ = self.stage()
        original = manager2.model_supplied_quality_plan_adopt(body2)
        replay = manager2.resume_supplied_quality_plan_adopt(body2)
        self.assertTrue(replay['replayed'])
        self.assertEqual(replay['plan_sha256'], original['plan_sha256'])
        self.assertEqual(f2.project.status()['budget']['local_tool_calls_used'], 1)

    def test_resume_http_requires_local_origin_and_original_intent(self):
        f, manager, _, body, _ = self.stage()
        helper = fixtures.SuppliedQualityWorkbenchTests('runTest')
        self.addCleanup(helper.doCleanups)
        server = helper.serve(local_workspace=manager, allow_local_actions=True)
        headers = helper.session(server)
        route = '/api/local-workbench/model-supplied-quality-plan-resume'
        for h in ({**headers, 'Origin':'http://evil.invalid'}, {**headers, 'X-AutoResearch-CSRF':'bad'},
                  {**headers, 'Host':'external.invalid'}, {**headers, 'Sec-Fetch-Site':'cross-site'}):
            self.assertEqual(helper.request(server, route, 'POST', body, h)[0], 403)
        before = (manager.db.read_bytes(), f.project.db.read_bytes())
        status, result = helper.request(server, route, 'POST', body, headers)
        self.assertEqual((status, result['code']), (409, 'OPERATION_INCOMPLETE'))
        self.assertEqual(before, (manager.db.read_bytes(), f.project.db.read_bytes()))
        manager.model_supplied_quality_plan_adopt(body)
        status, result = helper.request(server, route, 'POST', body, headers)
        self.assertEqual(status, 200, result)
        self.assertTrue(result['replayed'])

if __name__ == '__main__': unittest.main()
