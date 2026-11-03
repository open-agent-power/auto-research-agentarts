"""Grouped mechanical quality counts over an unchanged, captured tabular source."""

from array import array
import copy
import hashlib
import math
from pathlib import Path
import re

from . import tabular_quality_adapter as tabular
from .contracts import ResearchError, fingerprint, identifier

TOOL_ID = "data.grouped-quality-profile"
ADAPTER_VERSION = "1"
COUNTS_ORDER = ("finite", "zero", "empty", "declared_missing", "invalid_numeric", "nonfinite")
EVENTS = COUNTS_ORDER[1:]


def _require(condition, code, message):
    if not condition:
        raise ResearchError(code, message)


def _parameters(parameters):
    _require(type(parameters) is dict and set(parameters) == {"based_on_action_id", "based_on_result_sha256"},
             "INVALID_REQUEST", "Exact saved-predecessor references are required.")
    identifier(parameters["based_on_action_id"], "based_on_action_id")
    digest = parameters["based_on_result_sha256"]
    _require(type(digest) is str and re.fullmatch(r"[a-f0-9]{64}", digest),
             "INVALID_REQUEST", "A complete saved-predecessor result SHA-256 is required.")
    return copy.deepcopy(parameters)


def code_identity() -> str:
    return hashlib.sha256(Path(__file__).read_bytes() + tabular.code_identity().encode("ascii")).hexdigest()


def _classify(token, missing):
    if token == "":
        return "empty", False
    if token in missing:
        return "declared_missing", False
    try:
        value = float(token)
        return ("finite", value == 0) if math.isfinite(value) else ("nonfinite", False)
    except (ValueError, OverflowError):
        return "invalid_numeric", False


def _counts(values, offset):
    return {name: values[offset + index] for index, name in enumerate(COUNTS_ORDER)}


def execute(payload, parameters) -> dict:
    """References are supplied by the host; only ResearchProject verifies their saved binding."""
    predecessor = _parameters(parameters)
    spec, _, (header, records, physical_end) = tabular._checked(payload)
    _require(bool(spec["group_columns"]), "UNSUPPORTED_SCOPE", "Declared grouping columns are required.")
    positions = {name: index for index, name in enumerate(header)}
    missing, width = set(spec["missing_tokens"]), len(spec["numeric_columns"])
    totals, incomplete = array("I", [0]) * (width * 6), array("I", [0]) * (width * 6)
    groups_by_key, groups, examples = {}, [], []
    rows, incomplete_rows = len(records), 0
    for logical_record, (row, physical_line) in enumerate(records, 1):
        key = tuple(row[positions[name]] for name in spec["group_columns"])
        complete = not any(token in missing for token in key)
        if complete:
            group = groups_by_key.get(key)
            if group is None:
                group = {"group_id": "group-" + fingerprint(list(key)), "rows": 0,
                         "first_coordinate": {"logical_record": logical_record, "physical_line_end": physical_line},
                         "_counts": array("I", [0]) * (width * 6)}
                groups_by_key[key] = group
                groups.append(group)
            group["rows"] += 1
            selected, group_id = group["_counts"], group["group_id"]
        else:
            incomplete_rows += 1
            selected, group_id = incomplete, None
        for column_index, name in enumerate(spec["numeric_columns"]):
            kind, zero = _classify(row[positions[name]], missing)
            offset = column_index * 6
            count_index = offset + COUNTS_ORDER.index(kind)
            selected[count_index] += 1
            totals[count_index] += 1
            if zero:
                selected[offset + 1] += 1
                totals[offset + 1] += 1
            if (kind != "finite" or zero) and len(examples) < 5:
                examples.append({"kind": "zero" if zero else kind, "column": name, "group_id": group_id,
                                 "logical_record": logical_record, "physical_line_end": physical_line})
    # Original rows and grouping values are not copied into result artifacts.
    groups_by_key.clear()
    del records
    numeric_summary = []
    for column_index, name in enumerate(spec["numeric_columns"]):
        offset = column_index * 6
        overall, incomplete_counts = _counts(totals, offset), _counts(incomplete, offset)
        complete_counts = {kind: sum(group["_counts"][offset + index] for group in groups)
                           for index, kind in enumerate(COUNTS_ORDER)}
        _require(all(overall[kind] == complete_counts[kind] + incomplete_counts[kind] for kind in COUNTS_ORDER)
                 and sum(overall[kind] for kind in COUNTS_ORDER if kind != "zero") == rows
                 and overall["zero"] <= overall["finite"], "INVALID_RESULT", "Grouped numeric subtotals differ from total records.")
        concentration = {}
        for kind in EVENTS:
            count_index = offset + COUNTS_ORDER.index(kind)
            affected = [(group["group_id"], group["_counts"][count_index]) for group in groups
                        if group["_counts"][count_index] > 0]
            affected.sort(key=lambda item: (-item[1], item[0]))
            total = complete_counts[kind]
            maximum = affected[0][1] if affected else 0
            concentration[kind] = {"total": total, "affected_groups": len(affected), "max_group_count": maximum,
                                   "max_group_share": maximum / total if total else None,
                                   "top_groups": [{"group_id": group_id, "count": count, "share": count / total}
                                                  for group_id, count in affected[:5]]}
        numeric_summary.append({"name": name, "totals": overall, "complete_group_totals": complete_counts,
                                "incomplete_group_totals": incomplete_counts, "concentration": concentration})
    complete_rows = sum(group["rows"] for group in groups)
    _require(complete_rows + incomplete_rows == rows and len(groups) <= 50_000,
             "INVALID_RESULT", "Grouped row totals differ from source records.")
    for group in groups:
        values = group.pop("_counts")
        group["numeric_counts"] = [list(values[index * 6:(index + 1) * 6]) for index in range(width)]
    summary = {"rows": rows, "complete_group_rows": complete_rows, "incomplete_group_rows": incomplete_rows,
               "group_count": len(groups), "numeric_columns": numeric_summary}
    scope = copy.deepcopy(payload["scope"])
    scope.update(contract="grouped-quality-profile-v1", input_contract=payload["scope"]["contract"])
    reference = {"source_snapshot_sha256": payload["snapshot_sha256"], "source_sha256": payload["source"]["sha256"],
                 "file_name": spec["file"], "url": spec["source_url"], "license_note": spec["license_note"],
                 "predecessor": copy.deepcopy(predecessor),
                 "locator": {"kind": "csv_logical_records", "first": 1 if rows else None, "last": rows or None,
                             "physical_line_end": physical_end}}
    result = {"schema_version": "grouped-quality-profile-v1", "source_snapshot_sha256": payload["snapshot_sha256"],
              "scope": scope, "predecessor": predecessor, "counts_order": list(COUNTS_ORDER),
              "group_columns": copy.deepcopy(spec["group_columns"]), "numeric_columns": copy.deepcopy(spec["numeric_columns"]),
              "summary": summary, "groups": groups,
              "incomplete_group": {"rows": incomplete_rows,
                                   "numeric_counts": [list(incomplete[index * 6:(index + 1) * 6]) for index in range(width)]},
              "examples": examples, "scientific_validation": False}
    return {"schema_version": "grouped-quality-profile-result-v1", "tool_id": TOOL_ID, "adapter_version": ADAPTER_VERSION,
            "status": "completed", "observations": [{"producer": TOOL_ID, "kind": "grouped_quality_profile",
                "summary": copy.deepcopy(summary), "scope": copy.deepcopy(scope), "predecessor": copy.deepcopy(predecessor),
                "examples": copy.deepcopy(examples), "evidence_refs": [copy.deepcopy(reference)],
                "interpretation_status": "mechanical_group_counts_not_cause_or_independence", "scientific_validation": False}],
            "metrics": [{"name": name, "value": summary[name], "unit": "count"}
                        for name in ("rows", "complete_group_rows", "incomplete_group_rows", "group_count")],
            "evidence_refs": [reference], "result": result, "failure": None,
            "scientific_validation": False, "new_fits": 0, "model_calls": 0}


