"""Cooperative fixed-pilot tickets; not an OS sandbox or provider spending cap.

This script never creates the research target, invokes a model, or dispatches a tool.
A same-user authorization file is a recorded declaration, not cryptographic identity.
"""
import argparse
from contextlib import contextmanager
from dataclasses import dataclass
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys

STUDY = "model-feedback-pilot-20261114-v1"
PIN = "78acfbe09c7d689b94e4787e83a32b3e7be9dd9c"
PROPOSAL_SHA = "cbb86b359b51f22ebb0a1dad33111e4bda055869b7979bb7bb63d1e3d842fe49"
TREE_SHA = "c38ed6b6bd319584dbdaec13cc4d29cadcec9a15f68a7d3afb6b065f2f805482"
AUTH_STATEMENT = "I authorize the fixed model-feedback-pilot-20261114-v1 within the recorded limits."
PHASES = {
    "selection": ("delegation", "mfp-v1-selection"),
    "fixed-pair": ("tool", "mfp-v1-selection"),
    "saved-audit": ("tool", "mfp-v1-saved-audit"),
    "plan-revision": ("delegation", "mfp-v1-plan-revision"),
    "independent-review": ("delegation", "mfp-v1-independent-review"),
}


class GuardError(Exception):
    def __init__(self, code):
        super().__init__(code)
        self.code = code


def _require(ok, code):
    if not ok:
        raise GuardError(code)


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode()


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _parse(raw, code):
    def unique(pairs):
        out = {}
        for key, value in pairs:
            _require(key not in out, code)
            out[key] = value
        return out
    try:
        return json.loads(raw.decode("utf-8"), object_pairs_hook=unique,
                          parse_constant=lambda _: (_ for _ in ()).throw(GuardError(code)))
    except (UnicodeError, ValueError, TypeError, RecursionError):
        raise GuardError(code) from None


def _safe_path(path):
    path = Path(path).absolute()
    for part in (path, *path.parents):
        try:
            _require(not stat.S_ISLNK(part.lstat().st_mode), "UNSAFE_PATH")
        except FileNotFoundError:
            pass
    return path


def _read(path, maximum=4 * 1024 * 1024):
    path = _safe_path(path)
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    except OSError:
        raise GuardError("FILE_UNAVAILABLE") from None
    try:
        before = os.fstat(fd)
        _require(stat.S_ISREG(before.st_mode) and before.st_nlink == 1 and before.st_size <= maximum,
                 "FILE_UNSAFE")
        chunks, count = [], 0
        while True:
            chunk = os.read(fd, min(65536, maximum + 1 - count))
            if not chunk:
                break
            chunks.append(chunk)
            count += len(chunk)
            _require(count <= maximum, "FILE_UNSAFE")
        after = os.fstat(fd)
        current = path.stat(follow_symlinks=False)
        identity = lambda x: (x.st_dev, x.st_ino, x.st_size, x.st_mtime_ns, x.st_ctime_ns)
        _require(identity(before) == identity(after) == identity(current), "FILE_CHANGED")
        return b"".join(chunks)
    finally:
        os.close(fd)


