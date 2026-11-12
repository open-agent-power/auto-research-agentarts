# Scenario Task Definitions

## Scenario 1 — Tabular Exploratory Research (P0)
输入：真实表格、相关论文/资料、字段字典或映射线索、研究问题。
任务：数据理解、质量诊断、假设、方法选择、实验、证据分析、计划修订、下一轮研究。
评价：字段映射正确、方法适用、结果可复算、证据可定位、路线修订有依据、结论不过界。
最低交付：一个完整课题、两轮以上有意义的研究推进、复现包、交接测试。

## Scenario 2 — RAG Retrieval Research (P1)
输入：固定 corpus/query set。
任务：设计检索策略实验、执行、比较、错误分析、改进下一轮。
评价：Recall@K/MRR/nDCG、延迟、成本、跨查询类型稳健性。

## Scenario 3 — Algorithm Optimization (P1)
输入：明确目标函数、约束和测试集。
任务：基线、假设、候选代码、正确性验证、性能比较、未见输入验证。
评价：正确性、目标值、时间、内存、可复现。

## Scenario 4 — Software Engineering (P1 extension)
输入：固定 commit、Issue、环境、测试。
任务：复现、根因、修复、测试、回归和审查。
评价：fail-to-pass、pass-to-pass、隐藏测试、安全、修改相关性。

## Scenario 5 — IT Operations (P1 extension)
输入：可重置服务环境、日志/指标/Trace。
任务：告警关联、根因假设、模拟修复、健康检查、复盘。
评价：根因准确、恢复成功、误操作率、证据覆盖、MTTR 模拟。

## Customer Service / Financial Risk
P2 扩展，不做真实退款、真实资金、真实理赔或真实客户系统操作。只使用合成/许可数据和模拟环境。
