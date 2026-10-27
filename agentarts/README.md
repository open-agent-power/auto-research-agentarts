# AgentArts tool boundary

The implemented entrypoint is `autoresearch.protocol.handle_request(request, workspace)` or `python -m autoresearch tool --workspace <operator-controlled-dir>` with JSON on stdin.

Requests use schema version `0.1`, a `request_id`, and one action: `create_campaign`, `campaign_status`, `run_trial`, `pause_campaign`, `resume_campaign`, `finalize_campaign`. Campaign actions require `campaign_id`. Only `run_trial` accepts an optional `candidate` containing `degree` (1–3) and `alpha` (0–1000000), plus a reason. Create accepts goal and max_trials (1–20). Extra fields are rejected.

Create and trial request IDs are idempotency keys scoped to this workspace and campaign respectively. Same ID with changed semantic input is a conflict. A retry of a running trial returns its recorded state; it never starts a second training job. Status, pause, resume and finalization are separate operations; terminal evaluation locks the campaign.

The workspace is supplied by the operator, never by the model request. The protocol accepts no code, commands, dataset paths, evaluator, score or hidden labels. Interrupted in-flight work requires the operator-only reconciliation command after the operator checks that its worker has stopped. This command is intentionally absent from the model-callable actions.

## Integration still to verify

1. User signs into AgentArts in a supported browser. Inspect region, existing resources and billing; determine a call budget before execution.
2. Select a code interpreter or controlled runtime capable of installing the pinned dependencies. This repository does not assume the normal workflow code node supplies that environment.
3. Invoke the actual entrypoint and preserve both platform execution identity and request/trial IDs, input, output and tool result. A local fixture response alone is not platform evidence.
4. Save and publish a dedicated test workflow, then run its success/error paths and independently reproduce it.

No AgentArts workflow or cloud integration has been executed by this code. Do not expose a development service on the public network to bypass environment setup. Long training jobs will need a separately verified submit/status/collect executor; this release only runs the fixed, small CPU fixture synchronously.

Official references: [code interpreter](https://support.huaweicloud.com/highcode-agentarts/agentarts_10_008.html), [HTTP node](https://support.huaweicloud.com/lowcode-agentarts/http_node.html), [billing](https://support.huaweicloud.com/price-agentarts/agentarts_08_0001.html).
