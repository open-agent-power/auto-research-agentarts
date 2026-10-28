"""Official AgentArts HTTP adapter; cloud authentication remains a deployment gate."""

import hashlib
import json
import logging
import math
import os
from pathlib import Path
import re

from agentarts.sdk.runtime import AgentArtsRuntimeApp, RequestContext
from starlette.middleware import Middleware
from starlette.responses import JSONResponse

from .contracts import canonical, fingerprint
from .protocol import FIELDS, handle_request

MAX_BODY_BYTES = 65536
SESSION_HEADER = "x-hw-agentarts-session-id"
logger = logging.getLogger("autoresearch.invocations")


def error(code, message):
    return {"schema_version": "0.1", "request_id": None, "ok": False,
            "error": {"code": code, "message": message}}


def reject_constant(value):
    raise ValueError("non-finite JSON value")


class InvocationBoundary:
    """Bound the body before the SDK parses it; never store request headers."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "websocket":
            await send({"type": "websocket.close", "code": 1008})
            return
        if scope["type"] != "http" or scope["path"] != "/invocations":
            await self.app(scope, receive, send)
            return
        body = bytearray()
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            body.extend(message.get("body", b""))
            if len(body) > MAX_BODY_BYTES:
                await JSONResponse(error("REQUEST_TOO_LARGE", "JSON body exceeds 65536 bytes"),
                                   status_code=413)(scope, receive, send)
                return
            if not message.get("more_body", False):
                break
        try:
            decoded = json.loads(body.decode("utf-8"), parse_constant=reject_constant)
            pending = [(decoded, 0)]
            while pending:
                value, depth = pending.pop()
                if depth > 64:
                    raise ValueError("JSON nesting exceeds 64 levels")
                if isinstance(value, float) and not math.isfinite(value):
                    raise ValueError("non-finite JSON number")
                if isinstance(value, dict):
                    pending.extend((item, depth+1) for item in value.values())
                elif isinstance(value, list):
                    pending.extend((item, depth+1) for item in value)
        except (ValueError, UnicodeError, RecursionError):
            await JSONResponse(error("INVALID_JSON", "expected finite UTF-8 JSON"),
                               status_code=400)(scope, receive, send)
            return
        replayed = False

        async def replay():
            nonlocal replayed
            if not replayed:
                replayed = True
                return {"type": "http.request", "body": bytes(body), "more_body": False}
            return await receive()

        await self.app(scope, replay, send)


def safe_id(value):
    return value if isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9_.:-]{1,160}", value) else None


def create_app(workspace):
    """Use one operator-owned root and a hashed directory per runtime session.

    A session header is a namespace, not authentication. Cloud ingress must be
    authenticated independently; the default CLI binds only to loopback.
    """
    root = Path(workspace)
    if not root.is_absolute():
        raise ValueError("workspace must be an operator-configured absolute path")
    root = root.resolve()
    root.mkdir(parents=True, exist_ok=True)
    app = AgentArtsRuntimeApp(max_concurrency=1, middleware=[Middleware(InvocationBoundary)])

    @app.entrypoint
    def invoke(payload: dict, context: RequestContext):
        session_id = context.session_id
        if not isinstance(session_id, str) or not 1 <= len(session_id) <= 256:
            return error("SESSION_REQUIRED", "supply a stable AgentArts session header")
        session_hash = hashlib.sha256(session_id.encode("utf-8")).hexdigest()
        session_root = root / "sessions" / session_hash
        # The fixed root and hashed session cannot be overridden by a payload path.
        resolved = session_root.resolve()
        if not resolved.is_relative_to(root):
            return error("STORAGE_ERROR", "session storage is outside the configured root")
        response = handle_request(payload, resolved)
        response["transport"] = {
            "adapter": "agentarts-sdk-http-v1",
            "transport_request_id": safe_id(context.request_id),
            "session_fingerprint": session_hash,
            "platform_trace_verified": False,
        }
        action = payload.get("action") if isinstance(payload, dict) else None
        result = response.get("result", {})
        logger.info(canonical({
            "event": "research_invocation",
            "action": action if isinstance(action, str) and action in FIELDS else "invalid",
            "request_id": safe_id(response.get("request_id")),
            "transport_request_id": safe_id(context.request_id),
            "session_fingerprint": session_hash,
            "ok": response["ok"],
            "campaign_id": safe_id(result.get("campaign_id")),
            "trial_id": safe_id(result.get("trial_id")),
            "error_code": response.get("error", {}).get("code"),
            "response_sha256": fingerprint(response),
        }))
        return response

    return app


def server_settings(environ):
    workspace = environ.get("AUTORESEARCH_WORKSPACE")
    if not workspace or not Path(workspace).is_absolute():
        raise ValueError("set AUTORESEARCH_WORKSPACE to an absolute storage directory")
    port = int(environ.get("AGENT_RUN_PORT", "8080"))
    if not 1 <= port <= 65535:
        raise ValueError("AGENT_RUN_PORT must be between 1 and 65535")
    host = environ.get("AUTORESEARCH_BIND_HOST", "127.0.0.1")
    if host not in {"127.0.0.1", "::1", "0.0.0.0"}:
        raise ValueError("unsupported bind address")
    return workspace, host, port


def main():
    workspace, host, port = server_settings(os.environ)
    create_app(workspace).run(host=host, port=port, access_log=False)


if __name__ == "__main__":
    main()
