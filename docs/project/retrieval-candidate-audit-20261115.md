# 新检索课题候选与意外曝光（2026-11-15）

本次只筛公开来源、许可证、规模和原生工具可行性；没有下载候选数据正文/qrels、选定最终集、创建研究 Project、排名/评分、fit 或调用模型。当前没有已通过来源权利、原数据身份、容量和评价协议的可直接执行候选。G5 许可范围是固定纯 CPU 检索/调度，不等于每份数据集和任意新预算自动获批。

## 意外曝光与处理

- 查 [QASPER 作者 NAACL 2021 论文](https://aclanthology.org/2021.naacl-main.365.pdf) 许可时，工具同时返回论文图示和测试误差分析中的若干公开问题及答案/预测片段；不能再称该 test 在当前上下文完全未曝光或为盲测。作者数据卡曾定位固定 revision `2614dfd2cfc0da26351d38e2f193eda7791970df`，没有读取该 revision 的数据文件。
- 查 [PubMedQA 作者 EMNLP-IJCNLP 2019 论文](https://aclanthology.org/D19-1259.pdf) 来源时，搜索结果自动显示一个已发表例子的答案类别，另一个索引返回一个示例问题；未核两者是否同一例或属于任何未来 final。作者仓库只记录 HEAD `1cbae8e92f72f20c8d3747cbb3bf5bc53554d997`，未下载数据/真值文件。不能称该候选完全未曝。

不复制以上问题、答案、标签；已停止可能返回样本的搜索。两次发生在 2026-11-15 08:56:20–08:57:52 UTC 的操作区间，确切秒数 unknown；工具原返回留在会话记录，本机过程记录 `runs/s079-exploration/exposure-audit.md`。不能由片段推断全部数据已曝或未曝；以后若使用任一来源，须在接触更多数据前固定独立方案并诚实披露污染范围。

## 本轮候选判断

- **PubMedQA：暂不准入。** 题目对应原配对摘要可作为一种单一代理正例，不是作者原本的完整检索真值；其他摘要未评判，原文章许可未核。自然 yes/no/maybe 是问答答案，不是检索相关性标注。加上上述曝光，不应声称盲测或直接启用。
- **bioCADDIE 2016：暂不准入。** [挑战论文](https://academic.oup.com/database/article/doi/10.1093/database/bax068/4237583)描述约 795,000 个来源于多个仓库的数据集；[参考标准论文](https://pmc.ncbi.nlm.nih.gov/articles/PMC5737202/)描述检索相关性评判。原生上限为 10,000 文档及有限资产/结果大小，且原始各来源和 qrels 许可、固定字节和可行子集仍 unknown。未评判项不能称人工负例，但当前二元指标实际不予相关性计分；保留被排除正例的分母也不自动保证子集有可比较性。不得根据标签或效果反复挑选子集，也不能把子集冒充完整挑战。

只读筛选完整过程在本机 `runs/s079-exploration/retrieval-candidates.md`。下一步是基于清晰权利和问题语义筛选其他来源，事前固定原数据、样本、规则、预算、源 pin 和唯一身份；若无法满足，就保留 unknown，不重启旧 Project 或扩大预算。该记录不构成新的前瞻实验、科研收益或模型调用。

## 后续元数据审查：SQuAD 2.0 和 Wikinews（2026-11-16）

只查公开元数据与许可，不下载正文、查询或标签，不创建项目或运行实验。SQuAD 2.0 官方称 CC BY-SA 4.0，含旧 1.1 内容及无答案问题；旧 S046/S054 已接触 1.1。原段落无答案不等于检索不相关或整个语料无正例，不能用当前二元检索指标直接声称无答案能力。官方 train 对象 42,123,633 字节，超过既有 40 MiB 接收上限；候选可能重复旧题、需要先固定去重和可复现截取，不能换身份重置预算或称新领域盲测。

英语 **enwikinews**（不是 enwiki）2026-11-01 官方 [dump](https://dumps.wikimedia.org/enwikinews/20261101/) 的 pages-articles.xml.bz2，经独立 HEAD 核为 47,533,780 字节；官方 sha1sums 为 `ce2fe5bdec3ef6b11fdd065b434b4283a695c40c`，实际文件字节和 SHA-256 未获取或复核。[站点 rightsinfo](https://en.wikinews.org/w/api.php?action=query&meta=siteinfo&siprop=rightsinfo&format=json)目前是 CC BY 4.0；[版权说明](https://en.wikinews.org/wiki/Wikinews:Copyrights)区分历史 CC BY 2.5 与较新 CC BY 4.0，逐篇归因、历史许可、转载等例外仍需核。它大于此前 40 MiB 接收上限，解压大小、可用文章、最终 packet 大小均 unknown。

标题→原文可以作为弱配对检索任务，不能当作人工完整相关性或真实性评价；标题与正文词汇重合、模板及事件重复可造成捷径，其他相关文章未标记而二元指标会计为不相关。须事前固定清洗、去重、分组和上限，确保 query/doc ID 不同以免 identical-ID 过滤误排正例，并核正例存在。解析整个 dump 可能接触未来 final 标题和配对，不能声称未读或盲测。两个候选目前均未准入；需独立固定来源、授权、预算和唯一 claim，不以新 ID 重开旧课题。元数据结果非真实研究收益。

## 后续跨领域候选与意外曝光（2026-11-16）

仅按官方网页与 API 元数据筛选：[UCI Beijing Multi-Site Air Quality 501](https://archive.ics.uci.edu/dataset/501/beijing+multi+site+air+quality+data)，DOI `10.24432/C5RK5G`，页面标 CC BY 4.0、12站逐小时、2013-03-01 至 2017-02-28，原压缩包网页显示约 7.6 MB，实际字节和 SHA-256 未下载核定，API last_updated 不是不可变版本。总 420,768 行超过本项目表格 50,000 行上限，压缩包大小不证明选定 CSV 满足 8 MiB 或 packet 上限。页面称缺失值 Yes、缺失用 NA；[官方 API](https://archive.ics.uci.edu/api/dataset?id=501) 却为 `has_missing_values: no`，且缺 data_url/feature；冲突待核，不能假设无缺失。原污染/气象监测机构数据归属与具体归因、压缩解压规模仍待核。若将来获批准，必须接触数值前固定站点与时间窗，不按结果筛选；只支持描述性观察，季节及时间依赖使因果结论不成立。此候选不是检索数据，不能证明 S109 经验迁移或 BM25/TF-IDF 收益，现未准入、未下载或执行。

另筛选 NFCorpus 官方数据卡时，网页预览意外展示一条医学文献标题和摘要片段，故不能声称完全未接触样本；未读取 final 查询/qrel 或下载文件。其[作者许可页](https://webserver.cl.uni-heidelberg.de/statnlpgroup/nfcorpus/)仅明确学术用途免费，与其他数据卡许可声明及原文权利尚需核对；当前不准入。
