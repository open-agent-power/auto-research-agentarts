"""Compact, verified projections of captured fixed CPU source protocols.

Validation reads the original bounded source. It never executes a study, scores
labels, solves schedules or requires a completed action or exported report.
"""
import copy
from dataclasses import dataclass
import hashlib
import math
from pathlib import Path
import re

from . import retrieval_adapter, relevance_retrieval_adapter, scheduling_adapter
from . import source_evidence_adapter as source_reader
from .contracts import ResearchError, canonical, fingerprint, identifier

MAX_RESPONSE_BYTES = 128 * 1024
SPEC_FIELDS = ("schema_version", "dataset_label", "source_url", "attribution", "license_notes",
               "source_provenance", "files", "comparison", "limits")
PROJECTION_NOTICE = (
    "This protocol view omits original data, Base64, query ID arrays, complete jobs and missing-positive ID lists. "
    "Provenance and license statements are captured declarations; mechanical verification does not establish "
    "scientific validity, independent license approval or sealed evaluation."
)


@dataclass(frozen=True)
class _Descriptor:
    module: object
    evaluation_ref: str
    scheduling: bool = False


_DESCRIPTORS = (
    _Descriptor(retrieval_adapter, "citation-retrieval-fixed-pair-v1"),
    _Descriptor(relevance_retrieval_adapter, "relevance-retrieval-fixed-pair-v1"),
    _Descriptor(scheduling_adapter, "weighted-interval-fixed-pair-v1", True),
)


def _require(condition, code="EVIDENCE_CHANGED", message="Captured CPU protocol differs from its registered source."):
    if not condition:
        raise ResearchError(code, message)


def _digest(value):
    return type(value) is str and re.fullmatch(r"[a-f0-9]{64}", value) is not None


def _scalar_scope(scope):
    value = {}
    for key, item in scope.items():
        if item is None or type(item) in (str, int, bool):
            value[key] = item
        elif type(item) is float:
            _require(math.isfinite(item))
            value[key] = item
    return value


def _read_fixed_protocol(project, state):
    _require(type(state) is dict and type(state["registration"]) is dict)
    method_id = state["registration"].get("method_id")
    descriptor = next((item for item in _DESCRIPTORS if method_id == item.module.TOOL_ID), None)
    _require(descriptor is not None, "ARTIFACT_NOT_AVAILABLE", "This registered method has no fixed CPU protocol view.")
    module = descriptor.module
    identifier(state["id"], "project_id")
    identifier(state["run_id"], "run_id")
    _require(type(state["state_version"]) is int and state["state_version"] >= 0
             and all(_digest(state[key]) for key in ("snapshot_ref", "source_snapshot_sha256", "code_identity"))
             and _digest(state["registration"]["source_sha256"]))
    if "supported_methods" in state:
        _require(type(state["supported_methods"]) is list)
        supported = [item for item in state["supported_methods"]
                     if type(item) is dict and item.get("id") == method_id]
        _require(len(supported) == 1 and supported[0]["version"] == module.ADAPTER_VERSION
                 and canonical(supported[0]["scope"]) == canonical(state["source_scope"])
                 and ("evaluation_ref" not in supported[0] or supported[0]["evaluation_ref"] == descriptor.evaluation_ref))
    try:
        raw = source_reader._read_file(Path(project.root).absolute() / "source.json", module.LIMITS["packet_bytes"])
    except FileNotFoundError:
        raise ResearchError("ARTIFACT_NOT_FOUND", "The captured CPU source is unavailable.") from None
    except OSError:
        raise ResearchError("EVIDENCE_CHANGED", "The captured CPU source cannot be read safely.") from None
    file_sha = hashlib.sha256(raw).hexdigest()
    _require(file_sha == state["registration"]["source_sha256"])
    packet = module._parse(raw)
    checked = module._checked(packet)  # Exactly one validation; scheduling returns checked original jobs.
    spec = checked[0]
    _require(packet["snapshot_sha256"] == state["source_snapshot_sha256"]
             and canonical(packet["scope"]) == canonical(state["source_scope"]))
    if descriptor.scheduling:
        splits = {}
        for case in checked[1]["cases"]:
            counts = splits.setdefault(case["split"], {"cases": 0, "jobs": 0})
            counts["cases"] += 1
            counts["jobs"] += len(case["jobs"])
    else:
        splits = {split: {"queries": len(ids), "query_ids_sha256": fingerprint(ids)}
                  for split, ids in spec["query_splits"].items()}
    value = {
        "schema_version": "fixed-cpu-protocol-view-v1",
        "binding": {"project_id": state["id"], "run_id": state["run_id"], "snapshot_ref": state["snapshot_ref"],
                    "state_version": state["state_version"], "method_id": method_id,
                    "project_code_identity": state["code_identity"], "source_snapshot_sha256": packet["snapshot_sha256"],
                    "source_file_sha256": file_sha},
        "adapter_version": module.ADAPTER_VERSION,
        "evaluation_ref": descriptor.evaluation_ref,
        "source_spec_identity": {key: packet["spec_source"][key] for key in ("sha256", "bytes")},
        "declared_spec": {key: copy.deepcopy(spec[key]) for key in SPEC_FIELDS},
        "scalar_scope": _scalar_scope(packet["scope"]),
        "input_identities": {role: {key: asset[key] for key in ("sha256", "bytes")}
                             for role, asset in packet["assets"].items()},
        "splits": splits,
        "projection_notice": PROJECTION_NOTICE,
    }
    _require(len(canonical(value).encode("utf-8")) <= MAX_RESPONSE_BYTES,
             "READER_TOO_LARGE", "The captured protocol exceeds its compact response limit.")
    return value


def read_fixed_protocol(project, state):
    """Read one existing source and return a bounded display, with no project mutation."""
    try:
        return _read_fixed_protocol(project, state)
    except ResearchError:
        raise
    except (KeyError, TypeError, ValueError, AttributeError, IndexError, UnicodeError, OverflowError, RecursionError):
        raise ResearchError("EVIDENCE_CHANGED", "Captured CPU protocol is malformed or incomplete.") from None
