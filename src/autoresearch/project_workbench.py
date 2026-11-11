"""Read-only domain projects, with optional matching sealed P02 evidence."""

import copy
import json
import hashlib
import socket
import re
import secrets
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

from . import research_methods, snapshot_viewer, method_registry
from .contracts import ResearchError, fingerprint, identifier
from .project_knowledge import POINTS
from .project_controller import ProjectController
from .project_selection import seal_context
from .project_selection_view import selection_view, read_selection_request
from .research_project import ResearchProject, safe_path
from .host_model_report import host_model_report_current
from .research_plan_proposal import build_context as build_plan_context

MAX_REPORT_FILE_BYTES = 64 * 1024 * 1024
MAX_REPORT_TOTAL_BYTES = 128 * 1024 * 1024
MAX_LOCAL_REQUEST_BYTES = 12 * 1024 * 1024
MAX_LOCAL_EVIDENCE_REQUEST_BYTES = 90 * 1024 * 1024
_RESTART_REQUIRED_MESSAGE = "Workbench code changed after startup; restart this service before previews or local commands."


def _runtime_sources():
    """Snapshot only project Python modules already imported when the server starts."""
    package = Path(__file__).resolve().parent
    paths = {Path(module.__file__).resolve() for name, module in tuple(sys.modules.items())
             if (name == "autoresearch" or name.startswith("autoresearch."))
             and isinstance(getattr(module, "__file__", None), str)}
    return {path: path.read_bytes() for path in paths if path.suffix == ".py" and path.is_relative_to(package)}


def _require_runtime_current(sources):
    try:
        unchanged = all(path.read_bytes() == original for path, original in sources.items())
    except OSError:
        unchanged = False
    _require(unchanged, "WORKBENCH_RESTART_REQUIRED", _RESTART_REQUIRED_MESSAGE)


def _local_body(raw):
    def unique(pairs):
        value = {}
        for key, item in pairs:
            if key in value:
                raise ValueError("duplicate JSON field")
            value[key] = item
        return value

    def invalid_constant(_):
        raise ValueError("nonfinite JSON value")

    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=unique, parse_constant=invalid_constant)
        _require(type(value) is dict, "INVALID_REQUEST", "Use a JSON command object.")
        return value
    except (UnicodeError, ValueError, RecursionError):
        raise ResearchError("INVALID_REQUEST", "Use bounded strict UTF-8 JSON without duplicate fields.") from None


def _require(condition, code, message):
    if not condition:
        raise ResearchError(code, message)


def _bound_state(project, iteration_snapshot):
    state = project.status()
    _require(iteration_snapshot is None or state.get("source_scope", {}).get("iteration_snapshot_sha256") == iteration_snapshot,
             "BUNDLE_PROJECT_MISMATCH", "Project and sealed iteration identities differ.")
    return state


def _binding(workspace, bundle):
    project = ResearchProject(workspace)
    if bundle is None:
        state = project.status()
        _require(method_registry.primary_id(state) != "p02.saved-oof-residuals", "MISSING_ITERATION",
                 "P02 still requires its matching sealed bundle.")
        project._source(state)
        return project, None, state
    files = snapshot_viewer.load_bundle(bundle)
    _require("data/iteration.json" in files, "MISSING_ITERATION", "A sealed iteration snapshot is required.")
    iteration = snapshot_viewer._json(files["data/iteration.json"])
    snapshot = iteration.get("snapshot_sha256")
    _require(type(snapshot) is str and snapshot == fingerprint(
        {key: value for key, value in iteration.items() if key != "snapshot_sha256"}),
        "EVIDENCE_CHANGED", "Sealed iteration identity is invalid.")
    return project, snapshot, _bound_state(project, snapshot)


def _public(value, project):
    """Keep internal host roots out of the projection, including saved error text."""
    if isinstance(value, dict):
        return {key: _public(item, project) for key, item in value.items()}
    if isinstance(value, list):
        return [_public(item, project) for item in value]
    if isinstance(value, str):
        for path, label in ((project.root, "[project]"), (Path(__file__).resolve().parents[2], "[application]")):
            for spelling in {str(path), path.as_posix()}:
                value = value.replace(spelling, label)
    return value


