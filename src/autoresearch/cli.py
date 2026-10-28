import argparse
import hashlib
import json
from pathlib import Path
import sys

from .contracts import ResearchError, canonical
from .engine import Engine
from .protocol import handle_request
from .reports import write_report


def code_identity():
    digest = hashlib.sha256()
    for path in sorted(Path(__file__).parent.glob("*.py")):
        digest.update(path.name.encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def reject_nonfinite_json(value):
    raise ValueError("nonfinite JSON number")


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stdin, "reconfigure"):
        sys.stdin.reconfigure(encoding="utf-8", errors="strict")
    parser = argparse.ArgumentParser(description="Bounded research execution; no automatic cloud calls")
    subs = parser.add_subparsers(dest="command", required=True)
    demo = subs.add_parser("demo")
    demo.add_argument("--workspace", default="runs/demo")
    demo.add_argument("--steps", type=int, choices=range(1, 4), default=3)
    demo.add_argument("--finalize", action="store_true")
    tool = subs.add_parser("tool")
    tool.add_argument("--workspace", default="runs/tool")
    reconcile = subs.add_parser("reconcile")
    reconcile.add_argument("--workspace", required=True)
    reconcile.add_argument("--campaign-id", required=True)
    reconcile.add_argument("--trial-id", required=True)
    reconcile.add_argument("--confirm-worker-stopped", action="store_true")
    report_command = subs.add_parser("report")
    report_command.add_argument("--workspace", required=True)
    report_command.add_argument("--campaign-id", required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "tool":
            try:
                raw = sys.stdin.read(65537)
            except UnicodeError:
                raise ResearchError("INVALID_REQUEST", "tool input must be UTF-8") from None
            if len(raw) > 65536:
                raise ResearchError("INVALID_REQUEST", "request exceeds 64 KiB character limit")
            try:
                request = json.loads(raw, parse_constant=reject_nonfinite_json)
            except (ValueError, RecursionError):
                raise ResearchError("INVALID_REQUEST", "invalid JSON") from None
            reply = handle_request(request, args.workspace)
            print(canonical(reply))
            return 0 if reply["ok"] else 2
        engine = Engine(args.workspace)
        if args.command == "report":
            print(json.dumps(write_report(engine, args.campaign_id), ensure_ascii=False, indent=2))
            return 0
        if args.command == "reconcile":
            result = engine.reconcile_interrupted(args.campaign_id, args.trial_id, confirm_stopped=args.confirm_worker_stopped)
        else:
            state = engine.create("engineering-demo-v1", "Verify real fitting, evaluated candidate selection and durable recovery on a public engineering fixture.")
            cid = state["campaign_id"]
            if state["status"] != "finalized":
                if state["status"] == "paused":
                    engine.pause(cid, False)
                for _ in range(min(args.steps, 3-len(state["trials"]))):
                    n = len(engine.status(cid)["trials"]) + 1
                    engine.step(cid, f"demo-trial-{n}")
                if args.finalize:
                    engine.finalize(cid)
                else:
                    engine.pause(cid)
            result = engine.status(cid)
            result["code_sha256"] = code_identity()
            result["cloud_calls_made"] = 0
            report = Path(args.workspace) / "report.json"
            report.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except ResearchError as exc:
        print(canonical({"ok": False, "error": {"code": exc.code, "message": str(exc)}}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
