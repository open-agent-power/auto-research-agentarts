"""One owned Qwen3:4b request from existing pinned bytes; no cloud or download path."""
import copy
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import traceback
import urllib.request

from . import local_ollama, local_process
from .contracts import ResearchError, canonical, fingerprint, identifier
from .research_project import safe_path

MODEL = "qwen3:4b"
MAX_RESPONSE = 2 * 1024 * 1024
TIMEOUT = 180
_CONTROL_FILES = ("transport-identity.json", "wire-request.json", "server-identity.json", "shutdown.json",
                  "server/server.stdout.log", "server/server.stderr.log", "server/native-show-evidence.json",
                  "server/native-tags-evidence.json", "worker.stdout.log", "worker.stderr.log", "preflight-error.txt")


def _require(condition, code, message):
    if not condition:
        raise ResearchError(code, message)


def code_identity():
    return hashlib.sha256(Path(__file__).read_bytes() + Path(local_ollama.__file__).read_bytes()
                          + Path(local_process.__file__).read_bytes()).hexdigest()


def _write(path, raw):
    safe_path(path)
    with path.open("xb") as stream:
        stream.write(raw); stream.flush(); os.fsync(stream.fileno())


def _json(path, value):
    _write(path, canonical(value).encode("utf-8"))


def _preflight_files(root):
    records = []
    for relative in _CONTROL_FILES:
        path = safe_path(root / relative)
        if path.exists():
            digest, size, prefix = local_ollama.file_info(path, 8 * 1024 * 1024)
            if relative.startswith("worker."):
                _require(size == 0, "INVALID_PREFLIGHT_PROOF", "Worker evidence is not empty; dispatch may have occurred.")
            if relative in {"server/server.stdout.log", "server/server.stderr.log"}:
                _require(b"/api/chat" not in path.read_bytes().lower(), "INVALID_PREFLIGHT_PROOF", "Native chat appears in original server logs.")
            records.append({"relative_path": relative, "sha256": digest, "bytes": size})
    for relative in ("response.bin", "response-metadata.json", "transport-receipt.json"):
        _require(not safe_path(root / relative).exists(), "INVALID_PREFLIGHT_PROOF", "Response evidence exists; do not classify as undispatched.")
    return records


def validate_preflight_no_dispatch(reference, request_id, request_sha256, identity, *, expected_transport_code_identity=None):
    """Re-read strict local proof, never a generic error-code or unknown reset."""
    from .project_model_protocol import validate_transport_identity
    _require(type(reference) is dict and set(reference) == {"proof_path", "proof_sha256"},
             "INVALID_PREFLIGHT_PROOF", "Exact local proof reference required.")
    path, _ = local_ollama.regular(Path(reference["proof_path"]).absolute(), 65536)
    _require(path.name == "preflight-no-dispatch.json", "INVALID_PREFLIGHT_PROOF", "Unexpected preflight proof file.")
    raw = path.read_bytes(); proof = local_ollama.parse_json(raw)
    fields = {"schema_version", "request_id", "request_sha256", "identity", "transport_code_identity", "stage", "phase",
              "worker_spawn_attempted", "chat_dispatched", "owned_server_stopped", "owned_process_created", "output", "files", "failure_code"}
    expected_code = code_identity() if expected_transport_code_identity is None else expected_transport_code_identity
    _require(hashlib.sha256(raw).hexdigest() == reference["proof_sha256"] and type(proof) is dict and set(proof) == fields
             and proof["schema_version"] == "project-local-model-preflight-v1" and proof["request_id"] == request_id
             and proof["request_sha256"] == request_sha256 and proof["identity"] == validate_transport_identity(identity)
             and proof["transport_code_identity"] == expected_code and proof["stage"] == "before_worker_spawn"
             and proof["worker_spawn_attempted"] is False and proof["chat_dispatched"] is False
             and proof["owned_server_stopped"] is True and type(proof["owned_process_created"]) is bool
             and Path(proof["output"]).absolute() == path.parent,
             "INVALID_PREFLIGHT_PROOF", "Preflight binding or execution boundary differs.")
    root = safe_path(path.parent)
    _require(proof["files"] == _preflight_files(root), "INVALID_PREFLIGHT_PROOF", "Original preflight evidence changed.")
    available = {item["relative_path"] for item in proof["files"]}
    if proof["owned_process_created"]:
        _require({"server/server.stdout.log", "server/server.stderr.log", "shutdown.json"} <= available,
                 "INVALID_PREFLIGHT_PROOF", "Owned-process logs and shutdown proof are required.")
        shutdown = local_ollama.parse_json((root / "shutdown.json").read_bytes())
        _require(shutdown.get("owned_server_stopped") is True, "INVALID_PREFLIGHT_PROOF", "Owned process shutdown is unconfirmed.")
    if "transport-identity.json" in available:
        _require(local_ollama.parse_json((root / "transport-identity.json").read_bytes()) == identity,
                 "INVALID_PREFLIGHT_PROOF", "Original offline identity differs.")
    if "wire-request.json" in available:
        wire = local_ollama.parse_json((root / "wire-request.json").read_bytes())
        _require(fingerprint(wire["payload"]) == request_sha256, "INVALID_PREFLIGHT_PROOF", "Original wire payload differs.")
    return proof


