# G0 real research data selection

Date: 2026-11-12 (Asia/Shanghai). Auditor: `research_task`. Input source commit: `5d497c8ae22100953f66c3c5b54746ca87e09f01`.

## Decision

Select **UCI Concrete Compressive Strength** for the first cloud vertical slice. This is a new cloud reproduction project with real laboratory data, not continuation of a missing local run and not a novel-data or blinded-discovery benchmark. Existing documentation already reveals outcomes; the system must report that prior knowledge explicitly. Selection and the candidate comparison are Agent decisions under the execution plan, not confirmation by a domain expert.

| Candidate | Existing usable design | Main advantage | Limitation and decision |
|---|---|---|---|
| Concrete, 1,030 rows / eight inputs | `examples/research-designs/concrete-mixture-transfer.json`, `...-v2.json` | Real laboratory measurements, small CPU workload, original raw-unit description, existing fixed-input-basis comparison | Batch/specimen/laboratory IDs missing. **Select** for bounded reproduction and feedback continuity. |
| Airfoil, 1,503 rows / five inputs | `airfoil-setting-transfer.json` | Real wind-tunnel measurements, saved group diagnostics | Scaled-dB semantics and independent run IDs unresolved; retain as second task. |
| Energy, 768 rows / eight inputs | `energy-geometry-transfer.json` | Cheap complete-case baseline and 12-group diagnostics | Ecotect simulation rather than independent physical buildings; units not established. Useful transfer task, not first physical-data choice. |
| Auto MPG, 398 published / 392 complete cases | `auto-mpg-origin-transfer*.json` | Small real historical data and adverse feature-ablation example | Vehicle independence, geography-code and unit details require more care; three-group external validity limited. |
| Yacht, 308 rows | `yacht-geometry-transfer*.json` | Existing failed and successful expression comparisons | Native hull mapping, target scale and model/full-scale source discrepancy unresolved. Defer as first topic. |

The table records repository document/design inspection, not freshly rerun outcomes for these five tasks. Historical runs are ignored and absent from this clone. The sole packaged `src/autoresearch/data/matbench_steels.json.gz` does not contain these five study inputs.

## Official source and license checks performed now

- Official page: https://archive.ics.uci.edu/dataset/165/concrete+compressive+strength
- Dataset DOI: https://doi.org/10.24432/C5PK67
- Author: I-Cheng Yeh. Introductory paper: I. Yeh (1998), *Modeling of strength of high-performance concrete using artificial neural networks*, DOI `10.1016/S0008-8846(98)00165-3`. The paper body was not obtained or claimed read.
- The official page explicitly states **CC BY 4.0**, not a license inferred merely from being on UCI. Retain attribution, license link and transformation description with every redistributed dataset bundle.
- The official `Concrete_Readme.txt` independently states unlimited database reuse with retention of Prof. I-Cheng Yeh copyright notice and the 1998 paper citation. Preserve that original notice. Dataset license is not a blanket license for journal-paper text or third-party software.
- Firecrawl live page scrape returned HTTP 200, scrape ID `01a1cfee-6c99-744b-b8c5-95068af71ba7`. Retrieved official API, CSV, ZIP and original readme using normal HTTPS with verification enabled; no package installation or model API call.

Local source snapshots: `/workspace/work/g0-data-research/`; full source manifest is `source-manifest.json` in that directory.

| Original | Source URL | SHA-256 |
|---|---|---|
| `data.csv` | `https://archive.ics.uci.edu/static/public/165/data.csv` | `8d4b15b6fc68cd932d745cbd663d5ceae66dd54422e99c1e4865f2936ab7e2af` |
| `concrete-compressive-strength.zip` | `https://archive.ics.uci.edu/static/public/165/concrete+compressive+strength.zip` | `dad85d14de8aee4e07479daa774e6b569a313715b71a3b92c95a07cf91c2c9a7` |
| `Concrete_Readme.txt` | `https://archive.ics.uci.edu/ml/machine-learning-databases/concrete/compressive/Concrete_Readme.txt` | `5cd3cdb31d3cfd68287daa6b22ed0541d6932113e83ee0980ced63641af3441d` |
| `uci-concrete-api.json` | `https://archive.ics.uci.edu/api/dataset?id=165` | `e6bf60c33164024edd612f205e429b48cf66a08b639184567e24536c5e3f8e03` |

## Actual input inspection

Official CSV has nine headers, **1,030 rows**, eight inputs and one target. Numeric tokens and order are to be preserved in the derived project CSV. Exact Decimal tuples of the first seven ingredient values give **427** declared mixture signatures, of which **246** are singleton signatures. There are **25** additional exact duplicate nine-value records; retain and disclose all of them. These checks used CSV/Decimal arithmetic only; no regression fit or research outcome was generated.

ZIP contains `Concrete_Data.xls` and `Concrete_Readme.txt`; XLS cells have **not** been compared to the API CSV. Do not claim byte identity between API CSV and XLS. Baseline source of record will be the official API CSV; ZIP remains a separately hashed upstream archive.

## G5 / R13 CPU feasibility boundary

The planned BM25 baseline and fixed small BEIR corpus/query subset are CPU-suitable in principle; dense encoders, rerankers and Ragas LLM judging introduce downloads and/or external inference and are not yet installed, measured or validated. No RAG metric or task completion is claimed by this G0 selection. Freeze a small licensed corpus and development/held-out queries before the later RAG comparison. Avoid OpenTelemetry full-stack and GPU-training workloads in the first 4-core/16-GiB slice. Actual resource enforcement remains the root runtime audit's responsibility.
