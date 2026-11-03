# Claude CLI 与子代理选择入口

`scripts/run_host_selection.py` 把真实项目 context 交给已安装的 Claude CLI，保存原始回答，再通过原 `ProjectController.advance_selection` 最多执行一个候选行动。也可以导入子代理回答。模型只选候选或等待，不能提供工具参数、增加额度或批准科学结论。完整选择协议见[选择提案](project-selection.md)，已有实跑见[外部模型验证](external-model-validation.md)。

## 先确认项目和本轮额度

在产品根运行。下列示例需要把项目目录和原生 Claude 可执行文件路径换成自己的已安装路径；不安装依赖、不下载模型。CLI分支必须明确传入 `--claude-executable`；Windows请选择原生 `claude.exe`，不要传Volta的 `.cmd` 启动包装。`--workspace` 指向已有 ResearchProject，不是工作台 manager 目录。

```powershell
$projectDir = 'runs/<已有项目目录>'
$claudeExe = 'C:/path/to/claude.exe'
$context = .venv/Scripts/python.exe scripts/run_research_project.py selection-context --workspace $projectDir | ConvertFrom-Json
$context | ConvertTo-Json -Depth 30
```

只有 `blockers` 为空且 `candidates` 非空才可准备请求；否则先处理已有阻塞或补所缺资料。首次 `prepare` 固定本项目 host journal 的累计 grant：

- `--decision-limit` 为 1 至 8。每个成功保存的 prepare 占一个名额，包括后来等待、失败或 invalid 的请求。
- `--cli-budget-usd` 为大于 0、至多 0.10 USD 的 CLI 累计报告估值上限。后续调用只获得剩余估值；未知用量不按 0 计算。
- `--reason` 记录已经获得的授权范围，填写这段文字本身不授予权限。

后续请求必须沿用完全相同的 grant，包括 reason；换 ID 不能扩额。当前没有 grant 修改或重置命令。这个额度从本 journal 开始累计，旧的外部调用、原生 Qwen 记录和历史 unknown 费用仍保留。原有 5 元现金上限及 AgentArts 暂缓边界不由此改变。

## 一条命令推进一次

在授权范围内，`advance` 顺序完成 prepare、一次 CLI 请求，以及回答合法时的一次显式消费。下面固定为最多一个决策。

```powershell
$hostArgs = @(
  '--workspace', $projectDir,
  '--request-id', 'host-choice-1',
  '--expected-state-version', $context.state_version,
  '--decision-limit', '1',
  '--cli-budget-usd', '0.10',
  '--reason', '已授权使用现有 Claude CLI 验证一次有界选择与执行',
  '--claude-executable', $claudeExe
)
.venv/Scripts/python.exe scripts/run_host_selection.py advance @hostArgs
```

`advance` 固定使用 `claude_cli`。它启动一个受本进程管理的 CLI，输入走 UTF-8 stdin；固定 `--print --safe-mode --tools '' --output-format json --no-session-persistence --effort low --max-turns 1`，并传入剩余 `--max-budget-usd`。自定义 hooks、MCP 和插件关闭，CLI 仍使用本机已有认证及模型路由配置。调用名称不能证明底层模型品牌，以返回的 `reported_models` 为准。

重复上面的**原命令和原参数**返回同一请求，不再调用 CLI 或创建新研究行动。保留首次的 `expected-state-version`；不要为了重放换成当前版本，也不要换 ID 绕过失败。

## 分步执行与检查

希望先查看实际送出的 context 时，用 `prepare` 代替直接 advance。以下命令与上一节是同一请求的两种操作方式。

```powershell
.venv/Scripts/python.exe scripts/run_host_selection.py prepare @hostArgs --provider claude_cli
.venv/Scripts/python.exe scripts/run_host_selection.py status --workspace $projectDir --request-id host-choice-1
.venv/Scripts/python.exe scripts/run_host_selection.py request --workspace $projectDir --request-id host-choice-1
.venv/Scripts/python.exe scripts/run_host_selection.py consume --workspace $projectDir --request-id host-choice-1
.venv/Scripts/python.exe scripts/run_host_selection.py status --workspace $projectDir
```

