# 后端索引

`saved_retrieval_reader`只读校验并投影已完成引用检索工件；分页25、两臂各20、source/action/result和audit前驱绑定。原研究codeidentity及预算不变；不调用rank/score/fit/controller。入口与真实验证见[阅读器](../../docs/saved-retrieval-reader.md)。

Ridge分组编码使用独立`encode_groups`首次出现字典映射，保留原整数ID/NumPy与GroupKFold语义；原生微函数确认和8纯回归/1164工程回归已核，[结果](../../docs/execution/g4-local/native-results.md)。源码身份改变，旧研究固定0ceb274服务/账本，不自动upgrade或重训。

独立`agent_tasks.AgentTaskLedger`为可信host分析任务提供ProjectRef固定绑定、DAG、事务claim/同ID恢复、attempt/result绑定协调和一致状态快照；与科研fit/source预算分离，无模型传输或任意执行。默认single；本地保存证据对照没有多线程收益，见[合同](../../docs/execution/g2-local/contract.md)与[结果](../../docs/execution/g2-local/results.md)。

`saved_materials`按显式action／诊断结果SHA选择完整保存groups／folds／rows，核对诊断及原CV封套、来源和历史设计，直接复制原值；不重新inspect或关联原输入。plan／recipe非空请求生成v3，最终64KiB全量校验，超限明确失败；默认旧context/prompt原字节保持。Host specification／freshness／same-ID、readonly preview、report与RSI导出读取共用冻结内容，见[字段供应](../../docs/research-design.md#明确供应保存诊断字段)。

原生保存OOF诊断复用`inspect_saved_oof`，两个check-specific方法独立注册于`DIAGNOSTICS/FOLLOWUP`，不进训练check或默认顺序。原CV/结果SHA与当前设计进入请求身份，trusted workspace只在执行端传入；工具1／fit0／来源0，computed资格、原ID／unknown／换设计恢复沿原账本。完整结果为`result.diagnostic`，不冒充CV；见[原生诊断](../../docs/research-design.md#原生保存误差诊断)。

`input_basis`新增显式selected-column log1p，`project_design`接`training.input_transforms`并沿原绑定需求预检验证完整案例域；Ridge共用映射／元数据和原2fit/折计数。`feature_comparison`将原`fixed_input_basis`门扩至精确声明log1p，仍只接受同原列的raw父版、同完整评价及除映射两字段之外相同协议；沿原父MAE assessment，见[固定log1p](../../docs/research-design.md#固定log1p原输入变换)。

`inspect_saved_oof(..., within_group_column=...)`在请求时追加同组相邻原输入变化。使用私有完整训练输入检查其他列固定及单评价折，先聚合同值记录再形成相邻对；保留不合条件组与层，每种确切取值对按组等权汇总。默认JSON／Markdown保持，旧项目与预算保持，见[对应语义](../../docs/research-design.md#同组原输入的相邻变化)。

`saved_oof_diagnostics.inspect_saved_oof`只读明确指定的单个原始Ridge行动，复用`project_experience`原工件及折核验，并按共享raw2048核对捕获CSV的完整行／排除、目标与划分组。独立提供全部行、折、组、行／组加权与原输入诊断，不改旧P02工具、父子比较或原项目；其单独CLI与上述原生计账入口分别使用，见[单结果诊断](../../docs/research-design.md#单个已保存验证的只读诊断)。

`research_plan_proposal`复用`research_design._records`已核验的保存结果，为当前绑定CV捕获v2可选顶层`prediction_ranges`；保持原feedback observations，计划与recipe-change提示共用条件说明。只改两wrapper，不改变core/controller/exporter身份；旧Host无字段不回填，现有离线RSI保留原观察等值与原件检查，不另重算范围。见[Host上下文](../../docs/host-model-selection.md#根据真实反馈建议研究计划)。

原始Ridge设计的`project_design.MAX_RAW_RECORDS=2048`由绑定、adapter与方法资格共用，raw保存OOF负对照沿用同一上限；显式保存预测列检查仍使用`prediction_adapter.MAX_RECORDS=512`。完整1030行Concrete课题触发扩展，不截断数据或改变拟合协议；既有项目须原显式代码登记，不能据容量扩展重置任何用量。见[原始训练边界](../../docs/research-design.md#原始数据的固定模型验证)。

`ProjectController._selection_context`沿原数值／来源执行分支捕获`conditions[].budget_cost`，Ridge复用当前绑定的`_fit_attempts_needed`，无对应设计为null。`plan_readiness`仅复制捕获成本到v2，旧Host保持v1。资格和执行计数不读取成本投影；见[额度需求](../../docs/method-budget-costs.md)。

`project_experience`复用原条件记忆存储，复核已保存Ridge OOF并导出方法案例；`project_experience_binding`保存目标项目显式导入与active／retired历史，原ID重放及manager接续不复活资格。控制器只把活动案例加入独立`experience`，保持候选、证据及预算；见[案例快照](../../docs/project-experience.md)。

`plan_fact_check`核对提交者标注的精确原句、冻结父子比较与数值声明，`LocalWorkbench.check_plan_fact`先复用Host原件核验，再纯计算。它不从自然语言关键词判断语义、不修改Host/项目/预算，也不补当前比较到旧context；见[断言核对](../../docs/plan-fact-check.md)。

`plan_feedback`为新计划/配方的v2反馈提供明确投影：历史决定指原action账本，来源原文与资源正文指原工具工件；保留数值、协议、范围和用量，不提高64KiB上限。`research_plan_proposal`复用严格父子对照，提供`saved_comparisons`帮助区分父版与均值参考。离线`recipe_improvement`从原工件重建同样投影再精确匹配，旧v1封存不变；见[Host上下文](../../docs/host-model-selection.md#计划执行条件)。

`ResearchProject.limit_evidence_budget`及CLI `limit-evidence-budget`显式收紧累计来源上限，保留已用/预留和其他额度，保存不可变预算修订；达到上限后原控制器不再提供来源候选。仅支持降低，不扩额、不重置；见[用法](../../docs/project-slice.md#收紧项目来源额度)。

`input_basis`提供唯一固定原尺度单列`[x,x²,x³]`展开，`project_design`冻结可选`training.input_basis`，Ridge适配器v2在训练折标准化前使用并保存三维参数。`fixed_input_basis`资源须明示父版，比较门仅允许这两项显式元数据差异；目录与报告的`saved_parent_mae`判断使用真实父版配对，不能用训练均值参考冒充。见[固定输入基对照](../../docs/research-design.md#固定输入基函数对照)。

`feature_comparison`接收已捕获输入时，为严格匹配的父子OOF派生`input_profiles`：按候选输入优先、父版补列，≤16个数值逐值分组，否则按输入范围分5等宽区间。保留完整评价行、逻辑行号、MAE、预测减观测均值、负预测和逐行变化；只读派生，不取误差定边界、不训练，见[研究设计](../../docs/research-design.md)。

`feature_comparison.compare_feature_checks`按明确资源父版本只读比较保存的原始训练结果，要求来源、目标、评价行、分组、折和均值参考一致；不取交集、不重拟合、不自动采用。`research_design`目录与`project_report`共用此投影。原始设计可仅配置`group_cv`，省去与当前问题无关的随机重训；累计拟合用量保持，见[研究设计](../../docs/research-design.md)。

`prediction_summary.summarize_oof_range`只读已保存OOF，供`research_design`与`project_report`共用，投影观察/预测范围及负值/越界计数，不改原结果或科学资格。[Yacht实际任务](../../docs/research/yacht-geometry-study.md)保留固定协议、两份计划无实质差异及不利局部诊断。

[计划执行条件](../../docs/host-model-selection.md#计划执行条件)由`plan_readiness`从Host冻结context纯只读派生，供新请求prompt、工作台与报告共用。扣除预留后的余量、真实候选和方法缺口分别保留；不修改原Host记录，不判读自由文本或自动批准科研解释。

[研究设计](../../docs/research-design.md)将保存预测的公平基线、分组与敏感性检查接入原控制器。`project_design`保存明确字段绑定及不可变资源版本，`research_design`提供资源目录与反馈候选。实际行动共享原项目预算和请求恢复。

[有界保存证据队列](../../docs/recipe-research/rsi-delivery.md#有界保存证据队列2026-11-08)由`recipe_improvement.run_improvement_sequence`复用原单轮和阶段读取；固定清单，轮数限额／pending／缺原件时保存不可变停点，重启复用完成轮次并核对有效版本链。只是读取已有证据，不是主动科研调度或新的预算来源。

[A64离线导出补充](../../docs/recipe-research/rsi-delivery.md#队友收到离线包后的补充2026-11-07)核对保存Host、回答SHA、提案、验证、行动和来源资产，形成独立外环结果；不构造数据库、不升级历史代码、不更改原项目或预算。`next-input`只读最新完整stage的有效配方，保留已有在线采用和阶段接续的职责边界。

[LocalWorkbench.continue_research](../../src/autoresearch/local_workbench.py)以同ID冻结计划方式、执行方式、方法和确切收据；复用已有Host计划明确采用门、LocalWorkbench.batch或HostModelBatch。服务启用固定CLI时，计划阶段沿原Host取得建议；未启用则准备delegated，首次提供方／路径保持，配置漂移保留原阶段。有效配方批次核对原编译决策与revision；未知不重发，不创建grant；见[阶段合同](../../docs/host-model-selection.md#继续研究的计划与行动阶段)。

[同轮阶段接续](../../docs/recipe-research/rsi-delivery.md)已由`run_improvement_round(resume=True)`实现：同round-id仅追加保存提案／验证的不可变stage，原pending、冻结上下文、已保存候选及终态保持。原Host／控制器核对仍走原入口，阶段读取与接续不派发模型或工具。

[数值关联](../../docs/numeric-association.md)由`numeric_association_adapter`注册为`data.numeric-association`，在原表格质量结果后按声明字段执行总体／分组Pearson分析。原控制器核对前序行动及结果身份，结果保留有效对、排除数、不可计算原因和原CSV坐标；调用消耗原本地工具额度，模型与拟合0。公开diabetes实际路径已完成state9及当前报告，原ID回读不重复执行。

[单轮RSI](../../docs/recipe-research/rsi-delivery.md)由`recipe_improvement.run_improvement_round/read_improvement_round`评估已有提案与验证，保存不可变输入、采用／回退／pending和有效配方。`saved-host`仅读原Host／控制器账本。项目接线由[project_recipe](../../src/autoresearch/project_recipe.py)核对原Host原件、保存显式`recipe_revisions`与完整工件，沿原ID恢复并保留预算。默认控制器读取最后有效配方，旧请求继续使用冻结版本，新请求在写入锁内再核对revision。原A64已页面采用v2并由默认控制器完成后续分组行动、反馈和state20报告。真实任务的新Host后轮、外环阶段恢复及有限多轮继续推进，已有项目batch和Host行动batch可复用。

`research_recipe`新增[方法卡纯读取与候选关联](../../docs/recipe-research/recipe-design.md)，复用原sealed context校验，返回完整方法知识、宿主候选与条件缺口，不进入执行／状态／预算路径。原`compile_recipe/advance_recipe`协议不变；该文件属于既有controller代码哈希，历史项目仍需原显式代码兼容处理，不自动升级。

本页导航现有实现；项目入口见 [docs/README](../../docs/README.md)。同一项目已连接登记白名单方法、条件选择一步、来源反馈与恢复；各领域Observation保留自身含义。开放式方法扩展仍待实现，有界模型选择的跨域收益仍待验证，目标设计见[研究架构](../../docs/architecture/foundation.md)。

架构基线见[底层模块与依赖](../../docs/architecture/foundation.md)和[状态/能力契约](../../docs/architecture/research-contracts.md)。已实现的是有限本地命令/目录、有界选择与既有执行协调，不等于目标契约全部端口或LLM自主科研。

## 项目与状态

- [LocalWorkbench.record_feedback](../../src/autoresearch/local_workbench.py)接[ResearchProject.record_feedback](../../src/autoresearch/research_project.py)，独立保存`state.researcher_feedback`的9字段原意见，关联请求、提交依据状态、计划版本和可选既有行动，信任标记为`unverified_researcher_statement`。保存使state版本加1，沿计划同等代码、版本、未决请求门禁及原ID恢复处理，预算和工具用量沿原账本保留。sealed context、计划/配方prompt及报告接收原意见。工程夹具已核对真实保存、回执丢失后只读确认、零新增重放和下一plan提示组装，3项定点回归及前端四门禁通过，模型/研究工具/Host请求0，见[意见用法](../../docs/local-workbench.md#记录研究者意见)。
- 模型计划建议由[research_plan_proposal](../../src/autoresearch/research_plan_proposal.py)构造原selection context与真实保存反馈，提供prompt、原回答解析及提案校验。[HostModelSelection](../../src/autoresearch/host_model_selection.py)以`purpose=plan`复用原grant，consume保存`proposed`，`adopt_plan/reject_plan`分别记录采用或拒绝。采用生成原项目研究计划修订，保留原ID恢复与过期状态，见[Host用法](../../docs/host-model-selection.md#根据真实反馈建议研究计划)。该轨迹可供配方RSI模块接线，外环职责见[队友接口](../../docs/recipe-research/team-module-interface.md#主团队提供的真实轨迹与host接线)。
  A63已在公开diabetes实例取得三次真实子代理决策、两版计划的网页采用、一次质量方法及随后一次来源读取，原ID重放后状态与用量一致，6页报告已实际查看。桌面及手机8张截图、五页导航和四报告下载身份已核对，运行静态资源与构建一致，已通过[PR #8](https://github.com/1263-ux/auto-research-agentarts/pull/8)合并至共享主线`23b6d91`。Host保留原未核验声明，内部推理与费用unknown，新增plan用途的CLI传输仍待实跑。具体范围见[实际接续](../../docs/host-model-selection.md#a63-真实子代理计划修订与后轮接续)。
- [recipe_change_proposal](../../src/autoresearch/recipe_change_proposal.py)冻结实际research context、当前配方与改进目标，校验下一版原生配方、实际反馈ID及conditions中成对的方法与评价引用。[recipe_improvement_adapter](../../src/autoresearch/recipe_improvement_adapter.py)提供`propose_recipe_change/validate_recipe_change`，以Host的`purpose=recipe`保存完整提案，再比较冻结baseline/候选决策，按允许方法与来源收据经原控制器最多执行一步。A64已在已有构造项目取得一次实际子代理候选v2和一次允许来源读取，baseline wait、候选execute，原ID重放无新增。桌面/手机截图、五页导航和四报告下载身份均已实际核对，运行静态资源与本次构建一致，功能已通过[PR #9](https://github.com/1263-ux/auto-research-agentarts/pull/9)合并。队友下一步复用原结果接`run_improvement_round`，继续负责外环、版本与连续轮次，见[实际范围](../../docs/host-model-selection.md#a64-配方修改提案与允许工具验证)与[适配约定](../../docs/recipe-research/team-module-interface.md#主开发的配方改进适配接线)。
- [read_recipe_validation](../../src/autoresearch/recipe_improvement_adapter.py)返回`recipe-change-validation-view-v1`，将原Host提案、两个validation sidecar及控制器回执对应后投影状态、输入、结果和错误。[LocalWorkbench.model_view](../../src/autoresearch/local_workbench.py)以独立`recipe_validations`数组提供这些记录，`records`承载Host原请求。完成状态需要原证据完整且一致，读取仅投影已保存事实。研究页已展示版本、冻结选择、实际工具状态和验证JSON下载，一项reader定点回归、前端门禁、8张桌面/手机截图及JSON下载核对通过。方法卡、采用或回退和后轮管理由队友按长期任务负责，见[读取约定](../../docs/host-model-selection.md#工作台读取验证记录)。
- 本地项目：[ResearchProject](../../src/autoresearch/research_project.py) 的 `create/status/step/resume` 保存单Run、行动/方法实例、完整工件、反馈与固定策略下一决定；最初的[saved_oof_adapter](../../src/autoresearch/saved_oof_adapter.py)保留P02保存OOF语义。见[用法与边界](../../docs/project-slice.md)：不导入历史请求计数，不调用模型；HTTP仅作只读投影，unknown不自动重算。
- 同项目来源：`upgrade/register_evidence/read_evidence/attach_evidence/evidence_task/method_options/knowledge`；[source_evidence_adapter](../../src/autoresearch/source_evidence_adapter.py)捕获任务绑定原件并提取选区。登记只做原件I/O/哈希/收据，不扣提取次数；读取才创建行动/观察和FTS，原attach保留兼容。[research_methods](../../src/autoresearch/research_methods.py)匹配条件，[project_knowledge](../../src/autoresearch/project_knowledge.py)检索真实选区，来源观察不批准终点。
- A7 注册方法：[method_registry](../../src/autoresearch/method_registry.py)显式注册 P02、[钢材模型复核](../../src/autoresearch/steel_audit_adapter.py)、[软件原件捕获检查](../../src/autoresearch/source_integrity_adapter.py)、表格质量、[引用检索](../../src/autoresearch/retrieval_adapter.py)与[合成调度](../../src/autoresearch/scheduling_adapter.py)，经同一 ResearchProject 的事务、恢复和预算执行。CPU两方法仅有各自保存结果审计后续；不得重新排名/求解。来源任务使用通用 research.source-selection（旧 P02 ID 保留），失败收据不自动重试，不把各领域塞入共同科学终点。实际loaded数值依赖须与安装版本一致，并绑定项目/code身份；兼容源码升级拒绝不同或未知旧runtime，历史精确receipt重放保留。
- [ProjectController](../../src/autoresearch/project_controller.py)的`next/advance`：next只读条件、来源索引与预算；advance先保存`controller_requests`父选择，再最多提交一个原step/read_evidence子请求。父ID重放不重新选择，waiting也冻结；子缺失且版本漂移则拒绝，不因PROJECT_BUSY补造工具失败。

- 通用历史原型：[Engine](../../src/autoresearch/engine.py) 的 `create/status/propose/observe/step/finalize` 与 [ResearchLoop](../../src/autoresearch/research_loop.py) 的 `configure/status/resume/run/evidence/export`；绑定既有 campaign/协议，不能视为跨域项目主干。
- C01 研究状态：[C01Research](../../src/autoresearch/c01_research.py)；领域示例：[ConfiguredStudy](../../src/autoresearch/configured_iteration.py) 的 `create/observe/apply` 与固定协议 [validate_protocol](../../src/autoresearch/experiment_protocol.py)。见 [配置化迭代](../../docs/configured-iteration.md)。
- 资料接收：[EvidenceIntake](../../src/autoresearch/evidence_intake.py) 的 `create/advance/status`；外层评议 [EvidenceWorkflow](../../src/autoresearch/evidence_workflow.py)。见 [接收入口](../../docs/evidence-intake.md)。

## 请求账本、控制器与工具

- [C01LocalLoop](../../src/autoresearch/c01_local_loop.py) 的 `_reserve/_received/_consume/run/status` 管理请求与恢复；[C01CloudLoop](../../src/autoresearch/c01_cloud_loop.py) 是云传输控制器，具体来源、预算和未知请求不能因新目录重置。
- [c01_native_tools](../../src/autoresearch/c01_native_tools.py) 的 `tools_from_schema/parse_tool_decision` 转换和验证原生调用；[Ollama 云传输](../../src/autoresearch/ollama_cloud.py)负责账户与传输约束。
- P02 专项：[PipelineResearchStudy/PipelineResearchCloudLoop](../../src/autoresearch/pipeline_research.py)、[SourceAssessmentStudy/SourceAssessmentCloudLoop](../../src/autoresearch/source_assessment.py)；[TabularResearchCloudLoop](../../src/autoresearch/tabular_research.py) 是后者的配置适配。见 [管线研究](../../docs/pipeline-research.md)和[表格证据](../../docs/tabular-evidence.md)。

## 知识、记忆与报告

- [knowledge_sources](../../src/autoresearch/knowledge_sources.py) 的 `collect_documents` 提取来源；[knowledge](../../src/autoresearch/knowledge.py) 的 `build_index/KnowledgeIndex` 是本地索引；[c01_knowledge](../../src/autoresearch/c01_knowledge.py) 的 `build_case_index` 绑定案例。见 [知识入口](../../docs/knowledge.md)。
- [ResearchMemory](../../src/autoresearch/research_memory.py) 的 `_import_derived/recall/set_status` 保存条件化记录；见 [研究记忆](../../docs/research-memory.md)。
- [project_report](../../src/autoresearch/project_report.py)只读导出三域当前项目快照；`registered_inputs`及输入包保留`registered_unread`与原字节，不把登记算作已提取。报告和[只读服务](../../src/autoresearch/project_workbench.py)按项目/snapshot绑定，过期拒绝。
- 当前报告在前部展示最新已完成来源行动保存的提交者、未核验主张和未决问题，失败或未读资料不替代该段。节选按最新读取优先，同一来源与定位使用最新展示主张，PDF最多8处；完整JSON、inputs与历史不截断。见[本地工作台](../../docs/local-workbench.md)。
- [dossier_data](../../src/autoresearch/research_dossier.py) 汇总封存数据，[export_dossier](../../src/autoresearch/research_dossier_render.py) 导出报告；[build_handoff](../../src/autoresearch/chemotopo_bundle.py) 打包，[snapshot_viewer](../../src/autoresearch/snapshot_viewer.py) 验证并只读服务。见 [研究综合报告](../../docs/research-dossier.md)与[离线工作台](../../docs/portable-workbench.md)。

## AgentArts 边界

- [runtime.create_app](../../src/autoresearch/runtime.py) 是独立运行时适配边界；[AgentArts 目录说明](../../agentarts/README.md)和[C01 代码节点说明](../../agentarts/c01-sensitivity/README.md)记录已做工作。独立节点验证不等于产品运行时、Trace 或平台已集成；以实际证据为准。

后端接口或身份变化时同步 [接口索引](interfaces.md)及对应正式文档；选与修改相匹配的定点验证，涉及封存兼容时核对旧快照读取，不默认重跑全套。

- A16 通用表格方法：[tabular_quality_adapter](../../src/autoresearch/tabular_quality_adapter.py)接有界CSV/spec，保留原件/声明/坐标；[用法](../../docs/tabular-quality.md)。四登记主方法仍每项目择一，后续同项目多分析待建；不为新输入另建控制器。

A17 [grouped_quality_adapter](../../src/autoresearch/grouped_quality_adapter.py)为data主方法的条件化后续分析；同一step/controller显式绑定method、前序action/result与评价，原primary指纹兼容。`extend_local_budget`单独留痕并保留累计用量；upgrade不扩额度，unknown不允许新分析或额度修订。

A18 [LocalWorkbench](../../src/autoresearch/local_workbench.py)仅管理宿主输入、活动项目和报告索引；创建/选择/导出意图持久，partial保留不自动重做，实际advance仍走原ProjectController。最多32登记意图，上传不得指定路径；[用法](../../docs/local-workbench.md)，不另建研究控制器。

A19 `LocalWorkbench.register_evidence`将界面原件捕获到固定宿主目录，再调用原项目登记；冻结请求、原件SHA和核心回执，原ID可核对已提交核心结果，核心未登记的partial不自动补做。同项目未决登记拒绝替换ID；提取仍用原条件选择/来源预算。非P02在来源读取后恢复最近已完成分析的完整取证要求，包含后续方法新增问题；旧结果不回写。

A20 `LocalWorkbench.batch/batch_record`在原manager账本冻结有界grant及逐步意图/结果，复用`ProjectController.advance`；本地编排/核心/controller身份和原parent/child可核对。已完成批次原ID冻结回放，未完成只沿原ID显式核对，unknown不派发；不同步扩预算或授权未来资料。manager保存批次不替代核心执行真相，当前报告包与批次JSON分别取得。实际受控进程退出/重开及失败链见[本地用法](../../docs/local-workbench.md)。

A26 [HostModelSelection](../../src/autoresearch/host_model_selection.py)在项目内保存独立 host journal；[host_selection_protocol](../../src/autoresearch/host_selection_protocol.py)只解析真实 context 下的候选选择，[claude_selection_transport](../../src/autoresearch/claude_selection_transport.py)用现有受控进程运行一次 CLI、保留原始输出与退出收据。prepare 固定累计决策/CLI报告估值 grant；request 不自动重发，consume 复用原 `advance_selection` 和原 child。导入子代理只声明未核验执行，native Qwen 历史不改，旧外部 unknown 不计零；当前报告导出同步模型证据，见下方A28及[正式入口与恢复](../../docs/host-model-selection.md)。

A33 [HostModelBatch](../../src/autoresearch/host_model_batch.py)沿原host请求链执行最多两次CLI选择，每步读取实际新反馈；原累计grant不改，初始方法和已登记来源集合冻结。批次保存确定子ID与原结果引用，原ID只恢复原请求；无候选不发模型、未知不重发、批次外变化停止。批次收据由原host报告捕获纳入双快照与复现附件；[CLI用法](../../docs/host-model-selection.md#一次授权按模型反馈最多推进两步)，没有新增网页入口或研究控制器。

A34 实跑发现CLI错误输出中的已报告费用被丢为unknown，以及单次CLI可超出其剩余预算参数。`parse_cli_usage`独立核对完整result envelope元数据，失败/invalid不解析成可执行选择；`HostModelSelection.reconcile_usage`沿原launch/stdout/exit离线补记，保留原失败及核心状态。原报告校验费用出处并标出超配置阈值；阈值不提供单次硬支出保证。实际第二次选择未成功，见[费用核对与原ID恢复](../../docs/host-model-selection.md#状态重放与恢复)。

A27 `LocalWorkbench.model_view/model_advance/model_resume`将同一 host journal 接回现有工作台，不增加 manager 数据库或另一份模型事实源。模型默认关闭；[服务启动](../../scripts/serve_local_workbench.py)须同时提供 `--enable-local-actions --claude-executable <现有原生可执行文件>`，浏览器不传路径、provider或命令。写入复用 manager 锁、活动项目、未完成批次/资料与原 Host/Origin/CSRF 门禁；原 ID resume 只定位既有请求、核对原 executable，再沿原 request/consume 恢复。`applied`表示已提交控制器，工具结果仍读取 `model_record.outcome.status`。2项必要HTTP检查覆盖默认禁用、门禁、提交后中断重开及零新增重放；本机浏览器已实际完成主质量检查→反馈分组两次CLI选择，报告估值合计0.048195USD，原ID恢复新增0，原生模型计数0须与外部CLI2次分开。A27当时的核心PDF未纳入host用量，当前导出见下方A28；领域/用户收益仍待验证。入口见[本地工作台](../../docs/local-workbench.md)。

A28 [host_model_report](../../src/autoresearch/host_model_report.py)提供 `capture_host_models → snapshot_sha256/status/records/assets`，供原报告导出和下载核对共用。报告JSON保留状态/请求，重现输入保留快照/status/asset_names及实际已有日志、提示、回答和CLI传输原件；source_manifest登记身份，不读认证或环境文件。四文件报告清单新增 `host_model_snapshot_sha256`，核心版本不变而宿主请求或原文变化也使旧报告stale；未含外部历史的已分发旧包仍可读，有外部历史但缺标记的须重导出，不改旧原件。PDF/Markdown分列native、CLI尝试、已知报告USD及未知/未关联历史；见[模型报告包](../../docs/host-model-selection.md#a28报告包包含宿主模型记录)。

原A27项目已实际重导出，核心v8/快照与CLI2次/0.048195USD不变，新增调用/行动0，15份模型原件核对、四下载身份及2项证据/2项HTTP检查通过；5页PDF逐页实看无重叠/截断。实际导出下载使用本地HTTP，未验证浏览器点击，见[A28核对](../../runs/a28-model-report-20261104/validation.json)。

A29 [research_recipe](../../src/autoresearch/research_recipe.py)把明确的 `ordered_methods` 编译成原六字段 proposal 和独立 `research-recipe-decision-v1`。`ProjectController.advance_recipe`在真实 context 中选择一步，将完整配方 decision 存入原父请求；原 child、预算、事务与重放机制共用，不发送模型。范围/need/blockers及方法评价匹配控制可选项，跳过原因留存；报告 `input.recipe_selections` 保留原 context/decision，PDF/Markdown展示顺序与选择。队友原型固定版本、主线接入用法及本轮证据见[配方整合](../../docs/recipe-research/integration.md)，研究依据与历史失败仍见[原研究记录](../../docs/recipe-research/experiment.md)。配置分歧不证明研究收益。

- A30 [LocalWorkbench.recipes/advance_recipe](../../src/autoresearch/local_workbench.py)将两份固定配方接回原本地会话；GET用真实context编译且复核快照，POST复用原writer/活动项目/pending及A29控制器，不另建预算或执行账本。新HTTP路径见[接口](interfaces.md)。

- [ResearchProject.save_plan](../../src/autoresearch/research_project.py)将使用者编写的计划与修订理由保存到原项目`plan_revisions`，递增项目版本，沿原锁、事务、代码身份、未决执行和原ID重放机制。当前版本进入`ProjectController.selection_context`及现有宿主模型提示，页面读取和保存见[研究计划](../../docs/local-workbench.md#保存与修订研究计划)。


- 原始数据设计复用原step/controller，固定Ridge随机/分组CV适配器为`ridge_validation_adapter.py`，完整样本过滤统一，训练折独立预处理；`prediction_controls.py`仅消费保存OOF预测做折内重排。项目逐次保存Scaler/Ridge started/completed/failed，累计拟合预算与unknown预留不因改绑清零。见[研究设计](../../docs/research-design.md)。
