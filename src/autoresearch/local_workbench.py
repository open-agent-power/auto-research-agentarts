"""Host-owned local inputs and active selection; research stays in ResearchProject."""

import base64
import binascii
import copy
from contextlib import contextmanager
import hashlib
from pathlib import Path
import re
import sqlite3

from . import source_evidence_adapter as reader, tabular_quality_adapter as tabular, method_registry as registry, project_controller
from .contracts import ResearchError, canonical, fingerprint, identifier
from .project_controller import ProjectController
from .host_model_selection import HostModelSelection
from .host_model_report import host_model_report_current
from .research_project import ResearchProject, safe_path, write_bytes_once

MAX_PROJECTS = 32


def batch_code_identity():
    """Bind unfinished grants to the local orchestration implementation too."""
    return hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


def _require(condition, code, message):
    if not condition:
        raise ResearchError(code, message)


def _body(body, fields):
    _require(type(body) is dict and set(body) == set(fields), "INVALID_REQUEST", "Use the exact local workbench command fields.")
    identifier(body["request_id"])
    try:
        return fingerprint(body)
    except (TypeError, ValueError, RecursionError):
        raise ResearchError("INVALID_REQUEST", "A finite JSON command is required.") from None


def _text(value, limit):
    return type(value) is str and 0 < len(value) <= limit and bool(value.strip()) and "\x00" not in value


