# 表格质量反馈驱动后续选择：最小设计草案

**状态：仅设计，尚未实现或授权新的研究行动。** 本文提出一个供未来新项目显式启用的通用机制：在质量行动之前固定有限质量条件，行动完成后读取其原始保存结果，并由原 Controller 在通过时选择同源数值关联候选，否则等待。这是机械质量观察驱动的路线选择，不是科学假设已经得到验证、来源或领域用途已获批准，也不是模型自主判断。已完成的 Bike 2011 是人工选择、反馈和计划修订；不能在其行动之后补造事前登记、升级原 pin 或重开 2/2 预算。

## 现有能力与缺口

- [`tabular_quality_adapter`](../../src/autoresearch/tabular_quality_adapter.py) 保存行、列、重复、键、分组、数值列计数及 flags 等机械 profile。其默认 `next_decision` 等待来源、单位、分组及科学资格核对；空 flags 不证明这些事项。
- [`research_methods.numeric_feedback_eligible`](../../src/autoresearch/research_methods.py) 在完成质量行动后，主要依据已声明数值目标及另一数值列提供关联资格；它不是研究者的质量门。现有 [`ResearchProject.step`](../../src/autoresearch/research_project.py) 复核后续候选绑定的原质量 action ID、result SHA、source 和工件，并执行原预算与版本门。关联候选不能由新策略凭空创建。
- [`hypothesis_feedback`](../../src/autoresearch/hypothesis_feedback.py) 的现有登记和读取绑定检索 primary、validation 配对差和检索家族协议；其联合条件仅支持既有 staged 家族。[`feedback_policy`](../../src/autoresearch/feedback_policy.py) 的已知分支只允许等待或相应检索 saved-audit，未知总是等待。它们的事前登记、原请求绑定与三态反馈模式值得复用，现有合同**不能直接接受表格质量 profile 或关联方法**。
- [`ProjectController.advance_feedback`](../../src/autoresearch/project_controller.py) 使用封存 context 和原选择入口，保留父子行动、状态版本和预算；[`project_selection`](../../src/autoresearch/project_selection.py) 对 context 的可选字段与形状有严格校验。新增类型须显式扩展 validator，不能把未经验证的自由文本塞进现有检索反馈。
- [`record_feedback`](../../src/autoresearch/research_project.py) 保存与 action 关联的研究者陈述，标记为 `unverified_researcher_statement`；`save_plan` 保存四字段操作者计划及可选 experience case 引用，并不提供质量 action/result 的结构化计划引用。两者不是质量结果的自动核验器。

## 第一增量：计划不变时的显式质量策略

新增独立版本的表格质量登记及只读 reader，先保持它与检索登记及其 v1–v3 wire 合同分离；具体 schema 和方法名以实现评审为准，不借用检索指标名来表示表格计数。新登记只用于新项目、须在所指质量 Controller 请求出现之前保存，并绑定原 Project/run、source packet/snapshot、声明 scope、原计划版本和 SHA、代码身份、质量候选、预定质量 Controller 请求 ID，以及固定条件和分支。登记及同 ID 原请求冲突沿既有持久化与版本规则；未知或已使用的身份不可换 ID 补登记。

条件采用上限固定的有序 AND 列表，使用有限白名单，而不是任意 JSON 路径、Python、表达式或调用方可改的 evaluator。首版可覆盖 profile 的 `rows`、`columns`、`exact_duplicate_rows`、键的 incomplete/duplicate/conflict 计数、组的 incomplete/group_count/min_group_size、保存 flags 列表的空/非空状态，以及**已声明数值列**的 finite/empty/declared_missing/invalid_numeric/nonfinite 计数。比较符和有限非负整数阈值需严格校验；为表达完整性，可提供明确的 `rows` 引用作比较右值，不允许任意字段间计算。`tabular_quality_adapter` 的 flags 是去重且最多保留 64 项的有界列表，并非全量异常总数；首版仅判断保存列表为空或非空，不将其长度解释为异常总数。此为设计候选，字段上限与 schema 须在实现前固定；不需要把某个研究的行数、列名或分组数写进产品代码。

质量结果须由只读 reader 从原 Project 读取：核对事前登记、原 Controller parent 的完整请求与 sealed context、唯一普通 child、SQLite 请求指纹、source/scope、评价身份、原工件封套、action/result SHA 及代码身份，再提取有限质量字段。不得重新执行 adapter 或依据调用者提供的 profile 直接判定。字段缺失、错误类型、布尔冒充整数、非有限数、工件/身份不一致、行动未完成或仍未决均不能作为通过；合法零是已知数值，不能补作缺失。损坏的登记本身应按原登记的错误合同拒绝读取，而不是静默当成有效登记。

结果按以下顺序判断：

1. 有任一必需值或绑定未知/无效时为 `unknown`，即使另一项已知不满足也不提前判为不通过；保留原因。
2. 所需值与绑定均有效且所有固定条件成立为 `condition_met`。
3. 所需值与绑定均有效但至少一项不成立为 `condition_not_met`。例如有效的 `group_count` 未达到事前阈值属于已知不满足；若 `group_count` 或其他必需字段本身缺失、损坏或类型不符，则为 `unknown`。

