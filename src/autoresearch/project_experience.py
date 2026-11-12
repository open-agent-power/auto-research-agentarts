"""Numerically checked project OOF cases, exported as explicit advisory snapshots."""
import copy
import hashlib
import math
from pathlib import Path
import re

from .contracts import ResearchError, canonical, fingerprint, identifier
from . import method_registry as registry, research_recipe
from .feature_comparison import compare_feature_pair, _paired_errors
from .input_basis import protocol as input_protocol
from .prediction_summary import summarize_oof_range
from .project_design import MAX_RAW_RECORDS, validate_resource
from .research_memory import ResearchMemory, observation_id, validate_scope
from .research_project import ResearchProject

MAX_BUNDLE_BYTES = 4 * 1024 * 1024
PROTOCOL = "project-saved-oof-arithmetic-v1"
PARENT_PROTOCOL = "project-saved-oof-parent-comparison-v1"
BUNDLE_FIELDS = {"schema_version", "id", "version", "record", "method_card", "limitations",
                 "source_inclusion_status", "scientific_validation"}
ENTRY_FIELDS = {"schema_version", "id", "kind", "scope", "review_status", "numerical_recomputation", "payload", "provenance"}


def _require(condition, message, code="INVALID_PROJECT_EXPERIENCE"):
    if not condition:
        raise ResearchError(code, message)


def _hash(value):
    return type(value) is str and re.fullmatch(r"[a-f0-9]{64}", value) is not None


def _near(actual, expected, message):
    _require(type(actual) in (int, float) and math.isfinite(actual)
             and math.isclose(actual, expected, rel_tol=1e-10, abs_tol=1e-10), message, "EVIDENCE_CHANGED")


def _checked_artifact(action, envelope, origin):
    _require(type(action) is dict and action.get("status") == "completed" and type(action.get("command")) is str
             and action.get("command") in registry.RIDGE, "Only completed registered Ridge OOF actions are supported.")
    _require(type(envelope) is dict and envelope.get("sha256") == action.get("result_sha256")
             and envelope["sha256"] == fingerprint({k: v for k, v in envelope.items() if k != "sha256"})
             and envelope.get("action_id") == action.get("id")
             and envelope.get("request_sha256") == action.get("request_sha256")
             and envelope.get("code_identity") == action.get("code_identity")
             and envelope.get("source_snapshot_sha256") == origin["source_snapshot_sha256"],
             "Original project action, artifact and producer identities differ.", "EVIDENCE_CHANGED")
    tool = envelope.get("tool_result", {})
    _require(type(tool) is dict and tool.get("tool_id") == action["command"] and tool.get("status") == "completed"
             and tool.get("scientific_validation") is False, "Require the completed unapproved Ridge result.", "EVIDENCE_CHANGED")
    result = tool.get("result")
    _require(type(result) is dict and type(result.get("analysis")) is dict, "Require the saved Ridge analysis.", "EVIDENCE_CHANGED")
    analysis = result["analysis"]
    expected_check = "group_cv" if action["command"] == "data.ridge-group-validation" else "random_cv"
    _require(analysis.get("schema_version") == "ridge-validation-v1" and analysis.get("check") == expected_check
             and analysis.get("source_snapshot_sha256") == origin["source_snapshot_sha256"]
             and analysis.get("target_column") == origin["source_scope"].get("target_column")
             and analysis.get("target_unit") == origin["source_scope"].get("target_unit")
             and analysis.get("scientific_validation") is False,
             "OOF source, check or target scope differs from the captured origin.", "EVIDENCE_CHANGED")
    return analysis