def _projection(project, state, report=None):
    view = {key: state.get(key) for key in (
        "id", "run_id", "snapshot_ref", "state_version", "research_status", "execution_status",
        "budget", "next_decision", "initial_decision", "actions", "evidence_actions", "knowledge_refs",
    )}
    capability = {"available": False, "stale": False}
    if report is not None:
        try:
            manifest = _report_manifest(report)
            capability["stale"] = (manifest["project_id"] != state["id"]
                                   or manifest["project_snapshot_ref"] != state["snapshot_ref"]
                                   or not host_model_report_current(project.root, manifest))
            if manifest["project_id"] == state["id"] and not capability["stale"]:
                for filename in manifest["files"]:
                    _report_bytes(report, manifest, filename)
                capability["available"] = True
        except (OSError, ValueError, ResearchError, KeyError):
            capability["error"] = "REPORT_UNAVAILABLE"
    registered = []
    for ordinal, source in enumerate(state.get("evidence_sources", []), 1):
        statuses = [item["status"] for item in state.get("evidence_actions", [])
                    if item.get("receipt_snapshot_sha256") == source["receipt_snapshot_sha256"]]
        status = ("unknown" if any(item in ("running", "pending", "unknown") for item in statuses)
                  else "failed" if "failed" in statuses else "completed" if "completed" in statuses else "unread")
        registered.append({"receipt_snapshot_sha256": source["receipt_snapshot_sha256"], "ordinal": ordinal,
                           "source_count": source["source_count"], "selection_count": source["selection_count"],
                           "read_status": status})
    view.update(schema_version="active-project-view-v1", goal=state["registration"]["goal"],
                primary_method=method_registry.primary_id(state), domain_scope=state["source_scope"], report=capability,
                selection_history=selection_view(state), registered_evidence=registered,
                method_options=research_methods.match_methods(state), scientific_validation=False)
    revisions = state.get("plan_revisions", [])
    view["research_plan"] = {"current": revisions[-1] if revisions else None, "revisions": revisions}
    view["recipe_revisions"] = copy.deepcopy(state.get("recipe_revisions", []))
    public_view = _public(view, project)
    public_view["researcher_feedback"] = copy.deepcopy(state.get("researcher_feedback", []))
    return public_view


def check_project_workbench(*, workspace, bundle=None, report=None):
    """Validate the exact binding without opening a socket or advancing the project."""
    project, snapshot, state = _binding(workspace, bundle)
    if report is not None:
        manifest = _report_manifest(report)
        _require(manifest["project_id"] == state["id"] and manifest["project_snapshot_ref"] == state["snapshot_ref"]
                 and host_model_report_current(project.root, manifest),
                 "REPORT_STALE", "Report is not bound to the current project and host-model snapshots.")
        for filename in manifest["files"]:
            _report_bytes(report, manifest, filename)
    return {"ok": True, "project_id": state["id"], "run_id": state["run_id"],
            "iteration_snapshot_sha256": snapshot, "state_version": state["state_version"],
            "mode": "read_only", "scientific_validation": False}


def _report_manifest(directory):
    root = safe_path(Path(directory).absolute())
    manifest = snapshot_viewer._json(snapshot_viewer._read(root / "manifest.json", 1_000_000))
    _require(manifest.get("schema_version") == "project-report-export-v1" and manifest.get("scientific_validation") is False
             and set(manifest.get("files", {})) == {"report.json", "report.md", "report.pdf", "input.json"},
             "EVIDENCE_CHANGED", "Current report manifest is invalid.")
    sizes = [entry.get("bytes") for entry in manifest["files"].values() if isinstance(entry, dict)]
    _require(len(sizes) == 4 and all(type(size) is int and 0 < size <= MAX_REPORT_FILE_BYTES for size in sizes)
             and sum(sizes) <= MAX_REPORT_TOTAL_BYTES,
             "REPORT_TOO_LARGE", "Current reports require at most 64 MiB per file and 128 MiB in total.")
    return manifest


def _report_bytes(directory, manifest, filename):
    _require(filename in manifest["files"], "ARTIFACT_NOT_FOUND", "Report file is not registered.")
    path = safe_path(Path(directory).absolute() / filename)
    raw = snapshot_viewer._read(path, MAX_REPORT_FILE_BYTES)
    identity = manifest["files"][filename]
    _require(len(raw) == identity["bytes"] and hashlib.sha256(raw).hexdigest() == identity["sha256"],
             "EVIDENCE_CHANGED", "Current report file changed.")
    return raw


