# 事前登记表格质量条件与只读反馈

本文描述 Python `ResearchProject` 的显式表格质量登记、只读反馈，以及单独调用的 `ProjectController` 条件策略和本地 Workbench 接口。登记或读取不会选择下一方法或派发工具；Controller 策略则可能立即执行一次符合条件的数值关联。它们都不会修订计划、调用模型或证明科学有效，也不证明模型采用。

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

当前计划如果在登记后改变，即使自然语言提及原观察或计划包含下述结构化引用，reader 也返回 `plan_binding_changed` 的 unknown。`record_feedback` 是未验证的操作者陈述，不能代替原工件。若目标 ID 未开始，原因可为 `controller_not_started`；被其他命令占用、源或代码漂移、原行动未完成以及并发变化也不能产生已知通过结果。不要换 ID、重置预算或升级原项目来掩盖 unknown。

## Python 显式引用已保存质量反馈

在原质量 Controller parent 已完成、原登记计划仍为当前计划、质量反馈为已知 `condition_met` 或 `condition_not_met` 时，可调用 `ResearchProject.prepare_tabular_quality_plan_ref(registration_request_id=...)` 只读派生引用，再通过 `ResearchProject.save_plan` 保存直接后继计划：

```python
ref = project.prepare_tabular_quality_plan_ref(registration_request_id="quality-conditions-1")
state = project.status()
plan = {
    "question": "人工填写的问题",
    "basis": "人工填写的计划依据",
    "steps": "人工填写的后续步骤",
    "expected_feedback": "人工填写的预期反馈",
    "quality_feedback_ref": ref,
}
revision = project.save_plan(
    request_id="quality-plan-2",
    expected_state_version=state["state_version"],
    plan=plan,
    reason="人工填写修订理由",
)
```

`quality_feedback_ref` 使用精确的 `tabular-quality-plan-reference-v1`：登记 ID/SHA、原计划版本/SHA、质量 parent ID/请求 SHA、child request ID、action ID/result SHA、反馈 SHA 和 source snapshot SHA。反馈 SHA 对完整 reader 反馈做 canonical 指纹，不是另造的持久 feedback ID。`quality_feedback_ref` 可与已有 `experience_case_refs` 同时出现，各自按原合同校验；普通四字段计划无需新增字段。操作者填写的计划文字及适用性仍是其陈述，不因引用存在而获得科学认证。

准备引用不写账本或派发；原行动未完成、反馈 unknown 或登记计划已不是当前计划时不能派生。保存时在原 Project writer 锁内重核登记、原计划、质量 parent/child、SQLite 指纹、原结果、source 与代码，并要求质量行动完成在计划依据状态之前或同一状态；新计划必须是登记原计划的直接后继。保存消耗一次状态修订，不增加研究工具、模型、fit 或 native evidence-read 用量。同 ID、相同原参数重放计划会重新核对原引用与原件后返回原修订；body 不同报冲突，原 source、代码或工件不可核时拒绝，不能靠重放重建原件。该一致性检查不是防止同时改写全部本地账本的签名认证。

保存后的 selection context 可以携带该字段，但其 context validator 只校验引用**形状**，不在每次生成 context 时重新认证底层原件；Project 保存与相同 ID 重放时才做上述原件核验，不应把单独读到 context 的引用视为实时认证。当前质量 Controller 策略仍要求当前计划与登记计划相同，保存此后继计划后，原质量 reader 为 `plan_binding_changed`、原策略会等待；此字段尚不会使该策略自动采用后继计划。Workbench 的 `save_plan`/对应 HTTP 在接受 manager 意图前拒绝包含 `quality_feedback_ref` 的计划；本版只支持上述 Project Python 入口，不提供 Workbench 恢复或 UI。

profile 和空 flags 不核实上游来源或许可、字段含义和单位、采样独立性、实际组编码、因果关系或领域资格；值有效只表明受检机械条件可计算。`scientific_validation: false` 始终保持。新模块纳入项目代码身份：旧 Project 和未决请求继续使用其原 source pin，不自动迁移或扩额。无需重新运行历史行动来读取结果，但读取会发生本地 source、SQLite 和工件 I/O。

登记与只读反馈本身不使用本地研究工具、模型、fit 或 native evidence-read 额度；它们不增加任何授权额度。后续实际行动仍须单独符合原候选、预算、身份和恢复门禁。现有 Controller 非终态同 ID 恢复可能继续执行原子行动；本 reader 不提供该恢复，也不保证直接 Controller/Project 调用受登记条件约束。

## 显式调用 Controller 条件策略

在质量行动完成并保存后，调用方可在已获授权的项目和预算范围内显式调用：

```python
state = project.status()
result = controller.advance_tabular_quality_feedback(
    request_id="quality-followup-1",
    registration_request_id="quality-conditions-1",
    expected_state_version=state["state_version"],
)
```

三个参数均为必需项；状态版本须为精确的非负整数，两个 request ID 使用上述标识符规则。此调用可能立即派发工具，调用前须由使用者确保本次行动已有授权；方法不弹出批准提示，也不增加模型、fit 或工具额度。这里的 `request_id` 是本次策略请求 ID，`registration_request_id` 指向原质量登记，两者不替代登记中指向原质量行动的 Controller ID。

