"""Mock processes only: native argv/raw bytes and a single bounded timeout."""
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from autoresearch import claude_selection_transport as transport
from autoresearch.contracts import ResearchError


class ClaudeSelectionTransportTests(unittest.TestCase):
    def test_exact_native_arguments_stdin_raw_bytes_and_known_exit(self):
        raw, errors = b'\xff{"result":"fixture"}\r\n', b'\x80fixture stderr\n'
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for code in (0, 7):
                output = root / str(code); output.mkdir()
                job, process = MagicMock(), MagicMock()
                job.__enter__.return_value = job
                job.spawn.return_value = process
                process.returncode = code; process.poll.return_value = code
                def complete(*, input, timeout):
                    self.assertEqual(input, "仅标准输入：真实问题".encode("utf-8"))
                    self.assertEqual(timeout, 180)
                    job.spawn.call_args.kwargs["stdout"].write(raw)
                    job.spawn.call_args.kwargs["stderr"].write(errors)
                process.communicate.side_effect = complete
                with patch.object(transport, "ManagedJob", return_value=job) as constructor:
                    result = transport.run_claude_selection(executable=root / "claude.exe", directory=output,
                        system_prompt="fixed system", prompt="仅标准输入：真实问题", max_budget_usd=0.1)
                    with self.assertRaisesRegex(ResearchError, "already exists"):
                        transport.run_claude_selection(executable=root / "claude.exe", directory=output,
                            system_prompt="fixed system", prompt="changed", max_budget_usd=0.1)
                constructor.assert_called_once(); job.spawn.assert_called_once(); process.communicate.assert_called_once()
                self.assertEqual(job.spawn.call_args.args[0], [str((root / "claude.exe").absolute()), "--print",
                    "--safe-mode", "--tools", "", "--output-format", "json", "--no-session-persistence", "--effort",
                    "low", "--max-turns", "1", "--max-budget-usd", "0.1", "--system-prompt", "fixed system"])
                self.assertEqual(job.spawn.call_args.kwargs["stdin"], subprocess.PIPE)
                self.assertEqual((output / result["stdout_file"]).read_bytes(), raw)
                self.assertEqual((output / result["stderr_file"]).read_bytes(), errors)
                self.assertEqual(result["stdout_sha256"], hashlib.sha256(raw).hexdigest())
                self.assertEqual((result["status"], result["exit_code"]), ("received" if code == 0 else "failed", code))
                receipt = json.loads((output / "exit.json").read_bytes())
                self.assertEqual(receipt["stdout_bytes"], len(raw)); self.assertIsNone(receipt["provider_cost_usd"])
                self.assertTrue(receipt["owned_process_stopped"])

    def test_timeout_closes_only_owned_job_without_a_second_dispatch(self):
        with tempfile.TemporaryDirectory() as directory:
            job, process = MagicMock(), MagicMock()
            job.__enter__.return_value = job; job.spawn.return_value = process
            process.returncode = None
            process.communicate.side_effect = subprocess.TimeoutExpired("fixture", 0.1)
            def stopped(*_):
                process.returncode = 137
                process.poll.return_value = 137
            job.__exit__.side_effect = stopped
            with patch.object(transport, "ManagedJob", return_value=job):
                result = transport.run_claude_selection(executable=Path(directory) / "claude.exe", directory=directory,
                    system_prompt="system", prompt="fixture", max_budget_usd=0.1, timeout=0.1)
            job.spawn.assert_called_once(); process.communicate.assert_called_once(); job.__exit__.assert_called_once()
            receipt = json.loads((Path(directory) / "exit.json").read_bytes())
            self.assertEqual(result["status"], "unknown")
            self.assertEqual(receipt["failure_code"], "CLAUDE_TIMEOUT")
            self.assertTrue(receipt["owned_process_stopped"])
            self.assertFalse(receipt["automatic_retry"]); self.assertFalse(receipt["automatic_fallback"])


if __name__ == "__main__":
    unittest.main()
