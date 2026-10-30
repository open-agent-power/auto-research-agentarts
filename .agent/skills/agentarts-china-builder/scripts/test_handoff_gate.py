"""Standard-library tests only: no browser, login, credentials or network."""

import json
from pathlib import Path
import subprocess
import sys
import unittest
from urllib.parse import quote, urlencode

from handoff_gate import FLAGS, MAX_INPUT_BYTES, evaluate


CONSOLE = "https://console.huaweicloud.com/agentarts/?region=cn-southwest-2"


def auth(service=CONSOLE, fragment="/login2", **parameters):
    values = {"service": service, **parameters}
    return "https://auth.huaweicloud.com/authui/login.html?" + urlencode(values) + "#" + fragment


def observation(url=None, **flags):
    return {"url": auth() if url is None else url, **dict.fromkeys(FLAGS, False), **flags}


class HandoffGateTests(unittest.TestCase):
    def assert_denied(self, value, state=None):
        result = evaluate(value)
        self.assertFalse(result["may_read_console"])
        self.assertFalse(result["may_run"])
        self.assertFalse(result["may_publish"])
        if state is not None:
            self.assertEqual(result["state"], state)
        return result

    def test_actual_login2_route_with_cloud_route_state_waits_for_user(self):
        service = CONSOLE + "&cloud_route_state=" + quote("/home/overview", safe="")
        result = self.assert_denied(observation(auth(service, quickLogin="true"),
                                              qr_visible=True, cloud_app_prompt=True),
                                    "await_user_cloud_app_scan")
        self.assertEqual(result["next_action"], "wait_for_user_cloud_app_scan")

    def test_regular_login_does_not_become_cloud_app_qr_ready(self):
        for route in ("", "/login"):
            with self.subTest(route=route):
                self.assert_denied(observation(auth(fragment=route), qr_visible=True,
                                               cloud_app_prompt=True), "cloud_account_entry_required")

    def test_qr_presence_without_cloud_app_prompt_is_not_enough(self):
        self.assert_denied(observation(qr_visible=True), "cloud_app_prompt_unconfirmed")
        self.assert_denied(observation(cloud_app_prompt=True), "await_cloud_app_qr_render")

    def test_expiry_and_phone_confirmation_never_refresh_or_confirm_automatically(self):
        result = self.assert_denied(observation(qr_visible=True, cloud_app_prompt=True,
                                               qr_expired=True), "qr_expired_manual_handoff")
        self.assertEqual(result["next_action"], "ask_user_before_any_single_manual_qr_refresh")
        self.assert_denied(observation(cloud_app_prompt=True, scan_confirmation_pending=True),
                           "await_user_phone_confirmation")

    def test_risk_takes_priority_over_ready_or_wrong_login_page(self):
        for url in (CONSOLE, auth(), "https://id1.cloud.huawei.com/CAS/remoteLogin"):
            with self.subTest(url=url):
                self.assert_denied(observation(url, risk_visible=True, console_loaded=True,
                                               account_confirmed=True, region_confirmed=True), "risk_stop")

    def test_huawei_id_is_explicitly_the_wrong_login(self):
        for host in ("id.cloud.huawei.com", "id1.cloud.huawei.com", "id7.cloud.huawei.com"):
            with self.subTest(host=host):
                self.assert_denied(observation("https://" + host + "/CAS/remoteLogin",
                                               qr_visible=True, cloud_app_prompt=True),
                                   "wrong_login_not_cloud_app")

    def test_console_requires_fresh_loaded_account_and_region_observations(self):
        ready = observation(CONSOLE + "#/home/overview", console_loaded=True,
                            account_confirmed=True, region_confirmed=True)
        result = evaluate(ready)
        self.assertTrue(result["may_read_console"])
        self.assertFalse(result["may_run"])
        self.assertFalse(result["may_publish"])
        for field in ("console_loaded", "account_confirmed", "region_confirmed"):
            with self.subTest(missing_confirmation=field):
                self.assert_denied({**ready, field: False})
        for field in ("qr_visible", "cloud_app_prompt", "qr_expired", "scan_confirmation_pending"):
            with self.subTest(stale_flag=field):
                self.assert_denied({**ready, field: True}, "inconsistent_observation")
        self.assert_denied(observation(console_loaded=True, account_confirmed=True,
                                       region_confirmed=True), "inconsistent_observation")

    def test_all_fields_are_required_and_booleans_are_strict(self):
        for field in ("url", *FLAGS):
            with self.subTest(missing=field):
                value = observation(); value.pop(field)
                self.assert_denied(value, "invalid_observation")
        for field in FLAGS:
            for invalid in (0, 1, "false", None, [], {}):
                with self.subTest(field=field, invalid=invalid):
                    self.assert_denied(observation(**{field: invalid}), "invalid_observation")
        self.assert_denied({**observation(), "cookie": "PRIVATE_SENTINEL"}, "invalid_observation")
        for value in (None, [], True, "PRIVATE_SENTINEL"):
            self.assert_denied(value, "invalid_observation")

    def test_rejects_unsafe_authorities_protocols_and_paths(self):
        invalid = [
            "http://console.huaweicloud.com/agentarts/?region=cn-southwest-2",
            "https://console.huaweicloud.com:444/agentarts/?region=cn-southwest-2",
            "https://console.huaweicloud.com:/agentarts/?region=cn-southwest-2",
            "https://user@console.huaweicloud.com/agentarts/?region=cn-southwest-2",
            "https://console.huaweicloud.com.evil.test/agentarts/?region=cn-southwest-2",
            "https://console.huaweicloud.com./agentarts/?region=cn-southwest-2",
            "https://id1.cloud.huawei.com.evil.test/CAS/remoteLogin",
            "https://console.huaweicloud.com/iam/?region=cn-southwest-2",
            "https://console.huaweicloud.com/agentarts/../iam?region=cn-southwest-2",
            "https://console.huaweicloud.com/agentarts%2f?region=cn-southwest-2",
            "https://auth.huaweicloud.com/authui/login.html.evil?service=x#/login2",
            "https://auth.huaweicloud.com:444/authui/login.html?service=x#/login2",
            "https://user:PRIVATE_SENTINEL@auth.huaweicloud.com/authui/login.html?service=x#/login2",
            "https://auth.huaweicloud.com.evil.test/authui/login.html?service=x#/login2",
            " https://console.huaweicloud.com/agentarts/?region=cn-southwest-2",
            "https://console.huaweicloud.com\t/agentarts/?region=cn-southwest-2",
            "https://console.huaweicloud.com\\@evil.test/agentarts/?region=cn-southwest-2",
        ]
        for url in invalid:
            with self.subTest(url=url):
                self.assert_denied(observation(url, console_loaded=True,
                                               account_confirmed=True, region_confirmed=True), "invalid_url")

    def test_service_region_and_route_parameters_are_unambiguous(self):
        invalid = [
            auth(CONSOLE).replace("#/login2", "&service=x#/login2"),
            "https://auth.huaweicloud.com/authui/login.html?service=" + quote(CONSOLE, safe="")
            + "&serv%69ce=" + quote(CONSOLE, safe="") + "#/login2",
            auth("https://evil.test/agentarts/?region=cn-southwest-2"),
            auth("http://console.huaweicloud.com/agentarts/?region=cn-southwest-2"),
            auth(CONSOLE.replace("/agentarts/", "/iam/")),
            auth(quote(CONSOLE, safe="")),
            auth(CONSOLE + "&region=cn-southwest-2"),
            auth(CONSOLE + "&reg%69on=cn-north-4"),
            CONSOLE + "&region=cn-southwest-2",
            CONSOLE + "&reg%69on=cn-north-4",
            CONSOLE.replace("cn-southwest-2", "cn-north-4"),
            auth(CONSOLE.replace("cn-southwest-2", "cn-north-4")),
            "https://console.huaweicloud.com/agentarts/",
            CONSOLE + "#/home?region=cn-north-4",
            CONSOLE + "&cloud_route_state=" + quote("https://evil.test/", safe=""),
            auth(CONSOLE, quickLogin="1"),
            auth(CONSOLE, quickLogin="true").replace("#/login2", "&quickLogin=false#/login2"),
            auth(CONSOLE, redirect="https://evil.test/"),
            "https://auth.huaweicloud.com/authui/login.html#/login2",
        ]
        for url in invalid:
            with self.subTest(url=url):
                self.assert_denied(observation(url), "invalid_url")

    def test_explicit_443_and_home_routes_are_allowed_without_extra_permissions(self):
        for url in (CONSOLE.replace(".com/", ".com:443/") + "#/home",
                    CONSOLE + "#/home/agent-center/app-flow/flow?id=public-id&from="):
            with self.subTest(url=url):
                result = evaluate(observation(url, console_loaded=True,
                                              account_confirmed=True, region_confirmed=True))
                self.assertTrue(result["may_read_console"])
                self.assertFalse(result["may_run"])
                self.assertFalse(result["may_publish"])
        self.assert_denied(observation(auth(CONSOLE, locale="zh-cn", quickLogin="false")),
                           "cloud_app_prompt_unconfirmed")

    def test_cli_bad_json_and_extra_fields_do_not_echo_secrets(self):
        sentinel = "DO_NOT_ECHO_PRIVATE_SENTINEL"
        values = [
            ('{"url":"' + sentinel).encode(),
            ('{"url":"' + sentinel + '","url":"duplicate"}').encode(),
            b"\xff" + sentinel.encode(),
            (" " * MAX_INPUT_BYTES + sentinel).encode(),
            json.dumps({**observation(), "cookie": sentinel}).encode(),
            b"NaN",
        ]
        script = Path(__file__).with_name("handoff_gate.py")
        for raw in values:
            with self.subTest(kind=raw[:8]):
                result = subprocess.run([sys.executable, "-B", str(script)], input=raw,
                                        capture_output=True, timeout=5)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stderr, b"")
                self.assertNotIn(sentinel.encode(), result.stdout + result.stderr)
                decision = json.loads(result.stdout)
                self.assertEqual(decision["state"], "invalid_observation")
                self.assertFalse(decision["may_read_console"])
                self.assertFalse(decision["may_run"])
                self.assertFalse(decision["may_publish"])

    def test_cli_valid_console_decision_is_read_only_and_omits_url(self):
        script = Path(__file__).with_name("handoff_gate.py")
        value = observation(CONSOLE, console_loaded=True, account_confirmed=True, region_confirmed=True)
        result = subprocess.run([sys.executable, "-B", str(script)], input=json.dumps(value).encode(),
                                capture_output=True, timeout=5)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stderr, b"")
        self.assertEqual(json.loads(result.stdout), evaluate(value))
        self.assertNotIn(CONSOLE.encode(), result.stdout)


if __name__ == "__main__":
    unittest.main()
