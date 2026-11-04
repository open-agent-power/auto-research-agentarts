# 组件搭建索引

当前前端为原生 TypeScript / DOM + X6，不是 React 组件项目。[依赖与构建](../../frontend/package.json)保存实际版本；先找已有实现，再决定是否抽取组件。

| 要搭建什么 | 优先复用入口 | 说明 |
|---|---|---|
| 当前 P02 五页及报告入口 | [p02-app.ts](../../frontend/src/p02-app.ts) | 当前展示主路径；不要只改旧通用页面后认为 P02 已更新 |
| 活跃项目、来源与检索 | [project-view.ts](../../frontend/src/project-view.ts) | `renderProject` 按观察kind显示P02 MAE、钢材MSE/MPa²、软件I/O检查；完整选区/方法条件/四处FTS共用，页面不执行研究 |
| 可操作本地项目五页 | [local-workbench.ts](../../frontend/src/local-workbench.ts)、[project-pages.ts](../../frontend/src/project-pages.ts) | 操作DOM只创建一次，五个hash页共用实际项目；`renderProjectPage`显式分派原section，不把CSV映射为历史P02 trials |
| 本地工作台的明确模型选择 | [local-model.ts](../../frontend/src/local-model.ts) | 位于研究页展开操作区，复用宿主原请求日志；显示累计grant、模型解释/控制器结果、CLI路由与原生/外部用量，沿原ID核对 |
| 本地工作台的确定性配方 | [local-recipe.ts](../../frontend/src/local-recipe.ts)、[local-workbench.ts](../../frontend/src/local-workbench.ts) | 原研究操作区预览两正式配方，按项目/版本/context核对；明确一步或等待，沿原请求恢复；选择记录由project-view区分配方身份 |
| 本地项目真实研究画布 | [project-flow.ts](../../frontend/src/project-flow.ts)、[c01-app.ts](../../frontend/src/c01-app.ts) | 复用C01Board/X6，显示实际课题/资料/行动/反馈/待办；原记录引用与项目包含关系分开，布局仅存浏览器 |
| 材料/软件独立项目入口 | [app.ts](../../frontend/src/app.ts)、[project-view.ts](../../frontend/src/project-view.ts) | `data-case=project`→`mountStandaloneProject`，沿用玻璃外壳，只保留可用项目入口，隐藏封存五页/全局搜索；P02仍由原shell挂载`#/project` |
| 当前快照报告与下载 | [project-view.ts](../../frontend/src/project-view.ts)、[project_workbench.py](../../src/autoresearch/project_workbench.py) | API的`report.available/stale`控制当前PDF/JSON，过期禁用；P02顶部封存PDF/ZIP保持独立，不能替代项目报告 |
| 历史通用页面与路由 | [app.ts](../../frontend/src/app.ts)、[pages.ts](../../frontend/src/pages.ts) | overview/research/experiments/knowledge/outputs/read；与当前页面共同核对 |
| C01 页面、行动与续算控件 | [c01-app.ts](../../frontend/src/c01-app.ts)、[c01-agent.ts](../../frontend/src/c01-agent.ts)、[c01-controls.ts](../../frontend/src/c01-controls.ts) | 案例专用能力，不能复制按钮就声称支持其他案例 |
| 画布节点、分组、缩放和布局 | [board.ts](../../frontend/src/board.ts)、[node-visual.ts](../../frontend/src/node-visual.ts) | X6 与已有卡片图示；布局状态与研究状态分离 |
| 当前 P02 卡片、预览与完整阅读 | [p02-app.ts](../../frontend/src/p02-app.ts) | `open()` 为预览抽屉，`read()` 为完整记录页；保留原对象身份和返回位置 |
| 历史通用/C01 分类与资料阅读 | [knowledge.ts](../../frontend/src/knowledge.ts)、[c01-library.ts](../../frontend/src/c01-library.ts) | 不把这些历史入口误当当前 P02 卡片的唯一实现 |
| 详情、引用、图表与格式化 | [content.ts](../../frontend/src/content.ts)、[dom.ts](../../frontend/src/dom.ts) | 复用 DOM 构造、数值/日期和外链处理 |
| 管线与表格研究阅读 | [p02-pipeline.ts](../../frontend/src/p02-pipeline.ts)、[p02-pipeline-research.ts](../../frontend/src/p02-pipeline-research.ts)、[p02-tabular-research.ts](../../frontend/src/p02-tabular-research.ts) | 显示原始记录，不补造评议或执行 |
| 数据类型与请求 | [types.ts](../../frontend/src/types.ts)、[api.ts](../../frontend/src/api.ts) | 同时核对[服务接口索引](interfaces.md)，不假定通用 api.ts 覆盖所有 P02 请求 |
| 材质、状态和响应式样式 | [styles.css](../../frontend/src/styles.css)、[令牌](../../docs/design/tokens.css) | 遵循[审美索引](aesthetics.md)，保留已认可的卡片和画布 |

