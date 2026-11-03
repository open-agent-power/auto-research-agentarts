"""Read-only report capture of the original host-model journal and evidence."""
import base64
from contextlib import nullcontext
import copy
import hashlib
import json
import re

from . import host_selection_protocol as protocol, snapshot_viewer
from .contracts import ResearchError, canonical, fingerprint
from .host_model_selection import HostModelSelection
from .research_project import ResearchProject, safe_path

MAX_FILE_BYTES = 2 * 1024 * 1024
MAX_TOTAL_BYTES = 48 * 1024 * 1024  # Raw assets need another third for report Base64.
FILES = {"context.json": "host_model_context", "prompt.json": "host_model_prompt",
         "proposal.json": "host_model_proposal", "delegated.bin": "host_model_delegated_response",
         "transport/launch.json": "host_model_cli_launch", "transport/stdout.bin": "host_model_cli_stdout",
         "transport/stderr.bin": "host_model_cli_stderr", "transport/exit.json": "host_model_cli_exit"}


def _require(condition, message):
    if not condition:
        raise ResearchError("EVIDENCE_CHANGED", message)


def _read(path):
    try:
        return snapshot_viewer._read(safe_path(path), MAX_FILE_BYTES)
    except (OSError, ValueError) as error:
        raise ResearchError("EVIDENCE_CHANGED", "Host-model evidence is missing, changed or exceeds 2 MiB.") from error


def _json(raw, *, incomplete=False):
    try:
        return snapshot_viewer._json(raw)
    except (ValueError, UnicodeError, RecursionError) as error:
        if incomplete:
            return None
        raise ResearchError("EVIDENCE_CHANGED", "Host-model journal evidence is not complete strict JSON.") from error


def _verify(record, files):
    folder = record["directory"] + "/"
    partial = record["status"] in ("prepared", "sending", "unknown", "invalid", "failed")
    for name, key in (("context.json", "context"), ("prompt.json", "prompt"), ("proposal.json", "proposal")):
        raw = files.get(folder + name)
        if raw is not None and key in record:
            _require(raw == canonical(record[key]).encode("utf-8"), "Saved host context, prompt or proposal differs from its record.")
        if key in record and not partial:
            _require(raw is not None, "Completed host-model record lost its frozen context, prompt or proposal.")
    response = record.get("response_file")
    if response is not None:
        expected = folder + ("transport/stdout.bin" if record["provider"] == "claude_cli" else "delegated.bin")
        _require(response == expected, "Host response must name its original controlled evidence file.")
        raw = files.get(response)
        _require(raw is not None or partial, "Completed host-model response is missing.")
        if raw is not None:
            _require(hashlib.sha256(raw).hexdigest() == record["response_sha256"], "Original host-model response bytes changed.")
            if "arguments" in record:
                parsed = protocol.parse_host_response(raw, record["provider"])
                _require(all(record.get(key) == value for key, value in parsed.items()),
                         "Host-model parsed response or reported usage differs from its original bytes.")
            elif record["provider"] == "claude_cli" and any(record.get(key) is not None for key in
                    ("reported_cost_usd", "reported_usage", "reported_models")):
                metadata = protocol.parse_cli_usage(raw)
                _require(all(record.get(key) == value for key, value in metadata.items()),
                         "Failed or invalid CLI reported usage differs from its original envelope.")
    launch_raw, receipt_raw = files.get(folder + "transport/launch.json"), files.get(folder + "transport/exit.json")
    if launch_raw is not None:
        launch = _json(launch_raw, incomplete=partial)
        if launch is not None:
            prompt, argv = record["prompt"]["prompt"].encode("utf-8"), launch.get("argv")
            _require(type(argv) is list and len(argv) >= 2
                     and argv[0] == record["prepare_specification"]["executable"] and argv[-1] == record["prompt"]["system"]
                     and launch.get("stdin_sha256") == hashlib.sha256(prompt).hexdigest()
                     and launch.get("stdin_bytes") == len(prompt)
                     and launch.get("configured_max_budget_usd") == record.get("cli_budget_at_launch_usd"),
                     "Original CLI launch does not bind the frozen prompt, executable and budget.")
    if receipt_raw is not None:
        receipt = _json(receipt_raw, incomplete=partial)
        if receipt is not None:
            _require(type(receipt) is dict and receipt.get("status") in ("received", "failed", "unknown"),
                     "Original CLI receipt has an invalid outcome.")
            raw = files.get(folder + "transport/stdout.bin")
            _require(raw is not None or partial, "Original CLI stdout is missing.")
            if raw is not None:
                _require(receipt.get("stdout_file") == "stdout.bin" and receipt.get("stdout_bytes") == len(raw)
                         and receipt.get("stdout_sha256") == hashlib.sha256(raw).hexdigest(),
                         "Original CLI stdout differs from its saved receipt.")
            if "transport" in record:
                _require(receipt == record["transport"], "Original CLI receipt differs from its host-model record.")
    if "transport" in record and not partial:
        _require(launch_raw is not None and receipt_raw is not None, "Completed CLI record lost its launch or exit receipt.")


