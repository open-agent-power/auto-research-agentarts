"""Opt-in preregistration and read-only feedback for one tabular quality action.

This is not a dispatch policy, scientific approval, source/license verification,
model request, or an automatic plan revision. Registration is permitted only
before any primary quality action and records a future controller ID. That ID
is a reference, not a reservation: if claimed elsewhere feedback is unknown.
The reader validates the original source, historical plan, controller parent,
ordinary child, SQLite fingerprint and saved envelope; it never recovers or runs
an action. Old retrieval hypothesis registrations retain their own wire format.
"""
import copy
import hashlib
import json
from pathlib import Path
import re

from . import tabular_quality_adapter as tabular, tabular_quality_conditions as quality_conditions
from . import source_evidence_adapter as source_reader, contracts as contract_module
from .contracts import ResearchError, canonical, fingerprint, identifier
from .research_project import code_identity as project_code_identity, require, safe_path

SCHEMA = "tabular-quality-registration-v1"
FEEDBACK_SCHEMA = "tabular-quality-feedback-v1"
MAX_REGISTRATIONS = 16
_HASH = re.compile(r"[a-f0-9]{64}\Z")
_CLAIM_TABLE_SQL = ("CREATE TABLE quality_manager_claims (kind TEXT NOT NULL, request_id TEXT NOT NULL, "
                    "intent_sha256 TEXT NOT NULL, core_sha256 TEXT NOT NULL, PRIMARY KEY(kind, request_id))")
_FIELDS = {"schema_version", "request_id", "request_sha256", "request", "controller_request_id",
           "project_id", "run_id", "state_version_before", "candidate", "conditions", "numeric_columns",
           "source_sha256", "source_snapshot_sha256", "scope_sha256", "plan_sha256", "plan_version",
           "project_code_identity", "controller_code_identity", "selection_context_sha256",
           "reader_sha256", "conditions_sha256", "scientific_validation", "registration_sha256"}


def _reader_sha():
    return hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


def _conditions_sha():
    return hashlib.sha256(Path(quality_conditions.__file__).read_bytes()).hexdigest()


_BOOT_READER_SHA = _reader_sha()
_BOOT_CONDITIONS_SHA = _conditions_sha()
_BOOT_CONTRACTS_SHA = hashlib.sha256(Path(contract_module.__file__).read_bytes()).hexdigest()
_BOOT_SOURCE_SHA = source_reader.code_identity()
_BOOT_TABULAR_SHA = tabular.code_identity()


def _check_loaded_code():
    require(_reader_sha() == _BOOT_READER_SHA and _conditions_sha() == _BOOT_CONDITIONS_SHA
            and hashlib.sha256(Path(contract_module.__file__).read_bytes()).hexdigest() == _BOOT_CONTRACTS_SHA
            and source_reader.code_identity() == _BOOT_SOURCE_SHA and tabular.code_identity() == _BOOT_TABULAR_SHA,
            "CODE_CHANGED", "Restart with the original loaded reader and dependency code.")


def _checked_record(record):
    try:
        require(type(record) is dict and set(record) == _FIELDS and record["schema_version"] == SCHEMA
                and record["scientific_validation"] is False
                and record["registration_sha256"] == fingerprint({k: v for k, v in record.items() if k != "registration_sha256"})
                and record["request_sha256"] == fingerprint(record["request"]),
                "EVIDENCE_CHANGED", "The saved quality registration changed.")
        request = record["request"]
        require(type(request) is dict and set(request) == {"request_id", "expected_state_version", "controller_request_id",
                                                          "candidate_id", "conditions"}
                and record["request_id"] == request["request_id"]
                and record["controller_request_id"] == request["controller_request_id"]
                and type(record["state_version_before"]) is int and record["state_version_before"] >= 0
                and type(request["expected_state_version"]) is int
                and record["state_version_before"] == request["expected_state_version"]
                and type(record["plan_version"]) is int and record["plan_version"] >= 1,
                "EVIDENCE_CHANGED", "The saved registration request differs.")
        for name in ("request_id", "controller_request_id"):
            identifier(record[name], name)
        require(record["request_id"] != record["controller_request_id"], "EVIDENCE_CHANGED", "Registration IDs conflict.")
        candidate = record["candidate"]
        require(type(candidate) is dict and set(candidate) == {"id", "method_id", "parameters", "evaluation_ref"}
                and type(candidate["id"]) is str and candidate["id"] == request["candidate_id"]
                and candidate["method_id"] == tabular.TOOL_ID and candidate["parameters"] == {}
                and candidate["evaluation_ref"] == "tabular-quality-v1",
                "EVIDENCE_CHANGED", "The saved primary candidate changed.")
        for name in ("source_sha256", "source_snapshot_sha256", "scope_sha256", "plan_sha256",
                     "project_code_identity", "controller_code_identity", "selection_context_sha256",
                     "reader_sha256", "conditions_sha256"):
            require(type(record[name]) is str and _HASH.fullmatch(record[name]) is not None,
                    "EVIDENCE_CHANGED", "A saved registration identity is invalid.")
        for name in ("project_id", "run_id"):
            identifier(record[name], name)
        require(canonical(record["conditions"]) == canonical(request["conditions"])
                and quality_conditions.validate_conditions(record["conditions"], numeric_columns=record["numeric_columns"]) == record["conditions"],
                "EVIDENCE_CHANGED", "The saved quality conditions changed.")
    except ResearchError as exc:
        if exc.code == "EVIDENCE_CHANGED":
            raise
        raise ResearchError("EVIDENCE_CHANGED", "The saved quality registration is malformed.") from None
    except (KeyError, TypeError, ValueError, OverflowError, RecursionError):
        raise ResearchError("EVIDENCE_CHANGED", "The saved quality registration is malformed.") from None


