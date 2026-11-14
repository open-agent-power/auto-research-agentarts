# 知识、数据与记忆索引

固定CPU保存经验使用独立schema与binding-only条目，完整原结果/协议保留、资产原字节只引用SHA；沿ResearchMemory撤回/精确scope和现有项目案例资格，不自动选臂。见[CPU经验](../../docs/cpu-project-experience.md)。

独立 ArguAna 来源已通过官方 Webis/Zenodo CC BY 4.0 与原件映射审计；NFCorpus 学术限定负证据保留。完整 corpus/query/qrels 与无成绩 SHA 选样见[准入审计](../../docs/execution/g5-local/retrieval-transfer-source-audit.json)，不由代码许可推断数据许可。


原生[保存误差诊断](../../docs/research-design.md#原生保存误差诊断)是本项目的工具反馈：完整原CV引用、行／折／组误差进入计划输入，完整小组表或明确整表引用保留全部坏结果。它不自动晋升为条件记忆或跨项目案例，不产生新CV／fit／来源读取；如需跨项目复用，仍走下述显式案例协议。

保存OOF案例支持显式父行动配对：完整2,048行边界、两份原工件与各自生产身份、离线全量算术和严格同评价核对。紧凑案例保留父版收益及恶化行／组／负预测，供context、知识页和报告读取；仍是历史类比，不新增本题证据或执行资格。见[配对用法](../../docs/project-experience.md#显式保存父版对照)。

[跨项目方法案例](../../docs/project-experience.md)复用`ResearchMemory`及既有方法卡；保存OOF数值先复核，再显式导入目标项目。来源active仅表示导出时资格，目标自行撤回／恢复；案例进入独立context，不进入本项目原文证据、FTS或执行资格。首版覆盖固定Ridge保存结果，尚非全部领域的统一经验学习。

结构化[方法卡](../../examples/research-method-cards/feedback-driven.example.json)通过`research_recipe.parse_method_card/match_method_card`读取与关联原宿主候选，保留依据、适用／不适用／未知说明、反馈分支和来源定位。文本不执行、不联网获取来源、不等于条件已自动满足；实际查询、未报告条件和下一轮接续见[方法卡设计](../../docs/recipe-research/recipe-design.md)。

适用：本地检索、RAG、外部来源接入、数据读取和经验复用。目标是让知识参与研究选择及证据核对；开发平台文档与科研证据分别使用。

| 任务 | 正式设计/说明 | 实际复用入口与状态 |
|---|---|---|
| 原文检索、限定来源和继续阅读 | [资料进入研究](../../docs/knowledge.md) | [KnowledgeIndex](../../src/autoresearch/knowledge.py)：catalogue/search/read_source；已有 SQLite FTS5 |
| 读取检索结果、来源身份与定位 | [知识工作台](../../docs/knowledge-workbench.md) | [knowledge_browser.py](../../src/autoresearch/knowledge_browser.py)；引用合法仍需核对解释 |
| 带适用条件的历史经验 | [条件记忆](../../docs/research-memory.md) | [ResearchMemory](../../src/autoresearch/research_memory.py)：recall/set_status；不能把模型判断直接当事实 |
| 经验进入后续模型请求 | [记忆接线](../../docs/c01-memory-loop.md) | [c01_memory_context.py](../../src/autoresearch/c01_memory_context.py)；已有案例接口不证明跨任务收益 |
| 外部资料和数据进入研究 | [公开来源接入](../../docs/public-source-connector.md)、[自适应研究设计](../../docs/research/adaptive-research.md) | [EuropePmcSource](../../src/autoresearch/europe_pmc.py)已接固定官方DOI公开GET；通用搜索、任意下载及其他提供方仍待建 |
| 真实材料—细胞数据的资格 | [数据候选](../../docs/data-candidates.md)、[P02 数据](../../docs/chemotopo-data.md) | 字段、终点、批次与对象对应单独核对，不靠向量相似度合并 |

## 四个服务时刻

A5 已把真实项目选区经 [project_knowledge](../../src/autoresearch/project_knowledge.py)送入现有 FTS，并在 [ResearchProject](../../src/autoresearch/research_project.py)保存四处查询与出处；[两方法目录](../../src/autoresearch/research_methods.py)据已读来源和未决项更新下一决定。当前是宿主检索/固定规则接线，不表示模型已读、ALP 已确认或跨域知识服务已完成。

有多次已完成来源读取时，查询先合并最新索引的实际命中，再按原limit截断，避免旧来源占满默认5条后使新证据无法进入选择上下文。索引与已保存的决定不改写；旧来源仍参与查询。改变检索代码后，已有项目须显式升级代码身份，额度与历史不重置。

项目新`pdf_page`选区的FTS命中保留原物理页码和选区字符范围/文本身份，沿原`project_knowledge.build`接线；旧冻结索引不重建。Yacht的一手手册读取保留了UCI描述与实验室模型试验语境的差异，未据图像表格补出原生hull映射或目标转换；见[真实任务记录](../../docs/research/yacht-geometry-study.md)。

A7 已将同一路径用于有限的材料/软件任务，按领域保留不同的四处知识需求；仍只读实际提取的来源片段。失败选区记录留在账本，但不会再次成为自动选择的“可读”收据。

问题形成时找已有发现和争议；选方法时找适用设计与工具；执行时读取字段和测量说明；复盘时召回条件匹配的真实行动与结果。具体数据流和外部来源计划以自适应设计为准，不在这里复制协议。

当前优先复用 FTS 和原文定位。向量召回、混合排序与重排只作为可比较候选，依据实际漏检与答案错误决定引入；未运行 embedding 不标为已向量化。

## 更新与最小验证

新增来源或检索方式时核对原文定位、数据/文献分流、无依据及冲突场景，并用实际研究问题检查是否影响下一行动。原始来源保留版本；经验条件变化后允许重新评估，避免永久封禁旧失败路线。

工作区外部材料入口见[参考索引](references.md)。私有项目材料的共享与训练用途沿原授权，不因写入索引扩大。

A16 [表格输入](../../docs/tabular-quality.md)保存spec与CSV的原字节、SHA及宿主派生声明；四处知识请求使用data字段/分组/目标词表。读取提交者spec不核验上游、许可、终点或独立性，原件和0/缺失保留，不能把本地转换当作者新资料。

A31 [hiMSC来源核对](../../docs/himsc-source-audit.md)取得此前缺失的作者CTC图像元数据并保留完整公开清单。只读 [inspect_himsc_source_linkage.py](../../scripts/inspect_himsc_source_linkage.py)复用现有XML读取器，核对原CSV/工作簿、联合零值及保存layout；它是独立取证脚本，没有增加运行时方法或自动调用。实际发现216行Chem0/28差异、17条全零行未建立同序对应，拒绝完整连接。新原件选区与明确标记的操作者派生结果沿原source-selection进入同一项目与FTS；命中不等于模型阅读或作者确认。

同轮实际发现data默认解释词无法命中当前原件，`project_knowledge.decision_needs`现保留通用词并追加source_scope的完整target/numeric/group/key字段名，限512字符/64词元，放不下的整字段跳过；不以claim充检索原文。新context可引用已保存片段，旧提取/决定不重写，不据命中推断科学有效性。

三项固定CPU primary的decision_needs已有独立领域词、正确方法角色及原标识，优先保留有效remaining question；不落ALP默认，非CPU/异常method旧fallback保持。这里只核有界词串，未证明FTS命中；SQLite默认拆下划线，不声称数据库精确单token。


[知识拼法兼容](../../docs/knowledge-query-spellings.md)：`knowledge._query_tokens`有限字母数字alias，source404ef97/37相关tests及真实小索引双版本项目query对比过，旧OR/TopK/单字符索引限制保持。FTS、精确scope memory、显式项目经验context仍独立，不自动选臂或晋级；[精确验收](../../docs/execution/g5-local/knowledge-query-spellings-verification.json)。

[S032经验决策引用](../../docs/experience-decision-citations.md)给直接proposal增加已绑定active case的精确来源引用，保留原association/反例，不自动跨项目recall或提升方法资格。真实双CPU包的等待/保存/退休/重放47工程检查不等于经验科研收益，内置模型wire尚未支持。
