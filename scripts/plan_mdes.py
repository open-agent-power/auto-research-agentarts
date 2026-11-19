"""What could this design actually have detected? Planning numbers for the next card.

Read-only. Consumes the published M1b per-query metrics, recomputes paired differences,
and turns them into minimum detectable effects. Nothing here ranks anything, and nothing
here is a result: it is a planning estimate that says how large a sample a future card
would need before its endpoint can move at all.

  .venv/Scripts/python.exe -B scripts/plan_mdes.py
  .venv/Scripts/python.exe -B scripts/plan_mdes.py --json runs/mdes-20261119/plan.json

Caveats that travel with every number below:
  * the spread is estimated from the same 24 queries it is applied to (pilot planning);
  * per-query metrics are bounded and lumpy, so the normal approximation is optimistic;
  * a binary endpoint is analysed with an exact sign test, which ignores magnitude.
"""

import argparse
import json
import math
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESULT = ROOT / "runs/m1b-cfr-20261119/primary-result.json"

Z_975 = 1.959963984540054      # two-sided alpha = 0.05
Z_95 = 1.6448536269514722      # one-sided alpha = 0.05, the alpha each TOST test uses
Z_80 = 0.8416212335729143      # power = 0.80
METRICS = ["recall@5", "recall@10", "recall@20", "mrr@10", "ndcg@10"]


def load(split="validation"):
    payload = json.loads(RESULT.read_text(encoding="utf-8"))
    rows = payload["result"]["per_query_metrics"]
    arms = defaultdict(dict)
    for row in rows:
        if row["split"] != split:
            continue
        arms[row["method"]][row["query_id"]] = row["metrics"]
    baseline, candidate = "bm25", "tfidf_cosine"
    queries = sorted(set(arms[baseline]) & set(arms[candidate]))
    return {m: [arms[candidate][q][m] - arms[baseline][q][m] for q in queries] for m in METRICS}, queries


def mean(xs):
    return sum(xs) / len(xs)


def stdev(xs):
    mu = mean(xs)
    return math.sqrt(sum((x - mu) ** 2 for x in xs) / (len(xs) - 1))


def describe(diffs):
    wins = sum(1 for d in diffs if d > 1e-12)
    losses = sum(1 for d in diffs if d < -1e-12)
    return {"n": len(diffs), "mean": mean(diffs), "sd": stdev(diffs),
            "wins": wins, "ties": len(diffs) - wins - losses, "losses": losses,
            "movable": wins + losses}


def continuous_mdes(diffs, alpha_z=Z_975, power_z=Z_80):
    sd = stdev(diffs)
    n = len(diffs)
    mdes = (alpha_z + power_z) * sd / math.sqrt(n)
    def n_for(delta):
        return math.ceil(((alpha_z + power_z) * sd / delta) ** 2)
    return {"sd_of_paired_difference": sd, "mdes_at_observed_n": mdes,
            "n_for_delta_0.05": n_for(0.05), "n_for_delta_0.10": n_for(0.10),
            "n_for_delta_0.15": n_for(0.15)}


def binom_tail(d, k):
    """P(X >= k) for X ~ Binomial(d, 0.5), two-sided sign test."""
    return sum(math.comb(d, i) for i in range(k, d + 1)) / 2 ** d


def binom_power(d, k, p):
    """P(X >= k) for X ~ Binomial(d, p) — power when p of the discordant pairs favour the candidate."""
    return sum(math.comb(d, i) * p ** i * (1 - p) ** (d - i) for i in range(k, d + 1))


def sign_test_table(max_d=400):
    """For each number of discordant pairs, the critical count and the power at p = 0.75."""
    rows = []
    for d in range(1, max_d + 1):
        k = next((k for k in range(1, d + 1) if binom_tail(d, k) <= 0.025), None)
        if k is None:
            continue
        rows.append({"discordant_pairs": d, "critical_wins": k,
                     "power_at_p_0.75": binom_power(d, k, 0.75),
                     "power_at_p_0.70": binom_power(d, k, 0.70)})
    return rows


