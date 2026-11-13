# G5-L native CPU research integration — proposed contract

Status: **root-accepted implementation contract; no retrieval execution yet**. Root accepted the generic bounded input/case-specific freeze distinction and source-verification clarification below before implementation.
Target: one retrieval study can use the same native project, plans, actions,
budget, report and recovery as the tabular study. Reuse the existing controller;
do not add another case controller or call the standalone benchmark through shell.

The SciFact labels mean **cited documents**, not support/refute judgments. This
stage does not generate answers, train a model, establish scientific validity,
repair cgroup isolation or prove sealed evaluation. Existing public outcomes are
already known; this is a new explicitly scoped native integration, not a reset of
the completed standalone G5-L experiment or any Concrete/G3 allowance.

## Source-checked reuse and minimum hooks

| Existing entry | Verified behavior / minimum proposed extension |
|---|---|
| `ResearchProject.create` (`research_project.py:135`) | Captures one validated source packet, original source SHA, immutable registration, project/run identity and cumulative local allowance. Register one new primary adapter; retain this lifecycle. |
| `method_registry.py:12..68` | PRIMARY/FOLLOWUP allowlists, per-method evaluation identity and transitive code hashes. Add only explicit fixed CPU adapters; no module names or commands from input. |
| `research_methods._domain_methods/_domain_choice` (`:181/:258`) | Native conditions and bounded selection. Add retrieval-specific eligibility/reasons; current generic follow-up assumes tabular quality and cannot be reused unchanged. |
| `ProjectController._selection_context` (`:141`) | Existing exact candidate identities, conditions and cost projection. New CPU methods cost one local call, zero fits/source extractions/model sends. No parallel controller or hidden API dispatch. |
| `ResearchProject.step` (`:495`) | Durable request reservation, source/code/version checks, one predecessor identity, immutable result envelope and unknown recovery. The new saved-result audit needs a narrow dispatch branch that supplies the verified predecessor result rather than recomputing it. |
| `LocalWorkbench.import_project` (`local_workbench.py:226`) | Host-only same-filesystem **rename**, preserving project ID, state and budget. Create the new CPU project through the existing host API, then import/select it with this method; no new public intake route needed for v1. Never use this to move an old protected case. |
| `ResearchProject.save_plan`, `LocalWorkbench.save_plan/advance` | Existing native plan revisions and exact selection/advance commands. Use these for observation-driven next-step changes. |
| `project_report.collect_report` (`:178`) / export (`:1381`) | Verifies source/action artifacts, exports four native report files with source manifests. Add one `retrieval` report kind/summary/adverse-query section; keep original exporter, hashes and download paths. |
| C04, `source_evidence_adapter`, `project_knowledge`, `KnowledgeIndex` | C04 is a provenance contract, not a separate executable module. Preserve original bytes/license/citation locators. KnowledgeIndex is existing chunked FTS5 with different tokens/ranking; **do not substitute it for the benchmark's document-level TF-IDF/BM25** or auto-index all 5,183 documents through its 4,096-chunk cap. Optional selected-source reading remains separately budgeted C04 work. |

Extract the fixed pure lexical functions from `scripts/run_cpu_transfer_benchmarks.py`
into a small reviewed native module; leave the old script, protocol, data and
frozen outputs unchanged. Its `build_index/retrieve/metrics` are useful reference
implementations, not current product adapters. Avoid importing a development
script into the native dependency graph or broad changes to KnowledgeIndex.

## Exact v1 input packet (proposed)

One host-selected directory contains fixed safe basenames only. A host capture
function validates and embeds original bytes; runtime/model/HTTP commands cannot
choose paths, URLs, archive members, executable names or output directories.
No symlinks, traversal, alternate streams, archives, pickle, executable decoding,
network fetch, dynamic imports or shell operations are accepted by this protocol.

Packet exact keys:
`schema_version,task_kind,spec_source,assets,spec,scope,snapshot_sha256`.
`schema_version=cpu-research-source-v1`, `task_kind=citation_retrieval`.
`snapshot_sha256` is canonical SHA256 of every other field, verified on every read.
`assets` is an object with exactly `corpus,queries,train_qrels,test_qrels,license`.
`spec_source` and each corresponding asset value have exact keys
`file_name,sha256,bytes,bytes_base64`, preserving original bytes. The parsed `spec`
must exactly equal spec_source JSON; strict UTF-8, duplicate/nonfinite JSON keys
rejected. Parsed scope is derived, never trusted independently from spec/bytes.

`spec` exact keys: `schema_version,dataset_label,source_url,attribution,license_notes,
source_provenance,files,query_splits,comparison,limits`.
`schema_version=citation-retrieval-spec-v1`.
`dataset_label` is nonempty text ≤300 chars, source_url ≤2,000 chars and attribution
≤4,000 chars. `license_notes` has exact keys `claims_and_qrels,abstracts`, both
nonempty ≤4,000-char text. Provenance digest fields are lowercase SHA256 and the
commit is a 40-hex Git identity. URL text is retained only; it never triggers I/O.

