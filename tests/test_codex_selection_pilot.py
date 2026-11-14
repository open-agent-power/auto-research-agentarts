"""Synthetic pilot safety gates with a real fake-CLI subprocess; never invokes a model."""
import importlib.util
import json
import marshal
import os
from pathlib import Path
import py_compile
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from autoresearch.contracts import canonical
from autoresearch.host_model_selection import HostModelSelection
from autoresearch.research_project import ResearchProject


SCRIPT = Path(__file__).resolve().parents[1] / "scripts/probe_codex_selection.py"
spec = importlib.util.spec_from_file_location("s050_probe", SCRIPT)
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)

FAKE = '''#!/usr/bin/env python3
import json, pathlib, sys
args = sys.argv[1:]
assert "--disable" in args and args[args.index("--disable") + 1] == "shell_tool"
assert not list(pathlib.Path.cwd().iterdir())
sys.stdin.buffer.read()
output = json.dumps({"choice":{"kind":"wait"},"rationale":"Synthetic fixture selection.","evidence_citation_ids":[]},separators=(",",":"))
pathlib.Path(args[args.index("--output-last-message") + 1]).write_text(output)
events = [{"type":"thread.started"},{"type":"turn.started"},
          {"type":"item.completed","item":{"type":"agent_message","text":output}},
          {"type":"turn.completed"}]
for event in events: print(json.dumps(event), flush=True)
'''


