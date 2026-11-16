"""One opt-in artificial time-bound quality action; no real-source admission.

Manager, controller parent and child are separate transactions. An accepted
nonterminal request is inspected without dispatch or replacement. This module
is not a source-rights check, scientific validation or authorization by itself.
"""
import copy
from functools import wraps
import hashlib
import re
import secrets

from .contracts import ResearchError, canonical, fingerprint, identifier
from . import project_controller, project_selection, tabular_quality_adapter as tabular
from . import tabular_quality_feedback as quality_feedback, synthetic_time_registration as time_registration
from .tabular_quality_feedback import _manager_claim

COMMAND = "advance_synthetic_time_quality_primary"
FIELDS = ("request_id", "project_id", "expected_state_version", "registration_request_id", "registration_sha256",
          "time_registration_request_id", "time_registration_sha256", "reason")
_HASH = re.compile(r"[a-f0-9]{64}\Z")


def _require(ok, code, message):
    if not ok:
        raise ResearchError(code, message)


def _checked_entry(function):
    """Map malformed originals and I/O failures without masking ResearchError."""
    @wraps(function)
    def checked(*args, **kwargs):
        try:
            return function(*args, **kwargs)
        except ResearchError:
            raise
        except (OSError, ValueError, TypeError, AttributeError, KeyError, IndexError, OverflowError, RecursionError):
            raise ResearchError("EVIDENCE_CHANGED", "The original time-bound quality records are malformed or unavailable.") from None
    return checked


def _check_body(body):
    from .local_workbench import _body, _text
    digest = _body(body, FIELDS)
    for name in ("project_id", "registration_request_id", "time_registration_request_id"):
        identifier(body[name], name)
    _require(type(body["expected_state_version"]) is int and body["expected_state_version"] >= 0
             and all(type(body[name]) is str and _HASH.fullmatch(body[name]) for name in ("registration_sha256", "time_registration_sha256"))
             and _text(body["reason"], 4000), "INVALID_REQUEST", "Use the original quality and artificial time registrations, version and bounded reason.")
    return digest


def _quality_original(manager, con, project, state, body):
    registration, intent_sha = time_registration._original_quality(manager, con, project, state, body)
    row = con.execute("SELECT record FROM requests WHERE id=? AND command='register_tabular_quality_conditions'", (body["registration_request_id"],)).fetchone()
    _require(row is not None, "OPERATION_INCOMPLETE", "Original quality registration is absent.")
    saved = tabular._parse(row["record"].encode("utf-8")); receipt = saved.get("result")
    expected = manager._response("register_tabular_quality_conditions", body["registration_request_id"], body["project_id"], status="completed", registration=registration)
    _require(type(receipt) is dict and set(receipt) == set(expected) and type(receipt.get("replayed")) is bool
             and canonical({k:v for k,v in receipt.items() if k != "replayed"}) == canonical({k:v for k,v in expected.items() if k != "replayed"}),
             "EVIDENCE_CHANGED", "Original quality manager receipt changed.")
    return registration, intent_sha


def _time_original(manager, con, project, body):
    from .local_workbench import _body
    row = con.execute("SELECT command,digest,record FROM requests WHERE id=?", (body["time_registration_request_id"],)).fetchone()
    _require(row is not None and row["command"] == time_registration.COMMAND,
             "OPERATION_INCOMPLETE", "The original synthetic time manager registration is absent.")
    saved = tabular._parse(row["record"].encode("utf-8"))
    _require(type(saved) is dict and set(saved) == {"status", "intent", "result"} and saved["status"] == "completed"
             and type(saved["intent"]) is dict and type(saved["intent"].get("body")) is dict and type(saved["result"]) is dict,
             "OPERATION_INCOMPLETE", "The original synthetic time manager receipt is incomplete.")
    original = saved["intent"]["body"]
    digest = time_registration._check_body(original)
    _require(_body(original, time_registration.FIELDS) == digest == row["digest"]
             and original["request_id"] == body["time_registration_request_id"] and original["project_id"] == body["project_id"]
             and original["registration_request_id"] == body["registration_request_id"] and original["registration_sha256"] == body["registration_sha256"],
             "EVIDENCE_CHANGED", "The original synthetic time manager body changed.")
    record = time_registration._inspect(manager, con, project, original, digest, saved)
    expected = manager._response(time_registration.COMMAND, original["request_id"], original["project_id"], status="completed", registration=record)
    receipt = saved["result"]
    _require(set(receipt) == set(expected) and type(receipt.get("replayed")) is bool
             and canonical({k:v for k,v in receipt.items() if k != "replayed"}) == canonical({k:v for k,v in expected.items() if k != "replayed"})
             and record["record_sha256"] == body["time_registration_sha256"],
             "EVIDENCE_CHANGED", "The original synthetic time record or receipt changed.")
    return record, saved["intent"]["intent_sha256"], original["report_dir"]


