# Independent retrieval arm-selection transfer

This is a new bounded ArguAna study, not another SciFact execution or an extension
of an old project's allowance. No target ranking or scoring is authorized merely
by creating this document or source packet. The root first commits reviewed code,
prepares a freeze, and obtains a separate independent approval of that exact
freeze, output, policy, selection and source identity.

The scope is trusted local pure CPU retrieval under the existing G5 authorization.
There is no generation, model service, paid API, estimator fitting, source
extraction, arbitrary candidate code, or new controller. The original isolation,
sealed evaluation and full Gate limitations remain. Public labels are available
to the same user; this protocol supplies procedural ordering, not confidentiality.

## Question and controls

The predeclared objective is Recall@20. The known source SciFact result showed a
negative BM25-minus-TF-IDF coverage delta. A frozen source-only coverage guard
therefore chooses TF-IDF for a different retrieval task, with fixed BM25 as the
baseline. The same TF-IDF method is also the source-free fixed-arm negative
control. Candidate and negative control reuse the exact same saved rankings and
metrics: their difference is structurally zero, so this cannot identify a causal
benefit of memory. Target development metrics are descriptive only; neither they
nor target validation/test outcomes select arms, tokens, parameters or splits.
Early-rank gains, coverage losses, ties and missing relevant documents all remain.
Before evaluation, the interpretation rule is fixed: test Recall@20
TF-IDF-minus-BM25 greater than1e-12 supports local coverage transfer; absolute
delta at most1e-12 means no coverage improvement; delta below−1e-12 is negative
transfer. This describes only the selected procedural query subset, with no
significance/generalization claim or automatic promotion. Every other metric's
loss is reported too. There is no added nDCG utility guard or target-driven
reselection. The saved policy projection records this exact rule and conclusion.

The source evidence is the original saved SciFact project/action/result/source
snapshot/producer and artifact identities plus an exact metric pointer. The host
reads the protected original final state and relocation receipt, resolves only
that completed source action's original artifact within the 494-file inventory,
and checks raw/envelope SHA, action/project/source/producer identity and the exact
saved negative Recall@20 value. A declared negative number alone is insufficient.
No source
project is upgraded, replayed, copied into a new budget, or refit. The independently
licensed target is ArguAna Counterargs: authors Henning Wachsmuth, Shahbaz Syed and
Benno Stein; official version DOI 10.5281/zenodo.3973258, CC BY 4.0. Official
originals, BEIR mapping receipts and license evidence must be audited separately;
reporting embedded bytes does not establish license/provenance declarations.

## Target and fixed procedural selection

The BEIR archive SHA256 is
`cfdf79adce27a401b3cd3ea267903134dbfab2c6afeb95d7fe5724a00bf7557b`.
All 8,674 corpus documents and all 1,406 original query records are retained. The
original BEIR data has only a test split. Sort all unique query IDs by the tuple
`(sha256(('arguana-transfer-v1' + '\n' + query_id).encode('utf-8')).hexdigest(), query_id)`.
Use the first 80 as dev, next 80 as validation, and next 300 as test; the remaining
946 are preserved but not evaluated. These are artificial procedural partitions,
not official heldout or sealed splits. Selection depends only on IDs, not scores,
relevance grades or label feasibility. All original labels and grades are retained;
no per-query label truncation or performance-based replacement is allowed.
The host checks the complete original corpus/query member SHA identities and all
1,406 original qrels as an exact sorted row-set SHA; each query retains its one
grade1 positive, with the 160 dev/validation queries in the derived train file and
the remaining1,246 in the derived test file. Row-set identity is not a claim that
these two derived files retain the original single TSV's byte order.

The new independent relevance contract preserves positive grades and evaluates
binary positive relevance with the existing pure lexical metric functions. Its
nDCG is a binary projection, not canonical graded BEIR nDCG. It excludes a document
with ID equal to the query ID before truncating to top 20, without rebuilding the
index or changing its corpus/IDF. Missing positive target documents remain in the
recall denominator; neither silent deletion nor fabricated corpus rows is allowed.
The old citation adapter, evaluator, packet, protocol and producer identity remain
unchanged; this task is counterargument relevance, not SciFact cited documents or
support/refutation classification.

## Prepare and independent review

Use the existing exact repository Python environment and the new host wrapper:

```text
.venv/bin/python -B scripts/run_retrieval_transfer_case.py prepare \
  --output runs/g5-retrieval-transfer-<unique> \
  --packet <prepared-source.json> --packet-sha256 <exact-sha256> \
  --policy <policy.json> --selection <selection.json> \
  --code-commit <full-reviewed-current-HEAD>
```

No engineering flag can relabel a real packet. Preparation only validates strict
source schema and the exact full population/80/80/300 hash-only selection, with
ranking, tokenization, index building, scoring, primary execution and timing
patched to reject. Output must be a fresh non-symlink directory directly under
`REPO/runs` with the stated prefix. Policy and selection JSON are bounded to 64KiB;
the source packet is bounded to the existing native 16,000,000-byte intake limit.
The command accepts no executable policy or free-form execution command.

