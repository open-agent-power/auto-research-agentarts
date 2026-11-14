"""Explicit historical cases from completed staged retrieval, never final raw data.

Capture verifies original source and three native actions, without dispatch or
reading the private final packet. Offline final aggregate provenance requires
reopening the original artifact: self-contained hashes are not signatures.
"""
import copy
import hashlib
import math
from pathlib import Path
import re

from . import staged_relevance_adapter as staged, retrieval_holdout as holdout, research_recipe
from . import source_evidence_adapter as source_reader
from .contracts import ResearchError, canonical, fingerprint, identifier
from .research_memory import ResearchMemory, observation_id, validate_scope
from .research_project import ResearchProject, code_identity as runtime_code_identity
from . import project_selection

SCHEMA = "staged-retrieval-experience-bundle-v1"
PROTOCOL = "staged-retrieval-saved-binding-v1"
MAX_BUNDLE_BYTES = 4 * 1024 * 1024
NOTICE = ("Historical analogy only. Final aggregate was checked against the original at capture; "
          "offline_final_binding_unverifiable_without_origin. Self-contained hashes are not signatures. "
          "No final query IDs, final per-query rows, private final bytes, or source asset bytes are included. "
          "Public data and same-user procedural separation do not establish blindness or scientific validity.")
EVALUATION = "staged-relevance-development-v1"


def _require(value, message, code="INVALID_STAGED_EXPERIENCE"):
    if not value:
        raise ResearchError(code, message)


def _hash(value):
    return type(value) is str and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def _read(project, action):
    from .research_project import safe_path
    path = safe_path(project.root / "artifacts" / (action["id"] + ".json"))
    raw = source_reader._read_file(path, 5 * 1024 * 1024)
    env = staged._parse(raw)
    _require(type(env) is dict and set(env) == {"action_id", "code_identity", "request_sha256", "sha256", "source_snapshot_sha256", "tool_result"}
             and env["sha256"] == fingerprint({k: v for k, v in env.items() if k != "sha256"}) == action["result_sha256"]
             and env["action_id"] == action["id"] and env["request_sha256"] == action["request_sha256"]
             and env["code_identity"] == action["code_identity"]
             and env["source_snapshot_sha256"] == action["source_snapshot_sha256"], "Original action envelope changed.", "EVIDENCE_CHANGED")
    return env, hashlib.sha256(raw).hexdigest()


def _action(action, state, method, primary=None):
    identifier(action["id"], "action_id")
    identifier(action["request_id"], "request_id")
    _require(action["status"] == "completed" and action["failure"] is None and action["command"] == method
             and action["project_id"] == state["id"] and action["run_id"] == state["run_id"]
             and action["source_snapshot_sha256"] == state["source_snapshot_sha256"]
             and action["code_identity"] == state["code_identity"] and action["dimension"] is None
             and action["artifact"] == "artifacts/" + action["id"] + ".json"
             and all(_hash(action[k]) for k in ("request_sha256", "result_sha256", "code_identity")),
             "Original action identity differs.", "EVIDENCE_CHANGED")
    request = {"project_id": state["id"], "command": method, "dimension": None,
               "source_snapshot_sha256": state["source_snapshot_sha256"]}
    from . import method_registry as registry
    evaluation = registry.evaluation_ref(method)
    params = {} if primary is None else {"based_on_action_id": primary["id"], "based_on_result_sha256": primary["result_sha256"]}
    if primary is not None:
        request.update(parameters=params, evaluation_ref=evaluation)
        _require(action["parameters"] == params and action["evaluation_ref"] == evaluation,
                 "Followup does not bind the original primary.", "EVIDENCE_CHANGED")
    instance = {"definition_ref": {"id": method, "version": "1"},
                "input_bindings": {"source_snapshot_sha256": state["source_snapshot_sha256"], **params},
                "parameters": params, "evaluation_ref": evaluation, "scope": state["source_scope"]}
    _require(action["request_sha256"] == fingerprint(request)
             and action["id"] == "action-" + fingerprint({"request_id": action["request_id"], **request})[:32]
             and action["method_instance"] == instance, "Action request or producer instance differs.", "EVIDENCE_CHANGED")


def _verify_action_rows(project, actions):
    """Bind status projections to original action-table record and fingerprint columns."""
    with project._connect(readonly=True) as con:
        con.execute("BEGIN")
        for action in actions:
            rows = con.execute("SELECT request_id, fingerprint, record FROM actions WHERE request_id=?",
                               (action["request_id"],)).fetchall()
            _require(len(rows) == 1 and rows[0]["request_id"] == action["request_id"]
                     and rows[0]["fingerprint"] == action["request_sha256"]
                     and staged._parse(rows[0]["record"].encode("utf-8")) == action,
                     "Original action database row or fingerprint differs from the project snapshot.", "EVIDENCE_CHANGED")


def _project_action(action):
    """Keep only typed action identity fields, never arbitrary action observations."""
    fields = {"artifact", "code_identity", "command", "dimension", "failure", "id", "method_instance", "project_id", "request_id", "request_sha256", "result_sha256", "run_id", "source_snapshot_sha256", "status"}
    if action["command"] != staged.TOOL_ID:
        fields |= {"parameters", "evaluation_ref"}
    return {key: copy.deepcopy(action[key]) for key in fields}


