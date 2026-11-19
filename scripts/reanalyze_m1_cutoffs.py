"""Post-hoc cutoff re-analysis of the captured M1 rankings. Spends no research action.

The M1 run stored the full top-20 ranking for both arms on all 32 queries, plus the
five metrics the protocol scored. recall@20 saturated at 1.0, so this script walks
the cutoffs that were not pre-registered: recall@1..20, mrr@1..20, ndcg@1..20.

It is **post-hoc and exploratory**. It cannot confirm the pre-registered question, and
the numbers must not be used to pick a new primary endpoint after the fact as if that
choice had been blind. What it can do is show where the variance actually is, so the
next pre-registration has a reason that is not "we saw the answer we wanted".

The metric implementation here is written from scratch and must reproduce all five
frozen metrics on all 64 per-query rows before any new cutoff is reported.

  .venv/Scripts/python.exe -B scripts/reanalyze_m1_cutoffs.py
"""

import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESULT = ROOT / "runs/m1-cfr-20261119/primary-result.json"
QRELS = ROOT / "runs/m0-cfr-20261118/assets/qrels.tsv"
OUT = ROOT / "runs/m1-reanalysis-20261119/cutoff-curve.json"

ARMS = ("bm25", "tfidf_cosine")
RECALL_K = (1, 2, 3, 5, 10, 15, 20)
MRR_K = (1, 2, 3, 5, 10, 20)
NDCG_K = (1, 3, 5, 10, 20)


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


def load_qrels():
    labels = {}
    lines = QRELS.read_text(encoding="utf-8").splitlines()
    for line in lines[1:]:
        if not line.strip():
            continue
        query_id, doc_id, score = line.split("\t")
        if int(score) > 0:
            labels.setdefault(query_id, set()).add(doc_id)
    return labels


def paired(rows):
    """rows: list of (query_id, baseline_value, candidate_value)"""
    deltas = [cand - base for _, base, cand in rows]
    wins = sum(1 for d in deltas if d > 1e-12)
    losses = sum(1 for d in deltas if d < -1e-12)
    return {"mean": sum(deltas) / len(deltas) if deltas else 0.0,
            "wins": wins, "ties": len(deltas) - wins - losses, "losses": losses,
            "n": len(deltas)}


