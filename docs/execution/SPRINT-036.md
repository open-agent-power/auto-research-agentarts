# Sprint036：把具体失败查询提供给后续计划

S035的反馈模型只拿到汇总，独审要求的“正例b未在两份空排名中出现”当时没有供应。这里沿现有明确选入保存材料的v3接口补这一缺口：选择原行动、结果SHA、划分及不利查询ID，新计划context就包含原标注、两臂排名ID和指标。原文不供应，不暗示模型读过查询或文档。

源码 **b2e05f80a76780834077a52fde58d20db4f5a27c**，clean pin `/workspace/work/saved-retrieval-materials-source-b2e05f8`；[接口](../host-model-selection.md#明确供应保存的不利检索查询)／[精确验证](g5-local/saved-retrieval-plan-materials-verification.json)。最多4条指定不利查询，完整context仍64KiB，超限整次失败；原OOF选择和旧冻结v2/v3提示保持。新selector暂只供plan，recipe明确拒绝，报告列身份摘要；没有新网页选择控件。

实现34项相关检查通过，其中6项新fixture；独审另跑6项和旧OOF/relevance合成检查，不把重叠项目相加称独有数量。独立验收核原pilot20项、旧pin4项、合成Host6项/容量2项及原ArguAna只读14项；验证了原qv正例b、两空排名/零分、旧提示字节、同ID回放/冲突和完整context freshness。真实relevance样本grade1、没有缺失正例；grade2及缺失正例只由独立合成夹具覆盖。6个冻结Git blob与验收字节相同，pin clean。

原pilot41文件/全路径和ArguAna全树不变，state11、2行动、baseline v1/proposed与3/2已用额度不改。新代码正确保留旧项目CODE_CHANGED门禁；不升级/替换其生产者，不使旧计划自动采纳。reader会读冻结来源并核保存算术，不能说没有计算；所列守卫下没有新排名、评分、fit、模型或Host调用，导入前bootstrap范围unknown。原工件的身份和完整context核对不是数值独立真实性或科学验证。

本轮没有追加研究模型来验证修复后的计划质量，不能宣称模型已经看见这些新材料或研究变好。下一步继续S037，把这个冻结源码构建成新wheel和独立安装环境，保留所有旧成品与源pin。
