# 本轮开发组织与能力

本轮为用户再次授权后的**持续执行阶段**。三小时任务用于对齐和汇报；执行窗口内继续实现、验证和必要独审，不以一个增量结束作为自动停止依据，也不声称会话结束后有常驻模型。

## 工作区与所有权

源基线 `ea3d92e9ebb194262170a4cc56bb0cb838a97b04`，origin 为 `open-agent-power/auto-research-agentarts`。新 checkout 在 `/workspace/development-continuation-20261114/auto-research-agentarts`。原 `/workspace/auto-research-agentarts`、参考原盘、S041 v2合同和历史 runs 不可见；这是源码续作，绝非历史研究恢复。原全局执行者/lease状态unknown；仅此新工作树使用project_autonomy_guard.py，本轮独有owner root-g5-continuation-20261115T0744，写/执行/提交前heartbeat，结束release。永久科研study claim与开发lease分离，不随release删除。

宿主并发上限7，用户默认总池≤10。本轮只复用root与以下两位既有成员，没有新建代理。其他可见旧成员不等于正在执行，使用前先核可调用与实际状态；不为换模型重建成员。

| 实际成员 | 本轮输出与文件范围 | 实际能力与边界 |
|---|---|---|
| root | S059合同/HTTP与原ID重放、S060纯描述审计实现与实际运行、交接与提交 | AAW/router及backend/interfaces/evaluation，Python/SQLite/已有reader；无产品模型调用 |
| engineering（复用） | S059四源与8专项；S060未看逐题数据的方法意见 | 原ResearchProject/Controller/S052、保存IR指标核验；不是S059独审人 |
| capability_review（复用） | S059 6纯机制与3实际case只读独审；S060脚本/原结果独算 | 未参与被审实现，明确mock/实际数据/回执核验的范围；不重跑研究 |

继承成员继续优先复用；若确需新成员，优先Terra/ultra或Luna/max并服从宿主，不能把角色改名算独立审查。专业方法针对当前问题选择：S059同份保存结果的两指标AND；S060配对逐题胜负及leave-one-out影响，不假定独立样本、不算p/CI。相关执行者已读准确Skill路径和索引，采用显式指引fallback，非按人原生挂载/工具权限隔离。

S059新门不改变旧scalar wire或S052固定Recall20 freeze，也不全局约束直接底层调用。S060是已有结果曝露后的描述审计、无原native项目/行动/额度变更；分析核public dev+validation、只输出validation。实际模型闭环仍受S050新增一次未批准请求阻塞，0模型/API不扩额。

## Skill与方法的真实状态

- `adaptive-agent-workflow` v0.3.1，固定上游 `02e72e3e411bec53db2288651df01afb27d8904d`；完整七文件（含checkpoint脚本）已替换到本机用户Skill目录并逐字节核验，native discovery有效。root及实际执行/独审负责人显式读取新版SKILL/runtime-playbook；当前宿主按上游fallback显式执行owner loop，未声称live hooks有效。旧native包已归档，current缩短并保留历史原文。后续平台Skill Library已更新正文，root核SKILL正文（仅YAML引号序列化不同）与runtime-playbook与本地v0.3.1一致；云端Python脚本resource读取未成功，不声称云包所有文件可执行。本机完整7文件已核。
- 项目 `research-dev-router` 通过 `.agent/skills/` 显式读取，不假定宿主扫描。`dev-system` 已归档停用；旧文档提及它不重新授权加载。
- superpowers与K-Dense专业方法已固定版本、静态评估，按需作有限参考；未整体安装或挂载给子代理。`hypothesis-generation`不适合作为自动假设评分/选择引擎；绘图/API、任意表达式执行和全库启动hook未启用。
- 子代理接口没有按人注入Skill或单独限制工具的参数；采用显式读取和任务/文件范围，不能声称原生挂载或权限隔离。
- 三项自主研究参考重新取回指定commit并读实际代码；保留许可和负例，采用原生JSON/SQLite和现有候选协议，没有复制受限/许可不明代码。

成功标准是可使用的自主决策与接续能力、真实结果绑定和可核验证据；不是角色数量、流程步骤或检查数量。工程构造数据与回复不作为模型或科研效果证据，旧研究额度和费用unknown边界保持。
