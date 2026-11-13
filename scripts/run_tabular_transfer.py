"""Staged trusted host glue for frozen tabular-transfer cases; not a controller.

Subclass only the dataset-specific Concrete host operations. All numerical and
source-read execution stays inside the existing native controller/allowlist.
Use preflight to freeze/check inputs without creating a manager or fitting.
"""
from __future__ import annotations

import argparse
import base64
import csv
from datetime import datetime, timezone
import fcntl
import importlib.metadata
import io
import json
import math
from pathlib import Path
import shutil
import sqlite3
import subprocess

from run_concrete_reproduction import Case as ParentCase, ROOT, canonical, code_identity, digest, once
from verify_tabular_transfer import Audit, audit_mapping, validate_config

AUTH = ROOT / "docs/execution/local-continuation.json"
PROTOCOL = ROOT / "docs/execution/g3-local/evaluation-protocol.md"
ASSETS = ["scripts/run_tabular_transfer.py", "scripts/run_concrete_reproduction.py",
          "scripts/verify_tabular_transfer.py", "docs/execution/g3-local/evaluation-protocol.md",
          "docs/execution/local-continuation.json", "src/autoresearch/project_controller.py"]


def safe_existing(path):
    path = Path(path).absolute()
    if any(p.is_symlink() for p in [path, *path.parents]):
        raise ValueError("Inputs must not redirect through symlinks")
    return path


def portfolio_fit_attempts(directory):
    total = 0
    for db in directory.glob("*/manager/projects/*/project.sqlite"):
        con = sqlite3.connect(db.resolve().as_uri()+"?mode=ro", uri=True)
        try:
            con.execute("PRAGMA query_only=ON")
            total += sum(len(json.loads(row[0]).get("fit_events", [])) for row in con.execute("SELECT record FROM actions"))
        finally:
            con.close()
    return total


