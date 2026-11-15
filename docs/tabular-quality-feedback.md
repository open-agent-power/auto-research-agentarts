# 事前登记表格质量条件与只读反馈

本文描述 Python `ResearchProject` 的显式表格质量登记和只读反馈接口。它对已保存的机械质量结果作有限条件判断；登记或读取不会选择下一方法、派发工具、修订计划、调用模型或证明科学有效。质量结果的自动分支策略、Controller 接线、Workbench/HTTP 和模型采用不属于本接口。

## 登记与读取

项目的主方法须为 `data.tabular-quality-audit`，事前已保存至少一版研究计划，source 和代码身份可核，且质量行动尚未尝试。先获取当前 `ProjectController.selection_context()`，从无 blocker 的当前候选中取得唯一表格质量候选 ID；其参数必须为空、评价为 `tabular-quality-v1`。例如，以下代码只登记和读取，不执行质量行动：

```python
from autoresearch.project_controller import ProjectController
from autoresearch.research_project import ResearchProject

project = ResearchProject(existing_project_workspace)
controller = ProjectController(project.root)
context = controller.selection_context()
quality = next(c for c in context["candidates"]
               if c["method_id"] == "data.tabular-quality-audit")
conditions = {
    "schema_version": "tabular-quality-conditions-v1",
    "conditions": [
        {"field": "rows", "operator": "gte", "value": 3},
        {"field": "numeric.finite", "column": "temp",
         "operator": "eq", "value": {"ref": "rows"}},
        {"field": "flags", "operator": "empty"},
    ],
}
registration = project.register_tabular_quality_conditions(
    request_id="quality-conditions-1",
    expected_state_version=context["state_version"],
    controller_request_id="quality-action-1",
    candidate_id=quality["id"],
    conditions=conditions,
)
feedback = project.read_tabular_quality_feedback(request_id="quality-conditions-1")
```

示例中的 `temp` 必须已在该项目 source 的 `numeric_columns` 声明；阈值仅为接口示例，不是通用科研质量标准。登记会改变项目状态，因此之后若要按原有 Controller 接口执行质量行动，必须重新获取封存 context、使用实际候选和精确当前 `expected_state_version`。reader 只接受登记目标所对应的 `controller.advance_selection`、`need="next_check"` 及其原 proposal/context，不能把其他执行路径的结果冒认为该登记的结果。该示例不创建或执行行动。

登记 request ID、未来 Controller request ID 和候选 ID 都须为 1–80 位 ASCII 字母、数字或 `_.:-`；登记 ID 与未来 Controller ID 必须不同。未来 ID 是**前置引用，不是预留或强制执行承诺**：若被其他命令占用、选了不同候选或原行动不完整，反馈不能把该行动当成目标结果。登记时检查已有的动作、项目请求、相关未来 ID 和未决执行；一个项目最多 16 条质量登记。保存原 registration 的完整 `request` 和返回的 `registration_sha256`：以同一 ID 和完全相同原 body 重放登记返回原记录；更换 body 会报 `IDEMPOTENCY_CONFLICT`。该重放仍要求原 source、Project 和 Controller 代码身份一致，不是恢复或重发质量行动。

## 条件格式与三态

`conditions` 顶层精确为 `schema_version` 和包含 1–32 项的 `conditions` 列表；所有项按 AND 判断，不接受任意路径、表达式或重复条件。

- 计数字段：`rows`、`columns`、`exact_duplicate_rows`；`key.incomplete_rows`、`key.duplicate_rows`、`key.conflict_groups`；`group.incomplete_group_rows`、`group.group_count`、`group.min_group_size`；以及 `numeric.finite`、`numeric.empty`、`numeric.declared_missing`、`numeric.invalid_numeric`、`numeric.nonfinite`。数值列条件必须多带一个已声明的 `column`。
- 计数项使用精确键 `field`、`operator`、`value`，数值列项另外要求 `column`。操作符为 `eq`、`gt`、`gte`、`lt`、`lte`；字面阈值须为 0–50000 的整数，布尔值和浮点数不当作整数。`{"ref":"rows"}` 仅允许用于 `exact_duplicate_rows`、`key.incomplete_rows`、`key.duplicate_rows`、`group.incomplete_group_rows` 和上述 `numeric.*` 计数。
- flags 项只可为 `{"field":"flags","operator":"empty"}` 或 `{"field":"flags","operator":"nonempty"}`。flags 是最多 64 项的去重、有界列表，不是完整异常数量。

key 和 group 条件要求相应完整计数字段存在且彼此一致；numeric 条件要求该列的完整计数分区一致，且 zero 是 finite 的子集。所需依赖缺失或不一致时，该条件为 unknown。

返回 `tabular-quality-feedback-v1`，包含登记 request ID、registration SHA、目标 Controller request ID、`outcome`、`unknown_reason`、`evaluation`、`action_id`、`result_sha256` 和 `scientific_validation: false`。已核验且所有条件成立为 `condition_met`；已核验、所有必需值有效但至少一项不成立为 `condition_not_met`。只要有必需值未知、格式错误、内部计数不一致或原行动/身份不能核验，整体为 `unknown`，即使其他条件已知不成立。合法零是已知值，不填成缺失。

有质量值但无法完成条件判断时，`evaluation` 可保留每项的已知值和未知原因，整体 `action_id` 和 `result_sha256` 仍为 null；若原行动/绑定无法核实，`evaluation` 通常也是 null。缺失或损坏的登记集合/记录由接口拒绝，而不是伪装成合法的 unknown 结果；缺少指定登记 ID 会报 `INVALID_REQUEST`。调用方应检查实际错误代码和返回值，不能把 unknown 当成不通过或通过。

## 原件绑定与限制

reader 检查保存的登记请求和散列、项目及 run、源 packet/snapshot/scope、当前原计划版本和散列、Project/Controller/reader/条件代码身份；核验目标原 Controller parent 的请求、封存 context、所选候选和时序，以及普通 child 的 SQLite 请求指纹、结果封套、观察和 source 绑定。读取前后检查项目快照，并重新检查原 source、工件和 child 指纹；读取不恢复或重跑行动。登记本身是项目内可回查的持久记录和一致性检查，不是对可以同时重写整个本地账本者的密码学认证。

当前计划如果在登记后改变，即使自然语言提及原观察，reader 也返回 `plan_binding_changed` 的 unknown。`record_feedback` 是未验证的操作者陈述，不能代替原工件；现阶段没有质量后先保存 plan v2 再由此策略选方法的结构化计划引用。若目标 ID 未开始，原因可为 `controller_not_started`；被其他命令占用、源或代码漂移、原行动未完成以及并发变化也不能产生已知通过结果。不要换 ID、重置预算或升级原项目来掩盖 unknown。

profile 和空 flags 不核实上游来源或许可、字段含义和单位、采样独立性、实际组编码、因果关系或领域资格；值有效只表明受检机械条件可计算。`scientific_validation: false` 始终保持。新模块纳入项目代码身份：旧 Project 和未决请求继续使用其原 source pin，不自动迁移或扩额。无需重新运行历史行动来读取结果，但读取会发生本地 source、SQLite 和工件 I/O。

登记与只读反馈本身不使用本地研究工具、模型、fit 或 native evidence-read 额度；它们不增加任何授权额度。后续实际行动仍须单独符合原候选、预算、身份和恢复门禁。现有 Controller 非终态同 ID 恢复可能继续执行原子行动；本 reader 不提供该恢复，也不保证直接 Controller/Project 调用受登记条件约束。