def _payload(value):
    _require(type(value) is dict and set(value) <= {"model", "messages", "stream", "think", "keep_alive", "options", "tools"}
             and value.get("model") == MODEL and value.get("stream") is False and value.get("keep_alive", 0) == 0
             and value.get("think") is False, "INVALID_REQUEST", "Only the fixed non-streaming local Qwen request is supported.")
    options, messages, tools = value.get("options"), value.get("messages"), value.get("tools")
    _require(options == {"temperature": 0, "seed": 20261103, "num_predict": 768, "num_ctx": 8192},
             "INVALID_REQUEST", "Use the fixed context and bounded deterministic output.")
    _require(type(messages) is list and 1 <= len(messages) <= 8
             and all(type(item) is dict and set(item) == {"role", "content"}
                     and item["role"] in {"system", "user", "assistant"} and type(item["content"]) is str for item in messages)
             and type(tools) is list and len(tools) == 1 and type(tools[0]) is dict
             and tools[0].get("type") == "function" and type(tools[0].get("function")) is dict
             and tools[0]["function"].get("name") == "propose_research_selection"
             and len(canonical(value).encode("utf-8")) <= 65536,
             "INVALID_REQUEST", "A bounded saved native tool request is required.")
    return copy.deepcopy(value)


def inspect_protocol_evidence(process_evidence):
    """Read a preserved transport only; never load weights, dispatch or consume."""
    from . import project_model_protocol as protocol
    root = safe_path(Path(process_evidence).absolute())

    def read(relative, limit=MAX_RESPONSE):
        path, stat = local_ollama.regular(root / relative, limit)
        raw = path.read_bytes()
        _require(len(raw) == stat.st_size, "EVIDENCE_CHANGED", "Saved protocol evidence changed while reading.")
        return raw

    wire = local_ollama.parse_json(read("wire-request.json", 100000))
    _require(type(wire) is dict and set(wire) == {"payload", "port"},
             "INVALID_REQUEST", "Use the original owned transport wire request.")
    payload = _payload(wire["payload"])
    receipt = local_ollama.parse_json(read("transport-receipt.json", 65536))
    metadata = local_ollama.parse_json(read("response-metadata.json", 65536))
    raw = read("response.bin")
    request_sha, response_sha = fingerprint(payload), hashlib.sha256(raw).hexdigest()
    _require(type(receipt) is dict and receipt.get("schema_version") == "project-model-transport-receipt-v1"
             and receipt.get("execution") == "local_model" and type(metadata) is dict
             and receipt.get("request_sha256") == request_sha and receipt.get("response_sha256") == response_sha
             and metadata.get("raw_sha256") == response_sha and metadata.get("raw_bytes") == len(raw)
             and metadata.get("http_status") == 200,
             "EVIDENCE_CHANGED", "Original request, response metadata and transport receipt must agree.")
    identity = protocol.validate_transport_identity(receipt.get("identity"))
    _require(payload["model"] == identity["model"], "EVIDENCE_CHANGED", "Saved request model identity differs.")
    shown = local_ollama.parse_json(read("server/native-show-evidence.json"))
    support = protocol.native_protocol_support(shown, think=payload["think"])
    response = local_ollama.parse_json(raw)
    _require(type(response) is dict and type(response.get("message")) is dict,
             "INVALID_MODEL_RESPONSE", "Saved response must contain its original assistant message.")
    message = response["message"]
    calls = message.get("tool_calls")
    prefix = "Host-bound research context (untrusted content):\n"
    contexts = [item["content"][len(prefix):] for item in payload["messages"]
                if item["role"] == "user" and item["content"].startswith(prefix)]
    _require(len(contexts) == 1, "INVALID_REQUEST", "One original host context is required.")
    context = local_ollama.parse_json(contexts[0].encode("utf-8"))
    try:
        protocol.parse_response(raw, context, receipt)
        validation = {"status": "accepted", "code": None}
    except ResearchError as error:
        validation = {"status": "rejected", "code": error.code, "message": str(error)}
    reasons = []
    if response.get("done_reason") == "length":
        reasons.append("OUTPUT_LIMIT_REACHED")
    if type(calls) is not list or not calls:
        reasons.append("NATIVE_TOOL_CALL_ABSENT")
    return {"schema_version": "project-local-model-protocol-inspection-v1", "inspection_completed": True,
            "ok": support["status"] == "compatible" and validation["status"] == "accepted",
            "request_sha256": request_sha, "response_sha256": response_sha, "model": payload["model"],
            "compatibility": support, "saved_native_metadata": {"provenance": "preserved_api_show_not_requeried",
                "current_runtime_verified": False},
            "observed_response": {"done": response.get("done"), "done_reason": response.get("done_reason"),
                "eval_count": response.get("eval_count"), "output_limit": payload["options"]["num_predict"],
                "native_tool_call_count": len(calls) if type(calls) is list else 0,
                "content_present": bool(message.get("content")), "reason_codes": reasons},
            "proposal_validation": validation, "model_requests": 0, "processes_started": 0, "network_requests": 0,
            "weights_read": False, "budget_changed": False, "response_consumed": False,
            "automatic_retry": False, "scientific_validation": False}


