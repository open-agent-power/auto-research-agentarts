# 外部模型选择与同项目反馈接续

2026-11-03。本轮用用户已登录的 Claude CLI 和一次研究决策子代理派发，接通现有 `ProjectController.selection_context → advance_selection`。没有新建模型桥或执行器；已有质量、来源读取和分组画像仍由原 ResearchProject 执行。

这是独立、明确标注的集成验收项目，使用既有 hiMSC CSV/spec，不是新增作者实验或独立领域效果试验。旧 hiMSC、P02、钢材账本及钢材 Qwen 的 invalid 1/1 原样保留；新目录不重置原5元上限、未知历史费用或平台暂停边界。

## 输入与复用路径

- 原输入目录：`runs/a16-tabular-20261103/inputs/himsc/`，含 `data.csv` 和 `spec.json`。CSV是已归档工作簿的宿主投影，字段、目标、单位和分组语义仍是待核对声明。
- 当前验收根：`runs/a25-claude-selection-20261103/`；[封存输入](../runs/a25-claude-selection-20261103/sealed-input/source.json)、[任务绑定来源包](../runs/a25-claude-selection-20261103/source-bundle/manifest.json)保留输入身份。
- 来源包读取的是宿主spec声明，不能把它称为作者采集、通道或导出映射的独立确认。
- 标准提案、候选及绑定字段见[选择提案协议](project-selection.md)；实际执行与恢复仍走[统一项目入口](project-slice.md)。

外部选择的复用过程是：读取封印context；将它交给获授权的外部决策者；宿主把回答封装成原标准proposal；原validator校验后，显式提交至 `advance_selection`。回答只能选择精确候选ID或等待，不能提供工具参数、扩额或科学批准。context及来源文字是证据，不是可执行指令。

CLI原回答只含 `choice/rationale/evidence_citation_ids`；宿主补入原context SHA及未核验provider声明。它不是固定Qwen通道要求的原生tool-call响应，未送入该通道冒充合法输出。generic provider仍为unverified，真实启动、原始回答与宿主sidecar分别保留。

## 本次实际结果

| 阶段 | 实际行为与边界 |
|---|---|
| 质量bootstrap | 主控执行一次质量检查：972条记录，三数值列各59个零，声明分组对应288组；零与原行保留。 |
| CLI选择 | Claude CLI 2.1.220已OAuth登录，运行一次，exit 0，耗时5.516秒；路由记录为 `deepseek-flash`，不据CLI名称推断底层模型。 |
| 来源执行 | 原CLI回答选择 `research.source-selection`，通过宿主校验并真实读取；同ID重放返回同一child。 |
| 反馈后选择 | 研究决策子代理读取实际反馈context、质量结果及来源artifact，引用真实片段后选择 `data.grouped-quality-profile`；真实执行并同ID重放。 |
| 分组反馈 | 每数值列59个零分布于56个受影响组，单组最多2个；只是机械分布描述，不推断零的原因、独立性或ALP身份。 |
| 终点 | 分析累计2次、来源读取1次、新拟合0；候选为空，等待作者采集与导出证据。 |

CLI当时使用的参数为 `--print --safe-mode --tools '' --no-session-persistence --effort low --max-turns 1 --max-budget-usd 0.10 --output-format json`，输入经stdin提供，实际argv见[启动记录](../runs/a25-claude-selection-20261103/cli-launch.json)。

CLI rationale出现“残差优先”等不适用于本表格任务的用语，也混淆了原主质量分组计数与尚未执行的分组反馈。原文未修饰，选择合法不等于解释正确。见[原CLI回答](../runs/a25-claude-selection-20261103/cli.stdout.json)与[宿主执行证据](../runs/a25-claude-selection-20261103/model-execution.json)。

