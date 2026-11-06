# 单轮RSI：读取保存结果、采用或回退、后轮使用

已保存的反馈、配方候选与验证结果形成可核对的采用／回退决定。外环记录确定本轮有效版本，研究者再通过工作台明确保存到项目，供后续默认控制器读取。范围对应任务队列第2／3项及其必要的后轮消费。

## 已实现的入口

- `src/autoresearch/recipe_improvement.py`：`run_improvement_round`接收原配方、完整`research-plan-context-v1`、原目标、`propose_recipe_change`格式的返回值及已有`recipe-change-validation-v1`结果。输出决定、逐项检查、可读理由、有效配方和下一项问题。`read_improvement_round`重新核对保存记录。
- `scripts/run_recipe_improvement.py`：`fixture`处理明确构造输入；`saved-host`通过已有`read_recipe_validation`核对原Host、验证sidecar及控制器账本，仅读取，不调用`propose/validate/advance`或恢复执行。实际模型和工具接线仍由主开发负责。
- 项目与工作台通过 `preview_recipe_round/apply_recipe_round` 核对原 Host 保存记录并追加 `recipe_revisions`。研究页展示当前有效版本，上传完整 `input.json` 后先核对，再填写理由明确采用或记录回退。操作步骤与 HTTP 字段见[工作台说明](../local-workbench.md#核对外环并保存有效版本)。

完整函数签名以源码为准。普通Python调用直接将既有适配返回值作为函数参数，无动态插件、进程或表达式。`evidence_kind`是证据来源类别，不证明真实用户、真实模型调用或科学效果；直接函数调用者必须提供可信的适配结果。脱离原账本的任意JSON只能使用`fixture`入口，不能作为Host验证原件。

## 如何决定

输入要明确一项`issue.summary`及实际完成／失败行动的`feedback_action_ids`、一个目标，以及一个精确`method_id/evaluation_ref`验收对。目标和判据与本轮输入一起固定，不能重放时更换。这里对已有结果作**回顾性工程验收**，不是前瞻预注册试验，也不证明因果收益。

首先复用原协议验证：原配方范围和need、完整封印context、候选同id／范围且版本恰加1、反馈引用、冻结conditions的方法／评价配对。重新编译原版和候选，检查保存结果与两份决定、原Host请求ID、项目ID、context SHA及控制器原配方决定完全对应。

采用仅在以下条件全部满足时发生：原版未选择目标对，候选选择目标对，原控制器结果为`completed`，并记录完成行动身份与工件引用。`selection_changed=true`或模型自述“更好”都不够。该判据只覆盖“补上遗漏的下一项可用方法”，其他改善类型留给后续实际反馈，不自行扩张为通用评分器。

| 保存事实 | 外环决定 | 有效配方 |
|---|---|---|
| 全部工程验收条件满足 | `keep` | 候选的原生配方 |
| 提案失败／拒绝，或终态验证未满足判据 | `revert`及失败项 | 原版 |
| 提案prepared、验证缺失或执行unknown等 | `pending`，先核对原请求 | 原版，不宣称已回退或失败 |
| 身份、原件或决定不一致 | 报错，不发布新决定 | 不变 |

“回退”把原版保留为有效配方，既有验证工具行动、反馈及累计用量继续保存在原账本。外环文件中的决定经工作台核对并明确保存后，才成为项目有效配方。配方决定、研究计划采用和科学结论按各自记录确认。

## 保存和下一轮

每轮在`<output>/<round-id>/`保存三份原子发布的JSON：

- `input.json`：原配方、完整反馈、问题、目标、验收对、完整提案与验证、前轮结果及其SHA。
- `result.json`：`recipe-improvement-result-v1`，含`decision/reason/explanation/checks`、原版／候选版本、`effective_recipe`、前轮ID和决定、下一项问题；始终`scientific_validation:false`。
- `effective-recipe.json`：与结果逐项相等的当前有效原生配方。

沿用原有目录writer lock和`write_bytes_once`，不新增数据库。相同轮ID／输入重放不覆盖；中断在原子文件发布之间可用完全相同输入补齐。不同输入使用同轮ID会拒绝。读取前轮重新计算决定、核对有效配方，后轮必须传该版本，并保持同项目和同证据类别；被拒候选不能污染后轮。

传`previous_round_id`或CLI的`--previous-round-id`显式关联前轮。前轮决定及下一项问题保存在新轮输入，可供主开发／研究者确定下一目标；首版不会自动生成新目标或自动申请资源。未知／待验证快照保持不可变，先由原Host完成核对，随后用新**外环记录ID**读取同一**Host请求ID**；这不是新模型／工具请求。完整阶段内接续和资源受限连续调度留在队列第4项。

### 保存到项目并供控制器使用

`POST /api/local-workbench/recipe-preview` 接收 `project_id/input`，沿原 Host 账本核对 context、prompt、回答、提案、验证原件和控制器回执，再返回工程判据及本轮有效配方。它使用只读路径，返回的项目版本用于后续提交。

研究者填写理由，通过 `POST /api/local-workbench/recipe-adopt` 提交 `request_id/project_id/expected_state_version/input/reason`。保存时再次核对原件、当前版本和前轮关系，只有 completed 的 keep/revert 决定可追加项目 `recipe_revisions`。记录包含轮次、原模型请求、有效配方全文、判据说明、保存理由和输入SHA，项目 state 版本加1。pending 先核对原请求，身份或原件不一致则拒绝。

`GET /api/local-workbench/recipes` 的 `effective_recipe` 返回最后一条项目修订，列表首先展示其配置，再按 id/version 去重补入正式配方。后续默认 `ProjectController.next/advance` 使用该有效版本和当前真实候选编译下一决定。旧请求重放使用原冻结版本，后轮外环输入继续绑定已保存的有效配方及前轮记录。网页保存回执不明时，先按原请求ID读取 `recipe_revisions`。

## 实际运行

在仓库根目录，使用已有环境，无需安装或升级依赖：

```powershell
.venv/Scripts/python.exe -B examples/recipe-improvement/demo_saved_rounds.py --output runs/recipe-rsi-demo
```

演示通过实际CLI先后运行两轮。**所有反馈、模型声明、验证回执和工件引用均为构造数据**，没有真实模型或工具调用。

1. 原版v1只包含已不在候选中的主检查，冻结结果为wait；候选v2补上分组方法，构造验证为completed，输出`keep`和有效v2。
2. 从第一轮保存结果读取v2，提出来源候选v3；构造验证为failed，输出`revert`，仍用v2，记录`previous_round_id=round-1/previous_decision=keep`。

同一命令可重放，输入与决定不变。手工调用单轮CLI可使用演示生成的`fixture-input-1.json`；不要把这些JSON标成真实Host材料。

原Host项目齐备后，先将[spec模板](../../examples/recipe-improvement/saved-host.spec.example.json)中的行动ID、问题、验收对和下一项替换为原记录对应值，再运行：

```powershell
.venv/Scripts/python.exe -B scripts/run_recipe_improvement.py saved-host --workspace <原Host项目目录> --request-id a64-recipe-change --spec <本轮spec.json> --output runs/recipe-rsi-real --round-id saved-a64
# 后轮有自己的原Host请求、原冻结反馈／配方及spec；原配方须等于前轮有效版本
.venv/Scripts/python.exe -B scripts/run_recipe_improvement.py saved-host --workspace <同一项目目录> --request-id <后轮原Host请求ID> --spec <后轮spec.json> --output runs/recipe-rsi-real --round-id next-round --previous-round-id saved-a64
```

第二条不是自动发起新轮的命令，只消费已经存在的后轮请求。`--output`选独立外环目录，不选原项目目录。成功读取包括pending状态均退出0，非法／不一致输入退出2。没有原Host项目时不要伪造workspace或重新执行A64来凑结果。

## 原单轮模块的验证记录

针对性检查覆盖采用、失败／等待／拒绝回退、未决不采用、仅改变选择不采用、目标已满足不采用、原版和候选不可变、原件及身份不一致拒绝、前轮篡改拒绝、旧版本不能接续、原子发布中断补齐、实际CLI两轮及重放。另在新建构造项目通过原适配器保存一份验证，再运行`saved-host`CLI，核对读取前后项目、Host记录及所有已有文件字节不变，篡改原控制器回执后入口拒绝。该检查的本地工具仅作用于隔离测试数据，导入的模型回答仍是构造的，不是实际模型调用。

本轮用`.venv/Scripts/python.exe -B -m unittest discover -s tests -p 'test_*recipe*.py' -v`通过39项（新增12项外环检查），退出0。首次误用系统Anaconda Python运行整组时，4个旧模块因未安装本仓库而出现`ModuleNotFoundError: autoresearch`；保留该启动失败，改用已有项目`.venv`后整组通过，无依赖安装或升级。实际双轮CLI输出位于本机ignored `runs/recipe-rsi-20261106-verified/`。前端按现有离线前缀执行format/lint/typecheck均退出0，format34文件、修改0。

该次单轮模块PR基于 `454d274`，当时未修改前端或公共控制器／项目存储。生产研究新增模型／工具／拟合／付费调用为0；隔离新建测试项目中的本地方法执行属于测试证据。本次项目修订与页面采用接线在上节说明，实际采用结果另行记录。

## 剩余问题与下一项

### 主开发的A64接线复核

2026-11-06，主开发沿本PR的正常`saved-host`CLI读取原`a64-recipe-change`请求，验收目标为原候选实际选择的`research.source-selection`与对应评价引用。原配方未选择该目标，候选选择目标，原控制器completed并保存工件，四项判据均满足，外环输出keep及有效配方v2。

同参数和原ID重放返回相同结果，三份外环文件逐字节一致。读取前后原项目20份文件逐字节一致，新增产品模型、工具、来源、拟合调用均为0。这次接线消费的是原实际提案与允许来源读取记录，输入仍为四行构造工程样例，判据属于回顾性工程验收。

原A64现已通过页面明确采用该保存结果。兼容代码登记使 state 14→15，随后以显式理由保存 `saved-a64`／Host `a64-recipe-change` 的 keep 决定，state 15→16。项目有效配方为 `a62-quality-follow-up` v2、revision 1，普通刷新后仍可读取。默认 `ProjectController.next` 与 `selection_context.baseline_decision` 均带 `policy_ref.kind=effective_recipe`、version 2、revision 1，当前选择 `data.grouped-quality-profile`。

该下一步尚未执行，原A64仍无基于有效v2生成的后轮 Host 请求。后轮消费的执行证据继续限定于明确标记的构造双轮演示，本次新增研究、模型及工具调用为0，预算与 Host 全部保留原值。A64原20份文件中，`project.sqlite`按上述状态写入，其余原件字节一致，仅新增兼容登记与配方修订工件。A63原24份文件、state和Host全等；manager新增1条completed采用请求，旧19条记录完整保留，其中含2条旧preparing记录。证据保存在本机 ignored `runs/a76-effective-recipe-20261106/actual-adoption-result.json`。[A64材料和读取边界](a64-rsi-handoff.md)

项目保存、原ID恢复、回退、过期原版、并发有效版本变更及HTTP接线共8项必要回归通过，前端四门禁通过。8张最终桌面／手机全页及分段截图已实际查看，五页导航和画布保留，当前版本、理由、刷新草稿及已保存轮次的重复采用停用均已核对。

### 后续工作

1. 原A64保存结果已通过页面采用，默认控制器已读取有效v2。后轮执行按实际问题和原累计资源安排。离线材料包支持读取原件，`saved-host`入口通过原数据库和控制器账本核对。
2. **P1，接续与连续推进**：单轮只读消费已实现；pending原ID核对、同轮阶段接续、资源边界与连续调度按实际需要实现，不用新外环记录绕过原Host未决状态。
3. **P2，扩充验收类型与结构化条件**：现判据只覆盖遗漏目标方法，文本条件不自动求值。根据真实问题增加小型、可比较的判据，不用选择变化代替收益。

后续从合并后的 main 选择依赖已满足的一项，围绕实际后轮问题推进中断接续或新的保存结果消费。PR合并由主开发执行。
