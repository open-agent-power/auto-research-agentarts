"""Compare a captured CSV with candidate workbook cache projections, without approval."""

import copy
from decimal import Decimal, InvalidOperation
import hashlib
from pathlib import Path
import re

from . import archive_inventory, c01, chemotopo_data as workbook, tabular_quality_adapter as tabular
from .contracts import ResearchError, identifier

TOOL_ID = "data.workbook-projection-check"
ADAPTER_VERSION = "1"
EMPTY_CELL = {"value": None, "raw": "", "status": "missing", "formula_present": False, "formula": None}


def _require(condition, code, message):
    if not condition:
        raise ResearchError(code, message)


def _parameters(parameters):
    fields = {"based_on_action_id", "based_on_result_sha256", "origin_receipt_sha256", "origin_source_id"}
    _require(type(parameters) is dict and set(parameters) == fields,
             "INVALID_REQUEST", "Exact predecessor and captured-origin references are required.")
    for field in ("based_on_action_id", "origin_source_id"):
        identifier(parameters[field], field)
    for field in ("based_on_result_sha256", "origin_receipt_sha256"):
        _require(type(parameters[field]) is str and re.fullmatch(r"[a-f0-9]{64}", parameters[field]),
                 "INVALID_REQUEST", "A complete SHA-256 is required: " + field)
    return copy.deepcopy(parameters)


def code_identity() -> str:
    dependencies = b"".join(Path(module.__file__).read_bytes() for module in (workbook, c01, archive_inventory))
    return hashlib.sha256(Path(__file__).read_bytes() + tabular.code_identity().encode("ascii") + dependencies).hexdigest()


def _origin(payload, spec, parameters):
    source, raw = payload["origin_source"], payload["origin_bytes"]
    _require(type(source) is dict and set(source) == {"id", "sha256", "media_type"}
             and type(raw) is bytes and type(source.get("media_type")) is str
             and 0 < len(source["media_type"]) <= 200,
             "INVALID_SOURCE", "Captured workbook bytes and exact source metadata are required.")
    _require(source["id"] == parameters["origin_source_id"]
             and source["sha256"] == hashlib.sha256(raw).hexdigest() == spec["provenance"]["origin_sha256"],
             "EVIDENCE_CHANGED", "Captured origin identity differs from the tabular provenance or selected source.")
    return {**copy.deepcopy(source), "receipt_sha256": parameters["origin_receipt_sha256"],
            "byte_identity": "matched", "conversion_status": "unconfirmed"}


def _numeric_equal(left, right):
    try:
        first, second = Decimal(left), Decimal(right)
        return first.is_finite() and second.is_finite() and first == second
    except InvalidOperation:
        return False


def _candidate(sheet, cells, header, records, columns):
    expected_rows = set(range(2, len(records) + 2))
    workbook_rows = set()
    for ref, cell in cells.items():
        match = re.fullmatch(r"([A-Z]+)([0-9]+)", ref)
        if match[1] in columns and int(match[2]) > 1 and cell["status"] != "missing":
            workbook_rows.add(int(match[2]))
    summary = {"sheet": sheet, "csv_rows": len(records), "workbook_data_rows": len(workbook_rows),
               "compared_cells": len(records) * len(header), "exact_matches": 0, "numeric_equal_text_diff": 0,
               "mismatch_cells": 0, "formula_cells": 0, "missing_cells": 0,
               "missing_workbook_rows": sorted(expected_rows - workbook_rows),
               "extra_workbook_rows": sorted(workbook_rows - expected_rows), "examples": []}
    for logical_record, (row, physical_line) in enumerate(records, 1):
        for index, token in enumerate(row):
            ref = columns[index] + str(logical_record + 1)
            cell = cells.get(ref, EMPTY_CELL)
            status = cell["status"]
            expected = (cell["raw"] if status == "finite" else cell["value"] if status == "text"
                        else "" if status == "missing" else None)
            kind = ("exact_matches" if expected is not None and token == expected else "numeric_equal_text_diff"
                    if status == "finite" and _numeric_equal(token, cell["raw"]) else "mismatch_cells")
            summary[kind] += 1
            summary["formula_cells"] += bool(cell["formula_present"])
            summary["missing_cells"] += status == "missing"
            if kind != "exact_matches" and len(summary["examples"]) < 5:
                summary["examples"].append({"logical_record": logical_record, "physical_line_end": physical_line,
                    "workbook_row": logical_record + 1, "cell": ref, "column": header[index], "csv_text": token,
                    "workbook_value": cell["value"], "workbook_raw": cell["raw"], "workbook_status": status,
                    "formula_present": cell["formula_present"], "formula": cell["formula"], "comparison": kind})
    summary["non_exact_cells"] = summary["numeric_equal_text_diff"] + summary["mismatch_cells"]
    summary["projection_candidate_exact"] = (bool(records) and summary["non_exact_cells"] == 0
        and not summary["missing_workbook_rows"] and not summary["extra_workbook_rows"])
    return summary


