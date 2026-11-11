"""Persist one local OOF tool result, feedback and the next research decision."""
import argparse
import json
from pathlib import Path
import sqlite3
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from autoresearch.contracts import ResearchError
from autoresearch.research_project import ResearchProject
from autoresearch import method_registry
from autoresearch.contracts import canonical
from autoresearch.research_project import safe_path
from autoresearch.project_controller import ProjectController
from autoresearch.source_evidence_adapter import _read_file
from autoresearch.research_recipe import MAX_RECIPE_BYTES, parse_json


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    create = commands.add_parser("create", help="Register a sealed source without running a tool.")
    create.add_argument("--workspace", required=True)
    create.add_argument("--source", required=True)
    create.add_argument("--goal", required=True)
    create.add_argument("--budget-ref", required=True)
    create.add_argument("--max-tool-calls", type=int, default=1)
    create.add_argument("--method", default="p02.saved-oof-residuals", choices=tuple(method_registry.PRIMARY))

    status = commands.add_parser("status", help="Read saved state without execution or recovery.")
    status.add_argument("--workspace", required=True)

    step = commands.add_parser("step", help="Submit one allowlisted OOF diagnostic.")
    step.add_argument("--workspace", required=True)
    step.add_argument("--request-id", required=True)
    step.add_argument("--dimension", choices=("chemistry", "topography"))
    step.add_argument("--expected-state-version", type=int)

    resume = commands.add_parser("resume", help="Recover a saved result; never rerun a tool.")
    resume.add_argument("--workspace", required=True)
    resume.add_argument("--request-id", required=True)

    upgrade = commands.add_parser("upgrade", help="Explicitly register a compatible application revision without resetting history.")
    upgrade.add_argument("--workspace", required=True)
    upgrade.add_argument("--request-id", required=True)
    upgrade.add_argument("--expected-code-identity", required=True)
    upgrade.add_argument("--evidence-read-limit", type=int, default=8)
    extend = commands.add_parser("extend-local-budget", help="Explicitly increase the bounded local tool allowance up to 16 without resetting usage or model/cash/source limits.")
    extend.add_argument("--workspace", required=True)
    extend.add_argument("--request-id", required=True)
    extend.add_argument("--expected-limit", type=int, required=True)
    extend.add_argument("--new-limit", type=int, required=True)
    extend.add_argument("--reason", required=True)
    extend.add_argument("--expected-version", type=int, dest="expected_state_version")
    evidence_limit = commands.add_parser("limit-evidence-budget", help="Explicitly tighten the cumulative source-read allowance without resetting usage or changing other caps.")
    evidence_limit.add_argument("--workspace", required=True)
    evidence_limit.add_argument("--request-id", required=True)
    evidence_limit.add_argument("--expected-limit", type=int, required=True)
    evidence_limit.add_argument("--new-limit", type=int, required=True)
    evidence_limit.add_argument("--expected-state-version", type=int, required=True)
    evidence_limit.add_argument("--reason", required=True)
    for name, help_text in (("evidence-task", "Read a task-bound empty evidence manifest template."),
                            ("methods", "Read local method conditions without executing them.")):
        entry = commands.add_parser(name, help=help_text)
        entry.add_argument("--workspace", required=True)
    attach = commands.add_parser("attach-evidence", help="Capture and extract a host-selected, task-bound source bundle.")
    attach.add_argument("--workspace", required=True)
    attach.add_argument("--request-id", required=True)
    attach.add_argument("--bundle", required=True)
    attach.add_argument("--expected-state-version", type=int)
    register = commands.add_parser("register-evidence", help="Capture task-bound sources without reading their selections.")
    register.add_argument("--workspace", required=True)
    register.add_argument("--request-id", required=True)
    register.add_argument("--bundle", required=True)
    register.add_argument("--expected-state-version", type=int)
    read = commands.add_parser("read-evidence", help="Read one already registered evidence receipt.")
    read.add_argument("--workspace", required=True)
    read.add_argument("--request-id", required=True)
    read.add_argument("--receipt-snapshot-sha256", required=True)
    read.add_argument("--expected-state-version", type=int)
    next_command = commands.add_parser("next", help="Read a condition-selected decision without executing it.")
    next_command.add_argument("--workspace", required=True)
    next_command.add_argument("--need", default="next_check")
    advance = commands.add_parser("advance", help="Freeze a parent request and advance at most one eligible local action.")
    advance.add_argument("--workspace", required=True)
    advance.add_argument("--request-id", required=True)
    advance.add_argument("--need", default="next_check")
    advance.add_argument("--expected-state-version", type=int)
    context = commands.add_parser("selection-context", help="Read host conditions, bounded candidates and source evidence for an external selection proposal.")
    context.add_argument("--workspace", required=True)
    context.add_argument("--need", default="next_check")
    selection = commands.add_parser("advance-selection", help="Validate a context-bound proposal and freeze at most one allowlisted action or wait.")
    selection.add_argument("--workspace", required=True)
    selection.add_argument("--request-id", required=True)
    selection.add_argument("--proposal", required=True)
    selection.add_argument("--need", default="next_check")
    selection.add_argument("--expected-state-version", type=int)
    recipe = commands.add_parser("advance-recipe", help="Freeze a recipe decision and execute at most one original host candidate; exact-ID replay retains the original context.")
    recipe.add_argument("--workspace", required=True)
    recipe.add_argument("--request-id", required=True)
    recipe.add_argument("--recipe", required=True)
    recipe.add_argument("--need", default="next_check")
    recipe.add_argument("--expected-state-version", type=int, required=True)
    query = commands.add_parser("knowledge", help="Read the frozen indexes of actually extracted project selections.")
    query.add_argument("--workspace", required=True)
    query.add_argument("--need", required=True)
    query.add_argument("--point", choices=("clarification", "design", "preparation", "interpretation"), default="interpretation")
    query.add_argument("--limit", type=int, default=5)
    prepare = commands.add_parser("prepare-source", help="Host-only capture of an allowlisted domain source; never executes it.")
    prepare.add_argument("--method", choices=("materials.saved-steel-audit", "software.source-integrity-check", "data.tabular-quality-audit"), required=True)
    prepare.add_argument("--input", required=True)
    prepare.add_argument("--output", required=True)

    args = parser.parse_args()
    try:
        if args.command == "prepare-source":
            original, output = safe_path(Path(args.input).absolute()), safe_path(Path(args.output).absolute())
            if output == original or (original.is_dir() and output.is_relative_to(original)):
                raise ResearchError("SOURCE_OVERLAP", "Capture output must stay outside the original source.")
            adapter = method_registry.get(args.method)
            packet = adapter.capture_source(original)
            raw = canonical(packet).encode("utf-8")
            adapter.load_source(raw)
            output.parent.mkdir(parents=True, exist_ok=True)
            with output.open("xb") as stream:
                stream.write(raw)
            print(json.dumps({"ok": True, "method_id": args.method, "source_snapshot_sha256": packet["snapshot_sha256"],
                              "executed": False, "new_fits": 0}, ensure_ascii=False))
            return 0
        project = ResearchProject(args.workspace)
        if args.command == "create":
            value = project.create(
                source=args.source,
                goal=args.goal,
                budget_ref=args.budget_ref,
                max_tool_calls=args.max_tool_calls,
                method_id=args.method,
            )
        elif args.command == "status":
            value = project.status()
        elif args.command == "step":
            value = project.step(
                request_id=args.request_id,
                dimension=args.dimension,
                expected_state_version=args.expected_state_version,
            )
        elif args.command == "resume":
            value = project.resume(request_id=args.request_id)
        elif args.command == "upgrade":
            value = project.upgrade(request_id=args.request_id, expected_code_identity=args.expected_code_identity,
                                    evidence_read_limit=args.evidence_read_limit)
        elif args.command == "extend-local-budget":
            value = project.extend_local_budget(request_id=args.request_id, expected_limit=args.expected_limit,
                                                new_limit=args.new_limit, reason=args.reason,
                                                expected_state_version=args.expected_state_version)
        elif args.command == "limit-evidence-budget":
            value = project.limit_evidence_budget(request_id=args.request_id, expected_limit=args.expected_limit,
                                                  new_limit=args.new_limit, reason=args.reason,
                                                  expected_state_version=args.expected_state_version)
        elif args.command == "evidence-task":
            value = project.evidence_task()
        elif args.command == "methods":
            value = project.method_options()
        elif args.command == "attach-evidence":
            value = project.attach_evidence(request_id=args.request_id, bundle=args.bundle,
                                           expected_state_version=args.expected_state_version)
        elif args.command == "register-evidence":
            value = project.register_evidence(request_id=args.request_id, bundle=args.bundle,
                                              expected_state_version=args.expected_state_version)
        elif args.command == "read-evidence":
            value = project.read_evidence(request_id=args.request_id, receipt_snapshot_sha256=args.receipt_snapshot_sha256,
                                          expected_state_version=args.expected_state_version)
        elif args.command == "next":
            value = ProjectController(args.workspace).next(need=args.need)
        elif args.command == "advance":
            value = ProjectController(args.workspace).advance(request_id=args.request_id, need=args.need,
                                                              expected_state_version=args.expected_state_version)
        elif args.command == "selection-context":
            value = ProjectController(args.workspace).selection_context(need=args.need)
        elif args.command == "advance-selection":
            from autoresearch.project_selection import parse_proposal
            proposal = parse_proposal(_read_file(Path(args.proposal).absolute(), 64 * 1024))
            value = ProjectController(args.workspace).advance_selection(request_id=args.request_id, proposal=proposal,
                                                                        need=args.need, expected_state_version=args.expected_state_version)
        elif args.command == "advance-recipe":
            recipe = parse_json(_read_file(safe_path(Path(args.recipe).absolute()), MAX_RECIPE_BYTES),
                                maximum=MAX_RECIPE_BYTES, code="INVALID_RESEARCH_RECIPE")
            value = ProjectController(args.workspace).advance_recipe(request_id=args.request_id, recipe=recipe,
                need=args.need, expected_state_version=args.expected_state_version)
        else:
            value = project.knowledge(need=args.need, point=args.point, limit=args.limit)
        print(json.dumps(value, ensure_ascii=False))
        return 0
    except (ResearchError, OSError, ValueError, sqlite3.Error) as error:
        print(json.dumps({
            "ok": False,
            "code": getattr(error, "code", "RESEARCH_PROJECT_FAILED"),
            "message": str(error),
        }, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
