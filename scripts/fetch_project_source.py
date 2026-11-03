"""Fetch one Europe PMC DOI response for an existing project, or prepare its bundle offline."""
import argparse
import json
from pathlib import Path
import sqlite3
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from autoresearch.contracts import ResearchError
from autoresearch.europe_pmc import EuropePmcSource


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    fetch = commands.add_parser("fetch", help="Reserve one fixed-endpoint DOI request within the frozen project allowance; unknown requests are never resent.")
    fetch.add_argument("--workspace", required=True)
    fetch.add_argument("--request-id", required=True)
    fetch.add_argument("--doi", required=True)
    fetch.add_argument("--output", required=True)
    status = commands.add_parser("status", help="Recover saved response metadata offline; never perform network I/O.")
    status.add_argument("--workspace", required=True)
    status.add_argument("--request-id", required=True)
    bundle = commands.add_parser("build-bundle", help="Build a task-bound selection bundle from the saved response; offline only.")
    bundle.add_argument("--workspace", required=True)
    bundle.add_argument("--request-id", required=True)
    bundle.add_argument("--output", required=True)
    args = parser.parse_args()
    try:
        if args.command == "build-bundle":
            from autoresearch.source_connector_bundle import build_bundle
            result = build_bundle(workspace=args.workspace, request_id=args.request_id, output=args.output)
        else:
            connector = EuropePmcSource(args.workspace)
            result = connector.fetch(args.request_id, args.doi, args.output) if args.command == "fetch" else connector.status(args.request_id)
        print(json.dumps(result, ensure_ascii=False))
        return 0 if result.get("status") not in ("failed", "unknown") else 2
    except (ResearchError, OSError, ValueError, sqlite3.Error) as error:
        print(json.dumps({"ok": False, "code": getattr(error, "code", "SOURCE_FETCH_FAILED"), "message": str(error)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
