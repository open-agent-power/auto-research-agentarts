"""Pure, advisory login handoff gate; never verifies or performs a login.

Read one JSON observation from stdin (then EOF), write one safe JSON decision.
All FLAGS and ``url`` are required; flags describe fresh, manually checked UI.
Only may_read_console can become true. No decision authorizes running/publishing.
The input URL/query is never returned, logged, persisted or fetched.
CLI exit code 0 means a decision was returned, NOT that anyone is logged in.
Callers must inspect state/may_read_console; never start an operation from the
exit code alone. Exit code 2 denotes an invalid or incomplete observation/input.
"""

import json
import re
import sys
from urllib.parse import parse_qsl, urlsplit


REGION = "cn-southwest-2"
MAX_INPUT_BYTES = 16384
MAX_URL_CHARS = 4096
FLAGS = (
    "qr_visible", "cloud_app_prompt", "qr_expired", "scan_confirmation_pending",
    "risk_visible", "console_loaded", "account_confirmed", "region_confirmed",
)


def _decision(state, next_action, may_read=False):
    return {
        "schema_version": "agentarts-cloud-app-handoff-v1",
        "state": state,
        "next_action": next_action,
        "may_read_console": may_read,
        "may_run": False,
        "may_publish": False,
    }


def _url(value):
    if (not value or len(value) > MAX_URL_CHARS or not value.isascii()
            or any(ord(c) <= 32 or ord(c) == 127 for c in value)
            or "\\" in value or re.search(r"%(?![0-9a-fA-F]{2})", value)):
        raise ValueError("url")
    parts = urlsplit(value)
    if (parts.scheme != "https" or parts.username is not None
            or parts.password is not None or not parts.hostname
            or parts.port not in (None, 443)
            or parts.netloc.lower() not in {parts.hostname, parts.hostname + ":443"}):
        raise ValueError("url")
    return parts


def _query(value):
    pairs = parse_qsl(value, keep_blank_values=True, strict_parsing=True,
                      encoding="utf-8", errors="strict", max_num_fields=16)
    if len({key for key, _ in pairs}) != len(pairs):
        raise ValueError("duplicate parameter")
    if any(ord(c) < 32 or ord(c) == 127 for pair in pairs for item in pair for c in item):
        raise ValueError("control character")
    return dict(pairs)


def _home_route(value):
    route = urlsplit(value)
    if (route.scheme or route.netloc or route.fragment
            or not re.fullmatch(r"/home(?:/[A-Za-z0-9_-]+)*/?", route.path)):
        raise ValueError("route")
    # Region/service must never be supplied a second time through a UI route.
    if set(_query(route.query)) - {"id", "from", "view", "scope", "section", "locale"}:
        raise ValueError("route parameters")


def _console(value):
    parts = _url(value)
    if parts.hostname != "console.huaweicloud.com" or parts.path not in {"/agentarts", "/agentarts/"}:
        raise ValueError("console target")
    query = _query(parts.query)
    if set(query) - {"region", "cloud_route_state"} or query.get("region") != REGION:
        raise ValueError("region or target")
    if "cloud_route_state" in query:
        _home_route(query["cloud_route_state"])
    if parts.fragment:
        _home_route(parts.fragment)


def _kind(value):
    parts = _url(value)
    if re.fullmatch(r"id[a-z0-9-]*\.cloud\.huawei\.com", parts.hostname):
        return "wrong_login_not_cloud_app"
    if parts.hostname == "console.huaweicloud.com":
        _console(value)
        return "console"
    if parts.hostname != "auth.huaweicloud.com" or parts.path != "/authui/login.html":
        raise ValueError("login target")
    query = _query(parts.query)
    if "service" not in query or set(query) - {"service", "locale", "quickLogin", "cloud_route_state"}:
        raise ValueError("login parameters")
    _console(query["service"])
    if "locale" in query and not re.fullmatch(r"[A-Za-z0-9_-]{1,32}", query["locale"]):
        raise ValueError("locale")
    if "quickLogin" in query and query["quickLogin"] not in {"true", "false"}:
        raise ValueError("quickLogin")
    if "cloud_route_state" in query:
        _home_route(query["cloud_route_state"])
    if parts.fragment not in {"", "/login", "/login2"}:
        raise ValueError("login route")
    return "cloud_account" if parts.fragment == "/login2" else "login_entry"


def evaluate(observation):
    """Use supplied observations conservatively; this is not authentication."""
    if (type(observation) is not dict or set(observation) != {"url", *FLAGS}
            or type(observation.get("url")) is not str
            or any(type(observation.get(key)) is not bool for key in FLAGS)):
        return _decision("invalid_observation", "provide_complete_boolean_observation")
    if observation["risk_visible"]:
        return _decision("risk_stop", "stop_and_request_manual_risk_resolution")
    try:
        kind = _kind(observation["url"])
    except (ValueError, UnicodeError):
        return _decision("invalid_url", "verify_official_cloud_login_target")
    if kind == "wrong_login_not_cloud_app":
        return _decision(kind, "select_huawei_cloud_account_and_reobserve")
    qr_flags = ("qr_visible", "cloud_app_prompt", "qr_expired", "scan_confirmation_pending")
    if kind == "console":
        if any(observation[key] for key in qr_flags):
            return _decision("inconsistent_observation", "refresh_read_only_observation")
        if not observation["console_loaded"]:
            return _decision("await_console_render", "wait_for_console_and_reobserve")
        if not observation["account_confirmed"] or not observation["region_confirmed"]:
            return _decision("console_verification_required", "verify_account_and_region_read_only")
        return _decision("console_ready_read_only", "read_console_only", True)
    if any(observation[key] for key in ("console_loaded", "account_confirmed", "region_confirmed")):
        return _decision("inconsistent_observation", "refresh_read_only_observation")
    if kind == "login_entry":
        return _decision("cloud_account_entry_required", "select_more_then_huawei_cloud_account")
    if not observation["cloud_app_prompt"]:
        return _decision("cloud_app_prompt_unconfirmed", "verify_huawei_cloud_app_prompt_before_scan")
    if observation["qr_expired"]:
        return _decision("qr_expired_manual_handoff", "ask_user_before_any_single_manual_qr_refresh")
    if observation["scan_confirmation_pending"]:
        return _decision("await_user_phone_confirmation", "wait_for_user_cloud_app_confirmation")
    if observation["qr_visible"]:
        return _decision("await_user_cloud_app_scan", "wait_for_user_cloud_app_scan")
    return _decision("await_cloud_app_qr_render", "reobserve_or_request_manual_handoff")


def _pairs(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("duplicate JSON key")
        value[key] = item
    return value


def _nonfinite(_value):
    raise ValueError("nonfinite JSON")


def main():
    try:
        raw = sys.stdin.buffer.read(MAX_INPUT_BYTES + 1)
        if not raw or len(raw) > MAX_INPUT_BYTES:
            raise ValueError("input size")
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_pairs, parse_constant=_nonfinite)
        result = evaluate(value)
    except (ValueError, UnicodeError, RecursionError, OSError):
        result = _decision("invalid_observation", "provide_complete_boolean_observation")
    try:
        sys.stdout.write(json.dumps(result, sort_keys=True) + "\n")
    except BrokenPipeError:
        return 2
    return 2 if result["state"] == "invalid_observation" else 0


if __name__ == "__main__":
    raise SystemExit(main())
