"""Windows lifetime containment for subprocesses created by this operator.

This is process cleanup, not a security sandbox. No existing process is adopted
or terminated by name. A child starts suspended, joins a private non-inheritable
kill-on-close job, and only then resumes. Assigned descendants die when the last
job handle closes, including when this Python owner exits unexpectedly.

Win32 declarations follow Microsoft Learn: jobapi2 CreateJobObjectW,
SetInformationJobObject, QueryInformationJobObject, AssignProcessToJobObject;
winnt JOBOBJECT_* / IO_COUNTERS; tlhelp32 THREADENTRY32 / Thread32First;
processthreadsapi OpenThread / GetProcessIdOfThread / ResumeThread.
https://learn.microsoft.com/en-us/windows/win32/procthread/job-objects
https://learn.microsoft.com/en-us/windows/win32/toolhelp/traversing-the-thread-list
"""
import ctypes
import os
import subprocess
import threading

from .contracts import ResearchError


class _WindowsAPI:
    def __init__(self):
        from ctypes import wintypes as w

        class BasicLimit(ctypes.Structure):
            _fields_ = [("PerProcessUserTimeLimit", ctypes.c_int64), ("PerJobUserTimeLimit", ctypes.c_int64),
                        ("LimitFlags", w.DWORD), ("MinimumWorkingSetSize", ctypes.c_size_t),
                        ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", w.DWORD),
                        ("Affinity", ctypes.c_size_t), ("PriorityClass", w.DWORD), ("SchedulingClass", w.DWORD)]

        class IOCounters(ctypes.Structure):
            _fields_ = [(name, ctypes.c_uint64) for name in ("ReadOperationCount", "WriteOperationCount",
                        "OtherOperationCount", "ReadTransferCount", "WriteTransferCount", "OtherTransferCount")]

        class ExtendedLimit(ctypes.Structure):
            _fields_ = [("BasicLimitInformation", BasicLimit), ("IoInfo", IOCounters),
                        ("ProcessMemoryLimit", ctypes.c_size_t), ("JobMemoryLimit", ctypes.c_size_t),
                        ("PeakProcessMemoryUsed", ctypes.c_size_t), ("PeakJobMemoryUsed", ctypes.c_size_t)]

        class ThreadEntry(ctypes.Structure):
            _fields_ = [("dwSize", w.DWORD), ("cntUsage", w.DWORD), ("th32ThreadID", w.DWORD),
                        ("th32OwnerProcessID", w.DWORD), ("tpBasePri", w.LONG),
                        ("tpDeltaPri", w.LONG), ("dwFlags", w.DWORD)]

        self.ExtendedLimit, self.ThreadEntry = ExtendedLimit, ThreadEntry
        self.kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        signatures = {
            "CreateJobObjectW": (w.HANDLE, [ctypes.c_void_p, w.LPCWSTR]),
            "SetInformationJobObject": (w.BOOL, [w.HANDLE, ctypes.c_int, ctypes.c_void_p, w.DWORD]),
            "QueryInformationJobObject": (w.BOOL, [w.HANDLE, ctypes.c_int, ctypes.c_void_p, w.DWORD, ctypes.POINTER(w.DWORD)]),
            "AssignProcessToJobObject": (w.BOOL, [w.HANDLE, w.HANDLE]),
            "SetHandleInformation": (w.BOOL, [w.HANDLE, w.DWORD, w.DWORD]),
            "CloseHandle": (w.BOOL, [w.HANDLE]),
            "CreateToolhelp32Snapshot": (w.HANDLE, [w.DWORD, w.DWORD]),
            "Thread32First": (w.BOOL, [w.HANDLE, ctypes.POINTER(ThreadEntry)]),
            "Thread32Next": (w.BOOL, [w.HANDLE, ctypes.POINTER(ThreadEntry)]),
            "OpenThread": (w.HANDLE, [w.DWORD, w.BOOL, w.DWORD]),
            "GetProcessIdOfThread": (w.DWORD, [w.HANDLE]),
            "ResumeThread": (w.DWORD, [w.HANDLE]),
        }
        for name, (result, arguments) in signatures.items():
            function = getattr(self.kernel, name)
            function.restype, function.argtypes = result, arguments

    @staticmethod
    def fail(operation):
        raise ResearchError("LOCAL_PROCESS_FAILED", operation + " failed (Win32 " + str(ctypes.get_last_error()) + ")")

    def create_job(self):
        handle = self.kernel.CreateJobObjectW(None, None)  # NULL attributes: non-inheritable, unnamed.
        if not handle: self.fail("CreateJobObjectW")
        try:
            if not self.kernel.SetHandleInformation(handle, 1, 0): self.fail("SetHandleInformation")
            limits = self.ExtendedLimit()
            limits.BasicLimitInformation.LimitFlags = 0x00002000  # KILL_ON_JOB_CLOSE; neither breakaway flag.
            if not self.kernel.SetInformationJobObject(handle, 9, ctypes.byref(limits), ctypes.sizeof(limits)):
                self.fail("SetInformationJobObject")
        except BaseException:
            self.kernel.CloseHandle(handle)
            raise
        return handle

    def assign(self, handle, process):
        if not self.kernel.AssignProcessToJobObject(handle, int(process._handle)):
            self.fail("AssignProcessToJobObject")

    def resume(self, process):
        # Popen closes CreateProcess's thread handle. Toolhelp is read-only; retain
        # only IDs belonging to this still-suspended, owned Popen, never names.
        snapshot = self.kernel.CreateToolhelp32Snapshot(0x00000004, 0)
        if snapshot == ctypes.c_void_p(-1).value: self.fail("CreateToolhelp32Snapshot")
        identifiers = []
        try:
            entry = self.ThreadEntry()
            entry.dwSize = ctypes.sizeof(entry)
            found = self.kernel.Thread32First(snapshot, ctypes.byref(entry))
            while found:
                if entry.th32OwnerProcessID == process.pid: identifiers.append(entry.th32ThreadID)
                entry.dwSize = ctypes.sizeof(entry)
                found = self.kernel.Thread32Next(snapshot, ctypes.byref(entry))
            if ctypes.get_last_error() != 18: self.fail("Thread32Next")  # ERROR_NO_MORE_FILES
        finally:
            self.kernel.CloseHandle(snapshot)
        if len(identifiers) != 1 or process.poll() is not None:
            raise ResearchError("LOCAL_PROCESS_FAILED", "owned suspended process must have exactly one initial thread")
        thread = self.kernel.OpenThread(0x0002 | 0x0800, False, identifiers[0])
        if not thread: self.fail("OpenThread")
        try:
            if self.kernel.GetProcessIdOfThread(thread) != process.pid: self.fail("GetProcessIdOfThread")
            if self.kernel.ResumeThread(thread) != 1:
                raise ResearchError("LOCAL_PROCESS_FAILED", "owned initial thread did not resume from its single suspension")
        finally:
            self.kernel.CloseHandle(thread)

    def pids(self, handle):
        # JOBOBJECT_BASIC_PROCESS_ID_LIST: two DWORDs then ULONG_PTR[].
        for count in (16, 64, 256, 1024, 4096):
            buffer = ctypes.create_string_buffer(8 + count * ctypes.sizeof(ctypes.c_size_t))
            ok = self.kernel.QueryInformationJobObject(handle, 3, buffer, ctypes.sizeof(buffer), None)
            assigned, returned = (ctypes.c_uint32 * 2).from_buffer(buffer)
            if ok and assigned == returned and returned <= count:
                return sorted((ctypes.c_size_t * returned).from_buffer(buffer, 8))
            if not ok and ctypes.get_last_error() not in (122, 234): self.fail("QueryInformationJobObject")
        raise ResearchError("LOCAL_PROCESS_FAILED", "owned job process list exceeds the bounded query size")


