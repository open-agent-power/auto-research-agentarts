# Claude CLI 与子代理的选择及计划建议入口

`scripts/run_host_selection.py` 把真实项目 context 交给已安装的 Claude CLI，保存原始回答，再通过原 `ProjectController.advance_selection` 最多执行一个候选行动。也可以导入子代理回答。选择用途下，模型只选候选或等待，不能提供工具参数、增加额度或批准科学结论。完整选择协议见[选择提案](project-selection.md)，已有实跑见[外部模型验证](external-model-validation.md)。

## 根据真实反馈建议研究计划

`prepare`和`advance`支持`--purpose plan`，默认用途为`selection`。计划请求与选择请求使用同一份累计grant，`decision_limit`、`cli_budget_usd`和原授权`reason`沿用原值。准备一次计划请求也占一个决策名额。CLI的`advance`会取得一次回答并消费为计划建议，`advance-batch`仍用于候选行动选择。

新计划context由[research_plan_proposal.py](../src/autoresearch/research_plan_proposal.py)的`build_context(project)`生成，schema为`research-plan-context-v2`。它保留完整原`selection_context`，并供应实际行动反馈的有界投影及`saved_comparisons`。行动ID、请求ID、方法、状态、失败和工件引用保持；数值、协议、范围及实际用量不截断，来源全文和资源正文改用明确原件定位，历史决定改用原行动账本定位。`build_prompt`说明这些引用没有包含原文，`parse_host_response`解析原回答，`build_proposal/validate_proposal`绑定提案。旧v1封存context按原合同验证和重放，不改写成v2。

模型原始JSON恰含`plan`、`reason`、`feedback_action_ids`和`expected_improvement`。`plan`恰含`question/basis/steps/expected_feedback`四项文本。反馈引用采用该请求context中的真实行动ID，已有反馈时至少引用一项。这里的`reason`解释计划为什么修订，与CLI参数中记录授权范围的`--reason`分别保存。

### 计划执行条件

v2的反馈仍有`action_id/request_id/method_id/status/observations/next_decision/failure/artifact_ref`八个字段。每项非空`next_decision`通过`kind=saved_action_record`及项目、行动、请求、`field=next_decision`定位完整原决定；决定只存在原行动账本，不能指向更早的工具工件。来源观察的`exact_text_ref`以`artifact_ref`与`path=[tool_result,observations,index,exact_text]`定位原文，`characters`记录原字符数。设计绑定保留原训练声明和资源身份，完整资源正文在`resource_ref`所指的原工件字段。其他观察值与原件保持，当前候选、预算、条件、未核验研究者意见及检索引文仍来自原sealed selection context；顶层`remaining_questions`另完整保留当前决定记录的同名问题列表，无该字段时为空。

`saved_comparisons`复用既有严格父子核对，保留双方行动/设计/资源身份、可比状态、失败原因、评价类型、完整匹配行数与MAE/负预测计数，省去输入画像正文。`mae_change`为候选减父版本，正值表示这次误差增加，负值表示降低；它与相对训练折均值参考的优势分别解释。不可比记录不提供数值优势，较低保存MAE也不证明物理因果、独立泛化或工程适用。

64KiB门限保持不变。固定投影后仍超过上限时明确拒绝，不按误差挑选行动、截断数值或自动扩额度。原行动、原文、完整资源与历史冻结context保留；字段引用不表示原文已经提供给模型。离线配方导出对v2先从原工件重建相同投影再逐值核对，对旧v1仍核对原观察。旧未提交请求的context若与当前构造不符，按原freshness门保留过期，不用新context覆盖旧请求。

新的计划请求在原冻结context之外附带`execution_conditions`：本地工具、来源读取与估计器拟合的剩余额度（扣除预留），当前合资格候选，各方法缺条件与整体阻塞。余额不等于方法资格；没有待选来源时，即使来源读取额度尚余也不能读取。拟合预留及未知执行继续占用原额度，缺失或未知预算显示为未知。

模型提示要求区分现在可执行的行动与补齐条件后的后续工作，立即行动注明原候选身份；无候选时可以等待、索取具体材料或复核已有结果。来源确认不补回工具额度，工程夹具仍按工程夹具解释；划分差异、训练量变化和负对照需要保留竞争解释与协议边界。

