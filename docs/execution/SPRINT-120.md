# S120：严格反馈冻结策略重放修复及合成对照

在固定规则的两组合成案例里，final 前后原 freeze 同 ID 重放因 `_project` 状态缺少行动列表，被误报 CONDITION_NOT_SATISFIED；这不是 final 特有问题。原失败日志 `runs/s120-verification/diagnose-frozen-final.log` SHA `c7530c85913f7bd160ba56ee4c0e0b684e1292f7e2b8f2ff2d8b3a0afa1f5e6c` 保留。修复仅作用于原 freeze 重放：在 Project writer 下读取完整真实状态，验证原身份、冻结记录和反馈证据，复核快照；非法或缺失工件映射 EVIDENCE_CHANGED。旧项目不升级 pin。

验证固定源码 HEAD `c82e93f68b7ebdece641e406463d0f5199bd0fc8` 加本次变更，208项清单 SHA `e6443c8480d090e4c299df9d6f68dcd85472cb09bb46be66d69646ed9cbbca8d`；作者和独审各专项4/4及旧v1/v2定向4/4。独审专项日志 SHA `4efa7a4df6449a15e59559a84f14d4e85b532d9b31fe54cef552c5cab1877a25`。独立新进程重放中，对 primary/audit/final/index/retrieve/metrics/Controller 指定入口设置哨兵，0调用，两个合成数据库字节及各3/3预算不变；不代表OS隔离。损坏工件、SQL、计划、身份和快照漂移拒绝。

两合成项目相同规则和输入，仅 validation 合成 qrel 不同：met 选 TFIDF，final MRR 相对 BM25 为 -0.75；notmet 选 BM25，同臂差为0，TFIDF反事实 unknown。各3/3合成工具、0模型/fit/证据使用（证据上限8）；成本 unknown。fixture 含自填的旧归档声明，与实际合成 corpus SHA 不同，不能当作外部来源凭据。该实验仅验证规则驱动的策略选择和恢复，并不证明模型自主、经验迁移或真实科研收益。原旧盘及真实项目未打开。