`prepare` 只冻结真实 context、prompt、provider、版本、可执行文件和 grant；`request` 才调用 CLI；`consume` 才提交原控制器。`status` 始终只读，不派发、不消费，也不恢复传输。回答只能包含 `choice`、`rationale`、`evidence_citation_ids` 三个字段；正文必须是完整严格 JSON，Markdown 包裹、重复键、额外参数和无效引用均不会自动修补后执行。

## 导入子代理回答

此分支用于已有的外部子代理派发。入口不会自行创建子代理，也不声称导入文件能证明它实际运行。首次准备时选择 `delegated`，不要传 `--claude-executable`。若项目已有 grant，必须复用原值且有剩余决策名额；上面 limit=1 的示例完成后不能在同 journal 再追加一个请求。纯导入分支仍需填写统一 grant 的 CLI 估值限额，这不表示已经调用 CLI，也不用于给子代理估价。

```powershell
$delegatedArgs = @(
  '--workspace', $projectDir,
  '--request-id', 'delegated-choice-1',
  '--provider', 'delegated',
  '--expected-state-version', $context.state_version,
  '--decision-limit', '1',
  '--cli-budget-usd', '0.10',
  '--reason', '已授权导入一次子代理有界选择并显式执行'
)
.venv/Scripts/python.exe scripts/run_host_selection.py prepare @delegatedArgs
```

把该请求保存的 `prompt.json` 交给子代理，让其按其中的 system 和 prompt 回答，并将原始回答保存为 UTF-8 JSON。回答示例结构如下；选择执行时，candidate ID 必须从该请求 context 的真实候选中取得，引用也只能使用其中已有的 citation ID。

```json
{"choice":{"kind":"wait"},"rationale":"现有证据不足以选择下一步，需要先补资料。","evidence_citation_ids":[]}
```

```powershell
.venv/Scripts/python.exe scripts/run_host_selection.py import-response --workspace $projectDir --request-id delegated-choice-1 --response 'runs/<原始回答>.json'
.venv/Scripts/python.exe scripts/run_host_selection.py consume --workspace $projectDir --request-id delegated-choice-1
```

导入只保存并解析原文，不执行研究。重复导入必须是同一字节内容，不能覆盖成另一个回答。`execution_declaration` 固定标记 `execution_verified=false`，模型、内部推理次数和费用均为 unknown；真实派发证据应另外保留，不能填成 0 或免费。

## 状态、重放与恢复

| 状态 | 含义与下一步 |
| --- | --- |
| `prepared` | 请求已冻结，尚未派发。可查看后用原 ID request；若项目 context 已变化，request 保存 stale 并拒绝派发。 |
| `sending` / `unknown` | 可能已经派发。保留全部原文件；只可用原 ID request 核对已有收据。完整 `exit.json` 存在时核对原 launch/stdout 后恢复，缺失或不完整时不重发。 |
| `received` | 原文已通过格式解析，尚未提交行动。用原 ID consume；候选、引用及当前状态仍由原 validator 检查。 |
| `applied` | 已提交原控制器，并保存其 outcome。读取 `outcome.status` 判断 completed、failed、waiting 或 unknown；applied 不等于工具成功。 |
| `invalid` / `stale` / `failed` | 保留原文及错误；同 ID 不替换回答、不重发。若要新请求，仍须满足原累计额度、项目条件及授权。 |

若原控制器已经提交行动，但进程在写 journal 的 applied 状态前中断，重新执行原 ID consume 会通过原控制器请求账本取得同一 child，再完成本 journal 保存。恢复不创建第二次行动。

`prepared`、`sending`、`unknown`、`received` 都会阻止另开决策，防止跳过未决请求。某次已启动 CLI 的费用未报告时，后续 CLI 发送也会被 `HOST_USAGE_UNKNOWN` 阻止。CLI 超时为 180 秒，停止本次拥有的进程树后保留 unknown；不自动重试或改用其他模型。

发送前确认过期的请求会终结为 stale，没有启动模型；已有名额仍计入累计决策数。若同一 grant 还有名额，可重新读取当前 context，以新 ID 准备下一次决策。sending/unknown 不按这种方式终结。

命令输出 JSON。invalid、stale、failed、unknown、sending 或明确错误的退出码为 2；退出码 0 仍需查看状态和 outcome，不能据此判定科学结论成立。

## 证据与用量

所有 host 记录保存在项目内部：

```text
<project>/host-model-selections/
  state.json
  requests/0001/
    context.json
    prompt.json
    transport/launch.json
    transport/stdout.bin
    transport/stderr.bin
    transport/exit.json
    delegated.bin
    proposal.json
```

