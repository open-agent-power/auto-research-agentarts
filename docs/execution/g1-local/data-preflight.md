# G1-L independent input and evidence preflight

Date: 2026-11-13 (Asia/Shanghai). Scope: approved trusted-local Concrete reproduction; does not certify the Docker-isolated gate or autonomous model runtime. Independent data auditor: `research_task`; root owns project creation and experiment execution.

## Executed check and outcome

Command from repository root:

```sh
python -B runs/g1-local-data-preflight/check_data.py
```

Exit 0. Machine-readable result and exact native extraction previews: `runs/g1-local-data-preflight/result.json` and `selection-precheck.json`. These files are ignored local audit evidence. No estimator was fitted, no project created, no model/API request sent, and no research outcome was calculated or copied.

- All five original files still match retained `source-manifest.json` byte sizes and SHA-256s (CSV, ZIP, readme, API metadata, official-page Markdown capture).
- Derived CSV SHA-256: `768a123975d7f56ddaef8f2965594614aa7a015b2719d545266e4965bd5b25aa`.
- Derived spec SHA-256: `6d0859af90ce37c5b02842702c585164da15d22b2d1663ccd56f87de0263ba70`.
- All **1,030** rows and **9,270** original numeric tokens match exactly, in original order. Added one-based `source_row` values are correct. All original numeric values are finite.
- All derived `mixture_signature` labels independently match first-appearance numbering of exact Decimal seven-ingredient tuples: **427** signatures, **246** singleton signatures; **25** extra original full-record duplicates retained.
- Numeric columns preserve eight inputs plus `strength`; target is MPa, original ingredients are kg/m³, `age` is day. Group and provenance columns are excluded from model inputs. Signature identity is operator-derived and cannot stand for known experimental batch/specimen/laboratory identity.
- Official retained metadata confirms creator I-Cheng Yeh, UCI ID 165, DOI `10.24432/C5PK67`. The retained official-page capture explicitly states CC BY 4.0 and the original readme separately requires retention of author's copyright and paper citation. This preflight rechecked saved bytes, not a new network retrieval.

## Minimal native evidence bundle

Use the existing files without reflowing their text, so their physical line numbers and original hashes remain valid. All three recommended selections were actually checked through `tabular_source.extract_selection`; they satisfy the current UTF-8, inclusive physical line and bounded extraction rules.

| Source file | SHA-256 | `media_type` | Exact `locator` | Purpose |
|---|---|---|---|---|
| `Concrete_Readme.txt` | `5cd3cdb31d3cfd68287daa6b22ed0541d6932113e83ee0980ced63641af3441d` | `text/plain` | `{"kind":"text_lines","value":"30-58"}` | Laboratory measurements, raw target, size and field units |
| Same original readme | Same | `text/plain` | `{"kind":"text_lines","value":"90-94"}` | Database reuse, copyright and required author/paper citation |
| `uci-concrete-page.md` | `3a3abe32fa5b695fae14d0e23922c77b4e438a464325de246684e7993dad00a4` | `text/markdown` | `{"kind":"text_lines","value":"141-156"}` | Author, dataset DOI and explicit CC BY 4.0 |

The Markdown page is a **Firecrawl-derived official-page capture**, not original HTTP HTML bytes. State this in the source `license_note`/contributor explanation. Do not describe the model or controller as having read this source until the source-selection action actually completes.

`locator.value` must be a **string** (`"30-58"`); `start/end` dictionaries, `line_range`, or integers are rejected. `text_lines` operates on one-based inclusive physical lines, with at most 256 selected lines and 60,000 UTF-8 bytes per selection. `media_type` records the actual representation; extraction is selected by `locator.kind`, not guessed from the media type.

For filesystem bundles, each `sources[]` entry must contain exactly `id,path,sha256,url,media_type,license_note`, with `path` relative to `sources/` (for example `sources/Concrete_Readme.txt`). A `project-evidence-bundle-v1` has `task_ref,contributor,sources,selections` and optional `remaining_questions`; `contributor={"role":"operator_assistant","label":"G1-L source preparation"}` is valid. Each selection contains exactly `id,source_id,locator,claim`.

Obtain the **actual** `task_ref` from the created project's `evidence_task()` result; do not manufacture project/action IDs. The method is `research.source-selection`. Registration captures bytes without reading; reading one receipt containing two sources and three selections is one native evidence action and must respect the allocated source-read allowance. Claims remain submitter statements rather than domain approval. Manager HTTP upload uses a different source envelope (`id,file_name,bytes_base64,url,media_type,license_note`), then generates the path and source hash; do not mix its envelope with the filesystem manifest.

## Current-run protocol identity

The shared `examples/research-designs/concrete-mixture-transfer-v2.json` contains the historical source text “原项目保存的完整1030行基线、427声明组及565个组内相邻龄期比较”. **Do not import this unchanged as this new project's evidence.** Preserve the shared historical example, but construct this run's resource v2 with:

1. official dataset/readme source URLs;
2. actual current-run baseline action ID, result SHA-256 and original artifact reference;
3. actual current-run diagnostic action ID/hash and any independently computed derived diagnostic locator;
4. the honest explanation that log1p is a predeclared, historically known expression candidate, whose execution decision must cite newly obtained current-run feedback.

Do not hard-code the old “565” count as newly observed. If current diagnostics genuinely compute that count, record it with their actual provenance after execution. `parent_version=1`, `comparison_kind=fixed_input_basis`, fixed feature order and original group folds must remain explicit. A claim that the candidate has lower MAE is a **hypothesis** until this run's saved paired evaluation establishes or refutes it. Known historical outcomes cannot replace current observations or establish an unseen-task/causal gain.
