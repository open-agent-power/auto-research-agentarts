"""Pure, bounded conditions over a supplied tabular-quality profile.

This module does not register a project, authenticate an action or source, read
an artifact, select a candidate, dispatch a tool, or validate scientific use.
The host must supply the declared numeric column names and independently verify
that the profile is the intended saved result before relying on this evaluation.

Registration schema (exact keys):
  {"schema_version": "tabular-quality-conditions-v1", "conditions": [condition, ...]}
There are 1..32 conditions. A count condition has exactly ``field``, ``operator``
and ``value``; numeric-column counts also require exactly ``column``. Operators
are eq, gt, gte, lt, lte. The value is an integer 0..50000, or the exact object
{"ref": "rows"} only for fields listed in ROW_REFERENCES. Field names below
are literal identifiers, never traversed as caller-controlled paths.

Count identifiers:
  rows, columns, exact_duplicate_rows;
  key.incomplete_rows, key.duplicate_rows, key.conflict_groups;
  group.incomplete_group_rows, group.group_count, group.min_group_size;
  numeric.finite, numeric.empty, numeric.declared_missing,
  numeric.invalid_numeric, numeric.nonfinite.
Count conditions use strict integer bounds. For a key condition, the dependent
key complete/incomplete/duplicate-group/duplicate-row/conflict-group counts
must all exist and be mutually consistent with rows. For a group condition, the
dependent group count, singleton/repeated counts, repeated-row/incomplete-row
counts and min/max sizes must all exist and be consistent with rows. Empty
actual grouping permits count zero and null min/max, but comparing a null size
is unknown. Numeric conditions require the complete numeric count partition,
including the finite zero subset. Unrelated profile sections are not required.

The sole flags condition has exactly {"field": "flags", "operator": "empty"}
or {"field": "flags", "operator": "nonempty"}; it has neither value nor
column. The adapter saves at most 64 distinct flags, not a total error count.

All conditions form AND. Every required value is inspected: if any is missing,
malformed or inconsistent, the aggregate is unknown even when another known
condition is false. Known zero is retained. This is only a calculation over
provided mechanical facts; unknown does not imply that its source was checked.
"""

import copy
import operator

from .contracts import ResearchError

SCHEMA = "tabular-quality-conditions-v1"
RESULT_SCHEMA = "tabular-quality-condition-evaluation-v1"
MAX_CONDITIONS = 32
MAX_ROWS = 50_000
MAX_COLUMNS = 128
MAX_NUMERIC_COLUMNS = 32
MAX_COLUMN_LENGTH = 256
MAX_FLAGS = 64
MAX_FLAG_LENGTH = 300

_FIELDS = {
    "rows": ("rows",),
    "columns": ("columns",),
    "exact_duplicate_rows": ("exact_duplicate_rows",),
    "key.incomplete_rows": ("key_columns", "incomplete_rows"),
    "key.duplicate_rows": ("key_columns", "duplicate_rows"),
    "key.conflict_groups": ("key_columns", "conflict_groups"),
    "group.incomplete_group_rows": ("group_columns", "incomplete_group_rows"),
    "group.group_count": ("group_columns", "group_count"),
    "group.min_group_size": ("group_columns", "min_group_size"),
}
_NUMERIC = {"numeric." + name: name for name in
            ("finite", "empty", "declared_missing", "invalid_numeric", "nonfinite")}
ROW_REFERENCES = frozenset({"exact_duplicate_rows", "key.incomplete_rows", "key.duplicate_rows",
                            "group.incomplete_group_rows", *_NUMERIC})
_OPS = {"eq": operator.eq, "gt": operator.gt, "gte": operator.ge,
        "lt": operator.lt, "lte": operator.le}
_COUNT_KINDS = ("finite", "empty", "declared_missing", "invalid_numeric", "nonfinite")


def _invalid(message):
    raise ResearchError("INVALID_REQUEST", message)


