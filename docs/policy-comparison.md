# 三任务的固定流程与条件选择比较

## 比较什么

| 任务 | 登记主方法 | 原有技术问题与保留范围 |
|---|---|---|
| P02 | `p02.saved-oof-residuals` | 对保存OOF做同规则内代理值残差诊断，再读取已有映射材料；不确认ALP或新生物终点 |
| 钢材 | `materials.saved-steel-audit` | 复核五份保存模型的训练/验证MSE及原1%采用门槛；MPa²、自定义组成划分，测试集只核对原已选基线 |
| 软件 | `software.source-integrity-check` | 一项正常I/O与四项受控故障，共五项；保留预期/实际反馈，不冒充生产事故或全面安全审计 |

两臂使用相同ResearchProject、允许工具、领域评价和结果解释代码，主方法预算1、来源读取上限8，每臂限定主方法与来源读取两项行动。实际每臂均为1次主方法、1次来源读取，新增模型调用、拟合与联网均为0。登记有原件I/O和哈希成本，不计为已提取观察，单独记录。

| 臂 | 一次项目内的调用顺序 | 保持的能力与边界 |
|---|---|---|
| fixed | `step → register-evidence → read-evidence` | 明确的强固定primary→source流程；同样检查来源、预算、失败和unknown，不故意忽略反证 |
| adaptive | `advance主方法 → 同版register-evidence → advance来源` | 使用当前条件选择和父请求冻结；每次advance最多派发一个合资格行动，不能重发未知或补造结果 |

这是同一工具内核上的调用/选择比较，不是两个独立LLM的推理试验。每题只有一个已登记主方法，且来源在主方法后才获得任务绑定；本次两臂均走相同路线。不能由此推断开放式策略或更丰富方法空间也无效，也不能为制造优势换输入、增加工具、删失败或临时修改策略。

## 执行前冻结

协议快照为`83c39979f51d2f98db3df99f17016207f98895fcb8d557754ab0552e49a0d194`。钢材另冻结包内数据依赖`bundled_dataset_dependency`的原gzip SHA、划分与版本；捕获的模型/描述包没有冒充包含全部原始数据。

| case顺序 | 臂的执行顺序 |
|---|---|
| P02 | fixed → adaptive |
| 钢材 | adaptive → fixed |
| 软件 | fixed → adaptive |

每臂的来源task_ref必须重新绑定其真实project/action，因此收据SHA和对象ID可不同；用原件SHA、实际定位和提交内容核对材料等价，不能把绑定差异说成研究差异。软件运行产生的时间戳、inode等元数据可随临时副本变化，原记录保留，比较case、预期错误、真实错误和passed，不要求这些环境值逐字相同。

## 调用入口

使用 `scripts/compare_project_policies.py --cases <JSON> --output <新目录>`。配置结构为`{"cases":[...]}`，恰含三个登记主方法、case ID唯一；每项含`id/method/source/evidence_bundle`，相对路径以cases.json所在目录为基准。P02来源用已封存OOF包，钢材/软件用prepare-source固定包，不重新拟合或联网取资料。runner先冻结原件和去task_ref后的manifest，再逐项目只替换实际任务绑定；claims、locators和原字节不改。

以下为本次已执行的原命令，配置和输出均保留在本机ignored runs；普通克隆不含这些材料：

这条命令会执行真实工具，并非只读status；当前输出目录已存在，重复调用已确认以退出码2和`OUTPUT_EXISTS`拒绝，既有文件不变。不要删除结果或换目录自动重试。运行布局为`protocol.json`、`inputs/<id>/`冻结材料、`arms/<id>/<fixed|adaptive>/project/`和绑定来源bundle，以及progress/results；失败时保存failure.json和部分记录，不自动恢复或替换项目。
