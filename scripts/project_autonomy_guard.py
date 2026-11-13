#!/usr/bin/env python3
"""Cooperative worktree lease; no runner, budget reset, daemon or OS isolation.

Use a distinct owner ID per work session and heartbeat before continuing writes.
An expired lease does not stop its former process: every writer must cooperate.
Only lease metadata beneath .agent/autonomy is read or written.
"""
import argparse
from contextlib import contextmanager
import fcntl
import json
import math
import os
from pathlib import Path
import re
import stat
import tempfile
import time

DEFAULT_TTL = 1200
MAX_TTL = 3600
MAX_STATE_BYTES = 1024 * 1024
DEFAULT_DIRECTORY = Path(__file__).resolve().parents[1] / ".agent" / "autonomy"
SCHEMA = "project-autonomy-lease-v1"


class GuardError(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def _require(value, code, message):
    if not value:
        raise GuardError(code, message)


def _owner(value):
    return type(value) is str and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:@-]{0,127}", value) is not None


def _number(value):
    try:
        return type(value) in (int, float) and math.isfinite(value) and value >= 0
    except OverflowError:
        return False


class Guard:
    def __init__(self, directory=None, *, clock=time.time):
        self.directory = Path(directory) if directory is not None else DEFAULT_DIRECTORY
        self.path = self.directory / "lease.json"
        self.clock = clock

    @contextmanager
    def _locked(self):
        self.directory.mkdir(parents=True, exist_ok=True)
        _require(not self.directory.is_symlink(), "STATE_INVALID", "Lease directory must not be a symlink")
        fd = os.open(self.directory / "lease.lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, "r+b") as lock:
            info = os.fstat(lock.fileno())
            _require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1, "STATE_INVALID", "Invalid lease lock file")
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(lock.fileno(), fcntl.LOCK_UN)

    @staticmethod
    def _validate(state):
        keys = {"schema_version", "owner", "expires", "status", "updated_at", "events"}
        _require(type(state) is dict and set(state) == keys and state["schema_version"] == SCHEMA,
                 "STATE_INVALID", "Unknown or malformed lease state")
        status = state["status"]
        _require(status in ("unclaimed", "active", "released") and _number(state["expires"])
                 and _number(state["updated_at"]) and type(state["events"]) is list,
                 "STATE_INVALID", "Invalid lease status or timestamps")
        if status == "unclaimed":
            _require(state["owner"] is None and state["expires"] == state["updated_at"] == 0 and not state["events"],
                     "STATE_INVALID", "Invalid unclaimed state")
        else:
            _require(_owner(state["owner"]) and bool(state["events"])
                     and (0 < state["expires"] - state["updated_at"] <= MAX_TTL if status == "active" else state["expires"] == state["updated_at"]),
                     "STATE_INVALID", "Invalid owned lease")
        previous_time = 0
        for event in state["events"]:
            _require(type(event) is dict and set(event) == {"kind", "owner", "at", "previous_owner"}
                     and event["kind"] in ("claim", "release", "takeover") and _owner(event["owner"])
                     and _number(event["at"]) and previous_time <= event["at"] <= state["updated_at"]
                     and (_owner(event["previous_owner"]) if event["kind"] == "takeover" else event["previous_owner"] is None),
                     "STATE_INVALID", "Invalid lease event history")
            previous_time = event["at"]
        if state["events"]:
            last = state["events"][-1]
            _require(last["owner"] == state["owner"] and ((last["kind"] == "release") == (status == "released")),
                     "STATE_INVALID", "Lease status differs from its last event")

    def _read(self):
        def pairs(items):
            result = {}
            for key, value in items:
                _require(key not in result, "STATE_INVALID", "Duplicate lease JSON key")
                result[key] = value
            return result
        try:
            fd = os.open(self.path, os.O_RDONLY | os.O_NOFOLLOW)
        except FileNotFoundError:
            return {"schema_version": SCHEMA, "owner": None, "expires": 0, "status": "unclaimed", "updated_at": 0, "events": []}
        try:
            with os.fdopen(fd, "rb") as stream:
                info = os.fstat(stream.fileno())
                _require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1 and 0 < info.st_size <= MAX_STATE_BYTES,
                         "STATE_INVALID", "Invalid lease file or size")
                raw = stream.read(MAX_STATE_BYTES + 1)
            _require(len(raw) <= MAX_STATE_BYTES, "STATE_INVALID", "Oversized lease state")
            state = json.loads(raw.decode("utf-8"), object_pairs_hook=pairs)
            self._validate(state)
            return state
        except (ValueError, UnicodeError, RecursionError, TypeError, OverflowError):
            raise GuardError("STATE_INVALID", "Malformed lease state; refusing to overwrite it") from None

    def _write(self, state):
        self._validate(state)
        raw = (json.dumps(state, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")
        _require(len(raw) <= MAX_STATE_BYTES, "STATE_INVALID", "Lease history full; preserve and review it before continuing")
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(prefix=".lease-", dir=self.directory, delete=False) as stream:
                temporary = Path(stream.name)
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
            directory_fd = os.open(self.directory, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)

    def _now(self, state):
        now = self.clock()
        _require(_number(now) and now >= state["updated_at"], "INVALID_CLOCK", "Finite forward wall-clock time is required")
        return now

    @staticmethod
    def _view(state, now):
        return {**state, "available": state["status"] != "active" or state["expires"] <= now}

    def status(self):
        with self._locked():
            state = self._read()
            return self._view(state, self._now(state))

    def _change(self, action, owner, ttl=DEFAULT_TTL):
        _require(_owner(owner), "INVALID_OWNER", "Use a distinct bounded owner ID")
        _require(type(ttl) is int and 1 <= ttl <= MAX_TTL, "INVALID_TTL", "TTL must be an integer from 1 to 3600 seconds")
        with self._locked():
            state = self._read()
            now = self._now(state)
            active = state["status"] == "active" and state["expires"] > now
            if action == "claim":
                _require(not active or state["owner"] == owner, "LEASE_BUSY", "Another owner has an unexpired lease")
                if active:  # Same-owner retries do not renew the lease or add events.
                    return self._view(state, now)
                kind = "takeover" if state["status"] == "active" else "claim"
                previous = state["owner"] if kind == "takeover" else None
                state.update(owner=owner, expires=now + ttl, status="active", updated_at=now)
                state["events"].append({"kind": kind, "owner": owner, "at": now, "previous_owner": previous})
            else:
                _require(state["owner"] == owner, "OWNER_MISMATCH", "Only the recorded owner may heartbeat or release")
                if action == "heartbeat":
                    _require(active, "LEASE_EXPIRED", "Expired or released leases require a new claim")
                    state.update(expires=now + ttl, updated_at=now)
                else:
                    if state["status"] == "released":
                        return self._view(state, now)
                    state.update(expires=now, status="released", updated_at=now)
                    state["events"].append({"kind": "release", "owner": owner, "at": now, "previous_owner": None})
            self._write(state)
            return self._view(state, now)

    def claim(self, owner, ttl=DEFAULT_TTL):
        return self._change("claim", owner, ttl)

    def heartbeat(self, owner, ttl=DEFAULT_TTL):
        return self._change("heartbeat", owner, ttl)

    def release(self, owner):
        return self._change("release", owner)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="action", required=True)
    for action in ("status", "claim", "heartbeat", "release"):
        command = commands.add_parser(action)
        command.add_argument("--owner", required=action != "status")
        if action in ("claim", "heartbeat"):
            command.add_argument("--ttl", type=int, default=DEFAULT_TTL)
    args = parser.parse_args(argv)
    guard = Guard()
    try:
        result = guard.status() if args.action == "status" else getattr(guard, args.action)(args.owner, **({"ttl": args.ttl} if hasattr(args, "ttl") else {}))
        print(json.dumps({"ok": True, **result}, sort_keys=True, allow_nan=False))
        return 0
    except GuardError as exc:
        print(json.dumps({"ok": False, "code": exc.code, "message": str(exc)}, sort_keys=True))
        return 1
    except OSError as exc:
        print(json.dumps({"ok": False, "code": "STATE_IO", "message": str(exc)}, sort_keys=True))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
