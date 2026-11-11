"""Explicit projections of retained plan feedback; references do not include their text."""
import copy


def projection_notice(context):
    if context["schema_version"] != "research-plan-context-v2":
        return ""
    return (" This v2 research context projects retained feedback. Historical next_decision entries are exact "
            "saved-action references, not included decisions. Source exact_text_ref and resource_ref identify fields "
            "in retained tool artifacts; their original text is not included or established as model-read. "
            "Only supplied excerpts are source text. Numerical summaries, protocols, scopes and actual usage remain "
            "recorded values. Use saved_comparisons to distinguish the explicitly identified parent from the "
            "training-fold mean reference. For comparable records, mae_change is candidate MAE minus parent MAE: "
            "positive is worse and negative is better in that saved comparison. Noncomparable records support no "
            "numerical advantage. A lower saved MAE does not establish independent validation, a physical cause, "
            "or engineering suitability; retain adverse counts and conditional evaluation scope.")


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
