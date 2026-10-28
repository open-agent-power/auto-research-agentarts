import hashlib
from importlib.metadata import PackageNotFoundError, version
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

try:
    version("agentarts-sdk")
except PackageNotFoundError:
    raise unittest.SkipTest("install the runtime extra to test the official AgentArts adapter")

from starlette.testclient import TestClient

from autoresearch.runtime import MAX_BODY_BYTES, SESSION_HEADER, create_app, server_settings


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.headers = {SESSION_HEADER: "engineering-session", "X-Request-Id": "transport-1"}

    def tearDown(self):
        self.temp.cleanup()

    def invoke(self, client, action, rid, **fields):
        return client.post("/invocations", headers=self.headers, json={
            "schema_version": "0.1", "action": action, "request_id": rid, **fields
        }).json()

    def test_real_http_training_retry_and_fresh_process_resume(self):
        with TestClient(create_app(self.root)) as client:
            self.assertEqual(client.get("/ping").status_code, 200)
            created = self.invoke(client, "create_campaign", "create", goal="HTTP fixture", max_trials=3)
            cid = created["result"]["campaign_id"]
            first = self.invoke(client, "run_trial", "first", campaign_id=cid)
            self.assertTrue(first["ok"])
            self.assertEqual(first["result"]["status"], "accepted")
            self.headers["X-Request-Id"] = "transport-retry"
            retry = self.invoke(client, "run_trial", "first", campaign_id=cid)
            self.assertEqual(retry["result"], first["result"])
            self.assertNotEqual(retry["transport"]["transport_request_id"], first["transport"]["transport_request_id"])
            self.invoke(client, "pause_campaign", "pause", campaign_id=cid)
        # A genuinely fresh process uses the same SDK HTTP boundary and storage.
        program = """
import json, sys
from starlette.testclient import TestClient
from autoresearch.runtime import create_app, SESSION_HEADER
with TestClient(create_app(sys.argv[1])) as c:
    headers={SESSION_HEADER:'engineering-session'}
    def call(a,r):
        return c.post('/invocations',headers=headers,json={'schema_version':'0.1','request_id':r,'action':a,'campaign_id':sys.argv[2]}).json()
    call('resume_campaign','resume')
    second=call('run_trial','second')
    third=call('run_trial','third')
    final=call('finalize_campaign','final')
    state=call('campaign_status','status')
    print(json.dumps({'second':second,'third':third,'final':final,'state':state}))
"""
        resumed = subprocess.run([sys.executable, "-c", program, str(self.root), cid],
                                 capture_output=True, text=True, check=True, timeout=45)
        result = json.loads(resumed.stdout.strip().splitlines()[-1])
        second, third = result["second"]["result"], result["third"]["result"]
        self.assertEqual(second["parent_trial_id"], first["result"]["trial_id"])
        self.assertEqual([second["status"], third["status"]], ["accepted", "rejected"])
        self.assertLess(second["metrics"]["validation_mse"], first["result"]["metrics"]["validation_mse"] * .01)
        self.assertEqual(result["state"]["result"]["budget"]["consumed_trials"], 3)
        self.assertTrue(result["final"]["ok"])
        session_root = self.root / "sessions" / first["transport"]["session_fingerprint"]
        artifact = session_root / second["model_artifact"]
        self.assertEqual(hashlib.sha256(artifact.read_bytes()).hexdigest(), second["model_sha256"])
        self.assertFalse(first["transport"]["platform_trace_verified"])
        self.assertFalse(result["state"]["result"]["platform_connected"])

    def test_sessions_are_distinct_namespaces_and_required(self):
        with TestClient(create_app(self.root)) as client:
            created = self.invoke(client, "create_campaign", "same-create", goal="session A")
            cid = created["result"]["campaign_id"]
            self.headers[SESSION_HEADER] = "another-session"
            absent = self.invoke(client, "campaign_status", "status", campaign_id=cid)
            self.assertEqual(absent["error"]["code"], "NOT_FOUND")
            another = self.invoke(client, "create_campaign", "same-create", goal="session B")
            self.assertNotEqual(cid, another["result"]["campaign_id"])
            self.headers.pop(SESSION_HEADER)
            missing = self.invoke(client, "create_campaign", "missing", goal="missing session")
            self.assertEqual(missing["error"]["code"], "SESSION_REQUIRED")

    def test_evidence_bound_materials_proposal_through_sdk_http(self):
        with TestClient(create_app(self.root)) as client:
            created = self.invoke(client, "create_campaign", "steel", goal="材料基准", max_trials=2,
                                  dataset_id="matbench-steels-v1", policy_kind="external_agent_proposal_v1")
            self.assertTrue(created["ok"])
            cid = created["result"]["campaign_id"]
            observation = self.invoke(client, "observe_campaign", "observe", campaign_id=cid)["result"]
            proposed = {"observation_sha256": observation["observation_sha256"],
                        "hypothesis": "先建立线性基准", "expected_effect": "获得实际基准误差",
                        "candidate": {"degree": 1, "alpha": 1.0}, "evidence_trial_ids": []}
            result = self.invoke(client, "submit_proposal", "trial", campaign_id=cid, proposal=proposed)
            self.assertEqual(result["result"]["status"], "accepted")
            report = self.invoke(client, "research_report", "report", campaign_id=cid)
            self.assertTrue(report["ok"])
            self.assertEqual(report["result"]["state"]["scientific_status"], "benchmark_only")
            self.assertEqual(report["result"]["state"]["trials"][0]["proposal"], proposed)
            self.assertTrue(report["result"]["artifact_integrity"][0]["verified"])
            self.assertFalse(report["transport"]["platform_trace_verified"])

    def test_payload_boundaries_and_unexposed_operator_actions(self):
        with TestClient(create_app(self.root)) as client:
            for body in (b'{"candidate":NaN}', b'{"candidate":1e999}', b'{', b'\xff', b'[' * 1500 + b']' * 1500):
                response = client.post("/invocations", headers=self.headers, content=body)
                self.assertEqual(response.status_code, 400)
                self.assertEqual(response.json()["error"]["code"], "INVALID_JSON")
            too_big = client.post("/invocations", headers=self.headers, content=b' ' * (MAX_BODY_BYTES+1))
            self.assertEqual(too_big.status_code, 413)
            forbidden = self.invoke(client, "reconcile_interrupted", "forbidden")
            self.assertEqual(forbidden["error"]["code"], "INVALID_REQUEST")
            paths = self.invoke(client, "create_campaign", "path", goal="bad", workspace="C:/private")
            self.assertEqual(paths["error"]["code"], "INVALID_REQUEST")
            huge = self.invoke(client, "run_trial", "huge", campaign_id="uncreated",
                               candidate={"degree": 2, "alpha": 10**400})
            self.assertEqual(huge["error"]["code"], "INVALID_REQUEST")
        self.assertFalse((self.root / "research.sqlite3").exists())

    def test_sensitive_context_is_not_logged(self):
        with TestClient(create_app(self.root)) as client:
            self.headers["Authorization"] = "Bearer sensitive-token"
            self.headers["x-hw-agentarts-workload-accesstoken"] = "secret-workload-token"
            with self.assertLogs("autoresearch.invocations", level="INFO") as captured:
                self.invoke(client, "create_campaign", "safe-id", goal="private-goal-must-not-be-logged")
            log = "\n".join(captured.output)
            for secret in ("sensitive-token", "secret-workload-token", "private-goal-must-not-be-logged", "engineering-session"):
                self.assertNotIn(secret, log)
            self.assertIn('"request_id":"safe-id"', log)

    def test_operator_server_configuration(self):
        self.assertEqual(server_settings({"AUTORESEARCH_WORKSPACE": str(self.root)})[1:], ("127.0.0.1", 8080))
        self.assertEqual(server_settings({"AUTORESEARCH_WORKSPACE": str(self.root), "AGENT_RUN_PORT": "8099"})[2], 8099)
        for env in ({}, {"AUTORESEARCH_WORKSPACE": "relative"},
                    {"AUTORESEARCH_WORKSPACE": str(self.root), "AGENT_RUN_PORT": "0"}):
            with self.assertRaises(ValueError):
                server_settings(env)
        with self.assertRaises(ValueError):
            create_app("relative")


if __name__ == "__main__":
    unittest.main()
