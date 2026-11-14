#!/usr/bin/env python3
"""One fixed S054 train-split study; preparation and execution are separate."""
import argparse
import base64
import copy
from datetime import datetime, timezone
import hashlib
import importlib.util
import io
import json
import math
import os
from pathlib import Path
import re
import signal
import sqlite3
import subprocess
import sys
import tempfile
import time
import unicodedata
import zipfile

if __name__ == "__main__" and any(x == "autoresearch" or x.startswith("autoresearch.") for x in sys.modules):
    raise RuntimeError("Project code was loaded before the private bytecode guard.")
_PRIVATE_CACHE = tempfile.TemporaryDirectory(prefix="s054-python-cache-")
sys.pycache_prefix = _PRIVATE_CACHE.name
sys.dont_write_bytecode = True
for _thread_variable in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ[_thread_variable] = "1"

from autoresearch import (method_registry, project_selection, retrieval_holdout, staged_relevance_adapter as staged, staged_continuation,
                          hypothesis_feedback, relevance_retrieval_adapter as relevance)
from autoresearch.contracts import ResearchError, canonical, fingerprint
from autoresearch.local_workbench import LocalWorkbench
from autoresearch.project_controller import ProjectController, code_identity as controller_identity
from autoresearch.research_project import ResearchProject, code_identity as project_identity, safe_path

REPO = Path(__file__).resolve().parent.parent
SCRIPT = Path(__file__).resolve()
PROTOCOL = REPO / "docs/execution/g5-local/squad-train-conditional-protocol-v1.json"
S046 = REPO / "scripts/run_squad_paragraph_study.py"
STUDY = "s054-squad-train-conditional-v1"
WORKSPACE = REPO / "runs" / STUDY
CLAIM = REPO.parent / ".study-claims" / (STUDY + ".json")
INPUT = Path("/workspace/reference-exploration-20261115/squad-train")
COORDINATOR_LEASE = Path("/workspace/development-continuation-20261114/auto-research-agentarts/.agent/autonomy/lease.json")
PROTOCOL_SHA = "eaea343cd2f9b653b546f6fb8b5b4b3b2ed38452ff6959a866feac2342f0d997"
INPUT_MANIFEST_SHA = "77f50e312c9d64910a9fb37108d49d82bf434647285c4b269f92d365f9b774a1"
CORE_SHA = "300421cc466b459f3b86e74fd6ebecf800dc67f10fb9d7e160f9ad46a839f1e1"
IDS = {"plan":"s054-plan", "evidence_cap":"s054-zero-evidence", "holdout":"s054-holdout",
       "hypothesis":"s054-hypothesis", "primary":"s054-primary", "conditional":"s054-conditional",
       "import":"s054-import", "select":"s054-select"}
PLAN = {"question":"Does the fixed validation-selected lexical method justify the preregistered continuation?",
        "basis":"Public SQuAD v1.1 train paragraphs; fixed source selection, no blind or independent-dataset claim.",
        "steps":"Run the fixed pair; audit and evaluate final only if validation Recall@20 delta is greater than zero.",
        "expected_feedback":"Preserve the original validation difference, unknown reasons, zero and adverse results."}
PLAN_REASON = "Apply the fixed S054 conditional train-split protocol."
CAP_REASON = "S054 authorizes no source-read actions."
CONTINUE_REASON = "Authorize the preregistered audit, freeze, final and report only when its exact condition selects audit."
PROVIDER = {"kind":"operator_assistant", "label":"S054 fixed preregistered protocol"}
RATIONALE = "Execute the original S054 validation pair under the fixed source and budget."


def fail(message):
    raise RuntimeError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def encoded(obj):
    return canonical(obj).encode("utf-8")


def load_s046():
    spec = importlib.util.spec_from_file_location("s054_reused_s046", S046)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_once(path, raw):
    load_s046().save_once(path, raw)


def save_json(path, value):
    write_once(path, encoded(value))


def read_json(path):
    raw = safe_path(path).read_bytes()
    value = json.loads(raw)
    if encoded(value) != raw:
        fail("Original JSON bytes are missing or noncanonical: " + str(path))
    return value


def source_pin(commit):
    if not re.fullmatch(r"[0-9a-f]{40}", commit) or REPO != Path("/workspace/development-continuation-20261114/source-pins") / commit[:7]:
        fail("Use only the canonical clean checkout for the exact source commit.")
    def git(*args):
        return subprocess.run(["git", *args], cwd=REPO, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE).stdout
    if git("rev-parse", "HEAD").decode().strip() != commit or git("status", "--porcelain", "--untracked-files=no").strip():
        fail("Original source checkout must remain clean and at the exact commit.")
    untracked = git("ls-files", "--others", "--", "src").decode().splitlines()
    if any(Path(p).suffix in {".py", ".pyc", ".so", ".pyd"} and "__pycache__" not in Path(p).parts for p in untracked):
        fail("Untracked importable source files could shadow the original code.")
    for path in (SCRIPT, PROTOCOL, S046):
        if git("show", commit + ":" + path.relative_to(REPO).as_posix()) != path.read_bytes():
            fail("Published driver, source helper or protocol bytes differ.")
    publication = load_s046().verify_publication(commit)
    raw = PROTOCOL.read_bytes()
    if sha(raw) != PROTOCOL_SHA:
        fail("The preregistered action protocol changed.")
    protocol = json.loads(raw)
    if (protocol.get("schema_version") != "s054-study-protocol-v1" or protocol.get("study_id") != STUDY
            or protocol.get("fixed_ids") != IDS or protocol.get("input", {}).get("manifest_sha256") != INPUT_MANIFEST_SHA
            or protocol["input"].get("source_data_helper_sha256") != sha(S046.read_bytes())
            or protocol.get("source_requirement", {}).get("project_core_identity") != CORE_SHA
            or protocol.get("budget", {}).get("max_wall_seconds") != 1800
            or protocol.get("runtime", {}).get("python") != ".".join(map(str, sys.version_info[:3]))
            or protocol.get("runtime", {}).get("unicode") != unicodedata.unidata_version
            or project_identity() != CORE_SHA or protocol.get("comparison") != staged.COMPARISON):
        fail("Frozen protocol, current core, runtime or fixed comparison differs.")
    for module in (staged, retrieval_holdout, method_registry, hypothesis_feedback):
        if not Path(module.__file__).resolve().is_relative_to((REPO / "src").resolve()):
            fail("A project module is not from the original pinned checkout.")
    return {"source_commit":commit,"publication":publication,"protocol_sha256":sha(raw),"driver_sha256":sha(SCRIPT.read_bytes()),
            "helper_sha256":sha(S046.read_bytes()),"project_code_identity":project_identity(),
            "controller_code_identity":controller_identity(),"runtime_dependencies":method_registry.runtime_dependencies(),
            "python":sys.version,"unicode":unicodedata.unidata_version}