def _checked_rows(analysis):
    rows, exclusions, saved = analysis.get("oof"), analysis.get("exclusions"), analysis.get("summary", {})
    _require(type(rows) is list and 1 <= len(rows) <= MAX_RAW_RECORDS and type(exclusions) is list and type(saved) is dict
             and saved.get("status") == "computed", "Require complete computable saved OOF rows.")
    by_id = {}
    for row in rows:
        _require(type(row) is dict and type(row.get("logical_record")) is int
                 and row["logical_record"] >= 1 and row["logical_record"] not in by_id
                 and type(row.get("physical_line_end")) is int and row["physical_line_end"] >= 2
                 and type(row.get("fold")) is int and row["fold"] >= 1
                 and (row.get("groups") is None or type(row["groups"]) is list
                      and all(type(group) is str for group in row["groups"]))
                 and all(type(row.get(key)) in (int, float) and math.isfinite(row[key])
                         for key in ("observed", "predicted", "reference_prediction")),
                 "Saved OOF coordinates or finite values are invalid.", "EVIDENCE_CHANGED")
        by_id[row["logical_record"]] = row
    excluded = [row.get("logical_record") for row in exclusions if type(row) is dict]
    _require(all(type(value) is int and value >= 1 for value in excluded)
             and len(excluded) == len(exclusions) == len(set(excluded))
             and set(excluded).isdisjoint(by_id)
             and type(saved.get("input_n")) is int and 1 <= saved["input_n"] <= MAX_RAW_RECORDS
             and set(excluded) | set(by_id) == set(range(1, saved["input_n"] + 1))
             and saved.get("n") == len(rows) and saved.get("excluded") == len(exclusions),
             "Original OOF coverage and exclusions differ.", "EVIDENCE_CHANGED")
    return rows, by_id


def _check_folds(analysis, by_id):
    folds, protocol = analysis.get("folds"), analysis.get("protocol", {})
    _require(type(folds) is list and type(protocol) is dict and len(folds) == protocol.get("n_splits") and 2 <= len(folds) <= 5
             and protocol.get("reference") == "training-fold target mean", "Require the fixed saved validation folds.")
    tested = []
    for expected, fold in enumerate(folds, 1):
        _require(type(fold) is dict, "Saved fold is not an object.", "EVIDENCE_CHANGED")
        train, test = fold.get("train_records"), fold.get("test_records")
        _require(fold.get("fold") == expected and type(train) is list and type(test) is list
                 and train and test and all(type(index) is int for index in [*train, *test])
                 and len(train) == len(set(train)) and len(test) == len(set(test))
                 and set(train).isdisjoint(test) and set(train) | set(test) == set(by_id),
                 "Saved training and evaluation sets do not partition the complete cases.", "EVIDENCE_CHANGED")
        mean = math.fsum(by_id[index]["observed"] for index in train) / len(train)
        _near(fold.get("reference_prediction"), mean, "The saved reference is not the training-fold target mean.")
        for index in test:
            _require(by_id[index]["fold"] == expected, "OOF membership differs from its saved fold.", "EVIDENCE_CHANGED")
            _near(by_id[index]["reference_prediction"], mean, "OOF reference differs from its training-fold mean.")
        if analysis["check"] == "group_cv":
            train_groups = {tuple(by_id[index].get("groups") or []) for index in train}
            test_groups = {tuple(by_id[index].get("groups") or []) for index in test}
            _require(not train_groups.intersection(test_groups), "Declared groups cross the saved group split.", "EVIDENCE_CHANGED")
        tested.extend(test)
    _require(len(tested) == len(by_id) and set(tested) == set(by_id), "Every complete row must be evaluated exactly once.", "EVIDENCE_CHANGED")


