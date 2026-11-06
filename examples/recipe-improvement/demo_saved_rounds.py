"""Two constructed rounds through the actual CLI. No model, research tools or scientific results."""

import argparse
import copy
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from autoresearch.contracts import canonical
from autoresearch.project_selection import seal_context
from autoresearch.recipe_change_proposal import build_proposal
from autoresearch.recipe_improvement import read_improvement_round
from autoresearch.research_project import safe_path, write_bytes_once
from autoresearch.research_recipe import compile_recipe


GROUPED = {"method_id": "data.grouped-quality-profile", "evaluation_ref": "grouped-quality-profile-v1"}
SOURCE = {"method_id": "research.source-selection",
          "evaluation_ref": "source-extraction-only-not-scientific-approval"}


def fixture_inputs(current=None, *, request_id="synthetic-rsi-1", target=None, failed=False):
    """Every feedback, provider declaration, artifact and controller receipt below is FAKE."""
    selection = json.loads((ROOT / "examples/recipe-improvement/contexts/feedback.context.json").read_text("utf-8"))
    selection.pop("context_sha256")
    primary = {"method_id": "data.tabular-quality-audit", "evaluation_ref": "tabular-quality-audit-v1"}
    selection["conditions"] = [{**pair, "condition": "satisfied", "completed": False,
                                "reasons": ["Synthetic saved-feedback fixture."], "missing_information": [],
                                "execution_blockers": []} for pair in (primary, GROUPED, SOURCE)]
    selection = seal_context(selection)
    if current is None:
        current = json.loads((ROOT / "examples/research-recipes/tabular-group-first.json").read_text("utf-8"))
        current["id"] = "synthetic-rsi-recipe"
        current["ordered_methods"] = [primary]
    current = copy.deepcopy(current)
    target = copy.deepcopy(target or GROUPED)
    trace = {"schema_version": "research-plan-context-v1", "selection_context": selection,
             "feedback": [{"action_id": "fixture-prior", "request_id": "synthetic-prior",
                           "method_id": primary["method_id"], "status": "completed",
                           "observations": [{"data_kind": "synthetic_engineering_fixture", "zeros": 2}],
                           "next_decision": {"reason": "Synthetic follow-up required."},
                           "failure": None, "artifact_ref": "synthetic/quality-result.json"}]}
    goal = "Synthetic: select the available follow-up omitted by the effective recipe."
    candidate = copy.deepcopy(current)
    candidate["version"] += 1
    candidate["ordered_methods"] = [target]
    context = {"schema_version": "recipe-change-context-v1", "research_context": trace,
               "current_recipe": current, "improvement_goal": goal}
    proposal = build_proposal(context, {"candidate": candidate, "reason": "Synthetic recipe omitted this follow-up.",
        "feedback_action_ids": ["fixture-prior"], "expected_improvement": "Select the named existing fixture candidate.",
        "validation_plan": "Read a constructed saved validation; no real tool was run."},
        "SYNTHETIC FIXTURE - NOT AN ACTUAL MODEL CALL")
    baseline, proposed = compile_recipe(current, selection), compile_recipe(candidate, selection)
    status = "failed" if failed else "completed"
    outcome = {"schema_version": "project-controller-advance-v1", "project_id": selection["project_id"],
        "request_id": request_id, "request_sha256": "a" * 64, "status": status, "replayed": False,
        "decision": {}, "blockers": [], "child_request_id": "synthetic-child-" + request_id,
        "result": {"data_kind": "synthetic_engineering_fixture"}, "scientific_validation": False,
        "selection_context_sha256": selection["context_sha256"], "selection_proposal": proposed["proposal"],
        "recipe_decision": proposed}
    return {"current_version": current, "trace": trace, "goal": goal,
        "proposal_result": {"schema_version": "recipe-change-proposal-result-v1", "request_id": request_id,
            "status": "proposed", "candidate": proposal, "context_ref": "synthetic/context.json",
            "prompt_ref": "synthetic/prompt.json", "response_ref": "synthetic/response.json", "scientific_validation": False},
        "validation_result": {"schema_version": "recipe-change-validation-v1", "request_id": request_id,
            "status": status, "baseline_decision": baseline, "candidate_decision": proposed,
            "selection_changed": baseline["proposal"]["choice"] != proposed["proposal"]["choice"],
            "controller_outcome": outcome, "artifact_refs": ["synthetic/validation-result.json"],
            "scientific_validation": False}, "request_id": request_id,
        "issue": {"summary": "Synthetic saved quality feedback is not followed up by the effective recipe.",
                  "feedback_action_ids": ["fixture-prior"]},
        "acceptance": target, "next_question": "Check source interpretation after this bounded fixture decision."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    directory = safe_path(Path(args.output).absolute())
    directory.mkdir(parents=True, exist_ok=True)
    for number in (1, 2):
        previous = read_improvement_round(directory, "round-1") if number == 2 else None
        inputs = fixture_inputs(previous["effective_recipe"] if previous else None,
                                request_id=f"synthetic-rsi-{number}", target=SOURCE if previous else GROUPED,
                                failed=bool(previous))
        path = directory / f"fixture-input-{number}.json"
        write_bytes_once(path, canonical(inputs).encode("utf-8"))
        command = [sys.executable, "-B", str(ROOT / "scripts/run_recipe_improvement.py"), "fixture",
                   "--input", str(path), "--output", str(directory), "--round-id", f"round-{number}"]
        if previous:
            command += ["--previous-round-id", "round-1"]
        subprocess.run(command, check=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
