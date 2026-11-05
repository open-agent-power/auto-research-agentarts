"""Two local method choices over saved facts; no execution, I/O or approval."""

import copy

from .contracts import ResearchError
from . import method_registry as registry


OOF = "p02.saved-oof-residuals"
SOURCE = "p02.source-mapping-check"
DIMENSIONS = ("chemistry", "topography")


def _actions(project):
    return [*project.get("actions", []), *project.get("evidence_actions", [])]


def _evidence(project):
    refs = []
    for action in _actions(project):
        for observation in action.get("observations", []):
            refs.extend(copy.deepcopy(observation.get("evidence_refs", [])))
    return refs


def match_methods(project: dict, need: str = "next_check") -> list[dict]:
    """Describe qualification, missing inputs and completed work without changing it."""
    if type(project) is not dict or type(need) is not str:
        raise ResearchError("INVALID_REQUEST", "Saved project and a named decision need are required.")
    if registry.primary_id(project) != OOF:
        return _domain_methods(project, need)
    actions = _actions(project)
    unresolved = [a.get("id") for a in actions if a.get("status") in ("running", "pending", "unknown")]
    done = [a for a in project.get("actions", [])
            if a.get("command") == OOF and a.get("status") == "completed"]
    remaining = [dimension for dimension in DIMENSIONS if not any(a.get("dimension") == dimension for a in done)]
    completed_receipts = {a.get("receipt_snapshot_sha256") for a in project.get("evidence_actions", [])
                          if a.get("status") == "completed"}
    failed_receipts = {a.get("receipt_snapshot_sha256") for a in project.get("evidence_actions", [])
                       if a.get("status") == "failed"}
    readable = [s for s in project.get("evidence_sources", [])
                if s.get("receipt_snapshot_sha256") and s.get("selection_count", 0) > 0
                and s["receipt_snapshot_sha256"] not in failed_receipts]
    unread = [s for s in readable if s["receipt_snapshot_sha256"] not in completed_receipts]
    proxy_available = bool(project.get("source_snapshot_sha256") and project.get("source_scope"))
    endpoint_need = need in ("alp_endpoint", "alp_effect")
    numerical_condition = "satisfied" if proxy_available else "uncertain"
    if endpoint_need:
        numerical_condition = "not_applicable"
    source_condition = "satisfied" if readable else "uncertain"
    if unresolved:
        numerical_condition = source_condition = "uncertain"
    refs = _evidence(project)
    return [
        {"method_id": OOF, "condition": numerical_condition,
         "reasons": ["Only the registered P02 raw-red proxy and frozen four-policy OOF are supported."
                     if not endpoint_need else "Proxy residuals cannot establish an ALP effect."],
         "missing_information": ([] if proxy_available else ["registered, validated saved-OOF source"]),
         "parameters": {"dimension": remaining[0]} if remaining else {},
         "completed": not remaining, "reusable_action_ids": [a["id"] for a in done],
         "remaining_dimensions": remaining, "unresolved_execution_ids": unresolved,
         "endpoint_eligibility": "uncertain", "evidence_refs": copy.deepcopy(refs)},
        {"method_id": SOURCE, "condition": source_condition,
         "reasons": ["Registered selections are readable; reading does not confirm an endpoint."],
         "missing_information": [] if readable else ["task-bound source bundle with exact selections"],
         "parameters": {"receipt_snapshot_sha256": unread[0]["receipt_snapshot_sha256"]} if unread else {},
         "completed": bool(readable) and not unread,
         "reusable_action_ids": [a["id"] for a in project.get("evidence_actions", [])
                                 if a.get("status") == "completed"],
         "unresolved_execution_ids": unresolved, "endpoint_eligibility": "uncertain",
         "source_readable": sum(s["selection_count"] for s in readable),
         "evidence_refs": copy.deepcopy(refs)},
    ]


