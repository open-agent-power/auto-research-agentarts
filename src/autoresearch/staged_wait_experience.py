"""Read-only capture of a conditional staged continuation that waited.

The receipt is an observation at one snapshot, not a lock on later work. The
portable case does not contain enough original material to authenticate itself.
"""
import copy
import hashlib
import json
from pathlib import Path
import re

from . import hypothesis_feedback as hypotheses, research_recipe, staged_continuation, retrieval_holdout
from . import staged_project_experience as evidence, staged_relevance_adapter as staged
from .contracts import ResearchError, canonical, fingerprint, identifier
from .host_model_selection import HostModelSelection, PENDING
from .local_workbench import LocalWorkbench
from .research_memory import ResearchMemory, observation_id, validate_scope

SCHEMA = "staged-retrieval-wait-experience-bundle-v1"
PROTOCOL = "staged-retrieval-wait-binding-v1"
NOTICE = ("The wait and its feedback were checked against their original local source at capture; "
          "offline_wait_binding_unverifiable_without_origin. Final was unmeasured at this snapshot; "
          "the wait does not prevent a later route. No scientific validation is claimed.")


def _require(condition, message, code="EVIDENCE_CHANGED"):
    if not condition:
        raise ResearchError(code, message)


def _unclaimed(project, state, manager, target):
    child = "controller-child-" + fingerprint({"project_id": state["id"], "request_id": target})[:32]
    with project._connect(readonly=True) as con:
        for value in (target, child):
            try:
                project._require_unclaimed(state, value)
            except ResearchError:
                raise ResearchError("EVIDENCE_CHANGED", "A future request ID is already occupied.") from None
            _require(project._action(con, value) is None, "A future request ID is occupied by an action.")
            _require(not any(action.get("id") == value for action in state["actions"] + state.get("evidence_actions", [])),
                     "A future ID is already an action identity.")
    with manager._connect(readonly=True) as con:
        for value in (target, child):
            _require(con.execute("SELECT 1 FROM requests WHERE id=?", (value,)).fetchone() is None,
                     "A future request ID is occupied by a manager request.")
    host = HostModelSelection(project.root).status()
    _require(not any(item.get("request_id") in (target, child) or item.get("controller_request_id") in (target, child)
                     for item in host["requests"]), "A future request ID is occupied by a host request.")
    return host


