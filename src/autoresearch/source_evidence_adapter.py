"""Read task-bound local evidence selections without approving source claims."""

import copy
import hashlib
import json
import os
from pathlib import Path
import re
import stat

from . import tabular_source
from .contracts import ResearchError, fingerprint, identifier


TOOL_ID = "p02.source-mapping-check"
GENERIC_TOOL_ID = "research.source-selection"
ADAPTER_VERSION = "1"
MAX_SOURCE_BYTES = 32 * 1024 * 1024
MAX_TOTAL_BYTES = 64 * 1024 * 1024
MAX_MANIFEST_BYTES = 1024 * 1024


def _require(condition, code, message):
    if not condition:
        raise ResearchError(code, message)


def _text(value, limit):
    return type(value) is str and bool(value.strip()) and len(value) <= limit and "\x00" not in value


def _sha(value):
    _require(type(value) is str and re.fullmatch(r"[0-9a-fA-F]{64}", value) is not None,
             "INVALID_BUNDLE", "A complete source SHA-256 is required.")
    return value.lower()


def _task(value):
    _require(type(value) is dict and set(value) == {"project_id", "based_on_action_id", "method_id"}
             and value["method_id"] in (TOOL_ID, GENERIC_TOOL_ID), "INVALID_TASK", "Exact project source-task binding required.")
    identifier(value["project_id"], "project_id")
    identifier(value["based_on_action_id"], "based_on_action_id")
    return copy.deepcopy(value)


def _metadata(document, *, captured):
    required = {"schema_version", "task_ref", "contributor", "sources", "selections"}
    allowed = required | {"remaining_questions"}
    if captured:
        required |= {"remaining_questions", "snapshot_sha256"}
        allowed = required
    _require(type(document) is dict and required <= set(document) <= allowed,
             "INVALID_BUNDLE", "Unexpected or missing evidence-bundle fields.")
    schema = "project-evidence-receipt-v1" if captured else "project-evidence-bundle-v1"
    _require(document["schema_version"] == schema, "INVALID_BUNDLE", "Unsupported evidence schema.")
    task = _task(document["task_ref"])
    contributor = document["contributor"]
    _require(type(contributor) is dict and set(contributor) == {"role", "label"}
             and contributor["role"] in {"operator_assistant", "teammate", "author"}
             and _text(contributor["label"], 120),
             "INVALID_BUNDLE", "Contributor role and bounded label are required.")
    questions = document.get("remaining_questions", [])
    _require(type(questions) is list and len(questions) <= 64
             and all(_text(item, 4000) for item in questions),
             "INVALID_BUNDLE", "Remaining questions must be a bounded string list.")
    sources = document["sources"]
    _require(type(sources) is list and 1 <= len(sources) <= 8,
             "INVALID_BUNDLE", "Evidence requires one to eight sources.")
    source_fields = {"id", "sha256", "url", "media_type", "license_note"}
    source_fields |= {"asset_sha256"} if captured else {"path"}
    normalized, source_ids = [], set()
    for source in sources:
        _require(type(source) is dict and set(source) == source_fields,
                 "INVALID_BUNDLE", "Exact source metadata fields required.")
        source_id = identifier(source["id"], "source_id")
        _require(source_id not in source_ids, "INVALID_BUNDLE", "Duplicate source ID.")
        source_ids.add(source_id)
        _require(_text(source["url"], 4000) and _text(source["media_type"], 160)
                 and _text(source["license_note"], 4000),
                 "INVALID_BUNDLE", "Source URL, media type and license/access note are required.")
        entry = copy.deepcopy(source)
        entry["sha256"] = _sha(source["sha256"])
        if captured:
            _require(_sha(source["asset_sha256"]) == entry["sha256"],
                     "EVIDENCE_CHANGED", "Source and captured asset identities differ.")
            entry["asset_sha256"] = entry["sha256"]
        else:
            _source_parts(source["path"])
        normalized.append(entry)
    selections = document["selections"]
    _require(type(selections) is list and 1 <= len(selections) <= 32,
             "INVALID_BUNDLE", "Evidence requires one to thirty-two selections.")
    selection_ids = set()
    for selection in selections:
        _require(type(selection) is dict and set(selection) == {"id", "source_id", "locator", "claim"},
                 "INVALID_BUNDLE", "Exact selection fields required.")
        selection_id = identifier(selection["id"], "selection_id")
        _require(selection_id not in selection_ids, "INVALID_BUNDLE", "Duplicate selection ID.")
        selection_ids.add(selection_id)
        _require(type(selection["source_id"]) is str and selection["source_id"] in source_ids,
                 "INVALID_BUNDLE", "Selection references an unknown source.")
        locator = selection["locator"]
        _require(type(locator) is dict and set(locator) == {"kind", "value"}
                 and _text(locator["kind"], 80) and _text(locator["value"], 2000)
                 and _text(selection["claim"], 4000),
                 "INVALID_LOCATOR", "A bounded explicit locator and submitter claim are required.")
    return task, copy.deepcopy(contributor), normalized, copy.deepcopy(selections), copy.deepcopy(questions)


