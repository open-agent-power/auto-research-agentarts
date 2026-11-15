# Meta Ax 转移条件参考审查（2026-11-15）

这是一项只读源码调研，目的是改进已有研究决策的可解释性，不代表已集成 Ax，也不证明自主研究收益。

## 固定来源

- 官方远端：<https://github.com/facebook/Ax.git>；实际检出提交 `fd8a67a524b063b2615815c638af2c94b034f476`，提交时间为 2026-11-13 18:20:29 -0800。
- 本地独立副本：`/workspace/reference-exploration-20261115/ax-public-20261115`。根目录 [LICENSE](https://github.com/facebook/Ax/blob/fd8a67a524b063b2615815c638af2c94b034f476/LICENSE) 为 MIT，SHA-256 `da6d3703ed11cbe42bd212c725957c98da23cbff1998c05fa4b3d976d1a58e93`；如以后复制代码或实质部分，须保留版权与许可声明。此处没有复制上游代码；依赖和数据各自的许可不因根许可而自动确定。

## 实际机制及限制

- [Client.complete_trial](https://github.com/facebook/Ax/blob/fd8a67a524b063b2615815c638af2c94b034f476/ax/api/client.py#L531) 允许完成时缺少优化指标，并将任务标记为 `COMPLETED`；[attach_data](https://github.com/facebook/Ax/blob/fd8a67a524b063b2615815c638af2c94b034f476/ax/api/client.py#L575) 也允许附加部分数据。执行状态完成本身不能证明所需科学反馈已知或条件成立。
- [试验计数](https://github.com/facebook/Ax/blob/fd8a67a524b063b2615815c638af2c94b034f476/ax/generation_strategy/transition_criterion.py#L89) 可按试验状态、所属节点及是否有数据筛选；此路径的“有数据”不要求所有指标齐备。[MinTrials](https://github.com/facebook/Ax/blob/fd8a67a524b063b2615815c638af2c94b034f476/ax/generation_strategy/transition_criterion.py#L603) 表示状态计数阈值，[MaxGenerationParallelism](https://github.com/facebook/Ax/blob/fd8a67a524b063b2615815c638af2c94b034f476/ax/generation_strategy/transition_criterion.py#L254) 则作为生成暂停条件。它们区分了推进条件与执行容量，但不能代替针对特定反馈字段的完整性认证。
- [GenerationNode.should_transition_to_next_node](https://github.com/facebook/Ax/blob/fd8a67a524b063b2615815c638af2c94b034f476/ax/generation_strategy/generation_node.py#L822) 对通往同一节点的条件取 AND，按顺序选择满足的转移边；未转移且 `raise_data_required_error=True` 时才检查暂停条件。这是该框架的调度语义，不能直接覆盖本项目的未知状态、额度或身份阻断。

Ax 主要解决预设参数空间及目标下的试验生成与优化；一次 trial 或优化指标不等同于科学假设、有效反证或因果结论。它的 [依赖声明](https://github.com/facebook/Ax/blob/fd8a67a524b063b2615815c638af2c94b034f476/pyproject.toml#L23) 包含 BoTorch 和 scikit-learn。未安装、运行或引入 Ax，也未调用模型、API 或研究实验；本审查不声称其全部持久化、恢复或安全属性。

## 与现有实现的关系

当前 [质量策略](../../src/autoresearch/project_controller.py#L51) 已绑定原登记、反馈、来源、代码身份和计划，并检查唯一匹配候选及预算；[v2 入口](../../src/autoresearch/project_controller.py#L708) 还在锁内校验当前计划和原反馈引用。已有非终态行动必须检查原请求，不能把 Ax 的 `COMPLETED`、失败或暂停简单映射为本项目的条件成立、反证或可重派。未知、缺失和数值零必须保持不同；代码漂移、额度不足及原请求未决仍按现有协议阻断或等待，不因建议的展示而放宽。

可考虑的最小下一步是先核对现有只读 context/界面是否已充分解释：反馈未知或字段不全、预算/未决请求阻塞、以及满足条件可选择候选三类原因，并关联原登记、反馈和计划身份。若确有缺口，仅在现有决策视图上补充解释，不另造调度器、账本或自动排名；执行时仍以现有锁内原件核验为准。若实施，合成验收应覆盖行动完成但必需指标缺失仍为 unknown、零值有效、预算不足及状态漂移不执行，并明确它只是工程能力，不是实际科研收益。
