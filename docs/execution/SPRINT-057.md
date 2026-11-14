# S057：把保存的 staged 查询证据供给计划上下文

S056让人和工具可查原query/排名，本轮沿原saved_materials→v3 plan→Host封存→报告接入显式新kind。完整rank/qrel/metrics与原query、每臂top3文档节选具有明确coverage和截断标记；不把全部文本自动放入上下文。跨新旧kind共同4选择器、完整64KiB上限保持，旧default/旧检索prompt与7c pin逐字相同；recipe两个入口和selection拒绝材料，Host报告/Markdown/PDF只身份定位不复制正文。

真实S054原源仅只读材料化：新v3原生校验28,513字节，reader一次、20+20排名、3+3节选；原47文件/状态/3预算不变。旧producer300421仍CODE_CHANGED，未Host prepare、写计划、发模型或迁移pin。该检查不是实际模型决策。

初版离线validator用dict相等使合同布尔true被数字1冒充，已独立复现；保存初版191源码快照/manifest及失败日志后，改用canonical严格比较并以同一负例复验。源freeze fixed SHA `c8aad6c4e1b017db881a70f7f530c26735146cd1d1437e25a7f5fb2e371747f5`，新core `e05a7272f675625c6972e71ab3d2702f3c7adfc34cdd5cd3450d3b96bd64e7d5`。

root最终59相关、独审5项新增通过；初版10项实际包含5新+5既有S056误收集，不作10个新样本。测试覆盖真实格式、去重/四项/超限、错误身份/等级/排名/节选类型、recipe双拒绝、合成Host原ID封存/重放及实际Markdown/PDF材料行不泄正文。无需真实模型/新研究；工程总dispatch未单独计，token/费用unknown。

[精确源/预算/验证与限制](g5-local/staged-plan-material-verification.json)、[使用合同](../host-model-selection.md#staged开发验证查询材料)。原件在ignored `runs/s057-verification/` 和 `runs/s057-review/`；源端binding校验不等于离线文本真实性/OS隔离、模型运行时或科研收益。下一主线实际模型接线仍受既有0模型边界及S050一次新调用待答复约束；继续S058可用原件归档交付，不追加研究或凭据。
