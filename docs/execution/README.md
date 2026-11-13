# Master Execution Pack v2 · 云端执行

[原始计划](pack-v2/README.md) · [来源身份](pack-provenance.json) · [接续入口](../project/current.md)

最新[Sprint010](SPRINT-010.md)：独立ArguAna官方许可/全量原件审计、新relevance原生合同及一次冻结对照已运行。test Recall20 +0.15，保留186混合坏例；固定TF-IDF等臂对照使记忆增量为0，无完整Gate声明。见[真实结果](g5-local/retrieval-transfer-results.md)。

本次研发以 `5d497c8ae22100953f66c3c5b54746ca87e09f01` 为代码基线。约15天是规划窗口，不是已完成时间或自动跳过 Gate 的依据。

| 阶段 | 状态 | 验收依据 |
|---|---|---|
| G0 仓库/环境/上游审计 | blocked | [验收记录](g0/G0-review.md)；资源隔离和上游runtime smoke未通过 |
| G1 真实研究闭环 | 原Gate依赖保持；获批G1-L已verified | [两轮真实切片与恢复](g1-local/results.md)，不宣称原G0通过 |
| G2 动态协作 | 原Gate未通过；G2-L已verified | [模块/真实无收益对照](g2-local/results.md)，保留single；无模型Agent研究收益 |
| G3 跨课题方法改进 | 原Gate未通过；G3-L已verified | [两目标闭环/语义拒绝/恢复](g3-local/results.md)，无记忆因果增益声明 |
| G4 隔离代码级 RSI | 原Gate未通过；G4-L已集成verified | [独立原生微函数/源码集成](g4-local/native-results.md)，非OS/sealed/多代RSI |
| G5 RAG/算法迁移 | 原Gate未通过；G5-L原生两领域已运行 | [原生检索/调度](g5-local/native-results.md)、[独立9910项](g5-local/native-results-independent.md)，citation检索不生成答案；无完整/sealed声明 |
| G6 发布交接 | 原Gate未通过；G6-L归档/参数核验已运行 | [Sprint006](SPRINT-006.md)、[归档重开](g6-local/archive-reopen-guide.md)、[保存参数算术](g6-local/saved-model-arithmetic-results.md)；非完整离线依赖安装/训练重现/正式发布 |

## 当前任务契约

所有任务输入均包含原始计划、基线 commit、仓库 AGENTS 和相关索引。工具/模型用量 unknown 不记零；本轮没有外部模型 API 采购。以下文件所有权互不重叠，生产实现暂不修改。

