#!/usr/bin/env python3
"""Fixed-code G5-L CPU benchmarks; data-only input, stdlib, no model/network/run hooks."""
import os

for _name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ[_name] = "1"

import argparse
import bisect
from collections import Counter, defaultdict
import csv
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import platform
import random
import re
import resource
import shutil
import signal
import statistics
import sys
import tarfile
import time

REPO = Path(__file__).resolve().parents[1]
PROTOCOL = REPO / "docs/execution/g5-local/protocol.md"
SCRIPT = Path(__file__).resolve()
FILES = ("scifact/corpus.jsonl", "scifact/queries.jsonl", "scifact/qrels/train.tsv",
         "scifact/qrels/test.tsv", "SCIFACT-LICENSE.md", "scifact-beir.zip", "scifact-original.tar.gz")
ARCHIVE_SHA = "536e14446a0ba56ed1398ab1055f39fe852686ecad24a6306c80c490fa8e0165"
ORIGINAL_SHA = "11c621288d41ac144d29b13b0f8503b3820b7d6e8b1f6ff24dff335c196d76be"
SOURCE_COMMIT = "68b98a56d93e0f9da0d2aab4e6c3294699a0f72e"
CONFIG = {"version": "g5l-cpu-v1", "top_k": 20, "k1": 1.2, "b": 0.75,
          "dev_count": 80, "validation_count": 80,
          "algorithm_sizes": [128, 512, 2048, 4096],
          "algorithm_test_seeds": [303, 404, 505], "repeats": 3,
          "wall_seconds": 180, "cpu_seconds": 120, "as_bytes": 1073741824}