def derive_wait_observation(manager_workspace, request_id):
    """Check a completed S052 wait using original read-only manager and Project data."""
    identifier(request_id, "request_id")
    initial_reader = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    from .research_project import code_identity
    initial_core = code_identity()
    manager = LocalWorkbench.open_readonly(manager_workspace)
    with manager._connect(readonly=True) as con:
        row = con.execute("SELECT command,digest,record FROM requests WHERE id=?", (request_id,)).fetchone()
        _require(row is not None and row["command"] == "continue_staged", "Original waiting continuation unavailable.")
        raw = row["record"]
        record = json.loads(raw)
        LocalWorkbench._check_staged_continuation(record, row["digest"])
        _, project = manager._project(con, record["body"]["project_id"])
        LocalWorkbench._no_pending_batch(con, record["body"]["project_id"], request_id, evidence=True)
    state = project.status()
    body, intent, policy = record["body"], record["intent"], record["conditional"]
    _require(record["schema_version"] == "local-staged-continuation-v2" and record["status"] == "completed"
             and record["phase"] == "waiting" and body["request_id"] == request_id
             and record["cursor_snapshot_ref"] == state["snapshot_ref"] == intent["initial_snapshot_ref"]
             and state["state_version"] == body["expected_state_version"]
             and state["id"] == intent["project_id"] and state["run_id"] == intent["run_id"]
             and state["code_identity"] == intent["project_code_identity"]
             and state["source_snapshot_sha256"] == intent["source_snapshot_sha256"]
             and state["registration"]["method_id"] == staged.TOOL_ID,
             "The original waiting snapshot or source changed.")
    staged_continuation.verify_conditional_policy(state, body, policy)
    context, registration = policy["context"], policy["registration"]
    _require(context.get("project_id") == state["id"] and context.get("run_id") == state["run_id"]
             and context.get("project_code_identity") == state["code_identity"]
             and context.get("controller_code_identity") == registration["controller_code_identity"] == intent["controller_code_identity"]
             and context.get("source_snapshot_sha256") == state["source_snapshot_sha256"]
             and canonical(context.get("domain_scope")) == canonical(state["source_scope"])
             and state.get("plan_revisions") and canonical(context.get("research_plan")) == canonical(state["plan_revisions"][-1])
             and canonical(context.get("staged_evaluation")) == canonical(retrieval_holdout.public_evaluation_context(state)),
             "The sealed context differs from the original project, plan or holdout metadata.")
    actual = hypotheses.feedback_context(project, state)
    items = [item for item in actual["items"] if item["request_id"] == body["registration_request_id"]]
    _require(len(items) == 1 and canonical(items[0]) == canonical(policy["feedback"]),
             "The original feedback no longer matches its saved source.")
    item = items[0]
    _require(policy["decision"] == "wait" and state.get("frozen_evaluation_strategy") is None,
             "Only a pre-freeze wait can be captured.")
    source_sha, _, _ = evidence._dev_source(project, state)
    if item["outcome"] == "unknown":
        _require(item["unknown_reason"] == "controller_not_started" and not state["actions"]
                 and not state.get("controller_requests") and all(item[k] is None for k in ("value", "action_id", "result_sha256")),
                 "Only an unstarted original primary may be captured as unknown.")
        host_before = _unclaimed(project, state, manager, item["controller_request_id"])
        _require(_unclaimed(project, state, manager, body["primary_action_id"]) == host_before,
                 "Host state changed while checking future identities.")
        primary = None
    else:
        _require(len(state["actions"]) == 1 and state["actions"][0]["id"] == item["action_id"]
                 and item["action_id"] == body["primary_action_id"], "Original primary is missing or ambiguous.")
        action = state["actions"][0]
        evidence._verify_action_rows(project, [action])
        envelope, artifact_sha = evidence._read(project, action)
        _require(envelope["sha256"] == item["result_sha256"], "Original primary artifact changed.")
        primary = {"action_id": action["id"], "result_sha256": action["result_sha256"], "artifact_sha256": artifact_sha}
        host_before = HostModelSelection(project.root).status()
    _require(not any(v.get("status") in PENDING for v in host_before["requests"]),
             "A host request remains unresolved.")
    capture = {"project_id": state["id"], "run_id": state["run_id"], "state_version": state["state_version"],
               "snapshot_ref": state["snapshot_ref"], "source_snapshot_sha256": state["source_snapshot_sha256"],
               "source_file_sha256": source_sha, "producer_code_identity": state["code_identity"],
               "capture_code_identity": initial_core, "capture_reader_sha256": initial_reader,
               "manager_request_id": request_id, "manager_body_sha256": fingerprint(body),
               "manager_record_sha256": record["record_sha256"], "context_sha256": policy["context"]["context_sha256"]}
    scope = {"source_manifest_sha256": state["source_snapshot_sha256"],
             "inputs_sha256": fingerprint({"capture": capture, "registration_sha256": item["registration_sha256"], "primary": primary}),
             "analysis_code_sha256": fingerprint({"core": initial_core, "reader": initial_reader}), "protocol": PROTOCOL}
    entry = {"schema_version": "conditional-research-memory-v1", "kind": "diagnostic_observation", "scope": scope,
             "review_status": "derived_not_scientifically_reviewed", "numerical_recomputation": False,
             "payload": {"method_id": staged.TOOL_ID, "evaluation_ref": "staged-relevance-development-v1",
                         "source_scope": copy.deepcopy(state["source_scope"]), "feedback": copy.deepcopy(item),
                         "reason": policy["reason"], "primary": primary, "final_status": "unmeasured_at_wait"},
             "provenance": {"action_id": item["action_id"], "source_record_sha256": fingerprint(state),
                            "origin": capture, "registration": copy.deepcopy(policy["registration"])}}
    entry["id"] = observation_id(entry)
    _validate_record(entry)
    with manager._connect(readonly=True) as con:
        after = con.execute("SELECT command,digest,record FROM requests WHERE id=?", (request_id,)).fetchone()
        _require(after is not None and after["command"] == "continue_staged" and after["digest"] == fingerprint(body)
                 and after["record"] == raw, "Original manager receipt changed during capture.")
        LocalWorkbench._no_pending_batch(con, body["project_id"], request_id, evidence=True)
    if primary is not None:
        evidence._verify_action_rows(project, [action])
        _require(evidence._read(project, action)[1] == artifact_sha, "Original primary changed during capture.")
    else:
        _require(_unclaimed(project, state, manager, item["controller_request_id"]) == host_before,
                 "Host state changed during capture.")
        _require(_unclaimed(project, state, manager, body["primary_action_id"]) == host_before,
                 "Future primary identity or host state changed during capture.")
    _require(project.status() == state and evidence._dev_source(project, state)[0] == source_sha
             and HostModelSelection(project.root).status() == host_before and code_identity() == initial_core
             and hashlib.sha256(Path(__file__).read_bytes()).hexdigest() == initial_reader,
             "Original source, project or reader changed during capture.")
    return {"scope": scope, "entries": [entry], "validation": {"source_checked_at_capture": True,
            "offline_wait_binding_unverifiable_without_origin": True, "final_status": "unmeasured_at_wait"}}


