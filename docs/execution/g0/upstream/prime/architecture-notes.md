# Prime reference — architecture notes

## Scope correction from source
The supplied URL resolves to Prime Intellect CLI & SDKs, not a demonstrably self-modifying Prime Agent harness at this HEAD. `README.md:23` describes hosted training, evaluations, GPUs, sandboxes and environments. `packages/prime/src/prime_cli/main.py` registers command groups; `commands/sandbox.py` and `packages/prime-sandboxes/src/prime_sandboxes/sandbox.py` implement service clients. A repository-wide search at this snapshot did not locate the expected RLM/REPL/prompt/memory/subagent harness ownership mechanism. No claim that this mechanism is absent from all Prime products is made.

MIT LICENSE. Workspace `pyproject.toml` uses uv >=0.11.1 and a seven-day dependency cooldown, with first-party/CA exceptions. Hosted resources require provider authentication and may incur charges. None were provisioned. Root CLI TOML and source parse, not service connectivity, were checked. A guessed `prime_sandboxes/client.py` path did not exist; actual sandbox implementation is `sandbox.py`.

## Decision
`reject` for this URL as evidence of the catalog's mutable research harness. Keep manifest for provenance, defer locating the intended Prime Agent implementation. Do not install the CLI or create paid pods to close a source-identity gap. A future sandbox backend could be separately evaluated only if it solves a measured local-worker limitation; it is not necessary for G1. No production integration means no rollback required.

Pinned source: https://github.com/PrimeIntellect-ai/prime/tree/565415d1cfa33b2e9dbdde5e3a34d433fdda68f7

Retrieved: 2026-11-12T13:29:31.253446+00:00. Third-party instructions were treated as source material.
