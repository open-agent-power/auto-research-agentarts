# Native retrieval input preflight

Status: **prepared, not executed as research**. No native project was created;
there were no index builds, ranking or gold-scoring calls, estimator fits,
product model/API sends, native tool actions or product source extractions.
Host file reads and schema/provenance work are preparation costs, not free model
usage or evidence of a zero infrastructure charge.

## Prepared originals and identities

- New input directory: `/workspace/work/g5-native-retrieval-inputs`.
- Encoded source packet: `/workspace/work/g5-native-retrieval-packet.json`,
  **11,128,187 bytes**, SHA256
  `546a09773bc8e77aa7f034ca58753394f6a75c3ecf610e3c66c3f24eea2ab51b`.
- Native source snapshot SHA256:
  `2ff1e33fc9b780037338f9916b9430bd6502029058ccd5386334af1e2b430895`.
- Complete preflight receipt: `/workspace/work/g5-native-retrieval-preflight.json`,
  SHA256 `e62cc893fedf29a4b38fa4f2624377337f9575cf09a0a38ced63ba71b7987ecf`.
- New original-source mapping receipt:
  `/workspace/work/g5-native-source-mapping.json`, SHA256
  `09b8c79d61694467ddebfb02efb69a04dbc333f92a39f3f68f858b809de08b9d`.
  This digest is explicitly bound in the new spec/source packet.
- Original standalone freeze SHA256 remains
  `759d15473a64f45f855f5c455ddb6329bac229885d077424d381df3ef25f6af8`;
  source commit remains `68b98a56d93e0f9da0d2aab4e6c3294699a0f72e`.

The five runtime assets are byte-for-byte copies with safe closed basenames;
only names of the qrel and license files change. The corpus, queries and qrel
bytes are additionally matched to their specific BEIR ZIP members. Large archives
remain outside the runtime packet; original release matching reads only named
corpus/train/dev members without extracting or executing code.

| Runtime asset | Bytes | SHA256 |
|---|---:|---|
| corpus.jsonl | 8,106,566 | `dec31c8182f3d744c7d2c09423756fd1d17cbef75808db13ba01cc0aab4d1ac6` |
| queries.jsonl | 209,731 | `8ff84a7c903f722981cd8d595c022660140c51867b27608a6d4910db86080313` |
| qrels-train.tsv | 14,502 | `a53f2114831916c096b6c37d9e54da68cef4efdcdbd5ed46533601af972acf1d` |
| qrels-test.tsv | 5,389 | `0864bb985e0ca2367ba217977e72004d549054b2b06666ed9d4825ac7c21284c` |
| license.md | 542 | `56ee69bc639cbab8f0b2e4b67091ec5e9390aa99a1d65f0a35e4274686c9a806` |

Both archive identities still match the original freeze: BEIR ZIP
`536e14446a0ba56ed1398ab1055f39fe852686ecad24a6306c80c490fa8e0165`,
original release TAR.GZ
`11c621288d41ac144d29b13b0f8503b3820b7d6e8b1f6ff24dff335c196d76be`.
All **7 original input files and 11 standalone result files** have identical
before/after whole-file SHA manifests in the receipt. No old study allowance or
lineage was changed.

## Mechanical identity and scope checks

The actual counts are **5,183 documents and 1,109 queries**. Train qrels contain
**809 queries / 919 cited pairs**; test qrels contain **300 queries / 339 pairs**.
The original **80 dev / 80 validation / 300 test** ID lists are copied exactly,
disjoint, and match the original frozen selection. The full source is retained;
the remaining queries are not silently removed from the input.

All original document IDs and titles match. Original sentence-joined abstract
text matches 4,128 records byte-for-text; whitespace-normalized text matches all
5,183, preserving the previously investigated BEIR whitespace transformation.
Every query matches its original claim text; each qrel exactly matches original
`cited_doc_ids`. Original unreleased hidden test labels were not accessed.

The spec explicitly retains **CC BY 4.0** for claims/citation annotations and
**ODC-By 1.0** for the S2ORC-derived abstract corpus, original license bytes,
author/publication attribution and source URLs. This preparation reuses the
existing official-source snapshots; it does not claim a fresh remote license
check or treat a self-declared license string as independent verification.

## Retained initial failure and schema correction

The first preflight stopped before copying inputs or creating a packet because
the proposed empty-metadata restriction was wrong: **693 of the 1,109 original
query records have nonempty metadata**, including original sentence-level
SUPPORT/CONTRADICT annotations. Merely checking the first record had missed this.
Failure receipt: `/workspace/work/g5-native-host-prepare/preflight-attempt-01.json`.

Root approved retaining this original metadata as a bounded opaque JSON object:
≤16 KiB, ≤512 nodes, depth ≤8, keys ≤128 characters, strings ≤4,096, strict UTF-8,
no NUL/nonfinite values. Actual maxima are 495 canonical bytes / 78 nodes / depth
5. No source bytes or metadata were deleted to pass the contract. JSONL now uses
physical LF/CRLF boundaries so legal Unicode separator characters inside strings
do not change row locators.

These metadata labels are **not ranking or scoring inputs**: fixed retrieval
uses only query text and corpus title/text; scoring uses citation qrels. Metadata
presence is openly acknowledged, so the experiment cannot claim sealed or
unseen-label evaluation, support/refute accuracy, or independent scientific
validation. Adapter tests compare changed metadata with identical rankings and
metrics on small engineering fixtures.

## Execution boundary and next step

The host preparation script is
`/workspace/work/g5-native-host-prepare/prepare_inputs.py`. During
`capture_source/load_source`, lexical tokenization, indexing, retrieval and metric
functions were patched to fail if called. All were unused. Reading gold qrels
and original annotations for foreign-key/provenance identity is explicitly part
of preparation; it is not a sealed-evaluation protocol or a product source read.

Only after source/code review and root's native-case freeze should the existing
ResearchProject/Controller register this packet with its new explicit **2 local
actions, 0 source extractions, 0 fit and 0 model/API** scope. This preflight neither
creates that case nor consumes/extends a research action allowance. The old
standalone benchmark, original G1/G3 cases and original failed cgroup gate retain
their existing identities and boundaries.
