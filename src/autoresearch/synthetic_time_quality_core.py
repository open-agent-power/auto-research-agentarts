"""Project-side consistency check for the S136 artificial time binding.

Write callers hold the Project writer; unlocked readers get an observed
snapshot with before/after checks. The manager separately authenticates its
own original S084/S135 intents; local SQL claims are not signatures.
"""
from .contracts import ResearchError, fingerprint
from .synthetic_time_binding import verify_observed as _verify_report_observed
from .tabular_quality_feedback import _checked_collection, _manager_claim


def verify_observed(project, state, meta):
    """Check an observed snapshot twice; callers need a writer for writes.

    Public readers may use this without locking and must still check their
    surrounding snapshot. This is not a claim of writer isolation.
    """
    try:
        quality = state.get("tabular_quality_registrations", [])
        _checked_collection(quality)
        quality = [r for r in quality if r["request_id"] == meta["registration_request_id"]]
        times = state.get("synthetic_time_registrations", [])
        if type(times) is not list:
            raise ResearchError("EVIDENCE_CHANGED", "Original time registrations are malformed.")
        times = [r for r in times if type(r) is dict and r.get("request_id") == meta["time_registration_request_id"]]
        if len(quality) != 1 or len(times) != 1:
            raise ResearchError("OPERATION_INCOMPLETE", "Original quality or time registration is absent.")
        registration, time = quality[0], times[0]
        if not (time.get("schema_version") == "synthetic-time-registration-v1"
                and time.get("record_sha256") == fingerprint({k:v for k,v in time.items() if k != "record_sha256"})
                and time["record_sha256"] == meta["time_registration_sha256"]
                and time["manager_intent_sha256"] == meta["time_intent_sha256"]
                and time["quality_intent_sha256"] == meta["registration_intent_sha256"]
                and time["project_id"] == registration["project_id"] == state["id"]
                and time["run_id"] == registration["run_id"] == state["run_id"]
                and time["registration_request_id"] == registration["request_id"]
                and time["registration_sha256"] == registration["registration_sha256"] == meta["registration_sha256"]
                and time["controller_request_id"] == registration["controller_request_id"] == meta["controller_request_id"]
                and time["child_request_id"] == meta["child_request_id"]
                and time["plan_sha256"] == registration["plan_sha256"] == meta["plan_sha256"]
                and registration["state_version_before"] < time["state_version_before"] < meta["state_version_before"]
                and registration["source_snapshot_sha256"] == state["source_snapshot_sha256"] == meta["source_snapshot_sha256"]
                and registration["source_sha256"] == state["registration"]["source_sha256"]
                and registration["scope_sha256"] == fingerprint(state["source_scope"])
                and registration["project_code_identity"] == state["code_identity"]):
            raise ResearchError("EVIDENCE_CHANGED", "Original quality, time or Project binding changed.")
        with project._connect(readonly=True) as con:
            _manager_claim(con, "registration", registration["request_id"], meta["registration_intent_sha256"], registration["registration_sha256"])
            _manager_claim(con, "synthetic_time_registration", time["request_id"], meta["time_intent_sha256"], time["record_sha256"])
        report = _verify_report_observed(project, state, meta["report_dir"])
        if not (time["report"] == report and fingerprint(report) == meta["time_report_sha256"]):
            raise ResearchError("EVIDENCE_CHANGED", "Original synthetic time report changed.")
        with project._connect(readonly=True) as con:
            _manager_claim(con, "registration", registration["request_id"], meta["registration_intent_sha256"], registration["registration_sha256"])
            _manager_claim(con, "synthetic_time_registration", time["request_id"], meta["time_intent_sha256"], time["record_sha256"])
        if project.status()["snapshot_ref"] != state["snapshot_ref"]:
            raise ResearchError("EVIDENCE_CHANGED", "Project changed during synthetic time inspection.")
        return registration, time, report
    except ResearchError:
        raise
    except (KeyError, TypeError, ValueError, AttributeError, RecursionError):
        raise ResearchError("EVIDENCE_CHANGED", "Original synthetic time binding is malformed.") from None


def verify_locked(project, state, meta):
    """Same checks; the caller holds the cooperative Project writer."""
    return verify_observed(project, state, meta)
