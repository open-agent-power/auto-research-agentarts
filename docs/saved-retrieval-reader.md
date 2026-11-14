# 保存不利查询阅读器

阅读器现按已登记的方法家族读取引用检索和正相关性检索。原SciFact引用协议响应保持，新增relevance响应具有独立schema及显式contract；不由客户端参数切换方法语义。以下原133条证据属于Sprint009；本轮ArguAna186条读取的实际验收另记Sprint011。

## 相关性保存记录

原`research.relevance-fixed-pair`和`research.relevance-saved-error-audit`也从实验中心同一按钮按需读取。角色为BM25基线、TF-IDF候选，两个接口/选择器/25条分页/1MiB响应/原项目快照门禁均复用，不增加研究工具或执行器。新schema分别为`saved-relevance-adverse-page-v1`、`saved-relevance-query-v1`；引用响应继续为旧`saved-retrieval-*-v1`，不追加新contract/grade字段。

新响应顶层`contract`精确含：`id=relevance-retrieval-fixed-pair-v1`、`qrels_semantics=positive_relevance_binary_projection`、`baseline=bm25`、`candidate=tfidf_cosine`、`ignore_identical_ids=true`、`missing_document_policy=retain_in_denominator`。服务端以已登记action及项目registration选固定家族，拒绝source/result/primary/audit不一致；前端再次校验contract、主行动、算法角色和保存指标绑定。

详情的`arms`按BM25、TF-IDF顺序返回；`qrel`保留`doc_ids/source_sha256/role`并新增原始`grades`（严格整数1/2）及`missing_doc_ids`（正标签目标缺于捕获语料）。每篇保存文档新增`original_grade`，原qrels未标注时为null，不填0或声称确证无关。原grade保留，现指标按grade>0做二元投影，不称任意graded benchmark官方分数。缺失正例仍在原指标分母，只显示原ID和grade，不补造原文、排名或命中。原排名不得含同query ID文档。

相关性分支额外核原action请求SHA、method instance、source/input binding、audit参数→保存前驱，以及完整保存指标的配对算术/坏例集合；这些校验不对gold重评分。原source/action/result/行号/SHA及完整保存覆盖继续验证。新query原文可大于4096字符，但展示仍按4096截断并标记；ArguAna实际186条中最长query3519字符，因此更长query的展示边界只能由明确工程fixture验证。

ArguAna原186条混合集合中，63条有指标下降，42条无指标下降但两臂召回不全，81条无指标下降但仅BM25不全。两条缺正例也保留；旧SciFact133条及其语义不改。程序划分/公开标签不构成封存盲测，固定TF-IDF等臂对照没有识别记忆因果收益。


已经完成的原生引用检索项目，可在实验中心的原行动卡点击“查看不利查询原记录”。页面不会自动读取，也不提交研究。每页最多25条，保留原顺序和原分类；选择查询后才读取原查询、两臂各最多20篇保存文档及原指标。主检索行动和保存审计行动均沿同一已登记项目读取。

133条原记录包括60条指标损失，以及73条无指标损失但召回不全（65两臂不足、8仅基线不足）。这些数字来自完整保存结果，不能由只有总数的observation投影补造。指标改善不自动采用候选；未列入原引用标签不等于文献与查询无关，引用标签也不是支持／反驳或答案真伪判定。

## 读取与边界

选择查询后展示原queries.jsonl行号、输入SHA、保存指标及两臂文档序位。展开文档可阅读标题和文本、原corpus.jsonl行号、文档ID、SHA及原引用标签；原行动和前驱身份可展开核对。返回列表恢复触发按钮焦点和列表位置。

没有保存逐文档检索分数，因此不提供或补算分数。文档正文最多展示4096个Unicode字符、标题512字符、查询4096字符，超过时明确提示展示截断；原输入字节和原定位保持。它读取保存的top20，不重建未保存的全语料排名。手机指标表可局部横向滑动，正文和来源身份换行，文档列表有界滚动。

切页、刷新或加载失败不新建项目、不重发科研请求、不扩预算。刷新后需重新显式读取。项目/快照不符时显示错误；失败分页保留上次已核对分页并标明，失效或已移除的异步视图不会接收新结果。

## 只读HTTP接口

两个接口均为GET，始终要求来自当前`GET /api/project`的三个字段：`project_id`、`snapshot_ref`、`action_id`。action须为当前项目中已完成的原检索或保存审计行动。客户端不提交文件路径、研究request_id、模型请求或运行参数。

| 路径 | 附加字段 | 返回 |
|---|---|---|
| `/api/project/retrieval-adverse.json` | 可选`offset`（默认0）、`limit`（默认25，1至25） | `saved-retrieval-adverse-page-v1`，binding、pagination、全体分类counts和本页items |
| `/api/project/retrieval-query.json` | 必须`query_id`、`split`（dev/validation/test） | `saved-retrieval-query-v1`，binding、原query、分类和两臂metrics/qrel/documents |

只接受单次非空字段和精确字段集合，选择器最多2048字节，页offset不得超过原不利行数（允许空终页）。不存在的原行动或不利查询返回404；非法、重复、未知或超限选择器返回400；旧快照或活动项目变化返回409。工件损坏或超限返回固定错误，不泄露宿主文件路径。现有写门禁与同源规则不变。

每次读取均验证项目、完整结果封套指纹、action/result/source身份及audit→primary关系。source.json先按既有16,000,000字节上限读取，再按原资产上限和SHA校验；单行动最多5MiB，响应最多1MiB。保存query/文档行号、qrel来源及两臂完整记录资格均核对；模块只验证并复制原值，不调用执行器、索引、rank、评分、拟合或控制器行动。

服务在读取前后重新核对当前活动项目和snapshot，前端再次核对project/snapshot/action/result/source与原primary绑定。接口不接受客户端任意路径。文本通过textContent展示，不把原metadata里的支持/反驳注释当作检索真值。

## 实现与实际证据

后端为`src/autoresearch/saved_retrieval_reader.py`，路由在`project_workbench.py`；前端为`frontend/src/retrieval-reader.ts`，从原`cpu-results.ts`／`project-view.ts`复用。源码固定提交 `0acb05e253f543ea2483e383c7e2358c81c422bd`，旧科研codeidentity仍为 `3945ed0f5ec85b0ce42af0bb9ac0d0c27034bf932dac27fee9f7008ec2d3707e`，不升级旧producer。

针对性测试17项、原HTTP门禁5项、前端format/lint/typecheck/build通过。真实原项目HTTP59次GET检查覆盖12页、两行动共6次查询详情及26次错误返回；两个已有项目的桌面/手机五页与按需阅读在实际浏览器验收。完整证据和限定审查见[Sprint009](execution/SPRINT-009.md)。这是保存结果阅读增量，不是新增科研收益、隐藏评价、完整隔离或多代RSI。
