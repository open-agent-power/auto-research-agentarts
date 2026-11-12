"""Copy explicitly selected complete fields from retained native OOF diagnostics."""
import copy
import json

from .contracts import ResearchError, canonical, fingerprint
from .project_selection import _hash, _text


FIELDS = ("groups", "folds", "rows")
METHODS = {"data.saved-oof-random-diagnostics": ("random_cv", "data.ridge-random-validation"),
           "data.saved-oof-group-diagnostics": ("group_cv", "data.ridge-group-validation")}
SOURCE_FIELDS = {"action_id", "request_id", "method_id", "result_sha256", "producer_code_identity",
                 "design_version", "resource_id", "resource_version", "target_column", "target_unit"}


def _require(condition, message, code="EVIDENCE_CHANGED"):
    if not condition:
        raise ResearchError(code, message)


def normalize_requests(value):
    if value is None:
        return []
    code = "INVALID_SAVED_MATERIALS"
    _require(type(value) is list, "Saved materials must be an array of explicit saved diagnostic selectors.", code)
    known = set()
    for item in value:
        _require(type(item) is dict and set(item) == {"action_id", "result_sha256", "fields"}
                 and _text(item["action_id"], 160) and _hash(item["result_sha256"])
                 and item["action_id"] not in known, "Use distinct diagnostic action IDs and exact result SHA256 values.", code)
        fields = item["fields"]
        _require(type(fields) is list and bool(fields) and all(type(field) is str and field in FIELDS for field in fields)
                 and len(set(fields)) == len(fields), "Select distinct complete groups, folds or rows fields.", code)
        known.add(item["action_id"])
    return copy.deepcopy(value)


def require_complete_size(context, maximum, code):
    try:
        size = len(canonical(context).encode("utf-8"))
    except (TypeError, ValueError, RecursionError):
        return  # The caller's JSON validator reports malformed values.
    _require(size <= maximum,
             f"Complete saved materials context requires {size} UTF-8 bytes; limit is {maximum}. "
             "Nothing was supplied partially; select fewer complete fields.", code)


def _artifact(project, state, action, schema):
    from .method_registry import evaluation_ref
    _require(action.get("status") == "completed" and action.get("project_id") == state["id"]
             and action.get("source_snapshot_sha256") == state["source_snapshot_sha256"]
             and action.get("artifact") == "artifacts/" + action["id"] + ".json"
             and action.get("evaluation_ref") == evaluation_ref(action["command"])
             and action.get("method_instance", {}).get("evaluation_ref") == action["evaluation_ref"],
             "Require a completed native action from this project's captured source.")
    try:
        envelope = json.loads(project._artifact(action).read_bytes())
    except (OSError, ValueError, UnicodeError) as error:
        raise ResearchError("EVIDENCE_CHANGED", "The retained native result artifact is missing or invalid.") from error
    _require(type(envelope) is dict and envelope.get("sha256") == action.get("result_sha256")
             and envelope["sha256"] == fingerprint({key: value for key, value in envelope.items() if key != "sha256"})
             and all(envelope.get(key) == action.get(key) for key in
                     ("request_sha256", "code_identity", "source_snapshot_sha256"))
             and envelope.get("action_id") == action["id"], "Saved action, result SHA and producer identities differ.")
    tool = envelope.get("tool_result")
    _require(type(tool) is dict and tool.get("schema_version") == schema
             and tool.get("tool_id") == action["command"] and tool.get("status") == "completed"
             and tool.get("scientific_validation") is False and tool.get("failure") is None,
             "Require the completed native result schema without scientific approval.")
    observations = tool.get("observations")
    _require(type(observations) is list and bool(observations) and all(type(item) is dict for item in observations)
             and action.get("observations") == [dict(item, id=action["id"] + ":observation:" + str(index),
                                                    action_id=action["id"]) for index, item in enumerate(observations)],
             "Saved observations differ from the original committed result.")
    return tool


