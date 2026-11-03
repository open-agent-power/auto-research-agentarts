"""Build a local task-bound bundle from a verified saved Europe PMC response."""

import copy
import hashlib
import json
from pathlib import Path

from . import source_evidence_adapter as evidence
from .contracts import ResearchError, canonical, fingerprint, identifier
from .research_project import ResearchProject, safe_path


MAX_PROJECTED_RECORDS = 8
MAX_PROJECTED_URLS = 4
MAX_FIELD_CHARACTERS = 512
METADATA_FIELDS = ("id", "source", "pmid", "pmcid", "title", "doi", "isOpenAccess")
URL_FIELDS = ("availability", "availabilityCode", "documentStyle", "site", "url")


def _require(condition, code, message):
    if not condition:
        raise ResearchError(code, message)


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _object(pairs):
    value = {}
    for key, item in pairs:
        _require(key not in value, "PROVIDER_JSON_INVALID", "Duplicate provider JSON member.")
        value[key] = item
    return value


def _reject_constant(value):
    raise ResearchError("PROVIDER_JSON_INVALID", "Nonfinite provider JSON constant: " + value)


def _parse(raw):
    try:
        return json.loads(raw.decode("utf-8-sig"), object_pairs_hook=_object, parse_constant=_reject_constant)
    except ResearchError:
        raise
    except (ValueError, UnicodeError, TypeError, RecursionError):
        raise ResearchError("PROVIDER_JSON_INVALID", "Saved provider response is not valid strict UTF-8 JSON.") from None


def _projection(raw, doi, raw_sha):
    document = _parse(raw)
    _require(type(document) is dict and type(document.get("hitCount")) is int and document["hitCount"] >= 0
             and type(document.get("resultList")) is dict and type(document["resultList"].get("result")) is list,
             "PROVIDER_JSON_INVALID", "Expected nonnegative integer hitCount and resultList.result array.")
    records = document["resultList"]["result"]
    hits = document["hitCount"]
    _require(all(type(record) is dict for record in records) and hits >= len(records)
             and ((hits == 0 and not records) or (hits > 0 and bool(records))),
             "PROVIDER_JSON_INVALID", "Provider hit count and returned result page are inconsistent.")
    _require(type(doi) is str and doi == doi.strip().lower() and doi.startswith("10.") and "/" in doi,
             "INVALID_SOURCE_RECEIPT", "The acquisition receipt must retain its canonical DOI.")
    matches = []
    for index, record in enumerate(records):
        record_doi = record.get("doi")
        _require(record_doi is None or type(record_doi) is str,
                 "PROVIDER_JSON_INVALID", "Provider DOI must be a string when supplied.")
        if record_doi is not None and record_doi.strip().casefold() == doi:
            matches.append((index, record))
    lines = [{"artifact_role": "host_derived_projection", "provider_json_pointer": "",
              "raw_response_sha256": raw_sha, "requested_doi": doi,
              "host_note": "Host metadata projection, not the provider's raw JSON, article full text or author measurement/export evidence."},
             {"artifact_role": "host_derived_projection", "provider_json_pointer": "/hitCount", "provider_value": hits,
              "host_context": {"returned_records": len(records), "exact_doi_matches_in_page": len(matches),
                               "projected_record_limit": MAX_PROJECTED_RECORDS,
                               "omitted_exact_records": max(0, len(matches) - MAX_PROJECTED_RECORDS),
                               "page_covers_hit_count": len(records) == hits, "additional_pages_requested": False}}]

    def field(pointer, value):
        _require(value is None or type(value) in (str, int, float, bool),
                 "PROVIDER_JSON_INVALID", "Selected provider metadata must be scalar.")
        truncated = type(value) is str and len(value) > MAX_FIELD_CHARACTERS
        lines.append({"artifact_role": "host_derived_projection", "provider_json_pointer": pointer,
                      "provider_value": value[:MAX_FIELD_CHARACTERS] if truncated else value,
                      "host_truncated": truncated, **({"original_characters": len(value)} if truncated else {})})

    for index, record in matches[:MAX_PROJECTED_RECORDS]:
        base = "/resultList/result/" + str(index)
        for key in METADATA_FIELDS:
            if key in record:
                field(base + "/" + key, record[key])
        url_list = record.get("fullTextUrlList")
        if url_list is not None:
            _require(type(url_list) is dict and type(url_list.get("fullTextUrl")) is list
                     and all(type(item) is dict for item in url_list["fullTextUrl"]),
                     "PROVIDER_JSON_INVALID", "fullTextUrlList must retain its provider array shape.")
            urls = url_list["fullTextUrl"]
            for url_index, url in enumerate(urls[:MAX_PROJECTED_URLS]):
                for key in URL_FIELDS:
                    if key in url:
                        field(base + "/fullTextUrlList/fullTextUrl/" + str(url_index) + "/" + key, url[key])
            if len(urls) > MAX_PROJECTED_URLS:
                lines.append({"artifact_role": "host_derived_projection", "provider_json_pointer": base + "/fullTextUrlList/fullTextUrl",
                              "host_note": "Additional URL metadata omitted from this bounded projection; original JSON is archived.",
                              "omitted_urls": len(urls) - MAX_PROJECTED_URLS})
    notice = ("Provider returned zero records. This does not prove the article or its measurement mapping does not exist."
              if hits == 0 else "Returned page contains no exact DOI match; unrelated records are not projected and absence is not proved."
              if not matches else "Only exact DOI-matching bibliographic metadata is projected. isOpenAccess and listed URLs are not reuse licenses or proof of accessible full text.")
    lines.append({"artifact_role": "host_derived_projection", "provider_json_pointer": "", "host_note": notice,
                  "remaining_boundary": "Object, channel, export-column, batch and ALP mappings remain unconfirmed. Abstracts/full text were not projected; listed URLs were not followed."})
    projected = ("\n".join(canonical(line) for line in lines) + "\n").encode("utf-8")
    _text_selection(projected)
    return projected, {"provider_hit_count": hits, "returned_records": len(records), "exact_doi_matches_in_page": len(matches),
                       "projected_records": min(len(matches), MAX_PROJECTED_RECORDS), "provider_zero_results": hits == 0}


