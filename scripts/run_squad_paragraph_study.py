#!/usr/bin/env python3
"""Run the preregistered, fixed S046 paragraph retrieval study once.

This driver must itself and its protocol be committed with the exact selected
source commit. It never creates a second workspace, retries an unknown action,
or changes budgets. Run only after the owner confirms the committed protocol.
"""
import argparse
import base64
import copy
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import urllib.request
import zipfile

from autoresearch import method_registry, project_selection, retrieval_holdout, staged_relevance_adapter as staged
from autoresearch.contracts import ResearchError, canonical, fingerprint
from autoresearch.project_controller import ProjectController, code_identity as controller_identity
from autoresearch.project_report import export_report
from autoresearch.research_project import ResearchProject, code_identity as project_identity, safe_path

REPO = Path(__file__).absolute().parent.parent
WORKSPACE = REPO / "runs" / "s046-squad-paragraph-retrieval-v1"
PROTOCOL = REPO / "docs" / "execution" / "g5-local" / "squad-paragraph-protocol-v1.json"
SCRIPT = REPO / "scripts" / "run_squad_paragraph_study.py"
URL = "https://rajpurkar.github.io/SQuAD-explorer/dataset/dev-v1.1.json"
EXPECTED_BYTES = 4_854_279
MAX_BYTES = 8_388_608
STUDY = "s046-squad-paragraph-retrieval-v1"
IDS = {"plan": "s046-plan", "cap": "s046-evidence-cap", "holdout": "s046-holdout", "primary": "s046-primary",
       "audit": "s046-audit", "freeze": "s046-freeze", "final": "s046-final"}
PLAN = {"question": "Does fixed validation-selected lexical retrieval improve final paragraph Recall@20 over BM25?",
        "basis": "Public SQuAD 1.1 paragraphs and questions; procedural 100/100/100 split, not a blind evaluation.",
        "steps": "Fixed BM25/TF-IDF development pair; saved audit; freeze validation delta > 0; evaluate final once.",
        "expected_feedback": "Keep zero and adverse results; final query-level Recall@20 selected-minus-BM25."}
PLAN_REASON = "S046 fixed public-data protocol preregistered before download and scoring."
CAP_REASON = "Fixed S046 protocol authorizes no source-read actions."


def fail(message):
    raise RuntimeError(message)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def utc():
    return datetime.now(timezone.utc).isoformat()


def encode(value):
    return canonical(value).encode("utf-8")