class CodexPilotTests(unittest.TestCase):
    def setUp(self):
        self.tmp = self.enterContext(tempfile.TemporaryDirectory())
        self.root = Path(self.tmp)
        self.fake = self.root / "fake-cli"
        self.fake.write_text(FAKE)
        self.fake.chmod(0o755)
        self.workspace = self.root / "pilot"
        self.identity = {"commit": "a" * 40, "script_sha256": "synthetic", "project_code": {}, "controller_code": {}}
        self.cli = {"executable": str(self.fake), "sha256": probe.sha(self.fake.read_bytes()), "version": "fake only"}
        self.enterContext(patch.object(probe, "WORKSPACE", self.workspace))
        self.enterContext(patch.object(probe, "source_pin", return_value=(self.identity, {"remote_head": "f" * 40})))
        self.enterContext(patch.object(probe, "cli_identity", return_value=self.cli))
        self.prepared = probe.prepare("a" * 40)
        self.cwd = Path(probe.read_json(self.workspace / "prepare.json")["transport_cwd"])
        self.addCleanup(self.cwd.rmdir)

    def approval(self):
        path = self.root / "user-approval-fixture.json"
        path.write_bytes(canonical({"schema_version": "s050-user-approval-v1",
                                    "source_reference": "synthetic test only", "approved_decisions": 1,
                                    "prepare_sha256": self.prepared["prepare_sha256"],
                                    "user_message": "我批准该合成探测一次。"}).encode())
        return path

    def test_missing_approval_refuses_before_marker_grant_or_process(self):
        with self.assertRaisesRegex(RuntimeError, "approval"):
            probe.execute(None)
        self.assertFalse((self.workspace / "launch.json").exists())
        self.assertFalse((self.workspace / "project/host-model-selections/state.json").exists())
        self.assertFalse((self.workspace / "stdout.jsonl").exists())
        self.assertEqual(ResearchProject(self.workspace / "project").status()["actions"], [])

    def test_valid_fake_process_imports_without_dispatch_and_never_relaunches(self):
        result = probe.execute(self.approval())
        self.assertEqual(result["status"], "received_validated_not_applied")
        self.assertEqual(result["model_cost"], "unknown")
        self.assertTrue((self.workspace / "launch.json").is_file())
        project = ResearchProject(self.workspace / "project")
        self.assertEqual(project.status()["actions"], [])
        self.assertEqual(project.status()["budget"]["local_tool_calls_used"], 0)
        self.assertEqual(HostModelSelection(project.root).status(request_id=probe.REQUEST_ID)["status"], "received")
        with self.assertRaisesRegex(RuntimeError, "never resend"):
            probe.execute(self.approval())

    def test_tampered_input_rejected_before_grant(self):
        (self.workspace / "stdin.txt").write_bytes(b"tampered")
        with self.assertRaisesRegex(RuntimeError, "changed"):
            probe.execute(self.approval())
        self.assertFalse((self.workspace / "launch.json").exists())
        self.assertFalse((self.workspace / "project/host-model-selections/state.json").exists())

    def test_tool_or_missing_terminal_event_is_unknown(self):
        valid_final = b'{}'
        self.assertFalse(probe.terminal_events(b'{"type":"thread.started"}\n', valid_final))
        events = [{"type":"thread.started"},{"type":"turn.started"},
                  {"type":"item.completed","item":{"type":"command_execution"}},
                  {"type":"turn.completed"}]
        self.assertFalse(probe.terminal_events("\n".join(json.dumps(e) for e in events).encode(), valid_final))

    def test_reasoning_and_formatting_are_allowed_but_other_json_and_duplicate_terminal_are_not(self):
        message = '{"choice":{"kind":"wait"},"rationale":"fixture","evidence_citation_ids":[]}'
        events = [{"type":"thread.started"}, {"type":"turn.started"},
                  {"type":"item.completed", "item":{"type":"reasoning", "text":"considering"}},
                  {"type":"item.completed", "item":{"type":"agent_message", "text":message}},
                  {"type":"turn.completed"}]
        as_bytes = lambda value: "\n".join(json.dumps(e) for e in value).encode()
        self.assertTrue(probe.terminal_events(as_bytes(events), (message + "\n").encode()))
        self.assertFalse(probe.terminal_events(as_bytes(events), b'{"choice":{"kind":"execute"}}'))
        self.assertFalse(probe.terminal_events(as_bytes(events + [events[-1]]), message.encode()))
        self.assertFalse(probe.terminal_events(as_bytes(events[:-1] + [events[-2], events[-1]]), message.encode()))
        self.assertFalse(probe.terminal_events(as_bytes(events), b'{"choice":{},"choice":{}}'))

    def test_approval_bound_to_original_sha_and_one_decision(self):
        path = self.approval()
        data = json.loads(path.read_bytes())
        for key, value in (("prepare_sha256", "f" * 64), ("approved_decisions", 2), ("approved_decisions", True)):
            changed = {**data, key: value}
            path.write_bytes(canonical(changed).encode())
            with self.assertRaisesRegex(RuntimeError, "Approval"):
                probe.execute(path)
            self.assertFalse((self.workspace / "launch.json").exists())
            self.assertFalse((self.workspace / "project/host-model-selections/state.json").exists())

    def test_real_fake_process_tool_event_stays_unknown_and_cannot_retry(self):
        original = self.fake.read_text()
        self.fake.write_text(original.replace('"type":"agent_message"', '"type":"command_execution"'))
        result = probe.execute(self.approval())
        self.assertEqual(result["status"], "unknown")
        journal = HostModelSelection(self.workspace / "project")
        self.assertEqual(journal.status(request_id=probe.REQUEST_ID)["status"], "prepared")
        self.assertFalse((self.workspace / "validated-proposal.json").exists())
        self.assertIn(b"command_execution", (self.workspace / "stdout.jsonl").read_bytes())
        with self.assertRaisesRegex(RuntimeError, "never resend"):
            probe.execute(self.approval())

    def test_existing_launch_marker_stops_before_host_grant(self):
        (self.workspace / "launch.json").write_bytes(b"original interrupted marker")
        with self.assertRaisesRegex(RuntimeError, "never resend"):
            probe.execute(self.approval())
        self.assertFalse((self.workspace / "project/host-model-selections/state.json").exists())

    def test_launch_directory_fsync_failure_blocks_host_and_process(self):
        approval = self.approval()
        original_fsync = os.fsync
        def failing_directory_fsync(fd):
            if stat.S_ISDIR(os.fstat(fd).st_mode):
                raise OSError("synthetic directory fsync failure")
            return original_fsync(fd)
        with patch.object(probe.os, "fsync", side_effect=failing_directory_fsync):
            with self.assertRaisesRegex(OSError, "synthetic directory fsync"):
                probe.execute(approval)
        self.assertTrue((self.workspace / "launch.json").exists())
        self.assertFalse((self.workspace / "project/host-model-selections/state.json").exists())
        self.assertFalse((self.workspace / "stdout.jsonl").exists())
        with self.assertRaisesRegex(RuntimeError, "never resend"):
            probe.execute(approval)


