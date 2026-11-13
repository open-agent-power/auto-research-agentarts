# Upstream check receipts — static only

Run on 2026-11-12 using the host's isolated interpreter `python -I` and stdlib ast/json/tomllib. Upstream Python was read/parsed, **never imported/executed**; no dependencies installed, images built, model calls or account actions. Exact file hashes and outcomes: static-checks.json.

Eight shallow clones succeeded and each HEAD/default branch was recorded. Source trees were clean when checked. Twenty-six Python paths parsed successfully (2 autoresearch, 6 AI-Scientist, 7 AgentLaboratory, 2 Prime, 3 software-agent-sdk, 3 BEIR, 3 Ragas). One guessed Prime client.py path was missing and is explicitly retained in the receipt; actual implementation was subsequently read at prime_sandboxes/sandbox.py. Root TOML/JSON dependency manifests parsed. Nonfatal invalid-escape SyntaxWarnings appeared in legacy writeup/report/util strings. None proves import or dependency compatibility.

| Requested smoke | Actual status | Reason / required next check |
|---|---|---|
| Karpathy GPU baseline | not run | host lacks established CUDA/GPU; irrelevant to CPU P0 research |
| Sakana generated experiment | not run | dependency/license/isolation/API prerequisites not approved; source confirms unsafe host subprocess |
| AgentLaboratory literature→report | not run | exec/checkpoint risks and model credentials; not needed for native G1 |
| Prime service CLI | not run | wrong source identity for intended harness; do not provision charged resources |
| OpenHands worker | not run | canonical SDK located; requires bounded Docker resource/credential PoC after G0 |
| BEIR/Ragas | not run | source feasibility only; select licensed real task and correct metric before installing |
| AIDE² | not reproduced | paper read; source/code endpoint not established |

The execution pack requests isolated runtime smoke: this subtask has **not satisfied that item**. Static parsing must not be relabeled a runtime smoke. Root should leave corresponding acceptance condition open or explicitly scope it through an evidence-backed ADR; resources and native-product baseline are separate tests.

## Remaining guide obligation

Runtime smoke remains a separately **deferred/blocked** task for the original clone-and-audit guide. Choosing inspiration_only avoids an unnecessary current integration; it does not convert AST parsing into runtime completion or waive this obligation. G0 acceptance must list it alongside any Docker or credential blocker. Optional SWE-bench/Pro, OpenTelemetry and Optuna/Nevergrad/DEAP references are later extension tasks, not all required clones for this P0 batch.
