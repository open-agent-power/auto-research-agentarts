# Agent Development OS

## 单一事实源
项目总纲、架构、ADR、任务板、Benchmark 规范、实验记录和发布记录都在项目目录中。聊天摘要不是事实源。

## 每个 Agent 开工前
读取根 AGENTS.md、项目宪章、相关架构、任务票据、依赖和当前 Git 状态。

## 每个任务必须有
明确目标、价值、输入快照、文件所有权、接口、依赖、验收、预算、风险、预期工件和文档更新。

## 并行模式
1. Read-only research：高并发拆分源码、论文、基准和许可研究；
2. Sectioned implementation：按模块和文件所有权并行；
3. Orchestrator-workers：开放任务动态分配；
4. Competition：多个独立假设/方案；
5. Evaluator-optimizer：按客观标准优化；
6. Independent review：不由实现者自己验收。

## 同步机制
任务完成 → 回执 → 独立审查 → 合并 → 更新架构/任务/实验文档 → 解锁下游任务。

## 每日集成回报
当前 Gate、完成任务及 commit、在途任务、阻塞、接口变更、测试结果、Benchmark 变化、成本、安全问题、下一批任务。
