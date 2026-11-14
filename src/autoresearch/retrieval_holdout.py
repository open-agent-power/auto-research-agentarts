"""Trusted-host-only, preregistered final retrieval evaluation.

The private package is a procedural separation between cooperating processes
under the same user. It is not an OS security boundary or a blind-study claim.
No API here accepts filesystem paths from a project request or a model.
"""
import copy
import hashlib
import json
import math
import os
import re
from pathlib import Path

from . import relevance_retrieval_adapter as relevance, retrieval_lexical as lexical
from .contracts import ResearchError, canonical, fingerprint, identifier


def require(*args, **kwargs):
    from .research_project import require as implementation
    return implementation(*args, **kwargs)


def safe_path(*args, **kwargs):
    from .research_project import safe_path as implementation
    return implementation(*args, **kwargs)


def write_bytes_once(*args, **kwargs):
    from .research_project import write_bytes_once as implementation
    return implementation(*args, **kwargs)

PRIMARY_TOOL_ID = "research.relevance-validation-pair"
FINAL_TOOL_ID = "research.relevance-final-evaluation"
ADAPTER_VERSION = "1"
MAX_HOLDOUT_BYTES = 2 * 1024 * 1024
POLICY = "validation-recall20-tfidf-minus-bm25-gt-zero-v1"
PRIVATE_DIR = "private_evaluation"
PRIVATE_FILE = "holdout.json"


def code_identity():
    return hashlib.sha256(Path(__file__).read_bytes() + Path(lexical.__file__).read_bytes()
                          + Path(relevance.__file__).read_bytes()).hexdigest()


def _source(project, state):
    from . import staged_relevance_adapter as staged
    require(state["registration"]["method_id"] == PRIMARY_TOOL_ID,
            "CONDITION_NOT_SATISFIED", "Final evaluation requires the staged retrieval primary.")
    payload = project._source(state)
    return staged, payload, staged._checked(payload)


def _host_ready(project, state):
    from .host_model_selection import HostModelSelection, PENDING
    require(not any(x["status"] in ("prepared", "running", "unknown") for x in state.get("controller_requests", []))
            and not any(x["status"] == "reserved" for x in state.get("local_model_requests", [])),
            "PROJECT_BUSY", "Resolve pending controller and model requests first.")
    require(not any(x["status"] in PENDING for x in HostModelSelection(project.root).status()["requests"]),
            "HOST_SELECTION_PENDING", "Resolve the original host request first.")


def _path(project):
    return safe_path(safe_path(project.root / PRIVATE_DIR) / PRIVATE_FILE)


def _checked_holdout(raw, payload, checked):
    require(type(raw) is bytes and 0 < len(raw) <= MAX_HOLDOUT_BYTES,
            "INVALID_REQUEST", "Use a bounded UTF-8 holdout JSON byte packet.")
    obj = relevance._parse(raw)
    require(type(obj) is dict and set(obj) == {"schema_version", "corpus_sha256", "queries_jsonl", "qrels_tsv"}
            and obj["schema_version"] == "retrieval-holdout-v1"
            and obj["corpus_sha256"] == payload["assets"]["corpus"]["sha256"]
            and type(obj["queries_jsonl"]) is str and type(obj["qrels_tsv"]) is str,
            "INVALID_REQUEST", "Holdout must bind the exact registered corpus and original query/qrels text.")
    try:
        qraw, rraw = obj["queries_jsonl"].encode("utf-8"), obj["qrels_tsv"].encode("utf-8")
    except UnicodeError:
        raise ResearchError("INVALID_REQUEST", "Holdout text is not valid UTF-8.") from None
    # _checked returns the staged source's parsed corpus and development queries.
    spec, docs, dev_queries, _, _, _ = checked
    queries, _ = relevance._jsonl(qraw, False)
    qrels = relevance._qrels(rraw, docs, queries)
    require(set(queries) == set(qrels) and not set(queries) & set(dev_queries)
            and all(row["metadata"] == {} for row in queries.values()),
            "INVALID_SOURCE", "Final query metadata must be empty; every final query requires qrels and a distinct development ID.")
    return queries, qrels


