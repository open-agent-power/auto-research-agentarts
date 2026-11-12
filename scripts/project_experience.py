"""Import checked saved-OOF memory, export advisory cases, and change source inclusion."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from autoresearch.contracts import ResearchError
from autoresearch.project_experience import ProjectExperienceMemory, MAX_BUNDLE_BYTES
from autoresearch.research_recipe import parse_json
from autoresearch.research_project import safe_path
from autoresearch.source_evidence_adapter import _read_file


def document(path):
    return parse_json(_read_file(safe_path(Path(path).absolute()), MAX_BUNDLE_BYTES),
                      maximum=MAX_BUNDLE_BYTES, code="INVALID_PROJECT_EXPERIENCE")


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    imported = commands.add_parser("import-project")
    imported.add_argument("--memory", required=True)
    imported.add_argument("--workspace", required=True)
    imported.add_argument("--action-id", required=True)
    imported.add_argument("--parent-action-id", help="Explicit saved parent action from the same source project")
    exported = commands.add_parser("export")
    for name in ("memory", "scope", "entry-id", "case-id", "method-card", "limitations", "output"):
        exported.add_argument("--" + name, required=True)
    exported.add_argument("--version", type=int, required=True)
    for name in ("retire", "restore"):
        status = commands.add_parser(name)
        for field in ("memory", "entry-id", "reason", "request-id"):
            status.add_argument("--" + field, required=True)
    args = parser.parse_args()
    try:
        memory = ProjectExperienceMemory(args.memory)
        if args.command == "import-project":
            result = memory.import_project(args.workspace, args.action_id, parent_action_id=args.parent_action_id)
        elif args.command == "export":
            # The limitations file is a named object, to retain the same strict
            # duplicate/nonfinite JSON handling as the other local inputs.
            limitations = document(args.limitations)
            if set(limitations) != {"limitations"}:
                raise ResearchError("INVALID_PROJECT_EXPERIENCE", "Limitations file contains exactly a limitations list.")
            result = memory.export_case(document(args.scope), args.entry_id, case_id=args.case_id,
                version=args.version, method_card=document(args.method_card), limitations=limitations["limitations"])
            destination = safe_path(Path(args.output).absolute())
            raw = (json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8")
            if destination.exists():
                if destination.read_bytes() != raw:
                    raise ResearchError("EVIDENCE_CONFLICT", "Existing case output differs; preserve the original snapshot.")
            else:
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(raw)
            result = {"output": str(destination), "case_id": result["id"], "version": result["version"],
                      "source_inclusion_status": result["source_inclusion_status"], "scientific_validation": False}
        else:
            result = memory.set_status(args.entry_id, "retired" if args.command == "retire" else "active", args.reason, args.request_id)
        print(json.dumps(result, ensure_ascii=False, allow_nan=False))
        return 0
    except (ResearchError, ValueError, OSError) as error:
        print(json.dumps({"ok": False, "code": getattr(error, "code", "INVALID_PROJECT_EXPERIENCE"), "message": str(error)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
