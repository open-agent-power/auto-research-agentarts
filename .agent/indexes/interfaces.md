# 接口索引

这是现有入口导航，不是新 API 规范。统一项目命令和研究 Observation 在 [自适应研究设计](../../docs/research/adaptive-research.md)中讨论，**尚未实现通用 create/start/resume REST 接口**。

新项目/运行/行动对象及命令边界见[研究契约](../../docs/architecture/research-contracts.md)，依赖关系见[底层架构](../../docs/architecture/foundation.md)。同一项目已有已登记白名单方法的本地Python/CLI实现和只读HTTP投影，HTTP不接受研究执行命令。

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
