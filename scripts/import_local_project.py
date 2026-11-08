"""Move one quiescent existing project into a local manager without resetting its ledgers."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from autoresearch.contracts import ResearchError
from autoresearch.local_workbench import LocalWorkbench
from autoresearch.research_project import safe_path
from autoresearch.research_recipe import parse_json
from autoresearch.source_evidence_adapter import _read_file


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, help="Existing host-owned local workbench manager directory.")
    parser.add_argument("--workspace", help="Existing separate project directory; stop its writers before importing.")
    parser.add_argument("--request-id", required=True, help="Keep this ID and all original arguments when recovering the move.")
    parser.add_argument("--platform-run", help="Optional strict JSON operator-supplied AgentArts console excerpt, never Host authority.")
    parser.add_argument("--status", action="store_true", help="Read the original import intent/receipt without moving or selecting a project.")
    args = parser.parse_args()
    if args.status and (args.workspace or args.platform_run) or not args.status and not args.workspace:
        parser.error("Use --workspace for import, or --status without --workspace/--platform-run to read its receipt.")
    try:
        if not safe_path(Path(args.root).absolute() / "workbench.sqlite").is_file():
            raise ResearchError("WORKBENCH_NOT_FOUND", "Use an existing local workbench manager root.")
        platform_run = None
        if args.platform_run:
            platform_run = parse_json(_read_file(safe_path(Path(args.platform_run).absolute()), 16 * 1024),
                                      maximum=16 * 1024, code="INVALID_REQUEST")
        manager = LocalWorkbench(args.root)
        result = (manager.import_record(args.request_id) if args.status else
                  manager.import_project(request_id=args.request_id, workspace=args.workspace, platform_run=platform_run))
        print(json.dumps(result, ensure_ascii=False, allow_nan=False, indent=2))
        return 0
    except ResearchError as error:
        result = {"ok": False, "code": error.code, "message": str(error), "automatic_retry": False}
    except (OSError, ValueError, TypeError):
        result = {"ok": False, "code": "WORKBENCH_OPERATION_FAILED",
                  "message": "Preserve both directories and the original import ID for inspection.", "automatic_retry": False}
    print(json.dumps(result, ensure_ascii=False))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
