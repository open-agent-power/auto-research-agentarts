"""Bounded CSV/TSV mechanical audit; declarations never establish scientific eligibility."""

import base64
import binascii
import collections
import copy
import csv
import hashlib
import io
import json
import math
from pathlib import Path
import re
import unicodedata

from . import source_evidence_adapter as reader
from .contracts import ResearchError, fingerprint

TOOL_ID = "data.tabular-quality-audit"
ADAPTER_VERSION = "1"
MAX_CSV_BYTES = 8 * 1024 * 1024
MAX_SPEC_BYTES = 64 * 1024
MAX_PACKET_BYTES = 12 * 1024 * 1024
SPEC_FIELDS = {"schema_version", "file", "dataset_label", "source_url", "license_note", "sample_unit",
               "group_columns", "key_columns", "numeric_columns", "target_column", "target_unit",
               "missing_tokens", "delimiter", "provenance"}


def _require(condition, code, message):
    if not condition:
        raise ResearchError(code, message)


def _text(value, limit):
    return type(value) is str and 0 < len(value) <= limit and bool(value.strip()) and "\x00" not in value


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _object(pairs):
    value = {}
    for key, item in pairs:
        _require(key not in value, "INVALID_SOURCE_JSON", "Duplicate JSON member.")
        value[key] = item
    return value


def _parse(raw):
    def reject(_):
        raise ResearchError("INVALID_SOURCE_JSON", "Nonfinite JSON constants are not allowed.")
    try:
        return json.loads(raw.decode("utf-8-sig"), object_pairs_hook=_object, parse_constant=reject)
    except (UnicodeError, ValueError, RecursionError):
        raise ResearchError("INVALID_SOURCE_JSON", "Strict UTF-8 JSON is required.") from None


def _filename(value):
    parts = reader._source_parts("sources/" + value) if type(value) is str else []
    _require(len(parts) == 2 and len(value) <= 160 and not any(char in value for char in '<>"|?*')
             and not any(ord(char) < 32 for char in value), "UNSAFE_PATH", "Use one safe source file name.")
    return value


def _spec(spec):
    _require(type(spec) is dict and set(spec) == SPEC_FIELDS
             and spec["schema_version"] == "tabular-quality-spec-v1", "INVALID_SPEC", "Exact tabular quality spec required.")
    _filename(spec["file"])
    _require(Path(spec["file"]).suffix.lower() in (".csv", ".tsv"), "INVALID_SPEC", "A CSV or TSV source is required.")
    for key, limit in (("dataset_label", 300), ("source_url", 2000), ("license_note", 4000), ("sample_unit", 300)):
        _require(_text(spec[key], limit), "INVALID_SPEC", "Bounded nonempty source declarations required: " + key)
    for key, minimum, maximum in (("group_columns", 0, 8), ("key_columns", 0, 8), ("numeric_columns", 1, 32)):
        columns = spec[key]
        _require(type(columns) is list and minimum <= len(columns) <= maximum
                 and all(_text(name, 256) and name == name.strip() for name in columns)
                 and len(set(columns)) == len(columns), "INVALID_SPEC", "Invalid declared column list: " + key)
    target, unit = spec["target_column"], spec["target_unit"]
    _require((target is None and unit is None) or (type(target) is str and target in spec["numeric_columns"] and _text(unit, 300)),
             "INVALID_SPEC", "A declared numeric target requires a nonempty declared unit; absent target uses null unit.")
    tokens = spec["missing_tokens"]
    _require(type(tokens) is list and 1 <= len(tokens) <= 16 and "" in tokens
             and all(type(token) is str and len(token) <= 256 and "\x00" not in token for token in tokens)
             and len(set(tokens)) == len(tokens) and spec["delimiter"] in (",", "\t"),
             "INVALID_SPEC", "Use distinct exact missing tokens including empty string and comma or tab delimiter.")
    provenance = spec["provenance"]
    _require(type(provenance) is dict and set(provenance) == {"origin_sha256", "description"}
             and type(provenance["origin_sha256"]) is str and re.fullmatch(r"[a-f0-9]{64}", provenance["origin_sha256"])
             and _text(provenance["description"], 4000), "INVALID_SPEC", "Bounded unverified provenance declaration required.")


def _scope(spec, source_sha):
    return {"domain": "data", "contract": "tabular-quality-v1", "dataset_label": spec["dataset_label"],
            "sample_unit": spec["sample_unit"], "target_column": spec["target_column"], "target_unit": spec["target_unit"],
            "source_sha256": source_sha, "group_columns": copy.deepcopy(spec["group_columns"]),
            "key_columns": copy.deepcopy(spec["key_columns"]), "numeric_columns": copy.deepcopy(spec["numeric_columns"]),
            "target_status": "declared_unconfirmed"}