def _copy(source, destination, digest, size):
    source, before = local_ollama.regular(source, max(size, 65536))
    _require(before.st_size == size, "MODEL_CHANGED", "Local model source size changed.")
    checked = hashlib.sha256(); count = 0
    safe_path(destination.parent).mkdir(parents=True, exist_ok=True)
    with source.open("rb") as incoming, safe_path(destination).open("xb") as outgoing:
        identity = lambda stat: (stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns)
        _require(identity(before) == identity(os.fstat(incoming.fileno())), "MODEL_CHANGED", "Model source changed before copying.")
        while chunk := incoming.read(1024 * 1024):
            count += len(chunk)
            _require(count <= size, "MODEL_CHANGED", "Model source grew during copying.")
            checked.update(chunk); outgoing.write(chunk)
        outgoing.flush(); os.fsync(outgoing.fileno())
        _, after = local_ollama.regular(source, max(size, 65536))
        _require(identity(before) == identity(after) == identity(os.fstat(incoming.fileno())),
                 "MODEL_CHANGED", "Model source identity changed during copying.")
    _require(count == size and checked.hexdigest() == digest, "MODEL_CHANGED", "Copied local bytes differ from the pinned identity.")


class _OfflineOllama(local_ollama.OwnedOllama):
    def acquire(self, **_):
        """Deliberately excludes OwnedOllama's optional `pull` branch."""
        self.assert_owner()
        weights = local_ollama.verify_weights(self.cache, MODEL)
        shown = self.http.request("/api/show", {"model": MODEL})
        _require(type(shown.get("details")) is dict and shown["details"].get("family") == "qwen3"
                 and not shown.get("remote_model") and not shown.get("remote_host"), "INVALID_MODEL", "Expected only local Qwen weights.")
        tags = self.http.request("/api/tags")
        _json(self.output / "native-show-evidence.json", shown); _json(self.output / "native-tags-evidence.json", tags)
        _require(type(tags.get("models")) is list and any(type(item) is dict and item.get("name") == MODEL
                 and item.get("digest") == weights["manifest_sha256"] for item in tags["models"]),
                 "MODEL_CHANGED", "Owned server tag differs from the verified materialized manifest; publisher identity remains separate.")
        from .project_model_protocol import native_protocol_support
        support = native_protocol_support(shown, think=False)
        _require(support["status"] == "compatible", "MODEL_PROTOCOL_INCOMPATIBLE",
                 "Native model declarations do not support the fixed tool/think:false request: "
                 + ", ".join(support["reason_codes"]) + ". No chat request was dispatched.")
        return weights


