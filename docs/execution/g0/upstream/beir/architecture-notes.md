# BEIR — CPU retrieval feasibility

Apache-2.0 source license (retain LICENSE/NOTICE/modified-file notices if applicable). `pyproject.toml` v2.2.0 requires Python >=3.9; dependencies sentence-transformers, pytrec-eval-terrier and datasets; Elasticsearch 7.9.1 and faiss-cpu are optional extras. CPU-capable algorithms do not imply a lightweight default dependency closure.

`beir/datasets/data_loader.py` reads corpus/query/qrels. `beir/retrieval/evaluation.py:69-122` uses pytrec_eval for NDCG/MAP/Recall/Precision, `:125` custom metrics. `beir/retrieval/search/lexical/bm25_search.py:16-45` instantiates Elasticsearch, so the bundled BM25 example is not a no-service in-memory baseline. Dense retrieval can run small embeddings on CPU but requires actual model download, bounded batches and measured RAM/time; not tested here.

README dataset table lists SciFact ~5K docs/300 test queries and NFCorpus ~3.6K/323 queries. These are plausible small CPU candidates, not downloaded or benchmarked. README:393 explicitly says dataset permissions remain independent of BEIR's code license. Freeze corpus/query/qrels hashes and check original dataset licensing before any G5 use; keep evaluator/qrels out of candidate worktree. Pure retrieval Recall/MRR/nDCG needs no LLM judge or API credentials.

Provisional `wrap_with_adapter`: reuse schema/evaluator behind a fixed-corpus task after G1, avoid pulling in Elasticsearch/large model runtime merely to evaluate scores. Required PoC: deterministic score fixture → adapter correctness, then real licensed corpus baseline with measured latency/RAM/disk and sealed heldout query split. AST parse passed loader/evaluation/BM25 files. No installation or retrieval run occurred. Revert by disabling optional benchmark adapter, preserving task manifests/raw results.

Pinned source: https://github.com/beir-cellar/beir/tree/ef83d29307061c65d04b035b4f4e7c18bd8374af

Retrieved: 2026-11-12T13:29:31.253446+00:00. Third-party instructions were treated as source material.
