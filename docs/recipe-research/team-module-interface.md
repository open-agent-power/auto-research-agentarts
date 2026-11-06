# 配方与RSI最小接口约定

更新于2026-11-05。起步PR确认这些对象能承载一轮真实改进，字段按实际使用收敛。主开发和队友分别实现自己拥有的部分，长期任务和PR接续按[持续开发任务书](team-module-handoff.md)推进。

## 配方知识

方法卡采用`research-method-card-v1`起步格式，包含`id`、`version`、`question`、`rationale`、`scope_match`、`method_refs`、`applicability`、`evaluation`、`feedback_branches`和`sources`。条件、评价和分支是可读方法知识，[JSON模板](../../examples/research-method-cards/feedback-driven.example.json)提供完整示例。

现有`research_recipe.py`增补`parse_method_card(raw)`和`match_method_card(card, context)`。解析复用既有JSON处理，关联依据实际context范围、方法和评价引用，返回卡片身份、版本、`matching_candidate_ids`、可读理由和完整说明。宿主阻断、范围不匹配或候选缺失时返回清楚状态。

现有`compile_recipe`、`research-recipe-v1`和选择提案继续服务已有调用。实际执行参数由宿主候选提供。

2026-11-06方法卡基础轮已由[PR #19](https://github.com/1263-ux/auto-research-agentarts/pull/19)合并，提供`parse_method_card/validate_method_card/match_method_card`及原编译CLI的互斥`--method-card`模式，返回`research-method-card-match-v1`并只写`match.json`。精确字段与实际演示见[方法卡设计](recipe-design.md)。RSI外环接续使用[A64材料和下一份PR要求](a64-rsi-handoff.md)。

## 外环的四份输入输出

| 对象 | 最少内容 | 提供方 |
|---|---|---|
| 当前版本 | 配方或策略身份、版本、内容与适用范围 | 配方模块与当前项目 |
| 反馈轨迹 | 当前问题、实际执行和结果、具体问题、工件引用 | 原项目与主开发的轨迹适配 |
| 候选修改 | 基于哪个版本、依据哪条反馈、改什么、预期改善什么、怎样验证 | 外环调用模型或开发Agent提出 |
| 验证与采用记录 | 相关检查、实际结果、保留或回退、理由、有效版本与下一步 | 验证入口与外环 |

首版可保存为JSON和可读摘要，复用现有本地存储。先让一轮真实闭环完成，再按出现的问题补字段。

## 一轮改进

新模块`recipe_improvement.py`建议提供`run_improvement_round`，调用入口为`run_recipe_improvement.py`。一轮按以下顺序执行。

1. 明确本轮要改善的一项问题与判定方式。
2. 调用已有模型入口或开发Agent取得候选，保存实际回答及原版本。
3. 形成可运行候选，在明确工作目录执行与改动相关的必要验证。
4. 比较原版与候选在本轮问题上的实际结果，记录采用或回退。
5. 输出当前有效版本、本轮结果和下一轮问题。

主开发提供`propose`和`validate`两项接入能力。`propose`接收当前版本、轨迹和目标，返回实际回答及候选。`validate`接收候选、原版和本轮目标，执行允许的检查并返回结果。队友负责外环状态、版本和连续推进，主开发连接模型传输、原项目工具和资源配置。

首版使用普通函数参数连接这两项能力，保持直接调用。构造返回用于模块开发，真实运行使用实际接入能力。

### 主开发的配方改进适配接线

主开发已在[recipe_improvement_adapter.py](../../src/autoresearch/recipe_improvement_adapter.py)提供以下函数入口。A64已取得一次真实子代理候选和允许来源读取结果，桌面及手机截图、五页导航与四报告下载均已实际核对，运行JS及CSS与本次构建一致，功能已通过[PR #9](https://github.com/1263-ux/auto-research-agentarts/pull/9)合并。队友继续实现`recipe_improvement`外环，消费提案和验证记录，管理版本、采用或回退及连续轮次。

```python
propose_recipe_change(
    current_version, trace, goal, *, workspace, request_id,
    decision_limit, cli_budget_usd, reason, provider="delegated",
    executable=None, response_file=None,
)

validate_recipe_change(
    candidate, original, goal, *, workspace, request_id,
    allowed_methods, allowed_receipts,
)
```

`trace`须为本次冻结的完整实际`research-plan-context-v1`，首次由当前项目按原配方need构建，后续调用沿用原请求context中的`research_context`。`current_version`传原生`research-recipe-v1`，`goal`传本轮有界改进目标。Host以`purpose=recipe`复用原累计grant，consume仅保存`proposed`。子代理首次调用返回`prepared`，按`context_ref/prompt_ref`取得原上下文和提示。使用同一ID传入`response_file`后，适配导入原回答并consume，合法提案进入`proposed`。CLI分支使用原传输，`response_file`仅用于子代理。

提案适配返回`recipe-change-proposal-result-v1`，字段为`request_id/status/candidate/context_ref/prompt_ref/response_ref/scientific_validation`，其中`scientific_validation`为false。`prepared`时`candidate`为null，`proposed`时为完整的`recipe-change-proposal-v1`，包含`schema_version/context_sha256/provider/candidate/reason/feedback_action_ids/expected_improvement/validation_plan`。内部`candidate`才是原生配方，保留原`id/scope_match/need`、版本加1、`on_no_match=wait`。方法与`evaluation_ref`必须成对来自冻结conditions，反馈行动ID必须指向实际完成或失败的记录。

调用`validate_recipe_change`时，`candidate`参数传提案结果中的完整`candidate`对象，`original`传原配方，`goal`沿用原目标，`request_id`沿用同一Host请求。适配校验原回答、提案与冻结输入一致，只读编译baseline和候选并比较选择决策，再通过原控制器最多执行候选一步。`allowed_methods`为本轮明确允许的方法ID，`allowed_receipts`为明确允许的来源收据身份，首次验证后沿原ID固定这些权限。原项目本地方法与来源用量继续累计。

返回`recipe-change-validation-v1`，包含`request_id/status/baseline_decision/candidate_decision/selection_changed/controller_outcome/artifact_refs/scientific_validation`。原Host请求目录保存`validation-input.json`与终态`validation-result.json`，completed、waiting、failed或rejected结果可重放，unknown保持可核对与恢复。`selection_changed`记录选择决策差异，外环依据实际结果决定采用或回退。以`proposal_result`表示提案适配返回值时，验证入参为`proposal_result["candidate"]`，决定采用后保存的新有效配方为`proposal_result["candidate"]["candidate"]`。Host用途与CLI参数见[接线说明](../host-model-selection.md#配方改进提案与验证接线)。

### 队友从A64结果继续

A64复用已有构造四行工程项目，经一次实际协作子代理请求`a64-recipe-change`得到完整候选v2。冻结baseline为wait、候选为execute，显式允许的方法和来源收据使原控制器读取团队自写运行说明1次，最终state v13，本地1/2、来源1/8、Host 1/1、native 0。原ID提案与验证重放均无新增，A63原v11全状态一致。

队友将保存的完整提案及`validation-result.json`接入`run_improvement_round`，记录采用或回退、有效版本和下一轮问题。原ID可以取回这次已完成结果。模型原`validation_plan`建议采用后执行，实际验证已独立按显式权限运行在采用决定前，原回答保留，可把这处顺序差异作为后轮反馈。Host7份原件、5页报告和页面证据范围见[A64记录](../host-model-selection.md#a64-配方修改提案与允许工具验证)。

主开发已整理只读材料包，原件、派生视图和两层candidate结构见[A64接续说明](a64-rsi-handoff.md#先取得材料)。包内`derived/proposal-result.json`按既有适配返回字段导出，采用状态由待实现的外环记录。在线回调与原项目写入继续由主开发接入。

## 连续推进与接续

入口支持单轮和在本次任务范围内的连续轮次。每轮读取前一轮结果后选下一项改进，沿当前有效版本继续。达到目标、用完本轮资源、缺少输入或有未决执行时保存状态，说明原因与接续位置。

同一轮重启时读取已保存阶段，已完成的候选生成和验证可以复用。执行状态未知时先核对原执行身份。一次候选被拒绝可成为后轮输入，后续修改说明怎样回应前轮结果。

配方和策略通过验证后产生新有效版本。模块代码建议作为同一目标下的开发任务，按文件归属和仓库流程落地，研究项目保留采用的版本与结果关系。

## 首轮样例与验证

随源码提供的[表格context及改进模板](../../examples/recipe-improvement/README.md)标记为构造数据，用于开发读取、关联和状态流转。既有方法身份采用`data.tabular-quality-audit`、`data.grouped-quality-profile`和`research.source-selection`及实际评价引用。

起步PR交配方与最小对象，后续PR以构造输入核对采用、回退和接续。联合验收使用真实模型和工具入口，记录一次实际改进及随后一轮怎样利用它。实例可替换，接口围绕问题、轨迹、候选和结果保持通用。此后持续根据实际轨迹扩展方法、修正策略并改进使用效果。

## 双方交接

队友提供模块调用方式、输入输出示例、已验证范围与待接入能力。主开发提供真实轨迹、模型调用方式和允许检查的执行入口，双方用一个实例完成整合。

每份PR交回本轮问题、改动、实际结果、剩余接入点和下一项。合并后从最新主线继续队列中的下一项，新增接口按实际调用收敛并同步对应说明。

### 主团队提供的真实轨迹与Host接线

主团队已提供`research_plan_proposal.py`的`build_context(project)`，返回`research-plan-context-v1`。其中`selection_context`是原控制器的完整实际context，`feedback`来自原项目已保存的分析和来源行动，保留`action_id/request_id/method_id/status/observations/next_decision/failure/artifact_ref`。队友可以据此关联当前问题、原观察和工件，形成外环输入。

该模块还提供`build_prompt`、`parse_host_response`、`build_proposal`和`validate_proposal`。Host的`prepare/advance --purpose plan`可以取得计划候选，子代理分支使用原请求的`context.json/prompt.json`，经`import-response/consume`保存为`proposed`。CLI分支沿现有传输取得原回答。计划与选择请求共用同一累计grant。

计划候选包含`plan`四项正文、`reason`、`feedback_action_ids`和`expected_improvement`。主团队通过`adopt-plan`将已保存建议采用为研究计划修订，或通过`reject-plan --reason`保留拒绝决定。项目过期时保留原建议与`stale`状态。入口说明见[Host计划建议](../host-model-selection.md#根据真实反馈建议研究计划)。

这条链提供当前研究计划的模型候选、真实反馈引用和采用记录。队友负责的`recipe_improvement`仍需连接配方或策略版本、对应验证、保留或回退以及后轮接续，把实际候选和结果映射到外环对象。计划修订记录可作为一份真实轨迹输入。

主团队已取得公开diabetes实例的一条真实轨迹。三次子代理决策依次提出初始计划、读取真实质量反馈后提出修订、按已采用的v2计划选择来源，原控制器完成来源读取。网页采用了计划v1和v2，6页报告已逐页查看，原ID重放后核心状态及用量一致。队友可将这条轨迹作为外环输入，继续实现配方或策略候选的验证、采用或回退与后轮管理。具体范围见[A63记录](../host-model-selection.md#a63-真实子代理计划修订与后轮接续)。

桌面1440×900与手机390×844的8张全页及分段截图已实际查看，覆盖计划、已采用提案和X6画布。两端无页面横向溢出，五页导航访问正确，pageErrors0、httpErrors0。四个正常报告下载HTTP200，与manager导出逐字节一致，运行app.js及CSS与构建文件一致。A63已通过[PR #8](https://github.com/1263-ux/auto-research-agentarts/pull/8)合并，共享主线为`23b6d91`。

实例任务范围是数据质量与计划调整，目标量表、变量编码和样本独立性按来源声明及实际证据解释。Host导入声明保留未核验的执行、模型和用量字段，协作实际派发另有会话工具记录。新增plan用途的CLI传输仍待单独实跑，配方RSI外环仍由队友接线。
