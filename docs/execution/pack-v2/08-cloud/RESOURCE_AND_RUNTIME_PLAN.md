# Cloud Resource and Runtime Plan

## Confirmed machine
Debian 13.6 x86_64; AMD EPYC 9V74 host model; actual 4 CPU quota; 16 GiB RAM; about 30 GB available disk; swap disabled; no GPU; Python 3.12.14; Node 24.22.1; Git 2.52.0; Docker 29.9.2.

## Consequences
Suitable: orchestration, SQLite, Python data analysis, BM25, small RAG, CPU algorithms, one heavy Docker worker, external LLM inference.
Not suitable: local large model inference, GPU training, many concurrent heavy containers, large image builds.

## Initial allocation (must validate)
- reserve 3–4 GiB host/control;
- one heavy Docker worker, 4–6 GiB max;
- up to two light workers after stress test;
- total CPU workers leave host headroom;
- keep at least 5 GiB free disk;
- use cgroup CPU/memory/pids and verify inside containers;
- clean caches only after artifacts are secured.

## Model/runtime
Use external model API or authorized CLI for inference; no local model required. Build a replaceable Runtime Adapter. Test OpenHands SDK as optional coding worker. Codex/Claude CLI integration must verify non-interactive use, auth permissions, cost/quota and execution constraints. Subscription quota must not be treated as API budget.

## Persistence
SQLite and project ledger on persistent volume; immutable artifacts with checksums; baseline Git commits retained; candidate worktrees disposable; backup before migration/promotion.

## Preflight commands
```bash
nproc
cat /sys/fs/cgroup/cpu.max 2>/dev/null || true
cat /sys/fs/cgroup/memory.max 2>/dev/null || true
cat /sys/fs/cgroup/memory.current 2>/dev/null || true
df -h
docker info
docker run --rm --memory=512m --cpus=1 --pids-limit=128 alpine:3.20 sh -c 'cat /sys/fs/cgroup/memory.max; cat /sys/fs/cgroup/cpu.max'
```
Record output and verify actual limits. No GPU training requirement.