def fixed_input(protocol):
    raw = safe_path(INPUT / "fixed-input-manifest.json").read_bytes()
    if sha(raw) != INPUT_MANIFEST_SHA:
        fail("The original prepared input manifest changed.")
    manifest = json.loads(raw)
    if (manifest.get("schema_version") != "s054-fixed-source-preparation-v1"
            or manifest.get("status") != "prepared_only_protocol_not_frozen_no_project"
            or manifest.get("source_url") != protocol["input"]["source_url"]
            or manifest.get("source", {}).get("sha256") != protocol["input"]["source_sha256"]
            or manifest.get("source", {}).get("bytes") != protocol["input"]["source_bytes"]
            or manifest.get("corpus_selection", {}).get("sha256") != protocol["input"]["corpus_selection_sha256"]
            or manifest.get("question_selection", {}).get("sha256") != protocol["input"]["question_selection_sha256"]
            or manifest.get("development_assets") != protocol["input"]["development_assets"]
            or manifest.get("holdout") != protocol["input"]["holdout"]
            or manifest.get("source_data_reused", {}).get("script_sha256") != protocol["input"]["source_data_helper_sha256"]
            or manifest.get("split_counts") != protocol["selection"]["splits"] or manifest.get("document_count") != 2200):
        fail("Prepared source metadata differs from the preregistered input.")
    fields = ("source", "source_head", "official_site", "derivation_script", "corpus_selection", "question_selection", "holdout")
    entries = [manifest[k] for k in fields] + manifest["development_assets"] + [manifest["license"]["legalcode"]]
    for entry in entries:
        name = entry["path"]
        if type(name) is not str or Path(name).is_absolute() or ".." in Path(name).parts:
            fail("Prepared input paths must stay within the original source directory.")
        data = safe_path(INPUT / name).read_bytes()
        if len(data) != entry["bytes"] or sha(data) != entry["sha256"]:
            fail("A prepared original or selected asset changed: " + name)
    return manifest, raw


def local_archive(raw):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_STORED) as archive:
        info = zipfile.ZipInfo("train-v1.1.json", (2020, 1, 1, 0, 0, 0))
        info.compress_type = zipfile.ZIP_STORED
        archive.writestr(info, raw)
    return stream.getvalue()


def current_owner():
    """Record the active cooperating coordinator; this is not a global OS lock."""
    lease = json.loads(safe_path(COORDINATOR_LEASE).read_bytes())
    owner = lease.get("owner")
    if (lease.get("schema_version") != "project-autonomy-lease-v1" or lease.get("status") != "active"
            or type(owner) is not str or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,120}", owner)
            or type(lease.get("expires")) not in (int, float) or lease["expires"] <= time.time()):
        fail("The original coordinator has no active readable owner to record.")
    return owner


def verify_selection(packet, holdout, selection, corpus_selection, protocol):
    spec, docs, queries, qrels, _, _ = staged._checked(packet)
    if (len(docs) != 2200 or list(docs) != corpus_selection["selected_document_ids"]
            or set(spec["query_splits"]) != {"dev", "validation"}):
        fail("Prepared corpus differs from the original fixed selection.")
    splits = selection["splits"]
    if set(splits) != {"dev", "validation", "final"} or any(len(splits[k]) != 100 for k in splits):
        fail("Original query selection does not contain the fixed 100/100/100 split.")
    for split in ("dev", "validation"):
        if spec["query_splits"][split] != [x["qid"] for x in splits[split]]:
            fail("Development split IDs differ from the original selection.")
        for row in splits[split]:
            if qrels.get(row["qid"]) != {row["document_id"]:1}:
                fail("Development qrels differ from the original paragraph mapping.")
    final, _ = relevance._jsonl(holdout["queries_jsonl"].encode(), False)
    final_qrels = relevance._qrels(holdout["qrels_tsv"].encode(), docs, final)
    if (holdout["schema_version"] != "retrieval-holdout-v1"
            or holdout["corpus_sha256"] != packet["assets"]["corpus"]["sha256"]
            or list(final) != [x["qid"] for x in splits["final"]] or set(final) & set(queries)
            or any(final_qrels.get(x["qid"]) != {x["document_id"]:1} for x in splits["final"])):
        fail("Original final source and query/paragraph bindings changed.")