def choose_next(project: dict, options: list, knowledge: dict | None = None) -> dict:
    """Choose an unexecuted proposal or an explicit gap from current saved facts."""
    if registry.primary_id(project) != OOF:
        return _domain_choice(project, options, knowledge)
    priority = project.get("policy_ref", {}).get("next_check_priority", "residual_first")
    if priority not in ("residual_first", "source_first"):
        raise ResearchError("INVALID_POLICY", "Only residual_first or source_first is supported.")
    by_id = {item["method_id"]: item for item in options}
    if set(by_id) != {OOF, SOURCE}:
        raise ResearchError("INVALID_REQUEST", "Both local method condition records are required.")
    refs, hits = _evidence(project), []
    for hit in (knowledge or {}).get("evidence", []):
        source = hit["source"]
        hits.append({"citation_id": hit["citation_id"], "source_sha256": source["sha256"],
                     "locator": copy.deepcopy(source.get("metadata", {}).get("locator")),
                     "location": copy.deepcopy(hit.get("location")),
                     "origin": "host_local_retrieval_not_model_read"})
    conditions = [{"method_id": item["method_id"], "outcome": item["condition"],
                   "missing_information": copy.deepcopy(item["missing_information"])} for item in options]

    def decision(status, action, reason):
        return {"project_status": status, "next_action": action, "reason": reason,
                "conditions": conditions, "evidence_refs": copy.deepcopy(refs),
                "knowledge_refs": copy.deepcopy(hits),
                "policy_ref": copy.deepcopy(project.get("policy_ref", {})),
                "scientific_validation": False, "endpoint_eligibility": "uncertain"}

    outstanding = [a for a in _actions(project) if a.get("status") in ("running", "pending", "unknown")]
    if outstanding:
        return decision("needs_review", {"kind": "reconcile_execution", "execution_status": "not_executed",
                                         "action_ids": [a.get("id") for a in outstanding]},
                        "Collect or reconcile the existing execution; policy preferences cannot resend it.")

    numeric, source = by_id[OOF], by_id[SOURCE]
    saved_next = (project.get("next_decision") or {}).get("next_action") or {}
    # Staging a readable selection can change the proposal, but cannot resolve its bound task.
    requires_mapping = bool(project.get("evidence_task_ref")) or (
        saved_next.get("method_id") == SOURCE and saved_next.get("kind") == "evidence_task")
    for action in project.get("actions", []):
        if action.get("status") != "completed":
            continue
        for observation in action.get("observations", []):
            counts = observation.get("values", {}).get("current_candidate", {})
            if counts.get("worse_groups", 0) * 2 > counts.get("group_count", 0):
                requires_mapping = True
    if numeric["condition"] == "not_applicable":
        requires_mapping = True
    # New evidence may change the order; neither a hit nor its text grants approval.
    knowledge_gap = bool(knowledge and knowledge.get("missing_information"))
    requires_mapping = requires_mapping or knowledge_gap
    qualified = {key: item for key, item in by_id.items()
                 if item["condition"] == "satisfied" and not item["completed"] and item["parameters"]}
    order = (SOURCE, OOF) if priority == "source_first" or requires_mapping else (OOF, SOURCE)
    if requires_mapping and SOURCE not in qualified:
        read_count = sum(len(action.get("observations", [])) for action in project.get("evidence_actions", [])
                         if action.get("status") == "completed")
        return decision("waiting", {"method_id": SOURCE, "kind": "evidence_task",
                                    "execution_status": "not_executed",
                                    "required_evidence": ["author object/channel/export-column/batch mapping"]},
                        f"Observed {read_count} extracted source selections and retrieved {len(hits)} host-indexed hits. "
                        "Saved feedback still requires source mapping; these selections do not provide scientific approval. "
                        "Keep the recorded remaining questions and request the missing original mapping.")
    for method_id in order:
        if method_id not in qualified:
            continue
        option = qualified[method_id]
        return decision("active", {"method_id": method_id, "parameters": copy.deepcopy(option["parameters"]),
                                   "kind": "conditional_proposal", "execution_status": "not_executed"},
                        "Choose an eligible unfinished check from saved conditions and the configured order; "
                        "the application must separately accept and execute it.")
    if not source["source_readable"]:
        return decision("waiting", {"method_id": SOURCE, "kind": "evidence_task",
                                    "execution_status": "not_executed",
                                    "required_evidence": copy.deepcopy(source["missing_information"])},
                        "No registered source selections are available; request the actual task-bound material.")
    return decision("waiting", {"kind": "review_saved_evidence", "execution_status": "not_executed",
                                "action_ids": numeric["reusable_action_ids"] + source["reusable_action_ids"]},
                    "Eligible saved checks are already complete. Reuse their observations; "
                    "endpoint mapping remains uncertain and no further numerical loop is justified.")


