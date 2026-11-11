"""Freeze a reusable research design and an explicit saved-prediction role."""

import copy

from .contracts import ResearchError, canonical, identifier
from . import input_basis


SAVED_CHECKS = ("baseline", "grouped", "sensitivity")
RAW_CHECKS = ("random_cv", "group_cv", "negative_control")
MAX_RAW_RECORDS = 2048
CHECKS = (*SAVED_CHECKS, *RAW_CHECKS)
CHECK_METHODS = {**{name: "data.prediction-" + name for name in SAVED_CHECKS},
                 "random_cv": "data.ridge-random-validation", "group_cv": "data.ridge-group-validation",
                 "negative_control": "data.prediction-negative-control"}
RESOURCE_FIELDS = {"schema_version", "id", "version", "title", "question", "claim", "alternatives", "checks",
                   "sources", "parent_version", "change_reason"}


def current(state):
    revisions = state.get("design_revisions", [])
    return copy.deepcopy(revisions[-1]) if revisions else None


def family(resource):
    return "raw" if resource["checks"][0] in RAW_CHECKS[:2] else "saved"


def validate_resource(resource):
    if (type(resource) is not dict or not RESOURCE_FIELDS <= set(resource) <= RESOURCE_FIELDS | {"comparison_kind"}
            or resource["schema_version"] != "research-design-resource-v1"
            or type(resource["version"]) is not int or resource["version"] < 1
            or resource["parent_version"] is not None and
            (type(resource["parent_version"]) is not int or not 1 <= resource["parent_version"] < resource["version"])):
        raise ResearchError("INVALID_DESIGN", "A versioned research design resource is required.")
    for field in ("id", "title", "question", "claim", "change_reason"):
        value = resource[field]
        if type(value) is not str or not value.strip() or len(value) > 6000 or "\x00" in value:
            raise ResearchError("INVALID_DESIGN", "Bounded research design text is required.")
    checks = resource["checks"]
    if (type(checks) is not list or not checks or checks[0] not in ("baseline", "random_cv", "group_cv")
            or any(check not in (RAW_CHECKS if checks[0] in RAW_CHECKS[:2] else SAVED_CHECKS) for check in checks)
            or len(set(checks)) != len(checks)
            or type(resource["alternatives"]) is not list or not resource["alternatives"]
            or any(type(item) is not str or not item.strip() for item in resource["alternatives"])
            or type(resource["sources"]) is not list):
        raise ResearchError("INVALID_DESIGN", "Declare a baseline-led saved check sequence or CV-led raw sequence, alternatives and source references.")
    if "comparison_kind" in resource and (resource["comparison_kind"] != "fixed_input_basis"
                                         or family(resource) != "raw" or resource["parent_version"] is None):
        raise ResearchError("INVALID_DESIGN", "A fixed_input_basis comparison requires a raw child resource with an explicit parent version.")
    if len(canonical(resource).encode("utf-8")) > 64 * 1024:
        raise ResearchError("INVALID_DESIGN", "Research design exceeds its saved resource limit.")
    return copy.deepcopy(resource)


def _training(payload, training):
    from . import tabular_quality_adapter as tabular, numeric_association_adapter as numeric
    require = tabular._require
    fields = {"feature_columns", "split_group_columns", "fit_limit"}
    require(type(training) is dict and fields <= set(training) <= fields | {"input_basis"},
            "INVALID_TRAINING", "Declare features, split groups and the cumulative fit limit.")
    spec, _, (column_names, rows, _) = tabular._checked(payload)
    features, groups = training["feature_columns"], training["split_group_columns"]
    require(type(features) is list and 1 <= len(features) <= 16 and all(type(name) is str for name in features)
            and len(set(features)) == len(features) and set(features) <= set(spec["numeric_columns"])
            and type(groups) is list and bool(groups) and all(type(name) is str for name in groups)
            and len(set(groups)) == len(groups) and set(groups) <= set(spec["group_columns"])
            and spec["target_column"] is not None and spec["target_column"] not in features
            and not set(features) & set(spec["group_columns"]) and type(training["fit_limit"]) is int and 0 <= training["fit_limit"] <= 40,
            "INVALID_TRAINING", "Use explicit numeric features, distinct target, declared split groups and 0..40 estimator attempts.")
    input_basis.protocol(training)
    require(10 <= len(rows) <= MAX_RAW_RECORDS, "UNSUPPORTED_SCOPE",
            f"Raw validation supports 10..{MAX_RAW_RECORDS} captured records.")
    positions, missing = {name: index for index, name in enumerate(column_names)}, set(spec["missing_tokens"])
    complete_groups = []
    for row, _ in rows:
        key = tuple(row[positions[name]] for name in groups)
        if all(numeric._finite(row[positions[name]], missing) is not None for name in [*features, spec["target_column"]]) and not any(value in missing for value in key):
            complete_groups.append(key)
    require(len(complete_groups) >= 10 and len(set(complete_groups)) >= 2,
            "UNSUPPORTED_SCOPE", "At least ten complete records and two complete declared groups are required.")
    return copy.deepcopy(training)


