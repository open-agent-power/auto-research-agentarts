# 研究状态与能力契约

## 对象边界

已实现的[历史方法案例快照](../project-experience.md)使用原记忆条目及方法卡，新增的是目标项目不可变`experience_revisions`与受控封套资产。资格变更增state，active摘要仅进入独立context；源case／action不能成为目标`evidence_citation_ids`或`feedback_action_ids`。源库与目标副本分别撤回，旧Host及报告保留当时内容。

| 对象 | 职责 | 最小字段 |
|---|---|---|
| Project | 长期研究问题、来源与累计资源的归属 | id, goal, research_status, scope, source_refs, budget_ids, state_version |
| Run | 一段有起止和执行配置的研究尝试 | id, project_id, execution_status, policy_ref, method_instance_refs, budget_id |
| Action | 已接受的研究或执行命令记录 | id, project_id, run_id, request_id, command, parameters, status, result_refs |
| Observation | 工具或人工取得的观察及出处 | id, action_id, producer, evidence_refs, values, interpretation_status |
| MethodDefinition | 可复用研究设计的版本定义 | id, version, question, conditions, inputs, steps, evaluation, limits |
| MethodInstance | 方法在具体项目条件下的绑定 | id, definition_ref, project_id, input_bindings, parameters, evaluation_ref, scope |
| SkillRef | 研究运行中可引用的操作指南 | id, version, purpose, instruction_ref |
| Tool | 实际执行能力及输入输出契约 | id, version, input_contract, output_contract, execution_mode |

Project不等于一次模型会话；Run不等于新的项目或新的预算。
Action描述实际接受的行动，Observation描述所得内容；一项行动可产生多项观察，也可能尚无结果。
模型提案和解释可作为行动内容保存，不因入库成为已确认观察。
MethodDefinition可以由人编写，MethodInstance可以由控制器选择并绑定；两者不等于执行成功。
运行时Skill可以指导具体操作，不把一整篇指南直接当成可比较的研究设计。研发Agent的索引/提醒Skill属于开发配置，不混入本项目的科学证据或评价。
Tool提供读取、计算或外部操作；Method说明为何以及在何条件下使用它。

## 项目状态与运行状态

Project的研究状态只需先区分active、waiting和stopped，另附reason与待办。
active表示仍在推进；waiting表示等待资料、人工决定或外部结果；stopped表示当前目标暂不继续。
stopped不表示科学问题已解决；若恢复继续，应留下一项明确状态变更记录。
Run单独记录执行状态，例如运行、pending、完成、失败或需要人工处理，并保存具体原因。
Run完成可以只是请求预算用尽，Project仍可能active或waiting；一次执行失败也不自动停止项目。
异步工具pending表示已有操作等待结果，不是失败；Project可继续执行与它无冲突的行动。
任何“研究成功”都需要评价证据，不能从这两类状态直接推导。

## 长期归属、策略与作用范围

来源引用来自Project的source_refs，Run与方法实例选择其明确版本，不各自生成无来历的副本。
SourceRef至少保留id、原始URL或合法来源标识、内容身份、版本及定位；本地路径只用于私有加载。
新来源加入项目时形成有出处的变更；历史Run继续引用原版本，不能被后来的来源替换。
budget_id必须从Project已登记资源中选择；启动Run不重置额度，也不暗中创建新授权。
预算服务同时记录可用、预留和已知消耗；未知消耗不能归零后重新使用。

PolicyRef至少包含id、version、configuration_ref与applicability_scope，表示本次选择策略而非模型权重。
Run固定所用策略版本，策略修订产生新版本；旧选择和结果不回写。
作用范围描述任务、数据条件及允许能力；不同范围的策略效果不直接混为总体能力提升。
模型身份、推理设置与执行代码身份属于Run配置，和策略版本分别记录。

## 条件检查：适用、不适用与未确定

条件检查返回结论、理由、所据来源及尚缺信息，而非仅返回一个布尔值。
uncertain允许提出补证请求、先运行低成本检查或交给用户决定，不机械地永久硬阻断。
not_applicable应指出具体冲突；satisfied仅表示所列条件满足，不保证方法成功或科学有效。
例如ALP身份未知时，确认ALP终点的条件为uncertain、执行资格未满足；明确限定的红通道代理值诊断仍可单独检查资格。若要求把代理值残差直接当ALP效果结论，该用途为not_applicable，因为现有证据类型不支持；不把未知当作已证伪。