首版只允许 `condition_met` 映射到同源的现有 `data.numeric-association`，另外两种状态固定等待。映射不是强制继续：若缺少资格、源/代码不一致、Project 有 blocker、剩余额不足、候选不存在或不唯一，也等待或按原合同拒绝，并保留原因。策略只从新的 sealed selection context 中选择**方法、evaluation_ref、原质量 action ID 和 result SHA 均精确匹配**的唯一候选，再交由原 `advance_selection` 完成接受、版本、预算、父子与 dispatch；不得直接调用 adapter 或重建候选。该关联候选在当前实现中成本为 1 本地工具、0 拟合、0 native evidence，仍须核对实际 context 的条件和预算；登记、只读反馈及等待本身不派研究工具，不授权模型请求。

第一增量要求当前计划仍与登记时的原计划 SHA 完全一致，沿用现有策略的保守语义。人工意见可以作为明确标记的未验证陈述保存，但不得替代原工件判断。该范围实现“质量观察决定可选下一行动”，**不声称实现质量后先保存新计划再选择**。

## 后续计划修订与原计划绑定

Bike 的人工链在质量后保存原行动反馈和有差异的 plan v2，再从新 context 选择关联。现有 `feedback_policy` 对当前 `research_plan` 要求与登记时 `plan_sha256` 一致；简单复用时，plan v2 会使策略等待。不能为了支持修订而删除这项绑定，也不能从计划自然语言声称已建立原观察关联。

如后续确需在选择之前保存 plan v2，须单独设计 opt-in 的结构化引用：同时核验登记时历史计划版本/SHA、后续计划版本和原请求、质量 action ID/result SHA、登记或反馈 ID/SHA 及其发生顺序；引用必须指向同 Project 的原已完成结果，变更、缺失或未知则等待/拒绝。自由文本中的引用和 `record_feedback` 的未验证陈述不能独立证明该绑定。应验证并发写入、状态新鲜度和重放，不改变现有检索策略对原计划的约束。该扩展不是第一增量已实现的承诺。

## 边界与恢复

质量 profile 不能核实外部许可、上游目标含义、采样独立性、实际组编码或因果关系。来源、许可证、单位和分组定义仍须另行由授权操作者核对；机械门没有输出可解释组编码时，不能凭组哈希推断它。未知优先、等待与预算边界不能被解释为领域验证或对模型/研究收益的证明。

这是**显式调用该策略时**的选择规则。现有直接 `advance_selection` 或 `step` 入口不会自动服从这个新策略；除非另行设计并验证全入口门禁，不能称质量条件是全局强制。现有 Controller 对 `prepared`、`running` 或 `unknown` 父请求的原 ID 续接可能再次进入 child 或 dispatch；若新合同要求不明即停，必须在调用执行入口前只读检查并显式守卫，不能把同 ID 重放一概称为只读。终态回执可按原绑定核验；中断、缺 body 或 source/code 漂移时保留原状态并停查，不换 ID、Project、source pin 或增加预算。

新模块、validator、Controller 或 Project 身份计算的变化可能改变 producer/core 身份。默认旧登记、旧 context 字节与旧项目行为须维持；旧 pending/unknown 继续使用其原 pin，新功能不得借兼容升级重开历史预算。对外的 CLI、Workbench 和报告若随后接入，须分别保持旧形状并明确新增字段；第一增量不自动承诺 UI、HTTP 或模型采纳。

## 最小合成验收

只使用隔离合成 Project 和独立工程预算，保留原请求/结果/失败；不读取真实 Bike、派发其 Project、调用模型或拟合。至少覆盖：

- 条件通过时，事前登记 → 原质量行动 → 已核验反馈 → 原计划不变的新 context → 唯一绑定关联候选；两项工具和 0 model/fit/native evidence 分别核原账本。不通过和 unknown 均等待且保留剩余额。
- 合法零、缺失字段、非有限值和错误类型；有效 `group_count` 未达事前阈值为 not-met，而必需字段缺失为 unknown；已知不满足与未知并存时未知优先。flags 仅检查有界保存列表的空/非空，不作为全量异常计数，也不代替字段或来源审查。
- 登记在行动后拒绝；不同 Project/run、计划、source/scope、context、质量 parent/child、SQLite 指纹、结果工件、评价或候选参数漂移时不派发；缺候选、多个候选、blocker 和预算不足时不派发。
- 同 ID 同 body 的终态核对与异 body 冲突；在接受后、child 前和结果完成而回执缺失等窗口模拟中断，核实不明状态不由新入口偷偷重发。新方案支持何种跨进程恢复，必须以实际测试为准，不以纯函数或同进程测试冒充。
- 对旧检索 v1–v3 的序列化、反馈、分支及旧 pin 只读状态做适当回归；确认未启用的项目无新字段或默认行为变化。若实现后支持计划 v2 结构化引用，还需单独验证历史计划和修订链，不以人写的 plan 文字代替。

合成通过仅证明受测机制和边界，不证明真实课题收益、来源合法性、模型自主采纳或 OS 级隔离。
