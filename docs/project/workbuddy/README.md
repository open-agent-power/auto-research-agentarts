# WorkBuddy 项目交接

本次交接于 2026-11-18 建立。项目目标是在现有研究工作台里提出可检验的问题，用真实输入跑实验，再让可复核的结果决定下一步。WorkBuddy 第一件交付是把一个具体真实课题准备到可批准、可执行的状态。拿到该课题的执行授权后，交付能从原请求接续的运行证据、研究结论和独立复核。

| 阅读顺序 | 用途 |
| --- | --- |
| [执行计划](execution-plan.md) | 分工、阶段交付、晋级条件和预算边界 |
| [外部调研与选型](research-review.md) | 核对学术方法、候选来源和本仓库的证据缺口 |
| [首个真实检索课题草案](first-study.md) | 固定来源候选、语料范围、对照、指标、决策和审批内容 |

## 开始前核对

仓库是 `open-agent-power/auto-research-agentarts`。交接调研对照的代码基线是 `dd3195c1305989acb1cb20c00af50b5d4f53bd75`。WorkBuddy 开始时以远端 `main` 和其 [current](../current.md) 为入口，记录实际提交。读 [AGENTS.md](../../../AGENTS.md)、[执行索引](../../execution/README.md)、[AUTONOMY](../../execution/AUTONOMY.md)、[任务基线](../research-baseline-20261115.md) 和 [阶段门](../../execution/pack-v2/06-roadmap/PHASE_DELIVERABLES_AND_GATES.md)。项目导航可读 [research-dev-router](../../../.agent/skills/research-dev-router/SKILL.md)。Adaptive Agent Workflow 在当前 Codex 会话中使用过。WorkBuddy 侧的 Skill、Shell、GitHub 写权限、独审和私有工件位置须在实际环境核验。项目导航可以直接按文件阅读。

本轮确认原目录 `/workspace/auto-research-agentarts` 和原参考目录 `/workspace/references/upstream` 不可见。Codex 源码续作目录为 `/workspace/development-continuation-20261114/auto-research-agentarts`。原研究盘及原执行者状态为 `unknown`。WorkBuddy 若在另一环境，从 GitHub 取得干净源码，并记录自己的目录、origin、HEAD 和 lease。若只能访问文档，先做 M0 中的协议与来源核验，明确实际缺失能力。

S139 的五份未提交文件留在 Codex 源码续作工作树，快照位于其本地 `runs/s139-checkpoint-002/manifest.json`，SHA-256 为 `c426eaca2780363b4046fbc10ece9faab76969282cc3f894ddf00930c5c36c51`。独审提交 `a3726697454735457591e6270ba3bc920c53a21f`，合成测试因缺入口失败。GitHub 有审查和失败记录，本地五份 WIP 和 `runs/` 未随交接推送。直接推进下述检索路线。只有所选真实研究路径实际依赖该代码时，才立独立任务处理 S139。访问同一旧工作树时须先查 lease 与未提交文件，禁止 `reset`、`clean` 或搬动原件。[S139 审查](../../execution/SPRINT-139-review.md)

## 可直接发给 WorkBuddy

```text
接手 open-agent-power/auto-research-agentarts，先完成 GitHub main 的
docs/project/workbuddy/README.md 所指执行计划的 M0，然后依阶段门推进。
交付优先级是用真实输入完成一次可复核的研究决定，并用原请求身份接续。

领取当前目录自己的 lease。下载固定 GovInfo 版本核 SHA，按草案做来源审计、
输入适配、问题和标签预登记，核对原生入口和阶段预算。用一名负责人、
至多一名执行者和一名未参与实现的评审，复用已有成员。首轮只交 M0 的
工件、精确 diff、检查结果和独审。干净 GitHub 源码不包含 Codex 本地 S139 WIP。

如准备通过，按草案给出一次可决策的真实研究审批卡，并完成所有可独立做的
工程验证。只在新切片明确批准后实际排名、派发研究行动。保护旧预算、
源码 pin、原请求和失败记录。新课题不购买服务或调用付费 API，受限实验内
模型为零。报告 WorkBuddy 自身可见用量，未知就填 unknown。

经审查的代码、协议和公开脱敏小结推 main。原始数据、留出题、运行数据库、
恢复请求及凭据只放有权限的持久位置。中文汇报真实完成物、精确 SHA、
结果及失败、复核状态、预算消耗和下一决定。
```
