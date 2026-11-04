# 队友当前任务：补齐 B8S1 从实际运行到工作簿的证据

日期：2026-11-04。对象：负责资料核对和真实任务反馈的队友。

**这次请查清：哪一次实际运行、哪份导出和哪一步工作簿转换，产生了 hiMSC B8S1 中的零值与行对应。先交两条能定位的样例；找不到原记录，就交清楚的证据缺口。**

## 原配方任务已经做到哪里

配方模块、两份配置、编译脚本和原九项专项测试已有交付；A29 已接入主控制器，A30 已在五页工作台实际完成分组→读取作者来源→等待及原 ID 重放。具体范围见[接入记录](recipe-research/integration.md)。不需要再开发同一模块、重交 PR 1/2，或重跑人工 8 行夹具；这些工程记录还不能证明真实研究收益。

2026-11-04 已按授权合并[PR #1](https://github.com/1263-ux/auto-research-agentarts/pull/1)和[PR #2](https://github.com/1263-ux/auto-research-agentarts/pull/2)，两者现均为 merged/closed；PR 2 从原依赖分支改为面向 main 后合并，原 head `03b08048/13054f5` 未变。远端 main 为 `61a79ed2ddf56f3654b633e30cd30a30b1e6b778`，内容与已检查的 PR 2 head 一致，原九项测试和 format/lint/typecheck 均通过。合并没有补出新的领域反馈。

本机 A29–A48 开发仍未发布到远端；普通远端克隆不包含这些轮次新增的工作台能力或本机 `runs/`。本页当前说明、保存证据和取证包由主开发另行交接，不把远端配方原型当作本机完整产品。

## 先用已有材料，不重复索要

已有 CSV/spec、原工作簿、保存的质量/分组结果、context 和 11 月 1 日审查笔记继续使用；请先读[hiMSC 来源核对](himsc-source-audit.md)的“下一份材料要回答什么”和 A38 段。

主开发补交的当前取证包包含作者原工作簿 `hiMSC_Raw_Data.xlsx`、元数据 `CTC_Image_Metadata.xlsx`、现成的 `zero-rows.csv`、`zero-metadata.csv` 和静态导出配置/出处。两份工作簿是本次补交的归档副本；来源 URL 与归档许可说明随包保留。普通源码克隆不包含 ignored `runs/`，不要求你重跑得到这些材料。

当前已知事实：

- 59 条记录的 Count、红强度、绿强度同时为 0，CSV 与原工作簿保存值一致；零值原因仍未知。
- 216 条同序记录是原表 Chem 0、元数据 Chem 28；作者材料名称提供线索，尚无本版逐行转换依据。
- `Series/Row` 和 `Topo/Chem` 连接有多解，保存行序不能直接充当图像或对象身份。
- 静态 `ExportToSpreadsheet` 保存配置为 `NaN`、前缀 `B10Pos`；它不是 B8S1 的运行回执，也不证明发生过 NaN→0。

## 首先找这一条链上的原记录

先在已给资料和作者一手材料中定向查找，最多追这三个缺口，不另写综述：

1. **实际运行。** 与 B8S1 对应的运行 ID/时间、实际配置版本、原图文件名及图像/对象 ID；`Series/Row` 在该次运行中具体指什么。
2. **实际导出。** 同次 `CellsGreen/CellsRed/Image` 原导出，保留列头、对象/图像关联字段和原保存文本；找出 Count 与两强度对应哪些列、无对象或缺失怎样写。
3. **工作簿转换。** 从导出到 B8S1 的列选择、聚合、过滤、缺失/零值规则和版本记录；若解释 Chem 0/28，还须说明适用版本与逐行对应依据。

这是找新增的运行与转换证据，不是再索要已经取得的 CSV 或工作簿。来源若受限，记录可分享范围和取得方式，不代替作者补写规则。

## 先手工只读核对两条样例

只查看原文件保存值和已有坐标表，不改值、补值、删行或重排；不要求启动服务、模型、CellProfiler或重新计算旧审计。

**样例一：普通编码下的全零。** 原表 `B8S1!D2:F2` 三值均为 0，Topo/Chem 为 `1/24`；元数据同序行 2 保存 `Series=0, Row=1`。仅按 Topo/Chem 有元数据行 `2、38、74` 三个候选，不能直接选行 2 当作唯一图像。

**样例二：编码冲突区的全零。** 原表 `B8S1!D472:F472` 三值均为 0，Coordinate 为 `3_0`；元数据同序行 472 保存 `Series=470, Topo=3, Chem=28, Row=5`。原 Chem 0 没有对应候选，不能先改成 28 再宣布连接成功。

每条都按同样方式填写：

1. 记下工作簿版本、sheet/格号、原保存值及 `zero-rows/zero-metadata` 对应行。
2. 用取得的运行/图像/对象 ID 找到实际导出位置，抄下原列头和值；有多个候选就全列出，找不到就写缺哪一个 ID。
3. 沿转换记录逐步对应到 B8S1，记录哪里可确认、哪里冲突、哪里仍未知。若取得同次运行的一条非零记录，可再加一条对照；没有同次证据就不凑第三条。

每个判断附原 URL、版本/日期和页码、单元格或文本行号；“保存配置如此”与“该次确实如此运行”分别写。

## 什么结果会改变下一决定

- 找到可唯一绑定的真实运行与转换记录：只对证据覆盖的行说明零值来源，下一步交作者/领域队员核对，再判断是否适合后续分析；本次不改数据。
- 找到版本冲突、多候选或不同赋值规则：保留冲突，下一步查具体版本/运行，不把所有 0 统一改缺失，也不自动执行 Chem 0→28。
- 找不到：交回查过的入口、实际结果、缺失文件/字段，以及缺它为何不能判断；下一决定可以继续等待。不要用通用 CellProfiler 说明冒充本次运行记录。

材料只能支持它覆盖的结论；ALP 身份、单位、独立样本和作者确认仍按原缺口保留。

## 怎样交回资料

先交完整返回目录和一份可分享的来源/结论摘要。字段沿用[证据返回说明](evidence-return.md)：真实提交者、来源、带定位的发现、未决问题；原件放普通返回目录的 `sources/`，不进 PR。`observed/unresolved/conflicting` 按实际填写，找不到也可交。

现有返回/接收包的 `task-binding.json` 只对应其原封存任务，保持不变；不能复制 R80/P02 绑定冒充当前 hiMSC。没有当前 hiMSC 绑定时，先按上述来源、发现、问题字段交完整普通目录，由主开发核对后按当前项目创建新来源收据。接收方式见[evidence-intake](evidence-intake.md)，本轮不要求你运行 intake 命令。

### 后续文档 PR

资料先交接。后续取得并确认远端 main 的 `61a79ed2ddf56f3654b633e30cd30a30b1e6b778` 后，从该提交独立开 `docs/himsc-run-followup` 分支，只改新的随访说明与来源索引；摘要写明出处、实际发现、下一决定与限制。不要从旧 head `13054f5` 或已合并 PR 2 的分支继续叠 PR，不自动 push/merge；本机尚未发布的功能由主开发另行同步。

本轮必要检查是文件/坐标能定位、样例与原记录一致，以及文档的 `git diff --check`；不用再跑旧测试或夹具。开发者仍遵守仓库强制 format/lint/typecheck，本轮由主开发统一执行，不要求资料队友搭开发环境。

## 可顺手做的一条使用反馈

你本人先写“目前我会采取的下一决定和理由”，再读当前报告，记录决定是否变化、依据哪条记录，并填“有帮助／无帮助／无法判断”。保留日期、实际身份和核对范围；无需编造耗时。它是实际使用反馈，模型自评不代替这份反馈，也不能冒充独立领域评价。

## 2026-11-03 原任务记录

以下第 1–11 节保留当时任务与命令，供核对原设计。文中的“拟新增”“目前还没有实现”“本文尚未执行”等仅描述 2026-11-03 当时状态；对应模块、原九项测试及 A29/A30 接入已完成，现状以上文和接入记录为准。下方两次 PR、夹具及运行步骤不属于本轮待办，不需再执行。

## 1. 我们推进的三个概念，各要做出什么

| 概念 | 用普通话解释 | 你要交的东西 |
|---|---|---|
| 科研配方 | 为一个问题写清：需要什么材料、先做什么、怎样判断结果、下一步怎么办 | 一份方法说明、两份可读取的 JSON 配方 |
| 方法适用条件 | 不是任何数据都能套任何方法；单位、样本、分组、来源不清时，要先补证据 | 一张“可用／不可用／缺什么”的说明，至少一个不适用例子 |
| 反馈后调整 | 得到结果后，依据具体证据改变下一步；没有依据就等待 | 一段实际的“输入→检查→反馈→下一决定”记录 |

第一版配方只负责**在程序已经允许的候选中，按配置选一个或等待**。完整的研究设计还要在说明里保留问题、样本、单位、评价和不能外推的范围。别把两份 JSON 当成通用科研能力已经完成。

### 已经有什么，缺什么

已经有：研究项目保存与恢复、方法条件检查、候选清单、外部选择提案、真实工具执行和结果记录。相关实现见 [project_controller.py](../src/autoresearch/project_controller.py)、[project_selection.py](../src/autoresearch/project_selection.py)。

已经比较过固定流程和条件选择，限定设置下两边走了相同路线，**没有观察到优势**，见[原比较说明](policy-comparison.md)。本次不要照着重跑同一套比较。

本次要补：

1. 人能编辑、程序能读取的配方；
2. 配方和现有候选接口之间的一小段转换代码；
3. 同一份候选下，两份配方确实产生不同选择的证据；
4. 真实问题中，这个选择是否有用、还缺什么依据的记录。

现有 [workbench_recipe.py](../src/autoresearch/workbench_recipe.py)处理工作台发布配置，不能把它当作已经实现的科研配方执行器。

## 2. 分工和工作顺序

| 负责人 | 负责什么 | 第一轮范围 |
|---|---|---|
| 你：队友 | 资料核查、方法条件、配方说明、独立小模块、实验与结果 | 下文两次 PR 的文件 |
| 主开发者 | 现有项目内核、执行器、预算和状态接口，后续接入界面 | 协助解释接口和合并；保留五页导航与画布 |
| 能判断课题的人 | 核对真实问题的字段含义、来源解释和下一决定 | 找得到老师/领域队员就记录实际反馈；找不到就明确写缺少专业判断 |

建议按四个工作段推进，不设虚假的完成日期：

1. 先读入口和已有资料，选定一个真实问题，提交 PR 1 草稿；
2. 补齐最关键的来源与不适用条件，定下两个配方；
3. 写最小转换模块，做必要检查和一次隔离实验，提交 PR 2；
4. 用真实资料核对下一决定，把支持、反证或无法判断的结果补进 PR 2。

资料核查与原型可以并行。不要等读完全部参考库才开始，也不要同时重构内核或前端。

## 3. 先读哪些资料

### 产品仓库内，按顺序读

1. [受限选择提案](project-selection.md)：看清 context、candidate、proposal 各负责什么。
2. [表格质量与分组核对](tabular-quality.md)：输入怎样声明、两个工具实际计算什么。
3. [已有比较](policy-comparison.md)：避免重复已经没有区分度的实验。
4. 开发前读 [Agent 导航](../.agent/README.md)及其中的开发提醒，按任务选接口和评测索引。

### 已有研究资料，定向阅读

完整 ICT 工作区里的资料位置如下；它们**不随产品 Git 克隆分发**。你之前收到的资料可以直接使用，但先核对名称和版本。

| 先后 | 工作区资料 | 要回答的问题 |
|---|---|---|
| 1 | [复用总索引](../../../references/auto-research/REUSE-INDEX.md) | 哪些资料与当前小功能有关？不用通读全部档案 |
| 2 | [配方可行性审查](../../../references/auto-research/11-recipe-feasibility/2026-11-01/README.md) | 哪些是已有证据，哪些仍是假设？ |
| 3 | [工作流优化核查](../../../references/auto-research/11-recipe-feasibility/2026-11-01/evidence/01-workflow-optimization.md) | 反馈到底改变什么？成本怎么计算？ |
| 4 | [科学评测核查](../../../references/auto-research/11-recipe-feasibility/2026-11-01/evidence/02-science-evaluation.md) | 怎样区分程序通过与研究结论可信？ |
| 按需 | [迁移、RAG 与 RSI 的反例](../../../references/auto-research/11-recipe-feasibility/2026-11-01/evidence/03-transfer-rag-rsi.md) | 哪些泛化和自我改进说法不能直接成立？ |

拿不到本地资料时，先使用下面的原始来源，不必停止全部工作。它们是已有笔记采用的版本，阅读不代表我们已经复现：

- [AFlow v4](https://arxiv.org/pdf/2410.10762v4)：关注预设方法空间、反馈、搜索成本。
- [GEPA v2](https://arxiv.org/pdf/2507.19457v2)：关注如何根据轨迹修改，以及组合后退化的情况。
- [ScienceAgentBench v3](https://arxiv.org/abs/2410.05080v3)：关注数值和工件检查，以及任务能力的范围。

笔记不等于附带了所有全文。如果仍缺材料，交回具体文件名和影响的问题；主开发者提供可分享的摘录、来源表和原始链接。不要把整套第三方仓库、权重或受限全文塞进 PR。

## 4. 你自己找资料时，只补这三个空缺

| 空缺 | 要找的具体证据 | 交回格式 |
|---|---|---|
| 反馈怎样改变下一步？ | 一项真实任务中的输入、检查结果、支持/反证，以及因此改变的行动 | 在 gaps.md 写一条完整例子；指出原文或字段位置 |
| 方法什么时候不能用？ | 一个方法的一手说明，以及一个违反其前提的例子 | 写清单位、样本/分组、来源或评价缺失时，为什么等待/换方法 |
| 比固定流程有用在哪里？ | 同样材料、工具和预算下，能否少做无用步骤、避免错误决定或解决原先卡点 | 先写比较方案和失败判据，再记录实际结果，不能先下结论 |

优先论文原文、作者代码、数据字典和原始采集说明。博客可用于找线索，关键判断要追到一手出处。

本轮最多补三项关键一手来源。每项至少记录：标题、URL、版本/日期、许可或访问限制、原文位置、支持什么、不能支持什么、会改变我们的哪一个决定。够支持一个具体选择和一个反例就停止扩展；不要做一份无边界综述。

## 5. PR 1：资料结论、配方规则和两个配置

**建议标题：** docs: define the first research recipes and evidence gaps

拟新增文件：

~~~text
docs/recipe-research/README.md
docs/recipe-research/sources.csv
docs/recipe-research/gaps.md
examples/research-recipes/tabular-group-first.json
examples/research-recipes/tabular-source-first.json
~~~

每份文件具体写什么：

- README.md：选了哪个真实问题、现在卡在哪、采用什么方法、哪些条件不可缺、什么结果会改变下一步、什么情况算失败。
- sources.csv：使用的来源与精确定位；推荐列为 title,url,version,license,locator,supports,limits,decision_effect。
- gaps.md：把“已经知道”“仍然不知道”“补什么能改变决定”分开；至少保留一个反例。
- 两份 JSON：问题和适用范围相同，只交换“先看分组结果／先读来源”的优先顺序。

第一份配置的建议结构如下，PR 1 可以根据接口核查作小调整，但要同步解释：

~~~json
{
  "schema_version": "research-recipe-v1",
  "id": "tabular-group-first",
  "version": 1,
  "question": "出现零值后，下一步优先核对分组分布还是读取已登记来源？",
  "scope_match": {
    "domain": "data",
    "contract": "tabular-quality-v1"
  },
  "need": "next_check",
  "ordered_methods": [
    {
      "method_id": "data.grouped-quality-profile",
      "evaluation_ref": "grouped-quality-profile-v1"
    },
    {
      "method_id": "research.source-selection",
      "evaluation_ref": "source-extraction-only-not-scientific-approval"
    }
  ],
  "on_no_match": "wait"
}
~~~

第二份改 id 为 tabular-source-first，并交换 ordered_methods 的顺序，其余研究条件保持一致。

这些 domain/contract 匹配只检查工程范围，不能自动证明单位、样本独立性和方法科学适用。科学条件由说明、原始证据和已有宿主检查共同约束；未实现的自动检查要明确写出来。

**PR 1 可合并的条件：**读者能说清这个配方解决什么、为什么这样排、何时不能用；来源能定位；两个 JSON 能解析，字段含义无歧义。没找到的证据明确保留为空缺，不能补写“已验证”。

## 6. PR 2：最小原型和实验结果

**建议标题：** feat: select allowed research actions from explicit recipes

拟新增文件与职责：

~~~text
src/autoresearch/research_recipe.py       配方校验与纯选择函数
scripts/compile_research_recipe.py        只读输入并输出提案的 CLI
scripts/verify_research_recipe.py         一次隔离工程实验入口
tests/test_research_recipe.py            下文三组必要检查
docs/recipe-research/experiment.md        执行方案、命令、实际结果和局限
~~~

原始 context、proposal、日志和运行项目放 ignored 的 runs/recipe-pilot-<日期>/。PR 中放可公开的小型构造数据、复现命令和结果摘要，不提交 SQLite、私有原件或历史运行目录。

### 原型必须怎样工作

1. 输入只有一份配方和一份原样导出的 selection-context。
2. 核对配方结构、范围、need，以及宿主 context 的原有校验。
3. 有 blockers、范围不匹配或没有匹配候选时，输出 wait。
4. 按 ordered_methods 找 context.candidates 中 method_id 与 evaluation_ref 都匹配的候选。同方法多个候选沿用宿主顺序，不自己重排来源或改参数。
5. 输出现有 project-selection-proposal-v1。choice 只能包含候选 id 或 wait；参数仍由宿主决定。
6. 再调用现有 validate_proposal 检查输出。实际执行仍交给原 advance-selection。
7. 单独输出 decision.json，保存配方 id/version、原配方、context_sha256、选中/跳过的理由及 proposal。不要往现有 proposal 塞新字段。

provider 使用 operator_assistant，label 清楚写 deterministic recipe policy; no model。默认 evidence_citation_ids 为空；确实使用了当前 context 的证据才填写真实 citation_id。结果保持 scientific_validation:false。

该模块不执行工具、不联网、不读任意项目路径、不加载模型、不批准科学结论。不要新增工具参数入口、预算覆盖、自动安装或配方自修改。执行内核、注册目录和五页界面由主开发者维护，本 PR 不改。

## 7. 工程实验：同一份候选，换配方能否改变选择

**这是你在 PR 2 中要做的一次实验，本文尚未执行。**目的仅是验证配置、现有执行器和记录接通。

### 准备一个明确标注为构造数据的夹具

~~~csv
record_id,batch,value
r1,A,0
r2,A,2
r3,B,3
r4,B,4
r5,C,0
r6,C,6
r7,D,7
r8,D,8
~~~

按[现有 spec 格式](tabular-quality.md)生成 spec.json：group_columns 为 batch，key_columns 为 record_id，numeric_columns 为 value，target_column/target_unit 为 null。来源写明确的 synthetic URN，样本单位写“人工构造行，不代表独立实验”。origin_sha256 使用实际夹具原件值，不能填占位哈希。

这里手工可核对：8 行，4 组，每组 2 行；value 有 8 个有限数、2 个零值，没有缺失。零值分布在 A、C 两组，每组 1 个。这些是夹具预期值，不是实际实验结果。

### 按这个顺序执行

1. 新建隔离输入和项目，主方法 data.tabular-quality-audit，本地工具上限 2；不得复制旧生产项目来重置其额度。
2. 用现有 step 执行一次主质量检查，保留实际反馈。
3. 用 evidence-task 取得这个项目当下生成的任务模板，绑定一份简短 UTF-8 来源文件。内容注明“人工构造夹具不能证明样本独立性”，来源身份写实际构造来源。
4. 用 register-evidence 登记，**先不读取**。具体 bundle 按[来源接回说明](project-slice.md#在同一项目接回来源)填写；不要伪造 task_ref。
5. 导出并冻结 selection-context。检查其中同时出现分组检查与未读来源两个合法候选。
6. 对**同一份未改动的 context**分别编译两份配方。预期 group-first 选分组候选，source-first 选来源候选，两份都通过原提案校验。
7. 实际只提交 group-first 的提案一次，让原控制器执行分组检查。来源优先提案只验证选择，不再执行。
8. 使用相同 request-id、相同 proposal、相同 need 和原 expected-state-version 重放，确认不增加工具行动。最后 status 核对分组计数和额度。

若第 5 步没有两个候选，保存实际 conditions/candidates/blockers，说明阻塞原因。**不要编辑 context 加候选，也不要把失败记录删掉后宣称完成。**

### 必要的三组自动检查

| 检查 | 要发现什么错误 |
|---|---|
| 配方结构与范围 | 非法字段/类型、任意参数或代码入口被接受；范围、need 不符却执行 |
| 选择行为 | 同一双候选 context 换顺序不生效；阻塞/无候选时不等待；函数改写输入 |
| 原协议接入 | 输出不通过现有 validator；篡改 context、candidate、参数或引用后仍被接受 |

只跑这组新测试和上面一次集成实验。没有受影响理由不跑全量研究、训练或旧六臂比较。发现问题后修复并重跑受影响部分即可，不堆重复测试。

### 实验结果怎样填

| 项目 | 预期 | 你填写的实际值 |
|---|---|---|
| 冻结 context 有两个合资格候选 | 是 | 待实验填写 |
| 同一 context，两配方选择不同 | 分组／来源 | 待实验填写 |
| 两份 proposal 通过原 validator | 是 | 待实验填写 |
| 实际执行及重放 | 分组执行一次；重放不新增 | 待实验填写 |
| 主质量＋分组工具累计 | 2；来源读取 0 | 待实验填写 |
| 新模型调用／新拟合／付费调用 | 0／0／0 | 待实验填写 |
| 分组结果 | 4 组，2 组各含 1 个零值 | 待实验填写 |

这能证明“配置影响选择，且选择通过原控制器执行”。不能据此说配方比人工更好、零值是错误、分组是独立样本，或已完成真实科研。

## 8. 真实问题：核对 hiMSC 零值来自什么采集或导出规则

**默认选题：hiMSC B8S1 表格中的 0 是原始保存值，还是某种处理/导出结果？目前有什么依据解释，下一步需要取得什么材料？**

主开发者已只读核对：钢材 CSV 有 312 行，yield_strength_MPa 零计数为 0，范围为 1005.9 至 2510.3 MPa；组成解析的缺元素填 0 是另一种派生特征，不能代替这个目标列。钢材保留为“没有目标零值”的输入条件对照，不作为两种科研策略的效果对照组。

hiMSC CSV 是原工作簿 B8S1!A1:F973 保存值的宿主投影，共 972 行；Count、Mean_Red_Intensity、Mean_Green_Intensity 各有 59 个零值。已有分组工件按声明的 Topo/Chem 统计出 288 组，各列零值分布于 56 组、单组最多 2 个。完整重复额外记录为 3 条。以上都是已有数据/工件的计数，不能解释零值原因、证明独立样本，或确认 ALP 终点。

CSV、spec、转换说明、保存质量/分组工件和历史 context 由主开发者补交。先读这些材料，再找对应版本的数据字典、作者论文和采集/导出说明。找不到时准确记录缺口，不拿另一数据集或通用字典代替。

具体做法：

1. 写下真实文件、版本、字段、单位和分组声明。Topo/Chem 是当前声明分组，不能直接叫实验批次；原始单位、独立性和重复测量定义不清就写未知。
2. 先写人工固定流程：核对字段和来源→查看已有质量结果→必要时查看已有分组结果→决定是否仍需取证。保留失败和未知，不故意删步骤制造弱基线。
3. 记录两个配方在适用且有多个合法候选时各选什么，以及你在看结果前认为哪一步更有帮助、为什么。本次补交的历史 context 只有 0 或 1 个候选，报告“当前历史材料不能区分两配方”，不改 context、不新增真实项目执行来凑比较。双候选机制由第 7 节人工夹具验证。
4. 优先读现有保存结果，避免重跑。同样的资料给人工流程和配方；不得一边多拿资料或多用模型。
5. 寻找一条能改变决定的真实反馈，例如作者说明 Count=0 时强度值怎样写入，或原始记录解释重复和组别。记录原文定位、反馈者及实际判断；原单元格含 0 只能证明保存值，不能自动解释采集意义。
6. 写出反馈前后的下一决定。如果没有可靠来源或专业判断，就保留“零值含义未知，暂不改值/删行”，并写需要谁提供什么。

这轮不拟合模型、不擅自补值、不把所有 0 改成缺失，也不改原数据。

experiment.md 中至少保存一条完整记录：

~~~text
问题及原件：
当前条件与仍缺条件：
人工固定流程原本会做什么：
配方选择及理由：
实际取得的反馈、出处和时间：
反馈后的下一决定：
谁核对了结论，核对范围：
是否有帮助：有 / 无 / 目前无法判断；具体依据：
成本：新增工具、模型、拟合、资料检索、人工耗时分别记录：
~~~

不要编造耗时或把旧运行耗时当成这次测量。真实材料缺失不阻塞工程原型，但“真实效果验证”要保留未完成。要声称优于固定流程，后续还须先冻结比较方案，在相同资源下对未参与调参的真实任务比较；这轮小实验不能支持该结论。

## 9. 命令怎么用：现成入口和拟新增入口分开

在产品根执行。已有环境用现有 Python；没有环境时按[项目 README](../README.md)准备，新增依赖先讨论。

下面这些命令**现在存在**，先看帮助和协议，不会因为查看帮助启动研究：

~~~powershell
$py = '.venv/Scripts/python.exe'
& $py scripts/run_research_project.py --help
& $py scripts/run_research_project.py prepare-source --help
& $py scripts/run_research_project.py evidence-task --help
& $py scripts/run_research_project.py register-evidence --help
& $py scripts/run_research_project.py advance-selection --help
~~~

实验脚本应复用 prepare-source → create → step → evidence-task → register-evidence → selection-context → advance-selection → status。各参数以现有帮助为准，输入声明和 bundle 格式见前面的产品说明。

下面是 **PR 2 要实现的命令接口，目前不能直接运行**：

~~~powershell
$py = '.venv/Scripts/python.exe'
& $py scripts/verify_research_recipe.py --output runs/recipe-pilot-<日期>
& $py -m unittest discover -s tests -p test_research_recipe.py
# verify 保存 context.json 后，可用两个新目录单独复核编译；不重复执行工具。
& $py scripts/compile_research_recipe.py --recipe examples/research-recipes/tabular-group-first.json --context runs/recipe-pilot-<日期>/context.json --output runs/recipe-pilot-<日期>/manual-group-first
& $py scripts/compile_research_recipe.py --recipe examples/research-recipes/tabular-source-first.json --context runs/recipe-pilot-<日期>/context.json --output runs/recipe-pilot-<日期>/manual-source-first
~~~

compile 只读取输入并输出 decision.json、proposal.json，不执行工具；已有输出目录应报错，避免覆盖旧结果。verify 在自己的隔离目录构造夹具并按第 7 节执行，保存冻结的 context.json、两份配方的编译结果、实际命令/状态与 before/after 记录。它可以内部调用已有 Python 接口，不必新增框架。

新测试导入 src 下包的方式沿用仓库现有测试环境；先按项目 README 将本项目安装到虚拟环境，不额外新增依赖。每个可执行入口出错应返回非零退出码，并保留错误说明。

## 10. PR 怎么交、怎么验收

### 先取得共同基线

产品 Git 根是 ICT/track2/auto-research/。你需要的是包含这份任务书和现有受限选择接口的共同提交。

主开发者提供实际可取得的提交号；本机新提交不代表远端已经有。先核对远端/交接包是否包含它，再从该提交开分支。不要直接在别人的脏工作树里开发。

~~~powershell
git status --short
git fetch origin
$baseCommit = '<主开发者提供且你已取得的提交号>'
git show --no-patch --oneline $baseCommit
git switch --create feat/research-recipe-spec $baseCommit
~~~

以上示例中的尖括号必须替换。工作树已有改动时先保留自己的工作，不运行 reset/clean，也不覆盖别人文件。

### 两次 PR 的提交方式

PR 1 只交第 5 节的资料、规则和配置。先完成下方“每次提交前”的门禁，再运行以下提交命令。明确列文件暂存，避免把原件和运行目录混进去：

~~~powershell
git add docs/recipe-research/README.md docs/recipe-research/sources.csv docs/recipe-research/gaps.md examples/research-recipes/tabular-group-first.json examples/research-recipes/tabular-source-first.json
git diff --cached --stat
git diff --cached
git commit -m "docs: define first research recipes and evidence gaps"
git push --set-upstream origin feat/research-recipe-spec
~~~

PR 2 从已合并的 PR 1 基线另开 feat/research-recipe-prototype；只暂存第 6 节文件及必要的小夹具。PR 1 未合并时可以本地继续写原型，但 PR 2 要说明依赖，避免混成一个无法判断的大改动。

push 和创建 PR 由拥有该远端写入权限的队员操作；以上是提交方法，本任务书的编写没有代替你推送。

每次提交前，按仓库要求在 frontend 目录运行三项门禁：

~~~powershell
Set-Location frontend
pnpm --config.verify-deps-before-run=false --config.offline=true --config.update-notifier=false run format
pnpm --config.verify-deps-before-run=false --config.offline=true --config.update-notifier=false run lint
pnpm --config.verify-deps-before-run=false --config.offline=true --config.update-notifier=false run typecheck
Set-Location ..
~~~

缺现有依赖就记录环境阻塞，不让检查自动安装新包。format 若改到本任务外的文件，要查明原因，不能一并塞入提交。

在代码托管平台比较你的分支和共同主分支创建 PR。正文直接用这个模板，把“待填写”换成实际内容：

~~~text
解决的问题：
本 PR 让什么输入产生什么可观察的变化：

修改文件及各自作用：
依据的来源、版本与精确位置：
方法何时不适用：

验证命令与实际退出码：
工程实验实际结果和运行证据位置：
真实任务反馈与下一决定：
新增工具/来源/模型/拟合/现金用量：

Limitations：
尚未证明什么、仍缺哪份资料或哪位判断者：
~~~

主开发者收到后，先看来源能否定位、配置是否只选合法候选、实验是否可复现、真实反馈是否支持所写结论。只复核受影响路径，不要求额外开一轮全量实验或增加多个审阅角色。

**工程原型验收：**两份配置可读取；同一双候选下能产生预期不同选择；原控制器执行其中一个，重放不重复；非法/不匹配输入不会获得执行；必要测试、实验记录和门禁可核对。

**研究记录验收：**一个真实问题、一条真实反馈或明确缺口、一个不适用例子，以及有依据的下一决定。结果是“没有帮助”或“目前无法判断”也可以，不能改写成正面效果。

## 11. Limitations：资源和目前不能承诺的结果

- 此任务书分配的是资料、原型和隔离工程验证。既有钢材/hiMSC/P02 项目和历史账本保持只读；需要改变真实项目时另列具体动作，不用新目录重置历史预算。
- 原钢材项目获准的一次纯本地模型推理已经用完；不能把这次配方任务当成额外模型授权。AgentArts 接入仍暂缓，历史 unknown 和原 5 元新增现金上限不重置。
- 第一轮不新增依赖、不下载权重、不调用付费 API、不重训模型。不具备专业判断或真实标签时，不给出自动科学成功的结论。
- 参考库、部分本地计划和真实运行证据不在产品克隆中。交接缺哪些就列哪些；PR 保留可公开的来源定位与摘要，受限材料单独交接。
- 人工构造实验只证明工程行为；一次真实案例只提供案例证据，不能证明跨领域泛化、自动搜索收益或持续自我改进。