def validate_metadata(state):
    """Validate persisted metadata and its state bindings without reading private bytes."""
    digest = lambda value: type(value) is str and re.fullmatch(r"[0-9a-f]{64}", value) is not None
    ident = lambda value: type(value) is str and re.fullmatch(r"[A-Za-z0-9_.:-]{1,80}", value) is not None
    bounded_int = lambda value, low, high: type(value) is int and low <= value <= high
    try:
        require(type(state) is dict, "EVIDENCE_CHANGED", "Project metadata is malformed.")
        private = state.get("private_evaluation")
        frozen = state.get("frozen_evaluation_strategy")
        if private is None:
            require("private_evaluation" not in state and "frozen_evaluation_strategy" not in state,
                    "EVIDENCE_CHANGED", "A freeze requires a valid holdout registration.")
            return None
        private_fields = {"schema_version", "request_id", "request_sha256", "request", "project_id", "run_id",
                          "state_version_before", "sha256", "bytes", "query_count", "corpus_sha256", "source_sha256",
                          "source_snapshot_sha256", "plan_sha256", "plan_version", "project_code_identity", "policy",
                          "scientific_validation", "record_sha256"}
        require(type(private) is dict and set(private) == private_fields
                and private["schema_version"] == "retrieval-holdout-registration-v1"
                and all(ident(private[k]) for k in ("request_id", "project_id", "run_id"))
                and all(digest(private[k]) for k in ("request_sha256", "sha256", "corpus_sha256", "source_sha256",
                        "source_snapshot_sha256", "plan_sha256", "project_code_identity", "record_sha256"))
                and bounded_int(private["state_version_before"], 0, 2**63 - 1)
                and bounded_int(private["bytes"], 1, MAX_HOLDOUT_BYTES)
                and bounded_int(private["query_count"], 1, relevance.LIMITS["max_queries"])
                and bounded_int(private["plan_version"], 1, 2**63 - 1)
                and type(private["policy"]) is str and private["policy"] == POLICY
                and private["scientific_validation"] is False,
                "EVIDENCE_CHANGED", "Holdout registration schema or values changed.")
        expected_request = {"request_id": private["request_id"], "expected_state_version": private["state_version_before"],
                            "holdout_sha256": private["sha256"], "holdout_bytes": private["bytes"]}
        require(type(private["request"]) is dict and private["request"] == expected_request
                and type(private["request"]["expected_state_version"]) is int
                and type(private["request"]["holdout_bytes"]) is int
                and private["request_sha256"] == fingerprint(expected_request)
                and private["record_sha256"] == fingerprint({k: v for k, v in private.items() if k != "record_sha256"}),
                "EVIDENCE_CHANGED", "Holdout request or record identity changed.")
        require(ident(state.get("id")) and ident(state.get("run_id"))
                and bounded_int(state.get("state_version"), 1, 2**63 - 1)
                and state["state_version"] > private["state_version_before"]
                and private["project_id"] == state["id"] and private["run_id"] == state["run_id"]
                and private["source_sha256"] == state["registration"]["source_sha256"]
                and private["source_snapshot_sha256"] == state["source_snapshot_sha256"]
                and private["project_code_identity"] == state["code_identity"]
                and private["corpus_sha256"] == state["source_scope"]["input_identities"]["corpus"]["sha256"],
                "EVIDENCE_CHANGED", "Holdout project or source identity changed.")
        plans = state.get("plan_revisions")
        require(type(plans) is list, "EVIDENCE_CHANGED", "Registered plan history is unavailable.")
        matching_plans = [plan for plan in plans if type(plan) is dict and type(plan.get("version")) is int
                          and plan["version"] == private["plan_version"]]
        require(len(matching_plans) == 1 and fingerprint(matching_plans[0]) == private["plan_sha256"],
                "EVIDENCE_CHANGED", "Registered plan identity changed.")
        if frozen is None:
            require("frozen_evaluation_strategy" not in state, "EVIDENCE_CHANGED", "Frozen metadata is malformed.")
            return {"private_evaluation": copy.deepcopy(private), "frozen_evaluation_strategy": None}
        freeze_fields = {"schema_version", "request_id", "request", "request_sha256", "project_id", "run_id",
                         "holdout_record_sha256", "source_snapshot_sha256", "plan_sha256", "project_code_identity",
                         "primary_action_id", "primary_result_sha256", "validation_delta_recall20", "policy",
                         "selected_method", "scientific_validation", "record_sha256"}
        require(type(frozen) is dict and set(frozen) == freeze_fields
                and frozen["schema_version"] == "retrieval-holdout-freeze-v1"
                and all(ident(frozen[k]) for k in ("request_id", "project_id", "run_id", "primary_action_id"))
                and all(digest(frozen[k]) for k in ("request_sha256", "holdout_record_sha256", "source_snapshot_sha256",
                        "plan_sha256", "project_code_identity", "primary_result_sha256", "record_sha256"))
                and type(frozen["validation_delta_recall20"]) in (int, float)
                and math.isfinite(frozen["validation_delta_recall20"]) and -1 <= frozen["validation_delta_recall20"] <= 1
                and type(frozen["policy"]) is str and frozen["policy"] == POLICY
                and type(frozen["selected_method"]) is str
                and frozen["selected_method"] == ("tfidf_cosine" if frozen["validation_delta_recall20"] > 0 else "bm25")
                and frozen["scientific_validation"] is False,
                "EVIDENCE_CHANGED", "Frozen strategy schema or values changed.")
        request = frozen["request"]
        require(type(request) is dict and set(request) == {"request_id", "expected_state_version", "primary_action_id"}
                and request["request_id"] == frozen["request_id"] and request["primary_action_id"] == frozen["primary_action_id"]
                and bounded_int(request["expected_state_version"], private["state_version_before"] + 1, state["state_version"] - 1)
                and frozen["request_sha256"] == fingerprint(request)
                and frozen["record_sha256"] == fingerprint({k: v for k, v in frozen.items() if k != "record_sha256"})
                and frozen["request_id"] != private["request_id"]
                and frozen["project_id"] == private["project_id"] and frozen["run_id"] == private["run_id"]
                and frozen["holdout_record_sha256"] == private["record_sha256"]
                and frozen["source_snapshot_sha256"] == private["source_snapshot_sha256"]
                and frozen["plan_sha256"] == private["plan_sha256"]
                and frozen["project_code_identity"] == private["project_code_identity"],
                "EVIDENCE_CHANGED", "Frozen request or registration binding changed.")
        return {"private_evaluation": copy.deepcopy(private), "frozen_evaluation_strategy": copy.deepcopy(frozen)}
    except ResearchError as exc:
        raise ResearchError("EVIDENCE_CHANGED", "Evaluation metadata or its state binding changed.") from exc
    except (KeyError, TypeError, ValueError, OverflowError, UnicodeError, RecursionError):
        raise ResearchError("EVIDENCE_CHANGED", "Evaluation metadata is malformed.") from None


