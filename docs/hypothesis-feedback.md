# 事前预测、结果反馈与下一行动

本接口把固定检索比较的事前预期接到已有 ResearchProject、Controller、Host 与 Workbench。它判定预登记的 validation 数值条件，并可按事先冻结的分支选择原结果审计或等待；不自动批准科学假设、采用计划或增加预算。

这是旧盘缺失后的新源码续作规格。S041 历史 v2 原文只有路径和哈希，未恢复；本实现不宣称逐字实现该原件。

## 登记与读取

先保存研究计划，再从当前 selection context 取得 citation、relevance 或独立 staged development 的 primary candidate。调用 `ResearchProject.register_hypothesis(request_id=..., expected_state_version=..., hypothesis=...)`，或向启用本地操作的工作台发送：

```json
{
  "request_id": "prediction-1",
  "project_id": "实际项目ID",
  "expected_state_version": 2,
  "hypothesis": {
    "candidate_id": "当前候选ID",
    "controller_request_id": "事先指定的原Controller请求ID",
    "metric": "recall@20",
    "operator": "gt",
    "threshold": 0,
    "branches": {
      "condition_met": {"kind": "wait"},
      "condition_not_met": {"kind": "method", "method_id": "research.relevance-saved-error-audit"}
    }
  }
}
```

POST 路径是 `/api/local-workbench/hypothesis`；沿原本地 Host、Origin、CSRF、活动项目及未决请求门禁。示例 ID、版本和方法须换成实际项目值；审计方法以当前 registry 为准。`branches` 可省略；省略时只提供预测反馈，不能调用分支执行。

指标限现有 `recall@5/10/20`、`mrr@10`、`ndcg@10`，固定为 **validation 的 candidate-minus-baseline 配对均值差**；比较符为 `gt/gte/lt/lte/eq`，阈值为 [-1,1] 有限数值。最多登记16条，不支持任意表达式、test 指标或事后改条件。登记捕获候选内容、来源、范围、协议、计划、代码及原状态身份，先持久保存，再允许目标行动创建。保存使状态版本增加1，后续行动须重新取得 context；不能继续使用登记前的 context SHA。

### 显式双指标联合条件（S059）

以后新建的 staged development 项目，可以在同一事前登记中用 `conditions` 替代上例三个标量字段。它恰好包含两项**不同**的现有 validation 指标，含义为两项同时满足，例如覆盖率改善且排名质量不退化：

```json
{
  "candidate_id": "当前staged主方法候选ID",
  "controller_request_id": "尚未执行的原Controller请求ID",
  "conditions": [
    {"metric": "recall@20", "operator": "gt", "threshold": 0},
    {"metric": "mrr@10", "operator": "gte", "threshold": 0}
  ],
  "branches": {
    "condition_met": {"kind": "method", "method_id": "research.relevance-validation-saved-audit"},
    "condition_not_met": {"kind": "wait"}
  }
}
```

这是原 `hypothesis` 字段内容，外层工作台请求字段和路径不变。不得混用原 `metric/operator/threshold` 标量字段，不接受同一指标两次、第三项、任意布尔表达式、test/final 指标、布尔或非有限阈值；旧 citation/relevance 家族不接受新模式。它不为同一个未来 Controller ID 新建两条登记，而是一次冻结两项及其顺序，仍要求在原 primary 之前登记。

新记录使用 `hypothesis-registration-v2`，规范条件为 `condition: {"all": [两个完整条件]}`。反馈使用 `hypothesis-feedback-context-v2`，`value` 是与条件同序的两个保存配对差。一份已完整核验的原 primary/source/SQLite/结果 summary 提供两值，不重复排名或评分。只有两值都有效时才判定：`[0.01, 0]` 满足示例，`[0.01, -0.01]` 不满足，`[0, 0]` 因第一项不满足而失败。任一结果缺失、损坏、未完成、非有限或布尔冒充数值，则整体为 `unknown`，`value/action_id/result_sha256` 均为空，保留原因并等待，不能用部分已知值继续。

纯标量登记仍生成原 v1 记录、反馈和提示字节；同一 staged 项目混有标量与联合登记时，整体 context 为 v2，每条 item 保持各自的条件和值形状。v2 必须至少有一条联合条件；不能混检索家族。联合条件顺序、数值表示与原登记进行 canonical 精确绑定，重新封存 context 不允许将原 `0` 改成 `0.0` 来替换原条件。原 ID/全部原参数重放及异内容冲突规则保持。

联合结果沿原 `advance_feedback` 和 S052 显式条件续作消费，只有配置为相应原 saved-audit 的分支才派发；示例的失败分支等待。它不强制所有低层接口等待，不自动采用计划或科学结论。**S052 后续冻结方法仍按原 Recall@20 规则，未变成多指标优化器**；研究者须在以后研究前确定指标、阈值及分支，不能依据 S054 已曝光结果补登记、改变原协议或重开原预算。此功能的合成分支/HTTP验证不证明新科研收益，真实模型反馈循环仍未由本增量执行。

同登记 ID 和全部原参数重放返回原记录，异内容冲突。未来 Controller ID 是事前引用，**不是全局预留**：用户可以改变路线；其他命令占用该 ID、错误候选、不同计划或无原普通 child 时不会被认作有效反馈。

