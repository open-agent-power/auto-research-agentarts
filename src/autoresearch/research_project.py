"""One durable local project slice; no model transport or historical ledger writes."""
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import uuid

from . import saved_oof_adapter as adapter
from . import source_evidence_adapter as source_adapter, research_methods as methods, project_knowledge
from . import method_registry as registry
from .contracts import ResearchError, canonical, fingerprint, identifier


def require(condition, code, message):
    if not condition:
        raise ResearchError(code, message)


def _source_metadata(receipt):
    return [{key: source[key] for key in ("id", "sha256", "media_type")} for source in receipt["sources"]]


def code_identity():
    from . import project_model_protocol
    return fingerprint({"application": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                        "registry": registry.code_identity(), "sources": source_adapter.code_identity(),
                        "methods": hashlib.sha256(Path(methods.__file__).read_bytes()).hexdigest(),
                        "knowledge": project_knowledge.code_identity(),
                        "local_model_protocol": hashlib.sha256(Path(project_model_protocol.__file__).read_bytes()).hexdigest()})


def safe_path(path):
    for part in (path, *path.parents):
        require(not part.is_symlink() and not getattr(part, "is_junction", lambda: False)(),
                "UNSAFE_PATH", "Project paths must not redirect through links.")
    return path


def write_once(path, value):
    """Flush a complete artifact before its atomic publication; never replace evidence."""
    raw = canonical(value).encode("utf-8")
    temporary = safe_path(path.with_suffix(".pending"))
    safe_path(path)
    with temporary.open("wb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    require(not path.exists(), "EVIDENCE_CHANGED", "Result artifact already exists.")
    temporary.replace(path)


def write_bytes_once(path, raw):
    """Publish a complete captured asset; a crash cannot publish a partial final file."""
    safe_path(path)
    if path.exists():
        require(source_adapter._read_file(path, source_adapter.MAX_SOURCE_BYTES) == raw,
                "EVIDENCE_CHANGED", "Captured asset differs from the registered original.")
        return
    temporary = safe_path(path.with_name(path.name + ".pending-" + uuid.uuid4().hex))
    with temporary.open("xb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    require(not path.exists(), "EVIDENCE_CHANGED", "Captured asset appeared before publication.")
    temporary.rename(path)


class ResearchProject:
    def __init__(self, workspace):
        self.root = safe_path(Path(workspace).absolute())
        self.db = self.root / "project.sqlite"

    @contextmanager
    def _connect(self, readonly=False):
        safe_path(self.db)
        require(self.db.is_file(), "PROJECT_NOT_FOUND", "Create the project first.")
        con = sqlite3.connect(self.db.as_uri() + ("?mode=ro" if readonly else "?mode=rw"), uri=True, timeout=5)
        con.row_factory = sqlite3.Row
        try:
            with con:
                yield con
        finally:
            con.close()

    @contextmanager
    def _writer(self):
        """OS lock releases on exit/crash; another process cannot mistake live work for unknown."""
        require(self.root.is_dir(), "PROJECT_NOT_FOUND", "Create the project first.")
        with safe_path(self.root / "writer.lock").open("a+b") as stream:
            stream.seek(0, 2)
            if stream.tell() == 0:
                stream.write(b"0")
                stream.flush()
            stream.seek(0)
            try:
                if os.name == "nt":
                    import msvcrt
                    msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError as exc:
                raise ResearchError("PROJECT_BUSY", "Another process is advancing this project.") from exc
            try:
                yield
            finally:
                stream.seek(0)
                if os.name == "nt":
                    msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(stream, fcntl.LOCK_UN)

    @staticmethod
    def _project(con):
        row = con.execute("SELECT record FROM project WHERE id=1").fetchone()
        require(row is not None, "INCOMPLETE_PROJECT", "Project registration did not complete.")
        return json.loads(row[0])

    @staticmethod
    def _save(con, project):
        con.execute("UPDATE project SET record=? WHERE id=1", (canonical(project),))

    def create(self, *, source, goal, budget_ref, max_tool_calls=1, method_id=adapter.TOOL_ID):
        primary = registry.get(method_id)
        require(isinstance(goal, str) and 0 < len(goal.strip()) <= 4000,
                "INVALID_REQUEST", "A bounded research goal is required.")
        require(isinstance(budget_ref, str) and 0 < len(budget_ref.strip()) <= 500,
                "INVALID_REQUEST", "An existing budget lineage reference is required.")
        require(type(max_tool_calls) is int and 1 <= max_tool_calls <= 2,
                "INVALID_REQUEST", "Local verification allowance must be 1 or 2 calls.")
        origin = safe_path(Path(source).absolute())
        require(origin.is_file(), "MISSING_SOURCE", "Obtain the sealed source package first.")
        require(not self.root.is_relative_to(origin.parent) and not origin.is_relative_to(self.root),
                "SOURCE_OVERLAP", "Use a workspace separate from the sealed source directory.")
        require(origin.stat().st_size <= 16_000_000, "INVALID_SOURCE", "Source exceeds the slice size limit.")
        raw = origin.read_bytes()
        payload = primary.load_source(raw)
        registration = {"goal": goal, "budget_ref": budget_ref, "max_tool_calls": max_tool_calls,
                        "source_sha256": hashlib.sha256(raw).hexdigest(), "method_id": method_id}
        if self.db.exists():
            current = self.status()
            previous = dict(current["registration"])
            previous.setdefault("method_id", adapter.TOOL_ID)
            require(previous == registration, "CONFIG_CHANGED", "Project configuration is immutable.")
            return current
        require(not self.root.exists(), "WORKSPACE_EXISTS", "Choose a new, separate workspace.")
        self.root.mkdir(parents=True)
        with (self.root / "source.json").open("xb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        (self.root / "artifacts").mkdir()
        project_id = "project-" + uuid.uuid4().hex
        source_method = registry.LEGACY_SOURCE if method_id == adapter.TOOL_ID else registry.SOURCE
        project = {"schema_version": "local-research-project-v3", "id": project_id,
                   "run_id": "run-" + uuid.uuid4().hex, "state_version": 0,
                   "research_status": "active", "execution_status": "ready", "registration": registration,
                   "source_snapshot_sha256": payload["snapshot_sha256"], "source_scope": payload["scope"],
                   "code_identity": code_identity(), "policy_ref": {"id": "local.condition-adaptive", "version": "1",
                                                                    "next_check_priority": "residual_first"},
                   "supported_methods": [{"id": method_id, "version": primary.ADAPTER_VERSION,
                                          "condition": "satisfied", "scope": payload["scope"]},
                                         {"id": source_method, "version": source_adapter.ADAPTER_VERSION,
                                          "condition": "uncertain", "scope": "task-bound source selections"}],
                   "initial_decision": {"method_id": method_id, "execution_status": "not_executed",
                                        "reason": "Execute the registered method only within its validated domain input and evaluation scope."},
                   "next_decision": None, "evidence_purpose": "isolated_adapter_regression_not_new_research",
                   "evidence_sources": [], "evidence_registrations": [], "knowledge_refs": [], "code_revisions": [],
                   "budget": {"lineage_ref": budget_ref, "historical_spend_cny": None,
                              "historical_request_counts": None, "historical_unknowns_resolved": False,
                              "cash_settlement": "unknown", "existing_cash_cap_cny": 5,
                              "model_requests_allowed": 0, "new_model_requests": 0, "model_requests_reserved": 0, "new_fits": 0,
                              "local_tool_call_limit": max_tool_calls, "evidence_read_limit": 8}}
        if method_id == "data.tabular-quality-audit":
            project["source_provenance"] = dict(payload["spec"]["provenance"])
        project["supported_methods"].extend({"id": method, "version": registry.get_analysis(method).ADAPTER_VERSION,
                                             "condition": "uncertain", "scope": payload["scope"]}
                                            for method in registry.followup_ids(method_id))
        con = sqlite3.connect(self.db)
        try:
            with con:
                con.executescript("CREATE TABLE project(id INTEGER PRIMARY KEY, record TEXT NOT NULL);"
                                  "CREATE TABLE actions(request_id TEXT PRIMARY KEY, fingerprint TEXT NOT NULL, record TEXT NOT NULL);"
                                  "CREATE TABLE replays(request_id TEXT PRIMARY KEY, action_request_id TEXT NOT NULL);")
                con.execute("INSERT INTO project VALUES(1,?)", (canonical(project),))
        finally:
            con.close()
        return self.status()

    def status(self):
        """Read persisted facts only; never perform recovery, compute or create a missing DB."""
        with self._connect(readonly=True) as con:
            con.execute("BEGIN")
            project = self._project(con)
            actions = [json.loads(row[0]) for row in con.execute("SELECT record FROM actions ORDER BY rowid")]
        numerical = [a for a in actions if not registry.is_source(a["command"])]
        sources = [a for a in actions if registry.is_source(a["command"])]
        project["actions"], project["evidence_actions"] = numerical, sources
        project["budget"].update(local_tool_calls_used=sum(a["status"] in ("completed", "failed") for a in numerical),
                                 local_tool_calls_reserved=sum(a["status"] in ("running", "unknown") for a in numerical),
                                 local_tool_dispatches=len(numerical),
                                 evidence_reads_used=sum(a["status"] in ("completed", "failed") for a in sources),
                                 evidence_reads_reserved=sum(a["status"] in ("running", "unknown") for a in sources))
        project["snapshot_ref"] = fingerprint(project)
        return project

    def _source(self, project):
        raw = safe_path(self.root / "source.json").read_bytes()
        require(hashlib.sha256(raw).hexdigest() == project["registration"]["source_sha256"],
                "EVIDENCE_CHANGED", "Registered source bytes changed.")
        return registry.get(registry.primary_id(project)).load_source(raw)

    def _artifact(self, action):
        return safe_path(self.root / "artifacts" / (action["id"] + ".json"))

    @staticmethod
    def _action(con, request_id):
        row = con.execute("SELECT record FROM actions WHERE request_id=?", (request_id,)).fetchone()
        if row is None:
            row = con.execute("SELECT a.record FROM replays r JOIN actions a ON a.request_id=r.action_request_id "
                              "WHERE r.request_id=?", (request_id,)).fetchone()
        return json.loads(row[0]) if row else None

    @staticmethod
    def _require_unclaimed(project, request_id, *, except_collection=None):
        for collection in ("code_revisions", "budget_revisions", "model_budget_revisions", "local_model_requests", "evidence_registrations", "controller_requests", "source_requests"):
            if collection != except_collection:
                require(not any(record["request_id"] == request_id for record in project.get(collection, [])),
                        "IDEMPOTENCY_CONFLICT", "Request ID belongs to another persisted command.")

    @staticmethod
    def _require_fresh(project, current, expected_state_version):
        require(expected_state_version is None or (type(expected_state_version) is int
                and expected_state_version == project["state_version"]), "STALE_STATE", "Project state changed.")
        require(project["code_identity"] == code_identity(), "CODE_CHANGED", "Explicitly upgrade this project first.")
        require(not any(action["status"] in ("running", "pending", "unknown")
                        for action in current["actions"] + current["evidence_actions"])
                and not any(item["status"] in ("sending", "unknown") for item in project.get("source_requests", [])),
                "EXECUTION_UNKNOWN", "Recover the original operation before accepting new work.")

    def _commit_result(self, action, envelope):
        require(envelope.get("sha256") == fingerprint({k: v for k, v in envelope.items() if k != "sha256"})
                and envelope["action_id"] == action["id"]
                and envelope["request_sha256"] == action["request_sha256"]
                and envelope["code_identity"] == action["code_identity"]
                and envelope["source_snapshot_sha256"] == action["source_snapshot_sha256"],
                "EVIDENCE_CHANGED", "Saved result identity differs from the accepted execution.")
        result = envelope["tool_result"]
        require(result.get("status") == "completed", "INVALID_RESULT", "Adapter did not complete.")
        observations = result["observations"]
        refs = [action["id"] + ":observation:" + str(i) for i in range(len(observations))]
        action.update(status="completed", result_sha256=envelope["sha256"],
                      artifact="artifacts/" + self._artifact(action).name,
                      observations=[dict(value, id=ref, action_id=action["id"]) for value, ref in zip(observations, refs)],
                      failure=None)
        knowledge_ref = None
        if registry.is_source(action["command"]):
            safe_path(self.root / "knowledge" / action["id"])
            knowledge_ref = project_knowledge.build(self.root, action, result)
            preview = self.status()
            preview["evidence_actions"] = [a for a in preview["evidence_actions"] if a["id"] != action["id"]] + [action]
            preview["knowledge_refs"] = preview.get("knowledge_refs", []) + [knowledge_ref]
            preview["next_decision"] = {**(preview.get("next_decision") or {}),
                                        "remaining_questions": result["result"]["remaining_questions"]}
            queries = project_knowledge.decision_needs(preview)
            contexts = [project_knowledge.query(self.root, preview, need=queries[point], point=point)
                        for point in project_knowledge.POINTS]
            decision = methods.choose_next(preview, methods.match_methods(preview), contexts[-1])
            decision["knowledge_contexts"] = contexts
            decision["receipt_snapshot_sha256"] = action["receipt_snapshot_sha256"]
            decision["remaining_questions"] = result["result"]["remaining_questions"]
        else:
            decision = registry.get_analysis(action["command"]).next_decision(result)
            if action["command"] in registry.followup_ids(registry.primary_id(self.status())):
                previous = self.status()
                prior = previous.get("next_decision") or {}
                pending = list(prior.get("next_action", {}).get("required_evidence", []))
                pending.extend(prior.get("remaining_questions", []))
                for old_action in previous["actions"]:
                    if old_action["status"] == "completed":
                        pending.extend((old_action.get("next_decision") or {}).get("next_action", {}).get("required_evidence", []))
                decision["retained_evidence_task_ref"] = previous.get("evidence_task_ref")
                decision["retained_unresolved_requirements"] = list(dict.fromkeys(pending))
                task = decision["next_action"]
                task["required_evidence"] = list(dict.fromkeys([*pending, *task.get("required_evidence", [])]))
        decision.update(based_on_action_id=action["id"], based_on_observation_ids=refs)
        action["next_decision"] = decision
        with self._connect() as con:
            project = self._project(con)
            existing = self._action(con, action["request_id"])
            if existing["status"] == "completed":
                return existing
            con.execute("UPDATE actions SET record=? WHERE request_id=?", (canonical(action), action["request_id"]))
            project.update(state_version=project["state_version"] + 1,
                           research_status=decision["project_status"], execution_status="completed", next_decision=decision)
            if knowledge_ref is not None:
                project.setdefault("knowledge_refs", []).append(knowledge_ref)
            elif (registry.is_source(decision["next_action"].get("method_id"))
                  and action["command"] not in registry.followup_ids(registry.primary_id(project))):
                project["evidence_task_ref"] = {"project_id": project["id"], "based_on_action_id": action["id"],
                                                "method_id": decision["next_action"]["method_id"]}
            self._save(con, project)
        return action

    def _recover(self, action):
        if action["status"] in ("completed", "failed"):
            if action["status"] == "completed":
                envelope = json.loads(self._artifact(action).read_bytes())
                require(envelope.get("sha256") == action["result_sha256"] and
                        envelope["sha256"] == fingerprint({k: v for k, v in envelope.items() if k != "sha256"}),
                        "EVIDENCE_CHANGED", "Completed result artifact changed.")
            return dict(action, replayed=True)
        path = self._artifact(action)
        if path.is_file():
            return dict(self._commit_result(action, json.loads(path.read_bytes())), recovered=True)
        with self._connect() as con:
            project = self._project(con)
            if action["status"] != "unknown":
                action.update(status="unknown", failure={"code": "EXECUTION_UNKNOWN", "automatic_retry": False})
                con.execute("UPDATE actions SET record=? WHERE request_id=?", (canonical(action), action["request_id"]))
                project.update(state_version=project["state_version"] + 1, research_status="waiting", execution_status="needs_review")
                self._save(con, project)
        return dict(action, automatic_retry=False)

    def step(self, *, request_id, dimension=None, expected_state_version=None, method_id=None, parameters=None):
        identifier(request_id)
        with self._writer():
            with self._connect() as con:
                project = self._project(con)
                primary_id = registry.primary_id(project)
                method_id = primary_id if method_id is None else method_id
                followup = method_id in registry.followup_ids(primary_id)
                require(method_id == primary_id or followup, "METHOD_NOT_SUPPORTED", "This method is not supported by the registered input.")
                primary = registry.get_analysis(method_id)
                if followup:
                    parameter_keys = {"based_on_action_id", "based_on_result_sha256"}
                    if method_id == registry.WORKBOOK:
                        parameter_keys |= {"origin_receipt_sha256", "origin_source_id"}
                    require(dimension is None and type(parameters) is dict
                            and set(parameters) == parameter_keys,
                            "INVALID_REQUEST", "A follow-up binds one saved predecessor action and result.")
                    identifier(parameters["based_on_action_id"])
                    require(type(parameters["based_on_result_sha256"]) is str
                            and re.fullmatch(r"[0-9a-f]{64}", parameters["based_on_result_sha256"]),
                            "INVALID_REQUEST", "A saved predecessor result SHA is required.")
                    if method_id == registry.WORKBOOK:
                        identifier(parameters["origin_source_id"], "origin_source_id")
                        require(type(parameters["origin_receipt_sha256"]) is str
                                and re.fullmatch(r"[0-9a-f]{64}", parameters["origin_receipt_sha256"]),
                                "INVALID_REQUEST", "A captured origin receipt SHA is required.")
                else:
                    require(parameters is None or parameters == {}, "INVALID_REQUEST", "Use the original primary-method parameters.")
                if method_id == adapter.TOOL_ID:
                    dimension = "chemistry" if dimension is None else dimension
                    require(dimension in ("chemistry", "topography"), "INVALID_REQUEST", "Only chemistry or topography is supported.")
                else:
                    require(dimension is None, "INVALID_REQUEST", "This domain method does not use P02 grouping parameters.")
                request = {"project_id": project["id"], "command": method_id, "dimension": dimension,
                           "source_snapshot_sha256": project["source_snapshot_sha256"]}
                if followup:
                    request.update(parameters=dict(parameters), evaluation_ref=registry.evaluation_ref(method_id))
                digest = fingerprint(request)
                old = self._action(con, request_id)
            if old:
                require(old["request_sha256"] == digest, "IDEMPOTENCY_CONFLICT", "Request ID is bound to different content.")
                return self._recover(old)
            self._require_unclaimed(project, request_id)
            require(expected_state_version is None or (type(expected_state_version) is int and
                    expected_state_version == project["state_version"]), "STALE_STATE", "Read the current project state before submitting.")
            require(project["code_identity"] == code_identity(), "CODE_CHANGED", "Use the registered application and adapter version.")
            payload = self._source(project)
            current = self.status()
            require(not any(a["status"] in ("running", "unknown") for a in current["actions"] + current["evidence_actions"])
                    and not any(item["status"] in ("sending", "unknown") for item in project.get("source_requests", [])),
                    "EXECUTION_UNKNOWN", "Recover the existing execution; do not submit another action.")
            prior = next((a for a in current["actions"] if a["request_sha256"] == digest and a["status"] == "completed"), None)
            if prior:
                with self._connect() as con:
                    con.execute("INSERT INTO replays VALUES(?,?)", (request_id, prior["request_id"]))
                return dict(self._recover(prior), reused=True)
            if followup:
                option = next((item for item in methods.match_methods(current) if item["method_id"] == method_id), None)
                require(option is not None and option["condition"] == "satisfied" and not option["completed"]
                        and option["parameters"] == parameters, "CONDITION_NOT_SATISFIED", "Saved feedback does not qualify this follow-up.")
                predecessor = next((a for a in current["actions"] if a["id"] == parameters["based_on_action_id"]), None)
                require(predecessor is not None and predecessor["status"] == "completed"
                        and predecessor["command"] == primary_id
                        and predecessor["source_snapshot_sha256"] == project["source_snapshot_sha256"]
                        and predecessor["result_sha256"] == parameters["based_on_result_sha256"]
                        and predecessor["method_instance"]["evaluation_ref"] == registry.evaluation_ref(primary_id),
                        "EVIDENCE_CHANGED", "The follow-up predecessor identity differs.")
                self._recover(predecessor)
                original = json.loads(self._artifact(predecessor).read_bytes())["tool_result"]
                if method_id != registry.WORKBOOK:
                    require(methods.grouped_feedback_eligible(original["result"]["profile"], original["result"]["scope"]),
                            "CONDITION_NOT_SATISFIED", "The verified original result does not qualify this follow-up.")
            else:
                require(project["research_status"] == "active", "PROJECT_WAITING", "Resolve the recorded evidence task before another execution.")
            require(len(current["actions"]) < project["budget"]["local_tool_call_limit"],
                    "BUDGET_EXHAUSTED", "Cumulative local verification allowance is exhausted.")
            if method_id == registry.WORKBOOK:
                payload = self._workbook_projection_input(project, payload, parameters)
            action = {**request, "id": "action-" + fingerprint({"request_id": request_id, **request})[:32],
                      "request_id": request_id, "request_sha256": digest, "status": "running",
                      "run_id": project["run_id"], "code_identity": project["code_identity"], "failure": None,
                      "method_instance": {"definition_ref": {"id": method_id, "version": primary.ADAPTER_VERSION},
                                          "input_bindings": {"source_snapshot_sha256": project["source_snapshot_sha256"]},
                                          "parameters": dict(parameters) if followup else {"dimension": dimension} if dimension is not None else {},
                                          "evaluation_ref": registry.evaluation_ref(method_id),
                                          "scope": project["source_scope"]}}
            if followup:
                action["method_instance"]["input_bindings"].update(parameters)
            with self._connect() as con:
                con.execute("INSERT INTO actions VALUES(?,?,?)", (request_id, digest, canonical(action)))
                project.update(state_version=project["state_version"] + 1, execution_status="running")
                self._save(con, project)
            try:
                result = primary.execute(payload, parameters) if followup else primary.execute(payload, dimension)
            except Exception as exc:
                action.update(status="failed", failure={"code": getattr(exc, "code", "TOOL_FAILED"),
                              "type": type(exc).__name__, "message": str(exc), "phase": "tool", "automatic_retry": False})
                with self._connect() as con:
                    con.execute("UPDATE actions SET record=? WHERE request_id=?", (canonical(action), request_id))
                    project.update(state_version=project["state_version"] + 1, research_status="waiting", execution_status="failed")
                    self._save(con, project)
                raise ResearchError(action["failure"]["code"], str(exc)) from exc
            envelope = {"action_id": action["id"], "request_sha256": digest, "code_identity": project["code_identity"],
                        "source_snapshot_sha256": project["source_snapshot_sha256"], "tool_result": result}
            envelope["sha256"] = fingerprint(envelope)
            write_once(self._artifact(action), envelope)
            return self._commit_result(action, envelope)

    def resume(self, *, request_id):
        identifier(request_id)
        with self._writer():
            with self._connect() as con:
                action = self._action(con, request_id)
                project = self._project(con)
            require(action is not None, "ACTION_NOT_FOUND", "No accepted execution has this request ID.")
            require(project["code_identity"] == code_identity() or action["status"] in ("completed", "failed"),
                    "CODE_CHANGED", "Recover using the registered application version.")
            return self._recover(action)

    def upgrade(self, *, request_id, expected_code_identity, evidence_read_limit=8):
        """Explicit compatible upgrade; retain the project, completed evidence and all usage."""
        identifier(request_id)
        require(type(evidence_read_limit) is int and 1 <= evidence_read_limit <= 16,
                "INVALID_REQUEST", "Evidence allowance must be 1..16 local reads.")
        with self._writer():
            with self._connect() as con:
                project = self._project(con)
                previous = next((r for r in project.get("code_revisions", []) if r["request_id"] == request_id), None)
                if previous:
                    require(previous["from"] == expected_code_identity and previous["to"] == code_identity()
                            and previous["evidence_read_limit"] == evidence_read_limit,
                            "IDEMPOTENCY_CONFLICT", "Upgrade request content changed.")
                    return previous
                require(self._action(con, request_id) is None, "IDEMPOTENCY_CONFLICT", "ID belongs to a tool action.")
                self._require_unclaimed(project, request_id, except_collection="code_revisions")
            require(project["code_identity"] == expected_code_identity, "CODE_CHANGED", "Expected old code identity differs.")
            require(project["schema_version"] in ("local-research-project-v1", "local-research-project-v2", "local-research-project-v3"),
                    "INCOMPATIBLE_PROJECT", "This project schema cannot be upgraded here.")
            current = self.status()
            require(not any(a["status"] in ("running", "unknown") for a in current["actions"] + current["evidence_actions"])
                    and not any(item["status"] in ("sending", "unknown") for item in project.get("source_requests", []))
                    and not any(item["status"] == "reserved" for item in project.get("local_model_requests", [])),
                    "EXECUTION_UNKNOWN", "Resolve existing execution with its original code before upgrading.")
            payload = self._source(project)
            for action in current["actions"] + current["evidence_actions"]:
                self._recover(action)
            source_metadata = {}
            for entry in project.get("evidence_sources", []):
                receipt, _, _ = self._load_evidence_input(project, entry["receipt_snapshot_sha256"],
                                                        input_receipt=entry["input_receipt"], task_ref=entry.get("task_ref"))
                source_metadata[entry["receipt_snapshot_sha256"]] = _source_metadata(receipt)
            require(project["budget"].get("evidence_read_limit", evidence_read_limit) == evidence_read_limit,
                    "CONFIG_CHANGED", "An existing evidence allowance cannot be reset or enlarged by upgrade.")
            revision = {"request_id": request_id, "from": expected_code_identity, "to": code_identity(),
                        "evidence_read_limit": evidence_read_limit, "state_version_before": project["state_version"],
                        "project_id": project["id"], "source_snapshot_sha256": project["source_snapshot_sha256"]}
            path = safe_path(self.root / "artifacts" / ("upgrade-" + fingerprint(revision) + ".json"))
            snapshot = {"revision": revision, "project_before": project}
            if path.exists():
                require(json.loads(path.read_bytes()) == snapshot, "EVIDENCE_CHANGED", "Upgrade receipt differs.")
            else:
                write_once(path, snapshot)
            with self._connect() as con:
                project["schema_version"] = "local-research-project-v3"
                project["code_identity"] = code_identity()
                project.setdefault("evidence_sources", [])
                for entry in project["evidence_sources"]:
                    entry["source_metadata"] = source_metadata[entry["receipt_snapshot_sha256"]]
                if registry.primary_id(project) == "data.tabular-quality-audit":
                    project["source_provenance"] = dict(payload["spec"]["provenance"])
                project.setdefault("evidence_registrations", [])
                project.setdefault("knowledge_refs", [])
                project.setdefault("code_revisions", []).append(revision)
                project["budget"].setdefault("evidence_read_limit", evidence_read_limit)
                project["state_version"] += 1
                if "evidence_task_ref" not in project and project.get("next_decision"):
                    origin = project["next_decision"].get("based_on_action_id")
                    if origin:
                        project["evidence_task_ref"] = {"project_id": project["id"], "based_on_action_id": origin,
                                                        "method_id": registry.source_id(project)}
                primary = registry.get(registry.primary_id(project))
                project["supported_methods"] = [{"id": primary.TOOL_ID, "version": primary.ADAPTER_VERSION},
                                                 {"id": registry.source_id(project), "version": source_adapter.ADAPTER_VERSION}]
                project["supported_methods"].extend({"id": method, "version": registry.get_analysis(method).ADAPTER_VERSION}
                                                    for method in registry.followup_ids(primary.TOOL_ID))
                self._save(con, project)
            return revision

    def extend_local_budget(self, *, request_id, expected_limit, new_limit, reason, expected_state_version=None):
        """Explicit local arithmetic allowance revision; never reset usage or financial/model caps."""
        identifier(request_id)
        require(type(expected_limit) is int and type(new_limit) is int and 1 <= expected_limit < new_limit <= 16,
                "INVALID_REQUEST", "Explicitly increase the local-tool limit within 1..16 calls.")
        require(type(reason) is str and 0 < len(reason.strip()) <= 1000 and "\x00" not in reason,
                "INVALID_REQUEST", "Record a bounded reason for the local allowance change.")
        request = {"request_id": request_id, "expected_limit": expected_limit, "new_limit": new_limit,
                   "reason": reason, "expected_state_version": expected_state_version}
        with self._writer():
            with self._connect() as con:
                project = self._project(con)
                old = next((item for item in project.get("budget_revisions", []) if item["request_id"] == request_id), None)
                if old:
                    require(old["request_sha256"] == fingerprint(request), "IDEMPOTENCY_CONFLICT", "Budget revision content changed.")
                    return old
                require(self._action(con, request_id) is None, "IDEMPOTENCY_CONFLICT", "ID belongs to an existing action.")
                self._require_unclaimed(project, request_id, except_collection="budget_revisions")
            current = self.status()
            self._require_fresh(project, current, expected_state_version)
            require(not any(item["status"] in ("prepared", "running") for item in project.get("controller_requests", [])),
                    "PROJECT_BUSY", "Finish the frozen controller request before revising its allowance.")
            self._source(project)
            require(project["budget"]["local_tool_call_limit"] == expected_limit,
                    "CONFIG_CHANGED", "Expected local-tool limit differs; usage and limits were not reset.")
            require(len(current["actions"]) <= new_limit, "BUDGET_EXHAUSTED", "The new limit must cover all existing dispatches.")
            revision = {"request_id": request_id, "request_sha256": fingerprint(request), "request": request,
                        "project_id": project["id"], "run_id": project["run_id"],
                        "source_snapshot_sha256": project["source_snapshot_sha256"], "code_identity": project["code_identity"],
                        "state_version_before": project["state_version"], "old_limit": expected_limit, "new_limit": new_limit,
                        "local_dispatches_preserved": len(current["actions"]),
                        "notice": "Only the local-tool limit changed; cumulative usage, historical unknowns and all other caps are preserved."}
            path = safe_path(self.root / "artifacts" / ("budget-" + fingerprint(revision) + ".json"))
            snapshot = {"revision": revision, "budget_before": project["budget"]}
            if path.exists():
                require(json.loads(path.read_bytes()) == snapshot, "EVIDENCE_CHANGED", "Budget revision receipt differs.")
            else:
                write_once(path, snapshot)
            with self._connect() as con:
                project["budget"]["local_tool_call_limit"] = new_limit
                project.setdefault("budget_revisions", []).append(revision)
                project["state_version"] += 1
                self._save(con, project)
            return revision

    def authorize_local_model_budget(self, *, request_id, expected_limit, new_limit, reason, expected_state_version=None):
        """Explicit one-slot offline authorization; unrelated limits and unknown costs remain unchanged."""
        identifier(request_id)
        require(type(expected_limit) is int and expected_limit == 0 and type(new_limit) is int and new_limit == 1
                and type(reason) is str and 0 < len(reason.strip()) <= 4000 and "\x00" not in reason,
                "INVALID_REQUEST", "Authorize exactly 0 to 1 offline Qwen3:4b request with a bounded reason.")
        request = {"request_id": request_id, "expected_limit": expected_limit, "new_limit": new_limit,
                   "reason": reason, "expected_state_version": expected_state_version}
        with self._writer():
            with self._connect() as con:
                project = self._project(con)
                old = next((item for item in project.get("model_budget_revisions", []) if item["request_id"] == request_id), None)
                if old is not None:
                    require(old["request_sha256"] == fingerprint(request), "IDEMPOTENCY_CONFLICT", "Model authorization content changed.")
                    return dict(old, replayed=True)
                require(self._action(con, request_id) is None, "IDEMPOTENCY_CONFLICT", "Authorization ID belongs to an action.")
                self._require_unclaimed(project, request_id)
                self._require_fresh(project, self.status(), expected_state_version)
                require(project["budget"].get("model_requests_allowed", 0) == 0
                        and project["budget"].get("new_model_requests", 0) == 0
                        and project["budget"].get("model_requests_reserved", 0) == 0
                        and not project.get("local_model_requests"), "CONFIG_CHANGED", "The cumulative model allowance cannot be reset or reused.")
                require(not any(item["status"] in ("prepared", "running", "unknown") for item in project.get("controller_requests", [])),
                        "PROJECT_BUSY", "Reconcile the original controller request before authorizing local inference.")
                revision = {"request_id": request_id, "request_sha256": fingerprint(request), "request": request,
                            "project_id": project["id"], "run_id": project["run_id"], "model": "qwen3:4b", "cloud_allowed": False,
                            "old_limit": 0, "new_limit": 1, "state_version_before": project["state_version"],
                            "code_identity": project["code_identity"], "scientific_validation": False}
                project["budget"].update(model_requests_allowed=1, model_requests_reserved=0)
                project.setdefault("model_budget_revisions", []).append(revision)
                project["state_version"] += 1
                self._save(con, project)
                return revision

    def reserve_local_model_slot(self, *, request_id, expected_state_version, transport_identity):
        """Reserve before sealing context; the core stores metadata, never recursive context/raw bytes."""
        from .project_model_protocol import validate_transport_identity
        identifier(request_id)
        identity = validate_transport_identity(transport_identity)
        require(type(expected_state_version) is int and expected_state_version >= 0, "INVALID_REQUEST", "An exact project version is required.")
        request = {"request_id": request_id, "expected_state_version": expected_state_version,
                   "transport_identity_sha256": fingerprint(identity)}
        with self._writer():
            with self._connect() as con:
                project = self._project(con)
                old = next((item for item in project.get("local_model_requests", []) if item["request_id"] == request_id), None)
                if old is not None:
                    require(old["request_sha256"] == fingerprint(request), "IDEMPOTENCY_CONFLICT", "Reserved local-model request content changed.")
                    return dict(old, replayed=True)
                require(self._action(con, request_id) is None, "IDEMPOTENCY_CONFLICT", "Model request ID belongs to an action.")
                self._require_unclaimed(project, request_id)
                self._require_fresh(project, self.status(), expected_state_version)
                budget = project["budget"]
                require(budget.get("model_requests_allowed", 0) == 1
                        and budget.get("new_model_requests", 0) + budget.get("model_requests_reserved", 0) < 1
                        and not project.get("local_model_requests"), "MODEL_BUDGET_EXHAUSTED", "No cumulative offline model slot is available.")
                require(not any(item["status"] in ("prepared", "running", "unknown") for item in project.get("controller_requests", [])),
                        "PROJECT_BUSY", "Complete the frozen controller request before reserving a model slot.")
                slot = {**request, "request_sha256": fingerprint(request), "project_id": project["id"], "run_id": project["run_id"],
                        "source_snapshot_sha256": project["source_snapshot_sha256"], "code_identity": project["code_identity"],
                        "status": "reserved", "model": "qwen3:4b", "cloud_allowed": False,
                        "state_version_before": project["state_version"], "state_version_after": project["state_version"] + 1}
                project.setdefault("local_model_requests", []).append(slot)
                budget["model_requests_reserved"] = 1
                project["state_version"] += 1
                self._save(con, project)
                return slot

    def finalize_local_model_slot(self, *, request_id, outcome, receipt_sha256):
        """A known terminal outcome spends the original slot once; unknown sends cannot release it."""
        identifier(request_id)
        require(outcome in {"applied", "invalid", "stale", "failed"} and type(receipt_sha256) is str
                and re.fullmatch(r"[a-f0-9]{64}", receipt_sha256), "INVALID_REQUEST", "A known outcome and immutable journal receipt are required.")
        with self._writer():
            with self._connect() as con:
                project = self._project(con)
                slot = next((item for item in project.get("local_model_requests", []) if item["request_id"] == request_id), None)
                require(slot is not None, "MODEL_REQUEST_NOT_FOUND", "No reserved local-model request matches this ID.")
                if slot["status"] == "finalized":
                    require(slot["outcome"] == outcome and slot["receipt_sha256"] == receipt_sha256,
                            "IDEMPOTENCY_CONFLICT", "Model finalization content changed.")
                    return dict(slot, replayed=True)
                require(slot["status"] == "reserved" and project["budget"].get("model_requests_reserved") == 1,
                        "EVIDENCE_CHANGED", "The original cumulative model reservation changed.")
                key = fingerprint({"project_id": project["id"], "request_id": request_id})
                directory = safe_path(self.root / "model-proposals")
                try:
                    proof = json.loads(source_adapter._read_file(safe_path(directory / "receipts" / (key + ".json")), 1_000_000))
                    raw = source_adapter._read_file(safe_path(directory / "responses" / (key + ".bin")), 2 * 1024 * 1024)
                except OSError:
                    raise ResearchError("MODEL_RESPONSE_NOT_RECEIVED", "A saved known response and terminal receipt are required; unknown reservations remain held.") from None
                require(proof.get("schema_version") == "project-model-finalization-v1"
                        and proof.get("sha256") == receipt_sha256 == fingerprint({k: v for k, v in proof.items() if k != "sha256"})
                        and proof.get("project_id") == project["id"] and proof.get("run_id") == project["run_id"]
                        and proof.get("request_id") == request_id and proof.get("slot_request_sha256") == slot["request_sha256"]
                        and proof.get("outcome") == outcome and proof.get("response_sha256") == hashlib.sha256(raw).hexdigest(),
                        "EVIDENCE_CHANGED", "A terminal response receipt is required; an unknown send cannot release its reservation.")
                slot.update(status="finalized", outcome=outcome, receipt_sha256=receipt_sha256,
                            finalized_state_version=project["state_version"] + 1)
                project["budget"]["model_requests_reserved"] = 0
                project["budget"]["new_model_requests"] = project["budget"].get("new_model_requests", 0) + 1
                project["state_version"] += 1
                self._save(con, project)
                return slot

    def evidence_task(self):
        project = self.status()
        require(bool(project.get("evidence_task_ref")), "TASK_NOT_AVAILABLE", "No source evidence task is bound yet.")
        return {"task_ref": project["evidence_task_ref"], "state_version": project["state_version"],
                "required_evidence": project["next_decision"]["next_action"].get("required_evidence", []),
                "manifest_template": {"schema_version": "project-evidence-bundle-v1", "task_ref": project["evidence_task_ref"],
                                      "contributor": {"role": "operator_assistant", "label": "fill actual contributor"},
                                      "sources": [], "selections": [], "remaining_questions": []},
                "notice": "Empty template is not evidence; source extraction does not approve scientific mapping."}

    def method_options(self, *, need="next_check"):
        project = self.status()
        return {"snapshot_ref": project["snapshot_ref"], "options": methods.match_methods(project, need)}

    def knowledge(self, *, need, point="interpretation", limit=5):
        return project_knowledge.query(self.root, self.status(), need=need, point=point, limit=limit)

    def _load_evidence_input(self, project, receipt_snapshot_sha256, *, input_receipt=None, task_ref=None):
        """Verify stored receipt/assets only; never parse selections or build knowledge."""
        require(type(receipt_snapshot_sha256) is str and re.fullmatch(r"[a-f0-9]{64}", receipt_snapshot_sha256),
                "INVALID_REQUEST", "A registered lowercase receipt SHA-256 is required.")
        relative = "evidence-inputs/" + receipt_snapshot_sha256 + "/receipt.json"
        require(input_receipt is None or input_receipt == relative, "EVIDENCE_CHANGED", "Registered receipt path differs.")
        inputs = safe_path(self.root / "evidence-inputs" / receipt_snapshot_sha256)
        try:
            raw = source_adapter._read_file(inputs / "receipt.json", source_adapter.MAX_MANIFEST_BYTES)
            receipt = json.loads(raw, object_pairs_hook=source_adapter._json_object,
                                 parse_constant=source_adapter._reject_constant)
            task, _, sources, _, _ = source_adapter._metadata(receipt, captured=True)
            require(receipt["snapshot_sha256"] == receipt_snapshot_sha256 == fingerprint(
                {key: value for key, value in receipt.items() if key != "snapshot_sha256"}),
                "EVIDENCE_CHANGED", "Registered receipt identity changed.")
            require(task["project_id"] == project["id"] and registry.is_source(task["method_id"])
                    and (task_ref is None or task == task_ref),
                    "TASK_MISMATCH", "Registered receipt belongs to a different project task.")
            assets, total = {}, 0
            for source in sources:
                digest = source["asset_sha256"]
                value = source_adapter._read_file(safe_path(inputs / (digest + ".bin")), source_adapter.MAX_SOURCE_BYTES)
                total += len(value)
                require(total <= source_adapter.MAX_TOTAL_BYTES and hashlib.sha256(value).hexdigest() == digest == source["sha256"],
                        "EVIDENCE_CHANGED", "Registered original source bytes changed.")
                assets[source["id"]] = value
            return receipt, assets, relative
        except ResearchError:
            raise
        except (OSError, KeyError, TypeError, ValueError):
            raise ResearchError("EVIDENCE_CHANGED", "Registered evidence is incomplete or malformed.") from None

    def _persist_evidence_input(self, receipt, assets):
        inputs = safe_path(self.root / "evidence-inputs" / receipt["snapshot_sha256"])
        inputs.mkdir(parents=True, exist_ok=True)
        for source in receipt["sources"]:
            write_bytes_once(safe_path(inputs / (source["asset_sha256"] + ".bin")), assets[source["id"]])
        receipt_path = safe_path(inputs / "receipt.json")
        if receipt_path.exists():
            require(json.loads(source_adapter._read_file(receipt_path, source_adapter.MAX_MANIFEST_BYTES)) == receipt,
                    "EVIDENCE_CHANGED", "Captured receipt differs from its saved identity.")
        else:
            write_once(receipt_path, receipt)
        return receipt_path.relative_to(self.root).as_posix()

    def _workbook_projection_input(self, project, payload, parameters):
        entry = next((item for item in project["evidence_sources"]
                      if item["receipt_snapshot_sha256"] == parameters["origin_receipt_sha256"]), None)
        require(entry is not None, "CONDITION_NOT_SATISFIED", "The workbook must already be captured in this project.")
        receipt, assets, _ = self._load_evidence_input(project, entry["receipt_snapshot_sha256"],
                                                     input_receipt=entry["input_receipt"], task_ref=entry["task_ref"])
        origin = next((item for item in receipt["sources"] if item["id"] == parameters["origin_source_id"]), None)
        require(origin is not None and origin["sha256"] == payload["spec"]["provenance"]["origin_sha256"]
                and origin["media_type"] == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                "EVIDENCE_CHANGED", "Captured workbook identity differs from the submitted origin declaration.")
        return {"tabular_source": payload, "origin_bytes": assets[origin["id"]],
                "origin_source": {key: origin[key] for key in ("id", "sha256", "media_type")}}

    def _register_evidence_locked(self, *, request_id, bundle, expected_state_version=None):
        current = self.status()
        with self._connect() as con:
            project = self._project(con)
            action_owner = self._action(con, request_id)
        old = next((item for item in project.get("evidence_registrations", []) if item["request_id"] == request_id), None)
        if old is None:
            require(action_owner is None, "IDEMPOTENCY_CONFLICT", "ID belongs to a tool action.")
            self._require_unclaimed(project, request_id)
            self._require_fresh(project, current, expected_state_version)
        task = old["task_ref"] if old else project.get("evidence_task_ref")
        require(bool(task), "TASK_NOT_AVAILABLE", "No task is bound to this project.")
        receipt, assets = source_adapter.capture_bundle(bundle, task)
        request = {"project_id": project["id"], "command": "register_evidence",
                   "receipt_snapshot_sha256": receipt["snapshot_sha256"],
                   "source_snapshot_sha256": project["source_snapshot_sha256"]}
        digest = fingerprint(request)
        if old:
            require(old["request_sha256"] == digest, "IDEMPOTENCY_CONFLICT", "Registration request content changed.")
            self._load_evidence_input(project, receipt["snapshot_sha256"], input_receipt=old["input_receipt"], task_ref=task)
            return dict(old, replayed=True)
        sources = project.setdefault("evidence_sources", [])
        existing = next((item for item in sources if item["receipt_snapshot_sha256"] == receipt["snapshot_sha256"]), None)
        unique = {item["receipt_snapshot_sha256"] for item in sources}
        require(existing is not None or len(unique) < project["budget"].get("evidence_read_limit", 0),
                "BUDGET_EXHAUSTED", "The existing source allowance also bounds unique registered receipts.")
        relative = self._persist_evidence_input(receipt, assets)
        record = {**request, "id": "registration-" + fingerprint({"request_id": request_id, **request})[:32],
                  "request_id": request_id, "request_sha256": digest, "status": "registered",
                  "task_ref": receipt["task_ref"], "input_receipt": relative,
                  "source_count": len(receipt["sources"]), "selection_count": len(receipt["selections"]),
                  "state_version_before": project["state_version"], "state_version_after": project["state_version"] + 1,
                  "read_performed": False, "scientific_validation": False}
        if existing is None:
            sources.append({"receipt_snapshot_sha256": receipt["snapshot_sha256"], "input_receipt": relative,
                            "task_ref": receipt["task_ref"], "source_count": len(receipt["sources"]),
                            "selection_count": len(receipt["selections"]), "registration_id": record["id"],
                            "source_metadata": _source_metadata(receipt)})
            preview = dict(current, evidence_sources=sources)
            decision = methods.choose_next(preview, methods.match_methods(preview))
            decision["based_on_registration_id"] = record["id"]
            project.update(research_status=decision["project_status"], execution_status="ready", next_decision=decision)
        else:
            require(existing.get("task_ref", receipt["task_ref"]) == receipt["task_ref"],
                    "TASK_MISMATCH", "The existing receipt task differs.")
            existing.update(input_receipt=relative, task_ref=receipt["task_ref"], source_metadata=_source_metadata(receipt))
        project.setdefault("evidence_registrations", []).append(record)
        project["state_version"] += 1
        with self._connect() as con:
            self._save(con, project)
        return dict(record, reused=existing is not None)

    def register_evidence(self, *, request_id, bundle, expected_state_version=None):
        """Capture immutable inputs only: no extraction, observation, index or read charge."""
        identifier(request_id)
        with self._writer():
            return self._register_evidence_locked(request_id=request_id, bundle=bundle,
                                                 expected_state_version=expected_state_version)

    def _read_evidence_locked(self, *, request_id, receipt_snapshot_sha256, expected_state_version=None):
        require(type(receipt_snapshot_sha256) is str and re.fullmatch(r"[a-f0-9]{64}", receipt_snapshot_sha256),
                "INVALID_REQUEST", "A registered lowercase receipt SHA-256 is required.")
        with self._connect() as con:
            project = self._project(con)
            old = self._action(con, request_id)
        if old:
            request = {"project_id": project["id"], "command": old["command"],
                       "receipt_snapshot_sha256": receipt_snapshot_sha256,
                       "source_snapshot_sha256": project["source_snapshot_sha256"]}
            require(registry.is_source(old["command"]) and old["request_sha256"] == fingerprint(request),
                    "IDEMPOTENCY_CONFLICT", "Request ID content changed.")
            return self._recover(old)
        self._require_unclaimed(project, request_id)
        current = self.status()
        self._require_fresh(project, current, expected_state_version)
        source = next((item for item in project.get("evidence_sources", [])
                       if item["receipt_snapshot_sha256"] == receipt_snapshot_sha256), None)
        require(source is not None, "SOURCE_NOT_REGISTERED", "Register the immutable receipt before reading it.")
        receipt, assets, relative = self._load_evidence_input(
            project, receipt_snapshot_sha256, input_receipt=source.get("input_receipt"), task_ref=source.get("task_ref"))
        request = {"project_id": project["id"], "command": receipt["task_ref"]["method_id"],
                   "receipt_snapshot_sha256": receipt_snapshot_sha256,
                   "source_snapshot_sha256": project["source_snapshot_sha256"]}
        digest = fingerprint(request)
        prior = next((item for item in current["evidence_actions"]
                      if item["receipt_snapshot_sha256"] == receipt_snapshot_sha256
                      and item["status"] in ("completed", "failed")), None)
        if prior:
            require(prior["request_sha256"] == digest, "IDEMPOTENCY_CONFLICT", "Receipt execution scope differs.")
            with self._connect() as con:
                con.execute("INSERT INTO replays VALUES(?,?)", (request_id, prior["request_id"]))
            return dict(self._recover(prior), reused=True)
        require(len(current["evidence_actions"]) < project["budget"].get("evidence_read_limit", 0),
                "BUDGET_EXHAUSTED", "Cumulative local source-read allowance is exhausted.")
        action = {**request, "id": "action-" + fingerprint({"request_id": request_id, **request})[:32],
                  "request_id": request_id, "request_sha256": digest, "status": "running",
                  "run_id": project["run_id"], "code_identity": project["code_identity"], "failure": None,
                  "input_receipt": relative,
                  "method_instance": {"definition_ref": {"id": request["command"], "version": source_adapter.ADAPTER_VERSION},
                                      "input_bindings": {"receipt_snapshot_sha256": receipt_snapshot_sha256},
                                      "task_ref": receipt["task_ref"], "scope": "source selections only; domain conditions unreviewed"}}
        with self._connect() as con:
            con.execute("INSERT INTO actions VALUES(?,?,?)", (request_id, digest, canonical(action)))
            project.update(state_version=project["state_version"] + 1, execution_status="running")
            self._save(con, project)
        try:
            result = source_adapter.execute(receipt, assets)
        except Exception as exc:
            action.update(status="failed", failure={"code": getattr(exc, "code", "TOOL_FAILED"),
                          "type": type(exc).__name__, "phase": "source_extraction", "automatic_retry": False})
            with self._connect() as con:
                con.execute("UPDATE actions SET record=? WHERE request_id=?", (canonical(action), request_id))
                project.update(state_version=project["state_version"] + 1, research_status="waiting", execution_status="failed")
                self._save(con, project)
            raise ResearchError(action["failure"]["code"], str(exc)) from exc
        envelope = {"action_id": action["id"], "request_sha256": digest, "code_identity": project["code_identity"],
                    "source_snapshot_sha256": project["source_snapshot_sha256"], "tool_result": result}
        envelope["sha256"] = fingerprint(envelope)
        write_once(self._artifact(action), envelope)
        return self._commit_result(action, envelope)

    def read_evidence(self, *, request_id, receipt_snapshot_sha256, expected_state_version=None):
        """Extract an already registered receipt once, using the original execution ledger."""
        identifier(request_id)
        with self._writer():
            return self._read_evidence_locked(request_id=request_id, receipt_snapshot_sha256=receipt_snapshot_sha256,
                                             expected_state_version=expected_state_version)

    def attach_evidence(self, *, request_id, bundle, expected_state_version=None):
        """Compatibility command: register then read, preserving the original read request ID."""
        identifier(request_id)
        with self._writer():
            with self._connect() as con:
                project = self._project(con)
                old = self._action(con, request_id)
            if old:
                require(registry.is_source(old["command"]), "IDEMPOTENCY_CONFLICT", "ID belongs to a different tool action.")
                saved, _, _ = self._load_evidence_input(project, old["receipt_snapshot_sha256"], input_receipt=old["input_receipt"])
                receipt, _ = source_adapter.capture_bundle(bundle, saved["task_ref"])
                request = {"project_id": project["id"], "command": old["command"],
                           "receipt_snapshot_sha256": receipt["snapshot_sha256"],
                           "source_snapshot_sha256": project["source_snapshot_sha256"]}
                require(fingerprint(request) == old["request_sha256"], "IDEMPOTENCY_CONFLICT", "Request ID content changed.")
                return self._recover(old)
            self._require_unclaimed(project, request_id)
            registration_id = "attach-register-" + fingerprint({"project_id": project["id"], "request_id": request_id})[:40]
            registration = self._register_evidence_locked(request_id=registration_id, bundle=bundle,
                                                          expected_state_version=expected_state_version)
            return self._read_evidence_locked(request_id=request_id,
                                             receipt_snapshot_sha256=registration["receipt_snapshot_sha256"],
                                             expected_state_version=registration["state_version_after"])