class Case(ParentCase):
    def __init__(self, root, data, config, experience):
        # Deliberately do not call the Concrete-specific parent constructor.
        self.root = safe_existing(root)
        self.data, self.config_path, self.experience_path = map(safe_existing, [data, config, experience])
        self.inputs = self.data / "inputs"
        self.config = validate_config(json.loads(self.config_path.read_text()))
        self.spec = json.loads((self.inputs / "spec.json").read_text())
        self.dataset = self.config["dataset_id"]
        auth = json.loads(AUTH.read_text())
        if auth["status"] != "accepted" or auth["schema_version"] != "trusted-local-continuation-v2":
            raise ValueError("Trusted local continuation has not been accepted")
        expected = auth["g3"]["per_target"][self.dataset]
        limit = self.config["budget"]
        if (limit != {"local_tool_calls": expected["tool_calls"], "fit_attempts": expected["estimator_attempts"],
                      "source_reads": expected["source_reads"], "model_calls": 0}
                or auth["g3"]["product_model_sends"] != 0 or auth["g3"]["external_api_sends"] != 0
                or auth["g3"]["research_concurrency"] != 1):
            raise ValueError("Config differs from the accepted per-target envelope")
        if portfolio_fit_attempts(self.root.parent) > auth["g3"]["portfolio_estimator_ceiling"]:
            raise ValueError("Existing portfolio fit ceiling exceeded; no reset or new execution")
        if shutil.disk_usage(ROOT).free < 5 * 1024**3:
            raise ValueError("Less than 5 GiB host disk headroom")
        if digest(self.experience_path) != self.config["experience"]["bundle_sha256"]:
            raise ValueError("The frozen source experience bundle changed")
        manifest = json.loads((self.data / "source-manifest.json").read_text())
        data_hashes = {"source-manifest.json": digest(self.data / "source-manifest.json")}
        for item in manifest["files"]:
            path = safe_existing(self.data / item["path"])
            if not path.resolve().is_relative_to(self.data.resolve()):
                raise ValueError("Source manifest path escaped its data directory")
            if digest(path) != item["sha256"] or path.stat().st_size != item["bytes"]:
                raise ValueError("Source manifest bytes changed: " + item["path"])
            data_hashes[item["path"]] = item["sha256"]
        # Check original-to-derived tokens/grouping before creating any project.
        def asset(path):
            raw = path.read_bytes()
            return {"file_name": path.name, "sha256": digest(path), "bytes": len(raw), "bytes_base64": base64.b64encode(raw).decode()}
        packet = {"spec_source": asset(self.inputs / "spec.json"), "source": asset(self.inputs / self.spec["file"]), "spec": self.spec}
        import hashlib
        packet["snapshot_sha256"] = hashlib.sha256(canonical(packet).encode()).hexdigest()
        check = Audit(); check.config = self.config
        audit_mapping(check, packet, Path(self.config["original_csv"]))
        if not all(c["passed"] for c in check.checks):
            raise ValueError("Preflight data mapping failed: " + canonical([c for c in check.checks if not c["passed"]]))
        self.manager = None
        freeze = {"schema_version": "trusted-tabular-transfer-freeze-v1", "dataset_id": self.dataset,
                  "case_root": str(self.root), "data_path": str(self.data), "source_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
                  "controller_code_identity": code_identity(), "asset_sha256": {p: digest(ROOT / p) for p in ASSETS},
                  "data_sha256": data_hashes, "config_path": str(self.config_path), "config_sha256": digest(self.config_path),
                  "experience_path": str(self.experience_path), "experience_sha256": digest(self.experience_path),
                  "authorization_sha256": digest(AUTH), "protocol_sha256": digest(PROTOCOL),
                  "packages": {n: importlib.metadata.version(n) for n in ["numpy", "scipy", "scikit-learn", "h5py", "reportlab"]},
                  "limits": limit, "portfolio_estimator_ceiling": auth["g3"]["portfolio_estimator_ceiling"],
                  "isolation": "trusted local process; original Docker controls remain unverified/failed",
                  "origin_note": "Imported Concrete experience is historical analogy, never target evidence."}
        self.root.mkdir(parents=True, exist_ok=True)
        once(self.root / "freeze.json", freeze)

    def baseline(self):
        cfg, spec = self.config, self.spec
        self.op("create", lambda: {"request_id": "transfer-create", "goal": "Evaluate the frozen " + self.dataset + " grouped Ridge baseline and conditionally one preregistered mapping; retain adverse local outcomes and separate historical source experience from current evidence.", "budget_ref": "approved-local-g3-" + self.dataset, "max_tool_calls": cfg["budget"]["local_tool_calls"], "input": {"file_name": spec["file"], "csv_base64": base64.b64encode((self.inputs / spec["file"]).read_bytes()).decode(), "spec_base64": base64.b64encode((self.inputs / "spec.json").read_bytes()).decode()}}, self.manager.create)
        self.op("source-limit", lambda: {"request_id": "transfer-source-limit", "expected_limit": 8, "new_limit": cfg["budget"]["source_reads"], "expected_state_version": self.state()["state_version"], "reason": "Accepted per-target cumulative source-read envelope; no external network/model grant."}, lambda body: self.project().limit_evidence_budget(**body))
        self.plan(1, {"question": "What fixed grouped Ridge predictions and adverse local outcomes occur for " + cfg["target_column"] + " in its declared unit " + cfg["target_unit"] + "?", "basis": "Published intact data and original field/unit sources; declared groups are mechanical equality signatures, not verified independent property, batch or laboratory identity. No historical source result is a target observation.", "steps": "Audit full data and source excerpts, execute one fixed five-fold grouped raw-feature StandardScaler/Ridge alpha1 baseline, then inspect saved group diagnostics. A later plan must cite these actual results before any candidate or explicit rejection. No feature/split/parameter search or target clipping.", "expected_feedback": "Full original rows, declared groups, folds, saved parameters, training-fold mean reference, negative predictions and local failures. Revise or wait precisely if semantic/identity/coverage assumptions fail."}, "Freeze target baseline before fitting; source experience will be imported only at the explicit later transfer decision.")
        self.select("quality", "data.tabular-quality-audit", rationale="Audit complete original numeric tokens, missingness and declared grouping before fitting.")
        self.register_sources()
        self.select("source-read", "research.source-selection", rationale="Read the registered official field/unit/attribution/license excerpts; no inference of independent sampling.")
        design = {"schema_version": "research-design-resource-v1", "id": self.dataset + "-cloud-method-transfer", "version": 1, "title": self.dataset + " fixed raw grouped baseline", "question": "How does the fixed raw-feature grouped Ridge predict the declared target, and what adverse results constrain the next action?", "claim": "Compare same-evaluation saved MAE with the training-fold target-mean reference; preserve nonbenefit and local failure.", "alternatives": ["Unrecorded sampling and grouping meaning may limit validity.", "Aggregate error may conceal local failures or impossible predictions."], "checks": ["group_cv"], "sources": [spec["source_url"]], "parent_version": None, "change_reason": "Preregistered raw baseline with intact original rows, fixed target/input/group mapping and no result-dependent search."}
        self.bind(1, design, {"feature_columns": cfg["feature_columns"], "split_group_columns": cfg["split_group_columns"], "fit_limit": cfg["budget"]["fit_attempts"]})
        accepted = any(r["request_id"] == "concrete-baseline" for r in self.state().get("controller_requests", []))
        if not accepted and portfolio_fit_attempts(self.root.parent) + 10 > 40:
            raise ValueError("Portfolio cannot cover this frozen five-fold baseline")
        self.select("baseline", "data.ridge-group-validation", rationale="Execute only the current native eligible baseline under the frozen source, grouped split and cumulative budget.")
        baseline = next(a for a in self.state()["actions"] if a["command"] == "data.ridge-group-validation" and a["design_binding"]["resource"]["version"] == 1)
        self.select("baseline-diagnostics", "data.saved-oof-group-diagnostics", action_id=baseline["id"], rationale="Inspect full saved group and prediction failures, without further fitting.")
        self.snapshot("baseline")

    def register_sources(self):
        bundle = self.root / "source-bundle"
        items = json.loads((self.data / "evidence-selections.json").read_text())
        sources, selections, seen = [], [], {}
        for number, item in enumerate(items, 1):
            relative = item["path"]
            original = safe_existing(self.data / relative)
            if not original.resolve().is_relative_to(self.data.resolve()) or digest(original) != item["source_sha256"]:
                raise ValueError("Frozen evidence source escaped its root or changed")
            if relative not in seen:
                sid = "source-" + str(len(seen)+1)
                seen[relative] = sid
                name = "source-" + str(len(seen)) + "-" + original.name
                target = bundle / "sources" / name
                target.parent.mkdir(parents=True, exist_ok=True)
                raw = original.read_bytes()
                if target.exists() and target.read_bytes() != raw:
                    raise ValueError("Original source bundle bytes changed")
                if not target.exists():
                    with target.open("xb") as stream: stream.write(raw)
                sources.append({"id": sid, "path": "sources/" + name, "sha256": item["source_sha256"], "url": self.spec["source_url"], "media_type": item["media_type"], "license_note": self.spec["license_note"] + " Captured Markdown is a derived representation, not original HTML; source extraction is not scientific approval."})
            selections.append({"id": "selection-"+str(number), "source_id": seen[relative], "locator": item["locator"], "claim": "Official original field/unit or attribution/license declaration; no independent sampling/causal confirmation."})
        once(bundle / "manifest.json", {"schema_version": "project-evidence-bundle-v1", "task_ref": self.project().evidence_task()["task_ref"], "contributor": {"role": "operator_assistant", "label": "Trusted local transfer task; original bytes retained"}, "sources": sources, "selections": selections, "remaining_questions": ["Derived equality groups do not verify independent property/specimen/batch identities."]})
        self.op("register-source", lambda: {"request_id": "transfer-register-source", "bundle": str(bundle), "expected_state_version": self.state()["state_version"]}, lambda body: self.project().register_evidence(**body))

    def candidate(self, path):
        plan = json.loads(path.read_text())
        once(self.root / "phase-inputs/candidate-plan.json", {"path": str(path.absolute()), "sha256": digest(path), "plan": plan})
        state = self.state()
        baseline = next(a for a in state["actions"] if a["command"] == "data.ridge-group-validation" and a["status"] == "completed" and a["design_binding"]["resource"]["version"] == 1)
        diagnostic = next(a for a in state["actions"] if a["command"] == "data.saved-oof-group-diagnostics" and a["status"] == "completed" and a["method_instance"]["parameters"].get("based_on_action_id") == baseline["id"])
        if any(a["status"] in ("running", "unknown", "pending") for a in state["actions"] + state["evidence_actions"]):
            raise ValueError("Reconcile the existing unknown execution before further decisions")
        self.op("import-experience", lambda: {"request_id": "transfer-import-experience", "project_id": self.state()["id"], "expected_state_version": self.state()["state_version"], "bundle_base64": base64.b64encode(self.experience_path.read_bytes()).decode(), "reason": "Active historical Concrete parent/child warning only; source age days and source MAE are not target evidence. Check target-specific semantics and adverse results before any candidate."}, self.manager.import_experience)
        cases = self.manager.experiences()["cases"]
        imported = [c for c in cases if c["bundle_sha256"] == digest(self.experience_path) and c["inclusion_status"] == "active"]
        if len(imported) != 1:
            raise ValueError("Original historical case is not currently active; do not silently restore retired inclusion")
        self.plan(2, plan, "Actual target baseline " + baseline["id"] + " and native diagnostics " + diagnostic["id"] + " determine this target revision; imported source remains a historical analogy.")
        transform = self.config["candidate_transform"]
        columns = self.config["feature_columns"]
        semantic = self.config["experience"]["transform_semantically_applicable"]
        unit = self.config["experience"]["target_age_unit"]
        flags = []
        if transform is None: flags.append("NO_TARGET_AGE_TRANSFORM_DECLARED")
        if not semantic: flags.append("SEMANTICALLY_NOT_APPLICABLE")
        if unit != "year": flags.append("TARGET_AGE_UNIT_NOT_YEAR")
        selected = next(iter(transform)) if transform else None
        if selected:
            with (self.inputs / self.spec["file"]).open(newline="", encoding="utf-8-sig") as stream:
                raw_rows = list(csv.DictReader(stream))
            try:
                values = [float(row[selected]) for row in raw_rows]
            except (ValueError, KeyError):
                values = []
            if selected not in columns or not values or not all(math.isfinite(v) and v >= 0 for v in values) or min(values) == max(values):
                flags.append("AGE_INPUT_NOT_FINITE_NONNEGATIVE_AND_VARYING")
        eligibility = {"schema_version": "target-transfer-eligibility-v1", "dataset_id": self.dataset, "applicable": not flags, "reason_codes": flags, "candidate_transform": transform, "target_age_unit": unit, "source_age_unit": self.config["experience"]["source_age_unit"], "baseline_action_id": baseline["id"], "diagnostic_action_id": diagnostic["id"], "case_bundle_sha256": digest(self.experience_path), "historical_case_retained_active": True, "scientific_validation": False, "native_method_association_is_not_semantic_approval": True}
        once(self.root / "transfer-eligibility.json", eligibility)
        if flags:
            if transform is not None or self.config["expected_fit_actions"] != 1:
                raise ValueError("Prespecified candidate eligibility failed; receipt retained, no fitting")
            self.snapshot("candidate")
            return
        design = dict(baseline["design_binding"]["resource"])
        design.update(version=2, parent_version=1, comparison_kind="fixed_input_basis", title=self.dataset+" one fixed age-years mapping candidate", question="Does the sole declared log1p house-age-in-years expression change same-fold saved error and local failures versus this target's own raw parent?", claim="A paired exploratory representation comparison, not transfer of Concrete's age-days effect, performance, coefficient or scientific law.", change_reason=plan["basis"][:2000], sources=[self.spec["source_url"], "Actual target parent "+baseline["id"]+" sha256:"+baseline["result_sha256"]+"; diagnostics "+diagnostic["id"]+" sha256:"+diagnostic["result_sha256"]])
        self.bind(2, design, {"feature_columns": columns, "split_group_columns": self.config["split_group_columns"], "fit_limit": self.config["budget"]["fit_attempts"], "input_transforms": transform})
        accepted = any(r["request_id"] == "concrete-candidate" for r in self.state().get("controller_requests", []))
        if not accepted and portfolio_fit_attempts(self.root.parent) + 10 > 40:
            raise ValueError("Portfolio cannot cover the sole preregistered candidate")
        self.select("candidate", "data.ridge-group-validation", rationale=plan["steps"][:4000])
        child = next(a for a in self.state()["actions"] if a["command"] == "data.ridge-group-validation" and a["design_binding"]["resource"]["version"] == 2)
        self.select("candidate-diagnostics", "data.saved-oof-group-diagnostics", action_id=child["id"], rationale="Inspect every saved candidate group and prediction failure without extra fitting.")
        self.snapshot("candidate")


    def finish(self, path):
        state = self.state()
        completed = [a for a in state["actions"] if a["command"] == "data.ridge-group-validation" and a["status"] == "completed"]
        eligibility = json.loads((self.root / "transfer-eligibility.json").read_text())
        if len(completed) != self.config["expected_fit_actions"]:
            raise ValueError("The target's declared baseline/paired stage is not complete; retain its actual stopping state")
        if self.config["candidate_transform"] is None:
            if eligibility["applicable"]:
                raise ValueError("The no-age target must preserve its semantic abstention")
            outcome = "The target has no applicable varying-age transform; retain the fixed baseline, explicit abstention and historical warning. No age feature or paired candidate was fabricated."
        else:
            if not eligibility["applicable"]:
                raise ValueError("The declared paired target did not qualify for its candidate")
            outcome = "The preregistered target-specific raw-parent/fixed-mapping comparison is complete; retain actual adverse results and do not attribute the outcome causally to memory."
        self.plan(3, json.loads(path.read_text()), outcome + " No further fitting or scientific promotion.")
        self.select("wait", rationale=outcome + " Stop at the accepted per-target envelope; independent sampling/domain evidence remains unresolved.")
        result = self.op("export", lambda: {"request_id": "transfer-report", "project_id": self.state()["id"], "expected_state_version": self.state()["state_version"]}, self.manager.export)
        once(self.root / "report-export.json", result)
        self.snapshot("finished")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=["preflight", "baseline", "candidate", "finish", "inspect"])
    for name in ["root", "data", "config", "experience"]: parser.add_argument("--"+name, type=Path, required=True)
    parser.add_argument("--plan", type=Path)
    args = parser.parse_args()
    if args.phase in ["candidate", "finish"] and not args.plan: parser.error("This phase requires a real target-feedback --plan JSON")
    case = Case(args.root, args.data, args.config, args.experience)
    if args.phase == "preflight":
        print(json.dumps({"status": "frozen_or_identity_verified", "dataset_id": case.dataset, "manager_created": False, "fits": 0, "freeze": str(case.root / "freeze.json")}))
        return
    with (case.root.parent / "research-execution.lock").open("a+b") as stream:
        fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            with case.lock():
                if args.phase == "baseline": case.baseline()
                elif args.phase == "candidate": case.candidate(args.plan)
                elif args.phase == "finish":
                    once(case.root / "phase-inputs/finish-plan.json", {"path": str(args.plan.absolute()), "sha256": digest(args.plan), "plan": json.loads(args.plan.read_text())})
                    case.finish(args.plan)
                else: case.snapshot("inspect")
        finally:
            fcntl.flock(stream, fcntl.LOCK_UN)


if __name__ == "__main__":
    main()