def _parent(state, action, registration, freeze):
    matches = [p for p in state.get("controller_requests", []) if p.get("child_request_id") == action["request_id"]]
    _require(len(matches) == 1, "Exactly one original controller parent is required.", "EVIDENCE_CHANGED")
    parent = matches[0]
    expected_id = "controller-child-" + fingerprint({"project_id": state["id"], "request_id": parent["request_id"]})[:32]
    child = {k: copy.deepcopy(action[k]) for k in ("id", "request_id", "command", "status", "artifact", "result_sha256", "failure") if k in action}
    _require(parent["status"] == "completed" and parent["project_id"] == state["id"]
             and parent["source_snapshot_sha256"] == state["source_snapshot_sha256"]
             and parent["code_identity"] == state["code_identity"] and parent["child_request_id"] == expected_id
             and parent["request_sha256"] == fingerprint(parent["request"])
             and parent["decision_sha256"] == fingerprint(parent["decision"])
             and parent["request"].get("command") == "controller.advance_selection"
             and parent["request"].get("project_id") == state["id"]
             and parent["request"].get("expected_state_version") == parent["state_version_before"]
             and type(parent.get("result")) is dict and parent["result"].get("child") == child
             and parent["result"].get("reused") is False,
             "Original controller parent/child binding changed.", "EVIDENCE_CHANGED")
    ctx = parent["selection_context"]
    selected = project_selection.validate_proposal(ctx, parent["request"]["proposal"])["candidate"]
    _require(selected is not None and selected["method_id"] == action["command"]
             and selected["parameters"] == action["method_instance"]["parameters"]
             and selected["evaluation_ref"] == action["method_instance"]["evaluation_ref"]
             and ctx["project_id"] == state["id"] and ctx["run_id"] == state["run_id"]
             and ctx["state_version"] == parent["state_version_before"]
             and ctx["snapshot_ref"] == parent["snapshot_ref_before"]
             and ctx["domain_scope"] == state["source_scope"]
             and fingerprint(ctx["research_plan"]) == registration["plan_sha256"]
             and ctx["source_snapshot_sha256"] == state["source_snapshot_sha256"]
             and ctx["project_code_identity"] == state["code_identity"]
             and ctx["controller_code_identity"] == parent["controller_code_identity"]
             and parent["decision"]["next_action"].get("method_id") == action["command"]
             and parent["decision"]["next_action"].get("parameters", {}) == selected["parameters"]
             and parent["decision"].get("selection_ref", {}).get("candidate_id") == selected["id"]
             and parent["decision"].get("selection_ref", {}).get("context_sha256") == ctx["context_sha256"],
             "Original selection and action differ.", "EVIDENCE_CHANGED")
    expected_freeze = None
    if action["command"] == holdout.FINAL_TOOL_ID:
        expected_freeze = {key: copy.deepcopy(freeze[key]) for key in
                           ("selected_method", "validation_delta_recall20", "primary_action_id", "primary_result_sha256")}
        expected_freeze["freeze_sha256"] = freeze["record_sha256"]
    expected_evaluation = {"schema_version": "staged-evaluation-context-v1", "holdout_sha256": registration["sha256"],
                           "query_count": registration["query_count"], "policy": registration["policy"],
                           "freeze": expected_freeze, "final": None, "scientific_validation": False,
                           "limitations": holdout.PUBLIC_LIMITATIONS}
    _require(ctx.get("staged_evaluation") == expected_evaluation,
             "Saved controller context differs from preregistered holdout or frozen strategy.", "EVIDENCE_CHANGED")
    return {"request_id": parent["request_id"], "request_sha256": parent["request_sha256"],
            "decision_sha256": parent["decision_sha256"], "context_sha256": ctx["context_sha256"],
            "controller_code_identity": parent["controller_code_identity"], "child_request_id": action["request_id"],
            "state_version_before": parent["state_version_before"], "state_version_after": parent["state_version_after"]}


def _dev_source(project, before):
    raw = source_reader._read_file(project.root / "source.json", staged.LIMITS["packet_bytes"])
    source_sha = hashlib.sha256(raw).hexdigest()
    _require(source_sha == before["registration"]["source_sha256"] and before["registration"]["method_id"] == staged.TOOL_ID,
             "Original staged source identity changed.", "EVIDENCE_CHANGED")
    packet = staged._parse(raw)
    spec, docs, queries, qrels, doc_lines, query_lines = staged._checked(packet)
    _require(packet["snapshot_sha256"] == before["source_snapshot_sha256"] and packet["scope"] == before["source_scope"],
             "Original source snapshot or scope changed.", "EVIDENCE_CHANGED")
    refs = {"task_kind": packet["task_kind"], "stage": packet["stage"], "spec": spec,
            "spec_source": packet["spec_source"],
            "assets": {k: {f: v[f] for f in ("sha256", "bytes")} for k, v in packet["assets"].items()},
            "source_inclusion": "asset_bytes_excluded_hash_references_only"}
    return source_sha, refs, (docs, queries, qrels, doc_lines, query_lines)


