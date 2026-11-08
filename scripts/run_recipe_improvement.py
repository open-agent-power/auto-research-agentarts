"""Record one RSI decision from saved evidence; no model/tool dispatch."""

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from autoresearch.contracts import ResearchError
from autoresearch.recipe_improvement import (
    load_saved_export, read_improvement_round, read_improvement_snapshot, read_json, run_improvement_round,
    run_improvement_sequence, saved_host_inputs,
)


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
    exported = modes.add_parser("saved-export", help="Read supplied offline originals without a project database.")
    exported.add_argument("--evidence-root", required=True)
    exported.add_argument("--spec", required=True)
    next_input = modes.add_parser("next-input", help="Read an effective version for the next round; dispatch nothing.")
    next_input.add_argument("--output", required=True)
    next_input.add_argument("--round-id", required=True)
    sequence = modes.add_parser("sequence", help="Consume a bounded queue of saved evidence; dispatch nothing.")
    sequence.add_argument("--manifest", required=True)
    sequence.add_argument("--output", required=True)
    sequence.add_argument("--max-rounds", type=int, default=1, help="Saved assessments per invocation, not research budget.")
    for command in (fixture, host, exported):
        command.add_argument("--output", required=True, help="Outer-loop receipt directory, not project storage.")
        command.add_argument("--round-id", required=True)
        command.add_argument("--previous-round-id")
    args = parser.parse_args()
    try:
        if args.mode == "sequence":
            result = run_improvement_sequence(read_json(args.manifest), directory=args.output,
                base_directory=Path(args.manifest).absolute().parent, max_rounds=args.max_rounds)
            print(json.dumps({"ok": True, **result}, ensure_ascii=False))
            return 0
        if args.mode == "next-input":
            previous = read_improvement_round(args.output, args.round_id)
            if previous["status"] != "completed":
                raise ResearchError("IMPROVEMENT_PENDING", "Reconcile the original request before continuing.")
            print(json.dumps({"ok": True, "status": "awaiting_next_feedback", "previous_result": previous,
                              "current_version": previous["effective_recipe"],
                              "next_question": previous["next_question"], "scientific_validation": False}, ensure_ascii=False))
            return 0
        if args.mode == "fixture":
            inputs = read_json(args.input)
            expected = {"current_version", "trace", "goal", "proposal_result", "validation_result",
                        "request_id", "issue", "acceptance", "next_question"}
            if type(inputs) is not dict or set(inputs) != expected:
                raise ResearchError("INVALID_IMPROVEMENT_ROUND", "Use the complete synthetic fixture input.")
            kind = "synthetic_engineering_fixture"
        elif args.mode == "saved-host":
            inputs = saved_host_inputs(args.workspace, args.request_id, read_json(args.spec))
            kind = "saved_host_validation"
        else:
            spec = read_json(args.spec)
            if type(spec) is not dict or set(spec) != {"issue", "acceptance", "next_question"}:
                raise ResearchError("INVALID_IMPROVEMENT_ROUND", "Spec requires issue, acceptance and next_question.")
            inputs = {**load_saved_export(args.evidence_root), **spec}
            kind = "saved_export_validation"
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