def prepare(identity, protocol):
    manifest, manifest_raw = fixed_input(protocol)
    safe_path(CLAIM.parent).mkdir(mode=0o700, parents=True, exist_ok=True)
    claim = {"schema_version":"s054-study-claim-v1","study_id":STUDY,"workspace":str(WORKSPACE),
             "source_commit":identity["source_commit"],"protocol_sha256":PROTOCOL_SHA,"input_manifest_sha256":sha(manifest_raw),
             "created_by_owner":current_owner()}
    if WORKSPACE.exists():
        fail("Original study workspace already exists; never prepare another project.")
    save_json(CLAIM, claim)  # O_EXCL, before creating a study or consuming a tool.
    WORKSPACE.mkdir(mode=0o700, parents=True, exist_ok=False)
    for name in ("private", "development", "requests"):
        (WORKSPACE / name).mkdir(mode=0o700)
    save_json(WORKSPACE / "start.json", {"schema_version":"s054-start-v1", "study_id":STUDY,
              "workspace":str(WORKSPACE),"claim_sha256":sha(encoded(claim)),"input_manifest_sha256":sha(manifest_raw),
              "created_at_utc":datetime.now(timezone.utc).isoformat(),**identity})
    save_json(WORKSPACE / "private/input-manifest.json", manifest)
    for name in ("train-v1.1.json", "source-head.txt", "official-site.html", "cc-by-sa-4.0-legalcode.html",
                 "prepare_source.py", "corpus-selection.json", "question-selection.json", "private/holdout.json"):
        dest = WORKSPACE / "private" / Path(name).name
        write_once(dest, safe_path(INPUT / name).read_bytes())
    for entry in manifest["development_assets"]:
        write_once(WORKSPACE / entry["path"], safe_path(INPUT / entry["path"]).read_bytes())
    raw = (WORKSPACE / "private/train-v1.1.json").read_bytes()
    archive = local_archive(raw)
    write_once(WORKSPACE / "private/original-local.zip", archive)
    receipt = {"schema_version":"s054-source-receipt-v1","url":protocol["input"]["source_url"],
               "original_bytes":len(raw),"original_sha256":sha(raw),"license":"CC BY-SA 4.0",
               "local_archive_description":"ZIP_STORED created locally from the original JSON; not an official ZIP",
               "local_archive_sha256":sha(archive),"local_archive_bytes":len(archive),
               "original_preparation_time":manifest["created_at_utc"]}
    save_json(WORKSPACE / "private/source-receipt.json", receipt)
    selection = read_json(WORKSPACE / "private/question-selection.json")
    corpus_selection = read_json(WORKSPACE / "private/corpus-selection.json")
    spec = {"schema_version":"staged-relevance-development-spec-v1","dataset_label":"SQuAD v1.1 train fixed paragraph cohort",
            "source_url":protocol["input"]["source_url"],"attribution":"Stanford SQuAD authors; CC BY-SA 4.0",
            "license_notes":{"corpus":"SQuAD v1.1 CC BY-SA 4.0","queries_and_qrels":"SQuAD v1.1 CC BY-SA 4.0; derived paragraph mapping"},
            "source_provenance":{"archive_sha256":sha(archive),"source_receipt_sha256":sha(encoded(receipt)),
                                 "selection_sha256":sha(encoded(selection)),"qrels_semantics":staged.SEMANTICS},
            "files":copy.deepcopy(staged.FILES),"query_splits":{k:[x["qid"] for x in selection["splits"][k]] for k in ("dev","validation")},
            "comparison":copy.deepcopy(staged.COMPARISON),"limits":copy.deepcopy(staged.LIMITS)}
    save_json(WORKSPACE / "development/spec.json", spec)
    packet = staged.capture_source(WORKSPACE / "development")
    holdout = read_json(WORKSPACE / "private/holdout.json")
    verify_selection(packet, holdout, selection, corpus_selection, protocol)
    save_json(WORKSPACE / "development/source.json", packet)
    files = sorted(p for directory in (WORKSPACE / "private", WORKSPACE / "development") for p in directory.iterdir() if p.is_file())
    saved = {p.relative_to(WORKSPACE).as_posix():{"bytes":p.stat().st_size,"sha256":sha(p.read_bytes())} for p in files}
    save_json(WORKSPACE / "prepared.json", {"schema_version":"s054-prepared-v1","files":saved,
               "source_snapshot_sha256":packet["snapshot_sha256"],"source_sha256":sha(raw),"claim":claim})
    return {"status":"prepared","project_created":False,"model_calls":0,"research_actions":0,"workspace":str(WORKSPACE)}


