# S134：仅内建合成小时数据的准备与报告重算

本片准备唯一的人工 CSV，不读真实 UCI、任意外部数据或调用者指定源，不联网、不创建 Project，也不调用质量/研究工具、模型、fit 或 dispatcher。公开命令只允许在 `runs/s134-synthetic-time-*` 全新直接子目录 `prepare`，或对原目录 `verify`；不接受 URL、原始文件或任意表格作为输入。输出目录、成员及路径不能是符号链接，原目录不可覆盖；失败保留已有 claim/部分原件，同路径不能重试。这些是可信合作本地约束，不是操作系统沙箱或防敌意并发。

固定合成站 `SYNTHETIC_S1` 和不带时区的虚构无 DST 时钟，闭开窗口 `[2024-02-28T22:00, 2024-03-01T02:00)` 恰好 28 个连续原始小时，包含闰日。CSV 按小时严格升序，字段 `station,year,month,day,hour,x,outcome`；第 5 行 x 为 `NA`、第 10 行 outcome 为空串，其余 x 为从0计数的整数、outcome 为2倍。0 是有效数值，两个缺失状态分别记录；非有限和非法数字、时间超界/重复/缺漏/无效日历、错站、顺序错乱或超限停止，不补行、不改窗。合成专用检查器只接受非负 ASCII 整数字面量，比原生 Python `float()` 的真实词法严格，不能称真实 UCI 数值或时区解析器。

输出 claim、CSV、spec、原生 tabular source packet、机械报告和 receipt 共六文件。report 只含汇总计数，不保存逐行值；绑定人工时钟配置、CSV/spec/packet 原 bytes SHA、source snapshot/scope SHA、生成器与机械重算模块当前源码 SHA 及 tabular 依赖 identity。`verify` 先将重读源与内建固定字节对照、核 packet 所含原资产，再从 CSV **重读重算**报告并对照各原件；prepare 与 verify 共用同一算法，不是独立第二算法。摘要不是签名、来源或许可认证，读取 CSV 会接触整个合成文件，包括数值。源码身份核验也不能证明内存代码未被替换或整个环境已固定。程序完成后目录 fsync 仍可能失败；如果 receipt 已写，落盘状态为 unknown，保留原目录核对，不覆盖或据此断言不存在。

这个 packet 与 S132 的四行 allowlist 不同，不能直接进入 S132 strict 入口；报告也不是自动派发门。未来若做执行前时间门，需另立版本及固定源码身份，按 manager→Project 锁序绑定原 source、报告、配置和 producer，并在 parent/child 提交边界及执行前核原件；漂移后保留原 ID 与预算，不自动重派。该后续工作不自动迁移旧项目，不授权真实 UCI。真实 UCI 的官方站名、观测时区/日界/DST、权利与来源完整性仍未确认，本合成时钟不能替代这些证据。

作者与独立合成专项各11/11，独立prepare/verify六文件逐字一致；独立标准库从CSV重算28小时、26完整对/2排除及原件身份。固定 HEAD `00f69edf222a9af1717c8c4ad22e55b8fca8e14d` 加候选206项清单 SHA `1c9983f1a2c1130384c6c48c3372b31b530c62ebd715eff2d89af55c9f2a1514`；packet SHA `e0930f259b942f03ba044bdd3e5dcf1a75f49cf14fe764e07b2e495c1be157e9`、report SHA `1d18eeb4c6fccfcf8675c235fb8c4e0d0028366da3a4f54ab9f15e2ccda59772`。独立日志见 `runs/s134-independent-review/`。公开和原始材料均为人工构造，不是科学发现或经验迁移。