- `files` is the exact mapping `{corpus:corpus.jsonl,queries:queries.jsonl,
  train_qrels:qrels-train.tsv,test_qrels:qrels-test.tsv,license:license.md}`.
- Corpus rows: exact `_id,title,text,metadata`; query rows: exact `_id,text,metadata`.
  `_id` is unique bounded nonempty text (≤80 chars); metadata must be an empty
  object for this BEIR v1. Preserve row order, raw JSONL bytes and physical line
  locators. Corpus title ≤4,096 chars, text ≤131,072 chars; query text ≤4,096.
- Qrels header is exactly `query-id\tcorpus-id\tscore`; unique query/doc pairs,
  score exactly integer 1, all foreign keys resolved. These are citation labels.
- `source_provenance` exact keys: `beir_archive_sha256,original_archive_sha256,
  original_source_commit,mapping_receipt_sha256,qrels_semantics`; last value is
  `cited_doc_ids_not_support_refute`. The host must match existing official-source
  and archive-mapping receipts before capture. Embedded declarations alone do
  not establish upstream verification or license validity. Large archives remain
  host-side preserved originals, not runtime inputs or an extraction capability.
- `query_splits` exact dev/validation/test ID arrays, disjoint, all IDs present:
  source-defined IDs fixed before execution. Generic intake permits smaller valid
  engineering/other-licensed corpora within the same caps; it does not hardcode
  SciFact IDs or use a separate per-dataset controller. Each split is nonempty;
  dev/validation IDs have train-qrels and test IDs have test-qrels; train/test
  qrel query sets are disjoint and every selected query has at least one label.
  The separately frozen **real SciFact case** must preserve exactly its prior
  80/80/300 IDs, 5,183 corpus/1,109 query records, 809/300 qrel query coverage and
  919/339 cited pairs. The host must compare all original byte hashes/counts to
  the existing source receipts. No result-dependent subset/reselection is allowed.
- `comparison` is the exact fixed pair: `baseline=tfidf_cosine`, `candidate=bm25`,
  `top_k=20`, `k1=1.2`, `b=0.75`, `tokenizer=ascii_alnum_lower_v1`,
  `tie_break=doc_id_ascending`, `metrics=[recall@5,recall@10,recall@20,mrr@10,ndcg@10]`.
  No prompt-supplied methods, tuning, embeddings, LLM judge or generator.
- `limits`: corpus ≤8.5 MiB, queries ≤512 KiB, each qrels/license ≤64 KiB;
  all asset raw bytes ≤9 MiB, spec ≤64 KiB, whole encoded packet ≤16,000,000 bytes.
  Cap total corpus rows at 6,000, queries at 1,200, qrel pairs at 2,000; validate
  row/field/byte limits before indexing. Current original corpus is 8,106,566 bytes
  and fits these bounds. Follow existing `ResearchProject.create`'s 16,000,000-byte
  source ceiling; do not globally raise legacy source/report/HTTP limits.

The exact limits object is `{corpus_bytes:8912896,queries_bytes:524288,
qrels_bytes:65536,license_bytes:65536,all_asset_bytes:9437184,spec_bytes:65536,
packet_bytes:16000000,max_corpus_rows:6000,max_queries:1200,max_qrel_pairs:2000}`;
these host caps cannot be increased by a spec. Derived `scope` exact keys are
`domain,contract,dataset_label,document_count,query_count,qrels_semantics,
input_identities,comparison_sha256`; domain is `retrieval`, contract is
`citation-retrieval-fixed-pair-v1`, counts come from checked originals, and
input_identities maps the five roles to verified `{sha256,bytes}` values.

The v1 host intake can call `capture_source(host_directory)` then
`ResearchProject.create(source=packet_path,method_id=research.retrieval-fixed-pair,
goal=...,budget_ref=<new explicit native-integration scope>,max_tool_calls=2)`;
these are proposed method/module identifiers, not currently implemented APIs.
The existing `LocalWorkbench.create(body)` remains the CSV-specific intake.

## Native actions, observations and artifacts

Proposed primary method: `research.retrieval-fixed-pair`, evaluation identity
`citation-retrieval-fixed-pair-v1`. `load_source` does strict mechanical intake;
`execute(payload,dimension=None)` allows no other parameters. Both declared arms
rank every query using only corpus/query data; complete rankings are captured
before the scorer accesses qrels. This is a reviewed fixed-code procedural
separation, not confidentiality or protection from the same operating-system user.