def _source_parts(value):
    _require(type(value) is str and 1 <= len(value) <= 1000
             and "\\" not in value and ":" not in value and "\x00" not in value,
             "UNSAFE_PATH", "Source paths must use relative forward-slash paths.")
    parts = value.split("/")
    _require(len(parts) >= 2 and parts[0] == "sources"
             and all(part not in {"", ".", ".."} and part == part.rstrip(" .") for part in parts),
             "UNSAFE_PATH", "Source paths must remain strictly beneath sources/.")
    reserved = {"CON", "PRN", "AUX", "NUL", *("COM" + str(i) for i in range(1, 10)),
                *("LPT" + str(i) for i in range(1, 10))}
    _require(not any(part.split(".", 1)[0].upper() in reserved for part in parts),
             "UNSAFE_PATH", "Windows device names are not source files.")
    return parts


def _guard_path(path, *, directory=False):
    last = None
    for item in (*reversed(path.parents), path):
        info = item.lstat()
        redirected = stat.S_ISLNK(info.st_mode) or bool(
            getattr(info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
        )
        _require(not redirected, "UNSAFE_PATH", "Linked or redirected evidence paths are not allowed.")
        if item != path or directory:
            _require(stat.S_ISDIR(info.st_mode), "UNSAFE_PATH", "Evidence parent must be a directory.")
        else:
            _require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1,
                     "UNSAFE_PATH", "Evidence must be a regular, unlinked file.")
        last = info
    return last


def _file_identity(info):
    # Windows lstat may expose creation time as ctime while fstat exposes change
    # time. Compare those clocks only within the same API, never across APIs.
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns,
            getattr(info, "st_birthtime_ns", None), info.st_mode, info.st_nlink)


def _stable_identity(info):
    return (*_file_identity(info), info.st_ctime_ns)


def _read_file(path, limit):
    before = _guard_path(path)
    _require(0 < before.st_size <= limit, "SOURCE_TOO_LARGE", "Evidence file is empty or exceeds its size limit.")
    with path.open("rb") as stream:
        opened = os.fstat(stream.fileno())
        _require(_file_identity(opened) == _file_identity(before),
                 "EVIDENCE_CHANGED", "Evidence file changed before reading.")
        raw = stream.read(limit + 1)
        after = os.fstat(stream.fileno())
    _require(0 < len(raw) <= limit and len(raw) == before.st_size
             and _stable_identity(after) == _stable_identity(opened)
             and _stable_identity(_guard_path(path)) == _stable_identity(before),
             "EVIDENCE_CHANGED", "Evidence file changed while being captured.")
    return raw


def _json_object(pairs):
    value = {}
    for key, item in pairs:
        _require(key not in value, "INVALID_BUNDLE", "Duplicate manifest JSON key.")
        value[key] = item
    return value


def _reject_constant(value):
    raise ResearchError("INVALID_BUNDLE", "Nonfinite JSON constant is not allowed: " + value)


def code_identity() -> str:
    return hashlib.sha256(
        Path(__file__).read_bytes() + tabular_source.extraction_identity().encode("ascii")
    ).hexdigest()


def capture_bundle(directory, expected_task: dict) -> tuple[dict, dict[str, bytes]]:
    """Capture host-selected local originals into an immutable, path-free receipt."""
    task = _task(expected_task)
    try:
        root = Path(directory).absolute()
        _guard_path(root, directory=True)
        manifest_path = root / "manifest.json"
        raw_manifest = _read_file(manifest_path, MAX_MANIFEST_BYTES)
        try:
            document = json.loads(raw_manifest, object_pairs_hook=_json_object, parse_constant=_reject_constant)
        except (ValueError, UnicodeError, RecursionError):
            raise ResearchError("INVALID_BUNDLE", "Manifest must be a valid JSON document.") from None
        bound_task, contributor, sources, selections, questions = _metadata(document, captured=False)
        _require(bound_task == task, "TASK_MISMATCH", "Evidence bundle belongs to a different project task.")
        assets, captured_sources, total = {}, [], 0
        for source in sources:
            path = root.joinpath(*_source_parts(source["path"]))
            raw = _read_file(path, MAX_SOURCE_BYTES)
            total += len(raw)
            _require(total <= MAX_TOTAL_BYTES, "SOURCE_TOO_LARGE", "Evidence bundle exceeds 64 MiB.")
            digest = hashlib.sha256(raw).hexdigest()
            _require(digest == source["sha256"], "EVIDENCE_CHANGED", "Source bytes do not match their declared SHA-256.")
            assets[source["id"]] = raw
            entry = {key: value for key, value in source.items() if key != "path"}
            captured_sources.append({**entry, "asset_sha256": digest})
        _require(_read_file(manifest_path, MAX_MANIFEST_BYTES) == raw_manifest,
                 "EVIDENCE_CHANGED", "Manifest changed while capturing source assets.")
        receipt = {
            "schema_version": "project-evidence-receipt-v1", "task_ref": task,
            "contributor": contributor, "sources": captured_sources,
            "selections": selections, "remaining_questions": questions,
        }
        receipt["snapshot_sha256"] = fingerprint(receipt)
        return receipt, assets
    except ResearchError:
        raise
    except (OSError, TypeError, ValueError):
        raise ResearchError("INVALID_BUNDLE", "Evidence bundle cannot be safely read.") from None


