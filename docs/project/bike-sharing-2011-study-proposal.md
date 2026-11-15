# Bike Sharing 2011 日度关联：供审阅的研究协议草案

**状态：未授权执行。** 本文件用于审阅；尚未下载本课题数据、读取其目标列、创建 Project 或调用研究工具。原 ZIP、`day.csv`、派生输入、spec 和源码发布身份的实际 SHA 均为 **unknown**，下面的路径和请求 ID 是待批准后固定的提议，不是已存在的记录。现有 G5 检索/调度及 G3 指定表格授权不自动覆盖此新课题；确认来源和协议后，仍需明确批准本研究的 2 次工具、0 模型、0 fit 和 0 新增 evidence-read 范围。原 Project、历史额度及 S050 未授权模型请求均不改变。

## 问题和可否证的观察

在 UCI Bike Sharing 原 `day.csv` 中，以 **2011-01-01 至 2011-12-31 闭区间**内的日记录为固定样本，计算气温字段 `temp` 与当日总租赁数 `cnt` 的 Pearson r：总体一项、`workingday=0` 一项、`workingday=1` 一项。待确认原资料中的编码含义，官方字段说明称 `workingday=1` 为既非周末也非节假日，`0` 为其余日。

事先固定判定：只有总体和两个组均存在、各自有效成对 `n≥3`、`pearson_r` 为有限数且在 [-1,1]，才判断方向；三处均有效且 **均严格大于 0** 时为 `condition_met`，三处均有效且至少一处 `r≤0` 时为 `condition_not_met`。只要任一组缺失、n 不足、常量、结果 null/非有限或身份/输入不一致，**整体优先为 `unknown`**，即使另一处已知非正也不提前判 false。零是已知数值，不是缺失；未知不填零。保留每项的 n、excluded、r 或原不可计算原因。该条件是协议中的人工解释规则，并非产品 `hypothesis_feedback` 已为这个表格任务实现的事前自动登记。

这只描述所选日记录的线性关联：不检验因果、节假日效应、统计显著性、预测性能、自动科研收益或跨城市泛化。季节、长期趋势、天气、节假日及连续日期自相关是竞争解释；每日记录不能自动视为独立样本。任何所见关联都不自动改变方法或准许模型调用。

## 来源、样本与曝光

