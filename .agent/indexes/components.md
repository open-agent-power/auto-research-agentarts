# 组件搭建索引

`research-design.ts`在原输入映射表单新增固定log1p与已选原训练列复选框，草稿、绑定恢复、无效选择阻断和真实模型项预览共用原工作流。被取消训练的变换列保留草稿并提示恢复后取消，不静默降为raw；结果／比较／报告区分原CSV、log1p项和父版／均值参考，见[固定映射](../../docs/research-design.md#固定log1p原输入变换)。

`project-view.ts`质量数值表复用`resultTable`的语义行表头，仅该表加`quality-numeric-table`。横向滚动固定字段列，使右端有限范围仍能对应材料／目标；≤720px首列140px并保留完整换行。其他结果表及研究状态不变，样式沿既有实色内容token。

`local-model.ts`在原模型操作区显示可展开的方法成本表，当前context须匹配项目／版本／快照，CLI关闭仍可阅读。历史计划分别处理readiness v1／v2，缺成本不猜值；手机局部横向滑动与原表格样式复用，见[方法额度](../../docs/method-budget-costs.md)。

`local-experience.ts`在知识空间提供显式案例导入、原观察／范围／限制、可读方法条件与协议、资格历史及JSON。`project-pages.ts`复用原focus路由直达`#/knowledge?focus=experience`；草稿和原请求恢复仍由`local-workbench.ts`管理。沿既有表单与表面，不另建主题；见[案例用法](../../docs/project-experience.md)。

`research-design.ts`新增直接输入/固定单列三次基选择，原CSV字段与展开模型项分别展示；多列cubic停用保存，直接输入提交省略可选字段。资源导入导出保留`comparison_kind`。双类对照分别命名为同协议特征对照与同评价划分输入基对照；父版判断与单项训练均值参考分开说明，见[研究设计](../../docs/research-design.md)。

`research-design.ts`在严格父子特征对照下显示输入列选择、保存误差主表及可展开的均差/逐行变化副表；两表复用`metricTable`与局部横向滚动，各自提供手机滑动提示。选择只重绘已收到的`input_profiles`，不提交或执行，见[研究设计](../../docs/research-design.md)。

计划原文与当前事实分开显示：[local-workbench.ts](../../frontend/src/local-workbench.ts)保留制定时原文，另从已完成来源行动显示当前读取／选区数量与最新未决项；不据此推断先后或科学确认。[project-view.ts](../../frontend/src/project-view.ts)的`sourceQuestionText`复用精确中文释义，未知问题保留原文，来源卡去重展示且保留完整原数组。两处共用同一问题显示方式。

“继续研究”复用[local-batch.ts](../../frontend/src/local-batch.ts)与原操作区，显示计划方式、执行方式及原阶段记录；[local-workbench.ts](../../frontend/src/local-workbench.ts)按原body确认丢失回执并恢复同ID，[local-model.ts](../../frontend/src/local-model.ts)仅对该任务关联的原计划请求放行核对／采用／拒绝。刷新不执行，其他新请求保持原锁。见[操作用法](../../docs/local-workbench.md#继续研究选计划再按授权行动)。

`project-view.ts`沿现有实验卡显示`numeric_association`的总体结论、分组成对指标、不可计算原因和CSV定位；原行动及匹配前序质量结果可下载。总览摘要、候选、配方、batch和画布使用对应方法名称；PDF／Markdown沿`project_report`展示同一保存结果。实际桌面、手机横向表格及五页／X6已核对，详见[数值关联用法](../../docs/numeric-association.md)。

当前前端为原生 TypeScript / DOM + X6，不是 React 组件项目。[依赖与构建](../../frontend/package.json)保存实际版本；先找已有实现，再决定是否抽取组件。

| 要搭建什么 | 优先复用入口 | 说明 |
|---|---|---|
| 当前 P02 五页及报告入口 | [p02-app.ts](../../frontend/src/p02-app.ts) | 当前展示主路径；不要只改旧通用页面后认为 P02 已更新 |
| 活跃项目、来源与检索 | [project-view.ts](../../frontend/src/project-view.ts) | `renderProject` 按观察kind显示P02 MAE、钢材MSE/MPa²、软件I/O检查；完整选区/方法条件/四处FTS共用，页面不执行研究 |
| 普通项目总览的可读进度 | [project-view.ts](../../frontend/src/project-view.ts)、[local-workbench.ts](../../frontend/src/local-workbench.ts)、[project-pages.ts](../../frontend/src/project-pages.ts) | 三块扁平展示研究问题、保存工作与当前下一步。local-workbench传入现有context，schema/项目/版本匹配后显示候选，project-pages按focus定位原计划或展开操作区，读取仅作展示 |
| 研究者意见 | [local-workbench.ts](../../frontend/src/local-workbench.ts)、[project-view.ts](../../frontend/src/project-view.ts)、[project-pages.ts](../../frontend/src/project-pages.ts) | 原研究页表单保存作者、评论、后续建议及可选行动绑定，总览显示最近2条并可展开原记录，`focus=feedback`定位表单。复用草稿与原ID恢复，回执不明时只读确认保存记录；意见标为未核验研究者陈述，工程联调与真实用户反馈分别记录 |
| 可操作本地项目五页 | [local-workbench.ts](../../frontend/src/local-workbench.ts)、[project-pages.ts](../../frontend/src/project-pages.ts) | 操作DOM只创建一次，五个hash页共用实际项目；`renderProjectPage`显式分派原section，不把CSV映射为历史P02 trials |
| 本地工作台的明确模型选择 | [local-model.ts](../../frontend/src/local-model.ts) | 位于研究页展开操作区，复用宿主原请求日志；显示累计grant、模型解释/控制器结果、CLI路由与原生/外部用量，沿原ID核对 |
| 本地工作台的确定性配方 | [local-recipe.ts](../../frontend/src/local-recipe.ts)、[local-workbench.ts](../../frontend/src/local-workbench.ts) | 研究正文显示当前有效版本和采用理由；原操作区核对保存的外环input.json，再显式采用或记录回退。预览包含有效配方和两份示例，以id＋version区分，刷新使旧核对失效并保留草稿，已保存轮次停用重复采用。后续一步仍须明确提交，沿原请求恢复 |
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

普通项目总览由project-view显示已采用计划版本、步骤及理由预览，按原数组取方法末3条和来源末2条保存记录，并依据匹配的context显示候选与阻塞。未收口执行优先提示核对原请求，计划预期反馈及保存未决问题继续展示，范围及资源完整内容折叠保留。project-pages处理`focus=plan/operations`，复用原DOM和草稿，操作区定位后展开并聚焦summary。前端四门禁、桌面及手机8张最终截图、键盘链接与深链接刷新、草稿保留、三个结果入口及五类客户端状态展示已核对。两端无页面横向溢出，A64/A63 core及Host完整值一致，读取过程POST为0。方法卡与配方RSI外环继续归队友，使用说明见[总览进度与下一步](../../docs/local-workbench.md#总览页的当前进度与下一步)。

A16 `project-view.ts`增加`data`域与`tabular_quality_audit`观察：逐列缺失/有限/零/范围、键/分组及代表重复坐标，沿原卡片与手机横向表格。目标/单位为声明，未声明键显示未计算，不套用P02终点；18790实际页面/3页匹配报告见[表格用法](../../docs/tabular-quality.md)。

A17 `grouped_quality_profile`观察复用原卡片及横向表格，显示完整/不完整组、每列事件/受影响组和代表坐标，键盘展开前序绑定；完整groups通过原行动JSON下载。18790当前4页报告及桌面/手机限定检查见[实际结果](../../docs/tabular-quality.md)。

A18 [local-workbench.ts](../../frontend/src/local-workbench.ts)由app.ts的`data-case=local-workbench`独立挂载，沿原玻璃外壳和保存结果reader；输入表单、角色勾选、宿主候选/理由、明确动作/等待/报告与原请求重试。样式仅限local-workbench，新动作不混入旧五页；桌面/手机实际操作与阅读见[用法](../../docs/local-workbench.md)。

A19 [local-evidence.ts](../../frontend/src/local-evidence.ts)作为同一工作台资料面板，共用父提交器的冻结请求、CSRF及忙碌状态；原件卡片、明确选区、取证任务和登记包下载沿原实色正文。登记与读取分成两次明确操作，后者仍走上方宿主真实候选；来源摘录与知识复用原reader，不增加第二条执行通道。

A20 [local-batch.ts](../../frontend/src/local-batch.ts)复用同一提交器，方法和确切未读收据默认不勾；显示授权上限/理由、逐步原父/子及停止原因。未完成批次可用宿主保存body/原ID明确恢复，允许切回原项目，其他新行动仍锁定；无浏览器定时执行器。桌面/手机与受控中断实际链见[用法](../../docs/local-workbench.md)。

A27 [local-model.ts](../../frontend/src/local-model.ts)复用同一页面提交器和宿主 `HostModelSelection`，默认只读已有记录。宿主启动时固定已有CLI后才可明确选择并执行一步；首次grant冻结，未知请求不重发，页面刷新不调用模型。原生Qwen与外部CLI启动/估值分别显示，完整原请求JSON可下载；核心PDF用量仍需外附host日志。五页导航和X6保留，实际hiMSC两次选择/反馈接续及启动说明见[工作台用法](../../docs/local-workbench.md#用模型选择并执行一步)。

A35同一模型面板使用“CLI配置阈值”，说明单次调用可能超出且现金结算未知；独立展示达到/超阈值、费用尚未核对的停止原因，每条原请求显示已报告估值，失败或无效回答也计入累计，未启动不填0。保留原grant、请求和发送门禁。A34真实合计0.124035USD超过0.10USD、第二次失败；A35不追加调用。静态页面更新不代表18791缓存的Python后端已加载修复，只读保存记录投影也不构成执行验证，范围见[用法](../../docs/local-workbench.md#a35阈值与费用提示)。