def _check_audit(tool, primary, params):
    staged.AUDIT.next_decision(tool)
    saved = staged._saved(primary)
    summary, deltas, adverse = staged._paired(saved["per_query_metrics"])
    audit = tool["result"]
    _require(audit["stage"] == "development" and audit["predecessor"] == params
             and audit["source_snapshot_sha256"] == saved["source_snapshot_sha256"] and audit["scope"] == saved["scope"]
             and audit["rankings_sha256"] == saved["rankings_before_scoring_sha256"]
             and audit["summary"] == summary and audit["per_query_deltas"] == deltas and audit["adverse_queries"] == adverse
             and audit["usage"] == {"query_pairs": len(deltas), "index_builds": 0, "ranking_calls": 0, "scoring_calls": 0,
                                     "native_fits": 0, "model_calls": 0},
             "Saved audit differs from the original primary.", "EVIDENCE_CHANGED")
    expected_result = {"stage": "development", "scope": copy.deepcopy(saved["scope"]),
        "source_snapshot_sha256": saved["source_snapshot_sha256"], "predecessor": copy.deepcopy(params),
        "rankings_sha256": saved["rankings_before_scoring_sha256"], "summary": summary,
        "adverse_queries": adverse, "per_query_deltas": deltas,
        "usage": {"query_pairs": len(deltas), "index_builds": 0, "ranking_calls": 0, "scoring_calls": 0, "native_fits": 0, "model_calls": 0},
        "limitations": copy.deepcopy(staged.NOTES) + ["Saved metrics are inspected without reranking or rescoring labels."]}
    refs = copy.deepcopy(primary["evidence_refs"])
    refs.append({"source_snapshot_sha256": saved["source_snapshot_sha256"], "producer": copy.deepcopy(params),
                 "locator": {"kind": "saved_development_action", **params}})
    expected_tool = staged._tool(staged.AUDIT_TOOL_ID, expected_result, "saved_staged_relevance_audit",
                                 {"query_pairs": len(deltas), "adverse_queries": len(adverse)}, refs)
    _require(tool == expected_tool, "Saved audit envelope has unexpected fields or observations.", "EVIDENCE_CHANGED")
    return summary, deltas, adverse


def _final_projection(tool, metadata, frozen, params, source_snapshot):
    result = holdout.validate_final_result(tool)
    _require(result["predecessor"] == params and result["source_snapshot_sha256"] == source_snapshot
             and result["holdout_sha256"] == metadata["sha256"] and result["freeze_sha256"] == frozen["record_sha256"]
             and result["scope"]["corpus_sha256"] == metadata["corpus_sha256"]
             and result["scope"]["query_count"] == metadata["query_count"]
             and result["selected_method"] == frozen["selected_method"],
             "Final result does not match its source, freeze or predecessor.", "EVIDENCE_CHANGED")
    return {"selected_method": result["selected_method"], "baseline_method": result["baseline_method"],
            "comparison_status": ("selected_equals_baseline_single_computation" if result["selected_method"] == "bm25" else "distinct_selected_and_baseline"),
            "query_count": result["scope"]["query_count"], "summary": copy.deepcopy(result["summary"]),
            "usage": copy.deepcopy(result["usage"]), "limitations": copy.deepcopy(result["limitations"]),
            "verification": "source_verified_at_capture; offline_final_binding_unverifiable_without_origin"}


