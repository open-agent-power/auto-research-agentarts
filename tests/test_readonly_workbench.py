import hashlib
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest

from autoresearch.contracts import ResearchError
from autoresearch.local_workbench import LocalWorkbench
from autoresearch.project_workbench import create_project_server


class ReadOnlyWorkbenchTests(unittest.TestCase):
    def test_open_preserves_manager_and_rejects_writes(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / 'manager'
            LocalWorkbench(root)
            def snapshot():
                return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
                        for p in root.rglob('*') if p.is_file()}
            before = snapshot()
            workbench = LocalWorkbench.open_readonly(root)
            self.assertTrue(workbench.read_only)
            self.assertEqual(workbench.describe()['projects'], [])
            for name in ('create', 'select', 'binding', 'import_project', 'bind_design', 'resume_experience'):
                with self.subTest(name=name), self.assertRaises(ResearchError) as error:
                    getattr(workbench, name)
                self.assertEqual(error.exception.code, 'READ_ONLY')
            with self.assertRaises(ResearchError):
                workbench._writer()
            with self.assertRaises(ResearchError):
                with workbench._connect():
                    pass
            with workbench._connect(readonly=True) as con:
                with self.assertRaises(sqlite3.OperationalError):
                    con.execute("INSERT INTO metadata VALUES ('forbidden', 'write')")
            sidecar = root / 'workbench.sqlite-journal'
            with self.assertRaises(ResearchError) as error:
                with workbench._connect(readonly=True) as con:
                    con.execute('SELECT * FROM metadata').fetchall()
                    sidecar.write_bytes(b'concurrent writer')
            self.assertEqual(error.exception.code, 'WORKBENCH_CHANGED')
            sidecar.unlink()
            with self.assertRaises(ResearchError):
                create_project_server(local_workspace=workbench, allow_local_actions=True, port=0)
            self.assertEqual(snapshot(), before)

    def test_missing_and_sidecars_fail_without_creating_anything(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / 'missing'
            with self.assertRaises(ResearchError):
                LocalWorkbench.open_readonly(root)
            self.assertFalse(root.exists())
            root.mkdir()
            with self.assertRaises(ResearchError):
                LocalWorkbench.open_readonly(root)
            self.assertEqual(list(root.iterdir()), [])
            LocalWorkbench(root)
            sidecar = root / 'workbench.sqlite-wal'
            sidecar.write_bytes(b'unresolved')
            with self.assertRaises(ResearchError):
                LocalWorkbench.open_readonly(root)
            self.assertEqual(sidecar.read_bytes(), b'unresolved')

    def test_cli_rejects_actions_before_opening(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / 'missing'
            script = Path(__file__).resolve().parents[1] / 'scripts/serve_local_workbench.py'
            result = subprocess.run([sys.executable, str(script), '--root', str(root), '--read-only', '--enable-local-actions'],
                                    capture_output=True, text=True, timeout=20)
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse(root.exists())


if __name__ == '__main__':
    unittest.main()
