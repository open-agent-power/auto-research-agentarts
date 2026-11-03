"""Export a frozen local research project as JSON, Markdown and an evidence paper."""

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from autoresearch.project_report import export_report


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    try:
        manifest = export_report(workspace=args.workspace, output=args.output)
        print(json.dumps(manifest, ensure_ascii=False))
        return 0
    except Exception as error:
        print(json.dumps({"ok": False, "code": getattr(error, "code", "PROJECT_REPORT_FAILED"),
                          "message": "Project report could not be collected, verified or exported; no research execution was started."},
                         ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
