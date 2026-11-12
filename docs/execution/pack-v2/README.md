# Autonomous Research Lab — Master Execution Pack v2.0

**基准日期：** 2026-11-12  
**研发窗口：** 约 15 天，动态里程碑制  
**主仓库：** https://github.com/open-agent-power/auto-research-agentarts  
**定位：** 面向真实研究问题的持续自主研究工作台

## 这是什么

本目录是供云端 Codex 主控和多个子代理执行的完整项目任务包。它不只是产品方案，而包含：
- 产品宪章和范围边界；
- 研究生命周期、Recipe、Evidence、Memory 和双层改进模型；
- 上游开源项目参考目录、源码研究清单、固定版本和许可证要求；
- 目标架构与现有仓库审计要求；
- 动态 Agent 团队组织和 Agent Development OS；
- 主研究任务、RAG/算法研究、软件研发/运维扩展 Benchmark；
- 阶段路线、任务依赖、阶段交付物、验收标准和失败处理；
- 统一任务契约、回执、评审、Sprint 复盘模板；
- Debian 云端资源方案、部署和发布验收。

## 产品定位不可偏离

我们做的是**持续自主研究工作台**，不是通用 Agent 平台或多 Agent 演示。

核心研究循环：

`研究问题 → 研究计划 → 方法选择 → 实际执行 → 证据分析 → 修订计划 → 下一轮研究`

两层改进：
1. **课题内自适应研究**：根据本课题新证据调整假设、方法和计划。
2. **跨课题方法改进 / RSI**：根据多个真实课题的反馈改进方法、Recipe、策略和 Harness，并用独立任务集验证。

近期主场景：研究者带着真实表格数据和相关资料，完成一项可检验的探索性研究。

长期领域：材料、生物医学、软件工程和实际问题相关的交叉研究。

软件研发和 IT 运维是重要的 Agent 闭环扩展评测场景，不取代研究工作台本身的产品定位。

## 先读这些文件

1. `00-charter/PRODUCT_CHARTER.md`
2. `01-product/RESEARCH_LIFECYCLE.md`
3. `02-architecture/REFERENCE_ARCHITECTURE.md`
4. `03-reference-projects/REFERENCE_CATALOG.md`
5. `04-benchmarks/BENCHMARK_MASTER_PLAN.md`
6. `05-agent-organization/AGENT_ORGANIZATION.md`
7. `06-roadmap/PHASE_DELIVERABLES_AND_GATES.md`
8. `07-task-management/INITIAL_TASK_BACKLOG.md`
9. `08-cloud/RESOURCE_AND_RUNTIME_PLAN.md`
10. `09-delivery/FINAL_DELIVERY_MANIFEST.md`

## 使用方式

- 主控先执行 G0 审计，不得直接大规模重写。
- 只读调研、参考源码分析、Benchmark 任务设计可以立即并行。
- 写代码任务必须等待接口契约和文件所有权明确。
- 每个阶段通过 Gate 后才推进依赖阶段；独立工作流可提前并行。
- 每个 Sprint 必须先研究、再实施、再评测、再复盘和重新决策。
- 任何能力声明必须附源码、命令、真实运行结果和工件。
- fixture、mock、模拟数据不得冒充真实研究或真实模型运行。

## 重要

本任务包包含上游项目的准确入口和源码研究任务，但不把多个上游完整仓库直接复制进本 ZIP。Codex 必须按 `03-reference-projects/CLONE_AND_AUDIT_GUIDE.md` 固定 commit 拉取到独立 `references/` 目录，检查许可证后研究。这样避免把第三方代码、依赖和许可证混入主项目。