class PublicationPinTests(unittest.TestCase):
    def setUp(self):
        self.commit = "a" * 40
        self.remote = "b" * 40
        self.untracked = b""
        self.calls = []
        self.enterContext(patch.object(probe.research_project, "code_identity", return_value={"project": "fixture"}))
        self.enterContext(patch.object(probe.project_controller, "code_identity", return_value={"controller": "fixture"}))
        self.enterContext(patch.object(probe.subprocess, "check_output", side_effect=self.output))
        self.run = self.enterContext(patch.object(probe.subprocess, "run"))

    def output(self, argv, **kwargs):
        args = argv[3:]
        self.calls.append(args)
        if args == ["rev-parse", "HEAD"]:
            return (self.commit + "\n").encode()
        if args == ["status", "--porcelain", "--untracked-files=no"]:
            return b""
        if args == ["ls-files", "--others", "--", "src"]:
            return self.untracked
        if args == ["ls-remote", "origin", "refs/heads/main"]:
            return (self.remote + "\trefs/heads/main\n").encode()
        if args[0] == "show":
            return (probe.REPO / args[1].split(":", 1)[1]).read_bytes()
        raise AssertionError(args)

    def test_remote_advances_without_changing_identity_and_ancestry_is_checked(self):
        identity, receipt = probe.source_pin(self.commit)
        self.assertEqual(receipt["observed_remote_head"], self.remote)
        self.assertIn(["ls-remote", "origin", "refs/heads/main"], self.calls)
        self.assertTrue(any("cat-file" in call.args[0] and self.remote + "^{commit}" in call.args[0]
                            for call in self.run.call_args_list))
        self.assertTrue(any("merge-base" in call.args[0] and self.commit in call.args[0] and self.remote in call.args[0]
                            for call in self.run.call_args_list))
        self.remote = "c" * 40
        later_identity, later_receipt = probe.source_pin(self.commit)
        self.assertEqual(later_identity, identity)
        self.assertNotEqual(later_receipt, receipt)

    def test_untracked_import_shadow_and_missing_remote_object_are_rejected(self):
        self.untracked = b"src/autoresearch/extra_shadow.py\n"
        with self.assertRaisesRegex(RuntimeError, "shadow"):
            probe.source_pin(self.commit)
        self.untracked = b""
        self.run.side_effect = subprocess.CalledProcessError(1, "git")
        with self.assertRaises(subprocess.CalledProcessError):
            probe.source_pin(self.commit)


class BytecodeIsolationTests(unittest.TestCase):
    def test_real_child_ignores_timestamp_and_size_valid_but_forged_project_pyc(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            package = root / "src/autoresearch"
            package.mkdir(parents=True)
            (package / "__init__.py").write_text("")
            loaded, forged = root / "source-loaded", root / "forged-loaded"
            source = package / "host_selection_protocol.py"
            source.write_text("from pathlib import Path\nPath(" + repr(str(loaded)) + ").write_text('source')\n")
            (package / "staged_relevance_adapter.py").write_text("")
            (package / "project_controller.py").write_text("class ProjectController: pass\n")
            (package / "research_project.py").write_text("class ResearchProject: pass\n")
            (package / "host_model_selection.py").write_text("class HostModelSelection: pass\n")
            (package / "contracts.py").write_text("def canonical(value): return str(value)\n")
            cache = package / "__pycache__" / ("host_selection_protocol." + sys.implementation.cache_tag + ".pyc")
            cache.parent.mkdir()
            py_compile.compile(str(source), cfile=str(cache), doraise=True,
                               invalidation_mode=py_compile.PycInvalidationMode.TIMESTAMP)
            original_header = cache.read_bytes()[:16]
            attack = compile("from pathlib import Path\nPath(" + repr(str(forged)) + ").write_text('forged')\n",
                             str(source), "exec")
            forged_raw = original_header + marshal.dumps(attack)
            cache.write_bytes(forged_raw)
            source_stat = source.stat()
            env = {**os.environ, "PYTHONPATH": str(root / "src")}
            result = subprocess.run([sys.executable, str(SCRIPT), "--help"], cwd=root, env=env,
                                    capture_output=True, timeout=30, check=False)
            self.assertEqual(result.returncode, 0, result.stderr.decode(errors="replace"))
            self.assertTrue(loaded.is_file())
            self.assertFalse(forged.exists())
            self.assertEqual(cache.read_bytes(), forged_raw)
            self.assertEqual((source.stat().st_mtime_ns, source.stat().st_size),
                             (source_stat.st_mtime_ns, source_stat.st_size))


if __name__ == "__main__":
    unittest.main()
