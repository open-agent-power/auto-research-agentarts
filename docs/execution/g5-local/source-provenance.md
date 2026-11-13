# SciFact source, license and split provenance

Data authors: David Wadden, Shanchuan Lin, Kyle Lo, Lucy Lu Wang, Madeleine van Zuylen, Arman Cohan and Hannaneh Hajishirzi, **Fact or Fiction: Verifying Scientific Claims**, EMNLP 2020. Abstracts derive from Semantic Scholar S2ORC. BEIR provides the retrieval-format redistribution. Attribution must accompany copied data/results.

## Original source

Original repository HEAD independently resolved to [`68b98a56d93e0f9da0d2aab4e6c3294699a0f72e`](https://github.com/allenai/scifact/tree/68b98a56d93e0f9da0d2aab4e6c3294699a0f72e). Official README identifies original release URL, claim/corpus schema and unreleased original test labels. The exact [LICENSE.md](https://raw.githubusercontent.com/allenai/scifact/68b98a56d93e0f9da0d2aab4e6c3294699a0f72e/LICENSE.md) explicitly separates:

- Claims/evidence annotations (`claims_*.jsonl`): [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/).
- Abstract corpus (`corpus.jsonl`), part of S2ORC: [ODC-By 1.0](https://opendatacommons.org/licenses/by/1-0/).
- Repository code: Apache-2.0. No code is installed/imported/run; code licensing alone was not used as dataset permission.

License local bytes: `/workspace/work/g5-cpu-inputs/SCIFACT-LICENSE.md`, SHA256 `56ee69bc639cbab8f0b2e4b67091ec5e9390aa99a1d65f0a35e4274686c9a806`.

## Downloaded data and independent matching

Data-only downloads used inherited HTTPS trust/proxy; compressed limits 32 MiB, request timeout, no shell/install/remote-code/pickle. Only named JSONL/TSV members were read from ZIP/tar; no archive executable was run or extracted as code. No models downloaded.

| Archive | Observed bytes | SHA256 |
|---|---:|---|
| [BEIR scifact.zip](https://public.ukp.informatik.tu-darmstadt.de/thakur/BEIR/datasets/scifact.zip) | 2,816,079 | `536e14446a0ba56ed1398ab1055f39fe852686ecad24a6306c80c490fa8e0165` |
| [Original release data.tar.gz](https://scifact.s3-us-west-2.amazonaws.com/release/latest/data.tar.gz) | 3,115,079 | `11c621288d41ac144d29b13b0f8503b3820b7d6e8b1f6ff24dff335c196d76be` |

BEIR MD5 `5f7d1de60b170fc8027bb7898e2efca1` matched the pinned BEIR source's dataset table. Original `latest` URL is mutable; the byte hash, not its URL, freezes this attempt. Freeze includes SHA256 for every actual corpus/query/qrel/license/archive file.

Preparation compared all 5,183 document IDs and titles exactly to the original release. Initial direct abstract concatenation matched 4,128 records; remaining differences were whitespace, and normalized whitespace matched **all 5,183**. This transformation difference was investigated rather than silently asserted as raw-byte identity.

All query texts match original claims. BEIR train = original `claims_train.jsonl`, **809 queries/919 pairs**; BEIR test = original `claims_dev.jsonl`, **300 queries/339 pairs**. Every qrel pair equals the claim's **cited_doc_ids**, whereas original support/refute evidence lists have fewer pairs. These retrieval labels must not be interpreted as scientifically verified support or refutation. Original hidden SciFact test labels were not used or reconstructed.

Development/validation query lists are frozen 80/80 disjoint selections from BEIR train by SHA256 of a constant prefix plus query ID; BEIR test stays full 300. No test-label-driven tuning. This is public benchmark data with possible related claim variants, not a clean claim of semantic independence from the world or security-sealed evaluation. Source validation intentionally inspected labels for identity before execution.

Only public data is in `/workspace/work/g5-cpu-inputs/`; these files are not committed with product source. Exact source-retrieval metadata are retained in `source-receipts.json`; framework/source downloads from previous G0 audit remain separate from this zero-framework execution.
