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

9 项专项测试退出 0。没有重跑全量研究、旧六臂比较、训练或模型。一次 fresh-context 只读复核未发现阻塞问题。首次提交门禁：frontend 使用任务书的 offline pnpm 前缀，format 退出0（32文件，0修改）；lint/typecheck 均退出1，缺现有 `frontend/node_modules` 和 `tsc`，首次未安装，PR 因而先以 draft 交付。该历史失败保留；下面的续办已关闭环境门禁缺口。

## 原续办：前端门禁已通过，补件前的交接状态

2026-11-03 用户要求继续完成未完成部分。先核对本机缓存，只有部分包可用，不能用不同版本冒充锁定工具链；随后显式恢复已有锁文件中的开发依赖，安装与门禁分开执行，禁用安装脚本：

```powershell
# frontend 目录；只恢复已有依赖，不新增或升级依赖项。
npm ci --ignore-scripts --no-audit --fund=false --fetch-retries=0 --fetch-timeout=30000
pnpm --config.verify-deps-before-run=false --config.offline=true --config.update-notifier=false run format
pnpm --config.verify-deps-before-run=false --config.offline=true --config.update-notifier=false run lint
pnpm --config.verify-deps-before-run=false --config.offline=true --config.update-notifier=false run typecheck
```

安装退出0，恢复10个包；核对顶层版本为TypeScript7.0.2、X6 3.1.8、tslib2.8.1、esbuild0.28.2，package.json/package-lock.json的前后SHA相同，没有新增依赖项、版本升级或安装脚本执行。依赖包下载有开发环境网络/I/O成本，不属于研究工具、模型、拟合或来源读取次数。

| 本次实际门禁 | 退出码 | 结果 |
|---|---|---|
| format | 0 | 32文件，0改动 |
| lint | 0 | 原tsc --noEmit --noUnusedLocals --noUnusedParameters通过 |
| typecheck | 0 | 原tsc --noEmit通过 |

续办仅更新文档与开发依赖环境，不改配方、编译器、执行内核和研究输入；前述测试及同项目实际试点按原身份与范围保留，没有另跑第二次研究实验或消耗历史预算。PR1的续办说明同步进入本PR，仍保留两PR的依赖关系。

补件前的只读查找覆盖ICT、参考库及相关ZIP清单，当时未取得对应CSV/spec/保存质量与分组项目或11月1日笔记；旧参考运行是engineering-polynomial-v1人工夹具，不能替代真实证据。**这一“未取得材料”的状态已被下述补件更新，不再是当前缺口。** 保留原环境失败、修复和门禁结果，不重跑。

工程门禁已完成，原型可进入审阅；真实效果验证仍未完成。当前只需版本匹配的采集/导出与领域解释，不再重复索要已收到文件，不把未审定解释写成科学确认。

## 补件更新：只读复用原工程证据，不重跑

