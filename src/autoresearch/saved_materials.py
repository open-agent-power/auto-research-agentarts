"""Copy explicitly selected bounded material from retained native results."""
import copy
import json
import math
import operator

from .contracts import ResearchError, canonical, fingerprint
from .project_selection import _hash, _text


FIELDS = ("groups", "folds", "rows")
RETRIEVAL_KIND = "retrieval_adverse_query"
STAGED_RETRIEVAL_KIND = "staged_retrieval_adverse_query"
STABILITY_KIND = "staged_validation_stability"
QUALITY_KIND = "tabular_quality_feedback"
MAX_RETRIEVAL_SELECTORS = 4
MAX_QUALITY_SELECTORS = 4
QUALITY_UNKNOWN_REASONS = frozenset({"controller_not_started", "controller_id_claimed_by_other_command",
    "controller_prepared", "controller_running", "controller_unknown", "controller_failed", "controller_rejected",
    "controller_waiting", "controller_needs_review", "quality_values_unknown"})
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
    known, queries, quality = set(), set(), set()
    for item in value:
        if type(item) is dict and item.get("kind") == QUALITY_KIND:
            _require(set(item) == {"kind", "registration_request_id", "registration_sha256"}
                     and _text(item["registration_request_id"], 160) and _hash(item["registration_sha256"])
                     and item["registration_request_id"] not in quality and len(quality) < MAX_QUALITY_SELECTORS,
                     "Select at most four distinct exact quality registrations.", code)
            quality.add(item["registration_request_id"])
            continue
        if type(item) is dict and item.get("kind") == STABILITY_KIND:
            _require(set(item) == {"kind", "action_id", "result_sha256"}
                     and _text(item["action_id"], 160) and _hash(item["result_sha256"]),
                     "Select the exact original staged primary action and result.", code)
            identity = (item["action_id"], None, None)
            _require(identity not in queries and len(queries) < MAX_RETRIEVAL_SELECTORS,
                     "Use at most four distinct saved retrieval selectors.", code)
            queries.add(identity)
            continue
        if type(item) is dict and item.get("kind") in (RETRIEVAL_KIND, STAGED_RETRIEVAL_KIND):
            _require(set(item) == {"kind", "action_id", "result_sha256", "split", "query_id"}
                     and _text(item["action_id"], 160) and _hash(item["result_sha256"])
                     and type(item["split"]) is str and item["split"] in (("dev", "validation") if item["kind"] == STAGED_RETRIEVAL_KIND else ("dev", "validation", "test"))
                     and _text(item["query_id"], 80),
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


def _quality_material(project, state, request):
    """Project one exact registration and the original reader's bounded result."""
    from .tabular_quality_feedback import _checked_collection
    records = state.get("tabular_quality_registrations", [])
    _checked_collection(records)
    found = [item for item in records if item["request_id"] == request["registration_request_id"]]
    _require(len(found) == 1 and found[0]["registration_sha256"] == request["registration_sha256"],
             "The original quality registration or SHA is unavailable.")
    record = found[0]
    first = project.read_tabular_quality_feedback(request_id=record["request_id"])
    second = project.read_tabular_quality_feedback(request_id=record["request_id"])
    _require(first == second and project.status()["snapshot_ref"] == state["snapshot_ref"],
             "Quality evidence changed during materialization.")
    _require(first["registration_sha256"] == record["registration_sha256"]
             and first["request_id"] == record["request_id"]
             and first["controller_request_id"] == record["controller_request_id"],
             "The original quality reader binding changed.")
    _require(first["unknown_reason"] != "plan_binding_changed",
             "The registered plan changed; its original quality evidence was not fully checked.")
    _require(first["outcome"] != "unknown" or first["unknown_reason"] in QUALITY_UNKNOWN_REASONS,
             "Quality evidence cannot be authenticated; inspect its original state.")
    return {"kind":QUALITY_KIND, "registration_request_id":record["request_id"],
            "registration_sha256":record["registration_sha256"], "controller_request_id":record["controller_request_id"],
            "plan_version":record["plan_version"], "plan_sha256":record["plan_sha256"],
            "source_snapshot_sha256":record["source_snapshot_sha256"],
            "conditions":copy.deepcopy(record["conditions"]), "feedback":copy.deepcopy(first),
            "scientific_validation":False}


def _validate_quality_material(context, material, feedback, seen):
    """Validate a frozen projection's shape; live authenticity is checked when built."""
    from . import tabular_quality_conditions as conditions
    code = "INVALID_PLAN_CONTEXT"
    fields = {"kind", "registration_request_id", "registration_sha256", "controller_request_id", "plan_version",
              "plan_sha256", "source_snapshot_sha256", "conditions", "feedback", "scientific_validation"}
    _require(set(material) == fields and _text(material["registration_request_id"], 160)
             and material["registration_request_id"] not in seen and len(seen) < MAX_QUALITY_SELECTORS
             and _text(material["controller_request_id"], 160) and _hash(material["registration_sha256"])
             and type(material["plan_version"]) is int and material["plan_version"] >= 1
             and _hash(material["plan_sha256"]) and _hash(material["source_snapshot_sha256"])
             and material["source_snapshot_sha256"] == context["selection_context"]["source_snapshot_sha256"]
             and material["scientific_validation"] is False,
             "Use distinct bounded original quality registration identities.", code)
    seen.add(material["registration_request_id"])
    try:
        registered = conditions.validate_conditions(material["conditions"], numeric_columns=context["selection_context"]["domain_scope"]["numeric_columns"])
    except (ResearchError, KeyError, TypeError):
        raise ResearchError(code, "The saved quality conditions are invalid.") from None
    result = material["feedback"]
    keys = {"schema_version", "outcome", "unknown_reason", "evaluation", "action_id", "result_sha256",
            "scientific_validation", "request_id", "registration_sha256", "controller_request_id"}
    _require(type(result) is dict and set(result) == keys and result["schema_version"] == "tabular-quality-feedback-v1"
             and result["outcome"] in ("condition_met", "condition_not_met", "unknown")
             and result["request_id"] == material["registration_request_id"]
             and result["registration_sha256"] == material["registration_sha256"]
             and result["controller_request_id"] == material["controller_request_id"]
             and result["scientific_validation"] is False,
             "The bounded quality feedback identity is invalid.", code)
    outcome, evaluation = result["outcome"], result["evaluation"]
    if outcome == "unknown":
        _require(type(result["unknown_reason"]) is str and result["unknown_reason"] in QUALITY_UNKNOWN_REASONS and result["action_id"] is None
                 and result["result_sha256"] is None
                 and ((result["unknown_reason"] == "quality_values_unknown") == (evaluation is not None)),
                 "Unknown quality must retain its reason without a known result identity.", code)
    else:
        _require(_text(result["action_id"], 160), "Known quality requires its original action ID.", code)
        action = feedback.get(result["action_id"])
        _require(result["unknown_reason"] is None
                 and _hash(result["result_sha256"]) and type(action) is dict
                 and action["status"] == "completed" and action["method_id"] == "data.tabular-quality-audit"
                 and evaluation is not None, "Known quality requires its supplied completed quality action.", code)
    if evaluation is None:
        return
    child_id = "controller-child-" + fingerprint({"project_id":context["selection_context"]["project_id"],
                                                  "request_id":material["controller_request_id"]})[:32]
    children = [item for item in feedback.values() if item.get("request_id") == child_id]
    _require(len(children) == 1 and children[0]["status"] == "completed"
             and children[0]["method_id"] == "data.tabular-quality-audit"
             and (outcome == "unknown" or children[0]["action_id"] == result["action_id"]),
             "The supplied quality observation does not match the original child.", code)
    observations = children[0]["observations"]
    _require(type(observations) is list and len(observations) == 1 and type(observations[0]) is dict
             and observations[0].get("kind") == "tabular_quality_audit" and type(observations[0].get("profile")) is dict,
             "The original quality observation is unavailable.", code)
    _require(conditions.evaluate_conditions(registered, observations[0]["profile"],
                 numeric_columns=context["selection_context"]["domain_scope"]["numeric_columns"]) == evaluation,
             "The supplied quality evaluation differs from its saved observation.", code)
    _require(type(evaluation) is dict and set(evaluation) == {"schema_version", "outcome", "items", "scientific_validation"}
             and evaluation["schema_version"] == conditions.RESULT_SCHEMA and evaluation["outcome"] == outcome
             and evaluation["scientific_validation"] is False and type(evaluation["items"]) is list
             and len(evaluation["items"]) == len(registered["conditions"]),
             "The original bounded quality evaluation is malformed.", code)
    states = []
    comparisons = {"eq":operator.eq, "gt":operator.gt, "gte":operator.ge, "lt":operator.lt, "lte":operator.le}
    for index, (item, condition) in enumerate(zip(evaluation["items"], registered["conditions"])):
        _require(type(item) is dict and set(item) == {"index", "outcome", "actual", "expected", "unknown_reason"}
                 and type(item["index"]) is int and item["index"] == index,
                 "The saved condition result order differs.", code)
        actual, expected = item["actual"], item["expected"]
        if condition["field"] == "flags":
            _require(actual is None or actual in ("empty", "nonempty"), "The saved flags state is invalid.", code)
            _require(expected == condition["operator"], "The saved flags expectation differs.", code)
            matched = actual == expected if actual is not None else None
        else:
            _require(actual is None or (type(actual) is int and 0 <= actual <= conditions.MAX_ROWS),
                     "The saved quality actual must be a bounded integer or unknown.", code)
            _require(expected is None or (type(expected) is int and 0 <= expected <= conditions.MAX_ROWS),
                     "The saved quality expectation must be bounded or unknown.", code)
            if type(condition["value"]) is int:
                _require(expected == condition["value"], "The saved literal expectation differs.", code)
            matched = None if actual is None or expected is None else comparisons[condition["operator"]](actual, expected)
        expected_outcome = "unknown" if matched is None else "condition_met" if matched else "condition_not_met"
        _require(item["outcome"] == expected_outcome and item["unknown_reason"] ==
                 ("missing_or_invalid_required_value" if matched is None else None),
                 "The saved condition result is inconsistent.", code)
        states.append(expected_outcome)
    aggregate = "unknown" if "unknown" in states else "condition_not_met" if "condition_not_met" in states else "condition_met"
    _require(outcome == aggregate, "Unknown and unmet conditions must retain their original precedence.", code)


def materialize(project, state, normalized_requests):
    materials = []
    for request in normalize_requests(normalized_requests):
        if request.get("kind") == QUALITY_KIND:
            materials.append(_quality_material(project, state, request))
            continue
        matches = [action for action in state["actions"] if action["id"] == request["action_id"]]
        _require(len(matches) == 1 and matches[0].get("result_sha256") == request["result_sha256"],
                 "The selected diagnostic action or exact result SHA is unavailable.")
        action = matches[0]
        if request.get("kind") == STABILITY_KIND:
            materials.append(_stability_material(project, state, action, request))
            continue
        if request.get("kind") == RETRIEVAL_KIND:
            materials.append(_retrieval_material(project, state, action, request))
            continue
        if request.get("kind") == STAGED_RETRIEVAL_KIND:
            materials.append(_staged_retrieval_material(project, state, action, request))
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
    known, queries, quality = set(), set(), set()
    for material in materials:
        if type(material) is dict and material.get("kind") == QUALITY_KIND:
            _validate_quality_material(context, material, feedback, quality)
            continue
        if type(material) is dict and material.get("kind") == STABILITY_KIND:
            _validate_stability_material(context, material, feedback, queries)
            continue
        if type(material) is dict and material.get("kind") == RETRIEVAL_KIND:
            _validate_retrieval_material(context, material, feedback, queries)
            continue
        if type(material) is dict and material.get("kind") == STAGED_RETRIEVAL_KIND:
            _validate_staged_retrieval_material(context, material, feedback, queries)
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


def _staged_retrieval_material(project, state, action, request):
    """Copy one strictly bound staged query; never access final or execute tools."""
    from . import staged_feedback_reader as reader, staged_relevance_adapter as staged
    _require(action.get("command") == staged.TOOL_ID and action.get("status") == "completed",
             "Staged materials require an original completed primary action.")
    value = reader.read_adverse_query(project, state, action_id=action["id"],
                                      split=request["split"], query_id=request["query_id"])
    binding = value["binding"]
    _require(binding["project_id"] == state["id"] and binding["snapshot_ref"] == state["snapshot_ref"]
             and binding["source_snapshot_sha256"] == state["source_snapshot_sha256"]
             and binding["action_id"] == binding["primary_action_id"] == action["id"]
             and binding["result_sha256"] == binding["primary_result_sha256"] == request["result_sha256"]
             and value["origin"]["producer_code_identity"] == action["code_identity"],
             "Staged query source, producer, primary or snapshot differs.")
    arms = [{"method": arm["method"], "metrics": copy.deepcopy(arm["metrics"]), "qrel": copy.deepcopy(arm["qrel"]),
             "ranking": [{key: doc[key] for key in ("rank", "id", "line")} for doc in arm["documents"]],
             "top_documents": copy.deepcopy(arm["documents"][:3])} for arm in value["arms"]]
    return {"kind": STAGED_RETRIEVAL_KIND, "action_id": action["id"], "result_sha256": action["result_sha256"],
            "artifact_ref": action["artifact"], "binding": copy.deepcopy(binding), "origin": copy.deepcopy(value["origin"]),
            "producer": {"request_id": action["request_id"], "method_id": action["command"],
                         "code_identity": action["code_identity"], "evaluation_ref": action["method_instance"]["evaluation_ref"]},
            "query": copy.deepcopy(value["query"]),
            "corpus_source_sha256": state["source_scope"]["input_identities"]["corpus"]["sha256"],
            "category": value["category"], "contract": copy.deepcopy(value["contract"]), "arms": arms,
            "coverage": "complete_saved_qrels_rankings_metrics; top_three_documents_per_arm",
            "source_text_included": True, "scientific_validation": False}


def _validate_staged_retrieval_material(context, material, feedback, seen):
    """Validate sealed fields and associations; original bytes require live materialization."""
    from . import staged_relevance_adapter as staged, saved_retrieval_reader as legacy
    from .method_registry import evaluation_ref
    code = "INVALID_PLAN_CONTEXT"
    try:
        fields = {"kind", "action_id", "result_sha256", "artifact_ref", "binding", "origin", "producer", "query",
                  "corpus_source_sha256", "category", "contract", "arms", "coverage", "source_text_included", "scientific_validation"}
        _require(set(material) == fields and material["kind"] == STAGED_RETRIEVAL_KIND
                 and material["coverage"] == "complete_saved_qrels_rankings_metrics; top_three_documents_per_arm"
                 and material["source_text_included"] is True and material["scientific_validation"] is False,
                 "Use the exact staged saved query material.", code)
        query, binding, origin, producer = (material[k] for k in ("query", "binding", "origin", "producer"))
        _require(type(query) is dict and set(query) == {"id", "split", "text", "text_truncated", "line", "source_sha256"}
                 and _text(query["id"], 80) and type(query["split"]) is str and query["split"] in staged.SPLITS
                 and type(query["text"]) is str and len(query["text"]) <= 4096
                 and type(query["text_truncated"]) is bool and (not query["text_truncated"] or len(query["text"]) == 4096)
                 and type(query["line"]) is int and query["line"] > 0 and _hash(query["source_sha256"]),
                 "Invalid saved staged query or source locator.", code)
        _require(_text(material["action_id"], 160) and _hash(material["result_sha256"]), "Invalid saved action identity.", code)
        identity = (material["action_id"], query["split"], query["id"])
        _require(identity not in seen and len(seen) < MAX_RETRIEVAL_SELECTORS, "Use at most four distinct saved queries.", code)
        selection = context["selection_context"]
        bfields = {"project_id", "snapshot_ref", "action_id", "result_sha256", "source_snapshot_sha256", "primary_action_id", "primary_result_sha256"}
        _require(type(binding) is dict and set(binding) == bfields and binding["project_id"] == selection["project_id"]
                 and binding["snapshot_ref"] == selection["snapshot_ref"]
                 and binding["source_snapshot_sha256"] == selection["source_snapshot_sha256"]
                 and binding["action_id"] == binding["primary_action_id"] == material["action_id"]
                 and binding["result_sha256"] == binding["primary_result_sha256"] == material["result_sha256"],
                 "Saved staged action, source or snapshot differs.", code)
        _require(type(origin) is dict and set(origin) == {"source_file_sha256", "producer_code_identity", "reader_implementation_sha256"}
                 and all(_hash(v) for v in origin.values()) and origin["producer_code_identity"] == selection["project_code_identity"],
                 "Saved staged producer or reader identity differs.", code)
        saved_action = feedback.get(material["action_id"], {})
        _require(type(producer) is dict and set(producer) == {"request_id", "method_id", "code_identity", "evaluation_ref"}
                 and producer["method_id"] == staged.TOOL_ID == saved_action.get("method_id")
                 and producer["request_id"] == saved_action.get("request_id") and _text(producer["request_id"], 160)
                 and producer["code_identity"] == origin["producer_code_identity"]
                 and producer["evaluation_ref"] == evaluation_ref(staged.TOOL_ID)
                 and saved_action.get("status") == "completed" and material["artifact_ref"] == saved_action.get("artifact_ref")
                 and material["artifact_ref"] == "artifacts/" + material["action_id"] + ".json",
                 "Saved staged primary feedback or producer differs.", code)
        contract = {"id": staged.CONTRACT, "stage": "development", "baseline": "bm25", "candidate": "tfidf_cosine",
                    "qrels_semantics": "positive_relevance_binary_projection", "missing_document_policy": "retain_in_denominator",
                    "ignore_identical_ids": True}
        assets = selection["domain_scope"]["input_identities"]
        _require(canonical(material["contract"]) == canonical(contract) and type(assets) is dict
                 and all(type(assets.get(k)) is dict for k in ("queries", "corpus", "qrels"))
                 and query["source_sha256"] == assets["queries"].get("sha256")
                 and _hash(material["corpus_source_sha256"])
                 and material["corpus_source_sha256"] == assets["corpus"].get("sha256"),
                 "Saved staged development contract or input differs.", code)
        arms = material["arms"]
        _require(type(arms) is list and len(arms) == 2 and all(type(a) is dict for a in arms)
                 and [a.get("method") for a in arms] == ["bm25", "tfidf_cosine"], "Both saved arms are required.", code)
        excerpt_docs = {}
        for arm in arms:
            _require(set(arm) == {"method", "metrics", "qrel", "ranking", "top_documents"}, "Invalid saved arm.", code)
            metrics, qrel, ranking, top = (arm[k] for k in ("metrics", "qrel", "ranking", "top_documents"))
            _require(type(metrics) is dict and set(metrics) == set(legacy.METRICS)
                     and all(type(x) in (int, float) and math.isfinite(x) and 0 <= x <= 1 for x in metrics.values()),
                     "Saved metrics must be finite and bounded.", code)
            _require(type(qrel) is dict and set(qrel) == {"doc_ids", "source_sha256", "role", "grades", "missing_doc_ids"}
                     and qrel["role"] == "qrels" and qrel["source_sha256"] == assets["qrels"].get("sha256")
                     and _hash(qrel["source_sha256"]) and type(qrel["doc_ids"]) is list
                     and len(qrel["doc_ids"]) <= staged.LIMITS["max_qrel_pairs"]
                     and all(_text(doc, 80) for doc in qrel["doc_ids"]) and qrel["doc_ids"] == sorted(set(qrel["doc_ids"]))
                     and type(qrel["grades"]) is dict and set(qrel["grades"]) == set(qrel["doc_ids"])
                     and all(type(v) is int and v in (1, 2) for v in qrel["grades"].values())
                     and type(qrel["missing_doc_ids"]) is list and qrel["missing_doc_ids"] == sorted(set(qrel["missing_doc_ids"]))
                     and all(doc in qrel["doc_ids"] for doc in qrel["missing_doc_ids"]), "Saved qrel grades or source differ.", code)
            _require(type(ranking) is list and len(ranking) <= 20
                     and all(type(d) is dict and set(d) == {"rank", "id", "line"} and type(d["rank"]) is int
                             and _text(d["id"], 80) and type(d["line"]) is int and d["line"] > 0 for d in ranking)
                     and [d["rank"] for d in ranking] == list(range(1, len(ranking) + 1))
                     and len({d["id"] for d in ranking}) == len(ranking)
                     and query["id"] not in {d["id"] for d in ranking}, "Saved ranking differs.", code)
            _require(type(top) is list and len(top) == min(3, len(ranking)), "Only the first three saved documents are included.", code)
            for doc, rank in zip(top, ranking):
                dfields = {"rank", "id", "title", "text", "title_truncated", "text_truncated", "line", "source_sha256", "relevant", "original_grade"}
                _require(type(doc) is dict and set(doc) == dfields and type(doc["rank"]) is int and type(doc["line"]) is int
                         and all(doc[k] == rank[k] for k in ("rank", "id", "line"))
                         and type(doc["title"]) is str and len(doc["title"]) <= 512
                         and type(doc["text"]) is str and len(doc["text"]) <= 4096
                         and type(doc["title_truncated"]) is bool and (not doc["title_truncated"] or len(doc["title"]) == 512)
                         and type(doc["text_truncated"]) is bool and (not doc["text_truncated"] or len(doc["text"]) == 4096)
                         and doc["source_sha256"] == material["corpus_source_sha256"]
                         and type(doc["relevant"]) is bool and doc["relevant"] == (doc["id"] in qrel["grades"])
                         and (doc["original_grade"] is None or type(doc["original_grade"]) is int)
                         and doc["original_grade"] == qrel["grades"].get(doc["id"]) and doc["id"] not in qrel["missing_doc_ids"],
                         "Document excerpt must match the saved rank, labels and source.", code)
                previous = excerpt_docs.get(doc["id"])
                content = {k: v for k, v in doc.items() if k != "rank"}
                _require(previous is None or previous == content, "Shared document excerpts differ between arms.", code)
                excerpt_docs[doc["id"]] = content
        _require(arms[0]["qrel"] == arms[1]["qrel"], "Both arms must retain the same labels.", code)
        baseline, candidate = arms[0]["metrics"], arms[1]["metrics"]
        category = ("metric_loss" if any(candidate[k] - baseline[k] < -1e-12 for k in legacy.METRICS)
                    else "no_metric_loss_both_incomplete" if baseline["recall@20"] < 1 and candidate["recall@20"] < 1
                    else "no_metric_loss_baseline_only_incomplete" if baseline["recall@20"] < 1 and candidate["recall@20"] == 1
                    else "no_metric_loss_other")
        _require(material["category"] == category and (category != "no_metric_loss_other" or min(baseline["recall@20"], candidate["recall@20"]) < 1),
                 "Saved adverse category differs.", code)
        seen.add(identity)
    except ResearchError:
        raise
    except (KeyError, TypeError, ValueError, OverflowError, RecursionError):
        raise ResearchError(code, "Malformed staged saved query material.") from None


def _stability_material(project, state, action, request):
    from . import staged_feedback_reader as reader, staged_relevance_adapter as staged
    _require(action.get("command") == staged.TOOL_ID and action.get("status") == "completed",
             "Stability material requires the original completed staged primary.")
    value = reader.read_validation_stability(project, state, action_id=action["id"])
    binding = value["binding"]
    _require(binding["project_id"] == state["id"] and binding["snapshot_ref"] == state["snapshot_ref"]
             and binding["source_snapshot_sha256"] == state["source_snapshot_sha256"]
             and binding["action_id"] == binding["primary_action_id"] == action["id"]
             and binding["result_sha256"] == binding["primary_result_sha256"] == request["result_sha256"]
             and value["origin"]["producer_code_identity"] == action["code_identity"],
             "Saved stability source, producer, primary or snapshot differs.")
    return {"kind": STABILITY_KIND, "action_id": action["id"], "result_sha256": action["result_sha256"],
            "artifact_ref": action["artifact"], "binding": copy.deepcopy(binding), "origin": copy.deepcopy(value["origin"]),
            "producer": {"request_id": action["request_id"], "method_id": action["command"],
                         "code_identity": action["code_identity"], "evaluation_ref": action["method_instance"]["evaluation_ref"]},
            "contract": copy.deepcopy(value["contract"]), "metrics": copy.deepcopy(value["metrics"]),
            "coverage": "all_saved_validation_pairs; leave_one_out_when_possible",
            "source_text_included": False, "scientific_validation": False}


def _validate_stability_material(context, material, feedback, seen):
    from . import staged_feedback_reader as reader, staged_relevance_adapter as staged
    from .method_registry import evaluation_ref
    code = "INVALID_PLAN_CONTEXT"
    try:
        fields = {"kind", "action_id", "result_sha256", "artifact_ref", "binding", "origin", "producer",
                  "contract", "metrics", "coverage", "source_text_included", "scientific_validation"}
        _require(type(material) is dict and set(material) == fields and material["kind"] == STABILITY_KIND
                 and material["coverage"] == "all_saved_validation_pairs; leave_one_out_when_possible"
                 and material["source_text_included"] is False and material["scientific_validation"] is False
                 and _text(material["action_id"], 160) and _hash(material["result_sha256"]),
                 "Use exact saved staged stability material.", code)
        identity = (material["action_id"], None, None)
        _require(identity not in seen and len(seen) < MAX_RETRIEVAL_SELECTORS,
                 "Use at most four distinct saved retrieval selectors.", code)
        selection = context["selection_context"]; binding = material["binding"]; origin = material["origin"]
        fields = {"project_id", "snapshot_ref", "action_id", "result_sha256", "source_snapshot_sha256",
                  "primary_action_id", "primary_result_sha256"}
        _require(type(binding) is dict and set(binding) == fields and binding["project_id"] == selection["project_id"]
                 and binding["snapshot_ref"] == selection["snapshot_ref"]
                 and binding["source_snapshot_sha256"] == selection["source_snapshot_sha256"]
                 and binding["action_id"] == binding["primary_action_id"] == material["action_id"]
                 and binding["result_sha256"] == binding["primary_result_sha256"] == material["result_sha256"],
                 "Saved stability source or snapshot differs.", code)
        _require(type(origin) is dict and set(origin) == {"source_file_sha256", "producer_code_identity", "reader_implementation_sha256"}
                 and all(_hash(v) for v in origin.values()) and origin["producer_code_identity"] == selection["project_code_identity"],
                 "Saved stability producer or reader differs.", code)
        producer = material["producer"]; action = feedback.get(material["action_id"], {})
        _require(type(producer) is dict and set(producer) == {"request_id", "method_id", "code_identity", "evaluation_ref"}
                 and producer["method_id"] == staged.TOOL_ID == action.get("method_id")
                 and producer["request_id"] == action.get("request_id") and _text(producer["request_id"], 160)
                 and producer["code_identity"] == origin["producer_code_identity"]
                 and producer["evaluation_ref"] == evaluation_ref(staged.TOOL_ID) and action.get("status") == "completed"
                 and material["artifact_ref"] == action.get("artifact_ref") == "artifacts/" + material["action_id"] + ".json",
                 "Saved stability feedback or producer differs.", code)
        contract = {"id": staged.CONTRACT, "split": "validation", "baseline": "bm25",
                    "candidate": "tfidf_cosine", "epsilon": reader.STABILITY_EPSILON}
        _require(canonical(material["contract"]) == canonical(contract)
                 and selection["domain_scope"].get("contract") == staged.CONTRACT
                 and selection["domain_scope"].get("stage") == "development",
                 "Saved stability contract differs.", code)
        try:
            reader.validate_stability_aggregate(material["metrics"])
        except ResearchError:
            raise ResearchError(code, "Malformed saved stability aggregate.") from None
        expected_n = selection["domain_scope"].get("query_split_counts", {}).get("validation")
        _require(type(expected_n) is int and all(item["queries"] == expected_n for item in material["metrics"].values()),
                 "Saved stability validation coverage differs.", code)
        seen.add(identity)
    except ResearchError:
        raise
    except (KeyError, TypeError, ValueError, OverflowError, RecursionError):
        raise ResearchError(code, "Malformed saved stability material.") from None
