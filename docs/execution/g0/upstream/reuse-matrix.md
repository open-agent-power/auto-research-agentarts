# Upstream reuse matrix — G0

All decisions are architecture recommendations, not installed integrations. No upstream code is in the product tree.

| Source | Decision | Gap/value | Cost and risk | Validation before integration | Rollback |
|---|---|---|---|---|---|
| Karpathy autoresearch | inspiration_only | frozen evaluator, bounded trial, keep/reject | GPU-only baseline; license text missing; reset/infinite-loop instructions unsuitable | CPU native-controller bounded trial and immutable receipts; license clarification for any copy | remove optional pattern, never reset shared history |
| AI Scientist | inspiration_only | experiment template, code snapshot, limited repair loop | restrictive license, generated host code, GPU/LaTeX and unpinned deps | exact license review and bounded worker contract; preserve failed artifacts | no package integration planned |
| Agent Laboratory | inspiration_only | phase context and copilot review | exec, pickle checkpoint without established resume, large old ML closure | JSON resume and cost/continuity comparison on real task | preserve native ledger |
| Prime URL | reject | catalog identity does not establish intended mutable harness | service CLI is wrong evidence; cloud resource charges | locate intended Prime Agent source first | none |
| OpenHands root | inspiration_only | UI/server separation | Canvas/Electron is unnecessary dependency for existing UI | use canonical SDK instead | none |
| OpenHands software-agent-sdk | wrap_with_adapter (PoC deferred) | optional isolated coding worker | image footprint, path-specific resource and network controls, credential mounts | explicit Worker protocol + real constrained Docker run + artifact return | disable adapter, keep native worker |
| AIDE² paper | inspiration_only | public/private separation and fixed-budget cross-task candidate selection | code not found in inspected sources, expensive/noisy multiseed study | implement independent protocol; cannot claim AIDE² reproduction | preserve baseline, reject candidate |
| BEIR | wrap_with_adapter (PoC deferred) | fixed qrels and deterministic IR metrics | default dense dependency closure; BM25 uses Elastic; data license separate | licensed small corpus, metric cross-check, sealed split, CPU measurements | optional benchmark disable |
| Ragas | wrap_with_adapter (PoC deferred) | optional reference-ID and generation metrics | base provider deps, LLM judge cost/noise | explicit metric/provider and rubric; human spot checks for judge | keep deterministic IR evaluation |

Choose the least new machinery that closes the measured G1 gap. No need to install three frameworks to demonstrate three source audits. Dynamic Agent or RSI integration depends on later Gates.
