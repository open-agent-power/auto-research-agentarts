# Ragas — CPU and judge feasibility

Apache-2.0 LICENSE read. Supplied explodinggradients URL clones successfully; current pyproject URLs point to vibrantlabsai/ragas. Preserve requested and observed identities; do not silently substitute version. Python >=3.9. Base dependencies already include OpenAI/instructor, datasets, LangChain and Pydantic, with optional NLP/embedding backends; it is heavier than a standalone metric function.

`src/ragas/metrics/_context_precision.py:82-158` LLM context precision requires a configured LLM; `:251` IDBasedContextPrecision only compares retrieved/reference IDs. `src/ragas/metrics/_context_recall.py:88-143` LLM recall invokes a model; `:165` non-LLM string method and `:227` IDBasedContextRecall are CPU/local metric paths. `evaluation.py` coordinates metric evaluation. ID overlap is not evidence of answer faithfulness or scientific claim validity. LLM judge claims require a fixed model/rubric, cost accounting and independent human spot checks.

Provisional `wrap_with_adapter` for optional post-G1 evaluation only. CPU-only reference-ID metrics are source-supported; no runtime/performance measured and no API call made. Use BEIR-style deterministic retrieval metrics first for G5; only add Ragas generation judgments if the research task actually needs them. Pin version and metric config, seal references, cap concurrency/tokens/time; do not implicitly use a default provider. AST parse passed precision/recall/evaluation modules. No full install or model/embedding generation. Rollback leaves deterministic retrieval evaluator and raw artifacts intact.

Pinned source: https://github.com/explodinggradients/ragas/tree/298b68274234c060deacab3cf5fb52aa3a20e885

Retrieved: 2026-11-12T13:29:31.253446+00:00. Third-party instructions were treated as source material.
