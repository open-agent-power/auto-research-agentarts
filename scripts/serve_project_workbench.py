"""Serve a read-only domain project, optional current report and sealed P02 evidence."""

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from autoresearch.project_workbench import check_project_workbench, create_project_server


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--bundle", help="Required matching sealed evidence for P02; omit for standalone domain projects.")
    parser.add_argument("--report", help="Explicit current project-report export directory.")
    parser.add_argument("--port", type=int, default=18785)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    try:
        if args.check:
            print(json.dumps(check_project_workbench(workspace=args.workspace, bundle=args.bundle, report=args.report), ensure_ascii=False))
            return 0
        server = create_project_server(workspace=args.workspace, bundle=args.bundle, report=args.report, port=args.port)
        print(f"Read-only active project: http://127.0.0.1:{server.server_port}/", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            server.server_close()
        return 0
    except Exception as error:
        print(json.dumps({"ok": False, "code": getattr(error, "code", "PROJECT_WORKBENCH_FAILED"),
                          "message": "Project workbench could not be bound, validated or served; existing services remain unchanged."},
                         ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
