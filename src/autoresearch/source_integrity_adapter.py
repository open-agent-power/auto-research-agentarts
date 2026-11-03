"""Bounded software file-I/O checks over captured source bytes, never executed code."""

import base64
import binascii
import builtins
import copy
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile

from . import source_evidence_adapter as reader
from .contracts import ResearchError, canonical, fingerprint


TOOL_ID = "software.source-integrity-check"
ADAPTER_VERSION = "1"
MAX_SOURCE_BYTES = 2 * 1024 * 1024
MAX_PACKET_BYTES = 3 * 1024 * 1024
STAT_FIELDS = ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns",
               "st_birthtime_ns", "st_mode", "st_nlink")
LIMITATIONS = [
    "Actual local software file I/O on task-owned copies, not a scientific endpoint or user-value evaluation.",
    "A deterministic read-boundary hook schedules the real append; OS metadata are not mocked.",
    "Traversal, SHA and task-binding cases are bounded probes, not a complete security audit or race proof.",
    "This run does not establish compatibility with other hosts, network filesystems, junctions or every link variant.",
]


def _require(condition, code, message):
    if not condition:
        raise ResearchError(code, message)


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _stats(info):
    return {field: getattr(info, field, None) for field in STAT_FIELDS}


def _platform():
    return {"os_name": os.name, "sys_platform": sys.platform, "python": sys.version}


def code_identity() -> str:
    return hashlib.sha256(Path(__file__).read_bytes() + reader.code_identity().encode("ascii")).hexdigest()


