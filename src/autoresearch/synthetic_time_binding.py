"""Read-only Project binding to the fixed S134 artificial time fixture.

This is not a UCI reader, source/license authentication, signature, scientific
validation or permission to dispatch.  The caller must hold the Project writer
and must recheck its manager/Project claims in the appropriate lock order.
"""
import builtins
import hashlib
import os
from pathlib import Path
import stat
import types

from .contracts import ResearchError, fingerprint, identifier

_PACKET_SHA = "e0930f259b942f03ba044bdd3e5dcf1a75f49cf14fe764e07b2e495c1be157e9"
_REPORT_SHA = "1d18eeb4c6fccfcf8675c235fb8c4e0d0028366da3a4f54ab9f15e2ccda59772"
_SNAPSHOT_SHA = "eba485b9b69a06ec57998dfc5ab2149f42ee307d984221df56f4693d5d468a72"
_CSV_SHA = "26ef793afe159f65bf221b7464217c0f6525492d160fe4cb2cdaa8a0d39eb96e"
_SPEC_SHA = "5214971da4b082abc658e78e3c08f8a683ca6566f214a0c076f95e3daa396705"
_CONFIG_SHA = "59b546287679cbc127b13ede131bfd6f6e47806bd167b9797e5ee58d08d0a94f"
_SCOPE_SHA = "3ce95bf96e2307d290ec5cfb2810ce14195b571a3e27f08cb792adda9f122cdf"
_GENERATOR_SHA = "fc9e020ca6c7be26d18521a2add31aa4450c6333cda5bb9dd8a2fa351449c398"
_RECALCULATOR_SHA = "c307a0b90682748018aa25bf75c1397ebc86d49e8dfb7262a0aa10177309beda"
_TABULAR_IDENTITY = "95c552ae5eb95e559fa9e9e94987caa131da0780ca45046bf8434a0b534fd825"
_FILES = ("claim.json", "source.csv", "spec.json", "source.json", "report.json", "receipt.json")
_ROOT = Path(__file__).absolute().parents[2]
_GENERATOR = _ROOT / "scripts" / "prepare_synthetic_time_fixture.py"
_RECALCULATOR = _ROOT / "scripts" / "synthetic_time_report.py"


def _require(condition, message):
    if not condition:
        raise ResearchError("EVIDENCE_CHANGED", message)


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _source_bytes(path, maximum):
    """Bound source-code reads and refuse symlink path components."""
    path = Path(path).absolute()
    for part in (path, *path.parents):
        _require(not part.is_symlink() and not getattr(part, "is_junction", lambda: False)(),
                 "A synthetic verifier source path redirects through a link.")
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        before = os.fstat(fd)
        _require(stat.S_ISREG(before.st_mode) and 0 < before.st_size <= maximum, "A verifier source is unavailable or oversized.")
        chunks = []; remaining = maximum + 1
        while remaining:
            part = os.read(fd, min(65536, remaining))
            if not part:
                break
            chunks.append(part); remaining -= len(part)
        raw = b"".join(chunks)
        after = os.fstat(fd); current = os.stat(path, follow_symlinks=False)
        identity = lambda st: (st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns, st.st_ctime_ns)
        _require(identity(before) == identity(after) == identity(current) and len(raw) == before.st_size,
                 "A verifier source changed while being read.")
        return raw
    finally:
        os.close(fd)


_BOOT_VERIFIER_SHA = _sha(_source_bytes(Path(__file__), 256 * 1024))


