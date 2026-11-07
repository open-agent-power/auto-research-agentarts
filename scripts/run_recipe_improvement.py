"""Record one RSI decision from saved evidence; no model/tool dispatch."""

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from autoresearch.contracts import ResearchError
from autoresearch.host_model_selection import HostModelSelection
from autoresearch.recipe_improvement import read_json, read_improvement_snapshot, run_improvement_round
from autoresearch.recipe_improvement_adapter import read_recipe_validation


def saved_host_inputs(workspace, request_id, spec):
    """Use the existing ledger reader, not unverified detached validation JSON."""
    if type(spec) is not dict or set(spec) != {"issue", "acceptance", "next_question"}:
        raise ResearchError("INVALID_IMPROVEMENT_ROUND", "Spec requires issue, acceptance and next_question.")
    journal = HostModelSelection(workspace)
    record = journal.status(request_id=request_id)
    view = read_recipe_validation(workspace, request_id)
    if view["status"] == "invalid":
        raise ResearchError(view["error"]["code"], view["error"]["message"])
    if record != journal.status(request_id=request_id):
        raise ResearchError("STALE_STATE", "Host record changed during read; inspect the original request.")
    context = record["context"]
    folder = (journal.directory / record["directory"]).relative_to(journal.project.root).as_posix()
    proposal = {"schema_version": "recipe-change-proposal-result-v1", "request_id": request_id,
                "status": record["status"], "candidate": record.get("proposal"),
                "context_ref": folder + "/context.json", "prompt_ref": folder + "/prompt.json",
                "response_ref": journal.directory.name + "/" + record["response_file"]
                    if record.get("response_file") else None, "scientific_validation": False}
    # Incomplete/unknown sidecars must not be presented as verified terminal results.
    validation = view["result"] if view["status"] in ("completed", "waiting", "failed") else None
    return {"current_version": context["current_recipe"], "trace": context["research_context"],
            "goal": context["improvement_goal"], "proposal_result": proposal, "validation_result": validation,
            "request_id": request_id, **spec}


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_subparsers(dest="mode", required=True)
    fixture = modes.add_parser("fixture", help="Assess explicitly constructed JSON; never real execution evidence.")
    fixture.add_argument("--input", required=True)
    host = modes.add_parser("saved-host", help="Read existing original Host/controller records only.")
    host.add_argument("--workspace", required=True)
    host.add_argument("--request-id", required=True)
    host.add_argument("--spec", required=True)
    host.add_argument("--resume", action="store_true", help="Append saved evidence to the same pending round without dispatch.")
    for command in (fixture, host):
        command.add_argument("--output", required=True, help="Outer-loop receipt directory, not project storage.")
        command.add_argument("--round-id", required=True)
        command.add_argument("--previous-round-id")
    args = parser.parse_args()
    try:
        if args.mode == "fixture":
            inputs = read_json(args.input)
            expected = {"current_version", "trace", "goal", "proposal_result", "validation_result",
                        "request_id", "issue", "acceptance", "next_question"}
            if type(inputs) is not dict or set(inputs) != expected:
                raise ResearchError("INVALID_IMPROVEMENT_ROUND", "Use the complete synthetic fixture input.")
            kind = "synthetic_engineering_fixture"
        else:
            inputs = saved_host_inputs(args.workspace, args.request_id, read_json(args.spec))
            kind = "saved_host_validation"
        run_improvement_round(**inputs, directory=args.output, round_id=args.round_id,
            previous_round_id=args.previous_round_id, evidence_kind=kind,
            resume=args.mode == "saved-host" and args.resume)
        snapshot = read_improvement_snapshot(args.output, args.round_id)
        print(json.dumps({"ok": True, **snapshot["result"], "input_path": snapshot["input_path"]}, ensure_ascii=False))
        return 0
    except (ResearchError, OSError, ValueError, TypeError, KeyError) as error:
        print(json.dumps({"ok": False, "code": getattr(error, "code", "IMPROVEMENT_READ_FAILED"),
                          "message": str(error)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