def bind(project, *, request_id, expected_state_version, resource, prediction_column, reason, training=None):
    """Append a design revision atomically, preserving original-ID recovery and budgets."""
    from . import method_registry as registry
    from .host_model_selection import HostModelSelection, PENDING
    from .research_project import require

    identifier(request_id)
    require(type(expected_state_version) is int and expected_state_version >= 0,
            "INVALID_REQUEST", "Bind a saved project state version.")
    resource = validate_resource(resource)
    require(type(reason) is str and bool(reason.strip()) and len(reason) <= 2000 and "\x00" not in reason,
            "INVALID_REQUEST", "Record why this research design applies.")
    with project._writer(), project._connect() as con:
        state = project._project(con)
        old = next((item for item in state.get("design_revisions", []) if item["request_id"] == request_id), None)
        if old is not None:
            require(old["based_on_state_version"] == expected_state_version and old["resource"] == resource
                    and old["prediction_column"] == prediction_column and old["reason"] == reason
                    and old.get("training") == training,
                    "IDEMPOTENCY_CONFLICT", "The original design request is bound to different content.")
            return copy.deepcopy(old)
        require(project._action(con, request_id) is None, "IDEMPOTENCY_CONFLICT", "ID belongs to an existing action.")
        project._require_unclaimed(state, request_id, except_collection="design_revisions")
        project._require_fresh(state, project.status(), expected_state_version)
        require(registry.primary_id(state) == "data.tabular-quality-audit",
                "UNSUPPORTED_SCOPE", "Prediction designs require a captured tabular project.")
        require(not any(item["status"] in ("prepared", "running", "unknown") for item in state.get("controller_requests", []))
                and not any(item["status"] == "reserved" for item in state.get("local_model_requests", [])),
                "PROJECT_BUSY", "Complete the accepted request before changing its design.")
        require(not any(item["status"] in PENDING for item in HostModelSelection(project.root).status()["requests"]),
                "HOST_SELECTION_PENDING", "Reconcile the original host-model request before changing its design.")
        payload = project._source(state)
        scope = payload["scope"]
        if family(resource) == "raw":
            require(prediction_column is None, "INVALID_PREDICTION_COLUMN", "Raw validation generates its own saved predictions.")
            training = _training(payload, training)
            usage = project.status()["budget"]
            require(training["fit_limit"] >= max(usage.get("fit_limit", 0), usage.get("fit_attempts_used", 0) + usage.get("fits_reserved", 0)),
                    "FIT_BUDGET_EXHAUSTED", "The cumulative fit limit must preserve previous attempts and reservations.")
            previous_limit = state["budget"].get("fit_limit", 0)
            state["budget"]["fit_limit"] = training["fit_limit"]
            state.setdefault("budget_revisions", []).append({"request_id": request_id, "kind": "fit_limit",
                "from": previous_limit, "to": training["fit_limit"], "reason": reason,
                "based_on_state_version": expected_state_version, "fit_attempts_preserved": usage.get("fit_attempts_used", 0)})
        else:
            require(training is None and type(prediction_column) is str and prediction_column in scope["numeric_columns"]
                    and scope["target_column"] is not None and prediction_column != scope["target_column"],
                    "INVALID_PREDICTION_COLUMN", "Declare different numeric observed and saved-prediction columns.")
        revisions = state.setdefault("design_revisions", [])
        revision = {"version": len(revisions) + 1, "request_id": request_id,
                    "based_on_state_version": expected_state_version, "reason": reason, "resource": resource,
                    "prediction_column": prediction_column, "target_column": scope["target_column"],
                    "project_id": state["id"], "source_snapshot_sha256": state["source_snapshot_sha256"]}
        if training is not None:
            revision["training"] = training
            bound_payload = {**payload, "design_binding": revision}
            revision["fit_requirements"] = {check: registry.RIDGE[CHECK_METHODS[check]].required_fit_attempts(bound_payload)
                                            for check in RAW_CHECKS[:2] if check in resource["checks"]}
        revisions.append(revision)
        state["state_version"] += 1
        project._save(con, state)
        return copy.deepcopy(revision)