def _private_record(state):
    checked = validate_metadata(state)
    require(checked is not None, "EVIDENCE_CHANGED", "Holdout registration is missing.")
    return checked["private_evaluation"]


def _verified_private(project, state):
    record = _private_record(state)
    try:
        with _path(project).open("rb") as stream:
            raw = stream.read(MAX_HOLDOUT_BYTES + 1)
    except OSError:
        raise ResearchError("EVIDENCE_CHANGED", "Registered private holdout bytes are unavailable.") from None
    require(len(raw) == record["bytes"] and len(raw) <= MAX_HOLDOUT_BYTES
            and hashlib.sha256(raw).hexdigest() == record["sha256"],
            "EVIDENCE_CHANGED", "Private holdout bytes differ from registration.")
    return record, raw


def register_holdout(project, *, request_id, expected_state_version, holdout):
    """Persist one private packet before any primary action exists."""
    identifier(request_id)
    require(type(expected_state_version) is int and expected_state_version >= 0,
            "INVALID_REQUEST", "A current exact state version is required.")
    require(type(holdout) is bytes and 0 < len(holdout) <= MAX_HOLDOUT_BYTES,
            "INVALID_REQUEST", "Use bounded holdout JSON bytes.")
    digest = hashlib.sha256(holdout).hexdigest()
    request = {"request_id": request_id, "expected_state_version": expected_state_version,
               "holdout_sha256": digest, "holdout_bytes": len(holdout)}
    with project._writer(), project._connect() as con:
        state = project._project(con)
        old = state.get("private_evaluation")
        if old is not None:
            require(old.get("request_id") == request_id and old.get("request_sha256") == fingerprint(request),
                    "IDEMPOTENCY_CONFLICT", "A different private holdout is already registered.")
            _verified_private(project, state)
            require(project._source(state)["snapshot_sha256"] == old["source_snapshot_sha256"],
                    "EVIDENCE_CHANGED", "The source binding changed.")
            return copy.deepcopy(old)
        require(project._action(con, request_id) is None, "IDEMPOTENCY_CONFLICT", "Request ID belongs to an action.")
        project._require_unclaimed(state, request_id)
        current = project.status()
        project._require_fresh(state, current, expected_state_version)
        _host_ready(project, state)
        require(not current["actions"] and not state.get("controller_requests"),
                "CONDITION_NOT_SATISFIED", "Register final data before primary or controller requests exist.")
        plans = state.get("plan_revisions", [])
        require(bool(plans), "CONDITION_NOT_SATISFIED", "Save the research plan before final registration.")
        staged, payload, checked = _source(project, state)
        queries, _ = _checked_holdout(holdout, payload, checked)
        directory = safe_path(project.root / PRIVATE_DIR)
        directory.mkdir(mode=0o700, exist_ok=True)
        require(directory.is_dir(), "EVIDENCE_CHANGED", "Private evaluation directory is unavailable.")
        os.chmod(directory, 0o700)
        write_bytes_once(_path(project), holdout)
        record = {"schema_version": "retrieval-holdout-registration-v1", "request_id": request_id,
                  "request_sha256": fingerprint(request), "request": request, "project_id": state["id"],
                  "run_id": state["run_id"], "state_version_before": expected_state_version,
                  "sha256": digest, "bytes": len(holdout), "query_count": len(queries),
                  "corpus_sha256": payload["assets"]["corpus"]["sha256"],
                  "source_sha256": state["registration"]["source_sha256"], "source_snapshot_sha256": state["source_snapshot_sha256"],
                  "plan_sha256": fingerprint(plans[-1]), "plan_version": plans[-1]["version"],
                  "project_code_identity": state["code_identity"], "policy": POLICY,
                  "scientific_validation": False}
        record["record_sha256"] = fingerprint(record)
        state["private_evaluation"] = record
        state["state_version"] += 1
        project._save(con, state)
        return copy.deepcopy(record)


def verify_holdout(project, state):
    """Verify privately after the original compute-start marker, return metadata only."""
    actions = [a for a in state.get("actions", []) if a.get("command") == FINAL_TOOL_ID]
    require(len(actions) == 1, "CONDITION_NOT_SATISFIED", "Private bytes are unavailable before the final action starts.")
    action = actions[0]
    identifier(action["id"], "action_id")
    marker = safe_path(project.root / PRIVATE_DIR / ("execution-" + action["id"] + ".json"))
    try:
        with marker.open("rb") as stream:
            raw = stream.read(8193)
        require(len(raw) <= 8192, "EVIDENCE_CHANGED", "Final start marker is oversized.")
        claim = json.loads(raw)
    except (OSError, ValueError, TypeError):
        raise ResearchError("CONDITION_NOT_SATISFIED", "Original final start marker is unavailable.") from None
    frozen = state.get("frozen_evaluation_strategy", {})
    require(claim == {"schema_version": "retrieval-final-execution-start-v1", "project_id": state["id"],
             "action_id": action["id"], "request_id": action["request_id"], "request_sha256": action["request_sha256"],
             "source_snapshot_sha256": state["source_snapshot_sha256"], "freeze_sha256": frozen.get("record_sha256"),
             "code_identity": state["code_identity"]}, "EVIDENCE_CHANGED", "Final start marker does not match its action.")
    record, _ = _verified_private(project, state)
    return copy.deepcopy(record)


