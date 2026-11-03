"""One bounded Europe PMC DOI request, reserved in the existing project ledger."""
import copy
from datetime import datetime, timezone
import hashlib
from http.client import HTTPException
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import threading
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

from .contracts import ResearchError, fingerprint, identifier
from .research_project import ResearchProject, code_identity as core_identity, require, safe_path, write_bytes_once, write_once
from .source_evidence_adapter import _json_object, _read_file, _reject_constant, _task


ENDPOINT = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
MAX_RESPONSE_BYTES = 2 * 1024 * 1024
TIMEOUT_SECONDS = 30
SOURCE_REQUEST_LIMIT = 8
SAFE_HEADERS = ("content-type", "content-length", "date", "etag", "last-modified", "cache-control", "retry-after")


def code_identity():
    return hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


def _doi(value):
    require(type(value) is str and re.fullmatch(r"10\.[0-9]{4,9}/[A-Za-z0-9][A-Za-z0-9._;()/:+\-]{0,199}", value),
            "INVALID_DOI", "Supply a DOI identifier using the supported bounded ASCII syntax, not a URL or query.")
    return value.lower()


def _url(doi):
    return ENDPOINT + "?" + urlencode({"query": 'DOI:"' + doi + '"', "format": "json", "resultType": "core", "pageSize": 5})


def _decode(raw):
    def finite_float(value):
        number = float(value)
        if not math.isfinite(number):
            raise ValueError("Non-finite JSON number")
        return number
    data = json.loads(raw.decode("utf-8"), object_pairs_hook=_json_object, parse_constant=_reject_constant, parse_float=finite_float)
    require(type(data) is dict and type(data.get("hitCount")) is int and data["hitCount"] >= 0
            and type(data.get("resultList")) is dict and type(data["resultList"].get("result")) is list,
            "INVALID_SOURCE_RESPONSE", "A complete Europe PMC search response with hitCount and resultList is required.")
    records = data["resultList"]["result"]
    require(len(records) <= min(data["hitCount"], 5) and (bool(records) == bool(data["hitCount"]))
            and all(type(record) is dict for record in records),
            "INVALID_SOURCE_RESPONSE", "Europe PMC search result counts or entries are inconsistent.")
    return data


def _outcome(raw, metadata):
    if metadata["truncated"]:
        return "failed", {"code": "SOURCE_RESPONSE_TOO_LARGE", "message": "Response exceeds the fixed 2 MiB limit; saved bytes are a prefix."}, None
    if not metadata["response_body_complete"]:
        return "unknown", {"code": "SOURCE_REQUEST_UNKNOWN", "message": "Transport did not save a complete response; never resend this request."}, None
    if metadata["http_status"] != 200:
        return "failed", {"code": "SOURCE_HTTP_ERROR", "message": "Europe PMC returned HTTP " + str(metadata["http_status"]) + "; no automatic retry."}, None
    if metadata["final_url"] != metadata["request_url"]:
        return "failed", {"code": "SOURCE_REDIRECT_REJECTED", "message": "The fixed endpoint identity changed."}, None
    if metadata["content_type"].split(";", 1)[0].strip().lower() != "application/json" or metadata.get("content_encoding", "identity").lower() not in ("", "identity"):
        return "failed", {"code": "INVALID_SOURCE_RESPONSE", "message": "Expected an uncompressed JSON response from the fixed endpoint."}, None
    try:
        data = _decode(raw)
    except (ResearchError, ValueError, UnicodeError, TypeError, KeyError, RecursionError):
        return "failed", {"code": "INVALID_SOURCE_RESPONSE", "message": "Saved response is not a valid, complete Europe PMC JSON result."}, None
    records = data["resultList"]["result"]
    matches = [record for record in records if type(record.get("doi")) is str and record["doi"].lower() == metadata["doi"]]
    return "received", None, {"hit_count": data["hitCount"], "returned_count": len(records), "exact_doi_matches": len(matches),
                                "notice": "Zero matches describe this lookup only; neither presence nor absence establishes scientific endpoint mapping."}


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _transport_worker(output, metadata):
    """Owned subprocess has no project writes; the host can stop it at a wall deadline."""
    folder = safe_path(Path(output))
    require(metadata["request_url"] == _url(_doi(metadata["doi"])), "INVALID_REQUEST", "Worker URL is outside the fixed DOI endpoint.")
    raw, complete, truncated = bytearray(), False, False
    response = None
    metadata = copy.deepcopy(metadata)
    metadata.update(http_status=None, safe_headers={}, content_type="", content_encoding="identity", final_url=metadata["request_url"])
    try:
        request = Request(metadata["request_url"], method="GET", headers={"Accept": "application/json", "Accept-Encoding": "identity"})
        opener = build_opener(ProxyHandler({}), _NoRedirect())
        try:
            response = opener.open(request, timeout=TIMEOUT_SECONDS)
        except HTTPError as error:
            response = error  # Known HTTP failures still preserve their bounded original body.
        metadata["http_status"] = response.getcode()
        metadata["final_url"] = response.geturl()
        for name in SAFE_HEADERS:
            value = response.headers.get(name)
            if value is not None and len(value) <= 2048 and "\r" not in value and "\n" not in value:
                metadata["safe_headers"][name] = value
        metadata["content_type"] = metadata["safe_headers"].get("content-type", "")
        metadata["content_encoding"] = response.headers.get("content-encoding", "identity")[:160]
        while len(raw) <= MAX_RESPONSE_BYTES:
            chunk = response.read(min(65536, MAX_RESPONSE_BYTES + 1 - len(raw)))
            if not chunk:
                complete = True
                break
            raw.extend(chunk)
        if len(raw) > MAX_RESPONSE_BYTES:
            del raw[MAX_RESPONSE_BYTES:]
            truncated = True
        expected_length = response.headers.get("content-length")
        if complete and expected_length is not None and (not expected_length.isdecimal() or int(expected_length) != len(raw)):
            complete = False
    except (URLError, OSError, HTTPException, ValueError, UnicodeError):
        pass  # A missing/partial response is unknown, never an empty search result.
    finally:
        if response is not None:
            response.close()
    metadata.update(schema_version="europe-pmc-response-v1", acquired_at_utc=datetime.now(timezone.utc).isoformat(),
                    raw_sha256=hashlib.sha256(raw).hexdigest(), raw_bytes=len(raw), response_body_complete=complete,
                    truncated=truncated, access_license_unknown=True, scientific_validation=False)
    status, failure, lookup = _outcome(bytes(raw), metadata)
    metadata.update(status=status, failure=failure, lookup=lookup)
    write_bytes_once(folder / "response.bin", bytes(raw))
    write_once(folder / "response.json", metadata)  # Receipt is the final publication marker.


