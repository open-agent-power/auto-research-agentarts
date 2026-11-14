"""Explicit project snapshots of method cases, with local inclusion revisions."""

import copy
import hashlib
from pathlib import Path
import re

from .contracts import identifier


def _request(request_id, expected_state_version, reason):
    from .research_project import require
    identifier(request_id)
    require(type(expected_state_version) is int and expected_state_version >= 0,
            "INVALID_REQUEST", "Bind the saved project version before changing case inclusion.")
    require(type(reason) is str and bool(reason.strip()) and len(reason) <= 2000 and "\x00" not in reason,
            "INVALID_REQUEST", "Record why this historical method case is included or retired.")


def _fresh(project, con, state, request_id, expected_state_version):
    from .host_model_selection import HostModelSelection, PENDING
    from .research_project import require
    require(project._action(con, request_id) is None, "IDEMPOTENCY_CONFLICT", "ID belongs to an existing action.")
    project._require_unclaimed(state, request_id, except_collection="experience_revisions")
    project._require_fresh(state, project.status(), expected_state_version)
    require(not any(item["status"] in ("prepared", "running", "unknown")
                    for item in state.get("controller_requests", []))
            and not any(item["status"] == "reserved" for item in state.get("local_model_requests", [])),
            "PROJECT_BUSY", "Complete the accepted request before changing historical case inclusion.")
    require(not any(item["status"] in PENDING for item in HostModelSelection(project.root).status()["requests"]),
            "HOST_SELECTION_PENDING", "Reconcile the original Host request before changing its historical case context.")


def _latest(state):
    latest = {}
    for revision in state.get("experience_revisions", []):
        latest[revision["case_id"]] = revision
    return latest


def _load(root, revision):
    from .project_experience_dispatch import parse_bundle, MAX_BUNDLE_BYTES
    from .research_project import require, safe_path
    from .source_evidence_adapter import _read_file
    digest = revision["bundle_sha256"]
    require(type(digest) is str and re.fullmatch(r"[a-f0-9]{64}", digest) is not None
            and revision["bundle_ref"] == "experience/case-" + digest + ".json",
            "EVIDENCE_CHANGED", "Historical case reference changed.")
    raw = _read_file(safe_path(Path(root) / revision["bundle_ref"]), MAX_BUNDLE_BYTES)
    require(hashlib.sha256(raw).hexdigest() == digest, "EVIDENCE_CHANGED", "Historical case snapshot bytes changed.")
    bundle = parse_bundle(raw)
    require((bundle["id"], bundle["version"], bundle["record"]["id"])
            == (revision["case_id"], revision["case_version"], revision["entry_id"]),
            "EVIDENCE_CHANGED", "Historical case identity differs from its project binding.")
    return bundle, raw


def import_case(project, *, request_id, expected_state_version, bundle, reason, _validate_only=False):
    """Save one exact active-at-export case; import never restores an old binding."""
    from .project_experience_dispatch import parse_bundle
    from .research_project import require, safe_path, write_bytes_once
    _request(request_id, expected_state_version, reason)
    require(type(bundle) is bytes, "INVALID_REQUEST", "Provide original case bundle bytes.")
    value = parse_bundle(bundle)
    digest = hashlib.sha256(bundle).hexdigest()
    with project._writer(), project._connect(readonly=_validate_only) as con:
        state = project._project(con)
        previous = next((item for item in state.get("experience_revisions", []) if item["request_id"] == request_id), None)
        if previous is not None:
            require(previous["command"] == "import_experience"
                    and previous["based_on_state_version"] == expected_state_version
                    and previous["bundle_sha256"] == digest and previous["reason"] == reason,
                    "IDEMPOTENCY_CONFLICT", "Original case import is bound to different content.")
            _load(project.root, previous)
            return copy.deepcopy(previous)
        _fresh(project, con, state, request_id, expected_state_version)
        latest = _latest(state)
        old = latest.get(value["id"])
        require(not any(item["case_id"] == value["id"] and item["case_version"] == value["version"]
                        for item in state.get("experience_revisions", [])),
                "EXPERIENCE_ALREADY_IMPORTED", "This case version is already imported; restore its inclusion explicitly.")
        require(old is None or value["version"] > old["case_version"],
                "INVALID_EXPERIENCE_VERSION", "Import a newer case version; do not implicitly restore an older snapshot.")
        active = sum(item["inclusion_status"] == "active" for item in latest.values())
        require(old is not None and old["inclusion_status"] == "active" or active < 4,
                "EXPERIENCE_LIMIT", "A project can include at most four active historical method cases.")
        if old is not None:
            _load(project.root, old)
        if _validate_only:
            return None
        directory = safe_path(project.root / "experience")
        directory.mkdir(exist_ok=True)
        relative = "experience/case-" + digest + ".json"
        write_bytes_once(safe_path(project.root / relative), bundle)
        revisions = state.setdefault("experience_revisions", [])
        revision = {"revision": len(revisions) + 1, "request_id": request_id,
                    "based_on_state_version": expected_state_version, "command": "import_experience",
                    "case_id": value["id"], "case_version": value["version"], "entry_id": value["record"]["id"],
                    "inclusion_status": "active", "bundle_ref": relative, "bundle_sha256": digest, "reason": reason}
        revisions.append(revision)
        state["state_version"] += 1
        project._save(con, state)
        return copy.deepcopy(revision)