def verify_prepared(identity, protocol):
    claim = read_json(CLAIM)
    start = read_json(WORKSPACE / "start.json")
    prepared = read_json(WORKSPACE / "prepared.json")
    owner = claim.get("created_by_owner")
    if type(owner) is not str or re.fullmatch(r"[A-Za-z0-9_.:-]{1,120}", owner) is None:
        fail("Original study claim owner is missing or invalid.")
    expected_claim = {"schema_version":"s054-study-claim-v1","study_id":STUDY,"workspace":str(WORKSPACE),
                      "source_commit":identity["source_commit"],"protocol_sha256":PROTOCOL_SHA,
                      "input_manifest_sha256":INPUT_MANIFEST_SHA,"created_by_owner":owner}
    expected_names = {"private/input-manifest.json", "private/train-v1.1.json", "private/source-head.txt", "private/official-site.html",
                      "private/cc-by-sa-4.0-legalcode.html", "private/prepare_source.py", "private/corpus-selection.json",
                      "private/question-selection.json", "private/holdout.json", "private/original-local.zip", "private/source-receipt.json",
                      "development/corpus.jsonl", "development/queries.jsonl", "development/qrels.tsv", "development/license.md",
                      "development/spec.json", "development/source.json"}
    if (claim != expected_claim or set(prepared.get("files", {})) != expected_names
            or start.get("schema_version") != "s054-start-v1" or start.get("study_id") != STUDY
            or start.get("workspace") != str(WORKSPACE) or start.get("input_manifest_sha256") != INPUT_MANIFEST_SHA
            or start.get("claim_sha256") != sha(encoded(claim)) or prepared.get("claim") != claim
            or any(start.get(k) != v for k,v in identity.items()) or prepared.get("schema_version") != "s054-prepared-v1"):
        fail("Original study claim, source identity or preparation changed.")
    for name, record in prepared["files"].items():
        if type(name) is not str or Path(name).is_absolute() or ".." in Path(name).parts:
            fail("Original prepared inventory contains an unsafe path.")
        path = safe_path(WORKSPACE / name)
        if path.is_relative_to(WORKSPACE) is False or record != {"bytes":path.stat().st_size,"sha256":sha(path.read_bytes())}:
            fail("Original prepared input changed: " + name)
    input_manifest = read_json(WORKSPACE / "private/input-manifest.json")
    if sha(encoded(input_manifest)) != INPUT_MANIFEST_SHA:
        fail("Original input manifest changed.")
    copies = {"source":"private/train-v1.1.json", "source_head":"private/source-head.txt", "official_site":"private/official-site.html",
              "derivation_script":"private/prepare_source.py", "corpus_selection":"private/corpus-selection.json",
              "question_selection":"private/question-selection.json", "holdout":"private/holdout.json"}
    for key, name in copies.items():
        expected = input_manifest[key]
        data = (WORKSPACE / name).read_bytes()
        if len(data) != expected["bytes"] or sha(data) != expected["sha256"]:
            fail("Copied input does not match the original manifest: " + name)
    legal = input_manifest["license"]["legalcode"]
    legal_raw = (WORKSPACE / "private/cc-by-sa-4.0-legalcode.html").read_bytes()
    if len(legal_raw) != legal["bytes"] or sha(legal_raw) != legal["sha256"]:
        fail("Copied original license differs from its manifest.")
    for entry in input_manifest["development_assets"]:
        data = (WORKSPACE / entry["path"]).read_bytes()
        if len(data) != entry["bytes"] or sha(data) != entry["sha256"]:
            fail("Original development asset changed.")
    raw = (WORKSPACE / "private/train-v1.1.json").read_bytes()
    archive = (WORKSPACE / "private/original-local.zip").read_bytes()
    receipt = read_json(WORKSPACE / "private/source-receipt.json")
    expected_receipt = {"schema_version":"s054-source-receipt-v1","url":protocol["input"]["source_url"],
               "original_bytes":len(raw),"original_sha256":sha(raw),"license":"CC BY-SA 4.0",
               "local_archive_description":"ZIP_STORED created locally from the original JSON; not an official ZIP",
               "local_archive_sha256":sha(archive),"local_archive_bytes":len(archive),
               "original_preparation_time":input_manifest["created_at_utc"]}
    if (sha(raw) != protocol["input"]["source_sha256"] or len(raw) != protocol["input"]["source_bytes"]
            or prepared.get("source_sha256") != sha(raw) or receipt != expected_receipt
            or local_archive(raw) != archive or receipt["local_archive_sha256"] != sha(archive)):
        fail("Original JSON or real local ZIP changed.")
    packet = staged.load_source((WORKSPACE / "development/source.json").read_bytes())
    if packet != staged.capture_source(WORKSPACE / "development") or packet["snapshot_sha256"] != prepared["source_snapshot_sha256"]:
        fail("Development packet differs from the original captured files.")
    provenance = packet["spec"]["source_provenance"]
    if (provenance["archive_sha256"] != sha(archive) or provenance["source_receipt_sha256"] != sha(encoded(receipt))
            or provenance["selection_sha256"] != sha((WORKSPACE / "private/question-selection.json").read_bytes())):
        fail("Original archive, receipt or question-selection provenance changed.")
    verify_selection(packet, read_json(WORKSPACE / "private/holdout.json"), read_json(WORKSPACE / "private/question-selection.json"),
                     read_json(WORKSPACE / "private/corpus-selection.json"), protocol)
    return prepared


def request_body(name, build, *, accepted=False):
    path = WORKSPACE / "requests" / (name + ".json")
    if path.exists():
        return read_json(path)
    if accepted:
        fail("Original accepted request body is missing; never reconstruct it.")
    value = build()
    save_json(path, value)
    return value


def require_body(body, fixed, version):
    if (type(body) is not dict or set(body) != set(fixed) | {"expected_state_version"}
            or {k:body[k] for k in fixed} != fixed or type(body["expected_state_version"]) is not int
            or body["expected_state_version"] != version):
        fail("Original request body, fixed fields or state version differ.")


def check_budget(state, cap):
    b = state["budget"]
    if (b["lineage_ref"] != STUDY or b["local_tool_call_limit"] != 3 or b["local_tool_calls_used"] > 3
            or b["local_tool_calls_reserved"] != 0 or b["evidence_read_limit"] != (0 if cap else 8)
            or b["evidence_reads_used"] != 0 or b["evidence_reads_reserved"] != 0
            or b["model_requests_allowed"] != 0 or b["new_model_requests"] != 0 or b["model_requests_reserved"] != 0
            or b["fit_limit"] != 0 or b["fit_attempts_used"] != 0 or b["new_fits"] != 0 or state["evidence_actions"]):
        fail("Original tool, source, model or fit budget changed or remains reserved.")
    expected = [staged.TOOL_ID, staged.AUDIT_TOOL_ID, retrieval_holdout.FINAL_TOOL_ID]
    if [a["command"] for a in state["actions"]] != expected[:len(state["actions"])]:
        fail("Original research action order or count changed.")