CLI 分支使用 transport 文件，导入分支使用 delegated.bin；proposal.json 在成功提交原控制器后保存。`state.json` 记录原请求、回答身份、结果和用量，不应手改或删除以重置额度。准备中断后，原参数 prepare 可从已有记录恢复 context/prompt 文件；已存在的不一致文件会拒绝覆盖。

项目级 status 分别返回：

- `usage.decision_slots_used`、`cli_launch_attempts`、`delegated_outputs_received`：本 journal 的请求名额、CLI 启动尝试和已接收导入数。
- `known_cli_reported_cost_usd` 与 `cli_cost_unknown`：已知报告估值之和及是否还有未知 CLI 费用。已知和不代表完整账单。
- `unlinked_external_selection_count` 与 `prior_external_usage`：原控制器中尚未由本 journal 覆盖的外部选择；存在时旧用量为 `unknown_not_zero`。
- `native_local_model_budget`：原生模型账本的允许、已用和预留次数，以及原现金上限；它不包含外部 CLI 或子代理用量。

导出核心报告时，应同时保存本入口 status JSON。现有核心 PDF 的模型数字只来自其原生账本，尚未自动合并 host journal。

## 正式入口实跑

2026-11-03，`runs/a26-host-selection-20261103/` 用真实归档的 312 行钢材 CSV 建立独立集成验证项目，通过正式 `advance` 完成一次选择与执行。

| 项目 | 实际结果 |
| --- | --- |
| 请求 | `a26-claude-quality`；累计决策限额 1，CLI 报告估值限额 0.10 USD。 |
| CLI | 实际启动 1 次，exit 0，5.906 秒；返回路由 `deepseek-flash`，报告估值 0.02707 USD。 |
| 执行 | 回答选择 `data.tabular-quality-audit`，原控制器 completed 1 个行动；输出 312 行、2 列，缺失、数值零及完全重复行均为 0，目标值范围 1005.9 至 2510.3 MPa。 |
| 重放 | 同一 advance 的原参数返回完全相同记录，核心状态、host status 与传输原件不变；新增 CLI 0、行动 0。新 ID 因 `HOST_DECISION_LIMIT` 拒绝。 |

原命令见 [command.json](../runs/a26-host-selection-20261103/command.json)，首次成功结果见 [advance.stdout.json](../runs/a26-host-selection-20261103/advance.stdout.json)，重放见 [replay.stdout.json](../runs/a26-host-selection-20261103/replay.stdout.json)。[CLI 原始输出](../runs/a26-host-selection-20261103/project/host-model-selections/requests/0001/transport/stdout.bin)、[退出收据](../runs/a26-host-selection-20261103/project/host-model-selections/requests/0001/transport/exit.json)、[host 用量](../runs/a26-host-selection-20261103/host-status.json)、[行动工件](../runs/a26-host-selection-20261103/action-artifact.json)与[核心 PDF](../runs/a26-host-selection-20261103/report/report.pdf)分别保留。这个新项目的原生模型计数为 0，只表示未调用原生桥；实际 CLI 次数是 1。

```powershell
.venv/Scripts/python.exe scripts/run_host_selection.py status --workspace runs/a26-host-selection-20261103/project
.venv/Scripts/python.exe scripts/run_host_selection.py consume --workspace runs/a26-host-selection-20261103/project --request-id a26-claude-quality
```

独立CSV计数、报告身份和原项目保护核对见[validation.json](../runs/a26-host-selection-20261103/validation.json)。

本次首个正式命令在模型派发前因 journal 目录尚未创建返回 `PROJECT_NOT_FOUND`；原失败输出保存在 `pre-dispatch-failure-*`。修复目录创建后沿原参数完成首次实际调用，没有重发已启动的模型请求。

## Limitations

此入口是显式 CLI 流程，尚未接入工作台按钮或 HTTP 写接口。它证明的是有界选择与既有行动链路；模型解释、来源声明、工具完成仍需按领域证据核对，`scientific_validation` 保持 false。CLI 报告的 token、模型标签和 USD 估值不是服务商账单或现金结算，旧历史费用仍可为 unknown。`runs/` 证据在本机忽略目录，普通源码克隆不包含；共享前应按资料许可提供获准分发的证据，不包含认证或会话文件。
