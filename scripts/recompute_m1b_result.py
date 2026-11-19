"""Independent read-only recomputation of the M1b primary result.

Does not rank anything and does not import src.autoresearch. It takes the stored
top-20 lists, the frozen qrels and the frozen corpus, and recomputes every
published metric with Decimal. If the numbers match, the result is reproducible
from the evidence on disk rather than merely self-reported by the tool that
produced it.

Checks
  R1 the 64 rows are exactly 32 queries x 2 arms, split labels agree with spec.json
  R2 every stored ranking has 20 unique ids and every id exists in the 940-doc corpus
  R3 recall@5/10/20, mrr@10, ndcg@10 recomputed per query and per arm
  R4 split means and paired candidate-minus-baseline means, wins/ties/losses
  R5 scope identities: corpus, queries, qrels, snapshot, comparison constants
  R6 budget: research actions, model calls, fits, cash
  R7 what the primary endpoint actually did (the question M1 could not answer)
  R8 the declared adverse queries are exactly the per-query losses

  python scripts/recompute_m1b_result.py   -> runs/m1b-recompute-20261119/result.json
"""

import argparse
import collections
import hashlib
import json
import math
import re
import sys
from decimal import Decimal, getcontext
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / "runs/m1b-cfr-20261119"
PACKET = ROOT / "runs/m1b-packet-20261119"
ASSETS = PACKET / "assets"
OUT = ROOT / "runs/m1b-recompute-20261119/result.json"

METRICS = ("recall@5", "recall@10", "recall@20", "mrr@10", "ndcg@10")
CUTOFF = {"recall@5": 5, "recall@10": 10, "recall@20": 20, "mrr@10": 10, "ndcg@10": 10}
TOL = Decimal("1e-12")
getcontext().prec = 40

CHECKS = []


def check(name, ok, detail):
    CHECKS.append({"check": name, "ok": bool(ok), "detail": detail})
    print(f"[{'PASS' if ok else 'FAIL'}] {name}: {detail}")
    return ok


def note(name, ok, detail):
    CHECKS.append({"check": name, "ok": bool(ok), "detail": detail, "kind": "finding"})
    print(f"[{'NOTE' if ok else 'WARN'}] {name}: {detail}")
    return ok


def sha256_bytes(raw):
    return hashlib.sha256(raw).hexdigest()


