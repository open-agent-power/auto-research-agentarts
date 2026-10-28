# 开发边界与代码地图

## 从哪里改

| 工作 | 当前代码 | 对应验证入口 |
|---|---|---|
| 配方与提案契约 | `contracts.py`、`protocol.py` | `test_proposals.py`、`test_engine.py` |
| 预算、候选采用、恢复 | `engine.py`、`research_loop.py` | `test_engine.py`、`test_research_loop.py` |
| 模型HTTP边界 | `model_client.py` | `test_model_client.py` |
| 数据和领域计算 | `datasets.py`、`training.py`、`data/` | `test_datasets.py`与实际计算证据 |
| 证据快照与人工问题 | `reports.py`、`studio_project.py` | `test_studio.py` |
| 图表、PDF与附件 | `studio_outputs.py`、`paper_export.py`、`reproduction_verifier.py` | `test_paper_export.py`、`test_studio.py`及逐页渲染 |
| 本地界面与构建 | `frontend/src/`、`studio.py`、生成的`web/` | TypeScript检查、构建、实际浏览器路径、截图与持久化验证 |
| AgentArts本地入口 | `runtime.py`、`agentarts/` | `test_runtime.py`、本地HTTP探针 |

表中Python模块位于 `src/autoresearch/`，测试位于 `tests/`。运行、前端构建和报告依赖的命令见[README](../README.md)。测试里的fixture不算新增科学实验；图形与交互验收必须使用实际界面。

## 文件归属

- `src/`：已经接入产品的实现。参考代码不是下载后就放入src。
- `tests/`：与实际行为对应的契约、失败和恢复验证。
- `scripts/`：产品开发及验证工具；`agentarts/`保存平台适配和部署说明。
- `examples/`：可复用的请求与接入范例，不填私有凭据。
- `docs/`与`DESIGN.md`：版本化架构、设计、复用决策和开发说明。
- `frontend/`：界面源码、固定依赖与构建脚本；统一导入`docs/design/tokens.css`，生成服务所用的`src/autoresearch/web/`，不维护第二套手写运行CSS。
- `runs/`：本机实验、快照、数据库、图和导出；Git忽略，不随源码发布。
- `.agent/`：本地检查点与验证证据；Git忽略，不替代正式设计。

## 复用如何进入产品

先从工作区参考索引找到方法与入口 → 查固定版本、具体文件许可、输入输出和环境 → 以适配器接到现有契约 → 执行对应验证 → 在来源说明中记录实际复用。

三种记录各归一处：外部资源归参考库；为什么选以及怎么接归产品docs；真正使用的实现与依赖归src或项目依赖配置。不要复制整个上游仓库进产品，也不要将仅调研过的能力写成“已接入”。

## 前端与研究系统的边界

前端采用X6的节点、分组、相机与事件，保留Python后端及已有快照/保存/导出契约。构建链及锁文件位于独立frontend目录，生成资产仍由同源本地服务提供。布局保存独立于科学记录；当前实现以本浏览器存储为范围，不代表多用户或跨设备同步。

不先把Python包拆成一串微服务；不为了视觉重构更改Engine的数据协议、预算账本或原实验目录。新增布局存储与研究命令分别设计、验证，再连接界面。React Flow需要React，选它意味着明确的前端迁移决策。

## 一轮怎样收口

先确定一个可验证结果与允许修改路径；引用稳定架构和设计，不另写长计划。复用少量已有Agent并明确文件所有权。发现与当前结果无关的问题进入待办。

验证声明所对应的真实路径：持久化看重启，协议看请求响应，论文看数据和渲染，UI看实际截图与交互。源代码、截图和报告各自说明边界。完成后只提交本轮文件，检查本地SHA与剩余改动；推送、云端部署和收费调用遵守已有授权及费用上限。
