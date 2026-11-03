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
- `--cli-budget-usd` 为大于0、至多0.10USD的累计报告估值配置阈值。宿主把剩余阈值传给CLI，并在已知合计达到阈值或费用未知时阻止后续发送。A34实跑已观察到单次CLI超出其剩余参数并返回预算错误，因此它不能保证单次调用或现金支出的硬上限。未知用量不按0计算。
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

## 一次授权，按模型反馈最多推进两步

`advance-batch`连续复用上述原请求链。每一步都从最新真实项目状态构建context，再让CLI选择；本地固定规则批次仍是单独入口。以下示例仅适用于本journal尚未固定grant，或已有grant与示例完全一致的情况；`--reason`须填写实际已授权范围。

```powershell
.venv/Scripts/python.exe scripts/run_host_selection.py advance-batch `
  --workspace $projectDir --request-id model-batch-1 `
  --expected-state-version $context.state_version --max-decisions 2 `
  --decision-limit 2 --cli-budget-usd 0.10 `
  --reason '已授权使用现有Claude CLI验证本批最多两次选择，沿原项目额度执行' `
  --claude-executable $claudeExe
.venv/Scripts/python.exe scripts/run_host_selection.py batch-status `
  --workspace $projectDir --request-id model-batch-1
```

`max-decisions`只能为1或2，是本批上限；`decision-limit`和`cli-budget-usd`仍是原host journal的累计grant，不能借新批次修改或重置。后者是配置阈值，单次CLI可能超出，不能作为硬支出保证。核心本地/来源/模型/现金额度照旧。没有合资格候选时不调用模型凑等待；模型选择等待、失败、invalid、stale、未知、达到本批或累计限制都会停下。

批次ID只接受1至60个ASCII字母、数字、下划线或连字符。原参数、初始项目/运行/来源身份、允许方法和确切已登记收据冻结在`host-model-selections/batches/batch-<ID>.json`。每步确定性子ID为`hostbatch-<ID>-s1/s2`，子请求仍保存原prompt、回答、费用和控制器结果。后来上传的资料不加入该批授权；项目在本批之外发生变化时停止，不能换当前版本偷偷续入原批次。

`batch-status`只读。中断后用首次原命令、原版本和全部原参数核对；只恢复原子请求，不能覆盖回答或重新派发sending/unknown。`record_status=incomplete`表示仍需核对原请求；`record_status=completed`表示本批已收口，原命令重放只返回保存记录，不增加模型或行动。子请求的`status=applied`仍须看其`outcome.status`，不代表工具成功或科学批准。

当前报告捕获完整批次收据为`host_model_batch`原件，报告JSON的`host_models.batches`保留授权、步骤和停止原因，输入包的`host-model-evidence/batches/`附件保留原字节。批次进展也会改变host快照，使旧报告过期；导出不会自动续批。此入口目前为CLI，尚未增加网页连续模型按钮。

2026-11-04，原A16钢材项目在同一ID/Run上从v5显式升级并登记版本匹配资料，随后真实CLI批次从v7执行一次来源读取至v11。CLI报告路由为`deepseek-flash`，估值0.040875USD、实际结算unknown；来源1/8，本地数值仍1/1，原生模型和拟合新增0。下一步无合法候选，批次保存`waiting/completed`，没有调用第二次模型。三个原登记/升级/批次ID重放均无新增，六页报告含批次及14份原件，见[A33结果](../runs/a33-bounded-model-20261104/README.md)。真实任务本次只有一次模型选择；双模型反馈及中断/未知恢复由两项工程夹具验证，不写成已在真实任务观察到两次连续模型决定。

同日A34沿原软件项目执行两次真实CLI尝试。第一请求完成官方Python文档选区读取，第二请求的冻结prompt确实包含第一次产生的2条新引用，但返回`error_max_budget_usd`、退出1，没有可执行选择或第二来源行动。两次CLI自报估值分别0.06301、0.061025USD，合计0.124035USD，超过原0.10USD配置阈值。原失败保留；离线费用补记后，当前报告明确显示超阈值与现金结算unknown，没有追加调用或扩大grant。原项目v11、数值仍1/1、来源2/8；第二份已登记资料仍未读。五个原ID核对零新增，5页报告与21份附件已核；两次连续成功尚未证明，详见[A34实跑与修复](../runs/a34-two-model-decisions-20261104/README.md)。

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

完整CLI错误输出若包含合法已报告费用，也计入累计数；请求仍为`failed/invalid`，不能消费成行动。输出截断、缺少费用或元数据非法时保持unknown。已保存的旧失败费用可按原请求离线核对，不发送模型、不执行工具：

```powershell
.venv/Scripts/python.exe scripts/run_host_selection.py reconcile-usage `
  --workspace $projectDir --request-id '<原failed或invalid请求ID>'
