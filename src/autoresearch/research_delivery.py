"""Startup-only verification of a completed public research delivery.

Returns frozen download bytes and checked JSON, never writes a ledger, executes
bundled source, or calls a model. The memory is a historical recall snapshot.
"""
import hashlib
from io import BytesIO
import json
import os
from pathlib import Path
import re
import stat
import zipfile

from .c01_research_verifier import PACKAGE_FILES
from .contracts import canonical, fingerprint
from .research_memory import derive_entries


REQUIRED_FILES = frozenset({"研究记录.json", "复现输入.json", "研究报告.pdf", "复现附件.zip", "图表摘要.png"})
MEMORY_FILES = frozenset({"研究记忆.json", "记忆验证.json"})
ALLOWED_FILES = REQUIRED_FILES | MEMORY_FILES | {
    "README.md", "图文检查.json", "指标对照.csv", "独立复算结果.json", "资料库验证概览.json"}
MAX_FILE_BYTES = 64 * 1024 * 1024
MAX_TOTAL_BYTES = 128 * 1024 * 1024


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _sha(value):
    _require(type(value) is str and re.fullmatch(r"[0-9a-f]{64}", value), "invalid delivery SHA-256")


def _read(path, limit=MAX_FILE_BYTES):
    metadata = path.lstat()
    _require(not path.is_symlink() and not getattr(path, "is_junction", lambda: False)()
             and stat.S_ISREG(metadata.st_mode) and metadata.st_nlink == 1
             and metadata.st_size <= limit, "unsafe or oversized delivery file")
    with path.open("rb") as stream:
        opened = os.fstat(stream.fileno())
        before = (metadata.st_dev, metadata.st_ino, metadata.st_size, metadata.st_mtime_ns, metadata.st_nlink)
        identity = (opened.st_dev, opened.st_ino, opened.st_size, opened.st_mtime_ns, opened.st_nlink)
        _require(before == identity, "delivery changed while opening")
        payload = stream.read(limit + 1)
        after = os.fstat(stream.fileno())
    _require(len(payload) == opened.st_size and len(payload) <= limit
             and identity == (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_nlink),
             "delivery changed while reading")
    return payload


def _json(payload):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            _require(key not in result, "duplicate delivery JSON key")
            result[key] = value
        return result
    def invalid(_):
        raise ValueError("nonfinite delivery JSON")
    try:
        result = json.loads(payload.decode("utf-8"), object_pairs_hook=unique, parse_constant=invalid)
        canonical(result)  # Also catches numeric overflow to infinity and excessive nesting.
        return result
    except (UnicodeError, RecursionError):
        raise ValueError("invalid delivery JSON") from None


def _check_archive(files, research, reproduction):
    """Bind the downloadable ZIP, PDF and figure to the same public record."""
    try:
        with zipfile.ZipFile(BytesIO(files["复现附件.zip"])) as archive:
            members = archive.infolist()
            names = [item.filename for item in members]
            _require(len(names) == len(set(names)) and set(names) == PACKAGE_FILES | {"package-manifest.json"},
                     "unexpected reproduction ZIP members")
            _require(sum(item.file_size for item in members) <= MAX_TOTAL_BYTES
                     and all(not item.is_dir() and not item.flag_bits & 1
                             and not stat.S_ISLNK(item.external_attr >> 16)
                             and item.file_size <= MAX_FILE_BYTES for item in members), "unsafe reproduction ZIP")
            payloads = {item.filename: archive.read(item) for item in members}
    except (zipfile.BadZipFile, RuntimeError, NotImplementedError):
        raise ValueError("invalid reproduction ZIP") from None
    manifest = _json(payloads.pop("package-manifest.json"))
    _require(type(manifest) is dict and set(manifest) == {"schema_version", "files"}
             and manifest["schema_version"] == "c01-reproduction-package-v1"
             and type(manifest["files"]) is dict and set(manifest["files"]) == PACKAGE_FILES,
             "invalid reproduction ZIP manifest")
    for name, digest in manifest["files"].items():
        _sha(digest)
        _require(hashlib.sha256(payloads[name]).hexdigest() == digest, "reproduction ZIP checksum differs")
    _require(fingerprint(_json(payloads["research.json"])) == fingerprint(research)
             and fingerprint(_json(payloads["reproduction.json"])) == fingerprint(reproduction),
             "reproduction ZIP has a different research record")
    _require(payloads["paper.pdf"] == files["研究报告.pdf"]
             and payloads["figures/comparison.png"] == files["图表摘要.png"], "report or figure belongs to another package")
    if "指标对照.csv" in files:
        _require(payloads["comparison.csv"] == files["指标对照.csv"], "comparison table belongs to another package")
    code = b"".join(payloads["source/" + name + ".py"] for name in ("c01", "c01_loop", "knowledge", "c01_research"))
    _require(hashlib.sha256(code).hexdigest() == reproduction.get("analysis_code_sha256"), "packaged evaluator identity differs")


