"""Fake stored records only; never execute a research project."""
import hashlib
import http.client
import json
from pathlib import Path
import sqlite3
import tempfile
import threading
import unittest
from unittest.mock import patch

from autoresearch.local_workbench import LocalWorkbench
from autoresearch.project_workbench import create_project_server
from autoresearch import project_workbench
from autoresearch import stored_project_summary as summary


class StoredProjectSummaryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'manager'
        LocalWorkbench(self.root)
        self.project_id, self.slot = 'project-fixture', 'a' * 64
        self.db = self.root / 'projects' / self.slot / 'project.sqlite'
        self.db.parent.mkdir(parents=True)
        self.project = {'schema_version': 'local-research-project-v3', 'id': self.project_id, 'run_id': 'run-fixture',
                        'state_version': 13, 'code_identity': 'original-native-source', 'runtime_dependencies': {},
                        'budget': {'local_tool_call_limit': 2, 'historical_spend_cny': None, 'cash_settlement': 'unknown',
                                   'model_requests_allowed': 0}}
        self.actions = [{'id': 'action-' + str(i), 'request_id': 'req-' + str(i), 'run_id': 'run-fixture', 'project_id': self.project_id,
                         'status': status, 'command': 'fixture.method', 'code_identity': 'original-action-source'}
                        for i, status in enumerate(('completed', 'unknown'))]
        with sqlite3.connect(self.db) as con:
            con.executescript('CREATE TABLE project(id INTEGER PRIMARY KEY, record TEXT NOT NULL);'
                              'CREATE TABLE actions(request_id TEXT PRIMARY KEY, fingerprint TEXT NOT NULL, record TEXT NOT NULL);')
            con.execute('INSERT INTO project VALUES(1,?)', (json.dumps(self.project),))
            for action in self.actions:
                con.execute('INSERT INTO actions VALUES(?,?,?)', (action['request_id'], 'unused', json.dumps(action)))
        with sqlite3.connect(self.root / 'workbench.sqlite') as con:
            con.execute("INSERT INTO metadata VALUES('active_project_id',?)", (self.project_id,))
            con.execute('INSERT INTO projects VALUES(?,?,?,?)', (self.project_id, 'fixture goal', self.slot, None))

    def files(self):
        return {str(p.relative_to(self.root)): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in self.root.rglob('*') if p.is_file()}

    def test_reads_only_stored_values_and_preserves_files(self):
        before = self.files()
        with patch('autoresearch.research_project.ResearchProject.__init__', side_effect=AssertionError('no runtime')):
            view = summary.read_stored_project_summary(self.root)
        self.assertEqual(view['status'], 'available')
        self.assertEqual(view['state_version'], 13)
        self.assertEqual(view['stored_budget'], self.project['budget'])
        self.assertNotIn('local_tool_calls_used', view['stored_budget'])
        self.assertEqual([a['status'] for a in view['stored_actions']], ['completed', 'unknown'])
        self.assertEqual(view['stored_actions'][0]['producer_code_identity'], 'original-action-source')
        self.assertEqual(self.files(), before)

    def test_no_active_missing_db_unsafe_slot_and_project_mismatch(self):
        manager_db = self.root / 'workbench.sqlite'
        with sqlite3.connect(manager_db) as con:
            con.execute("DELETE FROM metadata WHERE key='active_project_id'")
        self.assertEqual(summary.read_stored_project_summary(self.root)['status'], 'no_active')
        with sqlite3.connect(manager_db) as con:
            con.execute("INSERT INTO metadata VALUES('active_project_id',?)", (self.project_id,))
            con.execute('UPDATE projects SET slot=?', ('../unsafe',))
        self.assertEqual(summary.read_stored_project_summary(self.root)['status'], 'integrity_error')
        with sqlite3.connect(manager_db) as con:
            con.execute('UPDATE projects SET slot=?', (self.slot,))
        with sqlite3.connect(self.db) as con:
            changed = dict(self.project, id='project-other')
            con.execute('UPDATE project SET record=?', (json.dumps(changed),))
        self.assertEqual(summary.read_stored_project_summary(self.root)['status'], 'integrity_error')
        self.db.unlink()
        self.assertEqual(summary.read_stored_project_summary(self.root)['status'], 'unavailable')
        self.assertFalse(self.db.exists())

    def test_sidecars_invalid_json_partial_and_action_binding(self):
        sidecar = Path(str(self.db) + '-wal')
        sidecar.write_bytes(b'unresolved')
        self.assertEqual(summary.read_stored_project_summary(self.root)['status'], 'unknown')
        sidecar.unlink()
        with sqlite3.connect(self.db) as con:
            con.execute('UPDATE project SET record=?', ('{"schema_version":"x","schema_version":"y"}',))
        self.assertEqual(summary.read_stored_project_summary(self.root)['status'], 'integrity_error')
        with sqlite3.connect(self.db) as con:
            con.execute('UPDATE project SET record=?', ('{"value":1e999}',))
        self.assertEqual(summary.read_stored_project_summary(self.root)['status'], 'integrity_error')
        with sqlite3.connect(self.db) as con:
            partial = dict(self.project); partial.pop('budget')
            con.execute('UPDATE project SET record=?', (json.dumps(partial),))
        self.assertEqual(summary.read_stored_project_summary(self.root)['status'], 'partial')
        with sqlite3.connect(self.db) as con:
            con.execute('UPDATE project SET record=?', (json.dumps(self.project),))
            invalid = dict(self.actions[0], run_id='another-project')
            con.execute('UPDATE actions SET record=? WHERE request_id=?', (json.dumps(invalid), invalid['request_id']))
        self.assertEqual(summary.read_stored_project_summary(self.root)['status'], 'integrity_error')

    def test_read_detects_sidecar_appearing_during_project_read(self):
        original = summary._sidecars_clear
        count = 0
        def changed(path):
            nonlocal count
            count += 1
            if count == 3:
                Path(str(self.db) + '-journal').write_bytes(b'concurrent')
            return original(path)
        with patch.object(summary, '_sidecars_clear', side_effect=changed):
            self.assertEqual(summary.read_stored_project_summary(self.root)['status'], 'unknown')

    def test_http_exact_get_and_denied_methods(self):
        manager = LocalWorkbench.open_readonly(self.root)
        server = create_project_server(local_workspace=manager, port=0)
        thread = threading.Thread(target=lambda: server.serve_forever(poll_interval=.01), daemon=True)
        thread.start()
        self.addCleanup(thread.join, 2)
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        def request(path, method='GET'):
            conn = http.client.HTTPConnection('127.0.0.1', server.server_port, timeout=5)
            try:
                conn.request(method, path)
                response = conn.getresponse()
                return response.status, json.loads(response.read())
            finally:
                conn.close()
        path = '/api/local-workbench/project-summary'
        status, value = request(path)
        self.assertEqual((status, value['status'], value['project_id']), (200, 'available', self.project_id))
        for suffix in ('?', '?project_id=other', '/other', '-other'):
            self.assertIn(request(path + suffix)[0], (400, 404))
        self.assertEqual(request(path, 'POST')[0], 405)
        self.assertEqual(request('/api/project')[0], 404)

    def test_changed_reader_source_requires_service_restart(self):
        self.assertIn(Path(summary.__file__).resolve(), project_workbench._runtime_sources())
        source = Path(self.temp.name) / 'runtime-identity.py'
        source.write_text('before', encoding='utf-8')
        with patch.object(project_workbench, '_runtime_sources', return_value={source: source.read_bytes()}):
            server = create_project_server(local_workspace=LocalWorkbench.open_readonly(self.root), port=0)
        thread = threading.Thread(target=lambda: server.serve_forever(poll_interval=.01), daemon=True)
        thread.start()
        self.addCleanup(thread.join, 2)
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        source.write_text('after', encoding='utf-8')
        conn = http.client.HTTPConnection('127.0.0.1', server.server_port, timeout=5)
        try:
            conn.request('GET', '/api/local-workbench/project-summary')
            response = conn.getresponse()
            value = json.loads(response.read())
            self.assertEqual((response.status, value['code']), (409, 'WORKBENCH_RESTART_REQUIRED'))
        finally:
            conn.close()


if __name__ == '__main__':
    unittest.main()
