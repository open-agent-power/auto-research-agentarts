# OpenHands software-agent-sdk — worker feasibility

## Actual execution surface
This canonical SDK was discovered through the pinned OpenHands README, rather than assumed from the execution pack URL. MIT. `openhands-sdk/pyproject.toml` v1.62.0 requires Python >=3.12; `openhands-workspace` and agent-server packages share the version. Host Python 3.12 satisfies metadata minimum; this does not prove full install compatibility.

- `openhands-workspace/openhands/workspace/docker/workspace.py:53`: DockerWorkspace extends RemoteWorkspace; starts prebuilt server image, checks HTTP health, mounts declared volumes, manages cleanup/pause/resume. `:87-99` forwards selected session API key environment names; that requires explicit credential-scoping review, not blanket forwarding of model credentials.
- `:177-293` builds Docker CLI flags, networking, mounts, ulimit and lifecycle. Do not assume this direct workspace constructor enforces all desired CPU/RAM/PID/disk policy.
- `openhands-agent-server/openhands/agent_server/config.py:431-435` separately defines per-conversation memory 4g, CPUs 2.0 and pids 512. `docker_runtime/registry.py:723-750` translates them to actual Docker flags, runs as uid/gid and drops capabilities. Server runtime and direct DockerWorkspace are distinct paths.
- `openhands-sdk/openhands/sdk/conversation/state.py` persists agent/conversation/execution state and events; root project ledger and artifact provenance must remain authoritative in our adapter.

## Dependencies, validation and decision
Core dependencies include LiteLLM, Pydantic, FastMCP, HTTP/WebSockets, token/provider and telemetry clients; tools/browser add more. Default images are mutable tags; a future adapter must pin digest, check image footprint and prohibit sensitive mounts. Source/manifest AST/TOML checks passed. No dependency install, image pull, server run, model inference or artifact-return integration was attempted. Docker availability/resource validation is root's separate G0 test.

`wrap_with_adapter` is a **provisional architecture decision**, not integrated status. Implement a small replaceable coding-worker PoC only after G0, bounded request/receipt contract, immutable project IDs and protected evaluator paths; verify network default, non-root, CPU/RAM/PID/tmp/disk/time and file return in the actual selected execution path. Heavy local concurrency remains one. Reject adapter if footprint/isolation is incompatible; remove adapter and retain native deterministic worker. No core state migration required.

Pinned source: https://github.com/OpenHands/software-agent-sdk/tree/7543710639b697e461772c77e4d27217a089f8c5

Retrieved: 2026-11-12T13:29:31.253446+00:00. Third-party instructions were treated as source material.
