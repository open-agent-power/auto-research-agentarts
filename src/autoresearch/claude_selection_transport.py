"""One explicit native Claude CLI process; raw evidence, no retry or fallback."""
from datetime import datetime, timezone
import hashlib
import math
from pathlib import Path
import os
import subprocess
import time

from .contracts import ResearchError, canonical
from .local_process import ManagedJob
from .research_project import safe_path


def run_claude_selection(*, executable, directory, system_prompt, prompt, max_budget_usd, timeout=180):
    if (type(system_prompt) is not str or type(prompt) is not str or not system_prompt.strip()
            or not prompt.strip() or "\0" in system_prompt or "\0" in prompt
            or type(max_budget_usd) not in (int, float) or not math.isfinite(max_budget_usd) or max_budget_usd <= 0
            or type(timeout) not in (int, float) or not math.isfinite(timeout) or not 0 < timeout <= 180):
        raise ResearchError("INVALID_REQUEST", "Use explicit prompts, a positive USD limit and a deadline of at most 180 seconds.")
    root = safe_path(Path(directory).absolute())
    if not root.is_dir():
        raise ResearchError("INVALID_REQUEST", "The host must first create a fresh transport evidence directory.")
    names = ("launch.json", "stdout.bin", "stderr.bin", "exit.json")
    if any(safe_path(root / name).exists() for name in names):
        raise ResearchError("EVIDENCE_EXISTS", "Transport evidence already exists; recover the original request without resending.")
    argv = [str(Path(executable).absolute()), "--print", "--safe-mode", "--tools", "", "--output-format", "json",
            "--no-session-persistence", "--effort", "low", "--max-turns", "1", "--max-budget-usd", str(max_budget_usd),
            "--system-prompt", system_prompt]
    incoming = prompt.encode("utf-8")
    launch = {"schema_version": "claude-selection-launch-v1", "argv": argv,
              "started_at_utc": datetime.now(timezone.utc).isoformat(), "cwd": str(root),
              "stdin_sha256": hashlib.sha256(incoming).hexdigest(), "stdin_bytes": len(incoming),
              "timeout_seconds": timeout, "configured_max_budget_usd": max_budget_usd,
              "tools_enabled": False, "custom_hooks_mcp_plugins_disabled": True, "automatic_retry": False}
    with (root / "launch.json").open("xb") as stream:
        stream.write(canonical(launch).encode("utf-8")); stream.flush(); os.fsync(stream.fileno())
    started = time.monotonic()
    status, process, failure_code = "unknown", None, None
    with (root / "stdout.bin").open("xb") as stdout, (root / "stderr.bin").open("xb") as stderr, \
            (root / "exit.json").open("xb") as receipt:
        try:
            with ManagedJob() as job:
                process = job.spawn(argv, cwd=str(root), stdin=subprocess.PIPE, stdout=stdout, stderr=stderr)
                process.communicate(input=incoming, timeout=timeout)
                status = "received" if process.returncode == 0 else "failed"
        except subprocess.TimeoutExpired:
            failure_code = "CLAUDE_TIMEOUT"
        except OSError:
            status = "failed" if process is None else "unknown"
            failure_code = "CLAUDE_LAUNCH_FAILED" if process is None else "CLAUDE_IO_UNKNOWN"
        except ResearchError as error:
            status, failure_code = "unknown", error.code
        for stream in (stdout, stderr):
            stream.flush(); os.fsync(stream.fileno())
        with (root / "stdout.bin").open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        result = {"status": status, "exit_code": process.returncode if process is not None else None,
                  "elapsed_seconds": time.monotonic() - started, "stdout_file": "stdout.bin", "stderr_file": "stderr.bin",
                  "stdout_sha256": digest, "stdout_bytes": (root / "stdout.bin").stat().st_size, "receipt_file": "exit.json"}
        detail = {"schema_version": "claude-selection-exit-v1", **result, "failure_code": failure_code,
                  "owned_process_stopped": process.poll() is not None if process is not None else None,
                  "provider_cost_usd": None, "automatic_retry": False, "automatic_fallback": False}
        receipt.write(canonical(detail).encode("utf-8")); receipt.flush(); os.fsync(receipt.fileno())
    return result