def grouped_feedback_eligible(profile, scope):
    """Mechanical follow-up qualification; zeros/missing values do not approve an endpoint."""
    return bool(scope.get("group_columns") and any(
        any(column.get("counts", {}).get(kind, 0) > 0
            for kind in ("zero", "empty", "declared_missing", "invalid_numeric", "nonfinite"))
        for column in profile.get("numeric_columns", [])))


def _workbook_origin(project):
    declared = project.get("source_provenance", {}).get("origin_sha256")
    for receipt in project.get("evidence_sources", []):
        for source in receipt.get("source_metadata", []):
            if source["sha256"] == declared and source["media_type"] == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet":
                return {"origin_receipt_sha256": receipt["receipt_snapshot_sha256"], "origin_source_id": source["id"]}
    return None


def _domain_methods(project, need):
    primary = registry.primary_id(project)
    registry.get(primary)
    actions = _actions(project)
    unresolved = [a["id"] for a in actions if a.get("status") in ("running", "pending", "unknown")]
    completed = [a for a in project.get("actions", []) if a.get("command") == primary and a.get("status") == "completed"]
    done_receipts = {a.get("receipt_snapshot_sha256") for a in project.get("evidence_actions", []) if a.get("status") == "completed"}
    failed_receipts = {a.get("receipt_snapshot_sha256") for a in project.get("evidence_actions", []) if a.get("status") == "failed"}
    readable = [r for r in project.get("evidence_sources", []) if r["receipt_snapshot_sha256"] not in failed_receipts]
    unread = [r for r in readable if r["receipt_snapshot_sha256"] not in done_receipts]
    valid_scope = bool(project.get("source_snapshot_sha256") and project.get("source_scope"))
    condition = "satisfied" if valid_scope and not unresolved else "uncertain"
    if need in ("alp_endpoint", "alp_effect"):
        condition = "not_applicable"
    options = [{"method_id": primary, "condition": condition,
             "domain_scope": copy.deepcopy(project.get("source_scope", {})),
             "reasons": ["Use only this adapter's validated domain source and frozen evaluation; do not compare unlike endpoints."],
             "missing_information": [] if valid_scope else ["validated domain source packet"], "parameters": {},
             "completed": bool(completed), "reusable_action_ids": [a["id"] for a in completed],
             "unresolved_execution_ids": unresolved, "evidence_refs": _evidence(project)},
            {"method_id": registry.SOURCE, "condition": "uncertain" if unresolved or not readable else "satisfied",
             "reasons": ["Source reading preserves original statements; domain interpretation remains unreviewed."],
             "missing_information": [] if readable else ["task-bound domain source selections"],
             "parameters": {"receipt_snapshot_sha256": unread[0]["receipt_snapshot_sha256"]} if unread else {},
             "completed": bool(readable) and not unread,
             "reusable_action_ids": [a["id"] for a in project.get("evidence_actions", []) if a.get("status") == "completed"],
             "source_readable": sum(r.get("selection_count", 0) for r in readable),
             "unresolved_execution_ids": unresolved, "evidence_refs": _evidence(project)}]
    for method_id in registry.followup_ids(primary):
        predecessor = completed[-1] if completed else None
        profile = next((item.get("profile", {}) for item in (predecessor or {}).get("observations", [])
                        if item.get("kind") == "tabular_quality_audit"), {})
        eligible = grouped_feedback_eligible(profile, project.get("source_scope", {}))
        parameters = ({"based_on_action_id": predecessor["id"], "based_on_result_sha256": predecessor["result_sha256"]}
                      if predecessor else {})
        reason = "Inspect zero/missing/invalid concentration only after saved quality feedback and declared group fields; keep all original values and unresolved source needs."
        missing = ["completed quality feedback with zero/missing/invalid values and declared group columns"]
        if method_id == registry.WORKBOOK:
            origin = _workbook_origin(project)
            eligible = bool(predecessor and origin)
            if origin:
                parameters.update(origin)
            reason = "Compare the unchanged CSV against saved workbook cells from its declared, captured origin; retain all unmatched or ambiguous projection candidates."
            missing = ["completed quality feedback and a captured XLSX matching the submitted origin SHA"]
        done = [item for item in project.get("actions", []) if item["command"] == method_id
                and item["status"] == "completed" and item["method_instance"]["parameters"] == parameters]
        options.append({"method_id": method_id,
                        "condition": "uncertain" if unresolved or not predecessor else "satisfied" if eligible and condition != "not_applicable" else "not_applicable",
                        "parameters": parameters, "completed": bool(done),
                        "reusable_action_ids": [item["id"] for item in done], "unresolved_execution_ids": unresolved,
                        "reasons": [reason],
                        "missing_information": [] if eligible else missing,
                        "evidence_refs": _evidence(project)})
    return options


