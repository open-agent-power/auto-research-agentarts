# 方法卡读取与宿主候选关联

2026-11-06，本轮改善：读入一张结构化方法卡，根据当前问题、范围与宿主条件，说明哪些已有方法可选、为什么可选，以及还缺哪些材料。入口是现有编译 CLI 和 `research_recipe.py` 的纯函数，不新增控制器、模型请求或研究执行。

## 直接运行一条完整过程

在产品根目录、已有项目环境中执行。输出目录必须尚不存在；重试时保留旧输出，改用新的预览目录。

```powershell
.venv/Scripts/python.exe -B scripts/compile_research_recipe.py --method-card examples/research-method-cards/feedback-driven.example.json --context examples/research-method-cards/conditions.context.json --output runs/my-method-card-preview
```

输入的当前问题是“当前 CSV 的零值集中在哪些声明分组，下一步如何核查？”。该 context **明确是构造接口示例**：声明 `data/tabular-quality-v1` 范围和 `batch` 分组，保存的构造质量反馈含零值；宿主提供一个分组候选，但尚无已登记的来源选区。示例使用合成身份并有实际计算的 context 封印，不表示有新的科学运行。

本轮实际执行退出码 0，输出以下要点，并生成唯一文件 `match.json`：

```json
{
  "status": "applicable",
  "card_id": "inspect-feedback-and-continue",
  "card_version": 1,
  "matching_candidate_ids": ["fixture-grouped"],
  "applicable_methods": [
    {
      "candidate_id": "fixture-grouped",
      "method_id": "data.grouped-quality-profile",
      "evaluation_ref": "grouped-quality-profile-v1"
    }
  ],
  "scientific_validation": false
}
```

完整输出的理由引用宿主条件：“已有质量反馈含零值，且输入声明了 batch 分组列”；缺口包含“与当前数据版本对应的零值编码和批次说明”“任务绑定的已登记原始来源选区”，并说明来源方法没有对应合法候选。卡片的依据、评价、反馈分支及来源定位均保存在结果 `card` 中，没有执行这些文本或读取其 URL。

下一决定：可以将已有分组候选交给原配方／控制器；来源方法暂不可选，应补交对应版本的说明并沿原项目登记。分组统计不能说明零值就是缺失，也不能批准批次独立性。真实执行仍需原项目的新鲜 context、原预算及显式提交，本预览本身没有执行任何方法。

## 函数与数据约定

```python
from autoresearch.research_recipe import parse_method_card, match_method_card

card = parse_method_card(raw_utf8_bytes)
match = match_method_card(card, original_sealed_selection_context)
```

`parse_method_card` 复用现有严格 JSON 读取，最多 64 KiB，拒绝重复字段、非有限数、非法 UTF-8 及非对象输入。`validate_method_card` 也可直接检查字典并返回深拷贝。卡片要求精确的 `research-method-card-v1` 字段：

- `id/version/question/rationale`：卡片身份、正整数版本和方法问题／理由。
- `scope_match`：仅 `domain/contract`。
- `method_refs`：1—16 对互不重复的方法与字符串评价引用，不接受参数或代码。
- `applicability`：`requires/not_applicable/uncertain` 的说明列表。
- `evaluation/feedback_branches/sources`：评价说明、带所需证据的反馈分支、可定位来源；均为知识，不是可执行规则。

卡片版本不是工具实现版本。工具的实际身份、参数和可执行性由宿主负责，方法与评价引用必须同时匹配。第一版未增加卡片自然语言条件求值器，也不靠问题文本相似度推断科学适用性。

`match_method_card` 首先用原 `validate_proposal` 的 wait 检查核对完整 context 封印，之后才读取范围、候选和条件。返回 `research-method-card-match-v1`：

| 字段 | 含义 |
|---|---|
| `card_id/card_version/card` | 原卡片身份及完整知识，返回值与输入互不共享可变内容 |
| `context_sha256/question/need` | 原 context 身份、当前保存计划的问题或 context.goal，以及原 need |
| `status/reasons` | `applicable/blocked/scope_mismatch/no_matching_candidate` 与实际条件记录；不是科学批准 |
| `matching_candidate_ids/applicable_methods` | 只包含宿主原候选，保持宿主候选顺序；仅 ID、方法与评价，不复制执行参数 |
| `method_matches` | 每对方法／评价的原宿主条件、关联 ID、理由与缺口 |
| `missing_information/host_blockers` | 精确方法／评价条件中的缺项与原宿主阻断，缺候选时明确提示，绝不创建候选 |
| `unreported_condition_refs` | 宿主没有提供对应评价条件明细的引用；不把“未报告”当成“满足” |
| `unverified_applicability` | 卡片中尚未自动核验的条件文本；`missing_information=[]` 不代表科学条件齐全 |
| `execution_status/scientific_validation` | 固定 `not_executed/false` |

