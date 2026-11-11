# 本地项目：领域方法、来源、反馈与恢复

同一 [ResearchProject](../src/autoresearch/research_project.py) 登记领域来源、执行允许工具、保存反馈与下一决定，并按原身份恢复；CLI见 [run_research_project.py](../scripts/run_research_project.py)，设计边界见[底层架构](architecture/foundation.md)。各白名单方法按自身范围展示并导出当前快照报告，实际运行证据以[当前进度](current-progress.md)为准。

当前由同一 ResearchProject 连接白名单主方法：P02 保存 OOF、钢材保存模型复核、软件原件捕获检查，以及表格质量审计，并共用任务绑定的来源登记/读取。[ProjectController](../src/autoresearch/project_controller.py)提供只读next与一次advance，使用现有条件选择，不是LLM自主研究。每项目仍只有一个Run，尚无策略修改命令、多Run、模型或科学映射批准执行器。方法注册不接受任意模块名、工具代码或模型指定文件路径。

已登记表格项目另可接续`data.grouped-quality-profile`，绑定同来源已完成基础审计的行动/结果SHA，由原controller候选派发；它是同项目后续方法，不创建第二套控制器或新primary项目。用法及原值/分组资格边界见[同项目分组画像](tabular-quality.md#a17-同项目接续分组画像)。

## 材料与软件项目

宿主先捕获只读原件为带 SHA 的来源包，再由同一 create/step/status/resume 接口运行：

```powershell
Set-Location 'D:/XiangMuLuoDi/Development/ICT/track2/auto-research'

.venv/Scripts/python.exe scripts/run_research_project.py prepare-source --method software.source-integrity-check --input src/autoresearch/source_evidence_adapter.py --output runs/my-inputs/software.json
.venv/Scripts/python.exe scripts/run_research_project.py create --method software.source-integrity-check --source runs/my-inputs/software.json --workspace runs/my-software-project --goal '核对稳定原件与真实改写的捕获行为' --budget-ref local-developer-task:software
.venv/Scripts/python.exe scripts/run_research_project.py step --workspace runs/my-software-project --request-id source-integrity
```

来源包与 workspace 要分开，输出文件必须新建；示例不能覆盖已有输入或账本。钢材只复核指定已封存 R3 五模型，保留 yield strength、MPa²、MSE、187/62/63 组成划分和 1% 门槛；测试集只核对原已选基线。软件只做固定的真实文件 I/O 与明确故障注入，不执行捕获的源码。二者都不使用 P02 的 chemistry/topography 参数，也不继承 ALP 语义。

这是三个有限领域方法共用一套持久化与恢复，不表示任意数据集或跨域迁移收益已经成立。材料/软件可以不挂载 P02 封存包直接进入只读项目页；P02继续绑定原迭代包并保留五页与 X6 画布。三类项目各自显示真实指标和范围，报告入口见下文。

## 表格质量项目

新增`data.tabular-quality-audit`复用`prepare-source`捕获同目录`spec.json`与CSV/TSV，再经同一create、selection-context/advance-selection执行；不接受维度参数，也不新建控制器。报告显示记录/列数、声明键/分组及逐数值列计数，CSV与spec原字节和SHA均保留。目标、单位、来源与许可只是声明，分组重复不自动作为错误或独立样本，Count=0不自动变成缺失。输入schema、边界、可复制命令及实际结果见[表格质量核对](tabular-quality.md)。

## 创建与执行

以下在产品根执行。`source.json`必须已经存在且可校验；普通源码克隆没有ignored runs，需先向主团队取得封存包。示例workspace必须是新目录，不修改原研究；`--source`仅由宿主在创建时登记，后续step/resume不能更换来源。

```powershell
Set-Location 'D:/XiangMuLuoDi/Development/ICT/track2/auto-research'

create只复制并登记已封存来源，不执行工具。上例P02的step只允许`chemistry`或`topography`分组，stdout返回action记录：含`artifact`工件路径/`result_sha256`、按四处理规则分别保存的4条`observations`，以及引用行动/观察的`next_decision`。完整分组、排名和逐行残差不直接打印在stdout，保存在`artifact`相对workspace指向的JSON中，路径为`envelope.tool_result.result`（其下含`groups`、`rankings`、`rows`）。材料/软件step不传分组参数，分别返回模型MSE复核和文件I/O观察。

固定策略根据真实组数反馈生成下一决定；需来源时生成取证待办和 waiting。下文 attach-evidence 可读取实际提交选区，但不自动确认映射。需要乐观并发检查时，将 status 返回的实际 state_version 传给命令，不要抄固定版本号。

## 按条件查看与推进一步

在已创建的项目中，可以用next/advance选择下一项，而不手工指定主方法或来源收据：

```powershell
$projectPath = 'runs/my-steel-project'
.venv/Scripts/python.exe scripts/run_research_project.py next --workspace $projectPath
$projectState = .venv/Scripts/python.exe scripts/run_research_project.py status --workspace $projectPath | ConvertFrom-Json
.venv/Scripts/python.exe scripts/run_research_project.py advance --workspace $projectPath --request-id choose-1 --expected-state-version $projectState.state_version
# 同一父请求重放：保留上次相同参数，不用新的state_version替换原值。
.venv/Scripts/python.exe scripts/run_research_project.py advance --workspace $projectPath --request-id choose-1 --expected-state-version $projectState.state_version
```

next只读检查真实方法条件、现有来源索引、输入身份与预算，返回decision/executable/blockers，不创建行动。advance是写入命令：先保存父请求的固定选择、来源快照、状态/代码身份和子请求ID，再最多执行一个合资格白名单方法（含已登记后续方法）或已登记未读来源；等待、预算不足或unknown都不会启动另一项工具。已执行主方法的项目可能直接返回等待补资料，这不是失败。

父ID绑定首次选择；重复advance先读该绑定，不能因项目后来变化改成下一行动。**首次waiting也会冻结**：资料随后登记完成，仍须用新父ID推进。父/子参数改变会冲突；子行动已存在则沿原ID核对或恢复，子行动尚未接受而状态已变化则拒绝原选择，不重新选。PROJECT_BUSY不被补记成工具失败。父记录存于`controller_requests`，只保留决定和子行动引用，不复制完整项目或工具大结果。

旧项目出现CODE_CHANGED时，先按下文显式upgrade登记兼容版本；不自动升级或覆盖原账本。next不会改快照，advance即使只保存waiting父记录也会推进状态版本；原报告若因此过期，需要新导出。

### 提交上下文绑定的选择提案

原`next/advance`固定策略之外，`selection-context --workspace ... [--need next_check]`只读导出真实条件、预算、候选和FTS原文；`advance-selection --workspace ... --request-id ... --proposal <UTF-8文件> [--need next_check] [--expected-state-version ...]`接收受限提案。方法、参数和评价由宿主候选确定，提案只能选该`id`或等待，不能增补任意命令或工具。

## 代码变化后继续原项目

`CODE_CHANGED`表示原项目登记的代码身份与当前实现不同。先核对实际代码差异，确认已保存结果仍可读取，且没有执行中或状态不明的工具、来源和模型请求，再明确登记兼容版本。

已完成的历史upgrade请求用原ID和原参数回读时返回原升级收据，即使此后又登记了其他代码版本；回读不会改回当前项目身份，也不能替代新代码所需的明确升级。改动原`expected_code_identity`或来源额度仍会拒绝，新行动继续核对当前代码身份及未知执行状态。

以下命令使用原项目的旧身份和来源额度，不增加研究或模型额度：

```powershell
$status = .venv/Scripts/python.exe scripts/run_research_project.py status --workspace $projectPath | ConvertFrom-Json
.venv/Scripts/python.exe scripts/run_research_project.py upgrade --workspace $projectPath --request-id register-compatible-code-1 --expected-code-identity $status.code_identity --evidence-read-limit $status.budget.evidence_read_limit
.venv/Scripts/python.exe scripts/run_research_project.py next --workspace $projectPath
```

`upgrade`保存兼容登记原件并使state版本加1，保留原行动、来源、Host用量和累计预算；它不判断任意代码变更是否兼容，也不执行下一步研究。同一请求恢复时沿用原来的旧身份、额度和请求ID，不重新读取新身份拼成一次不同请求。

项目快照变化后，旧报告仍是原快照材料，当前下载会标记过期并停用。在“成果与复现”的“当前快照报告”区域明确点击“生成当前快照报告”，完成后在同一区域核对和下载；生成按钮仅在报告缺失或过期时显示，当前报告可下载时隐藏。生成不推进研究，不覆盖旧报告或旧演示材料；结果未知时保留原请求ID核对，不换ID重发。版本门解除后若无符合条件的候选，等待仍是有效结果，不能通过增加额度或伪造新反馈继续。

## 在同一项目接回来源

```powershell
$registration = .venv/Scripts/python.exe scripts/run_research_project.py register-evidence --workspace $projectPath --request-id register-sources-1 --bundle runs/my-source-bundle | ConvertFrom-Json
.venv/Scripts/python.exe scripts/run_research_project.py next --workspace $projectPath
.venv/Scripts/python.exe scripts/run_research_project.py advance --workspace $projectPath --request-id choose-read-1
.venv/Scripts/python.exe scripts/run_research_project.py knowledge --workspace $projectPath --point preparation --need 'ObjectName Count Intensity channel'
```

`runs/my-source-bundle`需先按当前项目模板填写，不能直接拿别的项目绑定套用。登记返回的`receipt_snapshot_sha256`可用于手工指定一次读取，作为上面advance的替代：

```powershell
.venv/Scripts/python.exe scripts/run_research_project.py read-evidence --workspace $projectPath --request-id read-sources-1 --receipt-snapshot-sha256 $registration.receipt_snapshot_sha256
```

| 阶段 | 实际成本与保存内容 |
|---|---|
| `register-evidence` | 读取原件、计算哈希并保存不可变收据/原字节，存在真实I/O；不提取选区、不创建来源行动或观察、不建FTS、不扣读次数。唯一登记收据数量也受既有来源上限约束 |
| `read-evidence`或advance选择来源 | 从已登记字节提取选区，创建来源行动/观察，成功后建FTS；完成/失败计入`evidence_reads_used`，未知保留`evidence_reads_reserved` |
| 原ID重放/完整结果恢复 | 核对原身份、复用或补交保存结果，不重新提取，不增加工具读次数 |

原`attach-evidence --workspace ... --request-id ... --bundle ...`仍兼容，在同一项目中连续登记并读取，原请求ID继续绑定读取行动。需要让控制器选择是否读取时使用拆分命令。完整提取结果在action.artifact；主方法用量、来源读取用量和旧模型预算分别保留，unknown不允许靠升级、新来源或新ID绕过。

真实选区进入现有 SQLite FTS5；四个决策点 clarification/design/preparation/interpretation 的请求与出处单独保留。命中和提取由宿主完成，不能称为模型已读或科学支持；来源状态始终保留 mapping unresolved、终点资格 unknown。

### 取得公开DOI元数据并接回

[公开来源接入](public-source-connector.md)提供可复制的`fetch → build-bundle → register-evidence → next → advance`命令：固定Europe PMC官方DOI公开GET先保存原HTTP实体字节和取得收据，再离线生成任务绑定包。包中raw、宿主projection、provenance分开保存；宿主投影保留原JSON pointer，不被标成论文原文或作者确认。register只登记，advance才从已登记身份读取选区并进入FTS，不重跑原primary。

项目`source_requests`在首次取源时冻结8次公开GET上限，与8次来源提取额度独立累计；换目录、重开或换ID不重置。received原ID只离线核对/恢复；known failed也耗1次，只有显式新ID才可在剩余额度内另取，0自动重试。sending/unknown阻断新执行及升级，原请求无完整回执时保留未知，不能把超时当零命中。模型仍0，原5元现金上限、历史P02未知模型请求及平台暂停均不变。

### 读取已归档PDF原文选区

同一任务绑定manifest的`pdf_page`支持单页`N`或页内`N:start-end`。页码从1起，偏移为pypdf整页提取文本的0基Unicode码点、end排除，不是PDF字节或视觉坐标。原PDF被完整捕获；结果另保留整页`page_text_sha256`、选区`text_sha256`、parser版本/警告及30秒截止。越界、空白、NUL或60000 UTF-8字节上限失败均拒绝，不OCR或改写原文。接回仍用`register-evidence → next → advance`；格式与实际坐标见[PDF选区入口](tabular-evidence.md#统一项目的pdf选区入口)。

## 导出当前项目报告

输出目录必须新建，且与项目目录分离。导出器只读收集一个稳定项目快照，核对完成行动、来源收据和原字节；保存失败/unknown及未决问题，不执行工具、不恢复请求、不拟合或调用模型。各方法用自己的结果表：P02为规则内MAE；钢材为MSE/MPa²及原1%门槛；软件为正常I/O与受控故障注入；表格为字段质量、键和分组计数，不套用前三者的科学含义。

| 文件 | 可核对什么 |
|---|---|
| `report.pdf` / `report.md` | 当前问题、方法、实际结果、来源节选、失败/未知、下一决定和边界 |
| `report.json` | 同一快照的项目记录、完整工具结果、来源身份与评价范围；`selection_history`保存已校验的外部选择投影，原context/proposal在完整父记录中；`registered_inputs.read_status=registered_unread`明确表示已登记尚未读取 |
| `input.json` | 主输入包、来源收据、读取状态及已捕获原件的Base64字节；已登记未读原件仍保留，不自动提取、执行源码或继续研究 |
| `manifest.json` | `project_id`、`project_snapshot_ref`及上述四文件的SHA/大小 |

PDF为有限摘要：当前P02报告只展示7处实际来源选区中的前4处，另3处明确指向完整`report.json`；PDF不包含全部论文原文。完整JSON保留全部实际选区、坐标、parser身份、失败和工具结果，原PDF字节在输入包中另存。

## 从工作台查看当前项目

打开对应端口的 `http://127.0.0.1:<端口>/#/project`；命令后加`--check`只核验挂载身份，不启动服务。非P02独立页只提供真实可用的当前项目入口与来源检索，隐藏历史五页和全局对象搜索；P02保留原五页和画布，`#/project`另展示活跃项目。钢材不显示ALP/红通道/MAE，软件检查明确区分实际正常I/O与故障注入，不将其称为生产事故。

`--report`可省略；此时当前快照报告按钮不可用。挂载时项目ID或`snapshot_ref`不匹配即拒绝启动；服务期间项目更新则`/api/project`标记报告`stale`，下载返回409 `REPORT_STALE`，需导出到新目录后重新挂载，不覆盖旧报告。独立页顶部PDF/JSON只指当前项目报告；P02顶部原PDF/ZIP仍属于封存研究，当前项目PDF/JSON在页面内另列，不混用。

| 只读下载/查询 | 内容 |
|---|---|
| `/api/project` | 项目状态、`primary_method`、领域范围、方法条件及报告可用/过期状态 |
| `/api/project/knowledge?need=...&point=...` | 已提取选区的四决策点FTS查询 |
| `/api/project/artifact/<action.id>` | 核对身份后的完整行动JSON |
| `/api/project/report.pdf`、`.json`、`.md` | 显式挂载且仍匹配当前快照的报告文件 |
| `/api/project/input.json` | 同版输入包；含原字节，来源许可与共享边界继续适用 |

## 重开与中断

```powershell
.venv/Scripts/python.exe scripts/run_research_project.py resume --workspace runs/project-slice-example --request-id oof-chemistry-1
.venv/Scripts/python.exe scripts/run_research_project.py step --workspace runs/project-slice-example --request-id oof-chemistry-1 --dimension chemistry
```

关闭终端后仍用原workspace和request ID。相同ID/内容返回原记录；同ID改维度会冲突，不能覆盖。结果工件已经保存但观察尚未提交时，resume只核验并继续提交；缺少已保存工件时保留unknown并记录待核对，不自动重算、重发或用新ID绕过，人工核对后的放行流程尚未实现。工件内容身份不符则报错，不当作有效结果。此同步工具本身不支持pending；不要将缺少回执写成成功。status只读，不恢复执行；失败输出`code/message`并以退出码2结束。

## 资源与科学边界

`--budget-ref`填写原研究的实际归属，例如本示例的`p02:r75-diagnostic-study`；它只保存历史预算归属引用，不导入原模型请求计数或费用，不验证供应商余额，也不增加云调用授权。状态中的`historical_spend_cny`、`historical_request_counts`保持`null`，`cash_settlement`为`unknown`，历史未知请求未解决；未知金额/次数不能按0处理。

P02输出仍是原始红通道代理值、四处理规则和探索性OOF，不确认ALP或机制。钢材输出限定固定组成划分下的保存模型审计，不算新拟合、官方Matbench分数或新材料有效性。软件输出限定本机文件读取与五项检查，不证明全部系统/竞态或生产安全。表格只做声明列的机械核对，不批准target、训练或科学资格。这些方法均未验证跨域策略收益和真实用户价值。观察与固定策略解释分别保存，完整工件而非摘要才是结果依据；有效负结果可以完成执行，下一决定不等于已完成下一研究任务。
