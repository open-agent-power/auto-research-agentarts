"""Small OpenAI-compatible HTTP boundary; no retries, pricing or SDK state.

The operator supplies the complete chat endpoint. Preflight validates local
configuration only; it does not establish a cloud connection. Loopback endpoints
are fixtures, including when HTTPS is used. Credentials are read on demand from
one named environment variable and are never retained on the client object.
"""

from http.client import HTTPException
import json
import math
import os
import re
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

from .contracts import ResearchError, identifier


MAX_RESPONSE_BYTES = 256 * 1024
_LOOPBACK_HOSTS = {"localhost", "127.0.0.1", "::1"}
_SETTINGS = {
    "endpoint", "model", "api_key_env", "max_output_tokens", "max_prompt_bytes",
    "timeout_seconds", "allow_loopback_http", "output_token_parameter",
}


class ModelClientError(ResearchError):
    """Sanitized failure; HTTP status is metadata, never a response-body echo."""

    def __init__(self, code, message, http_status=None):
        super().__init__(code, message)
        self.http_status = http_status


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _bounded_integer(config, name, default, maximum):
    value = config.get(name, default)
    if type(value) is not int or not 1 <= value <= maximum:
        raise ModelClientError("INVALID_REQUEST", "invalid connection limit: " + name)
    return value


