# 分阶段检索的保存查询读取

S056 在原 `staged_feedback_reader` 复用 `_checked_primary`，既保留原 validation delta，也供应仅 dev/validation 的不利列表和单查询。只接受已完成 staged primary；audit/final、test/final split、不存在查询或损坏原件拒绝，不读取私有 final，不排名、评分、拟合、发模型或恢复行动。

沿已有 `GET /api/project/retrieval-adverse.json` 与 `retrieval-query.json`：原 project_id、snapshot_ref、action_id 和分页/单query selector不变，按项目注册的staged方法显式分派。旧 citation/relevance响应和train/test语义不变。新schema分别为 `saved-staged-relevance-adverse-page-v1`、`saved-staged-relevance-query-v1`，不可当成旧DTO处理。

binding保持原项目/快照/行动/结果/来源及primary ID/SHA。origin分列原source文件SHA、producer code identity和reader实现SHA；历史producer与新reader不同不意味着升级原项目。contract明确development、BM25/TF-IDF和二元正相关语义。

列表返回保存的category/两臂指标/delta/loss与分页计数。详情返回原查询文本/行/SHA、两臂原指标、完整qrel grades/缺正例IDs，以及各最多20个原排名文档的标题、文本、坐标和原grade。沿旧reader的query/正文4096、title512及明确truncated标记，不截断qrels；整次序列化超过1MiB拒绝，不用半份数据冒充完整响应。分页默认25。

每次核原source/action/SQLite指纹/封套、两臂完整覆盖、原query/document坐标与qrel grade、保存配对算术，并在投影后重新核原件与snapshot。数据漂移不返回部分内容。纯读取保持原预算和行动；执行/unknown仍要求原source pin。

真实S054旧producer读取已核：原纽约周收入问题的正例BM25排第1、TF-IDF排第2，保存MRR为1与.5；原47文件/状态/3工具额度不变。本片只交付library/HTTP API，没有改前端或把staged原文接入Host/plan的saved_materials。[证据与限制](execution/g5-local/staged-reader-verification.json)。