def digest(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for b in iter(lambda: f.read(1024 * 1024), b""):
            h.update(b)
    return h.hexdigest()


def value_hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def save(path, value):
    with Path(path).open("x") as f:
        json.dump(value, f, indent=2, allow_nan=False)
        f.write("\n")


def read_jsonl(path):
    rows = [json.loads(line) for line in Path(path).read_text().splitlines() if line.strip()]
    assert len(rows) == len({row["_id"] for row in rows}), "duplicate document/query ID"
    return {row["_id"]: row for row in rows}


def read_qrels(path):
    rows = defaultdict(dict)
    with Path(path).open() as f:
        for row in csv.DictReader(f, delimiter="\t"):
            q, d, score = row["query-id"], row["corpus-id"], int(row["score"])
            assert d not in rows[q] and score == 1, "invalid or duplicate binary qrel"
            rows[q][d] = score
    return dict(rows)


def check_sources(inputs):
    assert digest(inputs / "scifact-beir.zip") == ARCHIVE_SHA, "BEIR archive changed"
    assert digest(inputs / "scifact-original.tar.gz") == ORIGINAL_SHA, "original archive changed"
    docs, queries = read_jsonl(inputs / FILES[0]), read_jsonl(inputs / FILES[1])
    assert len(docs) == 5183 and len(queries) == 1109
    with tarfile.open(inputs / "scifact-original.tar.gz") as archive:
        def original(name):
            member = archive.getmember("data/" + name)
            assert member.isfile() and member.size < 16 * 1024 * 1024
            return [json.loads(line) for line in archive.extractfile(member) if line.strip()]
        originals = {str(row["doc_id"]): row for row in original("corpus.jsonl")}
        assert set(originals) == set(docs)
        for doc_id, row in docs.items():
            source = originals[doc_id]
            assert row["title"] == source["title"]
            assert " ".join(row["text"].split()) == " ".join(" ".join(source["abstract"]).split())
        details = {}
        for split, name, count, pairs in (("train", "claims_train.jsonl", 809, 919),
                                          ("test", "claims_dev.jsonl", 300, 339)):
            claims = original(name)
            qrels = read_qrels(inputs / f"scifact/qrels/{split}.tsv")
            expected = {str(row["id"]): {str(doc): 1 for doc in row["cited_doc_ids"]} for row in claims}
            assert expected == qrels and len(qrels) == count
            assert sum(map(len, qrels.values())) == pairs
            assert all(queries[str(row["id"])]["text"] == row["claim"] for row in claims)
            assert all(doc_id in docs for rel in qrels.values() for doc_id in rel)
            details[split] = {"queries": count, "pairs": pairs, "original_file": name,
                              "qrels_semantics": "original cited_doc_ids, not support/refute"}
    return details


def prepare(inputs, output):
    assert not output.exists(), "output directory exists; preserve original attempt"
    output.mkdir(parents=True)
    details = check_sources(inputs)
    train = sorted(read_qrels(inputs / "scifact/qrels/train.tsv"),
                   key=lambda q: hashlib.sha256(("g5l-dev-v1:" + q).encode()).hexdigest())
    test = sorted(read_qrels(inputs / "scifact/qrels/test.tsv"))
    split = {"dev": train[:80], "validation": train[80:160], "test": test}
    assert len(set().union(*map(set, split.values()))) == 460
    frozen = {"created_utc": datetime.now(timezone.utc).isoformat(), "config": CONFIG,
              "script_sha256": digest(SCRIPT), "protocol_sha256": digest(PROTOCOL),
              "input_dir": str(inputs), "inputs": {f: digest(inputs / f) for f in FILES},
              "splits": split, "provenance_checks": details,
              "original_source_commit": SOURCE_COMMIT,
              "licenses": {"claims_and_qrels": "CC-BY-4.0", "abstracts": "ODC-By-1.0"},
              "attribution": "SciFact, Wadden et al., Fact or Fiction: Verifying Scientific Claims, EMNLP 2020; Semantic Scholar S2ORC abstracts; BEIR redistribution"}
    save(output / "freeze.json", frozen)
    shutil.copyfile(PROTOCOL, output / "protocol-frozen.md")
    print(json.dumps({"status": "prepared_not_executed", "output": str(output),
                      "freeze_sha256": digest(output / "freeze.json"), "provenance": details}))


def tokens(text):
    return re.findall(r"[a-z0-9]+", text.lower())


def build_index(docs):
    postings, lengths = defaultdict(list), {}
    for doc_id in sorted(docs):
        row = docs[doc_id]
        terms = Counter(tokens(row["title"] + " " + row["text"]))
        lengths[doc_id] = sum(terms.values())
        for term, count in terms.items():
            postings[term].append((doc_id, count))
    n = len(docs)
    idfs = {term: math.log((n + 1) / (len(rows) + 1)) + 1 for term, rows in postings.items()}
    normsq = defaultdict(float)
    for term, rows in postings.items():
        for doc_id, count in rows:
            normsq[doc_id] += ((1 + math.log(count)) * idfs[term]) ** 2
    norms = {doc: math.sqrt(v) for doc, v in normsq.items()}
    return postings, lengths, idfs, norms, n, sum(lengths.values()) / n


def retrieve(query, index, method):
    postings, lengths, idfs, norms, n, avgdl = index
    counts = Counter(tokens(query))
    score = defaultdict(float)
    if method == "tfidf_cosine":
        qweights = {term: (1 + math.log(count)) * idfs[term] for term, count in counts.items() if term in idfs}
        qnorm = math.sqrt(sum(v * v for v in qweights.values()))
        for term, weight in qweights.items():
            for doc, tf in postings[term]:
                score[doc] += weight * ((1 + math.log(tf)) * idfs[term]) / (qnorm * norms[doc])
    elif method == "bm25":
        k1, b = CONFIG["k1"], CONFIG["b"]
        for term in counts:
            rows = postings.get(term, ())
            idf = math.log(1 + (n - len(rows) + .5) / (len(rows) + .5))
            for doc, tf in rows:
                score[doc] += idf * tf * (k1 + 1) / (tf + k1 * (1 - b + b * lengths[doc] / avgdl))
    else:
        raise ValueError("unknown fixed method")
    return sorted(score, key=lambda doc: (-score[doc], doc))[:20]


def metrics(ranking, relevant):
    relevant = set(relevant)
    result = {f"recall@{k}": len(set(ranking[:k]) & relevant) / len(relevant) if relevant else 0.
              for k in (5, 10, 20)}
    result["mrr@10"] = next((1 / (i + 1) for i, doc in enumerate(ranking[:10]) if doc in relevant), 0.)
    dcg = sum(1 / math.log2(i + 2) for i, doc in enumerate(ranking[:10]) if doc in relevant)
    ideal = sum(1 / math.log2(i + 2) for i in range(min(10, len(relevant))))
    result["ndcg@10"] = dcg / ideal if ideal else 0.
    return result


def metric_checks():
    result = metrics(["a", "b", "c"], {"b", "c"})
    assert result["recall@5"] == 1 and result["mrr@10"] == .5
    assert abs(result["ndcg@10"] - ((1 / math.log2(3) + .5) / (1 + 1 / math.log2(3)))) < 1e-12
    assert all(v == 0 for v in metrics(["z"], set()).values())
    assert all(v == 0 for v in metrics(["z"], {"x"}).values())
    tiny = {"a": {"title": "cat", "text": "cat"}, "b": {"title": "dog", "text": "dog"}}
    for method in ("tfidf_cosine", "bm25"):
        assert retrieve("cat", build_index(tiny), method) == ["a"]
        assert retrieve("unknown", build_index(tiny), method) == []
    return {"manual_metric_cases": 3, "tiny_retrieval_cases": 4, "passed": True}


def retrieval_benchmark(inputs, output, frozen):
    docs, queries = read_jsonl(inputs / FILES[0]), read_jsonl(inputs / FILES[1])
    started = time.perf_counter()
    index = build_index(docs)
    index_seconds = time.perf_counter() - started
    ranks = []
    with (output / "retrieval-rankings.jsonl").open("x") as log:
        for split, qids in frozen["splits"].items():
            for qid in qids:
                for method in ("tfidf_cosine", "bm25"):
                    started = time.perf_counter()
                    ranking = retrieve(queries[qid]["text"], index, method)
                    row = {"split": split, "query_id": qid, "method": method, "ranking": ranking,
                           "ranking_seconds": time.perf_counter() - started}
                    ranks.append(row)
                    log.write(json.dumps(row) + "\n")
    # Gold is loaded only after both fixed methods' complete rankings are on disk.
    gold = {"dev": read_qrels(inputs / "scifact/qrels/train.tsv"),
            "test": read_qrels(inputs / "scifact/qrels/test.tsv")}
    rows = []
    for row in ranks:
        relevant = gold["test" if row["split"] == "test" else "dev"][row["query_id"]]
        rows.append({**row, "metrics": metrics(row["ranking"], relevant)})
    with (output / "retrieval-per-query.jsonl").open("x") as log:
        for row in rows:
            log.write(json.dumps(row) + "\n")
    summary = {"documents": len(docs), "index_seconds": index_seconds, "splits": {}}
    for split in frozen["splits"]:
        group = [row for row in rows if row["split"] == split]
        arms = {}
        for method in ("tfidf_cosine", "bm25"):
            arm = [row for row in group if row["method"] == method]
            arms[method] = {"queries": len(arm),
                            "metrics": {key: statistics.mean(r["metrics"][key] for r in arm) for key in arm[0]["metrics"]},
                            "mean_ranking_seconds": statistics.mean(r["ranking_seconds"] for r in arm),
                            "empty_rankings": sum(not r["ranking"] for r in arm)}
        paired = {qid: {r["method"]: r for r in group if r["query_id"] == qid} for qid in frozen["splits"][split]}
        delta = {key: [v["bm25"]["metrics"][key] - v["tfidf_cosine"]["metrics"][key] for v in paired.values()]
                 for key in arms["bm25"]["metrics"]}
        summary["splits"][split] = {"arms": arms, "paired_candidate_minus_baseline": {
            key: {"mean": statistics.mean(ds), "wins": sum(d > 1e-12 for d in ds),
                  "ties": sum(abs(d) <= 1e-12 for d in ds), "losses": sum(d < -1e-12 for d in ds)}
            for key, ds in delta.items()}}
    return summary


def jobs_for(seed, n):
    rng = random.Random(seed * 100000 + n)
    jobs = []
    for i in range(n):
        start = rng.randrange(10 * n + 1)
        jobs.append((start, start + rng.randint(1, max(2, n // 4)), rng.randint(1, 100), i))
    return jobs


def schedule(jobs, binary):
    ordered = sorted(jobs, key=lambda job: (job[1], job[0], job[3]))
    ends = [job[1] for job in ordered]
    dp, parents, taken, operations = [0], [0], [False], 0
    for i, (start, end, weight, job_id) in enumerate(ordered):
        if binary:
            previous = bisect.bisect_right(ends, start, 0, i)
        else:
            previous = 0
            operations += i
            for j in range(i):
                if ends[j] <= start:
                    previous = j + 1
        pick = dp[previous] + weight
        take = pick > dp[-1]
        dp.append(pick if take else dp[-1])
        parents.append(previous if take else i)
        taken.append(take)
    selected, i = [], len(ordered)
    while i:
        if taken[i]:
            selected.append(ordered[i - 1][3])
        i = parents[i]
    return {"objective": dp[-1], "schedule": list(reversed(selected)), "full_scan_comparisons": operations}


def verify_schedule(jobs, result):
    ids = result["schedule"]
    assert len(ids) == len(set(ids))
    lookup = {job[3]: job for job in jobs}
    chosen = sorted((lookup[i] for i in ids), key=lambda j: j[0])
    assert all(a[1] <= b[0] for a, b in zip(chosen, chosen[1:]))
    assert sum(j[2] for j in chosen) == result["objective"]


def brute_force(jobs):
    optimum = 0
    for mask in range(1 << len(jobs)):
        chosen = sorted((j for i, j in enumerate(jobs) if mask & (1 << i)), key=lambda j: j[0])
        if all(a[1] <= b[0] for a, b in zip(chosen, chosen[1:])):
            optimum = max(optimum, sum(j[2] for j in chosen))
    return optimum


def algorithm_benchmark(output):
    correctness = []
    edge_cases = [[], [(0, 1, 1, 0), (1, 2, 2, 1)],
                  [(0, 2, 2, 0), (0, 2, 3, 1)], [(0, 1, 0, 0), (0, 1, 0, 1)]]
    for case_id, jobs in enumerate(edge_cases + [jobs_for(seed, 12) for seed in range(700, 724)]):
        optimum = brute_force(jobs)
        for binary in (False, True):
            result = schedule(jobs, binary)
            verify_schedule(jobs, result)
            assert result["objective"] == optimum
        correctness.append({"case": case_id, "input_sha256": value_hash(jobs), "n": len(jobs), "optimum": optimum, "passed": True})
    for split, seeds, n in (("dev", [101, 102], 32), ("validation", [201, 202], 64)):
        for seed in seeds:
            jobs = jobs_for(seed, n)
            a, b = schedule(jobs, False), schedule(jobs, True)
            verify_schedule(jobs, a)
            verify_schedule(jobs, b)
            assert a["objective"] == b["objective"] and a["schedule"] == b["schedule"]
            correctness.append({"split": split, "seed": seed, "n": n,
                                "input_sha256": value_hash(jobs), "objective": a["objective"], "passed": True})
    save(output / "algorithm-correctness.json", correctness)
    rows, cases = [], []
    with (output / "algorithm-timings.jsonl").open("x") as log:
        for n in CONFIG["algorithm_sizes"]:
            for seed in CONFIG["algorithm_test_seeds"]:
                jobs = jobs_for(seed, n)
                results = {}
                for repeat in range(CONFIG["repeats"]):
                    for binary in ((False, True) if repeat % 2 == 0 else (True, False)):
                        started = time.perf_counter()
                        result = schedule(jobs, binary)
                        seconds = time.perf_counter() - started
                        verify_schedule(jobs, result)
                        arm = "binary_search_dp" if binary else "quadratic_scan_dp"
                        row = {"split": "test", "seed": seed, "n": n, "repeat": repeat,
                               "method": arm, "seconds": seconds, "objective": result["objective"],
                               "schedule_sha256": value_hash(result["schedule"]),
                               "input_sha256": value_hash(jobs), "full_scan_comparisons": result["full_scan_comparisons"]}
                        results[arm] = result
                        rows.append(row)
                        log.write(json.dumps(row) + "\n")
                    assert results["binary_search_dp"]["objective"] == results["quadratic_scan_dp"]["objective"]
                    assert results["binary_search_dp"]["schedule"] == results["quadratic_scan_dp"]["schedule"]
                times = {arm: statistics.median(r["seconds"] for r in rows if r["n"] == n and r["seed"] == seed and r["method"] == arm)
                         for arm in results}
                cases.append({"n": n, "seed": seed, "median_seconds": times,
                              "speedup_baseline_over_candidate": times["quadratic_scan_dp"] / times["binary_search_dp"],
                              "correct_objective_and_schedule": True})
    return {"kind": "synthetic_engineering_known_exact_algorithm_code_optimization",
            "correctness_cases": len(correctness), "test_cases": cases,
            "baseline_complexity": "O(n^2)", "candidate_complexity": "O(n log n)",
            "algorithm_discovery": False}


def run(output):
    frozen = json.loads((output / "freeze.json").read_text())
    inputs = Path(frozen["input_dir"])
    assert not (output / "attempt.json").exists(), "attempt already exists; never overwrite"
    assert digest(SCRIPT) == frozen["script_sha256"] and digest(PROTOCOL) == frozen["protocol_sha256"], "frozen code/protocol changed"
    assert frozen["config"] == CONFIG
    assert all(digest(inputs / f) == sha for f, sha in frozen["inputs"].items())
    assert shutil.disk_usage(output).free >= 5 * 1024**3
    save(output / "attempt.json", {"started_utc": datetime.now(timezone.utc).isoformat(),
                                   "freeze_sha256": digest(output / "freeze.json"), "config": CONFIG})
    resource.setrlimit(resource.RLIMIT_CPU, (120, 130))
    resource.setrlimit(resource.RLIMIT_AS, (CONFIG["as_bytes"], CONFIG["as_bytes"]))
    resource.setrlimit(resource.RLIMIT_FSIZE, (32 * 1024**2, 32 * 1024**2))
    def expired(signum, frame):
        raise TimeoutError("fixed wall/CPU budget expired")
    signal.signal(signal.SIGALRM, expired)
    signal.signal(signal.SIGXCPU, expired)
    signal.alarm(CONFIG["wall_seconds"])
    started, cpu = time.perf_counter(), time.process_time()
    try:
        checks = metric_checks()
        retrieval = retrieval_benchmark(inputs, output, frozen)
        algorithm = algorithm_benchmark(output)
        summary = {"status": "completed_fixed_local_benchmark", "metric_checks": checks,
                   "retrieval": retrieval, "algorithm": algorithm,
                   "measured": {"wall_seconds": time.perf_counter() - started,
                                "cpu_seconds": time.process_time() - cpu,
                                "max_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss},
                   "cost": {"program_model_calls": 0, "external_api_calls_during_run": 0,
                            "development_tokens": None, "currency": None, "amount": None},
                   "environment": {"python": sys.version, "platform": platform.platform(), "threads": 1},
                   "limitations": ["No workbench adapter integration", "No claim verification/generation", "Known public benchmark, no statistical significance", "Synthetic scheduling is engineering optimization, not scientific discovery", "No cgroup isolation or RSI"]}
        save(output / "summary.json", summary)
        save(output / "errors.json", [])
        print(json.dumps({"status": summary["status"], "wall_seconds": summary["measured"]["wall_seconds"],
                          "test_metrics": retrieval["splits"]["test"]}))
    except BaseException as error:
        save(output / "errors.json", [{"type": type(error).__name__, "message": str(error),
                                        "wall_seconds": time.perf_counter() - started}])
        raise
    finally:
        signal.alarm(0)
        save(output / "manifest.json", {"files": {p.name: digest(p) for p in output.iterdir() if p.is_file() and p.name != "manifest.json"},
                                         "script_sha256": digest(SCRIPT), "protocol_sha256": digest(PROTOCOL)})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("prepare", "run"))
    parser.add_argument("--input-dir", type=Path, default=Path("/workspace/work/g5-cpu-inputs"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.mode == "prepare":
        prepare(args.input_dir.resolve(), args.output.resolve())
    else:
        run(args.output.resolve())


if __name__ == "__main__":
    main()