def _worker_main(output):
    # Also bounds an orphan after a hard host exit; a socket timeout alone does not bound DNS or a slow body.
    deadline = threading.Timer(TIMEOUT_SECONDS, lambda: os._exit(124))
    deadline.daemon = True
    deadline.start()
    try:
        folder = safe_path(Path(output).absolute())
        metadata = json.loads(_read_file(folder / "request.json", 65536), object_pairs_hook=_json_object, parse_constant=_reject_constant)
        _transport_worker(folder, metadata)
    finally:
        deadline.cancel()


class EuropePmcSource:
    def __init__(self, workspace):
        self.project = ResearchProject(workspace)

    @staticmethod
    def _record(project, request_id):
        return next((item for item in project.get("source_requests", []) if item["request_id"] == request_id), None)

    @staticmethod
    def _counts(project):
        records = project.get("source_requests", [])
        project["budget"].setdefault("source_request_limit", SOURCE_REQUEST_LIMIT)
        project["budget"].update(source_requests_dispatched=len(records),
                                 source_requests_used=sum(item["status"] in ("received", "failed") for item in records),
                                 source_requests_reserved=sum(item["status"] in ("sending", "unknown") for item in records))

    def _load_receipt(self, record):
        folder = safe_path(Path(record["output"]))
        path = safe_path(folder / "response.json")
        if not path.exists():
            return None
        try:
            receipt_raw = _read_file(path, 65536)
            receipt = json.loads(receipt_raw, object_pairs_hook=_json_object, parse_constant=_reject_constant)
            for key, expected in record["receipt_binding"].items():
                require(receipt[key] == expected, "EVIDENCE_CHANGED", "Source receipt binding changed.")
            require(receipt["schema_version"] == "europe-pmc-response-v1" and receipt["access_license_unknown"] is True
                    and receipt["scientific_validation"] is False and type(receipt["safe_headers"]) is dict
                    and set(receipt["safe_headers"]) <= set(SAFE_HEADERS)
                    and all(type(value) is str and len(value) <= 2048 and "\r" not in value and "\n" not in value
                            for value in receipt["safe_headers"].values())
                    and type(receipt["content_type"]) is str and type(receipt["content_encoding"]) is str
                    and receipt["content_type"] == receipt["safe_headers"].get("content-type", "")
                    and type(receipt["response_body_complete"]) is bool and type(receipt["truncated"]) is bool
                    and (receipt["http_status"] is None or type(receipt["http_status"]) is int)
                    and type(receipt["raw_bytes"]) is int and 0 <= receipt["raw_bytes"] <= MAX_RESPONSE_BYTES,
                    "EVIDENCE_CHANGED", "Source response receipt metadata is invalid.")
            require(datetime.fromisoformat(receipt["acquired_at_utc"]).utcoffset().total_seconds() == 0,
                    "EVIDENCE_CHANGED", "Source receipt acquisition time must be UTC.")
            raw_path = safe_path(folder / "response.bin")
            if receipt["raw_bytes"] == 0:
                require(raw_path.stat().st_size == 0, "EVIDENCE_CHANGED", "Empty response bytes changed.")
                with raw_path.open("rb") as stream:
                    raw = stream.read(1)
                require(raw == b"" and raw_path.stat().st_size == 0, "EVIDENCE_CHANGED", "Empty response bytes changed while reading.")
            else:
                raw = _read_file(raw_path, MAX_RESPONSE_BYTES)
            require(len(raw) == receipt["raw_bytes"] and hashlib.sha256(raw).hexdigest() == receipt["raw_sha256"],
                    "EVIDENCE_CHANGED", "Saved response bytes or length changed.")
            require(not record.get("receipt_sha256") or hashlib.sha256(receipt_raw).hexdigest() == record["receipt_sha256"],
                    "EVIDENCE_CHANGED", "Saved response receipt changed.")
            status, failure, lookup = _outcome(raw, receipt)
            require((receipt["status"], receipt["failure"], receipt["lookup"]) == (status, failure, lookup),
                    "EVIDENCE_CHANGED", "Source receipt interpretation differs from its original bytes.")
            return receipt, hashlib.sha256(receipt_raw).hexdigest()
        except ResearchError:
            raise
        except (OSError, ValueError, KeyError, TypeError, AttributeError, UnicodeError, RecursionError):
            raise ResearchError("EVIDENCE_CHANGED", "Saved source response or receipt is incomplete or malformed.") from None

    def _recover_locked(self, project, record):
        require(record["request_sha256"] == fingerprint(record["request"]), "EVIDENCE_CHANGED", "Saved source request identity changed.")
        loaded = self._load_receipt(record)
        if loaded is not None:
            receipt, digest = loaded
            changed = record["status"] != receipt["status"] or record.get("receipt_sha256") != digest
            record.update(status=receipt["status"], receipt_sha256=digest, failure=receipt["failure"])
        else:
            require(record["status"] in ("sending", "unknown"), "EVIDENCE_CHANGED", "A previously saved response receipt is missing.")
            changed = record["status"] != "unknown"
            record.update(status="unknown", failure={"code": "SOURCE_REQUEST_UNKNOWN", "message": "No complete saved response receipt; preserve the reservation and do not resend."})
        if changed:
            project["state_version"] += 1
            self._counts(project)
            with self.project._connect() as con:
                self.project._save(con, project)
        return self._view(record, loaded[0] if loaded else None, replayed=True)

    @staticmethod
    def _view(record, receipt, *, replayed):
        return {"schema_version": "project-source-request-v1", "request_id": record["request_id"], "project_id": record["project_id"],
                "status": record["status"], "output": record["output"], "receipt": receipt,
                "failure": record.get("failure"), "replayed": replayed, "network_sent_this_call": not replayed,
                "source_request_limit": record["source_request_limit"], "scientific_validation": False}

    def status(self, request_id):
        """Offline recovery and metadata only; never open a network connection."""
        identifier(request_id)
        with self.project._writer():
            with self.project._connect(readonly=True) as con:
                project = self.project._project(con)
            record = self._record(project, request_id)
            require(record is not None, "SOURCE_REQUEST_NOT_FOUND", "No source request has this ID.")
            return self._recover_locked(project, record)

    def fetch(self, request_id, doi, output):
        identifier(request_id)
        doi = _doi(doi)
        folder = safe_path(Path(output).absolute())
        with self.project._writer():
            with self.project._connect(readonly=True) as con:
                project = self.project._project(con)
                owner = self.project._action(con, request_id)
            old = self._record(project, request_id)
            if old is not None:
                require(old["doi"] == doi and old["output"] == str(folder), "IDEMPOTENCY_CONFLICT", "Source request DOI or fixed output changed.")
                require(old["request_sha256"] == fingerprint(old["request"]), "EVIDENCE_CHANGED", "Saved source request identity changed.")
                return self._recover_locked(project, old)  # Replay precedes current code/task checks.
            require(owner is None, "IDEMPOTENCY_CONFLICT", "Request ID belongs to an existing action or replay.")
            self.project._require_unclaimed(project, request_id)
            require(not any(item["request_id"] == request_id for key in ("code_revisions", "evidence_registrations", "controller_requests")
                            for item in project.get(key, [])), "IDEMPOTENCY_CONFLICT", "Request ID belongs to another command.")
            require(project["budget"].get("source_request_limit", SOURCE_REQUEST_LIMIT) == SOURCE_REQUEST_LIMIT,
                    "CONFIG_CHANGED", "The fixed source request allowance cannot change.")
            require(not any(item["status"] in ("sending", "unknown") for item in project.get("source_requests", [])),
                    "SOURCE_REQUEST_UNKNOWN", "Recover the original source request first; its reservation cannot be resent or bypassed.")
            require(len(project.get("source_requests", [])) < SOURCE_REQUEST_LIMIT,
                    "SOURCE_BUDGET_EXHAUSTED", "This project's frozen eight-request allowance is exhausted; output changes cannot reset it.")
            current = self.project.status()
            self.project._require_fresh(project, current, None)
            require(not any(item["status"] in ("prepared", "running") for item in project.get("controller_requests", [])),
                    "PROJECT_BUSY", "Finish the accepted controller request before fetching a source.")
            self.project._source(project)
            require(bool(project.get("evidence_task_ref")), "TASK_NOT_AVAILABLE", "No source evidence task is bound yet.")
            task = _task(project.get("evidence_task_ref"))
            require(task["project_id"] == project["id"], "TASK_MISMATCH", "The current source task belongs to another project.")
            primary = next((item for item in current["actions"] if item["id"] == task["based_on_action_id"] and item["status"] == "completed"), None)
            require(primary is not None, "TASK_NOT_AVAILABLE", "A completed original primary action must bind the source task.")
            require(not folder.exists() and not self.project.root.is_relative_to(folder) and not folder.is_relative_to(self.project.root),
                    "OUTPUT_EXISTS", "Use a new output directory separate from the existing project.")
            request = {"command": "source.fetch.europe-pmc", "project_id": project["id"], "task_ref": task, "doi": doi,
                       "request_url": _url(doi), "timeout_seconds": TIMEOUT_SECONDS, "max_response_bytes": MAX_RESPONSE_BYTES}
            require(not any(item["request_sha256"] == fingerprint(request) and item["status"] != "failed"
                            for item in project.get("source_requests", [])),
                    "SOURCE_ALREADY_REQUESTED", "This task-bound DOI response or unresolved request already exists; use its original request ID.")
            identities = {"core": core_identity(), "connector": code_identity()}
            binding = {"request_id": request_id, "project_id": project["id"], "task_ref": task, "doi": doi,
                       "request_url": request["request_url"], "request_sha256": fingerprint(request), "code_identity": identities}
            record = {"schema_version": "project-source-request-v1", "request_id": request_id, "project_id": project["id"],
                      "doi": doi, "request": request, "request_sha256": fingerprint(request), "output": str(folder),
                      "raw_response_path": str(folder / "response.bin"), "receipt_path": str(folder / "response.json"),
                      "receipt_binding": binding, "code_identity": identities, "primary_action_id": primary["id"],
                      "source_request_limit": SOURCE_REQUEST_LIMIT,
                      "state_version_before": project["state_version"], "status": "sending", "failure": None}
            folder.mkdir(parents=True)
            project.setdefault("source_requests", []).append(record)
            project["state_version"] += 1
            record["dispatch_state_version"] = project["state_version"]
            self._counts(project)
            with self.project._connect() as con:
                self.project._save(con, project)  # Commit reservation before opening any socket.
            write_once(folder / "request.json", binding)
            environment = os.environ.copy()
            environment["PYTHONPATH"] = str(Path(__file__).resolve().parents[1])
            process = None
            try:
                process = subprocess.Popen([sys.executable, "-m", "autoresearch.europe_pmc", str(folder)],
                                           stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                           env=environment, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                try:
                    process.wait(timeout=TIMEOUT_SECONDS)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
            except (OSError, subprocess.SubprocessError):
                pass  # Reservation remains unknown even if transport could not start.
            finally:
                if process is not None and process.poll() is None:
                    process.kill()
            result = self._recover_locked(project, record)
            sent = bool(result["receipt"] and result["receipt"]["http_status"] is not None) if process is not None else False
            result.update(replayed=False, network_sent_this_call=True if sent else None if process is not None else False)
            return result


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit(2)
    _worker_main(sys.argv[1])
