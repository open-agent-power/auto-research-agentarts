"""Analysis of the M1b primary: pre-registered verdict plus every per-query detail.

Reads only the captured artefacts (primary-result.json, M0 primary-result.json) and the
frozen qrels. No research action, no model call. Every arm mean and paired delta is
recomputed in Decimal from per_query_metrics and must match the recorded summary.

  .venv/Scripts/python.exe -B scripts/analyze_m1b.py
"""

import json
import math
from decimal import Decimal, getcontext
from pathlib import Path

getcontext().prec = 40

ROOT = Path(__file__).resolve().parents[1]
M1B = ROOT / "runs/m1b-cfr-20261119/primary-result.json"
M1 = ROOT / "runs/m1-cfr-20261119/primary-result.json"
QRELS = ROOT / "runs/m0-cfr-20261118/assets/qrels.tsv"
OUT = ROOT / "runs/m1b-cfr-20261119/analysis.json"

ARMS = ("bm25", "tfidf_cosine")
METRICS = ("recall@5", "recall@10", "recall@20", "mrr@10", "ndcg@10")


def load_qrels():
    labels = {}
    for line in QRELS.read_text(encoding="utf-8").splitlines()[1:]:
        if line.strip():
            query_id, doc_id, score = line.split("\t")
            if int(score) > 0:
                labels.setdefault(query_id, set()).add(doc_id)
    return labels


def recall_at(ranking, relevant, k):
    return len(set(ranking[:k]) & relevant) / len(relevant) if relevant else 0.0


def mrr_at(ranking, relevant, k):
    for index, doc in enumerate(ranking[:k]):
        if doc in relevant:
            return 1.0 / (index + 1)
    return 0.0


def ndcg_at(ranking, relevant, k):
    dcg = sum(1 / math.log2(i + 2) for i, doc in enumerate(ranking[:k]) if doc in relevant)
    ideal = sum(1 / math.log2(i + 2) for i in range(min(k, len(relevant))))
    return dcg / ideal if ideal else 0.0


def rank_of_positive(ranking, relevant):
    return next((i + 1 for i, doc in enumerate(ranking) if doc in relevant), None)


def sign_test(wins, losses):
    """Two-sided exact binomial on the discordant pairs, p0 = 0.5."""
    n = wins + losses
    if n == 0:
        return {"n_discordant": 0, "p_two_sided": None}
    k = min(wins, losses)
    tail = sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n
    return {"n_discordant": n, "p_two_sided": min(1.0, 2 * tail),
            "note": "descriptive only; n is tiny and the pairs are not independent draws"}