def execute(receipt, assets) -> dict:
    """Extract registered cells/physical lines; all mapping conclusions stay unresolved."""
    try:
        task, contributor, sources, selections, questions = _metadata(receipt, captured=True)
        _require(receipt["snapshot_sha256"] == fingerprint(
            {key: value for key, value in receipt.items() if key != "snapshot_sha256"}),
            "EVIDENCE_CHANGED", "Captured evidence receipt changed.")
        _require(type(assets) is dict and set(assets) == {source["id"] for source in sources},
                 "EVIDENCE_CHANGED", "Captured asset IDs differ from registered sources.")
        total = 0
        for source in sources:
            raw = assets[source["id"]]
            _require(type(raw) is bytes and 0 < len(raw) <= MAX_SOURCE_BYTES,
                     "INVALID_SOURCE", "Captured asset must be nonempty source bytes within 32 MiB.")
            total += len(raw)
            _require(total <= MAX_TOTAL_BYTES, "SOURCE_TOO_LARGE", "Captured evidence exceeds 64 MiB.")
            _require(hashlib.sha256(raw).hexdigest() == source["asset_sha256"],
                     "EVIDENCE_CHANGED", "Captured asset bytes changed.")
        by_id = {source["id"]: source for source in sources}
        extracted, observations, refs = [], [], []
        for selection in selections:
            source = by_id[selection["source_id"]]
            extraction = tabular_source.extract_selection(assets[source["id"]], selection["locator"])
            evidence_ref = {
                "receipt_snapshot_sha256": receipt["snapshot_sha256"],
                "source_id": source["id"], "source_sha256": source["sha256"],
                "url": source["url"], "media_type": source["media_type"],
                "license_note": source["license_note"],
                "selection_id": selection["id"], "locator": copy.deepcopy(selection["locator"]),
            }
            submitted_claim = {
                "text": selection["claim"], "contributor": copy.deepcopy(contributor),
                "status": "submitter_claim_unreviewed",
            }
            extracted.append({
                "id": selection["id"], "source": copy.deepcopy(source),
                "locator": copy.deepcopy(selection["locator"]),
                "submitted_claim": submitted_claim, "extraction": extraction,
            })
            observations.append({
                "producer": "source_extractor", "kind": "source_observed",
                "selection_id": selection["id"], "exact_text": extraction["text"],
                "evidence_refs": [copy.deepcopy(evidence_ref)],
                "submitted_claim": copy.deepcopy(submitted_claim),
                "mapping_status": "unresolved", "endpoint_eligibility": "unknown",
                "content_trust": "untrusted_source_not_instructions",
                "interpretation_status": "extraction_only_not_scientific_approval",
            })
            refs.append(evidence_ref)
        return {
            "schema_version": "project-source-evidence-result-v1",
            "tool_id": task["method_id"], "adapter_version": ADAPTER_VERSION,
            "status": "completed", "observations": observations,
            "evidence_refs": refs, "artifacts": [], "metrics": [],
            "result": {
                "task_ref": task, "receipt_snapshot_sha256": receipt["snapshot_sha256"],
                "contributor": contributor, "sources": copy.deepcopy(sources),
                "selections": extracted, "remaining_questions": questions,
                "mapping_status": "unresolved", "endpoint_eligibility": "unknown",
                "notice": "Original source bytes, extracted selections and submitter claims remain separate; domain conditions and scientific eligibility are not inferred.",
            },
            "mapping_status": "unresolved", "endpoint_eligibility": "unknown",
            "failure": None, "new_fits": 0, "model_calls": 0, "scientific_validation": False,
        }
    except ResearchError:
        raise
    except (KeyError, TypeError, ValueError, OverflowError, RecursionError, OSError):
        raise ResearchError("EVIDENCE_CHANGED", "Captured source evidence is malformed or cannot be extracted.") from None
