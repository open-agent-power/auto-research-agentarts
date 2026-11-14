# 本轮开发组织与能力

本轮为用户再次授权后的**持续执行阶段**。三小时任务用于对齐和汇报；执行窗口内继续实现、验证和必要独审，不以一个增量结束作为自动停止依据，也不声称会话结束后有常驻模型。

## 工作区与所有权

源基线 `ea3d92e9ebb194262170a4cc56bb0cb838a97b04`，origin 为 `open-agent-power/auto-research-agentarts`。新 checkout 在 `/workspace/development-continuation-20261114/auto-research-agentarts`。原 `/workspace/auto-research-agentarts`、参考原盘、S041 v2合同和历史 runs 不可见；这是源码续作，绝非历史研究恢复。原全局执行者/lease 状态 unknown；仅此新工作树使用 `project_autonomy_guard.py`、当前独有 owner `root-evaluation-20261115T0042`（前owner已release）。修改、执行和提交前 heartbeat，结束 release。

宿主最多并发7人。本轮实际建立6人可复用池（含root），不为小目标再开新人；角色可调整，独审不由实现者兼任。同工作树按文件明确单writer，提示边界不是安全沙箱。

| 实际成员 | 本轮输出与文件范围 | 能力状态 |
|---|---|---|
| root | 契约、Controller/HTTP/报告接线、集成测试、文档、提交 | 已读取新版工作流、项目router及相关索引；使用Git/本地执行工具 |
| engineering · Terra/ultra | S047 staged_continuation只读helper及其测试（S042/045已交付） | 已读取工作流、router、相关索引；原生Project/reader复用 |
| workbench_continuation · Terra/ultra | S047 LocalWorkbench固定阶段接续、HTTP和集成测试 | 已读取工作流、现有持久批次及接续合同；新增预览/导入/恢复 |
| research_mechanisms · Terra/ultra | S048负结果经验复用设计；S042反馈策略/S045holdout已交付 | 已读取能力发现方法及上游实际代码；方法参考，不安装上游runtime |
| runtime_evidence · Luna/max | S047独立真实HTTP/跨进程恢复证据，仅ignored runs | 已读取工作流、router、依赖合同；工具实际执行，不编辑产品 |
| capability_review · Terra/ultra（复用） | S046真实原件独核完成；接续S047独审 | 已读取工作流及相关参考、项目代码；未实现被审产品 |

表格记录已经存在的成员及本轮职责，**不表示所有成员始终活跃**。实时状态以宿主agent列表为准，完成成员通过follow-up复用。

## Skill与方法的真实状态

- `adaptive-agent-workflow` v0.3.0，固定上游 `81610ae298ec915eed5b1ff01326c112b0262b28`；六文件已替换到本机用户Skill目录并逐字节核验，native discovery有效。root及负责人显式读取；未开启自动hook。云端Skill Library旧副本仍未通过当前工具替换，不冒称同步成功。
- 项目 `research-dev-router` 通过 `.agent/skills/` 显式读取，不假定宿主扫描。`dev-system` 已归档停用；旧文档提及它不重新授权加载。
- superpowers与K-Dense专业方法已固定版本、静态评估，按需作有限参考；未整体安装或挂载给子代理。`hypothesis-generation`不适合作为自动假设评分/选择引擎；绘图/API、任意表达式执行和全库启动hook未启用。
- 子代理接口没有按人注入Skill或单独限制工具的参数；采用显式读取和任务/文件范围，不能声称原生挂载或权限隔离。
- 三项自主研究参考重新取回指定commit并读实际代码；保留许可和负例，采用原生JSON/SQLite和现有候选协议，没有复制受限/许可不明代码。

成功标准是可使用的自主决策与接续能力、真实结果绑定和可核验证据；不是角色数量、流程步骤或检查数量。工程构造数据与回复不作为模型或科研效果证据，旧研究额度和费用unknown边界保持。
