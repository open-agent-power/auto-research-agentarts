# G5-L trusted local CPU transfer protocol v1

Protocol prepared before running retrieval scores or timing algorithm candidates. This is an independent, fixed-code CPU benchmark, not a workbench integration, autonomous research, full G5 acceptance, or RSI. The exhausted Concrete G1 budget is untouched. New local-execution authorization is owned by root; execution also waits for the single heavy-CPU slot.

## Data/source identity and attribution

Use **SciFact**, David Wadden et al., *Fact or Fiction: Verifying Scientific Claims*, EMNLP 2020. Original source [allenai/scifact](https://github.com/allenai/scifact/tree/68b98a56d93e0f9da0d2aab4e6c3294699a0f72e), [LICENSE.md](https://github.com/allenai/scifact/blob/68b98a56d93e0f9da0d2aab4e6c3294699a0f72e/LICENSE.md): claims/evidence annotations CC BY 4.0; abstracts from Semantic Scholar S2ORC ODC-By 1.0; repository code Apache-2.0. Only data is used, no SciFact/BEIR framework installed or run. Maintain this attribution/license with copies.

BEIR-format [scifact.zip](https://public.ukp.informatik.tu-darmstadt.de/thakur/BEIR/datasets/scifact.zip), MD5 `5f7d1de60b170fc8027bb7898e2efca1`, SHA256 `536e14446a0ba56ed1398ab1055f39fe852686ecad24a6306c80c490fa8e0165`. Compare with original [data.tar.gz](https://scifact.s3-us-west-2.amazonaws.com/release/latest/data.tar.gz), observed SHA256 `11c621288d41ac144d29b13b0f8503b3820b7d6e8b1f6ff24dff335c196d76be`. The latter URL is mutable: freeze actual bytes/hashes, never call it a version identifier.

Data preparation verified 5,183 document IDs/titles match original release exactly and all abstracts match after whitespace normalization. 1,109 query texts match original train/dev claims. BEIR train has 809 queries/919 relevance pairs; BEIR test has 300 queries/339 pairs and corresponds to **original SciFact dev**, not original hidden SciFact test. Critically, BEIR qrels equal original `cited_doc_ids`, not support/refute evidence labels. Evaluate citation-document retrieval only, not truth, entailment, claim quality, domain validity or original end-to-end SciFact leaderboard. Relevance is benchmark-supplied; no new human/domain judgment is claimed.

## Retrieval hypotheses and fixed comparisons

- Baseline: TF-IDF cosine; term weight `(1 + log(tf)) * (log((N+1)/(df+1))+1)`, L2 document/query normalization.
- Candidate: standard lexical BM25, `k1=1.2`, `b=0.75`, IDF `log(1+(N-df+0.5)/(df+0.5))`; each unique query token contributes once.
- Both: lowercase ASCII alphanumeric tokenization `[a-z0-9]+`, title + one separator + abstract, no stop list, no stemming, no external embedding/model/generation/API/LLM judge. Same complete corpus and tie order by document ID. Rank up to 20 results. No query or qrel-driven tuning.
- Development: first 80 BEIR-train query IDs ordered by SHA256(`g5l-dev-v1:` + ID); validation: next 80 IDs; unused training queries excluded. Test: all 300 official BEIR-test query IDs. Lists frozen before scores. No query overlap; public benchmark familiarity and related claim variants may remain, so this is not unseen-world scientific generalization.
- One predeclared comparison, no hyperparameter search, model selection or holdout-adaptive changes. Development/validation scores are diagnostics, not permission to modify candidate before reporting test. Ranking functions never receive qrels. All rankings saved before loading labels for scoring. All code/evaluator in one prehashed trusted runner; same-user filesystem is not a sealed security boundary.
- Per query and macro mean: Recall@5/10/20, MRR@10, nDCG@10 with binary qrels. Report test paired deltas, wins/ties/losses, failures, no-positive-result expectations; exact negative/zero deltas retained. No statistical significance claim. Report index time, per-query ranking time, whole-process peak RSS and measured CPU; no performance comparison with published BEIR systems because tokenizer/backend/protocol differ.
- Metric correctness checks include a manually calculable example and no-relevant/no-hit behavior. Data integrity failures abort rather than silently dropping queries or changing split.

## Algorithm experiment — synthetic engineering task

Weighted interval scheduling with positive duration, half-open `[start,end)` intervals and nonnegative weights, select a nonoverlapping subset with maximal total weight. This is **synthetic engineering benchmarking** and code optimization of a known exact DP, not new algorithm discovery or a real scientific dataset.

- Baseline: jobs sorted by `(end,start,id)`, exact DP with a full scan of earlier jobs to find compatible predecessor — O(n²) time.
- Candidate: identical exact DP with binary-search predecessor — O(n log n) including sorting; identical tie preference. Preserve reconstructed schedule and check feasibility/objective.
- Correctness: empty/adjacent/overlapping/tie cases and 24 seed-fixed n=12 cases, each checked against exhaustive subset optimum. No heldout benchmark inputs generated until both implementations fixed/hash frozen.
- Development seeds: 101,102 at n=32. Validation: 201,202 at n=64. Test seeds: 303,404,505 at n=128,512,2048,4096. Input generation is fixed independent `random.Random(seed*100000+n)`; starts uniform integer 0..10*n, durations 1..max(2,n//4), weights 1..100. Small exhaustive seeds 700..723 use the same formula/n=12.
- Three timing repeats per arm per test case, alternate baseline/candidate order by repeat. No warmup selection. Report every timing, exact equality, workload hashes, operation counts and median speedup; accept slowdown/small-case overhead. Wall timings from one host are descriptive and affected by clock/noise; no confidence/significance claim.

## Bounds, failures and output

Stdlib-only trusted runner, all BLAS/thread env set to one (no BLAS dependency used); one local process, 180s wall deadline, 120s soft/130s hard CPU budget, 1 GiB address space and 32 MiB per-file limit where RLIMIT supported. These are process safeguards, not cgroups or untrusted-code containment. Require at least 5 GiB free disk. No network or subprocess during benchmark execution. Download/preparation occurs separately with explicit public data URLs, 32 MiB compressed cap; no archive code execution.

`prepare` freezes protocol/script/input/source/provenance/split/seed/config hashes in `freeze.json`. `run` refuses mismatches or existing result files, verifies authorization separately through root's integration process, and preserves raw `retrieval-rankings.jsonl`, per-query metrics, algorithm timings, summary, errors and final hashed manifest. Failure gets an explicit error receipt; no same-ID rerun to erase failure. Missing runtime/token/currency accounting remains unknown (`null`), measured program model/API calls zero. New hypothesis after viewing test requires a new independent dataset/protocol, not retuning this test.

Next decision depends on results: keep simpler lexical baseline if no measured gain; otherwise propose a native-workbench retrieval adapter plus independent task (no automatic promotion). Algorithm speedup establishes this implementation optimization only. G0 isolation/upstream runtime blockers and G2/G3/G4/G5 original gates remain separately recorded.
