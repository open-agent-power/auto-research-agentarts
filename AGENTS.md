# Product working agreements

- Start with `docs/README.md` for implementation boundaries and `DESIGN.md` before any UI work. The unified UI uses an X6 research canvas with restrained floating glass navigation, solid reading surfaces and a mobile list fallback. Edit `frontend/` and rebuild the packaged `web/` assets, never maintain a second hand-edited runtime theme.
- Keep actual implementation in `src/`, product architecture/design in `docs/`, reusable request examples in `examples/`, and local evidence in ignored `runs/` and `.agent/`. External source archives belong to the workspace reference library, never the product code tree.
- Distinguish implemented modules from proposed architecture. Canvas positions and visual connectors must not overwrite experiments, citations, evaluation protocols or research state. A draft question or manual connector does not execute research or establish a scientific claim.

- Mission: continuous cross-domain research with traceable experiments, evaluated strategy or model changes, and resumable execution. Topic generation is an entry point.
- Root owns contracts, persistence, integration and final verification. Reuse existing agents; delegate only independent work worth parallelizing. Never revert another contributor's changes.
- The engineering fixture does not establish biomedical, materials or cross-domain scientific validity. A local runner is not an AgentArts integration or an LLM weight-training result.
- Keep execution state, scientific status, and candidate promotion separate. Evaluators and hidden labels must not be editable through candidate requests.
- No arbitrary Python, shell commands, pickle loading or user-selected filesystem paths through the tool protocol. Initial tools are explicitly allowlisted.
- Never commit credentials, private data, browser state, reference repositories, run outputs or local focus checkpoints.
- Use one ignored `.agent/focus.json` for the active development round. Preserve actual failures and missing integration evidence.
- Validate persistent state, idempotency, budget accounting, candidate rejection and recovery with real execution before claiming completion.
- UI work must be checked using actual rendered screenshots under the user's visual inspection rules.
