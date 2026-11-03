import ctypes
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from autoresearch import local_process
from autoresearch.contracts import ResearchError


class UnsupportedPlatformTests(unittest.TestCase):
    def test_import_is_portable_but_use_is_fail_closed(self):
        with patch.object(local_process.os, "name", "posix"):
            with self.assertRaises(ResearchError) as error: local_process.ManagedJob()
        self.assertEqual(error.exception.code, "UNSUPPORTED_PLATFORM")


@unittest.skipUnless(os.name == "nt", "actual Windows Job Object lifecycle")
class ManagedJobTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.environment = os.environ.copy()
        self.environment["PYTHONPATH"] = str(Path(__file__).resolve().parents[1] / "src")
        self.kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        self.kernel.OpenProcess.argtypes = [ctypes.c_uint32, ctypes.c_int, ctypes.c_uint32]
        self.kernel.OpenProcess.restype = ctypes.c_void_p
        self.kernel.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
        self.kernel.WaitForSingleObject.restype = ctypes.c_uint32
        self.kernel.CloseHandle.argtypes = [ctypes.c_void_p]
        self.kernel.CloseHandle.restype = ctypes.c_int

    def stop(self, process):
        if process.poll() is None: process.terminate()
        process.wait(timeout=5)

    def outside(self, code="import time;time.sleep(60)", *arguments):
        process = subprocess.Popen([sys.executable, "-B", "-c", code, *map(str, arguments)],
            env=self.environment, cwd=self.root, stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW, close_fds=True)
        self.addCleanup(self.stop, process)
        return process

    def wait_file(self, path):
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            if path.exists():
                try: return json.loads(path.read_text(encoding="utf-8"))
                except (ValueError, OSError): pass
            time.sleep(0.02)
        self.fail("owned disposable child did not produce its ready receipt")

    def owned_handle(self, pid):
        # Only PIDs just returned by this test's child or by its private job.
        handle = self.kernel.OpenProcess(0x00100000, False, pid)  # SYNCHRONIZE
        self.assertTrue(handle, "cannot open owned test child")
        self.addCleanup(self.kernel.CloseHandle, handle)
        return handle

    def spawn(self, job, code="import time;time.sleep(60)", *arguments):
        return job.spawn([sys.executable, "-B", "-c", code, *map(str, arguments)],
            env=self.environment, cwd=self.root, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def test_close_kills_owned_root_and_descendant_but_not_unrelated_child(self):
        unrelated = self.outside()
        marker = self.root / "descendant.json"
        code = "import subprocess,sys,json,time;from pathlib import Path;" \
               "child=subprocess.Popen([sys.executable,'-B','-c','import time;time.sleep(60)']);" \
               "Path(sys.argv[1]).write_text(json.dumps({'child':child.pid}),encoding='utf-8');time.sleep(60)"
        job = local_process.ManagedJob()
        self.addCleanup(job.close)
        root = self.spawn(job, code, marker)
        descendant = self.wait_file(marker)["child"]
        members = job.pids()
        # Windows venv launchers may introduce extra interpreter processes.
        self.assertTrue({root.pid, descendant} <= set(members))
        handles = [self.owned_handle(pid) for pid in members]
        self.assertTrue(job.contains(root.pid))
        self.assertFalse(job.contains(unrelated.pid))
        self.assertIsInstance(root, subprocess.Popen)
        job.close()
        self.assertIsNotNone(root.poll())
        for handle in handles: self.assertEqual(self.kernel.WaitForSingleObject(handle, 5000), 0)
        self.assertIsNone(unrelated.poll())
        self.assertEqual(job.pids(), [])
        job.close()
        with self.assertRaises(ResearchError) as error: self.spawn(job)
        self.assertEqual(error.exception.code, "LOCAL_PROCESS_CLOSED")

    def test_context_exception_cleans_and_job_handle_is_not_inheritable(self):
        self.kernel.GetHandleInformation.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint32)]
        self.kernel.GetHandleInformation.restype = ctypes.c_int
        with self.assertRaisesRegex(RuntimeError, "test exception"):
            with local_process.ManagedJob() as job:
                flags = ctypes.c_uint32()
                self.assertTrue(self.kernel.GetHandleInformation(job._handle, ctypes.byref(flags)))
                self.assertEqual(flags.value & 1, 0)
                process = self.spawn(job)
                raise RuntimeError("test exception")
        self.assertIsNotNone(process.poll())

    def test_assignment_failure_never_runs_child_and_terminates_owned_handle(self):
        marker = self.root / "must-not-run"
        job = local_process.ManagedJob()
        self.addCleanup(job.close)
        with patch.object(job._api, "assign", side_effect=ResearchError("LOCAL_PROCESS_FAILED", "test assignment failure")):
            with self.assertRaises(ResearchError):
                self.spawn(job, "from pathlib import Path;import sys;Path(sys.argv[1]).write_text('ran')", marker)
        self.assertFalse(marker.exists())
        self.assertEqual(len(job._children), 1)
        self.assertIsNotNone(job._children[0].poll())
        self.assertEqual(job.pids(), [])

    def test_child_cannot_execute_during_the_pre_assignment_window(self):
        marker = self.root / "execution-started.json"
        with local_process.ManagedJob() as job:
            assign = job._api.assign
            def delayed_assignment(handle, process):
                time.sleep(0.2)
                self.assertFalse(marker.exists(), "child ran before containment")
                assign(handle, process)
            with patch.object(job._api, "assign", side_effect=delayed_assignment):
                process = self.spawn(job, "from pathlib import Path;import sys,time;" \
                    "Path(sys.argv[1]).write_text('{}',encoding='utf-8');time.sleep(60)", marker)
            self.wait_file(marker)
            self.assertTrue(job.contains(process.pid))

    def test_resume_failure_closes_job_without_leaving_a_suspended_child(self):
        job = local_process.ManagedJob()
        self.addCleanup(job.close)
        with patch.object(job._api, "resume", side_effect=ResearchError("LOCAL_PROCESS_FAILED", "test resume failure")):
            with self.assertRaises(ResearchError): self.spawn(job)
        self.assertIsNotNone(job._children[0].poll())
        self.assertIsNone(job._handle)

    def test_abrupt_owner_exit_releases_kernel_job_and_kills_only_its_children(self):
        unrelated = self.outside()
        marker, release = self.root / "owner-ready.json", self.root / "owner-release"
        descendant_marker = self.root / "owner-descendant.json"
        child_code = "import subprocess,sys,json,time;from pathlib import Path;" \
                     "child=subprocess.Popen([sys.executable,'-B','-c','import time;time.sleep(60)']);" \
                     "Path(sys.argv[1]).write_text(json.dumps({'pid':child.pid}),encoding='utf-8');time.sleep(60)"
        code = "from autoresearch.local_process import ManagedJob;import subprocess,sys,json,time,os;from pathlib import Path;" \
               "job=ManagedJob();child=job.spawn([sys.executable,'-B','-c',sys.argv[4],sys.argv[3]]," \
               "env=os.environ.copy(),cwd=None,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL);" \
               "\nwhile not Path(sys.argv[3]).exists():time.sleep(.02)" \
               "\nPath(sys.argv[1]).write_text(json.dumps({'pid':child.pid,'members':job.pids()}),encoding='utf-8')" \
               "\nwhile not Path(sys.argv[2]).exists():time.sleep(.02)" \
               "\nos._exit(0)"
        owner = self.outside(code, marker, release, descendant_marker, child_code)
        receipt = self.wait_file(marker)
        descendant = self.wait_file(descendant_marker)["pid"]
        self.assertTrue({receipt["pid"], descendant} <= set(receipt["members"]))
        handles = [self.owned_handle(pid) for pid in receipt["members"]]
        release.write_text("exit", encoding="utf-8")
        self.assertEqual(owner.wait(timeout=5), 0)
        for handle in handles: self.assertEqual(self.kernel.WaitForSingleObject(handle, 5000), 0)
        self.assertIsNone(unrelated.poll())


if __name__ == "__main__": unittest.main()