def _validate_record(record):
    try:
        _require(type(record) is dict and set(record) == {"schema_version", "id", "kind", "scope", "review_status", "numerical_recomputation", "payload", "provenance"}
                 and record["schema_version"] == "conditional-research-memory-v1" and record["kind"] == "diagnostic_observation"
                 and record["review_status"] == "derived_not_scientifically_reviewed" and record["numerical_recomputation"] is False,
                 "Invalid waiting observation.", "INVALID_STAGED_EXPERIENCE")
        validate_scope(record["scope"])
        _require(record["scope"]["protocol"] == PROTOCOL and observation_id(record) == record["id"], "Waiting scope changed.")
        p, payload = record["provenance"], record["payload"]
        _require(set(p) == {"action_id", "source_record_sha256", "origin", "registration"}
                 and set(payload) == {"method_id", "evaluation_ref", "source_scope", "feedback", "reason", "primary", "final_status"}
                 and payload["method_id"] == staged.TOOL_ID and payload["evaluation_ref"] == "staged-relevance-development-v1"
                 and payload["final_status"] == "unmeasured_at_wait", "Invalid waiting payload.")
        item, reg, origin = payload["feedback"], p["registration"], p["origin"]
        _require(type(origin) is dict and set(origin) == {"project_id", "run_id", "state_version", "snapshot_ref", "source_snapshot_sha256",
                 "source_file_sha256", "producer_code_identity", "capture_code_identity", "capture_reader_sha256",
                 "manager_request_id", "manager_body_sha256", "manager_record_sha256", "context_sha256"}
                 and type(origin["state_version"]) is int and origin["state_version"] >= 0
                 and all(type(origin[k]) is str and re.fullmatch(r"[0-9a-f]{64}", origin[k]) for k in
                         ("snapshot_ref", "source_snapshot_sha256", "source_file_sha256", "producer_code_identity",
                          "capture_code_identity", "capture_reader_sha256", "manager_body_sha256", "manager_record_sha256", "context_sha256"))
                 and type(p["source_record_sha256"]) is str and re.fullmatch(r"[0-9a-f]{64}", p["source_record_sha256"]),
                 "Invalid captured identities.")
        for key in ("project_id", "run_id", "manager_request_id"):
            identifier(origin[key], key)
        hypotheses._check_record(reg)
        version = "hypothesis-feedback-context-v3" if "leave_one_out" in item["condition"] else "hypothesis-feedback-context-v2" if "all" in item["condition"] else "hypothesis-feedback-context-v1"
        hypotheses.validate_context({"schema_version": version, "items": [item], "scientific_validation": False, "test_notice": hypotheses.STAGED_NOTICE})
        _require(all(canonical(item[k]) == canonical(reg[k]) for k in ("request_id", "controller_request_id", "registration_sha256", "candidate", "condition", "branches"))
                 and reg["project_id"] == origin["project_id"] and reg["run_id"] == origin["run_id"]
                 and reg["source_snapshot_sha256"] == origin["source_snapshot_sha256"]
                 and fingerprint(payload["source_scope"]) == reg["scope_sha256"]
                 and reg["project_code_identity"] == origin["producer_code_identity"]
                 and p["action_id"] == item["action_id"], "Waiting registration binding changed.")
        if item["outcome"] == "unknown":
            _require(item["unknown_reason"] == "controller_not_started" and payload["reason"] == "feedback_unknown"
                     and payload["primary"] is None, "Unknown wait cannot claim a primary result.")
        else:
            primary = payload["primary"]
            _require(payload["reason"] == "policy_wait" and item["branches"][item["outcome"]] == {"kind": "wait"}
                     and type(primary) is dict and set(primary) == {"action_id", "result_sha256", "artifact_sha256"}
                     and primary["action_id"] == item["action_id"] and primary["result_sha256"] == item["result_sha256"]
                     and type(primary["artifact_sha256"]) is str and re.fullmatch(r"[0-9a-f]{64}", primary["artifact_sha256"]),
                     "Known wait differs from its original primary or branch.")
        _require(record["scope"]["source_manifest_sha256"] == origin["source_snapshot_sha256"]
                 and record["scope"]["inputs_sha256"] == fingerprint({"capture": origin, "registration_sha256": item["registration_sha256"], "primary": payload["primary"]})
                 and record["scope"]["analysis_code_sha256"] == fingerprint({"core": origin["capture_code_identity"], "reader": origin["capture_reader_sha256"]}),
                 "Waiting source scope changed.")
        return record
    except ResearchError:
        raise
    except (KeyError, TypeError, ValueError, AttributeError, RecursionError, OverflowError):
        raise ResearchError("INVALID_STAGED_EXPERIENCE", "Malformed waiting experience.") from None