def main():
    result = json.loads(RESULT.read_text(encoding="utf-8"))["result"]
    rankings = {(row["split"], row["method"], row["query_id"]): row["ranking"]
                for row in result["rankings"]}
    frozen = {(row["split"], row["method"], row["query_id"]): row
              for row in result["per_query_metrics"]}
    qrels = load_qrels()

    # --- guard 1: the ranking set is complete ------------------------------
    splits = result["scope"]["query_split_counts"]
    expected = sum(splits.values()) * len(ARMS)
    if len(rankings) != expected or len(frozen) != expected:
        print(f"ABORT: {len(rankings)} rankings / {len(frozen)} metric rows, expected {expected} each")
        return 1

    # --- guard 2: qrels used here match the ones the run recorded ----------
    for (split, method, qid), row in frozen.items():
        recorded = set(row["qrel_locator"]["document_ids"])
        if recorded != qrels.get(qid, set()):
            print(f"ABORT: qrels disagree for {qid}: {sorted(recorded)} vs {sorted(qrels.get(qid, set()))}")
            return 1

    # --- guard 3: independent implementation reproduces the frozen metrics --
    mismatches = []
    for key, row in frozen.items():
        _, method, qid = key
        ranking, relevant = rankings[key], qrels[qid]
        mine = {"recall@5": recall_at(ranking, relevant, 5),
                "recall@10": recall_at(ranking, relevant, 10),
                "recall@20": recall_at(ranking, relevant, 20),
                "mrr@10": mrr_at(ranking, relevant, 10),
                "ndcg@10": ndcg_at(ranking, relevant, 10)}
        for name, value in mine.items():
            if abs(value - row["metrics"][name]) > 1e-12:
                mismatches.append({"split": key[0], "method": method, "query_id": qid,
                                   "metric": name, "frozen": row["metrics"][name],
                                   "recomputed": value})
    if mismatches:
        print(f"ABORT: {len(mismatches)} frozen metrics not reproduced; first {mismatches[0]}")
        return 1

    # --- guard 4: hand-computed fixtures for the new cutoffs ---------------
    fixtures = [
        {"name": "positive at rank 1, single positive",
         "ranking": ["a", "b", "c"], "relevant": {"a"},
         "expect": {"recall@1": 1.0, "mrr@1": 1.0, "ndcg@1": 1.0}},
        {"name": "positive at rank 3, single positive",
         "ranking": ["a", "b", "c"], "relevant": {"c"},
         "expect": {"recall@1": 0.0, "recall@2": 0.0, "recall@3": 1.0,
                    "mrr@2": 0.0, "mrr@3": 1 / 3, "ndcg@3": 1 / math.log2(4)}},
        {"name": "two positives, one at rank 2 of a 2-deep ideal",
         "ranking": ["a", "b", "c", "d"], "relevant": {"b", "d"},
         "expect": {"recall@1": 0.0, "recall@2": 0.5, "recall@3": 0.5, "recall@20": 1.0,
                    "mrr@20": 0.5, "ndcg@2": (1 / math.log2(3)) / (1 + 1 / math.log2(3))}},
    ]
    for fixture in fixtures:
        for name, want in fixture["expect"].items():
            if name.startswith("recall@"):
                got = recall_at(fixture["ranking"], fixture["relevant"], int(name.split("@")[1]))
            elif name.startswith("mrr@"):
                got = mrr_at(fixture["ranking"], fixture["relevant"], int(name.split("@")[1]))
            else:
                got = ndcg_at(fixture["ranking"], fixture["relevant"], int(name.split("@")[1]))
            if abs(got - want) > 1e-12:
                print(f"ABORT: fixture {fixture['name']!r} {name}: {got} != {want}")
                return 1

    # --- the actual curves -------------------------------------------------
    curve = {"source": "runs/m1-cfr-20261119/primary-result.json",
             "rankings_sha256": result["rankings_before_scoring_sha256"],
             "status": "post_hoc_exploratory",
             "note": ("Cutoffs other than 5/10/20 were not pre-registered. These numbers locate the "
                      "variance that recall@20 hid; they do not confirm the M1 hypothesis and must not "
                      "be presented as a planned endpoint."),
             "guards": {"rankings": len(rankings), "frozen_metrics_reproduced": len(frozen) * 5,
                        "fixtures": len(fixtures)},
             "splits": {}}

    for split in ("dev", "validation"):
        block = {"recall": {}, "mrr": {}, "ndcg": {}, "positive_rank": {}}
        for k in RECALL_K:
            bm, tf, rows = 0.0, 0.0, []
            qids = sorted({q for (s, _, q) in rankings if s == split})
            for qid in qids:
                value = {m: recall_at(rankings[(split, m, qid)], qrels[qid], k) for m in ARMS}
                bm += value["bm25"]
                tf += value["tfidf_cosine"]
                rows.append((qid, value["bm25"], value["tfidf_cosine"]))
            block["recall"][f"recall@{k}"] = {"bm25": bm / len(qids), "tfidf_cosine": tf / len(qids),
                                             "paired": paired(rows)}
        for k in MRR_K:
            bm, tf, rows = 0.0, 0.0, []
            qids = sorted({q for (s, _, q) in rankings if s == split})
            for qid in qids:
                value = {m: mrr_at(rankings[(split, m, qid)], qrels[qid], k) for m in ARMS}
                bm += value["bm25"]
                tf += value["tfidf_cosine"]
                rows.append((qid, value["bm25"], value["tfidf_cosine"]))
            block["mrr"][f"mrr@{k}"] = {"bm25": bm / len(qids), "tfidf_cosine": tf / len(qids),
                                        "paired": paired(rows)}
        for k in NDCG_K:
            bm, tf, rows = 0.0, 0.0, []
            qids = sorted({q for (s, _, q) in rankings if s == split})
            for qid in qids:
                value = {m: ndcg_at(rankings[(split, m, qid)], qrels[qid], k) for m in ARMS}
                bm += value["bm25"]
                tf += value["tfidf_cosine"]
                rows.append((qid, value["bm25"], value["tfidf_cosine"]))
            block["ndcg"][f"ndcg@{k}"] = {"bm25": bm / len(qids), "tfidf_cosine": tf / len(qids),
                                          "paired": paired(rows)}
        # where does the single positive actually land, per arm
        for method in ARMS:
            ranks = []
            for qid in sorted({q for (s, _, q) in rankings if s == split}):
                ranking = rankings[(split, method, qid)]
                rank = next((i + 1 for i, doc in enumerate(ranking) if doc in qrels[qid]), None)
                ranks.append({"query_id": qid, "rank": rank})
            block["positive_rank"][method] = {
                "at_1": sum(1 for r in ranks if r["rank"] == 1),
                "within_3": sum(1 for r in ranks if r["rank"] and r["rank"] <= 3),
                "within_5": sum(1 for r in ranks if r["rank"] and r["rank"] <= 5),
                "within_10": sum(1 for r in ranks if r["rank"] and r["rank"] <= 10),
                "beyond_20_or_missing": sum(1 for r in ranks if not r["rank"]),
                "n": len(ranks), "per_query": ranks}
        curve["splits"][split] = block

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(curve, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"guards: {len(rankings)} rankings, {len(frozen) * 5} frozen metrics reproduced, "
          f"{len(fixtures)} fixtures")
    for split in ("dev", "validation"):
        print(f"\n[{split}]")
        for name, cell in curve["splits"][split]["recall"].items():
            p = cell["paired"]
            print(f"  {name:<10} bm25 {cell['bm25']:.4f}  tfidf {cell['tfidf_cosine']:.4f}  "
                  f"delta {p['mean']:+.4f}  {p['wins']}/{p['ties']}/{p['losses']}")
        for name, cell in curve["splits"][split]["mrr"].items():
            p = cell["paired"]
            print(f"  {name:<10} bm25 {cell['bm25']:.4f}  tfidf {cell['tfidf_cosine']:.4f}  "
                  f"delta {p['mean']:+.4f}  {p['wins']}/{p['ties']}/{p['losses']}")
        for method in ARMS:
            block = curve["splits"][split]["positive_rank"][method]
            print(f"  rank of positive, {method:<12} at1 {block['at_1']} w3 {block['within_3']} "
                  f"w5 {block['within_5']} w10 {block['within_10']} miss {block['beyond_20_or_missing']} "
                  f"/ {block['n']}")
    print(f"\nwrote {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