def _preflight(manager, con, project, state, body):
    from .host_model_selection import HostModelSelection, PENDING
    registration, quality_intent = _quality_original(manager, con, project, state, body)
    time_record, time_intent, report_dir = _time_original(manager, con, project, body)
    _require(project.status()["snapshot_ref"] == state["snapshot_ref"] and state["state_version"] == body["expected_state_version"]
             and registration["registration_sha256"] == body["registration_sha256"]
             and registration["controller_request_id"] == body["request_id"] == time_record["controller_request_id"]
             and time_record["registration_request_id"] == registration["request_id"]
             and time_record["registration_sha256"] == registration["registration_sha256"]
             and registration["state_version_before"] < time_record["state_version_before"] < state["state_version"],
             "EVIDENCE_CHANGED", "Use the exact preregistered future ID and temporal ordering.")
    project._require_fresh(state, state, body["expected_state_version"])
    _require(not state.get("actions") and not state.get("evidence_actions") and not state.get("controller_requests")
             and not any(item.get("status") in ("sending", "unknown") for item in state.get("source_requests", []))
             and not any(item.get("status") == "reserved" for item in state.get("local_model_requests", []))
             and not any(item.get("status") in PENDING for item in HostModelSelection(project.root).status()["requests"]),
             "PROJECT_BUSY", "Inspect existing source, action, controller or Host requests first.")
    budget = state["budget"]
    _require(all(type(budget.get(k)) is int for k in ("local_tool_call_limit", "local_tool_calls_used", "local_tool_calls_reserved",
                                                      "model_requests_allowed", "new_model_requests", "model_requests_reserved", "fit_attempts_used", "fits_reserved"))
             and budget["local_tool_call_limit"] >= 1
             and budget.get("local_tool_calls_used") == 0 and budget.get("local_tool_calls_reserved") == 0
             and budget.get("model_requests_allowed") == 0 and budget.get("new_model_requests") == 0 and budget.get("model_requests_reserved") == 0
             and budget.get("fit_attempts_used") == 0 and budget.get("fits_reserved") == 0,
             "CONDITION_NOT_SATISFIED", "The artificial quality action requires its original unspent tool, model and fit budget.")
    child = "controller-child-" + fingerprint({"project_id":state["id"], "request_id":body["request_id"]})[:32]
    _require(len({body["request_id"], body["registration_request_id"], body["time_registration_request_id"], child}) == 4
             and child == time_record["child_request_id"], "EVIDENCE_CHANGED", "The original future and child IDs differ.")
    manager._quality_unclaimed(project, state, (body["request_id"], child))
    _require(con.execute("SELECT 1 FROM requests WHERE id=?", (child,)).fetchone() is None,
             "IDEMPOTENCY_CONFLICT", "The original child ID is already used by the workbench.")
    _require(state.get("plan_revisions") and fingerprint(state["plan_revisions"][-1]) == registration["plan_sha256"] == time_record["plan_sha256"]
             and state["source_snapshot_sha256"] == registration["source_snapshot_sha256"] == time_record["report"]["source_snapshot_sha256"],
             "EVIDENCE_CHANGED", "The original plan or synthetic source changed.")
    controller = project_controller.ProjectController(project.root)
    context = controller._selection_context(state, "next_check")
    feedback = quality_feedback.read_feedback(project, request_id=body["registration_request_id"])
    _require(feedback.get("outcome") == "unknown" and feedback.get("unknown_reason") == "controller_not_started"
             and not context["blockers"] and context["candidates"].count(registration["candidate"]) == 1
             and registration["candidate"]["method_id"] == tabular.TOOL_ID,
             "CONDITION_NOT_SATISFIED", "The original quality candidate is not uniquely eligible and unstarted.")
    proposal = {"schema_version":"project-selection-proposal-v1", "context_sha256":context["context_sha256"],
                "provider":{"kind":"operator_assistant", "label":"Explicit artificial time-bound quality action"},
                "choice":{"kind":"execute", "candidate_id":registration["candidate"]["id"]},
                "rationale":body["reason"], "evidence_citation_ids":[]}
    selected = project_selection.validate_proposal(context, proposal)
    plan = controller._selected_plan(state, "next_check", proposal, context=context)
    _require(selected["candidate"] == registration["candidate"] and selected["evidence_citation_ids"] == []
             and plan["executable"] and plan["decision"]["next_action"]["method_id"] == tabular.TOOL_ID
             and project.status()["snapshot_ref"] == state["snapshot_ref"],
             "CONDITION_NOT_SATISFIED", "The bound quality candidate is not executable under the current budget.")
    return registration, quality_intent, time_record, time_intent, report_dir, context, proposal