def _payload(action, envelope, origin):
    analysis = _checked_artifact(action, envelope, origin)
    rows, by_id = _checked_rows(analysis)
    _check_folds(analysis, by_id)
    mae = math.fsum(abs(row["observed"] - row["predicted"]) for row in rows) / len(rows)
    reference = math.fsum(abs(row["observed"] - row["reference_prediction"]) for row in rows) / len(rows)
    _require(reference > 0, "A zero-reference result is not a computable experience case.")
    saved = analysis["summary"]
    for key, expected in (("candidate_mae", mae), ("reference_mae", reference), ("improvement", 1 - mae / reference)):
        _near(saved.get(key), expected, "Saved OOF arithmetic differs: " + key)
    _require(saved.get("outperforms_reference") is (mae < reference), "Saved reference comparison differs.", "EVIDENCE_CHANGED")
    numerical = {**copy.deepcopy(saved), "negative_predictions": sum(row["predicted"] < 0 for row in rows),
                 "observed_min": min(row["observed"] for row in rows), "observed_max": max(row["observed"] for row in rows),
                 "predicted_min": min(row["predicted"] for row in rows), "predicted_max": max(row["predicted"] for row in rows)}
    return {"schema_version": "project-oof-experience-v1", "method_id": action["command"],
            "evaluation_ref": action["evaluation_ref"], "source_scope": copy.deepcopy(origin["source_scope"]),
            "check": analysis["check"], "protocol": copy.deepcopy(analysis["protocol"]),
            "numerical_summary": numerical, "exclusions": copy.deepcopy(analysis["exclusions"]),
            "target_column": analysis["target_column"], "target_unit": analysis["target_unit"],
            "origin_limitations": copy.deepcopy(analysis.get("limitations", [])),
            "numerical_validation": "saved_oof_arithmetic_only_not_refitting_or_scientific_review"}


def _paired_binding(action, analysis, origin, state=None):
    binding = action.get("design_binding")
    _require(type(binding) is dict and type(binding.get("version")) is int
             and binding == analysis.get("design_binding")
             and binding.get("project_id") == origin["project_id"]
             and binding.get("source_snapshot_sha256") == origin["source_snapshot_sha256"]
             and binding.get("target_column") == origin["source_scope"]["target_column"]
             and binding.get("prediction_column") is None,
             "The original action, analysis and project design binding differ.", "EVIDENCE_CHANGED")
    if state is not None:
        revisions = [item for item in state.get("design_revisions", []) if item.get("version") == binding["version"]]
        _require(revisions == [binding], "The action does not match its unique registered historical design.", "EVIDENCE_CHANGED")
    training, saved = binding.get("training"), analysis["protocol"]
    _require(type(training) is dict and type(training.get("feature_columns")) is list
             and training["feature_columns"] and type(training.get("split_group_columns")) is list
             and saved.get("feature_columns") == training["feature_columns"]
             and saved.get("split_group_columns") == training["split_group_columns"]
             and all(type(row["groups"]) is list and len(row["groups"]) == len(training["split_group_columns"])
                     if training["split_group_columns"] else row["groups"] is None for row in analysis["oof"]),
             "The original training columns and saved protocol differ.", "EVIDENCE_CHANGED")
    expected = input_protocol(training)
    _require({key: saved[key] for key in ("input_basis", "model_input_terms") if key in saved} == expected,
             "The saved input mapping differs from its declared fixed training mapping.", "EVIDENCE_CHANGED")
    resource = validate_resource(binding.get("resource"))
    _require(analysis["check"] in resource["checks"] and type(action.get("evaluation_ref")) is str
             and 0 < len(action["evaluation_ref"]) <= 1000
             and all(type(fold.get("model_params")) is dict for fold in analysis["folds"]),
             "The action must preserve its authorized raw validation and estimator parameters.", "EVIDENCE_CHANGED")
    group_count = len({tuple(row["groups"] or []) for row in analysis["oof"]}) if training["split_group_columns"] else None
    _require(analysis["summary"].get("group_count") == group_count,
             "The saved group count differs from the complete OOF grouping.", "EVIDENCE_CHANGED")
    return {**analysis, "action_id": action["id"], "status": action["status"]}