def _original(project, state, action_id):
    from . import staged_relevance_adapter as staged, method_registry as registry
    current = project.status()
    actions = [a for a in current["actions"] if a["id"] == action_id]
    require(len(actions) == 1, "EVIDENCE_CHANGED", "Original primary action is unavailable.")
    action = actions[0]
    require(action["status"] == "completed" and action["command"] == PRIMARY_TOOL_ID
            and action.get("project_id") == state["id"] and action.get("run_id") == state["run_id"]
            and action.get("code_identity") == state["code_identity"]
            and action.get("source_snapshot_sha256") == state["source_snapshot_sha256"]
            and action.get("method_instance", {}).get("evaluation_ref") == registry.evaluation_ref(PRIMARY_TOOL_ID)
            and action.get("method_instance", {}).get("definition_ref", {}).get("id") == PRIMARY_TOOL_ID,
            "EVIDENCE_CHANGED", "Original primary action does not match this project.")
    with project._connect(readonly=True) as con:
        require(project._action(con, action["request_id"]) == action, "EVIDENCE_CHANGED", "Primary action record changed.")
    try:
        envelope = json.loads(project._artifact(action).read_bytes())
    except (OSError, ValueError, TypeError):
        raise ResearchError("EVIDENCE_CHANGED", "Original primary artifact is unavailable.") from None
    require(envelope.get("sha256") == action["result_sha256"] == fingerprint({k: v for k, v in envelope.items() if k != "sha256"})
            and envelope.get("action_id") == action_id and envelope.get("request_sha256") == action["request_sha256"]
            and envelope.get("source_snapshot_sha256") == state["source_snapshot_sha256"]
            and envelope.get("code_identity") == state["code_identity"],
            "EVIDENCE_CHANGED", "Original action/result envelope binding changed.")
    original = envelope["tool_result"]
    result = staged._saved(original)
    require(result["source_snapshot_sha256"] == state["source_snapshot_sha256"]
            and result["scope"] == state["source_scope"],
            "EVIDENCE_CHANGED", "Original result source or scope differs.")
    return action, original, result


def freeze_strategy(project, *, request_id, expected_state_version, primary_action_id):
    """Freeze the predetermined strategy based only on saved validation data."""
    identifier(request_id)
    identifier(primary_action_id, "primary_action_id")
    require(type(expected_state_version) is int and expected_state_version >= 0,
            "INVALID_REQUEST", "A current exact state version is required.")
    request = {"request_id": request_id, "expected_state_version": expected_state_version, "primary_action_id": primary_action_id}
    with project._writer(), project._connect() as con:
        state = project._project(con)
        old = state.get("frozen_evaluation_strategy")
        if old is not None:
            require(old.get("request_id") == request_id and old.get("request_sha256") == fingerprint(request),
                    "IDEMPOTENCY_CONFLICT", "A different strategy freeze already exists.")
            _check_frozen(project, state, old)
            return copy.deepcopy(old)
        require(project._action(con, request_id) is None, "IDEMPOTENCY_CONFLICT", "Request ID belongs to an action.")
        project._require_unclaimed(state, request_id)
        require(request_id != state.get("private_evaluation", {}).get("request_id"), "IDEMPOTENCY_CONFLICT", "Request ID already registered the holdout.")
        current = project.status()
        project._require_fresh(state, current, expected_state_version)
        _host_ready(project, state)
        holdout = _private_record(state)
        staged, payload, _ = _source(project, state)
        plans = state.get("plan_revisions", [])
        require(bool(plans) and fingerprint(plans[-1]) == holdout["plan_sha256"]
                and state["id"] == holdout["project_id"] and state["run_id"] == holdout["run_id"]
                and state["code_identity"] == holdout["project_code_identity"]
                and state["source_snapshot_sha256"] == holdout["source_snapshot_sha256"]
                and state["registration"]["source_sha256"] == holdout["source_sha256"],
                "EVIDENCE_CHANGED", "Plan, source or code differs from preregistration.")
        require(not any(a["command"] == FINAL_TOOL_ID for a in current["actions"]),
                "CONDITION_NOT_SATISFIED", "Final evaluation has already been attempted.")
        action, _, result = _original(project, state, primary_action_id)
        summary, _, _ = staged._paired(result["per_query_metrics"])
        require(canonical(summary) == canonical(result["paired_summary"]), "EVIDENCE_CHANGED", "Saved validation arithmetic differs.")
        delta = summary["splits"]["validation"]["paired_candidate_minus_baseline"]["recall@20"]["mean"]
        require(type(delta) in (int, float) and math.isfinite(delta) and -1 <= delta <= 1,
                "INVALID_RESULT", "Saved validation delta is invalid.")
        record = {"schema_version": "retrieval-holdout-freeze-v1", "request_id": request_id,
                  "request": request, "request_sha256": fingerprint(request), "project_id": state["id"], "run_id": state["run_id"],
                  "holdout_record_sha256": holdout["record_sha256"], "source_snapshot_sha256": state["source_snapshot_sha256"],
                  "plan_sha256": holdout["plan_sha256"], "project_code_identity": state["code_identity"],
                  "primary_action_id": action["id"], "primary_result_sha256": action["result_sha256"],
                  "validation_delta_recall20": delta, "policy": POLICY,
                  "selected_method": "tfidf_cosine" if delta > 0 else "bm25", "scientific_validation": False}
        record["record_sha256"] = fingerprint(record)
        state["frozen_evaluation_strategy"] = record
        state["state_version"] += 1
        project._save(con, state)
        return copy.deepcopy(record)