def read_jsonl(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").split("\n") if line.strip()]


def dec(value):
    return Decimal(str(value))


def close(a, b):
    return abs(a - b) <= TOL


def query_metrics(ranking, positive_ids):
    """Recompute the five metrics for one ranked list given the binary positives."""
    hits = [1 if doc in positive_ids else 0 for doc in ranking]
    out = {}
    for metric in ("recall@5", "recall@10", "recall@20"):
        k = CUTOFF[metric]
        out[metric] = Decimal(sum(hits[:k])) / Decimal(len(positive_ids))
    rr = Decimal(0)
    for rank, hit in enumerate(hits[:CUTOFF["mrr@10"]], start=1):
        if hit:
            rr = Decimal(1) / Decimal(rank)
            break
    out["mrr@10"] = rr
    dcg = Decimal(0)
    for rank, hit in enumerate(hits[:CUTOFF["ndcg@10"]], start=1):
        if hit:
            # One positive, grade 2, binary gain 1: DCG = 1/log2(rank+1) and the
            # ideal DCG is 1/log2(1+1) = 1, so nDCG equals that single term.
            dcg = Decimal(1) / (Decimal(rank + 1).ln() / Decimal(2).ln())
            break
    out["ndcg@10"] = dcg
    return out


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=None)
    args = parser.parse_args(argv)
    out = Path(args.out) if args.out else OUT

    payload = json.loads((RUN / "primary-result.json").read_text(encoding="utf-8"))
    result = payload["result"]
    ledger = json.loads((RUN / "ledger.json").read_text(encoding="utf-8"))
    spec = json.loads((ASSETS / "spec.json").read_text(encoding="utf-8"))
    corpus = read_jsonl(ASSETS / "corpus.jsonl")
    queries = read_jsonl(ASSETS / "queries.jsonl")
    qrels_lines = [line.split("\t") for line in
                   (ASSETS / "qrels.tsv").read_text(encoding="utf-8").splitlines()[1:] if line.strip()]

    doc_ids = {row["_id"] for row in corpus}
    qrels = collections.defaultdict(dict)
    for qid, doc, grade in qrels_lines:
        qrels[qid][doc] = int(grade)
    positives = {qid: {d for d, g in grades.items() if g > 0} for qid, grades in qrels.items()}
    declared_split = {qid: split for split in ("dev", "validation")
                      for qid in spec["query_splits"][split]}

    # --- R1 shape ---------------------------------------------------------
    rankings = result["rankings"]
    keys = collections.Counter((row["query_id"], row["method"]) for row in rankings)
    arms = sorted({row["method"] for row in rankings})
    check("R1 64 rankings cover every query x arm pair exactly once",
          len(rankings) == 64 and set(keys.values()) == {1}
          and len({row["query_id"] for row in rankings}) == len(queries) == 32
          and arms == ["bm25", "tfidf_cosine"],
          {"rows": len(rankings), "queries": len({row["query_id"] for row in rankings}),
           "arms": arms, "duplicate_pairs": [k for k, v in keys.items() if v > 1]})

    split_mismatch = [row["query_id"] for row in rankings
                      if declared_split.get(row["query_id"]) != row["split"]]
    check("R1b split labels agree with spec.json on all 64 rows", not split_mismatch,
          {"splits": dict(collections.Counter(row["split"] for row in rankings)),
           "mismatch": split_mismatch[:10]})

    # --- R2 ranking hygiene ----------------------------------------------
    bad_len = [row["query_id"] for row in rankings if len(row["ranking"]) != 20]
    bad_dup = [row["query_id"] for row in rankings if len(set(row["ranking"])) != len(row["ranking"])]
    unknown = sorted({doc for row in rankings for doc in row["ranking"] if doc not in doc_ids})
    self_hit = [row["query_id"] for row in rankings if row["query_id"] in row["ranking"]]
    check("R2 every ranking is 20 unique corpus ids with no self-hit",
          not bad_len and not bad_dup and not unknown and not self_hit,
          {"bad_length": bad_len[:5], "duplicated_ids": bad_dup[:5],
           "ids_not_in_corpus": unknown[:5], "self_hits": self_hit[:5]})

    # --- R3 recompute per query -------------------------------------------
    stored_rows = collections.defaultdict(list)
    for entry in result["per_query_metrics"]:
        stored_rows[(entry["query_id"], entry["method"])].append(entry["metrics"])

    recomputed = {}
    mismatch = []
    for row in rankings:
        mine = query_metrics(row["ranking"], positives[row["query_id"]])
        recomputed[(row["query_id"], row["method"])] = {"split": row["split"], **mine}
        stored = stored_rows.get((row["query_id"], row["method"]), [])
        if len(stored) != 1:
            mismatch.append({"query_id": row["query_id"], "method": row["method"],
                             "reason": f"{len(stored)} stored rows"})
            continue
        stored = stored[0]
        for metric in METRICS:
            if not close(mine[metric], dec(stored[metric])):
                mismatch.append({"query_id": row["query_id"], "method": row["method"],
                                 "metric": metric, "stored": stored[metric],
                                 "recomputed": str(mine[metric])})
    check("R3 all 5 metrics recomputed from rankings + qrels match the tool's per-query rows",
          not mismatch,
          {"pairs_checked": len(recomputed), "metric_comparisons": len(recomputed) * len(METRICS),
           "mismatches": mismatch[:8], "mismatch_count": len(mismatch)})

    # --- R4 split means and paired deltas ---------------------------------
    mean_mismatch = []
    for split in ("dev", "validation"):
        for arm in arms:
            rows = [v for k, v in recomputed.items() if v["split"] == split and k[1] == arm]
            for metric in METRICS:
                mine = sum(r[metric] for r in rows) / Decimal(len(rows))
                stated = dec(result["paired_summary"]["splits"][split]["arms"][arm]["metrics"][metric])
                if not close(mine, stated):
                    mean_mismatch.append({"split": split, "arm": arm, "metric": metric,
                                          "recomputed": str(mine), "stated": str(stated)})
    check("R4a split means for both arms match the recomputation", not mean_mismatch,
          {"mismatch_count": len(mean_mismatch), "mismatches": mean_mismatch[:8]})

    paired_mismatch = []
    winloss = {}
    for split in ("dev", "validation"):
        qids = [q for q, s in declared_split.items() if s == split]
        for metric in METRICS:
            deltas = [recomputed[(q, "tfidf_cosine")][metric] - recomputed[(q, "bm25")][metric]
                      for q in qids]
            mean = sum(deltas) / Decimal(len(deltas))
            w = sum(1 for d in deltas if d > 0)
            t = sum(1 for d in deltas if d == 0)
            l = sum(1 for d in deltas if d < 0)
            winloss.setdefault(split, {})[metric] = {"wins": w, "ties": t, "losses": l,
                                                     "mean": str(mean.quantize(Decimal("1e-12")))}
            stated = result["paired_summary"]["splits"][split]["paired_candidate_minus_baseline"][metric]
            if not close(mean, dec(stated["mean"])) or (w, t, l) != (stated["wins"], stated["ties"], stated["losses"]):
                paired_mismatch.append({"split": split, "metric": metric,
                                        "recomputed": {"mean": str(mean), "w": w, "t": t, "l": l},
                                        "stated": stated})
    check("R4b paired means and win/tie/loss counts match", not paired_mismatch,
          {"mismatch_count": len(paired_mismatch), "mismatches": paired_mismatch[:8],
           "validation": winloss.get("validation")})

    # --- R5 scope identities ---------------------------------------------
    scope = result["scope"]
    freeze = json.loads((PACKET / "freeze.json").read_text(encoding="utf-8"))
    identities = {
        "corpus": sha256_bytes((ASSETS / "corpus.jsonl").read_bytes()),
        "queries": sha256_bytes((ASSETS / "queries.jsonl").read_bytes()),
        "qrels": sha256_bytes((ASSETS / "qrels.tsv").read_bytes()),
    }
    stated_inputs = {k: v["sha256"] for k, v in scope["input_identities"].items()}
    check("R5a result scope binds the packet bytes on disk",
          scope["document_count"] == len(corpus) == 940
          and all(stated_inputs[k] == v for k, v in identities.items())
          and scope["comparison_sha256"]
          == hashlib.sha256(json.dumps(spec["comparison"], sort_keys=True, separators=(",", ":"))
                            .encode("utf-8")).hexdigest(),
          {"documents": scope["document_count"], "identities_match": {k: stated_inputs[k] == v
                                                                     for k, v in identities.items()},
           "comparison_sha256": scope["comparison_sha256"]})

    check("R5b source snapshot is the frozen M1b snapshot",
          result["source_snapshot_sha256"] == freeze["snapshot_sha256"],
          {"result": result["source_snapshot_sha256"], "freeze": freeze["snapshot_sha256"]})

    # --- R6 budget --------------------------------------------------------
    check("R6 budget: 2 research actions, 0 model calls, 0 fits, no cash",
          ledger["research_actions_used"] == 2 and ledger["research_action_limit"] == 2
          and payload["model_calls"] == 0 and payload["new_fits"] == 0
          and [a["action"] for a in ledger["actions"]] == ["capture_source", "execute"]
          and result["usage"]["model_calls"] == 0 and result["usage"]["native_fits"] == 0,
          {"actions": [a["action"] for a in ledger["actions"]],
           "limit": ledger["research_action_limit"], "model_calls": payload["model_calls"],
           "new_fits": payload["new_fits"], "ranking_calls": result["usage"]["ranking_calls"],
           "scoring_calls": result["usage"]["scoring_calls"], "cash": "no paid call in this run"})

    # --- R7 what the primary endpoint did ---------------------------------
    val = {arm: result["paired_summary"]["splits"]["validation"]["arms"][arm]["metrics"] for arm in arms}
    distinct = {arm: sorted({str(dec(recomputed[(q, arm)]["recall@20"])) for q in declared_split
                             if declared_split[q] == "validation"}) for arm in arms}
    delta_r20 = dec(val["tfidf_cosine"]["recall@20"]) - dec(val["bm25"]["recall@20"])
    delta_mrr = dec(val["tfidf_cosine"]["mrr@10"]) - dec(val["bm25"]["mrr@10"])
    check("R7 recall@20 regained variance on validation, so the primary endpoint is answerable",
          (len(distinct["bm25"]) > 1 or len(distinct["tfidf_cosine"]) > 1)
          and not (distinct["bm25"] == ["1.0"] and distinct["tfidf_cosine"] == ["1.0"]),
          {"validation_recall@20_values": distinct,
           "bm25": val["bm25"]["recall@20"], "tfidf_cosine": val["tfidf_cosine"]["recall@20"],
           "delta_recall@20": str(delta_r20), "delta_mrr@10": str(delta_mrr),
           "verdict": "D1 (recall up, mrr down)" if delta_r20 > 0 and delta_mrr < 0 else
                      "D2 (neither trade-off)" if delta_r20 >= 0 and delta_mrr >= 0 else
                      "D3 (indistinguishable)" if delta_r20 == 0 and delta_mrr == 0 else
                      "D4 other: candidate lost recall@20 and gained mrr@10 -- the pre-registered "
                      "trade-off is not what happened, and the sign is reversed",
           "note": "the stop condition 'still 1.0 everywhere -> pool insufficient' was not triggered"})

    # --- R8 adverse queries ----------------------------------------------
    losses = {}
    both_zero = []
    for q, split in declared_split.items():
        if split != "validation":
            continue
        if all(recomputed[(q, arm)]["mrr@10"] == 0 for arm in arms):
            both_zero.append(q)
        lost = [m for m in METRICS if recomputed[(q, "tfidf_cosine")][m] < recomputed[(q, "bm25")][m]]
        if lost:
            losses[q] = lost
    declared_loss = {entry["query_id"]: sorted(entry["loss_metrics"])
                     for entry in result["adverse_queries"] if entry["loss_metrics"]}
    declared_empty = sorted(entry["query_id"] for entry in result["adverse_queries"]
                            if not entry["loss_metrics"])
    check("R8 declared adverse queries split exactly into 'candidate lost' and 'both arms missed'",
          declared_loss == {q: sorted(v) for q, v in losses.items()}
          and declared_empty == sorted(both_zero),
          {"candidate_lost": {q: sorted(v) for q, v in losses.items()},
           "both_arms_zero": sorted(both_zero),
           "declared_without_loss_metrics": declared_empty})

    # --- R9 how coarse the endpoint still is ------------------------------
    val_queries = [q for q, s in declared_split.items() if s == "validation"]
    per_query_weight = Decimal(1) / Decimal(len(val_queries))
    check("R9 report the granularity the endpoint actually has",
          len(val_queries) == 24 and close(delta_r20, -per_query_weight),
          {"validation_queries": len(val_queries),
           "one_query_weight": str(per_query_weight.quantize(Decimal("1e-6"))),
           "delta_recall@20": str(delta_r20.quantize(Decimal("1e-6"))),
           "reading": "the whole recall@20 difference is a single query; two validation queries "
                      "are unreachable for both arms, so the attainable ceiling is 22/24, and "
                      "bm25 already sits on it",
           "ceiling_bm25": str((Decimal(len(val_queries) - len(both_zero)) / Decimal(len(val_queries)))
                               .quantize(Decimal("1e-6"))),
           "ceiling_reached_by_bm25": close(dec(val["bm25"]["recall@20"]),
                                            Decimal(len(val_queries) - len(both_zero)) / Decimal(len(val_queries)))})

    # --- R10 the published per-query table, recomputed from its own columns -
    report_path = ROOT / "docs/project/workbuddy/m1b-primary-20261119.md"
    table_issues = []
    rows_checked = 0
    if report_path.exists():
        for line in report_path.read_text(encoding="utf-8").splitlines():
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if len(cells) != 6 or not re.fullmatch(r"q-val-\d+", cells[0]):
                continue
            rows_checked += 1
            qid = cells[0]

            def rank_of(cell):
                # "10 → 19" -> 19; "8 → >20" -> None (outside top 20); tolerates **bold**
                right = cell.split("→")[-1].replace("*", "").strip()
                return None if ">" in right else int(right)

            ranks = {"bm25": rank_of(cells[1]), "tfidf_cosine": rank_of(cells[2])}

            def mrr10(rank):
                # mrr@10 truncates at 10, so a positive at rank 11 or beyond scores 0
                return Decimal(0) if rank is None or rank > 10 else Decimal(1) / Decimal(rank)

            expected = mrr10(ranks["tfidf_cosine"]) - mrr10(ranks["bm25"])
            # cells may carry markdown bold and the typographic minus sign; the
            # table prints four decimals, so compare at that resolution
            stated = dec(cells[3].replace("*", "").replace("−", "-").strip())
            if expected.quantize(Decimal("0.0001")) != stated.quantize(Decimal("0.0001")):
                table_issues.append({"query_id": qid, "column": "Δmrr@10",
                                     "printed": cells[3], "from_printed_ranks": str(expected)})

            stored = {row["method"]: row["ranking"] for row in rankings if row["query_id"] == qid}
            for arm, printed in (("bm25", ranks["bm25"]), ("tfidf_cosine", ranks["tfidf_cosine"])):
                positive = next(iter(positives[qid]))
                actual = stored[arm].index(positive) + 1 if positive in stored.get(arm, []) else None
                if actual != printed:
                    table_issues.append({"query_id": qid, "arm": arm, "column": "M1b rank",
                                         "printed": printed, "recomputed": actual})
    check("R10 published per-query table reproduces from the stored rankings",
          rows_checked == 11 and not table_issues,
          {"rows_checked": rows_checked, "issues": table_issues, "issue_count": len(table_issues),
           "note": "mrr@10 truncates at 10, so a positive ranked 19 scores 0 and q-val-05 is "
                   "correctly +1.0 rather than +0.947"})

    # --- R11 the pre-registered sign test ---------------------------------
    def exact_two_sided(wins, losses):
        n = wins + losses
        if n == 0:
            return Decimal(1)
        probs = [Decimal(math.comb(n, k)) / Decimal(2 ** n) for k in range(n + 1)]
        observed = probs[wins]
        return sum(p for p in probs if p <= observed) / Decimal(1)

    sign_tests = {}
    for metric in ("mrr@10", "ndcg@10", "recall@20"):
        w = winloss["validation"][metric]["wins"]
        l = winloss["validation"][metric]["losses"]
        n = w + l
        sign_tests[metric] = {"wins": w, "losses": l, "discordant": n,
                              "two_sided_p": str(exact_two_sided(w, l).quantize(Decimal("0.0001"))) if n else None,
                              "required_by_protocol": n >= 6}
    check("R11 the pre-registered sign test is reported wherever it was required",
          sign_tests["mrr@10"]["required_by_protocol"] and sign_tests["mrr@10"]["two_sided_p"] == "1.0000"
          and sign_tests["ndcg@10"]["two_sided_p"] == "1.0000",
          {"sign_tests": sign_tests,
           "reading": "9 discordant pairs split 4/5 is the least extreme split possible; p=1.0000 "
                      "is an absence of evidence, not evidence of absence, and n=24 cannot "
                      "reach significance unless at least 6 pairs agree in direction"})

    # --- summary ----------------------------------------------------------
    failed = [c["check"] for c in CHECKS if not c["ok"]]
    findings = [c["check"] for c in CHECKS if c.get("kind") == "finding"]
    summary = {
        "run": "m1b-cfr-20261119",
        "verifier": "scripts/recompute_m1b_result.py",
        "independent": "stdlib + Decimal; recomputes metrics from stored top-20 lists and frozen qrels; "
                       "no ranking is performed",
        "generated_at_local": "2026-11-19 (Asia/Shanghai)",
        "validation": {arm: {m: val[arm][m] for m in METRICS} for arm in arms},
        "paired_validation": winloss.get("validation"),
        "delta_validation": {"recall@20": str(delta_r20), "mrr@10": str(delta_mrr)},
        "checks_total": len(CHECKS),
        "checks_failed": failed,
        "findings": findings,
        "checks": CHECKS,
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"\n{len(CHECKS) - len(failed)}/{len(CHECKS)} checks passed; wrote {out}")
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
