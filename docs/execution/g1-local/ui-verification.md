# G1-L native workbench read-only verification

Date: 2026-11-13 (Asia/Shanghai). Independent product verifier: `research_task`. Service: `http://127.0.0.1:18830`; original case: `runs/cloud-concrete-local-20261113-01/`. This verifies existing rendered behavior and exported evidence, not a visual redesign, scientific validation, or user satisfaction.

## Observed identity and no-write boundary

GET `/api/project`, `/api/local-workbench`, and `/api/local-workbench/model` confirm:

- project `project-431366b59dac432dabb315d82dee6eae`, state **32**;
- adopted plan **v3**, research state **waiting**;
- **20** estimator attempts and **5** local tools used; project model/API sends **0**;
- local action writes **disabled**, model runtime **disabled**.

Chromium was launched with the existing Python Playwright and `/usr/bin/chromium`; no installation or UI source change. Browser routing allowed only GET/HEAD to this loopback origin and aborted other methods/origins. The nine-view main pass recorded **22 GETs**, no nonread request attempts, **0 page errors**, **0 HTTP errors**. Canonical `/api/project` projection before and after is identical, SHA-256 `efa40c9cc4cf090dabe691ad8612f833a8a72e4123236fda0fd2e990439d2173`. No research dispatch was triggered.

Reproducible main check: `python -B runs/g1-local-ui/verify_ui.py`; raw outcome: `runs/g1-local-ui/result.json`, browser log: `log.txt`. Two earlier helper failures (wrong API-envelope assumption and a `body` selector matching X6 SVG foreign-object bodies) are retained in `initial-helper-error.log` and `second-helper-error.log`; they are verifier defects corrected before the successful pass, not product failures.

## Rendered pages and findings

| Viewport | Pages captured | Navigation/result |
|---|---|---|
| 1440 × 1000 desktop | Overview, research, experiments, knowledge, outputs | All five native page titles and active navigation states correct |
| 390 × 844 mobile | Overview, research, experiments, outputs | All four representative pages load with correct active navigation |

Nine full-page PNGs and their visible text captures are saved as `desktop-*.png/.txt` and `mobile-*.png/.txt` under `runs/g1-local-ui/`. Representative overview, experiments, knowledge and outputs screenshots on the captured devices were actually inspected. Automated measurement found no positive whole-page horizontal overflow; mobile numeric tables intentionally have internal horizontal scroll rather than fitting all columns at once. Mobile full-page captures include the fixed bottom navigation at the viewport's initial position; that static overlay is not proof of a scrolling obstruction.

Research and experiments visibly retain this run's **baseline MAE 8.383388056181742 MPa** and **candidate MAE 5.702072514528066 MPa** (UI summaries round to 8.38339/5.70207). The research design comparison/plan records explicitly retain **313 worsened rows / 129 worsened groups**, **one negative candidate prediction**, and the negative row prediction **−1.962895071052401 MPa**. Native saved diagnostics show candidate negative/below-observed/above-observed counts **1/7/0**, versus baseline **0/0/0**. The same group fields and negative-count text remain present on mobile. These are this run's current saved results, not imported historical MAEs.

Overview displays adopted plan v3, stop at 20/20 fits and 5/6 local tools, and waiting for independently characterized data/review. Knowledge displays two registered originals, completed source reading, and the three expected source selections. Outputs provides the four current snapshot attachments. Current plan and report distinguish the saved-result improvement from scientific approval, new independent data, engineering deployment or RSI.

An additional GET-only mobile interaction pass expanded the **current candidate's complete 427-group table**, verified `mixture-0427` and all **427 rendered data rows**, then scrolled the table horizontally from 0 to **378 px** (282 px viewport / 660 px content). The retained official-page selection was expanded and its actual text includes the dataset DOI and **CC BY 4.0**. Both interactions left the project projection unchanged, with no page errors or write attempts. Evidence: `interaction-result.json`, `mobile-candidate-group-table-right.png`, `mobile-license-source.png`. Initial interaction-helper selectors also matched a hidden outputs-page table because all pages coexist in the SPA; scoping to visible summaries corrected the verifier, without changing UI code or research state.

## Download and PDF checks

All four existing `/api/project/<file>` downloads returned HTTP **200** and matched both the mounted manifest and actual disk files byte-for-byte:

| File | Bytes | SHA-256 |
|---|---:|---|
| `report.pdf` | 133445 | `e6147a112a3b18f401d9544492daa3adcf6fbed91a5665ee5d4991dcbb61d455` |
| `report.json` | 3428119 | `c4bd7580d8b53fb19a1095f3c52aa5146234fe769b5c05d6bedac814591afbc5` |
| `report.md` | 83811 | `12f8a386d8daa05ad4580d1189b7263ee6eb6473d364fdac1ef1fa88be99bd11` |
| `input.json` | 118058 | `6694a64e2cb950f5f63f553823303f0bf6f5ea68e611c6324c7972f64c55e1a4` |

The downloaded PDF has **39 pages** and extractable text containing both MAEs and negative-prediction limitations. Page **1** and page **39** were rendered with installed PyMuPDF and actually inspected (`pdf-first.png`, `pdf-last.png`): the first page contains plan v3, actual comparison, adverse outcomes and wait; the last retains code/input identity, resumption instructions and scientific limitations. This is **not** a full 39-page visual/layout audit. See `pdf-result.json` and `pdf-text.txt`.

## Interpretation and limits

- Native quality UI reports zero exact duplicate **11-field input rows**, since `source_row` is unique; this does not contradict the **25 duplicate original nine-numeric-value records** independently retained in the input/preflight and explicitly stated in plan v3. Do not report this UI zero as evidence that the original physical records are all independent or unique.
- Native overview still offers possible zero-fit methods even while the adopted plan says wait. That is a list of technical candidates, not an authorization or evidence of automatic dispatch; writes are disabled and no action was sent.
- Full precision and unfavorable outcomes are available through native detail/report paths; default overview and outputs summaries do not display every result. Their omission from a collapsed summary is not proof of absence from the saved record.
- This read-only browser pass does not establish real-user satisfaction, multi-user collaboration, secure Docker isolation, autonomous model-runtime operation, new-data generalization, causal effects or G2–G6 completion.