def _check_frozen(project, state, frozen):
    checked = validate_metadata(state)
    require(checked is not None and checked["frozen_evaluation_strategy"] == frozen,
            "EVIDENCE_CHANGED", "Frozen strategy metadata changed.")
    holdout = checked["private_evaluation"]
    require(type(frozen) is dict and frozen.get("record_sha256") == fingerprint({k: v for k, v in frozen.items() if k != "record_sha256"})
            and frozen.get("holdout_record_sha256") == holdout["record_sha256"]
            and frozen.get("project_id") == state["id"] and frozen.get("run_id") == state["run_id"]
            and frozen.get("source_snapshot_sha256") == state["source_snapshot_sha256"]
            and frozen.get("project_code_identity") == state["code_identity"]
            and frozen.get("plan_sha256") == holdout["plan_sha256"]
            and state.get("plan_revisions") and fingerprint(state["plan_revisions"][-1]) == frozen["plan_sha256"]
            and frozen.get("policy") == POLICY
            and frozen.get("scientific_validation") is False,
            "EVIDENCE_CHANGED", "Frozen strategy or its source/plan binding changed.")
    action, original, result = _original(project, state, frozen["primary_action_id"])
    from . import staged_relevance_adapter as staged
    summary, _, _ = staged._paired(result["per_query_metrics"])
    delta = summary["splits"]["validation"]["paired_candidate_minus_baseline"]["recall@20"]["mean"]
    require(canonical(summary) == canonical(result["paired_summary"]) and delta == frozen["validation_delta_recall20"]
            and frozen["selected_method"] == ("tfidf_cosine" if delta > 0 else "bm25")
            and action["result_sha256"] == frozen["primary_result_sha256"],
            "EVIDENCE_CHANGED", "Frozen strategy disagrees with the original saved validation result.")
    return holdout, original


PUBLIC_LIMITATIONS = "Procedural same-user separation; not a blind or scientifically approved evaluation."


def validate_public_evaluation_context(value):
    """Validate the exact metadata-only projection accepted by selection contexts."""
    digest = lambda x: type(x) is str and re.fullmatch(r"[0-9a-f]{64}", x) is not None
    try:
        require(type(value) is dict and set(value) == {"schema_version", "holdout_sha256", "query_count", "policy", "freeze", "final", "scientific_validation", "limitations"}
                and value["schema_version"] == "staged-evaluation-context-v1" and digest(value["holdout_sha256"])
                and type(value["query_count"]) is int and 1 <= value["query_count"] <= relevance.LIMITS["max_queries"]
                and value["policy"] == POLICY and value["scientific_validation"] is False
                and value["limitations"] == PUBLIC_LIMITATIONS, "INVALID_SELECTION_CONTEXT", "Invalid evaluation metadata.")
        frozen = value["freeze"]
        if frozen is not None:
            require(type(frozen) is dict and set(frozen) == {"selected_method", "validation_delta_recall20", "primary_action_id", "primary_result_sha256", "freeze_sha256"}
                    and frozen["selected_method"] in ("bm25", "tfidf_cosine")
                    and type(frozen["validation_delta_recall20"]) in (int, float) and math.isfinite(frozen["validation_delta_recall20"])
                    and -1 <= frozen["validation_delta_recall20"] <= 1
                    and frozen["selected_method"] == ("tfidf_cosine" if frozen["validation_delta_recall20"] > 0 else "bm25")
                    and type(frozen["primary_action_id"]) is str and 0 < len(frozen["primary_action_id"]) <= 160
                    and digest(frozen["primary_result_sha256"]) and digest(frozen["freeze_sha256"]),
                    "INVALID_SELECTION_CONTEXT", "Invalid frozen evaluation metadata.")
        final = value["final"]
        if final is not None:
            require(frozen is not None and type(final) is dict and set(final) == {"status", "action_id", "result_sha256"}
                    and final["status"] in ("running", "unknown", "failed", "completed")
                    and type(final["action_id"]) is str and 0 < len(final["action_id"]) <= 160
                    and (digest(final["result_sha256"]) if final["status"] == "completed" else final["result_sha256"] is None),
                    "INVALID_SELECTION_CONTEXT", "Invalid final action metadata.")
        return copy.deepcopy(value)
    except ResearchError:
        raise
    except (KeyError, TypeError, ValueError, OverflowError, RecursionError):
        raise ResearchError("INVALID_SELECTION_CONTEXT", "Malformed evaluation metadata.") from None


