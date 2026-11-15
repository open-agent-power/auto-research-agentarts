# S085：质量行动的结构化计划引用

Project Python 可从原质量登记和已完成的原行动派生 `quality_feedback_ref`，并在原 Project writer 锁内保存原计划的直接后继。引用绑定同项目原登记、原计划、Controller parent/child、行动/result、反馈和source身份；写入及同ID重放时重新核原SQL指纹、工件、代码和顺序。已知 met/not_met 可引用，unknown 不可伪装为已知。调用者自由文本和自给profile不替代原件。

作者专项8/8、相关七模块64/64合成通过；独审专项8/8、旧计划/selection 21/21通过。独审发现工件认证到写入间仅看项目快照不能检测源码漂移，作者增加原加载代码/producer/controller末尾重核与中途漂移测试。测试使用隔离合成项目，不是新真实研究或模型/fit收益；未证明断电恢复。

范围：selection context 只校引用形状，不代表每次已重验原件；原 Controller 质量策略因计划改变仍等待，尚不消费plan v2；Workbench 在写入意图前拒绝该新字段。下一步独立显式策略需对真实当前最新plan v2和原件重认证，不能用历史计划视图派发，再单独接入Workbench。旧plan wire、旧项目和Bike 2/2预算保持，原pin不升级。成本/token unknown，非OS隔离或科学有效性证明。
