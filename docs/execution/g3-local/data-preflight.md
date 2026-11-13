# G3-L target-data provenance and applicability preflight

Date: 2026-11-13 (Asia/Shanghai). Data auditor: `research_task`. Scope: two complete published target datasets for a new bounded trusted-local transfer experiment. No project creation, estimator fit, prediction, regression error, historical model-score lookup, or product model/API send was performed. Original Concrete's exhausted ledger was not opened for mutation. The overlap check reads only original ingredient quantities, not historical fitted results.

## Official sources actually checked

| Target | Official source and DOI | Author and verified data license |
|---|---|---|
| Real Estate Valuation | https://archive.ics.uci.edu/dataset/477/real+estate+valuation+data+set ; DOI `10.24432/C5J30W` | I-Cheng Yeh; official page explicitly states **CC BY 4.0** |
| Concrete Slump Test | https://archive.ics.uci.edu/dataset/182/concrete+slump+test ; DOI `10.24432/C5FG7D` | I-Cheng Yeh; official page explicitly states **CC BY 4.0** |

Both pages were retrieved live with Firecrawl (`maxAge:0`); scrape IDs are `01a1d3a6-8af2-76de-b4bf-8c8308f83cbc` and `01a1d3a6-8ab4-7038-aef9-ab7ef375753e`. Original HTTP HTML bytes, Firecrawl-derived Markdown and retrieval metadata are preserved separately. Normal HTTPS with inherited proxy/CA and verification enabled downloaded official API metadata and archives. No third-party package or dataset mirror was substituted.

Directories:

- `/workspace/work/g3-data/real-estate/`
- `/workspace/work/g3-data/slump/`

Each has `source-manifest.json` listing individual file bytes/SHA-256s, `retrieval.json` with URLs/status/time, `field-dictionary.json`, `preflight.json`, native-tested `evidence-selections.json`, `column-mapping.json`, `conversion-receipt.json`, and complete derivative CSV/spec under `inputs/`. Every listed file was rehashed successfully after generation. Logs are excluded from the immutable source-file list. `real-estate/prepare_inputs.py` reproduces both transformations and parser checks without fitting; do not rerun after the root freezes manifests without recording a new capture timestamp.

## Real Estate: source, fields and complete conversion

Official API reports **414** published real-estate records and **six inputs**, collected in Sindian District, New Taipei City, Taiwan. UCI page donation date is 2018-08-17; the API creation year is 2018. Transaction date is retained as its original decimal encoding, not converted to daily timestamps or treated as house age.

| Published field | Mapped column | Role / preserved source unit |
|---|---|---|
| `No` | `original_no` | Original ID; excluded from training |
| `X1 transaction date` | `transaction_date` | Feature; published decimal calendar-date encoding (e.g. 2013.250 means March 2013 per source) |
| `X2 house age` | `house_age` | Feature; **year** |
| `X3 distance to the nearest MRT station` | `distance_to_mrt` | Feature; meter |
| `X4 number of convenience stores` | `convenience_stores` | Feature; count in walking living circle |
| `X5 latitude` | `latitude` | Feature; degree |
| `X6 longitude` | `longitude` | Feature; degree |
| `Y house price of unit area` | `house_price_unit_area` | Target; **10000 New Taiwan Dollar/Ping** |

The target is price **per Ping**, not total house price or NTD/m². Official documentation says `1 Ping = 3.3 meter squared`; preserve its published numerical target and unit. Do not replace it with another conversion constant or silently rescale. Source `.xlsx` is retained separately; source-of-record for this reproduction is the official API CSV. No XLSX/API token equality or cell-by-cell reconciliation is claimed.

All **414 × 8 = 3,312** original numeric tokens, including `No` and target, and original order are exactly preserved. Add `source_row` and `location_group`; **259** groups are first-appearance IDs of exact Decimal `(latitude, longitude)` tuples, **191** are singletons and maximum group size is **13**. All original values are finite; no row exclusion, imputation, rounding, deduplication, target conversion or truncation occurred. No duplicate original value records excluding `No` were found. There are **17** zero-valued house ages; `log1p` is numerically defined without altering them.

Verifier-facing rule:

```json
{"kind":"decimal_columns","columns":["latitude","longitude"],"target_column":"location_group","id_prefix":"location-","id_width":4}
```

Six model inputs are exactly `transaction_date, house_age, distance_to_mrt, convenience_stores, latitude, longitude`. `source_row`, `original_no`, and `location_group` are not model inputs. Only `{"house_age":"log1p"}` is the predeclared expression candidate; transaction date is not transformed. Location tuple equality is not verified property/household identity, independence, or a geographic region split; nearby locations and time dependence remain limitations. A grouped result cannot certify future-market or other-city performance.

## Slump: official API gap, real raw CSV and endpoint meaning

Official metadata's structured variable table is blank and `data_url` is null; the guessed modern `.../182/data.csv` endpoint returned **HTTP 404**, retained as a failed retrieval. The official ZIP successfully contains the original **CSV-formatted** `slump_test.data` and original documentation `slump_test.names`. These originals are the source of record; there is no invented successful API CSV or readme.

The `.names` file and official page agree on **103** observations, **seven input quantities** in kg per m³ of concrete and **three output variables**:

| Published field | Mapped column | Role / unit |
|---|---|---|
| `No` | `original_no` | Original ID, excluded from training |
| `Cement, Slag, Fly ash, Water, SP, Coarse Aggr., Fine Aggr.` | `cement, slag, fly_ash, water, superplasticizer, coarse_aggregate, fine_aggregate` | Seven features, each kg/m³ |
| `SLUMP(cm)` | `slump_cm` | Other outcome, cm, retained but excluded from strength-model features |
| `FLOW(cm)` | `flow_cm` | Other outcome, cm, retained but excluded from strength-model features |
| `Compressive Strength (28-day)(Mpa)` | `strength_28d` | Chosen target: 28-day compressive strength, MPa |