def public_evaluation_context(state):
    """Project a narrow, metadata-only view without opening the private file."""
    checked = validate_metadata(state)
    if checked is None:
        return None
    try:
        registered = checked["private_evaluation"]
        require(registered["project_id"] == state["id"] and registered["run_id"] == state["run_id"]
                and registered["source_snapshot_sha256"] == state["source_snapshot_sha256"]
                and registered["project_code_identity"] == state["code_identity"] and registered["policy"] == POLICY,
                "EVIDENCE_CHANGED", "Private registration identity changed.")
        value = {"schema_version": "staged-evaluation-context-v1", "holdout_sha256": registered["sha256"],
                 "query_count": registered["query_count"], "policy": POLICY, "freeze": None, "final": None,
                 "scientific_validation": False, "limitations": PUBLIC_LIMITATIONS}
        frozen = state.get("frozen_evaluation_strategy")
        if frozen is not None:
            require(frozen.get("record_sha256") == fingerprint({k: v for k, v in frozen.items() if k != "record_sha256"})
                    and frozen["holdout_record_sha256"] == registered["record_sha256"]
                    and frozen["project_id"] == state["id"] and frozen["run_id"] == state["run_id"]
                    and frozen["source_snapshot_sha256"] == state["source_snapshot_sha256"]
                    and frozen["project_code_identity"] == state["code_identity"] and frozen["policy"] == POLICY,
                    "EVIDENCE_CHANGED", "Frozen evaluation identity changed.")
            value["freeze"] = {key: copy.deepcopy(frozen[key]) for key in ("selected_method", "validation_delta_recall20", "primary_action_id", "primary_result_sha256")}
            value["freeze"]["freeze_sha256"] = frozen["record_sha256"]
        actions = [a for a in state["actions"] if a["command"] == FINAL_TOOL_ID]
        require(len(actions) <= 1, "EVIDENCE_CHANGED", "Multiple final actions violate the fixed protocol.")
        if actions:
            action = actions[0]
            require(frozen is not None and action.get("project_id") == state["id"] and action.get("run_id") == state["run_id"]
                    and action.get("source_snapshot_sha256") == state["source_snapshot_sha256"]
                    and action.get("code_identity") == state["code_identity"]
                    and action.get("method_instance", {}).get("parameters") == {"based_on_action_id": frozen["primary_action_id"],
                                                                                "based_on_result_sha256": frozen["primary_result_sha256"]},
                    "EVIDENCE_CHANGED", "Final action identity changed.")
            value["final"] = {"status": action["status"], "action_id": action["id"],
                              "result_sha256": action.get("result_sha256") if action["status"] == "completed" else None}
        return validate_public_evaluation_context(value)
    except ResearchError:
        raise
    except (KeyError, TypeError, ValueError, RecursionError):
        raise ResearchError("EVIDENCE_CHANGED", "Evaluation metadata is malformed.") from None


def eligible_metadata(state, parameters):
    """Conservative metadata-only candidate hint; dispatch must revalidate evidence."""
    try:
        frozen = state["frozen_evaluation_strategy"]
        holdout = state["private_evaluation"]
        return bool(frozen["record_sha256"] == fingerprint({k: v for k, v in frozen.items() if k != "record_sha256"})
                and holdout["record_sha256"] == fingerprint({k: v for k, v in holdout.items() if k != "record_sha256"})
                and frozen["holdout_record_sha256"] == holdout["record_sha256"]
                and frozen["project_id"] == state["id"] and frozen["run_id"] == state["run_id"]
                and frozen["source_snapshot_sha256"] == state["source_snapshot_sha256"]
                and frozen["project_code_identity"] == state["code_identity"]
                and state.get("plan_revisions") and fingerprint(state["plan_revisions"][-1]) == frozen["plan_sha256"]
                and parameters == {"based_on_action_id": frozen["primary_action_id"],
                                   "based_on_result_sha256": frozen["primary_result_sha256"]}
                and not any(a["command"] == FINAL_TOOL_ID for a in state["actions"]))
    except (KeyError, TypeError, ValueError, RecursionError):
        return False


def eligible_project(project, state, original, parameters):
    """Fresh-dispatch eligibility; caller owns budget and unknown/replay guards."""
    try:
        frozen = state["frozen_evaluation_strategy"]
        _, expected_original = _check_frozen(project, state, frozen)
        return (type(parameters) is dict and parameters == {"based_on_action_id": frozen["primary_action_id"],
                    "based_on_result_sha256": frozen["primary_result_sha256"]}
                and canonical(original) == canonical(expected_original)
                and not any(a["command"] == FINAL_TOOL_ID for a in state["actions"]))
    except (ResearchError, KeyError, TypeError, ValueError, OSError, RecursionError):
        return False