def _decode(value, limit):
    _require(type(value) is str and 0 < len(value) <= 4 * ((limit + 2) // 3), "INVALID_REQUEST", "Bounded base64 original bytes required.")
    try:
        raw = base64.b64decode(value, validate=True)
    except (ValueError, binascii.Error):
        raise ResearchError("INVALID_REQUEST", "Strict base64 original bytes required.") from None
    _require(0 < len(raw) <= limit, "SOURCE_TOO_LARGE", "Original bytes are empty or exceed the input limit.")
    return raw


class LocalWorkbench:
    def __init__(self, root):
        self.root = safe_path(Path(root).absolute())
        _require(not (self.root / "project.sqlite").exists(), "WORKBENCH_OVERLAP", "Use a separate local workbench root.")
        self.root.mkdir(parents=True, exist_ok=True)
        self.db = safe_path(self.root / "workbench.sqlite")
        with self._writer(), self._connect() as con:
            con.executescript("CREATE TABLE IF NOT EXISTS metadata(key TEXT PRIMARY KEY, value TEXT NOT NULL);"
                              "CREATE TABLE IF NOT EXISTS projects(id TEXT PRIMARY KEY, goal TEXT NOT NULL, slot TEXT NOT NULL, report TEXT);"
                              "CREATE TABLE IF NOT EXISTS requests(id TEXT PRIMARY KEY, digest TEXT NOT NULL, command TEXT NOT NULL, record TEXT NOT NULL);")
            con.execute("INSERT OR IGNORE INTO metadata VALUES('schema_version','local-research-workbench-v1')")
            _require(con.execute("SELECT value FROM metadata WHERE key='schema_version'").fetchone()[0] == "local-research-workbench-v1",
                     "WORKBENCH_CHANGED", "Unsupported local workbench schema.")

    def _writer(self):
        # A separate manager-root OS lock; each child still acquires its core lock.
        return ResearchProject(self.root)._writer()

    @contextmanager
    def _connect(self, readonly=False):
        safe_path(self.db)
        con = sqlite3.connect(self.db.as_uri() + ("?mode=ro" if readonly else "?mode=rwc"), uri=True, timeout=5)
        con.row_factory = sqlite3.Row
        try:
            with con:
                if readonly:
                    con.execute("BEGIN")
                yield con
        finally:
            con.close()

    @staticmethod
    def _active(con):
        row = con.execute("SELECT value FROM metadata WHERE key='active_project_id'").fetchone()
        return row[0] if row else None

    def _project(self, con, project_id, *, active=False):
        identifier(project_id, "project_id")
        if active:
            _require(self._active(con) == project_id, "STALE_STATE", "The active project changed; reload before submitting.")
        row = con.execute("SELECT * FROM projects WHERE id=?", (project_id,)).fetchone()
        _require(row is not None, "PROJECT_NOT_FOUND", "No managed local project matches this identifier.")
        _require(type(row["slot"]) is str and re.fullmatch(r"[a-f0-9]{64}", row["slot"]), "WORKBENCH_CHANGED", "Managed project identity changed.")
        return row, ResearchProject(safe_path(self.root / "projects" / row["slot"]))

    @staticmethod
    def _old(con, body, digest):
        row = con.execute("SELECT * FROM requests WHERE id=?", (body["request_id"],)).fetchone()
        if row is None:
            return None
        _require(row["digest"] == digest, "IDEMPOTENCY_CONFLICT", "Local request ID is already bound to different content.")
        return tabular._parse(row["record"].encode("utf-8"))

    @staticmethod
    def _save(con, request_id, record):
        con.execute("UPDATE requests SET record=? WHERE id=?", (canonical(record), request_id))

    @staticmethod
    def _accept(con, body, digest, command, intent):
        record = {"status": "preparing", "intent": intent, "result": None}
        con.execute("INSERT INTO requests VALUES(?,?,?,?)", (body["request_id"], digest, command, canonical(record)))
        return record

    @staticmethod
    def _response(command, request_id, project_id, **values):
        return {"schema_version": "local-workbench-command-v1", "command": command, "request_id": request_id,
                "project_id": project_id, "replayed": False, **values}

    @staticmethod
    def _completed(old):
        _require(old["status"] == "completed" and type(old["result"]) is dict,
                 "OPERATION_INCOMPLETE", "The original operation did not complete; preserved inputs and intent require inspection.")
        return dict(copy.deepcopy(old["result"]), replayed=True)

    def _incomplete(self, request_id, record, error):
        record.update(status="incomplete", failure={"code": getattr(error, "code", "WORKBENCH_OPERATION_FAILED"), "automatic_retry": False})
        with self._connect() as con:
            self._save(con, request_id, record)

    def describe(self):
        with self._connect(readonly=True) as con:
            projects = [{"id": row["id"], "goal": row["goal"]} for row in con.execute("SELECT id,goal FROM projects ORDER BY rowid")]
            active = self._active(con)
            pending = []
            for row in con.execute("SELECT id,command,record FROM requests WHERE command IN ('create','export','evidence','batch') ORDER BY rowid DESC"):
                record = tabular._parse(row["record"].encode("utf-8"))
                if record["status"] != "completed":
                    pending.append({"request_id": row["id"], "command": row["command"], "status": record["status"],
                                    "project_id": (record.get("result") or {}).get("project_id", record["intent"].get("project_id"))})
                    if len(pending) == 8:
                        break
            batches = []
            for row in con.execute("SELECT id,digest,record FROM requests WHERE command='batch' ORDER BY rowid DESC LIMIT 8"):
                record = tabular._parse(row["record"].encode("utf-8"))
                self._check_batch_record(record, row["digest"])
                batches.append({"request_id": row["id"], "project_id": record["body"]["project_id"],
                                "status": (record.get("result") or {}).get("status", record["status"]),
                                "record_status": record["status"], "body": copy.deepcopy(record["body"]), "result": copy.deepcopy(record["result"])})
        return {"schema_version": "local-research-workbench-v1", "active_project_id": active, "projects": projects,
                "pending_requests": pending, "batches": batches,
                "constraints": {"max_projects": MAX_PROJECTS, "max_csv_bytes": tabular.MAX_CSV_BYTES, "max_spec_bytes": tabular.MAX_SPEC_BYTES,
                    "max_tool_calls": [1, 2], "local_tool_limit_choices": [1, 2], "model_requests_allowed": 0, "new_fits": 0,
                    "existing_cash_cap_cny": 5, "historical_costs": "unknown", "automatic_retry": False}}

    def binding(self):
        with self._connect(readonly=True) as con:
            active = self._active(con)
            if active is None:
                return None, None
            row, project = self._project(con, active)
            report = row["report"]
        _require(report is None or re.fullmatch(r"[a-f0-9]{64}", report), "WORKBENCH_CHANGED", "Managed report identity changed.")
        return project, safe_path(self.root / "reports" / report) if report else None

    def create(self, body):
        digest = _body(body, ("request_id", "goal", "budget_ref", "max_tool_calls", "input"))
        _require(_text(body["goal"], 4000) and _text(body["budget_ref"], 500) and type(body["max_tool_calls"]) is int
                 and body["max_tool_calls"] in (1, 2), "INVALID_REQUEST", "Bounded goal, budget lineage and one or two local calls required.")
        submitted = body["input"]
        _require(type(submitted) is dict and set(submitted) == {"file_name", "csv_base64", "spec_base64"},
                 "INVALID_REQUEST", "Upload original CSV and spec bytes only.")
        file_name = tabular._filename(submitted["file_name"])
        csv_raw, spec_raw = _decode(submitted["csv_base64"], tabular.MAX_CSV_BYTES), _decode(submitted["spec_base64"], tabular.MAX_SPEC_BYTES)
        spec = tabular._parse(spec_raw)
        tabular._spec(spec)
        _require(spec["file"] == file_name, "INVALID_SPEC", "Uploaded file name must equal the original spec declaration.")
        tabular._records(csv_raw, spec)  # Parsing checks input, never performs a research action.
        with self._writer():
            with self._connect() as con:
                old = self._old(con, body, digest)
                if old is not None:
                    response = self._completed(old)
                    _, existing = self._project(con, response["project_id"])
                    saved = existing._source(existing.status())
                    _require(saved["snapshot_sha256"] == old["intent"]["source_snapshot_sha256"], "EVIDENCE_CHANGED", "Saved project input changed.")
                    originals = safe_path(self.root / "inputs" / old["intent"]["slot"])
                    for name, limit, identity in ((old["intent"]["file_name"], tabular.MAX_CSV_BYTES, "csv_sha256"),
                                                   ("spec.json", tabular.MAX_SPEC_BYTES, "spec_sha256")):
                        original = reader._read_file(safe_path(originals / name), limit)
                        _require(hashlib.sha256(original).hexdigest() == old["intent"][identity],
                                 "EVIDENCE_CHANGED", "Preserved uploaded original bytes changed.")
                    return response
                _require(con.execute("SELECT COUNT(*) FROM requests WHERE command='create'").fetchone()[0] < MAX_PROJECTS,
                         "PROJECT_LIMIT", "At most 32 project creation intents are allowed in this workbench.")
                intent = {"slot": digest, "goal": body["goal"], "budget_ref": body["budget_ref"], "max_tool_calls": body["max_tool_calls"],
                          "file_name": file_name, "csv_sha256": hashlib.sha256(csv_raw).hexdigest(), "spec_sha256": hashlib.sha256(spec_raw).hexdigest()}
                record = self._accept(con, body, digest, "create", intent)
            try:
                inputs = safe_path(self.root / "inputs" / digest)
                inputs.mkdir(parents=True, exist_ok=False)
                write_bytes_once(inputs / file_name, csv_raw)
                write_bytes_once(inputs / "spec.json", spec_raw)
                packet = tabular.capture_source(inputs)
                packet_path = inputs / "source.json"
                write_bytes_once(packet_path, canonical(packet).encode("utf-8"))
                record["intent"]["source_snapshot_sha256"] = packet["snapshot_sha256"]
                with self._connect() as con:
                    self._save(con, body["request_id"], record)
                safe_path(self.root / "projects").mkdir(exist_ok=True)
                project = ResearchProject(self.root / "projects" / digest)
                state = project.create(source=packet_path, goal=body["goal"], budget_ref=body["budget_ref"],
                                       max_tool_calls=body["max_tool_calls"], method_id=tabular.TOOL_ID)
                response = self._response("create", body["request_id"], state["id"], status="created")
                record.update(status="completed", result=response)
                with self._connect() as con:
                    con.execute("INSERT INTO projects VALUES(?,?,?,NULL)", (state["id"], body["goal"], digest))
                    con.execute("INSERT OR REPLACE INTO metadata VALUES('active_project_id',?)", (state["id"],))
                    self._save(con, body["request_id"], record)
                return response
            except Exception as error:
                self._incomplete(body["request_id"], record, error)
                if isinstance(error, ResearchError):
                    raise
                raise ResearchError("WORKBENCH_OPERATION_FAILED", "Project creation stopped; original inputs and intent were retained.") from None

    def select(self, body):
        digest = _body(body, ("request_id", "project_id"))
        with self._writer(), self._connect() as con:
            old = self._old(con, body, digest)
            if old is not None:
                return self._completed(old)
            self._project(con, body["project_id"])
            response = self._response("select", body["request_id"], body["project_id"], status="selected")
            record = self._accept(con, body, digest, "select", {"project_id": body["project_id"]})
            record.update(status="completed", result=response)
            con.execute("INSERT OR REPLACE INTO metadata VALUES('active_project_id',?)", (body["project_id"],))
            self._save(con, body["request_id"], record)
            return response

    def advance(self, body):
        digest = _body(body, ("request_id", "project_id", "expected_state_version", "proposal"))
        _require(type(body["expected_state_version"]) is int and body["expected_state_version"] >= 0,
                 "INVALID_REQUEST", "An exact saved state version is required.")
        with self._writer():
            with self._connect() as con:
                _, project = self._project(con, body["project_id"], active=True)
                self._no_pending_batch(con, body["project_id"])
                old = self._old(con, body, digest)
                if old is None:
                    self._accept(con, body, digest, "advance", {"project_id": body["project_id"], "request_sha256": digest})
            # The original core request ID performs all replay, unknown and version checks.
            return ProjectController(project.root).advance_selection(request_id=body["request_id"], proposal=body["proposal"],
                                                                     expected_state_version=body["expected_state_version"])

    def model_view(self, *, enabled=False):
        with self._connect(readonly=True) as con:
            active = self._active(con)
            project = self._project(con, active)[1] if active is not None else None
        view = {"schema_version": "local-host-model-view-v1", "enabled": enabled,
                "project_id": active, "journal": None, "records": []}
        if project is not None:
            journal = HostModelSelection(project.root)
            view["journal"] = journal.status()
            view["records"] = [journal.status(request_id=item["request_id"]) for item in view["journal"]["requests"]]
        return view

    def model_advance(self, body, *, executable):
        _body(body, ("request_id", "project_id", "expected_state_version", "decision_limit", "cli_budget_usd", "reason"))
        return self._model_command(body, executable=executable, resume=False)

    def model_resume(self, body, *, executable):
        _body(body, ("request_id", "project_id"))
        return self._model_command(body, executable=executable, resume=True)

    def _model_command(self, body, *, executable, resume):
        _require(executable is not None and Path(executable).is_file(), "MODEL_DISABLED", "No host-selected CLI is enabled.")
        executable = str(Path(executable).absolute())
        with self._writer():
            with self._connect(readonly=True) as con:
                _, project = self._project(con, body["project_id"], active=True)
                self._no_pending_batch(con, body["project_id"], evidence=True)
            journal = HostModelSelection(project.root)
            if resume:
                record = journal.status(request_id=body["request_id"])
                _require(record["provider"] == "claude_cli"
                         and record["prepare_specification"]["executable"] == executable,
                         "CONFIG_CHANGED", "Resume requires the original host-selected CLI.")
            else:
                record = journal.prepare(request_id=body["request_id"], provider="claude_cli", executable=executable,
                    expected_state_version=body["expected_state_version"], decision_limit=body["decision_limit"],
                    cli_budget_usd=body["cli_budget_usd"], reason=body["reason"])
            record = journal.request(request_id=body["request_id"])
            if record["status"] == "received":
                record = journal.consume(request_id=body["request_id"])
            return self._response("model-resume" if resume else "model-advance", body["request_id"], body["project_id"],
                                  status=record["status"], model_record=record, usage=journal.status())

    @staticmethod
    def _no_pending_batch(con, project_id, except_id=None, *, evidence=False):
        commands = ("batch", "evidence") if evidence else ("batch",)
        for row in con.execute("SELECT id,command,record FROM requests WHERE command IN ('batch','evidence')"):
            if row["id"] == except_id or row["command"] not in commands:
                continue
            record = tabular._parse(row["record"].encode("utf-8"))
            _require(record["status"] == "completed" or record["intent"].get("project_id") != project_id,
                     "OPERATION_INCOMPLETE", "Reconcile the original unfinished request for this project before submitting another operation.")

    @staticmethod
    def _seal_batch(record):
        record["record_sha256"] = fingerprint({key: value for key, value in record.items() if key != "record_sha256"})
        _require(len(canonical(record).encode("utf-8")) <= 2 * 1024 * 1024, "WORKBENCH_TOO_LARGE", "Batch metadata exceeds its bounded download size.")

    @staticmethod
    def _check_batch_record(record, digest):
        _require(record.get("schema_version") == "local-workbench-batch-v1" and record.get("status") in {"preparing", "incomplete", "completed"}
                 and fingerprint(record["body"]) == digest == record["intent"]["request_sha256"]
                 and record["record_sha256"] == fingerprint({key: value for key, value in record.items() if key != "record_sha256"})
                 and type(record["steps"]) is list and len(record["steps"]) <= record["body"]["max_actions"] <= 8,
                 "EVIDENCE_CHANGED", "Saved batch grant or metadata changed.")
        for index, step in enumerate(record["steps"], 1):
            _require(step["ordinal"] == index and step["request_id"] == "local-batch-" + digest[:32] + "-step" + str(index)
                     and step["need"] == "next_check" and step["decision_sha256"] == fingerprint(step["decision"])
                     and step["method_id"] in record["body"]["allowed_methods"]
                     and step["decision"]["next_action"]["method_id"] == step["method_id"]
                     and step["decision"]["next_action"].get("parameters", {}) == step["parameters"]
                     and (not registry.is_source(step["method_id"]) or step["parameters"].get("receipt_snapshot_sha256") in record["body"]["source_receipt_sha256s"]),
                     "EVIDENCE_CHANGED", "Saved batch step differs from the frozen authorization.")

    def _save_batch(self, record):
        self._seal_batch(record)
        with self._connect() as con:
            self._save(con, record["body"]["request_id"], record)

    @staticmethod
    def _batch_core_step(project, state, record, step):
        parent = next((item for item in state.get("controller_requests", []) if item["request_id"] == step["request_id"]), None)
        child_id = "controller-child-" + fingerprint({"project_id": state["id"], "request_id": step["request_id"]})[:32]
        with project._connect(readonly=True) as con:
            child = project._action(con, child_id)
        if parent is None:
            _require(child is None and step.get("parent") is None, "EVIDENCE_CHANGED", "A batch child cannot exist without its original controller parent.")
            return None, None
        request = {"project_id": state["id"], "command": "controller.advance", "need": step["need"], "expected_state_version": step["expected_state_version"]}
        _require(parent["request"] == request and parent["request_sha256"] == fingerprint(request)
                 and parent["project_id"] == record["body"]["project_id"] == state["id"]
                 and parent["snapshot_ref_before"] == step["snapshot_ref_before"]
                 and parent["state_version_before"] == step["expected_state_version"]
                 and parent["decision"] == step["decision"] and parent["decision_sha256"] == step["decision_sha256"]
                 and parent["code_identity"] == record["intent"]["project_code_identity"]
                 and parent["controller_code_identity"] == record["intent"]["controller_code_identity"]
                 and parent["source_snapshot_sha256"] == record["intent"]["source_snapshot_sha256"]
                 and parent["child_request_id"] == child_id,
                 "EVIDENCE_CHANGED", "Core controller parent differs from its saved batch intent.")
        if child is not None:
            actual_parameters = (child["method_instance"].get("parameters", {}) if not registry.is_source(step["method_id"])
                                 else {"receipt_snapshot_sha256": child["receipt_snapshot_sha256"]})
            _require(child["project_id"] == state["id"] and child["run_id"] == record["intent"]["run_id"]
                     and child["command"] == step["method_id"] and actual_parameters == step["parameters"]
                     and child["code_identity"] == record["intent"]["project_code_identity"]
                     and child["source_snapshot_sha256"] == record["intent"]["source_snapshot_sha256"],
                     "EVIDENCE_CHANGED", "Core child differs from the accepted method or input.")
            if child["status"] == "completed":
                project._recover(child)  # Completed branch only verifies the existing artifact; never executes.
            if parent["status"] in {"completed", "failed"}:
                summary = {key: child[key] for key in ("id", "request_id", "command", "status", "artifact", "result_sha256", "failure") if key in child}
                _require((parent.get("result") or {}).get("child") == summary and parent["status"] == child["status"],
                         "EVIDENCE_CHANGED", "Saved parent result and core child differ.")
        else:
            _require(parent["status"] not in {"completed", "failed"}, "EVIDENCE_CHANGED", "A completed batch parent has no registered child.")
        return copy.deepcopy(parent), copy.deepcopy(child)

    def _finish_batch(self, record, state, status, code, reason, *, incomplete=False, replayed=False):
        response = self._response("batch", record["body"]["request_id"], record["body"]["project_id"], status=status,
            batch={"grant": copy.deepcopy(record["body"]), "steps": copy.deepcopy(record["steps"]),
                   "stop": {"code": code, "reason": reason}, "snapshot_ref": state["snapshot_ref"], "budget": copy.deepcopy(state["budget"])})
        response["replayed"] = replayed
        record.update(status="incomplete" if incomplete else "completed", result=response)
        self._save_batch(record)
        return copy.deepcopy(response)

    def batch_record(self, request_id):
        identifier(request_id)
        with self._connect(readonly=True) as con:
            row = con.execute("SELECT digest,record FROM requests WHERE id=? AND command='batch'", (request_id,)).fetchone()
            _require(row is not None, "ARTIFACT_NOT_FOUND", "No saved local batch matches this request ID.")
            record = tabular._parse(row["record"].encode("utf-8"))
            self._check_batch_record(record, row["digest"])
            _, project = self._project(con, record["body"]["project_id"])
        state = project.status()
        for step in record["steps"]:
            parent, _ = self._batch_core_step(project, state, record, step)
            if record["status"] == "completed":
                _require(parent == step["parent"], "EVIDENCE_CHANGED", "Frozen batch history differs from the core parent.")
        return copy.deepcopy(record)

    def batch(self, body):
        digest = _body(body, ("request_id", "project_id", "expected_state_version", "max_actions", "allowed_methods", "source_receipt_sha256s", "reason"))
        _require(type(body["expected_state_version"]) is int and body["expected_state_version"] >= 0
                 and type(body["max_actions"]) is int and 1 <= body["max_actions"] <= 8 and _text(body["reason"], 4000)
                 and type(body["allowed_methods"]) is list and 1 <= len(body["allowed_methods"]) <= 8
                 and all(type(item) is str for item in body["allowed_methods"])
                 and len(set(body["allowed_methods"])) == len(body["allowed_methods"])
                 and type(body["source_receipt_sha256s"]) is list and len(body["source_receipt_sha256s"]) <= 16
                 and all(type(item) is str and re.fullmatch(r"[a-f0-9]{64}", item) for item in body["source_receipt_sha256s"])
                 and len(set(body["source_receipt_sha256s"])) == len(body["source_receipt_sha256s"]),
                 "INVALID_REQUEST", "A bounded, exact batch authorization is required.")
        with self._writer():
            with self._connect() as con:
                old = self._old(con, body, digest)
                _, project = self._project(con, body["project_id"], active=old is None or old["status"] != "completed")
                if old is not None:
                    self._check_batch_record(old, digest)
                    if old["status"] == "completed":
                        self.batch_record(body["request_id"])
                        return dict(copy.deepcopy(old["result"]), replayed=True)
                self._no_pending_batch(con, body["project_id"], body["request_id"], evidence=True)
                state = project.status()
                if old is None:
                    project._require_fresh(state, state, body["expected_state_version"])
                    allowed = {registry.primary_id(state), *registry.followup_ids(registry.primary_id(state)), registry.source_id(state)}
                    _require(set(body["allowed_methods"]) <= allowed, "METHOD_NOT_SUPPORTED", "Batch methods must belong to this project's allowlist.")
                    _require(set(body["source_receipt_sha256s"]) <= {item["receipt_snapshot_sha256"] for item in state.get("evidence_sources", [])},
                             "SOURCE_NOT_REGISTERED", "A batch can authorize exact already-registered receipts only.")
                    with project._connect(readonly=True) as project_con:
                        _require(project._action(project_con, body["request_id"]) is None, "IDEMPOTENCY_CONFLICT", "Batch ID belongs to an existing action.")
                    project._require_unclaimed(state, body["request_id"])
                    intent = {"project_id": state["id"], "run_id": state["run_id"], "source_snapshot_sha256": state["source_snapshot_sha256"],
                              "project_code_identity": state["code_identity"], "controller_code_identity": project_controller.code_identity(),
                              "batch_code_identity": batch_code_identity(),
                              "snapshot_ref_before": state["snapshot_ref"], "request_sha256": digest}
                    record = self._accept(con, body, digest, "batch", intent)
                    record.update(schema_version="local-workbench-batch-v1", body=copy.deepcopy(body), steps=[])
                    self._seal_batch(record); self._save(con, body["request_id"], record)
                else:
                    record = old
            controller = ProjectController(project.root)
            try:
                for completed_step in record["steps"]:
                    if completed_step["status"] == "completed":
                        parent, _ = self._batch_core_step(project, project.status(), record, completed_step)
                        _require(parent == completed_step["parent"], "EVIDENCE_CHANGED", "Previously completed batch history changed.")
                while True:
                    state = project.status()
                    if record["steps"] and record["steps"][-1]["status"] != "completed":
                        step = record["steps"][-1]
                        parent, child = self._batch_core_step(project, state, record, step)
                        if (child is not None and child["status"] in {"running", "pending", "unknown"}) or (parent and parent["status"] == "unknown"):
                            step.update(status=(child or parent)["status"], parent=parent, child_request_id=parent["child_request_id"],
                                        response=controller._response(parent, True))
                            return self._finish_batch(record, state, "needs_review", "EXECUTION_UNKNOWN", "Reconcile the original core execution; this batch will not resend it.", incomplete=True, replayed=old is not None)
                        if parent is None and (state["state_version"] != step["expected_state_version"] or state["snapshot_ref"] != step["snapshot_ref_before"]):
                            return self._finish_batch(record, state, "blocked", "STALE_STATE", "The saved undispatched step is stale and will not be replaced.", replayed=old is not None)
                        response = None
                        if parent is None or parent["status"] in {"prepared", "running", "unknown"}:
                            if batch_code_identity() != record["intent"]["batch_code_identity"]:
                                step.update(parent=parent, child_request_id=parent["child_request_id"] if parent else None)
                                return self._finish_batch(record, state, "needs_review", "CODE_CHANGED", "The unfinished grant requires its original local batch implementation.", incomplete=True, replayed=old is not None)
                            try:
                                response = controller.advance(request_id=step["request_id"], need=step["need"], expected_state_version=step["expected_state_version"])
                            except ResearchError:
                                state = project.status()
                                parent, child = self._batch_core_step(project, state, record, step)
                                if parent is None:
                                    raise
                        state = project.status()
                        parent, child = self._batch_core_step(project, state, record, step)
                        step.update(parent=parent, response=response or controller._response(parent, True), status=parent["status"],
                                    child_request_id=parent["child_request_id"])
                        record["cursor_snapshot_ref"] = state["snapshot_ref"]
                        self._save_batch(record)
                        if parent["status"] == "failed":
                            return self._finish_batch(record, state, "failed", "TOOL_FAILED", "The original core child failed; no automatic retry was made.", replayed=old is not None)
                        if parent["status"] == "rejected":
                            return self._finish_batch(record, state, "blocked", (parent.get("result") or {}).get("failure", {}).get("code", "REJECTED"), "The saved core request was rejected.", replayed=old is not None)
                        if parent["status"] != "completed":
                            return self._finish_batch(record, state, "needs_review", "EXECUTION_UNKNOWN", "Collect the original core result before continuing.", incomplete=True, replayed=old is not None)
                    if state["snapshot_ref"] != record.get("cursor_snapshot_ref", record["intent"]["snapshot_ref_before"]):
                        return self._finish_batch(record, state, "blocked", "STALE_STATE", "Project state changed outside the saved batch feedback.", replayed=old is not None)
                    if batch_code_identity() != record["intent"]["batch_code_identity"]:
                        return self._finish_batch(record, state, "needs_review", "CODE_CHANGED", "The unfinished grant requires its original local batch implementation.", incomplete=True, replayed=old is not None)
                    if state["code_identity"] != record["intent"]["project_code_identity"] or project_controller.code_identity() != record["intent"]["controller_code_identity"]:
                        return self._finish_batch(record, state, "blocked", "CODE_CHANGED", "The frozen batch requires its original registered implementation.", replayed=old is not None)
                    plan = controller.next()
                    if plan["snapshot_ref"] != state["snapshot_ref"]:
                        return self._finish_batch(record, project.status(), "blocked", "STALE_STATE", "Project state changed before freezing the next step.", replayed=old is not None)
                    action = plan["decision"].get("next_action", {})
                    blockers = {item["code"] for item in plan["blockers"]}
                    if not plan["executable"]:
                        unknown = bool(blockers & {"EXECUTION_UNKNOWN", "PROJECT_BUSY"}) or action.get("kind") == "reconcile_execution"
                        status = "needs_review" if unknown else "blocked" if blockers else "waiting"
                        code = "EXECUTION_UNKNOWN" if unknown else sorted(blockers)[0] if blockers else "WAITING"
                        return self._finish_batch(record, state, status, code, "The current saved feedback does not permit another authorized execution.", incomplete=unknown, replayed=old is not None)
                    method, parameters = action["method_id"], action.get("parameters", {})
                    if method not in body["allowed_methods"] or (registry.is_source(method) and parameters.get("receipt_snapshot_sha256") not in body["source_receipt_sha256s"]):
                        return self._finish_batch(record, state, "not_authorized", "NOT_AUTHORIZED", "The proposed method or exact source receipt is outside this frozen grant.", replayed=old is not None)
                    if len(record["steps"]) >= body["max_actions"]:
                        return self._finish_batch(record, state, "limit_reached", "ACTION_LIMIT", "The explicit action limit was reached; the next proposal was read only.", replayed=old is not None)
                    decision = project_controller._compact_decision(plan["decision"])
                    ordinal = len(record["steps"]) + 1
                    record["steps"].append({"ordinal": ordinal, "request_id": "local-batch-" + digest[:32] + "-step" + str(ordinal),
                        "expected_state_version": plan["state_version"], "need": "next_check", "snapshot_ref_before": plan["snapshot_ref"],
                        "decision": decision, "decision_sha256": fingerprint(decision), "method_id": method, "parameters": copy.deepcopy(parameters),
                        "status": "prepared", "child_request_id": None, "parent": None, "response": None})
                    self._save_batch(record)
            except Exception as error:
                return self._finish_batch(record, project.status(), "needs_review", getattr(error, "code", "BATCH_INTERRUPTED"),
                    "The batch stopped with its original intent retained; explicitly reconcile this same request ID.", incomplete=True, replayed=old is not None)

    @staticmethod
    def _evidence_upload(body):
        submitted = body["sources"]
        _require(type(submitted) is list and 1 <= len(submitted) <= 8, "INVALID_BUNDLE", "Upload one to eight evidence originals.")
        sources, assets, identities, total = [], {}, [], 0
        for index, source in enumerate(submitted, 1):
            _require(type(source) is dict and set(source) == {"id", "file_name", "bytes_base64", "url", "media_type", "license_note"},
                     "INVALID_BUNDLE", "Use exact uploaded source fields.")
            source_id = identifier(source["id"], "source_id")
            _require(source_id not in assets, "INVALID_BUNDLE", "Uploaded source IDs must be distinct.")
            name = tabular._filename(source["file_name"])
            _require(Path(name).suffix.lower() in {".txt", ".md", ".json", ".csv", ".tsv", ".pdf", ".xlsx"},
                     "INVALID_BUNDLE", "Only supported document, table or text source file types are allowed.")
            raw = _decode(source["bytes_base64"], reader.MAX_SOURCE_BYTES)
            total += len(raw)
            _require(total <= reader.MAX_TOTAL_BYTES, "SOURCE_TOO_LARGE", "Evidence originals exceed 64 MiB in total.")
            path, sha = "sources/" + str(index).zfill(2) + "-" + name, hashlib.sha256(raw).hexdigest()
            sources.append({"id": source_id, "path": path, "sha256": sha,
                            **{key: source[key] for key in ("url", "media_type", "license_note")}})
            assets[source_id] = raw
            identities.append({"id": source_id, "path": path, "sha256": sha, "bytes": len(raw)})
        manifest = {"schema_version": "project-evidence-bundle-v1", "task_ref": body["task_ref"], "contributor": body["contributor"],
                    "sources": sources, "selections": body["selections"], "remaining_questions": body["remaining_questions"]}
        task, contributor, sources, selections, questions = reader._metadata(manifest, captured=False)
        _require(all(selection["locator"]["kind"] in {"text_lines", "pdf_page", "xlsx_cell"} for selection in selections),
                 "INVALID_LOCATOR", "Select text_lines, pdf_page or xlsx_cell only; registration does not extract them.")
        manifest = {"schema_version": "project-evidence-bundle-v1", "task_ref": task, "contributor": contributor,
                    "sources": sources, "selections": selections, "remaining_questions": questions}
        manifest_raw = canonical(manifest).encode("utf-8")
        _require(len(manifest_raw) <= reader.MAX_MANIFEST_BYTES, "SOURCE_TOO_LARGE", "Evidence metadata exceeds the manifest limit.")
        receipt = {"schema_version": "project-evidence-receipt-v1", "task_ref": task, "contributor": contributor,
                   "sources": [{**{key: value for key, value in source.items() if key != "path"}, "asset_sha256": source["sha256"]}
                               for source in sources], "selections": selections, "remaining_questions": questions}
        receipt["snapshot_sha256"] = fingerprint(receipt)
        return manifest_raw, assets, identities, receipt

    def _verify_evidence_registration(self, project, state, request_id, intent):
        registration = next((item for item in state.get("evidence_registrations", []) if item["request_id"] == request_id), None)
        _require(registration is not None, "OPERATION_INCOMPLETE", "No completed core registration exists; preserved upload intent will not be resubmitted.")
        expected = intent["receipt"]
        request = {"project_id": state["id"], "command": "register_evidence", "receipt_snapshot_sha256": expected["snapshot_sha256"],
                   "source_snapshot_sha256": state["source_snapshot_sha256"]}
        _require(registration["project_id"] == intent["project_id"] == state["id"]
                 and registration["task_ref"] == expected["task_ref"] == intent["task_ref"]
                 and registration["receipt_snapshot_sha256"] == expected["snapshot_sha256"]
                 and registration["source_snapshot_sha256"] == intent["source_snapshot_sha256"] == state["source_snapshot_sha256"]
                 and registration["request_sha256"] == fingerprint(request)
                 and registration["state_version_before"] == intent["expected_state_version"]
                 and registration["read_performed"] is False and registration["scientific_validation"] is False,
                 "EVIDENCE_CHANGED", "Core registration differs from the accepted upload intent.")
        uploads = safe_path(self.root / "evidence-uploads" / intent["upload_slot"])
        manifest_raw = reader._read_file(safe_path(uploads / "manifest.json"), reader.MAX_MANIFEST_BYTES)
        _require(hashlib.sha256(manifest_raw).hexdigest() == intent["manifest_sha256"], "EVIDENCE_CHANGED", "Preserved upload manifest changed.")
        for source in intent["sources"]:
            path = uploads.joinpath(*reader._source_parts(source["path"]))
            raw = reader._read_file(safe_path(path), reader.MAX_SOURCE_BYTES)
            _require(len(raw) == source["bytes"] and hashlib.sha256(raw).hexdigest() == source["sha256"],
                     "EVIDENCE_CHANGED", "Preserved uploaded source bytes changed.")
        receipt, _, _ = project._load_evidence_input(state, expected["snapshot_sha256"],
                                                    input_receipt=registration["input_receipt"], task_ref=intent["task_ref"])
        _require(receipt == expected, "EVIDENCE_CHANGED", "Registered original receipt differs from the accepted upload.")
        return copy.deepcopy(registration)

    def register_evidence(self, body):
        digest = _body(body, ("request_id", "project_id", "expected_state_version", "task_ref", "contributor", "sources", "selections", "remaining_questions"))
        _require(type(body["expected_state_version"]) is int and body["expected_state_version"] >= 0,
                 "INVALID_REQUEST", "An exact saved state version is required.")
        manifest_raw, assets, identities, receipt = self._evidence_upload(body)
        with self._writer():
            with self._connect() as con:
                _, project = self._project(con, body["project_id"], active=True)
                old = self._old(con, body, digest)
                state = project.status()
                if old is not None:
                    assets.clear()
                    _require(old["intent"]["upload_slot"] == digest and old["intent"]["receipt"] == receipt
                             and old["intent"]["sources"] == identities
                             and old["intent"]["manifest_sha256"] == hashlib.sha256(manifest_raw).hexdigest(),
                             "EVIDENCE_CHANGED", "Saved upload intent differs from the original request.")
                    registration = self._verify_evidence_registration(project, state, body["request_id"], old["intent"])
                    if old["status"] == "completed":
                        response = self._completed(old)
                        saved = {key: value for key, value in response["registration"].items() if key not in {"replayed", "reused"}}
                        _require(saved == registration, "EVIDENCE_CHANGED", "Saved registration response changed.")
                        return response
                    response = self._response("evidence", body["request_id"], state["id"], status="registered",
                                              registration=dict(registration, replayed=True), recovered=True)
                    response["replayed"] = True
                    old.update(status="completed", result=response)
                    self._save(con, body["request_id"], old)
                    return response
                self._no_pending_batch(con, body["project_id"])
                for row in con.execute("SELECT record FROM requests WHERE command='evidence'"):
                    pending = tabular._parse(row["record"].encode("utf-8"))
                    _require(pending["status"] == "completed" or pending["intent"]["project_id"] != state["id"],
                             "OPERATION_INCOMPLETE", "Reconcile the original evidence request ID before another upload; it will not be replaced.")
                project._require_fresh(state, state, body["expected_state_version"])
                _require(bool(state.get("evidence_task_ref")), "TASK_NOT_AVAILABLE", "No current source task is bound to this project.")
                _require(receipt["task_ref"] == state["evidence_task_ref"] and receipt["task_ref"]["project_id"] == state["id"],
                         "TASK_MISMATCH", "Upload the originals for the exact current project source task.")
                with project._connect(readonly=True) as project_con:
                    _require(project._action(project_con, body["request_id"]) is None, "IDEMPOTENCY_CONFLICT", "Request ID belongs to an existing action.")
                project._require_unclaimed(state, body["request_id"])
                intent = {"project_id": state["id"], "source_snapshot_sha256": state["source_snapshot_sha256"],
                          "expected_state_version": body["expected_state_version"], "task_ref": receipt["task_ref"],
                          "upload_slot": digest, "manifest_sha256": hashlib.sha256(manifest_raw).hexdigest(),
                          "sources": identities, "receipt": receipt}
                record = self._accept(con, body, digest, "evidence", intent)
            try:
                uploads = safe_path(self.root / "evidence-uploads" / digest)
                safe_path(uploads / "sources").mkdir(parents=True, exist_ok=False)
                for source in identities:
                    path = uploads.joinpath(*reader._source_parts(source["path"]))
                    write_bytes_once(safe_path(path), assets[source["id"]])
                assets.clear()
                write_bytes_once(safe_path(uploads / "manifest.json"), manifest_raw)
                registration = project.register_evidence(request_id=body["request_id"], bundle=uploads,
                                                         expected_state_version=body["expected_state_version"])
                self._verify_evidence_registration(project, project.status(), body["request_id"], intent)
                response = self._response("evidence", body["request_id"], state["id"], status="registered", registration=registration)
                record.update(status="completed", result=response)
                with self._connect() as con:
                    self._save(con, body["request_id"], record)
                return response
            except Exception as error:
                self._incomplete(body["request_id"], record, error)
                if isinstance(error, ResearchError):
                    raise
                raise ResearchError("WORKBENCH_OPERATION_FAILED", "Evidence registration stopped; original upload intent and bytes were retained.") from None

    def _verify_report(self, slot, expected):
        root = safe_path(self.root / "reports" / slot)
        try:
            manifest = tabular._parse(reader._read_file(safe_path(root / "manifest.json"), 1_000_000))
            _require(manifest == expected and manifest["schema_version"] == "project-report-export-v1"
                     and manifest["scientific_validation"] is False
                     and set(manifest["files"]) == {"report.json", "report.md", "report.pdf", "input.json"},
                     "EVIDENCE_CHANGED", "Saved report manifest changed.")
            total = 0
            for name, identity in manifest["files"].items():
                _require(type(identity) is dict and type(identity.get("bytes")) is int and 0 < identity["bytes"] <= 64 * 1024 * 1024,
                         "EVIDENCE_CHANGED", "Saved report size identity is invalid.")
                raw = reader._read_file(safe_path(root / name), 64 * 1024 * 1024)
                total += len(raw)
                _require(len(raw) == identity["bytes"] and hashlib.sha256(raw).hexdigest() == identity["sha256"] and total <= 128 * 1024 * 1024,
                         "EVIDENCE_CHANGED", "Saved report bytes changed.")
            return manifest
        except ResearchError:
            raise
        except (OSError, KeyError, TypeError, ValueError):
            raise ResearchError("EVIDENCE_CHANGED", "Saved report is incomplete or changed.") from None

    def export(self, body):
        digest = _body(body, ("request_id", "project_id", "expected_state_version"))
        _require(type(body["expected_state_version"]) is int and body["expected_state_version"] >= 0,
                 "INVALID_REQUEST", "An exact saved state version is required.")
        with self._writer():
            with self._connect() as con:
                _, project = self._project(con, body["project_id"], active=True)
                old = self._old(con, body, digest)
                if old is not None:
                    response = self._completed(old)
                    self._verify_report(digest, response["manifest"])
                    return response
                state = project.status()
                _require(state["state_version"] == body["expected_state_version"], "STALE_STATE", "Reload the current project before exporting.")
                record = self._accept(con, body, digest, "export", {"project_id": state["id"], "snapshot_ref": state["snapshot_ref"],
                                                                  "state_version": state["state_version"], "report_slot": digest})
            try:
                # Lazy import avoids the read-only report/workbench module dependency cycle.
                from .project_report import export_report
                output = safe_path(self.root / "reports" / digest)
                safe_path(self.root / "reports").mkdir(exist_ok=True)
                manifest = export_report(workspace=project.root, output=output)
                _require(manifest["project_id"] == state["id"] and manifest["project_snapshot_ref"] == state["snapshot_ref"],
                         "STALE_STATE", "Project changed while exporting; the output was retained.")
                self._verify_report(digest, manifest)
                _require(project.status()["snapshot_ref"] == state["snapshot_ref"]
                         and host_model_report_current(project.root, manifest),
                         "STALE_STATE", "Project or host-model requests changed before report publication; output was retained.")
                response = self._response("export", body["request_id"], state["id"], status="exported", manifest=manifest)
                record.update(status="completed", result=response)
                with self._connect() as con:
                    con.execute("UPDATE projects SET report=? WHERE id=?", (digest, state["id"]))
                    self._save(con, body["request_id"], record)
                return response
            except Exception as error:
                self._incomplete(body["request_id"], record, error)
                if isinstance(error, ResearchError):
                    raise
                raise ResearchError("WORKBENCH_OPERATION_FAILED", "Report export stopped; its intent and partial output were retained.") from None
