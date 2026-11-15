# S099：把登记的质量反馈供给研究计划

背景：Host 计划上下文原有质量行动 observation，但不含事前登记条件及原 reader 的三态结果。事后由宿主附加质量引用不证明这些条件已提供给模型。

实现：显式 plan-only saved_materials selector 绑定原 registration ID/SHA；投影有界条件和原 reader 反馈，并固定完整 Host context/prompt。按原来源、Project、代码、原行动/SQL及工件的可用检查拒绝漂移；原计划变化时拒绝供应。Controller 未完成类 unknown 仅是 reader 当前阶段的报告，不证明行动未发生或未读取的证据已经认证。已知 evaluation 与封存的原 quality profile 纯重算一致；这不替代原工件认证。旧无 selector 行为不变、recipe 拒绝，新材料不复制原始行及异常 token；原有 feedback 本身仍可能包含已保存示例。条件列名属不可信数据。材料不授予执行许可。

验证：作者最终隔离合成 14/14、旧合同 58/58，独立 reviewer 新进程 38/38，均 exit 0；此前中间版本误把计划漂移和 SQL/工件篡改的组合供应为 unknown，两个失败保留 `runs/s099-quality-materials/plan-drift-before-fix.log`，SHA256 `1224efef033e101a15bb6cf1d1e18cc2c7c97394c32250b06c56d35cc5627956`。独审还发现离线逐项结果缺 profile 交叉核对，已修并测试。测试文件 SHA256 `226c9e760b5ecdd68da4a1393598e1539662c1ddefa77a6b624367f652a73a58`。另有未修订版 101/101 回归不能当作最终版验证。

范围：无新增真实研究、真实模型/API 或预算；合成准备和原生工具另计。完整 context/prompt 已保存不证明实际送达、模型理解或科研收益。旧 Bike 项目和 pin 不改。下一步审视材料、原回答引用及采纳是否能严格绑定同一登记，仍不假称模型能力。

最终版本另由工程成员复跑旧Host、Workbench及相关材料 71/71，exit 0，日志 `runs/s099-related-regression/fixed-unittest.log` SHA256 `e2438025f6d9f243e8469f28252c3598ebccf86a6d543b40665e5054fbb59228`；全包源码前后清单相同。工程资源不按零计。
