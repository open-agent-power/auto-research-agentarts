"""Compile a recipe or associate a method card with a frozen host context; never execute."""

import argparse
import json
from pathlib import Path
import stat
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from autoresearch.contracts import ResearchError
from autoresearch.project_selection import MAX_CONTEXT_BYTES
from autoresearch.research_recipe import (
    MAX_METHOD_CARD_BYTES, MAX_RECIPE_BYTES, compile_recipe, match_method_card, parse_json,
)


def read_json(path, *, maximum, code):
    path = Path(path)
    metadata = path.lstat()
    if not stat.S_ISREG(metadata.st_mode) or path.is_symlink():
        raise ResearchError(code, "Input must be a regular JSON file, not a link or directory.")
    with path.open("rb") as stream:
        raw = stream.read(maximum + 1)
    return parse_json(raw, maximum=maximum, code=code)


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    kind = parser.add_mutually_exclusive_group(required=True)
    kind.add_argument("--recipe", help="Compile the existing recipe into decision.json/proposal.json.")
    kind.add_argument("--method-card", help="Associate method knowledge; write match.json only, without a proposal.")
    parser.add_argument("--context", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    try:
        output = Path(args.output)
        if output.exists() or output.is_symlink():
            raise ResearchError("OUTPUT_EXISTS", "Output directory already exists; use a new directory.")
        context = read_json(args.context, maximum=MAX_CONTEXT_BYTES, code="INVALID_SELECTION_CONTEXT")
        if args.method_card:
            card = read_json(args.method_card, maximum=MAX_METHOD_CARD_BYTES, code="INVALID_RESEARCH_METHOD_CARD")
            decision = match_method_card(card, context)
            records = (("match.json", decision),)
            summary = {key: decision[key] for key in
                       ("status", "card_id", "card_version", "question", "applicable_methods",
                        "matching_candidate_ids", "reasons", "missing_information", "host_blockers",
                        "unreported_condition_refs", "unverified_applicability")}
        else:
            recipe = read_json(args.recipe, maximum=MAX_RECIPE_BYTES, code="INVALID_RESEARCH_RECIPE")
            decision = compile_recipe(recipe, context)
            records = (("decision.json", decision), ("proposal.json", decision["proposal"]))
            summary = {"choice": decision["proposal"]["choice"]}
        output.mkdir(parents=True, exist_ok=False)
        for filename, value in records:
            with (output / filename).open("x", encoding="utf-8", newline="\n") as stream:
                json.dump(value, stream, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)
                stream.write("\n")
        print(json.dumps({"ok": True, "output": str(output), **summary,
                          "scientific_validation": False}, ensure_ascii=False))
        return 0
    except (ResearchError, OSError, ValueError) as error:
        print(json.dumps({"ok": False, "code": getattr(error, "code", "RECIPE_COMPILE_FAILED"),
                          "message": str(error)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