def execute(payload, parameters) -> dict:
    """The host verifies saved predecessor/receipt binding; this method verifies bytes."""
    predecessor = _parameters(parameters)
    _require(type(payload) is dict and set(payload) == {"tabular_source", "origin_bytes", "origin_source"},
             "INVALID_SOURCE", "Captured tabular and workbook inputs are required.")
    source = payload["tabular_source"]
    spec, _, (header, records, physical_end) = tabular._checked(source)
    origin = _origin(payload, spec, predecessor)
    book = workbook.read_workbook(payload["origin_bytes"])
    columns = [workbook._column(index + 1) for index in range(len(header))]
    candidates = []
    for sheet, cells in book.items():
        full_header = (all(cells.get(column + "1", EMPTY_CELL)["value"] == name
                           for column, name in zip(columns, header))
                       and not any(re.fullmatch(r"([A-Z]+)1", ref) and ref[:-1] not in columns
                                   and cell["status"] != "missing" for ref, cell in cells.items()))
        if full_header:
            candidates.append(_candidate(sheet, cells, header, records, columns))
    exact = [item["sheet"] for item in candidates if item["projection_candidate_exact"]]
    summary = {"csv_rows": len(records), "csv_columns": len(header), "candidate_sheet_count": len(candidates),
               "exact_candidate_sheet_count": len(exact), "exact_candidate_sheets": exact,
               "candidate_status": ("ambiguous" if len(exact) > 1 else "single_exact_candidate" if exact
                                    else "no_exact_candidate" if candidates else "missing_header_candidate")}
    scope = copy.deepcopy(source["scope"])
    scope.update(contract="workbook-projection-check-v1", input_contract=source["scope"]["contract"],
                 target_status="declared_unconfirmed", origin_byte_identity="matched", conversion_status="unconfirmed")
    references = [{"source_snapshot_sha256": source["snapshot_sha256"], "source_sha256": source["source"]["sha256"],
                   "file_name": spec["file"], "url": spec["source_url"], "license_note": spec["license_note"],
                   "locator": {"kind": "csv_logical_records", "first": 1 if records else None,
                               "last": len(records) or None, "physical_line_end": physical_end}},
                  {"origin_receipt_sha256": predecessor["origin_receipt_sha256"], "source_id": origin["id"],
                   "source_sha256": origin["sha256"], "media_type": origin["media_type"],
                   "locator": {"kind": "xlsx_candidate_sheets", "sheets": [item["sheet"] for item in candidates]}}]
    value = {"schema_version": "workbook-projection-check-v1", "source_snapshot_sha256": source["snapshot_sha256"],
             "scope": scope, "predecessor": predecessor, "origin": origin, "summary": summary, "candidates": candidates,
             "projection_rule": "Candidate only: CSV logical data record n maps to worksheet row n+1, with all headers in row1 starting at A. Compare exact numeric cache text, decoded text or empty missing cells; never execute formulas.",
             "comparison_rule": "exact_matches + numeric_equal_text_diff + mismatch_cells = compared_cells; non_exact_cells is the latter two categories combined.",
             "formulas_executed": 0, "scientific_validation": False}
    observation = {key: copy.deepcopy(value[key]) for key in ("summary", "candidates", "scope", "predecessor", "origin")}
    observation.update(producer=TOOL_ID, kind="workbook_projection_check", evidence_refs=copy.deepcopy(references),
                       interpretation_status="candidate_projection_not_author_conversion_or_endpoint_confirmation",
                       scientific_validation=False)
    return {"schema_version": "workbook-projection-check-result-v1", "tool_id": TOOL_ID, "adapter_version": ADAPTER_VERSION,
            "status": "completed", "observations": [observation], "result": value, "evidence_refs": references,
            "metrics": [{"name": name, "value": summary[name], "unit": "count"}
                        for name in ("csv_rows", "candidate_sheet_count", "exact_candidate_sheet_count")],
            "failure": None, "scientific_validation": False, "model_calls": 0, "new_fits": 0}


def next_decision(result) -> dict:
    try:
        _require(result["tool_id"] == TOOL_ID and result["status"] == "completed"
                 and result["scientific_validation"] is False and result["new_fits"] == 0 and result["model_calls"] == 0
                 and result["result"]["schema_version"] == "workbook-projection-check-v1",
                 "INVALID_RESULT", "A completed candidate workbook projection check is required.")
        value = result["result"]
        required = [
            "Actual acquisition/run logs and original exported tables, plus the author conversion records or script linking them to the workbook and CSV rows.",
            "Confirm endpoint identity and unit, zero/missing rules, provenance and license against original records.",
            "Confirm grouping, sample units and independence; matching workbook caches do not establish these meanings."]
        if value["summary"]["exact_candidate_sheet_count"] > 1:
            required.append("Resolve the multiple exact candidate worksheets using original run and conversion records.")
        if not value["summary"]["candidate_sheet_count"]:
            required.append("Identify the original worksheet and column transformation; no complete header candidate was found.")
        return {"policy_ref": {"id": TOOL_ID, "version": ADAPTER_VERSION}, "project_status": "waiting",
                "next_action": {"kind": "evidence_task", "method_id": "research.source-selection",
                                "execution_status": "not_executed", "required_evidence": required},
                "reason": "Candidate projection comparisons are saved; author conversion, endpoint meaning and independence remain unconfirmed.",
                "source_snapshot_sha256": value["source_snapshot_sha256"], "predecessor": copy.deepcopy(value["predecessor"]),
                "evidence_refs": copy.deepcopy(result["evidence_refs"]), "scientific_validation": False,
                "new_fits": 0, "model_calls": 0}
    except ResearchError:
        raise
    except (KeyError, TypeError, ValueError):
        raise ResearchError("INVALID_RESULT", "Malformed workbook projection feedback.") from None