def baseline_action(state):
    binding = current(state)
    return next((action for action in reversed(state.get("actions", []))
                 if action["command"] == "data.prediction-baseline" and action["status"] == "completed"
                 and action.get("design_binding") == binding), None)


def action_for_check(state, check):
    binding = current(state)
    return next((action for action in reversed(state.get("actions", []))
                 if action["command"] == CHECK_METHODS[check] and action["status"] == "completed"
                 and action.get("design_binding") == binding), None)


def preferred_checks(state):
    binding = current(state)
    if binding is None:
        return []
    if family(binding["resource"]) == "raw":
        return [check for check in RAW_CHECKS if check in binding["resource"]["checks"]]
    baseline = baseline_action(state)
    improves = baseline is not None and baseline["observations"][0]["summary"].get("outperforms_reference") is True
    order = ("baseline", "grouped", "sensitivity") if improves else ("baseline", "sensitivity", "grouped")
    return [check for check in order if check in binding["resource"]["checks"]]


def choice_reason(state, check):
    binding = current(state)
    if binding is not None and family(binding["resource"]) == "raw":
        previous = action_for_check(state, "group_cv") or action_for_check(state, "random_cv")
        if previous is None:
            return f"The raw-table design executes its configured {check} Ridge comparison within the declared estimator budget."
        summary = previous["observations"][0]["summary"]
        return (f"Validation {previous['id']} saved OOF MAE {summary.get('candidate_mae')}. "
                f"Continue with the configured {check} to inspect the declared split or saved prediction pairing.")
    baseline = baseline_action(state)
    if baseline is None:
        return "The bound research design first compares the explicitly declared saved predictions with the fixed mean reference."
    summary = baseline["observations"][0]["summary"]
    preference = ("Check grouped errors before sensitivity because the saved baseline has lower MAE."
                  if summary.get("outperforms_reference") is True else
                  "Check removal sensitivity before grouped errors because the saved baseline has no established MAE advantage.")
    return (f"Baseline {baseline['id']} saved candidate MAE {summary['candidate_mae']}, reference MAE {summary['reference_mae']} "
            f"and relative improvement {summary['improvement']}. {preference} Selected {check} from the bound design.")


def check_eligible(state, check):
    binding = current(state)
    if binding is None or check not in binding["resource"]["checks"]:
        return False
    if family(binding["resource"]) == "raw":
        if check in RAW_CHECKS[:2]:
            return binding["fit_requirements"].get(check, 0) > 0
        return any(action_for_check(state, name) is not None for name in RAW_CHECKS[:2])
    if check == "baseline":
        return True
    baseline = baseline_action(state)
    if baseline is None:
        return False
    if check == "grouped":
        return bool(state.get("source_scope", {}).get("group_columns"))
    return True


def raw_comparison_reason(state):
    entries = []
    for check in ("random_cv", "group_cv"):
        action = action_for_check(state, check)
        if action is not None:
            summary = action["observations"][0]["summary"]
            entries.append(f"{check} {action['id']} saved OOF MAE {summary.get('candidate_mae')}")
    control = action_for_check(state, "negative_control")
    if control is not None:
        summary = control["observations"][0]["summary"]
        entries.append(f"within-OOF-fold negative control {control['id']} alignment_supported={summary.get('alignment_supported')}")
    return "; ".join(entries) + ". No further configured raw-design check is currently eligible; review the split comparison and original sampling conditions."
