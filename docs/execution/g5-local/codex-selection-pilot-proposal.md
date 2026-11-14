# S050: proposed one-shot Codex selection pilot

This is an engineering probe, not a production provider or a scientific study. The default command prepares a new fixed three-document synthetic project and a sealed existing selection context. It makes no model request and creates no positive Host decision grant. Project tool calls and fits remain zero. The project API requires a prospective tool-call limit of one; the probe never dispatches it. Preparation records the exact prompt, stdin, schema, source commit and code identities, CLI version and executable SHA-256, original project budget, and command arguments.

The real run requires a **new explicit user approval**, after this script and proposal have been reviewed and published. It is limited to one Codex CLI model execution and one logical delegated Host selection. There is no authorization to consume or dispatch its proposal. Current authorization remains zero model calls. The CLI may internally perform an unknown number of provider requests; token counts, real spending and maximum USD are unknown. The Host API requires a `0.1` USD configured estimate field, but a delegated response is externally executed and that field does not cap this CLI, enforce spending, or establish a charge.

After publication, use a clean checkout of the exact published commit with the original dependencies and run:

```sh
PYTHONPATH="$PWD/src" python scripts/probe_codex_selection.py --source-commit <40-character-published-commit>
```

The fixed workspace is `runs/s050-codex-selection-pilot`; preparation refuses an existing workspace. Preserve partial failures, and do not create a replacement project or change IDs to retry. Preparation calls only CLI `--version` for metadata, never `codex exec`. It returns the preparation SHA and a pending approval status. Only after review and publication may the user approve the described one-decision scope in their own words. No generated template or operator statement is itself approval. If and only if the user actually approves this exact prepared scope, transcribe their actual message and a reference to the original user message into a canonical JSON file, together with the separate prepared SHA and the one-decision bound:

```json
{"approved_decisions":1,"prepare_sha256":"PREPARE_SHA256","schema_version":"s050-user-approval-v1","source_reference":"REFERENCE_TO_ACTUAL_USER_MESSAGE","user_message":"ACTUAL_USER_MESSAGE"}
```

The script checks those bytes and binds the approval to the complete preparation, which includes source, CLI, context, argv and one-call limit. This is an operator-maintained record, not cryptographic authentication of the user message. The operator must check the referenced original. Do not create a record purporting to be user approval without the actual user message. To execute an approved original:

```sh
PYTHONPATH="$PWD/src" python scripts/probe_codex_selection.py --execute --approval-file /absolute/path/to/original-approval.json
```

Before any positive Host grant or model launch, execution verifies that approval, the original clean published source, executable and version, project, context, prompt, schema, source files and empty isolated working directory still match. Before loading project modules, the script switches Python bytecode lookup to a fresh private cache namespace and disables cache writes; this prevents the ordinary source-tree `__pycache__` from substituting stale code, not arbitrary host compromise. An exclusive launch marker precedes both Host preparation and process creation; its file and parent directory are fsynced, and a sync error stops execution. This basic durability step is not proof against every power-loss or filesystem failure. Once this marker exists, even a crash or failed process start is unknown and must never be retried under this or a new ID. Preserve stdout JSONL, stderr, exit receipt, final message, Host record and any validated proposal. A successful proposal is validated by the existing Host selection protocol, imported as a delegated response and **never consumed**. It cannot trigger a project tool.

The available CLI advertises `--ignore-user-config`, `--disable <FEATURE>`, `--ephemeral`, `--json`, `--sandbox read-only`, `--output-schema`, and `--output-last-message`; the argv requests `--disable shell_tool`, avoids enabling web search, and uses a fresh empty working directory outside the checkout. The prompt asks for no tools. These are requested controls, not proof that shell, MCP, web, skills, filesystem access or network are technically disabled, nor proof of OS isolation. `--ignore-user-config` does not disable authentication. Any unexpected/recognizable tool event, error, missing terminal event, mismatched final output, invalid response, interruption or timeout remains unknown and stops. Do not hide such events or infer a safe outcome from the exit code alone. Output files may contain information emitted by the CLI and should be inspected before sharing.

This probe does not establish real model usage, a cost cap, research quality or performance. Both preparation and execution query actual `origin` main with `git ls-remote`, require its head to exist in the local Git object store, and verify that the exact source commit is an ancestor. If the remote head is not locally available, stop and fetch before rechecking; do not silently change the source commit. Observed remote heads are preserved separately as publication receipts and are not part of the immutable source identity, so a valid advance of main does not invalidate the prepared scope. Untracked importable files in `src` are rejected. Do not reuse old research workspaces or budgets.
