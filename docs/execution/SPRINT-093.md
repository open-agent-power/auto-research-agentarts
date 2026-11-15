# S093：已保存反馈请求的保守历史核对

隔离合成真实 manager→Controller→primary→反馈链复现：合法 manager `advance_feedback` 会在 core 保存 `controller.advance_selection`；旧 saved history 将两者命令名直接比较，错误标成 `integrity_error`，即使原manager双摘要与原请求一致。修前合成原件与日志 `runs/workbench-unknown-probe/feedback-handoff-v2.log` 保留，无真实网络/模型/研究。

新只读核对对同Project真实保存的有限登记集合构造精确候选，要求manager行摘要与原intent摘要唯一匹配，并在绑定的原登记/parent/封存context、原plan/source/code和时序约束下对照当前reader计算的proposal；不从rationale猜测ID，不以当前新context替代原context。明确摘要/身份/时序矛盾仍 `integrity_error`；缺原件、多义或原producer不一致保持partial/unavailable。即使磁盘producer与当前计算相符，也不能证明进程已加载函数来自原producer，因此仅标 `partial`、`semantic_match=current_reader_matched`、`producer_verified=false`；不披露body、不授权恢复或派发。旧 advance/recipe 投影和旧项目原pin不升级。

作者及独审分别运行25/25合成专项和旧stored history/summary/readonly回归，覆盖原context与当前不同、双摘要/登记/时间/封存漂移、缺失与重复、旧producer不同及默认不含body；未见新阻断。独审发现先前“不同producer恰好输出相同”可能误标available，以及磁盘identity无法证明已加载代码，作者改为producer不同时不编译、当前匹配也仍partial并补负例。纯读取不代表物理证据完整、OS隔离、科学判断或真实断电恢复；本轮无新真实研究/模型/fit，费用/token unknown。
