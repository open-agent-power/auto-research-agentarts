# 自主研究方法与真实课题选型

调研于北京时间 2026-11-18 对照仓库基线 `dd3195c1305989acb1cb20c00af50b5d4f53bd75`。查阅项目历史、原生接口、公开论文和候选数据官方资料，另读取一份 GovInfo 固定版 XML 核对结构。本文支持工程选型和课题准备。实验指标沿用有出处的历史记录，本轮没有运行检索或拟合。

## 外部方法与可检验的采纳

| 来源与观察 | 对本项目的决策及验收 |
| --- | --- |
| **ScienceAgentBench** 从 44 篇同行评审论文抽取 102 个任务，由 9 名专家参与验证，评价代码、实际运行及成本，关注训练数据污染。[论文](https://arxiv.org/abs/2410.05080) | 先验证单独的真实任务，留下输入、可运行代码、输出及费用状态。提前检查问题和标签泄漏。历史接口回归继续单列。 |
| **MLAgentBench** 有 13 个实际机器学习任务，允许读写、执行、看结果再迭代。各任务成功率跨度大，说明不同任务难度和先前曝光对结果有影响。[论文](https://arxiv.org/abs/2310.03302) | 在一个 Project 内保存真实输出触发的下一决定，定位到具体观察和计划差异。G3/G5 的跨任务结论需要独立输入、相同预算和可区分的对照。 |
| **PaperBench** 用 20 篇论文和分层规则来验收代码、实跑与复现，将自动评审的质量单独评估。[论文](https://arxiv.org/abs/2504.01848) | 固定“源可取、两臂可核、实际结果改变计划、他人从原身份接续”四项验收。独审从标签和原榜单复算，按条指出缺证据。 |
| **BEIR** 比较 18 套数据、10 种检索方法，表明 BM25 是强基线，重排的平均表现伴随较高计算成本。参考代码的入口明确分 corpus、queries、qrels 并评多个排名指标。[论文](https://arxiv.org/abs/2104.08663) · [代码与用法](https://github.com/beir-cellar/beir) | 沿用本仓库已审计的原生语料、查询、qrels 和词法基线。用 Recall@20 衡量覆盖、MRR@10 衡量首个相关结果位置，nDCG@10 只作补充。本项目现评估正例二值化，报告须明确其语义。 |
| **AI Scientist-v2** 展示实验管理和预算受限的渐进式树搜索。论文报告 3 篇投稿中的一篇在 workshop 审稿得到达到接收标准的分数。上游源码有独立专用许可。[论文](https://arxiv.org/abs/2504.08066) · [源码许可](https://github.com/SakanaAI/AI-Scientist-v2/blob/main/LICENSE) | 复用事前定义分支、保留失败实验、根据原结果选下一步的设计。先用已有两分支合同，团队自行复核，采用树搜索之前需有真实实验对照说明其收益。上游代码未引入。 |
| **Anthropic** 建议从最简单可成功的方案开始，迭代优化要求明确评价标准，增加复杂度会消耗时间和成本。[文章](https://www.anthropic.com/research/building-effective-agents) | 小团队按交付分工。没有清晰性能增益指标时，先使用现成的确定性规则。若将来验证模型参与，事前对照纯规则与受限模型，按实际采用的计划和实验结果计收益。 |

算法线可用经典加权区间调度的前驱索引和最优值递推作为可复核基线。仓库已有扫描与二分版本、独立 Fenwick 最优值验证。复用原排序、端点与平局约定，先做结果正确性和计时成本归因，再决定是否值得加候选。[Princeton 课程讲义](https://www.cs.princeton.edu/~wayne/kleinberg-tardos/pdf/06DynamicProgrammingI.pdf) · [原生运行证据](../../execution/g5-local/native-results.md)

## 本项目已有结果和真实缺口

| 已有事实 | 交接决策 |
| --- | --- |
| Hotpot 支持文档检索终评 Recall@20 从 0.91 到 0.92，MRR@10 从 0.865984 到 0.830095。公开源曾读入，相关标签不完备。[S065](../../execution/SPRINT-065.md) | 预注册覆盖提升及排名无退化，保留每题下降情况。查询任务名须准确描述标注范围。 |
| BoolQ 两套选择规则均选 BM25。正式终评只实际测了 BM25，TF-IDF 的终评反事实未知。[S067](../../execution/SPRINT-067.md) | 后续若验证规则收益，需有独立数据、预先定义的同预算比较和实际不同决策。同臂可说明两规则这次行为一致。 |
| Bike 2011 的真实数据和两次工具行动已保存。质量观察后的计划由操作者修订，结论是描述性相关。[任务基线](../research-baseline-20261115.md) | 保留已完课题和预算。已有的人工参与证据可作比较背景。 |
| S130 在两个合成项目走通等待和保存审计，S131 保存人工计划并按原 ID 恢复。S065 展示过不同的原生终评链路。当前 `save_staged_feedback_plan` 明确拒绝已登记 holdout、冻结策略或已有终评的项目。[S130](../../execution/SPRINT-130.md) · [S131](../../execution/SPRINT-131.md) · [Workbench 源码](../../../src/autoresearch/local_workbench.py) | 首轮选择无 holdout 的 S130/S131 路径，用真实来源检验双指标反馈和后续计划。后续终评须提前选兼容路径，独立注册，保持已完成项目原身份。 |
| S014 三臂调度对照的小任务阶段 12/12 较慢，拒绝晋级。它是独立 harness。G5-L 有两个原生方法的对照和回执，调度输入为合成负载。[S014](../../execution/SPRINT-014.md) · [G5-L](../../execution/g5-local/native-results.md) | 可用已有原生调度入口做新登记的窄比较，保留所有输入规模和失败。先证实问题适合单资源区间任务，再谈真实算法迁移。 |
| S035 的模型复核给出 `needs_revision`，方案未采用。S139 核心表格路径仍是未合入的中断修复。[S035](../../execution/SPRINT-035.md) · [S139](../../execution/SPRINT-139-review.md) | 当前先做零产品模型的真实检索闭环。研究代理自治、表格时间修复和多代 RSI 各自保留缺口。 |

## 真实来源比较

| 候选 | 本轮实际核对 | 选择 |
| --- | --- | --- |
| GovInfo 16 CFR 2025 第 1 卷 | 官方目录与 bulk 下载均返回 200。原 XML 为 4,422,809 B，共 96 个 PART 元素和 992 个 SECTION 元素。Part 425 有两套生效标记，超出条文定位小样范围。已固定 11 个候选 Part，合计 86 个 SECTION 元素。[GovInfo 目录](https://www.govinfo.gov/app/details/CFR-2025-title16-vol1) · [XML](https://www.govinfo.gov/bulkdata/CFR/2025/title-16/CFR-2025-title16-vol1.xml) | **优先**。稳定的历史文本和可核条文编号适合做条文定位。待独审条文权利、标签和最终资产；结果限所选历史版和构造问题。 |
| 现有 Wikinews 候选 | 项目既有调研记录显示来源范围、权利和弱标签仍有缺口。[原调研](../baseline-research-20261115.md) | 暂缓。优先补来源和标签质量，无须重拉多个完整仓库。 |
| UCI Appliances Energy Prediction | 官方元数据列 19,735 行、目标 `Appliances`，原始研究约 4.5 个月、10 分钟间隔。数据包含室内传感器与外部气象资料。本轮没有下载数据或验证各字段权利。[UCI](https://archive.ics.uci.edu/dataset/374/appliances+energy+prediction) · [元数据接口](https://archive.ics.uci.edu/api/dataset?id=374) | 另列真实表格备选。准备时先核字段、权利、时间语义和按时间划分，随后定义可区分对照。本课题不占首轮检索预算。 |

GovInfo 源只作固定年份检索。政府作品权利以具体内容核验，外部并入材料、标准、商标等单列。如无法确认再发布权，保留受限原始材料的受控复现路径，公开只发规范、哈希和审查过的指标。[GovInfo 政策](https://www.govinfo.gov/about/policies) · [17 U.S.C. §105](https://www.law.cornell.edu/uscode/text/17/105)
