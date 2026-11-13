# 独立 ArguAna 对照结果

一次真实对照已完成，原生状态为 state13/waiting、3版计划、2个行动。研究源码 `250954e98024844e102352aac8666859e4f761be`，producer identity `867075eb62d29a71bb71e99175c063c10fd3f9c8c9427ab8b4679a44b4969e30`；独立clean源码 pin `/workspace/work/arguana-transfer-source-250954e`。输入/许可/选样见[来源审计](retrieval-transfer-source-audit.json)，评价前冻结与审查见[协议](retrieval-transfer-protocol.md)，精确状态/行动/文件SHA见[机器结果](retrieval-transfer-results.json)。

项目 `project-0940a2e0cbd841e58677d2ecd99a33e2` 位于 `runs/g5-retrieval-transfer-20261114-01/manager/projects/8ac431dceaa72d506249738877b0331e8725bf79719bcf879cb52fd7f69dd658`。不得重跑driver、重新create/import或换输出目录开额度。共享study claim固定为 `g5-arguana-source-arm-transfer-v1`，pending/unknown只读原stage请求与relocation后恢复原ID；后续main/展示提交不升级producer。

## 冻结目标的实际结果

保留全8,674文档、1,406查询/标签；程序SHA划分仅评价460查询（80dev/80validation/300test）。一次主行动建1个index，保存920条完整排名、920条逐query指标；排名均排除了相同query/doc ID。以下为300个程序test查询，候选−基线按冻结的TF-IDF−BM25方向计算。

| 指标 | BM25基线 | TF-IDF候选 | 差值 | 胜/平/负 |
|---|---:|---:|---:|---:|
| Recall@5 | 0.500000 | 0.610000 | +0.110000 | 45/243/12 |
| Recall@10 | 0.643333 | 0.776667 | +0.133333 | 46/248/6 |
| Recall@20 | 0.746667 | 0.896667 | +0.150000 | 47/251/2 |
| MRR@10 | 0.318643 | 0.418357 | +0.099714 | 117/140/43 |
| binary nDCG@10 | 0.396192 | 0.503379 | +0.107188 | 117/140/43 |

dev Recall20为0.7500→0.8875（13胜/65平/2负）；validation为0.6625→0.9125（21/58/1），仅作描述，没有据此改选臂/参数/划分。预声明test Recall20符号规则得到`local_coverage_transfer_supported`，只支持这组公开程序查询上的局部覆盖表现，不包含显著性、通用性或自动采用结论。

来源指导候选和无来源固定TF-IDF对照读取相同460份保存值，逐query/逐metric完全相同；增量差按构造为0。该结果没有识别出记忆的因果收益。来源政策是薄host按旧SciFact已知public结果冻结的规则，原生Controller执行冻结pair并接收实际反馈；没有据此完成通用方法经验资格、自动学习策略或上游agent runtime集成。

## 保留的损失与范围

全部460 query的坏例混合集合186条：63条有至少一个指标下降，123条无指标下降但召回不全。按Recall20看，两臂都不全42条、仅BM25不全81条、仅TF-IDF不全5条；这组分类与指标损失有交集，不能相加充作独立样本。test仍有43条MRR/nDCG下降和2条Recall20下降。

5条缺目标文档的原正标注完整保留，其中2条落入test：`test-education-ufsdfkhbwu-con03a`、`test-society-asfhwapg-con04a`。两臂全部指标均为0，没有删标签、补文档或换查询。完整原grade、行号、排名与工件SHA在原行动/原生JSON报告，摘要不替代原证据。

这不是官方全量BEIR成绩、封存holdout、反论证真实性评审、新算法发现或LLM研究收益。ArguAna本次grade全1；新合同允许grade1/2并明确使用binary projection，不能把该nDCG泛称graded指标。旧SciFact覆盖损失、调度慢例、历史50 estimator和所有旧case/pins均保留。

## 生命周期与预算

新独立study额度仅2次原生工具：一次fixed pair、一次saved-only audit。计划1绑定冻结政策与来源；计划2引用实际primary action/result/观察/坏例；计划3引用audit后等待。primary/audit/wait均以原body重放确认不再计工具；四文件报告导出成功，包含完整输入与两行动。

工具2/预留0，fit/model/source extraction均0；子进程已装守卫阶段没有尝试网络、Ridge/Scaler fit或来源抽取。公开原件获取、回环HTTP和开发进程确有活动，开发token/金额unknown。资源限制沿原180s wall、CPU120/130s、1GiB、单文件32MiB、单线程及至少5GiB空盘；不宣称cgroup/OS或多代RSI通过。

首条schema-only准备命令因手录完整commit SHA错误被拒，尚未建研究项目；原stderr保留，随后从Git读取实际SHA在同一output成功冻结。只有一次获审研究attempt，完成returncode0，无批量重试。NFCorpus许可、来源403/转换初版、pytest缺失和浏览器选择器失败各自保留，不能抹成全程无失败。
