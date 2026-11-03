# 表格质量与分组核对

## 输入目录与声明

```text
my-tabular-input/
  spec.json
  file.csv
```

`spec.json`严格只含以下字段；`file`是同目录一个安全CSV/TSV文件名，禁止任意目录或代码路径。示例中的来源、标签、字段与SHA必须替换为实际值，不能把模板当证据：

```json
{
  "schema_version": "tabular-quality-spec-v1",
  "file": "file.csv",
  "dataset_label": "填写实际数据及版本",
  "source_url": "填写实际来源URL或明确的宿主派生URN",
  "license_note": "填写原来源许可及仍未核对的范围",
  "sample_unit": "填写每行代表什么；独立性仍待核对",
  "group_columns": [],
  "key_columns": [],
  "numeric_columns": ["value"],
  "target_column": null,
  "target_unit": null,
  "missing_tokens": ["", "NA"],
  "delimiter": ",",
  "provenance": {
    "origin_sha256": "替换为上游原件64位小写SHA256",
    "description": "记录原件到本CSV的实际转换，或明确原CSV直接捕获"
  }
}
```

group/key各可声明0至8列，numeric须为1至32列，均须与实际表头精确对应。若声明target，必须属于numeric并给出非空unit；不声明时两项均为null。来源、许可、sample_unit、字段角色、target和单位都只是提交者声明；`scope.target_status`始终为`declared_unconfirmed`。上游SHA及转换说明被保存，不代表适配器已取得或核验该上游原件。

CSV/TSV上限8MiB、spec上限64KiB；严格UTF-8，可带BOM，分隔符只允许逗号或tab。表头1至128列、无空名或歧义重名；数据至多50000条，须为与表头等宽的矩形CSV。拒绝NUL、非法编码/CSV和不存在的声明列，不执行公式或来源内容。封存包保留两份输入的原字节、SHA与大小；不改写原输入。

## 复用项目命令

先准备真实输入目录。下例的输出和项目目录须新建，且与输入分离；`--budget-ref`填写原任务的真实预算归属，不用新目录重置历史或增加模型额度。

```powershell
Set-Location 'D:/XiangMuLuoDi/Development/ICT/track2/auto-research'
.venv/Scripts/python.exe scripts/run_research_project.py prepare-source --method data.tabular-quality-audit --input runs/my-tabular-input --output runs/my-tabular-source.json
.venv/Scripts/python.exe scripts/run_research_project.py create --method data.tabular-quality-audit --source runs/my-tabular-source.json --workspace runs/my-tabular-project --goal '核对声明字段的缺失、重复和分组范围' --budget-ref '填写原任务预算归属' --max-tool-calls 1
.venv/Scripts/python.exe scripts/run_research_project.py selection-context --workspace runs/my-tabular-project
# 按实际context填写UTF-8提案，只选宿主候选id或wait；不要提交method/parameters。
.venv/Scripts/python.exe scripts/run_research_project.py advance-selection --workspace runs/my-tabular-project --request-id tabular-check-1 --proposal runs/my-tabular-proposal.json
.venv/Scripts/python.exe scripts/run_research_project.py status --workspace runs/my-tabular-project
.venv/Scripts/python.exe scripts/export_project_report.py --workspace runs/my-tabular-project --output runs/my-tabular-report
```

提案模板、need及乐观版本绑定见[受限选择提案](project-selection.md)。本方法不接受`--dimension`；列角色已在捕获的spec里固定。capture/create只校验并封存输入，不算研究工具执行；主方法执行才保存`tabular_quality_audit`观察和`tool_result.result.profile/scope`，并消耗既有本地工具额度。重开使用原项目、原request ID及原参数；unknown不重发，原父选择不因新状态改选。

## 统计口径与报告

| 保存字段 | 有限含义 |
|---|---|
| `rows/columns` | 不含表头的数据逻辑记录数与列数，不是独立样本量 |
| `exact_duplicate_rows` | 解析后整行字符串元组的额外重复数N−unique，不是原CSV物理字节相同的证明 |
| `key_columns` | 声明键完整/不完整记录、重复组、额外重复行、冲突组；同一完整键对应至少两种不同完整字符串行即为冲突，不限数值列 |
| `group_columns` | 声明分组数、单记录/重复组、重复组内记录、组大小与不完整字段记录；没有声明时统计为null，不补0，不证明独立 |
| `numeric_columns` | 每列`counts`含finite、zero、empty、declared_missing、invalid_numeric、nonfinite及有限值min/max。zero是finite子集；空串与其他声明缺失互斥，token按原字符串精确匹配 |
| `flags/mechanical_status` | 至多64条机械标记；`needs_data_review`或`no_flags_in_selected_checks`只描述所选核对，不是训练/科学资格批准 |
| `examples` | 总计至多5个代表样例，优先保存完整重复的后记录/首次记录坐标；其余数值样例保留column/token及截短标记。重复样例不抄整行，也没有column/token字段，不代表全部问题清单 |

样例`logical_record`从1起、不含表头；`physical_line_end`是CSV解析器结束物理行号、包含表头及带引号换行，不能把两者混为同一个行号。原字符串和来源字节不因数值转换而被替换；group重复本身不自动产生错误标记。

报告使用独立`kind=tabular`和“表格质量与分组核对报告”标题，显示实计数、每个数值列及键/分组范围；完整profile、声明scope和样例在JSON中。`source_manifest`区分嵌入spec与被核对CSV的实际SHA/字节，输入包保留两份原件。宿主导出的CSV必须注明转换及上游身份，不能冒充原作者外部CSV。选择历史和来源取证仍走原链路。

零不自动作为缺失，Count=0不自动排除或解释为有效终点；重复group不自动作为错误，也不视为新的独立样本。具体目标含义、单位、训练资格或领域结论仍未核验。模型预算0、原5元现金上限、未知费用与平台暂停不变；基于既有钢材和hiMSC数据的转换核对不构成新增独立科学任务，用户价值仍待评价。

## A17 同项目接续分组画像

旧项目先按[项目升级说明](project-slice.md#在同一项目接回来源)显式登记兼容代码。下例仅在本地上限仍为1时显式扩至2，再取得新的选择上下文；这会保留所有既有dispatch和用量，不增加来源、模型或现金额度：

新观察`grouped_quality_profile`保留summary、predecessor、examples和scope；完整分组仅在`tool_result.result.groups`，与原`tabular_quality_audit`按行动分列。每字段保存全部记录/完整组/不完整组的6类计数，完整组集中统计另含事件总数、受影响组数、单组最多事件数、最大份额及最多5个top_groups。份额分母是完整组内该类事件总数，零事件份额为null；不完整组事件单列，不能混入分母。

Markdown/UI摘要最多8个数值列，PDF最多6列，代表坐标最多5例；完整JSON保留全部groups、first_coordinate和numeric_counts。组ID是原分组字符串数组的规范哈希，不展开原分组值；代表逻辑记录/物理结束行可回到原CSV定位。零仍是finite子集，集中情况只作描述，不证明原因、独立性、目标/单位或训练资格。标题继续为表格报告，原spec声明及hiMSC红强度资格未确认的边界不变。
