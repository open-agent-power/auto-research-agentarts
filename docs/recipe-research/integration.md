# 科研配方接入主控制器

科研配方是研究者明确写出的候选方法顺序。例如，先看零值在各组中的分布，或先读已经登记的来源。主控制器根据当前项目的真实候选挑选一步，保存理由并执行；取得反馈后，用新的请求重新选择。配方不修改数据、方法参数、评价或预算，也不调用模型。

## 当前两份配方

| 配方 | 方法顺序 | 适用问题 |
|---|---|---|
| [tabular-group-first](../../examples/research-recipes/tabular-group-first.json) v1 | 分组画像 → 已登记来源 | 已有表格主质量反馈，需要先定位异常分布 |
| [tabular-source-first](../../examples/research-recipes/tabular-source-first.json) v1 | 已登记来源 → 分组画像 | 未读资料可能解释当前字段或编码 |

两份配置都要求 `domain=data`、`contract=tabular-quality-v1` 和 `need=next_check`，只有方法顺序不同。匹配同时要求 `method_id` 和字符串 `evaluation_ref` 相同；同方法有多个候选时，沿宿主原候选顺序取第一个。更早的方法没有合资格候选，才考虑后一项；已完成的方法不会因列在前面而重跑。

有宿主 blockers、范围或 need 不匹配、没有可匹配候选时选择 wait，并记录原因。结构非法或 context 封印无效则报错。配置只接受 `research-recipe-v1` 的八个字段：`schema_version/id/version/question/scope_match/need/ordered_methods/on_no_match`。`question` 是研究问题文本，`on_no_match` 固定为 `wait`，不执行配置中的文字。完整适用条件、研究依据及零值含义的缺口见[研究说明](README.md)、[来源表](sources.csv)和[缺口记录](gaps.md)。

## 在工作台推进