`LocalWorkbench.model_view`的独立`plan_reviews`数组与报告JSON同名字段均由`plan_readiness.review_plan_requests`从原请求context只读派生。每项含`request_id`和`assessment`，后者保留`project_id/state_version/snapshot_ref/context_sha256`及`plan-readiness-v1`。工作台模型计划卡、Markdown和PDF显示**请求准备时**的条件；历史条件不会随当前项目变化，也不写回Host原记录或改写旧prompt。prepared/unknown/invalid请求同样可显示其准备条件，不表示回答已经审阅。

此投影不解析计划正文、不自动判定科学解释或拒绝自由文本计划。`scientific_review=required`与`scientific_validation=false`始终保留；等待或补材料的计划仍可明确采用。计划文本协议及原采用、拒绝、过期和同ID恢复门保持，实际执行继续由原控制器重新核对条件和累计预算。

### 研究者意见进入后续context

sealed selection context以可选`researcher_feedback`保存原项目意见，每条共9个字段，为`id/request_id/based_on_state_version/plan_version/author/comment/next_step/action_id/content_trust`。意见与原请求、提交依据版本、当时计划版本及可选既有行动关联，`plan_version`可为空，信任标记为`unverified_researcher_statement`。原Host context保留封存内容，新意见随后续新context提供。

