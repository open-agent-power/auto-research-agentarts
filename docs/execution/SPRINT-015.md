# Sprint015：字母数字拼法的实际FTS命中

连续开发接续Sprint014，未增加团队成员或启动新研究。源码 `404ef9772c2160c036788d3fd5b156f512e4f172`，clean pin `/workspace/work/knowledge-query-alias-source-404ef97`。仅`knowledge._query_tokens`追加有限别名，新建相关测试；原词/中文别名优先，64项、公开query512字符/返回8项限制保持，索引、source filters、引用和权限不变。

同一个七文档手造冻结索引分别由旧62f源码与新源码实际读取；`top20`/`Factor47`新增命中空格摘录，反向新增命中连写摘录。`KnowledgeIndex.search`与已有`project_knowledge.query`两条入口引用一致，quote/line/source SHA/text SHA/`may_execute=false`及索引/清单前后字节保持。37相关工程测试通过，独立代码审查与独立实际查询对比通过；没有拟合、真实研究排名或Recall收益证据。

原空格查询OR噪声仍在；alias可能改变BM25排序/TopK，不保证全结果超集。重叠相邻对已补测；旧索引丢单字符词，`x1`/`x12`不能保证找回分写原文，负例保留。不跨标点/tab/邻接Unicode词字符泛化，也不重建旧索引。下划线可被SQLite解释为连续短语，不能笼统说未命中。

FTS只检显式项目知识引用，ResearchMemory精确scope与显式项目经验context没有自动打通。实际CPU经验库8cc9445c…只读检查前后相同，不创建新项目或候选。source404的新native codeidentity为 `4b93246c616c927921199b547a46c09c233f76aa0f764fcfa55504269a50d9c9`；旧study62/e731、所有producer/pins不升级、不替代。已有79b6安装包不包含本次改动，新wheel安装验收另行推进。

[使用及边界](../knowledge-query-spellings.md) · [精确验证/身份](g5-local/knowledge-query-spellings-verification.json)。本增量新增研究/fit/模型/API/来源抽取0，开发成本unknown。下一交付为已完成study的静态证据胶囊，再补当前source的独立成品安装，不执行研究或重复正式audit。