有 blocker 或范围不匹配时，所有可关联候选 ID 清空。宿主条件只按完全相同的 `method_id/evaluation_ref` 关联，另一评价的缺口不能混入。`host_conditions` 保留原记录；旧 context 没有评价条件明细时保留 `unreported_condition_refs`，不猜测或修补旧 context。

## 与现有配方兼容

`--recipe` 仍输出原来的 `decision.json/proposal.json`，原 `compile_recipe`、八字段配方与六字段 proposal 保持不变。`--method-card` 与它互斥，只输出 `match.json`，不生成可执行 proposal。已有输出目录拒绝覆盖，输入必须是有界的普通 JSON 文件。

方法卡读取仅产生解释和关联，**没有改变两份固定配方的选择策略**。从匹配结果自动生成或修订配方属于后续任务，不能因卡片列出某方法就把它加入宿主允许集合。

`ProjectController.code_identity` 本来就包含 `research_recipe.py` 的文件哈希；新增辅助函数会改变该身份。历史项目和 context 不自动升级、不重写；本轮只读复用旧 context 的离线关联，不据此声称旧项目在当前代码下可以直接执行。在线操作仍沿原显式兼容登记／新鲜状态检查。

## 实际验证与运行记录

本轮基线是最新拉取的 `main 41afedcf0ef803ee9ce8a77c2424141175e2199c`。源码、CLI 与样例的工作树改动作为本轮验证身份；最终提交身份由 PR 固定，不把后续结果追认到旧提交。

```powershell
.venv/Scripts/python.exe -B -m unittest discover -s tests -p 'test_*recipe*.py' -v
# frontend 目录，沿用已有依赖和任务书门禁前缀
pnpm --config.verify-deps-before-run=false --config.offline=true --config.update-notifier=false run format
pnpm --config.verify-deps-before-run=false --config.offline=true --config.update-notifier=false run lint
pnpm --config.verify-deps-before-run=false --config.offline=true --config.update-notifier=false run typecheck
```

- 27 项配方相关检查通过，退出码 0，包括新增的卡片校验／关联／CLI、原配方、宿主、控制器、工作台和改进适配契约；使用隔离测试夹具，不重跑历史研究。
- 补充标准输出中的未报告／未核验条件，以及结构化评价不误匹配的断言后，最终 `test_research_recipe.py` 的 16 项定点复核退出 0，实际 CLI 再次输出完整方法、理由与缺口；没有重复其余未受影响的检查。
- 前端 format/lint/typecheck 全部退出 0，format 检查 34 文件、修改 0；未修改前端源码，未安装或升级依赖，无 UI 变更，未新增页面验收声明。
- 真实 CLI 对本次 `conditions` 和既有 `feedback/blocked/scope-mismatch/start` 构造 context，分别返回单候选适用、双候选适用、阻断、范围不符、无候选，均退出 0。`blocked` 等是成功完成查询后的状态，不是工具失败。
- 只读关联 2026-11-03 已保存的人工试点 context，保持其宿主来源→分组顺序；原 context 文件 SHA-256 仍为 `66499b53dac45d2d1f21045a974ad397c6ebc1959350b9d3e01d8faa282ce703`。这是旧快照的新增读取，不是重新执行试点。
- 原 `--recipe` CLI 对既有反馈 context 仍选择 `fixture-grouped`，输出两份原格式文件。拒绝覆盖及输入／context 篡改检查包含在专项测试中。

本机新输出保存在 ignored `runs/method-card-20261106/`；运行 JSON、真实资料、数据库和历史证据不提交 Git。生产研究新增模型／工具／拟合／付费调用为 0；隔离测试内的构造方法调用不冒充真实研究效果。

## 剩余问题与下一项

1. 方法卡首份PR已合并。队友从最新main开下一轮，关联实际反馈说明，接入`recipe_improvement`的采用或回退、有效版本及后轮读取。现有`propose_recipe_change/validate_recipe_change`由主开发维护。
2. A64原当前配方、完整冻结context、完整提案、验证输入与结果、关联Host及工件已整理为只读交接包，由负责人转交。[材料位置与下一份PR要求](a64-rsi-handoff.md)说明原件和派生视图的对应关系，先复用保存结果开发接续。
3. **P2，方法条件自动核验**：当前自由文本不能可靠地自动求值；后续若真实使用需要更细条件，应提出小型、可验证的宿主事实字段约定，不增加任意表达式或脚本入口。

第一轮未实现通用自然语言方法理解、反馈驱动策略收益、RSI 采用／回退或跨实例泛化。真实科学结论与用户价值仍需匹配的实际证据和专业判断。
