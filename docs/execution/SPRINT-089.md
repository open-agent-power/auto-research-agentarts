# S089：未知 Controller 父请求阻断新行动

对照 [Ax 参考机制](../project/ax-transition-review-20261115.md) 时发现：原 child 按原 ID 从延迟结果恢复 completed，但原 Controller parent 仍为 unknown，旧 preview 只看 prepared/running parent，可能显示下一候选；旧新ID入口也可能接受一个新 parent。这是合成 Project 实际复现，不假设真实旧研究发生该问题。修复前原始证据 `runs/s088-unknown-parent/pre-fix.json` SHA `6c9ecf595b68e157c56f50fbcc4184ebff2294b1e05a481bbd87d920d7c2120f`：原 parent unknown、child completed、无未决 child、blockers 空、关联候选1、新 parent prepared；第二次 dispatch 在工具前被测试哨兵拦截，原预算1/2保持，0模型/fit/native evidence。

修复使 preview/context 对 unknown parent 报阻断和 needs_review；writer 锁内拒绝新 ID，原 parent 的原 ID/body仍走原恢复路径。此处拒绝产生新等待 parent 是有意的安全行为变化，避免修改账本而妨碍原操作；旧生产 Project 保持原源码 pin，不隐式升级。

真实可达的隔离合成链及质量 v1/v2、recipe由独审先验36/36，调整相关旧断言后四模块独审13/13；作者完整相关回归最终75/75。原 recipe/controller/selection 三处断言原允许新 wait 或预期较晚的 SELECTION_BLOCKED，新合同统一更早报 EXECUTION_UNKNOWN；仅更新相关断言并核数据库原字节、预算和原ID。完整原回归 75 项的 1 failure/1 error 日志保留在 `runs/s088-unknown-parent/regression-75-pre-update.log`，SHA `9b32f99796ae72962bfff7fea203b2884d468fd40f374e0e9cd5f484a52563bc`；修复后日志 SHA `f8855b0023f60e3e7f4e6d9ae591c6e0cad59f1f837eb26b4941b74236bd889c`。

均是隔离工程验证，部分有本地合成工具与文件I/O；本轮无新真实科研行动、模型或fit，费用/token unknown。未证明断电、OS隔离或完整自主科研收益；原 Bike pin/预算与历史账本保留。
