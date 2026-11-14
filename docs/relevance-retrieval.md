# 原生相关性检索对照

`research.relevance-fixed-pair` 与 `research.relevance-saved-error-audit` 使用现有 ResearchProject、ProjectController、LocalWorkbench 和原生报告。不建立另一套控制器。旧 SciFact citation 工具、冻结协议、评价器与研究预算保持原身份；新方法改变当前研究代码身份，不能直接升级旧项目。

新输入合同为 `relevance-retrieval-spec-v1`，packet 的 `task_kind=relevance_retrieval`，scope 为 `relevance-retrieval-fixed-pair-v1`。`license_notes` 分为 `corpus`、`queries_and_qrels`；来源记录真实 archive/receipt/selection SHA，不填不存在的原作者 Git commit。`source_provenance.qrels_semantics=positive_relevance_binary_projection`，保存原始 grade 1/2，评分使用正相关文档集合。它不是引用文献、支持/反驳分类或事实核查。二元 nDCG 不作为任意 graded benchmark 的官方分数。

固定基线为 BM25，候选为 TF-IDF 余弦，top20、ASCII 字母数字小写分词、按 doc ID 破同分。复用本项目纯 lexical index/metric 核；新排名函数在 top20 截断前排除与 query 同 ID 的文档，保留补位结果和完整语料的 index 统计。缺失正例文档 ID 仍留在分母，scope 显示全部缺失 ID/条数，不补造文档、不静默删标签。未判断文档在计算中当作非相关，不代表人工已证明其无关。

全部 query/arm 排名完成后先计算内存内容 SHA，再计算指标；最终随不可变行动工件保存。没有在评分前将排名独立封存落盘，不构成 OS 或 sealed 评价。完整排名、原文行号、标注及 grade 定位、逐 query 指标和坏例均保留。后续 audit 只核保存结构与配对算术，不新建 index、不排名、不对 gold 重评分。工件封套与行动绑定沿现有核心校验。

原生报告 kind 为 `relevance`，指标表按 BM25→TF-IDF 展示，保留全部坏例及输入 SHA。工作台识别新的观察种类。后续保存逐query阅读复用同一GET路径和工作台阅读组件，以独立relevance schema/contract、原grade和missing IDs区分语义；接口与边界见[保存阅读器](saved-retrieval-reader.md)。Sprint010原验收仅覆盖JSON/报告，本轮新实现须以Sprint011真实HTTP/浏览器证据为准，不能追溯认领旧阅读器已支持新合同。

## 独立迁移课题

来源准入见[实际许可与输入审计](execution/g5-local/retrieval-transfer-source-audit.json)，一次性执行边界见[冻结/运行协议](execution/g5-local/retrieval-transfer-protocol.md)。ArguAna 使用作者官方 Webis 页面和 Zenodo 版本 DOI 的 CC BY 4.0 声明；保留作者、版本与转换说明。不沿用 NFCorpus 的学术限定许可，也不从 BEIR 的代码许可推断数据许可。

本题冻结 source-only coverage guard：旧 SciFact 保存结果中 BM25 相对 TF-IDF 的 test Recall20 下降，因此候选固定选 TF-IDF；新目标成绩不用于选臂。固定 TF-IDF 的无来源对照与候选完全同臂，读取同一保存值，增量记忆收益按构造为零。一次对独立领域的固定选择对照不能证明记忆因果收益、LLM 自主发现或通用策略有效。

ArguAna 原官方 BEIR 只有 test 划分；这里从全部 1,406 query ID 按预声明 SHA 选 80/80/300 个程序 dev/validation/test，保留完整语料、查询及全部 1,406 judgments。未评价的 946 查询原件仍保留。它是有界派生课题，不是 canonical 全量 leaderboard，也不是未知或封存数据。预算仅为这个真正独立课题的 2 次原生工具，0 模型/API/fit/source extraction；不增加任何旧案例额度。
