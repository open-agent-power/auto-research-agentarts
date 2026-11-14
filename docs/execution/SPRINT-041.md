# Sprint041：下一项自主决策能力，设计已审未实现

下一优先项是事前登记可检验的预期和分支，读取后来真实行动并将condition_met/condition_not_met/unknown放进下一选择context，复用原Controller候选/预算。源码诊断和v2机器合同已独审，[精确入口](g5-local/hypothesis-feedback-design.json)；本轮没有产品实现或研究运行。

v1把空排名当unknown的设计负例保留；v2修为合法已计算0是已知值，按事前gt/gte等比较符决定，失败原因未知另列。现有adapter已保存且可能反馈test，不能声称盲测；新的最终测试协议须在策略冻结后单次评价，不改旧case或评价器。
