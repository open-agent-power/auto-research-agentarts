# License and execution risk audit — G0

Date: 2026-11-12. Scope: eight exact Git commits plus AIDE² paper/post, recorded in upstream-manifest.json. This is source inspection, not a dependency vulnerability scan or legal certification.

## License findings

| Project | Observed license | Integration consequence |
|---|---|---|
| autoresearch | README states MIT, no LICENSE file at HEAD | source reading only; obtain full notice before copying |
| AI-Scientist | The AI Scientist Source Code License v1.0, Dec 2025 | **not MIT**; Section 3 use restrictions, manuscript disclosure and downstream obligations; no copying or dependency adoption approved |
| AgentLaboratory | MIT | retain copyright/license if later reused |
| Prime / OpenHands / software-agent-sdk | MIT | retain notices; hosted services have independent terms |
| BEIR / Ragas | Apache-2.0 | retain license/notices and mark modifications as applicable; dataset/model/API terms separate |
| AIDE² arXiv v1 | arXiv perpetual non-exclusive license indicated | method citation, no redistribution of paper text/source assumption |

All LICENSE/README/dependency file hashes are in manifest. Nested template assets may carry separate terms; a top-level license does not complete a copied-file audit. No production source was copied, no package installed, no account logged in, no paid compute provisioned, no secrets supplied. No claim of vulnerability-free dependencies is made.

## Concrete execution boundaries

- Karpathy `train.py` runs CUDA immediately; `prepare.py` downloads shards/tokenizer. Its `program.md` instructs an infinite loop and Git reset. These were read as source, never executed or adopted.
- Sakana `perform_experiments.py:30` executes generated Python with inherited process authority, and removes failed run directories. Its timeouts do not protect filesystem/network/budget or preserve failed evidence by themselves. Requirements unpinned; template/LaTeX tooling broadens attack surface.
- AgentLaboratory `tools.py:298` calls exec in a subprocess; `tools.py:123` enables dataset remote code. `ai_lab_repo.py:113` pickles process state; no supported complete recovery established. Main launch removes old research directories. Do not run against shared assets or load untrusted pickle.
- Prime CLI can create charged remote resources; cloning is not authorization to provision them. Catalog's intended mutable harness remains unresolved.
- OpenHands Canvas local mode runs an agent server with host file access. Canonical SDK DockerWorkspace and per-conversation server runtime are separate paths: verify actual flags, network, mounts, uid/caps, timeout and artifact-return behavior for the chosen path. Pin image digest. Do not grant Docker socket, evaluator, baseline, credential or whole-host mounts to untrusted candidate code.
- BEIR default BM25 uses Elasticsearch; dense retrieval downloads models. Code license is not dataset permission (BEIR README explicitly warns). Ragas LLM judges need selected provider, budget/rubric and independent audit; CPU ID metrics are narrower claims.

## Gate implications

Core three repositories fixed/read: yes. License/runtime risks identified: yes. Runtime smoke of these frameworks: **not run** (no production need established, GPU/API/isolation prerequisites absent). Static checks: recorded separately and must not be counted as live experiments. AIDE² code-level reproducibility remains unestablished. Root owns G0 resource test and final acceptance. These notes do not authorize bypassing any Gate.
