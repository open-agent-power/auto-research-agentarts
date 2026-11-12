# 跨项目的方法案例快照

项目可以显式引用另一项目的历史方法案例，把当时的观察、适用条件和不利结果带入后续判断。它复用既有条件记忆存储和方法卡，目标项目保存独立版本；控制器只关联当前已有方法与候选，原执行资格和预算继续决定能否行动。

首版来源适配器支持已完成的固定Ridge随机／分组OOF。源项目原工件的行动、结果、输入与代码身份先核对，再复算完整OOF MAE、训练折均值参考、负预测数、观察／预测范围及排除行。完整原工件随案例封套保存，进入建议context的是带来源与限制的有界摘要。

## 来源记忆与导出

`ProjectExperienceMemory`复用`ResearchMemory`的SQLite条目、来源版本、active／retired历史及重导入不复活规则。旧C01／P02的精确条件召回保持；不同数据、代码或协议不能通过相似匹配取得原数值观察。

新条目的scope明确表示“保存OOF算术复核”：`source_manifest_sha256`绑定原输入快照，`inputs_sha256`绑定作为复核输入的原结果工件，`analysis_code_sha256`绑定本复核器真实源码，`protocol=project-saved-oof-arithmetic-v1`。原估计器生产代码与捕获时项目兼容代码分别保留，后续兼容登记不冒充旧行动执行身份。

在原项目已有完成行动后执行，不会重新拟合或继续研究：

```powershell
.venv/Scripts/python.exe scripts/project_experience.py import-project --memory runs/method-cases --workspace <原项目目录> --action-id <已完成Ridge行动ID>
```

取返回的完整scope与entry ID，另准备既有`research-method-card-v1`说明和`{"limitations":["实际适用限制"]}`文件，再导出：

```powershell
.venv/Scripts/python.exe scripts/project_experience.py export --memory runs/method-cases --scope scope.json --entry-id <ENTRY_ID> --case-id <CASE_ID> --version 1 --method-card method-card.json --limitations limitations.json --output case.json
```

### 显式保存父版对照

固定Ridge原输入的完整行边界与训练入口统一为2,048行；不会为导出截取或抽样。需要比较时，在导入来源记忆时明确指定同一项目的已完成父行动：

```powershell
.venv/Scripts/python.exe scripts/project_experience.py import-project --memory runs/method-cases --workspace <原项目目录> --action-id <子行动ID> --parent-action-id <父行动ID>
```

配对协议为`project-saved-oof-parent-comparison-v1`，scope的`inputs_sha256`同时绑定两份原结果；单行动仍使用原算术协议。原生捕获核对两侧行动、工件与历史设计绑定，资源必须显式声明父子版本；原始输入、固定多项式基或固定log1p映射均沿实际协议保留。父子生产代码可以不同，各自身份分别保存。不会搜索较好的父版，也不会在不可比时降级成单结果。

两份完整工件随封套保存。离线读取分别复核全行覆盖、排除、训练／评价划分、训练均值参考及OOF算术，再严格匹配完整行、原坐标、目标、组、折、参考和其余协议。摘要保留明确父版与子版的MAE及差值、相对父版变化、行与组的改善／恶化／持平数，以及两侧负预测、观察／预测范围和低于／高于本批观测范围的计数。组按组内MAE比较，不把行加权结果当组等权结果。

这些紧凑事实进入后续案例context、知识页和成果报告，逐行OOF仍在可下载的完整封套。相对训练均值参考的改善与相对明确父版的改善分别表示；误差降低不覆盖新增负预测或局部恶化。单结果旧快照按其原封存合同核对，导出封套上限仍为4MiB。

可复用的[Concrete方法卡](../examples/research-method-cards/concrete-log-age-tradeoff.json)说明如何同时保留父版收益和局部失败。卡片正文由整理者提供；其文字不会取得数值复核或科学审阅资格。

方法卡复用问题、原理、要求、不适用项、未知项、反馈分支和来源引用。其domain／contract及方法／evaluation必须对应原案例。卡片解释由整理者提供，不转化为执行条件语言。卡片修订可以形成新的案例封套版本，原数值观察仍保持不可变。