def no_unknown(state):
    if (any(a["status"] != "completed" for a in state["actions"] + state["evidence_actions"])
            or any(p["status"] in ("prepared", "running", "unknown", "failed", "rejected", "needs_review")
                   for p in state.get("controller_requests", []))):
        fail("Original action or controller is unfinished, failed or unknown; never redispatch it.")


def plan_cap_holdout(project, manager):
    state = project.status(); no_unknown(state)
    plans = state.get("plan_revisions", [])
    if len(plans) > 1 or (plans and plans[0].get("request_id") != IDS["plan"]):
        fail("Original study plan changed.")
    old = plans[0] if plans else None
    body = request_body("plan", lambda:{"request_id":IDS["plan"],"expected_state_version":state["state_version"],
                                       "plan":copy.deepcopy(PLAN),"reason":PLAN_REASON}, accepted=old is not None)
    require_body(body, {"request_id":IDS["plan"],"plan":PLAN,"reason":PLAN_REASON}, old["based_on_state_version"] if old else state["state_version"])
    if old:
        if any(old.get(k) != v for k,v in PLAN.items()) or old.get("reason") != PLAN_REASON:
            fail("Saved plan differs from the original body.")
    else:
        project.save_plan(**body)
    state = project.status(); revisions = state.get("budget_revisions", [])
    if len(revisions) > 1 or (revisions and revisions[0].get("request_id") != IDS["evidence_cap"]):
        fail("Original evidence cap history changed.")
    old = revisions[0] if revisions else None
    fixed = {"request_id":IDS["evidence_cap"],"expected_limit":8,"new_limit":0,"reason":CAP_REASON}
    body = request_body("evidence-cap", lambda:{**fixed,"expected_state_version":state["state_version"]}, accepted=old is not None)
    require_body(body, fixed, old["state_version_before"] if old else state["state_version"])
    if old:
        if old.get("request") != {"command":"limit_evidence_budget", **body}:
            fail("Original evidence cap body changed.")
    else:
        project.limit_evidence_budget(**body)
    state = project.status(); check_budget(state, True)
    original = (WORKSPACE / "private/holdout.json").read_bytes()
    old = state.get("private_evaluation")
    fixed = {"request_id":IDS["holdout"],"project_id":state["id"],"holdout_base64":base64.b64encode(original).decode("ascii")}
    body = request_body("holdout", lambda:{**fixed,"expected_state_version":state["state_version"]}, accepted=old is not None)
    require_body(body, fixed, old["state_version_before"] if old else state["state_version"])
    if old:
        expected = {"request_id":IDS["holdout"],"expected_state_version":body["expected_state_version"],
                    "holdout_sha256":sha(original),"holdout_bytes":len(original)}
        if old.get("request") != expected:
            fail("Original registered holdout differs from the saved body.")
        retrieval_holdout.validate_metadata(state)
    else:
        manager.register_holdout(body)


def hypothesis(project, protocol):
    state = project.status(); records = state.get("hypothesis_registrations", [])
    if len(records) > 1 or (records and records[0].get("request_id") != IDS["hypothesis"]):
        fail("Original hypothesis ledger changed.")
    old = records[0] if records else None
    if old:
        hypothesis_feedback._check_record(old)
        candidate_id = old["candidate"]["id"]
    else:
        context = ProjectController(project.root).selection_context()
        candidates = [c for c in context["candidates"] if c["method_id"] == staged.TOOL_ID and c["parameters"] == {}]
        if context["blockers"] or len(candidates) != 1:
            fail("The original primary candidate is unavailable or blocked.")
        candidate_id = candidates[0]["id"]
    value = {"candidate_id":candidate_id,"controller_request_id":IDS["primary"],"metric":"recall@20",
             "operator":"gt","threshold":0,"branches":copy.deepcopy(protocol["hypothesis"]["branches"])}
    fixed = {"request_id":IDS["hypothesis"],"hypothesis":value}
    body = request_body("hypothesis", lambda:{**fixed,"expected_state_version":state["state_version"]}, accepted=old is not None)
    require_body(body, fixed, old["state_version_before"] if old else state["state_version"])
    if old:
        if old["request"] != body or old["candidate"]["method_id"] != staged.TOOL_ID:
            fail("Saved hypothesis differs from the original fixed registration.")
    else:
        project.register_hypothesis(**body)


def primary(project):
    state = project.status(); no_unknown(state); check_budget(state, True)
    controller = ProjectController(project.root)
    parents = [p for p in state.get("controller_requests", []) if p["request_id"] == IDS["primary"]]
    if len(parents) > 1:
        fail("Original primary parent is ambiguous.")
    old = parents[0] if parents else None
    def expected(context):
        matches = [c for c in context["candidates"] if c["method_id"] == staged.TOOL_ID and c["parameters"] == {}]
        if context["blockers"] or len(matches) != 1:
            fail("Original sealed context lacks a unique primary candidate.")
        proposal = {"schema_version":"project-selection-proposal-v1","context_sha256":context["context_sha256"],
                    "provider":PROVIDER,"choice":{"kind":"execute","candidate_id":matches[0]["id"]},
                    "rationale":RATIONALE,"evidence_citation_ids":[]}
        project_selection.validate_proposal(context, proposal)
        return {"request_id":IDS["primary"],"expected_state_version":context["state_version"],"proposal":proposal}
    body = request_body("primary", lambda:expected(controller.selection_context()), accepted=old is not None)
    context = old["selection_context"] if old else controller.selection_context()
    if body != expected(context):
        fail("Original primary body differs from its sealed context.")
    if old:
        request = {"project_id":state["id"],"command":"controller.advance_selection","need":"next_check",
                   "expected_state_version":body["expected_state_version"],"proposal":body["proposal"]}
        if old["status"] != "completed" or old["request"] != request:
            fail("The original primary is not completed; never redispatch it.")
    else:
        response = controller.advance_selection(**body)
        if response["status"] != "completed":
            fail("Original primary did not complete.")
    state = project.status(); no_unknown(state); check_budget(state, True)
    parent = next(p for p in state["controller_requests"] if p["request_id"] == IDS["primary"])
    actions = [a for a in state["actions"] if a["request_id"] == parent["child_request_id"]]
    if len(actions) != 1 or actions[0]["command"] != staged.TOOL_ID or actions[0]["status"] != "completed":
        fail("Original primary child is missing or changed.")
    return actions[0]