def _checked_collection(records):
    require(type(records) is list and len(records) <= MAX_REGISTRATIONS,
            "EVIDENCE_CHANGED", "The saved quality registration collection is malformed.")
    requests, targets = set(), set()
    for record in records:
        _checked_record(record)
        require(record["request_id"] not in requests and record["controller_request_id"] not in targets,
                "EVIDENCE_CHANGED", "Duplicate quality registration or future controller ID.")
        requests.add(record["request_id"])
        targets.add(record["controller_request_id"])
    require(not requests.intersection(targets), "EVIDENCE_CHANGED", "A registration ID collides with a future controller ID.")


def _manager_claim(con, kind, request_id, intent_sha256, core_sha256, *, create=False):
    """Store/check cooperative ownership in the same transaction as core acceptance."""
    require(kind in ("registration", "policy", "plan", "hypothesis_registration", "staged_primary_parent", "staged_primary_child", "staged_feedback_parent", "staged_feedback_child", "staged_feedback_plan", "quality_primary_parent", "quality_primary_child") and type(intent_sha256) is str and _HASH.fullmatch(intent_sha256)
            and type(core_sha256) is str and _HASH.fullmatch(core_sha256),
            "EVIDENCE_CHANGED", "Invalid manager ownership identity.")
    identifier(request_id)
    schema = con.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='quality_manager_claims'").fetchone()
    if schema is None and create:
        con.execute(_CLAIM_TABLE_SQL)
        schema = con.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='quality_manager_claims'").fetchone()
    require(schema is not None and schema[0] == _CLAIM_TABLE_SQL,
            "OPERATION_INCOMPLETE", "The original manager ownership table is absent or changed; inspect without retrying.")
    if create:
        existing = con.execute("SELECT intent_sha256, core_sha256 FROM quality_manager_claims WHERE kind=? AND request_id=?",
                               (kind, request_id)).fetchone()
        require(existing is None, "IDEMPOTENCY_CONFLICT", "A manager ownership claim already exists.")
        con.execute("INSERT INTO quality_manager_claims VALUES(?,?,?,?)", (kind, request_id, intent_sha256, core_sha256))
    else:
        row = con.execute("SELECT intent_sha256, core_sha256 FROM quality_manager_claims WHERE kind=? AND request_id=?",
                          (kind, request_id)).fetchone()
        require(row is not None and row[0] == intent_sha256 and row[1] == core_sha256,
                "OPERATION_INCOMPLETE", "The original manager ownership claim is absent or changed; inspect without retrying.")


def register(project, *, request_id, expected_state_version, controller_request_id, candidate_id, conditions):
    """Persist one opt-in registration before any quality action, never dispatch."""
    result, _ = _register_with_created(project, request_id=request_id, expected_state_version=expected_state_version,
                                        controller_request_id=controller_request_id, candidate_id=candidate_id,
                                        conditions=conditions)
    return result


