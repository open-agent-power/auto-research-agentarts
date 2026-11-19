"""Pre-execution gate for the single M1 primary run over the frozen M0 packet.

Read-only, and deliberately zero research actions: nothing here ranks the frozen
corpus. The gate answers three questions before a run may start.

  1. Is a run permitted at all?      approval card signed, budget headroom intact
  2. Are the bytes and the scorer the frozen ones?
                                     freeze.py --check, independent content
                                     cross-check, independent code-pin chain
  3. Does the scorer compute what the protocol says?
                                     metrics vs an independent reference on
                                     fixtures whose answers were computed by hand,
                                     plus ranking tie-break / cutoff / exclude

  .venv/Scripts/python.exe -B scripts/m1_preflight.py
  .venv/Scripts/python.exe -B scripts/m1_preflight.py --declared-research-actions 0

Exit 0 = GO, 2 = blocked only by the unsigned approval card (everything else
green), 1 = a real check failed and the run must not start.
"""

import argparse
import datetime
import hashlib
import importlib.metadata
import json
import math
import platform
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKET = ROOT / "runs/m0-cfr-20261118"
CARD = PACKET / "approval-card.md"
FREEZE = PACKET / "freeze.json"
BUDGET = ROOT / ".agent/team-budget.json"
VENV_PY = ROOT / ".venv/Scripts/python.exe"
CROSSCHECK = ROOT / "scripts/crosscheck_m0_packet.py"
OUT = ROOT / "runs/m1-preflight-20261119"

RESEARCH_ACTION_LIMIT = 2  # approval card section 6 / protocol budget
TOLERANCE = 1e-12

CHECKS = []


def record(name, state, detail):
    CHECKS.append({"check": name, "state": state, "detail": detail})
    print(f"[{state:<7}] {name}: {json.dumps(detail, ensure_ascii=False)[:300]}")
    return state == "PASS"


def sha256(raw):
    return hashlib.sha256(raw).hexdigest()


# --------------------------------------------------------------------------- 1
def check_interpreter():
    exe = Path(sys.executable).resolve()
    want = VENV_PY.resolve()
    try:
        import numpy  # noqa: F401
        numpy_version = importlib.metadata.version("numpy")
    except Exception as exc:  # noqa: BLE001 - any import failure is the finding
        numpy_version = f"unavailable ({type(exc).__name__})"
    ok = exe == want and sys.version_info[:2] == (3, 12) and not numpy_version.startswith("unavailable")
    record("P0 interpreter is the pinned .venv", "PASS" if ok else "FAIL",
           {"executable": str(exe), "expected": str(want), "python": platform.python_version(),
            "numpy": numpy_version,
            "why": "staged_adapter_identity folds sys.version and pypdf into one hash, so the "
                   "interpreter is part of the freeze"})


def check_approval():
    """Research authorisation and publication authorisation are separate questions.

    Boxes 1-3 authorise the run; box 4 authorises pushing publishable material to
    GitHub. A run does not need box 4, so requiring it would block M1 for an
    unrelated reason -- it is reported instead of demanded.
    """
    text = CARD.read_text(encoding="utf-8")
    boxes = re.findall(r"^\s*-\s*\[([ xX])\]\s*(\S.*)$", text, flags=re.M)
    marks = [mark.lower() == "x" for mark, _ in boxes]
    research_ok = len(marks) == 4 and all(marks[:3])
    signature = re.search(r"^签字人：(.*?)日期：(.*)$", text, flags=re.M)
    name = re.sub(r"[_\s]", "", signature.group(1)) if signature else ""
    date = re.sub(r"[_\s]", "", signature.group(2)) if signature else ""
    pending = "待签字" in text
    ok = research_ok and bool(name) and bool(date) and not pending
    record("P1 approval card authorises the run", "PASS" if ok else "BLOCKED",
           {"boxes_total": len(boxes), "research_boxes_ticked": sum(marks[:3]),
            "publication_box_ticked": marks[3] if len(marks) == 4 else None,
            "signature_name_filled": bool(name), "signature_date_filled": bool(date),
            "status_line_says_pending": pending,
            "publication_note": "box 4 is push authorisation only; when unticked no material may be pushed",
            "note": "an unsigned card is a hard stop for M1; nothing below overrides it"})


def check_budget(declared_actions, declared_models, declared_fits):
    data = json.loads(BUDGET.read_text(encoding="utf-8"))
    limit = data.get("cumulative_additional_cash_limit")
    spent = data.get("confirmed_cash_spent")
    over = isinstance(spent, (int, float)) and isinstance(limit, (int, float)) and spent > limit
    actions_ok = declared_actions <= RESEARCH_ACTION_LIMIT
    ok = (not over) and isinstance(limit, (int, float)) and actions_ok
    record("P2 budget headroom", "PASS" if ok else "FAIL",
           {"cash_limit_cny": limit, "confirmed_cash_spent": spent,
            "cash_settlement": "unknown" if spent is None else "recorded",
            "ledger_status": data.get("status"),
            "research_actions_declared": f"{declared_actions}/{RESEARCH_ACTION_LIMIT}",
            "model_calls_declared": declared_models, "native_fits_declared": declared_fits,
            "note": "declared values are operator statements; this gate does not meter them, "
                    "and platform-side usage remains unknown"})