def deadline_check():
    start = read_json(WORKSPACE / "run-start.json")
    if (type(start) is not dict or set(start) != {"schema_version", "study_id", "started_unix", "deadline_unix", "max_wall_seconds"}
            or start["schema_version"] != "s054-run-start-v1" or start["study_id"] != STUDY
            or type(start["max_wall_seconds"]) is not int or start["max_wall_seconds"] != 1800
            or any(type(start[k]) not in (int, float) or not 0 <= start[k] <= 100000000000
                   or not math.isfinite(start[k]) for k in ("started_unix", "deadline_unix"))
            or start["started_unix"] < 0 or start["deadline_unix"] != start["started_unix"] + 1800):
        fail("Original research window metadata changed.")
    if time.time() >= start["deadline_unix"]:
        fail("Original 1800-second research window expired; do not start a new action.")


def make_summary(project, state, continuation, identity, prepared, protocol):
    no_unknown(state); check_budget(state, True)
    saved_feedback = continuation["conditional"]["feedback"]
    if not state["actions"] or state["actions"][0]["command"] != staged.TOOL_ID:
        fail("Original primary result is unavailable for the final summary.")
    primary_action = state["actions"][0]
    try:
        primary_result = staged._saved(load_s046().saved_tool(project, primary_action))
        if (primary_result["source_snapshot_sha256"] != state["source_snapshot_sha256"]
                or primary_result["scope"] != state["source_scope"]):
            fail("Original primary summary belongs to a different source.")
    except (ResearchError, RuntimeError, OSError, KeyError, ValueError, TypeError):
        if saved_feedback["outcome"] != "unknown":
            raise
        primary_result = None
    primary_summary = {"action_id":primary_action["id"],"request_id":primary_action["request_id"],
                       "artifact":primary_action["artifact"],"result_sha256":primary_action["result_sha256"],
                       "paired_summary":None if primary_result is None else copy.deepcopy(primary_result["paired_summary"]),
                       "adverse_query_count":None if primary_result is None else len(primary_result["adverse_queries"])}
    if continuation["phase"] == "waiting":
        if (continuation["result"]["status"] != "waiting" or len(state["actions"]) != 1
                or saved_feedback["outcome"] not in ("condition_not_met", "unknown")):
            fail("Terminal wait does not match the original fixed branch.")
        final_summary = None; final_status = "unmeasured"; report = None; frozen = None
    elif continuation["phase"] == "done":
        if saved_feedback["outcome"] != "condition_met" or len(state["actions"]) != 3:
            fail("Completed final does not match the original met condition and three-tool budget.")
        tool = load_s046().saved_tool(project, state["actions"][-1])
        result = retrieval_holdout.validate_final_result(tool)
        verified = retrieval_holdout.verify_holdout(project, state)  # Only after the original final completed.
        if verified["sha256"] != state["private_evaluation"]["sha256"]:
            fail("Original project private holdout changed after final completion.")
        final_summary = result["summary"]; final_status = "measured"
        frozen = state["frozen_evaluation_strategy"]
        report = continuation["result"]["manifest"]
    else:
        fail("Original continuation has no verified terminal outcome.")
    return {"schema_version":"s054-study-summary-v1","study_id":STUDY,"source_commit":identity["source_commit"],
        "created_by_owner":prepared["claim"]["created_by_owner"],
        "protocol_sha256":identity["protocol_sha256"],"driver_sha256":identity["driver_sha256"],
        "project_id":state["id"],"run_id":state["run_id"],"project_code_identity":state["code_identity"],
        "project_snapshot_ref":state["snapshot_ref"],"original_source_sha256":prepared["source_sha256"],
        "source_snapshot_sha256":state["source_snapshot_sha256"],"primary":primary_summary,"feedback":saved_feedback,
        "conditional_request_id":IDS["conditional"],"continuation_phase":continuation["phase"],
        "selected_method":None if frozen is None else frozen["selected_method"],"final_status":final_status,
        "final_summary":final_summary,"report_manifest":report,
        "actions":[{k:a[k] for k in ("id","request_id","command","status","result_sha256")} for a in state["actions"]],
        "budget":state["budget"],"limitations":protocol["limitations"],"scientific_validation":False}


