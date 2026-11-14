"""Prepare, dispatch/import and consume bounded durable host-model selections."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from autoresearch.contracts import ResearchError, canonical
from autoresearch import research_plan_proposal, recipe_change_proposal
from autoresearch.host_model_selection import HostModelSelection
from autoresearch.host_model_batch import HostModelBatch
from autoresearch.research_recipe import MAX_RECIPE_BYTES, parse_json, validate_recipe
from autoresearch.research_project import safe_path
from autoresearch.source_evidence_adapter import _read_file
from autoresearch.saved_materials import normalize_requests


def _request_args(parser):
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--request-id", required=True)


def _prepare_args(parser, *, provider=False, purpose=True):
    _request_args(parser)
    if provider:
        parser.add_argument("--provider", choices=("claude_cli", "delegated"), required=True)
    if purpose:
        parser.add_argument("--purpose", choices=("selection", "plan", "recipe"), default="selection")
        parser.add_argument("--recipe", help="Recipe request only: a strict research-recipe-v1 JSON file.")
        parser.add_argument("--improvement-goal", help="Recipe request only: the bounded issue to improve.")
        parser.add_argument("--saved-materials", help="Plan/recipe only: strict JSON file containing exact saved-field selectors.")
    parser.add_argument("--expected-state-version", type=int, required=True)
    parser.add_argument("--decision-limit", type=int, required=True, help="Immutable prospective limit for this host journal, at most 8.")
    parser.add_argument("--cli-budget-usd", type=float, required=True, help="Configured cumulative CLI estimate threshold, at most 0.10 USD; one call can overshoot, not billing settlement.")
    parser.add_argument("--reason", required=True, help="Record actual operator-authorized scope; this text is not authorization.")
    parser.add_argument("--claude-executable", help="Required for claude_cli: explicit existing native executable, not a shell launcher.")


def _saved_materials(path):
    if path is None:
        return None
    raw = _read_file(safe_path(Path(path).absolute()), 65536)
    value = parse_json(b'{"requests":' + raw + b'}', maximum=65550, code="INVALID_REQUEST")
    if set(value) != {"requests"}:
        raise ResearchError("INVALID_REQUEST", "Use one strict saved material selector JSON value.")
    return normalize_requests(value["requests"])


def _recipe_input(args):
    if args.purpose == "recipe":
        if not args.recipe or not args.improvement_goal:
            raise ResearchError("INVALID_REQUEST", "Recipe requests require --recipe and --improvement-goal.")
        return validate_recipe(parse_json(_read_file(safe_path(Path(args.recipe).absolute()), MAX_RECIPE_BYTES),
            maximum=MAX_RECIPE_BYTES, code="INVALID_RESEARCH_RECIPE"))
    if args.recipe is not None or args.improvement_goal is not None:
        raise ResearchError("INVALID_REQUEST", "Use --recipe and --improvement-goal with --purpose recipe.")
    return None


def _preview(journal, args):
    recipe, selectors = _recipe_input(args), _saved_materials(args.saved_materials)
    materials = {"saved_materials": selectors} if selectors else {}
    protocol = recipe_change_proposal if args.purpose == "recipe" else research_plan_proposal
    context = (protocol.build_context(journal.project, recipe, args.improvement_goal, **materials)
               if args.purpose == "recipe" else protocol.build_context(journal.project, **materials))
    prompt = protocol.build_prompt(context)
    output = safe_path(Path(args.output).absolute())
    if output.is_relative_to(journal.project.root) or output.exists():
        raise ResearchError("INVALID_REQUEST", "Preview output must be a new directory outside the research project.")
    manifest = {"schema_version": "host-context-preview-v1", "purpose": args.purpose,
                "context_schema": context["schema_version"], "files": ["context.json", "prompt.json"],
                "read_only_project": True, "host_request_prepared": False, "scientific_validation": False}
    output.mkdir(parents=True, exist_ok=False)
    for name, value in (("context.json", context), ("prompt.json", prompt), ("manifest.json", manifest)):
        with (output / name).open("xb") as stream:
            stream.write(canonical(value).encode("utf-8"))
    return {**manifest, "output": str(output)}


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    prepare = commands.add_parser("prepare", help="Freeze context, prompt and prospective limits; no model or tool execution.")
    _prepare_args(prepare, provider=True)
    advance = commands.add_parser("advance", help="Request one CLI response and consume its action or save its plan proposal; original IDs never resend.")
    _prepare_args(advance)
    preview = commands.add_parser("preview", help="Read-only plan/recipe context and native prompt export; no Host preparation or allowance.")
    preview.add_argument("--workspace", required=True)
    preview.add_argument("--purpose", choices=("plan", "recipe"), required=True)
    preview.add_argument("--recipe", "--current-recipe", dest="recipe")
    preview.add_argument("--improvement-goal")
    preview.add_argument("--saved-materials")
    preview.add_argument("--output", required=True)
    batch = commands.add_parser("advance-batch", help="Advance at most two CLI decisions using saved feedback and one frozen batch; original IDs resume without resending.")
    _prepare_args(batch, purpose=False)
    batch.add_argument("--max-decisions", type=int, choices=(1, 2), required=True)
    delegated = commands.add_parser("advance-delegated-batch", help="Prepare or resume delegated decisions without dispatching a model; import each original response separately.")
    _request_args(delegated)
    delegated.add_argument("--expected-state-version", type=int, required=True)
    delegated.add_argument("--decision-limit", type=int, required=True, help="Original cumulative Host decision-slot limit, at most 8.")
    delegated.add_argument("--cli-budget-usd", type=float, required=True, help="Original CLI estimate threshold; delegated cost remains unknown.")
    delegated.add_argument("--reason", required=True)
    delegated.add_argument("--max-decisions", type=int, choices=(1, 2), required=True, help="Maximum selection steps; an optional plan uses one additional original Host slot.")
    delegated.add_argument("--post-action-plan", action="store_true", help="After a completed action, prepare one feedback plan for explicit adoption; no saved per-query materials are added automatically.")
    batch_status = commands.add_parser("batch-status", help="Read one saved model batch without dispatch, consumption or recovery.")
    _request_args(batch_status)
    command_help = {
        "request": "Dispatch the original CLI request once.",
        "consume": "Consume one saved response as an action or a proposed plan.",
        "reconcile-usage": "Read original CLI receipts to reconcile reported usage without dispatch or consumption.",
        "adopt-plan": "Explicitly adopt the original plan proposal into a saved research plan revision.",
        "reject-plan": "Preserve the original plan proposal and record why it was rejected.",
    }
    for name, help_text in command_help.items():
        entry = commands.add_parser(name, help=help_text)
        _request_args(entry)
        if name == "reject-plan":
            entry.add_argument("--reason", required=True)
    imported = commands.add_parser("import-response", help="Capture operator-supplied delegated JSON; does not execute research.")
    _request_args(imported)
    imported.add_argument("--response", required=True)
    status = commands.add_parser("status", help="Read journal and native/external usage separately without dispatch or consumption.")
    status.add_argument("--workspace", required=True)
    status.add_argument("--request-id")
    args = parser.parse_args()
    try:
        journal = HostModelSelection(args.workspace)
        if args.command == "preview":
            result = _preview(journal, args)
        elif args.command == "advance-batch":
            result = HostModelBatch(args.workspace).advance(request_id=args.request_id,
                expected_state_version=args.expected_state_version, max_decisions=args.max_decisions,
                decision_limit=args.decision_limit, cli_budget_usd=args.cli_budget_usd,
                reason=args.reason, executable=args.claude_executable)
        elif args.command == "advance-delegated-batch":
            result = HostModelBatch(args.workspace).advance_delegated(request_id=args.request_id,
                expected_state_version=args.expected_state_version, max_decisions=args.max_decisions,
                decision_limit=args.decision_limit, cli_budget_usd=args.cli_budget_usd,
                reason=args.reason, post_action_plan=args.post_action_plan)
        elif args.command == "batch-status":
            result = HostModelBatch(args.workspace).status(request_id=args.request_id)
        elif args.command in ("prepare", "advance"):
            provider = args.provider if args.command == "prepare" else "claude_cli"
            executable = args.claude_executable if provider == "claude_cli" else None
            current_recipe = _recipe_input(args)
            if args.purpose == "selection" and args.saved_materials is not None:
                raise ResearchError("INVALID_REQUEST", "Use --saved-materials with plan or recipe requests.")
            selectors = _saved_materials(args.saved_materials)
            materials = {"saved_materials": selectors} if selectors else {}
            result = journal.prepare(request_id=args.request_id, provider=provider,
                expected_state_version=args.expected_state_version, decision_limit=args.decision_limit,
                cli_budget_usd=args.cli_budget_usd, reason=args.reason, executable=executable, purpose=args.purpose,
                current_recipe=current_recipe, improvement_goal=args.improvement_goal, **materials)
            if args.command == "advance":
                result = journal.request(request_id=args.request_id)
                if result["status"] == "received":
                    result = journal.consume(request_id=args.request_id)
        elif args.command == "request":
            result = journal.request(request_id=args.request_id)
        elif args.command == "consume":
            result = journal.consume(request_id=args.request_id)
        elif args.command == "reconcile-usage":
            result = journal.reconcile_usage(request_id=args.request_id)
        elif args.command == "adopt-plan":
            result = journal.adopt_plan(request_id=args.request_id)
        elif args.command == "reject-plan":
            result = journal.reject_plan(request_id=args.request_id, reason=args.reason)
        elif args.command == "import-response":
            result = journal.import_response(request_id=args.request_id, response_file=args.response)
        else:
            result = journal.status(request_id=args.request_id)
        print(json.dumps(result, ensure_ascii=False, allow_nan=False, indent=2))
        return 2 if result.get("status") in ("invalid", "stale", "failed", "unknown", "sending", "blocked", "needs_review") else 0
    except ResearchError as error:
        print(json.dumps({"ok": False, "code": error.code, "message": str(error), "automatic_retry": False}, ensure_ascii=False))
        return 2
    except (OSError, ValueError, TypeError):
        print(json.dumps({"ok": False, "code": "HOST_SELECTION_FAILED",
            "message": "Preserve the original journal and evidence; inspect the same request ID without resending.", "automatic_retry": False}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