def _intent(manager, body, digest, state, quality_intent, time_record, time_intent, report_dir, context, proposal):
    from .local_workbench import batch_code_identity
    from .research_project import code_identity
    intent = {"schema_version":"local-synthetic-time-quality-primary-intent-v1", "command":COMMAND,
              "body":copy.deepcopy(body), "request_sha256":digest, "project_id":state["id"], "run_id":state["run_id"],
              "source_snapshot_sha256":state["source_snapshot_sha256"], "project_code_identity":code_identity(),
              "controller_code_identity":project_controller.code_identity(), "manager_code_identity":batch_code_identity(),
              "manager_root":str(manager.root.resolve()), "quality_intent_sha256":quality_intent,
              "time_intent_sha256":time_intent, "time_record_sha256":time_record["record_sha256"],
              "report_dir":report_dir, "report_identity_sha256":fingerprint(time_record["report"]),
              "selection_context":copy.deepcopy(context), "proposal":copy.deepcopy(proposal), "nonce":secrets.token_hex(32)}
    intent["intent_sha256"] = fingerprint(intent)
    return intent


def _check_intent(manager, intent, body, digest, state):
    from .local_workbench import batch_code_identity, _EXPORT_BOOT_IDENTITY
    from .research_project import code_identity
    fields = {"schema_version", "command", "body", "request_sha256", "project_id", "run_id", "source_snapshot_sha256",
              "project_code_identity", "controller_code_identity", "manager_code_identity", "manager_root", "quality_intent_sha256",
              "time_intent_sha256", "time_record_sha256", "report_dir", "report_identity_sha256", "selection_context", "proposal", "nonce", "intent_sha256"}
    _require(type(intent) is dict and set(intent) == fields and intent["schema_version"] == "local-synthetic-time-quality-primary-intent-v1"
             and intent["command"] == COMMAND and canonical(intent["body"]) == canonical(body)
             and digest == intent["request_sha256"] == fingerprint(body)
             and intent["intent_sha256"] == fingerprint({k:v for k,v in intent.items() if k != "intent_sha256"})
             and intent["project_id"] == body["project_id"] == state["id"] and intent["run_id"] == state["run_id"]
             and intent["source_snapshot_sha256"] == state["source_snapshot_sha256"]
             and intent["project_code_identity"] == state["code_identity"] == code_identity()
             and intent["controller_code_identity"] == project_controller.code_identity()
             and intent["manager_code_identity"] == batch_code_identity() == _EXPORT_BOOT_IDENTITY
             and intent["manager_root"] == str(manager.root.resolve())
             and all(type(intent.get(k)) is str and _HASH.fullmatch(intent[k]) for k in ("nonce", "quality_intent_sha256", "time_intent_sha256", "time_record_sha256", "report_identity_sha256"))
             and type(intent["report_dir"]) is str and 0 < len(intent["report_dir"]) <= 4096,
             "EVIDENCE_CHANGED", "Original time-bound quality intent or producer changed.")


