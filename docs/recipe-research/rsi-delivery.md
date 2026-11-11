# 单轮RSI：读取保存结果、采用或回退、后轮使用

已保存的反馈、配方候选与验证结果形成可核对的采用／回退决定。外环记录确定本轮有效版本，研究者再通过工作台明确保存到项目，供后续默认控制器读取。范围对应任务队列第2／3项及其必要的后轮消费。

## 已实现的入口

- `src/autoresearch/recipe_improvement.py`：`run_improvement_round`接收原配方、完整冻结context（新`research-plan-context-v2`，历史v1原件保持）、原目标、`propose_recipe_change`格式的返回值及已有`recipe-change-validation-v1`结果。输出决定、逐项检查、可读理由、有效配方和下一项问题。显式 `resume=True` 可在同一轮追加新的保存回执。`read_improvement_round`重新核对并返回最新完整阶段，`read_improvement_snapshot`另提供对应原生输入和 `input_path`。
- `scripts/run_recipe_improvement.py`：`fixture`处理明确构造输入；`saved-host`通过已有`read_recipe_validation`核对原Host、验证sidecar及控制器账本，`--resume`继续同一外环记录。CLI始终输出当前最新完整阶段的 `input_path`。实际模型和工具接线仍由主开发负责。
- 离线材料使用`saved-export --evidence-root --spec`及`load_saved_export`，核对团队导出原件后保存独立外环结果，不构造数据库。`next-input --output --round-id`读取最新完整阶段的有效配方、前轮结果和下一项问题，状态为`awaiting_next_feedback`，不产生新提案或行动。
- 项目与工作台通过 `preview_recipe_round/apply_recipe_round` 核对原 Host 保存记录并追加 `recipe_revisions`。研究页展示当前有效版本，上传完整 `input.json` 后先核对，再填写理由明确采用或记录回退。操作步骤与 HTTP 字段见[工作台说明](../local-workbench.md#核对外环并保存有效版本)。

完整函数签名以源码为准。普通Python调用直接将既有适配返回值作为函数参数，无动态插件、进程或表达式。`evidence_kind`是证据来源类别，不证明真实用户、真实模型调用或科学效果；直接函数调用者必须提供可信的适配结果。任意脱离原件的JSON只能使用`fixture`；团队完整导出使用独立的`saved_export_validation`类别，只核对包内一致性，不冒充原数据库核对。既有项目采用入口仍只允许`saved_host_validation`，不能上传离线结果绕过在线Host核验。

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

每轮首次在 `<output>/<round-id>/` 逐文件不可变发布三份JSON，三件套完整后才作为可读取的当前阶段。

- `input.json`：原配方、完整反馈、问题、目标、验收对、完整提案与验证、前轮结果及其SHA。
- `result.json`：`recipe-improvement-result-v1`，含`decision/reason/explanation/checks`、原版／候选版本、`effective_recipe`、前轮ID和决定、下一项问题；始终`scientific_validation:false`。
- `effective-recipe.json`：与结果逐项相等的当前有效原生配方。

沿用原有目录writer lock和 `write_bytes_once`。相同轮ID和相同最新输入重放复用该阶段。显式接续时，新的 `proposal_result/validation_result` 保存到同轮 `stages/0001/`、`stages/0002/` 等目录，各有同样三件套，原根目录和已保存阶段保留原字节。round／Host请求ID、原配方、冻结trace、目标、问题、判据、前轮和下一问题均固定，已保存候选及其来源引用也须一致，completed终态保持冻结。

只读入口遇到合法半写阶段时返回前一个完整阶段，已存在的不一致记录会报错。`resume=True`先按半写阶段已保存的input补齐，再处理新的回执。原pending记录继续保留其当时状态，新的阶段反映原Host提案与验证的后续结果。Host或控制器原请求的执行与回执核对由原入口处理，外环接续读取这些保存事实。控制器完成但验证回执缺失时仍保存pending。

传 `previous_round_id` 或CLI的 `--previous-round-id` 显式关联下一轮的前轮。读取前轮时重新核对最新完整结果，前轮须已completed，后轮原配方须等于其有效版本，并保持同项目和证据类别。前轮决定及下一项问题保存在新轮输入，供研究者确定下一目标。

两项新增定点检查已通过，覆盖 prepared→proposed→验证终态的同轮接续、半写阶段补齐、损坏记录拒绝、原pending字节保留、终态冻结，以及CLI读取前后原Host、控制器、预算和项目文件一致。另运行受影响的原子发布恢复与旧两轮CLI演示，两项均通过。日志保存在本机 ignored `runs/a80-feedback-stage-resumption-20261107/new-tests.log` 和 `existing-tests.log`。Host阶段演进使用隔离工程项目与构造回答，真实研究多轮推进仍需对应任务记录。

### 保存到项目并供控制器使用

`POST /api/local-workbench/recipe-preview` 接收 `project_id/input`，沿原 Host 账本核对 context、prompt、回答、提案、验证原件和控制器回执，再返回工程判据及本轮有效配方。它使用只读路径，返回的项目版本用于后续提交。

研究者填写理由，通过 `POST /api/local-workbench/recipe-adopt` 提交 `request_id/project_id/expected_state_version/input/reason`。保存时再次核对原件、当前版本和前轮关系，只有 completed 的 keep/revert 决定可追加项目 `recipe_revisions`。记录包含轮次、原模型请求、有效配方全文、判据说明、保存理由和输入SHA，项目 state 版本加1。pending 先核对原请求，身份或原件不一致则拒绝。

`GET /api/local-workbench/recipes` 的 `effective_recipe` 返回最后一条项目修订，列表首先展示其配置，再按 id/version 去重补入正式配方。后续默认 `ProjectController.next/advance` 使用该有效版本和当前真实候选编译下一决定。旧请求重放使用原冻结版本，后轮外环输入继续绑定已保存的有效配方及前轮记录。网页保存回执不明时，先按原请求ID读取 `recipe_revisions`。

### 有界保存证据队列（2026-11-08）

本轮要改善：保存轮次已经可以逐个接续，但多个原请求仍须手工串接。`run_improvement_sequence(manifest, *, directory, base_directory=None, max_rounds=1)`与CLI `sequence --manifest --output --max-rounds`按固定顺序消费已有证据，遇到限额、未决或缺输入时保存接续位置。它不调用`propose/validate`，不创建Host请求、不采用到项目，也不代替工作台的内层“继续研究”。

manifest严格为`recipe-improvement-sequence-v1`、`mode`和`rounds`三字段，1至32项，轮次ID唯一。整个队列只能使用同一种来源；各项精确字段如下。

| mode | 每项字段 | 来源类别 |
|---|---|---|
| `fixture` | `round_id/input` | 明确构造输入 |
| `saved-host` | `round_id/workspace/request_id/spec` | 原数据库、Host和控制器账本 |
| `saved-export` | `round_id/evidence_root/spec` | 团队完整离线导出，仅包内一致性 |

相对路径以manifest所在目录为基准，不以启动命令的目录为基准；Python调用可传`base_directory`。路径先按原安全守卫检查，再规范化保存。输出目录与原Host项目／离线包必须互不包含，不能把队列回执写进原件。`saved-host`中的原请求ID也须唯一。引用可指向尚未取得的未来输入，缺失时暂停，不预造候选或验证。

输出在独立目录保存`sequence.json`（固定顺序及规范化引用）、`rounds/<round-id>/`（原单轮三件套和stage）与`checkpoints/<内容SHA>.json`（不可变停点）。清单一旦保存，修改顺序、ID、模式或引用会报冲突。每轮仍检查原版等于前轮有效版本、同项目、同证据类别及前轮结果SHA。完成轮次从自身不可变快照复用，不重读其可变外部原件；这些快照不独立认证外部模型或数据库。未决轮次才读取后续保存证据，并沿同ID执行已有阶段接续。损坏记录或身份冲突报错，不跳过继续。

`--max-rounds`是本次调用最多评估的保存轮数（1至32，默认1），**不是模型、研究工具、费用或项目额度**。重启时已完成轮次不占本次评估名额；pending和终态回退也不重发原请求。停止结果明确区分：

- `paused_round_limit / ROUND_LIMIT`：达到本次保存结果评估上限，`next_entry`保留下一项。
- `pending_original_request / ROUND_PENDING`：先核对该原请求，后续轮次不处理。
- `awaiting_input / SAVED_INPUT_UNAVAILABLE`：文件或原Host请求尚未取得，保留已有有效版本和具体缺口；不把缺失记为验证失败。
- `queue_consumed / QUEUE_CONSUMED`：清单中的保存结果已消费完，**不表示研究目标达成或实际多轮研究完成**。

结果还提供前轮决定、当前有效版本、下一问题、各轮最新`input_path`、停点路径及`evaluated_this_call`。该计数只表示本次保存结果评估次数，不写入停点内容；相同状态重放复用同一个内容SHA停点。调用者根据保存的`next_entry`补原件或明确再次调用，不自动轮询、重试或扩额度。

可从[构造清单示例](../../examples/recipe-improvement/sequence.fixture.example.json)开始。以下实际入口在全新目录演示：首轮keep v2后达到单轮上限；再次调用复用首轮，第二轮候选v3失败并revert，仍有效v2；最后`next-input`读取v2并等待新反馈。

```powershell
.venv/Scripts/python.exe -B examples/recipe-improvement/demo_saved_sequence.py --output runs/recipe-rsi-sequence-demo
# 手工重启同一队列；已完成轮次不再次评估
.venv/Scripts/python.exe -B scripts/run_recipe_improvement.py sequence --manifest runs/recipe-rsi-sequence-demo/sequence.fixture.json --output runs/recipe-rsi-sequence-demo/queue --max-rounds 1
.venv/Scripts/python.exe -B scripts/run_recipe_improvement.py next-input --output runs/recipe-rsi-sequence-demo/queue/rounds --round-id round-2
```

示例的反馈、模型声明、验证结果与工件引用全部构造，未调用真实模型或研究工具。2026-11-08最终实际演示保存于本机ignored `runs/recipe-rsi-sequence-20261108-final/`，两次队列调用及`next-input`均退出0。新增7项专项覆盖轮数限额、keep/revert、pending阶段接续、输入暂缺、固定清单与前轮身份、半写恢复、完成重放不新增文件、原Host项目全部文件不变及输出路径隔离；原离线导出专项也增加队列消费与原件不变核对。

最终固定源码后运行`.venv/Scripts/python.exe -B -m unittest discover -s tests -p 'test_*recipe*.py' -v`，55项全部通过；现有前端format/lint/typecheck均退出0，34文件、修改0，无安装或升级。首次整组回归时源码仍在变动，一项已有同轮接续检查报`STALE_SELECTION_CONTEXT`；原代码身份包含本次模块。保留该失败，停止源码修改后，该项独立通过、最终55项整组通过，未改保护检查。测试中的本地工具仅作用于隔离构造项目，不能算作真实研究反馈或模型执行。

主动提出下一项配方、取得新验证、按科研资源停止和真实研究中的多轮收益仍待接线。当前A79的研究计划v2及其Host用量，不等于A64配方v2或新的配方RSI请求。P1需提供实际任务的新反馈与对应原Host/验证记录，以及明确允许的方法、来源与资源范围；P2再围绕这项反馈扩充现有“补遗漏方法”以外的判据。

`recipe_improvement.py`已属于原`ResearchProject.code_identity()`的哈希范围；本次增加函数也会改变当前代码身份。原项目若要在新代码下继续执行，仍需主开发走既有显式兼容登记和未决请求核对，不能静默升级。离线读取或构造队列通过，不表示历史项目已适配新执行身份。

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
# 原请求的提案或验证后来取得新回执时，沿同round-id明确接续
.venv/Scripts/python.exe -B scripts/run_recipe_improvement.py saved-host --workspace <原Host项目目录> --request-id a64-recipe-change --spec <同一本轮spec.json> --output runs/recipe-rsi-real --round-id saved-a64 --resume
# 后轮有自己的原Host请求、原冻结反馈／配方及spec；原配方须等于前轮有效版本
.venv/Scripts/python.exe -B scripts/run_recipe_improvement.py saved-host --workspace <同一项目目录> --request-id <后轮原Host请求ID> --spec <后轮spec.json> --output runs/recipe-rsi-real --round-id next-round --previous-round-id saved-a64
```

三条命令分别保存首个阶段、继续同轮、读取已有后轮请求。`--output`选独立外环目录。接续后按CLI返回的 `input_path` 选择文件交给工作台核对及采用，例如 `saved-a64/stages/0002/input.json`；根目录 `input.json`继续保存首次观察，可能仍为pending。成功读取包括pending状态均退出0，非法／不一致输入退出2。没有原Host项目时，使用明确构造的fixture演示。

## 原单轮模块的验证记录

2026-11-07，同轮接续新增两项必要验证：prepared→proposed→验证终态、半写恢复与不可变原件；以及正常`saved-host --resume`对原Host、控制器与预算无新增写入。另两项受影响的原发布中断／双轮CLI回归通过。原A64已完成Host账本也由新版CLI读取，终态接续重放一致，未执行其研究。阶段演进验证来自隔离工程项目和构造回答；真实研究中的阶段演进及多轮配方收益仍待实际记录。原件位于本机ignored `runs/a80-feedback-stage-resumption-20261107/`。

针对性检查覆盖采用、失败／等待／拒绝回退、未决不采用、仅改变选择不采用、目标已满足不采用、原版和候选不可变、原件及身份不一致拒绝、前轮篡改拒绝、旧版本不能接续、原子发布中断补齐、实际CLI两轮及重放。另在新建构造项目通过原适配器保存一份验证，再运行`saved-host`CLI，核对读取前后项目、Host记录及所有已有文件字节不变，篡改原控制器回执后入口拒绝。该检查的本地工具仅作用于隔离测试数据，导入的模型回答仍是构造的，不是实际模型调用。

本轮用`.venv/Scripts/python.exe -B -m unittest discover -s tests -p 'test_*recipe*.py' -v`通过39项（新增12项外环检查），退出0。首次误用系统Anaconda Python运行整组时，4个旧模块因未安装本仓库而出现`ModuleNotFoundError: autoresearch`；保留该启动失败，改用已有项目`.venv`后整组通过，无依赖安装或升级。实际双轮CLI输出位于本机ignored `runs/recipe-rsi-20261106-verified/`。前端按现有离线前缀执行format/lint/typecheck均退出0，format34文件、修改0。

该次单轮模块PR基于 `454d274`，当时未修改前端或公共控制器／项目存储。生产研究新增模型／工具／拟合／付费调用为0；隔离新建测试项目中的本地方法执行属于测试证据。本次项目修订与页面采用接线在上节说明，实际采用结果另行记录。

## 剩余问题与下一项

### 主开发的A64接线复核

2026-11-06，主开发沿本PR的正常`saved-host`CLI读取原`a64-recipe-change`请求，验收目标为原候选实际选择的`research.source-selection`与对应评价引用。原配方未选择该目标，候选选择目标，原控制器completed并保存工件，四项判据均满足，外环输出keep及有效配方v2。

同参数和原ID重放返回相同结果，三份外环文件逐字节一致。读取前后原项目20份文件逐字节一致，新增产品模型、工具、来源、拟合调用均为0。这次接线消费的是原实际提案与允许来源读取记录，输入仍为四行构造工程样例，判据属于回顾性工程验收。

原A64现已通过页面明确采用该保存结果。兼容代码登记使 state 14→15，随后以显式理由保存 `saved-a64`／Host `a64-recipe-change` 的 keep 决定，state 15→16。项目有效配方为 `a62-quality-follow-up` v2、revision 1，普通刷新后仍可读取。默认 `ProjectController.next` 与 `selection_context.baseline_decision` 均带 `policy_ref.kind=effective_recipe`、version 2、revision 1，当前选择 `data.grouped-quality-profile`。

A76采用验证结束时，该下一步尚未执行，原A64仍无基于有效v2生成的后轮 Host 请求。当时后轮消费的执行证据来自明确标记的构造双轮演示，该次采用新增研究、模型及工具调用为0，预算与 Host 全部保留原值。A64原20份文件中，`project.sqlite`按上述状态写入，其余原件字节一致，仅新增兼容登记与配方修订工件。A63原24份文件、state和Host全等；manager新增1条completed采用请求，旧19条记录完整保留，其中含2条旧preparing记录。证据保存在本机 ignored `runs/a76-effective-recipe-20261106/actual-adoption-result.json`。[A64材料和读取边界](a64-rsi-handoff.md)

项目保存、原ID恢复、回退、过期原版、并发有效版本变更及HTTP接线共8项必要回归通过，前端四门禁通过。8张最终桌面／手机全页及分段截图已实际查看，五页导航和画布保留，当前版本、理由、刷新草稿及已保存轮次的重复采用停用均已核对。

### A64有效v2的实际后续行动

2026-11-07，通过原 CLI `scripts/run_research_project.py advance` 提交 `a77-effective-v2-grouped-20261107`，绑定原 state 16。默认控制器使用 `effective_recipe_revision=1`、冻结 `recipe_version=2`，完成 `data.grouped-quality-profile`，state 16→20。父请求关联 `controller-child-84c45c43749cf26a7af7dbd3ac1e7f3c` 与 `action-30c32ef36b47dc91a7cfb13bbb3f9660`。相同原ID和原版本重放后，完整项目状态一致。

保存反馈为4行、2个完整组，A与B各2行。`measurement` 唯一缺失为 B组逻辑记录3、物理行4的 empty，已按原CSV坐标回看确认，零值数为0。当前 `next` 为 waiting、`executable=false`，原因为 `NO_MATCHING_HOST_CANDIDATE`。继续前需补充来源、采集与分组定义及缺失解释，再依据新条件决定下一步。本地方法已用2/2、来源1/8、Host仍1/1，本轮新增模型、来源及拟合调用为0。

页面已导出 state 20 的当前报告，PDF共6页，已逐页查看。四种报告下载均HTTP200且与manager导出逐字节一致，报告保留v2实际选择、分组反馈及等待原因。A64本轮仅更新 `project.sqlite` 并新增1份行动工件，A63全部文件、state及Host一致。执行与原ID回读证据位于本机 ignored `runs/a77-effective-recipe-continuation-20261107/execution-validation.json`，导出及下载核对为同目录 `export-receipt.json` 与 `report-validation.json`。此次已采用配方驱动了实际工具行动，输入仍为四行工程样例，科学收益和真实用户价值仍待验证。PDF沿用现有分页模板，第3页留白较大。

### 队友收到离线包后的补充（2026-11-07）

本轮要改善：负责人转交的是不含`project.sqlite`的证据包，原`saved-host`入口不能直接读取。新增离线导出读取与后轮输入预备，沿最新main `cd3768f`保留团队已合并的在线采用、v2后续行动和同轮阶段接续，不重复执行这些路径。

收到`A64-RSI接续材料-20261106(1).zip`，SHA-256为`28e11a81514b0c081da2ae47e243027e21ffab6bb089412a3b50b1789a3f2fae`，共18文件、101433未压缩字节。安全解包到本机ignored `runs/a64-rsi-received-20261106/a64-rsi-handoff-20261106/`，仅读包内文档作为交接资料，没有执行其中命令。运行后18份文件的SHA仍逐一与ZIP原条目相等。运行包不提交Git。

`load_saved_export`核对原Host/context/prompt、原回答SHA及重建提案、四个派生视图、冻结验证输入和显式方法／收据权限、两份行动工件及反馈观察、来源收据／原资产。历史质量工件与后续来源验证的代码身份不同，保持其各自原值；历史观察按原提交规则补行动／观察ID后核对，不擅自升级历史身份。包内一致性不等于独立认证原执行或模型身份，原模型／用量unknown仍保留。

根据原质量反馈的1个空值，将本轮问题限定为“原配方只列已完成主检查，遗漏已有来源候选”。spec中的验收对为`research.source-selection`与`source-extraction-only-not-scientific-approval`，反馈ID取原提案实际引用，不使用模板占位值。原始工具来源仍是团队自写说明，`mapping_status=unresolved/endpoint_eligibility=unknown`。

```powershell
.venv/Scripts/python.exe -B scripts/run_recipe_improvement.py saved-export --evidence-root runs/a64-rsi-received-20261106/a64-rsi-handoff-20261106 --spec <按原反馈填写的spec.json> --output runs/recipe-rsi-a64-20261107 --round-id a64-saved-round
.venv/Scripts/python.exe -B scripts/run_recipe_improvement.py next-input --output runs/recipe-rsi-a64-20261107 --round-id a64-saved-round
```

实际离线结果为`keep`、有效v2，input SHA为`4986883d28a8050cfb1b187c9de6ca7dae5d94876e3d512d4453cd805516ccf6`；同参数重放相同。`next-input`确实读出该v2和前轮理由，保持`awaiting_next_feedback`。下一项问题保留原模型“采用后验证”建议与已保存独立验证顺序的差异，并要求先核对已读来源的未决状态，不重读原来源。这里没有伪造新反馈、候选v3或实际第二轮，也没有改写主团队已经完成的在线采用和后续行动。

必要检查覆盖无数据库导出、真实CLI及下一输入、原件读取前后字节一致、原回答／派生配方／来源资产篡改拒绝、路径越界拒绝，以及离线输入被原项目采用入口拒绝。保留并验证主线`saved-host --resume`与最新stage的`input_path`输出。实际新增模型、工具、来源读取、拟合、付费及原项目写入均为0；工程采用决定不等于科学收益。

在最新主线`cd3768f`上运行`.venv/Scripts/python.exe -B -m unittest discover -s tests -p 'test_*recipe*.py' -v`，48项全部通过，包含新增离线导出检查及主线阶段接续回归。上述两条实际A64命令在同一基线上重放成功，18份原件的SHA仍与ZIP全部对应。现有前端format/lint/typecheck均退出0，format34文件、修改0，无依赖安装或升级。

### Limitations

`load_saved_export`针对当前`a64-rsi-evidence-handoff-v1`导出格式，每份JSON或原始来源文件均限制为4 MiB。现有18文件A64包在此范围内；该离线入口不覆盖来源读取接口允许的全部32 MiB文件。包内一致性核对不认证缺失的原数据库或原模型执行，离线结果不能用于在线项目采用。

### 后续工作

1. 原A64有效v2已驱动一次分组画像并生成当前报告，四行工程样例已收口。下一项从真实研究材料中的未决问题选择，明确所需分析、来源与资源后接续。离线材料包保留为工程证据，`saved-host`入口继续通过原数据库和控制器账本核对。
2. **P1，真实多轮与验收类型**：同轮保存阶段接续已接入，prepared／pending可读取原提案与验证的后续回执，资源受限的真实多轮调度按实际任务继续。原Host未决状态先沿原入口核对。
3. **P2，扩充验收类型与结构化条件**：现判据只覆盖遗漏目标方法，文本条件不自动求值。根据真实问题增加小型、可比较的判据，不用选择变化代替收益。

后续从合并后的 main 选择依赖已满足的一项，围绕实际后轮问题推进中断接续或新的保存结果消费。PR合并由主开发执行。
