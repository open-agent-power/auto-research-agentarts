"""Read-only execution constraints for reviewing a frozen research plan context."""

import copy


def _remaining(budget, limit, used, reserved):
    values = [budget.get(key) for key in (limit, used, reserved)]
    if any(type(value) is not int or value < 0 for value in values):
        return None
    return max(0, values[0] - values[1] - values[2])


def assess_plan_readiness(context):
    """Project saved eligibility and budgets, without evaluating the plan's prose.

    The caller supplies a validated frozen research plan context. Remaining budget
    does not establish method eligibility; only the frozen candidates do that.
    Reservations continue to reduce available budget while execution is unknown.
    """
    selection = context["selection_context"]
    budget = selection["budget"]
    blockers = selection["blockers"]
    candidates = selection["candidates"]
    blocked_methods = [
        {key: copy.deepcopy(condition[key]) for key in
         ("method_id", "evaluation_ref", "execution_blockers", "missing_information")
         if key in condition}
        for condition in selection["conditions"]
        if condition["execution_blockers"] or blockers
    ]
    return {
        "schema_version": "plan-readiness-v1",
        "project_id": selection["project_id"],
        "snapshot_ref": selection["snapshot_ref"],
        "state_version": selection["state_version"],
        "context_sha256": selection["context_sha256"],
        "execution_status": "available" if candidates and not blockers else "blocked",
        "remaining_budget": {
            "local_tool_calls": _remaining(budget, "local_tool_call_limit", "local_tool_calls_used", "local_tool_calls_reserved"),
            "evidence_reads": _remaining(budget, "evidence_read_limit", "evidence_reads_used", "evidence_reads_reserved"),
            "estimator_fits": _remaining(budget, "fit_limit", "fit_attempts_used", "fits_reserved"),
        },
        "available_actions": copy.deepcopy(candidates),
        "blocked_methods": blocked_methods,
        "blockers": copy.deepcopy(blockers),
        "scientific_review": "required",
        "scientific_validation": False,
    }


def review_plan_requests(records):
    """Review each plan request's frozen constraints, independent of its answer."""
    return [{"request_id": record["request_id"],
             "assessment": assess_plan_readiness(record["context"])}
            for record in records if record.get("purpose") == "plan"]