def main():
    data = json.loads(M1B.read_text(encoding="utf-8"))["result"]
    old = json.loads(M1.read_text(encoding="utf-8"))["result"]
    qrels = load_qrels()

    rows = data["per_query_metrics"]
    new_rankings = {(r["split"], r["method"], r["query_id"]): r["ranking"] for r in data["rankings"]}
    old_rankings = {(r["split"], r["method"], r["query_id"]): r["ranking"] for r in old["rankings"]}

    # --- guard 1: Decimal recompute of both arm means and paired deltas ----
    problems = []
    for split, block in data["paired_summary"]["splits"].items():
        subset = [r for r in rows if r["split"] == split]
        for method in ARMS:
            arm_rows = [r for r in subset if r["method"] == method]
            for name in METRICS:
                mean = sum(Decimal(str(r["metrics"][name])) for r in arm_rows) / Decimal(len(arm_rows))
                recorded = Decimal(str(block["arms"][method]["metrics"][name]))
                if abs(mean - recorded) > Decimal("1e-15"):
                    problems.append(f"{split}/{method}/{name}: {mean} != {recorded}")
        by_query = {}
        for row in subset:
            by_query.setdefault(row["query_id"], {})[row["method"]] = row["metrics"]
        for name in METRICS:
            deltas = [Decimal(str(v["tfidf_cosine"][name])) - Decimal(str(v["bm25"][name]))
                      for v in by_query.values()]
            mean = sum(deltas) / Decimal(len(deltas))
            cell = block["paired_candidate_minus_baseline"][name]
            wins = sum(1 for d in deltas if d > Decimal("1e-15"))
            losses = sum(1 for d in deltas if d < Decimal("-1e-15"))
            if abs(mean - Decimal(str(cell["mean"]))) > Decimal("1e-15") or \
                    (wins, losses) != (cell["wins"], cell["losses"]):
                problems.append(f"{split}/{name}: delta {mean} vs {cell}")
    if problems:
        print("ABORT: Decimal recompute disagrees with the recorded summary")
        for item in problems[:5]:
            print(" ", item)
        return 1

    # --- guard 2: an independent metric implementation matches the scorer ---
    mismatches = 0
    for row in rows:
        ranking, relevant = new_rankings[(row["split"], row["method"], row["query_id"])], qrels[row["query_id"]]
        mine = {"recall@5": recall_at(ranking, relevant, 5),
                "recall@10": recall_at(ranking, relevant, 10),
                "recall@20": recall_at(ranking, relevant, 20),
                "mrr@10": mrr_at(ranking, relevant, 10),
                "ndcg@10": ndcg_at(ranking, relevant, 10)}
        for name, value in mine.items():
            if abs(value - row["metrics"][name]) > 1e-12:
                mismatches += 1
    if mismatches:
        print(f"ABORT: {mismatches} recomputed metrics disagree with the scorer")
        return 1

    # --- per-query detail --------------------------------------------------
    per_query = []
    for split in ("dev", "validation"):
        qids = sorted({r["query_id"] for r in rows if r["split"] == split})
        for qid in qids:
            entry = {"split": split, "query_id": qid, "arms": {}}
            for method in ARMS:
                key = (split, method, qid)
                entry["arms"][method] = {
                    "metrics": {k: v for k, v in rows_key(rows, key).items()},
                    "positive_rank_m1b": rank_of_positive(new_rankings[key], qrels[qid]),
                    "positive_rank_m1": rank_of_positive(old_rankings.get(key, []), qrels[qid])
                    if key in old_rankings else None,
                }
            entry["delta"] = {name: round(entry["arms"]["tfidf_cosine"]["metrics"][name] -
                                         entry["arms"]["bm25"]["metrics"][name], 12) for name in METRICS}
            per_query.append(entry)

    # --- cutoff curve on the new rankings ---------------------------------
    curve = {}
    for split in ("dev", "validation"):
        qids = sorted({r["query_id"] for r in rows if r["split"] == split})
        block = {"recall": {}, "mrr": {}}
        for k in (1, 2, 3, 5, 10, 15, 20):
            bm = sum(recall_at(new_rankings[(split, "bm25", q)], qrels[q], k) for q in qids) / len(qids)
            tf = sum(recall_at(new_rankings[(split, "tfidf_cosine", q)], qrels[q], k) for q in qids) / len(qids)
            block["recall"][f"recall@{k}"] = {"bm25": round(bm, 6), "tfidf_cosine": round(tf, 6)}
        for k in (1, 5, 10, 20):
            bm = sum(mrr_at(new_rankings[(split, "bm25", q)], qrels[q], k) for q in qids) / len(qids)
            tf = sum(mrr_at(new_rankings[(split, "tfidf_cosine", q)], qrels[q], k) for q in qids) / len(qids)
            block["mrr"][f"mrr@{k}"] = {"bm25": round(bm, 6), "tfidf_cosine": round(tf, 6)}
        curve[split] = block

    # --- pre-registered decision rules ------------------------------------
    validation = data["paired_summary"]["splits"]["validation"]["paired_candidate_minus_baseline"]
    d_recall20 = validation["recall@20"]["mean"]
    d_mrr10 = validation["mrr@10"]["mean"]
    all_zero = all(abs(cell["mean"]) <= 1e-12 for cell in validation.values())
    if all_zero:
        verdict, rule = "D3", "both endpoints flat on every query"
    elif d_recall20 > 0 and d_mrr10 < 0:
        verdict, rule = "D1", "recall@20 up with mrr@10 down"
    elif d_recall20 >= 0 and d_mrr10 >= 0:
        verdict, rule = "D2", "no trade-off observed on this packet"
    else:
        verdict, rule = "D4", "recall@20 did not increase; direction reported as measured"

    tests = {name: sign_test(validation[name]["wins"], validation[name]["losses"]) for name in METRICS}

    analysis = {
        "run": "m1b-cfr-20261119",
        "packet": "m1b-cfr-open-corpus-20261119",
        "documents": data["scope"]["document_count"],
        "verdict": {"rule": verdict, "reason": rule,
                    "delta_recall20": d_recall20, "delta_mrr10": d_mrr10,
                    "note": "rules were fixed in m1b-protocol-20261119.md before the run"},
        "guards": {"decimal_recompute": "pass", "independent_metrics": "pass",
                   "panels": "32 queries x 2 arms", "qrel_pairs": 32},
        "validation_vs_m1": {
            name: {"m1_packet": old["paired_summary"]["splits"]["validation"]
                   ["paired_candidate_minus_baseline"][name],
                   "m1b_packet": validation[name]} for name in METRICS},
        "sign_tests_validation": tests,
        "cutoff_curve": curve,
        "per_query": per_query,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(analysis, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"guards pass; verdict {verdict} ({rule})")
    print(f"validation delta recall@20 {d_recall20:+.6f}  mrr@10 {d_mrr10:+.6f}")
    for name, test in tests.items():
        print(f"  sign test {name:<10} wins/losses {validation[name]['wins']}/{validation[name]['losses']}  "
              f"p={test['p_two_sided']:.4f}" if test["p_two_sided"] is not None else f"  {name}: no discordant pairs")
    print("\nper-query rank of the positive (validation):")
    for item in per_query:
        if item["split"] != "validation":
            continue
        bm = item["arms"]["bm25"]
        tf = item["arms"]["tfidf_cosine"]
        moved = f"{bm['positive_rank_m1']}->{bm['positive_rank_m1b']}" if bm["positive_rank_m1"] else "?"
        moved_tf = f"{tf['positive_rank_m1']}->{tf['positive_rank_m1b']}" if tf["positive_rank_m1"] else "?"
        print(f"  {item['query_id']:<10} bm25 rank {moved:<9} tfidf rank {moved_tf:<9} "
              f"d_mrr {item['delta']['mrr@10']:+.4f} d_r5 {item['delta']['recall@5']:+.3f} "
              f"d_r20 {item['delta']['recall@20']:+.3f}")
    print(f"\nwrote {OUT.relative_to(ROOT)}")
    return 0


def rows_key(rows, key):
    split, method, qid = key
    for row in rows:
        if (row["split"], row["method"], row["query_id"]) == (split, method, qid):
            return row["metrics"]
    raise KeyError(key)


if __name__ == "__main__":
    raise SystemExit(main())
