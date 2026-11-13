import contextlib
import io
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from autoresearch import runtime_cli


class RuntimeCommandTests(unittest.TestCase):
    def test_help_in_fresh_process_never_imports_runtime_or_sdk_or_starts_server(self):
        program = """
import importlib.abc
from pathlib import Path
import socket
import sys
from unittest.mock import patch
sys.path.insert(0, sys.argv[1])
class RejectRuntime(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == 'autoresearch.runtime' or fullname.split('.')[0] in {'agentarts', 'starlette'}:
            raise AssertionError('help attempted optional runtime import: ' + fullname)
sys.meta_path.insert(0, RejectRuntime())
from autoresearch.runtime_cli import main
sys.argv = ['autoresearch-runtime', '--help']
with patch.object(socket, 'socket', side_effect=AssertionError('help attempted socket creation')):
    try:
        main()
    except SystemExit as result:
        assert result.code == 0
    else:
        raise AssertionError('argparse help should terminate normally')
assert not Path(__import__('os').environ['AUTORESEARCH_WORKSPACE']).exists()
assert 'autoresearch.runtime' not in sys.modules
assert not any(name.split('.')[0] in {'agentarts', 'starlette'} for name in sys.modules)
"""
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory) / "must-not-create"
            environment = dict(os.environ, AUTORESEARCH_WORKSPACE=str(workspace), PYTHONDONTWRITEBYTECODE="1")
            result = subprocess.run(
                [sys.executable, "-I", "-B", "-c", program, str(Path(__file__).resolve().parents[1] / "src")],
                cwd=directory, env=environment, capture_output=True, text=True, timeout=15,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("usage: autoresearch-runtime", result.stdout)
            self.assertIn("AUTORESEARCH_WORKSPACE", result.stdout)
            self.assertIn("agentarts-autoresearch[runtime]", result.stdout)
            self.assertFalse(workspace.exists())

    def test_help_aliases_terminate_before_loading_the_optional_adapter(self):
        for option in ("-h", "--help"):
            with self.subTest(option=option), patch.object(runtime_cli, "import_module") as loader:
                with contextlib.redirect_stdout(io.StringIO()), self.assertRaises(SystemExit) as stopped:
                    runtime_cli.main([option])
                self.assertEqual(stopped.exception.code, 0)
                loader.assert_not_called()

    def test_unknown_runtime_option_fails_before_import(self):
        with patch.object(runtime_cli, "import_module") as loader:
            with contextlib.redirect_stderr(io.StringIO()) as output, self.assertRaises(SystemExit) as stopped:
                runtime_cli.main(["--port", "8081"])
            self.assertEqual(stopped.exception.code, 2)
            self.assertIn("unrecognized arguments", output.getvalue())
            loader.assert_not_called()

    def test_missing_optional_dependencies_return_actionable_error_without_storage_or_socket(self):
        for name in ("agentarts", "agentarts.sdk.runtime", "starlette", "starlette.responses"):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as directory:
                workspace = Path(directory) / "must-not-create"
                missing = ModuleNotFoundError("optional dependency missing", name=name)
                with patch.dict(os.environ, {"AUTORESEARCH_WORKSPACE": str(workspace)}), \
                        patch.object(runtime_cli, "import_module", side_effect=missing) as loader, \
                        patch("socket.socket") as socket, contextlib.redirect_stderr(io.StringIO()) as output:
                    self.assertEqual(runtime_cli.main([]), 2)
                loader.assert_called_once_with(".runtime", package="autoresearch")
                socket.assert_not_called()
                self.assertFalse(workspace.exists())
                self.assertIn("Missing optional runtime dependency: " + name, output.getvalue())
                self.assertIn("agentarts-autoresearch[runtime]", output.getvalue())
                self.assertNotIn("Traceback", output.getvalue())

    def test_available_adapter_main_is_delegated_once_without_cli_configuration_changes(self):
        run = Mock(return_value=7)
        with patch.object(runtime_cli, "import_module", return_value=SimpleNamespace(main=run)) as loader:
            self.assertEqual(runtime_cli.main([]), 7)
        loader.assert_called_once_with(".runtime", package="autoresearch")
        run.assert_called_once_with()

    def test_unrelated_missing_dependency_is_not_misdiagnosed_as_runtime_extra(self):
        missing = ModuleNotFoundError("unrelated package missing", name="numpy")
        with patch.object(runtime_cli, "import_module", side_effect=missing), contextlib.redirect_stderr(io.StringIO()) as output:
            with self.assertRaises(ModuleNotFoundError) as stopped:
                runtime_cli.main([])
        self.assertIs(stopped.exception, missing)
        self.assertEqual(output.getvalue(), "")

    def test_import_error_other_than_known_missing_optional_module_is_not_masked(self):
        failure = ImportError("adapter contract changed")
        with patch.object(runtime_cli, "import_module", side_effect=failure):
            with self.assertRaises(ImportError) as stopped:
                runtime_cli.main([])
        self.assertIs(stopped.exception, failure)

    def test_error_after_delegation_is_not_claimed_to_have_started_no_server(self):
        failure = ModuleNotFoundError("failure after adapter startup", name="agentarts")
        run = Mock(side_effect=failure)
        with patch.object(runtime_cli, "import_module", return_value=SimpleNamespace(main=run)), contextlib.redirect_stderr(io.StringIO()) as output:
            with self.assertRaises(ModuleNotFoundError) as stopped:
                runtime_cli.main([])
        self.assertIs(stopped.exception, failure)
        run.assert_called_once_with()
        self.assertEqual(output.getvalue(), "")


if __name__ == "__main__":
    unittest.main()