def _batch_originals(journal, project_id, files, roles, inventory):
    directory = safe_path(journal.directory / "batches")
    if not directory.exists():
        return []
    batches = []
    for path in sorted(directory.glob("batch-*.json")):
        if re.fullmatch(r"batch-[A-Za-z0-9_-]{1,60}\.json", path.name) is None:
            continue
        raw = _read(safe_path(path))
        batch = _json(raw)
        _require(type(batch) is dict and batch.get("schema_version") == "host-model-batch-v1"
                 and batch.get("project_id") == project_id
                 and path.name == "batch-" + str(batch.get("request_id")) + ".json"
                 and batch.get("record_status") in ("incomplete", "completed"),
                 "Saved model batch does not bind its original project and request.")
        name = "batches/" + path.name
        files[name], roles[name] = raw, "host_model_batch"
        inventory.append({"name": name, "exists": True})
        batches.append(batch)
    return batches


def _capture(workspace, *, include_assets):
    journal = HostModelSelection(workspace)
    lock = ResearchProject(journal.directory)._writer() if journal.directory.is_dir() else nullcontext()
    with lock:
        state_raw = _read(journal.state_file) if journal.state_file.exists() else None
        state = journal._load()
        status = journal.status()
        records, files, roles, inventory = list(state["requests"].values()), {}, {}, []
        if state_raw is not None:
            _require(_json(state_raw) == state, "Host journal changed while its snapshot was read.")
            files["state.json"], roles["state.json"] = state_raw, "host_model_journal"
        total = len(state_raw or b"")
        for request_id, record in state["requests"].items():
            folder = record["directory"]
            _require(record["request_id"] == request_id and re.fullmatch(r"requests/[0-9]{4}", folder) is not None,
                     "Host journal request does not name its original controlled directory.")
            for suffix, role in FILES.items():
                name = folder + "/" + suffix
                path = safe_path(journal.directory / name)
                inventory.append({"name": name, "exists": path.exists()})
                if path.exists():
                    raw = _read(path)
                    total += len(raw)
                    _require(total <= MAX_TOTAL_BYTES, "Host-model originals exceed the report capture size limit.")
                    files[name], roles[name] = raw, role
            _verify(record, files)
        batches = _batch_originals(journal, state["project_id"], files, roles, inventory)
        _require(sum(len(raw) for raw in files.values()) <= MAX_TOTAL_BYTES,
                 "Host-model originals and batch receipts exceed the report capture size limit.")
        _require((journal.state_file.exists() and _read(journal.state_file) == state_raw)
                 if state_raw is not None else not journal.state_file.exists(), "Host journal changed while capturing originals.")
        identities = [{"name": name, "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}
                      for name, raw in sorted(files.items())]
        snapshot = fingerprint({"schema_version": "host-model-report-snapshot-v1", "files": identities,
                                "expected_request_files": inventory})
        assets = [{**identity, "name": "host-model-evidence/" + identity["name"],
                   "role": roles[identity["name"]], "bytes_base64": base64.b64encode(files[identity["name"]]).decode("ascii")}
                  for identity in identities] if include_assets else []
        return {"snapshot_sha256": snapshot, "status": status, "records": copy.deepcopy(records), "assets": assets,
                **({"batches": batches} if batches else {})}


def capture_host_models(workspace) -> dict:
    """Freeze existing originals only; never launch, consume, restore or create a journal."""
    return _capture(workspace, include_assets=True)


def host_model_snapshot_sha256(workspace) -> str:
    """Read the same original identities without allocating their Base64 copies."""
    return _capture(workspace, include_assets=False)["snapshot_sha256"]


def host_model_report_current(workspace, manifest) -> bool:
    """Old distributed reports are current only when no external decisions are omitted."""
    try:
        captured = _capture(workspace, include_assets=False)
        if "host_model_snapshot_sha256" in manifest:
            return manifest["host_model_snapshot_sha256"] == captured["snapshot_sha256"]
        return not captured["records"] and not captured.get("batches") and captured["status"]["usage"]["unlinked_external_selection_count"] == 0
    except (ResearchError, OSError, ValueError, KeyError, TypeError):
        return False