def derive_staged_observation(workspace, primary_action_id):
    """Capture only completed original native actions; perform no research dispatch."""
    try:
        identifier(primary_action_id, "primary_action_id")
        project = ResearchProject(workspace)
        before = project.status()
        initial_code = runtime_code_identity()
        implementation = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
        _require(not any(a["status"] in ("pending", "running", "unknown") for a in before["actions"] + before["evidence_actions"])
                 and not any(p["status"] in ("prepared", "running", "unknown") for p in before.get("controller_requests", [])),
                 "Resolve all pending source requests first.", "EXECUTION_UNKNOWN")
        metadata = holdout.validate_metadata(before)
        _require(metadata is not None and metadata["frozen_evaluation_strategy"] is not None,
                 "A preregistered holdout and frozen strategy are required.", "ARTIFACT_NOT_AVAILABLE")
        reg, freeze = metadata["private_evaluation"], metadata["frozen_evaluation_strategy"]
        source_sha, source, parsed = _dev_source(project, before)
        actions = []
        for method in (staged.TOOL_ID, staged.AUDIT_TOOL_ID, holdout.FINAL_TOOL_ID):
            matching = [x for x in before["actions"] if x["command"] == method]
            _require(len(matching) == 1 and matching[0]["status"] == "completed", "One completed action per stage is required.", "ARTIFACT_NOT_AVAILABLE")
            actions.append(matching[0])
        primary, audit, final = actions
        _verify_action_rows(project, actions)
        _require(primary["id"] == primary_action_id and freeze["primary_action_id"] == primary_action_id
                 and freeze["primary_result_sha256"] == primary["result_sha256"], "Frozen primary identity differs.", "EVIDENCE_CHANGED")
        for item, method in zip(actions, (staged.TOOL_ID, staged.AUDIT_TOOL_ID, holdout.FINAL_TOOL_ID)):
            _action(item, before, method, None if item is primary else primary)
        parents = [_parent(before, item, reg, freeze) for item in actions]
        _require(reg["state_version_before"] < parents[0]["state_version_before"]
                 and parents[0]["state_version_after"] <= parents[1]["state_version_before"]
                 and parents[1]["state_version_after"] <= freeze["request"]["expected_state_version"]
                 and freeze["request"]["expected_state_version"] < parents[2]["state_version_before"],
                 "Original staged registration and action order differs.", "EVIDENCE_CHANGED")
        envelopes, raw_hashes = zip(*[_read(project, item) for item in actions])
        first, second, third = [env["tool_result"] for env in envelopes]
        for action, tool in zip(actions, (first, second, third)):
            observations = [dict(item, id=action["id"] + ":observation:" + str(i), action_id=action["id"])
                            for i, item in enumerate(tool["observations"])]
            _require(action["observations"] == observations, "Action observations differ from the original result.", "EVIDENCE_CHANGED")
        saved = staged._saved(first)
        _require(saved["scope"] == before["source_scope"] and saved["source_snapshot_sha256"] == before["source_snapshot_sha256"]
                 and saved["comparison"] == source["spec"]["comparison"], "Saved primary differs from the source.", "EVIDENCE_CHANGED")
        docs, queries, qrels, doc_lines, query_lines = parsed
        for row in saved["rankings"]:
            _require(row["query_id"] in queries and row["query_line"] == query_lines[row["query_id"]]
                     and all(doc in docs and doc_lines[doc] == line for doc, line in zip(row["ranking"], row["ranked_doc_lines"])),
                     "Saved development ranking coordinates differ.", "EVIDENCE_CHANGED")
        for row in saved["per_query_metrics"]:
            _require(row["qrel_locator"]["document_grades"] == qrels[row["query_id"]],
                     "Saved development labels differ from the source.", "EVIDENCE_CHANGED")
        params = {"based_on_action_id": primary["id"], "based_on_result_sha256": primary["result_sha256"]}
        paired, _, adverse = _check_audit(second, first, params)
        _, expected = holdout._check_frozen(project, before, freeze)
        _require(canonical(expected) == canonical(first), "Frozen result differs from original primary.", "EVIDENCE_CHANGED")
        final_projection = _final_projection(third, reg, freeze, params, before["source_snapshot_sha256"])
        origin = {"project_id": before["id"], "run_id": before["run_id"], "state_version": before["state_version"],
                  "snapshot_ref": before["snapshot_ref"], "source_snapshot_sha256": before["source_snapshot_sha256"],
                  "source_file_sha256": source_sha, "registered_project_code_identity": before["code_identity"],
                  "producer_code_identity": primary["code_identity"], "capture_runtime_code_identity": initial_code,
                  "capture_implementation_sha256": implementation}
        provenance = {"action_id": primary["id"], "source_record_sha256": fingerprint(before), "origin": origin,
                      "source": source, "actions": {"primary": _project_action(primary), "audit": _project_action(audit), "final": _project_action(final)},
                      "artifacts": {"primary": envelopes[0], "audit": envelopes[1]},
                      "artifact_file_sha256": {"primary": raw_hashes[0], "audit": raw_hashes[1], "final": raw_hashes[2]},
                      "parent_bindings": {k: p for k, p in zip(("primary", "audit", "final"), parents)},
                      "holdout_registration": reg, "freeze": freeze,
                      "final_ref": {"action_id": final["id"], "request_id": final["request_id"], "result_sha256": final["result_sha256"]}}
        scope = {"source_manifest_sha256": before["source_snapshot_sha256"],
                 "inputs_sha256": fingerprint({"primary": primary["result_sha256"], "audit": audit["result_sha256"],
                                                "final": final["result_sha256"], "source": fingerprint(source),
                                                "freeze": freeze["record_sha256"]}),
                 "analysis_code_sha256": fingerprint({"implementation_sha256": implementation, "runtime_code_identity": initial_code}),
                 "protocol": PROTOCOL}
        payload = {"method_id": staged.TOOL_ID, "evaluation_ref": EVALUATION,
                   "source_scope": before["source_scope"], "comparison": saved["comparison"],
                   "paired_summary": paired, "adverse_queries": len(adverse),
                   "final": final_projection, "origin_limitations": saved["limitations"],
                   "verification": "saved_only_binding_structure_and_arithmetic"}
        entry = {"schema_version": "conditional-research-memory-v1", "kind": "diagnostic_observation", "scope": scope,
                 "review_status": "derived_not_scientifically_reviewed", "numerical_recomputation": False,
                 "payload": payload, "provenance": provenance}
        entry["id"] = observation_id(entry)
        _validate_record(entry)
        _require(hashlib.sha256(source_reader._read_file(project.root / "source.json", staged.LIMITS["packet_bytes"])).hexdigest() == source_sha
                 and all(_read(project, item)[1] == raw_hash for item, raw_hash in zip(actions, raw_hashes)),
                 "Source or action artifact changed while capturing.", "STALE_STATE")
        _verify_action_rows(project, actions)
        _require(project.status() == before and runtime_code_identity() == initial_code
                 and hashlib.sha256(Path(__file__).read_bytes()).hexdigest() == implementation,
                 "Project or capture implementation changed.", "STALE_STATE")
        return {"scope": scope, "entries": [entry], "validation": {"protocol": PROTOCOL,
                "source_packet_checked_at_capture": True, "final_aggregate_verified_at_capture": True,
                "offline_final_binding_unverifiable_without_origin": True, "scientific_validation": False}}
    except ResearchError:
        raise
    except (KeyError, TypeError, ValueError, AttributeError, IndexError, UnicodeError, OverflowError, RecursionError, OSError):
        raise ResearchError("EVIDENCE_CHANGED", "Staged project or saved evidence is malformed.") from None