```python
check = methods.check_conditions(definition_ref, project_snapshot, bindings)
# check: outcome, reasons, evidence_refs, missing_information, next_checks
if check.outcome == "uncertain":
    proposal = controller.choose_evidence_check(check.next_checks)
# 选择补证也是提案，须通过普通command提交后才会执行。
```

跨域实例化要确认endpoint、unit、sample及批次/重复的对应关系，必要时附转换依据。
不能把不同终点都塞进一个宽泛target字段，就声称能够比较或迁移。
若对应关系未知，保留未知和范围限制；单位转换、聚合或样本映射本身也是可追溯操作。

## 最小query接口

Query只读已保存状态或登记能力；不发送模型请求、不执行工具、不产生新观察。
查询返回快照身份，供后续command说明它依据哪个状态作出选择。
方法匹配在此仅查询目录与已知条件；需要模型选择、联网检索或获取新来源时，经command登记和计费，不能藏在只读query内。

```python
project = projects.get(project_id)
run = runs.get(run_id)
options = methods.match(project.snapshot_ref, need)
action = actions.get(action_id)
result = executions.get(operation_id)  # 查询已有操作，不重新提交
report_data = projections.read(project_id, snapshot_ref)
```

检索可返回来源片段、定位、内容身份和相关性说明；相关性不是证据有效性。
检索结果不会直接写入confirmed memory；须区分原文主张、工具核验观察与未审定解释。
条件记忆的晋级或退役需要单独的有依据变更，查询与展示不能隐式触发。

## 最小command接口

每个command有独立request_id；同一命令的恢复沿用该ID，不把网络重试当新行动。
幂等键同时绑定命令名、参数与项目身份；同ID同内容返回已有结果，不重复执行。
同ID不同内容返回冲突，不能覆盖原请求。新的研究决定使用新ID并引用前置行动。
涉及状态前提的command带expected_state_version，过期时返回当前状态供重新判断。

```python
run = runs.start(project_id, budget_id, policy_ref,
                 request_id=start_id, expected_state_version=project.state_version)
spec = methods.bind(definition_ref, bindings, evaluation_ref)  # 纯值构造，不落库/执行
accepted = actions.submit(run.id, spec, tool_command,
                          request_id=action_request_id,
                          expected_state_version=run.project_state_version)
# accepted: action_ref, execution_ref, status；接受不等于完成。
```

command在发送前持久化身份与所需预留；实际发送未知时保留unknown，不自动重发。
已收到响应但尚未提交行动，可按保存响应恢复处理，不新增模型请求或工具执行。
有外部幂等键的工具也需保存该键及回执；不能仅因暂时没有回执就假定执行失败。
上述bind只构造设计；方法实例在行动接受时登记并绑定版本。工具执行、项目状态变更和记忆更新保留明确的command记录。
重放检查先于状态新鲜度检查：同ID同内容的已提交行动，即使当前state_version已前进，也返回原行动；未提交的新行动才检查版本与条件。Action同时保存请求指纹、输入/方法/评价版本及execution_ref，不能仅按工具名去重。

## 工具结果与异步执行

工具输出保留领域语义，不将科学负结果、工具异常和未获得结果混成一个failure分数。

```python
ToolResult = {
    "operation_id": "...", "status": "completed | pending | failed | unknown",
    "observations": [], "evidence_refs": [], "artifacts": [],
    "metrics": [], "failure": None, "continuation_ref": None,
}
```

同步结果可立即携带观察；异步结果返回operation_id及可查询状态，后续用同操作身份收取结果。
pending不触发重新执行；超时先查询或标未知，不能默默提交第二份计算或外部实验。
工具失败保留类型、阶段和已产生工件；部分结果不自动变成完整实验，也不直接丢弃。
指标携带名称、值、单位、endpoint、样本/分组范围、比较对象和评价版本。
工件携带内容身份、格式与产生行动；大数据可用引用，摘要不能替代完整结果。
“MAE更差”是有效观察；“命令未执行”是执行问题；“无ALP映射”是资格缺口，分别反馈。

## A0：首个适配入口及真实来源

