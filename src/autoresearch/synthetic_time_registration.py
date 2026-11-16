"""Opt-in registration of the fixed artificial S134 clock; never dispatches.

This is a cooperative ownership and byte-consistency record, not a signature,
an authorization for a research action, or a gate on older direct APIs.
"""
import copy
import re

from .contracts import ResearchError, canonical, fingerprint, identifier
from . import tabular_quality_adapter as tabular
from .tabular_quality_feedback import _manager_claim

COMMAND = "register_synthetic_time_report"
FIELDS = ("request_id", "project_id", "expected_state_version", "registration_request_id", "registration_sha256", "report_dir")


def _require(ok, code, message):
    if not ok:
        raise ResearchError(code, message)


def _original_quality(manager, con, project, state, body):
    from .local_workbench import _body
    row = con.execute("SELECT command,digest,record FROM requests WHERE id=?", (body["registration_request_id"],)).fetchone()
    _require(row is not None and row["command"] == "register_tabular_quality_conditions",
             "OPERATION_INCOMPLETE", "Original quality manager registration is absent.")
    saved = tabular._parse(row["record"].encode("utf-8"))
    _require(type(saved) is dict and saved.get("status") == "completed" and type(saved.get("intent")) is dict
             and type(saved["intent"].get("body")) is dict and type(saved.get("result")) is dict,
             "OPERATION_INCOMPLETE", "Original quality registration is not complete.")
    original = saved["intent"]["body"]
    fields = ("request_id", "project_id", "expected_state_version", "controller_request_id", "candidate_id", "conditions")
    _require(_body(original, fields) == row["digest"] and original["request_id"] == body["registration_request_id"]
             and original["project_id"] == body["project_id"], "EVIDENCE_CHANGED", "Original quality body changed.")
    manager._check_quality_intent(saved["intent"], original, row["digest"], "register_tabular_quality_conditions", state)
    registration = manager._quality_registration(project, original, saved["intent"])
    response = manager._response("register_tabular_quality_conditions", original["request_id"], original["project_id"],
                                 status="completed", registration=registration)
    _require(registration["registration_sha256"] == body["registration_sha256"]
             and canonical({k:v for k,v in saved["result"].items() if k != "replayed"})
             == canonical({k:v for k,v in response.items() if k != "replayed"}),
             "EVIDENCE_CHANGED", "Original quality registration receipt changed.")
    return registration, saved["intent"]["intent_sha256"]


def _before_action(project, con, state, body, registration, manager_con):
    _require(state["state_version"] == body["expected_state_version"], "STALE_STATE", "Read the current project version.")
    stored = project._project(con)
    project._require_fresh(stored, state, body["expected_state_version"])
    _require(not state["actions"] and not state["evidence_actions"] and not stored.get("controller_requests"),
             "CONDITION_NOT_SATISFIED", "Time registration must precede all actions and controller requests.")
    _require(not any(item.get("status") in ("sending", "unknown") for item in stored.get("source_requests", []))
             and not any(item.get("status") == "reserved" for item in stored.get("local_model_requests", []))
             and not state["budget"].get("model_requests_reserved", 0), "PROJECT_BUSY", "Reconcile pending work first.")
    from .host_model_selection import HostModelSelection, PENDING
    _require(not any(r["status"] in PENDING for r in HostModelSelection(project.root).status()["requests"]),
             "HOST_SELECTION_PENDING", "Reconcile the original host request.")
    _require(stored.get("plan_revisions") and fingerprint(stored["plan_revisions"][-1]) == registration["plan_sha256"]
             and registration["state_version_before"] < state["state_version"], "EVIDENCE_CHANGED", "Original plan or registration order changed.")
    future = registration["controller_request_id"]
    child = "controller-child-" + fingerprint({"project_id":stored["id"], "request_id":future})[:32]
    _require(len({body["request_id"], registration["request_id"], future, child}) == 4,
             "IDEMPOTENCY_CONFLICT", "Use distinct original request IDs.")
    project._require_unclaimed(stored, body["request_id"])
    project._require_unclaimed(stored, future)
    project._require_unclaimed(stored, child)
    for request_id in (future, child):
        _require(manager_con.execute("SELECT 1 FROM requests WHERE id=?", (request_id,)).fetchone() is None,
                 "IDEMPOTENCY_CONFLICT", "A future request ID is already occupied in the manager.")
    for request_id in (body["request_id"], future, child):
        _require(con.execute("SELECT 1 FROM actions WHERE request_id=?", (request_id,)).fetchone() is None
                 and con.execute("SELECT 1 FROM replays WHERE request_id=? OR action_request_id=?", (request_id, request_id)).fetchone() is None,
                 "IDEMPOTENCY_CONFLICT", "An original ID or replay is already occupied.")
    _require(not stored.get("synthetic_time_registrations"), "IDEMPOTENCY_CONFLICT", "An artificial time registration already exists.")
    return stored, child