class ManagedJob:
    """Create and clean only owned Windows children; use with ``with`` or close().

    spawn returns a real Popen with the actual root PID. pids() is a momentary
    kernel job-membership snapshot, not a durable authorization or service lease.
    The operator supplies executable/arguments/environment; these are not model
    actions. No shell, global service, process-name kill, or filesystem cleanup.
    """
    def __init__(self):
        if os.name != "nt":
            raise ResearchError("UNSUPPORTED_PLATFORM", "owned local processes require Windows Job Objects")
        self._lock = threading.RLock()
        self._children = []
        self._api = _WindowsAPI()
        self._handle = self._api.create_job()

    def __enter__(self):
        with self._lock:
            if self._handle is None: raise ResearchError("LOCAL_PROCESS_CLOSED", "owned job is already closed")
        return self

    def __exit__(self, *_):
        self.close()

    def spawn(self, args, *, env=None, cwd=None, stdin=subprocess.DEVNULL, stdout=None, stderr=None):
        if not isinstance(args, (list, tuple)) or not args:
            raise ResearchError("INVALID_REQUEST", "owned process requires an executable argument list")
        with self._lock:
            if self._handle is None: raise ResearchError("LOCAL_PROCESS_CLOSED", "owned job is already closed")
            process = None
            try:
                process = subprocess.Popen(args, env=env, cwd=cwd, stdin=stdin,
                    stdout=stdout, stderr=stderr, shell=False, close_fds=True,
                    creationflags=0x00000004 | subprocess.CREATE_NO_WINDOW)  # CREATE_SUSPENDED
                self._children.append(process)
                self._api.assign(self._handle, process)
                self._api.resume(process)
                return process
            except BaseException:
                # Assignment may have failed: close the job AND terminate this
                # exact Popen handle, never seek a replacement PID by name.
                try:
                    if process is not None and process.poll() is None:
                        process.terminate()
                finally:
                    self.close()
                raise

    def pids(self):
        with self._lock:
            return [] if self._handle is None else self._api.pids(self._handle)

    def contains(self, pid):
        return type(pid) is int and pid in self.pids()

    def close(self):
        with self._lock:
            if self._handle is None: return
            handle = self._handle
            if not self._api.kernel.CloseHandle(handle): self._api.fail("CloseHandle(job)")
            self._handle = None
            # Kernel close kills descendants; wait only on our own Popen handles.
            for process in self._children:
                try: process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.terminate()
                    try: process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        raise ResearchError("LOCAL_PROCESS_CLEANUP_FAILED", "owned child did not exit after job close") from None

    def __del__(self):
        handle = getattr(self, "_handle", None)
        if handle:
            self._handle = None
            try: self._api.kernel.CloseHandle(handle)
            except Exception: pass