def _decode(payload):
    _require(type(payload) is dict and set(payload) == {
        "schema_version", "source", "scope", "captured_platform", "snapshot_sha256"}
        and payload["schema_version"] == "software-source-integrity-input-v1",
        "INVALID_SOURCE", "Exact software source packet is required.")
    _require(payload["snapshot_sha256"] == fingerprint(
        {key: value for key, value in payload.items() if key != "snapshot_sha256"}),
        "EVIDENCE_CHANGED", "Software source packet identity changed.")
    source = payload["source"]
    _require(type(source) is dict and set(source) == {
        "file_name", "sha256", "bytes", "bytes_base64", "media_type", "license_note", "content_trust"}
        and source["file_name"] == "source_evidence_adapter.py"
        and source["media_type"] == "text/x-python"
        and source["content_trust"] == "source_bytes_are_data_never_executed"
        and type(source["license_note"]) is str and 1 <= len(source["license_note"]) <= 2000
        and type(source["bytes"]) is int and 0 < source["bytes"] <= MAX_SOURCE_BYTES
        and type(source["bytes_base64"]) is str
        and len(source["bytes_base64"]) <= 4 * ((MAX_SOURCE_BYTES + 2) // 3),
        "INVALID_SOURCE", "Expected bounded captured source-adapter bytes and provenance.")
    try:
        raw = base64.b64decode(source["bytes_base64"], validate=True)
    except (ValueError, binascii.Error):
        raise ResearchError("INVALID_SOURCE", "Captured source base64 is invalid.") from None
    _require(len(raw) == source["bytes"] and _sha(raw) == source["sha256"],
             "EVIDENCE_CHANGED", "Captured original source bytes or SHA differ.")
    expected_scope = {"domain": "software", "contract": "file-capture-consistency-v1",
                      "source_sha256": source["sha256"], "sample_unit": "task-owned-file-copy"}
    _require(payload["scope"] == expected_scope
             and type(payload["captured_platform"]) is dict
             and set(payload["captured_platform"]) == {"os_name", "sys_platform", "python"}
             and all(type(value) is str and value for value in payload["captured_platform"].values()),
             "INVALID_SOURCE", "Explicit software capture-contract scope is required.")
    return raw


def capture_source(source_file) -> dict:
    """Capture the host-selected implementation as immutable data, without its host path."""
    try:
        path = Path(source_file).absolute()
        _require(path.name == "source_evidence_adapter.py", "UNSUPPORTED_SOURCE",
                 "This software check supports the selected source evidence adapter only.")
        raw = reader._read_file(path, MAX_SOURCE_BYTES)
        digest = _sha(raw)
        payload = {
            "schema_version": "software-source-integrity-input-v1",
            "source": {"file_name": path.name, "sha256": digest, "bytes": len(raw),
                       "bytes_base64": base64.b64encode(raw).decode("ascii"), "media_type": "text/x-python",
                       "license_note": "Local project source snapshot under workspace authorization; no external license or author claim inferred.",
                       "content_trust": "source_bytes_are_data_never_executed"},
            "scope": {"domain": "software", "contract": "file-capture-consistency-v1",
                      "source_sha256": digest, "sample_unit": "task-owned-file-copy"},
            "captured_platform": _platform(),
        }
        payload["snapshot_sha256"] = fingerprint(payload)
        return payload
    except ResearchError:
        raise
    except (OSError, TypeError, ValueError):
        raise ResearchError("INVALID_SOURCE", "Selected software source cannot be safely captured.") from None


def _object(pairs):
    result = {}
    for key, value in pairs:
        _require(key not in result, "INVALID_SOURCE", "Duplicate source packet JSON key.")
        result[key] = value
    return result


def _reject_constant(value):
    raise ResearchError("INVALID_SOURCE", "Nonfinite source packet constant: " + value)


def load_source(raw: bytes) -> dict:
    _require(type(raw) is bytes and 0 < len(raw) <= MAX_PACKET_BYTES,
             "INVALID_SOURCE", "Software source packet must be bounded nonempty JSON bytes.")
    try:
        payload = json.loads(raw, object_pairs_hook=_object, parse_constant=_reject_constant)
        _decode(payload)
        return payload
    except ResearchError:
        raise
    except (ValueError, TypeError, KeyError, OverflowError, RecursionError):
        raise ResearchError("INVALID_SOURCE", "Software source packet is malformed.") from None


def _bundle(root, original):
    (root / "sources").mkdir(parents=True)
    path = root / "sources" / "source_evidence_adapter.py"
    path.write_bytes(original)
    task = {"project_id": "software-source-integrity-probe", "based_on_action_id": "capture-contract-probe",
            "method_id": reader.TOOL_ID}
    manifest = {
        "schema_version": "project-evidence-bundle-v1", "task_ref": task,
        "contributor": {"role": "operator_assistant", "label": "Bounded software capture check"},
        "sources": [{"id": "code", "path": "sources/source_evidence_adapter.py", "sha256": _sha(original),
                     "url": "local-source:source_evidence_adapter.py?sha256=" + _sha(original),
                     "media_type": "text/plain", "license_note": "Task-owned copy of host-selected project source; data only."}],
        "selections": [{"id": "first-line", "source_id": "code", "locator": {"kind": "text_lines", "value": "1"},
                        "claim": "Read source bytes only; no scientific approval."}],
    }
    return path, task, manifest


def _save_manifest(root, manifest):
    (root / "manifest.json").write_text(canonical(manifest), encoding="utf-8")


def _rejected(callback, expected):
    try:
        callback()
    except ResearchError as error:
        return {"passed": error.code == expected, "expected_code": expected,
                "actual_code": error.code, "message": str(error)}
    return {"passed": False, "expected_code": expected, "actual_code": None,
            "message": "The controlled invalid input was accepted."}


class _AppendStream:
    def __init__(self, stream, path, evidence):
        self.stream, self.path, self.evidence = stream, path, evidence

    def __enter__(self):
        self.stream.__enter__()
        return self

    def __exit__(self, *args):
        return self.stream.__exit__(*args)

    def fileno(self):
        return self.stream.fileno()

    def read(self, *args):
        raw = self.stream.read(*args)
        self.evidence["fstat_before_append"] = _stats(os.fstat(self.fileno()))
        self.evidence["preappend_sha256"] = _sha(raw)
        with builtins.open(str(self.path), "ab") as stream:
            stream.write(b"\n# Controlled source-integrity probe append.\n")
            stream.flush()
            os.fsync(stream.fileno())
        self.evidence["fstat_after_append"] = _stats(os.fstat(self.fileno()))
        return raw


def _append_probe(path):
    evidence = {}

    class AppendAtRead(type(Path())):
        def open(self, *args, **kwargs):
            return _AppendStream(super().open(*args, **kwargs), path, evidence)

    result = _rejected(lambda: reader._read_file(AppendAtRead(path), MAX_SOURCE_BYTES), "EVIDENCE_CHANGED")
    return {**result, **evidence, "after_sha256": _sha(path.read_bytes()),
            "boundary": "real append after stream.read, before post-read fstat; no global patch or mocked metadata"}


def execute(payload, dimension=None) -> dict:
    _require(dimension is None, "INVALID_REQUEST", "Software integrity checks do not take a numerical grouping.")
    try:
        original = _decode(payload)
        checks = []
        prefix = "autoresearch-source-integrity-"
        parent = Path(tempfile.gettempdir()).resolve()
        with tempfile.TemporaryDirectory(prefix=prefix, dir=parent) as directory:
            root = Path(directory).resolve()
            _require(root.parent == parent and root.name.startswith(prefix), "UNSAFE_PATH", "Invalid owned probe directory.")
            try:
                normal_root = root / "normal"
                path, task, manifest = _bundle(normal_root, original)
                _save_manifest(normal_root, manifest)
                before = _stats(path.lstat())
                with path.open("rb") as stream:
                    opened = _stats(os.fstat(stream.fileno()))
                    directly_read = stream.read()
                    closed = _stats(os.fstat(stream.fileno()))
                after = _stats(path.lstat())
                captured = reader._read_file(path, MAX_SOURCE_BYTES)
                receipt, assets = reader.capture_bundle(normal_root, task)
                checks.append({"id": "normal_capture", "classification": "actual_normal_io",
                               "passed": captured == original == directly_read == assets["code"]
                               and before == after and opened == closed,
                               "source_sha256": _sha(original), "captured_sha256": _sha(captured),
                               "receipt_snapshot_sha256": receipt["snapshot_sha256"],
                               "lstat_before": before, "lstat_after": after,
                               "fstat_before": opened, "fstat_after": closed,
                               "same_api_lstat_stable": before == after, "same_api_fstat_stable": opened == closed,
                               "cross_api_different_fields": [field for field in STAT_FIELDS if before[field] != opened[field]]})

                changed_root = root / "changed"
                path, _, _ = _bundle(changed_root, original)
                checks.append({"id": "controlled_midread_append", "classification": "fault_injection", **_append_probe(path)})
                for case in ("sha_mismatch", "task_mismatch", "path_traversal"):
                    case_root = root / case
                    path, task, manifest = _bundle(case_root, original)
                    if case == "sha_mismatch":
                        manifest["sources"][0]["sha256"] = "0" * 64
                        expected = "EVIDENCE_CHANGED"
                    elif case == "task_mismatch":
                        manifest["task_ref"] = {**task, "based_on_action_id": "a-different-source-task"}
                        expected = "TASK_MISMATCH"
                    else:
                        (case_root / "outside.py").write_bytes(original)
                        manifest["sources"][0]["path"] = "sources/../outside.py"
                        expected = "UNSAFE_PATH"
                    _save_manifest(case_root, manifest)
                    checks.append({"id": case, "classification": "fault_injection",
                                   "original_sha256": _sha(original),
                                   **_rejected(lambda: reader.capture_bundle(case_root, task), expected)})
            finally:
                # TemporaryDirectory cleanup is restricted to the verified task-owned target.
                _require(root.resolve().parent == parent and root.name.startswith(prefix)
                         and not root.is_symlink() and not getattr(root, "is_junction", lambda: False)(),
                         "UNSAFE_PATH", "Owned probe directory redirected before cleanup.")
        passed = all(check["passed"] for check in checks)
        evidence = {"source_snapshot_sha256": payload["snapshot_sha256"],
                    "source_sha256": payload["source"]["sha256"], "source_name": payload["source"]["file_name"],
                    "scope": copy.deepcopy(payload["scope"])}
        result = {"schema_version": "software-source-integrity-result-v1", "checks": checks,
                  "all_checks_passed": passed, "captured_platform": payload["captured_platform"],
                  "execution_platform": _platform(), "source_sha256": _sha(original),
                  "reader_code_identity": reader.code_identity(),
                  "scope": copy.deepcopy(payload["scope"]), "limitations": LIMITATIONS,
                  "temporary_files": "task-owned copies removed after capture"}
        return {"tool_id": TOOL_ID, "adapter_version": ADAPTER_VERSION, "status": "completed",
                "observations": [{"producer": TOOL_ID, "kind": "software_file_io_check", "case_id": check["id"],
                                  "classification": check["classification"], "outcome": "pass" if check["passed"] else "fail",
                                  "values": copy.deepcopy(check), "evidence_refs": [copy.deepcopy(evidence)]}
                                 for check in checks],
                "metrics": [{"name": "checks_passed", "value": sum(check["passed"] for check in checks), "unit": "case"},
                            {"name": "checks_total", "value": len(checks), "unit": "case"}],
                "evidence_refs": [evidence], "result": result, "failure": None,
                "new_fits": 0, "scientific_validation": False}
    except ResearchError:
        raise
    except (OSError, ValueError, TypeError, KeyError, OverflowError, RecursionError):
        raise ResearchError("SOFTWARE_CHECK_FAILED", "Software capture probe could not complete; no success is inferred.") from None


def next_decision(result) -> dict:
    try:
        _require(result["tool_id"] == TOOL_ID and result["adapter_version"] == ADAPTER_VERSION
                 and result["status"] == "completed" and result["scientific_validation"] is False,
                 "INVALID_RESULT", "A completed software file-I/O result is required.")
        checks = result["result"]["checks"]
        _require(type(checks) is list and len(checks) == 5
                 and {item["id"] for item in checks} == {
                     "normal_capture", "controlled_midread_append", "sha_mismatch", "task_mismatch", "path_traversal"}
                 and all(type(item["passed"]) is bool for item in checks),
                 "INVALID_RESULT", "The five fixed software capture probes are required.")
        failed = [item["id"] for item in checks if not item["passed"]]
        _require(result["result"]["all_checks_passed"] is (not failed),
                 "INVALID_RESULT", "Software result summary differs from its actual checks.")
        return {"project_status": "waiting",
                "next_action": {"method_id": "research.source-selection", "kind": "investigate" if failed else "evidence_task",
                                "parameters": {"failed_checks": failed,
                                               "need": ("Inspect failed local checks and their raw metadata before any retry or compatibility claim."
                                                        if failed else "Acquire comparable evidence from another host/filesystem before extending the compatibility claim.")},
                                "execution_status": "not_executed"},
                "reason": ("At least one real capture-contract probe failed; investigate the recorded failure before retaining this behavior."
                           if failed else "All five bounded file-I/O checks matched expectations. Retain the ctime compatibility fix with exact SHA and same-API stability checks; broader filesystem compatibility remains untested."),
                "scientific_validation": False}
    except ResearchError:
        raise
    except (KeyError, TypeError, ValueError):
        raise ResearchError("INVALID_RESULT", "Malformed software capture result.") from None