| 现有入口 | 输入与约束 | 已有输出或错误 | 统一接口的责任 |
|---|---|---|---|
| `prepare_source(source_study, iteration_directory)` | 已停止的`ConfiguredStudy`，恰好一个完成候选及匹配的`iteration.json`；核对账本读取前后身份 | `p02-diagnostic-source-v1`，含inputs、candidate、iteration、scope、snapshot_sha256 | 后续受控来源准备；只允许宿主解析登记资产，不接受模型自由路径，不重建冻结历史 |
| `validate_source(payload)` / `_joined(payload)` | 精确四规则；同一材料键覆盖；候选target/fold与输入一致；目标/预测有限数值；无重复键 | 正常无返回值；显式校验失败为`ResearchError(EVIDENCE_CHANGED)` | 适配前验证内容身份；不能把损坏来源降级成正常数值结果 |
| `inspect_residuals(payload, dimension)` | dimension仅`topography`或`chemistry`；四种模型的保存OOF预测 | `p02-residual-diagnostics-v1`；summary、完整groups/rankings/rows；残差=预测−目标；new_fits=0 | 包装为completed及有范围的Observation；完整结果作为工件，摘要仅供决策 |
| [DiagnosticStudy.apply](../../src/autoresearch/diagnostic_research.py) | request_id、观察SHA、允许动作及宿主来源/最近行动绑定；每分组在该专项中最多一次 | 同ID同内容replayed；同ID异内容`IDEMPOTENCY_CONFLICT`，另有`STALE_OBSERVATION`、`ACTION_NOT_AVAILABLE`、`NOT_ACTIVE` | 只借鉴已有事务/幂等行为；专项次数、方向枚举和2..6请求上限不作为通用研究限制 |

纯函数无request_id、operation_id、持久化、pending或unknown，正常返回结果，否则抛异常。统一执行器负责记录操作、预留和结果；已知执行失败映射failed并保存原code/type/phase，未处理的I/O、解析或结构异常也不能伪造为空结果。上述包装和统一错误映射仍待实现。

本机已保存来源按下面身份对应，均在ignored `runs/`，普通克隆不包含。SHA中的`snapshot`是规范化内容身份，与文件字节SHA分别核对；不能将两者混用。

| 工件/字段 | 具体位置或身份 |
|---|---|
| scope.study_configuration_sha256 | `582a851767ab2fd4e549d59a82477dbfa6ef47a772c190c3bb460c27a6b181c8` |
| scope.candidate_action_id / candidate_result_sha256 | `p02cfg-416e13884cd84dd4b9855203ebf45ab2` / `e02e7d31052fd6cca0831699a157cad3d9cac3b96b1fb8aea803e1fa00406736` |

这组scope整体进入Observation的evidence_refs/范围，不能只留下候选名`alpha05`；模型原始理由单独保存。现有`DiagnosticStudy._state`还核对冻结代码身份；后续统一适配器应版本化读入，不通过修改旧配置解除`CODE_CHANGED`。

## A2：两个方法实例怎样使用同一能力接口

下列ID为待实现目录的设计名。两者共用来源、条件、行动与观察接口，保留各自的领域输入及结果，不能把来源判定换成MAE。

| 绑定 | `p02.saved-oof-residuals` | `p02.source-mapping-check` |
|---|---|---|
| 待决定问题/终点 | 当前alpha0.5相对同规则化学基线的误差分布；终点为同section平坦对照归一化的原红通道代理，未确认ALP | 指定主张是否有作者原件中的对象→通道→导出列→工作簿目标对应；终点是这条映射的证据资格，不是新的生物效应 |
| 单位与样本单位 | 比值，无量纲；每行一个`(topography, chemistry)`材料组合，每规则870键；不是细胞/spot独立重复 | 每条带准确定位的映射主张；单元格/原文片段是证据单位，不是实验样本；物理测量单位未知时原样保留 |
| 批次/分组 | 原三批次及section已按规则聚合；35折整纹理留出，化学组只是内部切片；无spot级重复 | B8S1等sheet名保留为来源标签；原始图像/实验批次及重复的对应关系仍未知，不从命名自动推出完整批次映射 |
| 处理规则 | 四规则全保留：`recorded_equal_batch`、`recorded_equal_section`、`positive_equal_batch`、`positive_equal_section`；同规则内比较，不跨目标选最佳MAE | 原字节和公式/缓存身份保留；文本按物理行定位；不执行公式、不补作者聚合定义；缺实际导出时形成取证任务 |
| 比较对象 | chemistry基线为主要参照；另保留additive、interaction_alpha1及current_candidate，固定评价版本 | 待核对主张与原文/字段/单元格逐项对应；开发助手索引与作者原件分开，保存管线配置与实际运行导出分开 |
| satisfied | 保存输入、scope、完整预测和同规则基线匹配，可做限定代理值诊断 | 指定主张、合法来源和可读取定位齐全，可以执行该范围核对；不意味着映射已支持 |
| uncertain | 预测/基线或终点绑定尚未提供，先请求缺项；ALP目标尚缺映射时不执行ALP解释 | 缺作者导出列、通道/对象或批次链，返回明确缺口与下一项取证；已有片段仍可阅读 |
| not_applicable | 只有聚合MAE而没有逐行OOF，或已知换了终点/键且不可配对；当前工具不能处理 | 已知提交材料属于另一数据集/对象，或现有提取器不支持定位类型；不据此判定原研究主张错误 |