The exact policy fields are schema_version, baseline, candidate, negative_control,
objective, selection_rule, selection_seed, source_evidence and limitations. Fixed
literals are `retrieval-transfer-policy-v1`, BM25 baseline, TF-IDF candidate and
negative control, `recall@20`, `source_scifact_coverage_guard_v1`, and
`arguana-transfer-v1`. Source evidence must declare an actual negative source
BM25-minus-TF-IDF Recall@20 delta with original digest pointers. Arbitrary policy
fields cannot change the execution or choose a target winner.

Freeze stores original packet/policy/selection bytes and hashes, derived scope,
full committed Python source file identities, this wrapper/protocol, the source
preparer and reused host helper, native producer identity, numerical runtime,
exact Python executable/version, output root, budget lineage and resource limits.
It also freezes and verifies the prior 494-file inventory and the three complete
original case tree path sets (including the old native retrieval/scheduling tree).
An absent or changed original tree prevents success; history is never rebuilt.
Frozen paths are regular files and source/protocol changes prevent execution.

The independent JSON review has exactly schema_version, status, freeze_sha256,
code_commit, output_root, policy_sha256, selection_sha256, reviewer and limitations.
Its schema is `g5-retrieval-transfer-review-v1`, status `approved`; all identities
must match this freeze. The reviewer checks source license/mapping, semantic
applicability, original grades, same-ID exclusion/refill, missing positives, honest
equal-arm interpretation, caps and native budget/recovery behavior.

```text
.venv/bin/python -B scripts/run_retrieval_transfer_case.py run \
  --output <same-output> --review <new-exact-independent-review.json>
```

One study ID and budget lineage are fixed as
`g5-arguana-source-arm-transfer-v1`. Before a per-output attempt the host exclusively
creates `.agent/autonomy/studies/g5-arguana-source-arm-transfer-v1.json`, binding the
original output/freeze/review/policy/selection. This permanent study claim prevents
starting a replacement project in another output directory; it is never deleted
to reset allowance. Approval is archived before an exclusive `attempt.json` claim.
An existing attempt is never batch-retried or replaced. The internal worker
checks the original study-wide claim and additionally exclusively
claims `worker-claim.json` and rechecks the original review/freeze, preventing an
accidental second worker. These same-user file controls are not OS authorization.

## Native execution and continuation

Only a newly spawned child sets wall alarm180s, CPU120s soft/130s hard, address
space1GiB, individual file32MiB, and numerical threads1. The parent also enforces
wall180s. Free disk headroom must be at least5GiB at prepare, run and child start.
These are subprocess limits, not cgroups, a total disk quota or an exact CPU meter.
The root session limits remain unchanged. No endpoint accepts arbitrary code.

The child creates one genuinely new independent target project with exactly two
local tools, lowers evidence reads8 to0, imports the same DB into LocalWorkbench,
explicitly selects it, saves plan1 including the frozen policy/source evidence,
then submits the exact native controller candidate/context for the fixed pair.
All selected queries/arms finish ranking before the first label scoring call.
Actual observed output and its original action/result SHA drive plan2 and the
saved-only audit. Plan3 cites the completed audit and waits. Native four-file
report export follows; there is no automatic promotion or new fit/model allowance.
The final state must contain two actions, three plan revisions, waiting status,
tools used2/reserved0, fits0/model0/evidence reads0.

Every dispatch saves its command, exact body, replay body, receiver path and
before budget, then its actual result/after budget. Completed primary, audit and
wait requests are replayed under compute-rejecting guards and must add no charge.
Saved-only audit, policy projection and export likewise reject ranking/scoring/
primary computation. The policy projection binds the original action/result SHA,
retains every saved baseline/candidate metric and candidate-minus-baseline delta,
and aliases the saved TF-IDF values for the fixed TF-IDF negative control. Its
zero contrast is a design fact, not measured extra research samples or memory
causal gain. No third research action or additional ranking/scoring is performed.
Network attempts, Ridge/StandardScaler fits and source extraction are rejected in
the child and attempts are counted. Development token/currency cost stays unknown,
distinct from the bounded zero product model/API/fit slice.

A timeout, nonzero child, or missing final result is `unknown` with no automatic
retry. Preserve attempt/review/freeze, stdout/stderr, requests, core reservations,
artifacts and worker error. Recover only an exact already persisted original
request through the existing native APIs after review; never rerun this wrapper
batch, create another target, change output IDs, or reset allowance. The relocation
receipt binds the same project and records the existing managed DB path. Create
has no request ID: after import, its vanished pre-import root must never receive a
new create. Interrupted import uses its original import intent/ID. Frozen source
and old cases remain read-only throughout.