class _ReadOnlyHandler(BaseHTTPRequestHandler):
    def log_message(self, *args): pass
    def host_ok(self):
        return self.headers.get_all("Host", []) in [[f"127.0.0.1:{self.server.server_port}"], [f"localhost:{self.server.server_port}"]]
    def send_data(self, status, body, mime, filename=None):
        self.send_response(status)
        for key, value in {"Content-Type": mime, "Content-Length": str(len(body)), "Cache-Control": "no-store",
                           "X-Content-Type-Options": "nosniff", "Referrer-Policy": "no-referrer",
                           "Content-Security-Policy": "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'"}.items():
            self.send_header(key, value)
        if filename: self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        self.end_headers(); self.wfile.write(body)
    def do_GET(self):
        self.send_data(404, b'{"code":"NOT_FOUND"}', "application/json")
    def deny(self):
        self.close_connection = True
        self.send_data(405 if self.host_ok() else 403, b'{"code":"READ_ONLY"}', "application/json")
    do_POST=do_PUT=do_PATCH=do_DELETE=do_OPTIONS=do_HEAD=do_TRACE=do_CONNECT=deny


class _ProjectServer(ThreadingHTTPServer):
    allow_reuse_address = False
    daemon_threads = True
    def server_bind(self):
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()


def _artifact(project, state, action_id):
    identifier(action_id, "action_id")
    action = next((item for item in state["actions"] + state["evidence_actions"]
                   if item["id"] == action_id), None)
    _require(action is not None, "ARTIFACT_NOT_FOUND", "No registered action matches this artifact.")
    _require(action["status"] == "completed", "ARTIFACT_NOT_AVAILABLE", "Action has no completed artifact.")
    relative = "artifacts/" + action_id + ".json"
    _require(action.get("artifact") == relative, "EVIDENCE_CHANGED", "Registered artifact reference differs.")
    path = safe_path(project.root / "artifacts" / (action_id + ".json"))
    raw = snapshot_viewer._read(path, snapshot_viewer.MAX_FILE)
    envelope = snapshot_viewer._json(raw)
    _require(envelope.get("sha256") == action["result_sha256"]
             and envelope["sha256"] == fingerprint({key: value for key, value in envelope.items() if key != "sha256"})
             and envelope["action_id"] == action_id
             and envelope["request_sha256"] == action["request_sha256"]
             and envelope["code_identity"] == action["code_identity"]
             and envelope["source_snapshot_sha256"] == action["source_snapshot_sha256"]
             and envelope["tool_result"]["status"] == "completed",
             "EVIDENCE_CHANGED", "Completed artifact identity differs from the registered result.")
    return raw


def _knowledge_query(query):
    try:
        values = parse_qs(query, keep_blank_values=True, strict_parsing=True, max_num_fields=3)
        _require(set(values) <= {"need", "point", "limit"} and "need" in values
                 and all(len(items) == 1 for items in values.values()),
                 "INVALID_QUERY", "Use one need, optional decision point and limit only.")
        need = values["need"][0]
        point = values.get("point", ["interpretation"])[0]
        limit = int(values.get("limit", ["5"])[0])
        _require(1 <= len(need.strip()) <= 512 and point in POINTS and 1 <= limit <= 8,
                 "INVALID_QUERY", "Knowledge needs 1..512 characters, a decision point and limit 1..8.")
        return {"need": need, "point": point, "limit": limit}
    except ValueError:
        raise ResearchError("INVALID_QUERY", "Invalid project knowledge query.") from None


def _registered_receipt(project, state, receipt_sha):
    _require(re.fullmatch(r"[a-f0-9]{64}", receipt_sha) is not None,
             "INVALID_REQUEST", "Use a complete registered receipt identity.")
    source = next((item for item in state.get("evidence_sources", [])
                   if item["receipt_snapshot_sha256"] == receipt_sha), None)
    _require(source is not None, "ARTIFACT_NOT_FOUND", "Receipt is not registered in this project.")
    receipt, assets, _ = project._load_evidence_input(
        state, receipt_sha, input_receipt=source.get("input_receipt"), task_ref=source.get("task_ref"))
    return receipt, assets