def validate_final_result(tool):
    """Reject extra fields and inconsistent numeric results before export."""
    try:
        require(type(tool) is dict and set(tool) == {"schema_version", "tool_id", "adapter_version", "status", "observations", "evidence_refs", "metrics", "result", "failure", "model_calls", "new_fits", "scientific_validation"}
                and tool["schema_version"] == "retrieval-final-evaluation-result-v1" and tool["tool_id"] == FINAL_TOOL_ID
                and tool["adapter_version"] == ADAPTER_VERSION and tool["status"] == "completed"
                and tool["failure"] is None and type(tool["model_calls"]) is int and tool["model_calls"] == 0
                and type(tool["new_fits"]) is int and tool["new_fits"] == 0 and tool["scientific_validation"] is False
                and tool["evidence_refs"] == [], "INVALID_RESULT", "Invalid final envelope.")
        result = tool["result"]
        require(type(result) is dict and set(result) == {"scope", "source_snapshot_sha256", "predecessor", "holdout_sha256", "freeze_sha256", "selected_method", "baseline_method", "summary", "per_query", "usage", "limitations"},
                "INVALID_RESULT", "Invalid final result fields.")
        digest = lambda x: type(x) is str and re.fullmatch(r"[0-9a-f]{64}", x) is not None
        scope = result["scope"]
        require(type(scope) is dict and set(scope) == {"contract", "query_count", "corpus_sha256"}
                and scope["contract"] == "procedural-final-retrieval-v1" and type(scope["query_count"]) is int
                and 1 <= scope["query_count"] <= relevance.LIMITS["max_queries"] and digest(scope["corpus_sha256"])
                and all(digest(result[k]) for k in ("source_snapshot_sha256", "holdout_sha256", "freeze_sha256"))
                and result["selected_method"] in ("bm25", "tfidf_cosine") and result["baseline_method"] == "bm25",
                "INVALID_RESULT", "Invalid final scope or identity.")
        pred = result["predecessor"]
        require(type(pred) is dict and set(pred) == {"based_on_action_id", "based_on_result_sha256"}
                and type(pred["based_on_action_id"]) is str and 0 < len(pred["based_on_action_id"]) <= 160
                and digest(pred["based_on_result_sha256"]), "INVALID_RESULT", "Invalid final predecessor.")
        rows = result["per_query"]
        require(type(rows) is list and len(rows) == scope["query_count"], "INVALID_RESULT", "Invalid final query count.")
        seen = set()
        for row in rows:
            require(type(row) is dict and set(row) == {"query_id_sha256", "baseline", "selected", "delta"}
                    and digest(row["query_id_sha256"]) and row["query_id_sha256"] not in seen,
                    "INVALID_RESULT", "Invalid hashed final query row.")
            seen.add(row["query_id_sha256"])
            for kind in ("baseline", "selected", "delta"):
                require(type(row[kind]) is dict and set(row[kind]) == set(lexical.METRICS)
                        and all(type(n) in (int, float) and math.isfinite(n) and (-1 if kind == "delta" else 0) <= n <= 1 for n in row[kind].values()),
                        "INVALID_RESULT", "Invalid final metric values.")
            require(all(row["delta"][k] == row["selected"][k] - row["baseline"][k] for k in lexical.METRICS),
                    "INVALID_RESULT", "Final per-query deltas differ.")
            if result["selected_method"] == "bm25":
                require(row["selected"] == row["baseline"], "INVALID_RESULT", "Baseline selection must reuse the baseline.")
        summary = {kind: {k: sum(row[kind][k] for row in rows) / len(rows) for k in lexical.METRICS}
                   for kind in ("baseline", "selected", "delta")}
        require(result["summary"] == summary, "INVALID_RESULT", "Final summary does not match rows.")
        n = len(rows)
        require(result["usage"] == {"index_builds": 1, "ranking_calls": n * (1 if result["selected_method"] == "bm25" else 2), "scoring_calls": n * (1 if result["selected_method"] == "bm25" else 2), "native_fits": 0, "model_calls": 0}
                and result["limitations"] == ["Procedural same-user separation only; not OS-isolated or independently blind.",
                                               "Final binary relevance metrics do not establish scientific validity."]
                and tool["metrics"] == [{"name": "evaluated_queries", "value": n, "unit": "query"}]
                and tool["observations"] == [{"producer": FINAL_TOOL_ID, "kind": "final_retrieval_evaluation",
                        "summary": {"query_count": n, "summary": summary}, "scope": scope, "evidence_refs": [],
                        "interpretation_status": "computed_not_scientifically_reviewed", "scientific_validation": False}],
                "INVALID_RESULT", "Final usage, observations or limitations differ.")
        return copy.deepcopy(result)
    except ResearchError:
        raise
    except (KeyError, TypeError, ValueError, OverflowError, RecursionError):
        raise ResearchError("INVALID_RESULT", "Malformed final retrieval result.") from None


