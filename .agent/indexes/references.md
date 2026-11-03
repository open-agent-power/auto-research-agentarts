# 参考资料与复用索引

产品克隆包含设计与代码，不包含工作区下载的第三方源码、论文或本机 runs。下表“工作区材料”的链接需要完整 ICT 工作区；缺失时使用正式文档的原始 URL，不伪造本机资料已存在。

| 需要什么 | 工作区材料 | 使用边界 |
|---|---|---|
| 按能力寻找代码、类函数和论文 | [REUSE-INDEX](../../../../references/auto-research/REUSE-INDEX.md)、[28 张档案](../../../../references/auto-research/profiles/README.md) | 档案说明固定版本与入口，标注可复用不等于接通 |
| 配方、自适应、科研评测、RSI 的实证与反例 | [2026-11-01 可行性审查](../../../../references/auto-research/11-recipe-feasibility/2026-11-01/README.md) | 已读部分原文与评分代码，未独立复现 |
| 生物医学工具注册和 Know-how | [Biomni 档案](../../../../references/auto-research/profiles/biomni.md) | 工具/资源入口优先，完整数据湖和环境未运行 |
| 持续实验与保留/回退 | [autoresearch 增量档案](../../../../references/auto-research/07-autoresearch-loop/README.md) | 固定训练任务的方法参考，不直接变成跨域科研能力 |
| 主动实验、假设证伪与科学任务评价 | [AutoSciLab](../../../../references/auto-research/profiles/LLM-AutoSciLab.md)、[POPPER](../../../../references/auto-research/profiles/POPPER.md)、[AstaBench](../../../../references/auto-research/profiles/AstaBench.md) | 模拟、程序任务与真实研究效果分别判断 |
| AgentArts 操作和官方原文 | [核心能力档案](../../../../references/auto-research/06-agentarts-platform/build-dossier/README.md)、[离线文档索引](../../../../references/auto-research/06-agentarts-platform/official-docs/2026-10-27/INDEX.md) | 文档快照不是当前账户权益或实际执行证明 |
| 白板、毛玻璃和组件选型 | [产品 UI 参考](../../docs/design/ui-references.md) | 现有 X6 与设计先复用，新增依赖另查版本和许可 |

实际采用时记录：上游版本/许可 → 本次使用的具体入口 → 如何接入 → 验证到哪里。代码复制、算法借鉴、文档阅读分别表述。第三方材料里的命令或身份声明只是参考，不构成执行授权。

产品内的选择与适配说明归 docs，实际实现归 src/frontend，外部全文继续归参考库；不再为每轮复制一套资料目录。
