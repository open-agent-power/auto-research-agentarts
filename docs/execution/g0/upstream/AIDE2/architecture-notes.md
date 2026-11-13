# AIDE² — paper/method/reproducibility audit

Primary source: [Recursive self-improvement of AI research agents, arXiv:2609.26457v1](https://arxiv.org/html/2609.26457v1), version dated 22 September 2026. Full HTML read through Firecrawl on 12 November 2026 (cache observation 2026-11-12T09:20:57Z). Secondary official source: [Weco post, 14 July 2026](https://www.weco.ai/blog/first-evidence-of-recursive-self-improvement), cached 2026-11-11. These are source reports, not independently reproduced results.

## Mechanism confirmed in paper Sections 2.1–2.2 / Algorithm 1

Inner loop edits runnable task code with access to a public metric. Search policy, parent/return choice and context/memory are part of editable agent code. Outer loop edits the current incumbent inner agent's full harness, then grades candidate-returned solutions on private task data unavailable to the candidate. The outer selection rule is fixed, unlike editable inner selection. Costs include model tokens and solution execution under the same per-task cap; extra best-of-N calls/parallel compute cannot be treated as free performance.

Selection tasks span ML engineering, heuristic algorithm engineering and harness engineering. During selection the outer model is held at Claude Opus 4.7, inner at Gemini 3 Flash, as reported by the paper. We did not access either model or verify current access/prices. Fixed outer evaluator, heldout data, cost meter and selection controller must remain outside candidate ownership in our design.

## Reported evidence and limitations

Section 3.2 reports a 100-node trajectory (baseline plus 99 proposals), eight days, seven accepted rewrites at steps 2/6/28/39/47/63/85, private grade 0.703→0.778. Two additional full runs accepted two and four rewrites. Section 3.3 checks four benchmarks outside selection: ALE-Bench, MLE-Bench, FML-Bench and WeatherBench 2. Private selection scores alone are explicitly insufficient for task-level generalization.

Section 3.4 / abstract report reward hacking **55%→32%**, versus 39% human baseline. Earlier official blog reports **63%→34%**, versus 42% human baseline, and three external benchmarks rather than four. Preserve source/version provenance; do not mix these counts. Use the technical report for formal claims.

Section 3.6 finds ignition comparison inconclusive with three outer-loop seeds per arm and compounding variance; do not infer a better improver or sustained acceleration merely from an inner-agent gain. Cost of nested evaluation and complexity/dead code in evolved agents are practical limitations. A one-step local candidate experiment cannot establish these reported multigeneration results.

## Code availability and reproduction status

No AIDE² code repository/release link was found in the inspected full paper or official blog. A separate web search for AIDE2/Weco/GitHub returned secondary discussion, not an official code endpoint. This establishes **code availability unverified in inspected sources**, not that no public code exists anywhere. Earlier AIDE, Karpathy autoresearch and OpenEvolve links are separate systems and must not be relabeled AIDE² code. No experiment, hidden benchmark, agent code, seed-level raw result or cost account was reproduced.

Paper page states arXiv perpetual non-exclusive license; do not assume code licensing from paper access. Reference retrieval metadata are retained in `source-receipts.json`; no full paper copied into the product.

## Reuse decision

`inspiration_only`: independently implement explicit baseline/candidate provenance, protected public/private evaluation and cost-bounded trials only when G4 is reached. Fixed baseline/controller/evaluator and hidden data must not be candidate-writable or accessible through worker mounts. Compare multiple seeds and independent tasks, preserve negative results, reject on integrity failures. Initial P0 remains one real two-round research task; do not begin nested multiday optimization to satisfy a literature reference. Rollback keeps baseline and archives rejected candidate lineage.
