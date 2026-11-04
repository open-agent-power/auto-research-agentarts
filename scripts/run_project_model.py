"""Check or explicitly run one authorized, journaled local Qwen selection proposal."""
import argparse
import json
import os
from pathlib import Path
import sqlite3
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from autoresearch.contracts import ResearchError
from autoresearch.project_local_model import ProjectLocalModel


def _transport_args(parser, *, output=False):
    parser.add_argument("--cache", default="runs/local-model-cache", help="Existing pinned Qwen3:4b cache; never downloaded.")
    parser.add_argument("--ollama-executable", default=str(Path(os.environ.get("LOCALAPPDATA", "")) / "Programs/Ollama/ollama.exe"))
    if output:
        parser.add_argument("--output", required=True, help="Fresh owned-process evidence directory; never replaces an old directory.")
        parser.add_argument("--port", type=int, default=11449, help="Dedicated free loopback port; existing servers are never adopted.")


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    check = commands.add_parser("check", help="Read/hash existing executable and fixed model bytes only; no process or model request.")
    _transport_args(check)
    inspect = commands.add_parser("check-protocol", help="Inspect saved wire/response/native metadata only; no process, weights or model request.")
    inspect.add_argument("--process-evidence", required=True, help="Existing owned transport evidence directory; never changes a project.")
    authorize = commands.add_parser("authorize", help="Explicit owner-authorized cumulative local model budget change from 0 to 1.")
    authorize.add_argument("--workspace", required=True)
    authorize.add_argument("--request-id", required=True)
    authorize.add_argument("--expected-limit", type=int, required=True, choices=[0])
    authorize.add_argument("--new-limit", type=int, required=True, choices=[1])
    authorize.add_argument("--owner", required=True, help="Declared authorizing owner; this text does not verify identity or create permission.")
    authorize.add_argument("--reason", required=True)
    authorize.add_argument("--expected-state-version", type=int, required=True)
    prepare = commands.add_parser("prepare", help="Reserve the existing authorized model slot and freeze one context/payload; no inference.")
    prepare.add_argument("--workspace", required=True)
    prepare.add_argument("--request-id", required=True)
    prepare.add_argument("--expected-state-version", type=int, required=True)
    _transport_args(prepare)
    request = commands.add_parser("request", help="Send the prepared original payload at most once through an owned offline-only process.")
    request.add_argument("--workspace", required=True)
    request.add_argument("--request-id", required=True)
    _transport_args(request, output=True)
    status = commands.add_parser("status", help="Read saved model request metadata without inference or consumption.")
    status.add_argument("--workspace", required=True)
    status.add_argument("--request-id")
    consume = commands.add_parser("consume", help="Validate a saved response and explicitly submit its bounded proposal, offline.")
    consume.add_argument("--workspace", required=True)
    consume.add_argument("--request-id", required=True)
    args = parser.parse_args()
    try:
        if args.command == "check":
            transport = ProjectLocalModel(cache=args.cache, executable=args.ollama_executable)
            result = {"ok": True, "status": "checked_local_files_only", "identity": transport.identity(),
                      "model_requests": 0, "processes_started": 0, "network_requests": 0, "downloads": 0,
                      "budget_changed": False, "scientific_validation": False}
        elif args.command == "check-protocol":
            from autoresearch.project_local_model import inspect_protocol_evidence
            result = inspect_protocol_evidence(args.process_evidence)
        elif args.command == "authorize":
            from autoresearch.research_project import ResearchProject
            owner, reason = args.owner.strip(), args.reason.strip()
            if not owner or len(owner) > 128 or "\0" in owner or not reason or len(reason) > 3500 or "\0" in reason:
                raise ResearchError("INVALID_REQUEST", "A bounded nonempty owner declaration and reason are required.")
            result = ResearchProject(args.workspace).authorize_local_model_budget(request_id=args.request_id,
                expected_limit=args.expected_limit, new_limit=args.new_limit,
                reason="Declared owner (identity unverified): " + owner + "\nOwner-authorized scope: " + reason,
                expected_state_version=args.expected_state_version)
        else:
            from autoresearch.project_model_proposal import ProjectModelProposal
            journal = ProjectModelProposal(args.workspace)
            if args.command == "prepare":
                transport = ProjectLocalModel(cache=args.cache, executable=args.ollama_executable)
                result = journal.prepare(request_id=args.request_id, expected_state_version=args.expected_state_version,
                                         transport_identity=transport.identity())
            elif args.command == "request":
                transport = ProjectLocalModel(cache=args.cache, executable=args.ollama_executable, output=args.output, port=args.port)
                result = journal.request(request_id=args.request_id, transport=transport)
            elif args.command == "consume":
                result = journal.consume(request_id=args.request_id)
            else:
                result = journal.status(request_id=args.request_id)
        print(json.dumps(result, ensure_ascii=False, allow_nan=False, indent=2))
        if args.command == "check-protocol" and not result["ok"]:
            return 2
        return 0
    except ResearchError as error:
        print(json.dumps({"ok": False, "code": error.code, "message": str(error), "automatic_retry": False}, ensure_ascii=False))
        return 2
    except (OSError, ValueError, TypeError, sqlite3.Error):
        print(json.dumps({"ok": False, "code": "PROJECT_MODEL_FAILED", "message": "Operation failed; preserve the original request and local evidence, and do not automatically resend.", "automatic_retry": False}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