def _evidence_task_view(project, before):
    task = project.evidence_task()
    # An unread source proposal temporarily replaces the displayed next task.
    # Preserve the last analysis requirements for display, without rebinding it.
    if not task["required_evidence"]:
        primary = method_registry.primary_id(before)
        latest = next((item for item in reversed(before.get("actions", []))
                       if item.get("status") == "completed"
                       and item.get("command") in {primary, *method_registry.followup_ids(primary)}), None)
        saved = ((latest or {}).get("next_decision") or {}).get("next_action", {})
        if saved.get("kind") == "evidence_task":
            task["required_evidence"] = saved.get("required_evidence", [])
            task["requirements_from_action_id"] = latest["id"]
    after = project.status()
    _require(before["snapshot_ref"] == after["snapshot_ref"] and task["state_version"] == before["state_version"],
             "STALE_STATE", "Project changed while preparing its evidence task.")
    return {**task, "schema_version": "local-evidence-task-view-v1", "project_id": before["id"],
            "snapshot_ref": before["snapshot_ref"], "scientific_validation": False}


def create_project_server(*, workspace=None, bundle=None, report=None, port=18785,
                          local_workspace=None, allow_local_actions=False, claude_executable=None):
    _require(type(port) is int and 0 <= port <= 65535, "INVALID_PORT", "Use a local port from 0 to 65535.")
    _require(type(allow_local_actions) is bool and (not allow_local_actions or local_workspace is not None),
             "INVALID_REQUEST", "Local actions require an explicit local workspace.")
    _require(claude_executable is None or (allow_local_actions and local_workspace is not None
             and isinstance(claude_executable, (str, Path)) and Path(claude_executable).is_file()),
             "INVALID_REQUEST", "A host-selected existing Claude executable requires enabled local actions.")
    if claude_executable is not None:
        claude_executable = str(Path(claude_executable).absolute())
    if local_workspace is None:
        project, iteration_snapshot, state = _binding(workspace, bundle)
        if report is not None:
            check_project_workbench(workspace=workspace, bundle=bundle, report=report)
    else:
        _require(workspace is None and bundle is None and report is None, "INVALID_REQUEST",
                 "Local intake uses its own managed projects; sealed or external projects stay read-only.")
        project, iteration_snapshot = None, None
    runtime_sources = _runtime_sources()
    csrf_token = secrets.token_urlsafe(32) if allow_local_actions else None

    def binding():
        if local_workspace is None:
            return project, iteration_snapshot, report
        selected, current_report = local_workspace.binding()
        _require(selected is not None, "PROJECT_NOT_FOUND", "Create or select a local project first.")
        return selected, None, current_report
    # Reuse the viewer's validated frozen routes, exclusive bind and method denial.
    server = snapshot_viewer.create_server(bundle, port) if bundle is not None else _ProjectServer(("127.0.0.1", port), _ReadOnlyHandler)
    parent = server.RequestHandlerClass
    web_root = Path(__file__).resolve().parent / "web"
    web_routes = {"/": ("index.html", "text/html; charset=utf-8"),
                  "/app.js": ("app.js", "text/javascript; charset=utf-8"),
                  "/app.css": ("app.css", "text/css; charset=utf-8")}

    class ProjectHandler(parent):
        def send_json(self, status, value, filename=None):
            self.send_data(status, json.dumps(value, ensure_ascii=False, allow_nan=False,
                                             separators=(",", ":")).encode("utf-8"),
                           "application/json; charset=utf-8", filename)

        def project_error(self, status, code, message):
            # Closing with unread, bounded request bytes can reset the connection on Windows.
            lengths = self.headers.get_all("Content-Length", [])
            framed = (self.command in ("POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD", "TRACE", "CONNECT")
                      and not getattr(self, "_request_body_read", False)
                      and self.headers.get_all("Transfer-Encoding", []) == []
                      and self.headers.get_all("Content-Encoding", []) == []
                      and len(lengths) == 1 and re.fullmatch(r"[0-9]{1,9}", lengths[0]) is not None)
            if framed:
                length = int(lengths[0])
                limit = MAX_LOCAL_EVIDENCE_REQUEST_BYTES if urlsplit(self.path).path == "/api/local-workbench/evidence" else MAX_LOCAL_REQUEST_BYTES
                if 0 < length <= limit:
                    self._request_body_read = True
                    self.connection.settimeout(10)
                    try:
                        self.rfile.read(length)
                    except OSError:
                        pass
            self.send_json(status, {"ok": False, "code": code, "message": message})

        def deny(self):
            self._request_body_read = False
            self.close_connection = True
            return self.project_error(405 if self.host_ok() else 403, "READ_ONLY", "This method is not enabled for this service.")

        do_PUT = do_PATCH = do_DELETE = do_OPTIONS = do_HEAD = do_TRACE = do_CONNECT = deny

        def do_POST(self):
            self._request_body_read = False
            if not self.host_ok():
                self.close_connection = True
                return self.project_error(403, "HOST_NOT_ALLOWED", "Only the bound local Host is accepted.")
            if local_workspace is None or not allow_local_actions:
                self.close_connection = True
                return self.project_error(405, "READ_ONLY", "Local actions were not enabled for this service.")
            try:
                origin = "http://" + self.headers["Host"]
                tokens = self.headers.get_all("X-AutoResearch-CSRF", [])
                _require(self.headers.get_all("Origin", []) == [origin]
                         and len(tokens) == 1 and secrets.compare_digest(tokens[0].encode("utf-8"), csrf_token.encode("ascii"))
                         and self.headers.get_all("Sec-Fetch-Site", []) in ([], ["same-origin"]),
                         "LOCAL_ORIGIN_REQUIRED", "Use the current local page and its session token.")
                parsed = urlsplit(self.path)
                commands = {"/api/local-workbench/create": "create", "/api/local-workbench/select": "select",
                            "/api/local-workbench/design-bind": "bind_design",
                            "/api/local-workbench/design-improve": "improve_design",
                            "/api/local-workbench/design-import": "import_design",
                            "/api/local-workbench/plan": "save_plan",
                            "/api/local-workbench/feedback": "record_feedback",
                            "/api/local-workbench/experience-import": "import_experience",
                            "/api/local-workbench/experience-status": "set_experience_status",
                            "/api/local-workbench/experience-resume": "resume_experience",
                            "/api/local-workbench/advance": "advance", "/api/local-workbench/report": "export",
                            "/api/local-workbench/advance-recipe": "advance_recipe",
                            "/api/local-workbench/recipe-preview": "preview_recipe_round",
                            "/api/local-workbench/plan-fact-check": "check_plan_fact",
                            "/api/local-workbench/recipe-adopt": "adopt_recipe_round",
                            "/api/local-workbench/evidence": "register_evidence", "/api/local-workbench/batch": "batch",
                            "/api/local-workbench/continue": "continue_research",
                            "/api/local-workbench/model-advance": "model_advance", "/api/local-workbench/model-resume": "model_resume",
                            "/api/local-workbench/model-plan-advance": "model_plan_advance",
                            "/api/local-workbench/model-plan-adopt": "model_plan_adopt",
                            "/api/local-workbench/model-plan-reject": "model_plan_reject"}
                _require(not parsed.scheme and not parsed.netloc and not parsed.query and not parsed.fragment
                         and parsed.path in commands, "INVALID_REQUEST", "Select a supported local command route.")
                _require_runtime_current(runtime_sources)
                _require(self.headers.get_all("Transfer-Encoding", []) == []
                         and self.headers.get_all("Content-Encoding", []) == []
                         and len(self.headers.get_all("Content-Type", [])) == 1
                         and self.headers["Content-Type"].lower() in ("application/json", "application/json; charset=utf-8"),
                         "INVALID_REQUEST", "Local commands accept uncompressed JSON with a bounded content length.")
                lengths = self.headers.get_all("Content-Length", [])
                _require(len(lengths) == 1 and re.fullmatch(r"[0-9]{1,9}", lengths[0]) is not None,
                         "INVALID_REQUEST", "One bounded content length is required.")
                length = int(lengths[0])
                limit = MAX_LOCAL_EVIDENCE_REQUEST_BYTES if parsed.path == "/api/local-workbench/evidence" else MAX_LOCAL_REQUEST_BYTES
                _require(0 < length <= limit, "INPUT_TOO_LARGE", "Local request exceeds the input limit.")
                self.connection.settimeout(10)
                self._request_body_read = True
                raw = self.rfile.read(length)
                _require(len(raw) == length, "INVALID_REQUEST", "The complete request body was not received.")
                body = _local_body(raw)
                command = commands[parsed.path]
                if command in ("model_advance", "model_plan_advance"):
                    _require(claude_executable is not None, "MODEL_DISABLED", "Host model selection was not enabled.")
                    result = getattr(local_workspace, command)(body, executable=claude_executable)
                elif command in ("continue_research", "model_resume"):
                    result = getattr(local_workspace, command)(body, executable=claude_executable)
                else:
                    result = getattr(local_workspace, command)(body)
                return self.send_json(200, result)
            except ResearchError as error:
                self.close_connection = True
                status = (405 if error.code == "MODEL_DISABLED" else 403 if error.code == "LOCAL_ORIGIN_REQUIRED" else 413 if error.code in {"INPUT_TOO_LARGE", "SOURCE_TOO_LARGE"}
                          else 409 if error.code in {"STALE_STATE", "STALE_SELECTION_CONTEXT", "STALE_ACTIVE_PROJECT", "PROJECT_BUSY",
                              "EXECUTION_UNKNOWN", "BUDGET_EXHAUSTED", "CODE_CHANGED", "CONFIG_CHANGED", "IDEMPOTENCY_CONFLICT",
                              "CONDITION_NOT_SATISFIED", "INTAKE_INCOMPLETE", "REPORT_INCOMPLETE", "OPERATION_INCOMPLETE", "PROJECT_LIMIT",
                              "HOST_GRANT_CHANGED", "HOST_DECISION_LIMIT", "HOST_SELECTION_PENDING", "HOST_USAGE_UNKNOWN",
                              "HOST_CLI_BUDGET_EXHAUSTED", "NO_HOST_CANDIDATES", "WORKBENCH_RESTART_REQUIRED"} else 400)
                return self.project_error(status, error.code, _RESTART_REQUIRED_MESSAGE if error.code == "WORKBENCH_RESTART_REQUIRED"
                                          else "Local command rejected; saved inputs and execution history were preserved.")
            except (TimeoutError, ConnectionError):
                self.close_connection = True
                return self.project_error(408, "INCOMPLETE_REQUEST", "The bounded local request was not completed.")
            except Exception:
                self.close_connection = True
                return self.project_error(500, "LOCAL_COMMAND_FAILED", "Local command could not be completed; inspect its saved request before retrying.")

        def do_GET(self):
            if not self.host_ok():
                return self.project_error(403, "HOST_NOT_ALLOWED", "Only the bound local Host is accepted.")
            try:
                parsed = urlsplit(self.path)
                _require(not parsed.scheme and not parsed.netloc and not parsed.fragment,
                         "INVALID_QUERY", "Use a relative local request path.")
                if parsed.path in {"/api/project/selection-context.json", "/api/project/plan-context.json", "/api/local-workbench/recipes", "/api/local-workbench/designs", "/api/local-workbench/experiences", "/api/project/knowledge"}:
                    _require_runtime_current(runtime_sources)
                if parsed.path == "/favicon.ico" and not parsed.query:
                    return self.send_data(204, b"", "image/x-icon")
                if parsed.path in web_routes:
                    _require(not parsed.query, "INVALID_QUERY", "Static project assets do not accept a query.")
                    name, mime = web_routes[parsed.path]
                    raw = snapshot_viewer._read(web_root / name, snapshot_viewer.MAX_FILE)
                    if name == "index.html":
                        _require(b"<body>" in raw, "INVALID_WEB_ASSET", "Current workbench entrypoint is invalid.")
                        kind = b"local-workbench" if local_workspace is not None else b"p02" if bundle is not None else b"project"
                        raw = raw.replace(b"<body>", b'<body data-case="'+kind+b'" data-active-project="true">', 1)
                    return self.send_data(200, raw, mime)
                if parsed.path == "/api/local-workbench" and local_workspace is not None:
                    _require(not parsed.query, "INVALID_QUERY", "Workspace metadata does not accept a query.")
                    return self.send_json(200, {**local_workspace.describe(), "enabled": allow_local_actions, "csrf_token": csrf_token})
                if parsed.path == "/api/local-workbench/model" and local_workspace is not None:
                    _require(not parsed.query, "INVALID_QUERY", "Model journal does not accept a query.")
                    return self.send_json(200, local_workspace.model_view(enabled=claude_executable is not None))
                if parsed.path == "/api/local-workbench/recipes" and local_workspace is not None:
                    _require(not parsed.query, "INVALID_QUERY", "Recipe previews do not accept a query.")
                    return self.send_json(200, local_workspace.recipes())
                if parsed.path == "/api/local-workbench/designs" and local_workspace is not None:
                    _require(not parsed.query, "INVALID_QUERY", "Research designs do not accept a query.")
                    return self.send_json(200, local_workspace.designs())
                if parsed.path == "/api/local-workbench/experiences" and local_workspace is not None:
                    _require(not parsed.query, "INVALID_QUERY", "Historical method cases do not accept a query.")
                    return self.send_json(200, local_workspace.experiences())
                if parsed.path.startswith("/api/local-workbench/batch/") and local_workspace is not None:
                    _require(not parsed.query and parsed.path.endswith(".json"), "INVALID_QUERY", "Use one saved batch JSON identifier.")
                    encoded = parsed.path.removeprefix("/api/local-workbench/batch/")[:-5]
                    try:
                        request_id = unquote(encoded, encoding="utf-8", errors="strict")
                    except UnicodeError:
                        raise ResearchError("INVALID_REQUEST", "Invalid batch identifier encoding.") from None
                    identifier(request_id)
                    return self.send_json(200, local_workspace.batch_record(request_id), request_id + ".json")
                if parsed.path.startswith("/api/local-workbench/continue/") and local_workspace is not None:
                    _require(not parsed.query and parsed.path.endswith(".json"), "INVALID_QUERY", "Use one saved continuation JSON identifier.")
                    encoded = parsed.path.removeprefix("/api/local-workbench/continue/")[:-5]
                    try:
                        request_id = unquote(encoded, encoding="utf-8", errors="strict")
                    except UnicodeError:
                        raise ResearchError("INVALID_REQUEST", "Invalid continuation identifier encoding.") from None
                    identifier(request_id)
                    return self.send_json(200, local_workspace.continuation_record(request_id), request_id + ".json")
                project, iteration_snapshot, report = binding()
                if parsed.path == "/api/project":
                    _require(not parsed.query, "INVALID_QUERY", "Project status does not accept a query.")
                    state = _bound_state(project, iteration_snapshot)
                    return self.send_json(200, _projection(project, state, report))
                if parsed.path == "/api/project/evidence-task.json":
                    _require(not parsed.query, "INVALID_QUERY", "Evidence task does not accept a query.")
                    state = _bound_state(project, iteration_snapshot)
                    return self.send_json(200, _evidence_task_view(project, state))
                if parsed.path.startswith("/api/project/evidence-receipt/"):
                    _require(not parsed.query and parsed.path.endswith(".json"), "INVALID_QUERY", "Use one receipt JSON identity.")
                    receipt_sha = parsed.path.removeprefix("/api/project/evidence-receipt/")[:-5]
                    state = _bound_state(project, iteration_snapshot)
                    receipt, _ = _registered_receipt(project, state, receipt_sha)
                    return self.send_json(200, receipt, "evidence-receipt-" + receipt_sha + ".json")
                if parsed.path.startswith("/api/project/evidence-source/"):
                    parts = parsed.path.removeprefix("/api/project/evidence-source/").split("/")
                    _require(not parsed.query and len(parts) == 2, "INVALID_QUERY", "Use a receipt identity and source identifier.")
                    try:
                        source_id = unquote(parts[1], encoding="utf-8", errors="strict")
                    except UnicodeError:
                        raise ResearchError("INVALID_REQUEST", "Invalid source identifier encoding.") from None
                    identifier(source_id, "source_id")
                    state = _bound_state(project, iteration_snapshot)
                    receipt, assets = _registered_receipt(project, state, parts[0])
                    source = next((item for item in receipt["sources"] if item["id"] == source_id), None)
                    _require(source is not None, "ARTIFACT_NOT_FOUND", "Source is not registered in this receipt.")
                    extension = {"application/pdf": ".pdf", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
                                 "text/plain": ".txt", "text/markdown": ".md", "text/html": ".html", "application/json": ".json",
                                 "text/csv": ".csv", "text/tab-separated-values": ".tsv"}.get(source["media_type"], ".bin")
                    return self.send_data(200, assets[source_id], "application/octet-stream", source_id + extension)
                if parsed.path == "/api/project/plan-context.json":
                    _require(not parsed.query, "INVALID_QUERY", "Read the current saved plan and feedback context.")
                    _bound_state(project, iteration_snapshot)
                    return self.send_json(200, build_plan_context(project), "plan-context.json")
                if parsed.path == "/api/project/selection-context.json":
                    try:
                        values = parse_qs(parsed.query, keep_blank_values=True, strict_parsing=True, max_num_fields=1)
                    except ValueError:
                        raise ResearchError("INVALID_QUERY", "Use at most one snapshot_ref.") from None
                    _require(not values or (set(values) == {"snapshot_ref"} and len(values["snapshot_ref"]) == 1
                             and re.fullmatch(r"[a-f0-9]{64}", values["snapshot_ref"][0]) is not None),
                             "INVALID_QUERY", "Use one full project snapshot identity.")
                    before = _bound_state(project, iteration_snapshot)
                    expected = values.get("snapshot_ref", [before["snapshot_ref"]])[0]
                    _require(expected == before["snapshot_ref"], "STALE_STATE", "Project snapshot changed.")
                    context = ProjectController(project.root).selection_context()
                    _require(seal_context({key: value for key, value in context.items() if key != "context_sha256"}) == context,
                             "EVIDENCE_CHANGED", "Selection context identity changed.")
                    after = _bound_state(project, iteration_snapshot)
                    _require(context["snapshot_ref"] == before["snapshot_ref"] == after["snapshot_ref"]
                             and context["project_id"] == before["id"] and context["run_id"] == before["run_id"]
                             and context["state_version"] == before["state_version"]
                             and context["source_snapshot_sha256"] == before["source_snapshot_sha256"]
                             and context["project_code_identity"] == before["code_identity"],
                             "STALE_STATE", "Project changed while preparing selection context.")
                    return self.send_json(200, context, "selection-context.json")
                if parsed.path.startswith("/api/project/selection-request/"):
                    _require(not parsed.query and parsed.path.endswith(".json"), "INVALID_QUERY", "Use one saved selection JSON identifier.")
                    encoded = parsed.path.removeprefix("/api/project/selection-request/")[:-5]
                    try:
                        request_id = unquote(encoded, encoding="utf-8", errors="strict")
                    except UnicodeError:
                        raise ResearchError("INVALID_REQUEST", "Invalid request identifier encoding.") from None
                    identifier(request_id)
                    state = _bound_state(project, iteration_snapshot)
                    return self.send_json(200, read_selection_request(state, request_id), request_id + ".json")
                if parsed.path in {"/api/project/report.pdf", "/api/project/report.json", "/api/project/report.md", "/api/project/input.json"}:
                    _require(not parsed.query, "INVALID_QUERY", "Report downloads do not accept a query.")
                    _require(report is not None, "ARTIFACT_NOT_FOUND", "No current report is mounted.")
                    state = _bound_state(project, iteration_snapshot)
                    manifest = _report_manifest(report)
                    _require(manifest["project_id"] == state["id"] and manifest["project_snapshot_ref"] == state["snapshot_ref"]
                             and host_model_report_current(project.root, manifest),
                             "REPORT_STALE", "The mounted report is not current.")
                    filename = parsed.path.rsplit("/", 1)[-1]
                    mime = "application/pdf" if filename.endswith(".pdf") else "text/markdown; charset=utf-8" if filename.endswith(".md") else "application/json; charset=utf-8"
                    return self.send_data(200, _report_bytes(report, manifest, filename), mime, filename)
                if parsed.path == "/api/project/knowledge":
                    query = _knowledge_query(parsed.query)
                    _bound_state(project, iteration_snapshot)
                    return self.send_json(200, _public(project.knowledge(**query), project))
                if parsed.path.startswith("/api/project/artifact/"):
                    _require(not parsed.query, "INVALID_QUERY", "Artifact downloads do not accept a query.")
                    action_id = parsed.path.removeprefix("/api/project/artifact/")
                    state = _bound_state(project, iteration_snapshot)
                    raw = _artifact(project, state, action_id)
                    return self.send_data(200, raw, "application/json; charset=utf-8", action_id + ".json")
                if parsed.path.startswith("/api/project"):
                    return self.project_error(404, "PROJECT_ROUTE_NOT_FOUND", "Unknown read-only project route.")
                return super().do_GET()
            except ResearchError as error:
                status = (409 if error.code in {"REPORT_STALE", "STALE_STATE", "TASK_NOT_AVAILABLE", "WORKBENCH_RESTART_REQUIRED"} else 400 if error.code in {"INVALID_QUERY", "INVALID_REQUEST"}
                          else 404 if error.code in {"ARTIFACT_NOT_FOUND", "ARTIFACT_NOT_AVAILABLE", "PROJECT_NOT_FOUND"} else 500)
                # Error messages are fixed here; an OS/SQL exception never exposes local paths.
                return self.project_error(status, error.code,
                                          _RESTART_REQUIRED_MESSAGE if error.code == "WORKBENCH_RESTART_REQUIRED" else
                                          "Project query rejected." if status < 500 else "Bound project data could not be read or verified.")
            except Exception:
                return self.project_error(500, "PROJECT_READ_FAILED", "Project data or current web assets could not be read or verified.")

    server.RequestHandlerClass = ProjectHandler
    return server