def _check_final_projection(value, frozen, reg):
    _require(type(value) is dict and set(value) == {"selected_method", "baseline_method", "comparison_status", "query_count", "summary", "usage", "limitations", "verification"}
             and value["selected_method"] == frozen["selected_method"] and value["baseline_method"] == "bm25"
             and value["comparison_status"] == ("selected_equals_baseline_single_computation" if value["selected_method"] == "bm25" else "distinct_selected_and_baseline")
             and type(value["query_count"]) is int and value["query_count"] == reg["query_count"]
             and 1 <= value["query_count"] <= staged.LIMITS["max_queries"]
             and value["verification"] == "source_verified_at_capture; offline_final_binding_unverifiable_without_origin",
             "Invalid final aggregate projection.")
    n = value["query_count"]
    calls = n * (1 if value["selected_method"] == "bm25" else 2)
    _require(value["usage"] == {"index_builds": 1, "ranking_calls": calls, "scoring_calls": calls, "native_fits": 0, "model_calls": 0}
             and all(type(x) is int for x in value["usage"].values())
             and value["limitations"] == ["Procedural same-user separation only; not OS-isolated or independently blind.",
                                           "Final binary relevance metrics do not establish scientific validity."],
             "Final count or limitation projection differs.")
    sums = value["summary"]
    from . import retrieval_lexical
    _require(type(sums) is dict and set(sums) == {"baseline", "selected", "delta"}, "Invalid final summary.")
    for kind in ("baseline", "selected", "delta"):
        _require(type(sums[kind]) is dict and set(sums[kind]) == set(retrieval_lexical.METRICS)
                 and all(type(x) in (int, float) and math.isfinite(x) and (-1 if kind == "delta" else 0) <= x <= 1
                         for x in sums[kind].values()), "Invalid final metric values.")
    _require(all(abs(sums["delta"][k] - (sums["selected"][k] - sums["baseline"][k])) <= 1e-12
                 for k in retrieval_lexical.METRICS), "Final aggregate deltas differ.")
    if value["selected_method"] == "bm25":
        _require(sums["selected"] == sums["baseline"] and all(v == 0 for v in sums["delta"].values()),
                 "Single-arm baseline cannot imply a separate final comparison.")