def _inspect_locked(manager, con, project, body, digest, saved):
    from .local_workbench import _check_staged_runtime, batch_code_identity, _EXPORT_BOOT_IDENTITY
    from .research_project import code_identity, _quality_primary_parent_claim_sha, _quality_primary_child_claim_sha, _quality_primary_claim_kinds
    from . import staged_project_experience as artifacts
    _check_staged_runtime()
    state = project.status(); intent = saved["intent"]
    _check_intent(manager, intent, body, digest, state)
    registration, quality_intent = _quality_original(manager, con, project, state, body)
    time_record, time_intent, report_dir = _time_original(manager, con, project, body)
    _require(quality_intent == intent["quality_intent_sha256"] and time_intent == intent["time_intent_sha256"]
             and time_record["record_sha256"] == intent["time_record_sha256"] == body["time_registration_sha256"]
             and fingerprint(time_record["report"]) == intent["report_identity_sha256"] and report_dir == intent["report_dir"]
             and registration["registration_sha256"] == body["registration_sha256"]
             and registration["controller_request_id"] == time_record["controller_request_id"] == body["request_id"]
             and registration["state_version_before"] < time_record["state_version_before"] < body["expected_state_version"] < state["state_version"],
             "EVIDENCE_CHANGED", "The original registrations, time report or chronology changed.")
    parents = [item for item in state.get("controller_requests", []) if item.get("request_id") == body["request_id"]]
    _require(len(parents) == 1 and parents[0].get("status") == "completed", "OPERATION_INCOMPLETE", "The original parent is absent or not completed; do not dispatch.")
    parent = parents[0]; meta = parent.get("tabular_quality_primary"); parent_sha = _quality_primary_parent_claim_sha(parent)
    context = intent["selection_context"]
    selected = project_selection.validate_proposal(context, intent["proposal"])
    expected_request = {"project_id":body["project_id"], "command":"controller.advance_selection", "need":"next_check",
                        "expected_state_version":body["expected_state_version"], "proposal":intent["proposal"]}
    _require(type(meta) is dict and meta.get("schema_version") == "tabular-quality-primary-binding-v2"
             and meta["manager_intent_sha256"] == intent["intent_sha256"] and meta["registration_intent_sha256"] == quality_intent
             and meta["registration_request_id"] == registration["request_id"] and meta["registration_sha256"] == registration["registration_sha256"]
             and meta["plan_sha256"] == registration["plan_sha256"] and meta["source_snapshot_sha256"] == state["source_snapshot_sha256"]
             and meta["time_registration_request_id"] == body["time_registration_request_id"]
             and meta["time_registration_sha256"] == time_record["record_sha256"] and meta["time_intent_sha256"] == time_intent
             and meta["time_report_sha256"] == fingerprint(time_record["report"]) == intent["report_identity_sha256"] and meta["report_dir"] == report_dir
             and meta["state_version_before"] == parent["state_version_before"] == body["expected_state_version"]
             and parent["dispatch_state_version"] == body["expected_state_version"] + 1
             and type(parent.get("state_version_after")) is int and parent["dispatch_state_version"] < parent["state_version_after"] <= state["state_version"]
             and parent["child_request_id"] == time_record["child_request_id"]
             and parent["request"] == expected_request and parent["request_sha256"] == fingerprint(expected_request)
             and canonical(parent["selection_context"]) == canonical(context)
             and context["project_id"] == state["id"] and context["run_id"] == state["run_id"]
             and context["state_version"] == body["expected_state_version"] and context["snapshot_ref"] == parent["snapshot_ref_before"]
             and context["source_snapshot_sha256"] == state["source_snapshot_sha256"]
             and context["project_code_identity"] == intent["project_code_identity"] and context["controller_code_identity"] == intent["controller_code_identity"]
             and fingerprint(context["research_plan"]) == registration["plan_sha256"]
             and selected["candidate"] == registration["candidate"] and selected["evidence_citation_ids"] == []
             and parent["decision"]["next_action"]["method_id"] == tabular.TOOL_ID,
             "EVIDENCE_CHANGED", "The original time-bound parent, candidate or report binding changed.")
    actions = [item for item in state.get("actions", []) if item.get("request_id") == parent["child_request_id"]]
    _require(len(actions) == 1 and actions[0].get("status") == "completed", "OPERATION_INCOMPLETE", "The original quality child is absent or not completed.")
    child = actions[0]
    artifacts._action(child, state, tabular.TOOL_ID); artifacts._verify_action_rows(project, [child])
    envelope, raw_sha = artifacts._read(project, child)
    _require(raw_sha == hashlib.sha256(canonical(envelope).encode("utf-8")).hexdigest(), "EVIDENCE_CHANGED", "The original quality artifact bytes changed.")
    child_view = {k:copy.deepcopy(child[k]) for k in ("id", "request_id", "command", "status", "artifact", "result_sha256", "failure") if k in child}
    _require(parent.get("result") == {"child":child_view, "recovered":False, "reused":False}, "EVIDENCE_CHANGED", "The original parent and child result differ.")
    plans = state.get("plan_revisions", []); version = registration["plan_version"]
    _require(type(plans) is list and type(version) is int and 1 <= version <= len(plans)
             and fingerprint(plans[version-1]) == registration["plan_sha256"] == time_record["plan_sha256"],
             "EVIDENCE_CHANGED", "The original saved quality plan changed.")
    historical = copy.deepcopy(state); historical["plan_revisions"] = [copy.deepcopy(plans[version-1])]
    feedback = quality_feedback._outcome(project, historical, registration)
    _require((feedback.get("outcome") in ("condition_met", "condition_not_met")
              and feedback.get("action_id") == child["id"] and feedback.get("result_sha256") == child["result_sha256"])
             or (feedback.get("outcome") == "unknown" and feedback.get("unknown_reason") == "quality_values_unknown"
                 and type(feedback.get("evaluation")) is dict),
             "EVIDENCE_CHANGED", "Saved quality feedback is unavailable or damaged.")
    parent_kind, child_kind = _quality_primary_claim_kinds(parent)
    _require((parent_kind, child_kind) == ("synthetic_time_quality_parent", "synthetic_time_quality_child"),
             "EVIDENCE_CHANGED", "The original quality ownership kind differs.")
    with project._connect(readonly=True) as core:
        _manager_claim(core, parent_kind, parent["request_id"], intent["intent_sha256"], parent_sha)
        _manager_claim(core, child_kind, child["request_id"], intent["intent_sha256"], _quality_primary_child_claim_sha(parent, child["request_sha256"]))
    project._source(state)
    _require(project.status()["snapshot_ref"] == state["snapshot_ref"] and artifacts._read(project, child)[1] == raw_sha
             and code_identity() == intent["project_code_identity"] and project_controller.code_identity() == intent["controller_code_identity"]
             and batch_code_identity() == intent["manager_code_identity"] == _EXPORT_BOOT_IDENTITY,
             "EVIDENCE_CHANGED", "The original source, result or code changed during inspection.")
    artifacts._verify_action_rows(project, [child])
    _require(_quality_original(manager, con, project, state, body) == (registration, quality_intent)
             and _time_original(manager, con, project, body) == (time_record, time_intent, report_dir),
             "EVIDENCE_CHANGED", "The original registrations changed during inspection.")
    with project._connect(readonly=True) as core:
        _manager_claim(core, parent_kind, parent["request_id"], intent["intent_sha256"], parent_sha)
        _manager_claim(core, child_kind, child["request_id"], intent["intent_sha256"], _quality_primary_child_claim_sha(parent, child["request_sha256"]))
    _require(project.status()["snapshot_ref"] == state["snapshot_ref"], "EVIDENCE_CHANGED", "The original Project changed during inspection.")
    _check_staged_runtime()
    return project_controller.ProjectController._response(parent, True)


