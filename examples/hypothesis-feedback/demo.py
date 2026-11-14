#!/usr/bin/env python3
"""Independent synthetic relevance example: fixed prediction and saved-audit branch.

This runs native local retrieval tools, not a model or a scientific study. All
request bodies are durable before dispatch. A pending/unknown operation stops
without recovery or a replacement request.
"""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import zipfile

from autoresearch import hypothesis_feedback, relevance_retrieval_adapter as adapter
from autoresearch.contracts import ResearchError, canonical
from autoresearch.project_controller import ProjectController, code_identity as controller_identity
from autoresearch.project_report import export_report
from autoresearch.research_project import ResearchProject, code_identity as project_identity, safe_path

PREDICTION_ID = "demo-prediction"
PRIMARY_ID = "demo-primary"
BRANCH_ID = "demo-branch"
SPLITS = {"dev": ["qd"], "validation": ["qv"], "test": ["qt"]}


def fail(message):
    raise RuntimeError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def write_new(path, raw):
    with path.open("xb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())


def json_bytes(value):
    return canonical(value).encode("utf-8")


def write_json(path, value):
    write_new(path, json_bytes(value))


def read_json(path):
    raw = path.read_bytes()
    value = json.loads(raw)
    if json_bytes(value) != raw:
        fail("A saved JSON document is missing, malformed, or no longer canonical: " + str(path))
    return value


def rows(values):
    return ("\n".join(canonical(value) for value in values) + "\n").encode()


def assets():
    docs = [{"_id": key, "title": value, "text": value, "metadata": {}}
            for key, value in (("a", "cat dog"), ("b", "dog"), ("c", "fish"))]
    queries = [{"_id": key, "text": value, "metadata": {}}
               for key, value in (("qd", "cat"), ("qv", "unseen token"), ("qt", "fish"))]
    return {"corpus.jsonl": rows(docs), "queries.jsonl": rows(queries),
            "qrels-train.tsv": b"query-id\tcorpus-id\tscore\nqd\ta\t2\nqv\tb\t1\n",
            "qrels-test.tsv": b"query-id\tcorpus-id\tscore\nqt\tc\t1\n",
            "license.md": b"Original synthetic example created locally for this engineering demonstration.\n"}


def archive_bytes(files):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_STORED) as archive:
        for name, content in sorted(files.items()):
            info = zipfile.ZipInfo(name, date_time=(2020, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_STORED
            archive.writestr(info, content)
    return buffer.getvalue()


def build_inputs(folder):
    folder.mkdir()
    files = assets()
    archive = archive_bytes(files)
    receipt = {"description": "Local synthetic files created by this example; no external archive or attribution claim.",
               "archive_sha256": sha(archive), "files": {name: sha(raw) for name, raw in sorted(files.items())}}
    receipt_raw = json_bytes(receipt)
    selection = {"description": "Declared local engineering splits", "source_receipt_sha256": sha(receipt_raw), "query_splits": SPLITS}
    selection_raw = json_bytes(selection)
    spec = {"schema_version": "relevance-retrieval-spec-v1", "dataset_label": "Local synthetic engineering example",
            "source_url": "https://example.invalid/local-synthetic-not-external", "attribution": "Generated locally by this example",
            "license_notes": {"corpus": "Local synthetic example", "queries_and_qrels": "Local synthetic example"},
            "source_provenance": {"archive_sha256": sha(archive), "source_receipt_sha256": sha(receipt_raw),
                                  "selection_sha256": sha(selection_raw), "qrels_semantics": adapter.SEMANTICS},
            "files": adapter.FILES, "query_splits": SPLITS, "comparison": adapter.COMPARISON, "limits": adapter.LIMITS}
    for name, raw in files.items():
        write_new(folder / name, raw)
    write_new(folder / "synthetic-source.zip", archive)
    write_new(folder / "source-receipt.json", receipt_raw)
    write_new(folder / "selection.json", selection_raw)
    write_json(folder / "spec.json", spec)
    packet = adapter.capture_source(folder)
    write_json(folder / "packet.json", packet)
    return packet


def verify_inputs(folder):
    files = assets()
    expected_names = set(files) | {"synthetic-source.zip", "source-receipt.json", "selection.json", "spec.json", "packet.json"}
    if {p.name for p in folder.iterdir()} != expected_names:
        fail("Synthetic source inventory changed.")
    if any((folder / name).read_bytes() != raw for name, raw in files.items()):
        fail("Synthetic source bytes changed.")
    archive = (folder / "synthetic-source.zip").read_bytes()
    if archive != archive_bytes(files):
        fail("Synthetic archive changed.")
    with zipfile.ZipFile(io.BytesIO(archive)) as zipped:
        if sorted(zipped.namelist()) != sorted(files) or any(zipped.read(name) != raw for name, raw in files.items()):
            fail("Archive and original local files disagree.")
    receipt = read_json(folder / "source-receipt.json")
    selection = read_json(folder / "selection.json")
    spec = read_json(folder / "spec.json")
    expected_hashes = {name: sha(raw) for name, raw in sorted(files.items())}
    if (receipt.get("archive_sha256") != sha(archive) or receipt.get("files") != expected_hashes
            or selection.get("source_receipt_sha256") != sha(json_bytes(receipt)) or selection.get("query_splits") != SPLITS
            or spec["source_provenance"] != {"archive_sha256": sha(archive), "source_receipt_sha256": sha(json_bytes(receipt)),
                                             "selection_sha256": sha(json_bytes(selection)), "qrels_semantics": adapter.SEMANTICS}):
        fail("Local source provenance identities changed.")
    packet = adapter.capture_source(folder)
    if read_json(folder / "packet.json") != packet:
        fail("Captured source packet changed.")
    return packet


def find_parent(state, request_id):
    found = [record for record in state.get("controller_requests", []) if record["request_id"] == request_id]
    if len(found) > 1:
        fail("Controller request ID is not unique.")
    return found[0] if found else None


def check_pending(state):
    pending = [a for a in state["actions"] + state["evidence_actions"] if a["status"] in ("pending", "running", "unknown")]
    pending += [p for p in state.get("controller_requests", []) if p["status"] in ("prepared", "running", "unknown")]
    if pending:
        fail("Original request is pending or unknown. Stop; do not redispatch or use a new ID.")


def initialize(root):
    if root.exists():
        if not root.is_dir() or any(root.iterdir()):
            fail("First run requires a nonexistent or empty workspace; existing work is never overwritten.")
    else:
        root.mkdir(parents=True, exist_ok=False)
    (root / "requests").mkdir()
    packet = build_inputs(root / "inputs")
    project = ResearchProject(root / "project")
    project.create(source=root / "inputs" / "packet.json", goal="Synthetic engineering demonstration; not scientific evidence",
                   budget_ref="independent-synthetic-demo", max_tool_calls=2, method_id=adapter.TOOL_ID)
    project.save_plan(request_id="demo-plan", expected_state_version=project.status()["state_version"],
                      plan={"question": "What does the synthetic validation comparison return?", "basis": "Locally generated inputs only",
                            "steps": "Fixed pair; if validation delta is not greater than zero, inspect the saved audit; otherwise wait.",
                            "expected_feedback": "Saved validation candidate-minus-baseline Recall@20 and explicit unknown reasons."},
                      reason="Bounded engineering demonstration")
    state = project.status()
    meta = {"schema_version": "synthetic-hypothesis-demo-v1", "project_id": state["id"], "run_id": state["run_id"],
            "source_sha256": state["registration"]["source_sha256"], "source_snapshot_sha256": packet["snapshot_sha256"],
            "project_code_identity": project_identity(), "controller_code_identity": controller_identity(),
            "demo_sha256": sha(Path(__file__).read_bytes())}
    write_json(root / "identity.json", meta)
    context = ProjectController(project.root).selection_context()
    candidates = [c for c in context["candidates"] if c["method_id"] == adapter.TOOL_ID]
    if len(candidates) != 1 or context["blockers"]:
        fail("The fixed relevance primary candidate is not uniquely available.")
    hypothesis = {"candidate_id": candidates[0]["id"], "controller_request_id": PRIMARY_ID, "metric": "recall@20",
                  "operator": "gt", "threshold": 0,
                  "branches": {"condition_met": {"kind": "wait"},
                               "condition_not_met": {"kind": "method", "method_id": adapter.AUDIT_TOOL_ID}}}
    body = {"request_id": PREDICTION_ID, "expected_state_version": context["state_version"], "hypothesis": hypothesis}
    write_json(root / "requests" / "registration.json", body)
    project.register_hypothesis(**body)
    return project


def verify_project(root):
    packet = verify_inputs(root / "inputs")
    meta = read_json(root / "identity.json")
    project = ResearchProject(root / "project")
    state = project.status()
    if (meta["schema_version"] != "synthetic-hypothesis-demo-v1" or meta["project_id"] != state["id"]
            or meta["run_id"] != state["run_id"] or meta["source_sha256"] != state["registration"]["source_sha256"]
            or meta["source_sha256"] != sha((root / "inputs" / "packet.json").read_bytes())
            or meta["source_snapshot_sha256"] != state["source_snapshot_sha256"]
            or meta["source_snapshot_sha256"] != packet["snapshot_sha256"]
            or meta["project_code_identity"] != state["code_identity"] or meta["project_code_identity"] != project_identity()
            or meta["controller_code_identity"] != controller_identity() or meta["demo_sha256"] != sha(Path(__file__).read_bytes())):
        fail("Project/source/code identity changed; use the original code and workspace, never recreate this project.")
    project._source(state)
    budget = state["budget"]
    if (state["registration"]["method_id"] != adapter.TOOL_ID
            or state["registration"]["max_tool_calls"] != 2 or budget["local_tool_call_limit"] != 2
            or budget["model_requests_allowed"] != 0 or budget["new_model_requests"] != 0
            or budget["model_requests_reserved"] != 0 or budget["fit_limit"] != 0
            or budget["fit_attempts_used"] != 0 or budget["new_fits"] != 0
            or state["evidence_actions"] or len(state["actions"]) > 2
            or any(action["command"] not in (adapter.TOOL_ID, adapter.AUDIT_TOOL_ID) for action in state["actions"])):
        fail("The original two-tool, zero-model, zero-fit demonstration budget or action scope changed.")
    body = read_json(root / "requests" / "registration.json")
    registrations = [r for r in state.get("hypothesis_registrations", []) if r["request_id"] == PREDICTION_ID]
    if not registrations:
        check_pending(state)
        if (body.get("request_id") != PREDICTION_ID
                or body.get("expected_state_version") != state["state_version"]
                or body.get("hypothesis", {}).get("controller_request_id") != PRIMARY_ID):
            fail("Saved registration body is missing its original state or request identity.")
        project.register_hypothesis(**body)
        state = project.status()
        registrations = [r for r in state.get("hypothesis_registrations", []) if r["request_id"] == PREDICTION_ID]
    if len(registrations) != 1 or registrations[0]["request"] != body:
        fail("Original prediction request or registration is unavailable or changed.")
    hypothesis_feedback._check_record(registrations[0])
    return project, registrations[0]


def primary_body(project, registration):
    context = ProjectController(project.root).selection_context()
    candidate = registration["candidate"]
    if (candidate not in context["candidates"] or context["blockers"]
            or context["state_version"] != registration["state_version_before"] + 1):
        fail("Original fixed candidate is unavailable or blocked; no replacement will be dispatched.")
    proposal = {"schema_version": "project-selection-proposal-v1", "context_sha256": context["context_sha256"],
                "provider": {"kind": "operator_assistant", "label": "synthetic engineering demonstration"},
                "choice": {"kind": "execute", "candidate_id": candidate["id"]},
                "rationale": "Run the one fixed preregistered synthetic pair.", "evidence_citation_ids": []}
    return {"request_id": PRIMARY_ID, "proposal": proposal, "expected_state_version": context["state_version"]}


def check_primary_binding(project, body, registration, parent):
    if (set(body) != {"request_id", "proposal", "expected_state_version"} or body["request_id"] != PRIMARY_ID
            or body["proposal"]["choice"] != {"kind": "execute", "candidate_id": registration["candidate"]["id"]}):
        fail("Saved primary request body changed.")
    if parent is not None:
        expected = {"project_id": project.status()["id"], "command": "controller.advance_selection", "need": "next_check",
                    "expected_state_version": body["expected_state_version"], "proposal": body["proposal"]}
        if parent["request"] != expected:
            fail("Saved primary body differs from the original controller request.")


def verify_report(root, project):
    report_dir = root / "report"
    if not report_dir.exists():
        return export_report(workspace=project.root, output=report_dir)
    manifest = read_json(report_dir / "manifest.json")
    if (manifest["project_id"] != project.status()["id"]
            or manifest["project_snapshot_ref"] != project.status()["snapshot_ref"]
            or set(manifest["files"]) != {"input.json", "report.json", "report.md", "report.pdf"}):
        fail("Existing report no longer matches the project; it was not overwritten.")
    for name, info in manifest["files"].items():
        raw = (report_dir / name).read_bytes()
        if info["sha256"] != sha(raw) or info["bytes"] != len(raw):
            fail("Existing report file changed: " + name)
    return manifest


def run(root, resume, stop_after_registration):
    if not resume:
        initialize(root)
    project, registration = verify_project(root)
    start = project.status()
    check_pending(start)
    controller = ProjectController(project.root)
    primary_path = root / "requests" / "primary.json"
    parent = find_parent(start, PRIMARY_ID)
    if not primary_path.exists():
        if parent is not None:
            fail("Original primary request body is missing; do not dispatch or reconstruct it.")
        write_json(primary_path, primary_body(project, registration))
    primary = read_json(primary_path)
    check_primary_binding(project, primary, registration, parent)
    if parent is None and primary != primary_body(project, registration):
        fail("Saved primary body is stale or differs from its original selection context.")
    if stop_after_registration:
        if parent is not None:
            fail("The primary request has already started; --stop-after-registration applies only before execution.")
        print(canonical({"phase": "registered", "project_id": start["id"], "prediction": registration["condition"],
                         "next_request_id": PRIMARY_ID, "actions_added_this_run": 0, "budget": start["budget"],
                         "notice": "Synthetic engineering data; no scientific result. Existing adapter computes test; not blind."}))
        return
    if parent is not None and parent["status"] != "completed":
        fail("Original primary is not completed; stop without redispatch.")
    first = controller.advance_selection(**primary)
    if first["status"] != "completed":
        fail("Original primary did not complete; stop without a replacement request.")
    state = project.status()
    check_pending(state)
    result = hypothesis_feedback.feedback_context(project, state)["items"][0]
    if result["outcome"] == "unknown":
        fail("Prediction feedback is unknown: " + result["unknown_reason"] + "; stop without a branch dispatch.")
    branch_path = root / "requests" / "branch.json"
    branch_parent = find_parent(state, BRANCH_ID)
    if not branch_path.exists():
        if branch_parent is not None:
            fail("Original branch request body is missing; no replacement will be dispatched.")
        write_json(branch_path, {"request_id": BRANCH_ID, "registration_request_id": PREDICTION_ID,
                                 "expected_state_version": state["state_version"]})
    branch = read_json(branch_path)
    if (set(branch) != {"request_id", "registration_request_id", "expected_state_version"}
            or branch["request_id"] != BRANCH_ID or branch["registration_request_id"] != PREDICTION_ID):
        fail("Saved branch request body changed.")
    if branch_parent is not None:
        if branch_parent["status"] not in ("completed", "waiting"):
            fail("Original branch did not complete; stop without redispatch.")
        if branch_parent["request"]["expected_state_version"] != branch["expected_state_version"]:
            fail("Saved branch body differs from its original controller request.")
    branched = controller.advance_feedback(**branch)
    if branched["status"] not in ("completed", "waiting"):
        fail("Original branch did not reach a completed or waiting state.")
    final = project.status()
    check_pending(final)
    result = hypothesis_feedback.feedback_context(project, final)["items"][0]
    manifest = verify_report(root, project)
    summary = {"phase": "finished", "project_id": final["id"], "prediction": result["condition"],
               "outcome": result["outcome"], "validation_candidate_minus_baseline": result["value"],
               "unknown_reason": result["unknown_reason"], "branch_status": branched["status"],
               "actions": [{key: action.get(key) for key in ("id", "request_id", "command", "status", "result_sha256")}
                           for action in final["actions"]],
               "actions_added_this_run": len(final["actions"]) - len(start["actions"]), "budget": final["budget"],
               "report": str(root / "report"), "report_snapshot_ref": manifest["project_snapshot_ref"],
               "notice": "Synthetic engineering data; no scientific result. Existing adapter computes test; not blind."}
    print(canonical(summary))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", required=True, help="Absolute dedicated local workspace directory")
    parser.add_argument("--resume", action="store_true", help="Resume only the original project and saved request IDs")
    parser.add_argument("--stop-after-registration", action="store_true", help="Persist prediction and primary request, then stop")
    args = parser.parse_args()
    root = Path(args.workspace)
    if not root.is_absolute() or root == Path(root.anchor):
        parser.error("--workspace must be an absolute dedicated directory, not a filesystem root")
    try:
        safe_path(root)
        run(root, args.resume, args.stop_after_registration)
    except (ResearchError, RuntimeError, OSError, KeyError, ValueError, TypeError, zipfile.BadZipFile) as exc:
        print("Demo stopped: " + str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