def _validate_record(record):
    import base64
    _require(type(record) is dict and set(record) == {"schema_version", "id", "kind", "scope", "review_status", "numerical_recomputation", "payload", "provenance"}
             and record["schema_version"] == "conditional-research-memory-v1" and record["kind"] == "diagnostic_observation"
             and record["review_status"] == "derived_not_scientifically_reviewed" and record["numerical_recomputation"] is False,
             "Invalid staged memory record.")
    scope = validate_scope(record["scope"])
    _require(scope["protocol"] == PROTOCOL and observation_id(record) == record["id"], "Staged record identity differs.")
    p = record["provenance"]
    _require(type(p) is dict and set(p) == {"action_id", "source_record_sha256", "origin", "source", "actions", "artifacts", "artifact_file_sha256", "parent_bindings", "holdout_registration", "freeze", "final_ref"}
             and _hash(p["source_record_sha256"]), "Invalid staged provenance.")
    origin, source, payload = p["origin"], p["source"], record["payload"]
    _require(type(origin) is dict and set(origin) == {"project_id", "run_id", "state_version", "snapshot_ref", "source_snapshot_sha256", "source_file_sha256", "registered_project_code_identity", "producer_code_identity", "capture_runtime_code_identity", "capture_implementation_sha256"}
             and type(origin["state_version"]) is int and origin["state_version"] > 0
             and all(_hash(origin[k]) for k in ("snapshot_ref", "source_snapshot_sha256", "source_file_sha256", "registered_project_code_identity", "producer_code_identity", "capture_runtime_code_identity", "capture_implementation_sha256")),
             "Invalid staged origin.")
    identifier(origin["project_id"], "project_id")
    identifier(origin["run_id"], "run_id")
    _require(type(source) is dict and set(source) == {"task_kind", "stage", "spec", "spec_source", "assets", "source_inclusion"}
             and source["task_kind"] == "staged_relevance_development" and source["stage"] == "development"
             and source["source_inclusion"] == "asset_bytes_excluded_hash_references_only"
             and type(source["assets"]) is dict and set(source["assets"]) == set(staged.FILES), "Invalid source references.")
    spec_asset = source["spec_source"]
    _require(type(spec_asset) is dict and set(spec_asset) == {"file_name", "sha256", "bytes", "bytes_base64"}
             and spec_asset["file_name"] == "spec.json" and _hash(spec_asset["sha256"]) and type(spec_asset["bytes"]) is int,
             "Original development specification bytes required.")
    try:
        raw_spec = base64.b64decode(spec_asset["bytes_base64"], validate=True)
    except (ValueError, TypeError):
        raise ResearchError("INVALID_STAGED_EXPERIENCE", "Malformed development specification encoding.") from None
    spec = staged._parse(raw_spec)
    staged._spec(spec)
    _require(0 < len(raw_spec) <= staged.LIMITS["spec_bytes"] and len(raw_spec) == spec_asset["bytes"]
             and hashlib.sha256(raw_spec).hexdigest() == spec_asset["sha256"]
             and base64.b64encode(raw_spec).decode("ascii") == spec_asset["bytes_base64"] and spec == source["spec"]
             and all(type(asset) is dict and set(asset) == {"sha256", "bytes"} and _hash(asset["sha256"])
                     and type(asset["bytes"]) is int and 0 < asset["bytes"] <= staged._limit(role)
                     for role, asset in source["assets"].items()), "Development source references differ.")
    _require(type(payload) is dict and set(payload) == {"method_id", "evaluation_ref", "source_scope", "comparison", "paired_summary", "adverse_queries", "final", "origin_limitations", "verification"}
             and payload["method_id"] == staged.TOOL_ID and payload["evaluation_ref"] == EVALUATION
             and type(payload["source_scope"]) is dict and payload["source_scope"].get("domain") == "retrieval"
             and payload["source_scope"].get("contract") == staged.CONTRACT
             and payload["source_scope"].get("input_identities") == source["assets"]
             and payload["comparison"] == spec["comparison"] and payload["verification"] == "saved_only_binding_structure_and_arithmetic",
             "Invalid staged observation payload.")
    fake_state = {"id": origin["project_id"], "run_id": origin["run_id"], "source_snapshot_sha256": origin["source_snapshot_sha256"],
                  "source_scope": payload["source_scope"], "code_identity": origin["registered_project_code_identity"]}
    actions, artifacts = p["actions"], p["artifacts"]
    _require(type(actions) is dict and set(actions) == {"primary", "audit", "final"}
             and type(artifacts) is dict and set(artifacts) == {"primary", "audit"}, "Invalid captured stage evidence.")
    primary, audit, final = actions["primary"], actions["audit"], actions["final"]
    for item, method in ((primary, staged.TOOL_ID), (audit, staged.AUDIT_TOOL_ID), (final, holdout.FINAL_TOOL_ID)):
        _require(type(item) is dict and item == _project_action(item), "Unexpected action projection fields.")
        _action(item, fake_state, method, None if item is primary else primary)
    _require(p["action_id"] == primary["id"] and origin["producer_code_identity"] == primary["code_identity"], "Staged primary identity differs.")
    for label in ("primary", "audit"):
        env, action = artifacts[label], actions[label]
        _require(type(env) is dict and set(env) == {"action_id", "code_identity", "request_sha256", "sha256", "source_snapshot_sha256", "tool_result"}
                 and env["sha256"] == fingerprint({k: v for k, v in env.items() if k != "sha256"}) == action["result_sha256"]
                 and env["action_id"] == action["id"] and env["request_sha256"] == action["request_sha256"]
                 and env["code_identity"] == action["code_identity"] and env["source_snapshot_sha256"] == origin["source_snapshot_sha256"],
                 "Saved stage envelope differs.")
    saved = staged._saved(artifacts["primary"]["tool_result"])
    _require(saved["scope"] == payload["source_scope"] and saved["comparison"] == payload["comparison"]
             and saved["source_snapshot_sha256"] == origin["source_snapshot_sha256"]
             and {(row["split"], row["query_id"]) for row in saved["per_query_metrics"]}
                 == {(split, qid) for split, ids in spec["query_splits"].items() for qid in ids}
             and all(ref["url"] == spec["source_url"] and ref["license_note"] == spec["license_notes"]["corpus" if ref["locator"]["role"] == "corpus" else "queries_and_qrels"]
                     for ref in artifacts["primary"]["tool_result"]["evidence_refs"]), "Saved primary source differs.")
    params = {"based_on_action_id": primary["id"], "based_on_result_sha256": primary["result_sha256"]}
    paired, _, adverse = _check_audit(artifacts["audit"]["tool_result"], artifacts["primary"]["tool_result"], params)
    _require(paired == payload["paired_summary"] and type(payload["adverse_queries"]) is int
             and payload["adverse_queries"] == len(adverse) and payload["origin_limitations"] == saved["limitations"],
             "Saved stage summaries differ.")
    reg, freeze = p["holdout_registration"], p["freeze"]
    reg_fields = {"schema_version", "request_id", "request_sha256", "request", "project_id", "run_id", "state_version_before", "sha256", "bytes", "query_count", "corpus_sha256", "source_sha256", "source_snapshot_sha256", "plan_sha256", "plan_version", "project_code_identity", "policy", "scientific_validation", "record_sha256"}
    freeze_fields = {"schema_version", "request_id", "request", "request_sha256", "project_id", "run_id", "holdout_record_sha256", "source_snapshot_sha256", "plan_sha256", "project_code_identity", "primary_action_id", "primary_result_sha256", "validation_delta_recall20", "policy", "selected_method", "scientific_validation", "record_sha256"}
    _require(type(reg) is dict and set(reg) == reg_fields and reg["schema_version"] == "retrieval-holdout-registration-v1"
             and type(freeze) is dict and set(freeze) == freeze_fields and freeze["schema_version"] == "retrieval-holdout-freeze-v1"
             and all(_hash(reg[k]) for k in ("request_sha256", "sha256", "corpus_sha256", "source_sha256", "source_snapshot_sha256", "plan_sha256", "project_code_identity", "record_sha256"))
             and all(_hash(freeze[k]) for k in ("request_sha256", "holdout_record_sha256", "source_snapshot_sha256", "plan_sha256", "project_code_identity", "primary_result_sha256", "record_sha256"))
             and type(reg["state_version_before"]) is int and 0 <= reg["state_version_before"] < origin["state_version"]
             and type(reg["bytes"]) is int and 0 < reg["bytes"] <= holdout.MAX_HOLDOUT_BYTES
             and type(reg["query_count"]) is int and 1 <= reg["query_count"] <= staged.LIMITS["max_queries"]
             and type(reg["plan_version"]) is int and 1 <= reg["plan_version"] <= origin["state_version"]
             and reg["policy"] == freeze["policy"] == holdout.POLICY
             and reg["scientific_validation"] is False and freeze["scientific_validation"] is False,
             "Invalid holdout or frozen metadata schema.")
    for item in (reg, freeze):
        identifier(item["request_id"])
    identifier(freeze["primary_action_id"], "primary_action_id")
    _require(type(reg["request"]) is dict and reg["request"] == {"request_id": reg["request_id"], "expected_state_version": reg["state_version_before"], "holdout_sha256": reg["sha256"], "holdout_bytes": reg["bytes"]}
             and type(reg["request"]["expected_state_version"]) is int and type(reg["request"]["holdout_bytes"]) is int
             and reg["request_sha256"] == fingerprint(reg["request"])
             and type(freeze["request"]) is dict and set(freeze["request"]) == {"request_id", "expected_state_version", "primary_action_id"}
             and freeze["request"]["request_id"] == freeze["request_id"] and freeze["request"]["primary_action_id"] == freeze["primary_action_id"]
             and type(freeze["request"]["expected_state_version"]) is int and reg["state_version_before"] < freeze["request"]["expected_state_version"] < origin["state_version"]
             and freeze["request_sha256"] == fingerprint(freeze["request"]) and reg["request_id"] != freeze["request_id"],
             "Holdout/freeze request identity differs.")
    _require(type(reg) is dict and type(freeze) is dict
             and reg.get("record_sha256") == fingerprint({k: v for k, v in reg.items() if k != "record_sha256"})
             and freeze.get("record_sha256") == fingerprint({k: v for k, v in freeze.items() if k != "record_sha256"})
             and reg.get("project_id") == origin["project_id"] and reg.get("run_id") == origin["run_id"]
             and reg.get("source_snapshot_sha256") == origin["source_snapshot_sha256"]
             and reg.get("source_sha256") == origin["source_file_sha256"]
             and reg.get("project_code_identity") == origin["registered_project_code_identity"]
             and reg.get("corpus_sha256") == source["assets"]["corpus"]["sha256"]
             and freeze.get("holdout_record_sha256") == reg["record_sha256"] and freeze.get("project_id") == origin["project_id"]
             and freeze.get("run_id") == origin["run_id"] and freeze.get("source_snapshot_sha256") == origin["source_snapshot_sha256"]
             and freeze.get("project_code_identity") == origin["registered_project_code_identity"]
             and freeze.get("plan_sha256") == reg.get("plan_sha256") and freeze.get("policy") == holdout.POLICY
             and freeze.get("primary_action_id") == primary["id"] and freeze.get("primary_result_sha256") == primary["result_sha256"],
             "Holdout or frozen registration binding differs.")
    delta = paired["splits"]["validation"]["paired_candidate_minus_baseline"]["recall@20"]["mean"]
    _require(type(delta) in (int, float) and math.isfinite(delta)
             and freeze["validation_delta_recall20"] == delta
             and freeze["selected_method"] == ("tfidf_cosine" if delta > 0 else "bm25"), "Frozen validation selection differs.")
    _check_final_projection(payload["final"], freeze, reg)
    final_ref = p["final_ref"]
    _require(final_ref == {"action_id": final["id"], "request_id": final["request_id"], "result_sha256": final["result_sha256"]}, "Final action reference differs.")
    file_hashes = p["artifact_file_sha256"]
    _require(type(file_hashes) is dict and set(file_hashes) == {"primary", "audit", "final"} and all(_hash(v) for v in file_hashes.values())
             and all(file_hashes[name] == hashlib.sha256(canonical(artifacts[name]).encode("utf-8")).hexdigest() for name in ("primary", "audit")),
             "Invalid artifact-byte references.")
    parents = p["parent_bindings"]
    _require(type(parents) is dict and set(parents) == {"primary", "audit", "final"}, "Three original parent references required.")
    parent_fields = {"request_id", "request_sha256", "decision_sha256", "context_sha256", "controller_code_identity", "child_request_id", "state_version_before", "state_version_after"}
    for name in ("primary", "audit", "final"):
        parent = parents[name]
        _require(type(parent) is dict and set(parent) == parent_fields and all(_hash(parent[k]) for k in ("request_sha256", "decision_sha256", "context_sha256", "controller_code_identity"))
                 and type(parent["state_version_before"]) is int and type(parent["state_version_after"]) is int
                 and 0 <= parent["state_version_before"] < parent["state_version_after"] <= origin["state_version"]
                 and parent["child_request_id"] == actions[name]["request_id"]
                 and parent["child_request_id"] == "controller-child-" + fingerprint({"project_id": origin["project_id"], "request_id": parent["request_id"]})[:32],
                 "Parent identity or ordering differs.")
        identifier(parent["request_id"])
    _require(reg["state_version_before"] < parents["primary"]["state_version_before"]
             and parents["primary"]["state_version_after"] <= parents["audit"]["state_version_before"]
             and parents["audit"]["state_version_after"] <= freeze["request"]["expected_state_version"]
             and freeze["request"]["expected_state_version"] < parents["final"]["state_version_before"], "Stage order differs.")
    _require(scope["source_manifest_sha256"] == origin["source_snapshot_sha256"]
             and scope["inputs_sha256"] == fingerprint({"primary": primary["result_sha256"], "audit": audit["result_sha256"],
                 "final": final["result_sha256"], "source": fingerprint(source), "freeze": freeze["record_sha256"]})
             and scope["analysis_code_sha256"] == fingerprint({"implementation_sha256": origin["capture_implementation_sha256"],
                                                                 "runtime_code_identity": origin["capture_runtime_code_identity"]}),
             "Staged record scope differs.")
    return record