def _column_names(columns):
    if (type(columns) is not list or not 1 <= len(columns) <= MAX_NUMERIC_COLUMNS
            or any(type(c) is not str or not c or len(c) > MAX_COLUMN_LENGTH
                   or c != c.strip() or "\x00" in c for c in columns)
            or len(set(columns)) != len(columns)):
        _invalid("Use 1..32 distinct declared numeric column names.")
    return columns


def validate_conditions(registration, *, numeric_columns):
    """Validate and copy a bounded registration; invalid contracts are rejected.

    ``numeric_columns`` is the verified declaration from the caller's source
    scope, not a list supplied inside the conditions. This pure function cannot
    establish that the caller actually obtained it from a registered source.
    """
    declared = _column_names(numeric_columns)
    if (type(registration) is not dict or set(registration) != {"schema_version", "conditions"}
            or registration["schema_version"] != SCHEMA
            or type(registration["conditions"]) is not list
            or not 1 <= len(registration["conditions"]) <= MAX_CONDITIONS):
        _invalid("Use the exact bounded tabular-quality condition schema.")
    seen = set()
    for item in registration["conditions"]:
        if type(item) is not dict or type(item.get("field")) is not str:
            _invalid("Each condition must use an allowlisted field.")
        field = item["field"]
        if field == "flags":
            if (set(item) != {"field", "operator"} or type(item["operator"]) is not str
                    or item["operator"] not in ("empty", "nonempty")):
                _invalid("Flags may only be tested for empty or nonempty.")
            identity = (field, item["operator"])
        else:
            numeric = field in _NUMERIC
            if field not in _FIELDS and not numeric:
                _invalid("Unknown quality condition field.")
            keys = {"field", "operator", "value"} | ({"column"} if numeric else set())
            if (set(item) != keys or type(item["operator"]) is not str or item["operator"] not in _OPS
                    or (numeric and (type(item["column"]) is not str or item["column"] not in declared))):
                _invalid("Use the exact field, declared column and comparison operator.")
            value = item["value"]
            if type(value) is int and 0 <= value <= MAX_ROWS:
                operand = ("literal", value)
            elif type(value) is dict and value == {"ref": "rows"} and field in ROW_REFERENCES:
                operand = ("ref", "rows")
            else:
                _invalid("Use a bounded integer or an allowed rows reference.")
            identity = (field, item.get("column"), item["operator"], operand)
        if identity in seen:
            _invalid("Duplicate conditions are not supported.")
        seen.add(identity)
    return copy.deepcopy(registration)


def _int_count(value, *, minimum=0, maximum=MAX_ROWS):
    return type(value) is int and minimum <= value <= maximum


def _rows(profile):
    value = profile.get("rows") if type(profile) is dict else None
    return value if _int_count(value) else None


def _flags(profile):
    value = profile.get("flags") if type(profile) is dict else None
    if (type(value) is not list or len(value) > MAX_FLAGS
            or any(type(flag) is not str or not flag or len(flag) > MAX_FLAG_LENGTH or "\x00" in flag
                   for flag in value) or len(set(value)) != len(value)):
        return None
    return "empty" if not value else "nonempty"


def _numeric_count(profile, name, column, declared, rows):
    values = profile.get("numeric_columns")
    if (type(values) is not list or len(values) != len(declared)
            or any(type(item) is not dict or type(item.get("name")) is not str for item in values)):
        return None
    names = [item["name"] for item in values]
    if len(set(names)) != len(names) or set(names) != set(declared):
        return None
    counts = next(item for item in values if item["name"] == column).get("counts")
    if type(counts) is not dict:
        return None
    if any(not _int_count(counts.get(key), maximum=rows) for key in (*_COUNT_KINDS, "zero")):
        return None
    if sum(counts[key] for key in _COUNT_KINDS) != rows or counts["zero"] > counts["finite"]:
        return None
    return counts[name]


def _key_counts(profile, rows):
    value = profile.get("key_columns")
    names = ("complete_rows", "incomplete_rows", "duplicate_groups", "duplicate_rows", "conflict_groups")
    if type(value) is not dict or any(not _int_count(value.get(name), maximum=rows) for name in names):
        return None
    complete, incomplete, groups, duplicates, conflicts = (value[name] for name in names)
    if (complete + incomplete != rows or groups > duplicates or duplicates > complete - groups
            or conflicts > groups or (groups == 0 and duplicates != 0)):
        return None
    return value


