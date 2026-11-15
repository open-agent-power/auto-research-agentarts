"""Host-owned local inputs and active selection; research stays in ResearchProject."""

import base64
import binascii
import copy
from contextlib import contextmanager
from datetime import datetime
import hashlib
import importlib.machinery
from pathlib import Path
import re
import secrets
import sqlite3
import sys
import tempfile

from . import source_evidence_adapter as reader, tabular_quality_adapter as tabular, method_registry as registry, project_controller, research_design
from .contracts import ResearchError, canonical, fingerprint, identifier
from .project_controller import ProjectController
from .host_model_selection import HostModelSelection, PENDING
from .host_model_batch import HostModelBatch
from .recipe_improvement_adapter import read_recipe_validation
from .host_model_report import host_model_report_current, host_model_snapshot_sha256
from .plan_readiness import review_plan_requests
from .research_project import ResearchProject, safe_path, write_bytes_once, code_identity as project_code_identity
from .research_recipe import MAX_RECIPE_BYTES, compile_recipe, parse_json

MAX_PROJECTS = 32
MAX_PLAN_RECOVERY_BYTES = 192 * 1024
PLAN_RECOVERY_VERSION = "local-plan-experience-recovery-v1"


def _no_database_sidecars(path):
    for suffix in ("-wal", "-shm", "-journal"):
        try:
            Path(str(path) + suffix).lstat()
        except FileNotFoundError:
            continue
        except OSError:
            return False
        return False
    return True


@contextmanager
def _immutable_inspection_database(path, *, project_status=False):
    """Use the stored-reader sidecar and file-identity checks without SQLite writes."""
    from .stored_project_summary import _database, _Unavailable
    try:
        with _database(path) as con:
            con.row_factory = sqlite3.Row
            if project_status:
                # ResearchProject.status starts its own read transaction.
                con.rollback()
            yield con
    except _Unavailable:
        raise ResearchError("WORKBENCH_CHANGED", "Stored database is unavailable or changed during read-only inspection.") from None


class _InspectionProject(ResearchProject):
    @contextmanager
    def _connect(self, readonly=False):
        _require(readonly, "READ_ONLY", "Inspection does not open a writable project connection.")
        with _immutable_inspection_database(self.db, project_status=True) as con:
            yield con


def batch_code_identity():
    """Bind unfinished grants to the local orchestration implementation too."""
    return hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


_EXPORT_BOOT_IDENTITY = batch_code_identity()


def _staged_source_tree_identity():
    root = Path(__file__).resolve().parent
    files = sorted(root.rglob("*.py"))
    return fingerprint({str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest() for path in files})


try:
    _STAGED_BOOT_SOURCE_IDENTITY = _staged_source_tree_identity()
except OSError:
    # The new opt-in path stops; legacy Workbench startup keeps its old behavior.
    _STAGED_BOOT_SOURCE_IDENTITY = None


def _check_staged_runtime():
    """Narrow cooperative source-only gate for the new staged registration path."""
    root = Path(__file__).resolve().parent
    _require(sys.dont_write_bytecode and _STAGED_BOOT_SOURCE_IDENTITY is not None
             and _staged_source_tree_identity() == _STAGED_BOOT_SOURCE_IDENTITY,
             "CODE_CHANGED", "Restart with -B and a new empty PYTHONPYCACHEPREFIX; original source must match startup.")
    for name, module in list(sys.modules.items()):
        if name != "autoresearch" and not name.startswith("autoresearch."):
            continue
        path = getattr(module, "__file__", None)
        loader = getattr(module, "__loader__", None)
        cached = getattr(module, "__cached__", None)
        _require(type(path) is str and Path(path).resolve().is_relative_to(root)
                 and isinstance(loader, importlib.machinery.SourceFileLoader)
                 and (cached is None or (not Path(cached).exists() and not Path(cached).is_symlink())),
                 "CODE_CHANGED", "Restart with -B and a new empty PYTHONPYCACHEPREFIX; cached project modules are not accepted.")


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


def _platform_run(value):
    if value is None:
        return None
    fields = {"host_request_id", "provider", "model", "started_at", "ended_at", "input_tokens", "output_tokens",
              "total_tokens", "record_source", "verification"}
    _require(type(value) is dict and set(value) == fields, "INVALID_REQUEST", "Use the exact console excerpt fields.")
    identifier(value["host_request_id"], "host_request_id")
    _require(value["provider"] == "AgentArts" and value["record_source"] == "console_excerpt"
             and value["verification"] == "operator_supplied" and _text(value["model"], 200),
             "INVALID_REQUEST", "A bounded operator-supplied AgentArts console excerpt is required.")
    for key in ("started_at", "ended_at"):
        if value[key] is not None:
            _require(_text(value[key], 64), "INVALID_REQUEST", "Console times must be ISO8601 text or null.")
            try:
                datetime.fromisoformat(value[key].replace("Z", "+00:00"))
            except ValueError:
                raise ResearchError("INVALID_REQUEST", "Console times must be ISO8601 text or null.") from None
    counts = [value[key] for key in ("input_tokens", "output_tokens", "total_tokens")]
    _require(all(item is None or type(item) is int and item >= 0 for item in counts),
             "INVALID_REQUEST", "Console token counts must be nonnegative integers or null, never estimates.")
    _require(any(item is None for item in counts) or counts[0] + counts[1] == counts[2],
             "INVALID_REQUEST", "Known console token counts must sum to the reported total.")
    return copy.deepcopy(value)


def _import_snapshot(project, platform_run):
    state = project.status()
    _require(all(item["status"] in ("completed", "failed") for item in state["actions"] + state["evidence_actions"])
             and state["execution_status"] not in ("pending", "running", "unknown")
             and not any(item["status"] in ("prepared", "running", "unknown") for item in state.get("controller_requests", []))
             and not any(item["status"] in ("sending", "unknown") for item in state.get("source_requests", []))
             and not any(item["status"] == "reserved" for item in state.get("local_model_requests", []))
             and not state["budget"].get("model_requests_reserved", 0),
             "PROJECT_BUSY", "Complete the original project requests before moving this project.")
    project._source(state)
    journal = HostModelSelection(project.root)
    host = journal.status()
    closed = {"applied", "rejected", "invalid", "stale", "failed"}
    _require(all(item["status"] in closed for item in host["requests"]),
             "HOST_SELECTION_PENDING", "Close the original Host requests before moving this project.")
    if platform_run is not None:
        record = journal.status(request_id=platform_run["host_request_id"])
        _require(record["status"] in closed and record["provider"] == "delegated" and record.get("response_file"),
                 "INVALID_REQUEST", "Bind the console excerpt to a closed imported Host response.")
    return state, host


