# 开发数据、冻结策略与最终评价

新主方法 `research.relevance-validation-pair` 只捕获 dev/validation 的 corpus、queries、qrels 和许可文件。查询与标注集合须恰等声明的两个拆分，拒绝多余行、非空metadata和额外asset；不会以旧三拆分schema伪造空test。旧citation/relevance适配器不修改，旧研究不升级或重置。

## 原生阶段

1. 在独立新项目保存计划。受信host于任何primary/Controller请求前调用 `ResearchProject.register_holdout(request_id, expected_state_version, holdout=bytes)`。私有包schema为 `retrieval-holdout-v1`，字段恰为 `schema_version/corpus_sha256/queries_jsonl/qrels_tsv`；绑定同一corpus，final query ID不得与开发集重叠。上限2MiB。原字节在固定私有目录，原项目状态只存严格校验的元数据及摘要。
2. 通过原Controller/Project执行validation主行动，消耗原工具预算1。BM25与TF-IDF两臂固定，全部排名先于评分；正例缺失保留分母、同ID截断前排除、合法0保留。
3. 调用 `freeze_retrieval_strategy(request_id, expected_state_version, primary_action_id)`。从已核原primary/工件读取validation Recall20配对差；预先固定规则为差值>0选TF-IDF，否则选BM25。冻结绑定原source、plan、code、action/result及holdout摘要，不能事后换方法或评价数据。
4. 原Controller只有在元数据及公开原结果符合条件时才提供 `research.relevance-final-evaluation` 候选，参数只能是原 `based_on_action_id/based_on_result_sha256`。原生step先持久原action/预算，再写排他持久启动标记，之后才读私有包并计算final。所选法与固定BM25在同一final集配对；选择BM25时共享排名和评分，不伪造第二次调用。保存审计是另一已有方法，若执行也计原工具1。
5. 完成后只保存final query哈希、数值、聚合、实际操作次数和来源/冻结绑定，不输出final query/qrels原文。重放原ID不重排；中断原请求只恢复原工件或保留unknown/预留，不换ID再计算。启动标记存在时直接重入也拒绝计算。

## Workbench与模型输入

启用本地操作时，沿原Origin/CSRF/活动项目门禁使用：

- POST `/api/local-workbench/retrieval-holdout`，exact body：`request_id/project_id/expected_state_version/holdout_base64`。manager只记摘要及元数据，不记原base64字节。
- POST `/api/local-workbench/retrieval-freeze`，exact body：`request_id/project_id/expected_state_version/primary_action_id`。
- 实际工具继续用既有advance/selection proposal；不是新的执行器、路径协议或预算来源。

sealed context可选 `staged_evaluation` 只投影登记摘要、计数、固定规则、冻结方法及final行动状态；旧无字段的context不回填。Host/native/plan/recipe提示沿同一投影，候选与冻结检查不打开私有文件。报告按新family验证source、完整元数据/请求绑定及final工件白名单，报告input不包含私有包。允许字段内的嵌套数组、非法类型及重算SHA后的错配均拒绝。

## 边界与验证

这是同一用户权限下的程序性分离，不能阻止用户预先知晓公开数据、语义重复、自由文本侧通道或协同重写全部磁盘；不宣称OS隔离或盲测。S042事前预测接口当前仍限其原reader家族，本family使用单独冻结协议，未冒称全部统一接线。

工程验收：91项相关回归、41项独立组合及4项独立不利probe通过；实际loopback登记/冻结/final共享原预算通过。私有文件Path.open被拦时仍可构造所有候选/模型提示及冻结；真正final中断后无第二次rank。完整证据与负例见[S045](execution/SPRINT-045.md)。这些不是科研收益；真实数据结果另记。
