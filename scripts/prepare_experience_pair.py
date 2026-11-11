"""Freeze an offline experience ablation from an existing project, without research."""

import argparse
import copy
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from autoresearch import research_plan_proposal as protocol
from autoresearch.contracts import ResearchError, canonical
from autoresearch.host_model_selection import HostModelSelection
from autoresearch.project_selection import seal_context
from autoresearch.research_project import ResearchProject, require, safe_path, write_bytes_once
from autoresearch.research_recipe import parse_json
from autoresearch.source_evidence_adapter import _read_file


MAX_FILE_BYTES = 1024 * 1024
FROZEN_FILES = {f"{arm}-{kind}.json" for arm in ("control", "current") for kind in ("context", "prompt")}


def _control_context(current):
    control = copy.deepcopy(current)
    selection = control["selection_context"]
    experience = selection.pop("experience", None)
    require(experience and experience.get("cases"), "NO_ACTIVE_EXPERIENCE",
            "The current plan context must contain an explicitly active historical case.")
    selection.pop("context_sha256")
    control["selection_context"] = seal_context(selection)
    return control


def _unchanged(project, host, before, host_before):
    require(project.status() == before, "STALE_STATE",
            "Project changed during capture; preserve any output artifacts and do not retry automatically.")
    require(host.status() == host_before, "HOST_STATE_CHANGED",
            "Host status changed during capture; preserve any output artifacts and do not retry automatically.")


def _read_json(path):
    return parse_json(_read_file(safe_path(path), MAX_FILE_BYTES), maximum=MAX_FILE_BYTES,
                      code="INVALID_EXPERIENCE_PAIR")


def verify_pair(output):
    """Reject changed frozen bytes before parsing or reusing either native prompt."""
    output = safe_path(Path(output).absolute()).resolve()
    manifest = _read_json(output / "manifest.json")
    require(manifest.get("schema_version") == "experience-pair-v1"
            and set(manifest.get("files", {})) == FROZEN_FILES,
            "INVALID_EXPERIENCE_PAIR", "Use the complete four-file experience pair manifest.")
    values = {}
    for name in sorted(FROZEN_FILES):
        raw = _read_file(safe_path(output / name), MAX_FILE_BYTES)
        require(manifest["files"][name] == {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()},
                "EVIDENCE_CHANGED", "Frozen file bytes changed: " + name)
        values[name] = parse_json(raw, maximum=MAX_FILE_BYTES, code="INVALID_EXPERIENCE_PAIR")
    current, control = values["current-context.json"], values["control-context.json"]
    require(control == _control_context(current), "INVALID_EXPERIENCE_PAIR",
            "Only selection_context.experience and its context_sha256 may differ.")
    selection = current["selection_context"]
    require(all(manifest[key] == selection[key] for key in ("project_id", "state_version", "snapshot_ref"))
            and manifest["case_ids"] == [item["case_id"] for item in selection["experience"]["cases"]]
            and manifest["scientific_validation"] is False,
            "INVALID_EXPERIENCE_PAIR", "Manifest must retain the actual project, snapshot and active case identities.")
    for arm, context in (("control", control), ("current", current)):
        require(manifest["arms"][arm] == {
            "mode": "offline_ablation" if arm == "control" else "frozen_current",
            "context_file": arm + "-context.json", "prompt_file": arm + "-prompt.json",
            "context_sha256": context["selection_context"]["context_sha256"]},
            "INVALID_EXPERIENCE_PAIR", "Arm identities or offline ablation designation changed.")
        require(values[arm + "-prompt.json"] == protocol.build_prompt(context),
                "INVALID_EXPERIENCE_PAIR", "Retain the native research-plan prompt for each frozen context.")
    return manifest


def prepare_pair(workspace, output):
    """Read one current plan context and publish a fresh, explicitly offline pair."""
    source = safe_path(Path(workspace).absolute()).resolve()
    output = safe_path(Path(output).absolute()).resolve()
    require(output != source and source not in output.parents and output not in source.parents,
            "INVALID_OUTPUT_PATH", "Output and source project must not contain one another.")
    require(not output.exists(), "OUTPUT_EXISTS", "Choose a fresh output directory; existing artifacts are retained.")
    project, host = ResearchProject(source), HostModelSelection(source)
    before, host_before = project.status(), host.status()
    current = protocol.build_context(project)
    selection = current["selection_context"]
    require(all(selection[key] == before[field] for key, field in
                (("project_id", "id"), ("state_version", "state_version"), ("snapshot_ref", "snapshot_ref"))),
            "STALE_STATE", "Plan context must bind the captured current project snapshot.")
    control = _control_context(current)
    documents = {"control-context.json": control, "current-context.json": current,
                 "control-prompt.json": protocol.build_prompt(control), "current-prompt.json": protocol.build_prompt(current)}
    _unchanged(project, host, before, host_before)
    output.mkdir(parents=True, exist_ok=False)
    identities = {}
    for name, document in documents.items():
        raw = canonical(document).encode("utf-8")
        write_bytes_once(output / name, raw)
        identities[name] = {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}
    _unchanged(project, host, before, host_before)
    manifest = {"schema_version": "experience-pair-v1", "project_id": before["id"],
        "state_version": before["state_version"], "snapshot_ref": before["snapshot_ref"],
        "case_ids": [item["case_id"] for item in selection["experience"]["cases"]],
        "scientific_validation": False, "host_status": host_before,
        "boundary": "Offline comparison only. The control is an explicit offline_ablation and must never be sent "
                    "to the live controller. Preparation calls no model, tool or fit and changes neither Host nor project. "
                    "This pair does not establish scientific validity, model adoption or research benefit.",
        "automatic_retry": False, "arms": {}, "files": identities}
    for arm, context in (("control", control), ("current", current)):
        manifest["arms"][arm] = {"mode": "offline_ablation" if arm == "control" else "frozen_current",
            "context_file": arm + "-context.json", "prompt_file": arm + "-prompt.json",
            "context_sha256": context["selection_context"]["context_sha256"]}
    write_bytes_once(output / "manifest.json", canonical(manifest).encode("utf-8"))
    verify_pair(output)
    _unchanged(project, host, before, host_before)
    return manifest


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", required=True, help="Existing research project; read only.")
    parser.add_argument("--output", required=True, help="Fresh directory outside the project for the offline pair.")
    args = parser.parse_args()
    try:
        manifest = prepare_pair(args.workspace, args.output)
        receipt = {"ok": True, "output": str(Path(args.output).absolute().resolve()),
                   **{key: manifest[key] for key in ("schema_version", "project_id", "state_version", "snapshot_ref", "case_ids")},
                   "scientific_validation": False}
        print(json.dumps(receipt, ensure_ascii=False, allow_nan=False))
        return 0
    except (ResearchError, ValueError, OSError) as error:
        print(json.dumps({"ok": False, "code": getattr(error, "code", "INVALID_EXPERIENCE_PAIR"),
                          "message": str(error), "automatic_retry": False}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
