# S095：工作台计划同 ID 冲突优先级

S094 扩大回归发现干净 HEAD 上的既存失败：`LocalWorkbench.save_plan` 先检查其他未决 manager intent，才核同 ID 请求摘要，因此已完成原ID遇到不同body时可能先报 `OPERATION_INCOMPLETE`，掩盖 `IDEMPOTENCY_CONFLICT`。干净 `git archive` 源码上独立复现的原日志 SHA `1720419730f29410db4d93240d9dd3ef6a3781d1255e552113376408c1a87a2a` 保留在 `runs/s094-host-quality/`；这是旧缺陷，不计作 S094 通过。

仅在活动项目校验后将 `_old` 摘要冲突检查移至 `_no_pending_batch` 之前：同ID异body先报冲突；同body和新ID仍无条件经过原pending门，inactive项目仍先拒绝。既有stale intent不自动删除、重试或认领。将旧测试中先前stale intent已存在与独立Project unknown场景拆开，分别核实际合同，不用改断言掩盖原失败。

作者23/23、独审20/20合成回归通过，涵盖旧格式/经验引用、跨项目、同异body、未决门、原ID恢复及HTTP；原失败日志另保留。无真实研究/模型/fit或旧项目预算重置；该行为变化不隐式升级旧pin，不证明OS隔离、断电恢复或科学收益。开发费用/token unknown。