def _load_exact_generator():
    """Compile the checked source bytes, avoiding script-module pyc and sys.modules.

    A local import hook injects only the equally checked S134 calculator into
    this isolated module namespace. It does not change global import state.
    """
    generator_raw = _source_bytes(_GENERATOR, 256 * 1024)
    calculator_raw = _source_bytes(_RECALCULATOR, 256 * 1024)
    _require(_sha(generator_raw) == _GENERATOR_SHA and _sha(calculator_raw) == _RECALCULATOR_SHA,
             "The fixed S134 generator or calculator source changed.")
    checker = types.ModuleType("_s135_fixed_synthetic_time_report")
    checker.__file__ = str(_RECALCULATOR)
    exec(compile(calculator_raw, str(_RECALCULATOR), "exec", dont_inherit=True), checker.__dict__)
    loader = types.ModuleType("_s135_fixed_synthetic_time_fixture")
    loader.__file__ = str(_GENERATOR)
    loader.__package__ = "scripts"
    original_import = builtins.__import__

    def import_fixed(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "scripts" and level == 0 and fromlist == ("synthetic_time_report",):
            return types.SimpleNamespace(synthetic_time_report=checker)
        return original_import(name, globals, locals, fromlist, level)

    namespace = dict(vars(builtins))
    namespace["__import__"] = import_fixed
    loader.__dict__["__builtins__"] = namespace
    exec(compile(generator_raw, str(_GENERATOR), "exec", dont_inherit=True), loader.__dict__)
    _require(loader.checker is checker and loader.__file__ == str(_GENERATOR)
             and checker.__file__ == str(_RECALCULATOR), "The fixed synthetic verifier binding changed.")
    return loader


def _read_originals(generator, output):
    """Read all original bytes using S134's exact allowlist and safe-path gates."""
    generator._require_files(output, _FILES)
    limits = {"claim.json": 256 * 1024, "source.csv": generator.checker.MAX_CSV_BYTES,
              "spec.json": generator.tabular.MAX_SPEC_BYTES, "source.json": generator.tabular.MAX_PACKET_BYTES,
              "report.json": 256 * 1024, "receipt.json": 256 * 1024}
    originals = {name: generator._read_bounded(output / name, limits[name]) for name in _FILES}
    generator._require_files(output, _FILES)
    return originals


def _directory_identity(path):
    value = path.stat(follow_symlinks=False)
    _require(stat.S_ISDIR(value.st_mode), "The original synthetic report directory is unavailable.")
    return value.st_dev, value.st_ino, value.st_mtime_ns, value.st_ctime_ns


def _committed_project(project, stored):
    """Compare the caller's full status with one actual committed snapshot."""
    actual = project.status()
    _require(type(stored) is dict and actual == stored, "The Project record differs from the committed original.")
    return actual


def verify_observed(project, stored, report_dir):
    """Recompute and bind the six S134 originals to this Project's source.

    Reads the full artificial CSV (including its numeric bytes). It performs no
    research action and writes no ledger or source. Only an already committed
    Project status is accepted. An unlocked reader receives a snapshot observation;
    a caller performing a write must hold the Project writer. The hashes are cooperative
    consistency checks, not cryptographic signatures or an OS isolation claim.
    """
    try:
        from .local_workbench import _check_staged_runtime
        from .research_project import ResearchProject, code_identity
        from . import tabular_quality_adapter as tabular

        _require(type(project) is ResearchProject, "A bound original Project is required.")
        _check_staged_runtime()
        verifier_sha = _sha(_source_bytes(Path(__file__), 256 * 1024))
        _require(verifier_sha == _BOOT_VERIFIER_SHA, "The loaded synthetic binding source changed.")
        generator = _load_exact_generator()
        _require(generator.tabular is tabular and tabular.code_identity() == _TABULAR_IDENTITY,
                 "The original synthetic tabular producer changed.")
        output = generator._path(report_dir, existing=True)
        directory_before = _directory_identity(output)
        before = _read_originals(generator, output)
        _require(_sha(before["source.json"]) == _PACKET_SHA and _sha(before["report.json"]) == _REPORT_SHA
                 and _sha(before["source.csv"]) == _CSV_SHA and _sha(before["spec.json"]) == _SPEC_SHA,
                 "The fixed synthetic originals changed.")
        state = _committed_project(project, stored)
        identifier(state["id"], "project_id"); identifier(state["run_id"], "run_id")
        _require(state["registration"]["method_id"] == tabular.TOOL_ID
                 and state["registration"]["source_sha256"] == _PACKET_SHA
                 and state["source_snapshot_sha256"] == _SNAPSHOT_SHA
                 and fingerprint(state["source_scope"]) == _SCOPE_SHA
                 and state["code_identity"] == code_identity(),
                 "The Project's fixed source, scope or producer differs.")
        source_path = project.root / "source.json"
        project_source = generator._read_bounded(source_path, tabular.MAX_PACKET_BYTES)
        _require(project_source == before["source.json"] and _sha(project_source) == _PACKET_SHA,
                 "The Project source bytes differ from the original synthetic packet.")
        packet = project._source(state)
        _require(packet["snapshot_sha256"] == _SNAPSHOT_SHA and packet["scope"] == state["source_scope"]
                 and packet["source"]["sha256"] == _CSV_SHA and packet["spec_source"]["sha256"] == _SPEC_SHA,
                 "The Project packet scope or original assets differ.")
        receipt = generator.verify(output)
        report = tabular._parse(before["report.json"])
        _require(type(receipt) is dict and receipt["report_sha256"] == _REPORT_SHA
                 and receipt["packet_sha256"] == _PACKET_SHA and receipt["source_snapshot_sha256"] == _SNAPSHOT_SHA
                 and receipt["generator_sha256"] == _GENERATOR_SHA and receipt["recalculator_sha256"] == _RECALCULATOR_SHA
                 and receipt["tabular_identity"] == _TABULAR_IDENTITY
                 and report["config_sha256"] == fingerprint(report["config"]) == _CONFIG_SHA
                 and report["scope_sha256"] == fingerprint(state["source_scope"]) == _SCOPE_SHA,
                 "The original synthetic receipt or report binding differs.")
        after = _read_originals(generator, output)
        _require(after == before and _directory_identity(output) == directory_before
                 and generator._read_bounded(source_path, tabular.MAX_PACKET_BYTES) == project_source
                 and _committed_project(project, stored) == state and project._source(state) == packet,
                 "The original synthetic files or Project changed during verification.")
        _require(_sha(_source_bytes(_GENERATOR, 256 * 1024)) == _GENERATOR_SHA
                 and _sha(_source_bytes(_RECALCULATOR, 256 * 1024)) == _RECALCULATOR_SHA
                 and _sha(_source_bytes(Path(__file__), 256 * 1024)) == verifier_sha
                 and tabular.code_identity() == _TABULAR_IDENTITY and state["code_identity"] == code_identity(),
                 "The synthetic verifier or Project producer changed during verification.")
        _check_staged_runtime()
        return {"schema_version": "synthetic-time-project-binding-v1", "synthetic_only": True,
                "project_id": state["id"], "run_id": state["run_id"], "packet_sha256": _PACKET_SHA,
                "report_sha256": _REPORT_SHA, "source_snapshot_sha256": _SNAPSHOT_SHA, "scope_sha256": _SCOPE_SHA,
                "csv_sha256": _CSV_SHA, "spec_sha256": _SPEC_SHA, "config_sha256": _CONFIG_SHA,
                "generator_sha256": _GENERATOR_SHA, "recalculator_sha256": _RECALCULATOR_SHA,
                "tabular_identity": _TABULAR_IDENTITY, "verifier_sha256": verifier_sha,
                "project_code_identity": state["code_identity"], "original_files_sha256": {name:_sha(before[name]) for name in _FILES},
                "clock": report["config"]["clock"], "facts": report["facts"], "scientific_validation": False,
                "source_license_verified": False, "execution_authorized": False}
    except ResearchError:
        raise
    except (OSError, ValueError, TypeError, AttributeError, KeyError, IndexError, OverflowError, RecursionError):
        raise ResearchError("EVIDENCE_CHANGED", "The synthetic report, producer or original Project is unavailable or changed.") from None


def verify_original(project, stored, report_dir):
    """Verify the original when the caller holds the cooperative Project writer."""
    return verify_observed(project, stored, report_dir)