Observation不是只保留这一条有利或不利摘要：四规则、全部组和逐行结果继续挂在同一工件。负的研究结论不改变`status=completed`；“误差更差所以模型无用/测量错误”仍是需另存并核对的解释。

## 四条路径与恢复时的状态归属

| 路径 | Project / Run / Action变化 | 观察及下一步 |
|---|---|---|
| 正常取得结果 | Project保持active；Run running；Action accepted→running→completed；提交一次后state_version前进 | 保存完整结果和范围，策略引用该Observation再提交新ID的下一行动；Run结束不自动停止Project |
| 结果反对原方案 | 执行状态仍completed，Project可继续active；不把不支持原方案的结果计为failed | 原目标和评价冻结，记录反证；解释/修订另存，转误差诊断、来源核对或等待，不靠改指标晋级 |
| 条件缺失或不适用 | 条件检查为uncertain/not_applicable时不提交原数值/ALP行动；保存检查依据；无可做动作则Project waiting及reason，Run可结束 | 无数值成功观察；另提交补证/读取行动可completed，仍缺映射则等待；新资料形成新版本后重查条件，不覆盖历史 |
| 执行中断/恢复 | 有持久operation_id且已知仍运行才为pending；实际发送/计算结果不明为unknown，Run needs_review；Project在无独立可做工作时waiting | 先查同一operation/request。完整结果核验后只提交一次；已received响应离线处理；未知保留预留与预算，不重发或新建目录重试 |

上述状态为统一应用层设计。实际[C01LocalLoop](../../src/autoresearch/c01_local_loop.py)的`_reserve/_received/_consume/run`使用`sending→received→applied/invalid`请求账本：`sending`残留要求`NEEDS_REVIEW`；`received`可离线恢复；`DiagnosticStudy.apply`已提交而请求账本尚未更新时靠原request_id重放。不能将旧`sending`无条件改成pending，也不能把模型请求无效写成已经执行的工具失败。

纯同步OOF工具不产生原生pending回执。后续执行器若在计算前已记running却中断，先核对保存结果；没有足够证据则unknown。其无副作用不授权后台静默重算，更不能借恢复重跑冻结拟合。来源提取不支持的locator保留具体`UNSUPPORTED_LOCATOR`和已支持范围，不把未读内容塞入Observation。

## 反馈、解释与只读投影

执行器保存原始结果，控制器据此选择下一检查、修订方法实例或暂停，并引用实际反馈。
Observation保留producer与核验范围；模型从观察推导的机制解释单独保存为待审定判断。
人工修正也单独记录，不能算作模型自主改善或改写原始理由。
报告与画布是Project/Run/Action/Observation的projection；读取、排版和移动节点不产生事实。
报告可展示已保存解释及来源，但不能通过摘要把未确定关系写成已确认结论。
projection注明快照与覆盖范围；发布状态不是研究完成状态，旧报告也不自动包含后续行动。

## 设计轮验收范围

先用一个现有真实任务走查这些对象和命令，确认能表达输入缺口、实际反馈和暂停恢复。
只确认契约足够表达需求，不在本设计轮声称控制器已接线、跨域迁移有效或平台已接通。
保留现有冻结来源、历史账本和费用边界；后续实现按[计划](../plan.md)逐项交付。

以上保留设计轮的验收范围。当前已实现的项目、控制器、计划与配方接线以[工作台说明](../local-workbench.md)和[实际RSI接续](../recipe-research/rsi-delivery.md#a64有效v2的实际后续行动)为准，真实研究能力、多轮改进与平台交付的剩余项统一见[提交计划](../research/submission-plan-20261130.md#近期待办)。
