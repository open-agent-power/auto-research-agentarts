# G5-L 原生 CPU 整层接线独立审查

当前结论：**代码接线可进入相关回归与固定提交，之后再按独立冻结运行两个新课题。真实课题验收仍 pending。**

本审不新领租约，不编写实现，不运行真实 SciFact 索引／排名／评分、准备的调度 workload、
研究 fit 或产品模型 API，也不重复全套回归。纯检索／调度模块分别由
[检索专审](native-retrieval-review.md)和[调度专审](native-algorithm-review.md)核对；
此审查负责 registry／matcher／core／report、原件绑定、预算恢复及依赖兼容边界。

## 原生方法与保存证据

registry 仅增加两个显式 primary 和各自一个 saved audit；不能由输入选择模块、命令或可调用名。
每个 CPU project 只投影本 family 的 follow-up。matcher 要求同 project、source snapshot、
evaluation、observation producer／kind／scope。step 不凭 matcher 的文字断言执行：它从本项目 action
再次核完成状态、方法、精确 result SHA、evaluation，验证已捕获 envelope 的完整 canonical fingerprint
及 action／request／source／code headers，然后检查实际 ToolResult 的工具、状态、scope／source 和 eligibility。

只有这份已验证 ToolResult 传给 `execute_saved`。保存审计不通过通用 `execute` 重做实验，
不重建索引／排名／gold 评分、DP 求解或计时。core 仍为 source 身份校验读取原 corpus／qrels 字节；
这不等于新的来源内容提取 action，也不能宣称 audit 完全不读来源。

原 exclusive writer、先登记 running、unknown 不换 ID 重派、完整 artifact 恢复、精确请求重放、
累计 local tool 额度均保留。CPU primary 与 audit 各消费一个 local action，fit／source-extraction／model
成本投影分别为 0。新真实课题需在执行前单独固定 2 tools／0 source／0 fit／0 model API 预算；
工程夹具通过不替代该冻结，更不重置旧研究额度。

报告沿现有 collector／四文件 exporter 路径导出。完整排名、逐 query 指标、每次 schedule／计时、
坏例与原 asset／spec 仍在 JSON；Markdown／PDF 明确前 12 项是展示样本并给完整数组定位。
qrels 是 cited-document 标签而非 SUPPORT／CONTRADICT；原 metadata 仅保留，不用于排名评分。
排名先在内存形成完整指纹，再评分并随最终 action 持久化；不冒充先落盘 checkpoint、隐藏 gold 或 OS 隔离。
调度只称已知精确 DP 的合成工程对照，内部 bisect 比较仍未知，不把零全扫描当零 CPU 工作。

## 两项发现及关闭

**High：兼容 upgrade 绕过依赖漂移拦截。** 原新增代码只在 step 依靠 code identity 拦住新 runtime，
但旧 upgrade 可直接 stamp 当前 identity 并保留旧 `runtime_dependencies`，使不同 GroupKFold 实现
被当成兼容升级。最终版先精确回放历史 upgrade receipt；任何 fresh upgrade 在来源读取、
artifact／状态／预算写入前要求已登记 runtime 与当前完全一致。漂移与 legacy 未登记均
`RUNTIME_CHANGED`，不自动补历史版本或重新许可执行。same-runtime 源码升级仍保留累计 usage。

**Medium：installed metadata 与实际已载入版本可能不同。** 最终 `runtime_dependencies()` 获取实际
numpy／scipy／sklearn `__version__`，与各 distribution metadata 精确交叉核对；不一致直接
`RUNTIME_CHANGED`。该值参与 registry code identity，新 project 另存观察到的 runtime 字段。
这解决本实现的版本身份记录，不构成运行环境 sandbox 或对旧代码记录的追溯改写。

新增工程测试覆盖 dependency-only step 拦截、漂移／unknown upgrade 的全树／状态／预算不变、
same-runtime 使用不重置、旧 receipt 跨后续版本变化仍只读重放及 loaded／installed 不一致。
最终 `test-cpu-projects-04.log` 实际 **9 项通过**；本审核对日志及源码，没有重跑。

G6 已保留真实跨版本反例：分组 ID 正确但 sklearn 1.9.1 相对 1.8.0 改变 Concrete 808 行、Real Estate
252 行 fold，partition 也不同，Slump 不变。独立完整数组比较在
`runs/g4-native-integration/cross-version-split-review.json`。历史用途的精确环境恢复原 fold，
不删除 1.9 失败、不声称重现 OOF 预测，更不凭新 guard 宣称旧项目自动兼容。

## 源码及验收状态

最终 core 文件 SHA：

| 文件 | SHA-256 |
|---|---|
| `method_registry.py` | `1f3c6e0dc23df197fe38b596ee666c6d6804edda8963c6b932c43ad048c53b8f` |
| `research_methods.py` | `854d8fbaef43d680a54c5dc893d9d2616cfed45809c4db8e0dec14b353495679` |
| `research_project.py` | `b4a183b9b1cab2059c5b453986f6570603a743f00832070e35e51978aa95a679` |
| `project_report.py` | `6a05c4aee76bdc8f36d56cf562f70988b686ead1a55be0206da304a6774050ff` |
| `cpu_report_sections.py` | `a7be068d80562f062d8341ac3e7817d181f4314946bf4d8a9fc15fb7a7903e5f` |

9-test 日志 SHA：`964c2113691530c9af600b8d36c14b44e234b228975f525cc39b62cf5629aa97`。
正式总审原件 `runs/g5-native-core-review/review.json` 记录这组 core、两个 adapter／kernel 和测试的完整 SHA。
独立只读全树比较再次确认 292 个旧 case 文件与已批准 VM 快照一致，旧 Ridge module 仍为精确
`ec965e31…69711`；未改旧 case、旧研究预算或冻结 G4 controls。

下一步须由 root 做相关回归、固定 source release，再冻结真实两个 case 的完整输入、评价、
预算／保护及资源上限。真实 plan-v2 需先观察 primary 的实际坏例／反馈，再选择 saved audit，
完成原件、报告、原 ID 无重算恢复及独立数值核验后才能验收原生连续研究。
本静态 READY 不等于原生两课题已执行、不代表自动 Agent 科研质量、完整 G5 或 OS／sealed Gate 通过。
