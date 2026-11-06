# A64冻结接续材料与当前状态

更新于2026-11-07。PR19、20、22、23已合并，方法卡、单轮采用／回退、项目有效版本、页面采用与后续工具执行均已交付。原A64已采用v2，完成分组画像并导出state20报告。本页保留11月6日冻结包的内容映射，最新执行范围见[实际接续](rsi-delivery.md#a64有效v2的实际后续行动)。

## 先取得材料

主开发已整理`A64-RSI接续材料-20261106.zip`，由负责人通过团队文件渠道转交。压缩包包含A64工程实例的原始记录和便于读取的派生JSON，运行材料按仓库约定独立分发。

队友先拉取最新main，再把压缩包解到仓库的`runs/`，得到`runs/a64-rsi-handoff-20261106/`。从包内README和`handoff.json`开始，按下面的对应关系读取。包内原件使用项目相对路径，派生文件均在`derived/`。

把收到的压缩包放入`runs/`后，在产品根目录解包。

```powershell
Expand-Archive -LiteralPath .\runs\A64-RSI接续材料-20261106.zip -DestinationPath .\runs
```

| 要取得什么 | 包内位置 | 使用方式 |
|---|---|---|
| 原版配方 | `derived/current-recipe.json` | 原生`research-recipe-v1`，版本1 |
| 完整冻结反馈与目标 | `project/host-model-selections/requests/0001/context.json` | `research_context`传给trace，`improvement_goal`作为原目标 |
| 冻结候选选择上下文 | `derived/selection-context.json` | 与原context中的`research_context.selection_context`相同，供只读CLI预览 |
| 原始回答 | `project/host-model-selections/requests/0001/delegated.bin` | 原协作子代理回答，保留模型原文与验证建议 |
| 完整提案 | `project/host-model-selections/requests/0001/proposal.json` | `recipe-change-proposal-v1`，包含候选、理由与反馈行动引用 |
| 提案适配返回视图 | `derived/proposal-result.json` | 按既有适配器返回字段从保存记录导出，`candidate`仍是完整提案 |
| 候选配方 | `derived/candidate-recipe.json` | 打包时的原生候选v2，当前采用状态见外环结果和项目修订 |
| 原验证权限与输入 | `project/host-model-selections/requests/0001/validation-input.json` | 对照原请求、允许方法、来源收据和两版选择 |
| 原验证结果 | `project/host-model-selections/requests/0001/validation-result.json` | 原`recipe-change-validation-v1`，直接供外环消费 |
| 关联Host与实际工件 | `project/host-model-selections/state.json`、`project/artifacts/` | 定位原请求、反馈行动和实际来源读取结果 |
| 原始工程输入与来源收据 | `project/source.json`、`project/evidence-inputs/` | 核对原四行构造输入与团队自写说明 |

提案适配结果与候选配方的层级沿[接口约定](team-module-interface.md#主开发的配方改进适配接线)。`proposal_result["candidate"]`是完整提案，`proposal_result["candidate"]["candidate"]`才是候选配方。采用决定已由单轮外环及项目`recipe_revisions`分别保存。

## 当前记录已经说明什么

原请求为`a64-recipe-change`。版本1在冻结context下选择wait，版本2选择已有来源候选。原控制器已按允许方法和来源收据取得一次来源结果，保存验证状态为completed。Host保留原proposed记录，外环已判定keep，项目已明确采用v2。默认控制器随后使用有效v2完成一次分组画像，当前为state20、等待补资料。

这条轨迹来自四行构造数据和团队自写运行说明。模型提案及工具执行均为实际调用，数据用途为工程联调。当前本地方法2/2、来源1/8、Host1/1，该样例作为已完成工程证据保留。下一项从真实材料中的问题选择，按原累计资源和明确的运行范围安排。

## 已完成的单轮交付

原起步问题为“已有候选和验证结果已经保存，怎样形成明确决定，并让下一轮沿有效版本继续”。以下五项已经交付，后续优先级见[长期任务书](team-module-handoff.md#当前起点)。

1. 提供`recipe_improvement.py`的一轮入口，接收当前版本、原目标、实际反馈、提案和验证结果。
2. 保存原版、候选、采用或回退决定及理由，输出当前有效版本和下一步。
3. 重开同轮时读取已保存结果，后轮读取当前有效版本。已完成的候选和验证通过原结果接续。
4. 提供`scripts/run_recipe_improvement.py`的实际命令、输入输出示例与使用说明。
5. 针对采用、回退和接续做必要检查，记录实际结果，在PR中说明剩余整合点。

已有`propose_recipe_change/validate_recipe_change`由主开发维护。外环通过普通函数参数连接它们。使用本包开发时，读取已保存的提案和验证结果作为输入，原累计资源记录一并保留。原项目采用和后续工具行动已接通，同轮阶段恢复、后轮Host提案与有界多轮外环继续开发。

先在产品根目录核对方法卡读取入口，输出目录使用尚不存在的新目录。

```powershell
python -B scripts/compile_research_recipe.py --method-card examples/research-method-cards/feedback-driven.example.json --context runs/a64-rsi-handoff-20261106/derived/selection-context.json --output runs/a64-method-card-preview
```

这条命令读取冻结context，生成候选关联结果。单轮采用、有效版本及后续执行的已完成证据见[RSI交付](rsi-delivery.md)，方法卡预览保留自身的只读范围。

## 分支 推送与反馈

队友从最新main选择同轮阶段恢复或实际配方问题，下面以阶段接续分支为例。

```powershell
git switch main
git pull --ff-only origin main
git switch -c feat/recipe-stage-resume
```

完成一项独立能力后提交并推送该分支，创建目标为main的PR。开发尚在进行时可先交Draft PR，写明卡点和下一次交付。推送后的检查与合并由主开发接续。

```powershell
git push -u origin feat/recipe-stage-resume
```

每个实际开发日反馈完成内容、实际结果、当前卡点和下一步。周二、周五为常规PR窗口，完成可提前交付。阶段日期作为目标随实际进度调整，长期队列见[任务书](team-module-handoff.md)。

## Limitations

材料包支持读取已有证据与开发外环。原项目在线写入需要数据库、原累计权限和兼容源码登记，由主开发在原工作区接续。包内原始Host资源配置属于历史记录。

原模型建议的验证顺序与实际执行顺序有差异，原回答和独立验证均保留。选择改变及工具completed说明本轮发生了什么，科研收益、跨实例效果与持续改进收益仍需对应证据。模型身份、原生用量与现金结算中的unknown继续使用原口径。
