"""Fixed capsule API tests with synthetic bytes only."""
import hashlib
import http.client
import json
import os
from pathlib import Path
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from autoresearch import project_workbench, saved_study_capsule as capsule
from autoresearch.local_workbench import LocalWorkbench

META = '/api/local-workbench/study-capsule'
ZIP = META + '.zip'


class SavedStudyCapsuleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.path = self.root / 'capsule.zip'
        self.raw = b'fixture capsule bytes only'
        self.path.write_bytes(self.raw)
        self.patches = [patch.object(capsule, '_CAPSULE', self.path), patch.object(capsule, '_SIZE', len(self.raw)),
                        patch.object(capsule, '_SHA256', hashlib.sha256(self.raw).hexdigest())]
        for item in self.patches:
            item.start()
            self.addCleanup(item.stop)

    def server(self, readonly=True, *, enabled=False):
        root = self.root / ('manager-' + str(len(list(self.root.glob('manager-*')))))
        writable = LocalWorkbench(root)
        manager = LocalWorkbench.open_readonly(root) if readonly else writable
        server = project_workbench.create_project_server(local_workspace=manager, allow_local_actions=enabled, port=0)
        thread = threading.Thread(target=lambda: server.serve_forever(poll_interval=.01), daemon=True)
        thread.start()
        self.addCleanup(thread.join, 2)
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        return server

    def request(self, server, path, method='GET', headers=None):
        conn = http.client.HTTPConnection('127.0.0.1', server.server_port, timeout=5)
        try:
            conn.request(method, path, headers=headers or {})
            response = conn.getresponse()
            return response.status, dict(response.getheaders()), response.read()
        finally:
            conn.close()

    def test_descriptor_and_exact_download_in_readonly_and_normal_mode(self):
        for readonly in (True, False):
            server = self.server(readonly)
            status, headers, body = self.request(server, META)
            value = json.loads(body)
            self.assertEqual((status, value['status'], value['expected_bytes']), (200, 'available', len(self.raw)))
            self.assertEqual(value['expected_sha256'], hashlib.sha256(self.raw).hexdigest())
            self.assertFalse(value['may_execute'])
            self.assertNotIn(str(self.path), body.decode())
            status, headers, body = self.request(server, ZIP)
            self.assertEqual((status, body), (200, self.raw))
            self.assertEqual(headers['Content-Type'], 'application/zip')
            self.assertEqual(headers['Content-Disposition'], 'attachment; filename="study-review-capsule.zip"')
            self.assertEqual(headers['Cache-Control'], 'no-store')
            self.assertEqual(headers['Content-Length'], str(len(self.raw)))

    def test_changes_never_send_old_or_unverified_bytes(self):
        server = self.server()
        self.assertEqual(json.loads(self.request(server, META)[2])['status'], 'available')
        self.path.write_bytes(b'x' * len(self.raw))
        status, _, body = self.request(server, ZIP)
        self.assertEqual((status, json.loads(body)['status']), (409, 'integrity_error'))
        self.assertNotEqual(body, self.raw)
        self.path.unlink()
        self.assertEqual(json.loads(self.request(server, META)[2])['status'], 'unavailable')
        status, _, body = self.request(server, ZIP)
        self.assertEqual((status, json.loads(body)['status']), (404, 'unavailable'))
        self.assertFalse(self.path.exists())

    def test_bad_queries_near_paths_encoded_names_and_host_do_not_read_file(self):
        for readonly in (True, False):
            server = self.server(readonly)
            with patch.object(capsule, '_read_verified') as reader:
                for path in (META + '?', META + '?path=x', ZIP + '?', ZIP + '?sha=x', META + '/other',
                             META + '-other', '/api/local-workbench/%73tudy-capsule', META + '%2ezip'):
                    self.assertIn(self.request(server, path)[0], (400, 404), path)
                self.assertEqual(self.request(server, ZIP, 'POST')[0], 405)
                self.assertEqual(self.request(server, META, headers={'Host': 'example.com'})[0], 403)
                reader.assert_not_called()

    def test_links_hardlinks_wrong_size_and_change_are_rejected(self):
        self.path.unlink()
        target = self.root / 'target.zip'; target.write_bytes(self.raw)
        self.path.symlink_to(target)
        self.assertEqual(capsule.describe_capsule()['status'], 'integrity_error')
        self.path.unlink(); os.link(target, self.path)
        self.assertEqual(capsule.describe_capsule()['status'], 'integrity_error')
        self.path.unlink(); target.unlink(); self.path.write_bytes(b'wrong length')
        self.assertEqual(capsule.describe_capsule()['status'], 'integrity_error')
        self.path.write_bytes(self.raw)
        real_fstat = os.fstat
        count = 0
        def changed(fd):
            nonlocal count
            original = real_fstat(fd); count += 1
            if count == 1:
                return original
            return SimpleNamespace(st_dev=original.st_dev, st_ino=original.st_ino, st_size=original.st_size,
                                   st_mtime_ns=original.st_mtime_ns + 1, st_ctime_ns=original.st_ctime_ns)
        with patch.object(capsule.os, 'fstat', side_effect=changed):
            self.assertEqual(capsule.describe_capsule()['status'], 'unknown')

    def test_runtime_drift_denies_both_routes_before_read(self):
        marker = self.root / 'source.py'; marker.write_text('before')
        self.assertIn(Path(capsule.__file__).resolve(), project_workbench._runtime_sources())
        with patch.object(project_workbench, '_runtime_sources', return_value={marker: marker.read_bytes()}):
            server = self.server()
        marker.write_text('after')
        with patch.object(capsule, '_read_verified') as reader:
            for path in (META, ZIP):
                status, _, body = self.request(server, path)
                self.assertEqual((status, json.loads(body)['code']), (409, 'WORKBENCH_RESTART_REQUIRED'))
            reader.assert_not_called()


if __name__ == '__main__':
    unittest.main()
