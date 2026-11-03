# 配方工程实验与真实问题记录

日期：2026-11-03。共同基线 `7e8ffd90ed6826df7ea1487660645152b533045a`；配方说明提交 `e5d1df9`。本原型依赖说明 PR，尚未合并时以其分支为比较基线。原内核、方法目录、五页界面和历史研究账本均未改动。

## 执行前的方案与失败判据

这里检验配置能否改变**同一候选集合**中的选择，并通过原宿主执行一次。两配方使用相同问题、材料、工具、need、评价、预算和未改动 context。来源优先提案仅编译和校验，不执行第二臂；这不是效果、成本或科学结论的配对比较。

夹具是脚本公开生成的 8 行人工数据：`record_id,batch,value`，A/B/C/D 各两行，数值依次 0/2/3/4/0/6/7/8。每行单位声明为“人工构造行，不代表独立实验”，target/unit 均为 null。CSV 原字节 SHA-256 为 `38ae8887357fb8cce755608139fa0c0f326af54320c2df12e0e7268867af6bf4`，来源为带该身份的 synthetic URN，没有占位哈希。

执行前 `protocol.json` 已冻结输入哈希、实现文件哈希、宿主代码身份、预期、顺序和失败判据。下列任一情况算失败：冻结 context 没有分组/未读来源两个合法候选；顺序不改变选择或原 validator 拒绝；执行/重放增加意外行动；预算、8 行/4 组/2 零计数不符。出现失败保留实际 conditions/candidates/blockers 和原运行目录，不编辑 context 或创建新项目重置额度。

## 实际命令、失败与同项目续跑

使用 Python 3.13.9 的本地 `.venv`，继承本机已有依赖；项目安装命令为 `python -m pip install --no-index --no-deps --no-build-isolation -e .`，退出 0，无新增依赖下载。先阅读原 CLI 及 prepare-source/evidence-task/register-evidence/advance-selection 的帮助。

在产品根执行的首次入口：

```powershell
.venv/Scripts/python.exe scripts/verify_research_recipe.py --output runs/recipe-pilot-20261103
```

首次 runner 在 `05-register` 失败，原 CLI 退出 **2**，原始 code 为 `UNSAFE_PATH`：bundle 来源路径必须严格位于 `sources/` 下，初稿错误生成 `source.txt`。宿主拒绝了该输入；此时主检查已执行 1 次，来源登记/读取均未成功。外层 PowerShell 工具报告进程退出 1，不能把首次入口记为通过。

修复仅将来源路径改成 `sources/source.txt`。旧 `bundle/`、`failure.json`、`commands.json` 和所有 stdout/stderr 保留；在同一根目录创建 `bundle-corrected/`，沿用实际 evidence-task 的 task_ref、同一原字节/哈希和原登记 request-id。只读 status 先确认主行动 1、来源行动 0、登记 0，随后登记并继续，不再次执行主检查、不新建项目或扩预算。一次性续跑脚本保留在本机 ignored `.agent/evidence/continue_recipe_pilot.py`，实际命令退出 **0**：

```powershell
.venv/Scripts/python.exe .agent/evidence/continue_recipe_pilot.py
```

成功部分复用正式 runner 的 `Pilot.finish()`，原 CLI 及两次 compile 的实际命令/退出码保存在 `commands-recovered.json`。首次完整 runner 失败、同项目受影响步骤续跑通过是两个分别保留的事实；修正后的新目录完整入口未另跑第二次实验。公开 runner 已包含正确的 `sources/` 布局，供新环境复现。

实际项目为 `project-add682ecdffc494b8cf87cfab503305e`，run 为 `run-70c80ce555664cf68ef2dbbc4bd7aa3d`。步骤顺序为 prepare-source → create(上限2) → step → evidence-task → register-evidence(拒绝并修正) → selection-context → compile 两配方 → advance-selection(group-first) → status → 完全相同参数重放 → status。

## 实际结果

| 核对项 | 实际值 |
|---|---|
| 冻结 context 的合资格候选 | 2：分组画像和未读来源；blockers 为空 |
| 两配方在同一 context 的选择 | group-first → data.grouped-quality-profile；source-first → research.source-selection |
| 两份 proposal 通过原 validate_proposal | 是；均为原六字段，provider=operator_assistant，label=deterministic recipe policy; no model，引用为空 |
| 实际执行 | 原控制器执行分组画像 1 次；来源提案只校验 |
| 相同父请求重放 | 原 request-id/proposal/need/expected-state-version；新增行动 0，child ID/snapshot/state_version 不变 |
| 累计工具与来源 | 主质量+分组=2，local_tool_dispatches=2，上限2；来源读取0，来源行动0 |
| 数值与分组 | 8 个有限值、2 个零，无缺失/非法/非有限数；4组，每组2行；A/C各1个零，B/D为0 |
| 新模型/拟合/付费调用 | 0/0/0；历史现金和历史请求仍 unknown，不改写为0 |
| 科学状态 | scientific_validation:false |

冻结 context 的内容封印为 `2eff30f11ee0badda651043a94f40b852e36c22bd8125d5d6ce454462df2e70d`；`context.json` 文件字节 SHA-256 为 `66499b53dac45d2d1f21045a974ad397c6ebc1959350b9d3e01d8faa282ce703`，两者含义不同。编译和执行后再次核对文件哈希不变。

可核对的本机证据在 ignored `runs/recipe-pilot-20261103/`：`protocol.json`、`failure.json`、原/修正 bundle、`commands.json`、`commands-recovered.json`、`context.json`、`group-first/`、`source-first/`、逐步 stdout/stderr、原项目及 `results.json`。不提交 SQLite、原运行目录、受限全文或私有原件。

