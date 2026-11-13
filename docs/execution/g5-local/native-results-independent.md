# Native CPU cases: independent saved-artifact verification

2026-11-13. **Passed: 9,910 checks, first attempt, exit 0.** The pre-run frozen verifier was used unchanged. This is native lifecycle replication of public, already visible standalone outcomes; it is not a fresh unseen evaluation. Neither method was automatically promoted. Both projects remain `research_status=waiting` after completed execution.

Producer source commit: `8e8a206ed0b71479a6e774e36ed91fdb06e21c22`. Verifier SHA-256: `ba82a2afe5e765ccf02ac12765cbfb6f2213a0b815f6d0f4f12e539176cf2f0d`. Verification receipt: `runs/g5-native-independent-20261113-01/verification.json`, SHA-256 `b6a252e12a4d11e0cd50b596bfd1d1b637054b8f83047d49e84358f0ba761d9c`. The [complete JSON summary](native-results-independent.json) preserves all split metrics, all 133 adverse queries, all 16 input hashes/optima, per-case measurements, report/source manifests, and evidence identities.

## Lifecycle and preservation

Each case has one primary action and one saved-result audit, exact source/request/result/envelope/parent links, three sequential research plan revisions, and the existing four-file report export. The reports retain complete original ToolResults and source packets; Markdown/PDF summaries do not replace the full JSON. Each project used exactly 2/2 local tools, 0/0 source reads, 0 fits and 0 model/API requests; no reservations remain. Guard counters for network, source extraction, scaler fit and Ridge fit are all zero. Cash history and development token/currency costs remain unknown.

| Case | Project ID | Source snapshot |
|---|---|---|
| retrieval | `project-b0ad79226f0a454b99b604e373e39bbb` | `2ff1e33fc9b780037338f9916b9430bd6502029058ccd5386334af1e2b430895` |
| scheduling | `project-148dac5d531144008498449cb16a54ea` | `08ebf6433efb414ff139197036f5fa419ffe9e0f11037954f537d5a80e8b678d` |

Project-manager bytes were identical before/after the verifier reads. The original Concrete 101, Real Estate 101 and Slump 90 files (292 total), five frozen G4 controls, and 11 standalone CPU evidence files were unchanged. Protection receipts are saved beside the verification receipt. Same-ID and relocation replay are outside this verification; no replay was requested or executed.

## Citation retrieval

All 920 saved rankings (460 queries × 2 methods) match the standalone originals exactly, as do all 920 per-query metric rows, every split macro metric and every win/tie/loss count. Five metrics were independently recomputed from saved ranks and original citation qrels with relative/absolute tolerance `1e-12`; there was no independent reranking or index execution. The original inputs contain 5,183 documents and 1,109 queries; train has 809 queries/919 pairs, test 300 queries/339 pairs. Frozen dev/validation/test IDs remain 80/80/300.

Baseline is TF-IDF cosine; candidate is fixed BM25. Table values are macro scores; W/T/L refer to paired query differences (candidate minus baseline).

| Split | Metric | TF-IDF | BM25 | Δ | W/T/L |
|---|---|---:|---:|---:|---:|
| dev | recall@5 | 0.703125 | 0.696875 | -0.006250 | 1/78/1 |
| dev | recall@10 | 0.750000 | 0.775000 | +0.025000 | 2/78/0 |
| dev | recall@20 | 0.800000 | 0.825000 | +0.025000 | 4/74/2 |
| dev | mrr@10 | 0.649911 | 0.653869 | +0.003958 | 7/70/3 |
| dev | ndcg@10 | 0.672456 | 0.684375 | +0.011920 | 11/66/3 |
| validation | recall@5 | 0.768750 | 0.754167 | -0.014583 | 2/75/3 |
| validation | recall@10 | 0.837500 | 0.831250 | -0.006250 | 1/77/2 |
| validation | recall@20 | 0.850000 | 0.843750 | -0.006250 | 0/79/1 |
| validation | mrr@10 | 0.656939 | 0.684633 | +0.027693 | 11/61/8 |
| validation | ndcg@10 | 0.696567 | 0.712845 | +0.016278 | 13/58/9 |
| test | recall@5 | 0.741556 | 0.724278 | -0.017278 | 8/276/16 |
| test | recall@10 | 0.778500 | 0.787611 | +0.009111 | 12/280/8 |
| test | recall@20 | 0.840278 | 0.829222 | -0.011056 | 5/286/9 |
| test | mrr@10 | 0.594004 | 0.626970 | +0.032966 | 56/208/36 |
| test | ndcg@10 | 0.632911 | 0.660464 | +0.027553 | 58/202/40 |