def _finish(manager, con, project, body, digest, saved):
    from .local_workbench import _check_staged_runtime
    try:
        with project._writer():
            result = _inspect_locked(manager, con, project, body, digest, saved)
            response = manager._response(COMMAND, body["request_id"], body["project_id"], status="completed", controller=result)
            if saved["status"] == "completed":
                receipt = saved.get("result")
                _require(type(receipt) is dict and set(receipt) == set(response) and type(receipt.get("replayed")) is bool
                         and canonical({k:v for k,v in receipt.items() if k != "replayed"}) == canonical({k:v for k,v in response.items() if k != "replayed"}),
                         "EVIDENCE_CHANGED", "The original time-bound manager receipt changed.")
            else:
                _require(saved["status"] == "preparing" and saved.get("result") is None, "OPERATION_INCOMPLETE", "The original manager intent is incomplete.")
                manager._save(con, body["request_id"], {"status":"completed", "intent":saved["intent"], "result":response})
                _require(_inspect_locked(manager, con, project, body, digest, saved) == result,
                         "EVIDENCE_CHANGED", "The original evidence changed before manager receipt commit.")
                _check_staged_runtime(); con.commit()
            return response
    except ResearchError:
        raise
    except (OSError, ValueError, TypeError, AttributeError, KeyError, IndexError, OverflowError, RecursionError):
        raise ResearchError("EVIDENCE_CHANGED", "The original time-bound quality records are malformed or unavailable.") from None