该策略在原 Project writer 锁内读取登记及已核验反馈，核对项目、source/scope、代码和登记时原计划，再基于当前封存 context 固定 proposal 与 parent。只有反馈为 `condition_met`，且无 blocker、存在唯一 `data.numeric-association` 候选、其评价和参数精确绑定原质量 action ID/result SHA，实际候选成本恰为 1 次本地工具、0 次 native evidence-read、0 次 fit，且原账本有剩余工具额度时，才交给原 Controller/Project 路径执行。质量条件未通过或为 unknown、资格/候选/预算不可用时可保存等待；代码身份漂移、读取失败或请求/状态冲突也可能直接拒绝或停查并保留原错误，不保证所有情况都有等待回执。存在未决 Controller 或行动时可能以 `EXECUTION_UNKNOWN` 停查，不伪造等待或重派。执行数值关联不消耗模型调用；登记、只读反馈和等待不会派发研究工具，但会进行本地文件和账本 I/O。

保留本次策略调用的完整三个参数和原回执。相同 ID、相同 body 的终态重放会在锁内核原登记、封存 context/proposal、相关原工件及身份；核验通过后返回原完成、等待或失败回执，不重新派发，原拒绝则抛出原拒绝。原计划之后若另有修订，历史回执仍按原封存计划核验，但 source、代码或所需原件缺失、绑定不符时会拒绝。改变 body 会报冲突。原 parent 为 `prepared`、`running` 或 `unknown` 时，同 ID 明确报 `EXECUTION_UNKNOWN`，不从此入口恢复或重发 child；其他入口也不能拿原策略 parent 当普通选择请求重放。保留原状态、原预算和原 source pin 并检查原因，不以新 ID 绕过未决状态。等待是该次请求的终态：同 ID 重放原等待，不依据之后的新状态重新选择。

策略是**显式入口**，直接调用其他 `advance_selection` 或 `ResearchProject.step` 不会自动服从该质量条件。当前新策略首次选择要求登记时的计划仍为当前计划；质量后另存 plan v2，即使带有上述结构化引用，也会使原反馈 unknown/策略等待。机械质量通过也不验证来源许可、字段科学含义、因果性或用户是否批准具体研究；调用者必须自行核实这些前提。

## 本地 Workbench 调用与恢复

对当前活动的受管项目，`LocalWorkbench.register_tabular_quality_conditions(body)` 接受恰好六个字段：`request_id`、`project_id`、`expected_state_version`、`controller_request_id`、`candidate_id`、`conditions`，条件与上述 Project 接口相同。成功返回 `local-workbench-command-v1`、`status: "completed"` 和原 `registration`。`LocalWorkbench.advance_tabular_quality_feedback(body)` 接受恰好四个字段：`request_id`、`project_id`、`expected_state_version`、`registration_request_id`，返回原 `project-controller-advance-v1` 回执；该方法可能立即执行已授权的关联行动。

只读反馈使用 `LocalWorkbench.read_tabular_quality_feedback(project_id=..., snapshot_ref=..., registration_request_id=...)`。三个参数均必需；项目须仍为活动项目，`snapshot_ref` 须为当前 64 位小写 SHA-256。该方法在读取前后检查项目快照及活动项目，返回上述有界 feedback，状态变化时拒绝；它不会返回整个 source packet 或启动行动。

本地 HTTP 对应：

| 方法与路径 | 输入 |
|---|---|
| POST `/api/local-workbench/tabular-quality-registration` | 上述六字段 JSON |
| POST `/api/local-workbench/advance-tabular-quality-feedback` | 上述四字段 JSON，可能派发一次工具 |
| GET `/api/local-workbench/tabular-quality-feedback.json` | 恰好各一次 query 参数 `project_id`、`snapshot_ref`、`registration_request_id` |

POST 沿现有活动项目、同源、CSRF、大小和代码身份门；不提供新的页面控件或通用执行权限。受限 `LocalWorkbench.open_readonly` HTTP 宿主不提供该反馈 GET（返回 404），也不能通过其只读 HTTP 服务提交这两个 POST；该限制不应误述为新增了只读报告或旧 pin 迁移接口。

Workbench 在 manager 中保存原完整 body、摘要、随机一次性 nonce 及 Project/run/source/代码和规范化 manager 根路径身份，但不把 body 或 nonce 放在 `pending_requests` 投影中。manager 调用首次创建核心质量登记或策略 parent 时，会在同一 Project SQLite 事务中写入对应的 manager 意图摘要与核心记录摘要作为归属 claim；直接通过 Project/Controller 创建的记录不会自动获得该 manager claim。恢复时 manager 要核对原意图、原件和事务 claim；claim 缺失或不符时停查，不能将相同 ID 或内容的其他调用冒认为自己的结果。manager 根路径变更也会使原身份核验失败，不应默认为可搬迁恢复。

调用方应保留原 ID 和完整 body；恢复时向同一活动项目提交相同 body，不以新版本重造请求。manager 意图已保存而原核心登记尚不存在时返回 `OPERATION_INCOMPLETE`；核心登记及匹配的事务 claim 已保存但 manager 回执丢失时，核原登记及身份后可补原回执，不再登记一次。策略请求若缺原 Controller parent，返回 `OPERATION_INCOMPLETE`；parent 为 `prepared`、`running` 或 `unknown` 时返回 `EXECUTION_UNKNOWN`，均不重派。parent 终态且原记录及事务 claim 核验通过时可补回或重放原回执；原拒绝继续抛原错误，身份/原件不符则拒绝。不同 body 发生 ID 冲突。对经过 `_no_pending_batch` 检查的研究写命令和切换活动项目，未决质量意图按项目阻止绕过；这不是所有操作的全局门，例如重新选择同一活动项目不受该切换门阻断。pending 列表最多显示八项，不代表后续未列出的意图已消失。

这些 claim 和 nonce 用于受信本地协作及原请求一致性检查，不是签名、防止可同时改写本地账本者的认证、OS 隔离或全局强制质量门。错误、网络中断或未知状态不能解释为行动未发生；保留原项目、原请求和预算后检查。实际跨进程恢复、独立验收和研究收益须分别按已保存证据判断。