class FinalRetrievalEvaluation:
    TOOL_ID = FINAL_TOOL_ID
    ADAPTER_VERSION = ADAPTER_VERSION
    code_identity = staticmethod(code_identity)

    @staticmethod
    def eligible(original):
        from . import staged_relevance_adapter as staged
        try:
            staged._saved(original)
            return True
        except (ResearchError, KeyError, TypeError, ValueError, RecursionError):
            return False

    def execute_project(self, workspace, original, parameters):
        from .research_project import ResearchProject
        project = ResearchProject(workspace)
        state = project.status()
        running = [a for a in state["actions"] if a["command"] == FINAL_TOOL_ID and a["status"] == "running"]
        require(len(running) == 1 and running[0].get("method_instance", {}).get("parameters") == parameters,
                "CONDITION_NOT_SATISFIED", "The original final action must already be reserved by Project.step.")
        action = running[0]
        frozen = state["frozen_evaluation_strategy"]
        private_record = _private_record(state)
        require(frozen.get("record_sha256") == fingerprint({k: v for k, v in frozen.items() if k != "record_sha256"})
                and frozen.get("holdout_record_sha256") == private_record["record_sha256"]
                and frozen.get("project_id") == state["id"] and frozen.get("run_id") == state["run_id"]
                and frozen.get("source_snapshot_sha256") == state["source_snapshot_sha256"]
                and frozen.get("project_code_identity") == state["code_identity"]
                and action.get("project_id") == state["id"] and action.get("run_id") == state["run_id"]
                and action.get("source_snapshot_sha256") == state["source_snapshot_sha256"]
                and action.get("code_identity") == state["code_identity"]
                and parameters == {"based_on_action_id": frozen["primary_action_id"],
                                   "based_on_result_sha256": frozen["primary_result_sha256"]},
                "EVIDENCE_CHANGED", "The final claim or preregistered bindings differ.")
        with project._connect(readonly=True) as con:
            require(project._action(con, action["request_id"]) == action, "EVIDENCE_CHANGED", "Final action claim changed.")
        identifier(action["id"], "action_id")
        claim = {"schema_version": "retrieval-final-execution-start-v1", "project_id": state["id"],
                 "action_id": action["id"], "request_id": action["request_id"], "request_sha256": action["request_sha256"],
                 "source_snapshot_sha256": state["source_snapshot_sha256"], "freeze_sha256": frozen["record_sha256"],
                 "code_identity": state["code_identity"]}
        marker = safe_path(project.root / PRIVATE_DIR / ("execution-" + action["id"] + ".json"))
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
        try:
            fd = os.open(marker, flags, 0o600)
        except FileExistsError:
            raise ResearchError("EXECUTION_UNKNOWN", "Final computation has already started; recover the original action.") from None
        with os.fdopen(fd, "wb") as stream:
            stream.write(canonical(claim).encode("utf-8"))
            stream.flush()
            os.fsync(stream.fileno())
        dir_fd = os.open(marker.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)
        # After this write-once marker, any crash is reconciled only through the
        # original action; never compute again, including an incomplete marker.
        holdout, expected = _check_frozen(project, state, frozen)
        require(canonical(original) == canonical(expected), "EVIDENCE_CHANGED", "Final input differs from the saved primary result.")
        _, raw = _verified_private(project, state)
        _, payload, checked = _source(project, state)
        queries, qrels = _checked_holdout(raw, payload, checked)
        _, docs, _, _, _, _ = checked
        index = lexical.build_index(docs)
        rows = []
        for qid in sorted(queries):
            selected = frozen["selected_method"]
            ranks = {"bm25": relevance.retrieve(queries[qid]["text"], index, "bm25", exclude_doc_id=qid)}
            if selected != "bm25":
                ranks[selected] = relevance.retrieve(queries[qid]["text"], index, selected, exclude_doc_id=qid)
            baseline = lexical.metrics(ranks["bm25"], qrels[qid])
            chosen = baseline if selected == "bm25" else lexical.metrics(ranks[selected], qrels[qid])
            rows.append({"query_id_sha256": hashlib.sha256(qid.encode("utf-8")).hexdigest(),
                         "baseline": baseline, "selected": chosen,
                         "delta": {key: chosen[key] - baseline[key] for key in lexical.METRICS}})
        n = len(rows)
        summary = {key: {name: sum(row[key][name] for row in rows) / n for name in lexical.METRICS}
                   for key in ("baseline", "selected", "delta")}
        result = {"scope": {"contract": "procedural-final-retrieval-v1", "query_count": n,
                            "corpus_sha256": holdout["corpus_sha256"]},
                  "source_snapshot_sha256": state["source_snapshot_sha256"], "predecessor": copy.deepcopy(parameters),
                  "holdout_sha256": holdout["sha256"], "freeze_sha256": frozen["record_sha256"],
                  "selected_method": frozen["selected_method"], "baseline_method": "bm25", "summary": summary,
                  "per_query": rows, "usage": {"index_builds": 1, "ranking_calls": n * (1 if frozen["selected_method"] == "bm25" else 2),
                                                "scoring_calls": n * (1 if frozen["selected_method"] == "bm25" else 2), "native_fits": 0, "model_calls": 0},
                  "limitations": ["Procedural same-user separation only; not OS-isolated or independently blind.",
                                  "Final binary relevance metrics do not establish scientific validity."]}
        tool = {"schema_version": "retrieval-final-evaluation-result-v1", "tool_id": FINAL_TOOL_ID,
                "adapter_version": ADAPTER_VERSION, "status": "completed",
                "observations": [{"producer": FINAL_TOOL_ID, "kind": "final_retrieval_evaluation",
                                  "summary": {"query_count": n, "summary": summary}, "scope": result["scope"],
                                  "evidence_refs": [], "interpretation_status": "computed_not_scientifically_reviewed", "scientific_validation": False}],
                "evidence_refs": [], "metrics": [{"name": "evaluated_queries", "value": n, "unit": "query"}],
                "result": result, "failure": None, "model_calls": 0, "new_fits": 0, "scientific_validation": False}
        require(len(canonical(tool).encode("utf-8")) <= relevance.MAX_RESULT_BYTES, "RESULT_TOO_LARGE", "Final result exceeds limit.")
        validate_final_result(tool)
        return tool

    def next_decision(self, result):
        validate_final_result(result)
        return {"policy_ref": {"id": FINAL_TOOL_ID, "version": ADAPTER_VERSION}, "project_status": "waiting",
                "next_action": {"kind": "review_saved_evidence", "execution_status": "not_executed",
                                "required_evidence": ["Review final results and limitations; no automatic scientific promotion."]},
                "reason": "The fixed final evaluation is complete and requires review.",
                "source_snapshot_sha256": result["result"]["source_snapshot_sha256"], "evidence_refs": [],
                "scientific_validation": False, "new_fits": 0, "model_calls": 0}


FINAL = FinalRetrievalEvaluation()
