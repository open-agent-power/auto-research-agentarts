"""JSON-only adapter for a future AgentArts invocation; no hidden platform calls."""

import sqlite3
from .contracts import Candidate, ResearchError, identifier
from .engine import Engine
from .reports import build_report

FIELDS = {
    "create_campaign": {"goal", "max_trials", "dataset_id", "policy_kind"},
    "campaign_status": {"campaign_id"},
    "run_trial": {"campaign_id", "candidate", "reason"},
    "pause_campaign": {"campaign_id"},
    "resume_campaign": {"campaign_id"},
    "finalize_campaign": {"campaign_id"},
    "observe_campaign": {"campaign_id"},
    "submit_proposal": {"campaign_id", "proposal"},
    "research_report": {"campaign_id"},
}


def handle_request(request, workspace):
    request_id = request.get("request_id") if isinstance(request, dict) else None
    response_id = request_id if isinstance(request_id, str) else None
    try:
        if not isinstance(request, dict) or request.get("schema_version") != "0.1":
            raise ResearchError("INVALID_REQUEST", "schema_version must be 0.1")
        identifier(request_id)
        action = request.get("action")
        if not isinstance(action, str) or action not in FIELDS:
            raise ResearchError("INVALID_REQUEST", "unknown action")
        allowed = FIELDS[action] | {"schema_version", "request_id", "action"}
        if set(request) - allowed:
            raise ResearchError("INVALID_REQUEST", "unsupported fields; evaluation, paths and commands are not caller-configurable")
        if action != "create_campaign":
            identifier(request.get("campaign_id"), "campaign_id")
        if "candidate" in request:
            Candidate.parse(request["candidate"])
        engine = Engine(workspace)
        if action == "create_campaign":
            options = {key: request[key] for key in ("dataset_id", "policy_kind") if key in request}
            result = engine.create(request_id, request.get("goal"), request.get("max_trials", 3), **options)
        elif action == "campaign_status":
            result = engine.status(request["campaign_id"])
        elif action == "run_trial":
            result = engine.step(request["campaign_id"], request_id, request.get("candidate"), request.get("reason"))
        elif action == "pause_campaign":
            result = engine.pause(request["campaign_id"])
        elif action == "resume_campaign":
            result = engine.pause(request["campaign_id"], False)
        elif action == "observe_campaign":
            result = engine.observe(request["campaign_id"])
        elif action == "submit_proposal":
            result = engine.submit(request["campaign_id"], request_id, request.get("proposal"))
        elif action == "research_report":
            result = build_report(engine, request["campaign_id"])
        else:
            result = engine.finalize(request["campaign_id"])
        return {"schema_version": "0.1", "request_id": response_id, "ok": True, "result": result}
    except ResearchError as exc:
        return {"schema_version": "0.1", "request_id": response_id, "ok": False,
                "error": {"code": exc.code, "message": str(exc)}}
    except (sqlite3.Error, OSError, ValueError, TypeError, KeyError):
        return {"schema_version": "0.1", "request_id": response_id, "ok": False,
                "error": {"code": "INTERNAL_ERROR", "message": "execution or storage error; inspect local operator logs"}}
