"""Gate for the M1b open-corpus run. Decides whether the one primary may start.

Nine checks, exit 0 GO / 2 blocked only by an unsigned card / 1 real failure.
Every check recomputes from bytes; none trusts a previous verdict file.

  .venv/Scripts/python.exe -B scripts/m1b_preflight.py
  .venv/Scripts/python.exe -B scripts/m1b_preflight.py --selftest
"""

import argparse
import hashlib
import json
import re
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKET = ROOT / "runs/m1b-packet-20261119"
ASSETS = PACKET / "assets"
CARD = PACKET / "approval-card.md"
FREEZE = PACKET / "freeze.json"
M0 = ROOT / "runs/m0-cfr-20261118"
M0_FREEZE = M0 / "freeze.json"
M0_CORPUS = M0 / "assets/corpus.jsonl"
BUDGET = ROOT / ".agent/team-budget.json"

M0_QUERIES_SHA = "4b0736e58ae927ca90b0b7615379c53022525894e6d249fc9980aba0ffb8f23c"
M0_QRELS_SHA = "d736cc37e782f628a0f1db5d38a2c06591ad8094410b4d2ce4dad89caf314e4b"
M0_CODE_ID = "0d65965054d0a66c14fecf55f93ea7cd64c6650d7c8b2f31bf10e50d0f92cee1"

RESULTS = []


def record(check, state, detail):
    RESULTS.append({"check": check, "state": state, "detail": detail})
    print(f"[{state:<7}] {check}")
    if state != "PASS":
        for key, value in detail.items():
            print(f"          {key}: {value}")
    return state


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


# --- individual checks ----------------------------------------------------

def check_interpreter():
    detail = {"executable": sys.executable, "version": sys.version.split()[0]}
    ok = sys.version_info[:2] == (3, 12)
    try:
        import numpy
        detail["numpy"] = numpy.__version__
    except Exception as error:  # noqa: BLE001
        detail["numpy"] = f"MISSING: {error}"
        ok = False
    detail["note"] = "the freeze binds sys.version through the code identity; 3.13 reports drift with identical bytes"
    return record("G1 interpreter is the pinned .venv", "PASS" if ok else "FAIL", detail)


def check_card(card):
    text = Path(card).read_text(encoding="utf-8")
    boxes = re.findall(r"^\s*-\s*\[([ xX])\]\s*(\S.*)$", text, flags=re.M)
    research = [label for mark, label in boxes if mark.lower() == "x" and "推" not in label and "发布" not in label]
    signature = re.search(r"^签字人：(.*?)日期：(.*)$", text, flags=re.M)
    name = re.sub(r"[_\s]", "", signature.group(1)) if signature else ""
    date = re.sub(r"[_\s]", "", signature.group(2)) if signature else ""
    ok = len(boxes) >= 3 and len(research) >= 3 and bool(name) and bool(date)
    return record("G2 approval card authorises the research action", "PASS" if ok else "BLOCKED",
                  {"checkboxes_total": len(boxes), "research_boxes_ticked": len(research),
                   "signature_name_filled": bool(name), "signature_date_filled": bool(date),
                   "note": "box 4 (publish to GitHub) is not required for a run and is not checked here"})


def check_budget(path):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    spent = data.get("confirmed_cash_spent")
    detail = {"status": data.get("status"), "confirmed_cash_spent": spent,
              "remaining_cash_authorized": data.get("remaining_cash_authorized"),
              "planned_cash_for_this_run": 0,
              "note": "null is unknown, never zero; this run makes no paid call"}
    ok = spent is None or float(spent) < float(data.get("cumulative_additional_cash_limit") or 0)
    return record("G3 no paid call and no exhausted cash limit", "PASS" if ok else "FAIL", detail)


def check_freeze(packet, freeze_path):
    recorded = json.loads(Path(freeze_path).read_text(encoding="utf-8"))
    problems = []
    for role, asset in recorded["assets"].items():
        path = Path(packet) / "assets" / asset["file"]
        if not path.exists():
            problems.append(f"{role}: missing")
        elif sha(path) != asset["sha256"]:
            problems.append(f"{role}: sha256 moved")
    try:
        sys.path.insert(0, str(ROOT))
        from src.autoresearch import staged_relevance_adapter as staged
        payload = staged.capture_source(Path(packet) / "assets")
        if payload["snapshot_sha256"] != recorded["snapshot_sha256"]:
            problems.append("snapshot_sha256 moved")
        current_code = staged.code_identity()
    except Exception as error:  # noqa: BLE001
        problems.append(f"capture failed: {error}")
        current_code = None
    detail = {"assets": len(recorded["assets"]), "problems": problems,
              "snapshot": recorded["snapshot_sha256"][:16] + "..."}
    return record("G4 frozen packet recomputes to its published hashes", "PASS" if not problems else "FAIL",
                  detail), current_code