def _register_with_created(project, *, request_id, expected_state_version, controller_request_id, candidate_id, conditions,
                           _manager_intent_sha256=None):
    """Internal atomic creation signal for the local manager; public wire remains unchanged."""
    _check_loaded_code()
    identifier(request_id)
    identifier(controller_request_id, "controller_request_id")
    identifier(candidate_id, "candidate_id")
    require(request_id != controller_request_id and type(expected_state_version) is int and expected_state_version >= 0,
            "INVALID_REQUEST", "Use different request IDs and an exact state version.")
    request = {"request_id": request_id, "expected_state_version": expected_state_version,
               "controller_request_id": controller_request_id, "candidate_id": candidate_id,
               "conditions": copy.deepcopy(conditions)}
    with project._writer(), project._connect() as con:
        stored = project._project(con)
        records = stored.get("tabular_quality_registrations", [])
        _checked_collection(records)
        previous = next((item for item in records if item.get("request_id") == request_id), None)
        if previous is not None:
            require(previous.get("request_sha256") == fingerprint(request), "IDEMPOTENCY_CONFLICT", "Original registration body differs.")
            _checked_record(previous)
            from .project_controller import code_identity as controller_code_identity
            require(stored["code_identity"] == previous["project_code_identity"] == project_code_identity()
                    and controller_code_identity() == previous["controller_code_identity"],
                    "CODE_CHANGED", "Use the original project and controller code to read this registration.")
            project._source(stored)
            require(stored["registration"]["source_sha256"] == previous["source_sha256"]
                    and stored["source_snapshot_sha256"] == previous["source_snapshot_sha256"]
                    and fingerprint(stored["source_scope"]) == previous["scope_sha256"],
                    "EVIDENCE_CHANGED", "The registered source binding changed.")
            return copy.deepcopy(previous), False
        require(len(records) < MAX_REGISTRATIONS, "LIMIT_EXCEEDED", "At most sixteen quality registrations are allowed.")
        require(project._action(con, request_id) is None and project._action(con, controller_request_id) is None,
                "IDEMPOTENCY_CONFLICT", "A request ID already belongs to an action.")
        project._require_unclaimed(stored, request_id, except_collection="tabular_quality_registrations")
        project._require_unclaimed(stored, controller_request_id)
        for record in records:
            require(record["request_id"] != request_id and record["controller_request_id"] not in (request_id, controller_request_id),
                    "IDEMPOTENCY_CONFLICT", "A quality registration or future ID already exists.")
        for old in stored.get("hypothesis_registrations", []):
            require(type(old) is dict and type(old.get("controller_request_id")) is str,
                    "EVIDENCE_CHANGED", "The existing prediction collection is malformed.")
            require(old["controller_request_id"] not in (request_id, controller_request_id),
                    "IDEMPOTENCY_CONFLICT", "A request ID collides with an existing future prediction ID.")
        current = project.status()
        project._require_fresh(stored, current, expected_state_version)
        require(stored["registration"].get("method_id") == tabular.TOOL_ID,
                "CONDITION_NOT_SATISFIED", "The primary method must be tabular quality.")
        require(not any(item["command"] == tabular.TOOL_ID for item in current["actions"]),
                "CONDITION_NOT_SATISFIED", "The quality action has already been attempted.")
        require(not any(item["status"] in ("prepared", "running", "unknown") for item in stored.get("controller_requests", []))
                and not any(item["status"] == "reserved" for item in stored.get("local_model_requests", [])),
                "PROJECT_BUSY", "Reconcile the original pending request first.")
        from .host_model_selection import HostModelSelection, PENDING
        require(not any(item["status"] in PENDING for item in HostModelSelection(project.root).status()["requests"]),
                "HOST_SELECTION_PENDING", "Reconcile the original host request first.")
        project._source(stored)
        plans = stored.get("plan_revisions", [])
        require(bool(plans), "CONDITION_NOT_SATISFIED", "Save the original plan before registration.")
        numeric_columns = stored["source_scope"]["numeric_columns"]
        checked_conditions = quality_conditions.validate_conditions(conditions, numeric_columns=numeric_columns)
        from .project_controller import ProjectController
        context = ProjectController(project.root)._selection_context(current, "next_check")
        candidates = [c for c in context["candidates"] if c["id"] == candidate_id]
        require(not context["blockers"] and len(candidates) == 1 and candidates[0]["method_id"] == tabular.TOOL_ID
                and candidates[0]["parameters"] == {} and candidates[0]["evaluation_ref"] == "tabular-quality-v1",
                "CONDITION_NOT_SATISFIED", "Select the unique eligible quality candidate.")
        record = {"schema_version": SCHEMA, "request_id": request_id, "request_sha256": fingerprint(request),
                  "request": request, "controller_request_id": controller_request_id,
                  "project_id": stored["id"], "run_id": stored["run_id"],
                  "state_version_before": expected_state_version, "candidate": copy.deepcopy(candidates[0]),
                  "conditions": checked_conditions, "numeric_columns": copy.deepcopy(numeric_columns),
                  "source_sha256": stored["registration"]["source_sha256"],
                  "source_snapshot_sha256": stored["source_snapshot_sha256"],
                  "scope_sha256": fingerprint(stored["source_scope"]), "plan_sha256": fingerprint(plans[-1]),
                  "plan_version": plans[-1]["version"], "project_code_identity": stored["code_identity"],
                  "controller_code_identity": context["controller_code_identity"],
                  "selection_context_sha256": context["context_sha256"], "reader_sha256": _reader_sha(),
                  "conditions_sha256": _conditions_sha(), "scientific_validation": False}
        record["registration_sha256"] = fingerprint(record)
        _checked_record(record)
        stored.setdefault("tabular_quality_registrations", []).append(record)
        stored["state_version"] += 1
        project._save(con, stored)
        if _manager_intent_sha256 is not None:
            _manager_claim(con, "registration", request_id, _manager_intent_sha256, record["registration_sha256"], create=True)
        return copy.deepcopy(record), True