def _domain_choice(project, options, knowledge):
    primary = registry.primary_id(project)
    by_id = {option["method_id"]: option for option in options}
    if set(by_id) != {primary, registry.SOURCE, *registry.followup_ids(primary)}:
        raise ResearchError("INVALID_REQUEST", "Expected the registered domain method and source-selection method.")
    base = {"scientific_validation": False, "conditions": copy.deepcopy(options),
            "knowledge_refs": copy.deepcopy((knowledge or {}).get("evidence", [])),
            "policy_ref": copy.deepcopy(project.get("policy_ref", {}))}
    unresolved = [a["id"] for a in _actions(project) if a.get("status") in ("running", "pending", "unknown")]
    if unresolved:
        return {**base, "project_status": "waiting", "next_action": {"kind": "reconcile_execution", "action_ids": unresolved,
                "execution_status": "not_executed"}, "reason": "Reconcile the original execution before any further work."}
    source = by_id[registry.SOURCE]
    if source["condition"] == "satisfied" and not source["completed"]:
        return {**base, "project_status": "active", "next_action": {"method_id": registry.SOURCE, "parameters": source["parameters"],
                "kind": "conditional_proposal", "execution_status": "not_executed"}, "reason": "Read the registered new domain selections before revising the interpretation."}
    if not by_id[primary]["completed"] and by_id[primary]["condition"] == "satisfied":
        return {**base, "project_status": "active", "next_action": {"method_id": primary, "parameters": {},
                "kind": "conditional_proposal", "execution_status": "not_executed"}, "reason": "Execute the qualified domain check with its original endpoint and evaluation."}
    for method_id in registry.followup_ids(primary):
        option = by_id[method_id]
        if option["condition"] == "satisfied" and not option["completed"]:
            return {**base, "project_status": "active", "next_action": {"method_id": method_id,
                    "parameters": copy.deepcopy(option["parameters"]), "kind": "conditional_proposal", "execution_status": "not_executed"},
                    "reason": ("Saved quality feedback and the captured declared origin qualify a workbook candidate projection check; conversion and scientific questions remain unresolved."
                               if method_id == registry.WORKBOOK else
                               "Saved quality feedback qualifies a grouped zero/missing inspection; prior source and scientific questions remain unresolved.")}
    saved = copy.deepcopy((project.get("next_decision") or {}).get("next_action", {}))
    if saved.get("method_id") != registry.SOURCE or saved.get("kind") != "evidence_task":
        # A completed read is no longer a next task. Recover the latest analysis need,
        # rather than carrying its already-read receipt forward as a proposal.
        latest = next((action for action in reversed(project.get("actions", []))
                       if action.get("command") in {primary, *registry.followup_ids(primary)}
                       and action.get("status") == "completed"), None)
        original = ((latest or {}).get("next_decision") or {}).get("next_action", {})
        if original.get("method_id") == registry.SOURCE and original.get("kind") == "evidence_task":
            saved = copy.deepcopy(original)
        else:
            saved = {"method_id": registry.SOURCE, "kind": "evidence_task", "required_evidence": ["independent sources for the recorded domain limitations"]}
    saved["execution_status"] = "not_executed"
    return {**base, "project_status": "waiting", "next_action": saved,
            "reason": f"Read {source['source_readable']} domain source selections; {len((knowledge or {}).get('evidence', []))} host-indexed excerpts informed this record. "
                      "Keep the actual technical feedback and unresolved domain conditions; reading does not establish scientific or user-value approval."}