def _check_intent(manager, intent, body, digest, state):
    from .local_workbench import batch_code_identity, _EXPORT_BOOT_IDENTITY
    from .research_project import code_identity
    from .project_controller import code_identity as controller_identity
    fields = {"schema_version", "command", "body", "request_sha256", "project_id", "run_id", "manager_root", "nonce",
              "project_code_identity", "controller_code_identity", "manager_code_identity", "source_snapshot_sha256",
              "quality_intent_sha256", "report_identity_sha256", "snapshot_ref_before", "intent_sha256"}
    _require(type(intent) is dict and set(intent) == fields and intent["schema_version"] == "synthetic-time-manager-intent-v1"
             and intent["command"] == COMMAND and canonical(intent["body"]) == canonical(body)
             and intent["request_sha256"] == digest == fingerprint(body)
             and intent["intent_sha256"] == fingerprint({k:v for k,v in intent.items() if k != "intent_sha256"})
             and intent["project_id"] == body["project_id"] == state["id"] and intent["run_id"] == state["run_id"]
             and intent["manager_root"] == str(manager.root.resolve())
             and type(intent["nonce"]) is str and re.fullmatch(r"[a-f0-9]{64}", intent["nonce"])
             and intent["project_code_identity"] == state["code_identity"] == code_identity()
             and intent["controller_code_identity"] == controller_identity()
             and intent["manager_code_identity"] == batch_code_identity() == _EXPORT_BOOT_IDENTITY
             and intent["source_snapshot_sha256"] == state["source_snapshot_sha256"],
             "EVIDENCE_CHANGED", "The original synthetic time intent or producer changed.")


def _check_body(body):
    from .local_workbench import _body
    digest = _body(body, FIELDS)
    identifier(body["project_id"], "project_id"); identifier(body["registration_request_id"], "registration_request_id")
    _require(type(body["expected_state_version"]) is int and body["expected_state_version"] >= 0
             and type(body["registration_sha256"]) is str and re.fullmatch(r"[a-f0-9]{64}", body["registration_sha256"])
             and type(body["report_dir"]) is str and 0 < len(body["report_dir"]) <= 4096,
             "INVALID_REQUEST", "Use the original quality registration, version and synthetic report directory.")
    return digest