def _unknown(reason):
    return {"schema_version": FEEDBACK_SCHEMA, "outcome": "unknown", "unknown_reason": reason,
            "evaluation": None, "action_id": None, "result_sha256": None, "scientific_validation": False}


def _artifact(project, action):
    path = safe_path(project.root / "artifacts" / (action["id"] + ".json"))
    raw = source_reader._read_file(path, source_reader.MAX_SOURCE_BYTES)
    envelope = tabular._parse(raw)
    require(canonical(envelope).encode("utf-8") == raw and type(envelope) is dict and set(envelope) == {"action_id", "request_sha256", "code_identity",
            "source_snapshot_sha256", "tool_result", "sha256"}
            and envelope["sha256"] == action["result_sha256"]
            and envelope["sha256"] == fingerprint({k:v for k,v in envelope.items() if k != "sha256"})
            and envelope["action_id"] == action["id"] and envelope["request_sha256"] == action["request_sha256"]
            and envelope["code_identity"] == action["code_identity"]
            and envelope["source_snapshot_sha256"] == action["source_snapshot_sha256"],
            "EVIDENCE_CHANGED", "The original quality result envelope differs.")
    return envelope


def _strict_quality_claims(project, parent, action):
    """Reject a missing strict marker or claim; old unmarked records remain readable."""
    from .research_project import _quality_primary_parent_claim_sha, _quality_primary_child_claim_sha
    marker = parent.get("tabular_quality_primary")
    with project._connect(readonly=True) as con:
        table = con.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='quality_manager_claims'").fetchone()
        rows = [] if table is None else con.execute(
            "SELECT kind FROM quality_manager_claims WHERE (kind='quality_primary_parent' AND request_id=?) "
            "OR (kind='quality_primary_child' AND request_id=?)",
            (parent["request_id"], parent["child_request_id"])).fetchall()
        if marker is None:
            require(not rows, "EVIDENCE_CHANGED", "Original quality primary marker is missing.")
            return
        require(type(marker) is dict and action is not None, "OPERATION_INCOMPLETE", "Original strict quality action is unavailable.")
        _manager_claim(con, "registration", marker["registration_request_id"], marker["registration_intent_sha256"],
                       marker["registration_sha256"])
        _manager_claim(con, "quality_primary_parent", parent["request_id"], marker["manager_intent_sha256"],
                       _quality_primary_parent_claim_sha(parent))
        _manager_claim(con, "quality_primary_child", parent["child_request_id"], marker["manager_intent_sha256"],
                       _quality_primary_child_claim_sha(parent, action["request_sha256"]))


