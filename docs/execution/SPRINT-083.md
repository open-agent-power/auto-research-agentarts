# S083：原生 Controller 的表格质量反馈策略

新增显式 `ProjectController.advance_tabular_quality_feedback`：在原 writer 锁内核验事前登记、原质量行动及结果、当前计划和 source/code；条件通过时从现有 sealed context 精确选择绑定该质量 action/result SHA 的唯一数值关联候选，并核原预算/成本；未知、不通过或候选不可用可保存等待，身份漂移或状态冲突可直接拒绝。仅首次接受的原请求在释放锁后进入既有 dispatcher；同 ID 的 prepared/running/unknown 在锁内停止，终态仅核原请求/证据后回放或保留原拒绝。旧低层 Controller 若遇新策略 parent 拒绝绕过保护；其他旧请求行为不变。该策略不自动约束所有直接 step/selection。

作者和独审分别运行最终冻结版新策略17/17合成通过，覆盖 met/not_met/unknown、预算不足、缺或重复候选、来源漂移、计划变化后的原 wait 重放、parent-only/child running/unknown/child完成但parent未终态、旧入口交叉、原报告读取及两个实际进程同 ID 竞争，仅首次派发。作者旧合同回归62/62、主代理选择回归7/7、独审旧入口回归11/11通过；均为隔离工程，部分调用本地合成工具。独审发现终态关联 child 请求身份未独立重算、质量前驱 SQL 漂移未复核、计划变化后原 wait 重放不一致、child 创建前原拒绝无法重放及 orphan replay 被 inner join 隐藏，作者修复并补相应用例；报告测试曾误用字段 `items` 导致 KeyError，按真实 `records` 修正后通过。测试不证明 OS 隔离、断电恢复或真实研究收益。

唯一 Bike 原项目/manager SQLite SHA 保持 `26aa23c73e6f50025c7cd0bf4d58196a8f12050c7b65496bc098903911204080`、`0413c121e3e63115fa4140b87c1c24061fadca70f4acd9e0dd73e5271db6d49c`，原 pin clean、2/2额度不重开。本轮无新真实科研行动、模型或 fit，开发费用/token unknown。Worker 隔离、完整 RSI 和外部研究收益未证明。

当前可通过 Python 显式入口使用策略；Workbench/UI 等后续接入需要另行验证。质量 profile 只提供机械事实，不代替来源许可、分组语义或科学判断。后续计划修订的结构化行动引用仍未实现；当前新派发要求登记时计划保持一致，已有原 wait 则可按冻结身份重放。
