# UI 参考与采用边界

目标是空气感的研究工作区：无限画布帮助组织课题、来源、假设、试验和论证；正文与论文保持清晰易读。当前 Python 后端、冻结证据和待执行问题的语义继续保留。

## 采用方向

- **采用 X6 + vanilla TypeScript**：节点、引用连线、分组、缩放及详情联动保留Python后端；esbuild构建和版本锁位于frontend。实际浏览器依赖的完整许可由构建归集到vendor-licenses.txt，不能都标成MIT。
- **React Flow 是备选**：只有决定迁移 React 后再采用。React Flow 依赖 React；同属 xyflow 的 Svelte Flow 是另一产品，不能混称。
- tldraw、AFFiNE、Excalidraw 优先作为交互参考。JSON Canvas 用于研究可交换格式，不充当画布渲染器。
- 不为了视觉样式并装多套画布或组件库；每次实现只验证一条完整研究路径。

## 参考清单

| 参考入口 | 可借用部分 | 许可及采用状态 |
| --- | --- | --- |
| [React Flow](https://reactflow.dev/learn)、[sub-flows](https://reactflow.dev/learn/layouting/sub-flows)、[xyflow](https://github.com/xyflow/xyflow) | 研究对象节点、父子分组、连接规则与视图控制 | 已确认 React 技术前提；所选包和示例文件许可待逐项核对。React 迁移后才进入候选。 |
| [tldraw](https://tldraw.dev/)、[许可说明](https://tldraw.dev/community/license) | 空间组织、选择与聚焦、工具栏和示例体验 | 已核查：默认开发使用；生产需有效 trial、commercial 或 hobby key。不能写成可免费商用。 |
| [AFFiNE](https://github.com/toeverything/AFFiNE)、[LICENSE](https://raw.githubusercontent.com/toeverything/AFFiNE/canary/LICENSE) | 文档与白板切换、资料卡与上下文侧栏 | 已核查：backend、common/native 适用单独许可，其余部分 MIT；不能称全仓 MIT。具体文件和版本仍需核对。 |
| [X6](https://github.com/antvis/X6)、[LICENSE](https://raw.githubusercontent.com/antvis/X6/master/LICENSE) | 图编辑器、分组和节点扩展；与现有后端薄适配 | 已采用3.1.8，主包MIT；实际依赖各自许可归集在vendor-licenses.txt，未使用其他库的商业模板。 |
| [JSON Canvas 1.0](https://jsoncanvas.org/spec/1.0/) | `nodes` / `edges` 与 text、file、link、group 节点的交换结构 | 已核查格式结构；它不是渲染引擎。导出映射、规范文本与代码的许可分别核对。 |
| [Excalidraw](https://github.com/excalidraw/excalidraw) | 草图表达、分组与低负担操作 | 所选组件、示例和素材许可待逐文件核对；不复制完整应用作为前置依赖。 |
| [Apple Materials](https://developer.apple.com/design/human-interface-guidelines/materials) | 控件层与内容层分工、材质的层次和可读性 | 已核查设计语义：Liquid Glass 面向控件与导航层，standard materials 可用于内容层；不是对全部透明材质的绝对禁令。仅借鉴原则。 |
| [Hype4 玻璃材质工具](https://hype4.academy/tools/glassmorphism-generator) | 模糊、透明度、边框与阴影的参数探索 | 视觉参考；生成内容、示例或资产若需复制，先逐项核对条款。 |
| [HeroUI Pro](https://www.heroui.pro/)、[Card](https://www.heroui.com/docs/components/card)、[Drawer](https://www.heroui.com/docs/components/drawer) | HUD 卡片、详情抽屉、状态与操作层级 | Pro、开源组件与具体示例分别核对；不能用组件库名称推定付费模板可复制。 |
| [Aceternity UI](https://ui.aceternity.com/)、[Magic UI](https://magicui.design/) | 少量聚焦、进入和反馈效果 | 所选组件与资产许可待逐文件核对；长时间研究阅读不采用持续装饰动画。 |

交互体验入口保留用户原始线索，未逐一完成浏览器体验或运行验证：[React Flow示例](https://reactflow.dev/examples)、[分组示例](https://reactflow.dev/examples/grouping/sub-flows)、[tldraw Showcase](https://tldraw.dev/showcase)、[X6示例画廊](https://x6.antv.antgroup.com/en/examples/)、[Excalidraw在线白板](https://excalidraw.com/)、[Aceternity组件](https://ui.aceternity.com/components)、[Magic UI组件](https://magicui.design/docs/components)。访问时按当前版本核对，不能据链接存在推定已体验或已复用。

## 视觉规则

1. **画布轻，内容实。** 底色 `#F4F5F7`，24px 点阵；点半径 1.25px。阅读面、证据正文、表格及论文预览默认实白。
2. **玻璃用于 HUD。** 导航与工具栏使用共享令牌：白色约 0.58、28px 模糊、155% 饱和度、20px 圆角；弱外边框、内高光和双层阴影维持层级。
3. **分组表达类别。** sage 组织资料与证据，sand 组织计划与假设，lavender 组织分析与成果。颜色不表示事实已成立、任务已执行或权限已授予。
4. **主次靠布局。** 画布组织研究流程与原始引用，抽屉提供预览，阅读和论文各有独立视图；不要把所有正文压在节点内。
5. **状态必须有文字。** fixture 决策、真实训练、未终测、待执行及接入暂缓等状态显式标注，不仅依靠颜色。
6. **焦点始终可见。** 令牌提供独立焦点描边与间距；实现时覆盖键盘焦点、缩放后命中区域及抽屉焦点回到来源的路径。

## 令牌使用

[tokens.css](tokens.css) 是实际构建共享的设计变量；交互由frontend源码实现，不能因新增一个令牌就推定对应能力已完成。

- `--ar-canvas-*`：画布底色与点阵；缩放策略由选定引擎实现后验证。
- `--ar-hud-*`：浮动控件材质；正文继续用 `--ar-content-surface`。
- `--ar-group-*`：类别背景与边框；状态和证据等级另有字段。
- `--ar-focus-*`：以后接到 `:focus-visible`，不移除浏览器默认焦点后留空。
- `--ar-motion-*`：仅供必要反馈；减少动态效果偏好下归零，不依赖动画才能理解状态。
- 不支持背景模糊或用户要求更强对比度时，HUD 降为实白并保留边界。

## 与研究数据的契约

- 节点和连线引用项目、来源、主张与试验 ID；空间位置不改写原始证据或候选采用记录。
- 保存布局与保存后续问题分开；移动卡片不触发模型请求、训练、终测或云资源操作。
- 导入、导出 JSON Canvas 需要单独做字段映射与 round-trip 验证；不预先承诺格式兼容。
- 文件节点只表达受控工件引用，不把模型提供的任意本机路径直接交给浏览器或后端读取。
- PDF 与复现附件保留自己的快照和校验关系，不以画布截图替代论文或实验结果。

## 后续实现的验收点

先确认引擎、版本、许可与最小适配，再检验：研究路径可读、正文可达、键盘可用、长卡片与长标题不截断、清晰的保存／失败状态、减少动态与模糊降级有效。

实际 UI 验收必须运行页面并查看完整及滚动截图；设计文件和令牌检查不能当作界面实现已通过。框架迁移、依赖引入及交互功能分别登记，不随本参考清单自动生效。