def _outcome(project, state, record):
    try:
        _check_loaded_code()
        from .project_controller import code_identity as controller_code_identity
        from .project_selection import validate_proposal
        project._source(state)
        if (state["id"] != record["project_id"] or state["run_id"] != record["run_id"]
                or state["registration"]["source_sha256"] != record["source_sha256"]
                or state["source_snapshot_sha256"] != record["source_snapshot_sha256"]
                or fingerprint(state["source_scope"]) != record["scope_sha256"]
                or state["source_scope"]["numeric_columns"] != record["numeric_columns"]):
            return _unknown("source_binding_changed")
        if (state["code_identity"] != record["project_code_identity"]
                or project_code_identity() != record["project_code_identity"]
                or controller_code_identity() != record["controller_code_identity"]
                or _reader_sha() != record["reader_sha256"] or _conditions_sha() != record["conditions_sha256"]):
            return _unknown("code_binding_changed")
        plans = state.get("plan_revisions", [])
        if not plans or plans[-1]["version"] != record["plan_version"] or fingerprint(plans[-1]) != record["plan_sha256"]:
            return _unknown("plan_binding_changed")
        parents = [p for p in state.get("controller_requests", []) if p["request_id"] == record["controller_request_id"]]
        if not parents:
            target = record["controller_request_id"]
            with project._connect(readonly=True) as con:
                claimed = project._action(con, target) is not None
            claimed = claimed or any(type(rows) is list and any(type(row) is dict and row.get("request_id") == target for row in rows)
                                     for key, rows in state.items() if key != "controller_requests")
            return _unknown("controller_id_claimed_by_other_command" if claimed else "controller_not_started")
        if len(parents) != 1:
            return _unknown("controller_binding_changed")
        parent = parents[0]
        if parent["status"] != "completed":
            return _unknown("controller_" + parent["status"])
        child_id = "controller-child-" + fingerprint({"project_id": state["id"], "request_id": parent["request_id"]})[:32]
        decision, context, request = parent["decision"], parent["selection_context"], parent["request"]
        selected = validate_proposal(context, request["proposal"])
        candidate, selection = record["candidate"], decision.get("selection_ref", {})
        if (parent["project_id"] != record["project_id"] or parent["state_version_before"] <= record["state_version_before"]
                or parent["code_identity"] != record["project_code_identity"]
                or parent["controller_code_identity"] != record["controller_code_identity"]
                or parent["source_snapshot_sha256"] != record["source_snapshot_sha256"]
                or set(request) != {"project_id", "command", "need", "expected_state_version", "proposal"}
                or request["project_id"] != record["project_id"] or request["command"] != "controller.advance_selection"
                or request["need"] != "next_check" or request["need"] != context.get("need")
                or type(request["expected_state_version"]) is not int
                or request["expected_state_version"] != context.get("state_version")
                or parent["request_sha256"] != fingerprint(request) or parent["decision_sha256"] != fingerprint(decision)
                or parent["dispatch_state_version"] != parent["state_version_before"] + 1
                or type(parent.get("state_version_after")) is not int
                or not parent["dispatch_state_version"] < parent["state_version_after"] <= state["state_version"]
                or parent["child_request_id"] != child_id
                or context.get("context_sha256") != fingerprint({k:v for k,v in context.items() if k != "context_sha256"})
                or context.get("project_id") != record["project_id"] or context.get("run_id") != record["run_id"]
                or context.get("source_snapshot_sha256") != record["source_snapshot_sha256"]
                or context.get("project_code_identity") != record["project_code_identity"]
                or context.get("controller_code_identity") != record["controller_code_identity"]
                or context.get("state_version") != parent["state_version_before"]
                or fingerprint(context.get("research_plan")) != record["plan_sha256"]
                or selection.get("context_sha256") != context["context_sha256"]
                or selection.get("candidate_id") != candidate["id"]
                or candidate not in context["candidates"] or selected.get("candidate") != candidate
                or decision["next_action"].get("method_id") != candidate["method_id"]
                or decision["next_action"].get("parameters", {}) != candidate["parameters"]):
            return _unknown("controller_binding_changed")
        actions = [a for a in state["actions"] if a["request_id"] == child_id]
        if len(actions) != 1:
            return _unknown("original_child_unavailable")
        action = actions[0]
        marker = parent.get("tabular_quality_primary")
        if marker is not None and (type(marker) is not dict or marker.get("registration_request_id") != record["request_id"]
                                   or marker.get("registration_sha256") != record["registration_sha256"]):
            return _unknown("quality_registration_binding_changed")
        _strict_quality_claims(project, parent, action)
        result = parent.get("result")
        parent_child = result.get("child") if type(result) is dict else None
        fields = ("id", "request_id", "command", "status", "artifact", "result_sha256", "failure")
        original_request = {"project_id": state["id"], "command": tabular.TOOL_ID, "dimension": None,
                            "source_snapshot_sha256": record["source_snapshot_sha256"]}
        with project._connect(readonly=True) as con:
            row = con.execute("SELECT fingerprint, record FROM actions WHERE request_id=?", (child_id,)).fetchone()
        if (action["status"] != "completed" or action["command"] != tabular.TOOL_ID
                or row is None or json.loads(row["record"]) != action or row["fingerprint"] != action["request_sha256"]
                or action["request_sha256"] != fingerprint(original_request)
                or action["code_identity"] != record["project_code_identity"]
                or action["source_snapshot_sha256"] != record["source_snapshot_sha256"]
                or action["method_instance"]["evaluation_ref"] != candidate["evaluation_ref"]
                or action["method_instance"]["parameters"] != candidate["parameters"]
                or any(key not in action for key in fields) or action["failure"] is not None
                or action["project_id"] != state["id"] or action["run_id"] != state["run_id"]
                or action["artifact"] != "artifacts/" + action["id"] + ".json"
                or type(result) is not dict or set(result) != {"child", "recovered", "reused"}
                or type(result["recovered"]) is not bool or result["reused"] is not False
                or parent_child != {key: action[key] for key in fields}):
            return _unknown("child_binding_changed")
        envelope = _artifact(project, action)
        tool = envelope["tool_result"]
        value = tool["result"]
        if (tool["schema_version"] != "tabular-quality-result-v1" or tool["tool_id"] != tabular.TOOL_ID
                or tool["adapter_version"] != tabular.ADAPTER_VERSION or tool["status"] != "completed"
                or tool["failure"] is not None or tool["new_fits"] != 0 or tool["model_calls"] != 0
                or tool["scientific_validation"] is not False or value["scope"] != state["source_scope"]
                or value["source_snapshot_sha256"] != record["source_snapshot_sha256"]):
            return _unknown("quality_result_binding_changed")
        observations = action["observations"]
        if (type(tool["observations"]) is not list or len(tool["observations"]) != 1
                or type(observations) is not list or len(observations) != 1
                or observations[0].get("id") != action["id"] + ":observation:0"
                or observations[0].get("action_id") != action["id"]
                or {k:v for k,v in observations[0].items() if k not in ("id", "action_id")} != tool["observations"][0]
                or tool["observations"][0].get("kind") != "tabular_quality_audit"
                or tool["observations"][0].get("profile") != value["profile"]):
            return _unknown("quality_observation_binding_changed")
        evaluation = quality_conditions.evaluate_conditions(record["conditions"], value["profile"], numeric_columns=record["numeric_columns"])
        # A status snapshot omits the SQLite fingerprint column, so compare the
        # exact original row again as well as source and artifact before return.
        project._source(state)
        _artifact(project, action)
        _strict_quality_claims(project, parent, action)
        with project._connect(readonly=True) as con:
            final_row = con.execute("SELECT fingerprint, record FROM actions WHERE request_id=?", (child_id,)).fetchone()
        if final_row is None or final_row["fingerprint"] != row["fingerprint"] or final_row["record"] != row["record"]:
            return _unknown("child_changed_during_read")
        if evaluation["outcome"] == "unknown":
            return {**_unknown("quality_values_unknown"), "evaluation": evaluation}
        return {"schema_version": FEEDBACK_SCHEMA, "outcome": evaluation["outcome"], "unknown_reason": None,
                "evaluation": evaluation, "action_id": action["id"], "result_sha256": action["result_sha256"],
                "scientific_validation": False}
    except ResearchError as exc:
        return _unknown("saved_evidence_" + exc.code.lower())
    except (KeyError, TypeError, ValueError, OSError, OverflowError, RecursionError):
        return _unknown("saved_evidence_unavailable_or_malformed")


def read_feedback(project, *, request_id):
    """Read one original saved registration and its result without dispatch or recovery."""
    identifier(request_id)
    before = project.status()
    records = before.get("tabular_quality_registrations", [])
    _checked_collection(records)
    matches = [record for record in records if record["request_id"] == request_id]
    require(len(matches) == 1, "INVALID_REQUEST", "Use one original quality registration ID.")
    record = matches[0]
    _checked_record(record)
    result = _outcome(project, before, record)
    after = project.status()
    if after["snapshot_ref"] != before["snapshot_ref"]:
        result = _unknown("project_changed_during_read")
    try:
        _check_loaded_code()
        if project_code_identity() != record["project_code_identity"]:
            result = _unknown("code_binding_changed")
    except (ResearchError, OSError, ValueError):
        result = _unknown("code_binding_changed")
    return {**result, "request_id": record["request_id"], "registration_sha256": record["registration_sha256"],
            "controller_request_id": record["controller_request_id"]}