计划与配方prompt按未核验研究者陈述读取意见，采用意见时要求在reason中指出原note ID。`feedback_action_ids`继续限于真实工具action。报告保留意见与该信任边界，科学结论按实际工具和来源证据确认。旧项目沿显式源码兼容升级流程使用新写入，资源用量沿原账本累计。用法见[研究者意见](local-workbench.md#记录研究者意见)。

A67工程夹具已真实保存1条意见，下一计划context及prompt的只读组装包含原意见，工具反馈数组为空。该轮模型、研究工具和Host请求均为0，实际模型读取及基于意见生成新计划的效果仍待后续验证。3项定点backend/protocol回归、前端四门禁、真实保存及原ID重放、报告四下载与原意见一致性均已核对，工程联调与实际用户试用分别记录。

### 导出给子代理并导入原回答

以下沿用已有且有剩余名额的授权。`$projectDir`指向原项目，先从该项目读取当前版本与原grant。

```powershell
$planState = .venv/Scripts/python.exe scripts/run_research_project.py status --workspace $projectDir | ConvertFrom-Json
$hostState = .venv/Scripts/python.exe scripts/run_host_selection.py status --workspace $projectDir | ConvertFrom-Json
.venv/Scripts/python.exe scripts/run_host_selection.py prepare --workspace $projectDir --request-id delegated-plan-1 --provider delegated --purpose plan --expected-state-version $planState.state_version --decision-limit $hostState.grant.decision_limit --cli-budget-usd $hostState.grant.cli_budget_usd --reason $hostState.grant.reason
```

把该请求保存的`context.json`和`prompt.json`交给子代理，按原prompt生成完整JSON并保存原回答。导入与消费沿用原请求ID。

```powershell
.venv/Scripts/python.exe scripts/run_host_selection.py import-response --workspace $projectDir --request-id delegated-plan-1 --response 'runs/<原始计划回答>.json'
.venv/Scripts/python.exe scripts/run_host_selection.py consume --workspace $projectDir --request-id delegated-plan-1
.venv/Scripts/python.exe scripts/run_host_selection.py status --workspace $projectDir --request-id delegated-plan-1
```

消费成功后，宿主请求进入`proposed`。使用者查看计划正文、修订理由、预期改善与反馈引用，再采用或拒绝。采用命令为以下一条。

```powershell
.venv/Scripts/python.exe scripts/run_host_selection.py adopt-plan --workspace $projectDir --request-id delegated-plan-1
```

拒绝建议时改用`reject-plan`，填写实际原因。

```powershell
.venv/Scripts/python.exe scripts/run_host_selection.py reject-plan --workspace $projectDir --request-id delegated-plan-1 --reason '填写实际拒绝原因'
```

采用后原请求为`applied`，`outcome.kind`为`plan_revision`并引用保存的研究计划版本。拒绝后为`rejected`，保留原建议和拒绝原因。原ID采用重放沿用原修订，中断后核对同一ID恢复；同ID拒绝重放使用原原因。项目或代码过期时保存`stale`及原回答，再按当前事实决定后续。

CLI分支采用实际新请求ID，在`advance`中增加`--purpose plan`，同时传入既有原生`--claude-executable`及相同grant。采用或拒绝已保存建议沿本地写入权限处理，服务关闭CLI进程能力时仍可处置这些建议。

本节说明协议与Host入口。实际子代理计划修订、后轮接续及桌面和手机页面验收见[A63记录](#a63-真实子代理计划修订与后轮接续)。

### A80：实际数值反馈后的研究计划修订

2026-11-07，公开diabetes关联项目沿原Host的`purpose=plan`入口准备`a80-feedback-plan`，将已保存质量与关联行动交给一次真实子代理决策。原回答通过`import-response/consume`保存为建议，再经工作台明确采用，计划v1→v2、state9→10。两条实际反馈均被原回答引用，完整回答保留，未改写为人工编写计划。

v2保留总体及两个原编码组的正向描述性关联，将下一步从重复计算改为核对来源、目标量尺、分组编码及抽样单位；原条件不足时继续等待。采用不执行来源读取或重算，原本地2/2、原生模型0、拟合0及现金历史保持。原请求再次采用后，完整项目state一致。

本项目Host累计决策为1/2，CLI启动0；原回答中的“模型请求额度为0”对应冻结context里的原生本地模型额度，外部Host沿独立日志记录。供应商声明、内部推理次数及费用保持unknown。本次证明实际工具反馈引起计划修订，不证明配方RSI收益、真人使用价值或外部定义已经核实。原件在本机ignored `runs/a80-feedback-stage-resumption-20261107/`。

外环接续实现完成后，仅对此关联项目显式登记新代码身份，state10→11，原行动、两版计划及全部预算保持。18797加载后已生成state11的5页当前报告并逐页查看，四种HTTP下载与保存原件一致；原A63/A64保留。桌面与手机的计划v2和采用记录已实际查看。本机读取已有结果、模型新请求与原生本地模型计数分别记录。

### A81：计划v2驱动来源读取与真实后轮选择

2026-11-07，沿A79同一项目的计划v2，正常登记本机scikit-learn描述与此前捕获的loader源码，明确读取后取得第一轮来源反馈。随后登记NCSU原页面HTML的11–44行，保留原字节及原始／R版入口区别。原Host grant剩余1个名额用于`a81-follow-planv2`，真实子代理根据当前计划、已读片段及原候选选择该来源，由原控制器完成。模型回答引用了已提取的两处实际citation，完整回答与消费记录均保留。

来源行动为`action-7087f722425a13d262cd6642ef954e71`和`action-1a95f98ceb49740b3d8ce7515c8b9188`，项目state11→21。原读取请求及Host consume按同ID回读后，完整state和Host用量一致。累计来源2/8、Host2/2、CLI0，本地分析仍2/2、原生模型0、拟合0；原费用unknown和5元现金归属保持。当前无未读来源候选，保存waiting，不追加模型请求。

这次补上了实际分析反馈→计划修订→资料补充→新反馈→后轮模型选择及执行的轨迹。默认baseline已能选择该来源，未人为构造遗漏方法或创建配方版本，不据此声称配方收益或多轮RSI已完成。字段语义可支持部分描述，具体量尺、编码语义、独立性及原数据使用条件仍按[来源解释范围](numeric-association.md#来源反馈后的实际接续)保留未知。state21的7页PDF已逐页查看，四下载与保存原件一致；PDF第3、5页留白较大，沿用原分页。原件在本机ignored `runs/a81-source-feedback-continuation-20261107/`。

## 继续研究的计划与行动阶段

工作台的“继续研究”把计划处理和行动批次放在同一条持久记录中，沿用原Host请求、采用门和执行器。起步与恢复步骤见[工作台用法](local-workbench.md#继续研究选计划再按授权行动)。

`POST /api/local-workbench/continue`严格接收`request_id/project_id/expected_state_version/plan_mode/execution_mode/max_actions/allowed_methods/source_receipt_sha256s/reason`。`plan_mode`只能为`reuse`或`suggest`，`execution_mode`只能为`rules`或`model`；方法与确切收据按本次body冻结，后续资料不会自动加入。

- `reuse`绑定当前已采用的研究计划，不创建计划建议。
- `suggest`沿已有且有剩余名额的Host grant准备`purpose=plan`，冻结实际context与反馈。服务显式启用固定`--claude-executable`时，新计划请求沿原Host的`prepare → request → consume`取得并保存建议；未启用CLI时仍准备delegated请求，停在`prepared`，需要沿原[导出/导入流程](#导出给子代理并导入原回答)提供原回答并消费。该入口不派发Codex子代理。回答消费为建议后停在明确采用/拒绝门，不自动采用。采用后沿原continue ID继续，拒绝不自动切换计划方式。
- 计划阶段完成后，`rules`接回原`LocalWorkbench.batch`，`model`接回原`HostModelBatch`。模型执行要求服务已启用固定CLI；浏览器不能更改可执行文件或提供方。每个模型选择仍按原grant计数，计划请求也占一个名额，`max_actions`不代表总模型请求数。

计划请求首次准备时冻结provider及可执行文件路径。旧delegated请求即使后来启用CLI，也只沿原请求的导出/导入流程恢复。CLI计划请求处于`prepared/sending/unknown`时，服务配置缺失或可执行文件路径改变，保留原计划阶段及请求，不改走delegated或另一CLI路径；恢复须匹配原配置。`received`只消费已保存回答，`proposed/applied`只读原建议及采用记录，不再准备或启动CLI。

`GET /api/local-workbench/continue/<request_id>.json`只读返回完整冻结body与`phase/plan_ref/batch_ref/steps/stop`，工作台`describe.continuations`列出接续记录。恢复先核对原记录，再以同ID、首次版本及全部原body明确继续；中间采用计划不会允许把当前版本替换进冻结body。原批次一经关联就沿该`batch_ref`恢复，已收口重放只返回原结果，unknown不重新派发或覆盖回答。

模型分支会先核对实际候选是否都在本次范围内；两次模型决策还要求授权覆盖原Host batch冻结的完整方法和收据范围，包括已有登记。因此只勾选未读资料不能满足某些旧项目的两步模型范围，入口会保存`NOT_AUTHORIZED`并停止；不会扩大授权或另造执行器。可按当前实际范围明确选择一次行动。

需要Host的阶段无grant或累计名额用尽时停止；`model`行动阶段CLI未启用、候选未获授权、原请求unknown及其他阻断也保存停止，不默认配置或扩大额度。规则批次与模型批次继续沿各自原预算及恢复门禁处理，历史费用unknown和现金归属保留。研究计划v2不等于配方v2；这个入口不创建新配方版本、不自动采用配方，RSI的验证及明确采用/回退仍走独立流程。

## 配方改进提案与验证接线

主开发已落盘recipe change的模型提案协议与允许工具验证适配。A64已通过一次真实子代理提案和允许来源读取，桌面及手机截图、五页导航与报告下载均已实际核对，功能已通过[PR #9](https://github.com/1263-ux/auto-research-agentarts/pull/9)合并。队友继续拥有`recipe_improvement`外环，负责版本、采用或回退以及连续轮次。实际范围见[A64记录](#a64-配方修改提案与允许工具验证)。

[recipe_change_proposal.py](../src/autoresearch/recipe_change_proposal.py)冻结实际`research_context`、`current_recipe`与`improvement_goal`，schema为`recipe-change-context-v1`。当前配方必须匹配项目范围和need，轨迹须含已完成或失败的真实反馈。模型原回答恰含`candidate/reason/feedback_action_ids/expected_improvement/validation_plan`。其中`candidate`是`research-recipe-v1`，保留原配方`id`、`scope_match`和`need`，版本加1，`on_no_match`为`wait`。方法与评价引用须成对来自冻结的`selection_context.conditions`，反馈引用须来自实际完成或失败的行动。

Host已支持`purpose=recipe`，复用原累计grant，consume保存为`proposed`。CLI的`prepare/advance`支持`--purpose recipe --recipe <JSON文件> --improvement-goal <文字>`，原请求和回答继续由Host记录。子代理分支先prepare，再经原请求ID导入原回答并consume。CLI分支沿既有传输。声明中的模型、内部推理次数和费用仍按已知或unknown保存。

[recipe_improvement_adapter.py](../src/autoresearch/recipe_improvement_adapter.py)提供`propose_recipe_change`与`validate_recipe_change`。提案适配返回`recipe-change-proposal-result-v1`，其`candidate`为完整的`recipe-change-proposal-v1`，该对象内部的`candidate`才是原生配方。子代理首次返回`prepared`及原context、prompt位置，导入实际回答后同ID返回`proposed`。验证时传入完整提案，采用后保存新配方时取提案内部的`candidate`。

验证适配使用同一Host `request_id`，只读编译同一冻结context下的baseline与候选，比较决策，再经原控制器最多执行候选一步。调用方显式提供`allowed_methods`与`allowed_receipts`，来源收据按精确身份限制。原Host请求目录保存`validation-input.json`与终态`validation-result.json`，中断沿原ID恢复，unknown保留待核对状态。本地方法和来源用量沿原项目账本累计，采用或回退由外环决定。参数与返回字段见[队友接口](recipe-research/team-module-interface.md#主开发的配方改进适配接线)。

### 工作台读取验证记录

[read_recipe_validation(workspace, request_id)](../src/autoresearch/recipe_improvement_adapter.py)返回`recipe-change-validation-view-v1`，共7个字段，为`schema_version/project_id/request_id/status/input/result/error`。读取绑定原Host提案、`validation-input.json`、`validation-result.json`和原控制器结果，完成状态需要原证据完整且一致。状态范围为`not_started/pending/recovery_required/unknown/completed/waiting/failed/invalid`。

该reader用于模型视图GET的独立`recipe_validations`数组，`records`承载原Host请求记录。读取仅投影已保存事实，执行恢复沿原显式流程处理。研究页已在计划与画布之间展示版本、冻结baseline及候选选择、实际工具状态、模型理由、原记录定位和验证JSON下载。采用决定及后轮管理由待实现的队友`recipe_improvement`外环提供。

一项定点reader回归通过，前端format、Lint、类型检查和构建通过，桌面及手机8张最终截图已实际查看，无页面横向溢出。验证JSON实际下载与reader view逐值一致，API records逐条等于原Host记录，A64 v13和A63 v11的core及Host完整状态逐值一致。五页正常点击、报告reader和项目切换均已核对，页面错误及HTTP失败为空，服务JS及CSS与最终构建一致。invalid客户端夹具隐藏完成标签与比较，本轮新增模型、工具及报告导出均为0。使用入口见[工作台展示](local-workbench.md#主工作台只读展示)。

## 已验证到哪里

- **A27：同项目两次显式CLI提交已走通。** 同一hiMSC集成项目先完成主质量检查，再完成绑定该action/result的分组画像；第二次冻结context与第一次执行后的context具有相同项目、版本、快照和context身份。两次请求均applied，控制器结果与子行动均completed，CLI报告合计0.048195USD。见[原反馈context](../runs/a27-workbench-model-20261103/after-first-context.json)、[原用量](../runs/a27-workbench-model-20261103/host-status.json)及[原验证记录](../runs/a27-workbench-model-20261103/validation.json)。这是两次明确提交，不能据此认定`advance-batch`已在真实任务中自动连续成功两次。
- **A25：同项目一次CLI加一次子代理接续已走通。** CLI选择来源读取后，子代理收到真实反馈和引用，再选择分组画像并完成执行；较早的主质量bootstrap由主控执行。不能把它写成两次CLI或内部恰好两次推理，见[原验证说明](external-model-validation.md)。
- **A34：原软件批次第二次CLI仍失败。** 第一次来源读取完成，第二次含新增引用但返回预算错误；该软件批次没有取得第二个合法选择或行动。它不覆盖A25/A27已有工程成功，也不能借其他项目成功改写本次失败。各路径的对照出处见[限定原件核对](../runs/a42-key-node-readiness-20261104/model-chain-readback.json)。

以上支持特定集成项目的选择、真实执行与反馈接续；CLI品牌以自报路由为准，内部推理次数和现金结算未独立核实。领域解释、独立用户收益与自动研究优势仍须分别验证。

## 先确认项目和本轮额度

在产品根运行。下列示例需要把项目目录和原生 Claude 可执行文件路径换成自己的已安装路径；不安装依赖、不下载模型。CLI分支必须明确传入 `--claude-executable`；Windows请选择原生 `claude.exe`，不要传Volta的 `.cmd` 启动包装。`--workspace` 指向已有 ResearchProject，不是工作台 manager 目录。

```powershell
$projectDir = 'runs/<已有项目目录>'
$claudeExe = 'C:/path/to/claude.exe'
$context = .venv/Scripts/python.exe scripts/run_research_project.py selection-context --workspace $projectDir | ConvertFrom-Json
$context | ConvertTo-Json -Depth 30
```

`selection`用途要求`blockers`为空且`candidates`非空。`plan`与`recipe`用途要求无全局阻断且无未决原生模型请求，候选为空时也可准备提案。`recipe`另要求有已完成或失败的真实反馈，以及匹配项目范围和need的当前配方。首次`prepare`固定本项目host journal的累计grant。

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

`advance-batch`连续复用上述原请求链。每一步都从最新真实项目状态构建context，再让CLI选择；规则批次沿原本地执行器处理，工作台通过“继续研究”选择这两种执行方式。以下CLI示例仅适用于本journal尚未固定grant，或已有grant与示例完全一致的情况；`--reason`须填写实际已授权范围。

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

当前报告捕获完整批次收据为`host_model_batch`原件，报告JSON的`host_models.batches`保留授权、步骤和停止原因，输入包的`host-model-evidence/batches/`附件保留原字节。批次进展也会改变host快照，使旧报告过期；导出不会自动续批。工作台“继续研究”的`model`分支接回同一模型批次，旧批次记录继续读取。

2026-11-04，原A16钢材项目在同一ID/Run上从v5显式升级并登记版本匹配资料，随后真实CLI批次从v7执行一次来源读取至v11。CLI报告路由为`deepseek-flash`，估值0.040875USD、实际结算unknown；来源1/8，本地数值仍1/1，原生模型和拟合新增0。下一步无合法候选，批次保存`waiting/completed`，没有调用第二次模型。三个原登记/升级/批次ID重放均无新增，六页报告含批次及14份原件，见[A33结果](../runs/a33-bounded-model-20261104/README.md)。真实任务本次只有一次模型选择；双模型反馈及中断/未知恢复由两项工程夹具验证，不写成已在真实任务观察到两次连续模型决定。

同日A34沿原软件项目执行两次真实CLI尝试。第一请求完成官方Python文档选区读取，第二请求的冻结prompt确实包含第一次产生的2条新引用，但返回`error_max_budget_usd`、退出1，没有可执行选择或第二来源行动。两次CLI自报估值分别0.06301、0.061025USD，合计0.124035USD，超过原0.10USD配置阈值。原失败保留；离线费用补记后，当前报告明确显示超阈值与现金结算unknown，没有追加调用或扩大grant。原项目v11、数值仍1/1、来源2/8；第二份已登记资料仍未读。五个原ID核对零新增，5页报告与21份附件已核；本次软件批次没有完成两次连续成功，详见[A34实跑与修复](../runs/a34-two-model-decisions-20261104/README.md)。

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
| `received` | 原文已通过格式解析，待原ID的consume处理，按purpose进入行动选择或计划建议。引用与当前状态仍由对应validator检查。 |
| `proposed` | 计划建议已保存，待使用者采用或拒绝，保留原回答、计划正文、理由、预期改善与反馈引用。 |
| `applied` | selection用途保存原控制器outcome，plan用途保存`kind=plan_revision`及采用的计划版本。实际结果读取对应outcome。 |
| `rejected` | 使用者已拒绝计划建议，原建议及固定的拒绝原因继续保留。 |
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

原单步“模型建议与行动”每次明确点击最多完成一次CLI选择与一个合法行动，首次提交固定累计grant；无候选或条件阻断时不发送。“继续研究”按[计划与行动阶段](#继续研究的计划与行动阶段)处理，沿既有grant进入原批次。刷新和重开只读原日志，“核对原请求”沿原ID恢复，unknown不重发。模型可能沿CLI现有路由联网；原生Qwen计数与宿主外部用量分别显示，当前报告包也保留这一区分及原请求证据。

A35面板将金额标为“CLI配置阈值”，说明单次调用可能超出、现金结算未知；达到或超出阈值、费用尚未核对的停止提示独立展示，不被无候选、旧内核或名额耗尽提示遮住。原请求逐条显示CLI报告估值，失败和回答无效的合法报告金额也计入累计；未启动请求不显示为零费用。此次只改展示，沿用原grant、请求与发送门禁。

2026-11-03的独立18792验证工作台已用浏览器上传归档hiMSC输入，明确运行两次模型选择并完成主质量/分组画像，CLI路由均报告deepseek-flash，累计估值0.048195USD；原ID页面核对新增CLI和行动均为0。该轮证据在 `runs/a27-workbench-model-20261103/`，数值、报告身份与视觉验收以该轮最终记录为准；A27当时的核心报告仍需配套host日志读取外部用量，原工件不改写。

## A38：实际子代理选择接回原项目

原hiMSC v31没有合法候选时，宿主在准备前停止，没有消费模型名额。随后将作者归档管线的静态导出配置及明确的派生出处登记到同一项目v32，形成一个真实来源候选；原生模型仍0、本地2/2、来源4/8。该项目此前没有host grant，按用户已有子代理授权首次固定为一次delegated决策，不传CLI可执行文件，不变更软件项目已用尽的grant或历史费用。

本轮实际协作子代理从冻结prompt/context独立返回execute及三项原引用。原响应字节直接由`import-response`保存，`consume`经原控制器完成来源读取至v36、来源5/8；下一context含新设置并无新候选。原prepare/import/consume/登记ID核对零新增。一次模型选择与一次来源执行不表示两次模型连续成功，也不表示编号、零值或ALP资格已确认。

当前8页报告嵌入该请求的原context/prompt/response/proposal及控制器结果，30附件逐字节核对，四HTTP下载与发布文件一致。协作工具真实派发与回答交付证据单独保存；核心导入声明仍`execution_verified=false`，内部模型/次数/费用unknown，不能靠导入文件自证执行或用CLI估值0表示全部模型免费。完整结果见[A38证据](../runs/a38-delegated-source-20261104/README.md)，领域发现见[hiMSC核对](himsc-source-audit.md)。旧服务未重启，报告由当前有限本地命令生成并通过原18793提供下载。

## A63 真实子代理计划修订与后轮接续

2026-11-05，公开diabetes数据的442行、11列按原`sex`编码声明分组，作为数据质量与计划修订实例。三条实际`collaboration.followup_task`决策的原JSON由Host正常捕获，依次完成以下接续。

| 原请求ID | 实际反馈与结果 |
|---|---|
| `a63-initial-plan` | 子代理提出初始计划，保存建议后由网页明确采用为计划v1 |
| `a63-feedback-plan` | 一次真实质量检查后，子代理读取原observations，针对机械检查未见标记、当前无候选的反馈，建议转向核对来源并引用真实行动，网页采用为计划v2 |
| `a63-follow-revised-plan` | 本机`sklearn.datasets._base`的`load_diabetes`原文1042—1161行登记后，子代理按计划v2选择来源候选，原控制器完成实际读取 |

最终项目state v11，计划版本为1与2，本地方法1/2、来源1/8、Host请求3/3、原生模型调用0。原ID的prepare、consume和adopt重放核对后，核心状态与用量保持一致。后续context带计划v2和一条实际来源证据。

本轮报告正常导出四份文件，6页PDF均已逐页查看，展示当前计划、修订及模型请求用途，并保留13份Host原件。四个正常报告下载均HTTP200，与manager导出逐字节一致。原模板第3页留白较多，完整内容可读报告JSON。本机验证记录按忽略规则保存。

桌面1440×900与手机390×844共8张真实截图已逐张查看，覆盖全页、计划、展开的已采用提案和X6画布分段。两端均无页面横向溢出，五页导航逐页访问正确，当前访问pageErrors0、httpErrors0。运行app.js及CSS与构建文件一致，前端format、Lint和类型检查重跑通过，format检查34份文件、改动0份。A63已通过[PR #8](https://github.com/1263-ux/auto-research-agentarts/pull/8)合并，共享主线为`23b6d91`。

协作会话记录可以核对这三次实际派发。Host导入仍保留`execution/model/usage unverified`声明，内部推理次数、模型身份和费用为unknown，现金结算unknown及原5元上限保留。此次计划用途实际采用子代理，新增plan用途的CLI传输尚待单独实跑。

本轮给出了研究计划建议、采用与按修订计划继续的真实轨迹。配方或策略版本的验证、采用或回退及RSI后轮管理由队友的`recipe_improvement`模块继续接线。目标量表、变量编码与样本独立性按数据来源的实际证据解释。

## A64 配方修改提案与允许工具验证

2026-11-05，复用A62已有构造四行工程项目，显式兼容升级后保留原预算及旧行动，登记团队自写工程运行说明。一次实际协作子代理请求`a64-recipe-change`提出完整候选v2，提案适配保存原回答，验证适配按显式允许的方法和来源收据，经原控制器实际读取该来源1次。冻结baseline为wait，候选为execute，验证completed，`selection_changed=true`。

最终state v13，本地方法1/2、来源1/8、Host 1/1、原生模型调用0。原ID的propose与validate重放后，核心及Host状态均未改变，A63原v11全状态逐值一致。报告正常导出4文件，5页PDF已全部实际查看，部分页沿原模板留白较多。7份Host原件包含真实`validation-input.json`与`validation-result.json`，本机验证记录按忽略规则保存。

页面验收使用CLI关闭的独立18795预览。桌面1440×900与手机390×844共8张全页、计划、配方记录与画布分段截图已实际查看，两端无页面横向溢出，键盘展开和收起原记录通过。当前A64项目五页导航已逐页访问，选中态及URL正确，pageErrors0、httpErrors0。四报告HTTP200，与manager导出逐字节一致，运行JS及CSS与本次构建一致。A64已通过[PR #9](https://github.com/1263-ux/auto-research-agentarts/pull/9)合并，功能合并提交为`5e50037`。

实际模型来自协作派发，Host供应商声明仍未核验，内部模型及费用unknown，plan和recipe用途的CLI均未实际调用。原回答的`validation_plan`建议采用后再执行，实际验证独立按显式allowed方法与receipt运行在采用决定前。该文字保留为模型建议，执行权限由调用方提供，原回答未改写，可作为后轮反馈。

这次结果供队友直接接入`run_improvement_round`，复用已保存的完整候选和验证结果。外环仍需保存采用或回退决定、有效版本与后轮状态。后续接线沿本次原ID取回结果，再按新的实际问题继续。

## Limitations

A67使用明确标记的工程夹具验证意见保存、提示组装和报告，真实用户理解反馈仍须独立取得。夹具4页PDF已实看，第2页沿旧模板留白较多，完整意见保留在报告JSON与input中。

Host及工作台入口支持候选选择、研究计划建议和明确采用。模型解释、来源声明与工具结果按领域证据核对，`scientific_validation`保持false。CLI报告的token、模型标签和USD估值按原报告口径保留，现金结算及旧历史费用继续记录实际已知或unknown。`runs/`证据在本机忽略目录，共享时按资料许可提供获准分发的原件与说明。

A35未重启18791服务：该进程能读取新静态页面，Python后端仍缓存旧实现，不能据页面变化认定A34费用修复已经加载。A34真实记录及费用补记前快照的只读界面投影只覆盖超阈值、未知费用的显示，投影阻止所有POST，不代表线上请求执行或恢复验证。