官方来源为 [UCI Bike Sharing Dataset](https://archive.ics.uci.edu/dataset/275/bike+sharing+dataset)，[字段元数据](https://archive.ics.uci.edu/api/dataset?id=275)，[官方 ZIP](https://archive.ics.uci.edu/static/public/275/bike+sharing+dataset.zip)，作者 Hadi Fanaee-T，数据 DOI `10.24432/C5W894`，来源论文 DOI `10.1007/s13748-013-0040-3`。UCI 页面声明 **CC BY 4.0**，须保留作者、来源、许可链接和修改说明；正式准备时还须核 ZIP 附带的原 README/notice，如有冲突停下核对，不以本草案替代许可或科学资格判断。官方网页列 `day.csv` 为 57,569 字节、ZIP 约 279,992 字节；为网页元数据，实际字节数及 SHA 尚未核验。质量适配器的 CSV 上限为 8 MiB、spec 上限 64 KiB、封存 packet 上限 12 MiB；实际读取和捕获超限即停止，不抽样压缩或换日期以追求可运行。

本题日记录字段：

| 字段 | 固定角色与解释 |
|---|---|
| `dteday` | 原日日期和候选唯一 key；实际唯一性由质量行动核对。 |
| `workingday` | 原编码 `0`/`1` 的分组列，不用分组哈希猜测编码。 |
| `temp` | 上游声明的归一化温度数值，无原始摄氏度单位；不自行反归一化。 |
| `cnt` | 原日总租赁次数，单位为次/日；是描述性关联中的目标，不作预测模型训练。 |

`casual` 和 `registered` 是 `cnt` 的组成，必须从本次输入中排除，不能作为预测字段；也排除其他非上述四列。`hour.csv` 与 `day.csv` 同源、粒度不同，不把 hourly 行当独立确认样本。

允许执行后，来源准备须保留下载的 ZIP 和原成员原字节，并逐一记录 URL、获取时间、原文件大小/SHA、许可、作者、README、转换脚本/版本及输出 SHA。按原 CSV header 精确选择四列；严格解析 `dteday` 为规范 `YYYY-MM-DD`，选闭区间内全部行并按日期升序，保留原字段字符串，UTF-8 CSV、固定逗号和 LF。不得按 `temp`/`cnt` 的值筛选、改值、补值或换时间窗。投影时验证日期恰覆盖 2011 年全部 365 个日历日且每日期一行，`workingday` 实际值集合恰为 `{"0","1"}`，两组各至少 3 行；异常保存失败并停止，不能以 `group_count=2` 代替实际编码核验。派生文件是明确注明修改的投影，不能冒称上游原始 CSV。ZIP/成员/投影/spec/source packet 的 SHA、实际大小和所用已发布代码身份必须先实测固定；当前均为 unknown。

原 `day.csv` 还含 2012 数据，完整 ZIP 下载、哈希、解压或逐行投影可能将包含 2012 目标的原始字节读入本机；项目输入只含 2011，并记录真实读取范围，不称最终目标从未接触或盲测。本协议不分析 2012、不安排跨年确认，也不以未来结果调整本题阈值。公开来源及其结构此前已曝光。

## 预定质量门与结果分支

捕获的 `tabular-quality-spec-v1` 固定 `key_columns=["dteday"]`、`group_columns=["workingday"]`、`numeric_columns=["temp","cnt"]`、`target_column="cnt"`、`target_unit="rentals per day"`、`missing_tokens=[""]` 和逗号分隔；样本单位写明“daily record, independence unverified”，来源和许可为可回查的声明，`provenance.origin_sha256` 只填实际核得的上游原件 SHA。四列 spec/source 通过 `tabular_quality_adapter.capture_source` 后登记，原文件不得覆盖。

质量行动成功后，只有同时满足以下条件，才由操作者选择关联候选：

1. 来源、许可及字段定义已经依据保存的一手资料核实，投影日期、列和编码检查全部通过，且原 source/spec 身份未漂移。
2. 原质量结果 `rows=365`、`columns=4`、`exact_duplicate_rows=0`；`key_columns` 的 `incomplete_rows=0`、`duplicate_rows=0`、`conflict_groups=0`；`group_columns` 的 `incomplete_group_rows=0`、`group_count=2`、`min_group_size≥3`。
3. 两个数值列各自 `finite=365`，且 `empty`、`declared_missing`、`invalid_numeric`、`nonfinite` 均为 0；`flags=[]`。`zero` 是 finite 的子集，允许存在，不作自动删除。

质量未完成、未决、来源/定义未确认、候选缺失、预算不足、任一质量条件不满足或无法读取原结果，均保留具体原因并等待，不执行关联、不换输入或阈值。质量结果没有组内值范围或各组成对 n，也不输出可直接解释为原编码的组值：关联后再依据所保存的 `first_coordinate` 回到已捕获投影，严格核对两个组分别是 `0` 和 `1`，逐组检查 n/excluded/r/reason。全局非恒定或 `group_count=2` 不能证明组内 r 可计算。

`tabular_quality_adapter.next_decision` 的现有默认反馈为等待来源证据；native 候选资格本身**不会**按上述质量门自动分支。操作者须在原质量行动完成后先保存基于该行动 ID 的原观察、依据及下一步（`record_feedback`，不构成已验证科学解释），再保存有明确差异的计划 v2：质量门通过则写出具体原计数和“选择现有数值关联候选”；不通过则写出具体事实/unknown 和“等待核对”，保持未使用额度。仅固定执行两工具或提交一条未引用观察的文字，不算观察导致的计划修订。

关联完成后保存原结果与观察，并在同一 Project 另存计划 v3 或明确 waiting：三处均有效且均正则保留“本样本方向一致”的有限描述；三处均有效且至少一处非正则记录反例和应检查的季节/时间解释；任一无效优先记为 unknown，记录不可计算原因并等待。无一分支授权新增来源读取、再分析、拟合、模型或跨年研究。该修订由操作者作出，不能声称模型自主采纳、科研提升或对照收益。

## 原生接口、额度和恢复（拟固定）

待授权并发布代码后，先确定唯一全局研究 claim、原 source pin 和唯一工作区；claim 仅为合作式排重，当前尚未创建，也不承诺 OS 级锁。若 claim、Project 或任何原持久文件已存在或部分准备状态无法判定，沿原身份只读核对并停止，不以新目录/新 ID 重开。提议请求 ID 预先固定为 `bike-2011-evidence-zero`、`bike-2011-plan-v1`、`bike-2011-quality`、`bike-2011-quality-feedback`、`bike-2011-plan-v2`、`bike-2011-association`、`bike-2011-association-feedback`、`bike-2011-plan-v3`；manager import/select ID 也在最终执行前固定。实际 Project UUID/run UUID 由原创建返回，当前 unknown。

1. 以 `ResearchProject.create(source=封存packet, goal=上述问题, budget_ref=新批准的唯一账本, max_tool_calls=2, method_id="data.tabular-quality-audit")` 创建一次；确认 source/spec、Project/run ID、producer core、runtime 版本与 `model_requests_allowed=0`。当前实现将每个新 Project 的 `evidence_purpose` 硬编码为 `isolated_adapter_regression_not_new_research`，与本案拟议的真实描述性研究目标不一致；该标记不是领域批准，也不能静默改写。真实执行前须将这项元信息差异作为独立产品缺口明确处理，不能通过本预案假定已解决。项目默认 evidence limit 为 8，必须在任何控制器行动前以 `ResearchProject.limit_evidence_budget(request_id="bike-2011-evidence-zero", expected_limit=8, new_limit=0, expected_state_version=原当前版本, reason=固定说明)` 保存收紧回执；不得误称默认即为 0。两候选均不拟合，禁止任何 Ridge/模型候选；本案 0 model/fit 是已批准范围和所选方法约束，不是新建项目自动锁死所有其他方法的证明。
2. 如需 Workbench，使用现有 `LocalWorkbench.import_project` 和 `select`，注意 import 是同文件系统的原 Project 移动，保存实际迁移路径和原身份；在唯一 manager 中用 `save_plan` 保存四字段计划 v1，写明问题、来源、质量门、关联判定与 unknown/停止规则。计划保存不是额外工具调用。原字段、完整 body、原 expected state version 和返回 revision 必须留存。
3. 用 `ProjectController.selection_context()` 获取封存 context，核无 blocker 且唯一预定 `data.tabular-quality-audit` 候选、`evaluation_ref="tabular-quality-v1"`；候选仅含 `id`、`method_id`、`parameters` 和 `evaluation_ref`，预算成本须在同方法的 `conditions[]` 条目中核对为 1 tool/0 fit/0 evidence，不能从候选虚构成本字段。持久化原 context、完整 proposal（`project-selection-proposal-v1`、实际 `context_sha256`、`provider={"kind":"human","label":"operator"}`、`choice={"kind":"execute","candidate_id":原候选ID}`、有界 rationale、实际可用 citation ID 或空列表）及 expected state version，再用 `advance_selection(request_id="bike-2011-quality", proposal=原proposal, expected_state_version=原版本)`。不得自造候选 ID/参数或绕过 blocker。
4. 严格回查原 controller parent/ordinary child、source 和结果工件、预算，再按上面的质量规则保存引用原行动的反馈和不同的 plan v2。若门通过，从**新**封存 context 选择 `data.numeric-association`、`evaluation_ref="numeric-association-v1"`；候选参数必须恰绑定原质量 action ID/result SHA。先持久化完整原 proposal/context/版本，再以 `advance_selection(request_id="bike-2011-association", ...)` 执行一次；门未通过/unknown 则不创建关联行动。
5. 如关联 completed，核原工件、逐组原编码定位、结果与预算，再保存原行动引用的反馈和 plan v3/等待；读现有 Project 报告只使用实际已完成行动。两项研究工具最多 2/2，model 0、fit 0、native evidence-read 0；来源下载和本地文件读写并非零 I/O，开发时间及费用未测为 unknown。

每次变更按实际 `state_version`、同一 Project/source/code 与原请求 body 绑定，不以猜测版本派发。原父选择已接受时重放原 proposal/ID 和原 context；`unknown`、pending、来源/code 漂移、原 body 缺失或账本不一致时保留原件并停查，不补发、换 ID、重建数据库或扩大预算。实际创建/导入和崩溃恢复能力须在本协议发布前用隔离合成样本验证；本草案本身不声称该新课题已实现专用驱动或完成跨进程恢复。

## 尚待批准/核实

需要独审本协议的字段和质量门、处理上述新 Project 用途元数据差异、核可用发布 commit/运行时、批准一次独立新表格研究和预算、取得原始 ZIP/README、固定全部真实 SHA 与唯一 claim；这些完成前不启动。协议只预先约束可做什么，不保证数据适配、结论可计算、行动成功或任何科研收益。

## S077 后的用途声明更新

[S077](../execution/SPRINT-077.md)已新增仅 Python `ResearchProject.create` 的显式 `operator_declared_descriptive_research`；它解决新项目可准确持久操作者用途的 API 能力，但不是研究授权、领域有效性、预算授权、文件冻结或已执行本案的证明。Workbench/CLI 的直接创建入口仍未扩展。若获批准，必须先确认采用的已发布源码 pin、完成本预案的隔离合成全链及原 ID 恢复验证、原始数据与派生 source 实际 SHA/许可/容量以及唯一 claim，之后才可行动。旧项目和预算不迁移。