def _paired_payload(action, artifact, parent, origin, state=None):
    payload = _payload(action, artifact, origin)
    _require(type(parent) is dict and set(parent) == {"action_id", "action", "artifact"}
             and type(parent["action"]) is dict and parent["action_id"] == parent["action"].get("id")
             and _hash(parent["action"].get("code_identity"))
             and parent["action_id"] != action["id"], "Select a distinct explicitly saved parent action.", "EVIDENCE_CHANGED")
    _payload(parent["action"], parent["artifact"], origin)
    records = [_paired_binding(item, envelope["tool_result"]["result"]["analysis"], origin, state)
               for item, envelope in ((parent["action"], parent["artifact"]), (action, artifact))]
    comparison = compare_feature_pair(*records)
    _require(comparison["status"] == "comparable",
             "The explicitly selected parent is not the same saved evaluation: " + ", ".join(comparison["reason_codes"]),
             "EVIDENCE_CHANGED")
    right = {row["logical_record"]: row for row in records[1]["oof"]}
    pairs = [(row, right[row["logical_record"]]) for row in records[0]["oof"]]
    counts = _paired_errors(pairs)
    comparison["row_summary"] = {key: counts[key] for key in ("n", "improved_rows", "worsened_rows", "tied_rows")}
    groups = {}
    if records[1]["protocol"]["split_group_columns"]:
        for pair in pairs:
            groups.setdefault(tuple(pair[0]["groups"]), []).append(pair)
    changes = [_paired_errors(group)["mae_change"] for group in groups.values()]
    comparison["group_summary"] = ({"group_count": len(changes), "improved_groups": sum(value < 0 for value in changes),
        "worsened_groups": sum(value > 0 for value in changes), "tied_groups": sum(value == 0 for value in changes)} if groups else None)
    comparison["prediction_ranges"] = {name: summarize_oof_range(record["oof"])
                                        for name, record in zip(("baseline", "candidate"), records)}
    payload["saved_parent_comparison"] = comparison
    return payload


def _result_scope(artifact, parent=None):
    return (artifact["sha256"] if parent is None else fingerprint({"candidate_result_sha256": artifact["sha256"],
                                                                  "parent_result_sha256": parent["artifact"]["sha256"]}))