研究页保留原五页导航和 X6 画布。展开操作区，在“按配方推进”选择顺序，先看当前预览，再明确提交一步或保存本次等待。反馈返回后才更新下一步；配方是确定性规则，不调用模型。模型、手工及有界批次入口保留各自身份。完整网页步骤与接口见[本地工作台](../local-workbench.md#按配方推进一步)，下面是同一控制器的 CLI 用法。

## 用现有项目推进一步

在产品根运行。项目应已完成主质量检查，并有真实可执行候选；来源只有在同项目登记后才可能成为候选。先读取当前状态和候选，保留这次的版本值：

```powershell
$projectWorkspace = "runs/my-study/project"
$state = .venv/Scripts/python.exe scripts/run_research_project.py status --workspace $projectWorkspace | ConvertFrom-Json
$decisionVersion = $state.state_version
.venv/Scripts/python.exe scripts/run_research_project.py selection-context --workspace $projectWorkspace --need next_check

.venv/Scripts/python.exe scripts/run_research_project.py advance-recipe --workspace $projectWorkspace --request-id recipe-step-1 --recipe examples/research-recipes/tabular-group-first.json --need next_check --expected-state-version $decisionVersion
```

`--expected-state-version` 必填，`--need` 默认 `next_check`。CLI 读取最多 64 KiB 的严格 JSON 配方，由 `ProjectController.advance_recipe` 在真实 context 中编译并提交，最多执行一个原 `step/read_evidence` 子请求；输出控制器结果，失败退出码为 2。配方命令本身不发送模型、下载来源、训练模型或增加额度。

同一 request ID、原配方、原 need 和**原版本值**再次调用，恢复同一个父/子请求。不能把原命令中的版本换成执行后的版本，也不能用同一 ID 换配方。waiting 同样冻结；取得新资料或反馈后，用新的 request ID 和新版本再作下一决定。未知执行状态沿原恢复路径核对，不用新 ID 绕过。

只想检查已保存 context 下两种顺序会怎样选择时，可运行只编译入口；它写出新的 `decision.json` 和原六字段 `proposal.json`，不执行研究：

```powershell
.venv/Scripts/python.exe scripts/compile_research_recipe.py --recipe examples/research-recipes/tabular-group-first.json --context runs/my-study/context.json --output runs/my-study/group-first-preview
.venv/Scripts/python.exe scripts/compile_research_recipe.py --recipe examples/research-recipes/tabular-source-first.json --context runs/my-study/context.json --output runs/my-study/source-first-preview
```

两个输出目录须尚不存在。旧 context 的编译结果只描述当时的候选；真正执行仍须在线检查当前项目、版本、代码身份和预算。不要修改 context 拼出双候选或重建项目消除已用额度。

## 保存什么，报告怎样核对

`research_recipe.compile_recipe` 生成 `research-recipe-decision-v1`：保存配方全文与 id/version、原 context 封印、范围/need/blockers 检查、每个方法及候选的选择或跳过原因，以及原六字段 proposal。proposal 的 provider 为 `operator_assistant`，说明为确定性配方且没有模型执行。

`ProjectController.advance_recipe` 把完整 `recipe_decision` 和六字段 proposal 一起保存到原 `controller_requests[].request`，命令身份为 `controller.advance_recipe`。原父请求保留 selection_context，执行仍复用同一 child 和原事务/恢复机制。配方不是另一个控制器；普通 `advance`、人工/模型 `advance_selection` 和 A26–A28 的模型原件链路继续各自保留身份。

现有四文件报告包继续使用 `report.pdf/report.md/report.json/input.json`。机器输入的 `recipe_selections` 保存请求 ID、原 context 和完整配方 decision；PDF/Markdown 展示配方 id/version、方法顺序、所选候选及跳过原因。报告中的配方选择、工具完成和 `scientific_validation:false` 分开呈现，不能把配置选中或来源抽取成功写成科学批准。

## 固定版本迁入与原实验记录

A29从队友原型固定提交 [`13054f5cf5b948c2251b197bdb3805864dd71b61`](https://github.com/1263-ux/auto-research-agentarts/commit/13054f5cf5b948c2251b197bdb3805864dd71b61) 迁入配方模块、编译与验证脚本、专项测试、两份 JSON 及四份研究资料，共 10 个此前不存在的文件。共享文档入口及索引按当时主线增补，保留已有 A26–A28 的 CLI、工作台和模型报告能力。

上游说明见 [PR #1](https://github.com/1263-ux/auto-research-agentarts/pull/1)（固定 head `03b08048cd2ca0d9177cb2aeae72234d9cab70c8`）和依赖它的[原型 PR #2](https://github.com/1263-ux/auto-research-agentarts/pull/2)（固定 head `13054f5cf5b948c2251b197bdb3805864dd71b61`）。A29当时仅在本地迁入，未执行远端合并或推送；这一历史事实不由后续合并改写。

[experiment.md](experiment.md) 保存队友当时的记录：人工 8 行试点初次因来源路径 `UNSAFE_PATH` 失败，在同项目修正来源布局后续跑；原九项测试及前端环境门禁也有各自的原执行时间与边界。补件后的只读更新未另跑这些实验。该文件中“没有真实配方选择”的叙述属于队友原记录，本轮主线的新增实跑须单独记账，不覆盖或追认原失败为成功。

## 2026-11-04：远端配方PR已合并

后续已按授权将PR #1合并为`1a295132b6e3c39b043cf609372a58b5d1b15a50`，再将PR #2从原依赖分支改为面向main后合并；两PR均为merged/closed，原head未改变。远端main为[`61a79ed2ddf56f3654b633e30cd30a30b1e6b778`](https://github.com/1263-ux/auto-research-agentarts/commit/61a79ed2ddf56f3654b633e30cd30a30b1e6b778)，tree与原PR #2 head一致；原九项测试和format/lint/typecheck通过，见[合并核对](../../runs/pr-merge-20261104/merge-validation.json)。此记录不重写原夹具或A29/A30实验。

随后[PR #3](https://github.com/1263-ux/auto-research-agentarts/pull/3)已将完整工作台源码合入main，代码基线为`04c2cfee836da6e61f099d65187a12d31da3dfb0`。队友取得最新`origin/main`并确认包含该基线后，独立开文档分支；五页工作台、模型反馈与当前说明已随源码分发。ignored `runs/`、作者原件和取证包仍由主开发另交，源码同步不代替研究结果或领域核对。

## 本轮真实接入验证

2026-11-04 使用原 hiMSC 的 972 行、6 列输入建立本轮集成项目。主质量检查执行一次后，同一原 context v3 自然具有“分组画像”和“未读作者 PDF/工作簿”两个候选；两份配方只读编译分别选择 grouped 和 source。实际只执行 group-first 路线：`a29-recipe-group-step` 从 v3 到 v7 完成分组；反馈后仅来源可用，`a29-recipe-source-step` 从 v7 到 v11 抽取作者 PDF/工作簿共 3 个选区；`a29-recipe-wait-step` 从 v11 到 v12 因无候选等待，没有 child。三个原 ID 用各自原版本重放，快照、行动和预算均无新增或变化。

本地工具累计 2/2，包含主质量检查和分组各一次；来源读取 1/8，本轮约定最多读取一次；新增模型及拟合均为 0，历史现金仍 unknown、原 5 元上限保留。机械结果为 3 条额外完全重复行、288 个声明组，三个数值列各 59 个零、分别涉及 56 组。作者选区已抽取不代表零值原因、ALP 映射、单位或样本独立性获批。

原四文件包一次导出成功，`input.recipe_selections` 保存 3 条决定，逐条用原配方和原 context 重编译完全一致；清单中四文件的 SHA-256/字节数核对通过，6 页 PDF 已逐页看图，无裁切或重叠。本轮 format/lint/typecheck 均退出 0，format 检查 33 文件、修改 0；迁入的 10 文件门禁前后原字节未变。集成证据保存在本机 ignored [`runs/a29-recipe-integration-20261104/`](../../runs/a29-recipe-integration-20261104/)，见[报告核对](../../runs/a29-recipe-integration-20261104/report-validation.json)和[本轮门禁](../../runs/a29-recipe-integration-20261104/frontend-gates/result.json)。

本轮驱动的两处问题分别保留：首次来源 manifest 错用 schema，原件另存为 `manifest.failed-schema.json` 后在同项目按正式 `project-evidence-bundle-v1` 修正，没有重建或重跑主检查；导出后核对代码误把 SHA 字符串与清单对象直接比较，修正为核对 `sha256/bytes`，保留同一份原报告，没有重新导出。这是集成验证，source-first 臂仅编译未执行，没有证明配方优于固定流程。

## A30 网页实跑

2026-11-04，原五页/X6研究操作区已支持两份配方预览与明确推进。归档真实hiMSC输入在[18793](http://127.0.0.1:18793/#/research)通过实际按钮完成分组→作者原件读取→等待；主质量bootstrap计一次，本地2/2、来源1/8、模型0/拟合0。三个捕获的原请求经同HTTP入口重放，原child与状态/用量不变。

一次浏览器报告导出及PDF下载成功，四HTTP下载与保存文件一致；input保存3份完整配方，6页PDF逐页看图。桌面/手机全页与分段实看，两端五页切换/草稿/键盘已核；一次模拟预览GET失败只验证禁用和清除旧预览，不是实际资料故障。2项后端必要检查及最终前端门禁通过。旧项目和额度保留，未另跑source-first收益比较，详细[证据](../../runs/a30-recipe-workbench-20261104/validation.json)仅支持工程接入范围。

## 怎样评价后续推进

同一真实 context 下两份配方选不同候选，只能证明配置影响选择。执行、原 ID 重放和报告原件还需各自核对；研究收益则需要在同资料、同工具、同预算下检验反馈是否减少关键未知、避免错误接受或帮助研究者决定下一步。

当前零值、分组独立性、单位和终点含义仍需对应版本的作者说明及领域判断。不能因为分组画像完成就解释零值原因，也不能因为论文抽取完成就批准字段映射。原三题六臂[固定流程比较](../policy-comparison.md)保留其同路线结果，不为制造收益删掉强固定流程的核对步骤。