# --------------------------------------------------------------------------- 2
def check_freeze():
    proc = subprocess.run([str(VENV_PY), "-B", str(PACKET / "freeze.py"), "--check"],
                          cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8", errors="replace")
    ok = proc.returncode == 0 and "FROZEN PACKET INTACT" in proc.stdout
    record("P3 freeze.py --check under .venv", "PASS" if ok else "FAIL",
           {"exit": proc.returncode, "stdout": proc.stdout.strip().splitlines()[:4],
            "stderr": proc.stderr.strip().splitlines()[-3:]})


def check_crosscheck():
    target = OUT / "crosscheck-result.json"
    proc = subprocess.run([str(VENV_PY), "-B", str(CROSSCHECK), "--out", str(target)],
                          cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8", errors="replace")
    ok = proc.returncode == 0 and target.exists()
    detail = {"exit": proc.returncode}
    if target.exists():
        data = json.loads(target.read_text(encoding="utf-8"))
        detail.update({"checks_total": data["checks_total"], "checks_failed": data["checks_failed"],
                       "snapshot_recomputed_matches_published":
                           data["snapshot_recomputed"] == data["snapshot_published"]})
        ok = ok and not data["checks_failed"]
    else:
        detail["stderr"] = proc.stderr.strip().splitlines()[-3:]
    record("P4 independent content cross-check", "PASS" if ok else "FAIL", detail)


def _tabular_identity(version_string, pypdf_version):
    """Independent re-statement of tabular_source.extraction_identity."""
    src = ROOT / "src/autoresearch"
    order = ["tabular_source.py", "chemotopo_data.py", "c01.py", "archive_inventory.py",
             "contracts.py", "knowledge_sources.py"]
    digest = hashlib.sha256((src / order[0]).read_bytes())
    for name in order[1:]:
        digest.update((src / name).read_bytes())
    digest.update(version_string.encode("utf-8"))
    digest.update(pypdf_version.encode("utf-8"))
    return digest.hexdigest()


def check_code_pin():
    try:
        pypdf_version = importlib.metadata.version("pypdf")
    except importlib.metadata.PackageNotFoundError:
        pypdf_version = "unavailable"
    src = ROOT / "src/autoresearch"

    def chain(tabular):
        reader = sha256((src / "source_evidence_adapter.py").read_bytes() + tabular.encode("ascii"))
        base = sha256((src / "relevance_retrieval_adapter.py").read_bytes()
                      + (src / "retrieval_lexical.py").read_bytes() + reader.encode("ascii"))
        return sha256((src / "staged_relevance_adapter.py").read_bytes() + base.encode("ascii")), base, reader

    freeze = json.loads(FREEZE.read_text(encoding="utf-8"))
    published = freeze["code"]["staged_adapter_identity"]
    tabular = _tabular_identity(sys.version, pypdf_version)
    staged, base, reader = chain(tabular)
    ok = staged == published

    # Same files, one character different in sys.version: shows the pin is
    # environment-bound without any asset moving.
    faked, _, _ = chain(_tabular_identity(sys.version + "~probe", pypdf_version))
    record("P5 code pin recomputed from bytes", "PASS" if ok else "FAIL",
           {"published": published, "recomputed": staged, "base": base, "reader": reader,
            "tabular": tabular, "pypdf": pypdf_version,
            "coverage": "staged_scorer + base_adapter + retrieval_lexical + source_evidence_adapter "
                        "+ tabular_source chain (5 module files + sys.version + pypdf version)",
            "environment_bound": faked != staged,
            "probe_detail": "changing only the sys.version string changes the pin to "
                            f"{faked[:16]}... with every asset untouched"})


# --------------------------------------------------------------------------- 3
def ref_metrics(ranking, relevant):
    """Second implementation: explicit ideal ranking, independent of the source code."""
    rel = set(relevant)
    result = {}
    for k in (5, 10, 20):
        hits = sum(1 for doc in ranking[:k] if doc in rel)
        result[f"recall@{k}"] = hits / len(rel) if rel else 0.0
    result["mrr@10"] = next((1.0 / rank for rank, doc in enumerate(ranking[:10], start=1) if doc in rel), 0.0)
    observed = [1.0 / math.log2(rank + 1)
                for rank, doc in enumerate(ranking[:10], start=1) if doc in rel]
    ideal_gains = [1.0 / math.log2(rank + 1) for rank in range(1, min(10, len(rel)) + 1)]
    result["ndcg@10"] = sum(observed) / sum(ideal_gains) if ideal_gains else 0.0
    return result


METRIC_FIXTURES = [
    {"name": "single positive at rank 2",
     "ranking": ["d1", "d2", "d3"], "relevant": ["d2"],
     "expect": {"recall@5": 1.0, "recall@10": 1.0, "recall@20": 1.0, "mrr@10": 0.5,
                "ndcg@10": 0.6309297535714574}},
    {"name": "two positives at ranks 1 and 3",
     "ranking": ["d1", "d2", "d3"], "relevant": ["d1", "d3"],
     "expect": {"recall@5": 1.0, "recall@10": 1.0, "recall@20": 1.0, "mrr@10": 1.0,
                "ndcg@10": 0.9197207891481877}},
    {"name": "positive at rank 14: inside 20, outside 10",
     "ranking": [f"d{i:02d}" for i in range(1, 21)], "relevant": ["d14"],
     "expect": {"recall@5": 0.0, "recall@10": 0.0, "recall@20": 1.0, "mrr@10": 0.0, "ndcg@10": 0.0}},
    {"name": "positive outside the top 20",
     "ranking": [f"d{i:02d}" for i in range(1, 21)], "relevant": ["d21"],
     "expect": {"recall@5": 0.0, "recall@10": 0.0, "recall@20": 0.0, "mrr@10": 0.0, "ndcg@10": 0.0}},
    {"name": "single-document corpus",
     "ranking": ["d1"], "relevant": ["d1"],
     "expect": {"recall@5": 1.0, "recall@10": 1.0, "recall@20": 1.0, "mrr@10": 1.0, "ndcg@10": 1.0}},
    {"name": "12 positives: nDCG ideal capped at 10, recall denominator 12",
     "ranking": [f"d{i:02d}" for i in range(1, 21)], "relevant": [f"d{i:02d}" for i in range(1, 13)],
     "expect": {"recall@5": 5 / 12, "recall@10": 10 / 12, "recall@20": 1.0, "mrr@10": 1.0,
                "ndcg@10": 1.0}},
    {"name": "no positive declared (edge the packet never exercises)",
     "ranking": ["d1", "d2"], "relevant": [],
     "expect": {"recall@5": 0.0, "recall@10": 0.0, "recall@20": 0.0, "mrr@10": 0.0, "ndcg@10": 0.0}},
]


def _close(left, right):
    return abs(left - right) <= TOLERANCE


def check_metrics(lexical):
    failures, rows = [], []
    for fixture in METRIC_FIXTURES:
        got = lexical.metrics(list(fixture["ranking"]), list(fixture["relevant"]))
        ref = ref_metrics(fixture["ranking"], fixture["relevant"])
        hand_ok = all(name in got and _close(got[name], value) for name, value in fixture["expect"].items())
        ref_ok = all(name in got and _close(got[name], value) for name, value in ref.items())
        missing_extra = set(got) ^ set(lexical.METRICS)
        rows.append({"fixture": fixture["name"], "matches_hand_computed": hand_ok,
                     "matches_reference": ref_ok, "missing_or_extra_keys": sorted(missing_extra)})
        if not (hand_ok and ref_ok and not missing_extra):
            failures.append({"fixture": fixture["name"], "got": got, "hand": fixture["expect"], "ref": ref})
    record("P6 metric contract vs hand-computed fixtures", "PASS" if not failures else "FAIL",
           {"fixtures": len(METRIC_FIXTURES), "failures": failures, "rows": rows})


def check_ranking(lexical, adapter):
    """Tie-break, top-k cutoff and exclude-before-cutoff, on synthetic documents only."""
    problems = []
    docs = {f"d{i:02d}": {"title": "", "text": f"common token{i}"} for i in range(25)}
    index = lexical.build_index(docs)
    ranked = adapter.retrieve("common", index, "bm25", exclude_doc_id="\x00none")
    if len(ranked) != 20:
        problems.append({"rule": "top_k=20", "got": len(ranked)})
    if ranked != [f"d{i:02d}" for i in range(20)]:
        problems.append({"rule": "tie-break doc_id_ascending", "got": ranked[:6]})
    excluded = adapter.retrieve("common", index, "bm25", exclude_doc_id="d00")
    if excluded != [f"d{i:02d}" for i in range(1, 21)]:
        problems.append({"rule": "exclude before cutoff keeps 20 hits", "got": excluded[:6],
                         "length": len(excluded)})

    varied = {
        "d-01": {"title": "Alpha duty", "text": "disclose alpha duty clearly"},
        "d-02": {"title": "Beta", "text": "beta penalty schedule"},
        "d-03": {"title": "Gamma", "text": "gamma alpha reference"},
        "d-04": {"title": "Delta", "text": "unrelated text about delta"},
    }
    varied_index = lexical.build_index(varied)
    for method in ("bm25", "tfidf_cosine"):
        mine = lexical.retrieve("alpha duty", varied_index, method)
        theirs = adapter.retrieve("alpha duty", varied_index, method, exclude_doc_id="\x00none")
        if mine != theirs:
            problems.append({"rule": f"module and adapter agree ({method})", "module": mine, "adapter": theirs})

    empty = adapter.retrieve("", lexical.build_index(varied), "bm25", exclude_doc_id="\x00none")
    record("P7 ranking contract on synthetic documents", "PASS" if not problems else "FAIL",
           {"problems": problems,
            "empty_query_returns": empty,
            "empty_query_note": "an all-stopword query yields no candidates rather than an error; "
                                "not exercised by the frozen queries"})


def check_constants(lexical, adapter):
    freeze = json.loads(FREEZE.read_text(encoding="utf-8"))
    spec = json.loads((PACKET / "assets/spec.json").read_text(encoding="utf-8"))
    published = freeze["comparison"]
    problems = []
    if json.loads(json.dumps(adapter.COMPARISON, sort_keys=True)) != json.loads(json.dumps(published, sort_keys=True)):
        problems.append({"where": "adapter.COMPARISON", "got": adapter.COMPARISON, "freeze": published})
    if list(lexical.METRICS) != list(published["metrics"]):
        problems.append({"where": "retrieval_lexical.METRICS", "got": list(lexical.METRICS),
                         "freeze": published["metrics"]})
    if spec.get("comparison") != published:
        problems.append({"where": "spec.json comparison", "got": spec.get("comparison"), "freeze": published})
    record("P8 comparison constants agree in four places", "PASS" if not problems else "FAIL",
           {"problems": problems, "k1": published.get("k1"), "b": published.get("b"),
            "top_k": published.get("top_k"), "methods": [published.get("baseline"), published.get("candidate")]})


def check_id_namespaces():
    """Read-only fact about the frozen packet, no scoring."""
    assets = PACKET / "assets"
    queries = [json.loads(line)["_id"] for line in
               assets.joinpath("queries.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    docs = [json.loads(line)["_id"] for line in
            assets.joinpath("corpus.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    overlap = sorted(set(queries) & set(docs))
    record("P9 identical-ID exclusion is inert here", "INFO",
           {"query_ids": len(queries), "document_ids": len(docs), "overlap": overlap,
            "meaning": "ignore_identical_ids cannot change any ranking in this packet because the two "
                       "id namespaces are disjoint; the clause stays in the contract unexercised"})


# -------------------------------------------------------------------------- run
def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--declared-research-actions", type=int, default=0,
                        help="research tool actions already spent on this study (operator statement)")
    parser.add_argument("--declared-model-calls", type=int, default=0)
    parser.add_argument("--declared-native-fits", type=int, default=0)
    args = parser.parse_args(argv)

    started = datetime.datetime.now().astimezone()
    check_interpreter()
    check_approval()
    check_budget(args.declared_research_actions, args.declared_model_calls, args.declared_native_fits)
    check_freeze()
    check_crosscheck()
    check_code_pin()

    lexical = adapter = None
    try:
        sys.path.insert(0, str(ROOT))
        from src.autoresearch import relevance_retrieval_adapter, retrieval_lexical
        lexical, adapter = retrieval_lexical, relevance_retrieval_adapter
    except Exception as exc:  # noqa: BLE001
        record("P6-P8 scorer import", "FAIL", {"error": f"{type(exc).__name__}: {exc}"})
    if lexical is not None:
        check_metrics(lexical)
        check_ranking(lexical, adapter)
        check_constants(lexical, adapter)
        check_id_namespaces()

    failed = [c["check"] for c in CHECKS if c["state"] == "FAIL"]
    blocked = [c["check"] for c in CHECKS if c["state"] == "BLOCKED"]
    if failed:
        verdict, code = "NO_GO_FAILED", 1
    elif blocked:
        verdict, code = "NO_GO_UNSIGNED", 2
    else:
        verdict, code = "GO", 0

    result = {
        "gate": "m1-preflight",
        "packet": "m0-cfr-20261118",
        "started_local": started.isoformat(timespec="seconds"),
        "finished_local": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
        "verdict": verdict,
        "exit_code": code,
        "blocking": blocked,
        "failed": failed,
        "research_actions_consumed_by_this_gate": 0,
        "model_calls_by_this_gate": 0,
        "note": "synthetic fixtures and byte checks only; the frozen corpus is read for id/hash "
                "facts and never ranked",
        "checks": CHECKS,
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"\nverdict {verdict} (exit {code}); wrote {(OUT / 'result.json').relative_to(ROOT)}")
    return code


if __name__ == "__main__":
    sys.exit(main())