Bad outcomes remain visible: test Recall@5 falls by 0.017278 (16 query losses) and Recall@20 falls by 0.011056 (9 losses), although MRR@10/nDCG@10 improve. The complete adverse union contains 21 dev, 20 validation and 92 test queries: any metric loss, or either arm Recall@20 below 1. For test query `1280`, Recall@20 drops from 1 to 0. For dev query `762`, it also drops from 1 to 0. All 133 full adverse rows are retained in the JSON summary and primary/audit artifacts.

The native primary saved one index build, 920 ranking calls and 920 scoring calls; saved index time is 0.767758 s. The saved audit made zero index, ranking or scoring calls. These are producer records; this verifier performed none of those operations.

Qrels mean `cited_doc_ids`, not support/refute judgements. The 693 nonempty original query metadata objects can contain SUPPORT/CONTRADICT sentence annotations; metadata is opaque to ranking/scoring and the dataset is not sealed. Claims/qrels carry CC BY 4.0 declarations, abstracts ODC-By 1.0. Original bytes and attribution are preserved; this verification does not independently establish licences or provenance facts.

## Weighted interval scheduling

All 16 original synthetic job sets retain their hashes, order and IDs. All 80 saved runs (72 test plus 8 dev/validation) have unique known selected jobs, feasible schedules, correct selected-weight objectives, correct reconstruction order/hashes, and identical paired schedules. All objectives match a separate coordinate-compressed Fenwick optimum. Test definitions/objectives/schedule hashes/full-scan counts match all 72 old saved runs; the four dev/validation definitions and optima also match. No production solver was called and no timing was repeated.

The table shows native saved medians (milliseconds), whose arithmetic was verified; test medians use three runs per arm, dev/validation one. Exact timing equality with the old run is not claimed.

| Case | Fenwick optimum | Scan ms | Binary ms | Speedup |
|---|---:|---:|---:|---:|
| dev-n32-seed101 | 1349 | 0.048773 | 0.020852 | 2.339× |
| dev-n32-seed102 | 1329 | 0.029694 | 0.035363 | 0.840× |
| validation-n64-seed201 | 2098 | 0.076004 | 0.026770 | 2.839× |
| validation-n64-seed202 | 2204 | 0.130476 | 0.026510 | 4.922× |
| test-n128-seed303 | 3320 | 0.256065 | 0.054232 | 4.722× |
| test-n128-seed404 | 3580 | 0.200962 | 0.049885 | 4.029× |
| test-n128-seed505 | 3374 | 0.238478 | 0.048794 | 4.887× |
| test-n512-seed303 | 7543 | 3.794082 | 0.234833 | 16.157× |
| test-n512-seed404 | 6694 | 3.754684 | 0.239089 | 15.704× |
| test-n512-seed505 | 7047 | 3.589735 | 0.228684 | 15.697× |
| test-n2048-seed303 | 13826 | 77.580115 | 1.133183 | 68.462× |
| test-n2048-seed404 | 15528 | 72.875504 | 1.123528 | 64.863× |
| test-n2048-seed505 | 14687 | 74.740045 | 1.263189 | 59.168× |
| test-n4096-seed303 | 20916 | 306.784681 | 2.596001 | 118.176× |
| test-n4096-seed404 | 19373 | 327.121959 | 2.721461 | 120.201× |
| test-n4096-seed505 | 21117 | 328.279057 | 3.103915 | 105.763× |

The candidate is slower for `dev-n32-seed102`: 0.035363 ms versus 0.029694 ms, +0.005669 ms (0.840×). It is faster on the other 15 cases, including all 12 test cases. The slower case is preserved in both primary and saved audit. These small, synthetic timings do not establish statistical confidence or production/end-to-end speedup. This compares known exact algorithms; it is not new algorithm discovery.

The native primary records 95,599,712 quadratic pair evaluations across its saved runs. Per run, scan comparisons equal n(n−1)/2; candidate scan comparisons are zero, with n DP steps and n bisect calls. Internal C bisect comparisons remain `null` (unknown), not zero. Reconstruction steps were independently checked against the saved selected path. The saved audit records zero solver, brute-force and new-timing calls. All 16 workload hashes and operations for every saved repetition are in the JSON summary; full jobs/schedules remain in the existing report and action JSON.

## Scope

This verifies stored numerical evidence, source/lifecycle bindings, reports and preservation. It does not independently rank the corpus, validate scientific claims, rerun the production DP, remeasure performance, or test same-ID/relocation replay. The entry point is host assisted; `LocalWorkbench.create` still accepts CSV. Trusted local success does not change the original failed resource-isolation gate. No project, budget, original case or frozen control was written by this verifier.

Raw evidence: `runs/g5-native-independent-20261113-01/`; native cases: `runs/g5-native-cases-20261113-01/{retrieval,scheduling}/`; old evidence: `runs/g5-local-cpu-20261113-01/`.
