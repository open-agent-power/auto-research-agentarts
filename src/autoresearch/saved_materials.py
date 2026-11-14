"""Copy explicitly selected bounded material from retained native results."""
import copy
import json
import math

from .contracts import ResearchError, canonical, fingerprint
from .project_selection import _hash, _text


FIELDS = ("groups", "folds", "rows")
RETRIEVAL_KIND = "retrieval_adverse_query"
MAX_RETRIEVAL_SELECTORS = 4
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
    known, queries = set(), set()
    for item in value:
        if type(item) is dict and item.get("kind") == RETRIEVAL_KIND:
            _require(set(item) == {"kind", "action_id", "result_sha256", "split", "query_id"}
                     and _text(item["action_id"], 160) and _hash(item["result_sha256"])
                     and item["split"] in ("dev", "validation", "test") and _text(item["query_id"], 80),
                     "Select an exact saved adverse query, split, action and result SHA.", code)
            identity = (item["action_id"], item["split"], item["query_id"])
            _require(identity not in queries and len(queries) < MAX_RETRIEVAL_SELECTORS,
                     "Use at most four distinct saved adverse queries.", code)
            queries.add(identity)
            continue
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


def _retrieval_action(state, action, family, predecessor=None):
    """Check native request and producer bindings for both retrieval families."""
    from .method_registry import evaluation_ref
    module = family.module
    method = action.get("command")
    _require(method in (module.TOOL_ID, module.AUDIT_TOOL_ID)
             and state.get("registration", {}).get("method_id") == module.TOOL_ID
             and action.get("status") == "completed" and action.get("project_id") == state["id"]
             and action.get("run_id") == state["run_id"] and action.get("dimension") is None
             and action.get("source_snapshot_sha256") == state["source_snapshot_sha256"]
             and _text(action.get("request_id"), 160) and _hash(action.get("code_identity"))
             and _hash(action.get("result_sha256")), "Retrieval action identity or source differs.")
    request = {"project_id": state["id"], "command": method, "dimension": None,
               "source_snapshot_sha256": state["source_snapshot_sha256"]}
    parameters = {}
    if method == module.AUDIT_TOOL_ID:
        parameters = {"based_on_action_id": predecessor["id"], "based_on_result_sha256": predecessor["result_sha256"]}
        _require(action.get("parameters") == parameters and action.get("evaluation_ref") == evaluation_ref(method),
                 "Saved audit must bind the exact primary action and result.")
        request.update(parameters=parameters, evaluation_ref=evaluation_ref(method))
    instance = action.get("method_instance", {})
    _require(action.get("request_sha256") == fingerprint(request)
             and action.get("id") == "action-" + fingerprint({"request_id": action["request_id"], **request})[:32]
             and action.get("artifact") == "artifacts/" + action["id"] + ".json"
             and instance.get("definition_ref") == {"id": method, "version": module.ADAPTER_VERSION}
             and instance.get("scope") == state["source_scope"] and instance.get("parameters") == parameters
             and instance.get("evaluation_ref") == evaluation_ref(method)
             and instance.get("input_bindings") == {"source_snapshot_sha256": state["source_snapshot_sha256"], **parameters},
             "Saved retrieval request, action, evaluator or producer binding differs.")


def _retrieval_material(project, state, action, request):
    from . import saved_retrieval_reader as reader
    value = reader.read_adverse_query(project, state, action_id=action["id"],
                                      split=request["split"], query_id=request["query_id"])
    binding = value["binding"]
    _require(binding["action_id"] == action["id"] and binding["result_sha256"] == request["result_sha256"]
             and binding["project_id"] == state["id"] and binding["snapshot_ref"] == state["snapshot_ref"]
             and binding["source_snapshot_sha256"] == state["source_snapshot_sha256"],
             "The selected retrieval result or current snapshot changed.")
    primary = [item for item in state["actions"] if item["id"] == binding["primary_action_id"]]
    _require(len(primary) == 1 and primary[0].get("result_sha256") == binding["primary_result_sha256"],
             "The selected retrieval primary result is unavailable.")
    family = reader._family(action["command"])
    _require(primary[0].get("command") == family.module.TOOL_ID, "The original retrieval family differs.")
    _retrieval_action(state, primary[0], family)
    if action["id"] != primary[0]["id"]:
        _retrieval_action(state, action, family, predecessor=primary[0])
    query = value["query"]
    arms = []
    for arm in value["arms"]:
        arms.append({"method": arm["method"], "metrics": copy.deepcopy(arm["metrics"]),
                     "qrel": copy.deepcopy(arm["qrel"]),
                     "ranking": [{key: doc[key] for key in ("rank", "id", "line")} for doc in arm["documents"]]})
    result = {"kind": RETRIEVAL_KIND, "action_id": action["id"], "result_sha256": action["result_sha256"],
              "artifact_ref": action["artifact"], "binding": copy.deepcopy(binding),
              "producer": {"request_id": action["request_id"], "method_id": action["command"],
                           "code_identity": action["code_identity"], "evaluation_ref": action["method_instance"]["evaluation_ref"]},
              "query": {key: query[key] for key in ("id", "split", "line", "source_sha256")},
              "corpus_source_sha256": state["source_scope"]["input_identities"]["corpus"]["sha256"],
              "category": value["category"], "arms": arms,
              "coverage": "complete_saved_qrels_rankings_metrics_for_both_arms", "source_text_included": False,
              "scientific_validation": False}
    if "contract" in value:
        result["contract"] = copy.deepcopy(value["contract"])
    return result