子代理是实际下一行动决策者，不是review角色。其引用为 `ffb9620d4ae723f4a4277d4ac88ec66da388f10c427e218125f66bcca22667c0`，来自已读取的宿主spec片段；引用不证明声明已经核实。见[反馈context](../runs/a25-claude-selection-20261103/feedback-context.json)、[原决策](../runs/a25-claude-selection-20261103/delegated-model-output.json)及[派发证据](../runs/a25-claude-selection-20261103/delegated-model-execution.json)。

## 模型与费用口径

- 实际记录为1次CLI调用，加1次研究决策子代理派发；子代理内部推理次数、底层模型和费用未报告，保持unknown。
- CLI报告 `total_cost_usd=0.034155`；`--max-budget-usd 0.10`是此次配置上限。报告值不是发票或结算凭证，现金结算仍unknown。
- 本轮未调用本地Qwen。项目本地Qwen计数不代表外部LLM总使用量，不能据此写“总LLM=0”或“免费”。
- 工具、来源、外部决策和费用分别记录；更多决策、有效提案或成功落库不自动代表科研收益、用户价值或自动策略优势。

## 只读查看与原ID重放

下列命令在产品根执行，不调用CLI模型或子代理。不要用新ID重发已完成行动；保留原proposal、原版本参数和ID。

```powershell
.venv/Scripts/python.exe scripts/run_research_project.py status --workspace runs/a25-claude-selection-20261103/project
.venv/Scripts/python.exe scripts/run_research_project.py selection-context --workspace runs/a25-claude-selection-20261103/project
```

两个已完成选择的原ID重放入口如下；重放核对原请求和结果，不重新选择或执行工具。参数变化会触发冲突，不应靠改ID绕过。

```powershell
.venv/Scripts/python.exe scripts/run_research_project.py advance-selection --workspace runs/a25-claude-selection-20261103/project --request-id a25-cli-selected-action-1 --proposal runs/a25-claude-selection-20261103/proposal.json --expected-state-version 3
.venv/Scripts/python.exe scripts/run_research_project.py advance-selection --workspace runs/a25-claude-selection-20261103/project --request-id a25-delegated-feedback-action-2 --proposal runs/a25-claude-selection-20261103/delegated-proposal.json --expected-state-version 7
```

首次执行和重放结果分别保存在 [executed](../runs/a25-claude-selection-20261103/executed.json) / [replay](../runs/a25-claude-selection-20261103/replay.json)、[delegated-executed](../runs/a25-claude-selection-20261103/delegated-executed.json) / [delegated-replay](../runs/a25-claude-selection-20261103/delegated-replay.json)。若其他请求出现unknown，应保留原请求并核对已有账本；不能自动换ID、重新派发决策或补成成功。本次两项均已completed，不需要恢复执行。

## 当前快照与附件

- Project：`project-6f13dd8e32fd4538b0b2ff40e0aa3b99`。
- 最终snapshot：`7c0543f2634fe0a113cffbdf9b5d76c20be9a056695ca43e7b077c411a79e530`。
- [最终context](../runs/a25-claude-selection-20261103/final-context.json) / [最终状态](../runs/a25-claude-selection-20261103/final-state.json)。
- 当前报告：[PDF](../runs/a25-claude-selection-20261103/final-report/report.pdf)、[Markdown](../runs/a25-claude-selection-20261103/final-report/report.md)、[完整JSON](../runs/a25-claude-selection-20261103/final-report/report.json)、[重现输入](../runs/a25-claude-selection-20261103/final-report/input.json)、[SHA清单](../runs/a25-claude-selection-20261103/final-report/manifest.json)。早期 `report/` 不作为最终报告。

## Limitations

`runs/`是本机忽略证据目录，普通克隆不含上述附件。共享给队友时应连同获准分发的输入和证据包提供，不提交账户、凭据或会话数据。核心报告的“新增模型请求0”只对应其原生模型账本，外部用量须结合本轮模型sidecar读取。本轮证明外部选择能沿保存反馈接入同一执行链并保持原ID重放；未证明独立领域效果、科学批准或自动研究增益。