`project-experience-bundle-v1`包含原记忆条目、方法卡、限制、case ID／version、`source_inclusion_status=active_at_export`与`scientific_validation=false`，上限4MiB。目标端离线读取时再次核对条目、原工件和算术，不能只凭上传者给出的摘要取得数值。

## 在目标项目中使用

进入完整工作台的“知识空间”，在“其他项目的方法案例”选择封套JSON，填写本次参考理由，再明确导入。文件准备不会自动提交；导入保存原字节及不可变版本，并使项目state加1。当前计划、工具行动、来源选区、FTS、模型请求和累计预算保持。

案例说明及原数值在知识页阅读，完整方法卡、协议、来源和资格历史可以展开及下载。原数值的目标与单位同时保留。例如Yacht的几何签名、Froude三次基和无量纲阻力不能复制为Auto MPG的特征效果或评价结论。

目标最新active案例进入sealed选择context的可选`experience`，标为`analogy_not_current_evidence`。方法卡关联仅使用当前domain／contract与确切method／evaluation，显示当前相关候选或缺口；不创建候选、不修改参数或配方排序。最多4个active案例；撤回的历史仍保存，但不占活动名额。

选择、计划与配方提示说明这种历史案例的用途：若建议参考某案例，应说明case ID、原项目及当前差异。案例不进入本项目的`evidence`，源行动也不能作为当前`evidence_citation_ids`或`feedback_action_ids`。空候选、缺来源、未知执行及用尽预算继续阻断相应行动。

## 撤回、版本与恢复

源记忆撤回阻止新的active导出；已经导出的文件是当时的快照。目标项目在知识页明确“从后续建议撤回”，才会把该本地案例从后续context移除；恢复也须明确填写理由。每次改变保留原版本和请求。最高版本撤回时不会自动退回更老案例。

同case／version重导入不会恢复已撤回资格。原导入ID在撤回后重放仍返回原回执，不改变当前资格。导入和资格变更使未提交的旧客户端context过期；已收口Host及其原回答继续保留制定时的封存内容。

提交结果不明时，先只读刷新，再用“核对原案例请求”沿原ID恢复。manager保存首次完整body，恢复不使用当前文件草稿，也不创建替代请求。core已保存而manager回执未收口时，原ID只补齐管理回执；不会再追加一次案例版本。已知重复、旧版本或活动名额不足在接受前拒绝，不遗留一条未决请求阻断后续操作。

## 接口与成果

| 入口 | 请求与结果 |
|---|---|
| `GET /api/local-workbench/experiences` | `project-experience-view-v1`，最新案例含active／retired及完整资格history |
| `POST /api/local-workbench/experience-import` | `request_id/project_id/expected_state_version/bundle_base64/reason` |
| `POST /api/local-workbench/experience-status` | `request_id/project_id/expected_state_version/case_id/status/reason` |
| `POST /api/local-workbench/experience-resume` | `request_id/project_id`，只恢复原已接受案例命令 |

写入沿原本地操作、同源／CSRF、活动项目、版本、代码及未决请求门禁。模型CLI关闭仍可导入方法知识；它不增加任何研究执行授权，也不消耗或补回研究工具、来源和fit额度。

当前报告单列历史方法案例与目标本地资格，源指标明确归属原项目。JSON保存案例摘要和资格历史；输入包捕获完整封套及原始工件，撤回后也不删除这些复现材料。原报告保留原快照，新导出才对应新案例版本。

## Limitations

这是显式快照复用，中央撤回不会自动传播到离线副本；旧记录不会被新状态重写。算术核对证明保存数值的计算一致，不验证来源作者身份、样本独立性、物理含义、因果或跨任务迁移。方法相同也不证明案例适用于新数据，卡片适用条件仍含整理者判断。

建议context继续使用原总大小上限。加入案例可能使某类建议超过上限；需要明确撤回部分案例或修订说明后再准备，不静默截断数值、扩额或替换原Host内容。

首版适配器支持明确的保存Ridge OOF，不覆盖任意算法或所有旧领域记忆。[同状态离线计划比较](research/experience-judgment-pair.md)已在原回答中出现有出处的案例参考，独立审阅结果为无实质差异；没有当前项目采用、两位真实使用者受益或持续科研质量提升的证据。配方内容、排序与RSI采用／回退仍沿原模块负责。
