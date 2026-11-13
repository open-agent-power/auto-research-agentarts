"""Host-only, staged Concrete reproduction through existing native interfaces.

This is fixed trusted glue, not a new controller, model runtime or sandbox.
Each native operation freezes original arguments before submission. Interrupted
or unknown operations are left to native same-ID recovery, never reset/retried
under a new identity. Numerical work remains inside the audited allowlist.
"""
from __future__ import annotations

import os
for _name in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ[_name] = "1"

import argparse
import base64
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import hashlib
import importlib.metadata
import json
from pathlib import Path
import resource
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from autoresearch.contracts import canonical
from autoresearch.local_workbench import LocalWorkbench
from autoresearch.project_controller import ProjectController
from autoresearch.research_project import ResearchProject, code_identity
from autoresearch.saved_oof_diagnostics import inspect_saved_oof

FEATURES = ["cement", "blast_furnace_slag", "fly_ash", "water", "superplasticizer", "coarse_aggregate", "fine_aggregate", "age"]
INPUT_HASHES = {"concrete.csv": "768a123975d7f56ddaef8f2965594614aa7a015b2719d545266e4965bd5b25aa", "spec.json": "6d0859af90ce37c5b02842702c585164da15d22b2d1663ccd56f87de0263ba70"}
AUTH = ROOT / "docs/execution/g1-local/authorization.json"
FROZEN_ASSETS = ["scripts/run_concrete_reproduction.py", "scripts/verify_concrete_reproduction.py", "src/autoresearch/project_controller.py", "docs/execution/g1-local/authorization.json", "docs/execution/g0/evaluation-protocol.md", "docs/execution/g0/initial-research-task-spec.md", "examples/research-designs/concrete-mixture-transfer.json", "examples/research-designs/concrete-mixture-transfer-v2.json"]


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def once(path, value):
    raw = (canonical(value) + "\n").encode()
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() != raw:
            raise ValueError(f"Immutable host record differs: {path}")
    else:
        with path.open("xb") as f:
            f.write(raw)
            f.flush()
            os.fsync(f.fileno())
    return value