2026-11-03 用户补交 `队友补件-科研配方-20261103.zip`，SHA-256 `ab7649c4db5e93629551c7ebea4db0f6c9db1b7fe2a66a21c7ea6cf783a9c780`。钢材/hiMSC CSV、spec、来源声明、保存质量/分组/来源抽取、三个hiMSC历史context和11月1日笔记已收到。各条目字节身份、内容封印及前序链路见 [gaps.md](gaps.md#补件身份与已保存反馈)。不扩展来源表或综述，不执行附件代码，不上传真实原件。

本次只更新三份科研配方 Markdown 及 PR 说明，工程实现、测试、配方配置和原夹具不变。复用上述9项专项测试和三项前端门禁的原记录，不声称是本次新测试；独立unittest stdout文件未作为附件取得，不补造。原双候选context、两份proposal、protocol、人工CSV/spec、实际执行/相同请求重放输出及results以PR附件提供，原运行目录和SQLite仍不提交。只核对既有文件字节哈希、文档差异和远端身份，不重新编译、执行或重放。

审阅附件：[PR #2 原人工夹具与执行/重放记录](https://github.com/1263-ux/auto-research-agentarts/pull/2#issuecomment-6607031366)。每份文本附原文件字节SHA-256，明确区分context封印与文件哈希，保留路径修复前protocol的身份和原失败边界；不是重建或新执行结果。

## 真实问题：反馈前后下一决定

问题及原件：默认真实案例改为 **hiMSC（A16 / himsc-final）**：Count和红/绿色强度的零值是什么意思，Topo/Chem分组是否具有实验含义？CSV是声明原工作簿B8S1!A1:F973保存单元格的投影，972条记录；不求值公式、不删除0或重复行，完整工作簿未交付。钢材A16投影的312行目标零值为0，保留为输入条件对照，不再用派生成分零值解释目标测量零。

当前条件与仍缺条件：保存结果中Count、Mean_Red_Intensity、Mean_Green_Intensity各59零；Topo/Chem声明288组、每组3–6行，各数值列零值分别落56组、单组最多2个，完整重复额外记录3条。相同零值数不证明逐行共现或成因相同；分组和重复统计不证明独立实验、批次或重复原因。单位仍为unknown raw intensity proxy，目标状态declared_unconfirmed，不能改称ALP；采集/导出、单位/终点及分组定义仍缺领域解释。

人工固定流程原本会做什么：核对原件/字段/来源 → 看已有质量结果 → 必要时看已有分组结果 → 决定还需什么证据。保留全部核对及未知；同样资料下没有删步骤制造弱基线。

配方选择及理由：来源与分组优先的有用条件仍是待验证假设；本次没有执行真实配方选择。原样历史context在同一项目的state_version 5/9/11分别只有1个来源候选、0候选、1个分组候选，不能拼接为同一真实双候选，更不能据此比较两配方收益。materials范围不匹配时，两data配方仍应等待；不能改context或重置预算。

实际取得的反馈、出处和时间：2026-11-03只读补件中的保存主质量、分组与source-selection结果，核对条目字节哈希及分组前序绑定，没有重跑这些工具。source-selection只抽取宿主spec的text_lines 1–28，并非作者采集/导出说明；仍为mapping_status=unresolved、endpoint_eligibility=unknown、scientific_validation:false。数据身份和已有分布缺口关闭，零值语义及科学适用性没有关闭。

反馈后的下一决定：不再寻找已收到的CSV/spec或重复计算已有分布；只需该版本的采集、计数为零时强度导出、缺失/检测下限、单位/终点及分组/重复说明，或针对具体字段的领域核对。读取同一宿主spec不能补齐作者语义；当前保留“hiMSC零值原因未知，暂不改值/删行”。取证建议不是未经当前context授权的可执行提案。

谁核对了结论，核对范围：开发助手只读核对补件身份、保存统计与链路；没有作者、老师或领域队员对零值、独立性或终点的专业判断，不能称其已批准解释。

是否有帮助：**真实配方收益未知**。补件关闭了文件与已有分布的取证缺口，但不证明配方优于强固定流程，不凑正面结论。真实效果验证保持未完成。

成本：原工程项目研究工具2、来源读取0；登记与失败有实际I/O/哈希/校验成本，历史成本和现金结算仍unknown。本次补件核查仅本地读取/哈希/文档与PR更新，没有新增研究工具、模型、拟合或付费/云调用，也未重跑测试/门禁；I/O与人工成本不冒称为0，人工耗时未测量。

需要主开发者/领域判断者提供：仅上述hiMSC版本匹配的采集/导出和字段/分组/终点说明。CSV/spec、保存结果/context与11月1日笔记不再重复索要。原因查不清继续保留未知；不要求为本轮工程审阅新跑真实研究或补造双候选。PR #1与依赖它的原型PR #2保持可审阅，未自动合并。

## Limitations

人工夹具仅证明配置影响合法选择并能沿原控制器执行；不能证明0是错误、分组独立、自动科研完成、策略优于人工或跨领域泛化。真实比较需预先冻结同资源方案并使用未参与调参的任务。本轮不修改真实数据、不补值、不训练、不调用模型、不扩大历史授权。
