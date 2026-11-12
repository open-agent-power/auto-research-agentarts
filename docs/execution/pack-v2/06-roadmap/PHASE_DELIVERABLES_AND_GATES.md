# Phase Deliverables and Acceptance Gates

时间是规划窗口，不是自动推进条件。每阶段的交付物、验收证据和失败处理必须完成。独立工作可并行。

## G0 — Repository / Environment / Upstream Audit
### 工作
- 审计现有仓库代码与文档；
- 核验本机 ignored runs、计划、数据和研究资产的交接需求；
- 固定上游项目 commit、许可证、依赖和安全；
- 实测 Debian/Docker 资源限制；
- 选定真实表格研究候选数据和资料；
- 定义基线流程和评价方式。
### 交付物
- repository-capability-audit.md；
- implemented-vs-planned-matrix.csv；
- local-assets-handoff.md；
- upstream-manifest.json；
- 每个上游 architecture-notes.md；
- license-security-audit.md；
- cloud-resource-smoke-test.md；
- initial-research-task-spec.md；
- G0-ADR.md；
- G0-review.md。
### 验收
- 所有核心能力有代码位置和证据状态；
- 至少三个核心上游固定版本并完成源码阅读；
- 许可证和运行风险明确；
- Docker CPU/RAM/PID/磁盘限制实测；
- 第一项研究问题、数据来源和评价边界明确。
### 未通过
不大规模重构；补齐审计、资产和数据语义问题。只读调研继续。

## G1 — One Complete Research Vertical Slice
### 工作
- 创建真实研究项目；
- 登记真实表格和相关资料；
- 澄清问题/范围；
- 生成计划和假设；
- Recipe 条件匹配；
- 实际执行方法；
- 分析证据；
- 根据反馈修订计划；
- 执行下一步或明确等待；
- 导出报告和复现包。
### 交付物
- 可运行研究项目；
- plan v1/v2 和变更差异；
- Recipe/method selection record；
- 原始输入与数据哈希；
- Action/Observation/Evidence；
- 实验脚本、日志、图表；
- 研究报告；
- reproduction bundle；
- handover test。
### 验收
至少两轮研究推进；至少一次真实观察导致计划有依据变化；关键结论可定位；失败路线和限制完整；另一成员按文档重开接续。
### 未通过
优先修复研究状态、方法条件和证据链，不扩 Agent 数量。

## G2 — Dynamic Agent Collaboration
### 工作
- 结构化 Agent Contract；
- 任务 DAG；
- 动态 sectioning/competition/review；
- 只在有价值时并发；
- 结果回到同一项目状态。
### 交付物
- Agent/Task schema；
- orchestration trace；
- 并发冲突和恢复测试；
- 单 Agent vs 固定多 Agent vs 动态多 Agent 对照。
### 验收
动态协作在研究质量、覆盖、效率或成本至少一项有可测收益，且没有严重证据/状态退化。无收益则简化为单 Agent 或静态流程。
### 未通过
减少 Agent 角色，重新设计任务分解和上下文传递。

## G3 — Cross-project Method / Memory Improvement
### 工作
- 从多个真实课题抽取经验候选；
- 记录适用条件、来源和失败范围；
- 在独立任务集重新验证；
- 对比原 Recipe/策略与候选。
### 交付物
- experience candidate records；
- transfer benchmark；
- baseline/candidate report；
- negative transfer analysis。
### 验收
至少一个方法/策略候选在独立任务上显示收益，或形成有价值的负结果；不得把检索相似度当有效迁移。
### 未通过
保留为 candidate/unverified，不晋级为默认经验。

## G4 — RSI Candidate Self-modification
### 工作
- 冻结 baseline commit、配置、模型和 evaluator；
- Agent 分析真实失败轨迹；
- 创建独立 worktree；
- 修改完整候选代码/Prompt/Policy/Harness；
- 沙箱测试；
- sealed evaluation；
- promotion/reject；
- 新版本恢复和下一代准备。
### 交付物
- baseline manifest；
- candidate diff；
- modification hypothesis；
- tests/security report；
- evaluation raw results；
- promotion/rejection receipt；
- lineage graph。
### 验收
完成真实代码级候选修改、独立评价、晋级或拒绝；候选无法修改 evaluator/hidden tests/budget/security/promotion。多代收益另行证明。
### 未通过
保留 baseline，候选归档，分析评价器或改进假设问题。

## G5 — RAG / Algorithm Transfer Validation
### 工作
- RAG 固定语料与 query set；
- CPU 算法任务；
- baseline/candidate；
- memory transfer；
- 跨任务测试。
### 交付物
- RAG experiment pack；
- algorithm experiment pack；
- metrics/raw results；
- cross-task report。
### 验收
同一研究工作台可运行两类不同研究任务；方法语义不被硬编码成单一领域；结果可复算。
### 未通过
缩小领域范围，先补核心抽象。

## G6 — Release and Handover
### 交付物
源码/tag、安装文档、配置样例、数据/许可证清单、研究任务包、Benchmark、原始实验结果、RSI lineage、技术报告、复现附件、演示视频、已知限制。
### 验收
干净环境安装；完成 smoke/regression；另一成员独立复现主研究案例；所有主张有证据和边界。
