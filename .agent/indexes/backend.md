# 后端索引

本页导航现有实现；项目入口见 [docs/README](../../docs/README.md)。同一项目已连接登记白名单方法、条件选择一步、来源反馈与恢复；各领域Observation保留自身含义。开放式方法扩展、研究模型决策及跨域收益仍待实现/验证，目标设计见[自适应研究](../../docs/research/adaptive-research.md)。

架构基线见[底层模块与依赖](../../docs/architecture/foundation.md)和[状态/能力契约](../../docs/architecture/research-contracts.md)。已实现的是有限本地命令/目录与固定规则协调，不等于目标契约全部端口或LLM自主科研。

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
- [dossier_data](../../src/autoresearch/research_dossier.py) 汇总封存数据，[export_dossier](../../src/autoresearch/research_dossier_render.py) 导出报告；[build_handoff](../../src/autoresearch/chemotopo_bundle.py) 打包，[snapshot_viewer](../../src/autoresearch/snapshot_viewer.py) 验证并只读服务。见 [研究综合报告](../../docs/research-dossier.md)与[离线工作台](../../docs/portable-workbench.md)。

## AgentArts 边界

- [runtime.create_app](../../src/autoresearch/runtime.py) 是独立运行时适配边界；[AgentArts 目录说明](../../agentarts/README.md)和[C01 代码节点说明](../../agentarts/c01-sensitivity/README.md)记录已做工作。独立节点验证不等于产品运行时、Trace 或平台已集成；以实际证据为准。

后端接口或身份变化时同步 [接口索引](interfaces.md)及对应正式文档；选与修改相匹配的定点验证，涉及封存兼容时核对旧快照读取，不默认重跑全套。

- A16 通用表格方法：[tabular_quality_adapter](../../src/autoresearch/tabular_quality_adapter.py)接有界CSV/spec，保留原件/声明/坐标；[用法](../../docs/tabular-quality.md)。四登记主方法仍每项目择一，后续同项目多分析待建；不为新输入另建控制器。

A17 [grouped_quality_adapter](../../src/autoresearch/grouped_quality_adapter.py)为data主方法的条件化后续分析；同一step/controller显式绑定method、前序action/result与评价，原primary指纹兼容。`extend_local_budget`单独留痕并保留累计用量；upgrade不扩额度，unknown不允许新分析或额度修订。

A18 [LocalWorkbench](../../src/autoresearch/local_workbench.py)仅管理宿主输入、活动项目和报告索引；创建/选择/导出意图持久，partial保留不自动重做，实际advance仍走原ProjectController。最多32登记意图，上传不得指定路径；[用法](../../docs/local-workbench.md)，不另建研究控制器。

A19 `LocalWorkbench.register_evidence`将界面原件捕获到固定宿主目录，再调用原项目登记；冻结请求、原件SHA和核心回执，原ID可核对已提交核心结果，核心未登记的partial不自动补做。同项目未决登记拒绝替换ID；提取仍用原条件选择/来源预算。非P02在来源读取后恢复最近已完成分析的完整取证要求，包含后续方法新增问题；旧结果不回写。

A20 `LocalWorkbench.batch/batch_record`在原manager账本冻结有界grant及逐步意图/结果，复用`ProjectController.advance`；本地编排/核心/controller身份和原parent/child可核对。已完成批次原ID冻结回放，未完成只沿原ID显式核对，unknown不派发；不同步扩预算或授权未来资料。manager保存批次不替代核心执行真相，当前报告包与批次JSON分别取得。实际受控进程退出/重开及失败链见[本地用法](../../docs/local-workbench.md)。
