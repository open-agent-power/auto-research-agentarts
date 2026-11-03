# 同项目的受限外部选择提案

`selection-context`导出宿主可核对的条件、预算、可执行候选和FTS来源原文；`advance-selection`接收一个上下文绑定的提案，在既有[ProjectController](../src/autoresearch/project_controller.py)中冻结父请求，再至多执行一个白名单行动或等待。原`next/advance`固定策略保留。2026-11-03已用封存钢材输入走通主方法、选择第二份资料、引用真实反馈后等待的CLI链路，结果与边界见下文。

候选的`method_id/parameters/evaluation_ref`由宿主确定，提案只能选择候选`id`或等待，不能更改目标、原始结果、评价、工具参数或预算。可用行动仍限已登记白名单方法和已登记未读来源；没有任意代码、命令或网络工具。

## 导出上下文并提交等待提案

以下在产品根执行，`$projectPath`必须是已有项目；两个输出文件须为新文件。旧项目若代码身份变化，先按[项目说明](project-slice.md#在同一项目接回来源)显式upgrade，不能绕过unknown或重置预算。

# 先阅读context的条件、候选和来源。本例明确选择等待，不执行候选。
$proposal = @{
    schema_version = 'project-selection-proposal-v1'
    context_sha256 = $context.context_sha256
    provider = @{ kind = 'operator_assistant'; label = 'Development assistant / bounded selection' }
    choice = @{ kind = 'wait' }
    rationale = '保留当前基线，等待补充加工条件来源与评价。'
    evidence_citation_ids = @()
}
[System.IO.File]::WriteAllText($proposalFile, ($proposal | ConvertTo-Json -Depth 8), $utf8)
.venv/Scripts/python.exe scripts/run_research_project.py advance-selection --workspace $projectPath --request-id my-selection-1 --proposal $proposalFile --need next_check --expected-state-version $context.state_version
```

等待也会保存固定父请求并推进版本，可能使旧报告stale；它不产生工具行动。上述provider须改为实际提交者，rationale也应说明真实选择原因。若决定执行，读取`context.candidates`，把choice改成`{"kind":"execute","candidate_id":"从该候选的id原样复制"}`；不从提案提交method或参数。只有宿主复核后仍合资格、未完成/未读且预算允许的候选才能执行。

## 提案与恢复边界

提案严格包含六个字段，不接受额外字段：

| 字段 | 允许内容 |
|---|---|
| `schema_version` | 固定`project-selection-proposal-v1` |
| `context_sha256` | 原上下文的封印SHA |
| `provider` | 仅`kind/label`；kind为`operator_assistant`、`human`或`external_model` |
| `choice` | 仅`{kind:wait}`，或`{kind:execute,candidate_id:实际候选id}` |
| `rationale` | 1至4000字符的非空选择理由，不是科学批准 |
| `evidence_citation_ids` | 至多16个互不重复的真实`context.evidence[].citation_id`；没有引用时为空数组，不编造引用 |

CLI按既有安全文件读取器捕获至多64KiB提案，再由[project_selection](../src/autoresearch/project_selection.py)严格解析UTF-8/JSON；重复键、NaN/Infinity、越界或额外字段会拒绝。上下文顶层含`state_version/context_sha256`；候选主键为`id`，证据含`citation_id/source/quote/location`。上下文是只读宿主检索结果，不表示模型已读。

接受新父请求前核对真实state、snapshot、core/controller/context身份和原件/预算，过期提案不能因重新选择而悄悄执行其他项。完整context与proposal随父请求保存；同ID重放先恢复原内容，不重新检索后改选，等待也冻结。重放保留原proposal、need与原`expected-state-version`，不要用当前版本替换；参数冲突拒绝。已有child沿原ID恢复，unknown不重发，不能用新提案绕过。

等待只使该父请求不产生child，不是暂停全部项目或宣布方法耗尽。Project保存的工具反馈/固定下一建议继续保留，后续新上下文仍可列出未读候选；最近外部决定与固定建议是两个有明确出处的记录，只读界面与报告分别标注它们。

## 在只读界面与报告中核对

| 只读下载 | 保存内容 |
|---|---|
| `/api/project/selection-context.json` | 当前宿主条件、候选及证据，含context封印；可加`?snapshot_ref=<当前项目快照>`绑定下载，项目变化时拒绝旧快照 |
| `/api/project/selection-request/<request_id>.json` | 原父请求，包含当时的完整context/proposal及选择/子行动绑定，不能用当前context替换原记录 |

报告JSON的`selection_history`复用[selection_view](../src/autoresearch/project_selection_view.py)已校验投影：最近最多12条、newest-first，并保留total/omitted；原完整父记录仍在`project.controller_requests`。Markdown摘要最多3条，PDF最多2条，包含理由、来源声明、是否有child/状态、引用定位和单独标注的历史固定建议，不抄整份上下文。没有导入选择的项目不补造记录；校验失败明确拒绝，不伪装为空历史。

provider身份和模型执行始终未核验。引用片段是宿主保存的真实出处，不能据显示它就声称模型读过、引用解释正确或获得科学批准。查看/下载/导出不执行方法、提案或模型，不消耗新的研究工具额度；完整内容与版本仍以对应JSON和SHA清单为准。
