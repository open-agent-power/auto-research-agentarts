# S047：一次授权后原生推进到报告

继续S046后的实际产品开发，复用原6人团队；没有增开代理或重开原研究。用户已授权持续实现/普通推main，本里程碑后继续S048，不释放工作租约等待定时。

新增Workbench `continue_staged` 和保存记录GET：从原已完成staged primary+事前holdout出发，固定saved audit→validation策略冻结→原预算一次final→原报告export。五字段exact body、唯一阶段子ID、每步派发前原body/context再核、预算不足/unknown/跨pin/其他manager意图阻断，已有唯一完整阶段可复用。未知只保留原ID，不通过新顶层请求重算。完整[合同](../staged-evaluation-continuation.md)。

纯helper只读核原SQLite指纹、原Controller parent/child、source/plan/工件和顺序，不另建journal或执行引擎；helper字节纳入Project core identity，未完成grant同时pin原helper/manager/Controller。S046 core6a5c9e47…保持原source4a159a9，不由新代码迁移。

## 实际验证

189源文件由每writer明确交回后冻结，root相关101/101、独立19/19通过，执行前后源SHA均不变。独立工程HTTP使用真实server进程：第一进程完成3原tools，停进程后新进程同body/同ID GET+POST返回原记录；原SQLite/完整manager-tree/预算/3行动ID/4报告SHA均不变，private query canary未在被检查表面泄露。这是产品持久编排与恢复证据，不是新科学收益。

原生合成项目`project-c5682fa38a224e709603c0f7948673b1`，预算3/3工具、0model/fit；原研究目录未触碰。精确源码SHA/命令/日志及独审见[验证索引](g5-local/staged-continuation-verification.json)，持久工程目录在runs/s047-verification/http-restart-01。

## 失败和仍有的边界

初版待派发body只信保存recordSHA、completed重放未核报告两项已修并有负例。测试HTTP最初因mock递归5秒超时，cleanup随后删临时fixture导致目录缺失；不计作产品通过，转录及工具记录保留。修正后作者HTTP0.853s、独立真实重启已验。

如果报告文件已完成但原manager receipt缺失，沿现有export限制停在原请求，不重新导出/换目录，也不能自动收敛；此缺口明确保留。无新UI表单、native Linux模型transport或长期自主研究收益声明。S048继续把staged负结果作为可追溯历史案例接入现有ResearchMemory；其独立staging首版正修两处审查发现，未计入本S047完成能力。