def validate_bundle(bundle):
    try:
        _require(type(bundle) is dict and set(bundle) == {"schema_version", "id", "version", "record", "method_card", "limitations", "source_inclusion_status", "scientific_validation"}
                 and bundle["schema_version"] == SCHEMA and bundle["source_inclusion_status"] == "active_at_export"
                 and bundle["scientific_validation"] is False and type(bundle["version"]) is int and 1 <= bundle["version"] <= 2**31 - 1,
                 "Invalid waiting bundle.", "INVALID_STAGED_EXPERIENCE")
        identifier(bundle["id"], "case_id")
        _require(len(canonical(bundle).encode("utf-8")) <= 4 * 1024 * 1024, "Bundle too large.", "BUNDLE_TOO_LARGE")
        _validate_record(bundle["record"])
        card = research_recipe.validate_method_card(bundle["method_card"])
        _require(card["scope_match"] == {"domain": "retrieval", "contract": staged.CONTRACT}
                 and card["method_refs"] == [{"method_id": staged.TOOL_ID, "evaluation_ref": "staged-relevance-development-v1"}], "Invalid waiting method card.")
        _require(type(bundle["limitations"]) is list and 1 <= len(bundle["limitations"]) <= 8
                 and all(type(v) is str and 0 < len(v.strip()) <= 4000 and "\x00" not in v for v in bundle["limitations"]), "Invalid limitations.")
        return copy.deepcopy(bundle)
    except ResearchError:
        raise
    except (KeyError, TypeError, ValueError, AttributeError, RecursionError, OverflowError):
        raise ResearchError("INVALID_STAGED_EXPERIENCE", "Malformed waiting bundle.") from None


def summary(bundle):
    bundle = validate_bundle(bundle)
    record, card = bundle["record"], bundle["method_card"]
    payload, p = record["payload"], record["provenance"]
    value = {"case_id": bundle["id"], "case_version": bundle["version"], "entry_id": record["id"], "method_card": card,
             "origin_evidence": {**p["origin"], "action_id": p["action_id"],
                                 "result_sha256": payload["feedback"]["result_sha256"], "binding_scope": record["scope"]},
             "source_scope": copy.deepcopy(payload["source_scope"]),
             "observation": {"kind": "staged_wait_feedback", "method_id": payload["method_id"],
                             "feedback": copy.deepcopy(payload["feedback"]), "reason": payload["reason"],
                             "primary": copy.deepcopy(payload["primary"]), "final_status": payload["final_status"]},
             "limitations": [*bundle["limitations"], NOTICE], "transfer_scope": "analogy_not_current_evidence", "scientific_validation": False}
    _require(len(canonical(value).encode("utf-8")) <= 64 * 1024, "Summary too large.", "SUMMARY_TOO_LARGE")
    return value


class StagedWaitExperienceMemory(ResearchMemory):
    def import_wait(self, manager_workspace, request_id):
        return self._import_derived(derive_wait_observation(manager_workspace, request_id), verification="binding")

    def export_case(self, scope, entry_id, *, case_id, version, method_card, limitations):
        validate_scope(scope)
        with self._connect() as con:
            row = con.execute("SELECT * FROM entries WHERE id=?", (entry_id,)).fetchone() if con is not None else None
            _require(row is not None, "Waiting memory entry not found.", "NOT_FOUND")
            record = self._verify(con, row)
            _require(record["scope"] == scope and row["status"] == "active", "Waiting memory is not active under this scope.")
            return validate_bundle({"schema_version": SCHEMA, "id": case_id, "version": version, "record": record,
                                    "method_card": method_card, "limitations": limitations,
                                    "source_inclusion_status": "active_at_export", "scientific_validation": False})
