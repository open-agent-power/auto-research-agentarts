"""Real localhost HTTP fixtures only: no vendor request or model inference."""

from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import math
import os
import socket
import threading
import traceback
import unittest
from unittest.mock import patch

from autoresearch.contracts import ResearchError
from autoresearch.model_client import ChatClient, MAX_RESPONSE_BYTES


KEY_ENV = "AUTORESEARCH_MODEL_CLIENT_FIXTURE_KEY"
FIXTURE_KEY = "local-fixture-secret-not-a-vendor-credential"
MESSAGES = [{"role": "system", "content": "Return a bounded proposal."},
            {"role": "user", "content": "公开材料，只读观察。"}]


def response(**changes):
    value = {"id": "fixture-response", "model": "fixture-model", "choices": [
        {"message": {"content": "A local fixture response; no model inference."}}],
        "usage": {"prompt_tokens": 12, "completion_tokens": 8, "total_tokens": 20}}
    value.update(changes)
    return value


@contextmanager
def fixture_server(body=None, status=200, headers=None):
    records = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def do_POST(self):
            raw = self.rfile.read(int(self.headers.get("Content-Length", "0")))
            records.append({"path": self.path, "body": raw, "headers": dict(self.headers)})
            value = response() if body is None else body
            encoded = value if isinstance(value, bytes) else json.dumps(value, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            for name, content in (headers or {}).items():
                self.send_header(name, content)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            try:
                self.wfile.write(encoded)
            except (BrokenPipeError, ConnectionResetError):
                pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    worker = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": .01}, daemon=True)
    worker.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/openai/v1/chat/completions", records
    finally:
        server.shutdown()
        server.server_close()
        worker.join(5)


class ModelClientTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {KEY_ENV: FIXTURE_KEY})
        self.env.start()
        self.addCleanup(self.env.stop)

    def client(self, endpoint="https://example.invalid/v1/chat/completions", **changes):
        config = {"endpoint": endpoint, "model": "fixture-model", "api_key_env": KEY_ENV}
        config.update(changes)
        return ChatClient(config)

    def assert_error(self, code, call):
        with self.assertRaises(ResearchError) as caught:
            call()
        self.assertEqual(caught.exception.code, code)
        self.assertNotIn(FIXTURE_KEY, str(caught.exception))
        self.assertNotIn(FIXTURE_KEY, repr(caught.exception))
        return caught.exception

    def test_preflight_is_local_json_safe_and_never_exposes_credentials(self):
        client = self.client()
        with patch("autoresearch.model_client.build_opener", side_effect=AssertionError("no preflight network")):
            info = client.preflight()
        self.assertFalse(info["fixture"])
        self.assertFalse(info["network_verified"])
        self.assertEqual(info["api_key_env"], KEY_ENV)
        self.assertEqual(info["max_output_tokens"], 768)
        self.assertEqual(info["max_prompt_bytes"], 24000)
        self.assertEqual(info["timeout_seconds"], 30)
        self.assertEqual(info["output_token_parameter"], "max_completion_tokens")
        self.assertNotIn(FIXTURE_KEY, json.dumps(info, allow_nan=False))
        self.assertNotIn(FIXTURE_KEY, repr(client))
        self.assertNotIn(FIXTURE_KEY, repr(vars(client)))

    def test_real_post_sends_deterministic_payload_and_marks_loopback_fixture(self):
        with fixture_server() as (endpoint, records):
            client = self.client(endpoint, allow_loopback_http=True)
            info = client.preflight()
            self.assertTrue(info["fixture"])
            with patch.dict(os.environ, {"HTTP_PROXY": "http://127.0.0.1:1", "NO_PROXY": ""}):
                result = client.complete(MESSAGES, "fixture-call-1")
            self.assertEqual(len(records), 1)
            self.assertEqual(records[0]["path"], "/openai/v1/chat/completions")
            self.assertEqual(records[0]["headers"]["Authorization"], "Bearer " + FIXTURE_KEY)
            self.assertEqual(records[0]["headers"]["X-Request-Id"], "fixture-call-1")
            self.assertEqual(json.loads(records[0]["body"]), client.prepare(MESSAGES))
            self.assertEqual(result, {"response_id": "fixture-response", "model": "fixture-model",
                                     "content": response()["choices"][0]["message"]["content"],
                                     "usage": {"prompt_tokens": 12, "completion_tokens": 8, "total_tokens": 20}})

    def test_prepare_has_one_selected_output_cap_and_no_streaming(self):
        for parameter in ("max_completion_tokens", "max_tokens"):
            client = self.client(output_token_parameter=parameter)
            first, second = client.prepare(MESSAGES), client.prepare(MESSAGES)
            self.assertEqual(first, second)
            self.assertFalse(first["stream"])
            self.assertEqual(first[parameter], 768)
            self.assertEqual(set(first) & {"max_tokens", "max_completion_tokens"}, {parameter})
            first["messages"][0]["content"] = "changed"
            self.assertEqual(client.prepare(MESSAGES), second)

    def test_limits_types_endpoint_and_roles_are_restricted(self):
        for setting, values in {
            "max_output_tokens": (0, 2049, True, 1.5),
            "max_prompt_bytes": (0, 64001, False, "24000"),
            "timeout_seconds": (0, 61, math.nan, math.inf, 10**400, True),
            "allow_loopback_http": (1, "true"),
            "output_token_parameter": ("both", None),
        }.items():
            for value in values:
                self.assert_error("INVALID_REQUEST", lambda s=setting, v=value: self.client(**{s: v}))
        for endpoint in ("http://example.com/chat", "http://127.0.0.1/chat", "ftp://example.com/chat",
                         "https://user:password@example.com/chat", "https://user@example.com/chat",
                         "https://example.com/chat?q=secret", "https://example.com/chat#secret",
                         "https://example.com/chat?", "https://example.com:0/chat", "https://example.com:bad/chat",
                         "https://example.com/\nchat", " https://example.com/chat", "https:///chat"):
            self.assert_error("INVALID_REQUEST", lambda e=endpoint: self.client(e))
        for hostname in ("localhost", "127.0.0.1", "[::1]"):
            self.assertTrue(self.client(f"http://{hostname}:8080/chat", allow_loopback_http=True).preflight()["fixture"])
        self.assert_error("INVALID_REQUEST", lambda: self.client("http://127.0.0.2/chat", allow_loopback_http=True))
        self.assert_error("INVALID_REQUEST", lambda: self.client(api_key=FIXTURE_KEY))
        for messages in ([], {}, [{"role": "assistant", "content": "x"}],
                         [{"role": "tool", "content": "x"}], [{"role": "user", "content": []}],
                         [{"role": "user", "content": math.nan}], [{"role": "user", "content": " "}],
                         [{"role": "user", "content": "x", "tool_calls": []}],
                         [{"role": "user", "content": "\ud800"}]):
            self.assert_error("INVALID_REQUEST", lambda m=messages: self.client().prepare(m))

    def test_utf8_limit_covers_actual_complete_json_body(self):
        client = self.client()
        payload = client.prepare(MESSAGES)
        size = len(json.dumps(payload, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8"))
        self.assertEqual(self.client(max_prompt_bytes=size).prepare(MESSAGES), payload)
        self.assert_error("INVALID_REQUEST", lambda: self.client(max_prompt_bytes=size - 1).prepare(MESSAGES))

    def test_missing_credentials_make_no_http_call_and_do_not_use_other_env(self):
        with fixture_server() as (endpoint, records):
            with patch.dict(os.environ, {KEY_ENV: "", "OPENAI_API_KEY": "unrelated-software-key"}):
                client = self.client(endpoint, allow_loopback_http=True)
                self.assert_error("CONFIG_REQUIRED", client.preflight)
                self.assert_error("CONFIG_REQUIRED", lambda: client.complete(MESSAGES, "missing-key"))
            self.assertEqual(records, [])

    def test_http_errors_are_sanitized_and_not_retried(self):
        for status in (401, 429, 500):
            with fixture_server(body=("sensitive-body " + FIXTURE_KEY).encode(), status=status) as (endpoint, records):
                error = self.assert_error("MODEL_HTTP_ERROR", lambda: self.client(endpoint, allow_loopback_http=True).complete(MESSAGES, "http-error"))
                self.assertEqual(error.http_status, status)
                self.assertEqual(len(records), 1)
                formatted = "".join(traceback.format_exception(error))
                self.assertNotIn("sensitive-body", formatted)
                self.assertNotIn(endpoint, formatted)
                self.assertNotIn(FIXTURE_KEY, formatted)
                self.assertIsNone(error.__context__)

    def test_all_http_redirects_are_rejected_without_second_request(self):
        with fixture_server() as (target, target_records):
            for status in (301, 302, 303, 307, 308):
                with fixture_server(status=status, headers={"Location": target}) as (endpoint, records):
                    error = self.assert_error("MODEL_HTTP_ERROR", lambda: self.client(endpoint, allow_loopback_http=True).complete(MESSAGES, "redirect"))
                    self.assertEqual(error.http_status, status)
                    self.assertEqual(len(records), 1)
            self.assertEqual(target_records, [])

    def test_network_errors_are_sanitized_and_not_retried(self):
        with socket.socket() as blocked:
            blocked.bind(("127.0.0.1", 0))
            endpoint = f"http://127.0.0.1:{blocked.getsockname()[1]}/fixture-only"
            error = self.assert_error("MODEL_NETWORK_ERROR", lambda: self.client(endpoint, allow_loopback_http=True).complete(MESSAGES, "network-error"))
        self.assertNotIn(endpoint, "".join(traceback.format_exception(error)))
        self.assertIsNone(error.__context__)

    def test_usage_details_are_preserved_without_double_counting_reasoning(self):
        usage = {"prompt_tokens": 12, "completion_tokens": 8, "total_tokens": 20,
                 "completion_tokens_details": {"reasoning_tokens": 6, "audio_tokens": 0},
                 "prompt_tokens_details": {"cached_tokens": 4}}
        with fixture_server(response(usage=usage)) as (endpoint, _):
            result = self.client(endpoint, allow_loopback_http=True).complete(MESSAGES, "usage-details")
        self.assertEqual(result["usage"], usage)
        self.assertEqual(result["usage"]["total_tokens"], 20)

    def test_missing_invalid_and_excess_usage_are_rejected(self):
        bad_usages = [None, {}, {"prompt_tokens": 12, "completion_tokens": 8},
                      {"prompt_tokens": True, "completion_tokens": 8, "total_tokens": 9},
                      {"prompt_tokens": 12.0, "completion_tokens": 8, "total_tokens": 20},
                      {"prompt_tokens": -1, "completion_tokens": 8, "total_tokens": 7},
                      {"prompt_tokens": 12, "completion_tokens": 8, "total_tokens": 21},
                      {"prompt_tokens": 12, "completion_tokens": 769, "total_tokens": 781}]
        for detail in (None, [], {"reasoning_tokens": -1}, {"reasoning_tokens": True},
                       {"reasoning_tokens": 1.5}, {"reasoning_tokens": 9}):
            bad_usages.append({"prompt_tokens": 12, "completion_tokens": 8, "total_tokens": 20,
                               "completion_tokens_details": detail})
        for usage in bad_usages:
            with fixture_server(response(usage=usage)) as (endpoint, records):
                self.assert_error("MODEL_RESPONSE_INVALID", lambda: self.client(endpoint, allow_loopback_http=True).complete(MESSAGES, "bad-usage"))
                self.assertEqual(len(records), 1)

    def test_malformed_responses_nonfinite_json_and_empty_content_are_rejected(self):
        valid_prefix = json.dumps(response()).encode("utf-8")[:-1]
        cases = [b"not-json", b"\xff", valid_prefix + b',"extra":NaN}',
                 valid_prefix + b',"extra":1e999}',
                 valid_prefix + b',"usage":{"prompt_tokens":12,"completion_tokens":8,"total_tokens":20}}',
                 response(choices=[]),
                 response(choices=[{"message": {"content": " "}}]),
                 response(choices=[{"message": {"content": []}}]),
                 response(id=""), response(model=""), []]
        missing_usage = response()
        del missing_usage["usage"]
        cases.append(missing_usage)
        for value in cases:
            with fixture_server(value) as (endpoint, _):
                self.assert_error("MODEL_RESPONSE_INVALID", lambda: self.client(endpoint, allow_loopback_http=True).complete(MESSAGES, "bad-response"))

    def test_response_byte_limit_is_enforced_before_json_decode(self):
        with fixture_server(b"x" * (MAX_RESPONSE_BYTES + 1)) as (endpoint, records):
            self.assert_error("MODEL_RESPONSE_TOO_LARGE", lambda: self.client(endpoint, allow_loopback_http=True).complete(MESSAGES, "oversized"))
            self.assertEqual(len(records), 1)

    def test_response_at_exact_byte_limit_is_accepted(self):
        raw = json.dumps(response()).encode("utf-8")
        padded = raw + b" " * (MAX_RESPONSE_BYTES - len(raw))
        with fixture_server(padded) as (endpoint, records):
            result = self.client(endpoint, allow_loopback_http=True).complete(MESSAGES, "exact-limit")
        self.assertEqual(result["response_id"], "fixture-response")
        self.assertEqual(len(records), 1)

    def test_secret_echo_is_rejected_in_any_returned_text(self):
        for value in (response(id=FIXTURE_KEY), response(model=FIXTURE_KEY),
                      response(choices=[{"message": {"content": "echo: " + FIXTURE_KEY}}]),
                      response(usage={"prompt_tokens": 12, "completion_tokens": 8, "total_tokens": 20,
                                      "completion_tokens_details": {FIXTURE_KEY: 0}})):
            with fixture_server(value) as (endpoint, _):
                self.assert_error("MODEL_RESPONSE_INVALID", lambda: self.client(endpoint, allow_loopback_http=True).complete(MESSAGES, "secret-echo"))
        self.assert_error("INVALID_REQUEST", lambda: self.client(model=FIXTURE_KEY).preflight())


if __name__ == "__main__":
    unittest.main()
