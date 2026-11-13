# Native CPU viewer verification

Status: **final read-only verification passed** after the separate UI-only
availability/title refinement. Final evidence is in
`runs/g5-native-ui-20261113-05/`; baseline409 evidence remains in
`runs/g5-native-ui-20261113-04/`. Neither study was rerun and the scientific
reports/case files were not changed.

## Final UI-only verification

The two current-main presentation services were verified through all5 desktop
and2 mobile views again. Both `/api/project` responses explicitly contain
`evidence_task_available=false`; browser request journals show **0 calls** to
`/api/project/evidence-task.json`, rather than filtering or ignoring409 responses.
Each case makes28 GET requests in the complete pass, with0 POST/other methods,
0 blocked requests,0 pageerrors and0 HTTP errors. Actions and models are disabled.

Exact visible desktop/mobile experiment titles are:

- Retrieval: **固定引用检索对照**, **检索保存结果诊断**.
- Scheduling: **合成区间调度对照**, **调度保存结果审计**.

Visible disclosure controls were expanded in a focused second inspection; the
same names and actual CPU metrics/negative retrieval deltas/scheduling evidence
remain available. Actually viewed final desktop experiment and mobile output
screenshots for both cases, plus both expanded experiment screenshots. All14
default screenshots have0 measured horizontal page overflow. This is read-only
functional and representative visual evidence, not a user-satisfaction study.

All8 final downloads again return HTTP200 and match source report manifest SHA/
sizes and disk. Every downloaded input/report byte, plus first/last PDF-render
bytes, is identical to the baseline. The same63/62 case file inventories match
both their own before/after checks and the baseline, and each final API projection
is unchanged before/after. Both retain3 plans,2 tools, waiting,0 fits/model/source
reads. Final source scopes are unchanged and do not use Concrete MAE language.

Final JSON: `summary.json`, each case's `result.json/requests.json`,
`focused-disclosure-diagnostic.json` and `visual-review.json` under the05 root.
The final visual review SHA256 is
`1ddc8c3da68e921e5979c0c4a271fed8a23c093ea2b8c3be7057c29971cc70f9`.
Original PDF typography/partial-page-inspection limitations below remain; no
scientific report was rebuilt to obtain this UI result.

## Actual read-only checks

Both completed projects were opened through pinned-source loopback services:
retrieval18832, scheduling18833. Each has5 desktop pages at1440×1000 (overview,
research, experiments, knowledge, outputs) and2 mobile pages at390×844
(experiments/outputs), screenshot/text evidence,4 actual HTTP report downloads,
PDF text extraction and representative first/last page renders.

| Case | Project | Case files unchanged | PDF pages |
|---|---|---:|---:|
| Retrieval | `project-b0ad79226f0a454b99b604e373e39bbb` | 63 | 7 |
| Scheduling | `project-148dac5d531144008498449cb16a54ea` | 62 | 8 |

The API shows3 plan revisions,2 completed tool actions, waiting,0 fit attempts,
0 fits/models/source reads for each. Action/model UI modes are disabled. Source
scope is exactly the registered packet's domain_scope: citation retrieval uses
5,183 documents/1,109 preserved queries and460 selected queries; scheduling uses
16 synthetic cases/20,544 jobs. No Concrete MAE values were visible or used.

All8 downloaded files (`input.json,report.json,report.md,report.pdf` per case)
return HTTP200 and match original native report manifest SHA/size and managed
disk files. GET-only API projection canonical hashes and every case file's full
SHA/path inventory are identical before/after the complete UI pass and focused
disclosure inspection. Browser requests allowed only GET/HEAD to the exact local
origin; blocked requests0, research actions dispatched0. There are0 pageerrors.

The baseline has2 expected HTTP409 responses per case, both from
`/api/project/evidence-task.json`: `{ok:false,code:TASK_NOT_AVAILABLE}`. A focused
reproduction places it at initial `#/overview` loading; the two full-pass events
come from the desktop/mobile contexts. It is not a JavaScript crash, missing
font/favicon or failed report download. Current projects have no evidence task;
the existing UI catches this absence. Raw status is retained as
`observed_browser_errors`, not mislabeled zero HTTP errors. Root separately
commissioned a small read-only availability projection/UI check and four method
titles; scientific core/adapter/report/driver/protocol and case bytes stay fixed.

## Representative visual inspection and limits

Actually viewed: retrieval desktop outputs, scheduling mobile experiments,
retrieval expanded experiment observations, scheduling expanded output shell,
and both reports' first/last pages. Pages are readable and representative images
show no horizontal page overflow. Existing disclosure controls reveal actual
TF-IDF/BM25/Recall and scan/binary/objective/schedule observation data. Default
cards still use generic follow-up labels in this baseline. The knowledge page's
historical reusable resources remain separate from current source extraction;
the projects correctly show no registered/read evidence selections.

The PDF titles, current plans and limits are readable. First-page revision
separators show box glyphs, and some Latin spacing is tight; last pages retain a
short limitations paragraph and substantial white space. Only pages1/7 and1/8
were visually inspected. Text extraction and file hashes do not constitute
whole-PDF visual approval, independent scientific validation or user satisfaction.

Initial helper failures are preserved: attempt01 used raw-state `source_scope`
instead of projection `domain_scope`; attempt02 used a strict `body` selector
matching SVG foreignObject bodies; attempt03 stopped on the expected HTTP409.
These were helper assumptions, not study execution failures. The corrected
fourth pass saves both domains completely. A focused disclosure helper initially
tried clicking hidden duplicate summaries; its correction clicks only visible
disclosures, with all case identities still unchanged. No frontend source was
modified by this verifier.

Machine evidence: each case's `result.json`, `case-before.json`, `case-after.json`,
`requests.json`, downloaded files and screenshots; top-level
`focused-disclosure-diagnostic.json`, `evidence-task-http-diagnostic.json` and
`visual-review.json`. Helpers/logs are under `/workspace/work/g5-native-ui/`.
The baseline alone does not establish zero HTTP errors; the separately recorded05
pass above does. Final checks did not suppress the baseline evidence or substitute
new research results.
