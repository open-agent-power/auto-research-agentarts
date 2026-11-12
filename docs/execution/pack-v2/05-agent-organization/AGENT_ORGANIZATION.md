# Dynamic Agent Organization

## 原则
Agent 团队是完成研究工作的临时组织，不是产品本身。根据研究任务动态选择角色和并发规模。

## 逻辑角色
- Research Director：维护问题、路线、优先级和整体决策；
- Literature/Source Agent：资料检索和证据定位；
- Data Analyst：数据语义、质量和分析；
- Hypothesis Agent：假设和竞争解释；
- Method/Recipe Agent：方法条件与评价匹配；
- Experiment Designer：实验设计；
- Coding/Execution Agent：实现和运行；
- Evidence Analyst：结果、稳健性和局限；
- Critic/Reviewer：反证与独立审查；
- Meta Research Agent：跨课题方法改进。

不是每次全部启动。可用 Sectioning、Orchestrator-Workers、Competition、Evaluator-Optimizer、Review、Sequential。

## 并发策略
- 只读调研可高并发；
- 代码修改按文件所有权隔离；
- 重型本地 Worker 初始最多 1 个；
- 轻量 Worker 经压测后最多 2 个；
- 模型侧并发与本地执行并发分开管理；
- review backlog、合并冲突、API 限速、预算和上下文质量决定并发上限。

## Agent Contract
输入：研究问题、任务范围、项目快照、证据、方法、允许工具、权限、预算、超时、输出 Schema。
输出：task_id、role、status、proposal、evidence_refs、tool_requests、artifact_refs、metrics、uncertainty、limitations、cost_usage、next_actions。
Agent 不能自行声明行动执行成功；Worker 回执决定执行状态，评价器决定是否满足验收。

## 研发团队模式
主控/架构集成者 + 多个工作流负责人 + 专项子代理 + 独立 QA/Red Team。
子代理数量动态决定，不以同时开多少会话作为绩效。