def set_status(project, *, request_id, expected_state_version, case_id, status, reason, _validate_only=False):
    """Explicitly retire or restore the latest local snapshot, never older versions."""
    from .research_project import require
    _request(request_id, expected_state_version, reason)
    require(type(case_id) is str and bool(case_id.strip()) and len(case_id) <= 160 and "\x00" not in case_id
            and type(status) is str and status in {"active", "retired"},
            "INVALID_REQUEST", "Select a known case and its local active or retired inclusion.")
    with project._writer(), project._connect(readonly=_validate_only) as con:
        state = project._project(con)
        previous = next((item for item in state.get("experience_revisions", []) if item["request_id"] == request_id), None)
        if previous is not None:
            require(previous["command"] == "set_experience_status"
                    and previous["based_on_state_version"] == expected_state_version
                    and previous["case_id"] == case_id and previous["inclusion_status"] == status and previous["reason"] == reason,
                    "IDEMPOTENCY_CONFLICT", "Original inclusion request is bound to different content.")
            _load(project.root, previous)
            return copy.deepcopy(previous)
        _fresh(project, con, state, request_id, expected_state_version)
        latest = _latest(state).get(case_id)
        require(latest is not None, "EXPERIENCE_NOT_FOUND", "No historical method case is bound under this ID.")
        _load(project.root, latest)
        require(latest["inclusion_status"] != status, "EXPERIENCE_STATUS_UNCHANGED", "This case already has the requested inclusion status.")
        require(status != "active" or latest["inclusion_status"] == "active"
                or sum(item["inclusion_status"] == "active" for item in _latest(state).values()) < 4,
                "EXPERIENCE_LIMIT", "Retire another case before restoring more than four active method cases.")
        if _validate_only:
            return None
        revisions = state["experience_revisions"]
        revision = {**copy.deepcopy(latest), "revision": len(revisions) + 1,
                    "request_id": request_id, "based_on_state_version": expected_state_version,
                    "command": "set_experience_status", "inclusion_status": status, "reason": reason}
        revisions.append(revision)
        state["state_version"] += 1
        project._save(con, state)
        return copy.deepcopy(revision)


def view_cases(root, project_state):
    """Read each latest local case including retired cases, without changing status."""
    from .project_experience_dispatch import summary
    cases = []
    for revision in _latest(project_state).values():
        bundle, _ = _load(root, revision)
        cases.append({**summary(bundle), "inclusion_status": revision["inclusion_status"],
                      "binding_revision": revision["revision"], "binding_request_id": revision["request_id"],
                      "reason": revision["reason"], "bundle_ref": revision["bundle_ref"],
                      "bundle_sha256": revision["bundle_sha256"]})
    return cases


def active_cases(root, project_state):
    return [case for case in view_cases(root, project_state) if case["inclusion_status"] == "active"]


def case_assets(root, project_state):
    """Read unique imported raw bundles for faithful report input capture."""
    assets, seen = [], set()
    for revision in project_state.get("experience_revisions", []):
        if revision["bundle_ref"] not in seen:
            _, raw = _load(root, revision)
            assets.append({"name": revision["bundle_ref"], "data": raw})
            seen.add(revision["bundle_ref"])
    return assets
