"""Prepare, dispatch/import and consume bounded durable host-model selections."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from autoresearch.contracts import ResearchError
from autoresearch.host_model_selection import HostModelSelection
from autoresearch.host_model_batch import HostModelBatch


def _request_args(parser):
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--request-id", required=True)


def _prepare_args(parser, *, provider=False):
    _request_args(parser)
    if provider:
        parser.add_argument("--provider", choices=("claude_cli", "delegated"), required=True)
    parser.add_argument("--expected-state-version", type=int, required=True)
    parser.add_argument("--decision-limit", type=int, required=True, help="Immutable prospective limit for this host journal, at most 8.")
    parser.add_argument("--cli-budget-usd", type=float, required=True, help="Cumulative reported CLI estimate cap, at most 0.10 USD; not billing settlement.")
    parser.add_argument("--reason", required=True, help="Record actual operator-authorized scope; this text is not authorization.")
    parser.add_argument("--claude-executable", help="Required for claude_cli: explicit existing native executable, not a shell launcher.")


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    prepare = commands.add_parser("prepare", help="Freeze context, prompt and prospective limits; no model or tool execution.")
    _prepare_args(prepare, provider=True)
    advance = commands.add_parser("advance", help="Explicitly request one CLI choice and consume at most one eligible action; original IDs never resend.")
    _prepare_args(advance)
    batch = commands.add_parser("advance-batch", help="Advance at most two CLI decisions using saved feedback and one frozen batch; original IDs resume without resending.")
    _prepare_args(batch)
    batch.add_argument("--max-decisions", type=int, choices=(1, 2), required=True)
    batch_status = commands.add_parser("batch-status", help="Read one saved model batch without dispatch, consumption or recovery.")
    _request_args(batch_status)
    for name in ("request", "consume"):
        entry = commands.add_parser(name, help="Dispatch the original CLI request once." if name == "request" else "Consume one saved response through the original controller.")
        _request_args(entry)
    imported = commands.add_parser("import-response", help="Capture operator-supplied delegated JSON; does not execute research.")
    _request_args(imported)
    imported.add_argument("--response", required=True)
    status = commands.add_parser("status", help="Read journal and native/external usage separately without dispatch or consumption.")
    status.add_argument("--workspace", required=True)
    status.add_argument("--request-id")
    args = parser.parse_args()
    try:
        journal = HostModelSelection(args.workspace)
        if args.command == "advance-batch":
            result = HostModelBatch(args.workspace).advance(request_id=args.request_id,
                expected_state_version=args.expected_state_version, max_decisions=args.max_decisions,
                decision_limit=args.decision_limit, cli_budget_usd=args.cli_budget_usd,
                reason=args.reason, executable=args.claude_executable)
        elif args.command == "batch-status":
            result = HostModelBatch(args.workspace).status(request_id=args.request_id)
        elif args.command in ("prepare", "advance"):
            provider = args.provider if args.command == "prepare" else "claude_cli"
            executable = args.claude_executable if provider == "claude_cli" else None
            result = journal.prepare(request_id=args.request_id, provider=provider,
                expected_state_version=args.expected_state_version, decision_limit=args.decision_limit,
                cli_budget_usd=args.cli_budget_usd, reason=args.reason, executable=executable)
            if args.command == "advance":
                result = journal.request(request_id=args.request_id)
                if result["status"] == "received":
                    result = journal.consume(request_id=args.request_id)
        elif args.command == "request":
            result = journal.request(request_id=args.request_id)
        elif args.command == "consume":
            result = journal.consume(request_id=args.request_id)
        elif args.command == "import-response":
            result = journal.import_response(request_id=args.request_id, response_file=args.response)
        else:
            result = journal.status(request_id=args.request_id)
        print(json.dumps(result, ensure_ascii=False, allow_nan=False, indent=2))
        return 2 if result.get("status") in ("invalid", "stale", "failed", "unknown", "sending", "blocked", "needs_review") else 0
    except ResearchError as error:
        print(json.dumps({"ok": False, "code": error.code, "message": str(error), "automatic_retry": False}, ensure_ascii=False))
        return 2
    except (OSError, ValueError, TypeError):
        print(json.dumps({"ok": False, "code": "HOST_SELECTION_FAILED",
            "message": "Preserve the original journal and evidence; inspect the same request ID without resending.", "automatic_retry": False}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
