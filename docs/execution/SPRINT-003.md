# Sprint 003 — bounded local continuation

用户接受无法补充隔离Worker，并要求按项目计划继续；[决定](local-continuation.json)记录新可信本地范围，原G0资源问题保持事实，不作为重复询问点。本轮完成G2-L协调模块及实际无收益对照、G3-L两新目标原生闭环、G5-L两类CPU基准和G6-L离线打包切片。完整原Gate与局部结果分别记录。

| 工作 | 实际结果 | 验证与决定 |
|---|---|---|
| G2-L可信分析任务协调 | 固定ProjectRef、DAG、claim、unknown/晚到结果与attempt/result绑定协调；不改科研预算 | 16测试、独立115检查；同4任务×3组织×3轮输出完全相同；single54.54ms/static57.27ms/dynamic56.15ms，无并发收益，保留single |
| G3-L Real Estate | 414行/259代理组，raw MAE6.425093→log1p房龄(年)6.287279，约2.14%改善 | 179行/107组恶化；原/新路径各1416算术、47/49重放检查；20estimator/5工具/1来源 |
| G3-L Slump | 103行/103配料组，baseline MAE2.257092MPa，均值参考6.231186；无age明确拒绝迁移 | 原/新路径各202算术、41/43重放检查；10estimator/3工具/1来源，不消耗剩余10fit |
| G5-L真实文献引用检索 | SciFact固定300测试查询，BM25 nDCG@10 .66046 vsTFIDF .63291 | Recall@5/20下降，负结果保留，不默认替换；独立复算属于60项G5检查 |
| G5-L合成加权区间调度 | 两exact DP同目标/同schedule；4096区间中位约107倍 | 相对朴素扫描DP的已知工程优化；32correctness、12case×3计时，独立参考最优值核对；非新算法或科研发现 |
| G6-L离线wheel | 172源码/资源逐字节核对、新venv安装、帮助/导入/资源读取 | 6命令exit0、175源文件/101旧Concrete文件保持；继承已有依赖，非完整干净依赖安装 |

程序产品模型/API发送0；G3实际新增30estimator尝试，总上限40，原Concrete20fit保持。开发Agent tokens、基础设施与货币成本未知。公开资料下载与程序模型/API调用分别统计。

[独立审查](SPRINT-003-review.md)、[G2结果](g2-local/results.md)、[G3结果](g3-local/results.md)/[验收](g3-local/acceptance.json)、[G5结果](g5-local/results.md)、[G6打包](g6-local/results.md)提供可复核入口。研究冻结代码提交`0ceb274`，后续结果提交不会回写freeze。G3同ID重放、迁移恢复及所有原文件字节校验通过；历史Concrete101文件/20fit也保护。

失败保留：G2首次warmup把“含坏行组233”误当“组MAE恶化129”，在实际臂执行前停止；修正定义并换新attempt，原失败保留。G2独立审查修复迟到审批错套新attempt及状态读不一致两项竞态。G3初次重放验收helper对原生省略`reused=False`元数据误判；只规范这一缺省false与replayed标记后通过，未改产品/evaluator，失败与旧helper保留。

局限：G3候选与适用性是预先策划的source启发实验，无no-memory决策臂，不能归因记忆收益。房龄年与Concrete龄期天不是物理或单位不变迁移；代理组不等于独立属性/试件。Slump与源有一组配料数值重叠，是语义负控而非完全独立正迁移。G2无模型Agent传输/真实科研协作收益；G5尚未接原生RAG工作台；G6未完整runtime/干净依赖/正式版本发布。原隔离、上游runtime与sealed/multigeneration RSI未通过。

下一轮继续G4-L有界代码候选：已选择真实分组编码效率假设，先完成并独立审查纯计算能力执行器与冻结评测，再单个独立worktree候选；允许拒绝或无结论，不改旧研究ledger或自动晋级生产。当前[方案](g4-local/next-step.md)是接续，不冒充已经运行的代码RSI。
