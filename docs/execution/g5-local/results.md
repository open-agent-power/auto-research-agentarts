# G5-L CPU transfer experiment results

On 2026-11-13, the single fixed-code local attempt completed in **10.531s wall / 10.515s CPU**, peak process RSS **84,944 KiB**. No model, embedding service, generation or LLM judge was called. These are two standalone CPU experiment packs, not evidence that the same research workbench is connected to both tasks, full G5 acceptance, autonomous researcher performance or RSI. G0 resource/upstream runtime limitations remain.

## Frozen identity and execution

- Prior protocol: [protocol.md](protocol.md); fixed implementation: `scripts/run_cpu_transfer_benchmarks.py`.
- Raw attempt: `runs/g5-local-cpu-20261113-01/`; freeze SHA256 `759d15473a64f45f855f5c455ddb6329bac229885d077424d381df3ef25f6af8`, script SHA256 `f9e51cd73b3c25daa2c3c34b0748cd999be0e0c130a5c373e96b7fc63a032b1a`.
- `authorization-link.json` binds the existing freeze to root's new `docs/execution/local-continuation.json` and CPU slot before execution; the original freeze was not backdated/rewritten. Prior Concrete project and exhausted estimator allowance were untouched.
- `prepare` completed before scores/timing and verified original data identity, fixed parameters, dev/validation/test query IDs, workload seeds and code/protocol/input hashes. It **read relevance labels for source integrity**. During `run`, ranking functions have no qrels input and all rankings are written before scoring reads labels. This is procedural fixed-code separation, not sealed labels, absence of prior benchmark familiarity or OS protection.
- One process, fixed 180s wall / 120s CPU soft / 130s CPU hard / 1 GiB address-space / 32 MiB file limits; >5 GiB disk headroom. No BLAS dependency; thread environment fixed to one. Process safeguards do not repair missing cgroup delegation.

## Real public-data retrieval result

SciFact/BEIR data: 5,183 documents; dev 80 and validation 80 preselected from BEIR train, test all 300 BEIR-test queries. Original-source data license and exact identity are in [source-provenance.md](source-provenance.md). BEIR test corresponds to original SciFact **dev** and relevance equals cited documents, not support/refute labels. No fact verification/domain assessment claim.

| Test metric (macro over 300 queries) | TF-IDF cosine | BM25 | BM25 − TF-IDF | Wins / ties / losses |
|---|---:|---:|---:|---:|
| Recall@5 | 0.741556 | 0.724278 | **−0.017278** | 8 / 276 / 16 |
| Recall@10 | 0.778500 | 0.787611 | +0.009111 | 12 / 280 / 8 |
| Recall@20 | 0.840278 | 0.829222 | **−0.011056** | 5 / 286 / 9 |
| MRR@10 | 0.594004 | 0.626970 | +0.032966 | 56 / 208 / 36 |
| nDCG@10 | 0.632911 | 0.660464 | +0.027553 | 58 / 202 / 40 |

BM25 improved early ranking metrics in this fixed implementation but reduced coverage at K=5 and K=20. It is not an across-the-board winner. Preserve TF-IDF as a comparison/coverage option; do not automatically replace the default. No hyperparameter was changed after seeing development, validation or test scores. No significance, unpublished-test generalization, published-BEIR comparability, answer faithfulness or user-value claim is made.

Per-query rankings and metrics for all 920 arm/query pairs (460×2), including every loss/tie, are in `retrieval-rankings.jsonl` / `retrieval-per-query.jsonl`. Test average query ranking time was ~6.38ms TF-IDF versus ~6.03ms BM25 on this run; this single-host difference is descriptive, without separate-process memory or robust latency inference. Indexing is shared and its measured duration is in `summary.json`.

## Synthetic scheduling/code optimization

Weighted interval scheduling is an engineering workload with a known exact DP. Both arms use the same recurrence; baseline scans all earlier ends, candidate binary-searches the predecessor. This is an implementation/complexity optimization, not invention of a new algorithm or validation of a scientific hypothesis.

Correctness passed 4 edge cases + 24 n=12 exhaustive-subset cases + 4 separate development/validation cases. All 12 fixed independent test cases × 3 repeats produced exactly matching optimum **and selected schedule**, with feasibility independently checked by the runner. Raw workload hashes, objectives, schedules' hashes, operation counts and every timing remain in `algorithm-correctness.json` / `algorithm-timings.jsonl`.

| Intervals n | Median speedup across 3 fixed test seeds | Range of case median speedups |
|---|---:|---:|
| 128 | 4.39× | 4.38–4.65× |
| 512 | 14.23× | 13.53–14.31× |
| 2,048 | 56.83× | 55.09–57.12× |
| 4,096 | 107.18× | 104.91–109.34× |

The n² reference is a reasonable straightforward exact DP, not a competitive optimized library. Large speedups demonstrate avoiding its full predecessor scan on these generated cases; they do not compare against state-of-the-art scheduling systems. Fixed random seeds, small sample and submillisecond small-n timings limit inference. No slower test case appeared in this attempt; no cases were discarded.

## Errors, cost and next decision

`errors.json` is empty; all final manifest file hashes revalidated after execution. Metric checks include a hand-calculable nDCG example, no-hit/no-relevance cases and tiny lexical checks. Independent review recomputation is separate from implementation's own checks and must be reported by its owner.

Actual program model/API calls: **0**. Development/tool token totals, infrastructure charge and currency cost are **unknown**, not zero. Public source retrieval happened before the network-free benchmark and is separately attributable; no provider inference billing was incurred by the program.

Recommended next slice: wire the fixed retrieval runner behind an explicit native task/observation/artifact contract, then evaluate a different licensed corpus/query set without tuning on this test. Preserve the coverage losses when choosing a method. For algorithms, retain the exact binary-search DP as the engineering baseline and use an independent task family before claiming transfer. Root must decide task integration under the trusted-local exception; no automatic promotion, self-modification or additional Concrete estimator attempts are authorized by these results.
