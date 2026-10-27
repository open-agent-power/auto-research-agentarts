# Product working agreements

- Mission: continuous cross-domain research with traceable experiments, evaluated strategy or model changes, and resumable execution. Topic generation is an entry point.
- Root owns contracts, persistence, integration and final verification. Reuse existing agents; delegate only independent work worth parallelizing. Never revert another contributor's changes.
- The engineering fixture does not establish biomedical, materials or cross-domain scientific validity. A local runner is not an AgentArts integration or an LLM weight-training result.
- Keep execution state, scientific status, and candidate promotion separate. Evaluators and hidden labels must not be editable through candidate requests.
- No arbitrary Python, shell commands, pickle loading or user-selected filesystem paths through the tool protocol. Initial tools are explicitly allowlisted.
- Never commit credentials, private data, browser state, reference repositories, run outputs or local focus checkpoints.
- Use one ignored `.agent/focus.json` for the active development round. Preserve actual failures and missing integration evidence.
- Validate persistent state, idempotency, budget accounting, candidate rejection and recovery with real execution before claiming completion.
- UI work must be checked using actual rendered screenshots under the user's visual inspection rules.