def _fsync_dir(path):
    fd = os.open(_safe_path(path), os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _create(path, raw):
    path = _safe_path(path)
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
    except FileExistsError:
        raise GuardError("CLAIM_EXISTS") from None
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
    finally:
        _fsync_dir(path.parent)


def _tree_sha(path):
    path = _safe_path(path)
    _require(path.is_dir(), "PIN_UNAVAILABLE")
    entries = {}
    for f in sorted(path.rglob("*")):
        _safe_path(f)
        if f.is_file() and "__pycache__" not in f.parts and f.suffix not in (".pyc", ".pyo"):
            entries[f.relative_to(path).as_posix()] = _sha(_read(f, 16 * 1024 * 1024))
    return _sha(_canonical(entries))


@dataclass(frozen=True)
class _Paths:
    authorization: Path
    claim: Path
    ledger: Path
    lock: Path
    target: Path
    proposal: Path
    pin_head: Path
    pin_tree: Path
    inputs: tuple


@dataclass(frozen=True)
class _Manifest:
    study: str
    pin: str
    proposal_sha: str
    tree_sha: str
    input_shas: tuple


def _default_paths():
    work = Path("/workspace/work")
    root = Path("/workspace/auto-research-agentarts")
    prefix = work / STUDY
    return _Paths(work / (STUDY + ".authorization.json"), work / (STUDY + ".claim.json"),
                  work / (STUDY + ".tickets.jsonl"), work / (STUDY + ".guard.lock"), prefix,
                  root / "runs/model-feedback-pilot-proposal-20261114/implementation/pilot.md",
                  root / ".git/worktrees/model-experience-protocol-source-78acfbe/HEAD",
                  work / "model-experience-protocol-source-78acfbe/src/autoresearch",
                  (root / "runs/sprint-013-validation-20261114/engineering-source/packet.json",
                   root / "runs/sprint-013-validation-20261114/citation-bundle.json",
                   root / "runs/sprint-013-validation-20261114/relevance-bundle.json"))


def _default_manifest():
    return _Manifest(STUDY, PIN, PROPOSAL_SHA, TREE_SHA,
        ("171ab3a47506656e17d0265dacf50c4b7e43c258ac420f6bc9ef061c1befb1d4",
         "81b4b7b06256bc85f44eac67831fdd7bef2164eb92daabf0529c0afe6bd26ea4",
         "0de61af557efc56c048692a8e4903cb961d9edd5a11ea9af8805d6d7869c4e66"))


class _Guard:
    """Internal injectable paths are for temporary tests; CLI always uses fixed constants."""
    def __init__(self, paths, manifest):
        self.p, self.m = paths, manifest

    def _anchor_path(self):
        return Path(str(self.p.claim) + ".initialized")

    def _witness_path(self, phase):
        return Path(str(self.p.ledger) + "." + phase + ".reserved")

    def _witness(self, phase, claim_sha, request_sha):
        return _canonical({"schema_version": "model-feedback-reservation-witness-v1",
                           "claim_sha256": claim_sha, "phase": phase,
                           "request_id": PHASES[phase][1], "request_sha256": request_sha})

    def _witness_names(self):
        parent = _safe_path(self.p.ledger.parent)
        prefix = self.p.ledger.name + "."
        with os.scandir(parent) as entries:
            return {entry.name for entry in entries if entry.name.startswith(prefix) and entry.name.endswith(".reserved")}

    def _project_path(self):
        return self.p.target / "project"

    def _artifact(self, phase, *, request=False):
        suffix = ".request.json" if request else ".json"
        return self.p.target / "artifacts" / (phase + suffix)

    def _authorization(self):
        try:
            raw = _read(self.p.authorization, 16384)
        except GuardError as error:
            if error.code == "FILE_UNAVAILABLE":
                raise GuardError("AUTHORIZATION_REQUIRED") from None
            raise
        value = _parse(raw, "AUTHORIZATION_INVALID")
        fields = {"schema_version", "authorized_by", "statement", "study", "proposal_sha256", "pin",
                  "workspace", "target", "delegation_limit", "tool_limit", "paid_api_allowed"}
        _require(type(value) is dict and set(value) == fields
                 and value["schema_version"] == "model-feedback-pilot-authorization-v1"
                 and value["authorized_by"] == "user" and value["statement"] == AUTH_STATEMENT
                 and value["study"] == self.m.study and value["proposal_sha256"] == self.m.proposal_sha
                 and value["pin"] == self.m.pin and value["workspace"] == str(self.p.target)
                 and value["target"] == str(self._project_path())
                 and type(value["delegation_limit"]) is int and 0 <= value["delegation_limit"] <= 3
                 and type(value["tool_limit"]) is int and 0 <= value["tool_limit"] <= 2
                 and value["paid_api_allowed"] is False, "AUTHORIZATION_INVALID")
        return value, _sha(raw)

    def _provenance(self):
        _require(_sha(_read(self.p.proposal, 100000)) == self.m.proposal_sha, "PROPOSAL_CHANGED")
        _require(_read(self.p.pin_head, 1024).decode("ascii").strip() == self.m.pin, "PIN_CHANGED")
        _require(_tree_sha(self.p.pin_tree) == self.m.tree_sha, "PIN_CHANGED")
        _require(len(self.p.inputs) == len(self.m.input_shas), "INPUT_CHANGED")
        for path, expected in zip(self.p.inputs, self.m.input_shas):
            _require(_sha(_read(path)) == expected, "INPUT_CHANGED")

    @contextmanager
    def _lock(self):
        path = _safe_path(self.p.lock)
        fd = os.open(path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
        try:
            s = os.fstat(fd)
            _require(stat.S_ISREG(s.st_mode) and s.st_nlink == 1, "FILE_UNSAFE")
            fcntl.flock(fd, fcntl.LOCK_EX)
            yield
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)

    def initialize(self):
        auth, digest = self._authorization()  # No lock, directory or claim is created without authorization.
        self._provenance()
        with self._lock():
            auth2, digest2 = self._authorization()
            _require(digest == digest2 and auth == auth2, "AUTHORIZATION_CHANGED")
            self._provenance()
            _require(not self._witness_names(), "CLAIM_EXISTS")
            for path in (self.p.claim, self.p.ledger, self._anchor_path(), self.p.target, self._project_path(),
                         *(self._witness_path(phase) for phase in PHASES)):
                _require(not _safe_path(path).exists(), "CLAIM_EXISTS")
            claim = {"schema_version": "model-feedback-pilot-claim-v1", "study": self.m.study,
                     "pin": self.m.pin, "proposal_sha256": self.m.proposal_sha,
                     "input_sha256": list(self.m.input_shas), "workspace": str(self.p.target),
                     "target": str(self._project_path()), "artifacts": str(self.p.target / "artifacts"),
                     "authorization_sha256": digest, "delegation_limit": auth["delegation_limit"],
                     "tool_limit": auth["tool_limit"], "phases": {k: list(v) for k, v in PHASES.items()}}
            claim_raw = _canonical(claim)
            _create(self.p.claim, claim_raw)
            initial = _canonical({"event": "initialized", "claim_sha256": _sha(claim_raw)})
            _create(self.p.ledger, initial + b"\n")
            _create(self._anchor_path(), _canonical({"claim_sha256": _sha(claim_raw),
                                                     "initial_sha256": _sha(initial)}))
            return {"status": "initialized", "claim_sha256": _sha(_canonical(claim))}

    def _state(self):
        auth, digest = self._authorization()
        self._provenance()
        raw = _read(self.p.claim, 65536)
        claim = _parse(raw, "CLAIM_INVALID")
        expected = {"schema_version": "model-feedback-pilot-claim-v1", "study": self.m.study,
                    "pin": self.m.pin, "proposal_sha256": self.m.proposal_sha,
                    "input_sha256": list(self.m.input_shas), "workspace": str(self.p.target),
                    "target": str(self._project_path()), "artifacts": str(self.p.target / "artifacts"),
                    "authorization_sha256": digest, "delegation_limit": auth["delegation_limit"],
                    "tool_limit": auth["tool_limit"], "phases": {k: list(v) for k, v in PHASES.items()}}
        _require(claim == expected and raw == _canonical(expected), "CLAIM_INVALID")
        ledger = _read(self.p.ledger, 1024 * 1024)
        _require(bool(ledger) and ledger.endswith(b"\n"), "LEDGER_INVALID")
        lines = ledger.splitlines()
        initial = _canonical({"event": "initialized", "claim_sha256": _sha(raw)})
        _require(lines[0] == initial, "LEDGER_INVALID")
        anchor = _canonical({"claim_sha256": _sha(raw), "initial_sha256": _sha(initial)})
        _require(_read(self._anchor_path(), 65536) == anchor, "ANCHOR_INVALID")
        states, last = {}, _sha(initial)
        for line in lines[1:]:
            event = _parse(line, "LEDGER_INVALID")
            _require(type(event) is dict and set(event) == {"previous_sha256", "event", "phase", "request_id", "request_sha256", "response_sha256"}
                     and event["previous_sha256"] == last and event["phase"] in PHASES
                     and event["request_id"] == PHASES[event["phase"]][1]
                     and type(event["request_sha256"]) is str
                     and re.fullmatch(r"[a-f0-9]{64}", event["request_sha256"])
                     and line == _canonical(event), "LEDGER_INVALID")
            phase, kind = event["phase"], event["event"]
            if kind == "reserved":
                _require(phase not in states and event["response_sha256"] is None, "LEDGER_INVALID")
                states[phase] = {"status": "unknown", "request_sha256": event["request_sha256"], "response_sha256": None}
            elif kind == "completed":
                _require(phase in states and states[phase]["status"] == "unknown"
                         and states[phase]["request_sha256"] == event["request_sha256"]
                         and type(event["response_sha256"]) is str
                         and re.fullmatch(r"[a-f0-9]{64}", event["response_sha256"]), "LEDGER_INVALID")
                states[phase] = {"status": "completed", "request_sha256": event["request_sha256"],
                                 "response_sha256": event["response_sha256"]}
            else:
                raise GuardError("LEDGER_INVALID")
            last = _sha(line)
        _require(sum(PHASES[k][0] == "delegation" for k in states) <= auth["delegation_limit"]
                 and sum(PHASES[k][0] == "tool" for k in states) <= auth["tool_limit"], "LEDGER_INVALID")
        known_names = {self._witness_path(phase).name for phase in PHASES}
        _require(self._witness_names() <= known_names, "WITNESS_MISMATCH")
        for phase in PHASES:
            path = _safe_path(self._witness_path(phase))
            if phase in states:
                _require(path.is_file() and _read(path, 65536) == self._witness(phase, _sha(raw), states[phase]["request_sha256"]),
                         "WITNESS_MISMATCH")
            else:
                _require(not path.exists(), "WITNESS_MISMATCH")
        for phase, state in states.items():
            _require(_sha(_read(self._artifact(phase, request=True), 65536)) == state["request_sha256"], "REQUEST_CHANGED")
            if state["status"] == "completed":
                _require(_sha(_read(self._artifact(phase))) == state["response_sha256"], "RESPONSE_CHANGED")
        return auth, states, last

    def _append(self, phase, event, request_sha, response_sha, last):
        item = {"previous_sha256": last, "event": event, "phase": phase,
                "request_id": PHASES[phase][1], "request_sha256": request_sha, "response_sha256": response_sha}
        fd = os.open(_safe_path(self.p.ledger), os.O_WRONLY | os.O_APPEND | os.O_NOFOLLOW | os.O_CLOEXEC)
        try:
            before = os.fstat(fd)
            _require(stat.S_ISREG(before.st_mode) and before.st_nlink == 1, "FILE_UNSAFE")
            data = _canonical(item) + b"\n"
            _require(os.write(fd, data) == len(data), "LEDGER_INCOMPLETE")
            os.fsync(fd)
        finally:
            os.close(fd)

    def reserve(self, phase):
        _require(phase in PHASES, "INVALID_PHASE")
        self._authorization()  # Preserve no-side-effect behavior if authorization is absent.
        with self._lock():
            auth, states, last = self._state()
            _require(phase not in states, "ALREADY_RESERVED")
            _require(not any(item["status"] == "unknown" for item in states.values()), "OUTCOME_UNKNOWN")
            kind = PHASES[phase][0]
            limit = auth["delegation_limit" if kind == "delegation" else "tool_limit"]
            _require(sum(PHASES[k][0] == kind for k in states) < limit, "LIMIT_EXHAUSTED")
            completed = lambda key: states.get(key, {}).get("status") == "completed"
            if phase == "selection":
                _require(not states, "PHASE_ORDER")
            elif phase == "fixed-pair":
                _require(completed("selection") and "plan-revision" not in states, "PHASE_ORDER")
            elif phase == "saved-audit":
                _require(completed("fixed-pair") and "plan-revision" not in states, "PHASE_ORDER")
            elif phase == "plan-revision":
                _require(completed("fixed-pair"), "PHASE_ORDER")
            elif phase == "independent-review":
                _require(completed("plan-revision"), "PHASE_ORDER")
            request_sha = _sha(_read(self._artifact(phase, request=True), 65536))
            claim_sha = _sha(_read(self.p.claim, 65536))
            _create(self._witness_path(phase), self._witness(phase, claim_sha, request_sha))
            self._append(phase, "reserved", request_sha, None, last)
            return {"phase": phase, "request_id": PHASES[phase][1], "request_sha256": request_sha,
                    "status": "unknown_do_not_redispatch"}

    def complete(self, phase, response_sha):
        _require(phase in PHASES and type(response_sha) is str and re.fullmatch(r"[a-f0-9]{64}", response_sha), "INVALID_REQUEST")
        self._authorization()
        with self._lock():
            _, states, last = self._state()
            _require(phase in states, "NOT_RESERVED")
            saved = states[phase]
            if saved["status"] == "completed":
                _require(saved["response_sha256"] == response_sha, "RESPONSE_CONFLICT")
            artifact = self._artifact(phase)
            _require(_sha(_read(artifact)) == response_sha, "RESPONSE_CHANGED")
            if saved["status"] == "completed":
                return {"phase": phase, "status": "response_recorded", "response_sha256": response_sha, "replayed": True}
            self._append(phase, "completed", saved["request_sha256"], response_sha, last)
            return {"phase": phase, "status": "response_recorded", "response_sha256": response_sha, "replayed": False}

    def status(self):
        self._authorization()
        with self._lock():
            auth, states, _ = self._state()
            return {"study": self.m.study, "states": states, "delegation_limit": auth["delegation_limit"],
                    "tool_limit": auth["tool_limit"], "scope": "cooperative_outer_tickets_only",
                    "completed_means": "response_recorded_not_action_success"}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("initialize")
    sub.add_parser("status")
    reserve = sub.add_parser("reserve"); reserve.add_argument("phase", choices=PHASES)
    complete = sub.add_parser("complete"); complete.add_argument("phase", choices=PHASES); complete.add_argument("sha256")
    args = parser.parse_args(argv)
    guard = _Guard(_default_paths(), _default_manifest())
    try:
        result = (guard.initialize() if args.command == "initialize" else guard.status() if args.command == "status"
                  else guard.reserve(args.phase) if args.command == "reserve" else guard.complete(args.phase, args.sha256))
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 0
    except GuardError as error:
        print(json.dumps({"error": error.code}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