def save_once(path, data):
    path = safe_path(path)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    directory = os.open(path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(directory)
    finally:
        os.close(directory)


def save_json(path, value):
    save_once(path, encode(value))


def read_json(path):
    raw = safe_path(path).read_bytes()
    value = json.loads(raw)
    if encode(value) != raw:
        fail("Saved JSON is noncanonical or changed: " + str(path))
    return value


def git(*args):
    return subprocess.run(["git", *args], cwd=REPO, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE).stdout


def verify_publication(source_commit):
    # Verify actual publication before the data GET. The remote head is not
    # part of immutable study identity: a later main may legitimately advance.
    published = git("ls-remote", "--exit-code", "origin", "refs/heads/main").decode("ascii").splitlines()
    if len(published) != 1 or re.fullmatch(r"[0-9a-f]{40}\trefs/heads/main", published[0]) is None:
        fail("The actual origin/main head could not be verified.")
    remote_head = published[0].split("\t", 1)[0]
    present = subprocess.run(["git", "cat-file", "-e", remote_head + "^{commit}"], cwd=REPO,
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if present.returncode != 0:
        fail("The verified remote head is not in the local Git object database; fetch it before retrying.")
    ancestor = subprocess.run(["git", "merge-base", "--is-ancestor", source_commit, remote_head], cwd=REPO,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if ancestor.returncode != 0:
        fail("The actual origin/main head does not contain the requested source commit.")
    return {"method": "git-ls-remote-origin-main-ancestor", "source_commit": source_commit}


def check_source_pin(source_commit):
    if not re.fullmatch(r"[0-9a-f]{40}", source_commit) or git("rev-parse", "HEAD").decode().strip() != source_commit:
        fail("Pass the exact current committed source SHA; switching or upgrading a study is forbidden.")
    publication = verify_publication(source_commit)
    for path in (SCRIPT, PROTOCOL):
        name = path.relative_to(REPO).as_posix()
        if git("show", source_commit + ":" + name) != path.read_bytes():
            fail("Driver or preregistered protocol differs from the committed bytes.")
    subprocess.run(["git", "diff", "--quiet", source_commit, "--", "src", str(SCRIPT.relative_to(REPO)),
                    str(PROTOCOL.relative_to(REPO))], cwd=REPO, check=True)
    if git("ls-files", "--others", "--exclude-standard", "--", "src").strip():
        fail("Untracked source files could change the registered implementation.")
    protocol = json.loads(PROTOCOL.read_bytes())
    if (protocol.get("schema_version") != "squad-paragraph-retrieval-protocol-v1" or protocol.get("study_id") != STUDY
            or protocol.get("status") != "preregistered_before_data_download_and_scoring"
            or protocol.get("source", {}).get("url") != URL or protocol["source"]["version"] != "1.1"
            or protocol["source"]["expected_bytes_from_official_HEAD"] != EXPECTED_BYTES
            or protocol["source"]["maximum_download_bytes"] != MAX_BYTES):
        fail("The committed protocol does not match this fixed driver.")
    # Refuse an installed older package that shadows this checkout.
    for module in (staged, retrieval_holdout, method_registry):
        if not Path(module.__file__).absolute().is_relative_to(REPO / "src"):
            fail("The active autoresearch package is outside this source checkout.")
    return {"source_commit": source_commit, "publication": publication,
            "protocol_sha256": digest(PROTOCOL.read_bytes()),
            "driver_sha256": digest(SCRIPT.read_bytes()), "project_code_identity": project_identity(),
            "controller_code_identity": controller_identity(), "runtime_dependencies": method_registry.runtime_dependencies()}


def source_data(raw):
    """Derive only from paragraph text, question ID and question text; never inspect answers."""
    obj = json.loads(raw.decode("utf-8"))
    if type(obj) is not dict or obj.get("version") != "1.1" or type(obj.get("data")) is not list:
        fail("The original dataset must be a SQuAD 1.1 data object.")
    docs, unique_by_text, seen_ids = [], {}, set()
    total_questions = 0
    for article_index, article in enumerate(obj["data"]):
        if type(article) is not dict or type(article.get("title")) is not str or type(article.get("paragraphs")) is not list:
            fail("Malformed original article.")
        for paragraph_index, paragraph in enumerate(article["paragraphs"]):
            if type(paragraph) is not dict or type(paragraph.get("context")) is not str or type(paragraph.get("qas")) is not list:
                fail("Malformed original paragraph.")
            doc_id = f"squad11-{article_index}-{paragraph_index}"
            docs.append({"_id": doc_id, "title": article["title"], "text": paragraph["context"], "metadata": {}})
            for qa in paragraph["qas"]:
                if type(qa) is not dict:
                    fail("Malformed original question.")
                qid, question = qa.get("id"), qa.get("question")
                if (type(qid) is not str or re.fullmatch(r"[A-Za-z0-9_.:-]{1,80}", qid) is None
                        or qid in seen_ids or type(question) is not str or not question.strip() or "\x00" in question):
                    fail("Question IDs must be unique and valid; questions must be nonempty.")
                seen_ids.add(qid)
                total_questions += 1
                key = question.strip().casefold()
                previous = unique_by_text.get(key)
                if previous is None or qid < previous["qid"]:
                    unique_by_text[key] = {"qid": qid, "question": question, "document_id": doc_id}
    ordered = sorted(unique_by_text.values(), key=lambda item: (
        hashlib.sha256(("s045-squad-paragraph-v1:" + item["qid"]).encode("utf-8")).hexdigest(), item["qid"]))
    if len(ordered) < 300:
        fail("Fewer than 300 distinct normalized questions; do not retune the protocol.")
    chosen = ordered[:300]
    return {"documents": docs, "dev": chosen[:100], "validation": chosen[100:200], "final": chosen[200:300],
            "original_question_count": total_questions, "unique_question_count": len(unique_by_text)}


def jsonl(rows):
    return ("\n".join(canonical(row) for row in rows) + "\n").encode("utf-8")


def query_rows(rows):
    return [{"_id": row["qid"], "text": row["question"], "metadata": {}} for row in rows]


def qrels(rows):
    return ("query-id\tcorpus-id\tscore\n" + "".join(row["qid"] + "\t" + row["document_id"] + "\t1\n" for row in rows)).encode("utf-8")


def original_archive(raw):
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_STORED) as archive:
        info = zipfile.ZipInfo("dev-v1.1.json", (2020, 1, 1, 0, 0, 0))
        info.compress_type = zipfile.ZIP_STORED
        archive.writestr(info, raw)
    value = output.getvalue()
    with zipfile.ZipFile(io.BytesIO(value)) as archive:
        if archive.namelist() != ["dev-v1.1.json"] or archive.read("dev-v1.1.json") != raw:
            fail("Created local ZIP does not contain the downloaded original.")
    return value


def download_original():
    request = urllib.request.Request(URL, headers={"Accept-Encoding": "identity", "User-Agent": "auto-research-s046/1.0"})
    with urllib.request.urlopen(request, timeout=60) as response:
        if response.status != 200 or response.geturl() != URL:
            fail("The official source did not return the exact pinned URL and status.")
        length = response.headers.get("Content-Length")
        if length is not None and int(length) != EXPECTED_BYTES:
            fail("The official Content-Length differs from the preregistered size.")
        raw = response.read(MAX_BYTES + 1)
    if len(raw) != EXPECTED_BYTES or len(raw) > MAX_BYTES:
        fail("The source byte count differs from the preregistered HEAD; no data will be substituted.")
    return raw


def initialize(source_identity):
    safe_path(WORKSPACE)
    WORKSPACE.mkdir(mode=0o700, parents=True, exist_ok=False)
    private = WORKSPACE / "private"
    private.mkdir(mode=0o700)
    development = WORKSPACE / "development"
    development.mkdir(mode=0o700)
    (WORKSPACE / "requests").mkdir(mode=0o700)
    save_json(WORKSPACE / "start.json", {"schema_version": "s046-start-v1", "study_id": STUDY,
               "started_at_utc": utc(), **source_identity, "download_url": URL, "expected_bytes": EXPECTED_BYTES})
    # The original body is requested once. An interrupted preparation is retained
    # and --resume will stop, rather than fetch again or create another study.
    raw = download_original()
    received_at = utc()
    save_once(private / "dev-v1.1.json", raw)
    archive = original_archive(raw)
    save_once(private / "original-local.zip", archive)
    data = source_data(raw)
    rows_by_split = {key: data[key] for key in ("dev", "validation", "final")}
    selection = {"schema_version": "s046-selection-v1", "source_sha256": digest(raw),
                 "selection_rule": "deduplicate strip.casefold by smallest qid, then SHA256(s045-squad-paragraph-v1:<qid>) and qid",
                 "original_question_count": data["original_question_count"], "unique_question_count": data["unique_question_count"],
                 "splits": {split: [{"qid": row["qid"], "document_id": row["document_id"]} for row in rows]
                            for split, rows in rows_by_split.items()}}
    selection_raw = encode(selection)
    save_once(private / "selection.json", selection_raw)
    receipt = {"schema_version": "s046-source-receipt-v1", "url": URL, "version": "1.1", "received_at_utc": received_at,
               "bytes": len(raw), "sha256": digest(raw), "license": "CC BY-SA 4.0",
               "license_url": "https://creativecommons.org/licenses/by-sa/4.0/",
               "archive_description": "ZIP created locally from the exact downloaded JSON; not an official ZIP",
               "local_zip_sha256": digest(archive), "local_zip_bytes": len(archive)}
    receipt_raw = encode(receipt)
    save_once(private / "source-receipt.json", receipt_raw)
    corpus = jsonl(data["documents"])
    dev = data["dev"] + data["validation"]
    save_once(development / "corpus.jsonl", corpus)
    save_once(development / "queries.jsonl", jsonl(query_rows(dev)))
    save_once(development / "qrels.tsv", qrels(dev))
    license_note = ("Stanford SQuAD v1.1 development dataset, CC BY-SA 4.0 as declared at "
                    "https://rajpurkar.github.io/SQuAD-explorer/; original bytes retained privately. "
                    "Paragraph retrieval mapping is a derived task, not question answering.\n").encode()
    save_once(development / "license.md", license_note)
    spec = {"schema_version": "staged-relevance-development-spec-v1", "dataset_label": "SQuAD v1.1 derived paragraph retrieval",
            "source_url": URL, "attribution": "Stanford Question Answering Dataset authors; CC BY-SA 4.0",
            "license_notes": {"corpus": "SQuAD v1.1, CC BY-SA 4.0", "queries_and_qrels": "SQuAD v1.1, CC BY-SA 4.0; paragraph mapping derived"},
            "source_provenance": {"archive_sha256": digest(archive), "source_receipt_sha256": digest(receipt_raw),
                                  "selection_sha256": digest(selection_raw), "qrels_semantics": staged.SEMANTICS},
            "files": copy.deepcopy(staged.FILES), "query_splits": {key: [row["qid"] for row in data[key]] for key in ("dev", "validation")},
            "comparison": copy.deepcopy(staged.COMPARISON), "limits": copy.deepcopy(staged.LIMITS)}
    save_json(development / "spec.json", spec)
    packet = staged.capture_source(development)
    save_json(development / "source.json", packet)
    final = data["final"]
    holdout = {"schema_version": "retrieval-holdout-v1", "corpus_sha256": packet["assets"]["corpus"]["sha256"],
               "queries_jsonl": jsonl(query_rows(final)).decode("utf-8"), "qrels_tsv": qrels(final).decode("utf-8")}
    save_json(private / "holdout.json", holdout)
    files = [private / "dev-v1.1.json", private / "original-local.zip", private / "selection.json", private / "source-receipt.json",
             private / "holdout.json", *[development / name for name in ("corpus.jsonl", "queries.jsonl", "qrels.tsv", "license.md", "spec.json", "source.json")]]
    records = {p.relative_to(WORKSPACE).as_posix(): {"sha256": digest(p.read_bytes()), "bytes": p.stat().st_size} for p in files}
    save_json(WORKSPACE / "prepared.json", {"schema_version": "s046-prepared-v1", "files": records,
               "source_snapshot_sha256": packet["snapshot_sha256"], "source_sha256": digest(raw),
               "document_count": len(data["documents"]), "original_question_count": data["original_question_count"],
               "unique_question_count": data["unique_question_count"], "split_counts": {key: len(data[key]) for key in rows_by_split}})


def verify_prepared(source_identity):
    start = read_json(WORKSPACE / "start.json")
    if any(start.get(key) != value for key, value in source_identity.items()) or start.get("study_id") != STUDY:
        fail("Original source, protocol, driver, runtime or code identity changed.")
    prepared = read_json(WORKSPACE / "prepared.json")
    if prepared.get("schema_version") != "s046-prepared-v1" or prepared.get("split_counts") != {"dev": 100, "validation": 100, "final": 100}:
        fail("Original preparation is incomplete or changed; no second download is allowed.")
    expected = {"private/dev-v1.1.json", "private/original-local.zip", "private/selection.json", "private/source-receipt.json",
                "private/holdout.json", "development/corpus.jsonl", "development/queries.jsonl", "development/qrels.tsv",
                "development/license.md", "development/spec.json", "development/source.json"}
    if set(prepared["files"]) != expected:
        fail("Prepared file inventory changed.")
    for name, info in prepared["files"].items():
        raw = safe_path(WORKSPACE / name).read_bytes()
        if info != {"sha256": digest(raw), "bytes": len(raw)}:
            fail("Original prepared bytes changed: " + name)
    raw = (WORKSPACE / "private" / "dev-v1.1.json").read_bytes()
    receipt = read_json(WORKSPACE / "private" / "source-receipt.json")
    archive = (WORKSPACE / "private" / "original-local.zip").read_bytes()
    if (len(raw) != EXPECTED_BYTES or digest(raw) != prepared["source_sha256"] or receipt["sha256"] != digest(raw)
            or receipt["local_zip_sha256"] != digest(archive) or original_archive(raw) != archive):
        fail("Downloaded original, real local ZIP, or receipt identity differs.")
    packet = staged.load_source((WORKSPACE / "development" / "source.json").read_bytes())
    if (packet["snapshot_sha256"] != prepared["source_snapshot_sha256"]
            or staged.capture_source(WORKSPACE / "development") != packet):
        fail("Development-only source packet no longer matches its original files.")
    return prepared


def request_body(name, create, *, accepted=False):
    path = WORKSPACE / "requests" / (name + ".json")
    if path.exists():
        return read_json(path)
    if accepted:
        fail("Original accepted request body is missing; do not reconstruct it.")
    value = create()
    save_json(path, value)
    return value


def assert_no_unknown(state):
    if (any(a["status"] != "completed" for a in state["actions"] + state["evidence_actions"])
            or any(p["status"] in ("prepared", "running", "unknown", "failed", "rejected", "needs_review")
                   for p in state.get("controller_requests", []))):
        fail("Original operation is incomplete, failed or unknown; retain the original ID and stop without redispatch.")


def check_budget(state, cap_applied):
    b = state["budget"]
    if (b["local_tool_call_limit"] != 3 or b["local_tool_calls_used"] > 3 or b["local_tool_calls_reserved"] != 0
            or b["model_requests_allowed"] != 0 or b["new_model_requests"] != 0 or b["model_requests_reserved"] != 0
            or b["fit_limit"] != 0 or b["fit_attempts_used"] != 0 or b["new_fits"] != 0
            or b["evidence_reads_used"] != 0 or b["evidence_reads_reserved"] != 0
            or b["evidence_read_limit"] != (0 if cap_applied else 8) or state["evidence_actions"]):
        fail("Original three-tool, zero-source, zero-model or zero-fit budget changed.")
    expected = [staged.TOOL_ID, staged.AUDIT_TOOL_ID, retrieval_holdout.FINAL_TOOL_ID]
    if [action["command"] for action in state["actions"]] != expected[:len(state["actions"])]:
        fail("An unexpected action, order or extra dispatch exists.")


def validate_fixed_body(body, fixed, state, original_version=None):
    if (type(body) is not dict or set(body) != set(fixed) | {"expected_state_version"}
            or canonical({key: body[key] for key in fixed}) != canonical(fixed)
            or type(body["expected_state_version"]) is not int or body["expected_state_version"] < 0):
        fail("A saved request differs from its fixed S046 fields.")
    if body["expected_state_version"] != (state["state_version"] if original_version is None else original_version):
        fail("A saved request does not bind its original project state version.")


def plan_and_registration(project):
    state = project.status()
    assert_no_unknown(state)
    plans = state.get("plan_revisions", [])
    if len(plans) > 1 or (plans and plans[0].get("request_id") != IDS["plan"]):
        fail("The original fixed study plan changed.")
    old_plan = plans[0] if plans else None
    body = request_body("plan", lambda: {"request_id": IDS["plan"], "expected_state_version": state["state_version"],
        "plan": copy.deepcopy(PLAN), "reason": PLAN_REASON}, accepted=old_plan is not None)
    validate_fixed_body(body, {"request_id": IDS["plan"], "plan": PLAN, "reason": PLAN_REASON}, state,
                        old_plan["based_on_state_version"] if old_plan else None)
    if old_plan and (canonical({key: old_plan[key] for key in PLAN}) != canonical(PLAN)
                     or old_plan["reason"] != PLAN_REASON):
        fail("The accepted plan differs from the fixed S046 plan.")
    project.save_plan(**body)
    state = project.status()
    revisions = state.get("budget_revisions", [])
    if len(revisions) > 1 or (revisions and revisions[0].get("request_id") != IDS["cap"]):
        fail("The original evidence cap revision changed.")
    old_cap = revisions[0] if revisions else None
    body = request_body("evidence-cap", lambda: {"request_id": IDS["cap"], "expected_limit": 8, "new_limit": 0,
                         "expected_state_version": state["state_version"], "reason": CAP_REASON}, accepted=old_cap is not None)
    validate_fixed_body(body, {"request_id": IDS["cap"], "expected_limit": 8, "new_limit": 0, "reason": CAP_REASON}, state,
                        old_cap["state_version_before"] if old_cap else None)
    if old_cap and canonical(old_cap.get("request")) != canonical({"command": "limit_evidence_budget", **body}):
        fail("The accepted evidence cap differs from its original body.")
    project.limit_evidence_budget(**body)
    state = project.status()
    check_budget(state, True)
    raw = safe_path(WORKSPACE / "private" / "holdout.json").read_bytes()
    old = state.get("private_evaluation")
    body = request_body("holdout", lambda: {"request_id": IDS["holdout"], "expected_state_version": state["state_version"],
                                            "holdout_base64": base64.b64encode(raw).decode("ascii")}, accepted=old is not None)
    validate_fixed_body(body, {"request_id": IDS["holdout"], "holdout_base64": base64.b64encode(raw).decode("ascii")}, state,
                        old["state_version_before"] if old else None)
    if old:
        expected = {"request_id": body["request_id"], "expected_state_version": body["expected_state_version"],
                    "holdout_sha256": digest(raw), "holdout_bytes": len(raw)}
        if canonical(old.get("request")) != canonical(expected):
            fail("The original holdout request differs from the saved body.")
        retrieval_holdout.validate_metadata(state)
    else:
        project.register_holdout(request_id=body["request_id"], expected_state_version=body["expected_state_version"], holdout=raw)


def controller_action(project, stage, method):
    controller = ProjectController(project.root)
    state = project.status()
    assert_no_unknown(state)
    check_budget(state, True)
    parent = next((p for p in state.get("controller_requests", []) if p["request_id"] == IDS[stage]), None)
    def expected_body(context):
        candidates = [row for row in context["candidates"] if row["method_id"] == method]
        if len(candidates) != 1 or context["blockers"]:
            fail("The single fixed native candidate is missing or blocked.")
        proposal = {"schema_version": "project-selection-proposal-v1", "context_sha256": context["context_sha256"],
                    "provider": {"kind": "operator_assistant", "label": "S046 fixed preregistered protocol"},
                    "choice": {"kind": "execute", "candidate_id": candidates[0]["id"]},
                    "rationale": "Execute the one fixed S046 stage under the original controller and budget.",
                    "evidence_citation_ids": []}
        project_selection.validate_proposal(context, proposal)
        return {"request_id": IDS[stage], "expected_state_version": context["state_version"], "proposal": proposal}
    body = request_body(stage, lambda: expected_body(controller.selection_context()), accepted=parent is not None)
    context = parent["selection_context"] if parent is not None else controller.selection_context()
    if canonical(body) != canonical(expected_body(context)):
        fail("Saved controller request differs from its sealed fixed-method selection context.")
    if parent is not None:
        request = {"project_id": state["id"], "command": "controller.advance_selection", "need": "next_check",
                   "expected_state_version": body["expected_state_version"], "proposal": body["proposal"]}
        if (parent["status"] != "completed" or canonical(parent["request"]) != canonical(request)
                or parent["decision"]["next_action"].get("method_id") != method):
            fail("Original controller request is not the same completed stage; do not redispatch.")
    response = controller.advance_selection(**body)
    if response["status"] != "completed":
        fail("The original controller action did not complete; stop without a new ID.")
    state = project.status()
    assert_no_unknown(state)
    check_budget(state, True)
    child = [a for a in state["actions"] if a["request_id"] == response["child_request_id"]]
    if len(child) != 1 or child[0]["command"] != method or child[0]["status"] != "completed":
        fail("The completed parent does not bind the expected original child.")
    return child[0]


def saved_tool(project, action):
    envelope = read_json(project._artifact(action))
    if (envelope.get("sha256") != action["result_sha256"]
            or envelope["sha256"] != fingerprint({k: v for k, v in envelope.items() if k != "sha256"})
            or envelope.get("action_id") != action["id"] or envelope.get("request_sha256") != action["request_sha256"]
            or envelope.get("source_snapshot_sha256") != action["source_snapshot_sha256"]
            or envelope.get("code_identity") != action["code_identity"]):
        fail("Original completed action artifact or envelope changed.")
    return envelope["tool_result"]


def freeze(project, primary):
    state = project.status()
    old = state.get("frozen_evaluation_strategy")
    body = request_body("freeze", lambda: {"request_id": IDS["freeze"], "expected_state_version": state["state_version"],
                                            "primary_action_id": primary["id"]}, accepted=old is not None)
    validate_fixed_body(body, {"request_id": IDS["freeze"], "primary_action_id": primary["id"]}, state,
                        old["request"]["expected_state_version"] if old else None)
    if old and canonical(old.get("request")) != canonical(body):
        fail("The accepted frozen-strategy request differs from its original body.")
    return project.freeze_retrieval_strategy(**body)


def verified_report(project):
    output = WORKSPACE / "report"
    if not output.exists():
        return export_report(workspace=project.root, output=output)
    manifest = read_json(output / "manifest.json")
    if manifest.get("project_id") != project.status()["id"] or manifest.get("project_snapshot_ref") != project.status()["snapshot_ref"]:
        fail("Original report no longer matches the study; do not overwrite it.")
    for name, info in manifest["files"].items():
        if name not in {"report.json", "report.md", "report.pdf", "input.json"}:
            fail("Unexpected report file.")
        data = (output / name).read_bytes()
        if info != {"sha256": digest(data), "bytes": len(data)}:
            fail("An original report file changed.")
    if set(manifest["files"]) != {"report.json", "report.md", "report.pdf", "input.json"}:
        fail("Original report is incomplete.")
    return manifest


def execute_study(source_identity, resume):
    if resume:
        if not WORKSPACE.is_dir() or not (WORKSPACE / "project" / "project.sqlite").is_file():
            fail("The original project database is missing; it must never be recreated.")
    else:
        if WORKSPACE.exists():
            fail("This study workspace already exists; use only its original IDs via --resume.")
        initialize(source_identity)
    prepared = verify_prepared(source_identity)
    project = ResearchProject(WORKSPACE / "project")
    if not resume:
        project.create(source=WORKSPACE / "development" / "source.json", goal="S046 fixed SQuAD paragraph retrieval protocol",
                       budget_ref=STUDY, max_tool_calls=3, method_id=staged.TOOL_ID)
        state = project.status()
        save_json(WORKSPACE / "project-identity.json", {"project_id": state["id"], "run_id": state["run_id"],
                  "source_sha256": state["registration"]["source_sha256"], "source_snapshot_sha256": state["source_snapshot_sha256"],
                  "project_code_identity": state["code_identity"], "budget_lineage": STUDY})
    identity = read_json(WORKSPACE / "project-identity.json")
    state = project.status()
    if (identity.get("project_id") != state["id"] or identity.get("run_id") != state["run_id"]
            or identity.get("source_sha256") != state["registration"]["source_sha256"]
            or identity.get("source_sha256") != digest((WORKSPACE / "development" / "source.json").read_bytes())
            or identity.get("source_snapshot_sha256") != state["source_snapshot_sha256"]
            or identity.get("source_snapshot_sha256") != prepared["source_snapshot_sha256"]
            or identity.get("project_code_identity") != state["code_identity"]
            or identity.get("project_code_identity") != source_identity["project_code_identity"]
            or identity.get("budget_lineage") != state["budget"]["lineage_ref"]
            or state["registration"]["method_id"] != staged.TOOL_ID):
        fail("The original project/source/code/budget identity changed; never create a replacement.")
    project._source(state)
    assert_no_unknown(state)
    # On replay plan/cap requests return their original revisions without new usage.
    plan_and_registration(project)
    primary = controller_action(project, "primary", staged.TOOL_ID)
    primary_result = staged._saved(saved_tool(project, primary))
    audit = controller_action(project, "audit", staged.AUDIT_TOOL_ID)
    audit_tool = saved_tool(project, audit)
    staged.AUDIT.next_decision(audit_tool)
    predecessor = {"based_on_action_id": primary["id"], "based_on_result_sha256": primary["result_sha256"]}
    if (audit.get("parameters") != predecessor or audit_tool["result"].get("predecessor") != predecessor
            or audit_tool["result"].get("summary") != primary_result["paired_summary"]
            or audit_tool["result"].get("rankings_sha256") != primary_result["rankings_before_scoring_sha256"]):
        fail("The saved audit does not bind the original primary result and paired summary.")
    frozen = freeze(project, primary)
    final = controller_action(project, "final", retrieval_holdout.FINAL_TOOL_ID)
    final_tool = saved_tool(project, final)
    retrieval_holdout.validate_final_result(final_tool)
    state = project.status()
    if (final.get("parameters") != predecessor or final_tool["result"]["predecessor"] != predecessor
            or final_tool["result"]["freeze_sha256"] != frozen["record_sha256"]
            or final_tool["result"]["holdout_sha256"] != state["private_evaluation"]["sha256"]
            or final_tool["result"]["selected_method"] != frozen["selected_method"]):
        fail("The final result does not bind the original holdout, frozen strategy and primary result.")
    # This opens the project's private copy only after its final action is complete.
    verified_holdout = retrieval_holdout.verify_holdout(project, state)
    if verified_holdout["sha256"] != state["private_evaluation"]["sha256"]:
        fail("The original project holdout bytes changed after final evaluation.")
    check_budget(state, True)
    if state["budget"]["local_tool_calls_used"] != 3 or len(state["actions"]) != 3:
        fail("Exactly the original three completed tool actions are required.")
    report = verified_report(project)
    result = final_tool["result"]
    summary = {"schema_version": "s046-study-summary-v1", "study_id": STUDY, "project_id": state["id"], "run_id": state["run_id"],
        "source_commit": source_identity["source_commit"], "project_code_identity": state["code_identity"],
        "protocol_sha256": source_identity["protocol_sha256"], "driver_sha256": source_identity["driver_sha256"],
        "original_source_sha256": prepared["source_sha256"], "source_snapshot_sha256": state["source_snapshot_sha256"],
        "document_count": prepared["document_count"], "original_question_count": prepared["original_question_count"],
        "unique_question_count": prepared["unique_question_count"], "split_counts": prepared["split_counts"],
        "validation_delta_recall20": frozen["validation_delta_recall20"], "selected_method": frozen["selected_method"],
        "final_summary": result["summary"], "final_usage": result["usage"],
        "actions": [{key: action[key] for key in ("id", "request_id", "command", "status", "result_sha256")} for action in state["actions"]],
        "budget": state["budget"], "report_snapshot_ref": report["project_snapshot_ref"],
        "limitations": ["Public SQuAD development data and same-user procedural separation are not blind or OS-isolated.",
                        "One positive paragraph mapping is not exhaustive relevance or QA answer quality.",
                        "This single fixed subset does not prove general research benefit or statistical significance."],
        "scientific_validation": False}
    path = WORKSPACE / "summary.json"
    if path.exists():
        if read_json(path) != summary:
            fail("The original completed summary changed; do not overwrite it.")
    else:
        save_json(path, summary)
    print(canonical(summary))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-commit", required=True, help="Exact committed S045 implementation and S046 protocol SHA")
    parser.add_argument("--resume", action="store_true", help="Read and reuse the original workspace and request IDs only")
    args = parser.parse_args()
    try:
        identity = check_source_pin(args.source_commit)
        execute_study(identity, args.resume)
    except (ResearchError, RuntimeError, OSError, KeyError, ValueError, TypeError, UnicodeError, zipfile.BadZipFile,
            subprocess.CalledProcessError) as exc:
        print("S046 stopped: " + str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