class LocalWorkbench:
    def __init__(self, root):
        self.read_only = False
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

    @classmethod
    def open_readonly(cls, root):
        """Open an existing manager without creating its directory, database or lock."""
        instance = cls.__new__(cls)
        instance.read_only = True
        instance.root = safe_path(Path(root).absolute())
        _require(instance.root.is_dir() and not (instance.root / "project.sqlite").exists(),
                 "WORKBENCH_NOT_FOUND", "An existing separate workbench is required.")
        instance.db = safe_path(instance.root / "workbench.sqlite")
        _require(instance.db.is_file(), "WORKBENCH_NOT_FOUND", "The existing workbench database is required.")
        # SQLite can create or update sidecars even on a read-only connection.
        _require(_no_database_sidecars(instance.db),
                 "WORKBENCH_CHANGED", "A workbench database sidecar requires inspection before read-only opening.")
        with instance._connect(readonly=True) as con:
            row = con.execute("SELECT value FROM metadata WHERE key='schema_version'").fetchone()
            _require(row is not None and row[0] == "local-research-workbench-v1",
                     "WORKBENCH_CHANGED", "Unsupported local workbench schema.")
        return instance

    def __getattribute__(self, name):
        # No command is exposed by a read-only manager, even when invoked directly.
        readers = {"describe", "saved_study_reference", "project_summary", "preview_continuation", "staged_continuation_record",
                   "read_unknown_controller_requests"}
        if not name.startswith("_") and name not in readers and name not in {"root", "db", "read_only", "open_readonly"}:
            if object.__getattribute__(self, "__dict__").get("read_only", False):
                raise ResearchError("READ_ONLY", "This workbench was opened read-only.")
        return object.__getattribute__(self, name)

    def _writer(self):
        # A separate manager-root OS lock; each child still acquires its core lock.
        _require(not self.read_only, "READ_ONLY", "This workbench was opened read-only.")
        return ResearchProject(self.root)._writer()

    @contextmanager
    def _connect(self, readonly=False):
        _require(not self.read_only or readonly, "READ_ONLY", "This workbench was opened read-only.")
        safe_path(self.db)
        before = None
        if self.read_only:
            _require(_no_database_sidecars(self.db),
                     "WORKBENCH_CHANGED", "A workbench database sidecar requires inspection before reading.")
            before = self.db.stat()
        # immutable prevents SQLite from creating WAL shared-memory files. The
        # sidecar check above prevents silently ignoring an existing journal.
        mode = "?mode=ro&immutable=1" if self.read_only else "?mode=ro" if readonly else "?mode=rwc"
        con = sqlite3.connect(self.db.as_uri() + mode, uri=True, timeout=5)
        con.row_factory = sqlite3.Row
        try:
            with con:
                if readonly:
                    con.execute("BEGIN")
                yield con
                if self.read_only:
                    safe_path(self.db)
                    after = self.db.stat()
                    _require(_no_database_sidecars(self.db)
                             and (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns)
                             == (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns),
                             "WORKBENCH_CHANGED", "The workbench changed during the read; retry only when no writer is active.")
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

    def read_unknown_controller_requests(self, *, project_id, snapshot_ref):
        """Project saved unknown parents using limited state fields, not SQL or artifact authentication."""
        identifier(project_id, "project_id")
        _require(type(snapshot_ref) is str and re.fullmatch(r"[a-f0-9]{64}", snapshot_ref) is not None,
                 "INVALID_QUERY", "Use the exact project snapshot identity.")
        manager_read = (lambda: _immutable_inspection_database(self.db)) if self.read_only else (lambda: self._connect(readonly=True))
        with manager_read() as con:
            row, project = self._project(con, project_id, active=True)
            slot = row["slot"]
        if self.read_only:
            project = _InspectionProject(project.root)
        state = project.status()
        _require(state.get("id") == project_id and state.get("snapshot_ref") == snapshot_ref,
                 "STALE_STATE", "The active project snapshot changed; reload it first.")
        _require(type(state.get("run_id")) is str and re.fullmatch(r"[A-Za-z0-9_.:-]{1,80}", state["run_id"]) is not None,
                 "EVIDENCE_CHANGED", "The saved run identity is malformed.")
        runtime_project = project_code_identity()
        runtime_controller = project_controller.code_identity()
        parents = state.get("controller_requests", [])
        history_complete = type(parents) is list
        if not history_complete:
            parents = []
        actions_complete = type(state.get("actions")) is list and type(state.get("evidence_actions")) is list
        actions = state["actions"] + state["evidence_actions"] if actions_complete else []
        actions_complete = actions_complete and all(type(a) is dict for a in actions)
        if not actions_complete:
            actions = []
        items, seen = [], {}
        def digest_or_none(value):
            return value if type(value) is str and re.fullmatch(r"[a-f0-9]{64}", value) else None
        for parent in parents:
            if type(parent) is not dict or parent.get("status") not in ("prepared", "running", "unknown", "completed", "failed", "rejected", "waiting", "needs_review"):
                history_complete = False
                continue
            if parent.get("status") != "unknown":
                continue
            request_id = parent.get("request_id")
            if type(request_id) is not str or re.fullmatch(r"[A-Za-z0-9_.:-]{1,80}", request_id) is None:
                request_id = None
                history_complete = False
            if request_id is not None and request_id in seen:
                history_complete = False
                seen[request_id].update(record_binding="malformed", identity_binding="unknown",
                                        command=None, child_request_id=None, child_status=None)
                continue
            original_source = digest_or_none(parent.get("source_snapshot_sha256"))
            original_core = digest_or_none(parent.get("code_identity"))
            controller_core = digest_or_none(parent.get("controller_code_identity"))
            current_source = digest_or_none(state.get("source_snapshot_sha256"))
            current_core = digest_or_none(state.get("code_identity"))
            identity = ("unknown" if None in (original_source, original_core, controller_core, current_source, current_core,
                                               digest_or_none(runtime_project), digest_or_none(runtime_controller))
                        else "match" if (original_source == current_source and original_core == current_core == runtime_project
                                          and controller_core == runtime_controller) else "mismatch")
            item = {"request_id": request_id, "command": None, "status": "unknown",
                    "child_request_id": None, "child_status": None,
                    "source_snapshot_sha256": original_source, "project_code_identity": original_core,
                    "controller_code_identity": controller_core, "current_source_snapshot_sha256": current_source,
                    "current_project_code_identity": current_core, "runtime_project_code_identity": digest_or_none(runtime_project),
                    "runtime_controller_code_identity": digest_or_none(runtime_controller), "identity_binding": identity,
                    "record_binding": "malformed", "unknown_reason": "controller_parent_unknown"}
            try:
                request, decision = parent["request"], parent["decision"]
                child_id, saved_child = parent["child_request_id"], parent["result"]["child"]
                children = [a for a in actions if a.get("request_id") == child_id]
                valid = (request_id is not None and parent["project_id"] == project_id
                         and type(request) is dict and request.get("project_id") == project_id
                         and request.get("command") in ("controller.advance", "controller.advance_selection", "controller.advance_recipe")
                         and parent["request_sha256"] == fingerprint(request)
                         and type(decision) is dict and parent["decision_sha256"] == fingerprint(decision)
                         and identity != "unknown"
                         and child_id == "controller-child-" + fingerprint({"project_id": project_id, "request_id": request_id})[:32]
                         and len(children) == 1 and type(saved_child) is dict
                         and saved_child.get("request_id") == child_id and saved_child.get("status") == "unknown"
                         and saved_child.get("id") == children[0].get("id")
                         and saved_child.get("command") == children[0].get("command")
                         and children[0].get("status") in ("pending", "running", "unknown", "completed", "failed"))
                if valid:
                    item.update(command=request["command"], child_request_id=child_id,
                                child_status=children[0]["status"], record_binding="limited_fields_match")
            except (KeyError, TypeError, ValueError, RecursionError):
                pass  # Preserve only safe identifiers for inspection; no recovery claim.
            items.append(item)
            if request_id is not None:
                seen[request_id] = item
        _require(project.status().get("snapshot_ref") == snapshot_ref, "STALE_STATE", "The project changed during this read.")
        _require(project_code_identity() == runtime_project and project_controller.code_identity() == runtime_controller,
                 "CODE_CHANGED", "The runtime identities changed during this read.")
        with manager_read() as con:
            after, _ = self._project(con, project_id, active=True)
            _require(after["slot"] == slot, "WORKBENCH_CHANGED", "The managed project binding changed during this read.")
        return {"schema_version": "local-unknown-controller-requests-v1", "project_id": project_id,
                "run_id": state["run_id"], "snapshot_ref": snapshot_ref,
                "total": len(items) if history_complete else None, "observed_total": len(items),
                "history_complete": history_complete, "actions_complete": actions_complete,
                "shown": min(len(items), 8), "truncated": True if len(items) > 8 else False if history_complete else None,
                "items": items[:8],
                "verification": "saved_state_projection_only", "binding_scope": "limited_state_fields_only_not_sql_or_artifacts",
                "recovery_verified": False,
                "request_body_included": False, "scientific_validation": False}

    def describe(self):
        with self._connect(readonly=True) as con:
            projects = [{"id": row["id"], "goal": row["goal"]} for row in con.execute("SELECT id,goal FROM projects ORDER BY rowid")]
            active = self._active(con)
            pending = []
            active_plan_pending = 0
            active_staged_pending = 0
            active_primary_pending = 0
            active_feedback_pending = 0
            active_staged_plan_pending = 0
            if active is not None:
                for row in con.execute("SELECT id,record FROM requests WHERE command='save_staged_feedback_plan' ORDER BY rowid DESC"):
                    record = tabular._parse(row["record"].encode("utf-8"))
                    if record.get("status") == "completed" or record.get("intent", {}).get("project_id") != active:
                        continue
                    active_staged_plan_pending += 1
                    if len(pending) < 8:
                        pending.append({"request_id":row["id"], "command":"save_staged_feedback_plan", "status":record.get("status"),
                                        "project_id":active, "recovery":"original_terminal_binding_check_only"})
                for row in con.execute("SELECT id,record FROM requests WHERE command='advance_staged_feedback' ORDER BY rowid DESC"):
                    record = tabular._parse(row["record"].encode("utf-8"))
                    if record.get("status") in ("completed", "waiting") or record.get("intent", {}).get("project_id") != active:
                        continue
                    active_feedback_pending += 1
                    if len(pending) < 8:
                        pending.append({"request_id":row["id"], "command":"advance_staged_feedback", "status":record.get("status"),
                                        "project_id":active, "recovery":"original_terminal_binding_check_only"})
                for row in con.execute("SELECT id,record FROM requests WHERE command='advance_staged_primary' ORDER BY rowid DESC"):
                    record = tabular._parse(row["record"].encode("utf-8"))
                    if record.get("status") == "completed" or record.get("intent", {}).get("project_id") != active:
                        continue
                    active_primary_pending += 1
                    if len(pending) < 8:
                        pending.append({"request_id":row["id"], "command":"advance_staged_primary", "status":record.get("status"),
                                        "project_id":active, "recovery":"original_terminal_binding_check_only"})
                for row in con.execute("SELECT id,record FROM requests WHERE command='register_staged_hypothesis' ORDER BY rowid DESC"):
                    record = tabular._parse(row["record"].encode("utf-8"))
                    if record.get("status") == "completed" or record.get("intent", {}).get("project_id") != active:
                        continue
                    active_staged_pending += 1
                    if len(pending) < 8:
                        pending.append({"request_id": row["id"], "command": "register_staged_hypothesis",
                                        "status": record.get("status"), "project_id": active,
                                        "recovery": "original_terminal_binding_check_only"})
            # Active-project plan intents take priority over other Projects' bounded
            # pending list; no original plan body is projected here.
            if active is not None:
                for row in con.execute("SELECT id,command,digest,record FROM requests WHERE command='save_plan' ORDER BY rowid DESC"):
                    record = tabular._parse(row["record"].encode("utf-8"))
                    if record.get("status") == "completed" or record.get("intent", {}).get("project_id") != active:
                        continue
                    active_plan_pending += 1
                    if len(pending) >= 8:
                        continue
                    item = {"request_id": row["id"], "command": "save_plan", "status": record["status"], "project_id": active}
                    try:
                        self._check_plan_intent(row["id"], row["digest"], record)
                        item["recovery"] = "original_body_available"
                    except ResearchError:
                        item["recovery"] = "original_body_unavailable"
                    pending.append(item)
            for row in con.execute("SELECT id,command,digest,record FROM requests WHERE command IN ('create','import','export','evidence','batch','continue','design_bind','import_experience','set_experience_status','register_holdout','freeze_retrieval_strategy','continue_staged','save_plan','save_staged_feedback_plan','register_staged_hypothesis','register_tabular_quality_conditions','advance_tabular_quality_feedback','save_quality_plan','advance_tabular_quality_feedback_v2','model_quality_plan_adopt','model_supplied_quality_plan_adopt') ORDER BY rowid DESC"):
                if len(pending) == 8:
                    break
                if any(item["request_id"] == row["id"] for item in pending):
                    continue
                record = tabular._parse(row["record"].encode("utf-8"))
                quality_terminal = row["command"] in ("advance_tabular_quality_feedback", "advance_tabular_quality_feedback_v2") and record["status"] in ("completed", "failed", "waiting", "needs_review", "rejected")
                if not quality_terminal and record["status"] != "completed" and (row["command"] == "save_plan" or record["status"] != "rejected"):
                    item = {"request_id": row["id"], "command": row["command"], "status": record["status"],
                            "project_id": (record.get("result") or {}).get("project_id", record["intent"].get("project_id"))}
                    if row["command"] == "save_plan":
                        try:
                            self._check_plan_intent(row["id"], row["digest"], record)
                            item["recovery"] = "original_body_available"
                        except ResearchError:
                            item["recovery"] = "original_body_unavailable"
                    pending.append(item)
                    if len(pending) == 8:
                        break
            batches = []
            for row in con.execute("SELECT id,digest,record FROM requests WHERE command='batch' ORDER BY rowid DESC LIMIT 8"):
                record = tabular._parse(row["record"].encode("utf-8"))
                self._check_batch_record(record, row["digest"])
                batches.append({"request_id": row["id"], "project_id": record["body"]["project_id"],
                                "status": (record.get("result") or {}).get("status", record["status"]),
                                "record_status": record["status"], "body": copy.deepcopy(record["body"]), "result": copy.deepcopy(record["result"])})
            continuations = []
            for row in con.execute("SELECT id,digest,record FROM requests WHERE command='continue' ORDER BY rowid DESC LIMIT 8"):
                record = tabular._parse(row["record"].encode("utf-8"))
                self._check_continuation(record, row["digest"])
                continuations.append(copy.deepcopy(record["result"]))
        result = {"schema_version": "local-research-workbench-v1", "active_project_id": active, "projects": projects,
                "pending_requests": pending, "batches": batches, "continuations": continuations,
                "constraints": {"max_projects": MAX_PROJECTS, "max_csv_bytes": tabular.MAX_CSV_BYTES, "max_spec_bytes": tabular.MAX_SPEC_BYTES,
                    "max_tool_calls": [1, 2], "local_tool_limit_choices": [1, 2], "model_requests_allowed": 0, "new_fits": 0,
                    "existing_cash_cap_cny": 5, "historical_costs": "unknown", "automatic_retry": False}}
        if active_plan_pending > 8:
            result["pending_plan_summary"] = {"project_id": active, "total": active_plan_pending, "shown": 8, "truncated": True}
        if active_staged_pending:
            shown = sum(item["command"] == "register_staged_hypothesis" and item.get("project_id") == active for item in pending)
            result["pending_staged_hypothesis_summary"] = {"project_id": active, "total": active_staged_pending,
                                                            "shown": shown, "truncated": shown < active_staged_pending}
        if active_primary_pending:
            shown = sum(item["command"] == "advance_staged_primary" and item.get("project_id") == active for item in pending)
            result["pending_staged_primary_summary"] = {"project_id":active, "total":active_primary_pending,
                                                        "shown":shown, "truncated":shown < active_primary_pending}
        if active_staged_plan_pending:
            shown = sum(item["command"] == "save_staged_feedback_plan" and item.get("project_id") == active for item in pending)
            result["pending_staged_feedback_plan_summary"] = {"project_id":active, "total":active_staged_plan_pending,
                                                               "shown":shown, "truncated":shown < active_staged_plan_pending}
        if active_feedback_pending:
            shown = sum(item["command"] == "advance_staged_feedback" and item.get("project_id") == active for item in pending)
            result["pending_staged_feedback_summary"] = {"project_id":active, "total":active_feedback_pending,
                                                         "shown":shown, "truncated":shown < active_feedback_pending}
        return result

    def binding(self):
        with self._connect(readonly=True) as con:
            active = self._active(con)
            if active is None:
                return None, None
            row, project = self._project(con, active)
            report = row["report"]
        _require(report is None or re.fullmatch(r"[a-f0-9]{64}", report), "WORKBENCH_CHANGED", "Managed report identity changed.")
        return project, safe_path(self.root / "reports" / report) if report else None

    def import_project(self, *, request_id, workspace, platform_run=None):
        """Explicit native-host move; never create a research project or select it implicitly."""
        source = safe_path(Path(workspace).absolute()).resolve()
        manager_root = self.root.resolve()
        _require(not source.is_relative_to(manager_root) and not manager_root.is_relative_to(source),
                 "WORKBENCH_OVERLAP", "Import requires separate source-project and manager directories.")
        body = {"request_id": request_id, "workspace": str(source), "platform_run": _platform_run(platform_run)}
        digest = _body(body, ("request_id", "workspace", "platform_run"))
        target = safe_path(manager_root / "projects" / digest)
        with self._writer():
            with self._connect() as con:
                record = self._old(con, body, digest)
                replayed = record is not None
                if record is not None and record["status"] == "completed":
                    response = self._completed(record)
                    row, _ = self._project(con, response["project_id"])
                    _require(row["slot"] == digest, "WORKBENCH_CHANGED", "Imported project binding changed.")
                    return response
                if record is None:
                    _require(source.is_dir() and not target.exists(), "PROJECT_NOT_FOUND", "Use the existing separate source project.")
                    _require(source.stat().st_dev == self.root.stat().st_dev,
                             "IMPORT_FILESYSTEM", "Project import requires a same-filesystem rename; no copying is performed.")
                    project = ResearchProject(source)
                    with project._writer():
                        state, host = _import_snapshot(project, body["platform_run"])
                    _require(con.execute("SELECT 1 FROM projects WHERE id=?", (state["id"],)).fetchone() is None,
                             "PROJECT_EXISTS", "This project identifier is already managed.")
                    _require(con.execute("SELECT COUNT(*) FROM requests WHERE command IN ('create','import')").fetchone()[0] < MAX_PROJECTS,
                             "PROJECT_LIMIT", "At most 32 project intake intents are allowed in this workbench.")
                    for row in con.execute("SELECT record FROM requests WHERE command='import'"):
                        other = tabular._parse(row[0].encode("utf-8"))
                        _require(other["intent"]["project_id"] != state["id"],
                                 "PROJECT_EXISTS", "Resume the original import ID for this project.")
                    intent = {"slot": digest, "workspace": str(source), "target_workspace": str(target), "project_id": state["id"],
                              "goal": state["registration"]["goal"], "snapshot_ref": state["snapshot_ref"],
                              "host": host, "platform_run": body["platform_run"]}
                    record = self._accept(con, body, digest, "import", intent)
            try:
                intent = record["intent"]
                _require(not (source.exists() and target.exists()), "IMPORT_CONFLICT", "Both import paths exist; preserve them for inspection.")
                if source.exists():
                    project = ResearchProject(source)
                    with project._writer():
                        state, host = _import_snapshot(project, intent["platform_run"])
                        _require(state["snapshot_ref"] == intent["snapshot_ref"] and host == intent["host"],
                                 "EVIDENCE_CHANGED", "Original project or Host changed after import was accepted.")
                    safe_path(target.parent).mkdir(exist_ok=True)
                    source.rename(target)
                _require(target.is_dir(), "OPERATION_INCOMPLETE", "The original import has no source or target; inspect its saved intent.")
                project = ResearchProject(target)
                with project._writer():
                    state, host = _import_snapshot(project, intent["platform_run"])
                    _require(state["snapshot_ref"] == intent["snapshot_ref"] and host == intent["host"],
                             "EVIDENCE_CHANGED", "Moved project or Host differs from the accepted import.")
                    response = self._response("import", request_id, state["id"], status="imported", workspace=str(target),
                                              state_version=state["state_version"])
                    record.update(status="completed", result=response)
                    record.pop("failure", None)
                    with self._connect() as con:
                        existing = con.execute("SELECT slot FROM projects WHERE id=?", (state["id"],)).fetchone()
                        _require(existing is None or existing[0] == digest, "PROJECT_EXISTS", "This project identifier is already managed.")
                        con.execute("INSERT OR IGNORE INTO projects VALUES(?,?,?,NULL)", (state["id"], intent["goal"], digest))
                        self._save(con, request_id, record)
                return dict(response, replayed=replayed)
            except Exception as error:
                self._incomplete(request_id, record, error)
                if isinstance(error, ResearchError):
                    raise
                raise ResearchError("WORKBENCH_OPERATION_FAILED", "Project import stopped; resume the same request ID and original paths.") from None

    def import_record(self, request_id):
        identifier(request_id)
        with self._connect(readonly=True) as con:
            row = con.execute("SELECT record FROM requests WHERE id=? AND command='import'", (request_id,)).fetchone()
        _require(row is not None, "ARTIFACT_NOT_FOUND", "No native project import matches this ID.")
        return {"request_id": request_id, **tabular._parse(row[0].encode("utf-8"))}

    def create(self, body):
        digest = _body(body, ("request_id", "goal", "budget_ref", "max_tool_calls", "input"))
        _require(_text(body["goal"], 4000) and _text(body["budget_ref"], 500) and type(body["max_tool_calls"]) is int
                 and 1 <= body["max_tool_calls"] <= 8, "INVALID_REQUEST", "Bounded goal, budget lineage and 1..8 local calls required.")
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
                self._no_staged_switch(con, self._active(con))
                _require(con.execute("SELECT COUNT(*) FROM requests WHERE command IN ('create','import')").fetchone()[0] < MAX_PROJECTS,
                         "PROJECT_LIMIT", "At most 32 project intake intents are allowed in this workbench.")
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
            if self._active(con) != body["project_id"]:
                self._no_staged_switch(con, self._active(con))
            self._project(con, body["project_id"])
            response = self._response("select", body["request_id"], body["project_id"], status="selected")
            record = self._accept(con, body, digest, "select", {"project_id": body["project_id"]})
            record.update(status="completed", result=response)
            con.execute("INSERT OR REPLACE INTO metadata VALUES('active_project_id',?)", (body["project_id"],))
            self._save(con, body["request_id"], record)
            return response

    def _quality_intent(self, body, digest, command, state):
        intent = {"schema_version":"local-tabular-quality-intent-v1", "command":command,
                  "project_id":body["project_id"], "run_id":state["run_id"], "body":copy.deepcopy(body),
                  "request_sha256":digest, "source_snapshot_sha256":state["source_snapshot_sha256"],
                  "project_code_identity":state["code_identity"], "controller_code_identity":project_controller.code_identity(),
                  "manager_code_identity":batch_code_identity(), "manager_root":str(self.root.resolve()),
                  "nonce":secrets.token_hex(32)}
        intent["intent_sha256"] = fingerprint(intent)
        return intent

    def _check_quality_intent(self, intent, body, digest, command, state):
        fields = {"schema_version","command","project_id","run_id","body","request_sha256",
                  "source_snapshot_sha256","project_code_identity","controller_code_identity","manager_code_identity","manager_root","nonce","intent_sha256"}
        _require(type(intent) is dict and set(intent) == fields and intent["schema_version"] == "local-tabular-quality-intent-v1"
                 and intent["command"] == command and canonical(intent["body"]) == canonical(body)
                 and intent["request_sha256"] == digest == fingerprint(body)
                 and intent["intent_sha256"] == fingerprint({k:v for k,v in intent.items() if k != "intent_sha256"})
                 and intent["project_id"] == body["project_id"] == state["id"] and intent["run_id"] == state["run_id"]
                 and intent["source_snapshot_sha256"] == state["source_snapshot_sha256"]
                 and intent["project_code_identity"] == state["code_identity"] == project_code_identity()
                 and intent["controller_code_identity"] == project_controller.code_identity()
                 and intent["manager_root"] == str(self.root.resolve())
                 and type(intent["nonce"]) is str and re.fullmatch(r"[a-f0-9]{64}", intent["nonce"]) is not None
                 and intent["manager_code_identity"] == batch_code_identity() == _EXPORT_BOOT_IDENTITY,
                 "EVIDENCE_CHANGED", "The original quality manager body, project or code identity changed.")

    @staticmethod
    def _quality_registration(project, body, intent):
        from .tabular_quality_feedback import _checked_collection, _manager_claim
        before = project.status()
        records = before.get("tabular_quality_registrations", [])
        _checked_collection(records)
        matches = [r for r in records if r["request_id"] == body["request_id"]]
        _require(len(matches) == 1, "OPERATION_INCOMPLETE", "The original core quality registration is absent; inspect it without retrying.")
        record = matches[0]
        expected = {k:copy.deepcopy(v) for k,v in body.items() if k != "project_id"}
        _require(canonical(record["request"]) == canonical(expected)
                 and record["project_id"] == before["id"] and record["run_id"] == before["run_id"]
                 and record["source_sha256"] == before["registration"]["source_sha256"]
                 and record["source_snapshot_sha256"] == before["source_snapshot_sha256"]
                 and record["scope_sha256"] == fingerprint(before["source_scope"])
                 and record["project_code_identity"] == before["code_identity"] == intent["project_code_identity"]
                 and record["controller_code_identity"] == intent["controller_code_identity"]
                 and any(p["version"] == record["plan_version"] and fingerprint(p) == record["plan_sha256"]
                         for p in before.get("plan_revisions", [])),
                 "EVIDENCE_CHANGED", "The original core quality registration or plan differs.")
        project._source(before)
        with project._connect(readonly=True) as con:
            _manager_claim(con, "registration", body["request_id"], intent["intent_sha256"], record["registration_sha256"])
        _require(project.status()["snapshot_ref"] == before["snapshot_ref"], "STALE_STATE", "Project changed during registration verification.")
        return copy.deepcopy(record)

    @staticmethod
    def _quality_policy_claim(project, parent, intent):
        from .tabular_quality_feedback import _manager_claim
        try:
            meta = parent["tabular_quality_policy"]
            core_sha = fingerprint({"request_sha256":parent["request_sha256"], "policy_sha256":meta["record_sha256"]})
            with project._connect(readonly=True) as con:
                _manager_claim(con, "policy", parent["request_id"], intent["intent_sha256"], core_sha)
        except (KeyError, TypeError, ValueError):
            raise ResearchError("EVIDENCE_CHANGED", "Original policy ownership identity is malformed.") from None

    @staticmethod
    def _quality_unclaimed(project, state, ids):
        # Inspect both tables directly: an orphan replay is still a claim.
        with project._connect(readonly=True) as con:
            for request_id in ids:
                project._require_unclaimed(state, request_id)
                _require(con.execute("SELECT 1 FROM actions WHERE request_id=?", (request_id,)).fetchone() is None
                         and con.execute("SELECT 1 FROM replays WHERE request_id=? OR action_request_id=?", (request_id, request_id)).fetchone() is None,
                         "IDEMPOTENCY_CONFLICT", "The original project ID is already claimed; inspect the original operation.")

    @staticmethod
    def _preflight_quality_registration(project, state, body):
        from .tabular_quality_conditions import validate_conditions
        from .tabular_quality_feedback import _checked_collection, MAX_REGISTRATIONS
        records = state.get("tabular_quality_registrations", [])
        _checked_collection(records)
        _require(body["request_id"] != body["controller_request_id"], "INVALID_REQUEST", "Use distinct registration and future controller IDs.")
        _require(len(records) < MAX_REGISTRATIONS, "LIMIT_EXCEEDED", "At most sixteen quality registrations are allowed.")
        LocalWorkbench._quality_unclaimed(project, state, (body["request_id"], body["controller_request_id"]))
        for item in records + state.get("hypothesis_registrations", []):
            _require(type(item) is dict and type(item.get("controller_request_id")) is str,
                     "EVIDENCE_CHANGED", "An existing future controller ID is malformed.")
            _require(item["controller_request_id"] not in (body["request_id"], body["controller_request_id"]),
                     "IDEMPOTENCY_CONFLICT", "A future controller ID is already claimed.")
        validate_conditions(body["conditions"], numeric_columns=state["source_scope"]["numeric_columns"])
        _require(state["registration"].get("method_id") == tabular.TOOL_ID and state.get("plan_revisions")
                 and not any(a["command"] == tabular.TOOL_ID for a in state["actions"]),
                 "CONDITION_NOT_SATISFIED", "An unexecuted quality project with a saved plan is required.")
        _require(not any(p["status"] in ("prepared", "running", "unknown") for p in state.get("controller_requests", []))
                 and not any(p["status"] == "reserved" for p in state.get("local_model_requests", []))
                 and not any(p["status"] in PENDING for p in HostModelSelection(project.root).status()["requests"]),
                 "PROJECT_BUSY", "Inspect pending project requests first.")
        project._source(state)
        context = ProjectController(project.root)._selection_context(state, "next_check")
        candidates = [c for c in context["candidates"] if c["id"] == body["candidate_id"]]
        _require(not context["blockers"] and len(candidates) == 1 and candidates[0]["method_id"] == tabular.TOOL_ID
                 and candidates[0]["parameters"] == {} and candidates[0]["evaluation_ref"] == "tabular-quality-v1",
                 "CONDITION_NOT_SATISFIED", "Select the unique eligible quality candidate.")
        _require(project.status()["snapshot_ref"] == state["snapshot_ref"], "STALE_STATE", "Project changed during preflight.")

    @staticmethod
    def _preflight_quality_advance(project, state, body):
        from .tabular_quality_feedback import _checked_collection
        registrations = state.get("tabular_quality_registrations", [])
        _checked_collection(registrations)
        found = [r for r in registrations if r["request_id"] == body["registration_request_id"]]
        _require(len(found) == 1, "INVALID_REQUEST", "Use one original quality registration.")
        _require(found[0]["project_code_identity"] == state["code_identity"] == project_code_identity()
                 and found[0]["controller_code_identity"] == project_controller.code_identity(),
                 "CODE_CHANGED", "Use the original registered project and controller code.")
        child_id = "controller-child-" + fingerprint({"project_id":state["id"], "request_id":body["request_id"]})[:32]
        LocalWorkbench._quality_unclaimed(project, state, (body["request_id"], child_id))
        _require(not any(p.get("status") in ("prepared", "running", "unknown") for p in state.get("controller_requests", []))
                 and not any(a.get("status") in ("pending", "running", "unknown") for a in state["actions"] + state["evidence_actions"]),
                 "EXECUTION_UNKNOWN", "Inspect the original nonterminal operation.")
        project._source(state)
        _require(project.status()["snapshot_ref"] == state["snapshot_ref"], "STALE_STATE", "Project changed during preflight.")

    @staticmethod
    def _preflight_quality_advance_v2(project, state, body):
        from .tabular_quality_plan import check_reference
        LocalWorkbench._preflight_quality_advance(project, state, body)
        revisions = state.get("plan_revisions", [])
        _require(bool(revisions) and revisions[-1].get("request_id") == body["plan_request_id"]
                 and fingerprint(revisions[-1]) == body["plan_sha256"]
                 and type(revisions[-1].get("quality_feedback_ref")) is dict
                 and revisions[-1]["quality_feedback_ref"].get("registration_request_id") == body["registration_request_id"],
                 "CONDITION_NOT_SATISFIED", "Use the current exact quality-linked successor plan.")
        plan = revisions[-1]
        check_reference(project, state, plan["quality_feedback_ref"],
                        based_on_state_version=plan["based_on_state_version"], revision=plan)

    def read_tabular_quality_feedback(self, *, project_id, snapshot_ref, registration_request_id):
        """Read bounded quality feedback for the active original snapshot only."""
        identifier(project_id, "project_id"); identifier(registration_request_id, "registration_request_id")
        _require(type(snapshot_ref) is str and re.fullmatch(r"[a-f0-9]{64}", snapshot_ref) is not None,
                 "INVALID_REQUEST", "Use the original project snapshot identity.")
        with self._connect(readonly=True) as con:
            _, project = self._project(con, project_id, active=True)
        before = project.status()
        _require(before["id"] == project_id and before["snapshot_ref"] == snapshot_ref,
                 "STALE_STATE", "The selected project snapshot changed.")
        value = project.read_tabular_quality_feedback(request_id=registration_request_id)
        after = project.status()
        with self._connect(readonly=True) as con:
            _, current = self._project(con, project_id, active=True)
        _require(before["snapshot_ref"] == after["snapshot_ref"] and current.root == project.root,
                 "STALE_STATE", "The selected project changed while reading quality feedback.")
        return value

    def read_tabular_quality_plan_ref(self, *, project_id, snapshot_ref, registration_request_id):
        """Read the exact quality reference only for the active current snapshot."""
        identifier(project_id, "project_id"); identifier(registration_request_id, "registration_request_id")
        _require(type(snapshot_ref) is str and re.fullmatch(r"[a-f0-9]{64}", snapshot_ref) is not None,
                 "INVALID_REQUEST", "Use the original project snapshot identity.")
        with self._connect(readonly=True) as con:
            _, project = self._project(con, project_id, active=True)
        before = project.status()
        _require(before["id"] == project_id and before["snapshot_ref"] == snapshot_ref,
                 "STALE_STATE", "The selected project snapshot changed.")
        value = project.prepare_tabular_quality_plan_ref(registration_request_id=registration_request_id)
        after = project.status()
        with self._connect(readonly=True) as con:
            _, current = self._project(con, project_id, active=True)
        _require(before["snapshot_ref"] == after["snapshot_ref"] and current.root == project.root,
                 "STALE_STATE", "The selected project changed while reading the quality reference.")
        return value

    @staticmethod
    def _checked_quality_plan(project, body, intent):
        from .tabular_quality_feedback import _manager_claim
        state = project.status()
        found = [p for p in state.get("plan_revisions", []) if p.get("request_id") == body["request_id"]]
        _require(len(found) == 1, "OPERATION_INCOMPLETE", "The original quality plan is absent; inspect without retrying.")
        revision = found[0]
        with project._connect(readonly=True) as con:
            _manager_claim(con, "plan", body["request_id"], intent["intent_sha256"], fingerprint(revision))
        original = project.save_plan(request_id=body["request_id"], expected_state_version=body["expected_state_version"],
                                     plan=body["plan"], reason=body["reason"], _validate_only=True)
        _require(canonical(original) == canonical(revision) and project.status()["snapshot_ref"] == state["snapshot_ref"],
                 "EVIDENCE_CHANGED", "The original quality plan or Project changed.")
        return revision

    def save_quality_plan(self, body):
        """Persist a quality-linked plan with a manager-owned core claim."""
        digest = _body(body, ("request_id", "project_id", "expected_state_version", "plan", "reason"))
        identifier(body["project_id"], "project_id")
        _require(type(body["plan"]) is dict and "quality_feedback_ref" in body["plan"]
                 and type(body["expected_state_version"]) is int and body["expected_state_version"] >= 0,
                 "INVALID_REQUEST", "Use an exact quality-linked plan and state version.")
        _require(len(canonical(body).encode("utf-8")) <= MAX_PLAN_RECOVERY_BYTES,
                 "INVALID_REQUEST", "Original plan request exceeds its recovery bound.")
        with self._writer():
            with self._connect() as con:
                _, project = self._project(con, body["project_id"], active=True)
                self._no_pending_batch(con, body["project_id"], except_id=body["request_id"], evidence=True)
                old = self._old(con, body, digest)
                state = project.status()
                if old is None:
                    # This validation acquires its own Project writer; do not nest it.
                    project.save_plan(request_id=body["request_id"], expected_state_version=body["expected_state_version"],
                                      plan=body["plan"], reason=body["reason"], _validate_only=True)
                    host_sha = host_model_snapshot_sha256(project.root)
                    with project._writer():
                        current = project.status()
                        _require(current["snapshot_ref"] == state["snapshot_ref"]
                                 and host_model_snapshot_sha256(project.root) == host_sha,
                                 "STALE_STATE", "Project or host changed before accepting the plan.")
                        _require(current["state_version"] == body["expected_state_version"]
                                 and current["code_identity"] == project_code_identity()
                                 and batch_code_identity() == _EXPORT_BOOT_IDENTITY,
                                 "CODE_CHANGED", "Use the original Project and manager code.")
                        self._quality_unclaimed(project, current, (body["request_id"],))
                        from .research_project import _check_plan_experience_refs
                        _check_plan_experience_refs(project.root, current,
                            {**body["plan"], "based_on_state_version":body["expected_state_version"]}, code="INVALID_REQUEST", pending=True)
                        from .tabular_quality_plan import check_reference
                        check_reference(project, current, body["plan"]["quality_feedback_ref"],
                                        based_on_state_version=body["expected_state_version"])
                        intent = self._quality_intent(body, digest, "save_quality_plan", current)
                        self._accept(con, body, digest, "save_quality_plan", intent)
                        con.commit()
                else:
                    row = con.execute("SELECT command FROM requests WHERE id=?", (body["request_id"],)).fetchone()
                    _require(row is not None and row["command"] == "save_quality_plan" and old.get("status") in ("preparing", "completed"),
                             "WORKBENCH_CHANGED", "Original quality plan receipt changed.")
                    intent = old.get("intent")
                    self._check_quality_intent(intent, body, digest, "save_quality_plan", state)
            if old is None:
                _, created = project.save_plan(request_id=body["request_id"], expected_state_version=body["expected_state_version"],
                    plan=body["plan"], reason=body["reason"], _manager_intent_sha256=intent["intent_sha256"], _return_created=True)
                _require(created, "OPERATION_INCOMPLETE", "Another caller accepted this plan; inspect without adopting it.")
            revision = self._checked_quality_plan(project, body, intent)
            response = self._response("save_quality_plan", body["request_id"], body["project_id"], status="completed", research_plan=revision)
            if old is not None and old["status"] == "completed":
                saved = old.get("result")
                _require(type(saved) is dict and {k:v for k,v in saved.items() if k != "replayed"}
                         == {k:v for k,v in response.items() if k != "replayed"},
                         "EVIDENCE_CHANGED", "Original manager quality plan receipt differs.")
                return dict(response, replayed=True)
            with self._connect() as con:
                self._save(con, body["request_id"], {"status":"completed", "intent":intent, "result":response})
            return dict(response, replayed=old is not None)

    def register_tabular_quality_conditions(self, body):
        fields = ("request_id","project_id","expected_state_version","controller_request_id","candidate_id","conditions")
        digest = _body(body, fields)
        identifier(body["project_id"], "project_id"); identifier(body["controller_request_id"], "controller_request_id")
        identifier(body["candidate_id"], "candidate_id")
        _require(type(body["expected_state_version"]) is int and body["expected_state_version"] >= 0,
                 "INVALID_REQUEST", "An exact saved state version is required.")
        with self._writer():
            with self._connect() as con:
                _, project = self._project(con, body["project_id"], active=True)
                self._no_pending_batch(con, body["project_id"], except_id=body["request_id"], evidence=True)
                old = self._old(con, body, digest)
                state = project.status()
                if old is None:
                    with project._writer():
                        state = project.status()
                        _require(state["state_version"] == body["expected_state_version"], "STALE_STATE", "The project state changed.")
                        _require(state["code_identity"] == project_code_identity() and batch_code_identity() == _EXPORT_BOOT_IDENTITY,
                                 "CODE_CHANGED", "Use the original project and manager code.")
                        self._preflight_quality_registration(project, state, body)
                        intent = self._quality_intent(body,digest,"register_tabular_quality_conditions",state)
                        self._accept(con,body,digest,"register_tabular_quality_conditions",intent)
                        con.commit()
                else:
                    row = con.execute("SELECT command FROM requests WHERE id=?", (body["request_id"],)).fetchone()
                    _require(row is not None and row["command"] == "register_tabular_quality_conditions"
                             and old.get("status") in ("preparing","completed"), "WORKBENCH_CHANGED", "Original quality registration receipt changed.")
                    intent = old.get("intent")
                    self._check_quality_intent(intent,body,digest,"register_tabular_quality_conditions",state)
            if old is None:
                from .tabular_quality_feedback import _register_with_created
                _, created = _register_with_created(project, **{k:v for k,v in body.items() if k != "project_id"},
                                                     _manager_intent_sha256=intent["intent_sha256"])
                _require(created, "OPERATION_INCOMPLETE", "Another caller accepted this registration; inspect without adopting it.")
            registration = self._quality_registration(project,body,intent)
            response = self._response("register_tabular_quality_conditions",body["request_id"],body["project_id"],
                                      status="completed",registration=registration)
            if old is not None and old["status"] == "completed":
                saved = old.get("result")
                _require(type(saved) is dict and {k:v for k,v in saved.items() if k != "replayed"}
                         == {k:v for k,v in response.items() if k != "replayed"},
                         "EVIDENCE_CHANGED", "Original manager registration receipt differs.")
                return dict(response,replayed=True)
            with self._connect() as con:
                self._save(con,body["request_id"],{"status":"completed","intent":intent,"result":response})
            return dict(response,replayed=old is not None)

    def advance_tabular_quality_feedback(self, body):
        digest = _body(body, ("request_id","project_id","expected_state_version","registration_request_id"))
        identifier(body["project_id"],"project_id"); identifier(body["registration_request_id"],"registration_request_id")
        _require(type(body["expected_state_version"]) is int and body["expected_state_version"] >= 0,
                 "INVALID_REQUEST", "An exact saved state version is required.")
        terminal = {"completed", "failed", "waiting", "needs_review", "rejected"}
        with self._writer():
            with self._connect() as con:
                _, project = self._project(con,body["project_id"],active=True)
                self._no_pending_batch(con,body["project_id"],except_id=body["request_id"],evidence=True)
                old = self._old(con,body,digest)
                state = project.status()
                if old is None:
                    with project._writer():
                        state = project.status()
                        _require(state["state_version"] == body["expected_state_version"], "STALE_STATE", "The project state changed.")
                        _require(state["code_identity"] == project_code_identity() and batch_code_identity() == _EXPORT_BOOT_IDENTITY,
                                 "CODE_CHANGED", "Use the original project and manager code.")
                        self._preflight_quality_advance(project, state, body)
                        intent = self._quality_intent(body,digest,"advance_tabular_quality_feedback",state)
                        self._accept(con,body,digest,"advance_tabular_quality_feedback",intent)
                        con.commit()
                else:
                    row = con.execute("SELECT command FROM requests WHERE id=?", (body["request_id"],)).fetchone()
                    _require(row is not None and row["command"] == "advance_tabular_quality_feedback"
                             and old.get("status") in terminal | {"preparing"}, "WORKBENCH_CHANGED", "Original quality strategy receipt changed.")
                    intent = old.get("intent")
                    self._check_quality_intent(intent,body,digest,"advance_tabular_quality_feedback",state)
                    parents = [p for p in state.get("controller_requests", []) if p.get("request_id") == body["request_id"]]
                    _require(len(parents) == 1, "OPERATION_INCOMPLETE", "Original controller parent is absent; inspect without dispatch.")
                    _require(parents[0].get("status") in terminal, "EXECUTION_UNKNOWN", "Original controller parent is nonterminal; inspect without dispatch.")
                    self._quality_policy_claim(project, parents[0], intent)
            controller = ProjectController(project.root)
            try:
                response = controller.advance_tabular_quality_feedback(request_id=body["request_id"],
                    registration_request_id=body["registration_request_id"], expected_state_version=body["expected_state_version"],
                    _manager_intent_sha256=intent["intent_sha256"])
            except ResearchError as exc:
                state = project.status()
                parents = [p for p in state.get("controller_requests", []) if p.get("request_id") == body["request_id"]]
                failure = ((parents[0].get("result") or {}).get("failure") if len(parents) == 1 and parents[0].get("status") == "rejected" else None)
                if type(failure) is dict and failure == {"code":exc.code,"message":str(exc)}:
                    self._quality_policy_claim(project, parents[0], intent)
                    if old is not None and old["status"] == "rejected":
                        _require(old.get("failure") == failure, "EVIDENCE_CHANGED", "Original rejected receipt differs.")
                    elif old is not None and old["status"] != "preparing":
                        raise ResearchError("EVIDENCE_CHANGED", "Original manager terminal receipt differs.") from None
                    elif old is None or old["status"] == "preparing":
                        with self._connect() as con:self._save(con,body["request_id"],{"status":"rejected","intent":intent,"result":None,"failure":failure})
                raise
            _require(type(response) is dict and response.get("schema_version") == "project-controller-advance-v1"
                     and response.get("project_id") == body["project_id"] and response.get("request_id") == body["request_id"]
                     and response.get("status") in terminal - {"rejected"}, "EVIDENCE_CHANGED", "Original controller response differs.")
            _require(old is not None or response.get("replayed") is False, "OPERATION_INCOMPLETE",
                     "A different caller accepted the core request after the manager intent; inspect without adopting it.")
            parents = [p for p in project.status().get("controller_requests", []) if p.get("request_id") == body["request_id"]]
            _require(len(parents) == 1, "EVIDENCE_CHANGED", "Original policy parent is absent.")
            self._quality_policy_claim(project, parents[0], intent)
            if old is not None and old["status"] in terminal:
                saved = old.get("result")
                _require(type(saved) is dict and {k:v for k,v in saved.items() if k != "replayed"}
                         == {k:v for k,v in response.items() if k != "replayed"}, "EVIDENCE_CHANGED", "Original manager receipt differs.")
                return response
            with self._connect() as con:
                self._save(con,body["request_id"],{"status":response["status"],"intent":intent,"result":copy.deepcopy(response)})
            return response

    def advance_tabular_quality_feedback_v2(self, body):
        digest = _body(body, ("request_id","project_id","expected_state_version","registration_request_id","plan_request_id","plan_sha256"))
        identifier(body["project_id"],"project_id"); identifier(body["registration_request_id"],"registration_request_id")
        identifier(body["plan_request_id"],"plan_request_id")
        _require(type(body["plan_sha256"]) is str and re.fullmatch(r"[a-f0-9]{64}",body["plan_sha256"]) is not None,
                 "INVALID_REQUEST", "Use the exact current plan identity.")
        _require(type(body["expected_state_version"]) is int and body["expected_state_version"] >= 0,
                 "INVALID_REQUEST", "An exact saved state version is required.")
        terminal = {"completed", "failed", "waiting", "needs_review", "rejected"}
        with self._writer():
            with self._connect() as con:
                _, project = self._project(con,body["project_id"],active=True)
                self._no_pending_batch(con,body["project_id"],except_id=body["request_id"],evidence=True)
                old = self._old(con,body,digest)
                state = project.status()
                if old is None:
                    with project._writer():
                        state = project.status()
                        _require(state["state_version"] == body["expected_state_version"], "STALE_STATE", "The project state changed.")
                        _require(state["code_identity"] == project_code_identity() and batch_code_identity() == _EXPORT_BOOT_IDENTITY,
                                 "CODE_CHANGED", "Use the original project and manager code.")
                        self._preflight_quality_advance_v2(project, state, body)
                        intent = self._quality_intent(body,digest,"advance_tabular_quality_feedback_v2",state)
                        self._accept(con,body,digest,"advance_tabular_quality_feedback_v2",intent)
                        con.commit()
                else:
                    row = con.execute("SELECT command FROM requests WHERE id=?", (body["request_id"],)).fetchone()
                    _require(row is not None and row["command"] == "advance_tabular_quality_feedback_v2"
                             and old.get("status") in terminal | {"preparing"}, "WORKBENCH_CHANGED", "Original quality strategy receipt changed.")
                    intent = old.get("intent")
                    self._check_quality_intent(intent,body,digest,"advance_tabular_quality_feedback_v2",state)
                    parents = [p for p in state.get("controller_requests", []) if p.get("request_id") == body["request_id"]]
                    _require(len(parents) == 1, "OPERATION_INCOMPLETE", "Original controller parent is absent; inspect without dispatch.")
                    _require(parents[0].get("status") in terminal, "EXECUTION_UNKNOWN", "Original controller parent is nonterminal; inspect without dispatch.")
                    self._quality_policy_claim(project, parents[0], intent)
            controller = ProjectController(project.root)
            try:
                response = controller.advance_tabular_quality_feedback_v2(request_id=body["request_id"],
                    registration_request_id=body["registration_request_id"], expected_state_version=body["expected_state_version"],
                    plan_request_id=body["plan_request_id"], plan_sha256=body["plan_sha256"],
                    _manager_intent_sha256=intent["intent_sha256"])
            except ResearchError as exc:
                state = project.status()
                parents = [p for p in state.get("controller_requests", []) if p.get("request_id") == body["request_id"]]
                failure = ((parents[0].get("result") or {}).get("failure") if len(parents) == 1 and parents[0].get("status") == "rejected" else None)
                if type(failure) is dict and failure == {"code":exc.code,"message":str(exc)}:
                    self._quality_policy_claim(project, parents[0], intent)
                    if old is not None and old["status"] == "rejected":
                        _require(old.get("failure") == failure, "EVIDENCE_CHANGED", "Original rejected receipt differs.")
                    elif old is not None and old["status"] != "preparing":
                        raise ResearchError("EVIDENCE_CHANGED", "Original manager terminal receipt differs.") from None
                    elif old is None or old["status"] == "preparing":
                        with self._connect() as con:self._save(con,body["request_id"],{"status":"rejected","intent":intent,"result":None,"failure":failure})
                raise
            _require(type(response) is dict and response.get("schema_version") == "project-controller-advance-v1"
                     and response.get("project_id") == body["project_id"] and response.get("request_id") == body["request_id"]
                     and response.get("status") in terminal - {"rejected"}, "EVIDENCE_CHANGED", "Original controller response differs.")
            _require(old is not None or response.get("replayed") is False, "OPERATION_INCOMPLETE",
                     "A different caller accepted the core request after the manager intent; inspect without adopting it.")
            parents = [p for p in project.status().get("controller_requests", []) if p.get("request_id") == body["request_id"]]
            _require(len(parents) == 1, "EVIDENCE_CHANGED", "Original policy parent is absent.")
            self._quality_policy_claim(project, parents[0], intent)
            if old is not None and old["status"] in terminal:
                saved = old.get("result")
                _require(type(saved) is dict and {k:v for k,v in saved.items() if k != "replayed"}
                         == {k:v for k,v in response.items() if k != "replayed"}, "EVIDENCE_CHANGED", "Original manager receipt differs.")
                return response
            with self._connect() as con:
                self._save(con,body["request_id"],{"status":response["status"],"intent":intent,"result":copy.deepcopy(response)})
            return response

    def advance(self, body):
        digest = _body(body, ("request_id", "project_id", "expected_state_version", "proposal"))
        _require(type(body["expected_state_version"]) is int and body["expected_state_version"] >= 0,
                 "INVALID_REQUEST", "An exact saved state version is required.")
        return self._advance_receipt(body, digest, "advance", evidence=False)

    def advance_feedback(self, body):
        digest = _body(body, ("request_id", "project_id", "expected_state_version", "registration_request_id"))
        _require(type(body["expected_state_version"]) is int and body["expected_state_version"] >= 0,
                 "INVALID_REQUEST", "An exact saved state version is required.")
        identifier(body["registration_request_id"], "registration_request_id")
        return self._advance_receipt(body, digest, "advance_feedback", evidence=True)

    def _advance_receipt(self, body, digest, command, *, evidence):
        terminal = {"completed", "failed", "waiting", "needs_review"}
        with self._writer():
            with self._connect() as con:
                _, project = self._project(con, body["project_id"], active=True)
                self._no_pending_batch(con, body["project_id"], evidence=evidence)
                old = self._old(con, body, digest)
                if old is None:
                    self._accept(con, body, digest, command, {"project_id": body["project_id"], "request_sha256": digest})
                else:
                    row = con.execute("SELECT command FROM requests WHERE id=?", (body["request_id"],)).fetchone()
                    _require(row is not None and row["command"] == command and type(old) is dict and type(old.get("intent")) is dict
                             and old["intent"].get("project_id") == body["project_id"]
                             and old["intent"].get("request_sha256") == digest
                             and type(old.get("status")) is str and old["status"] in terminal | {"preparing", "unknown"},
                             "WORKBENCH_CHANGED", "The original manager receipt binding changed.")
                    if old["status"] == "preparing":
                        _require("result" in old and old["result"] is None,
                                 "EVIDENCE_CHANGED", "The unfinished manager receipt has a missing or unexpected result.")
                    else:
                        saved = old.get("result")
                        _require(type(saved) is dict and saved.get("schema_version") == "project-controller-advance-v1"
                                 and saved.get("project_id") == body["project_id"] and saved.get("request_id") == body["request_id"]
                                 and saved.get("status") == old["status"],
                                 "EVIDENCE_CHANGED", "The saved manager receipt has an inconsistent core identity or status.")
            # Always ask the original controller to check and replay its own ID.
            controller = ProjectController(project.root)
            if command == "advance":
                response = controller.advance_selection(request_id=body["request_id"], proposal=body["proposal"],
                                                        expected_state_version=body["expected_state_version"])
            elif command == "advance_feedback":
                response = controller.advance_feedback(request_id=body["request_id"], registration_request_id=body["registration_request_id"],
                                                       expected_state_version=body["expected_state_version"])
            else:
                response = controller.advance_recipe(request_id=body["request_id"], recipe=body["recipe"],
                                                     expected_state_version=body["expected_state_version"])
            _require(type(response) is dict and response.get("schema_version") == "project-controller-advance-v1"
                     and response.get("project_id") == body["project_id"] and response.get("request_id") == body["request_id"]
                     and type(response.get("status")) is str and response["status"] in terminal | {"unknown"},
                     "EVIDENCE_CHANGED", "The original controller response is incomplete or belongs to another request.")
            if response["status"] == "completed":
                child = (response.get("result") or {}).get("child") if type(response.get("result")) is dict else None
                _require(type(child) is dict and child.get("status") == "completed"
                         and type(response.get("child_request_id")) is str and bool(response["child_request_id"])
                         and child.get("request_id") == response["child_request_id"],
                         "EVIDENCE_CHANGED", "A completed controller response requires its original completed child.")
            if old is not None and (old["status"] in terminal or old["status"] == response["status"] == "unknown"):
                saved = old.get("result")
                _require(type(saved) is dict and {k: v for k, v in saved.items() if k != "replayed"}
                         == {k: v for k, v in response.items() if k != "replayed"},
                         "EVIDENCE_CHANGED", "The saved manager receipt differs from the replayed core response.")
                return response
            record = copy.deepcopy(old) if old is not None else {"intent": {"project_id": body["project_id"], "request_sha256": digest}}
            if old is not None and old["status"] == "unknown" and response["status"] != "unknown":
                _require("previous_unknown" not in record, "EVIDENCE_CHANGED", "The original unknown receipt history changed.")
                record["previous_unknown"] = copy.deepcopy(old["result"])
            record.update(status=response["status"], result=copy.deepcopy(response))
            with self._connect() as con:
                self._save(con, body["request_id"], record)
            return response

    @staticmethod
    def _check_plan_intent(request_id, digest, record):
        intent = record.get("intent") if type(record) is dict else None
        fields = {"project_id", "request_sha256", "recovery_version", "body", "snapshot_ref", "state_version",
                  "run_id", "source_sha256", "source_snapshot_sha256", "project_code_identity", "manager_source_identity", "host_snapshot_sha256"}
        _require(type(record) is dict and set(record) == {"status", "intent", "result"}
                 and ((record["status"] == "preparing" and record["result"] is None)
                      or (record["status"] == "completed" and type(record["result"]) is dict
                          and record["result"].get("status") == "completed" and record["result"].get("command") == "save_plan"
                          and record["result"].get("request_id") == request_id))
                 and type(intent) is dict and set(intent) == fields and intent.get("recovery_version") == PLAN_RECOVERY_VERSION
                 and type(intent.get("body")) is dict and len(canonical(intent["body"]).encode("utf-8")) <= MAX_PLAN_RECOVERY_BYTES
                 and _body(intent["body"], ("request_id", "project_id", "expected_state_version", "plan", "reason")) == digest
                 and intent["request_sha256"] == digest and intent["body"]["request_id"] == request_id
                 and intent["body"]["project_id"] == intent["project_id"]
                 and intent["body"]["expected_state_version"] == intent["state_version"]
                 and type(intent["state_version"]) is int and intent["state_version"] >= 0
                 and type(intent["body"].get("plan")) is dict and "experience_case_refs" in intent["body"]["plan"]
                 and all(type(intent.get(k)) is str and re.fullmatch(r"[0-9a-f]{64}", intent[k]) for k in
                         ("request_sha256", "snapshot_ref", "source_sha256", "source_snapshot_sha256", "project_code_identity",
                          "manager_source_identity", "host_snapshot_sha256")),
                 "EVIDENCE_CHANGED", "The original recoverable plan intent changed.")
        identifier(intent["run_id"], "run_id")
        if record["status"] == "completed":
            result = record["result"]
            _require(set(result) == {"schema_version", "command", "request_id", "project_id", "replayed", "status", "research_plan"}
                     and result["schema_version"] == "local-workbench-command-v1" and result["project_id"] == intent["project_id"]
                     and type(result["replayed"]) is bool and type(result["research_plan"]) is dict,
                     "EVIDENCE_CHANGED", "The original completed plan receipt changed.")
        return intent

    def save_plan(self, body):
        digest = _body(body, ("request_id", "project_id", "expected_state_version", "plan", "reason"))
        _require(type(body.get("plan")) is not dict or "quality_feedback_ref" not in body["plan"],
                 "INVALID_REQUEST", "Quality-linked plans are only available through the Project Python API.")
        versioned = type(body.get("plan")) is dict and "experience_case_refs" in body["plan"]
        with self._writer():
            with self._connect() as con:
                _, project = self._project(con, body["project_id"], active=True)
                old = self._old(con, body, digest)
                self._no_pending_batch(con, body["project_id"], body["request_id"], evidence=True)
                if old is not None and old["status"] == "completed":
                    if versioned:
                        if old.get("intent", {}).get("recovery_version") == PLAN_RECOVERY_VERSION:
                            self._check_plan_intent(body["request_id"], digest, old)
                        revision = project.save_plan(request_id=body["request_id"], expected_state_version=body["expected_state_version"],
                                                     plan=body["plan"], reason=body["reason"], _validate_only=True)
                        _require(revision == old.get("result", {}).get("research_plan"), "EVIDENCE_CHANGED",
                                 "The saved plan receipt differs from its original Project revision.")
                    return self._completed(old)
                if old is None:
                    intent = {"project_id": body["project_id"]}
                    if versioned:
                        _require(batch_code_identity() == _EXPORT_BOOT_IDENTITY, "CODE_CHANGED", "Restart with the loaded manager source.")
                        _require(len(canonical(body).encode("utf-8")) <= MAX_PLAN_RECOVERY_BYTES,
                                 "INVALID_REQUEST", "Original plan request exceeds its recovery bound.")
                        state = project.status()
                        project._source(state)
                        project.save_plan(request_id=body["request_id"], expected_state_version=body["expected_state_version"],
                                          plan=body["plan"], reason=body["reason"], _validate_only=True)
                        _require(project.status()["snapshot_ref"] == state["snapshot_ref"], "STALE_STATE", "Project changed before plan intent.")
                        intent = {"project_id": state["id"], "request_sha256": digest, "recovery_version": PLAN_RECOVERY_VERSION,
                                  "body": copy.deepcopy(body), "snapshot_ref": state["snapshot_ref"], "state_version": state["state_version"],
                                  "run_id": state["run_id"], "source_sha256": state["registration"]["source_sha256"],
                                  "source_snapshot_sha256": state["source_snapshot_sha256"],
                                  "project_code_identity": state["code_identity"], "manager_source_identity": batch_code_identity(),
                                  "host_snapshot_sha256": host_model_snapshot_sha256(project.root)}
                    self._accept(con, body, digest, "save_plan", intent)
                elif versioned:
                    intent = self._check_plan_intent(body["request_id"], digest, old)
                    state = project.status()
                    _require(state["id"] == intent["project_id"] and state["run_id"] == intent["run_id"]
                             and state["registration"]["source_sha256"] == intent["source_sha256"]
                             and state["source_snapshot_sha256"] == intent["source_snapshot_sha256"]
                             and state["code_identity"] == intent["project_code_identity"] == project_code_identity()
                             and batch_code_identity() == _EXPORT_BOOT_IDENTITY == intent["manager_source_identity"],
                             "CODE_CHANGED", "Use the original project and manager source identities.")
                    project._source(state)
                    saved = [item for item in state.get("plan_revisions", []) if item.get("request_id") == body["request_id"]]
                    _require(len(saved) <= 1, "EVIDENCE_CHANGED", "Multiple saved original plans are ambiguous.")
                    if not saved:
                        _require(state["state_version"] == intent["state_version"] and state["snapshot_ref"] == intent["snapshot_ref"]
                                 and host_model_snapshot_sha256(project.root) == intent["host_snapshot_sha256"],
                                 "STALE_STATE", "The original unsaved plan snapshot or host state changed.")
            revision = project.save_plan(request_id=body["request_id"], expected_state_version=body["expected_state_version"],
                                         plan=body["plan"], reason=body["reason"])
            response = self._response("save_plan", body["request_id"], body["project_id"], status="completed",
                                      research_plan=revision)
            if old is not None:
                response["replayed"] = True
            with self._connect() as con:
                self._save(con, body["request_id"], {"status": "completed", "result": response,
                                                    "intent": intent if versioned else {"project_id": body["project_id"]}})
            return response

    def resume_plan(self, body):
        _body(body, ("request_id", "project_id"))
        with self._connect(readonly=True) as con:
            self._project(con, body["project_id"], active=True)
            row = con.execute("SELECT digest,record FROM requests WHERE id=? AND command='save_plan'", (body["request_id"],)).fetchone()
            _require(row is not None, "ARTIFACT_NOT_FOUND", "No original plan request matches this ID.")
            record = tabular._parse(row["record"].encode("utf-8"))
            try:
                intent = self._check_plan_intent(body["request_id"], row["digest"], record)
            except ResearchError:
                raise ResearchError("OPERATION_INCOMPLETE", "The original plan body is unavailable or changed; do not reconstruct it.") from None
            _require(intent["project_id"] == body["project_id"], "EVIDENCE_CHANGED", "The original plan belongs to another Project.")
            original = copy.deepcopy(intent["body"])
        result = self.save_plan(original)
        revision = result["research_plan"]
        response = self._response("plan-resume", body["request_id"], body["project_id"], status="completed",
                                  plan_revision={key: revision[key] for key in ("request_id", "version", "based_on_state_version")})
        response["replayed"] = True
        return response

    def register_hypothesis(self, body):
        digest = _body(body, ("request_id", "project_id", "expected_state_version", "hypothesis"))
        with self._writer():
            with self._connect() as con:
                _, project = self._project(con, body["project_id"], active=True)
                self._no_pending_batch(con, body["project_id"], evidence=True)
                old = self._old(con, body, digest)
                if old is not None:
                    row = con.execute("SELECT command FROM requests WHERE id=?", (body["request_id"],)).fetchone()
                    _require(row is not None and row["command"] == "register_hypothesis", "IDEMPOTENCY_CONFLICT",
                             "The original request belongs to another command.")
                if old is not None and old["status"] == "completed":
                    return self._completed(old)
                if old is None:
                    self._accept(con, body, digest, "register_hypothesis", {"project_id": body["project_id"]})
            registration = project.register_hypothesis(request_id=body["request_id"],
                expected_state_version=body["expected_state_version"], hypothesis=body["hypothesis"])
            response = self._response("register_hypothesis", body["request_id"], body["project_id"],
                                      status="completed", hypothesis=registration, replayed=old is not None)
            with self._connect() as con:
                self._save(con, body["request_id"], {"status": "completed", "result": response,
                                                    "intent": {"project_id": body["project_id"]}})
            return response

    @staticmethod
    def _preflight_staged_hypothesis(project, state, body, con):
        from . import hypothesis_feedback as h, staged_relevance_adapter as staged
        hypothesis = body["hypothesis"]
        _require(type(hypothesis) is dict and set(hypothesis) == {"candidate_id", "controller_request_id", "conditions", "branches"},
                 "INVALID_REQUEST", "Use exactly two staged conditions and both explicit branches.")
        condition = h._condition(hypothesis)
        _require(set(item["metric"] for item in condition["all"]) == {"recall@20", "mrr@10"},
                 "INVALID_REQUEST", "Use one recall@20 and one mrr@10 validation condition.")
        h._branches(hypothesis["branches"], staged.TOOL_ID)
        target = hypothesis["controller_request_id"]
        _require(body["request_id"] != target, "INVALID_REQUEST", "Use separate registration and future controller IDs.")
        child = "controller-child-" + fingerprint({"project_id": state["id"], "request_id": target})[:32]
        LocalWorkbench._quality_unclaimed(project, state, (body["request_id"], target, child))
        for value in (target, child):
            _require(con.execute("SELECT 1 FROM requests WHERE id=?", (value,)).fetchone() is None,
                     "IDEMPOTENCY_CONFLICT", "A future ID is already used in the workbench.")
        records = state.get("hypothesis_registrations", [])
        _require(type(records) is list and len(records) < h.MAX_ITEMS, "LIMIT_EXCEEDED", "Hypothesis registration limit reached.")
        from .tabular_quality_feedback import _checked_collection
        quality = state.get("tabular_quality_registrations", [])
        _checked_collection(quality)
        for item in records:
            h._check_record(item)
        for item in records + quality:
            _require(item.get("controller_request_id") not in (body["request_id"], target, child),
                     "IDEMPOTENCY_CONFLICT", "A future controller ID already has a registration.")
        host = HostModelSelection(project.root).status()
        _require(not any(item.get("status") in PENDING for item in host["requests"]),
                 "HOST_SELECTION_PENDING", "Inspect the existing Host request first.")
        _require(not any(item.get("request_id") in (body["request_id"], target, child)
                         or item.get("controller_request_id") in (body["request_id"], target, child)
                         for item in host["requests"]), "IDEMPOTENCY_CONFLICT", "An original Host ID is already used.")
        _require(state.get("plan_revisions") and state["registration"].get("method_id") == staged.TOOL_ID
                 and not any(item["status"] in ("prepared", "running", "unknown") for item in state.get("controller_requests", []))
                 and not any(item["status"] == "reserved" for item in state.get("local_model_requests", [])),
                 "CONDITION_NOT_SATISFIED", "Use an idle staged project with a saved plan.")
        project._source(state)
        context = ProjectController(project.root)._selection_context(state, "next_check")
        candidates = [item for item in context["candidates"] if item["id"] == hypothesis["candidate_id"]]
        _require(not context["blockers"] and len(candidates) == 1 and candidates[0]["method_id"] == staged.TOOL_ID
                 and candidates[0]["parameters"] == {} and candidates[0]["evaluation_ref"] == "staged-relevance-development-v1",
                 "CONDITION_NOT_SATISFIED", "Choose the unique eligible staged primary.")
        _require(project.status()["snapshot_ref"] == state["snapshot_ref"], "STALE_STATE", "Project changed during preflight.")
        return context

    def _staged_hypothesis_intent(self, body, digest, state, context):
        intent = {"schema_version": "local-staged-hypothesis-intent-v1", "command": "register_staged_hypothesis",
                  "project_id": state["id"], "run_id": state["run_id"], "body": copy.deepcopy(body), "request_sha256": digest,
                  "source_snapshot_sha256": state["source_snapshot_sha256"], "project_code_identity": state["code_identity"],
                  "controller_code_identity": project_controller.code_identity(), "manager_code_identity": batch_code_identity(),
                  "manager_root": str(self.root.resolve()), "selection_context": copy.deepcopy(context),
                  "plan_sha256": fingerprint(state["plan_revisions"][-1]), "nonce": secrets.token_hex(32)}
        intent["intent_sha256"] = fingerprint(intent)
        return intent

    def _finish_staged_hypothesis(self, project, body, digest, record):
        # Cooperative Project writers cannot change the source, state or claim
        # during this check. Direct database tampering is outside this lock.
        with project._writer():
            return self._finish_staged_hypothesis_locked(project, body, digest, record)

    def _finish_staged_hypothesis_locked(self, project, body, digest, record):
        from . import hypothesis_feedback as h, project_selection
        from .tabular_quality_feedback import _manager_claim
        _check_staged_runtime()
        intent = record.get("intent")
        fields = {"schema_version", "command", "project_id", "run_id", "body", "request_sha256", "source_snapshot_sha256",
                  "project_code_identity", "controller_code_identity", "manager_code_identity", "manager_root", "selection_context",
                  "plan_sha256", "nonce", "intent_sha256"}
        state = project.status()
        _require(type(intent) is dict and set(intent) == fields and intent["schema_version"] == "local-staged-hypothesis-intent-v1"
                 and intent["command"] == "register_staged_hypothesis" and canonical(intent["body"]) == canonical(body)
                 and intent["request_sha256"] == digest == fingerprint(body)
                 and intent["intent_sha256"] == fingerprint({k: v for k, v in intent.items() if k != "intent_sha256"})
                 and intent["project_id"] == body["project_id"] == state["id"] and intent["run_id"] == state["run_id"]
                 and intent["source_snapshot_sha256"] == state["source_snapshot_sha256"]
                 and intent["project_code_identity"] == state["code_identity"] == project_code_identity()
                 and intent["controller_code_identity"] == project_controller.code_identity()
                 and intent["manager_code_identity"] == batch_code_identity() == _EXPORT_BOOT_IDENTITY
                 and intent["manager_root"] == str(self.root.resolve()) and type(intent["nonce"]) is str
                 and re.fullmatch(r"[a-f0-9]{64}", intent["nonce"]) is not None,
                 "EVIDENCE_CHANGED", "Original staged registration intent or identities changed.")
        context = intent["selection_context"]
        _require(type(context) is dict and canonical(project_selection.seal_context({k: v for k, v in context.items() if k != "context_sha256"})) == canonical(context),
                 "EVIDENCE_CHANGED", "Original staged context changed.")
        found = [item for item in state.get("hypothesis_registrations", []) if item.get("request_id") == body["request_id"]]
        _require(len(found) == 1, "OPERATION_INCOMPLETE", "The original core registration is absent; inspect without creating it.")
        saved = found[0]
        h._check_record(saved)
        expected = {k: copy.deepcopy(v) for k, v in body.items() if k != "project_id"}
        candidates = [item for item in context.get("candidates", []) if item.get("id") == body["hypothesis"]["candidate_id"]]
        _require(canonical(saved["request"]) == canonical(expected) and saved["schema_version"] == "hypothesis-registration-v2"
                 and saved["project_id"] == state["id"] and saved["run_id"] == state["run_id"]
                 and saved["source_sha256"] == state["registration"]["source_sha256"]
                 and saved["source_snapshot_sha256"] == state["source_snapshot_sha256"]
                 and saved["scope_sha256"] == fingerprint(state["source_scope"])
                 and saved["project_code_identity"] == intent["project_code_identity"]
                 and saved["controller_code_identity"] == intent["controller_code_identity"]
                 and saved["selection_context_sha256"] == context["context_sha256"]
                 and saved["plan_sha256"] == intent["plan_sha256"]
                 and context.get("project_id") == state["id"] and context.get("run_id") == state["run_id"]
                 and context.get("state_version") == body["expected_state_version"]
                 and context.get("project_code_identity") == intent["project_code_identity"]
                 and context.get("controller_code_identity") == intent["controller_code_identity"]
                 and fingerprint(context.get("domain_scope")) == saved["scope_sha256"]
                 and fingerprint(context.get("research_plan")) == saved["plan_sha256"]
                 and len(candidates) == 1 and canonical(candidates[0]) == canonical(saved["candidate"])
                 and any(plan["version"] == saved["plan_version"] and fingerprint(plan) == saved["plan_sha256"]
                         for plan in state.get("plan_revisions", [])),
                 "EVIDENCE_CHANGED", "Original registration, context or historical plan differs.")
        project._source(state)
        with project._connect(readonly=True) as con:
            _manager_claim(con, "hypothesis_registration", body["request_id"], intent["intent_sha256"], saved["registration_sha256"])
        project._source(state)
        _require(project.status()["snapshot_ref"] == state["snapshot_ref"] and project_code_identity() == intent["project_code_identity"]
                 and project_controller.code_identity() == intent["controller_code_identity"]
                 and batch_code_identity() == intent["manager_code_identity"] == _EXPORT_BOOT_IDENTITY,
                 "EVIDENCE_CHANGED", "Project or code changed during registration verification.")
        with project._connect(readonly=True) as con:
            _manager_claim(con, "hypothesis_registration", body["request_id"], intent["intent_sha256"], saved["registration_sha256"])
        _check_staged_runtime()
        return copy.deepcopy(saved)

    def register_staged_hypothesis(self, body):
        fields = ("request_id", "project_id", "expected_state_version", "hypothesis")
        digest = _body(body, fields)
        identifier(body["project_id"], "project_id")
        _require(type(body["expected_state_version"]) is int and body["expected_state_version"] >= 0,
                 "INVALID_REQUEST", "Use an exact project version.")
        _check_staged_runtime()
        with self._writer():
            with self._connect() as con:
                _, project = self._project(con, body["project_id"], active=True)
                self._no_pending_batch(con, body["project_id"], except_id=body["request_id"], evidence=True)
                old = self._old(con, body, digest)
                if old is None:
                    with project._writer():
                        state = project.status()
                        _require(state["state_version"] == body["expected_state_version"], "STALE_STATE", "Project state changed.")
                        _require(state["code_identity"] == project_code_identity() and batch_code_identity() == _EXPORT_BOOT_IDENTITY,
                                 "CODE_CHANGED", "Use the original project and manager code.")
                        context = self._preflight_staged_hypothesis(project, state, body, con)
                        _check_staged_runtime()
                        intent = self._staged_hypothesis_intent(body, digest, state, context)
                        self._accept(con, body, digest, "register_staged_hypothesis", intent)
                        con.commit()
                else:
                    row = con.execute("SELECT command FROM requests WHERE id=?", (body["request_id"],)).fetchone()
                    _require(row is not None and row["command"] == "register_staged_hypothesis" and type(old) is dict
                             and type(old.get("intent")) is dict and old.get("status") in ("preparing", "completed")
                             and (old["status"] != "preparing" or old.get("result") is None),
                             "OPERATION_INCOMPLETE", "Original staged registration receipt is unavailable.")
                    intent = old["intent"]
            if old is None:
                from .hypothesis_feedback import _register_with_created
                _check_staged_runtime()
                _, created = _register_with_created(project, **{k: v for k, v in body.items() if k != "project_id"},
                                                     _manager_intent_sha256=intent["intent_sha256"])
                _require(created, "OPERATION_INCOMPLETE", "Another caller accepted this ID; inspect without adopting it.")
                record = {"intent": intent}
            else:
                record = old
            registration = self._finish_staged_hypothesis(project, body, digest, record)
            response = self._response("register_staged_hypothesis", body["request_id"], body["project_id"],
                                      status="completed", registration=registration)
            if old is not None and old["status"] == "completed":
                _require(type(old.get("result")) is dict and canonical({k: v for k, v in old["result"].items() if k != "replayed"})
                         == canonical({k: v for k, v in response.items() if k != "replayed"}),
                         "EVIDENCE_CHANGED", "Original staged registration receipt changed.")
                return dict(response, replayed=True)
            with self._connect() as con:
                self._save(con, body["request_id"], {"status": "completed", "intent": intent, "result": response})
            return dict(response, replayed=old is not None)

    def resume_staged_hypothesis(self, body):
        _body(body, ("request_id", "project_id"))
        _check_staged_runtime()
        with self._writer():
            with self._connect() as con:
                _, project = self._project(con, body["project_id"], active=True)
                self._no_pending_batch(con, body["project_id"], except_id=body["request_id"], evidence=True)
                row = con.execute("SELECT command,digest,record FROM requests WHERE id=?", (body["request_id"],)).fetchone()
                _require(row is not None and row["command"] == "register_staged_hypothesis",
                         "OPERATION_INCOMPLETE", "The original staged manager intent is absent; do not create a replacement.")
                record = tabular._parse(row["record"].encode("utf-8"))
                _require(record.get("status") in ("preparing", "completed") and type(record.get("intent")) is dict
                         and type(record["intent"].get("body")) is dict
                         and record["intent"]["body"].get("request_id") == body["request_id"]
                         and record["intent"]["body"].get("project_id") == body["project_id"]
                         and (record["status"] != "preparing" or record.get("result") is None),
                         "OPERATION_INCOMPLETE", "The original staged intent or body is unavailable.")
                original = record["intent"]["body"]
                _require(_body(original, ("request_id", "project_id", "expected_state_version", "hypothesis")) == row["digest"],
                         "EVIDENCE_CHANGED", "The original staged request body changed.")
            registration = self._finish_staged_hypothesis(project, original, row["digest"], record)
            response = self._response("register_staged_hypothesis", body["request_id"], body["project_id"],
                                      status="completed", registration=registration)
            if record["status"] == "completed":
                _require(type(record.get("result")) is dict and canonical({k: v for k, v in record["result"].items() if k != "replayed"})
                         == canonical({k: v for k, v in response.items() if k != "replayed"}),
                         "EVIDENCE_CHANGED", "Original staged registration receipt changed.")
            else:
                with self._connect() as con:
                    self._save(con, body["request_id"], {"status": "completed", "intent": record["intent"], "result": response})
            return dict(response, replayed=True)

    def _staged_primary_registration_locked(self, con, project, registration_request_id):
        row = con.execute("SELECT command,digest,record FROM requests WHERE id=?", (registration_request_id,)).fetchone()
        _require(row is not None and row["command"] == "register_staged_hypothesis",
                 "OPERATION_INCOMPLETE", "The original manager registration is unavailable.")
        record = tabular._parse(row["record"].encode("utf-8"))
        _require(type(record) is dict and record.get("status") == "completed" and type(record.get("intent")) is dict
                 and type(record["intent"].get("body")) is dict, "OPERATION_INCOMPLETE", "The original manager registration is incomplete.")
        original = record["intent"]["body"]
        _require(_body(original, ("request_id", "project_id", "expected_state_version", "hypothesis")) == row["digest"],
                 "EVIDENCE_CHANGED", "The original registration body changed.")
        registration = self._finish_staged_hypothesis_locked(project, original, row["digest"], record)
        _require(type(record.get("result")) is dict and record["result"].get("registration") == registration,
                 "EVIDENCE_CHANGED", "The original manager registration receipt differs.")
        return registration, record["intent"]["intent_sha256"]

    def _preflight_staged_primary_locked(self, con, project, state, body):
        from . import hypothesis_feedback, project_selection, staged_relevance_adapter as staged
        registration, registration_intent = self._staged_primary_registration_locked(con, project, body["registration_request_id"])
        _require(registration["registration_sha256"] == body["registration_sha256"]
                 and registration["controller_request_id"] == body["request_id"]
                 and state["state_version"] == body["expected_state_version"],
                 "EVIDENCE_CHANGED", "Use the exact registered future ID, registration and project version.")
        _require(state.get("plan_revisions") and fingerprint(state["plan_revisions"][-1]) == registration["plan_sha256"]
                 and state["source_snapshot_sha256"] == registration["source_snapshot_sha256"]
                 and state["code_identity"] == registration["project_code_identity"] == project_code_identity()
                 and project_controller.code_identity() == registration["controller_code_identity"],
                 "EVIDENCE_CHANGED", "The registered plan, source or producer changed.")
        _require(not any(item.get("status") in ("prepared", "running", "unknown") for item in state.get("controller_requests", []))
                 and not any(item.get("status") in ("running", "unknown") for item in state.get("actions", []) + state.get("evidence_actions", []))
                 and not any(item.get("status") in PENDING for item in HostModelSelection(project.root).status()["requests"]),
                 "EXECUTION_UNKNOWN", "Inspect the original unfinished project or Host operation.")
        child = "controller-child-" + fingerprint({"project_id": state["id"], "request_id": body["request_id"]})[:32]
        self._quality_unclaimed(project, state, (body["request_id"], child))
        _require(con.execute("SELECT 1 FROM requests WHERE id=?", (child,)).fetchone() is None,
                 "IDEMPOTENCY_CONFLICT", "The derived child ID is already used by the workbench.")
        project._source(state)
        context = ProjectController(project.root)._selection_context(state, "next_check")
        items = [item for item in hypothesis_feedback.feedback_context(project, state)["items"]
                 if item["request_id"] == body["registration_request_id"]]
        _require(len(items) == 1 and items[0]["outcome"] == "unknown" and items[0]["unknown_reason"] == "controller_not_started"
                 and not context["blockers"] and registration["candidate"] in context["candidates"]
                 and registration["candidate"]["method_id"] == staged.TOOL_ID,
                 "CONDITION_NOT_SATISFIED", "The registered primary is not the unique unstarted eligible candidate.")
        proposal = {"schema_version":"project-selection-proposal-v1", "context_sha256":context["context_sha256"],
                    "provider":{"kind":"operator_assistant", "label":"Explicit staged primary authorization"},
                    "choice":{"kind":"execute", "candidate_id":registration["candidate"]["id"]},
                    "rationale":body["reason"], "evidence_citation_ids":[]}
        selected = project_selection.validate_proposal(context, proposal)
        plan = ProjectController(project.root)._selected_plan(state, "next_check", proposal, context=context)
        _require(selected["candidate"] == registration["candidate"] and plan["executable"]
                 and plan["decision"]["next_action"]["method_id"] == staged.TOOL_ID
                 and project.status()["snapshot_ref"] == state["snapshot_ref"],
                 "CONDITION_NOT_SATISFIED", "The original primary is not executable within the current budget.")
        return registration, registration_intent, context, proposal

    def _staged_primary_intent(self, body, digest, state, registration_intent, context, proposal):
        intent = {"schema_version":"local-staged-primary-intent-v1", "command":"advance_staged_primary",
                  "body":copy.deepcopy(body), "request_sha256":digest, "project_id":state["id"], "run_id":state["run_id"],
                  "source_snapshot_sha256":state["source_snapshot_sha256"], "project_code_identity":state["code_identity"],
                  "controller_code_identity":project_controller.code_identity(), "manager_code_identity":batch_code_identity(),
                  "manager_root":str(self.root.resolve()), "registration_intent_sha256":registration_intent,
                  "selection_context":copy.deepcopy(context), "proposal":copy.deepcopy(proposal), "nonce":secrets.token_hex(32)}
        intent["intent_sha256"] = fingerprint(intent)
        return intent

    def _inspect_staged_primary(self, con, project, body, digest, record):
        try:
            return self._inspect_staged_primary_checked(con, project, body, digest, record)
        except ResearchError:
            raise
        except (KeyError, TypeError, ValueError, AttributeError, IndexError, OverflowError, RecursionError, OSError):
            raise ResearchError("EVIDENCE_CHANGED", "Original staged primary records are malformed or unavailable.") from None

    def _inspect_staged_primary_checked(self, con, project, body, digest, record):
        """Read only a fully completed original primary; never call Controller dispatch."""
        _check_staged_runtime()
        with project._writer():
            return self._inspect_staged_primary_locked(con, project, body, digest, record)

    def _inspect_staged_primary_locked(self, con, project, body, digest, record):
        from . import project_selection, staged_project_experience as saved, staged_relevance_adapter as staged
        from .research_project import _staged_primary_parent_claim_sha, _staged_primary_child_claim_sha
        from .tabular_quality_feedback import _manager_claim
        state = project.status()
        intent = record.get("intent")
        fields = {"schema_version", "command", "body", "request_sha256", "project_id", "run_id", "source_snapshot_sha256",
                  "project_code_identity", "controller_code_identity", "manager_code_identity", "manager_root",
                  "registration_intent_sha256", "selection_context", "proposal", "nonce", "intent_sha256"}
        _require(type(intent) is dict and set(intent) == fields and intent["schema_version"] == "local-staged-primary-intent-v1"
                 and intent["command"] == "advance_staged_primary" and canonical(intent["body"]) == canonical(body)
                 and intent["request_sha256"] == digest == fingerprint(body)
                 and intent["intent_sha256"] == fingerprint({k:v for k,v in intent.items() if k != "intent_sha256"})
                 and intent["project_id"] == body["project_id"] == state["id"] and intent["run_id"] == state["run_id"]
                 and intent["source_snapshot_sha256"] == state["source_snapshot_sha256"]
                 and intent["project_code_identity"] == state["code_identity"] == project_code_identity()
                 and intent["controller_code_identity"] == project_controller.code_identity()
                 and intent["manager_code_identity"] == batch_code_identity() == _EXPORT_BOOT_IDENTITY
                 and intent["manager_root"] == str(self.root.resolve()) and type(intent["nonce"]) is str
                 and re.fullmatch(r"[a-f0-9]{64}", intent["nonce"]) is not None,
                 "EVIDENCE_CHANGED", "Original staged primary manager intent or identity changed.")
        registration, registration_intent = self._staged_primary_registration_locked(con, project, body["registration_request_id"])
        _require(registration_intent == intent["registration_intent_sha256"] and registration["registration_sha256"] == body["registration_sha256"]
                 and registration["controller_request_id"] == body["request_id"], "EVIDENCE_CHANGED", "Original preregistration changed.")
        parents = [item for item in state.get("controller_requests", []) if item.get("request_id") == body["request_id"]]
        _require(len(parents) == 1, "OPERATION_INCOMPLETE", "Original staged parent is missing; inspect without dispatch.")
        parent = parents[0]
        _require(parent.get("status") == "completed", "EXECUTION_UNKNOWN", "Original staged parent is not completed; inspect without dispatch.")
        meta = parent.get("staged_primary")
        parent_sha = _staged_primary_parent_claim_sha(parent)
        context = intent["selection_context"]
        selected = project_selection.validate_proposal(context, intent["proposal"])
        _require(type(meta) is dict and meta["manager_intent_sha256"] == intent["intent_sha256"]
                 and meta["registration_request_id"] == body["registration_request_id"]
                 and meta["registration_sha256"] == body["registration_sha256"]
                 and meta["plan_sha256"] == registration["plan_sha256"]
                 and canonical(parent["selection_context"]) == canonical(context)
                 and canonical(parent["request"]["proposal"]) == canonical(intent["proposal"])
                 and parent["state_version_before"] == body["expected_state_version"]
                 and selected["candidate"] == registration["candidate"] and selected["evidence_citation_ids"] == []
                 and parent["decision"]["next_action"]["method_id"] == staged.TOOL_ID,
                 "EVIDENCE_CHANGED", "The original staged parent or candidate changed.")
        actions = [item for item in state.get("actions", []) if item.get("request_id") == parent["child_request_id"]]
        _require(len(actions) == 1 and actions[0].get("status") == "completed", "EXECUTION_UNKNOWN", "Original staged child is not completed.")
        child = actions[0]
        saved._action(child, state, staged.TOOL_ID)
        saved._verify_action_rows(project, [child])
        envelope, artifact_sha = saved._read(project, child)
        _require(artifact_sha == hashlib.sha256(canonical(envelope).encode("utf-8")).hexdigest(),
                 "EVIDENCE_CHANGED", "Original staged artifact is not its native canonical bytes.")
        staged._saved(envelope["tool_result"])
        child_view = {k: copy.deepcopy(child[k]) for k in ("id", "request_id", "command", "status", "artifact", "result_sha256", "failure") if k in child}
        _require(parent.get("result") == {"child":child_view,"recovered":False,"reused":False},
                 "EVIDENCE_CHANGED", "Original staged parent and child result differ.")
        with project._connect(readonly=True) as project_con:
            _manager_claim(project_con, "staged_primary_parent", body["request_id"], intent["intent_sha256"], parent_sha)
            _manager_claim(project_con, "staged_primary_child", parent["child_request_id"], intent["intent_sha256"],
                           _staged_primary_child_claim_sha(parent, child["request_sha256"]))
        project._source(state)
        _require(project.status()["snapshot_ref"] == state["snapshot_ref"] and project_code_identity() == intent["project_code_identity"]
                 and project_controller.code_identity() == intent["controller_code_identity"]
                 and batch_code_identity() == intent["manager_code_identity"] == _EXPORT_BOOT_IDENTITY
                 and saved._read(project, child)[1] == artifact_sha,
                 "EVIDENCE_CHANGED", "Original staged source, result or code changed during inspection.")
        saved._verify_action_rows(project, [child])
        with project._connect(readonly=True) as project_con:
            _manager_claim(project_con, "staged_primary_parent", body["request_id"], intent["intent_sha256"], parent_sha)
            _manager_claim(project_con, "staged_primary_child", parent["child_request_id"], intent["intent_sha256"],
                           _staged_primary_child_claim_sha(parent, child["request_sha256"]))
        _check_staged_runtime()
        return ProjectController._response(parent, True)


    def advance_staged_primary(self, body):
        fields = ("request_id", "project_id", "expected_state_version", "registration_request_id", "registration_sha256", "reason")
        digest = _body(body, fields)
        identifier(body["project_id"], "project_id")
        identifier(body["registration_request_id"], "registration_request_id")
        _require(type(body["expected_state_version"]) is int and body["expected_state_version"] >= 0
                 and type(body["registration_sha256"]) is str and re.fullmatch(r"[a-f0-9]{64}", body["registration_sha256"])
                 and _text(body["reason"], 4000), "INVALID_REQUEST", "Use the original registration, project version and bounded reason.")
        _check_staged_runtime()
        with self._writer():
            with self._connect() as con:
                _, project = self._project(con, body["project_id"], active=True)
                old = self._old(con, body, digest)
                self._no_pending_batch(con, body["project_id"], except_id=body["request_id"], evidence=True)
                if old is None:
                    with project._writer():
                        state = project.status()
                        _, registration_intent, context, proposal = self._preflight_staged_primary_locked(con, project, state, body)
                        intent = self._staged_primary_intent(body, digest, state, registration_intent, context, proposal)
                        _check_staged_runtime()
                        self._accept(con, body, digest, "advance_staged_primary", intent)
                        con.commit()
                else:
                    row = con.execute("SELECT command FROM requests WHERE id=?", (body["request_id"],)).fetchone()
                    _require(row is not None and row["command"] == "advance_staged_primary" and type(old) is dict
                             and old.get("status") in ("preparing", "completed") and type(old.get("intent")) is dict
                             and (old["status"] != "preparing" or old.get("result") is None),
                             "OPERATION_INCOMPLETE", "Original staged primary intent is unavailable.")
                    intent = old["intent"]
            if old is None:
                _check_staged_runtime()
                ProjectController(project.root)._advance_staged_primary(
                    request_id=body["request_id"], registration_request_id=body["registration_request_id"],
                    registration_sha256=body["registration_sha256"], expected_state_version=body["expected_state_version"],
                    proposal=intent["proposal"], _manager_intent_sha256=intent["intent_sha256"],
                    _registration_intent_sha256=intent["registration_intent_sha256"])
                record = {"status":"preparing", "intent":intent, "result":None}
            else:
                record = old
            with self._connect() as con:
                result = self._inspect_staged_primary(con, project, body, digest, record)
            response = self._response("advance_staged_primary", body["request_id"], body["project_id"], status="completed", controller=result)
            if old is not None and old["status"] == "completed":
                _require(type(old.get("result")) is dict and canonical({k:v for k,v in old["result"].items() if k != "replayed"})
                         == canonical({k:v for k,v in response.items() if k != "replayed"}),
                         "EVIDENCE_CHANGED", "Original staged primary receipt changed.")
                return dict(response, replayed=True)
            with self._connect() as con:
                self._save(con, body["request_id"], {"status":"completed", "intent":intent, "result":response})
            return dict(response, replayed=old is not None)

    def resume_staged_primary(self, body):
        _body(body, ("request_id", "project_id"))
        _check_staged_runtime()
        with self._writer():
            with self._connect() as con:
                _, project = self._project(con, body["project_id"], active=True)
                self._no_pending_batch(con, body["project_id"], except_id=body["request_id"], evidence=True)
                row = con.execute("SELECT command,digest,record FROM requests WHERE id=?", (body["request_id"],)).fetchone()
                _require(row is not None and row["command"] == "advance_staged_primary", "OPERATION_INCOMPLETE", "Original staged primary intent is absent.")
                record = tabular._parse(row["record"].encode("utf-8"))
                _require(type(record) is dict and record.get("status") in ("preparing", "completed")
                         and type(record.get("intent")) is dict and type(record["intent"].get("body")) is dict
                         and record["intent"]["body"].get("request_id") == body["request_id"]
                         and record["intent"]["body"].get("project_id") == body["project_id"]
                         and (record["status"] != "preparing" or record.get("result") is None),
                         "OPERATION_INCOMPLETE", "Original staged primary body is unavailable.")
                original = record["intent"]["body"]
                _require(_body(original, ("request_id", "project_id", "expected_state_version", "registration_request_id", "registration_sha256", "reason")) == row["digest"],
                         "EVIDENCE_CHANGED", "Original staged primary body changed.")
                result = self._inspect_staged_primary(con, project, original, row["digest"], record)
            response = self._response("advance_staged_primary", body["request_id"], body["project_id"], status="completed", controller=result)
            if record["status"] == "completed":
                _require(type(record.get("result")) is dict and canonical({k:v for k,v in record["result"].items() if k != "replayed"})
                         == canonical({k:v for k,v in response.items() if k != "replayed"}), "EVIDENCE_CHANGED", "Original staged primary receipt changed.")
            else:
                with self._connect() as con:
                    self._save(con, body["request_id"], {"status":"completed", "intent":record["intent"], "result":response})
            return dict(response, replayed=True)

    def _authenticated_staged_primary_locked(self, con, project, registration_id, primary_action_id):
        registration, registration_intent = self._staged_primary_registration_locked(con, project, registration_id)
        row = con.execute("SELECT command,digest,record FROM requests WHERE id=?", (registration["controller_request_id"],)).fetchone()
        _require(row is not None and row["command"] == "advance_staged_primary", "OPERATION_INCOMPLETE", "The original primary manager intent is absent.")
        record = tabular._parse(row["record"].encode("utf-8"))
        _require(type(record) is dict and record.get("status") == "completed" and type(record.get("intent")) is dict
                 and type(record["intent"].get("body")) is dict, "OPERATION_INCOMPLETE", "The original primary is not fully completed.")
        original = record["intent"]["body"]
        _require(_body(original, ("request_id", "project_id", "expected_state_version", "registration_request_id", "registration_sha256", "reason")) == row["digest"]
                 and original["registration_request_id"] == registration_id and original["registration_sha256"] == registration["registration_sha256"],
                 "EVIDENCE_CHANGED", "The original primary request differs from the registration.")
        controller = self._inspect_staged_primary_locked(con, project, original, row["digest"], record)
        child = (controller.get("result") or {}).get("child")
        expected = self._response("advance_staged_primary", original["request_id"], original["project_id"], status="completed", controller=controller)
        _require(type(child) is dict and child.get("id") == primary_action_id and type(record.get("result")) is dict
                 and canonical({k:v for k,v in record["result"].items() if k != "replayed"})
                 == canonical({k:v for k,v in expected.items() if k != "replayed"}),
                 "EVIDENCE_CHANGED", "The original completed primary receipt or action differs.")
        return registration, registration_intent, record["intent"]["intent_sha256"]

    def _preflight_staged_feedback_locked(self, con, project, state, body):
        from . import staged_continuation
        registration, registration_intent, primary_intent = self._authenticated_staged_primary_locked(
            con, project, body["registration_request_id"], body["primary_action_id"])
        _require(registration["registration_sha256"] == body["registration_sha256"] and state["state_version"] == body["expected_state_version"]
                 and state.get("plan_revisions") and fingerprint(state["plan_revisions"][-1]) == registration["plan_sha256"]
                 and project.status()["snapshot_ref"] == state["snapshot_ref"],
                 "EVIDENCE_CHANGED", "Use the original registration, plan and current snapshot.")
        _require(not any(p.get("status") in ("prepared", "running", "unknown") for p in state.get("controller_requests", []))
                 and not any(a.get("status") in ("running", "unknown") for a in state.get("actions", []) + state.get("evidence_actions", []))
                 and not any(item.get("status") in PENDING for item in HostModelSelection(project.root).status()["requests"]),
                 "EXECUTION_UNKNOWN", "Inspect the original unfinished project or Host operation.")
        _require(body["request_id"] != registration["controller_request_id"], "INVALID_REQUEST", "Use a separate feedback request ID.")
        self._quality_unclaimed(project, state, (body["request_id"],))
        context = ProjectController(project.root)._selection_context(state, "next_check")
        frozen = staged_continuation.conditional_policy(state, body["registration_request_id"], body["primary_action_id"], context)
        feedback = frozen["feedback"]
        _require(feedback["outcome"] in ("condition_met", "condition_not_met"), "OPERATION_INCOMPLETE",
                 "This version cannot certify unknown feedback; inspect the original evidence without dispatch.")
        if frozen["decision"] == "audit":
            child = "controller-child-" + fingerprint({"project_id":state["id"], "request_id":body["request_id"]})[:32]
            self._quality_unclaimed(project, state, (child,))
            _require(con.execute("SELECT 1 FROM requests WHERE id=?", (child,)).fetchone() is None,
                     "IDEMPOTENCY_CONFLICT", "The audit child ID is already used by the workbench.")
        _require(project.status()["snapshot_ref"] == state["snapshot_ref"], "STALE_STATE", "Project changed during feedback preflight.")
        return registration_intent, primary_intent, frozen

    def _staged_feedback_intent(self, body, digest, state, registration_intent, primary_intent, frozen):
        intent = {"schema_version":"local-staged-feedback-intent-v1", "command":"advance_staged_feedback", "body":copy.deepcopy(body),
                  "request_sha256":digest, "project_id":state["id"], "run_id":state["run_id"],
                  "source_snapshot_sha256":state["source_snapshot_sha256"], "project_code_identity":state["code_identity"],
                  "controller_code_identity":project_controller.code_identity(), "manager_code_identity":batch_code_identity(),
                  "manager_root":str(self.root.resolve()), "registration_intent_sha256":registration_intent,
                  "primary_manager_intent_sha256":primary_intent, "frozen":copy.deepcopy(frozen), "nonce":secrets.token_hex(32)}
        intent["intent_sha256"] = fingerprint(intent)
        return intent

    def _inspect_staged_feedback(self, con, project, body, digest, record):
        try:
            return self._inspect_staged_feedback_checked(con, project, body, digest, record)
        except ResearchError:
            raise
        except (KeyError, TypeError, ValueError, AttributeError, IndexError, OverflowError, RecursionError, OSError):
            raise ResearchError("EVIDENCE_CHANGED", "Original staged feedback records are malformed or unavailable.") from None

    def _inspect_staged_feedback_checked(self, con, project, body, digest, record):
        with project._writer():
            return self._inspect_staged_feedback_locked(con, project, body, digest, record)

    def _inspect_staged_feedback_locked(self, con, project, body, digest, record):
        """Authenticate the frozen feedback while the caller holds the Project writer."""
        from . import staged_continuation, staged_project_experience as saved, staged_relevance_adapter as staged
        from .research_project import _staged_feedback_parent_claim_sha, _staged_feedback_child_claim_sha
        from .tabular_quality_feedback import _manager_claim
        _check_staged_runtime()
        state = project.status(); intent = record.get("intent")
        fields = {"schema_version","command","body","request_sha256","project_id","run_id","source_snapshot_sha256",
                  "project_code_identity","controller_code_identity","manager_code_identity","manager_root","registration_intent_sha256",
                  "primary_manager_intent_sha256","frozen","nonce","intent_sha256"}
        _require(type(intent) is dict and set(intent) == fields and intent["schema_version"] == "local-staged-feedback-intent-v1"
                 and intent["command"] == "advance_staged_feedback" and canonical(intent["body"]) == canonical(body)
                 and intent["request_sha256"] == digest == fingerprint(body)
                 and intent["intent_sha256"] == fingerprint({k:v for k,v in intent.items() if k != "intent_sha256"})
                 and intent["project_id"] == body["project_id"] == state["id"] and intent["run_id"] == state["run_id"]
                 and intent["source_snapshot_sha256"] == state["source_snapshot_sha256"]
                 and intent["project_code_identity"] == state["code_identity"] == project_code_identity()
                 and intent["controller_code_identity"] == project_controller.code_identity()
                 and intent["manager_code_identity"] == batch_code_identity() == _EXPORT_BOOT_IDENTITY
                 and intent["manager_root"] == str(self.root.resolve()) and type(intent["nonce"]) is str
                 and re.fullmatch(r"[a-f0-9]{64}", intent["nonce"]) is not None,
                 "EVIDENCE_CHANGED", "Original staged feedback intent or producer changed.")
        registration, registration_intent, primary_intent = self._authenticated_staged_primary_locked(con, project, body["registration_request_id"], body["primary_action_id"])
        _require(registration_intent == intent["registration_intent_sha256"] and primary_intent == intent["primary_manager_intent_sha256"]
                 and registration["registration_sha256"] == body["registration_sha256"], "EVIDENCE_CHANGED", "Original primary registration changed.")
        frozen = staged_continuation.verify_conditional_policy(state, body, intent["frozen"])
        parents = [p for p in state.get("controller_requests", []) if p.get("request_id") == body["request_id"]]
        _require(len(parents) == 1, "OPERATION_INCOMPLETE", "Original feedback parent is missing; do not create a replacement.")
        parent = parents[0]; meta = parent.get("staged_feedback_policy"); parent_sha = _staged_feedback_parent_claim_sha(parent)
        primary = next(a for a in state["actions"] if a["id"] == body["primary_action_id"])
        from .project_controller import _compact_decision
        rebuilt = ProjectController(project.root)._selected_plan(state, "next_check", frozen["proposal"], context=frozen["context"])
        expected_request = {"project_id":state["id"], "command":"controller.advance_selection", "need":"next_check",
                            "expected_state_version":body["expected_state_version"], "proposal":frozen["proposal"]}
        _require(meta["manager_intent_sha256"] == intent["intent_sha256"] and meta["primary_manager_intent_sha256"] == primary_intent
                 and meta["registration_request_id"] == body["registration_request_id"] and meta["registration_sha256"] == body["registration_sha256"]
                 and meta["primary_action_id"] == body["primary_action_id"] == frozen["feedback"]["action_id"]
                 and meta["primary_result_sha256"] == primary["result_sha256"] == frozen["feedback"]["result_sha256"]
                 and parent["project_id"] == state["id"] and parent["source_snapshot_sha256"] == state["source_snapshot_sha256"]
                 and parent["code_identity"] == state["code_identity"] and parent["controller_code_identity"] == intent["controller_code_identity"]
                 and meta["decision"] == frozen["decision"] and canonical(parent["request"]) == canonical(expected_request)
                 and canonical(parent["decision"]) == canonical(_compact_decision(rebuilt["decision"]))
                 and canonical(parent["selection_context"]) == canonical(frozen["context"])
                 and canonical(parent["request"]["proposal"]) == canonical(frozen["proposal"])
                 and parent["snapshot_ref_before"] == frozen["context"]["snapshot_ref"]
                 and parent["state_version_before"] == frozen["context"]["state_version"] == body["expected_state_version"]
                 and parent["dispatch_state_version"] == body["expected_state_version"] + 1,
                 "EVIDENCE_CHANGED", "Original feedback policy or context changed.")
        with project._connect(readonly=True) as pc:
            _manager_claim(pc, "staged_feedback_parent", body["request_id"], intent["intent_sha256"], parent_sha)
        if frozen["decision"] == "wait":
            _require(parent.get("status") == "waiting" and parent.get("child_request_id") is None and parent.get("result") is None
                     and frozen["proposal"].get("choice") == {"kind":"wait"}
                     and parent.get("decision", {}).get("next_action", {}).get("kind") == "external_wait",
                     "EVIDENCE_CHANGED", "Original waiting feedback differs.")
            child_id = "controller-child-" + fingerprint({"project_id":state["id"], "request_id":body["request_id"]})[:32]
            self._quality_unclaimed(project, state, (child_id,))
            with project._connect(readonly=True) as pc:
                _require(pc.execute("SELECT 1 FROM quality_manager_claims WHERE kind='staged_feedback_child' AND request_id=?", (child_id,)).fetchone() is None,
                         "EVIDENCE_CHANGED", "Waiting feedback unexpectedly has a child claim.")
        else:
            _require(parent.get("status") == "completed", "EXECUTION_UNKNOWN", "Original audit parent is not completed; inspect without dispatch.")
            _require(parent.get("child_request_id") == "controller-child-" + fingerprint({"project_id":state["id"], "request_id":body["request_id"]})[:32]
                     and type(parent.get("state_version_after")) is int
                     and parent["dispatch_state_version"] < parent["state_version_after"] <= state["state_version"],
                     "EVIDENCE_CHANGED", "Original audit child or terminal state version differs.")
            actions = [a for a in state["actions"] if a.get("request_id") == parent["child_request_id"]]
            _require(len(actions) == 1 and actions[0].get("status") == "completed", "EXECUTION_UNKNOWN", "Original audit child is not completed.")
            child = actions[0]; params = {"based_on_action_id":body["primary_action_id"], "based_on_result_sha256":meta["primary_result_sha256"]}
            saved._action(child, state, staged.AUDIT_TOOL_ID, primary); saved._verify_action_rows(project, [child])
            envelope, raw_sha = saved._read(project, child)
            _require(raw_sha == hashlib.sha256(canonical(envelope).encode("utf-8")).hexdigest(), "EVIDENCE_CHANGED", "Original audit bytes changed.")
            prior, _ = saved._read(project, primary); saved._check_audit(envelope["tool_result"], prior["tool_result"], params)
            child_view = {k:copy.deepcopy(child[k]) for k in ("id","request_id","command","status","artifact","result_sha256","failure") if k in child}
            _require(parent.get("result") == {"child":child_view,"recovered":False,"reused":False}, "EVIDENCE_CHANGED", "Original audit parent and child differ.")
            with project._connect(readonly=True) as pc:
                _manager_claim(pc, "staged_feedback_child", child["request_id"], intent["intent_sha256"], _staged_feedback_child_claim_sha(parent, child["request_sha256"]))
        # The cooperative writer does not freeze raw files or independent SQL
        # fingerprint columns: recheck the entire primary and audit at exit.
        _, final_registration_intent, final_primary_intent = self._authenticated_staged_primary_locked(
            con, project, body["registration_request_id"], body["primary_action_id"])
        _require(final_registration_intent == registration_intent and final_primary_intent == primary_intent,
                 "EVIDENCE_CHANGED", "Original primary ownership changed during inspection.")
        if frozen["decision"] == "audit":
            saved._verify_action_rows(project, [child])
            final_envelope, final_raw_sha = saved._read(project, child)
            _require(final_raw_sha == raw_sha and canonical(final_envelope) == canonical(envelope),
                     "EVIDENCE_CHANGED", "Original audit changed during inspection.")
        _require(project.status()["snapshot_ref"] == state["snapshot_ref"] and project_code_identity() == intent["project_code_identity"]
                 and project_controller.code_identity() == intent["controller_code_identity"] and batch_code_identity() == intent["manager_code_identity"],
                 "EVIDENCE_CHANGED", "Project or producer changed during feedback inspection.")
        with project._connect(readonly=True) as pc:
            _manager_claim(pc, "staged_feedback_parent", body["request_id"], intent["intent_sha256"], parent_sha)
            if frozen["decision"] == "audit":
                _manager_claim(pc, "staged_feedback_child", child["request_id"], intent["intent_sha256"], _staged_feedback_child_claim_sha(parent, child["request_sha256"]))
        _check_staged_runtime()
        return ProjectController._response(parent, True)

    def advance_staged_feedback(self, body):
        fields = ("request_id", "project_id", "expected_state_version", "registration_request_id", "registration_sha256", "primary_action_id")
        digest = _body(body, fields)
        for field in ("project_id", "registration_request_id", "primary_action_id"):
            identifier(body[field], field)
        _require(type(body["expected_state_version"]) is int and body["expected_state_version"] >= 0
                 and type(body["registration_sha256"]) is str and re.fullmatch(r"[a-f0-9]{64}", body["registration_sha256"]),
                 "INVALID_REQUEST", "Use the original registration, primary and project version.")
        _check_staged_runtime()
        with self._writer():
            with self._connect() as con:
                _, project = self._project(con, body["project_id"], active=True)
                old = self._old(con, body, digest)
                self._no_pending_batch(con, body["project_id"], except_id=body["request_id"], evidence=True)
                if old is None:
                    with project._writer():
                        state = project.status()
                        registration_intent, primary_intent, frozen = self._preflight_staged_feedback_locked(con, project, state, body)
                        intent = self._staged_feedback_intent(body, digest, state, registration_intent, primary_intent, frozen)
                        _check_staged_runtime()
                        self._accept(con, body, digest, "advance_staged_feedback", intent)
                        con.commit()
                else:
                    row = con.execute("SELECT command FROM requests WHERE id=?", (body["request_id"],)).fetchone()
                    _require(row is not None and row["command"] == "advance_staged_feedback" and type(old) is dict
                             and old.get("status") in ("preparing", "completed", "waiting") and type(old.get("intent")) is dict
                             and (old["status"] != "preparing" or old.get("result") is None),
                             "OPERATION_INCOMPLETE", "Original staged feedback intent is unavailable.")
                    intent = old["intent"]
            if old is None:
                _check_staged_runtime()
                ProjectController(project.root)._advance_staged_feedback(request_id=body["request_id"],
                    registration_request_id=body["registration_request_id"], registration_sha256=body["registration_sha256"],
                    primary_action_id=body["primary_action_id"], expected_state_version=body["expected_state_version"],
                    frozen=intent["frozen"], _manager_intent_sha256=intent["intent_sha256"],
                    _registration_intent_sha256=intent["registration_intent_sha256"],
                    _primary_manager_intent_sha256=intent["primary_manager_intent_sha256"])
                record = {"status":"preparing", "intent":intent, "result":None}
            else:
                record = old
            with self._connect() as con:
                result = self._inspect_staged_feedback(con, project, body, digest, record)
            response = self._response("advance_staged_feedback", body["request_id"], body["project_id"], status=result["status"], controller=result)
            if old is not None and old["status"] in ("waiting", "completed"):
                _require(type(old.get("result")) is dict and canonical({k:v for k,v in old["result"].items() if k != "replayed"})
                         == canonical({k:v for k,v in response.items() if k != "replayed"}), "EVIDENCE_CHANGED", "Original feedback receipt changed.")
                return dict(response, replayed=True)
            with self._connect() as con:
                self._save(con, body["request_id"], {"status":result["status"], "intent":intent, "result":response})
            return dict(response, replayed=old is not None)

    def resume_staged_feedback(self, body):
        _body(body, ("request_id", "project_id")); _check_staged_runtime()
        with self._writer():
            with self._connect() as con:
                _, project = self._project(con, body["project_id"], active=True)
                self._no_pending_batch(con, body["project_id"], except_id=body["request_id"], evidence=True)
                row = con.execute("SELECT command,digest,record FROM requests WHERE id=?", (body["request_id"],)).fetchone()
                _require(row is not None and row["command"] == "advance_staged_feedback", "OPERATION_INCOMPLETE", "Original feedback manager intent is absent.")
                record = tabular._parse(row["record"].encode("utf-8"))
                _require(type(record) is dict and record.get("status") in ("preparing", "completed", "waiting")
                         and type(record.get("intent")) is dict and type(record["intent"].get("body")) is dict
                         and record["intent"]["body"].get("request_id") == body["request_id"]
                         and record["intent"]["body"].get("project_id") == body["project_id"]
                         and (record["status"] != "preparing" or record.get("result") is None),
                         "OPERATION_INCOMPLETE", "Original feedback body is unavailable.")
                original = record["intent"]["body"]
                _require(_body(original, ("request_id", "project_id", "expected_state_version", "registration_request_id", "registration_sha256", "primary_action_id")) == row["digest"],
                         "EVIDENCE_CHANGED", "Original feedback body changed.")
                result = self._inspect_staged_feedback(con, project, original, row["digest"], record)
            response = self._response("advance_staged_feedback", body["request_id"], body["project_id"], status=result["status"], controller=result)
            if record["status"] in ("waiting", "completed"):
                _require(type(record.get("result")) is dict and canonical({k:v for k,v in record["result"].items() if k != "replayed"})
                         == canonical({k:v for k,v in response.items() if k != "replayed"}), "EVIDENCE_CHANGED", "Original feedback receipt changed.")
            else:
                with self._connect() as con:
                    self._save(con, body["request_id"], {"status":result["status"], "intent":record["intent"], "result":response})
            return dict(response, replayed=True)

    def _staged_plan_reference_locked(self, con, project, feedback_id):
        """Authenticate a completed strict feedback under manager -> Project writers."""
        try:
            return self._staged_plan_reference_locked_checked(con, project, feedback_id)
        except ResearchError:
            raise
        except (KeyError, TypeError, ValueError, AttributeError, IndexError, OverflowError, RecursionError, OSError):
            raise ResearchError("EVIDENCE_CHANGED", "Original staged feedback records are malformed or unavailable.") from None

    def _staged_plan_reference_locked_checked(self, con, project, feedback_id):
        from .research_project import validate_staged_feedback_plan_ref
        identifier(feedback_id, "feedback_request_id")
        row = con.execute("SELECT command,digest,record FROM requests WHERE id=?", (feedback_id,)).fetchone()
        _require(row is not None and row["command"] == "advance_staged_feedback", "OPERATION_INCOMPLETE", "Original strict feedback manager request is unavailable.")
        record = tabular._parse(row["record"].encode("utf-8"))
        _require(type(record) is dict and record.get("status") in ("completed", "waiting") and type(record.get("intent")) is dict
                 and type(record["intent"].get("body")) is dict, "OPERATION_INCOMPLETE", "Original feedback is not a complete manager receipt.")
        body = record["intent"]["body"]
        fields = ("request_id", "project_id", "expected_state_version", "registration_request_id", "registration_sha256", "primary_action_id")
        _require(_body(body, fields) == row["digest"] and body["request_id"] == feedback_id,
                 "EVIDENCE_CHANGED", "Original feedback body changed.")
        controller = self._inspect_staged_feedback_locked(con, project, body, row["digest"], record)
        expected = self._response("advance_staged_feedback", feedback_id, body["project_id"], status=controller["status"], controller=controller)
        _require(type(record.get("result")) is dict and canonical({k:v for k,v in record["result"].items() if k != "replayed"})
                 == canonical({k:v for k,v in expected.items() if k != "replayed"}), "EVIDENCE_CHANGED", "Original feedback receipt changed.")
        state = project.status(); frozen = record["intent"]["frozen"]; reg = frozen["registration"]; item = frozen["feedback"]
        parents = [p for p in state.get("controller_requests", []) if p.get("request_id") == feedback_id]
        _require(len(parents) == 1 and item.get("outcome") in ("condition_met", "condition_not_met"), "EVIDENCE_CHANGED", "A unique known original feedback is required.")
        parent = parents[0]; decision = frozen["decision"]
        child = (parent.get("result") or {}).get("child") if decision == "audit" else None
        _require(decision == "wait" or type(child) is dict, "EVIDENCE_CHANGED", "Original audit result is unavailable.")
        ref = {"schema_version":"staged-feedback-plan-reference-v1", "registration_request_id":reg["request_id"],
               "registration_sha256":reg["registration_sha256"], "original_plan_version":reg["plan_version"],
               "original_plan_sha256":reg["plan_sha256"], "source_snapshot_sha256":state["source_snapshot_sha256"],
               "primary_parent_request_id":reg["controller_request_id"], "primary_action_id":item["action_id"],
               "primary_result_sha256":item["result_sha256"], "feedback_parent_request_id":feedback_id,
               "feedback_parent_request_sha256":parent["request_sha256"], "feedback_intent_sha256":record["intent"]["intent_sha256"],
               "feedback_sha256":fingerprint(item), "feedback_outcome":item["outcome"], "decision":decision,
               "audit_action_id":child["id"] if child else None, "audit_result_sha256":child["result_sha256"] if child else None}
        validate_staged_feedback_plan_ref(ref, code="EVIDENCE_CHANGED")
        dispatch = parent.get("dispatch_state_version")
        finished = dispatch if decision == "wait" else parent.get("state_version_after")
        _require(type(dispatch) is int and type(finished) is int and finished <= state["state_version"]
                 and ((decision == "wait" and parent.get("state_version_after") is None and parent.get("child_request_id") is None)
                      or (decision == "audit" and finished > dispatch)),
                 "EVIDENCE_CHANGED", "Feedback must finish before the successor plan.")
        return ref, finished

    def save_staged_feedback_plan(self, body):
        """Save an explicit successor of authenticated feedback; never dispatch research."""
        from .research_project import _check_plan_experience_refs, validate_plan_experience_refs
        from .tabular_quality_feedback import _manager_claim
        from .retrieval_holdout import FINAL_TOOL_ID
        fields = ("request_id", "project_id", "expected_state_version", "feedback_request_id", "plan", "reason")
        digest = _body(body, fields)
        identifier(body["project_id"], "project_id"); identifier(body["feedback_request_id"], "feedback_request_id")
        limits = {"question":4000, "basis":6000, "steps":12000, "expected_feedback":4000}
        plan = body["plan"]
        _require(type(body["expected_state_version"]) is int and body["expected_state_version"] >= 0
                 and type(plan) is dict and set(limits) <= set(plan) <= set(limits) | {"experience_case_refs"}
                 and _text(body["reason"], 2000) and len(canonical(body).encode("utf-8")) <= MAX_PLAN_RECOVERY_BYTES,
                 "INVALID_REQUEST", "Use one bounded explicit successor plan and current state.")
        for key, limit in limits.items():
            value = plan[key]
            _require(type(value) is str and len(value) <= limit and "\x00" not in value and (key == "basis" or bool(value.strip())),
                     "INVALID_REQUEST", "Research plan text is missing or exceeds its limit.")
        if "experience_case_refs" in plan:
            validate_plan_experience_refs(plan["experience_case_refs"])
        _check_staged_runtime()
        with self._writer():
            with self._connect() as con:
                _, project = self._project(con, body["project_id"], active=True)
                old = self._old(con, body, digest)
                self._no_pending_batch(con, body["project_id"], except_id=body["request_id"], evidence=True)
                if old is not None:
                    row = con.execute("SELECT command FROM requests WHERE id=?", (body["request_id"],)).fetchone()
                    _require(row is not None and row["command"] == "save_staged_feedback_plan" and type(old) is dict
                             and old.get("status") in ("preparing", "completed") and type(old.get("intent")) is dict
                             and (old["status"] != "preparing" or old.get("result") is None),
                             "OPERATION_INCOMPLETE", "The original successor plan intent is unavailable.")
                with project._writer():
                    state = project.status()
                    _require(state.get("private_evaluation") is None and state.get("frozen_evaluation_strategy") is None
                             and not any(a.get("command") == FINAL_TOOL_ID for a in state["actions"]),
                             "CONDITION_NOT_SATISFIED", "Projects with holdout, freeze or final are excluded.")
                    ref, finished_at = self._staged_plan_reference_locked(con, project, body["feedback_request_id"])
                    revisions = state.get("plan_revisions", [])
                    _require(type(revisions) is list and 1 <= ref["original_plan_version"] <= len(revisions)
                             and fingerprint(revisions[ref["original_plan_version"]-1]) == ref["original_plan_sha256"],
                             "EVIDENCE_CHANGED", "Original registered plan changed.")
                    if old is None:
                        _require(len(revisions) == ref["original_plan_version"] and state["state_version"] == body["expected_state_version"]
                                 and finished_at <= body["expected_state_version"], "STALE_STATE", "Use the original plan and current state.")
                        project._require_fresh(state, state, body["expected_state_version"])
                        _require(not any(p.get("status") in ("prepared", "running", "unknown") for p in state.get("controller_requests", []))
                                 and not any(x.get("status") == "reserved" for x in state.get("local_model_requests", []))
                                 and not any(x.get("status") in PENDING for x in HostModelSelection(project.root).status()["requests"]),
                                 "EXECUTION_UNKNOWN", "Inspect unfinished project or Host operations.")
                        self._quality_unclaimed(project, state, (body["request_id"],))
                        _check_plan_experience_refs(project.root, state, {**plan, "based_on_state_version":body["expected_state_version"]}, code="INVALID_REQUEST", pending=True)
                        intent = self._quality_intent(body, digest, "save_staged_feedback_plan", state)
                        intent["schema_version"] = "local-staged-feedback-plan-intent-v1"
                        intent["feedback_ref_sha256"] = fingerprint(ref)
                        intent["intent_sha256"] = fingerprint({k:v for k,v in intent.items() if k != "intent_sha256"})
                        _check_staged_runtime()
                        self._accept(con, body, digest, "save_staged_feedback_plan", intent); con.commit()
                        ref2, _ = self._staged_plan_reference_locked(con, project, body["feedback_request_id"])
                        _require(canonical(ref2) == canonical(ref) and project.status()["snapshot_ref"] == state["snapshot_ref"],
                                 "EVIDENCE_CHANGED", "Feedback or Project changed before saving the plan.")
                        _check_plan_experience_refs(project.root, state, {**plan, "based_on_state_version":body["expected_state_version"]}, code="EVIDENCE_CHANGED", pending=True)
                        _check_staged_runtime()
                        with project._connect() as pc:
                            stored = project._project(pc)
                            _require(stored["state_version"] == body["expected_state_version"], "STALE_STATE", "Project changed before saving the plan.")
                            revision = {"version":len(revisions)+1, **copy.deepcopy(plan), "staged_feedback_ref":ref,
                                        "reason":body["reason"], "request_id":body["request_id"], "based_on_state_version":body["expected_state_version"]}
                            stored.setdefault("plan_revisions", []).append(revision); stored["state_version"] += 1
                            project._save(pc, stored)
                            _manager_claim(pc, "staged_feedback_plan", body["request_id"], intent["intent_sha256"], fingerprint(revision), create=True)
                    else:
                        intent = old["intent"]
                        expected_fields = {"schema_version","command","project_id","run_id","body","request_sha256","source_snapshot_sha256",
                                           "project_code_identity","controller_code_identity","manager_code_identity","manager_root","nonce","intent_sha256","feedback_ref_sha256"}
                        _require(set(intent) == expected_fields and intent["schema_version"] == "local-staged-feedback-plan-intent-v1"
                                 and intent["command"] == "save_staged_feedback_plan" and canonical(intent["body"]) == canonical(body)
                                 and intent["request_sha256"] == digest and intent["intent_sha256"] == fingerprint({k:v for k,v in intent.items() if k != "intent_sha256"})
                                 and intent["project_id"] == state["id"] and intent["run_id"] == state["run_id"] and intent["manager_root"] == str(self.root.resolve())
                                 and intent["source_snapshot_sha256"] == state["source_snapshot_sha256"] and intent["project_code_identity"] == state["code_identity"] == project_code_identity()
                                 and intent["controller_code_identity"] == project_controller.code_identity() and intent["manager_code_identity"] == batch_code_identity() == _EXPORT_BOOT_IDENTITY
                                 and type(intent["nonce"]) is str and re.fullmatch(r"[a-f0-9]{64}", intent["nonce"]) is not None
                                 and intent["feedback_ref_sha256"] == fingerprint(ref), "EVIDENCE_CHANGED", "Original successor intent changed.")
                        found = [p for p in revisions if p.get("request_id") == body["request_id"]]
                        _require(len(found) == 1, "OPERATION_INCOMPLETE", "Original successor plan is absent; do not create it again.")
                        revision = found[0]
                        expected_revision = {"version":ref["original_plan_version"]+1, **copy.deepcopy(plan), "staged_feedback_ref":ref,
                                             "reason":body["reason"], "request_id":body["request_id"], "based_on_state_version":body["expected_state_version"]}
                        _require(canonical(revision) == canonical(expected_revision) and body["expected_state_version"] < state["state_version"]
                                 and finished_at <= body["expected_state_version"], "EVIDENCE_CHANGED", "Original successor revision differs.")
                        _check_plan_experience_refs(project.root, state, revision)
                        with project._connect(readonly=True) as pc:
                            _manager_claim(pc, "staged_feedback_plan", body["request_id"], intent["intent_sha256"], fingerprint(revision))
                        _require(project.status()["snapshot_ref"] == state["snapshot_ref"], "STALE_STATE", "Project changed during verification.")
                    # Re-authenticate both the evidence and the committed Project claim
                    # while the same manager and Project writers remain held.
                    final_state = project.status()
                    final_ref, _ = self._staged_plan_reference_locked(con, project, body["feedback_request_id"])
                    matching = [p for p in final_state.get("plan_revisions", []) if p.get("request_id") == body["request_id"]]
                    _require(canonical(final_ref) == canonical(ref) and len(matching) == 1
                             and canonical(matching[0]) == canonical(revision), "EVIDENCE_CHANGED", "Committed successor or feedback changed.")
                    _check_plan_experience_refs(project.root, final_state, revision)
                    with project._connect(readonly=True) as pc:
                        _manager_claim(pc, "staged_feedback_plan", body["request_id"], intent["intent_sha256"], fingerprint(revision))
                    _require(project.status()["snapshot_ref"] == final_state["snapshot_ref"], "STALE_STATE", "Project changed during successor verification.")
                    _check_staged_runtime()
                    response = self._response("save_staged_feedback_plan", body["request_id"], body["project_id"], status="completed", research_plan=revision)
                    if old is not None and old["status"] == "completed":
                        _require(type(old.get("result")) is dict and canonical({k:v for k,v in old["result"].items() if k != "replayed"})
                                 == canonical({k:v for k,v in response.items() if k != "replayed"}), "EVIDENCE_CHANGED", "Original successor receipt changed.")
                        return dict(response, replayed=True)
                    self._save(con, body["request_id"], {"status":"completed", "intent":intent, "result":response}); con.commit()
                    return dict(response, replayed=old is not None)

    def register_holdout(self, body):
        from .retrieval_holdout import MAX_HOLDOUT_BYTES, _feedback_policy
        if type(body) is dict and "selection_policy" in body:
            _feedback_policy(body["selection_policy"])
            _require(body["selection_policy"]["registration_request_id"] != body.get("request_id"),
                     "INVALID_REQUEST", "Policy and holdout request IDs must differ.")
        fields = ("request_id", "project_id", "expected_state_version", "holdout_base64")
        digest = _body(body, (*fields, "selection_policy") if type(body) is dict and "selection_policy" in body else fields)
        holdout = _decode(body["holdout_base64"], MAX_HOLDOUT_BYTES)
        return self._retrieval_evaluation_command(body, digest, "register_holdout", holdout=holdout)

    def freeze_retrieval_strategy(self, body):
        digest = _body(body, ("request_id", "project_id", "expected_state_version", "primary_action_id"))
        identifier(body["primary_action_id"], "primary_action_id")
        return self._retrieval_evaluation_command(body, digest, "freeze_retrieval_strategy")

    def _retrieval_evaluation_command(self, body, digest, command, *, holdout=None):
        _require(type(body["expected_state_version"]) is int and body["expected_state_version"] >= 0,
                 "INVALID_REQUEST", "An exact saved state version is required.")
        with self._writer():
            with self._connect() as con:
                _, project = self._project(con, body["project_id"], active=True)
                self._no_pending_batch(con, body["project_id"], body["request_id"], evidence=True)
                old = self._old(con, body, digest)
                if old is None:
                    self._accept(con, body, digest, command, {"project_id": body["project_id"], "request_sha256": digest})
                else:
                    row = con.execute("SELECT command FROM requests WHERE id=?", (body["request_id"],)).fetchone()
                    _require(row is not None and row["command"] == command and old.get("status") in {"preparing", "completed"}
                             and old.get("intent") == {"project_id": body["project_id"], "request_sha256": digest},
                             "EVIDENCE_CHANGED", "The original manager request binding changed.")
            if command == "register_holdout":
                options = {"selection_policy": body["selection_policy"]} if "selection_policy" in body else {}
                value = project.register_holdout(request_id=body["request_id"], expected_state_version=body["expected_state_version"], holdout=holdout, **options)
                result_key = "private_evaluation"
            else:
                value = project.freeze_retrieval_strategy(request_id=body["request_id"], expected_state_version=body["expected_state_version"],
                                                          primary_action_id=body["primary_action_id"])
                result_key = "frozen_evaluation_strategy"
            _require(type(value) is dict and value.get("request_id") == body["request_id"],
                     "EVIDENCE_CHANGED", "The original evaluation registration differs from this request.")
            response = self._response(command, body["request_id"], body["project_id"], status="completed",
                                      **{result_key: value})
            if old is not None and old["status"] == "completed":
                _require(old.get("result") == response, "EVIDENCE_CHANGED", "The manager receipt differs from the original registration.")
                return dict(response, replayed=True)
            with self._connect() as con:
                self._save(con, body["request_id"], {"status": "completed", "result": response,
                           "intent": {"project_id": body["project_id"], "request_sha256": digest}})
            return dict(response, replayed=old is not None)

    def record_feedback(self, body):
        digest = _body(body, ("request_id", "project_id", "expected_state_version", "author", "comment", "next_step", "action_id"))
        with self._writer():
            with self._connect() as con:
                _, project = self._project(con, body["project_id"], active=True)
                self._no_pending_batch(con, body["project_id"], evidence=True)
                old = self._old(con, body, digest)
                if old is not None and old["status"] == "completed":
                    return self._completed(old)
                if old is None:
                    self._accept(con, body, digest, "record_feedback", {"project_id": body["project_id"]})
            feedback = project.record_feedback(request_id=body["request_id"], expected_state_version=body["expected_state_version"],
                author=body["author"], comment=body["comment"], next_step=body["next_step"], action_id=body["action_id"])
            response = self._response("record_feedback", body["request_id"], body["project_id"], status="completed",
                                      feedback=feedback, replayed=old is not None)
            with self._connect() as con:
                self._save(con, body["request_id"], {"status": "completed", "result": response,
                                                    "intent": {"project_id": body["project_id"]}})
            return response

    @staticmethod
    def saved_study_reference():
        """Read the fixed standalone reference without selecting a project."""
        return ProjectController.saved_study_reference()

    def project_summary(self):
        """Read a bounded stored projection, without opening a project runtime."""
        from .stored_project_summary import read_stored_project_summary
        return read_stored_project_summary(self.root)

    def experiences(self):
        from .project_experience_binding import view_cases
        view = {"schema_version": "project-experience-view-v1", "project_id": None,
                "state_version": None, "cases": [], "history": []}
        with self._connect(readonly=True) as con:
            active = self._active(con)
            project = self._project(con, active)[1] if active is not None else None
        if project is None:
            return view
        state = project.status()
        view.update(project_id=state["id"], state_version=state["state_version"],
                    cases=view_cases(project.root, state), history=copy.deepcopy(state.get("experience_revisions", [])))
        _require(project.status()["snapshot_ref"] == state["snapshot_ref"],
                 "STALE_STATE", "Project changed while reading its historical method cases.")
        return view

    def import_experience(self, body):
        from .project_experience import MAX_BUNDLE_BYTES
        digest = _body(body, ("request_id", "project_id", "expected_state_version", "bundle_base64", "reason"))
        raw = _decode(body["bundle_base64"], MAX_BUNDLE_BYTES)
        return self._experience_command(body, digest, bundle=raw)

    def set_experience_status(self, body):
        digest = _body(body, ("request_id", "project_id", "expected_state_version", "case_id", "status", "reason"))
        return self._experience_command(body, digest)

    def resume_experience(self, body):
        _body(body, ("request_id", "project_id"))
        with self._connect(readonly=True) as con:
            self._project(con, body["project_id"], active=True)
            row = con.execute("SELECT command,digest,record FROM requests WHERE id=?", (body["request_id"],)).fetchone()
            _require(row is not None and row["command"] in {"import_experience", "set_experience_status"},
                     "ARTIFACT_NOT_FOUND", "Select the original case inclusion request.")
            saved = tabular._parse(row["record"].encode("utf-8"))
            original = saved["intent"]["body"]
            _require(original["project_id"] == body["project_id"] and original["request_id"] == body["request_id"]
                     and fingerprint(original) == row["digest"],
                     "EVIDENCE_CHANGED", "Original case inclusion body changed.")
            command = row["command"]
        return getattr(self, command)(original)

    def _experience_command(self, body, digest, *, bundle=None):
        from .project_experience_binding import import_case, set_status
        command = "import_experience" if bundle is not None else "set_experience_status"
        values = {key: body[key] for key in ("request_id", "expected_state_version", "reason")}
        if bundle is not None:
            values["bundle"] = bundle
        else:
            values.update(case_id=body["case_id"], status=body["status"])
        with self._writer():
            with self._connect() as con:
                _, project = self._project(con, body["project_id"], active=True)
                old = self._old(con, body, digest)
                if old is not None and old["status"] == "completed":
                    revision = getattr(project, command)(**values)
                    _require(revision == old["result"]["experience_revision"],
                             "EVIDENCE_CHANGED", "Saved case inclusion receipt differs from the original project revision.")
                    return self._completed(old)
                if old is None:
                    for row in con.execute("SELECT record FROM requests WHERE command IN ('import_experience','set_experience_status')"):
                        pending = tabular._parse(row[0].encode("utf-8"))
                        _require(pending["status"] == "completed" or pending["intent"].get("project_id") != body["project_id"],
                                 "OPERATION_INCOMPLETE", "Recover the original case inclusion request before starting another.")
                    self._no_pending_batch(con, body["project_id"], evidence=True)
                    validator = import_case if bundle is not None else set_status
                    validator(project, **values, _validate_only=True)
                    self._accept(con, body, digest, command, {"project_id": body["project_id"], "body": copy.deepcopy(body)})
            revision = getattr(project, command)(**values)
            response = self._response(command, body["request_id"], body["project_id"], status="completed",
                                      experience_revision=revision, replayed=old is not None)
            with self._connect() as con:
                self._save(con, body["request_id"], {"status": "completed", "result": response,
                                                    "intent": {"project_id": body["project_id"], "body": copy.deepcopy(body)}})
            return response

    def recipes(self):
        view = {"schema_version": "local-research-recipes-v1", "project_id": None,
                "state_version": None, "context_sha256": None, "recipes": [], "effective_recipe": None}
        with self._connect(readonly=True) as con:
            active = self._active(con)
            project = self._project(con, active)[1] if active is not None else None
        if project is None:
            return view
        context = ProjectController(project.root).selection_context()
        revisions = project.status().get("recipe_revisions", [])
        effective = revisions[-1] if revisions else None
        recipes = [effective["recipe"]] if effective is not None else []
        directory = Path(__file__).resolve().parents[2] / "examples/research-recipes"
        for name in ("tabular-group-first.json", "tabular-source-first.json"):
            recipe = parse_json(reader._read_file(safe_path(directory / name), MAX_RECIPE_BYTES),
                                maximum=MAX_RECIPE_BYTES, code="INVALID_RESEARCH_RECIPE")
            if any((item["id"], item["version"]) == (recipe["id"], recipe["version"]) for item in recipes):
                continue
            recipes.append(recipe)
        for recipe in recipes:
            view["recipes"].append({"recipe": recipe, "decision": compile_recipe(recipe, context)})
        _require(project.status()["snapshot_ref"] == context["snapshot_ref"],
                 "STALE_STATE", "Project changed while previewing recipes.")
        view.update(project_id=context["project_id"], state_version=context["state_version"],
                    context_sha256=context["context_sha256"], effective_recipe=copy.deepcopy(effective))
        return view

    def designs(self):
        return research_design.view(self)

    def bind_design(self, body):
        return research_design.bind(self, body)

    def improve_design(self, body):
        return research_design.improve(self, body)

    def import_design(self, body):
        return research_design.import_resource(self, body)

    def preview_recipe_round(self, body):
        _require(type(body) is dict and set(body) == {"project_id", "input"},
                 "INVALID_REQUEST", "Provide the project and complete saved round input.")
        with self._connect(readonly=True) as con:
            _, project = self._project(con, body["project_id"], active=True)
        before = project.status()
        result = project.preview_recipe_round(body["input"])
        _require(project.status()["snapshot_ref"] == before["snapshot_ref"],
                 "STALE_STATE", "Project changed while verifying the saved round.")
        return {"schema_version": "local-recipe-preview-v1", "project_id": before["id"],
                "state_version": before["state_version"], "result": result}

    def adopt_recipe_round(self, body):
        digest = _body(body, ("request_id", "project_id", "expected_state_version", "input", "reason"))
        with self._writer():
            with self._connect() as con:
                _, project = self._project(con, body["project_id"], active=True)
                self._no_pending_batch(con, body["project_id"], evidence=True)
                old = self._old(con, body, digest)
                if old is not None and old["status"] == "completed":
                    return self._completed(old)
                if old is None:
                    self._accept(con, body, digest, "adopt_recipe_round", {"project_id": body["project_id"]})
            revision = project.apply_recipe_round(request_id=body["request_id"],
                expected_state_version=body["expected_state_version"], round_input=body["input"], reason=body["reason"])
            response = self._response("recipe-adopt", body["request_id"], body["project_id"],
                                      status="completed", recipe_revision=revision, replayed=old is not None)
            with self._connect() as con:
                self._save(con, body["request_id"], {"status": "completed", "result": response,
                                                    "intent": {"project_id": body["project_id"]}})
            return response

    def advance_recipe(self, body):
        digest = _body(body, ("request_id", "project_id", "expected_state_version", "recipe"))
        _require(type(body["expected_state_version"]) is int and body["expected_state_version"] >= 0,
                 "INVALID_REQUEST", "An exact saved state version is required.")
        return self._advance_receipt(body, digest, "advance_recipe", evidence=True)

    def model_view(self, *, enabled=False):
        with self._connect(readonly=True) as con:
            active = self._active(con)
            project = self._project(con, active)[1] if active is not None else None
        view = {"schema_version": "local-host-model-view-v1", "enabled": enabled,
                "project_id": active, "journal": None, "records": [], "recipe_validations": [], "platform_runs": [], "plan_reviews": []}
        if project is not None:
            journal = HostModelSelection(project.root)
            view["journal"] = journal.status()
            view["records"] = [journal.status(request_id=item["request_id"]) for item in view["journal"]["requests"]]
            identities = []
            for record in view["records"]:
                context = record.get("context")
                materials = context.get("supplied_materials") if type(context) is dict else None
                quality = [m for m in materials if type(m) is dict and m.get("kind") == "tabular_quality_feedback"] if type(materials) is list else []
                if not quality:
                    continue
                identity = {"host_request_id": record.get("request_id"), "status": "unavailable"}
                try:
                    response_sha = record.get("response_sha256")
                    ids = [m.get("registration_request_id") for m in quality]
                    valid = (type(record.get("request_id")) is str and len(quality) <= 4
                             and all(type(i) is str and re.fullmatch(r"[A-Za-z0-9_.:-]{1,80}", i) for i in ids)
                             and len(set(ids)) == len(ids)
                             and all(type(m.get("registration_sha256")) is str
                                     and re.fullmatch(r"[0-9a-f]{64}", m["registration_sha256"]) for m in quality)
                             and type(response_sha) is str and re.fullmatch(r"[0-9a-f]{64}", response_sha))
                    if valid:
                        identity.update(status="available", context_sha256=fingerprint(context), response_sha256=response_sha,
                                        materials=[{"registration_request_id":m["registration_request_id"],
                                                    "registration_sha256":m["registration_sha256"],
                                                    "material_sha256":fingerprint(m)} for m in quality])
                except (TypeError, ValueError, RecursionError):
                    pass
                identities.append(identity)
            if identities:
                # Snapshot hashes of exactly the records returned above; this GET
                # does not authenticate the saved Host files or original producer.
                view["quality_fact_identities"] = identities
            # Snapshot identity only; adoption's POST is responsible for verifying
            # original files, ownership and the manager/Host/Project binding.
            adopted = [record for record in view["records"] if record.get("status") == "applied"
                       and record.get("quality_adoption", {}).get("schema_version") == "host-quality-adoption-v4"]
            if adopted:
                state = project.status()
                receipts = []
                for record in adopted:
                    plan = record.get("outcome", {}).get("research_plan")
                    binding = record.get("quality_adoption", {}).get("manager_binding", {})
                    revisions = [r for r in state.get("plan_revisions", []) if r.get("request_id") == record.get("request_id")]
                    if (type(plan) is dict and len(revisions) == 1 and revisions[0] == plan
                            and type(binding.get("request_id")) is str):
                        receipts.append({"host_request_id":record["request_id"], "request_id":binding["request_id"],
                                         "plan_version":plan["version"], "plan_sha256":fingerprint(plan)})
                _require(project.status()["snapshot_ref"] == state["snapshot_ref"], "STALE_STATE", "Project changed while reading adoption identity.")
                view["quality_adoption_receipts"] = {"project_id":state["id"], "snapshot_ref":state["snapshot_ref"], "items":receipts}
            view["plan_reviews"] = review_plan_requests(view["records"])
            view["recipe_validations"] = [read_recipe_validation(project.root, record["request_id"])
                                          for record in view["records"] if record.get("purpose") == "recipe"]
            with self._connect(readonly=True) as con:
                for row in con.execute("SELECT record FROM requests WHERE command='import' ORDER BY rowid"):
                    imported = tabular._parse(row[0].encode("utf-8"))
                    if (imported["status"] == "completed" and imported["result"]["project_id"] == active
                            and imported["intent"]["platform_run"] is not None):
                        view["platform_runs"].append(copy.deepcopy(imported["intent"]["platform_run"]))
        return view

    def check_plan_fact(self, body):
        from .host_model_report import capture_host_models
        from .plan_fact_check import check_plan_fact, check_quality_plan_fact
        _require(type(body) is dict and set(body) == {"project_id", "host_request_id", "claim"},
                 "INVALID_REQUEST", "Provide the project, original Host request and selected assertion.")
        identifier(body["host_request_id"], "host_request_id")
        with self._connect(readonly=True) as con:
            _, project = self._project(con, body["project_id"], active=True)
        captured = capture_host_models(project.root)
        record = next((item for item in captured["records"] if item["request_id"] == body["host_request_id"]), None)
        _require(record is not None, "ARTIFACT_NOT_FOUND", "No original Host request matches this ID.")
        if type(body["claim"]) is dict and "quality" in body["claim"]:
            folder = record.get("directory")
            response = record.get("response_file")
            _require(type(folder) is str and type(response) is str
                     and record.get("status") in ("proposed", "applied", "rejected")
                     and type(record.get("context")) is dict and type(record.get("prompt")) is dict
                     and type(record.get("proposal")) is dict and type(record.get("arguments")) is dict
                     and type(record["context"].get("selection_context")) is dict
                     and record["context"].get("selection_context", {}).get("project_id") == body["project_id"],
                     "EVIDENCE_CHANGED", "The original parsed plan and its project identity are required.")
            names = {item["name"] for item in captured["assets"]}
            needed = {"host-model-evidence/" + folder + "/" + suffix
                      for suffix in ("context.json", "prompt.json", "proposal.json")}
            needed.add("host-model-evidence/" + response)
            _require(needed <= names, "EVIDENCE_CHANGED", "The original Host context, prompt, proposal and response files are required.")
            return check_quality_plan_fact(record, body["claim"])
        return check_plan_fact(record, body["claim"])

    def model_advance(self, body, *, executable):
        _body(body, ("request_id", "project_id", "expected_state_version", "decision_limit", "cli_budget_usd", "reason"))
        return self._model_command(body, executable=executable, resume=False)

    def model_plan_advance(self, body, *, executable):
        fields = ("request_id", "project_id", "expected_state_version", "decision_limit", "cli_budget_usd", "reason")
        _body(body, (*fields, "saved_materials") if type(body) is dict and "saved_materials" in body else fields)
        return self._model_command(body, executable=executable, resume=False, purpose="plan")

    def prepare_manual_quality_plan(self, body):
        """Explicitly prepare a direct delegated Host plan; never launch a model."""
        fields = ("request_id", "project_id", "expected_state_version", "expected_snapshot_ref", "decision_limit", "cli_budget_usd", "reason", "saved_materials")
        _body(body, fields)
        _require(body["request_id"].startswith("local-manual-plan-") and type(body["saved_materials"]) is list
                 and any(type(item) is dict and item.get("kind") == "tabular_quality_feedback" for item in body["saved_materials"]),
                 "INVALID_REQUEST", "Choose an explicit quality material and a direct manual Host ID.")
        _require(type(body["expected_snapshot_ref"]) is str and re.fullmatch(r"[a-f0-9]{64}", body["expected_snapshot_ref"]) is not None,
                 "INVALID_REQUEST", "Bind the original project snapshot.")
        with self._writer():
            with self._connect(readonly=True) as con:
                _, project = self._project(con, body["project_id"], active=True)
                self._no_pending_batch(con, body["project_id"], evidence=True)
                _require(not self._linked_continuation_plan(con, body["project_id"], body["request_id"]),
                         "OPERATION_INCOMPLETE", "A continuation owns this Host request.")
            before = project.status()
            _require(before["snapshot_ref"] == body["expected_snapshot_ref"] and before["state_version"] == body["expected_state_version"],
                     "STALE_STATE", "The previewed project state changed.")
            journal = HostModelSelection(project.root)
            record = journal.prepare(request_id=body["request_id"], provider="delegated", purpose="plan",
                expected_state_version=body["expected_state_version"], decision_limit=body["decision_limit"],
                cli_budget_usd=body["cli_budget_usd"], reason=body["reason"], saved_materials=body["saved_materials"], require_new=True)
            _require(record["context"]["selection_context"]["snapshot_ref"] == body["expected_snapshot_ref"]
                     and project.status()["snapshot_ref"] == body["expected_snapshot_ref"],
                     "STALE_STATE", "The project changed during the original preparation; retain this Host ID.")
            return self._response("prepare-manual-quality-plan", body["request_id"], body["project_id"],
                                  status=record["status"], model_record=record, usage=journal.status())

    def import_manual_quality_plan(self, body):
        """Import exact operator bytes to an existing direct Host plan, then parse only that plan."""
        from .host_selection_protocol import MAX_RESPONSE_BYTES
        _body(body, ("request_id", "project_id", "response_base64"))
        _require(body["request_id"].startswith("local-manual-plan-"), "INVALID_REQUEST", "Select a direct manual Host request.")
        raw = _decode(body["response_base64"], MAX_RESPONSE_BYTES)
        with self._writer():
            with self._connect(readonly=True) as con:
                _, project = self._project(con, body["project_id"], active=True)
                self._no_pending_batch(con, body["project_id"], evidence=True)
                _require(not self._linked_continuation_plan(con, body["project_id"], body["request_id"]),
                         "OPERATION_INCOMPLETE", "A continuation owns this Host request.")
            journal = HostModelSelection(project.root)
            record = journal.status(request_id=body["request_id"])
            spec = record.get("prepare_specification", {})
            _require(record.get("provider") == "delegated" and record.get("purpose") == "plan"
                     and record.get("controller_request_id") == body["request_id"]
                     and record.get("context", {}).get("selection_context", {}).get("project_id") == body["project_id"]
                     and any(type(item) is dict and item.get("kind") == "tabular_quality_feedback" for item in spec.get("saved_materials", [])),
                     "INVALID_REQUEST", "Only the original direct delegated quality plan may receive these bytes.")
            _require(record.get("status") in ("prepared", "received", "proposed"), "OPERATION_INCOMPLETE", "Inspect the original Host status before importing.")
            with tempfile.TemporaryDirectory(dir=self.root, prefix="manual-plan-response-") as directory:
                path = Path(directory) / "response.bin"
                write_bytes_once(path, raw)
                record = journal.import_response(request_id=body["request_id"], response_file=path, strict_manual_plan=True)
            if record["status"] == "received":
                record = journal.consume(request_id=body["request_id"], strict_manual_plan=True)
            return self._response("import-manual-quality-plan", body["request_id"], body["project_id"],
                                  status=record["status"], model_record=record, usage=journal.status())

    def model_plan_adopt(self, body):
        _body(body, ("request_id", "project_id"))
        return self._plan_decision(body, reject=False)

    def model_quality_plan_adopt(self, body):
        """Adopt one original Host proposal with a manager-bound quality intent."""
        return self._model_quality_plan_adopt(body, supplied_quality=False)

    def model_supplied_quality_plan_adopt(self, body):
        """Adopt only the exact quality material sealed into the original Host prompt."""
        return self._model_quality_plan_adopt(body, supplied_quality=True)

    def resume_supplied_quality_plan_adopt(self, body):
        """Reconcile only an already accepted original manager intent."""
        return self._model_quality_plan_adopt(body, supplied_quality=True, resume_only=True)

    def _model_quality_plan_adopt(self, body, *, supplied_quality, resume_only=False):
        command = "model_supplied_quality_plan_adopt" if supplied_quality else "model_quality_plan_adopt"
        digest = _body(body, ("request_id", "project_id", "expected_state_version", "host_request_id", "registration_request_id"))
        for name in ("request_id", "project_id", "host_request_id", "registration_request_id"):
            identifier(body[name], name)
        _require(body["request_id"] != body["host_request_id"]
                 and type(body["expected_state_version"]) is int and body["expected_state_version"] >= 0,
                 "INVALID_REQUEST", "Use distinct manager and original Host IDs and an exact state version.")
        with self._writer():
            with self._connect() as con:
                _, project = self._project(con, body["project_id"], active=True)
                old = self._old(con, body, digest)
                _require(not resume_only or old is not None, "OPERATION_INCOMPLETE",
                         "The original manager intent is unavailable; no replacement request was accepted.")
                self._no_pending_batch(con, body["project_id"], except_id=body["request_id"], evidence=True)
                host = HostModelSelection(project.root)
                if old is None:
                    with host._writer():
                        with project._writer():
                            state = project.status()
                            with project._connect(readonly=True) as core:
                                project._require_fresh(project._project(core), state, body["expected_state_version"])
                            _require(batch_code_identity() == _EXPORT_BOOT_IDENTITY
                                     and state["code_identity"] == project_code_identity(),
                                     "CODE_CHANGED", "Use the original manager and Project source identities.")
                            host_state = host._load()
                            _require(not any(item["status"] in PENDING for item in host_state["requests"].values()),
                                     "HOST_SELECTION_PENDING", "Resolve the original Host request first.")
                            record = host._record(host_state, body["host_request_id"])
                            preflight = (host._preflight_manager_supplied_quality_adoption if supplied_quality
                                         else host._preflight_manager_quality_adoption)
                            evidence = preflight(record, body["registration_request_id"], body["expected_state_version"])
                            ref = evidence[0] if supplied_quality else evidence
                            self._quality_unclaimed(project, state, (body["request_id"], body["host_request_id"]))
                            _require(preflight(record, body["registration_request_id"], body["expected_state_version"]) == evidence
                                     and project.status()["snapshot_ref"] == state["snapshot_ref"]
                                     and batch_code_identity() == _EXPORT_BOOT_IDENTITY,
                                     "STALE_STATE", "Host or quality evidence changed before manager acceptance.")
                            intent = {"schema_version":"local-host-supplied-quality-intent-v1" if supplied_quality else "local-host-quality-intent-v1", "command":command,
                                      "project_id":state["id"], "run_id":state["run_id"], "body":copy.deepcopy(body),
                                      "request_sha256":digest, "source_snapshot_sha256":state["source_snapshot_sha256"],
                                      "project_code_identity":state["code_identity"], "controller_code_identity":project_controller.code_identity(),
                                      "manager_code_identity":batch_code_identity(), "manager_root":str(self.root.resolve()),
                                      "nonce":secrets.token_hex(32), "host_context_sha256":fingerprint(record["context"]),
                                      "host_prompt_sha256":fingerprint(record["prompt"]), "host_proposal_sha256":fingerprint(record["proposal"]),
                                      "host_response_sha256":record["response_sha256"], "quality_ref_sha256":fingerprint(ref)}
                            if supplied_quality:
                                intent.update(prepare_specification_sha256=evidence[1], supplied_quality_material_sha256=evidence[2])
                            intent["intent_sha256"] = fingerprint(intent)
                            self._accept(con, body, digest, command, intent)
                            con.commit()
                else:
                    row = con.execute("select command from requests where id=?", (body["request_id"],)).fetchone()
                    _require(row is not None and row["command"] == command
                             and old.get("status") in ("preparing", "completed") and type(old.get("intent")) is dict,
                             "OPERATION_INCOMPLETE", "The original manager intent is unavailable.")
                    intent = old["intent"]
                    _require(type(intent.get("intent_sha256")) is str
                             and re.fullmatch(r"[a-f0-9]{64}", intent["intent_sha256"]) is not None,
                             "EVIDENCE_CHANGED", "The original manager intent identity is malformed.")
            binding = {"manager_root":str(self.root.resolve()), "request_id":body["request_id"], "intent_sha256":intent["intent_sha256"]}
            if old is not None:
                original = host.status(request_id=body["host_request_id"])
                _require(original.get("status") == "applied" and type(original.get("quality_adoption")) is dict
                         and original["quality_adoption"].get("manager_binding") == binding
                         and original["quality_adoption"].get("schema_version") == ("host-quality-adoption-v4" if supplied_quality else "host-quality-adoption-v2"),
                         "OPERATION_INCOMPLETE", "The original Host adoption is not terminal and manager-bound.")
            if supplied_quality:
                adopted = host._adopt_manager_supplied_quality_plan(request_id=body["host_request_id"],
                            registration_request_id=body["registration_request_id"], manager_binding=binding)
            else:
                adopted = host.adopt_quality_plan(request_id=body["host_request_id"],
                            registration_request_id=body["registration_request_id"], _manager_binding=binding)
            revision = adopted["outcome"]["research_plan"]
            _require(adopted["status"] == "applied" and revision["request_id"] == body["host_request_id"],
                     "EVIDENCE_CHANGED", "The original Host plan identity changed.")
            response = self._response(command, body["request_id"], body["project_id"],
                                      status="applied", host_request_id=body["host_request_id"],
                                      plan_version=revision["version"], plan_sha256=fingerprint(revision))
            if old is not None and old["status"] == "completed":
                _require(type(old.get("result")) is dict and {k:v for k,v in old["result"].items() if k != "replayed"}
                         == {k:v for k,v in response.items() if k != "replayed"},
                         "EVIDENCE_CHANGED", "The original manager receipt changed.")
                return dict(response, replayed=True)
            with self._connect() as con:
                self._save(con, body["request_id"], {"status":"completed", "intent":intent, "result":response})
            return dict(response, replayed=old is not None)

    def model_plan_reject(self, body):
        _body(body, ("request_id", "project_id", "reason"))
        return self._plan_decision(body, reject=True)

    def _plan_decision(self, body, *, reject):
        with self._writer():
            with self._connect(readonly=True) as con:
                _, project = self._project(con, body["project_id"], active=True)
                self._no_pending_batch(con, body["project_id"], evidence=True, plan_request_id=body["request_id"])
            journal = HostModelSelection(project.root)
            record = (journal.reject_plan(request_id=body["request_id"], reason=body["reason"]) if reject
                      else journal.adopt_plan(request_id=body["request_id"]))
            return self._response("model-plan-reject" if reject else "model-plan-adopt", body["request_id"], body["project_id"],
                                  status=record["status"], model_record=record, usage=journal.status())

    def model_resume(self, body, *, executable):
        _body(body, ("request_id", "project_id"))
        return self._model_command(body, executable=executable, resume=True)

    def _model_command(self, body, *, executable, resume, purpose="selection"):
        with self._writer():
            with self._connect(readonly=True) as con:
                _, project = self._project(con, body["project_id"], active=True)
                linked = self._linked_continuation_plan(con, body["project_id"], body["request_id"]) if resume else False
                self._no_pending_batch(con, body["project_id"], evidence=True,
                                       plan_request_id=body["request_id"] if resume else None)
            journal = HostModelSelection(project.root)
            if resume and linked:
                record = journal.status(request_id=body["request_id"])
                if record["provider"] == "delegated":
                    _require(record.get("purpose") == "plan", "INVALID_REQUEST", "Resume the linked plan request only.")
                    if record["status"] == "received":
                        record = journal.consume(request_id=body["request_id"])
                    return self._response("model-resume", body["request_id"], body["project_id"],
                                          status=record["status"], model_record=record, usage=journal.status())
            _require(executable is not None and Path(executable).is_file(), "MODEL_DISABLED", "No host-selected CLI is enabled.")
            executable = str(Path(executable).absolute())
            if resume:
                record = journal.status(request_id=body["request_id"])
                _require(record["provider"] == "claude_cli"
                         and record["prepare_specification"]["executable"] == executable,
                         "CONFIG_CHANGED", "Resume requires the original host-selected CLI.")
            else:
                materials = {"saved_materials": body["saved_materials"]} if purpose == "plan" and "saved_materials" in body else {}
                record = journal.prepare(request_id=body["request_id"], provider="claude_cli", executable=executable,
                    expected_state_version=body["expected_state_version"], decision_limit=body["decision_limit"],
                    cli_budget_usd=body["cli_budget_usd"], reason=body["reason"], purpose=purpose, **materials)
            record = journal.request(request_id=body["request_id"])
            if record["status"] == "received":
                record = journal.consume(request_id=body["request_id"])
            command = "model-resume" if resume else "model-plan-advance" if purpose == "plan" else "model-advance"
            return self._response(command, body["request_id"], body["project_id"],
                                  status=record["status"], model_record=record, usage=journal.status())

    @staticmethod
    def _linked_continuation_plan(con, project_id, request_id):
        for row in con.execute("SELECT record FROM requests WHERE command='continue'"):
            record = tabular._parse(row["record"].encode("utf-8"))
            view = record.get("result") or {}
            if (record["status"] != "completed" and view.get("project_id") == project_id
                    and view.get("phase") in {"plan", "awaiting_adoption"}
                    and (view.get("plan_ref") or {}).get("kind") == "host_plan"
                    and view["plan_ref"]["request_id"] == request_id):
                return True
        return False

    @staticmethod
    def _no_staged_switch(con, project_id):
        if project_id is None:
            return
        for row in con.execute("SELECT command,record FROM requests WHERE command IN ('save_staged_feedback_plan','advance_staged_feedback','advance_staged_primary','register_staged_hypothesis','register_tabular_quality_conditions','advance_tabular_quality_feedback','save_quality_plan','advance_tabular_quality_feedback_v2','model_quality_plan_adopt','model_supplied_quality_plan_adopt')"):
            record = tabular._parse(row["record"].encode("utf-8"))
            terminal = ({"completed", "waiting"} if row["command"] == "advance_staged_feedback" else {"completed"} if row["command"] in ("save_staged_feedback_plan", "advance_staged_primary", "register_staged_hypothesis", "register_tabular_quality_conditions", "save_quality_plan", "model_quality_plan_adopt", "model_supplied_quality_plan_adopt") else {"completed", "failed", "waiting", "needs_review", "rejected"})
            _require(record.get("status") in terminal or record.get("intent", {}).get("project_id") != project_id,
                     "OPERATION_INCOMPLETE", "Reconcile the original unfinished quality request before switching projects.")
        for row in con.execute("SELECT record FROM requests WHERE command='continue_staged'"):
            record = tabular._parse(row["record"].encode("utf-8"))
            _require(record.get("status") == "completed" or record.get("intent", {}).get("project_id") != project_id,
                     "OPERATION_INCOMPLETE", "Reconcile the original staged continuation before switching projects.")

    @staticmethod
    def _no_pending_batch(con, project_id, except_id=None, *, evidence=False, plan_request_id=None):
        quality_commands = ("save_staged_feedback_plan", "advance_staged_feedback", "advance_staged_primary", "register_staged_hypothesis", "register_tabular_quality_conditions", "advance_tabular_quality_feedback", "save_quality_plan", "advance_tabular_quality_feedback_v2", "model_quality_plan_adopt", "model_supplied_quality_plan_adopt")
        commands = (("batch", "evidence", "continue", "register_holdout", "freeze_retrieval_strategy", "continue_staged", "save_plan") if evidence else ("batch", "continue", "register_holdout", "freeze_retrieval_strategy", "continue_staged", "save_plan")) + quality_commands
        rows = list(con.execute("SELECT id,command,record FROM requests WHERE command IN ('batch','evidence','continue','register_holdout','freeze_retrieval_strategy','continue_staged','save_plan','save_staged_feedback_plan','advance_staged_feedback','advance_staged_primary','register_staged_hypothesis','register_tabular_quality_conditions','advance_tabular_quality_feedback','save_quality_plan','advance_tabular_quality_feedback_v2','model_quality_plan_adopt','model_supplied_quality_plan_adopt')"))
        owned = set()
        for row in rows:
            if row["command"] != "continue":
                continue
            record = tabular._parse(row["record"].encode("utf-8"))
            view = record.get("result") or {}
            child_id = (view.get("batch_ref") or {}).get("request_id")
            if row["id"] == except_id and child_id:
                owned.add(child_id)
            if except_id is not None and child_id == except_id and view.get("project_id") == project_id:
                owned.add(row["id"])
            if (plan_request_id and view.get("phase") in {"plan", "awaiting_adoption"}
                    and (view.get("plan_ref") or {}).get("kind") == "host_plan"
                    and view["plan_ref"]["request_id"] == plan_request_id):
                owned.add(row["id"])
            if (plan_request_id and view.get("phase") == "actions"
                    and (view.get("batch_ref") or {}).get("kind") == "delegated"
                    and view["batch_ref"].get("plan_request_id") == plan_request_id):
                owned.add(row["id"])
        for row in rows:
            if row["id"] == except_id or row["id"] in owned or row["command"] not in commands:
                continue
            record = tabular._parse(row["record"].encode("utf-8"))
            terminal = ({"completed", "waiting"} if row["command"] == "advance_staged_feedback" else
                        {"completed", "failed", "waiting", "needs_review", "rejected"}
                        if row["command"] in ("advance_tabular_quality_feedback", "advance_tabular_quality_feedback_v2") else {"completed"})
            _require(record["status"] in terminal or record["intent"].get("project_id") != project_id,
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
        if step.get("recipe_decision") is not None:
            request.update(command="controller.advance_recipe", proposal=step["recipe_decision"]["proposal"],
                           recipe_decision=step["recipe_decision"])
        _require(parent["request"] == request and parent["request_sha256"] == fingerprint(request)
                 and parent["project_id"] == record["body"]["project_id"] == state["id"]
                 and parent["snapshot_ref_before"] == step["snapshot_ref_before"]
                 and parent["state_version_before"] == step["expected_state_version"]
                 and parent["decision"] == step["decision"] and parent["decision_sha256"] == step["decision_sha256"]
                 and parent["code_identity"] == record["intent"]["project_code_identity"]
                 and parent["controller_code_identity"] == record["intent"]["controller_code_identity"]
                 and parent["source_snapshot_sha256"] == record["intent"]["source_snapshot_sha256"]
                 and parent.get("effective_recipe_revision") == step.get("effective_recipe_revision")
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
                 and type(body["allowed_methods"]) is list and bool(body["allowed_methods"])
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
                    if plan.get("recipe_decision") is not None:
                        compiled = plan["recipe_decision"]
                        decision["policy_ref"] = {"id": compiled["recipe_id"], "version": compiled["recipe_version"], "kind": "deterministic_recipe"}
                    ordinal = len(record["steps"]) + 1
                    record["steps"].append({"ordinal": ordinal, "request_id": "local-batch-" + digest[:32] + "-step" + str(ordinal),
                        "expected_state_version": plan["state_version"], "need": "next_check", "snapshot_ref_before": plan["snapshot_ref"],
                        "decision": decision, "decision_sha256": fingerprint(decision), "method_id": method, "parameters": copy.deepcopy(parameters),
                        "status": "prepared", "child_request_id": None, "parent": None, "response": None})
                    if plan.get("recipe_decision") is not None:
                        record["steps"][-1].update(recipe_decision=copy.deepcopy(plan["recipe_decision"]),
                                                   effective_recipe_revision=plan["decision"]["policy_ref"]["revision"])
                    self._save_batch(record)
            except Exception as error:
                return self._finish_batch(record, project.status(), "needs_review", getattr(error, "code", "BATCH_INTERRUPTED"),
                    "The batch stopped with its original intent retained; explicitly reconcile this same request ID.", incomplete=True, replayed=old is not None)

    @staticmethod
    def _check_continuation(record, digest):
        view = record.get("result") or {}
        _require(view.get("schema_version") == "local-research-continuation-v1"
                 and record.get("status") in {"incomplete", "completed"}
                 and view.get("record_status") == record["status"]
                 and fingerprint(view.get("body")) == digest == record["intent"]["request_sha256"]
                 and view.get("request_id") == view["body"]["request_id"]
                 and view.get("project_id") == view["body"]["project_id"] == record["intent"]["project_id"],
                 "EVIDENCE_CHANGED", "Saved continuation differs from its original request.")

    def continuation_record(self, request_id):
        identifier(request_id)
        with self._connect(readonly=True) as con:
            row = con.execute("SELECT digest,record FROM requests WHERE id=? AND command='continue'", (request_id,)).fetchone()
            _require(row is not None, "ARTIFACT_NOT_FOUND", "No saved research continuation matches this request ID.")
            record = tabular._parse(row["record"].encode("utf-8"))
            self._check_continuation(record, row["digest"])
            self._project(con, record["intent"]["project_id"])
        return copy.deepcopy(record["result"])

    def delegated_response(self, body):
        """Import only the original bytes for a Host request owned by this continuation."""
        from .host_selection_protocol import MAX_RESPONSE_BYTES
        _body(body, ("request_id", "project_id", "host_request_id", "response_base64"))
        identifier(body["host_request_id"], "host_request_id")
        raw = _decode(body["response_base64"], MAX_RESPONSE_BYTES)
        with self._writer():
            with self._connect(readonly=True) as con:
                _, project = self._project(con, body["project_id"], active=True)
                row = con.execute("SELECT digest,record FROM requests WHERE id=? AND command='continue'", (body["request_id"],)).fetchone()
                _require(row is not None, "ARTIFACT_NOT_FOUND", "No original continuation matches this ID.")
                record = tabular._parse(row["record"].encode("utf-8"))
                self._check_continuation(record, row["digest"])
                intent, view = record["intent"], record["result"]
                _require(intent["project_id"] == body["project_id"] and view["body"]["execution_mode"] == "delegated",
                         "INVALID_REQUEST", "The original continuation must own this delegated request.")
                self._no_pending_batch(con, body["project_id"], body["request_id"], evidence=True)
            state = project.status()
            _require(state["run_id"] == intent["run_id"] and state["source_snapshot_sha256"] == intent["source_snapshot_sha256"]
                     and state["code_identity"] == intent["project_code_identity"]
                     and batch_code_identity() == intent["batch_code_identity"]
                     and project_controller.code_identity() == intent["controller_code_identity"],
                     "EVIDENCE_CHANGED", "The original project or continuation implementation changed.")
            journal = HostModelSelection(project.root)
            host_id = body["host_request_id"]
            spec = intent.get("plan_specification")
            if spec is not None and spec["request_id"] == host_id:
                _require(spec["provider"] == "delegated", "EVIDENCE_CHANGED", "The original plan used a different provider.")
                step = None
            else:
                batch_body = intent.get("batch_body")
                _require(batch_body is not None, "ARTIFACT_NOT_FOUND", "No original delegated batch is prepared.")
                saved = HostModelBatch(project.root).status(request_id=batch_body["request_id"])
                _require(saved["schema_version"] == "host-model-batch-v2"
                         and saved["body"] == {**batch_body, "provider": "delegated"}
                         and saved["run_id"] == intent["run_id"] and saved["source_snapshot_sha256"] == intent["source_snapshot_sha256"],
                         "EVIDENCE_CHANGED", "The saved batch differs from its original continuation.")
                matches = [item for item in [*saved["steps"], saved.get("plan_step")] if item and item["host_request_id"] == host_id]
                _require(len(matches) == 1, "ARTIFACT_NOT_FOUND", "This Host request is not an original batch step.")
                step = matches[0]
            host = journal.status(request_id=host_id)
            grant = journal.status()["grant"]
            original = spec if step is None else batch_body
            _require(grant is not None and all(grant.get(key) == original[key] for key in ("decision_limit", "cli_budget_usd", "reason"))
                     and host.get("prepare_specification", {}).get("grant") == grant,
                     "EVIDENCE_CHANGED", "The original Host grant changed.")
            _require(host.get("provider") == "delegated" and host.get("controller_request_id") == host_id,
                     "EVIDENCE_CHANGED", "The original Host identity changed.")
            if step is not None:
                _require(host.get("purpose", "selection") == step["purpose"]
                         and fingerprint(host.get("context")) == step["context_sha256"]
                         and fingerprint(host.get("prompt")) == step["prompt_sha256"],
                         "EVIDENCE_CHANGED", "The original Host context or prompt changed.")
            else:
                _require(host.get("purpose") == "plan" and host.get("prepare_specification", {}).get("expected_state_version") == spec["expected_state_version"],
                         "EVIDENCE_CHANGED", "The original Host plan identity changed.")
            with tempfile.TemporaryDirectory(dir=self.root, prefix="delegated-response-") as directory:
                path = Path(directory) / "response.bin"
                write_bytes_once(path, raw)
                saved_host = journal.import_response(request_id=host_id, response_file=path)
            return self._response("delegated-response", body["request_id"], body["project_id"],
                                  host_request_id=host_id, status=saved_host["status"], model_record=saved_host)

    def _save_continuation(self, record):
        _require(len(canonical(record).encode("utf-8")) <= 2 * 1024 * 1024,
                 "WORKBENCH_TOO_LARGE", "Continuation metadata exceeds its bounded download size.")
        with self._connect() as con:
            self._save(con, record["result"]["request_id"], record)

    def _stop_continuation(self, record, status, code, reason, *, incomplete=False, phase="stopped"):
        record["status"] = "incomplete" if incomplete else "completed"
        record["result"].update(record_status=record["status"], status=status, phase=phase,
            stop={"code": code, "reason": reason, "resume_allowed": incomplete})
        self._save_continuation(record)
        return copy.deepcopy(record["result"])

    @staticmethod
    def _continuation_host_gate(journal, state, own_request=None):
        host = journal.status()
        adopted = {item["model_request_id"] for item in state.get("recipe_revisions", [])}
        _require(not any(item["request_id"] != own_request and (item["status"] in PENDING
                     or (item["status"] == "proposed" and (item.get("purpose") == "plan"
                         or (item.get("purpose") == "recipe" and item["request_id"] not in adopted))))
                     for item in host["requests"]),
                 "HOST_SELECTION_PENDING", "Resolve the existing host request or explicit proposal adoption before starting another stage.")
        return host

    @staticmethod
    def _continuation_grant(host):
        grant, usage = host["grant"], host["usage"]
        _require(grant is not None, "HOST_GRANT_REQUIRED", "No existing host grant is available; continuation cannot create one.")
        _require(usage["decision_slots_used"] < grant["decision_limit"], "HOST_DECISION_LIMIT", "The original host decision limit is exhausted.")
        _require(not usage["cli_cost_unknown"], "HOST_USAGE_UNKNOWN", "Earlier CLI usage is unknown, not zero.")
        _require(usage["known_cli_reported_cost_usd"] < grant["cli_budget_usd"],
                 "HOST_CLI_BUDGET_EXHAUSTED", "The original reported CLI estimate cap is exhausted.")
        return grant

    def _request_continuation_plan(self, record, journal, host, executable):
        specification, view = record["intent"]["plan_specification"], record["result"]
        request_id = specification["request_id"]
        model = journal.status(request_id=request_id) if any(item["request_id"] == request_id for item in host["requests"]) else None
        if model is not None:
            _require(model["provider"] == specification["provider"] and model.get("purpose") == "plan"
                     and model["prepare_specification"]["executable"] == specification.get("executable"),
                     "EVIDENCE_CHANGED", "The plan request differs from its frozen provider and route.")
            view["plan_ref"]["status"] = view["steps"][0]["status"] = model["status"]
        if specification["provider"] == "claude_cli" and (model is None or model["status"] in {"prepared", "sending", "unknown"}):
            _require(executable is not None and Path(executable).is_file(), "MODEL_DISABLED", "Resume the plan with the original service-selected native CLI.")
            _require(str(Path(executable).absolute()) == specification["executable"],
                     "CONFIG_CHANGED", "The plan must keep its original service-selected native CLI path.")
        if model is None or model["status"] in {"prepared", "sending", "unknown"}:
            model = journal.prepare(**specification)
        if model["provider"] == "claude_cli" and model["status"] in {"prepared", "sending", "unknown"}:
            model = journal.request(request_id=request_id)
        if model["status"] == "received":
            model = journal.consume(request_id=request_id)
        return model

    def _continue_plan(self, record, project, executable):
        view, intent = record["result"], record["intent"]
        state = project.status()
        journal = HostModelSelection(project.root)
        ref = view["plan_ref"]
        host = self._continuation_host_gate(journal, state, ref["request_id"] if ref else None)
        if view["body"]["plan_mode"] == "reuse":
            _require(state["snapshot_ref"] == intent["cursor_snapshot_ref"], "STALE_STATE", "Project changed outside this continuation.")
            revisions = state.get("plan_revisions", [])
            _require(bool(revisions), "PLAN_REQUIRED", "Save or explicitly adopt a research plan before reusing it.")
            revision = revisions[-1]
            view["plan_ref"] = {"kind": "project_plan", "request_id": revision["request_id"],
                                "plan_version": revision["version"], "status": "applied"}
            view["steps"] = [{"ordinal": 1, "phase": "plan", "request_id": revision["request_id"], "status": "applied",
                "controller_request_id": None, "child_request_id": None,
                "snapshot_ref_before": state["snapshot_ref"], "snapshot_ref_after": state["snapshot_ref"]}]
        else:
            if ref is None:
                _require(state["snapshot_ref"] == intent["cursor_snapshot_ref"]
                         and batch_code_identity() == intent["batch_code_identity"],
                         "STALE_STATE", "The original plan preparation cursor changed.")
                grant = self._continuation_grant(host)
                request_id = "continue-" + intent["request_sha256"][:32] + "-plan"
                view["plan_ref"] = ref = {"kind": "host_plan", "request_id": request_id, "plan_version": None, "status": "preparing"}
                intent["plan_specification"] = {"request_id": request_id, "provider": "claude_cli" if executable is not None else "delegated", "purpose": "plan",
                    "expected_state_version": view["cursor_state_version"], **{key: grant[key] for key in ("decision_limit", "cli_budget_usd", "reason")}}
                if executable is not None:
                    intent["plan_specification"]["executable"] = str(Path(executable).absolute())
                view["steps"] = [{"ordinal": 1, "phase": "plan", "request_id": request_id, "status": "preparing",
                    "controller_request_id": request_id, "child_request_id": None,
                    "snapshot_ref_before": intent["cursor_snapshot_ref"], "snapshot_ref_after": None}]
                self._save_continuation(record)
            model = self._request_continuation_plan(record, journal, host, executable)
            ref["status"] = view["steps"][0]["status"] = model["status"]
            if model["status"] == "applied":
                revision = (model.get("outcome") or {}).get("research_plan")
                _require(bool(state.get("plan_revisions")) and state["plan_revisions"][-1] == revision
                         and revision["request_id"] == model["controller_request_id"]
                         and revision["based_on_state_version"] == view["cursor_state_version"]
                         and state["state_version"] == view["cursor_state_version"] + 1,
                         "STALE_STATE", "Only adoption of this exact plan may advance the continuation cursor.")
                ref["plan_version"] = revision["version"]
                view["steps"][0]["snapshot_ref_after"] = state["snapshot_ref"]
                intent["cursor_snapshot_ref"] = state["snapshot_ref"]
                view["cursor_state_version"] = state["state_version"]
            else:
                _require(state["snapshot_ref"] == intent["cursor_snapshot_ref"], "STALE_STATE", "Project changed outside the linked plan adoption.")
                if model["status"] == "proposed":
                    self._stop_continuation(record, "waiting", "PLAN_ADOPTION_REQUIRED", "Explicitly adopt or reject the linked saved plan before continuing.",
                                            incomplete=True, phase="awaiting_adoption")
                elif model["status"] in PENDING:
                    reason = ("Reconcile the original CLI plan request and saved transport; an unresolved launch will not be resent."
                              if model["provider"] == "claude_cli" else
                              "Wait for or import the original delegated plan response; no model was launched by this continuation.")
                    self._stop_continuation(record, "needs_review" if model["status"] in {"sending", "unknown"} else "waiting",
                        "HOST_PLAN_PENDING", reason,
                        incomplete=True, phase="plan")
                else:
                    self._stop_continuation(record, "blocked", "PLAN_" + model["status"].upper(), "The original plan proposal stopped; no replacement was prepared.")
                return False
        view.update(phase="actions", stop=None)
        self._save_continuation(record)
        return True

    @staticmethod
    def _check_delegated_continuation(record, project):
        intent, state = record["intent"], project.status()
        _require(state["id"] == intent["project_id"] and state["run_id"] == intent["run_id"]
                 and state["source_snapshot_sha256"] == intent["source_snapshot_sha256"]
                 and state["code_identity"] == intent["project_code_identity"],
                 "EVIDENCE_CHANGED", "The original project identity changed.")
        _require(batch_code_identity() == intent["batch_code_identity"]
                 and project_controller.code_identity() == intent["controller_code_identity"],
                 "CODE_CHANGED", "Resume using the original continuation implementation.")

    def _prepare_continuation_actions(self, record, project, executable):
        view, intent = record["result"], record["intent"]
        if "batch_body" in intent:
            if view["body"]["execution_mode"] == "model":
                _require(executable is not None and Path(executable).is_file()
                         and str(Path(executable).absolute()) == intent["batch_body"]["executable"],
                         "MODEL_DISABLED", "Resume requires the original service-selected native CLI.")
            return
        state, body = project.status(), view["body"]
        _require(state["snapshot_ref"] == intent["cursor_snapshot_ref"], "STALE_STATE", "Project changed before the action batch was frozen.")
        _require(batch_code_identity() == intent["batch_code_identity"]
                 and project_controller.code_identity() == intent["controller_code_identity"],
                 "CODE_CHANGED", "Unfinished continuation requires its original implementation.")
        project._require_fresh(state, state, view["cursor_state_version"])
        host = self._continuation_host_gate(HostModelSelection(project.root), state)
        request_id = self._continuation_batch_id(intent["request_sha256"])
        if body["execution_mode"] == "rules":
            batch_body = {key: copy.deepcopy(body[key]) for key in ("project_id", "max_actions", "allowed_methods", "source_receipt_sha256s", "reason")}
            batch_body.update(request_id=request_id, expected_state_version=view["cursor_state_version"])
        else:
            context = ProjectController(project.root).selection_context()
            if context["blockers"]:
                raise ResearchError(context["blockers"][0]["code"], "Resolve the current saved execution or code blocker before requesting a model.")
            _require(bool(context["candidates"]), "NO_HOST_CANDIDATES", "No eligible model action is available; no decision was requested.")
            _require(all(item["method_id"] in body["allowed_methods"]
                         and ("receipt_snapshot_sha256" not in item["parameters"]
                              or item["parameters"]["receipt_snapshot_sha256"] in body["source_receipt_sha256s"])
                         for item in context["candidates"]),
                     "NOT_AUTHORIZED", "Current model candidates exceed the explicit method or exact receipt scope.")
            if body["max_actions"] > 1 or body["execution_mode"] == "delegated":
                _require({item["method_id"] for item in context["conditions"]} <= set(body["allowed_methods"])
                         and {item["receipt_snapshot_sha256"] for item in state.get("evidence_sources", [])} <= set(body["source_receipt_sha256s"]),
                         "NOT_AUTHORIZED", "Two model decisions require the native batch's entire frozen method and receipt scope.")
            grant = self._continuation_grant(host)
            batch_body = {"request_id": request_id, "expected_state_version": view["cursor_state_version"], "max_decisions": body["max_actions"],
                          **{key: grant[key] for key in ("decision_limit", "cli_budget_usd", "reason")}}
            if body["execution_mode"] == "delegated":
                batch_body["post_action_plan"] = body["post_action_plan"]
            else:
                _require(executable is not None and Path(executable).is_file(), "MODEL_DISABLED", "Model actions require a service-selected native CLI.")
                batch_body["executable"] = str(Path(executable).absolute())
        intent["batch_body"] = batch_body
        view["batch_ref"] = {"kind": "local" if body["execution_mode"] == "rules" else "delegated" if body["execution_mode"] == "delegated" else "host",
                             "request_id": request_id, "status": "prepared", "record_status": "incomplete"}
        self._save_continuation(record)

    def _complete_continuation_batch(self, record, project, native):
        view = record["result"]
        is_local = view["batch_ref"]["kind"] == "local"
        saved = self.batch_record(view["batch_ref"]["request_id"]) if is_local else native
        steps = saved["steps"]
        view["steps"] = [step for step in view["steps"] if step["phase"] == "plan"]
        state = project.status()
        for index, step in enumerate(steps):
            request_id = step["request_id"] if is_local else step["host_request_id"]
            parent_id = request_id if is_local else step.get("controller_request_id")
            parent = (step.get("parent") if is_local else None) or next((item for item in state.get("controller_requests", []) if item["request_id"] == parent_id), None)
            after = (steps[index + 1]["snapshot_ref_before"] if index + 1 < len(steps) else saved.get("cursor_snapshot_ref")) if is_local and step["status"] == "completed" else step.get("snapshot_ref_after")
            view["steps"].append({"ordinal": len(view["steps"]) + 1, "phase": "actions", "request_id": request_id,
                "status": parent["status"] if is_local and parent else step["status"] if is_local else step["host_status"],
                "controller_request_id": parent["request_id"] if parent else None,
                "child_request_id": step.get("child_request_id") or (parent or {}).get("child_request_id"),
                "snapshot_ref_before": step["snapshot_ref_before"], "snapshot_ref_after": after})
            if parent and parent.get("state_version_after") is not None:
                view["cursor_state_version"] = parent["state_version_after"]
        status = native["status"]
        record_status = saved["status"] if is_local else saved["record_status"]
        view["batch_ref"].update(status=status, record_status=record_status)
        if view["batch_ref"]["kind"] == "delegated" and saved.get("plan_step") is not None:
            plan = saved["plan_step"]
            view["batch_ref"]["plan_request_id"] = plan["host_request_id"]
            view["steps"].append({"ordinal": len(view["steps"]) + 1, "phase": "post_action_plan",
                "request_id": plan["host_request_id"], "status": plan["host_status"],
                "controller_request_id": plan.get("controller_request_id"), "child_request_id": None,
                "snapshot_ref_before": plan["snapshot_ref_before"], "snapshot_ref_after": plan.get("snapshot_ref_after")})
            if status == "plan_adopted" and plan.get("snapshot_ref_after") == state["snapshot_ref"]:
                view["cursor_state_version"] = state["state_version"]
        stop = native["batch"]["stop"] if is_local else native["stop"]
        return self._stop_continuation(record, "needs_review" if status == "unknown" else status, stop["code"], stop["reason"],
                                       incomplete=record_status != "completed", phase="actions" if record_status != "completed" else "stopped")

    @staticmethod
    def _continuation_batch_id(digest):
        return "continue-" + digest[:32] + "-actions"

    @staticmethod
    def _continuation_body(body):
        fields = ("request_id", "project_id", "expected_state_version", "plan_mode", "execution_mode", "max_actions",
                  "allowed_methods", "source_receipt_sha256s", "reason")
        delegated = type(body) is dict and body.get("execution_mode") == "delegated"
        digest = _body(body, (*fields, "post_action_plan") if delegated else fields)
        _require(type(body["plan_mode"]) is str and body["plan_mode"] in {"reuse", "suggest"}
                 and type(body["execution_mode"]) is str and body["execution_mode"] in {"rules", "model", "delegated"}
                 and (not delegated or type(body["post_action_plan"]) is bool)
                 and type(body["expected_state_version"]) is int and body["expected_state_version"] >= 0
                 and type(body["max_actions"]) is int and 1 <= body["max_actions"] <= (8 if body["execution_mode"] == "rules" else 2)
                 and _text(body["reason"], 4000) and type(body["allowed_methods"]) is list and bool(body["allowed_methods"])
                 and all(type(item) is str for item in body["allowed_methods"]) and len(set(body["allowed_methods"])) == len(body["allowed_methods"])
                 and type(body["source_receipt_sha256s"]) is list and len(body["source_receipt_sha256s"]) <= 16
                 and all(type(item) is str and re.fullmatch(r"[a-f0-9]{64}", item) for item in body["source_receipt_sha256s"])
                 and len(set(body["source_receipt_sha256s"])) == len(body["source_receipt_sha256s"]),
                 "INVALID_REQUEST", "Use a bounded plan and action continuation with exact existing method and receipt scope.")
        return digest, delegated

    def preview_continuation(self, body):
        """Read-only identifiers for an unprepared future request, never execution eligibility."""
        digest, delegated = self._continuation_body(body)
        with self._connect(readonly=True) as con:
            self._project(con, body["project_id"], active=True)
        predictable = delegated and body["plan_mode"] == "reuse"
        batch_id = self._continuation_batch_id(digest) if predictable else None
        steps = []
        if predictable:
            for ordinal in range(1, body["max_actions"] + 1):
                host_id = HostModelBatch.delegated_step_id(batch_id, "selection", ordinal)
                steps.append({"ordinal": ordinal, "host_request_id": host_id, "controller_request_id": host_id})
        plan_id = (HostModelBatch.delegated_step_id(batch_id, "plan", 0)
                   if predictable and body["post_action_plan"] else None)
        return {"schema_version": "local-research-continuation-preview-v1", "project_id": body["project_id"],
                "request_id": body["request_id"], "body_sha256": digest, "batch_request_id": batch_id,
                "steps": steps, "post_action_plan_host_request_id": plan_id,
                "status": "identifiers_computed" if predictable else "stage_unknown", "authorization": "not_authorized",
                "preparation_state": "unknown_not_checked", "execution_eligibility": "not_checked"}

    def continue_research(self, body, *, executable=None):
        digest, delegated = self._continuation_body(body)
        with self._writer():
            with self._connect() as con:
                old = self._old(con, body, digest)
                _, project = self._project(con, body["project_id"], active=old is None or old["status"] != "completed")
                if old is not None:
                    self._check_continuation(old, digest)
                    if old["status"] == "completed":
                        return copy.deepcopy(old["result"])
                self._no_pending_batch(con, body["project_id"], body["request_id"], evidence=True)
                if old is None:
                    state = project.status()
                    project._require_fresh(state, state, body["expected_state_version"])
                    _require(set(body["allowed_methods"]) <= {registry.primary_id(state), *registry.followup_ids(registry.primary_id(state)), registry.source_id(state)},
                             "METHOD_NOT_SUPPORTED", "Continue methods must belong to the existing project allowlist.")
                    _require(set(body["source_receipt_sha256s"]) <= {item["receipt_snapshot_sha256"] for item in state.get("evidence_sources", [])},
                             "SOURCE_NOT_REGISTERED", "Only exact already-registered receipts may be authorized.")
                    project._require_unclaimed(state, body["request_id"])
                    with project._connect(readonly=True) as project_con:
                        _require(project._action(project_con, body["request_id"]) is None, "IDEMPOTENCY_CONFLICT", "Continue ID belongs to an existing action.")
                    intent = {"project_id": state["id"], "request_sha256": digest, "run_id": state["run_id"],
                        "source_snapshot_sha256": state["source_snapshot_sha256"], "project_code_identity": state["code_identity"],
                        "controller_code_identity": project_controller.code_identity(), "batch_code_identity": batch_code_identity(),
                        "cursor_snapshot_ref": state["snapshot_ref"]}
                    record = self._accept(con, body, digest, "continue", intent)
                    view = {"schema_version": "local-research-continuation-v1", "request_id": body["request_id"], "project_id": state["id"],
                        "body": copy.deepcopy(body), "record_status": "incomplete", "status": "waiting", "phase": "plan",
                        "plan_ref": None, "batch_ref": None, "steps": [], "stop": None, "cursor_state_version": state["state_version"]}
                    record.update(status="incomplete", result=view)
                    self._save(con, body["request_id"], record)
                else:
                    record = old
            try:
                if delegated:
                    self._check_delegated_continuation(record, project)
                if record["result"]["phase"] in {"plan", "awaiting_adoption"} and not self._continue_plan(record, project, None if delegated else executable):
                    return copy.deepcopy(record["result"])
                self._prepare_continuation_actions(record, project, executable)
            except ResearchError as error:
                pending_batch = "batch_body" in record["intent"]
                pending_plan = (record["result"]["phase"] in {"plan", "awaiting_adoption"}
                                and bool(record["intent"].get("plan_specification")))
                status = "needs_review" if pending_batch or pending_plan or error.code in {"EXECUTION_UNKNOWN", "PROJECT_BUSY"} else "waiting" if error.code == "NO_HOST_CANDIDATES" else "blocked"
                return self._stop_continuation(record, status,
                    error.code, str(error), incomplete=pending_batch or pending_plan,
                    phase="actions" if pending_batch else "plan" if pending_plan else "stopped")
            batch_body = copy.deepcopy(record["intent"]["batch_body"])
        # Existing batches acquire their own manager/Host locks and preserve original IDs.
        try:
            if delegated:
                with self._writer():
                    with self._connect(readonly=True) as con:
                        self._project(con, body["project_id"], active=True)
                    native = HostModelBatch(project.root).advance_delegated(**batch_body)
            else:
                native = self.batch(batch_body) if body["execution_mode"] == "rules" else HostModelBatch(project.root).advance(**batch_body)
        except Exception as error:
            with self._writer():
                with self._connect(readonly=True) as con:
                    latest = self._old(con, body, digest)
                if latest["status"] == "completed":
                    return copy.deepcopy(latest["result"])
                return self._stop_continuation(latest, "needs_review", getattr(error, "code", "CONTINUATION_INTERRUPTED"),
                    "Read and reconcile the original saved batch before continuing; no replacement was created.", incomplete=True, phase="actions")
        with self._writer():
            with self._connect(readonly=True) as con:
                latest = self._old(con, body, digest)
            if latest["status"] == "completed":
                return copy.deepcopy(latest["result"])
            return self._complete_continuation_batch(latest, project, native)

    @staticmethod
    def _check_staged_continuation(record, digest):
        _require(type(record) is dict and record.get("schema_version") in {"local-staged-continuation-v1", "local-staged-continuation-v2"}
                 and record.get("status") in {"incomplete", "completed"} and record.get("phase") in {"audit", "freeze", "final", "report", "done", "waiting"}
                 and type(record.get("body")) is dict and fingerprint(record["body"]) == digest
                 and record.get("intent", {}).get("request_sha256") == digest
                 and record["intent"].get("project_id") == record["body"].get("project_id")
                 and type(record.get("steps")) is dict
                 and record.get("record_sha256") == fingerprint({k: v for k, v in record.items() if k != "record_sha256"}),
                 "EVIDENCE_CHANGED", "The saved staged continuation differs from its original authorization.")
        if record["schema_version"] == "local-staged-continuation-v1":
            _require("registration_request_id" not in record["body"] and record["phase"] != "waiting",
                     "EVIDENCE_CHANGED", "The original fixed continuation changed version.")
        else:
            policy = record.get("conditional")
            _require(set(record["body"]) == {"request_id", "project_id", "expected_state_version", "primary_action_id", "reason", "registration_request_id"}
                     and type(policy) is dict and type(policy.get("context")) is dict and type(policy.get("feedback")) is dict
                     and type(policy.get("proposal")) is dict and type(policy.get("registration")) is dict
                     and policy.get("decision") in {"audit", "wait"}
                     and policy["context"].get("snapshot_ref") == record["intent"].get("initial_snapshot_ref")
                     and policy["context"].get("state_version") == record["body"]["expected_state_version"]
                     and (record["phase"] != "waiting" or (record["status"] == "completed" and policy.get("decision") == "wait"
                          and record["steps"] == {} and record.get("result") == {"status": "waiting", "reason": policy.get("reason"),
                          "feedback_outcome": policy.get("feedback", {}).get("outcome"), "final_evaluation_performed": False})),
                     "EVIDENCE_CHANGED", "The original conditional continuation changed.")
            if record["phase"] != "waiting":
                audit = record["steps"].get("audit")
                _require(policy["decision"] == "audit" and type(audit) is dict and audit.get("reused") is False
                         and audit.get("snapshot_ref_before") == policy["context"]["snapshot_ref"]
                         and audit.get("body") == {"request_id": "staged-" + digest[:32] + "-audit",
                                                   "expected_state_version": policy["context"]["state_version"],
                                                   "proposal": policy["proposal"]},
                         "EVIDENCE_CHANGED", "The original conditional audit request changed.")

    def staged_continuation_record(self, request_id):
        identifier(request_id)
        with self._connect(readonly=True) as con:
            row = con.execute("SELECT digest,record FROM requests WHERE id=? AND command='continue_staged'", (request_id,)).fetchone()
            _require(row is not None, "ARTIFACT_NOT_FOUND", "No saved staged continuation matches this ID.")
            record = tabular._parse(row["record"].encode("utf-8"))
            self._check_staged_continuation(record, row["digest"])
        return copy.deepcopy(record)

    def _save_staged_continuation(self, record):
        record["record_sha256"] = fingerprint({k: v for k, v in record.items() if k != "record_sha256"})
        _require(len(canonical(record).encode("utf-8")) <= 2 * 1024 * 1024,
                 "WORKBENCH_TOO_LARGE", "Staged continuation metadata exceeds its bound.")
        with self._connect() as con:
            self._save(con, record["body"]["request_id"], record)

    def _stop_staged_continuation(self, record, code, reason):
        record["status"] = "incomplete"
        record["stop"] = {"code": code, "reason": reason, "resume_allowed": True}
        self._save_staged_continuation(record)
        return copy.deepcopy(record)

    def _verify_completed_staged(self, record, project, digest):
        from . import staged_continuation as staged
        _require(record["phase"] == "done" and type(record.get("result")) is dict
                 and record["result"].get("status") == "completed"
                 and set(record["steps"]) == {"audit", "freeze", "final", "report"}
                 and all(record["steps"][key].get("status") == "completed" for key in ("audit", "freeze", "final", "report")),
                 "EVIDENCE_CHANGED", "The completed staged receipt is incomplete.")
        state = project.status()
        _require(record["intent"]["helper_code_identity"] == staged.code_identity()
                 and record["intent"]["batch_code_identity"] == batch_code_identity()
                 and record["intent"]["controller_code_identity"] == project_controller.code_identity(),
                 "CODE_CHANGED", "Use the original staged continuation implementation.")
        report_step, body = record["steps"]["report"], record["body"]
        report_body = {"request_id": "staged-" + digest[:32] + "-report", "project_id": body["project_id"],
                       "expected_state_version": state["state_version"]}
        _require(report_step.get("body") == report_body and report_step.get("snapshot_ref_before") == state["snapshot_ref"]
                 and record["result"].get("report_request_id") == report_body["request_id"]
                 and record["result"].get("manifest") == report_step.get("manifest"),
                 "EVIDENCE_CHANGED", "The completed report binding differs from the original project.")
        inspection = staged.inspect(project, state, body["primary_action_id"])
        _require(not inspection["blockers"] and all(record["steps"][key].get("reference") == inspection[key] for key in ("audit", "freeze", "final")),
                 "EVIDENCE_CHANGED", "The original completed staged evidence changed.")
        if record["schema_version"] == "local-staged-continuation-v2":
            staged.verify_conditional_audit(state, body, record["conditional"], "staged-" + digest[:32] + "-audit", inspection)
        manifest = self._verify_report(fingerprint(report_body), report_step["manifest"])
        _require(manifest.get("project_id") == body["project_id"] and manifest.get("project_snapshot_ref") == state["snapshot_ref"]
                 and host_model_report_current(project.root, manifest), "EVIDENCE_CHANGED", "The original report or host evidence changed.")

    def _verify_staged_report_ready(self, record, project):
        from . import staged_continuation as staged
        state, intent = project.status(), record["intent"]
        _require(state["id"] == intent["project_id"] and state["run_id"] == intent["run_id"]
                 and state["source_snapshot_sha256"] == intent["source_snapshot_sha256"]
                 and state["snapshot_ref"] == record["cursor_snapshot_ref"]
                 and state["code_identity"] == intent["project_code_identity"]
                 and project_controller.code_identity() == intent["controller_code_identity"]
                 and batch_code_identity() == intent["batch_code_identity"] and staged.code_identity() == intent["helper_code_identity"],
                 "EVIDENCE_CHANGED", "The original staged project, cursor or implementation changed.")
        self._continuation_host_gate(HostModelSelection(project.root), state)
        inspection = staged.inspect(project, state, record["body"]["primary_action_id"])
        _require(not inspection["blockers"] and all(record["steps"].get(key, {}).get("status") == "completed"
                 and record["steps"][key].get("reference") == inspection[key] for key in ("audit", "freeze", "final")),
                 "EVIDENCE_CHANGED", "Original completed stages changed before the report.")
        if record["schema_version"] == "local-staged-continuation-v2":
            staged.verify_conditional_audit(state, record["body"], record["conditional"],
                "staged-" + record["intent"]["request_sha256"][:32] + "-audit", inspection)
        return state

    def continue_staged(self, body):
        from . import staged_continuation as staged
        conditional = type(body) is dict and "registration_request_id" in body
        fields = ("request_id", "project_id", "expected_state_version", "primary_action_id", "reason")
        digest = _body(body, fields + (("registration_request_id",) if conditional else ()))
        identifier(body["primary_action_id"], "primary_action_id")
        if conditional:
            identifier(body["registration_request_id"], "registration_request_id")
        _require(type(body["expected_state_version"]) is int and body["expected_state_version"] >= 0
                 and _text(body["reason"], 4000), "INVALID_REQUEST", "Use an exact version, primary action and bounded authorization reason.")
        ids = {phase: "staged-" + digest[:32] + "-" + phase for phase in ("audit", "freeze", "final", "report")}
        with self._writer():
            with self._connect() as con:
                old = self._old(con, body, digest)
                _, project = self._project(con, body["project_id"], active=old is None or old["status"] != "completed")
                if old is not None:
                    self._check_staged_continuation(old, digest)
                    if old["status"] == "completed":
                        if conditional and old["phase"] == "waiting":
                            staged.verify_conditional_policy(project.status(), body, old["conditional"])
                            return copy.deepcopy(old)
                        self._verify_completed_staged(old, project, digest)
                        return copy.deepcopy(old)
                self._no_pending_batch(con, body["project_id"], body["request_id"], evidence=True)
                if old is None:
                    state = project.status()
                    private = state.get("private_evaluation")
                    if type(private) is dict and private.get("schema_version") == "retrieval-holdout-registration-v2":
                        from .retrieval_holdout import validate_metadata
                        validated = validate_metadata(state)
                        _require(conditional and body["registration_request_id"] == validated["private_evaluation"]["policy"]["registration_request_id"],
                                 "CONDITION_NOT_SATISFIED", "This holdout requires its original conditional continuation.")
                    if conditional:
                        _require(state["state_version"] == body["expected_state_version"], "STALE_STATE", "Project state changed.")
                        _require(state["code_identity"] == project_code_identity(), "CODE_CHANGED", "Use the original project implementation.")
                    else:
                        project._require_fresh(state, state, body["expected_state_version"])
                        self._continuation_host_gate(HostModelSelection(project.root), state)
                    for row in con.execute("SELECT record FROM requests WHERE command='export'"):
                        existing = tabular._parse(row["record"].encode("utf-8"))
                        _require(existing.get("status") == "completed" or existing.get("intent", {}).get("project_id") != body["project_id"],
                                 "OPERATION_INCOMPLETE", "Resolve the original unfinished report before continuing.")
                    policy = None
                    if conditional:
                        _require(not any(action.get("command") == "research.relevance-validation-saved-audit"
                                         for action in state["actions"]),
                                 "CONDITION_NOT_SATISFIED", "Conditional continuation cannot reuse a prior saved audit.")
                        context = ProjectController(project.root).selection_context()
                        _require(context["snapshot_ref"] == state["snapshot_ref"], "STALE_STATE", "Project changed during feedback inspection.")
                        policy = staged.conditional_policy(state, body["registration_request_id"], body["primary_action_id"], context)
                        if policy["decision"] == "wait":
                            project._require_unclaimed(state, body["request_id"])
                            with project._connect(readonly=True) as project_con:
                                _require(project._action(project_con, body["request_id"]) is None,
                                         "IDEMPOTENCY_CONFLICT", "The parent ID is already an action.")
                            intent = {"project_id": state["id"], "run_id": state["run_id"], "request_sha256": digest,
                                      "source_snapshot_sha256": state["source_snapshot_sha256"], "project_code_identity": state["code_identity"],
                                      "controller_code_identity": project_controller.code_identity(), "batch_code_identity": batch_code_identity(),
                                      "helper_code_identity": staged.code_identity(), "initial_snapshot_ref": state["snapshot_ref"]}
                            record = self._accept(con, body, digest, "continue_staged", intent)
                            record.update(schema_version="local-staged-continuation-v2", status="completed", body=copy.deepcopy(body),
                                phase="waiting", steps={}, cursor_snapshot_ref=state["snapshot_ref"], stop=None, conditional=policy,
                                result={"status": "waiting", "reason": policy["reason"], "feedback_outcome": policy["feedback"]["outcome"],
                                        "final_evaluation_performed": False})
                            record["record_sha256"] = fingerprint({k: v for k, v in record.items() if k != "record_sha256"})
                            self._save(con, body["request_id"], record)
                            return copy.deepcopy(record)
                        project._require_fresh(state, state, body["expected_state_version"])
                        self._continuation_host_gate(HostModelSelection(project.root), state)
                    inspection = staged.inspect(project, state, body["primary_action_id"])
                    if inspection["blockers"]:
                        blocker = inspection["blockers"][0]
                        raise ResearchError(blocker["code"], blocker["reason"])
                    if conditional:
                        _require(inspection["audit"] is None and inspection["freeze"] is None and inspection["final"] is None,
                                 "CONDITION_NOT_SATISFIED", "Conditional continuation cannot reuse an existing audit or later stage.")
                    _require(inspection["required_tool_calls"] <= 2 and inspection["required_tool_calls"] <= inspection["available_tool_calls"],
                             "BUDGET_EXHAUSTED", "The existing project budget cannot cover the missing authorized stages.")
                    _require(body["request_id"] not in ids.values(), "IDEMPOTENCY_CONFLICT", "The parent and stage IDs must differ.")
                    project._require_unclaimed(state, body["request_id"])
                    with project._connect(readonly=True) as project_con:
                        _require(project._action(project_con, body["request_id"]) is None, "IDEMPOTENCY_CONFLICT", "The parent ID is already an action.")
                    for phase, child_id in ids.items():
                        _require(con.execute("SELECT 1 FROM requests WHERE id=?", (child_id,)).fetchone() is None,
                                 "IDEMPOTENCY_CONFLICT", "A derived stage ID is already a manager request.")
                        project._require_unclaimed(state, child_id)
                        with project._connect(readonly=True) as project_con:
                            _require(project._action(project_con, child_id) is None, "IDEMPOTENCY_CONFLICT", "A derived stage ID is already an action.")
                            if phase in {"audit", "final"}:
                                controller_child = "controller-child-" + fingerprint({"project_id": state["id"], "request_id": child_id})[:32]
                                project._require_unclaimed(state, controller_child)
                                _require(project._action(project_con, controller_child) is None,
                                         "IDEMPOTENCY_CONFLICT", "A derived controller child ID is already an action.")
                    intent = {"project_id": state["id"], "run_id": state["run_id"], "request_sha256": digest,
                              "source_snapshot_sha256": state["source_snapshot_sha256"], "project_code_identity": state["code_identity"],
                              "controller_code_identity": project_controller.code_identity(), "batch_code_identity": batch_code_identity(),
                              "helper_code_identity": staged.code_identity(), "initial_snapshot_ref": state["snapshot_ref"]}
                    record = self._accept(con, body, digest, "continue_staged", intent)
                    record.update(schema_version="local-staged-continuation-v2" if conditional else "local-staged-continuation-v1", status="incomplete", body=copy.deepcopy(body),
                                  phase="audit", steps={}, cursor_snapshot_ref=state["snapshot_ref"], stop=None, result=None)
                    if conditional:
                        record["conditional"] = policy
                        record["steps"]["audit"] = {"status": "prepared", "reused": False,
                            "body": {"request_id": ids["audit"], "expected_state_version": state["state_version"],
                                     "proposal": copy.deepcopy(policy["proposal"])}, "snapshot_ref_before": state["snapshot_ref"]}
                    record["record_sha256"] = fingerprint({k: v for k, v in record.items() if k != "record_sha256"})
                    self._save(con, body["request_id"], record)
                else:
                    record = old
            try:
                while record["phase"] != "report":
                    state = project.status()
                    intent = record["intent"]
                    _require(state["id"] == intent["project_id"] and state["run_id"] == intent["run_id"]
                             and state["source_snapshot_sha256"] == intent["source_snapshot_sha256"]
                             and state["code_identity"] == intent["project_code_identity"]
                             and project_controller.code_identity() == intent["controller_code_identity"]
                             and batch_code_identity() == intent["batch_code_identity"] and staged.code_identity() == intent["helper_code_identity"],
                             "CODE_CHANGED", "Resume the original continuation with its original project and implementation.")
                    if conditional:
                        staged.verify_conditional_policy(state, body, record["conditional"])
                    self._continuation_host_gate(HostModelSelection(project.root), state)
                    inspection = staged.inspect(project, state, body["primary_action_id"])
                    if inspection["blockers"]:
                        blocker = inspection["blockers"][0]
                        raise ResearchError(blocker["code"], blocker["reason"])
                    phase = record["phase"]
                    if conditional and inspection["audit"] is not None and inspection["audit"].get("status") == "completed":
                        staged.verify_conditional_audit(state, body, record["conditional"], ids["audit"], inspection)
                    ref = inspection[phase]
                    entry = record["steps"].get(phase)
                    if ref is not None:
                        _require(ref.get("status", "completed") == "completed", "EXECUTION_UNKNOWN", "The original stage is not completed.")
                        if entry is not None:
                            _require(entry["status"] == "completed" or
                                     (ref["request_id"] == ids[phase] if phase == "freeze" else ref["parent_request_id"] == ids[phase]),
                                     "EVIDENCE_CHANGED", "The completed stage does not match its frozen request.")
                            if entry["status"] == "completed":
                                _require(entry["reference"] == ref, "EVIDENCE_CHANGED", "The original completed stage changed.")
                            else:
                                saved_body = entry["body"]
                                if phase == "freeze":
                                    _require(ref["state_version_before"] == saved_body["expected_state_version"]
                                             and state["state_version"] == saved_body["expected_state_version"] + 1,
                                             "EVIDENCE_CHANGED", "The frozen strategy does not match its original version.")
                                else:
                                    parent = ProjectController._parent(state, ids[phase])
                                    expected_request = {"project_id": state["id"], "command": "controller.advance_selection",
                                                        "need": "next_check", "expected_state_version": saved_body["expected_state_version"],
                                                        "proposal": saved_body["proposal"]}
                                    _require(parent is not None and parent["request"] == expected_request
                                             and parent["request_sha256"] == fingerprint(expected_request)
                                             and parent["snapshot_ref_before"] == entry["snapshot_ref_before"]
                                             and parent["state_version_before"] == saved_body["expected_state_version"]
                                             and parent["state_version_after"] == state["state_version"],
                                             "EVIDENCE_CHANGED", "The controller result differs from the frozen original stage.")
                        else:
                            _require(state["snapshot_ref"] == record["cursor_snapshot_ref"], "STALE_STATE", "Project changed outside this continuation.")
                            entry = {"status": "completed", "reused": True, "reference": copy.deepcopy(ref)}
                            record["steps"][phase] = entry
                        entry.update(status="completed", reference=copy.deepcopy(ref))
                        record["cursor_snapshot_ref"] = state["snapshot_ref"]
                        record["phase"] = {"audit": "freeze", "freeze": "final", "final": "report"}[phase]
                        record["stop"] = None
                        self._save_staged_continuation(record)
                        continue
                    if entry is None:
                        _require(state["snapshot_ref"] == record["cursor_snapshot_ref"], "STALE_STATE", "Project changed before the original stage was frozen.")
                        if phase == "freeze":
                            stage_body = {"request_id": ids[phase], "expected_state_version": state["state_version"],
                                          "primary_action_id": body["primary_action_id"]}
                        else:
                            context = ProjectController(project.root).selection_context()
                            method = "research.relevance-validation-saved-audit" if phase == "audit" else "research.relevance-final-evaluation"
                            proposal = staged.selection_proposal(context, method, inspection["primary"])
                            stage_body = {"request_id": ids[phase], "expected_state_version": state["state_version"], "proposal": proposal}
                        entry = {"status": "prepared", "reused": False, "body": stage_body, "snapshot_ref_before": state["snapshot_ref"]}
                        record["steps"][phase] = entry
                        self._save_staged_continuation(record)
                    _require(entry["status"] == "prepared" and state["snapshot_ref"] == entry["snapshot_ref_before"],
                             "STALE_STATE", "The original undispatched stage changed; no replacement will be prepared.")
                    if phase == "freeze":
                        expected_body = {"request_id": ids[phase], "expected_state_version": state["state_version"],
                                         "primary_action_id": body["primary_action_id"]}
                        _require(entry["body"] == expected_body, "EVIDENCE_CHANGED", "The original freeze body changed.")
                        project.freeze_retrieval_strategy(**entry["body"])
                    else:
                        method = "research.relevance-validation-saved-audit" if phase == "audit" else "research.relevance-final-evaluation"
                        context = ProjectController(project.root).selection_context()
                        if conditional and phase == "audit":
                            _require(context == record["conditional"]["context"], "EVIDENCE_CHANGED", "The original feedback context changed before audit.")
                            proposal = record["conditional"]["proposal"]
                        else:
                            proposal = staged.selection_proposal(context, method, inspection["primary"])
                        expected_body = {"request_id": ids[phase], "expected_state_version": state["state_version"],
                                         "proposal": proposal}
                        _require(entry["body"] == expected_body, "EVIDENCE_CHANGED", "The original selection body changed.")
                        parent = ProjectController._parent(state, ids[phase])
                        _require(parent is None, "EXECUTION_UNKNOWN", "Reconcile the original controller request; do not dispatch it again.")
                        ProjectController(project.root).advance_selection(**entry["body"])
                    # Re-read and verify the actual original parent/child or freeze before advancing.
                state = self._verify_staged_report_ready(record, project)
                if "report" not in record["steps"]:
                    record["steps"]["report"] = {"status": "prepared", "body": {"request_id": ids["report"], "project_id": body["project_id"],
                                                   "expected_state_version": state["state_version"]}, "snapshot_ref_before": state["snapshot_ref"]}
                    self._save_staged_continuation(record)
                report_body = copy.deepcopy(record["steps"]["report"]["body"])
                _require(report_body == {"request_id": ids["report"], "project_id": body["project_id"],
                                         "expected_state_version": state["state_version"]}
                         and record["steps"]["report"]["snapshot_ref_before"] == state["snapshot_ref"],
                         "EVIDENCE_CHANGED", "The original report body or snapshot changed.")
            except ResearchError as error:
                return self._stop_staged_continuation(record, error.code, str(error))
            except Exception as error:
                return self._stop_staged_continuation(record, getattr(error, "code", "STAGED_INTERRUPTED"),
                    "Inspect the original stage and request; no replacement was created.")
        # Report uses the existing manager export and the original frozen child ID.
        try:
            report = self._export(report_body, staged_parent=body["request_id"])
        except Exception as error:
            with self._writer():
                with self._connect(readonly=True) as con:
                    latest = self._old(con, body, digest)
                self._check_staged_continuation(latest, digest)
                if latest["status"] == "completed":
                    return copy.deepcopy(latest)
                return self._stop_staged_continuation(latest, getattr(error, "code", "REPORT_INTERRUPTED"),
                    "Inspect the original report request and directory; no replacement was created.")
        with self._writer():
            with self._connect(readonly=True) as con:
                latest = self._old(con, body, digest)
                _, project = self._project(con, body["project_id"], active=True)
            self._check_staged_continuation(latest, digest)
            if latest["status"] == "completed":
                return copy.deepcopy(latest)
            _require(latest["phase"] == "report" and latest["steps"]["report"]["body"] == report_body
                     and project.status()["snapshot_ref"] == latest["steps"]["report"]["snapshot_ref_before"]
                     and host_model_report_current(project.root, report["manifest"]),
                     "EVIDENCE_CHANGED", "The original staged report or project changed.")
            latest["steps"]["report"].update(status="completed", manifest=copy.deepcopy(report["manifest"]))
            latest.update(status="completed", phase="done", stop=None,
                          result={"status": "completed", "report_request_id": report_body["request_id"], "manifest": copy.deepcopy(report["manifest"])})
            self._save_staged_continuation(latest)
            return copy.deepcopy(latest)

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
            _require(Path(name).suffix.lower() in {".txt", ".md", ".html", ".htm", ".json", ".csv", ".tsv", ".pdf", ".xlsx",
                                                  ".names", ".data", ".data-original"},
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
        return self._export(body)

    @staticmethod
    def _export_source_identity(state):
        from . import project_report
        method = state["registration"].get("method_id", "p02.saved-oof-residuals")
        _require(method in project_report.KINDS, "UNSUPPORTED_REPORT", "The original project method has no report exporter.")
        kind = project_report.KINDS[method]
        source = project_report.recovery_source_identity(kind)
        _require(source == project_report._RECOVERY_BOOT_IDENTITIES[kind] and batch_code_identity() == _EXPORT_BOOT_IDENTITY
                 and state["code_identity"] == project_code_identity(),
                 "CODE_CHANGED", "Restart using the original report and project source identities.")
        return {"generator_source_identity": source, "exporter_code_identity": project_report.exporter_code_identity(kind),
                "manager_source_identity": _EXPORT_BOOT_IDENTITY}

    @staticmethod
    def _pending_export(con, project_id, own_id):
        for row in con.execute("SELECT id,record FROM requests WHERE command='export'"):
            previous = tabular._parse(row["record"].encode("utf-8"))
            _require(row["id"] == own_id or previous.get("status") == "completed"
                     or previous.get("intent", {}).get("project_id") != project_id,
                     "OPERATION_INCOMPLETE", "Reconcile the original report request before submitting another export.")

    def _recover_export(self, con, body, digest, record, project, staged_parent):
        intent = record.get("intent") or {}
        _require(record.get("status") in {"preparing", "incomplete"}
                 and type(intent) is dict and set(intent) == {"project_id", "snapshot_ref", "state_version", "report_slot", "request_sha256",
                     "recovery_version", "run_id", "project_code_identity", "source_sha256", "source_snapshot_sha256", "host_model_snapshot_sha256",
                     "staged_parent", "generator_source_identity", "exporter_code_identity", "manager_source_identity", "prepared_manifest_sha256"}
                 and intent.get("recovery_version") == "local-export-recovery-v1"
                 and intent.get("request_sha256") == digest and intent.get("report_slot") == digest
                 and intent.get("project_id") == body["project_id"] and intent.get("state_version") == body["expected_state_version"]
                 and intent.get("staged_parent") == staged_parent and type(intent.get("prepared_manifest_sha256")) is str
                 and re.fullmatch(r"[a-f0-9]{64}", intent["prepared_manifest_sha256"]) is not None,
                 "OPERATION_INCOMPLETE", "The original report has no recoverable prepublication identity.")
        state = project.status()
        source_identity = self._export_source_identity(state)
        _require(all(intent.get(key) == value for key, value in source_identity.items())
                 and state["id"] == intent["project_id"] and state["run_id"] == intent["run_id"]
                 and state["state_version"] == intent["state_version"] and state["snapshot_ref"] == intent["snapshot_ref"]
                 and state["source_snapshot_sha256"] == intent["source_snapshot_sha256"]
                 and state["registration"]["source_sha256"] == intent["source_sha256"]
                 and state["code_identity"] == intent["project_code_identity"]
                 and host_model_snapshot_sha256(project.root) == intent["host_model_snapshot_sha256"],
                 "EVIDENCE_CHANGED", "The original report source, project or Host snapshot changed.")
        root = safe_path(self.root / "reports" / digest)
        try:
            _require(root.is_dir() and {path.name for path in root.iterdir()} == {"manifest.json", "report.json", "report.md", "report.pdf", "input.json"},
                     "EVIDENCE_CHANGED", "The original report directory is incomplete or contains extra entries.")
            raw_manifest = reader._read_file(safe_path(root / "manifest.json"), 1_000_000)
            manifest = tabular._parse(raw_manifest)
            _require(canonical(manifest).encode("utf-8") == raw_manifest
                     and hashlib.sha256(raw_manifest).hexdigest() == intent["prepared_manifest_sha256"]
                     and type(manifest) is dict and set(manifest) == {"schema_version", "project_id", "project_snapshot_ref", "host_model_snapshot_sha256", "files", "source_manifest", "scientific_validation"}
                     and manifest.get("project_id") == body["project_id"] and manifest.get("project_snapshot_ref") == state["snapshot_ref"]
                     and manifest.get("host_model_snapshot_sha256") == intent["host_model_snapshot_sha256"]
                     and type(manifest.get("files")) is dict
                     and all(type(identity) is dict and set(identity) == {"sha256", "bytes"}
                             and type(identity["sha256"]) is str and re.fullmatch(r"[a-f0-9]{64}", identity["sha256"]) is not None
                             for identity in manifest["files"].values()),
                     "EVIDENCE_CHANGED", "The original prepared report manifest differs.")
            self._verify_report(digest, manifest)
            report = tabular._parse(reader._read_file(safe_path(root / "report.json"), 64 * 1024 * 1024))
            report_input = tabular._parse(reader._read_file(safe_path(root / "input.json"), 64 * 1024 * 1024))
            raw_source = reader._read_file(safe_path(project.root / "source.json"), 30_000_000)
            source = tabular._parse(raw_source)
            _require(type(report) is dict and type(report_input) is dict and type(source) is dict
                     and report.get("snapshot_sha256") == fingerprint({k: v for k, v in report.items() if k != "snapshot_sha256"})
                     and report.get("project_id") == state["id"] and report.get("project_snapshot_ref") == state["snapshot_ref"]
                     and report.get("project") == state and report.get("exporter_code_identity") == intent["exporter_code_identity"]
                     and report.get("source_manifest") == manifest["source_manifest"] and report.get("input") == report_input
                     and report_input.get("source_packet") == source and source.get("snapshot_sha256") == state["source_snapshot_sha256"]
                     and report_input.get("source_file_identity") == {"sha256": hashlib.sha256(raw_source).hexdigest(), "bytes": len(raw_source)}
                     and hashlib.sha256(raw_source).hexdigest() == intent["source_sha256"]
                     and report.get("host_models", {}).get("snapshot_sha256") == intent["host_model_snapshot_sha256"]
                     and report_input.get("host_models", {}).get("snapshot_sha256") == intent["host_model_snapshot_sha256"],
                     "EVIDENCE_CHANGED", "The original report, input or source binding changed.")
            self._verify_report(digest, manifest)
            _require(project.status()["snapshot_ref"] == state["snapshot_ref"] and host_model_report_current(project.root, manifest)
                     and self._export_source_identity(project.status()) == source_identity,
                     "EVIDENCE_CHANGED", "The original project, report or Host changed during recovery.")
        except ResearchError:
            raise
        except (OSError, KeyError, TypeError, ValueError, RecursionError):
            raise ResearchError("EVIDENCE_CHANGED", "The original report cannot be verified without regeneration.") from None
        response = self._response("export", body["request_id"], body["project_id"], status="exported", manifest=manifest)
        recovered = copy.deepcopy(record)
        recovered.update(status="completed", result=response, recovery_receipt={"schema_version": "local-export-recovered-v1",
                         "prepared_manifest_sha256": intent["prepared_manifest_sha256"]})
        recovered.pop("failure", None)
        updated = con.execute("UPDATE requests SET record=? WHERE id=? AND digest=? AND record=?",
                              (canonical(recovered), body["request_id"], digest, canonical(record)))
        _require(updated.rowcount == 1, "EVIDENCE_CHANGED", "The original manager intent changed during recovery.")
        con.execute("UPDATE projects SET report=? WHERE id=?", (digest, body["project_id"]))
        return dict(response, replayed=True)

    def _export(self, body, *, staged_parent=None):
        digest = _body(body, ("request_id", "project_id", "expected_state_version"))
        _require(type(body["expected_state_version"]) is int and body["expected_state_version"] >= 0,
                 "INVALID_REQUEST", "An exact saved state version is required.")
        with self._writer():
            with self._connect() as con:
                _, project = self._project(con, body["project_id"], active=True)
                if staged_parent is not None:
                    row = con.execute("SELECT digest,record FROM requests WHERE id=? AND command='continue_staged'", (staged_parent,)).fetchone()
                    _require(row is not None, "EVIDENCE_CHANGED", "The original staged authorization is unavailable.")
                    staged = tabular._parse(row["record"].encode("utf-8"))
                    self._check_staged_continuation(staged, row["digest"])
                    state = self._verify_staged_report_ready(staged, project)
                    _require(staged["status"] == "incomplete" and staged["phase"] == "report"
                             and staged["body"]["project_id"] == body["project_id"]
                             and staged["steps"].get("report", {}).get("body") == body
                             and body == {"request_id": "staged-" + row["digest"][:32] + "-report",
                                         "project_id": staged["body"]["project_id"],
                                         "expected_state_version": state["state_version"]}
                             and staged["steps"]["report"].get("snapshot_ref_before") == state["snapshot_ref"],
                             "EVIDENCE_CHANGED", "Report request differs from the frozen staged authorization.")
                self._no_pending_batch(con, body["project_id"], staged_parent, evidence=True)
                old = self._old(con, body, digest)
                if old is not None and old["status"] == "completed":
                    response = self._completed(old)
                    self._verify_report(digest, response["manifest"])
                    return response
                self._pending_export(con, body["project_id"], body["request_id"])
                if old is not None:
                    row = con.execute("SELECT command FROM requests WHERE id=?", (body["request_id"],)).fetchone()
                    _require(row is not None and row["command"] == "export", "EVIDENCE_CHANGED", "The original manager command changed.")
                    return self._recover_export(con, body, digest, old, project, staged_parent)
                state = project.status()
                _require(state["state_version"] == body["expected_state_version"], "STALE_STATE", "Reload the current project before exporting.")
                identity = self._export_source_identity(state)
                host_identity = host_model_snapshot_sha256(project.root)
                _require(project.status()["snapshot_ref"] == state["snapshot_ref"], "STALE_STATE", "Project changed before report intent was accepted.")
                record = self._accept(con, body, digest, "export", {"project_id": state["id"], "snapshot_ref": state["snapshot_ref"],
                    "state_version": state["state_version"], "report_slot": digest, "request_sha256": digest,
                    "recovery_version": "local-export-recovery-v1", "run_id": state["run_id"],
                    "project_code_identity": state["code_identity"], "source_sha256": state["registration"]["source_sha256"],
                    "source_snapshot_sha256": state["source_snapshot_sha256"], "host_model_snapshot_sha256": host_identity,
                    "staged_parent": staged_parent, **identity})
            try:
                # Lazy import avoids the read-only report/workbench module dependency cycle.
                from .project_report import export_report
                output = safe_path(self.root / "reports" / digest)
                safe_path(self.root / "reports").mkdir(exist_ok=True)
                def before_publish(manifest, report):
                    _require(self._export_source_identity(project.status()) == identity
                             and project.status()["snapshot_ref"] == state["snapshot_ref"]
                             and host_model_snapshot_sha256(project.root) == host_identity
                             and manifest.get("project_id") == state["id"] and manifest.get("project_snapshot_ref") == state["snapshot_ref"]
                             and manifest.get("host_model_snapshot_sha256") == host_identity
                             and report.get("project") == state and report.get("exporter_code_identity") == identity["exporter_code_identity"],
                             "EVIDENCE_CHANGED", "The prepared report differs from its original source or project.")
                    if staged_parent is not None:
                        with self._connect(readonly=True) as staged_con:
                            row = staged_con.execute("SELECT digest,record FROM requests WHERE id=? AND command='continue_staged'", (staged_parent,)).fetchone()
                        _require(row is not None, "EVIDENCE_CHANGED", "The original staged parent disappeared.")
                        original = tabular._parse(row["record"].encode("utf-8"))
                        self._check_staged_continuation(original, row["digest"])
                        self._verify_staged_report_ready(original, project)
                        _require(original["phase"] == "report" and original["steps"]["report"]["body"] == body,
                                 "EVIDENCE_CHANGED", "The original staged report authorization changed.")
                    original_record = copy.deepcopy(record)
                    record["intent"]["prepared_manifest_sha256"] = hashlib.sha256(canonical(manifest).encode("utf-8")).hexdigest()
                    with self._connect() as publish_con:
                        updated = publish_con.execute("UPDATE requests SET record=? WHERE id=? AND digest=? AND record=?",
                            (canonical(record), body["request_id"], digest, canonical(original_record)))
                        _require(updated.rowcount == 1, "EVIDENCE_CHANGED", "The original report intent changed before publication.")
                manifest = export_report(workspace=project.root, output=output, before_publish=before_publish)
                _require(manifest["project_id"] == state["id"] and manifest["project_snapshot_ref"] == state["snapshot_ref"],
                         "STALE_STATE", "Project changed while exporting; the output was retained.")
                _require(hashlib.sha256(canonical(manifest).encode("utf-8")).hexdigest() == record["intent"].get("prepared_manifest_sha256"),
                         "EVIDENCE_CHANGED", "The published manifest differs from its original prepared identity.")
                self._verify_report(digest, manifest)
                _require(project.status()["snapshot_ref"] == state["snapshot_ref"]
                         and host_model_report_current(project.root, manifest)
                         and self._export_source_identity(project.status()) == identity,
                         "STALE_STATE", "Project or host-model requests changed before report publication; output was retained.")
                response = self._response("export", body["request_id"], state["id"], status="exported", manifest=manifest)
                record.update(status="completed", result=response)
                with self._connect() as con:
                    con.execute("UPDATE projects SET report=? WHERE id=?", (digest, state["id"]))
                    self._save(con, body["request_id"], record)
                return response
            except Exception as error:
                failed = copy.deepcopy(record)
                failed.update(status="incomplete", failure={"code": getattr(error, "code", "WORKBENCH_OPERATION_FAILED"), "automatic_retry": False})
                with self._connect() as failed_con:
                    failed_con.execute("UPDATE requests SET record=? WHERE id=? AND digest=? AND record=?",
                                       (canonical(failed), body["request_id"], digest, canonical(record)))
                if isinstance(error, ResearchError):
                    raise
                raise ResearchError("WORKBENCH_OPERATION_FAILED", "Report export stopped; its intent and partial output were retained.") from None