def terminal_replay(identity, protocol):
    """Verify a completed original without writable manager access or deadline reset."""
    prepared = verify_prepared(identity, protocol)
    if not (WORKSPACE / "manager/workbench.sqlite").is_file() or not (WORKSPACE / "project-identity.json").is_file():
        fail("Original terminal manager or project identity is missing.")
    manager = LocalWorkbench.open_readonly(WORKSPACE / "manager")
    saved_identity = read_json(WORKSPACE / "project-identity.json")
    body = read_json(WORKSPACE / "requests/conditional.json")
    with manager._connect(readonly=True) as con:
        row = con.execute("SELECT digest,record FROM requests WHERE id=? AND command='continue_staged'", (IDS["conditional"],)).fetchone()
        if row is None or row["digest"] != fingerprint(body):
            fail("Original terminal conditional receipt is missing or changed.")
        continuation = json.loads(row["record"])
        _, project = manager._project(con, saved_identity["project_id"])
    manager._check_staged_continuation(continuation, row["digest"])
    if continuation["status"] != "completed" or continuation["body"] != body:
        fail("Original conditional receipt is not the same terminal request.")
    state = project.status()
    if (state["id"] != saved_identity["project_id"] or state["run_id"] != saved_identity["run_id"]
            or state["code_identity"] != saved_identity["project_code_identity"]
            or state["source_snapshot_sha256"] != saved_identity["source_snapshot_sha256"]):
        fail("Original terminal project identity changed.")
    if continuation["phase"] == "waiting":
        staged_continuation.verify_conditional_policy(state, body, continuation["conditional"])
    else:
        manager._verify_completed_staged(continuation, project, row["digest"])
    actual = make_summary(project, state, continuation, identity, prepared, protocol)
    if read_json(WORKSPACE / "summary.json") != actual:
        fail("Original terminal summary differs from the saved project and receipt.")
    return actual


def verify_resume_manager(manager_path, seed, saved_identity):
    """Read-only verify an existing manager and original project before any writable open."""
    try:
        manager = LocalWorkbench.open_readonly(manager_path)
        import_body = {"request_id":IDS["import"],"workspace":str(seed),"platform_run":None}
        digest = fingerprint(import_body)
        target = manager_path / "projects" / digest
        with manager._connect(readonly=True) as con:
            expected_columns = {"metadata":["key","value"], "projects":["id","goal","slot","report"],
                                "requests":["id","digest","command","record"]}
            for table, columns in expected_columns.items():
                if [row[1] for row in con.execute("PRAGMA table_info(" + table + ")")] != columns:
                    fail("Original manager schema is missing or changed; do not recreate it.")
            projects = list(con.execute("SELECT id,slot FROM projects"))
            if len(projects) > 1 or any(row["id"] != saved_identity["project_id"] or row["slot"] != digest for row in projects):
                fail("Original manager project binding changed.")
            active = manager._active(con)
            if active is not None and active != saved_identity["project_id"]:
                fail("Original active project binding changed.")
            row = con.execute("SELECT digest,command,record FROM requests WHERE id=?", (IDS["import"],)).fetchone()
            if row is None:
                if projects or not seed.is_dir():
                    fail("Original import intent is missing.")
            else:
                record = json.loads(row["record"])
                if (row["digest"] != digest or row["command"] != "import"
                        or record.get("intent", {}).get("project_id") != saved_identity["project_id"]
                        or record.get("intent", {}).get("workspace") != str(seed)
                        or record.get("intent", {}).get("target_workspace") != str(target)
                        or record.get("status") not in {"preparing", "incomplete", "completed"}):
                    fail("Original manager import intent changed.")
                if record["status"] == "completed" and (not projects or record.get("result", {}).get("project_id") != saved_identity["project_id"]):
                    fail("Original completed import receipt changed.")
        if seed.is_dir() == target.is_dir():
            fail("Original project source and managed destination are missing or ambiguous.")
        root = seed if seed.is_dir() else target
        if not (root / "project.sqlite").is_file():
            fail("Original project database is missing; never recreate it.")
        state = ResearchProject(root).status()
        if (state["id"] != saved_identity["project_id"] or state["run_id"] != saved_identity["run_id"]
                or state["registration"]["source_sha256"] != saved_identity["source_sha256"]
                or state["source_snapshot_sha256"] != saved_identity["source_snapshot_sha256"]
                or state["code_identity"] != saved_identity["project_code_identity"]
                or state["budget"]["lineage_ref"] != saved_identity["budget_lineage"]):
            fail("Original project database identity changed.")
    except (sqlite3.Error, KeyError, TypeError, ValueError) as exc:
        raise RuntimeError("Original manager or project database is corrupt; preserve its bytes.") from exc


