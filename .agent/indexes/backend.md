# 后端索引

本页导航现有实现；项目入口见 [docs/README](../../docs/README.md)。同一项目已连接登记白名单方法、条件选择一步、来源反馈与恢复；各领域Observation保留自身含义。开放式方法扩展仍待实现，有界模型选择的跨域收益仍待验证，目标设计见[自适应研究](../../docs/research/adaptive-research.md)。

架构基线见[底层模块与依赖](../../docs/architecture/foundation.md)和[状态/能力契约](../../docs/architecture/research-contracts.md)。已实现的是有限本地命令/目录、有界选择与既有执行协调，不等于目标契约全部端口或LLM自主科研。

## 项目与状态

- 本地项目：[ResearchProject](../../src/autoresearch/research_project.py) 的 `create/status/step/resume` 保存单Run、行动/方法实例、完整工件、反馈与固定策略下一决定；最初的[saved_oof_adapter](../../src/autoresearch/saved_oof_adapter.py)保留P02保存OOF语义。见[用法与边界](../../docs/project-slice.md)：不导入历史请求计数，不调用模型；HTTP仅作只读投影，unknown不自动重算。
- 同项目来源：`upgrade/register_evidence/read_evidence/attach_evidence/evidence_task/method_options/knowledge`；[source_evidence_adapter](../../src/autoresearch/source_evidence_adapter.py)捕获任务绑定原件并提取选区。登记只做原件I/O/哈希/收据，不扣提取次数；读取才创建行动/观察和FTS，原attach保留兼容。[research_methods](../../src/autoresearch/research_methods.py)匹配条件，[project_knowledge](../../src/autoresearch/project_knowledge.py)检索真实选区，来源观察不批准终点。
- A7 注册方法：[method_registry](../../src/autoresearch/method_registry.py)只允许 P02、[钢材模型复核](../../src/autoresearch/steel_audit_adapter.py)、[软件原件捕获检查](../../src/autoresearch/source_integrity_adapter.py)三个主方法，经同一 ResearchProject 的事务、恢复和预算执行。来源任务使用通用 research.source-selection（旧 P02 ID 保留），失败收据不自动重试，不把各领域塞入共同科学终点。
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