def _validate_retrieval_material(context, material, feedback, seen):
    from . import saved_retrieval_reader as reader
    from .method_registry import evaluation_ref
    code = "INVALID_PLAN_CONTEXT"
    base = {"kind", "action_id", "result_sha256", "artifact_ref", "binding", "producer", "query", "corpus_source_sha256", "category",
            "arms", "coverage", "source_text_included", "scientific_validation"}
    _require(set(material) in (base, base | {"contract"}) and material["coverage"] == "complete_saved_qrels_rankings_metrics_for_both_arms"
             and material["source_text_included"] is False and material["scientific_validation"] is False,
             "Use only the selected saved query without claiming source text was provided.", code)
    query, binding, producer = material["query"], material["binding"], material["producer"]
    _require(type(query) is dict and set(query) == {"id", "split", "line", "source_sha256"}
             and _text(query["id"], 80) and query["split"] in reader.SPLITS
             and type(query["line"]) is int and query["line"] >= 1 and _hash(query["source_sha256"]),
             "Use an exact saved query identity and source locator.", code)
    _require(_text(material["action_id"], 160), "Use the exact saved action ID.", code)
    identity = (material["action_id"], query["split"], query["id"])
    _require(identity not in seen and len(seen) < MAX_RETRIEVAL_SELECTORS,
             "Use at most four distinct saved adverse queries.", code)
    selection = context["selection_context"]
    fields = {"project_id", "snapshot_ref", "action_id", "result_sha256", "source_snapshot_sha256",
              "primary_action_id", "primary_result_sha256"}
    _require(type(binding) is dict and set(binding) == fields and binding["project_id"] == selection["project_id"]
             and binding["snapshot_ref"] == selection["snapshot_ref"]
             and binding["source_snapshot_sha256"] == selection["source_snapshot_sha256"]
             and binding["action_id"] == material["action_id"] and binding["result_sha256"] == material["result_sha256"]
             and _text(binding["primary_action_id"], 160)
             and _hash(binding["result_sha256"]) and _hash(binding["primary_result_sha256"]),
             "Saved retrieval source, result or snapshot identity differs.", code)
    action = feedback.get(material["action_id"], {})
    _require(type(producer) is dict and set(producer) == {"request_id", "method_id", "code_identity", "evaluation_ref"}
             and _text(producer["method_id"], 160)
             and _hash(producer["code_identity"]) and producer["request_id"] == action.get("request_id")
             and producer["method_id"] == action.get("method_id") and action.get("status") == "completed"
             and material["artifact_ref"] == action.get("artifact_ref"), "Use the exact completed feedback action.", code)
    try:
        family = reader._family(producer["method_id"])
    except ResearchError:
        raise ResearchError(code, "Unsupported saved retrieval family.") from None
    _require(producer["evaluation_ref"] == evaluation_ref(producer["method_id"])
             and ("contract" in material) == family.relevance
             and (not family.relevance or material["contract"] == family.contract()),
             "Saved retrieval evaluator or family differs.", code)
    primary = feedback.get(binding["primary_action_id"], {})
    _require(primary.get("status") == "completed" and primary.get("method_id") == family.module.TOOL_ID,
             "The complete primary retrieval feedback must be supplied.", code)
    assets = selection.get("domain_scope", {}).get("input_identities", {})
    _require(type(assets) is dict and all(type(assets.get(key)) is dict for key in ("queries", "corpus", "train_qrels", "test_qrels")),
             "Captured retrieval input identities are required.", code)
    role = "test_qrels" if query["split"] == "test" else "train_qrels"
    _require(query["source_sha256"] == assets["queries"].get("sha256")
             and _hash(material["corpus_source_sha256"])
             and material["corpus_source_sha256"] == assets["corpus"].get("sha256"), "Query or corpus source differs.", code)
    arms = material["arms"]
    _require(type(arms) is list and len(arms) == 2 and [arm.get("method") for arm in arms if type(arm) is dict] == list(family.methods)
             and material["category"] in reader.CATEGORIES, "Both saved retrieval arms are required.", code)
    for arm in arms:
        _require(type(arm) is dict and set(arm) == {"method", "metrics", "qrel", "ranking"}, "Invalid saved arm.", code)
        metrics, qrel, ranking = arm["metrics"], arm["qrel"], arm["ranking"]
        _require(type(metrics) is dict and set(metrics) == set(reader.METRICS)
                 and all(type(x) in (int, float) and math.isfinite(x) and 0 <= x <= 1 for x in metrics.values()),
                 "Saved metrics must be finite and bounded.", code)
        qfields = {"doc_ids", "source_sha256", "role"} | ({"grades", "missing_doc_ids"} if family.relevance else set())
        _require(type(qrel) is dict and set(qrel) == qfields and qrel["role"] == role
                 and _hash(qrel["source_sha256"]) and qrel["source_sha256"] == assets.get(role, {}).get("sha256")
                 and type(qrel["doc_ids"]) is list and all(_text(doc, 160) for doc in qrel["doc_ids"])
                 and len(qrel["doc_ids"]) <= 2000 and len(set(qrel["doc_ids"])) == len(qrel["doc_ids"]),
                 "Saved positive labels or source differ.", code)
        if family.relevance:
            _require(type(qrel["grades"]) is dict and set(qrel["grades"]) == set(qrel["doc_ids"])
                     and all(type(value) is int and value > 0 for value in qrel["grades"].values())
                     and type(qrel["missing_doc_ids"]) is list
                     and all(_text(doc, 160) and doc in qrel["doc_ids"] for doc in qrel["missing_doc_ids"])
                     and len(set(qrel["missing_doc_ids"])) == len(qrel["missing_doc_ids"]),
                     "Original grades and missing positive document IDs must be preserved.", code)
        _require(type(ranking) is list and len(ranking) <= 20
                 and all(type(doc) is dict and set(doc) == {"id", "rank", "line"}
                         and _text(doc["id"], 160) and type(doc["rank"]) is int and type(doc["line"]) is int
                         and doc["line"] >= 1 for doc in ranking)
                 and [doc["rank"] for doc in ranking] == list(range(1, len(ranking) + 1))
                 and len({doc["id"] for doc in ranking}) == len(ranking), "Saved ranking identities differ.", code)
    _require(arms[0]["qrel"] == arms[1]["qrel"], "Both arms must retain the same original query labels.", code)
    baseline, candidate = arms[0]["metrics"], arms[1]["metrics"]
    category = ("metric_loss" if any(candidate[name] - baseline[name] < -1e-12 for name in reader.METRICS)
                else "no_metric_loss_both_incomplete" if baseline["recall@20"] < 1 and candidate["recall@20"] < 1
                else "no_metric_loss_baseline_only_incomplete" if baseline["recall@20"] < 1 and candidate["recall@20"] == 1
                else "no_metric_loss_other")
    _require(material["category"] == category, "Saved adverse category differs from the supplied metrics.", code)
    seen.add(identity)


def materialize(project, state, normalized_requests):
    materials = []
    for request in normalize_requests(normalized_requests):
        matches = [action for action in state["actions"] if action["id"] == request["action_id"]]
        _require(len(matches) == 1 and matches[0].get("result_sha256") == request["result_sha256"],
                 "The selected diagnostic action or exact result SHA is unavailable.")
        action = matches[0]
        if request.get("kind") == RETRIEVAL_KIND:
            materials.append(_retrieval_material(project, state, action, request))
            continue
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
    known, queries = set(), set()
    for material in materials:
        if type(material) is dict and material.get("kind") == RETRIEVAL_KIND:
            _validate_retrieval_material(context, material, feedback, queries)
            continue
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
