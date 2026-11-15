# S066：真实Hotpot反馈与负结果进入经验

原S065独立研究完成并经独审后，将该真实已完成case经S064 v2经验只读捕获，保留原事前3条件/validation反馈、原audit与TFIDF选臂、final R20 .91→.92但MRR .865984→.830095及nDCG下降。原42文件/claim/state/3工具预算相同；没有重跑排名、评分、fit或模型。

本地bundle 1,180,183B（含尾LF）SHA `67deff921b5a42c28d075ec84129fce6df199aa3f7d5f50ae671b42d75f3d4b2`；实际导入canonical无尾LF为1,180,182B/SHA `4ff88cb1fb5c365b9cd333f9dd56035d7d2cc366b2df98a2a6ddf8ded4a7712a`。两者明确不同字节，不是冲突。原case `s065-hotpot-support-history` 在原生Memory/目标工程Project成功绑定并供计划context/prompt；目标原生tool limit=1、used=0，model/fit/evidence used=0，不伪称上限为0。原ID导入重放由作者完成，独审仅核其回执；独审另对作者Memory的独立副本重复导入两次，inserted均0、仍一条案例/一source版本，原Memory不变。

独审核原SQLite/三行动/登记/audit/freeze/final聚合与导出case、目标计划/预算一致。捕获读取已完成真实final行动工件；单独canary阶段与全42文件hash在guard外实际读private selection/holdout/字节。独审在五个输出中核100 final qid/hash/题文/base64共4组canary未命中，仅为精确字符串范围而非普遍无泄漏证明。导出bundle和计划原context仅本地；离线原策略与最终聚合的归属需回源，自hash不是签名。执行入口/索引/排名/评分/模型被拦；未单独patch sklearn.fit，已执行只读路径未fit，不夸大哨兵范围。

独审三次初稿分别误解inventory mode、嵌套context SHA及目标association投影，属审查脚本失败，原日志保留，修正后通过；root曾重复尝试已发布S065 commit，Git返回nothing to commit，无重复提交并留记录。此案例可供计划参考，但没有模型实际采用或证明迁移收益，也不解锁旧预算。[精确证据](g5-local/hotpot-feedback-experience-verification.json)。

待发布aggregate本身经独审与S066原件/双SHA/预算核对，100 final qid/hash/题文/base64及200正例doc ID/正文/base64精确canary未命中，SHA08dd897627bb9856ec5ea13c679fb01a320a970ab2f93257eabbbc0490bbefa5；本次实际读取original private selection/holdout和corpus，有限canary不证明完全无泄漏。

验证JSON的 `verified_pending_publication` 是公开canary前的历史状态；本提交将该已独审聚合纳入Git，完整经验包/目标上下文仍只留本地。