def _json_bytes(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8")


def _invalid_json(_):
    raise ValueError("nonfinite JSON")


def _finite_float(value):
    result = float(value)
    if not math.isfinite(result):
        raise ValueError("nonfinite JSON")
    return result


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON member")
        result[key] = value
    return result


def _contains_secret(value, secret):
    if isinstance(value, str):
        return secret in value
    if isinstance(value, dict):
        return any(_contains_secret(key, secret) or _contains_secret(item, secret)
                   for key, item in value.items())
    if isinstance(value, list):
        return any(_contains_secret(item, secret) for item in value)
    return False


class ChatClient:
    def __init__(self, config: dict):
        if not isinstance(config, dict) or set(config) - _SETTINGS:
            raise ModelClientError("INVALID_REQUEST", "unsupported connection configuration")
        endpoint, model = config.get("endpoint"), config.get("model")
        if endpoint in (None, "") or model in (None, ""):
            raise ModelClientError("CONFIG_REQUIRED", "model endpoint and model are required")
        if (not isinstance(endpoint, str) or len(endpoint) > 2048
                or not isinstance(model, str) or not 1 <= len(model.strip()) <= 256
                or any(ord(char) < 32 or ord(char) == 127 for char in endpoint + model)
                or any(char.isspace() for char in endpoint)):
            raise ModelClientError("INVALID_REQUEST", "invalid model endpoint or model")
        try:
            endpoint.encode("ascii")
            parsed = urlsplit(endpoint)
            port = parsed.port
        except (ValueError, UnicodeError):
            raise ModelClientError("INVALID_REQUEST", "invalid model endpoint") from None
        allow_http = config.get("allow_loopback_http", False)
        if type(allow_http) is not bool:
            raise ModelClientError("INVALID_REQUEST", "allow_loopback_http must be boolean")
        fixture = parsed.hostname in _LOOPBACK_HOSTS
        if (not parsed.hostname or parsed.username is not None or parsed.password is not None
                or parsed.query or parsed.fragment or "?" in endpoint or "#" in endpoint
                or (port is not None and not 1 <= port <= 65535)
                or (parsed.scheme != "https" and not (parsed.scheme == "http" and allow_http and fixture))):
            raise ModelClientError("INVALID_REQUEST", "endpoint must be HTTPS or an explicit loopback HTTP fixture")
        env_name = config.get("api_key_env", "AUTORESEARCH_API_KEY")
        if not isinstance(env_name, str) or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,127}", env_name):
            raise ModelClientError("INVALID_REQUEST", "invalid api_key_env name")
        timeout = config.get("timeout_seconds", 30)
        if type(timeout) not in (int, float) or not 0 < timeout <= 60 or not math.isfinite(timeout):
            raise ModelClientError("INVALID_REQUEST", "timeout_seconds must be finite and at most 60")
        token_parameter = config.get("output_token_parameter", "max_completion_tokens")
        if token_parameter not in ("max_completion_tokens", "max_tokens"):
            raise ModelClientError("INVALID_REQUEST", "invalid output_token_parameter")
        self.endpoint = endpoint
        self.model = model
        self.api_key_env = env_name
        self.max_output_tokens = _bounded_integer(config, "max_output_tokens", 768, 2048)
        self.max_prompt_bytes = _bounded_integer(config, "max_prompt_bytes", 24000, 64000)
        self.timeout_seconds = timeout
        self.output_token_parameter = token_parameter
        self.fixture = fixture

    def __repr__(self):
        return f"<ChatClient fixture={self.fixture}>"

    def _api_key(self):
        key = os.environ.get(self.api_key_env)
        if not key or not key.strip():
            raise ModelClientError("CONFIG_REQUIRED", "configured model API key environment variable is missing")
        if any(ord(char) < 33 or ord(char) > 126 for char in key):
            raise ModelClientError("CONFIG_REQUIRED", "configured model API key is not a valid HTTP token")
        return key

    def preflight(self):
        """Inspect configuration and credential availability without any HTTP I/O."""
        key = self._api_key()
        info = {
            "endpoint": self.endpoint, "model": self.model, "api_key_env": self.api_key_env,
            "max_output_tokens": self.max_output_tokens, "max_prompt_bytes": self.max_prompt_bytes,
            "timeout_seconds": self.timeout_seconds, "output_token_parameter": self.output_token_parameter,
            "max_response_bytes": MAX_RESPONSE_BYTES, "fixture": self.fixture,
            "network_verified": False, "automatic_retries": 0, "redirects_allowed": False,
            "environment_proxy_used": False,
        }
        if _contains_secret(info, key):
            raise ModelClientError("INVALID_REQUEST", "connection metadata contains credential material")
        return info

    def prepare(self, messages):
        """Return deterministic JSON data; the limit covers the full UTF-8 body."""
        if not isinstance(messages, list) or not messages:
            raise ModelClientError("INVALID_REQUEST", "messages must be a nonempty list")
        clean = []
        for message in messages:
            if (not isinstance(message, dict) or set(message) != {"role", "content"}
                    or message["role"] not in ("system", "user")
                    or not isinstance(message["content"], str) or not message["content"].strip()):
                raise ModelClientError("INVALID_REQUEST", "messages require system/user roles and nonempty text only")
            clean.append({"role": message["role"], "content": message["content"]})
        payload = {"model": self.model, "messages": clean, "stream": False,
                   self.output_token_parameter: self.max_output_tokens}
        try:
            body = _json_bytes(payload)
        except (ValueError, UnicodeError, TypeError):
            raise ModelClientError("INVALID_REQUEST", "model request is not valid UTF-8 JSON") from None
        if len(body) > self.max_prompt_bytes:
            raise ModelClientError("INVALID_REQUEST", "model request exceeds max_prompt_bytes")
        return payload

    def complete(self, messages, request_id):
        payload = self.prepare(messages)
        identifier(request_id)
        key = self._api_key()
        request = Request(self.endpoint, data=_json_bytes(payload), method="POST", headers={
            "Authorization": "Bearer " + key, "Content-Type": "application/json; charset=utf-8",
            "Accept": "application/json", "X-Request-ID": request_id,
        })
        # Explicit direct transport also avoids inheriting unrelated proxy credentials.
        opener = build_opener(ProxyHandler({}), _NoRedirect())
        failure = None
        try:
            with opener.open(request, timeout=self.timeout_seconds) as response:
                raw = response.read(MAX_RESPONSE_BYTES + 1)
        except HTTPError as exc:
            status = exc.code
            exc.close()
            failure = ModelClientError("MODEL_HTTP_ERROR", f"model request failed (HTTP {status})", status)
        except (URLError, OSError, HTTPException, ValueError, UnicodeError):
            failure = ModelClientError("MODEL_NETWORK_ERROR", "model request failed during transport")
        if failure is not None:
            # Raise outside the handler so the original URL/body exception is not chained.
            raise failure
        if len(raw) > MAX_RESPONSE_BYTES:
            raise ModelClientError("MODEL_RESPONSE_TOO_LARGE", "model response exceeds the fixed byte limit")
        result = self._decode_response(raw)
        if _contains_secret(result, key):
            raise ModelClientError("MODEL_RESPONSE_INVALID", "model response contains credential material")
        return result

    def _decode_response(self, raw):
        try:
            data = json.loads(raw.decode("utf-8"), parse_constant=_invalid_json,
                              parse_float=_finite_float, object_pairs_hook=_unique_object)
            response_id, model = data["id"], data["model"]
            content = data["choices"][0]["message"]["content"]
            usage = data["usage"]
            if not all(isinstance(value, str) and value.strip() for value in (response_id, model, content)):
                raise ValueError("missing text")
            counts = {name: usage[name] for name in ("prompt_tokens", "completion_tokens", "total_tokens")}
            if (any(type(value) is not int or value < 0 for value in counts.values())
                    or counts["total_tokens"] != counts["prompt_tokens"] + counts["completion_tokens"]
                    or counts["completion_tokens"] > self.max_output_tokens):
                raise ValueError("invalid usage")
            for name, bound in (("completion_tokens_details", counts["completion_tokens"]),
                                ("prompt_tokens_details", counts["prompt_tokens"])):
                if name in usage:
                    details = usage[name]
                    if not isinstance(details, dict) or any(
                            type(value) is not int or not 0 <= value <= bound for value in details.values()):
                        raise ValueError("invalid usage details")
                    counts[name] = dict(details)
            return {"response_id": response_id, "model": model, "content": content, "usage": counts}
        except (ValueError, KeyError, TypeError, IndexError, UnicodeError, RecursionError):
            raise ModelClientError("MODEL_RESPONSE_INVALID", "model response text or usage is invalid") from None