def validate_bundle(bundle):
    try:
        _require(type(bundle) is dict and set(bundle) == {"schema_version", "id", "version", "record", "method_card", "limitations", "source_inclusion_status", "scientific_validation"}
                 and bundle["schema_version"] == SCHEMA and bundle["source_inclusion_status"] == "active_at_export"
                 and bundle["scientific_validation"] is False and type(bundle["version"]) is int and 1 <= bundle["version"] <= 2**31 - 1,
                 "Invalid staged case bundle.")
        identifier(bundle["id"], "case_id")
        _require(len(canonical(bundle).encode("utf-8")) <= MAX_BUNDLE_BYTES, "Staged case bundle exceeds 4 MiB.", "BUNDLE_TOO_LARGE")
        record = _validate_record(bundle["record"])
        card = research_recipe.validate_method_card(bundle["method_card"])
        _require(card["scope_match"] == {"domain": "retrieval", "contract": staged.CONTRACT}
                 and card["method_refs"] == [{"method_id": staged.TOOL_ID, "evaluation_ref": EVALUATION}], "Method card must match the staged source.")
        _require(type(bundle["limitations"]) is list and 1 <= len(bundle["limitations"]) <= 8
                 and all(type(v) is str and 0 < len(v.strip()) <= 4000 and "\x00" not in v for v in bundle["limitations"]), "Bounded limitations required.")
        return copy.deepcopy(bundle)
    except ResearchError:
        raise
    except (KeyError, TypeError, ValueError, AttributeError, IndexError, UnicodeError, OverflowError, RecursionError):
        raise ResearchError("INVALID_STAGED_EXPERIENCE", "Malformed staged case bundle.") from None