```

此命令核对原launch/stdout/exit和响应身份，只补已报告的费用、路由及usage字段。原失败、错误、控制器结果与原件保留；重复核对没有新增请求。输出仍含原`failed/invalid`状态，按统一CLI约定退出码仍可能为2，应核对费用字段和原失败，不能因此重新发送。报告标明已知合计是否超出配置阈值，CLI自报估值仍不等于现金账单。

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

当前报告导出会一并冻结host日志和已有原件；PDF及Markdown分别列出原生计数、CLI启动尝试、已知报告估值与未知用量。单独读取status仍可用于核对运行中的状态，交付不再依赖另外拼接该JSON。

## A28：报告包包含宿主模型记录

原四文件报告包保留不变，模型记录进入其中：

| 文件 | 宿主模型内容 |
|---|---|
| `report.json` | `host_models`中的状态摘要、原请求记录与证据快照 |
| `input.json` | `host_models.snapshot_sha256/status/asset_names`；`assets`以Base64保留实际已存在的日志、context、prompt、proposal、delegated原文及CLI launch/stdout/stderr/exit |
| `report.pdf` / `report.md` | 原生模型与外部CLI用量分别展示；已知USD估值、未知费用及未关联的历史外部选择单列，保留每条请求和控制器结果的区别 |

`source_manifest`列出这些原件的身份；不读取CLI认证或环境文件。`manifest.json`仍只登记上述四个交付文件，新增 `host_model_snapshot_sha256` 绑定宿主模型证据。导出只读取和保存，不调用模型或继续研究。

报告同时核对核心项目快照和宿主模型快照。即使核心版本未变化，准备了新模型请求、更新了原请求状态或已有原文改变，旧报告也会过期并拒绝下载；需重新导出当前报告，不覆盖旧原件。已分发的旧包若既无host记录、核心也无 `external_model` 选择，仍可读取；已有外部历史却缺少host快照标记的旧包须重新导出，不能继续把其原生模型数字当全部用量。

`applied`只说明已提交控制器，工具是否完成仍看 `outcome.status`。CLI费用是报告估值，子代理内部推理及未关联历史仍可未知，报告包不会把它们补成0或已结算。

2026-11-04已对原A27项目重导出：核心仍为v8、`764ee199…`快照，CLI仍2次/报告估值0.048195USD，本轮新增模型调用及行动均为0。重现输入内15份模型原件逐字节核对，四个HTTP下载与当前挂载文件一致；新PDF五页逐页渲染实看，无重叠或截断，保留原分节分页。旧A27报告先判stale，新导出为current；18791无外部历史的旧报告仍available。2项证据与2项HTTP必要检查通过。此次实际导出和下载通过同组本地HTTP接口完成，浏览器控制API不可用，未验证浏览器点击。见[核对结果](../runs/a28-model-report-20261104/validation.json)、[本轮说明](../runs/a28-model-report-20261104/README.md)及[新PDF](../runs/a28-model-report-20261104/report/report.pdf)；此证据覆盖报告与原件交付，不代表科研价值已验证。

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

A26按当时格式分别交付核心报告与host-status，原生计数未包含外部CLI；上述旧报告和原件保留。当前导出采用A28的模型证据快照，不回写该历史工件。

## 工作台入口

同一请求日志已接入本地工作台的“研究推进 → 开展下一步 → 模型选择与执行”。服务须同时显式传入 `--enable-local-actions` 和 `--claude-executable`，模型默认关闭；路径由宿主启动指定，浏览器不能改命令、可执行文件或提供方。启动示例、原请求核对及两次真实反馈接续见[工作台用法](local-workbench.md#用模型选择并执行一步)。

页面每次明确点击最多完成一次CLI选择与一个合法行动，首次提交固定累计grant；无候选或条件阻断时不发送。刷新和重开只读原日志，“核对原请求”沿原ID恢复，unknown不重发。模型可能沿CLI现有路由联网；原生Qwen计数与宿主外部用量分别显示，当前报告包也保留这一区分及原请求证据。

2026-11-03的独立18792验证工作台已用浏览器上传归档hiMSC输入，明确运行两次模型选择并完成主质量/分组画像，CLI路由均报告deepseek-flash，累计估值0.048195USD；原ID页面核对新增CLI和行动均为0。该轮证据在 `runs/a27-workbench-model-20261103/`，数值、报告身份与视觉验收以该轮最终记录为准；A27当时的核心报告仍需配套host日志读取外部用量，原工件不改写。

## Limitations

CLI及工作台入口支持显式有界选择与既有行动链路；模型解释、来源声明、工具完成仍需按领域证据核对，`scientific_validation` 保持 false。CLI 报告的 token、模型标签和 USD 估值不是服务商账单或现金结算，旧历史费用仍可为 unknown。`runs/` 证据在本机忽略目录，普通源码克隆不包含；共享前应按资料许可提供获准分发的证据，不包含认证或会话文件。