def _diagnostic(project, state, action):
    _require(action.get("command") in METHODS, "Select a native saved-OOF diagnostic action.")
    check, source_method = METHODS[action["command"]]
    tool = _artifact(project, state, action, "saved-oof-diagnostic-result-v1")
    diagnostic = tool.get("result", {}).get("diagnostic")
    _require(type(diagnostic) is dict and diagnostic.get("schema_version") == "saved-oof-diagnostics-v1"
             and diagnostic.get("check") == check and diagnostic.get("scientific_validation") is False
             and tool.get("new_fits") == 0 and tool.get("model_calls") == 0,
             "Require the saved zero-fit diagnostic and its original check.")
    observations = tool["observations"]
    _require(len(observations) == 1 and observations[0].get("kind") == "saved_oof_diagnostic"
             and observations[0].get("producer") == action["command"]
             and observations[0].get("source_check") == check and observations[0].get("scientific_validation") is False,
             "Require the native diagnostic's saved observation.")
    observation, origin = observations[0], diagnostic.get("provenance", {})
    source_ref = observation.get("source_ref")
    _require(type(source_ref) is dict and set(source_ref) == SOURCE_FIELDS,
             "The original diagnostic source reference is incomplete.")
    matches = [item for item in state["actions"] if item["id"] == source_ref["action_id"]]
    _require(len(matches) == 1 and matches[0].get("command") == source_method,
             "The diagnostic's original CV source is missing or has a different check.")
    source = matches[0]
    source_tool = _artifact(project, state, source, "ridge-validation-result-v1")
    analysis = source_tool.get("result", {}).get("analysis", {})
    binding = action.get("design_binding")
    _require(type(binding) is dict and type(binding.get("version")) is int
             and [item for item in state.get("design_revisions", []) if item.get("version") == binding["version"]] == [binding]
             and binding == source.get("design_binding") == analysis.get("design_binding") == origin.get("design_binding")
             and binding.get("project_id") == state["id"]
             and binding.get("source_snapshot_sha256") == state["source_snapshot_sha256"],
             "The saved diagnostic and CV must share their registered historical design.")
    expected_source = {"action_id": source["id"], "request_id": source["request_id"], "method_id": source["command"],
                       "result_sha256": source["result_sha256"], "producer_code_identity": source["code_identity"],
                       "design_version": binding["version"], "resource_id": binding["resource"]["id"],
                       "resource_version": binding["resource"]["version"], "target_column": analysis.get("target_column"),
                       "target_unit": analysis.get("target_unit")}
    _require(source_ref == expected_source and analysis.get("schema_version") == "ridge-validation-v1"
             and analysis.get("check") == check and analysis.get("scientific_validation") is False
             and analysis.get("source_snapshot_sha256") == state["source_snapshot_sha256"]
             and analysis.get("summary", {}).get("status") == "computed"
             and all(analysis.get(key) == diagnostic.get(key) for key in ("protocol", "target_column", "target_unit"))
             and analysis.get("target_column") == binding.get("target_column")
             and origin.get("project_id") == state["id"] and origin.get("source_scope") == state["source_scope"]
             and origin.get("source_snapshot_sha256") == state["source_snapshot_sha256"]
             and origin.get("current_project_code_identity") == action["code_identity"]
             and origin.get("artifact_sha256") == source["result_sha256"]
             and origin.get("action") == {key: source[key] for key in ("id", "request_id", "command", "status",
                 "request_sha256", "source_snapshot_sha256", "code_identity", "result_sha256", "evaluation_ref")},
             "Diagnostic provenance, original source CV, producer or evaluation scope differs.")
    evidence = source_tool.get("evidence_refs", [])
    _require(len(evidence) == 1 and origin.get("source_sha256") == evidence[0].get("source_sha256")
             and origin.get("source_file") == evidence[0].get("file_name")
             and action.get("parameters") == {"based_on_action_id": source["id"], "based_on_result_sha256": source["result_sha256"]}
             and action.get("method_instance", {}).get("input_bindings", {}).get("design_revision") == binding["version"]
             and tool.get("evidence_refs") == [{"source_snapshot_sha256": state["source_snapshot_sha256"],
                 "source_sha256": origin["source_sha256"], "producer": source_ref,
                 "locator": {"kind": "saved_oof_action", "action_id": source["id"], "result_sha256": source["result_sha256"]}}],
             "Diagnostic source receipt or frozen predecessor differs.")
    _require(all(type(diagnostic.get(field)) is list for field in FIELDS), "Require all original diagnostic tables.")
    _require(all(diagnostic.get(key) == observation.get(key) for key in
                 ("input_n", "excluded", "row_weighted", "group_weighted", "group_columns", "prediction_ranges"))
             and len(diagnostic["rows"]) == observation.get("row_weighted", {}).get("n")
             and len(diagnostic["rows"]) == len(analysis.get("oof", []))
             and len(diagnostic["groups"]) == observation.get("group_weighted", {}).get("group_count")
             and len(diagnostic["folds"]) == len(observation.get("fold_errors", [])),
             "The complete diagnostic tables differ from their original saved coverage.")
    return diagnostic, source_ref, binding


def materialize(project, state, normalized_requests):
    materials = []
    for request in normalize_requests(normalized_requests):
        matches = [action for action in state["actions"] if action["id"] == request["action_id"]]
        _require(len(matches) == 1 and matches[0].get("result_sha256") == request["result_sha256"],
                 "The selected diagnostic action or exact result SHA is unavailable.")
        action = matches[0]
        diagnostic, source_ref, binding = _diagnostic(project, state, action)
        materials.append({"action_id": action["id"], "result_sha256": action["result_sha256"], "artifact_ref": action["artifact"],
            "producer": {"request_id": action["request_id"], "method_id": action["command"],
                "code_identity": action["code_identity"], "source_snapshot_sha256": action["source_snapshot_sha256"],
                "design_version": binding["version"]}, "source_ref": copy.deepcopy(source_ref),
            "fields": {field: {"path": ["tool_result", "result", "diagnostic", field],
                               "count": len(diagnostic[field]), "value": copy.deepcopy(diagnostic[field])}
                       for field in request["fields"]},
            "coverage": "complete_saved_fields", "scientific_validation": False})
    return materials