@_checked_entry
def advance(manager, body):
    from .local_workbench import _check_staged_runtime
    digest = _check_body(body); _check_staged_runtime()
    with manager._writer():
        with manager._connect() as con:
            _, project = manager._project(con, body["project_id"], active=True)
            old = manager._old(con, body, digest)
            manager._no_pending_batch(con, body["project_id"], except_id=body["request_id"], evidence=True)
            if old is None:
                with project._writer():
                    state = project.status()
                    registration, quality_intent, time_record, time_intent, report_dir, context, proposal = _preflight(manager, con, project, state, body)
                    intent = _intent(manager, body, digest, state, quality_intent, time_record, time_intent, report_dir, context, proposal)
                    checked = _preflight(manager, con, project, state, body)
                    _require(checked == (registration, quality_intent, time_record, time_intent, report_dir, context, proposal)
                             and project.status()["snapshot_ref"] == state["snapshot_ref"], "EVIDENCE_CHANGED", "Original preflight changed before manager acceptance.")
                    _check_intent(manager, intent, body, digest, state)
                    _check_staged_runtime(); manager._accept(con, body, digest, COMMAND, intent); con.commit()
            else:
                row = con.execute("SELECT command FROM requests WHERE id=?", (body["request_id"],)).fetchone()
                _require(row is not None and row["command"] == COMMAND and type(old) is dict and set(old) == {"status", "intent", "result"}
                         and old["status"] in ("preparing", "completed") and type(old["intent"]) is dict
                         and (old["status"] != "preparing" or old["result"] is None),
                         "OPERATION_INCOMPLETE", "The original time-bound primary intent is unavailable.")
                intent = old["intent"]
            if old is None:
                _check_staged_runtime()
                project_controller.ProjectController(project.root)._advance_synthetic_time_quality_primary(
                    request_id=body["request_id"], registration_request_id=body["registration_request_id"], registration_sha256=body["registration_sha256"],
                    time_registration_request_id=body["time_registration_request_id"], time_registration_sha256=body["time_registration_sha256"],
                    expected_state_version=body["expected_state_version"], proposal=intent["proposal"], _manager_intent_sha256=intent["intent_sha256"],
                    _registration_intent_sha256=intent["quality_intent_sha256"], _time_intent_sha256=intent["time_intent_sha256"], _report_dir=intent["report_dir"])
                saved = {"status":"preparing", "intent":intent, "result":None}
            else:
                saved = old
            response = _finish(manager, con, project, body, digest, saved)
            return dict(response, replayed=old is not None)


@_checked_entry
def resume(manager, body):
    from .local_workbench import _body, _check_staged_runtime
    _body(body, ("request_id", "project_id")); _check_staged_runtime()
    with manager._writer(), manager._connect() as con:
        _, project = manager._project(con, body["project_id"], active=True)
        manager._no_pending_batch(con, body["project_id"], except_id=body["request_id"], evidence=True)
        row = con.execute("SELECT command,digest,record FROM requests WHERE id=?", (body["request_id"],)).fetchone()
        _require(row is not None and row["command"] == COMMAND, "OPERATION_INCOMPLETE", "The original time-bound intent is absent; acceptance cannot be established.")
        saved = tabular._parse(row["record"].encode("utf-8"))
        _require(type(saved) is dict and set(saved) == {"status", "intent", "result"} and saved["status"] in ("preparing", "completed")
                 and type(saved["intent"]) is dict and type(saved["intent"].get("body")) is dict
                 and (saved["status"] != "preparing" or saved["result"] is None),
                 "OPERATION_INCOMPLETE", "The original manager body is unavailable.")
        original = saved["intent"]["body"]; digest = _check_body(original)
        _require(digest == row["digest"] and original["request_id"] == body["request_id"] and original["project_id"] == body["project_id"],
                 "EVIDENCE_CHANGED", "The original time-bound manager body changed.")
        response = _finish(manager, con, project, original, digest, saved)
        return dict(response, replayed=True)
