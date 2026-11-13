# 开发边界与代码地图

开发任务先用[Agent 导航](../.agent/README.md)和[开发提醒 Skill](../.agent/skills/research-dev-router/SKILL.md)选入口。当前目标和分工见[提交计划](research/submission-plan-20261130.md)，职责与目标接口见[底层架构](architecture/foundation.md)和[研究契约](architecture/research-contracts.md)。这些入口随源码分发，主开发本机计划的归属见[文档说明](README.md)。

## 从哪里改

当前开发从统一项目、计划、模型建议和工作台进入。新工作区的创建、计划及意见操作见[本地工作台](local-workbench.md)，队友的持续配方与RSI任务见[长期任务书](recipe-research/team-module-handoff.md)。

| 工作 | 当前代码 | 使用与验证入口 |
|---|---|---|
| 项目、计划和研究者意见保存 | [research_project.py](../src/autoresearch/research_project.py)、[local_workbench.py](../src/autoresearch/local_workbench.py)、[project_workbench.py](../src/autoresearch/project_workbench.py) | [计划与修订](local-workbench.md#保存与修订研究计划)、[研究者意见](local-workbench.md#记录研究者意见)，`test_research_project.py`、`test_local_workbench.py`、`test_local_workbench_http.py` |
| 模型计划建议、采用和拒绝 | [research_plan_proposal.py](../src/autoresearch/research_plan_proposal.py)、[host_model_selection.py](../src/autoresearch/host_model_selection.py) | [模型建议入口](host-model-selection.md#根据真实反馈建议研究计划)，`test_research_plan_proposal.py`、`test_host_model_selection.py` |
| 注册方法与下一步选择 | [research_methods.py](../src/autoresearch/research_methods.py)、[method_registry.py](../src/autoresearch/method_registry.py)、[project_controller.py](../src/autoresearch/project_controller.py) | 原项目selection context与显式执行，`test_research_methods.py`、`test_research_project.py` |
| 有界CPU研究与保存审计 | [检索](../src/autoresearch/retrieval_adapter.py)、[调度](../src/autoresearch/scheduling_adapter.py)、[报告投影](../src/autoresearch/cpu_report_sections.py) | 同一原生生命周期；`test_cpu_projects.py`验证双领域/预算/unknown/恢复/依赖边界，真实运行另按[合同](execution/g5-local/native-integration-contract.md)冻结 |
| 配方修改候选与允许工具验证 | [recipe_change_proposal.py](../src/autoresearch/recipe_change_proposal.py)、[recipe_improvement_adapter.py](../src/autoresearch/recipe_improvement_adapter.py) | [适配接口](recipe-research/team-module-interface.md#主开发的配方改进适配接线)，`test_recipe_change_proposal.py`、`test_recipe_improvement_adapter.py` |
| 五页工作台、计划和反馈展示 | [local-workbench.ts](../frontend/src/local-workbench.ts)、[project-pages.ts](../frontend/src/project-pages.ts)、[project-view.ts](../frontend/src/project-view.ts)、[project-flow.ts](../frontend/src/project-flow.ts) | [总览与下一步](local-workbench.md#总览页的当前进度与下一步)，前端格式、Lint、类型检查及真实页面验收 |

### 专项实现

| 工作 | 当前代码 | 对应验证入口 |
|---|---|---|
| P02回传资料到模型评议的持续工作流 | `evidence_workflow.py`、`source_assessment.py`、`scripts/continue_evidence_workflow.py` | 单个工作流复用同一累计预算与账本；[证据回传](evidence-submission.md) |
| 已执行的P02来源、数值迭代与交接展示 | `chemotopo_studio.py`、`snapshot_viewer.py`、`frontend/src/p02-app.ts` | 封存来源一致、真实页面路径与截图；[独立工作台](portable-workbench.md) |
| C01来源字节与原始字段核验 | `c01_source_audit.py`；`scripts/audit_c01_sources.py` | `test_c01_source_audit.py`、[作者快照与真实对照](source-audit.md) |
| C01证据约束研究与导出 | `c01_research.py`、`c01_research_outputs.py`、`c01_research_verifier.py` | `test_c01_research.py`、`test_c01_research_outputs.py`及独立复算 |
| C01持续执行及记忆使用 | `c01_model_loop.py`、`c01_memory_context.py`、`c01_memory_loop.py` | `test_c01_model_loop.py`、`test_c01_memory_context.py`、`test_c01_memory_loop.py`；本机脚本服务限定 |
| 资料原文与工作台来源阅读 | `knowledge.py`、`knowledge_browser.py`、`c01_studio.py` | `test_knowledge.py`、`test_knowledge_browser.py`和真实同一语料浏览 |
| 配方与提案契约 | `contracts.py`、`protocol.py` | `test_proposals.py`、`test_engine.py` |
| 预算、候选采用、恢复 | `engine.py`、`research_loop.py` | `test_engine.py`、`test_research_loop.py` |
| 模型HTTP边界 | `model_client.py` | `test_model_client.py` |
| 数据和领域计算 | `datasets.py`、`training.py`、`data/` | `test_datasets.py`与实际计算证据 |
| 证据快照与人工问题 | `reports.py`、`studio_project.py` | `test_studio.py` |
| 图表、PDF与附件 | `studio_outputs.py`、`paper_export.py`、`reproduction_verifier.py` | `test_paper_export.py`、`test_studio.py`及逐页渲染 |
| 本地界面与构建 | `frontend/src/`、`studio.py`、生成的`web/` | TypeScript检查、构建、实际浏览器路径、截图与持久化验证 |
| CSV与捕获原工作簿核对 | `workbook_projection_adapter.py`、`research_project.py`、`research_methods.py` | `test_workbook_projection_adapter.py`、`test_project_workbook_projection.py`；[使用与边界](workbook-projection.md) |
| AgentArts本地入口 | `runtime.py`、`agentarts/` | `test_runtime.py`、本地HTTP探针 |

表中Python模块位于 `src/autoresearch/`，测试位于 `tests/`。运行、前端构建和报告依赖的命令见[README](../README.md)。测试里的fixture不算新增科学实验；图形与交互验收必须使用实际界面。

统一项目控制器已接通有限注册方法、来源、计划修订、模型建议和意见保存，具体运行范围见[工作台用法](local-workbench.md)与[模型接入](host-model-selection.md)。主开发继续负责这些公共入口及页面整合，队友负责方法知识、配方RSI的采用或回退、有效版本和后轮管理，实际接线按[接口约定](recipe-research/team-module-interface.md)推进。

P02、C01与钢材专项保留各自的数据、账本和结论。C01验证器限定8合金、4特征、4终点，P02代理目标仍待作者导出映射。领域有效性和真实用户收益继续依对应证据确认，平台接入沿既有暂缓安排。

## 文件归属

- `src/`：已经接入产品的实现。参考代码不是下载后就放入src。
- `tests/`：与实际行为对应的契约、失败和恢复验证。
- `scripts/`：产品开发及验证工具；`agentarts/`保存平台适配和部署说明。
- `examples/`：可复用的请求与接入范例，不填私有凭据。
- `docs/`与`DESIGN.md`：版本化架构、设计、复用决策和开发说明。
- `frontend/`：界面源码、固定依赖与构建脚本；统一导入`docs/design/tokens.css`，生成服务所用的`src/autoresearch/web/`，不维护第二套手写运行CSS。
- `runs/`：本机实验、快照、数据库、图和导出；Git忽略，不随源码发布。
- `.agent/README.md`、`indexes/`与批准的`skills/`：共享开发导航和提醒；正式设计仍在docs。
- `.agent/focus.json`、工作台选择、预算、worktrees和artifacts：本机状态与验证证据，Git忽略。

## 复用如何进入产品

先从工作区参考索引找到方法与入口 → 查固定版本、具体文件许可、输入输出和环境 → 以适配器接到现有契约 → 执行对应验证 → 在来源说明中记录实际复用。

三种记录各归一处：外部资源归参考库；为什么选以及怎么接归产品docs；真正使用的实现与依赖归src或项目依赖配置。不要复制整个上游仓库进产品，也不要将仅调研过的能力写成“已接入”。

## 前端与研究系统的边界

前端采用X6的节点、分组、相机与事件，保留Python后端及已有快照/保存/导出契约。构建链及锁文件位于独立frontend目录，生成资产仍由同源本地服务提供。布局保存独立于科学记录；当前实现以本浏览器存储为范围，不代表多用户或跨设备同步。

不先把Python包拆成一串微服务；不为了视觉重构更改Engine的数据协议、预算账本或原实验目录。新增布局存储与研究命令分别设计、验证，再连接界面。React Flow需要React，选它意味着明确的前端迁移决策。

## 一轮怎样收口

先确定一个可验证结果与允许修改路径；引用稳定架构和设计，不另写长计划。复用少量已有Agent并明确文件所有权。发现与当前结果无关的问题进入待办。
