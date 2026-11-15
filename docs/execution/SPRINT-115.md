# S115：staged 已知反馈的严格后端首片

新增显式manager→Controller策略入口，仅接同源码版本下已完成且原S111登记/claim、S112 primary parent/child claims、source/SQL/canonical工件完整认证的v2反馈。仅 condition_met/not_met 已知值可决策；所有 unknown、未开始primary、凭据或工件损坏均停查，不伪装成可信wait，也不声称一般 unknown wait 已支持。当前计划不同于登记时的计划按策略安全等待或拒绝，不伪造历史。

writer内依原登记分支和真实上下文决定：wait 的parent+claim同事务、无child/额外工具；已知audit须原唯一候选/结果及额度符合，parent+claim与首次child+claim分别事务绑定，仅首次创建者派发。audit最多1额外工具，读取已保存dev/validation和共享源，不新rank/score/fit/model/final；预算不足时可因候选不可用而wait，保留实际rationale，不改原登记分支。旧入口/跨ID在marked未决时拒绝；终态原body/claims/SQL/工件复核后仅补原manager回执，不重派。Project、manager和child非同一跨库事务，非OS隔离。新源码下须先新建合成登记和primary；旧pin原登记不自动迁移。

作者52/52，独审52/52、另51/51，exit0；额外独审3/3验证wait parent claim及audit child claim失败同事务回滚、wait重放遇派生child orphan replay两方向拒绝。已知met/not_met合成audit各1工具、已知wait及额度不足wait 0额外工具；S063事前holdout→audit→freeze合成通过，未执行final。child已接受后上游SQL漂移保留running和1 reserved、adapter 0调用。原WIP audit终态错误传参使合成行动完成后EVIDENCE_CHANGED，修复并保留 `runs/s115-verification/initial-tests.log`、`audit-debug.log`。S115中断/抢占当前为函数注入，旧S112部分含新进程回放，不声称S115多进程竞争或SIGKILL；本轮未接UI、真实研究或模型。
