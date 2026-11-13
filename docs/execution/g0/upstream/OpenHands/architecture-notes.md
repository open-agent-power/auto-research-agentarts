# OpenHands root repository — architecture notes

At this HEAD the formerly All-Hands-AI URL is Agent Canvas (`package.json` name `@openhands/agent-canvas`, v1.39.0), a Node >=24 UI/desktop application. README lines 199-223 direct the canonical execution API to **OpenHands/software-agent-sdk**. This materially differs from assuming the root repository is the Python worker runtime.

`README.md:65,172` explicitly warns the local agent server has full host filesystem access; Docker and multi-sandbox examples occur at lines 81 and 152. They are options, not proof that resource/network constraints match our worker policy. `package.json` pins the SDK TypeScript client 1.62.0, includes UI, Vite/Electron dependencies and install/build hooks. Installing the Canvas stack is unnecessary for our existing workbench.

MIT LICENSE was read. JSON manifest parse passed; no npm install/build/browser or server run. `inspiration_only` for UI-to-agent-server separation, and defer Canvas dependency. The worker feasibility decision is in the separately pinned `software-agent-sdk` notes. No product UI copied or replaced; no rollback needed.

Pinned source: https://github.com/All-Hands-AI/OpenHands/tree/d58ca3dcdf95c5847f1888de6d5e0600b53b718c

Retrieved: 2026-11-12T13:29:31.253446+00:00. Third-party instructions were treated as source material.
