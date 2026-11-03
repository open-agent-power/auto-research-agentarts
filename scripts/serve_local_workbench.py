"""Serve managed local CSV projects; actions require an explicit loopback startup opt-in."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from autoresearch.local_workbench import LocalWorkbench
from autoresearch.project_workbench import create_project_server


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, help="Host-owned managed intake/project/report directory; do not use an existing research project.")
    parser.add_argument("--port", type=int, default=18791)
    parser.add_argument("--enable-local-actions", action="store_true", help="Allow explicit local intake, selection and report commands; models remain disabled without --claude-executable.")
    parser.add_argument("--claude-executable", help="Opt in to explicit model selection using this existing native Claude executable; requires --enable-local-actions.")
    args = parser.parse_args()
    try:
        workspace = LocalWorkbench(args.root)
        server = create_project_server(local_workspace=workspace, allow_local_actions=args.enable_local_actions,
                                       claude_executable=args.claude_executable, port=args.port)
        print(f"Local research workbench: http://127.0.0.1:{server.server_port}/ (actions {'enabled' if args.enable_local_actions else 'disabled'}, models {'enabled' if args.claude_executable else 'disabled'})", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            server.server_close()
        return 0
    except Exception as error:
        print(json.dumps({"ok": False, "code": getattr(error, "code", "LOCAL_WORKBENCH_FAILED"),
                          "message": "Managed local workbench could not be started; existing services remain unchanged."}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
