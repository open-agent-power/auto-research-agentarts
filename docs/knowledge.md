# 资料进入研究循环

资料库现在有独立的只读检索工具。它从已有来源清单建立固定索引，返回原文、来源哈希和定位；不执行参考仓库、不联网补答案，也不把档案里的“可复用”标记当成已经接通。

## 使用

使用项目虚拟环境，在产品根目录运行；输出目录必须是新的。`references` 指向工作区已有资料，单独克隆产品仓库不包含这些外部文件。

```powershell
$env:PYTHONPATH = Join-Path (Get-Location) 'src'
.venv/Scripts/python.exe scripts/build_knowledge_pack.py --references ../../references/auto-research --output runs/knowledge-your-run
.venv/Scripts/python.exe scripts/evaluate_knowledge_pack.py --database runs/knowledge-your-run/knowledge.sqlite --tasks examples/knowledge-tasks.json --output runs/knowledge-your-run/evaluation.json
```

先验证平台文档和项目档案可加 `--no-papers`。该模式明确跳过论文正文；评估里的论文任务记为 skipped，不能计作通过。

```python
from autoresearch.knowledge import KnowledgeIndex

index = KnowledgeIndex('runs/knowledge-your-run/knowledge.sqlite')
result = index.search('AgentArts Runtime SDK HTTP 运行时', kinds=['official_doc'], limit=5)
```

每条结果含 `citation_id`、`source`、`location`、`quote`。Markdown 为行范围，PDF 为真实页码。相同文件最多返回两段；每次最多八段。没有依据时返回空 evidence。研究决策应保存本次完整结果并引用 citation_id，不能只保存模型转述。

项目的`pdf_page`选区也保留真实PDF页码：新来源行动完成后，FTS命中的`location.page`来自实际提取页，`source.metadata.extraction`保留页内字符范围、偏移说明及整页/选区文本身份。字符范围描述整个已读选区，命中的`quote`可以只是其中一个chunk；不把它当作原PDF字节或视觉坐标。旧冻结索引和决定保持原记录，不自动重建；非PDF选区仍沿原定位和chunk行号返回。项目读取方式见[PDF选区](project-slice.md#读取已归档pdf原文选区)。

### 固定来源内检索与有界阅读

现有索引无需重建。`catalogue(limit=8)`返回有上限的文档目录；`search(..., document_id=..., source_sha256=...)`在排序与全局截断之前限定精确来源。两个选择字段必须同时提供，不把标题、路径或另一份同名论文当成该来源。

`read_source(document_id, source_sha256, start_chunk=0, count=2)`只读当前冻结数据库中的原片段。结果含`evidence`、实际`window`、`next_chunk`和最多40项标题导航；每次最多两段。片段顺序从原构建时的`document_id:ordinal`确定性引用ID恢复，不以行号或哈希字典序排序。导航项的`chunk_offset`可用于下一窗口，目录不是正文阅读证明。原source SHA与索引文本SHA分别保存，不能把正文前缀说成原文件全文。

这一步复用[PaperQA的检索／证据汇集分层](https://github.com/Future-House/paper-qa)和[ParentDocumentRetriever的小片段定位、较大上下文读取模式](https://reference.langchain.com/python/langchain-classic/retrievers/parent_document_retriever/ParentDocumentRetriever)，沿用现有SQLite与引用契约，没有安装另一套检索服务。新增操作会核对冻结库和sidecar，来源记录最多1MiB、单来源最多4096段；范围或SHA错误拒绝，不修复模型选择。它仍只证明读取一致性，不自动批准模型对原文的解释。

### 默认表格解释查询

`data.tabular-quality-audit`在`interpretation`的默认查询以已保存的未决问题为先：使用`next_decision.remaining_questions`中首个合资格问题，问题至多512字符、64个检索token。保留原问题，并为字母与数字连写的标识符追加拆分别名，例如`Factor47`同时检索`Factor 47`；不把标识符解释成字段映射或改变原值。没有合资格问题时，沿用已有的声明字段查询。

新来源完成时，用本次保存的未决问题构建解释预览，再进行四处既有证据查询。范围仅为表格解释的默认查询，其他领域和另外三个决策点沿用原行为；不拼接宽泛的基础问题，不合并多次查询排名，也不重建冻结索引、修改引用格式或新增接口。返回结果仍保留原`citation_id/source/location/quote`。

A37的hiMSC v30核对暴露了查询差异：默认5条引用遗漏已保存的编号冲突，但同一冻结索引查询`Chem 28`能返回原`iMSC_B8S1!A434:D436`。原项目显式登记兼容代码至v31后，默认上下文已同时保留作者标签与原冲突引用，用量仍为本地2/2、来源4/8；原ID重放没有变化，未新增模型或读取。修复的是默认查询选词，未发现原引用被阅读窗口剪掉；实际对比及领域边界见[hiMSC核对](himsc-source-audit.md)。检索命中只证明宿主取回了原文，不表示模型已阅读或编号对应已确认。

## 资料分层

| 类型 | 入口 | 能证明什么 |
|---|---|---|
| official_doc | 华为官方快照 manifest 中下载成功的 Markdown | 对应快照的接口、步骤与限制原文 |
| research_profile | catalog 中的28份项目简要档案 | 固定版本的候选模块、位置、许可与尚未验证项 |
| research_paper | catalog 记录且哈希一致的论文，按页读取 | 原论文正文及页码；不是自动复现实验 |
| reuse_note | REUSE-INDEX、autoresearch、C01三份复用说明 | 本项目整理的适配建议；不是原始研究证据 |

原清单中未成功下载、文件缺失、大小或哈希不符、越界路径等不进入索引；原因写入 audit。档案没有历史文件哈希的，只能标注本次计算哈希，不能冒充历史一致性校验。PDF 许可与代码许可分别记录，扫描页不伪造正文。

源文件保留原位置。SQLite 与同名 JSON 清单保存在 ignored runs 中，清单含源清单哈希、语料身份和数据库哈希。每次查询核对冻结数据库，查询以只读方式打开，不修改上游材料。PDF逐文件在独立Python进程解析，每份最多30秒，整次论文采集最多300秒；超时或解析失败明确隔离，不让整个资料入口无限等待。这不是操作系统级沙箱或内存配额。

## 检索与复用选择

直接复用 Python 自带 SQLite FTS5，采用英文标识符与中文双字词分词、BM25、精确标题优先和来源类型过滤。无需向量服务、付费 embedding 或运行外部项目。具体评分方式见 [SQLite FTS5 官方说明](https://sqlite.org/fts5.html)。

资源元数据与正文分离的组织方式参考已有 Biomni 的 `KnowHowLoader` / `ResourceRetriever`；没有复制其框架或默认模型调用，也没有安装其数据湖。现阶段需要的是可复核的少量上下文，不足以证明采用完整 Biomni 能提升研究质量。autoresearch 的固定输入、固定评估与保留失败记录用于后续实验契约；其无限运行指令没有进入本工具。