def _text_selection(raw):
    try:
        count = len(raw.decode("utf-8").splitlines())
    except UnicodeError:
        raise ResearchError("PROJECTION_INVALID", "Host projection must be UTF-8.") from None
    _require(1 <= count <= 256 and len(raw) <= 60_000,
             "PROJECTION_TOO_LARGE", "Each host projection must fit 256 physical lines and 60000 UTF-8 bytes.")
    return {"kind": "text_lines", "value": "1" if count == 1 else "1-" + str(count)}


def build_bundle(*, workspace, request_id, output) -> dict:
    """Offline only: validate received bytes, project metadata and create a fresh bundle."""
    from .europe_pmc import EuropePmcSource

    identifier(request_id)
    acquisition = EuropePmcSource(workspace).status(request_id)
    _require(acquisition["status"] == "received" and type(acquisition.get("receipt")) is dict,
             "SOURCE_NOT_RECEIVED", "Only a complete received provider response may become a source bundle.")
    project = ResearchProject(workspace)
    before = project.status()
    receipt = acquisition["receipt"]
    task = copy.deepcopy(receipt["task_ref"])
    primary = next((action for action in before["actions"] if action["id"] == task["based_on_action_id"]), None)
    _require(receipt["request_id"] == request_id and receipt["project_id"] == task["project_id"] == before["id"]
             and before.get("evidence_task_ref") == task and task["method_id"] == evidence.TOOL_ID
             and primary is not None and primary["command"] == "p02.saved-oof-residuals" and primary["status"] == "completed",
             "TASK_MISMATCH", "Response must bind this P02 project's original completed primary evidence task.")
    _require(receipt["http_status"] == 200 and receipt["response_body_complete"] is True
             and receipt["truncated"] is False and receipt["access_license_unknown"] is True
             and receipt["scientific_validation"] is False and receipt["content_type"].split(";", 1)[0].strip().lower() == "application/json"
             and receipt["content_encoding"].strip().lower() in ("", "identity"),
             "INVALID_SOURCE_RECEIPT", "A complete uncompressed JSON response with explicit unknown licensing is required.")
    origin = safe_path(Path(acquisition["output"]).absolute()).resolve()
    target = safe_path(Path(output).absolute()).resolve()
    project_root = project.root.resolve()
    _require(not target.exists() and all(not target.is_relative_to(root) and not root.is_relative_to(target)
                                        for root in (origin, project_root)),
             "OUTPUT_OVERLAP", "Choose a fresh bundle separate from the original response and project.")
    receipt_raw = evidence._read_file(origin / "response.json", 65_536)
    _require(_parse(receipt_raw) == receipt, "EVIDENCE_CHANGED", "Saved response receipt differs from its verified record.")
    raw = evidence._read_file(origin / "response.bin", evidence.MAX_SOURCE_BYTES)
    _require(type(receipt["raw_bytes"]) is int and len(raw) == receipt["raw_bytes"]
             and _sha(raw) == receipt["raw_sha256"], "EVIDENCE_CHANGED", "Original provider response bytes changed.")
    projection, lookup = _projection(raw, receipt["doi"], receipt["raw_sha256"])
    projection_sha = _sha(projection)
    provenance = {"schema_version": "public-source-provenance-v1", "artifact_role": "host_acquisition_provenance",
                  "provider": "Europe PMC", "acquisition_receipt": copy.deepcopy(receipt),
                  "acquisition_receipt_file_sha256": _sha(receipt_raw),
                  "provider_response": {"artifact_role": "provider_original_response_entity_bytes", "sha256": _sha(raw),
                                        "bytes": len(raw), "request_url": receipt["request_url"], "final_url": receipt["final_url"]},
                  "host_projection": {"artifact_role": "host_derived_projection", "sha256": projection_sha,
                                      "bytes": len(projection), "format": "one JSON metadata item per UTF-8 physical line with original provider JSON pointer",
                                      "lookup": lookup, "abstract_projected": False, "full_text_fetched": False,
                                      "urls_followed": False},
                  "builder_code_identity": _sha(Path(__file__).read_bytes()),
                  "access_license_status": "unknown; public retrieval and isOpenAccess do not establish reuse rights",
                  "mapping_status": "unresolved", "endpoint_eligibility": "unknown", "scientific_validation": False}
    provenance_raw = (json.dumps(provenance, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n").encode("utf-8")
    provenance_sha = _sha(provenance_raw)
    files = {"provider-response.json": raw, "host-projection.txt": projection, "host-provenance.json": provenance_raw}
    manifest = {"schema_version": "project-evidence-bundle-v1", "task_ref": task,
                "contributor": {"role": "operator_assistant", "label": "Public-source bridge / host-derived metadata"},
                "sources": [
                    {"id": "provider-response", "path": "sources/provider-response.json", "sha256": _sha(raw),
                     "url": receipt["request_url"], "media_type": "application/json",
                     "license_note": "Original provider HTTP entity bytes. Metadata reuse license and access terms are unverified/unknown; isOpenAccess is not a reuse grant."},
                    {"id": "host-projection", "path": "sources/host-projection.txt", "sha256": projection_sha,
                     "url": "urn:autoresearch:host-projection:sha256:" + projection_sha, "media_type": "text/plain",
                     "license_note": "Host-derived exact-DOI bibliographic projection, not provider original bytes or author confirmation. Underlying metadata licensing remains unknown."},
                    {"id": "host-provenance", "path": "sources/host-provenance.json", "sha256": provenance_sha,
                     "url": "urn:autoresearch:host-provenance:sha256:" + provenance_sha, "media_type": "application/json",
                     "license_note": "Host-generated acquisition record, not the provider response or author research evidence. Underlying source reuse/license status remains unknown."}],
                "selections": [
                    {"id": "doi-metadata", "source_id": "host-projection", "locator": _text_selection(projection),
                     "claim": "Host projects only exact DOI-matching bibliographic metadata; no object/channel/export-column mapping or ALP approval is established."},
                    {"id": "acquisition-provenance", "source_id": "host-provenance", "locator": _text_selection(provenance_raw),
                     "claim": "Host records request URLs, UTC time, HTTP status, response identity and derivation. Acquisition success does not establish reuse license or scientific eligibility."}],
                "remaining_questions": list(dict.fromkeys([
                    *(before.get("next_decision") or {}).get("next_action", {}).get("required_evidence", []),
                    "Bibliographic metadata does not replace author object/channel/export-column/batch mapping.",
                    "Metadata/full-text reuse licensing remains unknown unless separately verified."]))}
    _require(project.status()["snapshot_ref"] == before["snapshot_ref"], "STALE_STATE", "Project changed while preparing source metadata.")
    target.mkdir(parents=True, exist_ok=False)
    (target / "sources").mkdir(exist_ok=False)
    for name, value in files.items():
        with (target / "sources" / name).open("xb") as stream:
            stream.write(value)
    manifest_raw = canonical(manifest).encode("utf-8")
    with (target / "manifest.json").open("xb") as stream:
        stream.write(manifest_raw)
    captured, _ = evidence.capture_bundle(target, task)
    _require(project.status()["snapshot_ref"] == before["snapshot_ref"], "STALE_STATE", "Project changed before bundle completion.")
    return {"ok": True, "status": "prepared", "output": str(target), "task_ref": task,
            "project_state_version": before["state_version"], "manifest_sha256": _sha(manifest_raw),
            "bundle_snapshot_sha256": captured["snapshot_sha256"], "raw_response_sha256": _sha(raw),
            "projection_sha256": projection_sha, "provenance_sha256": provenance_sha, "lookup": lookup,
            "registered": False, "read_performed": False, "network_sent_this_call": False,
            "mapping_status": "unresolved", "endpoint_eligibility": "unknown", "scientific_validation": False}
