"""The installed module CLI uses only an existing, read-only manager."""
import hashlib
import http.client
import json
import os
from pathlib import Path
import re
import select
import signal
import sqlite3
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
MODULE = 'autoresearch.readonly_workbench'


class ReadOnlyWorkbenchCLITests(unittest.TestCase):
    def environment(self):
        return {**os.environ, 'PYTHONPATH': str(ROOT / 'src'), 'PYTHONDONTWRITEBYTECODE': '1'}

    def run_cli(self, *args, no_site=False):
        return subprocess.run([sys.executable, *(['-S'] if no_site else []), '-m', MODULE, *args],
                              env=self.environment(), capture_output=True, text=True, timeout=20)

    def test_help_and_rejected_options_do_not_import_dependencies(self):
        help_result = self.run_cli('--help', no_site=True)
        self.assertEqual(help_result.returncode, 0)
        self.assertIn('--root', help_result.stdout)
        self.assertIn('--port', help_result.stdout)
        for args in [('--root', 'unused', '--enable-local-actions'), ('--root', 'unused', '--claude-executable', 'x'),
                     ('--root', 'unused', '--ro'), ('--root', 'unused', '--port', '65536')]:
            result = self.run_cli(*args, no_site=True)
            self.assertEqual(result.returncode, 2)
            self.assertNotIn('ModuleNotFoundError', result.stderr)

    def test_missing_root_is_not_created(self):
        with tempfile.TemporaryDirectory() as temporary:
            missing = Path(temporary) / 'missing'
            result = self.run_cli('--root', str(missing), '--port', '0')
            self.assertEqual(result.returncode, 2)
            self.assertEqual(json.loads(result.stderr)['code'], 'WORKBENCH_NOT_FOUND')
            self.assertFalse(missing.exists())

    def test_loopback_service_uses_fixture_and_closes_on_interrupt(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / 'manager'
            root.mkdir()
            db = root / 'workbench.sqlite'
            with sqlite3.connect(db) as con:
                con.executescript('CREATE TABLE metadata(key TEXT PRIMARY KEY,value TEXT NOT NULL);'
                                  'CREATE TABLE projects(id TEXT PRIMARY KEY,goal TEXT NOT NULL,slot TEXT NOT NULL,report TEXT);'
                                  'CREATE TABLE requests(id TEXT PRIMARY KEY,digest TEXT NOT NULL,command TEXT NOT NULL,record TEXT NOT NULL);'
                                  "INSERT INTO metadata VALUES('schema_version','local-research-workbench-v1');")
            before = hashlib.sha256(db.read_bytes()).hexdigest()
            process = subprocess.Popen([sys.executable, '-m', MODULE, '--root', str(root), '--port', '0'],
                                       env=self.environment(), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            try:
                ready, _, _ = select.select([process.stdout], [], [], 20)
                self.assertTrue(ready, 'The loopback service did not start in time.')
                line = process.stdout.readline()
                match = re.fullmatch(r'Read-only workbench: http://127\.0\.0\.1:(\d+)/#/saved-study\n', line)
                self.assertIsNotNone(match, line)
                port = int(match.group(1))
                conn = http.client.HTTPConnection('127.0.0.1', port, timeout=5)
                try:
                    conn.request('GET', '/api/local-workbench/project-summary')
                    reply = conn.getresponse()
                    self.assertEqual((reply.status, json.loads(reply.read())['status']), (200, 'no_active'))
                    conn.request('POST', '/api/local-workbench/create', body='{}', headers={'Content-Type': 'application/json'})
                    reply = conn.getresponse()
                    self.assertEqual(reply.status, 405)
                    reply.read()
                finally:
                    conn.close()
                process.send_signal(signal.SIGINT)
                self.assertEqual(process.wait(timeout=10), 0)
                with self.assertRaises(OSError):
                    conn = http.client.HTTPConnection('127.0.0.1', port, timeout=2)
                    try:
                        conn.connect()
                    finally:
                        conn.close()
            finally:
                if process.poll() is None:
                    process.kill()
                    process.wait(timeout=10)
                process.stdout.close()
                process.stderr.close()
            self.assertEqual(hashlib.sha256(db.read_bytes()).hexdigest(), before)
            self.assertEqual({p.name for p in root.iterdir()}, {'workbench.sqlite'})


if __name__ == '__main__':
    unittest.main()