def first_d_with_power(rows, p_key, target=0.80):
    for row in rows:
        if row[p_key] >= target:
            return row
    return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", type=Path, default=None)
    args = parser.parse_args()

    diffs, queries = load()
    print(f"validation queries: {len(queries)}")
    print("candidate = tfidf_cosine, baseline = bm25, difference = candidate - baseline\n")

    observed = {m: describe(diffs[m]) for m in METRICS}
    print(f"{'metric':<11}{'mean':>10}{'sd':>9}{'w/t/l':>10}{'movable':>9}  mdes@n")
    for m in METRICS:
        o = observed[m]
        plan = continuous_mdes(diffs[m])
        print(f"{m:<11}{o['mean']:>10.6f}{o['sd']:>9.4f}"
              f"{o['wins']:>4}/{o['ties']:>2}/{o['losses']:<3}{o['movable']:>9}"
              f"  {plan['mdes_at_observed_n']:.4f}")

    print("\ncontinuous metrics — sample needed (80% power, alpha .05 two-sided)")
    print(f"{'metric':<11}{'sd':>9}{'n(d=.05)':>10}{'n(d=.10)':>10}{'n(d=.15)':>10}")
    plans = {}
    for m in METRICS:
        plan = continuous_mdes(diffs[m])
        plans[m] = plan
        print(f"{m:<11}{plan['sd_of_paired_difference']:>9.4f}"
              f"{plan['n_for_delta_0.05']:>10}{plan['n_for_delta_0.10']:>10}"
              f"{plan['n_for_delta_0.15']:>10}")

    print("\nequivalence (TOST) — sample needed to *claim* a difference stays inside a margin")
    print("  this is not the same question as detecting a difference; a non-significant test is not evidence of equivalence")
    print(f"{'metric':<11}{'sd':>9}{'margin .05':>12}{'margin .10':>12}")
    tost = {}
    for m in METRICS:
        sd = stdev(diffs[m])
        plan = {"margin_0.05": math.ceil(((Z_95 + Z_80) * sd / 0.05) ** 2),
                "margin_0.10": math.ceil(((Z_95 + Z_80) * sd / 0.10) ** 2)}
        tost[m] = plan
        print(f"{m:<11}{sd:>9.4f}{plan['margin_0.05']:>12}{plan['margin_0.10']:>12}")

    rows = sign_test_table()
    p75 = first_d_with_power(rows, "power_at_p_0.75")
    p70 = first_d_with_power(rows, "power_at_p_0.70")
    p100 = rows[0] if rows else None
    print("\nbinary endpoint — exact sign test (direction only, no magnitude)")
    print(f"  discordant pairs needed for 80% power: {p75['discordant_pairs']} at p=.75, "
          f"{p70['discordant_pairs']} at p=.70")
    print(f"  at that size the test needs {p75['critical_wins']}/{p75['discordant_pairs']} "
          f"one-directional wins to reach p<.05")
    print(f"  if every discordant pair points the same way, {p100['critical_wins']} suffice "
          f"(2^-d <= .025)")

    # Mean shift and discordant count are tied together: delta = (2p - 1) * d / N.
    # So "how many queries" depends on how one-sided the flipping is, and both scenarios below
    # are internally consistent — unlike quoting d/rate, which mixes the two conventions.
    scaling = []
    print("\nbinary endpoint — queries needed, two consistent scenarios")
    print(f"{'direction rate p':<20}{'discordant d':>13}{'N for d=.05':>13}"
          f"{'N for d=.10':>13}{'N for d=.15':>13}")
    for label, p, d_needed in (("all same way (1.00)", 1.00, p100["critical_wins"]),
                               ("3 of 4 (0.75)", 0.75, p75["discordant_pairs"]),
                               ("7 of 10 (0.70)", 0.70, p70["discordant_pairs"])):
        spread = 2 * p - 1
        row = {"direction_rate": p, "discordant_pairs": d_needed, "queries": {}}
        cells = []
        for delta in (0.05, 0.10, 0.15):
            n_needed = math.ceil(spread * d_needed / delta)
            row["queries"][f"{delta:.2f}"] = n_needed
            cells.append(n_needed)
        scaling.append(row)
        print(f"{label:<20}{d_needed:>13}{cells[0]:>13}{cells[1]:>13}{cells[2]:>13}")

    r20 = observed["recall@20"]
    discordance_rate = r20["movable"] / r20["n"] if r20["n"] else 0.0
    print(f"\nobserved recall@20 discordance in this pack: {r20['movable']}/{r20['n']} "
          f"({discordance_rate:.4f}); ceiling: {r20['ties']} queries cannot move at all")

    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "generated_by": "scripts/plan_mdes.py",
            "source": str(RESULT.relative_to(ROOT)).replace("\\", "/"),
            "split": "validation", "queries": len(queries),
            "baseline": "bm25", "candidate": "tfidf_cosine",
            "observed": observed, "continuous_plans": plans,
            "tost": tost,
            "sign_test": {"discordant_for_power_0.80_at_p_0.75": p75,
                          "discordant_for_power_0.80_at_p_0.70": p70},
            "binary_scaling": scaling,
            "caveats": ["spread estimated from the same 24 queries it is applied to",
                        "bounded, lumpy per-query metrics make the normal approximation optimistic",
                        "the sign test ignores magnitude, so it needs many discordant pairs"],
        }
        args.json.write_bytes((json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
        print(f"wrote {args.json}")


if __name__ == "__main__":
    main()
