# Bike Sharing 2011：温度与日租赁数的描述性关联

## 研究结果

在 UCI Bike Sharing `day.csv` 的 2011 年全部 365 天中，按[事前协议](../../project/bike-sharing-2011-study-proposal.md)计算原归一化 `temp` 与 `cnt` 的 Pearson r：

| 样本 | 天数 | 排除数 | Pearson r |
|---|---:|---:|---:|
| 全部 | 365 | 0 | 0.7712141978934428 |
| `workingday=0` | 115 | 0 | 0.7624328784923204 |
| `workingday=1` | 250 | 0 | 0.7798472351298569 |

三项均有效且严格为正，满足预先固定的 `condition_met` 规则；质量检查无 flags、日期无重复、两数值列均有 365 个有限数值。独立审查用标准库重新计算三项，最大差异在浮点舍入范围内，并核对分组原编码、行动工件与账本。这里描述所选日期上的线性关联，不证明温度导致租赁变化、不保证预测或跨年泛化，也没有显著性或置信区间结论。季节、天气、趋势和假日等因素以及日期相关性均可能影响观察。

## 来源及限制

数据：Hadi Fanaee-T，[UCI Bike Sharing Dataset](https://archive.ics.uci.edu/dataset/275/bike+sharing+dataset)，DOI [10.24432/C5W894](https://doi.org/10.24432/C5W894)，UCI 声明 [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/)。此处将原 `day.csv` 改为仅含 2011 年 `dteday,workingday,temp,cnt` 四列的按日排序投影；未修改字段值。原 README 要求出版时引用 H. Fanaee-T and J. Gama, *Event labeling combining ensemble detectors and background knowledge*, DOI [10.1007/s13748-013-0040-3](https://doi.org/10.1007/s13748-013-0040-3)。

官方 README 和元数据对温度归一化的表述不同，后者的转换公式注明仅适用于小时尺度；每日尺度确切转换未知。本研究仅使用原归一化数值，不声称摄氏温度。完整 ZIP 与原日表的读取可能接触 2012 年目标值，不能称盲测；项目输入只含 2011。工作日定义来自原 README：编码 1 既非周末也非节假日。数据质量门只覆盖约定的机械检查，不代表数据没有其他偏差。

## 可追溯身份及预算

- 执行源码 commit `7926608e981eaf1fdfc94c0d125ae04b7f4423da`，project core `3bcccb20f6b428795fe7563ba9892af99fa83ed06704923fefe9e3f70c846f0e`；源码 pin `/workspace/development-continuation-20261114/source-pins/7926608`。
- 原 ZIP 279,992 字节，SHA-256 `b70182d0d0508e9abbb79306ce5c0cec34869000f8220175ac83d11dbe845401`；封存 source snapshot `6d9b7d96b9999a969c926cdf03fdc182779f8b5ac544b41ab9cbfcaa891885af`；来源人工复核 SHA `9b3c965aae328edce0a026dd5f7fc7ecc001ce4f4a772a75b3f5b26df1e73248`。
- 独立 Project `project-4654ecc751e94e92ba61ea22178360f5`、run `run-f78600530c7546d09fdd7bd8016d0576`，最终 state version 14、snapshot `c41d3a0245a0ff308f1b031fbef0f4e615b5967b2bdadc4756366b5d7d6efd06`，原计划为等待。
- 质量 action `action-446f306b9895bf9d5eb66b48f43b9e8d`，结果 SHA `927a84051517e9ba11fb9673aad1247abd80e7eb10ece682fdc2ac457b4719ca`；关联 action `action-898cceeaa4b37c9b544f21988202a893`，结果 SHA `2a58492c47ddecf14a5ce7d429a236eaba037de54002398f311e2ea8219400fb`。
- 真实研究用完 2/2 本地工具；账本记录模型请求 0、拟合 0、原生 evidence 读取 0。费用结算与开发 token 为 unknown；本地原件/报告文件 I/O 实际发生。

操作者在质量结果后保存引用该行动的观察和计划 v2，再选择与其绑定的关联候选；关联后保存反馈与计划 v3。这是受监督的原生 Project/Controller/Workbench 链，不是模型自主决策或实验对照收益。新进程只读 `inspect` 看到全部 11 个已完成阶段；未重放真实请求，也未证明跨进程中断或断电恢复。

原件、请求、行动、原生 PDF/Markdown 报告和本机账本位于 pin 的 `runs/bike-sharing-2011-v1/`，独立审查在主工作树 `runs/s080-real-review/independent-assessment.md`，SHA `193cbe6ad3a684d8c032400a9990a8e14dc4b6271b133b0a428c92afdf463fa2`。原生导出 manifest SHA `c6fe091677d3d2d253e07b534c9de11b90ce858780f46659c24fcaddc1a85e6a`。导出后首次校验脚本误把 manifest 项对象当字符串，断言失败；针对同一已生成报告正确核对四文件大小/SHA及项目状态后通过，未重新导出或重跑研究。报告的组坐标须对照原投影映射编码，许可及温度限制以本说明补充。
