#!/usr/bin/env python3
"""One-shot synthetic Codex selection experiment; preparation never calls a model."""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import zipfile

# CPython may read a valid-looking stale __pycache__ even with -B. Point all
# subsequent project imports at a fresh private cache namespace before import.
if __name__ == "__main__" and any(name == "autoresearch" or name.startswith("autoresearch.") for name in sys.modules):
    raise RuntimeError("Project modules were loaded before the source cache guard.")
_PRIVATE_BYTECODE_CACHE = tempfile.TemporaryDirectory(prefix="s050-python-cache-")
sys.pycache_prefix = _PRIVATE_BYTECODE_CACHE.name
sys.dont_write_bytecode = True

from autoresearch import host_selection_protocol as protocol, staged_relevance_adapter as adapter
from autoresearch import project_controller, research_project
from autoresearch.contracts import canonical
from autoresearch.host_model_selection import HostModelSelection
from autoresearch.project_controller import ProjectController
from autoresearch.research_project import ResearchProject

REPO = Path(__file__).resolve().parents[1]
WORKSPACE = REPO / "runs/s050-codex-selection-pilot"
REQUEST_ID = "s050-synthetic-codex-selection"
CLI = Path("/opt/codex/bin/codex")


def fail(message):
    raise RuntimeError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def sha_file(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def encoded(value):
    return canonical(value).encode("utf-8")


def write_once(path, raw):
    with path.open("xb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    directory = os.open(path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(directory)
    finally:
        os.close(directory)


def read_json(path):
    raw = path.read_bytes()
    value = json.loads(raw)
    if raw != encoded(value):
        fail("Saved JSON must retain its original canonical bytes: " + str(path))
    return value


def source_pin(commit):
    if len(commit) != 40 or any(ch not in "0123456789abcdef" for ch in commit):
        fail("An exact published source commit is required.")
    for module in (protocol, adapter, project_controller, research_project):
        if not Path(module.__file__).resolve().is_relative_to((REPO / "src").resolve()):
            fail("Loaded project modules must come from the pinned checkout's src directory.")
    def git(*args):
        return subprocess.check_output(["git", "-C", str(REPO), *args], stderr=subprocess.DEVNULL).decode().strip()
    if git("rev-parse", "HEAD") != commit or git("status", "--porcelain", "--untracked-files=no"):
        fail("Use the clean original source commit; do not change or reconstruct the project.")
    untracked = git("ls-files", "--others", "--", "src").splitlines()
    shadow_suffixes = {".py", ".pyc", ".so", ".pyd"}
    if any(Path(name).suffix in shadow_suffixes and "__pycache__" not in Path(name).parts for name in untracked):
        fail("Untracked importable source files may shadow the pinned checkout.")
    observed = git("ls-remote", "origin", "refs/heads/main").splitlines()
    if len(observed) != 1:
        fail("The actual remote main head cannot be uniquely verified.")
    fields = observed[0].split("\t")
    if (len(fields) != 2 or fields[1] != "refs/heads/main" or len(fields[0]) != 40
            or any(ch not in "0123456789abcdef" for ch in fields[0])):
        fail("The actual remote main head is malformed.")
    remote_head = fields[0]
    subprocess.run(["git", "-C", str(REPO), "cat-file", "-e", remote_head + "^{commit}"],
                   check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.run(["git", "-C", str(REPO), "merge-base", "--is-ancestor", commit, remote_head],
                   check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for path in (Path(__file__), REPO / "docs/execution/g5-local/codex-selection-pilot-proposal.md",
                 REPO / "docs/execution/g5-local/codex-selection-pilot-proposal.json"):
        relative = str(path.relative_to(REPO))
        raw = subprocess.check_output(["git", "-C", str(REPO), "show", commit + ":" + relative])
        if raw != path.read_bytes():
            fail("The script or proposal is not bound to the source commit.")
    identity = {"commit": commit, "script_sha256": sha(Path(__file__).read_bytes()),
            "python_executable": str(Path(sys.executable).resolve()), "python_version": sys.version,
            "project_code": research_project.code_identity(), "controller_code": project_controller.code_identity()}
    receipt = {"method": "git ls-remote origin refs/heads/main plus local-object ancestry verification",
               "source_commit": commit, "observed_remote_head": remote_head}
    return identity, receipt


def cli_identity():
    path = CLI.resolve(strict=True)
    result = subprocess.run([str(path), "--version"], check=True, capture_output=True, timeout=10)
    return {"executable": str(path), "sha256": sha_file(path), "version": result.stdout.decode().strip()}


def assets(folder):
    folder.mkdir()
    def rows(data):
        return b"".join(encoded(row) + b"\n" for row in data)
    docs = [{"_id": key, "title": value, "text": value, "metadata": {}}
            for key, value in (("a", "cat dog"), ("b", "dog"), ("c", "fish"))]
    queries = [{"_id": key, "text": value, "metadata": {}}
               for key, value in (("qd", "cat"), ("qv", "unseen token"))]
    raw = {"corpus.jsonl": rows(docs), "queries.jsonl": rows(queries),
           "qrels.tsv": b"query-id\tcorpus-id\tscore\nqd\ta\t1\nqv\tb\t1\n",
           "license.md": b"Synthetic data generated locally for an engineering probe.\n"}
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, value in sorted(raw.items()):
            info = zipfile.ZipInfo(name, date_time=(2020, 1, 1, 0, 0, 0))
            archive.writestr(info, value)
    archive = buffer.getvalue()
    receipt = encoded({"description": "Locally generated synthetic files, no external source",
                       "archive_sha256": sha(archive), "files": {k: sha(v) for k, v in raw.items()}})
    selection = encoded({"dev": ["qd"], "validation": ["qv"]})
    spec = {"schema_version": "staged-relevance-development-spec-v1", "dataset_label": "Three synthetic documents",
            "source_url": "https://example.invalid/synthetic-s050", "attribution": "Locally generated synthetic fixture",
            "license_notes": {"corpus": "Synthetic", "queries_and_qrels": "Synthetic"},
            "source_provenance": {"archive_sha256": sha(archive), "source_receipt_sha256": sha(receipt),
                                  "selection_sha256": sha(selection), "qrels_semantics": adapter.SEMANTICS},
            "files": adapter.FILES, "query_splits": {"dev": ["qd"], "validation": ["qv"]},
            "comparison": adapter.COMPARISON, "limits": adapter.LIMITS}
    for name, value in {**raw, "synthetic-source.zip": archive, "source-receipt.json": receipt,
                        "selection.json": selection, "spec.json": encoded(spec)}.items():
        write_once(folder / name, value)
    packet = adapter.capture_source(folder)
    write_once(folder / "packet.json", encoded(packet))
    return packet


def schema():
    choice = {"anyOf": [
        {"type": "object", "properties": {"kind": {"const": "wait"}}, "required": ["kind"], "additionalProperties": False},
        {"type": "object", "properties": {"kind": {"const": "execute"}, "candidate_id": {"type": "string"}},
         "required": ["kind", "candidate_id"], "additionalProperties": False}]}
    return {"type": "object", "properties": {"choice": choice, "rationale": {"type": "string"},
            "evidence_citation_ids": {"type": "array", "items": {"type": "string"}}},
            "required": ["choice", "rationale", "evidence_citation_ids"], "additionalProperties": False}


def cli_argv(executable):
    return [executable, "exec", "--ignore-user-config", "--disable", "shell_tool", "--ephemeral", "--json",
            "--sandbox", "read-only", "--skip-git-repo-check", "--output-schema", str(WORKSPACE / "schema.json"),
            "--output-last-message", str(WORKSPACE / "last-message.json"), "-"]


def prepare(commit):
    identity, publication = source_pin(commit)
    cli = cli_identity()
    WORKSPACE.mkdir(parents=True, exist_ok=False)
    packet = assets(WORKSPACE / "inputs")
    project = ResearchProject(WORKSPACE / "project")
    project.create(source=WORKSPACE / "inputs/packet.json", goal="Synthetic engineering selection probe; no scientific claim",
                   budget_ref="s050-synthetic-no-project-dispatch", max_tool_calls=1, method_id=adapter.TOOL_ID)
    state = project.status()
    context = ProjectController(project.root).selection_context()
    if context["blockers"] or not context["candidates"] or state["actions"] or state["evidence_actions"]:
        fail("Synthetic project did not produce an untouched eligible selection context.")
    prompt = protocol.build_prompt(context)
    stdin = (prompt["system"] + "\n\n" + prompt["prompt"] +
             "\n\nDo not call shell, files, MCP, web, or any tools. Return only the required JSON.\n").encode()
    write_once(WORKSPACE / "context.json", encoded(context))
    write_once(WORKSPACE / "prompt.json", encoded(prompt))
    write_once(WORKSPACE / "stdin.txt", stdin)
    write_once(WORKSPACE / "schema.json", encoded(schema()))
    transport_cwd = Path(tempfile.mkdtemp(prefix="s050-codex-selection-", dir="/tmp"))
    argv = cli_argv(cli["executable"])
    record = {"schema_version": "s050-codex-selection-probe-v1", "project_id": state["id"], "run_id": state["run_id"],
              "project_snapshot_ref": state["snapshot_ref"], "project_budget": state["budget"], "source": identity, "cli": cli,
              "context_sha256": context["context_sha256"], "source_packet_sha256": packet["snapshot_sha256"],
              "input_files": {p.name: sha(p.read_bytes()) for p in sorted((WORKSPACE / "inputs").iterdir())},
              "stdin_sha256": sha(stdin), "schema_sha256": sha(encoded(schema())), "argv": argv, "transport_cwd": str(transport_cwd),
              "request_id": REQUEST_ID, "max_cli_processes": 1, "max_logical_host_delegations": 1,
              "model_cost": "unknown", "token_usage": "unknown", "provider_requests": "unknown"}
    raw = encoded(record)
    write_once(WORKSPACE / "prepare.json", raw)
    write_once(WORKSPACE / "publication-prepare.json", encoded(publication))
    return {"status": "prepared_no_host_grant_no_model", "workspace": str(WORKSPACE),
            "prepare_sha256": sha(raw), "approval_status": "pending_actual_user_approval"}


def check_approval(path, prepared):
    if path is None or not Path(path).is_file():
        fail("Explicit user approval record is required before a Host grant or CLI launch.")
    approval = read_json(Path(path))
    if (set(approval) != {"schema_version", "user_message", "source_reference", "prepare_sha256", "approved_decisions"}
            or approval["schema_version"] != "s050-user-approval-v1" or approval["prepare_sha256"] != prepared
            or type(approval["approved_decisions"]) is not int or approval["approved_decisions"] != 1
            or type(approval["user_message"]) is not str or not approval["user_message"].strip()
            or len(approval["user_message"]) > 4000
            or type(approval["source_reference"]) is not str or not approval["source_reference"].strip()):
        fail("Approval must preserve the actual user's message, source, original prepared SHA and one-decision scope.")
    return approval


def terminal_events(raw, final_raw):
    try:
        events = [protocol._json(line) for line in raw.splitlines()]
        if not events or any(type(e) is not dict for e in events):
            return False
        kinds = [e.get("type") for e in events]
        if kinds.count("thread.started") != 1 or kinds.count("turn.started") != 1 or kinds.count("turn.completed") != 1:
            return False
        if kinds[0] != "thread.started" or kinds[1] != "turn.started" or kinds[-1] != "turn.completed":
            return False
        item_events = [e for e in events if e.get("type") in {"item.started", "item.updated", "item.completed"}]
        if any(k not in {"thread.started", "turn.started", "turn.completed", "item.started", "item.updated", "item.completed"} for k in kinds):
            return False
        if any(type(e.get("item")) is not dict or e["item"].get("type") not in {"reasoning", "agent_message"}
               or (e["item"].get("type") == "agent_message" and e["type"] != "item.completed") for e in item_events):
            return False
        messages = [e["item"] for e in item_events if e["item"].get("type") == "agent_message"]
        if len(messages) != 1 or type(messages[0].get("text")) is not str:
            return False
        return encoded(protocol._json(messages[0]["text"].encode())) == encoded(protocol._json(final_raw))
    except Exception:
        return False


def execute(approval_file):
    raw = (WORKSPACE / "prepare.json").read_bytes()
    prepared = read_json(WORKSPACE / "prepare.json")
    check_approval(approval_file, sha(raw))
    if (WORKSPACE / "launch.json").exists():
        fail("Original launch marker exists; execution is unknown or complete, never resend.")
    identity, publication = source_pin(prepared["source"]["commit"])
    if identity != prepared["source"] or cli_identity() != prepared["cli"]:
        fail("Source or CLI identity changed; preserve the original pilot.")
    project = ResearchProject(WORKSPACE / "project")
    state = project.status()
    context = ProjectController(project.root).selection_context()
    prompt = protocol.build_prompt(context)
    journal = HostModelSelection(project.root)
    host_status = journal.status()
    if (state["snapshot_ref"] != prepared["project_snapshot_ref"] or state["budget"] != prepared["project_budget"]
            or state["actions"] or state["evidence_actions"] or context != read_json(WORKSPACE / "context.json")
            or host_status["grant"] is not None or host_status["requests"]
            or prepared["argv"] != cli_argv(prepared["cli"]["executable"])
            or context["context_sha256"] != prepared["context_sha256"] or prompt != read_json(WORKSPACE / "prompt.json")
            or sha((WORKSPACE / "stdin.txt").read_bytes()) != prepared["stdin_sha256"]
            or sha((WORKSPACE / "schema.json").read_bytes()) != prepared["schema_sha256"]
            or {p.name: sha(p.read_bytes()) for p in sorted((WORKSPACE / "inputs").iterdir())} != prepared["input_files"]
            or adapter.capture_source(WORKSPACE / "inputs")["snapshot_sha256"] != prepared["source_packet_sha256"]
            or not Path(prepared["transport_cwd"]).is_dir() or Path(prepared["transport_cwd"]).is_symlink()
            or any(Path(prepared["transport_cwd"]).iterdir())):
        fail("Original project, source, context, prompt or schema changed; do not launch.")
    approval = check_approval(approval_file, sha(raw))
    marker = {"prepare_sha256": sha(raw), "approval_sha256": sha(encoded(approval)), "argv": prepared["argv"],
              "status": "launch_may_have_occurred_never_retry"}
    write_once(WORKSPACE / "launch.json", encoded(marker))
    write_once(WORKSPACE / "publication-execute.json", encoded(publication))
    write_once(WORKSPACE / "approval.json", encoded(approval))
    host = journal.prepare(request_id=REQUEST_ID, provider="delegated", expected_state_version=context["state_version"],
        decision_limit=1, cli_budget_usd=0.1, reason="User approved one synthetic Codex selection; no project dispatch")
    if host["context"] != context or host["prompt"] != prompt:
        fail("Host preparation differs from the original sealed context; no launch.")
    exit_info = {"status": "unknown", "exit_code": None, "model_cost": "unknown", "token_usage": "unknown",
                 "provider_requests": "unknown", "project_dispatch": False}
    with (WORKSPACE / "stdout.jsonl").open("xb") as out, (WORKSPACE / "stderr.bin").open("xb") as err:
        try:
            completed = subprocess.run(prepared["argv"], input=(WORKSPACE / "stdin.txt").read_bytes(), stdout=out, stderr=err,
                                       cwd=prepared["transport_cwd"], timeout=180, check=False)
            exit_info["exit_code"] = completed.returncode
        except (OSError, subprocess.TimeoutExpired) as error:
            exit_info["error"] = type(error).__name__
        out.flush(); os.fsync(out.fileno()); err.flush(); os.fsync(err.fileno())
    stdout_path = WORKSPACE / "stdout.jsonl"
    output = stdout_path.read_bytes() if stdout_path.stat().st_size <= protocol.MAX_RESPONSE_BYTES else b""
    final_path = WORKSPACE / "last-message.json"
    safe_final = final_path.is_file() and not final_path.is_symlink() and final_path.stat().st_size <= protocol.MAX_RESPONSE_BYTES
    if exit_info["exit_code"] == 0 and safe_final and output:
        final = final_path.read_bytes()
        if terminal_events(output, final):
            try:
                parsed = protocol.parse_host_response(final, "delegated", context=context)
                proposal = protocol.build_proposal(context, parsed["arguments"], "Unverified Codex CLI pilot")
                received = journal.import_response(request_id=REQUEST_ID, response_file=final_path)
                if received["status"] == "received":
                    write_once(WORKSPACE / "validated-proposal.json", encoded(proposal))
                    exit_info["status"] = "received_validated_not_applied"
            except Exception as error:
                exit_info["error"] = type(error).__name__
    exit_info.update(stdout_sha256=sha_file(stdout_path), stderr_sha256=sha_file(WORKSPACE / "stderr.bin"),
                     final_sha256=sha_file(final_path) if safe_final else None)
    write_once(WORKSPACE / "exit.json", encoded(exit_info))
    if project.status() != state:
        fail("Project state changed; preserve original evidence for investigation.")
    return exit_info


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-commit", help="exact published source commit, required for preparation")
    parser.add_argument("--execute", action="store_true", help="requires a separately approved original user record")
    parser.add_argument("--approval-file")
    args = parser.parse_args()
    if args.execute:
        if args.source_commit is not None:
            parser.error("execute uses the original prepared source identity")
        result = execute(args.approval_file)
    else:
        if not args.source_commit or args.approval_file:
            parser.error("preparation requires only --source-commit")
        result = prepare(args.source_commit)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError) as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(1)