def _group_counts(profile, rows):
    value = profile.get("group_columns")
    names = ("group_count", "singletons", "repeated_groups", "rows_in_repeated_groups", "incomplete_group_rows")
    if type(value) is not dict or any(not _int_count(value.get(name), maximum=rows) for name in names):
        return None
    if "min_group_size" not in value or "max_group_size" not in value:
        return None
    count, singles, repeated, repeated_rows, incomplete = (value[name] for name in names)
    minimum, maximum = value["min_group_size"], value["max_group_size"]
    complete = rows - incomplete
    if count != singles + repeated or singles + repeated_rows != complete:
        return None
    if count == 0:
        return value if complete == 0 and minimum is None and maximum is None else None
    if (not _int_count(minimum, minimum=1, maximum=rows)
            or not _int_count(maximum, minimum=1, maximum=rows) or minimum > maximum
            or complete < minimum * (count - 1) + maximum
            or complete > maximum * (count - 1) + minimum
            or (singles > 0 and minimum != 1) or (singles == 0 and minimum < 2)
            or (repeated == 0 and (repeated_rows != 0 or maximum != 1))
            or (repeated > 0 and (maximum < 2 or repeated_rows < maximum + 2 * (repeated - 1)
                                  or repeated_rows > maximum * repeated))):
        return None
    return value


def _actual(profile, item, declared):
    if type(profile) is not dict:
        return None
    field = item["field"]
    if field == "flags":
        return _flags(profile)
    rows = _rows(profile)
    if field == "rows":
        return rows
    if field == "columns":
        value = profile.get("columns")
        return value if _int_count(value, minimum=1, maximum=MAX_COLUMNS) else None
    # Every remaining supported count describes rows or groups bounded by rows.
    if rows is None:
        return None
    if field in _NUMERIC:
        return _numeric_count(profile, _NUMERIC[field], item["column"], declared, rows)
    if field.startswith("key."):
        key = _key_counts(profile, rows)
        return None if key is None else key[_FIELDS[field][1]]
    if field.startswith("group."):
        group = _group_counts(profile, rows)
        return None if group is None else group[_FIELDS[field][1]]
    current = profile
    for part in _FIELDS[field]:
        if type(current) is not dict or part not in current:
            return None
        current = current[part]
    # At least one distinct row exists whenever the input is nonempty.
    maximum = max(rows - 1, 0) if field == "exact_duplicate_rows" else rows
    return current if _int_count(current, maximum=maximum) else None


def evaluate_conditions(registration, profile, *, numeric_columns):
    """Evaluate a valid registration over supplied facts, without side effects.

    Invalid registrations raise INVALID_REQUEST. Missing or invalid profile
    values are returned as unknown; all conditions are examined before the
    aggregate is decided. The result is not evidence or a scientific judgment.
    """
    validated = validate_conditions(registration, numeric_columns=numeric_columns)
    results = []
    for index, item in enumerate(validated["conditions"]):
        actual = _actual(profile, item, numeric_columns)
        if item["field"] == "flags":
            expected = item["operator"]
        elif type(item["value"]) is dict:
            expected = _rows(profile)
        else:
            expected = item["value"]
        if actual is None or expected is None:
            outcome = "unknown"
        else:
            matched = (actual == expected if item["field"] == "flags"
                       else _OPS[item["operator"]](actual, expected))
            outcome = "condition_met" if matched else "condition_not_met"
        results.append({"index": index, "outcome": outcome, "actual": actual,
                        "expected": expected,
                        "unknown_reason": "missing_or_invalid_required_value" if outcome == "unknown" else None})
    states = [item["outcome"] for item in results]
    outcome = ("unknown" if "unknown" in states else "condition_not_met" if "condition_not_met" in states
               else "condition_met")
    return {"schema_version": RESULT_SCHEMA, "outcome": outcome, "items": results,
            "scientific_validation": False}