def validate_supplied(context):
    """Check frozen shapes and feedback associations without consulting live artifacts."""
    code = "INVALID_PLAN_CONTEXT"
    materials = context.get("supplied_materials")
    _require(context.get("schema_version") == "research-plan-context-v3" and type(materials) is list and bool(materials),
             "A v3 context requires explicitly supplied complete saved materials.", code)
    feedback = {item["action_id"]: item for item in context["feedback"]}
    known = set()
    for material in materials:
        _require(type(material) is dict and set(material) == {"action_id", "result_sha256", "artifact_ref", "producer",
                     "source_ref", "fields", "coverage", "scientific_validation"}
                 and _text(material["action_id"], 160) and material["action_id"] not in known
                 and material["action_id"] in feedback and _hash(material["result_sha256"])
                 and material["coverage"] == "complete_saved_fields" and material["scientific_validation"] is False,
                 "Retain distinct complete saved material identities and coverage.", code)
        action, producer = feedback[material["action_id"]], material["producer"]
        _require(type(producer) is dict and set(producer) == {"request_id", "method_id", "code_identity",
                     "source_snapshot_sha256", "design_version"}
                 and producer["method_id"] in METHODS and producer["method_id"] == action["method_id"]
                 and producer["request_id"] == action["request_id"] and _hash(producer["code_identity"])
                 and producer["source_snapshot_sha256"] == context["selection_context"]["source_snapshot_sha256"]
                 and type(producer["design_version"]) is int and producer["design_version"] >= 1
                 and action["status"] == "completed" and material["artifact_ref"] == action["artifact_ref"]
                 and _text(material["artifact_ref"], 500), "Associate each material with its completed diagnostic feedback.", code)
        observations = action["observations"]
        _require(len(observations) == 1 and observations[0].get("kind") == "saved_oof_diagnostic"
                 and observations[0].get("producer") == producer["method_id"]
                 and observations[0].get("source_check") == METHODS[producer["method_id"]][0]
                 and observations[0].get("scientific_validation") is False,
                 "Retain the associated native diagnostic observation.", code)
        observation, source = observations[0], material["source_ref"]
        _require(type(source) is dict and set(source) == SOURCE_FIELDS and source == observation.get("source_ref")
                 and source["design_version"] == producer["design_version"]
                 and source["method_id"] == METHODS[producer["method_id"]][1]
                 and all(_hash(source[key]) for key in ("result_sha256", "producer_code_identity"))
                 and observation.get("diagnostic_ref") == {"kind": "action_artifact_field",
                     "artifact_ref": material["artifact_ref"], "path": ["tool_result", "result", "diagnostic"],
                     "coverage": "complete_rows_folds_groups"}, "Retain the original CV and complete diagnostic reference.", code)
        source_feedback = feedback.get(source["action_id"], {})
        source_observations = source_feedback.get("observations", [])
        _require(source_feedback.get("status") == "completed" and source_feedback.get("request_id") == source["request_id"]
                 and source_feedback.get("method_id") == source["method_id"]
                 and any(item.get("kind") == "ridge_validation" and item.get("check") == observation["source_check"]
                         and item.get("design_binding", {}).get("version") == source["design_version"]
                         and item.get("design_binding", {}).get("resource", {}).get("id") == source["resource_id"]
                         and item.get("design_binding", {}).get("resource", {}).get("version") == source["resource_version"]
                         and item.get("scientific_validation") is False for item in source_observations),
                 "Associate the supplied diagnostic with its original completed CV feedback and design.", code)
        fields = material["fields"]
        _require(type(fields) is dict and bool(fields) and set(fields) <= set(FIELDS),
                 "Only complete saved groups, folds and rows may be supplied.", code)
        for name, field in fields.items():
            expected = {"rows": observation.get("row_weighted", {}).get("n"),
                        "groups": observation.get("group_weighted", {}).get("group_count"),
                        "folds": len(observation.get("fold_errors", []))}[name]
            _require(type(field) is dict and set(field) == {"path", "count", "value"}
                     and field["path"] == ["tool_result", "result", "diagnostic", name]
                     and type(field["value"]) is list and all(type(item) is dict for item in field["value"])
                     and type(field["count"]) is int and field["count"] == len(field["value"]) == expected,
                     "Supply the complete original field with its exact path and saved coverage count.", code)
            summary = observation.get("group_errors") if name == "groups" else observation.get("fold_errors") if name == "folds" else None
            if summary is not None:
                _require(type(summary) is list and len(summary) == len(field["value"])
                         and all({key: value.get(key) for key in row} == row for value, row in zip(field["value"], summary)),
                         "Supplied table values differ from the saved diagnostic feedback.", code)
            if name == "groups" and "group_errors_ref" in observation:
                _require(observation["group_errors_ref"].get("count") == field["count"],
                         "The complete supplied group count differs from its retained table reference.", code)
        known.add(material["action_id"])
    return context