def _memory_snapshot(snapshot, receipt, derived):
    _require(type(snapshot) is dict and {"scope", "condition_match", "entries", "scientific_validation", "warning"} <= set(snapshot)
             and not set(snapshot) - {"scope", "condition_match", "entries", "scientific_validation", "warning", "empty_reason"}
             and snapshot["scientific_validation"] is False and snapshot["condition_match"] == "exact"
             and canonical(snapshot["scope"]) == canonical(derived["scope"]), "memory scope or scientific status differs")
    _require(type(snapshot["warning"]) is str and 0 < len(snapshot["warning"]) <= 2000
             and type(snapshot["entries"]) is list and len(snapshot["entries"]) <= 8, "invalid recall snapshot")
    _require(type(receipt) is dict and receipt.get("scientific_validation") is False
             and canonical(receipt.get("scope")) == canonical(derived["scope"]), "memory verification receipt scope differs")
    if "entries" in receipt:
        _require(type(receipt["entries"]) is int and receipt["entries"] == len(snapshot["entries"]), "memory receipt count differs")
    expected = {entry["id"]: entry for entry in derived["entries"]}
    seen = set()
    for item in snapshot["entries"]:
        _require(type(item) is dict and set(item) == {"record", "inclusion_status", "source_versions"}
                 and item["inclusion_status"] == "active" and type(item["record"]) is dict, "invalid active memory entry")
        record = item["record"]
        key = record.get("id")
        _require(type(key) is str and key in expected and key not in seen, "unknown or duplicate memory observation")
        seen.add(key)
        current = expected[key]
        _require(set(record) == set(current)
                 and canonical({k: v for k, v in record.items() if k != "provenance"})
                 == canonical({k: v for k, v in current.items() if k != "provenance"}), "memory payload or role differs")
        versions = item["source_versions"]
        _require(type(versions) is list and 1 <= len(versions) <= 64, "invalid memory source history")
        hashes = set()
        for version in versions:
            _require(type(version) is dict and set(version) == set(current["provenance"])
                     and version["action_id"] == current["provenance"]["action_id"]
                     and version["reproduction_sha256"] == current["provenance"]["reproduction_sha256"], "memory source action differs")
            for field in ("source_record_sha256", "reproduction_sha256", "origin_observation_sha256"):
                _sha(version[field])
            _require(version["source_record_sha256"] not in hashes, "duplicate memory source version")
            hashes.add(version["source_record_sha256"])
        encoded = {canonical(version) for version in versions}
        _require(canonical(record["provenance"]) in encoded and canonical(current["provenance"]) in encoded,
                 "memory lacks its original or current source version")
    return snapshot


def load_research_delivery(root, expected_archive_sha256):
    """Check a fixed delivery and return JSON plus frozen download bytes.

    Scientific/source authenticity and live memory state are not established.
    Unknown files, mismatched conditions and invalid optional memory fail closed.
    """
    _sha(expected_archive_sha256)
    root = Path(root).absolute()
    for path in (root, *root.parents):
        _require(not path.is_symlink() and not getattr(path, "is_junction", lambda: False)(), "redirected research delivery")
    _require(root.is_dir(), "research delivery requires a directory")
    manifest = _json(_read(root / "交付清单.json", 65536))
    _require(type(manifest) is dict and type(manifest.get("files")) is dict
             and manifest.get("scientific_validation") is False
             and manifest.get("delivery_kind") == "local_verified_artifacts_not_cloud_deployment", "invalid delivery manifest")
    names = set(manifest["files"])
    _require(REQUIRED_FILES <= names and names <= ALLOWED_FILES
             and names & MEMORY_FILES in (set(), MEMORY_FILES), "unknown or missing delivery member")
    _require({path.name for path in root.iterdir()} == names | {"交付清单.json"}, "unlisted delivery member")
    files, total = {}, 0
    for name, digest in manifest["files"].items():
        _sha(digest)
        files[name] = _read(root / name)
        total += len(files[name])
        _require(total <= MAX_TOTAL_BYTES and hashlib.sha256(files[name]).hexdigest() == digest, "delivery checksum or byte limit differs")
    research, reproduction = _json(files["研究记录.json"]), _json(files["复现输入.json"])
    _require(type(research) is dict and type(reproduction) is dict
             and research.get("archive_sha256") == expected_archive_sha256, "research belongs to another C01 archive")
    _check_archive(files, research, reproduction)
    derived = derive_entries(research, reproduction)  # Independently invokes validate_record once; no ledger or network.
    memory = None
    if names & MEMORY_FILES:
        memory = _memory_snapshot(_json(files["研究记忆.json"]), _json(files["记忆验证.json"]), derived)
    return {"research": research, "memory": memory, "validation": derived["validation"],
            "files": {"report.pdf": files["研究报告.pdf"], "reproduction.zip": files["复现附件.zip"],
                      "comparison.png": files["图表摘要.png"]}}