def derive_project_observation(workspace, action_id, *, parent_action_id=None):
    project = ResearchProject(workspace)
    before = project.status()
    source = project._source(before)
    _require(source["snapshot_sha256"] == before["source_snapshot_sha256"] and source["scope"] == before["source_scope"],
             "Captured source and registered origin scope differ.", "EVIDENCE_CHANGED")
    action = next((item for item in before["actions"] if item["id"] == action_id), None)
    _require(action is not None, "Select an action actually saved in the source project.")
    raw = project._artifact(action).read_bytes()
    envelope = research_recipe.parse_json(raw, maximum=len(raw), code="EVIDENCE_CHANGED")
    origin = {"project_id": before["id"], "state_version": before["state_version"], "snapshot_ref": before["snapshot_ref"],
              "source_snapshot_sha256": before["source_snapshot_sha256"], "source_scope": before["source_scope"],
              "current_project_code_identity": before["code_identity"], "producer_code_identity": action["code_identity"],
              "captured_data_sha256": source["source"]["sha256"]}
    parent = None
    if parent_action_id is not None:
        parent_action = next((item for item in before["actions"] if item["id"] == parent_action_id), None)
        _require(parent_action is not None, "Select a parent action actually saved in the same source project.")
        parent_raw = project._artifact(parent_action).read_bytes()
        parent = {"action_id": parent_action_id, "action": copy.deepcopy(parent_action),
                  "artifact": research_recipe.parse_json(parent_raw, maximum=len(parent_raw), code="EVIDENCE_CHANGED")}
    payload = _payload(action, envelope, origin) if parent is None else _paired_payload(action, envelope, parent, origin, before)
    protocol = PROTOCOL if parent is None else PARENT_PROTOCOL
    scope = {"source_manifest_sha256": before["source_snapshot_sha256"], "inputs_sha256": _result_scope(envelope, parent),
             "analysis_code_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(), "protocol": protocol}
    action_fields = ("id", "request_id", "command", "status", "request_sha256", "code_identity", "result_sha256", "evaluation_ref")
    if parent is not None:
        action_fields += ("design_binding",)
        parent["action"] = {key: copy.deepcopy(parent["action"][key]) for key in action_fields}
    provenance = {"action_id": action_id, "source_record_sha256": fingerprint(before),
                  "origin": copy.deepcopy(origin), "action": {key: copy.deepcopy(action[key]) for key in action_fields},
                  "artifact": envelope, "recomputation_scope": copy.deepcopy(scope)}
    if parent is not None:
        provenance["parent"] = parent
    entry = {"schema_version": "conditional-research-memory-v1", "kind": "fit_observation", "scope": scope,
             "review_status": "derived_not_scientifically_reviewed", "numerical_recomputation": True,
             "payload": payload, "provenance": provenance}
    entry["id"] = observation_id(entry)
    _require(project.status() == before, "Source project changed while deriving an experience.", "STALE_STATE")
    return {"scope": scope, "entries": [entry], "validation": {"protocol": protocol, "saved_oof_rows": payload["numerical_summary"]["n"],
            "fit_calls": 0, "scientific_validation": False}}


def _validate_record(record):
    _require(type(record) is dict and set(record) == ENTRY_FIELDS
             and record["schema_version"] == "conditional-research-memory-v1" and record["kind"] == "fit_observation"
             and record["review_status"] == "derived_not_scientifically_reviewed" and record["numerical_recomputation"] is True,
             "Use the original numerically checked project memory record.")
    scope = validate_scope(record["scope"])
    _require(set(scope) == {"source_manifest_sha256", "inputs_sha256", "analysis_code_sha256", "protocol"}
             and scope["protocol"] in (PROTOCOL, PARENT_PROTOCOL) and observation_id(record) == record["id"], "Project arithmetic memory scope or identity differs.")
    provenance = record["provenance"]
    fields = {"action_id", "source_record_sha256", "origin", "action", "artifact", "recomputation_scope"}
    if scope["protocol"] == PARENT_PROTOCOL:
        fields.add("parent")
    _require(type(provenance) is dict and set(provenance) == fields
             and _hash(provenance["source_record_sha256"]) and provenance["recomputation_scope"] == scope,
             "Use the original project provenance and arithmetic scope.")
    origin, action, artifact = provenance["origin"], provenance["action"], provenance["artifact"]
    _require(type(origin) is dict and set(origin) == {"project_id", "state_version", "snapshot_ref", "source_snapshot_sha256", "source_scope",
             "current_project_code_identity", "producer_code_identity", "captured_data_sha256"}
             and type(origin["state_version"]) is int and origin["state_version"] >= 0
             and all(_hash(origin[key]) for key in ("snapshot_ref", "source_snapshot_sha256", "current_project_code_identity", "producer_code_identity", "captured_data_sha256"))
             and type(origin["source_scope"]) is dict
             and all(type(origin["source_scope"].get(key)) is str and origin["source_scope"][key].strip() for key in ("domain", "contract")),
             "Origin project identity and source scope are required.")
    identifier(origin["project_id"], "origin_project_id")
    _require(type(action) is dict and type(artifact) is dict and provenance["action_id"] == action.get("id")
             and action.get("code_identity") == origin["producer_code_identity"]
             and type(action.get("evaluation_ref")) is str and 0 < len(action["evaluation_ref"]) <= 1000
             and scope["source_manifest_sha256"] == origin["source_snapshot_sha256"],
             "Origin result and method identities differ.", "EVIDENCE_CHANGED")
    parent = provenance.get("parent")
    payload = (_payload(action, artifact, origin) if scope["protocol"] == PROTOCOL
               else _paired_payload(action, artifact, parent, origin))
    _require(scope["inputs_sha256"] == _result_scope(artifact, parent)
             and payload == record["payload"], "Immutable experience values differ from recomputed source observations.", "EVIDENCE_CHANGED")


def validate_bundle(bundle):
    _require(type(bundle) is dict and set(bundle) == BUNDLE_FIELDS
             and bundle["schema_version"] == "project-experience-bundle-v1" and bundle["scientific_validation"] is False
             and bundle["source_inclusion_status"] == "active_at_export"
             and type(bundle["version"]) is int and 1 <= bundle["version"] <= 2**31 - 1,
             "Use the exact unapproved experience snapshot bundle fields.")
    identifier(bundle["id"], "case_id")
    _validate_record(bundle["record"])
    card = research_recipe.validate_method_card(bundle["method_card"])
    payload = bundle["record"]["payload"]
    _require(card["scope_match"] == {key: payload["source_scope"][key] for key in ("domain", "contract")}
             and card["method_refs"] == [{"method_id": payload["method_id"], "evaluation_ref": payload["evaluation_ref"]}],
             "The advisory method card must describe this original method and source contract.")
    limits = bundle["limitations"]
    _require(type(limits) is list and 1 <= len(limits) <= 8
             and all(type(value) is str and 0 < len(value.strip()) <= 4000 and "\x00" not in value for value in limits),
             "Provide one to eight explicit limitations for transfer.")
    _require(len(canonical(bundle).encode("utf-8")) <= MAX_BUNDLE_BYTES, "Experience bundle exceeds 4 MiB.")
    return copy.deepcopy(bundle)


def parse_bundle(raw):
    return validate_bundle(research_recipe.parse_json(raw, maximum=MAX_BUNDLE_BYTES, code="INVALID_PROJECT_EXPERIENCE"))


def summary(bundle):
    bundle = validate_bundle(bundle)
    record, payload = bundle["record"], bundle["record"]["payload"]
    provenance, origin = record["provenance"], record["provenance"]["origin"]
    result = {"case_id": bundle["id"], "case_version": bundle["version"], "entry_id": record["id"],
            "method_card": bundle["method_card"], "origin_evidence": {**{key: origin[key] for key in
                ("project_id", "state_version", "snapshot_ref", "source_snapshot_sha256", "producer_code_identity")},
                "action_id": provenance["action_id"], "result_sha256": provenance["action"]["result_sha256"],
                "recomputation_scope": copy.deepcopy(record["scope"])},
            "source_scope": payload["source_scope"], "observation": {key: payload[key] for key in
                ("check", "protocol", "numerical_summary", "exclusions")},
            "limitations": [*payload["origin_limitations"], *bundle["limitations"]],
            "transfer_scope": "analogy_not_current_evidence", "scientific_validation": False}
    if "saved_parent_comparison" in payload:
        result["observation"]["saved_parent_comparison"] = copy.deepcopy(payload["saved_parent_comparison"])
        parent = provenance["parent"]
        result["origin_evidence"].update(parent_action_id=parent["action_id"],
            parent_result_sha256=parent["action"]["result_sha256"], parent_producer_code_identity=parent["action"]["code_identity"])
    return result


class ProjectExperienceMemory(ResearchMemory):
    def import_project(self, workspace, action_id, *, parent_action_id=None):
        return self._import_derived(derive_project_observation(workspace, action_id, parent_action_id=parent_action_id))

    def export_case(self, scope, entry_id, *, case_id, version, method_card, limitations):
        validate_scope(scope)
        with self._connect() as con:
            row = con.execute("SELECT * FROM entries WHERE id=?", (entry_id,)).fetchone() if con is not None else None
            _require(row is not None, "No source memory entry matches this identity.", "NOT_FOUND")
            record = self._verify(con, row)
            _require(record["scope"] == scope, "Export requires the source's exact arithmetic scope.", "INVALID_SCOPE")
            _require(row["status"] == "active", "The source memory entry is retired; do not export a new active snapshot.", "EXPERIENCE_RETIRED")
            return validate_bundle({"schema_version": "project-experience-bundle-v1", "id": case_id, "version": version,
                "record": record, "method_card": method_card, "limitations": limitations,
                "source_inclusion_status": "active_at_export", "scientific_validation": False})