One completed action returns the existing ToolResult envelope:
`status,tool_id,adapter_version,schema_version,observations,evidence_refs,metrics,
result,failure,model_calls,new_fits,scientific_validation`.
Set `model_calls=0,new_fits=0,scientific_validation=false`. `result` contains
`scope,source_snapshot_sha256,comparison,rankings,per_query_metrics,paired_summary,
adverse_queries,usage,limitations`; observations describe exact coverage, macro
scores and wins/ties/losses separately for each cutoff. They are actual computed
retrieval observations, not validated medical claims or model-agent statements.
All query IDs and every loss/tie remain in the complete ≤4 MiB result envelope;
do not emit only an improved aggregate or drop low-recall/no-hit queries.

Proposed follow-up: `research.retrieval-saved-error-audit`, parameter keys exactly
`based_on_action_id,based_on_result_sha256` (existing predecessor envelope).
Eligibility requires the same project's completed fixed-pair action/source and
frozen comparison. Controller verifies and supplies its saved ToolResult to this
pure adapter; it **does not rerank, rebuild an index, re-score against qrels or fit**.
The existing core still verifies the immutable source packet on a follow-up;
this may read/decode original corpus/qrel bytes for integrity. Do not describe
that generic integrity I/O as absent or as a new scientific source extraction.
The audit separates citation recall losses from early-rank gains, reports all
paired failure IDs and optional **predeclared** query-length/relevance-count
strata. No new learned candidate or post-test tuning is created.

Reuse the original immutable action JSON and canonical result fingerprint. Every
rank/metric/adverse item carries query ID and method; corpus/query/qrel references
carry exact original SHA plus JSONL line or TSV query/doc locator. Document hits
are unreviewed references. Reusing a document in generated prose would require
the separate original-source reading and interpretation path, not a rank score.

## Budget, plans, recovery and acceptance

New integration scope: **2 cumulative local actions, 0 fit attempts, 0 model/API
sends**. Source extraction starts at 0; if root elects one C04 license/metadata
reading, freeze its separate limit at 1 before execution. Original input loading
and lexical scanning belong to the local computational action and are recorded
as corpus/query counts; they are not free scientific source verification. No old
study/standalone allowance is reset. Host CPU concurrency remains 1, thread count
1; freeze supported time/address-space/file/output bounds before executing.

Plan v1 states fixed pair, metrics, known-outcome status and stopping conditions.
After real paired coverage losses/rank gains are observed, save native v2 citing
the action and source evidence, then execute the saved-error audit or enter a
precise wait. Save final stop/wait and remaining questions. Two phases are useful
research continuity only when the second analysis addresses the actual feedback;
a cosmetic plan edit or static report cannot satisfy that claim.

Keep `ResearchProject.step/resume` and controller request semantics: request ID
binds command/source/code/evaluation/predecessor and payload; exact replay checks
before freshness. Completed same-ID replay with ranking/index construction and
model/fit access disabled must return the original result with no new calls.
Unknown/running execution preserves the original reservation and blocks new IDs;
restart may consume an already saved complete envelope, never reissue work just
because its receipt was lost. Import uses same-filesystem native rename, not a
new project identity. Report/export/reopen must work through existing native
paths and include all original assets, result identities, adverse outcomes,
license/attribution, uncertainty and budget lineage.

Registration/imports change registry and application code identities. Freeze a
new source release and new integration case; keep prior G1/G3/G4/G5 artifacts and
their old-code services pinned. Do not upgrade, re-fit, rewrite or migrate those
cases just to demonstrate this interface. Hash their whole trees before/after.

Required tests are targeted source-schema/size/path/foreign-key rejection,
hand-calculable lexical/metric checks, procedural qrels separation, real native
action/plan/report flow, adverse preservation, exact/changed-ID behavior,
interruption/unknown/recovery, and original-case byte preservation. Patch model
transport and all fit methods to fail. Independently recompute the saved native
scores and compare to the frozen standalone definitions; reuse cannot be assumed
merely because both modules contain the words BM25 or TF-IDF.

## Later algorithm endpoint

The common CPU envelope can later use a distinct task_kind `weighted_interval`
and its own exact job/constraint/source schema, fixed baseline/candidate pair,
feasibility/objective/evaluation identities and observation units. Reuse the
same project/action/budget/recovery/report services; do not pretend document
qrels and scheduling ground truth share domain semantics. This proposal freezes
only the retrieval v1 slice; no algorithm input or extra CPU batch is authorized
by adding a future task_kind name to this document.

Root implementation decision: the next retrieval case is authorized by the
existing trusted-local continuation, with its own explicit 2-action lineage,
0 estimator/model/API allowance and 0 source-read limit before execution. The
standalone study remains frozen; new implementation and input identities are
committed/reviewed before this native case executes. Later algorithm integration
needs its own exact task contract and fixed workload, not a renamed retrieval result.
