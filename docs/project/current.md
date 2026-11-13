# 当前接续

## 当前结果

经用户批准的可信本地G1切片已完成技术验收。原G0资源隔离及上游runtime仍未通过；用户已接受当前环境限制，新的G2-L/G3-L/G5-L可信本地轮次开始。只有只读工作台服务，没有无人值守模型研究或定时任务。

## 本轮已完成

- 研究源码冻结提交`5d36424`，项目`project-431366b59dac432dabb315d82dee6eae`，原生manager在`runs/cloud-concrete-local-20261113-01/manager`。
- 完整1030行/427配合比签名组，两轮固定Ridge：MAE8.383388→5.702073MPa；313行/129组恶化，负预测0→1。计划v1→真实反馈v2→v3收束，原wait状态32。
- 预算5/6本地工具、20/20estimator尝试（10Scaler+10Ridge）、1/1来源提取、0产品模型/API；无unknown或fit预留。不能通过新ID/目录重置额度。
- 冻结独立验算3252项通过。原位置29请求重放/11检查通过，96原文件字节不变；新路径数学3252项及29请求/18检查通过，101恢复文件与原预算不变，重放禁止访问旧case。
- 原生报告4附件、39页PDF、完整来源/SQLite/工件和派生图保存。五页桌面及390px代表页实际检查，下载SHA匹配；PDF仅首页末页视觉检查，未声称全部页面或真人评价。

## 接续入口

[结果与限制](../execution/g1-local/results.md) · [验收JSON](../execution/g1-local/acceptance.json) · [独立审查](../execution/g1-local/independent-review.md) · [界面](../execution/g1-local/ui-verification.md) · [复现/恢复](../execution/g1-local/reproduction.md) · [本轮复盘](../execution/SPRINT-002.md)。

原始公开数据：`/workspace/work/g0-data-research/`；独立证据：`runs/g1-local-verification/`、`runs/g1-local-review/`、`runs/g1-local-ui/`；新路径恢复：`runs/g1-local-restored/`。只读工作台在云电脑`http://127.0.0.1:18830/`，模型/写操作关闭。

## 已完成交付

复现归档`runs/g1-local-delivery/concrete-reproduction.zip`已生成，约19.5MB/280条目，包含完整Git bundle、原/恢复case、公开数据/许可、独立检查、界面与图表，ZIP CRC与每文件SHA全核验；[清单](../execution/g1-local/delivery-manifest.json)保留身份。新Worker[主机接入/验收包](../../deploy/worker/README.md)及无副作用封装已准备并通过语法/帮助/已存在目录拒绝检查，未发生远程部署或采购。

## 当前Sprint 003结果与下一轮

用户明确接受缺失隔离Worker并要求继续，[授权边界](../execution/local-continuation.json)保持。已完成[本轮报告](../execution/SPRINT-003.md)与对应独立审查/验收；G0原问题不再逐阶段重复询问。

- G2-L任务DAG/恢复模块16测试、独立115检查通过；真实保存证据4任务×3组织×3轮没有并发收益，继续single默认。无LLM transport或自动科研多Agent收益声明。
- G3-L两新目标完成三版原生计划、真实来源/经验导入/报告与独立恢复。RealEstate414行MAE6.425093→6.287279(2.14%)，179行/107组恶化；Slump103行MAE2.257092MPa，无age明确拒绝变换。新增累计30/40estimator、8数值工具/2来源/0产品模型；旧Concrete20fit保持。
- G3原/新路径各1416+202算术检查，原47+41/新49+43请求恢复检查通过；原RE101/Slump90文件及旧Concrete101文件字节保持。研究源码冻结`0ceb274`，后续host driver需固定该commit，不篡改freeze或upgrade旧case。
- G5-L SciFact检索保留BM25早排改善与Recall5/20下降；明示合成调度工程优化。独立60检查，尚未原生RAG接线。G6-L离线wheel安装/资源核对通过，继承已有依赖，不称完整干净安装或runtime。

证据在`runs/g2-local-comparison-20261113-02`、`runs/g3-local-transfer-20261113-01`、`runs/g3-local-verification`、`runs/g3-local-restored`、`runs/g5-local-cpu-20261113-01`及`work/g6-local-release-20261113-01`。原始公开数据/许可`/workspace/work/g3-data`，参考库`/workspace/references/upstream`保持。

下一轮root集成G4-L代码候选；research_task实现固定纯计算能力解释器/协议，resource_audit实现评测器，repo_audit与independent_review独立审查，upstream_audit补G3派生图。仅独立worktree修改真实分组编码纯helper，0研究fit/API；先冻结/审查再执行单候选，可reject/inconclusive。不自动晋级生产，不迁移旧研究项目，不声称sealed或多代RSI。

每轮完成后验证并直接推送main、说明改动/实测/限制，再继续可独立任务。不会创建无人值守定时任务、采购服务或发送产品模型API。