def next_decision(result) -> dict:
    try:
        _require(result["tool_id"] == TOOL_ID and result["status"] == "completed" and result["scientific_validation"] is False
                 and result["new_fits"] == 0 and result["model_calls"] == 0
                 and result["result"]["schema_version"] == "grouped-quality-profile-v1",
                 "INVALID_RESULT", "A completed grouped mechanical profile is required.")
        summary = result["result"]["summary"]
        observed = [column["name"] + ":" + kind for column in summary["numeric_columns"] for kind in EVENTS
                    if column["totals"][kind] > 0]
        required = ["Original collection/group definitions and sample-unit records; grouped counts do not establish independence.",
                    "Confirm target meaning, unit, zero/missing rules, provenance and license against original records."]
        if observed:
            required.append("Explain the observed group distributions without changing or deleting original values: " + "; ".join(observed))
        if summary["incomplete_group_rows"]:
            required.append("Resolve the original grouping fields for records counted separately as incomplete groups.")
        return {"policy_ref": {"id": TOOL_ID, "version": ADAPTER_VERSION}, "project_status": "waiting",
                "next_action": {"kind": "evidence_task", "method_id": "research.source-selection", "execution_status": "not_executed",
                                "required_evidence": required},
                "reason": "Grouped zero and data-quality event counts are saved. Concentration is descriptive; causes, independent samples and scientific eligibility remain unconfirmed.",
                "source_snapshot_sha256": result["result"]["source_snapshot_sha256"],
                "predecessor": copy.deepcopy(result["result"]["predecessor"]),
                "evidence_refs": copy.deepcopy(result["evidence_refs"]), "scientific_validation": False, "new_fits": 0, "model_calls": 0}
    except ResearchError:
        raise
    except (KeyError, TypeError, ValueError):
        raise ResearchError("INVALID_RESULT", "Malformed grouped quality feedback.") from None
