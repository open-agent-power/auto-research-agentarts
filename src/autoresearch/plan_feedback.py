"""Explicit projections of retained plan feedback; references do not include their text."""
import copy

from .contracts import canonical


MAX_INLINE_DIAGNOSTIC_GROUP_BYTES = 8192


def projection_notice(context):
    if context["schema_version"] not in ("research-plan-context-v2", "research-plan-context-v3"):
        return ""
    notice = (" This v2 research context projects retained feedback. Historical next_decision entries are exact "
            "saved-action references, not included decisions. Source exact_text_ref and resource_ref identify fields "
            "in retained tool artifacts; their original text is not included or established as model-read. "
            "Only supplied excerpts are source text. Numerical summaries, protocols, scopes and actual usage remain "
            "recorded values. Use saved_comparisons to distinguish the explicitly identified parent from the "
            "training-fold mean reference. For comparable records, mae_change is candidate MAE minus parent MAE: "
            "positive is worse and negative is better in that saved comparison. Noncomparable records support no "
            "numerical advantage. A lower saved MAE does not establish independent validation, a physical cause, "
            "or engineering suitability; retain adverse counts and conditional evaluation scope.")
    if any(observation.get("kind") == "saved_oof_diagnostic"
           for feedback in context.get("feedback", []) for observation in feedback.get("observations", [])):
        notice += (" Saved OOF diagnostic feedback describes the explicitly identified original CV action, not a new fit. "
                   "Its row/group counts, ranges and fold errors are supplied values. An inline group_errors array is "
                   "the complete group table, not ranked examples. group_errors_ref identifies the entire table when "
                   "it is not included; do not infer its individual entries from counts. diagnostic_ref identifies "
                   "complete retained rows/folds/groups, not additional model-read text. Comparisons use that CV's "
                   "training-fold mean reference, not a parent model; adverse groups and ranges do not establish "
                   "physical impossibility, sample independence or scientific approval.")
    if context["schema_version"] == "research-plan-context-v3":
        notice = notice.replace("This v2 research context", "This v3 research context")
        notice += (" supplied_materials contains complete original saved diagnostic fields selected explicitly by action_id "
                   "and result_sha256. Only fields actually included there are supplied: other diagnostic_ref and "
                   "group_errors_ref fields remain unread references. Counts describe complete saved fields, never ranked "
                   "examples or recomputed tables. Rows contain only saved input_values; missing original inputs were not "
                   "joined from CSV or invented. These supplied values establish no scientific approval.")
    return notice


def project_observations(observations, artifact_ref):
    projected = copy.deepcopy(observations)
    if artifact_ref is None:
        return projected
    for index, observation in enumerate(projected):
        def reference(field):
            return {"kind": "action_artifact_field", "artifact_ref": artifact_ref,
                    "path": ["tool_result", "observations", index, *field]}

        if observation.get("kind") == "source_observed" and "exact_text" in observation:
            text = observation.pop("exact_text")
            observation["exact_text_ref"] = {**reference(["exact_text"]), "characters": len(text)}
        if observation.get("kind") == "saved_oof_diagnostic":
            observation["diagnostic_ref"] = {"kind": "action_artifact_field", "artifact_ref": artifact_ref,
                "path": ["tool_result", "result", "diagnostic"], "coverage": "complete_rows_folds_groups"}
            groups = observation.get("group_errors")
            if type(groups) is list and len(canonical(groups).encode("utf-8")) > MAX_INLINE_DIAGNOSTIC_GROUP_BYTES:
                observation.pop("group_errors")
                observation["group_errors_ref"] = {**reference(["group_errors"]),
                    "mode": "complete_table_not_included", "count": len(groups)}
        binding = observation.get("design_binding")
        if type(binding) is dict and type(binding.get("resource")) is dict:
            resource = binding["resource"]
            binding["resource"] = {key: resource[key] for key in
                                   ("id", "version", "parent_version", "title", "comparison_kind") if key in resource}
            binding["resource_ref"] = reference(["design_binding", "resource"])
    return projected


def decision_reference(project_id, action):
    if action.get("next_decision") is None:
        return None
    return {"kind": "saved_action_record", "project_id": project_id,
            "action_id": action["id"], "request_id": action["request_id"], "field": "next_decision"}