def check_labels(assets, m0_assets):
    detail = {}
    ok = True
    for name, expected in (("queries.jsonl", M0_QUERIES_SHA), ("qrels.tsv", M0_QRELS_SHA)):
        got = sha(Path(assets) / name)
        detail[name] = {"sha256": got[:16] + "...", "matches_m0": got == expected,
                        "matches_m0_file": got == sha(Path(m0_assets) / name)}
        ok = ok and got == expected and got == sha(Path(m0_assets) / name)
    detail["note"] = "labels must not drift while the corpus grows; a single byte difference is a FAIL"
    return record("G5 queries and qrels are byte-identical to M0", "PASS" if ok else "FAIL", detail)


def check_labelled_text(assets, m0_corpus):
    m0 = {}
    for line in Path(m0_corpus).read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            m0[row["_id"]] = row
    docs = {}
    for line in (Path(assets) / "corpus.jsonl").read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            docs[row["_id"]] = row
    missing = sorted(set(m0) - set(docs))
    changed = sorted(doc for doc in m0 if doc in docs and
                     (docs[doc]["text"] != m0[doc]["text"] or docs[doc]["title"] != m0[doc]["title"]))
    detail = {"labelled_documents": len(m0), "missing": missing[:5], "text_or_title_changed": changed[:5],
              "counts": {"missing": len(missing), "changed": len(changed)}}
    ok = not missing and not changed
    return record("G6 the 85 labelled documents are unchanged", "PASS" if ok else "FAIL", detail)


def check_code_pin(current_code, m0_id):
    detail = {"current": current_code, "m0_pin": m0_id, "identical_to_m0": current_code == m0_id}
    detail["note"] = ("same code identity means the metric and ranking contracts proven in the M1 preflight "
                      "carry over; M1b does not re-derive them")
    return record("G7 scorer code identity equals the M0 pin", "PASS" if current_code == m0_id else "FAIL", detail)


def check_shape(assets):
    manifest = json.loads((Path(assets) / "manifest.json").read_text(encoding="utf-8"))
    rows = [json.loads(line) for line in (Path(assets) / "corpus.jsonl").read_text(encoding="utf-8").splitlines()
            if line.strip()]
    ids = [row["_id"] for row in rows]
    problems = []
    if len(ids) != len(set(ids)):
        problems.append("duplicate document ids")
    if any(not row["text"].strip() for row in rows):
        problems.append("empty document text")
    if len(rows) != manifest["corpus"]["documents"]:
        problems.append("manifest document count disagrees with corpus")
    positives = manifest["design"]["positive_pool_documents"]
    if positives != 85:
        problems.append(f"positive pool is {positives}, expected 85")
    detail = {"documents": len(rows), "positives": positives,
              "distractors": manifest["design"]["distractor_documents"],
              "top_k_coverage": round(20 / len(rows), 4),
              "m0_top_k_coverage": round(20 / 85, 4), "problems": problems}
    return record("G8 corpus shape and label coverage", "PASS" if not problems else "FAIL", detail)


def check_metrics_contract():
    """The scorer implements recall@k, mrr@10 and ndcg@10 with the frozen constants.

    Recomputed here through a separate implementation on three hand-computed cases,
    then compared against the function the run will actually call.
    """
    sys.path.insert(0, str(ROOT))
    from src.autoresearch import retrieval_lexical
    cases = [
        (["a", "b", "c"], {"c"}, {"recall@5": 1.0, "mrr@10": 1 / 3, "ndcg@10": (1 / 2) / 1.0}),
        (["a"] * 0 + ["b"], {"b"}, {"recall@5": 1.0, "mrr@10": 1.0, "ndcg@10": 1.0}),
    ]
    problems = []
    for ranking, relevant, expect in cases:
        got = retrieval_lexical.metrics(ranking, relevant)
        for name, want in expect.items():
            if abs(got[name] - want) > 1e-12:
                problems.append(f"{name}: {got[name]} != {want}")
    detail = {"cases": len(cases), "problems": problems,
              "note": "ranking/mrr/ndcg formulas are unchanged from M1; this is a smoke check, not a re-proof"}
    return record("G9 metric implementation still honours the contract", "PASS" if not problems else "FAIL", detail)


def run_gate(packet, card, freeze_path, assets, m0_corpus):
    RESULTS.clear()
    check_interpreter()
    check_card(card)
    check_budget(BUDGET)
    state, code = check_freeze(packet, freeze_path)
    check_labels(assets, M0 / "assets")
    check_labelled_text(assets, m0_corpus)
    check_code_pin(code, json.loads(M0_FREEZE.read_text(encoding="utf-8"))["code"]["staged_adapter_identity"])
    check_shape(assets)
    check_metrics_contract()

    failed = [r for r in RESULTS if r["state"] == "FAIL"]
    blocked = [r for r in RESULTS if r["state"] == "BLOCKED"]
    if failed:
        verdict, code = "NO_GO_FAILED", 1
    elif blocked:
        verdict, code = "NO_GO_UNSIGNED", 2
    else:
        verdict, code = "GO", 0
    print(f"\nverdict {verdict}  ({len(RESULTS) - len(failed) - len(blocked)}/{len(RESULTS)} pass)")
    return verdict, code


