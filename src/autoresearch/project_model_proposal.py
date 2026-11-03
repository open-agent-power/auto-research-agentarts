"""One durable offline model proposal; transport, controller and slot finalization are separate."""

import base64
import copy
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import sqlite3

from . import project_model_protocol as protocol, project_controller
from .contracts import ResearchError, canonical, fingerprint, identifier
from .research_project import ResearchProject, safe_path, write_bytes_once
from .source_evidence_adapter import _read_file

TERMINAL = {"applied", "invalid", "stale", "failed"}


def _require(condition, code, message):
    if not condition:
        raise ResearchError(code, message)


def code_identity():
    return hashlib.sha256(Path(__file__).read_bytes() + Path(protocol.__file__).read_bytes()).hexdigest()


class ProjectModelProposal:
    def __init__(self, workspace):
        self.project = ResearchProject(workspace)
        self.directory = safe_path(self.project.root / "model-proposals")
        self.db = safe_path(self.directory / "journal.sqlite")

    @contextmanager
    def _connect(self, write=False):
        _require(write or self.db.is_file(), "ARTIFACT_NOT_FOUND", "No local-model proposal journal exists.")
        safe_path(self.db)
        con = sqlite3.connect(self.db.as_uri() + ("?mode=rwc" if write else "?mode=ro"), uri=True, timeout=5)
        con.row_factory = sqlite3.Row
        try:
            with con:
                if write:
                    con.execute("CREATE TABLE IF NOT EXISTS requests(request_id TEXT PRIMARY KEY, fingerprint TEXT NOT NULL, record TEXT NOT NULL)")
                else:
                    con.execute("BEGIN")
                yield con
        finally:
            con.close()

    def _writer(self):
        return ResearchProject(self.directory)._writer()

    @staticmethod
    def _decode(row):
        _require(row is not None, "ARTIFACT_NOT_FOUND", "No saved local-model request matches this identifier.")
        record = json.loads(row["record"])
        _require(record["request_sha256"] == row["fingerprint"] == fingerprint(record["prepare_request"])
                 and record["record_sha256"] == fingerprint({k: v for k, v in record.items() if k != "record_sha256"})
                 and record["payload_sha256"] == fingerprint(record["payload"]),
                 "EVIDENCE_CHANGED", "Saved local-model request or journal record changed.")
        return record

    def _save(self, record, *, create=False):
        record["record_sha256"] = fingerprint({k: v for k, v in record.items() if k != "record_sha256"})
        with self._connect(True) as con:
            if create:
                con.execute("INSERT INTO requests VALUES(?,?,?)", (record["request_id"], record["request_sha256"], canonical(record)))
            else:
                changed = con.execute("UPDATE requests SET record=? WHERE request_id=? AND fingerprint=?",
                                      (canonical(record), record["request_id"], record["request_sha256"])).rowcount
                _require(changed == 1, "EVIDENCE_CHANGED", "The original model-request journal row changed.")

    def read(self, request_id):
        identifier(request_id)
        with self._connect() as con:
            record = self._decode(con.execute("SELECT * FROM requests WHERE request_id=?", (request_id,)).fetchone())
        _require(record["project_id"] == self.project.status()["id"], "EVIDENCE_CHANGED", "Model request belongs to another project.")
        return copy.deepcopy(record)

    def status(self, request_id=None):
        if request_id is not None:
            return self.read(request_id)
        state = self.project.status()
        records = []
        if self.db.is_file():
            with self._connect() as con:
                records = [{key: record.get(key) for key in ("request_id", "status", "context_sha256", "payload_sha256", "response_sha256", "controller_request_id", "outcome")}
                           for record in (self._decode(row) for row in con.execute("SELECT * FROM requests ORDER BY rowid"))]
        return {"schema_version": "project-model-proposals-status-v1", "project_id": state["id"], "requests": records,
                "budget": copy.deepcopy(state["budget"]), "scientific_validation": False}

    def _key(self, record):
        return fingerprint({"project_id": record["project_id"], "request_id": record["request_id"]})

    def _paths(self, record):
        key = self._key(record)
        return (safe_path(self.directory / "responses" / (key + ".bin")),
                safe_path(self.directory / "responses" / (key + ".transport.json")))

    def prepare(self, request_id, expected_state_version, transport_identity):
        identifier(request_id)
        identity = protocol.validate_transport_identity(transport_identity)
        prepare_request = {"request_id": request_id, "project_id": self.project.status()["id"],
                           "expected_state_version": expected_state_version, "transport_identity": identity}
        digest = fingerprint(prepare_request)
        self.directory.mkdir(exist_ok=True)
        with self._writer():
            with self._connect(True) as con:
                row = con.execute("SELECT * FROM requests WHERE request_id=?", (request_id,)).fetchone()
                if row is not None:
                    record = self._decode(row)
                    _require(record["request_sha256"] == digest, "IDEMPOTENCY_CONFLICT", "Model preparation content changed.")
                    return record
            slot = self.project.reserve_local_model_slot(request_id=request_id, expected_state_version=expected_state_version,
                                                         transport_identity=identity)
            state = self.project.status()
            _require(slot["status"] == "reserved" and state["state_version"] == slot["state_version_after"],
                     "STALE_STATE", "The original reserved state changed before context sealing.")
            context = project_controller.ProjectController(self.project.root).selection_context()
            _require(context["snapshot_ref"] == state["snapshot_ref"], "STALE_STATE", "Project changed while sealing its model request.")
            payload = protocol.build_request(context, identity)
            record = {"schema_version": "project-model-proposal-record-v1", "request_id": request_id, "request_sha256": digest,
                      "prepare_request": prepare_request, "project_id": state["id"], "run_id": state["run_id"], "slot": slot,
                      "journal_code_identity": code_identity(), "controller_code_identity": project_controller.code_identity(),
                      "transport_identity": identity, "context": context, "context_sha256": context["context_sha256"],
                      "payload": payload, "payload_sha256": fingerprint(payload), "status": "prepared", "response_sha256": None,
                      "raw_response_base64": None, "transport_receipt": None, "proposal": None, "controller_result": None,
                      "controller_request_id": "model-selection-" + self._key({"project_id": state["id"], "request_id": request_id})[:32],
                      "outcome": None, "host_local_model_receipt": None, "scientific_validation": False}
            self._save(record, create=True)
            return copy.deepcopy(record)

    def _received(self, record, raw, receipt):
        _require(type(raw) is bytes and 0 < len(raw) <= 2 * 1024 * 1024, "INVALID_MODEL_RESPONSE", "A bounded original native response is required.")
        raw_path, receipt_path = self._paths(record)
        raw_path.parent.mkdir(exist_ok=True)
        write_bytes_once(raw_path, raw)  # Original response is durable before parsing or consuming it.
        try:
            receipt_raw = canonical(receipt).encode("utf-8")
            _require(len(receipt_raw) <= 64 * 1024, "INVALID_TRANSPORT_RECEIPT", "Transport receipt is too large.")
        except (TypeError, ValueError, RecursionError, ResearchError):
            receipt = {"invalid_transport_receipt": True}
            receipt_raw = canonical(receipt).encode("utf-8")
        write_bytes_once(receipt_path, receipt_raw)
        record.update(status="received", response_sha256=hashlib.sha256(raw).hexdigest(), raw_response_base64=base64.b64encode(raw).decode("ascii"),
                      transport_receipt=copy.deepcopy(receipt))
        self._save(record)
        return record

    def request(self, request_id, transport):
        identifier(request_id)
        with self._writer():
            record = self.read(request_id)
            if record["status"] == "prepared":
                _require(record["journal_code_identity"] == code_identity() and record["controller_code_identity"] == project_controller.code_identity(),
                         "CODE_CHANGED", "The prepared request requires its original implementation.")
                _require(protocol.validate_transport_identity(transport.identity()) == record["transport_identity"],
                         "MODEL_CHANGED", "The transport differs from the frozen offline model identity.")
                _require(self.project.status()["snapshot_ref"] == record["context"]["snapshot_ref"], "STALE_STATE", "Project changed before model dispatch.")
                record["status"] = "sending"
                self._save(record)
                try:
                    raw, receipt = transport.send(copy.deepcopy(record["payload"]), request_id)
                    return copy.deepcopy(self._received(record, raw, receipt))
                except Exception as error:
                    reference = getattr(error, "preflight_no_dispatch", None)
                    if reference is not None:
                        try:
                            from .project_local_model import validate_preflight_no_dispatch
                            proof = validate_preflight_no_dispatch(reference, request_id, record["payload_sha256"], record["transport_identity"])
                            _require(proof["failure_code"] == getattr(error, "code", type(error).__name__),
                                     "INVALID_PREFLIGHT_PROOF", "Preflight failure code differs from its bound error.")
                            record.update(status="prepared", preflight_failure={"code": proof["failure_code"],
                                "reference": copy.deepcopy(reference), "proof": proof, "automatic_retry": False})
                            record.pop("error", None)
                            self._save(record)
                            return copy.deepcopy(record)
                        except (ResearchError, OSError, ValueError, KeyError, TypeError):
                            pass  # A missing or invalid proof is still an unknown send, never a reset.
                    record.update(status="unknown", error={"code": getattr(error, "code", "MODEL_SEND_UNKNOWN"), "automatic_retry": False})
                    self._save(record)
                    return copy.deepcopy(record)
            if record["status"] in {"sending", "unknown"}:
                raw_path, receipt_path = self._paths(record)
                if raw_path.is_file() and receipt_path.is_file():
                    raw = _read_file(raw_path, 2 * 1024 * 1024)
                    receipt = json.loads(_read_file(receipt_path, 64 * 1024))
                    return copy.deepcopy(self._received(record, raw, receipt))
                return record  # Ambiguous sending is never sent again, even on explicit replay.
            return record


    def _finalize(self, record):
        proof = {"schema_version": "project-model-finalization-v1", "project_id": record["project_id"], "run_id": record["run_id"],
                 "request_id": record["request_id"], "slot_request_sha256": record["slot"]["request_sha256"],
                 "context_sha256": record["context_sha256"], "payload_sha256": record["payload_sha256"],
                 "response_sha256": record["response_sha256"], "outcome": record["outcome"],
                 "transport_receipt_sha256": fingerprint(record["transport_receipt"]),
                 "controller_request_id": record["controller_request_id"], "controller_result_sha256": fingerprint(record["controller_result"])}
        proof["sha256"] = fingerprint(proof)
        target = safe_path(self.directory / "receipts" / (self._key(record) + ".json"))
        target.parent.mkdir(exist_ok=True)
        write_bytes_once(target, canonical(proof).encode("utf-8"))
        final = self.project.finalize_local_model_slot(request_id=record["request_id"], outcome=record["outcome"], receipt_sha256=proof["sha256"])
        record.update(status=record["outcome"], finalization=final)
        self._save(record)
        return copy.deepcopy(record)

    def consume(self, request_id):
        identifier(request_id)
        with self._writer():
            record = self.read(request_id)
            if record["status"] in TERMINAL:
                return record
            _require(record["status"] in {"received", "consumed"}, "MODEL_RESPONSE_NOT_RECEIVED", "Only a saved known response can be consumed; unknown requests are never resent.")
            if record["status"] == "consumed":
                return self._finalize(record)
            _require(record["journal_code_identity"] == code_identity() and record["controller_code_identity"] == project_controller.code_identity(),
                     "CODE_CHANGED", "Consume the original response with its frozen implementation.")
            raw_path, receipt_path = self._paths(record)
            raw = _read_file(raw_path, 2 * 1024 * 1024)
            _require(hashlib.sha256(raw).hexdigest() == record["response_sha256"]
                     and base64.b64decode(record["raw_response_base64"], validate=True) == raw
                     and json.loads(_read_file(receipt_path, 64 * 1024)) == record["transport_receipt"],
                     "EVIDENCE_CHANGED", "Saved original response or transport receipt changed.")
            try:
                proposal = protocol.parse_response(raw, record["context"], record["transport_receipt"])
                record["proposal"] = proposal
                execution = record["transport_receipt"].get("execution")
                record["host_local_model_receipt"] = {"identity": copy.deepcopy(record["transport_identity"]), "execution": execution,
                    "request_sha256": record["payload_sha256"], "response_sha256": record["response_sha256"],
                    "transport_receipt_sha256": fingerprint(record["transport_receipt"]), "model_execution_verified": execution == "local_model",
                    "fixture": execution == "fixture", "scientific_validation": False}
                self._save(record)
                state = self.project.status()
                parent = next((item for item in state.get("controller_requests", []) if item["request_id"] == record["controller_request_id"]), None)
                if parent and parent["child_request_id"]:
                    with self.project._connect(readonly=True) as con:
                        child = self.project._action(con, parent["child_request_id"])
                    if child and child["status"] in {"running", "pending", "unknown"}:
                        record["consume_error"] = {"code": "EXECUTION_UNKNOWN", "automatic_retry": False}
                        self._save(record)
                        return record
                result = project_controller.ProjectController(self.project.root).advance_selection(request_id=record["controller_request_id"],
                    proposal=proposal, expected_state_version=record["context"]["state_version"])
                if result["status"] in {"prepared", "running", "unknown", "needs_review"}:
                    record.update(controller_result=result, consume_error={"code": "EXECUTION_UNKNOWN", "automatic_retry": False})
                    self._save(record)
                    return record
                record.update(controller_result=result, outcome="failed" if result["status"] == "failed" else "applied")
            except ResearchError as error:
                if error.code in {"PROJECT_BUSY", "EXECUTION_UNKNOWN", "CODE_CHANGED", "EVIDENCE_CHANGED", "UNSAFE_PATH"}:
                    record["consume_error"] = {"code": error.code, "automatic_retry": False}
                    self._save(record)
                    return record
                state = self.project.status()
                parent = next((item for item in state.get("controller_requests", []) if item["request_id"] == record["controller_request_id"]), None)
                if parent and parent["status"] == "failed":
                    record.update(outcome="failed", controller_result=project_controller.ProjectController._response(parent, True))
                else:
                    record["outcome"] = "stale" if error.code in {"STALE_STATE", "STALE_SELECTION_CONTEXT"} else "invalid"
                record["consume_error"] = {"code": error.code, "automatic_retry": False}
            record["status"] = "consumed"
            self._save(record)
            return self._finalize(record)