def _asset(name, raw):
    return {"file_name": name, "sha256": _sha(raw), "bytes": len(raw), "bytes_base64": base64.b64encode(raw).decode("ascii")}


def _decode_asset(asset, limit):
    _require(type(asset) is dict and set(asset) == {"file_name", "sha256", "bytes", "bytes_base64"}
             and type(asset["bytes"]) is int and 0 < asset["bytes"] <= limit
             and type(asset["sha256"]) is str and re.fullmatch(r"[a-f0-9]{64}", asset["sha256"])
             and type(asset["bytes_base64"]) is str and len(asset["bytes_base64"]) <= 4 * ((limit + 2) // 3),
             "INVALID_SOURCE", "Bounded original source bytes and identity required.")
    _filename(asset["file_name"])
    try:
        raw = base64.b64decode(asset["bytes_base64"], validate=True)
    except (ValueError, binascii.Error):
        raise ResearchError("INVALID_SOURCE", "Original source bytes must use strict base64.") from None
    _require(len(raw) == asset["bytes"] and _sha(raw) == asset["sha256"], "EVIDENCE_CHANGED", "Original source bytes changed.")
    return raw


def _records(raw, spec):
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeError:
        raise ResearchError("INVALID_CSV", "CSV/TSV must be strict UTF-8 with optional BOM.") from None
    _require("\x00" not in text, "INVALID_CSV", "CSV/TSV cannot contain NUL characters.")
    # The whole original is already bounded; permit a cell up to that same bound.
    old_limit = csv.field_size_limit()
    try:
        csv.field_size_limit(MAX_CSV_BYTES)
        parser = csv.reader(io.StringIO(text, newline=""), delimiter=spec["delimiter"], strict=True)
        header = next(parser, None)
        _require(header is not None and 1 <= len(header) <= 128
                 and all(_text(name, 256) and name == name.strip() for name in header),
                 "INVALID_CSV", "Use 1..128 nonempty unpadded column names.")
        normalized = [unicodedata.normalize("NFKC", name).casefold() for name in header]
        _require(len(set(normalized)) == len(header), "INVALID_CSV", "Duplicate or ambiguous column names are not allowed.")
        _require(set(spec["group_columns"] + spec["key_columns"] + spec["numeric_columns"]) <= set(header),
                 "INVALID_SPEC", "A declared column is absent from the original header.")
        rows = []
        for logical_record, row in enumerate(parser, 1):
            _require(logical_record <= 50_000, "SOURCE_TOO_LARGE", "At most 50000 data records are supported.")
            _require(len(row) == len(header), "INVALID_CSV", "CSV records must have the exact header width.")
            rows.append((tuple(row), parser.line_num))
        return header, rows, parser.line_num
    except csv.Error:
        raise ResearchError("INVALID_CSV", "Strict CSV parsing failed.") from None
    finally:
        csv.field_size_limit(old_limit)


def _checked(payload):
    try:
        _require(type(payload) is dict and set(payload) == {"schema_version", "spec_source", "source", "spec", "scope", "snapshot_sha256"}
                 and payload["schema_version"] == "tabular-quality-source-v1"
                 and payload["snapshot_sha256"] == fingerprint({key: value for key, value in payload.items() if key != "snapshot_sha256"}),
                 "EVIDENCE_CHANGED", "Tabular source snapshot changed.")
        spec_raw = _decode_asset(payload["spec_source"], MAX_SPEC_BYTES)
        raw = _decode_asset(payload["source"], MAX_CSV_BYTES)
        spec = _parse(spec_raw)
        _spec(spec)
        _require(payload["spec_source"]["file_name"] == "spec.json" and payload["source"]["file_name"] == spec["file"]
                 and payload["spec"] == spec and payload["scope"] == _scope(spec, _sha(raw)),
                 "EVIDENCE_CHANGED", "Declared spec, source name or derived scope differs from original bytes.")
        return spec, raw, _records(raw, spec)
    except ResearchError:
        raise
    except (KeyError, TypeError, ValueError, OverflowError, RecursionError):
        raise ResearchError("INVALID_SOURCE", "Malformed tabular source packet.") from None


def code_identity() -> str:
    return _sha(Path(__file__).read_bytes() + reader.code_identity().encode("ascii"))


def capture_source(directory) -> dict:
    """Host-selected directory only; spec and original bytes remain immutable data."""
    try:
        root = Path(directory).absolute()
        spec_raw = reader._read_file(root / "spec.json", MAX_SPEC_BYTES)
        spec = _parse(spec_raw)
        _spec(spec)
        raw = reader._read_file(root / _filename(spec["file"]), MAX_CSV_BYTES)
        payload = {"schema_version": "tabular-quality-source-v1", "spec_source": _asset("spec.json", spec_raw),
                   "source": _asset(spec["file"], raw), "spec": spec, "scope": _scope(spec, _sha(raw))}
        payload["snapshot_sha256"] = fingerprint(payload)
        _checked(payload)
        _require(reader._read_file(root / "spec.json", MAX_SPEC_BYTES) == spec_raw
                 and reader._read_file(root / spec["file"], MAX_CSV_BYTES) == raw,
                 "EVIDENCE_CHANGED", "Original inputs changed during capture.")
        return payload
    except ResearchError:
        raise
    except (OSError, TypeError, ValueError):
        raise ResearchError("INVALID_SOURCE", "Tabular source directory cannot be safely captured.") from None


def load_source(raw: bytes) -> dict:
    _require(type(raw) is bytes and 0 < len(raw) <= MAX_PACKET_BYTES, "INVALID_SOURCE", "A bounded tabular source packet is required.")
    payload = _parse(raw)
    _checked(payload)
    return payload


def execute(payload, dimension=None) -> dict:
    _require(dimension is None, "INVALID_REQUEST", "Tabular quality audit has no grouping execution parameter.")
    spec, _, (header, records, physical_end) = _checked(payload)
    positions = {name: index for index, name in enumerate(header)}
    missing, examples, flags = set(spec["missing_tokens"]), [], []
    def flag(value):
        if value not in flags and len(flags) < 64:
            flags.append(value)
    def example(name, record, physical_line, token, kind):
        if len(examples) < 5:
            examples.append({"column": name, "logical_record": record, "physical_line_end": physical_line,
                             "token": token[:160], "token_truncated": len(token) > 160, "kind": kind})
    numeric = []
    for name in spec["numeric_columns"]:
        counts = dict.fromkeys(("finite", "zero", "empty", "declared_missing", "invalid_numeric", "nonfinite"), 0)
        minimum = maximum = None
        for logical_record, (row, physical_line) in enumerate(records, 1):
            token = row[positions[name]]
            if token == "":
                kind = "empty"
            elif token in missing:
                kind = "declared_missing"
            else:
                try:
                    value = float(token)
                    kind = "finite" if math.isfinite(value) else "nonfinite"
                except (ValueError, OverflowError):
                    kind = "invalid_numeric"
            counts[kind] += 1
            if kind == "finite":
                counts["zero"] += int(value == 0)
                minimum = value if minimum is None else min(minimum, value)
                maximum = value if maximum is None else max(maximum, value)
            else:
                example(name, logical_record, physical_line, token, kind)
        for kind in ("empty", "declared_missing", "invalid_numeric", "nonfinite"):
            if counts[kind]:
                flag("numeric:" + name + ":" + kind)
        numeric.append({"name": name, "counts": counts, "min": minimum, "max": maximum})
    exact_duplicates = len(records) - len({row for row, _ in records})
    if exact_duplicates:
        flag("exact_duplicate_rows")
        first_occurrences, duplicate_examples = {}, []
        for logical_record, (row, physical_line) in enumerate(records, 1):
            first = first_occurrences.get(row)
            if first is None:
                first_occurrences[row] = (logical_record, physical_line)
            else:
                duplicate_examples.append({"kind": "exact_duplicate_row", "logical_record": logical_record,
                                           "physical_line_end": physical_line, "first_logical_record": first[0],
                                           "first_physical_line_end": first[1]})
                if len(duplicate_examples) == 5:
                    break
        # Keep duplicate coordinates visible even when numeric examples fill the cap.
        examples = duplicate_examples + examples[:5 - len(duplicate_examples)]
    if not records:
        flag("empty_dataset")
    keys, incomplete_keys = {}, 0
    for row, _ in records:
        if not spec["key_columns"]:
            break
        key = tuple(row[positions[name]] for name in spec["key_columns"])
        if any(token in missing for token in key):
            incomplete_keys += 1
        else:
            count, unique_rows = keys.setdefault(key, [0, set()])
            keys[key][0] = count + 1
            unique_rows.add(row)
    key_profile = {"complete_rows": sum(count for count, _ in keys.values()) if spec["key_columns"] else None,
                   "incomplete_rows": incomplete_keys if spec["key_columns"] else None,
                   "duplicate_groups": sum(count > 1 for count, _ in keys.values()) if spec["key_columns"] else None,
                   "duplicate_rows": sum(count - 1 for count, _ in keys.values()) if spec["key_columns"] else None,
                   "conflict_groups": sum(len(rows) > 1 for _, rows in keys.values()) if spec["key_columns"] else None}
    if key_profile["duplicate_groups"]:
        flag("declared_key_duplicate_groups")
    if key_profile["conflict_groups"]:
        flag("declared_key_conflicting_rows")
    if incomplete_keys:
        flag("declared_key_incomplete_rows")
    groups, incomplete_groups = collections.Counter(), 0
    if spec["group_columns"]:
        for row, _ in records:
            group = tuple(row[positions[name]] for name in spec["group_columns"])
            if any(token in missing for token in group):
                incomplete_groups += 1
            else:
                groups[group] += 1
    group_profile = {"group_count": len(groups) if spec["group_columns"] else None,
                     "singletons": sum(count == 1 for count in groups.values()) if spec["group_columns"] else None,
                     "repeated_groups": sum(count > 1 for count in groups.values()) if spec["group_columns"] else None,
                     "rows_in_repeated_groups": sum(count for count in groups.values() if count > 1) if spec["group_columns"] else None,
                     "min_group_size": min(groups.values(), default=None), "max_group_size": max(groups.values(), default=None),
                     "incomplete_group_rows": incomplete_groups if spec["group_columns"] else None}
    if incomplete_groups:
        flag("declared_group_incomplete_rows")
    profile = {"rows": len(records), "columns": len(header), "column_names": header,
               "exact_duplicate_rows": exact_duplicates, "key_columns": key_profile, "group_columns": group_profile,
               "numeric_columns": numeric, "examples": examples, "flags": flags,
               "mechanical_status": "needs_data_review" if flags else "no_flags_in_selected_checks",
               "record_coordinates": "logical_record: 1-based data record excluding header; physical_line_end: csv.reader.line_num including header"}
    reference = {"source_snapshot_sha256": payload["snapshot_sha256"], "source_sha256": payload["source"]["sha256"],
                 "file_name": spec["file"], "url": spec["source_url"], "license_note": spec["license_note"],
                 "locator": {"kind": "csv_logical_records", "first": 1 if records else None,
                             "last": len(records) or None, "physical_line_end": physical_end}}
    sources = [{key: asset[key] for key in ("file_name", "sha256", "bytes")} for asset in (payload["spec_source"], payload["source"])]
    observed = {"producer": TOOL_ID, "kind": "tabular_quality_audit", "profile": copy.deepcopy(profile),
                "scope": copy.deepcopy(payload["scope"]), "sources": sources, "evidence_refs": [reference],
                "interpretation_status": "mechanical_checks_only_declarations_unverified", "scientific_validation": False}
    return {"schema_version": "tabular-quality-result-v1", "tool_id": TOOL_ID, "adapter_version": ADAPTER_VERSION,
            "status": "completed", "observations": [observed],
            "metrics": [{"name": name, "value": profile[name], "unit": "count"} for name in ("rows", "columns", "exact_duplicate_rows")],
            "evidence_refs": [reference], "result": {"profile": profile, "scope": copy.deepcopy(payload["scope"]),
                                                      "source_snapshot_sha256": payload["snapshot_sha256"]},
            "failure": None, "scientific_validation": False, "new_fits": 0, "model_calls": 0}


def next_decision(result) -> dict:
    try:
        _require(result["tool_id"] == TOOL_ID and result["status"] == "completed" and result["scientific_validation"] is False
                 and result["new_fits"] == 0 and result["model_calls"] == 0,
                 "INVALID_RESULT", "A completed mechanical tabular audit is required.")
        profile, scope = result["result"]["profile"], result["result"]["scope"]
        required = ["Original data provenance, access and license evidence; submitter declarations remain unverified.",
                    "Confirm target meaning and unit before any scientific or training use." if scope["target_column"] else
                    "Clarify the intended target or confirm this is an untargeted data-quality task.",
                    "Confirm grouping and independence meaning against collection records." if scope["group_columns"] else
                    "Obtain grouping or sampling-unit definitions; absent group columns do not prove independence."]
        if scope["key_columns"]:
            required.append("Confirm the submitter-declared key's uniqueness and conflict-resolution rules.")
        if profile["flags"]:
            required.append("Resolve or explain observed mechanical flags without silently dropping rows or replacing values: " + "; ".join(profile["flags"]))
        return {"policy_ref": {"id": TOOL_ID, "version": ADAPTER_VERSION}, "project_status": "waiting",
                "next_action": {"kind": "evidence_task", "method_id": "research.source-selection", "execution_status": "not_executed",
                                "required_evidence": required},
                "reason": "Mechanical checks completed; original values were preserved. Target, grouping and scientific eligibility remain unconfirmed.",
                "evidence_refs": copy.deepcopy(result["evidence_refs"]), "scientific_validation": False, "new_fits": 0, "model_calls": 0}
    except ResearchError:
        raise
    except (KeyError, TypeError, ValueError):
        raise ResearchError("INVALID_RESULT", "Malformed tabular audit feedback.") from None