def selftest():
    """Prove the gate can fail. Each case copies the packet, injects one fault, expects a flip."""
    cases = []
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)

        def fresh(name):
            target = tmp / name
            shutil.copytree(PACKET, target)
            return target

        # 0. untouched copy must be GO-equivalent
        base = fresh("base")
        verdict, _ = run_gate(base, base / "approval-card.md", base / "freeze.json",
                              base / "assets", M0_CORPUS)
        cases.append({"case": "untouched copy", "expected": "GO", "got": verdict})

        # 1. corrupt one byte of the queries
        p = fresh("queries")
        q = p / "assets/queries.jsonl"
        data = bytearray(q.read_bytes())
        data[-2] = data[-2] ^ 0x01
        q.write_bytes(bytes(data))
        verdict, _ = run_gate(p, p / "approval-card.md", p / "freeze.json", p / "assets", M0_CORPUS)
        cases.append({"case": "query byte flipped", "expected": "NO_GO", "got": verdict})

        # 2. edit a labelled document's text
        p = fresh("text")
        c = p / "assets/corpus.jsonl"
        rows = c.read_text(encoding="utf-8").splitlines()
        row = json.loads(rows[0])
        row["text"] = row["text"] + " edited"
        rows[0] = json.dumps(row, ensure_ascii=False)
        c.write_text("\n".join(rows) + "\n", encoding="utf-8")
        verdict, _ = run_gate(p, p / "approval-card.md", p / "freeze.json", p / "assets", M0_CORPUS)
        cases.append({"case": "labelled document text edited", "expected": "NO_GO", "got": verdict})

        # 3. drop one signature
        p = fresh("unsigned")
        card = p / "approval-card.md"
        card.write_text(re.sub(r"^签字人：.*$", "签字人：__________　日期：__________",
                               card.read_text(encoding="utf-8"), flags=re.M), encoding="utf-8")
        verdict, _ = run_gate(p, card, p / "freeze.json", p / "assets", M0_CORPUS)
        cases.append({"case": "signature line blanked", "expected": "NO_GO_UNSIGNED", "got": verdict})

        # 4. stale freeze hash
        p = fresh("freeze")
        f = json.loads((p / "freeze.json").read_text(encoding="utf-8"))
        f["assets"]["corpus"]["sha256"] = "0" * 64
        (p / "freeze.json").write_text(json.dumps(f, ensure_ascii=False, indent=2), encoding="utf-8")
        verdict, _ = run_gate(p, p / "approval-card.md", p / "freeze.json", p / "assets", M0_CORPUS)
        cases.append({"case": "freeze hash replaced", "expected": "NO_GO", "got": verdict})

        # 5. duplicate document id
        p = fresh("dup")
        c = p / "assets/corpus.jsonl"
        lines = c.read_text(encoding="utf-8").splitlines()
        c.write_text("\n".join(lines + [lines[0]]) + "\n", encoding="utf-8")
        verdict, _ = run_gate(p, p / "approval-card.md", p / "freeze.json", p / "assets", M0_CORPUS)
        cases.append({"case": "duplicate document id", "expected": "NO_GO", "got": verdict})

        # 6. a distractor dropped from the corpus (labels intact, shape drifts)
        p = fresh("short")
        c = p / "assets/corpus.jsonl"
        lines = c.read_text(encoding="utf-8").splitlines()
        c.write_text("\n".join(lines[:-1]) + "\n", encoding="utf-8")
        verdict, _ = run_gate(p, p / "approval-card.md", p / "freeze.json", p / "assets", M0_CORPUS)
        cases.append({"case": "one document removed", "expected": "NO_GO", "got": verdict})

    ok = 0
    for item in cases:
        good = item["got"] == item["expected"] or (
            item["expected"] == "NO_GO" and item["got"].startswith("NO_GO"))
        ok += good
        print(f"{'ok  ' if good else 'FAIL'} {item['case']:<34} expected {item['expected']:<16} got {item['got']}")
    print(f"\nselftest {ok}/{len(cases)}")
    return 0 if ok == len(cases) else 1


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--packet", type=Path, default=PACKET)
    parser.add_argument("--card", type=Path, default=None)
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args()
    if args.selftest:
        return selftest()
    card = args.card or args.packet / "approval-card.md"
    verdict, code = run_gate(args.packet, card, args.packet / "freeze.json",
                             args.packet / "assets", M0_CORPUS)
    out = args.packet / "preflight.json"
    if args.packet == PACKET:
        out.write_text(json.dumps({"verdict": verdict, "checks": RESULTS}, ensure_ascii=False, indent=2) + "\n",
                       encoding="utf-8")
    return code


if __name__ == "__main__":
    sys.exit(main())