def _inspect(manager, con, project, body, digest, saved):
    from .local_workbench import _check_staged_runtime
    from .synthetic_time_binding import verify_original
    _check_staged_runtime()
    state = project.status(); intent = saved["intent"]
    _check_intent(manager, intent, body, digest, state)
    registration, quality_sha = _original_quality(manager, con, project, state, body)
    report = verify_original(project, state, body["report_dir"])
    records = state.get("synthetic_time_registrations", [])
    _require(type(records) is list and len(records) == 1 and type(records[0]) is dict,
             "OPERATION_INCOMPLETE", "Original synthetic time registration is absent.")
    record = records[0]
    fields = {"schema_version", "request_id", "request_sha256", "project_id", "run_id", "state_version_before",
              "snapshot_ref_before", "registration_request_id", "registration_sha256", "quality_intent_sha256",
              "controller_request_id", "child_request_id", "plan_sha256", "report", "manager_intent_sha256", "record_sha256"}
    _require(set(record) == fields and record["schema_version"] == "synthetic-time-registration-v1"
             and record["record_sha256"] == fingerprint({k:v for k,v in record.items() if k != "record_sha256"})
             and record["request_id"] == body["request_id"] and record["request_sha256"] == digest
             and record["project_id"] == state["id"] and record["run_id"] == state["run_id"]
             and registration["state_version_before"] < record["state_version_before"] == body["expected_state_version"] < state["state_version"]
             and record["snapshot_ref_before"] == intent["snapshot_ref_before"]
             and record["registration_request_id"] == registration["request_id"]
             and record["registration_sha256"] == registration["registration_sha256"]
             and record["quality_intent_sha256"] == quality_sha == intent["quality_intent_sha256"]
             and record["controller_request_id"] == registration["controller_request_id"]
             and record["child_request_id"] == "controller-child-" + fingerprint({"project_id":state["id"], "request_id":registration["controller_request_id"]})[:32]
             and record["plan_sha256"] == registration["plan_sha256"] and record["report"] == report
             and fingerprint(report) == intent["report_identity_sha256"] and record["manager_intent_sha256"] == intent["intent_sha256"],
             "EVIDENCE_CHANGED", "Original synthetic time registration changed.")
    with project._connect(readonly=True) as core:
        _manager_claim(core, "synthetic_time_registration", body["request_id"], intent["intent_sha256"], record["record_sha256"])
    _require(project.status()["snapshot_ref"] == state["snapshot_ref"] and verify_original(project, state, body["report_dir"]) == report,
             "EVIDENCE_CHANGED", "Original synthetic time evidence changed during inspection.")
    _require(_original_quality(manager, con, project, state, body)[1] == quality_sha,
             "EVIDENCE_CHANGED", "Original quality registration changed during inspection.")
    with project._connect(readonly=True) as core:
        _manager_claim(core, "synthetic_time_registration", body["request_id"], intent["intent_sha256"], record["record_sha256"])
    _check_staged_runtime()
    return copy.deepcopy(record)


def _finish(manager, con, project, body, digest, saved):
    # Keep the manager -> Project writer lock order through receipt commit.
    # External processes that ignore these locks can still modify files.
    with project._writer():
        record = _inspect(manager, con, project, body, digest, saved)
        response = manager._response(COMMAND, body["request_id"], body["project_id"], status="completed", registration=record)
        if saved["status"] == "completed":
            _require(type(saved.get("result")) is dict and canonical({k:v for k,v in saved["result"].items() if k != "replayed"})
                     == canonical({k:v for k,v in response.items() if k != "replayed"}), "EVIDENCE_CHANGED", "Original receipt changed.")
        else:
            _require(saved["status"] == "preparing" and saved.get("result") is None, "OPERATION_INCOMPLETE", "Original manager intent is incomplete.")
            manager._save(con, body["request_id"], {"status":"completed", "intent":saved["intent"], "result":response})
            _require(_inspect(manager, con, project, body, digest, saved) == record,
                     "EVIDENCE_CHANGED", "Original evidence changed before receipt commit.")
            con.commit()
        return response


def _create_project_record(manager, con, project, body, digest, intent):
    from .local_workbench import _check_staged_runtime
    from .synthetic_time_binding import verify_original
    with project._writer(), project._connect() as core:
        state = project.status()
        _check_intent(manager, intent, body, digest, state)
        registration, quality_sha = _original_quality(manager, con, project, state, body)
        stored, child = _before_action(project, core, state, body, registration, con)
        report = verify_original(project, state, body["report_dir"])
        _require(quality_sha == intent["quality_intent_sha256"] and fingerprint(report) == intent["report_identity_sha256"]
                 and state["snapshot_ref"] == intent["snapshot_ref_before"], "EVIDENCE_CHANGED", "Original preflight changed.")
        record = {"schema_version":"synthetic-time-registration-v1", "request_id":body["request_id"], "request_sha256":digest,
                  "project_id":state["id"], "run_id":state["run_id"], "state_version_before":state["state_version"],
                  "snapshot_ref_before":state["snapshot_ref"], "registration_request_id":registration["request_id"],
                  "registration_sha256":registration["registration_sha256"], "quality_intent_sha256":quality_sha,
                  "controller_request_id":registration["controller_request_id"], "child_request_id":child,
                  "plan_sha256":registration["plan_sha256"], "report":report, "manager_intent_sha256":intent["intent_sha256"]}
        record["record_sha256"] = fingerprint(record)
        _require(verify_original(project, state, body["report_dir"]) == report
                 and _original_quality(manager, con, project, state, body)[1] == quality_sha
                 and project.status()["snapshot_ref"] == state["snapshot_ref"], "EVIDENCE_CHANGED", "Preflight evidence changed before commit.")
        _require(_before_action(project, core, state, body, registration, con) == (stored, child),
                 "EVIDENCE_CHANGED", "Original request identities changed before commit.")
        _check_staged_runtime()
        stored.setdefault("synthetic_time_registrations", []).append(record); stored["state_version"] += 1
        project._save(core, stored)
        _manager_claim(core, "synthetic_time_registration", body["request_id"], intent["intent_sha256"], record["record_sha256"], create=True)


