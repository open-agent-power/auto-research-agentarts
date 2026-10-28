"""Scripted HTTP test endpoint. This is deliberately not a language model."""

from contextlib import contextmanager
from datetime import date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import threading

KEY_ENV = "AUTORESEARCH_LOOPBACK_FIXTURE_KEY"
FIXTURE_KEY = "local-http-fixture-only-not-a-real-model-key"


def configuration(endpoint):
    return {"connection": {"endpoint": endpoint, "model": "scripted-loopback-not-an-llm", "api_key_env": KEY_ENV,
                           "allow_loopback_http": True, "max_output_tokens": 768, "max_prompt_bytes": 64000,
                           "output_token_parameter": "max_completion_tokens", "timeout_seconds": 10},
            "pricing": {"input_cny_per_million": "2", "output_cny_per_million": "8", "input_tokens_ceiling": 10000,
                        "source_url": "https://example.invalid/fixture-simulated-prices",
                        "input_ceiling_source_url": "https://example.invalid/fixture-simulated-token-ceiling",
                        "checked_on": date.today().isoformat(), "verified": True,
                        "output_cap_covers_all_billed_tokens": True}}


def decision(observation):
    trials = observation["trials"]
    cited = [trials[-1]["id"]] if trials else []
    common = {"observation_sha256": observation["observation_sha256"], "evidence_trial_ids": cited}
    if len(trials) >= 3:
        return {"action": "stop", "reason": "FIXTURE stop after three real feedback actions; this scripted policy is not an LLM.", **common}
    if not trials:
        candidate = {"degree": 1, "alpha": 1.0}
        hypothesis = "FIXTURE baseline: measure a linear recipe before comparing interactions."
    elif len(trials) == 1:
        candidate = {"degree": 2, "alpha": 1.0}
        hypothesis = f"FIXTURE interaction probe after observed validation MSE {trials[-1]['metrics']['validation_mse']:.6g}."
    else:
        # Read actual acceptance/metrics; never assert a prerecorded training score.
        rejected = trials[-1]["status"] == "rejected"
        candidate = {"degree": 1 if rejected else 2, "alpha": .01 if rejected else 1000.0}
        hypothesis = "FIXTURE feedback branch: rejected interactions prompt a linear comparison." if rejected else "FIXTURE feedback branch: compare stronger regularization."
    return {"action": "propose", "proposal": {**common, "hypothesis": hypothesis,
            "expected_effect": "A measured comparison under the frozen evaluator, with possible rejection; no scientific claim.",
            "candidate": candidate}}


@contextmanager
def model_fixture(mode="normal"):
    records = []
    lock = threading.Lock()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def do_POST(self):
            raw = self.rfile.read(int(self.headers.get("Content-Length", "0")))
            payload = json.loads(raw)
            observation = json.loads(payload["messages"][-1]["content"])["observation"]
            with lock:
                ordinal = len(records) + 1
                record = {"ordinal": ordinal, "request_id": self.headers.get("X-Request-ID"),
                          "path": self.path, "payload": payload, "fixture": True}
                records.append(record)
            if mode == "http_error":
                self.send_response(503)
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            chosen = decision(observation)
            content = json.dumps(chosen, ensure_ascii=False)
            if mode == "always_invalid" or (mode == "invalid_first" and ordinal == 1):
                content = "FIXTURE invalid JSON decision"
            usage = {"prompt_tokens": 200 if mode != "over_input" else 20000,
                     "completion_tokens": 100, "total_tokens": 300 if mode != "over_input" else 20100,
                     "completion_tokens_details": {"reasoning_tokens": 20}}
            response = {"id": f"fixture-response-{ordinal}", "model": "scripted-loopback-not-an-llm",
                        "choices": [{"message": {"role": "assistant", "content": content}}], "usage": usage}
            record["response"] = response
            encoded = json.dumps(response, ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    worker = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": .01}, daemon=True)
    worker.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/openai/v1/chat/completions", records
    finally:
        server.shutdown()
        server.server_close()
        worker.join(5)