Original `.names` describes an initial 78 records followed years later by 25 additional records, but does not supply reliable per-row batch/laboratory identity. Do not create a validated temporal/batch split from that sentence. It cites Yeh's 2007 *Modeling slump flow of concrete using second-order regressions and artificial neural networks*; retain the citation request and data license. No cited paper body or reported model performance was used.

All **103 × 11 = 1,133** original numeric tokens, including ID and **all three outputs**, and original order are preserved. Add `source_row` and `mixture_group`. Exact Decimal seven-input tuples give **103** unique groups, all singletons. All numbers are finite; no rows were removed or target values transformed. No original value duplicates excluding ID were found. This native grouped baseline consequently separates unique input signatures, and does not establish held-out experimental batches.

Verifier-facing rule:

```json
{"kind":"decimal_columns","columns":["cement","slag","fly_ash","water","superplasticizer","coarse_aggregate","fine_aggregate"],"target_column":"mixture_group","id_prefix":"mixture-","id_width":4}
```

There is **no age feature**. “28-day” is the fixed strength-response condition, not an observed per-row age. The Concrete age-transformation candidate is therefore **not applicable**. Preserve the actual field-based rejection/wait, keep `candidate_transform:null`, and do not substitute cement, transaction-like IDs or an invented constant 28-day field. Native case association can only check generic mechanical contracts; it does not provide this semantic decision automatically.

## Sample overlap and transfer limits

Both targets and the source Concrete dataset list **I-Cheng Yeh**; changing dataset/task does not establish an independent laboratory or different investigators. Conversely, common authorship alone does not prove sample overlap.

An explicit arithmetic comparison used original published seven-ingredient values only, as exact Decimal tuples in matched ingredient order. Source Concrete has **427** unique signatures; Slump has **103**. Their intersection is **one** tuple: Slump original row/ID **15**, source Concrete row **838**. One target record and one source record have these ingredient quantities. They were retained unchanged. No target-strength or model-error comparison was made for this match; equal ingredients do not by themselves establish the same physical specimen or endpoint observation. Slump must not be described as fully disjoint samples, and the semantic non-applicability case is not an independent efficacy result.

Source Concrete age is in **days** and refers to material age/curing conditions; Real Estate age is in **years** and refers to a house. `log1p(house_age_years)` and `log1p(concrete_age_days)` are dimension- and meaning-sensitive representations, not the same physical law, parameter transfer, or guaranteed method. No automatic years→days conversion is justified by the source experience. The one selected-column test may produce benefit, no benefit or harm under the target's frozen evaluation; no outcome was calculated during this data preparation. There is no independent domain-expert approval, causal-memory arm or unseen-task scientific claim here.

## Key fixed hashes

| Dataset / file | SHA-256 |
|---|---|
| Real Estate official API CSV | `0730a5687ec285a3c2f9921a808855bd1bde21fc53e6377561cbdce2dda9cbb1` |
| Real Estate original ZIP | `aa437bdac3ca23200258a0a58d251c0af90651aeaf7c7a07aaa714f0f9f25e2c` |
| Real Estate `inputs/real-estate.csv` | `260416d0c66b3c93fcfce9ea0e861cb1aa0a6c7dc7313dbd740309c5ff77c389` |
| Real Estate `inputs/spec.json` | `3a8ef36e957f6713ccb5ff279cb6dfdda66310b1caf6a8ad584db434d70ea2b7` |
| Slump original ZIP | `68d6a6813261bf8ecf79d8d7cc82b665bd5e9e6800c7705a16e671688c78e491` |
| Slump original `slump_test.data` | `78cea9fbb28ad8fc17f389e216e724dc04642c6c363143e67f6bcb97e74525ee` |
| Slump original `slump_test.names` | `7b2e1c99d25b46de3cc6abf78c6999ac87ca5cb5162deca990bb1aaeae63bd0e` |
| Slump `inputs/slump.csv` | `722f3eb1d4b39e9c06f837d7b5177f0b5ef52c35bd9207163f186449043b0a27` |
| Slump `inputs/spec.json` | `813c221983c61f9f5d1c369476b361ef4dba3a14a3eac4549585fe77e1f5b7e6` |

`column-mapping.json` has the evaluator's complete ordered `original_columns`, ordered `{source,target}` mapping, `source_row_column` and closed grouping schema. `conversion-receipt.json` adds absolute original/derived CSV and spec paths/hashes, `feature_columns`, `target_column`, `target_unit`, `split_group_columns` and the proposed `candidate_transform`. Root supplies separately approved per-target budgets and experience identity when freezing the final verifier config; conversion does not grant execution.

## Native source-evidence selections

Use original `.names` and retained official-page Markdown, preserving exact bytes and honest representation identity. Locator format is `{"kind":"text_lines","value":"55-79"}` with a string one-based inclusive range. Native extraction was actually checked for all five selections:

- Real Estate `official-page.md`, `text/markdown`, **55–79**: six inputs, house-age and price units; **95–114**: creator/DOI/CC BY.
- Slump `archive-originals/slump_test.names`, `text/plain`, **30–52**: sample description, seven inputs and three endpoints; **76–80**: requested citation.
- Slump `official-page.md`, `text/markdown`, **92–107**: creator/DOI/CC BY.

The Markdown is a derived Firecrawl page capture, not original HTTP HTML. Raw HTML and metadata are retained independently. Evidence source hashes and exact extraction text are in `evidence-selections.json`; future registration/reading must bind real project/action IDs and source allowance. Do not turn this offline extraction check into a claim that a future native project or model already read those sources.