def parse_bundle(raw):
    return validate_bundle(research_recipe.parse_json(raw, maximum=MAX_BUNDLE_BYTES, code="INVALID_STAGED_EXPERIENCE"))


def summary(bundle):
    bundle = validate_bundle(bundle)
    record = bundle["record"]
    p, payload = record["provenance"], record["payload"]
    compact_scope = {k: copy.deepcopy(v) for k, v in payload["source_scope"].items()
                     if v is None or type(v) in (str, int, float, bool) or k == "input_identities"}
    value = {"case_id": bundle["id"], "case_version": bundle["version"], "entry_id": record["id"],
             "method_card": bundle["method_card"], "origin_evidence": {**p["origin"], "action_id": p["action_id"],
                 "result_sha256": p["actions"]["primary"]["result_sha256"], "binding_scope": record["scope"],
                 "audit_action_id": p["actions"]["audit"]["id"], "audit_result_sha256": p["actions"]["audit"]["result_sha256"],
                 "final_action_id": p["final_ref"]["action_id"], "final_result_sha256": p["final_ref"]["result_sha256"]},
             "source_scope": compact_scope, "observation": {"kind": "saved_staged_retrieval",
                 "method_id": payload["method_id"], "evaluation_ref": payload["evaluation_ref"], "comparison": payload["comparison"],
                 "paired_summary": payload["paired_summary"], "adverse_queries": payload["adverse_queries"],
                 "final": payload["final"], "verification": payload["verification"]},
             "limitations": [*payload["origin_limitations"], *bundle["limitations"], NOTICE],
             "transfer_scope": "analogy_not_current_evidence", "scientific_validation": False}
    _require(len(canonical(value).encode("utf-8")) <= 64 * 1024, "Staged case summary exceeds 64 KiB.", "SUMMARY_TOO_LARGE")
    return value


class StagedExperienceMemory(ResearchMemory):
    def import_project(self, workspace, primary_action_id):
        return self._import_derived(derive_staged_observation(workspace, primary_action_id), verification="binding")

    def export_case(self, scope, entry_id, *, case_id, version, method_card, limitations):
        validate_scope(scope)
        with self._connect() as con:
            row = con.execute("SELECT * FROM entries WHERE id=?", (entry_id,)).fetchone() if con is not None else None
            _require(row is not None, "No staged source entry matches this identity.", "NOT_FOUND")
            record = self._verify(con, row)
            _require(record["scope"] == scope, "Export requires exact source scope.", "INVALID_SCOPE")
            _require(row["status"] == "active", "Retired evidence cannot be exported.", "EXPERIENCE_RETIRED")
            return validate_bundle({"schema_version": SCHEMA, "id": case_id, "version": version, "record": record,
                    "method_card": method_card, "limitations": limitations, "source_inclusion_status": "active_at_export", "scientific_validation": False})
