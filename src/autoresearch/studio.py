"""Single-operator loopback viewer with an explicitly enabled local-only demo."""
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import secrets
import sqlite3
import time

from .contracts import ResearchError, canonical
from .studio_project import ProjectStore
from .studio_outputs import ProjectOutputs
from .local_demo import LocalDemo


def _object(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("duplicate JSON key")
        value[key] = item
    return value


def _nonfinite(value):
    raise ValueError("nonfinite JSON")


def create_server(workspace, port=8766, *, local_demo=False):
    if type(port) is not int or not 0 <= port <= 65535:
        raise ResearchError("INVALID_REQUEST", "invalid local port")
    store = ProjectStore(workspace)
    store.verify()
    outputs = ProjectOutputs(store)
    demo = LocalDemo(store.root, store.project()["snapshot"]["sha256"], enabled=local_demo)
    token = secrets.token_urlsafe(32)
    assets = Path(__file__).with_name("web")

    class Handler(BaseHTTPRequestHandler):
        server_version = "LocalResearch/1"

        def log_message(self, *args):
            pass  # Do not log operator notes, tokens or request headers.

        def send(self, status, data, mime="application/json; charset=utf-8", filename=None):
            self.send_response(status)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            # X6 sets SVG/HTML geometry through inline styles and draws its local grid
            # as a data image. Scripts stay local, without inline code or eval.
            self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'")
            if filename:
                self.send_header("Content-Disposition", 'attachment; filename="'+filename+'"')
            self.end_headers()
            self.wfile.write(data)

        def reply(self, status, value):
            self.send(status, canonical(value).encode("utf-8"))

        def host_ok(self):
            hosts = self.headers.get_all("Host", [])
            return len(hosts) == 1 and hosts[0] in {
                f"127.0.0.1:{self.server.server_port}", f"localhost:{self.server.server_port}"}

        def error(self, status, code, message):
            # On Windows, closing with an unread small request body can reset the
            # connection before a rejection reaches the client. Drain only a
            # bounded, explicitly sized body; never wait for arbitrary uploads.
            if self.command == "POST" and not getattr(self, "_body_consumed", False):
                sizes = self.headers.get_all("Content-Length", [])
                if (not self.headers.get("Transfer-Encoding") and len(sizes) == 1
                        and 1 <= len(sizes[0]) <= 5 and sizes[0].isascii() and sizes[0].isdigit()
                        and 1 <= int(sizes[0]) <= 8193):
                    try:
                        deadline = time.monotonic() + 1
                        remaining = int(sizes[0])
                        while remaining:
                            timeout = deadline - time.monotonic()
                            if timeout <= 0:
                                break
                            self.connection.settimeout(timeout)
                            chunk = self.rfile.read1(remaining)
                            if not chunk:
                                break
                            remaining -= len(chunk)
                    except OSError:
                        pass
                    self._body_consumed = True
            self.reply(status, {"ok":False, "error":{"code":code,"message":message}})

        def do_GET(self):
            if not self.host_ok():
                return self.error(403, "HOST_DENIED", "only the configured loopback host is accepted")
            try:
                if self.path == "/favicon.ico":
                    return self.send(204,b"","image/x-icon")
                static = {"/":("index.html","text/html; charset=utf-8"),
                          "/app.js":("app.js","text/javascript; charset=utf-8"),
                          "/app.css":("app.css","text/css; charset=utf-8"),
                          "/vendor-licenses.txt":("vendor-licenses.txt","text/plain; charset=utf-8")}
                if self.path in static:
                    name,mime = static[self.path]
                    return self.send(200, (assets/name).read_bytes(), mime)
                if self.path == "/api/project":
                    return self.reply(200, {**store.project(), "csrf_token":token})
                if self.path == "/api/local-demo":
                    store.verify()
                    return self.reply(200, demo.status())
                figures = {"/api/figures/validation.svg":"validation.svg", "/api/figures/prediction.svg":"prediction.svg"}
                if self.path in figures:
                    return self.send(200,outputs.figure(figures[self.path]),"image/svg+xml")
                downloads = {"/api/export/paper.pdf":("research-paper.pdf","application/pdf"),
                             "/api/export/reproduction.zip":("reproduction.zip","application/zip")}
                if self.path in downloads:
                    with outputs.lock:
                        outputs.export()
                        name,mime = downloads[self.path]
                        return self.send(200,(outputs.exports/name).read_bytes(),mime,name)
                return self.error(404,"NOT_FOUND","page or artifact not found")
            except ResearchError as exc:
                return self.error(409,exc.code,str(exc))
            except (OSError, ValueError, KeyError):
                return self.error(500,"ARTIFACT_UNAVAILABLE","local artifact could not be read; inspect it before retrying")

        def do_POST(self):
            if not self.host_ok():
                return self.error(403,"HOST_DENIED","only the configured loopback host is accepted")
            origins = self.headers.get_all("Origin", [])
            if len(origins) > 1 or (origins and origins[0] not in {
                    f"http://127.0.0.1:{self.server.server_port}", f"http://localhost:{self.server.server_port}"}):
                return self.error(403,"ORIGIN_DENIED","request origin is not this local project")
            tokens = self.headers.get_all("X-Research-CSRF", [])
            if len(tokens) != 1 or not tokens[0].isascii() or not hmac.compare_digest(tokens[0], token):
                return self.error(403,"CSRF_DENIED","refresh the project before saving")
            if self.path not in {"/api/questions", "/api/local-demo/step"}:
                return self.error(404,"NOT_FOUND","no research execution endpoint is exposed")
            is_demo = self.path == "/api/local-demo/step"
            if is_demo and not demo.enabled:
                return self.error(403,"LOCAL_DEMO_DISABLED","本地演示未启用。")
            if self.headers.get_content_type() != "application/json":
                return self.error(415,"INVALID_REQUEST","JSON content type is required")
            sizes = self.headers.get_all("Content-Length", [])
            if (self.headers.get("Transfer-Encoding") or len(sizes) != 1 or not 1 <= len(sizes[0]) <= 5
                    or not sizes[0].isascii() or not sizes[0].isdigit() or not 1 <= int(sizes[0]) <= 8192):
                return self.error(413,"INVALID_REQUEST","request must have a bounded JSON body")
            self.connection.settimeout(5)
            executing_demo = False
            try:
                raw = self.rfile.read(int(sizes[0]))
                self._body_consumed = True
                if len(raw) != int(sizes[0]):
                    raise ValueError("incomplete body")
                value = json.loads(raw.decode("utf-8"), object_pairs_hook=_object, parse_constant=_nonfinite)
                expected = {"request_id"} if is_demo else {"text"}
                if not isinstance(value,dict) or set(value) != expected:
                    raise ValueError("unsupported request fields")
                if is_demo:
                    executing_demo = True
                    store.verify()
                    result = demo.step(value["request_id"])
                    return self.reply(200 if result["replayed"] else 202,result)
                item = store.add_question(value["text"])
                return self.reply(201,{"ok":True,"question":item})
            except ResearchError as exc:
                status = (403 if exc.code == "LOCAL_DEMO_DISABLED" else 400 if exc.code == "INVALID_REQUEST" else 409) if is_demo else 400
                return self.error(status,exc.code,str(exc))
            except sqlite3.Error:
                return self.error(500,"LOCAL_DEMO_STORAGE_ERROR","本地演示存储不可用，请核查后重试。")
            except (ValueError, UnicodeError, RecursionError, OSError):
                if executing_demo:
                    return self.error(500,"LOCAL_DEMO_STORAGE_ERROR","本地演示存储不可用，请核查后重试。")
                return self.error(400,"INVALID_REQUEST","a complete UTF-8 JSON question is required")

    server = ThreadingHTTPServer(("127.0.0.1",port),Handler)
    server.daemon_threads = True
    server.project_store = store
    server.project_outputs = outputs
    server.local_demo = demo
    return server


def serve(workspace, port=8766, *, local_demo=False):
    with create_server(workspace, port, local_demo=local_demo) as server:
        print(canonical({"ready":True,"url":f"http://127.0.0.1:{server.server_port}","cloud_calls":0}),flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