代码身份：原项目核心 `c12071b2a175672a0c45eb8e252f15084f693d8f8ef3c0495384c80210760726`，控制器 `d5a08ec68bc0250951885459e195fdbe3374fa6fc8ff268b42d0b92d80e5e5e7`。首次 runner 的哈希及修复差异保留在 protocol 和本机修复记录中；实际成功部分调用修复后的 `finish()`。配方/纯选择模块/编译器未因这次路径修正改变。

## 自动检查与复现入口

三组必要检查由 `tests/test_research_recipe.py` 的 9 项测试覆盖：闭合 schema/类型/范围与 need；候选顺序、等待、输入不变；原协议及 context/candidate/参数/引用篡改拒绝。原 validator 只验证封印内容一致性，在线项目身份和预算仍由原控制器重查。

```powershell
.venv/Scripts/python.exe -m unittest discover -s tests -p test_research_recipe.py -v
# 新环境只运行一次；已存在的输出目录会报错，不能用换目录规避已运行项目的预算。
.venv/Scripts/python.exe scripts/verify_research_recipe.py --output runs/recipe-pilot-new
# 仅复核选择时，不再执行研究工具；两输出目录也须不存在。
.venv/Scripts/python.exe scripts/compile_research_recipe.py --recipe examples/research-recipes/tabular-group-first.json --context runs/recipe-pilot-20261103/context.json --output runs/recipe-pilot-20261103/manual-group-first
.venv/Scripts/python.exe scripts/compile_research_recipe.py --recipe examples/research-recipes/tabular-source-first.json --context runs/recipe-pilot-20261103/context.json --output runs/recipe-pilot-20261103/manual-source-first
```

9 项专项测试退出 0。没有重跑全量研究、旧六臂比较、训练或模型。一次 fresh-context 只读复核未发现阻塞问题。提交门禁：frontend 使用任务书的 offline pnpm 前缀，format 退出0（32文件，0修改）；lint/typecheck 均退出1，缺现有 `frontend/node_modules` 和 `tsc`，未自动安装。环境门禁尚未全部通过，PR 以 draft 交付。

## 真实问题：反馈前后下一决定

问题及原件：任务书所指钢材 CSV 的 0 是测量还是缺失、是否集中分组。该 CSV、spec 和保存质量/分组项目未定位；本次不把包内 Matbench gzip 当作已经取得的 CSV。

当前条件与仍缺条件：本地包内 `matbench_steels.json.gz` SHA-256 `473bc4957b2ea5e6465aef84bc29bb48ac34db27d69ea4ec5f508745c6fae252`，8,836 bytes，匹配官方固定元数据。原始字段仅 composition/yield strength，目标单位 MPa；分组/试样重复及具体 CSV 零值字段未知。

人工固定流程原本会做什么：核对原件/字段/来源 → 看已有质量结果 → 必要时看已有分组结果 → 决定还需什么证据。保留全部核对及未知；同样资料下没有删步骤制造弱基线。

配方选择及理由：在查看数值反馈前，先核对来源身份更可能帮助区别真实测量、派生编码和导出占位，这是人工提出的待验证判断。实际没有可用的真实双候选 context，因此本任务目前不能区分两配方，没有伪造真实选择记录。materials 范围不匹配时，两 data 配方都等待。

实际取得的反馈、出处和时间：2026-11-03 只读解压上述原件：312行，屈服强度0值为0，范围1005.9–2510.3 MPa；主集成者再次独立核对相同计数。官方 matminer commit `9fca4fde11617279096e194ebe72e3a0bf48477e` 的 `matbench_steels` 字段/hash/num_entries 对应。项目 `datasets.py::_parse_composition` 的 `amounts.get(element, 0.0)` 明确表明本项目派生成分特征会为未出现元素填0；这条代码证据不解释所有钢材测量0。三项来源及定位见 [sources.csv](sources.csv)。

反馈后的下一决定：从笼统的“解释钢材0并按组比较”收窄为先取得具体 CSV/spec/导出与变换身份，确认零值列和真实分组后，再索取对应采集/编码说明。当前保留“该 CSV 零值含义未知，暂不改值/删行”。

谁核对了结论，核对范围：开发助手只核对字节身份、字段、数值计数和代码转换；没有作者、老师或领域队员对具体 CSV 的专业判断，不能称其已批准解释。

是否有帮助：**目前无法判断真实配方收益**。现有反馈避免了把目标测量零和项目派生零混为一谈，并明确下一项索取材料；它不证明配方优于强固定流程。真实效果验证保持未完成。

成本：工程项目实际研究工具2、来源读取0；来源登记有实际I/O/哈希/捕获成本，失败路径亦有校验成本。资料核查采用3项关键一手来源和本地只读核对，检索/核查成本不记为0；命令执行秒数在日志自动测量，人工耗时未测量。新增模型0、拟合0、付费调用0；历史消耗未知继续保留。

需要主开发者提供：具体钢材 CSV/spec/保存质量与分组结果或可分享摘录及哈希；采集者/作者解释零值与单位/批次定义；可分享的11月1日配方审查笔记。需要领域判断者核对的仅是这些真实字段与下一决定，工程原型不等待其确认才可审阅。

## Limitations

人工夹具仅证明配置影响合法选择并能沿原控制器执行；不能证明0是错误、分组独立、自动科研完成、策略优于人工或跨领域泛化。真实比较需预先冻结同资源方案并使用未参与调参的任务。本轮不修改真实数据、不补值、不训练、不调用模型、不扩大历史授权。
