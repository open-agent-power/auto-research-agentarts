# S059：事前双指标条件，避免只看覆盖率继续实验

Status: fixed verified，代码/HTTP/恢复已验证，不认领科研收益。

S054真实结果暴露“覆盖改善、排名质量下降”的取舍。保持S054协议、最终结果和已用满预算；新能力仅对以后新登记的staged开发/验证primary生效，不能事后重写旧假设。复用原ResearchProject/Controller/Workbench、已保存配对指标核验及S052条件续作。

显式opt-in hypothesis新增conditions恰两项不同指标，各为{metric,operator,threshold}，不得混原scalar字段。只staged，注册v2；归一化condition:{all:[两个validation candidate-minus-baseline谓词]}。反馈context-v2中该item value为同序两真实值，任一不可用则整体unknown/value/action/result为None，未知始终等待。一次原primary完整核验、同一保存summary取两指标。原scalar注册/context-v1及prompt保持，不混family；混合新旧staged记录时明确采用context-v2。

本门只决定显式原条件路径audit或wait；不改变原freeze的Recall@20选择规则、不自动采用研究计划，也不强制所有低层API遵循新门。无任意表达式/重新排名/读取final数据/新模型许可。

root负责真实HTTP、跨进程原body恢复及原件保护；engineering实现；capability_review未参与实现，负责独立探针。三人复用、没有新增agent。专业方法沿用项目router/backend/interfaces/evaluation和已核的保存IR指标/JSON-SQLite事务，不新增通用runtime。合成fixture专门选择分支覆盖，不计科研收益。

最终源191文件/core a05f668cb8de230b134ab4e0394c17297b7aa5cd026c378172bce2001325b4b5，manifest SHA4903d279ad6a31045de7b1ec4090cdd29cc67dbfa73c501e050d075d853c98dd。作者8项/root49相关/独审6纯机制通过，独审另只读核root3个实际HTTP案例的源/SQL/父子/事前登记/两保存值与原回执。

真实合成数据实际运行：R20+1/MRR0满足→原audit/freeze/final/report、3工具；R20+.5/MRR−.04444444444444445→不满足/等待、仅primary1工具；未primary→unknown等待、0工具。root三组新进程HTTP原body重放响应完全相同、原状态/预算/公开文件不变；private/重排/评分/step/resume/recover哨兵通过，独审只核回执未重复执行。audit分支被授权final/report可读合成private，不泛称该分支零private I/O。

初版登记检查对旧v1也用了canonical，独审前自查识别兼容语义微差；保留初191源/manifest/test，最终仅v2 canonical，v1恢复原比较。root初HTTP夹具source与workspace未分离被正确拒绝，尚无action；初runner/log/目录保留，修夹具后另建明确工程验证目录，不是重置科研。

原S054真实标量feedback/notice/state/budget，用72b旧pin与本次新reader两个进程输出逐字节一致，仍原v1 +.01/met，未事后加联合假设。原S04636/S05017/S05447文件全相同。新科研行动/模型/fit为0，工程夹具计数分列、开发token/费用unknown。

[精确源与验证](g5-local/conjunctive-validation-verification.json)；[使用合同](../hypothesis-feedback.md#显式双指标联合条件s059)。通过后继续S060只读真实validation配对胜负/单题影响分析，不改原实验或读取final。
