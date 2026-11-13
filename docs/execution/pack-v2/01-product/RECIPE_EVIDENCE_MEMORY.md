# Research Recipe, Evidence and Memory

## Recipe 必备字段
recipe_id/version；适用问题类型；适用条件；必需材料；输入 Schema；步骤；评价协议；资源估计；失败模式；结果分支；证据要求；限制；来源和审查状态。

## 方法选择
1. 程序确定性门禁：数据类型、字段映射、材料、权限、预算、协议版本、工具可用性。
2. 智能建议：在合格方法中比较适用性、信息价值、成本和风险。
3. 控制器验证并执行；模型不能绕过硬门禁或修改累计预算。

## Evidence 类型
- source_evidence：论文、数据说明、官方文档、原始文件；
- data_evidence：数据快照、字段映射、质量报告；
- execution_evidence：命令、工具、Worker 回执；
- analysis_evidence：统计、模型、计算结果；
- review_evidence：独立审查和领域意见；
- interpretation：模型或研究者解释，不自动升级为事实。

每条证据保存来源、版本、定位、哈希、时间、许可、适用范围和引用关系。

## Research Memory
复用现有 ResearchMemory 的 scope/provenance/revocation 能力。区分观察记忆、方法记忆、决策记忆、失败记忆、经验候选。跨课题使用前检查任务相似性、数据身份、评价协议和领域语义。检索只产生候选，不等于验证。

## 经验迁移验收
同一条经验在源课题和目标课题都保存条件；目标课题重新验证；记录正迁移、无影响和负迁移；不能仅凭语义相似度自动推广。
