# Two-level Improvement and RSI

## Layer 1: 课题内自适应
真实观察进入后，比较当前假设和计划；分析支持、反驳或无法区分的解释；检查方法是否仍适用；选择继续、细化、改道、补证据、等待或停止；保存新计划版本和理由。

## Layer 2: 跨课题方法改进
从多个真实课题抽取失败模式和有效经验；保存来源和适用条件；形成 Recipe/方法/策略/Harness 改进假设；在独立任务集上比较质量、成本、稳健性和迁移；晋级、拒绝或待验证。

## RSI
第一阶段允许候选完整修改研究系统代码、Prompt、Recipe selector、Planner、Agent definitions、Memory policy 和 Harness。候选在独立 Git worktree/branch + Docker 中执行。

保护对象：评价器、隐藏测试、数据真值、预算账本、安全权限、晋级控制器、生产基线和密钥。候选不得修改这些对象。

状态：
`baseline_frozen → baseline_evaluated → diagnosis_ready → candidate_created → candidate_tested → sealed_evaluation → promoted/rejected → next_generation_ready`

暂停：
`budget_exhausted / needs_review / evaluation_integrity_error / worker_unknown / no_improvement_streak`

一次自我修改只证明完成一次自修改实验。持续 RSI 需要多代、留出任务和可重复收益。
