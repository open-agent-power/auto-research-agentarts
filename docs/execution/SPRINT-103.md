# S103：核对计划陈述与质量反馈

现有 LocalWorkbench `check_plan_fact` / HTTP POST 增显式质量声明分支：操作者选择原回复的精确 Unicode span、原登记 ID/SHA 以及 overall outcome、条件 outcome 或逐项 actual/expected，比较冻结 Host context 中原质量材料；旧比较格式保持。结果只评价操作者声明的映射和选中片段：supported、contradicted、undetermined；已知0不混unknown，字面unknown可支持但不意味着行动没发生，整体unknown下已知单项仍可单独比较。不会自动采用、执行、扩额或重跑。

目标原 response/context/prompt/proposal 必须存在并通过捕获和原回复解析；新分支用当前reader从原context再生prompt并精确比较。当前reader规则变化可能使历史记录保守拒绝；这是协作本地一致性，不是签名/历史producer认证或对可重写所有本地文件者的防护。只验证封存材料，不重验当前source/SQL/工件；选中条件可能包含敏感列名，原CSV/profile/样例不进入新结果；capture可创建协作锁文件。

作者修后相关50/50、独审50/50，另一独立复验20/20，exit 0；含HTTP、0/unknown、四原件、原响应篡改、旧wire及后续计划。修前同步篡改ledger与prompt文件的实际失败保留 `runs/s103-engineering/resealed-before-fix.log` SHA `89f2412c2c4f4f169a4073f3a23d2cb6b27fa91ade855d7bf71c823cb1d02fa5`；修后相关日志 `runs/s103-engineering/fixed-unittest.log` SHA `62f3799ebc757adce49cb2cca0cc51bcb8830d423fda56629fa4d65f1695fcbe`。独审20项运行期间负责人更新文档，源码/测试固定、文档测试后单独核。无真实模型/API/研究或预算增加；手写合成回复不能证明真实模型犯错、理解或科研收益。