def run(identity, protocol, *, resume):
    prepared = verify_prepared(identity, protocol)
    seed = WORKSPACE / "project-seed"
    manager_path = WORKSPACE / "manager"
    identity_path = WORKSPACE / "project-identity.json"
    if resume:
        if not (WORKSPACE / "run-start.json").is_file() or not identity_path.is_file() or not (manager_path / "workbench.sqlite").is_file():
            fail("Original project identity or manager database is missing; never recreate it.")
    else:
        if any(p.exists() for p in (WORKSPACE / "run-start.json", identity_path, seed, manager_path)):
            fail("Original study execution already started; use the same project with --resume.")
        started = time.time()
        save_json(WORKSPACE / "run-start.json", {"schema_version":"s054-run-start-v1","study_id":STUDY,
                  "started_unix":started,"deadline_unix":started + 1800,"max_wall_seconds":1800})
        save_json(WORKSPACE / "project-create.json", {"study_id":STUDY,"workspace":str(seed),
                  "source_sha256":sha((WORKSPACE / "development/source.json").read_bytes()),"budget_ref":STUDY,
                  "method_id":staged.TOOL_ID,"max_tool_calls":3})
        project = ResearchProject(seed)
        state = project.create(source=WORKSPACE / "development/source.json", goal="S054 fixed SQuAD train conditional study",
                               budget_ref=STUDY, max_tool_calls=3, method_id=staged.TOOL_ID)
        save_json(identity_path, {"project_id":state["id"],"run_id":state["run_id"],
                  "source_sha256":state["registration"]["source_sha256"],"source_snapshot_sha256":state["source_snapshot_sha256"],
                  "project_code_identity":state["code_identity"],"budget_lineage":STUDY})
    deadline_check()
    project_identity_record = read_json(identity_path)
    if resume:
        verify_resume_manager(manager_path, seed, project_identity_record)
    manager = LocalWorkbench(manager_path)
    import_fixed = {"request_id":IDS["import"],"workspace":str(seed),"platform_run":None}
    import_body = request_body("import", lambda:import_fixed,
                               accepted=not seed.exists())
    if import_body != import_fixed:
        fail("Original import body changed.")
    deadline_check()
    imported = manager.import_project(**import_body)
    if imported["project_id"] != project_identity_record["project_id"]:
        fail("Original managed import changed project identity.")
    select_fixed = {"request_id":IDS["select"],"project_id":project_identity_record["project_id"]}
    select_body = request_body("select", lambda:select_fixed)
    if select_body != select_fixed:
        fail("Original project selection body changed.")
    deadline_check(); manager.select(select_body)
    project, _ = manager.binding()
    state = project.status()
    expected = {"project_id":state["id"],"run_id":state["run_id"],"source_sha256":state["registration"]["source_sha256"],
                "source_snapshot_sha256":state["source_snapshot_sha256"],"project_code_identity":state["code_identity"],"budget_lineage":STUDY}
    if (project_identity_record != expected or state["registration"]["method_id"] != staged.TOOL_ID
            or state["registration"]["source_sha256"] != sha((WORKSPACE / "development/source.json").read_bytes())
            or state["source_snapshot_sha256"] != prepared["source_snapshot_sha256"]
            or state["code_identity"] != identity["project_code_identity"]):
        fail("Original project, source, code or budget lineage changed.")
    project._source(state); no_unknown(state)
    check_budget(state, bool(state.get("budget_revisions")))
    deadline_check(); plan_cap_holdout(project, manager)
    deadline_check(); hypothesis(project, protocol)
    deadline_check(); original_primary = primary(project)
    state = project.status(); no_unknown(state); check_budget(state, True)
    existing = None
    with manager._connect(readonly=True) as con:
        row = con.execute("SELECT 1 FROM requests WHERE id=? AND command='continue_staged'", (IDS["conditional"],)).fetchone()
    if row is not None:
        existing = manager.staged_continuation_record(IDS["conditional"])
    fixed = {"request_id":IDS["conditional"],"project_id":state["id"],"primary_action_id":original_primary["id"],
             "reason":CONTINUE_REASON,"registration_request_id":IDS["hypothesis"]}
    body = request_body("conditional", lambda:{**fixed,"expected_state_version":state["state_version"]}, accepted=existing is not None)
    require_body(body, fixed, existing["body"]["expected_state_version"] if existing else state["state_version"])
    if existing and existing["body"] != body:
        fail("Original conditional manager body changed.")
    stop_path = WORKSPACE / "stopped.json"
    if stop_path.is_file() and read_json(stop_path).get("stop", {}).get("code") == "EXECUTION_UNKNOWN":
        fail("The original continuation was recorded unknown; never redispatch it.")
    deadline_check()
    continuation = manager.continue_staged(body)
    state = project.status()
    if continuation["status"] != "completed":
        stop = {"schema_version":"s054-stopped-v1","study_id":STUDY,"request_id":IDS["conditional"],
                "phase":continuation.get("phase"),"stop":continuation.get("stop"),"project_snapshot_ref":state["snapshot_ref"],
                "final_summary":None,"final_status":"unmeasured"}
        path = WORKSPACE / "stopped.json"
        if not path.exists():
            save_json(path, stop)
        fail("The original continuation is incomplete; inspect its saved stop and never substitute a request.")
    summary = make_summary(project, state, continuation, identity, prepared, protocol)
    output = WORKSPACE / "summary.json"
    if output.exists():
        if read_json(output) != summary:
            fail("Original terminal summary changed; do not replace it.")
    else:
        save_json(output, summary)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-commit", required=True)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--prepare", action="store_true")
    mode.add_argument("--run", action="store_true")
    mode.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    identity = source_pin(args.source_commit)
    protocol = json.loads(PROTOCOL.read_bytes())
    if args.prepare:
        result = prepare(identity, protocol)
    elif args.resume and (WORKSPACE / "summary.json").is_file():
        result = terminal_replay(identity, protocol)
    else:
        if args.resume and (WORKSPACE / "run-start.json").is_file():
            deadline_check()
        # A single process alarm bounds a running native stage as well as dispatches.
        if args.run:
            signal.signal(signal.SIGALRM, lambda *_: (_ for _ in ()).throw(TimeoutError("Original research window expired.")))
            signal.alarm(1800)
        elif args.resume:
            start = read_json(WORKSPACE / "run-start.json")
            signal.signal(signal.SIGALRM, lambda *_: (_ for _ in ()).throw(TimeoutError("Original research window expired.")))
            signal.alarm(max(1, int(start["deadline_unix"] - time.time())))
        try:
            result = run(identity, protocol, resume=args.resume)
        finally:
            signal.alarm(0)
    print(canonical(result))


if __name__ == "__main__":
    try:
        main()
    except (ResearchError, RuntimeError, OSError, KeyError, ValueError, TypeError, UnicodeError,
            zipfile.BadZipFile, subprocess.CalledProcessError, TimeoutError, sqlite3.Error) as exc:
        if (WORKSPACE / "run-start.json").is_file() and not (WORKSPACE / "summary.json").exists():
            failure = WORKSPACE / "failure.json"
            if not failure.exists():
                try:
                    save_json(failure, {"schema_version":"s054-failure-v1","study_id":STUDY,
                              "error_type":type(exc).__name__,"error_code":getattr(exc, "code", None),
                              "message":str(exc),"final_status":"unmeasured"})
                except (OSError, ValueError, TypeError):
                    pass
        print("S054 stopped: " + str(exc), file=sys.stderr)
        raise SystemExit(1)
