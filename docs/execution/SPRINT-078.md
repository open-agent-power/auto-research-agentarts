# S078 — 表格研究反馈链的隔离合成预演

以已发布源码 pin `3ba33b62a0d8456fb0d04765285e11d0b7e1195c`、Project core `3bcccb20f6b428795fe7563ba9892af99fa83ed06704923fefe9e3f70c846f0e`，在两个独立的合成 Project/manager 中预演 Bike 协议拟用的原生链。每个输入均为人工生成的 365 行日期与数值，**未下载或读取真实 UCI Bike 数据**；这不是已获批准的真实 Bike 研究，也不证明科研收益、模型采纳或自动科研决策。

两个 Project 各自以 Python `ResearchProject.create` 显式声明 S077 的操作者用途，在 state version 0 将 evidence 上限从 8 收紧到 0，保存计划 v1，经原 Controller 完成 `data.tabular-quality-audit`。质量结果是 365 行、4 列、2 组、最小组 182 行，所选机械检查无 flags。原质量工具的默认反馈是等待；操作者再引用该已完成行动记录具体观察和理由，保存依据及下一步与 v1 不同的计划 v2，并显式选择绑定原质量 action ID/result SHA 的 `data.numeric-association` 候选。关联结果另保存原行动引用的操作者反馈及计划 v3，随后等待。该选择是合成操作者的明确决定，不是产品自动执行的表格假设分支。

| 合成 Project | 总体 r | 组 0 r | 组 1 r | 固定规则结果 |
|---|---:|---:|---:|---|
| `project-0088441b2f9040dca690f2616a3c3d33` | 1.0 | 1.0 | 1.0 | `condition_met`；数值由人工构造，并非真实世界发现。 |
| `project-15e1bbbf3e1e4759aff02434e2f1c17a` | 0.6974091294759049 | 1.0 | null，`constant_predictor` | `unknown`；组数和行数充足不保证组内关联可计算。 |

每个 Project 的原账本分别为 **2/2 合成工具、0 evidence/model/fit**，两例合计 4 次合成工具。独立审查以标准库重算两组合成 Pearson 值，并核原 source/SQLite、质量与关联工件、parent/child、请求及结果摘要绑定、组坐标、计划和预算；没有发现已测范围内的阻断。作者另用纯内存合成值检查正、零、非正加 null/NaN 与布尔值的分支，任一无效值优先为 `unknown`；独审没有重跑该纯函数日志。

作者对每例分别启动新的 Python 调用，使用保存的原 cap、manager import/select、三个 plan、两个 Controller proposal 和两条 feedback 的原 body/ID 重放；重放中阻断所选执行入口，原 Project 状态和各自 8 个 manager 文件的 SHA 均不变。独审**只检查作者保存的原请求、驱动及重放回执，没有自行重放**。`ResearchProject.create` 无请求 ID，Project 被 manager 移动后没有重放 create；未保存进程 PID，因此只声明分开调用，不声明有 PID 对照。未测试进程崩溃或断电恢复。

合成原件、精确命令及限制见 `runs/s076-verification/synthetic-assessment.md`；80 文件冻结清单 `runs/s076-verification/synthetic-freeze.json` SHA-256 `8af21e1467c4d15ba31db9e32124114868866f34a491b282eb2e4f1ac877513b`，独审前后逐项一致。该 80 文件仅覆盖合成证据；pin 工作树 clean 与 core 是独立检查，不把它说成所有源码的 80 项清单。独审范围和独立核算见 `runs/s078-review/independent-assessment.md`。本轮没有失败后改 ID 或重建的情况。

作者进程守卫所选 Host 模型入口、socket connect/create_connection、Ridge/StandardScaler fit 和 evidence-read；重放另守卫所选 adapter execute 及 Project step。这些是**选定入口**的工程检查，不是全网络/所有 fit 哨兵或 OS 隔离。作者全 manager 哈希和独审核算会读取合成 CSV、SQLite 和工件；不称零文件 I/O。历史费用、现金结算、开发时间与 token 未测，保持 unknown。真实 Bike 数据、来源字节身份、独立研究授权和后续计划仍待决定。
