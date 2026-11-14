# S052：让一次明确续作遵循事前反馈条件

S051 已能根据独立 staged 验证反馈选择 saved-audit 或等待，但 S047 的固定阶段续作并不检查它。本轮在原 `LocalWorkbench.continue_staged` 增加明确 opt-in：原五字段再加 `registration_request_id`，保存 v2 条件模式；原五字段 v1 行为不变。

新模式先持久保存原登记/SHA、封存 context、真实反馈与 policy proposal。unknown 或选择 wait 时保存 terminal waiting 回执，不创建阶段行动、freeze、final 或报告，也不永久锁住后续路线。只有同一条件确实选中原 primary 对应的 audit，并核验它的原 parent/child、SQLite 指纹和工件后，才沿既有 freeze→final→report。audit 后恢复使用原封存决定，不用已变化的候选重新选择。本版 v2 初次接受前已有 audit/freeze/final 会明确拒绝；v1 原复用行为保留。

## 实际完成与验证

新增独立错绑定 probe 发现并修复一处真实缺口：初版已知 wait 分支未核 body primary ID，可保存引用另一行动的等待回执（未派发工具或越过等待）。现在所有已知反馈在接受前核原 action ID，不符 `EVIDENCE_CHANGED`，不保存错误回执。unknown 无原 action 时仍保持等待。初版全部191源快照、原 manifest 和 HTTP 工件保存在 `runs/s052-verification/initial-source/` 等原目录；最终修复版证据另存，未覆盖失败。

- 191 产品源码冻结 manifest SHA `f8ee42fe9a56d045207d4cdff5b2dcadcbe85c8550dff0207c4547f05d0b26a0`，Project core `300421cc466b459f3b86e74fd6ebecf800dc67f10fb9d7e160f9ad46a839f1e1`；只改原 manager/helper 和专项测试。
- 作者修复后45相关/root最终54相关通过；独立9项通过，包含 terminal wait 可另选路线及状态变化后原回执、原 audit 落账后外层进度中断同 ID 接续且不重审、v2 拒已有 audit/v1 继续可复用、重封篡改原 proposal 拒绝、unknown final 原请求/新 ID 均不重派。191源及3改动文件前后相同。
- 两个新合成项目走实际 HTTP：`0 > 0` 对应 not-met→原 audit→freeze→final→report，共3工具；`0 >= 0` 对应 met→wait，仅原 primary 共1工具。不同 Python 进程和新 server 以原 exact body/ID 重放，完整响应、Project 状态/预算/公开文件哈希相同，重建索引/排名/评分抛错哨兵未触发。
- private 原字节不参与这次 HTTP 文件清单。独立 probe 在 feedback/audit 阶段禁止 private I/O；真正获条件授权的 final 及其后原 report verify 允许读取原合成 holdout。报告 input 无合成 final 原文/ID；不声称整个流程无 private I/O 或盲测。
- S046 的36和 S050 的17个受保护文件再次逐字节核同；旧研究、预算和 source pin 未改，S050 未执行。

## 失败、方法和限制

独审前两次的真实未通过记录保留：一次钩错初次准备写入点，没有触发预计中断；一次把产品更早抛出的 `EVIDENCE_CHANGED` 错断言成必须返回 incomplete。修正探针后通过，无产品源码修改，不掩盖原日志。当前实现不是任意自主计划器、科学假设生成或研究收益证明；既有 trusted-local/非 OS 隔离和旧盘缺失边界保持。

复用同一 root、engineering、capability_review 团队及 AAW v0.3.1 显式 owner loop、项目 router、已有 Project/Controller/SQLite 意图和 S049 report 预封，不新增 ledger 或费用范围。新研究行动/模型/fit 均0；最终修复版新合成 HTTP 实际4次工具，初版已完成合成 HTTP 另4次工具保留、未冒充最终版，均另计，所有回归总 dispatch 未单独计量，开发 token/费用 unknown。

使用见[条件模式](../staged-evaluation-continuation.md#显式条件模式s052)。最终修复版实际 HTTP 及原body位于 `runs/s052-verification/http-fixed/`，最终回归日志 `root-regression-fixed.log`，独审 `independent-run-fixed.log`。原始命令/输入/ID/状态/预算/回执及失败日志位于 ignored `runs/s052-verification/`、`runs/s052-review/`；[精确共享索引](g5-local/conditional-staged-verification.json)保存源码提交、输入/行动ID、预算、恢复与原失败身份。源码身份改变，S051 及更早 pending 必须使用原 pin；不得用新代码升级旧项目。
