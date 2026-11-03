# Agent 开发导航

本目录把开发任务引到对应设计、代码和复用材料。先读与任务最直接的索引，跨组件、接口或评测时按需增加，再进入正式文档；不需要每次加载整个资料库。

## 先确认当前方向

- [产品计划](../docs/plan.md)：稳定目标、实施阶段和价值验证。
- [底层架构](../docs/architecture/foundation.md)与[状态/能力契约](../docs/architecture/research-contracts.md)：A0–A3 基线已定；[A4 本地项目](../docs/project-slice.md)已实现单个 OOF 工具、固定反馈策略和恢复，目标端口尚未全部接线。
- [自适应研究设计](../docs/research/adaptive-research.md)：本轮讨论的六项决策、运行方式与待验证假设。
- [当前实现与证据](../docs/current-progress.md)：实际完成什么、缺什么；当前工作台不是通用研究执行入口。
- [正式文档入口](../docs/README.md)：阅读和维护设计。

## 按任务找入口

| 任务 | 读取索引 | 开工时确认 |
|---|---|---|
| 前端审美、版式、文案 | [审美与交互](indexes/aesthetics.md) | 五页分工、悬浮玻璃、实色正文、图文卡片与 X6 画布 |
| 页面、卡片、抽屉、图表、画布组件 | [组件搭建](indexes/components.md) | 当前 P02 与历史视图的代码归属、共享令牌和已有组件 |
| 项目状态、控制器、工具、恢复 | [后端](indexes/backend.md) | 先核对底层架构；现有能力与待建接口分开，不为每个案例再写控制器 |
| HTTP、CLI、模型请求、前后端数据 | [接口](indexes/interfaces.md) | 当前读写边界、数据来源与调用方 |
| RAG、数据来源、外部知识接入、记忆 | [知识与数据](indexes/knowledge.md) | 本地原文、外部来源、方法经验各怎样参与决策 |
| 自适应收益、研究推进、用户价值 | [评测](indexes/evaluation.md) | 实际任务和外部证据，避免用格式通过替代效果 |
| 找可复用代码、论文、平台资料 | [参考资料](indexes/references.md) | 固定版本、许可、已验证范围与适配成本 |
| 操作华为云中国站 | [平台 Skill](skills/agentarts-china-builder/SKILL.md) | 是否已有该操作授权、登录形态、费用边界 |

## Skill 怎样提醒

项目开发使用 [research-dev-router](skills/research-dev-router/SKILL.md)。它根据任务提醒读取上表的对应入口，指出应复用的代码和需要同步的正式文档；不另设一套审批或全量测试流程。

`AGENTS.md` 显式指向这个 Skill。`.agent/skills/` 是本项目约定，不能据此假定所有宿主都会自动扫描；队友使用的工具若不读取 AGENTS，可直接加载上述 SKILL.md。提醒属于 Agent 遵循的工作约定，本轮没有安装宿主 hook。

开发 Skill 指导**开发者 Agent**；产品内的科研配方指导**研究运行**，两者不混用。读取 Skill 不会启动模型、执行实验或授权云资源。

## 目录归属与维护

```text
.agent/README.md          开发导航
.agent/indexes/           任务到正式设计、代码和资料的索引
.agent/skills/            项目可共享的开发及平台操作 Skill
docs/                    产品计划、正式架构、设计和实现说明
src/ + frontend/         真实实现
../../references/        工作区外部资料，不随产品克隆分发
runs/                    本机执行证据，不提交
.agent/focus.json 等      本机检查点与选择状态，不提交
```

索引只保留定位与提醒；正式规则在 docs 或 DESIGN，运行事实在原账本。新增模块或改变接口时同步相关索引；历史证据文档保留原范围，不批量改写为新能力。旧计划归档与轮次导航已清理，讨论决策以产品计划的六项落点为准。
