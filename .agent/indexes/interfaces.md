# 接口索引

新增CPU经验本机CLI与显式双schema分派；原experience-import/status/resume兼CPU原包，旧Ridge validator保持严格。binding_validation区别数值复核、实际原包≤4MiB与同ID资格不变，见[字段与边界](../../docs/cpu-project-experience.md)。

新增只读 `GET /api/project/fixed-protocol.json`，绑定原project/snapshot，直接核验三类固定CPU原source并返回≤128KiB摘要，不依赖报告或行动、不执行研究。字段、省略内容与错误见[固定协议接口](../../docs/fixed-cpu-protocol.md)。

同两条保存GET新增独立saved-relevance-*-v1响应和6字段contract；详情原grades、missing_doc_ids、original_grade=null语义与旧citation隔离，选择器/上限/快照门禁保持。见[相关性保存记录](../../docs/saved-retrieval-reader.md#相关性保存记录)。


新增GET `/api/project/retrieval-adverse.json`和`retrieval-query.json`，严格绑定project_id/snapshot_ref/action_id，读取前后核当前项目；分页/查询参数、1MiB响应及错误边界见[保存查询接口](../../docs/saved-retrieval-reader.md#只读http接口)。不接受客户端路径或研究执行参数。

后续Host plan／recipe可明确带`saved_materials`数组，按诊断action／结果SHA读取完整groups／folds／rows，非空生成v3独立`supplied_materials`，默认v2与旧prompt保持。CLI prepare／advance及只读preview、plan HTTP与GET预览共用校验；same-ID先返原封存记录，不能更换字段或扩grant。完整最终context仍64KiB，超限整次拒绝。Airfoil此前的实际[等待与全文未读记录](../../docs/research/airfoil-noise-study.md#两份首次计划与实际等待)不追溯改写，见[新入口](../../docs/host-model-selection.md#选择后续输入中的保存字段)。

两个`data.saved-oof-*-diagnostics`候选使用原参数`based_on_action_id`／`based_on_result_sha256`指向明确原CV，当前设计冻结于原请求。新obs.kind为`saved_oof_diagnostic`，`source_check/source_ref`区别源CV与本次0fit行动；完整结果`result.diagnostic`。模型小组表全量、大表明确整表引用；新`baseline_decision.conditions_ref`仅复用已提供且完全相同的条件，旧Host／独有recipe条件不改。见[契约](../../docs/research-design.md#原生保存误差诊断)。

方法案例CLI `import-project`及`ProjectExperienceMemory.import_project`可显式带`--parent-action-id`／keyword-only `parent_action_id`。新配对protocol的scope绑定父子两结果，summary.observation.saved_parent_comparison投影紧凑全量对照；旧单结果字段保持。完整封套仍4MiB，不可比直接拒绝，见[接口语义](../../docs/project-experience.md#显式保存父版对照)。

原始训练绑定可带非空`input_transforms={原训练列:"log1p"}`，与`input_basis`互斥。协议保持`input_basis`／`model_input_terms`两个映射字段，kind为log1p时保存全部source_columns和按原顺序transformed_columns，维度不变；仍用`comparison_kind="fixed_input_basis"`及原`saved_parent_mae`。工作台明确选列、保留无效草稿，域x>-1在原需求预检及执行前验证，见[字段与边界](../../docs/research-design.md#固定log1p原输入变换)。

保存OOF诊断CLI可明确增加`--within-group-column <原训练数值列>`，API参数为keyword-only `within_group_column=None`。只在请求时增加`within_group`；该列与`--column`输入画像分别选择，默认输出原样。声明组、固定其他训练输入和单保存折条件不足时保留组与原因，见[相邻变化](../../docs/research-design.md#同组原输入的相邻变化)。

只读CLI `inspect_saved_oof.py --workspace <项目> --action-id <已完成Ridge行动> --column <原输入> --output <新目录>`导出`saved-oof-diagnostics-v1`和阅读用Markdown；列可重复／省略，结果保留原行动／设计／工件与全部覆盖，错误沿ResearchError退出。输出在项目外，不向API、Host或当前报告自动回填，见[使用与语义](../../docs/research-design.md#单个已保存验证的只读诊断)。

新`research-plan-context-v2`可捕获`prediction_ranges=[{action_id,check,summary}]`，仅当前设计已完成`random_cv/group_cv`。条目关联原反馈／工件；summary为保存OOF范围或null，字段缺失/null与真实零计数区分。配方外层schema保持，原obs不改；既有无字段v1/v2 prompt不追加说明。`GET /api/project/plan-context.json`继续只读，完整context仍限64KiB，见[字段语义](../../docs/host-model-selection.md#根据真实反馈建议研究计划)。

选择context的条件新增可选`budget_cost={local_tool_calls,evidence_reads,estimator_fits}`；前两项为非负整数，拟合可null。readiness有捕获值时为`plan-readiness-v2`并含`method_budget_costs`，无值旧v1不变。报告`execution_conditions`为当前，`plan_reviews`为原Host冻结条件，完整依据在`input.selection_context`；见[字段与语义](../../docs/method-budget-costs.md)。

跨项目方法案例通过`GET /experiences`读取，`POST /experience-import`、`/experience-status`明确导入或改变本地资格，`/experience-resume`仅恢复原manager请求。前缀均为`/api/local-workbench`；原选择／计划／配方回答协议不变，见[案例接口](../../docs/project-experience.md#接口与成果)。

`POST /api/local-workbench/plan-fact-check`精确接收`project_id/host_request_id/claim`，返回`plan-fact-check-v1`只读预览，不进入命令账本。claim绑定原字段Unicode码点span、quote、双方action及check、MAE方向或指标数值。结果区分支持/矛盾/不可核对，保留提交者语义映射与选句范围；原4字段plan、Host采用及预算不变。CLI为`check_plan_fact.py`，见[完整合同](../../docs/plan-fact-check.md)。

原始训练声明可增加`input_basis="univariate_cubic"`（必须一个原CSV输入），资源可增加`comparison_kind="fixed_input_basis"`（raw且明示parent）。结果协议保存`input_basis`描述和`model_input_terms`；对照增加比较类型及`changed_protocol_fields`，其余严格门不放松。`assessment`与报告`design_assessment`共用`saved_parent_mae`范围及真实候选行动配对。详见[研究设计](../../docs/research-design.md)。

`feature_comparisons[].input_profiles`包含列、分组方式、覆盖数、每桶指标与逻辑行号。目录与报告使用同一捕获source核对目标/坐标后派生；不可比较不输出局部交集。工作台输入列切换只读内存数据，JSON保留所有列，Markdown/PDF展示候选首列，详见[按输入描述误差](../../docs/research-design.md)。

研究设计目录与报告JSON的`feature_comparisons`保留两侧资源/项目设计版本和行动引用。仅明确父子版本、同协议同评价集合输出差值与负预测计数；不可比较保留`reason_codes`且不输出指标。工作台显示实际配置的检查与已保存指标，不为仅`group_cv`补造随机或负控结果，详见[研究设计](../../docs/research-design.md)。

资料登记接受`.html/.htm`与`text/html`，使用原始HTML的`text_lines`坐标，标签不执行、不渲染；原件下载保持`application/octet-stream`附件，详见[来源用法](../../docs/local-workbench.md#在同一项目登记资料再明确读取)。新计划context为v2，历史决定、来源全文与资源正文有明确原账本/工件引用，数值、协议、范围、用量及完整sealed selection context保持；另供应严格`saved_comparisons`，详见[计划执行条件](../../docs/host-model-selection.md#计划执行条件)。

`LocalWorkbench.model_view`新增独立`plan_reviews=[{request_id,assessment}]`；报告JSON提供同名字段，Markdown/PDF显示冻结条件。`assessment`为`plan-readiness-v1`，含项目/版本/快照/context身份、`execution_status`、三类`remaining_budget`、`available_actions`、`blocked_methods`与`blockers`，科学解释固定需审阅。新plan提示附带同一`execution_conditions`，原计划回答字段及采用/拒绝协议不变，见[计划执行条件](../../docs/host-model-selection.md#计划执行条件)。

[研究设计与保存预测核验](../../docs/research-design.md)通过`GET /api/local-workbench/designs`读取目录与实际验证，`design-bind`冻结项目/资源/预测列，`design-improve`从反馈生成版本，`design-import`导入已知检查协议。执行复用原`advance`，JSON/Markdown/PDF报告包含原设计和实际计算。

`run_recipe_improvement.py sequence --manifest --output [--max-rounds 1]`消费1至32项固定的同类保存输入，输出`recipe-improvement-sequence-result-v1`、有效版本、前轮结果、`next_entry`和不可变停点路径。模式为`fixture/saved-host/saved-export`，各项字段与四种停止原因见[队列合同](../../docs/recipe-research/rsi-delivery.md#有界保存证据队列2026-11-08)。不派发请求或在线采用，原单轮CLI不变。

`recipe_improvement.load_saved_export`与CLI `saved-export --evidence-root --spec`只读核对A64完整导出，不需要SQLite；结果类别为`saved_export_validation`，不能绕过项目采用入口对`saved_host_validation`的要求。`next-input --output --round-id`读取最新有效版本／前轮结果／下一问题，明确等待新反馈，不派发任何请求。原`saved-host --resume`及`input_path`保持，见[离线补充](../../docs/recipe-research/rsi-delivery.md#队友收到离线包后的补充2026-11-07)。

`POST /api/local-workbench/continue`接收冻结的计划／行动范围，`GET /api/local-workbench/continue/<id>.json`与`describe.continuations`投影`phase/plan_ref/batch_ref/steps/stop`；采用后仍以首次版本和全部原body继续。新计划在服务启用CLI时取得建议，未启用时准备delegated，首次提供方／路径冻结。只对精确关联计划放行原model-resume/adopt/reject，模型行动沿原CLI批次及grant；含模型的网页接续使用420秒等待窗口。完整字段见[继续研究接口](../../docs/host-model-selection.md#继续研究的计划与行动阶段)。

RSI `saved-host --resume`沿原Host请求和同round-id读取后续回执；`read_improvement_round`返回最新完整结果，新增`read_improvement_snapshot`提供原生input及其路径。CLI额外`input_path`用于选择最新stage文件交给既有工作台核对／采用，原result schema保留，见[保存和接续](../../docs/recipe-research/rsi-delivery.md#保存和下一轮)。

`data.numeric-association`复用原方法选择、控制器、行动工件与报告接口，参数为已保存质量前序的`based_on_action_id/based_on_result_sha256`。结果为`numeric-association-v1`，观察为`numeric_association`，含`overall/groups/incomplete_group`及成对`n/excluded/pearson_r/reason`。声明目标须在数值列中并至少有一项其他数值列，字段口径见[数值关联](../../docs/numeric-association.md)。

[单轮RSI入口](../../scripts/run_recipe_improvement.py)提供`fixture --input`与`saved-host --workspace --request-id --spec`，共用`--output/--round-id/--previous-round-id`。通过`recipe_improvement`消费现有适配结果，输出`recipe-improvement-result-v1`、理由与有效原生配方。后轮必须匹配前轮有效版本；saved-host使用原reader核对保存账本，不派发模型／工具。字段、pending和验收边界见[RSI交付](../../docs/recipe-research/rsi-delivery.md)。

项目采用入口为同源CSRF保护的`POST /api/local-workbench/recipe-preview`（`project_id/input`）与`recipe-adopt`（`request_id/project_id/expected_state_version/input/reason`）。前者只读核对原Host与控制器原件，后者保存completed的keep／revert及有效配方。`GET /api/local-workbench/recipes`增加`effective_recipe`，`GET /api/project`增加`recipe_revisions`。默认next／advance消费该版本，原ID重放保留冻结决定，接口用法见[工作台](../../docs/local-workbench.md#核对外环并保存有效版本)。

方法卡新增只读`parse_method_card/validate_method_card/match_method_card`，现有编译CLI新增互斥`--method-card`，只写`research-method-card-match-v1`的`match.json`。按原sealed context的范围与方法／评价精确关联，返回候选、条件、理由、缺口及未核验说明；不改原配方／proposal格式，不执行方法。完整字段与CLI结果见[方法卡设计](../../docs/recipe-research/recipe-design.md)。

这是现有入口导航，不是新 API 规范。统一项目命令和研究Observation见[研究契约](../../docs/architecture/research-contracts.md)，**尚未实现通用 create/start/resume REST 接口**。

新项目/运行/行动对象及命令边界见[研究契约](../../docs/architecture/research-contracts.md)，依赖关系见[底层架构](../../docs/architecture/foundation.md)。同一项目已有已登记白名单方法的本地Python/CLI实现和只读HTTP投影。显式启用的本地写入、模型和计划操作见[本地工作台](../../docs/local-workbench.md#接口与只读边界)。

## 记录研究者意见

`POST /api/local-workbench/feedback`的精确body为`request_id/project_id/expected_state_version/author/comment/next_step/action_id`。`author`自填且非空、最多120字，`comment`非空且最多6000字，`next_step`可为空文本、最多4000字，`action_id`为null或原项目既有action ID。

manager与core的`record_feedback`保存独立`researcher_feedback`。记录恰含9字段，为`id/request_id/based_on_state_version/plan_version/author/comment/next_step/action_id/content_trust`。id为`feedback-`加原request ID，`plan_version`可为null，`content_trust`为`unverified_researcher_statement`。state版本加1，沿计划同等版本、代码及未决请求门禁处理，原ID和相同内容重放使用原记录，资源用量沿原账本保留。响应为`local-workbench-command-v1`，command为`record_feedback`，status为`completed`，`feedback`携原记录，响应信封另含`replayed`。

sealed selection context的可选`researcher_feedback`字段保留这些原记录，后续plan和recipe提示按未核验人类陈述引用，`feedback_action_ids`继续限定真实工具action。原Host封存context保留，报告包含意见和信任标记。A67工程夹具已核对真实保存、回执丢失后只读确认、原ID重放、下一plan提示组装及四报告下载，模型/工具/Host请求0。使用说明见[工作台](../../docs/local-workbench.md#记录研究者意见)。

## 模型建议研究计划

`GET /api/project/plan-context.json`只读返回`research-plan-context-v2`，含完整原`selection_context`、保留精确原件定位的行动反馈投影与严格`saved_comparisons`。旧v1封存记录不重写；`research_plan_proposal.py`提供`build_context/build_prompt/parse_host_response/build_proposal/validate_proposal`，`run_host_selection.py prepare/advance --purpose plan`使用同一Host累计grant。

工作台接口沿原本地写入、会话和活动项目检查处理，命令采用既有信封。

| 入口 | 精确请求字段与用途 |
|---|---|
| `POST /api/local-workbench/model-plan-advance` | `request_id/project_id/expected_state_version/decision_limit/cli_budget_usd/reason`，沿固定CLI取得并保存计划建议 |
| `POST /api/local-workbench/model-plan-adopt` | `request_id/project_id`，明确采用原请求保存的计划建议 |
| `POST /api/local-workbench/model-plan-reject` | `request_id/project_id/reason`，保留原建议及拒绝原因 |

计划consume进入`proposed`，采用后`applied`且`outcome.kind=plan_revision`，拒绝后`rejected`。采用或拒绝已保存建议使用本地操作权限，服务未启用CLI进程时仍可处理。新计划请求与selection共享原`decision_limit/cli_budget_usd/reason`，原ID重放、过期状态与原始回答继续沿Host记录管理。用法见[Host计划建议](../../docs/host-model-selection.md#根据真实反馈建议研究计划)和[工作台计划建议](../../docs/local-workbench.md#模型建议与采用)。

准备selection请求要求存在合法候选，plan请求在无全局阻断时可基于真实反馈处理空候选情形。A63子代理实例已按实际质量反馈修订计划并在网页采用v2，下一次选择带该版本完成来源读取。桌面及手机8张截图、五页导航与四报告下载身份已核对，运行静态资源与构建一致，已通过[PR #8](https://github.com/1263-ux/auto-research-agentarts/pull/8)合并至共享主线`23b6d91`。原ID重放、CLI未实跑及RSI待接线范围见[A63记录](../../docs/host-model-selection.md#a63-真实子代理计划修订与后轮接续)。

## 配方改进提案与验证

Host支持`purpose=recipe`及`prepare/advance --purpose recipe --recipe <JSON文件> --improvement-goal <文字>`，与原grant累计记账，consume保存`proposed`。[协议模块](../../src/autoresearch/recipe_change_proposal.py)冻结实际`research_context/current_recipe/improvement_goal`，校验候选保留原配方id、scope_match和need、版本加1，方法与evaluation_ref成对来自冻结conditions。

[适配模块](../../src/autoresearch/recipe_improvement_adapter.py)的`propose_recipe_change`返回`recipe-change-proposal-result-v1`，其candidate为完整`recipe-change-proposal-v1`，内部candidate才是原生配方。`validate_recipe_change`传完整提案与同一Host请求ID，比较冻结baseline/候选决策，按显式allowed_methods和allowed_receipts经原控制器最多执行候选一步。验证输入与终态结果保存于原请求目录，unknown沿原ID核对恢复。

A64已在已有构造项目通过一次实际子代理候选v2和一次允许来源读取，baseline wait、候选execute，原ID提案与验证重放无新增。队友复用已保存结果接`run_improvement_round`，继续负责`recipe_improvement`外环的版本、采用或回退和连续轮次。桌面与手机截图、五页导航及四报告下载身份均已实际核对，运行静态资源与本次构建一致，功能已通过[PR #9](https://github.com/1263-ux/auto-research-agentarts/pull/9)合并。函数签名与返回字段见[适配约定](../../docs/recipe-research/team-module-interface.md#主开发的配方改进适配接线)，实际运行范围见[A64记录](../../docs/host-model-selection.md#a64-配方修改提案与允许工具验证)。

## 配方验证只读投影

`GET /api/local-workbench/model`在`local-host-model-view-v1`中提供独立`recipe_validations`数组。`records`承载Host原请求，验证投影逐项使用`recipe-change-validation-view-v1`，共7个字段，为`schema_version/project_id/request_id/status/input/result/error`。reader入口为[read_recipe_validation(workspace, request_id)](../../src/autoresearch/recipe_improvement_adapter.py)，读取仅投影已保存证据。

状态范围为`not_started/pending/recovery_required/unknown/completed/waiting/failed/invalid`。完成投影需要原Host提案、两个validation sidecar与原控制器结果相互对应。缺失回执或证据不一致时，状态反映当前未收口事实。研究页已展示验证时原版及候选选择、实际工具状态和JSON下载，invalid投影隐藏完成标签与比较。采用决定由队友外环单独保存，本轮CLI不代表页面已整合采用操作。

一项reader定点回归、前端format、Lint、类型检查及构建通过。桌面及手机8张最终截图、JSON实际下载与API一致性、invalid客户端夹具及A63/A64切换均已核对。使用说明见[工作台](../../docs/local-workbench.md#主工作台只读展示)和[Host读取边界](../../docs/host-model-selection.md#工作台读取验证记录)。

## 当前项目的三域只读入口

- [project_workbench](../../src/autoresearch/project_workbench.py) / [serve_project_workbench.py](../../scripts/serve_project_workbench.py) 以`--workspace`挂载同一保存项目；材料/软件省略`--bundle`进入独立项目页，P02必须给匹配封存迭代并保留原五页。默认18785，不改变18784选择；`--check`只核验，不启动服务。
- GET `/api/project`返回`active-project-view-v1`，含`primary_method/domain_scope`、真实行动/方法条件及`report.available/stale`；GET `/api/project/knowledge?need=...&point=...`只查已提取选区，point为clarification/design/preparation/interpretation；GET `/api/project/artifact/<action.id>`核对原工件身份后下载完整JSON。POST/PUT等研究写入为405。
- `--report <export-directory>`显式挂载同项目同`snapshot_ref`的报告，提供GET `/api/project/report.pdf`、`/api/project/report.json`、`/api/project/report.md`、`/api/project/input.json`。清单只允许这四文件，按SHA/大小核对；新导出同时绑定 `host_model_snapshot_sha256`。挂载时过期拒绝，运行后核心或宿主模型快照变化则拒绝下载，不回退旧报告。不挂载报告时相应下载不可用。
- [export_project_report.py](../../scripts/export_project_report.py) / [project_report](../../src/autoresearch/project_report.py) 用`--workspace/--output`导出新目录；稳定快照包含完整结果、失败/unknown、来源坐标及Base64输入，`registered_inputs.read_status=registered_unread`不计为来源提取。导出不恢复/执行研究；命令及数据/许可边界见[本地项目说明](../../docs/project-slice.md)。

## 封存 P02 只读工作台

- [workbench.py](../../scripts/workbench.py) 的 `select/status/serve` 与 [current_workbench](../../src/autoresearch/current_workbench.py) 的 `select_bundle/status/create_current_server` 选择并服务封存包；默认本机端口 18784。
- [snapshot_viewer](../../src/autoresearch/snapshot_viewer.py) 的 `load_bundle/create_server` 验证并冻结文件，提供 GET，例如 `/api/p02/research`、`/api/p02/iteration`、`/api/p02/pipeline-research`、`/api/p02/tabular-research`、`/api/p02/research-dossier.pdf` 和 `/api/p02/downloads`；POST/PUT/PATCH 等返回 405。可选资料缺失时相应路由不可用。
- [chemotopo_studio](../../src/autoresearch/chemotopo_studio.py) 是另一只读 P02 服务入口，按其实际参数挂载资料；不假设其每条路由与便携 viewer 相同。[P02 前端](../../frontend/src/p02-app.ts)读取这些快照。见 [离线工作台](../../docs/portable-workbench.md)。

## 其他服务与边界

- [c01_studio](../../src/autoresearch/c01_studio.py) 以 GET 提供 C01 研究及知识；配置 continuation 时，`POST /api/c01/continuation/step` 可推进该**特定**本地续算，带 CSRF/来源和请求检查；已完成研究与知识接口仍只读。不是 P02 通用研究提交接口。
- [studio](../../src/autoresearch/studio.py) 为历史原型，存在 `POST /api/questions` 和可选 `/api/local-demo/step`；能力和数据范围以该实现为准，不能代表当前封存服务可写。
- [runtime](../../src/autoresearch/runtime.py) 的 `create_app` 提供独立 AgentArts `/invocations` 适配；session 命名空间不是鉴权，也不代表平台接入已经完成。见 [AgentArts 说明](../../agentarts/README.md)。

## 原生模型与命令行

- [run_project_model.py](../../scripts/run_project_model.py) 的 `check-protocol --process-evidence <saved-process-directory>`只读核对原wire请求、response metadata/receipt/raw与native-show，检查SHA绑定并诊断工具/思考能力及原响应；不启动进程、调用chat、读取权重或改预算。实际request在show后、worker启动前预检tools及`thinking.values`；要求`think:false`却只支持`[true]`时拒绝`MODEL_PROTOCOL_INCOMPATIBLE`，可核实未派发时保留原prepared预留、不自动重发。旧A22响应仍invalid、累计1/1已用，诊断不恢复额度；`oneOf/const`丢失尚未证实，本轮不改builder。命令、证据与现金/AgentArts边界见[本地模型桥](../../docs/project-model.md)。
- [run_research_project.py](../../scripts/run_research_project.py) 提供 `create/status/step/resume`，JSON输出，失败退出码2；`--source`只由宿主创建时登记，`--method`从三类允许主方法中选择。`step`返回行动、观察和工件引用，完整结果在`envelope.tool_result.result`；`resume`只核对或提交已保存结果。见[本地项目说明](../../docs/project-slice.md)，不调用原生模型。
- 同一 CLI 的 `upgrade/evidence-task/attach-evidence/methods/knowledge` 接续旧项目；升级显式绑定旧代码身份，来源读取绑定任务及原字节，knowledge 只查已抽取内容的冻结 FTS。没有新增模型、付费或科学批准接口。
- `next --workspace ... [--need next_check]`只读返回真实条件/决定、`executable/blockers`；`advance --workspace ... --request-id ... [--expected-state-version ...]`通过[ProjectController](../../src/autoresearch/project_controller.py)冻结父请求后至多执行一个主方法或已登记未读来源。父ID及参数重放返回原选择/原子请求，即使原结果为waiting也不自动推进下一行动；改变参数冲突，后续推进使用新父ID。
- `register-evidence --workspace ... --request-id ... --bundle ...`捕获原字节/哈希并登记收据，有实际I/O但无提取行动/观察/FTS及读次数消耗；`read-evidence --workspace ... --request-id ... --receipt-snapshot-sha256 ...`只读取该已登记身份，使用原来源预算。原attach连续登记并读取，仍兼容；旧项目需显式upgrade，不能用升级绕过unknown或重置预算。可复制命令见[条件选择与来源接回](../../docs/project-slice.md#按条件查看与推进一步)。
- `prepare-source --method <allowlisted-id> --input <host-source> --output <new-packet>` 捕获钢材封存模型或软件源码原字节；`create --method ...` 选择相应固定契约，step 共用执行/恢复而非动态加载模块。只有 P02 接受 chemistry/topography 维度；材料保留 MSE/MPa²、软件保留 I/O 场景，不混用协议。
- [fetch_project_source.py](../../scripts/fetch_project_source.py)的`fetch --workspace ... --request-id ... --doi ... --output ...`只向`https://www.ebi.ac.uk/europepmc/webservices/rest/search`发固定DOI公开GET（core JSON/pageSize=5），不接受任意URL、凭据或付费接口；30秒截止、2MiB上限、无redirect/proxy/自动重试。项目`source_requests`先持久预留，首次冻结8次独立累计额度；不计研究tool action或来源提取，模型0/原5元现金上限/平台暂停不变。
- 同一CLI的`status --workspace ... --request-id ...`只离线核对/恢复；received原ID不再发送，known failed保留额度消耗，显式新ID可在剩余额度内另取。sending/unknown阻断新执行及升级，重复命令或换输出目录不能绕过。`build-bundle --workspace ... --request-id ... --output ...`离线生成任务绑定包，分开保存raw/projection/provenance，随后用原项目`register-evidence → next → advance`读取并进入FTS；登记不扣提取次数。完整命令和未知/许可边界见[公开来源接入](../../docs/public-source-connector.md)。

- [c01_native_tools](../../src/autoresearch/c01_native_tools.py) 的 `tools_from_schema/parse_tool_decision` 是原生工具 schema 和响应绑定入口；[C01LocalLoop](../../src/autoresearch/c01_local_loop.py) 管理请求预留及接续；各领域控制器另有自己的允许动作和参数。
- [CLI 主入口](../../src/autoresearch/cli.py) 与 `scripts/` 中专项命令彼此独立；例如 [run_pipeline_research.py](../../scripts/run_pipeline_research.py)、[run_tabular_research.py](../../scripts/run_tabular_research.py)、[intake_evidence.py](../../scripts/intake_evidence.py)。先读对应 [管线研究](../../docs/pipeline-research.md)、[表格证据](../../docs/tabular-evidence.md)、[接收入口](../../docs/evidence-intake.md)；不要推断统一跨阶段续跑已接通。
- [publish_workbench.py](../../scripts/publish_workbench.py) / [workbench_recipe](../../src/autoresearch/workbench_recipe.py) 核对来源并打包；此 recipe 是交付配置，不是科研 skills/tools 流程配方。

接口改动时同步本页、[后端索引](backend.md)、对应正式文档及调用方；按范围运行一次针对性协议/路由验证。若影响只读页面，按工作区要求实际渲染截图检查，不能仅凭代码判断布局。

统一项目的来源`locator.kind=pdf_page`可写`N`或`N:start-end`（单页一基；页内pypdf文本Unicode码点零基、end排除），不接受页范围或自动OCR。页外/空白/NUL/超60KB选区拒绝，解析复用已有30秒隔离worker；原文件大小/哈希与任务绑定沿原适配器。解析器及整页文本身份保留在结果，解释仍未批准。当前项目报告另用64MiB单文件/128MiB合计上限，旧封存包大小边界不变。实际失败/修正与接线见[P02核对](../../docs/p02-mapping-audit.md)。

[run_research_project.py](../../scripts/run_research_project.py)新增`selection-context --workspace [--need]`只读真实候选/条件/预算/原文，并封印snapshot/core/controller身份；`advance-selection --workspace --request-id --proposal <file> [--need] [--expected-state-version]`安全读取64KiB严格JSON提案。提案只能选择context.candidates[].id或wait，不接参数/命令/批准字段；完整context/proposal保存在原controller父请求，相同ID与原expected版本恢复同一child。provider是未核验声明，不会据此发送模型或证明模型已读。等待只约束此父请求，未读候选仍保留。完整协议/实跑边界见[选择提案](../../docs/project-selection.md)。

- A16 `prepare-source --method data.tabular-quality-audit --input <directory>`捕获spec+CSV原字节，再走原create/selection/advance/report；[字段与限制](../../docs/tabular-quality.md)。数据独立页18790沿同一只读GET，无新增写入HTTP。

- A26 [run_host_selection.py](../../scripts/run_host_selection.py) 提供 `prepare/request/import-response/consume/advance/status`：prepare 冻结项目真实 context/provider/版本及不可重置的 grant（决策1至8次，累计CLI报告估值至多0.10 USD）；advance 显式串行一次CLI选择和至多一个原控制器行动。同ID及原参数重放不再派发或执行，sending/unknown只核对原收据，不自动重发；子代理文件导入不证明实际执行或费用。status只读分列native/host用量；A26当时仅有CLI入口，工作台HTTP见A27，当前报告包含模型证据见A28。具体命令、严格JSON与恢复见[Claude CLI与子代理入口](../../docs/host-model-selection.md)。

- A27 [create_project_server](../../src/autoresearch/project_workbench.py)新增 `claude_executable=None`；[serve_local_workbench.py](../../scripts/serve_local_workbench.py)只有显式 `--enable-local-actions --claude-executable <现有原生可执行文件>` 才启用模型，路径由宿主固定。`GET /api/local-workbench/model`只读返回 `local-host-model-view-v1`：`enabled/project_id/journal/records`；无活动项目正常返回null/空记录，disabled服务仍可读历史，不恢复或派发。`POST /api/local-workbench/model-advance`只接 `request_id/project_id/expected_state_version/decision_limit/cli_budget_usd/reason`，沿原journal执行prepare→request→合法时consume；`POST .../model-resume`只接 `request_id/project_id`，核对原提供方和可执行文件，不能创建请求或更换原回答。响应为 `local-workbench-command-v1`，包含 `status/model_record/usage`；`applied`不等于工具completed，需看 `model_record.outcome.status`。两POST沿原本地会话、活动项目及未完成操作门禁，未启用返回405 `MODEL_DISABLED`，原ID重放/重开不重复派发；unknown保留原请求。浏览器实际两次选择与反馈执行已核，外部报告估值0.048195USD、原生计数0分别展示；A27当时的核心PDF须配套host日志，当前导出见下方A28。完整操作见[工作台](../../docs/local-workbench.md)，正式journal边界见[模型入口](../../docs/host-model-selection.md)。

- A28 原 `export_project_report.py --workspace/--output` 和四个报告GET入口不变。`report.json.host_models`含状态/原记录，`input.json.host_models`含 `snapshot_sha256/status/asset_names`，其assets保留已有宿主原件Base64并纳入source_manifest；清单新增 `host_model_snapshot_sha256`。下载同时核对核心与host快照，host请求/原文变化即使未改核心版本也会使报告stale。已分发且无host记录、核心无external_model选择的旧四文件包仍可读；有外部历史却缺host标记的旧包须重新导出，不覆盖旧工件。PDF/Markdown区分原生计数、CLI尝试、已知USD报告值、未知及未关联历史，`applied`不当作工具完成；导出不调用模型，不读CLI认证/环境文件。见[模型报告包](../../docs/host-model-selection.md#a28报告包包含宿主模型记录)。

  A28已通过同组本地HTTP接口重导出及下载：四文件与挂载字节相同，15份原件身份一致；旧A27报告stale、新导出current，18791无外部的旧报告仍available，未新增模型调用或行动。浏览器控制API不可用，未验证页面点击；[核对结果](../../runs/a28-model-report-20261104/validation.json)保留该边界。

- A29 [run_research_project.py](../../scripts/run_research_project.py)新增 `advance-recipe --workspace --request-id --recipe --expected-state-version [--need next_check]`，版本必填，配方严格JSON最多64KiB。`ProjectController.advance_recipe`在线编译后沿原控制器提交至多一个合法 child；父请求命令为 `controller.advance_recipe`，保存原六字段 proposal、完整 `recipe_decision` 及 context。原 ID/原参数重放不重新选择，换配方或版本冲突；新反馈用新 ID/新版本。`compile_research_recipe.py --recipe --context --output`仅编译冻结 context，不能替代在线执行检查。四文件报告继续原入口，`input.json.recipe_selections`保存请求/context/decision，PDF/Markdown展示配方版本、顺序和跳过原因。A29当时只有CLI；A30网页入口见下条，均不自动派发模型；[具体用法与迁入范围](../../docs/recipe-research/integration.md)。

- A30 `GET /api/local-workbench/recipes`返回固定两配方的真实只读预览（`local-research-recipes-v1`，project_id/state_version/context_sha256/recipes[{recipe,decision}]）；无项目null/[]。`POST /api/local-workbench/advance-recipe` exact4字段request_id/project_id/expected_state_version/recipe，need固定next_check，沿原本地写开关/会话/活动项目/pending守卫调用A29。配置全文随原请求保存，重放不用新context。操作与草稿规则见[本地工作台](../../docs/local-workbench.md#按配方推进一步)。

- `POST /api/local-workbench/plan`精确接收`request_id/project_id/expected_state_version/plan/reason`。plan包含`question/basis/steps/expected_feedback`正文，返回原命令信封和本次`research_plan`版本。`GET /api/project`增加`research_plan.current/revisions`，保存后的当前版本进入`selection-context`的可选`research_plan`字段。使用与修订见[研究计划](../../docs/local-workbench.md#保存与修订研究计划)。


- 原始训练设计继续`POST /api/local-workbench/design-bind`，`prediction_column:null`，新增`training:{feature_columns,split_group_columns,fit_limit}`。GET designs提供numeric_columns/group_columns/budget；三种原方法为data.ridge-random-validation、data.ridge-group-validation、data.prediction-negative-control，仍沿原advance。目录completed_requests包含导入、改版与绑定的原ID，支持响应丢失后只读核对。详见[研究设计](../../docs/research-design.md)。


[固定保存研究reference](../../docs/saved-study-reference.md)：sourcea1152b4的host-only `read_saved_study_reference.py summary|status`，只读绑定原study及最终audit，<=64KiB，缺失/unknown/损坏不补0。没有任意path/study/execute参数；S019只读getter/API另行实现，不把reference当新native primary或项目预算。


S019 sourcee88c3f5已接唯一 `GET /api/local-workbench/saved-study-reference`，无query/路径参数、不在POST动作表、不取项目binding，外部保存引用scope；[实际8HTTP/异常态/构造器及bootstrap边界](../../docs/execution/g5-local/saved-study-reference-http-verification.json)。getter无项目预算访问，UI/关联/三臂执行不冒称完成。


S020–022增加正式readonly host入口与固定GET `/api/local-workbench/project-summary`，无query/路径选择、拒写，读取真实active原项目记录，项目状态与source62/e731外部study分开。[使用](../../docs/readonly-study-workbench.md) · [成品](../../docs/execution/g6-local/readonly-workbench-release.json)。后续fixed capsule下载另行验证，旧b1包不含该路由。


S023增加固定无query GET study-capsule/study-capsule.zip，先size/SHA/identity再回原bytes，UI显式点击；S024保存引用增加原protocol hypothesis_source字段，不重算/自动关联。[精确下载](../../docs/execution/g5-local/study-capsule-download-verification.json) · [原字段投影](../../docs/execution/g5-local/hypothesis-source-verification.json)。

S026沿用固定project-summary GET，增加stored_history/stored_report，旧字段不变；每组256KiB上限，原manager/project双快照和新模块sourceguard覆盖。没有新增恢复或报告下载动作。[字段与真实边界](../../docs/execution/SPRINT-026.md)。

S028沿既有advance/advance_recipe body与响应，不增新POST或自动恢复端点；manager落盘原core响应status，显式同ID仍经core。终态/unknown漂移不覆盖，核心异常不制造完成。[同ID语义与验证](../../docs/manager-advance-receipts.md)。

S030在project-summary原controller子项增加request_handoff，固定GET不变；原body仅canonical语义与双用途摘要验证，非原wirebytes/执行许可，缺失或错配无body。S031最新安装不改变旧原案。[字段与精确边界](../../docs/execution/SPRINT-030.md)。

S032直接project-selection-proposal-v1可选experience_case_refs（最多4唯一case_id/case_version/bundle_sha256）；Controller原接口不增权限，结果view/report留原association。Host/local-model/recipe当前仍旧wire，不称模型可生成。[边界](../../docs/experience-decision-citations.md)。
