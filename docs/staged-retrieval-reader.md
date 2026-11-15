# 分阶段检索的保存查询读取

S056 在原 `staged_feedback_reader` 复用 `_checked_primary`，既保留原 validation delta，也供应仅 dev/validation 的不利列表和单查询。只接受已完成 staged primary；audit/final、test/final split、不存在查询或损坏原件拒绝，不读取私有 final，不排名、评分、拟合、发模型或恢复行动。

沿已有 `GET /api/project/retrieval-adverse.json` 与 `retrieval-query.json`：原 project_id、snapshot_ref、action_id 和分页/单query selector不变，按项目注册的staged方法显式分派。旧 citation/relevance响应和train/test语义不变。新schema分别为 `saved-staged-relevance-adverse-page-v1`、`saved-staged-relevance-query-v1`，不可当成旧DTO处理。

binding保持原项目/快照/行动/结果/来源及primary ID/SHA。origin分列原source文件SHA、producer code identity和reader实现SHA；历史producer与新reader不同不意味着升级原项目。contract明确development、BM25/TF-IDF和二元正相关语义。

列表返回保存的category/两臂指标/delta/loss与分页计数。详情返回原查询文本/行/SHA、两臂原指标、完整qrel grades/缺正例IDs，以及各最多20个原排名文档的标题、文本、坐标和原grade。沿旧reader的query/正文4096、title512及明确truncated标记，不截断qrels；整次序列化超过1MiB拒绝，不用半份数据冒充完整响应。分页默认25。

每次核原source/action/SQLite指纹/封套、两臂完整覆盖、原query/document坐标与qrel grade、保存配对算术，并在投影后重新核原件与snapshot。数据漂移不返回部分内容。纯读取保持原预算和行动；执行/unknown仍要求原source pin。

真实S054旧producer读取已核：原纽约周收入问题的正例BM25排第1、TF-IDF排第2，保存MRR为1与.5；原47文件/状态/3工具额度不变。本片只交付library/HTTP API，没有改前端或把staged原文接入Host/plan的saved_materials。[证据与限制](execution/g5-local/staged-reader-verification.json)。

## 新 staged Project 的显式用途

Python `ResearchProject.create` 对新建 `research.relevance-validation-pair` Project 可选 `evidence_purpose="operator_declared_staged_retrieval_research"`。它只是一项操作者声明，不授予研究、来源使用或数据获取权限，不证明许可、预注册、盲测或科学有效，也不改变预算、候选、工具、模型许可或 `scientific_validation`。它仅接受原生 `staged_relevance_development`、development、dev/validation 范围的 source packet；调用前仍需单独确定课题和预算的授权及来源权利。当前 Workbench/CLI 的直接创建入口没有新增此字段；Python 创建后可使用现有 manager import。

显式用途同时保存于 Project 顶层与 registration，并在读取状态时检查这两处与方法及范围形状一致。状态和报告中的范围是持久状态投影，**不代表 status 已重新读取并认证磁盘 source**；例如只将 split 的正数计数改成另一个正数，可能仍通过形状检查。同一 workspace、完整相同配置显式重开时才核当前 Project core 与原 pin、项目内 source 原 bytes/SHA、source snapshot 和完整 scope；任何不符都停查。`create` 本身没有 request ID，manager import 才使用其原 ID；部分创建保留原目录，不以新目录假称恢复。两处字段是同一账本的一致性约束，不是独立见证、签名或对整体重写的防护。

未传用途时保持原默认值及原 registration 形状；原表格 `operator_declared_descriptive_research` 只适用于原表格方法，不因新枚举改变。新用途会改变新 Project 的源码 core 身份，旧项目与旧 pin、预算和状态不自动迁移；如当前源码与新 staged 声明项目的原 core 不同，显式重开返回 `CODE_CHANGED`，应使用原 pin。已有只读状态和实际来源/工件仍按各原接口合同分别核对。