class ProjectLocalModel:
    def __init__(self, *, cache, executable, output=None, port=11449):
        self.cache, self.executable = Path(cache).absolute(), Path(executable).absolute()
        self.output = Path(output).absolute() if output is not None else None
        if self.output is not None:
            _require(not self.output.is_relative_to(self.cache) and not self.cache.is_relative_to(self.output)
                     and not self.executable.is_relative_to(self.output), "UNSAFE_PATH", "Process evidence must not overlap original model or executable files.")
        _require(type(port) is int and 1024 <= port <= 65535, "INVALID_REQUEST", "A dedicated local port is required.")
        self.port, self._sent = port, False

    def identity(self):
        """Read/hash existing files only; no process, account, download or inference."""
        _require(self.executable.name.lower() == "ollama.exe", "INVALID_EXECUTABLE", "Select an existing Ollama executable.")
        digest, size = local_ollama.file_hash(self.executable, 1_000_000_000)
        self._verified_weights = local_ollama.verify_weights(self.cache, MODEL)
        self._last_identity = {"schema_version": "project-local-model-identity-v1", "transport": "owned-local-ollama", "model": MODEL,
                "publisher_manifest_sha256": self._verified_weights["publisher_manifest_sha256"],
                "executable_sha256": digest, "cloud_disabled": True}
        return copy.deepcopy(self._last_identity)

    def send(self, payload, request_id):
        state = {"phase": "validate", "worker_spawn_attempted": False, "server": None, "root_created": False,
                 "identity": getattr(self, "_last_identity", None)}
        try:
            return self._send_once(payload, request_id, state)
        except Exception as error:
            if not state["worker_spawn_attempted"] and self.output is not None and state["identity"] is not None:
                try:
                    server = state["server"]
                    _require(server is None or getattr(server, "process", None) is None or server.stopped is True,
                             "INVALID_PREFLIGHT_PROOF", "Owned process shutdown is not confirmed.")
                    root = safe_path(self.output)
                    if not state["root_created"]:
                        root.mkdir(parents=True, exist_ok=False)
                    _write(root / "preflight-error.txt", traceback.format_exc().encode("utf-8"))
                    proof = {"schema_version": "project-local-model-preflight-v1", "request_id": request_id,
                             "request_sha256": fingerprint(payload), "identity": state["identity"],
                             "transport_code_identity": code_identity(), "stage": "before_worker_spawn", "phase": state["phase"],
                             "worker_spawn_attempted": False, "chat_dispatched": False, "owned_server_stopped": True,
                             "owned_process_created": server is not None and getattr(server, "process", None) is not None,
                             "output": str(root), "files": _preflight_files(root), "failure_code": getattr(error, "code", type(error).__name__)}
                    path = root / "preflight-no-dispatch.json"; _json(path, proof)
                    reference = {"proof_path": str(path), "proof_sha256": fingerprint(proof)}
                    validate_preflight_no_dispatch(reference, request_id, fingerprint(payload), state["identity"])
                    error.preflight_no_dispatch = reference
                except Exception:
                    pass  # Missing/unverifiable evidence stays unknown; never invent a reset proof.
            raise

    def _send_once(self, payload, request_id, state):
        identifier(request_id); payload = _payload(payload)
        _require(not self._sent, "NEEDS_REVIEW", "This transport never repeats a model request.")
        _require(self.output is not None, "INVALID_REQUEST", "A fresh local process evidence directory is required.")
        self._sent = True
        state["phase"] = "offline_identity"
        identity = self.identity()
        state["identity"] = identity
        root = safe_path(self.output); root.mkdir(parents=True, exist_ok=False)
        state["root_created"] = True; state["phase"] = "copy_verified_originals"
        _json(root / "transport-identity.json", identity)
        isolated_cache = root / "model-cache"
        weights = self._verified_weights
        profile = local_ollama.model_profile(MODEL)
        _copy(self.cache / profile["manifest_relative_path"], isolated_cache / profile["manifest_relative_path"],
              weights["manifest_sha256"], weights["manifest_bytes"])
        for blob in weights["blobs"]:
            relative = Path("blobs") / blob["digest"].replace(":", "-")
            _copy(self.cache / relative, isolated_cache / relative, blob["digest"][7:], blob["bytes"])
        process_output = root / "server"
        process_output.mkdir()
        _json(root / "wire-request.json", {"port": self.port, "payload": payload})
        server = _OfflineOllama(self.executable, isolated_cache, process_output, port=self.port, model=MODEL)
        state["server"] = server; state["phase"] = "native_acquire"
        try:
            with server:
                _require(server.identity["executable_sha256"] == identity["executable_sha256"],
                         "MODEL_CHANGED", "Owned executable changed after offline preparation.")
                acquired = server.acquire()
                _require(acquired == weights, "MODEL_CHANGED", "Owned process changed the prepared weights identity.")
                _json(root / "server-identity.json", server.identity)
                environment = local_ollama.child_environment(isolated_cache, self.port, root / "http-profile")
                environment["PYTHONPATH"] = str(Path(__file__).resolve().parents[1])
                with (root / "worker.stdout.log").open("xb") as stdout, (root / "worker.stderr.log").open("xb") as stderr, local_process.ManagedJob() as job:
                    state["worker_spawn_attempted"] = True
                    worker = job.spawn([sys.executable, "-B", "-m", "autoresearch.project_local_model", "--raw-worker", str(root / "wire-request.json")],
                                       env=environment, cwd=str(root), stdout=stdout, stderr=stderr)
                    try:
                        worker.wait(timeout=TIMEOUT + 5)
                    except subprocess.TimeoutExpired:
                        raise ResearchError("LOCAL_REQUEST_UNKNOWN", "Local response deadline reached; never resend inference.") from None
                    _require(worker.returncode == 0, "LOCAL_REQUEST_UNKNOWN", "Local response unavailable; retain the original reservation.")
                server.assert_owner()
        finally:
            _json(root / "shutdown.json", {"owned_server_stopped": server.stopped,
                                          "generated_task_key_files_removed_without_reading": server.generated_task_key_files_removed})
        raw_path, metadata = local_ollama.regular(root / "response.bin", MAX_RESPONSE)
        raw = raw_path.read_bytes()
        receipt = local_ollama.parse_json((root / "response-metadata.json").read_bytes())
        _require(metadata.st_size == len(raw) == receipt["raw_bytes"] and hashlib.sha256(raw).hexdigest() == receipt["raw_sha256"],
                 "EVIDENCE_CHANGED", "Captured native response bytes changed.")
        receipt = {"schema_version": "project-model-transport-receipt-v1", "identity": identity,
                   "request_sha256": fingerprint(payload), "response_sha256": hashlib.sha256(raw).hexdigest(),
                   "execution": "local_model", "process": {**receipt, "request_id": request_id,
                       "server": server.identity, "owned_server_stopped": server.stopped,
                       "generated_task_key_files_removed_without_reading": server.generated_task_key_files_removed,
                       "automatic_retry": False, "model_requests": 1, "cloud_requests": 0, "new_fits": 0,
                       "transport_code_identity": code_identity(), "scientific_validation": False}}
        _json(root / "transport-receipt.json", receipt)
        return raw, receipt