def register(manager, body):
    from .local_workbench import _check_staged_runtime
    from .synthetic_time_binding import verify_original
    digest = _check_body(body); _check_staged_runtime()
    with manager._writer():
        with manager._connect() as con:
            _, project = manager._project(con, body["project_id"], active=True)
            manager._no_pending_batch(con, body["project_id"], except_id=body["request_id"], evidence=True)
            old = manager._old(con, body, digest)
            if old is None:
                with project._writer(), project._connect(readonly=True) as core:
                    state = project.status()
                    registration, quality_sha = _original_quality(manager, con, project, state, body)
                    _before_action(project, core, state, body, registration, con)
                    report = verify_original(project, state, body["report_dir"])
                    intent = manager._quality_intent(body, digest, COMMAND, state)
                    intent.pop("intent_sha256"); intent["schema_version"] = "synthetic-time-manager-intent-v1"
                    intent.update(quality_intent_sha256=quality_sha, report_identity_sha256=fingerprint(report), snapshot_ref_before=state["snapshot_ref"])
                    intent["intent_sha256"] = fingerprint(intent)
                    _require(verify_original(project, state, body["report_dir"]) == report
                             and _original_quality(manager, con, project, state, body)[1] == quality_sha
                             and project.status()["snapshot_ref"] == state["snapshot_ref"], "EVIDENCE_CHANGED", "Preflight evidence changed.")
                    _before_action(project, core, state, body, registration, con)
                    _check_staged_runtime(); manager._accept(con, body, digest, COMMAND, intent); con.commit()
                _create_project_record(manager, con, project, body, digest, intent)
                old = {"status":"preparing", "intent":intent, "result":None}
            else:
                row = con.execute("SELECT command FROM requests WHERE id=?", (body["request_id"],)).fetchone()
                _require(row is not None and row["command"] == COMMAND and type(old) is dict
                         and old.get("status") in ("preparing", "completed") and type(old.get("intent")) is dict,
                         "OPERATION_INCOMPLETE", "The original synthetic time intent is unavailable.")
            result = _finish(manager, con, project, body, digest, old)
            return dict(result, replayed=old.get("status") == "completed")


def resume(manager, body):
    from .local_workbench import _body, _check_staged_runtime
    _body(body, ("request_id", "project_id")); _check_staged_runtime()
    with manager._writer(), manager._connect() as con:
        _, project = manager._project(con, body["project_id"], active=True)
        manager._no_pending_batch(con, body["project_id"], except_id=body["request_id"], evidence=True)
        row = con.execute("SELECT command,digest,record FROM requests WHERE id=?", (body["request_id"],)).fetchone()
        _require(row is not None and row["command"] == COMMAND, "OPERATION_INCOMPLETE", "Original time intent is absent; acceptance cannot be established.")
        saved = tabular._parse(row["record"].encode("utf-8"))
        _require(type(saved) is dict and saved.get("status") in ("preparing", "completed") and type(saved.get("intent")) is dict
                 and type(saved["intent"].get("body")) is dict, "OPERATION_INCOMPLETE", "Original time body is unavailable.")
        original = saved["intent"]["body"]; digest = _check_body(original)
        _require(digest == row["digest"] and original["request_id"] == body["request_id"] and original["project_id"] == body["project_id"],
                 "EVIDENCE_CHANGED", "Original time body changed.")
        result = _finish(manager, con, project, original, digest, saved)
        return dict(result, replayed=True)
