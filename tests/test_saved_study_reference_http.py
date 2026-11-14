"""Read-only HTTP access to the fixed study; no real study or project used."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import http.client
import json
import threading
import unittest
from unittest.mock import patch

from autoresearch import project_controller, project_workbench, saved_study_reference
from autoresearch.local_workbench import LocalWorkbench

ROUTE = '/api/local-workbench/saved-study-reference'


class _Manager:
    saved_study_reference = staticmethod(LocalWorkbench.saved_study_reference)

    def __init__(self):
        self.binding_calls = 0
        self.budget = {'local_tool_calls_used': 2, 'model_requests_used': 0}

    def binding(self):
        self.binding_calls += 1
        raise AssertionError('The fixed study view must not load any project')

    def describe(self):
        return {'active_project_id': None, 'projects': []}


class SavedStudyReferenceHTTPTests(unittest.TestCase):
    def start(self, **kwargs):
        server = project_workbench.create_project_server(port=0, **kwargs)
        thread = threading.Thread(target=lambda: server.serve_forever(poll_interval=.01), daemon=True)
        thread.start()
        self.addCleanup(thread.join, 2)
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        return server

    def request(self, server, path, method='GET', body=None, headers=None):
        con = http.client.HTTPConnection('127.0.0.1', server.server_port, timeout=5)
        try:
            con.request(method, path, body=body, headers=headers or {})
            reply = con.getresponse()
            return reply.status, json.loads(reply.read())
        finally:
            con.close()

    def test_controller_and_manager_getters_do_not_load_projects(self):
        value = {'status': 'completed', 'actual_spent': {'kernel_total': 1140},
                 'binding_only': True, 'current_project_budget_unchanged': True}
        with patch.object(saved_study_reference, 'read_saved_study_reference', return_value=value) as reader, \
             patch.object(project_controller, 'ResearchProject', side_effect=AssertionError('No project access')):
            first = project_controller.ProjectController.saved_study_reference()
            second = LocalWorkbench.saved_study_reference()
        self.assertEqual(reader.call_count, 2)
        self.assertEqual(first, {**value, 'scope': 'saved_external_reference_not_current_project_result'})
        self.assertEqual(second, first)
        self.assertNotIn('project_id', first)
        self.assertNotIn('project_budget', first)
        self.assertEqual(value['actual_spent'], {'kernel_total': 1140})

    def test_readonly_get_preserves_noncompleted_states_without_project_binding(self):
        manager = _Manager()
        server = self.start(local_workspace=manager)
        before = deepcopy(manager.budget)
        with patch.object(saved_study_reference, 'read_saved_study_reference') as reader:
            for status in ('completed', 'unknown', 'unavailable', 'failed', 'integrity_error'):
                value = {'status': status, 'study_id': 'fixed-id', 'may_execute': False}
                if status == 'completed':
                    value['actual_spent'] = {'kernel_total': 1140}
                reader.return_value = value
                response_status, response = self.request(server, ROUTE)
                self.assertEqual(response_status, 200)
                self.assertEqual(response, {**value, 'scope': 'saved_external_reference_not_current_project_result'})
                if status != 'completed':
                    self.assertNotIn('actual_spent', response)
            self.assertEqual(reader.call_count, 5)
        self.assertEqual(manager.binding_calls, 0)
        self.assertEqual(manager.budget, before)

    def test_bad_queries_nearby_paths_and_posts_do_not_call_reader_or_manager(self):
        manager = _Manager()
        server = self.start(local_workspace=manager)
        with patch.object(saved_study_reference, 'read_saved_study_reference') as reader:
            for suffix in ('?', '?root=/tmp', '?study_id=other', '?x=', '?x=1&x=2', '/other', '-other'):
                with self.subTest(suffix=suffix):
                    status, _ = self.request(server, ROUTE + suffix)
                    self.assertIn(status, (400, 404))
            status, _ = self.request(server, ROUTE, 'POST', b'{}', {'Content-Type': 'application/json'})
            self.assertEqual(status, 405)
            reader.assert_not_called()
        self.assertEqual(manager.binding_calls, 0)

    def test_enabled_actions_still_do_not_accept_post_on_this_route(self):
        manager = _Manager()
        server = self.start(local_workspace=manager, allow_local_actions=True)
        _, session = self.request(server, '/api/local-workbench')
        headers = {'Origin': f'http://127.0.0.1:{server.server_port}',
                   'X-AutoResearch-CSRF': session['csrf_token'], 'Content-Type': 'application/json'}
        with patch.object(saved_study_reference, 'read_saved_study_reference') as reader:
            status, _ = self.request(server, ROUTE, 'POST', b'{}', headers)
            self.assertEqual(status, 400)
            reader.assert_not_called()
        self.assertEqual(manager.binding_calls, 0)

    def test_unconfigured_workbench_does_not_call_reader_or_binding(self):
        with patch.object(project_workbench, '_binding', return_value=(None, None, None)):
            server = self.start()
        with patch.object(saved_study_reference, 'read_saved_study_reference') as reader, \
             patch.object(project_workbench.ProjectController, 'saved_study_reference') as getter:
            status, _ = self.request(server, ROUTE)
            self.assertEqual(status, 404)
            reader.assert_not_called()
            getter.assert_not_called()

    def test_concurrent_readonly_gets_make_no_project_or_action_calls(self):
        manager = _Manager()
        server = self.start(local_workspace=manager)
        before = deepcopy(manager.budget)
        value = {'status': 'unknown', 'study_id': 'fixed-id', 'may_execute': False}
        with patch.object(saved_study_reference, 'read_saved_study_reference', return_value=value) as reader:
            with ThreadPoolExecutor(max_workers=4) as pool:
                results = list(pool.map(lambda _: self.request(server, ROUTE), range(8)))
            self.assertEqual(reader.call_count, 8)
        self.assertTrue(all(status == 200 and body['status'] == 'unknown' for status, body in results))
        self.assertEqual(manager.binding_calls, 0)
        self.assertEqual(manager.budget, before)


if __name__ == '__main__':
    unittest.main()
