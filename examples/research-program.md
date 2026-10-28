# 外部研究 Agent 程序：证据驱动实验

这是提案与执行的协作契约，供当前任务已授权的研究 Agent 使用。本文件不启动后台服务，也不授予云调用或无限运行权限。

## 建立研究

通过操作者配置的 CLI `tool --workspace ...` 或 SDK HTTP `/invocations` 发送 JSON。HTTP 需要稳定会话标识，入站鉴权另行验证。

```json
{
  "schema_version": "0.1",
  "request_id": "create-material-study",
  "action": "create_campaign",
  "goal": "研究成分交互和正则化对钢材屈服强度预测的影响",
  "max_trials": 5,
  "dataset_id": "matbench-steels-v1",
  "policy_kind": "external_agent_proposal_v1"
}
```

另可选 `engineering-polynomial-v1`；省略策略时保留原固定工程演示，只支持工程数据。两种策略在状态和报告中分别标明。

## 观察与提案

1. `observe_campaign`：提供研究ID，取得冻结的数据与评价描述、预算、最佳候选、历史试验和 `observation_sha256`。终测指标不在观察中。
2. 阅读训练／验证误差、已有提案和失败结果，提出一个假设及受约束配方。基准尚不存在时先建立基准；之后必须引用最新完成试验，可同时引用其他已完成试验。
3. 用 `submit_proposal` 提交。下例指纹和ID是占位符，必须替换成真实观察；不要预写完整候选列表再声称是反馈决策。

```json
{
  "schema_version": "0.1",
  "request_id": "trial-unique-id",
  "action": "submit_proposal",
  "campaign_id": "<campaign_id>",
  "proposal": {
    "observation_sha256": "<current observation_sha256>",
    "hypothesis": "根据已观察结果，说明本次想检验的变化",
    "expected_effect": "说明预期改善或反证以及失败后怎样处理",
    "candidate": {"degree": 2, "alpha": 100.0},
    "evidence_trial_ids": ["<latest completed trial_id>"]
  }
}
```

配方目前仅允许 `degree=1..3`、有限 `alpha=0..1000000`。这是受约束的模型结构／训练配置实验；任意Python、评价器、标签、路径、命令和分数不进入提案。

## 决定、重试与恢复

- 控制器在同一写锁中校验观察、证据和预算，再预留并训练候选。已有最佳模型时，验证MSE必须降低超过1%才采用；不修改门槛迎合结果。
- 同一提案重试使用相同业务 `request_id` 与完整内容；状态前进后也只返回原试验。改内容用新ID，未知在途任务先查状态。
- `STALE_OBSERVATION`：重读并重新考虑；`INVALID_EVIDENCE`：修正引用；`BUSY`：核对在途工作；`BUDGET_EXHAUSTED`：停止训练并总结。
- 用 `pause_campaign/resume_campaign` 暂停恢复。聊天摘要不是任务状态事实源。
- 阶段结束后调用一次 `finalize_campaign` 做独立终测，之后锁定优化。结果不作为同一研究后续选参反馈。

## 证据与声明

`research_report` 返回结构化证据和Markdown；操作者也可用 `autoresearch report` 导出文件。报告核对模型哈希，记录提案、代码／配方、指标、决定与终测。

R3提案由开发Agent逐轮提供；R4新增的产品决策控制器可从HTTP模型接口接收提案并执行此契约，参见[自主研究接入说明](autonomous-research.md)。R4实际只用明确标注的脚本端点验证流程，真实LLM接入仍pending。来源字段不构成模型身份认证；公开材料结果为`benchmark_only`，不证明科学发现或策略优于搜索基线。论文式PDF和真实领域验证另行验收。