| 任务 | 负责人/文件所有权 | 验收/依赖 | 状态 |
|---|---|---|---|
| R01–R06 现有能力审计 | repo_audit；g0/repository-capability-audit.md、matrix.csv | 源码行号、实现/目标区分、G1缺口；只读生产代码 | verified |
| R07–R12 上游机制/许可 | upstream_audit；g0/upstream/、仓库外references/upstream | ≥3核心固定commit与源码审查、许可证、复用决定 | verified |
| R13/R15/R16 课题与评价 | research_task；g0/*research*、evaluation-protocol.md | 官方数据许可/字段/来源、基线、竞争解释、独立评价边界 | verified |
| R14 云端资源 | resource_audit；verify_cloud_resources.py、g0/cloud-resource-smoke-test.md | 真实限制及失败保存，不用请求参数代替实测 | verified |
| G0 集成/基线/交接 | root；project/、execution主入口及ADR/验收 | 所有审计覆盖、基线日志、资产缺口与Gate结论 | verified |
| G0 独立评审 | independent_review；g0/independent-review.md | 不由实施者自己验收；报告实质漏项 | verified |

本轮每项调研约10分钟起始预算，本地重型Worker并发至多1。失败分支：保留证据、修复具体缺口、仅重验相关项；资源门不通过不解锁G1实现。

## 交付与下一步

[G0验收](g0/G0-review.md) · [ADR决定](g0/G0-ADR.md) · [独立审查](g0/independent-review.md) · [基线验证](g0/baseline-verification.md) · [资产交接](g0/local-assets-handoff.md)

`verified`表示对应审计/探针交付已核验，**不表示被审计产品能力、资源环境或整个Gate通过**。R14交付的结果就是资源门失败。输入准备和任务规范也不等于G1已执行。上游运行smoke保留独立blocked任务。

最终完整工程回归：1111项，1092通过、19跳过，exit0；详见[机器回执](g0/verification-results.json)。G0仍因资源和上游runtime条件阻塞。

GitHub交付：2026-11-13组织授权生效后，已成功推送`codex/execution-pack-v2-g0`，[PR #1](https://github.com/open-agent-power/auto-research-agentarts/pull/1)随后按用户指示直接合并至`main`，合并提交`269388af8f6d0a3330e5ea0e668459c428071367`。首个成功远程提交为`257ed278b4ded8d05d21ef7b4f94c29cdc7f5db4`；历史403记录保留，GitHub写入阻塞已解除。G0资源隔离及上游runtime验证仍未通过。

## 持续推进的决策节点

只读恢复复核表明Docker资源问题未改变，可信输入哈希一致。已向用户提出[具体执行顺序修订](g0/LOCAL_EXECUTION_DECISION.md)，当前`needs_user_decision`，不修改原G0结果，不启动拟合。G0允许的接口与评价准备可独立继续；收到明确选择后再实施对应路径。

已核对[现有原生接口合同](g0/NATIVE_INTERFACE_FREEZE.md)：真实字段、输入/计划/方法绑定、精确候选、累计预算、来源登记与读取、报告与恢复路径。该文件仅为G0独立准备，不创建新API，也不授权研究执行。

本地先行决定已接受：用户对具体推荐方案回复“继续推进”，[授权](g1-local/authorization.json)记录方案A及累计范围。此前needs_user_decision为历史状态；原G0仍blocked，G2+仍受限。

## Sprint 002 结果

获批本地G1切片已技术验收：[结果](g1-local/results.md)、[验收](g1-local/acceptance.json)、[复盘](SPRINT-002.md)、[恢复](g1-local/reproduction.md)。两轮MAE8.383388→5.702073MPa，313行/129组恶化、负值1保留；5工具/20estimator尝试/1来源/0产品模型，独立算术3252项及原/新路径29请求重放通过。原G0/G2+不变。

恢复归档已核验并记录[身份](g1-local/delivery-manifest.json)。为下一阶段准备的[Worker主机接入/验收包](../../deploy/worker/README.md)只运行既有有界探针、不安装或部署服务；实际可接入主机仍缺失，原G0保持阻塞。

## Sprint 003：扩大可信本地范围后的结果

用户最新[决定](local-continuation.json)取代上文历史G2+限制，允许受控本地继续，原隔离失败不再重复询问。[本轮报告](SPRINT-003.md)和[独立审查](SPRINT-003-review.md)记录实际G2/G3/G5/G6局部结果、失败/恢复/负结果及未通过的完整Gate。下一轮G4-L纯计算能力边界与代码候选准备中。

## Sprint 004：代码候选的实际闭环

[报告](SPRINT-004.md)与[原生/集成验收](g4-local/native-acceptance.json)记录真实helper差异、固定原生确认、源码集成及1164工程回归。旧研究292文件/50fit保持，旧服务固定原source。G6全新依赖环境已准备；G5同原生框架接线正在实施，未执行前不标已完成。

## Sprint 005–006：原生跨领域与归档交接

[Sprint005](SPRINT-005.md)完成两领域原生计划/执行/保存审计、9910数值检查、移址恢复、UI、clean wheel和77MB归档；[Sprint006](SPRINT-006.md)在继承云盘继续完成原提交推送、归档新target的8原ID恢复、2991保存参数预测重建及UCI原下载独立小补充包。失败/负例/原预算保持；不把保存参数核验写成重新训练、把依赖复用写成完整离线安装或推断平台调度完成。


## Sprint 007：CPU结果的实际阅读

[Sprint007](SPRINT-007.md)完成两领域保存宏指标、负结果与原行动入口。两个真实已有项目的桌面/手机五页、下载、只读状态和末列文字范围实测，独立审查通过，失败原件保留。这是展示增量，不是新排名、拟合或科研收益；[验收与恢复](g5-local/cpu-results-ui.md)、[精确身份与预算](g5-local/cpu-results-ui.json)。


## Sprint 008：补齐每次触发汇报与下步输入

[Sprint008](SPRINT-008.md)修正单个既有3小时任务的无进展/失败也需汇报规则，统一北京时间，新增[持久报告](../project/latest-report.md)；真实回读不等于未来通知送达证明。并完成保存不利查询原输入/定位审计，下一有界GET阅读器未实现，不补算缺失检索分数。[输入契约](g5-local/adverse-reader-contract.md)。


## Sprint 009：保存证据阅读与独立安装

[Sprint009](SPRINT-009.md)实现原不利查询分页/原文定位，真实原项目HTTP、桌面/手机五页和异常状态检查通过；继续安装物验证并处理实际可选CLI帮助缺陷。原数据、负结果、预算与producer保持。[阅读器](../saved-retrieval-reader.md)、[精确证据索引](g5-local/saved-reader-verification.json)、[分阶段安装物验证](g6-local/reader-release.md)。安装/帮助可用不代表云runtime、重训、隔离或完整G6通过。