class Case:
    def __init__(self, root, inputs):
        self.root, self.inputs = root.absolute(), inputs.absolute()
        if any(p.is_symlink() for p in [self.root, *self.root.parents]):
            raise ValueError("Case workspace must not redirect through symlinks")
        auth = json.loads(AUTH.read_text())
        if auth["status"] != "accepted" or auth["choice"] != "A":
            raise ValueError("Trusted-local scope has not been accepted")
        if shutil.disk_usage(ROOT).free < 5 * 1024**3:
            raise ValueError("Less than 5 GiB host disk headroom")
        for name, expected in INPUT_HASHES.items():
            if digest(inputs / name) != expected:
                raise ValueError(f"Frozen original input changed: {name}")
        self.root.mkdir(parents=True, exist_ok=True)
        self.manager = None
        frozen = self.root / "freeze.json"
        assets = {name: digest(ROOT / name) for name in FROZEN_ASSETS}
        if frozen.exists():
            record = json.loads(frozen.read_text())
            if record["controller_code_identity"] != code_identity() or record["input_sha256"] != INPUT_HASHES or record["asset_sha256"] != assets:
                raise ValueError("Frozen native/host/evaluator code, protocol, authorization or input identity changed")
        else:
            once(frozen, {"case_id": "P0-CONCRETE-CLOUD-001", "kind": "approved_trusted_local_reproduction", "created_at_utc": datetime.now(timezone.utc).isoformat(), "source_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(), "controller_code_identity": code_identity(), "asset_sha256": assets, "input_sha256": INPUT_HASHES, "authorization_sha256": digest(AUTH), "protocol_sha256": digest(ROOT / "docs/execution/g0/evaluation-protocol.md"), "task_spec_sha256": digest(ROOT / "docs/execution/g0/initial-research-task-spec.md"), "packages": {n: importlib.metadata.version(n) for n in ["numpy", "scipy", "scikit-learn", "h5py", "reportlab"]}, "limits": auth["limits"], "isolation": "trusted local process; original Docker isolation gate remains blocked"})

    @contextmanager
    def lock(self):
        with (self.root / "runner.lock").open("a+b") as stream:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
            try:
                self.manager = LocalWorkbench(self.root / "manager")
                yield
            finally:
                fcntl.flock(stream, fcntl.LOCK_UN)

    def op(self, name, make, call):
        path = self.root / "requests" / (name + ".json")
        body = json.loads(path.read_text()) if path.exists() else once(path, make())
        result = call(body)
        receipt = self.root / "receipts" / (name + ".json")
        if not receipt.exists():
            once(receipt, result)
        return result

    def project(self):
        paths = list((self.root / "manager/projects").glob("*/project.sqlite"))
        if len(paths) != 1:
            raise ValueError("Require exactly one native managed case, never reconstruct a missing mapping")
        return ResearchProject(paths[0].parent)

    def state(self):
        return self.project().status()

    def plan(self, number, plan, reason):
        return self.op(f"plan-{number}", lambda: {"request_id": f"concrete-plan-{number}", "project_id": self.state()["id"], "expected_state_version": self.state()["state_version"], "plan": plan, "reason": reason}, self.manager.save_plan)

    def select(self, name, method=None, action_id=None, rationale=""):
        def make():
            ctx = ProjectController(self.project().root).selection_context()
            if method is None:
                choice = {"kind": "wait"}
            else:
                matches = [c for c in ctx["candidates"] if c["method_id"] == method and (action_id is None or c["parameters"].get("based_on_action_id") == action_id)]
                if len(matches) != 1 or ctx["blockers"]:
                    raise ValueError(f"No unique eligible {method}: {ctx['blockers']}")
                choice = {"kind": "execute", "candidate_id": matches[0]["id"]}
            once(self.root / "contexts" / (name + ".json"), ctx)
            return {"request_id": "concrete-" + name, "project_id": ctx["project_id"], "expected_state_version": ctx["state_version"], "proposal": {"schema_version": "project-selection-proposal-v1", "context_sha256": ctx["context_sha256"], "provider": {"kind": "operator_assistant", "label": "Host developer Agent; no product model invocation"}, "choice": choice, "rationale": rationale, "evidence_citation_ids": []}}
        return self.op(name, make, self.manager.advance)

    def bind(self, number, resource_value, training):
        self.op(f"import-design-{number}", lambda: {"request_id": f"concrete-import-design-{number}", "resource": resource_value}, self.manager.import_design)
        return self.op(f"bind-design-{number}", lambda: {"request_id": f"concrete-bind-design-{number}", "project_id": self.state()["id"], "expected_state_version": self.state()["state_version"], "resource_id": resource_value["id"], "resource_version": number, "prediction_column": None, "reason": resource_value["change_reason"], "training": training}, self.manager.bind_design)

    def baseline(self):
        self.op("create", lambda: {"request_id": "concrete-create", "goal": "Reproduce held-out mixture-signature prediction on the complete official Concrete data; use actual saved feedback to revise research, retaining adverse local results and noncausal limits.", "budget_ref": "approved-local-P0-CONCRETE-CLOUD-001", "max_tool_calls": 6, "input": {"file_name": "concrete.csv", "csv_base64": base64.b64encode((self.inputs / "concrete.csv").read_bytes()).decode(), "spec_base64": base64.b64encode((self.inputs / "spec.json").read_bytes()).decode()}}, self.manager.create)
        self.op("source-limit", lambda: {"request_id": "concrete-source-limit", "expected_limit": 8, "new_limit": 1, "expected_state_version": self.state()["state_version"], "reason": "Accepted new-case cumulative allowance: one source extraction; no new network/model grant."}, lambda b: self.project().limit_evidence_budget(**b))
        self.plan(1, {"question": "What does fixed additive Ridge predict for entire held-out ingredient signatures, and which actual errors justify the next research step?", "basis": "Known-outcome reproduction, not novel discovery. All 1030 original observations and duplicate rows retained. Groups are exact seven-ingredient signatures, not verified batches; strength is MPa and age days.", "steps": "Check full data quality and original documentation; run one fixed five-fold grouped raw-eight-feature StandardScaler/Ridge alpha1 baseline; inspect saved group and age errors. Keep at most one fixed log1p-age comparison conditional on actual feedback. No tuning, clipping, causal claim or unseen-task claim.", "expected_feedback": "Preserve full OOF, folds, local failures, training-fold mean reference, parameter artifacts and budget. Stop precisely if source, coverage, identity or comparison assumptions fail; otherwise revise the plan using actual action IDs and observations."}, "Freeze before any study fit; 6 tools / 20 estimator attempts / 1 source extraction / 0 product model sends.")
        self.select("quality", "data.tabular-quality-audit", rationale="Check all original numeric tokens, missingness, duplicate and declared grouping before training.")
        self.register_sources()
        self.select("source-read", "research.source-selection", rationale="Read the registered official field/unit, attribution and license selections; extraction does not certify physical independence.")
        design = json.loads((ROOT / "examples/research-designs/concrete-mixture-transfer.json").read_text())
        design["id"] = "concrete-cloud-mixture-transfer"
        self.bind(1, design, {"feature_columns": FEATURES, "split_group_columns": ["mixture_signature"], "fit_limit": 20})
        self.select("baseline", "data.ridge-group-validation", rationale="Execute the frozen raw-eight-input grouped baseline with training-fold preprocessing and mean reference, preserving all rows.")
        baseline = next(a for a in self.state()["actions"] if a["command"] == "data.ridge-group-validation" and a["design_binding"]["resource"]["version"] == 1)
        self.select("baseline-diagnostics", "data.saved-oof-group-diagnostics", action_id=baseline["id"], rationale="Inspect complete saved group errors without any further fit; a global average may hide local failure.")
        derived = inspect_saved_oof(self.project().root, baseline["id"], columns=("age",), within_group_column="age")
        once(self.root / "baseline-age-diagnostics.json", derived)
        self.snapshot("baseline")

    def register_sources(self):
        bundle = self.root / "source-bundle"
        sources, selections = [], []
        items = [("readme", "Concrete_Readme.txt", "text/plain", "https://archive.ics.uci.edu/ml/machine-learning-databases/concrete/compressive/Concrete_Readme.txt", [("field-units", "30-58"), ("attribution", "90-94")]), ("license-page", "uci-concrete-page.md", "text/markdown", "https://archive.ics.uci.edu/dataset/165/concrete+compressive+strength", [("license", "141-156")])]
        for sid, name, media, url, ranges in items:
            target = bundle / "sources" / name
            target.parent.mkdir(parents=True, exist_ok=True)
            raw = (self.inputs.parent / name).read_bytes()
            if target.exists():
                if target.read_bytes() != raw:
                    raise ValueError("Source bundle bytes changed")
            else:
                target.write_bytes(raw)
            sources.append({"id": sid, "path": "sources/" + name, "sha256": digest(target), "url": url, "media_type": media, "license_note": "I-Cheng Yeh; UCI CC BY 4.0; preserve original readme copyright/citation. Page Markdown is a derived captured representation, not original HTTP HTML."})
            selections.extend({"id": key, "source_id": sid, "locator": {"kind": "text_lines", "value": span}, "claim": "Source declaration of original data fields/units, author or reuse license; no independent batch or causal validation."} for key, span in ranges)
        manifest = bundle / "manifest.json"
        if not manifest.exists():
            once(manifest, {"schema_version": "project-evidence-bundle-v1", "task_ref": self.project().evidence_task()["task_ref"], "contributor": {"role": "operator_assistant", "label": "Cloud local reproduction; original source bytes retained"}, "sources": sources, "selections": selections, "remaining_questions": ["No verified batch/specimen/laboratory identity; equal ingredients only define derived groups."]})
        self.op("register-source", lambda: {"request_id": "concrete-register-source", "bundle": str(bundle), "expected_state_version": self.state()["state_version"]}, lambda b: self.project().register_evidence(**b))

    def candidate(self, path):
        plan = json.loads(path.read_text())
        state = self.state()
        baseline = next(a for a in state["actions"] if a["command"] == "data.ridge-group-validation" and a["status"] == "completed" and a["design_binding"]["resource"]["version"] == 1)
        diagnostic = next(a for a in state["actions"] if a["command"] == "data.saved-oof-group-diagnostics" and a["status"] == "completed" and a["method_instance"]["parameters"].get("based_on_action_id") == baseline["id"])
        saved = inspect_saved_oof(self.project().root, baseline["id"], columns=("age",), within_group_column="age")
        if canonical(saved) != canonical(json.loads((self.root / "baseline-age-diagnostics.json").read_text())):
            raise ValueError("Original complete baseline diagnostics changed before plan revision")
        if any(a["status"] in ("running", "unknown", "pending") for a in state["actions"] + state["evidence_actions"]):
            raise ValueError("Original pending/unknown execution must be reconciled first")
        self.plan(2, plan, "Host Agent revision from this case's completed baseline and saved diagnostics; no historical result imported as new evidence.")
        design = json.loads((ROOT / "examples/research-designs/concrete-mixture-transfer-v2.json").read_text())
        design["id"] = "concrete-cloud-mixture-transfer"
        design["sources"][2] = f"Current cloud baseline {baseline['id']} sha256:{baseline['result_sha256']}; saved diagnostics {diagnostic['id']} sha256:{diagnostic['result_sha256']}. Full current saved age analysis is baseline-age-diagnostics.json; no prior-study results substituted."
        design["change_reason"] = plan["basis"][:2000]
        self.bind(2, design, {"feature_columns": FEATURES, "split_group_columns": ["mixture_signature"], "fit_limit": 20, "input_transforms": {"age": "log1p"}})
        self.select("candidate", "data.ridge-group-validation", rationale=plan["steps"][:4000])
        child = next(a for a in self.state()["actions"] if a["command"] == "data.ridge-group-validation" and a["design_binding"]["resource"]["version"] == 2)
        self.select("candidate-diagnostics", "data.saved-oof-group-diagnostics", action_id=child["id"], rationale="Audit all saved child group failures and ranges without spending further fits or claiming aggregate gain implies universal benefit.")
        once(self.root / "candidate-age-diagnostics.json", inspect_saved_oof(self.project().root, child["id"], columns=("age",), within_group_column="age"))
        self.snapshot("candidate")

    def finish(self, path):
        self.plan(3, json.loads(path.read_text()), "Bounded reproduction conclusion and precise next evidence needs; no further fits or scientific promotion.")
        self.select("wait", rationale="Stop the bounded known-outcome case after actual feedback and fixed comparison; independent external data and domain review remain necessary, no additional fitting authorized.")
        result = self.op("export", lambda: {"request_id": "concrete-report", "project_id": self.state()["id"], "expected_state_version": self.state()["state_version"]}, self.manager.export)
        once(self.root / "report-export.json", result)
        self.snapshot("finished")

    def snapshot(self, phase):
        state = self.state()
        b = state["budget"]
        if b["local_tool_calls_used"] > 6 or b["fit_attempts_used"] > 20 or b["evidence_reads_used"] > 1 or b.get("new_model_requests", 0):
            raise ValueError("Accepted cumulative envelope exceeded")
        snapshot = self.root / "snapshots" / (phase + ".json")
        if not snapshot.exists():
            once(snapshot, state)
        summary = {"phase": phase, "project_workspace": str(self.project().root), "project_id": state["id"], "state_version": state["state_version"], "research_status": state["research_status"], "budget": b, "actions": [{"id": a["id"], "command": a["command"], "status": a["status"], "result_sha256": a.get("result_sha256"), "observations": a.get("observations", [])} for a in state["actions"]], "max_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss}
        once(self.root / "summaries" / (phase + ".json"), summary) if not (self.root / "summaries" / (phase + ".json")).exists() else None
        print(json.dumps({k: v for k, v in summary.items() if k != "actions"}, ensure_ascii=False, indent=2))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("phase", choices=["baseline", "candidate", "finish", "inspect"])
    p.add_argument("--root", required=True)
    p.add_argument("--inputs", required=True)
    p.add_argument("--plan")
    args = p.parse_args()
    if args.phase in ["candidate", "finish"] and not args.plan:
        p.error("This phase requires a real feedback-based --plan JSON")
    case = Case(Path(args.root), Path(args.inputs))
    with case.lock():
        if args.phase == "baseline":
            case.baseline()
        elif args.phase == "candidate":
            case.candidate(Path(args.plan))
        elif args.phase == "finish":
            case.finish(Path(args.plan))
        else:
            case.snapshot("inspect")


if __name__ == "__main__":
    main()
