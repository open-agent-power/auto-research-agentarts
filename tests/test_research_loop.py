import copy
from datetime import date, timedelta
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from autoresearch.contracts import ResearchError
from autoresearch.model_client import ChatClient
from autoresearch.research_loop import ResearchLoop, cost_micros, parse_decision

_path = Path(__file__).resolve().parents[1] / "scripts/loopback_model_fixture.py"
_spec = importlib.util.spec_from_file_location("loopback_model_fixture", _path)
fixture = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(fixture)


class ResearchLoopTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.loop = ResearchLoop(self.tmp.name)
        self.key = patch.dict(os.environ, {fixture.KEY_ENV: fixture.FIXTURE_KEY})
        self.key.start()
        self.addCleanup(self.key.stop)

    def error(self, code, operation):
        with self.assertRaises(ResearchError) as caught:
            operation()
        self.assertEqual(caught.exception.code, code)

    def configure(self, endpoint, **limits):
        config = fixture.configuration(endpoint)
        self.loop.configure("Test product-owned research loop with fixture model responses.", config, **limits)
        return config

    def test_real_http_fixture_drives_three_real_trainings_and_stops(self):
        with fixture.model_fixture() as (endpoint, requests):
            config = self.configure(endpoint)
            result = self.loop.run(config)
            self.assertEqual(len(requests), 4)
        state = result["state"]
        self.assertEqual(state["status"], "stopped")
        self.assertTrue(state["fixture"])
        self.assertEqual(state["live_model_responses_received"], 0)
        self.assertEqual(state["live_model_verification"], "pending")
        self.assertEqual(state["campaign"]["budget"]["consumed_trials"], 3)
        self.assertEqual(len(result["experiment_report"]["artifact_integrity"]), 3)
        self.assertEqual(result["paper_evidence"]["model_evidence"], "loopback_fixture_responses")
        for request in requests:
            text = json.dumps(request["payload"])
            self.assertNotIn("test_mse", text)
            self.assertNotIn(fixture.FIXTURE_KEY, text)
            self.assertIn("max_completion_tokens", request["payload"])
        self.assertFalse(state["platform_connected"])
        self.assertIsNone(state["campaign"]["final_evaluation"])

    def test_restart_preserves_budget_and_trials(self):
        with fixture.model_fixture() as (endpoint, requests):
            config = self.configure(endpoint)
            first = self.loop.run(config, max_new_requests=1)
            self.assertEqual(first["state"]["status"], "paused")
            second = ResearchLoop(self.tmp.name)
            second.resume()
            result = second.run(config)
            self.assertEqual(len(requests), 4)
            self.assertEqual(result["state"]["campaign"]["trials"][0]["id"], first["state"]["campaign"]["trials"][0]["id"])
            self.assertEqual(result["state"]["budget"]["reserved_model_requests"], 4)
            # Completed/stopped invocation never dispatches another call.
            second.run(config)
            self.assertEqual(len(requests), 4)

    def test_invalid_decisions_spend_model_slots_not_trial_slots(self):
        with fixture.model_fixture("always_invalid") as (endpoint, requests):
            config = self.configure(endpoint, max_requests=2)
            result = self.loop.run(config)
            self.assertEqual(len(requests), 2)
        self.assertEqual(result["state"]["status"], "completed")
        self.assertEqual(result["state"]["campaign"]["budget"]["consumed_trials"], 0)
        self.assertEqual(result["state"]["budget"]["reserved_model_requests"], 2)
        self.assertTrue(all(c["error_code"] == "INVALID_DECISION" for c in result["state"]["model_calls"]))

    def test_model_request_budget_and_trial_budget_stop_before_dispatch(self):
        with fixture.model_fixture() as (endpoint, requests):
            config = self.configure(endpoint, max_requests=1)
            result = self.loop.run(config)
            self.assertEqual(len(requests), 1)
        self.assertEqual(result["state"]["status"], "completed")
        self.assertEqual(result["state"]["reason"], "MODEL_BUDGET_EXHAUSTED")
        with tempfile.TemporaryDirectory() as directory, fixture.model_fixture() as (endpoint, requests):
            loop = ResearchLoop(directory)
            config = fixture.configuration(endpoint)
            loop.configure("One-trial scope", config, max_trials=1)
            result = loop.run(config)
            self.assertEqual(len(requests), 1)
            self.assertEqual(result["state"]["reason"], "trial_budget_exhausted")

    def test_full_context_reservation_denies_call_when_no_money_fits(self):
        with fixture.model_fixture() as (endpoint, requests):
            config = self.configure(endpoint, max_cost_cny="0.001")
            result = self.loop.run(config)
            self.assertEqual(requests, [])
        self.assertEqual(result["state"]["budget"]["reserved_model_requests"], 0)

    def test_failed_http_keeps_reservation_and_has_no_automatic_retry(self):
        with fixture.model_fixture("http_error") as (endpoint, requests):
            config = self.configure(endpoint)
            result = self.loop.run(config)
            self.assertEqual(len(requests), 1)
        state = result["state"]
        self.assertEqual(state["status"], "needs_review")
        call = state["model_calls"][0]
        self.assertIsNone(call["usage_estimated_cny"])
        self.assertEqual(state["budget"]["accounted_or_reserved_cny"], call["reserved_cny"])
        self.error("NEEDS_REVIEW", self.loop.resume)
        self.loop.reconcile(call["id"], confirm_worker_stopped=True)
        self.assertEqual(self.loop.status()["budget"], state["budget"])

    def test_unknown_inflight_is_never_resent_or_refunded(self):
        with fixture.model_fixture() as (endpoint, requests):
            config = self.configure(endpoint)
            observation = self.loop.engine.observe(self.loop.status()["campaign_id"])
            call_id, _ = self.loop._reserve(observation, self.loop._messages(observation), 100000, True)
            other = ResearchLoop(self.tmp.name)
            self.error("NEEDS_REVIEW", lambda: other.run(config))
            self.assertEqual(requests, [])
            self.error("RECONCILIATION_REQUIRED", lambda: other.reconcile(call_id))
            before = other.status()["budget"]
            other.reconcile(call_id, confirm_worker_stopped=True)
            self.assertEqual(other.status()["budget"], before)

    def test_received_response_recovers_without_key_or_new_model_request(self):
        with fixture.model_fixture() as (endpoint, requests):
            config = self.configure(endpoint)
            observation = self.loop.engine.observe(self.loop.status()["campaign_id"])
            messages = self.loop._messages(observation)
            call_id, request_id = self.loop._reserve(observation, messages, 100000, True)
            self.loop._received(call_id, ChatClient(config["connection"]).complete(messages, request_id), config)
            with patch.dict(os.environ, {}, clear=True):
                other = ResearchLoop(self.tmp.name)
                result = other.run(config, max_new_requests=0)
            self.assertEqual(len(requests), 1)
        self.assertEqual(result["state"]["campaign"]["budget"]["consumed_trials"], 1)
        self.assertEqual(result["state"]["model_calls"][0]["status"], "applied")

    def test_response_replay_after_training_uses_same_request_id(self):
        with fixture.model_fixture() as (endpoint, requests):
            config = self.configure(endpoint)
            observation = self.loop.engine.observe(self.loop.status()["campaign_id"])
            messages = self.loop._messages(observation)
            call_id, request_id = self.loop._reserve(observation, messages, 100000, True)
            response = ChatClient(config["connection"]).complete(messages, request_id)
            self.loop._received(call_id, response, config)
            chosen = parse_decision(response["content"], observation)
            original = self.loop.engine.submit(self.loop.status()["campaign_id"], request_id, chosen["proposal"])
            # Simulates process loss after training committed, before loop-call commit.
            other = ResearchLoop(self.tmp.name)
            result = other.run(config, max_new_requests=0)
            self.assertEqual(len(requests), 1)
        self.assertEqual(result["state"]["campaign"]["budget"]["consumed_trials"], 1)
        self.assertEqual(result["state"]["model_calls"][0]["trial_id"], original["trial_id"])

    def test_overrun_is_accounted_without_clipping_and_requires_review(self):
        with fixture.model_fixture("over_input") as (endpoint, requests):
            config = self.configure(endpoint)
            self.error("COST_BOUND_EXCEEDED", lambda: self.loop.run(config))
            self.assertEqual(len(requests), 1)
        state = self.loop.status()
        self.assertEqual(state["status"], "needs_review")
        self.assertGreater(state["model_calls"][0]["usage_estimated_cny"], state["model_calls"][0]["reserved_cny"])
        self.assertEqual(state["campaign"]["budget"]["consumed_trials"], 0)

    def test_unverified_stale_and_live_disabled_configs_do_not_dispatch(self):
        for kind in ("unverified", "stale", "live"):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as directory:
                with fixture.model_fixture() as (endpoint, requests):
                    loop = ResearchLoop(directory)
                    config = fixture.configuration(endpoint)
                    expected = "PRICING_NOT_VERIFIED"
                    if kind == "unverified":
                        config["pricing"]["verified"] = False
                    elif kind == "stale":
                        config["pricing"]["checked_on"] = (date.today()-timedelta(days=8)).isoformat()
                        expected = "CONFIG_REQUIRED"
                    else:
                        config["connection"]["endpoint"] = "https://example.invalid/v1/chat/completions"
                        config["connection"]["allow_loopback_http"] = False
                        expected = "LIVE_ACCESS_DISABLED"
                    loop.configure("Configuration gate", config)
                    self.error(expected, lambda: loop.run(config))
                    self.assertEqual(requests, [])
                    self.assertEqual(loop.status()["budget"]["reserved_model_requests"], 0)

    def test_frozen_configuration_and_absolute_limits_cannot_be_reset(self):
        with fixture.model_fixture() as (endpoint, _):
            config = self.configure(endpoint)
            changed = copy.deepcopy(config)
            changed["connection"]["model"] = "different-model"
            self.error("CONFIG_CHANGED", lambda: self.loop.run(changed))
            for kwargs in ({"max_trials": 6}, {"max_requests": 9}, {"max_cost_cny": 6}):
                self.error("INVALID_REQUEST", lambda: self.loop.configure("new", config, **kwargs))
            self.error("CONFIG_CHANGED", lambda: self.loop.configure("Test product-owned research loop with fixture model responses.", config, max_requests=2))

    def test_stop_decision_schema_evidence_and_duplicate_json_are_checked(self):
        with fixture.model_fixture() as (endpoint, _):
            self.configure(endpoint)
            observation = self.loop.engine.observe(self.loop.status()["campaign_id"])
            self.error("INVALID_DECISION", lambda: parse_decision('{"action":"stop","action":"pause"}', observation))
            value = {"action": "stop", "reason": "Done", "observation_sha256": observation["observation_sha256"], "evidence_trial_ids": [{"bad": 1}]}
            self.error("INVALID_REQUEST", lambda: parse_decision(json.dumps(value), observation))
            value["evidence_trial_ids"] = []
            self.assertEqual(parse_decision(json.dumps(value), observation)["action"], "stop")
            for invalid_action in ([], {}, 1, None):
                self.error("INVALID_DECISION", lambda: parse_decision(json.dumps({"action": invalid_action}), observation))

    def test_malformed_action_in_stored_response_does_not_block_recovery(self):
        with fixture.model_fixture() as (endpoint, requests):
            config = self.configure(endpoint)
            observation = self.loop.engine.observe(self.loop.status()["campaign_id"])
            messages = self.loop._messages(observation)
            call_id, request_id = self.loop._reserve(observation, messages, 100000, True)
            response = ChatClient(config["connection"]).complete(messages, request_id)
            response["content"] = '{"action":[]}'
            self.loop._received(call_id, response, config)
            recovered = ResearchLoop(self.tmp.name).run(config, max_new_requests=0)
            self.assertEqual(recovered["state"]["model_calls"][0]["status"], "invalid")
            self.assertEqual(recovered["state"]["campaign"]["budget"]["consumed_trials"], 0)
            self.loop.resume()
            self.loop.run(config, max_new_requests=1)
            self.assertEqual(len(requests), 2)
        self.assertEqual(self.loop.status()["campaign"]["budget"]["consumed_trials"], 1)

    def test_late_pause_cannot_revive_a_stopped_project(self):
        with fixture.model_fixture() as (endpoint, requests):
            config = self.configure(endpoint)
            result = self.loop.run(config)
            self.assertEqual(result["state"]["status"], "stopped")
            stale = ResearchLoop(self.tmp.name)
            self.assertFalse(stale._pause("paused", "operator_step_limit"))
            self.error("NOT_PAUSED", stale.resume)
            stale.run(config)
            self.assertEqual(len(requests), 4)
        self.assertEqual(self.loop.status()["status"], "stopped")

    def test_reasoning_details_are_not_double_charged(self):
        pricing = fixture.configuration("http://127.0.0.1/x")["pricing"]
        usage = {"prompt_tokens": 200, "completion_tokens": 100, "total_tokens": 300,
                 "completion_tokens_details": {"reasoning_tokens": 80}}
        self.assertEqual(cost_micros(usage, pricing), 1200)

    def test_concurrent_runner_cannot_reserve_or_send_a_second_request(self):
        entered, release = threading.Event(), threading.Event()
        errors = []
        original = ChatClient.complete
        def slow(client, messages, request_id):
            entered.set()
            if not release.wait(10):
                raise RuntimeError("test release timeout")
            return original(client, messages, request_id)
        with fixture.model_fixture() as (endpoint, requests):
            config = self.configure(endpoint)
            def first_worker():
                try:
                    self.loop.run(config, max_new_requests=1)
                except BaseException as exc:
                    errors.append(exc)
            with patch.object(ChatClient, "complete", autospec=True, side_effect=slow):
                thread = threading.Thread(target=first_worker)
                thread.start()
                self.assertTrue(entered.wait(10))
                try:
                    other = ResearchLoop(self.tmp.name)
                    self.error("NEEDS_REVIEW", lambda: other.run(config))
                    self.assertEqual(other.status()["budget"]["reserved_model_requests"], 1)
                finally:
                    release.set()
                    thread.join(15)
            self.assertFalse(thread.is_alive())
            self.assertEqual(errors, [])
            self.assertEqual(len(requests), 1)
        self.assertEqual(self.loop.status()["campaign"]["budget"]["consumed_trials"], 1)


if __name__ == "__main__":
    unittest.main()