新 selection context 的可选 `hypothesis_feedback` 使用 `hypothesis-feedback-context-v1`，有记录时才出现。它只读核对原 parent、普通 child、数据库请求指纹、工件字节/结果 SHA 和保存指标算术，不派发、不恢复、不重新排名或按 qrel 评分。有效的0是已知值：`0 > 0` 为 `condition_not_met`，`0 >= 0` 为 `condition_met`。未完成、来源/绑定不符、工件缺失或损坏返回 `unknown` 及原因；未知不填0。登记本身损坏则拒绝读取。

## 事前分支与同ID执行

两个可选分支只能等待或指定**该检索家族已有的 saved-audit 方法**；未知分支固定等待，不能配置。实际审计参数只能由已核验反馈中的原 action ID 和 result SHA 构成。纯函数 `feedback_policy.select_from_feedback` 只生成已有 selection proposal；原 Controller 的新鲜 context 必须恰有一个方法、参数和评价身份全匹配的候选，且无 blocker，否则等待。

调用 `ProjectController.advance_feedback(request_id=..., registration_request_id=..., expected_state_version=...)`，或 POST `/api/local-workbench/advance-feedback`，body 为上述三个字段加 `project_id`。它通过原 `advance_selection` 执行，消耗原工具额度；不是新执行器或预算账本。原记录保存登记 ID/SHA、所选分支的理由、封存 context 和原 child。重启后使用全部原参数和原请求 ID；重放使用该请求原 context，不用后来结果重新选动作。未知/失败原请求不得换 ID 重派。

Workbench 的活动项目 GET 和报告 JSON 保存反馈；报告输入同时保存登记原件。尚未增加新的可视化表单或自动科研解释器。

## delegated批次的行动ID

`LocalWorkbench.preview_continuation(body)` / POST `/api/local-workbench/continuation-preview` 对与 continue 相同的 body 做只读 ID 计算。`plan_mode=reuse`、`execution_mode=delegated` 时，返回批次、各 Host/Controller step ID 及可选后置计划 ID；它不创建请求、grant 或授权，也不检查未来状态是否可执行。返回 preparation state 未检查，不能据此断言请求尚未创建。

登记前可预览一个预计登记后版本（当前版本+1）的 body，以第1步原 Controller ID 登记，再以完全相同 body 继续。原候选内容仍须匹配。`plan_mode=suggest` 的计划采用会改变计划/状态，预览标阶段未知；应先完成并明确采用计划，再登记预测及预览下一行动，不把旧预测移到新计划上。

`continue_research` 新增 `execution_mode=delegated`，需明确 `post_action_plan` 布尔值，沿已有 Host grant 调用持久 v2 batch。等待外部回答时保存原批次；POST `/api/local-workbench/delegated-response` 接受 `request_id`（continuation ID）、`project_id`、该批次的 `host_request_id`、`response_base64` 原字节，只导入原回答，后续同 body 的 continue 才消费并推进。行动后的计划保留 `awaiting_adoption`，经现有明确 adopt/reject 门处理。没有新增原生模型传输。

## 验证与科学边界

工程验收使用新合成输入、真实本地适配器/SQLite/文件/HTTP 和构造的 delegated 回复；它们不替代旧研究，不是实际模型推理或科研收益。已完成的旧 Concrete、原 pilot、调度阈值实验及其预算不恢复、不重置。

旧 citation/relevance 适配器会计算并保存 dev/validation/test，本投影仅取 validation，**整条旧流程不具备盲测保证**。独立 staged 路径见下节。长期自适应收益、跨课题因果收益和受控 Linux 模型运行时仍待验证。改变源码会改变 core/Controller/批次身份，旧 pending/unknown 仍需原 source pin；没有跨版本自动迁移。

## 独立 staged development 的反馈

S051 将 `research.relevance-validation-pair` 接入相同登记与 `advance_feedback`，可选分支只允许等待或本家族 `research.relevance-validation-saved-audit`。原字段、validation 指标、原请求/预算语义保持；不能通过分支选择 final 或其他家族的方法。

`staged_feedback_reader.read_validation_delta` 复用已有分阶段证据校验器，核对原公开 dev/validation source、action/SQLite 请求指纹、工件封套、完整双臂覆盖、原 query/document 坐标、qrel 资产 SHA 和 grades，再核保存指标的配对算术。它不读取私有 final、不构建索引或重新排名评分；不把 staged 强行套入旧 train/test 阅读器。无完整原证据时反馈 unknown 并等待，已知零值仍按原比较符判定。

staged 的 context/prompt 使用独立说明：来源仅含 dev/validation，任何 final 需单独登记；读取反馈不建立此前未接触、盲测或科学有效性。旧家族说明和消息仍保留原范围，混用 family/说明会被拒绝。合成输入的条件分支及重放验证只证明工程接线；旧 SQuAD 验证负差的只读读取不能补造事前假设或证明新的研究收益。

`continue_staged` 原五字段 v1 仍是另一次明确授权的固定审计→冻结→final→报告流程，不自动遵循 `advance_feedback` 的等待分支。S052 的显式六字段条件模式可绑定原登记并在 wait/unknown 停止，见[条件续作](staged-evaluation-continuation.md#显式条件模式s052)；两种授权不可混称。

[S043](execution/SPRINT-043.md)补齐reader源身份与非终态恢复无写门禁；源码不符不会将原未完成parent永久拒绝或把child改成unknown，回到原pin仍可核对/恢复。可运行的[独立演示](../examples/hypothesis-feedback/README.md)展示登记、分进程执行和终态重放，使用独立工程输入和预算。
