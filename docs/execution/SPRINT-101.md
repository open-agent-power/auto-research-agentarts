# S101：严格质量材料采纳接入工作台

新增显式 Workbench Python/HTTP 入口，将 S100 的登记材料及原回答引用严格采纳接到原有三层工作台。新 manager intent 与 Host v4 同时绑定 manager 身份、原 prepare selector、冻结材料、原反馈/计划，并由 Project 事务 claim 绑定完整 Host intent；保留锁序、预算、旧接口及原 ID 恢复。直接 Host/Project 抢先或原管理意图丢失不能被归功于当前 manager；回执仅在原三层凭据完整时补回。HTTP输出有界状态，不额外输出 prompt/回复/nonce/材料正文。

作者最终新旧合同52/52、独立复验36/36、另一独立相关回归65/65，进程exit 0；覆盖HTTP、直接Host/Project抢先、管理意图重建、双进程同ID、原资料漂移与四个模拟中断窗口。源码一致，测试SHA `a37371d5315d49f0070c4af8eb1ee7e84c644098d76113f919fbc2ebf05d51bd`；相关日志 `runs/s101-related-regression/unittest.log` SHA `c927b77b113a482297a0f4122367184d91508441c0a75e591ed38350e533b222`。独审一次输出丢失，未计入通过，保存日志后重跑；合同曾把三层四窗口误写四层，已修。

仅隔离合成和人工回复，故障注入不代表本版本实际SIGKILL或断电；信任本地进程，未证明OS隔离、模型实际收到/理解材料或科研收益。无新增真实模型/API/研究、原预算与pin不变。下一步可对严格三层固定提交窗口进行实际进程终止与不同PID原ID恢复验证。
