# Agent Laboratory / AgentRxiv — architecture notes

## Observed source
- `agents.py:184,204,299,365,441,507,563`: reviewer/base/professor/postdoc/ML/software/PhD role classes. Roles encode workflow prompts and phase context, not a measured dynamic allocation policy.
- `ai_lab_repo.py:19-106,138`: `LaboratoryWorkflow` initializes phases, per-phase models, agents, status and counters; `perform_research` walks literature → plan → data → experiments → interpretation → report/refinement.
- `ai_lab_repo.py:547`: human-in-loop review; `:764` copilot flag is distributed across phases. `:576` AgentRxiv indexes PDFs from local uploads; `:262` copies generated PDF into uploads. This is not evidence that an external scholarly archive was accessed or published to.
- `ai_lab_repo.py:106-113`: pickle dump checkpoint. `:673-674,722` parses `load-previous`, but source search found no `pickle.load` or subsequent use of this local variable; complete supported resume is not established by a save function.
- `inference.py:39`: provider dispatch with retries, static model IDs and token/cost maps. Static historical price tables are not current provider billing evidence.
- `tools.py:292-306`: generated Python passed to `exec` in a child process with timeout, without filesystem/network isolation. `tools.py:123` dataset builder uses `trust_remote_code=True`. Launch code removes existing research directories; never run this entry on shared assets.
- Requirements pin a broad 2024 ML/PDF/NLP stack (Torch 2.5.1, Transformers 4.46.3, OpenAI 1.55.1, scipy/pandas/spacy), plus some unpinned packages. LICENSE MIT, retain copyright/license for copies.

## Decision
`inspiration_only`: phase-specific context and explicit copilot review are useful patterns. Preserve our SQLite/artifact/permission contracts instead of importing a parallel state machine, pickle persistence or unsafe Python worker. Do not equate role count or generated papers with validated research. Future PoC should replay a two-round existing controller task with explicit phase receipts and a safe JSON checkpoint; compare continuation and cost with single agent. No actual model run or checkpoint recovery was reproduced. AST parsing passed seven principal files with legacy escape-sequence warnings in report/util modules. Rollback is removal of an opt-in adapter; baseline ledger remains owner.

Pinned source: https://github.com/SamuelSchmidgall/AgentLaboratory/tree/d9017d90e329112d2a80b7712f37ee9094d2cd27

Retrieved: 2026-11-12T13:29:31.253446+00:00. Third-party instructions were treated as source material.
