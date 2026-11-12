# Master Execution Pack v2 · 云端执行

[原始计划](pack-v2/README.md) · [来源身份](pack-provenance.json) · [接续入口](../project/current.md)

本次研发以 `5d497c8ae22100953f66c3c5b54746ca87e09f01` 为代码基线。约15天是规划窗口，不是已完成时间或自动跳过 Gate 的依据。

| 阶段 | 状态 | 验收依据 |
|---|---|---|
| G0 仓库/环境/上游审计 | blocked | [验收记录](g0/G0-review.md)；资源隔离和上游runtime smoke未通过 |
| G1 真实研究闭环 | blocked_by_G0 | 至少两轮、观察导致计划变化、证据链、独立复现 |
| G2 动态协作 | blocked | 测量收益后选择组织；开发子代理不算产品收益 |
| G3 跨课题方法改进 | blocked | 独立任务重验及负迁移 |
| G4 隔离代码级 RSI | blocked | 受保护评价器、真实候选差异、晋级/拒绝 |
| G5 RAG/算法迁移 | blocked | 可复算两类任务及对照 |
| G6 发布交接 | blocked | 干净安装、回归、主研究案例独立复现 |

## 当前任务契约

所有任务输入均包含原始计划、基线 commit、仓库 AGENTS 和相关索引。工具/模型用量 unknown 不记零；本轮没有外部模型 API 采购。以下文件所有权互不重叠，生产实现暂不修改。

| 任务 | 负责人/文件所有权 | 验收/依赖 | 状态 |
|---|---|---|---|
| R01–R06 现有能力审计 | repo_audit；g0/repository-capability-audit.md、matrix.csv | 源码行号、实现/目标区分、G1缺口；只读生产代码 | verified |
| R07–R12 上游机制/许可 | upstream_audit；g0/upstream/、仓库外references/upstream | ≥3核心固定commit与源码审查、许可证、复用决定 | verified |
| R13/R15/R16 课题与评价 | research_task；g0/*research*、evaluation-protocol.md | 官方数据许可/字段/来源、基线、竞争解释、独立评价边界 | verified |
| R14 云端资源 | resource_audit；verify_cloud_resources.py、g0/cloud-resource-smoke-test.md | 真实限制及失败保存，不用请求参数代替实测 | verified |
| G0 集成/基线/交接 | root；project/、execution主入口及ADR/验收 | 所有审计覆盖、基线日志、资产缺口与Gate结论 | verified |
| G0 独立评审 | independent_review；g0/independent-review.md | 不由实施者自己验收；报告实质漏项 | verified |

本轮每项调研约10分钟起始预算，本地重型Worker并发至多1。失败分支：保留证据、修复具体缺口、仅重验相关项；资源门不通过不解锁G1实现。

## 交付与下一步

[G0验收](g0/G0-review.md) · [ADR决定](g0/G0-ADR.md) · [独立审查](g0/independent-review.md) · [基线验证](g0/baseline-verification.md) · [资产交接](g0/local-assets-handoff.md)

`verified`表示对应审计/探针交付已核验，**不表示被审计产品能力、资源环境或整个Gate通过**。R14交付的结果就是资源门失败。输入准备和任务规范也不等于G1已执行。上游运行smoke保留独立blocked任务。

最终完整工程回归：1111项，1092通过、19跳过，exit0；详见[机器回执](g0/verification-results.json)。G0仍因资源和上游runtime条件阻塞。

GitHub交付：本地提交就绪；Git、gh REST和GitHub连接器写入均403（集成缺写入授权），**未成功推送或创建PR**。需要修复此仓库的Contents写入授权后重试；不影响本地Git bundle和证据包交付。
