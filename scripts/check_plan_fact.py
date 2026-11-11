"""Check one declared plan assertion against its original frozen facts, without research."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from autoresearch.contracts import ResearchError
from autoresearch.local_workbench import LocalWorkbench
from autoresearch.snapshot_viewer import _json
from autoresearch.source_evidence_adapter import _read_file
from autoresearch.research_project import safe_path


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, help="Existing local workbench manager directory; never creates a research project.")
    parser.add_argument("--input", required=True, help="JSON containing project_id, host_request_id and the selected claim.")
    args = parser.parse_args()
    root = safe_path(Path(args.root).absolute())
    if not (root / "workbench.sqlite").is_file():
        print(json.dumps({"ok": False, "code": "WORKBENCH_NOT_FOUND", "message": "Select the existing workbench manager directory."}))
        return 2
    try:
        body = _json(_read_file(safe_path(Path(args.input).absolute()), 256 * 1024))
        result = LocalWorkbench(root).check_plan_fact(body)
        print(json.dumps(result, ensure_ascii=False, allow_nan=False))
        return 0
    except (ResearchError, ValueError, OSError) as error:
        print(json.dumps({"ok": False, "code": getattr(error, "code", "INVALID_REQUEST"), "message": str(error)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