def _raw_worker(path):
    """One fixed loopback POST; the parent Job bounds the full response lifetime."""
    root = Path(path).absolute().parent
    file, _ = local_ollama.regular(path, 100000)
    request = local_ollama.parse_json(file.read_bytes())
    _require(type(request) is dict and set(request) == {"port", "payload"}
             and type(request["port"]) is int and 1024 <= request["port"] <= 65535,
             "INVALID_REQUEST", "Exact loopback worker request required.")
    payload = _payload(request["payload"])
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), local_ollama.NoRedirect())
    wire = urllib.request.Request(f"http://127.0.0.1:{request['port']}/api/chat", data=canonical(payload).encode("utf-8"),
                                  headers={"Content-Type": "application/json", "Accept-Encoding": "identity"}, method="POST")
    with opener.open(wire, timeout=TIMEOUT) as response:
        raw = response.read(MAX_RESPONSE + 1)
        _require(response.status == 200 and 0 < len(raw) <= MAX_RESPONSE, "LOCAL_REQUEST_UNKNOWN", "Incomplete or oversized local response.")
        metadata = {"http_status": response.status, "content_type": response.headers.get("Content-Type", ""),
                    "raw_sha256": hashlib.sha256(raw).hexdigest(), "raw_bytes": len(raw),
                    "acquired_at_utc": datetime.now(timezone.utc).isoformat()}
    _write(root / "response.bin", raw); _json(root / "response-metadata.json", metadata)


if __name__ == "__main__":
    try:
        _require(len(sys.argv) == 3 and sys.argv[1] == "--raw-worker", "INVALID_REQUEST", "Internal raw worker arguments required.")
        _raw_worker(sys.argv[2])
    except Exception:
        raise SystemExit(2)