## 修改路径

从当前入口找到调用方 → 复用已有块或抽取确有多个调用方的组件 → 改 `frontend/` 源码 → 按 package.json 检查/构建，生成 `src/autoresearch/web/`。不只手改生成资产。

业务状态、错误和空内容先核对真实接口；展示状态不要替代后台执行状态。实际改 UI 后按[审美索引](aesthetics.md)运行并看截图，验证本次改变的交互即可。

本索引记录现有组件入口，未创建新的组件库或替换前端框架。

A16 `project-view.ts`增加`data`域与`tabular_quality_audit`观察：逐列缺失/有限/零/范围、键/分组及代表重复坐标，沿原卡片与手机横向表格。目标/单位为声明，未声明键显示未计算，不套用P02终点；18790实际页面/3页匹配报告见[表格用法](../../docs/tabular-quality.md)。

A17 `grouped_quality_profile`观察复用原卡片及横向表格，显示完整/不完整组、每列事件/受影响组和代表坐标，键盘展开前序绑定；完整groups通过原行动JSON下载。18790当前4页报告及桌面/手机限定检查见[实际结果](../../docs/tabular-quality.md)。

A18 [local-workbench.ts](../../frontend/src/local-workbench.ts)由app.ts的`data-case=local-workbench`独立挂载，沿原玻璃外壳和保存结果reader；输入表单、角色勾选、宿主候选/理由、明确动作/等待/报告与原请求重试。样式仅限local-workbench，新动作不混入旧五页；桌面/手机实际操作与阅读见[用法](../../docs/local-workbench.md)。

A19 [local-evidence.ts](../../frontend/src/local-evidence.ts)作为同一工作台资料面板，共用父提交器的冻结请求、CSRF及忙碌状态；原件卡片、明确选区、取证任务和登记包下载沿原实色正文。登记与读取分成两次明确操作，后者仍走上方宿主真实候选；来源摘录与知识复用原reader，不增加第二条执行通道。

A20 [local-batch.ts](../../frontend/src/local-batch.ts)复用同一提交器，方法和确切未读收据默认不勾；显示授权上限/理由、逐步原父/子及停止原因。未完成批次可用宿主保存body/原ID明确恢复，允许切回原项目，其他新行动仍锁定；无浏览器定时执行器。桌面/手机与受控中断实际链见[用法](../../docs/local-workbench.md)。

A27 [local-model.ts](../../frontend/src/local-model.ts)复用同一页面提交器和宿主 `HostModelSelection`，默认只读已有记录。宿主启动时固定已有CLI后才可明确选择并执行一步；首次grant冻结，未知请求不重发，页面刷新不调用模型。原生Qwen与外部CLI启动/估值分别显示，完整原请求JSON可下载；核心PDF用量仍需外附host日志。五页导航和X6保留，实际hiMSC两次选择/反馈接续及启动说明见[工作台用法](../../docs/local-workbench.md#用模型选择并执行一步)。

A35同一模型面板使用“CLI配置阈值”，说明单次调用可能超出且现金结算未知；独立展示达到/超阈值、费用尚未核对的停止原因，每条原请求显示已报告估值，失败或无效回答也计入累计，未启动不填0。保留原grant、请求和发送门禁。A34真实合计0.124035USD超过0.10USD、第二次失败；A35不追加调用。静态页面更新不代表18791缓存的Python后端已加载修复，只读保存记录投影也不构成执行验证，范围见[用法](../../docs/local-workbench.md#a35阈值与费用提示)。
